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
from pbm_game.effets.outils import registre_outils
from pbm_game.effets.stades import registre_stades
from pbm_game.state.modele import EtatPartie, PokemonEnJeu
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks.energy import is_energy
from pbm_api.jeu.catalogue import (
    definition_depuis_card,
    definition_energie_depuis_card,
    definition_objet_depuis_card,
    definition_outil_depuis_card,
    definition_stade_depuis_card,
    definition_supporter_depuis_card,
    genre_dresseur,
)
from pbm_api.jeu.couverture_jeu import fiche_talent_active
from pbm_api.jeu.scripts.empreinte import ORIGINE_ATTAQUE, ORIGINE_DRESSEUR, effets_scriptables
from pbm_api.jeu.scripts.programmes import programme_depuis_json, scripts_valides_par_empreinte
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
    objets: dict = {}
    supporters: dict = {}
    stades: dict = {}
    outils: dict = {}
    talents: dict = {}
    talents_programmes: dict = {}

    # Première passe — classement des cartes et **collecte de toutes les empreintes de texte** à
    # charger en une seule requête : attaques à effet des Pokémon, et textes d'Objet/Supporter.
    # Pokémon : def construite après le chargement des scripts (attaques à effet).
    pokemon_cards: list[tuple[str, Card]] = []
    dresseurs: list[tuple[str, str, Card]] = []  # (ref, genre, carte)
    empreintes_dresseur: dict[str, str] = {}  # ref → empreinte du texte de Dresseur
    empreintes: set[str] = set()
    for ref in refs:
        card = index.get(ref)
        if card is None:
            continue  # ref inconnue du catalogue : jamais devinée (D9).
        if is_energy(getattr(card, "supertype", None)):
            try:
                energies[ref] = definition_energie_depuis_card(card)
            except ValueError:
                pass  # Énergie spéciale non scriptée : omise (D9).
            continue
        genre = genre_dresseur(card)
        if genre is not None:
            dresseurs.append((ref, genre, card))
            if genre in ("objet", "supporter"):
                for effet in effets_scriptables(card):
                    if effet.origine == ORIGINE_DRESSEUR:
                        empreintes_dresseur[ref] = effet.empreinte
                        empreintes.add(effet.empreinte)
                        break
            continue
        pokemon_cards.append((ref, card))
        for effet in effets_scriptables(card):
            if effet.origine == ORIGINE_ATTAQUE:
                empreintes.add(effet.empreinte)  # script d'attaque à effet (j-cartes-attaques)

    # Scripts DSL validés de toutes ces empreintes, en **une** requête (attaques + Dresseurs).
    scripts = await scripts_valides_par_empreinte(db, empreintes)

    # Pokémon : def construite avec les scripts de ses attaques à effet branchés (une attaque sans
    # script reste non jouable, D9). Fiche de talent activé écrite à la main si la ``ref`` en a une.
    for ref, card in pokemon_cards:
        try:
            pokemon[ref] = definition_depuis_card(card, scripts_attaques=scripts)
        except ValueError:
            continue  # Pokémon non compilable (donnée manquante) : omis (D9).
        fiche = fiche_talent_active(ref)
        if fiche is not None:
            talents[ref] = fiche.talent(ref)
            talents_programmes[ref] = fiche.programme

    # Objets/Supporters : script compilé en Programme ; une carte dont l'effet n'a pas de script
    # valide est **omise** (D9) — aucune famille ne la jouera. Stades et Outils n'ont pas de DSL.
    for ref, genre, card in dresseurs:
        if genre == "stade":
            stades[ref] = definition_stade_depuis_card(card)
        elif genre == "outil":
            outils[ref] = definition_outil_depuis_card(card)
        elif genre in ("objet", "supporter"):
            empreinte = empreintes_dresseur.get(ref)
            script = scripts.get(empreinte) if empreinte else None
            if script is None:
                continue  # effet non scripté ou illisible : carte omise (D9).
            programme = programme_depuis_json(script)
            if genre == "objet":
                objets[ref] = definition_objet_depuis_card(card, programme)
            else:
                supporters[ref] = definition_supporter_depuis_card(card, programme)

    # Effets continus — producteurs réels d'Outils et de Stades, pour les seules ``ref`` présentes
    # dans l'état. La métadonnée porte le type de chaque Pokémon (Metal Core Barrier en dépend).
    meta = {r: {"type": d.type, "stade": d.stade, "nom": d.nom} for r, d in pokemon.items()}
    registre_continus: dict = {}
    for source in (registre_outils(meta), registre_stades(meta)):
        for ref, producteur in source.items():
            if ref in refs:
                registre_continus[ref] = producteur

    return CatalogueJeu(
        pokemon=pokemon,
        energies=energies,
        objets=objets,
        supporters=supporters,
        stades=stades,
        outils=outils,
        talents=talents,
        talents_programmes=talents_programmes,
        registre_continus=registre_continus,
    )


__all__ = ["CatalogueJeu", "construire_catalogue_jeu", "refs_etat"]
