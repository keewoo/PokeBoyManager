"""Assistant IA de construction de deck (mission `v7-deck-ia`).

Un **seul appel IA par proposition** (principe « dès le premier tir », `docs/ARCHITECTURE.md`) :
on donne au modèle la liste NUMÉROTÉE des cartes possédées utiles (nom, type, PV, stade, coût
d'attaque le moins cher, exemplaires possédés) et des Énergies de base disponibles ; il répond
par des `ref` (jamais un UUID, jamais un nom libre : impossible d'inventer une carte hors
collection — un `ref` hors bornes est simplement ignoré), une quantité et une explication d'une
ligne par carte.

La proposition n'est **jamais** affichée telle quelle (risque du lot) : `reconcile` la passe au
crible des mêmes règles que le contrôle de légalité (possession, 4 exemplaires par nom, Pokémon
de base, taille 60) et corrige ce qui peut l'être — compléter en Énergies de base, retirer les
surnuméraires — en gardant une **trace** de chaque correction (jamais un repli silencieux). La
légalité finale reste calculée par `pbm_api.decks.legality`, source unique : le service écrit le
deck corrigé puis relit sa légalité, il ne la devine pas.

Les candidats sont restreints d'emblée aux cartes **possédées ET dans le format du deck**, ce qui
garantit qu'un deck proposé sans surnuméraire est possédé et en format ; il ne peut rester
illégal que si le joueur ne possède aucun Pokémon de base en format (signalé, jamais corrigé en
inventant une carte).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai import service as ai_service
from pbm_api.ai.base import AIProvider
from pbm_api.decks import energy, formats
from pbm_api.decks.errors import DeckNotFoundError, EmptyCollectionError, NoAiKeyForDeckError
from pbm_api.decks.legality import DECK_SIZE, MAX_COPIES_PER_NAME, is_basic_pokemon
from pbm_api.decks.replacements import attack_cost
from pbm_api.models import AiCredential, Card, CollectionItem, Deck, DeckCard, User
from pbm_api.models import AiProvider as AiProviderEnum
from pbm_api.security.crypto import decrypt_api_key

# Plafond de cartes décrites au modèle : borne le coût en jetons d'un appel (mission point 3,
# « mesure du coût moyen »). Les candidats sont triés par pertinence avant d'être coupés ici, donc
# ce qui tombe est le moins utile — et la coupe est signalée dans la trace, jamais silencieuse.
MAX_CANDIDATES = 150

# Correspondance nom d'Énergie de base -> type élémentaire du jeu (`Card.element_type`), pour
# choisir l'Énergie qui complète un deck. Fermé et connu (cf. `pbm_api.decks.energy`).
_ENERGY_NAME_TO_ELEMENT: dict[str, str] = {
    "energie plante": "grass",
    "energie feu": "fire",
    "energie eau": "water",
    "energie electrique": "lightning",
    "energie electrik": "lightning",
    "energie psy": "psychic",
    "energie combat": "fighting",
    "energie obscurite": "darkness",
    "energie metal": "metal",
    "energie fee": "fairy",
    "grass energy": "grass",
    "fire energy": "fire",
    "water energy": "water",
    "lightning energy": "lightning",
    "psychic energy": "psychic",
    "fighting energy": "fighting",
    "darkness energy": "darkness",
    "metal energy": "metal",
    "fairy energy": "fairy",
}


def basic_energy_element(name: str | None) -> str | None:
    """Type élémentaire d'une Énergie de base d'après son nom (`None` si non reconnu)."""
    return _ENERGY_NAME_TO_ELEMENT.get(energy.normalize(name))


# --------------------------------------------------------------------------- schéma de sortie IA
class ProposedCard(BaseModel):
    """Une carte choisie par le modèle, désignée par son `ref` (indice de la liste fournie)."""

    ref: int = Field(ge=0)
    quantity: int = Field(ge=1, le=DECK_SIZE)
    reason: str = Field(min_length=1, max_length=200)


class DeckProposal(BaseModel):
    cards: list[ProposedCard] = Field(default_factory=list, max_length=DECK_SIZE)
    summary: str | None = Field(default=None, max_length=400)


# --------------------------------------------------------------------------- entrées / sorties
@dataclass(frozen=True)
class Candidate:
    """Une carte offerte au modèle — possédée et dans le format du deck."""

    ref: int
    card_id: uuid.UUID
    name: str
    supertype: str | None
    element_type: str | None
    stage: str | None
    hp: int | None
    attack_cost: int | None
    owned: int
    is_basic_pokemon: bool
    is_basic_energy: bool


@dataclass(frozen=True)
class BasicEnergyOption:
    """Une Énergie de base du catalogue, disponible pour compléter le deck (D10 : fournie)."""

    element: str
    card_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class ProposalOptions:
    """Les vœux du joueur, indépendants de FastAPI (testables directement)."""

    types: list[tuple[str, int | None]] = field(default_factory=list)
    energy_types: list[str] = field(default_factory=list)
    style: str | None = None
    must_include: list[uuid.UUID] = field(default_factory=list)
    size: int = DECK_SIZE


@dataclass(frozen=True)
class ChosenCard:
    card_id: uuid.UUID
    name: str
    quantity: int
    reason: str


@dataclass(frozen=True)
class Correction:
    code: str
    message: str


@dataclass
class ReconcileResult:
    cards: list[ChosenCard] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)


# Codes de correction stables (repris par l'écran / la trace).
CODE_UNKNOWN_REF = "unknown_ref"
CODE_COPY_CAP = "copy_cap"
CODE_OWNED_CAP = "owned_cap"
CODE_MUST_INCLUDE = "must_include_added"
CODE_ADD_BASIC_POKEMON = "basic_pokemon_added"
CODE_NO_BASIC_POKEMON = "no_basic_pokemon_available"
CODE_ENERGY_FILL = "energy_fill"
CODE_TRIMMED = "trimmed_oversize"
CODE_INCOMPLETE = "could_not_complete"


# ------------------------------------------------------------------------------------ prompt
def _candidate_line(c: Candidate) -> str:
    bits: list[str] = [f"[{c.ref}] {c.name}"]
    if c.is_basic_energy:
        bits.append("Énergie de base (fournie, illimitée)")
    else:
        kind = c.supertype or "?"
        if c.element_type:
            kind += f"/{c.element_type}"
        bits.append(kind)
        if c.stage:
            bits.append(f"stade {c.stage}")
        if c.hp is not None:
            bits.append(f"{c.hp} PV")
        if c.attack_cost is not None:
            bits.append(f"attaque dès {c.attack_cost} énergie(s)")
        bits.append(f"possédée ×{c.owned}")
    return " — ".join(bits)


def build_prompt(
    options: ProposalOptions,
    candidates: list[Candidate],
    deck_format_label: str,
) -> str:
    wishes: list[str] = []
    if options.types:
        parts = [f"{t}" + (f" (~{s}%)" if s is not None else "") for t, s in options.types]
        wishes.append("Types privilégiés : " + ", ".join(parts) + ".")
    if options.energy_types:
        wishes.append("Énergies souhaitées : " + ", ".join(options.energy_types) + ".")
    if options.style:
        wishes.append(f"Style de jeu voulu : {options.style}.")
    wishes.append(f"Le deck vise {options.size} cartes au total (Énergies comprises).")
    wishes_text = "\n".join(f"- {w}" for w in wishes)

    catalogue = "\n".join(_candidate_line(c) for c in candidates)

    return (
        "Tu es un assistant de construction de deck Pokémon JCC. Compose le meilleur deck "
        f"possible EN FORMAT {deck_format_label}, UNIQUEMENT à partir des cartes ci-dessous "
        "(elles appartiennent au joueur). Ne cite jamais une carte hors de cette liste.\n\n"
        "Contraintes de jeu à respecter :\n"
        f"- exactement {DECK_SIZE} cartes au total (tu peux viser {options.size}, le reste "
        "sera complété en Énergies de base) ;\n"
        f"- au plus {MAX_COPIES_PER_NAME} exemplaires d'une même carte (sauf Énergies de base) ;\n"
        "- au moins un Pokémon de base, sinon le deck ne peut pas démarrer ;\n"
        "- n'inclus pas plus d'exemplaires d'une carte que le joueur n'en possède "
        "(indiqué « possédée ×N »).\n\n"
        "Vœux du joueur :\n"
        f"{wishes_text}\n\n"
        "Réponds en désignant chaque carte par son `ref` (le nombre entre crochets), avec une "
        "quantité et une explication d'UNE ligne (à quoi elle sert dans le deck). Ajoute un court "
        "`summary` de la stratégie.\n\n"
        "Cartes disponibles :\n"
        f"{catalogue}"
    )


# --------------------------------------------------------------------------------- réconciliation
def _name_key(name: str) -> str:
    return energy.normalize(name)


def reconcile(
    proposal: DeckProposal,
    candidates: list[Candidate],
    energy_options: list[BasicEnergyOption],
    options: ProposalOptions,
) -> ReconcileResult:
    """Transforme la proposition brute du modèle en un deck jouable, en traçant chaque correction.

    Fonction pure : la même logique est testable sans base (`test_deck_ai_builder.py`)."""
    by_ref = {c.ref: c for c in candidates}
    by_id = {c.card_id: c for c in candidates}
    corrections: list[Correction] = []

    # 1) refs -> cartes, quantités fusionnées par carte (le modèle peut citer un ref deux fois).
    merged: dict[uuid.UUID, int] = {}
    reasons: dict[uuid.UUID, str] = {}
    unknown_refs: list[int] = []
    for item in proposal.cards:
        cand = by_ref.get(item.ref)
        if cand is None:
            unknown_refs.append(item.ref)
            continue
        merged[cand.card_id] = merged.get(cand.card_id, 0) + item.quantity
        reasons.setdefault(cand.card_id, item.reason.strip())
    if unknown_refs:
        corrections.append(
            Correction(
                CODE_UNKNOWN_REF,
                f"{len(unknown_refs)} carte(s) proposée(s) hors de la liste fournie, ignorée(s).",
            )
        )

    # 2) must_include : chaque carte voulue est présente au moins une fois.
    for cid in options.must_include:
        if cid in by_id and cid not in merged:
            merged[cid] = 1
            reasons.setdefault(cid, "Ajoutée à ta demande (inclusion imposée).")
            corrections.append(
                Correction(
                    CODE_MUST_INCLUDE,
                    f"« {by_id[cid].name} » ajoutée : tu l'avais demandée en inclusion.",
                )
            )

    # 3) plafonds : possession (cartes non-Énergie de base) puis 4 exemplaires par NOM.
    for cid, qty in list(merged.items()):
        cand = by_id[cid]
        if cand.is_basic_energy:
            continue
        capped = min(qty, cand.owned)
        if capped < qty:
            corrections.append(
                Correction(
                    CODE_OWNED_CAP,
                    f"« {cand.name} » ramenée à {capped} : tu n'en possèdes que {cand.owned}.",
                )
            )
        merged[cid] = capped

    # 4 exemplaires par nom (Énergies de base exclues) — répartis sur les cartes de ce nom.
    per_name: dict[str, list[uuid.UUID]] = {}
    for cid in merged:
        cand = by_id[cid]
        if cand.is_basic_energy:
            continue
        per_name.setdefault(_name_key(cand.name), []).append(cid)
    for ids in per_name.values():
        total = sum(merged[cid] for cid in ids)
        if total <= MAX_COPIES_PER_NAME:
            continue
        excess = total - MAX_COPIES_PER_NAME
        # Retire l'excédent des exemplaires les moins possédés d'abord (arbitraire mais stable).
        for cid in sorted(ids, key=lambda c: by_id[c].owned):
            if excess <= 0:
                break
            take = min(merged[cid], excess)
            merged[cid] -= take
            excess -= take
        corrections.append(
            Correction(
                CODE_COPY_CAP,
                f"« {by_id[ids[0]].name} » plafonnée à {MAX_COPIES_PER_NAME} exemplaires.",
            )
        )

    # Élague les quantités nulles (une carte ramenée à 0 par un plafond n'est plus dans le deck).
    merged = {cid: q for cid, q in merged.items() if q > 0}

    # 4) au moins un Pokémon de base — sinon on en ajoute un possédé, sinon on le signale.
    has_basic = any(by_id[cid].is_basic_pokemon for cid in merged)
    if not has_basic:
        basics = [c for c in candidates if c.is_basic_pokemon]
        if basics:
            # le moins cher à jouer d'abord, puis le plus possédé.
            pick = min(basics, key=lambda c: (c.attack_cost if c.attack_cost is not None else 99))
            add = min(2, pick.owned)
            merged[pick.card_id] = merged.get(pick.card_id, 0) + add
            reasons.setdefault(pick.card_id, "Pokémon de base ajouté pour pouvoir démarrer.")
            corrections.append(
                Correction(
                    CODE_ADD_BASIC_POKEMON,
                    f"« {pick.name} » ajouté : un deck a besoin d'un Pokémon de base.",
                )
            )
        else:
            corrections.append(
                Correction(
                    CODE_NO_BASIC_POKEMON,
                    "Aucun Pokémon de base possédé en format : le deck reste incomplet, "
                    "complète ta collection.",
                )
            )

    # 5) taille : compléter en Énergies de base, ou retirer les surnuméraires.
    target = options.size
    total = sum(merged.values())
    energy_by_element = {e.element: e for e in energy_options}

    if total < target:
        _fill_with_energy(
            merged, reasons, corrections, by_id, energy_by_element, options, need=target - total
        )
    elif total > target:
        _trim_oversize(merged, corrections, by_id, options, excess=total - target)

    # 6) résultat, dans un ordre stable (Pokémon puis Dresseurs puis Énergies, par nom).
    def sort_key(cid: uuid.UUID) -> tuple:
        cand = by_id.get(cid)
        name = cand.name if cand else ""
        is_energy = cand.is_basic_energy if cand else True
        return (1 if is_energy else 0, name)

    cards = [
        ChosenCard(
            card_id=cid,
            name=(by_id[cid].name if cid in by_id else _energy_name(cid, energy_options)),
            quantity=merged[cid],
            reason=reasons.get(cid, ""),
        )
        for cid in sorted(merged, key=sort_key)
    ]
    return ReconcileResult(cards=cards, corrections=corrections)


def _energy_name(cid: uuid.UUID, energy_options: list[BasicEnergyOption]) -> str:
    for e in energy_options:
        if e.card_id == cid:
            return e.name
    return "Énergie"


def _fill_with_energy(
    merged: dict[uuid.UUID, int],
    reasons: dict[uuid.UUID, str],
    corrections: list[Correction],
    by_id: dict[uuid.UUID, Candidate],
    energy_by_element: dict[str, BasicEnergyOption],
    options: ProposalOptions,
    *,
    need: int,
) -> None:
    """Complète le deck jusqu'à la cible avec des Énergies de base, choisies selon les types du
    deck (types des Pokémon retenus) ou, à défaut, les vœux du joueur — jamais au hasard tant
    qu'un type est déterminable."""
    if need <= 0 or not energy_by_element:
        if need > 0:
            corrections.append(
                Correction(
                    CODE_INCOMPLETE,
                    f"Impossible de compléter les {need} dernière(s) carte(s) : aucune Énergie "
                    "de base disponible au catalogue.",
                )
            )
        return

    # Types à privilégier : ceux des Pokémon retenus, sinon les vœux, sinon toutes les Énergies.
    pokemon_elements: Counter[str] = Counter()
    for cid, qty in merged.items():
        cand = by_id.get(cid)
        if cand and not cand.is_basic_energy and cand.element_type:
            pokemon_elements[cand.element_type] += qty
    wished = [e for e in options.energy_types if e in energy_by_element]
    wished += [t for t, _ in options.types if t in energy_by_element and t not in wished]

    if pokemon_elements:
        elements = [e for e, _ in pokemon_elements.most_common() if e in energy_by_element]
    else:
        elements = list(wished)
    if not elements:
        elements = list(energy_by_element)  # dernier recours : n'importe quelle Énergie de base
    if not elements:
        corrections.append(
            Correction(
                CODE_INCOMPLETE,
                f"Impossible de déterminer un type d'Énergie pour compléter les {need} "
                "dernière(s) carte(s).",
            )
        )
        return

    # Répartition tourniquet sur les types retenus.
    added: Counter[str] = Counter()
    idx = 0
    while need > 0:
        element = elements[idx % len(elements)]
        opt = energy_by_element[element]
        merged[opt.card_id] = merged.get(opt.card_id, 0) + 1
        reasons.setdefault(opt.card_id, "Énergie de base pour alimenter les attaques.")
        added[element] += 1
        need -= 1
        idx += 1

    detail = ", ".join(f"{n} {el}" for el, n in added.most_common())
    corrections.append(
        Correction(CODE_ENERGY_FILL, f"Deck complété avec des Énergies de base ({detail}).")
    )


def _trim_oversize(
    merged: dict[uuid.UUID, int],
    corrections: list[Correction],
    by_id: dict[uuid.UUID, Candidate],
    options: ProposalOptions,
    *,
    excess: int,
) -> None:
    """Retire les surnuméraires : d'abord les Énergies de base (remplissage), puis les cartes non
    imposées, en préservant toujours au moins un Pokémon de base et les inclusions demandées."""
    must = set(options.must_include)
    removed = 0

    def is_energy(cid: uuid.UUID) -> bool:
        cand = by_id.get(cid)
        return cand.is_basic_energy if cand else True

    def is_protected_basic(cid: uuid.UUID) -> bool:
        cand = by_id.get(cid)
        if cand is None or not cand.is_basic_pokemon:
            return False
        # protège le DERNIER exemplaire d'un unique Pokémon de base.
        basics = [c for c in merged if by_id.get(c) and by_id[c].is_basic_pokemon]
        return len(basics) == 1 and merged[cid] == 1

    # Ordre de retrait : Énergies d'abord, puis grosses quantités non imposées.
    def removal_order() -> list[uuid.UUID]:
        return sorted(
            merged,
            key=lambda cid: (
                0 if is_energy(cid) else 1,
                0 if cid not in must else 1,
                -merged[cid],
            ),
        )

    while excess > 0:
        progressed = False
        for cid in removal_order():
            if excess <= 0:
                break
            if merged[cid] <= 0 or is_protected_basic(cid):
                continue
            if cid in must and merged[cid] <= 1:
                continue  # ne descend pas une inclusion imposée sous 1 exemplaire
            merged[cid] -= 1
            excess -= 1
            removed += 1
            progressed = True
        if not progressed:
            break  # plus rien de retirable sans casser une contrainte

    # nettoie les zéros.
    for cid in [c for c, q in merged.items() if q <= 0]:
        del merged[cid]

    if removed:
        corrections.append(
            Correction(
                CODE_TRIMMED,
                f"{removed} carte(s) en trop retirée(s) pour tenir la taille du deck.",
            )
        )


# ============================================================================ orchestration (DB)
# Séparé des fonctions pures ci-dessus (prompt + `reconcile`) : ici on touche la base et le
# fournisseur IA. `propose_deck` ne fait qu'UN aller-retour IA (mission), écrit le deck corrigé
# puis laisse la légalité être recalculée par `service.deck_detail` (source unique).

ProviderFactory = Callable[[AiProviderEnum, str], AIProvider]


@dataclass
class ProposalOutcome:
    """Ce que le routeur doit rendre : la légalité, elle, est relue via `service.deck_detail`."""

    result: ReconcileResult
    summary: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


async def _default_credential(session: AsyncSession, user: User) -> AiCredential | None:
    """Fournisseur par défaut de l'utilisateur avec une clé (D4) — jamais une clé plateforme."""
    if user.ai_default_provider is None:
        return None
    result = await session.execute(
        select(AiCredential).where(
            AiCredential.user_id == user.id, AiCredential.provider == user.ai_default_provider
        )
    )
    return result.scalar_one_or_none()


async def _load_basic_energy_options(session: AsyncSession) -> list[BasicEnergyOption]:
    """Une Énergie de base du catalogue par type élémentaire (fournie, jamais possédée, D10)."""
    rows = await session.execute(
        select(Card.id, Card.name, Card.energy_type, Card.supertype).where(
            or_(
                Card.energy_type.is_not(None),
                func.lower(Card.supertype).like("%nergie%"),
                func.lower(Card.supertype).like("%energy%"),
            )
        )
    )
    by_element: dict[str, BasicEnergyOption] = {}
    for card_id, name, energy_type, supertype in rows.all():
        if not energy.is_basic_energy(supertype, name, energy_type):
            continue
        element = basic_energy_element(name)
        if element is None or element in by_element:
            continue
        by_element[element] = BasicEnergyOption(element=element, card_id=card_id, name=name)
    return list(by_element.values())


def _relevance(cand_supertype: str | None, element: str | None, wanted: set[str]) -> int:
    """Score de tri des candidats offerts au modèle (plus grand = plus pertinent), pour que la
    coupe à `MAX_CANDIDATES` retire le moins utile en premier."""
    is_pokemon = energy.normalize(cand_supertype) == "pokemon"
    if is_pokemon and element in wanted:
        return 4
    if is_pokemon:
        return 3
    if energy.normalize(cand_supertype) in {"dresseur", "trainer"}:
        return 2
    return 1


async def _load_candidates(
    session: AsyncSession,
    user: User,
    deck_format: str,
    options: ProposalOptions,
    energy_options: list[BasicEnergyOption],
) -> list[Candidate]:
    """Cartes possédées (hors contrefaçon) ET dans le format du deck, plus les Énergies de base
    du catalogue. Triées par pertinence puis coupées à `MAX_CANDIDATES` pour borner le coût IA."""
    rows = await session.execute(
        select(
            Card.id,
            Card.name,
            Card.supertype,
            Card.energy_type,
            Card.element_type,
            Card.stage,
            Card.hp,
            Card.attacks,
            Card.legal_standard,
            Card.legal_expanded,
            func.count(CollectionItem.id).label("owned"),
        )
        .join(CollectionItem, CollectionItem.card_id == Card.id)
        .where(
            CollectionItem.user_id == user.id,
            CollectionItem.counterfeit_suspected.is_(False),
        )
        .group_by(Card.id)
    )
    wanted = {t for t, _ in options.types}
    must = set(options.must_include)

    scored: list[tuple[int, int, dict]] = []
    for row in rows.mappings():
        basic_e = energy.is_basic_energy(row["supertype"], row["name"], row["energy_type"])
        if basic_e:
            continue  # les Énergies de base viennent du catalogue (fournies), pas de la collection
        in_fmt = formats.card_in_format(
            deck_format,
            is_basic_energy=False,
            legal_standard=row["legal_standard"],
            legal_expanded=row["legal_expanded"],
        )
        if not in_fmt:
            continue
        rel = _relevance(row["supertype"], row["element_type"], wanted)
        priority = 5 if row["id"] in must else rel
        scored.append((priority, int(row["owned"]), dict(row)))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    kept = scored[:MAX_CANDIDATES]

    candidates: list[Candidate] = []
    ref = 0
    for _priority, owned, row in kept:
        candidates.append(
            Candidate(
                ref=ref,
                card_id=row["id"],
                name=row["name"],
                supertype=row["supertype"],
                element_type=row["element_type"],
                stage=row["stage"],
                hp=row["hp"],
                attack_cost=attack_cost(row["attacks"]),
                owned=owned,
                is_basic_pokemon=is_basic_pokemon(row["supertype"], row["stage"]),
                is_basic_energy=False,
            )
        )
        ref += 1

    # Les Énergies de base sont proposées comme candidats (le modèle peut les choisir lui-même) —
    # `owned` très grand : elles ne sont jamais plafonnées par la possession (D10).
    for opt in energy_options:
        candidates.append(
            Candidate(
                ref=ref,
                card_id=opt.card_id,
                name=opt.name,
                supertype="Énergie",
                element_type=opt.element,
                stage=None,
                hp=None,
                attack_cost=None,
                owned=DECK_SIZE,
                is_basic_pokemon=False,
                is_basic_energy=True,
            )
        )
        ref += 1

    return candidates


async def _replace_deck_cards(
    session: AsyncSession, deck: Deck, cards: list[ChosenCard]
) -> None:
    await session.execute(delete(DeckCard).where(DeckCard.deck_id == deck.id))
    for c in cards:
        session.add(DeckCard(deck_id=deck.id, card_id=c.card_id, quantity=c.quantity))
    deck.updated_at = datetime.now(UTC)
    await session.commit()


async def propose_deck(
    session: AsyncSession,
    user: User,
    deck_id: uuid.UUID,
    options: ProposalOptions,
    provider_factory: ProviderFactory,
) -> ProposalOutcome:
    """Un appel IA -> une proposition réconciliée -> le deck (existant) réécrit. Borné au
    propriétaire (un deck d'un autre utilisateur lève `DeckNotFoundError` -> 404)."""
    deck = await session.get(Deck, deck_id)
    if deck is None or deck.user_id != user.id:
        raise DeckNotFoundError

    credential = await _default_credential(session, user)
    if credential is None:
        raise NoAiKeyForDeckError

    energy_options = await _load_basic_energy_options(session)
    candidates = await _load_candidates(session, user, deck.format, options, energy_options)
    if not any(not c.is_basic_energy for c in candidates):
        raise EmptyCollectionError

    prompt = build_prompt(options, candidates, formats.label(deck.format))
    key = decrypt_api_key(credential.encrypted_key, credential.nonce, user.id)
    provider = provider_factory(credential.provider, key)
    try:
        proposal, usage = await provider.extract(
            [], DeckProposal, prompt, model=user.ai_default_model
        )
        used_model = user.ai_default_model or provider.DEFAULT_MODEL
    finally:
        await provider.aclose()

    await ai_service.record_usage(session, user, usage)
    result = reconcile(proposal, candidates, energy_options, options)
    await _replace_deck_cards(session, deck, result.cards)

    return ProposalOutcome(
        result=result,
        summary=proposal.summary,
        provider=credential.provider.value,
        model=used_model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
