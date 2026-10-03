"""Les deux bots de simulation : ils décident sur la **seule vue joueur**, jamais l'état complet.

C'est la règle d'or du lot (et du jeu) : *le serveur fait autorité*. Un bot reçoit exactement ce
qu'un vrai client reçoit — la projection :func:`pbm_game.state.vue` (sa main, le plateau public, le
nombre de cartes cachées) et la **liste des coups légaux** que le moteur a calculés pour lui — puis
il en choisit un. Il ne voit **jamais** la main de l'adversaire, l'ordre de la pioche ni le contenu
des récompenses : ces fonctions ne reçoivent pas l'``EtatPartie``, par construction. Un bot qui
trouve un blocage est donc un blocage qu'un vrai joueur pourrait rencontrer.

Deux stratégies, comme le demande la fiche du lot :

* :func:`bot_aleatoire` — joue **n'importe quel** coup légal (hors abandon), au hasard de son
  propre flux d'aléatoire. C'est lui qui explore les combinaisons tordues et débusque les états
  que personne n'a prévus.
* :func:`bot_heuristique` — joue « proprement » : il promeut le Pokémon le moins amoché, attaque
  pour le plus de dégâts, évolue, pose ses bases, et n'attache une énergie que si ça le rapproche
  d'une attaque — *il économise ses ressources*. Les parties qu'il joue ressemblent à de vraies
  parties, donc les durées qu'on en mesure sont parlantes.

Les deux **ignorent l'abandon** : un bot qui abandonnerait au hasard mettrait fin aux parties sans
rien exercer. L'abandon reste un coup légal du moteur ; simplement, aucun bot de simulation ne le
choisit tant qu'un autre coup existe (et il en existe toujours un : avancer la phase).
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from pbm_game.actions import ActionLegale
from pbm_game.journal.modele import (
    ACTION_ABANDONNER,
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_EVOLUER,
    ACTION_PLACER_MISE_EN_PLACE,
    ACTION_POSER,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
)


def _sans_abandon(legales: Sequence[ActionLegale]) -> list[ActionLegale]:
    """Les coups légaux sauf l'abandon — ce parmi quoi un bot de simulation choisit vraiment."""
    return [c for c in legales if c.action.type != ACTION_ABANDONNER]


def bot_aleatoire(
    vue: dict, legales: Sequence[ActionLegale], alea: random.Random
) -> ActionLegale | None:
    """Choisit un coup légal **au hasard** (hors abandon), via le flux ``alea`` reproductible.

    ``vue`` est présent pour l'uniformité de signature avec :func:`bot_heuristique` : le bot
    aléatoire n'en a pas besoin, mais aucun bot ne reçoit jamais l'état complet — c'est la vue ou
    rien. Renvoie ``None`` seulement si la liste est vide (l'appelant en fait une anomalie :
    un point de décision sans coup est un blocage).
    """
    choix = _sans_abandon(legales)
    if not choix:
        return None
    # Tri par une clé stable avant tirage : deux exécutions sous la même graine voient la liste
    # dans le même ordre, donc tirent le même coup (le déterminisme ne dépend pas de l'ordre
    # d'insertion des familles).
    choix.sort(key=_cle_tri)
    return alea.choice(choix)


def _cle_tri(coup: ActionLegale) -> tuple:
    """Clé d'ordre **stable et déterministe** d'un coup (type, étiquette, cibles)."""
    refs = tuple(c.reference for c in coup.cibles)
    return (coup.action.type, coup.etiquette, refs)


def _degats_du_coup(coup: ActionLegale) -> int:
    """Les dégâts d'un coup d'attaque, lus dans ses ``params`` (0 si ce n'est pas une attaque).

    Le moteur porte les dégâts imprimés dans ``action.params["attaque"]["degats"]`` — donnée
    **publique** (c'est écrit sur la carte), que le bot a le droit de lire pour comparer deux
    attaques sans jamais toucher à l'état caché.
    """
    attaque = coup.action.params.get("attaque")
    if isinstance(attaque, dict):
        degats = attaque.get("degats", 0)
        if isinstance(degats, int):
            return degats
    return 0


def _degats_subis(vue: dict, identite: str) -> int:
    """Les compteurs de dégâts d'un Pokémon en jeu (du camp de ``vue``), par son identité stable.

    L'identité d'un Pokémon est l'``instance_id`` de sa carte de base (``cartes[0]``) — la même
    que porte la cible d'un coup de promotion. On la cherche dans la vue (zones publiques), donc
    sans rien apprendre d'interdit. ``-1`` si introuvable : le bot la classera en dernier.
    """
    moi = vue["pour"]
    for joueur in vue["joueurs"]:
        if joueur["id"] != moi:
            continue
        candidats = ([joueur["actif"]] if joueur["actif"] else []) + list(joueur["banc"])
        for pokemon in candidats:
            cartes = pokemon.get("cartes") or []
            if cartes and cartes[0]["instance_id"] == identite:
                return pokemon["compteurs_degats"]
    return -1


def bot_heuristique(
    vue: dict, legales: Sequence[ActionLegale], alea: random.Random | None = None
) -> ActionLegale | None:
    """Joue proprement : promouvoir le plus sain, attaquer fort, évoluer, poser, charger utile.

    Priorité, du plus urgent au plus opportuniste (toutes lues sur la **vue** et la liste légale) :

    1. **promouvoir** (R-8.7) — obligatoire quand l'Actif est K.O. : on promeut le Pokémon du banc
       le **moins amoché**, pour tenir le plus longtemps ;
    2. **placer** la mise en place (R-4.2) — le premier placement proposé ;
    3. **attaquer** (R-9/R-10) — l'attaque aux **plus gros dégâts** disponible : finir le tour sur
       un coup, c'est avancer vers les six récompenses ;
    4. **évoluer** (R-7) — une évolution renforce le plateau ;
    5. **poser** une base au banc (R-5.3) — élargit le banc, assure un remplaçant après un K.O. ;
    6. **attacher une énergie** *seulement si* aucune attaque n'est encore possible — sinon on
       garde l'énergie pour un Pokémon qui en a besoin (*économiser ses ressources*) ;
    7. **avancer la phase** — quand il n'y a rien de mieux à faire.

    La retraite n'est jamais choisie spontanément (elle coûte des énergies) : au jalon J2 elle
    n'apporte rien au bot. ``alea`` n'est pas utilisé (stratégie déterministe) ; il complète la
    signature commune. Renvoie ``None`` si la liste est vide (anomalie côté appelant).
    """
    choix = _sans_abandon(legales)
    if not choix:
        return None
    par_type: dict[str, list[ActionLegale]] = {}
    for coup in choix:
        par_type.setdefault(coup.action.type, []).append(coup)

    if ACTION_PROMOUVOIR in par_type:
        return min(
            par_type[ACTION_PROMOUVOIR],
            key=lambda c: (
                _degats_le_plus_bas(vue, c),
                _cle_tri(c),
            ),
        )
    if ACTION_PLACER_MISE_EN_PLACE in par_type:
        return min(par_type[ACTION_PLACER_MISE_EN_PLACE], key=_cle_tri)
    if ACTION_DECLARER_ATTAQUE in par_type:
        # Plus gros dégâts d'abord ; à dégâts égaux, départage par la clé de tri stable (le
        # premier dans l'ordre déterministe). On trie plutôt que ``max`` pour que le départage
        # soit lisible et indépendant de ``PYTHONHASHSEED``.
        attaques = par_type[ACTION_DECLARER_ATTAQUE]
        return sorted(attaques, key=lambda c: (-_degats_du_coup(c), _cle_tri(c)))[0]
    if ACTION_EVOLUER in par_type:
        return min(par_type[ACTION_EVOLUER], key=_cle_tri)
    if ACTION_POSER in par_type:
        return min(par_type[ACTION_POSER], key=_cle_tri)
    # On n'attache une énergie que si AUCUNE attaque n'est possible ce tour-ci : sinon on garde la
    # ressource (économie). Attaquer ET charger sont souvent proposés ensemble ; on a déjà traité
    # l'attaque plus haut, donc arriver ici en ayant une attache signifie « pas encore d'attaque ».
    if ACTION_ATTACHER_ENERGIE in par_type:
        return min(par_type[ACTION_ATTACHER_ENERGIE], key=_cle_tri)
    # Rien de constructif : avancer la phase (termine le tour depuis le Checkup). La retraite est
    # volontairement ignorée.
    non_retraite = [c for c in choix if c.action.type != ACTION_RETRAITE]
    candidats = non_retraite or choix
    avancer = [c for c in candidats if c.action.type == ACTION_AVANCER_PHASE]
    if avancer:
        return avancer[0]
    return min(candidats, key=_cle_tri)


def _degats_le_plus_bas(vue: dict, coup: ActionLegale) -> int:
    """Les dégâts déjà subis par la cible d'un coup de promotion (pour promouvoir le plus sain)."""
    if not coup.cibles:
        return 0
    return _degats_subis(vue, coup.cibles[0].reference)


def _identite_actif(vue: dict) -> str | None:
    """L'``instance_id`` de la carte de base de l'Actif du camp de ``vue``.

    ``None`` s'il n'y a pas d'Actif.

    Lu sur la vue publique (zone Actif, toujours visible, R-3.6) : aucune information cachée n'est
    touchée. Sert à :func:`bot_coriace` pour reconnaître, parmi les attaches proposées, celle qui
    vise le Pokémon qui attaquera.
    """
    moi = vue["pour"]
    for joueur in vue["joueurs"]:
        if joueur["id"] == moi:
            actif = joueur.get("actif")
            cartes = actif.get("cartes") if actif else None
            if cartes:
                return cartes[0]["instance_id"]
    return None


def bot_coriace(
    vue: dict, legales: Sequence[ActionLegale], alea: random.Random | None = None
) -> ActionLegale | None:
    """Troisième niveau (« coriace ») : l'heuristique, mais qui **concentre l'énergie sur l'Actif**.

    Même ordre de priorités que :func:`bot_heuristique` (promouvoir, placer, attaquer fort,
    évoluer, poser), à une différence près qui le rend plus mordant **sans rien apprendre
    d'interdit** : quand il n'a pas encore d'attaque et doit attacher une énergie, il la pose
    sur son **Actif** (le Pokémon qui attaquera) plutôt que sur le premier venu — il atteint
    donc une attaque plus tôt (R-9.2). L'heuristique « correct », attache au premier coup trié,
    Pokémon du banc : l'énergie s'y gaspille. Le gain est calculé sur la **seule vue** (identité de
    l'Actif) et la liste légale (cible de chaque attache), jamais sur l'état complet.

    ``alea`` complète la signature commune (stratégie déterministe). ``None`` si la liste est vide.
    """
    choix = _sans_abandon(legales)
    if not choix:
        return None
    par_type: dict[str, list[ActionLegale]] = {}
    for coup in choix:
        par_type.setdefault(coup.action.type, []).append(coup)

    if ACTION_PROMOUVOIR in par_type:
        return min(
            par_type[ACTION_PROMOUVOIR],
            key=lambda c: (_degats_le_plus_bas(vue, c), _cle_tri(c)),
        )
    if ACTION_PLACER_MISE_EN_PLACE in par_type:
        return min(par_type[ACTION_PLACER_MISE_EN_PLACE], key=_cle_tri)
    if ACTION_DECLARER_ATTAQUE in par_type:
        attaques = par_type[ACTION_DECLARER_ATTAQUE]
        return sorted(attaques, key=lambda c: (-_degats_du_coup(c), _cle_tri(c)))[0]
    if ACTION_EVOLUER in par_type:
        return min(par_type[ACTION_EVOLUER], key=_cle_tri)
    if ACTION_POSER in par_type:
        return min(par_type[ACTION_POSER], key=_cle_tri)
    if ACTION_ATTACHER_ENERGIE in par_type:
        # La différence avec « correct » : viser l'Actif en priorité (concentrer la ressource).
        actif = _identite_actif(vue)
        attaches = par_type[ACTION_ATTACHER_ENERGIE]
        sur_actif = [c for c in attaches if c.action.params.get("cible") == actif]
        return min(sur_actif or attaches, key=_cle_tri)
    non_retraite = [c for c in choix if c.action.type != ACTION_RETRAITE]
    candidats = non_retraite or choix
    avancer = [c for c in candidats if c.action.type == ACTION_AVANCER_PHASE]
    if avancer:
        return avancer[0]
    return min(candidats, key=_cle_tri)


#: Les bots par nom (``BOT_*`` de :mod:`pbm_sim.decks`) — ce que l'orchestrateur résout.
_PAR_NOM = {
    "aleatoire": bot_aleatoire,
    "heuristique": bot_heuristique,
    "coriace": bot_coriace,
}


def par_nom(nom: str):
    """La fonction de décision du bot nommé ``nom`` ; lève si le nom est inconnu (jamais deviné)."""
    bot = _PAR_NOM.get(nom)
    if bot is None:
        raise ValueError(f"Bot inconnu : « {nom} » (connus : {sorted(_PAR_NOM)}).")
    return bot


__all__ = ["bot_aleatoire", "bot_heuristique", "bot_coriace", "par_nom"]
