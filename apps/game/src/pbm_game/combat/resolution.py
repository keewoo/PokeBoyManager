"""Résolution des **dégâts** d'une attaque — l'ordre officiel, pas à pas (R-10).

Module **pur** (aucune E/S). C'est le geste central du jeu, et celui dont le calcul est le
plus souvent faux : l'ordre des opérations entre faiblesse, résistance et modificateurs
change le résultat. On suit donc **à la lettre** l'ordre strict du corpus (R-10.1).

:func:`resoudre_degats` ne **pose** rien : elle **calcule** un :class:`ResultatDegats` (les
dégâts, les compteurs, la trace et le détail lisible). La pose se fait par :func:`poser_degats`
et :func:`poser_compteurs`, qui augmentent les **compteurs de dégâts** d'un Pokémon — **jamais**
en soustrayant des PV (R-10.4), car les soins et les effets « PV restants » en dépendent.

Chaque étape du calcul est un **point d'accroche nommé** (``modificateurs_attaquant``,
``modificateurs_defenseur``) : au jalon J1 ces listes sont vides (aucun effet de carte n'est
encore scripté, D9), mais l'ordre et les crochets sont déjà là pour les lots d'effets à venir.

L'ordre strict (R-10.1) :

1. dégâts de **base** imprimés ;
2. **modificateurs côté attaquant** — puis on **s'arrête si le résultat est ≤ 0** (ou si
   l'attaque ne fait pas de dégâts) : la faiblesse n'est alors **jamais** appliquée (R-16.8) ;
3. **+ faiblesse** (×facteur, R-10.2) ;
4. **− résistance** (−réduction, R-10.3) ;
5. **modificateurs côté défenseur** (réductions) ;
6. **plancher** à 0 (R-10.7) puis **1 compteur par 10 dégâts** (R-10.1 étape 6).

Les dégâts infligés au **banc** (``au_banc=True``) sautent les étapes 3 et 4 — **ni
faiblesse ni résistance** (R-10.5). Un compteur **posé directement** par un effet (« placez
N compteurs ») n'est affecté par rien (R-10.6) : voir :func:`poser_compteurs`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..journal.modele import EVT_DEGATS, Evenement
from ..state.modele import PokemonEnJeu
from .modele import (
    SIGNE_MOINS,
    SIGNE_MULTIPLIE,
    EtapeCalcul,
    Faiblesse,
    Modificateur,
    Resistance,
    ResultatDegats,
)


def _applicable(type_attaque: str | None, type_cible: str) -> bool:
    """La faiblesse/résistance de type ``type_cible`` s'applique-t-elle à l'attaque ?

    Vrai si l'attaque est du type ciblé. ``type_attaque=None`` signifie « applicabilité déjà
    décidée par l'appelant » (il passe la faiblesse/résistance parce qu'elle s'applique) : on
    renvoie alors vrai. C'est le mode utilisé quand l'appariement de type a été fait en amont
    (le catalogue, lot ``j-cartes-pokemon``) ou dans les tests d'ordre des opérations.
    """
    return type_attaque is None or type_attaque == type_cible


def _finaliser(etapes: list[EtapeCalcul], total: int, *, arrete: bool) -> ResultatDegats:
    """Plancher (R-10.7), conversion en compteurs (R-10.1 étape 6), détail (R-10.9)."""
    if total < 0:
        etapes.append(EtapeCalcul("plancher à 0", "R-10.7", total, 0))
        total = 0
    compteurs = total // 10
    degats = compteurs * 10
    if degats != total:
        # Dégâts non multiples de 10 (inhabituel) : « 1 compteur par 10 dégâts » tronque.
        etapes.append(EtapeCalcul(f"{compteurs} compteur(s)", "R-10.1", total, degats))
    detail = ", ".join(e.fragment for e in etapes) + f" = {degats}"
    return ResultatDegats(
        degats=degats,
        compteurs=compteurs,
        etapes=tuple(etapes),
        detail=detail,
        arrete_avant_degats=arrete,
    )


def resoudre_degats(
    *,
    base: int,
    type_attaque: str | None = None,
    modificateurs_attaquant: Sequence[Modificateur] = (),
    faiblesse: Faiblesse | None = None,
    resistance: Resistance | None = None,
    modificateurs_defenseur: Sequence[Modificateur] = (),
    au_banc: bool = False,
) -> ResultatDegats:
    """Calcule les dégâts d'une attaque dans l'ordre strict du corpus (R-10.1).

    ``base`` sont les dégâts imprimés (``0`` pour une attaque sans dégât direct). Les
    faiblesse/résistance ne s'appliquent que si l'attaque est de leur type (voir
    :func:`_applicable`) et **jamais** au banc (``au_banc=True``, R-10.5). Renvoie un
    :class:`ResultatDegats` ; ne pose aucun compteur (c'est le rôle de :func:`poser_degats`).

    Lève ``ValueError`` si ``base`` est négatif — des dégâts de base négatifs n'ont pas de sens.
    """
    if not isinstance(base, int) or isinstance(base, bool) or base < 0:
        raise ValueError(f"Dégâts de base invalides : {base!r} (entier ≥ 0).")

    etapes: list[EtapeCalcul] = [EtapeCalcul(f"{base} base", "R-10.1", base, base)]
    total = base

    # Étape 2 — modificateurs côté attaquant.
    for m in modificateurs_attaquant:
        avant = total
        total = m.appliquer(total)
        etapes.append(EtapeCalcul(m.fragment(), m.regle, avant, total))

    # R-10.1 étape 2 : on s'arrête si le résultat est ≤ 0 — la faiblesse n'est JAMAIS
    # appliquée à une attaque qui ne fait pas de dégâts (R-16.8).
    if total <= 0:
        return _finaliser(etapes, total, arrete=True)

    # Étape 3 — faiblesse (×facteur), sauf au banc (R-10.2, R-10.5).
    if not au_banc and faiblesse is not None and _applicable(type_attaque, faiblesse.type):
        avant = total
        total = total * faiblesse.facteur
        etapes.append(
            EtapeCalcul(f"{SIGNE_MULTIPLIE}{faiblesse.facteur} faiblesse", "R-10.2", avant, total)
        )

    # Étape 4 — résistance (−réduction), sauf au banc (R-10.3, R-10.5).
    if not au_banc and resistance is not None and _applicable(type_attaque, resistance.type):
        avant = total
        total = total - resistance.reduction
        etapes.append(
            EtapeCalcul(f"{SIGNE_MOINS}{resistance.reduction} résistance", "R-10.3", avant, total)
        )

    # Étape 5 — modificateurs côté défenseur (réductions de dégâts).
    for m in modificateurs_defenseur:
        avant = total
        total = m.appliquer(total)
        etapes.append(EtapeCalcul(m.fragment(), m.regle, avant, total))

    # Étape 6 — plancher (R-10.7) + conversion en compteurs (R-10.1 étape 6).
    return _finaliser(etapes, total, arrete=False)


def poser_degats(pokemon: PokemonEnJeu, degats: int) -> PokemonEnJeu:
    """Pose ``degats`` sur ``pokemon`` en **compteurs** — jamais en PV soustraits (R-10.4).

    Augmente ``compteurs_degats`` (cumulatif) et renvoie un **nouveau** ``PokemonEnJeu`` (l'état
    est figé). Lève ``ValueError`` si ``degats`` est négatif : poser des dégâts négatifs serait
    un soin déguisé, qui ne passe pas par ce chemin.
    """
    if not isinstance(degats, int) or isinstance(degats, bool) or degats < 0:
        raise ValueError(f"Dégâts à poser invalides : {degats!r} (entier ≥ 0).")
    return replace(pokemon, compteurs_degats=pokemon.compteurs_degats + degats)


def poser_compteurs(pokemon: PokemonEnJeu, nombre: int) -> PokemonEnJeu:
    """Pose ``nombre`` **compteurs de dégâts** directement (R-10.6) — ``nombre × 10`` dégâts.

    Pour les effets « placez N compteurs de dégâts » : ils ne sont affectés par **aucune**
    faiblesse, résistance ni modificateur (R-10.6). ``1`` compteur = ``10`` dégâts.
    """
    if not isinstance(nombre, int) or isinstance(nombre, bool) or nombre < 0:
        raise ValueError(f"Nombre de compteurs invalide : {nombre!r} (entier ≥ 0).")
    return poser_degats(pokemon, nombre * 10)


def evenement_degats(resultat: ResultatDegats, cible: str, *, au_banc: bool = False) -> Evenement:
    """Construit l'événement de journal :data:`EVT_DEGATS` portant le **détail** (R-10.9).

    ``cible`` est l'``instance_id`` du Pokémon touché. Les valeurs sont **JSON natives**
    (int / str / bool) pour que l'entrée se sérialise et se rejoue sans surprise. C'est cet
    événement que le journal de partie et l'aide en jeu affichent — « 60 base, ×2 faiblesse,
    −30 résistance = 90 ».
    """
    return Evenement(
        EVT_DEGATS,
        {
            "cible": cible,
            "degats": resultat.degats,
            "compteurs": resultat.compteurs,
            "detail": resultat.detail,
            "au_banc": au_banc,
        },
    )


__all__ = [
    "resoudre_degats",
    "poser_degats",
    "poser_compteurs",
    "evenement_degats",
]
