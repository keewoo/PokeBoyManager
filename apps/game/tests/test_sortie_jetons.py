"""Jetons opaques des cartes cachées (``pbm_game.sortie.jetons``) — lot ``j-autorite-vues``.

Deux garanties anti-triche, prouvées ici : l'**opacité** (le jeton ne révèle pas l'``instance_id``,
et change de secret à secret) et la **non-corrélation entre deux mélanges** (un même ``instance_id``
produit un jeton différent à chaque époque, et un jeton d'une époque ne résout plus rien dans une
autre — on ne suit pas une carte d'un mélange à l'autre).
"""

from __future__ import annotations

import pytest

from pbm_game.sortie.jetons import PREFIXE_JETON, Jetonneur, secret_jetons

GRAINE = b"\x11" * 32
SECRET = secret_jetons(GRAINE)


def test_jeton_stable_dans_une_epoque():
    """Même carte, même époque, même secret → même jeton (repère stable pour l'écran)."""
    j = Jetonneur(SECRET, epoque=0)
    assert j.jeton("recompense-3") == j.jeton("recompense-3")
    assert j.jeton("recompense-3").startswith(PREFIXE_JETON)


def test_jeton_ne_revele_pas_l_instance_id():
    """Le jeton ne contient ni l'``instance_id`` ni le ``ref`` en clair — il est opaque."""
    jeton = Jetonneur(SECRET, epoque=0).jeton("recompense-secrete-xyz")
    assert "recompense-secrete-xyz" not in jeton


def test_jeton_change_a_chaque_melange():
    """Non-corrélation : un même ``instance_id`` a un jeton différent d'une époque à l'autre."""
    avant = Jetonneur(SECRET, epoque=0)
    apres = Jetonneur(SECRET, epoque=1)
    ids = [f"recompense-{n}" for n in range(6)]
    assert all(avant.jeton(i) != apres.jeton(i) for i in ids)


def test_jeton_d_une_autre_epoque_ne_resout_plus_rien():
    """Le cœur de la règle : un jeton capturé AVANT un mélange ne désigne plus rien APRÈS.

    L'attaquant note le jeton d'une récompense à l'époque 0 ; le deck est mélangé (époque 1) ; il
    rejoue son jeton pour tenter de suivre la carte : ``resoudre`` renvoie ``None``. Impossible de
    corréler une carte d'un mélange à l'autre.
    """
    ids = [f"recompense-{n}" for n in range(6)]
    jeton_avant = Jetonneur(SECRET, epoque=0).jeton("recompense-3")
    apres = Jetonneur(SECRET, epoque=1)
    assert apres.resoudre(jeton_avant, ids) is None


def test_resoudre_retrouve_parmi_les_candidats_legitimes():
    """Dans la bonne époque, ``resoudre`` retrouve l'``instance_id`` parmi l'ensemble légitime."""
    j = Jetonneur(SECRET, epoque=2)
    ids = ["recompense-0", "recompense-1", "recompense-2"]
    jeton = j.jeton("recompense-1")
    assert j.resoudre(jeton, ids) == "recompense-1"
    # Un jeton forgé au hasard ne résout vers aucun candidat (pas de repli silencieux).
    assert j.resoudre(PREFIXE_JETON + "0" * 20, ids) is None


def test_ordre_des_jetons_ne_suit_pas_l_ordre_des_cartes_entre_epoques():
    """Trier les cartes par leur jeton donne un ordre DIFFÉRENT d'une époque à l'autre.

    Si l'ordre était préservé, un attaquant suivrait une carte par son rang dans la liste triée.
    Sur 50 cartes, la probabilité que deux permutations HMAC indépendantes coïncident est nulle en
    pratique.
    """
    ids = [f"recompense-{n}" for n in range(50)]
    e0 = Jetonneur(SECRET, epoque=0)
    e1 = Jetonneur(SECRET, epoque=1)
    ordre0 = sorted(ids, key=e0.jeton)
    ordre1 = sorted(ids, key=e1.jeton)
    assert ordre0 != ordre1


def test_secret_depend_de_la_graine():
    """Deux graines différentes donnent des secrets — donc des jetons — différents."""
    autre = secret_jetons(b"\x22" * 32)
    assert autre != SECRET
    assert Jetonneur(SECRET, 0).jeton("x") != Jetonneur(autre, 0).jeton("x")


def test_jetonneur_refuse_une_epoque_ou_un_secret_invalides():
    with pytest.raises(ValueError):
        Jetonneur(b"", 0)
    with pytest.raises(ValueError):
        Jetonneur(SECRET, -1)
    with pytest.raises(ValueError):
        Jetonneur(SECRET, 0).jeton("")
