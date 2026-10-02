"""Service de parties : créer, appliquer, reprendre, expirer, purger (lot `j-partie-service`).

Ce module est l'**enveloppe** qui transforme le moteur de règles pur (`pbm_game`) en parties
réelles persistées. Le moteur ne connaît ni HTTP ni base ; ici vivent la transaction, le verrou,
l'idempotence et la lecture du catalogue. Les cinq opérations :

* :func:`creer_partie` — résout deux decks en scripts (refuse une carte non jouable, D9), fabrique
  l'état initial, tire une graine, et persiste la partie + un instantané au coup 0 ;
* :func:`appliquer_action` — la **boucle** : reçoit un coup → le valide par le moteur → l'écrit au
  journal → en déduit le nouvel état → renvoie les événements, dans **une** transaction,
  sous verrou de ligne et avec **idempotence par numéro d'action** (risque nommé du lot) ;
* :func:`reprendre` — reconstruit l'état depuis le dernier instantané + la queue du journal, et
  **compare l'empreinte** : ce qui fait survivre une partie à un redémarrage complet de l'API ;
* :func:`expirer_parties` — fige les parties abandonnées (inactives trop longtemps) ;
* :func:`purger` — supprime les parties mortes anciennes et les instantanés superflus, avec une
  métrique de ce qui a été purgé (jamais un nettoyage muet).

« Tout est rejouable » : on ne stocke jamais l'état courant comme source de vérité, seulement l'état
initial, la graine et le journal numéroté. `current_numero`/`current_empreinte` sur `Game` sont un
cache reconstructible.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pbm_game.journal import (
    JOURNAL_VERSION,
    Action,
    appliquer,
    compacter,
    empreinte,
    entree_depuis_json,
    entree_vers_json,
    instantane_depuis_json,
    instantane_vers_json,
    partie_neuve,
    reprendre,
)
from pbm_game.journal.modele import AUTEUR_SYSTEME, Entree, Instantane
from pbm_game.rng import GRAINE_MIN_OCTETS, Rng, engagement
from pbm_game.state.modele import EtatPartie
from pbm_game.state.serialisation import vers_json as etat_vers_json
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pbm_api.config import settings
from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.construction import (
    construire_etat_initial,
    joueur_id_de,
    resoudre_deck,
)
from pbm_api.games.errors import (
    ActionRefusee,
    CartesNonJouables,
    ConflitNumero,
    PartieIntrouvable,
    PartieNonActive,
)
from pbm_api.models.games import (
    GAME_STATUS_EN_COURS,
    GAME_STATUS_EXPIREE,
    GAME_STATUS_TERMINEE,
    Game,
    GameEvent,
    GamePlayer,
    GameSnapshot,
)

logger = logging.getLogger(__name__)

#: Un instantané de compaction est figé tous les N coups, pour borner la queue à rejouer à la
#: reprise (une partie de 400 coups ne doit pas en rejouer 400 à chaque F5). Surchargeable par
#: :func:`appliquer_action` (les tests prennent un intervalle court pour exercer la compaction).
INTERVALLE_INSTANTANE = 16

#: Une partie sans action depuis ce délai est « abandonnée » : :func:`expirer_parties` la fige.
#: Chaque coup repousse l'échéance (``last_action_at`` + ce délai).
DELAI_INACTIVITE = timedelta(days=3)

#: Une partie morte (terminée ou expirée) plus ancienne que ce délai est purgée.
ANCIENNETE_PURGE = timedelta(days=30)

#: Fenêtre glissante d'observation des coups refusés, par (partie, joueur). Un client honnête se
#: trompe rarement ; une **rafale** de coups illégaux trahit un client modifié qui sonde l'autorité
#: du serveur. Cadre du lot `j-autorite-vues` : « alerter sur les motifs anormaux ».
FENETRE_REFUS = timedelta(minutes=1)

#: Au-delà de ce nombre de refus dans la fenêtre pour un même joueur sur une même partie, on hausse
#: le ton : un avis (WARNING par coup) devient une **alerte** (ERROR).
SEUIL_REFUS_RAFALE = 5

#: Horodatages des refus récents, par (game_id, user_id). En mémoire du process : c'est une sonde
#: d'alerte, pas une source de vérité ni une limite de débit dure — elle ne persiste rien et ne
#: bloque aucun coup ; elle rend seulement visible un comportement anormal.
_refus_recents: dict[tuple[uuid.UUID, uuid.UUID], list[datetime]] = {}


def reinitialiser_alerte_refus() -> None:
    """Vide la fenêtre d'observation des refus — point d'entrée pour les tests, jamais en prod."""
    _refus_recents.clear()


def _journaliser_refus(
    game_id: uuid.UUID, user_id: uuid.UUID, type_action: str, motif: str, maintenant: datetime
) -> int:
    """Trace un coup refusé et **alerte** en cas de rafale ; renvoie le nombre de refus récents.

    Un coup refusé n'est jamais avalé en silence (« aucun repli silencieux ») : il est tracé avec
    sa cause. Si un même joueur accumule les coups illégaux dans :data:`FENETRE_REFUS`, on émet une
    alerte — signe d'un client modifié. On ne bloque pas le joueur pour autant : le serveur fait
    déjà autorité (l'état n'a pas bougé), l'alerte sert la supervision, pas le refus.
    """
    logger.warning(
        "coup refusé — partie %s, joueur %s, action « %s » : %s",
        game_id,
        user_id,
        type_action,
        motif,
    )
    cle = (game_id, user_id)
    recents = [t for t in _refus_recents.get(cle, []) if maintenant - t < FENETRE_REFUS]
    recents.append(maintenant)
    _refus_recents[cle] = recents
    if len(recents) >= SEUIL_REFUS_RAFALE:
        logger.error(
            "ALERTE anti-triche : %d coups illégaux en moins de %s pour le joueur %s sur la "
            "partie %s — client possiblement modifié.",
            len(recents),
            FENETRE_REFUS,
            user_id,
            game_id,
        )
    return len(recents)


def _maintenant() -> datetime:
    """Instant courant en UTC **aware** — les colonnes de parties sont `DateTime(timezone=True)`.

    On garde des datetimes aware de bout en bout (création, comparaison d'expiration, purge) pour ne
    jamais mélanger aware et naïf : un mélange casse les comparaisons SQL et l'évaluation ORM.
    """
    return datetime.now(UTC)


@dataclass(frozen=True)
class ResultatAction:
    """Ce que :func:`appliquer_action` renvoie — de quoi journaliser, diffuser et afficher.

    `rejoue` est vrai quand l'action était un **rejeu idempotent** (même numéro, même coup déjà
    appliqué) : aucune nouvelle entrée n'a été écrite, on renvoie le résultat déjà enregistré. La
    diffusion temps réel des événements est le lot `j-temps-reel` ; ici on les **renvoie** à
    l'appelant, qui les diffusera — jamais un stub muet.
    """

    numero: int
    evenements: list[dict]
    empreinte: str
    terminee: bool
    vainqueur_user_id: uuid.UUID | None
    raison_fin: str | None
    etat: dict
    rejoue: bool
    #: Compteurs de tirages du Rng à ce point (``rng.compteurs()``). La **projection** vers un
    #: client (lot `j-autorite-vues`) en dérive l'**époque** des jetons de cartes cachées : le
    #: nombre de mélanges du deck d'un joueur. Donnée interne — jamais renvoyée telle quelle.
    rng_compteurs: dict[str, int]
    #: Temps restant affichable (vérité serveur au moment du coup), ou None si la partie n'a
    #: pas d'horloges (créée avant j-timer). Le client en fait une estimation recalée (j-timer).
    horloges: dict | None = None


# --- Création ----------------------------------------------------------------


async def creer_partie(
    db: AsyncSession,
    *,
    joueur_a: tuple[uuid.UUID, uuid.UUID],
    joueur_b: tuple[uuid.UUID, uuid.UUID],
    graine_hex: str | None = None,
    maintenant: datetime | None = None,
) -> Game:
    """Crée une partie entre deux joueurs (chacun `(user_id, deck_id)`), ou **refuse**.

    Résout chaque deck en scripts : toute carte non jouable fait lever :class:`CartesNonJouables`
    avec la liste des cartes (D9 — jamais jouée de travers). Construit l'état initial, tire une
    graine d'aléatoire (le moteur est pur : la graine vient d'ici), et persiste `Game`, les deux
    `GamePlayer` et un `GameSnapshot` au coup 0. La graine est un **secret** (commit-reveal) : seul
    l'engagement est destiné à être publié.
    """
    maintenant = maintenant or _maintenant()
    user_a, deck_a = joueur_a
    user_b, deck_b = joueur_b
    id_a, id_b = joueur_id_de(user_a), joueur_id_de(user_b)

    cartes_a, refus_a = await resoudre_deck(db, deck_a, id_a)
    cartes_b, refus_b = await resoudre_deck(db, deck_b, id_b)
    refus = refus_a + refus_b
    if refus:
        raise CartesNonJouables(refus)

    etat_initial = construire_etat_initial((id_a, cartes_a), (id_b, cartes_b))

    graine_hex = graine_hex or os.urandom(max(32, GRAINE_MIN_OCTETS)).hex()
    engagement_hex = engagement(bytes.fromhex(graine_hex))

    partie = partie_neuve(etat_initial, graine_hex)
    instantane0 = compacter(partie, 0)
    empreinte0 = instantane0.empreinte

    game = Game(
        status=GAME_STATUS_EN_COURS,
        etat_initial=etat_vers_json(etat_initial),
        graine=graine_hex,
        engagement=engagement_hex,
        journal_version=JOURNAL_VERSION,
        current_numero=0,
        current_empreinte=empreinte0,
        last_action_at=maintenant,
        expires_at=maintenant + DELAI_INACTIVITE,
        horloges=_adapt_horloges.etat_initial_json(
            _adapt_horloges.config_horloges(settings), etat_initial, maintenant.timestamp()
        ),
    )
    db.add(game)
    await db.flush()

    db.add_all(
        [
            GamePlayer(game_id=game.id, user_id=user_a, deck_id=deck_a, seat=0),
            GamePlayer(game_id=game.id, user_id=user_b, deck_id=deck_b, seat=1),
        ]
    )
    db.add(_snapshot_row(game.id, instantane0))
    await db.commit()
    await db.refresh(game)
    return game


def _snapshot_row(game_id: uuid.UUID, instantane: Instantane) -> GameSnapshot:
    """Un `GameSnapshot` depuis un :class:`Instantane` du moteur (forme JSON versionnée)."""
    brut = instantane_vers_json(instantane)
    return GameSnapshot(
        game_id=game_id,
        numero_entrees=brut["numero_entrees"],
        etat=brut["etat"],
        rng_etat=brut["rng_etat"],
        empreinte=brut["empreinte"],
        journal_version=brut["journal_version"],
    )


# --- Accès -------------------------------------------------------------------


async def _game_pour_participant(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, *, verrou: bool = False
) -> Game:
    """Charge une partie **à laquelle l'utilisateur participe**, sinon :class:`PartieIntrouvable`.

    On ne distingue pas « n'existe pas » de « pas la vôtre » (→ 404, jamais 403) : pas de fuite
    d'existence. `verrou=True` pose un `SELECT ... FOR UPDATE` sur la ligne de partie — c'est le
    point de sérialisation des écritures concurrentes (idempotence par numéro).
    """
    requete = select(Game).where(Game.id == game_id)
    if verrou:
        requete = requete.with_for_update()
    game = (await db.execute(requete)).scalar_one_or_none()
    if game is None:
        raise PartieIntrouvable(f"Partie {game_id} introuvable.")
    participe = (
        await db.execute(
            select(GamePlayer.id).where(
                GamePlayer.game_id == game_id, GamePlayer.user_id == user_id
            )
        )
    ).first()
    if participe is None:
        raise PartieIntrouvable(f"Partie {game_id} introuvable.")
    return game


async def parties_du_joueur(db: AsyncSession, user_id: uuid.UUID) -> list[Game]:
    """Les parties auxquelles l'utilisateur participe, de la plus récente à la plus ancienne."""
    rows = await db.execute(
        select(Game)
        .join(GamePlayer, GamePlayer.game_id == Game.id)
        .where(GamePlayer.user_id == user_id)
        .order_by(Game.created_at.desc())
    )
    return list(rows.scalars().all())


# --- Reconstruction / reprise ------------------------------------------------


async def _entrees_queue(
    db: AsyncSession, game_id: uuid.UUID, depuis: int, jusqu_a: int
) -> tuple[Entree, ...]:
    """Les entrées de numéro ∈ [`depuis`, `jusqu_a`), dans l'ordre, en `Entree` du moteur."""
    rows = await db.execute(
        select(GameEvent)
        .where(
            GameEvent.game_id == game_id,
            GameEvent.numero >= depuis,
            GameEvent.numero < jusqu_a,
        )
        .order_by(GameEvent.numero)
    )
    return tuple(_entree_depuis_row(row) for row in rows.scalars().all())


def _entree_depuis_row(row: GameEvent) -> Entree:
    return entree_depuis_json(
        {
            "numero": row.numero,
            "auteur": row.auteur,
            "action": row.action,
            "evenements": row.evenements,
            "horodatage": row.horodatage,
            "empreinte": row.empreinte,
        }
    )


async def _dernier_instantane(
    db: AsyncSession, game_id: uuid.UUID, jusqu_a: int
) -> Instantane:
    """Le dernier instantané de numéro ≤ `jusqu_a` (il en existe toujours un au coup 0)."""
    row = (
        await db.execute(
            select(GameSnapshot)
            .where(
                GameSnapshot.game_id == game_id,
                GameSnapshot.numero_entrees <= jusqu_a,
            )
            .order_by(GameSnapshot.numero_entrees.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(
            f"Partie {game_id} sans instantané au coup 0 : incohérence de persistance "
            "(une partie est toujours créée avec son instantané initial)."
        )
    return instantane_depuis_json(
        {
            "journal_version": row.journal_version,
            "numero_entrees": row.numero_entrees,
            "etat": row.etat,
            "rng_etat": row.rng_etat,
            "empreinte": row.empreinte,
        }
    )


async def _reconstruire(db: AsyncSession, game: Game) -> tuple[EtatPartie, Rng]:
    """Reconstruit `(etat, rng)` à `game.current_numero` : dernier instantané + rejeu de la queue.

    C'est la mécanique de « tout est rejouable » : rien n'est gardé en mémoire d'un redémarrage à
    l'autre, l'état se recalcule depuis la base. `reprendre` vérifie l'empreinte de l'instantané
    puis de **chaque** coup rejoué — une divergence lève, jamais tue en silence.
    """
    instantane = await _dernier_instantane(db, game.id, game.current_numero)
    queue = await _entrees_queue(db, game.id, instantane.numero_entrees, game.current_numero)
    return reprendre(instantane, queue)


async def reprendre_partie(
    db: AsyncSession, game: Game
) -> tuple[EtatPartie, Rng]:
    """Reprend une partie et **vérifie l'empreinte** contre le cache (`game.current_empreinte`).

    Satisfait le critère d'acceptation : « une partie survit à un redémarrage complet de l'API : la
    reprise redonne l'état exact, empreinte comprise ». Un écart lève :class:`RuntimeError` (jamais
    de reprise silencieuse sur un état douteux).
    """
    etat, rng = await _reconstruire(db, game)
    empr = empreinte(etat)
    if empr != game.current_empreinte:
        raise RuntimeError(
            f"Reprise divergente de la partie {game.id} : empreinte reconstruite {empr}, "
            f"cache {game.current_empreinte}."
        )
    return etat, rng


# --- Boucle d'application ----------------------------------------------------


def _memes_actions(stockee: dict, soumise: Action) -> bool:
    """Deux actions sont « le même coup » si type, auteur et params coïncident (idempotence)."""
    return (
        stockee.get("type") == soumise.type
        and stockee.get("auteur") == soumise.auteur
        and (stockee.get("params") or {}) == (soumise.params or {})
    )


async def appliquer_action(
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    type: str,
    params: dict | None = None,
    numero_attendu: int,
    maintenant: datetime | None = None,
    intervalle_instantane: int = INTERVALLE_INSTANTANE,
) -> ResultatAction:
    """Applique un coup à une partie, dans une transaction, sous verrou, avec idempotence.

    Déroulé (le serveur fait autorité) :

    1. charge la partie **sous verrou de ligne** (sérialise les requêtes concurrentes) et vérifie
       que l'utilisateur y participe (sinon 404) et qu'elle est **en cours** (sinon 409) ;
    2. **idempotence par numéro** : si `numero_attendu` est déjà joué par **le même** coup, on
       renvoie le résultat déjà enregistré sans rien réappliquer (`rejoue=True`) ; si c'est un
       **autre** coup, ou un numéro en avance, c'est un :class:`ConflitNumero` (409) ;
    3. reconstruit l'état courant, rejoue l'action par le moteur (un refus lève
       :class:`ActionRefusee`, 422), écrit l'entrée de journal, met à jour le cache et, à intervalle
       régulier, fige un instantané de compaction ;
    4. **commit** : journal, cache et instantané sont écrits ensemble ou pas du tout.

    L'identifiant de joueur du coup est toujours `str(user_id)` de l'appelant : un joueur agit sous
    sa propre identité, jamais sous un identifiant reçu du client.
    """
    maintenant = maintenant or _maintenant()
    params = params or {}
    auteur = joueur_id_de(user_id)
    action = Action(type=type, auteur=auteur, params=params)

    game = await _game_pour_participant(db, game_id, user_id, verrou=True)

    # (2) Idempotence / conflit — avant toute reconstruction coûteuse.
    if numero_attendu < game.current_numero:
        existante = (
            await db.execute(
                select(GameEvent).where(
                    GameEvent.game_id == game_id, GameEvent.numero == numero_attendu
                )
            )
        ).scalar_one()
        if _memes_actions(existante.action, action):
            etat, rng = await _reconstruire(db, game)
            return ResultatAction(
                numero=existante.numero,
                evenements=list(existante.evenements),
                empreinte=existante.empreinte,
                terminee=game.status != GAME_STATUS_EN_COURS,
                vainqueur_user_id=game.vainqueur_user_id,
                raison_fin=game.raison_fin,
                etat=etat_vers_json(etat),
                rejoue=True,
                rng_compteurs=rng.compteurs(),
                horloges=_adapt_horloges.restant_json(game.horloges, maintenant.timestamp()),
            )
        raise ConflitNumero(
            numero_attendu,
            game.current_numero,
            "ce numéro est déjà joué par une autre action (pas le même coup rejoué)",
        )
    if numero_attendu > game.current_numero:
        raise ConflitNumero(
            numero_attendu, game.current_numero, "numéro en avance (trou dans le journal)"
        )

    # Ici numero_attendu == game.current_numero : la partie doit être en cours.
    if game.status != GAME_STATUS_EN_COURS:
        raise PartieNonActive(
            f"Partie {game_id} au statut « {game.status} » : elle n'accepte plus d'action."
        )

    # (3) Reconstruire, valider par le moteur, journaliser.
    etat_courant, rng = await _reconstruire(db, game)
    try:
        etat2, evenements = appliquer(etat_courant, action, rng)
    except ValueError as exc:
        # Le serveur fait autorité : un coup illégal est refusé, l'état n'a pas bougé (rien n'a été
        # écrit, le `commit` est plus bas). On le trace, et on alerte si c'est une rafale.
        _journaliser_refus(game_id, user_id, type, str(exc), maintenant)
        raise ActionRefusee(str(exc)) from exc

    empr = empreinte(etat2)
    horodatage = maintenant.isoformat()
    entree = Entree(
        numero=game.current_numero,
        auteur=auteur,
        action=action,
        evenements=evenements,
        horodatage=horodatage,
        empreinte=empr,
    )
    brut = entree_vers_json(entree)
    db.add(
        GameEvent(
            game_id=game.id,
            numero=brut["numero"],
            auteur=brut["auteur"],
            action=brut["action"],
            evenements=brut["evenements"],
            horodatage=brut["horodatage"],
            empreinte=brut["empreinte"],
        )
    )

    game.current_numero += 1
    game.current_empreinte = empr
    game.last_action_at = maintenant
    game.expires_at = maintenant + DELAI_INACTIVITE
    if etat2.terminee:
        game.status = GAME_STATUS_TERMINEE
        game.vainqueur_user_id = uuid.UUID(etat2.vainqueur) if etat2.vainqueur else None
        game.raison_fin = etat2.raison_fin

    # Horloges (lot j-timer) : mises à jour selon la transition d'état observée, dans la même
    # transaction que le coup — donc reprises après un F5 (dans la partie, pas en mémoire).
    if game.horloges is not None:
        game.horloges = _adapt_horloges.transition_json(
            game.horloges, etat_courant, etat2, maintenant.timestamp()
        )

    # Compaction périodique : un instantané borne la queue à rejouer à la reprise.
    if intervalle_instantane > 0 and game.current_numero % intervalle_instantane == 0:
        db.add(
            _snapshot_row(
                game.id,
                Instantane(
                    numero_entrees=game.current_numero,
                    etat=etat2,
                    rng_etat=rng.etat(),
                    empreinte=empr,
                ),
            )
        )

    await db.commit()
    return ResultatAction(
        numero=entree.numero,
        evenements=[dict(e) for e in brut["evenements"]],
        empreinte=empr,
        terminee=etat2.terminee,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=etat2.raison_fin,
        etat=etat_vers_json(etat2),
        rejoue=False,
        rng_compteurs=rng.compteurs(),
        horloges=_adapt_horloges.restant_json(game.horloges, maintenant.timestamp()),
    )


# --- Expiration / purge ------------------------------------------------------


async def expirer_parties(db: AsyncSession, maintenant: datetime | None = None) -> int:
    """Fige les parties en cours inactives au-delà du délai (abandon silencieux). Renvoie le compte.

    Une partie ne reste jamais suspendue : faute d'activité, elle passe en `expiree`. Le compte est
    journalisé — un balayage qui n'aurait rien fait le **dit**, il ne reste pas muet.
    """
    maintenant = maintenant or _maintenant()
    resultat = await db.execute(
        update(Game)
        .where(Game.status == GAME_STATUS_EN_COURS, Game.expires_at < maintenant)
        .values(status=GAME_STATUS_EXPIREE)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    compte = resultat.rowcount or 0
    logger.info("expiration des parties abandonnées : %d partie(s) figée(s).", compte)
    return compte


async def purger(
    db: AsyncSession,
    maintenant: datetime | None = None,
    *,
    anciennete: timedelta = ANCIENNETE_PURGE,
) -> dict[str, int]:
    """Purge les parties mortes anciennes et les instantanés superflus, avec une métrique.

    * **Instantanés** : on ne garde que le plus récent par partie (le seul utile à la reprise) ;
      les plus anciens sont supprimés.
    * **Parties mortes** : terminées ou expirées et plus vieilles que `anciennete` → supprimées
      (le `ON DELETE CASCADE` emporte joueurs, journal et instantanés).

    Renvoie `{"instantanes_purges": …, "parties_purgees": …}` et le journalise : jamais une purge
    muette (on doit pouvoir expliquer ce qui a disparu).
    """
    maintenant = maintenant or _maintenant()

    # Instantanés superflus : tout sauf le plus récent (numero_entrees max) de **sa** partie. La
    # sous-requête corrèle sur le game_id de la ligne supprimée (alias), sans jointure à `games`.
    autre = aliased(GameSnapshot)
    max_de_la_partie = (
        select(func.max(autre.numero_entrees))
        .where(autre.game_id == GameSnapshot.game_id)
        .scalar_subquery()
    )
    instantanes = await db.execute(
        delete(GameSnapshot)
        .where(GameSnapshot.numero_entrees < max_de_la_partie)
        .execution_options(synchronize_session=False)
    )

    parties = await db.execute(
        delete(Game)
        .where(
            Game.status.in_((GAME_STATUS_TERMINEE, GAME_STATUS_EXPIREE)),
            Game.updated_at < maintenant - anciennete,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    metrique = {
        "instantanes_purges": instantanes.rowcount or 0,
        "parties_purgees": parties.rowcount or 0,
    }
    logger.info(
        "purge des parties : %d instantané(s) et %d partie(s) morte(s) supprimé(s).",
        metrique["instantanes_purges"],
        metrique["parties_purgees"],
    )
    return metrique


# --- Horloges : expiration et pause de déconnexion (lot j-timer) -------------


async def _game_sous_verrou(db: AsyncSession, game_id: uuid.UUID) -> Game | None:
    """Charge une partie sous verrou de ligne, par identifiant (chemin **système**, sans joueur)."""
    return (
        await db.execute(select(Game).where(Game.id == game_id).with_for_update())
    ).scalar_one_or_none()


async def expirer_horloge(
    db: AsyncSession, game_id: uuid.UUID, maintenant: datetime | None = None
) -> ResultatAction | None:
    """Applique l'action par défaut si une horloge a expiré ; renvoie le résultat, ou None.

    Pilotée par le serveur (appelée au gré des synchronisations et des battements de cœur), sous
    verrou de ligne comme un coup de joueur. Une pause de déconnexion dont la grâce est passée fait
    **reprendre** les horloges (sans coup). Sinon, une expiration journalise l'action par défaut :
    de tour, réponse par défaut d'une demande, ou défaite au temps) : **jamais un blocage** (critère
    d'acceptation). Renvoie ``None`` si rien n'a expiré, ou si la partie n'est pas en cours / sans
    horloges.
    """
    maintenant = maintenant or _maintenant()
    ts = maintenant.timestamp()
    game = await _game_sous_verrou(db, game_id)
    if game is None or game.status != GAME_STATUS_EN_COURS or game.horloges is None:
        return None
    if _adapt_horloges.pause_a_expire(game.horloges, ts):
        game.horloges = _adapt_horloges.reprendre_json(game.horloges, ts)
        await db.commit()
        return None
    decision = _adapt_horloges.action_par_defaut(game.horloges, ts)
    if decision is None:
        return None
    type_action, params = decision

    etat_courant, rng = await _reconstruire(db, game)
    action = Action(type=type_action, auteur=AUTEUR_SYSTEME, params=params)
    etat2, evenements = appliquer(etat_courant, action, rng)
    empr = empreinte(etat2)
    entree = Entree(
        numero=game.current_numero,
        auteur=AUTEUR_SYSTEME,
        action=action,
        evenements=evenements,
        horodatage=maintenant.isoformat(),
        empreinte=empr,
    )
    brut = entree_vers_json(entree)
    db.add(
        GameEvent(
            game_id=game.id,
            numero=brut["numero"],
            auteur=brut["auteur"],
            action=brut["action"],
            evenements=brut["evenements"],
            horodatage=brut["horodatage"],
            empreinte=brut["empreinte"],
        )
    )
    game.current_numero += 1
    game.current_empreinte = empr
    game.last_action_at = maintenant
    game.expires_at = maintenant + DELAI_INACTIVITE
    if etat2.terminee:
        game.status = GAME_STATUS_TERMINEE
        game.vainqueur_user_id = uuid.UUID(etat2.vainqueur) if etat2.vainqueur else None
        game.raison_fin = etat2.raison_fin
    game.horloges = _adapt_horloges.transition_json(game.horloges, etat_courant, etat2, ts)
    await db.commit()

    logger.info(
        "expiration d'horloge appliquée — partie %s, coup système « %s » au numéro %d.",
        game_id,
        type_action,
        entree.numero,
    )
    return ResultatAction(
        numero=entree.numero,
        evenements=[dict(e) for e in brut["evenements"]],
        empreinte=empr,
        terminee=etat2.terminee,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=etat2.raison_fin,
        etat=etat_vers_json(etat2),
        rejoue=False,
        rng_compteurs=rng.compteurs(),
        horloges=_adapt_horloges.restant_json(game.horloges, ts),
    )


async def marquer_deconnexion(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, maintenant: datetime | None = None
) -> None:
    """Gèle les horloges d'une partie à la déconnexion d'un joueur (pause de grâce, DJ4).

    Idempotente côté horloges (une pause déjà posée ne bouge pas) ; sans effet si la partie n'est
    pas en cours ou n'a pas d'horloges.
    """
    maintenant = maintenant or _maintenant()
    game = await _game_sous_verrou(db, game_id)
    if game is None or game.status != GAME_STATUS_EN_COURS or game.horloges is None:
        return
    game.horloges = _adapt_horloges.pause_json(
        game.horloges, joueur_id_de(user_id), maintenant.timestamp()
    )
    await db.commit()


async def marquer_reconnexion(
    db: AsyncSession, game_id: uuid.UUID, maintenant: datetime | None = None
) -> None:
    """Lève la pause à la reconnexion : les horloges reprennent là où elles s'étaient gelées."""
    maintenant = maintenant or _maintenant()
    game = await _game_sous_verrou(db, game_id)
    if game is None or game.status != GAME_STATUS_EN_COURS or game.horloges is None:
        return
    game.horloges = _adapt_horloges.reprendre_json(game.horloges, maintenant.timestamp())
    await db.commit()
