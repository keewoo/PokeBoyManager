"""Sonde du **jeu** : relève les métriques, alerte si ça cloche, récapitule chaque semaine.

Lot ``j-observabilite-jeu``. Elle suit exactement le motif de la **sonde honnête** des prix
(``docs/infra/JOBS-LOURDS.md``) : une pièce portable, versionnée ici, lancée depuis la release
déployée, qui écrit son **verdict** dans un fichier d'état et envoie un e-mail — plutôt qu'un
script ad hoc par signal à surveiller.

Deux modes, et ils ne font pas le même métier :

* ``--mode quotidien`` — n'envoie **que s'il y a quelque chose à dire** (alertes de
  :mod:`pbm_api.observabilite.regles`). Un e-mail quotidien qui dit toujours « tout va bien »
  n'est plus lu au bout d'une semaine ;
* ``--mode hebdo`` — envoie **toujours** le récapitulatif des parties jouées. C'est l'homme mort
  du dispositif : son absence est elle-même un signal, et le mode quotidien la détecte en lisant
  la date du dernier envoi dans le fichier d'état.

Exemples (depuis ``apps/api``, avec ``DATABASE_URL`` pointant la base à observer) :

    UV_PYTHON=3.12 uv run python scripts/sonde_jeu.py --mode quotidien
    UV_PYTHON=3.12 uv run python scripts/sonde_jeu.py --mode hebdo
    UV_PYTHON=3.12 uv run python scripts/sonde_jeu.py --a-blanc        # affiche, n'envoie rien

Codes de sortie : ``0`` rien à signaler, ``2`` alerte(s) émise(s) — dont ``PANNE`` —, ``1`` la
sonde elle-même a échoué (elle ne peut alors rien conclure, et le dit). Aucun secret n'est affiché.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from pbm_api.config import settings
from pbm_api.db import async_session_factory
from pbm_api.email import get_email_sender
from pbm_api.observabilite.metriques import FENETRE_DEFAUT_H, FENETRE_HEBDO_H, relever
from pbm_api.observabilite.rapport import (
    sujet_alerte,
    sujet_recap_hebdo,
    texte_alerte,
    texte_recap_hebdo,
)
from pbm_api.observabilite.regles import alerte_recap_manquant, evaluer, verdict

#: Fichier d'état par défaut — hors du dépôt, comme celui de la sonde des prix
#: (``~/dev/pbm/jobs/state/prices.json``). Il porte le dernier verdict ET la date du dernier
#: récapitulatif hebdomadaire : c'est cette date qui permet de transformer une absence en signal.
ETAT_DEFAUT = Path.home() / ".pbm-sonde-jeu" / "etat.json"

MODE_QUOTIDIEN = "quotidien"
MODE_HEBDO = "hebdo"


def lire_etat(chemin: Path) -> dict:
    """Le fichier d'état, ou un état vide s'il n'existe pas encore (premier passage).

    Un état **illisible** (tronqué par un arrêt brutal) n'est pas traité comme un état vide : on
    le signale sur la sortie d'erreur et on repart d'un état vide, ce qui déclenchera l'alerte
    « récapitulatif jamais envoyé » plutôt que de faire silence.
    """
    if not chemin.exists():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"état illisible ({chemin}) : {exc} — on repart d'un état vide", file=sys.stderr)
        return {}


def ecrire_etat(chemin: Path, etat: dict) -> None:
    """Écrit l'état, en créant son dossier au besoin. Une écriture qui échoue **remonte**."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")


def _date_ou_none(valeur: str | None) -> date | None:
    """Lit une date ISO de l'état, ou ``None`` si absente/invalide (traitée comme « jamais »)."""
    if not valeur:
        return None
    try:
        return date.fromisoformat(valeur)
    except ValueError:
        return None


async def executer(
    *,
    mode: str,
    fenetre_heures: int,
    chemin_etat: Path,
    destinataire: str,
    a_blanc: bool,
) -> int:
    """Un passage complet : relève, juge, envoie, écrit l'état. Renvoie le code de sortie."""
    maintenant = datetime.now(UTC)
    async with async_session_factory() as session:
        releve = await relever(session, maintenant=maintenant, fenetre_heures=fenetre_heures)

    alertes = evaluer(releve)
    etat_precedent = lire_etat(chemin_etat)

    # Le mode quotidien porte aussi la garde de l'homme mort : si le récapitulatif hebdomadaire
    # n'est plus parti depuis trop longtemps, c'est la sonde qui ne tourne plus — et ça s'ajoute
    # aux alertes du jeu, même quand le jeu lui-même va bien.
    if mode == MODE_QUOTIDIEN:
        manquant = alerte_recap_manquant(
            _date_ou_none(etat_precedent.get("dernier_hebdo")), maintenant.date()
        )
        if manquant is not None:
            alertes = [*alertes, manquant]

    instant = maintenant.strftime("%Y-%m-%d %H:%M UTC")
    if mode == MODE_HEBDO:
        sujet, corps, envoyer = sujet_recap_hebdo(releve), texte_recap_hebdo(
            releve, alertes, instant=instant
        ), True
    else:
        sujet, corps = sujet_alerte(alertes), texte_alerte(releve, alertes, instant=instant)
        envoyer = bool(alertes)

    print(f"verdict : {verdict(alertes)}")
    print(corps)

    if envoyer and not a_blanc:
        await get_email_sender().send(destinataire, sujet, corps)
        print(f"e-mail envoyé à {destinataire} — « {sujet} »")
    elif envoyer:
        print(f"(à blanc) e-mail NON envoyé à {destinataire} — « {sujet} »")
    else:
        print("rien à signaler : aucun e-mail (le mode quotidien n'envoie que sur alerte).")

    etat = {
        **etat_precedent,
        "dernier_passage": maintenant.isoformat(),
        "mode": mode,
        "verdict": verdict(alertes),
        "alertes": [a.code for a in alertes],
        "releve": releve.en_json(),
    }
    if mode == MODE_HEBDO and envoyer and not a_blanc:
        etat["dernier_hebdo"] = maintenant.date().isoformat()
    if not a_blanc:
        ecrire_etat(chemin_etat, etat)

    return 2 if alertes else 0


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI. Toute panne de la sonde elle-même sort en ``1``, avec sa cause."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=(MODE_QUOTIDIEN, MODE_HEBDO), default=MODE_QUOTIDIEN)
    parser.add_argument(
        "--fenetre-heures",
        type=int,
        default=None,
        help="Fenêtre d'observation (défaut : 24 h en quotidien, 168 h en hebdomadaire).",
    )
    parser.add_argument("--etat", type=Path, default=ETAT_DEFAUT)
    parser.add_argument(
        "--destinataire",
        default=settings.supervision_email,
        help="Boîte qui reçoit alertes et récapitulatifs (défaut : SUPERVISION_EMAIL).",
    )
    parser.add_argument(
        "--a-blanc",
        action="store_true",
        help="Affiche ce qui serait envoyé, n'envoie rien et n'écrit pas l'état.",
    )
    args = parser.parse_args(argv)

    fenetre = args.fenetre_heures
    if fenetre is None:
        fenetre = FENETRE_HEBDO_H if args.mode == MODE_HEBDO else FENETRE_DEFAUT_H

    try:
        return asyncio.run(
            executer(
                mode=args.mode,
                fenetre_heures=fenetre,
                chemin_etat=args.etat,
                destinataire=args.destinataire,
                a_blanc=args.a_blanc,
            )
        )
    except Exception as exc:  # noqa: BLE001 — une sonde qui tombe le DIT, elle ne conclut pas
        print(f"SONDE EN ÉCHEC : {exc.__class__.__name__} — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
