"""Adaptateur **catalogue → familles de coups** : le :class:`CatalogueJeu` d'une partie.

Les familles de coups du moteur (``pbm_game.actions.familles_jeu``) ont besoin, pour **lister** ce
qui est jouable (poser, évoluer, attacher, attaquer, battre en retraite, placer), des définitions de
carte des deux decks : Pokémon (:class:`~pbm_game.cartes.modele.DefinitionCarte`) et Énergies
(:class:`~pbm_game.cartes.energie.DefinitionEnergie`). Le moteur étant **pur** (il ne lit jamais la
base), c'est ici qu'on extrait ces définitions du catalogue, **une fois par partie**, à partir des
cartes réellement présentes dans l'état.

Une carte dont la définition ne se compile pas (donnée manquante, marqueur inconnu, Énergie spéciale
non scriptée) est **omise** du catalogue (D9) : les familles ne produisent alors **aucun** coup avec
elle — elle n'est pas jouée de travers. La construction de deck (``games.construction``) refuse déjà
ces cartes en amont, donc en pratique le catalogue d'une partie est complet.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from pbm_game.actions.familles_jeu import CatalogueJeu
from pbm_game.state.modele import EtatPartie, PokemonEnJeu
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks.energy import is_energy
from pbm_api.jeu.catalogue import definition_depuis_card, definition_energie_depuis_card
from pbm_api.models import Card


def _refs_pokemon(pokemon: PokemonEnJeu) -> Iterable[str]:
    for carte in pokemon.cartes:
        yield carte.ref
    for energie in pokemon.energies:
        yield energie.ref
    if pokemon.outil is not None:
        yield pokemon.outil.ref


def refs_etat(etat: EtatPartie) -> set[str]:
    """Toutes les ``ref`` de carte présentes dans l'état (toutes zones, les deux joueurs).

    Le catalogue d'une partie doit couvrir **toute** carte qu'un joueur pourrait jouer : main et
    Pokémon en jeu surtout, mais aussi pioche/défausse/récompenses (pour rester stable quelle que
    soit la zone où une carte se trouve au moment où on interroge).
    """
    refs: set[str] = set()
    for joueur in etat.joueurs:
        zones = (
            joueur.pioche, joueur.main, joueur.defausse,
            joueur.recompenses, joueur.zone_perdue,
        )
        for zone in zones:
            refs.update(c.ref for c in zone)
        if joueur.actif is not None:
            refs.update(_refs_pokemon(joueur.actif))
        for p in joueur.banc:
            refs.update(_refs_pokemon(p))
    if etat.stade is not None:
        refs.add(etat.stade.ref)
    return {r for r in refs if r}


async def construire_catalogue_jeu(db: AsyncSession, etat: EtatPartie) -> CatalogueJeu:
    """Construit le :class:`CatalogueJeu` d'une partie depuis les cartes de son état.

    Une requête unique bornée aux refs de l'état (``tcgdex_id``/``ptcg_id``/``id``), comme
    ``games.indicateurs.catalogue_affichage``. Chaque carte est classée Pokémon ou Énergie et
    compilée en sa définition ; une carte qui ne compile pas est **omise** (D9).
    """
    refs = refs_etat(etat)
    if not refs:
        return CatalogueJeu()

    ids_uuid: list[uuid.UUID] = []
    for ref in refs:
        try:
            ids_uuid.append(uuid.UUID(ref))
        except ValueError:
            pass
    conditions = [Card.tcgdex_id.in_(refs), Card.ptcg_id.in_(refs)]
    if ids_uuid:
        conditions.append(Card.id.in_(ids_uuid))
    rows = (await db.execute(select(Card).where(or_(*conditions)))).scalars().all()

    index: dict[str, Card] = {}
    for card in rows:
        if card.tcgdex_id:
            index.setdefault(card.tcgdex_id, card)
        if card.ptcg_id:
            index.setdefault(card.ptcg_id, card)
        index.setdefault(str(card.id), card)

    pokemon: dict = {}
    energies: dict = {}
    for ref in refs:
        card = index.get(ref)
        if card is None:
            continue  # ref inconnue du catalogue : jamais devinée (D9).
        try:
            if is_energy(getattr(card, "supertype", None)):
                energies[ref] = definition_energie_depuis_card(card)
            else:
                pokemon[ref] = definition_depuis_card(card)
        except ValueError:
            # Carte non compilable (donnée manquante, Énergie spéciale non scriptée) : omise (D9) —
            # aucune famille ne produira de coup avec elle.
            continue
    return CatalogueJeu(pokemon=pokemon, energies=energies)


__all__ = ["CatalogueJeu", "construire_catalogue_jeu", "refs_etat"]
