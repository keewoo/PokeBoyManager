"""Génération GROUPÉE à contenu RÉDUIT — lot `pbm-insights-ciblage-large`.

Décisions de JF (21/09), après la mesure du lot `pbm-insights-toutes-cartes` (5 anecdotes FR +
5 EN + étude en jeu ≈ 72 € pour tout le catalogue, au-dessus du plafond) :

1. Plafond relevé à 50 € (arrêt net au-delà).
2. Contenu réduit : **2 anecdotes, en français seulement**, **plus les règles de jeu** (comment
   la carte se joue : coût et effet de ses attaques, talent, règle ex/V/VMAX, rôle typique,
   formats où elle est légale). Plus d'anglais, plus de cinq anecdotes, plus d'« étude » libre.
3. Ciblage large : viser 80 % des cartes (voir `scripts/generate_large_insights.py` pour l'ordre
   de priorité).

Diffère de `grouped_generation` (lot précédent) sur le seul contenu : deux anecdotes FR au lieu
de cinq FR + cinq EN, et un champ `game_rules` (texte) au lieu de la structure `game_study`. Le
groupage par extension (contexte partagé envoyé une seule fois par paquet) et le contrôle
anti-mélange par `card_ref` sont repris à l'identique — c'est ce qui a fait ses preuves à la
mesure (25 cartes/requête : le moins cher, le moins d'échecs).

⛔ Anti-mélange (risque nommé : « une anecdote d'une carte se retrouve sur une autre ») :
`parse_large_result` rejette le **paquet entier** si l'ensemble des `card_ref` rendus ne coïncide
pas exactement avec l'ensemble demandé. Un JSON invalide est traité de la même façon par
l'appelant. Les règles de jeu, elles, viennent du **catalogue** (attaques, coûts, talents,
légalités, règle des Prix) : le modèle les met en forme, il ne les invente pas.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from pbm_api.ai.json_schema import to_strict_schema
from pbm_api.insights.context import ContextPage

# Version du prompt/schéma — encodée dans `CardInsight.source_model`/`game_study_source_model`
# (`f"anthropic:{model}:batch:{LARGE_PROMPT_VERSION}"`) pour l'import idempotent : une carte déjà
# couverte par la version courante n'est plus candidate ; changer cette version rend toutes les
# fiches candidates au prochain passage. Distincte de `combined_generation.PROMPT_VERSION` ("v1")
# et de `grouped_generation.GROUPED_PROMPT_VERSION` ("grp-v1").
LARGE_PROMPT_VERSION = "large-v1"

# Deux anecdotes maximum par carte (décision de JF). Le schéma envoyé à Anthropic ne PORTE pas
# cette borne (`ai.json_schema` retire les contraintes de longueur, 400 sinon) : elle est donc
# répétée dans le prompt ET ré-appliquée à l'écriture (`take` des deux premières sourcées).
MAX_ANECDOTES = 2


class LargeAnecdote(BaseModel):
    text: str
    source_url: str


class LargeCardInsight(BaseModel):
    """Un objet par carte : `card_ref` de rappel, anecdotes FR sourcées, règles de jeu."""

    card_ref: str
    anecdotes: list[LargeAnecdote]
    game_rules: str


class LargeInsightExtraction(BaseModel):
    cards: list[LargeCardInsight]


LARGE_JSON_SCHEMA = to_strict_schema(LargeInsightExtraction)


@dataclass
class PacketCard:
    """Une carte à inclure dans un paquet. Le contexte d'extension est partagé (passé une seule
    fois à `build_large_prompt`) ; le contexte propre à la carte et ses données de jeu sont ici."""

    card_ref: str  # identifiant local du paquet (ex "c1") — recopié à l'identique par le modèle
    card_name: str
    card_pages: list[ContextPage]  # pages wiki propres à la carte, hors contexte d'extension
    supertype: str | None
    legal_standard: bool | None
    legal_expanded: bool | None
    prize_label: str
    rule_marker: str | None
    hp: int | None
    retreat_cost: int | None
    attacks: list | None
    abilities: list | None
    weaknesses: list | None
    resistances: list | None


class PacketMixingError(Exception):
    """L'ensemble des `card_ref` rendus ne coïncide pas exactement avec l'ensemble demandé —
    le paquet entier est rejeté (aucune carte du paquet n'est écrite)."""


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "inconnu"
    return "légale" if value else "non légale"


def allowed_urls_for(set_pages: list[ContextPage], card: PacketCard) -> set[str]:
    """URLs autorisées pour les anecdotes d'UNE carte : le contexte d'extension partagé plus les
    seules sources propres à cette carte. Sert au filtrage anti-hallucination d'URL."""
    return {page.source_url for page in set_pages} | {page.source_url for page in card.card_pages}


def _render_pages(pages: list[ContextPage]) -> str:
    return "\n\n".join(
        f"Source [{page.source_url}] — {page.title} :\n{page.text}" for page in pages
    )


def _render_game_data(card: PacketCard) -> list[str]:
    """Données de jeu déterministes du catalogue à mettre en forme — jamais à réinventer."""
    lines = [
        "Données de jeu (catalogue TCGdex, à mettre en forme SANS rien inventer ni ajouter) :",
        f"- Catégorie : {card.supertype or 'inconnue'}.",
        f"- Format Standard : {_yes_no(card.legal_standard)} ; "
        f"Format Étendu : {_yes_no(card.legal_expanded)}.",
        f"- Règle des Prix : {card.prize_label}.",
    ]
    if card.rule_marker:
        lines.append(f"- Type de carte spécial : {card.rule_marker}.")
    if card.hp is not None:
        lines.append(f"- PV : {card.hp}.")
    if card.retreat_cost is not None:
        lines.append(f"- Coût de retraite : {card.retreat_cost}.")
    if card.attacks:
        lines.append(f"- Attaques (nom, coût en énergies, dégâts, effet) : {card.attacks}")
    if card.abilities:
        lines.append(f"- Talents : {card.abilities}")
    if card.weaknesses:
        lines.append(f"- Faiblesses : {card.weaknesses}")
    if card.resistances:
        lines.append(f"- Résistances : {card.resistances}")
    return lines


def build_large_prompt(
    *, set_name: str, set_pages: list[ContextPage], cards: list[PacketCard]
) -> str:
    lines = [
        f'Tu rédiges la fiche de PLUSIEURS cartes Pokémon de la même extension "{set_name}", en '
        "une seule réponse structurée. Pour CHAQUE carte, tu produis DEUX parties : au plus deux "
        "anecdotes en français, et les règles de jeu (comment la carte se joue).",
        "",
        "Règles générales strictes :",
        "- Traite chaque carte séparément. N'utilise JAMAIS le contexte ni les faits d'une carte "
        "pour une autre : une anecdote ne parle que de la carte sous laquelle elle est rangée.",
        "- Rends exactement un objet par carte, avec le champ `card_ref` recopié À L'IDENTIQUE "
        "depuis l'en-tête « CARTE <card_ref> ». Le `card_ref` est le CODE COURT (par exemple "
        "`c1`, `c2`), JAMAIS le nom de la carte. N'ajoute aucune carte hors de cette liste, "
        "n'en oublie aucune, ne répète aucun `card_ref`.",
        "",
        "=== Partie 1 — anecdotes (français, au plus DEUX par carte) ===",
        f"- Rédige AU PLUS {MAX_ANECDOTES} anecdotes courtes (une ou deux phrases) par carte : "
        "illustrateur, réédition, événement qui a fait varier sa cote, ou autre fait marquant.",
        "- Chaque anecdote doit se baser uniquement sur les extraits fournis (contexte "
        "d'extension commun ci-dessous et sources propres à la carte) et son `source_url` doit "
        "reprendre EXACTEMENT l'une des URLs listées entre crochets. N'invente aucun fait ni "
        "aucune URL. S'il n'y a pas assez de matière sourcée pour une carte, renvoie moins "
        "d'anecdotes (liste vide acceptée) plutôt que d'en inventer.",
        "",
        "=== Partie 2 — règles de jeu (`game_rules`, texte français) ===",
        "- Décris en quelques phrases comment la carte se joue, en t'appuyant UNIQUEMENT sur les "
        "données de jeu déterministes fournies pour chaque carte ci-dessous : coût en énergies et "
        "effet de ses attaques, talent éventuel, règle des Prix (ex/V/VMAX…), rôle typique dans "
        "un deck, et formats où elle est légale (Standard / Étendu).",
        "- N'invente aucune attaque, aucun coût, aucun effet, aucune légalité, aucun tournoi : "
        "reformule seulement les données fournies en français clair. Si une donnée manque "
        "(attaques inconnues, par exemple), ne la mentionne pas plutôt que de la deviner.",
        "",
        f'=== CONTEXTE COMMUN DE L\'EXTENSION "{set_name}" (pour les anecdotes) ===',
    ]
    if set_pages:
        lines.append(_render_pages(set_pages))
    else:
        lines.append("Aucune source d'extension disponible.")

    for card in cards:
        lines += ["", f'=== CARTE {card.card_ref} : "{card.card_name}" ===']
        if card.card_pages:
            lines.append("Sources propres à cette carte (pour les anecdotes) :")
            lines.append(_render_pages(card.card_pages))
        else:
            lines.append(
                "Aucune source propre disponible : ses anecdotes peuvent s'appuyer sur le "
                "contexte d'extension commun, ou rester vides."
            )
        lines += _render_game_data(card)

    return "\n".join(lines)


def parse_large_result(
    text: str,
    requested_refs: list[str],
    card_names_by_ref: dict[str, str] | None = None,
) -> dict[str, LargeCardInsight]:
    """Valide le JSON contre `LargeInsightExtraction` puis vérifie que l'ensemble des `card_ref`
    rendus coïncide EXACTEMENT avec `requested_refs` (aucun manquant, inconnu ni doublon).

    Tolérance de libellé (`card_names_by_ref`, ref→nom) : le modèle renvoie parfois le NOM de la
    carte en `card_ref` au lieu du code court `cN` demandé — observé sur les paquets courts (cartes
    rares/nommées : « Dracaufeu GX », « M-Rayquaza EX »…). Un tel libellé est remappé vers son `cN`
    UNIQUEMENT si ce nom est unique dans le paquet (sinon ambigu → laissé en discordance, rejeté).
    La BIJECTION exacte entre cartes demandées et objets rendus — le vrai garde-fou anti-mélange :
    aucune carte perdue, ajoutée ni dupliquée — est préservée APRÈS remappage.

    Lève `pydantic.ValidationError` (JSON hors schéma, réponse tronquée) ou `PacketMixingError`
    (discordance de `card_ref`) : dans les deux cas l'appelant rejette le paquet entier."""
    extraction = LargeInsightExtraction.model_validate_json(text)
    requested_set = set(requested_refs)

    # Table nom→ref, restreinte aux noms UNIQUES dans le paquet (un nom partagé par deux cartes
    # serait ambigu : on ne remappe pas, la discordance sera signalée comme d'habitude).
    name_to_ref: dict[str, str] = {}
    if card_names_by_ref:
        counts: dict[str, int] = {}
        for name in card_names_by_ref.values():
            counts[name] = counts.get(name, 0) + 1
        name_to_ref = {
            name: ref for ref, name in card_names_by_ref.items() if counts[name] == 1
        }

    normalized: list[tuple[str, LargeCardInsight]] = []
    for card in extraction.cards:
        ref = card.card_ref
        if ref not in requested_set and ref in name_to_ref:
            ref = name_to_ref[ref]  # le modèle a rendu le nom au lieu du code court
        normalized.append((ref, card))

    returned = [ref for ref, _ in normalized]
    returned_set = set(returned)
    if len(returned) != len(returned_set):
        duplicates = sorted({ref for ref in returned if returned.count(ref) > 1})
        raise PacketMixingError(f"card_ref en double dans la réponse : {duplicates}")
    if returned_set != requested_set:
        missing = sorted(requested_set - returned_set)
        unknown = sorted(returned_set - requested_set)
        raise PacketMixingError(
            f"card_ref demandés/rendus discordants — manquants={missing} inconnus={unknown}"
        )
    return {ref: card for ref, card in normalized}


# --------------------------------------------------------------------------- variante RÈGLES SEULES
#
# Lot `pbm-fiches-reste` (22/09) : les 4 434 cartes sans fiche que le ciblage 80 % avait laissées
# de côté (surtout Communes/Peu communes/Rares) sont couvertes SANS anecdotes, avec UNIQUEMENT les
# règles de jeu. Décision de JF : « le modèle met en forme, il n'invente pas » — exactement la
# partie 2 du prompt groupé, mais isolée. Conséquence directe et voulue : AUCUNE source wiki n'est
# récupérée (c'est ce qui coûtait ≈1 750 jetons d'entrée/carte au lot précédent). Le champ
# `anecdotes` de la fiche reste donc vide (`[]`, cache négatif frais) — l'onglet « En jeu » se lit
# sur `in_game_study`, sans appel IA. Le contrôle anti-mélange par `card_ref` est repris à
# l'identique (`parse_rules_only_result`), seul le contenu par carte change (plus d'anecdotes).

# Version distincte de `LARGE_PROMPT_VERSION` ("large-v1") : une carte déjà couverte par ce lot
# n'est plus candidate, une évolution du prompt règles-seules la rendrait candidate à nouveau.
RULES_ONLY_PROMPT_VERSION = "rules-v1"


class RulesOnlyCardInsight(BaseModel):
    """Un objet par carte : `card_ref` de rappel et les seules règles de jeu (pas d'anecdotes)."""

    card_ref: str
    game_rules: str


class RulesOnlyExtraction(BaseModel):
    cards: list[RulesOnlyCardInsight]


RULES_ONLY_JSON_SCHEMA = to_strict_schema(RulesOnlyExtraction)


def build_rules_only_prompt(*, set_name: str, cards: list[PacketCard]) -> str:
    """Prompt règles-seules : uniquement les données de jeu déterministes du catalogue, mises en
    forme en français clair. Pas de contexte wiki, pas d'anecdotes — le modèle reformule, il
    n'invente rien (ni attaque, ni coût, ni légalité, ni tournoi)."""
    lines = [
        f'Tu rédiges les RÈGLES DE JEU de PLUSIEURS cartes Pokémon de l\'extension "{set_name}", '
        "en une seule réponse structurée. Pour CHAQUE carte, tu produis un seul texte français : "
        "comment la carte se joue.",
        "",
        "Règles générales strictes :",
        "- Traite chaque carte séparément. N'utilise JAMAIS les données d'une carte pour une "
        "autre.",
        "- Rends exactement un objet par carte, avec le champ `card_ref` recopié À L'IDENTIQUE "
        "depuis l'en-tête « CARTE <card_ref> ». Le `card_ref` est le CODE COURT (par exemple "
        "`c1`, `c2`), JAMAIS le nom de la carte. N'ajoute aucune carte hors de cette liste, "
        "n'en oublie aucune, ne répète aucun `card_ref`.",
        "",
        "=== `game_rules` (texte français, par carte) ===",
        "- Décris en quelques phrases comment la carte se joue, en t'appuyant UNIQUEMENT sur les "
        "données de jeu déterministes fournies pour chaque carte ci-dessous : coût en énergies et "
        "effet de ses attaques, talent éventuel, faiblesse, résistance, coût de retraite, règle "
        "des Prix (ex/V/VMAX/GX…), rôle typique dans un deck (une phrase), et formats où elle est "
        "légale (Standard / Étendu).",
        "- Pour un Dresseur ou une Énergie : dis ce que la carte fait, quand la jouer et ses "
        "limites (un Supporter par tour, un Outil par Pokémon…), à partir des seules données "
        "fournies.",
        "- N'invente aucune attaque, aucun coût, aucun effet, aucune légalité, aucun tournoi : "
        "reformule seulement les données fournies. Si une donnée manque, ne la mentionne pas "
        "plutôt que de la deviner.",
    ]
    for card in cards:
        lines += ["", f'=== CARTE {card.card_ref} : "{card.card_name}" ===']
        lines += _render_game_data(card)
    return "\n".join(lines)


def parse_rules_only_result(
    text: str,
    requested_refs: list[str],
    card_names_by_ref: dict[str, str] | None = None,
) -> dict[str, RulesOnlyCardInsight]:
    """Comme `parse_large_result` (même garde-fou anti-mélange : bijection exacte entre cartes
    demandées et objets rendus, avec la même tolérance nom→ref sur les noms uniques du paquet),
    mais pour le schéma règles-seules. Lève `ValidationError` (JSON hors schéma / réponse tronquée)
    ou `PacketMixingError` (discordance de `card_ref`) : l'appelant rejette alors le
    paquet entier."""
    extraction = RulesOnlyExtraction.model_validate_json(text)
    requested_set = set(requested_refs)

    name_to_ref: dict[str, str] = {}
    if card_names_by_ref:
        counts: dict[str, int] = {}
        for name in card_names_by_ref.values():
            counts[name] = counts.get(name, 0) + 1
        name_to_ref = {
            name: ref for ref, name in card_names_by_ref.items() if counts[name] == 1
        }

    normalized: list[tuple[str, RulesOnlyCardInsight]] = []
    for card in extraction.cards:
        ref = card.card_ref
        if ref not in requested_set and ref in name_to_ref:
            ref = name_to_ref[ref]
        normalized.append((ref, card))

    returned = [ref for ref, _ in normalized]
    returned_set = set(returned)
    if len(returned) != len(returned_set):
        duplicates = sorted({ref for ref in returned if returned.count(ref) > 1})
        raise PacketMixingError(f"card_ref en double dans la réponse : {duplicates}")
    if returned_set != requested_set:
        missing = sorted(requested_set - returned_set)
        unknown = sorted(returned_set - requested_set)
        raise PacketMixingError(
            f"card_ref demandés/rendus discordants — manquants={missing} inconnus={unknown}"
        )
    return {ref: card for ref, card in normalized}


__all__ = [
    "LARGE_JSON_SCHEMA",
    "LARGE_PROMPT_VERSION",
    "MAX_ANECDOTES",
    "RULES_ONLY_JSON_SCHEMA",
    "RULES_ONLY_PROMPT_VERSION",
    "LargeAnecdote",
    "LargeCardInsight",
    "LargeInsightExtraction",
    "RulesOnlyCardInsight",
    "RulesOnlyExtraction",
    "PacketCard",
    "PacketMixingError",
    "ValidationError",
    "allowed_urls_for",
    "build_large_prompt",
    "build_rules_only_prompt",
    "parse_large_result",
    "parse_rules_only_result",
]
