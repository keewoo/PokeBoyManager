"""Les badges obtenus par un compte (lot `j-profil-jeu`, jalon J4, DJ6).

Une table, une contrainte, et une raison pour chacune.

**Pourquoi une table — alors que le classement, lui, ne stocke rien.** Le classement privé est
recalculé à chaque lecture depuis ``game_result_players`` (voir `docs/jeu/CLASSEMENT.md`), et c'est
le bon choix *pour lui* : un état qu'on ne stocke pas ne peut pas se corrompre. Les badges ne
peuvent pas suivre ce chemin, pour une raison précise : l'un d'eux (« K.O. en un coup ») est un fait
du **journal** de la partie, et le journal est **purgé au bout de trente jours**
(:func:`pbm_api.games.service.purger`). Un badge recalculé à la lecture disparaîtrait donc un mois
après avoir été mérité, sans un mot. On capte donc le fait à la clôture, pendant que la preuve
existe.

**L'idempotence est une contrainte de base, pas un ``if``** — comme ``uq_game_results_game`` pour la
clôture. ``uq_player_badges_user_code`` interdit le doublon, et l'écriture est un
``INSERT … ON CONFLICT DO NOTHING`` : c'est le critère d'acceptation du lot (« un badge ne peut être
attribué deux fois »), et il tient même si deux clôtures concurrentes passent en même temps.

``obtenu_a`` et ``game_id`` racontent **quand** et **dans quelle partie** — c'est ce qui rend la
vitrine intéressante (« gagné le 14 octobre, contre Aymeric »). ``game_id`` n'a volontairement
**aucune clé étrangère** vers ``games``, pour la même raison que ``game_results`` : la purge efface
les parties, pas les traces. Un badge dont la partie a été purgée reste acquis ; il n'a simplement
plus de replay à montrer.

**Aucune valeur, aucun compte de points, aucune monnaie** : un badge est un code et une date. C'est
la mission du lot (« aucun achat, aucune monnaie, aucune récompense aléatoire »), et la forme de la
table l'interdit plutôt que de le promettre.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base


class PlayerBadge(Base):
    """Un badge obtenu par un compte — **une ligne, jamais deux** pour le même code.

    Le ``code`` est celui d'une entrée de :data:`pbm_api.jeu.badges.BADGES`. Un code retiré de la
    déclaration laisse ses lignes en base : la vitrine ne les montre plus (elle n'affiche que les
    badges déclarés), et personne ne perd rien si JF le remet. C'est pour cela que ``code`` est une
    chaîne et non une énumération SQL — retirer un badge doit être un geste de code, pas une
    migration.

    Ne porte pas de ``TimestampMixin`` : un badge ne se met jamais à jour. Il naît une fois.
    """

    __tablename__ = "player_badges"
    __table_args__ = (
        # La clé d'idempotence du lot, en base : deux clôtures concurrentes ne peuvent pas écrire
        # deux fois le même badge (un `if` perdrait cette course).
        UniqueConstraint("user_id", "code", name="uq_player_badges_user_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    # La partie qui l'a fait gagner. SANS clé étrangère : la purge efface les parties mortes de plus
    # de trente jours, et un badge ne doit pas disparaître avec elles (en-tête du module).
    game_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    obtenu_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["PlayerBadge"]
