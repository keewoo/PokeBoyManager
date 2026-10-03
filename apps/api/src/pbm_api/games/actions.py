"""Sérialisation des **actions légales** d'un joueur pour un client (lot `j-plateau-interactions`).

Le moteur `pbm_game.actions` est pur et fait autorité : il dit ce qui est jouable
(`actions_legales`) et pourquoi un coup est refusé (`valider`). Ce module est l'**adaptateur**
qui traduit ces objets purs en JSON pour la vue projetée, comme `projection.py` adapte la sortie
du moteur. **Aucune règle n'est réécrite ici** : on sérialise ce que le moteur déclare.

Il alimente la vue de deux listes, pour que l'écran **n'ait aucune règle à connaître** :

* ``actions_legales`` — les coups jouables, chacun avec son étiquette lisible et ses cibles
  valides (à illuminer côté écran). C'est la **seule source** de ce que l'interface propose.
* ``actions_refusees`` — les commandes de la palette d'interface qui ne sont **pas** jouables
  dans l'état courant, chacune avec la règle ``R-x.y`` et le message du moteur (`valider`) :
  l'écran les grise en montrant la raison, sans jamais l'inventer.

``irreversible`` marque les coups dont l'écran demande une **confirmation** (ils ne s'annulent
pas une fois validés) : abandonner (R-14.3), terminer le tour (R-5.1 / R-5.7), et — quand leurs
familles seront livrées — attaquer et défausser. C'est une **politique d'affichage** dérivée de
l'état côté serveur (jamais une règle rejouée par le client) : l'écran ne lit qu'un booléen.
"""

from __future__ import annotations

from pbm_game.actions import actions_legales, valider
from pbm_game.actions.familles_jeu import CatalogueJeu, familles_jeu
from pbm_game.actions.modele import ActionLegale, Cible
from pbm_game.journal.modele import ACTION_ABANDONNER, ACTION_AVANCER_PHASE, Action
from pbm_game.state.modele import PHASE_CHECKUP, EtatPartie

#: La **palette de commandes** de l'interface — les coups « boutons » qu'un joueur peut tenter
#: hors ciblage (``type``, ``params``, libellé de repli). Sa seule raison d'être : savoir, quand
#: un de ces coups n'est **pas** jouable, en demander la raison au moteur (`valider`) pour le
#: griser avec son motif. La légalité et la raison viennent toujours du moteur — ceci n'est qu'une
#: liste de candidats à interroger. Les coups ciblés (attacher, attaquer…) passent par
#: ``actions_legales`` et leurs cibles, pas par cette palette.
PALETTE_COMMANDES: tuple[tuple[str, dict, str], ...] = (
    (ACTION_AVANCER_PHASE, {}, "Passer à la phase suivante"),
    (ACTION_ABANDONNER, {}, "Abandonner la partie"),
)

#: Types de coups **irréversibles** : une fois validés, ils ne s'annulent pas, donc l'écran
#: demande une confirmation. ``avancer_phase`` ne l'est que lorsqu'il **termine le tour** (phase
#: de checkup) — voir :func:`_irreversible`. Les familles ``attaquer`` / ``defausser`` les
#: rejoindront quand elles seront livrées (D9 : on ne les approxime pas, on nomme leur type).
TYPES_IRREVERSIBLES: frozenset[str] = frozenset({ACTION_ABANDONNER, "attaquer", "defausser"})


def _irreversible(type_: str, etat: EtatPartie) -> bool:
    """Vrai si un coup de ce type, dans cet état, demande une confirmation (il ne s'annule pas).

    Dérivé de l'état côté serveur, pas d'une règle rejouée par le client : ``avancer_phase`` n'est
    irréversible que s'il **termine le tour** (depuis la phase de checkup, R-5.1 / R-5.7), là où
    un simple passage de phase se laisse enchaîner sans gravité.
    """
    if type_ == ACTION_AVANCER_PHASE:
        return etat.tour.phase == PHASE_CHECKUP
    return type_ in TYPES_IRREVERSIBLES


def _cible_json(cible: Cible) -> dict:
    """Une cible valide en JSON : son genre, sa référence stable et son libellé lisible."""
    return {"genre": cible.genre, "reference": cible.reference, "etiquette": cible.etiquette}


def _legale_json(legale: ActionLegale, etat: EtatPartie) -> dict:
    """Un coup jouable en JSON : l'action exacte, son libellé, ses cibles, et ``irreversible``."""
    action = legale.action
    return {
        "type": action.type,
        "params": dict(action.params),
        "etiquette": legale.etiquette,
        "cibles": [_cible_json(c) for c in legale.cibles],
        "irreversible": _irreversible(action.type, etat),
    }


def _est_legale(action: Action, legales: tuple[ActionLegale, ...]) -> bool:
    """Vrai si ``action`` figure dans la liste légale — par **égalité**, comme le fait le moteur.

    ``Action`` porte un ``dict`` de paramètres : elle n'est pas hachable, d'où la comparaison
    terme à terme plutôt qu'un ensemble.
    """
    return any(coup.action == action for coup in legales)


def actions_pour(etat: EtatPartie, joueur: str, catalogue_jeu: CatalogueJeu | None = None) -> dict:
    """Les actions d'un joueur pour la vue : ``{"legales": [...], "refusees": [...]}``.

    ``legales`` vient de `pbm_game.actions.actions_legales` (source de vérité), avec les **familles
    du jeu** (``familles_jeu``) dès qu'un ``catalogue_jeu`` est fourni : poser, évoluer, attacher,
    attaquer, battre en retraite, promouvoir, placer. Sans catalogue (partie brute), seules les
    familles sans données de carte s'appliquent. ``refusees`` donne le motif cité d'un refus.
    """
    familles = familles_jeu(catalogue_jeu or CatalogueJeu())
    legales = actions_legales(etat, joueur, familles=familles)
    legales_json = [_legale_json(coup, etat) for coup in legales]

    refusees_json: list[dict] = []
    for type_, params, etiquette in PALETTE_COMMANDES:
        action = Action(type=type_, auteur=joueur, params=dict(params))
        if _est_legale(action, legales):
            continue
        verdict = valider(etat, action, familles=familles)
        if verdict.refuse:
            refusees_json.append(
                {
                    "type": type_,
                    "params": dict(params),
                    "etiquette": etiquette,
                    "regle": verdict.regle,
                    "message": verdict.message,
                    "irreversible": _irreversible(type_, etat),
                }
            )
    return {"legales": legales_json, "refusees": refusees_json}
