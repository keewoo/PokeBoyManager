"""L'orchestrateur joue une partie complète, contrôle les invariants, et nomme toute anomalie.

Couvre les critères « jouées de la mise en place à la victoire », « reproductible depuis sa
graine », et la **détection** elle-même (une campagne verte ne vaut que si la machine à détecter
mord vraiment) :

* une poignée de graines se terminent **saines**, invariants tenus, rejeu identique (R-4, R-14) ;
* la détection d'une **partie sans fin** mord (plafond de coups bas) et **archive la graine** ;
* le filtre d'invariants est **étroit** : le transitoire « Actif K.O., banc non vide » (R-3.3,
  R-8.7) est exempté, mais une vraie violation (carte en double) passe et devient une anomalie.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pbm_game.journal import empreinte, rejouer
from pbm_game.state import PHASE_PRINCIPALE, Carte, EtatPartie, Joueur, PokemonEnJeu, Tour
from pbm_sim.orchestrateur import (
    ANOMALIE_PARTIE_SANS_FIN,
    _violations_significatives,
    jouer_partie,
)

GRAINES = [f"orch:{i}" for i in range(12)]


@pytest.mark.parametrize("graine", GRAINES)
def test_une_partie_se_termine_saine_et_se_rejoue_identique(graine):
    """De la mise en place à la victoire (R-4 → R-14), sans anomalie, et rejouable à l'identique."""
    r = jouer_partie(graine, garder_partie=True)
    assert r.terminee, f"{graine} ne s'est pas terminée (tours={r.tours}, pas={r.pas})"
    assert not r.anomalies, f"{graine} : anomalies {[a.message for a in r.anomalies]}"
    assert r.raison_fin is not None
    etat_rejoue, _ = rejouer(r.partie)
    # Le rejeu du journal redonne l'état final : son empreinte est celle portée par la dernière
    # entrée du journal (« tout est rejouable »).
    assert empreinte(etat_rejoue) == r.partie.entrees[-1].empreinte


def test_la_meme_graine_redonne_exactement_la_meme_partie():
    """Déterminisme : deux exécutions d'une graine donnent la même issue et la même empreinte."""
    a = jouer_partie("determinisme-1", garder_partie=True)
    b = jouer_partie("determinisme-1", garder_partie=True)
    cle = lambda r: (r.tours, r.pas, r.vainqueur, r.raison_fin)  # noqa: E731
    assert cle(a) == cle(b)
    assert a.partie.entrees[-1].empreinte == b.partie.entrees[-1].empreinte


def test_la_detection_de_partie_sans_fin_mord_et_archive_la_graine():
    """Critère de confiance : un plafond bas déclenche l'anomalie, avec la graine à rejouer.

    Sans cette détection, une boucle d'effets (le risque nommé par la fiche) passerait inaperçue :
    on prouve ici qu'elle NE passe PAS inaperçue.
    """
    r = jouer_partie("orch:0", max_pas=5)
    assert not r.saine
    types = {a.type for a in r.anomalies}
    assert ANOMALIE_PARTIE_SANS_FIN in types
    assert all(a.graine == "orch:0" for a in r.anomalies)  # reproductible


def test_le_filtre_d_invariants_exempte_la_promotion_mais_pas_une_vraie_faute():
    """R-3.3/R-8.7 — « Actif K.O., banc non vide » est exempté ; une carte en double ne l'est pas.

    L'état est minimal (pas 60 cartes), donc le contrôle de total signalera autre chose — ce n'est
    pas ce qu'on teste : on vérifie **précisément** que la violation de promotion disparaît du
    filtre, et qu'une carte présente dans deux zones y reste.
    """
    base = Carte(instance_id="A-0", ref="pika")
    banc_pk = PokemonEnJeu(cartes=(Carte(instance_id="A-1", ref="pika"),))
    j_promo = Joueur(id="A", actif=None, banc=(banc_pk,))
    adv = Joueur(id="B", actif=PokemonEnJeu(cartes=(base,)))
    etat_promo = EtatPartie(
        joueurs=(j_promo, adv), tour=Tour(joueur_actif="B", numero=2, phase=PHASE_PRINCIPALE)
    )
    # Le transitoire de promotion est exempté : plus aucune violation « banc non vide sans Actif ».
    assert not any("banc non vide sans Actif" in v for v in _violations_significatives(etat_promo))

    # Une carte présente dans deux zones est une vraie faute : elle doit, elle, passer le filtre.
    doublon = Carte(instance_id="A-1", ref="pika")  # même instance_id que le banc
    j_double = replace(j_promo, actif=PokemonEnJeu(cartes=(doublon,)))
    etat_double = replace(etat_promo, joueurs=(j_double, adv))
    assert any("double" in v.lower() for v in _violations_significatives(etat_double))
