"""Plafond de **parties simultanées** : ce que la machine qui sert peut tenir.

Lot ``j-charge-temps-reel``.

Le jeu est servi par un serveur partagé : **2 vCPU, 3,8 Go**, qui héberge déjà `kailo.life`, l'UAT
de Kailo et ACX. Une partie n'est pas gratuite — chaque coup recharge un instantané, rejoue la queue
du journal, applique l'action et écrit une ligne. Au-delà d'un certain nombre de parties qui jouent
en même temps, la latence d'un coup cesse d'être tenable et **toutes** les parties se dégradent
ensemble : c'est le pire mode de panne, parce que personne ne sait qui est en cause.

Le choix de ce lot est donc : **refuser une partie de plus, plutôt que ralentir toutes les autres.**
Un refus est lisible (« le serveur est à sa capacité, réessaie dans un instant »), un ralentissement
général ne l'est pas. Les chiffres qui fixent le plafond sont dans ``docs/jeu/CHARGE.md`` — ce sont
eux qu'on relira le jour d'un incident, et ``apps/api/scripts/measure_game_load.py`` qui les refait.

Deux détails qui n'en sont pas :

* **Une partie échue ne compte pas.** Le plafond ne retient que les parties `en_cours` dont
  ``expires_at`` est encore dans le futur. Sans ce filtre, quelques dizaines de parties abandonnées
  confisqueraient toutes les places jusqu'au passage du balayage (``expirer_parties``, toutes les
  10 min) — au pire pendant ``jeu_inactivite_plafond_h`` heures. Le plafond protège le CPU, et une
  partie que personne ne joue n'en consomme pas.
* **Une partie d'entraînement compte.** Elle ne compte pas au classement, mais le bot (et plus
  encore l'IA) consomme *plus* de serveur qu'un humain, qui réfléchit entre deux coups.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.games.errors import PlafondPartiesAtteint
from pbm_api.models.games import GAME_STATUS_EN_COURS, Game
from pbm_api.models.observabilite import INCIDENT_PARTIE_REFUSEE
from pbm_api.observabilite.consignation import consigner_incident
from pbm_api.observabilite.motifs import MOTIF_CAPACITE_ATTEINTE, detail_borne

logger = logging.getLogger(__name__)

#: Plafond de repli, utilisé si la configuration est absente ou absurde (≤ 0). Volontairement égal
#: au défaut de ``settings.jeu_parties_simultanees_max`` : un réglage cassé ne doit pas *ouvrir* la
#: vanne en silence, il doit retomber sur la valeur mesurée.
PLAFOND_REPLI = 24

#: Clé du verrou consultatif Postgres qui sérialise les **créations** de parties, le temps du
#: comptage et de l'insertion. Un `bigint` arbitraire mais stable (il n'a de sens que partagé) ;
#: aucun autre code du dépôt ne prend de ``pg_advisory_xact_lock``.
CLE_VERROU_CAPACITE = 7_061_431_000_001

#: Délai suggéré au client avant de retenter (en-tête ``Retry-After``). Une partie dure quelques
#: dizaines de minutes, mais une place se libère à la granularité de la minute (fin de partie,
#: balayage des parties échues toutes les 10 min) : retenter dans 30 s est utile et sans effet de
#: meute — c'est aussi le délai qu'affiche l'écran.
RETRY_APRES_SECONDES = 30


def plafond() -> int:
    """Le plafond de parties simultanées, depuis la configuration.

    Lu à chaque appel plutôt que figé à l'import : on peut desserrer ou resserrer la vanne par
    l'environnement sans redéployer — ce qui compte le jour où le serveur cible change de taille.
    Une valeur absente ou ≤ 0 retombe sur :data:`PLAFOND_REPLI` **en le disant** : un réglage cassé
    qui ouvrirait grand la vanne serait un repli silencieux.
    """
    brut = settings.jeu_parties_simultanees_max
    if brut is None or brut <= 0:
        logger.warning(
            "jeu_parties_simultanees_max absent ou invalide (%r) — repli sur %d.",
            brut,
            PLAFOND_REPLI,
        )
        return PLAFOND_REPLI
    return int(brut)


async def compter_parties_actives(db: AsyncSession, *, maintenant: datetime | None = None) -> int:
    """Le nombre de parties qui **occupent une place** : en cours et non échues.

    Un seul `count(*)` agrégé, servi par les index de ``games.status`` et ``games.expires_at`` :
    aucune ligne de partie n'est rapatriée (même principe que
    :mod:`pbm_api.observabilite.metriques`), parce que ce comptage est sur le chemin de **chaque**
    création de partie.
    """
    maintenant = maintenant or datetime.now(UTC)
    compte = await db.execute(
        select(func.count())
        .select_from(Game)
        .where(Game.status == GAME_STATUS_EN_COURS, Game.expires_at > maintenant)
    )
    return int(compte.scalar_one())


async def verifier_capacite(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
    consigner: bool = True,
) -> int:
    """Lève :class:`PlafondPartiesAtteint` si le serveur tient déjà son plafond ; sinon le compte.

    Appelée **deux fois** par :func:`pbm_api.games.service.creer_partie`, et c'est voulu :

    1. une première fois à l'entrée, **sans verrou** — elle évite de payer la résolution des deux
       decks (requêtes catalogue + scripts) pour une partie qu'on va refuser. En régime saturé,
       c'est la différence entre un refus bon marché et un refus qui coûte autant qu'une création,
       donc entre un serveur qui encaisse les tentatives et un serveur qui s'écroule sous elles ;
    2. une seconde fois sous :func:`verrouiller_creations`, juste avant l'insertion — elle rend le
       plafond **exact** sous concurrence. Sans elle, dix créations simultanées lisent toutes le
       même compte et en insèrent dix : le plafond serait indicatif, pas appliqué.

    ``consigner`` écrit un incident ``partie_refusee`` / ``capacite_atteinte`` : c'est ce qui rend
    la saturation visible dans ``GET /jeu/metriques`` (compteur ``parties_refusees``) avant qu'elle
    n'arrive sous forme de plainte — le but du jalon J5. On ne le fait qu'au **premier** contrôle,
    pour ne pas compter deux fois le même refus.
    """
    actives = await compter_parties_actives(db, maintenant=maintenant)
    maximum = plafond()
    if actives < maximum:
        return actives

    logger.warning(
        "partie refusée : plafond de parties simultanées atteint (%d/%d) — joueur %s.",
        actives,
        maximum,
        user_id,
    )
    if consigner:
        await consigner_incident(
            genre=INCIDENT_PARTIE_REFUSEE,
            motif=MOTIF_CAPACITE_ATTEINTE,
            user_id=user_id,
            detail=detail_borne(f"{actives} parties actives pour un plafond de {maximum}"),
            horodatage=maintenant,
        )
    raise PlafondPartiesAtteint(actives, maximum)


async def verrouiller_creations(db: AsyncSession) -> None:
    """Prend le verrou consultatif qui sérialise les créations de parties jusqu'au `commit`.

    ``pg_advisory_xact_lock`` est relâché par Postgres à la fin de la transaction, y compris en cas
    d'erreur ou de `rollback` : il ne peut pas rester pris sur une création qui échoue. Il ne
    sérialise **que** les créations — un coup joué dans une partie en cours ne le demande jamais,
    donc les parties en vol ne ralentissent pas quand des joueurs cherchent à en lancer d'autres
    (c'est le critère « une partie de plus est refusée *et* les parties en cours ne ralentissent
    pas »).

    Il est réentrant pour un même détenteur : une transaction qui crée deux parties l'obtient deux
    fois sans se bloquer elle-même — le cas des tests, qui tiennent une transaction par test.
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:cle)"), {"cle": CLE_VERROU_CAPACITE})


__all__ = [
    "CLE_VERROU_CAPACITE",
    "PLAFOND_REPLI",
    "RETRY_APRES_SECONDES",
    "compter_parties_actives",
    "plafond",
    "verifier_capacite",
    "verrouiller_creations",
]
