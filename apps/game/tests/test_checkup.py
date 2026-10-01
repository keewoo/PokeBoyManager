"""Tests du **Pokémon Checkup** — la phase entre les deux tours (lot ``j-checkup``, R-12).

Le moteur est **pur** : chaque test construit un état, appelle la résolution et contrôle le
résultat ; aucune base, aucun réseau. Chaque test de règle **cite son identifiant** ``R-x.y``
dans son nom et son docstring, et un test vérifie que chaque règle citée par les événements du
Checkup existe bel et bien dans le corpus ``docs/jeu/REGLES.md``.

Sans le paquet ``pbm_game.checkup`` (le livrable de ce lot), l'import en tête échoue : toute la
suite échoue alors, ce qui est la preuve exigée « un test qui échoue sans le changement ».
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pbm_game.actions import actions_legales
from pbm_game.checkup import BRULURE_DEGATS, POISON_DEGATS, resoudre_checkup
from pbm_game.journal import (
    ACTION_CHECKUP,
    AUTEUR_SYSTEME,
    EVT_EFFET_EXPIRE,
    EVT_ETAT_CHECKUP,
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION_REQUISE,
    RAISON_PLUS_DE_POKEMON,
    Action,
    Evenement,
    appliquer,
    jouer,
    partie_neuve,
    rejouer,
)
from pbm_game.journal.serialisation import action_depuis_json, action_vers_json
from pbm_game.regles import MOTIF_REGLE, identifiants_definis
from pbm_game.rng import FACE, PILE, Rng, flux_checkup
from pbm_game.state import (
    BRULE,
    EMPOISONNE,
    ENDORMI,
    PARALYSE,
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    RAISON_EGALITE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
    carte_active,
)
from pbm_game.tour import FENETRE_EXPIRATION_EFFETS

RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"

GRAINE_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # 16 octets (minimum du Rng)


def _regles_definies() -> set[str]:
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


def _rng() -> Rng:
    return Rng(bytes.fromhex(GRAINE_HEX))


# --- Fabriques déterministes -------------------------------------------------


def _pk(
    jid: str,
    tag: str = "actif",
    *,
    compteurs: int = 0,
    etats: frozenset[str] = frozenset(),
    energies: tuple[Carte, ...] = (),
    outil: Carte | None = None,
) -> PokemonEnJeu:
    return PokemonEnJeu(
        cartes=(Carte(f"{jid}-{tag}", "ref-pk"),),
        energies=energies,
        outil=outil,
        compteurs_degats=compteurs,
        etats_speciaux=etats,
    )


def _etat(alice: Joueur, bob: Joueur, *, actif: str = "bob") -> EtatPartie:
    """État en phase Checkup ; ``actif`` est le joueur dont le tour **s'achève** (R-12.4)."""
    tour = Tour(joueur_actif=actif, numero=5, phase=PHASE_CHECKUP)
    return EtatPartie(joueurs=(alice, bob), tour=tour)


def _fiche(pokemon: PokemonEnJeu, pv: int, recompenses: int = 1) -> dict:
    return {carte_active(pokemon).instance_id: {"pv": pv, "recompenses": recompenses}}


# =========================================================================================
# Pureté / API
# =========================================================================================


def test_import_checkup_ne_tire_aucune_dependance_lourde():
    """Le moteur est pur : importer ``pbm_game.checkup`` ne charge ni HTTP, ni base, ni React."""
    interdits = {"requests", "httpx", "fastapi", "sqlalchemy", "psycopg", "redis", "boto3"}
    avant = set(sys.modules)
    importlib.import_module("pbm_game.checkup")
    nouveaux = set(sys.modules) - avant
    assert not (interdits & nouveaux), f"Dépendances interdites tirées : {interdits & nouveaux}"


def test_resoudre_checkup_ne_mute_pas_l_etat_d_entree():
    """Fonction pure : l'état figé passé en entrée n'est jamais modifié sur place."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({EMPOISONNE}), compteurs=10))
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = _etat(alice, bob)
    fiches = _fiche(alice.actif, pv=100)
    resoudre_checkup(etat, _rng(), fiches=fiches)
    # L'Actif d'alice n'a pas bougé dans l'état d'origine (dataclass figée).
    assert etat.joueurs[0].actif.compteurs_degats == 10
    assert EMPOISONNE in etat.joueurs[0].actif.etats_speciaux


# =========================================================================================
# Ordre de la phase (R-12.2) — poison, brûlure, réveil sur les DEUX joueurs
# =========================================================================================


def test_ordre_poison_brulure_reveil_sur_les_deux_joueurs_r122():
    """R-12.2 — états résolus dans l'ordre poison → brûlure → sommeil, joueur du tour d'abord.

    Critère d'acceptation : l'ordre est testé sur un cas qui combine poison, brûlure et réveil
    sur les deux joueurs. On contrôle l'ORDRE des événements (indépendant du pile ou face), et
    que les compteurs de poison/brûlure sont bien posés.
    """
    etats = frozenset({EMPOISONNE, BRULE, ENDORMI})
    alice = Joueur(id="alice", actif=_pk("alice", etats=etats, compteurs=0))
    bob = Joueur(id="bob", actif=_pk("bob", etats=etats, compteurs=0))
    etat = _etat(alice, bob, actif="bob")  # tour de bob qui s'achève → bob résolu en premier
    fiches = {**_fiche(alice.actif, pv=200), **_fiche(bob.actif, pv=200)}

    _, evenements = resoudre_checkup(etat, _rng(), fiches=fiches)
    etats_evts = [e for e in evenements if e.type == EVT_ETAT_CHECKUP]

    # Bob (dont le tour s'achève) d'abord, puis alice ; chacun poison → brûlure → sommeil.
    sequence = [(e.donnees["joueur"], e.donnees["etat"]) for e in etats_evts]
    assert sequence == [
        ("bob", EMPOISONNE), ("bob", BRULE), ("bob", ENDORMI),
        ("alice", EMPOISONNE), ("alice", BRULE), ("alice", ENDORMI),
    ]
    # Poison (R-11.7) = 1 compteur, brûlure (R-11.4) = 2 compteurs : 30 posés avant tout K.O.
    for e in etats_evts:
        if e.donnees["etat"] == EMPOISONNE:
            assert e.donnees["degats"] == POISON_DEGATS == 10
        if e.donnees["etat"] == BRULE:
            assert e.donnees["degats"] == BRULURE_DEGATS == 20


def test_chaque_etat_resolu_cite_une_regle_du_corpus():
    """Tout événement d'état au Checkup cite un ``R-x.y`` réellement défini dans REGLES.md."""
    definies = _regles_definies()
    etats = frozenset({EMPOISONNE, BRULE, ENDORMI, PARALYSE})
    alice = Joueur(id="alice", actif=_pk("alice", etats=etats))
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = _etat(alice, bob, actif="alice")
    _, evenements = resoudre_checkup(etat, _rng(), fiches=_fiche(alice.actif, pv=200))
    citees = {e.donnees["regle"] for e in evenements if e.type == EVT_ETAT_CHECKUP}
    assert citees, "aucun état résolu — le cas de test est vide"
    for regle in citees:
        assert MOTIF_REGLE.fullmatch(regle), f"« {regle} » n'est pas un identifiant R-x.y"
        assert regle in definies, f"« {regle} » citée mais absente du corpus"


# =========================================================================================
# Effets de chaque état au Checkup (R-11.3 / R-11.4 / R-11.6 / R-11.7)
# =========================================================================================


def test_empoisonne_pose_un_compteur_sans_pile_ou_face_r117():
    """R-11.7 — l'empoisonnement pose 1 compteur (10 dégâts) au Checkup, sans tirage."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({EMPOISONNE}), compteurs=20))
    bob = Joueur(id="bob", actif=_pk("bob"))
    rng = _rng()
    etat2, evenements = resoudre_checkup(_etat(alice, bob, actif="alice"), rng,
                                         fiches=_fiche(alice.actif, pv=100))
    assert etat2.joueurs[0].actif.compteurs_degats == 30
    assert EMPOISONNE in etat2.joueurs[0].actif.etats_speciaux  # le poison persiste (R-11.7)
    evt = next(e for e in evenements if e.donnees.get("etat") == EMPOISONNE)
    assert evt.donnees["gueri"] is False
    assert rng.journal() == ()  # aucun pile ou face : le poison n'en tire pas


def test_brulure_pose_deux_compteurs_et_son_pile_ou_face_est_journalise_r114():
    """R-11.4 — la brûlure pose 2 compteurs puis tire un pile ou face (face = guéri), journalisé."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({BRULE}), compteurs=0))
    bob = Joueur(id="bob", actif=_pk("bob"))
    rng = _rng()
    etat2, evenements = resoudre_checkup(_etat(alice, bob, actif="alice"), rng,
                                         fiches=_fiche(alice.actif, pv=100))
    assert etat2.joueurs[0].actif.compteurs_degats == 20  # 2 compteurs posés dans tous les cas
    evt = next(e for e in evenements if e.donnees.get("etat") == BRULE)
    # Le pile ou face est journalisé par le Rng, dans le flux dédié à la brûlure d'alice.
    tirages = [t for t in rng.journal() if t.flux == flux_checkup("brule", "alice")]
    assert len(tirages) == 1 and tirages[0].resultat in (FACE, PILE)
    # Cohérence : guéri ⇔ face ; marqueur retiré ssi guéri.
    assert evt.donnees["pile_ou_face"] == tirages[0].resultat
    assert evt.donnees["gueri"] == (tirages[0].resultat == FACE)
    assert (BRULE in etat2.joueurs[0].actif.etats_speciaux) == (not evt.donnees["gueri"])


def test_endormi_reveil_au_pile_ou_face_r113():
    """R-11.3 — au Checkup, pile ou face : face = réveil (guéri), pile = reste endormi."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({ENDORMI})))
    bob = Joueur(id="bob", actif=_pk("bob"))
    rng = _rng()
    etat2, evenements = resoudre_checkup(_etat(alice, bob, actif="alice"), rng,
                                         fiches=_fiche(alice.actif, pv=100))
    evt = next(e for e in evenements if e.donnees.get("etat") == ENDORMI)
    assert evt.donnees["degats"] == 0  # le sommeil ne pose aucun dégât
    assert evt.donnees["gueri"] == (evt.donnees["pile_ou_face"] == FACE)
    assert (ENDORMI in etat2.joueurs[0].actif.etats_speciaux) == (not evt.donnees["gueri"])


def test_paralysie_guerit_seulement_apres_le_tour_de_son_proprietaire_r116():
    """R-11.6 — la paralysie guérit au Checkup APRÈS le tour de son propriétaire, pas avant.

    Alice et bob sont tous deux paralysés ; c'est le tour de bob qui s'achève. La paralysie de
    bob guérit (c'est son Checkup), celle d'alice persiste (son tour n'est pas encore passé).
    """
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({PARALYSE})))
    bob = Joueur(id="bob", actif=_pk("bob", etats=frozenset({PARALYSE})))
    etat = _etat(alice, bob, actif="bob")
    fiches = {**_fiche(alice.actif, pv=100), **_fiche(bob.actif, pv=100)}
    etat2, evenements = resoudre_checkup(etat, _rng(), fiches=fiches)

    assert PARALYSE not in etat2.joueurs[1].actif.etats_speciaux  # bob guéri (son tour)
    assert PARALYSE in etat2.joueurs[0].actif.etats_speciaux  # alice reste paralysée
    gueri_par_joueur = {e.donnees["joueur"]: e.donnees["gueri"]
                        for e in evenements if e.donnees.get("etat") == PARALYSE}
    assert gueri_par_joueur == {"bob": True, "alice": False}


def test_sans_actif_aucun_etat_resolu_r112():
    """R-11.2 — un état spécial ne frappe que l'Actif ; sans Actif, rien à résoudre."""
    alice = Joueur(id="alice", actif=None)  # banc vide → pas d'Actif, état valide
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat2, evenements = resoudre_checkup(_etat(alice, bob, actif="bob"), _rng(), fiches={})
    assert not [e for e in evenements if e.type == EVT_ETAT_CHECKUP]
    assert not etat2.terminee


# =========================================================================================
# K.O. hors attaque (R-12.4) — récompenses (R-13) + promotion demandée (R-8.7)
# =========================================================================================


def test_un_empoisonne_meurt_entre_les_tours_ladversaire_prend_sa_recompense_et_promotion_r124():
    """R-12.4 — un Pokémon empoisonné meurt au Checkup ; l'adversaire prend sa récompense et la
    promotion est demandée au bon joueur (critère d'acceptation central du lot)."""
    alice_actif = _pk("alice", etats=frozenset({EMPOISONNE}), compteurs=90)
    alice = Joueur(id="alice", actif=alice_actif, banc=(_pk("alice", "banc0"),),
                   recompenses=tuple(Carte(f"a-rec-{i}", "r") for i in range(6)))
    bob = Joueur(id="bob", actif=_pk("bob"),
                 recompenses=tuple(Carte(f"b-rec-{i}", "r") for i in range(6)))
    etat = _etat(alice, bob, actif="bob")  # bob a joué, a empoisonné alice
    fiches = _fiche(alice_actif, pv=100, recompenses=1)

    etat2, evenements = resoudre_checkup(etat, _rng(), fiches=fiches)

    # Alice n'a plus d'Actif (K.O.), son Pokémon est à la défausse (R-13.2).
    assert etat2.joueurs[0].actif is None
    assert any(c.instance_id == "alice-actif" for c in etat2.joueurs[0].defausse)
    # Bob — l'adversaire — a pris 1 récompense (R-13.3) : 5 restantes, 1 en main.
    assert len(etat2.joueurs[1].recompenses) == 5
    assert len(etat2.joueurs[1].main) == 1
    # La promotion est demandée à alice (le bon joueur, R-8.7), pas à bob.
    requises = [e.donnees["joueur"] for e in evenements if e.type == EVT_PROMOTION_REQUISE]
    assert requises == ["alice"]
    ko = next(e for e in evenements if e.type == EVT_KO)
    assert ko.donnees["joueur"] == "alice" and ko.donnees["par"] == "bob"
    assert ko.donnees["recompenses_prises"] == 1
    assert not etat2.terminee


def test_ko_dun_pokemon_ex_donne_deux_recompenses_r133():
    """R-13.3 — le nombre de récompenses vient de la fiche (2 pour un Pokémon ex), pas d'une
    liste en dur."""
    alice_actif = _pk("alice", etats=frozenset({EMPOISONNE}), compteurs=90)
    alice = Joueur(id="alice", actif=alice_actif, banc=(_pk("alice", "banc0"),),
                   recompenses=())
    bob = Joueur(id="bob", actif=_pk("bob"),
                 recompenses=tuple(Carte(f"b-rec-{i}", "r") for i in range(6)))
    etat = _etat(alice, bob, actif="bob")
    etat2, evenements = resoudre_checkup(etat, _rng(),
                                         fiches=_fiche(alice_actif, pv=100, recompenses=2))
    assert len(etat2.joueurs[1].recompenses) == 4  # 6 − 2
    ko = next(e for e in evenements if e.type == EVT_KO)
    assert ko.donnees["recompenses_prises"] == 2


def test_ko_entre_les_tours_banc_vide_termine_la_partie_r89_r141():
    """R-8.9/R-14.1 — K.O. au Checkup avec banc vide = défaite, la bonne raison, l'adversaire
    gagne. Le code de victoire ne vit donc pas que dans la résolution d'attaque (risque du lot)."""
    alice_actif = _pk("alice", etats=frozenset({EMPOISONNE}), compteurs=90)
    alice = Joueur(id="alice", actif=alice_actif, banc=(),
                   recompenses=tuple(Carte(f"a-rec-{i}", "r") for i in range(6)))
    bob = Joueur(id="bob", actif=_pk("bob"),
                 recompenses=tuple(Carte(f"b-rec-{i}", "r") for i in range(6)))
    etat = _etat(alice, bob, actif="bob")
    etat2, evenements = resoudre_checkup(etat, _rng(), fiches=_fiche(alice_actif, pv=100))
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_PLUS_DE_POKEMON
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["perdant"] == "alice" and fin.donnees["vainqueur"] == "bob"
    # Aucune promotion n'est demandée : il n'y a plus de Pokémon à promouvoir.
    assert not [e for e in evenements if e.type == EVT_PROMOTION_REQUISE]
    assert_invariants(etat2)


def test_double_ko_des_deux_derniers_actifs_est_une_egalite_r144():
    """R-14.4 — les deux derniers Actifs K.O. au même Checkup, banc vide des deux côtés =
    égalité (vainqueur None, raison égalité). Le détail complet est au lot j-ko-recompenses."""
    a = _pk("alice", etats=frozenset({EMPOISONNE}), compteurs=90)
    b = _pk("bob", etats=frozenset({EMPOISONNE}), compteurs=90)
    alice = Joueur(id="alice", actif=a, banc=(), recompenses=(Carte("a-rec", "r"),))
    bob = Joueur(id="bob", actif=b, banc=(), recompenses=(Carte("b-rec", "r"),))
    etat = _etat(alice, bob, actif="bob")
    fiches = {**_fiche(a, pv=100), **_fiche(b, pv=100)}
    etat2, evenements = resoudre_checkup(etat, _rng(), fiches=fiches)
    assert etat2.terminee and etat2.vainqueur is None
    assert etat2.raison_fin == RAISON_EGALITE
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert set(fin.donnees["perdants"]) == {"alice", "bob"}


def test_promotion_apres_checkup_remplit_lactif_et_letat_redevient_sain():
    """Enchaînement réel : le Checkup vide l'Actif K.O., puis ``promouvoir`` le remplit et
    l'état repasse les invariants (R-3.3)."""
    from pbm_game.banc import promouvoir

    alice_actif = _pk("alice", etats=frozenset({EMPOISONNE}), compteurs=90)
    alice = Joueur(id="alice", actif=alice_actif, banc=(_pk("alice", "banc0"),),
                   recompenses=(Carte("a-rec", "r"),))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=(Carte("b-rec", "r"),))
    etat = _etat(alice, bob, actif="bob")
    etat2, _ = resoudre_checkup(etat, _rng(), fiches=_fiche(alice_actif, pv=100))
    assert etat2.joueurs[0].actif is None  # transitoire : promotion en attente
    etat3, _ = promouvoir(etat2, "alice", 0)
    assert etat3.joueurs[0].actif is not None and not etat3.joueurs[0].banc
    assert_invariants(etat3)


# =========================================================================================
# Expiration des effets temporaires (R-12.5) — journalisée, jamais en silence
# =========================================================================================


def test_aucun_effet_temporaire_au_jalon_j1_mais_la_fenetre_existe_r125():
    """R-12.5 — au jalon J1 aucun effet temporaire n'existe : la fenêtre d'expiration est câblée
    et franchie, mais ne produit rien (absence réelle, pas un repli silencieux)."""
    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    _, evenements = resoudre_checkup(_etat(alice, bob), _rng(), fiches={})
    assert not [e for e in evenements if e.type == EVT_EFFET_EXPIRE]


def test_expiration_dun_effet_temporaire_est_journalisee_r125():
    """R-12.5 — tout effet temporaire qui expire au Checkup émet une entrée de journal qui
    l'explique (sinon un effet « jusqu'à la fin du tour » devient éternel sans que rien ne le
    dise). On injecte un déclencheur d'expiration jouet, comme la fenêtre le permet pour les
    tests."""
    marque = {"expire": 0}

    def _expiration_jouet(etat: EtatPartie, rng: Rng) -> tuple[EtatPartie, list[Evenement]]:
        marque["expire"] += 1
        return etat, [Evenement(EVT_EFFET_EXPIRE,
                                {"effet": "degats_doubles_jusqua_fin_tour", "regle": "R-12.5"})]

    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    _, evenements = resoudre_checkup(
        _etat(alice, bob), _rng(), fiches={},
        declencheurs={FENETRE_EXPIRATION_EFFETS: (_expiration_jouet,)},
    )
    expires = [e for e in evenements if e.type == EVT_EFFET_EXPIRE]
    assert marque["expire"] == 1 and len(expires) == 1
    assert expires[0].donnees["regle"] == "R-12.5"


# =========================================================================================
# D9 — le moteur ne devine ni PV ni récompenses
# =========================================================================================


def test_fiche_manquante_pour_un_pokemon_endommage_echoue_bruyamment_d9():
    """D9/R-13.1 — un Pokémon endommagé sans fiche (PV inconnus) fait échouer le Checkup, jamais
    un repli silencieux."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=frozenset({EMPOISONNE}), compteurs=50))
    bob = Joueur(id="bob", actif=_pk("bob"))
    with pytest.raises(ValueError, match="Fiche de catalogue manquante"):
        resoudre_checkup(_etat(alice, bob, actif="bob"), _rng(), fiches={})


@pytest.mark.parametrize("fiche", [
    {"pv": 0, "recompenses": 1},
    {"pv": 100, "recompenses": 0},
    {"pv": 100},
    {"recompenses": 1},
    "pas-un-mapping",
])
def test_fiche_malformee_refusee_jamais_par_defaut_1_r134(fiche):
    """R-13.4 — une fiche malformée (PV ou marqueur absurde) est refusée, jamais « défaut 1 »."""
    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    fiches = {carte_active(alice.actif).instance_id: fiche}
    with pytest.raises(ValueError):
        resoudre_checkup(_etat(alice, bob), _rng(), fiches=fiches)


# =========================================================================================
# Intégration au journal : transition système, rejeu, sérialisation, gardes
# =========================================================================================


def test_checkup_passe_par_le_registre_et_est_rejouable():
    """La transition ``checkup`` s'applique via ``appliquer`` et le journal la rejoue à
    l'identique (empreinte contrôlée à chaque coup)."""
    alice_actif = _pk("alice", etats=frozenset({EMPOISONNE, BRULE}), compteurs=0)
    alice = Joueur(id="alice", actif=alice_actif,
                   recompenses=tuple(Carte(f"a-rec-{i}", "r") for i in range(6)))
    bob = Joueur(id="bob", actif=_pk("bob"),
                 recompenses=tuple(Carte(f"b-rec-{i}", "r") for i in range(6)))
    etat = _etat(alice, bob, actif="alice")
    fiches = _fiche(alice_actif, pv=100)
    action = Action(ACTION_CHECKUP, AUTEUR_SYSTEME, {"fiches": fiches})

    partie = partie_neuve(etat, GRAINE_HEX)
    partie, etat2 = jouer(partie, action, "2026-10-01T10:00:00Z", etat, _rng())
    # Rejouer le journal depuis l'état initial reproduit exactement le même état final.
    etat_rejoue, _ = rejouer(partie)
    assert etat_rejoue == etat2


def test_checkup_action_fiches_survivent_a_la_serialisation():
    """Les ``fiches`` (mapping imbriqué) traversent la sérialisation d'action sans perte."""
    fiches = {"p-1": {"pv": 100, "recompenses": 2}}
    action = Action(ACTION_CHECKUP, AUTEUR_SYSTEME, {"fiches": fiches})
    assert action_depuis_json(action_vers_json(action)) == action


def test_checkup_refuse_hors_phase_checkup_r121():
    """R-12.1 — le Pokémon Checkup ne se résout qu'en phase checkup."""
    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    tour = Tour(joueur_actif="bob", numero=5, phase=PHASE_PRINCIPALE)
    etat = EtatPartie(joueurs=(alice, bob), tour=tour)
    with pytest.raises(ValueError, match="R-12.1"):
        appliquer(etat, Action(ACTION_CHECKUP, AUTEUR_SYSTEME, {"fiches": {}}), _rng())


def test_checkup_refuse_sur_partie_terminee_r146():
    """R-14.6 — une partie terminée refuse toute action supplémentaire, le Checkup compris."""
    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("bob", 5, PHASE_CHECKUP),
                      terminee=True, vainqueur="bob", raison_fin=RAISON_PLUS_DE_POKEMON)
    with pytest.raises(ValueError, match="R-14.6"):
        resoudre_checkup(etat, _rng(), fiches={})


def test_checkup_n_est_pas_un_coup_liste_du_joueur():
    """Le Checkup est une action **système** (R-12.1), jamais un coup proposé à un joueur."""
    alice = Joueur(id="alice", actif=_pk("alice"))
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = _etat(alice, bob, actif="alice")
    for joueur in ("alice", "bob"):
        types = {al.action.type for al in actions_legales(etat, joueur)}
        assert ACTION_CHECKUP not in types
