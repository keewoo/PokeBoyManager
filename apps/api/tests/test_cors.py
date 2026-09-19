"""`apps/web` et `apps/api` sont deux origines distinctes : sans CORS, le navigateur bloque
tout appel aux routes d'authentification, y compris avec un cookie de session valide.
Ce test échoue sans le middleware CORS branché dans `main.py` et passe une fois posé.
"""

from pbm_api.config import settings


async def test_preflight_allows_configured_web_origin(api_client):
    response = await api_client.options(
        "/auth/login",
        headers={
            "Origin": settings.app_public_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers["access-control-allow-origin"] == settings.app_public_url
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_actual_request_exposes_cors_headers_for_web_origin(api_client):
    response = await api_client.post(
        "/auth/login",
        json={"email": "inconnu@example.com", "password": "peu importe"},
        headers={"Origin": settings.app_public_url},
    )
    assert response.headers["access-control-allow-origin"] == settings.app_public_url
    assert response.headers["access-control-allow-credentials"] == "true"
