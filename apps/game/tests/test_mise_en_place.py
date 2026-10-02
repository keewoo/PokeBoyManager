"""Tests de la **mise en place** (R-4) — lot ``j-initialisation``.

Ce fichier FAIT FOI sur les critères d'acceptation de la mission :

1. **le placement face caché ne laisse rien fuir** avant la révélation (test dédié de non-fuite) ;
2. **le comptage des cartes bonus après mulligans est exact et journalisé** (R-4.5/R-16.9) ;
3. **la révélation est simultanée** même quand un joueur valide bien avant l'autre.

S'y ajoutent les trois scénarios demandés — **trois mulligans de suite**, **mulligan des deux
joueurs** (R-4.6), **main sans base cinq fois d'affilée** —, les six récompenses face cachée
(R-3.4/R-4.3), la garde « rien d'autre que placer/abandonner pendant la mise en place », la
sérialisation round-trip et la **rejouabilité** (même graine ⇒ même état). Chaque test de règle
nomme le ``R-x.y`` qu'il vérifie, et ce nom **existe** dans ``docs/jeu/REGLES.md``.

La suite échoue naturellement sans le paquet ``pbm_game.mise_en_place`` (import en tête) : c'est le
« test qui échoue sans le changement et passe avec ».

Les shuffles sont pilotés par un :class:`FauxRng` scripté — il implémente le seul contrat que les
transitions utilisent (``melanger(flux, motif, sequence)``) — pour contrôler **exactement** combien
de mulligans chaque joueur prend, sans chercher une graine au hasard. Un test de bout en bout avec
le **vrai** :class:`~pbm_game.rng.Rng` prouve en plus le déterminisme réel et la rejouabilité.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pbm_game.journal import (
    ACTION_ABANDONNER,
    ACTION_DEBUT_TOUR,
    ACTION_PIOCHER,
    AUTEUR_SYSTEME,
    Action,
    appliquer,
)
from pbm_game.journal.modele import (
    ACTION_MISE_EN_PLACE_INITIALE,
    ACTION_PLACER_MISE_EN_PLACE,
    EVT_MAIN_REVELEE,
    EVT_MISE_EN_PLACE_REVELEE,
    EVT_MULLIGAN,
)
from pbm_game.mise_en_place import RECOMPENSES
from pbm_game.regles import identifiants_definis
from pbm_game.rng import Rng, flux_melange_deck
from pbm_game.state import (
    Carte,
    EtatPartie,
    Joueur,
    Tour,
    assert_invariants,
    depuis_json,
    vers_json,
    vue,
)
from pbm_game.state.modele import PHASE_PIOCHE

CHEMIN_REGLES = Path(__file__).resolve().parents[3] / "docs" / "jeu" / "REGLES.md"


def _regles_connues() -> set[str]:
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


# --- Fiches catalogue minimales (fournies par le service en vrai, D9) --------

_BASE_DEF = {
    "ref": "base",
    "nom": "Basique",
    "stade": "base",
    "pv": 60,
    "type": "incolore",
    "marqueur": "ordinaire",
    "cout_retraite": 1,
    "attaques": [],
}
_EVO_DEF = {
    "ref": "evo",
    "nom": "Évoluée",
    "stade": "stade1",
    "pv": 90,
    "type": "incolore",
    "marqueur": "ordinaire",
    "evolue_depuis": "Basique",
    "cout_retraite": 1,
    "attaques": [],
}
_DEFS = {"base": _BASE_DEF, "evo": _EVO_DEF}


def _deck(jid: str, nb_base: int = 4, nb_evo: int = 56) -> list[Carte]:
    """Un deck de 60 : quelques bases (ref ``base``), le reste en évolutions (ref ``evo``)."""
    base = [Carte(instance_id=f"{jid}-base-{i}", ref="base") for i in range(nb_base)]
    evo = [Carte(instance_id=f"{jid}-evo-{i}", ref="evo") for i in range(nb_evo)]
    return base + evo


def _etat_initial(jid_a: str = "a", jid_b: str = "b") -> EtatPartie:
    """État minimal d'avant mise en place : chaque joueur a son deck en pioche (cf. service)."""
    return EtatPartie(
        joueurs=(
            Joueur(id=jid_a, pioche=tuple(_deck(jid_a))),
            Joueur(id=jid_b, pioche=tuple(_deck(jid_b))),
        ),
        tour=Tour(joueur_actif=jid_a, numero=1, phase=PHASE_PIOCHE),
    )


def _main_sans_base(jid: str) -> list[str]:
    """Sept instance_id d'évolutions : une main d'ouverture SANS base (déclenche R-4.4)."""
    return [f"{jid}-evo-{i}" for i in range(7)]


def _bonne_main(jid: str) -> list[str]:
    """Sept instance_id dont une base : une main d'ouverture valide (une base au sommet)."""
    return [f"{jid}-base-0", *[f"{jid}-evo-{i}" for i in range(6)]]


def _main_multi_base(jid: str) -> list[str]:
    """Sept instance_id dont trois bases : de quoi poser un Actif ET garnir le banc (R-4.2)."""
    return [f"{jid}-base-0", f"{jid}-base-1", f"{jid}-base-2",
            *[f"{jid}-evo-{i}" for i in range(4)]]


class FauxRng:
    """Un Rng **scripté** pour les tests : il place des cartes précises au sommet à chaque mélange.

    Il n'implémente que ``melanger(flux, motif, sequence)`` — le seul point du vrai
    :class:`~pbm_game.rng.Rng` que les transitions de mise en place utilisent. Pour chaque flux
    (un par joueur), ``scripts`` donne, mélange après mélange, la liste des ``instance_id`` à mettre
    **en tête** (donc dans la main de sept) ; le reste suit dans l'ordre d'origine. Quand un flux
    n'a plus de script, le mélange est l'identité. On enregistre chaque appel (flux, motif) pour
    vérifier que l'aléatoire a bien été sollicité au bon flux.
    """

    def __init__(self, scripts: dict[str, list[list[str]]]) -> None:
        self._scripts = {flux: list(etapes) for flux, etapes in scripts.items()}
        self.appels: list[tuple[str, str]] = []

    def melanger(self, flux: str, motif: str, sequence) -> list:
        seq = list(sequence)
        self.appels.append((flux, motif))
        etapes = self._scripts.get(flux)
        if not etapes:
            return seq
        tete_ids = etapes.pop(0)
        par_id = {c.instance_id: c for c in seq}
        manquant = [i for i in tete_ids if i not in par_id]
        if manquant:
            raise AssertionError(f"Script FauxRng : instance_id absents de la zone : {manquant}")
        tete = [par_id[i] for i in tete_ids]
        en_tete = set(tete_ids)
        reste = [c for c in seq if c.instance_id not in en_tete]
        return tete + reste


def _initialiser(scripts: dict[str, list[list[str]]], etat: EtatPartie | None = None):
    """Applique la mise en place système avec un :class:`FauxRng` scripté ; renvoie (etat, evts)."""
    etat = etat or _etat_initial()
    rng = FauxRng(scripts)
    action = Action(ACTION_MISE_EN_PLACE_INITIALE, AUTEUR_SYSTEME, {"definitions": _DEFS})
    etat2, evts = appliquer(etat, action, rng)
    return etat2, evts, rng


def _placer(etat: EtatPartie, jid: str, actif: str, banc: list[str] | None = None):
    action = Action(
        ACTION_PLACER_MISE_EN_PLACE,
        jid,
        {"actif": actif, "banc": banc or [], "definitions": _DEFS},
    )
    return appliquer(etat, action, FauxRng({}))


# --- Les R-x.y cités existent -------------------------------------------------


def test_regles_citees_existent():
    """Garde : chaque R-x.y nommé ici est défini dans REGLES.md (pas de citation morte)."""
    connues = _regles_connues()
    for regle in ("R-4.1", "R-4.2", "R-4.3", "R-4.4", "R-4.5", "R-4.6", "R-3.2", "R-3.4", "R-16.9"):
        assert regle in connues, f"{regle} n'existe pas dans REGLES.md"


# --- Pureté -------------------------------------------------------------------


def test_import_mise_en_place_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.mise_en_place`` ne charge aucune dépendance interdite (moteur pur)."""
    interdits = {"fastapi", "sqlalchemy", "asyncpg", "redis", "boto3", "httpx", "pbm_api"}
    importlib.import_module("pbm_game.mise_en_place")
    charges = interdits & set(sys.modules)
    assert not charges, f"L'import a tiré des dépendances interdites : {sorted(charges)}"


# --- Mélange et pioche de sept (R-4.1) ---------------------------------------


def test_melange_et_pioche_de_sept_sans_mulligan():
    """R-4.1 : chaque joueur mélange et pioche sept ; main valide = aucun mulligan."""
    etat, _evts, rng = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    assert etat.mise_en_place is not None
    assert etat.mise_en_place.mulligans == (0, 0)
    for j in etat.joueurs:
        assert len(j.main) == 7
        assert len(j.pioche) == 53  # 60 - 7, les récompenses ne sont pas encore posées
    # L'aléatoire a bien été sollicité, une fois par joueur (le mélange d'ouverture).
    assert (flux_melange_deck("a"), ) != ()  # flux nommé
    assert len([a for a in rng.appels if a[0] == flux_melange_deck("a")]) == 1


# --- Boucle de mulligan (R-4.4 / R-4.5 / R-4.6) ------------------------------


def test_trois_mulligans_de_suite():
    """R-4.4/R-4.5 : A sans base trois fois de suite → 3 mulligans, 3 cartes bonus dues à B."""
    etat, evts, _ = _initialiser({
        flux_melange_deck("a"): [
            _main_sans_base("a"),  # main d'ouverture sans base → mulligan
            _main_sans_base("a"),  # encore
            _main_sans_base("a"),  # encore
            _bonne_main("a"),      # enfin une base
        ],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    mep = etat.mise_en_place
    assert mep.mulligans == (3, 0)  # A a pris 3 mulligans, B aucun
    assert mep.bonus == (0, 3)      # B a droit à 3 cartes bonus (R-4.5)
    mulligans = [e for e in evts if e.type == EVT_MULLIGAN]
    assert len(mulligans) == 3
    assert all(e.donnees["bonus_pour"] == "b" for e in mulligans)
    assert all(e.donnees["simultane"] is False for e in mulligans)
    assert [e.donnees["numero"] for e in mulligans] == [1, 2, 3]


def test_mulligan_des_deux_joueurs_sans_carte_bonus():
    """R-4.6 : les deux sans base au même tour → les deux remélangent, SANS carte bonus."""
    etat, evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_sans_base("a"), _bonne_main("a")],
        flux_melange_deck("b"): [_main_sans_base("b"), _bonne_main("b")],
    })
    mep = etat.mise_en_place
    assert mep.mulligans == (1, 1)
    assert mep.bonus == (0, 0)  # double mulligan simultané : aucune carte bonus (R-4.6)
    mulligans = [e for e in evts if e.type == EVT_MULLIGAN]
    assert len(mulligans) == 2
    assert all(e.donnees["simultane"] is True for e in mulligans)
    assert all("bonus_pour" not in e.donnees for e in mulligans)


def test_main_sans_base_cinq_fois_daffilee():
    """R-4.4 : A sans base cinq fois d'affilée → 5 mulligans, 5 bonus dus à B, puis valide."""
    etat, evts, _ = _initialiser({
        flux_melange_deck("a"): [*([_main_sans_base("a")] * 5), _bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    mep = etat.mise_en_place
    assert mep.mulligans == (5, 0)
    assert mep.bonus == (0, 5)
    assert len([e for e in evts if e.type == EVT_MULLIGAN]) == 5
    # À la fin, la main de A a bien un Pokémon de base (la boucle ne s'arrête pas avant, R-4.4).
    assert any(c.ref == "base" for c in etat.joueurs[0].main)


def test_main_revelee_est_journalisee_avec_son_contenu():
    """R-4.4 : une main d'ouverture sans base est révélée, et le journal garde son contenu."""
    etat, evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_sans_base("a"), _bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    revelees = [e for e in evts if e.type == EVT_MAIN_REVELEE]
    assert len(revelees) == 1
    contenu = revelees[0].donnees
    assert contenu["joueur"] == "a"
    ids = {c["instance_id"] for c in contenu["cartes"]}
    assert ids == set(_main_sans_base("a"))  # la main révélée, carte par carte


def test_comptage_bonus_exact_quand_les_deux_prennent_des_mulligans():
    """R-4.5/R-16.9 : on ne gagne de bonus que pour les mulligans que l'autre prend SEUL."""
    # Tour 1 : les deux sans base (simultané, aucun bonus). Tour 2 : seul A sans base (bonus à B).
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_sans_base("a"), _main_sans_base("a"), _bonne_main("a")],
        flux_melange_deck("b"): [_main_sans_base("b"), _bonne_main("b")],
    })
    mep = etat.mise_en_place
    assert mep.mulligans == (2, 1)  # A : 2 (un simultané + un seul), B : 1 (le simultané)
    assert mep.bonus == (0, 1)      # seul le mulligan que A prend SEUL donne une carte bonus à B


# --- Placement face caché + non-fuite (R-4.2) --------------------------------


def test_placement_face_cachee_ne_fuit_pas_avant_revelation():
    """R-4.2 : A placé, pas B → la vue de B n'apprend RIEN du placement de A (non-fuite)."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_multi_base("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    etat, _ = _placer(etat, "a", actif="a-base-0", banc=["a-base-1", "a-base-2"])
    # A a placé, B pas encore : on est toujours en mise en place.
    assert etat.mise_en_place is not None
    # L'Actif/banc publics de A restent VIDES (le placement vit caché, hors des zones publiques).
    assert etat.joueurs[0].actif is None
    assert etat.joueurs[0].banc == ()

    vue_de_b = vue(etat, "b")
    # Aucun instance_id du placement de A ne survit dans ce que B a le droit de voir.
    texte = repr(vue_de_b)
    for cache in ("a-base-0", "a-base-1", "a-base-2"):
        assert cache not in texte, f"fuite : « {cache} » visible de l'adversaire"
    # B voit SEULEMENT que A est prêt, jamais quoi.
    vu_a = next(j for j in vue_de_b["mise_en_place"]["joueurs"] if j["id"] == "a")
    assert vu_a["a_place"] is True
    assert "placement" not in vu_a
    # A, lui, revoit son propre placement (utile à la reprise après un F5).
    vu_a_pour_a = next(j for j in vue(etat, "a")["mise_en_place"]["joueurs"] if j["id"] == "a")
    assert vu_a_pour_a["placement"]["actif"] == "a-base-0"


# --- Révélation simultanée (R-4.2 / R-4.3) -----------------------------------


def test_revelation_est_simultanee_meme_si_un_joueur_valide_bien_avant():
    """R-4.2/R-4.3 : A valide d'abord, mais rien ne lui est révélé de B avant que B valide aussi."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    etat, evts_a = _placer(etat, "a", actif="a-base-0")
    # Avant que B place : A ne voit RIEN de l'Actif de B (toujours vide, toujours en mise en place).
    assert etat.mise_en_place is not None
    assert etat.joueurs[1].actif is None
    vue_de_a = vue(etat, "a")
    assert "b-base-0" not in repr(vue_de_a)
    assert all(e.type != EVT_MISE_EN_PLACE_REVELEE for e in evts_a)

    # B place : la révélation tombe MAINTENANT, pour les deux à la fois, en un seul événement.
    etat, evts_b = _placer(etat, "b", actif="b-base-0")
    assert etat.mise_en_place is None  # la partie a commencé
    reveles = [e for e in evts_b if e.type == EVT_MISE_EN_PLACE_REVELEE]
    assert len(reveles) == 1
    joueurs_reveles = {j["joueur"] for j in reveles[0].donnees["joueurs"]}
    assert joueurs_reveles == {"a", "b"}  # un seul événement porte les DEUX côtés
    # Les Actifs sont désormais publics, des deux côtés.
    assert etat.joueurs[0].actif is not None
    assert etat.joueurs[1].actif is not None
    assert_invariants(etat)


def test_six_recompenses_face_cachee_a_la_revelation():
    """R-3.4/R-4.3 : à la révélation, chaque joueur a exactement 6 récompenses, face cachée."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    etat, _ = _placer(etat, "a", actif="a-base-0")
    etat, _ = _placer(etat, "b", actif="b-base-0")
    for j in etat.joueurs:
        assert len(j.recompenses) == RECOMPENSES == 6
    # Face cachée : la vue n'expose qu'un nombre, jamais les cartes.
    v = vue(etat, "a")
    assert v["joueurs"][0]["recompenses_nombre"] == 6
    assert "recompenses" not in v["joueurs"][0]


def test_cartes_bonus_piochees_a_la_revelation():
    """R-4.5 : les bonus dus à B (mulligans de A) sont piochés à la révélation, pas avant."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_sans_base("a"), _main_sans_base("a"), _bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    assert etat.mise_en_place.bonus == (0, 2)
    main_b_avant = len(etat.joueurs[1].main)  # 7, bonus pas encore pioché
    assert main_b_avant == 7
    etat, _ = _placer(etat, "a", actif="a-base-0")
    etat, evts = _placer(etat, "b", actif="b-base-0")
    reveles = [e for e in evts if e.type == EVT_MISE_EN_PLACE_REVELEE][0]
    resume_b = next(j for j in reveles.donnees["joueurs"] if j["joueur"] == "b")
    assert resume_b["bonus_pioches"] == 2
    # Main de B après révélation : 7 - 1 (Actif posé) + 2 (bonus) = 8.
    assert len(etat.joueurs[1].main) == 7 - 1 + 2


# --- Placement : gardes de légalité (R-4.2 / R-3.2) --------------------------


def test_actif_doit_etre_un_pokemon_de_base():
    """R-4.2 : poser une évolution comme Actif est refusé — seul un Pokémon de base s'y pose."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    with pytest.raises(ValueError, match="base"):
        _placer(etat, "a", actif="a-evo-0")


def test_banc_au_plus_cinq():
    """R-3.2/R-4.2 : poser plus de cinq Pokémon au banc à la mise en place est refusé."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [["a-base-0", *[f"a-base-{i}" for i in range(1, 4)],
                                  "a-evo-0", "a-evo-1", "a-evo-2"]],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    # Six cartes au banc : refusé (R-3.2) avant même de regarder leur stade.
    with pytest.raises(ValueError, match="R-3.2|R-4.2"):
        _placer(etat, "a", actif="a-base-0",
                banc=["a-evo-0", "a-evo-1", "a-evo-2", "a-base-1", "a-base-2", "a-base-3"])


def test_carte_hors_de_la_main_refusee():
    """R-4.2 : on ne place que ses propres cartes — un instance_id absent de la main est refusé."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    with pytest.raises(ValueError, match="absente de la main"):
        _placer(etat, "a", actif="a-base-3")  # pas dans la main (hors du top-7 scripté)


# --- Garde centrale pendant la mise en place (R-4) ---------------------------


def test_pendant_la_mise_en_place_seuls_placer_et_abandonner_sont_permis():
    """R-4 : pendant la mise en place, piocher/commencer un tour est refusé ; abandon OK."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_bonne_main("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    with pytest.raises(ValueError, match="[Mm]ise en place"):
        appliquer(etat, Action(ACTION_PIOCHER, "a", {"nombre": 1}), FauxRng({}))
    with pytest.raises(ValueError, match="[Mm]ise en place"):
        appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME, {"joueur": "a"}), FauxRng({}))
    # L'abandon reste permis à tout moment (R-14.3).
    etat_ab, _ = appliquer(etat, Action(ACTION_ABANDONNER, "a", {}), FauxRng({}))
    assert etat_ab.terminee is True


def test_deck_sans_aucune_base_refuse_plutot_que_boucler():
    """R-2/R-4.4 : un deck sans aucun Pokémon de base ne peut pas aboutir — refus, jamais boucle."""
    etat = EtatPartie(
        joueurs=(
            Joueur(id="a", pioche=tuple(_deck("a", nb_base=0, nb_evo=60))),
            Joueur(id="b", pioche=tuple(_deck("b"))),
        ),
        tour=Tour(joueur_actif="a", numero=1, phase=PHASE_PIOCHE),
    )
    with pytest.raises(ValueError, match="sans aucun Pokémon de base"):
        _initialiser(
            {flux_melange_deck("a"): [_main_sans_base("a")],
             flux_melange_deck("b"): [_bonne_main("b")]},
            etat=etat,
        )


# --- Sérialisation et rejouabilité -------------------------------------------


def test_etat_en_mise_en_place_fait_un_aller_retour_json_exact():
    """Round-trip : un état en pleine mise en place (placement partiel) se sérialise et se relit."""
    etat, _evts, _ = _initialiser({
        flux_melange_deck("a"): [_main_sans_base("a"), _main_multi_base("a")],
        flux_melange_deck("b"): [_bonne_main("b")],
    })
    etat, _ = _placer(etat, "a", actif="a-base-0", banc=["a-base-1"])
    relu = depuis_json(vers_json(etat))
    assert relu == etat
    assert relu.mise_en_place.mulligans == (1, 0)
    assert relu.mise_en_place.placements[0].actif == "a-base-0"
    assert relu.mise_en_place.placements[1] is None


def test_rejouabilite_avec_le_vrai_rng():
    """Déterminisme réel : le vrai Rng, deux fois sur la même graine, donne le même état (rejeu)."""
    def jouer_mise_en_place():
        etat = _etat_initial()
        rng = Rng(b"mise-en-place-seed-rejouable")
        action = Action(ACTION_MISE_EN_PLACE_INITIALE, AUTEUR_SYSTEME, {"definitions": _DEFS})
        etat, _ = appliquer(etat, action, rng)
        return etat

    etat1 = jouer_mise_en_place()
    etat2 = jouer_mise_en_place()
    # Même graine ⇒ mêmes mélanges ⇒ mêmes mains, mêmes mulligans : états égaux au bit près.
    assert vers_json(etat1) == vers_json(etat2)
    # Et c'est une mise en place valide : deux mains non vides, chacune avec au moins une base.
    for j in etat1.joueurs:
        assert len(j.main) == 7
        assert any(c.ref == "base" for c in j.main)
