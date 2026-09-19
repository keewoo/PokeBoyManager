"""Extraction par carte (mission point 1) : un appel `AIProvider.extract` par recadrage, sortie
`CardExtraction` validée par schéma (mission `v3-ia-providers`)."""

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.identification.schemas import CardExtraction

PROMPT = (
    "This image shows a single Pokémon trading card, already cropped and straightened from a "
    "photo. Read everything printed on the card: its name, its collector number as printed at "
    "the bottom (e.g. \"236\", \"025/025\", or a promo/gallery code like \"TG05\", \"XY121\", "
    "\"SWSH283\"), the total card count of the set if printed right after the number, the set "
    "symbol or set code if legible, the language the printed text is written in (\"fr\" or "
    "\"en\"), its HP if it is a Pokémon card, its type or category (e.g. \"Fire\", \"Trainer\", "
    "\"Energy\"), and which special variant it is (normal, holo, reverse holo, 1st edition, "
    "full art, or gold — pick \"other\" if it is clearly special but does not match any of "
    "these). For every field, also return a confidence between 0 and 1: 0 if you could not read "
    "it at all, close to 1 if it is printed clearly and unambiguously. Never guess a value you "
    "cannot actually read on the card — leave it null with confidence 0 instead."
)


async def extract_card(
    provider: AIProvider, image: ImageInput, *, model: str | None = None
) -> tuple[CardExtraction, ExtractionUsage]:
    return await provider.extract([image], CardExtraction, PROMPT, model=model)
