"""Moteur de résolution suspendable — demande à l'adversaire, imbrication, expiration, reprise F5.

Lot ``j-effets-choix``. Aucun effet de carte réel n'est scripté (D9) : on prouve le **mécanisme**
avec des résolveurs *jouets* (comme ``test_effets_pile``). Les règles servies sont R-9.3 (étape D,
choix imposés) et R-14.3 (abandon toujours permis, même une demande en cours).

Ce qui est démontré ici correspond aux critères d'acceptation du lot :

* une partie interrompue au milieu d'une demande **reprend exactement à cette demande, temps
  restant compris** (``test_reprise_apres_f5_par_serialisation``) ;
* les demandes **imbriquées** se résolvent dans le bon ordre et se voient au journal
  (``test_demandes_imbriquees_*``) ;
* l'**expiration** applique la réponse par défaut et l'**écrit** au journal
  (``test_expiration_applique_le_defaut_et_le_journalise``).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pbm_game.demandes.gestionnaire import Gestionnaire
from pbm_game.demandes.modele import CAT_CARTE, CAT_OUI_NON, NON, OUI, DemandeDecision, Reponse
from pbm_game.demandes.moteur import (
    EVT_DEMANDE_EMISE,
    EVT_DEMANDE_EXPIREE,
    EVT_DEMANDE_REPONDUE,
    ResolutionEnCours,
    demarrer_resolution,
    expirer,
    repondre,
    resoudre,
)
from pbm_game.effets.pile import EffetEnAttente, PileEffets, SourceEffet
from pbm_game.journal.modele import Evenement
from pbm_game.rng import Rng
from pbm_game.state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour


def _etat() -> EtatPartie:
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    alice = Joueur(id="alice", actif=base)
    bob = Joueur(id="bob", actif=base)
    return EtatPartie(
        joueurs=(alice, bob), tour=Tour(joueur_actif="alice", numero=3, phase="principale")
    )


def _effet(type_effet: str, libelle: str, **params) -> EffetEnAttente:
    return EffetEnAttente(
        type_effet=type_effet,
        source=SourceEffet(f"carte {libelle}", ref=f"r-{libelle}", instance_id=f"i-{libelle}"),
        regle="R-9.3",
        libelle=libelle,
        params=params,
    )


def _resolveur_carte(etat, effet, rng, gestionnaire):
    """Jouet : fait choisir UNE carte, puis inscrit le choix dans la défausse d'alice.

    L'inscription prouve que l'état **progresse** quand l'effet aboutit, et qu'il est **jeté** quand
    l'effet se suspend (la défausse ne gonfle qu'une fois, à la passe qui aboutit).
    """
    d = DemandeDecision(
        destinataire=effet.params["destinataire"],
        categorie=CAT_CARTE,
        source=effet.source,
        regle="R-9.3",
        libelle=effet.libelle,
        options=tuple(effet.params["options"]),
        obligatoire=effet.params.get("obligatoire", True),
        delai_ms=effet.params.get("delai_ms"),
        temps_restant_ms=effet.params.get("delai_ms"),
    )
    reponse = gestionnaire.demander(d)
    choisi = reponse.choix[0] if reponse.choix else "aucun"
    j0 = etat.joueurs[0]
    j0b = replace(j0, defausse=j0.defausse + (Carte(f"{effet.libelle}:{choisi}", "choisi"),))
    etat2 = replace(etat, joueurs=(j0b, etat.joueurs[1]))
    return (
        etat2,
        [Evenement("carte_choisie", {"libelle": effet.libelle, "choix": list(reponse.choix)})],
        [],
    )


_REG = {"carte": _resolveur_carte}


# --- Demande adressée à l'adversaire (mission 2) -----------------------------


def test_demande_peut_viser_l_adversaire_pendant_le_tour_de_l_autre():
    etat = _etat()  # c'est le tour d'alice
    pile = PileEffets().empiler(_effet("carte", "Appat", destinataire="bob", options=["b1", "b2"]))
    _, evts, res = resoudre(etat, pile, _REG, Rng(b"seed-0123456789a"), Gestionnaire())
    assert res is not None
    assert res.demande.destinataire == "bob"  # l'adversaire décide, en plein tour d'alice
    assert res.demande.id == "d0"
    assert [e.type for e in evts] == [EVT_DEMANDE_EMISE]


def test_reponse_reprend_la_resolution_et_applique_le_choix():
    etat = _etat()
    pile = PileEffets().empiler(_effet("carte", "Appat", destinataire="bob", options=["b1", "b2"]))
    rng = Rng(b"seed-0123456789a")
    etat1, _ = demarrer_resolution(etat, pile, rng, registre=_REG)
    assert (
        etat1.resolution is not None and etat1.joueurs[0].defausse == ()
    )  # rien joué tant qu'on attend
    etat2, evts = repondre(etat1, Reponse("d0", ("b2",)), rng, registre=_REG)
    assert etat2.resolution is None
    assert etat2.joueurs[0].defausse[-1].instance_id == "Appat:b2"
    assert [e.type for e in evts][0] == EVT_DEMANDE_REPONDUE


def test_reponse_hors_ensemble_refusee():
    etat = _etat()
    pile = PileEffets().empiler(_effet("carte", "Appat", destinataire="bob", options=["b1", "b2"]))
    rng = Rng(b"seed-0123456789a")
    etat1, _ = demarrer_resolution(etat, pile, rng, registre=_REG)
    with pytest.raises(ValueError, match="attendu un seul id"):
        repondre(etat1, Reponse("d0", ("b9",)), rng, registre=_REG)


# --- Reprise après un F5, au milieu de la demande (mission 5, critère 1) ------


def test_reprise_apres_f5_par_serialisation_garde_le_temps_restant():
    from pbm_game.state.serialisation import depuis_json, vers_json

    etat = _etat()
    pile = PileEffets().empiler(
        _effet("carte", "Appat", destinataire="bob", options=["b1", "b2"], delai_ms=30000)
    )
    etat1, _ = demarrer_resolution(etat, pile, Rng(b"seed-0123456789a"), registre=_REG)
    # On fait "tomber" un peu d'horloge, comme le ferait l'adaptateur temps réel avant la coupure.
    res = etat1.resolution
    etat1 = replace(etat1, resolution=replace(res, demande=res.demande.avec_temps_restant(12000)))

    repris = depuis_json(vers_json(etat1))
    assert repris == etat1  # la demande revient intacte…
    assert repris.resolution.demande.temps_restant_ms == 12000  # …temps restant compris

    etat2, _ = repondre(repris, Reponse("d0", ("b1",)), Rng(b"seed-0123456789a"), registre=_REG)
    assert etat2.resolution is None
    assert etat2.joueurs[0].defausse[-1].instance_id == "Appat:b1"


def test_serialisation_resolution_aller_retour():
    etat = _etat()
    pile = PileEffets().empiler(_effet("carte", "Appat", destinataire="bob", options=["b1"]))
    etat1, _ = demarrer_resolution(etat, pile, Rng(b"seed-0123456789a"), registre=_REG)
    assert ResolutionEnCours.depuis_json(etat1.resolution.en_json()) == etat1.resolution


# --- Demandes imbriquées (mission 5, critère 2) ------------------------------


def _resolveur_parent(etat, effet, rng, gestionnaire):
    """Jouet : demande oui/non, puis **empile** un effet « enfant » qui demandera à son tour."""
    d = DemandeDecision(
        destinataire=effet.params["destinataire"],
        categorie=CAT_OUI_NON,
        source=effet.source,
        regle="R-9.3",
        libelle="parent",
        options=(OUI, NON),
    )
    reponse = gestionnaire.demander(d)
    enfant = _effet(
        "carte", "enfant", destinataire=effet.params["destinataire"], options=["e1", "e2"]
    )
    return etat, [Evenement("parent_fait", {"choix": list(reponse.choix)})], [enfant]


def test_demandes_imbriquees_se_resolvent_dans_le_bon_ordre_et_au_journal():
    reg = {"carte": _resolveur_carte, "racine": _resolveur_parent}
    etat = _etat()
    pile = PileEffets().empiler(_effet("racine", "racine", destinataire="alice"))
    rng = Rng(b"seed-0123456789a")

    etat1, evts1 = demarrer_resolution(etat, pile, rng, registre=reg)
    # Première demande : le parent (oui/non), id d0.
    assert etat1.resolution.demande.id == "d0"
    assert etat1.resolution.demande.categorie == CAT_OUI_NON
    assert [e.type for e in evts1] == [EVT_DEMANDE_EMISE]

    etat2, evts2 = repondre(etat1, Reponse("d0", (OUI,)), rng, registre=reg)
    # Le parent aboutit, empile l'enfant, qui demande à son tour : seconde demande, id d1.
    assert etat2.resolution.demande.id == "d1"
    assert etat2.resolution.demande.categorie == CAT_CARTE
    types2 = [e.type for e in evts2]
    assert EVT_DEMANDE_REPONDUE in types2  # d0 répondue
    assert "parent_fait" in types2  # le parent a bien produit son événement, une seule fois
    assert types2[-1] == EVT_DEMANDE_EMISE  # d1 posée

    etat3, evts3 = repondre(etat2, Reponse("d1", ("e2",)), rng, registre=reg)
    assert etat3.resolution is None
    assert etat3.joueurs[0].defausse[-1].instance_id == "enfant:e2"
    assert [e.type for e in evts3][0] == EVT_DEMANDE_REPONDUE


# --- Expiration → réponse par défaut → journal (mission 3, critère 3) ---------


def test_expiration_applique_le_defaut_et_le_journalise():
    etat = _etat()
    pile = PileEffets().empiler(
        _effet("carte", "Appat", destinataire="bob", options=["b1", "b2"], delai_ms=30000)
    )
    rng = Rng(b"seed-0123456789a")
    etat1, _ = demarrer_resolution(etat, pile, rng, registre=_REG)
    # Personne n'a répondu : le délai expire. La réponse par défaut (1re option, car obligatoire)
    # est appliquée ET écrite au journal — jamais un abandon muet.
    etat2, evts = expirer(etat1, rng, registre=_REG)
    assert etat2.resolution is None
    expirees = [e for e in evts if e.type == EVT_DEMANDE_EXPIREE]
    assert expirees and expirees[0].donnees["choix"] == ["b1"]
    assert etat2.joueurs[0].defausse[-1].instance_id == "Appat:b1"


def test_expiration_d_un_effet_facultatif_abandonne_proprement():
    etat = _etat()
    pile = PileEffets().empiler(
        _effet("carte", "Bonus", destinataire="bob", options=["b1"], obligatoire=False)
    )
    rng = Rng(b"seed-0123456789a")
    etat1, _ = demarrer_resolution(etat, pile, rng, registre=_REG)
    etat2, evts = expirer(etat1, rng, registre=_REG)
    assert etat2.resolution is None
    expirees = [e for e in evts if e.type == EVT_DEMANDE_EXPIREE]
    assert expirees and expirees[0].donnees["choix"] == []  # abandon de l'effet facultatif
    assert etat2.joueurs[0].defausse[-1].instance_id == "Bonus:aucun"


# --- Déterminisme de l'aléatoire au re-déroulé (piège de la section 5) --------


def _resolveur_pile_puis_carte(etat, effet, rng, gestionnaire):
    """Tire un pile ou face **avant** de demander — pour éprouver le retour en arrière de l'aléa."""
    face = rng.pile_ou_face("demande:test", "avant le choix")
    d = DemandeDecision(
        destinataire="alice",
        categorie=CAT_CARTE,
        source=effet.source,
        regle="R-9.3",
        libelle="apres pile",
        options=("c1", "c2"),
    )
    reponse = gestionnaire.demander(d)
    return etat, [Evenement("resultat", {"face": face, "choix": list(reponse.choix)})], []


def test_re_deroule_ne_rejoue_pas_l_aleatoire():
    reg = {"pf": _resolveur_pile_puis_carte}
    reference = Rng(b"graine-pf-00000a").pile_ou_face("demande:test", "avant le choix")

    etat = _etat()
    pile = PileEffets().empiler(_effet("pf", "pf"))
    rng = Rng(b"graine-pf-00000a")
    etat1, _ = demarrer_resolution(etat, pile, rng, registre=reg)
    # La suspension a ramené l'aléatoire en arrière : aucun tirage ne subsiste pour ce flux.
    assert [t for t in rng.journal() if t.flux == "demande:test"] == []

    etat2, evts = repondre(etat1, Reponse("d0", ("c1",)), rng, registre=reg)
    resultat = [e for e in evts if e.type == "resultat"][0]
    assert resultat.donnees["face"] == reference  # même position → même tirage
    # Un seul tirage au total pour ce flux : il n'a PAS été compté deux fois (anti-triche).
    assert len([t for t in rng.journal() if t.flux == "demande:test"]) == 1


# --- Rng.restaurer (brique du re-déroulé) ------------------------------------


def test_rng_restaurer_ramene_en_arriere_a_l_identique():
    rng = Rng(b"graine-xyz-00000")
    instantane = rng.etat()
    a = rng.pile_ou_face("flux", "1")
    rng.restaurer(instantane)
    b = rng.pile_ou_face("flux", "1")
    assert a == b  # même indice de flux → même tirage
    assert len([t for t in rng.journal() if t.flux == "flux"]) == 1  # un seul, pas deux


def test_rng_restaurer_refuse_une_autre_graine():
    rng = Rng(b"graine-xyz-00000")
    autre = Rng(b"autre-graine-000").etat()
    with pytest.raises(ValueError, match="graine différente"):
        rng.restaurer(autre)


# --- Garde : rien d'autre qu'une réponse pendant une demande (mission 4) ------


def test_type_d_effet_inconnu_refuse_d9():
    etat = _etat()
    pile = PileEffets().empiler(_effet("inexistant", "x", destinataire="bob", options=["b1"]))
    with pytest.raises(ValueError, match="jamais approximé"):
        resoudre(etat, pile, _REG, Rng(b"seed-0123456789a"), Gestionnaire())


def test_repondre_sans_demande_en_cours_refuse():
    etat = _etat()
    with pytest.raises(ValueError, match="Aucune résolution"):
        repondre(etat, Reponse("d0", ("x",)), Rng(b"seed-0123456789a"), registre=_REG)
