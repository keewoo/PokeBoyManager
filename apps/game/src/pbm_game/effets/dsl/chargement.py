"""Le **chargement validant** d'un script d'effet — la porte d'entrée, seul endroit de refus.

Module **pur** (aucune E/S). :func:`charger_programme` transforme un ``dict`` JSON-ish en
:class:`~pbm_game.effets.dsl.modele.Programme` **validé**, ou lève :class:`ProgrammeInvalide`.

**Un script non conforme est refusé ICI, au chargement — jamais en pleine partie** (critère
d'acceptation n°3). C'est le pendant de la validation des ``DefinitionCarte``
et des ``action.type`` : un ``op`` inconnu, une clé parasite, une cible incohérente, un état hors
des cinq, un verrou inventé — tout cela **mord** avant qu'une seule instruction ne s'exécute. Le
validateur est **strict** : une clé qu'il ne connaît pas est une erreur (jamais ignorée en
silence), parce qu'une clé ignorée, c'est un effet qu'on croit avoir décrit et qui ne s'exécute pas.

**Versionnement** (critère n°4). Le champ ``version`` est obligatoire. L'interprète courant lit
les versions ``DSL_VERSION_MIN`` … :data:`~pbm_game.effets.dsl.vocabulaire.DSL_VERSION` : un script
écrit pour la v1 **reste lisible** quand la v2 sort. Une version **future** (ou antérieure au
plancher) est **refusée bruyamment** — jamais chargée « au mieux ».
"""

from __future__ import annotations

from collections.abc import Mapping

from ...state.modele import ETATS_SPECIAUX
from ..verrous import PORTEES_VERROU, VERROUS
from .modele import Condition, Instruction, Programme, Selecteur
from .vocabulaire import (
    CATEGORIES,
    COND_TYPE_CIBLE,
    CONDITIONS,
    CTRL_REPETER,
    CTRL_SI,
    DSL_VERSION,
    DSL_VERSION_MIN,
    INSTRUCTIONS,
    OP_ATTACHER,
    OP_CHANGER_ACTIF,
    OP_CHERCHER,
    OP_CHOISIR,
    OP_DEFAUSSER,
    OP_DEPLACER,
    OP_EMPECHER,
    OP_INFLIGER_DEGATS,
    OP_MELANGER,
    OP_PILE_OU_FACE,
    OP_PIOCHER,
    OP_POSER_COMPTEURS,
    OP_POSER_ETAT,
    OP_REGARDER,
    OP_RETIRER_ETAT,
    OP_REVELER,
    OP_SOIGNER,
    POSITIONS,
    PROPRIETAIRES,
    ZONE_PIOCHE,
    ZONE_STADE,
    ZONES,
)

# Les stades d'évolution reconnus comme filtre d'un sélecteur (R-7). Importés ici plutôt que
# depuis cartes.modele pour ne pas faire dépendre le DSL du socle de cartes : ce sont des
# chaînes de règle, pas un type.
_STADES: frozenset[str] = frozenset({"base", "stade1", "stade2"})

# Primitives qui EXIGENT une cible principale (hors contexte d'un ``choisir``, où la cible par
# défaut est l'ensemble choisi).
_OPS_CIBLE_REQUISE: frozenset[str] = frozenset(
    {
        OP_CHERCHER,
        OP_DEFAUSSER,
        OP_ATTACHER,
        OP_DEPLACER,
        OP_SOIGNER,
        OP_POSER_COMPTEURS,
        OP_INFLIGER_DEGATS,
        OP_REVELER,
        OP_REGARDER,
        OP_CHOISIR,
        OP_CHANGER_ACTIF,
        OP_POSER_ETAT,
        OP_RETIRER_ETAT,
    }
)
# Primitives qui EXIGENT un sélecteur source (origine) en plus de la cible (destination).
_OPS_SOURCE_REQUISE: frozenset[str] = frozenset({OP_ATTACHER, OP_DEPLACER})
# Primitives qui EXIGENT un ``nombre`` entier strictement positif.
_OPS_NOMBRE_REQUIS: frozenset[str] = frozenset({OP_PIOCHER, OP_POSER_COMPTEURS, OP_INFLIGER_DEGATS})

# Clés autorisées, par brique — tout le reste est refusé (strict).
_CLES_SELECTEUR = {"zone", "proprietaire", "categorie", "stade", "nombre", "position"}
_CLES_CONDITION = {"type", "cible", "etat", "attendu", "minimum", "type_pokemon"}
_CLES_INSTRUCTION = {
    "op",
    "cible",
    "source",
    "nombre",
    "etat",
    "verrou",
    "portee",
    "condition",
    "alors",
    "sinon",
    "jusqu_a_echec",
    "regle",
}
_CLES_PROGRAMME = {"version", "effets", "cout"}


class ProgrammeInvalide(ValueError):
    """Un script d'effet non conforme — refusé **au chargement**, jamais en pleine partie."""


def _exiger_mapping(valeur: object, quoi: str) -> Mapping:
    if not isinstance(valeur, Mapping):
        raise ProgrammeInvalide(f"{quoi} : attendu un objet, reçu {type(valeur).__name__}.")
    return valeur


def _refuser_cles_parasites(donnees: Mapping, autorisees: set[str], quoi: str) -> None:
    parasites = set(donnees) - autorisees
    if parasites:
        raise ProgrammeInvalide(
            f"{quoi} : clé(s) inconnue(s) {sorted(parasites)} — une clé ignorée est un effet "
            f"qu'on croit avoir décrit (refus strict). Clés connues : {sorted(autorisees)}."
        )


def _entier_positif(valeur: object, quoi: str) -> int:
    if not isinstance(valeur, int) or isinstance(valeur, bool) or valeur <= 0:
        raise ProgrammeInvalide(f"{quoi} : entier strictement positif attendu, reçu {valeur!r}.")
    return valeur


def _charger_selecteur(donnees: object, quoi: str) -> Selecteur:
    d = _exiger_mapping(donnees, quoi)
    _refuser_cles_parasites(d, _CLES_SELECTEUR, quoi)
    zone = d.get("zone")
    if zone not in ZONES:
        raise ProgrammeInvalide(f"{quoi} : zone inconnue {zone!r} (connues : {sorted(ZONES)}).")
    proprietaire = d.get("proprietaire", "moi")
    if proprietaire not in PROPRIETAIRES:
        raise ProgrammeInvalide(
            f"{quoi} : propriétaire inconnu {proprietaire!r} (connus : {sorted(PROPRIETAIRES)})."
        )
    categorie = d.get("categorie")
    if categorie is not None and categorie not in CATEGORIES:
        raise ProgrammeInvalide(
            f"{quoi} : catégorie inconnue {categorie!r} (connues : {sorted(CATEGORIES)})."
        )
    stade = d.get("stade")
    if stade is not None and stade not in _STADES:
        raise ProgrammeInvalide(f"{quoi} : stade inconnu {stade!r} (connus : {sorted(_STADES)}).")
    nombre = d.get("nombre")
    if nombre is not None:
        nombre = _entier_positif(nombre, f"{quoi}.nombre")
    position = d.get("position", "au_choix")
    if position not in POSITIONS:
        raise ProgrammeInvalide(
            f"{quoi} : position inconnue {position!r} (connues : {sorted(POSITIONS)})."
        )
    return Selecteur(
        zone=zone,
        proprietaire=proprietaire,
        categorie=categorie,
        stade=stade,
        nombre=nombre,
        position=position,
    )


def _charger_condition(donnees: object, quoi: str) -> Condition:
    d = _exiger_mapping(donnees, quoi)
    _refuser_cles_parasites(d, _CLES_CONDITION, quoi)
    type_ = d.get("type")
    if type_ not in CONDITIONS:
        raise ProgrammeInvalide(
            f"{quoi} : condition inconnue {type_!r} (connues : {sorted(CONDITIONS)})."
        )
    cible = _charger_selecteur(d["cible"], f"{quoi}.cible") if "cible" in d else None
    etat = d.get("etat")
    if etat is not None and etat not in ETATS_SPECIAUX:
        raise ProgrammeInvalide(
            f"{quoi} : état inconnu {etat!r} (les cinq : {sorted(ETATS_SPECIAUX)})."
        )
    attendu = d.get("attendu")
    if attendu is not None and attendu not in ("face", "pile"):
        raise ProgrammeInvalide(f"{quoi}.attendu : « face » ou « pile » attendu, reçu {attendu!r}.")
    minimum = d.get("minimum")
    if minimum is not None:
        minimum = _entier_positif(minimum, f"{quoi}.minimum")
    type_pokemon = d.get("type_pokemon")
    if type_pokemon is not None and (not isinstance(type_pokemon, str) or not type_pokemon.strip()):
        raise ProgrammeInvalide(
            f"{quoi}.type_pokemon : chaîne non vide attendue (le type de la cible), "
            f"reçu {type_pokemon!r}."
        )
    # Garanties par condition : chacune exige ce dont elle a besoin, jamais deviné (D9).
    if type_ == COND_TYPE_CIBLE:
        if cible is None:
            raise ProgrammeInvalide(
                f"{quoi} : « type_cible » exige une « cible » (le Pokémon visé)."
            )
        if type_pokemon is None:
            raise ProgrammeInvalide(
                f"{quoi} : « type_cible » exige un « type_pokemon » (le type attendu)."
            )
    elif type_pokemon is not None:
        raise ProgrammeInvalide(f"{quoi} : « type_pokemon » n'a de sens que pour « type_cible ».")
    return Condition(
        type=type_,
        cible=cible,
        etat=etat,
        attendu=attendu,
        minimum=minimum,
        type_pokemon=type_pokemon,
    )


def _charger_instructions(
    donnees: object, quoi: str, *, dans_choix: bool
) -> tuple[Instruction, ...]:
    if not isinstance(donnees, (list, tuple)):
        raise ProgrammeInvalide(
            f"{quoi} : liste d'instructions attendue, reçu {type(donnees).__name__}."
        )
    return tuple(
        _charger_instruction(d, f"{quoi}[{i}]", dans_choix=dans_choix)
        for i, d in enumerate(donnees)
    )


def _charger_instruction(donnees: object, quoi: str, *, dans_choix: bool) -> Instruction:
    d = _exiger_mapping(donnees, quoi)
    _refuser_cles_parasites(d, _CLES_INSTRUCTION, quoi)
    op = d.get("op")
    if op not in INSTRUCTIONS:
        raise ProgrammeInvalide(
            f"{quoi} : instruction inconnue {op!r} — il n'existe aucune primitive « code libre » "
            f"(D9). Connues : {sorted(INSTRUCTIONS)}."
        )

    cible = _charger_selecteur(d["cible"], f"{quoi}.cible") if "cible" in d else None
    source = _charger_selecteur(d["source"], f"{quoi}.source") if "source" in d else None
    nombre = _entier_positif(d["nombre"], f"{quoi}.nombre") if "nombre" in d else None
    etat = d.get("etat")
    verrou = d.get("verrou")
    portee = d.get("portee")
    condition = (
        _charger_condition(d["condition"], f"{quoi}.condition") if "condition" in d else None
    )
    regle = d.get("regle", "")
    if not isinstance(regle, str):
        raise ProgrammeInvalide(f"{quoi}.regle : chaîne attendue, reçu {regle!r}.")

    # --- Structures de contrôle -------------------------------------------------
    if op == CTRL_SI:
        if condition is None:
            raise ProgrammeInvalide(f"{quoi} : un « si » exige une « condition ».")
        alors = _charger_instructions(d.get("alors", []), f"{quoi}.alors", dans_choix=dans_choix)
        sinon = _charger_instructions(d.get("sinon", []), f"{quoi}.sinon", dans_choix=dans_choix)
        if not alors and not sinon:
            raise ProgrammeInvalide(
                f"{quoi} : un « si » vide ne fait rien — donnez « alors » ou « sinon »."
            )
        return Instruction(op=op, condition=condition, alors=alors, sinon=sinon, regle=regle)

    if op == CTRL_REPETER:
        if nombre is None and source is None:
            raise ProgrammeInvalide(
                f"{quoi} : un « repeter » exige « nombre » (fixe) ou « source » (pour chaque …)."
            )
        alors = _charger_instructions(d.get("alors", []), f"{quoi}.alors", dans_choix=dans_choix)
        if not alors:
            raise ProgrammeInvalide(f"{quoi} : un « repeter » sans corps « alors » ne fait rien.")
        return Instruction(op=op, nombre=nombre, source=source, alors=alors, regle=regle)

    # --- Primitives : « condition » est réservé au « si » (le « sinon » légitime de
    # pile_ou_face est traité dans son bloc ; tout « sinon » parasite tombe au catch-all plus bas).
    if "condition" in d:
        raise ProgrammeInvalide(f"{quoi} : « condition » n'a de sens que pour un « si ».")

    # --- pile_ou_face : nombre de pièces (ou jusqu'à échec) + branches alors (face) / sinon (pile)
    if op == OP_PILE_OU_FACE:
        alors = _charger_instructions(d.get("alors", []), f"{quoi}.alors", dans_choix=dans_choix)
        sinon = _charger_instructions(d.get("sinon", []), f"{quoi}.sinon", dans_choix=dans_choix)
        if not alors and not sinon:
            raise ProgrammeInvalide(f"{quoi} : un « pile_ou_face » sans branche ne décide de rien.")
        jusqu_a_echec = d.get("jusqu_a_echec", False)
        if not isinstance(jusqu_a_echec, bool):
            raise ProgrammeInvalide(
                f"{quoi}.jusqu_a_echec : booléen attendu, reçu {jusqu_a_echec!r}."
            )
        if jusqu_a_echec and nombre is not None:
            raise ProgrammeInvalide(
                f"{quoi} : « jusqu_a_echec » (jusqu'à pile) exclut « nombre » (pièces fixes)."
            )
        return Instruction(
            op=op, nombre=nombre, alors=alors, sinon=sinon, jusqu_a_echec=jusqu_a_echec, regle=regle
        )

    # --- choisir : la cible est les OPTIONS ; son corps « alors » agit sur le choix ---
    if op == OP_CHOISIR:
        if cible is None:
            raise ProgrammeInvalide(
                f"{quoi} : « choisir » exige une cible (les options parmi lesquelles choisir)."
            )
        if "sinon" in d:
            raise ProgrammeInvalide(f"{quoi} : « choisir » n'a pas de branche « sinon ».")
        alors = _charger_instructions(d.get("alors", []), f"{quoi}.alors", dans_choix=True)
        return Instruction(op=op, cible=cible, nombre=nombre, alors=alors, regle=regle)

    # Hors pile_ou_face/si/repeter/choisir, « alors »/« sinon » sont parasites.
    if "alors" in d or "sinon" in d:
        raise ProgrammeInvalide(
            f"{quoi} : « alors »/« sinon » ne valent que pour « si », « repeter », "
            "« pile_ou_face » ou « choisir »."
        )
    # « jusqu_a_echec » n'a de sens que pour « pile_ou_face » — ne jamais l'avaler en silence.
    if "jusqu_a_echec" in d:
        raise ProgrammeInvalide(f"{quoi} : « jusqu_a_echec » ne vaut que pour « pile_ou_face ».")

    # --- Cible / source / nombre requis selon la primitive --------------------
    if op in _OPS_CIBLE_REQUISE and cible is None and not dans_choix:
        raise ProgrammeInvalide(f"{quoi} : l'instruction « {op} » exige une cible.")
    if op in _OPS_SOURCE_REQUISE and source is None:
        raise ProgrammeInvalide(f"{quoi} : l'instruction « {op} » exige une « source » (origine).")
    if op in _OPS_NOMBRE_REQUIS and nombre is None:
        raise ProgrammeInvalide(f"{quoi} : l'instruction « {op} » exige un « nombre ».")
    if op == OP_INFLIGER_DEGATS and nombre is not None and nombre % 10 != 0:
        raise ProgrammeInvalide(
            f"{quoi} : des dégâts se comptent par multiples de 10 (R-10.6), reçu {nombre}."
        )
    if op == OP_POSER_ETAT:
        if etat not in ETATS_SPECIAUX:
            raise ProgrammeInvalide(
                f"{quoi} : « poser_etat » exige un état parmi {sorted(ETATS_SPECIAUX)}."
            )
    elif op == OP_RETIRER_ETAT:
        if etat is not None and etat not in ETATS_SPECIAUX:
            raise ProgrammeInvalide(
                f"{quoi} : état inconnu {etat!r} (les cinq : {sorted(ETATS_SPECIAUX)})."
            )
    elif etat is not None:
        raise ProgrammeInvalide(
            f"{quoi} : « etat » n'a de sens que pour « poser_etat »/« retirer_etat »."
        )

    if op == OP_EMPECHER:
        if verrou not in VERROUS:
            raise ProgrammeInvalide(
                f"{quoi} : « empecher » exige un verrou parmi {sorted(VERROUS)}."
            )
        if portee not in PORTEES_VERROU:
            raise ProgrammeInvalide(
                f"{quoi} : « empecher » exige une portée parmi {sorted(PORTEES_VERROU)}."
            )
    elif verrou is not None or portee is not None:
        raise ProgrammeInvalide(
            f"{quoi} : « verrou »/« portee » n'ont de sens que pour « empecher »."
        )

    if (
        op == OP_MELANGER
        and cible is not None
        and cible.zone
        not in ("pioche", "main", "defausse", ZONE_STADE, "zone_perdue", "recompenses")
    ):
        raise ProgrammeInvalide(
            f"{quoi} : on ne mélange qu'une zone de cartes, pas {cible.zone!r}."
        )

    # « piocher » agit sur UNE pioche : le joueur visé se lit sur ``proprietaire`` (``moi`` par
    # défaut, ``adversaire`` pour « votre adversaire pioche N »). Une autre zone de cible n'a pas de
    # sens — refus strict plutôt qu'un ``proprietaire`` deviné (lot j-cartes-supporters).
    if op == OP_PIOCHER and cible is not None and cible.zone != ZONE_PIOCHE:
        raise ProgrammeInvalide(
            f"{quoi} : « piocher » ne cible qu'une pioche (le joueur visé se lit sur "
            f"« proprietaire »), pas {cible.zone!r}."
        )

    return Instruction(
        op=op,
        cible=cible,
        source=source,
        nombre=nombre,
        etat=etat,
        verrou=verrou,
        portee=portee,
        regle=regle,
    )


def charger_programme(donnees: object) -> Programme:
    """Charge et **valide** un script d'effet. Lève :class:`ProgrammeInvalide` si non conforme.

    C'est la **seule** porte d'entrée d'un script dans le moteur : rien ne s'exécute avant d'être
    passé par ici (critère n°3). La ``version`` est obligatoire et bornée (critère n°4).
    """
    d = _exiger_mapping(donnees, "programme")
    _refuser_cles_parasites(d, _CLES_PROGRAMME, "programme")
    version = d.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ProgrammeInvalide(f"programme : « version » entière obligatoire, reçu {version!r}.")
    if version > DSL_VERSION:
        raise ProgrammeInvalide(
            f"programme : version {version} postérieure à la version lue par l'interprète "
            f"({DSL_VERSION}) — refus (jamais chargé « au mieux »). Mettez l'interprète à jour."
        )
    if version < DSL_VERSION_MIN:
        raise ProgrammeInvalide(
            f"programme : version {version} antérieure au plancher lisible ({DSL_VERSION_MIN})."
        )
    if "effets" not in d:
        raise ProgrammeInvalide("programme : « effets » (liste d'instructions) obligatoire.")
    effets = _charger_instructions(d["effets"], "effets", dans_choix=False)
    cout = _charger_instructions(d.get("cout", []), "cout", dans_choix=False) if "cout" in d else ()
    return Programme(version=version, effets=effets, cout=cout)


__all__ = ["ProgrammeInvalide", "charger_programme"]
