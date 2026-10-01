"""Journal d'actions — lot ``j-journal-actions``.

Ces tests FONT FOI sur les critères d'acceptation du lot :

1. **Rejouabilité** — sur **1 000 parties simulées**, rejouer le journal redonne
   *exactement* l'état final **et** toutes les empreintes intermédiaires concordent ;
   une entrée truquée (empreinte ou événement) est attrapée **au coup près**.
2. **Lisibilité** — une entrée se lit sans outil, identifiants de cartes résolus en noms.
3. **Compaction** — reprendre depuis un instantané + queue donne le même état que le rejeu
   complet, octet pour octet.

Le moteur est **pur** : ces tests n'ouvrent ni base, ni réseau, ni fichier. Chaque test de
règle cite son ``R-x.y`` (``docs/jeu/REGLES.md``). Le simulateur utilise ``random`` — ce
qui est permis dans les **tests** (le grep de pureté ne scanne que ``src/pbm_game``) —
pour choisir des actions ; l'aléatoire **du jeu** passe, lui, uniquement par le ``Rng``.
"""

from __future__ import annotations

import importlib
import random
import sys

import pytest
from fabrique_etats import fabrique_etat

from pbm_game.journal import (
    ACTION_AVANCER_PHASE,
    ACTION_MELANGER_PIOCHE,
    ACTION_PIOCHER,
    AUTEUR_SYSTEME,
    EVT_CARTES_PIOCHEES,
    JOURNAL_VERSION,
    Action,
    RejeuDivergent,
    appliquer,
    compacter,
    decrire_entree,
    empreinte,
    entree_vers_json,
    instantane_depuis_json,
    instantane_vers_json,
    jouer,
    partie_depuis_json,
    partie_neuve,
    partie_vers_json,
    rejouer,
    reprendre_partie,
)
from pbm_game.rng import Rng
from pbm_game.state import PHASE_PIOCHE, PHASE_PRINCIPALE, vers_json

GRAINE_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"


def _etat_jouable(seed: int):
    """Un état initial valide avec, pour chaque joueur, une pioche non vide (R-5.2 utile).

    ``fabrique_etat`` peut rendre une pioche vide ; les actions du simulateur ne demandent
    alors que ce qui est faisable (voir ``_simuler``). L'identité des joueurs reste
    ``alice`` / ``bob``.
    """
    etat = fabrique_etat(seed)
    # On ne corrige pas l'état ; on choisit seulement des actions compatibles (voir
    # _simuler), ce qui évite d'introduire un état hors fabrique.
    return etat


# --- Noyau : appliquer est pur et refuse l'inconnu ---------------------------


def test_appliquer_ne_mute_pas_l_etat_entrant():
    """``appliquer`` renvoie un nouvel état sans toucher l'entrant (fonction pure, R-forme)."""
    etat = fabrique_etat(1)
    avant = vers_json(etat)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), rng)
    assert vers_json(etat) == avant, "appliquer a muté l'état d'entrée (effet de bord)."


def test_type_d_action_inconnu_est_refuse_pas_approxime():
    """Un type d'action inconnu lève plutôt que d'être deviné (D9)."""
    etat = fabrique_etat(2)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    with pytest.raises(ValueError, match="inconnu"):
        appliquer(etat, Action("telekinesie", "alice"), rng)


def test_piocher_refuse_une_pioche_insuffisante():
    """Piocher plus que la pioche ne contient est refusé, pas replié en silence (R-5.2)."""
    etat = fabrique_etat(3)
    # Joueur dont on connaît la taille de pioche.
    jid = etat.joueurs[0].id
    trop = len(etat.joueurs[0].pioche) + 1
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    with pytest.raises(ValueError, match="insuffisante"):
        appliquer(etat, Action(ACTION_PIOCHER, jid, {"nombre": trop}), rng)


def test_piocher_deplace_du_sommet_vers_la_main():
    """Piocher déplace le sommet de la pioche (pioche[0]) vers la main (R-5.2)."""
    etat = fabrique_etat(7)
    jid = etat.joueurs[0].id
    if not etat.joueurs[0].pioche:
        pytest.skip("pioche vide pour cette graine")
    sommet = etat.joueurs[0].pioche[0].instance_id
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    etat2, evenements = appliquer(etat, Action(ACTION_PIOCHER, jid, {"nombre": 1}), rng)
    assert etat2.joueurs[0].main[-1].instance_id == sommet
    assert len(etat2.joueurs[0].pioche) == len(etat.joueurs[0].pioche) - 1
    assert evenements[0].type == EVT_CARTES_PIOCHEES
    assert evenements[0].donnees["instance_ids"] == [sommet]


def test_avancer_phase_boucle_sur_le_tour_suivant():
    """pioche→principale→attaque→checkup→(tour+1, joueur adverse, pioche) — R-5.1, R-12.1."""
    etat = fabrique_etat(5)
    # Forcer un point de départ connu : on part du modèle en phase pioche, tour 1, alice.
    from dataclasses import replace

    from pbm_game.state import Tour

    etat = replace(etat, tour=Tour(joueur_actif="alice", numero=1, phase=PHASE_PIOCHE))
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    etat, _ = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), rng)  # → principale
    assert etat.tour.phase == PHASE_PRINCIPALE
    etat, _ = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), rng)  # → attaque
    etat, _ = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), rng)  # → checkup
    etat, evenements = appliquer(etat, Action(ACTION_AVANCER_PHASE, "alice"), rng)  # → tour 2
    assert etat.tour.numero == 2
    assert etat.tour.joueur_actif == "bob"
    assert etat.tour.phase == PHASE_PIOCHE
    assert etat.tour.energie_posee is False  # drapeaux « une fois par tour » remis (R-5.4/5/6)


# --- Simulateur de partie ----------------------------------------------------


def _simuler(seed: int, nb_coups: int):
    """Construit une partie de ``nb_coups`` actions mécaniques valides, et renvoie
    ``(partie, etat_final, empreintes)`` où ``empreintes`` est la suite des empreintes
    après chaque coup, telles qu'en avant de jeu.
    """
    rnd = random.Random(seed)
    graine = rnd.randbytes(32).hex()
    etat = _etat_jouable(seed)
    partie = partie_neuve(etat, graine)
    rng = Rng(bytes.fromhex(graine))
    empreintes: list[str] = []
    for i in range(nb_coups):
        joueur = rnd.choice([etat.joueurs[0].id, etat.joueurs[1].id])
        choix = rnd.random()
        # Les trois actions mécaniques, en ne demandant que ce qui est faisable.
        idx = 0 if joueur == etat.joueurs[0].id else 1
        pioche = etat.joueurs[idx].pioche
        if choix < 0.45 and pioche:
            action = Action(ACTION_PIOCHER, joueur, {"nombre": rnd.randint(1, len(pioche))})
        elif choix < 0.75:
            action = Action(ACTION_MELANGER_PIOCHE, joueur)
        else:
            action = Action(ACTION_AVANCER_PHASE, joueur)
        horodatage = f"2026-10-01T12:00:{i:02d}Z"
        partie, etat = jouer(partie, action, horodatage, etat, rng)
        empreintes.append(empreinte(etat))
    return partie, etat, empreintes


# --- Critère 1 : rejouabilité sur 1 000 parties ------------------------------


def test_mille_parties_rejouees_a_l_identique():
    """Sur 1 000 parties simulées, ``rejouer`` redonne l'état final exact (R-forme).

    C'est le critère d'acceptation central : une partie = état initial + graine + journal.
    On compare la **sérialisation** (égalité octet pour octet via ``vers_json``), pas
    seulement ``==``.
    """
    for seed in range(1000):
        nb = (seed % 12) + 1  # de 1 à 12 coups : des journaux courts et un peu plus longs
        partie, etat_final, empreintes = _simuler(seed, nb)
        rejoue, _rng = rejouer(partie)
        assert vers_json(rejoue) == vers_json(etat_final), f"divergence de rejeu (seed={seed})"
        # Toutes les empreintes intermédiaires, telles qu'enregistrées, concordent avec
        # celles observées en avant de jeu.
        assert [e.empreinte for e in partie.entrees] == empreintes, f"empreintes (seed={seed})"


def test_rejeu_mord_sur_une_empreinte_truquee():
    """Une empreinte d'entrée falsifiée est attrapée **au coup près** (anti-triche)."""
    from dataclasses import replace

    partie, _etat, _ = _simuler(42, 6)
    assert partie.entrees, "le journal doit porter au moins une entrée"
    cible = 3
    truquee = replace(partie.entrees[cible], empreinte="0" * 64)
    entrees = list(partie.entrees)
    entrees[cible] = truquee
    partie_truquee = replace(partie, entrees=tuple(entrees))
    with pytest.raises(RejeuDivergent) as exc:
        rejouer(partie_truquee)
    assert exc.value.numero == cible
    assert "empreinte" in exc.value.quoi


def test_rejeu_mord_sur_un_evenement_truque():
    """Un événement d'entrée falsifié est attrapé au coup près (le journal ne peut mentir)."""
    from dataclasses import replace

    from pbm_game.journal import Evenement

    partie, _etat, _ = _simuler(99, 6)
    cible = 2
    faux = replace(partie.entrees[cible], evenements=(Evenement("mensonge", {}),))
    entrees = list(partie.entrees)
    entrees[cible] = faux
    partie_truquee = replace(partie, entrees=tuple(entrees))
    with pytest.raises(RejeuDivergent) as exc:
        rejouer(partie_truquee)
    assert exc.value.numero == cible


# --- Critère 2 : lisibilité sans outil ---------------------------------------


def test_entree_lisible_resout_les_noms_de_cartes():
    """Une entrée de pioche se lit avec les **noms** de cartes, pas les identifiants bruts."""
    etat = fabrique_etat(11)
    jid = etat.joueurs[0].id
    if not etat.joueurs[0].pioche:
        pytest.skip("pioche vide pour cette graine")
    sommet = etat.joueurs[0].pioche[0].instance_id
    partie = partie_neuve(etat, GRAINE_HEX)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    partie, _etat = jouer(
        partie, Action(ACTION_PIOCHER, jid, {"nombre": 1}), "2026-10-01T12:00:00Z", etat, rng
    )
    noms = {sommet: "Dracaufeu"}
    ligne = decrire_entree(partie.entrees[0], noms)
    assert "Dracaufeu" in ligne
    assert jid in ligne


def test_entree_lisible_signale_un_nom_inconnu_sans_le_masquer():
    """Un identifiant absent de la table est rendu explicitement, jamais masqué (pas de repli)."""
    etat = fabrique_etat(12)
    jid = etat.joueurs[0].id
    if not etat.joueurs[0].pioche:
        pytest.skip("pioche vide pour cette graine")
    partie = partie_neuve(etat, GRAINE_HEX)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    partie, _etat = jouer(
        partie, Action(ACTION_PIOCHER, jid, {"nombre": 1}), "2026-10-01T12:00:00Z", etat, rng
    )
    ligne = decrire_entree(partie.entrees[0], noms={})
    assert "nom inconnu" in ligne


# --- Critère 3 : compaction (instantané + queue) -----------------------------


def test_reprise_depuis_instantane_egale_le_rejeu_complet():
    """Reprendre depuis un instantané + queue donne le même état que le rejeu complet."""
    for seed in (1, 2, 3, 7, 13, 21):
        partie, _etat, _ = _simuler(seed, 10)
        complet, _ = rejouer(partie)
        for k in range(len(partie.entrees) + 1):  # 0 (état initial) .. len (état final)
            instantane = compacter(partie, k)
            repris, _ = reprendre_partie(partie, instantane)
            assert vers_json(repris) == vers_json(complet), f"seed={seed}, k={k}"
            assert empreinte(repris) == empreinte(complet)


def test_instantane_incoherent_est_refuse():
    """Un instantané dont l'empreinte ne colle pas à son état est refusé (cache non cru)."""
    from dataclasses import replace

    partie, _etat, _ = _simuler(4, 8)
    instantane = compacter(partie, 4)
    corrompu = replace(instantane, empreinte="f" * 64)
    with pytest.raises(RejeuDivergent):
        reprendre_partie(partie, corrompu)


# --- Sérialisation versionnée (round-trip + refus d'une version inconnue) ----


def test_round_trip_partie():
    """``partie_depuis_json(partie_vers_json(p)) == p`` (journal versionné, R-forme)."""
    partie, _etat, _ = _simuler(77, 9)
    assert partie_depuis_json(partie_vers_json(partie)) == partie


def test_round_trip_instantane():
    """Round-trip exact d'un instantané, état du Rng compris."""
    partie, _etat, _ = _simuler(78, 9)
    instantane = compacter(partie, 5)
    assert instantane_depuis_json(instantane_vers_json(instantane)) == instantane


def test_version_de_journal_inconnue_est_refusee():
    """Relire un journal d'une version inconnue est refusé, jamais replié (pas de silence)."""
    partie, _etat, _ = _simuler(79, 3)
    brut = partie_vers_json(partie)
    brut["journal_version"] = JOURNAL_VERSION + 1
    with pytest.raises(ValueError, match="journal_version"):
        partie_depuis_json(brut)


def test_entree_round_trip_preserve_les_types_json():
    """Une entrée re-sérialisée reste égale (listes conservées) : le rejeu peut comparer."""
    partie, _etat, _ = _simuler(80, 6)
    for entree in partie.entrees:
        from pbm_game.journal import entree_depuis_json

        assert entree_depuis_json(entree_vers_json(entree)) == entree


# --- Pureté du paquet journal ------------------------------------------------

_MODULES_INTERDITS = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "redis",
    "boto3",
    "httpx",
    "requests",
    "pbm_api",
}


def test_import_journal_ne_tire_aucune_dependance_lourde():
    """Importer ``pbm_game.journal`` ne charge aucun module interdit (preuve de pureté)."""
    importlib.import_module("pbm_game.journal")
    charges = _MODULES_INTERDITS & set(sys.modules)
    assert not charges, f"L'import du journal a tiré des dépendances interdites : {sorted(charges)}"


def test_action_systeme_sans_joueur_cible_refusee():
    """Une action système sans « params.joueur » est refusée (pas de joueur deviné)."""
    etat = fabrique_etat(6)
    rng = Rng(bytes.fromhex(GRAINE_HEX))
    with pytest.raises(ValueError, match="joueur cible"):
        appliquer(etat, Action(ACTION_MELANGER_PIOCHE, AUTEUR_SYSTEME), rng)
