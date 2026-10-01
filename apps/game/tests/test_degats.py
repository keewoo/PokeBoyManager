"""Tests de la résolution d'attaque — lot ``j-degats-resolution``.

Ce fichier FAIT FOI sur les critères d'acceptation de la mission :

1. **tous les cas de dégâts** de ``docs/jeu/cas-de-regles.yaml`` passent — la table
   :data:`CAS_DEGATS` les exécute, et un test de couverture garantit qu'aucun n'est laissé
   de côté en silence (un cas ajouté au corpus sans test ici fait échouer la suite) ;
2. le **détail de calcul** est produit pour chaque attaque (R-10.9) et porté par l'événement
   de journal :data:`~pbm_game.journal.EVT_DEGATS` ;
3. les dégâts au **banc** n'appliquent ni faiblesse ni résistance (R-10.5).

S'y ajoutent : la vérification du **coût** (colorés, incolores, énergies multi-unités — R-9.2),
la pose en **compteurs** jamais en PV (R-10.4), les **compteurs directs** (R-10.6), le
**plancher** (R-10.7), l'arrêt à l'étape 2 sur une attaque sans dégât (R-16.8) et les
**points d'accroche** de modificateurs des étapes 2 et 5 (R-10.1). Chaque test de règle nomme
le ``R-x.y`` qu'il vérifie.

La suite échoue naturellement sans le paquet ``pbm_game.combat`` (import en tête) : c'est le
« test qui échoue sans le changement et passe avec ».
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pbm_game.combat import (
    INCOLORE,
    CoutAttaque,
    Faiblesse,
    Resistance,
    cout_satisfait,
    evenement_degats,
    modificateur_ajout,
    modificateur_multiplie,
    poser_compteurs,
    poser_degats,
    resoudre_degats,
)
from pbm_game.journal import EVT_DEGATS
from pbm_game.regles import charger_cas
from pbm_game.state import Carte, PokemonEnJeu

# apps/game/tests/test_degats.py -> racine du dépôt (parents[3]).
RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_CAS = RACINE_DEPOT / "docs" / "jeu" / "cas-de-regles.yaml"


def _pokemon(compteurs: int = 0) -> PokemonEnJeu:
    """Un Pokémon en jeu minimal, avec ``compteurs`` compteurs de dégâts déjà posés."""
    return PokemonEnJeu(
        cartes=(Carte(instance_id="pk-1", ref="ref-pk-1"),),
        energies=(Carte(instance_id="en-1", ref="ref-en-1"),),
        compteurs_degats=compteurs,
    )


# --- Table des cas de dégâts du corpus (docs/jeu/cas-de-regles.yaml) ----------
# Chaque entrée EXÉCUTE le cas de même id : les paramètres de ``resoudre_degats`` et le
# résultat attendu (dégâts posés, compteurs, détail lisible). ``type_attaque=None`` signifie
# « applicabilité déjà décidée » — on isole ici l'arithmétique et l'ORDRE des opérations ;
# l'appariement de type a son propre test (``test_faiblesse_ne_s_applique_pas_hors_type``).
CAS_DEGATS: dict[str, dict] = {
    # R-10.2 : la faiblesse multiplie les dégâts de base par 2 (étape 3).
    "degats-faiblesse-x2": {
        "regles": {"R-10.2", "R-10.1"},
        "params": {"base": 60, "faiblesse": Faiblesse("feu")},
        "degats": 120,
        "compteurs": 12,
        "detail": "60 base, ×2 faiblesse = 120",
    },
    # R-10.3 : la résistance réduit les dégâts de 30 (étape 4).
    "degats-resistance-moins-30": {
        "regles": {"R-10.3", "R-10.1"},
        "params": {"base": 50, "resistance": Resistance("eau")},
        "degats": 20,
        "compteurs": 2,
        "detail": "50 base, −30 résistance = 20",
    },
    # R-10.1 / R-10.8 : faiblesse PUIS résistance — 60×2=120 puis −30=90, jamais (60−30)×2.
    "degats-ordre-faiblesse-puis-resistance": {
        "regles": {"R-10.1", "R-10.8"},
        "params": {"base": 60, "faiblesse": Faiblesse("feu"), "resistance": Resistance("eau")},
        "degats": 90,
        "compteurs": 9,
        "detail": "60 base, ×2 faiblesse, −30 résistance = 90",
    },
    # R-10.4 : vérifié par la pose (test_poser_degats_*) ; ici on contrôle le calcul brut.
    "degats-compteurs-pas-pv": {
        "regles": {"R-10.4"},
        "params": {"base": 30},
        "degats": 30,
        "compteurs": 3,
        "detail": "30 base = 30",
    },
    # R-10.5 : au banc, ni faiblesse ni résistance — malgré une faiblesse ET une résistance.
    "degats-banc-sans-faiblesse-resistance": {
        "regles": {"R-10.5"},
        "params": {
            "base": 60,
            "faiblesse": Faiblesse("feu"),
            "resistance": Resistance("eau"),
            "au_banc": True,
        },
        "degats": 60,
        "compteurs": 6,
        "detail": "60 base = 60",
    },
    # R-10.7 : résistance supérieure aux dégâts → plancher à 0, aucun compteur.
    "degats-plancher-zero": {
        "regles": {"R-10.7"},
        "params": {"base": 20, "resistance": Resistance("eau")},
        "degats": 0,
        "compteurs": 0,
        "detail": "20 base, −30 résistance, plancher à 0 = 0",
    },
    # R-10.1 (étape 2) : attaque de 0 dégât → arrêt, la faiblesse n'est JAMAIS appliquée (R-16.8).
    "degats-faiblesse-sur-zero": {
        "regles": {"R-10.1"},
        "params": {"base": 0, "faiblesse": Faiblesse("feu")},
        "degats": 0,
        "compteurs": 0,
        "detail": "0 base = 0",
        "arrete": True,
    },
    # R-10.9 : le détail de calcul est produit (exemple canonique du corpus).
    "degats-detail-journalise": {
        "regles": {"R-10.9"},
        "params": {"base": 60, "faiblesse": Faiblesse("feu"), "resistance": Resistance("eau")},
        "degats": 90,
        "compteurs": 9,
        "detail": "60 base, ×2 faiblesse, −30 résistance = 90",
    },
}


@pytest.fixture(scope="module")
def cas_corpus():
    donnees = yaml.safe_load(CHEMIN_CAS.read_text(encoding="utf-8"))
    return {c.id: c for c in charger_cas(donnees)}


def test_tous_les_cas_de_degats_du_corpus_sont_couverts(cas_corpus):
    """Chaque cas « degats-* » du corpus a une entrée exécutable ici (pas d'oubli silencieux)."""
    du_corpus = {cid for cid in cas_corpus if cid.startswith("degats-")}
    couverts = set(CAS_DEGATS)
    assert du_corpus == couverts, (
        f"Cas de dégâts non exécutés : {sorted(du_corpus - couverts)} ; "
        f"entrées orphelines : {sorted(couverts - du_corpus)}."
    )


@pytest.mark.parametrize("cid", sorted(CAS_DEGATS))
def test_cas_de_degats(cid: str, cas_corpus):
    """Exécute un cas de dégâts du corpus et contrôle dégâts, compteurs, détail et règles."""
    cas = CAS_DEGATS[cid]
    # Les règles déclarées par le test sont bien celles que le corpus attache à ce cas.
    attendues = set(cas_corpus[cid].regles)
    assert cas["regles"] <= attendues, (
        f"{cid} : le test cite {sorted(cas['regles'])}, "
        f"hors des règles du corpus {sorted(attendues)}."
    )

    resultat = resoudre_degats(**cas["params"])
    assert resultat.degats == cas["degats"], f"{cid} : dégâts {resultat.degats} ≠ {cas['degats']}"
    assert resultat.compteurs == cas["compteurs"], f"{cid} : compteurs {resultat.compteurs}"
    assert resultat.detail == cas["detail"], f"{cid} : détail {resultat.detail!r}"
    if cas.get("arrete"):
        assert resultat.arrete_avant_degats, f"{cid} : l'attaque aurait dû s'arrêter à l'étape 2."


# --- Détail de calcul et journal (R-10.9) ------------------------------------


def test_detail_exact_de_l_exemple_du_corpus():
    """R-10.9 — le détail reproduit EXACTEMENT l'exemple du corpus (×2 et −30 typographiques)."""
    r = resoudre_degats(base=60, faiblesse=Faiblesse("feu"), resistance=Resistance("eau"))
    assert r.detail == "60 base, ×2 faiblesse, −30 résistance = 90"


def test_chaque_etape_est_tracee_avec_sa_regle():
    """R-10.1 — chaque étape du calcul porte la règle R-x.y qui la motive."""
    r = resoudre_degats(base=60, faiblesse=Faiblesse("feu"), resistance=Resistance("eau"))
    regles = [e.regle for e in r.etapes]
    assert regles == ["R-10.1", "R-10.2", "R-10.3"]
    assert all(e.regle.startswith("R-") for e in r.etapes)


def test_evenement_degats_porte_le_detail_pour_le_journal():
    """R-10.9 — l'événement de journal porte le détail lisible, en valeurs JSON natives."""
    r = resoudre_degats(base=60, faiblesse=Faiblesse("feu"), resistance=Resistance("eau"))
    evt = evenement_degats(r, "pk-adverse-1")
    assert evt.type == EVT_DEGATS
    assert evt.donnees["detail"] == "60 base, ×2 faiblesse, −30 résistance = 90"
    assert evt.donnees["degats"] == 90
    assert evt.donnees["compteurs"] == 9
    assert evt.donnees["cible"] == "pk-adverse-1"
    assert evt.donnees["au_banc"] is False
    # Toutes les valeurs sont JSON natives (sérialisables/rejouables).
    assert all(isinstance(v, (str, int, bool)) for v in evt.donnees.values())


# --- Pose des dégâts : en COMPTEURS, jamais en PV (R-10.4) --------------------


def test_poser_degats_augmente_les_compteurs_sans_toucher_le_reste():
    """R-10.4 — poser des dégâts augmente ``compteurs_degats`` et ne touche à rien d'autre."""
    avant = _pokemon(compteurs=10)
    apres = poser_degats(avant, 90)
    assert apres.compteurs_degats == 100
    # Rien d'autre n'a bougé : mêmes cartes, mêmes énergies, même Outil, mêmes états.
    assert apres.cartes == avant.cartes
    assert apres.energies == avant.energies
    assert apres.outil == avant.outil
    assert apres.etats_speciaux == avant.etats_speciaux
    # L'état d'origine est figé : il n'a pas changé (fonction pure).
    assert avant.compteurs_degats == 10


def test_poser_degats_est_cumulatif():
    """R-10.4 — deux attaques successives cumulent leurs compteurs."""
    pk = _pokemon(compteurs=0)
    pk = poser_degats(pk, 30)
    pk = poser_degats(pk, 40)
    assert pk.compteurs_degats == 70


def test_poser_degats_refuse_un_montant_negatif():
    """R-10.4 — un montant négatif serait un soin déguisé : refusé, jamais replié en silence."""
    with pytest.raises(ValueError, match="négatif|invalides"):
        poser_degats(_pokemon(), -10)


def test_poser_compteurs_directs_ignore_tout(cas_corpus):  # noqa: ARG001
    """R-10.6 — « placez N compteurs » pose N×10 dégâts, sans faiblesse/résistance/modificateur."""
    pk = poser_compteurs(_pokemon(compteurs=20), 3)
    assert pk.compteurs_degats == 20 + 30


# --- Résolution : plancher, arrêt, auto-dégâts, banc -------------------------


def test_plancher_a_zero_ne_pose_aucun_compteur():
    """R-10.7 — un résultat ≤ 0 (résistance > dégâts) plancher à 0, aucun compteur."""
    r = resoudre_degats(base=20, resistance=Resistance("eau"))
    assert r.degats == 0
    assert r.compteurs == 0
    assert r.detail == "20 base, −30 résistance, plancher à 0 = 0"


def test_attaque_sans_degat_s_arrete_avant_la_faiblesse():
    """R-16.8 — base 0 : on s'arrête à l'étape 2, la faiblesse n'est JAMAIS appliquée."""
    r = resoudre_degats(base=0, faiblesse=Faiblesse("feu"))
    assert r.degats == 0
    assert r.arrete_avant_degats is True
    # La faiblesse n'apparaît pas dans la trace : elle n'a pas été appliquée.
    assert all("faiblesse" not in e.fragment for e in r.etapes)


def test_degats_au_banc_ignorent_faiblesse_et_resistance():
    """R-10.5 — au banc, une faiblesse et une résistance présentes ne changent rien."""
    sans_banc = resoudre_degats(base=60, faiblesse=Faiblesse("feu"))
    au_banc = resoudre_degats(base=60, faiblesse=Faiblesse("feu"), au_banc=True)
    assert sans_banc.degats == 120
    assert au_banc.degats == 60


def test_auto_degats_posent_des_compteurs_sur_soi():
    """Auto-dégâts (recul) : on résout sans faiblesse/résistance et on pose sur l'attaquant."""
    r = resoudre_degats(base=20, au_banc=True)  # un Pokémon n'est ni faible ni résistant à soi
    attaquant = poser_degats(_pokemon(compteurs=0), r.degats)
    assert attaquant.compteurs_degats == 20


# --- Points d'accroche de modificateurs (R-10.1 étapes 2 et 5) ---------------


def test_modificateur_attaquant_s_applique_avant_la_faiblesse():
    """R-10.1 étape 2 — un modificateur attaquant (+20) s'ajoute avant la faiblesse."""
    r = resoudre_degats(
        base=40,
        modificateurs_attaquant=[modificateur_ajout("Grande Griffe", "R-10.1", 20)],
        faiblesse=Faiblesse("feu"),
    )
    # (40 + 20) × 2 = 120
    assert r.degats == 120
    assert r.detail == "40 base, +20 Grande Griffe, ×2 faiblesse = 120"


def test_modificateur_defenseur_reduit_apres_la_resistance():
    """R-10.1 étape 5 — une réduction côté défenseur (−20) s'applique après la résistance."""
    r = resoudre_degats(
        base=90,
        resistance=Resistance("eau"),
        modificateurs_defenseur=[modificateur_ajout("Bouclier", "R-10.1", -20)],
    )
    # 90 − 30 − 20 = 40
    assert r.degats == 40
    assert r.detail == "90 base, −30 résistance, −20 Bouclier = 40"


def test_modificateur_multiplicatif_dans_la_trace():
    """R-10.1 — un modificateur multiplicatif apparaît avec le signe × dans le détail."""
    r = resoudre_degats(
        base=30,
        modificateurs_attaquant=[modificateur_multiplie("Rage", "R-10.1", 3)],
    )
    assert r.degats == 90
    assert r.detail == "30 base, ×3 Rage = 90"


def test_faiblesse_ne_s_applique_pas_hors_type():
    """R-10.2 — la faiblesse ne joue que si l'attaque est de son type."""
    sans = resoudre_degats(base=60, type_attaque="eau", faiblesse=Faiblesse("feu"))
    avec = resoudre_degats(base=60, type_attaque="feu", faiblesse=Faiblesse("feu"))
    assert sans.degats == 60
    assert avec.degats == 120


def test_base_negative_refusee():
    """Des dégâts de base négatifs n'ont pas de sens : refusés, jamais repliés en silence."""
    with pytest.raises(ValueError, match="base invalides|≥ 0"):
        resoudre_degats(base=-10)


# --- Vérification du coût de l'attaque (R-9.2) -------------------------------


def test_cout_vide_est_gratuit():
    """R-9.2 — une attaque sans coût est toujours satisfaite."""
    assert cout_satisfait(CoutAttaque(), []).accepte


def test_cout_colore_exactement_paye():
    """R-9.2 — un symbole coloré se paie par une énergie de ce type exact."""
    cout = CoutAttaque(types={"feu": 2})
    assert cout_satisfait(cout, [{"feu": 1}, {"feu": 1}]).accepte


def test_cout_colore_insuffisant_refuse_en_citant_la_regle():
    """R-9.2 — coût coloré non couvert : refus motivé citant R-9.2."""
    v = cout_satisfait(CoutAttaque(types={"feu": 2}), [{"feu": 1}])
    assert v.refuse
    assert v.regle == "R-9.2"
    assert "feu" in v.message


def test_symbole_incolore_paye_par_n_importe_quel_type():
    """R-9.2 — un symbole incolore (★) se paie par n'importe quelle énergie restante."""
    cout = CoutAttaque(types={"feu": 1}, incolore=2)
    assert cout_satisfait(cout, [{"feu": 1}, {"eau": 1}, {"plante": 1}]).accepte


def test_energie_multi_unites_compte_pour_plusieurs():
    """R-9.2 — une énergie peut fournir plusieurs unités (Double Énergie Incolore = 2)."""
    cout = CoutAttaque(incolore=2)
    assert cout_satisfait(cout, [{INCOLORE: 2}]).accepte


def test_energie_speciale_bi_type():
    """R-9.2 — une énergie spéciale peut fournir des unités de deux types."""
    cout = CoutAttaque(types={"feu": 1, "eau": 1})
    assert cout_satisfait(cout, [{"feu": 1, "eau": 1}]).accepte


def test_unite_incolore_ne_paie_pas_un_symbole_colore():
    """R-9.2 — une unité incolore ne paie qu'un symbole incolore, jamais un symbole coloré."""
    v = cout_satisfait(CoutAttaque(types={"feu": 1}), [{INCOLORE: 2}])
    assert v.refuse
    assert v.regle == "R-9.2"


def test_cout_incolore_insuffisant_refuse():
    """R-9.2 — pas assez d'unités pour couvrir les symboles incolores : refus motivé."""
    v = cout_satisfait(CoutAttaque(incolore=3), [{"feu": 1}, {"eau": 1}])
    assert v.refuse
    assert v.regle == "R-9.2"
    assert "incolore" in v.message


def test_energie_en_trop_ne_gene_pas():
    """R-9.2 — « au moins » l'énergie requise : de l'énergie en trop ne refuse pas l'attaque."""
    cout = CoutAttaque(types={"feu": 1})
    assert cout_satisfait(cout, [{"feu": 1}, {"eau": 1}, {"plante": 1}]).accepte


def test_fourniture_malformee_echoue_bruyamment():
    """Une fourniture d'énergie malformée est une panne, jamais un zéro silencieux."""
    with pytest.raises(ValueError):
        cout_satisfait(CoutAttaque(types={"feu": 1}), [{"feu": -1}])
