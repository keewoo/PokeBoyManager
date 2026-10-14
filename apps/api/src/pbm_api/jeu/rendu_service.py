"""Côté base du rendu des cartes en jeu (lot ``j-rendu-carte``) : réglages, variantes, résolution.

La **décision** (quel rendu, pour quel regard) est pure et vit dans :mod:`pbm_api.jeu.rendu` ; la
**mesure** de qualité dans :mod:`pbm_api.jeu.rendu_qualite` ; la **fabrication** d'image dans
:mod:`pbm_api.jeu.rendu_image`. Ce module est l'adaptateur : il lit la base et le stockage objet,
et alimente les trois autres en données. Le moteur (``pbm_game``) n'apparaît nulle part ici — il ne
connaît ni image ni URL, et ce lot ne lui en apprend aucune.

**Où la variante de jeu est produite**, et pourquoi là :

* au **constructeur de deck** (:func:`apercu_deck`) : c'est le moment « à l'avance » du lot — le
  joueur regarde son deck avant de jouer, la fabrication est bornée à ses cartes, et c'est aussi là
  qu'on lui **dit** ce qui se repliera sur l'officielle ;
* à la **première demande** d'une photo (:func:`servir_photo`) : une seule image, pour l'exemplaire
  demandé ;
* jamais dans la **projection d'une partie** : un plateau se lit plusieurs fois par seconde, on n'y
  fabrique pas d'image. Une photo pas encore préparée s'y replie sur l'officielle **en le disant**
  (``RAISON_PAS_PRETE``) — le critère du lot est « sans trou ni attente », pas « coûte que coûte ».
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.rendu import (
    RENDU_PHOTO,
    RENDUS_REGLABLES,
    PhotoDeJeu,
    ReglagesRendu,
    choisir_rendu,
    decider_origine,
    preference_effective,
)
from pbm_api.jeu.rendu_image import (
    TYPE_MIME_JEU,
    PhotoIndecodable,
    cle_image_jeu,
    decoder,
    fabriquer_image_jeu,
)
from pbm_api.jeu.rendu_qualite import NotePhoto, noter_photo
from pbm_api.models import (
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Detection,
    GamePlayer,
    JeuRenduReglages,
    User,
)
from pbm_api.storage import StorageBackend


class PhotoIntrouvable(Exception):
    """Cette photo n'est pas visible par ce joueur — **404**, jamais 403.

    Un 403 dirait « elle existe, mais tu n'y as pas droit » : sur une photo personnelle, c'est déjà
    une information de trop (même frontière que partout dans le jeu, D11). Le refus de
    confidentialité, la partie à laquelle on ne participe pas et l'exemplaire qui n'existe pas
    rendent donc la **même** réponse.
    """


class RenduValeurInvalide(ValueError):
    """Un rendu demandé hors vocabulaire (:data:`pbm_api.jeu.rendu.RENDUS_REGLABLES`)."""


# --- Réglages du compte -------------------------------------------------------------------------


def _reglages_depuis_ligne(ligne: JeuRenduReglages | None) -> ReglagesRendu:
    """Traduit la ligne de base en vue pure, ou rend les défauts si le compte n'en a pas.

    C'est ici que « pas de ligne » devient « les défauts », une fois pour toutes — aucun appelant
    n'a à connaître cette convention.
    """
    if ligne is None:
        return ReglagesRendu()
    return ReglagesRendu(
        rendu_defaut=ligne.rendu_defaut,
        jamais_montrer_mes_photos=ligne.jamais_montrer_mes_photos,
    )


async def charger_reglages(db: AsyncSession, user_id: uuid.UUID) -> ReglagesRendu:
    """Les réglages de rendu du compte — les défauts DJ5 s'il n'y a jamais touché."""
    return _reglages_depuis_ligne(await db.get(JeuRenduReglages, user_id))


async def enregistrer_reglages(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    rendu_defaut: str | None = None,
    jamais_montrer_mes_photos: bool | None = None,
) -> ReglagesRendu:
    """Écrit les réglages (création de la ligne au premier passage) et rend l'état complet.

    Modification **partielle** : seuls les champs fournis changent — l'écran peut basculer le veto
    sans renvoyer le rendu par défaut, donc sans écraser un réglage changé dans un autre onglet.
    """
    if rendu_defaut is not None and rendu_defaut not in RENDUS_REGLABLES:
        raise RenduValeurInvalide(
            f"rendu « {rendu_defaut} » inconnu (attendus : {sorted(RENDUS_REGLABLES)})"
        )
    ligne = await db.get(JeuRenduReglages, user_id)
    if ligne is None:
        defauts = ReglagesRendu()
        ligne = JeuRenduReglages(
            user_id=user_id,
            rendu_defaut=defauts.rendu_defaut,
            jamais_montrer_mes_photos=defauts.jamais_montrer_mes_photos,
        )
        db.add(ligne)
    if rendu_defaut is not None:
        ligne.rendu_defaut = rendu_defaut
    if jamais_montrer_mes_photos is not None:
        ligne.jamais_montrer_mes_photos = jamais_montrer_mes_photos
    await db.flush()
    return _reglages_depuis_ligne(ligne)


# --- Variante de jeu d'un exemplaire ------------------------------------------------------------


async def _crop_quality(db: AsyncSession, item: CollectionItem) -> Mapping | None:
    """La qualité de découpe mesurée à la détection, si l'exemplaire en vient.

    Un exemplaire créé sans détection (import, saisie manuelle) n'a pas de cadrage mesuré : on rend
    ``None`` plutôt qu'un cadrage parfait supposé — supposer parfait ferait passer en jeu une carte
    coupée.
    """
    if item.detection_id is None:
        return None
    detection = await db.get(Detection, item.detection_id)
    if detection is None or not detection.bbox:
        return None
    qualite = detection.bbox.get("crop_quality")
    return qualite if isinstance(qualite, Mapping) else None


async def preparer_variante(
    db: AsyncSession, storage: StorageBackend, item: CollectionItem
) -> NotePhoto | None:
    """Note la photo de ``item`` et produit sa variante de jeu. **Idempotent**.

    Rend la note obtenue, ou ``None`` si l'exemplaire n'a pas de photo. Trois cas, tous écrits en
    base pour ne pas être recalculés à chaque partie :

    * photo exploitable → variante produite, ``jeu_image_key`` posée ;
    * photo inexploitable → ``jeu_image_key`` laissée vide et la **raison** stockée : c'est elle que
      le joueur lira dans son constructeur de deck ;
    * photo illisible (:class:`PhotoIndecodable`) → la panne est notée comme une raison de repli,
      jamais avalée.

    Un second appel sur un exemplaire déjà préparé ne refait rien (ni décodage, ni écriture) : la
    préparation est appelée depuis un écran, elle doit coûter zéro la deuxième fois.
    """
    if item.photo_s3_key is None:
        return None
    if item.jeu_image_key is not None and item.jeu_qualite is not None:
        return NotePhoto.depuis_json(item.jeu_qualite)

    photo = await storage.get(item.photo_s3_key)
    if photo is None:
        # La clé est en base mais l'objet n'est pas dans le stockage : une incohérence réelle, qu'on
        # nomme comme telle. Le repli sur l'officielle garde la partie jouable.
        item.jeu_qualite = {
            "nettete": 0.0,
            "luminosite": 0.0,
            "part_brulee": 0.0,
            "cadrage": None,
            "exploitable": False,
            "raison": "photo absente du stockage",
        }
        await db.flush()
        return NotePhoto.depuis_json(item.jeu_qualite)

    try:
        note = noter_photo(decoder(photo), crop_quality=await _crop_quality(db, item))
    except (PhotoIndecodable, ValueError) as exc:
        item.jeu_qualite = {
            "nettete": 0.0,
            "luminosite": 0.0,
            "part_brulee": 0.0,
            "cadrage": None,
            "exploitable": False,
            "raison": f"photo illisible ({exc})",
        }
        await db.flush()
        return NotePhoto.depuis_json(item.jeu_qualite)

    item.jeu_qualite = note.en_json()
    if note.exploitable:
        cle = cle_image_jeu(item.user_id, item.id)
        await storage.put(cle, fabriquer_image_jeu(photo), TYPE_MIME_JEU)
        item.jeu_image_key = cle
    await db.flush()
    return note


def _photo_de(item: CollectionItem) -> PhotoDeJeu:
    """La vue pure de la photo d'un exemplaire, telle que la décision l'attend."""
    return PhotoDeJeu(
        item_id=item.id,
        prete=item.jeu_image_key is not None,
        note=NotePhoto.depuis_json(item.jeu_qualite),
    )


def _meilleur(items: Iterable[CollectionItem]) -> CollectionItem | None:
    """L'exemplaire dont la photo représentera cette carte en jeu.

    Un joueur peut posséder la même carte en plusieurs exemplaires, chacun avec sa photo. On prend
    celui qui est **prêt** et **exploitable** avant tout autre, puis le plus net — c'est la plus
    lisible qui gagne, pas la plus récente : sur un plateau de téléphone, la lisibilité est la seule
    qualité qui compte.
    """
    classes: list[tuple[tuple[int, int, float], CollectionItem] ] = []
    for item in items:
        note = NotePhoto.depuis_json(item.jeu_qualite)
        classes.append(
            (
                (
                    1 if item.jeu_image_key is not None else 0,
                    1 if (note is None or note.exploitable) else 0,
                    note.nettete if note is not None else 0.0,
                ),
                item,
            )
        )
    if not classes:
        return None
    return max(classes, key=lambda c: c[0])[1]


async def photos_par_carte(
    db: AsyncSession, user_id: uuid.UUID, card_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, PhotoDeJeu]:
    """``card_id → photo`` pour les cartes données, parmi les exemplaires de ``user_id``.

    Bornée aux cartes demandées (celles visibles en jeu, ou celles d'un deck) : on ne charge jamais
    la collection entière pour afficher un plateau.
    """
    ids = list({c for c in card_ids})
    if not ids:
        return {}
    rows = (
        (
            await db.execute(
                select(CollectionItem).where(
                    CollectionItem.user_id == user_id,
                    CollectionItem.card_id.in_(ids),
                    CollectionItem.photo_s3_key.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    par_carte: dict[uuid.UUID, list[CollectionItem]] = {}
    for item in rows:
        par_carte.setdefault(item.card_id, []).append(item)
    resultat: dict[uuid.UUID, PhotoDeJeu] = {}
    for card_id, items in par_carte.items():
        choisi = _meilleur(items)
        if choisi is not None:
            resultat[card_id] = _photo_de(choisi)
    return resultat


# --- Résolution pour une partie -----------------------------------------------------------------


@dataclass(frozen=True)
class RendusPartie:
    """Les rendus résolus d'une partie, pour **les deux regards** à la fois.

    La clé est ``(regard, propriétaire, ref)`` — trois éléments, et aucun n'est superflu : le même
    Pokémon vu par son propriétaire et par l'adversaire peut porter deux rendus différents (c'est
    tout l'objet du veto de confidentialité), et deux joueurs peuvent jouer la même carte avec des
    photos différentes.

    On résout pour les deux sièges d'un coup parce que le canal temps réel projette **un** résultat
    vers **tous** les abonnés (``HUB.publier``) : une résolution par regard, faite au moment de
    l'enrichissement, demanderait une lecture de base par abonné.
    """

    par_regard: dict[tuple[str, str, str], dict]

    def pour(self, regard: str, proprietaire: str, ref: str) -> dict | None:
        """Le rendu de ``ref`` chez ``proprietaire``, vu par ``regard`` — ``None`` si aucun."""
        return self.par_regard.get((regard, proprietaire, ref))

    def __bool__(self) -> bool:
        return bool(self.par_regard)


@dataclass(frozen=True)
class _Joueur:
    """Un siège résolu : son identifiant moteur, ses réglages, sa préférence de deck, son pseudo."""

    joueur_id: str
    user_id: uuid.UUID
    reglages: ReglagesRendu
    preference_deck: str | None
    pseudo: str | None


async def _joueurs_de_partie(db: AsyncSession, game_id: uuid.UUID) -> list[_Joueur]:
    """Les deux sièges d'une partie, réglages et préférence de deck résolus."""
    rows = (
        (
            await db.execute(
                select(GamePlayer)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.seat)
            )
        )
        .scalars()
        .all()
    )
    joueurs: list[_Joueur] = []
    for place in rows:
        deck = await db.get(Deck, place.deck_id) if place.deck_id is not None else None
        utilisateur = await db.get(User, place.user_id)
        joueurs.append(
            _Joueur(
                joueur_id=str(place.user_id),
                user_id=place.user_id,
                reglages=await charger_reglages(db, place.user_id),
                preference_deck=deck.rendu_cartes if deck is not None else None,
                pseudo=utilisateur.pseudo if utilisateur is not None else None,
            )
        )
    return joueurs


async def rendus_de_partie(
    db: AsyncSession,
    game_id: uuid.UUID,
    *,
    ids_par_ref: Mapping[str, uuid.UUID],
) -> RendusPartie:
    """Résout le rendu de chaque ``ref`` visible, pour chaque propriétaire et chaque regard.

    ``ids_par_ref`` vient de l'adaptateur de catalogue (``ref`` d'état → ``cards.id``) : une ref
    inconnue du catalogue n'a pas de rendu du tout, et n'en reçoit pas un inventé (D9).

    Ne fabrique **aucune** image : voir l'en-tête du module.
    """
    joueurs = await _joueurs_de_partie(db, game_id)
    if not joueurs or not ids_par_ref:
        return RendusPartie(par_regard={})

    photos: dict[str, dict[uuid.UUID, PhotoDeJeu]] = {
        j.joueur_id: await photos_par_carte(db, j.user_id, ids_par_ref.values()) for j in joueurs
    }

    par_regard: dict[tuple[str, str, str], dict] = {}
    for regard in joueurs:
        for proprietaire in joueurs:
            for ref, card_id in ids_par_ref.items():
                rendu = choisir_rendu(
                    card_id=card_id,
                    photo=photos[proprietaire.joueur_id].get(card_id),
                    reglages=proprietaire.reglages,
                    preference_deck=proprietaire.preference_deck,
                    pseudo_proprietaire=proprietaire.pseudo,
                    cest_moi=regard.joueur_id == proprietaire.joueur_id,
                    game_id=game_id,
                )
                if rendu is not None:
                    par_regard[(regard.joueur_id, proprietaire.joueur_id, ref)] = rendu.en_json()
    return RendusPartie(par_regard=par_regard)


# --- Servir une photo (route) -------------------------------------------------------------------


async def servir_photo(
    db: AsyncSession,
    storage: StorageBackend,
    *,
    game_id: uuid.UUID,
    item_id: uuid.UUID,
    regardant_id: uuid.UUID,
) -> tuple[bytes, str]:
    """La variante de jeu d'une photo, pour un joueur de cette partie — ou 404.

    **Toute la décision est rejouée ici**, elle n'est pas supposée acquise parce que l'URL a été
    émise : participation du regardant, appartenance de l'exemplaire à un joueur de la partie,
    préférence du propriétaire et veto de confidentialité. Une URL devinée ou gardée d'une partie
    précédente ne sert donc rien.
    """
    joueurs = await _joueurs_de_partie(db, game_id)
    par_user = {j.user_id: j for j in joueurs}
    if regardant_id not in par_user:
        raise PhotoIntrouvable("le regardant ne participe pas à cette partie")

    item = await db.get(CollectionItem, item_id)
    if item is None or item.photo_s3_key is None:
        raise PhotoIntrouvable("exemplaire inconnu ou sans photo")
    proprietaire = par_user.get(item.user_id)
    if proprietaire is None:
        raise PhotoIntrouvable("cet exemplaire n'appartient à aucun joueur de la partie")

    cest_moi = proprietaire.user_id == regardant_id
    if preference_effective(proprietaire.reglages, proprietaire.preference_deck) != RENDU_PHOTO:
        raise PhotoIntrouvable("le propriétaire joue avec les images officielles")
    if not cest_moi and proprietaire.reglages.jamais_montrer_mes_photos:
        raise PhotoIntrouvable("le propriétaire ne montre pas ses photos")

    # Une seule image à fabriquer, et seulement si elle manque : c'est le chemin de rattrapage des
    # exemplaires photographiés avant ce lot.
    if item.jeu_image_key is None:
        note = await preparer_variante(db, storage, item)
        await db.commit()
        if note is None or not note.exploitable or item.jeu_image_key is None:
            raise PhotoIntrouvable("photo non exploitable en jeu")

    donnees = await storage.get(item.jeu_image_key)
    if donnees is None:
        raise PhotoIntrouvable("variante de jeu absente du stockage")
    return donnees, TYPE_MIME_JEU


# --- Aperçu pour le constructeur de deck --------------------------------------------------------


@dataclass(frozen=True)
class ApercuCarte:
    """Ce qu'une carte du deck montrera en jeu, et pourquoi — pour le constructeur de deck."""

    card_id: uuid.UUID
    nom: str
    origine: str
    raison: str | None


async def apercu_deck(
    db: AsyncSession, storage: StorageBackend, *, user_id: uuid.UUID, deck_id: uuid.UUID
) -> list[ApercuCarte]:
    """Ce que chaque carte du deck montrera en jeu — en **préparant** les variantes manquantes.

    C'est le moment « produit à l'avance » du lot : borné aux cartes du deck, déclenché par le
    joueur qui regarde son deck, et c'est là qu'on lui **dit** ce qui se repliera sur l'officielle.
    Le deck est vérifié comme appartenant à ``user_id`` par l'appelant (route).
    """
    reglages = await charger_reglages(db, user_id)
    deck = await db.get(Deck, deck_id)
    preference_deck = deck.rendu_cartes if deck is not None else None

    cartes = (
        (
            await db.execute(
                select(Card)
                .join(DeckCard, DeckCard.card_id == Card.id)
                .where(DeckCard.deck_id == deck_id)
                .order_by(Card.name, Card.number)
            )
        )
        .scalars()
        .all()
    )
    if not cartes:
        return []

    # Prépare les variantes manquantes des exemplaires concernés, une fois, avant de conclure.
    items = (
        (
            await db.execute(
                select(CollectionItem).where(
                    CollectionItem.user_id == user_id,
                    CollectionItem.card_id.in_([c.id for c in cartes]),
                    CollectionItem.photo_s3_key.isnot(None),
                    CollectionItem.jeu_qualite.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for item in items:
        await preparer_variante(db, storage, item)
    if items:
        await db.commit()

    photos = await photos_par_carte(db, user_id, [c.id for c in cartes])
    apercus: list[ApercuCarte] = []
    for carte in cartes:
        origine, raison = decider_origine(
            photo=photos.get(carte.id),
            reglages=reglages,
            preference_deck=preference_deck,
            cest_moi=True,
        )
        apercus.append(
            ApercuCarte(card_id=carte.id, nom=carte.name, origine=origine, raison=raison)
        )
    return apercus


__all__ = [
    "ApercuCarte",
    "PhotoIntrouvable",
    "RendusPartie",
    "RenduValeurInvalide",
    "apercu_deck",
    "charger_reglages",
    "enregistrer_reglages",
    "photos_par_carte",
    "preparer_variante",
    "rendus_de_partie",
    "servir_photo",
]
