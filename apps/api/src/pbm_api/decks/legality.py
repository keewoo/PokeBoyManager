"""Contrôle de légalité d'un deck — logique pure, sans accès base.

Socle posé par `v7-decks-api` (60 cartes, 4 exemplaires par nom, possession) ; étendu par
`v7-decks-legalite` :
  - chaque constat porte une **sévérité** (`bloquant` / `avertissement`) : seuls les constats
    bloquants rendent le deck illégal, les avertissements informent sans interdire ;
  - **au moins un Pokémon de base** — un deck sans Pokémon de base ne peut pas démarrer une
    partie (bloquant) ;
  - **légalité par format** (Standard / Étendu / Illimité, `pbm_api.decks.formats`) : une carte
    explicitement hors du format choisi est signalée avec son explication (bloquant) ;
  - **contrefaçons exclues** : les exemplaires signalés contrefaçon (`v6-contrefacon`) ne
    comptent pas dans la possession ; leur exclusion est signalée (avertissement) pour expliquer
    un décompte de possession plus bas que le nombre d'exemplaires réellement en collection.

Étendu par `j-effets-couverture-outil` :
  - chaque constat porte une **catégorie** (`possession` / `legalite` / `script`) : le constructeur
    peut ainsi dire, pour chaque carte refusée, *ce qui* la bloque (critère n°1 du lot) ;
  - les **effets non scriptés** (D9) deviennent un constat bloquant explicite, alimenté depuis le
    registre `card_scripts` par l'appelant (le service, qui a la base) et passé ici déjà résolu —
    `evaluate` reste pur : il ne lit aucune base, il reçoit la carte → raison déjà calculée.

Une seule implémentation, exposée telle quelle par l'API et destinée à l'écran (risque du lot :
« la même règle côté serveur et côté écran ») : jamais deux logiques qui divergent. Recalculé à
chaque lecture, aucune légalité n'est mémorisée — une carte vendue ou signalée contrefaçon rend
le deck injouable sans écriture (« revalidation quand la collection change »).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from pbm_api.decks import energy, formats, regles_speciales

DECK_SIZE = 60
MAX_COPIES_PER_NAME = 4

# Sévérités : seul `BLOCKING` retire la légalité ; `WARNING` informe sans interdire.
BLOCKING = "bloquant"
WARNING = "avertissement"

# Catégories d'un constat : ce qui bloque la carte, pour que le constructeur le dise (critère n°1).
CATEGORY_POSSESSION = "possession"  # il manque des exemplaires (ou ils sont contrefaçon)
CATEGORY_LEGALITE = "legalite"  # taille, 4 exemplaires, format, Pokémon de base
CATEGORY_SCRIPT = "script"  # l'effet de la carte n'est pas (encore) scripté (D9)

# Codes de constat (stables, réutilisés par l'écran).
CODE_DECK_SIZE = "deck_size"
CODE_COPY_LIMIT = "copy_limit"
CODE_NOT_OWNED = "not_owned"
CODE_NO_BASIC_POKEMON = "no_basic_pokemon"
CODE_OUT_OF_FORMAT = "out_of_format"
CODE_COUNTERFEIT_EXCLUDED = "counterfeit_excluded"
CODE_UNSUPPORTED_EFFECT = "unsupported_effect"
# Règles de cartes particulières (lot `j-cartes-regles-speciales`, R-2.3/2.4/2.7/2.8, R-15.22).
CODE_ACE_SPEC_LIMIT = "ace_spec_limit"  # R-2.3 — au plus 1 ACE SPEC
CODE_RADIANT_LIMIT = "radiant_limit"  # R-2.4 — au plus 1 Radiant
CODE_PRISM_STAR_LIMIT = "prism_star_limit"  # R-2.7 — au plus 1 Prisme Étoile par nom
CODE_STAR_LIMIT = "star_limit"  # R-2.8 — au plus 1 ★ par deck
CODE_UNKNOWN_RULE_BOX = "unknown_rule_box"  # R-15.22 — Rule Box non classable, refusée

# La catégorie de chaque code — une seule table, pour que tout constat la porte automatiquement.
_CATEGORY_BY_CODE = {
    CODE_NOT_OWNED: CATEGORY_POSSESSION,
    CODE_COUNTERFEIT_EXCLUDED: CATEGORY_POSSESSION,
    CODE_UNSUPPORTED_EFFECT: CATEGORY_SCRIPT,
    CODE_DECK_SIZE: CATEGORY_LEGALITE,
    CODE_COPY_LIMIT: CATEGORY_LEGALITE,
    CODE_NO_BASIC_POKEMON: CATEGORY_LEGALITE,
    CODE_OUT_OF_FORMAT: CATEGORY_LEGALITE,
}

_POKEMON_SUPERTYPES = {"pokemon"}
_BASIC_STAGES = {"base", "basic"}


def category_for(code: str) -> str:
    """La catégorie d'un code (`possession`/`legalite`/`script`) ; `legalite` par défaut."""
    return _CATEGORY_BY_CODE.get(code, CATEGORY_LEGALITE)


def is_basic_pokemon(supertype: str | None, stage: str | None) -> bool:
    """Vrai pour un Pokémon au stade de base (TCGdex `stage="Base"`, en anglais `"Basic"`)."""
    if energy.normalize(supertype) not in _POKEMON_SUPERTYPES:
        return False
    return energy.normalize(stage) in _BASIC_STAGES


@dataclass(frozen=True)
class DeckCardFact:
    """Une entrée de deck enrichie de ce qu'il faut pour juger sa légalité.

    `stage`/`legal_standard`/`legal_expanded` viennent du catalogue ; `counterfeit_owned` est le
    nombre d'exemplaires possédés mais signalés contrefaçon (déjà exclus de `owned`)."""

    card_id: uuid.UUID
    name: str
    supertype: str | None
    energy_type: str | None
    quantity: int
    owned: int
    stage: str | None = None
    legal_standard: bool | None = None
    legal_expanded: bool | None = None
    counterfeit_owned: int = 0
    rule_marker: str | None = None
    prize_marker: str | None = None


@dataclass
class LegalityIssue:
    """Un constat de légalité — bloquant (rend le deck illégal) ou simple avertissement.

    `category` est dérivée du `code` (table :data:`_CATEGORY_BY_CODE`) si elle n'est pas fournie :
    tout constat porte ainsi sa catégorie sans qu'on ait à la répéter à chaque construction."""

    code: str
    message: str
    severity: str = BLOCKING
    card_id: uuid.UUID | None = None
    card_name: str | None = None
    detail: dict | None = None
    category: str = ""

    def __post_init__(self) -> None:
        if not self.category:
            self.category = category_for(self.code)


@dataclass
class CardLegality:
    """Le détail de légalité d'une carte du deck : possession, format, nature (énergie/base)."""

    card_id: uuid.UUID
    name: str
    quantity: int
    is_basic_energy: bool
    is_special_energy: bool
    is_basic_pokemon: bool
    owned: int
    missing: int
    in_collection: bool
    in_format: bool
    counterfeit_excluded: int


@dataclass
class DeckLegality:
    """Le verdict de légalité d'un deck, recalculé à la lecture : légal ou non, et le détail."""

    legal: bool
    card_count: int
    size_ok: bool
    format: str
    format_label: str
    issues: list[LegalityIssue] = field(default_factory=list)
    cards: list[CardLegality] = field(default_factory=list)


def evaluate(
    facts: list[DeckCardFact],
    deck_format: str = formats.DEFAULT_FORMAT,
    unsupported: Mapping[uuid.UUID, str] | None = None,
) -> DeckLegality:
    """Juge la légalité d'un deck à partir des faits fournis : taille, 4 exemplaires par nom,
    possession, Pokémon de base, format, et effets non scriptés — fonction pure, source unique
    côté serveur et écran.

    ``unsupported`` : ``{card_id: raison}`` des cartes dont un effet n'est pas scripté (D9), déjà
    résolu par l'appelant contre le registre `card_scripts` (le service, qui a la base). `evaluate`
    reste pur : il ne lit aucune base, il n'émet un constat `unsupported_effect` que pour les cartes
    **présentes dans ce deck** (intersection avec les faits — la carte d'un autre deck ne fuit pas).
    """
    if not formats.is_valid(deck_format):
        deck_format = formats.DEFAULT_FORMAT
    card_count = sum(f.quantity for f in facts)
    issues: list[LegalityIssue] = []
    cards: list[CardLegality] = []
    has_basic_pokemon = False

    # Détail par carte : possession, format, contrefaçon.
    for f in facts:
        basic_e = energy.is_basic_energy(f.supertype, f.name, f.energy_type)
        special_e = energy.is_special_energy(f.supertype, f.name, f.energy_type)
        basic_p = is_basic_pokemon(f.supertype, f.stage)
        if basic_p:
            has_basic_pokemon = True
        # Énergie de base : fournie, jamais un manque de possession.
        missing = 0 if basic_e else max(0, f.quantity - f.owned)
        in_fmt = formats.card_in_format(
            deck_format,
            is_basic_energy=basic_e,
            legal_standard=f.legal_standard,
            legal_expanded=f.legal_expanded,
        )
        cards.append(
            CardLegality(
                card_id=f.card_id,
                name=f.name,
                quantity=f.quantity,
                is_basic_energy=basic_e,
                is_special_energy=special_e,
                is_basic_pokemon=basic_p,
                owned=f.owned,
                missing=missing,
                in_collection=f.owned > 0,
                in_format=in_fmt,
                counterfeit_excluded=f.counterfeit_owned,
            )
        )
        if missing > 0:
            issues.append(
                LegalityIssue(
                    code=CODE_NOT_OWNED,
                    severity=BLOCKING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"required": f.quantity, "owned": f.owned, "missing": missing},
                    message=(
                        f"Il manque {missing} exemplaire(s) de « {f.name} » dans votre "
                        f"collection ({f.owned} possédé(s), {f.quantity} dans le deck)."
                    ),
                )
            )
        if f.counterfeit_owned > 0:
            issues.append(
                LegalityIssue(
                    code=CODE_COUNTERFEIT_EXCLUDED,
                    severity=WARNING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"counterfeit": f.counterfeit_owned},
                    message=(
                        f"{f.counterfeit_owned} exemplaire(s) de « {f.name} » signalé(s) comme "
                        f"contrefaçon probable : exclus du décompte de possession."
                    ),
                )
            )
        if not in_fmt:
            issues.append(
                LegalityIssue(
                    code=CODE_OUT_OF_FORMAT,
                    severity=BLOCKING,
                    card_id=f.card_id,
                    card_name=f.name,
                    detail={"format": deck_format},
                    message=(
                        f"« {f.name} » n'est pas autorisée en format "
                        f"{formats.label(deck_format)}."
                    ),
                )
            )

    # Règle des 4 exemplaires par NOM (Énergies de base exclues).
    by_name: dict[str, dict] = {}
    for f in facts:
        if energy.is_basic_energy(f.supertype, f.name, f.energy_type):
            continue
        key = energy.normalize(f.name)
        entry = by_name.setdefault(key, {"count": 0, "name": f.name})
        entry["count"] += f.quantity
    for entry in by_name.values():
        if entry["count"] > MAX_COPIES_PER_NAME:
            issues.append(
                LegalityIssue(
                    code=CODE_COPY_LIMIT,
                    severity=BLOCKING,
                    card_name=entry["name"],
                    detail={"count": entry["count"], "limit": MAX_COPIES_PER_NAME},
                    message=(
                        f"{entry['count']} exemplaires de « {entry['name']} » — maximum "
                        f"{MAX_COPIES_PER_NAME} (les Énergies de base ne sont pas limitées)."
                    ),
                )
            )

    # Règles de cartes particulières (R-2.3/2.4/2.7/2.8, R-15.22) — limites PROPRES par catégorie,
    # lues sur les marqueurs STRUCTURÉS du catalogue (jamais le nom, R-13.7 ; voir
    # `pbm_api.decks.regles_speciales`). Une carte à Rule Box non classable est refusée (R-15.22).
    nb_ace_spec = 0
    nb_radiant = 0
    nb_etoile = 0
    prisme_par_nom: dict[str, dict] = {}
    for f in facts:
        cat = regles_speciales.marqueur_special(
            supertype=f.supertype, rule_marker=f.rule_marker, prize_marker=f.prize_marker
        )
        if cat is None:
            continue
        if cat == regles_speciales.RULE_BOX_INCONNU:
            issues.append(
                LegalityIssue(
                    code=CODE_UNKNOWN_RULE_BOX,
                    severity=BLOCKING,
                    card_id=f.card_id,
                    card_name=f.name,
                    message=(
                        f"« {f.name} » porte une règle (Rule Box) que le jeu ne sait pas classer : "
                        "refusée plutôt que jouée avec un nombre de récompenses deviné "
                        "(R-13.4/R-15.22)."
                    ),
                )
            )
            continue
        if cat == regles_speciales.ACE_SPEC:
            nb_ace_spec += f.quantity
        elif cat == regles_speciales.RADIANT:
            nb_radiant += f.quantity
        elif cat == regles_speciales.ETOILE:
            nb_etoile += f.quantity
        elif cat == regles_speciales.PRISME_ETOILE:
            e = prisme_par_nom.setdefault(energy.normalize(f.name), {"count": 0, "name": f.name})
            e["count"] += f.quantity
    if nb_ace_spec > 1:
        issues.append(
            LegalityIssue(
                code=CODE_ACE_SPEC_LIMIT,
                severity=BLOCKING,
                detail={"count": nb_ace_spec, "limit": 1},
                message=f"{nb_ace_spec} cartes ACE SPEC — au plus 1 ACE SPEC par deck (R-2.3).",
            )
        )
    if nb_radiant > 1:
        issues.append(
            LegalityIssue(
                code=CODE_RADIANT_LIMIT,
                severity=BLOCKING,
                detail={"count": nb_radiant, "limit": 1},
                message=(
                    f"{nb_radiant} Pokémon Radiant — au plus 1 Pokémon Radiant par deck (R-2.4)."
                ),
            )
        )
    if nb_etoile > 1:
        issues.append(
            LegalityIssue(
                code=CODE_STAR_LIMIT,
                severity=BLOCKING,
                detail={"count": nb_etoile, "limit": 1},
                message=(
                    f"{nb_etoile} Pokémon ★ — au plus 1 Pokémon ★ par deck, tous noms confondus "
                    "(R-2.8)."
                ),
            )
        )
    for e in prisme_par_nom.values():
        if e["count"] > 1:
            issues.append(
                LegalityIssue(
                    code=CODE_PRISM_STAR_LIMIT,
                    severity=BLOCKING,
                    card_name=e["name"],
                    detail={"count": e["count"], "limit": 1},
                    message=(
                        f"{e['count']} cartes Prisme Étoile « {e['name']} » — au plus 1 Prisme "
                        "Étoile de même nom par deck (R-2.7)."
                    ),
                )
            )

    # Effets non scriptés (D9) : alimenté depuis le registre `card_scripts` par l'appelant. On
    # n'émet que pour les cartes réellement présentes dans ce deck (intersection avec les faits).
    if unsupported:
        by_id = {f.card_id: f for f in facts}
        for card_id, reason in unsupported.items():
            fact = by_id.get(card_id)
            if fact is None:
                continue
            issues.append(
                LegalityIssue(
                    code=CODE_UNSUPPORTED_EFFECT,
                    severity=BLOCKING,
                    card_id=card_id,
                    card_name=fact.name,
                    detail={"reason": reason},
                    message=f"« {fact.name} » : effet pas encore jouable — {reason}",
                )
            )

    # Au moins un Pokémon de base (un deck vide échoue déjà sur la taille : on n'ajoute ce
    # constat que si le deck contient au moins une carte, pour ne pas doubler le bruit).
    if card_count > 0 and not has_basic_pokemon:
        issues.append(
            LegalityIssue(
                code=CODE_NO_BASIC_POKEMON,
                severity=BLOCKING,
                message=(
                    "Un deck doit contenir au moins un Pokémon de base pour pouvoir démarrer "
                    "une partie."
                ),
            )
        )

    # Taille exacte (Énergies de base comprises).
    size_ok = card_count == DECK_SIZE
    if not size_ok:
        if card_count < DECK_SIZE:
            message = (
                f"Il manque {DECK_SIZE - card_count} carte(s) : un deck compte exactement "
                f"{DECK_SIZE} cartes ({card_count} pour l'instant)."
            )
        else:
            message = (
                f"{card_count - DECK_SIZE} carte(s) en trop : un deck compte exactement "
                f"{DECK_SIZE} cartes."
            )
        issues.append(
            LegalityIssue(
                code=CODE_DECK_SIZE,
                severity=BLOCKING,
                detail={"count": card_count, "expected": DECK_SIZE},
                message=message,
            )
        )

    legal = not any(i.severity == BLOCKING for i in issues)
    return DeckLegality(
        legal=legal,
        card_count=card_count,
        size_ok=size_ok,
        format=deck_format,
        format_label=formats.label(deck_format),
        issues=issues,
        cards=cards,
    )
