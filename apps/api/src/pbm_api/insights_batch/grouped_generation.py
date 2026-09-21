"""Génération GROUPÉE : plusieurs cartes d'une même extension en une seule requête.

Diffère de `combined_generation` (une carte par requête, lot `v4-insights-batch`) sur un point :
le contexte partagé de l'extension n'est envoyé **qu'une fois** pour tout le paquet au lieu d'être
répété par carte, ce qui abaisse le coût d'entrée par carte (consigne du lot
`pbm-insights-toutes-cartes` : « groupe les cartes dans une même requête… par paquets d'une même
extension »). La sortie structurée rend un objet par carte, chacun portant le `card_ref` demandé.

⛔ Contrôle anti-mélange (risque nommé de la mission : « une anecdote d'une carte se retrouve sur
une autre ») : `parse_grouped_result` rejette le **paquet entier** si l'ensemble des `card_ref`
rendus ne coïncide pas exactement avec l'ensemble demandé — un `card_ref` manquant, inconnu ou en
double fait échouer tout le paquet plutôt que d'attribuer silencieusement de mauvaises anecdotes.
Un JSON invalide (schéma non respecté, réponse tronquée) est traité de la même façon par l'appelant.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from pbm_api.ai.json_schema import to_strict_schema
from pbm_api.ingame.generation import MAX_RELATED_CARDS
from pbm_api.insights.context import ContextPage
from pbm_api.insights.generation import MAX_ANECDOTES

# Version du prompt/schéma groupé — distincte de `combined_generation.PROMPT_VERSION` ("v1") pour
# que `CardInsight.source_model` distingue une fiche produite en paquet d'une fiche produite carte
# par carte, et rende la régénération traçable.
GROUPED_PROMPT_VERSION = "grp-v1"


# Modèles VOLONTAIREMENT sans borne de longueur/de nombre — décision du lot
# `pbm-insights-toutes-cartes` : les bornes de `insights.generation.AnecdoteItem` (texte ≤ 500) et
# `ingame.generation.InGameStudyExtraction` (champs ≤ 300/400, ≤ 8 cartes associées) sont de toute
# façon RETIRÉES du schéma envoyé à Anthropic (`ai.json_schema` les refuse, 400) : le modèle n'est
# donc pas contraint côté serveur et dépasse parfois la borne (mesuré : `playability_note` > 300).
# Les réappliquer côté client ferait échouer TOUT le paquet (N cartes perdues) pour une note un
# peu longue, alors que `card_insights.in_game_study`/`anecdotes` (TEXT/JSONB) n'ont aucune limite
# de stockage. On accepte donc la longueur telle quelle ; seuls la STRUCTURE et l'anti-mélange
# (`parse_grouped_result`) peuvent rejeter un paquet.
class GroupedAnecdote(BaseModel):
    text: str
    source_url: str


class GroupedGameStudy(BaseModel):
    role: str
    strengths: str
    weaknesses: str
    related_cards: list[str] = Field(default_factory=list)
    playability_note: str


class GroupedCardInsight(BaseModel):
    """Un objet par carte dans la réponse du modèle — mêmes trois parties que
    `combined_generation.CombinedCardInsightExtraction`, plus le `card_ref` de rappel."""

    card_ref: str
    anecdotes_fr: list[GroupedAnecdote]
    anecdotes_en: list[GroupedAnecdote]
    game_study: GroupedGameStudy


class GroupedInsightExtraction(BaseModel):
    cards: list[GroupedCardInsight]


GROUPED_JSON_SCHEMA = to_strict_schema(GroupedInsightExtraction)


@dataclass
class PacketCard:
    """Une carte à inclure dans un paquet, avec son contexte propre déjà collecté (le contexte
    d'extension, lui, est partagé et passé une seule fois à `build_grouped_prompt`)."""

    card_ref: str  # identifiant local du paquet (ex "c1") — recopié à l'identique par le modèle
    card_name: str
    card_pages: list[ContextPage]  # pages wiki propres à la carte, hors contexte d'extension
    legal_standard: bool | None
    legal_expanded: bool | None
    prize_label: str
    attacks: list | None
    abilities: list | None


class PacketMixingError(Exception):
    """L'ensemble des `card_ref` rendus ne coïncide pas exactement avec l'ensemble demandé —
    le paquet entier est rejeté (aucune carte du paquet n'est écrite)."""


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "inconnu"
    return "légale" if value else "non légale"


def allowed_urls_for(set_pages: list[ContextPage], card: PacketCard) -> set[str]:
    """URLs autorisées pour les anecdotes d'UNE carte du paquet : le contexte d'extension partagé
    plus les seules sources propres à cette carte. Sert au filtrage anti-hallucination d'URL
    (`pbm_api.insights.service` fait de même à la demande)."""
    return {page.source_url for page in set_pages} | {page.source_url for page in card.card_pages}


def _render_pages(pages: list[ContextPage]) -> str:
    return "\n\n".join(
        f"Source [{page.source_url}] — {page.title} :\n{page.text}" for page in pages
    )


def build_grouped_prompt(
    *, set_name: str, set_pages: list[ContextPage], cards: list[PacketCard]
) -> str:
    lines = [
        f'Tu rédiges la fiche de PLUSIEURS cartes Pokémon de la même extension "{set_name}", '
        "en une seule réponse structurée. Pour CHAQUE carte, tu produis trois parties : des "
        "anecdotes en français, les mêmes anecdotes en anglais, et une étude d'utilisation en jeu.",
        "",
        "Règles générales strictes :",
        "- Traite chaque carte séparément. N'utilise JAMAIS le contexte ni les faits d'une carte "
        "pour une autre : une anecdote ne parle que de la carte sous laquelle elle est rangée.",
        f"- Rédige au plus {MAX_ANECDOTES} anecdotes courtes par carte et par langue, et une note "
        "de jouabilité brève (deux ou trois phrases).",
        "- Chaque anecdote doit se baser uniquement sur les extraits fournis (contexte d'extension "
        "commun ci-dessous et sources propres à la carte) et son `source_url` doit reprendre "
        "exactement l'une des URLs listées entre crochets. N'invente aucun fait ni aucune URL. "
        "S'il n'y a pas assez de matière sourcée pour une carte, renvoie moins d'anecdotes pour "
        "elle (listes vides acceptées) plutôt que d'en inventer.",
        "- Les anecdotes FR et EN d'une même carte disent la même chose (même nombre, même "
        "`source_url` pour l'anecdote correspondante).",
        "- L'étude en jeu ne s'appuie que sur les données déterministes fournies pour la carte.",
        "- Rends exactement un objet par carte, avec le champ `card_ref` recopié À L'IDENTIQUE "
        'depuis l\'en-tête « CARTE <card_ref> » de la carte. N\'ajoute aucune carte hors de cette '
        "liste, n'en oublie aucune, ne répète aucun `card_ref`.",
        "",
        f'=== CONTEXTE COMMUN DE L\'EXTENSION "{set_name}" (utilisable par toutes les cartes) ===',
    ]
    if set_pages:
        lines.append(_render_pages(set_pages))
    else:
        lines.append("Aucune source d'extension disponible.")

    for card in cards:
        lines += ["", f'=== CARTE {card.card_ref} : "{card.card_name}" ===']
        if card.card_pages:
            lines.append("Sources propres à cette carte :")
            lines.append(_render_pages(card.card_pages))
        else:
            lines.append(
                "Aucune source propre disponible pour cette carte : ses anecdotes peuvent "
                "s'appuyer sur le contexte d'extension commun, ou rester vides."
            )
        lines.append("Données de jeu (catalogue, à ne pas réinventer) :")
        lines.append(f"- Format Standard : {_yes_no(card.legal_standard)}.")
        lines.append(f"- Format Étendu : {_yes_no(card.legal_expanded)}.")
        lines.append(f"- Règle des Prix : {card.prize_label}.")
        if card.attacks:
            lines.append(f"- Attaques : {card.attacks}")
        if card.abilities:
            lines.append(f"- Talents : {card.abilities}")
        lines.append(
            "- Aucune présence en tournoi n'a été relevée pour cette carte : ne prétends pas le "
            "contraire ; indique plutôt si son profil (légalités, règle des Prix, attaques) "
            "explique cette absence."
        )

    lines += [
        "",
        f"Rappel : jusqu'à {MAX_RELATED_CARDS} cartes associées par étude en jeu ; base-toi "
        "uniquement sur ce message, n'invente aucun tournoi, placement, règle ou URL.",
    ]
    return "\n".join(lines)


def parse_grouped_result(
    text: str, requested_refs: list[str]
) -> dict[str, GroupedCardInsight]:
    """Valide le JSON contre `GroupedInsightExtraction` puis vérifie que l'ensemble des `card_ref`
    rendus coïncide EXACTEMENT avec `requested_refs` (aucun manquant, aucun inconnu, aucun doublon).

    Lève `pydantic.ValidationError` si le JSON ne respecte pas le schéma (réponse tronquée
    comprise) et `PacketMixingError` en cas de discordance de `card_ref`. Dans les deux cas
    l'appelant rejette le paquet entier. Renvoie un dict indexé par `card_ref` sinon."""
    extraction = GroupedInsightExtraction.model_validate_json(text)
    returned = [card.card_ref for card in extraction.cards]
    returned_set = set(returned)
    if len(returned) != len(returned_set):
        duplicates = sorted({ref for ref in returned if returned.count(ref) > 1})
        raise PacketMixingError(f"card_ref en double dans la réponse : {duplicates}")
    requested_set = set(requested_refs)
    if returned_set != requested_set:
        missing = sorted(requested_set - returned_set)
        unknown = sorted(returned_set - requested_set)
        raise PacketMixingError(
            f"card_ref demandés/rendus discordants — manquants={missing} inconnus={unknown}"
        )
    return {card.card_ref: card for card in extraction.cards}


__all__ = [
    "GROUPED_JSON_SCHEMA",
    "GROUPED_PROMPT_VERSION",
    "GroupedAnecdote",
    "GroupedCardInsight",
    "GroupedGameStudy",
    "GroupedInsightExtraction",
    "PacketCard",
    "PacketMixingError",
    "ValidationError",
    "allowed_urls_for",
    "build_grouped_prompt",
    "parse_grouped_result",
]
