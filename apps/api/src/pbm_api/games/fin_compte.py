"""Clôture d'une partie : ce qu'elle écrit sur les comptes — une fois, et exactement (lot
`j-fin-effets-compte`, jalon J4, DJ6).

Une partie finie laisse une trace : son résultat, et ce qu'il fait aux totaux de ses deux joueurs.
Ce module est le **seul** chemin qui l'écrit, et il est bâti sur trois décisions.

**1. L'idempotence est une contrainte de base, pas un ``if``.** Une partie peut se terminer deux
fois — un coup rejoué (le client renvoie le même numéro), une reprise qui repasse par la fin, le
balayage qui croise la route du coup final, deux requêtes concurrentes. ``game_results.game_id``
est *unique* : l'écriture est un ``INSERT … ON CONFLICT DO NOTHING … RETURNING id``, et c'est
**la base** qui tranche. Pas de ligne rendue = la partie était déjà enregistrée, et on ne touche
à rien d'autre. Un test de concurrence ne serait pas nécessaire pour s'en convaincre, mais il est
là quand même.

**2. Les chiffres se recalculent, ils ne s'accumulent pas.** Le risque nommé du lot est de compter
les victoires au fil de l'eau : « personne ne remarque un compteur faux avant que quelqu'un ne
compte ». Donc :

* les chiffres **de la partie** viennent du journal, par le module pur du moteur
  (:func:`pbm_game.journal.recapitulatif.construire_recapitulatif`) — le même que celui de l'écran
  de fin, pour que les deux ne puissent pas se contredire ;
* les **totaux du joueur** (:class:`~pbm_api.models.fin_compte.PlayerStats`) sont un *cache* :
  :func:`recalculer_stats_joueur` les reconstruit intégralement depuis ses lignes de parties, à
  chaque clôture. Aucune fonction de ce module n'incrémente quoi que ce soit. Une série de victoires
  calculée par incréments serait fausse dès que le balayage répare une partie ancienne après une
  récente ; recalculée dans l'ordre des dates, elle est juste par construction.

**3. La trace ne fait jamais échouer la partie.** La clôture s'écrit **après** le commit du coup, et
dans sa propre transaction (:func:`enregistrer_fin_si_due`). Le coup gagnant ne peut donc pas être
perdu à cause d'une écriture de statistiques — ce serait le pire moment pour rendre une erreur. En
échange, cette écriture peut manquer : elle est alors journalisée en ``error``, et le **balayage**
(:func:`reprendre_fins_non_enregistrees`, appelé par le cron de maintenance des parties toutes les
dix minutes) la reprend et le dit. Ce n'est pas un repli silencieux : l'échec part dans le journal
avec sa cause, le balayage compte ce qu'il répare, et une partie close sans résultat est une
anomalie **détectable par une requête** (c'est exactement celle que le balayage fait).

⚠️ Le balayage doit tourner **avant** la purge (:func:`pbm_api.games.service.purger`) dans le même
cycle de maintenance : une partie purgée n'a plus de journal, donc plus de chiffres à recalculer.
L'ordre est posé dans :func:`pbm_api.worker.games_maintenance_task`.

**Ce que ce module ne fait pas** : ni badge (`j-profil-jeu` arrête la liste avec JF et Aymeric), ni
points de classement (`j-classement-prive` implémente la formule retenue en DJ6, « activable par
JF »). Les deux liront :class:`~pbm_api.models.fin_compte.GameResultPlayer`, qui porte déjà le
résultat, le deck et l'adversaire de chaque partie.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pbm_game.journal.recapitulatif import construire_recapitulatif
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import _entrees_queue
from pbm_api.models import (
    GAME_STATUS_EN_COURS,
    GAME_STATUS_TERMINEE,
    Game,
    GameEvent,
    GamePlayer,
)
from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
    GameResult,
    GameResultPlayer,
    PlayerStats,
)

logger = logging.getLogger(__name__)

#: Plafond d'un passage de balayage. Un balayage qui trouve plus de parties que ça (reprise après
#: une longue panne) en répare autant et **le dit** : le passage suivant, dix minutes plus tard,
#: prendra la suite. Borner évite qu'un cron de maintenance ne tienne la base une demi-heure.
BALAYAGE_PLAFOND = 50


# --- Totaux d'un joueur : une fonction pure, la seule qui calcule ------------


@dataclass(frozen=True)
class LignePartie:
    """Ce qu'une partie close apporte aux totaux d'un joueur — la forme minimale, sans base.

    C'est la projection de :class:`~pbm_api.models.fin_compte.GameResultPlayer` dont
    :func:`cumuler` a besoin. L'isoler rend le calcul des séries testable sans base de données, et
    garantit que le recalcul et la relecture passent par le **même** code.
    """

    resultat: str
    comptabilisee: bool
    duree_s: int | None
    finie_a: datetime


@dataclass(frozen=True)
class Totaux:
    """Les totaux d'un joueur, tels qu'ils seront écrits dans ``player_stats``.

    Les sept premiers champs ne portent que les parties *comptabilisées* (hors entraînement, hors
    parties expirées) ; l'entraînement a ses deux champs. ``derniere_partie_a`` compte **toutes**
    les parties, entraînement inclus : c'est « la dernière fois que j'ai joué ».
    """

    parties: int = 0
    victoires: int = 0
    defaites: int = 0
    egalites: int = 0
    serie_en_cours: int = 0
    meilleure_serie: int = 0
    temps_jeu_s: int = 0
    parties_entrainement: int = 0
    temps_jeu_entrainement_s: int = 0
    derniere_partie_a: datetime | None = None


def cumuler(lignes: Iterable[LignePartie]) -> Totaux:
    """Les totaux d'un joueur, calculés depuis la liste **complète** de ses parties, dans l'ordre.

    Fonction **pure** : deux appels sur la même liste rendent le même résultat, et elle n'a besoin
    d'aucune base. C'est ce qui permet de ne jamais incrémenter un compteur — on relit, on
    recalcule, on écrit.

    ``lignes`` doit être dans l'ordre **chronologique** (du plus ancien au plus récent) : la série
    en cours est celle qui termine la liste. Un ordre faux ne donnerait pas une série fausse « un
    peu », il donnerait n'importe quoi — l'appelant trie (:func:`_lignes_du_joueur`), et cette
    exigence est la raison pour laquelle ``finie_a`` est dénormalisé sur chaque ligne.

    ``duree_s`` à ``None`` (horodatages de journal illisibles) n'ajoute rien au temps de jeu : on
    préfère un temps légèrement sous-estimé à un temps inventé.
    """
    parties = victoires = defaites = egalites = 0
    serie = meilleure = 0
    temps = 0
    entrainements = temps_entrainement = 0
    derniere: datetime | None = None

    for ligne in lignes:
        if derniere is None or ligne.finie_a > derniere:
            derniere = ligne.finie_a
        if not ligne.comptabilisee:
            entrainements += 1
            temps_entrainement += ligne.duree_s or 0
            # Une partie qui ne compte pas ne touche NI les totaux NI la série : s'entraîner contre
            # le bot ne peut ni nourrir ni casser une série (critère d'acceptation du lot).
            continue
        parties += 1
        temps += ligne.duree_s or 0
        if ligne.resultat == RESULTAT_VICTOIRE:
            victoires += 1
            serie += 1
            meilleure = max(meilleure, serie)
        elif ligne.resultat == RESULTAT_DEFAITE:
            defaites += 1
            serie = 0
        else:
            egalites += 1
            # Une égalité n'est pas une victoire : elle interrompt la série (voir
            # :class:`~pbm_api.models.fin_compte.PlayerStats`).
            serie = 0

    return Totaux(
        parties=parties,
        victoires=victoires,
        defaites=defaites,
        egalites=egalites,
        serie_en_cours=serie,
        meilleure_serie=meilleure,
        temps_jeu_s=temps,
        parties_entrainement=entrainements,
        temps_jeu_entrainement_s=temps_entrainement,
        derniere_partie_a=derniere,
    )


# --- Recalcul du cache des totaux -------------------------------------------


async def _lignes_du_joueur(db: AsyncSession, user_id: uuid.UUID) -> list[LignePartie]:
    """Toutes les parties closes d'un joueur, **dans l'ordre des dates de fin**.

    Une seule table, aucune jointure : c'est à cela que servent ``comptabilisee`` et ``finie_a``
    dénormalisés sur :class:`~pbm_api.models.fin_compte.GameResultPlayer`. Le départage par
    ``game_id`` rend l'ordre total déterministe quand deux parties se terminent dans la même
    microseconde — sans lui, deux recalculs pourraient rendre deux séries différentes.
    """
    rows = await db.execute(
        select(
            GameResultPlayer.resultat,
            GameResultPlayer.comptabilisee,
            GameResultPlayer.duree_s,
            GameResultPlayer.finie_a,
        )
        .where(GameResultPlayer.user_id == user_id)
        .order_by(GameResultPlayer.finie_a, GameResultPlayer.game_id)
    )
    return [
        LignePartie(resultat=r, comptabilisee=c, duree_s=d, finie_a=f) for r, c, d, f in rows.all()
    ]


async def recalculer_stats_joueur(db: AsyncSession, user_id: uuid.UUID) -> Totaux:
    """Reconstruit **intégralement** les totaux d'un joueur depuis ses parties — sans commit.

    C'est la seule écriture de ``player_stats`` du dépôt : il n'existe aucun chemin qui incrémente.
    Appelée à chaque clôture (pour les deux joueurs) et utilisable seule pour réparer ou vérifier —
    la suite de tests s'en sert pour prouver que le cache est bien un cache (le supprimer puis
    recalculer redonne la même ligne).

    Renvoie les totaux écrits, pour que l'appelant puisse les journaliser ou les comparer.
    """
    totaux = cumuler(await _lignes_du_joueur(db, user_id))
    valeurs = {
        "parties": totaux.parties,
        "victoires": totaux.victoires,
        "defaites": totaux.defaites,
        "egalites": totaux.egalites,
        "serie_en_cours": totaux.serie_en_cours,
        "meilleure_serie": totaux.meilleure_serie,
        "temps_jeu_s": totaux.temps_jeu_s,
        "parties_entrainement": totaux.parties_entrainement,
        "temps_jeu_entrainement_s": totaux.temps_jeu_entrainement_s,
        "derniere_partie_a": totaux.derniere_partie_a,
    }
    # `ON CONFLICT … DO UPDATE` plutôt qu'un « lire puis écrire » : la ligne peut naître de deux
    # clôtures concurrentes du même joueur (deux parties en parallèle), et un `SELECT` suivi d'un
    # `INSERT` perdrait la course. L'écriture reste idempotente — elle pose un état calculé.
    await db.execute(
        pg_insert(PlayerStats)
        .values(user_id=user_id, **valeurs)
        .on_conflict_do_update(index_elements=["user_id"], set_=valeurs)
    )
    return totaux


# --- Écriture de la clôture --------------------------------------------------


def _resultat_de(vainqueur_user_id: uuid.UUID | None, user_id: uuid.UUID) -> str:
    """Le résultat d'un joueur : victoire, défaite, ou égalité quand il n'y a pas de vainqueur."""
    if vainqueur_user_id is None:
        return RESULTAT_EGALITE
    return RESULTAT_VICTOIRE if vainqueur_user_id == user_id else RESULTAT_DEFAITE


async def _fin_a(db: AsyncSession, game_id: uuid.UUID) -> datetime:
    """L'instant de fin de la partie : l'horodatage que **la base** a posé sur son dernier coup.

    On ne prend pas l'horodatage porté par l'entrée de journal : c'est une donnée *fournie* au
    moteur (qui est pur, sans horloge), rien n'en garantit la forme sur une partie ancienne.
    ``created_at`` est posé par PostgreSQL à l'insertion — c'est la date la plus fiable dont on
    dispose pour ranger l'historique. Journal vide (cas de plumberie) : l'instant courant, faute de
    mieux, et c'est dit dans le journal du serveur.
    """
    dernier = (
        await db.execute(select(func.max(GameEvent.created_at)).where(GameEvent.game_id == game_id))
    ).scalar_one_or_none()
    if dernier is not None:
        return dernier
    logger.info(
        "clôture de la partie %s : journal vide, la date de fin est l'instant courant.", game_id
    )
    return datetime.now(UTC)


async def enregistrer_fin_de_partie(db: AsyncSession, game_id: uuid.UUID) -> bool:
    """Écrit ce que cette partie close laisse sur les comptes — **une transaction, une seule fois**.

    Renvoie ``True`` si cet appel a écrit le résultat, ``False`` s'il n'y avait rien à écrire : soit
    la partie n'existe pas (purgée), soit elle est encore en cours, soit son résultat était **déjà**
    enregistré. Ce dernier cas est tranché par la contrainte d'unicité
    ``uq_game_results_game`` — pas par une lecture préalable, qui perdrait la course entre deux
    clôtures concurrentes.

    Ce qui est écrit, dans l'ordre et dans la même transaction : le résultat de la partie, une ligne
    par joueur avec ses chiffres recalculés depuis le journal, puis les totaux des deux joueurs
    (recalculés, jamais incrémentés). Commit à la fin : soit tout est là, soit rien ne l'est — et
    dans ce second cas le balayage repassera.
    """
    game = (await db.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if game is None or game.status == GAME_STATUS_EN_COURS:
        return False

    sieges: Sequence[GamePlayer] = (
        (
            await db.execute(
                select(GamePlayer).where(GamePlayer.game_id == game_id).order_by(GamePlayer.seat)
            )
        )
        .scalars()
        .all()
    )
    entrees = await _entrees_queue(db, game.id, 0, game.current_numero)
    recap = construire_recapitulatif(entrees, [joueur_id_de(s.user_id) for s in sieges])
    # Une partie d'entraînement (DJ7) et une partie expirée faute d'activité entrent dans
    # l'historique mais ne comptent pas : voir `GameResult.comptabilisee`.
    comptabilisee = game.status == GAME_STATUS_TERMINEE and not game.entrainement
    finie_a = await _fin_a(db, game.id)

    inseree = (
        await db.execute(
            pg_insert(GameResult)
            .values(
                id=uuid.uuid4(),
                game_id=game.id,
                statut=game.status,
                raison_fin=game.raison_fin,
                vainqueur_user_id=game.vainqueur_user_id,
                entrainement=game.entrainement,
                comptabilisee=comptabilisee,
                coups=recap.coups,
                tours=recap.tours,
                duree_s=recap.duree_s,
                journal_numero=game.current_numero,
                finie_a=finie_a,
            )
            .on_conflict_do_nothing(constraint="uq_game_results_game")
            .returning(GameResult.id)
        )
    ).scalar_one_or_none()

    if inseree is None:
        # Déjà enregistrée : on ne retouche NI les lignes de joueurs NI les totaux. C'est le
        # critère d'acceptation du lot — rejouer la clôture ne modifie rien la deuxième fois.
        await db.commit()
        logger.debug("clôture de la partie %s déjà enregistrée — rien écrit.", game_id)
        return False

    stats_par_jid = {s.joueur: s for s in recap.joueurs}
    for index, siege in enumerate(sieges):
        autre = sieges[1 - index] if len(sieges) == 2 else None
        chiffres = stats_par_jid.get(joueur_id_de(siege.user_id))
        db.add(
            GameResultPlayer(
                game_id=game.id,
                user_id=siege.user_id,
                seat=siege.seat,
                deck_id=siege.deck_id,
                adversaire_user_id=autre.user_id if autre is not None else None,
                adversaire_bot=autre is not None and autre.bot_niveau is not None,
                resultat=_resultat_de(game.vainqueur_user_id, siege.user_id),
                comptabilisee=comptabilisee,
                finie_a=finie_a,
                duree_s=recap.duree_s,
                degats_infliges=chiffres.degats_infliges if chiffres else 0,
                kos_infliges=chiffres.kos_infliges if chiffres else 0,
                recompenses_prises=chiffres.recompenses_prises if chiffres else 0,
                cartes_jouees=chiffres.cartes_jouees if chiffres else 0,
                energies_attachees=chiffres.energies_attachees if chiffres else 0,
                coups_joues=chiffres.coups_joues if chiffres else 0,
            )
        )
    # Les lignes de joueurs doivent exister avant le recalcul : c'est d'elles qu'il part.
    await db.flush()
    for siege in sieges:
        await recalculer_stats_joueur(db, siege.user_id)
    await db.commit()

    logger.info(
        "clôture enregistrée — partie %s (%s, raison %s, %d coup(s), comptabilisée : %s).",
        game_id,
        game.status,
        game.raison_fin,
        recap.coups,
        comptabilisee,
    )
    return True


async def enregistrer_fin_si_due(db: AsyncSession, game: Game) -> bool:
    """Écrit la clôture d'une partie qui vient d'être close — et ne casse **jamais** la partie.

    Appelée depuis le chemin d'un coup, **après son commit** : la trace a sa propre transaction, et
    le coup gagnant ne peut donc pas être perdu à cause d'une écriture de statistiques. L'échec est
    journalisé en ``error`` (jamais avalé) et le balayage
    (:func:`reprendre_fins_non_enregistrees`) reprend la partie au passage suivant — c'est le
    « prévoir la reprise après panne » de la mission du lot.

    Ne fait rien si la partie est encore en cours : l'appelant n'a pas à le savoir.
    """
    if game.status == GAME_STATUS_EN_COURS:
        return False
    try:
        return await enregistrer_fin_de_partie(db, game.id)
    except Exception:  # noqa: BLE001 — la trace n'interrompt jamais une partie (en-tête du module)
        await db.rollback()
        logger.exception(
            "échec d'écriture de la clôture de la partie %s : la partie reste close et correcte, "
            "le balayage de maintenance la reprendra.",
            game.id,
        )
        return False


# --- Balayage de reprise ----------------------------------------------------


async def reprendre_fins_non_enregistrees(
    db: AsyncSession, *, plafond: int = BALAYAGE_PLAFOND
) -> dict[str, int]:
    """Reprend les parties closes dont la trace manque — et **le dit**.

    Deux populations, toutes les deux réelles : les parties dont l'écriture a échoué (serveur tué
    entre le commit du coup et celui de la trace, base indisponible une seconde), et les parties
    **closes avant ce lot**, qui n'ont jamais eu de résultat. Les deux se reconnaissent de la même
    façon : un statut terminal, et aucune ligne dans ``game_results``.

    Renvoie ``{"reprises": n, "restantes": m}`` et le journalise. ``restantes`` est ce que le
    plafond a laissé pour le passage suivant : un balayage ne cache pas ce qu'il n'a pas fait.

    ⚠️ À appeler **avant** la purge dans un cycle de maintenance : une partie purgée n'a plus de
    journal, donc plus de chiffres (voir :func:`pbm_api.worker.games_maintenance_task`).
    """
    manquantes = (
        (
            await db.execute(
                select(Game.id)
                .where(
                    Game.status != GAME_STATUS_EN_COURS,
                    ~select(GameResult.id)
                    .where(GameResult.game_id == Game.id)
                    .exists(),
                )
                .order_by(Game.updated_at)
            )
        )
        .scalars()
        .all()
    )

    reprises = 0
    for game_id in manquantes[:plafond]:
        if await enregistrer_fin_de_partie(db, game_id):
            reprises += 1
    restantes = max(0, len(manquantes) - plafond)

    if reprises or restantes:
        logger.warning(
            "balayage des clôtures : %d partie(s) close(s) sans résultat ont été reprises, "
            "%d restent pour le passage suivant.",
            reprises,
            restantes,
        )
    else:
        logger.info("balayage des clôtures : rien à reprendre, toute partie close a son résultat.")
    return {"reprises": reprises, "restantes": restantes}


__all__ = [
    "BALAYAGE_PLAFOND",
    "LignePartie",
    "Totaux",
    "cumuler",
    "enregistrer_fin_de_partie",
    "enregistrer_fin_si_due",
    "recalculer_stats_joueur",
    "reprendre_fins_non_enregistrees",
]
