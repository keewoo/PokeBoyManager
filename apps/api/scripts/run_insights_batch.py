"""Lance un passage du lot `v4-insights-batch` (pré-génération des anecdotes/étude en jeu de
TOUTES les cartes, voir CLAUDE.md § « Insights par lots »). Cible la base pointée par
`DATABASE_URL` ; idempotent et reprenable (`pbm_api.insights_batch.runner.run_once`) — un
arrêt en cours de route ne perd rien, relancer ce script continue depuis le grand livre local
(`var/insights_batch/ledger.json`).

Sans `PLATFORM_ANTHROPIC_API_KEY` ni `INSIGHTS_BUDGET_EUR` positionnées (D4, à fournir par JF),
ce script refuse de dépenser quoi que ce soit — voir `pbm_api.insights_batch.runner.run_once`,
statut `pas_de_cle_plateforme`.

Usage :
    # Un passage (soumet un nouveau lot Anthropic, ou reprend celui déjà en cours) :
    PLATFORM_ANTHROPIC_API_KEY=sk-ant-... INSIGHTS_BUDGET_EUR=50 \
        uv run python scripts/run_insights_batch.py

    # Boucle jusqu'à couverture complète du catalogue ou budget épuisé (un passage peut prendre
    # jusqu'à une heure — la plupart des lots Anthropic finissent en moins de ça, voir
    # platform.claude.com/docs) :
    uv run python scripts/run_insights_batch.py --loop
"""

import asyncio
import sys
from datetime import UTC, datetime

from pbm_api.config import settings
from pbm_api.db import async_session_factory
from pbm_api.insights_batch.runner import run_once

# Statuts qui signifient "plus rien à faire maintenant" — la boucle --loop s'arrête là plutôt
# que de retenter indéfiniment un budget épuisé ou un taux de change manquant.
_TERMINAL_STATUSES = {
    "catalogue_couvert",
    "budget_epuise",
    "budget_insuffisant",
    "pas_de_cle_plateforme",
    "taux_de_change_indisponible",
}


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def _run_once() -> str:
    async with async_session_factory() as session:
        report = await run_once(session)
    _log(
        f"status={report.status} cartes_selectionnees={report.cards_selected} "
        f"cartes_appliquees={report.cards_applied} cartes_rejetees={report.cards_rejected} "
        f"anecdotes_hors_contexte={report.anecdotes_rejected_out_of_context} "
        f"cout_usd={report.cost_usd} cout_eur={report.cost_eur} "
        f"budget_restant_eur={report.budget_remaining_eur} batch_id={report.batch_id} "
        f"detail={report.detail!r}"
    )
    return report.status


async def main() -> None:
    loop_mode = "--loop" in sys.argv[1:]
    status = await _run_once()
    while loop_mode and status not in _TERMINAL_STATUSES:
        if status == "en_cours":
            # `run_once` a déjà sondé jusqu'à `insights_batch_poll_max_attempts` avant de
            # renvoyer "en_cours" — encore une pause ici avant de resonder, jamais en boucle
            # serrée contre l'API Anthropic.
            await asyncio.sleep(settings.insights_batch_poll_interval_seconds)
        status = await _run_once()
    if status in ("pas_de_cle_plateforme", "taux_de_change_indisponible", "budget_insuffisant"):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
