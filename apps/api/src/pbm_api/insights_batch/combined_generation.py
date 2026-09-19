"""Schéma et prompt de l'appel unique par carte — mission point 1 : « un appel qui rend
ensemble anecdotes sourcées FR + EN, synthèse d'usage en jeu et note de jouabilité ».

Réutilise les briques déjà écrites et testées par `v4-anecdotes`
(`pbm_api.insights.context`/`generation`) et `v4-jeu` (`pbm_api.ingame.generation`/`rules`) —
seul le prompt qui les assemble est nouveau, avec les mêmes garde-fous anti-hallucination : les
anecdotes ne doivent citer qu'une des URLs de contexte fournies, l'étude en jeu ne doit
s'appuyer que sur les données déterministes du catalogue et les tournois déjà relevés.
"""

from pydantic import BaseModel, Field

from pbm_api.ai.json_schema import to_strict_schema
from pbm_api.ingame.generation import MAX_RELATED_CARDS, InGameStudyExtraction
from pbm_api.insights.context import ContextPage
from pbm_api.insights.generation import MAX_ANECDOTES, AnecdoteItem

# Version du prompt combiné — change à chaque évolution de `build_combined_prompt`/du schéma
# ci-dessous, encodée dans `CardInsight.source_model`/`game_study_source_model`
# (`f"anthropic:{model}:batch:{PROMPT_VERSION}"`, voir `runner.py`) pour l'import idempotent :
# une carte déjà couverte par une version antérieure du prompt redevient candidate au prochain
# passage, une carte déjà couverte par la version courante ne l'est plus.
PROMPT_VERSION = "v1"


class CombinedCardInsightExtraction(BaseModel):
    anecdotes_fr: list[AnecdoteItem] = Field(max_length=MAX_ANECDOTES)
    anecdotes_en: list[AnecdoteItem] = Field(max_length=MAX_ANECDOTES)
    game_study: InGameStudyExtraction


COMBINED_JSON_SCHEMA = to_strict_schema(CombinedCardInsightExtraction)


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "inconnu"
    return "légale" if value else "non légale"


def build_combined_prompt(
    *,
    card_name: str,
    set_name: str,
    context_pages: list[ContextPage],
    legal_standard: bool | None,
    legal_expanded: bool | None,
    prize_label: str,
    attacks: list | None,
    abilities: list | None,
    tournament_decks: list[dict] | None,
) -> str:
    lines = [
        f'Tu rédiges la fiche de la carte Pokémon "{card_name}" (extension "{set_name}") en '
        "une seule réponse structurée, avec trois parties : des anecdotes en français, les "
        "mêmes anecdotes en anglais, et une étude d'utilisation en jeu.",
        "",
        "=== Anecdotes (FR et EN) ===",
        "Rédige trois à cinq anecdotes courtes (une ou deux phrases chacune) en français dans "
        '"anecdotes_fr" et leur équivalent en anglais dans "anecdotes_en" (même contenu, même '
        "nombre d'anecdotes, un `source_url` identique pour la même anecdote dans les deux "
        "langues) : illustrateur, réédition, événement qui a fait varier sa cote, ou autre fait "
        "marquant.",
        "Règle stricte : chaque anecdote doit se baser uniquement sur les extraits ci-dessous, "
        "et son `source_url` doit reprendre exactement l'une des URLs listées entre crochets. "
        "N'invente aucun fait absent de ces extraits ; s'il n'y a pas assez de matière pour "
        "trois anecdotes sourcées, renvoies-en moins plutôt que d'en inventer (listes vides "
        "acceptées).",
        "",
    ]
    if context_pages:
        sources = "\n\n".join(
            f"Source [{page.source_url}] — {page.title} :\n{page.text}" for page in context_pages
        )
        lines.append(sources)
    else:
        lines.append("Aucune source disponible : renvoie des listes d'anecdotes vides.")

    lines += [
        "",
        "=== Étude d'utilisation en jeu ===",
        "Rédige, dans \"game_study\", le rôle typique de cette carte dans un deck, ses forces, "
        "ses limites, jusqu'à "
        f"{MAX_RELATED_CARDS} cartes associées, et une note de jouabilité courte.",
        f"Format Standard : {_yes_no(legal_standard)}.",
        f"Format Étendu : {_yes_no(legal_expanded)}.",
        f"Règle des Prix : {prize_label}.",
    ]
    if attacks:
        lines.append(f"Attaques (données du catalogue, à ne pas réinventer) : {attacks}")
    if abilities:
        lines.append(f"Talents (données du catalogue, à ne pas réinventer) : {abilities}")

    if tournament_decks:
        decks_text = "; ".join(
            f'{d["deck_name"]} — {d["tournament_name"]} ({d["placement"]})'
            for d in tournament_decks
        )
        lines.append(
            "Présence en tournoi relevée (source Limitless TCG, n'utilise que ces résultats, "
            f"n'invente aucun autre tournoi ni placement) : {decks_text}"
        )
    else:
        lines.append(
            "Aucune présence en tournoi n'a été relevée pour cette carte à ce jour : ne "
            "prétends pas le contraire, indique plutôt si son profil (légalités, règle des "
            "Prix, attaques) explique cette absence."
        )

    lines.append(
        "Règle stricte générale : base-toi uniquement sur les informations fournies ci-dessus "
        "dans ce message, pour les deux parties. N'invente aucun fait, aucune URL, aucun "
        "tournoi, aucun placement, aucune règle absente de ce message."
    )
    return "\n".join(lines)
