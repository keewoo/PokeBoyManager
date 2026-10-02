"""Tests du lot ``j-cartes-energies`` — fourniture d'énergie générique et paiement expliqué.

Trois mécaniques, chacune citant sa règle du corpus (``docs/jeu/REGLES.md``) :

1. **fourniture générique (R-9.2)** — une énergie n'a pas un type figé, elle *fournit* des
   unités : Énergie de base (1 unité, 1 type), Double Énergie Incolore (2 unités incolores),
   énergie spéciale bi-type (2 unités, 2 types), et l'énergie spéciale qui ne compte que pour
   un seul type ;
2. **paiement expliqué (R-9.2)** — :func:`payer_cout` trouve une combinaison valide quand elle
   existe et dit *laquelle* ; elle refuse en citant R-9.2 quand aucune n'existe, sans jamais
   accepter de l'incolore pour un symbole coloré (le piège combinatoire nommé par la fiche) ;
3. **effets d'énergie spéciale branchés sur la pile (D9)** — une énergie porteuse d'effet
   produit des :class:`EffetEnAttente` empilables, résolus avec l'énergie pour source.

Le décompte « de base illimitée / spéciale possédée » (D10) et la règle des 4 relèvent du
**service de légalité des decks** (``apps/api``, ``test_deck_legality.py``) — on ne le redit
pas ici : ce module teste la capacité de **jeu** de l'énergie, pas sa légalité en deck.
"""

from __future__ import annotations

import pytest

from pbm_game.cartes.energie import (
    DefinitionEnergie,
    EffetEnergie,
    definition_energie_depuis_dict,
)
from pbm_game.combat.cout import (
    EVT_COUT_PAYE,
    GENRE_SYMBOLE_COLORE,
    GENRE_SYMBOLE_INCOLORE,
    SYMBOLE_INCOLORE,
    EnergieAttachee,
    cout_satisfait,
    payer_cout,
)
from pbm_game.combat.modele import INCOLORE, CoutAttaque
from pbm_game.effets.pile import (
    EVT_EFFET_RESOLU,
    EffetEnAttente,
    PileEffets,
    resoudre_pile,
)
from pbm_game.journal.modele import Evenement
from pbm_game.rng import Rng
from pbm_game.state.modele import PHASE_PRINCIPALE, EtatPartie, Joueur, Tour

_RNG = Rng(b"cartes-energies-seed")


# --- 1. Fourniture générique (R-9.2) -----------------------------------------


def test_energie_de_base_fournit_une_unite_de_son_type_r92():
    """R-9.2 — une Énergie de base fournit une unité de son unique type (pas un type figé)."""
    feu = DefinitionEnergie(ref="base-feu", nom="Énergie Feu", fournit={"feu": 1})
    assert feu.attachee("e1") == EnergieAttachee("e1", {"feu": 1}, "Énergie Feu")


def test_double_energie_incolore_fournit_deux_unites_r92():
    """R-9.2 — une énergie peut fournir plusieurs unités (Double Énergie Incolore = 2 ★)."""
    dbl = DefinitionEnergie(ref="dbl", nom="Double Énergie Incolore", fournit={INCOLORE: 2})
    assert dbl.attachee("e1").fournit == {INCOLORE: 2}


def test_energie_speciale_bi_type_fournit_deux_types_r92():
    """R-9.2 — une énergie spéciale peut fournir des unités de deux types distincts."""
    bi = DefinitionEnergie(ref="bi", nom="Énergie Double Face", fournit={"feu": 1, "eau": 1})
    assert bi.attachee("e1").fournit == {"feu": 1, "eau": 1}


def test_energie_speciale_ne_compte_que_pour_un_type_r92():
    """R-9.2 — une énergie spéciale mono-type paie son type, jamais un autre symbole coloré."""
    mono = DefinitionEnergie(ref="mono", nom="Énergie Feu Brillante", fournit={"feu": 1})
    assert payer_cout(CoutAttaque(types={"feu": 1}), [mono.attachee("e1")]).paye is True
    refus = payer_cout(CoutAttaque(types={"eau": 1}), [mono.attachee("e1")])
    assert refus.paye is False
    assert refus.verdict.regle == "R-9.2"


def test_fourniture_vide_est_refusee():
    """Une énergie qui ne fournit rien est une panne, jamais un cas normal."""
    with pytest.raises(ValueError, match="au moins une unité"):
        DefinitionEnergie(ref="vide", nom="Énergie Fantôme", fournit={})
    with pytest.raises(ValueError, match="au moins une unité"):
        DefinitionEnergie(ref="zero", nom="Énergie Nulle", fournit={"feu": 0})


def test_fourniture_malformee_echoue_bruyamment():
    """R-9.2 — une fourniture malformée (unités négatives) échoue, jamais un zéro silencieux."""
    with pytest.raises(ValueError):
        DefinitionEnergie(ref="neg", nom="Énergie Buguée", fournit={"feu": -1})


def test_definition_energie_depuis_dict():
    """Le service fournit un mapping ``{ref, nom, fournit, effets}`` depuis le catalogue."""
    e = definition_energie_depuis_dict(
        {
            "ref": "dbl",
            "nom": "Double Énergie Incolore",
            "fournit": {INCOLORE: 2},
            "effets": [],
        }
    )
    assert e.fournit == {INCOLORE: 2}
    assert e.effets == ()


# --- 2. Paiement expliqué (R-9.2) --------------------------------------------


def test_paiement_trouve_une_combinaison_et_la_nomme_r92():
    """R-9.2 — payer_cout trouve une combinaison valide et dit quelle énergie paie quoi."""
    bi = DefinitionEnergie(ref="bi", nom="Énergie Double Face", fournit={"feu": 1, "eau": 1})
    p = payer_cout(CoutAttaque(types={"feu": 1, "eau": 1}), [bi.attachee("e1")])
    assert p.paye is True
    assert len(p.affectations) == 2
    assert {a.symbole for a in p.affectations} == {"feu", "eau"}
    assert all(a.energie_instance_id == "e1" for a in p.affectations)
    assert all(a.genre == GENRE_SYMBOLE_COLORE for a in p.affectations)
    assert "Énergie Double Face" in p.detail


def test_cout_mixte_paye_par_une_double_energie_incolore_r92():
    """R-9.2 — coût mixte (1 feu + 2 ★) : le feu par l'Énergie Feu, les 2 ★ par la Double."""
    feu = DefinitionEnergie(ref="feu", nom="Énergie Feu", fournit={"feu": 1})
    dbl = DefinitionEnergie(ref="dbl", nom="Double Énergie Incolore", fournit={INCOLORE: 2})
    p = payer_cout(
        CoutAttaque(types={"feu": 1}, incolore=2),
        [feu.attachee("f1"), dbl.attachee("d1")],
    )
    assert p.paye is True
    colore = [a for a in p.affectations if a.genre == GENRE_SYMBOLE_COLORE]
    incolore = [a for a in p.affectations if a.genre == GENRE_SYMBOLE_INCOLORE]
    assert len(colore) == 1 and colore[0].energie_instance_id == "f1"
    assert len(incolore) == 2 and all(a.energie_instance_id == "d1" for a in incolore)
    assert all(a.symbole == SYMBOLE_INCOLORE for a in incolore)
    assert "Double Énergie Incolore" in p.detail


def test_unite_incolore_ne_paie_jamais_un_symbole_colore_r92():
    """R-9.2 — le piège combinatoire : de l'incolore ne doit pas « réussir » un coût coloré."""
    dbl = DefinitionEnergie(ref="dbl", nom="Double Énergie Incolore", fournit={INCOLORE: 2})
    p = payer_cout(CoutAttaque(types={"feu": 1}), [dbl.attachee("d1")])
    assert p.paye is False
    assert p.verdict.regle == "R-9.2"


def test_cout_vide_est_gratuit_et_son_detail_le_dit_r92():
    """R-9.2 — une attaque sans coût est payée sans énergie, et le détail le dit."""
    p = payer_cout(CoutAttaque(), [])
    assert p.paye is True
    assert p.affectations == ()
    assert "gratuit" in p.detail.casefold()


def test_paiement_est_deterministe_pour_le_rejeu():
    """Rejouer la même situation redonne EXACTEMENT la même combinaison (rejeu, journal)."""
    e1 = EnergieAttachee("a", {"feu": 1}, "Feu A")
    e2 = EnergieAttachee("b", {"feu": 1}, "Feu B")
    cout = CoutAttaque(types={"feu": 1}, incolore=1)
    p1 = payer_cout(cout, [e1, e2])
    p2 = payer_cout(cout, [e1, e2])
    assert p1.affectations == p2.affectations


def test_paiement_refuse_ne_se_journalise_pas():
    """Un paiement qui n'a pas eu lieu ne produit aucun événement (pas de repli silencieux)."""
    p = payer_cout(CoutAttaque(types={"eau": 1}), [EnergieAttachee("e1", {"feu": 1}, "Feu")])
    assert p.paye is False
    with pytest.raises(ValueError, match="n'a pas été payé"):
        p.evenement(CoutAttaque(types={"eau": 1}))


def test_evenement_cout_paye_porte_le_detail_et_la_combinaison():
    """Le coût payé est journalisé (EVT_COUT_PAYE) avec son détail et ses affectations (R-9.2)."""
    feu = DefinitionEnergie(ref="feu", nom="Énergie Feu", fournit={"feu": 1})
    cout = CoutAttaque(types={"feu": 1})
    p = payer_cout(cout, [feu.attachee("f1")])
    evt = p.evenement(cout)
    assert isinstance(evt, Evenement)
    assert evt.type == EVT_COUT_PAYE
    assert evt.donnees["detail"] == p.detail
    assert evt.donnees["affectations"][0]["energie"] == "f1"
    assert evt.donnees["cout"] == {"types": {"feu": 1}, "incolore": 0}


def test_payer_cout_accorde_exactement_comme_cout_satisfait():
    """payer_cout et cout_satisfait rendent le même verdict (une seule logique de coût)."""
    cout = CoutAttaque(types={"feu": 1}, incolore=1)
    energies = [EnergieAttachee("e1", {"feu": 1}, "Feu"), EnergieAttachee("e2", {"eau": 1}, "Eau")]
    verdict_direct = cout_satisfait(cout, [e.fournit for e in energies])
    assert payer_cout(cout, energies).verdict.accepte == verdict_direct.accepte


# --- 3. Effets d'énergie spéciale branchés sur la pile (D9) ------------------


def _etat_minimal() -> EtatPartie:
    """Un état à deux joueurs, sans Pokémon : suffisant pour résoudre une pile d'effets."""
    return EtatPartie(
        joueurs=(Joueur(id="alice"), Joueur(id="bob")),
        tour=Tour(joueur_actif="alice", numero=1, phase=PHASE_PRINCIPALE),
    )


def test_effets_en_attente_sont_empilables_et_attribues_a_l_energie():
    """Une énergie porteuse d'effet produit un EffetEnAttente attribué à elle-même (source)."""
    energie = DefinitionEnergie(
        ref="retraite-libre",
        nom="Énergie Fuite",
        fournit={INCOLORE: 1},
        effets=(
            EffetEnergie(
                type_effet="energie_cout_retraite",
                regle="R-8.2",
                libelle="Retraite allégée",
                params={"reduction": 1},
            ),
        ),
    )
    (effet,) = energie.effets_en_attente("e1")
    assert isinstance(effet, EffetEnAttente)
    assert effet.type_effet == "energie_cout_retraite"
    assert effet.regle == "R-8.2"
    assert effet.source.instance_id == "e1"
    assert effet.source.libelle == "Énergie Fuite"
    assert effet.params == {"reduction": 1}


def test_effet_d_energie_se_resout_sur_la_pile_en_citant_sa_source():
    """D9 — l'effet d'énergie, empilé, se résout et sa résolution nomme l'énergie source."""
    energie = DefinitionEnergie(
        ref="retraite-libre",
        nom="Énergie Fuite",
        fournit={INCOLORE: 1},
        effets=(
            EffetEnergie(
                type_effet="energie_cout_retraite",
                regle="R-8.2",
                libelle="Retraite allégée",
                params={"reduction": 1},
            ),
        ),
    )

    def _resolveur(etat, effet, rng):
        # Résolveur de test (le vrai est livré par un lot d'effets, D9) : il journalise
        # l'application sans muter l'état, pour prouver que l'effet passe bien par la pile.
        evt = Evenement("energie_effet_applique", {"reduction": effet.params["reduction"]})
        return etat, [evt], []

    pile = PileEffets().empiler(*energie.effets_en_attente("e1"))
    _, evenements = resoudre_pile(
        _etat_minimal(), pile, {"energie_cout_retraite": _resolveur}, _RNG
    )
    resolus = [e for e in evenements if e.type == EVT_EFFET_RESOLU]
    assert len(resolus) == 1
    assert resolus[0].donnees["source"]["instance_id"] == "e1"
    assert resolus[0].donnees["source"]["libelle"] == "Énergie Fuite"
    assert any(e.type == "energie_effet_applique" for e in evenements)


def test_effet_d_energie_non_enregistre_est_refuse_d9():
    """D9 — un effet d'énergie dont le type n'est pas scripté est refusé, jamais deviné."""
    energie = DefinitionEnergie(
        ref="mystere",
        nom="Énergie Inconnue",
        fournit={INCOLORE: 1},
        effets=(EffetEnergie(type_effet="effet_jamais_ecrit", regle="R-9.2", libelle="?"),),
    )
    pile = PileEffets().empiler(*energie.effets_en_attente("e1"))
    with pytest.raises(ValueError, match="Type d'effet inconnu"):
        resoudre_pile(_etat_minimal(), pile, {}, _RNG)
