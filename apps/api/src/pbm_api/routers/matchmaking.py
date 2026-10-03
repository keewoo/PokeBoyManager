"""Routes de la recherche d'adversaire : file d'attente, présence, jouabilité du deck.

Entrer dans la file avec un deck choisi, consulter son attente, annuler, voir la présence des
comptes invités, et — pour le salon (lot `j-salon-partie`) — **savoir si un deck est jouable avant
d'entrer en file**. **Toutes** les routes sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans droit d'accès au jeu
reçoit **404** partout, comme pour un objet d'autrui —
le jeu n'existe pas pour lui. Les écritures (entrer, annuler) exigent le jeton CSRF, comme toute
mutation utilisateur.

Le serveur fait autorité : le client propose un `deck_id`, le serveur vérifie (possession, légalité,
scripts) et refuse en nommant ce qui manque. L'appariement lui-même, et son verrou anti-course,
vivent dans :mod:`pbm_api.games.matchmaking` — le routeur ne fait que traduire exceptions et
résultats en réponses HTTP.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.games import bot, matchmaking
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable, verifier_deck
from pbm_api.games.matchmaking import Apparie, DejaEnPartie, EnAttente
from pbm_api.models import User
from pbm_api.security.rate_limit import get_redis

router = APIRouter(prefix="/matchmaking", tags=["matchmaking"])

NOT_FOUND_MESSAGE = "Ressource introuvable."


def get_redis_client() -> Redis:
    """Un client Redis par requête (comme `pbm_api.security.rate_limit.get_redis`).

    Exposé en dépendance FastAPI pour que les tests puissent le surcharger si besoin ; en pratique
    il renvoie le même client que le reste de l'app.
    """
    return get_redis()


# --- Schémas d'entrée / sortie ----------------------------------------------


class EntrerFileIn(BaseModel):
    """Entrée dans la file : le deck avec lequel le joueur veut jouer."""

    deck_id: uuid.UUID


class RefusDeckOut(BaseModel):
    """Une carte (ou le deck) refusé à l'entrée, avec la raison — jamais un refus muet."""

    carte: str
    raison: str


class JouabiliteOut(BaseModel):
    """Jouabilité d'un deck **avant** l'entrée en file — de quoi l'afficher au choix du deck.

    `jouable` vrai = l'appariement aboutira (chaque carte se compile pour le moteur, D9) ; sinon
    `refus` nomme chaque carte en cause et sa raison, exactement comme le refus à l'entrée. Le
    salon (lot `j-salon-partie`, critère « le choix du deck affiche sa jouabilité avant l'entrée en
    file ») lit ce verdict pour ne proposer d'entrer qu'avec un deck réellement jouable.
    """

    deck_id: uuid.UUID
    jouable: bool
    refus: list[RefusDeckOut] = Field(default_factory=list)


class FileOut(BaseModel):
    """État de la file pour le joueur. `status` discrimine les deux cas vivants.

    * `apparie` — une partie a été créée : `game_id` et `adversaire_user_id` sont renseignés ;
    * `en_attente` — personne encore : `position`, `joueurs_en_file`, `attente_secondes` ;
    * `absent` — le joueur n'est pas (ou plus) dans la file (seulement en consultation GET).
    """

    status: str
    game_id: uuid.UUID | None = None
    adversaire_user_id: uuid.UUID | None = None
    position: int | None = None
    joueurs_en_file: int | None = None
    attente_secondes: float | None = None


class PresenceOut(BaseModel):
    """Présence des comptes invités, et options de repli s'il n'y a personne à affronter."""

    en_ligne: int
    en_partie: int
    en_file: int
    autres_disponibles: int = Field(
        description="Joueurs en ligne, hors partie, autres que soi : les adversaires possibles."
    )
    options: list[str]


class EntrainementIn(BaseModel):
    """Lancer une partie d'entraînement : le deck du joueur et le niveau du bot (DJ7)."""

    deck_id: uuid.UUID
    niveau: str = "correct"


class EntrainementOut(BaseModel):
    """La partie d'entraînement créée : son identifiant, le niveau choisi, le délai d'animation.

    ``bot_delai_ms`` est le temps de réflexion **visible** du bot (DJ7, « rester lisible ») : le
    serveur ne temporise pas (il sert d'autres joueurs), l'écran révèle les coups à ce rythme.
    """

    game_id: uuid.UUID
    niveau: str
    bot_delai_ms: int


def _reponse(resultat: Apparie | EnAttente) -> FileOut:
    """Traduit le résultat du service en réponse HTTP (apparié ou en attente)."""
    if isinstance(resultat, Apparie):
        return FileOut(
            status="apparie",
            game_id=resultat.game_id,
            adversaire_user_id=resultat.adversaire_user_id,
        )
    return FileOut(
        status="en_attente",
        position=resultat.position,
        joueurs_en_file=resultat.joueurs_en_file,
        attente_secondes=resultat.attente_secondes,
    )


# --- Routes -----------------------------------------------------------------


@router.post("/queue", response_model=FileOut)
async def entrer_file(
    body: EntrerFileIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """Entre dans la file avec un deck et tente un appariement immédiat.

    404 si le deck n'est pas celui du joueur (pas de fuite) ; 422 si le deck n'est pas jouable, avec
    les cartes en cause ; 409 si le joueur est déjà dans une partie. Sinon : apparié (partie créée)
    ou en attente.
    """
    try:
        resultat = await matchmaking.rejoindre(
            db, redis, user_id=current_user.id, deck_id=body.deck_id
        )
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        # 422 avec le détail nommé : le client affiche exactement ce qui manque (critère du lot).
        raise HTTPException(
            422,
            detail={
                "message": "Deck non jouable.",
                "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.refus],
            },
        ) from exc
    except DejaEnPartie as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _reponse(resultat)


@router.get("/queue", response_model=FileOut)
async def consulter_file(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """L'état réel de la recherche du joueur : apparié, en attente (rang, temps), ou pas en file."""
    game_id = await matchmaking.partie_active_de(db, current_user.id)
    if game_id is not None:
        return FileOut(status="apparie", game_id=game_id)
    attente = await matchmaking.statut_attente(redis, current_user.id)
    if attente is None:
        return FileOut(status="absent")
    return _reponse(attente)


@router.delete("/queue", response_model=FileOut)
async def quitter_file(
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """Annule la recherche : retire le joueur de la file. Idempotent (absent → `absent`)."""
    await matchmaking.quitter(redis, current_user.id)
    return FileOut(status="absent")


@router.get("/decks/{deck_id}/jouabilite", response_model=JouabiliteOut)
async def jouabilite_deck(
    deck_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
) -> JouabiliteOut:
    """Dit si un deck est jouable **sans** entrer dans la file — pour l'afficher au choix du deck.

    Même contrôle exact que l'entrée en file (:func:`~pbm_api.games.entry.verifier_deck`) : 404 si
    le deck n'est pas celui du joueur (pas de fuite d'existence, comme un deck d'autrui) ; sinon le
    verdict, et en cas de refus la liste des cartes en cause avec leur raison (D9 — jamais un refus
    muet). Lecture seule, pas de CSRF : elle n'écrit rien, elle éclaire le choix.
    """
    try:
        await verifier_deck(db, current_user.id, deck_id)
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        return JouabiliteOut(
            deck_id=deck_id,
            jouable=False,
            refus=[RefusDeckOut(carte=nom, raison=raison) for nom, raison in exc.refus],
        )
    return JouabiliteOut(deck_id=deck_id, jouable=True, refus=[])


@router.get("/presence", response_model=PresenceOut)
async def presence(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> PresenceOut:
    """La présence des comptes invités, et les options de repli s'il n'y a personne à affronter."""
    p = await matchmaking.presence(db, redis, current_user.id)
    return PresenceOut(
        en_ligne=p.en_ligne,
        en_partie=p.en_partie,
        en_file=p.en_file,
        autres_disponibles=p.autres_disponibles,
        options=p.options,
    )


@router.post("/entrainement", response_model=EntrainementOut, status_code=status.HTTP_201_CREATED)
async def entrainement(
    body: EntrainementIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> EntrainementOut:
    """Lance une partie d'entraînement contre le bot — en un clic, sans file ni invitation (DJ7).

    C'est l'entrée « S'entraîner » du salon (lot `j-salon-partie`) : le repli quand personne n'est
    en ligne (`presence` propose alors l'option ``entrainement_bot``). 404 si le deck n'est pas
    celui du joueur (pas de fuite) ; 422 si le deck n'est pas jouable (cartes nommées) ou si le
    niveau est inconnu ; 409 si le joueur est déjà dans une partie. Sinon la partie est créée, le
    bot a placé son camp, et le joueur n'a plus qu'à ouvrir ``/games/{game_id}``.
    """
    if await matchmaking.partie_active_de(db, current_user.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Vous êtes déjà dans une partie en cours : terminez-la avant d'en lancer une autre.",
        )
    try:
        game = await bot.creer_partie_entrainement(
            db, user_id=current_user.id, deck_id=body.deck_id, niveau=body.niveau
        )
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        raise HTTPException(
            422,
            detail={
                "message": "Deck non jouable.",
                "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.refus],
            },
        ) from exc
    except bot.NiveauBotInconnu as exc:
        raise HTTPException(422, str(exc)) from exc
    return EntrainementOut(
        game_id=game.id, niveau=body.niveau, bot_delai_ms=bot.DELAI_REFLEXION_MS
    )
