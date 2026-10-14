"""Ce que le serveur dit d'une attaque pour qu'elle puisse s'**animer** — lot
``j-anim-attaques-typees``. La CI fait foi.

L'écran joue un effet **par type d'énergie** (une attaque Feu brûle la carte d'en face), d'une
intensité qui suit le résultat réel du calcul : les dégâts, la faiblesse, la résistance. Rien de
tout cela ne peut être deviné côté client — le serveur fait autorité, y compris sur ces trois
faits. Cette suite est la **parité serveur** du lot : elle fixe les trois champs que l'écran lit,
et elle mord sans le changement (``type`` absent de ``attaque_declaree`` ; ``faiblesse`` et
``resistance`` absents de ``degats``).

Pourquoi des booléens plutôt que la phrase ``detail`` : chercher le mot « faiblesse » dans une
phrase française serait un repli silencieux, qui cesserait de marcher le jour où la phrase change
— et personne ne le verrait, puisque l'effet continuerait de s'afficher, simplement faux.
"""

from __future__ import annotations

from fabrique_dsl import carte, etat, joueur, pokemon

from pbm_game.combat.modele import Faiblesse, Resistance
from pbm_game.combat.resolution import evenement_degats, resoudre_degats
from pbm_game.journal import Action, appliquer
from pbm_game.journal.modele import (
    ACTION_DECLARER_ATTAQUE,
    EVT_ATTAQUE_DECLAREE,
    EVT_DEGATS,
)
from pbm_game.rng import Rng

_GRAINE = b"anim-attaques-typees"


def _attaquer(
    e, jid, *, degats=60, type_attaque="fire", faiblesse=None, resistance=None, fiches=None
):
    """Déclare une attaque par le **vrai chemin** du moteur (transition → combat)."""
    params: dict = {
        "attaque": {
            "nom": "Flammèche",
            "cout": {"types": {}, "incolore": 0},
            "degats": degats,
            "effet": "",
        },
        "type_attaque": type_attaque,
        "energies": [],
        "fiches": fiches or {},
        "metadonnees": {},
    }
    if faiblesse is not None:
        params["faiblesse"] = faiblesse
    if resistance is not None:
        params["resistance"] = resistance
    return appliquer(e, Action(ACTION_DECLARER_ATTAQUE, jid, params), Rng(_GRAINE))


def _etat():
    al = joueur("alice", actif=pokemon("a-1", ref="atk"))
    bo = joueur("bob", actif=pokemon("b-1", ref="def", cartes=(carte("b-1", "def"),)))
    return etat(al, bo, numero=3, phase="principale")


def _de_type(evts, type_evt):
    return [e for e in evts if e.type == type_evt]


# --- `attaque_declaree` porte le type de l'attaque (R-10.2) ----------------------------------


def test_attaque_declaree_porte_le_type_de_l_attaque():
    """Le type d'énergie de l'attaque est **public** et part dans l'événement.

    C'est celui qui décide de la faiblesse (R-10.2) : le type du Pokémon attaquant. Sans lui,
    l'écran n'a aucun moyen de savoir quel effet jouer, et retomberait sur un effet neutre pour
    les onze types.
    """
    _, evts = _attaquer(
        _etat(), "alice", type_attaque="fire", fiches={"b-1": {"pv": 200, "marqueur": "ordinaire"}}
    )
    declarees = _de_type(evts, EVT_ATTAQUE_DECLAREE)
    assert len(declarees) == 1
    assert declarees[0].donnees["type"] == "fire"
    assert declarees[0].donnees["degats"] == 60


def test_attaque_sans_degat_porte_quand_meme_son_type():
    """Une attaque qui ne fait aucun dégât reste **déclarée**, et reste typée.

    C'est le cas de l'attaque purement à effet, et celui de l'attaque annulée : l'écran doit
    pouvoir jouer son effet « raté » dans la couleur du type, pas un effet gris.
    """
    _, evts = _attaquer(
        _etat(),
        "alice",
        degats=0,
        type_attaque="psychic",
        fiches={"b-1": {"pv": 200, "marqueur": "ordinaire"}},
    )
    declarees = _de_type(evts, EVT_ATTAQUE_DECLAREE)
    assert len(declarees) == 1
    assert declarees[0].donnees["degats"] == 0
    assert declarees[0].donnees["type"] == "psychic"


def test_type_inconnu_donne_une_chaine_vide_jamais_une_supposition():
    """Pas de type connu → ``""`` (D9).

    Le chemin sans catalogue ne connaît pas le type du Pokémon. On l'écrit vide : l'écran garde
    alors l'effet neutre du socle. On n'invente pas un type pour avoir une couleur.
    """
    _, evts = _attaquer(
        _etat(), "alice", type_attaque=None, fiches={"b-1": {"pv": 200, "marqueur": "ordinaire"}}
    )
    declarees = _de_type(evts, EVT_ATTAQUE_DECLAREE)
    assert declarees[0].donnees["type"] == ""


# --- `degats` porte faiblesse et résistance, en booléens (R-10.2 / R-10.3) -------------------


def test_degats_dit_si_la_faiblesse_a_joue():
    """``faiblesse: True`` quand l'étape R-10.2 a réellement été appliquée."""
    evt = evenement_degats(
        resoudre_degats(base=60, type_attaque="fire", faiblesse=Faiblesse("fire")), "b-1"
    )
    assert evt.type == EVT_DEGATS
    assert evt.donnees["faiblesse"] is True
    assert evt.donnees["resistance"] is False
    assert evt.donnees["degats"] == 120


def test_degats_dit_si_la_resistance_a_joue():
    """``resistance: True`` quand l'étape R-10.3 a réellement été appliquée."""
    evt = evenement_degats(
        resoudre_degats(base=60, type_attaque="water", resistance=Resistance("water")), "b-1"
    )
    assert evt.donnees["faiblesse"] is False
    assert evt.donnees["resistance"] is True
    assert evt.donnees["degats"] == 30


def test_faiblesse_d_un_autre_type_ne_joue_pas_et_le_dit():
    """Une faiblesse qui ne s'applique pas n'est **pas** annoncée comme ayant joué.

    Le piège : l'attaque porte bien une faiblesse en paramètre, mais d'un autre type — l'effet ne
    doit donc pas être renforcé à l'écran. C'est l'étape du calcul qui tranche, pas la présence
    du paramètre.
    """
    evt = evenement_degats(
        resoudre_degats(base=60, type_attaque="fire", faiblesse=Faiblesse("water")), "b-1"
    )
    assert evt.donnees["faiblesse"] is False
    assert evt.donnees["degats"] == 60


def test_au_banc_ni_faiblesse_ni_resistance():
    """R-10.5 — au banc, ni faiblesse ni résistance : les deux booléens sont faux."""
    evt = evenement_degats(
        resoudre_degats(
            base=60,
            type_attaque="fire",
            faiblesse=Faiblesse("fire"),
            resistance=Resistance("fire"),
            au_banc=True,
        ),
        "b-2",
        au_banc=True,
    )
    assert evt.donnees["faiblesse"] is False
    assert evt.donnees["resistance"] is False
    assert evt.donnees["au_banc"] is True


def test_les_deux_booleens_restent_json_natifs():
    """Toutes les valeurs de l'événement restent sérialisables (rejeu, temps réel)."""
    evt = evenement_degats(
        resoudre_degats(
            base=60, type_attaque="fire", faiblesse=Faiblesse("fire"), resistance=Resistance("fire")
        ),
        "b-1",
    )
    assert all(isinstance(v, (str, int, bool)) for v in evt.donnees.values())


def test_de_bout_en_bout_l_ecran_a_les_trois_faits():
    """Une attaque Feu sur une cible faible au Feu : type, dégâts doublés, faiblesse annoncée.

    C'est exactement ce que l'écran lit pour choisir l'effet (Feu) et son intensité (renforcée).
    """
    _, evts = _attaquer(
        _etat(),
        "alice",
        degats=60,
        type_attaque="fire",
        faiblesse={"type": "fire", "facteur": 2},
        fiches={"b-1": {"pv": 200, "marqueur": "ordinaire"}},
    )
    degats = _de_type(evts, EVT_DEGATS)
    declarees = _de_type(evts, EVT_ATTAQUE_DECLAREE)
    assert declarees[0].donnees["type"] == "fire"
    assert degats[0].donnees["degats"] == 120
    assert degats[0].donnees["faiblesse"] is True
    assert degats[0].donnees["resistance"] is False
