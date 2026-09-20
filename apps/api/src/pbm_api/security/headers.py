"""En-têtes de sécurité de réponse (lot `v5-securite`, mission point 2), appliqués à toute
requête de l'API.

L'API ne sert que du JSON et des octets d'image (jamais de HTML fourni par un utilisateur) :
`default-src 'none'` est donc sans risque de casser quoi que ce soit ici, contrairement à une
CSP sur `apps/web`. Seule exception : `/docs`/`/redoc` (Swagger UI / ReDoc) et `/openapi.json`
qu'ils chargent — ces pages intègrent des scripts depuis un CDN, une CSP stricte les casserait ;
elles gardent les en-têtes défensifs (nosniff, frame-ancestors, referrer-policy) mais pas la CSP.

`Strict-Transport-Security` est sans effet si la réponse part en clair (les navigateurs
l'ignorent hors HTTPS) : l'envoyer aussi en dev HTTP est donc inoffensif, pas besoin de
condition sur le schéma de la requête.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_UNRESTRICTED_CSP_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path not in _UNRESTRICTED_CSP_PATHS:
            response.headers["Content-Security-Policy"] = _CSP
        return response
