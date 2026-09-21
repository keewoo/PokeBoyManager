#!/usr/bin/env python3
"""Backlog du jeu — vérification de l'ordonnancement et génération du document.

    python3 docs/roadmap/jeu/build-jeu.py            # vérifie et génère
    python3 docs/roadmap/jeu/build-jeu.py --verifier # vérifie seulement

Source : docs/roadmap/jeu/plan/*.json  (meta.json + fichiers de lots)
Produit : docs/roadmap/jeu/BACKLOG-JEU.md  et  docs/roadmap/jeu/jeu.json

Ce plan n'a pas de dates : l'ordre est celui des dépendances. Le « palier » d'un
lot est calculé (0 = rien devant lui), et tous les lots d'un même palier peuvent
avancer en parallèle s'ils sont dans des couloirs différents.
Codes de sortie : 0 ok, 1 plan incohérent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
PLAN = RACINE / "plan"
POIDS = {"S": 1, "M": 2, "L": 3, "XL": 5}


def charger() -> tuple[dict, list[dict]]:
    meta = json.loads((PLAN / "meta.json").read_text(encoding="utf-8"))
    lots: list[dict] = []
    for f in sorted(PLAN.glob("*.json")):
        if f.name == "meta.json":
            continue
        lots.extend(json.loads(f.read_text(encoding="utf-8")))
    return meta, lots


def valider(meta: dict, lots: list[dict]) -> list[str]:
    err: list[str] = []
    par_id: dict[str, dict] = {}
    for lot in lots:
        if lot["id"] in par_id:
            err.append(f"{lot['id']} : identifiant en double")
        par_id[lot["id"]] = lot

    pistes = {p["id"] for p in meta["pistes"]}
    couloirs = {c["id"] for c in meta["couloirs"]}
    jalons = {j["id"] for j in meta["jalons"]}
    decisions = {d["id"] for d in meta["decisions"]} | {f"D{n}" for n in range(1, 12)}
    champs = ("titre", "piste", "couloir", "jalon", "priorite", "taille", "gain",
              "fonctionnalites", "mission", "acceptation", "livrables", "risques")

    for lot in lots:
        for champ in champs:
            if not lot.get(champ):
                err.append(f"{lot['id']} : champ « {champ} » manquant ou vide")
        if not isinstance(lot.get("apres"), list):
            err.append(f"{lot['id']} : champ « apres » manquant (liste, éventuellement vide)")
        if lot.get("piste") not in pistes:
            err.append(f"{lot['id']} : piste inconnue « {lot.get('piste')} »")
        if lot.get("couloir") not in couloirs:
            err.append(f"{lot['id']} : couloir inconnu « {lot.get('couloir')} »")
        if lot.get("jalon") not in jalons:
            err.append(f"{lot['id']} : jalon inconnu « {lot.get('jalon')} »")
        if lot.get("decision") and lot["decision"] not in decisions:
            err.append(f"{lot['id']} : décision inconnue « {lot['decision']} »")
        for dep in lot.get("apres", []):
            if dep not in par_id:
                err.append(f"{lot['id']} : dépend de « {dep} », qui n'existe pas")

    # décisions qui débloquent des lots inexistants
    for d in meta["decisions"]:
        for cible in d.get("debloque", []):
            if cible not in par_id:
                err.append(f"{d['id']} : débloque « {cible} », qui n'existe pas")

    # correspondance avec le plan daté
    for ancien, remplacants in meta["correspondance_plan_date"]["remplaces"].items():
        for r in remplacants:
            if r not in par_id:
                err.append(f"correspondance {ancien} : « {r} » n'existe pas")
    return err


def paliers(lots: list[dict]) -> dict[str, int]:
    """Rang topologique. Lève si un cycle existe."""
    par_id = {lot["id"]: lot for lot in lots}
    rang: dict[str, int] = {}
    en_cours: set[str] = set()

    def calcul(i: str, chemin: list[str]) -> int:
        if i in rang:
            return rang[i]
        if i in en_cours:
            boucle = " → ".join(chemin[chemin.index(i):] + [i])
            raise ValueError(f"cycle de dépendances : {boucle}")
        en_cours.add(i)
        deps = par_id[i].get("apres", [])
        r = 0 if not deps else 1 + max(calcul(d, chemin + [i]) for d in deps)
        en_cours.discard(i)
        rang[i] = r
        return r

    for lot in lots:
        calcul(lot["id"], [])
    return rang


def chemin_critique(lots: list[dict]) -> list[str]:
    """Plus longue chaîne de dépendances, pondérée par la taille des lots."""
    par_id = {lot["id"]: lot for lot in lots}
    memo: dict[str, tuple[int, list[str]]] = {}

    def calcul(i: str) -> tuple[int, list[str]]:
        if i in memo:
            return memo[i]
        poids = POIDS.get(par_id[i].get("taille", "M"), 2)
        deps = par_id[i].get("apres", [])
        if not deps:
            memo[i] = (poids, [i])
        else:
            meilleur = max((calcul(d) for d in deps), key=lambda x: x[0])
            memo[i] = (meilleur[0] + poids, meilleur[1] + [i])
        return memo[i]

    return max((calcul(lot["id"]) for lot in lots), key=lambda x: x[0])[1]


def puces(items: list[str], indent: str = "") -> str:
    return "\n".join(f"{indent}- {x}" for x in items)


def document(meta: dict, lots: list[dict], rang: dict[str, int], critique: list[str]) -> str:
    par_id = {lot["id"]: lot for lot in lots}
    nom_piste = {p["id"]: p["nom"] for p in meta["pistes"]}
    machine = {c["id"]: c["machine"] for c in meta["couloirs"]}
    suivants: dict[str, list[str]] = {lot["id"]: [] for lot in lots}
    for lot in lots:
        for dep in lot.get("apres", []):
            suivants[dep].append(lot["id"])

    L: list[str] = []
    A = L.append
    A(f"# {meta['titre']}")
    A("")
    A("> GÉNÉRÉ par `docs/roadmap/jeu/build-jeu.py` depuis `docs/roadmap/jeu/plan/`. Ne pas éditer à la main.")
    A(f"> Version {meta['version']} — {meta['date']} — {len(lots)} lots.")
    A("")
    A(f"**Objet.** {meta['objet']}")
    A("")
    A(f"**Pourquoi une section à part.** {meta['pourquoi_a_part']}")
    A("")
    A("## Principes")
    A("")
    A(puces(meta["principes"]))
    A("")
    A("## Comment lire ce plan")
    A("")
    A("- **Palier** : rang calculé depuis les dépendances. Palier 0 = rien devant. "
      "Deux lots du même palier peuvent avancer **en parallèle** s'ils sont dans des couloirs différents.")
    A("- **Jalon** : ce que le jeu sait faire quand le lot est livré. C'est l'avancement qu'on montre à JF, "
      "à la place d'une date.")
    A("- **Couloir** : un couloir porte un lot à la fois, dans son propre worktree, sur la machine indiquée.")
    A("- **Taille** : S ≈ une session, M ≈ deux à trois, L ≈ une semaine de couloir. Aucune date n'en est déduite.")
    A("")
    A("| Couloir | Machine | Rôle |")
    A("|---|---|---|")
    for c in meta["couloirs"]:
        A(f"| `{c['id']}` | {c['machine']} | {c['quoi']} |")
    A("")
    A("| Piste | Nom | Ce qu'elle couvre |")
    A("|---|---|---|")
    for p in meta["pistes"]:
        A(f"| `{p['id']}` | {p['nom']} | {p['quoi']} |")
    A("")

    A("## Roadmap — cinq jalons, aucune date")
    A("")
    for j in meta["jalons"]:
        dedans = [l for l in lots if l["jalon"] == j["id"]]
        poids = sum(POIDS.get(l.get("taille", "M"), 2) for l in dedans)
        A(f"### {j['id']} — {j['nom']}")
        A("")
        A(f"_{j['these']}_")
        A("")
        A(f"**Preuve attendue.** {j['preuve']}")
        A("")
        rmin = min(rang[l["id"]] for l in dedans)
        rmax = max(rang[l["id"]] for l in dedans)
        A(f"**{len(dedans)} lots**, poids {poids} (S=1, M=2, L=3), paliers {rmin} → {rmax}. "
          f"Les jalons se chevauchent : pendant que l'interface se construit, les cartes se scriptent "
          f"dans un autre couloir. Un jalon est atteint quand son dernier lot est livré.")
        A("")
        A("| Palier | Lot | Titre | Piste | Couloir | Prio | Taille | Après |")
        A("|---|---|---|---|---|---|---|---|")
        for lot in sorted(dedans, key=lambda x: (rang[x["id"]], x["id"])):
            apres = ", ".join(f"`{d}`" for d in lot.get("apres", [])) or "—"
            A(f"| {rang[lot['id']]} | [`{lot['id']}`](#{lot['id']}) | {lot['titre']} | {lot['piste']} | "
              f"`{lot['couloir']}` | {lot['priorite']} | {lot['taille']} | {apres} |")
        A("")

    A("## Ordre d'exécution — les paliers")
    A("")
    A("Un palier ne peut commencer que quand tout ce dont il dépend est livré. "
      "À l'intérieur d'un palier, les lots sont indépendants : ils partent ensemble, "
      "autant que les couloirs le permettent.")
    A("")
    A("| Palier | Lots | Couloirs mobilisés |")
    A("|---|---|---|")
    for r in range(max(rang.values()) + 1):
        dedans = sorted([l for l in lots if rang[l["id"]] == r], key=lambda x: x["id"])
        if not dedans:
            continue
        cl = sorted({l["couloir"] for l in dedans})
        A(f"| **{r}** | " + ", ".join(f"[`{l['id']}`](#{l['id']})" for l in dedans) + " | " +
          ", ".join(f"`{c}`" for c in cl) + " |")
    A("")
    A("### Chemin critique")
    A("")
    A("La plus longue chaîne de dépendances, pondérée par la taille des lots. "
      "C'est elle qui fixe la durée du chantier : tout retard pris ici se paie intégralement.")
    A("")
    A(" → ".join(f"[`{i}`](#{i})" for i in critique))
    A("")
    poids_crit = sum(POIDS.get(par_id[i].get("taille", "M"), 2) for i in critique)
    A(f"*{len(critique)} lots, poids cumulé {poids_crit}.*")
    A("")

    A("## Décisions à prendre par JF")
    A("")
    A("Aucune n'empêche de commencer : le premier palier n'en dépend pas. Mais chacune bloque un lot précis, "
      "et la prendre tard coûte une reprise.")
    A("")
    for d in meta["decisions"]:
        cibles = ", ".join(f"[`{c}`](#{c})" for c in d.get("debloque", [])) or "—"
        A(f"### {d['id']} — {d['question']}")
        A("")
        A(f"**Enjeu.** {d['enjeu']}")
        A("")
        A(f"**Proposition du pilote.** {d['proposition']}")
        A("")
        A(f"**Bloque :** {cibles}")
        A("")

    A("## Les lots, un par un")
    A("")
    for lot in sorted(lots, key=lambda x: (rang[x["id"]], x["jalon"], x["id"])):
        i = lot["id"]
        A(f"<a id=\"{i}\"></a>")
        A(f"### `{i}` — {lot['titre']}")
        A("")
        A(f"**Palier {rang[i]}** · jalon **{lot['jalon']}** · piste {lot['piste']} ({nom_piste[lot['piste']]}) · "
          f"couloir `{lot['couloir']}` ({machine[lot['couloir']]}) · {lot['priorite']} · taille {lot['taille']}"
          + (f" · complexité {lot['complexite']}/5" if lot.get("complexite") else "")
          + (f" · difficulté {lot['difficulte']}/5" if lot.get("difficulte") else "")
          + (f" · décision **{lot['decision']}**" if lot.get("decision") else ""))
        A("")
        A(f"**Pourquoi ce lot.** {lot['gain']}")
        A("")
        A(f"**Ce qu'il fait.** {lot['fonctionnalites']}")
        A("")
        A("**Mission**")
        A("")
        A(puces(lot["mission"]))
        A("")
        A("**Critères d'acceptation**")
        A("")
        A(puces(lot["acceptation"]))
        A("")
        A(f"**Livrables** : {', '.join(lot['livrables'])}.")
        A("")
        A(f"**Risque à surveiller.** {lot['risques']}")
        A("")
        avant = ", ".join(f"[`{d}`](#{d})" for d in lot.get("apres", [])) or "— (rien ne le précède)"
        apres = ", ".join(f"[`{d}`](#{d})" for d in sorted(suivants[i])) or "— (rien n'en dépend)"
        A(f"**Vient après** : {avant}  ")
        A(f"**Débloque** : {apres}")
        A("")

    A("## Ce que ce backlog remplace dans le plan daté")
    A("")
    A(meta["correspondance_plan_date"]["note"])
    A("")
    A("| Lot du plan daté | Remplacé par |")
    A("|---|---|")
    for ancien, remplacants in meta["correspondance_plan_date"]["remplaces"].items():
        A(f"| `{ancien}` | " + ", ".join(f"[`{r}`](#{r})" for r in remplacants) + " |")
    A("")
    couverts = {r for rs in meta["correspondance_plan_date"]["remplaces"].values() for r in rs}
    nouveaux = [l for l in lots if l["id"] not in couverts]
    if nouveaux:
        A("### Lots qui n'existaient nulle part dans le plan daté")
        A("")
        A("Ce sont les manques que le découpage grossier cachait : sans eux, le jeu se livre "
          "sans être jouable en vrai, ou sans que personne ne s'en aperçoive.")
        A("")
        A("| Lot | Titre |")
        A("|---|---|")
        for l in sorted(nouveaux, key=lambda x: x["id"]):
            A(f"| [`{l['id']}`](#{l['id']}) | {l['titre']} |")
        A("")
    A("### Préalables qui restent dans le plan daté")
    A("")
    A("| Lot | Ce qu'il apporte au jeu |")
    A("|---|---|")
    for lot_id, quoi in meta["correspondance_plan_date"]["prealables_hors_section"].items():
        A(f"| `{lot_id}` | {quoi} |")
    A("")
    return "\n".join(L) + "\n"


def main() -> int:
    meta, lots = charger()
    err = valider(meta, lots)
    if err:
        print("PLAN INCOHÉRENT :", file=sys.stderr)
        for e in err:
            print(f"  - {e}", file=sys.stderr)
        return 1
    try:
        rang = paliers(lots)
    except ValueError as e:
        print(f"PLAN INCOHÉRENT : {e}", file=sys.stderr)
        return 1
    critique = chemin_critique(lots)

    orphelins = [l["id"] for l in lots if not l.get("apres") and rang[l["id"]] == 0]
    print(f"{len(lots)} lots · {max(rang.values()) + 1} paliers · "
          f"chemin critique {len(critique)} lots · points de départ : {', '.join(orphelins)}")

    if "--verifier" in sys.argv:
        print("ordonnancement cohérent (aucun cycle, toutes les dépendances existent)")
        return 0

    fusion = dict(meta)
    fusion["lots"] = [dict(lot, palier=rang[lot["id"]]) for lot in lots]
    fusion["chemin_critique"] = critique
    (RACINE / "jeu.json").write_text(
        json.dumps(fusion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RACINE / "BACKLOG-JEU.md").write_text(
        document(meta, lots, rang, critique), encoding="utf-8")
    print("écrit : docs/roadmap/jeu/BACKLOG-JEU.md et docs/roadmap/jeu/jeu.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
