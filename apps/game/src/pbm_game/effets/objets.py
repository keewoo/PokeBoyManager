"""Transition « jouer un Objet » — le script d'effet d'une carte Objet se résout (j-cartes-objets).

Module **pur** (aucune E/S). Il branche le **langage d'effets** sur un coup de joueur : jouer une
carte Objet (R-5.5), autant de fois qu'on veut pendant son tour. La carte quitte la main pour la
défausse, puis son script DSL se résout — recherche dans la pioche, pioche, défausse, soin,
déplacement d'énergie, changement d'Actif, et **appât** (sortir l'Actif adverse du banc).

Comme :mod:`pbm_game.banc.mouvements`, la transition s'enregistre elle-même dans le ``REGISTRE`` du
journal **en bas de ce module**, et ``pbm_game`` importe ``effets.objets`` à son chargement pour que
``appliquer`` la reconnaisse. Les imports du DSL sont **locaux** (dans la fonction) : le noyau des
transitions ne dépend pas du paquet ``effets`` à son chargement, il le tire à l'usage — même motif
que :mod:`pbm_game.combat.attaque`.

**L'appât et le bus (le risque nommé par la fiche).** Quand le script force un Pokémon à devenir
Actif, le DSL le **note** (``ResultatProgramme.devenus_actifs``).
La transition reporte cette liste dans l'événement :data:`~pbm_game.journal.modele.EVT_OBJET_JOUE`
(champ ``devient_actif``), pour que l'orchestrateur — qui seul connaît les réacteurs des cartes en
jeu — publie :data:`~pbm_game.effets.evenements.EJ_DEVIENT_ACTIF` sur le bus
(:func:`~pbm_game.effets.bus.publier_devient_actif`). La transition reste pure et sans bus : elle ne
peut pas connaître les talents abonnés (ils dépendent des decks en présence), mais elle **transmet
le moment** au lieu de l'avaler — sans quoi les déclencheurs « quand ce Pokémon devient Actif… »
seraient oubliés.
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import ACTION_JOUER_OBJET, EVT_OBJET_JOUE, Action, Evenement
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


def appliquer_jouer_objet(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``jouer_objet`` : défausse la carte, résout son script, renvoie état + événements.

    Gardes serveur (le serveur tient les règles seul) : partie vivante (R-14.6, en plus de la garde
    centrale d'``appliquer``), carte réellement en main (sinon ``ValueError``, D9), coût **payable**
    avant de rien résoudre (jamais un demi-effet). Les verrous posés par un ``empecher`` du script
    rejoignent ``etat.verrous`` (sans re-journaliser : la primitive a déjà émis son événement).
    ``rng`` sert aux pile-ou-face du script (tirages rejouables).
    """
    from .dsl.chargement import charger_programme
    from .dsl.contexte import ContexteEffet
    from .dsl.interprete import cout_payable, executer_programme
    from .pile import SourceEffet
    from .verrous import VERROUS_VIDES, JeuDeVerrous

    if etat.terminee:
        raise ValueError("Partie terminée : aucun Objet n'est joué (R-14.6).")
    jid = action.auteur
    params = action.params
    carte_main = params.get("carte_main")
    if not isinstance(carte_main, str) or not carte_main:
        raise ValueError("« carte_main » (instance_id de l'Objet en main) est requise (R-5.5).")
    programme_brut = params.get("programme")
    if programme_brut is None:
        raise ValueError(
            "Objet sans script : un effet non implémenté n'est jamais approximé (R-15.12/D9)."
        )
    programme = charger_programme(programme_brut)

    index, joueur = _joueur(etat, jid)
    carte = next((c for c in joueur.main if c.instance_id == carte_main), None)
    if carte is None:
        raise ValueError(
            f"Objet « {carte_main} » absent de la main de « {jid} » : on ne joue pas une carte "
            "qu'on n'a pas (R-5.5)."
        )

    source_brut = params.get("source") or {}
    source = SourceEffet(
        libelle=str(source_brut.get("libelle") or params.get("nom") or "Objet"),
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

    # La carte Objet quitte la main pour la défausse AVANT la résolution : son texte « coûte N
    # autres cartes » ne doit pas pouvoir se défausser elle-même (R-5.5). Le coût se vérifie donc
    # sur la main **sans** l'Objet (jamais un demi-effet : D9).
    main = tuple(c for c in joueur.main if c.instance_id != carte_main)
    joueur = replace(joueur, main=main, defausse=joueur.defausse + (carte,))
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    etat = replace(etat, joueurs=(joueurs[0], joueurs[1]))

    if programme.cout and not cout_payable(etat, programme.cout, ctx):
        raise ValueError(
            f"Objet « {source.libelle} » : son coût ne peut pas être payé — il n'aurait pas dû "
            "être proposé (R-5.5/D9)."
        )

    # Mode **décision** (branché par le service, lot j-effets-cablage-service, reste-à-faire
    # « injecter la demande de décision ») : chaque ``choisir`` du script devient une **fenêtre de
    # décision réelle** adressée au joueur (:func:`~pbm_game.demandes.moteur.demarrer_resolution`),
    # au lieu d'un choix tranché d'office. La partie se met en pause (``etat.resolution``) et
    # reprend
    # à la réponse (``repondre_demande``). Le drapeau n'est posé que par le service (jamais par le
    # client ni le générateur : il changerait l'appartenance au coup légal) — les tests du moteur et
    # les bots gardent la résolution déterministe (``strategie_canonique``).
    evenement = Evenement(
        EVT_OBJET_JOUE,
        {"joueur": jid, "ref": carte.ref, "nom": source.libelle, "carte": carte.instance_id,
         "devient_actif": []},
    )
    if params.get("decisions"):
        from ..demandes.moteur import demarrer_resolution
        from .dsl.interprete import compiler_en_effet
        from .pile import PileEffets

        effet = compiler_en_effet(programme, ctx, libelle=source.libelle, regle="R-5.5")
        etat, evts = demarrer_resolution(etat, PileEffets((effet,)), rng)
        return etat, [evenement, *evts]

    resultat = executer_programme(etat, programme, ctx, rng)
    etat = resultat.etat
    if resultat.verrous:
        base = etat.verrous if etat.verrous is not None else VERROUS_VIDES
        etat = replace(etat, verrous=JeuDeVerrous(base.verrous + tuple(resultat.verrous)))

    evenement = Evenement(
        EVT_OBJET_JOUE,
        {
            "joueur": jid,
            "ref": carte.ref,
            "nom": source.libelle,
            "carte": carte.instance_id,
            "devient_actif": [list(da) for da in resultat.devenus_actifs],
        },
    )
    return etat, [evenement, *resultat.evenements]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête du module) : ``appliquer``
# reconnaît désormais ``jouer_objet``, qui est donc journalisé et rejouable.
REGISTRE[ACTION_JOUER_OBJET] = appliquer_jouer_objet


__all__ = ["appliquer_jouer_objet"]
