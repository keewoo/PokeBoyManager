"""La pile d'effets — LIFO, source journalisée, interruptions, D9. Lot j-effets-architecture.

Aucun effet réel n'est scripté (D9) : on utilise des résolveurs *jouets* pour prouver que le
mécanisme tient — l'ordre dernier entré premier sorti, l'attribution de chaque résolution à sa
carte source, le refus d'un type inconnu, l'effet sans cible qui le **dit**, et l'interruption.
"""

from __future__ import annotations

import pytest

from pbm_game.effets.pile import (
    EVT_EFFET_RESOLU,
    EVT_EFFET_SANS_CIBLE,
    EffetEnAttente,
    PileEffets,
    SourceEffet,
    evenement_sans_cible,
    resoudre_pile,
)
from pbm_game.journal.modele import Evenement
from pbm_game.rng import Rng
from pbm_game.state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu, Tour

_RNG = Rng(b"effets-pile-seed")


def _etat() -> EtatPartie:
    base = PokemonEnJeu(cartes=(Carte("a-1", "ref-a"),))
    j = Joueur(id="alice", actif=base)
    k = Joueur(id="bob", actif=base)
    return EtatPartie(joueurs=(j, k), tour=Tour(joueur_actif="alice", numero=3, phase="principale"))


def _effet(libelle: str, type_effet: str = "note", **params) -> EffetEnAttente:
    return EffetEnAttente(
        type_effet=type_effet,
        source=SourceEffet(f"carte {libelle}", ref=f"ref-{libelle}", instance_id=f"i-{libelle}"),
        regle="R-12.3",
        libelle=libelle,
        params=params,
    )


def _resolveur_note(etat, effet, rng):
    """Émet un simple événement « note » portant le libellé — sert à lire l'ordre de résolution."""
    return etat, [Evenement("note", {"libelle": effet.libelle})], []


def _notes(evenements) -> list[str]:
    return [e.donnees["libelle"] for e in evenements if e.type == "note"]


def test_pile_resolue_en_dernier_entre_premier_sorti():
    registre = {"note": _resolveur_note}
    pile = PileEffets().empiler(_effet("A"), _effet("B"), _effet("C"))
    _, evenements = resoudre_pile(_etat(), pile, registre, _RNG)
    assert _notes(evenements) == ["C", "B", "A"]  # LIFO


def test_chaque_resolution_est_journalisee_avec_sa_source():
    registre = {"note": _resolveur_note}
    pile = PileEffets().empiler(_effet("Outil X"))
    _, evenements = resoudre_pile(_etat(), pile, registre, _RNG)
    resolus = [e for e in evenements if e.type == EVT_EFFET_RESOLU]
    assert len(resolus) == 1
    assert resolus[0].donnees["source"]["libelle"] == "carte Outil X"
    assert resolus[0].donnees["regle"] == "R-12.3"


def test_type_d_effet_inconnu_est_refuse_d9():
    pile = PileEffets().empiler(_effet("Z", type_effet="inexistant"))
    with pytest.raises(ValueError, match="jamais approximé"):
        resoudre_pile(_etat(), pile, {}, _RNG)


def test_effet_sans_cible_ne_bloque_pas_et_le_dit():
    def _resolveur_vide(etat, effet, rng):
        return etat, [evenement_sans_cible(effet.source, effet, "banc adverse vide")], []

    pile = PileEffets().empiler(_effet("Appât", type_effet="appat"))
    _, evenements = resoudre_pile(_etat(), pile, {"appat": _resolveur_vide}, _RNG)
    sans_cible = [e for e in evenements if e.type == EVT_EFFET_SANS_CIBLE]
    assert sans_cible and sans_cible[0].donnees["raison"] == "banc adverse vide"


def test_interruption_insere_un_effet_qui_se_resout_d_abord():
    """Un effet « en réaction » empilé par la fenêtre d'interruption passe AVANT le sommet.

    Le garde d'interruption est appelé avant chaque résolution ; c'est à lui de n'injecter sa
    réaction qu'**une fois** (ici, un drapeau à usage unique), faute de quoi il boucle — et le
    garde anti-boucle de la pile l'arrêterait bruyamment (jamais un silence).
    """
    registre = {"note": _resolveur_note}
    deja_reagi: list[bool] = []

    def _interruption(etat, sommet, pile, rng):
        if sommet.libelle == "principal" and not deja_reagi:
            deja_reagi.append(True)
            return pile.empiler(_effet("reaction")), []
        return pile, []

    pile = PileEffets().empiler(_effet("principal"))
    _, evenements = resoudre_pile(_etat(), pile, registre, _RNG, interruption=_interruption)
    assert _notes(evenements) == ["reaction", "principal"]


def test_effet_qui_en_empile_un_autre_le_resout_avant_la_suite():
    def _resolveur_chaine(etat, effet, rng):
        return etat, [Evenement("note", {"libelle": effet.libelle})], [_effet("feuille")]

    registre = {"racine": _resolveur_chaine, "note": _resolveur_note}
    pile = PileEffets().empiler(_effet("apres", "note"), _effet("racine", "racine"))
    _, evenements = resoudre_pile(_etat(), pile, registre, _RNG)
    # « racine » (sommet) se résout, empile « feuille » qui passe AVANT « apres ».
    assert _notes(evenements) == ["racine", "feuille", "apres"]


def test_boucle_d_effets_s_arrete_bruyamment():
    def _resolveur_boucle(etat, effet, rng):
        return etat, [], [_effet("encore", "boucle")]

    pile = PileEffets().empiler(_effet("depart", "boucle"))
    with pytest.raises(ValueError, match="boucle d'effets"):
        resoudre_pile(_etat(), pile, {"boucle": _resolveur_boucle}, _RNG)


def test_pile_vide_ne_produit_rien():
    etat = _etat()
    etat2, evenements = resoudre_pile(etat, PileEffets(), {}, _RNG)
    assert etat2 is etat and evenements == []


def test_effet_en_attente_exige_regle_et_libelle_d9():
    with pytest.raises(ValueError, match="citer la règle"):
        EffetEnAttente(type_effet="note", source=SourceEffet("x"), regle="  ", libelle="l")
    with pytest.raises(ValueError, match="libellé"):
        EffetEnAttente(type_effet="note", source=SourceEffet("x"), regle="R-1.1", libelle="")
