"""Erreurs du coffre de clés IA et des appels normalisés aux fournisseurs (Anthropic, Gemini,
OpenAI)."""


class ProviderKeyNotFoundError(Exception):
    """Aucune clé enregistrée pour ce fournisseur, pour cet utilisateur."""


class DefaultProviderWithoutKeyError(Exception):
    """Le fournisseur par défaut choisi n'a pas de clé enregistrée."""


class UnsupportedImageFormatError(Exception):
    """Photo dont le format n'a pas pu être détecté (`pbm_api.ai.images.detect_media_type`)."""


class AIProviderError(Exception):
    """Base commune aux erreurs normalisées d'un appel d'extraction (mission `v3-ia-providers`
    point 3) — `user_message` est le texte à montrer à l'utilisateur et à consigner sur le
    job ; `detail` (brut, jamais montré tel quel) part dans les journaux serveur seulement."""

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        self.user_message = user_message
        super().__init__(detail or user_message)


class InvalidApiKeyError(AIProviderError):
    """Clé rejetée par le fournisseur (401/403 Anthropic/OpenAI, ou `PERMISSION_DENIED` Gemini)."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__("Clé invalide ou révoquée par le fournisseur.", detail=detail)


class QuotaExceededError(AIProviderError):
    """Quota ou débit dépassé chez le fournisseur (429, ou `RESOURCE_EXHAUSTED` Gemini)."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__("Quota dépassé chez le fournisseur.", detail=detail)


class ProviderOverloadedError(AIProviderError):
    """Fournisseur en panne ou saturé (5xx, ou `UNAVAILABLE` Gemini) — à réessayer plus tard."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__("Fournisseur surchargé — réessayez plus tard.", detail=detail)


class ProviderUnreachableError(AIProviderError):
    """Échec réseau avant toute réponse HTTP du fournisseur (coupure, DNS, délai dépassé)."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__("Fournisseur injoignable — réessayez plus tard.", detail=detail)


class ContentRefusedError(AIProviderError):
    """Le fournisseur a refusé de produire une sortie (filtre de sécurité, contenu bloqué)."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__("Contenu refusé par le fournisseur.", detail=detail)


class InvalidExtractionResponseError(AIProviderError):
    """Sortie toujours invalide contre le schéma après la tentative de correction d'`extract`."""

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            "Le fournisseur n'a pas renvoyé de réponse exploitable après une nouvelle "
            "tentative.",
            detail=detail,
        )
