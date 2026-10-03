"""Machine de **lancement d'une partie** : choix du deck, prêt, tirage au sort, bascule en partie.

Ce module est l'**enveloppe** qui conduit deux joueurs du salon d'attente (`j-invitations`) à une
partie en cours (`j-partie-service`). Il vit dans `apps/api` (il lit la base) ; le moteur `pbm_game`
reste pur — seul son :class:`~pbm_game.rng.Rng` (pur lui aussi) est sollicité, pour le pile ou face.

Quatre exigences du lot guident le code :

* **Le serveur fait autorité, même pour l'animation.** Le pile ou face R-4.7 est tiré ici, côté
  serveur, à partir de la graine de la partie ; l'écran ne fait que montrer un résultat déjà tombé.
* **Tout est persisté, donc repris après un F5.** Chaque étape est une écriture : un rechargement
  lit le statut courant et reprend à la bonne étape. On **commit** explicitement (le contrat de ce
  dépôt : un service qui veut persister commit — cf. `pbm_api.games.service`).
* **Le tirage est vérifiable après coup.** On publie l'**engagement** (empreinte de la graine)
  *avant* le tirage, on journalise le :class:`~pbm_game.rng.Tirage` du pile ou face, et on ne révèle
  la **graine** qu'une fois la partie terminée (la révéler tôt rendrait la pioche prévisible). Les
  deux joueurs recalculent alors le pile ou face hors du serveur (`verifier_engagement` +
  `rejouer_tirage`).
* **Un deck devenu injouable arrête le lancement, en disant pourquoi.** Entre la file et le
  lancement, une carte peut être **vendue** (possession perdue) ou son **script retiré** (D9) : on
  recontrôle à chaque étape et au lancement final — jamais de partie fantôme sur un deck mort.

**Règle appliquée — qui commence (R-4.7 / R-1.1).** R-4.7 fixe un **pile ou face** pour déterminer
qui commence ; le livret officiel (source de vérité, R-1.1) laisse au **gagnant du tirage** le choix
de commencer ou non. On implémente les deux : le pile ou face désigne le gagnant, qui choisit,
et **à défaut de choix dans le délai, le gagnant commence** — la lecture littérale de R-4.7. Le pile
ou face lui-même n'est jamais approximé : c'est exactement le i-ème tirage du flux
:data:`~pbm_game.rng.FLUX_QUI_COMMENCE` sous la graine de la partie.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pbm_game.rng import (
    FACE,
    FLUX_QUI_COMMENCE,
    GRAINE_MIN_OCTETS,
    Rng,
    engagement,
    tirage_vers_json,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks import energy
from pbm_api.games.construction import (  # noqa: F401 (joueur_id_de documenté)
    joueur_id_de,
    resoudre_deck,
)
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable, verifier_deck
from pbm_api.games.errors import GameError
from pbm_api.games.service import creer_partie, demarrer_partie
from pbm_api.models import (
    Card,
    CollectionItem,
    DeckCard,
    Game,
    GameInvitation,
    User,
)
from pbm_api.models.game_launch import (
    LANCEMENT_STATUT_ABANDONNE,
    LANCEMENT_STATUT_LANCE,
    LANCEMENT_STATUT_PREPARATION,
    LANCEMENT_STATUT_TIRAGE,
    GameLaunch,
)
from pbm_api.models.games import GAME_STATUS_TERMINEE
from pbm_api.models.invitations import INVITATION_STATUT_ACCEPTEE

logger = logging.getLogger(__name__)

#: Motif journalisé du pile ou face de début de partie — lisible sans table de correspondance.
MOTIF_TIRAGE = "R-4.7 tirage au sort du premier joueur"

#: Délai laissé au gagnant du tirage pour choisir de commencer ou non. Au-delà, le **choix par
#: défaut** s'applique : le gagnant commence (lecture littérale de R-4.7). Court par choix produit :
#: on ne fait pas attendre l'adversaire indéfiniment. Les tests passent ``maintenant`` pour franchir
#: l'échéance sans attendre.
DELAI_CHOIX = timedelta(seconds=30)


def _maintenant(fourni: datetime | None) -> datetime:
    """Instant courant (UTC, conscient du fuseau), ou celui fourni par un test (déterminisme)."""
    return fourni if fourni is not None else datetime.now(UTC)


# --- Erreurs du lot (chacune dit pourquoi ; la couche HTTP les traduit en statuts) -----------


class LancementIntrouvable(GameError):
    """L'invitation n'existe pas, ou l'appelant n'y a aucun rôle (→ 404, jamais 403).

    Même règle que les decks, les parties et les invitations : on ne révèle pas l'existence d'un
    objet qui n'est pas le vôtre.
    """


class InvitationPasAcceptee(GameError):
    """On tente de lancer depuis une invitation qui n'est pas (ou plus) acceptée (→ 409).

    Un lancement part d'un salon d'attente à deux — donc d'une invitation **acceptée**. Une
    invitation encore « envoyée », refusée, annulée ou expirée n'ouvre aucun salon.
    """


class LancementMauvaisePhase(GameError):
    """L'action demandée ne correspond pas au statut courant du lancement (→ 409).

    Porte le statut réel pour que le message dise l'état plutôt qu'un échec muet (p. ex. « se
    préparer » quand le tirage est déjà lancé).
    """

    def __init__(self, statut: str, attendu: str) -> None:
        self.statut = statut
        super().__init__(
            f"Action impossible au statut « {statut} » : elle n'est permise qu'en « {attendu} »."
        )


class PasLeGagnantDuTirage(GameError):
    """Seul le gagnant du pile ou face choisit de commencer ou non (→ 409).

    Ce n'est pas une fuite (les deux joueurs voient le tirage et son gagnant) : c'est une règle de
    tour — l'autre joueur n'a pas ce choix.
    """


# --- Vue (symétrique pour les deux joueurs, sans secret avant la fin) -------------------------


@dataclass
class CampLancement:
    """Un camp du lancement : l'utilisateur, son pseudo, le deck choisi, l'état « prêt »."""

    user_id: uuid.UUID
    pseudo: str | None
    deck_id: uuid.UUID | None
    pret: bool


@dataclass
class LancementVue:
    """La vue d'un lancement — identique pour les deux joueurs, **sans la graine** avant la fin.

    ``engagement`` et ``tirage`` sont publics dès le tirage (c'est ce qui le rend vérifiable). La
    ``graine`` n'est renseignée qu'une fois la partie **terminée** (commit-reveal) : avant, elle
    reste secrète, sinon la pioche adverse serait prévisible.
    """

    invitation_id: uuid.UUID
    launch_id: uuid.UUID
    statut: str
    inviter: CampLancement
    invitee: CampLancement
    engagement: str | None
    tirage: dict | None
    tirage_gagnant_user_id: uuid.UUID | None
    premier_joueur_user_id: uuid.UUID | None
    choix_commencer: bool | None
    choix_expire_at: datetime | None
    game_id: uuid.UUID | None
    graine: str | None


# --- Contrôle de légalité et de possession (carte vendue, script retiré) ---------------------


async def _cartes_non_possedees(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> list[tuple[str, str]]:
    """Les cartes du deck dont le joueur ne possède plus assez d'exemplaires — « carte vendue ».

    Même logique de possession que `decks.legality` (code ``not_owned``, « même règle serveur
    et écran ») : les **Énergies de base** sont fournies, les exemplaires signalés
    **contrefaçon** ne comptent pas. Renvoie la liste des ``(nom, raison)`` — vide si tout est
    possédé. Ne lève pas : l'appelant décide (le deck peut être injouable pour d'autres raisons).
    """
    rows = (
        await db.execute(
            select(Card, DeckCard.quantity)
            .join(DeckCard, DeckCard.card_id == Card.id)
            .where(DeckCard.deck_id == deck_id)
        )
    ).all()
    card_ids = [card.id for card, _ in rows]
    owned: dict[uuid.UUID, int] = {}
    if card_ids:
        comptes = await db.execute(
            select(CollectionItem.card_id, func.count())
            .where(
                CollectionItem.user_id == user_id,
                CollectionItem.card_id.in_(card_ids),
                CollectionItem.counterfeit_suspected.is_(False),
            )
            .group_by(CollectionItem.card_id)
        )
        owned = {card_id: compte for card_id, compte in comptes.all()}

    manquants: list[tuple[str, str]] = []
    for card, quantity in rows:
        if energy.is_basic_energy(card.supertype, card.name, card.energy_type):
            continue  # Énergie de base : fournie, jamais un manque de possession.
        possede = owned.get(card.id, 0)
        if possede < quantity:
            manque = quantity - possede
            manquants.append(
                (
                    card.name,
                    f"il manque {manque} exemplaire(s) dans votre collection "
                    f"({possede} possédé(s), {quantity} dans le deck) — carte vendue ?",
                )
            )
    return manquants


async def verifier_lancable(db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID) -> None:
    """Vérifie qu'un deck est **lançable** par son joueur, ou **lève** en nommant ce qui manque.

    Trois contrôles, dans l'ordre : **propriété** (le deck est le vôtre, sinon
    :class:`~pbm_api.games.entry.DeckIntrouvable` → 404, pas de fuite), **scripts D9** (chaque carte
    se compile pour le moteur, sinon :class:`~pbm_api.games.entry.DeckInjouable` → 422, cartes
    nommées), puis **possession** (chaque carte non-Énergie est possédée en quantité suffisante,
    sinon :class:`DeckInjouable` → 422). C'est le « dernier contrôle de légalité
    et de possession » du lot : il attrape une carte vendue ou un script retiré depuis l'entrée.

    La **légalité de format / taille** n'est pas imposée ici : au jalon J1 (« laid
    mais juste »), c'est la mise en place `j-initialisation` qui fera du deck complet l'unité de jeu
    (report explicite déjà documenté dans `pbm_api.games.entry`), pas un abandon silencieux.
    """
    await verifier_deck(db, user_id, deck_id)  # propriété (404) + scripts D9 (422), cartes nommées
    non_possedees = await _cartes_non_possedees(db, user_id, deck_id)
    if non_possedees:
        raise DeckInjouable(non_possedees)


# --- Chargement et rôles ---------------------------------------------------------------------


async def _charger_invitation_participant(
    db: AsyncSession, invitation_id: uuid.UUID, user_id: uuid.UUID
) -> GameInvitation:
    """Charge l'invitation si l'appelant y participe, sinon :class:`LancementIntrouvable` (404)."""
    invitation = await db.get(GameInvitation, invitation_id)
    if invitation is None or user_id not in {
        invitation.inviter_user_id,
        invitation.invitee_user_id,
    }:
        raise LancementIntrouvable("Invitation introuvable.")
    return invitation


def _est_inviteur(invitation: GameInvitation, user_id: uuid.UUID) -> bool:
    """Vrai si l'utilisateur est l'émetteur de l'invitation (siège « inviter » du lancement)."""
    return invitation.inviter_user_id == user_id


# --- Création / obtention (avec résolution paresseuse du choix par défaut) --------------------


async def obtenir_ou_creer(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    user_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> tuple[GameLaunch, GameInvitation]:
    """Le lancement d'une invitation acceptée (créé au premier accès), prêt à être affiché.

    404 si l'invitation n'existe pas ou si l'appelant n'y a aucun rôle ; 409 si elle n'est pas
    acceptée. Au premier accès, le lancement naît en **préparation**, chaque camp pré-garni du deck
    qu'il a **annoncé** dans le salon (il pourra le changer). Si le délai de
    choix est écoulé en phase de tirage, le **choix par défaut** est résolu ici
    — ce qui fait de cette fonction le point de reprise après un F5 **et** l'échéance du délai.
    """
    maintenant = _maintenant(maintenant)
    invitation = await _charger_invitation_participant(db, invitation_id, user_id)
    if invitation.statut != INVITATION_STATUT_ACCEPTEE:
        raise InvitationPasAcceptee(
            f"L'invitation n'est pas acceptée (statut « {invitation.statut} ») : "
            "aucun salon d'attente n'est ouvert."
        )

    launch = (
        await db.execute(select(GameLaunch).where(GameLaunch.invitation_id == invitation_id))
    ).scalar_one_or_none()
    if launch is None:
        launch = GameLaunch(
            invitation_id=invitation_id,
            statut=LANCEMENT_STATUT_PREPARATION,
            inviter_deck_id=invitation.inviter_deck_id,
            invitee_deck_id=invitation.invitee_deck_id,
        )
        db.add(launch)
        await db.commit()
        await db.refresh(launch)

    await _resoudre_defaut_si_echu(db, launch, invitation, maintenant)
    return launch, invitation


async def _resoudre_defaut_si_echu(
    db: AsyncSession, launch: GameLaunch, invitation: GameInvitation, maintenant: datetime
) -> None:
    """Applique le **choix par défaut** (le gagnant commence) si le délai de choix est écoulé.

    N'agit qu'en phase de tirage, choix non encore tranché, échéance passée. Si un deck est devenu
    injouable entre-temps, le lancement par défaut échoue (:class:`DeckInjouable`) : on **ne tue pas
    le défaut en silence** — on laisse le lancement en « tirage » (état observable, aucune partie
    fantôme) et on journalise la cause ; elle sera renommée au joueur dès qu'il agira explicitement.
    """
    if (
        launch.statut != LANCEMENT_STATUT_TIRAGE
        or launch.choix_commencer is not None
        or launch.choix_expire_at is None
        or maintenant < launch.choix_expire_at
    ):
        return
    try:
        await _lancer(db, launch, invitation, commencer=True, maintenant=maintenant)
    except DeckInjouable as exc:
        logger.warning(
            "Lancement par défaut de l'invitation %s impossible : %s",
            invitation.id,
            exc,
        )


# --- Préparation (choix du deck + prêt) ------------------------------------------------------


async def se_preparer(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    user_id: uuid.UUID,
    deck_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
) -> tuple[GameLaunch, GameInvitation]:
    """Choisit son deck et se déclare **prêt** ; lance le tirage si les deux le sont.

    ``deck_id`` ``None`` garde le deck déjà choisi/annoncé ; faute de deck, l'appel lève
    :class:`~pbm_api.games.entry.DeckIntrouvable` (on ne se prépare pas sans deck). Le deck est
    recontrôlé (propriété, scripts D9, possession) : injouable → :class:`DeckInjouable` (422, cartes
    nommées), et le joueur reste non prêt. Quand **les deux** camps sont prêts, le tirage au sort
    part automatiquement (graine engagée, pile ou face R-4.7).
    """
    maintenant = _maintenant(maintenant)
    launch, invitation = await obtenir_ou_creer(
        db, invitation_id=invitation_id, user_id=user_id, maintenant=maintenant
    )
    if launch.statut != LANCEMENT_STATUT_PREPARATION:
        raise LancementMauvaisePhase(launch.statut, LANCEMENT_STATUT_PREPARATION)

    est_inviteur = _est_inviteur(invitation, user_id)
    deck_choisi = deck_id or (launch.inviter_deck_id if est_inviteur else launch.invitee_deck_id)
    if deck_choisi is None:
        raise DeckIntrouvable(
            "Aucun deck choisi : sélectionnez un deck avant de vous déclarer prêt."
        )

    await verifier_lancable(db, user_id, deck_choisi)

    if est_inviteur:
        launch.inviter_deck_id = deck_choisi
        launch.inviter_pret = True
    else:
        launch.invitee_deck_id = deck_choisi
        launch.invitee_pret = True

    if launch.inviter_pret and launch.invitee_pret:
        _demarrer_tirage(launch, invitation, maintenant)

    await db.commit()
    await db.refresh(launch)
    return launch, invitation


def _demarrer_tirage(launch: GameLaunch, invitation: GameInvitation, maintenant: datetime) -> None:
    """Engage la graine, **publie l'engagement**, tire le pile ou face R-4.7 et fixe l'échéance.

    L'engagement (empreinte de la graine) est posé **avant** que le tirage ne compte : c'est le
    commit du commit-reveal. Le pile ou face est le tirage ``0`` du flux
    :data:`~pbm_game.rng.FLUX_QUI_COMMENCE` sous cette graine. **Convention de face** : ``face`` =
    l'émetteur gagne, ``pile`` = l'invité — déterministe, donc revérifiable. La graine reste secrète
    (jamais exposée avant la fin de partie) ; seul l'engagement et le tirage sont publiables.
    """
    graine_hex = os.urandom(max(32, GRAINE_MIN_OCTETS)).hex()
    rng = Rng(bytes.fromhex(graine_hex))
    resultat = rng.pile_ou_face(FLUX_QUI_COMMENCE, MOTIF_TIRAGE)
    tirage = rng.journal()[0]

    launch.graine = graine_hex
    launch.engagement = engagement(bytes.fromhex(graine_hex))
    launch.tirage = tirage_vers_json(tirage)
    launch.tirage_gagnant_user_id = (
        invitation.inviter_user_id if resultat == FACE else invitation.invitee_user_id
    )
    launch.choix_expire_at = maintenant + DELAI_CHOIX
    launch.statut = LANCEMENT_STATUT_TIRAGE


# --- Choix du gagnant + bascule en partie ----------------------------------------------------


async def choisir(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    user_id: uuid.UUID,
    commencer: bool,
    maintenant: datetime | None = None,
) -> tuple[GameLaunch, GameInvitation]:
    """Le **gagnant du tirage** choisit de commencer (ou non) : la partie est créée et on bascule.

    409 si le lancement n'est pas en phase de tirage, 409 si l'appelant n'est pas le gagnant du
    pile ou face. Avant de créer la partie, les **deux** decks sont recontrôlés : un deck devenu
    injouable arrête le lancement en nommant les cartes (:class:`DeckInjouable`, 422), **sans partie
    fantôme** (le lancement reste en tirage). Sinon, la partie est créée avec la graine et le
    premier joueur assis au siège 0 (le tour 1 est celui qui commence, invariant du moteur).
    """
    maintenant = _maintenant(maintenant)
    launch, invitation = await obtenir_ou_creer(
        db, invitation_id=invitation_id, user_id=user_id, maintenant=maintenant
    )
    if launch.statut != LANCEMENT_STATUT_TIRAGE:
        raise LancementMauvaisePhase(launch.statut, LANCEMENT_STATUT_TIRAGE)
    if launch.tirage_gagnant_user_id != user_id:
        raise PasLeGagnantDuTirage("Seul le gagnant du tirage au sort choisit qui commence.")

    await _lancer(db, launch, invitation, commencer=commencer, maintenant=maintenant)
    await db.refresh(launch)
    return launch, invitation


async def _lancer(
    db: AsyncSession,
    launch: GameLaunch,
    invitation: GameInvitation,
    *,
    commencer: bool,
    maintenant: datetime,
) -> None:
    """Recontrôle les deux decks, crée la partie et passe le lancement en « lancé ».

    Le gagnant commence si ``commencer`` est vrai, sinon c'est l'autre. Les deux decks sont
    revérifiés **avant** création : un échec lève :class:`DeckInjouable` et laisse le lancement
    intact (aucune partie n'est créée — critère « sans partie fantôme »). La partie reçoit **la
    graine engagée** (le même aléatoire que le tirage) et l'ordre des sièges place le premier joueur
    au siège 0.
    """
    gagnant = launch.tirage_gagnant_user_id
    autre = (
        invitation.invitee_user_id
        if gagnant == invitation.inviter_user_id
        else invitation.inviter_user_id
    )
    premier = gagnant if commencer else autre

    deck_inviteur = launch.inviter_deck_id
    deck_invite = launch.invitee_deck_id
    if deck_inviteur is None or deck_invite is None:
        # Ne peut normalement pas arriver (les deux sont prêts avec un deck) : on le dit, sans
        # créer une partie bancale.
        raise DeckIntrouvable("Un deck manque au lancement : impossible de créer la partie.")

    # Dernier contrôle de légalité et de possession, les deux camps — carte vendue / script retiré.
    await verifier_lancable(db, invitation.inviter_user_id, deck_inviteur)
    await verifier_lancable(db, invitation.invitee_user_id, deck_invite)

    # Le premier joueur est assis au siège 0 (joueur_a) : le moteur fait du siège 0 le joueur actif
    # du tour 1, et « le tour 1 est celui qui commence » (invariant de `pbm_game.state.Tour`).
    if premier == invitation.inviter_user_id:
        joueur_a = (invitation.inviter_user_id, deck_inviteur)
        joueur_b = (invitation.invitee_user_id, deck_invite)
    else:
        joueur_a = (invitation.invitee_user_id, deck_invite)
        joueur_b = (invitation.inviter_user_id, deck_inviteur)

    game = await creer_partie(
        db, joueur_a=joueur_a, joueur_b=joueur_b, graine_hex=launch.graine, maintenant=maintenant
    )
    # Lancer la mise en place (R-4) : mélange, pioche de sept, mulligans — la partie attend alors le
    # placement des joueurs (lot ``j-coups-joueur``). Sans ce coup système, une partie lancée
    # restait decks en pioche, injouable.
    await demarrer_partie(db, game, maintenant)

    launch.choix_commencer = commencer
    launch.premier_joueur_user_id = premier
    launch.game_id = game.id
    launch.statut = LANCEMENT_STATUT_LANCE
    await db.commit()


# --- Abandon (déconnexion / renoncement avant le lancement) ----------------------------------


async def abandonner(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    user_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> tuple[GameLaunch, GameInvitation]:
    """Un joueur quitte avant le lancement : le lancement est figé, aucune partie n'est créée.

    Couvre la déconnexion ou le renoncement d'un camp avant d'être prêt (ou pendant le tirage). 409
    si la partie est déjà lancée (on n'abandonne pas une partie en cours par ce chemin — c'est le
    lot de l'abandon en partie). Les autres statuts finaux restent idempotents.
    """
    maintenant = _maintenant(maintenant)
    launch, invitation = await obtenir_ou_creer(
        db, invitation_id=invitation_id, user_id=user_id, maintenant=maintenant
    )
    if launch.statut == LANCEMENT_STATUT_LANCE:
        raise LancementMauvaisePhase(launch.statut, LANCEMENT_STATUT_PREPARATION)
    if launch.statut != LANCEMENT_STATUT_ABANDONNE:
        launch.statut = LANCEMENT_STATUT_ABANDONNE
        await db.commit()
        await db.refresh(launch)
    return launch, invitation


# --- Vue (reveal de la graine seulement à la fin de la partie) -------------------------------


async def composer_vue(
    db: AsyncSession, *, launch: GameLaunch, invitation: GameInvitation
) -> LancementVue:
    """Assemble la vue du lancement ; révèle la graine **seulement** si la partie est finie.

    La vue est identique pour les deux joueurs (comme le salon d'attente). La ``graine`` n'est
    révélée que lorsque la partie liée est **terminée** (commit-reveal) : avant, elle reste nulle.
    """
    inviteur = await db.get(User, invitation.inviter_user_id)
    invite = (
        await db.get(User, invitation.invitee_user_id)
        if invitation.invitee_user_id is not None
        else None
    )
    graine_revelee = await _graine_si_partie_terminee(db, launch)
    return LancementVue(
        invitation_id=invitation.id,
        launch_id=launch.id,
        statut=launch.statut,
        inviter=CampLancement(
            user_id=invitation.inviter_user_id,
            pseudo=inviteur.pseudo if inviteur else None,
            deck_id=launch.inviter_deck_id,
            pret=launch.inviter_pret,
        ),
        invitee=CampLancement(
            user_id=invitation.invitee_user_id,
            pseudo=invite.pseudo if invite else None,
            deck_id=launch.invitee_deck_id,
            pret=launch.invitee_pret,
        ),
        engagement=launch.engagement,
        tirage=launch.tirage,
        tirage_gagnant_user_id=launch.tirage_gagnant_user_id,
        premier_joueur_user_id=launch.premier_joueur_user_id,
        choix_commencer=launch.choix_commencer,
        choix_expire_at=launch.choix_expire_at,
        game_id=launch.game_id,
        graine=graine_revelee,
    )


async def _graine_si_partie_terminee(db: AsyncSession, launch: GameLaunch) -> str | None:
    """La graine révélée si la partie liée est terminée, sinon ``None`` (secret maintenu)."""
    if launch.game_id is None:
        return None
    game = await db.get(Game, launch.game_id)
    if game is None or game.status != GAME_STATUS_TERMINEE:
        return None
    return launch.graine
