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
* :func:`abandonner_partie` — abandon volontaire d'un joueur (lot ``j-deconnexion-abandon``) ;
* :func:`expirer_horloge` — désertion (pause dépassée) ou action par défaut à une expiration ;
* :func:`expirer_parties` — clôt les parties fantômes (inactives au-delà du plafond) avec un motif
  **journalisé** (``j-deconnexion-abandon`` : jamais un nettoyage muet) ;
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

from pbm_game.actions import valider
from pbm_game.actions.familles_jeu import _fiches, familles_jeu
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
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_AVANCER_PHASE,
    ACTION_CHECKUP,
    ACTION_DEBUT_TOUR,
    ACTION_DESERTER,
    ACTION_EXPIRER_INACTIVITE,
    ACTION_MISE_EN_PLACE_INITIALE,
    AUTEUR_SYSTEME,
    Entree,
    Instantane,
)
from pbm_game.rng import GRAINE_MIN_OCTETS, Rng, engagement
from pbm_game.state.modele import PHASE_CHECKUP, PHASE_PIOCHE, EtatPartie
from pbm_game.state.serialisation import vers_json as etat_vers_json
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pbm_api.config import settings
from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
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

#: Une partie sans action depuis ce délai est une **partie fantôme** : :func:`expirer_parties` la
#: clôt pour inactivité. Chaque coup repousse l'échéance (``last_action_at`` + ce délai). Défaut de
#: repli si la configuration est absente ; le plafond réel vient des réglages
#: (:func:`_delai_inactivite`, ``settings.jeu_inactivite_plafond_h``) — critère « aucune partie ne
#: reste en cours plus longtemps que le plafond **configuré** » (lot ``j-deconnexion-abandon``).
DELAI_INACTIVITE = timedelta(days=3)

#: Une partie morte (terminée ou expirée) plus ancienne que ce délai est purgée (défaut de repli ;
#: le réel vient de ``settings.jeu_purge_anciennete_j``).
ANCIENNETE_PURGE = timedelta(days=30)


def _delai_inactivite() -> timedelta:
    """Le plafond d'inactivité, depuis la configuration (``settings.jeu_inactivite_plafond_h``).

    Lu à chaque appel plutôt que figé à l'import : un changement d'environnement s'applique sans
    redéployer. C'est le **plafond configuré** du critère d'acceptation — aucune partie ne reste en
    cours au-delà.
    """
    return timedelta(hours=settings.jeu_inactivite_plafond_h)


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
    entrainement: bool = False,
    bot_niveau: str | None = None,
) -> Game:
    """Crée une partie entre deux joueurs (chacun `(user_id, deck_id)`), ou **refuse**.

    Résout chaque deck en scripts : toute carte non jouable fait lever :class:`CartesNonJouables`
    avec la liste des cartes (D9 — jamais jouée de travers). Construit l'état initial, tire une
    graine d'aléatoire (le moteur est pur : la graine vient d'ici), et persiste `Game`, les deux
    `GamePlayer` et un `GameSnapshot` au coup 0. La graine est un **secret** (commit-reveal) : seul
    l'engagement est destiné à être publié.

    ``entrainement`` marque une partie d'**entraînement contre un bot** (lot `j-mode-solo`,
    DJ7) : elle entre dans l'historique mais ne compte pas. ``bot_niveau``, s'il est fourni,
    est posé sur le **siège 1** (``joueur_b``) : c'est lui, et lui seul, que le bot tient.
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
        entrainement=entrainement,
        last_action_at=maintenant,
        expires_at=maintenant + _delai_inactivite(),
        horloges=_adapt_horloges.etat_initial_json(
            _adapt_horloges.config_horloges(settings), etat_initial, maintenant.timestamp()
        ),
    )
    db.add(game)
    await db.flush()

    db.add_all(
        [
            GamePlayer(game_id=game.id, user_id=user_a, deck_id=deck_a, seat=0),
            GamePlayer(
                game_id=game.id, user_id=user_b, deck_id=deck_b, seat=1, bot_niveau=bot_niveau
            ),
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


def _jouable(etat: EtatPartie) -> bool:
    """Vrai si la partie est **en cours de jeu** (mise en place entamée ou partie commencée).

    Une partie « jouable » passe par le générateur de coups légaux (validation d'appartenance,
    orchestration des coups système). Une partie **brute** — decks en pioche, aucun Actif, aucune
    mise en place — ne l'est pas : c'est l'état juste après :func:`creer_partie`, avant
    :func:`demarrer_partie`. Le critère est observable sur l'état seul.
    """
    if etat.mise_en_place is not None:
        return True
    return any(j.actif is not None for j in etat.joueurs)


def _persister_coup(
    db: AsyncSession,
    game: Game,
    action: Action,
    etat_avant: EtatPartie,
    etat_apres: EtatPartie,
    evenements,
    maintenant: datetime,
    rng: Rng,
    intervalle: int,
) -> list[dict]:
    """Écrit un coup au journal et met à jour le cache de la partie — **sans commit**.

    Mutualise l'écriture d'un coup (joueur ou système) : entrée numérotée, avancée du cache (numéro,
    empreinte, échéance), statut terminal, horloges, et instantané de compaction périodique.
    L'appelant commit une fois tous les coups écrits. Renvoie les événements en JSON.
    """
    empr = empreinte(etat_apres)
    entree = Entree(
        numero=game.current_numero,
        auteur=action.auteur,
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
    game.expires_at = maintenant + _delai_inactivite()
    if etat_apres.terminee:
        game.status = GAME_STATUS_TERMINEE
        game.vainqueur_user_id = uuid.UUID(etat_apres.vainqueur) if etat_apres.vainqueur else None
        game.raison_fin = etat_apres.raison_fin
    if game.horloges is not None:
        game.horloges = _adapt_horloges.transition_json(
            game.horloges, etat_avant, etat_apres, maintenant.timestamp()
        )
    if intervalle > 0 and game.current_numero % intervalle == 0:
        db.add(
            _snapshot_row(
                game.id,
                Instantane(
                    numero_entrees=game.current_numero,
                    etat=etat_apres,
                    rng_etat=rng.etat(),
                    empreinte=empr,
                ),
            )
        )
    return [dict(e) for e in brut["evenements"]]


async def _piloter(
    db: AsyncSession,
    game: Game,
    etat: EtatPartie,
    rng: Rng,
    maintenant: datetime,
    catalogue,
    intervalle: int,
) -> tuple[EtatPartie, list[dict]]:
    """Enchaîne les coups **système** dus jusqu'à ce que la partie attende un joueur.

    Entre les tours, le serveur fait seul : la **pioche de début de tour** (``debut_tour``) en phase
    de pioche, le **Pokémon Checkup** puis le tour suivant (``checkup`` → ``avancer_phase``)
    en phase de checkup. Il s'arrête dès qu'un joueur doit agir (phase principale/attaque), qu'un
    placement est attendu (mise en place), ou que la partie est finie. Un garde-fou borne les
    enchaînements (jamais de boucle infinie).
    """
    evts: list[dict] = []
    for _ in range(100):
        if etat.terminee or etat.mise_en_place is not None:
            break
        phase = etat.tour.phase
        if phase == PHASE_PIOCHE:
            action = Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME)
        elif phase == PHASE_CHECKUP:
            action = Action(ACTION_CHECKUP, AUTEUR_SYSTEME, {"fiches": _fiches(catalogue, etat)})
        else:
            break  # phase principale / attaque : au joueur de jouer.
        etat2, evenements = appliquer(etat, action, rng)
        evts += _persister_coup(
            db, game, action, etat, etat2, evenements, maintenant, rng, intervalle
        )
        etat = etat2
        # Après le Checkup, passer au tour suivant si la partie continue (checkup → pioche).
        if phase == PHASE_CHECKUP and not etat.terminee:
            av = Action(ACTION_AVANCER_PHASE, AUTEUR_SYSTEME)
            etat2, evenements = appliquer(etat, av, rng)
            evts += _persister_coup(
                db, game, av, etat, etat2, evenements, maintenant, rng, intervalle
            )
            etat = etat2
    return etat, evts


async def demarrer_partie(
    db: AsyncSession, game: Game, maintenant: datetime | None = None
) -> None:
    """Lance la **mise en place** d'une partie fraîchement créée (R-4) — coup système journalisé.

    Appelée par le lancement après :func:`creer_partie` : applique ``mise_en_place_initiale``
    (mélange, pioche de sept, mulligans) depuis le catalogue de la partie, ce qui met l'état en
    attente du **placement** des joueurs (Actif + banc face cachée). Idempotente : rien si la
    mise en place est déjà entamée ou la partie commencée (``_jouable``).
    """
    maintenant = maintenant or _maintenant()
    etat, rng = await _reconstruire(db, game)
    if _jouable(etat):
        return
    catalogue = await construire_catalogue_jeu(db, etat)
    action = Action(
        ACTION_MISE_EN_PLACE_INITIALE, AUTEUR_SYSTEME, {"definitions": catalogue.definitions()}
    )
    etat2, evenements = appliquer(etat, action, rng)
    _persister_coup(
        db, game, action, etat, etat2, evenements, maintenant, rng, INTERVALLE_INSTANTANE
    )
    await db.commit()


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

    # (3) Reconstruire l'état courant et le Rng vivant.
    etat_courant, rng = await _reconstruire(db, game)

    # Une partie JOUABLE (mise en place en cours ou commencée) passe par le générateur de coups
    # légaux : le coup soumis DOIT appartenir à la liste que le moteur déclare (une seule source de
    # vérité), ce qui vaut anti-triche — un paramètre falsifié ne correspond à aucun coup légal. Une
    # partie « brute » (decks en pioche, avant mise en place) garde la voie mécanique directe, celle
    # qu'exercent les tests de plumberie (idempotence, reprise) avec des coups système.
    catalogue = None
    if _jouable(etat_courant):
        catalogue = await construire_catalogue_jeu(db, etat_courant)
        verdict = valider(etat_courant, action, familles=familles_jeu(catalogue))
        if verdict.refuse:
            motif = f"{verdict.message} ({verdict.regle})"
            _journaliser_refus(game_id, user_id, type, motif, maintenant)
            raise ActionRefusee(motif)

    try:
        etat2, evenements = appliquer(etat_courant, action, rng)
    except ValueError as exc:
        # Le serveur fait autorité : un coup illégal est refusé, l'état n'a pas bougé (rien n'est
        # écrit, le commit est plus bas). On le trace, et on alerte si c'est une rafale.
        _journaliser_refus(game_id, user_id, type, str(exc), maintenant)
        raise ActionRefusee(str(exc)) from exc

    numero_joueur = game.current_numero
    evts_json = _persister_coup(
        db, game, action, etat_courant, etat2, evenements, maintenant, rng, intervalle_instantane
    )
    etat_courant = etat2

    # Orchestration : après le coup d'un joueur, le serveur enchaîne les coups SYSTÈME dus
    # début de tour, Pokémon Checkup, passage au tour suivant) jusqu'à ce que la partie attende de
    # (pioche de début de tour, Checkup, tour suivant) jusqu'à ce qu'elle attende un joueur — tout
    # par le journal (lot ``j-coups-joueur``). Seules les parties jouables en ont besoin.
    if catalogue is not None and not etat_courant.terminee:
        etat_courant, evts_sys = await _piloter(
            db, game, etat_courant, rng, maintenant, catalogue, intervalle_instantane
        )
        evts_json += evts_sys

    # Mode solo : après le coup de l'humain, le bot d'entraînement joue son tour — il ne voit
    # que sa vue projetée, jamais l'état complet (lot `j-mode-solo`). Import local : le module
    # `bot` importe ce service, l'importer au chargement créerait un cycle.
    if game.entrainement and catalogue is not None and not etat_courant.terminee:
        from pbm_api.games.bot import boucle_bot_pour_partie

        etat_courant, evts_bot = await boucle_bot_pour_partie(
            db, game, etat_courant, rng, maintenant, catalogue, intervalle_instantane
        )
        evts_json += evts_bot

    await db.commit()
    return ResultatAction(
        numero=numero_joueur,
        evenements=evts_json,
        empreinte=game.current_empreinte,
        terminee=etat_courant.terminee,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=etat_courant.raison_fin,
        etat=etat_vers_json(etat_courant),
        rejoue=False,
        rng_compteurs=rng.compteurs(),
        horloges=_adapt_horloges.restant_json(game.horloges, maintenant.timestamp()),
    )


# --- Application journalisée d'un coup déjà construit (hors boucle de joueur) ----


async def _appliquer_coup(
    db: AsyncSession,
    game: Game,
    action: Action,
    maintenant: datetime,
    *,
    statut_termine: str,
) -> ResultatAction:
    """Reconstruit, rejoue une action **déjà construite** et la journalise, sous verrou. La partie
    doit être chargée ``with_for_update`` par l'appelant.

    Mutualise ce que partagent l'expiration d'horloge (lot ``j-timer``) et les trois clôtures de ce
    lot (abandon, désertion, inactivité) : reconstruire l'état courant, rejouer l'action par le
    moteur, écrire l'entrée de journal, mettre à jour le cache, l'échéance d'inactivité et les
    horloges, puis commit. L'action vient de l'appelant (système ou joueur) ; elle peut être
    **terminale** (abandon, désertion, défaite au temps, inactivité) ou non (fin de tour, réponse
    par défaut). Le statut ne change **que** si le moteur marque la partie terminée :
    ``statut_termine`` distingue alors une fin *méritée* (``terminee``) d'un ménage sans vainqueur
    (``expiree``). Une partie déjà terminée est refusée par le moteur (R-14.6), jamais clôturée
    deux fois en silence.
    """
    ts = maintenant.timestamp()
    etat_courant, rng = await _reconstruire(db, game)
    etat2, evenements = appliquer(etat_courant, action, rng)
    empr = empreinte(etat2)
    entree = Entree(
        numero=game.current_numero,
        auteur=action.auteur,
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
    game.expires_at = maintenant + _delai_inactivite()
    if etat2.terminee:
        game.status = statut_termine
        game.vainqueur_user_id = uuid.UUID(etat2.vainqueur) if etat2.vainqueur else None
        game.raison_fin = etat2.raison_fin
    if game.horloges is not None:
        game.horloges = _adapt_horloges.transition_json(game.horloges, etat_courant, etat2, ts)
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
        horloges=_adapt_horloges.restant_json(game.horloges, ts),
    )


async def abandonner_partie(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID, maintenant: datetime | None = None
) -> ResultatAction:
    """**Abandon volontaire** d'un joueur (R-14.3) : la partie se termine, l'adversaire gagne.

    Chemin dédié de l'« abandon explicite » du lot : un geste simple, sans numéro d'action à
    deviner (contrairement à :func:`appliquer_action`). Chargée sous verrou et **bornée au
    participant** (sinon :class:`PartieIntrouvable` → 404, pas de fuite d'existence). Une partie qui
    n'est plus en cours refuse l'abandon (:class:`PartieNonActive` → 409) : jamais clos deux fois.
    L'auteur est **toujours** le joueur de la session (jamais une identité reçue du client).
    """
    maintenant = maintenant or _maintenant()
    game = await _game_pour_participant(db, game_id, user_id, verrou=True)
    if game.status != GAME_STATUS_EN_COURS:
        raise PartieNonActive(
            f"Partie {game_id} au statut « {game.status} » : elle n'accepte plus d'abandon."
        )
    action = Action(type=ACTION_ABANDONNER, auteur=joueur_id_de(user_id), params={})
    resultat = await _appliquer_coup(
        db, game, action, maintenant, statut_termine=GAME_STATUS_TERMINEE
    )
    logger.info("abandon volontaire — partie %s, joueur %s.", game_id, user_id)
    return resultat


# --- Expiration / purge ------------------------------------------------------


async def expirer_parties(db: AsyncSession, maintenant: datetime | None = None) -> int:
    """Clôt les parties fantômes (inactives au-delà du plafond) **avec un motif journalisé**.

    Une partie ne reste jamais suspendue : faute d'activité au-delà de ``expires_at``, elle est
    close pour inactivité (statut `expiree`, raison `inactivite`, **aucun** vainqueur — personne n'a
    joué). Chaque clôture est un **coup journalisé** (transition système ``expirer_inactivite``),
    pas un simple changement de statut : l'historique porte son motif, et « tout est rejouable »
    tient (critère « chaque clôture automatique porte son motif dans le journal et dans
    l'historique », risque nommé : le nettoyage silencieux). On clôt une partie à la fois, sous
    verrou de ligne, pour ne pas heurter un coup concurrent. Renvoie le compte, et le journalise.
    """
    maintenant = maintenant or _maintenant()
    ids = (
        await db.execute(
            select(Game.id).where(
                Game.status == GAME_STATUS_EN_COURS, Game.expires_at < maintenant
            )
        )
    ).scalars().all()

    compte = 0
    for game_id in ids:
        game = await _game_sous_verrou(db, game_id)
        # Re-contrôle sous verrou : un coup concurrent a pu la ranimer (nouvelle échéance) ou la
        # clore entre-temps. On ne force rien dans ce cas — jamais une clôture « de mémoire ».
        if game is None or game.status != GAME_STATUS_EN_COURS or game.expires_at >= maintenant:
            await db.rollback()
            continue
        action = Action(type=ACTION_EXPIRER_INACTIVITE, auteur=AUTEUR_SYSTEME, params={})
        await _appliquer_coup(
            db, game, action, maintenant, statut_termine=GAME_STATUS_EXPIREE
        )
        compte += 1

    logger.info("expiration des parties fantômes : %d partie(s) close(s) pour inactivité.", compte)
    return compte


async def purger(
    db: AsyncSession,
    maintenant: datetime | None = None,
    *,
    anciennete: timedelta | None = None,
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
    if anciennete is None:
        anciennete = timedelta(days=settings.jeu_purge_anciennete_j)

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
    """Résout une horloge expirée : **désertion** d'une pause dépassée, sinon action par défaut.

    Pilotée par le serveur (appelée au gré des synchronisations et des battements de cœur), sous
    verrou de ligne comme un coup de joueur :

    * une **pause de déconnexion dont la grâce est passée** devient une **désertion** (lot
      ``j-deconnexion-abandon``) : le joueur déconnecté qui n'est pas revenu perd par forfait, coup
      système ``deserter`` journalisé, l'adversaire gagne. C'est l'affinement de ``j-timer``, qui se
      contentait de reprendre les horloges : la partie ne reste pas suspendue le temps que le
      budget du déserteur s'épuise, elle se clôt dès la fin du délai de grâce annoncé ;
    * sinon, une expiration journalise l'**action par défaut** (fin de tour, réponse par défaut
      d'une demande, ou défaite au temps — DJ4) : **jamais un blocage** (critère d'acceptation).

    Renvoie ``None`` si rien n'a expiré, ou si la partie n'est pas en cours / sans horloges.
    """
    maintenant = maintenant or _maintenant()
    ts = maintenant.timestamp()
    game = await _game_sous_verrou(db, game_id)
    if game is None or game.status != GAME_STATUS_EN_COURS or game.horloges is None:
        return None

    # Pause dépassée → désertion (forfait du joueur qui ne revient pas). Le déserteur est nommé
    # depuis l'état des horloges (celui dont la déconnexion a posé la pause), jamais « de mémoire ».
    if _adapt_horloges.pause_a_expire(game.horloges, ts):
        deserteur = _adapt_horloges.joueur_en_pause(game.horloges)
        if deserteur is None:  # garde : pause_a_expire implique un joueur en pause
            return None
        action = Action(type=ACTION_DESERTER, auteur=AUTEUR_SYSTEME, params={"joueur": deserteur})
        resultat = await _appliquer_coup(
            db, game, action, maintenant, statut_termine=GAME_STATUS_TERMINEE
        )
        logger.info(
            "désertion — partie %s, le joueur %s n'est pas revenu avant la fin de la grâce ; "
            "forfait au numéro %d.",
            game_id,
            deserteur,
            resultat.numero,
        )
        return resultat

    decision = _adapt_horloges.action_par_defaut(game.horloges, ts)
    if decision is None:
        return None
    type_action, params = decision
    action = Action(type=type_action, auteur=AUTEUR_SYSTEME, params=params)
    resultat = await _appliquer_coup(
        db, game, action, maintenant, statut_termine=GAME_STATUS_TERMINEE
    )
    logger.info(
        "expiration d'horloge appliquée — partie %s, coup système « %s » au numéro %d.",
        game_id,
        type_action,
        resultat.numero,
    )
    return resultat


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
