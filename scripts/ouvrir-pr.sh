#!/usr/bin/env bash
# ouvrir-pr.sh — ouvre la PR d'un lot, ou ECHOUE en disant pourquoi.
#
# Aucun repli silencieux : sans PR, le workflow ne tourne pas sur ton travail
# (il se declenche sur `pull_request` et sur `push: [main]`), et c'est la CI qui
# fait foi. Le 22/09, trois lots ont conclu « outil absent » et se sont declares
# finis sans CI — alors que `gh` etait installe et que seul le PATH manquait.
#
# Ne depend PAS de `gh` : il est absent de la WSL de chimera. Avec un jeton, il
# passe par l'API REST (curl + python3, presents partout).
#
# usage : bash scripts/ouvrir-pr.sh <branche>
# codes : 0 ouverte / deja ouverte / deja fusionnee
#         3 branche introuvable   4 refus de GitHub   5 pas de jeton ici
set -uo pipefail

BR="${1:?usage: ouvrir-pr.sh <branche>}"
REPO="${PBM_REPO:-keewoo/PokeBoyManager}"

[ -r "$HOME/.kailo-tokens" ] && . "$HOME/.kailo-tokens"
JETON="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

# Le remote GitHub ne s'appelle pas pareil partout : `origin` sur devAI, `github`
# sur chimera (dont `origin` est un depot relais local, qui retarde).
DIST=""
for R in $(git remote 2> /dev/null); do
  case "$(git remote get-url "$R" 2> /dev/null)" in *github.com*|*github-pokeboy*) DIST="$R"; break;; esac
done
[ -n "$DIST" ] || { echo "/!\\ aucun remote GitHub dans ce depot"; exit 3; }
git fetch -q "$DIST" 2> /dev/null

git rev-parse --verify -q "$DIST/$BR" > /dev/null \
  || { echo "/!\\ branche absente de $DIST : $BR — pousse-la d'abord"; exit 3; }

if git merge-base --is-ancestor "$DIST/$BR" "$DIST/main" 2> /dev/null; then
  echo "Branche deja fusionnee dans main : pas de PR a ouvrir."
  echo "Verifie que la CI est verte sur le commit de main — c'est elle qui fait foi."
  exit 0
fi

if [ -z "$JETON" ]; then
  echo "/!\\ aucun jeton GitHub sur cette machine ($(hostname -s))."
  echo "    C'est normal sur une machine de CONSTRUCTION : elle pousse par cle de depot,"
  echo "    et une cle de depot n'ouvre pas de PR. La PR s'ouvre depuis devAI :"
  echo "        ssh devai 'cd ~/dev/pokeboy && bash scripts/ouvrir-pr.sh $BR'"
  echo "    NE CONCLUS PAS SANS LE DIRE : nomme ce reste dans ton compte rendu."
  exit 5
fi

api() { curl -s -w '\n%{http_code}' -H "Authorization: Bearer $JETON" \
        -H "Accept: application/vnd.github+json" "$@"; }

REP=$(api "https://api.github.com/repos/$REPO/pulls?state=open&head=${REPO%%/*}:$BR")
if [ "$(printf '%s' "$REP" | tail -1)" = "200" ]; then
  URL=$(printf '%s' "$REP" | sed '$d' | python3 -c \
    'import sys,json;d=json.load(sys.stdin);print(d[0]["html_url"] if d else "")' 2> /dev/null)
  [ -n "$URL" ] && { echo "PR deja ouverte : $URL"; exit 0; }
fi

TITRE=$(git log -1 --format=%s "$DIST/$BR")
CORPS=$(git log -1 --format=%b "$DIST/$BR")
# Les variables passent a python3 par l'environnement : un titre ou un corps de
# commit peut contenir guillemets, apostrophes ou sauts de ligne, et json.dumps est
# le seul echappement en qui on ait confiance.
CHARGE=$(BR="$BR" TITRE="$TITRE" CORPS="$CORPS" python3 -c '
import os, json
print(json.dumps({"title": os.environ["TITRE"].strip() or "PR du lot",
                  "head": os.environ["BR"], "base": "main",
                  "body": os.environ.get("CORPS", "").strip() or "Ouverte par scripts/ouvrir-pr.sh"}))')
REP=$(printf '%s' "$CHARGE" | api -X POST -d @- "https://api.github.com/repos/$REPO/pulls")

CODE=$(printf '%s' "$REP" | tail -1)
CORPS_REP=$(printf '%s' "$REP" | sed '$d')
if [ "$CODE" = "201" ]; then
  printf '%s' "$CORPS_REP" | python3 -c 'import sys,json;print("PR ouverte :",json.load(sys.stdin)["html_url"])'
  exit 0
fi

MSG=$(printf '%s' "$CORPS_REP" | python3 -c \
  'import sys,json
d=json.load(sys.stdin)
print(d.get("message",""), *[e.get("message","") for e in d.get("errors",[])])' 2> /dev/null)
echo "/!\\ ouverture de PR refusee (HTTP $CODE) : $MSG"
case "$CODE:$MSG" in
  403:*"not accessible by personal access token"*|403:*)
    echo "    CAUSE : le jeton GitHub n'a pas la permission « Pull requests: write »."
    echo "    Il lit et il pousse, il n'ouvre pas de PR. Correction cote GitHub (JF)." ;;
  401:*) echo "    CAUSE : jeton GitHub invalide ou expire." ;;
esac
echo "    NE CONCLUS PAS SANS LE DIRE : passe le lot en « bloque », ou nomme ce manque"
echo "    dans ton compte rendu ET dans ton dernier message. Sans PR, pas de CI."
exit 4
