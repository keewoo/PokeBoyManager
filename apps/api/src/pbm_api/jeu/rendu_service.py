"""Côté base du rendu des cartes en jeu (lot ``j-rendu-carte``) : réglages, variantes, résolution.

La **décision** (quel rendu, pour quel regard) est pure et vit dans :mod:`pbm_api.jeu.rendu` ; la
**mesure** de qualité dans :mod:`pbm_api.jeu.rendu_qualite` ; la **fabrication** d'image dans
:mod:`pbm_api.jeu.rendu_image`. Ce module est l'adaptateur : il lit la base et le stockage objet,
et alimente les trois autres en données. Le moteur (``pbm_game``) n'apparaît nulle part ici — il ne
connaît ni image ni URL, et ce lot ne lui en apprend aucune.

**Où les variantes sont produites**, et pourquoi là — revu par ``j-assets-pipeline`` :

* à l'**ajout en collection**, dans le worker (``preparer_variantes_jeu_task``) : le moment que
  nomme la fiche du lot, et le seul qui ne fasse attendre personne — la route de validation enfile
  le job et répond, le décodage se joue ailleurs ;
* au **constructeur de deck** (:func:`apercu_deck`) : filet pour ce que le worker n'a pas encore
  traité, borné aux cartes du deck, et c'est là qu'on **dit** au joueur ce qui se repliera sur
  l'officielle ;
* par **lots sur la flotte** (``scripts/preparer_rendus_jeu.py``) : pour tout le parc déjà
  photographié, et pour un changement de recette (une variante ajoutée, une largeur revue) ;
* **jamais** pendant une partie — ni dans la projection, ni dans :func:`servir_photo`, qui
  fabriquait encore au premier accès avant ce lot. Un plateau se lit plusieurs fois par seconde et
  demande jusqu'à 120 images ; y décoder des photos met à genoux la machine qui sert. Une photo
  pas encore préparée se replie sur l'officielle **en le disant** (``RAISON_PAS_PRETE`` dans la
  vue, 404 sur la route) — le critère du lot est « sans trou ni attente », pas « coûte que coûte ».
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu import vedettes
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
    VARIANTE_ZOOM,
    VARIANTES,
    PhotoIndecodable,
    Variante,
    VarianteTropLourde,
    cle_image_jeu,
    cle_variante,
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

#: Clé, dans ``collection_items.jeu_qualite``, où est inscrite la liste des variantes produites.
#:
#: Rangée **avec la note** plutôt que dans une colonne neuve : les deux sont écrites par le même
#: appel, dans le même flush, et séparer deux informations qui ne peuvent pas diverger aurait
#: coûté une migration — donc une tête Alembic de plus, à fusionner avec celle du lot voisin.
#: L'absence de cette clé sur une ligne ancienne signifie « préparée avant le dédoublement des
#: variantes », ce qui est exactement l'information dont le rattrapage a besoin.
CLE_VARIANTES = "variantes"


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
    """Note la photo de ``item`` et produit **toutes** ses variantes de jeu. **Idempotent**.

    Rend la note obtenue, ou ``None`` si l'exemplaire n'a pas de photo. Trois cas, tous écrits en
    base pour ne pas être recalculés à chaque partie :

    * photo exploitable → variantes produites, ``jeu_image_key`` posée ;
    * photo inexploitable → ``jeu_image_key`` laissée vide et la **raison** stockée : c'est elle que
      le joueur lira dans son constructeur de deck ;
    * photo illisible (:class:`PhotoIndecodable`) → la panne est notée comme une raison de repli,
      jamais avalée.

    Un second appel sur un exemplaire déjà préparé ne refait rien (ni décodage, ni écriture) : la
    préparation est appelée depuis un écran, elle doit coûter zéro la deuxième fois.

    **Le jeu de variantes produites est inscrit en base** (:data:`CLE_VARIANTES` dans
    ``jeu_qualite``), et c'est ce qui rend l'idempotence vraie *après un changement de recette* :
    un exemplaire préparé par ``j-rendu-carte``, qui n'avait que le zoom, est reconnu comme
    incomplet et gagne sa variante de plateau au prochain passage — sans qu'on ait à relire le
    stockage objet pour chaque carte d'un deck.
    """
    if item.photo_s3_key is None:
        return None
    if item.jeu_image_key is not None and item.jeu_qualite is not None:
        if not _variantes_manquantes(item):
            return NotePhoto.depuis_json(item.jeu_qualite)
        return await _completer_variantes(db, storage, item)

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
        produites, refus = await _produire(storage, item, photo, VARIANTES)
        if refus is not None:
            # Une variante hors budget n'est pas servie en silence (D9) : la photo devient
            # inexploitable et se replie sur l'officielle, avec la raison écrite en base.
            item.jeu_qualite = {**note.en_json(), "exploitable": False, "raison": refus}
            await db.flush()
            return NotePhoto.depuis_json(item.jeu_qualite)
        item.jeu_qualite = {**note.en_json(), CLE_VARIANTES: produites}
        item.jeu_image_key = cle_image_jeu(item.user_id, item.id)
    await db.flush()
    return note


async def _produire(
    storage: StorageBackend,
    item: CollectionItem,
    photo: bytes,
    variantes: Iterable[Variante],
) -> tuple[list[str], str | None]:
    """Fabrique et range ``variantes`` pour ``item``. Rend les noms produits, et le refus éventuel.

    Le refus est une **phrase** (la raison de repli lue par le joueur), pas une exception qui
    remonterait : une photo trop bruitée pour tenir sous son plafond est un cas prévu du produit,
    pas une panne du serveur — mais elle est nommée, jamais avalée.
    """
    produites: list[str] = []
    for variante in variantes:
        try:
            donnees = fabriquer_image_jeu(photo, variante)
        except VarianteTropLourde as exc:
            return produites, f"photo trop lourde pour le jeu ({exc})"
        await storage.put(cle_variante(item.user_id, item.id, variante), donnees, TYPE_MIME_JEU)
        produites.append(variante.nom)
    return produites, None


def _variantes_manquantes(item: CollectionItem) -> tuple[Variante, ...]:
    """Les variantes que ``item`` n'a pas encore, d'après ce que la base a inscrit.

    Un exemplaire préparé avant le dédoublement des variantes n'a pas de liste inscrite : toutes
    sont donc déclarées manquantes, et un passage de préparation les produit. C'est le chemin de
    rattrapage du lot, et il est **hors partie** par construction (voir :func:`servir_photo`).
    """
    inscrites = variantes_pretes(item)
    return tuple(v for v in VARIANTES if v.nom not in inscrites)


def variantes_pretes(item: CollectionItem) -> frozenset[str]:
    """Les noms des variantes effectivement produites pour ``item``, d'après la base.

    Lu par le script de fabrication par lots (``scripts/preparer_rendus_jeu.py``) autant que
    par la préparation : une seule source pour « qu'est-ce qui existe déjà ».
    """
    if not item.jeu_qualite:
        return frozenset()
    noms = item.jeu_qualite.get(CLE_VARIANTES)
    return frozenset(noms) if isinstance(noms, list) else frozenset()


async def _completer_variantes(
    db: AsyncSession, storage: StorageBackend, item: CollectionItem
) -> NotePhoto | None:
    """Produit les variantes manquantes d'un exemplaire **déjà noté**, sans le renoter.

    La note de qualité ne dépend que de la photo d'origine, qui n'a pas changé : la refaire
    coûterait un décodage OpenCV pour un résultat identique.
    """
    photo = await storage.get(item.photo_s3_key) if item.photo_s3_key else None
    if photo is None:
        return NotePhoto.depuis_json(item.jeu_qualite)
    produites, refus = await _produire(storage, item, photo, _variantes_manquantes(item))
    if refus is not None:
        item.jeu_qualite = {**item.jeu_qualite, "exploitable": False, "raison": refus}
        item.jeu_image_key = None
        await db.flush()
        return NotePhoto.depuis_json(item.jeu_qualite)
    deja = sorted(variantes_pretes(item) | set(produites))
    item.jeu_qualite = {**item.jeu_qualite, CLE_VARIANTES: deja}
    await db.flush()
    return NotePhoto.depuis_json(item.jeu_qualite)


async def invalider_variantes(
    db: AsyncSession, storage: StorageBackend, item: CollectionItem
) -> None:
    """Efface les variantes de ``item`` et sa note : la photo d'origine a changé.

    À appeler **chaque fois** que ``photo_s3_key`` est réaffecté. Au 15/10/2026 aucune route du
    produit ne remplace la photo d'un exemplaire existant (une nouvelle détection crée un nouvel
    exemplaire), donc ce chemin n'a pas encore d'appelant en production — il est là parce que le
    jour où un écran « reprendre la photo » existera, l'oublier afficherait l'ancienne photo
    indéfiniment : les variantes sont nommées d'après l'exemplaire, pas d'après la photo, et rien
    dans leur clé ne changerait. Un test le garde (``test_jeu_assets_pipeline.py``).

    Les objets sont **supprimés** et pas seulement déréférencés : laisser l'ancienne variante dans
    le stockage, c'est garder une photo que son propriétaire croit avoir remplacée.
    """
    for variante in VARIANTES:
        await storage.delete(cle_variante(item.user_id, item.id, variante))
    item.jeu_image_key = None
    item.jeu_qualite = None
    await db.flush()


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


async def _vedettes_visibles(
    db: AsyncSession, card_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """``card_id → tcgdex_id`` pour les seules cartes visibles qui sont des **vedettes publiées**.

    Une requête, une fois par vue de partie, et son résultat est borné **des deux côtés** : par les
    cartes réellement visibles et par la liste des vedettes (dix-sept au 15/10/2026). Elle ne rend
    donc jamais plus de lignes qu'il n'y a d'apparitions publiées, quelle que soit la taille du
    plateau.

    ⛔ **On ne demande jamais au stockage objet « cette découpe existe-t-elle ? ».** Une vue de
    partie résout jusqu'à 120 cartes, pour deux regards : une vérification d'existence par carte,
    ce sont jusqu'à 120 allers-retours réseau sur chaque rafraîchissement d'écran, et un plateau
    se relit plusieurs fois par seconde. C'est la raison d'être du registre versionné
    (:mod:`pbm_api.jeu.vedettes`) : l'appartenance se lit dans un ``frozenset`` en mémoire, et ce
    que le registre annonce est ce que la chaîne de découpe a réellement déposé. Si l'objet
    manquait quand même, la route rend 404 et l'écran se passe d'apparition — jamais d'attente.

    Le registre vide (aucune vedette publiée) ne déclenche **aucune** requête : le cas nominal d'un
    environnement sans découpes déployées ne doit rien coûter.
    """
    publiees = vedettes.publiees()
    ids = list(set(card_ids))
    if not publiees or not ids:
        return {}
    lignes = await db.execute(
        select(Card.id, Card.tcgdex_id).where(
            Card.id.in_(ids), Card.tcgdex_id.in_(publiees)
        )
    )
    return {card_id: tcgdex_id for card_id, tcgdex_id in lignes.all()}


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
    vedettes_vues = await _vedettes_visibles(db, ids_par_ref.values())

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
                    tcgdex_id=vedettes_vues.get(card_id),
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
    variante: Variante = VARIANTE_ZOOM,
) -> tuple[bytes, str]:
    """La variante demandée d'une photo, pour un joueur de cette partie — ou 404.

    **Toute la décision est rejouée ici**, elle n'est pas supposée acquise parce que l'URL a été
    émise : participation du regardant, appartenance de l'exemplaire à un joueur de la partie,
    préférence du propriétaire et veto de confidentialité. Une URL devinée ou gardée d'une partie
    précédente ne sert donc rien.

    ⛔ **Aucune image n'est fabriquée ici** — c'est un critère du lot ``j-assets-pipeline``, et ça
    n'a pas toujours été vrai : ``j-rendu-carte`` rattrapait ici la variante manquante, au premier
    accès. Une route d'image de partie est appelée jusqu'à 120 fois en quelques secondes, par deux
    joueurs à la fois ; y décoder et réencoder des photos met à genoux la machine qui sert (le VPS
    a deux cœurs, et c'est le risque nommé par la fiche du lot). Une variante absente rend donc
    **404**, l'écran retombe sur ``url_repli`` (l'image officielle), et la préparation se fait là
    où elle ne gêne personne : à l'ajout en collection (job ``preparer_variantes_jeu``), au
    constructeur de deck (:func:`apercu_deck`) ou par lots sur la flotte
    (``scripts/preparer_rendus_jeu.py``).

    Le défaut reste la variante de **zoom** : c'est la seule qu'ait connue ``j-rendu-carte``, donc
    celle que désignent les URL sans ``?v=`` émises avant ce lot.
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

    if item.jeu_image_key is None:
        raise PhotoIntrouvable("photo non exploitable en jeu, ou variante pas encore préparée")
    if variante.nom not in variantes_pretes(item) and variante is not VARIANTE_ZOOM:
        # Exemplaire préparé avant le dédoublement des variantes : le zoom existe, le plateau non.
        # On le dit par un 404 (l'écran prend l'officielle) plutôt que de servir le zoom à sa
        # place — 45 Ko au lieu de 12, cent vingt fois, c'est exactement le budget qu'on borne.
        raise PhotoIntrouvable(f"variante « {variante.nom} » pas encore préparée")

    donnees = await storage.get(cle_variante(item.user_id, item.id, variante))
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
    # Le filtre retient deux cas, et le second a été ajouté par `j-assets-pipeline` : l'exemplaire
    # jamais noté (`jeu_qualite IS NULL`), et l'exemplaire noté AVANT le dédoublement des variantes
    # (`jeu_qualite` sans clé `variantes`), qui n'a que son zoom. Sans ce second cas, un joueur dont
    # la collection date d'avant ce lot n'aurait jamais de variante de plateau — donc jouerait
    # indéfiniment avec les images officielles, sans que rien ne le signale.
    items = (
        (
            await db.execute(
                select(CollectionItem).where(
                    CollectionItem.user_id == user_id,
                    CollectionItem.card_id.in_([c.id for c in cartes]),
                    CollectionItem.photo_s3_key.isnot(None),
                    or_(
                        CollectionItem.jeu_qualite.is_(None),
                        ~CollectionItem.jeu_qualite.op("?")(CLE_VARIANTES),
                    ),
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
    "CLE_VARIANTES",
    "ApercuCarte",
    "PhotoIntrouvable",
    "RendusPartie",
    "RenduValeurInvalide",
    "apercu_deck",
    "charger_reglages",
    "enregistrer_reglages",
    "invalider_variantes",
    "photos_par_carte",
    "preparer_variante",
    "rendus_de_partie",
    "servir_photo",
]
