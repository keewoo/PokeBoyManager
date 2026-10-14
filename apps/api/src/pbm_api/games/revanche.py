"""Revanche : relancer la même partie — mêmes joueurs, mêmes decks, sans repasser par la file.

Lot ``j-partie-fin-ui`` (jalon J4). C'est le bouton qui fait revenir : à la fin d'une partie, on ne
veut pas rechoisir un deck, ni refaire la queue, ni réinviter quelqu'un. On veut rejouer.

Ce module ne réinvente **aucune** création de partie : il retrouve les deux sièges de la partie
finie et rappelle les mêmes fonctions que la file d'attente et que l'entraînement
(:func:`pbm_api.games.service.creer_partie` / :func:`~pbm_api.games.service.demarrer_partie`, ou
:func:`pbm_api.games.bot.creer_partie_entrainement`). Tout ce qui est propre à la revanche tient
en quatre décisions, et chacune ferme un trou qu'on aurait sinon.

1. **Le perdant commence.** Le siège 0 joue en premier. Donner la revanche au vainqueur serait lui
   offrir deux fois l'avantage du premier tour ; alors que le tirage au sort de R-4.7 existe pour
   un *lancement*, une revanche a déjà un perdant désigné — autant lui rendre la main. Sans
   vainqueur (égalité R-14.4, clôture pour inactivité), les sièges sont simplement **échangés** :
   l'alternance vaut mieux qu'un tirage qu'on ne saurait pas expliquer.

2. **Les decks sont recontrôlés, un par un.** Entre la partie finie et la revanche, une carte peut
   avoir été vendue, un script retiré, un deck supprimé.
   :func:`~pbm_api.games.lancement.verifier_lancable` est donc rejoué pour **les deux** joueurs :
   propriété, scripts D9, possession. Un deck mort arrête la revanche en nommant ce qui manque
   (D9), jamais une partie fantôme. Et ``game_players.deck_id`` est ``ON DELETE SET NULL`` : un
   siège sans deck est un cas **nommé** (:class:`SiegeSansDeck`), pas un ``None`` qui filerait
   jusqu'à une trace de pile.

3. **Jamais deux parties.** C'est la garde du salon (``partie_active_de``) : un joueur déjà engagé
   ne peut pas en commencer une autre. Mais elle a un angle mort ici, et il arrive tout le temps :
   **les deux** joueurs cliquent « Revanche » en même temps. Le second recevrait un conflit alors
   qu'il veut exactement la partie que le premier vient de créer. Donc avant de refuser, on
   regarde s'il existe déjà une partie en cours **entre ces deux comptes** : si oui, on la rend
   (``deja_creee``), et les deux clics mènent au même plateau. L'idempotence vaut mieux qu'une
   course.

4. **Une revanche d'entraînement reste un entraînement.** Si le siège adverse était tenu par le bot
   ou par l'IA du joueur (DJ7), on repasse par
   :func:`~pbm_api.games.bot.creer_partie_entrainement` avec le même niveau et le même adversaire :
   mêmes gardes, même clé IA exigée, même placement immédiat du bot. On ne fabrique pas un second
   chemin qui ferait *presque* la même chose.

La revanche ne demande **pas** l'accord de l'adversaire : le critère du lot est qu'elle relance
« sans repasser par la file », et une poignée de main serait exactement ce détour. L'adversaire
retrouve la partie à l'endroit où il retrouve toutes les siennes — le salon (``RepriseSection``) la
propose, et le canal temps réel l'y attend.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pbm_api.games.bot import creer_partie_entrainement
from pbm_api.games.errors import GameError, PartieIntrouvable
from pbm_api.games.lancement import verifier_lancable
from pbm_api.games.matchmaking import partie_active_de
from pbm_api.games.service import _game_pour_participant, creer_partie, demarrer_partie
from pbm_api.models import GAME_STATUS_EN_COURS, Game, GamePlayer, User


class RevanchePartieEnCours(GameError):
    """Revanche demandée sur une partie qui n'est pas finie → 409 : on finit celle-ci d'abord."""


class SiegeSansDeck(GameError):
    """Un siège de la partie finie n'a plus de deck (supprimé depuis) → 422, en le nommant.

    ``game_players.deck_id`` est ``ON DELETE SET NULL`` : un deck effacé laisse un siège sans deck.
    On refuse en le disant plutôt que de choisir un deck à la place du joueur.
    """


class JoueurDejaEnPartie(GameError):
    """Un des deux joueurs est déjà dans une **autre** partie en cours → 409, en disant lequel."""


async def _sieges(db: AsyncSession, game_id: uuid.UUID) -> list[GamePlayer]:
    """Les sièges de la partie, dans l'ordre (``seat`` 0 puis 1)."""
    rows = await db.execute(
        select(GamePlayer).where(GamePlayer.game_id == game_id).order_by(GamePlayer.seat)
    )
    return list(rows.scalars().all())


async def partie_active_entre(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> Game | None:
    """Une partie **en cours** où ces deux comptes sont assis ensemble, ou ``None``.

    C'est la clé de l'idempotence de la revanche (décision 3 de l'en-tête) : deux clics
    simultanés doivent mener au même plateau, pas à un conflit. On apparie sur la **paire** de
    joueurs, pas sur l'un d'eux : le compte du bot joue des dizaines de parties en parallèle, et
    chercher « une partie du bot » rendrait n'importe laquelle.
    """
    siege_a, siege_b = aliased(GamePlayer), aliased(GamePlayer)
    return (
        await db.execute(
            select(Game)
            .join(siege_a, siege_a.game_id == Game.id)
            .join(siege_b, siege_b.game_id == Game.id)
            .where(
                Game.status == GAME_STATUS_EN_COURS,
                siege_a.user_id == user_a,
                siege_b.user_id == user_b,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def _ordre_des_sieges(
    sieges: list[GamePlayer], vainqueur_user_id: uuid.UUID | None
) -> tuple[GamePlayer, GamePlayer]:
    """``(siège qui commence, siège qui suit)`` pour la revanche — le perdant d'abord.

    Décision 1 de l'en-tête. Sans vainqueur, les sièges sont échangés par rapport à la partie
    précédente : c'est une alternance, pas un tirage, et elle s'explique en une phrase à l'écran.
    """
    premier, second = sieges[0], sieges[1]
    if vainqueur_user_id is None:
        return second, premier
    if premier.user_id == vainqueur_user_id:
        return second, premier
    return premier, second


async def _pseudo(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Le pseudo d'un compte, pour nommer un refus ; son identifiant si le pseudo manque."""
    nom = (await db.execute(select(User.pseudo).where(User.id == user_id))).scalar_one_or_none()
    return nom or str(user_id)


async def creer_revanche(
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> tuple[Game, bool]:
    """Relance la partie ``game_id`` entre les mêmes joueurs et les mêmes decks.

    Renvoie ``(partie, deja_creee)`` : ``deja_creee`` est vrai quand une partie en cours existait
    déjà entre ces deux comptes — on la rend telle quelle au lieu d'en créer une seconde
    (idempotence, décision 3 de l'en-tête).

    Lève :class:`~pbm_api.games.errors.PartieIntrouvable` (404) si l'appelant ne joue pas la partie
    finie, :class:`RevanchePartieEnCours` (409) si elle n'est pas finie, :class:`SiegeSansDeck`
    (422) si un deck a disparu, :class:`JoueurDejaEnPartie` (409) si l'un des deux est engagé
    ailleurs, et ce que lève :func:`~pbm_api.games.lancement.verifier_lancable`
    (``DeckIntrouvable`` 404 / ``DeckInjouable`` 422, cartes nommées).
    """
    game = await _game_pour_participant(db, game_id, user_id)
    if game.status == GAME_STATUS_EN_COURS:
        raise RevanchePartieEnCours(
            f"Partie {game_id} encore en cours : terminez-la avant de demander une revanche."
        )

    sieges = await _sieges(db, game_id)
    if len(sieges) != 2:
        # Une partie a toujours deux sièges (unicité ``(game_id, seat)``). Zéro ou un, c'est une
        # donnée abîmée : on le dit, on ne complète pas le siège manquant au hasard.
        raise PartieIntrouvable(f"Partie {game_id} sans ses deux sièges : revanche impossible.")
    for siege in sieges:
        if siege.deck_id is None:
            nom = await _pseudo(db, siege.user_id)
            raise SiegeSansDeck(
                f"Le deck joué par {nom} n'existe plus : choisissez un deck depuis le salon pour "
                "relancer une partie."
            )

    # Déjà relancée (par l'adversaire, ou par un second clic) ? On rend cette partie-là.
    deja = await partie_active_entre(db, sieges[0].user_id, sieges[1].user_id)
    if deja is not None:
        return deja, True

    # Entraînement (bot ou IA du joueur, DJ7) : on repasse par le chemin de l'entraînement, avec le
    # même niveau et le même adversaire. L'humain est le siège qui n'est pas celui du bot.
    siege_auto = next(
        (s for s in sieges if s.bot_niveau is not None or s.adversaire_ia), None
    )
    if siege_auto is not None:
        humain = next(s for s in sieges if s is not siege_auto)
        if await partie_active_de(db, humain.user_id) is not None:
            raise JoueurDejaEnPartie(
                "Vous êtes déjà dans une partie en cours : terminez-la avant la revanche."
            )
        partie = await creer_partie_entrainement(
            db,
            user_id=humain.user_id,
            deck_id=humain.deck_id,
            niveau=siege_auto.bot_niveau,
            adversaire="ia" if siege_auto.adversaire_ia else "bot",
            maintenant=maintenant,
        )
        return partie, False

    # Partie entre deux comptes : chacun doit être libre, et chaque deck encore jouable.
    for siege in sieges:
        if await partie_active_de(db, siege.user_id) is not None:
            nom = await _pseudo(db, siege.user_id)
            raise JoueurDejaEnPartie(
                f"{nom} est déjà dans une partie en cours : la revanche attendra la fin de "
                "celle-ci."
            )
        await verifier_lancable(db, siege.user_id, siege.deck_id)

    premier, second = _ordre_des_sieges(sieges, game.vainqueur_user_id)
    partie = await creer_partie(
        db,
        joueur_a=(premier.user_id, premier.deck_id),
        joueur_b=(second.user_id, second.deck_id),
        maintenant=maintenant,
    )
    await demarrer_partie(db, partie, maintenant)
    return partie, False


__all__ = [
    "JoueurDejaEnPartie",
    "RevanchePartieEnCours",
    "SiegeSansDeck",
    "creer_revanche",
    "partie_active_entre",
]
