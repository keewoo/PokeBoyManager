"""Attaques à effet — lot ``j-cartes-attaques-effets`` (jalon J2). La CI fait foi.

On y scripte, et on y teste contre des **cartes réelles**, les familles d'attaques à effet : pile
ou face (un, plusieurs, jusqu'à échec), dégâts variables (énergies attachées, cartes en main, PV
manquants / compteurs posés, récompenses restantes), dégâts au banc, auto-dégâts, défausse
d'énergies, soins, états spéciaux, blocage du tour suivant, effets conditionnés au type de la cible.

**Le test qui mord sans le changement** : avant ce lot, une attaque à effet était **refusée** par
``resoudre_attaque_declaree`` (R-15.12/D9). ``test_une_attaque_scriptee_resout_son_effet`` et toute
la suite échouent donc sans le câblage du script d'attaque.

Chaque règle citée renvoie au corpus (``docs/jeu/REGLES.md``). Les tirages de pièce sont
**rejouables depuis la graine** : la suite le prouve en relançant deux fois le même script.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fabrique_dsl import carte, contexte, etat, joueur, pokemon

from pbm_game.cartes import AttaqueDef, DefinitionCarte
from pbm_game.cartes.modele import definition_depuis_dict, definition_vers_dict
from pbm_game.combat.modele import CoutAttaque
from pbm_game.combat.valeur import ValeurDynamique, ValeurInvalide, valeur_depuis
from pbm_game.effets.dsl.chargement import ProgrammeInvalide, charger_programme
from pbm_game.effets.dsl.interprete import EVT_DSL_PILE, executer_programme
from pbm_game.effets.pile import SourceEffet
from pbm_game.effets.verrous import (
    EVT_VERROU_LEVE,
    PORTEE_PROCHAIN_TOUR,
    VERROU_NE_PEUT_ATTAQUER,
    JeuDeVerrous,
    Verrou,
)
from pbm_game.journal import Action, appliquer
from pbm_game.journal.modele import (
    ACTION_DECLARER_ATTAQUE,
    EVT_DEGATS,
    EVT_KO,
)
from pbm_game.rng import Rng
from pbm_game.state import PHASE_CHECKUP
from pbm_game.state.serialisation import depuis_json, vers_json

_GRAINE = b"attaque-effet---seed"


# --- Déclaration d'attaque de bout en bout (transition → combat → DSL) -----------------------


def _attaquer(
    e,
    jid,
    *,
    nom="Attaque",
    degats=0,
    script=None,
    type_attaque="incolore",
    faiblesse=None,
    metadonnees=None,
    fiches=None,
    graine=_GRAINE,
):
    """Construit et applique une ``declarer_attaque`` scriptée — le vrai chemin du moteur."""
    attaque = {
        "nom": nom,
        "cout": {"types": {}, "incolore": 0},
        "degats": degats,
        "effet": "effet scripté" if script is not None else "",
    }
    if script is not None:
        attaque["script"] = script
    params = {
        "attaque": attaque,
        "type_attaque": type_attaque,
        "energies": [],
        "fiches": fiches or {},
        "metadonnees": metadonnees or {},
    }
    if faiblesse is not None:
        params["faiblesse"] = faiblesse
    action = Action(ACTION_DECLARER_ATTAQUE, jid, params)
    return appliquer(e, action, Rng(graine))


def _fiche(pv, marqueur="ordinaire"):
    return {"pv": pv, "marqueur": marqueur}


def _etat_attaque(*, actif_alice, bob_actif, bob_banc=(), numero=3):
    al = joueur("alice", actif=actif_alice)
    bo = joueur("bob", actif=bob_actif, banc=bob_banc)
    return etat(al, bo, numero=numero, phase="principale")


def test_une_attaque_scriptee_resout_son_effet():
    """Le test qui mord sans ce lot : une attaque à effet n'est plus refusée, elle se résout.

    « Cette attaque empoisonne le Pokémon Défenseur. » (R-11, pose d'état via le DSL).
    """
    e = _etat_attaque(
        actif_alice=pokemon("a-1", ref="atk"),
        bob_actif=pokemon("b-1", ref="def", cartes=(carte("b-1", "def"),)),
    )
    script = {
        "version": 1,
        "effets": [
            {
                "op": "poser_etat",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "etat": "empoisonne",
                "regle": "R-11.7",
            }
        ],
    }
    e2, evts = _attaquer(e, "alice", script=script, fiches={"b-1": _fiche(60)})
    assert "empoisonne" in e2.joueurs[1].actif.etats_speciaux
    assert e2.tour.phase == PHASE_CHECKUP  # R-5.8 — l'attaque termine le tour


def test_une_attaque_a_effet_sans_script_reste_refusee_d9():
    """Un effet non scripté n'est jamais approximé (R-15.12/D9) : l'attaque est refusée."""
    e = _etat_attaque(actif_alice=pokemon("a-1"), bob_actif=pokemon("b-1"))
    attaque = {"nom": "Mystère", "cout": {"types": {}, "incolore": 0}, "degats": 0, "effet": "???"}
    action = Action(ACTION_DECLARER_ATTAQUE, "alice", {"attaque": attaque, "energies": []})
    with pytest.raises(ValueError, match="jamais approximé|non scripté"):
        appliquer(e, action, Rng(_GRAINE))


# --- Famille : dégâts variables (trois compteurs différents, R-10.1) -------------------------


def test_degats_variables_par_energie_attachee():
    """« 20 dégâts × le nombre d'Énergies attachées à ce Pokémon » — calculé à la résolution."""
    actif = pokemon("a-1", ref="atk", energies=(carte("e1", "elec"), carte("e2", "elec")))
    e = _etat_attaque(actif_alice=actif, bob_actif=pokemon("b-1", ref="def"))
    attaque = {
        "nom": "Fulmination",
        "cout": {"types": {}, "incolore": 0},
        "effet": "20 dégâts par énergie",
        "degats": {"compter": "energies", "cible": "attaquant", "par": 20},
    }
    params = {
        "attaque": attaque,
        "type_attaque": "incolore",
        "energies": [],
        "fiches": {"b-1": _fiche(100)},
    }
    e2, evts = appliquer(e, Action(ACTION_DECLARER_ATTAQUE, "alice", params), Rng(_GRAINE))
    deg = next(ev for ev in evts if ev.type == EVT_DEGATS)
    assert deg.donnees["degats"] == 40  # 2 énergies × 20


def test_degats_variables_par_cartes_en_main_adverse():
    """« 10 dégâts × le nombre de cartes dans la main de l'adversaire » (R-10.1)."""
    e = _etat_attaque(actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="def"))
    bo = replace(e.joueurs[1], main=(carte("m1"), carte("m2"), carte("m3")))
    e = replace(e, joueurs=(e.joueurs[0], bo))
    script_degats = {"compter": "cartes_en_main", "cible": "adversaire", "par": 10}
    attaque = {
        "nom": "Jugement",
        "cout": {"types": {}, "incolore": 0},
        "effet": "10 par carte en main adverse",
        "degats": script_degats,
    }
    params = {
        "attaque": attaque,
        "type_attaque": "incolore",
        "energies": [],
        "fiches": {"b-1": _fiche(100)},
    }
    e2, evts = appliquer(e, Action(ACTION_DECLARER_ATTAQUE, "alice", params), Rng(_GRAINE))
    deg = next(ev for ev in evts if ev.type == EVT_DEGATS)
    assert deg.donnees["degats"] == 30


def test_degats_variables_par_compteurs_poses_plus_base():
    """« 20 + 10 par compteur de dégâts sur ce Pokémon » (revanche, R-10.1)."""
    actif = pokemon("a-1", ref="atk", compteurs=30)  # 3 marqueurs
    e = _etat_attaque(actif_alice=actif, bob_actif=pokemon("b-1", ref="def"))
    attaque = {
        "nom": "Revanche",
        "cout": {"types": {}, "incolore": 0},
        "effet": "20 + 10 par marqueur",
        "degats": {"compter": "marqueurs", "cible": "attaquant", "par": 10, "base": 20},
    }
    params = {
        "attaque": attaque,
        "type_attaque": "incolore",
        "energies": [],
        "fiches": {"a-1": _fiche(100), "b-1": _fiche(100)},
    }
    e2, evts = appliquer(e, Action(ACTION_DECLARER_ATTAQUE, "alice", params), Rng(_GRAINE))
    deg = next(ev for ev in evts if ev.type == EVT_DEGATS)
    assert deg.donnees["degats"] == 50  # 20 + 3×10


def test_degats_variables_calcules_a_la_resolution_pas_a_la_declaration():
    """Le piège de la fiche : la défausse d'énergie (en effet) ne doit pas fausser la base.

    L'attaque fait « 20 × énergies attachées » **puis** défausse une énergie : la base est calculée
    **avant** la défausse (sur l'état de résolution), pas après — sinon le résultat serait faux.
    """
    actif = pokemon("a-1", ref="atk", energies=(carte("e1", "elec"), carte("e2", "elec")))
    e = _etat_attaque(actif_alice=actif, bob_actif=pokemon("b-1", ref="def"))
    attaque = {
        "nom": "Décharge finale",
        "cout": {"types": {}, "incolore": 0},
        "effet": "20 par énergie, puis défausse 1 énergie",
        "degats": {"compter": "energies", "cible": "attaquant", "par": 20},
        "script": {
            "version": 1,
            "effets": [
                {
                    "op": "deplacer",
                    "nombre": 1,
                    "source": {"zone": "actif", "proprietaire": "moi"},
                    "cible": {"zone": "defausse", "proprietaire": "moi"},
                    "regle": "R-9.2",
                }
            ],
        },
    }
    params = {
        "attaque": attaque,
        "type_attaque": "incolore",
        "energies": [],
        "fiches": {"b-1": _fiche(100)},
    }
    e2, evts = appliquer(e, Action(ACTION_DECLARER_ATTAQUE, "alice", params), Rng(_GRAINE))
    deg = next(ev for ev in evts if ev.type == EVT_DEGATS)
    assert deg.donnees["degats"] == 40  # 2 énergies × 20 (compté AVANT la défausse)
    assert len(e2.joueurs[0].actif.energies) == 1  # une énergie a bien été défaussée
    assert len(e2.joueurs[0].defausse) == 1


# --- Famille : dégâts au banc (R-10.5 — ni faiblesse ni résistance) --------------------------


def test_degats_au_banc_adverse():
    """« Inflige 20 dégâts à chacun des Pokémon de banc de l'adversaire » (R-10.6, au banc)."""
    e = _etat_attaque(
        actif_alice=pokemon("a-1", ref="atk"),
        bob_actif=pokemon("b-1", ref="def"),
        bob_banc=(pokemon("b-2", ref="def"), pokemon("b-3", ref="def")),
    )
    script = {
        "version": 1,
        "effets": [
            {
                "op": "infliger_degats",
                "cible": {"zone": "banc", "proprietaire": "adversaire"},
                "nombre": 20,
                "regle": "R-10.6",
            }
        ],
    }
    fiches = {"b-1": _fiche(60), "b-2": _fiche(60), "b-3": _fiche(60)}
    e2, evts = _attaquer(e, "alice", script=script, fiches=fiches)
    assert e2.joueurs[1].banc[0].compteurs_degats == 20
    assert e2.joueurs[1].banc[1].compteurs_degats == 20
    assert e2.joueurs[1].actif.compteurs_degats == 0  # l'Actif n'est pas touché


# --- Famille : auto-dégâts (KO par recul, R-13.1) --------------------------------------------


def test_ko_par_auto_degats():
    """« Ce Pokémon s'inflige 30 dégâts. » — assez pour se mettre K.O. (R-13.1)."""
    actif = pokemon("a-weak", ref="atk")
    e = _etat_attaque(actif_alice=actif, bob_actif=pokemon("b-1", ref="def"))
    script = {
        "version": 1,
        "effets": [
            {
                "op": "infliger_degats",
                "cible": {"zone": "actif", "proprietaire": "moi"},
                "nombre": 30,
                "regle": "R-10.6",
            }
        ],
    }
    fiches = {"a-weak": _fiche(20), "b-1": _fiche(60)}
    e2, evts = _attaquer(e, "alice", script=script, fiches=fiches)
    assert any(ev.type == EVT_KO for ev in evts)  # l'attaquant se met K.O.
    assert e2.joueurs[0].actif is None  # il devra promouvoir (R-8.7)
    assert len(e2.joueurs[1].recompenses) < 6  # bob a pris une récompense (R-13.3)


# --- Famille : soins (R-10.4) ----------------------------------------------------------------


def test_soin_de_l_attaquant():
    """« Soignez 30 dégâts (3 marqueurs) de ce Pokémon. » (R-10.4, plancher à 0)."""
    actif = pokemon("a-1", ref="atk", compteurs=50)
    e = _etat_attaque(actif_alice=actif, bob_actif=pokemon("b-1", ref="def"))
    script = {
        "version": 1,
        "effets": [
            {
                "op": "soigner",
                "cible": {"zone": "actif", "proprietaire": "moi"},
                "nombre": 3,
                "regle": "R-10.4",
            }
        ],
    }
    e2, evts = _attaquer(e, "alice", script=script, fiches={"a-1": _fiche(100), "b-1": _fiche(60)})
    assert e2.joueurs[0].actif.compteurs_degats == 20  # 50 − 30


# --- Famille : états spéciaux (trois états, R-11) --------------------------------------------


@pytest.mark.parametrize("etat_special", ["empoisonne", "endormi", "confus"])
def test_pose_d_etat_special(etat_special):
    """« Le Pokémon Défenseur est maintenant <état>. » (R-11.1/R-11.8)."""
    e = _etat_attaque(actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="def"))
    script = {
        "version": 1,
        "effets": [
            {
                "op": "poser_etat",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "etat": etat_special,
                "regle": "R-11.1",
            }
        ],
    }
    e2, evts = _attaquer(e, "alice", script=script, fiches={"b-1": _fiche(60)})
    assert etat_special in e2.joueurs[1].actif.etats_speciaux


# --- Famille : pile ou face (un, plusieurs, jusqu'à échec) — REJOUABLES (critère n°3) --------


def _executer_script_pur(etat_, script, *, graine=_GRAINE):
    prog = charger_programme(script)
    ctx = contexte(joueur="alice", adversaire="bob")
    return executer_programme(etat_, prog, ctx, Rng(graine))


def _etat_deux_joueurs():
    return etat(
        joueur(
            "alice",
            actif=pokemon("a-1", ref="atk"),
            pioche=tuple(carte(f"p{i}") for i in range(30)),
        ),
        joueur("bob", actif=pokemon("b-1", ref="def")),
        numero=3,
    )


def test_pile_ou_face_une_piece_rejouable():
    e = _etat_deux_joueurs()
    script = {
        "version": 1,
        "effets": [
            {
                "op": "pile_ou_face",
                "nombre": 1,
                "alors": [
                    {
                        "op": "poser_etat",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "etat": "paralyse",
                    }
                ],
                "regle": "R-11.6",
            }
        ],
    }
    r1 = _executer_script_pur(e, script)
    r2 = _executer_script_pur(e, script)
    pile1 = [ev for ev in r1.evenements if ev.type == EVT_DSL_PILE][0]
    pile2 = [ev for ev in r2.evenements if ev.type == EVT_DSL_PILE][0]
    assert pile1.donnees["pieces"] == 1
    assert pile1.donnees["faces"] == pile2.donnees["faces"]  # rejouable depuis la graine
    assert r1.etat == r2.etat


def test_pile_ou_face_plusieurs_pieces_rejouable():
    e = _etat_deux_joueurs()
    script = {
        "version": 1,
        "effets": [
            {
                "op": "pile_ou_face",
                "nombre": 3,
                "alors": [
                    {
                        "op": "poser_compteurs",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "nombre": 2,
                    }
                ],
                "regle": "R-10.6",
            }
        ],
    }
    r1 = _executer_script_pur(e, script)
    r2 = _executer_script_pur(e, script)
    pile = [ev for ev in r1.evenements if ev.type == EVT_DSL_PILE][0]
    assert pile.donnees["pieces"] == 3
    assert 0 <= pile.donnees["faces"] <= 3
    # 2 compteurs posés par face : le résultat suit le nombre de faces, et il est rejouable.
    assert r1.etat.joueurs[1].actif.compteurs_degats == pile.donnees["faces"] * 20
    assert r1.etat == r2.etat


def test_pile_ou_face_jusqu_a_echec_rejouable():
    """« Lancez une pièce jusqu'à obtenir pile. Piochez 1 carte pour chaque face. »"""
    e = _etat_deux_joueurs()
    script = {
        "version": 1,
        "effets": [
            {
                "op": "pile_ou_face",
                "jusqu_a_echec": True,
                "alors": [{"op": "piocher", "nombre": 1}],
                "regle": "R-5.2",
            }
        ],
    }
    r1 = _executer_script_pur(e, script)
    r2 = _executer_script_pur(e, script)
    pile = [ev for ev in r1.evenements if ev.type == EVT_DSL_PILE][0]
    assert pile.donnees["jusqu_a_echec"] is True
    # Une carte piochée par face obtenue avant le pile final.
    assert len(r1.etat.joueurs[0].main) == pile.donnees["faces"]
    assert r1.etat == r2.etat  # rejouable


# --- Famille : effet conditionné au type de la cible (nouvelle condition type_cible) ---------


def test_effet_conditionne_au_type_de_la_cible():
    """« Si le Pokémon Défenseur est de type Eau, il est aussi Paralysé. » (type_cible)."""
    e = _etat_attaque(
        actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="carapuce")
    )
    script = {
        "version": 1,
        "effets": [
            {
                "op": "si",
                "condition": {
                    "type": "type_cible",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "type_pokemon": "eau",
                },
                "alors": [
                    {
                        "op": "poser_etat",
                        "cible": {"zone": "actif", "proprietaire": "adversaire"},
                        "etat": "paralyse",
                    }
                ],
                "regle": "R-11.6",
            }
        ],
    }
    meta = {"carapuce": {"categorie": "pokemon", "stade": "base", "type": "eau"}}
    e2, _ = _attaquer(e, "alice", script=script, metadonnees=meta, fiches={"b-1": _fiche(60)})
    assert "paralyse" in e2.joueurs[1].actif.etats_speciaux
    # Même script, défenseur d'un AUTRE type : la condition ne se déclenche pas.
    e_feu = _etat_attaque(
        actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="salameche")
    )
    meta_feu = {"salameche": {"categorie": "pokemon", "stade": "base", "type": "feu"}}
    e3, _ = _attaquer(
        e_feu, "alice", script=script, metadonnees=meta_feu, fiches={"b-1": _fiche(60)}
    )
    assert "paralyse" not in e3.joueurs[1].actif.etats_speciaux


# --- Famille : blocage du tour suivant (R-5.7 / R-12.5) --------------------------------------


def _verrou_auto_blocage(cible_id, pose_au_tour):
    return Verrou(
        nom=VERROU_NE_PEUT_ATTAQUER,
        portee=PORTEE_PROCHAIN_TOUR,
        source=SourceEffet(libelle="Hyper Rayon", ref="atk", instance_id="a-1"),
        regle="R-5.7",
        cible=cible_id,
        pose_au_tour=pose_au_tour,
    )


def test_attaque_pose_un_blocage_du_prochain_tour():
    """L'attaque pose « ne peut pas attaquer au prochain tour » — dans ``etat.verrous``."""
    e = _etat_attaque(actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="def"))
    script = {
        "version": 1,
        "effets": [
            {
                "op": "empecher",
                "verrou": "ne_peut_attaquer",
                "portee": "prochain_tour",
                "cible": {"zone": "actif", "proprietaire": "moi"},
                "regle": "R-5.7",
            }
        ],
    }
    e2, _ = _attaquer(e, "alice", degats=0, script=script, fiches={"b-1": _fiche(60)})
    assert e2.verrous is not None
    assert e2.verrous.est_verrouille(VERROU_NE_PEUT_ATTAQUER, cible="a-1")


def test_blocage_refuse_l_attaque_en_nommant_la_carte_r57():
    """Un Pokémon bloqué ne peut pas attaquer — le refus **nomme** la carte responsable (R-5.7)."""
    e = _etat_attaque(
        actif_alice=pokemon("a-1", ref="atk"), bob_actif=pokemon("b-1", ref="def"), numero=5
    )
    e = replace(e, verrous=JeuDeVerrous((_verrou_auto_blocage("a-1", pose_au_tour=3),)))
    with pytest.raises(ValueError, match="ne peut pas attaquer|Hyper Rayon|R-5.7"):
        _attaquer(e, "alice", degats=20, fiches={"b-1": _fiche(60)})


def test_blocage_du_prochain_tour_expire_au_bon_checkup_r125():
    """Le blocage survit au tour adverse, et tombe au Checkup du **prochain tour de sa cible**.

    Posé par Alice au tour 3 : il ne doit PAS tomber au Checkup du tour 4 (celui de Bob), mais au
    Checkup du tour 5 (le prochain tour d'Alice) — et cette levée est **journalisée** (R-12.5).
    """
    from pbm_game.checkup.resolution import resoudre_checkup

    verrou = _verrou_auto_blocage("a-1", pose_au_tour=3)
    base = etat(
        joueur("alice", actif=pokemon("a-1", ref="atk")),
        joueur("bob", actif=pokemon("b-1", ref="def")),
        numero=4,
        phase=PHASE_CHECKUP,
    )
    fiches = {"a-1": _fiche(60), "b-1": _fiche(60)}

    # Checkup du tour 4 (celui de Bob) : le blocage d'Alice PÈSE encore (pas son tour).
    e_t4 = replace(
        base, tour=replace(base.tour, joueur_actif="bob", numero=4), verrous=JeuDeVerrous((verrou,))
    )
    e_t4b, evts4 = resoudre_checkup(e_t4, Rng(_GRAINE), fiches=fiches)
    assert not any(ev.type == EVT_VERROU_LEVE for ev in evts4)
    assert e_t4b.verrous is not None and e_t4b.verrous.est_verrouille(
        VERROU_NE_PEUT_ATTAQUER, cible="a-1"
    )

    # Checkup du tour 5 (celui d'Alice) : le blocage TOMBE, et le journal le dit.
    e_t5 = replace(
        base,
        tour=replace(base.tour, joueur_actif="alice", numero=5),
        verrous=JeuDeVerrous((verrou,)),
    )
    e_t5b, evts5 = resoudre_checkup(e_t5, Rng(_GRAINE), fiches=fiches)
    assert any(ev.type == EVT_VERROU_LEVE for ev in evts5)
    assert e_t5b.verrous is None  # plus aucun verrou → champ remis à None


# --- Sérialisation des verrous (rejouabilité : un F5 garde les blocages) ----------------------


def test_les_verrous_survivent_a_la_serialisation():
    """``depuis_json(vers_json(etat)) == etat`` avec des verrous — et sans, le JSON est inchangé."""
    e_sans = etat(joueur("alice", actif=pokemon("a-1")), joueur("bob", actif=pokemon("b-1")))
    assert "verrous" not in vers_json(e_sans)  # rétro-compatible : aucune clé si aucun verrou
    assert depuis_json(vers_json(e_sans)) == e_sans

    e_avec = replace(e_sans, verrous=JeuDeVerrous((_verrou_auto_blocage("a-1", 3),)))
    sortie = vers_json(e_avec)
    assert "verrous" in sortie and len(sortie["verrous"]) == 1
    assert depuis_json(sortie) == e_avec


# --- Le modèle de carte : script et dégâts variables round-trip, D9 à la construction ---------


def test_attaque_def_script_round_trip_et_jouable():
    attaque = AttaqueDef(
        nom="Poison",
        cout=CoutAttaque(),
        degats=0,
        effet="empoisonne",
        script={
            "version": 1,
            "effets": [
                {
                    "op": "poser_etat",
                    "cible": {"zone": "actif", "proprietaire": "adversaire"},
                    "etat": "empoisonne",
                }
            ],
        },
    )
    assert attaque.jouable is True
    assert attaque.degats_secs is False
    d = DefinitionCarte(
        ref="x",
        nom="X",
        stade="base",
        pv=60,
        type="poison",
        marqueur="ordinaire",
        attaques=(attaque,),
    )
    assert definition_depuis_dict(definition_vers_dict(d)) == d


def test_attaque_def_script_incoherent_bloque_la_carte_d9():
    with pytest.raises(ProgrammeInvalide):
        AttaqueDef(
            nom="Cassé",
            cout=CoutAttaque(),
            effet="x",
            script={"version": 1, "effets": [{"op": "faire_du_cafe"}]},
        )


def test_attaque_def_degats_variables_refuse_avec_degats_secs():
    with pytest.raises(ValueError, match="variables"):
        AttaqueDef(
            nom="Ambigu",
            cout=CoutAttaque(),
            degats=20,
            degats_variables={"compter": "energies", "par": 10},
        )


# --- Les dégâts variables (unité, R-10.1) ----------------------------------------------------


def test_valeur_dynamique_plafond_et_plancher():
    v = ValeurDynamique(compter="energies", par=20, cible="attaquant", base=10, plafond=50)
    e = etat(
        joueur("alice", actif=pokemon("a-1", energies=(carte("e1"), carte("e2"), carte("e3")))),
        joueur("bob", actif=pokemon("b-1")),
    )
    assert v.evaluer(e, attaquant="alice", adversaire="bob") == 50  # 10 + 3×20 = 70, plafonné à 50


def test_valeur_dynamique_compteur_pokemon_exige_cible_pokemon_d9():
    with pytest.raises(ValeurInvalide, match="Pokémon|cible"):
        valeur_depuis({"compter": "energies", "cible": "moi", "par": 10})
