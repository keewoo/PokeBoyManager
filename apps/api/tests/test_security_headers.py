"""En-têtes de sécurité de réponse (mission `v5-securite` point 2). Avant ce lot, aucune de
ces routes ne posait `Content-Security-Policy`/`X-Frame-Options`/`X-Content-Type-Options`/
`Referrer-Policy`/`Strict-Transport-Security` : ces tests échouent sans
`SecurityHeadersMiddleware` et passent une fois branché sur `main.py`.
"""

from fastapi.testclient import TestClient

from pbm_api.main import app

client = TestClient(app)


def test_json_response_carries_defensive_headers() -> None:
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_json_response_carries_a_locked_down_content_security_policy() -> None:
    response = client.get("/health")
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_404_response_still_carries_defensive_headers() -> None:
    """Les en-têtes viennent du middleware, pas d'une route précise : une réponse d'erreur
    (jamais atteint une route) doit les porter aussi."""
    response = client.get("/route-qui-nexiste-pas")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response.headers


def test_docs_page_keeps_defensive_headers_but_not_the_strict_csp() -> None:
    """`/docs` (Swagger UI) charge ses scripts depuis un CDN : une CSP `script-src 'self'`
    casserait la page. Les autres en-têtes défensifs restent posés."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" not in response.headers
