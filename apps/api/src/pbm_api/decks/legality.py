"""Contrôle de légalité d'un deck — logique pure, sans accès base.

Socle posé par `v7-decks-api` (60 cartes, 4 exemplaires par nom, possession) ; étendu par
`v7-decks-legalite` :
  - chaque constat porte une **sévérité** (`bloquant` / `avertissement`) : seuls les constats
    bloquants rendent le deck illégal, les avertissements informent sans interdire ;
  - **au moins un Pokémon de base** — un deck sans Pokémon de base ne peut pas démarrer une
    partie (bloquant) ;
  - **légalité par format** (Standard / Étendu / Illimité, `pbm_api.decks.formats`) : une carte
    explicitement hors du format choisi est signalée avec son explication (bloquant) ;
  - **contrefaçons exclues** : les exemplaires signalés contrefaçon (`v6-contrefacon`) ne
    comptent pas dans la possession ; leur exclusion est signalée (avertissement) pour expliquer
    un décompte de possession plus bas que le nombre d'exemplaires réellement en collection.

Une seule implémentation, exposée telle quelle par l'API et destinée à l'écran (risque du lot :
« la même règle côté serveur et côté écran ») : jamais deux logiques qui divergent. Recalculé à
chaque lecture, aucune légalité n'est mémorisée — une carte vendue ou signalée contrefaçon rend
le deck injouable sans écriture (« revalidation quand la collection change »).
"""

import uuid
from dataclasses import dataclass, field

from pbm_api.decks import energy, formats

DECK_SIZE = 60
MAX_COPIES_PER_NAME = 4

# Sévérités : seul `BLOCKING` retire la légalité ; `WARNING` informe sans interdire.
BLOCKING = "bloquant"
WARNING = "avertissement"

# Codes de constat (stables, réutilisés par l'écran).
CODE_DECK_SIZE = "deck_size"
CODE_COPY_LIMIT = "copy_limit"
CODE_NOT_OWNED = "not_owned"
CODE_NO_BASIC_POKEMON = "no_basic_pokemon"
CODE_OUT_OF_FORMAT = "out_of_format"
CODE_COUNTERFEIT_EXCLUDED = "counterfeit_excluded"
CODE_UNSUPPORTED_EFFECT = "unsupported_effect"

_POKEMON_SUPERTYPES = {"pokemon"}
_BASIC_STAGES = {"base", "basic"}


def is_basic_pokemon(supertype: str | None, stage: str | None) -> bool:
    """Vrai pour un Pokémon au stade de base (TCGdex `stage="Base"`, en anglais `"Basic"`)."""
    if energy.normalize(supertype) not in _POKEMON_SUPERTYPES:
        return False
    return energy.normalize(stage) in _BASIC_STAGES


@dataclass(frozen=True)
class DeckCardFact:
    """Une entrée de deck enrichie de ce qu'il faut pour juger sa légalité.

    `stage`/`legal_standard`/`legal_expanded` viennent du catalogue ; `counterfeit_owned` est le
    nombre d'exemplaires possédés mais signalés contrefaçon (déjà exclus de `owned`)."""

    card_id: uuid.UUID
    name: str
    supertype: str | None
    energy_type: str | None
    quantity: int
    owned: int
    stage: str | None = None
    legal_standard: bool | None = None
    legal_expanded: bool | None = None
    counterfeit_owned: int = 0


@dataclass
class LegalityIssue:
    code: str
    message: str
    severity: str = BLOCKING
    card_id: uuid.UUID | None = None
    card_name: str | None = None
    detail: dict | None = None


@dataclass
class CardLegality:
    card_id: uuid.UUID
    name: str
    quantity: int
    is_basic_energy: bool
    is_special_energy: bool
    is_basic_pokemon: bool
    owned: int
    missing: int
    in_collection: bool
    in_format: bool
    counterfeit_excluded: int


@dataclass
class DeckLegality:
    legal: bool
    card_count: int
    size_ok: bool
    format: str
    format_label: str
    issues: list[LegalityIssue] = field(default_factory=list)
    cards: list[CardLegality] = field(default_factory=list)


def unsupported_card_ids(facts: list[DeckCardFact]) -> set[uuid.UUID]:
    """Cartes dont l'effet n'est pas pris en charge par le moteur de règles (`v7-regles-cartes`).

    Point d'intégration : tant que le moteur n'existe pas dans le dépôt, on ne peut PAS déclarer
    un effet « non pris en charge » (sans moteur ce serait tous les effets — un deck jamais
    légal, absurde). On retourne l'ensemble vide, et le rapport ne porte aucune issue de ce type.
    S'activera en remplaçant ce corps par un appel au moteur — report explicite, pas un repli
    silencieux : une dépendance non encore livrée."""
    return set()


def evaluate(
    facts: list[DeckCardFact], deck_format: str = formats.DEFAULT_FORMAT
) -> DeckLegality:
    if not formats.is_valid(deck_format):
        deck_format = formats.DEFAULT_FORMAT
    card_count = sum(f.quantity for f in facts)
    issues: list[LegalityIssue] = []
    cards: list[CardLegality] = []
    has_basic_pokemon = False

    # Détail par carte : possession, format, contrefaçon.
    for f in facts:
        basic_e = energy.is_basic_energy(f.supertype, f.name, f.energy_type)
        special_e = energy.is_special_energy(f.supertype, f.name, f.energy_type)
        basic_p = is_basic_pokemon(f.supertype, f.stage)
        if basic_p:
            has_basic_pokemon = True
        # Énergie de base : fournie, jamais un manque de possession.
        missing = 0 if basic_e else max(0, f.quantity - f.owned)
        in_fmt = formats.card_in_format(
            deck_format,
            is_basic_energy=basic_e,
            legal_standard=f.legal_standard,
            legal_expanded=f.legal_expanded,
        )
        cards.append(
            CardLegality(
                card_id=f.card_id,
                name=f.name,
                quantity=f.quantity,
                is_basic_energy=basic_e,
                is_special_energy=special_e,
                is_basic_pokemon=basic_p,
                owned=f.owned,
                missing=missing,
                in_collection=f.owned > 0,
                in_format=in_fmt,
                counterfeit_excluded=f.counterfeit_owned,
            )
        )
        if missing > 0:
            issues.append(
                LegalityIssue(
                    code=CODE_NOT_OWNED,
                    severity=BLOCKING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"required": f.quantity, "owned": f.owned, "missing": missing},
                    message=(
                        f"Il manque {missing} exemplaire(s) de « {f.name} » dans votre "
                        f"collection ({f.owned} possédé(s), {f.quantity} dans le deck)."
                    ),
                )
            )
        if f.counterfeit_owned > 0:
            issues.append(
                LegalityIssue(
                    code=CODE_COUNTERFEIT_EXCLUDED,
                    severity=WARNING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"counterfeit": f.counterfeit_owned},
                    message=(
                        f"{f.counterfeit_owned} exemplaire(s) de « {f.name} » signalé(s) comme "
                        f"contrefaçon probable : exclus du décompte de possession."
                    ),
                )
            )
        if not in_fmt:
            issues.append(
                LegalityIssue(
                    code=CODE_OUT_OF_FORMAT,
                    severity=BLOCKING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"format": deck_format},
                    message=(
                        f"« {f.name} » n'est pas autorisée en format "
                        f"{formats.label(deck_format)}."
                    ),
                )
            )

    # Règle des 4 exemplaires par NOM (Énergies de base exclues).
    by_name: dict[str, dict] = {}
    for f in facts:
        if energy.is_basic_energy(f.supertype, f.name, f.energy_type):
            continue
        key = energy.normalize(f.name)
        entry = by_name.setdefault(key, {"count": 0, "name": f.name})
        entry["count"] += f.quantity
    for entry in by_name.values():
        if entry["count"] > MAX_COPIES_PER_NAME:
            issues.append(
                LegalityIssue(
                    code=CODE_COPY_LIMIT,
                    severity=BLOCKING,
                    card_name=entry["name"],
                    detail={"count": entry["count"], "limit": MAX_COPIES_PER_NAME},
                    message=(
                        f"{entry['count']} exemplaires de « {entry['name']} » — maximum "
                        f"{MAX_COPIES_PER_NAME} (les Énergies de base ne sont pas limitées)."
                    ),
                )
            )

    # Effets non pris en charge (désactivé tant que `v7-regles-cartes` n'est pas livré).
    unsupported = unsupported_card_ids(facts)
    if unsupported:
        by_id = {f.card_id: f for f in facts}
        for cid in unsupported:
            name = by_id[cid].name if cid in by_id else str(cid)
            issues.append(
                LegalityIssue(
                    code=CODE_UNSUPPORTED_EFFECT,
                    severity=BLOCKING,
                    card_id=cid,
                    card_name=name,
                    message=(
                        f"« {name} » : effet pas encore pris en charge par le moteur de règles."
                    ),
                )
            )

    # Au moins un Pokémon de base (un deck vide échoue déjà sur la taille : on n'ajoute ce
    # constat que si le deck contient au moins une carte, pour ne pas doubler le bruit).
    if card_count > 0 and not has_basic_pokemon:
        issues.append(
            LegalityIssue(
                code=CODE_NO_BASIC_POKEMON,
                severity=BLOCKING,
                message=(
                    "Un deck doit contenir au moins un Pokémon de base pour pouvoir démarrer "
                    "une partie."
                ),
            )
        )

    # Taille exacte (Énergies de base comprises).
    size_ok = card_count == DECK_SIZE
    if not size_ok:
        if card_count < DECK_SIZE:
            message = (
                f"Il manque {DECK_SIZE - card_count} carte(s) : un deck compte exactement "
                f"{DECK_SIZE} cartes ({card_count} pour l'instant)."
            )
        else:
            message = (
                f"{card_count - DECK_SIZE} carte(s) en trop : un deck compte exactement "
                f"{DECK_SIZE} cartes."
            )
        issues.append(
            LegalityIssue(
                code=CODE_DECK_SIZE,
                severity=BLOCKING,
                detail={"count": card_count, "expected": DECK_SIZE},
                message=message,
            )
        )

    legal = not any(i.severity == BLOCKING for i in issues)
    return DeckLegality(
        legal=legal,
        card_count=card_count,
        size_ok=size_ok,
        format=deck_format,
        format_label=formats.label(deck_format),
        issues=issues,
        cards=cards,
    )
