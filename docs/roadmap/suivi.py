#!/usr/bin/env python3
"""Suivi de la roadmap PokeBoyManager.

Le plan (`roadmap.json`) est la seule source ; l'état réel vit dans `etat.json`.
Tout le reste est GÉNÉRÉ : prompts/<id>.md, BACKLOG.md, docs/roadmap/ROADMAP.html.

    python3 docs/roadmap/suivi.py build                    # valide le plan, régénère tout
    python3 docs/roadmap/suivi.py verifier <id>            # garde-fou d'ordre (code 2 = ordre non tenu)
    python3 docs/roadmap/suivi.py demarrer <id> --machine chimera --branche roadmap/<id>
    python3 docs/roadmap/suivi.py tache <id> <tache> <fait|en_cours|na|bloque> "<preuve>"
    python3 docs/roadmap/suivi.py statut <id> <statut> [--motif "…"]
    python3 docs/roadmap/suivi.py compte-rendu <id> --resume "…" [--livrable …] [--preuve …] [--ecart …] [--reste …]
    python3 docs/roadmap/suivi.py decision <Dn> "<texte exact de JF>"

Codes de sortie : 0 ok, 1 erreur d'outillage ou plan incohérent, 2 ordre non tenu.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent
PLAN = ICI / "roadmap.json"
ETAT = ICI / "etat.json"
GABARIT = ICI / "template.html"
SORTIE_HTML = ICI / "ROADMAP.html"
PROMPTS = RACINE / "prompts"
BACKLOG = RACINE / "BACKLOG.md"
ARTEFACT = "https://claude.ai/artifact/2w2cvcLhUGZdorHNVvTahy"
PLAN_JEU = ICI / "jeu" / "jeu.json"   # backlog du jeu, plan sans dates (build-jeu.py)

# Un lot est ACQUIS pour l'aval dès qu'il est intégré dans main : le garde-fou d'ordre et le
# contrôle de cohérence du plan doivent lire la MÊME liste, sinon ils divergent — c'est arrivé
# (35 lots en « integre » que `verifier` refusait alors que `fini` les acceptait).
ACQUIS = ("integre", "livre", "livre_uat", "attente_go_prod")

MACHINES = {
    "devAI": {
        "hote": "devai",
        "depot": "~/dev/pokeboy",
        "ssh": "ssh devai '{cmd}'",
        "hostname": "Mac-mini-de-keewoo (hostname -s)",
        "lot": "`ssh devai 'cd ~/dev/wt-{id} && nohup claude -p --dangerously-skip-permissions < prompts/{id}.md > ~/dev/logs/{id}.log 2>&1 &'` (toutes les sorties redirigées : ssh rend la main).",
    },
    "chimera": {
        "hote": "chimera",
        "depot": "~/dev/pokeboy (WSL Ubuntu-24.04, utilisateur upgreg)",
        "ssh": "ssh chimera 'wsl -d Ubuntu-24.04 -u upgreg -- bash -lc \"{cmd}\"'",
        "hostname": "Chimaera (dans la WSL)",
        "lot": "par le mécanisme de lots de chimera (`~/dev/lots/launch-lot.sh`, étendu au dépôt `~/dev/pokeboy` par le lot `v0-flotte`), **lancé côté Windows** — un `nohup` interne à la WSL meurt avec la session. Journal : `~/dev/logs/{id}.log`.",
    },
}


def maintenant() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M%z")


def charger() -> tuple[dict, dict]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    etat = json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {"etats": {}, "decisions_prises": {}}
    for it in plan["items"]:
        e = etat["etats"].setdefault(it["id"], {"statut": "a_faire", "machine": None, "branche": None,
                                                 "debut_reel": None, "fin_reelle": None, "taches": {},
                                                 "journal": [], "compte_rendu": {}})
        for t in plan["taches"]:
            if t["id"] not in e["taches"]:
                na = it.get("taches_na", {}).get(t["id"])
                e["taches"][t["id"]] = {"etat": "na", "preuve": f"sans objet : {na}", "maj": None} if na \
                    else {"etat": "a_faire", "preuve": "", "maj": None}
    return plan, etat


def sauver(etat: dict) -> None:
    ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def valider(plan: dict, etat: dict | None = None) -> list[str]:
    """Refuse un plan incohérent : dépendance inconnue ou mal datée, couloir en double, décision orpheline.

    Les lots DÉJÀ LIVRÉS ne sont plus contrôlés sur les dates : la réalité a eu lieu (plusieurs lots
    le même jour, dans le même couloir), et on ne réécrit pas l'histoire pour satisfaire le plan.
    """
    err, par_id = [], {i["id"]: i for i in plan["items"]}
    etats = (etat or {}).get("etats", {})
    fini = lambda x: etats.get(x, {}).get("statut") in ACQUIS
    couloirs = {c["id"] for c in plan["meta"]["couloirs"]}
    decisions = {d["id"]: d for d in plan["decisions"]}
    for i in plan["items"]:
        if fini(i["id"]):
            continue
        if i["couloir"] not in couloirs:
            err.append(f"{i['id']} : couloir inconnu {i['couloir']}")
        if i["debut"] > i["fin"]:
            err.append(f"{i['id']} : début après la fin")
        for d in i["dependances"]:
            if d not in par_id:
                err.append(f"{i['id']} : dépendance inconnue {d}")
            elif not fini(d) and par_id[d]["fin"] >= i["debut"]:
                err.append(f"{i['id']} commence le {i['debut']} mais {d} finit le {par_id[d]['fin']}")
        if i["decision"]:
            if i["decision"] not in decisions:
                err.append(f"{i['id']} : décision inconnue {i['decision']}")
            elif decisions[i["decision"]]["date"] > i["debut"]:
                err.append(f"{i['id']} commence avant sa décision {i['decision']}")
    for c in couloirs:
        its = sorted((i for i in plan["items"] if i["couloir"] == c and not fini(i["id"])), key=lambda x: x["debut"])
        for a, b in zip(its, its[1:]):
            if b["debut"] <= a["fin"]:
                err.append(f"couloir {c} : {a['id']} et {b['id']} se chevauchent")
    for d in plan["decisions"]:
        for u in d["debloque"]:
            if u not in par_id:
                err.append(f"{d['id']} débloque un chantier inconnu {u}")
    return err


# ---------------------------------------------------------------- prompts
def fr_date(s: str) -> str:
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    d = dt.date.fromisoformat(s)
    return f"{d.day} {mois[d.month - 1]}"


def prompt(plan: dict, it: dict) -> str:
    par_id = {i["id"]: i for i in plan["items"]}
    coul = {c["id"]: c for c in plan["meta"]["couloirs"]}[it["couloir"]]
    piste = {p["id"]: p["nom"] for p in plan["pistes"]}[it["piste"]]
    j1 = plan["meta"]["jalons"][0]
    jalon = j1["nom"] if it["fin"] <= j1["date"] else plan["meta"]["jalons"][1]["nom"]
    dec = {d["id"]: d for d in plan["decisions"]}.get(it["decision"] or "")
    m = MACHINES.get(coul["machine"])
    i_id = it["id"]
    L = []
    L += [f"# Lot `{i_id}` — {it['titre']}", "",
          "> Prompt GÉNÉRÉ depuis `docs/roadmap/roadmap.json` par `docs/roadmap/suivi.py build` — ne pas éditer à la main.",
          "> Suivi : `docs/roadmap/ROADMAP.html` (onglets Roadmap et Maquette) · processus : `docs/roadmap/PROCESSUS.md`.", "",
          f"**{it['priorite']}** · piste {piste} · couloir **{it['couloir']}** — {coul['nom']} (**{coul['machine']}**) · "
          f"prévu du {fr_date(it['debut'])} au {fr_date(it['fin'])} · jalon **{jalon}** · taille {it['taille']} · "
          f"complexité {it['complexite']}/5 · difficulté {it['difficulte']}/5", ""]

    if m:
        prep = f"cd ~/dev/pokeboy && git fetch -q origin && git worktree add ../wt-{i_id} -b roadmap/{i_id} origin/main && mkdir -p ~/dev/logs"
        L += ["## A. Où tourne cette session ? — à trancher AVANT tout le reste", "",
              f"Ce lot **s'exécute sur {coul['machine']}**. Lance `hostname -s` :", "",
              f"- **{m['hostname']}** → **mode EXÉCUTANT** : passe à la section 0.",
              "- **Toute autre machine** (le Mac de JF `M-DRHKN6GJ77` notamment) → **mode PILOTE** : tu ne codes rien ici. Section P uniquement.", "",
              "## P. Mode PILOTE", "",
              f"1. Garde-fou : `python3 docs/roadmap/suivi.py verifier {i_id}`. Code 2 → présente les raisons à JF et demande-lui quoi faire ; ne passe jamais outre sans son « oui » explicite.",
              f"2. Prépare le worktree sur {coul['machine']} :", "",
              "```bash", m["ssh"].format(cmd=prep), "```", "",
              f"3. Lance le lot autonome : {m['lot'].format(id=i_id)}",
              f"4. **3 minutes plus tard**, lis le journal du lot. Journal vide et processus mort = lot mort au démarrage : relance UNE fois, puis arrête-toi et alerte JF avec la cause. Un lot silencieux n'est jamais une conclusion.",
              f"5. À la fin : `git fetch` et lis le compte rendu du lot dans `docs/roadmap/etat.json` de la branche `roadmap/{i_id}` ; résume à JF : statut, grille, preuves, décisions attendues.", "",
              "---", ""]
    else:
        L += ["## A. Qui fait ce lot ?", "", "Ce lot est un **geste de JF** (console, décision, compte externe). Une session Claude l'accompagne : elle prépare, vérifie et consigne ; elle ne fait pas le geste à sa place.", ""]

    L += ["> ⛔ **RÈGLE DE CLÔTURE — QUELLE QUE SOIT L'ISSUE.** Livré, partiel, bloqué, erreur, contexte qui s'épuise : avant ton dernier message, fais la section 7 (état + compte rendu + build). Un lot qui s'arrête sans compte rendu est une PANNE.", "",
          "## 0. Garde-fou d'ordre — avant toute ligne de code", "",
          f"Dépôt : `{m['depot'] if m else '—'}`. Travaille dans ton **worktree** `../wt-{i_id}`, branche `roadmap/{i_id}` depuis `origin/main` — jamais dans l'arbre commun, jamais `git stash`, jamais `git add -A`.", "",
          "```bash",
          f"python3 docs/roadmap/suivi.py verifier {i_id}",
          f"python3 docs/roadmap/suivi.py demarrer {i_id} --machine \"$(hostname -s)\" --branche roadmap/{i_id}",
          "```", "",
          "- **Code 0** → continuer.",
          f"- **Code 2 — ordre non tenu** (dépendance non livrée, décision non prise) → ne rien coder. Session interactive : demande à JF. Lot autonome : `suivi.py statut {i_id} attente_validation --motif \"<raisons>\"`, section 7, dernier message `ATTENTE VALIDATION — {i_id} — <raisons>`.",
          "- Tu n'accordes **jamais** toi-même une dérogation.", ""]

    L += ["## 1. Cadre — relire avant d'agir", "",
          "| Document | Pourquoi |", "|---|---|",
          "| `CLAUDE.md` | règles du dépôt, commandes, conventions |",
          "| `docs/ARCHITECTURE.md` | stack, données, coffre de clés, reconnaissance |",
          "| `docs/roadmap/PROCESSUS.md` | suivi, garde-fou, clôture |",
          "| `docs/roadmap/ROADMAP.html` — onglet **Maquette** | l'écran à reproduire (front) |",
          "| `BACKLOG.md` | l'état des autres lots |",
          "| `~/.claude/CLAUDE.md` de la machine | règles de la flotte (construire ≠ servir, Python 3.12, WSL) |", "",
          "Le cadre l'emporte sur ce prompt : en cas de contradiction, passe en `attente_validation` avec la contradiction en motif.", ""]

    deps = "\n".join(f"- `{d}` — {par_id[d]['titre']}" for d in it["dependances"]) or "- aucune"
    L += ["## 2. Contexte", "",
          f"**Gain.** {it['gain']}", "",
          f"**Fonctionnalités.** {it['fonctionnalites']}", "",
          f"**Tenants — ce qu'il faut avant.** {it['tenants']}", "",
          f"**Aboutissants — ce que ça ouvre.** {it['aboutissants']}", "",
          "**Dépend de :**", deps, ""]
    if dec:
        L += [f"**Décision {dec['id']}** (avant le {fr_date(dec['date'])}) : {dec['quoi']} — lis la décision prise dans `etat.json` (`decisions_prises`) et applique-la à la lettre.", ""]

    L += ["## 3. Mission", ""] + [f"{n}. {x}" for n, x in enumerate(it["mission"], 1)] + [""]
    L += ["## 4. Risques & pièges", "", it["risques"], ""]
    L += ["## 5. Livrables — définition de « fini »", ""] + [f"- {x}" for x in it["livrables"]] + [
          "- CI GitHub Actions verte sur la PR (elle fait foi, pas une suite verte sur une machine).",
          "- Aucun secret dans le dépôt, les journaux ou les sorties.", ""]
    L += ["## 6. Tests exigés", "",
          "- Un test qui **échoue sans** ton changement et passe avec.",
          "- Route utilisateur → test d'accès croisé (l'utilisateur B reçoit 404 sur les objets de A).",
          "- Front → conformité à l'écran de la maquette (capture jointe au compte rendu).",
          "- Suites complètes lancées sur la flotte (`fleet-run` depuis le Mac, ou directement sur la machine), jamais sur le Mac de JF.", ""]
    taches = "\n".join(f"- `{t['id']}` — {t['lib']}" + (f" (sans objet : {it['taches_na'][t['id']]})" if t["id"] in it.get("taches_na", {}) else "")
                       for t in plan["taches"])
    L += ["## 7. Clôture — obligatoire", "",
          "Grille de tâches du lot :", taches, "",
          "```bash",
          f"python3 docs/roadmap/suivi.py tache {i_id} <tache> fait \"<preuve : commit, test, URL, capture>\"",
          f"python3 docs/roadmap/suivi.py compte-rendu {i_id} --resume \"…\" --livrable \"…\" --preuve \"…\" --ecart \"…\" --reste \"…\"",
          f"python3 docs/roadmap/suivi.py statut {i_id} <livre_uat|attente_go_prod|livre|bloque>",
          "python3 docs/roadmap/suivi.py build",
          f"git add docs/roadmap/etat.json docs/roadmap/ROADMAP.html BACKLOG.md prompts/ <tes fichiers>   # jamais git add -A",
          f"git commit -m \"{i_id}: …\" && git push -u origin roadmap/{i_id} && gh pr create --fill",
          "```", "",
          f"Puis republie la page : lis l'artefact {ARTEFACT} (action `read`) et publie `docs/roadmap/ROADMAP.html` avec ce même `url`.", "",
          f"Dernier message : statut, grille, preuves, écarts au plan, ce qui attend JF.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- backlog
def backlog(plan: dict, etat: dict) -> str:
    st = plan["statuts"]
    coul = {c["id"]: c for c in plan["meta"]["couloirs"]}
    L = ["# BACKLOG — PokeBoyManager", "",
         "> GÉNÉRÉ par `docs/roadmap/suivi.py build` depuis `docs/roadmap/roadmap.json` et `etat.json`. Ne pas éditer à la main.",
         "> Vue complète (calendrier, fiches, prompts, maquette) : `docs/roadmap/ROADMAP.html`.", "",
         f"**Objectif.** {plan['meta']['objectif']}", ""]
    for j in plan["meta"]["jalons"]:
        L.append(f"- **{j['date']} — {j['nom']}** : {j['quoi']}")
    L.append("")
    for v in plan["vagues"]:
        its = [i for i in plan["items"] if i["vague"] == v["id"]]
        L += [f"## {v['id']} — {v['nom']} ({fr_date(v['debut'])} → {fr_date(v['fin'])})", "", f"_{v['these']}_", "",
              "| Lot | Prio | Titre | Couloir | Prévu | Dépend de | Décision | Statut | Prompt |",
              "|---|---|---|---|---|---|---|---|---|"]
        for i in sorted(its, key=lambda x: x["debut"]):
            L.append(f"| `{i['id']}` | {i['priorite']} | {i['titre']} | {i['couloir']} ({coul[i['couloir']]['machine']}) | "
                     f"{fr_date(i['debut'])} → {fr_date(i['fin'])} | {', '.join(i['dependances']) or '—'} | {i['decision'] or '—'} | "
                     f"{st[etat['etats'][i['id']]['statut']]} | [prompt](prompts/{i['id']}.md) |")
        L.append("")
    L += ["## Décisions de JF", "", "| # | Avant le | Décision | Prise | Débloque |", "|---|---|---|---|---|"]
    for d in plan["decisions"]:
        p = etat["decisions_prises"].get(d["id"])
        L.append(f"| {d['id']} | {d['date']} | {d['quoi']} | {p['prise'] if p else 'en attente'} | {', '.join(d['debloque'])} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- commandes
def build(_a=None) -> int:
    plan, etat = charger()
    err = valider(plan, etat)
    if err:
        print("PLAN INCOHÉRENT — rien n'est généré :", *err, sep="\n  - ")
        return 1
    PROMPTS.mkdir(exist_ok=True)
    prompts = {}
    for it in plan["items"]:
        prompts[it["id"]] = prompt(plan, it)
        (PROMPTS / f"{it['id']}.md").write_text(prompts[it["id"]] + "\n", encoding="utf-8")
    BACKLOG.write_text(backlog(plan, etat), encoding="utf-8")
    # Backlog du jeu : plan séparé, sans dates, généré par docs/roadmap/jeu/build-jeu.py.
    # Son absence ne bloque pas la génération, mais elle se DIT ici et dans l'onglet — un
    # onglet vide sans explication est exactement le genre de panne muette qu'on ne remarque pas.
    jeu = None
    if PLAN_JEU.exists():
        jeu = json.loads(PLAN_JEU.read_text(encoding="utf-8"))
    else:
        print(f"ATTENTION — {PLAN_JEU.relative_to(RACINE)} absent : l'onglet « Backlog du jeu » "
              f"sera vide. Lancer d'abord : python3 docs/roadmap/jeu/build-jeu.py")
    data = dict(plan, etats=etat["etats"], decisions_prises=etat["decisions_prises"], prompts=prompts,
                jeu=jeu, artefact=ARTEFACT, genere=maintenant())
    html = GABARIT.read_text(encoding="utf-8").replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    SORTIE_HTML.write_text(html, encoding="utf-8")
    sauver(etat)
    jeu_txt = f", {len(jeu['lots'])} lots de jeu" if jeu else ", backlog du jeu ABSENT"
    print(f"ok — {len(plan['items'])} lots, {len(prompts)} prompts{jeu_txt}, BACKLOG.md et ROADMAP.html régénérés")
    return 0


def verifier(a) -> int:
    plan, etat = charger()
    it = next((i for i in plan["items"] if i["id"] == a.id), None)
    if not it:
        print(f"lot inconnu : {a.id}")
        return 1
    raisons = [f"dépendance {d} non livrée ({etat['etats'][d]['statut']})" for d in it["dependances"]
               if etat["etats"][d]["statut"] not in ACQUIS]
    if it["decision"] and it["decision"] not in etat["decisions_prises"]:
        raisons.append(f"décision {it['decision']} non prise")
    if etat["etats"][a.id].get("derogation"):
        raisons = []
    if raisons:
        print("ORDRE NON TENU :", *raisons, sep="\n  - ")
        return 2
    print(f"ordre tenu — {a.id} peut démarrer")
    return 0


def journal(e: dict, evenement: str, detail: str = "") -> None:
    e["journal"].append({"quand": maintenant(), "machine": e.get("machine") or "?", "evenement": evenement, "detail": detail})


def demarrer(a) -> int:
    code = verifier(a)
    if code:
        return code
    plan, etat = charger()
    e = etat["etats"][a.id]
    e.update(statut="en_cours", machine=a.machine, branche=a.branche, debut_reel=e["debut_reel"] or dt.date.today().isoformat())
    journal(e, "démarrage", a.branche or "")
    sauver(etat)
    return 0


def tache(a) -> int:
    plan, etat = charger()
    e = etat["etats"][a.id]
    if a.tache not in e["taches"]:
        print(f"tâche inconnue : {a.tache}")
        return 1
    e["taches"][a.tache] = {"etat": a.etat, "preuve": a.preuve, "maj": maintenant()}
    journal(e, f"tâche {a.tache} → {a.etat}", a.preuve)
    sauver(etat)
    return 0


def statut(a) -> int:
    plan, etat = charger()
    if a.statut not in plan["statuts"]:
        print(f"statut inconnu : {a.statut}")
        return 1
    e = etat["etats"][a.id]
    e["statut"] = a.statut
    e["attente"] = {"quand": maintenant(), "raisons": [a.motif]} if a.motif else None
    if a.statut == "livre":
        e["fin_reelle"] = dt.date.today().isoformat()
    journal(e, f"statut → {a.statut}", a.motif or "")
    sauver(etat)
    return 0


def compte_rendu(a) -> int:
    plan, etat = charger()
    e = etat["etats"][a.id]
    e["compte_rendu"] = {"resume": a.resume, "livrables": a.livrable or [], "preuves": a.preuve or [],
                         "ecarts": a.ecart or [], "reste": a.reste or []}
    journal(e, "compte rendu publié")
    sauver(etat)
    return 0


def decision(a) -> int:
    plan, etat = charger()
    if a.id not in {d["id"] for d in plan["decisions"]}:
        print(f"décision inconnue : {a.id}")
        return 1
    etat["decisions_prises"][a.id] = {"prise": a.texte, "par": "JF", "quand": maintenant()}
    sauver(etat)
    return 0


# ---------------------------------------------------------------- synchro (ordonnanceur de chimera)
def _cr_depuis_fichier(chemin: Path) -> dict:
    """Extrait résumé et « reste à faire » du compte rendu écrit par le lot."""
    if not chemin.exists():
        return {}
    txt = chemin.read_text(encoding="utf-8")
    sections, cur = {}, None
    for ligne in txt.splitlines():
        if ligne.startswith("## "):
            cur = ligne[3:].strip().lower()
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(ligne)
    def sec(*mots):
        for k, v in sections.items():
            if any(m in k for m in mots):
                return v
        return []
    resume = " ".join(l.strip() for l in "\n".join(sec("résumé", "resume")).strip().split("\n\n")[0].splitlines()).strip()
    puces = lambda lignes: [l.strip()[2:].strip() for l in lignes if l.strip().startswith(("- ", "* "))][:8]
    return {"resume": resume[:1200], "livrables": puces(sec("livrable"))[:8], "preuves": [],
            "ecarts": puces(sec("écart", "ecart")), "reste": puces(sec("reste"))}


def synchro(a) -> int:
    """Reporte dans etat.json l'état réel des lots de chimera (fichiers .done/.failed/.blocked, pid vivants)."""
    plan, etat = charger()
    avant = json.dumps(etat, sort_keys=True)
    st, logs = Path(a.etat_dir).expanduser(), Path(a.logs).expanduser()
    for it in plan["items"]:
        i, e = it["id"], etat["etats"][it["id"]]
        if e["statut"] in ("livre", "livre_uat", "attente_go_prod"):
            continue
        done, bad = st / f"{i}.done", [st / f"{i}.failed", st / f"{i}.blocked"]
        pid = logs / f"pbm-{i}.pid"
        vivant = False
        if pid.exists():
            try:
                import os
                os.kill(int(pid.read_text().strip()), 0)
                vivant = True
            except (OSError, ValueError):
                vivant = False
        lance = st / f"{i}.launched"
        if done.exists():
            sha = done.read_text().strip()[:9]
            quand = dt.datetime.fromtimestamp(done.stat().st_mtime).astimezone()
            if e["statut"] != "integre":
                e.update(statut="integre", machine="chimera", branche=f"roadmap/{i}", attente=None,
                         fin_reelle=quand.date().isoformat(),
                         debut_reel=e["debut_reel"] or dt.datetime.fromtimestamp(lance.stat().st_mtime).date().isoformat() if lance.exists() else e["debut_reel"])
                e["journal"].append({"quand": quand.strftime("%Y-%m-%dT%H:%M%z"), "machine": "chimera",
                                     "evenement": "intégré dans main", "detail": f"commit {sha}"})
            for t in ("dev", "tests", "compte_rendu", "backlog"):
                if e["taches"][t]["etat"] != "na":
                    e["taches"][t] = {"etat": "fait", "preuve": f"commit {sha} intégré dans main — voir docs/roadmap/comptes-rendus/{i}.md", "maj": quand.strftime("%Y-%m-%dT%H:%M%z")}
            cr = _cr_depuis_fichier(RACINE / "docs/roadmap/comptes-rendus" / f"{i}.md")
            if cr.get("resume"):
                e["compte_rendu"] = cr
        elif any(b.exists() for b in bad) and not vivant:
            raison = next(b.read_text().strip() for b in bad if b.exists())
            if e["statut"] != "bloque":
                e["journal"].append({"quand": maintenant(), "machine": "chimera", "evenement": "arrêté", "detail": raison})
            e.update(statut="bloque", machine="chimera", attente={"quand": maintenant(), "raisons": [f"lot arrêté par l'ordonnanceur : {raison}"]})
        elif vivant or lance.exists():
            if e["statut"] != "en_cours":
                e["journal"].append({"quand": maintenant(), "machine": "chimera", "evenement": "démarré", "detail": f"roadmap/{i}"})
            e.update(statut="en_cours", machine="chimera", branche=f"roadmap/{i}", attente=None,
                     debut_reel=e["debut_reel"] or (dt.datetime.fromtimestamp(lance.stat().st_mtime).date().isoformat() if lance.exists() else dt.date.today().isoformat()))
    if json.dumps(etat, sort_keys=True) != avant:
        sauver(etat)
        print("etat.json mis à jour")
    else:
        print("rien de changé")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("build").set_defaults(f=build)
    x = s.add_parser("verifier"); x.add_argument("id"); x.set_defaults(f=verifier)
    x = s.add_parser("demarrer"); x.add_argument("id"); x.add_argument("--machine", default="?"); x.add_argument("--branche"); x.set_defaults(f=demarrer)
    x = s.add_parser("tache"); x.add_argument("id"); x.add_argument("tache"); x.add_argument("etat", choices=["a_faire", "en_cours", "fait", "na", "bloque", "attente_validation"]); x.add_argument("preuve"); x.set_defaults(f=tache)
    x = s.add_parser("statut"); x.add_argument("id"); x.add_argument("statut"); x.add_argument("--motif"); x.set_defaults(f=statut)
    x = s.add_parser("compte-rendu"); x.add_argument("id"); x.add_argument("--resume", required=True)
    for k in ("livrable", "preuve", "ecart", "reste"):
        x.add_argument(f"--{k}", action="append")
    x.set_defaults(f=compte_rendu)
    x = s.add_parser("synchro"); x.add_argument("--etat-dir", default="~/dev/pbm-state"); x.add_argument("--logs", default="~/dev/logs"); x.set_defaults(f=synchro)
    x = s.add_parser("decision"); x.add_argument("id"); x.add_argument("texte"); x.set_defaults(f=decision)
    a = p.parse_args()
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
