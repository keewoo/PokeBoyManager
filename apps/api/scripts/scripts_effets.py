"""Commande de maintenance du registre `card_scripts` : importer, valider, lister, diffuser, errata.

Le couteau suisse des scripts d'effet (lot `j-effets-catalogue-compilation`). Il opère sur la base
pointée par ``DATABASE_URL`` : les sous-commandes qui lisent le **catalogue** (`mesurer`,
`diffuser`) peuvent viser une base en lecture seule (`pbm_catalogue_ref` de la flotte) ;
celles qui touchent le **registre** (`importer`, `valider`, `errata`) exigent une base où la table
`card_scripts` existe (`alembic upgrade head`).

Sous-commandes :

* ``lister`` — l'état du registre, compté par statut, une ligne par script.
* ``importer <fichier.json>`` — enregistre un ou plusieurs scripts depuis un JSON (idempotent : la
  même empreinte met à jour sa ligne). Chaque entrée : ``source_text``, ``statut``, ``dsl_version``,
  et selon le statut ``script`` / ``lang`` / ``author`` / ``tests`` / ``notes``.
* ``valider <empreinte> --auteur X`` — fait passer un script existant à ``scripte`` (sa validation),
  après que ses tests sont au vert ; refuse si la ligne n'a pas de programme (rien de deviné, D9).
* ``diffuser`` — pour chaque script ``scripte``, combien de cartes vivantes il rend jouables : la
  *diffusion* d'un script unique sur les centaines de cartes qui partagent son texte.
* ``errata [--a-blanc]`` — réconcilie le registre avec le catalogue : les scripts dont le texte
  source a disparu repassent « à revoir » (``--a-blanc`` montre sans écrire).
* ``mesurer`` — le regroupement chiffré sur le catalogue : scripts naïfs vs scripts groupés, et la
  part économisée (critère n°2 du lot).

Usage :
    DATABASE_URL=postgresql+asyncpg://... uv run python scripts/scripts_effets.py lister
    DATABASE_URL=... uv run python scripts/scripts_effets.py importer mes_scripts.json
    DATABASE_URL=... uv run python scripts/scripts_effets.py valider <empreinte> --auteur jf
    DATABASE_URL=<catalogue> uv run python scripts/scripts_effets.py mesurer
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter

from sqlalchemy import func, select

from pbm_api.db import async_session_factory
from pbm_api.jeu.scripts.depot import enregistrer_script, script_par_empreinte, tous_les_scripts
from pbm_api.jeu.scripts.empreinte import effets_scriptables
from pbm_api.jeu.scripts.errata import detecter_errata
from pbm_api.jeu.scripts.groupement import mesurer_groupement
from pbm_api.models import Card
from pbm_api.models.card_scripts import SCRIPT_STATUT_SCRIPTE


async def _lister() -> None:
    """Affiche le registre entier, compté par statut."""
    async with async_session_factory() as db:
        scripts = await tous_les_scripts(db)
    compte = Counter(s.statut for s in scripts)
    resume = ", ".join(f"{k}: {v}" for k, v in sorted(compte.items()))
    print(f"{len(scripts)} script(s) au registre — {resume}")
    for s in scripts:
        apercu = s.source_text.replace("\n", " ")[:70]
        print(f"  [{s.statut:<13}] v{s.dsl_version} {s.text_fingerprint[:12]}…  « {apercu} »")


async def _importer(fichier: str) -> None:
    """Enregistre les scripts décrits dans un fichier JSON (un objet, ou une liste d'objets)."""
    with open(fichier, encoding="utf-8") as f:
        donnees = json.load(f)
    entrees = donnees if isinstance(donnees, list) else [donnees]
    async with async_session_factory() as db:
        for i, e in enumerate(entrees):
            if "source_text" not in e or "statut" not in e or "dsl_version" not in e:
                raise SystemExit(f"Entrée {i} : source_text, statut et dsl_version obligatoires.")
            ligne = await enregistrer_script(
                db,
                source_text=e["source_text"],
                statut=e["statut"],
                dsl_version=int(e["dsl_version"]),
                script=e.get("script"),
                lang=e.get("lang"),
                author=e.get("author"),
                tests=e.get("tests"),
                notes=e.get("notes"),
            )
            print(f"  {ligne.statut:<13} {ligne.text_fingerprint[:12]}…  (import ok)")
    print(f"{len(entrees)} script(s) importé(s).")


async def _valider(empreinte: str, auteur: str) -> None:
    """Valide (passe à « scripté ») un script existant ; refuse s'il n'a pas de programme."""
    async with async_session_factory() as db:
        ligne = await script_par_empreinte(db, empreinte)
        if ligne is None:
            raise SystemExit(f"Aucun script pour l'empreinte {empreinte} — rien à valider.")
        if ligne.script is None:
            raise SystemExit(
                f"Script {empreinte[:12]}… sans programme : on ne valide pas un effet vide (D9)."
            )
        await enregistrer_script(
            db,
            source_text=ligne.source_text,
            statut=SCRIPT_STATUT_SCRIPTE,
            dsl_version=ligne.dsl_version,
            script=ligne.script,
            lang=ligne.lang,
            author=auteur,
            tests=ligne.tests,
            notes=ligne.notes,
        )
    print(f"Script {empreinte[:12]}… validé (scripté) par {auteur}.")


async def _diffuser() -> None:
    """Pour chaque script « scripté », combien de cartes vivantes il rend jouables (diffusion)."""
    portee: Counter[str] = Counter()
    async with async_session_factory() as db:
        resultat = await db.stream(
            select(Card.id, Card.name, Card.abilities, Card.attacks, Card.effect)
        )
        async for row in resultat:
            for effet in effets_scriptables(row):
                portee[effet.empreinte] += 1
        scriptes = [s for s in await tous_les_scripts(db) if s.statut == SCRIPT_STATUT_SCRIPTE]
    if not scriptes:
        print("Aucun script « scripté » au registre — rien à diffuser.")
        return
    total_cartes = sum(portee[s.text_fingerprint] for s in scriptes)
    print(f"{len(scriptes)} script(s) « scripté(s) » couvrent {total_cartes} carte(s) vivante(s) :")
    for s in sorted(scriptes, key=lambda s: portee[s.text_fingerprint], reverse=True):
        apercu = s.source_text.replace("\n", " ")[:60]
        n = portee[s.text_fingerprint]
        print(f"  {n:>5} carte(s)  {s.text_fingerprint[:12]}…  « {apercu} »")


async def _errata(a_blanc: bool) -> None:
    """Réconcilie le registre : les scripts au texte disparu repassent « à revoir »."""
    async with async_session_factory() as db:
        orphelins = await detecter_errata(db, appliquer=not a_blanc)
    verbe = "seraient à revoir" if a_blanc else "repassés « à revoir »"
    print(f"{len(orphelins)} script(s) {verbe} (texte source absent du catalogue).")
    for s in orphelins:
        apercu = s.source_text.replace("\n", " ")[:60]
        print(f"  {s.text_fingerprint[:12]}…  « {apercu} »")


async def _mesurer() -> None:
    """Le regroupement chiffré sur le catalogue (critère n°2) : scripts naïfs vs groupés."""
    async with async_session_factory() as db:
        total = (await db.execute(select(func.count()).select_from(Card))).scalar_one()
        resultat = await db.stream(
            select(Card.id, Card.name, Card.abilities, Card.attacks, Card.effect)
        )
        cartes = [row async for row in resultat]
    mesure = mesurer_groupement(cartes)
    print(f"Catalogue : {total} carte(s) au total, {mesure.cartes_examinees} examinée(s).")
    print(f"  cartes porteuses d'au moins un effet : {mesure.cartes_porteuses}")
    print(f"  scripts à écrire — voie naïve (un par couple carte+effet) : {mesure.effets_total}")
    print(f"  scripts à écrire — voie groupée (un par texte distinct) : {mesure.textes_distincts}")
    print(f"  scripts économisés par le regroupement : {mesure.scripts_economises}  "
          f"({mesure.reduction_pct} %)")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Maintenance du registre des scripts d'effet.")
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("lister", help="l'état du registre")
    imp = sous.add_parser("importer", help="enregistrer des scripts depuis un JSON")
    imp.add_argument("fichier")
    val = sous.add_parser("valider", help="valider (scripté) un script existant")
    val.add_argument("empreinte")
    val.add_argument("--auteur", required=True)
    sous.add_parser("diffuser", help="la portée de chaque script sur le catalogue")
    err = sous.add_parser("errata", help="réconcilier le registre avec le catalogue")
    err.add_argument("--a-blanc", action="store_true", help="montrer sans écrire")
    sous.add_parser("mesurer", help="le regroupement chiffré (critère n°2)")
    return p


def main(argv: list[str] | None = None) -> None:
    """Point d'entrée : lit la sous-commande et exécute la coroutine correspondante."""
    args = _parser().parse_args(argv)
    if args.commande == "lister":
        asyncio.run(_lister())
    elif args.commande == "importer":
        asyncio.run(_importer(args.fichier))
    elif args.commande == "valider":
        asyncio.run(_valider(args.empreinte, args.auteur))
    elif args.commande == "diffuser":
        asyncio.run(_diffuser())
    elif args.commande == "errata":
        asyncio.run(_errata(args.a_blanc))
    elif args.commande == "mesurer":
        asyncio.run(_mesurer())


if __name__ == "__main__":
    sys.exit(main())
