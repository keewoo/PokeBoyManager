"""Indicateurs d'affichage du plateau — ``pbm_game.sortie.enrichir_indicateurs`` (lot
``j-plateau-etat-visuel``).

On vérifie ce que l'écran doit pouvoir dessiner **sans recalcul** :

* les **PV restants** sont exacts, y compris quand un Outil **ajoute des PV** (R-13.1) — c'est le
  risque nommé par la fiche : ne jamais afficher « PV imprimés − dégâts » ;
* les dégâts restent des **compteurs** (R-10.4), les PV restants ne descendent jamais sous 0 ;
* chaque **énergie** et l'**Outil** portent leur type (code d'élément), pour une pastille typée ;
* un PV **inconnu** du catalogue n'est **pas deviné** (D9) : l'indicateur est absent, pas faux.

Le moteur est **pur** : la fonction ne reçoit que des données (PV et types résolus par le service),
jamais le catalogue. ``test_effets_purete`` garde cette pureté côté effets continus.
"""

from __future__ import annotations

from pbm_game.effets.continus import PORTEE_OUTIL, EffetContinu, RegistreContinus
from pbm_game.effets.pile import SourceEffet
from pbm_game.sortie import enrichir_indicateurs, projeter, refs_en_jeu
from pbm_game.state.modele import (
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

PIKACHU = "base1-25-pikachu"  # R-13.1 : 60 PV imprimés dans ce test
SALAMECHE = "base1-46-salameche"
ENERGIE_FEU = "base1-98-energie-feu"
OUTIL_PV = "tool-ceinture-pv"


def _etat(
    *,
    degats_alice: int = 20,
    outil: Carte | None = None,
    energies: tuple[Carte, ...] = (),
) -> EtatPartie:
    """Un état minimal : alice a un Actif Pikachu (avec dégâts/énergies/Outil), bob un Actif nu."""
    actif_alice = PokemonEnJeu(
        cartes=(Carte(instance_id="a-actif", ref=PIKACHU),),
        energies=energies,
        outil=outil,
        compteurs_degats=degats_alice,
    )
    actif_bob = PokemonEnJeu(cartes=(Carte(instance_id="b-actif", ref=SALAMECHE),))
    return EtatPartie(
        joueurs=(
            Joueur(id="alice", actif=actif_alice),
            Joueur(id="bob", actif=actif_bob),
        ),
        tour=Tour(joueur_actif="alice", numero=1, phase=PHASE_PRINCIPALE),
    )


def _registre_outil_plus_20() -> RegistreContinus:
    """Un Outil scripté qui **ajoute 20 PV** à son porteur (R-13.1) — pour prouver que ``pv_max``
    suit l'Outil, exactement comme le fera la résolution des K.O."""

    def producteur(etat, ref, cible):
        return [
            EffetContinu(
                libelle="Ceinture de vigueur (+20 PV)",
                regle="R-13.1",
                source=SourceEffet(libelle="Ceinture", ref=ref, instance_id=None),
                portee=PORTEE_OUTIL,
                cible=cible,
                pv=20,
            )
        ]

    return {OUTIL_PV: producteur}


def test_pv_restants_exacts_sans_outil():
    """60 PV imprimés, 20 de dégâts → 40 PV restants (R-13.1 / R-10.4)."""
    etat = _etat(degats_alice=20)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(vue, etat, pv_imprimes={PIKACHU: 60}, types={})
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["pv_max"] == 60
    assert actif["pv_restants"] == 40
    assert actif["compteurs_degats"] == 20  # les dégâts restent des compteurs (R-10.4)


def test_pv_max_suit_un_outil_qui_ajoute_des_pv():
    """Un Outil +20 PV déplace le seuil de K.O. : 60 → 80 PV max, donc 60 restants (R-13.1).

    C'est le critère d'acceptation du lot : afficher ``imprimés − dégâts`` (= 40) mentirait.
    """
    outil = Carte(instance_id="a-outil", ref=OUTIL_PV)
    etat = _etat(degats_alice=20, outil=outil)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(
        vue,
        etat,
        pv_imprimes={PIKACHU: 60},
        types={},
        registre=_registre_outil_plus_20(),
    )
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["pv_max"] == 80, "les PV de l'Outil doivent compter dans le maximum"
    assert actif["pv_restants"] == 60


def test_retirer_loutil_fait_redescendre_le_pv_max():
    """Sans Outil (ou Outil non scripté), pv_max = PV imprimés seuls — pas d'approximation."""
    etat = _etat(degats_alice=20)  # pas d'Outil
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(
        vue, etat, pv_imprimes={PIKACHU: 60}, types={}, registre=_registre_outil_plus_20()
    )
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["pv_max"] == 60
    assert actif["pv_restants"] == 40


def test_pv_restants_jamais_negatifs():
    """Des dégâts au-delà des PV donnent 0 restant, jamais un nombre négatif."""
    etat = _etat(degats_alice=100)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(vue, etat, pv_imprimes={PIKACHU: 60}, types={})
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["pv_restants"] == 0


def test_pv_inconnu_du_catalogue_nest_pas_devine():
    """PV imprimés absents → aucun ``pv_max``/``pv_restants`` (D9) : absent, jamais faux."""
    etat = _etat(degats_alice=20)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(vue, etat, pv_imprimes={}, types={})
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert "pv_max" not in actif
    assert "pv_restants" not in actif
    assert actif["compteurs_degats"] == 20  # les dégâts restent lisibles


def test_type_des_energies_et_du_pokemon():
    """Chaque énergie et le Pokémon portent leur code d'élément, pour une pastille typée."""
    energies = (
        Carte(instance_id="e1", ref=ENERGIE_FEU),
        Carte(instance_id="e2", ref=ENERGIE_FEU),
    )
    etat = _etat(energies=energies)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(
        vue,
        etat,
        pv_imprimes={PIKACHU: 60},
        types={PIKACHU: "lightning", ENERGIE_FEU: "fire"},
    )
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["type"] == "lightning"
    assert [e["type"] for e in actif["energies"]] == ["fire", "fire"]


def test_type_inconnu_reste_none_jamais_invente():
    """Un type absent du catalogue reste ``None`` : couleur neutre côté écran, jamais inventée."""
    energies = (Carte(instance_id="e1", ref=ENERGIE_FEU),)
    etat = _etat(energies=energies)
    vue = projeter(etat, pour="alice")["vue"]
    enrichir_indicateurs(vue, etat, pv_imprimes={PIKACHU: 60}, types={})
    actif = next(j for j in vue["joueurs"] if j["id"] == "alice")["actif"]
    assert actif["type"] is None
    assert actif["energies"][0]["type"] is None


def test_refs_en_jeu_ne_releve_que_le_visible():
    """``refs_en_jeu`` relève les cartes visibles (Pokémon, énergie, Outil), pas une zone cachée."""
    outil = Carte(instance_id="a-outil", ref=OUTIL_PV)
    energies = (Carte(instance_id="e1", ref=ENERGIE_FEU),)
    etat = _etat(outil=outil, energies=energies)
    # Une pioche cachée ne doit pas apparaître dans les refs d'affichage.
    alice = etat.joueurs[0]
    alice_avec_pioche = Joueur(
        id="alice",
        actif=alice.actif,
        pioche=(Carte(instance_id="p1", ref="carte-pioche-cachee"),),
    )
    etat = EtatPartie(joueurs=(alice_avec_pioche, etat.joueurs[1]), tour=etat.tour)
    refs = refs_en_jeu(etat)
    assert PIKACHU in refs
    assert ENERGIE_FEU in refs
    assert OUTIL_PV in refs
    assert SALAMECHE in refs
    assert "carte-pioche-cachee" not in refs  # zone cachée : jamais exposée
