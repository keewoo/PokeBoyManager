"""Projection d'une demande de décision par joueur — qui voit quoi, et ce qui ne fuit jamais.

Lot ``j-effets-choix``. Qu'une décision soit en attente, et de **qui**, est public (la partie est
en pause, personne ne reste devant un écran muet). Mais les **options** sont réservées au
destinataire — et, pour un ensemble **caché** (« choisis dans la main adverse »), réduites à un
**nombre**, jamais les identités : la même frontière anti-triche que pour les zones cachées.
"""

from __future__ import annotations

from dataclasses import replace

from pbm_game.demandes.modele import CAT_CARTE, DemandeDecision
from pbm_game.demandes.moteur import ResolutionEnCours
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour
from pbm_game.state.projection import vue


def _etat_avec_demande(*, ensemble_cache: bool) -> EtatPartie:
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    alice = Joueur(id="alice", actif=base)
    bob = Joueur(id="bob", actif=base)
    demande = DemandeDecision(
        destinataire="bob",
        categorie=CAT_CARTE,
        source=SourceEffet("Appât", ref="r-appat", instance_id="i-appat"),
        regle="R-9.3",
        libelle="Choisis une carte",
        options=("secret-1", "secret-2", "secret-3"),
        ensemble_cache=ensemble_cache,
        delai_ms=30000,
        temps_restant_ms=12000,
    ).avec_id("d0")
    effet = EffetEnAttente("dsl", SourceEffet("Appât"), "R-9.3", "Appât")
    resolution = ResolutionEnCours(pile=PileEffets().empiler(effet), demande=demande)
    return EtatPartie(
        joueurs=(alice, bob),
        tour=Tour(joueur_actif="alice", numero=3, phase="principale"),
        resolution=resolution,
    )


def test_les_deux_joueurs_voient_qu_une_demande_attend_et_de_qui():
    etat = _etat_avec_demande(ensemble_cache=False)
    for jid in ("alice", "bob"):
        d = vue(etat, jid)["demande"]
        assert d["destinataire"] == "bob"
        assert d["libelle"] == "Choisis une carte"
        assert d["temps_restant_ms"] == 12000  # le temps restant est public (horloge à l'écran)


def test_seul_le_destinataire_voit_les_options_d_un_ensemble_visible():
    etat = _etat_avec_demande(ensemble_cache=False)
    vue_bob = vue(etat, "bob")["demande"]
    assert vue_bob["options"] == ["secret-1", "secret-2", "secret-3"]  # le destinataire choisit
    vue_alice = vue(etat, "alice")["demande"]
    assert "options" not in vue_alice  # l'autre joueur ne reçoit pas la liste


def test_un_ensemble_cache_ne_livre_qu_un_nombre_meme_au_destinataire():
    etat = _etat_avec_demande(ensemble_cache=True)
    vue_bob = vue(etat, "bob")["demande"]
    assert "options" not in vue_bob  # jamais les identités d'un ensemble caché
    assert vue_bob["options_nombre"] == 3
    # Aucune identité secrète ne doit apparaître où que ce soit dans la vue.
    import json

    texte = json.dumps(vue(etat, "bob"), ensure_ascii=False)
    assert "secret-1" not in texte and "secret-2" not in texte and "secret-3" not in texte


def test_sans_demande_la_vue_n_a_pas_de_cle_demande():
    etat = replace(_etat_avec_demande(ensemble_cache=False), resolution=None)
    assert "demande" not in vue(etat, "alice")
