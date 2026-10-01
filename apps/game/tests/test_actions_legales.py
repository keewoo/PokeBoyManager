"""Tests du générateur d'actions légales — lot ``j-actions-legales``.

Ce fichier FAIT FOI sur les critères d'acceptation de la mission :

1. sur des milliers d'états tirés de parties simulées, **toute** action de la liste
   s'applique sans erreur (et laisse l'état sain), et **aucune** action hors liste n'est
   acceptée par :func:`valider` ;
2. **chaque refus** porte un identifiant de règle qui **existe** dans ``docs/jeu/REGLES.md`` ;
3. le calcul de la liste reste **sous 5 ms** sur un état complet.

Chaque test de règle nomme le ``R-x.y`` qu'il vérifie (principe du corpus). La suite échoue
naturellement sans le paquet ``pbm_game.actions`` : c'est le « test qui échoue sans le
changement et passe avec ».
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

from fabrique_etats import fabrique_etat

from pbm_game.actions import (
    ActionLegale,
    Cible,
    Famille,
    actions_legales,
    valider,
)
from pbm_game.actions.modele import GENRE_POKEMON_EN_JEU, refus
from pbm_game.journal import (
    ACTION_ABANDONNER,
    ACTION_AVANCER_PHASE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    RAISON_ABANDON,
    Action,
    appliquer,
)
from pbm_game.regles import identifiants_definis
from pbm_game.rng import Rng
from pbm_game.state import (
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
)

# apps/game/tests/test_actions_legales.py -> racine du dépôt (parents[3]).
RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"

# Un Rng partagé suffit : avancer_phase et abandonner ne tirent aucun aléatoire.
_RNG = Rng(b"actions-legales-seed")


def _regles_definies() -> set[str]:
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


def _etat_simple(
    *, phase: str = PHASE_PRINCIPALE, actif: str = "alice", terminee: bool = False
) -> EtatPartie:
    """Un état minimal à deux joueurs, vivant par défaut — pour les cas nommés."""
    pk = PokemonEnJeu(cartes=(Carte("a-pk-1", "ref-pk"),))
    alice = Joueur(id="alice", actif=pk)
    bob = Joueur(id="bob", actif=PokemonEnJeu(cartes=(Carte("b-pk-1", "ref-pk"),)))
    return EtatPartie(
        joueurs=(alice, bob),
        tour=Tour(joueur_actif=actif, numero=3, phase=phase),
        terminee=terminee,
        vainqueur="alice" if terminee else None,
        raison_fin="test" if terminee else None,
    )


# --- Pureté et API -----------------------------------------------------------


def test_import_actions_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.actions`` ne charge aucun module interdit (preuve de pureté)."""
    interdits = {"fastapi", "sqlalchemy", "httpx", "requests", "redis", "boto3", "pbm_api"}
    importlib.import_module("pbm_game.actions")
    charges = interdits & set(sys.modules)
    assert not charges, f"L'import a tiré des dépendances interdites : {sorted(charges)}"


def test_actions_expose_son_api():
    mod = importlib.import_module("pbm_game.actions")
    attendus = ("actions_legales", "valider", "ActionLegale", "Cible", "Verdict", "FAMILLES_DEFAUT")
    for nom in attendus:
        assert hasattr(mod, nom), f"pbm_game.actions n'expose pas « {nom} »"


# --- Familles livrées : avancer_phase (R-5.1) --------------------------------


def test_avancer_phase_legal_pour_le_joueur_actif():
    """R-5.1 — le joueur actif peut avancer la phase ; l'autre ne le peut pas."""
    etat = _etat_simple(actif="alice")
    types_alice = {al.action.type for al in actions_legales(etat, "alice")}
    types_bob = {al.action.type for al in actions_legales(etat, "bob")}
    assert ACTION_AVANCER_PHASE in types_alice
    assert ACTION_AVANCER_PHASE not in types_bob


def test_avancer_phase_refuse_au_joueur_non_actif_cite_r51():
    """R-5.1 — avancer la phase quand ce n'est pas son tour est refusé, règle citée."""
    etat = _etat_simple(actif="alice")
    verdict = valider(etat, Action(ACTION_AVANCER_PHASE, "bob"))
    assert verdict.refuse
    assert verdict.regle == "R-5.1"
    assert verdict.message


def test_etiquette_avancer_phase_depend_de_la_phase():
    """L'étiquette lisible distingue « terminer le tour » (checkup) du reste."""
    def etiquette_avancer(etat: EtatPartie) -> str:
        coups = [a for a in actions_legales(etat, "alice") if a.action.type == ACTION_AVANCER_PHASE]
        (coup,) = coups
        return coup.etiquette

    assert etiquette_avancer(_etat_simple(phase=PHASE_CHECKUP)) == "Terminer le tour"
    assert etiquette_avancer(_etat_simple(phase=PHASE_PRINCIPALE)) == "Passer à la phase suivante"


# --- Familles livrées : abandonner (R-14.3) ----------------------------------


def test_abandonner_legal_pour_les_deux_joueurs():
    """R-14.3 — un joueur peut abandonner à tout moment, même hors de son tour."""
    etat = _etat_simple(actif="alice")
    for joueur in ("alice", "bob"):
        types = {al.action.type for al in actions_legales(etat, joueur)}
        assert ACTION_ABANDONNER in types, f"{joueur} doit pouvoir abandonner (R-14.3)"


def test_abandonner_termine_la_partie_au_profit_de_l_adversaire():
    """R-14.3 / R-14.6 — l'abandon fige la partie, l'adversaire gagne."""
    etat = _etat_simple(actif="alice")
    etat2, evenements = appliquer(etat, Action(ACTION_ABANDONNER, "alice"), _RNG)
    assert etat2.terminee
    assert etat2.vainqueur == "bob"
    assert etat2.raison_fin == RAISON_ABANDON
    assert evenements and evenements[0].donnees["abandon_par"] == "alice"
    assert_invariants(etat2)


def test_abandonner_refuse_a_un_non_joueur_cite_r143():
    """R-14.3 — seul un joueur de la partie peut abandonner."""
    etat = _etat_simple()
    verdict = valider(etat, Action(ACTION_ABANDONNER, "carol"))
    assert verdict.refuse and verdict.regle == "R-14.3"


# --- Partie terminée figée (R-14.6) ------------------------------------------


def test_partie_terminee_ne_rend_aucun_coup_et_refuse_tout():
    """R-14.6 — une partie terminée ne propose aucun coup et refuse toute action."""
    etat = _etat_simple(terminee=True)
    assert actions_legales(etat, "alice") == ()
    assert actions_legales(etat, "bob") == ()
    verdict = valider(etat, Action(ACTION_ABANDONNER, "alice"))
    assert verdict.refuse and verdict.regle == "R-14.6"


# --- Types non jouables par un joueur (R-5.2, R-4.1, R-15.12) ----------------


def test_piocher_par_un_joueur_refuse_cite_r52():
    """R-5.2 — la pioche de début de tour est automatique, pas un coup libre."""
    etat = _etat_simple(actif="alice")
    verdict = valider(etat, Action(ACTION_PIOCHER, "alice"))
    assert verdict.refuse and verdict.regle == "R-5.2"


def test_melanger_par_un_joueur_refuse_cite_r41():
    """R-4.1 — le mélange appartient à la mise en place."""
    etat = _etat_simple(actif="alice")
    verdict = valider(etat, Action(ACTION_MELANGER_PIOCHE, "alice"))
    assert verdict.refuse and verdict.regle == "R-4.1"


def test_type_inconnu_refuse_cite_d9():
    """R-15.12 (D9) — un effet non implémenté n'est jamais approximé."""
    etat = _etat_simple(actif="alice")
    verdict = valider(etat, Action("poser_pokemon", "alice"))
    assert verdict.refuse and verdict.regle == "R-15.12"


def test_refus_helper_exige_une_regle_et_un_message():
    """Un refus muet est interdit : ``refus`` lève sans règle ou sans message."""
    import pytest

    with pytest.raises(ValueError):
        refus("", "message")
    with pytest.raises(ValueError):
        refus("R-1.1", "")


# --- Cohérence liste ⇔ validation : le mécanisme de cibles -------------------


class _FamilleJouet(Famille):
    """Famille de test : prouve que le cadre porte des cibles calculées depuis l'état.

    Elle gouverne un type fictif et propose, pour le joueur actif, de « marquer » chacun de
    ses Pokémon en jeu — une cible par Pokémon. Aucune règle de carte n'est inventée en
    production : ce jouet vit **dans les tests**, pour exercer le cadre bout à bout.
    """

    nom = "jouet"
    TYPE = "jouet_marquer"

    def gouverne(self, action: Action) -> bool:
        return action.type == self.TYPE

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        if joueur != etat.tour.joueur_actif:
            return []
        j = next(x for x in etat.joueurs if x.id == joueur)
        pokemons = ([j.actif] if j.actif else []) + list(j.banc)
        cibles = tuple(
            Cible(GENRE_POKEMON_EN_JEU, p.cartes[-1].instance_id, p.cartes[-1].ref)
            for p in pokemons
        )
        if not cibles:
            return []
        return [ActionLegale(Action(self.TYPE, joueur), "Marquer un Pokémon", cibles)]

    def refuser(self, etat: EtatPartie, action: Action):
        return refus("R-5.1", "jouet non applicable")


def test_cadre_porte_des_cibles_calculees_depuis_l_etat():
    """Le cadre expose des cibles ; valider accepte un coup de la liste, refuse hors liste."""
    familles = (_FamilleJouet(),)
    etat = _etat_simple(actif="alice")
    (coup,) = actions_legales(etat, "alice", familles=familles)
    assert coup.cibles and all(c.genre == GENRE_POKEMON_EN_JEU for c in coup.cibles)
    # Un coup de la liste est accepté…
    assert valider(etat, coup.action, familles=familles).accepte
    # …et le même type joué par le joueur NON actif est refusé (hors liste).
    assert valider(etat, Action(_FamilleJouet.TYPE, "bob"), familles=familles).refuse


# --- Critère 2 : chaque refus cite une règle qui EXISTE dans REGLES.md -------


def test_chaque_refus_cite_une_regle_du_corpus():
    """Critère d'acceptation : tout ``R-x.y`` de refus existe dans docs/jeu/REGLES.md."""
    definies = _regles_definies()
    etat = _etat_simple(actif="alice")
    refus_observes = [
        valider(_etat_simple(terminee=True), Action(ACTION_ABANDONNER, "alice")),
        valider(etat, Action(ACTION_AVANCER_PHASE, "bob")),
        valider(etat, Action(ACTION_ABANDONNER, "carol")),
        valider(etat, Action(ACTION_PIOCHER, "alice")),
        valider(etat, Action(ACTION_MELANGER_PIOCHE, "alice")),
        valider(etat, Action("effet_inconnu", "alice")),
    ]
    for v in refus_observes:
        assert v.refuse, "ce cas doit être un refus"
        assert v.regle in definies, f"règle citée « {v.regle} » absente du corpus REGLES.md"
        assert v.message.strip(), "un refus doit porter un message lisible"


# --- Critère 1 : propriété sur des milliers d'états simulés -------------------


def test_propriete_toute_action_legale_s_applique_sans_erreur():
    """Critère 1 — 10 000 états : chaque coup listé s'applique et laisse l'état sain,
    chaque coup listé est accepté par valider, et un coup hors liste est refusé."""
    definies = _regles_definies()
    for seed in range(10_000):
        etat = fabrique_etat(seed)
        ids = [j.id for j in etat.joueurs]
        for joueur in ids:
            legales = actions_legales(etat, joueur)
            for coup in legales:
                # (a) s'applique sans lever, et l'état résultant est sain.
                etat2, _ = appliquer(etat, coup.action, _RNG)
                assert_invariants(etat2)
                # (b) la liste et la validation ne divergent jamais.
                assert valider(etat, coup.action).accepte, (
                    f"coup listé refusé : {coup.action} (seed {seed}, {joueur})"
                )
            # (c) un coup hors liste est refusé, avec une règle qui existe.
            hors_liste = Action("coup_imaginaire", joueur)
            v = valider(etat, hors_liste)
            assert v.refuse and v.regle in definies


def test_aucune_action_hors_liste_n_est_acceptee():
    """Critère 1 (volet négatif) — une batterie de coups hors liste est toujours refusée."""
    for seed in range(500):
        etat = fabrique_etat(seed)
        actif = etat.tour.joueur_actif
        autre = next(j.id for j in etat.joueurs if j.id != actif)
        hors_liste = [
            Action(ACTION_AVANCER_PHASE, autre),  # pas son tour (R-5.1)
            Action(ACTION_PIOCHER, actif),  # pioche non libre (R-5.2)
            Action(ACTION_MELANGER_PIOCHE, actif),  # mise en place (R-4.1)
            Action(ACTION_ABANDONNER, "intrus"),  # pas un joueur (R-14.3)
            Action("attaquer", actif),  # non implémenté (R-15.12)
        ]
        for action in hors_liste:
            assert valider(etat, action).refuse, f"devrait être refusé : {action} (seed {seed})"


# --- Critère 3 : coût de calcul sous 5 ms ------------------------------------


def test_actions_legales_sous_5ms_sur_un_etat_complet():
    """Critère 3 — la liste se calcule bien sous 5 ms sur un état complet.

    On mesure le **meilleur** temps sur plusieurs essais (réduit la sensibilité au bruit de
    l'ordonnanceur CI) ; le seuil de 5 ms reste très largement tenu.
    """
    # Un état « complet » : banc plein, mains et pioches garnies, états spéciaux, stade.
    etat = fabrique_etat(123_456)
    joueur = etat.tour.joueur_actif
    meilleur = min(_chrono(lambda: actions_legales(etat, joueur)) for _ in range(50))
    assert meilleur < 5e-3, f"actions_legales a pris {meilleur * 1e3:.3f} ms (> 5 ms)"


def _chrono(fn) -> float:
    debut = time.perf_counter()
    fn()
    return time.perf_counter() - debut
