"""Replay — la suite des états d'une partie, pas seulement le dernier. Lot ``j-replay``.

Ces tests FONT FOI sur le premier critère d'acceptation du lot : **« le replay reproduit
exactement les états successifs (empreintes comparées) »**. Le moyen est direct : on simule
une partie, on garde la suite des empreintes observées *en avant de jeu*, puis on la
reconstruit avec :func:`~pbm_game.journal.etapes_partie` depuis les trois seules choses
qu'on persiste (état initial, graine, journal) et on compare rang par rang.

Deux pièges que ces tests gardent fermés :

* un replay qui s'alignerait sur le journal au lieu de le **contrôler** — on vérifie donc
  qu'une entrée truquée fait lever au coup près, comme pour :func:`rejouer` ;
* un replay reparti d'un instantané qui donnerait autre chose que le replay complet — la
  pagination du serveur repose précisément là-dessus.

Le moteur est **pur** : aucune base, aucun réseau, aucun fichier. ``random`` ne sert qu'à
*choisir* les coups du simulateur ; l'aléatoire **du jeu** passe par le ``Rng`` seul.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

# Le simulateur de parties du lot ``j-journal-actions`` : un seul simulateur pour les deux
# lots, pour que le replay soit mesuré sur les mêmes parties que le rejeu (aucune dérive).
from test_journal import _simuler

from pbm_game.journal import (
    ACTION_ABANDONNER,
    Action,
    Evenement,
    RejeuDivergent,
    compacter,
    empreinte,
    etapes,
    etapes_partie,
    jouer,
    rejouer,
)
from pbm_game.state import vers_json

# --- Critère : le replay reproduit exactement les états successifs -----------


def test_replay_redonne_rang_par_rang_les_empreintes_de_la_partie_jouee():
    """Sur 200 parties simulées, chaque rang du replay porte l'empreinte vue en avant de jeu.

    C'est le critère d'acceptation central du lot, et il porte sur **tous** les rangs, pas
    seulement le dernier : un replay qui n'arriverait au bon état final qu'en passant par
    des états faux serait inutile (on le regarde coup par coup, justement).
    """
    for seed in range(200):
        nb = (seed % 12) + 1
        partie, etat_final, empreintes = _simuler(seed, nb)
        rangs = list(etapes_partie(partie))

        # Une partie de n coups a n+1 rangs : le rang 0 (avant tout coup) puis un par coup.
        assert len(rangs) == nb + 1, f"nombre de rangs (seed={seed})"
        assert [e.rang for e in rangs] == list(range(nb + 1)), f"rangs (seed={seed})"

        # Rang 0 : l'état initial, aucun coup pour y mener, aucun événement.
        assert rangs[0].entree is None
        assert rangs[0].evenements == ()
        assert vers_json(rangs[0].etat) == vers_json(partie.etat_initial), f"rang 0 (seed={seed})"
        assert rangs[0].empreinte == empreinte(partie.etat_initial)

        # Rangs 1..n : les empreintes du replay == celles observées en avant de jeu.
        assert [e.empreinte for e in rangs[1:]] == empreintes, f"empreintes (seed={seed})"
        # …et chaque empreinte est bien celle de l'état rendu (pas une valeur recopiée).
        for etape in rangs:
            assert etape.empreinte == empreinte(etape.etat), f"rang {etape.rang} (seed={seed})"

        # Le dernier rang est l'état final, octet pour octet.
        assert vers_json(rangs[-1].etat) == vers_json(etat_final), f"état final (seed={seed})"


def test_chaque_rang_porte_son_coup_et_ses_evenements_recalcules():
    """Le coup qui mène à un rang, et ses événements — recalculés, pas recopiés du journal."""
    partie, _etat, _ = _simuler(7, 10)
    rangs = list(etapes_partie(partie))
    for etape, entree in zip(rangs[1:], partie.entrees, strict=True):
        assert etape.entree is entree, "le rang doit porter l'entrée de journal qui y mène"
        assert etape.rang == entree.numero + 1, "rang = nombre d'entrées appliquées"
        # Les événements rendus sont ceux que le moteur vient de produire ; ils ont été
        # comparés à ceux du journal par le rejeu contrôlé, donc ils leur sont égaux.
        assert etape.evenements == entree.evenements


def test_replay_identique_au_rejeu_complet_sur_l_etat_final():
    """Le dernier rang du replay == ce que rend :func:`rejouer`. Deux chemins, un seul état."""
    partie, _etat, _ = _simuler(123, 12)
    attendu, _rng = rejouer(partie)
    dernier = list(etapes_partie(partie))[-1]
    assert vers_json(dernier.etat) == vers_json(attendu)


# --- Critère : une partie interrompue par abandon se rejoue aussi ------------


def test_replay_d_une_partie_interrompue_par_abandon():
    """Une partie close par **abandon** (R-14.3) se rejoue jusqu'à son dernier rang.

    Le cas du lot : on ne rejoue pas que des parties menées à leur terme « normal ». Le
    dernier rang doit porter l'état terminé, avec le vainqueur et le motif — et son
    empreinte doit concorder comme les autres.
    """
    partie, etat, _ = _simuler(31, 5)
    abandonneur = etat.joueurs[0].id
    survivant = etat.joueurs[1].id

    # On rejoue le journal pour retrouver le Rng au bon point, puis on abandonne.
    etat_av, rng = rejouer(partie)
    partie, etat_fin = jouer(
        partie,
        Action(ACTION_ABANDONNER, abandonneur),
        "2026-10-01T12:30:00Z",
        etat_av,
        rng,
    )
    assert etat_fin.terminee, "l'abandon doit clore la partie (R-14.3)"
    assert etat_fin.vainqueur == survivant, "l'adversaire de l'abandonneur gagne (R-14.3)"

    rangs = list(etapes_partie(partie))
    assert len(rangs) == 7, "rang 0 + 5 coups + l'abandon = 7 rangs"
    dernier = rangs[-1]
    assert dernier.entree is not None and dernier.entree.action.type == ACTION_ABANDONNER
    assert dernier.etat.terminee and dernier.etat.vainqueur == survivant
    assert dernier.empreinte == empreinte(dernier.etat)
    assert [e.empreinte for e in rangs[1:]] == [e.empreinte for e in partie.entrees]
    # Les rangs d'AVANT l'abandon montrent une partie encore en cours : un replay ne
    # réécrit pas l'histoire en fonction de sa fin.
    assert not any(e.etat.terminee for e in rangs[:-1])


# --- Le replay contrôle le journal, il ne s'y aligne pas ---------------------


def test_replay_mord_sur_une_empreinte_truquee_au_coup_pres():
    """Une empreinte d'entrée falsifiée lève :class:`RejeuDivergent` **au coup fautif**."""
    partie, _etat, _ = _simuler(42, 8)
    cible = 4
    entrees = list(partie.entrees)
    entrees[cible] = replace(entrees[cible], empreinte="0" * 64)
    truquee = replace(partie, entrees=tuple(entrees))

    rangs = etapes_partie(truquee)
    # Paresseux : les rangs d'avant le coup fautif sortent normalement, puis ça lève.
    for _ in range(cible + 1):
        next(rangs)
    with pytest.raises(RejeuDivergent) as exc:
        next(rangs)
    assert exc.value.numero == cible
    assert "empreinte" in exc.value.quoi


def test_replay_mord_sur_un_evenement_truque():
    """Un événement d'entrée falsifié est attrapé lui aussi (le journal ne peut pas mentir)."""
    partie, _etat, _ = _simuler(99, 6)
    cible = 2
    entrees = list(partie.entrees)
    entrees[cible] = replace(entrees[cible], evenements=(Evenement("mensonge", {}),))
    truquee = replace(partie, entrees=tuple(entrees))
    with pytest.raises(RejeuDivergent) as exc:
        list(etapes_partie(truquee))
    assert exc.value.numero == cible
    assert exc.value.quoi == "événements"


def test_replay_refuse_un_instantane_incoherent():
    """Un instantané dont l'empreinte ne colle pas à son état est refusé, pas cru sur parole."""
    partie, _etat, _ = _simuler(5, 4)
    instantane = replace(compacter(partie, 2), empreinte="f" * 64)
    with pytest.raises(RejeuDivergent) as exc:
        next(etapes(instantane, partie.entrees[2:]))
    assert exc.value.quoi == "empreinte d'instantané"


# --- Pagination : repartir d'un instantané donne les mêmes rangs -------------


@pytest.mark.parametrize("coupe", [0, 1, 4, 8])
def test_repartir_d_un_instantane_donne_les_memes_rangs(coupe: int):
    """Les rangs servis depuis un instantané == la queue des rangs du replay complet.

    C'est ce sur quoi repose la **pagination** côté serveur : une page de replay repart du
    dernier instantané qui précède son premier rang. Si les deux chemins divergeaient, la
    deuxième page d'un replay ne montrerait pas la même partie que la première.
    """
    partie, _etat, _ = _simuler(17, 8)
    complet = list(etapes_partie(partie))
    depuis_instantane = list(etapes(compacter(partie, coupe), partie.entrees[coupe:]))

    assert [e.rang for e in depuis_instantane] == [e.rang for e in complet[coupe:]]
    for a, b in zip(depuis_instantane, complet[coupe:], strict=True):
        assert vers_json(a.etat) == vers_json(b.etat), f"état au rang {a.rang}"
        assert a.empreinte == b.empreinte
    # Le premier rang d'une page est un état déjà atteint : aucun coup ne « mène » à lui
    # dans cette page, et il ne porte donc aucun événement (il ne se rejoue pas deux fois).
    assert depuis_instantane[0].entree is None
    assert depuis_instantane[0].evenements == ()
