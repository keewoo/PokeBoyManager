"""Proxy `/img/cards/{id}` : sert l'image officielle, mise en cache dans le stockage objet au
premier accès (mission `v2-catalogue`, point 3). Pas de repli silencieux : une carte sans image
ou une image officielle injoignable renvoie une erreur explicite, jamais un succès vide.

La même famille d'URL sert aussi `/img/apparitions/{tcgdex_id}` (lot `j-anim-pokemon-apparition`) :
la découpe du Pokémon utilisée par l'animation d'apparition. Elle, en revanche, ne fabrique **rien**
— voir :func:`get_apparition`.
"""

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import get_session
from pbm_api.http_images import reponse_image
from pbm_api.jeu import vedettes
from pbm_api.jeu.decoupe import TYPE_MIME_APPARITION
from pbm_api.models import Card
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter()

# `build_storage()` (comme `routers/uploads.py`), jamais `ObjectStorage()` en dur : sur le PROD
# `STORAGE_BACKEND=local` (disque du serveur, aucun S3) — un client S3 codé en dur y lève
# une erreur de connexion et le proxy renvoie 500 pour TOUTES les cartes (l'accueil visiteur du
# lot `pbm-front-accueil` retombait alors sur neuf vignettes « Image à venir »). Trouvé en servant
# la première fois de vraies images officielles depuis la PROD.
_storage = build_storage()
_tcgdex = TcgdexClient()


def get_storage() -> StorageBackend:
    """Dépendance FastAPI : backend de stockage objet (cache des images), remplaçable en test."""
    return _storage


def get_tcgdex_client() -> TcgdexClient:
    """Dépendance FastAPI : client de la source d'images officielle Tcgdex, remplaçable en test."""
    return _tcgdex


@router.get("/img/cards/{card_id}")
async def get_card_image(
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    tcgdex: Annotated[TcgdexClient, Depends(get_tcgdex_client)],
    size: str = Query("high", pattern="^(high|low)$"),
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """Sert l'image officielle d'une carte (route publique), mise en cache dans le stockage
    objet au premier accès. Lève 404 si la carte est inconnue ou sans image, 502 si la source
    officielle est injoignable — jamais un succès vide.

    **Cache immuable** (lot ``j-assets-pipeline``) : pour un couple (carte, taille), le contenu ne
    change jamais — l'image officielle d'une carte éditée est un fait, pas un réglage. On promet
    donc ``immutable`` et un an de validité, et le navigateur ne redemande rien. Avant ce lot cette
    route ne posait **aucun** en-tête : chaque rechargement de page repayait tout le poids d'images
    du plateau, ce qui annulait le budget de poids d'une partie (:mod:`pbm_api.jeu.budget`).
    """
    result = await session.execute(select(Card.image_url).where(Card.id == card_id))
    image_base_url = result.scalar_one_or_none()
    if image_base_url is None:
        raise HTTPException(status_code=404, detail="carte introuvable ou sans image officielle")

    object_key = f"cards/{card_id}/{size}.webp"
    cached = await storage.get(object_key)
    if cached is not None:
        return reponse_image(
            cached, "image/webp", if_none_match=if_none_match, immuable=True
        )

    try:
        image_bytes = await tcgdex.fetch_image_bytes(image_base_url, size)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"image officielle injoignable : {exc}"
        ) from exc

    await storage.put(object_key, image_bytes, "image/webp")
    return reponse_image(image_bytes, "image/webp", if_none_match=if_none_match, immuable=True)


#: Le **seul** message de refus de la route d'apparition. Un identifiant mal formé, un identifiant
#: absent du registre et une découpe absente du stockage rendent tous les trois exactement ce
#: texte : la route est publique, et distinguer « mal formé » de « non publié » donnerait à qui
#: sonde la route de quoi reconstituer la liste des vedettes sans jamais charger une image.
DETAIL_APPARITION_INTROUVABLE = "aucune apparition pour cette carte"


@router.get("/img/apparitions/{tcgdex_id}")
async def get_apparition(
    tcgdex_id: str,
    storage: Annotated[StorageBackend, Depends(get_storage)],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """Sert la découpe du Pokémon d'une carte vedette (route publique) — **sans rien fabriquer**.

    ⛔ **Une découpe absente est un 404, point.** Ni segmentation à la volée, ni proxy vers
    l'illustration officielle. La segmentation coûte un modèle U²-Net et plusieurs secondes de CPU
    (:mod:`pbm_api.jeu.segmentation`) : la déclencher depuis une route d'image, c'est-à-dire depuis
    un plateau qui s'affiche, mettrait à genoux la machine qui sert — le VPS a deux cœurs. Et
    proxyfier l'illustration entière à la place donnerait une carte complète là où l'écran attend
    un sujet détouré sur fond transparent : l'animation afficherait un rectangle, ce qui est pire
    qu'une animation absente. Une carte sans découpe n'a pas d'apparition et son attaque joue
    l'effet de type générique (D9) : la dégradation est prévue, et elle ne laisse aucun trou.

    Les découpes sont produites hors ligne par ``scripts/decouper_apparitions.py`` et publiées par
    le registre :mod:`pbm_api.jeu.vedettes`.

    **Le registre tranche avant le stockage.** Deux gardes, dans cet ordre, et toutes deux avant la
    moindre lecture d'objet : le motif d'identifiant (qui empêche de fabriquer une clé hors du
    préfixe ``jeu/apparitions/``) et l'appartenance au registre (qui empêche de transformer la
    route en sonde d'existence sur le stockage). Lire d'abord et vérifier ensuite aurait rendu le
    temps de réponse bavard.

    **Cache immuable** : comme l'image officielle d'une carte, une découpe publiée ne change pas
    pour un identifiant donné — une reprise de découpe passe par un nouveau déploiement du
    registre. Un an de validité, et le navigateur ne redemande rien.
    """
    if not vedettes.MOTIF_ID.match(tcgdex_id) or tcgdex_id not in vedettes.publiees():
        raise HTTPException(status_code=404, detail=DETAIL_APPARITION_INTROUVABLE)

    decoupe = await storage.get(vedettes.cle_apparition(tcgdex_id))
    if decoupe is None:
        # Le registre annonce une découpe que le stockage n'a pas : une incohérence réelle (objet
        # effacé, déploiement partiel), et on la dit par le même 404 plutôt que de la rattraper.
        raise HTTPException(status_code=404, detail=DETAIL_APPARITION_INTROUVABLE)

    return reponse_image(
        decoupe, TYPE_MIME_APPARITION, if_none_match=if_none_match, immuable=True
    )
