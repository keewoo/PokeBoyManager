"""Classement des suggestions de remplacement — logique pure (mission `v7-decks-collection-sync`).

Ces tests ne touchent pas la base : ils fixent le comportement du cœur déterministe
(`rank_replacements`), celui qui doit rester identique quelle que soit la requête qui le nourrit.
Ils échouent si le classement n'ordonne plus par type → rôle → coût d'attaque, ou si une carte
non possédée se glisse dans les suggestions.
"""

import uuid

from pbm_api.decks.replacements import (
    Candidate,
    CardTraits,
    attack_cost,
    rank_replacements,
)


def _traits(name, *, supertype="Pokémon", element=None, stage=None, energy_type=None, cost=None):
    return CardTraits(
        card_id=uuid.uuid4(),
        name=name,
        supertype=supertype,
        element_type=element,
        stage=stage,
        energy_type=energy_type,
        attack_cost=cost,
    )


def _cand(traits, owned=1):
    return Candidate(
        traits=traits,
        owned_count=owned,
        number="1",
        set_name="Set test",
        set_code="TST",
        hp=60,
        image_url=None,
    )


def test_attack_cost_takes_cheapest_attack():
    attacks = [
        {"name": "Tonnerre", "cost": ["Lightning", "Lightning", "Colorless"]},
        {"name": "Éclair", "cost": ["Lightning"]},
    ]
    assert attack_cost(attacks) == 1
    assert attack_cost(None) is None
    assert attack_cost([]) is None
    assert attack_cost([{"name": "Talent sans coût"}]) is None  # aucune clé `cost`


def test_ranks_by_type_then_role_then_cost():
    target = _traits("Pikachu", element="Lightning", stage="Base", cost=1)
    same = _cand(_traits("Voltali", element="Lightning", stage="Base", cost=1))
    same_element_evo = _cand(_traits("Raichu", element="Lightning", stage="Niveau 1", cost=2))
    other_element = _cand(_traits("Salamèche", element="Fire", stage="Base", cost=1), owned=3)

    ranked = rank_replacements(target, [other_element, same_element_evo, same], limit=10)

    names = [s.candidate.traits.name for s in ranked]
    # Même type ET même rôle d'abord ; puis même type mais évolution ; le type différent en dernier
    # (même si possédé en plus d'exemplaires — le type prime sur le nombre).
    assert names == ["Voltali", "Raichu", "Salamèche"]
    assert "même type Lightning".lower() in ranked[0].reason.lower()
    assert "coût d'attaque identique" in ranked[0].reason


def test_excludes_target_and_unowned_and_respects_limit():
    target = _traits("Pikachu", element="Lightning", stage="Base", cost=1)
    itself = _cand(CardTraits(target.card_id, "Pikachu", "Pokémon", "Lightning", "Base", None, 1))
    unowned = _cand(_traits("Voltali", element="Lightning", stage="Base", cost=1), owned=0)
    real = _cand(_traits("Élecsprint", element="Lightning", stage="Base", cost=1))

    ranked = rank_replacements(target, [itself, unowned, real], limit=10)
    ids = [s.candidate.traits.card_id for s in ranked]
    assert target.card_id not in ids  # jamais se remplacer soi-même
    assert all(s.candidate.owned_count > 0 for s in ranked)  # jamais une carte non possédée
    assert len(ranked) == 1 and ranked[0].candidate.traits.name == "Élecsprint"

    limited = rank_replacements(
        target,
        [_cand(_traits(f"Carte {i}", element="Lightning", stage="Base", cost=1)) for i in range(5)],
        limit=2,
    )
    assert len(limited) == 2
