"""Service de lancement de partie (`pbm_api.games.lancement`) — lot `j-lancement-partie`.

Vérifie le lot **sans HTTP** (le routeur a ses propres tests) : la machine à états
persistée (préparation → tirage → lancé), le **tirage vérifiable** (engagement publié avant, graine
révélée à la fin, pile ou face recalculable depuis la graine), le **choix du gagnant** avec
délai et choix par défaut, le refus d'un deck **devenu injouable** (carte vendue), et l'isolation.

Chaque test échoue sans le code du lot (les modules `pbm_api.games.lancement` et
`pbm_api.models.game_launch` n'existeraient pas). Les factories créent comptes, decks, exemplaires
possédés et invitations directement en base (la fixture `db_session` annule tout en fin de test).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pbm_game.rng import (
    FLUX_QUI_COMMENCE,
    rejouer_tirage,
    tirage_depuis_json,
    verifier_engagement,
    verifier_journal,
)

from pbm_api.games import lancement as service
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.entry import DeckInjouable
from pbm_api.games.lancement import (
    InvitationPasAcceptee,
    LancementIntrouvable,
    PasLeGagnantDuTirage,
)
from pbm_api.models import (
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    GameInvitation,
    GamePlayer,
    Set,
    User,
)
from pbm_api.models.game_launch import (
    LANCEMENT_STATUT_ABANDONNE,
    LANCEMENT_STATUT_LANCE,
    LANCEMENT_STATUT_PREPARATION,
    LANCEMENT_STATUT_TIRAGE,
)
from pbm_api.models.games import GAME_STATUS_TERMINEE
from pbm_api.models.invitations import (
    INVITATION_MODE_PSEUDO,
    INVITATION_STATUT_ACCEPTEE,
    INVITATION_STATUT_ENVOYEE,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _make_user(db, *, pseudo=None) -> User:
    user = User(
        email=f"u-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        last_name="Dresseur",
        birth_date=date(2000, 1, 1),
        terms_version="1",
        terms_accepted_at=datetime(2000, 1, 1),
        game_access=True,
        pseudo=pseudo,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_deck_possede(
    db, user_id: uuid.UUID, *, quantity: int = 20, name="Carapuce"
) -> Deck:
    """Un deck jouable (carte scriptée) ET **possédé** : quantity exemplaires en collection."""
    set_row = Set(code=f"lp-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name=name,
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    db.add(card)
    await db.flush()
    deck = Deck(user_id=user_id, name=f"Deck {name}")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=quantity))
    for _ in range(quantity):
        db.add(CollectionItem(user_id=user_id, card_id=card.id))
    await db.flush()
    return deck


async def _invitation_acceptee(
    db, a: User, b: User, deck_a, deck_b, *, statut=INVITATION_STATUT_ACCEPTEE
):
    inv = GameInvitation(
        mode=INVITATION_MODE_PSEUDO,
        statut=statut,
        inviter_user_id=a.id,
        invitee_user_id=b.id,
        inviter_deck_id=deck_a.id,
        invitee_deck_id=deck_b.id,
        expires_at=T0 + timedelta(days=7),
        resolved_at=T0,
    )
    db.add(inv)
    await db.flush()
    return inv


async def _preparer_les_deux(db, inv, a, b, *, maintenant=T0):
    """Les deux camps se déclarent prêts → le tirage part. Renvoie le lancement."""
    await service.se_preparer(db, invitation_id=inv.id, user_id=a.id, maintenant=maintenant)
    launch, _ = await service.se_preparer(
        db, invitation_id=inv.id, user_id=b.id, maintenant=maintenant
    )
    return launch


# -------------------------------------------------------------------- machine à états / reprise


async def test_preparation_puis_tirage_etape_par_etape(db_session):
    """Un rechargement reprend à la bonne étape : préparation → (un prêt) → tirage (deux prêts)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    da = await _make_deck_possede(db_session, a.id)
    db_ = await _make_deck_possede(db_session, b.id)
    inv = await _invitation_acceptee(db_session, a, b, da, db_)

    launch, _ = await service.obtenir_ou_creer(db_session, invitation_id=inv.id, user_id=a.id)
    assert launch.statut == LANCEMENT_STATUT_PREPARATION
    assert launch.inviter_deck_id == da.id  # pré-garni du deck annoncé

    # A se prépare : toujours en préparation (B pas encore prêt) — reprise fidèle après un F5.
    await service.se_preparer(db_session, invitation_id=inv.id, user_id=a.id, maintenant=T0)
    relu, _ = await service.obtenir_ou_creer(
        db_session, invitation_id=inv.id, user_id=b.id, maintenant=T0
    )
    assert relu.statut == LANCEMENT_STATUT_PREPARATION
    assert relu.inviter_pret is True and relu.invitee_pret is False

    # B se prépare : les deux prêts → tirage, engagement publié, pile ou face présent.
    launch, _ = await service.se_preparer(
        db_session, invitation_id=inv.id, user_id=b.id, maintenant=T0
    )
    assert launch.statut == LANCEMENT_STATUT_TIRAGE
    assert launch.engagement is not None
    assert launch.tirage is not None and launch.tirage["flux"] == FLUX_QUI_COMMENCE
    assert launch.tirage_gagnant_user_id in {a.id, b.id}
    assert launch.choix_expire_at == T0 + service.DELAI_CHOIX


async def test_graine_jamais_revelee_avant_la_fin(db_session):
    """L'engagement est public dès le tirage ; la graine reste secrète tant que la partie tourne."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    vue = await service.composer_vue(db_session, launch=launch, invitation=inv)
    assert vue.engagement is not None
    assert vue.graine is None  # secret maintenu : révéler tôt rendrait la pioche prévisible


# ------------------------------------------------ tirage vérifiable (R-4.7)


async def test_tirage_verifiable_apres_la_partie(db_session):
    """R-4.7 — le pile ou face se **recalcule** depuis la graine révélée : vérifiable des deux.

    Engagement publié avant le tirage, graine révélée seulement à la fin, puis le pile ou face se
    rejoue à l'identique (commit-reveal). C'est le critère « le tirage est vérifiable
    après coup par les deux joueurs ».
    """
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    gagnant = launch.tirage_gagnant_user_id
    launch, _ = await service.choisir(
        db_session, invitation_id=inv.id, user_id=gagnant, commencer=True, maintenant=T0
    )
    assert launch.statut == LANCEMENT_STATUT_LANCE and launch.game_id is not None

    # Fin de partie : la graine est révélée.
    game = await db_session.get(Game, launch.game_id)
    game.status = GAME_STATUS_TERMINEE
    await db_session.flush()
    vue = await service.composer_vue(db_session, launch=launch, invitation=inv)
    assert vue.graine is not None

    graine = bytes.fromhex(vue.graine)
    assert verifier_engagement(graine, vue.engagement)
    tir = tirage_depuis_json(vue.tirage)
    assert rejouer_tirage(graine, tir) == tir.resultat  # rejoué à l'identique
    assert verifier_journal(graine, [tir]) == []  # séquence et résultat conformes à la graine
    assert "R-4.7" in tir.motif


# ------------------------------------------------ choix du gagnant + premier joueur


async def test_gagnant_choisit_de_commencer_siege_zero(db_session):
    """Le gagnant choisit de commencer : il est le premier joueur, assis au siège 0 (tour 1)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    gagnant = launch.tirage_gagnant_user_id
    launch, _ = await service.choisir(
        db_session, invitation_id=inv.id, user_id=gagnant, commencer=True, maintenant=T0
    )
    assert launch.premier_joueur_user_id == gagnant
    siege0 = (
        await db_session.execute(
            GamePlayer.__table__.select().where(
                (GamePlayer.game_id == launch.game_id) & (GamePlayer.seat == 0)
            )
        )
    ).first()
    assert siege0.user_id == gagnant


async def test_gagnant_laisse_commencer_adversaire(db_session):
    """Le gagnant peut refuser de commencer : l'autre est alors le premier joueur (livret R-1.1)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    gagnant = launch.tirage_gagnant_user_id
    autre = b.id if gagnant == a.id else a.id
    launch, _ = await service.choisir(
        db_session, invitation_id=inv.id, user_id=gagnant, commencer=False, maintenant=T0
    )
    assert launch.premier_joueur_user_id == autre


async def test_seul_le_gagnant_choisit(db_session):
    """L'autre joueur n'a pas le choix du premier tour : il est refusé (→ 409)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    perdant = b.id if launch.tirage_gagnant_user_id == a.id else a.id
    with pytest.raises(PasLeGagnantDuTirage):
        await service.choisir(
            db_session, invitation_id=inv.id, user_id=perdant, commencer=True, maintenant=T0
        )


async def test_choix_par_defaut_apres_le_delai(db_session):
    """Sans choix dans le délai, le choix par défaut s'applique : le gagnant commence (R-4.7)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b, maintenant=T0)
    gagnant = launch.tirage_gagnant_user_id

    apres = T0 + service.DELAI_CHOIX + timedelta(seconds=1)
    launch, _ = await service.obtenir_ou_creer(
        db_session, invitation_id=inv.id, user_id=a.id, maintenant=apres
    )
    assert launch.statut == LANCEMENT_STATUT_LANCE
    assert launch.premier_joueur_user_id == gagnant
    assert launch.choix_commencer is True
    assert launch.game_id is not None


# ------------------------------------------------------- deck devenu injouable : arrêt, sans partie


async def test_deck_vendu_arrete_le_lancement_sans_partie(db_session):
    """Une carte vendue arrête le lancement en nommant les cartes, sans partie."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    da = await _make_deck_possede(db_session, a.id)
    db_deck = await _make_deck_possede(db_session, b.id)
    inv = await _invitation_acceptee(db_session, a, b, da, db_deck)
    launch = await _preparer_les_deux(db_session, inv, a, b)
    gagnant = launch.tirage_gagnant_user_id

    # « Vente » : on retire tous les exemplaires possédés du deck de A — il devient injouable.
    da_cards = [
        row.card_id
        for row in (
            await db_session.execute(DeckCard.__table__.select().where(DeckCard.deck_id == da.id))
        ).all()
    ]
    await db_session.execute(
        CollectionItem.__table__.delete().where(
            (CollectionItem.user_id == a.id) & (CollectionItem.card_id.in_(da_cards))
        )
    )
    await db_session.flush()

    with pytest.raises(DeckInjouable) as exc:
        await service.choisir(
            db_session, invitation_id=inv.id, user_id=gagnant, commencer=True, maintenant=T0
        )
    assert any("Carapuce" in nom for nom, _ in exc.value.refus)
    # Aucune partie fantôme : le lancement reste en tirage, sans game_id.
    relu, _ = await service.obtenir_ou_creer(
        db_session, invitation_id=inv.id, user_id=a.id, maintenant=T0
    )
    assert relu.statut == LANCEMENT_STATUT_TIRAGE
    assert relu.game_id is None
    assert (await db_session.execute(Game.__table__.select())).first() is None


async def test_deck_injouable_refuse_a_la_preparation(db_session):
    """Un deck non possédé est refusé dès la préparation (le joueur reste non prêt)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    da = await _make_deck_possede(db_session, a.id)
    # Deck de B sans aucun exemplaire possédé.
    set_row = Set(code=f"np-{uuid.uuid4().hex[:8]}", name="S", series="T")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
        name="Salamèche",
        supertype="Pokémon",
        energy_type="fire",
        element_type="fire",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    db_session.add(card)
    await db_session.flush()
    deck_b = Deck(user_id=b.id, name="Deck non possédé")
    db_session.add(deck_b)
    await db_session.flush()
    db_session.add(DeckCard(deck_id=deck_b.id, card_id=card.id, quantity=4))
    await db_session.flush()
    inv = await _invitation_acceptee(db_session, a, b, da, deck_b)

    with pytest.raises(DeckInjouable):
        await service.se_preparer(db_session, invitation_id=inv.id, user_id=b.id, maintenant=T0)
    relu, _ = await service.obtenir_ou_creer(
        db_session, invitation_id=inv.id, user_id=b.id, maintenant=T0
    )
    assert relu.invitee_pret is False


# ------------------------------------------------------------- déconnexion / abandon avant le prêt


async def test_abandon_avant_le_pret(db_session):
    """Un joueur quitte avant d'être prêt : lancement figé « abandonne », aucune partie créée."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    await service.se_preparer(db_session, invitation_id=inv.id, user_id=a.id, maintenant=T0)
    launch, _ = await service.abandonner(
        db_session, invitation_id=inv.id, user_id=b.id, maintenant=T0
    )
    assert launch.statut == LANCEMENT_STATUT_ABANDONNE
    assert launch.game_id is None


# ------------------------------------------------------------------------------- isolation / phases


async def test_tiers_ne_voit_pas_le_lancement(db_session):
    """Un joueur sans rôle dans l'invitation ne voit pas le lancement (→ 404, pas de fuite)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    c = await _make_user(db_session, pseudo="carol")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    with pytest.raises(LancementIntrouvable):
        await service.obtenir_ou_creer(db_session, invitation_id=inv.id, user_id=c.id)


async def test_invitation_non_acceptee_refusee(db_session):
    """On ne lance pas depuis une invitation encore « envoyée » (→ 409)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
        statut=INVITATION_STATUT_ENVOYEE,
    )
    with pytest.raises(InvitationPasAcceptee):
        await service.obtenir_ou_creer(db_session, invitation_id=inv.id, user_id=a.id)


async def test_premier_joueur_est_joueur_actif_du_moteur(db_session):
    """Le premier joueur est bien le joueur actif du tour 1 dans l'état initial du moteur."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    inv = await _invitation_acceptee(
        db_session,
        a,
        b,
        await _make_deck_possede(db_session, a.id),
        await _make_deck_possede(db_session, b.id),
    )
    launch = await _preparer_les_deux(db_session, inv, a, b)
    gagnant = launch.tirage_gagnant_user_id
    launch, _ = await service.choisir(
        db_session, invitation_id=inv.id, user_id=gagnant, commencer=True, maintenant=T0
    )
    game = await db_session.get(Game, launch.game_id)
    assert game.etat_initial["tour"]["joueur_actif"] == joueur_id_de(launch.premier_joueur_user_id)
    assert game.etat_initial["tour"]["numero"] == 1
