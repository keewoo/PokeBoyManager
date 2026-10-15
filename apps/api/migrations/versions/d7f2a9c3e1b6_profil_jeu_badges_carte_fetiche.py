"""Profil de joueur : badges obtenus et carte fétiche (lot ``j-profil-jeu``, jalon J4, DJ6).

Deux choses, et la deuxième tient en une colonne.

**``player_badges``** — un badge obtenu par un compte, une ligne, jamais deux. L'unicité
``(user_id, code)`` **est** le critère d'acceptation du lot (« un badge ne peut être attribué deux
fois ») : elle vit en base parce qu'un ``if`` perdrait la course entre deux clôtures concurrentes,
exactement comme ``uq_game_results_game`` pour la clôture elle-même. ``game_id`` est **sans clé
étrangère**, volontairement : la purge efface les parties mortes de plus de trente jours, et un
badge ne doit pas disparaître avec la partie qui l'a fait gagner (c'est la panne muette que
`j-fin-effets-compte` avait déjà payée pour ``game_results``).

**``users.carte_fetiche_card_id``** — la carte que le joueur montre à son adversaire au lancement.
En ``SET NULL`` sur ``cards`` : une carte retirée du catalogue vide le choix plutôt que de bloquer sa
suppression. Nullable sans valeur de repli : « je n'ai pas encore choisi » est l'état normal, et
semer une carte par défaut aurait fait parler le produit à la place du joueur.

Aucune ligne n'est semée : ni badge rétroactif, ni carte fétiche d'office. Les badges déjà mérités
avant ce lot ne sont pas reconstruits — quatre des cinq le seront naturellement à la prochaine
partie (leurs conditions se relisent dans l'historique), le cinquième (« K.O. en un coup ») dépend
du journal de la partie et ne se rattrape pas. C'est écrit dans `docs/jeu/PROFIL.md` plutôt que
compensé par un script qui inventerait des dates.

Revision ID: d7f2a9c3e1b6
Revises: c2d9b4e7f315
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "d7f2a9c3e1b6"
down_revision: str | Sequence[str] | None = "c2d9b4e7f315"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_badges",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=48), nullable=False),
        # Sans clé étrangère vers `games` : la trace survit à la purge (en-tête du module).
        sa.Column("game_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column(
            "obtenu_a", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "code", name="uq_player_badges_user_code"),
    )
    op.create_index("ix_player_badges_user_id", "player_badges", ["user_id"])

    op.add_column(
        "users",
        sa.Column(
            "carte_fetiche_card_id", PGUUID(as_uuid=True), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_users_carte_fetiche_card",
        "users",
        "cards",
        ["carte_fetiche_card_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Redescendre efface les badges obtenus et les cartes fétiches : c'est assumé, et c'est la
    # raison pour laquelle aucun des deux ne porte de valeur monnayable (DJ6 : « sans perte de
    # points » parle du barème, pas d'un retour arrière de schéma).
    op.drop_constraint("fk_users_carte_fetiche_card", "users", type_="foreignkey")
    op.drop_column("users", "carte_fetiche_card_id")
    op.drop_index("ix_player_badges_user_id", table_name="player_badges")
    op.drop_table("player_badges")
