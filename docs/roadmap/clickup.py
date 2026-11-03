#!/usr/bin/env python3
"""Porte la roadmap de PokeBoyManager dans ClickUp — et sait reprendre là où elle s'est arrêtée.

Le plan du dépôt (`roadmap.json`, `jeu/jeu.json`) et l'état réel (`etat.json`) restent la **seule
source de vérité** : ce script ne fait que les refléter dans ClickUp, pour que le pilotage se fasse
là où JF regarde. Il ne relit jamais ClickUp pour décider de l'état d'un lot.

**Idempotent, parce que le quota l'exige.** Le jeton est partagé avec la QA nocturne (~300 appels
par jour) et ClickUp limite à 100 requêtes par minute : un passage qui crée 155 tâches peut être
coupé en route. Chaque objet créé est donc noté dans un fichier d'état local (``--etat``), et un
second passage ne recrée rien — il complète. Un lot déjà présent dont le statut a changé est
**mis à jour** plutôt que dupliqué.

    python3 docs/roadmap/clickup.py --a-blanc          # ce qu'il ferait, sans un seul appel d'écriture
    python3 docs/roadmap/clickup.py                    # crée ce qui manque, met à jour les statuts
    python3 docs/roadmap/clickup.py --max-appels 80    # s'arrête avant d'épuiser le quota partagé

Le jeton vient de ``CLICKUP_API_TOKEN`` (chargé par ``~/.zshenv`` depuis ``infra/.env.qa``). Il
n'est **jamais** affiché, ni dans une erreur, ni dans le journal.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

API = "https://api.clickup.com/api/v2"
ESPACE = "901210355186"  # espace « Space » du workspace Pokeboy (90122087734)

RACINE = pathlib.Path(__file__).resolve().parent
ETAT_DEFAUT = "/Volumes/Data/DevAI/pokeboy/ops/clickup-etat.json"

# L'état du dépôt vers les statuts de l'espace ClickUp (« to do », « in progress », « complete »).
# `livre` et `integre` sont tous deux terminés côté pilotage ; la nuance est dite dans le corps.
STATUT = {
    "a_faire": "to do",
    "en_cours": "in progress",
    "integre": "complete",
    "livre": "complete",
    "attente_validation": "in progress",
    "bloque": "in progress",
}
PRIORITE = {"P0": 1, "P1": 2, "P2": 3, "P3": 4}

PAUSE_S = 0.7  # ClickUp : 100 requêtes/minute. 0,7 s laisse de la marge à la QA nocturne.


class Quota(Exception):
    """Levée quand le plafond d'appels de ce passage est atteint — on s'arrête proprement."""


class Client:
    """Appels ClickUp, avec plafond, temporisation et reprise sur 429."""

    def __init__(self, jeton: str, max_appels: int, a_blanc: bool) -> None:
        self._jeton = jeton
        self.max_appels = max_appels
        self.a_blanc = a_blanc
        self.appels = 0

    def _appel(self, methode: str, chemin: str, corps: dict | None = None) -> dict:
        if self.appels >= self.max_appels:
            raise Quota(f"plafond de {self.max_appels} appels atteint")
        self.appels += 1
        donnees = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(API + chemin, data=donnees, method=methode)
        req.add_header("Authorization", self._jeton)
        req.add_header("Content-Type", "application/json")
        for essai in (1, 2, 3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    brut = r.read().decode()
                    time.sleep(PAUSE_S)
                    return json.loads(brut) if brut else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode()[:300]
                if e.code == 429 and essai < 3:
                    print(f"    429 (cadence) — pause 30 s, essai {essai}/3")
                    time.sleep(30)
                    continue
                # Jamais le jeton dans le message : seul le code et la réponse du serveur.
                raise RuntimeError(f"{methode} {chemin} → HTTP {e.code} : {detail}") from e
        raise RuntimeError(f"{methode} {chemin} : trois essais sans réponse exploitable")

    def lire(self, chemin: str) -> dict:
        """Une lecture (jamais soumise à ``--a-blanc`` : lire ne change rien)."""
        return self._appel("GET", chemin)

    def creer_dossier(self, nom: str) -> str:
        if self.a_blanc:
            return f"(à blanc:dossier:{nom})"
        return str(self._appel("POST", f"/space/{ESPACE}/folder", {"name": nom})["id"])

    def creer_liste(self, dossier_id: str, nom: str) -> str:
        if self.a_blanc:
            return f"(à blanc:liste:{nom})"
        return str(self._appel("POST", f"/folder/{dossier_id}/list", {"name": nom})["id"])

    def creer_tache(self, liste_id: str, corps: dict) -> str:
        if self.a_blanc:
            return f"(à blanc:tache:{corps['name'][:40]})"
        return str(self._appel("POST", f"/list/{liste_id}/task", corps)["id"])

    def majour_tache(self, task_id: str, corps: dict) -> None:
        if self.a_blanc:
            return
        self._appel("PUT", f"/task/{task_id}", corps)


def corps_tache(lot: dict, statut_depot: str, origine: str) -> dict:
    """La tâche ClickUp d'un lot : son nom, son statut, et un corps qui dit POURQUOI il existe."""
    lignes = [f"**{lot.get('gain', '').strip()}**", ""]
    if lot.get("fonctionnalites") and lot["fonctionnalites"] != "—":
        lignes += ["## Ce que le lot fait", lot["fonctionnalites"].strip(), ""]
    if lot.get("tenants") and lot["tenants"] != "—":
        lignes += ["## Tenants", lot["tenants"].strip(), ""]
    if lot.get("aboutissants") and lot["aboutissants"] != "—":
        lignes += ["## Aboutissants", lot["aboutissants"].strip(), ""]
    if lot.get("risques") and lot["risques"] != "—":
        lignes += ["## Risques", lot["risques"].strip(), ""]
    meta = [
        f"- **état dans le dépôt** : `{statut_depot}`",
        f"- **piste** : {lot.get('piste', '?')} · **couloir** : {lot.get('couloir', '?')}",
        f"- **priorité** {lot.get('priorite', '?')} · taille {lot.get('taille', '?')}"
        f" · complexité {lot.get('complexite', '?')}/5 · difficulté {lot.get('difficulte', '?')}/5",
    ]
    if lot.get("decision"):
        meta.append(f"- **décision requise** : {lot['decision']}")
    if lot.get("apres"):
        meta.append("- **après** : " + ", ".join(f"`{a}`" for a in lot["apres"]))
    if lot.get("debut") or lot.get("fin"):
        meta.append(f"- **fenêtre du plan** : {lot.get('debut', '?')} → {lot.get('fin', '?')}")
    meta += [
        f"- **prompt** : `prompts/{lot['id']}.md`",
        f"- **source** : `{origine}` — le dépôt fait foi, ClickUp ne fait que le refléter.",
    ]
    lignes += ["## Repères", *meta]

    corps = {
        "name": f"{lot['id']} — {lot.get('titre', '')}"[:255],
        "markdown_content": "\n".join(lignes),
        "status": STATUT.get(statut_depot, "to do"),
    }
    if lot.get("priorite") in PRIORITE:
        corps["priority"] = PRIORITE[lot["priorite"]]
    return corps


def charger_plan() -> list[tuple[str, str, dict]]:
    """Tous les lots, avec leur groupe de liste : ``(groupe, origine, lot)``."""
    etats = json.loads((RACINE / "etat.json").read_text(encoding="utf-8"))["etats"]
    plan = json.loads((RACINE / "roadmap.json").read_text(encoding="utf-8"))
    jeu = json.loads((RACINE / "jeu" / "jeu.json").read_text(encoding="utf-8"))

    items = plan["items"]
    liste_items = list(items.values()) if isinstance(items, dict) else items
    sortie: list[tuple[str, str, dict]] = []
    for lot in liste_items:
        lot = dict(lot)
        lot["_statut"] = etats.get(lot["id"], {}).get("statut", "a_faire")
        sortie.append((f"Plan daté — {lot.get('vague', '?')}", "docs/roadmap/roadmap.json", lot))
    for lot in jeu["lots"]:
        lot = dict(lot)
        lot["_statut"] = etats.get(lot["id"], {}).get("statut", "a_faire")
        sortie.append((f"Jeu — {lot.get('jalon', '?')}", "docs/roadmap/jeu/jeu.json", lot))
    return sortie


def reconstruire(cli: "Client", etat: dict) -> int:
    """Retrouve dans ClickUp ce qu'un état local perdu ne dit plus — sinon on crée des DOUBLONS.

    L'état local (``--etat``) vit hors du dépôt : un disque réinitialisé, une autre machine, et il
    n'existe plus. Sans ce rattrapage, le passage suivant recréerait les 155 tâches à côté des
    anciennes. On réapparie donc par le **préfixe du nom** (`<id> — titre`), qui est notre clé.

    Coûte 1 + (nombre de listes) lectures, et ne s'exécute que si l'état ne connaît aucune tâche
    alors que le dossier existe déjà.
    """
    retrouvees = 0
    dossiers = cli.lire(f"/space/{ESPACE}/folder?archived=false").get("folders", [])
    for dossier in dossiers:
        prefixe = {"Roadmap — plan daté": "Plan daté — ", "Roadmap — jeu": "Jeu — "}.get(dossier["name"])
        if prefixe is None:
            continue
        etat["dossiers"][dossier["name"]] = str(dossier["id"])
        for liste in dossier.get("lists", []):
            etat["listes"][prefixe + liste["name"]] = str(liste["id"])
            taches = cli.lire(
                f"/list/{liste['id']}/task?archived=false&include_closed=true"
            ).get("tasks", [])
            for tache in taches:
                lot_id = tache["name"].split(" — ", 1)[0].strip()
                if not lot_id:
                    continue
                etat["taches"][lot_id] = {
                    "id": str(tache["id"]),
                    # Le statut ClickUp ne dit pas si c'était `integre` ou `livre` : on note le
                    # statut ClickUp, et la comparaison suivante remettra l'état du dépôt.
                    "statut": "?",
                    "statut_clickup": tache["status"]["status"],
                }
                retrouvees += 1
    return retrouvees


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a-blanc", action="store_true", help="n'écrit rien, montre le plan d'action")
    ap.add_argument("--etat", default=ETAT_DEFAUT, help="fichier d'état local (reprise)")
    ap.add_argument("--max-appels", type=int, default=400, help="plafond d'appels pour ce passage")
    args = ap.parse_args()

    jeton = os.environ.get("CLICKUP_API_TOKEN", "")
    if not jeton and not args.a_blanc:
        print("⛔ CLICKUP_API_TOKEN absent de l'environnement (zsh -lc le charge)", file=sys.stderr)
        return 1

    chemin_etat = pathlib.Path(args.etat)
    etat = (
        json.loads(chemin_etat.read_text(encoding="utf-8"))
        if chemin_etat.exists()
        else {"dossiers": {}, "listes": {}, "taches": {}}
    )

    lots = charger_plan()

    # État local absent ou vide alors que ClickUp porte déjà la roadmap : on se réapparie AVANT
    # de créer quoi que ce soit. Sans ça, on doublerait les 155 tâches.
    if not etat["taches"] and not args.a_blanc:
        sonde = Client(jeton, args.max_appels, False)
        if any(
            d.get("name") in ("Roadmap — plan daté", "Roadmap — jeu")
            for d in sonde.lire(f"/space/{ESPACE}/folder?archived=false").get("folders", [])
        ):
            print("état local vide mais ClickUp porte déjà la roadmap — réappariement en cours")
            n = reconstruire(sonde, etat)
            print(f"  {n} tâches retrouvées par leur identifiant de lot")
            chemin_etat.parent.mkdir(parents=True, exist_ok=True)
            chemin_etat.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")

    groupes: dict[str, list[tuple[str, dict]]] = {}
    for groupe, origine, lot in lots:
        groupes.setdefault(groupe, []).append((origine, lot))

    a_creer = sum(1 for _, _, l in lots if l["id"] not in etat["taches"])
    def doit_majour(lot: dict) -> bool:
        """Vrai seulement si ClickUp ne porte pas DÉJÀ le bon statut.

        Une tâche réappariée a un statut de dépôt inconnu (« ? ») mais un statut ClickUp connu :
        la comparer sur le seul statut de dépôt annoncerait 155 mises à jour pour n'en faire
        aucune. Un compteur qui annonce du travail fictif ne vaut pas mieux qu'un journal muet.
        """
        connu = etat["taches"].get(lot["id"])
        if connu is None:
            return False
        if connu.get("statut") == lot["_statut"]:
            return False
        return connu.get("statut_clickup") != STATUT.get(lot["_statut"])

    a_majour = sum(1 for _, _, l in lots if doit_majour(l))
    print(f"{len(lots)} lots · {len(groupes)} listes · à créer : {a_creer} · à mettre à jour : {a_majour}")
    if args.a_blanc:
        for g in sorted(groupes):
            neufs = [l["id"] for _, l in groupes[g] if l["id"] not in etat["taches"]]
            print(f"  {g:22} {len(groupes[g]):3} lots · à créer {len(neufs)}")
        print("À BLANC — aucun appel d'écriture")
        return 0

    cli = Client(jeton, args.max_appels, args.a_blanc)
    code = 0
    try:
        for dossier_nom, prefixe in (("Roadmap — plan daté", "Plan daté — "), ("Roadmap — jeu", "Jeu — ")):
            if dossier_nom not in etat["dossiers"]:
                etat["dossiers"][dossier_nom] = cli.creer_dossier(dossier_nom)
                print(f"dossier créé : {dossier_nom}")
            dossier_id = etat["dossiers"][dossier_nom]

            for groupe in sorted(g for g in groupes if g.startswith(prefixe)):
                nom_liste = groupe[len(prefixe):]
                if groupe not in etat["listes"]:
                    etat["listes"][groupe] = cli.creer_liste(dossier_id, nom_liste)
                    print(f"  liste créée : {nom_liste}")
                liste_id = etat["listes"][groupe]

                for origine, lot in groupes[groupe]:
                    connu = etat["taches"].get(lot["id"])
                    if connu is None:
                        tid = cli.creer_tache(liste_id, corps_tache(lot, lot["_statut"], origine))
                        etat["taches"][lot["id"]] = {"id": tid, "statut": lot["_statut"]}
                        print(f"    + {lot['id']} ({STATUT.get(lot['_statut'])})")
                    elif doit_majour(lot):
                        cli.majour_tache(connu["id"], {"status": STATUT.get(lot["_statut"], "to do")})
                        connu["statut"] = lot["_statut"]
                        print(f"    ~ {lot['id']} → {STATUT.get(lot['_statut'])}")
    except Quota as e:
        print(f"⏸ {e} — état sauvegardé, relancer pour continuer")
        code = 2
    except RuntimeError as e:
        print(f"⛔ {e}", file=sys.stderr)
        code = 1
    finally:
        chemin_etat.parent.mkdir(parents=True, exist_ok=True)
        chemin_etat.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"appels consommés : {cli.appels} · état : {chemin_etat}")
    return code


if __name__ == "__main__":
    sys.exit(main())
