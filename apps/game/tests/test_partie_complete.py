"""Une **partie complète** jouée par le moteur jusqu'à la victoire par les récompenses, et rejouée.

Preuve du jalon J1 au niveau du moteur (lot ``j-coups-joueur``) : deux decks Pokémon + Énergies de
base s'affrontent de la mise en place jusqu'à ce qu'un joueur prenne sa **sixième** récompense
(R-14.1 cas 1), *tout passe par le journal* (mise en place, pioche de début de tour, coups des
joueurs, Pokémon Checkup, fin de partie), et **rejouer le journal redonne l'état final à
l'identique** — ce que ``rejouer`` vérifie empreinte par empreinte.

L'orchestration (coups système entre les tours) et la stratégie des deux « joueurs » sont ici des
helpers de test ; côté produit, c'est le service de parties (``apps/api``) qui tient ce rôle, en
rejouant la **même** liste d'actions légales. La CI fait foi.
"""

from __future__ import annotations

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import CatalogueJeu, _fiches, familles_jeu
from pbm_game.cartes import AttaqueDef, DefinitionCarte, definition_vers_dict
from pbm_game.cartes.energie import DefinitionEnergie
from pbm_game.combat.modele import CoutAttaque
from pbm_game.journal import (
    AUTEUR_SYSTEME,
    RAISON_DERNIERE_RECOMPENSE,
    Action,
    empreinte,
    jouer,
    partie_neuve,
    rejouer,
)
from pbm_game.journal.modele import (
    ACTION_ATTACHER_ENERGIE,
    ACTION_AVANCER_PHASE,
    ACTION_CHECKUP,
    ACTION_DEBUT_TOUR,
    ACTION_DECLARER_ATTAQUE,
    ACTION_MISE_EN_PLACE_INITIALE,
    ACTION_PLACER_MISE_EN_PLACE,
    ACTION_PROMOUVOIR,
)
from pbm_game.state import PHASE_CHECKUP, PHASE_PIOCHE, Carte, EtatPartie, Joueur, Tour

# --- Catalogue : un attaquant (Pikachu), une cible à 3 récompenses, une énergie de base --------
PIKA = DefinitionCarte(
    ref="pika", nom="Pikachu", stade="base", pv=60, type="electrique", marqueur="ordinaire",
    cout_retraite=1,
    attaques=(AttaqueDef("Charge Foudre", CoutAttaque(types={"electrique": 1}), 60),),
)
# Cible « tag_team » = 3 récompenses (R-13.3) ; 60 PV → mise K.O. en un coup ; aucune attaque
# (le défenseur ne riposte pas, la partie reste déterministe).
TAG = DefinitionCarte(
    ref="tag", nom="Duo Tag", stade="base", pv=60, type="incolore", marqueur="tag_team",
    cout_retraite=0, attaques=(),
)
ENERGIE = DefinitionEnergie(ref="e-elec", nom="Énergie Électrique", fournit={"electrique": 1})

CAT = CatalogueJeu(
    pokemon={PIKA.ref: PIKA, TAG.ref: TAG},
    energies={ENERGIE.ref: ENERGIE},
)
# ``definitions`` pour la mise en place : fiche par ref (le stade suffit ; énergie = non-base).
DEFS = {
    PIKA.ref: definition_vers_dict(PIKA),
    TAG.ref: definition_vers_dict(TAG),
    ENERGIE.ref: {"stade": "energie"},
}
GRAINE = b"partie-complete!".hex()  # 16 octets → hex


def _deck(prefixe: str, refs: list[str]) -> tuple[Carte, ...]:
    return tuple(Carte(instance_id=f"{prefixe}-{i}", ref=r) for i, r in enumerate(refs))


def _etat_initial() -> EtatPartie:
    """Deux decks en pioche, tour 1 phase pioche sur le siège 0 (comme le fait le service)."""
    alice = Joueur(id="alice", pioche=_deck("alice", ["pika"] * 6 + ["e-elec"] * 10))
    bob = Joueur(id="bob", pioche=_deck("bob", ["tag"] * 16))
    return EtatPartie(
        joueurs=(alice, bob), tour=Tour(joueur_actif="alice", numero=1, phase=PHASE_PIOCHE)
    )


def _choisir_placement(joueur: Joueur) -> tuple[str, list[str]]:
    """Choisit l'Actif (première base en main) et jusqu'à cinq bases au banc (R-4.2)."""
    bases = [
        c for c in joueur.main if (d := CAT.pokemon_de(c.ref)) is not None and d.stade == "base"
    ]
    return bases[0].instance_id, [c.instance_id for c in bases[1:6]]


def _strategie(etat: EtatPartie, jid: str) -> Action | None:
    """Joueur minimal : promouvoir si Actif absent, sinon attaquer, sinon charger, sinon passer."""
    legales = actions_legales(etat, jid, familles=familles_jeu(CAT))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    if ACTION_PROMOUVOIR in par_type:
        return par_type[ACTION_PROMOUVOIR][0].action
    if ACTION_DECLARER_ATTAQUE in par_type:
        return par_type[ACTION_DECLARER_ATTAQUE][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    actif_sans_energie = joueur.actif is not None and not joueur.actif.energies
    if ACTION_ATTACHER_ENERGIE in par_type and actif_sans_energie:
        return par_type[ACTION_ATTACHER_ENERGIE][0].action
    if ACTION_AVANCER_PHASE in par_type:
        return par_type[ACTION_AVANCER_PHASE][0].action
    return None


def test_partie_complete_jusqua_la_victoire_par_recompenses_et_rejeu_identique():
    etat = _etat_initial()
    partie = partie_neuve(etat, GRAINE)
    rng = __import__("pbm_game.rng", fromlist=["Rng"]).Rng(bytes.fromhex(GRAINE))
    ts = "2026-10-03T00:00:00+00:00"

    def joue(action: Action) -> None:
        nonlocal partie, etat
        partie, etat = jouer(partie, action, ts, etat, rng)

    # 1) Mise en place système (mélange, pioche de sept, mulligans) — tout par le journal.
    joue(Action(ACTION_MISE_EN_PLACE_INITIALE, AUTEUR_SYSTEME, {"definitions": DEFS}))

    # 2) Boucle d'orchestration : placement, coups système entre les tours, coups des joueurs.
    for _ in range(600):
        if etat.terminee:
            break
        if etat.mise_en_place is not None:
            for idx, placement in enumerate(etat.mise_en_place.placements):
                if placement is None:
                    jid = etat.joueurs[idx].id
                    actif, banc = _choisir_placement(etat.joueurs[idx])
                    joue(Action(ACTION_PLACER_MISE_EN_PLACE, jid,
                                {"actif": actif, "banc": banc, "definitions": DEFS}))
                    break
            continue
        phase = etat.tour.phase
        if phase == PHASE_PIOCHE:
            joue(Action(ACTION_DEBUT_TOUR, AUTEUR_SYSTEME))
            continue
        if phase == PHASE_CHECKUP:
            joue(Action(ACTION_CHECKUP, AUTEUR_SYSTEME, {"fiches": _fiches(CAT, etat)}))
            if etat.terminee:
                break
            joue(Action(ACTION_AVANCER_PHASE, etat.tour.joueur_actif))
            continue
        action = _strategie(etat, etat.tour.joueur_actif)
        assert action is not None, f"aucun coup pour {etat.tour.joueur_actif} en phase {phase}"
        joue(action)

    # 3) La partie est finie, et c'est une victoire PAR LES RÉCOMPENSES (R-14.1 cas 1).
    assert etat.terminee, "la partie aurait dû se terminer"
    assert etat.vainqueur == "alice", f"vainqueur inattendu : {etat.vainqueur}"
    assert etat.raison_fin == RAISON_DERNIERE_RECOMPENSE, f"raison : {etat.raison_fin}"
    # Le perdant a encore des Pokémon en jeu (sinon ce serait « sans Pokémon »).
    bob = next(j for j in etat.joueurs if j.id == "bob")
    assert bob.actif is not None or bob.banc, "bob ne devait pas être sans Pokémon"

    # 4) Tout est rejouable : rejouer le journal redonne l'état final à l'identique (empreinte par
    #    empreinte, vérifié par rejouer lui-même).
    etat_rejoue, _ = rejouer(partie)
    assert empreinte(etat_rejoue) == empreinte(etat)
    assert etat_rejoue.terminee and etat_rejoue.vainqueur == "alice"
    # Une partie non triviale : la mise en place, plusieurs tours et la fin sont dans le journal.
    assert len(partie.entrees) > 15
