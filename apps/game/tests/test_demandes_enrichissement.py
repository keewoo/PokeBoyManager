"""Enrichissement d'une demande avec les cartes à afficher (lot ``j-plateau-decisions``).

Une demande de catégorie carte porte des ``options`` qui sont des **instance_id** nus. Pour que
l'écran rende une vraie carte — et laisse **chercher** dans une pioche de soixante cartes —
l'adaptateur API résout chaque option en ``{id, ref, nom, type}`` via :func:`enrichir_demande`
(règle R-9.3 : c'est au destinataire de choisir, donc il faut lui montrer **quoi** choisir).

La non-fuite reste tenue par la projection : un ensemble **caché** ne porte pas d'``options``, donc
rien n'est enrichi et aucune identité ne sort.
"""

from __future__ import annotations

import json

from pbm_game.demandes.modele import CAT_CARTES, CAT_OUI_NON, DemandeDecision
from pbm_game.demandes.moteur import ResolutionEnCours
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.sortie.demande import enrichir_demande, refs_demande
from pbm_game.state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour
from pbm_game.state.projection import vue


def _etat_pioche_a_fouiller(*, categorie=CAT_CARTES, options=("c1", "c2", "c3")) -> EtatPartie:
    """Un état où ``bob`` doit choisir des cartes de sa **pioche** (zone cachée) — R-9.3.

    Les cartes désignées par les options vivent réellement dans la pioche de bob, avec une ``ref``
    catalogue ; c'est ce qui permet de résoudre chaque option en carte affichable.
    """
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    pioche = (
        Carte("c1", "ref-dracaufeu"),
        Carte("c2", "ref-bulbizarre"),
        Carte("c3", "ref-dracaufeu"),
    )
    alice = Joueur(id="alice", actif=base)
    bob = Joueur(id="bob", actif=base, pioche=pioche)
    demande = DemandeDecision(
        destinataire="bob",
        categorie=categorie,
        source=SourceEffet("Professeur", ref="r-prof", instance_id="i-prof"),
        regle="R-9.3",
        libelle="Choisis une carte de ta pioche",
        options=tuple(options),
        minimum=1,
        maximum=2 if categorie == CAT_CARTES else 1,
    ).avec_id("d0")
    effet = EffetEnAttente("dsl", SourceEffet("Professeur"), "R-9.3", "Professeur")
    resolution = ResolutionEnCours(pile=PileEffets().empiler(effet), demande=demande)
    return EtatPartie(
        joueurs=(alice, bob),
        tour=Tour(joueur_actif="bob", numero=3, phase="principale"),
        resolution=resolution,
    )


NOMS = {"ref-dracaufeu": "Dracaufeu", "ref-bulbizarre": "Bulbizarre"}
TYPES = {"ref-dracaufeu": "fire", "ref-bulbizarre": "grass"}


def test_refs_demande_releve_les_cartes_d_une_zone_cachee():
    # R-9.3 : les cartes à choisir sont dans la pioche — refs_en_jeu ne les verrait pas, mais
    # refs_demande, si, pour que l'API charge leurs nom/type du catalogue.
    etat = _etat_pioche_a_fouiller()
    assert refs_demande(etat) == {"ref-dracaufeu", "ref-bulbizarre"}


def test_enrichir_demande_resout_chaque_option_en_carte_affichable():
    etat = _etat_pioche_a_fouiller()
    v = vue(etat, "bob")  # projection : bob (destinataire) reçoit les options
    enrichir_demande(v, etat, noms=NOMS, types=TYPES)
    cartes = v["demande"]["options_cartes"]
    assert [c["id"] for c in cartes] == ["c1", "c2", "c3"]  # l'ordre des options est préservé
    assert cartes[0] == {"id": "c1", "ref": "ref-dracaufeu", "nom": "Dracaufeu", "type": "fire"}
    assert cartes[1]["nom"] == "Bulbizarre" and cartes[1]["type"] == "grass"


def test_enrichir_demande_retombe_sur_la_ref_quand_le_nom_est_inconnu():
    # D9 : jamais de nom inventé — à défaut de catalogue, la ref sert d'étiquette distinctive.
    etat = _etat_pioche_a_fouiller()
    v = vue(etat, "bob")
    enrichir_demande(v, etat, noms={}, types={})
    cartes = v["demande"]["options_cartes"]
    assert cartes[0]["nom"] == "ref-dracaufeu" and cartes[0]["type"] is None


def test_enrichir_demande_ne_touche_pas_la_vue_de_l_autre_joueur():
    # alice n'est pas destinataire : sa vue n'a pas d'options, donc rien à enrichir, rien ne fuit.
    etat = _etat_pioche_a_fouiller()
    v = vue(etat, "alice")
    enrichir_demande(v, etat, noms=NOMS, types=TYPES)
    assert "options_cartes" not in v["demande"]
    assert "c1" not in json.dumps(v, ensure_ascii=False)


def test_un_ensemble_cache_ne_laisse_rien_enrichir():
    # ensemble_cache : la projection ne livre que options_nombre — enrichir ne doit rien ajouter.
    from dataclasses import replace

    etat = _etat_pioche_a_fouiller()
    demande_cachee = replace(etat.resolution.demande, ensemble_cache=True)
    resolution = replace(etat.resolution, demande=demande_cachee)
    etat2 = replace(etat, resolution=resolution)
    v = vue(etat2, "bob")
    assert "options" not in v["demande"] and v["demande"]["options_nombre"] == 3
    enrichir_demande(v, etat2, noms=NOMS, types=TYPES)
    assert "options_cartes" not in v["demande"]


def test_des_options_non_cartes_restent_telles_quelles():
    # Une demande oui/non n'a pas d'options-cartes : rien à résoudre, aucune clé options_cartes.
    etat = _etat_pioche_a_fouiller(categorie=CAT_OUI_NON, options=("oui", "non"))
    v = vue(etat, "bob")
    enrichir_demande(v, etat, noms=NOMS, types=TYPES)
    assert "options_cartes" not in v["demande"]
    assert v["demande"]["options"] == ["oui", "non"]
    assert refs_demande(etat) == set()  # aucune option ne désigne une carte de l'état
