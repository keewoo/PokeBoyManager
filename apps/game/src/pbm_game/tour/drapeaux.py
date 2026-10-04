"""Drapeaux et prédicats du tour — la couche **sans jugement** de la machine à tour.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``, et
volontairement **sans dépendance au paquet ``pbm_game.actions``** : il ne porte que des
booléens et des fabriques de :class:`~pbm_game.state.Tour`. C'est ce qui permet aux
transitions (``pbm_game.journal.transitions``) de l'importer sans créer de cycle, là où
:mod:`pbm_game.tour.contraintes` — qui rend des :class:`~pbm_game.actions.Verdict` motivés —
ne le pourrait pas.

Deux familles de fonctions :

* des **prédicats** qui lisent l'état du tour (« l'énergie est-elle déjà posée ? », « est-ce
  le premier tour du joueur qui commence ? ») — ils ne décident de rien, ils constatent ;
* des **marqueurs** qui renvoient un **nouveau** :class:`~pbm_game.state.Tour` avec un
  drapeau levé (``Tour`` est figé : on ne mute jamais, on remplace), à l'usage des lots de
  résolution quand l'action correspondante (attacher, jouer un Supporter, battre en retraite,
  poser un Pokémon) sera réellement appliquée.

Règles servies : **R-5.4** (une énergie/tour), **R-5.5** (un Supporter/tour), **R-5.6** (une
retraite/tour), **R-6.1/6.2/6.5** (règle du premier tour), **R-7.3** (pas d'évolution le tour
d'entrée en jeu).
"""

from __future__ import annotations

from dataclasses import replace

from ..state.modele import PokemonEnJeu, Tour

# --- Identité d'un Pokémon en jeu --------------------------------------------


def identite_pokemon(pokemon: PokemonEnJeu) -> str:
    """L'identité **stable** d'un Pokémon en jeu : l'``instance_id`` de sa carte de base.

    La carte de base (``cartes[0]``) reste la même à travers toutes les évolutions (R-7.1) ;
    c'est donc elle qui identifie le Pokémon de façon continue, là où ``carte_active`` change
    à chaque évolution. On s'en sert pour suivre « ce Pokémon est-il entré en jeu ce tour ? »
    (R-7.3) à travers d'éventuelles évolutions ultérieures.
    """
    if not pokemon.cartes:
        raise ValueError("Un Pokémon en jeu a toujours au moins une carte dans sa pile (R-3.6).")
    return pokemon.cartes[0].instance_id


# --- Prédicats « premier tour » (dérivés du seul numéro, voir Tour) ----------


def est_premier_tour_du_joueur_qui_commence(tour: Tour) -> bool:
    """Vrai au **premier tour du joueur qui commence** (numéro 1) — portée de R-6.1/R-6.2.

    Seul ce joueur-là est privé d'attaque (R-6.1) et de Supporter (R-6.2) à son premier tour ;
    le second joueur, lui, le peut dès son premier tour (numéro 2).
    """
    return tour.numero == 1


def est_premier_tour_du_joueur_actif(tour: Tour) -> bool:
    """Vrai si le tour courant est le **premier tour du joueur actif** — portée de R-6.5.

    Le premier tour de chaque joueur est le numéro 1 (joueur qui commence) ou 2 (l'autre) :
    **aucun** joueur ne peut faire évoluer à son premier tour (R-6.5).
    """
    return tour.numero <= 2


# --- Prédicats « une fois par tour » / entrée en jeu -------------------------


def energie_deja_posee(tour: Tour) -> bool:
    """Vrai si l'énergie du tour a déjà été attachée (R-5.4)."""
    return tour.energie_posee


def supporter_deja_joue(tour: Tour) -> bool:
    """Vrai si un Supporter a déjà été joué ce tour (R-5.5)."""
    return tour.supporter_joue


def retraite_deja_faite(tour: Tour) -> bool:
    """Vrai si une retraite a déjà eu lieu ce tour (R-5.6)."""
    return tour.retraite_faite


def pokemon_entre_ce_tour(tour: Tour, base_id: str) -> bool:
    """Vrai si le Pokémon d'identité ``base_id`` est entré en jeu pendant CE tour (R-7.3)."""
    return base_id in tour.entres_en_jeu_ce_tour


def pokemon_evolue_ce_tour(tour: Tour, base_id: str) -> bool:
    """Vrai si le Pokémon d'identité ``base_id`` a déjà évolué pendant CE tour (R-7.4)."""
    return base_id in tour.evolues_ce_tour


def talent_active_ce_tour(tour: Tour, cle: str) -> bool:
    """Vrai si le talent de clé ``cle`` (``« identité|nom »``) a déjà été activé CE tour (R-5).

    Le suivi est **par Pokémon** (la clé porte l'identité du porteur), pas par joueur : un
    autre Pokémon portant le même talent garde son propre usage du tour.
    """
    return cle in tour.talents_actives_ce_tour


# --- Marqueurs : lèvent un drapeau en renvoyant un NOUVEAU Tour --------------


def marquer_energie_posee(tour: Tour) -> Tour:
    """Renvoie un tour où l'énergie du tour est marquée comme posée (R-5.4)."""
    return replace(tour, energie_posee=True)


def marquer_supporter_joue(tour: Tour) -> Tour:
    """Renvoie un tour où le Supporter du tour est marqué comme joué (R-5.5)."""
    return replace(tour, supporter_joue=True)


def marquer_retraite_faite(tour: Tour) -> Tour:
    """Renvoie un tour où la retraite du tour est marquée comme faite (R-5.6)."""
    return replace(tour, retraite_faite=True)


def marquer_entree_en_jeu(tour: Tour, base_id: str) -> Tour:
    """Renvoie un tour où ``base_id`` est noté comme entré en jeu ce tour (R-7.3)."""
    return replace(tour, entres_en_jeu_ce_tour=tour.entres_en_jeu_ce_tour | {base_id})


def marquer_evolution(tour: Tour, base_id: str) -> Tour:
    """Renvoie un tour où ``base_id`` est noté comme ayant évolué ce tour (R-7.4)."""
    return replace(tour, evolues_ce_tour=tour.evolues_ce_tour | {base_id})


def marquer_talent_active(tour: Tour, cle: str) -> Tour:
    """Renvoie un tour où le talent de clé ``cle`` est noté comme activé ce tour (R-5)."""
    return replace(tour, talents_actives_ce_tour=tour.talents_actives_ce_tour | {cle})


__all__ = [
    "identite_pokemon",
    "est_premier_tour_du_joueur_qui_commence",
    "est_premier_tour_du_joueur_actif",
    "energie_deja_posee",
    "supporter_deja_joue",
    "retraite_deja_faite",
    "pokemon_entre_ce_tour",
    "pokemon_evolue_ce_tour",
    "talent_active_ce_tour",
    "marquer_energie_posee",
    "marquer_supporter_joue",
    "marquer_retraite_faite",
    "marquer_entree_en_jeu",
    "marquer_evolution",
    "marquer_talent_active",
]
