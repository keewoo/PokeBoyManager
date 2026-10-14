"""Adaptateur **catalogue → indicateurs d'affichage** du plateau (lot ``j-plateau-etat-visuel``).

Le moteur (``pbm_game``) est **pur** : il ne lit jamais la base. Pour que l'écran dessine les PV
restants et les pastilles d'énergies typées **sans recalcul**, il faut lui fournir en **données**
les PV imprimés et les codes de type de chaque carte visible en jeu. C'est le rôle de ce module :
il lit le catalogue (``Card``) et produit une :class:`CatalogueAffichage` que la projection passe à
:func:`pbm_game.sortie.enrichir_indicateurs`.

On **ne passe pas** par :func:`pbm_api.jeu.catalogue.definition_depuis_card` : elle **refuse** une
carte non Pokémon (une Énergie, par exemple) — ce qu'on veut à la *construction* d'un deck, pas à
l'*affichage*, où une énergie attachée doit justement être typée. Ici la lecture est **tolérante** :
une donnée absente devient ``None`` (PV inconnu, type inconnu), jamais une valeur inventée (D9) —
l'écran retombe alors sur un repère neutre.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from pbm_game.effets.continus import RegistreContinus
from pbm_game.sortie import refs_demande, refs_en_jeu
from pbm_game.state.modele import EtatPartie
from pbm_game.state.serialisation import depuis_json
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.element_type import element_code
from pbm_api.jeu.rendu_service import RendusPartie, rendus_de_partie
from pbm_api.models import Card


@dataclass(frozen=True)
class CatalogueAffichage:
    """Les données d'affichage résolues du catalogue, passées telles quelles au moteur pur.

    * ``pv_imprimes`` : ``ref → PV imprimés`` (R-13.1) — absent pour une carte sans PV (énergie) ;
    * ``types`` : ``ref → code d'élément`` (``None`` si inconnu) ;
    * ``registre`` : les producteurs d'effets continus (deltas de PV d'un Outil). **Vide** au jalon
      J1 — aucune carte à effet continu n'est encore scriptée — mais c'est par lui que ``pv_max``
      deviendra exact dès qu'un Outil ajoutera des PV, sans changer le code d'affichage.
    """

    pv_imprimes: dict[str, int] = field(default_factory=dict)
    types: dict[str, str | None] = field(default_factory=dict)
    noms: dict[str, str] = field(default_factory=dict)
    registre: RegistreContinus = field(default_factory=dict)
    #: ``ref → cards.id`` des cartes visibles : la seule façon de construire l'URL d'une image
    #: (``/img/cards/{id}``) depuis une ``ref`` d'état, qui est un ``tcgdex_id`` (lot
    #: ``j-rendu-carte``). Une ref inconnue du catalogue n'y figure pas — donc n'a aucune image.
    ids: dict[str, uuid.UUID] = field(default_factory=dict)
    #: Les rendus résolus de la partie, pour les deux regards (lot ``j-rendu-carte``). **Vide**
    #: hors d'une partie (aucun ``game_id`` fourni) : il n'y a alors ni propriétaire ni réglage à
    #: appliquer, donc aucune image à proposer.
    rendus: RendusPartie = field(default_factory=lambda: RendusPartie(par_regard={}))


async def catalogue_affichage(
    db: AsyncSession,
    refs: Iterable[str],
    *,
    registre: RegistreContinus | None = None,
    game_id: uuid.UUID | None = None,
) -> CatalogueAffichage:
    """Lit le catalogue pour les ``refs`` données et en tire PV imprimés, type, nom et rendu.

    Une requête unique bornée aux refs visibles (``tcgdex_id`` ou ``ptcg_id``). Tolérante : une ref
    absente du catalogue est simplement omise (l'indicateur manquera plutôt que de mentir).

    ``game_id`` déclenche la résolution des **rendus de cartes** (lot ``j-rendu-carte``) : elle a
    besoin de la partie pour savoir qui possède quoi, avec quel deck et quels réglages. Sans lui,
    les rendus restent vides — un appel hors partie (test, outil) n'a rien à montrer.
    """
    refs_set = {r for r in refs if r}
    if not refs_set:
        return CatalogueAffichage(registre=dict(registre or {}))

    # Une ref d'état est un ``tcgdex_id``/``ptcg_id`` en production ; en l'absence de ceux-ci
    # (fixtures), ``pbm_game`` retombe sur ``str(id)`` — on interroge donc aussi par UUID.
    ids_uuid: list[uuid.UUID] = []
    for ref in refs_set:
        try:
            ids_uuid.append(uuid.UUID(ref))
        except ValueError:
            pass
    conditions = [Card.tcgdex_id.in_(refs_set), Card.ptcg_id.in_(refs_set)]
    if ids_uuid:
        conditions.append(Card.id.in_(ids_uuid))
    rows = (await db.execute(select(Card).where(or_(*conditions)))).scalars().all()

    # Indexe chaque carte par toutes ses clés possibles, pour retrouver la carte quelle que soit
    # la forme de ``ref`` portée par l'état (``_ref`` du moteur : tcgdex_id, puis ptcg_id, puis id).
    index: dict[str, Card] = {}
    for card in rows:
        if card.tcgdex_id:
            index.setdefault(card.tcgdex_id, card)
        if card.ptcg_id:
            index.setdefault(card.ptcg_id, card)
        index.setdefault(str(card.id), card)

    pv_imprimes: dict[str, int] = {}
    types: dict[str, str | None] = {}
    noms: dict[str, str] = {}
    ids: dict[str, uuid.UUID] = {}
    for ref in refs_set:
        card = index.get(ref)
        if card is None:
            continue  # ref inconnue du catalogue : jamais devinée (D9)
        ids[ref] = card.id
        if card.hp is not None:
            pv_imprimes[ref] = card.hp
        # ``element_type`` est déjà le code normalisé (fire/water/…) pour un Pokémon comme pour une
        # énergie de base ; ``energy_type`` (Normal/Special) sert de filet via ``element_code``.
        types[ref] = element_code(card.element_type or card.energy_type)
        # Nom lisible pour les fenêtres de décision (lot ``j-plateau-decisions``) : chercher une
        # carte dans une pioche de soixante se fait sur le nom, pas sur un identifiant opaque.
        noms[ref] = card.name
    rendus = (
        await rendus_de_partie(db, game_id, ids_par_ref=ids)
        if game_id is not None
        else RendusPartie(par_regard={})
    )
    return CatalogueAffichage(
        pv_imprimes=pv_imprimes,
        types=types,
        noms=noms,
        registre=dict(registre or {}),
        ids=ids,
        rendus=rendus,
    )


async def catalogue_pour_etat(
    db: AsyncSession, etat: EtatPartie, *, game_id: uuid.UUID | None = None
) -> CatalogueAffichage:
    """Les cartes visibles d'un état **et** les cartes des options d'une demande en cours.

    En plus du visible (:func:`refs_en_jeu`), on charge les cartes désignées par une demande en
    cours (:func:`refs_demande`) — même dans une zone cachée qu'on fait fouiller (la pioche) : la
    fenêtre de décision doit afficher de vraies cartes (lot ``j-plateau-decisions``).

    ``game_id`` est ce qui permet de résoudre le **rendu** des cartes (lot ``j-rendu-carte``) : le
    passer est la règle, l'omettre ne laisse que les indicateurs (aucune image).
    """
    return await catalogue_affichage(
        db, refs_en_jeu(etat) | refs_demande(etat), game_id=game_id
    )


async def catalogue_pour_resultat(
    db: AsyncSession, resultat, *, game_id: uuid.UUID | None = None
) -> CatalogueAffichage:
    """Les cartes visibles d'un résultat d'action **et** les options de sa demande en cours."""
    etat = depuis_json(resultat.etat)
    return await catalogue_affichage(
        db, refs_en_jeu(etat) | refs_demande(etat), game_id=game_id
    )


__all__ = [
    "CatalogueAffichage",
    "catalogue_affichage",
    "catalogue_pour_etat",
    "catalogue_pour_resultat",
]
