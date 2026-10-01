"""Projection par joueur ``vue(etat, joueur)`` — le cœur anti-triche, lot j-modele-etat.

Le serveur fait autorité : un joueur ne doit jamais apprendre la main de l'adversaire,
ni l'ordre d'une pioche, ni l'identité des récompenses. Le test central parcourt la
structure produite à la recherche des identifiants des zones cachées : il ne doit en
trouver **aucun**.
"""

from __future__ import annotations

import json

import pytest
from fabrique_etats import fabrique_etat

from pbm_game.state import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour, vue


def _cartes_interdites_pour(etat: EtatPartie, demandeur: str) -> set[str]:
    """Tous les identifiants (instance_id et ref) qu'un joueur n'a PAS le droit de voir.

    = les pioches des deux joueurs (ordre + identités), les récompenses des deux joueurs
    (face cachée), et la main de l'ADVERSAIRE.
    """
    interdits: set[str] = set()
    for j in etat.joueurs:
        for c in j.pioche:
            interdits |= {c.instance_id, c.ref}
        for c in j.recompenses:
            interdits |= {c.instance_id, c.ref}
        if j.id != demandeur:
            for c in j.main:
                interdits |= {c.instance_id, c.ref}
    return interdits


def test_vue_ne_laisse_fuir_aucune_carte_cachee():
    """Sur 300 états aléatoires, aucune carte cachée n'apparaît dans la vue d'un joueur."""
    for seed in range(300):
        etat = fabrique_etat(seed)
        for demandeur in ("alice", "bob"):
            texte = json.dumps(vue(etat, demandeur))
            for interdit in _cartes_interdites_pour(etat, demandeur):
                assert interdit not in texte, (
                    f"Fuite seed={seed}, vue de {demandeur} : « {interdit} » visible."
                )


def test_vue_montre_sa_propre_main():
    """Un joueur voit l'identité de ses propres cartes en main."""
    main = (Carte("m1", "ref-m1"), Carte("m2", "ref-m2"))
    j = Joueur(id="alice", main=main)
    etat = EtatPartie(joueurs=(j, Joueur(id="bob")), tour=Tour("alice", 1, "principale"))
    v = vue(etat, "alice")
    moi = next(x for x in v["joueurs"] if x["id"] == "alice")
    refs = {c["ref"] for c in moi["main"]}
    assert refs == {"ref-m1", "ref-m2"}


def test_vue_cache_la_main_adverse_en_nombre():
    """La main adverse n'est connue que par son nombre, jamais par ses identités."""
    adverse = Joueur(id="bob", main=(Carte("x", "ref-x"), Carte("y", "ref-y")))
    etat = EtatPartie(joueurs=(Joueur(id="alice"), adverse), tour=Tour("alice", 1, "principale"))
    v = vue(etat, "alice")
    bob = next(x for x in v["joueurs"] if x["id"] == "bob")
    assert bob["main_nombre"] == 2
    assert "main" not in bob


def test_vue_reduit_pioche_et_recompenses_au_nombre():
    """Pioche (ordre caché) et récompenses (face cachée) : nombre seulement, pour soi aussi."""
    j = Joueur(
        id="alice",
        pioche=(Carte("p1", "ref-p1"), Carte("p2", "ref-p2"), Carte("p3", "ref-p3")),
        recompenses=(Carte("r1", "ref-r1"), Carte("r2", "ref-r2")),
    )
    etat = EtatPartie(joueurs=(j, Joueur(id="bob")), tour=Tour("alice", 1, "principale"))
    v = vue(etat, "alice")
    moi = next(x for x in v["joueurs"] if x["id"] == "alice")
    assert moi["pioche_nombre"] == 3
    assert moi["recompenses_nombre"] == 2
    assert "pioche" not in moi and "recompenses" not in moi
    # Même sa propre pioche ne révèle pas son ordre.
    assert "ref-p1" not in json.dumps(v)


def test_vue_expose_les_zones_publiques():
    """Actif, banc et défausse sont publics : leurs identités sont visibles."""
    actif = PokemonEnJeu(cartes=(Carte("a1", "ref-a1"),), energies=(Carte("e1", "ref-e1"),))
    j = Joueur(id="bob", actif=actif, defausse=(Carte("d1", "ref-d1"),))
    etat = EtatPartie(joueurs=(Joueur(id="alice"), j), tour=Tour("alice", 1, "principale"))
    texte = json.dumps(vue(etat, "alice"))  # alice regarde l'Actif public de bob
    assert "ref-a1" in texte and "ref-e1" in texte and "ref-d1" in texte


def test_vue_refuse_un_joueur_hors_partie():
    etat = EtatPartie(
        joueurs=(Joueur(id="alice"), Joueur(id="bob")),
        tour=Tour("alice", 1, "principale"),
    )
    with pytest.raises(ValueError, match="participe"):
        vue(etat, "carol")
