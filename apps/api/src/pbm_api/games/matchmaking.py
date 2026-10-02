"""File d'attente privée et appariement (lot `j-file-attente`).

« Je veux jouer » doit aboutir à une partie en quelques secondes, ou à une réponse claire
(« personne en ligne »). Ce module tient la **file**, la **présence** et le **verrou
d'appariement**. Il vit dans `apps/api` car il lit la base et parle à Redis ; le moteur `pbm_game`
reste pur.

**Le risque nommé du lot est une condition de course** : deux joueurs appariés chacun avec un
troisième. La parade est un **verrou atomique**, pas une relecture. Toute la section critique
d'appariement (choisir deux joueurs, créer la partie, les retirer de la file) s'exécute sous un
verrou Redis (`SET NX EX`) : un seul appariement tourne à la fois, donc un joueur retiré de la file
sous verrou ne peut être apparié qu'une seule fois. En défense supplémentaire, avant chaque
appariement on revérifie en base qu'aucun des deux candidats n'est **déjà** dans une partie active
— un joueur ne peut jamais se retrouver dans deux parties.

Structures Redis (toutes préfixées par :data:`~pbm_api.config.Settings.redis_prefix` + ``mm:``) :

* ``mm:queue`` — ensemble trié (ZSET), score = horodatage d'arrivée, membre = `user_id` hex.
  L'ordre d'arrivée (FIFO) est l'ordre des scores. La proximité de niveau viendra **quand un
  classement de joueur existera** — il n'en existe aucun aujourd'hui (le module `ranking` classe des
  cartes, pas des joueurs), donc l'appariement est strictement FIFO, sans approximation (D9).
* ``mm:deck:<user>`` — le deck choisi à l'entrée, avec expiration (une entrée de file ne survit pas
  éternellement à un onglet laissé ouvert).
* ``mm:online`` — ensemble trié de présence, score = instant d'expiration du battement de cœur.
  Un joueur « en ligne » est un compte invité dont le dernier battement n'a pas expiré.
* ``mm:lock`` — le verrou d'appariement (un seul détenteur à la fois).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.games.entry import verifier_deck
from pbm_api.games.errors import CartesNonJouables, GameError
from pbm_api.games.service import creer_partie
from pbm_api.models import Game, GamePlayer
from pbm_api.models.games import GAME_STATUS_EN_COURS

logger = logging.getLogger(__name__)

#: Durée de validité d'un battement de cœur de présence : au-delà, le joueur est hors ligne. Chaque
#: passage par la file ou la présence le repousse.
PRESENCE_TTL_SECONDES = 30

#: Durée de vie du verrou d'appariement. Volontairement courte : la section critique est rapide (au
#: plus quelques créations de partie), et un détenteur mort ne doit pas bloquer la file longtemps.
#: `EX` garantit la libération même en cas de crash du process entre `acquérir` et `libérer`.
LOCK_TTL_SECONDES = 10

#: Une entrée de file (le deck choisi) expire après ce délai : un joueur qui a laissé un onglet
#: ouvert une heure n'est plus « en attente ». Son entrée dans la file sera écartée à l'appariement
#: (deck introuvable), jamais appariée en silence sur un deck périmé.
DECK_TTL_SECONDES = 3600


def _k(suffixe: str) -> str:
    """Clé Redis préfixée par l'espace de noms de l'application, puis ``mm:``."""
    return f"{settings.redis_prefix}mm:{suffixe}"


_QUEUE = _k("queue")
_ONLINE = _k("online")
_LOCK = _k("lock")


def _deck_key(user_hex: str) -> str:
    return _k(f"deck:{user_hex}")


class DejaEnPartie(GameError):
    """Le joueur est déjà dans une partie en cours : il ne peut pas entrer dans la file (→ 409).

    Protection contre l'entrée simultanée dans deux parties, côté entrée. La garde définitive est
    sous le verrou d'appariement (on revérifie en base), mais refuser tôt évite une entrée inutile.
    """


@dataclass
class Apparie:
    """Résultat d'une entrée en file quand un adversaire a été trouvé : la partie est créée."""

    game_id: uuid.UUID
    adversaire_user_id: uuid.UUID


@dataclass
class EnAttente:
    """Résultat d'une entrée en file quand personne n'est encore disponible.

    `position` est le rang dans la file (1 = prochain à être apparié). `joueurs_en_file` est le
    nombre total de joueurs en attente (y compris soi). `attente_secondes` est le temps écoulé
    depuis l'entrée. L'écran affiche l'état réel (critère d'acceptation du lot).
    """

    position: int
    joueurs_en_file: int
    attente_secondes: float


@dataclass
class Presence:
    """Photographie de la présence des comptes invités, à un instant donné.

    `en_ligne` = comptes invités dont le battement de cœur est frais ; `en_partie` = ceux d'entre
    eux qui jouent une partie en cours ; `en_file` = ceux en attente d'appariement ;
    `autres_disponibles` = joueurs en ligne, hors partie, **autres que soi**. Quand ce dernier est
    nul, `options` propose les chemins de repli (invitation directe, entraînement contre le bot) —
    ces chemins sont les lots `j-invitations` et le bot, pas encore implémentés : on nomme l'option,
    on ne l'approxime pas (D9).
    """

    en_ligne: int
    en_partie: int
    en_file: int
    autres_disponibles: int
    options: list[str] = field(default_factory=list)


async def _maintenant(fourni: float | None) -> float:
    """Horodatage courant en secondes, ou celui fourni par un test (déterminisme)."""
    return fourni if fourni is not None else time.time()


async def partie_active_de(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    """L'id d'une partie **en cours** à laquelle le joueur participe, ou ``None``.

    C'est la garde contre « deux parties » : un joueur déjà engagé n'entre pas dans la file, et
    n'est jamais choisi pour un appariement (revérifié sous le verrou). Public : le routeur s'en
    sert pour répondre « vous avez déjà une partie » à une consultation de la file.
    """
    row = (
        await db.execute(
            select(Game.id)
            .join(GamePlayer, GamePlayer.game_id == Game.id)
            .where(GamePlayer.user_id == user_id, Game.status == GAME_STATUS_EN_COURS)
            .limit(1)
        )
    ).first()
    return row[0] if row else None


async def _battre_coeur(redis: Redis, user_id: uuid.UUID, maintenant: float) -> None:
    """Marque le joueur en ligne jusqu'à ``maintenant + PRESENCE_TTL_SECONDES``."""
    await redis.zadd(_ONLINE, {user_id.hex: maintenant + PRESENCE_TTL_SECONDES})


async def _en_ligne(redis: Redis, maintenant: float) -> set[uuid.UUID]:
    """Les comptes en ligne (battement non expiré), après purge des battements périmés."""
    await redis.zremrangebyscore(_ONLINE, "-inf", maintenant)
    membres = await redis.zrange(_ONLINE, 0, -1)
    return {uuid.UUID(h) for h in membres}


async def rejoindre(
    db: AsyncSession,
    redis: Redis,
    *,
    user_id: uuid.UUID,
    deck_id: uuid.UUID,
    maintenant: float | None = None,
) -> Apparie | EnAttente:
    """Entre dans la file avec un deck vérifié, puis tente un appariement immédiat.

    Déroulé : refuse si le joueur est déjà en partie (:class:`DejaEnPartie`) ; vérifie le deck
    (:func:`~pbm_api.games.entry.verifier_deck` lève si une carte manque ou si le deck n'est pas le
    sien) ; inscrit le joueur dans la file (sans écraser son horodatage d'arrivée s'il y était déjà,
    pour un FIFO stable) ; bat le cœur de présence ; puis déclenche un appariement. Renvoie
    :class:`Apparie` si une partie a été créée pour ce joueur, sinon :class:`EnAttente`.
    """
    maintenant = await _maintenant(maintenant)

    if await partie_active_de(db, user_id) is not None:
        raise DejaEnPartie(
            "Vous êtes déjà dans une partie en cours : terminez-la avant d'en chercher une autre."
        )

    # Lève DeckIntrouvable (→404) ou DeckInjouable (→422, cartes nommées) — avant toute inscription.
    await verifier_deck(db, user_id, deck_id)

    # `nx=True` : ne pas réécrire le score si le joueur est déjà en file (garde son rang d'arrivée).
    await redis.zadd(_QUEUE, {user_id.hex: maintenant}, nx=True)
    await redis.set(_deck_key(user_id.hex), str(deck_id), ex=DECK_TTL_SECONDES)
    await _battre_coeur(redis, user_id, maintenant)

    parties = await apparier(db, redis, maintenant=maintenant)
    for game, (ua, ub) in parties:
        if user_id in (ua, ub):
            adversaire = ub if ua == user_id else ua
            return Apparie(game_id=game.id, adversaire_user_id=adversaire)

    return await _etat_attente(redis, user_id, maintenant)


async def quitter(redis: Redis, user_id: uuid.UUID) -> bool:
    """Retire le joueur de la file (annulation). Renvoie ``True`` s'il y était.

    Ne touche pas à la présence : annuler sa recherche ne veut pas dire quitter le jeu.
    """
    retire = await redis.zrem(_QUEUE, user_id.hex)
    await redis.delete(_deck_key(user_id.hex))
    return bool(retire)


async def apparier(
    db: AsyncSession, redis: Redis, *, maintenant: float | None = None
) -> list[tuple[Game, tuple[uuid.UUID, uuid.UUID]]]:
    """Apparie les joueurs en attente, deux par deux, **sous verrou** — le cœur anti-course du lot.

    Acquiert le verrou Redis (`SET NX EX`). S'il est déjà pris, un autre appariement est en cours :
    on renonce sans forcer (il traitera la file ; notre entrée y restera et sera prise au tour
    suivant). Sous le verrou, tant qu'il reste au moins deux joueurs en file :

    1. on prend les **deux premiers** (ordre d'arrivée) ;
    2. on écarte (sans apparier) tout joueur déjà en partie active — garde « jamais deux parties » —
       ou dont le deck a expiré de la file ;
    3. on crée la partie ; si un deck est devenu injouable entre-temps, on retire les deux candidats
       et on continue (jamais un appariement silencieux sur un deck cassé, jamais un `pass` muet) ;
    4. on retire les deux appariés de la file.

    Renvoie la liste des `(partie, (user_a, user_b))` créés pendant ce passage.
    """
    maintenant = await _maintenant(maintenant)
    jeton = uuid.uuid4().hex
    if not await redis.set(_LOCK, jeton, nx=True, ex=LOCK_TTL_SECONDES):
        return []

    cree: list[tuple[Game, tuple[uuid.UUID, uuid.UUID]]] = []
    try:
        while True:
            paire = await redis.zrange(_QUEUE, 0, 1)
            if len(paire) < 2:
                break
            ua_hex, ub_hex = paire[0], paire[1]
            ua, ub = uuid.UUID(ua_hex), uuid.UUID(ub_hex)

            # Garde « jamais deux parties » : un candidat déjà engagé est retiré, pas apparié.
            a_retirer = [
                hx
                for hx, uid in ((ua_hex, ua), (ub_hex, ub))
                if await partie_active_de(db, uid) is not None
            ]
            if a_retirer:
                await redis.zrem(_QUEUE, *a_retirer)
                continue

            deck_a = await redis.get(_deck_key(ua_hex))
            deck_b = await redis.get(_deck_key(ub_hex))
            manquants = [hx for hx, d in ((ua_hex, deck_a), (ub_hex, deck_b)) if d is None]
            if manquants:
                # Deck expiré : l'entrée n'est plus valable. On l'écarte — explicitement, pas en
                # silence — et le joueur devra re-entrer (son deck sera revérifié).
                logger.info(
                    "appariement : entrée de file sans deck (expiré) écartée : %s", manquants
                )
                await redis.zrem(_QUEUE, *manquants)
                continue

            try:
                game = await creer_partie(
                    db,
                    joueur_a=(ua, uuid.UUID(deck_a)),
                    joueur_b=(ub, uuid.UUID(deck_b)),
                    maintenant=None,
                )
            except CartesNonJouables as exc:
                # Un deck vérifié à l'entrée est devenu injouable (catalogue modifié entre-temps).
                # On retire les deux candidats en le disant (jamais un repli muet) ; à leur
                # prochaine entrée, `verifier_deck` les refusera proprement.
                logger.warning(
                    "appariement : deck devenu injouable entre l'entrée et la création "
                    "(joueurs %s / %s) : %s",
                    ua,
                    ub,
                    exc,
                )
                await redis.zrem(_QUEUE, ua_hex, ub_hex)
                continue

            await redis.zrem(_QUEUE, ua_hex, ub_hex)
            await redis.delete(_deck_key(ua_hex), _deck_key(ub_hex))
            cree.append((game, (ua, ub)))
    finally:
        await _liberer_verrou(redis, jeton)

    return cree


#: Script Lua de libération atomique : ne supprime le verrou que si c'est toujours le nôtre
#: (compare-and-delete). Sans ça, un verrou expiré puis repris par un autre appariement pourrait
#: être effacé par le nôtre — on relâcherait le verrou d'autrui.
_LIBERER_VERROU = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


async def _liberer_verrou(redis: Redis, jeton: str) -> None:
    """Libère le verrou d'appariement, uniquement s'il porte encore notre jeton."""
    await redis.eval(_LIBERER_VERROU, 1, _LOCK, jeton)


async def _etat_attente(redis: Redis, user_id: uuid.UUID, maintenant: float) -> EnAttente:
    """Construit l'état d'attente réel : rang dans la file, taille de la file, temps écoulé."""
    rang = await redis.zrank(_QUEUE, user_id.hex)
    taille = await redis.zcard(_QUEUE)
    arrivee = await redis.zscore(_QUEUE, user_id.hex)
    attente = max(0.0, maintenant - arrivee) if arrivee is not None else 0.0
    return EnAttente(
        position=(rang + 1) if rang is not None else 0,
        joueurs_en_file=taille,
        attente_secondes=attente,
    )


async def statut_attente(
    redis: Redis, user_id: uuid.UUID, *, maintenant: float | None = None
) -> EnAttente | None:
    """L'état d'attente du joueur s'il est dans la file, sinon ``None`` (il n'y est pas).

    Pour une consultation (GET) : ne modifie pas la file. Le routeur combine ce résultat avec
    :func:`partie_active_de` pour répondre « apparié / en attente / pas en file ».
    """
    maintenant = await _maintenant(maintenant)
    if await redis.zrank(_QUEUE, user_id.hex) is None:
        return None
    return await _etat_attente(redis, user_id, maintenant)


async def presence(
    db: AsyncSession, redis: Redis, user_id: uuid.UUID, *, maintenant: float | None = None
) -> Presence:
    """Photographie de la présence, et bat le cœur du demandeur (consulter, c'est être en ligne).

    Compte les comptes invités en ligne, ceux en partie, ceux en file, et les **autres** joueurs
    disponibles (en ligne, hors partie, hors soi). Si aucun autre n'est disponible, propose les
    options de repli (`j-invitations`, entraînement contre le bot).
    """
    maintenant = await _maintenant(maintenant)
    await _battre_coeur(redis, user_id, maintenant)

    en_ligne = await _en_ligne(redis, maintenant)
    en_partie: set[uuid.UUID] = set()
    if en_ligne:
        rows = await db.execute(
            select(distinct(GamePlayer.user_id))
            .join(Game, Game.id == GamePlayer.game_id)
            .where(
                GamePlayer.user_id.in_(en_ligne),
                Game.status == GAME_STATUS_EN_COURS,
            )
        )
        en_partie = {r[0] for r in rows.all()}

    en_file = await redis.zcard(_QUEUE)
    disponibles = (en_ligne - en_partie) - {user_id}
    options = ["invitation", "entrainement_bot"] if not disponibles else []
    return Presence(
        en_ligne=len(en_ligne),
        en_partie=len(en_partie),
        en_file=en_file,
        autres_disponibles=len(disponibles),
        options=options,
    )
