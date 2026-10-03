"""Mode solo : marqueur « entraînement », niveau du bot, et compte bot réservé.

Lot ``j-mode-solo`` (DJ7) — jouer une partie d'entraînement contre un bot :

* ``games.entrainement`` (bool) — la partie est un entraînement contre le bot : elle entre dans
  l'historique du joueur mais ne compte pas (ni classement ni séries) ;
* ``game_players.bot_niveau`` (str) — le niveau du bot quand ce siège est le sien
  (« hasard » / « correct » / « coriace »), ``NULL`` pour un siège humain ;
* le **compte bot réservé** — une ligne ``users`` d'identité fixe, jamais connectable (hash de
  mot de passe impossible, e-mail non vérifié, aucun accès jeu HTTP) : le bot joue côté serveur,
  la clé étrangère ``game_players.user_id`` exige un compte réel. On l'insère ici, une fois, de
  façon idempotente (``ON CONFLICT DO NOTHING``) : ainsi il est toujours présent, sans course à la
  création d'une partie.

Revision ID: f1c0b07a1d02
Revises: d4e1f2a3b5c6
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "f1c0b07a1d02"
down_revision = "d4e1f2a3b5c6"
branch_labels = None
depends_on = None

#: Identité fixe du compte bot réservé (doit coïncider avec ``pbm_api.games.bot.BOT_USER_ID``).
BOT_USER_ID = "b07b07b0-0000-4000-8000-000000000001"
BOT_EMAIL = "pokebot@system.pokeboy.invalid"


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("entrainement", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "game_players",
        sa.Column("bot_niveau", sa.String(length=16), nullable=True),
    )
    # Compte bot réservé. `password_hash = '!'` n'est le hash d'aucun mot de passe (argon2/bcrypt
    # produisent toujours un préfixe `$...`) : la vérification échoue toujours, le compte est donc
    # inconnectable. `game_access` reste faux (le bot ne voit rien du jeu en HTTP) ; il n'agit que
    # côté serveur. `ON CONFLICT DO NOTHING` : rejouer la migration ne duplique rien.
    # Valeurs littérales (constantes maîtrisées, aucun paramètre externe) : op.execute applique le
    # SQL tel quel, sans liaison de paramètres (plus robuste au travers des pilotes).
    op.execute(
        f"""
        INSERT INTO users (
            id, email, password_hash, last_name, birth_date,
            terms_version, terms_accepted_at, preferred_currency,
            must_change_password, game_access, created_at, updated_at
        ) VALUES (
            '{BOT_USER_ID}', '{BOT_EMAIL}', '!', 'Entra\u00eenement', DATE '2000-01-01',
            'system', now(), 'EUR',
            false, false, now(), now()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Retirer le compte bot (ses parties et sièges partent en cascade) puis les colonnes.
    op.execute(f"DELETE FROM users WHERE id = '{BOT_USER_ID}'")
    op.drop_column("game_players", "bot_niveau")
    op.drop_column("games", "entrainement")
