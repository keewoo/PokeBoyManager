"""Joue **une** partie complète entre deux bots, et débusque toute anomalie — sans repli silencieux.

C'est l'organe qui tient le rôle que le service de parties (``apps/api``) tiendra en production :
il enchaîne les coups **système** entre les tours (mise en place, pioche de début de tour, Pokémon
Checkup) et demande aux **bots** leurs coups de joueur — chaque bot ne voyant que sa
:func:`~pbm_game.state.vue`. Après **chaque** coup, il contrôle les invariants de l'état ; à la fin,
il rejoue le journal et compare l'empreinte. Tout ce qui cloche devient une :class:`Anomalie`
nommée, jamais un ``continue`` muet (le risque explicite de la fiche : une partie « trop longue »
est la forme que prend une boucle d'effets, pas un artefact à ignorer).

Une partie est **entièrement déterminée par sa graine**
(:func:`pbm_sim.decks.scenario_depuis_graine`) : :func:`jouer_partie` ne prend qu'elle. Rejouer la
même graine redonne exactement la même partie — c'est ce qui rend une anomalie reproductible en une
commande (``python -m pbm_sim reproduire <graine>``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import _fiches, familles_jeu
from pbm_game.journal import (
    ACTION_AVANCER_PHASE,
    ACTION_CHECKUP,
    ACTION_DEBUT_TOUR,
    AUTEUR_SYSTEME,
    Action,
    Partie,
    empreinte,
    jouer,
    partie_neuve,
    rejouer,
)
from pbm_game.journal.modele import ACTION_MISE_EN_PLACE_INITIALE
from pbm_game.rng import Rng
from pbm_game.state import PHASE_CHECKUP, PHASE_PIOCHE, Carte, EtatPartie, Joueur, Tour, vue
from pbm_game.state.invariants import verifier

from .bots import par_nom
from .decks import CATALOGUE, TAILLE_DECK, Scenario, scenario_depuis_graine

# --- Types d'anomalie (chaînes stables : elles sont publiées, groupées, comptées) ---------------
#: L'état viole un invariant après un coup (carte dupliquée, banc > 5, compteurs négatifs…).
ANOMALIE_ETAT_INVALIDE = "etat_invalide"
#: Un coup — légal, ou système — a levé une exception en s'appliquant.
ANOMALIE_EXCEPTION = "exception"
#: Un point de décision sans aucun coup jouable : la partie est coincée sans être finie.
ANOMALIE_BLOCAGE = "blocage"
#: La partie n'a pas fini sous le plafond de coups : une boucle probable (le risque de la fiche).
ANOMALIE_PARTIE_SANS_FIN = "partie_sans_fin"
#: Le rejeu du journal ne redonne pas l'état final : le déterminisme est cassé.
ANOMALIE_REJEU_DIVERGENT = "rejeu_divergent"
#: Une demande de décision est en attente alors que le harnais J2 ne sait pas en piloter : les
#: decks de simulation n'en produisent pas (attaques à dégâts secs, énergies de base). Si une
#: apparaît, c'est un fait à regarder, pas à avaler silencieusement.
ANOMALIE_DEMANDE_INATTENDUE = "demande_inattendue"

#: Plafond de coups par défaut avant de déclarer une partie « sans fin ». Avec des decks de 60
#: cartes, une partie se termine au pire par pioche vide (R-14.2) vers ~120 tours, soit quelques
#: centaines de coups ; 3000 laisse une marge franche — l'atteindre dénonce une vraie boucle.
MAX_PAS_DEFAUT = 3000


@dataclass(frozen=True)
class Anomalie:
    """Une anomalie trouvée pendant une partie — nommée, datée au coup près, et reproductible.

    * ``type`` — un des ``ANOMALIE_*`` ;
    * ``graine`` — la graine du scénario : la rejouer reproduit exactement la partie ;
    * ``pas`` — le numéro du coup où l'anomalie est apparue (−1 si hors d'un coup précis) ;
    * ``message`` — l'explication lisible (violation(s), exception, blocage…).
    """

    type: str
    graine: str
    pas: int
    message: str


@dataclass
class ResultatPartie:
    """Le compte rendu d'**une** partie simulée — ce qu'une campagne agrège.

    ``partie`` n'est rempli que si ``garder_partie=True`` (coûteux en mémoire : une campagne de
    masse ne le garde pas ; la reproduction d'une anomalie, si).
    """

    graine: str
    deck0: str
    deck1: str
    bot0: str
    bot1: str
    terminee: bool = False
    vainqueur: str | None = None
    raison_fin: str | None = None
    tours: int = 0
    pas: int = 0
    anomalies: list[Anomalie] = field(default_factory=list)
    partie: Partie | None = None

    @property
    def saine(self) -> bool:
        """Vrai si la partie s'est terminée **sans** la moindre anomalie."""
        return self.terminee and not self.anomalies


def _etat_initial(scenario: Scenario) -> EtatPartie:
    """Deux decks en pioche, tour 1 phase pioche au siège 0 (le joueur qui commence, R-6.1).

    Le moteur mélange lui-même à la mise en place (R-4.1) : l'ordre des ``ref`` ici n'influe pas.
    Les ``instance_id`` sont uniques par joueur, condition d'un état sain (aucune carte en double).
    """
    j0 = Joueur(
        id=scenario.JOUEUR_0,
        pioche=tuple(
            Carte(instance_id=f"{scenario.JOUEUR_0}-{i}", ref=r)
            for i, r in enumerate(scenario.deck0.refs())
        ),
    )
    j1 = Joueur(
        id=scenario.JOUEUR_1,
        pioche=tuple(
            Carte(instance_id=f"{scenario.JOUEUR_1}-{i}", ref=r)
            for i, r in enumerate(scenario.deck1.refs())
        ),
    )
    return EtatPartie(
        joueurs=(j0, j1),
        tour=Tour(joueur_actif=scenario.JOUEUR_0, numero=1, phase=PHASE_PIOCHE),
    )


#: Fragment de la violation R-3.3 « banc non vide sans Actif » produite par
#: :func:`pbm_game.state.invariants.verifier`. C'est l'état **transitoire légitime** d'un joueur
#: dont l'Actif vient d'être mis K.O. et qui doit promouvoir à son prochain tour (R-8.7) : le
#: moteur le produit à chaque K.O. et ses PROPRES tests ne vérifient d'ailleurs pas les invariants
#: sur cet état précis (test_ko_recompenses, cas « promotion demandée »). On l'exempte donc du
#: contrôle par coup — mais lui seul, et seulement quand le joueur owe effectivement une promotion.
_MARQUEUR_PROMOTION_DUE = "banc non vide sans Actif"


def _violations_significatives(etat: EtatPartie) -> list[str]:
    """Les violations d'invariant **réelles** d'un état en jeu (R-3.3 transitoire exclu).

    On garde tout ce que :func:`pbm_game.state.invariants.verifier` signale (carte dupliquée, banc
    trop grand, compteurs négatifs, total de cartes qui bouge…), **sauf** la seule « banc non vide
    sans Actif » d'un joueur qui attend réellement de promouvoir (Actif K.O., banc non vide, partie
    non finie) : c'est le transitoire normal entre un K.O. et la promotion du tour suivant. Le
    filtre est **étroit** (un joueur donné, dans cet état précis) : toute autre violation — y
    compris un « banc non vide sans Actif » qui ne correspondrait à aucun joueur en attente —
    passe et devient une anomalie. Jamais un repli silencieux.
    """
    violations = verifier(etat, total_par_joueur=TAILLE_DECK)
    if etat.terminee:
        return violations
    attend_promotion = {
        f"Joueur « {j.id} »" for j in etat.joueurs if j.actif is None and j.banc
    }
    reelles: list[str] = []
    for v in violations:
        due = _MARQUEUR_PROMOTION_DUE in v and any(v.startswith(p) for p in attend_promotion)
        if not due:
            reelles.append(v)
    return reelles


def jouer_partie(
    graine: str,
    *,
    verifier_chaque_pas: bool = True,
    garder_partie: bool = False,
    max_pas: int | None = None,
) -> ResultatPartie:
    """Joue la partie déterminée par ``graine`` jusqu'à sa fin (ou sa première anomalie).

    * ``verifier_chaque_pas`` — contrôle les invariants après **chaque** coup (le défaut : c'est
      ce qui transforme un état impossible en anomalie immédiate plutôt qu'en symptôme lointain) ;
    * ``garder_partie`` — conserve l'objet :class:`~pbm_game.journal.Partie` dans le résultat (pour
      la reproduction : on peut alors dérouler le journal) ;
    * ``max_pas`` — plafond de coups avant de déclarer la partie « sans fin ».

    Ne lève jamais : toute défaillance est **capturée** et rangée dans ``resultat.anomalies`` (une
    exception non rattrapée interromprait une campagne de 10 000 parties au premier pépin). La
    partie s'arrête à la **première** anomalie — l'état est alors suspect, continuer n'aurait pas
    de sens.
    """
    if max_pas is None:
        max_pas = MAX_PAS_DEFAUT
    scenario = scenario_depuis_graine(graine)
    etat = _etat_initial(scenario)
    partie = partie_neuve(etat, scenario.graine_moteur)
    rng = Rng(bytes.fromhex(scenario.graine_moteur))
    familles = familles_jeu(CATALOGUE)
    bots = {
        scenario.JOUEUR_0: par_nom(scenario.bot0),
        scenario.JOUEUR_1: par_nom(scenario.bot1),
    }
    # Un flux d'aléatoire **par joueur**, dérivé de la graine : deux exécutions sous la même graine
    # font les mêmes choix. On ne partage pas un seul flux entre les deux bots, pour que changer
    # l'un ne décale pas les tirages de l'autre.
    alea_bot = {
        scenario.JOUEUR_0: random.Random(f"{graine}:{scenario.JOUEUR_0}"),
        scenario.JOUEUR_1: random.Random(f"{graine}:{scenario.JOUEUR_1}"),
    }

    resultat = ResultatPartie(
        graine=graine,
        deck0=scenario.deck0.nom,
        deck1=scenario.deck1.nom,
        bot0=scenario.bot0,
        bot1=scenario.bot1,
    )

    def avancer(action: Action) -> bool:
        """Applique ``action``, journalise, puis contrôle les invariants. ``False`` = anomalie."""
        nonlocal partie, etat
        try:
            partie, etat = jouer(partie, action, f"t{len(partie.entrees)}", etat, rng)
        except Exception as exc:  # noqa: BLE001 — on VEUT tout attraper : une exception sur un
            # coup légal (ou système) EST l'anomalie qu'on cherche ; la laisser filer tuerait la
            # campagne. On l'archive avec le coup fautif, jamais un repli muet.
            resultat.anomalies.append(
                Anomalie(
                    ANOMALIE_EXCEPTION,
                    graine,
                    len(partie.entrees),
                    f"« {action.type} » par « {action.auteur} » a levé : {exc!r}",
                )
            )
            return False
        if verifier_chaque_pas:
            violations = _violations_significatives(etat)
            if violations:
                resultat.anomalies.append(
                    Anomalie(
                        ANOMALIE_ETAT_INVALIDE, graine, len(partie.entrees), "; ".join(violations)
                    )
                )
                return False
        return True

    def anomalie(type_: str, message: str) -> None:
        resultat.anomalies.append(Anomalie(type_, graine, len(partie.entrees), message))

    def coup_du_bot(jid: str):
        """Demande au bot de ``jid`` son coup, à partir de sa SEULE vue + ses coups légaux."""
        legales = actions_legales(etat, jid, familles)
        return bots[jid](vue(etat, jid), legales, alea_bot[jid])

    # 1) Mise en place système (mélange, pioche de sept, mulligans) — R-4.
    definitions = {"definitions": CATALOGUE.definitions()}
    ok = avancer(Action(ACTION_MISE_EN_PLACE_INITIALE, AUTEUR_SYSTEME, definitions))

    # 2) Boucle d'orchestration — jusqu'à la fin, la première anomalie, ou le plafond de coups.
    while ok and not etat.terminee and not resultat.anomalies:
        if len(partie.entrees) > max_pas:
            anomalie(ANOMALIE_PARTIE_SANS_FIN, f"plus de {max_pas} coups sans fin de partie")
            break

        # Une demande de décision en attente : le harnais J2 ne la pilote pas (decks sans effet).
        if etat.resolution is not None:
            anomalie(
                ANOMALIE_DEMANDE_INATTENDUE,
                f"demande « {etat.resolution.demande.id} » : "
                f"{etat.resolution.demande.libelle} (non pilotable au jalon J2)",
            )
            break

        # Mise en place (R-4) : chaque joueur non encore placé choisit son Actif + banc, via la
        # liste légale (famille « placer ») — depuis sa seule vue.
        if etat.mise_en_place is not None:
            places = etat.mise_en_place.placements
            idx = next((i for i, p in enumerate(places) if p is None), None)
            if idx is None:
                anomalie(ANOMALIE_BLOCAGE, "mise en place sans joueur à placer (état incohérent)")
                break
            jid = etat.joueurs[idx].id
            coup = coup_du_bot(jid)
            if coup is None:
                anomalie(ANOMALIE_BLOCAGE, f"aucun placement possible pour « {jid} » (R-4.2)")
                break
            ok = avancer(coup.action)
            continue

        phase = etat.tour.phase
        # Pioche de début de tour : automatique (R-5.2), défaite sur pioche vide (R-14.2).
        if phase == PHASE_PIOCHE:
            ok = avancer(Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME))
            continue
        # Pokémon Checkup (R-12) : coup système, puis le joueur actif termine son tour (R-5.1).
        if phase == PHASE_CHECKUP:
            fiches = {"fiches": _fiches(CATALOGUE, etat)}
            ok = avancer(Action(ACTION_CHECKUP, AUTEUR_SYSTEME, fiches))
            if not ok or etat.terminee or resultat.anomalies:
                continue
            ok = avancer(Action(ACTION_AVANCER_PHASE, etat.tour.joueur_actif))
            continue
        # Phases principale / attaque : le joueur actif joue, sur sa seule vue.
        jid = etat.tour.joueur_actif
        coup = coup_du_bot(jid)
        if coup is None:
            anomalie(ANOMALIE_BLOCAGE, f"aucun coup jouable pour « {jid} » en phase {phase}")
            break
        ok = avancer(coup.action)

    # 3) Bilan : tours, coups, issue.
    resultat.tours = etat.tour.numero
    resultat.pas = len(partie.entrees)
    resultat.terminee = etat.terminee
    resultat.vainqueur = etat.vainqueur
    resultat.raison_fin = etat.raison_fin

    # 4) Tout est rejouable : le journal rejoué doit redonner l'état final à l'empreinte près
    #    (seulement si la partie s'est finie proprement — sinon l'état est déjà suspect).
    if etat.terminee and not resultat.anomalies:
        try:
            etat_rejoue, _ = rejouer(partie)
            if empreinte(etat_rejoue) != empreinte(etat):
                anomalie(ANOMALIE_REJEU_DIVERGENT, "le rejeu ne redonne pas l'état final")
        except Exception as exc:  # noqa: BLE001 — un rejeu qui lève est lui-même l'anomalie.
            anomalie(ANOMALIE_REJEU_DIVERGENT, f"rejeu : {exc!r}")

    if garder_partie:
        resultat.partie = partie
    return resultat


__all__ = [
    "Anomalie",
    "ResultatPartie",
    "jouer_partie",
    "ANOMALIE_ETAT_INVALIDE",
    "ANOMALIE_EXCEPTION",
    "ANOMALIE_BLOCAGE",
    "ANOMALIE_PARTIE_SANS_FIN",
    "ANOMALIE_REJEU_DIVERGENT",
    "ANOMALIE_DEMANDE_INATTENDUE",
    "MAX_PAS_DEFAUT",
]
