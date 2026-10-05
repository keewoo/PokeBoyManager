"""Construction d'une partie à partir de deux decks : résolution en scripts et état initial.

« Résoudre un deck en scripts », au jalon J1, c'est **vérifier que chaque carte du deck est
jouable** — c'est-à-dire qu'elle se compile en une `DefinitionCarte` du moteur via l'adaptateur
`pbm_api.jeu.catalogue` (PV, stade, marqueur de règle, coût de retraite présents et cohérents). Un
effet non implémenté n'est jamais approximé (D9) : si une carte ne se compile pas, la partie est
**refusée** en nommant les cartes fautives, plutôt que jouée de travers.

Le moteur (`pbm_game`) est **pur** : il ne lit jamais la base. Ce module est l'adaptateur qui lit le
catalogue et produit un `EtatPartie` sérialisable que le moteur sait manipuler. L'état initial de ce
lot est **minimal** : chaque joueur reçoit son deck dans sa **pioche**, rien d'autre. La mise en
place réelle (mélange, main de sept, mulligans, actif et banc, six récompenses, tirage au sort) est
le lot `j-initialisation` — on ne l'approxime pas ici.
"""

from __future__ import annotations

import uuid

from pbm_game.state.modele import PHASE_PIOCHE, Carte, EtatPartie, Joueur, Tour
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks.energy import is_energy
from pbm_api.jeu.catalogue import (
    definition_depuis_card,
    definition_energie_depuis_card,
    genre_dresseur,
    ref_catalogue,
)
from pbm_api.models import Card, DeckCard


def joueur_id_de(user_id: uuid.UUID) -> str:
    """Identifiant de joueur du moteur pour un utilisateur — `str(user_id)`, déterministe.

    Déterministe (donc rejouable) et stable : l'état initial, le journal et l'empreinte en
    dépendent. On ne dérive jamais un identifiant d'un compteur de session ou d'un alias mutable.
    """
    return str(user_id)


async def _cartes_du_deck(db: AsyncSession, deck_id: uuid.UUID) -> list[tuple[Card, int]]:
    """Les cartes d'un deck avec leur quantité, carte du catalogue complète (pour l'adaptateur).

    Charge les objets `Card` entiers (attaques, faiblesses, marqueur…) : l'adaptateur
    `definition_depuis_card` en a besoin pour juger la jouabilité. Ordre stable par nom puis
    numéro, pour que l'état initial soit déterministe d'une création à l'autre.
    """
    rows = await db.execute(
        select(Card, DeckCard.quantity)
        .join(DeckCard, DeckCard.card_id == Card.id)
        .where(DeckCard.deck_id == deck_id)
        .order_by(Card.name, Card.number)
    )
    return [(card, quantity) for card, quantity in rows.all()]


async def resoudre_deck(
    db: AsyncSession, deck_id: uuid.UUID, joueur_id: str
) -> tuple[list[Carte], list[tuple[str, str]]]:
    """Résout un deck en cartes de pioche, en relevant les cartes **non jouables**.

    Renvoie `(cartes, refus)` :

    * `cartes` — la pioche du joueur : une `Carte` (`instance_id` unique, `ref` catalogue) par
      exemplaire (quantité comprise), **seulement** pour les cartes jouables ;
    * `refus` — la liste des `(nom, raison)` des cartes qui ne se compilent pas (D9).

    L'appelant décide : s'il reste un seul refus, la partie n'est pas créée (`CartesNonJouables`).
    Les `instance_id` sont déterministes (`<joueur>:d<index>`) pour que deux créations du même deck
    donnent le même état initial — un `instance_id` aléatoire casserait la reproductibilité.
    """
    cartes: list[Carte] = []
    refus: list[tuple[str, str]] = []
    index = 0
    for card, quantity in await _cartes_du_deck(db, deck_id):
        try:
            # Une carte Énergie se compile en DefinitionEnergie (seules les Énergies de base sont
            # jouables au jalon J1) ; un Pokémon en DefinitionCarte. Une carte **Dresseur** (Objet,
            # Supporter, Stade, Outil) n'a pas de définition de combat : elle est jouable au titre
            # de sa famille, et c'est son **script** (porte D9, ``refus_scripts_deck``) qui décide
            # si son effet est implémenté — pas cette compilation. On la retient par sa ``ref``.
            if is_energy(getattr(card, "supertype", None)):
                ref = definition_energie_depuis_card(card).ref
            elif genre_dresseur(card) is not None:
                ref = ref_catalogue(card)
            else:
                ref = definition_depuis_card(card).ref
        except ValueError as exc:
            nom = getattr(card, "name", None) or str(getattr(card, "id", "?"))
            refus.append((nom, str(exc)))
            continue
        for _ in range(quantity):
            cartes.append(Carte(instance_id=f"{joueur_id}:d{index}", ref=ref))
            index += 1
    return cartes, refus


def construire_etat_initial(
    joueur_a: tuple[str, list[Carte]], joueur_b: tuple[str, list[Carte]]
) -> EtatPartie:
    """Assemble l'état initial minimal : deux joueurs, chacun son deck en pioche (R-3.1 partiel).

    L'ordre de la pioche est celui des cartes reçues (non mélangé : le mélange est une **action**
    journalisée, `melanger_pioche`, jouée par la mise en place `j-initialisation`). Le tour 1 est
    posé en phase de pioche sur le siège 0 ; le vrai « qui commence » (tirage au sort R-4.7) est
    fixé par `j-lancement-partie`/`j-initialisation`, pas deviné ici.
    """
    id_a, cartes_a = joueur_a
    id_b, cartes_b = joueur_b
    return EtatPartie(
        joueurs=(
            Joueur(id=id_a, pioche=tuple(cartes_a)),
            Joueur(id=id_b, pioche=tuple(cartes_b)),
        ),
        tour=Tour(joueur_actif=id_a, numero=1, phase=PHASE_PIOCHE),
    )
