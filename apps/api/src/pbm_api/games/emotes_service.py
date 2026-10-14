"""Mécanique des emotes (lot ``j-echanges-emotes``) : réglage en base, débit en mémoire, diffusion.

La **décision** (le catalogue fermé, la règle de débit, les défauts) est pure et vit dans
:mod:`pbm_api.games.emotes`. Ce module en est l'adaptateur : il lit la base (le réglage « je reçois
les emotes »), tient le **compteur de débit en mémoire** et publie au bus de diffusion du canal
temps réel.

**Rien n'est persisté d'une emote.** Ni le code envoyé, ni l'instant, ni le destinataire :

* le code traverse le :class:`~pbm_api.games.temps_reel.Hub` et s'arrête aux files des abonnés
  connectés — il n'entre **jamais** dans le journal numéroté de la partie (une emote n'est pas un
  coup : elle ne change pas l'état, elle n'est pas rejouable, et un replay ne la rediffusera pas) ;
* le compteur de débit vit dans :data:`LIMITEUR`, en mémoire du process, et il est **oublié** quand
  la partie n'a plus d'abonné (:meth:`LimiteurEmotes.oublier`) — donc au plus tard quand les deux
  joueurs ont fermé leur onglet.

Ce qui se garde en base, c'est le **choix du joueur** (couper les emotes), et lui seul : un réglage
qu'il faudrait reposer à chaque partie n'est pas un réglage.

⚠️ **Portée du débit : un process.** Le limiteur partage exactement la portée du hub, qui est
documentée comme « en mémoire du process ». Ce n'est pas un trou : les emotes d'un joueur passent
toutes par le process qui tient *sa* WebSocket, donc son débit est bien compté pour la connexion
qui l'émet. Une reconnexion sur un autre process repartirait sur un budget neuf — borne connue,
assumée pour un jeu privé entre comptes invités (D11), et à revoir le jour où l'API tournera en
plusieurs réplicas.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games.emotes import (
    CODES,
    ERREUR_COUPEES,
    ERREUR_INCONNUE,
    ERREUR_TROP_RAPIDE,
    FENETRE_SECONDES,
    ReglagesEmotes,
    debit_autorise,
    message_trop_rapide,
)
from pbm_api.models import JeuEmoteReglages

logger = logging.getLogger(__name__)


# --- Réglage du compte ---------------------------------------------------------------------------


async def charger_reglages(db: AsyncSession, user_id: uuid.UUID) -> ReglagesEmotes:
    """Le réglage d'emotes d'un compte, ou les **défauts** s'il n'y a jamais touché.

    C'est ici que « pas de ligne » devient « les défauts », une fois pour toutes — aucun appelant
    n'a à connaître cette convention (même choix que :mod:`pbm_api.jeu.rendu_service`).
    """
    ligne = await db.get(JeuEmoteReglages, user_id)
    if ligne is None:
        return ReglagesEmotes()
    return ReglagesEmotes(recevoir_emotes=ligne.recevoir_emotes)


async def enregistrer_reglages(
    db: AsyncSession, user_id: uuid.UUID, *, recevoir_emotes: bool | None
) -> ReglagesEmotes:
    """Écrit le réglage (création à la première modification) et rend l'état complet qui en résulte.

    ``None`` laisse le champ inchangé : c'est ce qui rend la route ``PATCH`` partielle, donc sûre
    quand deux onglets règlent deux choses différentes. Ne **commite pas** — l'appelant décide.
    """
    if recevoir_emotes is None:
        return await charger_reglages(db, user_id)
    ligne = await db.get(JeuEmoteReglages, user_id)
    if ligne is None:
        ligne = JeuEmoteReglages(user_id=user_id, recevoir_emotes=recevoir_emotes)
        db.add(ligne)
    else:
        ligne.recevoir_emotes = recevoir_emotes
    await db.flush()
    return ReglagesEmotes(recevoir_emotes=ligne.recevoir_emotes)


async def comptes_ayant_coupe(
    db: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> frozenset[uuid.UUID]:
    """Parmi ``user_ids``, ceux qui ont **coupé** les emotes — en une requête.

    Les comptes sans ligne de réglage suivent le défaut (ils reçoivent) : ils ne sont donc jamais
    dans l'ensemble renvoyé. Lu à **chaque** emote et non mis en cache : c'est ce qui rend la
    coupure *immédiate* (critère du lot) — basculer l'interrupteur agit sur l'emote suivante, sans
    rouvrir la partie ni rafraîchir la page.
    """
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        return frozenset()
    lignes = (
        await db.execute(
            select(JeuEmoteReglages.user_id).where(
                JeuEmoteReglages.user_id.in_(ids),
                JeuEmoteReglages.recevoir_emotes.is_(False),
            )
        )
    ).scalars()
    return frozenset(lignes)


# --- Débit, en mémoire du process ----------------------------------------------------------------


class LimiteurEmotes:
    """Compteur de débit des emotes, par (partie, joueur), **en mémoire** et jamais persisté.

    On ne garde que les instants d'envoi encore utiles (ceux de la fenêtre glissante) : la mémoire
    occupée par une partie est donc bornée par
    :data:`~pbm_api.games.emotes.MAX_PAR_FENETRE` flottants par joueur, et :meth:`oublier` efface
    une partie entière quand plus personne ne l'écoute.
    """

    def __init__(self) -> None:
        self._envois: dict[uuid.UUID, dict[uuid.UUID, list[float]]] = {}

    def autoriser(
        self, game_id: uuid.UUID, user_id: uuid.UUID, maintenant: float
    ) -> tuple[bool, float]:
        """Enregistre une emote si le débit le permet ; renvoie ``(autorise, attente)``.

        Un refus **n'enregistre rien** : spammer ne repousse donc pas indéfiniment sa propre
        autorisation (un compteur qui punirait les tentatives finirait par bloquer un joueur qui
        clique une fois de trop).
        """
        par_joueur = self._envois.setdefault(game_id, {})
        envois = par_joueur.setdefault(user_id, [])
        autorise, attente = debit_autorise(envois, maintenant)
        if not autorise:
            return False, attente
        envois.append(maintenant)
        # On ne garde que la fenêtre utile : au-delà, ces instants ne pèsent plus sur aucune
        # décision, et les garder serait une fuite mémoire lente sur une longue partie.
        par_joueur[user_id] = [t for t in envois if t > maintenant - FENETRE_SECONDES]
        return True, 0.0

    def oublier(self, game_id: uuid.UUID) -> None:
        """Efface tout ce que le limiteur sait d'une partie — « rien au-delà de la partie »."""
        self._envois.pop(game_id, None)

    def connait(self, game_id: uuid.UUID) -> bool:
        """Le limiteur garde-t-il encore une trace de cette partie ? (supervision et tests)."""
        return game_id in self._envois


#: Limiteur partagé par l'application (un process = un limiteur, comme le hub). Les tests en
#: fabriquent un local.
LIMITEUR = LimiteurEmotes()


# --- Diffusion -----------------------------------------------------------------------------------


class BusEmotes(Protocol):
    """Ce que la diffusion attend d'un bus : qui écoute, et comment lui déposer une emote.

    Le :class:`~pbm_api.games.temps_reel.Hub` le satisfait. Déclaré en Protocol **plutôt
    qu'importé** pour deux raisons : aucune dépendance circulaire (c'est ``temps_reel`` qui appelle
    ce module), et un bus de test en dix lignes suffit à exercer toute la logique.
    """

    def user_ids(self, game_id: uuid.UUID) -> frozenset[uuid.UUID]:
        """Les comptes actuellement abonnés à cette partie."""
        ...

    def publier_emote(
        self,
        game_id: uuid.UUID,
        *,
        code: str,
        de_user_id: uuid.UUID,
        coupes: frozenset[uuid.UUID],
    ) -> int:
        """Dépose l'emote chez les abonnés qui ne l'ont pas coupée ; renvoie le nombre servis."""
        ...


async def diffuser_emote(
    bus: BusEmotes,
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    de_user_id: uuid.UUID,
    code: object,
    maintenant: float,
    limiteur: LimiteurEmotes | None = None,
) -> dict | None:
    """Valide puis diffuse une emote. Renvoie ``None`` si elle est partie, sinon l'erreur à rendre.

    Quatre refus, dans cet ordre — et chacun **dit pourquoi** (jamais un refus muet) :

    1. **code hors catalogue** → :data:`~pbm_api.games.emotes.ERREUR_INCONNUE`. On ne replie pas sur
       une emote par défaut : afficher à l'adversaire une phrase que personne n'a choisie serait
       exactement le contraire de DJ10 ;
    2. **l'émetteur a coupé les emotes** → :data:`~pbm_api.games.emotes.ERREUR_COUPEES`. L'écran
       masque déjà la palette, mais le serveur fait autorité : un client bricolé ne contourne pas
       un réglage de confidentialité ;
    3. **débit dépassé** → :data:`~pbm_api.games.emotes.ERREUR_TROP_RAPIDE`, avec le délai ;
    4. (pas un refus) **tous les destinataires ont coupé** : l'emote est acceptée et simplement
       délivrée à personne. On ne le dit pas à l'émetteur — annoncer « l'adversaire t'a coupé »
       transformerait un réglage de confort en information sociale, et donc en reproche.

    L'émetteur reçoit son propre écho (``de: "moi"``) : c'est la confirmation que son geste est
    parti, et ça évite que l'écran invente un affichage que le serveur n'a pas validé.
    """
    if not isinstance(code, str) or code not in CODES:
        return {
            "type": "erreur",
            "code": ERREUR_INCONNUE,
            "message": "Cette emote n'existe pas.",
        }

    limiteur = limiteur if limiteur is not None else LIMITEUR

    reglages = await charger_reglages(db, de_user_id)
    if not reglages.recevoir_emotes:
        return {
            "type": "erreur",
            "code": ERREUR_COUPEES,
            "message": "Tu as coupé les emotes : réactive-les pour en envoyer.",
        }

    autorise, attente = limiteur.autoriser(game_id, de_user_id, maintenant)
    if not autorise:
        return {
            "type": "erreur",
            "code": ERREUR_TROP_RAPIDE,
            "message": message_trop_rapide(attente),
            "attente": round(attente, 2),
        }

    coupes = await comptes_ayant_coupe(db, bus.user_ids(game_id))
    servis = bus.publier_emote(game_id, code=code, de_user_id=de_user_id, coupes=coupes)
    logger.debug(
        "emote %s du joueur %s sur la partie %s : %d abonné(s) servi(s).",
        code,
        de_user_id,
        game_id,
        servis,
    )
    return None


__all__ = [
    "LIMITEUR",
    "BusEmotes",
    "LimiteurEmotes",
    "charger_reglages",
    "comptes_ayant_coupe",
    "diffuser_emote",
    "enregistrer_reglages",
]
