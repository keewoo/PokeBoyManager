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

from pbm_api.games import horloges as _adapt_horloges
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
    """Le siège tenu par le bot dans cette partie (``bot_niveau`` renseigné), ou ``None``."""
    return (
        await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id, GamePlayer.bot_niveau.isnot(None)
            )
        )
    ).scalar_one_or_none()


async def boucle_bot(
    db: AsyncSession,
    game: Game,
    etat: EtatPartie,
    rng,
    maintenant,
    catalogue,
    *,
    bot_jid: str,
    bot_fn,
    intervalle: int,
    max_coups: int = 400,
) -> tuple[EtatPartie, list[dict]]:
    """Fait jouer le bot **jusqu'à ce que la main revienne au joueur humain** (ou la fin de partie).

    N'écrit **aucun** commit (l'appelant décide) et ne pose **aucun** verrou (l'appelant a déjà
    chargé la partie sous verrou). À chaque tour de boucle :

    1. on laisse :func:`~pbm_api.games.service._piloter` enchaîner les coups **système** dus (pioche
       de début de tour, Pokémon Checkup) — exactement comme pour une partie entre deux humains ;
    2. si la partie est finie, ou si une **demande** de décision est en attente (pour l'humain, ou
       pour le bot — qu'il ne sait pas résoudre à ce jalon : decks à dégâts secs, D9), on rend la
       main en le journalisant ;
    3. en mise en place, le bot place **son** camp s'il ne l'a pas encore fait, sinon il attend ;
    4. en phase de jeu, si l'Actif est au bot il joue **un** coup choisi sur sa **seule vue**
       (:func:`pbm_game.state.vue`) et la liste légale ; sinon il rend la main.

    Un coup ``None`` (aucun coup jouable) n'est jamais inventé : on s'arrête en le journalisant
    (jamais un repli silencieux). ``max_coups`` borne la boucle par sécurité.
    """
    evts: list[dict] = []
    familles = familles_jeu(catalogue)
    bot_idx = next(i for i, j in enumerate(etat.joueurs) if j.id == bot_jid)

    for _ in range(max_coups):
        # 1) Coups système dus (pioche, Checkup) : le serveur fait seul entre les tours.
        etat, e_sys = await _piloter(db, game, etat, rng, maintenant, catalogue, intervalle)
        evts += e_sys
        if etat.terminee:
            break

        # 2) Une demande de décision en attente : on rend la main (le bot ne pilote pas de demande
        # à ce jalon — decks à dégâts secs ; l'humain, lui, répondra via HTTP). Jamais inventé.
        if etat.resolution is not None:
            if etat.resolution.demande.destinataire == bot_jid:
                logger.warning(
                    "mode-solo : demande « %s » adressée au bot, non pilotée (partie %s) — "
                    "le bot rend la main.",
                    etat.resolution.demande.id,
                    game.id,
                )
            break

        # 3) Mise en place : le bot place son camp s'il ne l'a pas fait ; sinon il attend l'humain.
        if etat.mise_en_place is not None:
            placements = etat.mise_en_place.placements
            if placements[bot_idx] is not None:
                break
            acteur = bot_jid
        else:
            # 4) Phase de jeu : au bot de jouer seulement si l'Actif est le sien.
            if etat.tour.joueur_actif != bot_jid:
                break
            acteur = bot_jid

        # Un flux d'aléatoire par coup, dérivé de la graine (secret serveur, jamais exposé) et du
        # numéro courant : « hasard » varie ses choix sans dépendre de l'ordre d'insertion.
        alea = random.Random(f"{game.graine}:{game.current_numero}")
        legales = actions_legales(etat, acteur, familles)
        coup = bot_fn(vue(etat, acteur), legales, alea)
        if coup is None:
            logger.warning(
                "mode-solo : aucun coup jouable pour le bot (partie %s, phase %s) — il rend la "
                "main (jamais un coup inventé, D9).",
                game.id,
                etat.tour.phase,
            )
            break

        etat2, evenements = appliquer(etat, coup.action, rng)
        evts += _persister_coup(
            db, game, coup.action, etat, etat2, evenements, maintenant, rng, intervalle
        )
        etat = etat2

    return etat, evts


async def boucle_bot_pour_partie(
    db: AsyncSession,
    game: Game,
    etat: EtatPartie,
    rng,
    maintenant,
    catalogue,
    intervalle: int,
) -> tuple[EtatPartie, list[dict]]:
    """Enveloppe pour la boucle d'application : résout le bot du siège puis le fait jouer.

    Appelée par :func:`~pbm_api.games.service.appliquer_action` après le coup de l'humain, quand la
    partie est un entraînement. Résout le siège bot et sa fonction de décision, puis délègue à
    :func:`boucle_bot`. Sans siège bot (ne devrait pas arriver pour une partie d'entraînement), ne
    fait rien plutôt que d'inventer un adversaire.
    """
    bot = await _bot_du_siege(db, game.id)
    if bot is None:
        logger.warning(
            "mode-solo : partie d'entraînement %s sans siège bot — aucun coup joué.", game.id
        )
        return etat, []
    return await boucle_bot(
        db,
        game,
        etat,
        rng,
        maintenant,
        catalogue,
        bot_jid=joueur_id_de(bot.user_id),
        bot_fn=_resoudre_bot(bot.bot_niveau),
        intervalle=intervalle,
    )


async def jouer_coups_bot(
    db: AsyncSession, game_id: uuid.UUID, maintenant=None
) -> ResultatAction | None:
    """Fait jouer le bot **sous verrou**, hors d'un coup de l'humain (placement initial, relance).

    Charge la partie sous verrou de ligne (comme un coup de joueur), reconstruit l'état, fait jouer
    le bot (:func:`boucle_bot`) puis **commit**. Renvoie le :class:`ResultatAction` du dernier état
    (de quoi diffuser et projeter), ou ``None`` si rien n'a bougé (bot déjà à jour, partie close,
    pas d'entraînement). Un verrou posé sans écriture est **relâché** (rollback), jamais laissé
    ouvert.
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
    etat, evts = await boucle_bot(
        db,
        game,
        etat,
        rng,
        maintenant,
        catalogue,
        bot_jid=joueur_id_de(bot.user_id),
        bot_fn=_resoudre_bot(bot.bot_niveau),
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
    maintenant=None,
) -> Game:
    """Crée et démarre une partie d'entraînement : le joueur (siège 0) contre le bot (siège 1).

    * refuse un ``niveau`` hors DJ7 (:class:`NiveauBotInconnu`, 422) ;
    * **recontrôle** le deck du joueur (propriété, scripts D9, possession)
      :func:`~pbm_api.games.lancement.verifier_lancable` — carte vendue ou script retiré arrête la
      création en nommant la carte (jamais une partie fantôme sur un deck mort) ;
    * le bot **joue le même deck** que le joueur (match miroir) : c'est un partenaire d'entraînement
      immédiat, sans deck ni collection propres — le choix explicite de ce lot, documenté, qu'un lot
      ultérieur pourra enrichir de decks préconstruits. Le deck du joueur étant déjà vérifié, celui
      du bot l'est par construction ;
    * crée la partie marquée ``entrainement`` (siège 1 = bot, ``bot_niveau`` posé), lance la mise en
      place (R-4), puis fait **placer le bot** tout de suite — le joueur voit « l'adversaire est
      prêt » et n'a plus qu'à placer son camp.

    Le joueur commence (siège 0) : un adversaire d'entraînement ne se dispute pas le premier tour.
    """
    maintenant = maintenant or _maintenant()
    if niveau not in NIVEAUX:
        raise NiveauBotInconnu(
            f"Niveau de bot « {niveau} » inconnu (connus : {sorted(NIVEAUX)})."
        )
    # Propriété + scripts D9 + possession du deck joueur (DeckIntrouvable 404 / DeckInjouable
    # 422, cartes nommées). Le deck du bot étant le même, il est jouable par construction.
    await verifier_lancable(db, user_id, deck_id)

    game = await creer_partie(
        db,
        joueur_a=(user_id, deck_id),
        joueur_b=(BOT_USER_ID, deck_id),
        maintenant=maintenant,
        entrainement=True,
        bot_niveau=niveau,
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
    "boucle_bot",
    "boucle_bot_pour_partie",
    "jouer_coups_bot",
    "creer_partie_entrainement",
]
