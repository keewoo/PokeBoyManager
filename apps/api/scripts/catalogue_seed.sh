#!/usr/bin/env bash
# Graine réutilisable du catalogue — mission `v2-catalogue-complet` point 5.
#
# Exporte/restaure uniquement les tables du catalogue et des prix (sets, cards, card_names,
# card_prices_daily) — jamais les données utilisateur (users, collection_items, uploads...).
# Le déploiement (D2, hors périmètre de ce lot) l'utilisera pour peupler UAT/PROD sans refaire
# l'import complet (~20 000 cartes, ~30-90 min sur le lien à ~250 ko/s de chimera).
#
# Usage :
#   catalogue_seed.sh export <DATABASE_URL> [DUMP_PATH]
#   catalogue_seed.sh import <DATABASE_URL> [DUMP_PATH]
#
# DATABASE_URL accepte le format asyncpg de l'API (postgresql+asyncpg://...) ou un DSN libpq
# standard — le préfixe +asyncpg est retiré automatiquement (pg_dump/pg_restore ne le comprennent
# pas). DUMP_PATH par défaut : `import` prend le dernier export (symlink `latest.dump`), `export`
# écrit un nouveau fichier horodaté.
#
# Dépendance : postgresql-client (pg_dump/pg_restore) sur la machine qui exécute ce script —
# absent par défaut sur chimera (voir compte rendu du lot pour l'avoir installé sans sudo).
#
# Idempotent : `import` vide d'abord les 4 tables ciblées (DELETE, dans l'ordre des dépendances,
# jamais TRUNCATE CASCADE) avant de restaurer — rejouer le même import ne duplique rien. Si une
# table utilisateur (collection_items, detections, card_insights) référence déjà une carte, le
# DELETE échoue explicitement plutôt que de supprimer silencieusement ces données : ce script est
# prévu pour peupler une base neuve, pas pour re-semer un environnement déjà ouvert aux
# utilisateurs.

set -euo pipefail

ARTEFACT_DIR="${PBM_ARTEFACT_DIR:-$HOME/dev/pbm-artefacts}"
TABLES=(sets cards card_names card_prices_daily)
# Ordre de suppression : les tables dépendantes (FK vers cards/sets) d'abord.
DELETE_ORDER=(card_prices_daily card_names cards sets)

usage() {
    echo "Usage: $0 export|import <DATABASE_URL> [DUMP_PATH]" >&2
    exit 1
}

[ $# -ge 2 ] || usage
ACTION="$1"
DATABASE_URL="$2"
DUMP_PATH="${3:-}"

# pg_dump/pg_restore parlent le DSN libpq, pas le préfixe du driver asyncpg de SQLAlchemy.
PG_DSN="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql://}"

mkdir -p "$ARTEFACT_DIR"

case "$ACTION" in
    export)
        if [ -z "$DUMP_PATH" ]; then
            DUMP_PATH="$ARTEFACT_DIR/catalogue-$(date +%Y%m%d-%H%M%S).dump"
        fi
        TABLE_ARGS=()
        for t in "${TABLES[@]}"; do
            TABLE_ARGS+=(--table="$t")
        done
        pg_dump "$PG_DSN" --format=custom --data-only --disable-triggers \
            --no-owner --no-privileges "${TABLE_ARGS[@]}" --file="$DUMP_PATH"
        ln -sf "$(basename "$DUMP_PATH")" "$ARTEFACT_DIR/latest.dump"
        echo "Export écrit : $DUMP_PATH"
        ;;
    import)
        if [ -z "$DUMP_PATH" ]; then
            DUMP_PATH="$ARTEFACT_DIR/latest.dump"
        fi
        [ -f "$DUMP_PATH" ] || {
            echo "Archive introuvable : $DUMP_PATH" >&2
            exit 1
        }
        for t in "${DELETE_ORDER[@]}"; do
            psql "$PG_DSN" -v ON_ERROR_STOP=1 -c "DELETE FROM $t;"
        done
        pg_restore --dbname="$PG_DSN" --data-only --disable-triggers \
            --no-owner --no-privileges "$DUMP_PATH"
        echo "Import terminé depuis : $DUMP_PATH"
        ;;
    *)
        usage
        ;;
esac
