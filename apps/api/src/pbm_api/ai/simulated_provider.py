"""Fournisseur IA simulé (lot `v5-e2e`) — activé uniquement par le drapeau `AI_SIMULATED_PROVIDER`
(faux par défaut, jamais en UAT/PROD, voir `pbm_api.config.Settings`). Permet à l'e2e Playwright
du parcours complet de faire tourner le *vrai* pipeline de reconnaissance
(`pbm_api.worker.detect_cards_task` : détection puis identification) sans clé IA réelle ni appel
réseau — aucune n'est disponible sur chimera (voir `CLAUDE.md`). Différent des scripts
`seed_*_e2e.py` des lots précédents, qui contournent le pipeline en écrivant le résultat
directement en base : ici, la détection, l'identification et le rapprochement catalogue
s'exécutent réellement, seul l'aller-retour réseau vers le fournisseur est remplacé.

Ne simule que le schéma réellement exercé par ce lot (`CardExtraction`, missions
`v3-identification`/`v3-etat`) : les neuf cartes de démonstration (`pbm_api.seed.DEMO_CARDS`, la
« photo de référence » du classeur 3×3), servies dans l'ordre d'appel, une par appel — mais dans
l'e2e du parcours complet, un seul appel a réellement lieu : les neuf recadrages du classeur
synthétique sont visuellement indiscernables (`pbm_api.detection.synthetic.draw_card`, pensé pour
la géométrie, pas l'identification), donc de même empreinte perceptuelle ; le cache
d'identification (`identification_cache`, une vraie fonctionnalité de production, pas un artefact
de la simulation) résout les huit détections suivantes sans repasser par ce fournisseur. Voir le
compte rendu du lot `v5-e2e`. Tout autre schéma (repli LLM de la détection, insights, étude en
jeu) lève une erreur explicite plutôt qu'une réponse inventée : ce lot ne les exerce pas (photo de
référence sans reflets, détectée par OpenCV seul).
"""

from itertools import cycle
from typing import TypeVar

import httpx
from pydantic import BaseModel

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.identification.schemas import CardExtraction
from pbm_api.models import AiProvider as AiProviderEnum
from pbm_api.seed import DEMO_CARDS as _DEMO_CARDS
from pbm_api.seed import DEMO_SETS

T = TypeVar("T", bound=BaseModel)

_SETS_BY_CODE = {s["code"]: s for s in DEMO_SETS}


def _simulated_extraction(card: dict) -> CardExtraction:
    return CardExtraction(
        name=card["names"]["fr"],
        name_confidence=0.99,
        number=card["number"],
        number_confidence=0.99,
        total=_SETS_BY_CODE[card["set_code"]]["total_cards"],
        total_confidence=0.9,
        set_code=card["set_code"],
        set_code_confidence=0.99,
        language="fr",
        language_confidence=0.99,
        corner_wear="near_mint",
        corner_wear_confidence=0.7,
        corner_wear_note=None,
        edge_wear="near_mint",
        edge_wear_confidence=0.7,
        edge_wear_note=None,
        surface_wear="near_mint",
        surface_wear_confidence=0.7,
        surface_wear_note=None,
        counterfeit_suspected=False,
        counterfeit_confidence=0.9,
        counterfeit_reason=None,
    )


class UnsimulatedSchemaError(RuntimeError):
    """Levée quand le pipeline demande au fournisseur simulé un schéma qu'il ne sait pas produire
    — jamais un JSON inventé (règle du dépôt contre les replis silencieux)."""


class SimulatedProvider(AIProvider):
    """`DEFAULT_MODEL` est purement indicatif : `_call` ne fait aucune requête réseau, jamais
    facturée nulle part."""

    DEFAULT_MODEL = "simulated"

    def __init__(
        self,
        requested_provider: AiProviderEnum,
        api_key: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(api_key, http_client=http_client)
        # Le fournisseur réellement choisi par l'utilisateur (anthropic/gemini/openai) est
        # conservé pour que le suivi d'usage (`GET /me/ai-usage`) reste cohérent avec sa clé,
        # même si aucun appel réseau n'a réellement eu lieu.
        self.PROVIDER = requested_provider
        self._cards = cycle(_DEMO_CARDS)

    async def _call(
        self,
        images: list[ImageInput],
        schema: type[T],
        prompt: str,
        model: str,
        retry_hint: str | None,
    ) -> tuple[str, ExtractionUsage]:
        if schema is not CardExtraction:
            raise UnsimulatedSchemaError(
                f"SimulatedProvider (lot v5-e2e) ne sait simuler que CardExtraction, pas "
                f"{schema.__name__}."
            )
        extraction = _simulated_extraction(next(self._cards))
        usage = ExtractionUsage(
            provider=self.PROVIDER, model=model, input_tokens=0, output_tokens=0
        )
        return extraction.model_dump_json(), usage
