#!/bin/bash
# prep-lol.sh — PRÉPARATION d'une release de PokeBoyManager sur `kailo-srv`.
#
# Pourquoi ce fichier est dans le dépôt : ses deux prédécesseurs vivaient dans `/tmp` du serveur et
# ont été PURGÉS (constaté le 19/10/2026, en livrant le jeu). Un script de livraison qui ne survit
# pas à un nettoyage de `/tmp` n'est pas un outil, c'est un souvenir — et il manque le jour où l'on
# en a besoin. Il est donc versionné ici, copié dans la release qu'il prépare.
#
# Ce script N'ENGAGE RIEN : il remplit `releases/<TS>/` pendant que l'ancienne release continue de
# servir. La bascule est le seul fait de `deploy-switch.sh`. Il applique en revanche les migrations
# Alembic — le seul geste qui ne se défait pas d'office — et c'est pourquoi il affiche la tête AVANT
# et APRÈS : « rien à faire » est une information, pas un silence.
#
# Usage (arguments d'abord, variables d'environnement en repli pour rester lisible à côté des
# livraisons déjà consignées dans docs/LIVRAISON.md) :
#   prep-lol.sh <TS> <COMMIT> <LOT>
#   TS=… COMMIT=… LOT=… prep-lol.sh
#
# Artefacts attendus (produits par `pbm-build-lol.sh` sur chimera), dans <REL>/.artefacts/ :
#   web-<TS>.tgz  api-<TS>.tgz  game-<TS>.tgz  pbm-deploy-<TS>.sha256
#
# Dernière ligne « PREPARATION_OK » = préparation complète. Toute autre fin est un échec.
set -euo pipefail

TS="${1:-${TS:-}}"
COMMIT="${2:-${COMMIT:-}}"
LOT="${3:-${LOT:-}}"

RACINE=/srv/pokeboy/prod
UV=/srv/pokeboy/tools/.local/bin/uv

# --- 0. Contrôles d'entrée : on refuse plutôt que de préparer une release à moitié nommée --------
for v in TS COMMIT LOT; do
  [ -n "${!v}" ] || { echo "⛔ $v manquant — usage : prep-lol.sh <TS> <COMMIT> <LOT>" >&2; exit 2; }
done
case "$TS" in
  [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]) ;;
  *) echo "⛔ TS « $TS » n'est pas un horodatage AAAAMMJJ-HHMMSS" >&2; exit 2 ;;
esac

echo "=== PREPARATION $TS (commit ${COMMIT:0:12}, lot $LOT) ==="

REL="$RACINE/releases/$TS"
ART="$REL/.artefacts"
[ -d "$ART" ] || { echo "⛔ $ART absent — les artefacts n'ont pas été transférés" >&2; exit 2; }

# Une release en service ne se re-prépare pas sous les pieds de ses propres processus.
if [ "$(readlink -f "$RACINE/app" 2>/dev/null || true)" = "$(readlink -f "$REL")" ]; then
  echo "⛔ $TS est la release EN SERVICE — préparer dessus casserait le service en cours" >&2
  exit 3
fi

# --- 1. Empreintes : ce qui est arrivé est bien ce que chimera a construit -----------------------
cd "$ART"
SHAFILE="pbm-deploy-$TS.sha256"
[ -f "$SHAFILE" ] || { echo "⛔ $SHAFILE absent — pas de relevé d'empreintes, on ne déballe rien" >&2; exit 2; }
for f in "web-$TS.tgz" "api-$TS.tgz" "game-$TS.tgz"; do
  [ -s "$f" ] || { echo "⛔ $f absent ou vide" >&2; exit 2; }
done
echo "--- empreintes SHA-256 ---"
sha256sum -c "$SHAFILE"

# --- 2. Déballage. `game` AVANT la synchronisation des dépendances : l'API le déclare en editable
#        sous `../game`, il doit donc exister comme frère de `api/` au moment du `uv sync`. -------
echo "--- déballage ---"
mkdir -p "$REL/web" "$REL/api" "$REL/game"
tar -C "$REL/game" -xzf "game-$TS.tgz"
tar -C "$REL/api"  -xzf "api-$TS.tgz"
tar -C "$REL/web"  -xzf "web-$TS.tgz"
[ -f "$REL/api/pyproject.toml" ]  || { echo "⛔ api/pyproject.toml absent après déballage" >&2; exit 1; }
[ -f "$REL/game/pyproject.toml" ] || { echo "⛔ game/pyproject.toml absent après déballage" >&2; exit 1; }
# Sans ce server.js, l'unité web démarrerait sur un dossier vide et « tout irait bien ».
SERVERJS=$(cd "$REL/web" && find . -maxdepth 4 -name server.js | head -1)
[ -n "$SERVERJS" ] || { echo "⛔ server.js introuvable dans l'artefact web" >&2; exit 1; }
echo "server.js : $SERVERJS"
[ -d "$REL/web/apps/web/.next/static" ] || { echo "⛔ .next/static absent de l'artefact web" >&2; exit 1; }

# --- 3. Dépendances Python de l'API : un venv propre à la release --------------------------------
echo "--- uv sync (api) ---"
cd "$REL/api"
[ -x "$UV" ] || { echo "⛔ uv introuvable à $UV" >&2; exit 1; }
"$UV" sync --frozen --no-dev
for b in uvicorn alembic; do
  [ -x "$REL/api/.venv/bin/$b" ] || { echo "⛔ .venv/bin/$b absent après uv sync" >&2; exit 1; }
done

# --- 4. Migrations, tête affichée avant et après ------------------------------------------------
set -a
# shellcheck disable=SC1091
. "$RACINE/config/.env"
set +a
echo "--- tête Alembic AVANT ---"; "$REL/api/.venv/bin/alembic" current 2>&1 | tail -3
echo "--- alembic upgrade head ---"; "$REL/api/.venv/bin/alembic" upgrade head
echo "--- tête Alembic APRÈS ---";  "$REL/api/.venv/bin/alembic" current 2>&1 | tail -3

# --- 5. Carte d'identité : c'est elle qui prouvera plus tard ce qui est en ligne -----------------
PREV=$(readlink -f "$RACINE/app" 2>/dev/null || echo "")
cat > "$REL/RELEASE_INFO" <<INFO
commit=$COMMIT
branch=main
lot=$LOT
ts=$TS
prev=$PREV
INFO
echo "--- RELEASE_INFO ---"; cat "$REL/RELEASE_INFO"

echo "PREPARATION_OK"
