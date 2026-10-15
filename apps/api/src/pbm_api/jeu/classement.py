"""Le classement privé entre comptes invités : **le calcul**, et rien d'autre (lot
`j-classement-prive`, jalon J4, DJ6).

Module **pur** — aucune base, aucune requête, aucune horloge. Il reçoit des parties déjà lues et
rend un tableau. La lecture vit dans :mod:`pbm_api.jeu.classement_service`, la route dans
:mod:`pbm_api.routers.classement`, et le choix d'activer tout ça dans
:mod:`pbm_api.jeu.reglages`.

## Le risque du lot, et comment il est tué

Le plan le nomme : « un classement incrémental non recalculable : la première erreur devient
définitive ». La parade n'est pas un test, c'est une **absence** : il n'existe dans ce dépôt aucune
table de classement, aucun compteur de points, rien à corriger. Le classement est **calculé à la
lecture** depuis ``game_result_players`` — les mêmes lignes que les statistiques du joueur, écrites
une seule fois par `j-fin-effets-compte`. Une erreur de formule se répare donc en changeant la
formule : le tableau suivant est déjà juste.

C'est aussi pourquoi la clôture d'une partie n'appelle **rien** d'ici. La mission demandait que « la
formule ne soit pas dans le code de clôture » ; elle n'y est pas, parce qu'il n'y a pas de code de
clôture à toucher.

## Les deux chemins de calcul, et pourquoi les deux existent

* :func:`calculer` — le **recalcul complet** : on compte les résultats de chaque joueur, puis on
  multiplie par le barème. C'est ce que le serveur appelle, à chaque requête.
* :func:`appliquer` — le pas **incrémental** : ce qu'une partie de plus ajoute à un cumul déjà
  établi. Personne ne l'appelle en production *aujourd'hui* ; c'est l'oracle du test
  d'acceptation (« le classement se recalcule intégralement depuis l'historique et retrouve le même
  état »), et le jour où cent mille parties rendraient le recalcul trop lent, c'est la fonction
  qu'un cache appellerait — avec son test de parité déjà écrit.

Les deux empruntent des chemins **arithmétiquement différents** (accumuler partie par partie contre
compter puis multiplier) : c'est ce qui rend leur comparaison informative. Un test qui comparerait
un pli à lui-même ne prouverait rien.

## Ce qui entre dans le classement, et ce qui n'y entre pas

Une seule condition : ``comptabilisee``. Pas deux, pas une liste de cas — **la même** notion que
celle des statistiques du joueur, posée par `j-fin-effets-compte` :

* une partie d'**entraînement** contre le bot (DJ7) n'est pas comptabilisée : elle ne peut donc
  jamais figurer au classement (critère d'acceptation du lot) ;
* une partie **expirée** faute d'activité ne l'est pas non plus : personne ne l'a jouée jusqu'au
  bout, et inventer un résultat serait contraire à D9.

**L'abandon et la désertion, en revanche, comptent** — et c'est un choix, que la mission laissait
ouvert (« selon la règle choisie »). Deux raisons, dans cet ordre :

1. **Ne pas rendre la fuite gratuite.** Si déserter effaçait la défaite du classement, le coup
   optimal d'une partie perdue serait de fermer l'onglet. Un classement qui récompense l'abandon
   fabrique exactement la dispute entre frères que le plan redoute.
2. **Ne pas se contredire.** Les statistiques du compte comptent déjà ces défaites (R-14.3 abandon,
   R-14.6 désertion). Un classement qui les ignorerait afficherait « 4 victoires / 1 défaite » à
   côté d'un total de 6 parties, sans que personne ne sache lequel des deux a tort.

Conséquence voulue : il n'y a **aucun** filtre sur la raison de fin dans ce module. Le jour où JF
voudrait l'inverse, c'est un barème qu'on ajoute, pas une condition qu'on glisse ici.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
)

# --- Les barèmes : la formule, nommée et remplaçable ------------------------


@dataclass(frozen=True)
class Bareme:
    """Combien rapporte chaque issue — la formule du classement, en trois entiers.

    ⚠️ **Aucun barème ne peut retirer de points.** DJ6 est explicite : « sans saison ni perte de
    points ». Ce n'est pas qu'une consigne, c'est une propriété vérifiée par un test sur *tous* les
    barèmes déclarés (:data:`BAREMES`) : un barème ajouté plus tard avec une défaite à ``-1`` fait
    rougir la suite. La garde porte donc sur la structure, pas sur la liste du jour — un barème
    futur est contrôlé sans que personne n'ait à y penser.

    Pourquoi des entiers et pas un calcul d'Elo : un enfant de onze ans doit pouvoir recompter son
    propre total. « Trois points par victoire » se vérifie de tête ; un écart de classement pondéré
    ne se vérifie pas, et un total qu'on ne peut pas recompter est un total qu'on soupçonne.
    """

    nom: str
    victoire: int
    egalite: int
    defaite: int
    libelle: str

    def points_de(self, resultat: str) -> int:
        """Les points que rapporte une issue. Un résultat inconnu rapporte ``0``.

        Les trois résultats possibles sont fermés par
        :data:`pbm_api.models.fin_compte.RESULTATS` ; un quatrième serait un bug d'écriture, pas une
        issue à barémer. On rend ``0`` au lieu de lever, pour qu'une ligne d'historique abîmée ne
        fasse pas disparaître le classement de tout le monde.
        """
        if resultat == RESULTAT_VICTOIRE:
            return self.victoire
        if resultat == RESULTAT_EGALITE:
            return self.egalite
        if resultat == RESULTAT_DEFAITE:
            return self.defaite
        return 0


#: Trois points la victoire, un l'égalité, zéro la défaite — le barème du football, que tout le
#: monde connaît sans l'avoir appris. Il récompense la victoire plus que deux égalités, ce qui
#: pousse à jouer pour gagner.
BAREME_POINTS = Bareme(
    nom="points",
    victoire=3,
    egalite=1,
    defaite=0,
    libelle="3 points la victoire, 1 l'égalité",
)

#: Le simple décompte des victoires (l'autre option offerte par le plan). Plus lisible encore, mais
#: aveugle à l'égalité : deux joueurs à une victoire sont à égalité même si l'un a joué dix parties.
#: C'est pourquoi ce n'est pas le défaut.
BAREME_VICTOIRES = Bareme(
    nom="victoires",
    victoire=1,
    egalite=0,
    defaite=0,
    libelle="une victoire = un point",
)

#: Les barèmes déclarés, par nom. :mod:`pbm_api.jeu.reglages` en dérive les valeurs acceptées du
#: réglage ``classement_bareme`` : ajouter un barème ici le rend choisissable par JF, sans migration
#: ni déploiement — juste une commande d'administration.
BAREMES: Mapping[str, Bareme] = {
    BAREME_POINTS.nom: BAREME_POINTS,
    BAREME_VICTOIRES.nom: BAREME_VICTOIRES,
}

#: Le barème par défaut. « points » plutôt que « victoires » parce qu'il ne laisse aucune partie
#: jouée sans effet : une égalité rapporte quelque chose, donc une partie serrée n'est pas une
#: partie perdue pour rien.
BAREME_DEFAUT = BAREME_POINTS.nom


def bareme(nom: str | None) -> Bareme:
    """Le barème portant ce nom, ou le barème par défaut si le nom est inconnu ou absent.

    Tolérant **par construction** : le nom vient d'un réglage en base, qu'un barème retiré du code
    pourrait rendre caduc. Afficher le classement sur la formule par défaut vaut mieux que de rendre
    une erreur à un joueur ; et l'écart reste visible, puisque la sortie nomme toujours le barème
    réellement appliqué (``Classement.bareme``).
    """
    if nom is None:
        return BAREMES[BAREME_DEFAUT]
    return BAREMES.get(nom, BAREMES[BAREME_DEFAUT])


# --- Ce qui entre : une partie close, vue du siège d'un joueur ---------------


@dataclass(frozen=True)
class PartieClassante:
    """Une ligne de ``game_result_players``, réduite à ce que le classement regarde.

    La projeter sert deux fois : le calcul devient testable sans base (c'est ce qui permet les cas
    limites — l'égalité, la série, le joueur à zéro partie), et il devient impossible de faire
    dépendre le classement d'un champ qu'on aurait oublié de lire.

    ``finie_a`` ne sert pas à ordonner les points (une addition s'en moque) mais à deux choses
    réelles : la fenêtre « évolution récente » et la date de dernière partie affichée.
    """

    user_id: uuid.UUID
    resultat: str
    comptabilisee: bool
    finie_a: datetime


@dataclass(frozen=True)
class Cumul:
    """Le total d'un joueur en cours de construction — l'état qu':func:`appliquer` fait avancer.

    ``points_recents`` est le sous-total des parties postérieures à la borne passée au calcul :
    c'est l'« évolution dans le temps » que demande le plan, sans table d'historique de classement.
    On montre volontairement *ce qui a été gagné récemment* plutôt qu'une variation de rang : un
    rang qui bouge parce qu'un tiers a joué ne dit rien de mon mois.
    """

    user_id: uuid.UUID
    points: int = 0
    parties: int = 0
    victoires: int = 0
    defaites: int = 0
    egalites: int = 0
    points_recents: int = 0
    derniere_partie_a: datetime | None = None


@dataclass(frozen=True)
class LigneClassement:
    """Une ligne du tableau : un joueur, son rang, ses points et de quoi les recompter.

    Les quatre compteurs (``parties``, ``victoires``, ``defaites``, ``egalites``) sont là pour que
    le total soit **vérifiable de tête** : un classement qu'on ne peut pas recompter est un
    classement qu'on conteste. ``pseudo`` peut manquer (un compte sans pseudo) : l'écran affiche
    alors ce qu'il veut, le calcul ne s'en occupe pas.
    """

    user_id: uuid.UUID
    pseudo: str | None
    rang: int
    points: int
    parties: int
    victoires: int
    defaites: int
    egalites: int
    points_recents: int
    derniere_partie_a: datetime | None


@dataclass(frozen=True)
class Classement:
    """Le tableau complet : ses lignes ordonnées, et le barème qui les a produites.

    ``bareme`` est rendu avec les lignes **exprès** : un total de points sans sa formule n'est pas
    interprétable, et si JF change de barème, l'écran doit pouvoir dire lequel s'applique au lieu de
    laisser croire à un bug.
    """

    lignes: tuple[LigneClassement, ...]
    bareme: Bareme


# --- Le pas incrémental (l'oracle du test de parité) ------------------------


def appliquer(
    cumuls: Mapping[uuid.UUID, Cumul],
    partie: PartieClassante,
    *,
    bareme: Bareme,
    recent_depuis: datetime | None = None,
) -> dict[uuid.UUID, Cumul]:
    """Ce qu'**une** partie de plus change aux cumuls — sans rien muter, à la façon d'un pli.

    Rend un **nouveau** dictionnaire : aucun appelant ne peut donc modifier un cumul par surprise,
    et appliquer la même partie deux fois à deux états différents donne deux résultats indépendants
    (ce qui serait faux avec une mutation en place, et difficile à voir dans un test).

    Une partie non comptabilisée (entraînement, partie expirée) est rendue **telle quelle** : pas de
    ligne créée, pas de compteur touché. C'est ici, et nulle part ailleurs, que se joue le critère
    « les parties d'entraînement n'y figurent jamais » — un seul endroit à relire pour s'en assurer.

    Personne n'appelle cette fonction en production (voir l'en-tête du module) : elle est l'oracle
    du test de parité avec :func:`calculer`, et la base d'un éventuel cache futur.
    """
    if not partie.comptabilisee:
        return dict(cumuls)

    courant = cumuls.get(partie.user_id, Cumul(user_id=partie.user_id))
    gagnes = bareme.points_de(partie.resultat)
    derniere = courant.derniere_partie_a
    if derniere is None or partie.finie_a > derniere:
        derniere = partie.finie_a

    suivant = replace(
        courant,
        points=courant.points + gagnes,
        parties=courant.parties + 1,
        victoires=courant.victoires + (1 if partie.resultat == RESULTAT_VICTOIRE else 0),
        defaites=courant.defaites + (1 if partie.resultat == RESULTAT_DEFAITE else 0),
        egalites=courant.egalites + (1 if partie.resultat == RESULTAT_EGALITE else 0),
        points_recents=courant.points_recents
        + (gagnes if _est_recente(partie, recent_depuis) else 0),
        derniere_partie_a=derniere,
    )
    return {**cumuls, partie.user_id: suivant}


def _est_recente(partie: PartieClassante, recent_depuis: datetime | None) -> bool:
    """La partie tombe-t-elle dans la fenêtre « récent » ? Sans borne, tout est récent.

    Borne **incluse** (``>=``) : une fenêtre « depuis trente jours » doit contenir la partie jouée
    exactement il y a trente jours, pas la perdre d'une microseconde.
    """
    return recent_depuis is None or partie.finie_a >= recent_depuis


# --- Le recalcul complet (ce que le serveur appelle) ------------------------


def calculer(
    parties: Iterable[PartieClassante],
    *,
    bareme: Bareme,
    pseudos: Mapping[uuid.UUID, str | None] | None = None,
    inclure: Iterable[uuid.UUID] = (),
    recent_depuis: datetime | None = None,
) -> Classement:
    """Le classement, recalculé **intégralement** depuis les parties fournies.

    Chemin volontairement différent de celui d':func:`appliquer` : on **compte** d'abord les issues
    de chaque joueur, puis on **multiplie** par le barème une fois à la fin. Deux implémentations
    indépendantes de la même définition, que le test de parité confronte — là où un recalcul qui
    replierait ``appliquer`` ne se comparerait qu'à lui-même.

    ``inclure`` ajoute des joueurs qui doivent figurer au tableau même sans aucune partie comptée :
    c'est ainsi que le demandeur se voit lui-même à zéro, plutôt que d'être absent de son propre
    classement et de croire à une panne. ``parties`` n'a **pas** besoin d'être triée : une somme ne
    dépend pas de l'ordre, et c'est précisément ce qui rend ce calcul reproductible (contrairement
    aux séries de victoires de `j-fin-effets-compte`, qui, elles, exigent l'ordre chronologique).
    """
    comptes: dict[uuid.UUID, dict[str, int]] = {}
    recents: dict[uuid.UUID, int] = {}
    dernieres: dict[uuid.UUID, datetime | None] = {}

    for joueur in inclure:
        comptes.setdefault(joueur, {})
        recents.setdefault(joueur, 0)
        dernieres.setdefault(joueur, None)

    for partie in parties:
        if not partie.comptabilisee:
            continue
        issues = comptes.setdefault(partie.user_id, {})
        issues[partie.resultat] = issues.get(partie.resultat, 0) + 1
        if _est_recente(partie, recent_depuis):
            recents[partie.user_id] = recents.get(partie.user_id, 0) + bareme.points_de(
                partie.resultat
            )
        else:
            recents.setdefault(partie.user_id, 0)
        precedente = dernieres.get(partie.user_id)
        if precedente is None or partie.finie_a > precedente:
            dernieres[partie.user_id] = partie.finie_a

    noms = pseudos or {}
    brutes = [
        _ligne(
            user_id=joueur,
            pseudo=noms.get(joueur),
            issues=issues,
            bareme=bareme,
            points_recents=recents.get(joueur, 0),
            derniere_partie_a=dernieres.get(joueur),
        )
        for joueur, issues in comptes.items()
    ]
    return Classement(lignes=ranger(brutes), bareme=bareme)


def _ligne(
    *,
    user_id: uuid.UUID,
    pseudo: str | None,
    issues: Mapping[str, int],
    bareme: Bareme,
    points_recents: int,
    derniere_partie_a: datetime | None,
) -> LigneClassement:
    """Une ligne de tableau depuis le décompte des issues d'un joueur (rang posé plus tard).

    C'est ici que « compter puis multiplier » se distingue d'« accumuler » : les points sont le
    produit des décomptes par le barème, calculé **une** fois.
    """
    victoires = issues.get(RESULTAT_VICTOIRE, 0)
    defaites = issues.get(RESULTAT_DEFAITE, 0)
    egalites = issues.get(RESULTAT_EGALITE, 0)
    points = (
        victoires * bareme.victoire
        + egalites * bareme.egalite
        + defaites * bareme.defaite
    )
    return LigneClassement(
        user_id=user_id,
        pseudo=pseudo,
        rang=0,
        points=points,
        parties=victoires + defaites + egalites,
        victoires=victoires,
        defaites=defaites,
        egalites=egalites,
        points_recents=points_recents,
        derniere_partie_a=derniere_partie_a,
    )


def ranger(lignes: Iterable[LigneClassement]) -> tuple[LigneClassement, ...]:
    """Ordonne les lignes et pose les rangs — **ex æquo compris**.

    Ordre d'affichage : points décroissants, puis victoires décroissantes, puis *moins* de parties
    d'abord (à points égaux, celui qui a fait autant en jouant moins est devant), puis
    l'identifiant pour que deux appels ne rendent jamais deux ordres différents.

    Le **rang**, lui, ne dépend que des points : deux joueurs à égalité de points portent le même
    rang, et le suivant saute (1, 1, 3 — la convention du sport). Départager un ex æquo au rang
    serait inventer une hiérarchie que le barème n'a pas produite, exactement le genre de détail qui
    transforme un tableau amical en dispute.
    """
    ordonnees = sorted(
        lignes,
        key=lambda ligne: (-ligne.points, -ligne.victoires, ligne.parties, str(ligne.user_id)),
    )
    rangees: list[LigneClassement] = []
    rang_courant = 0
    points_precedents: int | None = None
    for position, ligne in enumerate(ordonnees, start=1):
        if points_precedents is None or ligne.points != points_precedents:
            rang_courant = position
            points_precedents = ligne.points
        rangees.append(replace(ligne, rang=rang_courant))
    return tuple(rangees)


__all__ = [
    "BAREMES",
    "BAREME_DEFAUT",
    "BAREME_POINTS",
    "BAREME_VICTOIRES",
    "Bareme",
    "Classement",
    "Cumul",
    "LigneClassement",
    "PartieClassante",
    "appliquer",
    "bareme",
    "calculer",
    "ranger",
]
