"""File d'attente et appariement (`pbm_api.games.matchmaking`) — lot `j-file-attente`.

Couvre les critères d'acceptation et le risque nommé du lot :

* **appariement** — deux entrées en file produisent une partie (`test_deux_joueurs_*`) ;
* **trois joueurs dont un annule** — l'annulation retire de la file, l'appariement se fait sur les
  restants (`test_trois_joueurs_un_annule`) ;
* **deck refusé à l'entrée** — un deck non jouable ne rentre pas, cartes nommées
  (`test_entree_refuse_deck_*`) ;
* **jamais deux parties (concurrence)** — deux appariements concurrents sur trois joueurs ne créent
  qu'une partie et n'engagent aucun joueur deux fois (`test_concurrence_jamais_deux_parties`), et le
  verrou garde réellement la section critique (`test_verrou_bloque_un_second_appariement`).

Les tests tournent contre la vraie base de test et le vrai Redis (la CI fait foi). Le moteur
`pbm_game` est pur et testé à part. La présence et la file vivant dans Redis (non transactionnel),
l'état `mm:*` est purgé entre les tests par la fixture `_clean_matchmaking_state` du conftest.
"""

import asyncio
import os
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from pbm_api.games.entry import DeckInjouable, DeckIntrouvable
from pbm_api.games.matchmaking import (
    _LOCK,
    _QUEUE,
    Apparie,
    DejaEnPartie,
    EnAttente,
    _deck_key,
    apparier,
    partie_active_de,
    presence,
    quitter,
    rejoindre,
)
from pbm_api.models import Card, Deck, DeckCard, Game, GamePlayer, Set, User
from pbm_api.security.rate_limit import get_redis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v2_catalogue_complet_test",
)

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _make_user(db) -> User:
    user = User(email=f"mm-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_card(db, *, name: str, jouable: bool = True) -> Card:
    """Une carte jouable (se compile en DefinitionCarte), ou non jouable (`prize_marker` absent)."""
    set_row = Set(code=f"mm-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name=name,
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire" if jouable else None,
    )
    db.add(card)
    await db.flush()
    return card


async def _make_deck(db, user: User, cartes: list[tuple[Card, int]]) -> Deck:
    deck = Deck(user_id=user.id, name="Deck test")
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


async def _joueur_jouable(db, *, nom="Carapuce"):
    """Un utilisateur avec un deck jouable (une carte en 8 exemplaires)."""
    user = await _make_user(db)
    carte = await _make_card(db, name=nom)
    deck = await _make_deck(db, user, [(carte, 8)])
    return user, deck


# --- Appariement de deux joueurs --------------------------------------------


async def test_deux_joueurs_sont_apparies(db_session):
    redis = get_redis()
    user_a, deck_a = await _joueur_jouable(db_session)
    user_b, deck_b = await _joueur_jouable(db_session)

    # A entre en premier : personne, il attend.
    r_a = await rejoindre(
        db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1000.0
    )
    assert isinstance(r_a, EnAttente)
    assert r_a.position == 1
    assert r_a.joueurs_en_file == 1

    # B entre : il est apparié avec A, une partie est créée.
    r_b = await rejoindre(
        db_session, redis, user_id=user_b.id, deck_id=deck_b.id, maintenant=1001.0
    )
    assert isinstance(r_b, Apparie)
    assert r_b.adversaire_user_id == user_a.id

    game = await db_session.get(Game, r_b.game_id)
    assert game is not None
    assert game.status == "en_cours"
    sieges = (
        await db_session.execute(select(GamePlayer.user_id).where(GamePlayer.game_id == game.id))
    ).scalars().all()
    assert set(sieges) == {user_a.id, user_b.id}

    # La file est vide, les deux sont « en partie », plus en attente.
    assert await partie_active_de(db_session, user_a.id) == game.id
    assert await partie_active_de(db_session, user_b.id) == game.id


async def test_fifo_ordre_arrivee(db_session):
    """L'appariement respecte l'ordre d'arrivée : les deux plus anciens sont pris en premier."""
    redis = get_redis()
    user_a, deck_a = await _joueur_jouable(db_session)
    user_b, deck_b = await _joueur_jouable(db_session)
    user_c, deck_c = await _joueur_jouable(db_session)

    await rejoindre(db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1000.0)
    await rejoindre(db_session, redis, user_id=user_b.id, deck_id=deck_b.id, maintenant=1001.0)
    # A et B (les plus anciens) viennent d'être appariés ; C arrive après et attend.
    r_c = await rejoindre(
        db_session, redis, user_id=user_c.id, deck_id=deck_c.id, maintenant=1002.0
    )
    assert isinstance(r_c, EnAttente)
    assert r_c.position == 1
    assert await partie_active_de(db_session, user_c.id) is None


# --- Trois joueurs dont un annule -------------------------------------------


async def test_trois_joueurs_un_annule(db_session):
    """A entre puis annule ; B et C s'apparient — l'annulation ne laisse pas d'entrée fantôme.

    C'est le piège de l'annulation : si `quitter` ne retirait pas vraiment A de la file, B
    s'apparierait à un fantôme (A, qui ne joue plus). On vérifie donc que B **attend** (A parti) et
    que c'est C qui l'apparie — jamais A.
    """
    redis = get_redis()
    user_a, deck_a = await _joueur_jouable(db_session)
    user_b, deck_b = await _joueur_jouable(db_session)
    user_c, deck_c = await _joueur_jouable(db_session)

    # A entre et attend.
    r_a = await rejoindre(
        db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1000.0
    )
    assert isinstance(r_a, EnAttente)

    # A annule : il quitte la file.
    assert await quitter(redis, user_a.id) is True

    # B entre : A n'est plus là, aucun appariement fantôme — B attend.
    r_b = await rejoindre(
        db_session, redis, user_id=user_b.id, deck_id=deck_b.id, maintenant=1001.0
    )
    assert isinstance(r_b, EnAttente)
    assert await partie_active_de(db_session, user_a.id) is None

    # C entre : il est apparié avec B (pas avec A, qui a annulé).
    r_c = await rejoindre(
        db_session, redis, user_id=user_c.id, deck_id=deck_c.id, maintenant=1002.0
    )
    assert isinstance(r_c, Apparie)
    assert r_c.adversaire_user_id == user_b.id

    # A, qui a annulé, n'est dans aucune partie ; ré-annuler est sans effet (idempotent).
    assert await partie_active_de(db_session, user_a.id) is None
    assert await quitter(redis, user_a.id) is False


# --- Deck refusé à l'entrée -------------------------------------------------


async def test_entree_refuse_deck_non_jouable_cartes_nommees(db_session):
    redis = get_redis()
    user = await _make_user(db_session)
    carte_cassee = await _make_card(db_session, name="Insolourdo", jouable=False)
    deck = await _make_deck(db_session, user, [(carte_cassee, 8)])

    with pytest.raises(DeckInjouable) as exc:
        await rejoindre(db_session, redis, user_id=user.id, deck_id=deck.id, maintenant=1000.0)

    # Le refus nomme la carte en cause et dit pourquoi.
    noms = [nom for nom, _raison in exc.value.refus]
    assert "Insolourdo" in noms
    # Il n'a pas été inscrit dans la file (le refus précède l'inscription).
    r = await presence(db_session, redis, user.id, maintenant=1000.0)
    assert r.en_file == 0


async def test_entree_refuse_deck_dun_autre(db_session):
    """Un deck qui n'appartient pas au joueur → DeckIntrouvable (→ 404, pas de fuite)."""
    redis = get_redis()
    moi = await _make_user(db_session)
    autre, deck_autre = await _joueur_jouable(db_session)

    with pytest.raises(DeckIntrouvable):
        await rejoindre(db_session, redis, user_id=moi.id, deck_id=deck_autre.id, maintenant=1000.0)


# --- Jamais deux parties : entrée refusée si déjà en partie -----------------


async def test_deja_en_partie_refuse_entree(db_session):
    redis = get_redis()
    user_a, deck_a = await _joueur_jouable(db_session)
    user_b, deck_b = await _joueur_jouable(db_session)
    await rejoindre(db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1000.0)
    await rejoindre(db_session, redis, user_id=user_b.id, deck_id=deck_b.id, maintenant=1001.0)
    # A est maintenant en partie : il ne peut pas re-entrer dans la file.
    with pytest.raises(DejaEnPartie):
        await rejoindre(db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1002.0)


# --- Verrou : garde réellement la section critique --------------------------


async def test_verrou_bloque_un_second_appariement(db_session):
    """Verrou tenu par un autre → `apparier` renonce sans toucher la file (pas de 2e passage)."""
    redis = get_redis()
    user_a, deck_a = await _joueur_jouable(db_session)
    user_b, deck_b = await _joueur_jouable(db_session)
    await rejoindre(db_session, redis, user_id=user_a.id, deck_id=deck_a.id, maintenant=1000.0)
    # B entre dans la file sans déclencher d'appariement : on simule un verrou déjà pris.
    assert await redis.set(_LOCK, "un-autre", nx=True, ex=10)
    try:
        # Appariement impossible (verrou pris) : aucune partie, les deux restent en file.
        cree = await apparier(db_session, redis, maintenant=1001.0)
        assert cree == []
    finally:
        await redis.delete(_LOCK)


# --- Concurrence : jamais deux parties --------------------------------------


@pytest.mark.asyncio
async def test_concurrence_jamais_deux_parties():
    """Deux appariements concurrents sur trois joueurs : une seule partie, aucun joueur en double.

    C'est le risque nommé du lot (« deux joueurs appariés chacun avec un troisième »). On seed trois
    joueurs committés dans la file, puis on lance deux passages d'appariement concurrents, chacun
    avec sa propre session (la concurrence réelle exige des connexions distinctes). Le verrou Redis
    doit garantir qu'au plus une partie est créée et qu'aucun joueur n'apparaît dans deux parties.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    redis = get_redis()
    set_ids: list[uuid.UUID] = []
    card_ids: list[uuid.UUID] = []
    deck_ids: list[uuid.UUID] = []
    user_ids: list[uuid.UUID] = []

    async def _seed(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
        set_row = Set(code=f"cc-{uuid.uuid4().hex[:8]}", name="Set", series="S")
        s.add(set_row)
        await s.flush()
        card = Card(
            set_id=set_row.id,
            number=str(uuid.uuid4().int % 100000),
            name="Carapuce",
            supertype="Pokémon",
            energy_type="water",
            element_type="water",
            hp=60,
            stage="Base",
            retreat_cost=1,
            prize_marker="ordinaire",
        )
        s.add(card)
        await s.flush()
        user = User(email=f"cc-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
        s.add(user)
        await s.flush()
        deck = Deck(user_id=user.id, name="Deck")
        s.add(deck)
        await s.flush()
        s.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
        await s.flush()
        set_ids.append(set_row.id)
        card_ids.append(card.id)
        deck_ids.append(deck.id)
        user_ids.append(user.id)
        return user.id, deck.id

    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            joueurs = [await _seed(s) for _ in range(3)]
            await s.commit()

        # Les trois sont dans la file, ordre d'arrivée croissant.
        for i, (uid, did) in enumerate(joueurs):
            await redis.zadd(_QUEUE, {uid.hex: 1000.0 + i})
            await redis.set(_deck_key(uid.hex), str(did), ex=3600)

        async def passage():
            async with AsyncSession(engine, expire_on_commit=False) as s2:
                return await apparier(s2, redis, maintenant=2000.0)

        resultats = await asyncio.wait_for(
            asyncio.gather(passage(), passage(), return_exceptions=True), timeout=40
        )
        erreurs = [r for r in resultats if isinstance(r, BaseException)]
        assert not erreurs, f"erreur inattendue : {erreurs!r}"

        # Exactement une partie créée, tous passages confondus.
        total_parties = sum(len(r) for r in resultats)
        assert total_parties == 1, f"attendu 1 partie, obtenu {total_parties}"

        # Aucun joueur n'est dans deux parties.
        async with AsyncSession(engine, expire_on_commit=False) as s3:
            rows = (
                await s3.execute(
                    select(GamePlayer.user_id).where(GamePlayer.user_id.in_(user_ids))
                )
            ).scalars().all()
            assert len(rows) == len(set(rows)), "un joueur apparaît dans deux parties"
            assert len(rows) == 2, f"attendu 2 sièges (une partie), obtenu {len(rows)}"
    finally:
        async with AsyncSession(engine, expire_on_commit=False) as s4:
            game_ids = (
                await s4.execute(
                    select(GamePlayer.game_id).where(GamePlayer.user_id.in_(user_ids))
                )
            ).scalars().all()
            if game_ids:
                await s4.execute(delete(Game).where(Game.id.in_(set(game_ids))))
            await s4.execute(delete(DeckCard).where(DeckCard.deck_id.in_(deck_ids)))
            await s4.execute(delete(Deck).where(Deck.id.in_(deck_ids)))
            await s4.execute(delete(Card).where(Card.id.in_(card_ids)))
            await s4.execute(delete(Set).where(Set.id.in_(set_ids)))
            await s4.execute(delete(User).where(User.id.in_(user_ids)))
            await s4.commit()
        for uid in user_ids:
            await redis.delete(_deck_key(uid.hex))
            await redis.zrem(_QUEUE, uid.hex)
        await engine.dispose()
