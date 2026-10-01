"""Tests des **états spéciaux** — pose, matrice de cumul, confusion, guérison (lot
``j-etats-speciaux``, R-11).

Le moteur est **pur** : chaque test construit un état, appelle une fonction et contrôle le
résultat ; aucune base, aucun réseau. Chaque test de règle **cite son identifiant** ``R-x.y``
dans son nom et son docstring, et un test final vérifie que chaque règle citée existe bel et bien
dans le corpus ``docs/jeu/REGLES.md``.

Sans le paquet ``pbm_game.etats`` (le livrable de ce lot), l'import en tête échoue : toute la
suite échoue alors, ce qui est la preuve exigée « un test qui échoue sans le changement ».
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from pbm_game.etats import (
    CONFUSION_COMPTEURS,
    appliquer_etat,
    etat_bloquant_attaque,
    resoudre_etats_avant_attaque,
    soigner_etats_speciaux,
)
from pbm_game.journal import (
    ACTION_DECLARER_ATTAQUE,
    EVT_ATTAQUE_DECLAREE,
    EVT_CONFUSION,
    Action,
    appliquer,
)
from pbm_game.regles import identifiants_definis
from pbm_game.rng import FACE, PILE, Rng, flux_confusion
from pbm_game.state import (
    BRULE,
    CONFUS,
    EMPOISONNE,
    ENDORMI,
    ETATS_SPECIAUX,
    ORIENTATION_NORMALE,
    PARALYSE,
    PHASE_CHECKUP,
    PHASE_PRINCIPALE,
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
    assert_invariants,
    orientation,
    verifier,
    vue,
)

RACINE_DEPOT = Path(__file__).resolve().parents[3]
CHEMIN_REGLES = RACINE_DEPOT / "docs" / "jeu" / "REGLES.md"
GRAINE_HEX = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # 16 octets (minimum du Rng)


def _rng(graine: bytes | None = None) -> Rng:
    return Rng(graine if graine is not None else bytes.fromhex(GRAINE_HEX))


def _pk(
    tag: str = "actif",
    *,
    etats: frozenset[str] = frozenset(),
    compteurs: int = 0,
    energies: tuple[Carte, ...] = (),
) -> PokemonEnJeu:
    return PokemonEnJeu(
        cartes=(Carte(f"id-{tag}", "ref-pk"),),
        energies=energies,
        compteurs_degats=compteurs,
        etats_speciaux=etats,
    )


def _graine_pour_confusion(jid: str, face_voulue: str) -> bytes:
    """Une graine dont le **premier** tirage du flux de confusion de ``jid`` donne ``face_voulue``.

    Le tirage de confusion à la déclaration d'attaque est le tirage d'indice 0 de ce flux (aucun
    autre usage ne le touche) : un ``Rng`` neuf sous cette graine donne donc le même résultat que
    le moteur. On cherche de façon déterministe (compteur croissant) — jamais un ``os.urandom``.
    """
    for n in range(10_000):
        graine = (b"confus-seed-" + str(n).encode()).ljust(16, b"\x00")
        if Rng(graine).pile_ou_face(flux_confusion(jid), "sonde") == face_voulue:
            return graine
    raise AssertionError(f"Aucune graine trouvée pour {face_voulue} (flux {jid}).")


# =========================================================================================
# Pureté / API — le moteur ne connaît ni HTTP, ni base, ni React
# =========================================================================================


def test_import_etats_ne_tire_aucune_dependance_lourde():
    """Le moteur est pur : importer ``pbm_game.etats`` ne charge ni HTTP, ni base, ni React."""
    interdits = {"requests", "httpx", "fastapi", "sqlalchemy", "psycopg", "redis", "boto3"}
    avant = set(sys.modules)
    importlib.import_module("pbm_game.etats")
    nouveaux = set(sys.modules) - avant
    assert not (interdits & nouveaux), f"Dépendances interdites tirées : {interdits & nouveaux}"


def test_appliquer_etat_ne_mute_pas_l_entree():
    """Fonction pure : le Pokémon figé passé en entrée n'est jamais modifié sur place."""
    pk = _pk(etats=frozenset({BRULE}))
    appliquer_etat(pk, ENDORMI)
    assert pk.etats_speciaux == frozenset({BRULE})


# =========================================================================================
# Matrice de cumul (R-11.8) — testée EXHAUSTIVEMENT, toutes les paires
# =========================================================================================

# La matrice EXACTE de ``docs/jeu/REGLES.md`` (R-11.8), recopiée à la main ici pour qu'une
# implémentation qui en diverge soit prise en défaut (ne pas la recalculer avec la même logique
# que le code — ce serait tautologique). Clé : (état en place, état posé) → ensemble résultant.
_EN_PLACE = {
    "—": frozenset(),
    ENDORMI: frozenset({ENDORMI}),
    CONFUS: frozenset({CONFUS}),
    PARALYSE: frozenset({PARALYSE}),
    BRULE: frozenset({BRULE}),
    EMPOISONNE: frozenset({EMPOISONNE}),
}
_MATRICE_R118 = {
    # posé = Endormi : remplace toute orientation, garde les marqueurs.
    (ENDORMI, "—"): {ENDORMI},
    (ENDORMI, ENDORMI): {ENDORMI},
    (ENDORMI, CONFUS): {ENDORMI},
    (ENDORMI, PARALYSE): {ENDORMI},
    (ENDORMI, BRULE): {ENDORMI, BRULE},
    (ENDORMI, EMPOISONNE): {ENDORMI, EMPOISONNE},
    # posé = Confus.
    (CONFUS, "—"): {CONFUS},
    (CONFUS, ENDORMI): {CONFUS},
    (CONFUS, CONFUS): {CONFUS},
    (CONFUS, PARALYSE): {CONFUS},
    (CONFUS, BRULE): {CONFUS, BRULE},
    (CONFUS, EMPOISONNE): {CONFUS, EMPOISONNE},
    # posé = Paralysé.
    (PARALYSE, "—"): {PARALYSE},
    (PARALYSE, ENDORMI): {PARALYSE},
    (PARALYSE, CONFUS): {PARALYSE},
    (PARALYSE, PARALYSE): {PARALYSE},
    (PARALYSE, BRULE): {PARALYSE, BRULE},
    (PARALYSE, EMPOISONNE): {PARALYSE, EMPOISONNE},
    # posé = Brûlé : marqueur, cumulable avec l'orientation et l'autre marqueur.
    (BRULE, "—"): {BRULE},
    (BRULE, ENDORMI): {ENDORMI, BRULE},
    (BRULE, CONFUS): {CONFUS, BRULE},
    (BRULE, PARALYSE): {PARALYSE, BRULE},
    (BRULE, BRULE): {BRULE},
    (BRULE, EMPOISONNE): {BRULE, EMPOISONNE},
    # posé = Empoisonné : marqueur.
    (EMPOISONNE, "—"): {EMPOISONNE},
    (EMPOISONNE, ENDORMI): {ENDORMI, EMPOISONNE},
    (EMPOISONNE, CONFUS): {CONFUS, EMPOISONNE},
    (EMPOISONNE, PARALYSE): {PARALYSE, EMPOISONNE},
    (EMPOISONNE, BRULE): {BRULE, EMPOISONNE},
    (EMPOISONNE, EMPOISONNE): {EMPOISONNE},
}


@pytest.mark.parametrize("pose", sorted(ETATS_SPECIAUX))
@pytest.mark.parametrize("en_place_nom", sorted(_EN_PLACE))
def test_matrice_de_cumul_exhaustive_r118(en_place_nom: str, pose: str):
    """R-11.8 — chaque paire (état en place, état posé) donne EXACTEMENT la matrice du corpus.

    Critère d'acceptation : « la matrice de cumul est testée exhaustivement (toutes les paires) ».
    6 états en place (dont « aucun ») × 5 états posés = 30 paires, comparées à la table écrite.
    """
    base = _pk(etats=_EN_PLACE[en_place_nom])
    resultat = appliquer_etat(base, pose)
    attendu = _MATRICE_R118[(pose, en_place_nom)]
    assert set(resultat.etats_speciaux) == attendu
    # L'état résultant est toujours cohérent : au plus un état d'orientation (R-11.8).
    assert verifier(_etat_simple(resultat)) == []
    orientation(resultat)  # ne lève jamais (jamais deux orientations à la fois)


def _etat_simple(actif: PokemonEnJeu) -> EtatPartie:
    """Un état minimal valide portant ``actif`` chez alice — pour passer ``verifier``."""
    alice = Joueur(id="alice", actif=actif)
    bob = Joueur(id="bob", actif=_pk("bob"))
    return EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 3, PHASE_PRINCIPALE))


def test_appliquer_etat_refuse_un_etat_inconnu_d9():
    """Un état inconnu est une panne (D9) : jamais posé « au mieux »."""
    with pytest.raises(ValueError, match="État spécial inconnu"):
        appliquer_etat(_pk(), "petrifie")


# =========================================================================================
# Un cas par état (R-11.1) et par combinaison AUTORISÉE (R-11.8)
# =========================================================================================


@pytest.mark.parametrize("etat", sorted(ETATS_SPECIAUX))
def test_chaque_etat_se_pose_seul_r111(etat: str):
    """R-11.1 — chacun des cinq états se pose sur un Pokémon sain."""
    pk = appliquer_etat(_pk(), etat)
    assert etat in pk.etats_speciaux
    assert len(pk.etats_speciaux) == 1


# Les combinaisons que R-11.8 autorise : un marqueur (Brûlé/Empoisonné) avec n'importe quelle
# orientation, les deux marqueurs ensemble, et l'exemple officiel Brûlé + Paralysé + Empoisonné.
_COMBOS_AUTORISES = [
    ({BRULE, EMPOISONNE}, "les deux marqueurs cumulent"),
    ({ENDORMI, BRULE}, "sommeil + brûlure"),
    ({ENDORMI, EMPOISONNE}, "sommeil + poison"),
    ({CONFUS, BRULE}, "confusion + brûlure"),
    ({CONFUS, EMPOISONNE}, "confusion + poison"),
    ({PARALYSE, BRULE}, "paralysie + brûlure"),
    ({PARALYSE, EMPOISONNE}, "paralysie + poison"),
    ({BRULE, PARALYSE, EMPOISONNE}, "exemple officiel du livret"),
]


@pytest.mark.parametrize("cible,nom", _COMBOS_AUTORISES, ids=[c[1] for c in _COMBOS_AUTORISES])
def test_combinaisons_autorisees_coexistent_r118(cible: set[str], nom: str):
    """R-11.8 — les combinaisons autorisées coexistent après pose successive (ordre indifférent)."""
    pk = _pk()
    for etat in sorted(cible):
        pk = appliquer_etat(pk, etat)
    assert set(pk.etats_speciaux) == cible


def test_orientation_derivee_du_dernier_etat_pose_r118():
    """R-11.8 — poser une orientation sur une autre remplace : c'est la dernière qui oriente."""
    pk = appliquer_etat(_pk(), CONFUS)
    assert orientation(pk) == CONFUS
    pk = appliquer_etat(pk, PARALYSE)  # remplace confus
    assert orientation(pk) == PARALYSE
    assert CONFUS not in pk.etats_speciaux


# =========================================================================================
# Guérison de TOUS les états (R-11.9) — passage au banc, évolution, effet de soin
# =========================================================================================


def test_soigner_retire_tous_les_etats_r119():
    """R-11.9 — la guérison partagée retire TOUS les états (sommeil, brûlure, poison ensemble)."""
    pk = _pk(
        etats=frozenset({ENDORMI, BRULE, EMPOISONNE}), compteurs=30, energies=(Carte("e", "r"),)
    )
    gueri = soigner_etats_speciaux(pk)
    assert gueri.etats_speciaux == frozenset()
    # Ne touche QU'aux états : compteurs et énergies conservés (R-8.6 pour le banc).
    assert gueri.compteurs_degats == 30
    assert gueri.energies == pk.energies


def test_soigner_sans_etat_renvoie_le_meme_objet():
    """Pureté/économie : soigner un Pokémon sans état ne crée pas de copie inutile."""
    pk = _pk()
    assert soigner_etats_speciaux(pk) is pk


def test_guerison_par_passage_au_banc_r119():
    """R-11.9 — la retraite (passage au banc) guérit tous les états de l'Actif qui descend.

    C'est le chemin déjà livré par ``j-retraite-banc``, qui route désormais sa guérison par la
    porte partagée :func:`soigner_etats_speciaux`.
    """
    from pbm_game.banc import battre_en_retraite

    # Confus + Brûlé : la confusion n'empêche pas la retraite (R-11.10 ne vise qu'Endormi/Paralysé).
    actif = _pk("actif", etats=frozenset({CONFUS, BRULE}), compteurs=20)
    remplacant = _pk("banc")
    alice = Joueur(id="alice", actif=actif, banc=(remplacant,))
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 3, PHASE_PRINCIPALE))

    etat2, _ = battre_en_retraite(etat, "alice", 0, 0, ())
    descendu = etat2.joueurs[0].banc[0]
    assert descendu.etats_speciaux == frozenset()  # guéri (R-11.9)
    assert descendu.compteurs_degats == 20  # mais garde ses compteurs (R-8.6)


# =========================================================================================
# etat_bloquant_attaque (R-11.3/R-11.6/R-11.10) — qui empêche d'attaquer / de se retirer
# =========================================================================================


@pytest.mark.parametrize("etat,bloque", [
    (ENDORMI, True), (PARALYSE, True), (CONFUS, False), (BRULE, False), (EMPOISONNE, False),
])
def test_etat_bloquant_attaque_r113_r116(etat: str, bloque: bool):
    """R-11.3/R-11.6 — seuls Endormi et Paralysé empêchent d'attaquer ; les autres non."""
    pk = _pk(etats=frozenset({etat}))
    resultat = etat_bloquant_attaque(pk)
    assert (resultat == etat) if bloque else (resultat is None)


# =========================================================================================
# Attaque sous état — bloquée sous Sommeil/Paralysie, confusion = pile ou face (R-11.3/5/6)
# =========================================================================================


def _etat_pour_attaque(etats_actif: frozenset[str], *, compteurs: int = 0) -> EtatPartie:
    """État en phase principale, tour 3 d'alice (pas le premier tour), prêt pour une attaque."""
    alice = Joueur(id="alice", actif=_pk("alice", etats=etats_actif, compteurs=compteurs))
    bob = Joueur(id="bob", actif=_pk("bob"))
    return EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 3, PHASE_PRINCIPALE))


@pytest.mark.parametrize("etat", [ENDORMI, PARALYSE])
def test_declarer_attaque_refusee_sous_sommeil_ou_paralysie_r113_r116(etat: str):
    """R-11.3/R-11.6 — un Pokémon endormi ou paralysé ne peut pas attaquer : refus motivé."""
    etat_partie = _etat_pour_attaque(frozenset({etat}))
    with pytest.raises(ValueError, match="ne peut pas attaquer"):
        appliquer(etat_partie, Action(ACTION_DECLARER_ATTAQUE, "alice"), _rng())


def test_confusion_face_attaque_a_lieu_r115():
    """R-11.5 — confusion + FACE : l'attaque a lieu normalement (aucun auto-dégât)."""
    etat_partie = _etat_pour_attaque(frozenset({CONFUS}))
    graine = _graine_pour_confusion("alice", FACE)
    etat2, evts = appliquer(etat_partie, Action(ACTION_DECLARER_ATTAQUE, "alice"), _rng(graine))

    confusions = [e for e in evts if e.type == EVT_CONFUSION]
    assert len(confusions) == 1
    assert confusions[0].donnees["pile_ou_face"] == FACE
    assert confusions[0].donnees["attaque_annulee"] is False
    # L'attaque a bien été déclarée, aucun compteur posé sur soi.
    assert any(e.type == EVT_ATTAQUE_DECLAREE for e in evts)
    assert etat2.joueurs[0].actif.compteurs_degats == 0
    # Le tour se termine quand même (R-5.8) : on entre en phase checkup.
    assert etat2.tour.phase == PHASE_CHECKUP


def test_confusion_pile_attaque_annulee_et_3_compteurs_r115():
    """R-11.5 — confusion + PILE : l'attaque n'a PAS lieu, 3 compteurs sur le Pokémon confus."""
    etat_partie = _etat_pour_attaque(frozenset({CONFUS}), compteurs=10)
    graine = _graine_pour_confusion("alice", PILE)
    etat2, evts = appliquer(etat_partie, Action(ACTION_DECLARER_ATTAQUE, "alice"), _rng(graine))

    confusions = [e for e in evts if e.type == EVT_CONFUSION]
    assert len(confusions) == 1
    assert confusions[0].donnees["pile_ou_face"] == PILE
    assert confusions[0].donnees["attaque_annulee"] is True
    assert confusions[0].donnees["degats"] == CONFUSION_COMPTEURS * 10
    # Pas d'attaque déclarée (elle n'a pas eu lieu), mais +30 dégâts (3 compteurs) sur soi.
    assert not any(e.type == EVT_ATTAQUE_DECLAREE for e in evts)
    assert etat2.joueurs[0].actif.compteurs_degats == 10 + CONFUSION_COMPTEURS * 10
    # Le tour se termine malgré tout (R-5.8).
    assert etat2.tour.phase == PHASE_CHECKUP


def test_confusion_est_deterministe_et_journalisee_r115():
    """R-11.5 — le pile ou face de confusion est reproductible et journalisé (rejouabilité J1)."""
    graine = _graine_pour_confusion("alice", PILE)
    rng = _rng(graine)
    etat, attaque_a_lieu, evts = resoudre_etats_avant_attaque(
        _etat_pour_attaque(frozenset({CONFUS})), "alice", rng
    )
    assert attaque_a_lieu is False
    # Le tirage est journalisé dans le flux de confusion, avec son motif citant la règle.
    tirages = [t for t in rng.journal() if t.flux == flux_confusion("alice")]
    assert len(tirages) == 1 and "R-11.5" in tirages[0].motif
    # Rejoué sous la même graine → même résultat (déterminisme).
    _, attaque_a_lieu2, _ = resoudre_etats_avant_attaque(
        _etat_pour_attaque(frozenset({CONFUS})), "alice", _rng(graine)
    )
    assert attaque_a_lieu2 is False


def test_marqueurs_seuls_n_empechent_pas_d_attaquer_r114_r117():
    """R-11.4/R-11.7 — Brûlé/Empoisonné (marqueurs) n'empêchent pas de déclarer l'attaque."""
    etat_partie = _etat_pour_attaque(frozenset({BRULE, EMPOISONNE}))
    etat2, evts = appliquer(etat_partie, Action(ACTION_DECLARER_ATTAQUE, "alice"), _rng())
    assert any(e.type == EVT_ATTAQUE_DECLAREE for e in evts)
    assert etat2.tour.phase == PHASE_CHECKUP


# =========================================================================================
# Orientation exposée au client (R-11.8) — l'interface la montre sans redériver la règle
# =========================================================================================


@pytest.mark.parametrize("etats,attendu", [
    (frozenset(), ORIENTATION_NORMALE),
    (frozenset({ENDORMI}), ENDORMI),
    (frozenset({PARALYSE, BRULE}), PARALYSE),
    (frozenset({BRULE, EMPOISONNE}), ORIENTATION_NORMALE),  # marqueurs seuls = carte droite
])
def test_projection_expose_l_orientation_r118(etats: frozenset[str], attendu: str):
    """R-11.8 — la vue par joueur porte l'orientation de chaque Pokémon, dérivée par le moteur."""
    etat = _etat_pour_attaque(etats)
    v = vue(etat, "alice")
    actif_vu = v["joueurs"][0]["actif"]
    assert actif_vu["orientation"] == attendu


# =========================================================================================
# Compteurs de poison/brûlure au Checkup (R-11.4/R-11.7/R-12.2) — « au bon moment »
# =========================================================================================


def test_poison_et_brulure_posent_leurs_compteurs_au_checkup_r117_r114():
    """R-11.7/R-11.4/R-12.2 — poison (1) et brûlure (2) posent leurs compteurs au Checkup, et le
    pile ou face de brûlure y est journalisé (critère d'acceptation)."""
    from pbm_game.checkup import BRULURE_DEGATS, POISON_DEGATS, resoudre_checkup
    from pbm_game.journal import EVT_ETAT_CHECKUP
    from pbm_game.state import carte_active

    actif = _pk("alice", etats=frozenset({EMPOISONNE, BRULE}), compteurs=0)
    alice = Joueur(id="alice", actif=actif)
    bob = Joueur(id="bob", actif=_pk("bob"))
    etat = EtatPartie(joueurs=(alice, bob), tour=Tour("alice", 5, PHASE_CHECKUP))
    fiches = {carte_active(actif).instance_id: {"pv": 200, "recompenses": 1}}

    etat2, evts = resoudre_checkup(etat, _rng(), fiches=fiches)
    # 1 (poison) + 2 (brûlure) compteurs = 30 dégâts posés au Checkup.
    assert etat2.joueurs[0].actif.compteurs_degats == POISON_DEGATS + BRULURE_DEGATS == 30
    etats_evts = [e for e in evts if e.type == EVT_ETAT_CHECKUP]
    brule_evt = next(e for e in etats_evts if e.donnees["etat"] == BRULE)
    assert "pile_ou_face" in brule_evt.donnees  # le pile ou face de brûlure est journalisé (R-11.4)


# =========================================================================================
# Cohérence du corpus — chaque règle citée par ce lot existe dans REGLES.md
# =========================================================================================


def test_regles_citees_existent_dans_le_corpus():
    """Chaque ``R-x.y`` sur lequel ce lot s'appuie est bien défini dans ``docs/jeu/REGLES.md``."""
    assert CHEMIN_REGLES.is_file(), f"Corpus introuvable : {CHEMIN_REGLES}"
    definies = identifiants_definis(CHEMIN_REGLES.read_text(encoding="utf-8"))
    citees = {"R-11.1", "R-11.2", "R-11.3", "R-11.4", "R-11.5", "R-11.6",
              "R-11.7", "R-11.8", "R-11.9", "R-11.10", "R-12.2"}
    manquantes = citees - definies
    assert not manquantes, f"Règles citées absentes du corpus : {sorted(manquantes)}"


def test_etat_apres_pose_passe_les_invariants():
    """Poser n'importe quel état laisse un état de partie qui passe tous les invariants (R-11.8)."""
    pk = _pk()
    for etat in sorted(ETATS_SPECIAUX):
        pk = appliquer_etat(pk, etat)
    assert_invariants(_etat_simple(pk))
