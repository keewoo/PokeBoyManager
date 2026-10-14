"""Réglages de **confort et d'accessibilité** du jeu (lot ``j-accessibilite-jeu``) — module **pur**.

Trois réglages par compte, et un seul a des conséquences sur les règles :

* ``animations`` et ``taille_texte`` sont des réglages d'**écran**. Ils vivent tout de même ici, en
  base, et non dans le navigateur : un enfant qui a demandé « ne pas animer » sur la tablette du
  salon ne doit pas avoir à le redemander sur l'ordinateur de sa chambre. Le client en garde une
  copie locale, mais seulement pour ne pas clignoter au chargement.
* ``temps_rallonge`` **double les horloges** d'une partie (DJ4). Ce n'est donc pas une préférence
  d'affichage : c'est un paramètre de la partie, et il est appliqué **au lancement**, côté serveur
  (:func:`rallonger`). La raison est dans :mod:`pbm_api.games.horloges` : une partie **fige** sa
  configuration d'horloges à sa création, et rien ne la change ensuite — un réglage lu en cours de
  route n'aurait aucun effet, ou pire, un effet au prochain redémarrage seulement.

**Qui décide quand les deux joueurs ne sont pas d'accord** : si l'un des deux a demandé le temps
rallongé, la partie entière l'obtient (:func:`temps_rallonge_partie`). C'est volontairement
dissymétrique — le jeu penche du côté du joueur le plus lent, comme il explique ses refus plutôt
que de les asséner. Le joueur rapide perd un confort ; le joueur lent, sans cela, perdrait la
partie.

Pur : aucune E/S, aucune dépendance à la base ni à HTTP. La lecture/écriture vit dans
:mod:`pbm_api.jeu.confort_service`, les routes dans :mod:`pbm_api.routers.jeu_confort`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pbm_game.horloges import ConfigHorloges

#: Les animations du jeu jouent normalement (défaut).
ANIMATIONS_COMPLETES = "completes"
#: Aucune animation n'est rendue — l'état du plateau reste lisible, il ne bouge plus.
ANIMATIONS_REDUITES = "reduites"

#: Le vocabulaire du réglage d'animation. Une valeur hors de cet ensemble est **refusée** (D9) :
#: un réglage qui ne règle rien est un mensonge fait au joueur.
ANIMATIONS: frozenset[str] = frozenset({ANIMATIONS_COMPLETES, ANIMATIONS_REDUITES})

#: Les trois tailles de texte, du plus petit au plus grand (le client en déduit l'échelle).
TAILLE_NORMALE = "normale"
TAILLE_GRANDE = "grande"
TAILLE_TRES_GRANDE = "tres_grande"
TAILLES_TEXTE: frozenset[str] = frozenset({TAILLE_NORMALE, TAILLE_GRANDE, TAILLE_TRES_GRANDE})

#: Le facteur appliqué aux trois durées d'horloge quand le temps rallongé est actif.
#:
#: Deux, et pas davantage : DJ4 donne 90 s par tour et 30 s par décision ; doubler laisse le temps
#: de lire une carte à voix haute et d'en discuter, sans qu'une partie abandonnée reste « en cours »
#: pendant une heure (le budget par joueur double aussi, il borne toujours la partie).
FACTEUR_TEMPS_RALLONGE = 2.0


@dataclass(frozen=True)
class ReglagesConfort:
    """Les réglages de confort d'un compte — les **défauts** quand il n'y a jamais touché.

    Ces défauts doivent rester d'accord avec les ``server_default`` de
    :class:`pbm_api.models.jeu_confort.JeuConfortReglages` **et** avec ``CONFORT_DEFAUT`` du client
    (``apps/web/src/lib/game/confort.ts``) : un test de parité le vérifie de chaque côté. Deux jeux
    de défauts qui divergent, c'est un réglage qui change de sens selon qu'une ligne existe ou non.
    """

    animations: str = ANIMATIONS_COMPLETES
    taille_texte: str = TAILLE_NORMALE
    temps_rallonge: bool = False


def rallonger(config: ConfigHorloges, actif: bool) -> ConfigHorloges:
    """La configuration d'horloges, **doublée** si le temps rallongé est actif, inchangée sinon.

    Les deux marges (``tolerance_reseau_s``, ``pause_deconnexion_s``) ne sont **pas** touchées :
    elles compensent le réseau et une déconnexion, pas la lenteur de réflexion — les rallonger
    reviendrait à laisser une partie désertée immobile deux fois plus longtemps.
    """
    if not actif:
        return config
    return replace(
        config,
        par_tour_s=config.par_tour_s * FACTEUR_TEMPS_RALLONGE,
        par_joueur_s=config.par_joueur_s * FACTEUR_TEMPS_RALLONGE,
        par_decision_s=config.par_decision_s * FACTEUR_TEMPS_RALLONGE,
    )


def temps_rallonge_partie(*reglages: ReglagesConfort) -> bool:
    """Vrai si **au moins un** des joueurs a demandé le temps rallongé.

    Dissymétrie assumée (voir l'en-tête du module) : on ne peut pas donner deux horloges
    différentes aux deux camps — DJ4 fixe un temps par tour, pas un temps par joueur et par tour —
    donc il faut trancher, et on tranche en faveur de qui a demandé de l'aide.
    """
    return any(r.temps_rallonge for r in reglages)


__all__ = [
    "ANIMATIONS",
    "ANIMATIONS_COMPLETES",
    "ANIMATIONS_REDUITES",
    "FACTEUR_TEMPS_RALLONGE",
    "ReglagesConfort",
    "TAILLES_TEXTE",
    "TAILLE_GRANDE",
    "TAILLE_NORMALE",
    "TAILLE_TRES_GRANDE",
    "rallonger",
    "temps_rallonge_partie",
]
