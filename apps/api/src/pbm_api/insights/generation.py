"""Génération d'anecdotes sourcées à partir du contexte collecté — mission `v4-anecdotes`
point 2. Le prompt liste explicitement les pages disponibles et leurs URLs et interdit tout
fait absent de ce contexte ; `pbm_api.insights.service` rejette après coup toute anecdote dont
`source_url` ne figure pas parmi les URLs de contexte — défense en profondeur contre une
hallucination d'URL malgré la consigne (mission point 2, risque « hallucinations »)."""

from pydantic import BaseModel, Field

from pbm_api.insights.context import ContextPage

MAX_ANECDOTES = 5


class AnecdoteItem(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source_url: str


class AnecdotesExtraction(BaseModel):
    anecdotes: list[AnecdoteItem] = Field(max_length=MAX_ANECDOTES)


def build_prompt(*, card_name: str, set_name: str, pages: list[ContextPage]) -> str:
    sources = "\n\n".join(
        f"Source [{page.source_url}] — {page.title} :\n{page.text}" for page in pages
    )
    return (
        f'Tu rédiges, pour la fiche de la carte Pokémon "{card_name}" (extension "{set_name}"), '
        "trois à cinq anecdotes courtes (une ou deux phrases chacune) : illustrateur, réédition, "
        "événement qui a fait varier sa cote, ou autre fait marquant.\n\n"
        "Règle stricte : chaque anecdote doit se baser uniquement sur les extraits ci-dessous, et "
        "son `source_url` doit reprendre exactement l'une des URLs listées entre crochets. "
        "N'invente aucun fait absent de ces extraits ; s'il n'y a pas assez de matière pour trois "
        "anecdotes sourcées, renvoies-en moins plutôt que d'en inventer.\n\n"
        f"{sources}"
    )
