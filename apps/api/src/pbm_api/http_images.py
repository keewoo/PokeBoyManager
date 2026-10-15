"""Servir une image avec son **empreinte** : le cache du navigateur, et le 304 qui l'exploite.

Avant le lot ``j-assets-pipeline``, les deux routes d'images du produit se comportaient comme si
aucun navigateur n'avait de cache : ``/img/cards/{id}`` ne posait **aucun** en-tête, et
``/jeu/rendu/parties/…/photos/{item}`` un ``private, max-age=3600`` sans empreinte. Conséquence
mesurable : rouvrir un plateau une heure plus tard, ou simplement recharger la page, refaisait
passer tout le poids d'images sur le réseau. Un budget tenu à l'octet (:mod:`pbm_api.jeu.budget`)
ne sert à rien s'il est payé à chaque F5.

Deux régimes, et la différence n'est pas cosmétique :

* **immuable** — l'image officielle d'une carte. Son contenu ne change jamais pour un couple
  (carte, taille) donné : on peut donc promettre ``immutable`` et un an de validité, et le
  navigateur ne redemande **rien**, pas même une revalidation.
* **révocable** — la variante de jeu d'une photo personnelle. Elle change quand son propriétaire
  reprend la photo. L'empreinte (``ETag``) est le seul moyen honnête : le navigateur garde l'image
  et redemande avec ``If-None-Match``, on répond **304** sans corps si rien n'a bougé, et le
  nouveau contenu part dès que la photo est refaite. Promettre ``immutable`` ici afficherait
  l'ancienne photo pendant un an.

L'empreinte est calculée sur les octets **déjà lus** pour répondre : elle ne coûte aucune lecture
supplémentaire, et elle est juste par construction (un contenu différent donne une empreinte
différente, sans dépendre d'une date de modification que le stockage objet local ne garantit pas).
"""

from __future__ import annotations

import hashlib

from fastapi import Response, status

#: Validité d'une image immuable : un an, la valeur maximale raisonnable de ``max-age``.
UN_AN_EN_SECONDES = 31_536_000

#: Validité d'une variante de jeu avant revalidation. Un jour : au-delà, la photo d'un joueur qui
#: la reprend tarderait trop à apparaître chez son adversaire ; en dessous, on paierait des
#: revalidations pour rien. La revalidation est de toute façon gratuite (304, aucun corps).
UN_JOUR_EN_SECONDES = 86_400


def empreinte(donnees: bytes) -> str:
    """L'ETag de ``donnees`` : un SHA-256 tronqué, entre guillemets comme l'exige la RFC 9110.

    Tronqué à 32 caractères hexadécimaux (128 bits) : largement assez pour qu'une collision soit
    hors de portée, et deux fois plus court dans chaque requête que l'empreinte complète.
    """
    return f'"{hashlib.sha256(donnees).hexdigest()[:32]}"'


def _deja_a_jour(entete_if_none_match: str | None, etag: str) -> bool:
    """``True`` si le navigateur détient déjà cette version exacte.

    Un ``If-None-Match`` peut porter plusieurs empreintes séparées par des virgules, et chacune
    peut être préfixée de ``W/`` (validateur faible). On compare donc membre à membre plutôt que
    la chaîne entière — sinon un navigateur qui envoie deux empreintes ne recevrait jamais de 304.
    """
    if not entete_if_none_match:
        return False
    if entete_if_none_match.strip() == "*":
        return True
    for candidat in entete_if_none_match.split(","):
        propre = candidat.strip()
        if propre.startswith("W/"):
            propre = propre[2:]
        if propre == etag:
            return True
    return False


def reponse_image(
    donnees: bytes,
    type_mime: str,
    *,
    if_none_match: str | None = None,
    immuable: bool = False,
    privee: bool = False,
    duree: int | None = None,
) -> Response:
    """Une réponse d'image avec son empreinte, ou **304** si le client l'a déjà.

    :param immuable: le contenu ne changera jamais pour cette URL (image officielle d'une carte).
    :param privee: la photo d'un joueur — ``private``, elle n'a rien à faire dans un cache partagé.
    :param duree: ``max-age`` en secondes ; par défaut un an si immuable, un jour sinon.

    Le 304 porte l'``ETag`` et le ``Cache-Control`` mais **aucun corps** : c'est tout l'intérêt, et
    c'est ce que la RFC exige.
    """
    etag = empreinte(donnees)
    age = duree if duree is not None else (UN_AN_EN_SECONDES if immuable else UN_JOUR_EN_SECONDES)
    portee = "private" if privee else "public"
    cache = f"{portee}, max-age={age}" + (", immutable" if immuable else "")
    entetes = {"Cache-Control": cache, "ETag": etag}

    if _deja_a_jour(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=entetes)
    return Response(content=donnees, media_type=type_mime, headers=entetes)


__all__ = [
    "UN_AN_EN_SECONDES",
    "UN_JOUR_EN_SECONDES",
    "empreinte",
    "reponse_image",
]
