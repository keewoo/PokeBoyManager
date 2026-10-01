"""Aléatoire reproductible — lot ``j-aleatoire-determinisme``.

Ces tests font foi sur les trois critères d'acceptation du lot :

1. **aucun appel à l'aléatoire global** (``random``) dans le moteur — test de grep
   statique sur tout le paquet ``pbm_game`` ;
2. **rejouabilité** — deux parties à graine et actions identiques donnent un état final
   identique, octet pour octet, sur une centaine de parties simulées ;
3. **vérification a posteriori** — le vérificateur commit-reveal confirme un journal
   honnête et **mord** sur un journal truqué (graine changée, pile ou face retourné,
   mélange réordonné, tirage effacé).

Le moteur est pur : ces tests n'ouvrent ni base, ni réseau, ni (pour le cœur) fichier.
Chaque test de règle cite son ``R-x.y`` (``docs/jeu/REGLES.md``).
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from pbm_game.rng import (
    FACE,
    FLUX_QUI_COMMENCE,
    PILE,
    Rng,
    Tirage,
    engagement,
    flux_melange_deck,
    rejouer_tirage,
    tirage_depuis_json,
    tirage_vers_json,
    verifier_engagement,
    verifier_journal,
)

# apps/game/tests/test_rng.py -> src/pbm_game (parents[1]/src/pbm_game).
PAQUET_MOTEUR = Path(__file__).resolve().parents[1] / "src" / "pbm_game"

GRAINE = bytes.fromhex("00112233445566778899aabbccddeeff")


# --- Critère 1 : aucun aléatoire global dans le moteur -----------------------


def test_aucun_import_ni_appel_a_random_dans_le_moteur():
    """Aucun fichier de ``pbm_game`` n'importe ``random`` ni n'y accède (R : rejouabilité).

    C'est le test de grep exigé par la mission : il interdit pour toujours un
    ``random.shuffle`` ou ``random.random()`` qui casserait la reproductibilité. Il
    échoue si on l'introduit n'importe où dans le moteur.
    """
    offenses: list[str] = []
    for fichier in PAQUET_MOTEUR.rglob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                for alias in noeud.names:
                    if alias.name == "random" or alias.name.startswith("random."):
                        offenses.append(f"{fichier.name}: import de « random »")
            elif isinstance(noeud, ast.ImportFrom):
                if (noeud.module or "") == "random" or (noeud.module or "").startswith("random."):
                    offenses.append(f"{fichier.name}: from random import …")
            elif isinstance(noeud, ast.Attribute):
                # Accès du type ``random.xxx`` (au cas où ``random`` serait exposé autrement).
                base = noeud.value
                if isinstance(base, ast.Name) and base.id == "random":
                    offenses.append(f"{fichier.name}: accès « random.{noeud.attr} »")
    assert not offenses, "Aléatoire global interdit dans le moteur :\n" + "\n".join(offenses)


# --- API de base -------------------------------------------------------------


def test_graine_trop_courte_refusee():
    with pytest.raises(ValueError, match="trop courte"):
        Rng(b"court")


def test_graine_non_octets_refusee():
    with pytest.raises(TypeError):
        Rng("pas des octets")  # type: ignore[arg-type]


def test_flux_vide_refuse():
    r = Rng(GRAINE)
    with pytest.raises(ValueError, match="flux"):
        r.pile_ou_face("", "motif")


def test_motif_vide_refuse():
    r = Rng(GRAINE)
    with pytest.raises(ValueError, match="motif"):
        r.pile_ou_face(FLUX_QUI_COMMENCE, "")


def test_pile_ou_face_rend_face_ou_pile():
    """R-4.7 : qui commence se tire à pile ou face — deux issues seulement."""
    r = Rng(GRAINE)
    resultat = r.pile_ou_face(FLUX_QUI_COMMENCE, "R-4.7 qui commence")
    assert resultat in (FACE, PILE)


def test_entier_dans_la_borne():
    r = Rng(GRAINE)
    for _ in range(50):
        v = r.entier("effet", "R-11 effet aléatoire", 6)
        assert 0 <= v < 6


def test_entier_borne_invalide_refuse():
    r = Rng(GRAINE)
    with pytest.raises(ValueError, match="positive"):
        r.entier("effet", "motif", 0)


def test_melanger_est_une_permutation():
    """R-4.1 : mélanger le deck réordonne sans perdre ni dupliquer de carte."""
    r = Rng(GRAINE)
    deck = list(range(60))
    melange = r.melanger(flux_melange_deck("joueur-A"), "R-4.1 mélange deck", deck)
    assert sorted(melange) == deck  # mêmes éléments
    assert melange != deck  # réellement battu (improbable identité sur 60 cartes)
    assert deck == list(range(60))  # l'entrée n'est pas mutée


def test_melanger_vide_et_singleton():
    r = Rng(GRAINE)
    assert r.melanger("f", "m", []) == []
    assert r.melanger("f", "m", ["x"]) == ["x"]


# --- Critère 1bis : flux indépendants ---------------------------------------


def test_flux_independants_un_tirage_ailleurs_ne_decale_rien():
    """Ajouter un pile ou face dans un flux ne change PAS la suite d'un autre flux.

    C'est le piège nommé dans la mission : un flux partagé casse la reproductibilité dès
    qu'une carte ajoute un tirage. Séparés, le flux B est identique avec ou sans tirage
    intercalé dans le flux A.
    """
    sans = Rng(GRAINE)
    b1 = sans.pile_ou_face("flux-B", "premier B")
    b2 = sans.pile_ou_face("flux-B", "second B")

    avec = Rng(GRAINE)
    avec.pile_ou_face("flux-A", "un tirage intercalé dans A")
    b1b = avec.pile_ou_face("flux-B", "premier B")
    avec.entier("flux-A", "encore A", 100)
    b2b = avec.pile_ou_face("flux-B", "second B")

    assert (b1, b2) == (b1b, b2b)


def test_compteurs_par_flux():
    r = Rng(GRAINE)
    r.pile_ou_face("a", "m")
    r.pile_ou_face("a", "m")
    r.melanger("b", "m", [1, 2, 3])
    assert r.compteurs() == {"a": 2, "b": 1}


# --- Critère 2 : rejouabilité (centaine de parties simulées) -----------------


def _partie_simulee(r: Rng) -> dict:
    """Une « partie » : une suite représentative de tirages sur plusieurs flux.

    Faute d'un moteur d'actions (lots suivants), on simule le hasard d'une partie réelle :
    mélange des deux decks (R-4.1), pile ou face de début (R-4.7), puis des pile ou face
    d'états spéciaux (R-11.3/4/5) et un effet entier. L'« état final » est l'ensemble des
    résultats — c'est lui qui doit être identique d'un rejeu à l'autre.
    """
    etat: dict = {}
    etat["deck_A"] = r.melanger(flux_melange_deck("A"), "R-4.1 deck A", list(range(60)))
    etat["deck_B"] = r.melanger(flux_melange_deck("B"), "R-4.1 deck B", list(range(60)))
    etat["qui_commence"] = r.pile_ou_face(FLUX_QUI_COMMENCE, "R-4.7 qui commence")
    reveils = []
    for tour in range(10):
        reveils.append(r.pile_ou_face("etat:endormi:A", f"R-11.3 réveil tour {tour}"))
        reveils.append(r.pile_ou_face("etat:confus:B", f"R-11.5 confusion tour {tour}"))
    etat["reveils"] = reveils
    etat["des"] = [r.entier("effet:pioche", f"R-11 effet {k}", 20) for k in range(5)]
    return etat


def test_cent_parties_rejouees_a_graine_identique_donnent_un_etat_identique():
    """Critère : rejouer (graine + actions) redonne l'état final, octet pour octet."""
    for _ in range(100):
        graine = os.urandom(32)
        a = Rng(graine)
        b = Rng(graine)
        etat_a = _partie_simulee(a)
        etat_b = _partie_simulee(b)
        assert etat_a == etat_b
        # Le journal lui-même est reproduit à l'identique (jusqu'au sérialisé JSON).
        assert a.etat() == b.etat()


def test_graines_differentes_divergent():
    """Deux graines distinctes ne produisent pas la même partie (sinon la graine ne sert à rien)."""
    a = _partie_simulee(Rng(os.urandom(32)))
    b = _partie_simulee(Rng(os.urandom(32)))
    assert a != b


def test_round_trip_etat_rng():
    r = Rng(os.urandom(32))
    _partie_simulee(r)
    rejoue = Rng.depuis_etat(json.loads(json.dumps(r.etat())))
    assert rejoue.etat() == r.etat()
    assert rejoue.journal() == r.journal()


def test_depuis_etat_refuse_version_inconnue():
    with pytest.raises(ValueError, match="rng_version"):
        Rng.depuis_etat({"rng_version": 999, "graine": GRAINE.hex(), "journal": []})


# --- Critère 3 : vérification commit-reveal ----------------------------------


def test_engagement_puis_revelation():
    graine = os.urandom(32)
    empreinte = engagement(graine)  # publiée AVANT la partie
    assert verifier_engagement(graine, empreinte)  # révélée à la fin
    assert not verifier_engagement(os.urandom(32), empreinte)


def test_journal_honnete_se_verifie():
    r = Rng(os.urandom(32))
    _partie_simulee(r)
    graine = bytes.fromhex(r.graine_hex)
    assert verifier_journal(graine, r.journal()) == []


def test_verificateur_mord_sur_un_pile_ou_face_retourne():
    r = Rng(GRAINE)
    r.pile_ou_face(FLUX_QUI_COMMENCE, "R-4.7")
    journal = list(r.journal())
    t = journal[0]
    retourne = PILE if t.resultat == FACE else FACE
    journal[0] = Tirage(t.flux, t.indice, t.motif, t.genre, t.parametre, retourne)
    anomalies = verifier_journal(GRAINE, journal)
    assert anomalies and "correspond pas" in anomalies[0].probleme


def test_verificateur_mord_sur_un_melange_reordonne():
    r = Rng(GRAINE)
    r.melanger(flux_melange_deck("A"), "R-4.1", list(range(10)))
    journal = list(r.journal())
    t = journal[0]
    # Inverser la permutation enregistrée : un mélange « choisi » plutôt que tiré.
    truque = Tirage(t.flux, t.indice, t.motif, t.genre, t.parametre, tuple(reversed(t.resultat)))
    journal[0] = truque
    assert verifier_journal(GRAINE, journal)


def test_verificateur_mord_sur_un_tirage_efface():
    """Effacer le 1er tirage d'un flux laisse les suivants avec un indice hors séquence."""
    r = Rng(GRAINE)
    r.pile_ou_face("f", "premier")
    r.pile_ou_face("f", "second")
    journal = list(r.journal())
    del journal[0]  # il reste un tirage d'indice 1 alors qu'on attend 0
    anomalies = verifier_journal(GRAINE, journal)
    assert anomalies and "hors séquence" in anomalies[0].probleme


def test_verificateur_mord_sur_graine_changee():
    r = Rng(GRAINE)
    _partie_simulee(r)
    autre_graine = os.urandom(32)
    anomalies = verifier_journal(autre_graine, r.journal())
    assert anomalies  # quasi tous les tirages divergent sous une autre graine


def test_rejouer_tirage_reproduit_chaque_genre():
    r = Rng(GRAINE)
    r.pile_ou_face("f", "m")
    r.entier("f", "m", 50)
    r.melanger("f", "m", list(range(8)))
    for t in r.journal():
        assert rejouer_tirage(GRAINE, t) == t.resultat


# --- Sérialisation d'un tirage ----------------------------------------------


def test_tirage_round_trip_json():
    r = Rng(GRAINE)
    r.pile_ou_face("f", "pof")
    r.entier("f", "ent", 12)
    r.melanger("f", "mel", list(range(5)))
    for t in r.journal():
        assert tirage_depuis_json(json.loads(json.dumps(tirage_vers_json(t)))) == t


def test_tirage_depuis_json_refuse_genre_inconnu():
    with pytest.raises(ValueError, match="genre inconnu"):
        tirage_depuis_json(
            {
                "flux": "f",
                "indice": 0,
                "motif": "m",
                "genre": "brouette",
                "parametre": 2,
                "resultat": 1,
            }
        )


def test_rng_est_pur_pas_de_dependance_lourde():
    """Importer le module d'aléatoire ne tire aucune dépendance interdite."""
    import importlib
    import sys

    importlib.import_module("pbm_game.rng")
    interdits = {"fastapi", "sqlalchemy", "httpx", "requests", "boto3", "redis", "pbm_api"}
    assert not (interdits & set(sys.modules))


def test_distribution_pile_ou_face_equilibree():
    """Sanité statistique : sur beaucoup de tirages, face et pile sont proches de 50/50."""
    r = Rng(os.urandom(32))
    faces = sum(1 for k in range(2000) if r.pile_ou_face("sanite", f"t{k}") == FACE)
    assert 850 <= faces <= 1150  # bornes larges : on détecte un biais grossier, pas le bruit


__all__: list[str] = []
