"""Appel minimal à chaque fournisseur IA pour valider une clé — un aller-retour de liste de
modèles, jamais une complétion : coût nul ou quasi nul pour l'utilisateur.

`ProviderKeyTester` est injecté par dépendance FastAPI (`get_provider_key_tester`) : la
suite automatisée le remplace par un double déterministe (aucune clé IA réelle disponible
sur cette machine, voir `apps/api/scripts/test_ai_key_manual.py` pour l'essai avec une vraie
clé). La clé est transmise en en-tête HTTP pour les trois fournisseurs, jamais en paramètre
d'URL : une URL de requête peut se retrouver journalisée par une bibliothèque tierce, un
en-tête beaucoup plus rarement.
"""

import httpx

from pbm_api.models import AiProvider

_TIMEOUT_SECONDS = 10.0

_ENDPOINTS: dict[AiProvider, str] = {
    AiProvider.anthropic: "https://api.anthropic.com/v1/models",
    AiProvider.openai: "https://api.openai.com/v1/models",
    AiProvider.gemini: "https://generativelanguage.googleapis.com/v1beta/models",
}

VALID_MESSAGE = "Clé valide."
REFUSED_MESSAGE = "Clé refusée par le fournisseur."
UNREACHABLE_MESSAGE = "Fournisseur injoignable — réessayez plus tard."


class ProviderKeyTester:
    def build_request(self, provider: AiProvider, api_key: str) -> tuple[str, dict[str, str]]:
        url = _ENDPOINTS[provider]
        if provider is AiProvider.anthropic:
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        elif provider is AiProvider.openai:
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            headers = {"x-goog-api-key": api_key}
        return url, headers

    async def test(self, provider: AiProvider, api_key: str) -> tuple[bool, str]:
        url, headers = self.build_request(provider, api_key)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError:
            return False, UNREACHABLE_MESSAGE

        if response.status_code == 200:
            return True, VALID_MESSAGE
        # Anthropic/OpenAI renvoient 401/403 sur une clé invalide ; Gemini renvoie 400
        # `API_KEY_INVALID` (vérifié en direct contre l'API réelle le 2026-09-19) — les trois
        # sont donc traités comme un refus, pas une erreur inattendue.
        if response.status_code in (400, 401, 403):
            return False, REFUSED_MESSAGE
        return False, f"Réponse inattendue du fournisseur ({response.status_code})."


def get_provider_key_tester() -> ProviderKeyTester:
    return ProviderKeyTester()
