"""Contrôle de légalité d'un deck — logique pure, sans accès base (mission `v7-decks-api`).

Prend des faits déjà chargés (`DeckCardFact` : carte + quantité + nombre possédé) et rend un
rapport lisible. Séparé de `service.py` pour être testable sans base et réutilisable par la
liste comme par le détail. Recalculé à chaque lecture : aucune légalité n'est mémorisée, donc
une carte vendue rend le deck injouable sans écriture (« revalidation quand la collection
change », mission point 3).

Règles (décision D10) :
  - exactement **60** cartes (Énergies de base comprises) ;
  - **4** exemplaires maximum d'une même carte *par son nom*, **sauf Énergies de base**
    (illimitées) ;
  - un deck ne peut contenir que des cartes **possédées**, sauf les Énergies de base (fournies) ;
    le manque est signalé, jamais corrigé en silence ;
  - une carte dont l'effet n'est pas pris en charge par le moteur de règles (`v7-regles-cartes`)
    est refusée — voir `unsupported_card_ids` (désactivé tant que le moteur n'existe pas).
"""

import uuid
from dataclasses import dataclass, field

from pbm_api.decks import energy

DECK_SIZE = 60
MAX_COPIES_PER_NAME = 4


@dataclass(frozen=True)
class DeckCardFact:
    """Une entrée de deck enrichie de ce qu'il faut pour juger sa légalité."""

    card_id: uuid.UUID
    name: str
    supertype: str | None
    energy_type: str | None
    quantity: int
    owned: int  # exemplaires de CETTE carte (card_id) possédés par le propriétaire du deck


@dataclass
class LegalityIssue:
    code: str  # "deck_size" | "copy_limit" | "not_owned" | "unsupported_effect"
    message: str
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
    owned: int
    missing: int
    in_collection: bool


@dataclass
class DeckLegality:
    legal: bool
    card_count: int
    size_ok: bool
    issues: list[LegalityIssue] = field(default_factory=list)
    cards: list[CardLegality] = field(default_factory=list)


def unsupported_card_ids(facts: list[DeckCardFact]) -> set[uuid.UUID]:
    """Cartes dont l'effet n'est pas pris en charge par le moteur de règles.

    Point d'intégration de `v7-regles-cartes` : tant que le moteur n'existe pas dans ce dépôt,
    on ne peut PAS déclarer un effet « non pris en charge » (sans moteur, ce serait tous les
    effets — un deck jamais légal, absurde). On retourne donc l'ensemble vide, et le report ne
    porte aucune issue de ce type. Report explicite dans le compte rendu du lot : cette
    vérification s'activera quand le moteur atterrira, en remplaçant ce corps par un appel au
    moteur — pas un repli silencieux, une dépendance non encore livrée."""
    return set()


def evaluate(facts: list[DeckCardFact]) -> DeckLegality:
    card_count = sum(f.quantity for f in facts)
    issues: list[LegalityIssue] = []
    cards: list[CardLegality] = []

    # Détail par carte + collecte des manques de possession.
    for f in facts:
        basic = energy.is_basic_energy(f.supertype, f.name, f.energy_type)
        special = energy.is_special_energy(f.supertype, f.name, f.energy_type)
        # Énergie de base : fournie, jamais un manque de possession.
        missing = 0 if basic else max(0, f.quantity - f.owned)
        cards.append(
            CardLegality(
                card_id=f.card_id,
                name=f.name,
                quantity=f.quantity,
                is_basic_energy=basic,
                is_special_energy=special,
                owned=f.owned,
                missing=missing,
                in_collection=f.owned > 0,
            )
        )
        if missing > 0:
            issues.append(
                LegalityIssue(
                    code="not_owned",
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"required": f.quantity, "owned": f.owned, "missing": missing},
                    message=(
                        f"Il manque {missing} exemplaire(s) de « {f.name} » dans votre "
                        f"collection ({f.owned} possédé(s), {f.quantity} dans le deck)."
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
                    code="copy_limit",
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
                    code="unsupported_effect",
                    card_id=cid,
                    card_name=name,
                    message=(
                        f"« {name} » : effet pas encore pris en charge par le moteur "
                        f"de règles."
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
                code="deck_size",
                detail={"count": card_count, "expected": DECK_SIZE},
                message=message,
            )
        )

    return DeckLegality(
        legal=not issues,
        card_count=card_count,
        size_ok=size_ok,
        issues=issues,
        cards=cards,
    )
