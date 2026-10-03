"""Partie d'**entraînement contre un bot** : brancher le bot de simulation comme 2e joueur (DJ7).

Lot ``j-mode-solo`` (jalon J4). On réutilise, sans le réécrire, le bot heuristique de
``pbm_sim.bots`` — celui qui joue déjà des milliers de parties de simulation — et on le branche
comme **adversaire serveur** d'une partie ordinaire du service (:mod:`pbm_api.games.service`). Trois
principes gouvernent ce module :

* **Le serveur fait autorité, le bot aussi.** Le bot ne passe **jamais** par HTTP : il décide côté
  serveur, à partir de la **seule** projection :func:`pbm_game.state.vue` (sa main, le plateau
  public, le nombre de cartes cachées) et de la liste légale que le moteur calcule pour lui —
  jamais
  l'``EtatPartie`` complet. Un bot qui lirait la main adverse serait indétectable côté joueur et
  ruinerait la confiance : la contrainte de vue est donc **vérifiée par un test**.
* **Un effet non implémenté n'est jamais approximé (D9).** Si le bot n'a aucun coup jouable, ou si
  une demande de décision lui est adressée qu'il ne sait pas résoudre, il **rend la main** en le
  journalisant — jamais un coup inventé, jamais un repli muet.
* **Entraînement, pas compétition.** La partie est marquée ``entrainement`` : elle entre dans
  l'historique du joueur mais ne compte pas (ni classement ni séries).

Trois niveaux (DJ7), chacun une stratégie **réelle** de ``pbm_sim.bots`` :

======= ============= =================================================================
Niveau  Bot           Comportement
======= ============= =================================================================
hasard  aleatoire     joue un coup légal au hasard (hors abandon)
correct heuristique   promeut le plus sain, attaque fort, évolue, pose, charge utile
coriace coriace       comme « correct », mais concentre l'énergie sur l'Actif (R-9.2)
======= ============= =================================================================
"""

from __future__ import annotations

import logging
import random
import uuid

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal import appliquer
from pbm_game.state import EtatPartie, vue
from pbm_game.state.serialisation import vers_json as etat_vers_json
from pbm_sim.bots import par_nom
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import AIProvider
from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.adversaire_ia import (
    MAX_APPELS_PAR_PARTIE,
    Decideur,
    ResultatDecision,
    choisir_coup_ia,
)
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import GameError
from pbm_api.games.lancement import verifier_lancable
from pbm_api.games.service import (
    INTERVALLE_INSTANTANE,
    ResultatAction,
    _game_sous_verrou,
    _maintenant,
    _persister_coup,
    _piloter,
    _reconstruire,
    creer_partie,
    demarrer_partie,
)
from pbm_api.models import User
from pbm_api.models.games import GAME_STATUS_EN_COURS, Game, GamePlayer

logger = logging.getLogger(__name__)

#: Identité fixe du compte bot réservé (doit coïncider avec la migration ``f1c0b07a1d02``). Le bot
#: n'est jamais connectable (hash de mot de passe impossible, pas d'accès jeu) : il joue uniquement
#: côté serveur. La clé étrangère ``game_players.user_id`` exige néanmoins un compte réel.
BOT_USER_ID = uuid.UUID("b07b07b0-0000-4000-8000-000000000001")

#: Les trois niveaux proposés au joueur (DJ7) → le bot de ``pbm_sim`` qui les réalise. On ne touche
#: pas à ``pbm_sim.decks.BOTS_DISPONIBLES`` (qui pilote le tirage des scénarios de simulation par
#: graine) : « coriace » est servi par ``par_nom`` sans entrer dans ce tirage, pour ne pas décaler
#: les parties que la simulation associe à une graine (reproductibilité des anomalies archivées).
NIVEAUX: dict[str, str] = {
    "hasard": "aleatoire",
    "correct": "heuristique",
    "coriace": "coriace",
}

#: Temps de réflexion **visible** du bot (DJ7 : « rester lisible »). Le serveur ne dort jamais (il
#: sert d'autres joueurs) : il renvoie ce délai, et c'est l'écran qui révèle les coups du bot à ce
#: rythme. Donnée d'animation, pas une temporisation serveur.
DELAI_REFLEXION_MS = 800


class NiveauBotInconnu(GameError):
    """Le niveau de bot demandé n'est pas l'un des trois de DJ7 (→ 422).

    Jamais un repli silencieux sur un niveau par défaut : un niveau inconnu est refusé en le
    nommant, comme tout refus de ce dépôt.
    """


class CleIAIndisponible(GameError):
    """Le joueur a demandé « mon IA » mais n'a **aucune clé IA** utilisable (→ 422).

    On refuse la création en le disant clairement (jamais un repli muet qui ferait croire que l'IA
    joue alors que le bot a pris sa place) : l'écran invite à déposer une clé dans le profil, et
    propose le bot en attendant (critère 4 du lot).
    """


def _resoudre_bot(niveau: str):
    """La fonction de décision du bot pour ``niveau`` (DJ7), ou lève :class:`NiveauBotInconnu`.

    Indirection volontaire : les tests la surchargent pour **espionner** ce que le bot reçoit (et
    prouver qu'il ne voit que la vue projetée, jamais l'état complet).
    """
    nom = NIVEAUX.get(niveau)
    if nom is None:
        raise NiveauBotInconnu(
            f"Niveau de bot « {niveau} » inconnu (connus : {sorted(NIVEAUX)})."
        )
    return par_nom(nom)


async def _bot_du_siege(db: AsyncSession, game_id: uuid.UUID) -> GamePlayer | None:
    """Le siège tenu par le joueur automatique (``bot_niveau`` renseigné), ou ``None``.

    Un siège IA (``adversaire_ia`` vrai) porte lui aussi un ``bot_niveau`` — c'est son **repli** —
    donc cette requête ramène aussi bien le siège d'un bot pur que celui d'une IA.
    """
    return (
        await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id, GamePlayer.bot_niveau.isnot(None)
            )
        )
    ).scalar_one_or_none()


async def _humain_du_siege(
    db: AsyncSession, game_id: uuid.UUID, siege_auto: GamePlayer
) -> User | None:
    """L'utilisateur **humain** de la partie (l'autre siège que celui du joueur automatique).

    Sert à retrouver, pour un adversaire IA, la clé IA du joueur (c'est **sa** clé qui joue, DJ7).
    ``None`` si l'autre siège est introuvable (ne devrait pas arriver en entraînement).
    """
    autre = (
        await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id, GamePlayer.id != siege_auto.id
            )
        )
    ).scalar_one_or_none()
    if autre is None:
        return None
    return await db.get(User, autre.user_id)


def _decideur_bot(niveau: str) -> Decideur:
    """Le joueur automatique **bot** : il décide sur sa seule vue, sans rien à expliquer (muet).

    Passe par :func:`_resoudre_bot` (indirection surchargée par les tests pour espionner la vue
    reçue) — c'est le même bot heuristique qu'en mode solo pur. Le coup est enveloppé dans un
    :class:`ResultatDecision` sans commentaire : un bot joue juste, il ne raisonne pas à voix haute.
    """
    bot_fn = _resoudre_bot(niveau)

    async def _decider(vue_joueur: dict, legales, alea: random.Random) -> ResultatDecision:
        return ResultatDecision(coup=bot_fn(vue_joueur, legales, alea))

    return _decider


def _decideur_ia(
    db: AsyncSession,
    game: Game,
    humain: User,
    provider: AIProvider | None,
    repli_niveau: str,
) -> Decideur:
    """Le joueur automatique **IA du joueur** : il raisonne, explique, et **bascule au bot** sinon.

    La clé de l'humain a déjà construit ``provider`` (``None`` si elle a disparu).
    À chaque décision :

    * si le fournisseur est indisponible, ou si le **plafond d'appels** de la partie est atteint, le
      bot de repli joue — le journal l'**annonce une fois** (puis joue en silence, le changement
      étant déjà dit) ;
    * sinon l'IA choisit (:func:`~pbm_api.games.adversaire_ia.choisir_coup_ia`) ; un appel réel
      incrémente le budget (``games.ia_appels``) et, s'il a renvoyé un usage, le total de
      jetons (``games.ia_tokens``, base du coût estimé) et l'usage mensuel de l'humain — **dans la
      transaction du coup** (``commit=False``), pour n'être compté que si le coup est persisté.

    Le repli sert le **niveau de bot** choisi par le joueur : son IA et son bot de secours jouent au
    même niveau de difficulté.
    """
    repli_fn = _resoudre_bot(repli_niveau)
    annonce = {"faite": False}

    async def _decider(vue_joueur: dict, legales, alea: random.Random) -> ResultatDecision:
        indisponible = provider is None
        plafond = game.ia_appels >= MAX_APPELS_PAR_PARTIE
        if indisponible or plafond:
            coup = repli_fn(vue_joueur, legales, alea)
            if not annonce["faite"]:
                annonce["faite"] = True
                raison = (
                    "ta clé IA n'est plus disponible"
                    if indisponible
                    else f"plafond d'appels atteint ({MAX_APPELS_PAR_PARTIE})"
                )
                return ResultatDecision(coup=coup, bascule_bot=True, raison=raison)
            return ResultatDecision(coup=coup)

        resultat = await choisir_coup_ia(
            provider, vue_joueur, legales, repli_bot=repli_fn, alea=alea
        )
        if resultat.appel_effectue:
            game.ia_appels += 1
            if resultat.usage is not None:
                game.ia_tokens += resultat.usage.input_tokens + resultat.usage.output_tokens
                await record_usage(db, humain, resultat.usage, commit=False)
        return resultat

    return _decider


async def boucle_joueur_auto(
    db: AsyncSession,
    game: Game,
    etat: EtatPartie,
    rng,
    maintenant,
    catalogue,
    *,
    acteur_jid: str,
    decideur: Decideur,
    intervalle: int,
    max_coups: int = 400,
) -> tuple[EtatPartie, list[dict], list[dict]]:
    """Fait jouer le **joueur automatique** (bot ou IA) jusqu'au retour de la main à l'humain.

    Interface **unique** du lot (mission point 1) : la boucle ne connaît ni le bot ni l'IA, elle
    appelle un ``decideur`` (:data:`~pbm_api.games.adversaire_ia.Decideur`) qui rend une
    :class:`~pbm_api.games.adversaire_ia.ResultatDecision`. Le serveur reste autorité : la boucle
    rejoue le coup choisi par le moteur (``appliquer``), jamais une action libre.

    N'écrit **aucun** commit (l'appelant décide) et ne pose **aucun** verrou (l'appelant a déjà
    chargé la partie sous verrou). À chaque tour de boucle :

    1. :func:`~pbm_api.games.service._piloter` enchaîne les coups **système** dus (pioche…) ;
    2. partie finie, ou **demande** de décision en attente (non pilotée à ce jalon — decks à dégâts
       secs, D9) : on rend la main en le journalisant ;
    3. en mise en place, l'acteur place **son** camp s'il ne l'a pas fait, sinon il attend ;
    4. en phase de jeu, si l'Actif est à l'acteur, le décideur choisit **un** coup sur sa **seule
       vue** (:func:`pbm_game.state.vue`) et la liste légale ; sinon il rend la main.

    Un coup ``None`` n'est jamais inventé : on s'arrête en le journalisant (jamais un repli
    silencieux). Le **commentaire** éventuel d'un coup (explication de l'IA, note de repli du bot)
    est écrit au journal et collecté dans la liste renvoyée, à destination de l'affichage.
    """
    evts: list[dict] = []
    commentaires: list[dict] = []
    familles = familles_jeu(catalogue)
    acteur_idx = next(i for i, j in enumerate(etat.joueurs) if j.id == acteur_jid)

    for _ in range(max_coups):
        # 1) Coups système dus (pioche, Checkup) : le serveur fait seul entre les tours.
        etat, e_sys = await _piloter(db, game, etat, rng, maintenant, catalogue, intervalle)
        evts += e_sys
        if etat.terminee:
            break

        # 2) Une demande de décision en attente : on rend la main (ni le bot ni l'IA ne pilotent de
        # demande à ce jalon — decks à dégâts secs ; l'humain répond via HTTP). Jamais inventé.
        if etat.resolution is not None:
            if etat.resolution.demande.destinataire == acteur_jid:
                logger.warning(
                    "joueur-auto : demande « %s » adressée à l'adversaire, non pilotée (partie %s) "
                    "— il rend la main.",
                    etat.resolution.demande.id,
                    game.id,
                )
            break

        # 3) Mise en place : l'acteur place son camp s'il ne l'a pas fait ; sinon il attend.
        if etat.mise_en_place is not None:
            if etat.mise_en_place.placements[acteur_idx] is not None:
                break
            acteur = acteur_jid
        else:
            # 4) Phase de jeu : à l'acteur de jouer seulement si l'Actif est le sien.
            if etat.tour.joueur_actif != acteur_jid:
                break
            acteur = acteur_jid

        # Un flux d'aléatoire par coup, dérivé de la graine (secret serveur, jamais exposé) et du
        # numéro courant : il varie les choix du bot sans dépendre de l'ordre d'insertion.
        alea = random.Random(f"{game.graine}:{game.current_numero}")
        legales = actions_legales(etat, acteur, familles)
        decision = await decideur(vue(etat, acteur), legales, alea)
        if decision.coup is None:
            logger.warning(
                "joueur-auto : aucun coup jouable pour l'adversaire (partie %s, phase %s) — "
                "il rend la main (jamais un coup inventé, D9).",
                game.id,
                etat.tour.phase,
            )
            break

        numero = game.current_numero
        commentaire = decision.commentaire_journal()
        etat2, evenements = appliquer(etat, decision.coup.action, rng)
        evts += _persister_coup(
            db, game, decision.coup.action, etat, etat2, evenements, maintenant, rng, intervalle,
            commentaire=commentaire,
        )
        if commentaire is not None:
            commentaires.append({"numero": numero, "texte": commentaire})
        etat = etat2

    return etat, evts, commentaires


async def boucle_bot_pour_partie(
    db: AsyncSession,
    game: Game,
    etat: EtatPartie,
    rng,
    maintenant,
    catalogue,
    intervalle: int,
) -> tuple[EtatPartie, list[dict], list[dict]]:
    """Enveloppe pour la boucle d'application : résout le joueur automatique et le fait jouer.

    Appelée par :func:`~pbm_api.games.service.appliquer_action` après le coup de l'humain, quand la
    partie est un entraînement. Résout le siège automatique, construit le **décideur** approprié —
    l'IA du joueur (:func:`_decideur_ia`) si ``adversaire_ia`` est posé, sinon le bot
    (:func:`_decideur_bot`) — puis délègue à :func:`boucle_joueur_auto`. Pour une IA, construit le
    fournisseur depuis la clé de l'humain (coffre) ; la clé reste dans cette fonction et le
    fournisseur est **refermé** à la fin, jamais laissé ouvert. Sans siège automatique (ne devrait
    pas arriver pour un entraînement), ne fait rien plutôt que d'inventer un adversaire.
    """
    siege = await _bot_du_siege(db, game.id)
    if siege is None:
        logger.warning(
            "entraînement : partie %s sans siège d'adversaire — aucun coup joué.", game.id
        )
        return etat, [], []

    acteur_jid = joueur_id_de(siege.user_id)
    provider: AIProvider | None = None
    if siege.adversaire_ia:
        humain = await _humain_du_siege(db, game.id, siege)
        credential = await get_default_credential(db, humain) if humain is not None else None
        if credential is not None:
            fournisseur_enum, cle = credential
            # La clé déchiffrée ne sert qu'ici, à construire le fournisseur ; jamais journalisée.
            provider = create_provider(fournisseur_enum, cle)
        decideur = _decideur_ia(db, game, humain, provider, siege.bot_niveau or "correct")
    else:
        decideur = _decideur_bot(siege.bot_niveau)

    try:
        return await boucle_joueur_auto(
            db,
            game,
            etat,
            rng,
            maintenant,
            catalogue,
            acteur_jid=acteur_jid,
            decideur=decideur,
            intervalle=intervalle,
        )
    finally:
        if provider is not None:
            await provider.aclose()


async def jouer_coups_bot(
    db: AsyncSession, game_id: uuid.UUID, maintenant=None
) -> ResultatAction | None:
    """Fait jouer le bot **sous verrou**, hors d'un coup de l'humain (placement initial, relance).

    Charge la partie sous verrou de ligne (comme un coup de joueur), reconstruit l'état, fait jouer
    le bot (:func:`boucle_joueur_auto`) puis **commit**. Renvoie le :class:`ResultatAction` du
    dernier état (de quoi diffuser et projeter), ou ``None`` si rien n'a bougé (bot déjà à jour,
    partie close, pas d'entraînement). Un verrou posé sans écriture est **relâché** (rollback),
    jamais laissé ouvert.

    Le **placement initial** du camp automatique est toujours fait par le **bot** — même pour un
    adversaire IA : il survient à la création (route synchrone), où l'on ne veut ni la latence ni
    les aléas d'un appel réseau. L'IA prend la main pour les **tours de jeu**, via
    :func:`boucle_bot_pour_partie`. Le placement d'un bot est muet : aucun commentaire ici.
    """
    maintenant = maintenant or _maintenant()
    game = await _game_sous_verrou(db, game_id)
    if game is None or not game.entrainement or game.status != GAME_STATUS_EN_COURS:
        if game is not None:
            await db.rollback()
        return None
    bot = await _bot_du_siege(db, game_id)
    if bot is None:
        await db.rollback()
        return None

    etat, rng = await _reconstruire(db, game)
    catalogue = await construire_catalogue_jeu(db, etat)
    numero_avant = game.current_numero
    etat, evts, _commentaires = await boucle_joueur_auto(
        db,
        game,
        etat,
        rng,
        maintenant,
        catalogue,
        acteur_jid=joueur_id_de(bot.user_id),
        decideur=_decideur_bot(bot.bot_niveau),
        intervalle=INTERVALLE_INSTANTANE,
    )
    if game.current_numero == numero_avant:
        await db.rollback()
        return None

    await db.commit()
    return ResultatAction(
        numero=numero_avant,
        evenements=evts,
        empreinte=game.current_empreinte,
        terminee=etat.terminee,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=etat.raison_fin,
        etat=etat_vers_json(etat),
        rejoue=False,
        rng_compteurs=rng.compteurs(),
        horloges=_adapt_horloges.restant_json(game.horloges, maintenant.timestamp()),
    )


async def creer_partie_entrainement(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    deck_id: uuid.UUID,
    niveau: str,
    adversaire: str = "bot",
    maintenant=None,
) -> Game:
    """Crée et démarre une partie d'entraînement : le joueur (siège 0) contre l'adversaire.

    ``adversaire`` vaut ``"bot"`` (le bot heuristique, muet) ou ``"ia"`` (l'IA du joueur, qui
    raisonne et explique, sur **sa** clé). Dans les deux cas, ``niveau`` fixe le niveau du bot — qui
    joue l'intégralité d'une partie « bot », et sert de **repli** à l'IA d'une partie « ia ».

    * refuse un ``niveau`` hors DJ7 (:class:`NiveauBotInconnu`, 422) ;
    * pour ``adversaire == "ia"``, exige que le joueur ait une **clé IA** utilisable
      (:class:`CleIAIndisponible`, 422) — sinon on refuse en le disant, jamais un repli muet sur le
      bot (critère 4 : l'écran invite alors à ajouter une clé, et propose le bot en attendant) ;
    * **recontrôle** le deck du joueur (propriété, scripts D9, possession)
      :func:`~pbm_api.games.lancement.verifier_lancable` — carte vendue ou script retiré arrête la
      création en nommant la carte (jamais une partie fantôme sur un deck mort) ;
    * l'adversaire **joue le même deck** que le joueur (match miroir) : partenaire immédiat, sans
      deck ni collection propres — choix explicite documenté, qu'un lot ultérieur enrichira. Le deck
      du joueur étant vérifié, celui de l'adversaire l'est par construction ;
    * crée la partie ``entrainement`` (siège 1, ``bot_niveau`` posé, ``adversaire_ia`` selon le
      choix), lance la mise en place (R-4), puis fait **placer le bot** aussitôt — le joueur voit
      « l'adversaire est prêt » et n'a plus qu'à placer son camp.

    Le joueur commence (siège 0) : un adversaire d'entraînement ne se dispute pas le premier tour.
    """
    maintenant = maintenant or _maintenant()
    if niveau not in NIVEAUX:
        raise NiveauBotInconnu(
            f"Niveau de bot « {niveau} » inconnu (connus : {sorted(NIVEAUX)})."
        )
    if adversaire not in ("bot", "ia"):
        raise NiveauBotInconnu(
            f"Adversaire « {adversaire} » inconnu (connus : bot, ia)."
        )
    adversaire_ia = adversaire == "ia"
    if adversaire_ia:
        # La clé de l'humain jouera : on vérifie dès la création qu'il en a une utilisable, pour
        # refuser clairement plutôt que lancer une partie « ia » qui basculerait aussitôt au bot.
        humain = await db.get(User, user_id)
        if humain is None or await get_default_credential(db, humain) is None:
            raise CleIAIndisponible(
                "Aucune clé IA enregistrée : ajoute une clé (Anthropic, Gemini ou OpenAI) dans "
                "ton profil pour jouer contre ton IA. Tu peux jouer contre le bot en attendant."
            )
    # Propriété + scripts D9 + possession du deck joueur (DeckIntrouvable 404 / DeckInjouable
    # 422, cartes nommées). Le deck de l'adversaire étant le même, il est jouable par construction.
    await verifier_lancable(db, user_id, deck_id)

    game = await creer_partie(
        db,
        joueur_a=(user_id, deck_id),
        joueur_b=(BOT_USER_ID, deck_id),
        maintenant=maintenant,
        entrainement=True,
        bot_niveau=niveau,
        adversaire_ia=adversaire_ia,
    )
    await demarrer_partie(db, game, maintenant)
    # Le bot place son camp immédiatement (sous son propre verrou + commit).
    await jouer_coups_bot(db, game.id, maintenant)
    rafraichi = await db.get(Game, game.id)
    return rafraichi if rafraichi is not None else game


__all__ = [
    "BOT_USER_ID",
    "NIVEAUX",
    "DELAI_REFLEXION_MS",
    "NiveauBotInconnu",
    "CleIAIndisponible",
    "boucle_joueur_auto",
    "boucle_bot_pour_partie",
    "jouer_coups_bot",
    "creer_partie_entrainement",
]
