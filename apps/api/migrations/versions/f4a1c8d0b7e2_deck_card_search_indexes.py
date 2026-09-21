"""deck card search indexes: immutable unaccent + trigram/btree/composite

Index de la recherche de cartes du constructeur (mission `v7-decks-recherche`, point 2 : cible de
150 ms au 95e centile sur 22 000 cartes / 5 000 exemplaires). Ajoute UNIQUEMENT des index et une
fonction — aucune donnée touchée, aucune table modifiée.

Choix hors modèle SQLAlchemy (contrairement aux index trigram de `models/catalog.py`) :
l'index trigram accent-insensible s'appuie sur une fonction `unaccent` rendue IMMUTABLE, qui ne
s'exprime pas proprement dans un `__table_args__`. Les migrations de ce dépôt sont écrites à la
main (pas d'autogenerate), donc poser ces index en SQL est cohérent avec la vue matérialisée
`card_value_rank` (migration `11f10f8c0f40`), elle aussi en SQL brut.

Revision ID: f4a1c8d0b7e2
Revises: d1c7a3f0b2e4
Create Date: 2026-09-21 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a1c8d0b7e2"
down_revision: str | Sequence[str] | None = "c3a7e1f4d820"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# `unaccent(text)` à un argument n'est que STABLE (elle dépend du `search_path` pour choisir le
# dictionaire) : non indexable. En figeant le dictionnaire (`'unaccent'::regdictionary`), la
# fonction devient déterministe et peut être déclarée IMMUTABLE — pattern standard pg_trgm +
# unaccent. STRICT : NULL en entrée -> NULL en sortie. C'est cette expression EXACTE que
# `pbm_api.decks.card_search._unaccent` reproduit, pour que la recherche par sous-chaîne utilise
# l'index fonctionnel.
#
# ⚠️ Le corps est qualifié par son schéma (`public.`), y compris le dictionnaire, parce qu'il est
# résolu À L'APPEL et non à la création. `pg_restore` ouvre sa session avec
# `set_config('search_path', '', false)` : un `unaccent('unaccent'::regdictionary, …)` nu n'y
# résout plus rien, et l'index fonctionnel, maintenu pendant le COPY, fait échouer la restauration
# du catalogue (« text search dictionary "unaccent" does not exist » — CI rouge du 21/09 sur
# `tests/test_catalogue_seed.py`). Qualifier ne change pas l'expression indexée
# (`pbm_immutable_unaccent(lower(name))`), donc aucun plan n'en dépend.
_CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION public.pbm_immutable_unaccent(text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
"""

_UPGRADE_INDEXES = [
    # Recherche par sous-chaîne accent-insensible des noms FR/EN (`col LIKE '%needle%'`).
    "CREATE INDEX IF NOT EXISTS ix_cards_name_unaccent_trgm "
    "ON cards USING gin (pbm_immutable_unaccent(lower(name)) gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_card_names_name_unaccent_trgm "
    "ON card_names USING gin (pbm_immutable_unaccent(lower(name)) gin_trgm_ops)",
    # Filtres de facettes (type, rareté, PV).
    "CREATE INDEX IF NOT EXISTS ix_cards_supertype ON cards (supertype)",
    "CREATE INDEX IF NOT EXISTS ix_cards_rarity ON cards (rarity)",
    "CREATE INDEX IF NOT EXISTS ix_cards_hp ON cards (hp)",
    # Sous-requête de possession (`WHERE user_id = :u GROUP BY card_id`) et bascules
    # « mes cartes »/« doublons » : le composé (user_id, card_id) sert le regroupement.
    "CREATE INDEX IF NOT EXISTS ix_collection_items_user_card "
    "ON collection_items (user_id, card_id)",
]

_DOWNGRADE_INDEXES = [
    "DROP INDEX IF EXISTS ix_collection_items_user_card",
    "DROP INDEX IF EXISTS ix_cards_hp",
    "DROP INDEX IF EXISTS ix_cards_rarity",
    "DROP INDEX IF EXISTS ix_cards_supertype",
    "DROP INDEX IF EXISTS ix_card_names_name_unaccent_trgm",
    "DROP INDEX IF EXISTS ix_cards_name_unaccent_trgm",
]


def upgrade() -> None:
    op.execute(_CREATE_FUNCTION)
    for statement in _UPGRADE_INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE_INDEXES:
        op.execute(statement)
    op.execute("DROP FUNCTION IF EXISTS public.pbm_immutable_unaccent(text)")
