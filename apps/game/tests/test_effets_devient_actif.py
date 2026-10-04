"""Le **passage par le bus** quand un appât change l'Actif (lot ``j-cartes-objets``).

Le risque central nommé par la fiche : « l'appât est aussi une carte qui déclenche des effets
adverses (« quand ce Pokémon devient actif… ») ; sans passage par le bus d'événements, ces
déclencheurs seront oubliés. » On le prouve ici : un appât note le Pokémon devenu Actif
(``ResultatProgramme.devenus_actifs``), et :func:`publier_devient_actif` **réveille** les réacteurs
abonnés à :data:`EJ_DEVIENT_ACTIF` — leurs effets se résolvent sur la pile.

Règles : R-8 (devient Actif), R-8.8 (échange forcé). La CI fait foi.
"""

from __future__ import annotations

from fabrique_dsl import contexte, etat, joueur, pokemon, rng

from pbm_game.effets.bus import Bus, publier_devient_actif
from pbm_game.effets.dsl.chargement import charger_programme
from pbm_game.effets.dsl.interprete import executer_programme
from pbm_game.effets.evenements import EJ_DEVIENT_ACTIF
from pbm_game.effets.pile import EVT_EFFET_RESOLU, EffetEnAttente, SourceEffet
from pbm_game.journal.modele import Evenement

# Un appât : « choisis 1 Pokémon du banc adverse et envoie-le au front » (type Gust of Wind).
APPAT = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        }
    ],
}

_MARQUEUR_PUBLIE = "talent_reveille"
_MARQUEUR_RESOLU = "reaction_resolue"


def _etat_appatable():
    """alice joue ; bob a un Actif et un banc d'un Pokémon fragile — cible de l'appât."""
    bob = joueur(
        "bob",
        actif=pokemon("bob-actif"),
        banc=(pokemon("bob-fragile"),),
    )
    alice = joueur("alice", actif=pokemon("alice-actif"))
    return etat(alice, bob)


def _appater(e):
    """Joue l'appât et renvoie ``(etat, devenus_actifs)``."""
    ctx = contexte("alice", "bob")
    resultat = executer_programme(e, charger_programme(APPAT), ctx, rng())
    return resultat.etat, resultat.devenus_actifs


def test_appat_note_le_pokemon_devenu_actif():
    """L'appât consigne le passage (joueur, identité) — la matière que le bus publiera (R-8)."""
    e = _etat_appatable()
    _, devenus = _appater(e)
    assert devenus == (("bob", "bob-fragile"),)


def test_publier_devient_actif_reveille_les_reacteurs():
    """Un réacteur abonné à EJ_DEVIENT_ACTIF empile son effet ; la pile se résout (R-8/R-8.8)."""

    def reacteur(etat_courant, evenement, pile, r):
        pokemon_id = evenement.donnees["pokemon"]
        effet = EffetEnAttente(
            type_effet="test_reaction",
            source=SourceEffet("Talent de test"),
            regle="R-8",
            libelle="réaction au front",
            params={"pokemon": pokemon_id},
        )
        return pile.empiler(effet), [Evenement(_MARQUEUR_PUBLIE, {"pokemon": pokemon_id})]

    def resolveur(etat_courant, effet, r):
        return etat_courant, [Evenement(_MARQUEUR_RESOLU, {"pokemon": effet.params["pokemon"]})], []

    bus = Bus().abonner(EJ_DEVIENT_ACTIF, reacteur)
    registre = {"test_reaction": resolveur}

    e = _etat_appatable()
    e, devenus = _appater(e)
    _, evenements = publier_devient_actif(e, devenus, bus, registre, rng())

    types = [ev.type for ev in evenements]
    # Le talent a été réveillé à la publication, puis son effet empilé s'est résolu sur la pile.
    assert _MARQUEUR_PUBLIE in types
    assert EVT_EFFET_RESOLU in types
    assert _MARQUEUR_RESOLU in types
    reveil = next(ev for ev in evenements if ev.type == _MARQUEUR_PUBLIE)
    assert reveil.donnees["pokemon"] == "bob-fragile"


def test_sans_reacteur_abonne_le_bus_ne_fait_rien():
    """Sans abonné à EJ_DEVIENT_ACTIF, aucun événement — l'absence réelle d'effet, pas un repli."""
    e = _etat_appatable()
    e, devenus = _appater(e)
    etat_apres, evenements = publier_devient_actif(e, devenus, Bus(), {}, rng())
    assert evenements == []
    assert etat_apres is e  # aucun réacteur : l'état ne bouge pas


def test_sans_devenu_actif_rien_a_publier():
    """Pas de changement d'Actif ⇒ rien à publier, même avec un bus garni."""

    def reacteur(etat_courant, evenement, pile, r):
        return pile, [Evenement(_MARQUEUR_PUBLIE, {})]

    bus = Bus().abonner(EJ_DEVIENT_ACTIF, reacteur)
    e = _etat_appatable()
    _, evenements = publier_devient_actif(e, [], bus, {}, rng())
    assert evenements == []
