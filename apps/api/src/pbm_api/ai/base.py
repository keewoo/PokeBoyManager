"""Interface commune aux fournisseurs IA (Anthropic, Google Gemini, OpenAI) — mission
`v3-ia-providers` point 1 : changer de fournisseur ne touche aucune fonctionnalité en aval.

Une photo (ou plusieurs) + un schéma Pydantic + une consigne -> un objet validé + l'usage
consommé. Chaque fournisseur produit sa sortie structurée native (`pbm_api.ai.json_schema`) ;
si elle ne valide pas contre le schéma, `extract` fait une seule nouvelle tentative en
expliquant au modèle l'erreur rencontrée (mission point 2) avant d'abandonner
(`InvalidExtractionResponseError`).
"""

from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from pbm_api.ai.errors import InvalidExtractionResponseError
from pbm_api.models import AiProvider

T = TypeVar("T", bound=BaseModel)


class ImageInput(BaseModel):
    """Une photo à transmettre au fournisseur. `media_type` vient de
    `pbm_api.ai.images.detect_media_type`, jamais supposé."""

    data: bytes
    media_type: str


class ExtractionUsage(BaseModel):
    provider: AiProvider
    model: str
    input_tokens: int
    output_tokens: int


class AIProvider(ABC):
    PROVIDER: ClassVar[AiProvider]
    DEFAULT_MODEL: ClassVar[str]
    ECONOMY_MODEL: ClassVar[str | None] = None

    def __init__(self, api_key: str, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=60.0)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def extract(
        self,
        images: list[ImageInput],
        schema: type[T],
        prompt: str,
        *,
        model: str | None = None,
    ) -> tuple[T, ExtractionUsage]:
        chosen_model = model or self.DEFAULT_MODEL
        text, usage = await self._call(images, schema, prompt, chosen_model, retry_hint=None)
        try:
            return schema.model_validate_json(text), usage
        except ValidationError as first_error:
            retry_text, retry_usage = await self._call(
                images, schema, prompt, chosen_model, retry_hint=str(first_error)
            )
            usage = ExtractionUsage(
                provider=usage.provider,
                model=usage.model,
                input_tokens=usage.input_tokens + retry_usage.input_tokens,
                output_tokens=usage.output_tokens + retry_usage.output_tokens,
            )
            try:
                return schema.model_validate_json(retry_text), usage
            except ValidationError as second_error:
                raise InvalidExtractionResponseError(str(second_error)) from second_error

    @abstractmethod
    async def _call(
        self,
        images: list[ImageInput],
        schema: type[T],
        prompt: str,
        model: str,
        retry_hint: str | None,
    ) -> tuple[str, ExtractionUsage]:
        """Un aller-retour vers le fournisseur ; lève une sous-classe d'`AIProviderError`
        normalisée en cas d'échec (clé invalide, quota, surcharge, contenu refusé)."""
