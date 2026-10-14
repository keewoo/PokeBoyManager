"""Récapitulatif d'une partie, **recalculé depuis le journal** — module pur.

Lot ``j-partie-fin-ui`` (jalon J4, « la partie laisse une trace »). L'écran de fin montre ce que
la partie a produit : sa durée, son nombre de tours, les dégâts, les cartes jouées, le meilleur
coup. Ce module calcule ces chiffres, et il les calcule **à partir du journal**, jamais au fil de
l'eau.

**Pourquoi depuis le journal, et pas en comptant pendant la partie.** C'est le risque nommé du
lot, et il est réel : le canal temps réel rejoue toute la partie depuis le coup 0 à chaque
reconnexion (un F5, un réseau qui cligne). Un compteur incrémenté à l'arrivée d'un événement
compterait donc deux fois tout ce qui a été rediffusé. Un calcul qui part du journal n'a pas ce
problème : le journal est la **source de vérité**, il ne contient chaque coup qu'une fois, et le
même journal donne toujours le même récapitulatif — c'est une fonction, pas un état.

**Pourquoi ici, dans le moteur.** Le récapitulatif lit des événements de journal, donc il
appartient au même vocabulaire que le journal. Le module reste **pur** (aucune E/S, ni base, ni
HTTP) : il reçoit des :class:`~pbm_game.journal.modele.Entree` et rend une valeur. L'adaptateur qui
va chercher les entrées en base vit côté serveur (``pbm_api.games.recapitulatif``).

**Ce qu'on attribue, et ce qu'on n'attribue pas.** Chaque chiffre par joueur vient d'un champ que
l'événement porte **explicitement** (``donnees["joueur"]``, ``donnees["par"]``) — jamais d'une
déduction. Attribuer un dégât « à l'adversaire du propriétaire du Pokémon touché » semblerait
naturel et serait faux sur les auto-dégâts (confusion R-12.3, recul) : on ne devine pas, on compte
ce que le moteur a écrit (D9 — un chiffre approximé est un chiffre faux, et personne ne le saurait).

Détail des sources, une par ligne du récapitulatif :

====================== =================================================================
Chiffre                Ce qui le produit dans le journal
====================== =================================================================
``coups``              le nombre d'entrées
``tours``              le plus grand ``numero`` d'un ``EVT_TOUR_COMMENCE``
``debut`` / ``fin``    les ``horodatage`` de la première et de la dernière entrée
``duree_s``            leur écart, en secondes (``None`` si un horodatage est illisible)
``degats_infliges``    Σ ``degats`` des ``EVT_ATTAQUE_DECLAREE``, par ``joueur``
``kos_infliges``       nombre de ``EVT_KO``, par ``par``
``recompenses_prises`` Σ ``recompenses_prises`` des ``EVT_KO``, par ``par``
``cartes_jouees``      nombre d'événements de :data:`EVENEMENTS_CARTE_JOUEE`, par ``joueur``
``energies_attachees`` nombre d'``EVT_ENERGIE_ATTACHEE``, par ``joueur``
``coups_joues``        nombre d'entrées dont l'``auteur`` est ce joueur
``meilleur_coup``      l'entrée dont l'attaque a infligé le plus de dégâts
====================== =================================================================

Deux précisions qui évitent de mal lire un chiffre :

* ``degats_infliges`` est le total **annoncé par les attaques** (``EVT_ATTAQUE_DECLAREE`` porte le
  résultat final, après faiblesse, résistance et modificateurs — R-10.9). Les dégâts d'un état
  spécial au Checkup (poison, brûlure — voir ``CHECKUP.md``) ne sont infligés par personne : ils ne
  sont donc comptés dans la colonne de personne. Ils restent lisibles dans le journal.
* ``cartes_jouees`` **exclut les Énergies**, comptées à part (``energies_attachees``) : « j'ai joué
  12 cartes » veut dire 12 Objets/Supporters/Stades/Outils/Pokémon, pas 12 dont 9 Énergies. Les
  Pokémon posés pendant la mise en place (R-4) ne passent pas par là : la mise en place a ses
  propres événements, et elle n'est pas un tour de jeu.

Règles de référence : R-14 (conditions de victoire), R-10.9 (détail des dégâts), R-13.3
(récompenses). Le récapitulatif ne décide d'aucune règle — il compte.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .modele import (
    EVT_ATTAQUE_DECLAREE,
    EVT_ENERGIE_ATTACHEE,
    EVT_EVOLUTION,
    EVT_KO,
    EVT_OBJET_JOUE,
    EVT_OUTIL_ATTACHE,
    EVT_POKEMON_POSE,
    EVT_STADE_JOUE,
    EVT_SUPPORTER_JOUE,
    EVT_TOUR_COMMENCE,
    Entree,
)

#: Les événements qui signent « une carte a été jouée », chacun portant son ``joueur``. L'Énergie
#: attachée en est **volontairement absente** : elle a sa propre ligne (voir l'en-tête du module).
#: Table **close** : un nouvel événement de jeu de carte doit être ajouté ici explicitement, sinon
#: il ne sera pas compté — mieux vaut un chiffre qui manque et qu'un test révèle qu'un chiffre qui
#: dérive en silence.
EVENEMENTS_CARTE_JOUEE: frozenset[str] = frozenset(
    {
        EVT_OBJET_JOUE,
        EVT_SUPPORTER_JOUE,
        EVT_STADE_JOUE,
        EVT_OUTIL_ATTACHE,
        EVT_POKEMON_POSE,
        EVT_EVOLUTION,
    }
)


@dataclass(frozen=True)
class StatsJoueur:
    """Ce qu'un joueur a fait pendant la partie — chaque champ vient d'un événement explicite.

    ``joueur`` est l'identifiant moteur du joueur (celui de ``EtatPartie.joueurs[*].id``). Les
    autres champs sont des compteurs ≥ 0 ; voir l'en-tête du module pour leur source exacte.
    """

    joueur: str
    degats_infliges: int = 0
    kos_infliges: int = 0
    recompenses_prises: int = 0
    cartes_jouees: int = 0
    energies_attachees: int = 0
    coups_joues: int = 0


@dataclass(frozen=True)
class MeilleurCoup:
    """Le coup qui a fait le plus de dégâts, pour en parler à l'écran.

    « Meilleur » veut dire ici **le plus de dégâts infligés en une attaque** : c'est le seul
    critère que le journal porte sans interprétation. À égalité de dégâts, le **premier** coup
    gagne (départage déterministe : deux lectures du même journal donnent le même meilleur coup).
    ``ko`` dit si ce coup a mis au moins un Pokémon K.O. — ce qui le rend racontable (« 90 dégâts,
    et c'était le K.O. décisif »).

    ``None`` quand aucune attaque n'a infligé de dégâts : il n'y a alors pas de meilleur coup, et
    on ne va pas en inventer un.
    """

    numero: int
    joueur: str
    degats: int
    ko: bool


@dataclass(frozen=True)
class Recapitulatif:
    """Le récapitulatif complet d'une partie, calculé depuis son journal.

    ``duree_s`` est ``None`` quand le journal est vide ou qu'un horodatage n'est pas une date ISO
    lisible : on préfère l'absence au faux (l'écran dit alors « durée inconnue »). ``joueurs`` est
    dans l'ordre demandé à :func:`construire_recapitulatif`.
    """

    coups: int = 0
    tours: int = 0
    debut: str | None = None
    fin: str | None = None
    duree_s: int | None = None
    joueurs: tuple[StatsJoueur, ...] = ()
    meilleur_coup: MeilleurCoup | None = None


@dataclass
class _Compteurs:
    """Accumulateur interne, mutable, converti en :class:`StatsJoueur` à la fin."""

    degats_infliges: int = 0
    kos_infliges: int = 0
    recompenses_prises: int = 0
    cartes_jouees: int = 0
    energies_attachees: int = 0
    coups_joues: int = 0


def _entier(donnees: object, cle: str) -> int:
    """La valeur entière de ``donnees[cle]``, ou 0 si elle est absente ou d'un autre type.

    Un ``bool`` est refusé explicitement (en Python c'est un entier, et ``True`` compterait pour 1
    sur un champ qui n'a rien à voir). Les données d'un événement sont des valeurs JSON natives
    produites par le moteur : un type inattendu signale un journal corrompu, pas un cas normal —
    mais un récapitulatif n'est pas le bon endroit pour s'arrêter (l'écran de fin doit s'afficher
    même sur une vieille partie), donc on compte 0 plutôt que de lever.
    """
    if not isinstance(donnees, dict):
        return 0
    valeur = donnees.get(cle)
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        return 0
    return valeur


def _texte(donnees: object, cle: str) -> str | None:
    """La valeur de ``donnees[cle]`` si c'est une chaîne non vide, sinon ``None``."""
    if not isinstance(donnees, dict):
        return None
    valeur = donnees.get(cle)
    return valeur if isinstance(valeur, str) and valeur else None


def _duree_secondes(debut: str | None, fin: str | None) -> int | None:
    """L'écart en secondes entre deux horodatages ISO, ou ``None`` si l'un est illisible.

    Les horodatages sont des **données d'entrée** du journal (le moteur est pur, il n'appelle
    aucune horloge) : rien ne garantit leur forme sur une partie ancienne. Un horodatage qu'on ne
    sait pas lire donne ``None`` — pas 0, qui se lirait « partie instantanée ». Un écart négatif
    (horloge serveur reculée entre deux coups) est ramené à 0 : un temps négatif ne s'affiche pas.
    """
    if not debut or not fin:
        return None
    try:
        t0 = datetime.fromisoformat(debut)
        t1 = datetime.fromisoformat(fin)
    except ValueError:
        return None
    if (t0.tzinfo is None) != (t1.tzinfo is None):
        # Un horodatage naïf et un horodatage daté ne se soustraient pas : on ne bricole pas un
        # fuseau par défaut, on renonce au chiffre.
        return None
    return max(0, int((t1 - t0).total_seconds()))


def construire_recapitulatif(
    entrees: Iterable[Entree], joueurs: Iterable[str]
) -> Recapitulatif:
    """Le récapitulatif d'une partie, calculé en **une passe** sur son journal.

    ``entrees`` est le journal dans l'ordre (la fonction n'exige pas qu'il soit trié pour compter,
    mais ``debut``/``fin`` supposent l'ordre des coups — c'est celui que la base rend) ; ``joueurs``
    donne les identifiants moteur des deux joueurs, et **fixe l'ordre** des colonnes du résultat. Un
    joueur sans aucun événement figure quand même, à zéro : une colonne vide est une information
    (« il n'a rien joué »), son absence serait un trou.

    Fonction **pure** : aucune E/S, aucun effet de bord, et deux appels sur le même journal rendent
    exactement le même résultat. C'est ce qui permet de l'appeler à chaque affichage de l'écran de
    fin sans rien mémoriser, et de la tester par cas.

    Les événements portant un joueur **inconnu** de ``joueurs`` sont ignorés : on ne fabrique pas
    une troisième colonne depuis une donnée qu'on ne sait pas situer.
    """
    ordre = list(joueurs)
    compteurs: dict[str, _Compteurs] = {jid: _Compteurs() for jid in ordre}

    coups = 0
    tours = 0
    debut: str | None = None
    fin: str | None = None
    meilleur: MeilleurCoup | None = None

    for entree in entrees:
        coups += 1
        if debut is None:
            debut = entree.horodatage or None
        if entree.horodatage:
            fin = entree.horodatage
        if entree.auteur in compteurs:
            compteurs[entree.auteur].coups_joues += 1

        # Dégâts et K.O. de CE coup : on les relève ensemble pour pouvoir dire si le meilleur coup
        # a été décisif, ce qu'un parcours événement par événement ne saurait pas.
        degats_du_coup: dict[str, int] = {}
        ko_dans_le_coup = False

        for evenement in entree.evenements:
            type_evt = evenement.type
            donnees = evenement.donnees
            if type_evt == EVT_TOUR_COMMENCE:
                tours = max(tours, _entier(donnees, "numero"))
                continue
            if type_evt == EVT_ATTAQUE_DECLAREE:
                jid = _texte(donnees, "joueur")
                degats = _entier(donnees, "degats")
                if jid in compteurs and degats:
                    compteurs[jid].degats_infliges += degats
                    degats_du_coup[jid] = degats_du_coup.get(jid, 0) + degats
                continue
            if type_evt == EVT_KO:
                ko_dans_le_coup = True
                # ``par`` est l'adversaire du joueur mis K.O. : celui qui prend les récompenses
                # (R-13.3). C'est lui qu'on crédite, jamais l'auteur de l'entrée — un K.O. au
                # Checkup est écrit par le système, et son bénéficiaire est nommé dans l'événement.
                par = _texte(donnees, "par")
                if par in compteurs:
                    compteurs[par].kos_infliges += 1
                    compteurs[par].recompenses_prises += _entier(donnees, "recompenses_prises")
                continue
            if type_evt == EVT_ENERGIE_ATTACHEE:
                jid = _texte(donnees, "joueur")
                if jid in compteurs:
                    compteurs[jid].energies_attachees += 1
                continue
            if type_evt in EVENEMENTS_CARTE_JOUEE:
                jid = _texte(donnees, "joueur")
                if jid in compteurs:
                    compteurs[jid].cartes_jouees += 1

        for jid, degats in degats_du_coup.items():
            # Strictement supérieur : à égalité, le premier coup reste le meilleur (départage
            # déterministe, voir :class:`MeilleurCoup`).
            if meilleur is None or degats > meilleur.degats:
                meilleur = MeilleurCoup(
                    numero=entree.numero, joueur=jid, degats=degats, ko=ko_dans_le_coup
                )

    return Recapitulatif(
        coups=coups,
        tours=tours,
        debut=debut,
        fin=fin,
        duree_s=_duree_secondes(debut, fin),
        joueurs=tuple(
            StatsJoueur(
                joueur=jid,
                degats_infliges=c.degats_infliges,
                kos_infliges=c.kos_infliges,
                recompenses_prises=c.recompenses_prises,
                cartes_jouees=c.cartes_jouees,
                energies_attachees=c.energies_attachees,
                coups_joues=c.coups_joues,
            )
            for jid, c in ((jid, compteurs[jid]) for jid in ordre)
        ),
        meilleur_coup=meilleur,
    )


__all__ = [
    "EVENEMENTS_CARTE_JOUEE",
    "MeilleurCoup",
    "Recapitulatif",
    "StatsJoueur",
    "construire_recapitulatif",
]
