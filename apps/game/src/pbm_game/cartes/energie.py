"""Définition d'une **carte Énergie** — sa fourniture et, pour les spéciales, ses effets.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il porte la **capacité** d'une énergie :
ce qu'elle **fournit** (types et quantités) et, pour une énergie spéciale, les **effets**
qu'elle apporte quand elle est en jeu. Rien n'est écrit en dur : le service (``apps/api``)
lit le catalogue (``energyType``, le texte de l'énergie) et fabrique une
:class:`DefinitionEnergie` que le moteur consomme — il ne devine aucune fourniture (D9).

**Fourniture générique, pas un type figé (R-9.2).** Une énergie n'est pas « de type Feu » :
elle **fournit** ``{"feu": 1}``. Ce détour permet d'exprimer, sans cas particulier, l'Énergie
Feu de base (``{"feu": 1}``), la Double Énergie Incolore (``{"incolore": 2}`` — plusieurs
unités) et une énergie spéciale bi-type (``{"feu": 1, "eau": 1}`` — plusieurs types). Le
paiement d'un coût (:func:`pbm_game.combat.cout.payer_cout`) travaille sur ces fournitures.

**De base vs spéciale : une décision de légalité, pas de jeu (D10).** Qu'une énergie soit
« de base » (fournie illimitée, jamais décomptée de la collection) ou « spéciale » (possédée,
soumise à la règle des 4) relève de la **construction du deck**, dont la seule source de
vérité est ``apps/api/src/pbm_api/decks/energy.py`` (on ne la redit pas ici). En jeu, le
moteur ne distingue pas : une énergie attachée fournit ce qu'elle fournit. Ce module ne porte
donc **que** la capacité de jeu — fourniture et effets.

**Effets d'énergie spéciale (D9).** Une énergie spéciale peut porter un effet (soin, dégâts
supplémentaires, coût de retraite modifié). On le décrit par un :class:`EffetEnergie` qui se
transforme en :class:`~pbm_game.effets.pile.EffetEnAttente` **empilable** sur la pile d'effets
— c'est le branchement demandé par ce lot. Le *script* de chaque effet (son résolveur dans le
``RegistreEffets``) est livré, scripté et testé, par les lots d'effets : une énergie dont
l'effet n'est pas enregistré est **refusée à la construction du deck** (D9), jamais jouée de
travers. Ce module ne fait que produire les entrées de pile, fidèlement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..combat.cout import EnergieAttachee, pool_energies
from ..effets.pile import EffetEnAttente, SourceEffet


@dataclass(frozen=True)
class EffetEnergie:
    """La spéc d'un effet porté par une énergie spéciale — un futur :class:`EffetEnAttente`.

    * ``type_effet`` — la clé du ``RegistreEffets`` qui saura le résoudre ; un type absent du
      registre est **refusé** (D9), jamais deviné ;
    * ``regle`` — l'identifiant ``R-x.y`` que l'effet applique (jamais vide) ;
    * ``libelle`` — le nom lisible de l'effet (« Soin à l'attache ») ;
    * ``params`` — les paramètres de résolution, en valeurs JSON natives.
    """

    type_effet: str
    regle: str
    libelle: str
    params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type_effet, str) or not self.type_effet.strip():
            raise ValueError("Un effet d'énergie doit nommer son type de résolution (D9).")
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un effet d'énergie doit citer la règle R-x.y qu'il applique (D9).")
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Un effet d'énergie doit porter un libellé lisible.")


@dataclass(frozen=True)
class DefinitionEnergie:
    """La capacité de jeu d'une carte Énergie, telle que le moteur la reçoit du catalogue.

    * ``ref`` — la référence catalogue (``tcgdex_id`` ou identifiant stable) ;
    * ``nom`` — le nom imprimé (sert de libellé lisible dans le journal) ;
    * ``fournit`` — ``{type: unités}`` que l'énergie apporte au paiement d'un coût (R-9.2) ;
      au moins une unité — une énergie qui ne fournit rien est une panne, pas un cas normal ;
    * ``effets`` — les effets portés (vide pour une énergie de base ou une spéciale sans effet).

    La validation **refuse** une fiche incohérente plutôt que de deviner (D9) : une fourniture
    malformée (type vide, unités négatives) ou vide fait échouer bruyamment.
    """

    ref: str
    nom: str
    fournit: Mapping[str, int]
    effets: tuple[EffetEnergie, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ValueError("Définition d'énergie : « ref » (référence catalogue) requis.")
        if not isinstance(self.nom, str) or not self.nom.strip():
            raise ValueError(f"Définition d'énergie « {self.ref} » : « nom » requis.")
        # Même garde que le pool (type/unités) : une fourniture malformée est une panne.
        total = sum(pool_energies([self.fournit]).values())
        if total < 1:
            raise ValueError(
                f"Énergie « {self.nom} » : doit fournir au moins une unité (R-9.2) — une "
                "fourniture vide est une panne, jamais un cas normal."
            )
        if not isinstance(self.effets, tuple) or any(
            not isinstance(e, EffetEnergie) for e in self.effets
        ):
            raise ValueError(
                f"Énergie « {self.nom} » : « effets » doit être un tuple d'EffetEnergie."
            )

    def attachee(self, instance_id: str) -> EnergieAttachee:
        """L':class:`~pbm_game.combat.cout.EnergieAttachee` de cet exemplaire en jeu (R-9.2).

        C'est le pont entre la carte (``DefinitionEnergie``) et le paiement d'un coût : le
        service résout une ``Carte`` attachée (``instance_id``) en cette énergie, puis en son
        descripteur de paiement, portant le nom lisible pour le journal.
        """
        return EnergieAttachee(
            instance_id=instance_id, fournit=dict(self.fournit), libelle=self.nom
        )

    def source(self, instance_id: str | None = None) -> SourceEffet:
        """La :class:`~pbm_game.effets.pile.SourceEffet` qui attribue un effet à cette énergie."""
        return SourceEffet(libelle=self.nom, ref=self.ref, instance_id=instance_id)

    def effets_en_attente(self, instance_id: str | None = None) -> tuple[EffetEnAttente, ...]:
        """Les :class:`EffetEnAttente` à **empiler** sur la pile d'effets pour cette énergie.

        Transforme chaque :class:`EffetEnergie` en un effet empilable, attribué à cette énergie
        comme source (« à cause de l'Énergie X »). C'est le branchement sur la pile d'effets
        (``pbm_game.effets.pile``) demandé par ce lot : le *résolveur* de chaque ``type_effet``
        est enregistré, scripté et testé, par les lots d'effets (D9). Vide pour une énergie sans
        effet (énergie de base, spéciale purement fournisseuse).
        """
        src = self.source(instance_id)
        return tuple(
            EffetEnAttente(
                type_effet=e.type_effet,
                source=src,
                regle=e.regle,
                libelle=e.libelle,
                params=dict(e.params),
            )
            for e in self.effets
        )


def definition_energie_depuis_dict(donnees: object) -> DefinitionEnergie:
    """Construit une :class:`DefinitionEnergie` depuis un mapping JSON-ish (catalogue, test).

    Entrée du moteur pour les énergies : le service fournit ``{ref, nom, fournit, effets}``.
    La validation de :class:`DefinitionEnergie` **mord** ici (fourniture vide ou malformée).
    """
    if not isinstance(donnees, Mapping):
        raise ValueError(
            "Une définition d'énergie se décrit par un mapping (fournie par le service depuis "
            "le catalogue, D9)."
        )
    effets_brut = donnees.get("effets", [])
    if not isinstance(effets_brut, (list, tuple)):
        raise ValueError("« effets » doit être une liste.")
    effets = tuple(
        EffetEnergie(
            type_effet=e.get("type_effet", ""),
            regle=e.get("regle", ""),
            libelle=e.get("libelle", ""),
            params=dict(e.get("params", {})),
        )
        for e in effets_brut
        if isinstance(e, Mapping)
    )
    return DefinitionEnergie(
        ref=donnees.get("ref", ""),
        nom=donnees.get("nom", ""),
        fournit=dict(donnees.get("fournit", {})),
        effets=effets,
    )


__all__ = [
    "EffetEnergie",
    "DefinitionEnergie",
    "definition_energie_depuis_dict",
]
