"""Ce qu'une partie finie laisse sur les comptes (lot `j-fin-effets-compte`, jalon J4, DJ6).

Trois tables : ``game_results`` (le résultat d'une partie, **unique par partie** — c'est la clé
d'idempotence de la clôture), ``game_result_players`` (le résultat et les chiffres d'un joueur dans
cette partie, matière des agrégats par deck et par adversaire) et ``player_stats`` (les totaux d'un
compte, **cache recalculé** depuis la table précédente, jamais incrémenté).

⚠️ ``game_id`` n'a **volontairement aucune clé étrangère** vers ``games`` : la purge des parties
mortes (30 jours par défaut) emporterait sinon tout l'historique des joueurs en cascade, sans un
mot. La trace survit à la partie ; c'est le journal, volumineux et rejouable, que la purge libère.

Revision ID: e2a7b4c1d6f9
Revises: a1f7c3d9e5b2
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "e2a7b4c1d6f9"
down_revision = "a1f7c3d9e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_results",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        # Sans clé étrangère : voir l'en-tête.
        sa.Column("game_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("statut", sa.String(16), nullable=False),
        sa.Column("raison_fin", sa.String(32), nullable=True),
        sa.Column(
            "vainqueur_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entrainement", sa.Boolean(), nullable=False),
        sa.Column("comptabilisee", sa.Boolean(), nullable=False),
        sa.Column("coups", sa.Integer(), nullable=False),
        sa.Column("tours", sa.Integer(), nullable=False),
        sa.Column("duree_s", sa.Integer(), nullable=True),
        sa.Column("journal_numero", sa.Integer(), nullable=False),
        sa.Column("finie_a", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # LA contrainte du lot : deux clôtures de la même partie ne font qu'une ligne.
        sa.UniqueConstraint("game_id", name="uq_game_results_game"),
    )

    op.create_table(
        "game_result_players",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("game_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column(
            "deck_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("decks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "adversaire_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("adversaire_bot", sa.Boolean(), nullable=False),
        sa.Column("resultat", sa.String(8), nullable=False),
        sa.Column("comptabilisee", sa.Boolean(), nullable=False),
        sa.Column("finie_a", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duree_s", sa.Integer(), nullable=True),
        sa.Column("degats_infliges", sa.Integer(), nullable=False),
        sa.Column("kos_infliges", sa.Integer(), nullable=False),
        sa.Column("recompenses_prises", sa.Integer(), nullable=False),
        sa.Column("cartes_jouees", sa.Integer(), nullable=False),
        sa.Column("energies_attachees", sa.Integer(), nullable=False),
        sa.Column("coups_joues", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("game_id", "user_id", name="uq_game_result_players_game_user"),
    )
    op.create_index("ix_game_result_players_game_id", "game_result_players", ["game_id"])
    # L'index qui porte le recalcul des totaux : toutes les parties d'un joueur, dans l'ordre de
    # leur fin. C'est la seule requête chaude de ce lot, et elle tourne à chaque clôture.
    op.create_index(
        "ix_game_result_players_user_finie",
        "game_result_players",
        ["user_id", "finie_a"],
    )

    op.create_table(
        "player_stats",
        sa.Column(
            "user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("parties", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("victoires", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defaites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("egalites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serie_en_cours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meilleure_serie", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temps_jeu_s", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parties_entrainement", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temps_jeu_entrainement_s", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("derniere_partie_a", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("player_stats")
    op.drop_index("ix_game_result_players_user_finie", table_name="game_result_players")
    op.drop_index("ix_game_result_players_game_id", table_name="game_result_players")
    op.drop_table("game_result_players")
    op.drop_table("game_results")
