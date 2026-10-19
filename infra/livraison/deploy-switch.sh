#!/bin/bash
# deploy-switch.sh — BASCULE de PokeBoyManager sur `kailo-srv`, avec retour arrière automatique.
#
# Versionné pour la même raison que `prep-lol.sh` : son prédécesseur vivait dans `/tmp` et a été
# purgé. Voir l'en-tête de `prep-lol.sh`.
#
# C'est le SEUL geste irréversible de la chaîne : il fait pointer `app/` sur la release préparée et
# redémarre les trois unités. Si la santé ne revient pas, il REMET l'ancienne release et le dit —
# il ne laisse jamais la production sur une version qui ne répond pas.
#
# Ce qu'il ne fait pas, volontairement : vérifier les sites voisins (kailo.life, ACX). Ils sont
# servis par le Caddy de l'hôte et ne dépendent pas de pokeboy ; c'est à la livraison de les
# mesurer avant et après, depuis l'extérieur (docs/LIVRAISON.md).
#
# Usage :  deploy-switch.sh <TS>   |   TS=… deploy-switch.sh
# Dernière ligne « BASCULE_OK » = en ligne et sain. « BASCULE_ANNULEE » = retour arrière effectué.
set -euo pipefail

TS="${1:-${TS:-}}"
RACINE=/srv/pokeboy/prod
UNITES=(pokeboy-prod-api pokeboy-prod-worker pokeboy-prod-web)
SANTE_API=http://127.0.0.1:8100/health   # l'API est montée à la racine : Caddy retire le //api/ (handle_path)
SANTE_WEB=http://127.0.0.1:3100/
PATIENCE=24                               # 24 essais × 2,5 s ≈ 60 s pour que les 3 unités reviennent

[ -n "$TS" ] || { echo "⛔ TS manquant — usage : deploy-switch.sh <TS>" >&2; exit 2; }
REL="$RACINE/releases/$TS"

# --- 0. La release est-elle réellement prête ? ---------------------------------------------------
[ -f "$REL/RELEASE_INFO" ]        || { echo "⛔ $REL/RELEASE_INFO absent — release non préparée" >&2; exit 2; }
[ -x "$REL/api/.venv/bin/uvicorn" ] || { echo "⛔ venv de l'API absent — release non préparée" >&2; exit 2; }
[ -f "$REL/web/apps/web/server.js" ] || { echo "⛔ web/apps/web/server.js absent — release non préparée" >&2; exit 2; }

ANCIEN=$(readlink -f "$RACINE/app" 2>/dev/null || echo "")
NOUVEAU=$(readlink -f "$REL")
[ -n "$ANCIEN" ] || { echo "⛔ app/ ne pointe sur rien — état inattendu, on n'y touche pas" >&2; exit 3; }
if [ "$ANCIEN" = "$NOUVEAU" ]; then echo "⛔ $TS est DÉJÀ en service — rien à basculer" >&2; exit 0; fi

echo "=== BASCULE $TS ==="
echo "ancien : $ANCIEN"
echo "nouveau : $NOUVEAU"

sante() { curl -fsS -o /dev/null --max-time 8 "$SANTE_API" && curl -fsS -o /dev/null --max-time 8 "$SANTE_WEB"; }

echo "--- santé AVANT bascule ---"
if sante; then echo "api+web : sains"; else echo "⚠ la production n'était DÉJÀ pas saine avant la bascule"; fi

bascule_vers() {  # $1 = chemin de release ; lien remplacé d'un seul coup (-T, sinon on écrit DEDANS)
  sudo -n -u pokeboy ln -sfnT "$1" "$RACINE/app"
  sudo -n systemctl restart "${UNITES[@]}"
}

echo "--- bascule du lien et redémarrage des trois unités ---"
bascule_vers "$NOUVEAU"

echo "--- attente du retour de la santé (≤ 60 s) ---"
OK=0
for i in $(seq 1 "$PATIENCE"); do
  if sante; then OK=1; echo "santé revenue au bout de $i essai(s)"; break; fi
  sleep 2.5
done

if [ "$OK" -ne 1 ]; then
  echo "⛔ la santé n'est pas revenue après ~60 s — RETOUR ARRIÈRE vers $ANCIEN" >&2
  bascule_vers "$ANCIEN"
  for i in $(seq 1 "$PATIENCE"); do
    if sante; then
      echo "retour arrière effectué et sain (essai $i) ; app/ -> $(readlink -f "$RACINE/app")" >&2
      echo "BASCULE_ANNULEE"; exit 4
    fi
    sleep 2.5
  done
  # Le pire des cas : ni la nouvelle ni l'ancienne ne répondent. On le hurle, on ne le cache pas.
  echo "⛔⛔ RETOUR ARRIÈRE FAIT MAIS LA SANTÉ NE REVIENT PAS — intervention humaine requise" >&2
  echo "    app/ -> $(readlink -f "$RACINE/app")" >&2
  systemctl is-active "${UNITES[@]}" >&2 || true
  echo "BASCULE_ANNULEE_ET_MALADE"; exit 5
fi

echo "--- état des unités ---"; systemctl is-active "${UNITES[@]}"
echo "--- release en service ---"; readlink -f "$RACINE/app"; cat "$RACINE/app/RELEASE_INFO"
echo "BASCULE_OK"
