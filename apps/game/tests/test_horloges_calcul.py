"""Calcul des horloges — décompte, bascule, pause/reprise, expiration (lot ``j-timer``, DJ4).

Toutes les fonctions sont **pures** : le temps entre par ``maintenant`` (secondes). On vérifie la
mécanique des trois horloges (par tour, par joueur, par décision), la tolérance réseau, la pause de
déconnexion qui ne consomme rien, et la détection d'expiration — y compris **une décision adressée à
l'adversaire** en plein tour de l'autre (mission du lot).
"""

from __future__ import annotations

from pbm_game.horloges import calcul
from pbm_game.horloges.modele import (
    CAUSE_BUDGET,
    CAUSE_DECISION,
    CAUSE_TOUR,
    ConfigHorloges,
    EtatHorloges,
)

T0 = 1_000_000.0  # un instant de départ arbitraire (secondes depuis l'époque)


def _config() -> ConfigHorloges:
    # DJ4 : 90 s par tour, 1500 s (25 min) par joueur, 30 s par décision, 10 s de tolérance.
    return ConfigHorloges(
        par_tour_s=90, par_joueur_s=1500, par_decision_s=30,
        tolerance_reseau_s=10, pause_deconnexion_s=120,
    )


def _depart() -> EtatHorloges:
    return calcul.demarrer(_config(), ("alice", "bob"), "alice", T0)


# --- Démarrage et décompte ---------------------------------------------------


def test_demarrer_arme_le_tour_du_premier_joueur_avec_plein_budget():
    e = _depart()
    assert e.budgets_s == {"alice": 1500.0, "bob": 1500.0}
    assert e.actif is not None and e.actif.joueur == "alice" and e.actif.genre == "tour"
    assert calcul.ecoule(e, T0) == 0.0
    assert calcul.ecoule(e, T0 + 42) == 42.0


def test_restant_recalcule_la_verite_du_moment():
    e = _depart()
    r = calcul.restant(e, T0 + 30)
    assert r["joueurs"]["alice"]["genre"] == "tour"
    assert r["joueurs"]["alice"]["horloge_s"] == 60.0  # 90 - 30
    assert r["joueurs"]["alice"]["budget_s"] == 1470.0  # 1500 - 30
    # L'adversaire ne compte pas : pas d'horloge courte, budget intact.
    assert r["joueurs"]["bob"]["genre"] is None
    assert r["joueurs"]["bob"]["horloge_s"] is None
    assert r["joueurs"]["bob"]["budget_s"] == 1500.0
    assert r["maintenant"] == T0 + 30


# --- Bascule de tour : le temps passé est débité du budget -------------------


def test_basculer_debite_le_budget_et_arme_l_autre():
    e = calcul.basculer(_depart(), "bob", T0 + 50, genre="tour")
    assert e.budgets_s["alice"] == 1450.0  # 50 s débitées du tour d'alice
    assert e.budgets_s["bob"] == 1500.0
    assert e.actif.joueur == "bob" and e.actif.depuis == T0 + 50
    # Une horloge courte neuve pour bob.
    assert calcul.restant(e, T0 + 50)["joueurs"]["bob"]["horloge_s"] == 90.0


# --- Décision adressée à l'adversaire (mission) ------------------------------


def test_decision_adverse_compte_pour_l_adversaire_pendant_le_tour_de_l_autre():
    """Tour d'alice, mais bob doit décider : l'horloge « décision » court pour bob (DJ4)."""
    e = calcul.poser_decision(_depart(), "bob", T0 + 20)
    assert e.budgets_s["alice"] == 1480.0  # alice débitée des 20 s avant la demande
    assert e.actif.joueur == "bob" and e.actif.genre == "decision"
    r = calcul.restant(e, T0 + 25)
    assert r["joueurs"]["bob"]["genre"] == "decision"
    assert r["joueurs"]["bob"]["horloge_s"] == 25.0  # 30 - 5
    # Au retour (demande levée), le tour revient à alice sur une horloge courte neuve.
    e2 = calcul.lever_decision(e, "alice", T0 + 35)
    assert e2.actif.joueur == "alice" and e2.actif.genre == "tour"
    assert e2.budgets_s["bob"] == 1485.0  # bob débité des 15 s de décision (35 - 20)
    assert calcul.restant(e2, T0 + 35)["joueurs"]["alice"]["horloge_s"] == 90.0


# --- Expiration : tour, décision, budget -------------------------------------


def test_premiere_echeance_tour_apres_limite_plus_tolerance():
    e = _depart()  # 90 + 10 de tolérance = 100
    assert calcul.premiere_echeance(e, T0 + 95) is None  # dans la tolérance : pas encore
    assert calcul.premiere_echeance(e, T0 + 101) == ("alice", CAUSE_TOUR)


def test_premiere_echeance_decision_pour_l_adversaire():
    e = calcul.poser_decision(_depart(), "bob", T0)  # 30 + 10 = 40
    assert calcul.premiere_echeance(e, T0 + 39) is None
    assert calcul.premiere_echeance(e, T0 + 41) == ("bob", CAUSE_DECISION)


def test_premiere_echeance_budget_prime_quand_le_total_est_epuise():
    """Un budget presque vide expire avant l'horloge de tour : c'est la défaite au temps (DJ4)."""
    e = EtatHorloges(
        config=_config(),
        budgets_s={"alice": 5.0, "bob": 1500.0},
        actif=calcul.demarrer(_config(), ("alice", "bob"), "alice", T0).actif,
    )
    # 5 (budget) + 10 (tolérance) = 15 : le budget tombe à 15 s, bien avant l'horloge de tour (100).
    assert calcul.premiere_echeance(e, T0 + 14) is None
    assert calcul.premiere_echeance(e, T0 + 16) == ("alice", CAUSE_BUDGET)


# --- Pause de déconnexion : elle gèle, ne consomme rien ----------------------


def test_pause_gele_le_decompte_et_la_reprise_ne_consomme_rien():
    e = calcul.pause(_depart(), "alice", T0 + 20)  # déconnexion à 20 s écoulées
    assert e.en_pause and e.pause_joueur == "alice"
    # Pendant la pause, l'écoulé reste figé à 20, même 500 s plus tard.
    assert calcul.ecoule(e, T0 + 520) == 20.0
    assert calcul.premiere_echeance(e, T0 + 520) is None  # rien n'expire en pause
    # Reprise 80 s plus tard : le compteur reprend là où il s'était gelé.
    e2 = calcul.reprendre(e, T0 + 100)
    assert not e2.en_pause
    assert calcul.ecoule(e2, T0 + 110) == 30.0  # 20 avant la pause + 10 après la reprise


def test_pause_restante_et_expiree():
    e = calcul.pause(_depart(), "bob", T0 + 10)
    assert calcul.pause_restante(e, T0 + 10) == 120.0
    assert calcul.pause_restante(e, T0 + 90) == 40.0  # 120 - 80
    assert calcul.pause_expiree(e, T0 + 90) is False
    assert calcul.pause_expiree(e, T0 + 200) is True  # grâce dépassée (> 120 s)
    # Hors pause, pas d'échéance de grâce.
    assert calcul.pause_restante(_depart(), T0) is None


def test_pause_idempotente():
    """Une seconde déconnexion ne décale pas le début de la grâce (il part de la première)."""
    e1 = calcul.pause(_depart(), "alice", T0 + 20)
    e2 = calcul.pause(e1, "alice", T0 + 50)
    assert e2.pause_depuis == T0 + 20


# --- Arrêt (fin de partie) ---------------------------------------------------


def test_arreter_debite_et_stoppe_tout_comptage():
    e = calcul.arreter(_depart(), T0 + 40)
    assert e.actif is None
    assert e.budgets_s["alice"] == 1460.0
    assert calcul.premiere_echeance(e, T0 + 10_000) is None  # plus rien ne court


# --- Stabilité d'affichage (acceptation : ≤ 2 s d'écart) ---------------------


def test_restant_est_exact_et_deterministe_a_chaque_instant():
    """``restant`` renvoie exactement limite - écoulé : l'affichage client s'y réaligne.

    La propriété « ≤ 2 s d'écart » tient côté client parce que l'estimation locale est recalée sur
    cette valeur serveur à chaque événement ; ici on prouve que la valeur serveur est exacte et
    reproductible pour un instant donné.
    """
    e = _depart()
    for dt in (0, 1, 2, 5, 13, 60, 89):
        assert calcul.restant(e, T0 + dt)["joueurs"]["alice"]["horloge_s"] == 90 - dt
