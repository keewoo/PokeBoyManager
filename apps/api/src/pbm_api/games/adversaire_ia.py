"""Adversaire **IA** d'une partie d'entraînement : l'IA du joueur raisonne et explique ses coups.

Lot ``j-adversaire-ia`` (jalon J4, DJ7). DJ7 a tranché : le bot heuristique d'abord
(``pbm_api.games.bot``), puis une IA branchée sur la **clé du joueur** (coffre ``pbm_api.ai``). Ce
module porte le **décideur IA** : à chaque fois que c'est au joueur automatique de jouer, il reçoit
la **vue projetée** de son camp — jamais l'état complet — et la liste des coups légaux étiquetés,
et il choisit **un index** dans cette liste puis l'explique en une phrase simple, en français.

Quatre principes, chacun payé par une règle du dépôt :

* **L'IA joue avec la même vue que n'importe quel joueur.** Le message ne contient que
  :func:`pbm_game.state.projection.vue` (qui cache déjà la main adverse, l'ordre de la pioche, les
  récompenses) et les étiquettes des coups légaux de l'acteur. Laisser l'IA voir l'état complet
  « pour qu'elle joue mieux » serait de la triche — et un enfant ne battrait jamais un adversaire
  qui voit sa main (risque nommé du lot). La non-fuite est **vérifiée par un test** qui parcourt le
  message.
* **L'IA ne contourne ni la validation du moteur ni l'autorité du serveur.** Elle ne renvoie pas une
  action libre : elle choisit un **index** dans la liste légale que le moteur a calculée, donc le
  coup joué est **légal par construction**. Un index hors bornes est traité comme un échec, jamais
  comme un coup inventé (D9).
* **Un échec n'est jamais un repli silencieux.** Réponse invalide, absente, trop lente, ou plafond
  d'appels atteint : c'est le **bot** qui joue ce coup, et le journal le **dit** (« Mon IA n'a pas
  pu jouer … — le bot a joué à sa place »). Jamais un coup inventé, jamais un silence.
* **La clé du joueur ne sort jamais.** Ce module ne manipule qu'un :class:`AIProvider` déjà
  construit (la clé déchiffrée reste dans l'appelant, :mod:`pbm_api.games.bot`) ; il ne journalise
  ni ne renvoie jamais la clé.

Ce module ne connaît **ni la base, ni FastAPI** : il reçoit un fournisseur et des données pures, et
renvoie une décision. L'enregistrement de l'usage, l'incrément du compteur de budget et l'écriture
au journal restent à l'appelant (:mod:`pbm_api.games.bot`), qui tient la transaction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pbm_game.actions.modele import ActionLegale
from pbm_game.journal.modele import ACTION_ABANDONNER
from pydantic import BaseModel, Field

from pbm_api.ai.base import AIProvider, ExtractionUsage
from pbm_api.ai.errors import AIProviderError

logger = logging.getLogger(__name__)

#: Nombre maximal d'appels à l'IA du joueur **par partie** (plafond de budget, lot j-adversaire-ia).
#: Au-delà, l'IA s'arrête proprement et le bot termine la partie — le journal le dit (jamais un
#: dépassement muet de la clé du joueur). Compté côté base (``games.ia_appels``), donc persistant
#: au fil des coups d'une même partie.
MAX_APPELS_PAR_PARTIE = 60

#: Délai maximal accordé à l'IA pour **un** coup. Au-delà, on ne fait pas attendre l'enfant devant
#: un écran muet (principe du jeu) : le bot joue à sa place et le journal l'explique.
DELAI_MAX_COUP_S = 20.0

#: Longueur maximale d'une explication affichée dans le journal : une ou deux phrases simples. On
#: tronque proprement plutôt que de laisser l'IA inonder le fil (lisible pour un enfant de 11 ans).
MAX_LONGUEUR_EXPLICATION = 240


class DecisionIA(BaseModel):
    """La réponse structurée attendue de l'IA : **quel** coup légal jouer, et **pourquoi**.

    ``index`` désigne un coup dans la liste légale **numérotée** fournie dans le message (0 = le
    premier). L'IA ne fabrique pas d'action libre : elle choisit parmi ce que le moteur autorise,
    ce qui garantit la légalité et vaut anti-triche. ``explication`` est une phrase courte en
    français, lisible par un enfant, montrée dans le journal de la partie.
    """

    index: int = Field(
        description="Le numéro du coup choisi dans la liste des coups légaux (0 pour le premier)."
    )
    explication: str = Field(
        description=(
            "Une phrase courte, en français simple, qui explique pourquoi tu joues ce coup "
            "(comme à un enfant de 11 ans)."
        )
    )


@dataclass
class ResultatDecision:
    """Ce que le décideur rend à la boucle du joueur automatique.

    * ``coup`` — le coup à appliquer (choisi par l'IA, ou par le bot en repli), ou ``None`` s'il n'y
      a aucun coup jouable (la boucle rend alors la main, jamais un coup inventé) ;
    * ``explication`` — la phrase de l'IA à journaliser quand elle a joué (sinon ``None``) ;
    * ``bascule_bot`` — vrai quand l'IA a échoué et que le **bot** a joué ce coup à sa place ;
    * ``raison`` — pourquoi l'IA n'a pas joué (délai, réponse invalide, fournisseur injoignable…),
      pour le journal ; jamais la clé ni le détail brut du fournisseur ;
    * ``usage`` — les jetons consommés par l'appel réel, ou ``None`` si aucun appel n'a abouti ;
    * ``appel_effectue`` — vrai dès qu'une requête a été **envoyée** au fournisseur (même ratée) :
      elle compte dans le budget de la partie, car elle a pu consommer le quota de la clé du joueur.
    """

    coup: ActionLegale | None
    explication: str | None = None
    bascule_bot: bool = False
    raison: str | None = None
    usage: ExtractionUsage | None = None
    appel_effectue: bool = False

    def commentaire_journal(self) -> str | None:
        """La ligne à écrire au journal pour ce coup — l'explication de l'IA, ou la note de repli.

        Jamais ``None`` quand l'IA a basculé sur le bot : le repli doit **se voir** (règle du dépôt
        contre les replis silencieux). ``None`` seulement quand l'IA a joué sans rien à dire (cas
        improbable : explication vide déjà remplacée par un défaut).
        """
        if self.bascule_bot:
            motif = self.raison or "réponse inexploitable"
            return f"Mon IA n'a pas pu jouer ({motif}) — le bot a joué à sa place."
        return self.explication


#: Signature d'une fonction de décision de **bot** (``pbm_sim.bots``) : vue projetée + coups légaux
#: + source d'aléa → un coup légal, ou ``None`` s'il n'y a rien à jouer. Sert de **repli** à l'IA.
RepliBot = Callable[[dict, Sequence[ActionLegale], random.Random], ActionLegale | None]

#: Signature du **joueur automatique** unifié (bot ou IA) que la boucle d'entraînement appelle : à
#: partir de la vue projetée, des coups légaux et d'une source d'aléa, il rend une
#: :class:`ResultatDecision`. Le bot et l'IA l'implémentent tous deux (mission point 1).
Decideur = Callable[[dict, Sequence[ActionLegale], random.Random], Awaitable[ResultatDecision]]


def _jouables(legales: Sequence[ActionLegale]) -> list[ActionLegale]:
    """Les coups légaux hors abandon : un adversaire d'entraînement n'abandonne jamais.

    Présenter l'abandon à l'IA l'inviterait à jeter l'éponge ; le jeu d'un enfant veut un partenaire
    qui joue jusqu'au bout. L'index renvoyé par l'IA porte donc sur **cette** liste filtrée.
    """
    return [c for c in legales if c.action.type != ACTION_ABANDONNER]


def etiqueter_coups(jouables: Sequence[ActionLegale]) -> list[str]:
    """Les coups légaux en lignes numérotées lisibles, pour le message envoyé à l'IA.

    On n'expose que l'**étiquette** du moteur (déjà lisible, « Passer à la phase suivante »,
    « Attacher une énergie à … ») et, s'il y en a, les étiquettes des **cibles** valides — toutes
    tirées de l'état de l'acteur, donc sans information cachée. Jamais d'``instance_id`` brut ni de
    paramètre technique : l'IA raisonne sur ce qu'un joueur voit, pas sur la plomberie.
    """
    lignes: list[str] = []
    for i, coup in enumerate(jouables):
        cibles = ", ".join(c.etiquette for c in coup.cibles)
        suffixe = f" (cibles : {cibles})" if cibles else ""
        lignes.append(f"{i}. {coup.etiquette}{suffixe}")
    return lignes


def construire_message(vue_joueur: dict, jouables: Sequence[ActionLegale]) -> str:
    """Le message envoyé à l'IA — construit **uniquement** depuis la vue projetée et les coups.

    ``vue_joueur`` est la sortie de :func:`pbm_game.state.projection.vue` : elle a déjà retiré la
    main adverse, l'ordre de la pioche et l'identité des récompenses. On la sérialise telle quelle,
    sans y ajouter aucune donnée de l'état complet — c'est ce qu'un test de non-fuite vérifie en
    parcourant la chaîne produite. L'IA doit répondre par un JSON ``{index, explication}``.
    """
    vue_json = json.dumps(vue_joueur, ensure_ascii=False, sort_keys=True, indent=2)
    coups = "\n".join(etiqueter_coups(jouables))
    return (
        "Tu joues une partie du jeu de cartes PokéBoy contre un enfant de 11 ans, comme "
        "partenaire d'entraînement. Tu ne vois que TON camp : la vue ci-dessous est tout ce que tu "
        "as le droit de connaître (la main et la pioche de l'adversaire te sont cachées, c'est "
        "normal).\n\n"
        "Choisis le meilleur coup parmi la liste des coups autorisés, en renvoyant son NUMÉRO dans "
        "le champ « index », puis explique ton choix en une phrase simple, en français, dans le "
        "champ « explication ».\n\n"
        f"=== Ta vue de la partie ===\n{vue_json}\n\n"
        f"=== Les coups autorisés (choisis-en un par son numéro) ===\n{coups}\n"
    )


def _nettoyer_explication(texte: str) -> str:
    """Réduit l'explication à une ou deux phrases affichables : on coupe au mot près si besoin.

    Jamais une troncature brutale au milieu d'un mot (lisible pour un enfant). Une explication vide
    reçoit un repli neutre plutôt qu'un blanc dans le journal.
    """
    texte = " ".join(texte.split())
    if not texte:
        return "L'IA a joué ce coup."
    if len(texte) <= MAX_LONGUEUR_EXPLICATION:
        return texte
    coupe = texte[:MAX_LONGUEUR_EXPLICATION].rsplit(" ", 1)[0]
    return (coupe or texte[:MAX_LONGUEUR_EXPLICATION]).rstrip(".,;: ") + "…"


def _raison_courte(exc: Exception) -> str:
    """Un motif de repli lisible, sans jamais exposer la clé ni le détail brut du fournisseur.

    Les erreurs normalisées du coffre (:class:`AIProviderError`) portent un ``user_message`` déjà
    destiné à l'utilisateur ; tout le reste est résumé en une phrase neutre.
    """
    if isinstance(exc, TimeoutError):
        return "délai dépassé"
    if isinstance(exc, AIProviderError):
        return exc.user_message
    if isinstance(exc, (IndexError, ValueError)):
        return "réponse hors des coups autorisés"
    return "réponse inexploitable"


async def choisir_coup_ia(
    provider: AIProvider,
    vue_joueur: dict,
    legales: Sequence[ActionLegale],
    *,
    repli_bot: RepliBot,
    alea: random.Random,
    delai_max_s: float = DELAI_MAX_COUP_S,
    modele: str | None = None,
) -> ResultatDecision:
    """Fait choisir un coup à l'IA du joueur, ou **bascule sur le bot** en cas d'échec.

    Déroulé :

    1. filtre les coups jouables (hors abandon) ; aucun → rend la main (``coup=None``) ;
    2. construit le message (vue projetée + coups numérotés) et appelle le fournisseur, **borné**
       par ``delai_max_s`` (:func:`asyncio.wait_for`) ;
    3. valide l'index renvoyé contre la liste légale — un index hors bornes est un échec, pas un
       coup inventé (D9) — et nettoie l'explication ;
    4. tout échec (délai, fournisseur injoignable, réponse non conforme, index invalide) fait jouer
       le **bot** ce coup, en nommant la raison pour le journal.

    Ne touche ni la base ni le compteur de budget : l'appelant enregistre ``usage`` et incrémente le
    compteur quand ``appel_effectue`` est vrai.
    """
    jouables = _jouables(legales)
    if not jouables:
        return ResultatDecision(coup=None)

    message = construire_message(vue_joueur, jouables)
    try:
        decision, usage = await asyncio.wait_for(
            provider.extract([], DecisionIA, message, model=modele), timeout=delai_max_s
        )
    except (TimeoutError, AIProviderError) as exc:
        # Un appel a (ou a pu être) envoyé : il compte dans le budget. Pas d'usage fiable ici.
        logger.warning(
            "adversaire-ia : appel échoué (%s) — le bot joue à sa place.", _raison_courte(exc)
        )
        return ResultatDecision(
            coup=repli_bot(vue_joueur, legales, alea),
            bascule_bot=True,
            raison=_raison_courte(exc),
            appel_effectue=True,
        )

    if not (0 <= decision.index < len(jouables)):
        # Réponse obtenue (donc usage réel à enregistrer), mais hors des coups autorisés.
        logger.warning(
            "adversaire-ia : index %s hors bornes (0..%s) — le bot joue à sa place.",
            decision.index,
            len(jouables) - 1,
        )
        return ResultatDecision(
            coup=repli_bot(vue_joueur, legales, alea),
            bascule_bot=True,
            raison="réponse hors des coups autorisés",
            usage=usage,
            appel_effectue=True,
        )

    return ResultatDecision(
        coup=jouables[decision.index],
        explication=_nettoyer_explication(decision.explication),
        usage=usage,
        appel_effectue=True,
    )


__all__ = [
    "MAX_APPELS_PAR_PARTIE",
    "DELAI_MAX_COUP_S",
    "MAX_LONGUEUR_EXPLICATION",
    "DecisionIA",
    "ResultatDecision",
    "Decideur",
    "RepliBot",
    "etiqueter_coups",
    "construire_message",
    "choisir_coup_ia",
]
