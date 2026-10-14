"""Sème de quoi **jouer une partie entière** à deux navigateurs (lot `j-e2e-deux-navigateurs`,
`apps/web/e2e/partie-deux-navigateurs.spec.ts`) : deux comptes avec le droit d'accès au jeu (D11)
et, pour chacun, un deck **compilable par le moteur et entièrement scripté** (D9).

Pourquoi un seed dédié plutôt que de réutiliser `seed_deck_builder_e2e.py` : ce dernier produit un
deck **légal pour le constructeur** mais pas **jouable par le moteur** — sa carte n'a ni
`prize_marker` ni `retreat_cost`, donc `pbm_api.jeu.catalogue.definition_depuis_card` la refuse et
`GET /matchmaking/decks/{id}/jouabilite` répond `jouable: false` (le bouton « Entrer dans la file »
reste désactivé). Les cartes ci-dessous portent donc tout ce que le moteur exige, et chaque texte
d'effet employé a son programme au registre `card_scripts` — sans quoi D9 refuserait le deck.

**Le deck de chaque joueur est taillé pour que la partie finisse vite, mais légitimement** :

* *Attaquant* (joueur A) — un Pokémon de base à 60 dégâts d'attaque **sans texte d'effet** (aucun
  script requis), plus des Énergies, un Objet et un Supporter dont les textes sont déjà scriptés.
  Les Dresseurs occupent 36 cartes sur 60 : l'ouverture en contient donc presque toujours un, ce
  qui fait jouer un Dresseur dans le parcours sans dépendre d'une graine (la partie créée par la
  file d'attente a une graine **aléatoire**, pas figée).
* *Cible* (joueur B) — **un seul** Pokémon de base à 110 PV **sans attaque**, et 59 Énergies. Il ne
  peut donc jamais mettre A K.O. (la partie ne se termine pas sous le test par l'autre bord), et
  deux attaques de A suffisent à le mettre K.O. Au K.O. de son Actif il n'a plus personne à
  promouvoir : c'est la deuxième voie de victoire de **R-14.1** (adossée à **R-8.9**) — une vraie
  fin de partie, pas un abandon.

**Pourquoi exactement un Pokémon dans le deck B, et pas quatre.** Le générateur de mise en place
propose de mettre au banc **tous** les Pokémon de base restants de la main (mesuré : avec 60 bases
en deck, la seule option offerte est « Actif + banc de 5 »). Un banc garni demanderait douze
attaques pour vider le banc, et c'est **A** qui épuiserait son deck le premier (**R-14.2**) — la
partie finirait par un *deck out* de A, l'inverse de ce que le parcours doit prouver. Avec un
unique exemplaire, le banc de B est vide **par construction**, et la fin arrive en deux attaques.

Le coût de ce choix est une série de mulligans (**R-4.x**) jusqu'à ce que l'unique base soit en
main — et il est **nul en temps de test** : la boucle de mulligan est résolue *à l'intérieur* de
l'action système `mise_en_place_initiale`, en un seul coup journalisé, sans aller-retour HTTP. Les
récompenses étant placées **après** la main (R-4.3), cette carte ne peut pas finir en récompense.

Ne passe PAS par `POST /auth/register` (limité en débit par IP depuis `v5-securite`, compteur
partagé par toutes les specs e2e) : les utilisateurs sont créés directement en base, comme
`seed_game_access_e2e.py`. Le test se connecte ensuite via `POST /auth/login`.

Idempotent — relançable sans dupliquer (upsert par code d'extension, par numéro de carte, par
e-mail, et `enregistrer_script` met à jour l'empreinte existante plutôt que d'en créer une
seconde).

Usage : uv run python scripts/seed_partie_e2e.py <email_a> <email_b> <password>
Sort sur la sortie standard un JSON `{"user_a", "user_b", "deck_a", "deck_b"}` — c'est ainsi que la
spec Playwright récupère les identifiants de deck à présenter au salon.
"""

import asyncio
import json
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select

from pbm_api.db import async_session_factory
from pbm_api.jeu.scripts.depot import enregistrer_script
from pbm_api.legal import CURRENT_TERMS_VERSION
from pbm_api.models import Card, Deck, DeckCard, Set, User
from pbm_api.models.card_scripts import SCRIPT_STATUT_SCRIPTE
from pbm_api.security.passwords import hash_password

SET_CODE = "e2epartie"

#: Textes d'effet employés par les Dresseurs ci-dessous, avec leur programme DSL. Ce sont
#: **mot pour mot** deux entrées de `scripts/seed_effets.json` (donc la même empreinte, et des
#: programmes déjà éprouvés par `test_games_effets_cablage`) : on les réinscrit ici pour que le
#: seed soit autonome — la spec e2e ne peut pas supposer qu'un import de `seed_effets.json` a eu
#: lieu sur la base de CI, qui repart vide à chaque exécution.
TXT_OBJET = "Piochez une carte."
DSL_OBJET = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}
TXT_SUPPORTER = "Piochez 3 cartes."
DSL_SUPPORTER = {"version": 1, "effets": [{"op": "piocher", "nombre": 3}]}

#: Dégâts de l'unique attaque du deck A, et PV de la cible du deck B : deux attaques suffisent
#: (60 + 60 ≥ 110) — assez de tours pour que le parcours en traverse « plusieurs », pas assez pour
#: que l'e2e s'éternise.
DEGATS_ATTAQUE = 60
PV_CIBLE = 110


async def _extension(session) -> Set:
    """L'extension de démonstration du lot, créée au premier passage."""
    row = (await session.execute(select(Set).where(Set.code == SET_CODE))).scalar_one_or_none()
    if row is not None:
        return row
    row = Set(code=SET_CODE, name="Démo partie e2e", series="E2E")
    session.add(row)
    await session.flush()
    return row


async def _carte(session, set_id, number: str, **champs) -> Card:
    """Une carte de l'extension, repérée par son numéro (upsert : relançable sans doublon)."""
    row = (
        await session.execute(select(Card).where(Card.set_id == set_id, Card.number == number))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = Card(set_id=set_id, number=number, **champs)
    session.add(row)
    await session.flush()
    return row


async def _cartes_du_jeu(session) -> dict[str, Card]:
    """Les cinq cartes du lot : l'attaquant, son énergie, son Objet, son Supporter, et la cible.

    Chaque Pokémon porte ce que `definition_depuis_card` exige (`supertype`, `stage`, `hp`,
    `energy_type`, `element_type`, `retreat_cost`, `prize_marker`) : il manquait précisément
    `prize_marker` et `retreat_cost` au seed du constructeur, d'où son deck injouable.
    """
    ext = await _extension(session)
    attaquant = await _carte(
        session, ext.id, "1",
        tcgdex_id="e2epartie-1", name="Attaquant E2E", supertype="Pokémon",
        stage="Base", hp=150, energy_type="metal", element_type="metal",
        retreat_cost=1, prize_marker="ordinaire", rarity="Commune",
        # Attaque à dégâts secs : `effect` vide, donc **aucun script requis** (D9 n'exige un
        # programme que pour un texte d'effet non vide).
        attacks=[
            {"name": "Frappe Nette", "cost": ["metal"], "damage": str(DEGATS_ATTAQUE), "effect": ""}
        ],
        legal_standard=True, legal_expanded=True,
    )
    energie = await _carte(
        session, ext.id, "2",
        tcgdex_id="e2epartie-2", name="Énergie Métal E2E", supertype="Énergie",
        energy_type="Normal", element_type="metal", rarity="Commune",
        legal_standard=True, legal_expanded=True,
    )
    objet = await _carte(
        session, ext.id, "3",
        tcgdex_id="e2epartie-3", name="Note de Recherche E2E", supertype="Dresseur",
        trainer_type="Objet", effect=TXT_OBJET, rarity="Commune",
        legal_standard=True, legal_expanded=True,
    )
    supporter = await _carte(
        session, ext.id, "4",
        tcgdex_id="e2epartie-4", name="Analyste E2E", supertype="Dresseur",
        trainer_type="Supporter", effect=TXT_SUPPORTER, rarity="Commune",
        legal_standard=True, legal_expanded=True,
    )
    cible = await _carte(
        session, ext.id, "5",
        tcgdex_id="e2epartie-5", name="Cible E2E", supertype="Pokémon",
        stage="Base", hp=PV_CIBLE, energy_type="incolore", element_type="incolore",
        retreat_cost=1, prize_marker="ordinaire", rarity="Commune",
        # Aucune attaque : la cible ne peut jamais rendre les coups, donc la partie ne se termine
        # que par la voie que le test pilote.
        attacks=[],
        legal_standard=True, legal_expanded=True,
    )
    return {
        "attaquant": attaquant, "energie": energie, "objet": objet,
        "supporter": supporter, "cible": cible,
    }


async def _semer_scripts(session) -> None:
    """Inscrit au registre `card_scripts` le programme des deux textes d'effet du deck A.

    Sans ces lignes au statut `scripte`, `refus_scripts_deck` refuserait l'Objet et le Supporter et
    le deck serait déclaré injouable (D9 : un effet non scripté n'est jamais approximé).
    `enregistrer_script` pose lui-même `validated_at` et `review_tests_ok`, ce qui satisfait la
    contrainte `ck_card_scripts_scripte_gate` côté Postgres.
    """
    for texte, dsl in ((TXT_OBJET, DSL_OBJET), (TXT_SUPPORTER, DSL_SUPPORTER)):
        await enregistrer_script(
            session, source_text=texte, statut=SCRIPT_STATUT_SCRIPTE, dsl_version=1, script=dsl,
            author="j-e2e-deux-navigateurs", tests=["partie-deux-navigateurs"],
        )


async def _utilisateur(session, email: str, password: str) -> User:
    """Un compte vérifié **avec `game_access`** (D11), créé ou remis à niveau."""
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            last_name="Joueur",
            birth_date=date(2000, 1, 1),
            terms_version=CURRENT_TERMS_VERSION,
            terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
            email_verified_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(user)
        await session.flush()
    user.game_access = True
    return user


async def _deck(session, user_id, nom: str, composition: list[tuple[Card, int]]) -> Deck:
    """Le deck nommé de cet utilisateur, recréé à l'identique s'il existe déjà.

    On réécrit les lignes plutôt que de les compléter : un seed rejoué ne doit pas doubler les
    quantités (ce qui ferait dériver la composition d'une exécution à l'autre).
    """
    deck = (
        await session.execute(select(Deck).where(Deck.user_id == user_id, Deck.name == nom))
    ).scalar_one_or_none()
    if deck is None:
        deck = Deck(user_id=user_id, name=nom)
        session.add(deck)
        await session.flush()
    else:
        for ligne in (
            await session.execute(select(DeckCard).where(DeckCard.deck_id == deck.id))
        ).scalars():
            await session.delete(ligne)
        await session.flush()
    for card, quantite in composition:
        session.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=quantite))
    await session.flush()
    return deck


async def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(1)
    email_a, email_b, password = sys.argv[1], sys.argv[2], sys.argv[3]

    async with async_session_factory() as session:
        await _semer_scripts(session)
        cartes = await _cartes_du_jeu(session)
        user_a = await _utilisateur(session, email_a, password)
        user_b = await _utilisateur(session, email_b, password)

        # 4 attaquants seulement : le mulligan (R-4.x) garantit une base en main d'ouverture, et
        # laisser 36 Dresseurs sur 60 rend quasi certaine la présence d'un Dresseur jouable.
        deck_a = await _deck(
            session, user_a.id, "Deck attaquant E2E",
            [
                (cartes["attaquant"], 4),
                (cartes["energie"], 20),
                (cartes["objet"], 18),
                (cartes["supporter"], 18),
            ],
        )
        # Un seul Pokémon : banc vide garanti (voir l'en-tête du module), le reste en Énergies
        # pour que B ait toujours une carte à piocher et ne gagne pas par épuisement (R-14.2).
        deck_b = await _deck(
            session, user_b.id, "Deck cible E2E",
            [(cartes["cible"], 1), (cartes["energie"], 59)],
        )
        await session.commit()

        print(json.dumps({
            "user_a": str(user_a.id), "user_b": str(user_b.id),
            "deck_a": str(deck_a.id), "deck_b": str(deck_b.id),
        }))


if __name__ == "__main__":
    asyncio.run(main())
