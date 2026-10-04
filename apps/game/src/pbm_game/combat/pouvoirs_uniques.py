"""Pouvoirs « une seule fois par partie » — attaque GX et VSTAR Power (R-15.3/R-15.6).

Module **pur** (aucune E/S), comme tout ``pbm_game``. Certaines cartes portent un pouvoir qu'un
joueur ne peut utiliser **qu'une fois par partie**, tous Pokémon confondus :

* **attaque GX** — une seule par partie et par joueur (R-15.3) ;
* **VSTAR Power** (attaque OU talent) — un seul par partie et par joueur (R-15.6).

**L'usage se suit dans l'état du JOUEUR, jamais dans celui de la carte** (consigne du lot
``j-cartes-regles-speciales``) : :attr:`pbm_game.state.modele.Joueur.pouvoirs_uniques_utilises`
porte les pouvoirs déjà dépensés. C'est de l'état **sérialisé** — donc l'interdiction d'un second
usage **survit à une reprise après F5** et au rejeu du journal, exactement comme les drapeaux
« une fois par tour » du :class:`~pbm_game.state.modele.Tour`.

**D9 — on ne devine pas.** Un identifiant de pouvoir inconnu fait échouer bruyamment
(:func:`valider_pouvoir`), jamais un repli silencieux.
"""

from __future__ import annotations

from dataclasses import replace

from ..state.modele import Joueur

#: Attaque GX — une seule par partie et par joueur (R-15.3).
POUVOIR_GX = "gx"
#: VSTAR Power (attaque ou talent) — un seul par partie et par joueur (R-15.6).
POUVOIR_VSTAR = "vstar"

#: Les pouvoirs à usage unique reconnus. Un identifiant hors de cet ensemble est refusé (D9).
POUVOIRS_UNIQUES: frozenset[str] = frozenset({POUVOIR_GX, POUVOIR_VSTAR})

#: La règle citée par pouvoir — pour qu'un refus nomme toujours sa règle (R-x.y).
REGLE_PAR_POUVOIR: dict[str, str] = {POUVOIR_GX: "R-15.3", POUVOIR_VSTAR: "R-15.6"}


def valider_pouvoir(pouvoir: object) -> str:
    """Valide un identifiant de pouvoir à usage unique et le renvoie ; lève si inconnu (D9).

    Le moteur ne devine pas : un pouvoir hors de :data:`POUVOIRS_UNIQUES` est une donnée fausse
    (fournie par le service depuis le catalogue), refusée bruyamment, jamais ignorée.
    """
    if not isinstance(pouvoir, str) or pouvoir not in POUVOIRS_UNIQUES:
        raise ValueError(
            f"Pouvoir à usage unique inconnu : {pouvoir!r} — connus : {sorted(POUVOIRS_UNIQUES)} "
            "(R-15.3/R-15.6). Un effet non implémenté n'est jamais approximé (D9)."
        )
    return pouvoir


def deja_utilise(joueur: Joueur, pouvoir: str) -> bool:
    """Vrai si ``joueur`` a déjà dépensé ``pouvoir`` cette partie (R-15.3/R-15.6)."""
    return valider_pouvoir(pouvoir) in joueur.pouvoirs_uniques_utilises


def marquer_utilise(joueur: Joueur, pouvoir: str) -> Joueur:
    """Renvoie ``joueur`` avec ``pouvoir`` marqué comme **dépensé** pour la partie (R-15.3/R-15.6).

    Idempotent : marquer un pouvoir déjà dépensé rend un joueur égal (un ``frozenset``). C'est
    :func:`deja_utilise`, à l'appel, qui interdit un second usage — pas cette fonction.
    """
    valider_pouvoir(pouvoir)
    return replace(
        joueur, pouvoirs_uniques_utilises=joueur.pouvoirs_uniques_utilises | {pouvoir}
    )


__all__ = [
    "POUVOIR_GX",
    "POUVOIR_VSTAR",
    "POUVOIRS_UNIQUES",
    "REGLE_PAR_POUVOIR",
    "valider_pouvoir",
    "deja_utilise",
    "marquer_utilise",
]
