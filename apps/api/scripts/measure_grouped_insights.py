"""Mesure du lot `pbm-insights-toutes-cartes` : coût ET qualité par taille de paquet (1/10/25
cartes par requête), sur 100 cartes représentatives, contre la vraie IA (clé d'Aymeric).

Tourne sur **devAI** : la clé personnelle d'Aymeric ne quitte pas cette machine. Elle est lue
uniquement depuis un fichier chmod 600 (`--key-file`) et n'est JAMAIS journalisée, ni passée en
argument de ligne de commande, ni en variable d'environnement visible par `ps`.

Pipeline :
  1. charge un échantillon exporté de `pbm_catalogue_ref` (4 extensions × 25 cartes) ;
  2. collecte le contexte wiki (contexte d'extension partagé + contexte propre à la carte),
     mis en cache local pour être ré-exécutable sans re-solliciter les wikis ;
  3. gate : un lot « smoke » d'UNE requête groupée valide la clé + le schéma de sortie structuré
     (jamais exercé contre l'API réelle avant ce lot) avant toute dépense plus large ;
  4. soumet 3 lots (Message Batches, -50 %) : 1, 10 puis 25 cartes par requête ;
  5. mesure le coût réel (jetons facturés × tarif Batch), le taux d'anecdotes sans source valide,
     les échecs de paquet (schéma/anti-mélange) et les mélanges entre cartes ;
  6. extrapole au catalogue complet (22 169 cartes) et compare les trois tailles.

Aucune écriture en base : c'est une mesure. Résultats → `--out` (JSON) + journal de progression.
"""

import argparse
import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from pbm_api.ingame.rules import legalities_of, prize_rule_of
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
from pbm_api.insights_batch.combined_generation import (
    COMBINED_JSON_SCHEMA,
    CombinedCardInsightExtraction,
    build_combined_prompt,
)
from pbm_api.insights_batch.grouped_generation import (
    GROUPED_JSON_SCHEMA,
    PacketCard,
    PacketMixingError,
    ValidationError,
    allowed_urls_for,
    build_grouped_prompt,
    parse_grouped_result,
)
from pbm_api.insights_batch.pricing import batch_cost_usd

_WIKI_COURTESY_SLEEP = 0.25  # débit raisonnable envers Poképédia/Bulbapedia (mission « qualité »)
FULL_CATALOG = 22169


def log(progress_path: Path, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}"
    print(line, flush=True)
    with progress_path.open("a") as handle:
        handle.write(line + "\n")


# --------------------------------------------------------------------------- contexte wiki


def _pages_to_json(pages: list[ContextPage]) -> list[dict]:
    return [p.model_dump() for p in pages]


def _pages_from_json(raw: list[dict]) -> list[ContextPage]:
    return [ContextPage(**p) for p in raw]


async def _fetch(client: MediaWikiClient, query: str) -> list[ContextPage]:
    page = await client.fetch_page(query)
    await asyncio.sleep(_WIKI_COURTESY_SLEEP)
    return [page] if page is not None else []


async def gather_context(
    cards: list[dict],
    sets_by_id: dict[str, dict],
    cache_path: Path,
    progress: Path,
) -> tuple[dict[str, list[ContextPage]], dict[str, list[ContextPage]]]:
    """Renvoie (set_pages_by_set_id, card_pages_by_card_id). Le contexte d'extension est collecté
    une seule fois par extension (partagé), le contexte de carte une fois par carte."""
    cache = {"sets": {}, "cards": {}}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
    set_pages: dict[str, list[ContextPage]] = {}
    card_pages: dict[str, list[ContextPage]] = {}

    pokepedia = MediaWikiClient(POKEPEDIA_API_URL)
    bulbapedia = MediaWikiClient(BULBAPEDIA_API_URL)
    try:
        # contexte d'extension (partagé)
        for set_id in {c["set_id"] for c in cards}:
            if set_id in cache["sets"]:
                set_pages[set_id] = _pages_from_json(cache["sets"][set_id])
                continue
            name = sets_by_id[set_id]["name"]
            pages = await _fetch(pokepedia, name) + await _fetch(bulbapedia, name)
            deduped = _dedup(pages)
            set_pages[set_id] = deduped
            cache["sets"][set_id] = _pages_to_json(deduped)
            cache_path.write_text(json.dumps(cache))
        # contexte propre à la carte
        done = 0
        for card in cards:
            cid = card["id"]
            if cid in cache["cards"]:
                card_pages[cid] = _pages_from_json(cache["cards"][cid])
                done += 1
                continue
            pages = await _fetch(pokepedia, card["name"])
            if card.get("en_name"):
                pages += await _fetch(bulbapedia, card["en_name"])
            deduped = _dedup(pages)
            card_pages[cid] = deduped
            cache["cards"][cid] = _pages_to_json(deduped)
            done += 1
            if done % 20 == 0:
                cache_path.write_text(json.dumps(cache))
                log(progress, f"contexte collecté pour {done}/{len(cards)} cartes")
        cache_path.write_text(json.dumps(cache))
    finally:
        await pokepedia.aclose()
        await bulbapedia.aclose()
    return set_pages, card_pages


def _dedup(pages: list[ContextPage]) -> list[ContextPage]:
    seen: set[str] = set()
    out: list[ContextPage] = []
    for p in pages:
        if p.source_url not in seen:
            out.append(p)
            seen.add(p.source_url)
    return out


# --------------------------------------------------------------------------- construction requêtes


def _packet_card(card: dict, ref: str, card_pages: list[ContextPage]) -> PacketCard:
    prize = prize_rule_of(card_name=card["name"], supertype=card.get("supertype"))
    return PacketCard(
        card_ref=ref,
        card_name=card["name"],
        card_pages=card_pages,
        legal_standard=card.get("legal_standard"),
        legal_expanded=card.get("legal_expanded"),
        prize_label=prize.label,
        attacks=card.get("attacks"),
        abilities=card.get("abilities"),
    )


@dataclass
class PacketMeta:
    custom_id: str
    ref_to_card_id: dict[str, str]
    allowed_by_ref: dict[str, set[str]]


def build_single_requests(cards, set_pages, card_pages, model):
    """Config 1-par-requête : chemin de production actuel (`build_combined_prompt`)."""
    requests = []
    allowed = {}
    for card in cards:
        cid = card["id"]
        pages = _dedup(set_pages[card["set_id"]] + card_pages[cid])
        prize = prize_rule_of(card_name=card["name"], supertype=card.get("supertype"))
        leg = legalities_of(
            legal_standard=card.get("legal_standard"), legal_expanded=card.get("legal_expanded")
        )
        prompt = build_combined_prompt(
            card_name=card["name"],
            set_name=card["set_name"],
            context_pages=pages,
            legal_standard=leg.standard,
            legal_expanded=leg.expanded,
            prize_label=prize.label,
            attacks=card.get("attacks"),
            abilities=card.get("abilities"),
            tournament_decks=None,
        )
        # custom_id Anthropic : ^[a-zA-Z0-9_-]{1,64}$ — un UUID (tirets) passe, pas les ":".
        custom_id = f"s_{cid}"
        requests.append(
            build_batch_request(
                custom_id=custom_id,
                model=model,
                max_tokens=2048,
                prompt=prompt,
                json_schema=COMBINED_JSON_SCHEMA,
            )
        )
        allowed[custom_id] = {p.source_url for p in pages}
    return requests, allowed


def build_grouped_requests(cards, set_pages, card_pages, model, packet_size, tag):
    """Config N-par-requête, groupée par extension. Renvoie (requests, list[PacketMeta])."""
    by_set: dict[str, list[dict]] = defaultdict(list)
    for card in cards:
        by_set[card["set_id"]].append(card)

    requests = []
    metas: list[PacketMeta] = []
    for set_id, set_cards in by_set.items():
        for chunk_idx in range(0, len(set_cards), packet_size):
            chunk = set_cards[chunk_idx : chunk_idx + packet_size]
            packet_cards = []
            ref_to_card_id = {}
            allowed_by_ref = {}
            for i, card in enumerate(chunk, start=1):
                ref = f"c{i}"
                pc = _packet_card(card, ref, card_pages[card["id"]])
                packet_cards.append(pc)
                ref_to_card_id[ref] = card["id"]
                allowed_by_ref[ref] = allowed_urls_for(set_pages[set_id], pc)
            prompt = build_grouped_prompt(
                set_name=set_cards[0]["set_name"], set_pages=set_pages[set_id], cards=packet_cards
            )
            # custom_id Anthropic : ^[a-zA-Z0-9_-]{1,64}$ — séparateur "_" (les ":" sont refusés).
            custom_id = f"{tag}_{set_id}_{chunk_idx}"
            # budget de sortie : ~900 jetons/carte + marge (borné, Haiku 4.5 plafonne à 64k)
            max_tokens = min(64000, 900 * len(chunk) + 1500)
            requests.append(
                build_batch_request(
                    custom_id=custom_id,
                    model=model,
                    max_tokens=max_tokens,
                    prompt=prompt,
                    json_schema=GROUPED_JSON_SCHEMA,
                )
            )
            metas.append(PacketMeta(custom_id, ref_to_card_id, allowed_by_ref))
    return requests, metas


# --------------------------------------------------------------------------- soumission + mesure


async def run_batch(client: AnthropicBatchClient, requests, label, progress, max_wait=2400):
    status = await client.create_batch(requests)
    log(progress, f"[{label}] lot soumis {status.batch_id} ({len(requests)} requêtes)")
    waited = 0
    interval = 15
    while True:
        st = await client.get_batch(status.batch_id)
        if st.processing_status == "ended":
            log(progress, f"[{label}] terminé : {st.request_counts}")
            return await client.iter_results(st.results_url or "")
        if waited >= max_wait:
            raise BatchApiError(f"[{label}] toujours en traitement après {max_wait}s")
        await asyncio.sleep(interval)
        waited += interval


@dataclass
class ConfigMetrics:
    label: str
    requests: int = 0
    cards_attempted: int = 0
    cards_covered: int = 0
    packet_failures: int = 0
    errored_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    anecdotes_total: int = 0
    anecdotes_rejected_no_source: int = 0
    cross_card_incidents: int = 0
    cost_usd: Decimal = Decimal("0")
    cache_read_tokens: int = 0
    notes: list[str] = field(default_factory=list)


def _count_anecdotes(items, allowed: set[str]) -> tuple[int, int]:
    total = len(items)
    rejected = sum(1 for a in items if a.source_url not in allowed)
    return total, rejected


def summarize_single(results, allowed, model) -> ConfigMetrics:
    m = ConfigMetrics(label="1-par-requête")
    for r in results:
        m.requests += 1
        m.cards_attempted += 1
        if r.result_type != "succeeded" or r.text is None:
            m.errored_requests += 1
            continue
        m.input_tokens += r.input_tokens
        m.output_tokens += r.output_tokens
        try:
            ex = CombinedCardInsightExtraction.model_validate_json(r.text)
        except ValidationError:
            m.packet_failures += 1
            continue
        m.cards_covered += 1
        allow = allowed[r.custom_id]
        for items in (ex.anecdotes_fr, ex.anecdotes_en):
            t, rej = _count_anecdotes(items, allow)
            m.anecdotes_total += t
            m.anecdotes_rejected_no_source += rej
    m.cost_usd = batch_cost_usd(model, input_tokens=m.input_tokens, output_tokens=m.output_tokens)
    return m


def summarize_grouped(
    results, metas, set_pages, card_pages, cards_by_id, model, label
) -> ConfigMetrics:
    m = ConfigMetrics(label=label)
    meta_by_id = {meta.custom_id: meta for meta in metas}
    for r in results:
        m.requests += 1
        meta = meta_by_id.get(r.custom_id)
        n = len(meta.ref_to_card_id) if meta else 0
        m.cards_attempted += n
        if r.result_type != "succeeded" or r.text is None:
            m.errored_requests += 1
            continue
        m.input_tokens += r.input_tokens
        m.output_tokens += r.output_tokens
        try:
            parsed = parse_grouped_result(r.text, list(meta.ref_to_card_id.keys()))
        except (ValidationError, PacketMixingError, ValueError) as exc:
            m.packet_failures += 1
            m.notes.append(f"paquet {r.custom_id} rejeté: {type(exc).__name__}")
            continue
        # URLs propres à CHAQUE autre carte du paquet — pour détecter un mélange
        other_urls = {}
        for ref in meta.ref_to_card_id:
            others = set()
            for oref, ocid in meta.ref_to_card_id.items():
                if oref != ref:
                    others |= {p.source_url for p in card_pages[ocid]}
            other_urls[ref] = others
        for ref, gc in parsed.items():
            m.cards_covered += 1
            allow = meta.allowed_by_ref[ref]
            for items in (gc.anecdotes_fr, gc.anecdotes_en):
                t, rej = _count_anecdotes(items, allow)
                m.anecdotes_total += t
                m.anecdotes_rejected_no_source += rej
                for a in items:
                    if a.source_url not in allow and a.source_url in other_urls[ref]:
                        m.cross_card_incidents += 1
    m.cost_usd = batch_cost_usd(model, input_tokens=m.input_tokens, output_tokens=m.output_tokens)
    return m


async def eur_per_usd() -> Decimal:
    """Taux EUR/USD depuis le flux quotidien BCE, via le même client que le reste du dépôt
    (`pbm_api.pricing.exchange_rates.EcbClient`, parse XML robuste) — jamais le parse de chaîne
    ad hoc d'avant. La BCE publie « USD pour 1 EUR » ; on renvoie l'inverse (EUR pour 1 USD).

    ⛔ Pas de repli silencieux : un flux BCE injoignable LÈVE plutôt que de renvoyer une valeur
    inventée. Le seul but de cette mesure est un coût en euros exact pour une décision de budget —
    un taux faux (0,92 au lieu de 0,87 mesuré) fausserait justement le chiffre qui tranche
    (règle « un repli silencieux est une panne », CLAUDE.md)."""
    from pbm_api.pricing.exchange_rates import EcbClient, EcbUnavailableError

    client = EcbClient()
    try:
        _day, rates = await client.fetch_daily_rates()
    finally:
        await client.aclose()
    usd_per_eur = rates.get("USD")
    if usd_per_eur is None or usd_per_eur <= 0:
        raise EcbUnavailableError("flux BCE sans taux USD exploitable — mesure interrompue")
    return (Decimal("1") / usd_per_eur).quantize(Decimal("0.0001"))


def select_representative(cards_by_set: dict[str, list[dict]], per_set: int) -> list[dict]:
    chosen = []
    for group in cards_by_set.values():
        ordered = sorted(group, key=lambda c: (len(c["number"]), c["number"]))
        n = len(ordered)
        if n <= per_set:
            chosen.extend(ordered)
        else:
            idxs = sorted({round(i * (n - 1) / (per_set - 1)) for i in range(per_set)})
            chosen.extend(ordered[i] for i in idxs)
    return chosen


async def main() -> int:
    ap = argparse.ArgumentParser()
    work = Path.home() / "dev/pbm-insights-work"
    default_key = str(Path.home() / ".pokeboy-secrets/aymeric-anthropic-key")
    ap.add_argument("--sample", default=str(work / "sample_cards.json"))
    ap.add_argument("--key-file", default=default_key)
    ap.add_argument("--cache", default=str(work / "context_cache.json"))
    ap.add_argument("--out", default=str(work / "measure_metrics.json"))
    ap.add_argument("--progress", default=str(Path.home() / "dev/logs/pbm-insights-progres.log"))
    ap.add_argument("--per-set", type=int, default=25)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument(
        "--build-only",
        action="store_true",
        help="construit les requêtes sans appeler Anthropic (débogage gratuit)",
    )
    args = ap.parse_args()

    progress = Path(args.progress)
    progress.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(args.sample).read_text())
    sets_by_id = {s["id"]: s for s in data["sets"]}
    cards_by_set: dict[str, list[dict]] = defaultdict(list)
    for card in data["cards"]:
        card["set_name"] = sets_by_id[card["set_id"]]["name"]
        cards_by_set[card["set_id"]].append(card)

    cards = select_representative(cards_by_set, args.per_set)
    cards_by_id = {c["id"]: c for c in cards}
    log(progress, f"=== MESURE démarrée : {len(cards)} cartes, {len(cards_by_set)} extensions ===")

    set_pages, card_pages = await gather_context(
        cards, sets_by_id, Path(args.cache), progress
    )
    with_card_ctx = sum(1 for c in cards if card_pages[c["id"]])
    log(progress, f"cartes avec contexte propre : {with_card_ctx}/{len(cards)}")

    if args.build_only:
        req_a, _ = build_single_requests(cards, set_pages, card_pages, args.model)
        req_b, meta_b = build_grouped_requests(cards, set_pages, card_pages, args.model, 10, "g10")
        req_c, meta_c = build_grouped_requests(cards, set_pages, card_pages, args.model, 25, "g25")

        def _chars(reqs):
            return sum(len(r["params"]["messages"][0]["content"]) for r in reqs)

        for label, reqs in (("1-par", req_a), ("10-par", req_b), ("25-par", req_c)):
            ch = _chars(reqs)
            log(
                progress,
                f"[build-only {label}] requêtes={len(reqs)} chars_prompt_total={ch} "
                f"~jetons_entree={ch // 4} (≈{ch // 4 // max(1, len(cards))}/carte)",
            )
        sample = req_c[0]["params"]["messages"][0]["content"][:900]
        log(progress, f"[build-only] extrait prompt 25-par:\n{sample}\n---")
        log(progress, "build-only terminé (aucun appel Anthropic).")
        return 0

    key = Path(args.key_file).expanduser().read_text().strip()
    if not key:
        log(progress, "ERREUR : clé vide")
        return 2

    rate = await eur_per_usd()
    log(progress, f"taux EUR/USD utilisé : {rate}")

    client = AnthropicBatchClient(key)
    try:
        # --- GATE : smoke test (1 requête groupée de 2 cartes) valide clé + schéma structuré ---
        # Cartes prises dans la sélection représentative (leur contexte est en cache), pas dans
        # l'extension complète.
        first_set = cards[0]["set_id"]
        smoke_cards = [c for c in cards if c["set_id"] == first_set][:2]
        smoke_reqs, smoke_metas = build_grouped_requests(
            smoke_cards, set_pages, card_pages, args.model, packet_size=2, tag="smoke"
        )
        # Le smoke valide la clé + le schéma structuré. Un échec de paquet ISOLÉ n'est PAS une
        # preuve que la clé/le schéma sont cassés : le modèle produit parfois un paquet non valide
        # (c'est justement le cas que l'anti-mélange rejette, et à l'échelle ces cartes restent
        # candidates pour une reprise). On réessaie donc jusqu'à 3 fois ; on n'ARRÊTE que si TOUTES
        # les tentatives échouent (clé invalide, schéma refusé => tout casse), pour distinguer une
        # panne réelle d'un simple aléa de génération. (Le lot précédent s'était arrêté sur un seul
        # échec sans jamais lire la réponse brute ; corrigé.)
        smoke_ok = False
        for attempt in range(1, 4):
            log(progress, f"GATE smoke tentative {attempt}/3 : validation clé + schéma structuré…")
            smoke_results = await run_batch(client, smoke_reqs, f"smoke{attempt}", progress, 900)
            sm = summarize_grouped(
                smoke_results, smoke_metas, set_pages, card_pages, cards_by_id, args.model, "smoke"
            )
            if not sm.errored_requests and not sm.packet_failures and sm.cards_covered == len(
                smoke_cards
            ):
                smoke_ok = True
                break
            log(progress, f"GATE smoke tentative {attempt} en échec : {sm}")
            for r in smoke_results:
                if r.result_type != "succeeded":
                    log(progress, f"  erreur smoke {r.custom_id}: {r.error}")
        if not smoke_ok:
            log(progress, "GATE smoke ÉCHOUÉ sur 3 tentatives — arrêt avant dépense large")
            return 3
        log(progress, "GATE smoke OK — poursuite des 3 configurations")

        # --- 3 configurations ---
        req_a, allowed_a = build_single_requests(cards, set_pages, card_pages, args.model)
        req_b, meta_b = build_grouped_requests(cards, set_pages, card_pages, args.model, 10, "g10")
        req_c, meta_c = build_grouped_requests(cards, set_pages, card_pages, args.model, 25, "g25")

        res_a, res_b, res_c = await asyncio.gather(
            run_batch(client, req_a, "1-par", progress),
            run_batch(client, req_b, "10-par", progress),
            run_batch(client, req_c, "25-par", progress),
        )
        ma = summarize_single(res_a, allowed_a, args.model)
        mb = summarize_grouped(
            res_b, meta_b, set_pages, card_pages, cards_by_id, args.model, "10-par-requête"
        )
        mc = summarize_grouped(
            res_c, meta_c, set_pages, card_pages, cards_by_id, args.model, "25-par-requête"
        )
    finally:
        await client.aclose()

    configs = [ma, mb, mc]
    report = {
        "model": args.model,
        "cards_sampled": len(cards),
        "sets": [
            {"name": s["name"], "series": s["series"], "release_date": s["release_date"]}
            for s in data["sets"]
        ],
        "cards_with_own_context": with_card_ctx,
        "eur_per_usd": str(rate),
        "full_catalog": FULL_CATALOG,
        "configs": [],
    }
    for m in configs:
        covered = m.cards_covered or 1
        cost_eur = (m.cost_usd * rate).quantize(Decimal("0.000001"))
        cost_per_card_usd = (m.cost_usd / covered).quantize(Decimal("0.00000001"))
        cost_per_card_eur = (cost_eur / covered).quantize(Decimal("0.00000001"))
        extrapolation_eur = (cost_per_card_eur * FULL_CATALOG).quantize(Decimal("0.01"))
        src_rej = (
            m.anecdotes_rejected_no_source / m.anecdotes_total if m.anecdotes_total else 0.0
        )
        entry = {
            "label": m.label,
            "requests": m.requests,
            "cards_attempted": m.cards_attempted,
            "cards_covered": m.cards_covered,
            "packet_failures": m.packet_failures,
            "errored_requests": m.errored_requests,
            "input_tokens": m.input_tokens,
            "output_tokens": m.output_tokens,
            "anecdotes_total": m.anecdotes_total,
            "anecdotes_rejected_no_source": m.anecdotes_rejected_no_source,
            "source_rejection_rate": round(src_rej, 4),
            "cross_card_incidents": m.cross_card_incidents,
            "cost_usd": str(m.cost_usd.quantize(Decimal("0.000001"))),
            "cost_eur": str(cost_eur),
            "cost_per_covered_card_usd": str(cost_per_card_usd),
            "cost_per_covered_card_eur": str(cost_per_card_eur),
            "extrapolation_full_catalog_eur": str(extrapolation_eur),
            "notes": m.notes[:10],
        }
        report["configs"].append(entry)
        log(
            progress,
            f"[{m.label}] couvertes={m.cards_covered}/{m.cards_attempted} "
            f"echecs_paquet={m.packet_failures} in={m.input_tokens} out={m.output_tokens} "
            f"cout={entry['cost_eur']}€ /carte={entry['cost_per_covered_card_eur']}€ "
            f"extrapolation={entry['extrapolation_full_catalog_eur']}€ "
            f"anecdotes_sans_source={entry['source_rejection_rate']} "
            f"melanges={m.cross_card_incidents}",
        )

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log(progress, f"=== MESURE terminée — rapport JSON : {args.out} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
