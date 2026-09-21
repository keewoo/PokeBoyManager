"""Génération des fiches (2 anecdotes FR + règles de jeu) sur ~80 % du catalogue —
lot `pbm-insights-ciblage-large`.

Tourne sur **devAI** : la clé personnelle d'Aymeric NE QUITTE PAS cette machine (décision de la
session de mesure — chimera n'a aucune clé). Le seul « lourd » réellement interdit est la machine
qui SERT (`kailo-srv`), pleinement respecté ici. La clé est lue depuis un fichier chmod 600
(`--key-file`) et n'est JAMAIS journalisée, ni passée en argument, ni en variable visible par `ps`.

Pipeline :
  1. charge le catalogue exporté de `pbm_catalogue_ref` (JSON) et la liste des cartes possédées ;
  2. ordonne les cartes par PRIORITÉ (voir `build_priority`) et coupe à la cible (80 % / budget) ;
  3. collecte le contexte wiki (extension partagée + carte), mis en cache par REQUÊTE (une même
     carte/extension n'est demandée qu'une fois aux wikis), rythme raisonnable + User-Agent ;
  4. groupe par extension en paquets, soumet des lots Anthropic (Message Batches, -50 %) avec le
     schéma réduit `large_generation.LARGE_JSON_SCHEMA` ;
  5. applique les résultats (anti-mélange par `card_ref`), écrit une ligne `card_insights` par
     carte dans un TSV clé `tcgdex_id` (import PROD par jointure) ; un paquet en échec est
     RÉ-ESSAYÉ carte par carte plutôt que perdu ;
  6. compte la dépense RÉELLE (jetons facturés × tarif Batch) au fil de l'eau, s'arrête net à
     `--budget-eur`, tient un grand livre pour la reprise (rien n'est recalculé deux fois).

Mode `--measure` : soumet un échantillon à une (ou plusieurs) taille(s) de paquet, mesure le coût
par carte et le taux d'échec de paquet, extrapole à la cible, N'ÉCRIT AUCUNE fiche — sert à
choisir la taille de paquet et confirmer que 80 % tient sous le budget AVANT la grande dépense.

Aucun repli silencieux (`~/.claude/CLAUDE.md`) : un paquet perdu, un contexte vide ou une carte
non écrite est compté et journalisé, jamais avalé.
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
from pbm_api.insights.context import (
    BULBAPEDIA_API_URL,
    POKEPEDIA_API_URL,
    ContextPage,
    MediaWikiClient,
)
from pbm_api.insights_batch.anthropic_batches import (
    AnthropicBatchClient,
    BatchApiError,
    build_batch_request,
)
from pbm_api.insights_batch.large_generation import (
    LARGE_JSON_SCHEMA,
    LARGE_PROMPT_VERSION,
    MAX_ANECDOTES,
    PacketCard,
    PacketMixingError,
    ValidationError,
    allowed_urls_for,
    build_large_prompt,
    parse_large_result,
)
from pbm_api.insights_batch.pricing import batch_cost_usd
from pbm_api.pricing.exchange_rates import convert_to_eur

FULL_CATALOG = 22169
_WIKI_COURTESY_SLEEP = 0.20  # rythme raisonnable envers Poképédia/Bulbapedia (mission « qualité »)
_WIKI_CONCURRENCY = 6
# Cache positif : une fiche pré-générée reste « fraîche » longtemps (contenu catalogue stable —
# attaques, légalités — et anecdotes sourcées). 180 jours pour les DEUX volets, à la différence
# du chemin à la demande (`ingame.service` = 30 j, calé sur la présence en tournoi qui peut
# changer) : ces règles de jeu-ci sont catalogue, pas tournoi. Choix propre à ce lot, documenté.
_CACHE_DAYS = 180
# Budget de sortie par carte (jetons) : 2 anecdotes courtes + règles de jeu ≈ bien moins que
# l'ancien contenu riche ; borne haute prudente, Haiku 4.5 plafonne à 64k.
_OUT_TOKENS_PER_CARD = 450
_ESTIMATED_CHARS_PER_TOKEN = 4


def _pricing_key(model: str) -> str:
    """Le tarif est indexé sur l'alias sans date (`claude-haiku-4-5`) ; l'API accepte l'id épinglé
    (`claude-haiku-4-5-20251001`). On retire un suffixe de date pour retrouver le tarif."""
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


# --------------------------------------------------------------------------- chargement + priorité


def load_catalog(path: Path) -> list[dict]:
    cards = json.loads(path.read_text())
    return [c for c in cards if c.get("tcgdex_id")]


def load_owned(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def _release_key(card: dict) -> str:
    # Tri par récence d'extension : date de sortie décroissante (les plus récentes d'abord).
    return card.get("set_release_date") or "0000-00-00"


def _value(card: dict) -> Decimal:
    v = card.get("value_proxy")
    return Decimal(str(v)) if v is not None else Decimal("-1")


def build_priority(
    cards: list[dict], owned: set[str], *, top_expensive: int
) -> tuple[list[dict], dict[str, int]]:
    """Ordre de priorité (décisions de JF) :
      (a) toutes les cartes POSSÉDÉES — doivent être couvertes à 100 % ;
      (c) les plus CHÈRES — les `top_expensive` premières par valeur (proxy prix, toutes cartes) ;
      (b) EXTENSIONS RÉCENTES puis complément par extension — le reste, par extension triée par
          date de sortie décroissante, toutes les cartes d'une extension ensemble (préserve le
          groupage à contexte partagé) ;
      (d) les plus CONSULTÉES — AUCUNE source de données en PROD (pas de table d'analytics au
          21/09), tier vide et documenté.

    Renvoie (liste ordonnée sans doublon, compteur par tier)."""
    by_id = {c["tcgdex_id"]: c for c in cards}
    seen: set[str] = set()
    ordered: list[dict] = []
    tiers = {"possedees": 0, "cheres": 0, "recentes_et_complement": 0}

    # (a) possédées d'abord (dans l'ordre donné, cartes réellement présentes au catalogue)
    for tid in sorted(owned):
        card = by_id.get(tid)
        if card is not None and tid not in seen:
            ordered.append(card)
            seen.add(tid)
            tiers["possedees"] += 1

    # (c) les plus chères ensuite (hors déjà vues)
    remaining = [c for c in cards if c["tcgdex_id"] not in seen]
    remaining.sort(key=_value, reverse=True)
    for card in remaining[:top_expensive]:
        if _value(card) <= 0:
            break  # pas de prix => pas « chère » ; laisse au tier récence/complément
        ordered.append(card)
        seen.add(card["tcgdex_id"])
        tiers["cheres"] += 1

    # (b) extensions récentes + complément : le reste, groupé par extension (récence décroissante)
    rest = [c for c in cards if c["tcgdex_id"] not in seen]
    rest.sort(key=lambda c: (_release_key(c), c.get("set_tcgdex_id") or ""), reverse=True)
    # tri stable : cartes d'une même extension déjà contiguës par la clé ci-dessus, on garde
    # l'ordre par numéro à l'intérieur pour une progression lisible
    by_set: dict[str, list[dict]] = defaultdict(list)
    set_order: list[str] = []
    for card in rest:
        s = card.get("set_tcgdex_id") or ""
        if s not in by_set:
            set_order.append(s)
        by_set[s].append(card)
    for s in set_order:
        for card in by_set[s]:
            ordered.append(card)
            seen.add(card["tcgdex_id"])
            tiers["recentes_et_complement"] += 1

    return ordered, tiers


# --------------------------------------------------------------------------- contexte wiki


@dataclass
class ContextCache:
    """Cache par REQUÊTE (wiki, query) — corrige le cache par carte de la mesure : 50 cartes
    « Pikachu » = UNE requête « Pikachu », pas cinquante."""

    path: Path
    data: dict[str, dict[str, list[dict] | None]] = field(default_factory=dict)

    def load(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        self.data.setdefault(POKEPEDIA_API_URL, {})
        self.data.setdefault(BULBAPEDIA_API_URL, {})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data))
        tmp.replace(self.path)

    def get(self, wiki: str, query: str) -> list[ContextPage] | None:
        raw = self.data.get(wiki, {}).get(query, "__MISS__")
        if raw == "__MISS__":
            return None
        return [ContextPage(**p) for p in (raw or [])]

    def has(self, wiki: str, query: str) -> bool:
        return query in self.data.get(wiki, {})

    def put(self, wiki: str, query: str, pages: list[ContextPage]) -> None:
        self.data.setdefault(wiki, {})[query] = [p.model_dump() for p in pages]


async def _fetch_one(
    client: MediaWikiClient, wiki: str, query: str, cache: ContextCache, sem: asyncio.Semaphore
) -> None:
    if cache.has(wiki, query):
        return
    async with sem:
        page = await client.fetch_page(query)
        await asyncio.sleep(_WIKI_COURTESY_SLEEP)
    cache.put(wiki, query, [page] if page is not None else [])


async def gather_context(
    cards: list[dict], cache: ContextCache, log: Logger
) -> tuple[dict[str, list[ContextPage]], dict[str, list[ContextPage]]]:
    """Renvoie (set_pages_by_set_tcgdex, card_pages_by_card_tcgdex). Contexte d'extension collecté
    une fois par extension, contexte de carte une fois par (nom | nom EN) — via le cache requête."""
    pokepedia = MediaWikiClient(POKEPEDIA_API_URL)
    bulbapedia = MediaWikiClient(BULBAPEDIA_API_URL)
    sem = asyncio.Semaphore(_WIKI_CONCURRENCY)

    # Requêtes uniques à résoudre
    set_names = {c["set_name"] for c in cards if c.get("set_name")}
    card_names = {c["name"] for c in cards if c.get("name")}
    en_names = {c["en_name"] for c in cards if c.get("en_name")}

    to_fetch: list[tuple[MediaWikiClient, str, str]] = []
    for name in set_names:
        to_fetch.append((pokepedia, POKEPEDIA_API_URL, name))
        to_fetch.append((bulbapedia, BULBAPEDIA_API_URL, name))
    for name in card_names:
        to_fetch.append((pokepedia, POKEPEDIA_API_URL, name))
    for name in en_names:
        to_fetch.append((bulbapedia, BULBAPEDIA_API_URL, name))

    pending = [(c, w, q) for (c, w, q) in to_fetch if not cache.has(w, q)]
    log(f"contexte : {len(pending)} requêtes wiki à résoudre "
        f"({len(to_fetch)} au total, reste en cache)")
    try:
        done = 0
        for i in range(0, len(pending), 200):
            chunk = pending[i : i + 200]
            await asyncio.gather(*(_fetch_one(c, w, q, cache, sem) for (c, w, q) in chunk))
            cache.save()
            done += len(chunk)
            log(f"contexte : {done}/{len(pending)} requêtes résolues")
    finally:
        await pokepedia.aclose()
        await bulbapedia.aclose()
        cache.save()

    def _dedup(pages: list[ContextPage]) -> list[ContextPage]:
        seen: set[str] = set()
        out: list[ContextPage] = []
        for p in pages:
            if p.source_url not in seen:
                out.append(p)
                seen.add(p.source_url)
        return out

    set_pages: dict[str, list[ContextPage]] = {}
    for card in cards:
        s = card["set_tcgdex_id"]
        if s in set_pages:
            continue
        name = card.get("set_name")
        pages = (cache.get(POKEPEDIA_API_URL, name) or []) + (
            cache.get(BULBAPEDIA_API_URL, name) or []
        )
        set_pages[s] = _dedup(pages)

    card_pages: dict[str, list[ContextPage]] = {}
    for card in cards:
        pages = list(cache.get(POKEPEDIA_API_URL, card.get("name")) or [])
        if card.get("en_name"):
            pages += cache.get(BULBAPEDIA_API_URL, card["en_name"]) or []
        card_pages[card["tcgdex_id"]] = _dedup(pages)

    return set_pages, card_pages


# --------------------------------------------------------------------------- construction paquets


def _packet_card(card: dict, ref: str, card_pages: list[ContextPage]) -> PacketCard:
    prize = prize_rule_of(card_name=card["name"], supertype=card.get("supertype"))
    return PacketCard(
        card_ref=ref,
        card_name=card["name"],
        card_pages=card_pages,
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
    allowed_by_ref: dict[str, set[str]]
    ref_to_name: dict[str, str]  # cN -> nom de carte : tolérance de libellé au parsing
    estimated_input_tokens: int
    card_count: int


def build_packets(
    cards: list[dict],
    set_pages: dict[str, list[ContextPage]],
    card_pages: dict[str, list[ContextPage]],
    *,
    model: str,
    packet_size: int,
    tag: str,
) -> list[Packet]:
    """Groupe par extension (contexte partagé envoyé une fois par paquet)."""
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
        for chunk_idx in range(0, len(set_cards), packet_size):
            chunk = set_cards[chunk_idx : chunk_idx + packet_size]
            packet_cards: list[PacketCard] = []
            ref_to_tcgdex: dict[str, str] = {}
            allowed_by_ref: dict[str, set[str]] = {}
            ref_to_name: dict[str, str] = {}
            for i, card in enumerate(chunk, start=1):
                ref = f"c{i}"
                pc = _packet_card(card, ref, card_pages.get(card["tcgdex_id"], []))
                packet_cards.append(pc)
                ref_to_tcgdex[ref] = card["tcgdex_id"]
                allowed_by_ref[ref] = allowed_urls_for(set_pages.get(s, []), pc)
                ref_to_name[ref] = card["name"]
            prompt = build_large_prompt(
                set_name=set_cards[0].get("set_name") or "", set_pages=set_pages.get(s, []),
                cards=packet_cards,
            )
            # custom_id Anthropic : ^[a-zA-Z0-9_-]{1,64}$ — un INDEX simple (le set_tcgdex_id
            # contient parfois un point, ex "me02.5"/"swsh10.5", interdit ici) ; le mappage
            # résultat→paquet passe par le dict `packets_by_id`, pas par le contenu du custom_id.
            custom_id = f"{tag}-{pkt_idx}"
            pkt_idx += 1
            max_tokens = min(64000, _OUT_TOKENS_PER_CARD * len(chunk) + 1200)
            request = build_batch_request(
                custom_id=custom_id, model=model, max_tokens=max_tokens,
                prompt=prompt, json_schema=LARGE_JSON_SCHEMA,
            )
            packets.append(Packet(
                custom_id=custom_id, request=request, ref_to_tcgdex=ref_to_tcgdex,
                allowed_by_ref=allowed_by_ref, ref_to_name=ref_to_name,
                estimated_input_tokens=len(prompt) // _ESTIMATED_CHARS_PER_TOKEN,
                card_count=len(chunk),
            ))
    return packets


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
            return cls(path=path, total_spent_usd=d["total_spent_usd"],
                       total_spent_eur=d["total_spent_eur"],
                       completed_batch_ids=d.get("completed_batch_ids", []),
                       cards_written=d.get("cards_written", 0))
        return cls(path=path)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "total_spent_usd": self.total_spent_usd, "total_spent_eur": self.total_spent_eur,
            "completed_batch_ids": self.completed_batch_ids, "cards_written": self.cards_written,
        }))
        tmp.replace(self.path)

    @property
    def spent_eur(self) -> Decimal:
        return Decimal(self.total_spent_eur)


def load_done_tcgdex(output_path: Path) -> set[str]:
    """Reprise : cartes déjà écrites dans le TSV de sortie (première colonne)."""
    if not output_path.exists():
        return set()
    done: set[str] = set()
    with output_path.open(newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if row:
                done.add(row[0])
    return done


# --------------------------------------------------------------------------- écriture sortie


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def write_rows(output_path: Path, rows: list[dict], model: str) -> None:
    """Ajoute des lignes `card_insights` (clé tcgdex_id) au TSV de sortie. Format CSV-tab, aligné
    sur `infra/fleet/import_insights.sql` (FORMAT csv, DELIMITER tab, NULL '')."""
    marker = f"anthropic:{_pricing_key(model)}:batch:{LARGE_PROMPT_VERSION}"
    now = _now_naive()
    until = now + timedelta(days=_CACHE_DAYS)
    now_s = now.isoformat(sep=" ")
    until_s = until.isoformat(sep=" ")
    with output_path.open("a", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for r in rows:
            anecdotes_json = json.dumps(r["anecdotes"], ensure_ascii=False)
            writer.writerow([
                r["tcgdex_id"], anecdotes_json, r["game_rules"],
                marker, now_s, until_s, marker, now_s, until_s,
            ])


# ------------------------------------------------------------------------- soumission + application


@dataclass
class BatchOutcome:
    cards_written: int = 0
    anecdotes_total: int = 0
    anecdotes_rejected_no_source: int = 0
    failed_packets: list[str] = field(default_factory=list)  # custom_ids
    failure_reasons: dict[str, int] = field(default_factory=dict)  # raison -> compte
    input_tokens: int = 0
    output_tokens: int = 0
    errored_requests: int = 0


async def _run_batch(client: AnthropicBatchClient, requests: list[dict], label: str, log: Logger,
                     poll_interval: int, max_wait: int):
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
            parsed = parse_large_result(
                r.text, list(packet.ref_to_tcgdex.keys()),
                card_names_by_ref=packet.ref_to_name,
            )
        except (ValidationError, PacketMixingError) as exc:
            outcome.failed_packets.append(r.custom_id)
            reason = type(exc).__name__
            outcome.failure_reasons[reason] = outcome.failure_reasons.get(reason, 0) + 1
            continue
        for ref, insight in parsed.items():
            allowed = packet.allowed_by_ref.get(ref, set())
            sourced = [a for a in insight.anecdotes if a.source_url in allowed][:MAX_ANECDOTES]
            outcome.anecdotes_total += len(insight.anecdotes)
            outcome.anecdotes_rejected_no_source += len(insight.anecdotes) - len(
                [a for a in insight.anecdotes if a.source_url in allowed]
            )
            rows.append({
                "tcgdex_id": packet.ref_to_tcgdex[ref],
                "anecdotes": [a.model_dump() for a in sourced],
                "game_rules": insight.game_rules,
            })
    return rows, outcome


def _record_spend(ledger: Ledger, batch_id: str, model: str, outcome: BatchOutcome,
                  usd_to_eur_rate: Decimal) -> tuple[Decimal, Decimal]:
    cost_usd = batch_cost_usd(_pricing_key(model), input_tokens=outcome.input_tokens,
                              output_tokens=outcome.output_tokens)
    cost_eur = convert_to_eur(cost_usd, usd_to_eur_rate)
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
    cache = ContextCache(work / "context_cache.json")
    cache.load()
    rate = Decimal(str(args.usd_to_eur_rate))
    budget = Decimal(str(args.budget_eur))
    model = args.model

    cards = load_catalog(Path(args.catalog))
    owned = load_owned(Path(args.owned) if args.owned else None)
    ordered, tiers = build_priority(cards, owned, top_expensive=args.top_expensive)
    target = int(FULL_CATALOG * args.target_fraction)
    log(f"=== GÉNÉRATION démarrée — catalogue={len(cards)} cible={target} "
        f"({args.target_fraction:.0%}) budget={budget}€ modèle={_pricing_key(model)} "
        f"paquet={args.packet_size} ===")
    log(f"priorité : possédées={tiers['possedees']} chères={tiers['cheres']} "
        f"récentes+complément={tiers['recentes_et_complement']} (consultées: aucune source PROD)")

    done = load_done_tcgdex(output_path)
    log(f"reprise : {len(done)} cartes déjà écrites, dépense cumulée {ledger.spent_eur:.4f}€")

    # Cartes restant à couvrir, dans l'ordre de priorité, coupées à la cible.
    worklist = [c for c in ordered if c["tcgdex_id"] not in done][: max(0, target - len(done))]
    if args.max_cards is not None:
        # Garde-fou de tranche (validation, reprise contrôlée) : ne traite qu'au plus N cartes
        # ce passage — la cible/budget restent les bornes dures.
        worklist = worklist[: args.max_cards]
    if not worklist:
        log("cible déjà atteinte ou rien à faire — arrêt.")
        return

    retry_counts: dict[str, int] = defaultdict(int)
    chunk_cards = args.chunk_cards
    idx = 0
    stopped_reason = "cible atteinte"
    while idx < len(worklist):
        if ledger.spent_eur >= budget:
            stopped_reason = f"budget atteint ({ledger.spent_eur:.4f}€ ≥ {budget}€)"
            break
        chunk = worklist[idx : idx + chunk_cards]
        idx += len(chunk)

        # contexte JUSTE pour ce lot (interleave collecte/génération)
        set_pages, card_pages = await gather_context(chunk, cache, log)
        packets = build_packets(chunk, set_pages, card_pages, model=model,
                                packet_size=args.packet_size, tag=f"g{args.packet_size}")

        # budget : ne soumettre que ce que le reste couvre (estimation prudente)
        kept: list[Packet] = []
        est_eur = Decimal("0")
        for p in packets:
            proj = batch_cost_usd(_pricing_key(model), input_tokens=p.estimated_input_tokens,
                                  output_tokens=_OUT_TOKENS_PER_CARD * p.card_count)
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
                args.poll_interval, args.max_wait)
            rows, outcome = _apply_results(results, packets_by_id)

            # RÉ-ESSAI des paquets en échec, carte par carte (taille 1) — jamais perdus en silence.
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
                log(f"[chunk@{idx}] {len(outcome.failed_packets)} paquet(s) en échec "
                    f"{dict(outcome.failure_reasons)} → ré-essai carte par carte de "
                    f"{len(failed_cards)} carte(s)")
            if failed_cards:
                retry_packets = build_packets(failed_cards, set_pages, card_pages, model=model,
                                              packet_size=1, tag="r1")
                retry_by_id = {p.custom_id: p for p in retry_packets}
                rb_id, rresults = await _run_batch(
                    client, [p.request for p in retry_packets], f"retry@{idx}", log,
                    args.poll_interval, args.max_wait)
                rrows, routcome = _apply_results(rresults, retry_by_id)
                rows += rrows
                # cumuler les jetons du ré-essai dans le même relevé de coût
                outcome.input_tokens += routcome.input_tokens
                outcome.output_tokens += routcome.output_tokens
                outcome.anecdotes_total += routcome.anecdotes_total
                outcome.anecdotes_rejected_no_source += routcome.anecdotes_rejected_no_source
                _record_spend(ledger, rb_id, model, routcome, rate)
                still_failed = [
                    p.ref_to_tcgdex["c1"]
                    for cid, p in retry_by_id.items()
                    if cid in routcome.failed_packets
                ]
                if still_failed:
                    log(f"[retry@{idx}] {len(still_failed)} carte(s) toujours en échec après "
                        f"ré-essai {dict(routcome.failure_reasons)} — laissées candidates : "
                        f"{still_failed[:10]}...")
        finally:
            await client.aclose()

        # écrire les lignes, compter la dépense réelle
        if rows:
            write_rows(output_path, rows, model)
            ledger.cards_written += len(rows)
        cost_usd, cost_eur = _record_spend(ledger, batch_id, model, outcome, rate)
        ledger.save()
        log(f"[chunk@{idx}] écrites={len(rows)} cumul_cartes={ledger.cards_written} "
            f"in={outcome.input_tokens} out={outcome.output_tokens} "
            f"coût_lot≈{cost_eur:.4f}€ CUMUL={ledger.spent_eur:.4f}€/{budget}€ "
            f"anecdotes_sans_source={outcome.anecdotes_rejected_no_source}")

    covered = len(load_done_tcgdex(output_path))
    log(f"=== GÉNÉRATION terminée — {stopped_reason} — cartes couvertes={covered} "
        f"({covered / FULL_CATALOG:.1%} du catalogue) dépense={ledger.spent_eur:.4f}€ ===")


# --------------------------------------------------------------------------- mode mesure


async def measure(args: argparse.Namespace, api_key: str, log: Logger) -> None:
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    cache = ContextCache(work / "context_cache.json")
    cache.load()
    rate = Decimal(str(args.usd_to_eur_rate))
    model = args.model

    cards = load_catalog(Path(args.catalog))
    # Échantillon : extensions récentes COMPLÈTES (contiguës par extension), pour que les paquets
    # de N cartes reflètent le gros du travail — pas la tête dispersée (possédées + plus chères,
    # éparpillées sur des dizaines d'extensions, qui ne testeraient que des paquets de 1).
    by_set: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        by_set[c["set_tcgdex_id"]].append(c)
    recent_sets = sorted(
        by_set, key=lambda s: (by_set[s][0].get("set_release_date") or "", s), reverse=True
    )
    sample: list[dict] = []
    for s in recent_sets:
        if len(sample) >= args.measure_sample:
            break
        sample.extend(by_set[s])
    sample = sample[: args.measure_sample]
    log(f"=== MESURE — échantillon={len(sample)} (extensions récentes) "
        f"tailles={args.measure_sizes} ===")
    set_pages, card_pages = await gather_context(sample, cache, log)

    report = {"model": _pricing_key(model), "sample": len(sample), "full_catalog": FULL_CATALOG,
              "target_fraction": args.target_fraction, "usd_to_eur_rate": str(rate), "configs": []}
    client = AnthropicBatchClient(api_key)
    try:
        for size in args.measure_sizes:
            packets = build_packets(sample, set_pages, card_pages, model=model,
                                    packet_size=size, tag=f"m{size}")
            packets_by_id = {p.custom_id: p for p in packets}
            batch_id, results = await _run_batch(
                client, [p.request for p in packets], f"mesure-{size}", log,
                args.poll_interval, args.max_wait)
            rows, outcome = _apply_results(results, packets_by_id)
            cost_usd = batch_cost_usd(_pricing_key(model), input_tokens=outcome.input_tokens,
                                      output_tokens=outcome.output_tokens)
            cost_eur = convert_to_eur(cost_usd, rate)
            covered = len(rows)
            per_card = (cost_eur / covered) if covered else Decimal("0")
            target = int(FULL_CATALOG * args.target_fraction)
            extrapolation = per_card * target
            cfg = {
                "packet_size": size, "packets": len(packets), "cards_attempted": len(sample),
                "cards_covered": covered, "failed_packets": len(outcome.failed_packets),
                "input_tokens": outcome.input_tokens, "output_tokens": outcome.output_tokens,
                "anecdotes_total": outcome.anecdotes_total,
                "anecdotes_rejected_no_source": outcome.anecdotes_rejected_no_source,
                "cost_eur": str(cost_eur.quantize(Decimal("0.0001"))),
                "cost_per_card_eur": str(per_card.quantize(Decimal("0.00000001"))),
                "extrapolation_target_eur": str(extrapolation.quantize(Decimal("0.01"))),
            }
            report["configs"].append(cfg)
            log(f"[mesure-{size}] couvertes={covered}/{len(sample)} "
                f"échecs={len(outcome.failed_packets)} in={outcome.input_tokens} "
                f"out={outcome.output_tokens} coût={cost_eur:.4f}€ /carte={per_card:.8f}€ "
                f"extrapolation_{args.target_fraction:.0%}={extrapolation:.2f}€ "
                f"anecdotes_sans_source={outcome.anecdotes_rejected_no_source}")
    finally:
        await client.aclose()

    out = work / "measure_metrics.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    log(f"=== MESURE terminée — rapport {out} ===")


# --------------------------------------------------------------------------- CLI


def _read_key(path: Path) -> str:
    key = path.read_text().strip()
    if not key:
        raise SystemExit(f"clé vide dans {path}")
    return key


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key-file", required=True, help="fichier chmod 600 contenant la clé Anthropic")
    p.add_argument("--catalog", required=True,
                   help="catalog_full.json exporté de pbm_catalogue_ref")
    p.add_argument("--owned", default=None, help="fichier des tcgdex_id possédés (un par ligne)")
    p.add_argument("--work-dir", required=True, help="répertoire d'état (cache, ledger, mesure)")
    p.add_argument("--output", default=None, help="TSV de sortie card_insights (mode génération)")
    p.add_argument("--progress", default=str(Path.home() / "dev/logs/pbm-insights-progres.log"))
    p.add_argument("--budget-eur", type=float, default=50.0)
    p.add_argument("--target-fraction", type=float, default=0.80)
    p.add_argument("--top-expensive", type=int, default=3000)
    p.add_argument("--packet-size", type=int, default=25)
    p.add_argument("--chunk-cards", type=int, default=4000)
    p.add_argument("--max-cards", type=int, default=None,
                   help="borne de tranche : au plus N cartes ce passage (validation/reprise)")
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--usd-to-eur-rate", type=float, default=1.146)
    p.add_argument("--poll-interval", type=int, default=15)
    p.add_argument("--max-wait", type=int, default=6000)
    p.add_argument("--measure", action="store_true", help="mode mesure (aucune écriture de fiche)")
    p.add_argument("--measure-sample", type=int, default=120)
    p.add_argument("--measure-sizes", type=int, nargs="+", default=[25])
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    log = Logger(Path(args.progress))
    api_key = _read_key(Path(args.key_file))
    if args.measure:
        asyncio.run(measure(args, api_key, log))
    else:
        if not args.output:
            raise SystemExit("--output requis en mode génération")
        asyncio.run(generate(args, api_key, log))


if __name__ == "__main__":
    main()
