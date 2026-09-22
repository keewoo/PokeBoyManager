"""Suggestions de remplacement d'une carte d'un deck (mission `v7-decks-collection-sync`).

Quand une carte manque à un deck, on propose au joueur de la remplacer — mais **jamais en
silence** (risque du lot) : on ne fait que proposer, l'échange reste un geste explicite côté
écran. Les suggestions sont prises **uniquement dans les cartes possédées** (hors contrefaçon),
classées par proximité, chacune accompagnée de la **raison** du classement. Aucun appel IA : le
classement est déterministe (type, rôle, coût d'attaque), et les candidats tiennent en **une
seule requête** (le comptage de possession est groupé, jamais une requête par carte).

Le cœur est une fonction pure (`rank_replacements`) : la même logique est testable sans base, et
la requête ne fait que fournir la matière.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks import energy
from pbm_api.decks.errors import DeckCardNotFoundError, DeckNotFoundError
from pbm_api.decks.legality import is_basic_pokemon
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Set, User

# Pénalité de coût quand l'un des deux n'a pas d'attaque (Dresseur/Énergie vs Pokémon) : on ne
# compare pas un coût à une absence de coût, on la classe simplement après les vraies proximités.
_NO_ATTACK_PENALTY = 99

_SUPERTYPE_POKEMON = "pokemon"


@dataclass(frozen=True)
class CardTraits:
    """Ce qu'il faut d'une carte pour juger si elle en remplace bien une autre."""

    card_id: uuid.UUID
    name: str
    supertype: str | None
    element_type: str | None
    stage: str | None
    energy_type: str | None
    attack_cost: int | None


@dataclass(frozen=True)
class Candidate:
    """Une carte possédée, candidate au remplacement."""

    traits: CardTraits
    owned_count: int
    number: str
    set_name: str
    set_code: str
    hp: int | None
    image_url: str | None


@dataclass(frozen=True)
class Suggestion:
    candidate: Candidate
    reason: str


def attack_cost(attacks: list | None) -> int | None:
    """Coût de l'attaque la moins chère (nombre de symboles d'énergie), `None` si aucune attaque.

    `Card.attacks` est la liste TCGdex : chaque attaque porte un `cost` (liste de symboles). On
    retient le minimum : deux Pokémon dont l'attaque la moins chère coûte autant sont proches à
    jouer, même si l'un a par ailleurs une attaque lourde."""
    if not attacks:
        return None
    costs = [
        len(a["cost"])
        for a in attacks
        if isinstance(a, dict) and isinstance(a.get("cost"), list)
    ]
    return min(costs) if costs else None


def _is_pokemon(supertype: str | None) -> bool:
    return energy.normalize(supertype) == _SUPERTYPE_POKEMON


def _cost_diff(a: int | None, b: int | None) -> int:
    if a is None and b is None:
        return 0
    if a is None or b is None:
        return _NO_ATTACK_PENALTY
    return abs(a - b)


def _reason(target: CardTraits, cand: CardTraits, *, same_element: bool, same_role: bool,
            cost_diff: int) -> str:
    """Phrase courte et vraie : ce qui rapproche vraiment cette carte de celle qu'elle remplace."""
    parts: list[str] = []
    if _is_pokemon(target.supertype):
        if same_element and target.element_type:
            parts.append(f"même type {target.element_type}")
        if same_role:
            role = "Pokémon de base" if is_basic_pokemon(target.supertype, target.stage) \
                else "même stade d'évolution"
            parts.append(role)
    elif energy.is_energy(target.supertype):
        parts.append("Énergie spéciale de remplacement")
    else:
        parts.append(
            f"même catégorie ({target.supertype})" if target.supertype else "même catégorie"
        )

    if target.attack_cost is not None and cand.attack_cost is not None:
        if cost_diff == 0:
            parts.append("coût d'attaque identique")
        else:
            parts.append(f"coût d'attaque proche (±{cost_diff})")
    if not parts:
        parts.append("possédée dans votre collection")
    reason = " · ".join(parts)
    return reason[0].upper() + reason[1:]


def rank_replacements(
    target: CardTraits, candidates: list[Candidate], limit: int
) -> list[Suggestion]:
    """Classe les candidats possédés par proximité à la carte cible (fonction pure, sans base).

    Ordre : même type élémentaire d'abord, puis même rôle, puis coût d'attaque le plus proche,
    puis le plus grand nombre d'exemplaires possédés (un doublon dépanne mieux), puis le nom."""
    target_is_pokemon = _is_pokemon(target.supertype)
    target_basic = is_basic_pokemon(target.supertype, target.stage)

    scored: list[tuple[tuple, Suggestion]] = []
    for cand in candidates:
        if cand.owned_count <= 0 or cand.traits.card_id == target.card_id:
            continue
        same_element = bool(
            target_is_pokemon
            and target.element_type
            and cand.traits.element_type == target.element_type
        )
        if target_is_pokemon:
            same_role = is_basic_pokemon(cand.traits.supertype, cand.traits.stage) == target_basic
        else:
            same_role = True  # même supertype déjà exigé par la requête
        cost_diff = _cost_diff(target.attack_cost, cand.traits.attack_cost)
        score = (
            0 if same_element else 1,
            0 if same_role else 1,
            cost_diff,
            -cand.owned_count,
            energy.normalize(cand.traits.name),
        )
        reason = _reason(
            target, cand.traits, same_element=same_element, same_role=same_role, cost_diff=cost_diff
        )
        scored.append((score, Suggestion(candidate=cand, reason=reason)))

    scored.sort(key=lambda pair: pair[0])
    return [suggestion for _score, suggestion in scored[:limit]]


def _traits_from_card(card: Card) -> CardTraits:
    return CardTraits(
        card_id=card.id,
        name=card.name,
        supertype=card.supertype,
        element_type=card.element_type,
        stage=card.stage,
        energy_type=card.energy_type,
        attack_cost=attack_cost(card.attacks),
    )


async def suggest_replacements(
    session: AsyncSession, user: User, deck_id: uuid.UUID, card_id: uuid.UUID, limit: int = 10
) -> list[Suggestion]:
    """Propose des cartes possédées pour remplacer `card_id` dans `deck_id`.

    Borné au propriétaire : un deck d'un autre utilisateur lève `DeckNotFoundError` (→ 404), une
    carte absente du deck `DeckCardNotFoundError` (→ 404)."""
    deck = await session.get(Deck, deck_id)
    if deck is None or deck.user_id != user.id:
        raise DeckNotFoundError
    in_deck = await session.execute(
        select(DeckCard.id).where(DeckCard.deck_id == deck_id, DeckCard.card_id == card_id)
    )
    if in_deck.scalar_one_or_none() is None:
        raise DeckCardNotFoundError
    target_card = await session.get(Card, card_id)
    if target_card is None:  # référencé par le deck (RESTRICT) : ne devrait pas arriver
        raise DeckCardNotFoundError
    target = _traits_from_card(target_card)

    # UNE seule requête : les cartes possédées (hors contrefaçon) de même supertype, avec leur
    # nombre d'exemplaires — jamais une requête de possession par carte.
    supertype_clause = (
        Card.supertype == target.supertype
        if target.supertype is not None
        else Card.supertype.is_(None)
    )
    rows = (
        await session.execute(
            select(
                Card.id,
                Card.name,
                Card.number,
                Card.supertype,
                Card.element_type,
                Card.stage,
                Card.energy_type,
                Card.attacks,
                Card.hp,
                Card.image_url,
                Set.name,
                Set.code,
                func.count(CollectionItem.id),
            )
            .join(CollectionItem, CollectionItem.card_id == Card.id)
            .join(Set, Set.id == Card.set_id)
            .where(
                CollectionItem.user_id == user.id,
                CollectionItem.counterfeit_suspected.is_(False),
                Card.id != card_id,
                supertype_clause,
            )
            .group_by(Card.id, Set.name, Set.code)
        )
    ).all()

    candidates = [
        Candidate(
            traits=CardTraits(
                card_id=cid,
                name=name,
                supertype=supertype,
                element_type=element_type,
                stage=stage,
                energy_type=energy_type,
                attack_cost=attack_cost(attacks),
            ),
            owned_count=owned_count,
            number=number,
            set_name=set_name,
            set_code=set_code,
            hp=hp,
            image_url=image_url,
        )
        for (
            cid,
            name,
            number,
            supertype,
            element_type,
            stage,
            energy_type,
            attacks,
            hp,
            image_url,
            set_name,
            set_code,
            owned_count,
        ) in rows
    ]
    return rank_replacements(target, candidates, limit)
