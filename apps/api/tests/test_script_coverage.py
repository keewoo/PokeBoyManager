"""Le cœur **pur** du tableau de couverture (`pbm_api.jeu.scripts.couverture`) — lot
`j-effets-couverture-outil`.

Aucune E/S : ces tests opèrent sur des `CarteCouverture` et un registre (dict empreinte→statut)
fabriqués à la main. Ils verrouillent la sémantique D9 au grain de la carte (une carte n'est
jouable que si TOUS ses effets le sont), la mesure par famille/extension/collection, et le
classement des cartes qui bloquent le plus — tout ce sur quoi s'appuie l'adaptateur base. Chaque
test échoue sans le lot (le module n'existait pas).
"""

from __future__ import annotations

import uuid

from pbm_api.jeu.scripts.couverture import (
    STATUT_ABSENT,
    CarteCouverture,
    EffetRef,
    carte_jouable,
    classer_cartes_manquantes,
    couverture_cartes,
    couverture_collections,
    couverture_effets,
    couverture_par_extension,
    couverture_par_famille,
    raison_blocage,
)
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_A_REVOIR,
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
)

SET_A = uuid.uuid4()
SET_B = uuid.uuid4()


def _carte(*effets: EffetRef, set_id: uuid.UUID = SET_A) -> CarteCouverture:
    return CarteCouverture(card_id=uuid.uuid4(), set_id=set_id, effets=tuple(effets))


def _eff(empreinte: str, origine: str = "attaque") -> EffetRef:
    return EffetRef(empreinte=empreinte, origine=origine)


# ----------------------------------------------------------------------------- jouabilité (D9)
def test_carte_sans_effet_est_jouable():
    assert carte_jouable(_carte(), {}) is True


def test_carte_tous_effets_scriptes_est_jouable():
    reg = {"a": SCRIPT_STATUT_SCRIPTE, "b": SCRIPT_STATUT_SCRIPTE}
    assert carte_jouable(_carte(_eff("a"), _eff("b", "talent")), reg) is True


def test_un_seul_effet_non_scripte_bloque_toute_la_carte():
    reg = {"a": SCRIPT_STATUT_SCRIPTE}  # "b" absent
    carte = _carte(_eff("a"), _eff("b", "talent"))
    assert carte_jouable(carte, reg) is False


def test_raison_blocage_nomme_origine_et_absence():
    carte = _carte(_eff("x", "talent"))
    raison = raison_blocage(carte, {})
    assert raison is not None
    assert "talent" in raison and "aucun script" in raison


def test_raison_blocage_none_si_jouable():
    assert raison_blocage(_carte(_eff("a")), {"a": SCRIPT_STATUT_SCRIPTE}) is None


def test_statut_non_supporte_et_a_revoir_bloquent():
    for st in (SCRIPT_STATUT_NON_SUPPORTE, SCRIPT_STATUT_A_REVOIR):
        assert carte_jouable(_carte(_eff("e")), {"e": st}) is False


# -------------------------------------------------------------------------- couverture effets
def test_couverture_effets_compte_empreintes_distinctes_par_statut():
    cartes = [
        _carte(_eff("a"), _eff("b")),
        _carte(_eff("a"), _eff("c")),  # "a" partagé : compté une fois
        _carte(_eff("d")),
    ]
    reg = {
        "a": SCRIPT_STATUT_SCRIPTE,
        "b": SCRIPT_STATUT_NON_SUPPORTE,
        "c": SCRIPT_STATUT_A_REVOIR,
        # "d" absent
    }
    cv = couverture_effets(cartes, reg)
    assert cv.effets_distincts == 4
    assert cv.scriptes == 1
    assert cv.non_supportes == 1
    assert cv.a_revoir == 1
    assert cv.absents == 1
    assert cv.pct_scriptes == 25.0


def test_couverture_effets_vide_ne_divise_pas_par_zero():
    cv = couverture_effets([_carte()], {})
    assert cv.effets_distincts == 0
    assert cv.pct_scriptes == 0.0


# --------------------------------------------------------------------------- couverture cartes
def test_couverture_cartes_pct_sur_cartes_avec_effet():
    # 1 carte sans effet (jouable d'office), 1 jouable, 1 bloquée.
    cartes = [
        _carte(),
        _carte(_eff("a")),
        _carte(_eff("b")),
    ]
    reg = {"a": SCRIPT_STATUT_SCRIPTE}  # "b" absent
    cv = couverture_cartes(cartes, reg)
    assert cv.cartes_total == 3
    assert cv.avec_effet == 2
    assert cv.jouables == 2  # la sans-effet + la scriptée
    assert cv.jouables_avec_effet == 1
    assert cv.pct == 50.0  # 1 jouable sur 2 porteuses d'effet, pas sur 3


# -------------------------------------------------------------------------------- par famille
def test_couverture_par_famille_groupe_par_origine():
    cartes = [
        _carte(_eff("t1", "talent"), _eff("a1", "attaque")),
        _carte(_eff("a2", "attaque")),
    ]
    reg = {"t1": SCRIPT_STATUT_SCRIPTE, "a1": SCRIPT_STATUT_SCRIPTE}  # a2 absent
    groupes = {g.libelle: g.couverture for g in couverture_par_famille(cartes, reg)}
    assert groupes["talent"].pct == 100.0
    assert groupes["attaque"].avec_effet == 2
    assert groupes["attaque"].jouables_avec_effet == 1
    assert groupes["attaque"].pct == 50.0


# ------------------------------------------------------------------------------ par extension
def test_couverture_par_extension_triee_moins_couverte_dabord():
    cartes = [
        _carte(_eff("a"), set_id=SET_A),  # A : jouable
        _carte(_eff("b"), set_id=SET_B),  # B : bloquée
    ]
    reg = {"a": SCRIPT_STATUT_SCRIPTE}
    libelles = {SET_A: "Extension A", SET_B: "Extension B"}
    groupes = couverture_par_extension(cartes, reg, libelles)
    assert [g.libelle for g in groupes] == ["Extension B", "Extension A"]  # 0 % avant 100 %
    assert groupes[0].couverture.pct == 0.0


# ----------------------------------------------------------------------------- par collection
def test_couverture_collections_mesure_le_possede_seulement():
    c_jouable = _carte(_eff("a"))
    c_bloquee = _carte(_eff("b"))
    c_absente_du_registre = _carte(_eff("c"))
    cartes_par_id = {c.card_id: c for c in (c_jouable, c_bloquee, c_absente_du_registre)}
    reg = {"a": SCRIPT_STATUT_SCRIPTE}
    collections = [
        (uuid.uuid4(), "aymeric", {c_jouable.card_id, c_bloquee.card_id}),
        (uuid.uuid4(), "zoe", {c_jouable.card_id}),
    ]
    res = {c.pseudo: c for c in couverture_collections(collections, cartes_par_id, reg)}
    assert res["aymeric"].possedees_distinctes == 2
    assert res["aymeric"].avec_effet == 2
    assert res["aymeric"].jouables == 1
    assert res["aymeric"].pct == 50.0
    assert res["zoe"].pct == 100.0


# ------------------------------------------------------------------- cartes qui bloquent le plus
def test_classer_cartes_manquantes_trie_par_decks_puis_joueurs():
    bloque_bcp = _carte(_eff("x"))
    bloque_peu = _carte(_eff("y"))
    jouable = _carte(_eff("z"))
    reg = {"z": SCRIPT_STATUT_SCRIPTE}  # x, y absents
    noms = {bloque_bcp.card_id: "Super Carte", bloque_peu.card_id: "Petite Carte"}
    decks = {bloque_bcp.card_id: 5, bloque_peu.card_id: 1}
    joueurs = {bloque_bcp.card_id: 3, bloque_peu.card_id: 2}
    exemplaires = {bloque_bcp.card_id: 10, bloque_peu.card_id: 4}
    classement = classer_cartes_manquantes(
        [bloque_bcp, bloque_peu, jouable], reg, noms, {}, decks, joueurs, exemplaires
    )
    assert [m.nom for m in classement] == ["Super Carte", "Petite Carte"]  # jouable exclue
    assert classement[0].decks_bloques == 5
    assert classement[0].joueurs_concernes == 3


def test_classer_cartes_manquantes_respecte_la_limite():
    cartes = [_carte(_eff(f"e{i}")) for i in range(5)]
    reg: dict[str, str] = {}
    noms = {c.card_id: f"C{i}" for i, c in enumerate(cartes)}
    classement = classer_cartes_manquantes(cartes, reg, noms, {}, {}, {}, {}, limite=2)
    assert len(classement) == 2


def test_statut_absent_est_la_valeur_par_defaut():
    # Documente le contrat : une empreinte hors registre vaut STATUT_ABSENT, jamais None/KeyError.
    carte = _carte(_eff("inconnue"))
    assert carte_jouable(carte, {}) is False
    assert STATUT_ABSENT == "absent"
