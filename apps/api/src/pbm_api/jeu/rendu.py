"""**Quel rendu pour quelle carte, pour quel regard** — la décision DJ5, pure (``j-rendu-carte``).

Trois rendus existent pour une carte en jeu : la **photo personnelle** de son propriétaire (le
cœur de la promesse : on joue avec SES cartes), l'**image officielle** du catalogue, et le **dos**
de carte (celui-là est dessiné par l'écran, le serveur n'a aucune image à en donner — une carte
face cachée n'a pas d'identité à révéler).

DJ5, telle que JF l'a tranchée le 14/10/2026 : *« Oui par défaut côté joueur, et réglage par deck :
"mes cartes telles que je les ai photographiées" ou "images officielles". L'adversaire voit ce que
le joueur a choisi de montrer ; un réglage "ne jamais montrer mes photos" existe. »*

Trois niveaux, du plus large au plus fort :

1. le **défaut du compte** (``jeu_rendu_reglages.rendu_defaut``), ``"photo"`` par défaut ;
2. la préférence **du deck** (``decks.rendu_cartes``), qui l'emporte quand elle est posée ;
3. le **veto** ``jamais_montrer_mes_photos``, qui l'emporte sur les deux — mais **seulement pour
   le regard de l'adversaire** : son propriétaire continue de voir ses propres photos.

Le veto est évalué **avant** toute consultation de la photo : c'est ce qui garantit qu'aucune URL
de photo ne peut être émise par erreur d'ordre, et que la raison renvoyée à l'adversaire ne révèle
pas *si* une photo existe (elle est la même dans les deux cas).

Le serveur fait autorité : l'écran ne choisit rien, il affiche l'URL qu'on lui donne. C'est aussi
ce qui rend le réglage de confidentialité **vérifiable** — il n'y a pas un second chemin, côté
client, par lequel la photo pourrait passer.

Pur : aucune E/S, aucune base. Les lectures de base vivent dans
:mod:`pbm_api.jeu.rendu_service`, qui alimente ces fonctions en données.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from pbm_api.jeu import vedettes
from pbm_api.jeu.rendu_image import VARIANTE_PLATEAU, VARIANTE_ZOOM, Variante
from pbm_api.jeu.rendu_qualite import (
    RAISON_CONFIDENTIALITE,
    RAISON_PREFERENCE,
    RAISON_SANS_PHOTO,
    NotePhoto,
)

#: Rendu « ma photo » : la carte telle que son propriétaire l'a photographiée.
RENDU_PHOTO = "photo"
#: Rendu « image officielle » : celle du catalogue, identique pour tout le monde.
RENDU_OFFICIELLE = "officielle"
#: Rendu « dos de carte » : dessiné par l'écran pour une carte face cachée (aucune image serveur).
RENDU_DOS = "dos"

#: Le vocabulaire **réglable** par le joueur. Le dos n'en fait pas partie : il n'est pas une
#: préférence, c'est l'état d'une carte qu'on ne voit pas.
RENDUS_REGLABLES: frozenset[str] = frozenset({RENDU_PHOTO, RENDU_OFFICIELLE})

#: La variante de jeu n'est pas encore produite pour cet exemplaire (photo arrivée avant ce lot, ou
#: préparation en échec). L'image officielle est servie — **sans attente** : le critère du lot est
#: qu'une carte sans photo exploitable se joue « sans trou ni attente », donc on ne fait jamais
#: patienter un plateau le temps d'une fabrication d'image.
RAISON_PAS_PRETE = "photo pas encore préparée pour le jeu"

#: Il n'existe aucun cadre (partie ou lancement) qui autoriserait à servir cette photo : c'est le
#: cas de la **vitrine du profil**, qu'on regarde hors de toute rencontre. L'image officielle est
#: servie, et la raison le dit — plutôt qu'un cadre inventé « juste pour afficher ».
RAISON_HORS_CADRE = "hors d'une partie, les photos ne sont pas servies"


@dataclass(frozen=True)
class ReglagesRendu:
    """Les réglages de rendu d'un compte — les **défauts DJ5** quand il n'y a jamais touché.

    Ces défauts doivent rester d'accord avec les ``server_default`` de
    :class:`pbm_api.models.jeu_rendu.JeuRenduReglages` (un test le vérifie) : deux jeux de défauts
    qui divergent, c'est un réglage qui change de sens selon qu'une ligne existe ou non.
    """

    rendu_defaut: str = RENDU_PHOTO
    jamais_montrer_mes_photos: bool = False


@dataclass(frozen=True)
class PhotoDeJeu:
    """La photo d'un exemplaire possédé, vue du rendu : son identifiant, son état, sa note.

    ``prete`` dit si la **variante de jeu** existe (:mod:`pbm_api.jeu.rendu_image`) — c'est elle
    qu'on sert, jamais l'original pleine résolution. ``note`` est la note de qualité stockée,
    ``None`` si la photo n'a jamais été notée.
    """

    item_id: uuid.UUID
    prete: bool
    note: NotePhoto | None


@dataclass(frozen=True)
class RenduResolu:
    """Ce que l'écran doit afficher pour une carte, et pourquoi.

    ``url`` est la taille **plateau**, ``url_zoom`` la taille **zoom** (« lisible sans pincer
    l'écran ») : les deux sont données par le serveur pour que l'écran n'ait aucune règle de taille
    à deviner. Pour une photo, c'est la même variante — elle est déjà dimensionnée pour le zoom.

    ``credit`` est l'indicateur discret « photo de Aymeric » : posé **seulement** quand la photo
    n'est pas la mienne (sur mes propres cartes, le crédit serait du bruit). ``raison`` dit pourquoi
    l'officielle a remplacé la photo — c'est ce que le constructeur de deck montre au joueur, et
    c'est ``None`` quand la photo est bien servie.

    ``url_repli`` n'accompagne qu'une **photo** : c'est l'image officielle de la même carte, pour
    que l'écran ait de quoi afficher si la photo ne se charge pas (variante effacée du stockage,
    réseau coupé en pleine partie). Elle ne révèle rien — l'officielle est publique, servie par le
    même proxy pour tout le monde — et c'est ce qui tient le critère « sans trou ni attente »
    jusque dans le cas dégradé.

    ``apparition`` (lot ``j-anim-pokemon-apparition``) est l'URL de la **découpe du Pokémon**, celle
    que l'animation fait surgir au-dessus de la carte. ``None`` sur l'immense majorité des cartes :
    seules les vedettes du registre (:mod:`pbm_api.jeu.vedettes`) en ont une, et une carte sans
    découpe joue l'effet de type générique (D9) — l'écran n'a aucune image à deviner, il lit ce
    champ ou il s'en passe.
    """

    origine: str
    url: str
    url_zoom: str
    credit: str | None = None
    raison: str | None = None
    url_repli: str | None = None
    apparition: str | None = None

    def en_json(self) -> dict:
        """Forme portée par la vue de partie, lue telle quelle par l'écran."""
        return {
            "origine": self.origine,
            "url": self.url,
            "url_zoom": self.url_zoom,
            "credit": self.credit,
            "raison": self.raison,
            "url_repli": self.url_repli,
            "apparition": self.apparition,
        }


def url_officielle(card_id: uuid.UUID, *, taille: str = "low") -> str:
    """L'URL de l'image officielle d'une carte — le proxy public ``/img/cards/{id}``.

    Ce proxy met déjà l'image en cache dans le stockage objet (lot ``v2-catalogue``) : l'officielle
    ne coûte donc pas un aller-retour chez TCGdex à chaque partie.
    """
    return f"/img/cards/{card_id}?size={taille}"


def url_photo(
    game_id: uuid.UUID, item_id: uuid.UUID, variante: Variante = VARIANTE_PLATEAU
) -> str:
    """L'URL d'une variante de jeu d'une photo, **bornée à une partie**.

    La partie est dans le chemin, et ce n'est pas décoratif : c'est elle qui donne le droit de
    regarder. Hors d'une partie partagée, l'adversaire n'a aucune raison de voir mes photos — la
    route (:mod:`pbm_api.routers.jeu_rendu`) revérifie la participation **et** le veto, pour que la
    confidentialité ne repose pas seulement sur le fait que l'URL n'a pas été publiée.

    ``?v=`` nomme la variante voulue (lot ``j-assets-pipeline``) : le plateau en charge jusqu'à 120,
    le zoom une seule à la fois, et c'est cet écart de poids qui fait tenir le budget d'une partie
    (:mod:`pbm_api.jeu.budget`). Le défaut est la variante **plateau** : c'est celle que l'écran
    demande le plus souvent, et laisser le zoom par défaut ferait du cas coûteux le cas implicite.
    """
    return f"/jeu/rendu/parties/{game_id}/photos/{item_id}?v={variante.nom}"


def url_photo_lancement(
    launch_id: uuid.UUID, item_id: uuid.UUID, variante: Variante = VARIANTE_ZOOM
) -> str:
    """L'URL d'une variante de jeu d'une photo, **bornée à un lancement** (lot ``j-profil-jeu``).

    Jumelle de :func:`url_photo`, avec un autre cadre d'autorisation : au moment du lancement, la
    partie **n'existe pas encore** (elle est créée quand le pile ou face est tranché), donc aucune
    URL de photo de partie ne peut être émise. Or la carte fétiche se montre précisément là, et
    « avec le rendu choisi » est un critère d'acceptation du lot : il faut donc un cadre, et le
    cadre naturel est le lancement — deux joueurs, une invitation acceptée, exactement le même
    « nous nous sommes trouvés » qu'une partie.

    Le défaut est la variante de **zoom** : une carte fétiche est montrée seule et en grand, jamais
    cent vingt fois comme les cartes d'un plateau — c'est le cas rare où la lourde est la bonne.

    Comme pour une partie, la route (:mod:`pbm_api.routers.jeu_rendu`) **rejoue** toute la
    décision : participation au lancement, propriété de l'exemplaire, préférence et veto. L'URL
    ne donne aucun droit par elle-même.
    """
    return f"/jeu/rendu/lancements/{launch_id}/photos/{item_id}?v={variante.nom}"


def rendu_carte_fetiche(
    *,
    card_id: uuid.UUID,
    photo: PhotoDeJeu | None,
    reglages: ReglagesRendu,
    cest_moi: bool,
    launch_id: uuid.UUID | None,
    pseudo_proprietaire: str | None = None,
) -> RenduResolu:
    """Le rendu d'une **carte fétiche** pour un regard donné (lot ``j-profil-jeu``).

    Passe par :func:`decider_origine` — le même et unique juge que la vue de partie et le
    constructeur de deck. C'est ce qui garantit qu'un joueur qui a coché « ne jamais montrer mes
    photos » ne voit pas sa photo partir par ce nouveau chemin : le veto n'est pas réécrit ici, il
    est **appelé**.

    ``preference_deck`` est volontairement ``None`` : une carte fétiche n'appartient à aucun deck,
    donc c'est le réglage **du compte** qui décide. ``launch_id`` à ``None`` (la vitrine du profil,
    hors de tout lancement) force l'image officielle : il n'y a alors aucun cadre qui autorise une
    photo, et en l'absence de cadre on montre **moins**, jamais plus.

    Rend toujours un :class:`RenduResolu` : une carte du catalogue a toujours son image officielle.
    """
    origine, raison = decider_origine(
        photo=photo, reglages=reglages, preference_deck=None, cest_moi=cest_moi
    )
    if origine == RENDU_PHOTO and launch_id is None:
        origine, raison = RENDU_OFFICIELLE, RAISON_HORS_CADRE
    if origine == RENDU_OFFICIELLE:
        return RenduResolu(
            origine=RENDU_OFFICIELLE,
            url=url_officielle(card_id, taille="low"),
            url_zoom=url_officielle(card_id, taille="high"),
            raison=raison,
        )

    assert photo is not None  # garanti par decider_origine
    assert launch_id is not None  # garanti par le repli ci-dessus
    url = url_photo_lancement(launch_id, photo.item_id, VARIANTE_ZOOM)
    return RenduResolu(
        origine=RENDU_PHOTO,
        url=url,
        url_zoom=url,
        credit=None if cest_moi else _credit(pseudo_proprietaire),
        url_repli=url_officielle(card_id, taille="low"),
    )


def preference_effective(reglages: ReglagesRendu, preference_deck: str | None) -> str:
    """Le rendu voulu par le propriétaire : celui du deck s'il en a un, sinon celui du compte.

    Une valeur inconnue (base retouchée à la main, réglage d'une version future) est traitée comme
    ``"officielle"`` : en cas de doute on montre **moins**, jamais plus — c'est le sens d'un
    réglage de confidentialité.
    """
    voulu = preference_deck or reglages.rendu_defaut
    return voulu if voulu in RENDUS_REGLABLES else RENDU_OFFICIELLE


def decider_origine(
    *,
    photo: PhotoDeJeu | None,
    reglages: ReglagesRendu,
    preference_deck: str | None,
    cest_moi: bool,
) -> tuple[str, str | None]:
    """``(origine, raison)`` : **l'ordre des verdicts de DJ5**, et le seul endroit où il vit.

    ``cest_moi`` dit si le regard est celui du **propriétaire** de la carte (pas celui du joueur
    actif) : c'est lui qui désarme le veto de confidentialité.

    Le constructeur de deck et la vue de partie passent tous deux par ici : sans cela,
    l'avertissement montré au joueur (« ta photo est trop sombre ») et ce qu'il verra réellement
    en jeu pourraient diverger — un mensonge d'écran qu'aucun test ne rattraperait.
    """
    if preference_effective(reglages, preference_deck) == RENDU_OFFICIELLE:
        return RENDU_OFFICIELLE, RAISON_PREFERENCE
    # Le veto, AVANT de regarder s'il existe une photo : aucune URL de photo ne peut fuiter par une
    # erreur d'ordre, et la raison rendue à l'adversaire ne dit pas si une photo existe.
    if not cest_moi and reglages.jamais_montrer_mes_photos:
        return RENDU_OFFICIELLE, RAISON_CONFIDENTIALITE
    if photo is None:
        return RENDU_OFFICIELLE, RAISON_SANS_PHOTO
    if photo.note is not None and not photo.note.exploitable:
        return RENDU_OFFICIELLE, photo.note.raison
    if not photo.prete:
        return RENDU_OFFICIELLE, RAISON_PAS_PRETE
    return RENDU_PHOTO, None


def choisir_rendu(
    *,
    card_id: uuid.UUID | None,
    photo: PhotoDeJeu | None,
    reglages: ReglagesRendu,
    preference_deck: str | None,
    pseudo_proprietaire: str | None,
    cest_moi: bool,
    game_id: uuid.UUID,
    tcgdex_id: str | None = None,
) -> RenduResolu | None:
    """Le rendu d'une carte pour un regard donné, ou ``None`` si aucune image n'existe.

    Rend ``None`` quand la carte est inconnue du catalogue (``card_id is None``) : il n'y a alors
    pas même d'image officielle, et on n'invente rien (D9) — l'écran retombe sur son repère texte.

    ``tcgdex_id`` est **facultatif** : les appelants qui ne résolvent pas le catalogue (constructeur
    de deck, tests purs) n'ont pas à le fournir, et la carte n'a alors simplement pas d'apparition.
    """
    if card_id is None:
        return None

    # L'apparition ne dépend PAS de l'origine de l'image, et c'est volontaire : la découpe est
    # faite à partir de l'**illustration officielle** de la carte, jamais de la photo du joueur.
    # Elle est donc la même qu'on joue avec ses propres photos ou avec les images du catalogue —
    # deux joueurs qui s'affrontent voient surgir le même Dracaufeu. Faire autrement aurait
    # demandé de détourer la photo de chacun, en direct, pendant la partie : le coût CPU est
    # rédhibitoire, et une photo de travers détourée mal donnerait une apparition difforme.
    # Un corollaire discret mais utile : l'apparition ne révèle rien sous veto de confidentialité,
    # puisqu'elle ne contient rien de personnel.
    apparition = (
        vedettes.url_apparition(tcgdex_id)
        if tcgdex_id and tcgdex_id in vedettes.publiees()
        else None
    )

    origine, raison = decider_origine(
        photo=photo, reglages=reglages, preference_deck=preference_deck, cest_moi=cest_moi
    )
    if origine == RENDU_OFFICIELLE:
        return RenduResolu(
            origine=RENDU_OFFICIELLE,
            url=url_officielle(card_id, taille="low"),
            url_zoom=url_officielle(card_id, taille="high"),
            raison=raison,
            apparition=apparition,
        )

    assert photo is not None  # garanti par decider_origine : « photo » implique une photo prête
    # Deux variantes distinctes depuis `j-assets-pipeline` : le plateau charge la légère (12 Ko)
    # jusqu'à 120 fois, le zoom la lourde (45 Ko) une carte à la fois. Servir la même aux deux —
    # ce que faisait `j-rendu-carte` — coûtait 5,2 Mo par partie, et le jeu mourait là.
    return RenduResolu(
        origine=RENDU_PHOTO,
        url=url_photo(game_id, photo.item_id, VARIANTE_PLATEAU),
        url_zoom=url_photo(game_id, photo.item_id, VARIANTE_ZOOM),
        credit=None if cest_moi else _credit(pseudo_proprietaire),
        url_repli=url_officielle(card_id, taille="low"),
        apparition=apparition,
    )


def _credit(pseudo: str | None) -> str:
    """L'indicateur discret du propriétaire d'une photo — « photo de Aymeric ».

    Sans pseudo (un compte qui n'en a pas choisi), on crédite « l'adversaire » plutôt que de
    laisser le crédit vide : le joueur doit comprendre que ce qu'il voit est la carte de quelqu'un,
    pas une image du catalogue.
    """
    return f"photo de {pseudo}" if pseudo else "photo de l'adversaire"


__all__ = [
    "RAISON_HORS_CADRE",
    "RAISON_PAS_PRETE",
    "RENDUS_REGLABLES",
    "RENDU_DOS",
    "RENDU_OFFICIELLE",
    "RENDU_PHOTO",
    "PhotoDeJeu",
    "ReglagesRendu",
    "RenduResolu",
    "choisir_rendu",
    "decider_origine",
    "preference_effective",
    "rendu_carte_fetiche",
    "url_officielle",
    "url_photo",
    "url_photo_lancement",
]
