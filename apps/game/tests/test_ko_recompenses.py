"""Tests des **mises K.O., récompenses et conditions de victoire** (lot ``j-ko-recompenses``).

Le moteur est **pur** : chaque test construit un état, appelle le résolveur partagé
:func:`pbm_game.combat.resoudre_kos` (ou la phase Checkup qui l'appelle) et contrôle le résultat ;
aucune base, aucun réseau. Chaque test de règle **cite son identifiant** ``R-x.y`` dans son nom et
son docstring, et un test vérifie que toutes les règles citées existent dans ``docs/jeu/REGLES.md``.

**Le test qui échoue sans le changement et passe avec** :
:func:`test_victoire_en_prenant_sa_derniere_recompense_r141` — avant ce lot, prendre sa dernière
récompense au Checkup ne terminait PAS la partie (seul le banc vide le faisait). Il échoue donc sur
la base et passe avec ce lot ; l'import de :mod:`pbm_game.combat.fin` en tête en est l'autre preuve.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pbm_game.checkup import resoudre_checkup
from pbm_game.combat import (
    MARQUEUR_RECOMPENSES,
    VOIE_ADVERSAIRE_SANS_POKEMON,
    VOIE_DERNIERE_RECOMPENSE,
    recompenses_pour_marqueur,
    resoudre_kos,
    terminer,
    valider_fiches,
)
from pbm_game.journal import (
    ACTION_ABANDONNER,
    ACTION_DEBUT_TOUR,
    AUTEUR_SYSTEME,
    EVT_KO,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION_REQUISE,
    RAISON_ABANDON,
    RAISON_DERNIERE_RECOMPENSE,
    RAISON_PIOCHE_IMPOSSIBLE,
    RAISON_PLUS_DE_POKEMON,
    Action,
    appliquer,
)
from pbm_game.regles import identifiants_definis
from pbm_game.rng import Rng
from pbm_game.state import (
    PHASE_CHECKUP,
    PHASE_PIOCHE,
    RAISON_EGALITE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
)

RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"
GRAINE_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def _rng() -> Rng:
    return Rng(bytes.fromhex(GRAINE_HEX))


# --- Fabriques déterministes -------------------------------------------------


def _pk(jid: str, tag: str = "actif", *, compteurs: int = 0) -> PokemonEnJeu:
    return PokemonEnJeu(cartes=(Carte(f"{jid}-{tag}", "ref-pk"),), compteurs_degats=compteurs)


def _recompenses(jid: str, n: int) -> tuple[Carte, ...]:
    return tuple(Carte(f"{jid}-rec-{i}", "r") for i in range(n))


def _etat_checkup(alice: Joueur, bob: Joueur, *, actif: str = "bob") -> EtatPartie:
    """État en phase Checkup ; ``actif`` est le joueur dont le tour s'achève (R-12.4)."""
    return EtatPartie(joueurs=(alice, bob), tour=Tour(actif, 5, PHASE_CHECKUP))


def _fiche(pokemon: PokemonEnJeu, *, pv: int, recompenses: int = 1) -> dict:
    return {pokemon.cartes[-1].instance_id: {"pv": pv, "recompenses": recompenses}}


def _ordre(etat: EtatPartie, premier: str) -> tuple[str, str]:
    autre = next(j.id for j in etat.joueurs if j.id != premier)
    return (premier, autre)


# =========================================================================================
# Pureté / API
# =========================================================================================


def test_import_fin_ne_tire_aucune_dependance_lourde():
    """Le moteur est pur : importer ``pbm_game.combat.fin`` ne charge ni HTTP, ni base, ni React."""
    interdits = {"requests", "httpx", "fastapi", "sqlalchemy", "psycopg", "redis", "boto3"}
    avant = set(sys.modules)
    importlib.import_module("pbm_game.combat.fin")
    nouveaux = set(sys.modules) - avant
    assert not (interdits & nouveaux), f"Dépendances interdites tirées : {interdits & nouveaux}"


def test_resoudre_kos_ne_mute_pas_l_etat_d_entree():
    """Fonction pure : l'état figé passé en entrée n'est jamais modifié sur place."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = _etat_checkup(alice, bob, actif="bob")
    resoudre_kos(etat, _fiche(alice.actif, pv=100), _ordre(etat, "bob"))
    assert etat.joueurs[0].actif is not None and etat.joueurs[0].actif.compteurs_degats == 100


# =========================================================================================
# Marqueur de règle → nombre de récompenses (R-13.3 / R-13.4 / R-13.7)
# =========================================================================================


@pytest.mark.parametrize(
    "marqueur, attendu",
    [
        ("ordinaire", 1),
        ("radiant", 1),  # R-15.9
        ("ex", 2),  # R-15.1
        ("v", 2),  # R-15.4
        ("gx", 2),  # R-15.3
        ("vmax", 3),  # R-15.5
        ("tag_team", 3),  # R-15.7 — finit par « GX » mais donne 3 (R-13.7)
        ("mega_ex", 3),  # R-15.13 — finit par « ex » mais donne 3 (R-13.7)
    ],
)
def test_recompenses_pour_marqueur_suit_le_corpus_r133(marqueur: str, attendu: int):
    """R-13.3 — le nombre de récompenses se lit sur le **marqueur de règle**, 1/2/3 selon R-15."""
    assert recompenses_pour_marqueur(marqueur) == attendu


def test_marqueur_inconnu_echoue_bruyamment_jamais_defaut_1_r134():
    """R-13.4/R-15.22 — un marqueur inconnu fait échouer bruyamment, jamais « par défaut 1 »."""
    with pytest.raises(ValueError, match="inconnu"):
        recompenses_pour_marqueur("super_duper_ex")


@pytest.mark.parametrize("marqueur", [None, "", 2, b"ex"])
def test_marqueur_non_chaine_refuse_r133(marqueur):
    """R-13.3 — un marqueur qui n'est pas une chaîne non vide est refusé (jamais deviné)."""
    with pytest.raises(ValueError):
        recompenses_pour_marqueur(marqueur)


def test_le_nombre_de_recompenses_vient_du_marqueur_de_la_fiche_r133_r137():
    """R-13.3/R-13.7 — le K.O. d'un TAG TEAM (marqueur) fait prendre **3** récompenses, pas 1 :
    le marqueur (sous-type / Rule Box) fait foi, jamais le suffixe du nom."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=200), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = _etat_checkup(alice, bob, actif="bob")
    fiches = {alice.actif.cartes[-1].instance_id: {"pv": 100, "marqueur": "tag_team"}}
    etat2, evenements = resoudre_kos(etat, fiches, _ordre(etat, "bob"))
    assert len(etat2.joueurs[1].recompenses) == 3  # 6 − 3 (R-13.7)
    ko = next(e for e in evenements if e.type == EVT_KO)
    assert ko.donnees["recompenses_prises"] == 3


def test_fiche_marqueur_inconnu_refusee_des_la_validation_r134():
    """R-13.4 — une fiche au marqueur inconnu est refusée **eager**, jamais repliée à 1."""
    with pytest.raises(ValueError, match="inconnu"):
        valider_fiches({"p-1": {"pv": 100, "marqueur": "carte_magique"}})


def test_table_marqueurs_ne_contient_que_1_2_3():
    """Garde-fou : la table close ne fixe que des récompenses 1, 2 ou 3 (R-13.3)."""
    assert set(MARQUEUR_RECOMPENSES.values()) == {1, 2, 3}


# =========================================================================================
# Condition de victoire 1 — prendre sa dernière récompense (R-14.1 cas 1)
# =========================================================================================


def test_victoire_en_prenant_sa_derniere_recompense_r141():
    """R-14.1 cas 1 — prendre sa **dernière** récompense après un K.O. gagne la partie.

    Bob n'a plus qu'une récompense ; le K.O. de l'Actif d'alice (qui garde du banc, donc n'est pas
    éliminée) la lui fait prendre : sa réserve passe à zéro → bob gagne, raison « dernière
    récompense ». AVANT ce lot, ce K.O. ne terminait pas la partie : c'est le test qui échoue sans
    le changement et passe avec."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 1))
    etat = _etat_checkup(alice, bob, actif="bob")
    etat2, evenements = resoudre_kos(etat, _fiche(alice.actif, pv=100), _ordre(etat, "bob"))

    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_DERNIERE_RECOMPENSE
    assert not etat2.joueurs[1].recompenses  # réserve vidée
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["perdant"] == "alice"
    assert VOIE_DERNIERE_RECOMPENSE in fin.donnees["voies"]
    # Aucune promotion n'est demandée : la partie est finie (R-14.6).
    assert not [e for e in evenements if e.type == EVT_PROMOTION_REQUISE]
    assert_invariants(etat2)


def test_une_reserve_deja_vide_ne_fait_pas_gagner_il_faut_PRENDRE_la_derniere_r141():
    """R-14.1 cas 1 — on gagne en **prenant** sa dernière récompense, pas en ayant une réserve
    vide par ailleurs. Bob a 0 récompense mais ne prend rien ici (l'Actif d'alice n'est pas
    K.O.) : la partie continue, personne ne gagne par les récompenses."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=())  # réserve déjà vide
    # Seul l'Actif d'alice est K.O. → c'est BOB qui prendrait, mais sa réserve est déjà à 0 :
    # il ne « prend » rien (prises = 0), donc pas de victoire par récompenses pour bob.
    etat = _etat_checkup(alice, bob, actif="bob")
    etat2, evenements = resoudre_kos(etat, _fiche(alice.actif, pv=100), _ordre(etat, "bob"))
    assert not etat2.terminee
    requises = [e.donnees["joueur"] for e in evenements if e.type == EVT_PROMOTION_REQUISE]
    assert requises == ["alice"]


# =========================================================================================
# Condition de victoire 2 — adversaire sans Pokémon à promouvoir (R-14.1 cas 2, R-8.9)
# =========================================================================================


def test_dernier_pokemon_ko_banc_vide_est_une_defaite_r141_r89():
    """R-14.1 cas 2 / R-8.9 — le dernier Pokémon K.O. (banc vide) : l'adversaire gagne, raison
    « plus de Pokémon »."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = _etat_checkup(alice, bob, actif="bob")
    etat2, evenements = resoudre_kos(etat, _fiche(alice.actif, pv=100), _ordre(etat, "bob"))
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_PLUS_DE_POKEMON
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["perdant"] == "alice"
    assert VOIE_ADVERSAIRE_SANS_POKEMON in fin.donnees["voies"]
    assert_invariants(etat2)


# =========================================================================================
# Condition de victoire 3 — adversaire incapable de piocher (R-14.1 cas 3, R-14.2)
# =========================================================================================


def test_victoire_quand_l_adversaire_ne_peut_plus_piocher_r141_r142():
    """R-14.1 cas 3 / R-14.2 — pioche impossible en début de tour = défaite du joueur actif.

    Cette troisième condition ne découle pas d'un K.O. : elle se vérifie à l'ouverture du tour
    (action système ``debut_tour``). On la couvre ici pour que les **trois** façons de gagner
    soient testées ensemble."""
    alice = Joueur(id="alice", actif=_pk("alice"), pioche=(), recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 5, PHASE_PIOCHE))
    etat2, evenements = appliquer(etat, Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME), _rng())
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_PIOCHE_IMPOSSIBLE
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["perdant"] == "alice"


# =========================================================================================
# Abandon (R-14.3)
# =========================================================================================


def test_abandon_fait_perdre_immediatement_r143():
    """R-14.3 — un joueur peut abandonner à tout moment ; il perd immédiatement, l'autre gagne."""
    alice = Joueur(id="alice", actif=_pk("alice"), recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 5, PHASE_CHECKUP))
    etat2, evenements = appliquer(etat, Action(ACTION_ABANDONNER, "alice"), _rng())
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_ABANDON
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert fin.donnees["abandon_par"] == "alice"


# =========================================================================================
# K.O. simultané (R-13.5) et égalité (R-14.4 / R-16.10 / R-14.5)
# =========================================================================================


def test_double_ko_chacun_prend_ses_recompenses_et_promeut_r135():
    """R-13.5 — K.O. simultané : chaque joueur prend ses récompenses ; si la partie n'est pas
    finie, chacun promeut (les deux ont du banc)."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob", compteurs=100), banc=(_pk("bob", "b0"),),
                 recompenses=_recompenses("bob", 6))
    etat = _etat_checkup(alice, bob, actif="bob")
    fiches = {**_fiche(alice.actif, pv=100), **_fiche(bob.actif, pv=100)}
    etat2, evenements = resoudre_kos(etat, fiches, _ordre(etat, "bob"))
    assert not etat2.terminee
    # Chacun a pris 1 récompense (R-13.5) : 5 restantes de chaque côté.
    assert len(etat2.joueurs[0].recompenses) == 5 and len(etat2.joueurs[1].recompenses) == 5
    requises = {e.donnees["joueur"] for e in evenements if e.type == EVT_PROMOTION_REQUISE}
    assert requises == {"alice", "bob"}
    assert len([e for e in evenements if e.type == EVT_KO]) == 2


def test_double_ko_qui_vide_les_deux_reserves_est_une_egalite_r144_r1610():
    """R-14.4/R-16.10 — un double K.O. qui ferait prendre à chacun sa dernière récompense (et vide
    les deux bancs) donne une **égalité**, jamais « le joueur actif gagne ». Nombre de voies égal
    des deux côtés → NULLE (R-14.5 ne départage pas)."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(),
                   recompenses=_recompenses("alice", 1))
    bob = Joueur(id="bob", actif=_pk("bob", compteurs=100), banc=(),
                 recompenses=_recompenses("bob", 1))
    etat = _etat_checkup(alice, bob, actif="bob")
    fiches = {**_fiche(alice.actif, pv=100), **_fiche(bob.actif, pv=100)}
    etat2, evenements = resoudre_kos(etat, fiches, _ordre(etat, "bob"))
    assert etat2.terminee and etat2.vainqueur is None
    assert etat2.raison_fin == RAISON_EGALITE
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert set(fin.donnees["perdants"]) == {"alice", "bob"}
    assert_invariants(etat2)


def test_deux_voies_contre_une_le_premier_gagne_pas_d_egalite_r145():
    """R-14.5 — si un joueur gagne par **deux** voies et l'autre par **une seule** au même instant,
    le premier est vainqueur (pas d'égalité).

    Montage : les deux Actifs tombent au même Checkup et chacun prend sa dernière récompense (1
    voie chacun). Mais alice garde du banc (pas éliminée) tandis que bob a le banc vide (éliminé) :
    alice gagne donc **aussi** par « adversaire sans Pokémon » → 2 voies contre 1, alice gagne."""
    alice = Joueur(id="alice", actif=_pk("alice", compteurs=100), banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 1))
    bob = Joueur(id="bob", actif=_pk("bob", compteurs=100), banc=(),
                 recompenses=_recompenses("bob", 1))
    etat = _etat_checkup(alice, bob, actif="bob")
    fiches = {**_fiche(alice.actif, pv=100), **_fiche(bob.actif, pv=100)}
    etat2, evenements = resoudre_kos(etat, fiches, _ordre(etat, "bob"))
    assert etat2.terminee and etat2.vainqueur == "alice"
    fin = next(e for e in evenements if e.type == EVT_PARTIE_TERMINEE)
    assert set(fin.donnees["voies"]) == {VOIE_DERNIERE_RECOMPENSE, VOIE_ADVERSAIRE_SANS_POKEMON}
    assert_invariants(etat2)


# =========================================================================================
# K.O. multiples d'une même attaque (mission point 1) — ordre officiel
# =========================================================================================


def test_une_attaque_qui_met_ko_plusieurs_pokemon_les_resout_tous_r124():
    """Mission — une attaque de zone met K.O. l'Actif ET un Pokémon du banc du même joueur : les
    deux sont défaussés, l'adversaire prend les récompenses des deux, dans un ordre déterministe
    (Actif avant banc). Le joueur garde un Pokémon de banc sain → promotion demandée."""
    alice = Joueur(
        id="alice",
        actif=_pk("alice", compteurs=100),
        banc=(_pk("alice", "b0", compteurs=100), _pk("alice", "b1")),  # b0 K.O., b1 sain
        recompenses=_recompenses("alice", 6),
    )
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = _etat_checkup(alice, bob, actif="bob")
    fiches = {
        **_fiche(alice.actif, pv=100),
        **_fiche(alice.banc[0], pv=100),
    }
    etat2, evenements = resoudre_kos(etat, fiches, _ordre(etat, "bob"))
    kos = [e for e in evenements if e.type == EVT_KO]
    assert len(kos) == 2
    # Ordre déterministe : l'Actif d'abord, puis le banc.
    assert kos[0].donnees["pokemon"] == "alice-actif"
    assert kos[1].donnees["pokemon"] == "alice-b0"
    # Bob a pris 2 récompenses (1 + 1) : 4 restantes.
    assert len(etat2.joueurs[1].recompenses) == 4
    # Alice garde b1 sain → promotion demandée, partie non finie.
    assert not etat2.terminee
    assert etat2.joueurs[0].actif is None and len(etat2.joueurs[0].banc) == 1
    requises = [e.donnees["joueur"] for e in evenements if e.type == EVT_PROMOTION_REQUISE]
    assert requises == ["alice"]


# =========================================================================================
# Partie terminée figée (R-14.6)
# =========================================================================================


def test_terminer_fige_vainqueur_et_raison_r146():
    """R-14.6 — ``terminer`` fige la partie (vainqueur + raison) et refuse de re-terminer."""
    alice = Joueur(id="alice", actif=_pk("alice"), recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 5, PHASE_CHECKUP))
    etat2, evt = terminer(etat, "bob", RAISON_DERNIERE_RECOMPENSE, perdant="alice")
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_DERNIERE_RECOMPENSE
    assert evt.type == EVT_PARTIE_TERMINEE and evt.donnees["perdant"] == "alice"
    with pytest.raises(ValueError, match="R-14.6"):
        terminer(etat2, "alice", RAISON_ABANDON)


def test_partie_terminee_refuse_toute_action_meme_mecanique_r146():
    """R-14.6 — ``appliquer`` refuse TOUTE action sur une partie terminée, y compris une action
    mécanique (ici l'abandon) : garde centrale, pas seulement par transition."""
    alice = Joueur(id="alice", actif=_pk("alice"), recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 6))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 5, PHASE_CHECKUP),
                      terminee=True, vainqueur="bob", raison_fin=RAISON_DERNIERE_RECOMPENSE)
    with pytest.raises(ValueError, match="R-14.6"):
        appliquer(etat, Action(ACTION_ABANDONNER, "alice"), _rng())


# =========================================================================================
# Intégration à la phase Checkup — la victoire par récompenses passe par le même résolveur
# =========================================================================================


def test_checkup_termine_la_partie_sur_derniere_recompense_r141():
    """R-14.1 cas 1 au Checkup — un empoisonnement met K.O. le dernier Actif d'alice (banc non
    vide) et fait prendre à bob sa **dernière** récompense : bob gagne via le résolveur partagé."""
    from pbm_game.state import EMPOISONNE

    alice_actif = PokemonEnJeu(cartes=(Carte("alice-actif", "ref-pk"),),
                               etats_speciaux=frozenset({EMPOISONNE}), compteurs_degats=90)
    alice = Joueur(id="alice", actif=alice_actif, banc=(_pk("alice", "b0"),),
                   recompenses=_recompenses("alice", 6))
    bob = Joueur(id="bob", actif=_pk("bob"), recompenses=_recompenses("bob", 1))
    etat = _etat_checkup(alice, bob, actif="bob")
    etat2, _ = resoudre_checkup(etat, _rng(), fiches=_fiche(alice_actif, pv=100))
    assert etat2.terminee and etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_DERNIERE_RECOMPENSE


# =========================================================================================
# Lien au corpus : toute règle citée par ce lot existe dans REGLES.md
# =========================================================================================


def test_les_regles_citees_par_ce_lot_existent_dans_le_corpus():
    """Toute règle ``R-x.y`` sur laquelle ce lot s'appuie est réellement définie dans REGLES.md
    (sinon une citation « pend » dans le vide)."""
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    definies = identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))
    citees = {
        "R-13.1", "R-13.2", "R-13.3", "R-13.4", "R-13.5", "R-13.7",
        "R-14.1", "R-14.2", "R-14.3", "R-14.4", "R-14.5", "R-14.6",
        "R-16.10", "R-8.9", "R-15.22",
    }
    manquantes = citees - definies
    assert not manquantes, f"Règles citées mais absentes du corpus : {sorted(manquantes)}"
