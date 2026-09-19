"""Preuve du livrable « onglet En jeu alimenté pour 20 cartes de test » (mission `v4-jeu`,
définition de fini). Script ponctuel, non exécuté par la suite pytest (comme les autres
`scripts/*_manual.py` et `scripts/prove_insights_20_cards.py`) : le rapprochement Limitless TCG
appelle le vrai site en réseau — une suite automatisée doit rester déterministe et hors ligne
(voir `tests/test_ingame_tournaments.py`).

Les 20 cartes ci-dessous sont des cartes réelles, choisies pour couvrir chaque catégorie de la
règle des Prix (standard, ex, VSTAR, VMAX) et plusieurs types de carte (Pokémon, Dresseur). Le
nom d'extension et la date de sortie de chacune sont ceux réellement publiés par Limitless TCG
(`client.list_sets()`, appelé une fois pour tout le lot, comme le ferait le relevé périodique
réel) — c'est exactement l'information qu'un catalogue importé depuis TCGdex contiendrait aussi
pour la même extension (même calendrier officiel), donc un bon substitut pour cette preuve.

Aucune clé IA réelle sur chimera (D4) : la synthèse est simulée par `_simulate_study`, qui ne
fait que composer un texte à partir du profil déterministe (légalités choisies pour la preuve,
règle des Prix réelle, decklists réellement récupérées) — jamais un appel IA réel.
"""

import asyncio

from pbm_api.ingame.rules import prize_rule_of
from pbm_api.ingame.tournaments import LimitlessTcgClient, find_card_page, parse_decklists

# (nom anglais réel, code d'extension Limitless, numéro dans l'extension, catégorie)
CARDS = [
    ("Charizard ex", "ASC", "22", "Pokemon"),
    ("Pikachu ex", "30C", "53", "Pokemon"),
    ("Mewtwo", "30C", "63", "Pokemon"),
    ("Gardevoir ex", "ASC", "89", "Pokemon"),
    ("Miraidon ex", "ASC", "73", "Pokemon"),
    ("Koraidon ex", "ASC", "121", "Pokemon"),
    ("Chien-Pao ex", "PAF", "242", "Pokemon"),
    ("Iron Hands ex", "PRE", "31", "Pokemon"),
    ("Gholdengo ex", "PRE", "164", "Pokemon"),
    ("Roaring Moon ex", "PRE", "162", "Pokemon"),
    ("Rare Candy", "MEG", "125", "Trainer"),
    ("Nest Ball", "PAF", "84", "Trainer"),
    ("Ultra Ball", "30C", "128", "Trainer"),
    ("Boss's Orders", "ASC", "183", "Trainer"),
    ("Professor's Research", "BLK", "85", "Trainer"),
    ("Arceus VSTAR", "BRS", "123", "Pokemon"),
    ("Giratina VSTAR", "LOR", "131", "Pokemon"),
    ("Lugia VSTAR", "SIT", "139", "Pokemon"),
    ("Rayquaza VMAX", "CRZ", "101", "Pokemon"),
    ("Snorlax", "30C", "119", "Pokemon"),
]


def _simulate_study(name: str, prize_label: str, decks: list) -> str:
    if decks:
        top = decks[0]
        return (
            f"Rôle : vu en tournoi ({top.tournament_name}, {top.placement}). "
            f"Règle des Prix : {prize_label}."
        )
    return f"Rôle : aucune présence en tournoi relevée à ce jour. Règle des Prix : {prize_label}."


async def main() -> None:
    client = LimitlessTcgClient()
    try:
        sets = await client.list_sets()
        sets_by_code = {s.code: s for s in sets}

        ready = 0
        for name, set_code, number, supertype in CARDS:
            set_info = sets_by_code.get(set_code)
            if set_info is None:
                print(f"{name:24s} status=set_introuvable ({set_code})")
                continue

            found = await find_card_page(
                client,
                sets=sets,
                set_release_date=set_info.release_date,
                set_name=set_info.name,
                card_number=number,
                expected_en_name=name,
            )
            prize = prize_rule_of(card_name=name, supertype=supertype)

            if found is None:
                print(f"{name:24s} status=unavailable prize={prize.label}")
                continue

            _url, html_page = found
            decks = parse_decklists(html_page)
            study = _simulate_study(name, prize.label, decks)
            ready += 1
            print(f"{name:24s} status=checked   decks={len(decks)} prize={prize.label}")
            print(f"    étude simulée : {study}")

        print(f"\n{ready}/{len(CARDS)} cartes rapprochées avec succès sur Limitless TCG.")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
