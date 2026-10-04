"""Définition d'une **carte Pokémon** — le descripteur que le moteur reçoit du catalogue.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il porte la
**forme** des caractéristiques d'une carte Pokémon — stade d'évolution, PV, type, faiblesse,
résistance, coût de retraite, marqueur de règle, attaques — mais **aucune** valeur en dur : le
service (``apps/api``) extrait ces champs du catalogue (``cards.attacks``, ``weaknesses``,
``resistances``, ``retreat_cost``, ``prize_marker``…) et fabrique un :class:`DefinitionCarte` que
le moteur consomme. Le moteur ne devine donc **aucune** caractéristique (D9 — un effet non
implémenté n'est jamais approximé) : une donnée manquante **bloque** la carte, elle n'est pas
inventée.

Règles de référence structurées ici (``docs/jeu/REGLES.md``) :

* **R-7.1** — l'évolution se pose sur son prédécesseur imprimé (``evolue_depuis``) ;
* **R-10.2 / R-10.3** — faiblesse et résistance (déléguées à :mod:`pbm_game.combat.modele`) ;
* **R-13.1** — les PV se lisent sur la carte ;
* **R-13.3 / R-13.4 / R-15.22** — le **marqueur de règle** fixe les récompenses ; un marqueur
  **inconnu** est refusé (jamais « par défaut 1 »), via la table close de
  :mod:`pbm_game.combat.fin` ;
* **R-9.2** — le coût d'une attaque (délégué à :class:`pbm_game.combat.modele.CoutAttaque`).

**Attaques à effet (lot ``j-cartes-attaques-effets``).** Une attaque peut porter un **script**
d'effet (DSL, ``pbm_game.effets.dsl``) et/ou des **dégâts variables** (``degats`` décrit alors une
formule calculée à la résolution, :mod:`pbm_game.combat.valeur`). Une attaque dont le texte porte un
effet **sans** script reste **non jouable** (D9) : elle se charge fidèlement pour que la
construction de deck la refuse en disant pourquoi, mais le moteur ne la résout pas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..combat.fin import recompenses_pour_marqueur
from ..combat.modele import (
    FAIBLESSE_FACTEUR_DEFAUT,
    RESISTANCE_REDUCTION_DEFAUT,
    CoutAttaque,
    Faiblesse,
    Resistance,
)

# --- Stades d'évolution (R-7) -------------------------------------------------
STADE_BASE = "base"
STADE_1 = "stade1"
STADE_2 = "stade2"

#: Les trois stades reconnus (R-7). Un stade absent de cet ensemble **bloque** la carte : on ne
#: devine pas le stade d'un Pokémon (D9).
STADES: frozenset[str] = frozenset({STADE_BASE, STADE_1, STADE_2})

#: Les stades d'**évolution** (ceux qui se posent sur un Pokémon déjà en jeu, R-7.1).
STADES_EVOLUTION: frozenset[str] = frozenset({STADE_1, STADE_2})


@dataclass(frozen=True)
class AttaqueDef:
    """Une attaque d'une carte Pokémon (R-9.2 / R-10).

    * ``nom`` — le nom imprimé de l'attaque ;
    * ``cout`` — son :class:`~pbm_game.combat.modele.CoutAttaque` (colorés + incolores) ;
    * ``degats`` — les dégâts **secs** imprimés (multiple de 10, ``≥ 0`` ; ``0`` = pas de dégâts
      secs, soit parce que l'attaque n'inflige rien directement, soit parce qu'elle a des dégâts
      **variables**, portés alors par ``degats_variables``) ;
    * ``effet`` — le texte d'effet brut ; **vide** = attaque à dégâts secs, **non vide** = l'attaque
      porte un effet (jouable **seulement** si elle a un ``script``, D9 sinon) ;
    * ``script`` — le **script DSL** de l'effet (mapping ``{version, effets, cout?}``), ou ``None``.
      Validé **ici** (il doit se charger) : un script incohérent **bloque** la carte à la
      construction du deck, jamais en pleine partie ;
    * ``degats_variables`` — une formule de **dégâts variables** (mapping),
      ou ``None``. Exclusif de dégâts secs non nuls (la base va dans la formule).
    """

    nom: str
    cout: CoutAttaque
    degats: int = 0
    effet: str = ""
    script: dict | None = None
    degats_variables: dict | None = None
    pouvoir_unique: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.nom, str) or not self.nom.strip():
            raise ValueError("Une attaque doit porter un nom imprimé.")
        if not isinstance(self.cout, CoutAttaque):
            raise ValueError(f"Attaque « {self.nom} » : « cout » doit être un CoutAttaque (R-9.2).")
        if not isinstance(self.degats, int) or isinstance(self.degats, bool) or self.degats < 0:
            raise ValueError(
                f"Attaque « {self.nom} » : « degats » invalides {self.degats!r} (entier ≥ 0)."
            )
        if self.degats % 10 != 0:
            raise ValueError(
                f"Attaque « {self.nom} » : « degats » {self.degats} non multiple de 10 (R-10.6)."
            )
        if not isinstance(self.effet, str):
            raise ValueError(
                f"Attaque « {self.nom} » : « effet » doit être une chaîne (vide si dégâts secs)."
            )
        if self.script is not None:
            if not isinstance(self.script, dict):
                raise ValueError(f"Attaque « {self.nom} » : « script » doit être un mapping DSL.")
            # Validation D9 au plus tôt : un script qui ne se charge pas bloque la carte à la
            # construction du deck, jamais au milieu d'une partie. Import local (``effets``
            # dépend de ``state`` ; on ne le tire pas au chargement de ``cartes``).
            from ..effets.dsl.chargement import charger_programme

            charger_programme(self.script)
        if self.degats_variables is not None:
            if not isinstance(self.degats_variables, dict):
                raise ValueError(
                    f"Attaque « {self.nom} » : « degats_variables » doit être un mapping."
                )
            if self.degats != 0:
                raise ValueError(
                    f"Attaque « {self.nom} » : des dégâts variables ne cohabitent pas avec des "
                    "dégâts secs non nuls (la base va dans la formule)."
                )
            from ..combat.valeur import valeur_depuis

            valeur_depuis(self.degats_variables)  # D9 : une formule incohérente bloque la carte.
        if self.pouvoir_unique is not None:
            # D9 : un pouvoir à usage unique inconnu bloque la carte à la construction du deck,
            # jamais en pleine partie (attaque GX R-15.3, VSTAR Power R-15.6).
            from ..combat.pouvoirs_uniques import valider_pouvoir

            valider_pouvoir(self.pouvoir_unique)

    @property
    def jouable(self) -> bool:
        """Vrai si l'attaque est **résoluble** : dégâts secs, scriptée, ou à dégâts variables.

        Une attaque à texte d'effet **sans** script **ni** dégâts variables n'est pas jouable (D9) —
        on ne l'approxime pas. Les dégâts variables portent à eux seuls une « 20 × énergie ».
        """
        return (
            not self.effet.strip() or self.script is not None or self.degats_variables is not None
        )

    @property
    def degats_secs(self) -> bool:
        """Vrai si l'attaque n'a aucun effet scripté ni dégâts variables (la forme simple)."""
        return not self.effet.strip() and self.script is None and self.degats_variables is None


@dataclass(frozen=True)
class DefinitionCarte:
    """La fiche complète d'une carte Pokémon, telle que le moteur la reçoit du catalogue.

    Aucune valeur n'est écrite en dur dans le moteur : le service alimente ces champs depuis le
    catalogue. La validation (:meth:`__post_init__`) **refuse** une fiche incohérente plutôt que
    de deviner (D9) — un marqueur de règle inconnu, un stade absent, des PV absurdes, une chaîne
    d'évolution manquante font **échouer bruyamment**.

    * ``ref`` — la référence catalogue (``tcgdex_id`` ou identifiant stable) ;
    * ``nom`` — le nom imprimé (sert la chaîne d'évolution, R-7.1) ;
    * ``stade`` — un des :data:`STADES` ;
    * ``pv`` — les points de vie (R-13.1) ;
    * ``type`` — le type du Pokémon (sa couleur d'énergie), pour faiblesse/résistance (R-10.2) ;
    * ``marqueur`` — le marqueur de règle normalisé (clé de
      :data:`pbm_game.combat.fin.MARQUEUR_RECOMPENSES`) : fixe les récompenses (R-13.3) ;
    * ``evolue_depuis`` — le **nom** du Pokémon dont cette carte est l'évolution (``None`` pour
      une base ; requis pour un stade 1 / stade 2, R-7.1) ;
    * ``faiblesse`` / ``resistance`` — facultatives (R-10.2/R-10.3) ;
    * ``cout_retraite`` — le nombre de symboles du coût de retraite (R-8.2) ;
    * ``attaques`` — les attaques de la carte (R-9.2 ; seules celles à dégâts secs sont jouables).
    """

    ref: str
    nom: str
    stade: str
    pv: int
    type: str
    marqueur: str
    evolue_depuis: str | None = None
    faiblesse: Faiblesse | None = None
    resistance: Resistance | None = None
    cout_retraite: int = 0
    attaques: tuple[AttaqueDef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ValueError("Définition de carte : « ref » (référence catalogue) requis.")
        if not isinstance(self.nom, str) or not self.nom.strip():
            raise ValueError(f"Définition « {self.ref} » : « nom » requis.")
        if self.stade not in STADES:
            raise ValueError(
                f"Définition « {self.nom} » : stade inconnu {self.stade!r} — un champ manquant "
                f"bloque la carte, jamais deviné (connus : {sorted(STADES)})."
            )
        if not isinstance(self.pv, int) or isinstance(self.pv, bool) or self.pv < 1:
            raise ValueError(
                f"Définition « {self.nom} » : PV invalides {self.pv!r} (entier ≥ 1, R-13.1)."
            )
        if not isinstance(self.type, str) or not self.type.strip():
            raise ValueError(f"Définition « {self.nom} » : « type » requis (R-10.2).")
        # Marqueur de règle : validé contre la table close du moteur. Inconnu = refus bruyant
        # (R-13.4/R-15.22) — jamais « par défaut 1 ». La valeur de retour n'importe pas ici.
        recompenses_pour_marqueur(self.marqueur)
        # Chaîne d'évolution (R-7.1) : une base n'évolue de rien ; une évolution nomme son
        # prédécesseur — un champ d'évolution manquant **bloque** la carte (jamais deviné, D9).
        if self.stade == STADE_BASE:
            if self.evolue_depuis is not None:
                raise ValueError(
                    f"Définition « {self.nom} » : un Pokémon de base n'évolue d'aucun autre "
                    "(« evolue_depuis » doit être absent)."
                )
        elif not isinstance(self.evolue_depuis, str) or not self.evolue_depuis.strip():
            raise ValueError(
                f"Définition « {self.nom} » (stade {self.stade}) : « evolue_depuis » requis — un "
                "champ d'évolution manquant bloque la carte, jamais deviné (R-7.1)."
            )
        if (
            not isinstance(self.cout_retraite, int)
            or isinstance(self.cout_retraite, bool)
            or self.cout_retraite < 0
        ):
            raise ValueError(
                f"Définition « {self.nom} » : coût de retraite invalide {self.cout_retraite!r} "
                "(entier ≥ 0, R-8.2)."
            )
        if self.faiblesse is not None and not isinstance(self.faiblesse, Faiblesse):
            raise ValueError(f"Définition « {self.nom} » : « faiblesse » doit être un Faiblesse.")
        if self.resistance is not None and not isinstance(self.resistance, Resistance):
            raise ValueError(f"Définition « {self.nom} » : « resistance » doit être un Resistance.")
        if not isinstance(self.attaques, tuple) or any(
            not isinstance(a, AttaqueDef) for a in self.attaques
        ):
            raise ValueError(
                f"Définition « {self.nom} » : « attaques » doit être un tuple d'AttaqueDef."
            )

    @property
    def est_evolution(self) -> bool:
        """Vrai si la carte est une évolution (stade 1/2) — elle se pose sur un Pokémon (R-7.1)."""
        return self.stade in STADES_EVOLUTION

    @property
    def recompenses(self) -> int:
        """Le nombre de récompenses que donne un K.O. de cette carte, via son marqueur (R-13.3)."""
        return recompenses_pour_marqueur(self.marqueur)

    def fiche(self) -> dict:
        """La fiche ``{pv, marqueur}`` attendue par le Checkup et la résolution des K.O. (D9).

        C'est le sous-ensemble de la définition que :func:`pbm_game.combat.fin.valider_fiches`
        consomme : une seule source (le catalogue), deux lecteurs (K.O. et Checkup).
        """
        return {"pv": self.pv, "marqueur": self.marqueur}


def _cout_depuis(donnees: object) -> CoutAttaque:
    if donnees is None:
        return CoutAttaque()
    if not isinstance(donnees, Mapping):
        raise ValueError("Le coût d'une attaque se décrit par un mapping {types, incolore}.")
    return CoutAttaque(types=dict(donnees.get("types", {})), incolore=donnees.get("incolore", 0))


def _attaque_depuis(donnees: object) -> AttaqueDef:
    if not isinstance(donnees, Mapping):
        raise ValueError("Une attaque se décrit par un mapping {nom, cout, degats, effet}.")
    return AttaqueDef(
        nom=donnees.get("nom", ""),
        cout=_cout_depuis(donnees.get("cout")),
        degats=donnees.get("degats", 0),
        effet=donnees.get("effet", ""),
        script=donnees.get("script"),
        degats_variables=donnees.get("degats_variables"),
        pouvoir_unique=donnees.get("pouvoir_unique"),
    )


def _attaque_vers_dict(a: AttaqueDef) -> dict:
    """Projette une :class:`AttaqueDef` en ``dict`` JSON-natif (script, dégâts variables inclus)."""
    donnees: dict = {
        "nom": a.nom,
        "cout": {"types": dict(a.cout.types), "incolore": a.cout.incolore},
        "degats": a.degats,
        "effet": a.effet,
    }
    if a.script is not None:
        donnees["script"] = a.script
    if a.degats_variables is not None:
        donnees["degats_variables"] = a.degats_variables
    if a.pouvoir_unique is not None:
        donnees["pouvoir_unique"] = a.pouvoir_unique
    return donnees


def definition_vers_dict(definition: DefinitionCarte) -> dict:
    """Projette une :class:`DefinitionCarte` en ``dict`` JSON-natif (inverse de la lecture).

    C'est le chemin **service → action** : le service (``apps/api``) a extrait la fiche du
    catalogue, il la sérialise ici pour la porter dans les ``params`` d'une action (``poser``,
    ``evoluer``, mise en place) — le journal la transporte, donc le rejeu n'a pas besoin du
    catalogue. Round-trip exact : ``definition_depuis_dict(definition_vers_dict(d)) == d``.
    """
    donnees: dict = {
        "ref": definition.ref,
        "nom": definition.nom,
        "stade": definition.stade,
        "pv": definition.pv,
        "type": definition.type,
        "marqueur": definition.marqueur,
        "evolue_depuis": definition.evolue_depuis,
        "cout_retraite": definition.cout_retraite,
        "attaques": [_attaque_vers_dict(a) for a in definition.attaques],
    }
    if definition.faiblesse is not None:
        donnees["faiblesse"] = {
            "type": definition.faiblesse.type,
            "facteur": definition.faiblesse.facteur,
        }
    if definition.resistance is not None:
        donnees["resistance"] = {
            "type": definition.resistance.type,
            "reduction": definition.resistance.reduction,
        }
    return donnees


def definition_depuis_dict(donnees: object) -> DefinitionCarte:
    """Construit un :class:`DefinitionCarte` depuis un mapping JSON-ish (params d'action, test).

    C'est l'entrée du moteur : une action ``poser`` / ``evoluer`` porte sa ``definition`` sous
    forme de ``dict`` (le journal la transporte, donc le rejeu n'a pas besoin du catalogue). La
    validation de :class:`DefinitionCarte` **mord** ici (marqueur inconnu, champ manquant).
    """
    if not isinstance(donnees, Mapping):
        raise ValueError(
            "Une définition de carte se décrit par un mapping (fournie par le service depuis le "
            "catalogue, D9)."
        )
    faiblesse_brut = donnees.get("faiblesse")
    faiblesse = (
        Faiblesse(
            type=faiblesse_brut.get("type", ""),
            facteur=faiblesse_brut.get("facteur", FAIBLESSE_FACTEUR_DEFAUT),
        )
        if isinstance(faiblesse_brut, Mapping)
        else None
    )
    resistance_brut = donnees.get("resistance")
    resistance = (
        Resistance(
            type=resistance_brut.get("type", ""),
            reduction=resistance_brut.get("reduction", RESISTANCE_REDUCTION_DEFAUT),
        )
        if isinstance(resistance_brut, Mapping)
        else None
    )
    attaques_brut = donnees.get("attaques", [])
    if not isinstance(attaques_brut, (list, tuple)):
        raise ValueError("« attaques » doit être une liste.")
    return DefinitionCarte(
        ref=donnees.get("ref", ""),
        nom=donnees.get("nom", ""),
        stade=donnees.get("stade", ""),
        pv=donnees.get("pv"),
        type=donnees.get("type", ""),
        marqueur=donnees.get("marqueur", ""),
        evolue_depuis=donnees.get("evolue_depuis"),
        faiblesse=faiblesse,
        resistance=resistance,
        cout_retraite=donnees.get("cout_retraite", 0),
        attaques=tuple(_attaque_depuis(a) for a in attaques_brut),
    )


__all__ = [
    "STADE_BASE",
    "STADE_1",
    "STADE_2",
    "STADES",
    "STADES_EVOLUTION",
    "AttaqueDef",
    "DefinitionCarte",
    "definition_depuis_dict",
    "definition_vers_dict",
]
