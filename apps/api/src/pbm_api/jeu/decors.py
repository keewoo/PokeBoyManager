"""Vocabulaire des **décors d'arène** (lot ``j-arene-decors``) — module **pur**.

Le serveur n'a pas à savoir *à quoi ressemble* un décor : les teintes et les dégradés vivent côté
écran (``apps/web/src/lib/game/decors.ts`` et ``globals.css``), parce que c'est là qu'ils se
peignent. Ce qu'il doit savoir, et lui seul, c'est **quelles clés existent** — sans quoi il
accepterait d'enregistrer ``"volcan_bleu"`` dans les réglages d'un compte, et le joueur se
retrouverait avec un fond nu en croyant avoir choisi un décor.

C'est la même règle que pour les animations et la taille du texte
(:mod:`pbm_api.jeu.confort`) : une valeur hors vocabulaire est **refusée**, jamais repliée en
silence (D9). La parité des deux listes est vérifiée par ``tests/test_jeu_decors.py``, qui lit le
fichier TypeScript — un décor ajouté d'un seul côté est une divergence qu'on voit tout de suite.
"""

from __future__ import annotations

#: Les six décors, dans l'ordre d'affichage de l'écran de choix.
#:
#: L'ordre compte : il va du plus neutre (le gymnase du quartier, qui reprend le fond d'origine du
#: plateau) au plus marqué, pour qu'un joueur qui descend la liste voie l'écart grandir.
DECORS: tuple[str, ...] = ("arene", "caldeira", "lagon", "orage", "temple", "faille")

#: Décor servi quand rien n'est choisi et que rien ne se déduit du deck.
DECOR_DEFAUT = "arene"

#: L'ensemble des clés reconnues. Une clé hors de cet ensemble est refusée à l'écriture.
DECORS_CONNUS: frozenset[str] = frozenset(DECORS)


def decor_valide(cle: str | None) -> bool:
    """Vrai si ``cle`` est un décor connu, ou ``None`` (« laisse le jeu choisir d'après mon deck »).

    ``None`` est une valeur **légitime**, pas une absence de réponse : c'est le réglage par défaut,
    celui qui laisse le thème automatique suivre le deck joué.
    """
    return cle is None or cle in DECORS_CONNUS


__all__ = ["DECORS", "DECORS_CONNUS", "DECOR_DEFAUT", "decor_valide"]
