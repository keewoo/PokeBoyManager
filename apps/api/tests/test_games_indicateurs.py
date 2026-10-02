"""Indicateurs d'affichage du plateau, câblage catalogue ↔ moteur — lot ``j-plateau-etat-visuel``.

Le moteur (pur) calcule PV restants et types ; c'est l'adaptateur
:mod:`pbm_api.games.indicateurs` qui lit le catalogue (``Card``) pour les lui fournir. On vérifie :

* ``catalogue_affichage`` lit bien PV (``hp``) et code d'élément (``element_type``) d'une carte,
  tolérant une ref absente (jamais une valeur inventée, D9) ;
* bout en bout (catalogue → :func:`pbm_game.sortie.enrichir_indicateurs`), un Actif reçoit des
  ``pv_restants`` **exacts** et des énergies **typées** — ce que l'écran dessinera sans recalcul.

Les propriétés fines du calcul (Outil qui ajoute des PV, plancher à 0) sont prouvées côté moteur
(``apps/game/tests/test_sortie_indicateurs.py``) ; ici on prouve le **câblage** à la base.
"""

from __future__ import annotations

import uuid

from pbm_game.sortie import enrichir_indicateurs, projeter
from pbm_game.state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

from pbm_api.games.indicateurs import catalogue_affichage, catalogue_pour_etat
from pbm_api.models import Card, Set


async def _carapuce_et_energie(db_session) -> tuple[Card, Card]:
    """Un Pokémon (Carapuce, 60 PV, Eau) et une Énergie Eau dans le catalogue de test."""
    set_row = Set(code=f"ind-{uuid.uuid4().hex[:8]}", name="Set indic", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    carapuce = Card(
        set_id=set_row.id,
        number="1",
        name="Carapuce",
        supertype="Pokémon",
        energy_type="water",
        element_type="water",
        hp=60,
        stage="Base",
        retreat_cost=1,
        prize_marker="ordinaire",
    )
    energie = Card(
        set_id=set_row.id,
        number="98",
        name="Énergie Eau",
        supertype="Énergie",
        energy_type="Normal",
        element_type="water",
        hp=None,
    )
    db_session.add_all([carapuce, energie])
    await db_session.flush()
    return carapuce, energie


async def test_catalogue_affichage_lit_pv_et_type(db_session):
    """PV depuis ``hp``, code d'élément depuis ``element_type`` ; une ref absente est omise."""
    carapuce, energie = await _carapuce_et_energie(db_session)
    ref_poke, ref_energie = str(carapuce.id), str(energie.id)
    catalogue = await catalogue_affichage(db_session, [ref_poke, ref_energie, "ref-fantome"])

    assert catalogue.pv_imprimes[ref_poke] == 60
    assert ref_energie not in catalogue.pv_imprimes  # une énergie n'a pas de PV
    assert catalogue.types[ref_poke] == "water"
    assert catalogue.types[ref_energie] == "water"
    assert "ref-fantome" not in catalogue.types  # ref inconnue : jamais devinée (D9)


async def test_enrichissement_bout_en_bout_pv_restants_et_energies_typees(db_session):
    """Catalogue → moteur : un Actif Carapuce à 20 dégâts montre 40 PV restants, énergies Eau."""
    carapuce, energie = await _carapuce_et_energie(db_session)
    actif = PokemonEnJeu(
        cartes=(Carte(instance_id="a-actif", ref=str(carapuce.id)),),
        energies=(
            Carte(instance_id="e1", ref=str(energie.id)),
            Carte(instance_id="e2", ref=str(energie.id)),
        ),
        compteurs_degats=20,
    )
    etat = EtatPartie(
        joueurs=(
            Joueur(id="alice", actif=actif),
            Joueur(id="bob", actif=PokemonEnJeu(cartes=(Carte("b-actif", str(carapuce.id)),))),
        ),
        tour=Tour(joueur_actif="alice", numero=1, phase=PHASE_PRINCIPALE),
    )

    catalogue = await catalogue_pour_etat(db_session, etat)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(
        vue,
        etat,
        pv_imprimes=catalogue.pv_imprimes,
        types=catalogue.types,
        registre=catalogue.registre,
    )

    actif_vu = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif_vu["pv_max"] == 60
    assert actif_vu["pv_restants"] == 40  # jamais « imprimés − dégâts » déguisé : un vrai calcul
    assert actif_vu["type"] == "water"
    assert [e["type"] for e in actif_vu["energies"]] == ["water", "water"]
