"""Les **Outils Pokémon** — attachés, défaussés au K.O. (lot ``j-cartes-outils``).

Les trois critères d'acceptation de la fiche sont ici, preuve à l'appui :

* **Le retrait d'un Outil de PV provoque le K.O.** si les compteurs dépassent le nouveau seuil
  (:func:`test_retrait_outil_de_pv_provoque_le_ko_immediat_r131`) — et les compteurs **ne bougent
  pas**, c'est le **seuil** qui descend (R-13.1) ;
* **un Pokémon ne porte jamais deux Outils** (:func:`test_deuxieme_outil_refuse_r37`) ;
* **trois Outils réels sont scriptés et testés** — Protective Poncho (``B2-147``/``B2-234``) et
  Metal Core Barrier (``B2-148``), le seul sous-ensemble d'Outils que le catalogue de jeu enrichit.

Un test qui **mord sans le changement** : rien de ce module (les transitions ``attacher_outil`` /
``retirer_outil``, ``effets.outils``, le helper ``fiches_avec_seuils_continus``) n'existe avant ce
lot — toute la suite échoue donc à l'import sans le câblage livré ici. La CI fait foi.
"""

from __future__ import annotations

import pytest
from fabrique_dsl import carte, etat, joueur, pokemon, rng

# ``import pbm_game`` enregistre les transitions ``attacher_outil`` / ``retirer_outil`` dans le
# REGISTRE du journal (via ``effets.outils``) : indispensable à ``appliquer``, et ce qui fait
# mordre la suite sans le lot.
import pbm_game  # noqa: F401
from pbm_game.combat.fin import resoudre_kos
from pbm_game.combat.modele import Modificateur
from pbm_game.combat.resolution import resoudre_degats
from pbm_game.effets.continus import (
    PORTEE_OUTIL,
    EffetContinu,
    collecter_effets_continus,
    fiches_avec_seuils_continus,
    modificateurs_degats,
    seuil_ko,
)
from pbm_game.effets.outils import (
    METAL_CORE_BARRIER,
    PROTECTIVE_PONCHO_A,
    PROTECTIVE_PONCHO_B,
    appliquer_attacher_outil,
    appliquer_retirer_outil,
    producteur_protective_poncho,
    registre_outils,
)
from pbm_game.effets.pile import SourceEffet
from pbm_game.journal.modele import (
    ACTION_ATTACHER_OUTIL,
    ACTION_RETIRER_OUTIL,
    EVT_KO,
    EVT_OUTIL_ATTACHE,
    EVT_OUTIL_RETIRE,
    Action,
)
from pbm_game.journal.transitions import REGISTRE
from pbm_game.sortie.evenements import PROJECTEURS

_RNG = rng()


def _attacher(jid: str, carte_main: str, cible: str, nom: str = "Outil") -> Action:
    return Action(
        ACTION_ATTACHER_OUTIL, jid, {"carte_main": carte_main, "cible": cible, "nom": nom}
    )


def _retirer(prop: str, cible: str, *, par: str, fiches: dict) -> Action:
    params = {"proprietaire": prop, "cible": cible, "fiches": fiches}
    return Action(ACTION_RETIRER_OUTIL, par, params)


# --- Attacher : Actif, banc, et le refus du deuxième Outil (R-3.7) -----------------------


def test_attacher_outil_sur_actif_r37():
    """R-3.7 — l'Outil quitte la main et rejoint l'Actif ; un EVT_OUTIL_ATTACHE est émis."""
    al = joueur("alice", actif=pokemon("p-a"), main=(carte("o-1", "B2-147"),))
    e = etat(al, joueur("bob", actif=pokemon("p-b")))

    e2, evts = appliquer_attacher_outil(e, _attacher("alice", "o-1", "p-a"), _RNG)

    assert e2.joueurs[0].actif.outil is not None
    assert e2.joueurs[0].actif.outil.instance_id == "o-1"
    assert not e2.joueurs[0].main  # la carte a quitté la main
    assert evts[0].type == EVT_OUTIL_ATTACHE
    assert evts[0].donnees["cible"] == "p-a"
    assert evts[0].donnees["ref"] == "B2-147"


def test_attacher_outil_sur_un_pokemon_du_banc_r37():
    """R-3.7 — un Outil s'attache aussi à un Pokémon du **banc**, pas seulement à l'Actif."""
    al = joueur(
        "alice", actif=pokemon("p-a"), banc=(pokemon("b-1"),), main=(carte("o-1", "B2-148"),)
    )
    e = etat(al, joueur("bob", actif=pokemon("p-b")))

    e2, _ = appliquer_attacher_outil(e, _attacher("alice", "o-1", "b-1"), _RNG)

    assert e2.joueurs[0].banc[0].outil is not None
    assert e2.joueurs[0].banc[0].outil.instance_id == "o-1"
    assert e2.joueurs[0].actif.outil is None  # l'Actif n'a rien reçu


def test_deuxieme_outil_refuse_r37():
    """R-3.7 — un Pokémon qui porte déjà un Outil en refuse un second, bruyamment."""
    porteur = pokemon("p-a", outil=carte("o-deja", "B2-147"))
    al = joueur("alice", actif=porteur, main=(carte("o-2", "B2-148"),))
    e = etat(al, joueur("bob", actif=pokemon("p-b")))

    with pytest.raises(ValueError, match="déjà un Outil"):
        appliquer_attacher_outil(e, _attacher("alice", "o-2", "p-a"), _RNG)


def test_attacher_outil_par_un_non_actif_refuse_r55():
    """R-5.5 — seul le joueur actif attache un Outil (le tour est à alice)."""
    bo = joueur("bob", actif=pokemon("p-b"), main=(carte("o-1", "B2-147"),))
    e = etat(joueur("alice", actif=pokemon("p-a")), bo)  # tour d'alice

    with pytest.raises(ValueError, match="joueur actif"):
        appliquer_attacher_outil(e, _attacher("bob", "o-1", "p-b"), _RNG)


def test_plusieurs_outils_dans_le_tour_r55():
    """R-5.5 — attacher un Outil ne lève aucun drapeau : on en attache un second dans le tour."""
    al = joueur(
        "alice",
        actif=pokemon("p-a"),
        banc=(pokemon("b-1"),),
        main=(carte("o-1", "B2-147"), carte("o-2", "B2-148")),
    )
    e = etat(al, joueur("bob", actif=pokemon("p-b")))

    e, _ = appliquer_attacher_outil(e, _attacher("alice", "o-1", "p-a"), _RNG)
    # Rien dans le tour n'interdit un second Outil (contrairement au Supporter, R-5.5).
    e, _ = appliquer_attacher_outil(e, _attacher("alice", "o-2", "b-1"), _RNG)

    assert e.joueurs[0].actif.outil.instance_id == "o-1"
    assert e.joueurs[0].banc[0].outil.instance_id == "o-2"


# --- Critère n°1 : retrait d'un Outil de PV → K.O. immédiat (R-13.1) ----------------------


def _jouet_pv30(etat_, ref, cible):
    """Un Outil **jouet** qui donne **+30 PV** au porteur — pour prouver le mécanisme.

    (Le catalogue de jeu n'enrichit aujourd'hui aucun Outil de PV ; le cadre, lui, le gère — ce
    producteur jouet le démontre, comme ``effets.continus`` l'y invite.)
    """
    source = SourceEffet(libelle="Jouet", ref=ref, instance_id=ref)
    return [
        EffetContinu(
            libelle="Jouet : +30 PV",
            regle="R-3.7",
            source=source,
            portee=PORTEE_OUTIL,
            cible=cible,
            pv=30,
        )
    ]


def test_retrait_outil_de_pv_provoque_le_ko_immediat_r131():
    """R-13.1 — un Outil +30 PV tient un Pokémon à 70 compteurs en vie (seuil 90) ; le
    retirer ramène le seuil à 60, donc 70 ≥ 60 ⇒ **K.O. immédiat**. Compteurs inchangés."""
    registre = {"toy-pv": _jouet_pv30}
    # alice (joueur actif) : Actif à 70 compteurs portant l'Outil de PV, un banc pour promouvoir.
    porteur = pokemon("p-a", compteurs=70, outil=carte("t-1", "toy-pv"))
    al = joueur("alice", actif=porteur, banc=(pokemon("b-1"),))
    bo = joueur("bob", actif=pokemon("p-b"), recompenses=(carte("r1"), carte("r2")))
    e = etat(al, bo)

    # PV imprimés : 60. Avec l'Outil, le seuil EFFECTIF monte à 90 ⇒ pas K.O. (70 < 90).
    imprimees = {"p-a": {"pv": 60, "marqueur": "ordinaire"}}
    avec_outil = fiches_avec_seuils_continus(e, registre, imprimees)
    assert avec_outil["p-a"]["pv"] == 90
    e_vivant, evts_sans = resoudre_kos(e, avec_outil, ("alice", "bob"))
    assert e_vivant.joueurs[0].actif is not None  # tenu en vie par l'Outil
    assert not any(ev.type == EVT_KO for ev in evts_sans)

    # On retire l'Outil : le service fournit alors le PV EFFECTIF post-retrait (plus de +30 ⇒ 60).
    apres = {"p-a": {"pv": 60, "marqueur": "ordinaire"}}
    e2, evts = appliquer_retirer_outil(e, _retirer("alice", "p-a", par="bob", fiches=apres), _RNG)

    assert evts[0].type == EVT_OUTIL_RETIRE
    assert any(ev.type == EVT_KO for ev in evts), "le retrait aurait dû provoquer un K.O."
    assert e2.joueurs[0].actif is None  # l'Actif est tombé
    # L'Outil retiré est dans la défausse d'alice (R-13.2) UNE seule fois : il y était
    # déjà quand le K.O. a défaussé le reste (pas de doublon).
    refs_defausse = [c.ref for c in e2.joueurs[0].defausse]
    assert refs_defausse.count("toy-pv") == 1


def test_pv_continus_changent_le_seuil_pas_les_compteurs_r131():
    """R-13.1 — l'Outil de PV déplace le **seuil**, jamais les compteurs déjà posés."""
    registre = {"toy-pv": _jouet_pv30}
    porteur = pokemon("p-a", compteurs=70, outil=carte("t-1", "toy-pv"))
    e = etat(joueur("alice", actif=porteur), joueur("bob", actif=pokemon("p-b")))

    effets = collecter_effets_continus(e, registre)
    assert seuil_ko(60, effets, "p-a") == 90  # seuil relevé
    assert e.joueurs[0].actif.compteurs_degats == 70  # compteurs inchangés


# --- Défausse au K.O. du porteur (R-13.2), déjà portée par combat.ko ----------------------


def test_outil_defausse_avec_le_porteur_au_ko_r132():
    """R-13.2 — un K.O. « ordinaire » défausse le Pokémon avec son Outil (non retiré avant)."""
    porteur = pokemon("p-a", compteurs=70, outil=carte("o-x", "B2-147"))
    al = joueur("alice", actif=porteur, banc=(pokemon("b-1"),))
    bo = joueur("bob", actif=pokemon("p-b"), recompenses=(carte("r1"),))
    e = etat(al, bo)

    e2, _ = resoudre_kos(e, {"p-a": {"pv": 60, "marqueur": "ordinaire"}}, ("alice", "bob"))

    assert e2.joueurs[0].actif is None
    assert any(c.ref == "B2-147" for c in e2.joueurs[0].defausse)  # l'Outil a suivi son porteur


# --- Critère n°3 : trois Outils réels scriptés et testés ----------------------------------


def test_protective_poncho_previent_les_degats_au_banc_r37():
    """R-3.7 — Protective Poncho annule les dégâts au porteur **au banc** ; rien si Actif."""
    poncho = producteur_protective_poncho({})
    registre = {PROTECTIVE_PONCHO_A: poncho}

    # Porteur au banc : l'effet s'applique (dégâts au banc, R-10.5).
    porteur = pokemon("b-1", ref="poke-x", outil=carte("pon", PROTECTIVE_PONCHO_A))
    al = joueur("alice", actif=pokemon("p-a"), banc=(porteur,))
    e = etat(al, joueur("bob", actif=pokemon("p-b")))
    effets = collecter_effets_continus(e, registre)
    _att, deff = modificateurs_degats(effets, attaquant="p-b", defenseur="b-1")
    res = resoudre_degats(base=100, modificateurs_defenseur=deff, au_banc=True)
    assert res.degats == 0  # tous les dégâts sont prévenus

    # Même porteur, mais **Actif** : l'Outil ne prévient rien (la carte ne vaut qu'au banc).
    actif = pokemon("b-1", ref="poke-x", outil=carte("pon", PROTECTIVE_PONCHO_A))
    e_actif = etat(joueur("alice", actif=actif), joueur("bob", actif=pokemon("p-b")))
    effets_actif = collecter_effets_continus(e_actif, registre)
    _a, deff_actif = modificateurs_degats(effets_actif, attaquant="p-b", defenseur="b-1")
    assert deff_actif == []
    assert resoudre_degats(base=100, modificateurs_defenseur=deff_actif).degats == 100


def test_metal_core_barrier_moins_50_pokemon_metal_r37():
    """R-3.7 — Metal Core Barrier retire 50 dégâts au porteur **Metal** ; rien sinon."""
    meta = {"poke-metal": {"type": "metal"}, "poke-feu": {"type": "fire"}}
    registre = registre_outils(meta)

    metal = pokemon("m-1", ref="poke-metal", outil=carte("mcb", METAL_CORE_BARRIER))
    e = etat(joueur("alice", actif=metal), joueur("bob", actif=pokemon("p-b")))
    effets = collecter_effets_continus(e, registre)
    _att, deff = modificateurs_degats(effets, attaquant="p-b", defenseur="m-1")
    assert resoudre_degats(base=90, modificateurs_defenseur=deff).degats == 40  # 90 − 50

    feu = pokemon("f-1", ref="poke-feu", outil=carte("mcb2", METAL_CORE_BARRIER))
    e_feu = etat(joueur("alice", actif=feu), joueur("bob", actif=pokemon("p-b")))
    effets_feu = collecter_effets_continus(e_feu, registre)
    _a, deff_feu = modificateurs_degats(effets_feu, attaquant="p-b", defenseur="f-1")
    assert deff_feu == []  # type non-Metal : la réduction ne s'applique pas
    assert resoudre_degats(base=90, modificateurs_defenseur=deff_feu).degats == 90


def test_registre_outils_couvre_les_trois_refs_reelles():
    """Les trois ``ref`` réelles d'Outils du catalogue de jeu ont un producteur scripté."""
    registre = registre_outils({})
    assert set(registre) == {PROTECTIVE_PONCHO_A, PROTECTIVE_PONCHO_B, METAL_CORE_BARRIER}


def test_retrait_de_metal_core_barrier_met_fin_a_son_effet_r37():
    """R-3.7 — retirer l'Outil (p. ex. auto-défausse de fin de tour) éteint sa réduction."""
    meta = {"poke-metal": {"type": "metal"}}
    registre = registre_outils(meta)
    metal = pokemon("m-1", ref="poke-metal", outil=carte("mcb", METAL_CORE_BARRIER))
    e = etat(joueur("alice", actif=metal), joueur("bob", actif=pokemon("p-b")))

    assert collecter_effets_continus(e, registre)  # l'effet est actif tant que l'Outil est là

    e2, evts = appliquer_retirer_outil(e, _retirer("alice", "m-1", par="alice", fiches={}), _RNG)
    assert evts[0].type == EVT_OUTIL_RETIRE
    assert not collecter_effets_continus(e2, registre)  # plus d'Outil ⇒ plus d'effet
    assert any(c.ref == METAL_CORE_BARRIER for c in e2.joueurs[0].defausse)  # défaussé chez alice


# --- Parité et enregistrement (aucun 500 par omission) ------------------------------------


def test_transitions_outils_enregistrees():
    """``appliquer`` reconnaît les deux actions d'Outil (sinon une action légale ferait 500)."""
    assert ACTION_ATTACHER_OUTIL in REGISTRE
    assert ACTION_RETIRER_OUTIL in REGISTRE


def test_evenements_outils_projetes():
    """Les deux EVT_OUTIL_* ont un projecteur public (parité émetteurs ↔ projecteurs)."""
    assert EVT_OUTIL_ATTACHE in PROJECTEURS
    assert EVT_OUTIL_RETIRE in PROJECTEURS


def test_producteurs_rendent_des_modificateurs_valides():
    """Garde-fou de typage : les producteurs produisent bien des Modificateur valides."""
    meta = {"poke-metal": {"type": "metal"}}
    metal = pokemon("m-1", ref="poke-metal", outil=carte("mcb", METAL_CORE_BARRIER))
    e = etat(joueur("alice", actif=metal), joueur("bob", actif=pokemon("p-b")))
    effets = collecter_effets_continus(e, registre_outils(meta))
    assert all(isinstance(ef.modificateur, Modificateur) for ef in effets)
