"""Modèle de persistance des **invitations à jouer** (lot `j-invitations`).

Entre deux frères ou deux amis, on n'« cherche pas un adversaire » : on invite quelqu'un de précis.
Cette table porte exactement cela — une invitation de jeu et son cycle de vie — distinct de la file
d'attente anonyme (`pbm_api.games.matchmaking`, lot `j-file-attente`) et du service de parties
(`pbm_api.games.service`).

Deux **modes** d'invitation, une même table :

* :data:`INVITATION_MODE_PSEUDO` — on vise un compte invité par son pseudo. ``invitee_user_id`` est
  renseigné dès la création (la cible connue), ``token_hash`` reste nul ;
* :data:`INVITATION_MODE_LIEN` — on fabrique un lien à usage unique à partager. ``token_hash`` porte
  l'empreinte SHA-256 du jeton (le jeton en clair ne transite qu'une fois, jamais stocké ni
  journalisé — même règle que les sessions et les jetons d'e-mail, `pbm_api.security.tokens`).
  ``invitee_user_id`` est nul jusqu'à ce qu'un joueur suive le lien et l'accepte : on enregistre
  alors **qui** a rejoint.

Le **deck annoncé** de chaque camp (``inviter_deck_id`` / ``invitee_deck_id``) est en ``SET NULL`` :
supprimer un deck ne doit pas effacer l'invitation, et le salon d'attente affichera « deck retiré »
plutôt que mentir. Le choix et le contrôle définitifs du deck, le tirage au sort et le « prêt à
jouer » sont le lot aval `j-lancement-partie` — ici on ne fait qu'**annoncer**.

Le cycle de vie (``statut``) est strict : une invitation part
:data:`INVITATION_STATUT_ENVOYEE`, puis l'une des issues finales — acceptée, refusée, annulée
(par l'émetteur) ou expirée (échéance passée).
Une issue finale ne revient jamais à « envoyée » : c'est ce qui rend un lien **à usage unique** (une
fois accepté, il n'est plus « envoyé », donc plus réutilisable) et une expiration irréversible. Les
transitions elles-mêmes vivent dans `pbm_api.games.invitations` — ce module ne décrit que la forme.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

# --- Statuts d'une invitation (stables, lus par le service et les écrans) ----
#: Invitation émise, en attente d'une réponse — le seul statut depuis lequel on peut agir.
INVITATION_STATUT_ENVOYEE = "envoyee"
#: Acceptée : le salon d'attente à deux est ouvert (les deux camps y sont annoncés).
INVITATION_STATUT_ACCEPTEE = "acceptee"
#: Refusée par le destinataire d'une invitation par pseudo.
INVITATION_STATUT_REFUSEE = "refusee"
#: Annulée par l'émetteur avant toute réponse.
INVITATION_STATUT_ANNULEE = "annulee"
#: Expirée : l'échéance est passée sans réponse. Irréversible — c'est ce qui périme un lien.
INVITATION_STATUT_EXPIREE = "expiree"

#: L'ensemble des statuts reconnus. Un statut hors de cet ensemble est un bug, jamais écrit.
INVITATION_STATUTS: frozenset[str] = frozenset(
    {
        INVITATION_STATUT_ENVOYEE,
        INVITATION_STATUT_ACCEPTEE,
        INVITATION_STATUT_REFUSEE,
        INVITATION_STATUT_ANNULEE,
        INVITATION_STATUT_EXPIREE,
    }
)

# --- Modes d'invitation ------------------------------------------------------
#: On vise un compte invité connu, par son pseudo.
INVITATION_MODE_PSEUDO = "pseudo"
#: On fabrique un lien à usage unique à partager.
INVITATION_MODE_LIEN = "lien"

#: L'ensemble des modes reconnus.
INVITATION_MODES: frozenset[str] = frozenset({INVITATION_MODE_PSEUDO, INVITATION_MODE_LIEN})


class GameInvitation(Base, TimestampMixin):
    """Une invitation à jouer : qui invite, qui est visé (ou quel lien), les decks annoncés.

    Pour un lien (:data:`INVITATION_MODE_LIEN`), ``token_hash`` est l'empreinte du jeton partagé —
    **jamais** le jeton en clair. Il est unique : deux liens ne peuvent pas porter le même secret.
    Comme un jeton de lien est nul pour une invitation par pseudo, la contrainte d'unicité tolère
    plusieurs NULL (sémantique SQL standard), ce qui laisse coexister autant d'invitations par
    pseudo que voulu.

    ``expires_at`` est l'échéance : au-delà, l'invitation est considérée expirée (transition
    paresseuse à la lecture, plus une purge éventuelle). C'est ce qui garantit qu'un lien ne vit pas
    indéfiniment. ``resolved_at`` est posé à l'instant de l'issue finale (acceptée/refusée/annulée/
    expirée) — nul tant que l'invitation est en attente.
    """

    __tablename__ = "game_invitations"
    __table_args__ = (
        # Un lien = un secret unique. Les invitations par pseudo (token_hash NULL) coexistent
        # librement — SQL ne contraint pas les NULL entre eux.
        UniqueConstraint("token_hash", name="uq_game_invitations_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    statut: Mapped[str] = mapped_column(
        String(16), nullable=False, default=INVITATION_STATUT_ENVOYEE, index=True
    )
    # Qui invite. CASCADE : supprimer le compte efface ses invitations (rien à conserver sans lui).
    inviter_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Qui est visé : connu dès le départ (mode pseudo), ou renseigné à l'acceptation (mode lien).
    invitee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Decks annoncés de chaque camp — SET NULL : supprimer un deck n'efface pas l'invitation.
    inviter_deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    invitee_deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    # Empreinte SHA-256 du jeton d'un lien (mode lien) ; nul pour une invitation par pseudo.
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Échéance d'expiration et instant de l'issue finale.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
