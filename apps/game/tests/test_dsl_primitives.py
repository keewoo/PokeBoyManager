"""Chaque **primitive**, isolément — ce qu'elle fait, et le cas « aucune cible » (critère n°2).

Pour chaque primitive : (1) un test où elle agit, avec état de départ et état attendu ; (2) un test
où sa cible est **vide**, qui vérifie qu'elle ne bloque pas la partie mais **le dit**
(``effet_sans_cible``). C'est exactement ce que le critère d'acceptation exige.
"""

from __future__ import annotations

from fabrique_dsl import carte, contexte, etat, joueur, pokemon, rng

from pbm_game.effets.dsl import charger_programme, executer_programme
from pbm_game.effets.pile import EVT_EFFET_SANS_CIBLE


def _run(e, instrs, ctx=None, r=None, meta=None):
    prog = charger_programme({"version": 1, "effets": instrs})
    c = ctx if ctx is not None else contexte(metadonnees=meta or {})
    return executer_programme(e, prog, c, r or rng())


def _a_dit_sans_cible(res) -> bool:
    return any(ev.type == EVT_EFFET_SANS_CIBLE for ev in res.evenements)


def _actif(res, jid):
    for j in res.etat.joueurs:
        if j.id == jid:
            return j.actif
    raise AssertionError(jid)


def _joueur(res, jid):
    for j in res.etat.joueurs:
        if j.id == jid:
            return j
    raise AssertionError(jid)


# --- piocher -----------------------------------------------------------------


def test_piocher_deplace_du_sommet_vers_la_main():
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("p1"), carte("p2"), carte("p3")))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(etat(alice, bob), [{"op": "piocher", "nombre": 2}])
    a = _joueur(res, "alice")
    assert [c.instance_id for c in a.main] == ["p1", "p2"]
    assert [c.instance_id for c in a.pioche] == ["p3"]


def test_piocher_pioche_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(etat(alice, bob), [{"op": "piocher", "nombre": 2}])
    assert _a_dit_sans_cible(res)
    assert _joueur(res, "alice").main == ()


# --- chercher ----------------------------------------------------------------


def test_chercher_un_pokemon_de_base_vers_la_main():
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("pk", "r-pk"), carte("en", "r-en")))
    bob = joueur("bob", actif=pokemon("b"))
    meta = {"r-pk": {"categorie": "pokemon", "stade": "base"}, "r-en": {"categorie": "energie"}}
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "chercher",
                "cible": {
                    "zone": "pioche",
                    "proprietaire": "moi",
                    "categorie": "pokemon",
                    "stade": "base",
                    "nombre": 1,
                },
            }
        ],
        meta=meta,
    )
    a = _joueur(res, "alice")
    assert "pk" in [c.instance_id for c in a.main]
    assert "pk" not in [c.instance_id for c in a.pioche]


def test_chercher_sans_correspondance_le_dit():
    alice = joueur("alice", actif=pokemon("a"), pioche=(carte("en", "r-en"),))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "chercher",
                "cible": {
                    "zone": "pioche",
                    "proprietaire": "moi",
                    "categorie": "pokemon",
                    "nombre": 1,
                },
            }
        ],
        meta={"r-en": {"categorie": "energie"}},
    )
    assert _a_dit_sans_cible(res)


# --- defausser ---------------------------------------------------------------


def test_defausser_depuis_la_main():
    alice = joueur("alice", actif=pokemon("a"), main=(carte("m1"), carte("m2")))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi", "nombre": 1}}],
    )
    a = _joueur(res, "alice")
    assert len(a.main) == 1
    assert len(a.defausse) == 1


def test_defausser_main_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "defausser", "cible": {"zone": "main", "proprietaire": "moi"}}]
    )
    assert _a_dit_sans_cible(res)


# --- attacher ----------------------------------------------------------------


def test_attacher_une_energie_de_la_main_a_l_actif():
    alice = joueur("alice", actif=pokemon("a"), main=(carte("e1", "r-e"),))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "attacher",
                "source": {
                    "zone": "main",
                    "proprietaire": "moi",
                    "categorie": "energie",
                    "nombre": 1,
                },
                "cible": {"zone": "actif", "proprietaire": "moi"},
            }
        ],
        meta={"r-e": {"categorie": "energie"}},
    )
    assert [c.instance_id for c in _actif(res, "alice").energies] == ["e1"]
    assert _joueur(res, "alice").main == ()


def test_attacher_sans_source_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "attacher",
                "source": {"zone": "main", "proprietaire": "moi", "categorie": "energie"},
                "cible": {"zone": "actif", "proprietaire": "moi"},
            }
        ],
    )
    assert _a_dit_sans_cible(res)


# --- deplacer ----------------------------------------------------------------


def test_deplacer_une_energie_de_l_actif_vers_le_banc():
    alice = joueur(
        "alice",
        actif=pokemon("a", energies=(carte("e1"), carte("e2"))),
        banc=(pokemon("b1"),),
    )
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "deplacer",
                "nombre": 1,
                "source": {"zone": "actif", "proprietaire": "moi"},
                "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            }
        ],
    )
    a = _joueur(res, "alice")
    assert len(a.actif.energies) == 1
    assert len(a.banc[0].energies) == 1


def test_deplacer_sans_energie_le_dit():
    alice = joueur("alice", actif=pokemon("a"), banc=(pokemon("b1"),))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "deplacer",
                "nombre": 1,
                "source": {"zone": "actif", "proprietaire": "moi"},
                "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1},
            }
        ],
    )
    assert _a_dit_sans_cible(res)


# --- soigner -----------------------------------------------------------------


def test_soigner_retire_des_marqueurs():
    alice = joueur("alice", actif=pokemon("a", compteurs=30))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}, "nombre": 2}],
    )
    assert _actif(res, "alice").compteurs_degats == 10  # 30 − 2×10


def test_soigner_tout_quand_nombre_absent():
    alice = joueur("alice", actif=pokemon("a", compteurs=50))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}}]
    )
    assert _actif(res, "alice").compteurs_degats == 0


def test_soigner_plancher_a_zero():
    alice = joueur("alice", actif=pokemon("a", compteurs=10))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "soigner", "cible": {"zone": "actif", "proprietaire": "moi"}, "nombre": 5}],
    )
    assert _actif(res, "alice").compteurs_degats == 0


def test_soigner_banc_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "soigner", "cible": {"zone": "banc", "proprietaire": "moi"}, "nombre": 1}],
    )
    assert _a_dit_sans_cible(res)


# --- poser_compteurs ---------------------------------------------------------


def test_poser_compteurs_ajoute_des_degats():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_compteurs",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 3,
            }
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 30


def test_poser_compteurs_sans_cible_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob")  # pas d'actif
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_compteurs",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 3,
            }
        ],
    )
    assert _a_dit_sans_cible(res)


# --- infliger_degats ---------------------------------------------------------


def test_infliger_degats_pose_en_compteurs():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b", compteurs=10))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "infliger_degats",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 20,
            }
        ],
    )
    assert _actif(res, "bob").compteurs_degats == 30


def test_infliger_degats_sans_cible_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob")
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "infliger_degats",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "nombre": 20,
            }
        ],
    )
    assert _a_dit_sans_cible(res)


# --- melanger ----------------------------------------------------------------


def test_melanger_conserve_le_multiensemble():
    cartes = tuple(carte(f"p{i}") for i in range(6))
    alice = joueur("alice", actif=pokemon("a"), pioche=cartes)
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}}]
    )
    avant = {c.instance_id for c in cartes}
    apres = {c.instance_id for c in _joueur(res, "alice").pioche}
    assert avant == apres  # mêmes cartes, ordre (probablement) changé


def test_melanger_pioche_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "melanger", "cible": {"zone": "pioche", "proprietaire": "moi"}}]
    )
    assert _a_dit_sans_cible(res)


# --- reveler / regarder ------------------------------------------------------


def test_reveler_journalise_les_refs():
    alice = joueur("alice", actif=pokemon("a"), main=(carte("m1", "r-1"),))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "reveler", "cible": {"zone": "main", "proprietaire": "moi"}}]
    )
    refs = [ev.donnees.get("refs") for ev in res.evenements if ev.type == "dsl_primitive"]
    assert ["r-1"] in refs


def test_regarder_ne_fuite_pas_les_refs():
    alice = joueur(
        "alice", actif=pokemon("a"), pioche=(carte("p1", "secret-1"), carte("p2", "secret-2"))
    )
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "regarder",
                "cible": {
                    "zone": "pioche",
                    "proprietaire": "moi",
                    "position": "dessus",
                    "nombre": 2,
                },
            }
        ],
    )
    for ev in res.evenements:
        assert "secret-1" not in str(ev.donnees)  # regarder sa pioche ne la révèle pas


def test_regarder_zone_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "regarder", "cible": {"zone": "pioche", "proprietaire": "moi"}}]
    )
    assert _a_dit_sans_cible(res)


# --- changer_actif -----------------------------------------------------------


def test_changer_actif_echange_banc_et_actif():
    alice = joueur("alice", actif=pokemon("a-actif"), banc=(pokemon("a-banc"),))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "changer_actif", "cible": {"zone": "banc", "proprietaire": "moi", "nombre": 1}}],
    )
    a = _joueur(res, "alice")
    assert a.actif.cartes[0].instance_id == "a-banc"
    assert "a-actif" in [p.cartes[0].instance_id for p in a.banc]


def test_changer_actif_banc_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a-actif"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [{"op": "changer_actif", "cible": {"zone": "banc", "proprietaire": "moi"}}],
    )
    assert _a_dit_sans_cible(res)


# --- poser_etat / retirer_etat ----------------------------------------------


def test_poser_etat_empoisonne_l_actif_adverse():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_etat",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "etat": "empoisonne",
            }
        ],
    )
    assert "empoisonne" in _actif(res, "bob").etats_speciaux


def test_poser_etat_un_seul_etat_d_orientation():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b", etats=frozenset({"endormi"})))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_etat",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "etat": "paralyse",
            }
        ],
    )
    etats = _actif(res, "bob").etats_speciaux
    assert "paralyse" in etats and "endormi" not in etats  # R-11.8 : un seul à la fois


def test_retirer_tous_les_etats():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b", etats=frozenset({"empoisonne", "paralyse"})))
    res = _run(
        etat(alice, bob),
        [{"op": "retirer_etat", "cible": {"zone": "actif", "proprietaire": "adversaire"}}],
    )
    assert _actif(res, "bob").etats_speciaux == frozenset()


def test_poser_etat_sans_cible_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob")
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "poser_etat",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
                "etat": "brule",
            }
        ],
    )
    assert _a_dit_sans_cible(res)


# --- empecher ----------------------------------------------------------------


def test_empecher_pose_un_verrou_global_sans_cible_nommee():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(
        etat(alice, bob), [{"op": "empecher", "verrou": "pas_de_supporter", "portee": "ce_tour"}]
    )
    assert len(res.verrous) == 1
    assert res.verrous[0].nom == "pas_de_supporter"
    assert res.verrous[0].cible is None  # global


def test_empecher_cible_un_pokemon_precis():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b-actif"))
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "empecher",
                "verrou": "ne_peut_attaquer",
                "portee": "prochain_tour",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
            }
        ],
    )
    assert res.verrous[0].cible == "b-actif"


def test_empecher_cible_nommee_vide_le_dit():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob")
    res = _run(
        etat(alice, bob),
        [
            {
                "op": "empecher",
                "verrou": "ne_peut_attaquer",
                "portee": "ce_tour",
                "cible": {"zone": "actif", "proprietaire": "adversaire"},
            }
        ],
    )
    assert _a_dit_sans_cible(res)
    assert res.verrous == ()


# --- annuler -----------------------------------------------------------------


def test_annuler_leve_le_drapeau():
    alice = joueur("alice", actif=pokemon("a"))
    bob = joueur("bob", actif=pokemon("b"))
    res = _run(etat(alice, bob), [{"op": "annuler"}])
    assert res.degats_annules is True
