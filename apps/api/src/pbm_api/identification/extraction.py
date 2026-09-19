"""Extraction par carte (mission point 1, étendue par `v3-etat`) : un appel `AIProvider.extract`
par recadrage, sortie `CardExtraction` validée par schéma (mission `v3-ia-providers`) — le même
appel rend aussi l'état indicatif de l'exemplaire (coins, bords, surface) et un signal de
contrefaçon, jamais un second aller-retour IA (principe cadre)."""

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
    "cannot actually read on the card — leave it null with confidence 0 instead.\n\n"
    "Also assess the physical condition of this exact card copy, as a grader would, on a scale "
    "of exactly these seven values from best to worst: \"mint\", \"near_mint\", \"excellent\", "
    "\"good\", \"light_played\", \"played\", \"poor\". Grade the four corners together "
    "(corner_wear: whiteness, rounding, fraying), the four edges together (edge_wear: "
    "whitening, nicks), and the front surface (surface_wear: scratches, scuffs, print lines, "
    "indentations) — never centering, which is measured separately. For each of these three, "
    "give a one-sentence justification (in French) and a confidence between 0 and 1: lower it "
    "sharply if the card is behind a glossy sleeve/toploader with glare, seen at an angle, or "
    "partly out of focus — a guess through plastic reflections is not a reliable grade. Never "
    "leave corner_wear/edge_wear/surface_wear null if the card is visible at all; only lower "
    "the confidence.\n\n"
    "Finally, flag counterfeit_suspected (true/false) if the card shows signs it may not be an "
    "authentic official print: wrong or inconsistent font, off colors, a malformed collector "
    "number format, missing expected holographic pattern, or any other visible inconsistency "
    "with genuine Pokémon cards. If true, give a short French reason in counterfeit_reason and "
    "a confidence; if false, leave counterfeit_reason null and counterfeit_confidence at 0."
)


async def extract_card(
    provider: AIProvider, image: ImageInput, *, model: str | None = None
) -> tuple[CardExtraction, ExtractionUsage]:
    return await provider.extract([image], CardExtraction, PROMPT, model=model)
