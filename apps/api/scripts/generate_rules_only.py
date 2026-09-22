"""Génération RÈGLES SEULES pour les cartes SANS fiche — lot `pbm-fiches-reste` (22/09).

Le ciblage 80 % (`pbm-insights-ciblage-large`) a laissé 4 434 cartes sans fiche (surtout Communes,
Peu communes, Rares). Décision de JF : les couvrir **sans anecdotes, avec seulement les règles de
jeu**. Ce driver reprend le pipeline `insights_batch` (Message Batches API, −50 %, groupage par
extension, anti-mélange par `card_ref`) en mode réduit :

  * AUCUNE source wiki n'est récupérée — c'est ce qui coûtait ≈1 750 jetons d'entrée/carte au lot
    précédent (lecture des pages pour sourcer les anecdotes). Estimation JF : 2 à 4 €.
  * Le prompt et le schéma sont ceux de `large_generation.build_rules_only_prompt` /
    `RULES_ONLY_JSON_SCHEMA` : un texte `game_rules` par carte, rien d'autre. Le modèle met en
    forme les données de jeu du catalogue (attaques, coûts, talents, faiblesses, légalités, règle
    des Prix), il n'invente rien.
  * La sortie TSV a le MÊME format que le lot précédent (import inchangé,
    `infra/fleet/import_insights.sql`) : la colonne `anecdotes` vaut `[]` (cache négatif frais —
    l'onglet « anecdotes » reste vide sans appel IA, à remplir plus tard si JF le décide), et
    `in_game_study` porte les règles de jeu (lues par l'onglet « En jeu », sans appel IA).

Tourne sur **devAI** (la clé personnelle d'Aymeric ne quitte pas cette machine — chimera n'a
aucune clé) ; le seul « lourd » réellement proscrit est la machine qui SERT (`kailo-srv`/PROD),
pleinement respecté. Clé lue depuis un fichier chmod 600 (`--key-file`), JAMAIS journalisée, ni
passée en argument, ni en variable visible par `ps`.

Plafond DUR `--budget-eur` (15 € pour ce lot) : arrêt net au-delà, ce qui est produit est gardé,
grand livre de reprise (aucune double facturation, aucune carte regénérée). Aucun repli silencieux
(`CLAUDE.md`) : un paquet perdu ou une carte non écrite est compté et journalisé, jamais avalé.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pbm_api.ingame.rules import prize_rule_of
from pbm_api.insights_batch.anthropic_batches import (
    AnthropicBatchClient,
    BatchApiError,
    build_batch_request,
)
from pbm_api.insights_batch.large_generation import (
    RULES_ONLY_JSON_SCHEMA,
    RULES_ONLY_PROMPT_VERSION,
    PacketCard,
    PacketMixingError,
    ValidationError,
    build_rules_only_prompt,
    parse_rules_only_result,
)
from pbm_api.insights_batch.pricing import batch_cost_usd
from pbm_api.pricing.exchange_rates import convert_to_eur

# Règles seules : moins de sortie que 2 anecdotes + règles. Borne haute prudente par carte.
_OUT_TOKENS_PER_CARD = 300
_ESTIMATED_CHARS_PER_TOKEN = 4
# Cache positif 180 j pour les deux volets (contenu catalogue stable), aligné sur le lot précédent
# — une fiche règles-seules reste « fraîche » aussi longtemps qu'une fiche complète.
_CACHE_DAYS = 180


def _pricing_key(model: str) -> str:
    """Tarif indexé sur l'alias sans date (`claude-haiku-4-5`) ; l'API accepte l'id épinglé."""
    return re.sub(r"-\d{8}$", "", model)


# --------------------------------------------------------------------------- journalisation


class Logger:
    def __init__(self, progress_path: Path) -> None:
        self.progress_path = progress_path

    def __call__(self, message: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}"
        print(line, flush=True)
        with self.progress_path.open("a") as handle:
            handle.write(line + "\n")


# --------------------------------------------------------------------------- chargement + reprise


def load_catalog(path: Path) -> list[dict]:
    cards = json.loads(path.read_text())
    return [c for c in cards if c.get("tcgdex_id")]


def load_done_tcgdex(path: Path) -> set[str]:
    """tcgdex_id déjà présents dans un TSV `card_insights` (première colonne)."""
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if row:
                done.add(row[0])
    return done


# --------------------------------------------------------------------------- grand livre / reprise


@dataclass
class Ledger:
    path: Path
    total_spent_usd: str = "0"
    total_spent_eur: str = "0"
    completed_batch_ids: list[str] = field(default_factory=list)
    cards_written: int = 0

    @classmethod
    def load(cls, path: Path) -> Ledger:
        if path.exists():
            d = json.loads(path.read_text())
            return cls(
                path=path,
                total_spent_usd=d["total_spent_usd"],
                total_spent_eur=d["total_spent_eur"],
                completed_batch_ids=d.get("completed_batch_ids", []),
                cards_written=d.get("cards_written", 0),
            )
        return cls(path=path)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "total_spent_usd": self.total_spent_usd,
                    "total_spent_eur": self.total_spent_eur,
                    "completed_batch_ids": self.completed_batch_ids,
                    "cards_written": self.cards_written,
                }
            )
        )
        tmp.replace(self.path)

    @property
    def spent_eur(self) -> Decimal:
        return Decimal(self.total_spent_eur)


# --------------------------------------------------------------------------- construction paquets


def _packet_card(card: dict, ref: str) -> PacketCard:
    prize = prize_rule_of(card_name=card["name"], supertype=card.get("supertype"))
    return PacketCard(
        card_ref=ref,
        card_name=card["name"],
        card_pages=[],  # règles seules : aucun contexte wiki
        supertype=card.get("supertype"),
        legal_standard=card.get("legal_standard"),
        legal_expanded=card.get("legal_expanded"),
        prize_label=prize.label,
        rule_marker=card.get("rule_marker"),
        hp=card.get("hp"),
        retreat_cost=card.get("retreat_cost"),
        attacks=card.get("attacks"),
        abilities=card.get("abilities"),
        weaknesses=card.get("weaknesses"),
        resistances=card.get("resistances"),
    )


@dataclass
class Packet:
    custom_id: str
    request: dict
    ref_to_tcgdex: dict[str, str]
    ref_to_name: dict[str, str]
    estimated_input_tokens: int
    card_count: int


def build_packets(cards: list[dict], *, model: str, packet_size: int, tag: str) -> list[Packet]:
    """Groupe par extension (l'en-tête d'instructions est partagé une fois par paquet) et découpe
    en paquets de `packet_size` cartes."""
    by_set: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for card in cards:
        s = card["set_tcgdex_id"]
        if s not in by_set:
            order.append(s)
        by_set[s].append(card)

    packets: list[Packet] = []
    pkt_idx = 0
    for s in order:
        set_cards = by_set[s]
        set_name = set_cards[0].get("set_name") or ""
        for chunk_idx in range(0, len(set_cards), packet_size):
            chunk = set_cards[chunk_idx : chunk_idx + packet_size]
            packet_cards: list[PacketCard] = []
            ref_to_tcgdex: dict[str, str] = {}
            ref_to_name: dict[str, str] = {}
            for i, card in enumerate(chunk, start=1):
                ref = f"c{i}"
                packet_cards.append(_packet_card(card, ref))
                ref_to_tcgdex[ref] = card["tcgdex_id"]
                ref_to_name[ref] = card["name"]
            prompt = build_rules_only_prompt(set_name=set_name, cards=packet_cards)
            # custom_id Anthropic ^[a-zA-Z0-9_-]{1,64}$ : un INDEX simple (le set_tcgdex_id peut
            # contenir un point, ex "me02.5"), le rapprochement passe par `packets_by_id`.
            custom_id = f"{tag}-{pkt_idx}"
            pkt_idx += 1
            max_tokens = min(64000, _OUT_TOKENS_PER_CARD * len(chunk) + 800)
            request = build_batch_request(
                custom_id=custom_id,
                model=model,
                max_tokens=max_tokens,
                prompt=prompt,
                json_schema=RULES_ONLY_JSON_SCHEMA,
            )
            packets.append(
                Packet(
                    custom_id=custom_id,
                    request=request,
                    ref_to_tcgdex=ref_to_tcgdex,
                    ref_to_name=ref_to_name,
                    estimated_input_tokens=len(prompt) // _ESTIMATED_CHARS_PER_TOKEN,
                    card_count=len(chunk),
                )
            )
    return packets


# --------------------------------------------------------------------------- écriture sortie


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def write_rows(output_path: Path, rows: list[dict], model: str) -> None:
    """Ajoute des lignes `card_insights` (clé tcgdex_id) au TSV — même format que le lot précédent
    (`infra/fleet/import_insights.sql`, FORMAT csv, DELIMITER tab, NULL ''). La colonne `anecdotes`
    vaut `[]` (aucune anecdote pour ces cartes — cache négatif frais)."""
    marker = f"anthropic:{_pricing_key(model)}:batch:{RULES_ONLY_PROMPT_VERSION}"
    now = _now_naive()
    until = now + timedelta(days=_CACHE_DAYS)
    now_s = now.isoformat(sep=" ")
    until_s = until.isoformat(sep=" ")
    with output_path.open("a", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for r in rows:
            writer.writerow(
                [
                    r["tcgdex_id"],
                    "[]",  # anecdotes vides (JSON), jamais NULL : cache négatif explicite
                    r["game_rules"],
                    marker,
                    now_s,
                    until_s,
                    marker,
                    now_s,
                    until_s,
                ]
            )


# ------------------------------------------------------------------------- soumission + application


@dataclass
class BatchOutcome:
    failed_packets: list[str] = field(default_factory=list)
    failure_reasons: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    errored_requests: int = 0


async def _run_batch(
    client: AnthropicBatchClient,
    requests: list[dict],
    label: str,
    log: Logger,
    poll_interval: int,
    max_wait: int,
):
    status = await client.create_batch(requests)
    log(f"[{label}] lot soumis {status.batch_id} ({len(requests)} requêtes)")
    waited = 0
    while True:
        st = await client.get_batch(status.batch_id)
        if st.processing_status == "ended":
            log(f"[{label}] terminé : {st.request_counts}")
            return status.batch_id, await client.iter_results(st.results_url or "")
        if waited >= max_wait:
            raise BatchApiError(
                f"[{label}] toujours en traitement après {max_wait}s (batch {status.batch_id})"
            )
        await asyncio.sleep(poll_interval)
        waited += poll_interval


def _apply_results(results, packets_by_id: dict[str, Packet]) -> tuple[list[dict], BatchOutcome]:
    outcome = BatchOutcome()
    rows: list[dict] = []
    for r in results:
        outcome.input_tokens += r.input_tokens
        outcome.output_tokens += r.output_tokens
        packet = packets_by_id.get(r.custom_id)
        if packet is None:
            continue
        if r.result_type != "succeeded" or r.text is None:
            outcome.errored_requests += 1
            outcome.failed_packets.append(r.custom_id)
            reason = f"errored:{r.result_type}"
            outcome.failure_reasons[reason] = outcome.failure_reasons.get(reason, 0) + 1
            continue
        try:
            parsed = parse_rules_only_result(
                r.text,
                list(packet.ref_to_tcgdex.keys()),
                card_names_by_ref=packet.ref_to_name,
            )
        except (ValidationError, PacketMixingError) as exc:
            outcome.failed_packets.append(r.custom_id)
            reason = type(exc).__name__
            outcome.failure_reasons[reason] = outcome.failure_reasons.get(reason, 0) + 1
            continue
        for ref, insight in parsed.items():
            rows.append(
                {"tcgdex_id": packet.ref_to_tcgdex[ref], "game_rules": insight.game_rules}
            )
    return rows, outcome


def _record_spend(
    ledger: Ledger, batch_id: str, model: str, outcome: BatchOutcome, rate: Decimal
) -> tuple[Decimal, Decimal]:
    cost_usd = batch_cost_usd(
        _pricing_key(model), input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens
    )
    cost_eur = convert_to_eur(cost_usd, rate)
    if batch_id not in ledger.completed_batch_ids:
        ledger.total_spent_usd = str(Decimal(ledger.total_spent_usd) + cost_usd)
        ledger.total_spent_eur = str(Decimal(ledger.total_spent_eur) + cost_eur)
        ledger.completed_batch_ids.append(batch_id)
    return cost_usd, cost_eur


# --------------------------------------------------------------------------- pilotage principal


async def generate(args: argparse.Namespace, api_key: str, log: Logger) -> None:
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    ledger = Ledger.load(work / "ledger.json")
    rate = Decimal(str(args.usd_to_eur_rate))
    budget = Decimal(str(args.budget_eur))
    model = args.model

    cards = load_catalog(Path(args.catalog))
    catalog_ids = {c["tcgdex_id"] for c in cards}

    # Reprise : cartes DÉJÀ couvertes = celles écrites par le lot précédent (`--done-from`) plus
    # celles déjà écrites par CE passage (`--output`), pour ne jamais regénérer.
    prior_done = load_done_tcgdex(Path(args.done_from)) if args.done_from else set()
    already_written = load_done_tcgdex(output_path)
    done = (prior_done | already_written) & catalog_ids
    covered_prior = len(prior_done & catalog_ids)

    # Ordre par extension (cohérence des paquets), puis par numéro à l'intérieur.
    worklist = [c for c in cards if c["tcgdex_id"] not in done]
    worklist.sort(
        key=lambda c: (c.get("set_tcgdex_id") or "", c.get("number") or "", c["tcgdex_id"])
    )
    if args.max_cards is not None:
        worklist = worklist[: args.max_cards]

    log(
        f"=== RÈGLES SEULES démarrée — catalogue={len(cards)} déjà couvertes={covered_prior} "
        f"restantes={len(cards) - covered_prior} à traiter ce passage={len(worklist)} "
        f"budget={budget}€ modèle={_pricing_key(model)} paquet={args.packet_size} ==="
    )
    log(
        f"reprise : {len(already_written)} déjà écrites par ce lot, "
        f"dépense cumulée {ledger.spent_eur:.4f}€"
    )

    # Comptage par catégorie (traçabilité de la répartition Pokémon / Dresseur / Énergie).
    by_super: dict[str, int] = defaultdict(int)
    for c in worklist:
        by_super[c.get("supertype") or "inconnu"] += 1
    log(f"répartition à traiter : {dict(by_super)}")

    if not worklist:
        log("rien à faire — toutes les cartes du catalogue ont déjà une fiche. Arrêt.")
        return

    retry_counts: dict[str, int] = defaultdict(int)
    chunk_cards = args.chunk_cards
    idx = 0
    stopped_reason = "toutes les cartes restantes traitées"
    while idx < len(worklist):
        if ledger.spent_eur >= budget:
            stopped_reason = f"budget atteint ({ledger.spent_eur:.4f}€ ≥ {budget}€)"
            break
        chunk = worklist[idx : idx + chunk_cards]
        idx += len(chunk)

        packets = build_packets(
            chunk, model=model, packet_size=args.packet_size, tag=f"ro{args.packet_size}"
        )

        kept: list[Packet] = []
        est_eur = Decimal("0")
        for p in packets:
            proj = batch_cost_usd(
                _pricing_key(model),
                input_tokens=p.estimated_input_tokens,
                output_tokens=_OUT_TOKENS_PER_CARD * p.card_count,
            )
            proj_eur = convert_to_eur(proj, rate)
            if ledger.spent_eur + est_eur + proj_eur > budget:
                stopped_reason = f"budget atteint (estimation) à {ledger.spent_eur + est_eur:.4f}€"
                break
            kept.append(p)
            est_eur += proj_eur
        if not kept:
            break

        packets_by_id = {p.custom_id: p for p in kept}
        client = AnthropicBatchClient(api_key)
        try:
            batch_id, results = await _run_batch(
                client, [p.request for p in kept], f"chunk@{idx}", log,
                args.poll_interval, args.max_wait,
            )
            rows, outcome = _apply_results(results, packets_by_id)

            # RÉ-ESSAI carte par carte des paquets en échec (jamais perdus en silence).
            failed_cards: list[dict] = []
            for cid in outcome.failed_packets:
                p = packets_by_id[cid]
                for tid in p.ref_to_tcgdex.values():
                    if retry_counts[tid] < 1:
                        retry_counts[tid] += 1
                        card = next((c for c in chunk if c["tcgdex_id"] == tid), None)
                        if card is not None:
                            failed_cards.append(card)
            if outcome.failed_packets:
                log(
                    f"[chunk@{idx}] {len(outcome.failed_packets)} paquet(s) en échec "
                    f"{dict(outcome.failure_reasons)} → ré-essai carte par carte de "
                    f"{len(failed_cards)} carte(s)"
                )
            if failed_cards:
                retry_packets = build_packets(failed_cards, model=model, packet_size=1, tag="ror1")
                retry_by_id = {p.custom_id: p for p in retry_packets}
                rb_id, rresults = await _run_batch(
                    client, [p.request for p in retry_packets], f"retry@{idx}", log,
                    args.poll_interval, args.max_wait,
                )
                rrows, routcome = _apply_results(rresults, retry_by_id)
                rows += rrows
                outcome.input_tokens += routcome.input_tokens
                outcome.output_tokens += routcome.output_tokens
                _record_spend(ledger, rb_id, model, routcome, rate)
                still_failed = [
                    p.ref_to_tcgdex["c1"]
                    for cid, p in retry_by_id.items()
                    if cid in routcome.failed_packets
                ]
                if still_failed:
                    log(
                        f"[retry@{idx}] {len(still_failed)} carte(s) toujours en échec après "
                        f"ré-essai {dict(routcome.failure_reasons)} — laissées candidates : "
                        f"{still_failed[:10]}..."
                    )
        finally:
            await client.aclose()

        if rows:
            write_rows(output_path, rows, model)
            ledger.cards_written += len(rows)
        cost_usd, cost_eur = _record_spend(ledger, batch_id, model, outcome, rate)
        ledger.save()
        log(
            f"[chunk@{idx}] écrites={len(rows)} cumul_cartes={ledger.cards_written} "
            f"in={outcome.input_tokens} out={outcome.output_tokens} "
            f"coût_lot≈{cost_eur:.4f}€ CUMUL={ledger.spent_eur:.4f}€/{budget}€"
        )

    written_total = len(load_done_tcgdex(output_path))
    covered_total = covered_prior + written_total
    log(
        f"=== RÈGLES SEULES terminée — {stopped_reason} — écrites ce lot={written_total} "
        f"couverture catalogue={covered_total}/{len(cards)} ({covered_total / len(cards):.1%}) "
        f"dépense={ledger.spent_eur:.4f}€ ==="
    )


# --------------------------------------------------------------------------- CLI


def _read_key(path: Path) -> str:
    key = path.read_text().strip()
    if not key:
        raise SystemExit(f"clé vide dans {path}")
    return key


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key-file", required=True, help="fichier chmod 600 contenant la clé Anthropic")
    p.add_argument(
        "--catalog", required=True, help="catalog_full.json exporté de pbm_catalogue_ref"
    )
    p.add_argument(
        "--done-from",
        default=None,
        help="TSV du lot précédent (tcgdex_id col 0) : cartes déjà couvertes, jamais regénérées",
    )
    p.add_argument("--work-dir", required=True, help="répertoire d'état (grand livre)")
    p.add_argument("--output", required=True, help="TSV de sortie card_insights")
    p.add_argument("--progress", default=str(Path.home() / "dev/logs/pbm-insights-progres.log"))
    p.add_argument("--budget-eur", type=float, default=15.0)
    p.add_argument("--packet-size", type=int, default=25)
    p.add_argument(
        "--chunk-cards", type=int, default=20000, help="un seul gros lot (anti-engorgement)"
    )
    p.add_argument(
        "--max-cards", type=int, default=None, help="borne de tranche : au plus N ce passage"
    )
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--usd-to-eur-rate", type=float, default=1.146)
    p.add_argument("--poll-interval", type=int, default=15)
    p.add_argument("--max-wait", type=int, default=72000, help="20 h (SLA Batch 24 h)")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    log = Logger(Path(args.progress))
    api_key = _read_key(Path(args.key_file))
    asyncio.run(generate(args, api_key, log))


if __name__ == "__main__":
    main()
