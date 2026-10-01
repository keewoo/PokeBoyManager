"""Invariants vérifiables d'un état de partie.

``verifier(etat)`` renvoie la **liste des violations** (vide = état sain) ; elle ne lève
pas, pour qu'on puisse l'appeler en masse. ``assert_invariants(etat)`` lève
:class:`InvariantViole` dès qu'il y en a une — c'est la forme qu'utilise la suite de
tests du moteur après chaque action (critère d'acceptation).

Invariants (règles de ``docs/jeu/REGLES.md``) :

* exactement deux joueurs, d'identifiants distincts ;
* banc ≤ 5 (**R-3.2**) ;
* exactement 1 Actif tant qu'un Pokémon est en jeu — sinon banc vide (**R-3.3**) ;
* au plus 1 Outil par Pokémon (**R-3.7**, par construction ; on contrôle sa cohérence) ;
* un seul Stade en jeu (**R-3.5**, par construction ; on contrôle son propriétaire) ;
* **aucune carte dans deux zones** : chaque ``instance_id`` apparaît au plus une fois ;
* total de cartes par joueur **constant** si on en donne l'attendu (``total_par_joueur``) ;
* au plus un état d'**orientation** par Pokémon (**R-11.8**) ;
* états spéciaux ∈ les cinq connus (**R-11.1**), compteurs de dégâts ≥ 0 (**R-10.4**) ;
* au plus 6 récompenses (**R-3.4**) ;
* tour cohérent : phase connue, numéro ≥ 1, joueur actif présent (**R-5**).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from .modele import (
    ETATS_ORIENTATION,
    ETATS_SPECIAUX,
    PHASES,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
)


class InvariantViole(Exception):
    """Levée par :func:`assert_invariants` quand au moins un invariant est violé."""


def _cartes_pokemon(pokemon: PokemonEnJeu) -> Iterator[Carte]:
    yield from pokemon.cartes
    yield from pokemon.energies
    if pokemon.outil is not None:
        yield pokemon.outil


def _cartes_joueur(joueur: Joueur) -> Iterator[Carte]:
    yield from joueur.pioche
    yield from joueur.main
    yield from joueur.defausse
    yield from joueur.recompenses
    yield from joueur.zone_perdue
    if joueur.actif is not None:
        yield from _cartes_pokemon(joueur.actif)
    for p in joueur.banc:
        yield from _cartes_pokemon(p)


def toutes_les_cartes(etat: EtatPartie) -> list[Carte]:
    """Toutes les cartes de l'état, tous joueurs et le Stade — pour compter / dédupliquer."""
    cartes: list[Carte] = []
    for j in etat.joueurs:
        cartes.extend(_cartes_joueur(j))
    if etat.stade is not None:
        cartes.append(etat.stade)
    return cartes


def total_cartes_joueur(joueur: Joueur) -> int:
    """Nombre total de cartes détenues par un joueur, toutes zones confondues (R-2.1)."""
    return sum(1 for _ in _cartes_joueur(joueur))


def _verifier_pokemon(etiquette: str, pokemon: PokemonEnJeu, violations: list[str]) -> None:
    if not pokemon.cartes:
        violations.append(f"{etiquette} : pile d'évolutions vide (R-3.6).")
    if pokemon.compteurs_degats < 0:
        violations.append(
            f"{etiquette} : compteurs de dégâts négatifs ({pokemon.compteurs_degats}) — R-10.4."
        )
    inconnus = sorted(pokemon.etats_speciaux - ETATS_SPECIAUX)
    if inconnus:
        violations.append(f"{etiquette} : états spéciaux inconnus {inconnus} (R-11.1).")
    orientation = pokemon.etats_speciaux & ETATS_ORIENTATION
    if len(orientation) > 1:
        violations.append(
            f"{etiquette} : {sorted(orientation)} coexistent — un seul état d'orientation (R-11.8)."
        )


def verifier(etat: EtatPartie, *, total_par_joueur: int | None = None) -> list[str]:
    """Renvoie la liste des invariants violés par ``etat`` (liste vide = sain).

    ``total_par_joueur`` : si fourni, exige que **chaque** joueur détienne exactement ce
    nombre de cartes (R-2.1 : 60 en début de partie, constant ensuite). Omis, ce contrôle
    est sauté — un état arbitraire de test de propriété n'a pas forcément 60 cartes.
    """
    violations: list[str] = []

    if len(etat.joueurs) != 2:
        violations.append("Une partie compte exactement deux joueurs.")
    ids = [j.id for j in etat.joueurs]
    if len(set(ids)) != len(ids):
        violations.append(f"Identifiants de joueurs non distincts : {ids}.")

    for joueur in etat.joueurs:
        etiq = f"Joueur « {joueur.id} »"
        if len(joueur.banc) > 5:
            violations.append(f"{etiq} : banc de {len(joueur.banc)} Pokémon (> 5, R-3.2).")
        # R-3.3 : exactement 1 Actif tant qu'un Pokémon est en jeu.
        if joueur.actif is None and joueur.banc:
            violations.append(f"{etiq} : banc non vide sans Actif (R-3.3).")
        if len(joueur.recompenses) > 6:
            violations.append(
                f"{etiq} : {len(joueur.recompenses)} récompenses (> 6, R-3.4)."
            )
        if joueur.actif is not None:
            _verifier_pokemon(f"{etiq} Actif", joueur.actif, violations)
        for i, p in enumerate(joueur.banc):
            _verifier_pokemon(f"{etiq} banc[{i}]", p, violations)
        if total_par_joueur is not None:
            total = total_cartes_joueur(joueur)
            if total != total_par_joueur:
                violations.append(
                    f"{etiq} : {total} cartes au total, {total_par_joueur} attendues (R-2.1)."
                )

    # Aucune carte dans deux zones : chaque instance_id apparaît au plus une fois.
    compteur = Counter(c.instance_id for c in toutes_les_cartes(etat))
    doublons = sorted(iid for iid, n in compteur.items() if n > 1)
    if doublons:
        violations.append(
            f"Cartes présentes dans plusieurs zones (instance_id en double) : {doublons}."
        )

    # Tour (R-5).
    if etat.tour.phase not in PHASES:
        violations.append(f"Phase de tour inconnue : {etat.tour.phase!r} (R-5.1).")
    if etat.tour.numero < 1:
        violations.append(f"Numéro de tour invalide : {etat.tour.numero} (< 1).")
    if etat.tour.joueur_actif not in set(ids):
        violations.append(
            f"Le joueur actif du tour « {etat.tour.joueur_actif} » n'est pas dans la partie."
        )

    # Stade partagé (R-3.5) : un propriétaire nommé doit être un joueur de la partie.
    if etat.stade_proprietaire is not None and etat.stade_proprietaire not in set(ids):
        violations.append(
            f"Propriétaire de Stade « {etat.stade_proprietaire} » absent de la partie (R-3.5)."
        )
    if etat.stade is None and etat.stade_proprietaire is not None:
        violations.append("Propriétaire de Stade renseigné sans Stade en jeu (R-3.5).")

    # Partie terminée figée (R-14.6) : une égalité n'a pas de vainqueur, mais une raison.
    if etat.terminee and etat.vainqueur is None and etat.raison_fin is None:
        violations.append("Partie terminée sans vainqueur ni raison (R-14.6).")

    return violations


def assert_invariants(etat: EtatPartie, *, total_par_joueur: int | None = None) -> None:
    """Lève :class:`InvariantViole` si ``etat`` viole un invariant ; ne renvoie rien sinon."""
    violations = verifier(etat, total_par_joueur=total_par_joueur)
    if violations:
        raise InvariantViole("; ".join(violations))
