"""Pose le **rendu** de chaque carte sur la vue projetée d'une partie (lot ``j-rendu-carte``).

Le moteur ne connaît ni image ni URL : sa projection (``pbm_game.state.projection``) ne décrit une
carte que par son ``instance_id`` et sa ``ref``. Ce module, côté API, ajoute à chaque carte visible
un champ ``rendu`` — ``{origine, url, url_zoom, credit, raison}`` — résolu par
:mod:`pbm_api.jeu.rendu_service` pour **ce regard-là**.

Pourquoi côté serveur et pas côté écran : la photo d'un joueur ne doit partir chez l'adversaire que
si son propriétaire l'a voulu (DJ5). Si l'écran choisissait entre « ma photo » et « l'officielle »,
le réglage de confidentialité ne serait qu'une politesse — l'URL de la photo aurait déjà été
envoyée. Ici, une photo qui ne doit pas être montrée n'a **aucune** URL dans la charge utile.

Le **propriétaire** d'une carte est le joueur dans la zone duquel elle se trouve ; pour le Stade,
c'est ``stade_proprietaire`` (R-7.4 : un Stade posé reste la carte de celui qui l'a jouée). Les
zones **cachées** ne portent aucune carte dans la vue (elles sont déjà réduites à un nombre à la
source) : il n'y a donc rien à enrichir, et rien à révéler — c'est l'écran qui dessine un **dos**
de carte quand il doit en montrer une face cachée.
"""

from __future__ import annotations

from collections.abc import Iterable

from pbm_api.jeu.rendu_service import RendusPartie


def _cartes_du_pokemon(pokemon_vue: dict) -> Iterable[dict]:
    """Toutes les cartes d'un Pokémon en jeu : sa pile d'évolutions, ses énergies, son Outil."""
    yield from pokemon_vue.get("cartes", ())
    yield from pokemon_vue.get("energies", ())
    if pokemon_vue.get("outil") is not None:
        yield pokemon_vue["outil"]


def _cartes_du_joueur(joueur_vue: dict) -> Iterable[dict]:
    """Les cartes **visibles** d'un joueur : en jeu, défaussées, en zone perdue, en main (soi)."""
    if joueur_vue.get("actif") is not None:
        yield from _cartes_du_pokemon(joueur_vue["actif"])
    for pokemon in joueur_vue.get("banc", ()):
        yield from _cartes_du_pokemon(pokemon)
    yield from joueur_vue.get("defausse", ())
    yield from joueur_vue.get("zone_perdue", ())
    # ``main`` n'existe que pour soi (anti-fuite côté moteur) : rien à tester ici, son
    # absence suffit — on n'enrichit que ce que la projection a laissé passer.
    yield from joueur_vue.get("main", ())


def enrichir_rendu(vue: dict, rendus: RendusPartie) -> dict:
    """Ajoute ``rendu`` à chaque carte visible de ``vue`` (mutée en place), puis rend ``vue``.

    Sans rendu résolu pour une carte (ref inconnue du catalogue, donc sans même d'image officielle),
    le champ est **absent** plutôt que nul : l'écran retombe alors sur son repère texte, et on
    n'invente aucune image (D9).
    """
    if not rendus:
        return vue
    regard = vue.get("pour")
    if not isinstance(regard, str):
        return vue

    for joueur_vue in vue.get("joueurs", ()):
        proprietaire = joueur_vue.get("id")
        if not isinstance(proprietaire, str):
            continue
        for carte in _cartes_du_joueur(joueur_vue):
            rendu = rendus.pour(regard, proprietaire, carte.get("ref", ""))
            if rendu is not None:
                carte["rendu"] = rendu

    stade = vue.get("stade")
    proprietaire_stade = vue.get("stade_proprietaire")
    if isinstance(stade, dict) and isinstance(proprietaire_stade, str):
        rendu = rendus.pour(regard, proprietaire_stade, stade.get("ref", ""))
        if rendu is not None:
            stade["rendu"] = rendu

    # Les cartes d'une fenêtre de décision (lot ``j-plateau-decisions``) : leurs options ne sont
    # exposées qu'à leur **destinataire**, qui est donc le regard courant — et ce sont ses cartes
    # qu'on lui fait chercher. Un ensemble caché n'a pas d'``options_cartes`` : rien à enrichir.
    demande = vue.get("demande")
    if isinstance(demande, dict):
        for option in demande.get("options_cartes", ()):
            rendu = rendus.pour(regard, regard, option.get("ref", ""))
            if rendu is not None:
                option["rendu"] = rendu

    return vue


__all__ = ["enrichir_rendu"]
