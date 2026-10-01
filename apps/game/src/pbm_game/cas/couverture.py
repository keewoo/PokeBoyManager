"""Couverture des règles par les cas — qui vérifie quoi, et ce qui n'a aucun cas.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il ne lit **aucun** fichier : il reçoit
les règles **définies** (extraites de ``docs/jeu/REGLES.md`` par ``pbm_game.regles``), les règles
**citées** par les cas exécutables (``docs/jeu/cas-executables/``), les règles citées par la table
**documentaire** (``docs/jeu/cas-de-regles.yaml``) et la liste des **exceptions** justifiées — et
en tire un rapport de couverture. La garde de CI (``tests/test_couverture_regles.py``) s'appuie
dessus : **une règle du corpus sans aucun cas fait échouer la CI**, à moins d'une exception écrite
et justifiée.

Pourquoi une exception plutôt qu'un cas pour quelques règles : certaines règles ne sont **pas
exécutables** au jalon J1 — elles parlent de la source du corpus (R-1.*), de construction de deck
non implémentée, ou d'effets de cartes qui n'existent pas encore (D9 : un effet non implémenté
n'est jamais approximé, donc pas « testé » pour de faux). Chaque exception **nomme sa raison**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MOTIF_REGLE = re.compile(r"R-\d+\.\d+")


def regles_d_un_cas(cas: object) -> list[str]:
    """Les ``R-x.y`` cités par un cas exécutable, en validant leur forme (jamais un id fautif)."""
    if not isinstance(cas, dict):
        raise ValueError("Un cas doit être un mapping.")
    cid = cas.get("id")
    if not isinstance(cid, str) or not cid.strip():
        raise ValueError(f"Cas sans « id » valide : {cas!r}.")
    regles = cas.get("regles")
    if not isinstance(regles, list) or not regles:
        raise ValueError(f"Cas « {cid} » : doit citer au moins une règle (« regles »).")
    for r in regles:
        if not isinstance(r, str) or not MOTIF_REGLE.fullmatch(r):
            raise ValueError(f"Cas « {cid} » : « {r!r} » n'est pas un identifiant R-x.y.")
    for champ in ("op", "description"):
        if not isinstance(cas.get(champ), str) or not cas[champ].strip():
            raise ValueError(f"Cas « {cid} » : « {champ} » manquant.")
    return list(regles)


def regles_couvertes(cas_list: list) -> set[str]:
    """L'ensemble des règles citées par au moins un cas exécutable (chaque cas validé)."""
    couvertes: set[str] = set()
    ids_vus: set[str] = set()
    for cas in cas_list:
        regles = regles_d_un_cas(cas)
        cid = cas["id"]
        if cid in ids_vus:
            raise ValueError(f"Identifiant de cas en double : « {cid} ».")
        ids_vus.add(cid)
        couvertes.update(regles)
    return couvertes


@dataclass(frozen=True)
class RapportCouverture:
    """Le bilan de couverture du corpus par les cas (exécutables + documentaires + exceptions)."""

    definies: frozenset[str]
    par_executable: frozenset[str]
    par_documentaire: frozenset[str]
    exceptions: frozenset[str]
    #: Règles définies sans **aucun** cas ni exception — ce que la garde CI interdit.
    sans_cas: frozenset[str] = field(default_factory=frozenset)
    #: Exceptions **périmées** : une règle déclarée en exception alors qu'un cas la couvre déjà.
    exceptions_perimees: frozenset[str] = field(default_factory=frozenset)
    #: Exceptions **hors corpus** : un identifiant d'exception absent de REGLES.md.
    exceptions_inconnues: frozenset[str] = field(default_factory=frozenset)


def rapport(
    definies: set[str],
    par_executable: set[str],
    par_documentaire: set[str],
    exceptions: set[str],
) -> RapportCouverture:
    """Calcule le bilan de couverture (fonction pure). Ne lève pas : la garde lit le rapport.

    * ``sans_cas`` = règles définies couvertes par **ni** un cas exécutable, **ni** la table
      documentaire, **ni** une exception → la garde CI échoue si cet ensemble n'est pas vide ;
    * ``exceptions_perimees`` = exceptions qu'un cas couvre déjà (à retirer, pour que la liste
      d'exceptions reste honnête : une exception ne se garde que tant qu'aucun cas n'existe) ;
    * ``exceptions_inconnues`` = exceptions qui ne nomment aucune règle définie.
    """
    cas_reels = par_executable | par_documentaire
    sans_cas = definies - cas_reels - exceptions
    exceptions_perimees = exceptions & cas_reels
    exceptions_inconnues = exceptions - definies
    return RapportCouverture(
        definies=frozenset(definies),
        par_executable=frozenset(par_executable),
        par_documentaire=frozenset(par_documentaire),
        exceptions=frozenset(exceptions),
        sans_cas=frozenset(sans_cas),
        exceptions_perimees=frozenset(exceptions_perimees),
        exceptions_inconnues=frozenset(exceptions_inconnues),
    )


__all__ = [
    "MOTIF_REGLE",
    "regles_d_un_cas",
    "regles_couvertes",
    "RapportCouverture",
    "rapport",
]
