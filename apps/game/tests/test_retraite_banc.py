"""Tests du lot ``j-retraite-banc`` — l'Actif change de place (R-8).

Ce fichier FAIT FOI sur les critères d'acceptation de la mission :

1. les **trois mouvements** — retraite volontaire, promotion après K.O., échange forcé — ont des
   **chemins distincts et testés**, aux règles différentes (R-8.2/3/4, R-8.7, R-8.8) ;
2. le **passage au banc** soigne **ce qu'il doit** (états spéciaux, R-8.6) et **rien d'autre**
   (énergies, Outil, compteurs de dégâts et pile d'évolutions conservés) ;
3. le **banc vide après un K.O.** termine la partie avec la **bonne raison** (R-8.9/R-14.1).

S'y ajoutent les pièges nommés par la fiche : ne pas confondre échange forcé et retraite (une
carte d'appât reste jouable sous Paralysie — R-16.12 — et ne consomme pas la retraite du tour),
et le coût de retraite payé en énergies **au choix** du joueur (R-8.2). Chaque test de règle nomme
le ``R-x.y`` qu'il vérifie, et un test final contrôle que tous ces identifiants **existent** dans
``docs/jeu/REGLES.md``.

La suite échoue naturellement sans le paquet ``pbm_game.banc`` (import en tête) : c'est le « test
qui échoue sans le changement et passe avec ».
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pbm_game.banc import battre_en_retraite, echange_force, promouvoir
from pbm_game.journal import (
    ACTION_ECHANGE_FORCE,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
    AUTEUR_SYSTEME,
    EVT_ECHANGE_FORCE,
    EVT_PARTIE_TERMINEE,
    EVT_PROMOTION,
    EVT_RETRAITE,
    RAISON_PLUS_DE_POKEMON,
    Action,
    appliquer,
    decrire_entree,
    jouer,
    partie_neuve,
    rejouer,
)
from pbm_game.journal.serialisation import (
    action_depuis_json,
    action_vers_json,
    evenement_depuis_json,
    evenement_vers_json,
)
from pbm_game.regles import MOTIF_REGLE, identifiants_definis
from pbm_game.rng import Rng
from pbm_game.state import (
    BRULE,
    CONFUS,
    EMPOISONNE,
    ENDORMI,
    PARALYSE,
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
    carte_active,
    depuis_json,
    vers_json,
)

RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"

GRAINE_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # 16 octets (minimum du Rng)
# La retraite, la promotion et l'échange forcé n'ont aucun aléa : le Rng ne doit jamais avancer.
_RNG = Rng(b"retraite-banc-seed")


def _regles_definies() -> set[str]:
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    return identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))


# --- Fabriques déterministes -------------------------------------------------


def _energie(jid: str, n: int) -> Carte:
    return Carte(instance_id=f"{jid}-en-{n}", ref="ref-energie")


def _pokemon(
    jid: str,
    tag: str,
    *,
    nb_cartes: int = 1,
    energies: tuple[Carte, ...] = (),
    outil: Carte | None = None,
    compteurs: int = 0,
    etats: frozenset[str] = frozenset(),
) -> PokemonEnJeu:
    cartes = tuple(Carte(f"{jid}-{tag}-{i}", "ref-pk") for i in range(nb_cartes))
    return PokemonEnJeu(
        cartes=cartes,
        energies=energies,
        outil=outil,
        compteurs_degats=compteurs,
        etats_speciaux=etats,
    )


def _tour(
    *,
    actif: str = "alice",
    numero: int = 3,
    phase: str = PHASE_PRINCIPALE,
    retraite_faite: bool = False,
) -> Tour:
    return Tour(joueur_actif=actif, numero=numero, phase=phase, retraite_faite=retraite_faite)


def _etat(alice: Joueur, bob: Joueur, tour: Tour) -> EtatPartie:
    etat = EtatPartie(joueurs=(alice, bob), tour=tour)
    return etat


def _bob() -> Joueur:
    return Joueur(id="bob", actif=_pokemon("bob", "actif"))


# =========================================================================================
# Mouvement 1 — RETRAITE volontaire (R-8.2/R-8.3/R-8.4)
# =========================================================================================


def test_retraite_defausse_les_energies_choisies_et_echange_lactif_r82():
    """R-8.2 — défausser une énergie **par symbole** (au choix), puis échanger Actif ↔ banc."""
    e1, e2, e3 = _energie("alice", 1), _energie("alice", 2), _energie("alice", 3)
    actif = _pokemon("alice", "actif", energies=(e1, e2, e3))
    bancmon = _pokemon("alice", "banc0")
    alice = Joueur(id="alice", actif=actif, banc=(bancmon,))
    etat = _etat(alice, _bob(), _tour())

    # Le joueur choisit de défausser e1 et e3 (coût = 2) ; e2 reste.
    etat2, evts = battre_en_retraite(etat, "alice", 0, 2, (e1.instance_id, e3.instance_id))

    a2 = etat2.joueurs[0]
    assert carte_active(a2.actif) == bancmon.cartes[-1]  # le banc est monté Actif
    descendu = a2.banc[0]
    assert {c.instance_id for c in descendu.energies} == {e2.instance_id}  # e1/e3 partis
    assert {c.instance_id for c in a2.defausse} == {e1.instance_id, e3.instance_id}
    assert etat2.tour.retraite_faite is True  # R-5.6/R-8.3
    assert evts[0].type == EVT_RETRAITE
    assert evts[0].donnees["cout"] == 2
    assert_invariants(etat2)


def test_retraite_gratuite_cout_nul_ne_defausse_aucune_energie_r82():
    """R-8.2 — coût de retraite nul = retraite **gratuite**, aucune énergie défaussée."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,)),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat2, _ = battre_en_retraite(_etat(alice, _bob(), _tour()), "alice", 0, 0, ())
    assert etat2.joueurs[0].defausse == ()  # rien défaussé
    assert etat2.joueurs[0].banc[0].energies[0].instance_id == e1.instance_id  # énergie gardée
    assert_invariants(etat2)


def test_retraite_sans_energie_suffisante_refusee_r82():
    """R-8.2 — coût 2 mais une seule énergie attachée : la retraite est **impossible**."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,)),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour())
    with pytest.raises(ValueError, match="insuffisante|R-8.2"):
        battre_en_retraite(etat, "alice", 0, 2, (e1.instance_id,))


def test_retraite_avec_banc_plein_reste_valide_et_ne_deborde_pas_r81():
    """R-8.1 — banc **plein** (5) : la retraite échange sans jamais dépasser 5 (R-3.2)."""
    banc = tuple(_pokemon("alice", f"banc{i}") for i in range(5))
    alice = Joueur(id="alice", actif=_pokemon("alice", "actif"), banc=banc)
    etat = _etat(alice, _bob(), _tour())
    etat2, _ = battre_en_retraite(etat, "alice", 2, 0, ())
    assert len(etat2.joueurs[0].banc) == 5  # un sort, un entre : toujours 5
    assert etat2.joueurs[0].actif is not None
    assert_invariants(etat2)  # pas de 6e Pokémon en jeu


def test_retraite_une_seule_par_tour_refusee_si_deja_faite_r56():
    """R-5.6/R-8.3 — une seule retraite par tour : la seconde est refusée."""
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    etat = _etat(alice, _bob(), _tour(retraite_faite=True))
    with pytest.raises(ValueError, match="R-5.6|R-8.3|déjà"):
        battre_en_retraite(etat, "alice", 0, 0, ())


@pytest.mark.parametrize("etat_bloquant", [ENDORMI, PARALYSE])
def test_retraite_interdite_sous_sommeil_ou_paralysie_r84(etat_bloquant):
    """R-8.4/R-11.10 — un Actif Endormi ou Paralysé **ne peut pas** battre en retraite."""
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", etats=frozenset({etat_bloquant})),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour())
    with pytest.raises(ValueError, match="R-8.4|R-11.10"):
        battre_en_retraite(etat, "alice", 0, 0, ())


def test_retraite_sous_confusion_ou_marqueurs_reste_permise_r84():
    """R-8.4 — seuls Sommeil et Paralysie bloquent : Confus, Brûlé, Empoisonné n'empêchent pas."""
    etats = frozenset({CONFUS, BRULE, EMPOISONNE})
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", etats=etats),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat2, _ = battre_en_retraite(_etat(alice, _bob(), _tour()), "alice", 0, 0, ())
    assert etat2.joueurs[0].banc[0].etats_speciaux == frozenset()  # soigné au passage (R-8.6)
    assert_invariants(etat2)


def test_retraite_refuse_une_energie_non_attachee_r82():
    """R-8.2 — défausser une énergie qui n'est pas sur l'Actif est refusé (pas d'approximation)."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,)),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour())
    with pytest.raises(ValueError, match="non attachée|R-8.2"):
        battre_en_retraite(etat, "alice", 0, 1, ("alice-en-999",))


def test_retraite_refusee_hors_du_joueur_actif_r51():
    """R-5.1 — seul le joueur actif bat en retraite (c'est son tour)."""
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    bob = Joueur(id="bob", actif=_pokemon("bob", "actif"), banc=(_pokemon("bob", "banc0"),))
    etat = _etat(alice, bob, _tour(actif="alice"))
    with pytest.raises(ValueError, match="R-5.1|joueur actif"):
        battre_en_retraite(etat, "bob", 0, 0, ())


def test_retraite_refusee_en_phase_checkup_r51():
    """R-5.1 — la retraite se fait pendant le corps du tour, pas au Checkup."""
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    etat = _etat(alice, _bob(), _tour(phase=PHASE_CHECKUP))
    with pytest.raises(ValueError, match="R-5.1|phase"):
        battre_en_retraite(etat, "alice", 0, 0, ())


def test_retraite_sans_banc_refusee_r82():
    """R-8.2 — aucun Pokémon de banc pour prendre la place : la retraite est impossible."""
    alice = Joueur(id="alice", actif=_pokemon("alice", "actif"))
    etat = _etat(alice, _bob(), _tour())
    with pytest.raises(ValueError, match="banc|R-8.2"):
        battre_en_retraite(etat, "alice", 0, 0, ())


# =========================================================================================
# R-8.6 — le passage au banc soigne CE QU'IL DOIT, et RIEN D'AUTRE
# =========================================================================================


def test_passage_au_banc_retire_les_etats_mais_conserve_tout_le_reste_r86():
    """R-8.6 — le Pokémon qui descend perd ses états, garde énergies, Outil, compteurs, pile."""
    e1, e2 = _energie("alice", 1), _energie("alice", 2)
    outil = Carte("alice-outil-1", "ref-outil")
    # États NON bloquants (Confus/Brûlé/Empoisonné) : la retraite a lieu, puis ils sont soignés.
    actif = _pokemon(
        "alice",
        "actif",
        nb_cartes=2,  # pile d'évolutions (base + évolution)
        energies=(e1, e2),
        outil=outil,
        compteurs=30,
        etats=frozenset({CONFUS, BRULE, EMPOISONNE}),
    )
    alice = Joueur(id="alice", actif=actif, banc=(_pokemon("alice", "banc0"),))
    etat2, _ = battre_en_retraite(_etat(alice, _bob(), _tour()), "alice", 0, 0, ())

    descendu = etat2.joueurs[0].banc[0]
    assert descendu.etats_speciaux == frozenset()  # soigné (R-8.6)
    assert {c.instance_id for c in descendu.energies} == {e1.instance_id, e2.instance_id}
    assert descendu.outil == outil  # Outil conservé
    assert descendu.compteurs_degats == 30  # compteurs conservés (R-10.4)
    assert len(descendu.cartes) == 2  # pile d'évolutions conservée
    assert_invariants(etat2)


# =========================================================================================
# Mouvement 2 — PROMOTION après un K.O. (R-8.7) ; banc vide = défaite (R-8.9)
# =========================================================================================


def _etat_post_ko(banc_alice: tuple[PokemonEnJeu, ...]) -> EtatPartie:
    """L'état juste après un K.O. de l'Actif d'alice : son Actif est absent (vide à combler)."""
    alice = Joueur(id="alice", actif=None, banc=banc_alice)
    # alice promeut : le tour peut être à bob (K.O. au Checkup du tour adverse).
    return EtatPartie(joueurs=(alice, _bob()), tour=_tour(actif="bob"))


def test_promotion_remplit_lactif_vide_depuis_le_banc_r87():
    """R-8.7 — après un K.O., promouvoir un Pokémon du banc le rend Actif ; le banc perd un."""
    banc = (_pokemon("alice", "banc0"), _pokemon("alice", "banc1"))
    etat = _etat_post_ko(banc)
    etat2, evts = promouvoir(etat, "alice", 1)
    assert etat2.joueurs[0].actif is not None
    assert carte_active(etat2.joueurs[0].actif) == banc[1].cartes[-1]
    assert len(etat2.joueurs[0].banc) == 1  # un Pokémon est monté
    assert evts[0].type == EVT_PROMOTION
    assert etat2.terminee is False
    assert_invariants(etat2)


def test_promotion_banc_vide_termine_la_partie_avec_la_bonne_raison_r89():
    """R-8.9/R-14.1 — banc vide à la promotion = **défaite** (pas une exception)."""
    etat = _etat_post_ko(())  # Actif K.O. et banc vide
    etat2, evts = promouvoir(etat, "alice", 0)
    assert etat2.terminee is True
    assert etat2.vainqueur == "bob"  # l'adversaire gagne
    assert etat2.raison_fin == RAISON_PLUS_DE_POKEMON
    assert evts[0].type == EVT_PARTIE_TERMINEE
    assert evts[0].donnees["perdant"] == "alice"
    assert_invariants(etat2)


def test_promotion_refusee_si_lactif_est_present_r87():
    """R-8.7 — la promotion ne comble qu'un Actif absent (K.O.) ; refusée si l'Actif est là."""
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    etat = _etat(alice, _bob(), _tour())
    with pytest.raises(ValueError, match="R-8.7|Actif est présent"):
        promouvoir(etat, "alice", 0)


def test_promotion_index_hors_banc_refuse_r87():
    """R-8.7 — un ``banc_index`` hors du banc est refusé (jamais d'index deviné)."""
    etat = _etat_post_ko((_pokemon("alice", "banc0"),))
    with pytest.raises(ValueError, match="hors du banc|R-8.7"):
        promouvoir(etat, "alice", 5)


# =========================================================================================
# Mouvement 3 — ÉCHANGE FORCÉ (R-8.8) — ni retraite du tour, ni énergie, autorisé sous état
# =========================================================================================


def test_echange_force_sous_paralysie_est_autorise_r88_r1612():
    """R-8.8/R-16.12 — un effet force l'échange d'un Actif Paralysé — là où la retraite refuse."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,), etats=frozenset({PARALYSE})),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour(actif="alice"))
    etat2, evts = echange_force(etat, "alice", 0)
    assert carte_active(etat2.joueurs[0].actif) == alice.banc[0].cartes[-1]
    descendu = etat2.joueurs[0].banc[0]
    assert descendu.etats_speciaux == frozenset()  # soigné au passage (R-8.6)
    assert {c.instance_id for c in descendu.energies} == {e1.instance_id}  # énergie GARDÉE (R-8.8)
    assert evts[0].type == EVT_ECHANGE_FORCE
    assert_invariants(etat2)


def test_echange_force_ne_consomme_pas_la_retraite_du_tour_r88():
    """R-8.8 — l'échange forcé ne marque PAS la retraite : le joueur peut encore se retirer."""
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif"),
        banc=(_pokemon("alice", "banc0"), _pokemon("alice", "banc1")),
    )
    etat = _etat(alice, _bob(), _tour(actif="alice", retraite_faite=False))
    etat2, _ = echange_force(etat, "alice", 0)
    assert etat2.tour.retraite_faite is False  # intact : l'échange forcé ne le consomme pas
    # … et une retraite volontaire reste donc possible dans le même tour.
    etat3, _ = battre_en_retraite(etat2, "alice", 0, 0, ())
    assert etat3.tour.retraite_faite is True
    assert_invariants(etat3)


def test_echange_force_sans_actif_est_refuse_c_est_une_promotion_r88():
    """R-8.8 — sans Actif (K.O.), ce n'est pas un échange mais une promotion (R-8.7)."""
    etat = _etat_post_ko((_pokemon("alice", "banc0"),))
    with pytest.raises(ValueError, match="R-8.7|R-8.8|Actif"):
        echange_force(etat, "alice", 0)


def test_echange_force_sans_banc_est_refuse_r88():
    """R-8.8 — aucun Pokémon de banc vers qui échanger : refusé (pas de repli silencieux)."""
    alice = Joueur(id="alice", actif=_pokemon("alice", "actif"))
    etat = _etat(alice, _bob(), _tour(actif="alice"))
    with pytest.raises(ValueError, match="banc|R-8.8"):
        echange_force(etat, "alice", 0)


# =========================================================================================
# Les trois sont des TRANSITIONS JOURNALISÉES (appliquer / REGISTRE) et REJOUABLES
# =========================================================================================


def test_appliquer_retraite_par_le_registre_et_etat_initial_fige():
    """La retraite passe par ``appliquer`` (REGISTRE) ; l'état d'entrée reste **inchangé** (pur)."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,)),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour())
    avant = vers_json(etat)
    action = Action(
        ACTION_RETRAITE, "alice", {"banc_index": 0, "cout_retraite": 1,
                                   "energies_defaussees": [e1.instance_id]}
    )
    etat2, evts = appliquer(etat, action, _RNG)
    assert evts[0].type == EVT_RETRAITE
    assert vers_json(etat) == avant  # l'état initial n'a pas bougé
    assert etat2.tour.retraite_faite is True


def test_appliquer_promotion_et_echange_force_par_le_registre():
    """Promotion et échange forcé sont reconnus par ``appliquer`` (enregistrés dans REGISTRE)."""
    # Promotion
    etat_ko = _etat_post_ko((_pokemon("alice", "banc0"),))
    etat2, evts = appliquer(etat_ko, Action(ACTION_PROMOUVOIR, "alice", {"banc_index": 0}), _RNG)
    assert evts[0].type == EVT_PROMOTION and etat2.joueurs[0].actif is not None

    # Échange forcé (auteur système, cible nommée dans les params)
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    etat = _etat(alice, _bob(), _tour(actif="alice"))
    action = Action(ACTION_ECHANGE_FORCE, AUTEUR_SYSTEME, {"joueur": "alice", "banc_index": 0})
    etat3, evts3 = appliquer(etat, action, _RNG)
    assert evts3[0].type == EVT_ECHANGE_FORCE


def test_echange_force_sans_cible_nommee_est_refuse():
    """L'échange forcé exige ``params.joueur`` : on ne devine pas quel Actif change (D9)."""
    alice = Joueur(
        id="alice", actif=_pokemon("alice", "actif"), banc=(_pokemon("alice", "banc0"),)
    )
    etat = _etat(alice, _bob(), _tour(actif="alice"))
    with pytest.raises(ValueError, match="cible|joueur|R-8.8"):
        appliquer(etat, Action(ACTION_ECHANGE_FORCE, AUTEUR_SYSTEME, {"banc_index": 0}), _RNG)


def test_retraite_journalisee_est_rejouable_a_lidentique():
    """Rejouer le journal d'une partie contenant une retraite redonne l'état exact (empreinte)."""
    e1, e2 = _energie("alice", 1), _energie("alice", 2)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1, e2)),
        banc=(_pokemon("alice", "banc0"),),
    )
    etat = _etat(alice, _bob(), _tour())
    partie = partie_neuve(etat, GRAINE_HEX)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    action = Action(
        ACTION_RETRAITE, "alice",
        {"banc_index": 0, "cout_retraite": 1, "energies_defaussees": [e2.instance_id]},
    )
    partie, etat_final = jouer(partie, action, "2026-10-01T12:00:00Z", etat, rng)
    rejoue, _ = rejouer(partie)
    assert vers_json(rejoue) == vers_json(etat_final)


def test_action_et_evenement_de_retraite_round_trip_json():
    """L'action et l'événement de retraite se sérialisent et se relisent à l'identique."""
    action = Action(
        ACTION_RETRAITE, "alice",
        {"banc_index": 1, "cout_retraite": 2, "energies_defaussees": ["alice-en-1", "alice-en-2"]},
    )
    assert action_depuis_json(action_vers_json(action)) == action

    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,)),
        banc=(_pokemon("alice", "banc0"),),
    )
    _, evts = battre_en_retraite(_etat(alice, _bob(), _tour()), "alice", 0, 1, (e1.instance_id,))
    assert evenement_depuis_json(evenement_vers_json(evts[0])) == evts[0]


def test_journal_lisible_decrit_les_trois_mouvements():
    """La vue de débogage rend les mouvements lisiblement (pas de repli brut sur nos events)."""
    etat_ko = _etat_post_ko((_pokemon("alice", "banc0"),))
    partie = partie_neuve(etat_ko, GRAINE_HEX)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    partie, _ = jouer(
        partie, Action(ACTION_PROMOUVOIR, "alice", {"banc_index": 0}),
        "2026-10-01T12:00:00Z", etat_ko, rng,
    )
    ligne = decrire_entree(partie.entrees[0], noms={})
    assert "promeut" in ligne and "alice" in ligne
    # Un événement connu n'est jamais rendu en brut (son type nu n'apparaît pas).
    assert EVT_PROMOTION not in ligne


# =========================================================================================
# Reprise après F5 : un état avec retraite faite survit à la sérialisation
# =========================================================================================


def test_etat_apres_retraite_survit_a_la_serialisation():
    """Un état issu d'une retraite se sérialise et se relit à l'identique (reprise après F5)."""
    e1 = _energie("alice", 1)
    alice = Joueur(
        id="alice",
        actif=_pokemon("alice", "actif", energies=(e1,), compteurs=20),
        banc=(_pokemon("alice", "banc0", compteurs=10),),
    )
    etat2, _ = battre_en_retraite(_etat(alice, _bob(), _tour()), "alice", 0, 1, (e1.instance_id,))
    assert depuis_json(vers_json(etat2)) == etat2
    assert_invariants(depuis_json(vers_json(etat2)))


# =========================================================================================
# Cohérence avec le corpus : chaque R-x.y cité par ces tests existe dans REGLES.md
# =========================================================================================

# Les identifiants de règle que cette suite revendique vérifier.
_REGLES_CITEES = {
    "R-8.1", "R-8.2", "R-8.3", "R-8.4", "R-8.6", "R-8.7", "R-8.8", "R-8.9",
    "R-5.1", "R-5.6", "R-11.10", "R-14.1", "R-16.12", "R-3.2", "R-10.4",
}


def test_les_regles_citees_existent_dans_le_corpus():
    """Critère : tout ``R-x.y`` revendiqué par ces tests est **défini** dans docs/jeu/REGLES.md."""
    definies = _regles_definies()
    for r in sorted(_REGLES_CITEES):
        assert MOTIF_REGLE.fullmatch(r), f"identifiant mal formé : {r}"
        assert r in definies, f"{r} cité par les tests mais absent du corpus"


def test_docstrings_ne_citent_que_des_regles_existantes():
    """Les ``R-x.y`` cités dans les docstrings de ce fichier existent tous dans le corpus."""
    definies = _regles_definies()
    source = Path(__file__).read_text(encoding="utf-8")
    cites = set(re.findall(r"R-\d+\.\d+", source))
    inconnues = sorted(c for c in cites if c not in definies)
    assert not inconnues, f"règles citées mais absentes du corpus : {inconnues}"
