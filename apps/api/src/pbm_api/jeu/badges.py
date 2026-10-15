"""Les badges : **ce qu'ils récompensent, et ce qu'ils ne peuvent pas récompenser** (lot
`j-profil-jeu`, jalon J4, décision **DJ6**).

Module **pur** : aucune base, aucune horloge, aucun effet. Il déclare les badges et calcule, à
partir des **faits d'une partie close**, ceux qui viennent d'être mérités. Les lectures de base
vivent dans :mod:`pbm_api.jeu.badges_service`, la table dans
:class:`pbm_api.models.player_badges.PlayerBadge`.

**Le risque nommé par le plan, et la parade.** La fiche du lot dit : *« Des badges de temps de jeu :
ils transforment un jeu en obligation quotidienne, ce qui n'est pas ce qu'on veut pour un enfant de
onze ans. »* Une consigne ne suffit pas — le lot suivant ajoutera un badge sans l'avoir lue. La
parade est donc **structurelle** : :class:`FaitsBadges` ne porte **aucun** champ de temps. Ni durée
de partie, ni date, ni série, ni jour de connexion. Un badge ne peut pas récompenser le temps passé
parce que la fonction qui les attribue **n'en sait rien** — et un test de non-régression relit les
noms de champs pour que ça reste vrai (`test_badges.py`).

C'est le même procédé que le barème du classement (`docs/jeu/CLASSEMENT.md`) : la propriété qu'on
veut tenir est vérifiée sur la **déclaration**, pas sur les badges du jour.

**La liste des badges.** La mission demande de l'arrêter « avec JF et Aymeric ». Cette session est
autonome : la liste retenue est donc **celle de la fiche du lot**, sans y rien ajouter, et JF la
confirme ou en retire d'un mot (chaque badge est une entrée de :data:`BADGES`, rien d'autre). Elle
est écrite dans `docs/jeu/PROFIL.md` avec, pour chacun, ce qu'il récompense.

**Ce qu'aucun badge ne fait**, et c'est la mission : aucun achat, aucune monnaie, aucun tirage au
sort. Un badge est une **conséquence déterministe** d'un fait de jeu : les mêmes faits donnent
toujours les mêmes badges, ce qu'un test rejoue deux fois.

**Une seule condition commune : la partie doit compter.** ``comptabilisee`` est la notion posée une
fois pour toutes par `j-fin-effets-compte` (voir `docs/jeu/FIN-COMPTE.md`) : ni l'entraînement
contre le bot (DJ7), ni une partie expirée faute d'activité. Un badge gagné contre un bot n'en
serait pas un, et une partie que personne n'a finie n'a rien prouvé.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields

# --- Ce qu'un badge peut récompenser : un vocabulaire FERMÉ ----------------------------------
#: Le **résultat** d'une partie (gagner).
MESURE_ISSUE = "issue"
#: Un **fait de jeu** précis, qui demande de l'adresse (un K.O. en un coup, une victoire sans rien
#: céder).
MESURE_EXPLOIT = "exploit"
#: Un **palier de parties jouées** — un seul existe, et c'est un plafond délibéré (voir
#: :data:`PALIER_PARTIES`).
MESURE_VOLUME = "volume"
#: Un choix de **construction** de deck (jouer monotype, et gagner avec).
MESURE_CONSTRUCTION = "construction"

#: Les quatre mesures permises, et aucune autre. **Il n'y a volontairement pas de mesure de temps**
#: (« temps de jeu », « jours consécutifs », « connexion quotidienne ») : elle n'est pas absente par
#: oubli, elle est refusée. Un test compare cet ensemble à la liste attendue — ajouter une mesure
#: oblige donc à le modifier *en connaissance de cause*, jamais par accident.
MESURES: frozenset[str] = frozenset(
    {MESURE_ISSUE, MESURE_EXPLOIT, MESURE_VOLUME, MESURE_CONSTRUCTION}
)

#: Le palier de volume, unique : **dix** parties comptabilisées. Un seul palier, et pas une échelle
#: (10, 50, 100, 500) : une échelle est un tapis roulant, et c'est exactement ce que la fiche du lot
#: refuse. Dix parties se font en quelques après-midi, puis le badge est acquis et on n'en reparle
#: plus.
PALIER_PARTIES = 10


@dataclass(frozen=True)
class FaitsBadges:
    """Les faits d'une partie close dont dépend l'attribution — **et rien de plus**.

    ⛔ **Aucun champ de temps n'a le droit d'entrer ici** : ni durée, ni date, ni série, ni
    nombre de jours. C'est la parade structurelle au risque du lot (en-tête du module), et un
    test relit les noms de champs de cette classe pour la tenir. Ajouter ``duree_s`` ici ferait
    rougir la suite — ce qui est le but : le débat doit avoir lieu avant, pas après.

    ``recompenses_perdues`` est le nombre de cartes récompense que **l'adversaire** m'a prises
    (R-13.3) : c'est la mesure de « sans perdre de récompense », et elle se lit sur la ligne de
    l'adversaire (``game_result_players.recompenses_prises``), jamais sur la mienne.

    ``parties_comptabilisees`` compte **cette** partie incluse : c'est le total d'après la clôture,
    donc le palier se franchit à la partie qui le franchit, pas à la suivante.

    ``deck_monotype`` dit que tous les Pokémon du deck joué partagent le même type élémentaire (et
    qu'il y en a au moins un) ; ``None`` n'existe pas — un deck supprimé ou illisible vaut
    ``False``, parce qu'on n'attribue pas un badge sur une supposition (D9).
    """

    comptabilisee: bool = False
    victoire: bool = False
    ko_en_un_coup: bool = False
    recompenses_perdues: int = 0
    parties_comptabilisees: int = 0
    deck_monotype: bool = False


@dataclass(frozen=True)
class Badge:
    """La déclaration d'un badge : son code, ce qu'il dit, et la condition qui l'accorde.

    ``code`` est l'identifiant **stable** écrit en base : il ne change jamais (un code renommé
    effacerait le badge de ceux qui l'avaient). ``nom`` et ``description`` sont ce que la vitrine
    affiche — la description est écrite au joueur (« comment je l'obtiens »), pas au développeur.

    ``mesure`` dit **ce que le badge récompense**, dans le vocabulaire fermé :data:`MESURES`. C'est
    la pièce qui rend le risque du lot vérifiable au lieu d'être recommandé.

    ``condition`` est une fonction **pure** de :class:`FaitsBadges` : elle ne peut donc regarder que
    des faits de jeu.
    """

    code: str
    nom: str
    description: str
    mesure: str
    condition: Callable[[FaitsBadges], bool]


#: Les badges déclarés — la liste de la fiche du lot, dans l'ordre où la vitrine les montre.
#: Ajouter un badge, c'est ajouter une entrée ici : aucune migration, aucun autre fichier à toucher.
BADGES: tuple[Badge, ...] = (
    Badge(
        code="premiere-victoire",
        nom="Première victoire",
        description="Gagner une partie contre un autre joueur.",
        mesure=MESURE_ISSUE,
        condition=lambda f: f.victoire,
    ),
    Badge(
        code="ko-en-un-coup",
        nom="K.O. en un coup",
        description="Mettre K.O. un Pokémon encore intact, d'une seule attaque.",
        mesure=MESURE_EXPLOIT,
        condition=lambda f: f.ko_en_un_coup,
    ),
    Badge(
        code="victoire-sans-recompense-cedee",
        nom="Sans rien céder",
        description="Gagner une partie sans que l'adversaire ne prenne une seule récompense.",
        mesure=MESURE_EXPLOIT,
        condition=lambda f: f.victoire and f.recompenses_perdues == 0,
    ),
    Badge(
        code="dix-parties",
        nom="Dix parties",
        description=f"Avoir joué {PALIER_PARTIES} parties qui comptent.",
        mesure=MESURE_VOLUME,
        condition=lambda f: f.parties_comptabilisees >= PALIER_PARTIES,
    ),
    Badge(
        code="deck-monotype-victorieux",
        nom="Monotype vainqueur",
        description="Gagner avec un deck dont tous les Pokémon sont du même type.",
        mesure=MESURE_CONSTRUCTION,
        condition=lambda f: f.victoire and f.deck_monotype,
    ),
)

#: Les badges par code, pour l'affichage d'une liste venue de la base.
PAR_CODE: Mapping[str, Badge] = {b.code: b for b in BADGES}

#: Les mots qui dénoncent un champ de temps dans :class:`FaitsBadges`. Volontairement large : le
#: test qui s'en sert doit attraper ``duree_s`` comme ``jours_consecutifs`` ou ``serie_en_cours``.
MOTS_DE_TEMPS: tuple[str, ...] = (
    "duree",
    "temps",
    "date",
    "jour",
    "heure",
    "minute",
    "seconde",
    "serie",
    "consecutif",
    "quotidien",
    "session",
    "anciennete",
)


def champs_de_temps() -> tuple[str, ...]:
    """Les champs de :class:`FaitsBadges` qui ressemblent à du temps — **doit rester vide**.

    Exposée ici plutôt qu'écrite dans le test : la règle appartient au module qu'elle protège, et
    elle est ainsi lisible par qui ajoute un badge sans ouvrir la suite de tests.
    """
    return tuple(
        champ.name
        for champ in fields(FaitsBadges)
        if any(mot in champ.name.lower() for mot in MOTS_DE_TEMPS)
    )


def attribuer(faits: FaitsBadges) -> frozenset[str]:
    """Les codes des badges mérités **au vu de ces faits** — fonction pure et déterministe.

    Rend l'ensemble **complet** des badges dont la condition est vraie, pas seulement les
    nouveaux : c'est la base qui tranche ce qui est nouveau (``uq_player_badges_user_code``),
    parce qu'un ``if`` perdrait la course entre deux clôtures concurrentes. Appeler deux fois sur
    les mêmes faits rend donc le même ensemble, et la seconde insertion n'écrit rien.

    Une partie qui ne compte pas (entraînement contre le bot, partie expirée) n'accorde **aucun**
    badge : la règle est unique et vaut pour tous les badges, plutôt que répétée dans chaque
    condition — où elle finirait par manquer dans l'une d'elles.
    """
    if not faits.comptabilisee:
        return frozenset()
    return frozenset(badge.code for badge in BADGES if badge.condition(faits))


__all__ = [
    "BADGES",
    "MESURES",
    "MESURE_CONSTRUCTION",
    "MESURE_EXPLOIT",
    "MESURE_ISSUE",
    "MESURE_VOLUME",
    "MOTS_DE_TEMPS",
    "PALIER_PARTIES",
    "PAR_CODE",
    "Badge",
    "FaitsBadges",
    "attribuer",
    "champs_de_temps",
]
