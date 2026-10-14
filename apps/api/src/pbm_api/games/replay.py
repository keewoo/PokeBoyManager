"""Replay d'une partie **finie** : la revoir coup par coup, et l'ouvrir à qui on veut.

Lot ``j-replay`` (jalon J4 — « la partie laisse une trace »). Le journal existe déjà ; ce module
n'invente rien, il **ouvre une fenêtre dessus** — et c'est tout l'enjeu : servir un journal, c'est
servir ce que les joueurs savaient, donc le filtrage n'est pas une option.

Trois décisions portent ce module, et chacune ferme un risque nommé du lot.

1. **Une partie en cours n'a pas de replay.** Pas « un replay tronqué », pas « un replay sans les
   zones cachées » : *pas de replay* (409). Le risque du lot est écrit noir sur blanc — « servir le
   journal complet d'une partie en cours sous prétexte de replay : c'est la fuite d'information la
   plus facile à commettre ». Une porte qui ne s'ouvre qu'après la fin ne peut pas fuiter pendant.

2. **La vue complète reste une vue projetée.** Le moteur n'a **aucune** sortie « tout voir »
   (:func:`pbm_game.sortie.projeter` exige un joueur destinataire, et :func:`vue` refuse un
   inconnu) — et on n'en ajoute pas une : ce serait fabriquer, pour le replay, le chemin brut que
   le lot ``j-autorite-vues`` a justement supprimé, en espérant qu'aucune route ne s'y trompe
   jamais. « Vue complète » veut donc dire : **les deux vues de joueur**, celle de chacun, servies
   ensemble une fois la partie finie. Ce que les deux joueurs ont su, on peut le rendre ; ce que
   ni l'un ni l'autre n'a jamais su (l'ordre du reste de la pioche) n'a pas à l'être.

3. **Le droit de regarder vit en base, pas dans l'URL.** Voir
   :class:`~pbm_api.models.GameReplayShare`.

Le replay se **pagine** (``depuis``/``limite``) : une partie de quatre cents coups, c'est quatre
cents états projetés deux fois, et on ne les met pas dans une réponse. La page dit toujours son
``total`` et si elle est ``complet`` — jamais de troncature muette : le client enchaîne les pages
jusqu'au bout, et l'écran sait dire ce qu'il n'a pas encore.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator

from pbm_game.journal import Etape, etapes
from pbm_game.sortie import (
    enrichir_demande,
    enrichir_indicateurs,
    projeter,
    refs_demande,
    refs_en_jeu,
)
from pbm_game.state.modele import EtatPartie
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import GameError, PartieIntrouvable
from pbm_api.games.indicateurs import CatalogueAffichage, catalogue_affichage
from pbm_api.games.service import _dernier_instantane, _entrees_queue
from pbm_api.models import (
    GAME_STATUS_EN_COURS,
    GAME_STATUS_TERMINEE,
    Game,
    GamePlayer,
    GameReplayShare,
    User,
)

#: Vue d'un seul joueur : ce que **moi** j'ai vu de la partie. Réservée aux deux joueurs.
VUE_MOI = "moi"
#: Vue complète : les deux vues de joueur, servies ensemble (voir l'en-tête du module).
VUE_COMPLETE = "complete"
#: Les vues reconnues. Une valeur hors de cet ensemble est refusée, jamais repliée sur un défaut.
VUES: frozenset[str] = frozenset({VUE_MOI, VUE_COMPLETE})

#: Nombre de rangs servis par page quand le client ne demande rien.
LIMITE_DEFAUT = 100
#: Plafond dur par page. Au-delà, on refuse la valeur plutôt que de la rogner en silence : un
#: client qui croit avoir demandé mille rangs et n'en reçoit que deux cent cinquante en déduirait
#: que la partie est finie à ce rang-là.
LIMITE_MAX = 250


class ReplayPartieEnCours(GameError):
    """Replay demandé sur une partie encore en cours → 409. Le risque nommé du lot."""


class VueInconnue(GameError):
    """Vue demandée hors de :data:`VUES` → 422 (jamais repliée sur un défaut)."""


class VueMoiHorsParticipant(GameError):
    """``vue=moi`` demandée par un spectateur → 422 : il n'a pas de siège, donc pas de « moi »."""


class DestinatairePartageIntrouvable(GameError):
    """Aucun **compte invité** ne porte ce pseudo → 404 (pas de fuite sur les comptes)."""


class AutoPartage(GameError):
    """Partager avec soi-même, ou avec l'autre joueur : ils y ont déjà droit → 422."""


# --- Accès -------------------------------------------------------------------


async def _sieges(db: AsyncSession, game_id: uuid.UUID) -> list[GamePlayer]:
    """Les sièges de la partie, dans l'ordre (``seat`` 0 puis 1)."""
    rows = await db.execute(
        select(GamePlayer).where(GamePlayer.game_id == game_id).order_by(GamePlayer.seat)
    )
    return list(rows.scalars().all())


async def _partage_ouvert(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Vrai si un joueur a ouvert le replay de cette partie à ``user_id``."""
    row = await db.execute(
        select(GameReplayShare.id).where(
            GameReplayShare.game_id == game_id, GameReplayShare.user_id == user_id
        )
    )
    return row.first() is not None


async def game_pour_spectateur(
    db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Game, list[GamePlayer], bool]:
    """Charge la partie si ``user_id`` a le droit d'en voir le replay, sinon lève.

    Le droit, c'est **participer** à la partie ou s'être vu **ouvrir** son replay
    (:class:`~pbm_api.models.GameReplayShare`). Tout le reste —  partie inexistante, partie
    d'autres joueurs, partage retiré — lève :class:`PartieIntrouvable` (→ 404, jamais 403) : pour
    un compte non autorisé, ce replay n'existe pas.

    Renvoie ``(partie, sièges, participe)`` : les sièges servent à nommer les joueurs et à
    résoudre les destinataires de projection, et ``participe`` distingue un joueur d'un spectateur
    (seul un joueur a un « moi » à regarder, et seul un joueur gère les partages).
    """
    game = (await db.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if game is None:
        raise PartieIntrouvable(f"Partie {game_id} introuvable.")
    sieges = await _sieges(db, game_id)
    participe = any(s.user_id == user_id for s in sieges)
    if not participe and not await _partage_ouvert(db, game_id, user_id):
        raise PartieIntrouvable(f"Partie {game_id} introuvable.")
    return game, sieges, participe


# --- Composition du replay ---------------------------------------------------


def _destinataires(
    sieges: Iterable[GamePlayer], *, vue: str, user_id: uuid.UUID, participe: bool
) -> list[str]:
    """Les identifiants de joueur du moteur pour lesquels projeter chaque rang.

    ``vue=moi`` → le seul siège de l'utilisateur ; ``vue=complete`` → les deux. Un spectateur qui
    demande ``moi`` est refusé (il n'a pas de siège) plutôt que servi en vue complète : un repli
    silencieux lui donnerait **plus** que ce qu'il a demandé, et personne ne le saurait.
    """
    if vue not in VUES:
        raise VueInconnue(f"Vue de replay inconnue : « {vue} » (attendu : {sorted(VUES)}).")
    if vue == VUE_COMPLETE:
        return [joueur_id_de(s.user_id) for s in sieges]
    if not participe:
        raise VueMoiHorsParticipant(
            "Vous ne jouez pas cette partie : demandez la vue complète (« complete »)."
        )
    return [joueur_id_de(user_id)]


async def _catalogue_des_etapes(
    db: AsyncSession, etats: Iterable[EtatPartie]
) -> CatalogueAffichage:
    """Un **seul** catalogue d'affichage pour tous les rangs d'une page.

    Les indicateurs du plateau (PV imprimés, type des énergies, noms des options d'une demande)
    se lisent dans le catalogue. Les demander rang par rang, c'est une requête par coup ; on
    rassemble donc les références de tous les états de la page et on interroge une fois.
    """
    refs: set[str] = set()
    for etat in etats:
        refs |= refs_en_jeu(etat) | refs_demande(etat)
    return await catalogue_affichage(db, refs)


def _vue_du_rang(
    etape: Etape, destinataire: str, catalogue: CatalogueAffichage
) -> dict:
    """La vue projetée d'un rang pour un destinataire, enrichie comme celle du plateau.

    Même point de sortie que la partie en direct (:func:`pbm_game.sortie.projeter`), donc mêmes
    règles de visibilité. Deux différences, volontaires :

    * **aucun jetonneur** — les jetons opaques servent à *désigner* une carte cachée (choisir une
      récompense) ; dans un replay il n'y a rien à désigner, donc rien à exposer ;
    * **aucune action légale** — un rang de replay n'est pas un tour de jeu. Les calculer
      donnerait à l'écran des coups cliquables sur une partie finie, et coûterait le catalogue de
      jeu à chaque rang pour un résultat que personne ne doit utiliser.
    """
    sortie = projeter(etape.etat, etape.evenements, pour=destinataire)
    enrichir_indicateurs(
        sortie["vue"],
        etape.etat,
        pv_imprimes=catalogue.pv_imprimes,
        types=catalogue.types,
        registre=catalogue.registre,
    )
    enrichir_demande(sortie["vue"], etape.etat, noms=catalogue.noms, types=catalogue.types)
    return sortie


def _coup_json(etape: Etape) -> dict | None:
    """Le coup qui a mené à ce rang, en **faits publics** : qui, quoi, quand, et son empreinte.

    Les ``params`` de l'action ne sont **pas** renvoyés : ils peuvent nommer une carte d'une zone
    cachée (répondre à une demande en désignant une carte de sa main), et le détail de ce qui s'est
    passé voyage déjà, filtré par destinataire, dans les ``evenements``. On garde l'empreinte :
    c'est ce qui permet à un lecteur de recalculer et de vérifier que le replay ne ment pas.
    """
    entree = etape.entree
    if entree is None:
        return None
    return {
        "numero": entree.numero,
        "auteur": entree.auteur,
        "type": entree.action.type,
        "horodatage": entree.horodatage,
        "empreinte": entree.empreinte,
    }


def _tranche(iterateur: Iterator[Etape], depuis: int, limite: int) -> list[Etape]:
    """Les ``limite`` rangs à partir du rang ``depuis``, en consommant l'itérateur paresseux.

    Les rangs d'avant ``depuis`` sont tout de même **rejoués** (c'est ce qui vérifie les
    empreintes du chemin), mais pas gardés : on part du dernier instantané qui précède ``depuis``,
    donc ce rejeu reste court.
    """
    gardes: list[Etape] = []
    for etape in iterateur:
        if etape.rang < depuis:
            continue
        gardes.append(etape)
        if len(gardes) >= limite:
            break
    return gardes


async def composer_replay(
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    vue: str = VUE_MOI,
    depuis: int = 0,
    limite: int = LIMITE_DEFAUT,
) -> dict:
    """Le replay d'une partie finie : une page de rangs, chacun avec son état projeté.

    Lève :class:`PartieIntrouvable` (404) si l'utilisateur n'a pas le droit de regarder,
    :class:`ReplayPartieEnCours` (409) si la partie n'est pas finie, :class:`VueInconnue` /
    :class:`VueMoiHorsParticipant` (422) sur une vue impossible, et ``ValueError`` sur une
    pagination hors bornes.

    La **graine** d'aléatoire n'accompagne la réponse que pour une partie terminée par les règles
    (comme :mod:`pbm_api.games.lancement` la révèle déjà) : c'est le volet « reveal » du
    commit-reveal, ce qui rend le replay vérifiable de bout en bout. Une partie close pour
    inactivité ne la révèle pas — elle n'a pas été jouée jusqu'au bout.
    """
    game, sieges, participe = await game_pour_spectateur(db, game_id, user_id)
    if game.status == GAME_STATUS_EN_COURS:
        raise ReplayPartieEnCours(
            f"Partie {game_id} encore en cours : son replay ne s'ouvre qu'à la fin."
        )
    destinataires = _destinataires(sieges, vue=vue, user_id=user_id, participe=participe)

    total = game.current_numero
    if not isinstance(depuis, int) or not (0 <= depuis <= total):
        raise ValueError(f"« depuis » hors bornes : {depuis!r} (attendu 0..{total}).")
    if not isinstance(limite, int) or not (1 <= limite <= LIMITE_MAX):
        raise ValueError(f"« limite » hors bornes : {limite!r} (attendu 1..{LIMITE_MAX}).")

    # Point de départ : le dernier instantané qui précède `depuis`, puis la queue du journal.
    # C'est la même mécanique que la reprise d'une partie — un replay ne lit pas autre chose
    # que ce que le serveur lit pour jouer.
    instantane = await _dernier_instantane(db, game.id, depuis)
    queue = await _entrees_queue(db, game.id, instantane.numero_entrees, total)
    rangs = _tranche(iter(etapes(instantane, queue)), depuis, limite)

    catalogue = await _catalogue_des_etapes(db, [e.etat for e in rangs])
    pseudos = await _pseudos(db, [s.user_id for s in sieges])

    etapes_json = []
    for etape in rangs:
        projections = {d: _vue_du_rang(etape, d, catalogue) for d in destinataires}
        etapes_json.append(
            {
                "rang": etape.rang,
                "coup": _coup_json(etape),
                "vues": {d: p["vue"] for d, p in projections.items()},
                "evenements": {d: p["evenements"] for d, p in projections.items()},
            }
        )

    dernier_rang_servi = depuis + len(rangs) - 1 if rangs else depuis
    return {
        "game_id": str(game.id),
        "statut": game.status,
        "raison_fin": game.raison_fin,
        "vainqueur_user_id": (
            str(game.vainqueur_user_id) if game.vainqueur_user_id is not None else None
        ),
        "engagement": game.engagement,
        # Volet « reveal » du commit-reveal, pour une partie allée à son terme (voir docstring).
        "graine": game.graine if game.status == GAME_STATUS_TERMINEE else None,
        "vue": vue,
        "joueurs": [
            {
                "seat": s.seat,
                "user_id": str(s.user_id),
                "joueur_id": joueur_id_de(s.user_id),
                "pseudo": pseudos.get(s.user_id),
                "bot_niveau": s.bot_niveau,
            }
            for s in sieges
        ],
        "total": total,
        "depuis": depuis,
        "limite": limite,
        # `total` coups = `total + 1` rangs (le rang 0 est l'état d'avant le premier coup).
        "complet": dernier_rang_servi >= total,
        "etapes": etapes_json,
    }


async def _pseudos(
    db: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """Les pseudos des comptes donnés, pour nommer les joueurs à l'écran (une requête)."""
    ids = list(user_ids)
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.pseudo).where(User.id.in_(ids)))
    return {uid: pseudo for uid, pseudo in rows.all()}


# --- Partage -----------------------------------------------------------------


async def _game_pour_joueur(db: AsyncSession, game_id: uuid.UUID, user_id: uuid.UUID) -> Game:
    """Charge la partie si ``user_id`` y **joue**, sinon :class:`PartieIntrouvable` (404)."""
    game, _sieges_, participe = await game_pour_spectateur(db, game_id, user_id)
    if not participe:
        # Un spectateur ne gère pas les partages d'une partie qui n'est pas la sienne. On ne le
        # distingue pas d'une partie inexistante : il n'a pas à apprendre qu'il y a là un réglage.
        raise PartieIntrouvable(f"Partie {game_id} introuvable.")
    return game


async def ouvrir_partage(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID, pseudo: str
) -> GameReplayShare:
    """Ouvre le replay de la partie à un **compte invité** désigné par son pseudo.

    Réservé aux deux joueurs (:class:`PartieIntrouvable` sinon). Refuse un pseudo qui n'est pas
    celui d'un compte invité (:class:`DestinatairePartageIntrouvable`, 404 — on ne révèle pas
    l'existence d'un compte ordinaire), et refuse de « partager » avec l'un des deux joueurs
    (:class:`AutoPartage`, 422 : ils y ont déjà droit, l'ajouter laisserait croire que le droit
    vient de là et qu'on peut le retirer).

    Idempotent : rouvrir un partage déjà ouvert rend la ligne existante sans rien dupliquer.
    """
    game = await _game_pour_joueur(db, game_id, user_id)
    sieges = await _sieges(db, game.id)

    cible = (
        await db.execute(select(User).where(func.lower(User.pseudo) == pseudo.strip().lower()))
    ).scalar_one_or_none()
    if cible is None or not cible.game_access:
        raise DestinatairePartageIntrouvable(
            f"Aucun joueur invité ne porte le pseudo « {pseudo} »."
        )
    if any(s.user_id == cible.id for s in sieges):
        raise AutoPartage(
            "Ce compte joue cette partie : il voit déjà son replay, rien à partager."
        )

    existant = (
        await db.execute(
            select(GameReplayShare).where(
                GameReplayShare.game_id == game.id, GameReplayShare.user_id == cible.id
            )
        )
    ).scalar_one_or_none()
    if existant is not None:
        return existant

    partage = GameReplayShare(
        game_id=game.id, user_id=cible.id, created_by_user_id=user_id
    )
    db.add(partage)
    await db.flush()
    return partage


async def partages(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID
) -> list[dict]:
    """Les comptes à qui le replay est ouvert, pour que le joueur voie ce qu'il a partagé.

    Réservé aux deux joueurs : un partage qu'on ne peut pas relire est un partage qu'on ne pense
    pas à fermer.
    """
    game = await _game_pour_joueur(db, game_id, user_id)
    rows = (
        await db.execute(
            select(GameReplayShare, User.pseudo)
            .join(User, User.id == GameReplayShare.user_id)
            .where(GameReplayShare.game_id == game.id)
            .order_by(GameReplayShare.created_at)
        )
    ).all()
    return [
        {
            "user_id": str(partage.user_id),
            "pseudo": pseudo,
            "partage_par_user_id": str(partage.created_by_user_id),
            "created_at": partage.created_at,
        }
        for partage, pseudo in rows
    ]


async def fermer_partage(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID, cible_user_id: uuid.UUID
) -> bool:
    """Retire le droit de regarder le replay à ``cible_user_id``. Vrai si une ligne est tombée.

    Réservé aux deux joueurs. Rend ``False`` quand il n'y avait rien à retirer — l'appelant en
    fait un 404, sans prétendre avoir fermé un partage qui n'existait pas.
    """
    game = await _game_pour_joueur(db, game_id, user_id)
    res = await db.execute(
        delete(GameReplayShare).where(
            GameReplayShare.game_id == game.id, GameReplayShare.user_id == cible_user_id
        )
    )
    await db.flush()
    return bool(res.rowcount)


__all__ = [
    "VUE_MOI",
    "VUE_COMPLETE",
    "VUES",
    "LIMITE_DEFAUT",
    "LIMITE_MAX",
    "ReplayPartieEnCours",
    "VueInconnue",
    "VueMoiHorsParticipant",
    "DestinatairePartageIntrouvable",
    "AutoPartage",
    "game_pour_spectateur",
    "composer_replay",
    "ouvrir_partage",
    "partages",
    "fermer_partage",
]
