#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$(cd "$PKG_DIR/../../apps/api" && pwd)"

uv run --project "$API_DIR" python "$SCRIPT_DIR/export_openapi.py" > "$PKG_DIR/openapi.json"
"$PKG_DIR/node_modules/.bin/openapi-typescript" "$PKG_DIR/openapi.json" -o "$PKG_DIR/src/schema.d.ts"
