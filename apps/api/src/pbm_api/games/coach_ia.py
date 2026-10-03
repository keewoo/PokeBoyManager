"""Coach IA d'une partie d'entraînement : un conseil sur demande, et un bilan de fin de partie.

Lot ``j-coach-ia`` (jalon J4, DJ7). Deuxième visage de l'IA du joueur, après l'adversaire de
``j-adversaire-ia`` : au lieu de jouer **contre** l'enfant, elle l'**aide**. Deux usages, tous deux
sur **sa** clé (coffre ``pbm_api.ai``), portés par ce module :

* **un conseil pendant son tour** — l'IA reçoit SA vue projetée et la liste de SES coups légaux
  numérotés, propose **un** coup (par son index dans la liste) et explique pourquoi, en une phrase
  simple. Elle ne joue jamais à sa place : le conseil est une suggestion, le geste reste celui de
  l'enfant (le serveur n'applique rien ici — c'est l'appelant, puis le joueur, qui décident) ;
* **un bilan après la partie** — à partir du **journal** (les coups réellement joués, pas l'état
  complet), elle dégage deux ou trois moments décisifs et ce qu'on aurait pu faire autrement.

Les mêmes principes que l'adversaire IA valent ici, chacun payé par une règle du dépôt :

* **Jamais un coup inventé (D9).** Le conseil choisit un **index** dans la liste légale calculée par
  le moteur : le coup suggéré est légal **par construction**. Un index hors bornes n'est pas un coup
  approximé — c'est un échec, et le coach **dit** qu'il n'a pas trouvé de conseil (jamais un repli
  silencieux ni un coup fabriqué).
* **Le bilan ne cite que des coups réellement joués.** Chaque moment renvoyé porte le **numéro**
  d'une entrée du journal ; l'appelant lui fournit l'ensemble des numéros valides et on **écarte**
  tout numéro qui n'existe pas (anti-hallucination, vérifié par un test). On ne raconte pas une
  partie qui n'a pas eu lieu.
* **La clé du joueur ne sort jamais.** Ce module ne manipule qu'un :class:`AIProvider` déjà
  construit (la clé déchiffrée reste dans l'appelant, :mod:`pbm_api.games.coach`) ; il ne journalise
  ni ne renvoie jamais la clé.

Ce module ne connaît **ni la base, ni FastAPI** : il reçoit un fournisseur et des données **pures**
(vue projetée, coups légaux, lignes de journal) et renvoie une suggestion ou un bilan. La résolution
de la clé, les compteurs de budget et la lecture du journal restent à l'appelant
(:mod:`pbm_api.games.coach`), qui tient la transaction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from pbm_game.actions.modele import ActionLegale
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_ECHANGE_FORCE,
    ACTION_EVOLUER,
    ACTION_FIN_TOUR,
    ACTION_PLACER_MISE_EN_PLACE,
    ACTION_POSER,
    ACTION_PROMOUVOIR,
    ACTION_REPONDRE_DEMANDE,
    ACTION_RETRAITE,
    AUTEUR_SYSTEME,
)
from pydantic import BaseModel, Field

# On réutilise, tels quels, les outils de l'adversaire IA : l'étiquetage des coups légaux, le
# nettoyage d'une explication (troncature au mot près) et la mise en phrase d'une raison d'échec —
# pour que le conseil et l'adversaire parlent exactement la même langue au joueur. Imports internes
# au sous-paquet ``games`` (couplage assumé et documenté), jamais la clé ni le réseau.
from pbm_api.ai.base import AIProvider, ExtractionUsage
from pbm_api.ai.errors import AIProviderError
from pbm_api.games.adversaire_ia import (
    _nettoyer_explication,
    _raison_courte,
    etiqueter_coups,
)

logger = logging.getLogger(__name__)

#: Nombre maximal de conseils demandés **par partie** (plafond de budget, lot j-coach-ia). Valeur
#: par défaut, **réglable** par l'environnement via ``settings.coach_max_conseils`` : un conseil
#: consomme la clé IA du joueur, donc on le borne. Compté côté base (``games.conseils_utilises``),
#: donc persistant au fil des coups d'une même partie et d'un F5.
MAX_CONSEILS_PAR_PARTIE = 3

#: Délai maximal accordé à l'IA pour **un** conseil. Au-delà, on ne fait pas attendre l'enfant
#: devant un écran muet : on dit qu'aucun conseil n'a pu être trouvé (jamais un coup inventé).
DELAI_MAX_CONSEIL_S = 20.0

#: Délai maximal accordé à l'IA pour le **bilan** de fin de partie — un peu plus long qu'un conseil
#: (elle lit tout le journal et rédige un petit texte), mais toujours borné.
DELAI_MAX_BILAN_S = 40.0

#: Libellés lisibles (français simple, enfant de 11 ans) des coups **joués par un joueur**, pour le
#: journal présenté au bilan. On ne décrit que le **type** d'action — ni ``instance_id`` ni fiche
#: catalogue : le bilan raconte la partie, il n'expose pas la plomberie. Les coups **système**
#: (pioche, Checkup, mise en place initiale…) ne sont pas des « coups joués » : ils sont écartés.
LIBELLE_ACTION: dict[str, str] = {
    ACTION_POSER: "a posé un Pokémon",
    ACTION_EVOLUER: "a fait évoluer un Pokémon",
    ACTION_ATTACHER_ENERGIE: "a attaché une énergie",
    ACTION_DECLARER_ATTAQUE: "a attaqué",
    ACTION_RETRAITE: "a battu en retraite",
    ACTION_PROMOUVOIR: "a promu un Pokémon du banc",
    ACTION_ECHANGE_FORCE: "a changé son Pokémon Actif",
    ACTION_AVANCER_PHASE: "a avancé d'une phase",
    ACTION_FIN_TOUR: "a passé son tour",
    ACTION_PLACER_MISE_EN_PLACE: "a placé son équipe de départ",
    ACTION_REPONDRE_DEMANDE: "a fait un choix demandé par une carte",
    ACTION_ABANDONNER: "a abandonné la partie",
}


# --- Conseil pendant la partie -------------------------------------------------------------------


class ConseilIA(BaseModel):
    """Réponse structurée de l'IA pour un conseil : **quel** coup légal, et **pourquoi**.

    ``index`` désigne un coup dans la liste légale **numérotée** fournie dans le message (0 = le
    premier). L'IA ne fabrique pas d'action libre : elle choisit parmi ce que le moteur autorise, ce
    qui garantit que le coup suggéré est légal. ``explication`` est une phrase courte, en français
    simple, montrée au joueur à côté du coup suggéré.
    """

    index: int = Field(
        description="Le numéro du coup conseillé dans la liste (0 pour le premier)."
    )
    explication: str = Field(
        description=(
            "Une phrase courte, en français simple, qui explique pourquoi ce coup est un bon choix "
            "(comme à un enfant de 11 ans)."
        )
    )


@dataclass
class ResultatConseil:
    """Ce que le moteur de conseil rend à l'appelant.

    * ``coup`` — le coup légal suggéré, ou ``None`` quand aucun conseil n'a pu être donné ;
    * ``index`` — l'index du coup dans la liste légale (pour que le client surligne le bon coup) ;
    * ``explication`` — la phrase du coach quand il a un conseil (sinon ``None``) ;
    * ``raison`` — pourquoi aucun conseil (ce n'est pas ton tour, délai, réponse invalide…), pour
      l'afficher ; jamais la clé ni le détail brut du fournisseur ;
    * ``usage`` — les jetons consommés par l'appel réel, ou ``None`` si aucun appel n'a abouti ;
    * ``appel_effectue`` — vrai dès qu'une requête a été **envoyée** au fournisseur (même ratée) :
      elle compte dans le plafond de conseils de la partie, car elle a consommé le quota de la clé.
    """

    coup: ActionLegale | None
    index: int | None = None
    explication: str | None = None
    raison: str | None = None
    usage: ExtractionUsage | None = None
    appel_effectue: bool = False


def _jouables(legales: Sequence[ActionLegale]) -> list[ActionLegale]:
    """Les coups légaux hors abandon : le coach ne conseille jamais d'abandonner.

    Un coach d'entraînement encourage l'enfant à jouer jusqu'au bout. L'index renvoyé par l'IA porte
    donc sur **cette** liste filtrée (cohérent avec l'adversaire IA).
    """
    return [c for c in legales if c.action.type != ACTION_ABANDONNER]


def construire_message_conseil(vue_joueur: dict, jouables: Sequence[ActionLegale]) -> str:
    """Le message envoyé à l'IA pour un conseil — construit **uniquement** depuis la vue du joueur.

    ``vue_joueur`` est la sortie de :func:`pbm_game.state.projection.vue` pour le joueur qui demande
    conseil : c'est **sa** vue, celle qu'il a déjà sous les yeux (la main et la pioche de
    l'adversaire y sont cachées, comme pour tout joueur). Le coach joue donc à armes égales avec
    l'enfant. Les coups possibles ne portent que leurs **étiquettes** (déjà lisibles), jamais
    d'``instance_id`` brut. L'IA doit répondre par un JSON ``{index, explication}``.
    """
    vue_json = json.dumps(vue_joueur, ensure_ascii=False, sort_keys=True, indent=2)
    coups = "\n".join(etiqueter_coups(jouables))
    return (
        "Tu es un coach de jeu bienveillant pour un enfant de 11 ans qui joue une partie "
        "d'entraînement du jeu de cartes PokéBoy. C'est à lui de jouer, et il te demande un "
        "conseil. Tu ne vois que SON camp (ci-dessous) : la main et la pioche de l'adversaire "
        "te sont cachées, c'est normal.\n\n"
        "Conseille-lui UN coup à jouer, en renvoyant son NUMÉRO dans le champ « index », puis "
        "explique en une phrase simple pourquoi c'est un bon choix (champ « explication »). Tu ne "
        "joues pas à sa place : tu lui suggères, il décide.\n\n"
        f"=== Sa vue de la partie ===\n{vue_json}\n\n"
        f"=== Les coups possibles (choisis-en un par son numéro) ===\n{coups}\n"
    )


async def proposer_conseil(
    provider: AIProvider,
    vue_joueur: dict,
    legales: Sequence[ActionLegale],
    *,
    delai_max_s: float = DELAI_MAX_CONSEIL_S,
    modele: str | None = None,
) -> ResultatConseil:
    """Fait proposer un coup légal au coach, ou **dit** qu'il n'a pas de conseil — jamais inventé.

    Déroulé :

    1. filtre les coups jouables (hors abandon) ; aucun → pas de conseil (``coup=None``), sans
       appeler l'IA (rien à consommer) ;
    2. construit le message (vue du joueur + coups numérotés) et appelle le fournisseur, **borné**
       par ``delai_max_s`` (:func:`asyncio.wait_for`) ;
    3. valide l'index renvoyé contre la liste légale — un index hors bornes est un échec, pas un
       coup inventé (D9) : on renvoie ``coup=None`` et une raison ;
    4. tout échec (délai, fournisseur injoignable, réponse non conforme) donne ``coup=None`` et une
       raison lisible — jamais un repli sur un coup fabriqué, jamais un silence.

    Contrairement à l'adversaire IA, il n'y a **aucun repli sur le bot** : un conseil absent se dit,
    il ne se remplace pas. Ne touche ni la base ni le compteur de budget : l'appelant enregistre
    ``usage`` et incrémente le compteur quand ``appel_effectue`` est vrai.
    """
    jouables = _jouables(legales)
    if not jouables:
        return ResultatConseil(coup=None, raison="Aucun coup à jouer pour l'instant.")

    message = construire_message_conseil(vue_joueur, jouables)
    try:
        conseil, usage = await asyncio.wait_for(
            provider.extract([], ConseilIA, message, model=modele), timeout=delai_max_s
        )
    except (TimeoutError, AIProviderError) as exc:
        # Un appel a (ou a pu être) envoyé : il compte dans le plafond. Pas d'usage fiable ici.
        logger.warning("coach-ia : conseil échoué (%s).", _raison_courte(exc))
        return ResultatConseil(coup=None, raison=_raison_courte(exc), appel_effectue=True)

    if not (0 <= conseil.index < len(jouables)):
        # Réponse obtenue (donc usage réel à enregistrer), mais hors des coups possibles.
        logger.warning(
            "coach-ia : index de conseil %s hors bornes (0..%s).",
            conseil.index,
            len(jouables) - 1,
        )
        return ResultatConseil(
            coup=None,
            raison="Le coach n'a pas trouvé de coup à conseiller.",
            usage=usage,
            appel_effectue=True,
        )

    return ResultatConseil(
        coup=jouables[conseil.index],
        index=conseil.index,
        explication=_nettoyer_explication(conseil.explication),
        usage=usage,
        appel_effectue=True,
    )


# --- Bilan de fin de partie ----------------------------------------------------------------------


class MomentBilan(BaseModel):
    """Un moment décisif du bilan : le **numéro** du coup concerné, et un commentaire d'une phrase.

    ``numero`` doit désigner une entrée **réelle** du journal : l'appelant écarte tout numéro
    inconnu (anti-hallucination). On ne raconte jamais un coup qui n'a pas été joué.
    """

    numero: int = Field(
        description="Le NUMÉRO exact du coup, tel qu'affiché dans le journal (jamais inventé)."
    )
    commentaire: str = Field(
        description="Une phrase simple : ce qui était bien, ou ce qu'on aurait pu faire autrement."
    )


class BilanIA(BaseModel):
    """Le bilan structuré attendu de l'IA : un résumé court, et deux ou trois moments décisifs."""

    resume: str = Field(
        description="Deux ou trois phrases, en français simple et encourageant, sur la partie."
    )
    moments: list[MomentBilan] = Field(
        default_factory=list,
        description="Deux ou trois moments décisifs, chacun avec le NUMÉRO exact du coup concerné.",
    )


@dataclass
class ResultatBilan:
    """Ce que le moteur de bilan rend à l'appelant.

    * ``resume`` — le résumé de la partie, ou ``None`` quand le bilan n'a pas pu être produit ;
    * ``moments`` — les moments **vérifiés** (numéro réel du journal), dans l'ordre de l'IA ;
    * ``usage`` — les jetons consommés par l'appel réel, ou ``None`` ;
    * ``appel_effectue`` — vrai dès qu'une requête a été envoyée au fournisseur (même ratée) ;
    * ``raison`` — pourquoi aucun bilan (délai, fournisseur injoignable, aucun coup à raconter…).
    """

    resume: str | None
    moments: list[MomentBilan] = field(default_factory=list)
    usage: ExtractionUsage | None = None
    appel_effectue: bool = False
    raison: str | None = None


def decrire_action(type_action: str) -> str:
    """Le libellé lisible d'un type d'action joué, ou un repli nommant le type (jamais muet).

    Un type inconnu de :data:`LIBELLE_ACTION` n'est pas masqué : on le nomme entre guillemets, pour
    qu'un nouveau type d'action apparaisse dans le bilan plutôt que d'y être silencieusement effacé.
    """
    return LIBELLE_ACTION.get(type_action, f"a joué « {type_action} »")


def construire_lignes_journal(
    entrees: Sequence[tuple[int, str, str]], jid_humain: str
) -> tuple[list[str], set[int]]:
    """Transforme le journal en lignes numérotées lisibles + l'ensemble des numéros **valides**.

    ``entrees`` est une liste de ``(numero, auteur, type_action)`` lue du journal (``game_events``).
    On ne garde que les **coups joués par un joueur** (l'humain ou son adversaire d'entraînement) :
    les coups **système** (``auteur == AUTEUR_SYSTEME`` : pioche, Checkup, mise en place…) ne sont
    pas des « coups joués » et sont écartés. Les numéros retournés sont ceux contre lesquels
    l'appelant **vérifie** les moments cités par l'IA (anti-hallucination).
    """
    lignes: list[str] = []
    numeros_valides: set[int] = set()
    for numero, auteur, type_action in entrees:
        if auteur == AUTEUR_SYSTEME:
            continue
        qui = "Toi" if auteur == jid_humain else "Ton adversaire"
        lignes.append(f"{numero}. {qui} {decrire_action(type_action)}.")
        numeros_valides.add(numero)
    return lignes, numeros_valides


def construire_message_bilan(lignes: Sequence[str], resultat: str) -> str:
    """Le message envoyé à l'IA pour le bilan — construit depuis le **journal**, pas l'état complet.

    ``lignes`` est le journal lisible (:func:`construire_lignes_journal`) : coups numérotés, sans
    aucune information cachée (ni main, ni pioche, ni identité de récompense). ``resultat`` est
    l'issue en une phrase. Réponse : un JSON ``{resume, moments:[{numero, commentaire}]}``.
    """
    journal = "\n".join(lignes)
    return (
        "Tu es un coach bienveillant pour un enfant de 11 ans qui vient de finir une partie "
        "d'entraînement du jeu de cartes PokéBoy. Voici, dans l'ordre, les coups réellement joués "
        "(chaque ligne commence par son NUMÉRO) :\n\n"
        f"{journal}\n\n"
        f"Issue de la partie : {resultat}\n\n"
        "Fais un bilan court et encourageant, en français simple. Donne un « resume » de deux ou "
        "trois phrases, puis deux ou trois « moments » décisifs : pour chacun, le NUMÉRO exact du "
        "coup concerné (tel qu'affiché ci-dessus, jamais un numéro inventé) et un « commentaire » "
        "d'une phrase disant ce qui était bien ou ce qu'on aurait pu faire autrement.\n"
    )


async def resumer_partie(
    provider: AIProvider,
    lignes: Sequence[str],
    numeros_valides: set[int],
    *,
    resultat: str,
    delai_max_s: float = DELAI_MAX_BILAN_S,
    modele: str | None = None,
) -> ResultatBilan:
    """Fait rédiger le bilan au coach, en **n'gardant que** les moments dont le numéro est réel.

    Déroulé :

    1. aucun coup à raconter → pas de bilan (``resume=None``), sans appeler l'IA ;
    2. construit le message (journal lisible + issue) et appelle le fournisseur, borné par
       ``delai_max_s`` ;
    3. tout échec (délai, injoignable, réponse non conforme) → ``resume=None`` et une
       raison — jamais un bilan inventé ni un texte vide passé pour un succès ;
    4. **filtre** les moments : on écarte tout numéro hors ``numeros_valides`` (le coach ne cite
       que des coups réellement joués, critère du lot).

    Ne touche ni la base ni l'usage : l'appelant enregistre ``usage`` si ``appel_effectue``.
    """
    if not lignes:
        return ResultatBilan(resume=None, raison="Aucun coup à raconter.")

    message = construire_message_bilan(lignes, resultat)
    try:
        bilan, usage = await asyncio.wait_for(
            provider.extract([], BilanIA, message, model=modele), timeout=delai_max_s
        )
    except (TimeoutError, AIProviderError) as exc:
        logger.warning("coach-ia : bilan échoué (%s).", _raison_courte(exc))
        return ResultatBilan(resume=None, raison=_raison_courte(exc), appel_effectue=True)

    # Anti-hallucination : on ne garde que les moments dont le numéro existe vraiment au journal.
    moments = [
        MomentBilan(numero=m.numero, commentaire=_nettoyer_explication(m.commentaire))
        for m in bilan.moments
        if m.numero in numeros_valides
    ]
    ignores = len(bilan.moments) - len(moments)
    if ignores:
        logger.warning("coach-ia : %s moment(s) cité(s) hors journal — écarté(s).", ignores)
    resume = bilan.resume.strip() or None
    return ResultatBilan(resume=resume, moments=moments, usage=usage, appel_effectue=True)


__all__ = [
    "MAX_CONSEILS_PAR_PARTIE",
    "DELAI_MAX_CONSEIL_S",
    "DELAI_MAX_BILAN_S",
    "LIBELLE_ACTION",
    "ConseilIA",
    "ResultatConseil",
    "MomentBilan",
    "BilanIA",
    "ResultatBilan",
    "construire_message_conseil",
    "proposer_conseil",
    "decrire_action",
    "construire_lignes_journal",
    "construire_message_bilan",
    "resumer_partie",
]
