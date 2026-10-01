"""Structures de la **résolution d'attaque** — coût, dégâts, détail de calcul.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base de
données ou à React, comme tout le moteur ``pbm_game`` (principe du jalon J1).

Il porte la **forme** des données que manipule la résolution d'une attaque — jamais les
données de carte elles-mêmes (type d'une énergie, coût imprimé, faiblesse d'un Pokémon) :
celles-ci viennent du **catalogue**, câblé par les lots suivants (``j-cartes-pokemon``, que
ce lot débloque). Le moteur reçoit donc des **descripteurs** déjà extraits du catalogue et
les résout ; il ne les devine pas (D9 — un effet non implémenté n'est jamais approximé).

Règles de référence structurées ici (``docs/jeu/REGLES.md``) :

* **R-9.2** — coût d'une attaque : symboles **colorés** (par type) + symboles **incolores**
  (payés par n'importe quelle énergie) ; une énergie peut **fournir plusieurs unités** ;
* **R-10.1** — l'ordre strict de calcul des dégâts, étape par étape ;
* **R-10.2 / R-10.3** — faiblesse **×2**, résistance **−30** par défaut (DJ1) ;
* **R-10.9** — le **détail de calcul** lisible (« 60 base, ×2 faiblesse, −30 résistance = 90 »).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# --- Signes du détail de calcul (R-10.9) -------------------------------------
# Choisis pour reproduire EXACTEMENT l'exemple du corpus : « ×2 faiblesse » utilise le
# signe multiplication U+00D7, « −30 résistance » le signe moins typographique U+2212.
SIGNE_MULTIPLIE = "×"  # ×
SIGNE_MOINS = "−"  # −
SIGNE_PLUS = "+"

# --- Énergie incolore (R-9.2) ------------------------------------------------
#: Type d'unité d'énergie « incolore » (p. ex. Double Énergie Incolore en fournit 2). Une
#: unité incolore ne paie **qu'un** symbole incolore (★), **jamais** un symbole coloré ; un
#: symbole incolore, lui, se paie par **n'importe quelle** unité (colorée ou incolore).
INCOLORE = "incolore"

# --- Valeurs par défaut de faiblesse / résistance (DJ1) ----------------------
#: Faiblesse par défaut : **×2** (R-10.2, décision DJ1).
FAIBLESSE_FACTEUR_DEFAUT = 2
#: Résistance par défaut : **−30** (R-10.3, décision DJ1).
RESISTANCE_REDUCTION_DEFAUT = 30

# --- Opérations d'un modificateur de dégâts ----------------------------------
# Un modificateur agit par une opération d'un **ensemble fermé** : additive (la forme la
# plus courante — « +20 »/« −20 »), multiplicative (« ×2 »), ou fixe (« les dégâts
# deviennent N »). Un effet de carte dont le calcul ne se réduit à aucune de ces trois
# formes n'est pas approximé ici : il est scripté et testé dans son propre lot (D9).
OP_AJOUT = "ajout"
OP_MULTIPLIE = "multiplie"
OP_FIXE = "fixe"
OPERATIONS: frozenset[str] = frozenset({OP_AJOUT, OP_MULTIPLIE, OP_FIXE})


@dataclass(frozen=True)
class CoutAttaque:
    """Le coût d'une attaque (R-9.2).

    * ``types`` — les symboles **colorés** requis, par type : ``{"feu": 1, "eau": 1}`` ;
    * ``incolore`` — le nombre de symboles **incolores** (★), payables par n'importe quelle
      énergie, colorée ou incolore.

    Un coût vide (``types={}``, ``incolore=0``) est une attaque **gratuite** : toujours
    satisfaite. Lève ``ValueError`` à la construction si un compte coloré est ``< 1`` ou si
    ``incolore`` est ``< 0`` — un coût malformé est une panne, jamais un repli silencieux.
    """

    types: Mapping[str, int] = field(default_factory=dict)
    incolore: int = 0

    def __post_init__(self) -> None:
        for t, n in self.types.items():
            if not isinstance(t, str) or not t:
                raise ValueError(f"Type d'énergie du coût invalide : {t!r}.")
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise ValueError(
                    f"Coût coloré « {t} » invalide : {n!r} (entier ≥ 1 ; un symbole absent "
                    "ne figure tout simplement pas dans « types »)."
                )
        inc = self.incolore
        if not isinstance(inc, int) or isinstance(inc, bool) or inc < 0:
            raise ValueError(f"Coût incolore invalide : {inc!r} (entier ≥ 0).")

    @property
    def total_symboles(self) -> int:
        """Nombre total de symboles du coût (colorés + incolores)."""
        return sum(self.types.values()) + self.incolore


@dataclass(frozen=True)
class Faiblesse:
    """La faiblesse d'un Pokémon (R-10.2) : un **type** et un **facteur** (×2 par défaut)."""

    type: str
    facteur: int = FAIBLESSE_FACTEUR_DEFAUT

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type:
            raise ValueError(f"Type de faiblesse invalide : {self.type!r}.")
        if not isinstance(self.facteur, int) or isinstance(self.facteur, bool) or self.facteur < 1:
            raise ValueError(f"Facteur de faiblesse invalide : {self.facteur!r} (entier ≥ 1).")


@dataclass(frozen=True)
class Resistance:
    """La résistance d'un Pokémon (R-10.3) : un **type** et une **réduction** (−30 par défaut)."""

    type: str
    reduction: int = RESISTANCE_REDUCTION_DEFAUT

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type:
            raise ValueError(f"Type de résistance invalide : {self.type!r}.")
        if (
            not isinstance(self.reduction, int)
            or isinstance(self.reduction, bool)
            or self.reduction < 0
        ):
            raise ValueError(f"Réduction de résistance invalide : {self.reduction!r} (entier ≥ 0).")


@dataclass(frozen=True)
class Modificateur:
    """Un modificateur de dégâts — **point d'accroche nommé** d'une étape (R-10.1, 2 & 5).

    * ``libelle`` — le nom lisible qui apparaît dans le détail de calcul (« Grande Griffe ») ;
    * ``regle`` — l'identifiant ``R-x.y`` qui le motive (jamais vide : un effet cite sa règle) ;
    * ``operation`` — un des :data:`OPERATIONS` (``ajout`` / ``multiplie`` / ``fixe``) ;
    * ``valeur`` — l'opérande entier.

    Au jalon J1, **aucun** modificateur n'est câblé : les listes d'étapes 2 et 5 sont vides
    par défaut. Ce type est le cadre que les lots d'effets (attaques, Dresseurs, Outils)
    rempliront, chacun scripté et testé. Lève ``ValueError`` si ``operation`` est hors de
    l'ensemble fermé ou si ``regle`` est vide.
    """

    libelle: str
    regle: str
    operation: str
    valeur: int

    def __post_init__(self) -> None:
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Un modificateur doit porter un libellé lisible.")
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un modificateur doit citer la règle R-x.y qui le motive (D9).")
        if self.operation not in OPERATIONS:
            raise ValueError(
                f"Opération de modificateur inconnue : {self.operation!r} — "
                f"un effet non prévu n'est jamais approximé (D9). Connues : {sorted(OPERATIONS)}."
            )
        if not isinstance(self.valeur, int) or isinstance(self.valeur, bool):
            raise ValueError(f"Valeur de modificateur invalide : {self.valeur!r} (entier).")

    def appliquer(self, total: int) -> int:
        """Applique l'opération à ``total`` et renvoie le nouveau total (fonction pure)."""
        if self.operation == OP_AJOUT:
            return total + self.valeur
        if self.operation == OP_MULTIPLIE:
            return total * self.valeur
        return self.valeur  # OP_FIXE

    def fragment(self) -> str:
        """Le fragment lisible de ce modificateur pour le détail de calcul (R-10.9)."""
        if self.operation == OP_AJOUT:
            signe = SIGNE_PLUS if self.valeur >= 0 else SIGNE_MOINS
            return f"{signe}{abs(self.valeur)} {self.libelle}"
        if self.operation == OP_MULTIPLIE:
            return f"{SIGNE_MULTIPLIE}{self.valeur} {self.libelle}"
        return f"={self.valeur} {self.libelle}"


def modificateur_ajout(libelle: str, regle: str, valeur: int) -> Modificateur:
    """Raccourci : un modificateur **additif** (``+N`` / ``−N``)."""
    return Modificateur(libelle=libelle, regle=regle, operation=OP_AJOUT, valeur=valeur)


def modificateur_multiplie(libelle: str, regle: str, valeur: int) -> Modificateur:
    """Raccourci : un modificateur **multiplicatif** (``×N``)."""
    return Modificateur(libelle=libelle, regle=regle, operation=OP_MULTIPLIE, valeur=valeur)


def modificateur_fixe(libelle: str, regle: str, valeur: int) -> Modificateur:
    """Raccourci : un modificateur **fixe** (les dégâts deviennent ``N``)."""
    return Modificateur(libelle=libelle, regle=regle, operation=OP_FIXE, valeur=valeur)


@dataclass(frozen=True)
class EtapeCalcul:
    """Une **étape** du calcul des dégâts — ce qui rend le détail vérifiable (R-10.1, R-10.9).

    * ``fragment`` — le morceau lisible affiché dans le détail (« ×2 faiblesse ») ;
    * ``regle`` — la règle ``R-x.y`` de cette étape ;
    * ``avant`` / ``apres`` — la valeur des dégâts avant et après l'étape.
    """

    fragment: str
    regle: str
    avant: int
    apres: int


@dataclass(frozen=True)
class ResultatDegats:
    """Le résultat d'une résolution de dégâts (R-10) — sérialisable, sans PV (R-10.4).

    * ``degats`` — les dégâts **appliqués** (en PV-équivalent), toujours un multiple de 10 et
      ``≥ 0`` (plancher R-10.7, conversion en compteurs R-10.1 étape 6) ;
    * ``compteurs`` — le nombre de **compteurs de dégâts** posés (``degats // 10``) ;
    * ``etapes`` — la trace ordonnée du calcul ;
    * ``detail`` — le détail lisible (R-10.9),
      p. ex. « 60 base, ×2 faiblesse, −30 résistance = 90 » ;
    * ``arrete_avant_degats`` — vrai quand le calcul s'est arrêté à l'étape 2 (résultat 0),
      la faiblesse et la résistance n'ayant alors **jamais** été appliquées (R-10.1, R-16.8).
    """

    degats: int
    compteurs: int
    etapes: tuple[EtapeCalcul, ...]
    detail: str
    arrete_avant_degats: bool = False


__all__ = [
    "SIGNE_MULTIPLIE",
    "SIGNE_MOINS",
    "SIGNE_PLUS",
    "INCOLORE",
    "FAIBLESSE_FACTEUR_DEFAUT",
    "RESISTANCE_REDUCTION_DEFAUT",
    "OP_AJOUT",
    "OP_MULTIPLIE",
    "OP_FIXE",
    "OPERATIONS",
    "CoutAttaque",
    "Faiblesse",
    "Resistance",
    "Modificateur",
    "modificateur_ajout",
    "modificateur_multiplie",
    "modificateur_fixe",
    "EtapeCalcul",
    "ResultatDegats",
]
