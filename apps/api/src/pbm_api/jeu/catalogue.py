"""Adaptateur **catalogue → moteur** : une carte du catalogue devient une ``DefinitionCarte``.

Le moteur de jeu (``pbm_game``) est **pur** : il ne lit jamais la base. Le service extrait d'une
carte du catalogue (modèle ``pbm_api.models.catalog.Card`` ou tout objet portant les mêmes
attributs) les caractéristiques que le moteur attend et les assemble en
:class:`~pbm_game.cartes.modele.DefinitionCarte`. La validation de cette dataclass **mord** ici :
un marqueur de règle inconnu, un stade absent, des PV ou un coût de retraite manquants **bloquent**
la carte (``ValueError``) — jamais devinés (D9, R-13.4/R-15.22, et le risque nommé du lot : « les
champs manquants doivent bloquer la carte, pas être devinés »).

**Le marqueur de règle ne se lit pas sur le nom** : on prend ``card.prize_marker``, déjà normalisé
à l'import (``pbm_api.catalog.prize_marker``) vers le vocabulaire du moteur
(``pbm_game.combat.fin.MARQUEUR_RECOMPENSES``). Un ``prize_marker`` ``None`` (carte hors Pokémon)
ou :data:`~pbm_api.catalog.prize_marker.MARQUEUR_INCONNU` fait refuser la carte.

**Seules les attaques à dégâts secs sont jouables** au jalon J1 : une attaque dont le texte porte
un effet, ou dont les dégâts sont variables (« 20× », « 20+ »), est chargée **fidèlement** mais
marquée (``AttaqueDef.effet`` non vide) — son script arrive avec ``j-cartes-attaques-effets`` (D9).

⚠️ Le catalogue de référence actuel **ne porte ni la chaîne d'évolution (``evolves_from``) ni, sur
la base de référence de chimera, la colonne ``stage``** : une carte d'évolution sans ces champs est
donc **bloquée** par cet adaptateur (c'est le comportement voulu — on ne devine pas). Alimenter ces
champs est un chantier de catalogue à part (voir le compte rendu du lot).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from pbm_game.cartes import AttaqueDef, DefinitionCarte
from pbm_game.cartes.energie import DefinitionEnergie
from pbm_game.combat.modele import (
    FAIBLESSE_FACTEUR_DEFAUT,
    RESISTANCE_REDUCTION_DEFAUT,
    CoutAttaque,
    Faiblesse,
    Resistance,
)

from pbm_api.catalog.prize_marker import MARQUEUR_INCONNU, POKEMON_SUPERTYPES
from pbm_api.decks.energy import is_basic_energy, is_energy, normalize

#: Correspondance des stades TCGdex (localisés) vers le vocabulaire du moteur (R-7). Un stade
#: absent de cette table **bloque** la carte (on ne devine pas le stade d'un Pokémon).
_STADES: dict[str, str] = {
    "base": "base",
    "basic": "base",
    "niveau 1": "stade1",
    "niveau 2": "stade2",
    "stage 1": "stade1",
    "stage 2": "stade2",
    "stage1": "stade1",
    "stage2": "stade2",
}

#: Symboles d'énergie **incolore** du coût d'attaque (TCGdex, FR et EN).
_INCOLORE = frozenset({"incolore", "colorless"})


def _ref(card: object) -> str:
    for attr in ("tcgdex_id", "ptcg_id"):
        valeur = getattr(card, attr, None)
        if isinstance(valeur, str) and valeur:
            return valeur
    ident = getattr(card, "id", None)
    if ident is not None:
        return str(ident)
    raise ValueError("Carte sans référence stable (ni tcgdex_id, ni ptcg_id, ni id).")


def _stade(stage: object, nom: str) -> str:
    if stage is None:
        raise ValueError(
            f"« {nom} » : stade absent du catalogue — carte bloquée, jamais deviné (R-7)."
        )
    cle = str(stage).strip().lower()
    if cle not in _STADES:
        raise ValueError(f"« {nom} » : stade « {stage} » non reconnu — carte bloquée (R-7).")
    return _STADES[cle]


def _premier_entier(valeur: object, defaut: int) -> int:
    if valeur is None:
        return defaut
    m = re.search(r"(\d+)", str(valeur))
    return int(m.group(1)) if m else defaut


def _faiblesse(brut: object) -> Faiblesse | None:
    if not brut or not isinstance(brut, (list, tuple)):
        return None
    premier = brut[0]
    if not isinstance(premier, Mapping):
        return None
    type_ = premier.get("type")
    if not type_:
        return None
    return Faiblesse(
        type=str(type_).strip().lower(),
        facteur=_premier_entier(premier.get("value"), FAIBLESSE_FACTEUR_DEFAUT),
    )


def _resistance(brut: object) -> Resistance | None:
    if not brut or not isinstance(brut, (list, tuple)):
        return None
    premier = brut[0]
    if not isinstance(premier, Mapping):
        return None
    type_ = premier.get("type")
    if not type_:
        return None
    return Resistance(
        type=str(type_).strip().lower(),
        reduction=_premier_entier(premier.get("value"), RESISTANCE_REDUCTION_DEFAUT),
    )


def _cout(brut: object) -> CoutAttaque:
    """Le coût d'une attaque depuis la liste de symboles TCGdex (``["Eau", "Incolore"]``)."""
    if not brut or not isinstance(brut, (list, tuple)):
        return CoutAttaque()
    types: dict[str, int] = {}
    incolore = 0
    for symbole in brut:
        s = str(symbole).strip().lower()
        if not s:
            continue
        if s in _INCOLORE:
            incolore += 1
        else:
            types[s] = types.get(s, 0) + 1
    return CoutAttaque(types=types, incolore=incolore)


def _degats_et_effet(damage: object, effet_texte: str) -> tuple[int, str]:
    """Sépare les **dégâts secs** d'un éventuel **effet** (texte, ou dégâts variables « × »/« + »).

    Une attaque à dégâts secs rend ``(n, "")`` ; une attaque à effet ou à dégâts variables rend
    ``(0, texte)`` — jamais résolue au jalon J1 (D9), mais chargée fidèlement.
    """
    texte = (effet_texte or "").strip()
    if damage is None:
        return 0, texte
    s = str(damage).strip()
    if not s:
        return 0, texte
    m = re.match(r"(\d+)", s)
    if not m:
        return 0, texte or s
    n = int(m.group(1))
    reste = s[m.end() :].strip()
    if reste:
        # Dégâts variables (« 20× », « 20+ ») : non secs → portés comme un effet (D9).
        return 0, texte or f"dégâts variables ({s})"
    return n, texte


def _attaque(brut: object) -> AttaqueDef:
    if not isinstance(brut, Mapping):
        raise ValueError(f"Attaque mal formée dans le catalogue : {brut!r} (mapping attendu).")
    nom = brut.get("name") or brut.get("nom") or ""
    effet_texte = brut.get("effect") or brut.get("text") or brut.get("effet") or ""
    degats, effet = _degats_et_effet(brut.get("damage", brut.get("degats")), effet_texte)
    return AttaqueDef(
        nom=nom, cout=_cout(brut.get("cost") or brut.get("cout")), degats=degats, effet=effet
    )


def definition_depuis_card(card: object, *, evolue_depuis: str | None = None) -> DefinitionCarte:
    """Construit un :class:`DefinitionCarte` depuis une carte du catalogue, ou **bloque** la carte.

    ``card`` porte les attributs du modèle ``Card`` (``name``, ``hp``, ``energy_type``,
    ``element_type``, ``stage``, ``attacks``, ``weaknesses``, ``resistances``, ``retreat_cost``,
    ``prize_marker``, ``supertype``…). ``evolue_depuis`` nomme le prédécesseur d'une évolution quand
    le catalogue ne le porte pas encore (sinon il est lu sur ``card.evolves_from`` s'il existe) ;
    pour une base il reste ``None``. Lève ``ValueError`` — jamais de valeur devinée — sur toute
    donnée manquante ou incohérente (marqueur inconnu, stade absent, PV/coût de retraite manquants).
    """
    nom = getattr(card, "name", None)
    supertype = getattr(card, "supertype", None)
    if supertype not in POKEMON_SUPERTYPES:
        raise ValueError(
            f"« {nom} » n'est pas un Pokémon (supertype {supertype!r}) : le jeu ne charge ici que "
            "des cartes Pokémon."
        )
    marqueur = getattr(card, "prize_marker", None)
    if not marqueur or marqueur == MARQUEUR_INCONNU:
        raise ValueError(
            f"« {nom} » : marqueur de règle inconnu ({marqueur!r}) — carte refusée, jamais jouée "
            "avec un nombre de récompenses deviné (R-13.4/R-15.22)."
        )
    retreat = getattr(card, "retreat_cost", None)
    if retreat is None:
        raise ValueError(
            f"« {nom} » : coût de retraite absent — carte bloquée, jamais deviné (R-8.2)."
        )
    evo = evolue_depuis if evolue_depuis is not None else getattr(card, "evolves_from", None)
    return DefinitionCarte(
        ref=_ref(card),
        nom=nom or "",
        stade=_stade(getattr(card, "stage", None), nom or "?"),
        pv=getattr(card, "hp", None),
        type=(getattr(card, "energy_type", None) or getattr(card, "element_type", None) or ""),
        marqueur=marqueur,
        evolue_depuis=evo,
        faiblesse=_faiblesse(getattr(card, "weaknesses", None)),
        resistance=_resistance(getattr(card, "resistances", None)),
        cout_retraite=retreat,
        attaques=tuple(_attaque(a) for a in (getattr(card, "attacks", None) or [])),
    )


def _type_energie_depuis_nom(nom: str | None) -> str:
    """Déduit le type d'une Énergie de base de son **nom** quand ``element_type`` manque.

    « Énergie Feu » → ``feu`` ; « Water Energy » → ``water``. On retire le préfixe/suffixe
    « énergie »/« energy » et on garde le reste (vocabulaire **brut**, comme les coûts d'attaque :
    ``_cout`` met les symboles en minuscules sans les normaliser — fournitures et coûts doivent
    parler la même langue). Vide si indéterminé (D9 : jamais deviné).
    """
    n = normalize(nom)
    for prefixe in ("energie ", "energy "):
        if n.startswith(prefixe):
            n = n[len(prefixe):]
    for suffixe in (" energie", " energy"):
        if n.endswith(suffixe):
            n = n[: -len(suffixe)]
    return n.strip()


def definition_energie_depuis_card(card: object) -> DefinitionEnergie:
    """Construit une :class:`DefinitionEnergie` depuis une carte Énergie **de base**, ou **bloque**.

    Au jalon J1, seules les Énergies **de base** sont jouables : une Énergie **spéciale** porte un
    effet non scripté (D9) et est refusée — jamais jouée de travers. La **fourniture** d'une énergie
    de base est son type (``{type: 1}``), dans le **même vocabulaire brut** que les coûts d'attaque
    (``element_type`` en minuscules, ou déduit du nom à défaut). Lève ``ValueError`` si la carte
    n'est pas une Énergie de base ou si son type reste indéterminé.
    """
    nom = getattr(card, "name", None)
    supertype = getattr(card, "supertype", None)
    energy_type = getattr(card, "energy_type", None)
    if not is_energy(supertype):
        raise ValueError(f"« {nom} » n'est pas une carte Énergie (supertype {supertype!r}).")
    if not is_basic_energy(supertype, nom, energy_type):
        raise ValueError(
            f"« {nom} » : Énergie spéciale non scriptée au jalon J1 — un effet non implémenté "
            "n'est jamais approximé (D9)."
        )
    element = getattr(card, "element_type", None)
    type_ = str(element).strip().lower() if element else _type_energie_depuis_nom(nom)
    if not type_:
        raise ValueError(
            f"« {nom} » : type d'Énergie de base indéterminé — carte bloquée, jamais deviné (D9)."
        )
    return DefinitionEnergie(ref=_ref(card), nom=nom or "", fournit={type_: 1})


__all__ = ["definition_depuis_card", "definition_energie_depuis_card"]
