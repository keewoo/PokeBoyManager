"""Le **profil de joueur** côté base : vitrine, carte fétiche (lot `j-profil-jeu`, jalon J4, DJ6).

Trois services, et aucune règle nouvelle : tout ce qui décide vit déjà ailleurs, et ce module
l'appelle.

* :func:`composer_vitrine` — ce que la page « Mon profil de joueur » montre : l'identité reprise du
  compte (pseudo, avatar), la carte fétiche, les badges, les décors.
* :func:`choisir_carte_fetiche` — poser ou retirer sa carte fétiche, en contrôlant qu'on la possède.
* :func:`carte_fetiche_de_camp` — ce que l'autre camp verra au lancement d'une partie.

**Ce que ce module ne décide pas, et c'est voulu** : la liste des badges est dans
:mod:`pbm_api.jeu.badges` (pur), leur attribution dans :mod:`pbm_api.jeu.badges_service`, le choix
photo/officielle dans :mod:`pbm_api.jeu.rendu` (DJ5), l'activation dans
:mod:`pbm_api.jeu.reglages`. Une vitrine qui recalculerait l'un des quatre finirait par le dire
autrement que le reste du jeu.

**Avatar et pseudo ne sont pas redéfinis ici.** Ils appartiennent au compte (lot `v1-profil`,
``users.pseudo`` / ``users.avatar_key``) et la vitrine les **reprend** : c'est la mission du lot
(« avatar et pseudo repris du compte »). Il n'existe donc pas de pseudo de jeu distinct du pseudo du
compte — un joueur n'a qu'un nom, et c'est celui que l'adversaire voit déjà dans le salon.

**Les décors ne se débloquent pas.** `j-arene-decors` a laissé les six décors **tous disponibles**,
et a écrit pourquoi : « on ne fabrique pas un mécanisme de déblocage qui ne débloque rien ». Ce lot
avait la possibilité d'en verrouiller derrière des badges ; il ne le fait pas, pour une raison plus
forte que la symétrie : **verrouiller aujourd'hui retirerait aux joueurs un choix qu'ils ont déjà**.
DJ6 dit « sans saison ni perte de points » — reprendre quatre décors sur six pour les faire regagner
serait exactement une perte. La vitrine les montre donc comme ce qu'ils sont : disponibles, avec
celui que le joueur a choisi mis en avant.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu import decors
from pbm_api.jeu.badges import BADGES, Badge
from pbm_api.jeu.badges_service import badges_du_joueur
from pbm_api.jeu.reglages import CLE_BADGES_ACTIFS, est_actif
from pbm_api.jeu.reglages_service import lire as lire_reglage
from pbm_api.jeu.rendu import RenduResolu, rendu_carte_fetiche
from pbm_api.jeu.rendu_service import (
    charger_reglages,
    photos_par_carte,
    preparer_variante,
)
from pbm_api.models import Card, CollectionItem, JeuConfortReglages, User
from pbm_api.storage import StorageBackend

logger = logging.getLogger(__name__)


class CarteNonPossedee(Exception):
    """La carte proposée comme fétiche n'est pas (ou n'est plus) dans la collection du joueur.

    Levée plutôt que tolérée : « choisie dans sa collection » est la définition même de la carte
    fétiche (fiche du lot). Accepter n'importe quelle carte du catalogue ferait de la vitrine une
    liste de souhaits, ce qu'elle n'est pas — et le joueur en serait le dernier informé.
    """


class CarteInconnue(Exception):
    """La carte proposée n'existe pas au catalogue."""


@dataclass(frozen=True)
class CarteFeticheVue:
    """La carte fétiche telle qu'un regard donné la voit : son identité, et son rendu DJ5.

    ``rendu`` vient de :func:`pbm_api.jeu.rendu.rendu_carte_fetiche` : c'est le **même** juge que
    celui du plateau et du constructeur de deck. ``nom`` est celui du catalogue — jamais un nom
    saisi par le joueur, qui pourrait être tout autre chose.
    """

    card_id: uuid.UUID
    nom: str
    rendu: RenduResolu


@dataclass(frozen=True)
class BadgeVitrine:
    """Un badge dans la vitrine : sa déclaration, et s'il est obtenu.

    Les badges **non obtenus** sont montrés aussi, avec leur description : c'est ce qui donne un
    objectif lisible (« gagne sans céder une récompense ») au lieu d'une collection mystérieuse.
    Aucun n'est caché, aucun n'est aléatoire — il n'y a rien à découvrir par hasard.
    """

    code: str
    nom: str
    description: str
    mesure: str
    obtenu: bool
    obtenu_a: datetime | None
    game_id: uuid.UUID | None


@dataclass(frozen=True)
class Vitrine:
    """Ce que la page « Mon profil de joueur » affiche.

    ``badges_actifs`` dit si JF a allumé la vitrine des badges (DJ6). Quand il est faux, ``badges``
    est **vide** — et l'écran le dit (« les badges ne sont pas activés »), plutôt que d'afficher une
    grille de cases grises qu'on prendrait pour une panne.

    ``decors`` est la liste des décors disponibles — tous (voir l'en-tête du module) — et
    ``decor_choisi`` celui que le joueur a réglé, ``None`` pour « laisse le jeu choisir ».
    """

    pseudo: str | None
    a_un_avatar: bool
    carte_fetiche: CarteFeticheVue | None
    badges_actifs: bool
    badges: tuple[BadgeVitrine, ...]
    decors: tuple[str, ...]
    decor_choisi: str | None


async def _carte_possedee(db: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID) -> bool:
    """Le joueur possède-t-il au moins un exemplaire **non suspect** de cette carte ?

    Même notion de possession que le contrôle de légalité des decks
    (:func:`pbm_api.games.lancement._cartes_non_possedees`) : un exemplaire signalé contrefaçon ne
    compte pas. Deux définitions de « posséder » dans le même produit, c'est une qui deviendra
    fausse.
    """
    return (
        await db.execute(
            select(CollectionItem.id)
            .where(
                CollectionItem.user_id == user_id,
                CollectionItem.card_id == card_id,
                CollectionItem.counterfeit_suspected.is_(False),
            )
            .limit(1)
        )
    ).scalar_one_or_none() is not None


async def _rendu_fetiche(
    db: AsyncSession,
    *,
    proprietaire: User,
    card_id: uuid.UUID,
    launch_id: uuid.UUID | None,
    cest_moi: bool,
) -> RenduResolu:
    """Le rendu DJ5 de la carte fétiche de ``proprietaire``, pour le regard demandé."""
    reglages = await charger_reglages(db, proprietaire.id)
    photos = await photos_par_carte(db, proprietaire.id, [card_id])
    return rendu_carte_fetiche(
        card_id=card_id,
        photo=photos.get(card_id),
        reglages=reglages,
        cest_moi=cest_moi,
        launch_id=launch_id,
        pseudo_proprietaire=proprietaire.pseudo,
    )


async def carte_fetiche_de_camp(
    db: AsyncSession, *, proprietaire: User, launch_id: uuid.UUID
) -> CarteFeticheVue | None:
    """La carte fétiche d'un camp, **telle que l'autre camp la voit** — ``None`` s'il n'en a pas.

    ⚠️ Le regard est toujours celui de l'**adversaire** (``cest_moi=False``), même quand c'est le
    propriétaire qui regarde la vue. Ce n'est pas une approximation : la vue d'un lancement est
    **symétrique** par construction (c'est ce qui rend le pile ou face vérifiable par les deux
    joueurs, voir :mod:`pbm_api.models.game_launch`), et la carte fétiche est précisément « ce que
    je montre ». Je la vois donc comme mon adversaire la voit — ce qui est l'information utile, et
    ce qui garantit qu'aucun chemin asymétrique ne puisse émettre une URL de photo sous veto.
    """
    if proprietaire.carte_fetiche_card_id is None:
        return None
    carte = await db.get(Card, proprietaire.carte_fetiche_card_id)
    if carte is None:
        # Carte retirée du catalogue : la colonne est en `SET NULL`, mais une lecture peut tomber
        # entre les deux. On ne montre rien plutôt que d'inventer un nom.
        return None
    rendu = await _rendu_fetiche(
        db,
        proprietaire=proprietaire,
        card_id=carte.id,
        launch_id=launch_id,
        cest_moi=False,
    )
    return CarteFeticheVue(card_id=carte.id, nom=carte.name, rendu=rendu)


async def choisir_carte_fetiche(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    user: User,
    card_id: uuid.UUID | None,
) -> CarteFeticheVue | None:
    """Pose (ou retire, avec ``None``) la carte fétiche du joueur. **Ne commite pas.**

    Lève :class:`CarteInconnue` si la carte n'existe pas au catalogue, :class:`CarteNonPossedee` si
    le joueur ne la possède pas : les deux refus **disent** lequel c'est, parce qu'il n'y a ici
    aucun secret à garder (le catalogue est public, et la collection est la sienne).

    **Prépare au passage la variante de jeu de sa photo**, si elle manque. C'est le bon moment, et
    c'est le seul : un geste délibéré du joueur, borné à **une** image, hors de toute partie —
    exactement les conditions que `j-assets-pipeline` pose (`docs/jeu/ASSETS.md`). Sans cela, la
    carte fétiche se replierait presque toujours sur l'image officielle au lancement, alors que le
    joueur a demandé ses photos : le critère d'acceptation du lot serait « vrai » et le produit
    faux.
    """
    if card_id is None:
        user.carte_fetiche_card_id = None
        return None

    carte = await db.get(Card, card_id)
    if carte is None:
        raise CarteInconnue(f"carte {card_id} inconnue au catalogue")
    if not await _carte_possedee(db, user.id, card_id):
        raise CarteNonPossedee(
            "cette carte n'est pas dans ta collection : une carte fétiche se choisit "
            "parmi les cartes que tu possèdes."
        )

    user.carte_fetiche_card_id = card_id

    exemplaire = (
        await db.execute(
            select(CollectionItem)
            .where(
                CollectionItem.user_id == user.id,
                CollectionItem.card_id == card_id,
                CollectionItem.photo_s3_key.isnot(None),
                CollectionItem.counterfeit_suspected.is_(False),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if exemplaire is not None:
        await preparer_variante(db, storage, exemplaire)

    # Le rendu rendu à l'écran est celui de la **vitrine** (hors lancement) : il montre donc
    # l'image officielle, et dit ce que l'adversaire verra le jour d'une partie.
    rendu = await _rendu_fetiche(
        db, proprietaire=user, card_id=card_id, launch_id=None, cest_moi=False
    )
    return CarteFeticheVue(card_id=card_id, nom=carte.name, rendu=rendu)


def _vitrine_badge(badge: Badge, obtenus: dict) -> BadgeVitrine:
    """Une ligne de la vitrine pour un badge déclaré, obtenu ou non."""
    trace = obtenus.get(badge.code)
    return BadgeVitrine(
        code=badge.code,
        nom=badge.nom,
        description=badge.description,
        mesure=badge.mesure,
        obtenu=trace is not None,
        obtenu_a=trace[1] if trace is not None else None,
        game_id=trace[0] if trace is not None else None,
    )


async def composer_vitrine(db: AsyncSession, user: User) -> Vitrine:
    """La vitrine du profil de jeu d'un compte — **le sien**, jamais celui d'un autre.

    Il n'existe aucun paramètre d'identité : la route lit le compte de la session, et ce module
    reçoit l'objet ``User``. L'isolation n'est donc pas un filtre qu'on pense à mettre, c'est la
    seule forme que la fonction sait prendre — la même règle que « Mes parties »
    (:mod:`pbm_api.jeu.stats_joueur_service`).

    Les badges ne sont lus que si JF a allumé la vitrine (``badges_actifs``, DJ6) : inutile
    d'interroger la base pour une liste qu'on ne montrera pas.
    """
    actifs = est_actif(await lire_reglage(db, CLE_BADGES_ACTIFS))
    badges: tuple[BadgeVitrine, ...] = ()
    if actifs:
        obtenus = await badges_du_joueur(db, user.id)
        badges = tuple(_vitrine_badge(b, obtenus) for b in BADGES)

    fetiche: CarteFeticheVue | None = None
    if user.carte_fetiche_card_id is not None:
        carte = await db.get(Card, user.carte_fetiche_card_id)
        if carte is not None:
            fetiche = CarteFeticheVue(
                card_id=carte.id,
                nom=carte.name,
                rendu=await _rendu_fetiche(
                    db,
                    proprietaire=user,
                    card_id=carte.id,
                    launch_id=None,
                    # Le regard de l'adversaire : la vitrine sert à voir **ce qu'on montre**.
                    cest_moi=False,
                ),
            )

    confort = (
        await db.execute(
            select(JeuConfortReglages).where(JeuConfortReglages.user_id == user.id)
        )
    ).scalar_one_or_none()

    return Vitrine(
        pseudo=user.pseudo,
        a_un_avatar=user.avatar_key is not None,
        carte_fetiche=fetiche,
        badges_actifs=actifs,
        badges=badges,
        decors=decors.DECORS,
        decor_choisi=confort.decor if confort is not None else None,
    )


__all__ = [
    "BadgeVitrine",
    "CarteFeticheVue",
    "CarteInconnue",
    "CarteNonPossedee",
    "Vitrine",
    "carte_fetiche_de_camp",
    "choisir_carte_fetiche",
    "composer_vitrine",
]
