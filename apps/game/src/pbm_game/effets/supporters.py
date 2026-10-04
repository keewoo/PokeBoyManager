"""Transition « jouer un Supporter » — le script d'effet d'une carte Supporter se résout.

Module **pur** (aucune E/S), jumeau de :mod:`pbm_game.effets.objets` : il branche le **langage
d'effets** sur un coup de joueur, mais pour une carte **Supporter** (R-5.5). La carte quitte la main
pour la défausse, puis son script DSL se résout — pioche, recherche, **perturbation adverse**
(mélanger sa main dans son deck et la faire repiocher) et effets **conditionnés**
(« si vous avez moins de récompenses »).

**Ce que le Supporter a de plus que l'Objet**, et que cette transition tient côté **serveur** (le
serveur fait autorité, jamais l'écran) :

* **un seul par tour** (R-5.5) et **aucun au premier tour du joueur qui commence** (R-6.2) :
  vérifiés par :func:`~pbm_game.tour.contraintes.peut_jouer_supporter` **avant** de rien résoudre ;
* **interdit sous le verrou** ``pas_de_supporter`` (type *Marnie*
  inversé, un talent adverse) : le refus **nomme la carte responsable**, jamais un refus muet ;
* une fois le Supporter joué, le drapeau ``Tour.supporter_joue`` est **levé**
  (:func:`~pbm_game.tour.drapeaux.marquer_supporter_joue`) — c'est ce drapeau, porté par l'état donc
  sérialisé, qui fait qu'un second Supporter est refusé et **survit à une reprise après un F5**.

Comme ``effets.objets``, la transition s'enregistre dans le ``REGISTRE`` du journal **en bas de ce
module**, ``pbm_game`` l'importe à son chargement, et les imports du DSL sont **locaux** (le noyau
des transitions ne dépend pas du paquet ``effets`` à son chargement). Les Pokémon forcés à devenir
Actifs par le script (un Supporter d'appât, type *Boss's Orders*) sont reportés dans
``EVT_SUPPORTER_JOUE`` (champ ``devient_actif``) pour que l'orchestrateur publie
:data:`~pbm_game.effets.evenements.EJ_DEVIENT_ACTIF` sur le bus — même passage que l'Objet.
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import ACTION_JOUER_SUPPORTER, EVT_SUPPORTER_JOUE, Action, Evenement
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import EtatPartie, Joueur


def _joueur(etat: EtatPartie, jid: str) -> tuple[int, Joueur]:
    for i, j in enumerate(etat.joueurs):
        if j.id == jid:
            return i, j
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _autre(etat: EtatPartie, jid: str) -> str:
    for j in etat.joueurs:
        if j.id != jid:
            return j.id
    raise ValueError(f"Pas d'adversaire pour « {jid} ».")


def appliquer_jouer_supporter(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``jouer_supporter`` : vérifie la règle du tour, résout le script, lève le drapeau.

    Gardes serveur (le serveur tient les règles seul, R-5.5) : partie vivante (R-14.6, en plus de la
    garde centrale d'``appliquer``), **joueur actif** seulement, **un seul Supporter par tour** et
    pas au premier tour du joueur qui commence, **pas sous un verrou**
    ``pas_de_supporter``, carte réellement en main (sinon ``ValueError``,
    D9), coût **payable** avant de rien résoudre (jamais un demi-effet). Les verrous posés par un
    ``empecher`` du script rejoignent ``etat.verrous``. En sortie, ``Tour.supporter_joue`` est levé.
    """
    from ..tour.contraintes import peut_jouer_supporter
    from ..tour.drapeaux import marquer_supporter_joue
    from .dsl.chargement import charger_programme
    from .dsl.contexte import ContexteEffet
    from .dsl.interprete import cout_payable, executer_programme
    from .pile import SourceEffet
    from .verrous import VERROU_PAS_DE_SUPPORTER, VERROUS_VIDES, JeuDeVerrous

    if etat.terminee:
        raise ValueError("Partie terminée : aucun Supporter n'est joué (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif joue un Supporter ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.5)."
        )

    # R-5.5 / R-6.2 — un seul Supporter par tour, aucun au premier tour du joueur qui commence.
    verdict = peut_jouer_supporter(etat.tour)
    if verdict.refuse:
        # Le refus **cite la règle** (R-5.5 déjà joué, R-6.2 premier tour), comme tout refus moteur.
        raise ValueError(f"{verdict.message} ({verdict.regle})")

    # R-5.5 — un verrou « pas de Supporter ce tour » (type Marnie inversé, talent adverse) interdit
    # le coup en **nommant** la carte responsable (jamais un refus muet, comme la garde d'attaque).
    if etat.verrous is not None and etat.verrous.est_verrouille(VERROU_PAS_DE_SUPPORTER, cible=jid):
        src = etat.verrous.source_du_verrou(VERROU_PAS_DE_SUPPORTER, cible=jid)
        nom = src.libelle if src is not None else "un effet"
        raise ValueError(
            f"Aucun Supporter ne peut être joué ce tour — bloqué par « {nom} » (R-5.5)."
        )

    params = action.params
    carte_main = params.get("carte_main")
    if not isinstance(carte_main, str) or not carte_main:
        raise ValueError("« carte_main » (instance_id du Supporter en main) est requise (R-5.5).")
    programme_brut = params.get("programme")
    if programme_brut is None:
        raise ValueError(
            "Supporter sans script : un effet non implémenté n'est jamais approximé (R-15.12/D9)."
        )
    programme = charger_programme(programme_brut)

    index, joueur = _joueur(etat, jid)
    carte = next((c for c in joueur.main if c.instance_id == carte_main), None)
    if carte is None:
        raise ValueError(
            f"Supporter « {carte_main} » absent de la main de « {jid} » : on ne joue pas une carte "
            "qu'on n'a pas (R-5.5)."
        )

    source_brut = params.get("source") or {}
    source = SourceEffet(
        libelle=str(source_brut.get("libelle") or params.get("nom") or "Supporter"),
        ref=source_brut.get("ref", carte.ref),
        instance_id=source_brut.get("instance_id", carte.instance_id),
    )
    metadonnees = params.get("metadonnees")
    ctx = ContexteEffet(
        source=source,
        joueur=jid,
        adversaire=_autre(etat, jid),
        metadonnees=metadonnees if isinstance(metadonnees, dict) else {},
    )

    # La carte Supporter quitte la main pour la défausse AVANT la résolution (R-5.5) : « mélangez
    # votre main dans votre deck » ne doit pas se remettre elle-même, et le coût se vérifie sur la
    # main **sans** le Supporter (jamais un demi-effet : D9).
    main = tuple(c for c in joueur.main if c.instance_id != carte_main)
    joueur = replace(joueur, main=main, defausse=joueur.defausse + (carte,))
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    etat = replace(etat, joueurs=(joueurs[0], joueurs[1]))

    if programme.cout and not cout_payable(etat, programme.cout, ctx):
        raise ValueError(
            f"Supporter « {source.libelle} » : son coût ne peut pas être payé — il n'aurait pas dû "
            "être proposé (R-5.5/D9)."
        )

    resultat = executer_programme(etat, programme, ctx, rng)
    etat = resultat.etat
    if resultat.verrous:
        base = etat.verrous if etat.verrous is not None else VERROUS_VIDES
        etat = replace(etat, verrous=JeuDeVerrous(base.verrous + tuple(resultat.verrous)))

    # R-5.5 — le Supporter du tour est consommé : on lève le drapeau (porté par l'état, donc
    # sérialisé → un second Supporter sera refusé, et le drapeau survit à une reprise après un F5).
    etat = replace(etat, tour=marquer_supporter_joue(etat.tour))

    evenement = Evenement(
        EVT_SUPPORTER_JOUE,
        {
            "joueur": jid,
            "ref": carte.ref,
            "nom": source.libelle,
            "carte": carte.instance_id,
            "devient_actif": [list(da) for da in resultat.devenus_actifs],
        },
    )
    return etat, [evenement, *resultat.evenements]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête) : ``appliquer`` reconnaît
# désormais ``jouer_supporter``, qui est donc journalisé et rejouable.
REGISTRE[ACTION_JOUER_SUPPORTER] = appliquer_jouer_supporter


__all__ = ["appliquer_jouer_supporter"]
