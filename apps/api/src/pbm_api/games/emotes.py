"""Emotes prédéfinies d'une partie (lot ``j-echanges-emotes``, jalon J4, décision **DJ10**).

DJ10, telle que JF l'a tranchée le 14/10/2026 : *« Emotes prédéfinies seulement ("bien joué",
"oups", "ton tour"), désactivables, jamais de texte libre. »*

Pourquoi ce compromis, et pourquoi il ne bougera pas : un jeu à deux sans aucun signe de vie est
froid, mais un **chat libre** entre un adulte et un enfant de onze ans demande une modération que ce
projet n'aura jamais. Une liste fermée de phrases bienveillantes donne la chaleur sans la charge.

Ce module est **pur** — aucune base, aucun réseau, aucun état global. Il porte trois choses :

* le **catalogue fermé** (:data:`CATALOGUE`) : dix phrases, et le seul vocabulaire que le serveur
  accepte. Un code hors catalogue est refusé, jamais replié sur un défaut (un repli silencieux
  afficherait à l'adversaire une phrase que personne n'a voulu dire) ;
* la **règle de débit** (:func:`debit_autorise`) : combien d'emotes en combien de temps, calculée
  sur une simple liste d'instants — donc testable sans horloge réelle ;
* les **défauts du réglage** « je reçois les emotes » (:class:`ReglagesEmotes`), d'accord avec les
  ``server_default`` de :class:`pbm_api.models.jeu_emotes.JeuEmoteReglages` (un test le vérifie).

La mécanique (limiteur en mémoire, lecture des réglages, diffusion au hub) vit dans
:mod:`pbm_api.games.emotes_service` ; le transport dans :mod:`pbm_api.games.temps_reel`.

⚠️ Le moteur (``pbm_game``) n'apparaît nulle part ici, et c'est voulu : une emote **n'est pas un
coup**. Elle ne touche ni l'état de la partie, ni le journal numéroté, ni le rejeu — c'est ce qui
permet de tenir la promesse « rien n'est conservé au-delà de la partie ». Aucune règle ``R-x.y`` du
corpus (``docs/jeu/REGLES.md``) ne s'y applique : les emotes sont à côté des règles du jeu, pas
dedans.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Emote:
    """Une emote du catalogue : son code (le seul qui circule), sa phrase et son pictogramme.

    Le **code** est l'identifiant stable échangé entre le client et le serveur ; la **phrase** et le
    pictogramme sont de l'affichage, doublés côté écran (``apps/web/src/lib/game/emotes.ts``) et
    tenus en parité par un test. On ne transmet jamais la phrase : seul un code d'une liste fermée
    traverse le canal, donc aucun texte saisi par un joueur ne peut atteindre l'autre.
    """

    code: str
    phrase: str
    pictogramme: str


#: Le catalogue **fermé** des emotes. Dix phrases, et la règle qui les choisit :
#:
#: > **Une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.**
#:
#: C'est ce qui répond au point 1 de la mission (« s'assurer qu'aucune ne peut servir à narguer ») :
#: « Oups… » dit *je me suis trompé*, pas *tu t'es trompé* ; il n'existe aucune emote qui commente
#: le coup de l'adversaire autrement que pour le saluer. Une emote ironique n'est pas une
#: question de goût, c'est une porte ouverte au harcèlement sans texte libre.
#:
#: La liste est **figée par un test** (``test_catalogue_ferme``) : en ajouter une oblige à repasser
#: par là, donc par cette règle. JF peut en retirer une d'un mot.
CATALOGUE: tuple[Emote, ...] = (
    Emote("bonjour", "Bonjour !", "👋"),
    Emote("bonne_partie", "Bonne partie !", "🎉"),
    Emote("bonne_chance", "Bonne chance !", "🍀"),
    Emote("bien_joue", "Bien joué !", "👏"),
    Emote("belle_carte", "Belle carte !", "✨"),
    Emote("merci", "Merci !", "🙏"),
    Emote("oups", "Oups…", "😅"),
    Emote("je_reflechis", "Je réfléchis…", "🤔"),
    Emote("un_instant", "Un instant, je reviens", "⏳"),
    Emote("ton_tour", "À toi de jouer", "👉"),
)

#: Les codes acceptés par le serveur — le vocabulaire, et rien d'autre.
CODES: frozenset[str] = frozenset(emote.code for emote in CATALOGUE)


# --- Débit ---------------------------------------------------------------------------------------

#: Largeur de la fenêtre glissante du débit, en secondes.
FENETRE_SECONDES = 20.0

#: Nombre maximal d'emotes envoyées par un joueur dans :data:`FENETRE_SECONDES`.
MAX_PAR_FENETRE = 5

#: Délai minimal entre deux emotes du même joueur, en secondes. La fenêtre seule laisserait passer
#: cinq emotes en un dixième de seconde — un clignotement sur l'écran de l'adversaire, pas un
#: message. Les deux règles ensemble donnent un rythme de conversation.
INTERVALLE_MIN_SECONDES = 1.0

#: Code d'erreur : le code d'emote n'est pas au catalogue (client obsolète, ou bricolage).
ERREUR_INCONNUE = "emote_inconnue"
#: Code d'erreur : débit dépassé. Le message porte le délai d'attente, jamais un refus muet.
ERREUR_TROP_RAPIDE = "emote_trop_rapide"
#: Code d'erreur : ce joueur a **coupé** les emotes — il n'en reçoit pas, et n'en envoie pas non
#: plus. Un seul interrupteur, dans les deux sens : voir :class:`ReglagesEmotes`.
ERREUR_COUPEES = "emotes_coupees"


def debit_autorise(
    envois: Sequence[float], maintenant: float
) -> tuple[bool, float]:
    """Dit si une nouvelle emote passe, et sinon **combien de temps attendre**.

    ``envois`` est la suite des instants (secondes, croissants) des emotes déjà envoyées par ce
    joueur dans cette partie ; ``maintenant`` l'instant de la demande. Renvoie
    ``(autorise, attente)`` — ``attente`` est le délai en secondes avant que la même demande passe,
    et vaut ``0.0`` quand elle passe tout de suite.

    Deux règles, et l'attente renvoyée est la plus contraignante des deux :

    1. **intervalle minimal** : au moins :data:`INTERVALLE_MIN_SECONDES` depuis la dernière ;
    2. **fenêtre glissante** : au plus :data:`MAX_PAR_FENETRE` dans les :data:`FENETRE_SECONDES`
       écoulées. Quand le quota est pris, l'attente est le temps qu'il faut à la plus ancienne des
       emotes retenues pour sortir de la fenêtre.

    Pure : aucune horloge, aucun état. C'est ce qui permet de tester le débit en décrivant des
    instants, sans faire dormir la suite de tests une seule seconde.
    """
    recents = [t for t in envois if t > maintenant - FENETRE_SECONDES]

    attentes: list[float] = []
    if recents:
        depuis_derniere = maintenant - max(recents)
        if depuis_derniere < INTERVALLE_MIN_SECONDES:
            attentes.append(INTERVALLE_MIN_SECONDES - depuis_derniere)
    if len(recents) >= MAX_PAR_FENETRE:
        # La plus ancienne emote **retenue par le quota** : c'est sa sortie de fenêtre qui libère
        # une place. On prend la (MAX_PAR_FENETRE)-ième en partant de la fin.
        plus_ancienne_retenue = sorted(recents)[-MAX_PAR_FENETRE]
        attentes.append(plus_ancienne_retenue + FENETRE_SECONDES - maintenant)

    if not attentes:
        return True, 0.0
    return False, max(attentes)


def message_trop_rapide(attente: float) -> str:
    """La phrase rendue au joueur trop pressé — elle **dit** le délai, elle ne se contente pas de
    refuser.

    Un refus sans raison, sur un jeu d'enfant, se lit comme une panne. On arrondit à la seconde
    supérieure : annoncer « 0 s » tout en refusant serait pire que ne rien dire.
    """
    secondes = max(1, int(attente + 0.999))
    return f"Doucement — attends {secondes} s avant la prochaine emote."


# --- Réglage du joueur ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReglagesEmotes:
    """Le réglage d'emotes d'un compte — le **défaut DJ10** s'il n'y a jamais touché.

    ``recevoir_emotes`` est **un seul interrupteur pour les deux sens** : coupé, le joueur n'en
    reçoit plus *et* n'en envoie plus. C'est un choix, et il se défend : un demi-réglage (« je ne
    te lis pas mais je te parle ») est précisément la position qui sert à narguer. Un interrupteur
    unique se comprend d'un coup d'œil, et l'écran peut alors masquer la palette entière.

    Ces défauts doivent rester d'accord avec les ``server_default`` de
    :class:`pbm_api.models.jeu_emotes.JeuEmoteReglages` (un test le vérifie) : deux jeux de défauts
    qui divergent, c'est un réglage qui change de sens selon qu'une ligne existe ou non.
    """

    recevoir_emotes: bool = True


__all__ = [
    "CATALOGUE",
    "CODES",
    "ERREUR_COUPEES",
    "ERREUR_INCONNUE",
    "ERREUR_TROP_RAPIDE",
    "FENETRE_SECONDES",
    "INTERVALLE_MIN_SECONDES",
    "MAX_PAR_FENETRE",
    "Emote",
    "ReglagesEmotes",
    "debit_autorise",
    "message_trop_rapide",
]
