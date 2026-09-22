#!/usr/bin/env bash
# ouvrir-pr.sh — ouvre la PR d'un lot, ou ECHOUE en disant pourquoi.
#
# Il n'y a volontairement aucun repli silencieux : une branche sans PR n'a pas de CI,
# et c'est la CI qui fait foi. Deux lots du 22/09 ont ecrit « gh absent » dans leur
# compte rendu puis se sont declares finis — alors que `gh` etait installe et que
# seul le PATH manquait. Un manque doit couter quelque chose, pas passer inapercu.
#
# usage : bash scripts/ouvrir-pr.sh <branche>
set -uo pipefail

BR="${1:?usage: ouvrir-pr.sh <branche>}"
REPO="${PBM_REPO:-keewoo/PokeBoyManager}"

[ -r "$HOME/.kailo-tokens" ] && . "$HOME/.kailo-tokens"
export GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

if ! command -v gh > /dev/null 2>&1; then
  echo "/!\\ gh introuvable. PATH=$PATH"
  echo "    Sur devAI il vit dans /opt/homebrew/bin — si ce repertoire manque du PATH,"
  echo "    c'est le ~/.zshenv qu'il faut corriger, pas ce script."
  exit 3
fi

N=$(gh pr list --repo "$REPO" --head "$BR" --json number --jq ".[0].number" 2> /dev/null)
if [ -n "${N:-}" ] && [ "$N" != "null" ]; then
  echo "PR deja ouverte : #$N"
  gh pr view "$N" --repo "$REPO" --json url --jq .url
  exit 0
fi

git fetch -q origin 2> /dev/null
if git merge-base --is-ancestor "origin/$BR" origin/main 2> /dev/null; then
  echo "Branche deja fusionnee dans main : pas de PR a ouvrir."
  echo "Verifie que la CI est verte sur le commit de main — c'est elle qui fait foi."
  exit 0
fi

# `--fill` lit la branche LOCALE : appele depuis un autre worktree, il echoue avant
# meme d'avoir joint GitHub, et son message masque alors la vraie cause. On ne lui
# confie le titre que si la branche est bien la ; sinon on le tire du dernier commit.
if git show-ref --verify --quiet "refs/heads/$BR"; then
  set -- --fill
else
  TITRE=$(git log -1 --format=%s "origin/$BR" 2> /dev/null)
  [ -n "$TITRE" ] || { echo "/!\\ branche introuvable, ni locale ni sur origin : $BR"; exit 3; }
  CORPS=$(git log -1 --format=%b "origin/$BR" 2> /dev/null)
  set -- --title "$TITRE" --body "${CORPS:-Ouverte par scripts/ouvrir-pr.sh}"
fi

SORTIE=$(gh pr create --repo "$REPO" --base main --head "$BR" "$@" 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
  echo "$SORTIE"
  exit 0
fi

echo "/!\\ ouverture de PR refusee : $SORTIE"
case "$SORTIE" in
  *"not accessible by personal access token"*|*"Resource not accessible"*)
    echo "    CAUSE : le jeton GitHub n'a pas la permission « Pull requests: write »."
    echo "    Il lit et il pousse, il n'ouvre pas de PR. Correction cote GitHub (JF)." ;;
  *"Bad credentials"*|*"HTTP 401"*|*"authentication"*)
    echo "    CAUSE : jeton GitHub invalide ou expire (gh auth status, ~/.kailo-tokens)." ;;
esac
echo "    NE CONCLUS PAS SANS LE DIRE : passe le lot en « bloque », ou nomme ce manque"
echo "    dans ton compte rendu ET dans ton dernier message. Sans PR, pas de CI."
exit 4
