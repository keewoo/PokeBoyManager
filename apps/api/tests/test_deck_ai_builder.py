"""Réconciliation de la proposition IA d'un deck (mission `v7-deck-ia`) — logique pure, sans base.

Ces tests prouvent que la proposition brute du modèle n'est JAMAIS prise telle quelle : chaque
règle de légalité corrigeable (possession, 4 exemplaires, Pokémon de base, taille) est appliquée
et TRACÉE. Ils échouent tous sans `pbm_api.decks.ai_builder` (le module n'existe pas avant ce lot).
"""

import uuid

from pbm_api.decks.ai_builder import (
    CODE_ADD_BASIC_POKEMON,
    CODE_COPY_CAP,
    CODE_ENERGY_FILL,
    CODE_MUST_INCLUDE,
    CODE_NO_BASIC_POKEMON,
    CODE_OWNED_CAP,
    CODE_TRIMMED,
    CODE_UNKNOWN_REF,
    BasicEnergyOption,
    Candidate,
    DeckProposal,
    ProposalOptions,
    ProposedCard,
    build_prompt,
    reconcile,
)

FIRE_ENERGY_ID = uuid.uuid4()


def _reconcile(proposal, candidates, *, size=10, **kwargs):
    """Réconcilie avec l'unique Énergie Feu et une taille cible petite (10) pour des assertions
    lisibles."""
    return reconcile(proposal, candidates, [_energy_option()], ProposalOptions(size=size, **kwargs))


def _pokemon(
    ref: int, name: str, *, owned: int, basic: bool = True, element: str = "fire"
) -> Candidate:
    return Candidate(
        ref=ref,
        card_id=uuid.uuid4(),
        name=name,
        supertype="Pokémon",
        element_type=element,
        stage="Base" if basic else "Niveau 1",
        hp=60,
        attack_cost=1,
        owned=owned,
        is_basic_pokemon=basic,
        is_basic_energy=False,
    )


def _energy_candidate(ref: int) -> Candidate:
    return Candidate(
        ref=ref,
        card_id=FIRE_ENERGY_ID,
        name="Énergie Feu",
        supertype="Énergie",
        element_type="fire",
        stage=None,
        hp=None,
        attack_cost=None,
        owned=60,
        is_basic_pokemon=False,
        is_basic_energy=True,
    )


def _energy_option() -> BasicEnergyOption:
    return BasicEnergyOption(element="fire", card_id=FIRE_ENERGY_ID, name="Énergie Feu")


def _codes(result) -> set[str]:
    return {c.code for c in result.corrections}


def test_reconcile_fills_deck_to_target_with_basic_energy() -> None:
    pika = _pokemon(0, "Pikachu", owned=4)
    candidates = [pika, _energy_candidate(1)]
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=4, reason="Attaquant principal.")])

    result = reconcile(proposal, candidates, [_energy_option()], ProposalOptions(size=10))

    total = sum(c.quantity for c in result.cards)
    assert total == 10
    assert CODE_ENERGY_FILL in _codes(result)
    energy_qty = next(c.quantity for c in result.cards if c.card_id == FIRE_ENERGY_ID)
    assert energy_qty == 6  # 10 visés - 4 Pokémon
    # une explication d'une ligne par carte, y compris l'Énergie ajoutée
    assert all(c.reason for c in result.cards)


def test_reconcile_caps_copies_at_four_per_name() -> None:
    pika = _pokemon(0, "Pikachu", owned=6)
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=6, reason="Trop d'exemplaires.")])

    result = _reconcile(proposal, [pika, _energy_candidate(1)])

    pika_qty = next(c.quantity for c in result.cards if c.card_id == pika.card_id)
    assert pika_qty == 4
    assert CODE_COPY_CAP in _codes(result)


def test_reconcile_caps_quantity_to_owned() -> None:
    pika = _pokemon(0, "Pikachu", owned=2)
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=5, reason="Plus que possédé.")])

    result = _reconcile(proposal, [pika, _energy_candidate(1)])

    pika_qty = next(c.quantity for c in result.cards if c.card_id == pika.card_id)
    assert pika_qty == 2
    assert CODE_OWNED_CAP in _codes(result)


def test_reconcile_ignores_unknown_ref() -> None:
    pika = _pokemon(0, "Pikachu", owned=4)
    proposal = DeckProposal(
        cards=[
            ProposedCard(ref=0, quantity=2, reason="Existe."),
            ProposedCard(ref=999, quantity=3, reason="Carte inventée hors liste."),
        ]
    )

    result = _reconcile(proposal, [pika, _energy_candidate(1)])

    assert CODE_UNKNOWN_REF in _codes(result)
    assert all(c.card_id in {pika.card_id, FIRE_ENERGY_ID} for c in result.cards)


def test_reconcile_adds_a_basic_pokemon_when_missing() -> None:
    # Le modèle n'a proposé qu'une évolution (pas de Pokémon de base) ; un Pokémon de base est
    # possédé -> il est ajouté, pour que le deck puisse démarrer.
    evolution = _pokemon(0, "Reptincel", owned=3, basic=False)
    basic = _pokemon(1, "Salamèche", owned=3, basic=True)
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=2, reason="Évolution.")])

    result = _reconcile(proposal, [evolution, basic, _energy_candidate(2)])

    assert CODE_ADD_BASIC_POKEMON in _codes(result)
    assert any(c.card_id == basic.card_id for c in result.cards)


def test_reconcile_reports_when_no_basic_pokemon_available() -> None:
    evolution = _pokemon(0, "Reptincel", owned=3, basic=False)
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=2, reason="Évolution seule.")])

    result = _reconcile(proposal, [evolution, _energy_candidate(1)])

    assert CODE_NO_BASIC_POKEMON in _codes(result)


def test_reconcile_honours_must_include() -> None:
    pika = _pokemon(0, "Pikachu", owned=4)
    wanted = _pokemon(1, "Dracaufeu", owned=1)
    proposal = DeckProposal(cards=[ProposedCard(ref=0, quantity=3, reason="Attaquant.")])

    result = _reconcile(
        proposal, [pika, wanted, _energy_candidate(2)], must_include=[wanted.card_id]
    )

    assert CODE_MUST_INCLUDE in _codes(result)
    assert any(c.card_id == wanted.card_id for c in result.cards)


def test_reconcile_trims_oversize_proposal() -> None:
    pika = _pokemon(0, "Pikachu", owned=4)
    proposal = DeckProposal(
        cards=[
            ProposedCard(ref=0, quantity=4, reason="Attaquant."),
            ProposedCard(ref=1, quantity=40, reason="Trop d'énergies."),
        ]
    )

    result = _reconcile(proposal, [pika, _energy_candidate(1)])

    assert sum(c.quantity for c in result.cards) == 10
    assert CODE_TRIMMED in _codes(result)


def test_build_prompt_lists_candidates_and_wishes() -> None:
    pika = _pokemon(0, "Pikachu", owned=4)
    options = ProposalOptions(types=[("fire", 60)], style="agressif", size=60)

    prompt = build_prompt(options, [pika, _energy_candidate(1)], "Standard")

    assert "Pikachu" in prompt
    assert "[0]" in prompt and "[1]" in prompt
    assert "fire" in prompt
    assert "agressif" in prompt
    assert "Standard" in prompt
