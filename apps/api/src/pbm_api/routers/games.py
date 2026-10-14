"""Routes de lecture des parties (lot `j-partie-service`) : lister ses parties, en consulter une.

Ce lot pose l'**enveloppe** de persistance d'une partie ; son API HTTP ici se limite à la lecture,
toujours **bornée au participant** : une partie à laquelle l'utilisateur ne joue pas répond 404
(jamais 403 — pas de fuite d'existence, comme les decks). La création d'une partie (choix du deck,
adversaire, tirage au sort) est le lot `j-lancement-partie` ; appliquer un coup, `j-autorite-vues` ;
sa diffusion temps réel, `j-temps-reel` (canal WebSocket + repli HTTP, `routers/games_ws.py`).
On ne les approxime pas ici.

Le **replay** d'une partie finie (lot `j-replay`) vit aussi ici, sous `/{game_id}/replay` : il est
le seul accès que des comptes **non participants** peuvent avoir à une partie, et seulement si un
joueur le leur a ouvert — toute la mécanique, et pourquoi elle est bâtie ainsi, est dans
`pbm_api.games.replay`.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pbm_game.state.serialisation import depuis_json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.adversaire_ia import MAX_APPELS_PAR_PARTIE
from pbm_api.games.bot import CleIAIndisponible, NiveauBotInconnu
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.coach import (
    BilanIndisponible,
    CleCoachIndisponible,
    CoachDesactive,
    ConseilHorsEntrainement,
    PartieNonTerminee,
    PlafondConseils,
    bilan_de_partie,
    conseil_pour_joueur,
)
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable
from pbm_api.games.errors import (
    ActionRefusee,
    CartesNonJouables,
    ConflitNumero,
    PartieIntrouvable,
    PartieNonActive,
    PlafondPartiesAtteint,
)
from pbm_api.games.indicateurs import catalogue_pour_etat, catalogue_pour_resultat
from pbm_api.games.projection import projeter_resultat, vue_autoritaire
from pbm_api.games.recapitulatif import RecapPartieEnCours, recapitulatif_de_partie
from pbm_api.games.replay import (
    LIMITE_DEFAUT,
    LIMITE_MAX,
    VUE_MOI,
    AutoPartage,
    DestinatairePartageIntrouvable,
    ReplayPartieEnCours,
    VueInconnue,
    VueMoiHorsParticipant,
    composer_replay,
    fermer_partage,
    ouvrir_partage,
    partages,
)
from pbm_api.games.revanche import (
    JoueurDejaEnPartie,
    RevanchePartieEnCours,
    SiegeSansDeck,
    creer_revanche,
)
from pbm_api.games.schemas import (
    ActionIn,
    BilanOut,
    ConseilOut,
    CoupConseille,
    GameDetailOut,
    GamePlayerOut,
    GameSummaryOut,
    IaCoutOut,
    MomentBilanOut,
    PartageReplayIn,
    PartageReplayOut,
    RecapitulatifOut,
    RevancheOut,
)
from pbm_api.games.service import (
    _game_pour_participant,
    abandonner_partie,
    appliquer_action,
    parties_du_joueur,
    reprendre_partie,
)
from pbm_api.games.temps_reel import HUB
from pbm_api.models import GamePlayer, User
from pbm_api.routers.capacite_http import erreur_capacite

router = APIRouter(prefix="/games", tags=["games"])

GAME_NOT_FOUND_MESSAGE = "Partie introuvable."


@router.get("", response_model=list[GameSummaryOut])
async def list_games(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> list[GameSummaryOut]:
    """Les parties du joueur courant, de la plus récente à la plus ancienne."""
    games = await parties_du_joueur(db, current_user.id)
    return [GameSummaryOut.model_validate(g, from_attributes=True) for g in games]


@router.get("/{game_id}", response_model=GameDetailOut)
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> GameDetailOut:
    """Le détail d'une partie du joueur courant, ou 404 s'il n'y participe pas (pas de fuite)."""
    try:
        game = await _game_pour_participant(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc

    players = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id).order_by(GamePlayer.seat)
        )
    ).scalars().all()

    # Coût estimé de l'adversaire IA (lot j-adversaire-ia) : présent seulement quand un siège est
    # tenu par l'IA du joueur. Compteurs réels de la partie ; le prix en euros reste à faire.
    ia_cout = None
    if any(p.adversaire_ia for p in players):
        ia_cout = IaCoutOut(
            appels=game.ia_appels,
            jetons=game.ia_tokens,
            plafond_appels=MAX_APPELS_PAR_PARTIE,
        )

    # Construction explicite (le `Game` ORM ne porte pas `players`) : on assemble le résumé et on
    # y greffe les sièges chargés à part.
    return GameDetailOut(
        id=game.id,
        status=game.status,
        current_numero=game.current_numero,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=game.raison_fin,
        created_at=game.created_at,
        updated_at=game.updated_at,
        entrainement=game.entrainement,
        engagement=game.engagement,
        journal_version=game.journal_version,
        players=[GamePlayerOut.model_validate(p, from_attributes=True) for p in players],
        ia_cout=ia_cout,
    )


@router.get("/{game_id}/state")
async def get_game_state(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """La **vue autoritaire** de la partie pour le joueur courant, ou 404 s'il n'y participe pas.

    Le client reçoit exclusivement ce que le serveur autorise (`pbm_game.sortie.projeter` via
    :func:`vue_autoritaire`) : jamais la main adverse, ni l'ordre d'une pioche, ni l'identité d'une
    récompense. L'état est reconstruit depuis le journal (« tout est rejouable »), empreinte
    vérifiée. Le secret d'aléatoire n'apparaît jamais, seuls les jetons opaques en dérivent.
    """
    try:
        game = await _game_pour_participant(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    etat, rng = await reprendre_partie(db, game)
    catalogue = await catalogue_pour_etat(db, etat, game_id=game_id)
    catalogue_jeu = await construire_catalogue_jeu(db, etat)
    vue = vue_autoritaire(
        etat, rng, user_id=current_user.id, graine_hex=game.graine,
        catalogue=catalogue, catalogue_jeu=catalogue_jeu,
    )
    vue["horloges"] = _adapt_horloges.restant_json(game.horloges, datetime.now(UTC).timestamp())
    # Numéro d'action courant (prochain attendu) : clé d'idempotence côté client pour soumettre
    # un coup (lot ``j-plateau-interactions``).
    vue["numero"] = game.current_numero
    return vue


@router.post("/{game_id}/actions")
async def play_action(
    game_id: uuid.UUID,
    body: ActionIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """Jouer un coup : le serveur fait autorité — il rejoue et valide, puis renvoie la vue projetée.

    L'auteur du coup est **toujours** le joueur de la session (`appliquer_action` l'impose) : un
    client ne peut pas agir sous une autre identité. Un coup illégal est refusé (422) avec le motif
    du moteur, **sans jamais altérer l'état** ; un conflit de numéro ou une partie close → 409. En
    retour, la vue autoritaire du joueur courant après le coup et les événements qui le concernent —
    jamais l'état brut, qui porte l'information cachée.

    Après un coup réel (non rejeu), le résultat est **diffusé** sur le canal temps réel (`HUB`) :
    chaque joueur abonné le reçoit projeté pour lui. Le journal reste la source de vérité — la
    diffusion est un raccourci de latence, pas la garantie de livraison (celle-ci tient à la
    resynchronisation par numéro, lot `j-temps-reel`).
    """
    try:
        resultat = await appliquer_action(
            db,
            game_id=game_id,
            user_id=current_user.id,
            type=body.type,
            params=body.params,
            numero_attendu=body.numero_attendu,
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except ActionRefusee as exc:
        # 422 en clair : le nom du constant `HTTP_422_*` a changé entre versions de Starlette
        # (ENTITY → CONTENT) ; le code numérique, lui, est stable et sans avertissement.
        raise HTTPException(422, str(exc)) from exc
    except (ConflitNumero, PartieNonActive) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    # `appliquer_action` a commité ; on relit la partie pour sa graine (secret serveur, jamais
    # renvoyé — seuls les jetons opaques en dérivent) et pour re-vérifier la participation.
    game = await _game_pour_participant(db, game_id, current_user.id)
    catalogue = await catalogue_pour_resultat(db, resultat, game_id=game_id)
    catalogue_jeu = await construire_catalogue_jeu(db, depuis_json(resultat.etat))
    HUB.publier(
        game_id, resultat, graine_hex=game.graine, catalogue=catalogue, catalogue_jeu=catalogue_jeu
    )
    reponse = projeter_resultat(
        resultat, user_id=current_user.id, graine_hex=game.graine, catalogue=catalogue,
        catalogue_jeu=catalogue_jeu,
    )
    # Le prochain numéro d'action attendu, pour que le client enchaîne un coup suivant sans aller
    # relire l'état (lot ``j-plateau-interactions``).
    reponse["numero"] = game.current_numero
    return reponse


@router.post("/{game_id}/abandon")
async def abandon_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """Abandonner explicitement la partie (R-14.3) : forfait du joueur courant, l'adversaire gagne.

    Chemin dédié de l'« abandon explicite » du lot ``j-deconnexion-abandon`` — plus simple que
    :func:`play_action` (aucun ``numero_attendu`` à fournir : abandonner est toujours légal à l'état
    courant). La **confirmation** est à la charge de l'écran (on peut annuler avant de valider) ; le
    serveur, lui, applique le forfait sitôt reçu. 404 si l'utilisateur ne participe pas (pas de
    fuite d'existence), 409 si la partie n'est plus en cours. Le résultat est diffusé sur le canal
    temps réel (`HUB`) : l'adversaire voit la partie se clore avec le motif « abandon ».
    """
    try:
        resultat = await abandonner_partie(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except PartieNonActive as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    game = await _game_pour_participant(db, game_id, current_user.id)
    catalogue = await catalogue_pour_resultat(db, resultat, game_id=game_id)
    catalogue_jeu = await construire_catalogue_jeu(db, depuis_json(resultat.etat))
    HUB.publier(
        game_id, resultat, graine_hex=game.graine, catalogue=catalogue, catalogue_jeu=catalogue_jeu
    )
    reponse = projeter_resultat(
        resultat, user_id=current_user.id, graine_hex=game.graine, catalogue=catalogue,
        catalogue_jeu=catalogue_jeu,
    )
    # Le prochain numéro d'action attendu, pour que le client enchaîne un coup suivant sans aller
    # relire l'état (lot ``j-plateau-interactions``).
    reponse["numero"] = game.current_numero
    return reponse


@router.post("/{game_id}/conseil", response_model=ConseilOut)
async def get_conseil(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ConseilOut:
    """Un conseil de l'IA du joueur pour SON tour (lot `j-coach-ia`, DJ7) — une **suggestion**.

    L'IA (sa clé) reçoit sa vue projetée et ses coups légaux, propose un coup et l'explique ; le
    serveur n'applique **rien** — le geste reste celui du joueur. Réservé aux parties d'entraînement
    (jamais entre deux humains), borné par un plafond de conseils par partie, et refusé sans clé IA
    ou si le coach est désactivé. 404 si l'utilisateur ne participe pas (pas de fuite d'existence).
    Quand aucun conseil n'est possible (ce n'est pas son tour, l'IA n'a rien trouvé), ``coup`` est
    nul et ``raison`` le dit — jamais un coup inventé.
    """
    try:
        res = await conseil_pour_joueur(
            db, game_id=game_id, user=current_user, max_conseils=settings.coach_max_conseils
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except CleCoachIndisponible as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CoachDesactive, ConseilHorsEntrainement, PlafondConseils, PartieNonActive) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    conseil = res.conseil
    coup = None
    if conseil.coup is not None:
        coup = CoupConseille(
            index=conseil.index if conseil.index is not None else -1,
            etiquette=conseil.coup.etiquette,
            type=conseil.coup.action.type,
            params=conseil.coup.action.params,
        )
    return ConseilOut(
        coup=coup,
        explication=conseil.explication,
        raison=conseil.raison,
        conseils_utilises=res.conseils_utilises,
        conseils_restants=res.conseils_restants,
    )


@router.get("/{game_id}/bilan", response_model=BilanOut)
async def get_bilan(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> BilanOut:
    """Le bilan de l'IA du joueur après une partie **terminée** (lot `j-coach-ia`, DJ7).

    À partir du **journal** (les coups réellement joués, pas l'état complet), l'IA (sa clé) dégage
    deux ou trois moments décisifs. Chaque moment cité est **vérifié** contre le journal : un numéro
    inventé est écarté. Désactivable (coach éteint -> 409), refusé sans clé IA (422) ou sur une
    partie non terminée (409). 404 si l'utilisateur ne participe pas. Si l'IA ne rend rien
    d'exploitable, on le dit (502) plutôt qu'un bilan vide.
    """
    try:
        res = await bilan_de_partie(db, game_id=game_id, user=current_user)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except CleCoachIndisponible as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CoachDesactive, PartieNonTerminee) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except BilanIndisponible as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return BilanOut(
        resume=res.resume,
        moments=[MomentBilanOut(**m) for m in res.moments],
    )


# --- Replay d'une partie finie (lot `j-replay`) -------------------------------


@router.get("/{game_id}/replay")
async def get_replay(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
    vue: str = VUE_MOI,
    depuis: Annotated[int, Query(ge=0)] = 0,
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAX)] = LIMITE_DEFAUT,
) -> dict:
    """Le replay d'une partie **finie** : une page de rangs, chacun avec son état projeté.

    Accessible aux **deux joueurs** et aux comptes à qui un joueur a ouvert ce replay ; à tout
    autre compte, **404** — pas 403 : pour lui, ce replay n'existe pas (c'est le critère
    « le lien de replay n'est pas accessible à un compte non autorisé »).

    Une partie **encore en cours** répond **409** et ne porte aucun rang : le risque nommé du lot
    est précisément de servir le journal d'une partie en cours « au titre du replay ». `vue=moi`
    donne ce que le joueur courant a vu ; `vue=complete` donne les deux vues de joueur — jamais
    autre chose : il n'existe pas de sortie non projetée (voir `pbm_api.games.replay`). Un
    spectateur qui demande `moi` reçoit 422 (il n'a pas de siège), jamais un repli silencieux sur
    la vue complète.

    La réponse dit toujours `total` et `complet` : un client enchaîne les pages (`depuis`) jusqu'à
    `complet`, et l'écran sait dire ce qu'il n'a pas encore chargé plutôt que de laisser croire
    que la partie s'arrête là.
    """
    try:
        return await composer_replay(
            db,
            game_id=game_id,
            user_id=current_user.id,
            vue=vue,
            depuis=depuis,
            limite=limite,
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except ReplayPartieEnCours as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (VueInconnue, VueMoiHorsParticipant) as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        # Pagination hors bornes (`depuis` au-delà du dernier coup) : le client a demandé une
        # page qui n'existe pas. On le dit, on ne rend pas une page vide qui ressemblerait à
        # « la partie finit ici ».
        raise HTTPException(422, str(exc)) from exc


@router.get("/{game_id}/replay/partages", response_model=list[PartageReplayOut])
async def list_replay_partages(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> list[PartageReplayOut]:
    """Les comptes à qui le replay de cette partie est ouvert (réservé à ses deux joueurs).

    404 pour qui n'y joue pas — y compris un compte à qui le replay est ouvert : regarder n'est
    pas administrer. Relire ses partages est ce qui permet de penser à les fermer.
    """
    try:
        lignes = await partages(db, game_id=game_id, user_id=current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    return [PartageReplayOut(**ligne) for ligne in lignes]


@router.post(
    "/{game_id}/replay/partages",
    response_model=PartageReplayOut,
    status_code=status.HTTP_201_CREATED,
)
async def ouvrir_replay_partage(
    game_id: uuid.UUID,
    body: PartageReplayIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
    _csrf: None = Depends(require_csrf),
) -> PartageReplayOut:
    """Ouvre le replay de cette partie à un **compte invité**, désigné par son pseudo.

    Réservé aux deux joueurs (404 sinon). 404 si aucun compte invité ne porte ce pseudo — on ne
    révèle pas l'existence d'un compte ordinaire. 422 si la cible joue déjà cette partie (elle y a
    droit de toute façon). Idempotent : ouvrir deux fois ne crée qu'un partage.
    """
    try:
        partage = await ouvrir_partage(
            db, game_id=game_id, user_id=current_user.id, pseudo=body.pseudo
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except DestinatairePartageIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except AutoPartage as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.commit()
    pseudo = (await db.get(User, partage.user_id)).pseudo
    return PartageReplayOut(
        user_id=partage.user_id,
        pseudo=pseudo,
        partage_par_user_id=partage.created_by_user_id,
        created_at=partage.created_at,
    )


@router.delete("/{game_id}/replay/partages/{cible_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def fermer_replay_partage(
    game_id: uuid.UUID,
    cible_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
    _csrf: None = Depends(require_csrf),
) -> Response:
    """Retire à un compte le droit de regarder ce replay (réservé aux deux joueurs).

    404 quand il n'y avait rien à retirer : on ne prétend pas avoir fermé un partage inexistant.
    Un droit qui s'accorde doit se reprendre aussi simplement, sinon on hésite à l'accorder.
    """
    try:
        ferme = await fermer_partage(
            db, game_id=game_id, user_id=current_user.id, cible_user_id=cible_user_id
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    if not ferme:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partage introuvable.")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Fin de partie : récapitulatif et revanche (lot `j-partie-fin-ui`) --------


@router.get("/{game_id}/recapitulatif", response_model=RecapitulatifOut)
async def get_recapitulatif(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> RecapitulatifOut:
    """Le récapitulatif d'une partie **finie**, recalculé depuis son journal.

    Lot `j-partie-fin-ui`.

    Durée, nombre de tours, dégâts, cartes jouées, K.O., récompenses, meilleur coup : tout est
    **recompté** depuis les entrées du journal à chaque demande, jamais accumulé pendant la
    partie. C'est le risque nommé du lot : le canal temps réel rejoue la partie entière à chaque
    reconnexion, donc un compteur incrémenté à l'arrivée des événements doublerait après un F5.

    404 si l'utilisateur ne joue pas cette partie (jamais 403 — pas de fuite d'existence) ; 409 si
    la partie est encore en cours (comme le replay : la fenêtre ne s'ouvre qu'à la fin).
    """
    try:
        recap = await recapitulatif_de_partie(db, game_id=game_id, user_id=current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except RecapPartieEnCours as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return RecapitulatifOut.model_validate(recap)


@router.post(
    "/{game_id}/revanche", response_model=RevancheOut, status_code=status.HTTP_201_CREATED
)
async def post_revanche(
    game_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
    _csrf: None = Depends(require_csrf),
) -> RevancheOut:
    """Relance la partie : mêmes joueurs, mêmes decks, **sans repasser par la file**.

    Le **perdant commence** (siège 0) ; sans vainqueur, les sièges sont échangés. Les deux decks
    sont recontrôlés (propriété, scripts D9, possession) : un deck vendu ou supprimé arrête la
    revanche en nommant ce qui manque, jamais une partie fantôme. Une revanche d'entraînement
    reste un entraînement, au même niveau et contre le même adversaire (bot ou IA du joueur).

    **201** quand la partie est créée ; **200** avec ``deja_creee`` quand une partie en cours
    existait déjà entre ces deux comptes — les deux joueurs ont cliqué en même temps, et on les
    envoie au même plateau au lieu d'en créer deux.

    404 si l'utilisateur ne joue pas la partie finie, ou si un deck n'est pas le sien ; 409 si
    la partie n'est pas terminée ou si un des deux joueurs est engagé ailleurs ; 422 si un deck
    n'est plus jouable (cartes nommées) ou n'existe plus ; **503** avec ``Retry-After`` si le
    serveur tient déjà son plafond de parties simultanées.
    """
    try:
        partie, deja_creee = await creer_revanche(
            db, game_id=game_id, user_id=current_user.id
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except (RevanchePartieEnCours, JoueurDejaEnPartie) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except SiegeSansDeck as exc:
        raise HTTPException(422, str(exc)) from exc
    except DeckInjouable as exc:
        raise HTTPException(
            422,
            detail={
                "message": "Deck non jouable.",
                "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.refus],
            },
        ) from exc
    except CartesNonJouables as exc:
        raise HTTPException(
            422,
            detail={
                "message": "Deck non jouable.",
                "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.cartes],
            },
        ) from exc
    except (NiveauBotInconnu, CleIAIndisponible) as exc:
        raise HTTPException(422, str(exc)) from exc
    except PlafondPartiesAtteint as exc:
        # 503 : plafond de parties simultanées atteint. La partie finie reste consultable et la
        # revanche reste possible plus tard — rien n'est perdu (lot `j-charge-temps-reel`).
        raise erreur_capacite(exc) from exc

    if deja_creee:
        response.status_code = status.HTTP_200_OK
    return RevancheOut(game_id=partie.id, deja_creee=deja_creee)
