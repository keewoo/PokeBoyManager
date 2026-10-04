"""Le **classement par famille d'effet** — pour le rapport à JF et son droit de veto (DJ8).

Module **pur** (aucune E/S). DJ8 tranche : il n'y a **pas** de relecture humaine carte par carte ;
à la place, l'IA valide (une seconde IA la contredit), et *« un rapport par famille d'effets est
fait à JF, qui peut retirer une famille d'un mot »*. Ce module décide à quelle **famille** un effet
appartient — c'est le grain du rapport, et le grain auquel JF accepte ou retire.

La famille se lit en priorité dans le **script** (les primitives réellement employées, donc ce que
l'effet *fait*), et à défaut (effet non supporté, sans script) dans le **texte** par mots-clés. On
ne devine jamais : un effet qu'on ne sait pas classer tombe dans ``"autre"``, nommé comme tel.
"""

from __future__ import annotations

from collections.abc import Mapping

#: Famille affectée quand ni le script ni le texte ne tranchent — nommée, jamais silencieuse.
FAMILLE_AUTRE = "autre"

# L'``op`` principal d'un script → sa famille. Deux primitives peuvent viser la même famille
# (``poser_compteurs``/``infliger_degats`` = dégâts d'effet). Ordre de priorité : la première
# primitive trouvée dans cette table, parcourue dans l'ordre des effets du script.
_FAMILLE_PAR_OP: dict[str, str] = {
    "piocher": "pioche",
    "chercher": "recherche",
    "regarder": "recherche",
    "reveler": "recherche",
    "soigner": "soin",
    "poser_compteurs": "degats",
    "infliger_degats": "degats",
    "poser_etat": "etat_special",
    "retirer_etat": "etat_special",
    "attacher": "energie",
    "deplacer": "deplacement",
    "defausser": "defausse",
    "melanger": "melange",
    "changer_actif": "position",
    "empecher": "verrou",
    "annuler": "prevention",
    "pile_ou_face": "aleatoire",
    "choisir": "choix",
}

# Mots-clés d'un texte → famille, quand aucun script n'existe (effet non supporté). Repli le plus
# grossier : il ne sert qu'à grouper le rapport des effets refusés, jamais à jouer quoi que ce soit.
_FAMILLE_PAR_MOT: tuple[tuple[str, str], ...] = (
    ("pioch", "pioche"),
    ("cherch", "recherche"),
    ("soign", "soin"),
    ("dégât", "degats"),
    ("degat", "degats"),
    ("compteur", "degats"),
    ("empoisonn", "etat_special"),
    ("endorm", "etat_special"),
    ("paralys", "etat_special"),
    ("confus", "etat_special"),
    ("brûl", "etat_special"),
    ("brul", "etat_special"),
    ("énergie", "energie"),
    ("energie", "energie"),
    ("défauss", "defausse"),
    ("defauss", "defausse"),
    ("mélang", "melange"),
    ("melang", "melange"),
    ("pièce", "aleatoire"),
    ("piece", "aleatoire"),
)


def _ops_du_script(script: Mapping) -> list[str]:
    """Les ``op`` rencontrés dans un script, dans l'ordre de parcours (effets puis sous-blocs)."""
    ops: list[str] = []

    def _descendre(instructions: object) -> None:
        if not isinstance(instructions, (list, tuple)):
            return
        for instr in instructions:
            if not isinstance(instr, Mapping):
                continue
            op = instr.get("op")
            if isinstance(op, str):
                ops.append(op)
            for cle in ("alors", "sinon"):
                _descendre(instr.get(cle))

    _descendre(script.get("cout"))
    _descendre(script.get("effets"))
    return ops


def famille_du_script(script: object) -> str:
    """La famille d'un script, lue depuis sa **première** primitive classante (ce qu'il fait).

    Les structures de contrôle (``si``/``repeter``) ne classent pas : on descend dedans jusqu'à
    une primitive connue. Un script sans primitive classante tombe dans :data:`FAMILLE_AUTRE`.
    """
    if not isinstance(script, Mapping):
        return FAMILLE_AUTRE
    for op in _ops_du_script(script):
        famille = _FAMILLE_PAR_OP.get(op)
        if famille is not None:
            return famille
    return FAMILLE_AUTRE


def famille_du_texte(texte: str) -> str:
    """La famille d'un texte d'effet par mots-clés — repli quand aucun script n'existe (refus)."""
    bas = texte.casefold()
    for motif, famille in _FAMILLE_PAR_MOT:
        if motif in bas:
            return famille
    return FAMILLE_AUTRE


def famille(texte: str, script: object | None) -> str:
    """La famille d'un effet : du script s'il existe (ce qu'il fait), sinon du texte (mots-clés).

    Un script vaut mieux qu'un texte pour classer : il dit ce que l'effet *fait*, pas ce qu'il
    *raconte*. On ne retombe sur le texte que faute de script (un effet non supporté, D9).
    """
    if script is not None:
        f = famille_du_script(script)
        if f != FAMILLE_AUTRE:
            return f
    return famille_du_texte(texte)


__all__ = ["FAMILLE_AUTRE", "famille", "famille_du_script", "famille_du_texte"]
