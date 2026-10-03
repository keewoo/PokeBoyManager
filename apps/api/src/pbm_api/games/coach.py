"""Service du **coach IA** (lot ``j-coach-ia``, jalon J4, DJ7) : conseil et bilan de fin.

Ce module fait le lien entre les routes HTTP (:mod:`pbm_api.routers.games`) et le moteur de conseil
pur (:mod:`pbm_api.games.coach_ia`). Il porte les **garde-fous**, indépendants de FastAPI (donc
testables directement), et toutes les lectures/écritures de base :

* résout la partie **bornée au participant** (404 pour un objet d'autrui, jamais de fuite) ;
* refuse hors du cadre : coach désactivé par le joueur, partie entre deux humains (le conseil n'a sa
  place qu'en **entraînement**), plafond de conseils atteint, clé IA absente, partie non terminée
  (pour le bilan) ;
* construit le fournisseur depuis la clé du joueur — la clé reste **ici**, jamais journalisée, et le
  fournisseur est **refermé** à la fin ;
* n'applique **aucun** coup : un conseil est une suggestion, le geste reste celui du joueur.

Un échec de l'IA n'est **jamais** un repli silencieux : le conseil absent se dit (``raison``), et un
bilan impossible lève :class:`BilanIndisponible` (→ 502) plutôt que de rendre un texte vide.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal.modele import AUTEUR_SYSTEME
from pbm_game.state import vue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.coach_ia import (
    ResultatConseil,
    construire_lignes_journal,
    decrire_action,
    proposer_conseil,
    resumer_partie,
)
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import GameError, PartieNonActive
from pbm_api.games.service import (
    _game_pour_participant,
    _game_sous_verrou,
    reprendre_partie,
)
from pbm_api.models import User
from pbm_api.models.games import GAME_STATUS_EN_COURS, GAME_STATUS_TERMINEE, GameEvent

logger = logging.getLogger(__name__)


# --- Refus nommés (chacun mappé à un code HTTP par la route) --------------------------------------


class CoachDesactive(GameError):
    """Le joueur a **désactivé** le coach dans son profil (``users.coach_actif`` faux) → 409.

    Jamais un repli muet : on refuse en le disant, pour que l'écran propose de le réactiver.
    """


class ConseilHorsEntrainement(GameError):
    """Conseil demandé dans une partie **entre deux joueurs humains** → 409 (critère du lot).

    Un conseil d'IA n'a sa place qu'en **entraînement** : dans un vrai match, il fausserait le jeu.
    """


class PlafondConseils(GameError):
    """Le plafond de conseils de la partie est atteint (``settings.coach_max_conseils``) → 409."""


class CleCoachIndisponible(GameError):
    """Le joueur n'a **aucune clé IA** utilisable → 422.

    On refuse clairement (l'écran invite à déposer une clé dans le profil) plutôt qu'un silence.
    """


class PartieNonTerminee(GameError):
    """Bilan sur une partie **pas terminée** → 409 : rien à retenir d'une partie en cours."""


class BilanIndisponible(GameError):
    """L'IA n'a pas pu produire le bilan (délai, fournisseur injoignable, réponse vide) → 502.

    On le **dit** (jamais un bilan vide passé pour un succès) : l'écran invite à réessayer.
    """


# --- Conseil pendant la partie -------------------------------------------------------------------


@dataclass
class ResultatConseilService:
    """Ce que :func:`conseil_pour_joueur` rend à la route : le conseil + l'état du budget."""

    conseil: ResultatConseil
    conseils_utilises: int
    conseils_restants: int


def _est_son_tour(etat, jid: str) -> bool:
    """Vrai quand c'est au joueur ``jid`` de jouer (phase de jeu, mise en place, ou demande à lui).

    On ne demande pas de conseil hors de son tour : ce serait consommer la clé pour rien. On lit
    l'état du moteur (autorité), comme la boucle du joueur auto : partie finie → non ; mise en
    place → oui tant qu'il n'a pas placé ; résolution → oui si la demande lui est adressée ;
    sinon → oui si l'Actif est le sien.
    """
    if etat.terminee:
        return False
    if etat.mise_en_place is not None:
        idx = next((i for i, j in enumerate(etat.joueurs) if j.id == jid), None)
        if idx is None:
            return False
        return etat.mise_en_place.placements[idx] is None
    if etat.resolution is not None:
        return etat.resolution.demande.destinataire == jid
    return etat.tour.joueur_actif == jid


async def conseil_pour_joueur(
    db: AsyncSession,
    *,
    game_id: uuid.UUID,
    user: User,
    max_conseils: int,
) -> ResultatConseilService:
    """Donne un conseil au joueur pour son tour, ou **refuse** / **dit** qu'il n'y en a pas.

    Garde-fous, dans l'ordre (chacun un refus nommé) : participation (404), coach activé, partie
    d'entraînement (pas entre deux humains), partie en cours, plafond de conseils, clé IA présente.
    Puis : si ce n'est pas son tour, on le dit **sans** appeler l'IA (rien à consommer). Sinon on
    appelle l'IA sur sa seule vue, **hors verrou** (un appel réseau peut durer, on ne bloque pas la
    ligne de partie pendant ce temps), puis on incrémente le compteur **sous verrou** et on commit —
    seulement si un appel a réellement eu lieu.

    N'applique **aucun** coup : le conseil est une suggestion que le joueur jouera lui-même.
    """
    game = await _game_pour_participant(db, game_id, user.id)
    if not user.coach_actif:
        raise CoachDesactive(
            "Le coach est désactivé dans ton profil : active-le pour recevoir des conseils."
        )
    if not game.entrainement:
        raise ConseilHorsEntrainement(
            "Un conseil n'est disponible qu'en partie d'entraînement, jamais dans une partie entre "
            "deux joueurs."
        )
    if game.status != GAME_STATUS_EN_COURS:
        raise PartieNonActive("La partie n'est plus en cours : aucun conseil à donner.")
    if game.conseils_utilises >= max_conseils:
        raise PlafondConseils(
            f"Tu as utilisé tous tes conseils pour cette partie (plafond : {max_conseils})."
        )
    credential = await get_default_credential(db, user)
    if credential is None:
        raise CleCoachIndisponible(
            "Aucune clé IA enregistrée : ajoute une clé (Anthropic, Gemini ou OpenAI) dans ton "
            "profil pour recevoir des conseils."
        )

    etat, _rng = await reprendre_partie(db, game)
    jid = joueur_id_de(user.id)
    restants = max(0, max_conseils - game.conseils_utilises)
    if not _est_son_tour(etat, jid):
        return ResultatConseilService(
            conseil=ResultatConseil(
                coup=None, raison="Ce n'est pas à toi de jouer pour l'instant."
            ),
            conseils_utilises=game.conseils_utilises,
            conseils_restants=restants,
        )

    catalogue = await construire_catalogue_jeu(db, etat)
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    fournisseur_enum, cle = credential
    # La clé déchiffrée ne sert qu'ici, à construire le fournisseur ; jamais journalisée.
    provider = create_provider(fournisseur_enum, cle)
    try:
        conseil = await proposer_conseil(provider, vue(etat, jid), legales)
    finally:
        await provider.aclose()

    utilises = game.conseils_utilises
    if conseil.appel_effectue:
        # Re-chargement sous verrou pour l'incrément : on n'a pas tenu la ligne pendant l'appel
        # IA (qui peut durer), et le verrou sérialise deux demandes concurrentes.
        verrou = await _game_sous_verrou(db, game_id)
        if verrou is not None:
            verrou.conseils_utilises += 1
            if conseil.usage is not None:
                await record_usage(db, user, conseil.usage, commit=False)
            await db.commit()
            utilises = verrou.conseils_utilises
        else:  # la partie a disparu entre-temps (rare) : rien à écrire, on relâche proprement
            await db.rollback()
    return ResultatConseilService(
        conseil=conseil,
        conseils_utilises=utilises,
        conseils_restants=max(0, max_conseils - utilises),
    )


# --- Bilan de fin de partie ----------------------------------------------------------------------


@dataclass
class ResultatBilanService:
    """Ce que :func:`bilan_de_partie` rend à la route : le résumé et les moments **vérifiés**.

    ``moments`` est une liste de ``{"numero", "etiquette", "commentaire"}`` : chaque numéro est une
    entrée réelle du journal, et ``etiquette`` en est la description lisible (affichage).
    """

    resume: str
    moments: list[dict] = field(default_factory=list)


def _resultat_lisible(game, user: User) -> str:
    """L'issue de la partie en une phrase, du point de vue du joueur (pour le message du bilan)."""
    if game.vainqueur_user_id == user.id:
        issue = "tu as gagné"
    elif game.vainqueur_user_id is None:
        issue = "match nul"
    else:
        issue = "tu as perdu"
    return f"{issue} ({game.raison_fin or 'fin de partie'})"


async def bilan_de_partie(
    db: AsyncSession, *, game_id: uuid.UUID, user: User
) -> ResultatBilanService:
    """Produit le bilan d'une partie **terminée**, en ne citant que des coups réellement joués.

    Garde-fous : participation (404), coach activé, partie terminée, clé IA présente. Lit le
    **journal** (pas l'état complet), en tire les coups joués (les coups système sont écartés),
    construit le fournisseur depuis la clé du joueur, demande le bilan et **vérifie** chaque moment
    cité contre les numéros réels du journal. Enregistre l'usage IA. Un bilan impossible lève
    :class:`BilanIndisponible` (jamais un texte vide passé pour un succès).
    """
    game = await _game_pour_participant(db, game_id, user.id)
    if not user.coach_actif:
        raise CoachDesactive(
            "Le coach est désactivé dans ton profil : active-le pour recevoir un bilan."
        )
    if game.status != GAME_STATUS_TERMINEE:
        raise PartieNonTerminee("Le bilan n'est disponible qu'une fois la partie terminée.")
    credential = await get_default_credential(db, user)
    if credential is None:
        raise CleCoachIndisponible(
            "Aucune clé IA enregistrée : ajoute une clé (Anthropic, Gemini ou OpenAI) dans ton "
            "profil pour recevoir un bilan."
        )

    rows = (
        await db.execute(
            select(GameEvent).where(GameEvent.game_id == game_id).order_by(GameEvent.numero)
        )
    ).scalars().all()
    jid = joueur_id_de(user.id)
    entrees = [(r.numero, r.auteur, (r.action or {}).get("type", "")) for r in rows]
    lignes, numeros_valides = construire_lignes_journal(entrees, jid)
    # Étiquette lisible par numéro, pour habiller les moments renvoyés (même source que les lignes).
    descriptions: dict[int, str] = {}
    for numero, auteur, type_action in entrees:
        if auteur == AUTEUR_SYSTEME:
            continue
        qui = "Toi" if auteur == jid else "Ton adversaire"
        descriptions[numero] = f"{qui} {decrire_action(type_action)}"

    fournisseur_enum, cle = credential
    provider = create_provider(fournisseur_enum, cle)
    try:
        res = await resumer_partie(
            provider, lignes, numeros_valides, resultat=_resultat_lisible(game, user)
        )
    finally:
        await provider.aclose()

    if res.usage is not None:
        await record_usage(db, user, res.usage, commit=True)
    if res.resume is None:
        raise BilanIndisponible(
            res.raison or "Le bilan n'a pas pu être généré. Réessaie dans un instant."
        )

    moments = [
        {
            "numero": m.numero,
            "etiquette": descriptions.get(m.numero, ""),
            "commentaire": m.commentaire,
        }
        for m in res.moments
    ]
    return ResultatBilanService(resume=res.resume, moments=moments)


__all__ = [
    "CoachDesactive",
    "ConseilHorsEntrainement",
    "PlafondConseils",
    "CleCoachIndisponible",
    "PartieNonTerminee",
    "BilanIndisponible",
    "ResultatConseilService",
    "ResultatBilanService",
    "conseil_pour_joueur",
    "bilan_de_partie",
]
