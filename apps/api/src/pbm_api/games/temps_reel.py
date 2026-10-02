"""Canal temps réel d'une partie (lot `j-temps-reel`) : resynchronisation, diffusion, reprise.

Ce module porte la **mécanique** du temps réel, indépendamment du transport (WebSocket ou
interrogation HTTP). Il s'appuie sur le socle du lot `j-partie-service` — le journal numéroté, la
source de vérité — et sur le point de sortie unique du moteur (`pbm_game.sortie.projeter`, lot
`j-autorite-vues`) : aucune donnée brute de partie ne circule au-delà d'ici.

Trois briques, chacune testable sans socket réel :

* :func:`resynchroniser` — « donne-moi tout depuis le numéro N » : reconstruit l'état autoritaire
  courant **plus** la file des coups de numéro ∈ [N, courant). C'est la réponse à une reprise après
  F5 (l'état complet remet le joueur exactement où il était) comme à une reconnexion après coupure
  (aucun coup manqué). Elle sert **à la fois** le WebSocket et le repli en interrogation ;
* :class:`Hub` — un bus de diffusion **en mémoire du process** : quand un coup est appliqué, chaque
  abonné d'une partie reçoit l'événement **projeté pour lui** (jamais la main adverse). Le journal
  reste le filet : un message perdu (abonné saturé, process distinct) est rattrapé par une
  resynchronisation côté client, qui détecte le trou par le numéro de séquence ;
* :func:`piloter_canal` — la boucle de pilotage d'un canal abstrait (:class:`Canal`) : resync
  initiale, diffusion des coups, battement de cœur (détection de coupure) et resynchronisation à la
  demande ou après saturation. Le WebSocket réel n'en est qu'un adaptateur mince.

Le **numéro de séquence** est le `numero` de l'entrée de journal (0, 1, 2, …) : `current_numero`
est le prochain attendu, les entrées existantes portent 0..`current_numero`-1. Le client applique
**par numéro**, jamais par ordre d'arrivée — c'est ce qui rend le canal insensible au désordre et
aux doublons (risque nommé du lot).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from pbm_game.journal import appliquer, empreinte, reprendre
from pbm_game.rng import Rng, flux_melange_deck
from pbm_game.sortie import (
    Jetonneur,
    enrichir_indicateurs,
    projeter,
    refs_en_jeu,
    secret_jetons,
)
from pbm_game.state.modele import EtatPartie
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.indicateurs import (
    CatalogueAffichage,
    catalogue_affichage,
    catalogue_pour_resultat,
)
from pbm_api.games.projection import projeter_resultat
from pbm_api.games.service import (
    GAME_STATUS_EN_COURS,
    ResultatAction,
    _dernier_instantane,
    _entrees_queue,
    expirer_horloge,
)
from pbm_api.models.games import Game

logger = logging.getLogger(__name__)

#: Intervalle (secondes) du battement de cœur quand aucun coup ne circule : il prouve que le canal
#: est vivant (le client arme une coupure s'il n'arrive pas) et porte le numéro courant du serveur,
#: pour que le client détecte une dernière diffusion manquée et demande une resynchronisation.
INTERVALLE_BATTEMENT = 20.0

#: Taille maximale de la file d'un abonné. Au-delà (client lent), on ne perd rien en silence : on
#: marque l'abonné « saturé » et le pilote de canal lui renverra une resynchronisation complète.
TAILLE_FILE_ABONNE = 256


# --- Resynchronisation -------------------------------------------------------


def _vue_et_file(
    etat_depart: EtatPartie,
    rng: Rng,
    entrees,
    *,
    joueur_id: str,
    secret: bytes,
) -> tuple[dict, list[dict], EtatPartie]:
    """Rejoue ``entrees`` depuis ``(etat_depart, rng)`` et projette chaque coup pour ``joueur_id``.

    Renvoie ``(vue_finale, file)`` où ``file`` est la liste ``[{numero, evenements}]`` des coups
    rejoués, chacun projeté avec le :class:`Jetonneur` **de ce point** (époque = nombre de mélanges
    du deck du joueur à cet instant) : les jetons des cartes cachées restent cohérents avec l'état
    qui suit le coup. L'empreinte de chaque coup rejoué est revérifiée contre le journal — une
    divergence lève, jamais tue en silence (« tout est rejouable »).
    """
    etat = etat_depart
    file: list[dict] = []
    for entree in entrees:
        etat, evenements = appliquer(etat, entree.action, rng)
        recalculee = empreinte(etat)
        if recalculee != entree.empreinte:
            raise RuntimeError(
                f"Resynchronisation divergente au coup {entree.numero} : empreinte journal "
                f"{entree.empreinte}, recalculée {recalculee}."
            )
        epoque = rng.compteurs().get(flux_melange_deck(joueur_id), 0)
        jetonneur = Jetonneur(secret=secret, epoque=epoque)
        projete = projeter(etat, tuple(evenements), pour=joueur_id, jetonneur=jetonneur)
        file.append({"numero": entree.numero, "evenements": projete["evenements"]})
    epoque_finale = rng.compteurs().get(flux_melange_deck(joueur_id), 0)
    jetonneur_final = Jetonneur(secret=secret, epoque=epoque_finale)
    vue = projeter(etat, (), pour=joueur_id, jetonneur=jetonneur_final)["vue"]
    return vue, file, etat


async def resynchroniser(
    db: AsyncSession, game: Game, *, user_id: uuid.UUID, depuis: int
) -> dict:
    """Vue autoritaire courante **plus** la file des coups depuis ``depuis``, pour ``user_id``.

    ``depuis`` est le numéro du **premier coup voulu** (le client passe « dernier appliqué + 1 ») ;
    il est borné à [0, `current_numero`]. La réponse porte toujours la vue complète de l'état
    courant — ce qui suffit à une reprise après F5, même au milieu d'une demande de décision — et la
    file des coups ∈ [`depuis`, courant), ce qui garantit qu'une coupure n'a rien fait perdre.

    Le travail est borné : on repart du dernier instantané ≤ `depuis`, on positionne l'état à
    `depuis`, puis on ne rejoue que [`depuis`, courant). Le secret des jetons vient de la graine
    (secret serveur, jamais renvoyé) ; seuls les jetons opaques en sortent.
    """
    joueur_id = joueur_id_de(user_id)
    courant = game.current_numero
    depuis = max(0, min(depuis, courant))

    instantane = await _dernier_instantane(db, game.id, depuis)
    queue_avant = await _entrees_queue(db, game.id, instantane.numero_entrees, depuis)
    etat, rng = reprendre(instantane, queue_avant)

    entrees = await _entrees_queue(db, game.id, depuis, courant)
    secret = secret_jetons(bytes.fromhex(game.graine))
    vue, file, etat_final = _vue_et_file(
        etat, rng, entrees, joueur_id=joueur_id, secret=secret
    )
    # Indicateurs d'affichage sur la vue de resynchronisation (lot ``j-plateau-etat-visuel``) :
    # la reprise après F5 doit montrer PV restants, énergies typées et Outil comme le temps réel.
    catalogue = await catalogue_affichage(db, refs_en_jeu(etat_final))
    enrichir_indicateurs(
        vue,
        etat_final,
        pv_imprimes=catalogue.pv_imprimes,
        types=catalogue.types,
        registre=catalogue.registre,
    )

    return {
        "type": "resync",
        "numero": courant,
        "depuis": depuis,
        "vue": vue,
        "evenements": file,
        "horloges": _adapt_horloges.restant_json(
            game.horloges, datetime.now(UTC).timestamp()
        ),
        "statut": game.status,
        "termine": game.status != GAME_STATUS_EN_COURS,
        "vainqueur_user_id": (
            str(game.vainqueur_user_id) if game.vainqueur_user_id else None
        ),
        "raison_fin": game.raison_fin,
    }


# --- Bus de diffusion en mémoire ---------------------------------------------


@dataclass(eq=False)
class Abonne:
    """Un abonné à une partie : son identité (pour projeter) et sa file de messages à émettre.

    ``eq=False`` : chaque abonné est unique par **identité d'objet** (une même connexion), ce qui le
    rend hachable et stockable tel quel dans l'ensemble des abonnés du :class:`Hub`.

    ``sature`` passe à vrai quand la file déborde (client trop lent) : le pilote de canal le lit,
    renvoie une resynchronisation complète et le remet à faux. On ne perd jamais un coup en silence.
    """

    user_id: uuid.UUID
    file: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(TAILLE_FILE_ABONNE))
    sature: bool = False


class Hub:
    """Bus de diffusion **en mémoire du process** : un ensemble d'abonnés par partie.

    Quand un coup est appliqué (route HTTP), :meth:`publier` projette l'événement **pour chaque
    abonné** et le dépose dans sa file. C'est le chemin « temps réel » à faible latence ; la
    **correction** ne repose pas sur lui mais sur le journal : un abonné sur un autre process, ou
    saturé, est rattrapé par une resynchronisation (le client détecte le trou par le numéro).
    """

    def __init__(self) -> None:
        self._abonnes: dict[uuid.UUID, set[Abonne]] = {}

    def souscrire(self, game_id: uuid.UUID, user_id: uuid.UUID) -> Abonne:
        """Inscrit un abonné à une partie et renvoie son jeton (:class:`Abonne`)."""
        abonne = Abonne(user_id=user_id)
        self._abonnes.setdefault(game_id, set()).add(abonne)
        return abonne

    def desouscrire(self, game_id: uuid.UUID, abonne: Abonne) -> None:
        """Retire un abonné ; vide l'entrée de partie devenue sans abonné (pas de fuite mémoire)."""
        abonnes = self._abonnes.get(game_id)
        if not abonnes:
            return
        abonnes.discard(abonne)
        if not abonnes:
            self._abonnes.pop(game_id, None)

    def nb_abonnes(self, game_id: uuid.UUID) -> int:
        """Nombre d'abonnés à une partie (supervision et tests)."""
        return len(self._abonnes.get(game_id, ()))

    def publier(
        self,
        game_id: uuid.UUID,
        resultat: ResultatAction,
        *,
        graine_hex: str,
        catalogue: CatalogueAffichage,
    ) -> None:
        """Diffuse un coup appliqué à tous les abonnés d'une partie, projeté pour chacun.

        Un rejeu idempotent (``resultat.rejoue``) n'ajoute aucun coup au journal : il n'est pas
        diffusé (rien de nouveau). Pour chaque abonné, la vue et les événements sont projetés pour
        **son** identité par le point de sortie unique du moteur — jamais l'état brut.
        """
        if resultat.rejoue:
            return
        for abonne in list(self._abonnes.get(game_id, ())):
            projete = projeter_resultat(
                resultat,
                user_id=abonne.user_id,
                graine_hex=graine_hex,
                catalogue=catalogue,
            )
            message = {
                "type": "evenement",
                "numero": resultat.numero,
                "vue": projete["vue"],
                "evenements": projete["evenements"],
                "termine": resultat.terminee,
                "vainqueur_user_id": (
                    str(resultat.vainqueur_user_id) if resultat.vainqueur_user_id else None
                ),
                "raison_fin": resultat.raison_fin,
                "horloges": resultat.horloges,
            }
            try:
                abonne.file.put_nowait(message)
            except asyncio.QueueFull:
                # Jamais de perte muette : on marque l'abonné, le pilote lui renverra une resync.
                abonne.sature = True
                logger.warning(
                    "file de diffusion saturée pour le joueur %s sur la partie %s "
                    "(coup %d) — resynchronisation programmée.",
                    abonne.user_id,
                    game_id,
                    resultat.numero,
                )


#: Hub partagé par l'application (un process = un hub). Les tests en fabriquent un local.
HUB = Hub()


# --- Pilotage d'un canal abstrait --------------------------------------------


class Canal(Protocol):
    """Transport minimal d'un canal temps réel, abstrait du WebSocket pour rester testable.

    Un adaptateur réel enveloppe une WebSocket Starlette ; un faux canal en mémoire sert les tests,
    dans la boucle du test (ni thread ni socket). :meth:`recevoir` renvoie ``None`` à la
    déconnexion.
    """

    async def recevoir(self) -> dict | None:
        """Attend le prochain message du client ; `None` quand la connexion se ferme."""
        ...

    async def envoyer(self, message: dict) -> None:
        """Émet un message vers le client (effet de bord réseau)."""
        ...


async def _resync_payload(
    fabrique_session, game_id: uuid.UUID, user_id: uuid.UUID, graine_hex: str, depuis: int
) -> dict:
    """Charge une session courte, relit la partie et calcule la resynchronisation depuis ``depuis``.

    On n'immobilise jamais une connexion de base pour toute la durée du canal : une session est
    ouverte le temps du calcul, puis rendue. La partie peut avoir disparu (purge) : on le signale
    par ``None`` plutôt que de lever.
    """
    async with fabrique_session() as db:
        game = await db.get(Game, game_id)
        if game is None:
            return {"type": "erreur", "code": "partie_absente", "message": "Partie introuvable."}
        return await resynchroniser(db, game, user_id=user_id, depuis=depuis)


async def _numero_courant(fabrique_session, game_id: uuid.UUID) -> int:
    """Le `current_numero` de la partie, porté par le battement de cœur ; -1 si elle a disparu."""
    async with fabrique_session() as db:
        game = await db.get(Game, game_id)
        return game.current_numero if game is not None else -1


async def piloter_canal(
    canal: Canal,
    *,
    abonne: Abonne,
    fabrique_session,
    game_id: uuid.UUID,
    graine_hex: str,
    depuis: int,
    intervalle_battement: float = INTERVALLE_BATTEMENT,
) -> None:
    """Pilote un canal : resync initiale, diffusion des coups, battement, resync à la demande.

    Déroulé : on envoie d'abord la resynchronisation depuis ``depuis`` (reprise exacte) ; puis on
    boucle en attendant, de front, un message du client et un message du hub, avec un délai de
    battement. Les messages du client gérés : ``souscrire``/``resync`` (le client redemande tout
    depuis un numéro — reconnexion ou trou détecté), ``ack`` (accusé de réception, pour la
    supervision), ``ping`` (→ ``pong``). À chaque silence de ``intervalle_battement`` secondes, un
    ``battement`` porte le numéro courant du serveur : le client y lit une éventuelle diffusion
    manquée et détecte une coupure s'il n'arrive plus.

    ``transmis`` est le plus grand numéro de coup réellement émis au client ; une resynchronisation
    après saturation repart de ``transmis + 1`` — donc sans rien perdre, et sans dépendre de
    l'ordre d'arrivée.
    """
    resync = await _resync_payload(fabrique_session, game_id, abonne.user_id, graine_hex, depuis)
    await canal.envoyer(resync)
    transmis = resync.get("numero", depuis) - 1 if resync.get("type") == "resync" else depuis - 1

    tache_recv = asyncio.ensure_future(canal.recevoir())
    tache_file = asyncio.ensure_future(abonne.file.get())
    try:
        while True:
            termines, _ = await asyncio.wait(
                {tache_recv, tache_file},
                timeout=intervalle_battement,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Saturation vue par le hub : on rattrape par une resync complète depuis transmis+1.
            if abonne.sature:
                abonne.sature = False
                rattrapage = await _resync_payload(
                    fabrique_session, game_id, abonne.user_id, graine_hex, transmis + 1
                )
                await canal.envoyer(rattrapage)
                if rattrapage.get("type") == "resync":
                    transmis = max(transmis, rattrapage["numero"] - 1)

            if not termines:
                # Expiration d'horloge (lots j-timer / j-deconnexion-abandon) : un silence est
                # l'occasion de vérifier qu'aucune horloge n'a expiré. Si oui, le coup est
                # journalisé et diffusé — action par défaut (fin de tour, défaite au temps), ou
                # **désertion** si un joueur déconnecté a dépassé sa grâce (forfait).
                async with fabrique_session() as db_exp:
                    resultat_exp = await expirer_horloge(db_exp, game_id)
                    catalogue_exp = (
                        await catalogue_pour_resultat(db_exp, resultat_exp)
                        if resultat_exp is not None
                        else None
                    )
                if resultat_exp is not None:
                    HUB.publier(
                        game_id,
                        resultat_exp,
                        graine_hex=graine_hex,
                        catalogue=catalogue_exp,
                    )
                # Silence : battement de cœur, porteur du numéro courant (détection de coupure +
                # rattrapage d'une dernière diffusion manquée côté client).
                numero = await _numero_courant(fabrique_session, game_id)
                await canal.envoyer({"type": "battement", "numero": numero})
                continue

            if tache_recv in termines:
                message = tache_recv.result()
                if message is None:
                    break  # déconnexion : fin propre du pilotage
                transmis = await _traiter_message_client(
                    canal, message, fabrique_session, game_id, abonne.user_id, graine_hex, transmis
                )
                tache_recv = asyncio.ensure_future(canal.recevoir())

            if tache_file in termines:
                diffusion = tache_file.result()
                await canal.envoyer(diffusion)
                if diffusion.get("type") == "evenement":
                    transmis = max(transmis, diffusion["numero"])
                tache_file = asyncio.ensure_future(abonne.file.get())
    finally:
        tache_recv.cancel()
        tache_file.cancel()


async def _traiter_message_client(
    canal: Canal,
    message: dict,
    fabrique_session,
    game_id: uuid.UUID,
    user_id: uuid.UUID,
    graine_hex: str,
    transmis: int,
) -> int:
    """Traite un message du client et renvoie le nouveau ``transmis``.

    Un message mal formé ou d'un type inconnu n'est pas avalé : il reçoit une erreur explicite
    (jamais un repli silencieux). Les types reconnus : ``souscrire``/``resync`` (resynchronisation
    depuis un numéro), ``ack`` (accusé, sans effet d'état) et ``ping`` (→ ``pong``).
    """
    type_message = message.get("type") if isinstance(message, dict) else None
    if type_message in ("resync", "souscrire"):
        depuis = message.get("depuis", 0)
        if not isinstance(depuis, int) or isinstance(depuis, bool) or depuis < 0:
            await canal.envoyer(
                {"type": "erreur", "code": "depuis_invalide", "message": "« depuis » attendu ≥ 0."}
            )
            return transmis
        resync = await _resync_payload(fabrique_session, game_id, user_id, graine_hex, depuis)
        await canal.envoyer(resync)
        if resync.get("type") == "resync":
            return max(transmis, resync["numero"] - 1)
        return transmis
    if type_message == "ack":
        return transmis
    if type_message == "ping":
        await canal.envoyer({"type": "pong"})
        return transmis
    await canal.envoyer(
        {
            "type": "erreur",
            "code": "type_inconnu",
            "message": f"Type de message inconnu : {type_message!r}.",
        }
    )
    return transmis
