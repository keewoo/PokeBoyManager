"""La **file de demandes** « je voudrais jouer cette carte » — table `card_play_requests`.

Lot `j-effets-couverture-outil`.

Un joueur dont le deck refuse une carte (effet non scripté, D9) peut demander qu'elle devienne
jouable. Chaque demande nourrit la **priorisation** du chantier de scriptage : les lots de scripts
lisent cette file pour savoir ce que les joueurs veulent vraiment jouer, plutôt que de scripter au
hasard dans les trente mille cartes du catalogue (risque du lot : scripter ce que personne ne
possède).

Une ligne = (un joueur, une carte). La contrainte d'unicité `(user_id, card_id)` fait qu'une
seconde demande du même joueur pour la même carte **met à jour** celle qui existe (jamais un
doublon) : le compte de demandeurs distincts par carte reste ainsi honnête.

Le ``statut`` suit le cycle de vie de la demande, posé par l'exploitation (un lot de scripts qui
traite la carte) :

* ``en_attente`` — demande reçue, pas encore traitée ;
* ``scriptee`` — l'effet a été scripté depuis : la demande est satisfaite ;
* ``refusee`` — l'effet ne sera pas pris en charge (hors langage v1), raison en ``note``.

La *vraie* progression visible par le joueur ne se lit pas seulement dans ce statut : elle se
recalcule à la lecture contre le registre `card_scripts` (une carte peut être devenue jouable sans
qu'on ait repassé le statut à la main). Le statut porte l'**intention** de l'exploitation ; la
jouabilité courante porte le **fait**. Les deux sont renvoyés au joueur (`jeu/scripts/demandes.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

#: Demande reçue, pas encore traitée par un lot de scripts.
REQUEST_STATUT_EN_ATTENTE = "en_attente"
#: L'effet de la carte a été scripté : la demande est satisfaite.
REQUEST_STATUT_SCRIPTEE = "scriptee"
#: L'effet ne sera pas pris en charge (hors langage v1) — la raison vit dans ``note``.
REQUEST_STATUT_REFUSEE = "refusee"

#: Les trois statuts reconnus — tout autre est une donnée corrompue, pas un cas « au mieux ».
REQUEST_STATUTS: frozenset[str] = frozenset(
    {REQUEST_STATUT_EN_ATTENTE, REQUEST_STATUT_SCRIPTEE, REQUEST_STATUT_REFUSEE}
)


class CardPlayRequest(Base, TimestampMixin):
    """Une demande « je voudrais jouer cette carte », bornée à (un joueur, une carte).

    Isolée par ``user_id`` comme toute donnée utilisateur : un joueur ne voit et ne touche que ses
    propres demandes (`routers/jeu_demandes.py`). L'agrégation pour la priorisation (combien de
    joueurs distincts veulent cette carte) se fait côté exploitation, jamais exposée à un joueur.
    """

    __tablename__ = "card_play_requests"
    __table_args__ = (
        # Une seule demande vivante par (joueur, carte) : une nouvelle demande met à jour celle-ci.
        UniqueConstraint("user_id", "card_id", name="uq_card_play_requests_user_card"),
        # L'agrégation de la file (priorisation) groupe par carte : un index y aide.
        Index("ix_card_play_requests_card", "card_id"),
        Index("ix_card_play_requests_statut", "statut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: Le joueur qui demande la carte (supprimé avec lui — une demande n'a pas de sens orpheline).
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: La carte demandée (supprimée avec elle du catalogue, cas théorique).
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: ``en_attente`` / ``scriptee`` / ``refusee`` — jamais hors de :data:`REQUEST_STATUTS`.
    statut: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REQUEST_STATUT_EN_ATTENTE
    )
    #: Mot libre du joueur (« je veux jouer ce talent »), ou raison d'un refus posée par l'exploit.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Date de résolution (passage à ``scriptee``/``refusee``), ``NULL`` tant qu'« en attente ».
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "CardPlayRequest",
    "REQUEST_STATUT_EN_ATTENTE",
    "REQUEST_STATUT_SCRIPTEE",
    "REQUEST_STATUT_REFUSEE",
    "REQUEST_STATUTS",
]
