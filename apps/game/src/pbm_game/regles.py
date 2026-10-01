"""Chargement et vérification de cohérence du corpus de règles du jeu.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base
de données ou à React — comme tout le moteur `pbm_game` (principe du jalon J1). Il
ne lit **pas** les fichiers du corpus lui-même ; il travaille sur leur contenu déjà
chargé (une chaîne markdown, une structure déjà désérialisée), pour rester testable
par milliers de cas et sans E/S.

Le corpus de référence vit hors du paquet, dans le dépôt :

* ``docs/jeu/REGLES.md`` — les règles numérotées ``R-x.y`` qui font foi ;
* ``docs/jeu/cas-de-regles.yaml`` — la table de cas qui, pour chacun, nomme la
  règle qu'il vérifie.

Lot d'origine : ``j-regles-reference``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "MOTIF_REGLE",
    "CAS_LIMITES_REQUIS",
    "Cas",
    "identifiants_definis",
    "identifiants_cites",
    "charger_cas",
    "regles_orphelines",
    "cas_limites_manquants",
]

# Un identifiant de règle a la forme ``R-<section>.<numéro>`` (ex. ``R-10.3``).
MOTIF_REGLE = re.compile(r"R-\d+\.\d+")

# Une règle est *définie* quand elle apparaît en gras en tête de point : ``**R-10.3**``.
# Les simples citations (dans une autre règle, dans la table de cas) ne sont pas en gras.
_MOTIF_DEFINITION = re.compile(r"\*\*(R-\d+\.\d+)\*\*")

# Les dix cas limites que la mission j-regles-reference exige de couvrir, par slug
# canonique (champ ``cas_limite`` dans la table). La table en couvre davantage ; ceux-ci
# sont le minimum garanti par un test.
CAS_LIMITES_REQUIS: frozenset[str] = frozenset(
    {
        "pioche-vide-debut-tour",
        "banc-vide-apres-ko",
        "ko-simultane",
        "dernier-pokemon-ko-hors-attaque",
        "abandon",
        "egalite",
        "resistance-superieure-aux-degats",
        "faiblesse-sur-degats-nuls",
        "mulligan-multiple",
        "echange-force-sous-etat",
    }
)


@dataclass(frozen=True)
class Cas:
    """Un cas de test de règle : il nomme la ou les règles qu'il vérifie."""

    id: str
    regles: tuple[str, ...]
    categorie: str
    description: str
    cas_limite: str | None = None
    regles_brutes: tuple[str, ...] = field(default=(), repr=False)


def identifiants_definis(markdown: str) -> set[str]:
    """Les identifiants ``R-x.y`` **définis** dans le corpus (en gras, en tête de point)."""
    return set(_MOTIF_DEFINITION.findall(markdown))


def identifiants_cites(markdown: str) -> set[str]:
    """Tous les identifiants ``R-x.y`` qui apparaissent dans un texte (définis ou cités)."""
    return set(MOTIF_REGLE.findall(markdown))


def definitions_en_double(markdown: str) -> list[str]:
    """Identifiants définis plus d'une fois — un corpus sain n'en a aucun."""
    vus: dict[str, int] = {}
    for ident in _MOTIF_DEFINITION.findall(markdown):
        vus[ident] = vus.get(ident, 0) + 1
    return sorted(ident for ident, n in vus.items() if n > 1)


def charger_cas(donnees: object) -> list[Cas]:
    """Valide la structure de la table de cas désérialisée et la convertit en ``Cas``.

    ``donnees`` est le YAML déjà chargé (``{"version": .., "cas": [..]}``). Toute
    malformation lève ``ValueError`` : un cas sans règle, un identifiant mal formé ou
    un champ manquant est une panne, jamais un cas silencieusement ignoré.
    """
    if not isinstance(donnees, dict):
        raise ValueError("La table de cas doit être un mapping à la racine.")
    cas_bruts = donnees.get("cas")
    if not isinstance(cas_bruts, list) or not cas_bruts:
        raise ValueError("La table de cas doit contenir une liste non vide sous la clé « cas ».")

    cas: list[Cas] = []
    ids_vus: set[str] = set()
    for i, brut in enumerate(cas_bruts):
        if not isinstance(brut, dict):
            raise ValueError(f"Cas #{i} : chaque cas doit être un mapping.")
        cid = brut.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise ValueError(f"Cas #{i} : « id » manquant ou vide.")
        if cid in ids_vus:
            raise ValueError(f"Cas « {cid} » : identifiant en double.")
        ids_vus.add(cid)

        regles = brut.get("regles")
        if not isinstance(regles, list) or not regles:
            raise ValueError(f"Cas « {cid} » : doit nommer au moins une règle (« regles »).")
        regles_norm: list[str] = []
        for r in regles:
            if not isinstance(r, str) or not MOTIF_REGLE.fullmatch(r):
                raise ValueError(
                    f"Cas « {cid} » : « {r!r} » n'est pas un identifiant de règle R-x.y."
                )
            regles_norm.append(r)

        categorie = brut.get("categorie")
        if not isinstance(categorie, str) or not categorie.strip():
            raise ValueError(f"Cas « {cid} » : « categorie » manquante.")
        description = brut.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Cas « {cid} » : « description » manquante.")

        cas_limite = brut.get("cas_limite")
        if cas_limite is not None and (not isinstance(cas_limite, str) or not cas_limite.strip()):
            raise ValueError(f"Cas « {cid} » : « cas_limite » doit être une chaîne non vide.")

        cas.append(
            Cas(
                id=cid,
                regles=tuple(regles_norm),
                categorie=categorie,
                description=description,
                cas_limite=cas_limite,
                regles_brutes=tuple(regles_norm),
            )
        )
    return cas


def regles_orphelines(cas: list[Cas], definies: set[str]) -> dict[str, list[str]]:
    """Pour chaque cas, les règles qu'il cite mais qui n'existent pas dans le corpus.

    Un dictionnaire vide = tout cas cite une règle définie. Un cas qui cite une règle
    absente est une incohérence : la table ment sur ce qu'elle vérifie.
    """
    manquants: dict[str, list[str]] = {}
    for c in cas:
        absentes = [r for r in c.regles if r not in definies]
        if absentes:
            manquants[c.id] = absentes
    return manquants


def cas_limites_manquants(cas: list[Cas], requis: frozenset[str] = CAS_LIMITES_REQUIS) -> set[str]:
    """Les cas limites exigés par la mission que la table ne couvre pas encore."""
    couverts = {c.cas_limite for c in cas if c.cas_limite}
    return set(requis) - couverts
