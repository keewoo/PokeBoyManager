"""Point de sortie unique ``pbm_game.sortie.projeter`` — lot ``j-autorite-vues``.

Trois choses y sont vérifiées :

* **Non-fuite sur 1 000 états** : la sortie destinée à un joueur (vue + jetons de récompenses)
  ne contient **aucun** identifiant d'une zone cachée (pioches des deux joueurs, récompenses des
  deux joueurs, main de l'adversaire) — et aucun jeton ne coïncide par hasard avec un identifiant
  réel. Ce test tourne dans le job `game` de la CI, donc **à chaque lot** qui touche le moteur ou
  les scripts de cartes.
* **Projection des événements** : la pioche n'est pas décrite pareil aux deux joueurs ; un type
  d'événement sans projecteur est refusé.
* **Jetons de récompenses** : le propriétaire reçoit un jeton par récompense, l'adversaire non.
"""

from __future__ import annotations

import json

import pytest
from fabrique_etats import fabrique_etat

from pbm_game.journal.modele import EVT_CARTES_PIOCHEES, Evenement
from pbm_game.sortie import projeter, projeter_evenement
from pbm_game.sortie.jetons import Jetonneur, secret_jetons

GRAINE = b"\x33" * 32
SECRET = secret_jetons(GRAINE)


def _ids_interdits(etat, demandeur: str) -> set[str]:
    """instance_id ET ref des zones cachées au demandeur : pioches + récompenses (des deux) +
    main adverse."""
    interdits: set[str] = set()
    for j in etat.joueurs:
        for c in j.pioche:
            interdits |= {c.instance_id, c.ref}
        for c in j.recompenses:
            interdits |= {c.instance_id, c.ref}
        if j.id != demandeur:
            for c in j.main:
                interdits |= {c.instance_id, c.ref}
    return interdits


def test_projeter_ne_fuit_aucune_carte_cachee_sur_1000_etats():
    """Sur 1 000 états, la sortie d'un joueur (jetons compris) ne révèle aucune carte cachée."""
    for seed in range(1000):
        etat = fabrique_etat(seed)
        # Une époque qui varie avec la graine, pour exercer des jetons différents.
        jetonneur = Jetonneur(SECRET, epoque=seed % 5)
        for demandeur in ("alice", "bob"):
            sortie = projeter(etat, pour=demandeur, jetonneur=jetonneur)
            texte = json.dumps(sortie)
            for interdit in _ids_interdits(etat, demandeur):
                assert interdit not in texte, (
                    f"Fuite seed={seed}, sortie de {demandeur} : « {interdit} » visible."
                )


def test_jetons_recompenses_pour_le_proprietaire_seulement():
    """Le propriétaire reçoit un jeton par récompense ; l'adversaire n'a que le nombre."""
    etat = fabrique_etat(7)
    jetonneur = Jetonneur(SECRET, epoque=0)
    alice = next(j for j in etat.joueurs if j.id == "alice")
    sortie = projeter(etat, pour="alice", jetonneur=jetonneur)
    moi = next(j for j in sortie["vue"]["joueurs"] if j["id"] == "alice")
    adverse = next(j for j in sortie["vue"]["joueurs"] if j["id"] == "bob")
    assert len(moi["recompenses_jetons"]) == len(alice.recompenses)
    assert moi["recompenses_jetons"] == [jetonneur.jeton(c.instance_id) for c in alice.recompenses]
    # Le regard d'alice sur bob ne porte jamais de jetons de récompenses, seulement un nombre.
    assert "recompenses_jetons" not in adverse


def test_sans_jetonneur_la_vue_reste_en_nombres():
    """Sans jetonneur fourni, aucun jeton n'est ajouté (un bot/test n'a pas à en fabriquer)."""
    etat = fabrique_etat(7)
    sortie = projeter(etat, pour="alice")
    moi = next(j for j in sortie["vue"]["joueurs"] if j["id"] == "alice")
    assert "recompenses_jetons" not in moi


def test_pioche_decrite_differemment_aux_deux_joueurs():
    """R-5.2 : le piocheur voit les identités tirées ; l'adversaire n'a que le nombre."""
    evt = Evenement(
        EVT_CARTES_PIOCHEES,
        {"joueur": "alice", "nombre": 2, "instance_ids": ["alice-pioche-1", "alice-pioche-2"]},
    )
    pour_alice = projeter_evenement(evt, pour="alice")
    pour_bob = projeter_evenement(evt, pour="bob")
    assert pour_alice.donnees["instance_ids"] == ["alice-pioche-1", "alice-pioche-2"]
    assert "instance_ids" not in pour_bob.donnees
    assert pour_bob.donnees == {"joueur": "alice", "nombre": 2}


def test_evenement_sans_projecteur_est_refuse():
    """Garde structurelle : un type d'événement inconnu du registre n'est jamais diffusé brut."""
    with pytest.raises(ValueError, match="sans projecteur"):
        projeter_evenement(Evenement("type_inexistant_futur", {}), pour="alice")


def test_pioche_dans_projeter_ne_fuit_pas_vers_l_adversaire():
    """Via le point de sortie complet : l'adversaire ne reçoit pas les instance_ids piochés."""
    etat = fabrique_etat(1)
    evt = Evenement(
        EVT_CARTES_PIOCHEES,
        {"joueur": "alice", "nombre": 1, "instance_ids": ["alice-pioche-secrete"]},
    )
    sortie_bob = projeter(etat, (evt,), pour="bob", jetonneur=Jetonneur(SECRET, 0))
    assert "alice-pioche-secrete" not in json.dumps(sortie_bob)
