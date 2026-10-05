"""Passage d'**assistance IA** : proposer les scripts des cartes non scriptées, sous contrôle (DJ8).

Opéré en script depuis la flotte (jamais une route HTTP). Déroule un passage de
:mod:`pbm_api.jeu.scripts.assistance.runner` : sélection DJ2, proposition + contradiction, porte,
écriture du registre, plafond de budget, reprise, rapport par famille.

**La clé plateforme (DJ8), jamais celle d'un utilisateur, jamais dans le dépôt / un journal / une
sortie.** Elle est lue, dans l'ordre : ``--fichier-cle`` (fichier chmod 600 temporaire), puis la
variable d'environnement ``PLATFORM_ANTHROPIC_API_KEY``, puis l'entrée standard. **Sans clé** (et
hors ``--factice``), DJ8 impose de livrer une **mesure sur un fournisseur factice, sans dépense** :
le script le fait et le **dit**, puis s'arrête avant toute dépense.

Usage ::

    # Mesure sans dépense (clé absente) — fournisseur factice :
    DATABASE_URL=... uv run python scripts/assistance_scripts_ia.py --factice --limite 20

    # Passage réel, clé par fichier chmod 600 (plafond 50 € par défaut) :
    DATABASE_URL=... uv run python scripts/assistance_scripts_ia.py \\
        --fichier-cle ~/.pokeboy-secrets/platform-anthropic-key --limite 100

    # Passage réel, clé par entrée standard :
    cat ~/.pokeboy-secrets/platform-anthropic-key | DATABASE_URL=... \\
        uv run python scripts/assistance_scripts_ia.py --limite 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pbm_api.config import settings
from pbm_api.db import async_session_factory
from pbm_api.jeu.scripts.assistance import budget as budget_mod
from pbm_api.jeu.scripts.assistance import runner
from pbm_api.jeu.scripts.assistance.fournisseur import (
    AnthropicGenerateur,
    FournisseurFactice,
    GenerateurScript,
)
from pbm_api.pricing.exchange_rates import get_rate_to_eur

#: Réponse du fournisseur factice : tout effet est déclaré non supporté (jamais un faux script),
#: coût nul. Démontre la mécanique (sélection, porte, rapport, mesures) sans aucune dépense (DJ8).
_REPONSE_FACTICE = json.dumps(
    {
        "non_supporte": True,
        "raison": "fournisseur factice : aucune génération réelle (clé plateforme absente, DJ8)",
        "confiance": "basse",
        "script": None,
        "essais": [],
    },
    ensure_ascii=False,
)


def _lire_cle(fichier: str | None) -> str | None:
    """La clé plateforme, lue sans jamais l'afficher : fichier, puis env, puis entrée standard.

    Rend ``None`` si aucune source ne la fournit — l'appelant bascule alors sur le fournisseur
    factice (DJ8). Ne journalise jamais la valeur ; ``--fichier-cle`` est le chemin recommandé
    (fichier chmod 600 temporaire), effacé par l'opérateur après usage.
    """
    if fichier:
        return Path(fichier).read_text(encoding="utf-8").strip() or None
    if settings.platform_anthropic_api_key:
        return settings.platform_anthropic_api_key
    if not sys.stdin.isatty():
        lu = sys.stdin.read().strip()
        return lu or None
    return None


def _lire_priorite(fichier: str | None) -> dict[str, tuple[int, int]] | None:
    """Charge la priorité de possession PROD : ``{tcgdex_id: [demandeurs, exemplaires]}`` (JSON).

    Extraite en **lecture seule** de la PROD par devAI (comptes ``game_access``), elle porte la
    priorité DJ2 jusqu'au catalogue de référence, qui ne connaît pas les collections des joueurs.
    Rend ``None`` si aucun fichier n'est fourni : le passage retombe alors sur l'univers possédé
    **local** de la base (chemin historique). Ne contient aucun secret (des identifiants de cartes).
    """
    if not fichier:
        return None
    brut = json.loads(Path(fichier).read_text(encoding="utf-8"))
    return {str(tcgdex): (int(v[0]), int(v[1])) for tcgdex, v in brut.items()}


async def _run(args: argparse.Namespace) -> int:
    cle = None if args.factice else _lire_cle(args.fichier_cle)
    plafond = Decimal(str(args.plafond_eur))
    ledger_path = Path(args.ledger) if args.ledger else budget_mod.DEFAULT_LEDGER_PATH
    priorite = _lire_priorite(args.priorite_possession)
    if priorite is not None:
        print(
            f"Priorité de possession PROD : {len(priorite)} carte(s) possédée(s) (DJ2), "
            "univers de sélection = catalogue entier de la base."
        )

    generateur: GenerateurScript
    if cle:
        generateur = AnthropicGenerateur(cle, model=args.model)
        print(f"Fournisseur : Anthropic (modèle {args.model}), plafond {plafond} €.")
    else:
        generateur = FournisseurFactice(lambda _prompt: _REPONSE_FACTICE)
        print(
            "⚠️ Aucune clé plateforme : mesure sur FOURNISSEUR FACTICE, AUCUNE dépense (DJ8). "
            "Fournissez --fichier-cle, PLATFORM_ANTHROPIC_API_KEY ou l'entrée standard pour un "
            "passage réel."
        )

    try:
        async with async_session_factory() as db:
            rate = await get_rate_to_eur(db, "USD", datetime.now(UTC).date())
            if cle and rate is None:
                # Fail-closed : un passage réel sans taux de change ne doit jamais se replier sur un
                # coût à 0 (le plafond deviendrait inopérant) — on refuse et on le dit.
                print(
                    "Aucun taux USD→EUR connu (pbm_api.pricing.exchange_rates) : "
                    "le relevé BCE n'a pas tourné. Passage réel refusé (plafond sinon inopérant).",
                    file=sys.stderr,
                )
                return 2
            rapport = await runner.run(
                db,
                generateur=generateur,
                plafond_eur=plafond,
                rate_usd_eur=rate,
                model=args.model,
                ledger_path=ledger_path,
                limite=args.limite,
                priorite_tcgdex=priorite,
            )
    finally:
        await generateur.aclose()

    print(runner.rapport_texte(rapport))
    if args.rapport:
        Path(args.rapport).write_text(runner.rapport_texte(rapport), encoding="utf-8")
        print(f"Rapport par famille écrit dans {args.rapport}.")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Assistance IA pour les scripts d'effet (DJ8).")
    p.add_argument("--model", default=settings.assistance_model, help="modèle Anthropic")
    p.add_argument("--limite", type=int, default=100, help="nombre d'effets traités ce passage")
    p.add_argument(
        "--plafond-eur",
        type=float,
        default=settings.assistance_budget_eur,
        dest="plafond_eur",
        help="plafond de dépense cumulée en euros (défaut : réglage, 50 €)",
    )
    p.add_argument("--ledger", default=None, help="chemin du grand livre (reprise)")
    p.add_argument("--fichier-cle", default=None, dest="fichier_cle", help="fichier clé chmod 600")
    p.add_argument(
        "--factice",
        action="store_true",
        help="force le fournisseur factice (mesure sans dépense, DJ8)",
    )
    p.add_argument("--rapport", default=None, help="écrit le rapport par famille dans ce fichier")
    p.add_argument(
        "--priorite-possession",
        default=None,
        dest="priorite_possession",
        help=(
            "fichier JSON {tcgdex_id: [demandeurs, exemplaires]} extrait en lecture seule de la "
            "PROD (comptes game_access) : porte la priorité DJ2 au catalogue de référence, dont "
            "l'univers de sélection devient alors le catalogue entier"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : un passage d'assistance, plafonné et reprenable."""
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
