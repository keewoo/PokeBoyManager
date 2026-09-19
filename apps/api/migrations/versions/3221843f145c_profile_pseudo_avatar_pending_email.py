"""profile: pseudo, avatar, pending email

Revision ID: 3221843f145c
Revises: d42b0620077e
Create Date: 2026-09-19 21:44:41.485855

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3221843f145c'
down_revision: str | Sequence[str] | None = 'd42b0620077e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('pending_email', sa.String(length=320), nullable=True))
    op.add_column('users', sa.Column('pseudo', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('avatar_key', sa.String(length=255), nullable=True))
    op.create_unique_constraint('uq_users_pseudo', 'users', ['pseudo'])
    # Nouvelle valeur de `email_token_kind` (jeton de confirmation de changement d'adresse) —
    # `ALTER TYPE ... ADD VALUE` ne peut pas être annulé par un `downgrade()` (Postgres ne sait
    # pas retirer une valeur d'un type énuméré) : accepté ici, comme documenté dans
    # `downgrade()`.
    op.execute("ALTER TYPE email_token_kind ADD VALUE 'change_email'")


def downgrade() -> None:
    """Downgrade schema.

    La valeur `change_email` ajoutée à `email_token_kind` reste en place : Postgres ne permet
    pas de retirer une valeur d'un type énuméré (il faudrait recréer le type et toutes ses
    dépendances). Sans impact si aucune ligne ne l'utilise plus après ce downgrade.
    """
    op.drop_constraint('uq_users_pseudo', 'users', type_='unique')
    op.drop_column('users', 'avatar_key')
    op.drop_column('users', 'pseudo')
    op.drop_column('users', 'pending_email')
