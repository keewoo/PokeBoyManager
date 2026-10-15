"""Mes parties, en chiffres — le calcul **pur** (lot `j-stats-joueur`, jalon J4).

Ce module ne connaît ni la base, ni HTTP : il reçoit une liste de :class:`PartieJouee` et rend des
agrégats. La lecture vit dans :mod:`pbm_api.jeu.stats_joueur_service`, la route dans
:mod:`pbm_api.routers.stats_joueur`. C'est ce découpage qui permet de mesurer les agrégats sur un
historique fabriqué à la main — y compris les cas qu'une partie réelle ne produit pas à la demande
(cent parties, un deck supprimé, un adversaire sans pseudo).

**Rien n'est stocké.** Comme le classement privé (`j-classement-prive`), tout est recalculé à la
lecture depuis ``game_result_players``. Il n'existe donc aucun agrégat à réparer : une erreur de
calcul se corrige en changeant le code, pas en migrant des données. C'est aussi ce qui garantit que
la page ne peut pas contredire l'historique qu'elle affiche juste au-dessus.

**Le seuil de significativité est le cœur du lot.** Le risque nommé par la mission est « des
statistiques flatteuses calculées sur trois parties : elles trompent le joueur sur son deck et
faussent ses choix ». La parade n'est pas un avertissement en bas de page : chaque taux porte son
propre :attr:`Taux.significatif`, calculé à côté du pourcentage, par la même fonction. Un écran ne
peut donc pas afficher un taux *sans* avoir sous la main l'information qu'il ne veut rien dire —
et un futur appelant (badges, profil) héritera de la même garde sans y penser.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
)

#: En dessous de ce nombre de parties, un taux de victoire **ne veut rien dire** et le serveur le
#: dit (``significatif=False``). Cinq, parce que c'est le seuil que la mission fixe (« un taux
#: calculé sur moins de cinq parties est signalé comme non significatif ») : à quatre parties, une
#: seule victoire de plus fait bouger le taux de 25 points.
SEUIL_SIGNIFICATIVITE = 5


@dataclass(frozen=True)
class PartieJouee:
    """Une partie close, vue depuis **un** siège — le reflet d'une ligne ``game_result_players``.

    Gelée et sans méthode de lecture de base : c'est la frontière du module pur. ``deck_nom`` et
    ``adversaire_pseudo`` sont résolus par le service (deux requêtes, pas une par ligne) et peuvent
    être ``None`` — un deck supprimé laisse ``deck_id`` à nul (``ON DELETE SET NULL``), et un compte
    peut n'avoir aucun pseudo. L'historique reste lisible dans les deux cas : on écrit « deck
    supprimé », on n'invente pas un nom.

    ``duree_s`` est ``None`` quand les horodatages du journal ne permettaient pas de conclure
    (``docs/jeu/FIN-COMPTE.md``) : une absence, jamais un zéro qui se lirait « partie instantanée ».
    """

    game_id: uuid.UUID
    finie_a: datetime
    resultat: str
    #: Faux pour une partie d'entraînement contre le bot (DJ7) ou expirée faute d'activité : elle
    #: entre dans l'historique mais ne nourrit ni les totaux, ni les taux, ni les séries.
    comptabilisee: bool
    entrainement: bool
    deck_id: uuid.UUID | None
    deck_nom: str | None
    adversaire_user_id: uuid.UUID | None
    adversaire_pseudo: str | None
    adversaire_bot: bool
    duree_s: int | None
    degats_infliges: int
    kos_infliges: int
    recompenses_prises: int
    cartes_jouees: int
    energies_attachees: int
    coups_joues: int


@dataclass(frozen=True)
class Taux:
    """Un bilan victoires/défaites/égalités, et **ce qu'il vaut**.

    ``pourcentage`` est le taux de victoire arrondi à l'entier, ou ``None`` quand il n'y a aucune
    partie : zéro pour cent se lirait « il perd toujours », ce qui est faux de quelqu'un qui n'a
    pas joué (D9 — on préfère l'absence au faux).

    ``significatif`` est la réponse au risque du lot : à moins de :data:`SEUIL_SIGNIFICATIVITE`
    parties, le pourcentage est **calculé quand même** (le masquer donnerait l'impression d'un bug)
    mais il est marqué. L'écran l'affiche alors en sourdine, avec le nombre de parties qui manquent.
    """

    parties: int
    victoires: int
    defaites: int
    egalites: int
    pourcentage: int | None
    significatif: bool

    @property
    def parties_manquantes(self) -> int:
        """Combien de parties manquent pour que ce taux devienne significatif (0 si atteint)."""
        return max(0, SEUIL_SIGNIFICATIVITE - self.parties)


@dataclass(frozen=True)
class Chiffres:
    """Les chiffres de jeu cumulés et leur moyenne par partie — ce que l'historique sait vraiment.

    Les six compteurs viennent du récapitulatif du moteur, écrit par `j-fin-effets-compte` pour
    chaque siège. Leur moyenne n'est rendue que sur les parties comptabilisées : mélanger
    l'entraînement y ferait entrer les parties contre un bot qui ne se défend pas.

    ⚠️ **« Cartes les plus jouées » et « attaques les plus décisives » ne sont pas ici**, et c'est
    un choix. Ces deux palmarès demandent le détail du journal (`game_events`), que la purge
    supprime au bout de ``jeu_purge_anciennete_j`` jours : un classement de cartes calculé sur les
    journaux survivants **rétrécirait tout seul**, et un joueur verrait sa carte préférée
    disparaître de son palmarès sans que rien ne l'explique — exactement la statistique trompeuse
    que ce lot doit empêcher. Les rendre justes demande de cumuler ces compteurs à la clôture, dans
    `game_result_players` : c'est une colonne à ajouter, pas un calcul à deviner (D9). Voir
    ``docs/jeu/STATS-JOUEUR.md`` § « Ce que ce lot ne sait pas encore dire ».
    """

    parties: int
    degats_infliges: int
    kos_infliges: int
    recompenses_prises: int
    cartes_jouees: int
    energies_attachees: int
    coups_joues: int

    @property
    def degats_par_partie(self) -> float | None:
        """Dégâts moyens par partie comptabilisée, ``None`` sans aucune partie."""
        return None if self.parties == 0 else round(self.degats_infliges / self.parties, 1)

    @property
    def coups_par_partie(self) -> float | None:
        """Coups moyens par partie comptabilisée, ``None`` sans aucune partie."""
        return None if self.parties == 0 else round(self.coups_joues / self.parties, 1)


@dataclass(frozen=True)
class AgregatAdversaire:
    """Mon bilan face à **un** adversaire.

    ``user_id`` peut être ``None`` : c'est la ligne du bot d'entraînement, regroupée sous un seul
    libellé (toutes les parties d'entraînement comptent pour le même « adversaire », quel que soit
    le compte technique derrière le bot).
    """

    user_id: uuid.UUID | None
    pseudo: str | None
    bot: bool
    taux: Taux
    derniere_partie_a: datetime | None


@dataclass(frozen=True)
class AgregatDeck:
    """Ce qu'un deck a produit : son bilan, ses chiffres, et contre qui il gagne.

    ``adversaires`` est le croisement deck × adversaire — la vue « ce deck gagne surtout contre… »
    de la mission, dans la version que l'historique permet. Le plan la formulait « contre les decks
    Eau » : le **type du deck adverse n'est pas conservé** (``game_result_players`` porte le deck du
    joueur, pas celui d'en face), et le déduire de la collection de l'adversaire serait deviner. On
    nomme donc l'adversaire, pas une couleur qu'on n'a pas.

    ``deck_id`` à ``None`` regroupe les parties dont le deck a été supprimé depuis : elles restent
    comptées dans les totaux, et visibles sous un libellé explicite plutôt que fondues dans un
    autre deck.
    """

    deck_id: uuid.UUID | None
    deck_nom: str | None
    taux: Taux
    chiffres: Chiffres
    duree_moyenne_s: int | None
    derniere_partie_a: datetime | None
    adversaires: tuple[AgregatAdversaire, ...]


@dataclass(frozen=True)
class Totaux:
    """Les totaux d'un compte, recalculés — jamais lus dans ``player_stats``.

    Le cache ``player_stats`` existe et dit la même chose ; cette page ne le lit **pas**, et c'est
    volontaire : un cache en retard ferait afficher un total qui contredit l'historique listé juste
    en dessous, et personne ne saurait lequel croire. Recalculer coûte une requête sur les lignes
    d'un seul joueur.

    ``serie_en_cours`` compte les victoires consécutives les plus récentes ; une défaite **comme**
    une égalité la remettent à zéro (prolonger une série sur une égalité serait flatteur, donc faux
    — même règle que `j-fin-effets-compte`, pour que les deux ne divergent pas).
    """

    taux: Taux
    serie_en_cours: int
    meilleure_serie: int
    temps_jeu_s: int
    parties_entrainement: int
    temps_jeu_entrainement_s: int
    premiere_partie_a: datetime | None
    derniere_partie_a: datetime | None


@dataclass(frozen=True)
class Statistiques:
    """Tout ce que la page « Mes parties » affiche au-dessus de la liste."""

    totaux: Totaux
    chiffres: Chiffres
    par_deck: tuple[AgregatDeck, ...]
    par_adversaire: tuple[AgregatAdversaire, ...]


def taux(resultats: list[str]) -> Taux:
    """Le bilan d'une liste de résultats, et sa significativité — **la seule porte** vers un taux.

    Tous les taux du lot (totaux, par deck, par adversaire, croisement des deux) passent par ici :
    c'est ce qui rend impossible d'afficher un pourcentage sans son ``significatif``. Un résultat
    inconnu n'est pas compté comme une défaite — il serait silencieusement transformé en mauvaise
    nouvelle ; il n'entre dans aucune colonne, et le total des trois colonnes le signale.
    """
    victoires = sum(1 for r in resultats if r == RESULTAT_VICTOIRE)
    defaites = sum(1 for r in resultats if r == RESULTAT_DEFAITE)
    egalites = sum(1 for r in resultats if r == RESULTAT_EGALITE)
    parties = victoires + defaites + egalites
    return Taux(
        parties=parties,
        victoires=victoires,
        defaites=defaites,
        egalites=egalites,
        pourcentage=None if parties == 0 else round(victoires * 100 / parties),
        significatif=parties >= SEUIL_SIGNIFICATIVITE,
    )


def _series(resultats_chronologiques: list[str]) -> tuple[int, int]:
    """La série en cours et la meilleure série, depuis des résultats triés du plus ancien au plus
    récent.

    Un seul passage, et la série courante est celle qui finit sur la dernière partie : ce calcul
    ne dépend pas de l'ordre d'*écriture* des résultats, seulement de leur ordre chronologique.
    C'est ce qui le rend reproductible même quand le balayage de reprise enregistre une partie
    ancienne après une récente (`docs/jeu/FIN-COMPTE.md`).
    """
    courante = meilleure = 0
    for resultat in resultats_chronologiques:
        courante = courante + 1 if resultat == RESULTAT_VICTOIRE else 0
        meilleure = max(meilleure, courante)
    return courante, meilleure


def _chiffres(parties: list[PartieJouee]) -> Chiffres:
    """Cumule les six compteurs du récapitulatif sur un lot de parties."""
    return Chiffres(
        parties=len(parties),
        degats_infliges=sum(p.degats_infliges for p in parties),
        kos_infliges=sum(p.kos_infliges for p in parties),
        recompenses_prises=sum(p.recompenses_prises for p in parties),
        cartes_jouees=sum(p.cartes_jouees for p in parties),
        energies_attachees=sum(p.energies_attachees for p in parties),
        coups_joues=sum(p.coups_joues for p in parties),
    )


def _duree_moyenne(parties: list[PartieJouee]) -> int | None:
    """Durée moyenne en secondes, calculée **sur les parties qui en ont une**.

    Traiter une durée absente comme zéro tirerait la moyenne vers le bas sans rien dire ; aucune
    durée connue rend ``None``, pas ``0``.
    """
    durees = [p.duree_s for p in parties if p.duree_s is not None]
    return None if not durees else round(sum(durees) / len(durees))


def _cle_adversaire(partie: PartieJouee) -> tuple[bool, uuid.UUID | None]:
    """La clé de regroupement d'un adversaire : le bot d'un côté, chaque compte de l'autre.

    Toutes les parties contre le bot tombent dans le même seau (``(True, None)``) : le compte
    technique qui le porte n'a pas à apparaître comme un joueur dans un tableau d'adversaires.
    """
    return (True, None) if partie.adversaire_bot else (False, partie.adversaire_user_id)


def _libelle_adversaire(parties: list[PartieJouee]) -> str | None:
    """Le pseudo de l'adversaire d'un groupe (le premier connu), ``None`` s'il n'en a pas."""
    for partie in parties:
        if partie.adversaire_pseudo:
            return partie.adversaire_pseudo
    return None


def _par_adversaire(parties: list[PartieJouee]) -> tuple[AgregatAdversaire, ...]:
    """Mon bilan adversaire par adversaire, du plus affronté au moins affronté.

    Ordonné par nombre de parties décroissant (puis par pseudo, pour que deux adversaires à égalité
    gardent un ordre stable d'un appel à l'autre — un tableau qui se réordonne au rafraîchissement
    se lit mal).
    """
    groupes: dict[tuple[bool, uuid.UUID | None], list[PartieJouee]] = defaultdict(list)
    for partie in parties:
        groupes[_cle_adversaire(partie)].append(partie)

    agregats = [
        AgregatAdversaire(
            user_id=user_id,
            pseudo=_libelle_adversaire(lot),
            bot=bot,
            taux=taux([p.resultat for p in lot]),
            derniere_partie_a=max(p.finie_a for p in lot),
        )
        for (bot, user_id), lot in groupes.items()
    ]
    return tuple(sorted(agregats, key=lambda a: (-a.taux.parties, a.pseudo or "", a.bot)))


def _par_deck(parties: list[PartieJouee]) -> tuple[AgregatDeck, ...]:
    """Mon bilan deck par deck, du plus joué au moins joué, chacun avec ses adversaires."""
    groupes: dict[uuid.UUID | None, list[PartieJouee]] = defaultdict(list)
    for partie in parties:
        groupes[partie.deck_id].append(partie)

    agregats = [
        AgregatDeck(
            deck_id=deck_id,
            deck_nom=next((p.deck_nom for p in lot if p.deck_nom), None),
            taux=taux([p.resultat for p in lot]),
            chiffres=_chiffres(lot),
            duree_moyenne_s=_duree_moyenne(lot),
            derniere_partie_a=max(p.finie_a for p in lot),
            adversaires=_par_adversaire(lot),
        )
        for deck_id, lot in groupes.items()
    ]
    return tuple(sorted(agregats, key=lambda a: (-a.taux.parties, a.deck_nom or "")))


def calculer(parties: list[PartieJouee]) -> Statistiques:
    """Tous les agrégats d'un joueur, depuis **toutes** ses parties closes.

    Un seul filtre structure le calcul : ``comptabilisee``. Les totaux, les taux, les séries et les
    chiffres ne portent que sur les parties comptées ; l'entraînement a ses deux compteurs à lui
    (parties et temps), parce qu'un joueur qui s'est entraîné dix heures a le droit de le voir sans
    que cela gonfle son palmarès.

    Dupliquer ici la définition de « ça compte » (en excluant par exemple une raison de fin) ferait
    exister deux définitions qui finiraient par se contredire : le champ est posé une fois pour
    toutes à la clôture par `j-fin-effets-compte`, on ne fait que le lire.
    """
    comptees = [p for p in parties if p.comptabilisee]
    entrainement = [p for p in parties if p.entrainement]
    chronologiques = sorted(comptees, key=lambda p: p.finie_a)
    courante, meilleure = _series([p.resultat for p in chronologiques])

    return Statistiques(
        totaux=Totaux(
            taux=taux([p.resultat for p in comptees]),
            serie_en_cours=courante,
            meilleure_serie=meilleure,
            temps_jeu_s=sum(p.duree_s or 0 for p in comptees),
            parties_entrainement=len(entrainement),
            temps_jeu_entrainement_s=sum(p.duree_s or 0 for p in entrainement),
            # Les bornes portent sur TOUTES les parties, entraînement compris : c'est « depuis
            # quand je joue », pas « depuis quand ça compte ».
            premiere_partie_a=min((p.finie_a for p in parties), default=None),
            derniere_partie_a=max((p.finie_a for p in parties), default=None),
        ),
        chiffres=_chiffres(comptees),
        par_deck=_par_deck(comptees),
        par_adversaire=_par_adversaire(comptees),
    )


__all__ = [
    "SEUIL_SIGNIFICATIVITE",
    "AgregatAdversaire",
    "AgregatDeck",
    "Chiffres",
    "PartieJouee",
    "Statistiques",
    "Taux",
    "Totaux",
    "calculer",
    "taux",
]
