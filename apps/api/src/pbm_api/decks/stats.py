"""Agrégats chiffrés d'un deck (mission `v7-decks-stats`) — logique pure, sans accès base.

Tout vient du **catalogue** (type, PV, coûts d'attaque, stade, marqueur de règle) et de la
**valorisation** existante (`pbm_api.pricing.valuation`, prix de référence passé en entrée) :
jamais une estimation du modèle (risque du lot). La fiche répond à trois questions — ce que le
deck coûte à jouer (courbe des coûts d'attaque, PV moyens), ce qu'il contient (répartition par
type de carte, par type élémentaire, par rôle, structure d'évolution, cartes spéciales), et ce
qu'il vaut (valeur marchande, part de doublons).

Le classement par rôle est un **partitionnement** (chaque exemplaire compte pour exactement un
rôle, la somme égale `card_count`) fondé sur des heuristiques de catalogue explicitement
documentées ci-dessous — pas un jugement du modèle. Ce que le catalogue ne porte pas, on ne
l'invente pas : faute de champ `evolveFrom`, la « complétude des lignes d'évolution » se
réduit à la **répartition par stade** et au signal « évolutions sans Pokémon de base ».
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from pbm_api.decks import energy

# Un Pokémon dont les PV atteignent ce seuil est classé « mur » (proxy défensif tiré du seul
# catalogue) — au-dessus, on considère son rôle premier comme défensif quelles que soient ses
# attaques. En deçà, un Pokémon qui attaque est un « attaquant », sinon un « soutien ».
WALL_HP_THRESHOLD = 200

# Coût d'attaque au-delà duquel on regroupe dans un même seau « 5+ » : au-delà de 4 énergies,
# le détail n'apporte rien à la lecture de la courbe.
MAX_COST_BUCKET = 5

_POKEMON_SUPERTYPES = {"pokemon"}

# Libellés français des onze codes de type élémentaire (`pbm_api.catalog.element_type`).
ELEMENT_LABELS: dict[str, str] = {
    "grass": "Plante",
    "fire": "Feu",
    "water": "Eau",
    "lightning": "Électrique",
    "psychic": "Psy",
    "fighting": "Combat",
    "darkness": "Obscurité",
    "metal": "Métal",
    "dragon": "Dragon",
    "fairy": "Fée",
    "colorless": "Incolore",
}

# Rôles (partition), dans l'ordre d'affichage.
ROLE_ATTACKER = "attaquant"
ROLE_WALL = "mur"
ROLE_SUPPORT = "soutien"
ROLE_ENERGY = "energie"
ROLE_LABELS = {
    ROLE_ATTACKER: "Attaquants",
    ROLE_WALL: "Murs",
    ROLE_SUPPORT: "Soutien",
    ROLE_ENERGY: "Énergies",
}

# Types de carte (supertype), dans l'ordre d'affichage.
SUPERTYPE_POKEMON = "pokemon"
SUPERTYPE_TRAINER = "dresseur"
SUPERTYPE_ENERGY = "energie"
SUPERTYPE_LABELS = {
    SUPERTYPE_POKEMON: "Pokémon",
    SUPERTYPE_TRAINER: "Dresseur",
    SUPERTYPE_ENERGY: "Énergie",
}

# Stades d'évolution (regroupés depuis TCGdex `stage`).
STAGE_BASE = "base"
STAGE_ONE = "stage1"
STAGE_TWO = "stage2"
STAGE_OTHER = "autre"
STAGE_LABELS = {
    STAGE_BASE: "De base",
    STAGE_ONE: "Niveau 1",
    STAGE_TWO: "Niveau 2",
    STAGE_OTHER: "Autre",
}
_STAGE_ONE_NAMES = {"niveau 1", "stage 1"}
_STAGE_TWO_NAMES = {"niveau 2", "stage 2"}
_STAGE_BASE_NAMES = {"base", "basic"}


@dataclass
class StatsCardInput:
    """Une entrée de deck aplatie pour le calcul des agrégats — tout ce dont `compute` a besoin,
    déjà lu du catalogue et de la valorisation par la couche service (`pbm_api.decks.service`)."""

    card_id: object
    name: str
    supertype: str | None
    energy_type: str | None
    stage: str | None
    hp: int | None
    element_type: str | None
    attacks: list | None
    rule_marker: str | None
    quantity: int
    # Prix de référence EUR d'un exemplaire (variante `normal`), tel que renvoyé par
    # `pbm_api.pricing.valuation.bulk_reference_prices_eur`. `None` = aucun relevé exploitable :
    # jamais une valeur inventée (risque documenté du lot prix).
    reference_price_eur: Decimal | None = None


@dataclass
class StatBucket:
    key: str
    label: str
    count: int


@dataclass
class DeckValue:
    total_eur: Decimal | None
    priced_cards: int
    missing_price_cards: int
    priced_copies: int
    counted_copies: int


@dataclass
class DeckStats:
    card_count: int
    distinct_cards: int
    by_supertype: list[StatBucket] = field(default_factory=list)
    by_role: list[StatBucket] = field(default_factory=list)
    type_distribution: list[StatBucket] = field(default_factory=list)
    untyped_pokemon: int = 0
    attack_cost_curve: list[StatBucket] = field(default_factory=list)
    attacks_counted: int = 0
    average_hp: float | None = None
    pokemon_with_hp: int = 0
    stage_distribution: list[StatBucket] = field(default_factory=list)
    has_basic_pokemon: bool = False
    evolution_copies_without_base: int = 0
    special_cards: int = 0
    duplicate_copies: int = 0
    duplicate_ratio: float = 0.0
    value: DeckValue = field(
        default_factory=lambda: DeckValue(None, 0, 0, 0, 0)
    )


def _is_pokemon(supertype: str | None) -> bool:
    return energy.normalize(supertype) in _POKEMON_SUPERTYPES


def _supertype_key(supertype: str | None) -> str:
    if energy.is_energy(supertype):
        return SUPERTYPE_ENERGY
    if _is_pokemon(supertype):
        return SUPERTYPE_POKEMON
    return SUPERTYPE_TRAINER


def _has_attacks(attacks: list | None) -> bool:
    return isinstance(attacks, list) and len(attacks) > 0


def _role_key(card: StatsCardInput) -> str:
    """Partition en un rôle unique, dans cet ordre de priorité :

    1. Énergie (de base ou spéciale) → `energie` ;
    2. carte non-Pokémon (Dresseur) → `soutien` ;
    3. Pokémon à PV ≥ `WALL_HP_THRESHOLD` → `mur` (proxy défensif) ;
    4. Pokémon qui possède au moins une attaque → `attaquant` ;
    5. Pokémon restant (aucune attaque : joué pour son talent ou son banc) → `soutien`.
    """
    if energy.is_energy(card.supertype):
        return ROLE_ENERGY
    if not _is_pokemon(card.supertype):
        return ROLE_SUPPORT
    if card.hp is not None and card.hp >= WALL_HP_THRESHOLD:
        return ROLE_WALL
    if _has_attacks(card.attacks):
        return ROLE_ATTACKER
    return ROLE_SUPPORT


def _stage_key(stage: str | None) -> str:
    normalized = energy.normalize(stage)
    if normalized in _STAGE_BASE_NAMES:
        return STAGE_BASE
    if normalized in _STAGE_ONE_NAMES:
        return STAGE_ONE
    if normalized in _STAGE_TWO_NAMES:
        return STAGE_TWO
    return STAGE_OTHER


def _attack_cost(attack: object) -> int | None:
    """Nombre d'énergies d'une attaque (`cost` TCGdex, liste de libellés). `None` si la forme
    n'est pas exploitable — on ne devine pas un coût, on l'ignore (jamais compté à tort)."""
    if not isinstance(attack, dict):
        return None
    cost = attack.get("cost")
    if cost is None:
        return 0  # attaque explicitement sans coût (rare mais réel)
    if isinstance(cost, list):
        return len(cost)
    return None


def _bucketed(counts: dict[str, int], order: list[str], labels: dict[str, str]) -> list[StatBucket]:
    """Seaux dans l'ordre canonique, en n'émettant que ceux qui ont au moins un exemplaire."""
    return [
        StatBucket(key=key, label=labels[key], count=counts[key])
        for key in order
        if counts.get(key, 0) > 0
    ]


def compute(cards: list[StatsCardInput]) -> DeckStats:
    """Agrégats chiffrés d'un deck. Tout est pondéré par la quantité (`quantity`) : un jeu de
    4 exemplaires pèse 4 dans chaque répartition, pas 1."""
    card_count = sum(c.quantity for c in cards)
    stats = DeckStats(card_count=card_count, distinct_cards=len(cards))

    supertype_counts: dict[str, int] = {k: 0 for k in SUPERTYPE_LABELS}
    role_counts: dict[str, int] = {k: 0 for k in ROLE_LABELS}
    element_counts: dict[str, int] = {}
    cost_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {k: 0 for k in STAGE_LABELS}

    hp_weighted_sum = 0
    hp_copies = 0
    attacks_counted = 0
    evolution_copies_without_base = 0
    special_copies = 0
    duplicate_copies = 0

    # Valeur marchande : prix de référence × quantité, hors Énergies de base (fournies, jamais
    # achetées — voir décision D10). Un prix manquant n'est jamais compté 0 : la carte est
    # rangée dans `missing_price_cards`, pour que la valeur affichée reste honnête.
    total_eur: Decimal | None = None
    priced_cards = 0
    missing_price_cards = 0
    priced_copies = 0
    counted_copies = 0

    for c in cards:
        qty = c.quantity
        supertype_counts[_supertype_key(c.supertype)] += qty
        role_counts[_role_key(c)] += qty

        is_basic_energy = energy.is_basic_energy(c.supertype, c.name, c.energy_type)
        is_special_energy = energy.is_special_energy(c.supertype, c.name, c.energy_type)

        if _is_pokemon(c.supertype):
            if c.element_type and c.element_type in ELEMENT_LABELS:
                element_counts[c.element_type] = element_counts.get(c.element_type, 0) + qty
            else:
                stats.untyped_pokemon += qty

            if c.hp is not None:
                hp_weighted_sum += c.hp * qty
                hp_copies += qty

            stage_counts[_stage_key(c.stage)] += qty

            if isinstance(c.attacks, list):
                for attack in c.attacks:
                    cost = _attack_cost(attack)
                    if cost is None:
                        continue
                    bucket = str(cost) if cost < MAX_COST_BUCKET else f"{MAX_COST_BUCKET}+"
                    cost_counts[bucket] = cost_counts.get(bucket, 0) + qty
                    attacks_counted += qty

        if c.rule_marker or is_special_energy:
            special_copies += qty

        # Doublons « utilisés » : exemplaires au-delà du premier d'une carte, hors Énergie
        # de base (toujours en multiples, ce ne sont pas des doublons de collection).
        if not is_basic_energy:
            duplicate_copies += max(0, qty - 1)
            counted_copies += qty
            if c.reference_price_eur is not None:
                priced_cards += 1
                priced_copies += qty
                total_eur = (total_eur or Decimal("0")) + c.reference_price_eur * qty
            else:
                missing_price_cards += 1

    stats.has_basic_pokemon = stage_counts[STAGE_BASE] > 0
    if not stats.has_basic_pokemon:
        evolution_copies_without_base = stage_counts[STAGE_ONE] + stage_counts[STAGE_TWO]

    stats.by_supertype = _bucketed(
        supertype_counts, [SUPERTYPE_POKEMON, SUPERTYPE_TRAINER, SUPERTYPE_ENERGY], SUPERTYPE_LABELS
    )
    stats.by_role = _bucketed(
        role_counts, [ROLE_ATTACKER, ROLE_WALL, ROLE_SUPPORT, ROLE_ENERGY], ROLE_LABELS
    )
    stats.type_distribution = sorted(
        (
            StatBucket(key=code, label=ELEMENT_LABELS[code], count=count)
            for code, count in element_counts.items()
        ),
        key=lambda b: (-b.count, b.label),
    )
    cost_order = [str(i) for i in range(MAX_COST_BUCKET)] + [f"{MAX_COST_BUCKET}+"]
    stats.attack_cost_curve = [
        StatBucket(key=bucket, label=bucket, count=cost_counts[bucket])
        for bucket in cost_order
        if cost_counts.get(bucket, 0) > 0
    ]
    stats.attacks_counted = attacks_counted
    stats.stage_distribution = _bucketed(
        stage_counts, [STAGE_BASE, STAGE_ONE, STAGE_TWO, STAGE_OTHER], STAGE_LABELS
    )
    stats.evolution_copies_without_base = evolution_copies_without_base
    stats.special_cards = special_copies
    stats.pokemon_with_hp = hp_copies
    if hp_copies > 0:
        stats.average_hp = round(hp_weighted_sum / hp_copies, 1)

    stats.duplicate_copies = duplicate_copies
    stats.duplicate_ratio = round(duplicate_copies / counted_copies, 4) if counted_copies else 0.0

    if total_eur is not None:
        total_eur = total_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    stats.value = DeckValue(
        total_eur=total_eur,
        priced_cards=priced_cards,
        missing_price_cards=missing_price_cards,
        priced_copies=priced_copies,
        counted_copies=counted_copies,
    )
    return stats
