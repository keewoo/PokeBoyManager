"""Couverture sur base et branchement dans la légalité du deck (lot `j-effets-couverture-outil`).

Tests sur base (la CI fait foi). Deux preuves clés du lot, qu'aucun test pur ne peut donner :

* ``charger_couverture`` ne mesure que l'**univers réel** (collections des joueurs du jeu + leurs
  decks) — un compte sans `game_access` n'y entre pas, et le chiffre **par collection** existe bien
  (critère n°2) ; les cartes qui bloquent sont classées par decks puis joueurs (mission n°2) ; la
  file de demandes figure dans le rapport (critère n°3) ;
* la légalité d'un deck (`decks.service.deck_detail`) porte désormais un constat
  `unsupported_effect` catégorie `script` pour une carte à l'effet non scripté (critère n°1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from pbm_api.decks import service
from pbm_api.decks.legality import CATEGORY_SCRIPT, CODE_UNSUPPORTED_EFFECT
from pbm_api.jeu.scripts import couverture, demandes
from pbm_api.jeu.scripts.depot import enregistrer_script
from pbm_api.models import (
    SCRIPT_STATUT_SCRIPTE,
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Set,
    User,
)

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}

#: Programme DSL minimal valide (se recharge), réutilisé du lot précédent.
_PROG_VALIDE = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}


async def _user(db, *, game: bool, pseudo: str) -> User:
    user = User(
        email=f"cov-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        pseudo=pseudo,
        game_access=game,
        **_IDENTITY,
    )
    db.add(user)
    await db.flush()
    return user


async def _card(db, set_row: Set, *, name: str, effet: str | None) -> Card:
    attacks = [{"name": "Éclair", "effect": effet}] if effet else None
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name=name,
        supertype="Pokémon",
        stage="Base",
        attacks=attacks,
    )
    db.add(card)
    await db.flush()
    return card


async def _own(db, user: User, card: Card, n: int = 1) -> None:
    for _ in range(n):
        db.add(CollectionItem(user_id=user.id, card_id=card.id))
    await db.flush()


@pytest.mark.asyncio
async def test_charger_couverture_mesure_les_collections_reelles(db_session):
    a = await _user(db_session, game=True, pseudo="aymeric")
    b = await _user(db_session, game=True, pseudo="zoe")
    c = await _user(db_session, game=False, pseudo="passant")  # pas game_access : exclu

    set_row = Set(code=f"cov-{uuid.uuid4().hex[:8]}", name="Extension test", series="Série")
    db_session.add(set_row)
    await db_session.flush()

    vanilla = await _card(db_session, set_row, name="Sans effet", effet=None)
    texte_ok = "Piochez 1 carte."
    scripted = await _card(db_session, set_row, name="Scriptée", effet=texte_ok)
    absent = await _card(db_session, set_row, name="Bloquée", effet="Un effet non scripté.")
    carte_de_c = await _card(db_session, set_row, name="Carte du passant", effet="Autre effet.")

    await enregistrer_script(
        db_session, source_text=texte_ok, statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=1, script=_PROG_VALIDE, author="test",
    )

    # Possession : A a les trois cartes du jeu ; B n'a que la bloquée ; C a une carte à lui seul.
    await _own(db_session, a, vanilla)
    await _own(db_session, a, scripted)
    await _own(db_session, a, absent)
    await _own(db_session, b, absent)
    await _own(db_session, c, carte_de_c)  # ne doit pas entrer dans l'univers

    # A met la carte bloquée dans un deck (→ decks bloqués).
    deck = Deck(user_id=a.id, name="Deck A")
    db_session.add(deck)
    await db_session.flush()
    db_session.add(DeckCard(deck_id=deck.id, card_id=absent.id, quantity=1))
    await db_session.flush()

    # A demande la carte bloquée.
    await demandes.creer_ou_maj_demande(db_session, user_id=a.id, card_id=absent.id, note="svp")

    rapport = await couverture.charger_couverture(db_session)

    # Seuls les deux joueurs du jeu comptent ; le passant est exclu.
    assert rapport.joueurs == 2
    ids_univers = {m.card_id for m in rapport.cartes_manquantes}
    assert str(carte_de_c.id) not in ids_univers

    # Par collection (critère n°2) : A a 2 cartes à effet, 1 jouable ; B a 1 à effet, 0 jouable.
    par_col = {c.pseudo: c for c in rapport.par_collection}
    assert par_col["aymeric"].possedees_distinctes == 3
    assert par_col["aymeric"].avec_effet == 2
    assert par_col["aymeric"].jouables == 1
    assert par_col["zoe"].avec_effet == 1
    assert par_col["zoe"].jouables == 0
    assert par_col["zoe"].pct == 0.0

    # Cartes qui bloquent (mission n°2) : la carte bloquée, 1 deck, 2 joueurs concernés.
    bloquee = next(m for m in rapport.cartes_manquantes if m.card_id == str(absent.id))
    assert bloquee.decks_bloques == 1
    assert bloquee.joueurs_concernes == 2
    # La scriptée et la sans-effet ne bloquent personne.
    assert str(scripted.id) not in ids_univers
    assert str(vanilla.id) not in ids_univers

    # La file de demandes figure dans le rapport (critère n°3).
    assert len(rapport.file_demandes) == 1
    assert rapport.file_demandes[0].card_id == str(absent.id)
    assert rapport.file_demandes[0].demandeurs == 1
    assert rapport.file_demandes[0].jouable_maintenant is False

    # Le rendu texte mentionne le chiffre par collection (la « page d'administration »).
    texte = couverture.rendu_texte(rapport)
    assert "aymeric" in texte and "zoe" in texte


@pytest.mark.asyncio
async def test_couverture_univers_vide_le_dit(db_session):
    # Aucun joueur du jeu ne possède de carte : le rapport le DIT, pas un 0 trompeur.
    await _user(db_session, game=True, pseudo="seul")
    rapport = await couverture.charger_couverture(db_session)
    assert rapport.univers_vide is True
    assert "AUCUNE carte" in couverture.rendu_texte(rapport)


@pytest.mark.asyncio
async def test_deck_legality_porte_le_constat_script(db_session):
    # Critère n°1 : un effet non scripté devient un constat `unsupported_effect` catégorie `script`.
    a = await _user(db_session, game=True, pseudo="dresseur")
    set_row = Set(code=f"lg-{uuid.uuid4().hex[:8]}", name="Set", series="Série")
    db_session.add(set_row)
    await db_session.flush()
    absent = await _card(db_session, set_row, name="Carte bloquée", effet="Un effet non scripté.")
    await _own(db_session, a, absent)

    deck = Deck(user_id=a.id, name="Deck")
    db_session.add(deck)
    await db_session.flush()
    db_session.add(DeckCard(deck_id=deck.id, card_id=absent.id, quantity=1))
    await db_session.commit()

    _, _, legality = await service.deck_detail(db_session, a, deck.id)
    script_issues = [i for i in legality.issues if i.code == CODE_UNSUPPORTED_EFFECT]
    assert len(script_issues) == 1
    assert script_issues[0].category == CATEGORY_SCRIPT
    assert script_issues[0].card_id == absent.id


@pytest.mark.asyncio
async def test_deck_legality_sans_effet_na_pas_de_constat_script(db_session):
    a = await _user(db_session, game=True, pseudo="dresseur2")
    set_row = Set(code=f"lg-{uuid.uuid4().hex[:8]}", name="Set", series="Série")
    db_session.add(set_row)
    await db_session.flush()
    vanilla = await _card(db_session, set_row, name="Sans effet", effet=None)
    await _own(db_session, a, vanilla)
    deck = Deck(user_id=a.id, name="Deck")
    db_session.add(deck)
    await db_session.flush()
    db_session.add(DeckCard(deck_id=deck.id, card_id=vanilla.id, quantity=1))
    await db_session.commit()

    _, _, legality = await service.deck_detail(db_session, a, deck.id)
    assert not any(i.code == CODE_UNSUPPORTED_EFFECT for i in legality.issues)
