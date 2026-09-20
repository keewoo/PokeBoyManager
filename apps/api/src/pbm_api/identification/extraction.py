"""Extraction par carte (mission point 1, étendue par `v3-etat`) : un appel `AIProvider.extract`
par recadrage, sortie `CardExtraction` validée par schéma (mission `v3-ia-providers`) — le même
appel rend aussi l'état indicatif de l'exemplaire (coins, bords, surface) et un signal de
contrefaçon, jamais un second aller-retour IA (principe cadre)."""

import cv2
import numpy as np

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.identification.schemas import CardBottomReading, CardExtraction

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
    "Pay special attention to the collector number and set code: they are printed small, usually "
    "in a bottom corner (bottom-left or bottom-right). Zoom in mentally on that area and report "
    "the number even when tiny — it is the single most useful field for identifying the card.\n\n"
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


def _prompt_with_visual_hints(visual_hints: list[str]) -> str:
    """Ajoute au prompt les candidats retenus par la comparaison visuelle (mission
    `v3-identification-visuelle` point 3) quand elle est ambiguë (groupe « même illustration ») :
    toujours le même appel, jamais un second — juste plus de contexte pour trancher entre un
    nombre restreint de cartes plutôt que de lire à l'aveugle."""
    if not visual_hints:
        return PROMPT
    hints = "\n".join(f"- {hint}" for hint in visual_hints)
    return (
        f"{PROMPT}\n\nA visual comparison against the official card images narrowed this down "
        f"to one of these candidates (same illustration, different printing/language/edition) — "
        f"use it to help pick the exact name/number/set, but only report what you can actually "
        f"read on the photo, never invent a match if none of them is visibly correct:\n{hints}"
    )


async def extract_card(
    provider: AIProvider,
    image: ImageInput,
    *,
    model: str | None = None,
    visual_hints: list[str] | None = None,
) -> tuple[CardExtraction, ExtractionUsage]:
    prompt = _prompt_with_visual_hints(visual_hints or [])
    return await provider.extract([image], CardExtraction, prompt, model=model)


# --- Seconde passe ciblée sur le bas de la carte (lot `pbm-parcours-validation`, point 4) ---

# Fraction inférieure du recadrage 630×880 où figurent numéro / total / code d'extension (imprimés
# en bas, souvent en tout petit) : seule cette bande est agrandie et relue.
BOTTOM_STRIP_FRACTION = 0.22
# Facteur d'agrandissement de la bande avant relecture — un numéro minuscule sur le recadrage
# entier devient lisible une fois la bande isolée et agrandie.
BOTTOM_STRIP_UPSCALE = 3.0

BOTTOM_PROMPT = (
    "This image is the bottom strip of a single Pokémon trading card, already enlarged. Read "
    "ONLY the small printed collector information found there: the collector number (e.g. "
    "\"236\", \"025/198\", or a promo/gallery code like \"TG05\", \"XY121\", \"SWSH283\", "
    "\"GG10\"), the total card count of the set if printed right after the number (the part "
    "after the \"/\"), and the set code / set abbreviation if legible (e.g. \"SVI\", \"OBF\", "
    "\"PAL\", \"MEW\"). Return a confidence between 0 and 1 for each field; if you truly cannot "
    "read a field, leave it null with confidence 0 — never guess."
)


def bottom_strip(crop: np.ndarray, *, fraction: float = BOTTOM_STRIP_FRACTION) -> np.ndarray:
    """Bande inférieure du recadrage BGR, agrandie pour la lisibilité de la seconde passe."""
    height = crop.shape[0]
    y0 = max(0, int(round(height * (1.0 - fraction))))
    strip = crop[y0:height]
    if strip.size == 0:
        strip = crop
    return cv2.resize(
        strip, None, fx=BOTTOM_STRIP_UPSCALE, fy=BOTTOM_STRIP_UPSCALE, interpolation=cv2.INTER_CUBIC
    )


def needs_bottom_pass(extraction: CardExtraction) -> bool:
    """Le premier appel n'a lu AUCUN numéro (mission point 4, « si le champ revient vide ») : c'est
    le cas qui fait tomber le rapprochement sur le palier « nom seul » (jamais présélectionné). Un
    numéro lu mais peu sûr n'est PAS visé ici — il est présent, le rapprochement s'en sert, et une
    lecture globale douteuse est déjà rattrapée par le secours vision (`rescue`, sous 0,75 de score
    combiné). Ne pas élargir au code d'extension : trop de cartes n'en impriment aucun."""
    return not extraction.number


async def read_card_bottom(
    provider: AIProvider, crop: np.ndarray, *, model: str | None = None
) -> tuple[CardBottomReading, ExtractionUsage]:
    """Relit le bas de la carte agrandi pour en extraire numéro / total / code d'extension."""
    image = ImageInput(data=encode_jpeg(bottom_strip(crop)), media_type="image/jpeg")
    return await provider.extract([image], CardBottomReading, BOTTOM_PROMPT, model=model)


def merge_bottom_reading(base: CardExtraction, bottom: CardBottomReading) -> CardExtraction:
    """Complète l'extraction du premier appel avec ce que la seconde passe a lu de plus sûr : un
    champ n'est remplacé que si la seconde passe le lit avec une meilleure confiance (jamais
    écraser une lecture sûre par une lecture douteuse)."""
    merged = base.model_copy()
    if bottom.number and bottom.number_confidence > base.number_confidence:
        merged.number = bottom.number
        merged.number_confidence = bottom.number_confidence
    if bottom.set_code and bottom.set_code_confidence > base.set_code_confidence:
        merged.set_code = bottom.set_code
        merged.set_code_confidence = bottom.set_code_confidence
    if bottom.total is not None and bottom.total_confidence > base.total_confidence:
        merged.total = bottom.total
        merged.total_confidence = bottom.total_confidence
    return merged
