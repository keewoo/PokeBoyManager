#!/bin/bash
# pbm-deploy-runner — lancé par launchd toutes les 5 min. Il exécute le déploiement AU PREMIER PLAN :
# c'est ce qui l'empêche d'être tué (launchd tue les enfants d'un script qui se termine).
set -u
export PATH=/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin
D=$HOME/dev/pbm; LOG=$HOME/dev/logs/pbm-deploy.log
mkdir -p "$D" "$HOME/dev/logs"
[ -f "$D/deploy.flag" ] || exit 0
[ -f "$D/deploy.done" ] && exit 0
N=$(cat "$D/deploy.launched" 2>/dev/null || echo 0)
[ "$N" -ge 2 ] && exit 0
echo $((N+1)) > "$D/deploy.launched"
{ echo; echo "=== déploiement lancé $(date -Is) (tentative $((N+1)))"; } >> "$LOG"
cd "$HOME/dev/pokeboy" || exit 1
git fetch -q origin && git checkout -q main && git merge -q --ff-only origin/main
CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p --dangerously-skip-permissions < "$D/pbm-deploy-prompt.txt" >> "$LOG" 2>&1
rc=$?
echo "=== fin du déploiement $(date -Is), code de sortie $rc" >> "$LOG"
grep -q 'FAIT — pbm-deploy' "$LOG" && touch "$D/deploy.done"
