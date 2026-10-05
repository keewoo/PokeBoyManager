"""Câblage des effets dans les **coups légaux** et le **calcul des dégâts** — lot
``j-effets-cablage-service`` (moteur pur).

Ce lot branche ce que les lots d'effets avaient laissé « à un lot ultérieur » côté familles de
coups : la famille **attacher un Outil** (``FamilleAttacherOutil``, R-3.7), la famille **activer un
talent** (``FamilleActiverTalent``, R-5), et la consultation des **modificateurs continus** (Outils,
Stades, talents) dans la résolution d'attaque (R-10.1). Chaque test **mord sans le changement** :
avant ce lot, ``attacher_outil``/``activer_talent`` n'étaient listés par aucune famille (coups
jamais proposés, refusés par ``valider``), et ``FamilleAttaquer`` n'embarquait aucun modificateur
continu dans ses ``params`` (les dégâts ignoraient Outils/Stades). La CI fait foi.
"""

from __future__ import annotations

from fabrique_dsl import carte, etat, joueur, pokemon

# ``import pbm_game`` enregistre les transitions d'effet (``attacher_outil``, ``activer_talent``…)
# dans le REGISTRE du journal : indispensable à ``appliquer``.
import pbm_game  # noqa: F401
from pbm_game.actions import actions_legales, valider
from pbm_game.actions.familles_jeu import (
    CatalogueJeu,
    DefinitionOutil,
    familles_jeu,
)
from pbm_game.cartes import AttaqueDef, DefinitionCarte
from pbm_game.cartes.energie import DefinitionEnergie
from pbm_game.combat.modele import CoutAttaque
from pbm_game.effets.outils import METAL_CORE_BARRIER, registre_outils
from pbm_game.effets.talents import NATURE_ACTIVE, Talent
from pbm_game.journal import appliquer
from pbm_game.journal.modele import (
    ACTION_ACTIVER_TALENT,
    ACTION_ATTACHER_OUTIL,
    ACTION_DECLARER_ATTAQUE,
    EVT_DEGATS,
    EVT_OUTIL_ATTACHE,
    EVT_TALENT_ACTIVE,
)
from pbm_game.rng import Rng

_RNG = Rng(b"cablage-effets-seed")


def _legaux(e, jid: str, cat: CatalogueJeu):
    return actions_legales(e, jid, familles=familles_jeu(cat))


def _un(e, jid: str, type_action: str, cat: CatalogueJeu):
    coups = [c for c in _legaux(e, jid, cat) if c.action.type == type_action]
    assert coups, f"aucun coup {type_action} listé"
    return coups[0]


# --- Attacher un Outil : R-3.7 ---------------------------------------------------------------

PIKA = DefinitionCarte(
    ref="pika", nom="Pikachu", stade="base", pv=60, type="electrique", marqueur="ordinaire",
    cout_retraite=1,
    attaques=(AttaqueDef("Éclair", CoutAttaque(types={"electrique": 1}), 30),),
)
PONCHO = DefinitionOutil(ref=METAL_CORE_BARRIER, nom="Metal Core Barrier")


def test_attacher_outil_liste_et_applique_r37():
    """Un Outil en main est listé pour chaque Pokémon **sans** Outil, et la transition l'attache."""
    cat = CatalogueJeu(pokemon={"pika": PIKA}, outils={METAL_CORE_BARRIER: PONCHO})
    actif = pokemon("a-pika", ref="pika")
    al = joueur("alice", actif=actif, main=(carte("outil-1", METAL_CORE_BARRIER),))
    bo = joueur("bob", actif=pokemon("b-pika", ref="pika"))
    e = etat(al, bo, numero=3, phase="principale")

    coup = _un(e, "alice", ACTION_ATTACHER_OUTIL, cat)
    assert coup.action.params["cible"] == actif.cartes[0].instance_id
    e2, evts = appliquer(e, coup.action, _RNG)
    assert any(ev.type == EVT_OUTIL_ATTACHE for ev in evts)
    assert e2.joueurs[0].actif.outil is not None
    assert e2.joueurs[0].actif.outil.ref == METAL_CORE_BARRIER
    # Une seule source de vérité : le coup listé est accepté par valider.
    assert not valider(e, coup.action, familles=familles_jeu(cat)).refuse


def test_pokemon_portant_deja_un_outil_nest_pas_relistes_r37():
    """R-3.7 — un Pokémon qui porte déjà un Outil n'apparaît pas comme cible d'attache."""
    cat = CatalogueJeu(pokemon={"pika": PIKA}, outils={METAL_CORE_BARRIER: PONCHO})
    actif = pokemon("a-pika", ref="pika", outil=carte("deja", "autre-outil"))
    al = joueur("alice", actif=actif, main=(carte("outil-1", METAL_CORE_BARRIER),))
    bo = joueur("bob", actif=pokemon("b-pika", ref="pika"))
    e = etat(al, bo, numero=3, phase="principale")
    assert not [c for c in _legaux(e, "alice", cat) if c.action.type == ACTION_ATTACHER_OUTIL]


# --- Outil continu dans le calcul des dégâts : R-10.1 ----------------------------------------

GARDE = DefinitionCarte(
    ref="garde", nom="Gardevoir", stade="base", pv=120, type="psy", marqueur="ordinaire",
    cout_retraite=1,
    attaques=(AttaqueDef("Choc", CoutAttaque(incolore=1), 60),),
)
METAGROSS = DefinitionCarte(
    ref="metagross", nom="Métalosse", stade="base", pv=150, type="metal", marqueur="ordinaire",
    cout_retraite=2, attaques=(),
)


def test_outil_metal_core_barrier_reduit_les_degats_r101():
    """Le porteur Metal subit −50 dégâts : l'attaque embarque le modificateur continu (R-10.1)."""
    meta = {"metagross": {"type": "metal"}}
    cat = CatalogueJeu(
        pokemon={"garde": GARDE, "metagross": METAGROSS},
        energies={"e-x": DefinitionEnergie(ref="e-x", nom="Énergie", fournit={"psy": 1})},
        registre_continus=registre_outils(meta),
    )
    attaquant = pokemon("a-garde", ref="garde", energies=(carte("en-1", "e-x"),))
    al = joueur("alice", actif=attaquant)
    cible = pokemon("b-meta", ref="metagross", outil=carte("mcb-1", METAL_CORE_BARRIER))
    bo = joueur("bob", actif=cible)
    e = etat(al, bo, numero=3, phase="principale")

    coup = _un(e, "alice", ACTION_DECLARER_ATTAQUE, cat)
    # Le modificateur défenseur continu est porté dans les params (le journal le transporte).
    mods = coup.action.params.get("modificateurs_defenseur")
    assert mods and any(m["valeur"] == -50 for m in mods), coup.action.params
    e2, evts = appliquer(e, coup.action, _RNG)
    degats = next(ev for ev in evts if ev.type == EVT_DEGATS)
    # 60 base − 50 (Metal Core Barrier) = 10. Sans le câblage, l'attaque ferait 60.
    assert degats.donnees["degats"] == 10


# --- Activer un talent : R-5 -----------------------------------------------------------------

PIOCHE_PROG = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}
BIBAREL = DefinitionCarte(
    ref="bibarel", nom="Castorno", stade="base", pv=100, type="incolore", marqueur="ordinaire",
    cout_retraite=1, attaques=(),
)
TALENT_PIOCHE = Talent(ref="bibarel", nom="Incisives Travailleuses", nature=NATURE_ACTIVE,
                       regle="R-5")


def _etat_talent():
    cat = CatalogueJeu(
        pokemon={"bibarel": BIBAREL},
        talents={"bibarel": TALENT_PIOCHE},
        talents_programmes={"bibarel": PIOCHE_PROG},
    )
    porteur = pokemon("a-bib", ref="bibarel")
    al = joueur("alice", actif=porteur, pioche=(carte("p1"), carte("p2")))
    bo = joueur("bob", actif=pokemon("b-pika", ref="pika"))
    e = etat(al, bo, numero=3, phase="principale")
    return cat, e


def test_activer_talent_liste_applique_et_une_fois_par_tour_r5():
    """Un talent activé en jeu est listé, résolu (pioche), puis plus relistes ce tour (R-5)."""
    cat, e = _etat_talent()
    coup = _un(e, "alice", ACTION_ACTIVER_TALENT, cat)
    assert coup.action.params["programme"] == PIOCHE_PROG
    e2, evts = appliquer(e, coup.action, _RNG)
    assert any(ev.type == EVT_TALENT_ACTIVE for ev in evts)
    assert len(e2.joueurs[0].main) == 1  # une carte piochée (R-5)
    assert len(e2.joueurs[0].pioche) == 1
    # R-5 — une seule fois par tour par Pokémon : le talent n'est plus listé après usage.
    assert not [c for c in _legaux(e2, "alice", cat) if c.action.type == ACTION_ACTIVER_TALENT]


def test_talent_active_sans_programme_non_liste_d9():
    """D9 — un talent activé **sans script** n'est jamais proposé (effet non implémenté)."""
    cat = CatalogueJeu(pokemon={"bibarel": BIBAREL}, talents={"bibarel": TALENT_PIOCHE})
    al = joueur("alice", actif=pokemon("a-bib", ref="bibarel"), pioche=(carte("p1"),))
    bo = joueur("bob", actif=pokemon("b-pika", ref="pika"))
    e = etat(al, bo, numero=3, phase="principale")
    assert not [c for c in _legaux(e, "alice", cat) if c.action.type == ACTION_ACTIVER_TALENT]
