"""Talents : passifs, activés une fois par tour, déclenchés — et annulables (``j-cartes-talents``).

Cinq talents **réels**, de natures différentes, scriptés et testés contre l'architecture d'effets
(critère d'acceptation n°3) :

* ``Bouclier Indéfectible`` (*Dauntless Shield*) — **continu** : −30 aux dégâts subis (R-10.1) ;
* ``Garbotoxine`` (type *Garbodor*) — **continu** : éteint les talents (R-12.3), auto-excepté ;
* ``Incisives Travailleuses`` (*Bibarel*) — **activé** : piocher, une fois par tour (R-5) ;
* ``Soin de Camp`` — **déclenché** entre les tours : soigne depuis le banc (R-12.3) ;
* ``Forge Ardente`` — **activé**, seulement depuis l'Actif et désactivé par un état spécial
  (R-11).

Les trois tests exigés par la fiche sont ici : un talent de banc qui soigne entre les tours
(:func:`test_talent_banc_soigne_entre_les_tours`), un talent annulé par un talent adverse
(:func:`test_talent_continu_annule_par_un_talent_adverse`), un talent activé deux fois refusé
(:func:`test_talent_active_deux_fois_refuse`). L'annulation **mutuelle** est tranchée et testée
(:func:`test_deux_verrous_ne_s_annulent_pas`), et le retrait **instantané** à la sortie du jeu
(:func:`test_talent_cesse_a_l_instant_ou_son_pokemon_quitte_le_jeu`). La décision écrite :
``docs/jeu/TALENTS.md``. La CI fait foi.

Un test qui **mord sans le changement** : rien de ce module (le paquet ``pbm_game.effets.talents``,
la transition ``activer_talent``, le drapeau ``Tour.talents_actives_ce_tour``) n'existe avant ce
lot — toute la suite échoue donc à l'import sans le câblage livré ici.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fabrique_dsl import carte, etat, joueur, pokemon, rng

# ``import pbm_game`` enregistre la transition ``activer_talent`` dans le REGISTRE du journal
# (via ``effets.talents_actives``), comme pour ``jouer_objet`` : indispensable à ``appliquer``.
import pbm_game  # noqa: F401
from pbm_game.combat.modele import modificateur_ajout
from pbm_game.effets.continus import (
    FACE_DEFENSEUR,
    PORTEE_EN_JEU,
    EffetContinu,
    collecter_effets_continus,
    modificateurs_degats,
)
from pbm_game.effets.dsl.chargement import charger_programme
from pbm_game.effets.dsl.contexte import ContexteEffet
from pbm_game.effets.dsl.interprete import (
    TYPE_EFFET_DSL,
    compiler_en_effet,
    resolveur_dsl,
)
from pbm_game.effets.evenements import EJ_ENTRE_TOURS, EvenementJeu
from pbm_game.effets.pile import PileEffets, SourceEffet, resoudre_pile
from pbm_game.effets.talents import (
    NATURE_ACTIVE,
    NATURE_CONTINU,
    NATURE_DECLENCHE,
    Talent,
    construire_bus,
    construire_registre_continus,
    identites_neutralisees,
    source_neutralisation,
    talent_actif,
    talents_en_jeu,
)
from pbm_game.journal.modele import ACTION_ACTIVER_TALENT, EVT_TALENT_ACTIVE, Action
from pbm_game.journal.transitions import appliquer
from pbm_game.state.modele import ENDORMI, PARALYSE, Tour
from pbm_game.state.serialisation import depuis_json, vers_json

# ================================================================================================
# Les cinq talents réels — leur fiche et, pour ceux qui en ont un, leur comportement.
# ================================================================================================

REF_BOUCLIER = "jouet-zamazenta"
REF_GARBO = "jouet-garbodor"
REF_CASTOR = "jouet-bibarel"
REF_INFIRMERIE = "jouet-infirmiere"
REF_FORGE = "jouet-forge"

BOUCLIER = Talent(REF_BOUCLIER, "Bouclier Indéfectible", NATURE_CONTINU, "R-10.1")
GARBOTOXINE = Talent(REF_GARBO, "Garbotoxine", NATURE_CONTINU, "R-12.3", supprime_talents=True)
INCISIVES = Talent(REF_CASTOR, "Incisives Travailleuses", NATURE_ACTIVE, "R-5.2")
SOIN_CAMP = Talent(REF_INFIRMERIE, "Soin de Camp", NATURE_DECLENCHE, "R-12.3")
FORGE = Talent(
    REF_FORGE,
    "Forge Ardente",
    NATURE_ACTIVE,
    "R-5.4",
    desactive_si_etat=frozenset({ENDORMI, PARALYSE}),
    depuis_banc=False,
)

#: Le registre de tous les talents scriptés de ce lot (ce que le service fournirait au moteur).
REGISTRE = {
    REF_BOUCLIER: BOUCLIER,
    REF_GARBO: GARBOTOXINE,
    REF_CASTOR: INCISIVES,
    REF_INFIRMERIE: SOIN_CAMP,
    REF_FORGE: FORGE,
}


# --- Continu : le Bouclier retranche 30 aux dégâts subis par son porteur (R-10.1). --------------
def _producteur_bouclier(etat_, ref, cible):
    src = SourceEffet(libelle="Bouclier Indéfectible", ref=ref, instance_id=cible)
    return [
        EffetContinu(
            libelle="Bouclier −30",
            regle="R-10.1",
            source=src,
            portee=PORTEE_EN_JEU,
            cible=cible,
            modificateur=modificateur_ajout("Bouclier Indéfectible", "R-10.1", -30),
            face=FACE_DEFENSEUR,
        )
    ]


PRODUCTEURS_CONTINUS = {REF_BOUCLIER: _producteur_bouclier}


# --- Déclenché : au Checkup, le Soin de Camp soigne 1 marqueur de l'Actif allié. ----------------
SOIN_CAMP_PROG = {
    "version": 1,
    "effets": [{"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}, "nombre": 1}],
}


def _proprietaire(etat_, identite):
    for j in etat_.joueurs:
        en_jeu = ([j.actif] if j.actif is not None else []) + list(j.banc)
        if any(p.cartes[0].instance_id == identite for p in en_jeu):
            return j.id
    raise ValueError(f"Porteur « {identite} » introuvable en jeu.")


def _reacteur_soin(etat_, evenement, pile, rng_, identite):
    """Empile un effet DSL « soigne 1 marqueur de ton Actif » pour le porteur ``identite``."""
    jid = _proprietaire(etat_, identite)
    autre = next(j.id for j in etat_.joueurs if j.id != jid)
    ctx = ContexteEffet(
        source=SourceEffet(libelle="Soin de Camp", ref=REF_INFIRMERIE, instance_id=identite),
        joueur=jid,
        adversaire=autre,
        acteur_actif=identite,
    )
    effet = compiler_en_effet(
        charger_programme(SOIN_CAMP_PROG), ctx, libelle="Soin de Camp", regle="R-12.3"
    )
    return pile.empiler(effet), []


# --- Scripts des talents activés. ---------------------------------------------------------------
INCISIVES_PROG = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}
FORGE_PROG = {
    "version": 1,
    "effets": [{"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}, "nombre": 1}],
}


# ================================================================================================
# 1. Les trois natures et leur fiche (validation D9).
# ================================================================================================


def test_nature_de_talent_inconnue_refusee() -> None:
    """Une nature hors des trois reconnues est refusée (D9), jamais approximée."""
    with pytest.raises(ValueError, match="Nature de talent inconnue"):
        Talent(REF_CASTOR, "Bancal", "porte_par_attaque", "R-5")


def test_etat_desactivant_inconnu_refuse() -> None:
    """Un état désactivant hors des cinq de R-11.1 est refusé (D9)."""
    with pytest.raises(ValueError, match="États désactivants inconnus"):
        Talent(REF_FORGE, "Bancal", NATURE_ACTIVE, "R-5", desactive_si_etat=frozenset({"gelé"}))


# ================================================================================================
# 2. Annulation de talents — la décision d'annulation MUTUELLE (critère n°1).
# ================================================================================================


def _etat_deux_garbos_et_un_bouclier():
    """Alice : Garbodor (Actif) + Bouclier (banc). Bob : Garbodor (Actif). Deux verrous en jeu."""
    alice = joueur(
        "alice",
        actif=pokemon("a-garbo", ref=REF_GARBO),
        banc=(pokemon("a-bouclier", ref=REF_BOUCLIER),),
    )
    bob = joueur("bob", actif=pokemon("b-garbo", ref=REF_GARBO))
    return etat(alice, bob)


def test_deux_verrous_ne_s_annulent_pas() -> None:
    """R-12.3 — deux talents-verrous coexistent (clause « sauf lui-même »), éteignent les autres.

    La décision écrite (``docs/jeu/TALENTS.md``) : un verrou n'éteint ni lui-même ni les autres
    verrous. Donc les deux Garbodor restent **actifs**, et le seul talent neutralisé est le
    Bouclier (un talent ordinaire).
    """
    e = _etat_deux_garbos_et_un_bouclier()
    neutralisees = identites_neutralisees(e, REGISTRE)

    # Les deux verrous survivent (ne s'annulent pas l'un l'autre, ni eux-mêmes).
    assert "a-garbo" not in neutralisees
    assert "b-garbo" not in neutralisees
    assert talent_actif(e, REGISTRE, "a-garbo").actif
    assert talent_actif(e, REGISTRE, "b-garbo").actif

    # Le talent ordinaire, lui, est éteint — et le verdict nomme le responsable (jamais muet).
    assert "a-bouclier" in neutralisees
    assert source_neutralisation(e, REGISTRE) == "Garbotoxine"
    verdict = talent_actif(e, REGISTRE, "a-bouclier")
    assert not verdict.actif
    assert "Garbotoxine" in verdict.raison


def test_sans_verrou_personne_n_est_neutralise() -> None:
    """Sans talent-verrou effectif en jeu, aucun talent n'est éteint (ensemble vide)."""
    alice = joueur("alice", actif=pokemon("a-bouclier", ref=REF_BOUCLIER))
    bob = joueur("bob", actif=pokemon("b-castor", ref=REF_CASTOR))
    e = etat(alice, bob)
    assert identites_neutralisees(e, REGISTRE) == frozenset()
    assert source_neutralisation(e, REGISTRE) is None
    assert talent_actif(e, REGISTRE, "a-bouclier").actif


# ================================================================================================
# 3. Un talent CONTINU annulé par un talent adverse (test exigé) — et le retrait instantané.
# ================================================================================================


def _etat_bouclier(avec_garbo_adverse: bool):
    """Alice : Bouclier (Actif). Bob : attaquant, Garbodor adverse en option."""
    alice = joueur("alice", actif=pokemon("a-bouclier", ref=REF_BOUCLIER))
    bob_actif = pokemon("b-atk", ref="jouet-attaquant")
    banc = (pokemon("b-garbo", ref=REF_GARBO),) if avec_garbo_adverse else ()
    bob = joueur("bob", actif=bob_actif, banc=banc)
    return etat(alice, bob, phase="attaque", numero=3)


def test_talent_continu_annule_par_un_talent_adverse() -> None:
    """R-12.3/R-10.1 — un Garbodor adverse éteint le Bouclier : sa réduction −30 quitte le calcul.

    Dérivé de l'état, pas « défait » : le producteur gardé consulte :func:`talent_actif` et rend
    ``[]`` quand le talent est neutralisé.
    """
    registre_continus = construire_registre_continus(REGISTRE, PRODUCTEURS_CONTINUS)

    # Sans Garbodor adverse : la réduction −30 du défenseur est produite.
    sans = collecter_effets_continus(_etat_bouclier(False), registre_continus)
    _, deff_sans = modificateurs_degats(sans, attaquant="b-atk", defenseur="a-bouclier")
    assert [m.valeur for m in deff_sans] == [-30]

    # Avec Garbodor adverse : le Bouclier est éteint, plus aucune réduction.
    avec = collecter_effets_continus(_etat_bouclier(True), registre_continus)
    _, deff_avec = modificateurs_degats(avec, attaquant="b-atk", defenseur="a-bouclier")
    assert deff_avec == []


def test_talent_cesse_a_l_instant_ou_son_pokemon_quitte_le_jeu() -> None:
    """Critère n°2 — un talent cesse d'agir dès que son Pokémon quitte le jeu, par construction.

    On ne défait rien : la source disparaît de l'état, donc le producteur n'est plus consulté.
    """
    registre_continus = construire_registre_continus(REGISTRE, PRODUCTEURS_CONTINUS)
    e = _etat_bouclier(False)

    present = collecter_effets_continus(e, registre_continus)
    assert any(eff.libelle == "Bouclier −30" for eff in present)

    # Le porteur du Bouclier quitte le jeu (remplacé par un Pokémon ordinaire) : même registre,
    # même appel — l'effet a disparu, sans aucune opération de « retrait ».
    alice_sans = replace(e.joueurs[0], actif=pokemon("a-autre", ref="jouet-ordinaire"))
    e2 = replace(e, joueurs=(alice_sans, e.joueurs[1]))
    parti = collecter_effets_continus(e2, registre_continus)
    assert not any(eff.libelle == "Bouclier −30" for eff in parti)


# ================================================================================================
# 4. Un talent DÉCLENCHÉ de banc qui soigne entre les tours (test exigé).
# ================================================================================================


def test_talent_banc_soigne_entre_les_tours() -> None:
    """R-12.3 — un talent de banc (``Soin de Camp``) soigne 1 marqueur de l'Actif, au Checkup.

    Le porteur est **au banc** : il agit tout de même (``depuis_banc`` vrai). Le bus publie
    :data:`EJ_ENTRE_TOURS`, le réacteur gardé empile l'effet, la pile le résout.
    """
    alice = joueur(
        "alice",
        actif=pokemon("a-actif", compteurs=30),
        banc=(pokemon("a-infirmiere", ref=REF_INFIRMERIE),),
    )
    bob = joueur("bob", actif=pokemon("b-actif"))
    e = etat(alice, bob)

    bus = construire_bus(REGISTRE, {REF_INFIRMERIE: (EJ_ENTRE_TOURS, _reacteur_soin)})
    r = rng()
    checkup = EvenementJeu(EJ_ENTRE_TOURS, {"joueur_actif": "alice", "numero": 1})
    pile, _ = bus.publier(e, checkup, PileEffets(), r)
    e2, _ = resoudre_pile(e, pile, {TYPE_EFFET_DSL: resolveur_dsl}, r)

    assert e2.joueurs[0].actif.compteurs_degats == 20  # 30 − 10 (1 marqueur = 10 PV).


def test_talent_declenche_neutralise_n_empile_rien() -> None:
    """Un talent déclenché neutralisé par un Garbodor adverse n'empile aucun effet (R-12.3)."""
    alice = joueur(
        "alice",
        actif=pokemon("a-actif", compteurs=30),
        banc=(pokemon("a-infirmiere", ref=REF_INFIRMERIE),),
    )
    bob = joueur("bob", actif=pokemon("b-garbo", ref=REF_GARBO))
    e = etat(alice, bob)

    bus = construire_bus(REGISTRE, {REF_INFIRMERIE: (EJ_ENTRE_TOURS, _reacteur_soin)})
    checkup = EvenementJeu(EJ_ENTRE_TOURS, {"joueur_actif": "alice", "numero": 1})
    pile, _ = bus.publier(e, checkup, PileEffets(), rng())
    assert pile.est_vide  # Soin de Camp éteint : rien empilé.


# ================================================================================================
# 5. Un talent ACTIVÉ, une fois par tour PAR POKÉMON (test exigé).
# ================================================================================================


def _etat_castors():
    """Alice (joueur actif) : deux Bibarel portant le même talent activé. Pioche fournie."""
    pioche = tuple(carte(f"p{i}") for i in range(5))
    alice = joueur(
        "alice",
        actif=pokemon("a-castor1", ref=REF_CASTOR),
        banc=(pokemon("a-castor2", ref=REF_CASTOR),),
        pioche=pioche,
    )
    bob = joueur("bob", actif=pokemon("b-actif"))
    return etat(alice, bob)


def _action_castor(identite: str) -> Action:
    return Action(
        ACTION_ACTIVER_TALENT,
        "alice",
        {"pokemon": identite, "nom": "Incisives Travailleuses", "programme": INCISIVES_PROG},
    )


def test_talent_active_deux_fois_refuse() -> None:
    """R-5 — un talent activé deux fois dans le même tour par le MÊME Pokémon est refusé.

    Le suivi est **par Pokémon** (mission n°3) : un autre Bibarel qui porte le même talent reste
    libre de l'activer dans le même tour.
    """
    e = _etat_castors()
    r = rng()

    # Premier usage par a-castor1 : la main grandit d'une carte, l'événement est émis.
    e1, evts = appliquer(e, _action_castor("a-castor1"), r)
    assert len(e1.joueurs[0].main) == 1
    assert evts[0].type == EVT_TALENT_ACTIVE

    # Second usage par le MÊME Pokémon : refusé.
    with pytest.raises(ValueError, match="déjà activé ce tour"):
        appliquer(e1, _action_castor("a-castor1"), r)

    # Un AUTRE Pokémon portant le même talent peut encore l'activer (par Pokémon, non par joueur).
    e2, _ = appliquer(e1, _action_castor("a-castor2"), r)
    assert len(e2.joueurs[0].main) == 2


def test_talent_active_survit_a_un_f5() -> None:
    """Le drapeau « talent activé ce tour » est porté par l'état, donc sérialisé : survit au F5."""
    e = _etat_castors()
    e1, _ = appliquer(e, _action_castor("a-castor1"), rng())
    # Aller-retour JSON complet : le refus du second usage doit tenir après reprise.
    e_repris = depuis_json(vers_json(e1))
    assert "a-castor1|Incisives Travailleuses" in e_repris.tour.talents_actives_ce_tour
    with pytest.raises(ValueError, match="déjà activé ce tour"):
        appliquer(e_repris, _action_castor("a-castor1"), rng())


def test_talent_active_desactive_par_un_etat_special() -> None:
    """R-11 — un talent activé « selon la carte » refusé si son porteur a l'état bloquant."""
    # Forge Ardente ne s'active pas tant que son porteur est Endormi (desactive_si_etat).
    porteur = pokemon("a-forge", ref=REF_FORGE, etats=frozenset({ENDORMI}), compteurs=20)
    alice = joueur("alice", actif=porteur)
    bob = joueur("bob", actif=pokemon("b-actif"))
    e = etat(alice, bob)
    action = Action(
        ACTION_ACTIVER_TALENT,
        "alice",
        {
            "pokemon": "a-forge",
            "nom": "Forge Ardente",
            "programme": FORGE_PROG,
            "desactive_si_etat": [ENDORMI, PARALYSE],
        },
    )
    with pytest.raises(ValueError, match="désactivé"):
        appliquer(e, action, rng())


def test_talent_active_refuse_hors_du_joueur_actif() -> None:
    """Seul le joueur actif active un talent (R-5.1) — le refus cite la règle, jamais muet."""
    e = _etat_castors()
    action = Action(
        ACTION_ACTIVER_TALENT,
        "bob",
        {"pokemon": "a-castor1", "nom": "x", "programme": INCISIVES_PROG},
    )
    with pytest.raises(ValueError, match="joueur actif"):
        appliquer(e, action, rng())


def test_talent_active_sans_script_refuse() -> None:
    """Un talent activé sans script est refusé (D9), jamais approximé."""
    e = _etat_castors()
    action = Action(ACTION_ACTIVER_TALENT, "alice", {"pokemon": "a-castor1", "nom": "x"})
    with pytest.raises(ValueError, match="sans script"):
        appliquer(e, action, rng())


# ================================================================================================
# 6. Le portillon : place (banc interdit) et état spécial.
# ================================================================================================


def test_talent_qui_n_agit_pas_depuis_le_banc() -> None:
    """``depuis_banc`` faux : au banc, le talent n'agit pas — le verdict le dit (jamais muet)."""
    alice = joueur("alice", actif=pokemon("a-actif"), banc=(pokemon("a-forge", ref=REF_FORGE),))
    bob = joueur("bob", actif=pokemon("b-actif"))
    e = etat(alice, bob)
    verdict = talent_actif(e, REGISTRE, "a-forge")
    assert not verdict.actif
    assert "Actif" in verdict.raison


def test_talent_desactive_par_un_etat_special() -> None:
    """Un talent dont le porteur est dans un état désactivant n'agit pas (R-11)."""
    alice = joueur("alice", actif=pokemon("a-forge", ref=REF_FORGE, etats=frozenset({PARALYSE})))
    bob = joueur("bob", actif=pokemon("b-actif"))
    e = etat(alice, bob)
    verdict = talent_actif(e, REGISTRE, "a-forge")
    assert not verdict.actif
    assert "paralyse" in verdict.raison


def test_talent_actif_ne_mute_pas_l_etat() -> None:
    """Le portillon est **pur** : il ne touche pas à l'état (deux appels, même verdict)."""
    e = _etat_deux_garbos_et_un_bouclier()
    avant = vers_json(e)
    talent_actif(e, REGISTRE, "a-bouclier")
    talents_en_jeu(e, REGISTRE)
    assert vers_json(e) == avant


# ================================================================================================
# 7. Sérialisation du drapeau « talents activés ce tour » (rejouabilité).
# ================================================================================================


def test_serialisation_du_drapeau_talents_actives() -> None:
    """Le nouveau champ ``Tour.talents_actives_ce_tour`` fait l'aller-retour JSON sans perte."""
    tour = Tour(
        joueur_actif="alice",
        numero=4,
        phase="principale",
        talents_actives_ce_tour=frozenset({"a-castor1|Incisives Travailleuses"}),
    )
    alice = joueur("alice", actif=pokemon("a-x"))
    bob = joueur("bob", actif=pokemon("b-x"))
    e = replace(etat(alice, bob), tour=tour)
    repris = depuis_json(vers_json(e))
    assert repris.tour.talents_actives_ce_tour == frozenset({"a-castor1|Incisives Travailleuses"})


def test_etat_ancien_sans_le_champ_se_relit() -> None:
    """Un tour sérialisé **avant** ce lot (sans la clé) se relit : drapeau vide, sans migration."""
    alice = joueur("alice", actif=pokemon("a-x"))
    bob = joueur("bob", actif=pokemon("b-x"))
    donnees = vers_json(etat(alice, bob))
    del donnees["tour"]["talents_actives_ce_tour"]  # état d'avant ce lot
    repris = depuis_json(donnees)
    assert repris.tour.talents_actives_ce_tour == frozenset()
