"""CSRF par double soumission signée : le cookie CSRF est un HMAC du jeton de session.

Le cookie de session est HttpOnly (illisible en JS) ; le cookie CSRF ne l'est pas — le
front le relit et le renvoie dans l'en-tête `X-CSRF-Token` sur toute requête qui écrit.
Un attaquant qui ne peut forger l'en-tête (CSRF classique) ni lire le cookie de session
(cross-origin) ne peut pas produire de HMAC valide.
"""

import hashlib
import hmac

from pbm_api.config import settings

CSRF_HEADER_NAME = "X-CSRF-Token"


def compute_csrf_token(session_token: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        session_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(session_token: str, submitted_token: str | None) -> bool:
    if not submitted_token:
        return False
    expected = compute_csrf_token(session_token)
    return hmac.compare_digest(expected, submitted_token)
