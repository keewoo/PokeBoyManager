"""Service des invitations à jouer (`pbm_api.games.invitations`) — lot `j-invitations`.

Vérifie le cœur du lot **sans passer par HTTP** (le routeur a ses propres tests) : les transitions
(acceptée, refusée, annulée, expirée), l'**usage unique** d'un lien, le fait qu'un lien **n'ouvre
aucun droit** (D11, `game_access` jamais touché), le refus d'un deck non jouable en nommant les
cartes (D9), et la **symétrie du salon** (les deux joueurs voient la même chose).

Chaque test échoue sans le code du lot (le module `pbm_api.games.invitations` n'existerait pas).
Les factories créent utilisateurs et decks directement en base (la fixture `db_session` annule tout
en fin de test).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from pbm_api.games import invitations as service
from pbm_api.games.entry import DeckInjouable
from pbm_api.games.invitations import (
    AutoInvitation,
    DestinataireIntrouvable,
    InvitationIntrouvable,
    InvitationNonEnAttente,
)
from pbm_api.models import Card, Deck, DeckCard, Set, User
from pbm_api.models.invitations import (
    INVITATION_STATUT_ACCEPTEE,
    INVITATION_STATUT_ANNULEE,
    INVITATION_STATUT_EXPIREE,
    INVITATION_STATUT_REFUSEE,
)


class _EmailMuet:
    """Émetteur d'e-mail de test : capture les envois sans dépendre d'un SMTP."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


async def _make_user(db, *, game_access=True, pseudo=None) -> User:
    """Crée un utilisateur minimal (champs non nuls renseignés), invité au jeu par défaut."""
    user = User(
        email=f"u-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        last_name="Dresseur",
        birth_date=date(2000, 1, 1),
        terms_version="1",
        terms_accepted_at=datetime(2000, 1, 1),
        game_access=game_access,
        pseudo=pseudo,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_deck_jouable(db, user_id: uuid.UUID) -> uuid.UUID:
    """Un deck dont chaque carte se compile pour le moteur (le même motif que les tests de file)."""
    set_row = Set(code=f"inv-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name="Carapuce",
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
    deck = Deck(user_id=user_id, name="Deck jouable")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
    await db.flush()
    return deck.id


async def _make_deck_casse(db, user_id: uuid.UUID) -> uuid.UUID:
    """Un deck avec une carte non scriptée (prize_marker nul) : refusé à l'annonce (D9)."""
    set_row = Set(code=f"invc-{uuid.uuid4().hex[:8]}", name="Set jeu", series="Série test")
    db.add(set_row)
    await db.flush()
    card = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 1000),
        name="Insolourdo",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker=None,
    )
    db.add(card)
    await db.flush()
    deck = Deck(user_id=user_id, name="Deck cassé")
    db.add(deck)
    await db.flush()
    db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=8))
    await db.flush()
    return deck.id


async def test_invitation_par_pseudo_acceptee(db_session):
    """Invitation par pseudo acceptée : statut « acceptee », deck annoncé, mail parti."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    deck_a = await _make_deck_jouable(db_session, a.id)
    deck_b = await _make_deck_jouable(db_session, b.id)
    email = _EmailMuet()

    inv = await service.inviter_par_pseudo(
        db_session, email, inviter_id=a.id, pseudo="bob", deck_id=deck_a
    )
    assert inv.statut == "envoyee"
    assert inv.invitee_user_id == b.id
    # Notification dans l'application : B la voit dans ses invitations reçues.
    assert [i.id for i in await service.recues(db_session, user_id=b.id)] == [inv.id]
    # Relais e-mail parti vers l'adresse de B (rappel).
    assert email.sent and email.sent[-1]["to"] == b.email

    accepte = await service.accepter(
        db_session, invitation_id=inv.id, invitee_id=b.id, deck_id=deck_b
    )
    assert accepte.statut == INVITATION_STATUT_ACCEPTEE
    assert accepte.invitee_deck_id == deck_b


async def test_pseudo_inconnu_ou_sans_acces_introuvable(db_session):
    """Pseudo inconnu ET pseudo sans accès au jeu lèvent la MÊME erreur (pas de fuite D11)."""
    a = await _make_user(db_session, pseudo="alice")
    await _make_user(db_session, game_access=False, pseudo="sansacces")
    email = _EmailMuet()
    with pytest.raises(DestinataireIntrouvable):
        await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="inexistant")
    with pytest.raises(DestinataireIntrouvable):
        await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="sansacces")


async def test_auto_invitation_refusee(db_session):
    """On ne s'invite pas soi-même."""
    a = await _make_user(db_session, pseudo="alice")
    email = _EmailMuet()
    with pytest.raises(AutoInvitation):
        await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="alice")


async def test_deck_non_jouable_refuse_nomme_les_cartes(db_session):
    """Un deck annoncé non jouable est refusé en nommant la carte en cause (D9)."""
    a = await _make_user(db_session, pseudo="alice")
    await _make_user(db_session, pseudo="bob")  # la cible doit exister pour atteindre le deck
    deck_casse = await _make_deck_casse(db_session, a.id)
    email = _EmailMuet()
    with pytest.raises(DeckInjouable) as exc:
        await service.inviter_par_pseudo(
            db_session, email, inviter_id=a.id, pseudo="bob", deck_id=deck_casse
        )
    assert any("Insolourdo" in nom for nom, _ in exc.value.refus)


async def test_invitation_refusee(db_session):
    """Refus d'une invitation reçue : statut « refusee », plus disponible."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    email = _EmailMuet()
    inv = await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="bob")
    refus = await service.refuser(db_session, invitation_id=inv.id, invitee_id=b.id)
    assert refus.statut == INVITATION_STATUT_REFUSEE
    assert await service.recues(db_session, user_id=b.id) == []


async def test_annulation_par_emetteur(db_session):
    """L'émetteur peut annuler ; un tiers ne « trouve » pas l'invitation (404-like)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    email = _EmailMuet()
    inv = await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="bob")
    with pytest.raises(InvitationIntrouvable):
        await service.annuler(db_session, invitation_id=inv.id, inviter_id=b.id)
    annule = await service.annuler(db_session, invitation_id=inv.id, inviter_id=a.id)
    assert annule.statut == INVITATION_STATUT_ANNULEE


async def test_invitation_expiree(db_session):
    """Une invitation échue est expirée paresseusement et ne peut plus être acceptée."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    email = _EmailMuet()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    inv = await service.inviter_par_pseudo(
        db_session, email, inviter_id=a.id, pseudo="bob", maintenant=t0
    )
    plus_tard = t0 + service.TTL_INVITATION + timedelta(seconds=1)
    # Elle n'apparaît plus dans les reçues, et l'accepter lève (statut devenu « expiree »).
    assert await service.recues(db_session, user_id=b.id, maintenant=plus_tard) == []
    with pytest.raises(InvitationNonEnAttente):
        await service.accepter(
            db_session, invitation_id=inv.id, invitee_id=b.id, maintenant=plus_tard
        )
    rafraichie = await db_session.get(type(inv), inv.id)
    assert rafraichie.statut == INVITATION_STATUT_EXPIREE


async def test_lien_usage_unique(db_session):
    """Un lien accepté ne peut pas resservir : la seconde acceptation est refusée."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    c = await _make_user(db_session, pseudo="carol")
    inv, jeton = await service.inviter_par_lien(db_session, inviter_id=a.id)
    assert inv.token_hash and inv.token_hash != jeton  # stocké haché, jamais en clair

    rejoint = await service.accepter_par_lien(db_session, jeton=jeton, invitee_id=b.id)
    assert rejoint.statut == INVITATION_STATUT_ACCEPTEE
    assert rejoint.invitee_user_id == b.id
    # Un second usage du même lien (par un autre joueur) est refusé : usage unique.
    with pytest.raises(InvitationNonEnAttente):
        await service.accepter_par_lien(db_session, jeton=jeton, invitee_id=c.id)


async def test_lien_inconnu_introuvable(db_session):
    """Un jeton qui ne correspond à aucun lien lève « introuvable » (→ 404)."""
    b = await _make_user(db_session, pseudo="bob")
    with pytest.raises(InvitationIntrouvable):
        await service.accepter_par_lien(db_session, jeton="jeton-bidon", invitee_id=b.id)


async def test_lien_nouvre_aucun_droit(db_session):
    """Suivre un lien ne modifie jamais `game_access` : il rejoint, il n'ouvre rien (D11)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob", game_access=True)
    _, jeton = await service.inviter_par_lien(db_session, inviter_id=a.id)
    avant = b.game_access
    await service.accepter_par_lien(db_session, jeton=jeton, invitee_id=b.id)
    await db_session.refresh(b)
    assert b.game_access == avant  # inchangé : aucune promotion d'accès


async def test_salon_symetrique(db_session):
    """Les deux joueurs voient le MÊME salon et le MÊME deck annoncé (vue symétrique)."""
    a = await _make_user(db_session, pseudo="alice")
    b = await _make_user(db_session, pseudo="bob")
    deck_a = await _make_deck_jouable(db_session, a.id)
    deck_b = await _make_deck_jouable(db_session, b.id)
    email = _EmailMuet()
    inv = await service.inviter_par_pseudo(
        db_session, email, inviter_id=a.id, pseudo="bob", deck_id=deck_a
    )
    await service.accepter(db_session, invitation_id=inv.id, invitee_id=b.id, deck_id=deck_b)

    vu_par_a = await service.salon(db_session, invitation_id=inv.id, user_id=a.id)
    vu_par_b = await service.salon(db_session, invitation_id=inv.id, user_id=b.id)
    assert vu_par_a == vu_par_b  # strictement identique
    assert vu_par_a.inviter.deck.deck_id == deck_a
    assert vu_par_a.invitee.deck.deck_id == deck_b


async def test_salon_tiers_introuvable(db_session):
    """Un joueur qui n'a aucun rôle dans l'invitation ne voit pas le salon (→ 404)."""
    a = await _make_user(db_session, pseudo="alice")
    await _make_user(db_session, pseudo="bob")  # destinataire de l'invitation
    c = await _make_user(db_session, pseudo="carol")
    email = _EmailMuet()
    inv = await service.inviter_par_pseudo(db_session, email, inviter_id=a.id, pseudo="bob")
    with pytest.raises(InvitationIntrouvable):
        await service.salon(db_session, invitation_id=inv.id, user_id=c.id)
