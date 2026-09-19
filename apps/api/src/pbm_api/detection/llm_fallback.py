"""Repli par boîtes englobantes demandées au LLM vision (mission point 2), quand OpenCV seul
ne trouve rien de plausible — pochettes plastiques, reflets, fond clair, cartes qui se
touchent. Une seule photo, un seul appel : le LLM ne fait que localiser les cartes, jamais les
identifier (l'identification est un lot ultérieur, un seul appel par carte à ce moment-là —
cette détection n'y compte pas puisqu'elle porte sur la photo entière, pas sur une carte).
"""

from pydantic import BaseModel, Field

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput

PROMPT = (
    "This photo shows one or more trading cards (Pokémon cards), possibly in plastic "
    "sleeves/toploaders, on a table or in a binder page. Find the rectangular boundary of "
    "each individual card (the card itself, not the sleeve or binder pocket if it extends "
    "beyond the card). Return one bounding box per card, in reading order: left to right, "
    "then top to bottom row by row. Coordinates are fractions of the image width/height "
    "(0.0 to 1.0), origin at the top-left corner."
)


class NormalizedBox(BaseModel):
    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)


class BoundingBoxesResult(BaseModel):
    boxes: list[NormalizedBox]


async def detect_boxes_with_llm(
    provider: AIProvider, image: ImageInput, *, model: str | None = None
) -> tuple[list[NormalizedBox], ExtractionUsage]:
    result, usage = await provider.extract(
        [image], BoundingBoxesResult, PROMPT, model=model
    )
    return result.boxes, usage


def denormalize_box(box: NormalizedBox, width: int, height: int) -> tuple[int, int, int, int]:
    """Boîte normalisée -> pixels `(x_min, y_min, x_max, y_max)`, bornée à l'image."""
    x_min = max(0, min(width - 1, round(box.x_min * width)))
    y_min = max(0, min(height - 1, round(box.y_min * height)))
    x_max = max(x_min + 1, min(width, round(box.x_max * width)))
    y_max = max(y_min + 1, min(height, round(box.y_max * height)))
    return x_min, y_min, x_max, y_max
