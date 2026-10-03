"""Catalogue et decks **synthétiques** pour la simulation, et le scénario dérivé d'une graine.

Pourquoi des cartes synthétiques et non le vrai catalogue : au jalon J2, seules les attaques à
**dégâts secs** sont jouables (D9 — une attaque à effet n'est pas scriptée, la construction de deck
la refuse). Les bots ont donc besoin de decks **entièrement jouables** par le moteur, du premier
coup à la victoire, pour que des milliers de parties se déroulent sans qu'un effet non implémenté
ne les bloque. On fabrique ici un petit **roster d'archétypes** — chacun 60 cartes, chacun capable
de mettre K.O. — qui exerce largement le moteur : aggro rapide, tank à coût incolore, ligne
d'**évolution** (R-7), **faiblesse** ×2 (R-10.2), **résistance** −30 (R-10.3), coût de **retraite**
élevé (R-8.2) et cible **TAG TEAM** à trois récompenses (R-15.7).

Ce module est de l'**outillage** (paquet ``pbm_sim``, hors du moteur pur ``pbm_game``) : il
fabrique des :class:`~pbm_game.cartes.modele.DefinitionCarte` et
:class:`~pbm_game.cartes.energie.DefinitionEnergie` — des **données** — que le moteur consomme. Le
moteur, lui, ne lit jamais ce fichier.

**Tout un scénario tient dans une seule graine** (:func:`scenario_depuis_graine`) : le choix des
deux decks, des deux bots, du siège qui commence et la graine d'aléatoire du moteur en découlent de
façon déterministe. C'est ce qui rend une anomalie **reproductible en une commande** : la même
graine redonne exactement la même partie.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from pbm_game.actions.familles_jeu import CatalogueJeu
from pbm_game.cartes.energie import DefinitionEnergie
from pbm_game.cartes.modele import AttaqueDef, DefinitionCarte
from pbm_game.combat.modele import CoutAttaque, Faiblesse, Resistance

#: Taille d'un deck (R-2.1). Tous les decks du roster en ont exactement autant, pour que
#: l'invariant « chaque joueur détient toujours 60 cartes » (``total_par_joueur``) soit
#: vérifiable sans cas particulier.
TAILLE_DECK = 60

# --- Énergies de base du roster (fourniture générique, R-9.2) -----------------------------------
_ENERGIES: dict[str, DefinitionEnergie] = {
    "e-elec": DefinitionEnergie(ref="e-elec", nom="Énergie Électrique", fournit={"electrique": 1}),
    "e-eau": DefinitionEnergie(ref="e-eau", nom="Énergie Eau", fournit={"eau": 1}),
    "e-feu": DefinitionEnergie(ref="e-feu", nom="Énergie Feu", fournit={"feu": 1}),
    "e-combat": DefinitionEnergie(ref="e-combat", nom="Énergie Combat", fournit={"combat": 1}),
    # Double Énergie Incolore : une carte, deux unités incolores (R-9.2, plusieurs unités).
    "e-double": DefinitionEnergie(ref="e-double", nom="Double Incolore", fournit={"incolore": 2}),
}

# --- Pokémon du roster --------------------------------------------------------------------------
# Chaque attaque est à dégâts SECS (``effet=""``) : la seule forme jouable au jalon J2 (D9).
_POKEMON: dict[str, DefinitionCarte] = {
    # Aggro électrique : frappe pour 60 dès qu'une énergie est attachée.
    "pika": DefinitionCarte(
        ref="pika", nom="Pikachu", stade="base", pv=60, type="electrique", marqueur="ordinaire",
        cout_retraite=1,
        attaques=(AttaqueDef("Éclair", CoutAttaque(types={"electrique": 1}), 60),),
    ),
    # Tank incolore : 120 PV, retraite lourde (R-8.2), attaque à coût incolore (R-9.2).
    "ronflex": DefinitionCarte(
        ref="ronflex", nom="Ronflex", stade="base", pv=120, type="incolore", marqueur="ordinaire",
        cout_retraite=4,
        attaques=(AttaqueDef("Plaquage", CoutAttaque(incolore=3), 80),),
    ),
    # Ligne d'évolution eau (R-7) : la base frappe peu, l'évolution frappe fort.
    "carapuce": DefinitionCarte(
        ref="carapuce", nom="Carapuce", stade="base", pv=50, type="eau", marqueur="ordinaire",
        cout_retraite=1,
        attaques=(AttaqueDef("Pistolet à O", CoutAttaque(types={"eau": 1}), 20),),
    ),
    "carabaffe": DefinitionCarte(
        ref="carabaffe", nom="Carabaffe", stade="stade1", pv=90, type="eau", marqueur="ordinaire",
        evolue_depuis="Carapuce", cout_retraite=1,
        attaques=(AttaqueDef("Charge-O", CoutAttaque(types={"eau": 1}, incolore=1), 60),),
    ),
    # Combat avec faiblesse eau ×2 (R-10.2) : encaisse double d'un deck eau.
    "machoc": DefinitionCarte(
        ref="machoc", nom="Machoc", stade="base", pv=70, type="combat", marqueur="ordinaire",
        faiblesse=Faiblesse(type="eau", facteur=2), cout_retraite=2,
        attaques=(AttaqueDef("Karaté", CoutAttaque(types={"combat": 1}), 40),),
    ),
    # Eau avec résistance combat −30 (R-10.3).
    "leviator": DefinitionCarte(
        ref="leviator", nom="Léviator", stade="base", pv=100, type="eau", marqueur="ordinaire",
        resistance=Resistance(type="combat", reduction=30), cout_retraite=3,
        attaques=(AttaqueDef("Hydrocanon", CoutAttaque(types={"eau": 1}, incolore=1), 70),),
    ),
    # Cible TAG TEAM : 3 récompenses (R-15.7), 180 PV — il faut plusieurs coups pour la coucher.
    "duo-tag": DefinitionCarte(
        ref="duo-tag", nom="Duo TAG", stade="base", pv=180, type="incolore", marqueur="tag_team",
        cout_retraite=2,
        attaques=(AttaqueDef("Fracas Duo", CoutAttaque(incolore=2), 90),),
    ),
}


@dataclass(frozen=True)
class Archetype:
    """Un deck du roster : un nom lisible et sa composition ``ref → nombre`` (total = 60)."""

    nom: str
    composition: dict[str, int] = field(default_factory=dict)

    def refs(self) -> list[str]:
        """La liste des 60 ``ref`` du deck (l'ordre importe peu : le moteur mélange, R-4.1)."""
        liste: list[str] = []
        for ref, nombre in self.composition.items():
            liste.extend([ref] * nombre)
        return liste


#: Le roster d'archétypes. Chacun fait 60 cartes, avec assez de bases pour que le mulligan (R-4.4)
#: reste rare et assez d'énergies pour alimenter ses attaques — sinon une partie stagnerait jusqu'à
#: la défaite par pioche vide (R-14.2), ce qui reste une fin légitime mais n'exerce pas l'attaque.
ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("aggro-electrique", {"pika": 30, "e-elec": 30}),
    Archetype("tank-incolore", {"ronflex": 30, "e-double": 30}),
    Archetype("evolution-eau", {"carapuce": 18, "carabaffe": 12, "e-eau": 30}),
    Archetype("combat-faible", {"machoc": 28, "e-combat": 32}),
    Archetype("eau-resistante", {"leviator": 26, "e-eau": 34}),
    Archetype("duo-tag", {"duo-tag": 26, "e-double": 34}),
)

#: Catalogue partagé : toutes les cartes du roster, par ``ref``. Une partie n'en utilise qu'un
#: sous-ensemble ; le moteur ne produit un coup que pour une ``ref`` présente ici (D9).
CATALOGUE: CatalogueJeu = CatalogueJeu(pokemon=dict(_POKEMON), energies=dict(_ENERGIES))

# --- Types de bot (chaînes stables, résolues en fonctions par ``bots.par_nom``) -----------------
BOT_ALEATOIRE = "aleatoire"
BOT_HEURISTIQUE = "heuristique"
BOTS_DISPONIBLES: tuple[str, ...] = (BOT_ALEATOIRE, BOT_HEURISTIQUE)


@dataclass(frozen=True)
class Scenario:
    """Une partie entièrement déterminée par une **graine** — donc reproductible en une commande.

    * ``graine`` — la chaîne d'origine, celle qu'on rejoue pour reproduire une anomalie ;
    * ``deck0`` / ``deck1`` — les archétypes des deux sièges (0 est le joueur qui commence, R-6.1) ;
    * ``bot0`` / ``bot1`` — les types de bot (``BOT_*``) qui pilotent chaque siège ;
    * ``graine_moteur`` — la graine **hex** de l'aléatoire du moteur (mélanges, piles ou faces).
    """

    graine: str
    deck0: Archetype
    deck1: Archetype
    bot0: str
    bot1: str
    graine_moteur: str

    #: Identifiants stables des deux joueurs (siège 0 commence).
    JOUEUR_0: str = "A"
    JOUEUR_1: str = "B"


def _graine_moteur(graine: str) -> str:
    """Dérive une graine **hex de 16 octets** pour l'aléatoire du moteur, de façon déterministe.

    On passe par un hachage (et non par ``random``) pour garantir que la même graine de scénario
    donne **toujours** la même graine moteur, indépendamment de la version de Python.
    """
    return hashlib.sha256(f"pbm-sim:moteur:{graine}".encode()).hexdigest()[:32]


def scenario_depuis_graine(graine: str) -> Scenario:
    """Construit le :class:`Scenario` complet déterminé par ``graine`` (anti-fragilité du rejeu).

    Tout — decks, bots, siège qui commence, graine moteur — découle de ``graine`` via un
    :class:`random.Random` ensemencé sur elle. Changer cet ordre de tirages changerait la partie
    associée à une graine : on ne le fait pas à la légère (les anomalies archivées citent leur
    graine).
    """
    if not isinstance(graine, str) or not graine:
        raise ValueError("Une graine de scénario doit être une chaîne non vide.")
    alea = random.Random(graine)
    deck0 = alea.choice(ARCHETYPES)
    deck1 = alea.choice(ARCHETYPES)
    bot0 = alea.choice(BOTS_DISPONIBLES)
    bot1 = alea.choice(BOTS_DISPONIBLES)
    return Scenario(
        graine=graine,
        deck0=deck0,
        deck1=deck1,
        bot0=bot0,
        bot1=bot1,
        graine_moteur=_graine_moteur(graine),
    )


__all__ = [
    "TAILLE_DECK",
    "Archetype",
    "ARCHETYPES",
    "CATALOGUE",
    "BOT_ALEATOIRE",
    "BOT_HEURISTIQUE",
    "BOTS_DISPONIBLES",
    "Scenario",
    "scenario_depuis_graine",
]
