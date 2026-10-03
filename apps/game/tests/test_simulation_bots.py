"""Les bots décident sur la **seule vue joueur** — jamais l'état complet (règle d'or du lot).

On vérifie trois choses, chacune un critère du lot :

1. **vue seulement** : les fonctions de décision ne reçoivent pas d'``EtatPartie`` (leur signature
   n'a pas de paramètre ``etat``) — un bot ne peut pas tricher sur ce qu'il ne reçoit pas ;
2. **appartenance** : tout coup choisi appartient à la liste légale fournie (le bot ne fabrique
   jamais un coup), et jamais l'abandon tant qu'un autre coup existe ;
3. **stratégies** : l'heuristique attaque pour le plus de dégâts et promeut le Pokémon le moins
   amoché (R-8.7) ; l'aléatoire est **reproductible** sous une graine donnée.
"""

from __future__ import annotations

import inspect
import random

from pbm_game.actions import ActionLegale, Cible
from pbm_game.actions.modele import GENRE_POKEMON_EN_JEU
from pbm_game.journal import Action
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_PROMOUVOIR,
)
from pbm_sim.bots import bot_aleatoire, bot_heuristique


def _attaque(degats: int) -> ActionLegale:
    return ActionLegale(
        action=Action(ACTION_DECLARER_ATTAQUE, "A", {"attaque": {"degats": degats, "effet": ""}}),
        etiquette=f"Attaquer ({degats})",
    )


def _avancer() -> ActionLegale:
    return ActionLegale(action=Action(ACTION_AVANCER_PHASE, "A"), etiquette="Avancer")


def _abandon() -> ActionLegale:
    return ActionLegale(action=Action(ACTION_ABANDONNER, "A"), etiquette="Abandonner")


def _attacher() -> ActionLegale:
    return ActionLegale(action=Action(ACTION_ATTACHER_ENERGIE, "A", {}), etiquette="Attacher")


def _promouvoir(banc_index: int, identite: str) -> ActionLegale:
    return ActionLegale(
        action=Action(ACTION_PROMOUVOIR, "A", {"banc_index": banc_index}),
        etiquette="Promouvoir",
        cibles=(Cible(GENRE_POKEMON_EN_JEU, identite, "X"),),
    )


def _vue_avec_banc(degats_par_identite: dict[str, int]) -> dict:
    """Une vue minimale où « A » a un banc dont chaque Pokémon porte les compteurs donnés."""
    banc = [
        {"cartes": [{"instance_id": iid, "ref": "x"}], "energies": [], "outil": None,
         "compteurs_degats": d, "etats_speciaux": [], "orientation": "normale"}
        for iid, d in degats_par_identite.items()
    ]
    return {
        "pour": "A",
        "joueurs": [
            {"id": "A", "actif": None, "banc": banc},
            {"id": "B", "actif": None, "banc": []},
        ],
    }


def test_les_bots_ne_recoivent_jamais_l_etat_complet():
    """Critère « sur la seule vue joueur » : aucune signature de bot n'expose ``etat``."""
    for bot in (bot_aleatoire, bot_heuristique):
        params = set(inspect.signature(bot).parameters)
        assert "etat" not in params, f"{bot.__name__} reçoit l'état complet : {params}"
        assert params <= {"vue", "legales", "alea"}, f"{bot.__name__} : paramètres {params}"


def test_un_coup_choisi_appartient_toujours_a_la_liste_legale():
    legales = [_avancer(), _attaque(40), _attacher(), _abandon()]
    vue = {"pour": "A", "joueurs": []}
    for bot in (bot_aleatoire, bot_heuristique):
        choix = bot(vue, legales, random.Random("z"))
        assert choix in legales


def test_aucun_bot_n_abandonne_tant_qu_un_autre_coup_existe():
    legales = [_avancer(), _abandon()]
    vue = {"pour": "A", "joueurs": []}
    for bot in (bot_aleatoire, bot_heuristique):
        for i in range(20):  # l'aléatoire aussi : l'abandon est exclu de son tirage
            choix = bot(vue, legales, random.Random(f"g{i}"))
            assert choix.action.type != ACTION_ABANDONNER


def test_heuristique_attaque_pour_le_plus_de_degats():
    """R-9/R-10 — à choix d'attaques, l'heuristique prend la plus forte (vers les 6 récompenses)."""
    legales = [_avancer(), _attaque(20), _attaque(90), _attaque(60)]
    choix = bot_heuristique({"pour": "A", "joueurs": []}, legales)
    assert choix.action.params["attaque"]["degats"] == 90


def test_heuristique_promeut_le_pokemon_le_moins_amoche():
    """R-8.7 — après un K.O., l'heuristique promeut le Pokémon du banc qui a le moins de dégâts."""
    vue = _vue_avec_banc({"sain": 10, "amoche": 80})
    legales = [_promouvoir(0, "amoche"), _promouvoir(1, "sain"), _abandon()]
    choix = bot_heuristique(vue, legales)
    assert choix.cibles[0].reference == "sain"


def test_aleatoire_est_reproductible_sous_une_graine():
    """La même graine ⇒ la même suite de choix : une partie aléatoire reste rejouable."""
    legales = [_avancer(), _attaque(40), _attacher()]
    vue = {"pour": "A", "joueurs": []}
    r1 = random.Random("k")
    r2 = random.Random("k")
    tir1 = [bot_aleatoire(vue, legales, r1).etiquette for _ in range(5)]
    tir2 = [bot_aleatoire(vue, legales, r2).etiquette for _ in range(5)]
    assert tir1 == tir2 and len(tir1) == 5


def test_un_point_de_decision_vide_rend_none():
    """Liste vide ⇒ ``None`` : l'orchestrateur en fait un blocage, jamais un choix inventé."""
    assert bot_aleatoire({"pour": "A"}, [], random.Random("x")) is None
    assert bot_heuristique({"pour": "A"}, []) is None
