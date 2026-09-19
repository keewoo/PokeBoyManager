"""Registre local de dépense cumulée et de reprise — mission point 2 : « le traitement s'arrête
proprement avant de [dépasser le budget] et le dit ». Un fichier JSON (pas une table : ce lot
n'expose aucune route HTTP, c'est un script/cron opéré depuis chimera, voir
`scripts/run_insights_batch.py`) plutôt qu'une estimation en mémoire à chaque lancement — le
budget est cumulatif sur tous les passages, y compris ceux d'hier.

`in_flight_batch` porte le lot Anthropic actuellement soumis mais pas encore récupéré : un
lancement interrompu entre la soumission et la récupération reprend ce lot précis au lieu d'en
resoumettre un second (double dépense) au prochain lancement.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_LEDGER_PATH = Path("var/insights_batch/ledger.json")


@dataclass
class InFlightBatch:
    batch_id: str
    model: str
    # Taux USD->EUR utilisé au moment de la soumission (`pbm_api.pricing.exchange_rates`) —
    # réutilisé tel quel au moment de comptabiliser le coût réel : la soumission a déjà vérifié
    # qu'un taux existait (fail-closed, jamais un taux à 0 inventé), pas besoin d'en chercher un
    # autre à la reprise, qui pourrait être manquant ce jour-là.
    usd_to_eur_rate: str
    # {custom_id: card_id} — rapprochement des résultats (ordre non garanti par Anthropic).
    custom_id_to_card_id: dict[str, str]
    # {custom_id: [source_url, ...]} — mêmes URLs de contexte que celles données au modèle pour
    # cette carte, conservées ici (pas seulement en mémoire du processus qui a soumis le lot) :
    # une reprise après redémarrage doit pouvoir revalider qu'aucune anecdote ne cite une URL
    # hors contexte, la même défense en profondeur que `pbm_api.insights.service`.
    allowed_urls: dict[str, list[str]]


@dataclass
class Ledger:
    total_spent_usd: str = "0"
    total_spent_eur: str = "0"
    cards_processed: int = 0
    runs: list[dict] = field(default_factory=list)
    in_flight_batch: InFlightBatch | None = None
    # `batch_id` des lots déjà comptabilisés — une reprise qui retrouve un lot déjà appliqué
    # (crash entre l'écriture en base et la levée de `in_flight_batch`) rejoue l'écriture
    # (idempotente) sans recompter son coût une seconde fois.
    completed_batch_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_json(cls, data: dict) -> "Ledger":
        in_flight_data = data.get("in_flight_batch")
        in_flight = InFlightBatch(**in_flight_data) if in_flight_data else None
        return cls(
            total_spent_usd=data.get("total_spent_usd", "0"),
            total_spent_eur=data.get("total_spent_eur", "0"),
            cards_processed=data.get("cards_processed", 0),
            runs=data.get("runs", []),
            in_flight_batch=in_flight,
            completed_batch_ids=data.get("completed_batch_ids", []),
        )


def load_ledger(path: Path = DEFAULT_LEDGER_PATH) -> Ledger:
    if not path.exists():
        return Ledger()
    return Ledger.from_json(json.loads(path.read_text()))


def save_ledger(ledger: Ledger, path: Path = DEFAULT_LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger.to_json(), indent=2, ensure_ascii=False))
