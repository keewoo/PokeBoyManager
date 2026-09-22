"""Mesure du coût moyen d'une proposition de deck par l'assistant IA (mission `v7-deck-ia`).

Fait un VRAI appel au fournisseur IA de l'utilisateur (aucune clé réelle sur chimera : ce script
ne tourne QUE sur un environnement disposant d'une clé — campagne UAT, compte de campagne, plafond
5 €, voir `~/.claude/CLAUDE.md`). Il refuse d'agir sans clé plutôt que d'estimer un coût à zéro.

Chaque proposition consomme des jetons : le script mesure l'entrée/sortie renvoyées par
`propose_deck` et, si le modèle est tarifé ici, l'euro correspondant. La table de prix est
vérifiée à une date donnée et doit être revérifiée avant tout passage réel (comme
`insights_batch/pricing.py`).

Exemple :

    UV_PYTHON=3.12 uv run python scripts/measure_deck_ia_cost.py \
        --email joueur@example.com --deck <deck_uuid> --runs 3 --types fire,water
"""

import argparse
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select

from pbm_api.ai.factory import create_provider
from pbm_api.db import async_session_factory
from pbm_api.decks.ai_builder import ProposalOptions, propose_deck
from pbm_api.models import User

# Tarifs STANDARD (hors remise Batch) $/Mtok — à revérifier sur https://claude.com/pricing.
_PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-4-5": (Decimal("1"), Decimal("5")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
}
_USD_PER_EUR = Decimal("1.08")  # ordre de grandeur, revérifier au besoin


def _cost_eur(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    if model not in _PRICING_USD_PER_MTOK:
        return None
    in_price, out_price = _PRICING_USD_PER_MTOK[model]
    usd = (Decimal(input_tokens) * in_price + Decimal(output_tokens) * out_price) / Decimal(
        1_000_000
    )
    return usd / _USD_PER_EUR


async def _run(email: str, deck_id: str, runs: int, types: list[str]) -> None:
    options = ProposalOptions(types=[(t, None) for t in types])
    total_in = total_out = 0
    total_eur = Decimal(0)
    priced = 0
    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"Utilisateur introuvable : {email}")
        if user.ai_default_provider is None:
            raise SystemExit(
                f"{email} n'a aucun fournisseur IA par défaut : impossible de mesurer un coût "
                "réel (le script refuse d'estimer à zéro)."
            )
        for i in range(runs):
            outcome = await propose_deck(
                session, user, uuid.UUID(deck_id), options, create_provider
            )
            total_in += outcome.input_tokens
            total_out += outcome.output_tokens
            eur = _cost_eur(outcome.model, outcome.input_tokens, outcome.output_tokens)
            price_txt = f"{eur:.4f} €" if eur is not None else "tarif inconnu"
            print(
                f"[{i + 1}/{runs}] {outcome.provider}:{outcome.model} — "
                f"in={outcome.input_tokens} out={outcome.output_tokens} — {price_txt}"
            )
            if eur is not None:
                total_eur += eur
                priced += 1

    print("—" * 60)
    print(f"Moyenne jetons : entrée {total_in / runs:.0f}, sortie {total_out / runs:.0f}")
    if priced:
        print(f"Coût moyen estimé : {total_eur / priced:.4f} € / proposition ({priced} tarifées)")
    else:
        print("Coût non chiffré : aucun modèle utilisé n'est présent dans la table de prix.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mesure le coût d'une proposition de deck IA.")
    parser.add_argument("--email", required=True, help="e-mail de l'utilisateur (avec clé IA)")
    parser.add_argument("--deck", required=True, help="UUID d'un deck existant de cet utilisateur")
    parser.add_argument("--runs", type=int, default=3, help="nombre de propositions à mesurer")
    parser.add_argument("--types", default="", help="types privilégiés, séparés par des virgules")
    args = parser.parse_args()
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    asyncio.run(_run(args.email, args.deck, args.runs, types))


if __name__ == "__main__":
    main()
