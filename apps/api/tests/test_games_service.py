"""Service de parties (`pbm_api.games.service`) — lot `j-partie-service`.

Couvre les trois critères d'acceptation et le risque nommé du lot :

* **reprise après redémarrage** — l'état se reconstruit depuis la base (instantané + journal) et
  rend la même empreinte (`test_reprise_*`, `test_compaction_*`) ;
* **idempotence / verrou** — un même numéro d'action ne s'applique jamais deux fois ; la contrainte
  d'unicité `(game_id, numero)` est le backstop (`test_idempotence_*`, `test_conflit_*`,
  `test_unicite_game_numero_backstop`) ;
* **refus d'une carte non scriptée** — une partie dont un deck porte une carte non jouable est
  refusée, cartes nommées (`test_creer_partie_refuse_*`).

Plus la boucle d'application, l'expiration et la purge. Les tests tournent contre la vraie base de
test (la CI fait foi) ; le moteur `pbm_game` est pur et testé à part dans le job `game`.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from pbm_api.games.errors import (
    ActionRefusee,
    CartesNonJouables,
    ConflitNumero,
    PartieIntrouvable,
    PartieNonActive,
)
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    expirer_parties,
    purger,
    reprendre_partie,
)
from pbm_api.models import Card, Deck, DeckCard, Game, GameEvent, GameSnapshot, Set, User

_IDENTITY = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _make_user(db) -> User:
    user = User(email=f"j-{uuid.uuid4().hex[:10]}@example.com", password_hash="x", **_IDENTITY)
    db.add(user)
    await db.flush()
    return user


async def _make_card(db, *, name: str, jouable: bool = True) -> Card:
    """Une carte Pokémon jouable (se compile en DefinitionCarte), ou volontairement non jouable.

    Non jouable = `prize_marker` absent : l'adaptateur `pbm_api.jeu.catalogue` la refuse (« marqueur
    de règle inconnu »), ce qui doit faire refuser la partie (D9).
    """
    set_row = Set(code=f"g-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
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


async def _deux_joueurs(db, *, taille_deck: int = 8):
    """Deux utilisateurs, chacun un deck jouable (une carte en `taille_deck` exemplaires)."""
    user_a = await _make_user(db)
    user_b = await _make_user(db)
    carte_a = await _make_card(db, name="Carpanaud")
    carte_b = await _make_card(db, name="Tiplouf")
    deck_a = await _make_deck(db, user_a, [(carte_a, taille_deck)])
    deck_b = await _make_deck(db, user_b, [(carte_b, taille_deck)])
    return user_a, deck_a, user_b, deck_b


# --- Création ----------------------------------------------------------------


async def test_creer_partie_charge_les_decks_en_pioche(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session, taille_deck=10)

    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    assert game.status == "en_cours"
    assert game.current_numero == 0
    assert game.current_empreinte  # empreinte de l'état initial posée
    # Un instantané au coup 0 est toujours créé (point de reprise de départ).
    snap0 = (
        await db_session.execute(
            select(GameSnapshot).where(
                GameSnapshot.game_id == game.id, GameSnapshot.numero_entrees == 0
            )
        )
    ).scalar_one()
    assert snap0.empreinte == game.current_empreinte

    etat, _ = await reprendre_partie(db_session, game)
    assert len(etat.joueurs[0].pioche) == 10
    assert len(etat.joueurs[1].pioche) == 10


async def test_creer_partie_refuse_une_carte_non_scriptee(db_session):
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    bonne = await _make_card(db_session, name="Salamèche")
    mauvaise = await _make_card(db_session, name="Carte Mystère", jouable=False)
    deck_a = await _make_deck(db_session, user_a, [(bonne, 4), (mauvaise, 2)])
    deck_b = await _make_deck(db_session, user_b, [(bonne, 6)])

    with pytest.raises(CartesNonJouables) as exc:
        await creer_partie(
            db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
        )

    noms = [nom for nom, _ in exc.value.cartes]
    assert "Carte Mystère" in noms
    # Aucune partie ne doit avoir été persistée (refus avant écriture).
    total = (await db_session.execute(select(func.count()).select_from(Game))).scalar_one()
    assert total == 0


# --- Boucle d'application ----------------------------------------------------


async def test_appliquer_action_journalise_et_avance(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    res = await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )

    assert res.rejoue is False
    assert res.numero == 0
    assert any(e["type"] == "cartes_piochees" for e in res.evenements)

    await db_session.refresh(game)
    assert game.current_numero == 1
    assert game.current_empreinte == res.empreinte

    event = (
        await db_session.execute(select(GameEvent).where(GameEvent.game_id == game.id))
    ).scalar_one()
    assert event.numero == 0
    assert event.action["type"] == "piocher"
    assert event.empreinte == res.empreinte


async def test_idempotence_meme_numero_meme_action_ne_rejoue_pas(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    premier = await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )
    second = await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )

    assert premier.rejoue is False
    assert second.rejoue is True
    assert second.empreinte == premier.empreinte
    # Une seule entrée de journal au numéro 0 : le coup n'a pas été appliqué deux fois.
    nb = (
        await db_session.execute(
            select(func.count()).select_from(GameEvent).where(GameEvent.game_id == game.id)
        )
    ).scalar_one()
    assert nb == 1
    await db_session.refresh(game)
    assert game.current_numero == 1


async def test_conflit_numero_meme_numero_autre_action(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )

    with pytest.raises(ConflitNumero):
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user_a.id,
            type="melanger_pioche",
            numero_attendu=0,
        )


async def test_conflit_numero_en_avance(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    with pytest.raises(ConflitNumero):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=5
        )


async def test_unicite_game_numero_backstop(db_session):
    """L'unicité `(game_id, numero)` empêche deux entrées au même numéro (course perdue)."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                GameEvent(
                    game_id=game.id,
                    numero=0,
                    auteur="x",
                    action={"type": "piocher", "auteur": "x", "params": {}},
                    evenements=[],
                    horodatage="t",
                    empreinte="e",
                )
            )
            await db_session.flush()


async def test_action_inconnue_refusee(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    with pytest.raises(ActionRefusee):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="sortilege", numero_attendu=0
        )
    await db_session.refresh(game)
    assert game.current_numero == 0


async def test_acces_croise_partie_dun_autre(db_session):
    """Un non-participant ne peut pas appliquer un coup : 404 (pas 403, pas de fuite)."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    intrus = await _make_user(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    with pytest.raises(PartieIntrouvable):
        await appliquer_action(
            db_session, game_id=game.id, user_id=intrus.id, type="piocher", numero_attendu=0
        )


# --- Reprise / compaction ----------------------------------------------------


async def test_reprise_apres_redemarrage_rend_etat_exact(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session, taille_deck=10)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    for n in range(3):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=n
        )

    # Simule un redémarrage complet : plus rien en mémoire, on relit la partie depuis la base.
    gid = game.id
    db_session.expire_all()
    game_relu = (
        await db_session.execute(select(Game).where(Game.id == gid))
    ).scalar_one()
    etat, _ = await reprendre_partie(db_session, game_relu)

    # 3 cartes piochées par A : pioche 10 → 7, main 0 → 3. Empreinte vérifiée par reprendre_partie.
    assert len(etat.joueurs[0].pioche) == 7
    assert len(etat.joueurs[0].main) == 3


async def test_compaction_instantane_et_reprise_identique(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session, taille_deck=12)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    # Un mélange (consomme l'aléatoire) puis des pioches : prouve la reconstruction du Rng aussi.
    await appliquer_action(
        db_session,
        game_id=game.id,
        user_id=user_a.id,
        type="melanger_pioche",
        numero_attendu=0,
        intervalle_instantane=3,
    )
    for n in range(1, 6):
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user_a.id,
            type="piocher",
            numero_attendu=n,
            intervalle_instantane=3,
        )

    # Des instantanés ont été figés aux multiples de 3 (3 et 6), en plus de celui du coup 0.
    numeros = (
        await db_session.execute(
            select(GameSnapshot.numero_entrees)
            .where(GameSnapshot.game_id == game.id)
            .order_by(GameSnapshot.numero_entrees)
        )
    ).scalars().all()
    assert numeros == [0, 3, 6]

    gid = game.id
    db_session.expire_all()
    game_relu = (await db_session.execute(select(Game).where(Game.id == gid))).scalar_one()
    etat, _ = await reprendre_partie(db_session, game_relu)  # empreinte vérifiée dedans
    assert len(etat.joueurs[0].main) == 5  # 5 pioches de 1 carte


# --- Fin de partie -----------------------------------------------------------


async def test_abandon_termine_la_partie_et_refuse_la_suite(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    res = await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="abandonner", numero_attendu=0
    )
    assert res.terminee is True
    assert res.vainqueur_user_id == user_b.id
    assert res.raison_fin == "abandon"

    await db_session.refresh(game)
    assert game.status == "terminee"

    # Une partie terminée n'accepte plus d'action au coup suivant.
    with pytest.raises(PartieNonActive):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_b.id, type="piocher", numero_attendu=1
        )


# --- Expiration / purge ------------------------------------------------------


async def test_expirer_parties_fige_les_inactives(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    vieille = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    user_c, deck_c, user_d, deck_d = await _deux_joueurs(db_session)
    recente = await creer_partie(
        db_session, joueur_a=(user_c.id, deck_c.id), joueur_b=(user_d.id, deck_d.id)
    )
    # On rend la première échue (échéance d'inactivité dépassée).
    await db_session.execute(
        update(Game)
        .where(Game.id == vieille.id)
        .values(expires_at=datetime(2000, 1, 1, tzinfo=UTC))
    )
    await db_session.flush()

    compte = await expirer_parties(db_session)

    assert compte >= 1
    await db_session.refresh(vieille)
    await db_session.refresh(recente)
    assert vieille.status == "expiree"
    assert recente.status == "en_cours"


async def test_purger_supprime_les_mortes_anciennes_et_les_instantanes_superflus(db_session):
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session, taille_deck=12)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    for n in range(6):
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user_a.id,
            type="piocher",
            numero_attendu=n,
            intervalle_instantane=3,
        )
    # Plusieurs instantanés existent (0, 3, 6) ; la purge n'en garde qu'un (le plus récent).
    await appliquer_action(
        db_session, game_id=game.id, user_id=user_a.id, type="abandonner", numero_attendu=6
    )
    # On vieillit la partie morte au-delà du seuil de purge.
    await db_session.execute(
        update(Game).where(Game.id == game.id).values(updated_at=datetime(2000, 1, 1, tzinfo=UTC))
    )
    await db_session.flush()

    metrique = await purger(db_session)

    assert metrique["instantanes_purges"] >= 1
    assert metrique["parties_purgees"] >= 1
    restant = (
        await db_session.execute(select(func.count()).select_from(Game).where(Game.id == game.id))
    ).scalar_one()
    assert restant == 0
