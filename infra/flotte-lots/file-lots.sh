#!/bin/bash
# pbm-file-lots — lancé par launchd toutes les 5 min sur devAI.
# Exécute AU PREMIER PLAN le prochain lot de la file (~/dev/pbm/file.txt, un nom de fichier prompt par ligne),
# un seul à la fois. Un lot terminé est retiré de la file et archivé dans ~/dev/pbm/file-faits.txt.
#
# Prompts reconnus : v7d-<id>.txt (vague V7D, plan daté), jeu-<id>.txt (backlog du jeu, depuis le 01/10),
# et tout autre nom (lot hors plan, sans suivi dans etat.json).
set -u
export PATH=/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin
# Deux files en parallèle depuis le 02/10/2026 : `a` (historique : file.txt, pbm-file.log) et `b`
# (file-b.txt, pbm-file-b.log), chacune avec son agent launchd. Chaque file ne regarde que SON lot
# (fichier pid), pas les `claude -p` des autres.
Q="${1:-a}"
D=$HOME/dev/pbm
case "$Q" in
  a) FILE="$D/file.txt";   TENT="$D/file-tentatives.txt";   LOG=$HOME/dev/logs/pbm-file.log ;;
  b) FILE="$D/file-b.txt"; TENT="$D/file-b-tentatives.txt"; LOG=$HOME/dev/logs/pbm-file-b.log ;;
  *) echo "file inconnue : $Q"; exit 1 ;;
esac
PIDF="$D/file-$Q.pid"
mkdir -p "$D" "$HOME/dev/logs"
exec >> "$LOG" 2>&1
note(){ echo "[$(date '+%F %T')] $*"; }
# L'agent B (chargé le 02/10) ne se redéclenche pas tout seul — 1 passage en 25 min, contre 2 597 pour A :
# chaque passage de A le relance (sans effet s'il tourne déjà). Un échec se voit dans le journal de A.
if [ "$Q" = a ]; then launchctl kickstart "gui/$(id -u)/ai.upgreg.pbm-file-b" >/dev/null 2>&1 || note "⚠ relance de la file B refusée par launchd"; fi
[ -s "$FILE" ] || exit 0
# Pause après une limite d'usage du compte Claude (voir plus bas) : 20 minutes, puis on réessaie.
if [ -f "$D/pause-$Q" ] && [ -n "$(find "$D/pause-$Q" -mmin -20)" ]; then exit 0; fi
rm -f "$D/pause-$Q"
# Un lot tourne déjà ? Seul le binaire compte (début de ligne ou après un « / ») : un simple
# `pgrep -f "claude -p"` reconnaissait aussi tout shell dont la commande MENTIONNE le texte — une
# surveillance par ssh a suffi, le 01/10, à suspendre la file en silence.
# Le lot de CETTE file tourne-t-il encore ? (les autres `claude -p` de devAI ne la bloquent plus)
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then exit 0; fi
rm -f "$PIDF"
P=$(head -1 "$FILE")
# Le clone ~/dev/pokeboy est partagé par les deux files : toute opération git y passe sous verrou.
VERROU="$D/.verrou-clone"
verrou(){ find "$VERROU" -maxdepth 0 -mmin +20 -exec rm -rf {} \; 2>/dev/null   # verrou orphelin (> 20 min)
          for _ in $(seq 1 90); do mkdir "$VERROU" 2>/dev/null && { echo $$ > "$VERROU/pid"; return 0; }; sleep 2; done
          note "⛔ verrou du clone tenu depuis plus de 3 min — tour sauté"; return 1; }
deverrou(){ [ "$(cat "$VERROU/pid" 2>/dev/null)" = "$$" ] && rm -rf "$VERROU"; return 0; }
trap deverrou EXIT
case "$P" in
  v7d-*.txt) ID="${P#v7d-}"; ID="${ID%.txt}" ;;
  jeu-*.txt) ID="${P#jeu-}"; ID="${ID%.txt}" ;;
  *)         ID="" ;;
esac
# main local aligné sur origin/main, ou rien ne part : le garde-fou et le marquage lisent ce clone.
verrou || exit 0
if ! (cd "$HOME/dev/pokeboy" && git fetch -q origin && git checkout -q main && git merge -q --ff-only origin/main); then
  deverrou
  note "⛔ ~/dev/pokeboy ne s'aligne pas sur origin/main (arbre sale ou divergent) — file SUSPENDUE avant $P"
  exit 0
fi
cd "$HOME/dev/pokeboy"
# Lot du jeu : le garde-fou d'ordre est rejoué AVANT de dépenser une session. Un amont absent de main
# (lot mort, fusion refusée, etat.json non marqué) ne se transforme ni en tentative brûlée ni en lot
# lancé sur une base fausse : la file s'arrête sur ce lot, et le journal le dit une fois par cause.
if [ "${P#jeu-}" != "$P" ]; then
  RAISON=$(python3 docs/roadmap/suivi.py verifier "$ID" 2>&1); RC=$?
  if [ "$RC" -ne 0 ]; then
    MARQ="$D/file-attente-$ID"
    if [ "$(cat "$MARQ" 2>/dev/null)" != "$RAISON" ]; then
      note "⛔ $ID ne part pas (verifier code $RC) — file SUSPENDUE sur ce lot : $(echo "$RAISON" | tr '\n' ' ')"
      echo "$RAISON" > "$MARQ"
    fi
    exit 0
  fi
  rm -f "$D/file-attente-$ID"
  # Le prompt est assemblé au départ, depuis le main du jour : un lot lancé dans trois jours lit le
  # plan et les décisions de ce jour-là, pas ceux du jour où on l'a mis dans la file.
  [ -f "prompts/$ID.md" ] || { note "⛔ prompts/$ID.md absent de main — $P retiré de la file"; sed -i '' '1d' "$FILE"; exit 0; }
  # L'en-tête dépend de la machine du couloir du lot (jeu.json) : devAI travaille sur place,
  # chimera est piloté depuis devAI (catalogue et calcul là-bas, jeton GitHub ici).
  MACH=$(python3 -c "import json,sys;j=json.load(open('docs/roadmap/jeu/jeu.json'));c={x['id']:x['machine'] for x in j['couloirs']};print(next(c[l['couloir']] for l in j['lots'] if l['id']==sys.argv[1]))" "$ID" 2>&1)
  case "$MACH" in
    devAI)   ENT=entete-jeu.md;         RAP=rappel-jeu.md ;;
    chimera) ENT=entete-jeu-chimera.md; RAP=rappel-jeu-chimera.md ;;
    *) note "⛔ $ID : machine du couloir introuvable (« $MACH ») — file SUSPENDUE avant $P"; exit 0 ;;
  esac
  if [ ! -f "$D/$ENT" ] || [ ! -f "$D/$RAP" ]; then
    note "⛔ $D/$ENT ou $RAP absent — file SUSPENDUE avant $P"; exit 0
  fi
  cat "$D/$ENT" "prompts/$ID.md" "$D/$RAP" | sed "s/<id>/$ID/g" > "$D/$P"
fi
[ -f "$D/$P" ] || { note "⛔ prompt introuvable : $P — retiré de la file"; sed -i '' '1d' "$FILE"; exit 0; }
N=$(grep -c "^$P$" "$TENT" 2>/dev/null | head -1); N=${N:-0}
# Déjà tenté et déjà fusionné ? (journal perdu, conclusion illisible) : on ne relance pas un lot fini.
if [ "$N" -ge 1 ] && git merge-base --is-ancestor "origin/roadmap/${ID:-${P%.txt}}" origin/main 2>/dev/null; then
  note "$P : roadmap/${ID:-${P%.txt}} déjà dans origin/main — compté terminé sans relance (à relire)"
  sed -i '' '1d' "$FILE"; echo "$P $(date +%FT%T%z) (fusion prouvée, sans relance)" >> "$D/file-faits.txt"; exit 0
fi
if [ "$N" -ge 2 ]; then note "⛔ $P a échoué deux fois — retiré de la file, intervention nécessaire"; sed -i '' '1d' "$FILE"; exit 0; fi
echo "$P" >> "$TENT"
note "lancement $P (tentative $((N+1)), file $Q)"
deverrou
# Pas de tâche de fond dans une session -p : elle quitterait en croyant être réveillée plus tard
# (morts du 01/10 22:54 et du 02/10 12:48). Les attentes se font au premier plan, par tranches ≤ 10 min.
CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p --dangerously-skip-permissions < "$D/$P" >> "$HOME/dev/logs/${P%.txt}.log" 2>&1 &
CPID=$!; echo "$CPID" > "$PIDF"
wait "$CPID"; rc=$?
rm -f "$PIDF"
# Limite d'usage du compte Claude : ce n'est PAS un échec du lot. Le 02/10 à 17:53, deux lots
# (j-initialisation, j-plateau-layout) ont brûlé leurs deux tentatives en 5 min sur « You've hit your
# weekly limit » et ont été retirés de la file ; la file B est restée bloquée cinq heures. On rend la
# tentative, on met la file en pause 20 min, et on le dit.
if [ "$rc" -ne 0 ] && tail -c 800 "$HOME/dev/logs/${P%.txt}.log" | grep -q -E "You've hit your|usage limit reached|Claude AI usage limit"; then
  n=$(grep -n -x "$P" "$TENT" | tail -1 | cut -d: -f1)
  [ -n "$n" ] && sed -i '' "${n}d" "$TENT"
  touch "$D/pause-$Q"
  note "⏸ $P : limite d'usage du compte Claude atteinte ($(tail -1 "$HOME/dev/logs/${P%.txt}.log" | cut -c1-80)) — tentative rendue, file $Q en pause 20 min"
  exit 0
fi
# Un lot est FINI s'il le DIT (ligne FAIT, gras markdown toléré) ou, à défaut, s'il le PROUVE
# (sa branche est un ancêtre de origin/main). Le 22/09, deux lots finis ont été pris pour des
# échecs : l'un avait conclu « **FAIT — …** », l'autre avait fusionné son travail dans main sans
# écrire de ligne de clôture. Les deux auraient été relancés pour 45 min de travail déjà fait —
# et un lot qui déploie, relancé, redéploie. On ne se fie donc pas au seul texte.
FINI=0
grep -qE "^[*]{0,2}FAIT — " "$HOME/dev/logs/${P%.txt}.log" 2>/dev/null && FINI=1
# Preuve par git, aussi pour un lot hors plan (branche roadmap/<nom du prompt>) : le 06/10, un nettoyage
# du disque de devAI a effacé ~/dev/logs pendant qu'un lot y écrivait — sa ligne FAIT ne pouvait plus
# être lue, et la file l'aurait relancé pour rien.
BR_ID="${ID:-${P%.txt}}"
if [ "$FINI" -eq 0 ]; then
  if (cd "$HOME/dev/pokeboy" && git fetch -q origin && git merge-base --is-ancestor "origin/roadmap/$BR_ID" origin/main) 2>/dev/null; then
    FINI=1
    note "⚠ $BR_ID : aucune ligne FAIT lisible, mais roadmap/$BR_ID EST dans origin/main — compté terminé (à relire)"
  fi
fi
if [ "$FINI" -eq 1 ]; then
  note "$P terminé (code $rc) — retiré de la file"
  sed -i '' '1d' "$FILE"; echo "$P $(date +%FT%T%z)" >> "$D/file-faits.txt"
  # Reconcilier docs/roadmap/etat.json avec main. L'ordonnanceur de chimera le faisait ; il est
  # arrêté depuis le 20/09. Or `suivi.py verifier` lit le STATUT, pas le code : un lot fusionné
  # mais resté `a_faire` fait refuser le démarrage de tout son aval (code 2, « ordre non tenu »).
  # Toute la vague V7D était bloquée ainsi le 22/09. On ne marque que SUR PREUVE : la branche du
  # lot est un ancêtre de origin/main. Les deux issues sont bruyantes — jamais de repli muet.
  if [ -n "$ID" ] && verrou; then
    (
      cd "$HOME/dev/pokeboy" || exit 1
      git fetch -q origin
      if ! git merge-base --is-ancestor "origin/roadmap/$ID" origin/main 2>/dev/null; then
        note "⚠ $ID a conclu mais roadmap/$ID n'est PAS dans origin/main — etat.json non touché, son aval restera bloqué : à regarder"
        exit 0
      fi
      [ -z "$(git status --porcelain --untracked-files=no)" ] || { note "⚠ $ID : clone ~/dev/pokeboy modifié à la main — etat.json non mis à jour, à regarder"; exit 0; }
      # Deux files + des lots qui fusionnent depuis chimera : main bouge souvent. Un commit de suivi
      # refusé ne se rebase pas (ROADMAP.html tient ses données sur une ligne : conflit certain) — on
      # repart de origin/main et on régénère, trois fois au plus.
      ok=0
      for essai in 1 2 3; do
        git fetch -q origin && git checkout -q main && git reset -q --hard origin/main || break
        python3 docs/roadmap/suivi.py statut "$ID" integre --motif "branche roadmap/$ID fusionnee dans main (verifie par git merge-base)" >/dev/null
        if git diff --quiet -- docs/roadmap/etat.json; then note "$ID : etat.json deja a jour"; ok=1; break; fi
        python3 docs/roadmap/suivi.py build >/dev/null || note "⚠ $ID : suivi.py build en échec — BACKLOG.md et ROADMAP.html non régénérés"
        git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/
        git commit -q -m "Suivi : $ID integre dans main"
        if git push -q origin main 2>/dev/null; then note "$ID marque integre dans etat.json (essai $essai)"; ok=1; break; fi
        sleep $((essai * 7))
      done
      if [ "$ok" != 1 ]; then
        git reset -q --hard origin/main
        note "⚠ $ID : push de etat.json refusé trois fois — NON marqué, son aval reste bloqué : à regarder"
      fi
      # Le graphe suit main (CLAUDE.md) : un graphe en retard envoie le lot suivant sur du code disparu.
      graphify update . >/dev/null 2>&1 || note "⚠ $ID : graphify update a échoué — graphe de ~/dev/pokeboy en retard sur main"
    )
    deverrou
  fi
else
  note "⚠ $P s'est arrêté sans conclusion (code $rc) — il sera relancé au prochain tour"
fi
