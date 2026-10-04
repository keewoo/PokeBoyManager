"""Chargeur de scripts, détection d'errata et refus au lancement (`pbm_api.jeu.scripts`).

Tests **sur base** (la CI fait foi) couvrant les trois critères d'acceptation du lot :

* n°1 — une carte dont le texte a changé ne se joue plus avec l'ancien script : elle passe « à
  revoir » et le deck le dit (`test_errata_*`) ;
* n°2 — le regroupement est prouvé à part, en pur (`test_card_scripts_empreinte`) ;
* n°3 — le lancement d'une partie avec une carte non scriptée est refusé **avant** la mise en place
  (`test_lancement_refuse_*`), jamais en plein milieu.

Plus les quatre états d'un script (absent, à revoir, non supporté, version illisible) qui bloquent
tous une carte à effet, et un deck de cartes sans effet qui reste jouable sans aucun script.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from pbm_api.games.entry import DeckInjouable, DeckIntrouvable, verifier_deck
from pbm_api.games.lancement import verifier_lancable
from pbm_api.jeu.scripts.chargeur import refus_scripts_deck
from pbm_api.jeu.scripts.depot import enregistrer_script, script_par_empreinte
from pbm_api.jeu.scripts.empreinte import empreinte_texte
from pbm_api.jeu.scripts.errata import detecter_errata
from pbm_api.models import (
    SCRIPT_STATUT_A_REVOIR,
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    Set,
    User,
)

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}

#: Un programme DSL minimal mais **valide** (se recharge par l'interprète) : « piochez 1 carte ».
_PROG_VALIDE = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}
#: Un programme à version **future** : stockable, mais refusé au rechargement (jamais « au mieux »).
_PROG_VERSION_FUTURE = {"version": 99, "effets": [{"op": "piocher", "nombre": 1}]}


async def _make_user(db) -> User:
    user = User(email=f"sc-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_card(db, *, effet_attaque: str | None = None) -> Card:
    """Un Pokémon jouable (se compile) ; avec un texte d'effet d'attaque si ``effet_attaque``."""
    set_row = Set(code=f"sc-{uuid.uuid4().hex[:8]}", name="Set scripts", series="Série test")
    db.add(set_row)
    await db.flush()
    attacks = [{"name": "Éclair", "cost": ["water"], "damage": "10", "effect": effet_attaque or ""}]
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name="Pokémon test",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
        attacks=attacks,
    )
    db.add(card)
    await db.flush()
    return card


async def _make_deck(db, user: User, card: Card, *, qty: int = 1, possede: bool = True) -> Deck:
    deck = Deck(user_id=user.id, name=f"Deck {uuid.uuid4().hex[:6]}")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    if possede:
        for _ in range(qty):
            db.add(CollectionItem(user_id=user.id, card_id=card.id))
    await db.flush()
    return deck


@pytest.mark.asyncio
async def test_deck_sans_effet_jouable_sans_script(db_session):
    """Un Pokémon à dégâts secs n'exige aucun script : le deck est jouable tel quel."""
    user = await _make_user(db_session)
    card = await _make_card(db_session, effet_attaque=None)
    deck = await _make_deck(db_session, user, card, qty=2)
    assert await refus_scripts_deck(db_session, deck.id) == []
    await verifier_deck(db_session, user.id, deck.id)  # ne lève pas


@pytest.mark.asyncio
async def test_carte_a_effet_sans_script_refusee(db_session):
    """Une carte à effet sans script au registre bloque le deck, carte nommée (D9)."""
    user = await _make_user(db_session)
    card = await _make_card(db_session, effet_attaque="Lancez une pièce. Si face, paralysez.")
    deck = await _make_deck(db_session, user, card, qty=1)
    refus = await refus_scripts_deck(db_session, deck.id)
    assert len(refus) == 1
    libelle, raison = refus[0]
    assert "Éclair" in libelle and "aucun script" in raison
    with pytest.raises(DeckInjouable):
        await verifier_deck(db_session, user.id, deck.id)


@pytest.mark.asyncio
async def test_carte_a_effet_avec_script_scripte_jouable(db_session):
    """Un script « scripté » et lisible pour le texte rend la carte jouable."""
    user = await _make_user(db_session)
    texte = "Lancez une pièce. Si face, paralysez."
    card = await _make_card(db_session, effet_attaque=texte)
    deck = await _make_deck(db_session, user, card, qty=1)
    await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=1,
        script=_PROG_VALIDE,
        author="test",
        tests=["t1"],
    )
    assert await refus_scripts_deck(db_session, deck.id) == []
    await verifier_deck(db_session, user.id, deck.id)  # ne lève pas


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statut,script",
    [
        (SCRIPT_STATUT_A_REVOIR, _PROG_VALIDE),
        (SCRIPT_STATUT_NON_SUPPORTE, None),
    ],
)
async def test_script_a_revoir_ou_non_supporte_refuse(db_session, statut, script):
    """Un script « à revoir » ou « non supporté » bloque la carte — jamais joué « au mieux »."""
    user = await _make_user(db_session)
    texte = "Un effet hors langage v1."
    card = await _make_card(db_session, effet_attaque=texte)
    deck = await _make_deck(db_session, user, card, qty=1)
    await enregistrer_script(
        db_session, source_text=texte, statut=statut, dsl_version=1, script=script, notes="raison"
    )
    refus = await refus_scripts_deck(db_session, deck.id)
    assert len(refus) == 1


@pytest.mark.asyncio
async def test_script_version_illisible_refuse(db_session):
    """Un script « scripté » dont la version dépasse l'interprète est refusé au rechargement."""
    user = await _make_user(db_session)
    texte = "Piochez autant de cartes."
    card = await _make_card(db_session, effet_attaque=texte)
    deck = await _make_deck(db_session, user, card, qty=1)
    await enregistrer_script(
        db_session,
        source_text=texte,
        statut=SCRIPT_STATUT_SCRIPTE,
        dsl_version=99,
        script=_PROG_VERSION_FUTURE,
    )
    refus = await refus_scripts_deck(db_session, deck.id)
    assert len(refus) == 1
    assert "invalide au rechargement" in refus[0][1]


@pytest.mark.asyncio
async def test_errata_texte_change_refuse_le_deck_et_bascule_le_script(db_session):
    """Critère n°1 : texte modifié → carte refusée (nouvelle empreinte) ET script « à revoir »."""
    user = await _make_user(db_session)
    ancien = "Piochez 2 cartes."
    card = await _make_card(db_session, effet_attaque=ancien)
    deck = await _make_deck(db_session, user, card, qty=1)
    await enregistrer_script(
        db_session, source_text=ancien, statut=SCRIPT_STATUT_SCRIPTE, dsl_version=1,
        script=_PROG_VALIDE, author="test",
    )
    # Jouable avec l'ancien texte.
    assert await refus_scripts_deck(db_session, deck.id) == []

    # Errata en base : le texte de l'attaque change.
    nouveau = "Piochez 3 cartes."
    card.attacks = [{"name": "Éclair", "cost": ["water"], "damage": "10", "effect": nouveau}]
    db_session.add(card)
    await db_session.commit()

    # La carte ne se joue plus : son nouveau texte n'a aucun script (versant carte du critère n°1).
    refus = await refus_scripts_deck(db_session, deck.id)
    assert len(refus) == 1

    # La détection fait repasser l'ancien script « à revoir » (versant script du critère n°1).
    orphelins = await detecter_errata(db_session)
    assert len(orphelins) == 1
    ligne = await script_par_empreinte(db_session, empreinte_texte(ancien))
    assert ligne.statut == SCRIPT_STATUT_A_REVOIR
    assert ligne.validated_at is None


@pytest.mark.asyncio
async def test_errata_a_blanc_ne_modifie_rien(db_session):
    """L'errata « à blanc » signale sans écrire : le statut « scripté » reste intact."""
    user = await _make_user(db_session)
    texte = "Un texte qui va disparaître."
    card = await _make_card(db_session, effet_attaque=texte)
    await _make_deck(db_session, user, card, qty=1)
    await enregistrer_script(
        db_session, source_text=texte, statut=SCRIPT_STATUT_SCRIPTE, dsl_version=1,
        script=_PROG_VALIDE,
    )
    card.attacks = [{"name": "Éclair", "effect": "Autre chose."}]
    db_session.add(card)
    await db_session.commit()
    orphelins = await detecter_errata(db_session, appliquer=False)
    assert len(orphelins) == 1
    ligne = await script_par_empreinte(db_session, empreinte_texte(texte))
    assert ligne.statut == SCRIPT_STATUT_SCRIPTE  # rien n'a été écrit


@pytest.mark.asyncio
async def test_lancement_refuse_carte_non_scriptee_avant_mise_en_place(db_session):
    """Critère n°3 : `verifier_lancable` refuse une carte non scriptée avant création de partie."""
    user = await _make_user(db_session)
    card = await _make_card(db_session, effet_attaque="Un effet non scripté.")
    deck = await _make_deck(db_session, user, card, qty=1)  # possédée : seul le script manque
    avant = (await db_session.execute(select(func.count()).select_from(Game))).scalar_one()
    with pytest.raises(DeckInjouable):
        await verifier_lancable(db_session, user.id, deck.id)
    apres = (await db_session.execute(select(func.count()).select_from(Game))).scalar_one()
    assert apres == avant  # aucune partie créée : le refus est bien avant la mise en place


@pytest.mark.asyncio
async def test_verifier_deck_autrui_404_avant_tout(db_session):
    """Accès croisé : le deck d'un autre reste introuvable (404), le gate scripts ne fuit rien."""
    a = await _make_user(db_session)
    b = await _make_user(db_session)
    card = await _make_card(db_session, effet_attaque="Un effet.")
    deck_a = await _make_deck(db_session, a, card, qty=1)
    with pytest.raises(DeckIntrouvable):
        await verifier_deck(db_session, b.id, deck_a.id)
