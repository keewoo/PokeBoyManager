"""Règles de cartes **particulières** à la construction d'un deck (R-2.3/2.4/2.7/2.8, R-15.22).

Logique **pure** (aucun accès base), comme :mod:`pbm_api.decks.legality` qu'elle alimente. Elle
classe une carte du deck dans sa **catégorie à règle particulière**, à partir des seuls signaux
**structurés** du catalogue — jamais du texte libre (R-13.7 : un nom seul ne tranche pas) :

* **Pokémon** : le marqueur de règle normalisé ``prize_marker`` (calculé à l'import par
  :func:`pbm_api.catalog.prize_marker.normalized_prize_marker`) distingue déjà Radiant,
  Prisme Étoile (◇) et ★ Étoile sans ambiguïté — et ``"inconnu"`` pour une carte à Rule Box que
  la classification n'a pas su ranger (R-13.4/R-15.22) ;
* **Dresseur ACE SPEC** : le ``rule_marker`` **brut** TCGdex (``"ACE SPEC"``), seul signal qui
  désigne un ACE SPEC — un Dresseur n'a pas de ``prize_marker`` (R-15.10, ce n'est pas un Pokémon).

**Le piège du lot, nommé — l'ACE SPEC n'est pas dans le catalogue importé.** Ces règles vivent
dans le texte de la carte, pas toujours dans un champ structuré. Mesuré sur ``pbm_catalogue_ref``
(22 653 cartes, 04/10/2026) : **aucune** carte ne porte ``rule_marker = "ACE SPEC"`` — l'import
ne reçoit pas ce suffixe de TCGdex. La règle R-2.3 est donc **implémentée et testée** (elle mord
dès qu'une carte porte le signal) mais **ne s'applique à aucune carte réelle tant que l'import ne
renseigne pas le marqueur ACE SPEC** : c'est un **écart de données**, documenté ici et dans le
compte rendu, jamais masqué (D9). Radiant, Prisme Étoile et ★ Étoile, eux, sont présents et
contrôlés sur du réel (16/16/24 cartes au catalogue de référence).
"""

from __future__ import annotations

#: Catégories à règle particulière de construction de deck.
ACE_SPEC = "ace_spec"  # R-2.3 — au plus 1 par deck (Dresseur)
RADIANT = "radiant"  # R-2.4 — au plus 1 par deck
PRISME_ETOILE = "prisme_etoile"  # R-2.7 — au plus 1 par NOM
ETOILE = "etoile"  # R-2.8 — au plus 1 par deck, tous noms confondus
RULE_BOX_INCONNU = "rule_box_inconnu"  # R-15.22 — refusée (jamais devinée)

#: `supertype` (brut, langue d'import) qui désigne un Dresseur.
_DRESSEUR_SUPERTYPES = frozenset({"dresseur", "trainer"})

#: `prize_marker` normalisés qui portent une limite de deck PROPRE (R-2.4/2.7/2.8).
_PRIZE_A_LIMITE = frozenset({RADIANT, PRISME_ETOILE, ETOILE})


def _normaliser(valeur: str | None) -> str:
    return (valeur or "").strip().casefold()


def marqueur_special(
    *,
    supertype: str | None,
    rule_marker: str | None,
    prize_marker: str | None,
) -> str | None:
    """La catégorie à règle particulière d'une carte, ou ``None`` si elle n'en porte aucune.

    Pure et déterministe ; ne lit que des signaux **structurés** (jamais le nom seul, R-13.7) :

    * un **Dresseur** dont le ``rule_marker`` brut vaut ``ACE SPEC`` → :data:`ACE_SPEC` (R-15.10) ;
    * un **Pokémon** dont le ``prize_marker`` vaut ``radiant`` / ``prisme_etoile`` / ``etoile`` →
      la catégorie correspondante (R-15.9 / R-15.18 / R-15.21) ;
    * un **Pokémon** dont le ``prize_marker`` vaut ``inconnu`` (Rule Box non classable) →
      :data:`RULE_BOX_INCONNU` (R-13.4 / R-15.22 : refusée, jamais une récompense ou une limite
      devinée) ;
    * tout le reste → ``None`` (carte ordinaire, ou Pokémon ex/GX/V… sans limite de deck PROPRE :
      la règle des 4 exemplaires suffit).
    """
    if _normaliser(supertype) in _DRESSEUR_SUPERTYPES:
        return ACE_SPEC if _normaliser(rule_marker) == "ace spec" else None
    pm = _normaliser(prize_marker)
    if pm in _PRIZE_A_LIMITE:
        return pm
    if pm == "inconnu":
        return RULE_BOX_INCONNU
    return None


__all__ = [
    "ACE_SPEC",
    "RADIANT",
    "PRISME_ETOILE",
    "ETOILE",
    "RULE_BOX_INCONNU",
    "marqueur_special",
]
