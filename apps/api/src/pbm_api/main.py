from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pbm_api.config import settings
from pbm_api.routers.ai_keys import router as ai_keys_router
from pbm_api.routers.auth import router as auth_router
from pbm_api.routers.card_insights import router as card_insights_router
from pbm_api.routers.catalog import router as catalog_router
from pbm_api.routers.collection import router as collection_router
from pbm_api.routers.export import router as export_router
from pbm_api.routers.health import router as health_router
from pbm_api.routers.images import router as images_router
from pbm_api.routers.profile import router as profile_router
from pbm_api.routers.uploads import router as uploads_router
from pbm_api.security.log_filter import install_api_key_redaction
from pbm_api.security.validation_errors import install_validation_error_redaction

install_api_key_redaction()

app = FastAPI(title="PokeBoyManager API")
install_validation_error_redaction(app)

# `apps/web` et `apps/api` sont deux origines distinctes (ports différents en local, sous-
# domaines distincts en UAT/PROD) : sans CORS, le navigateur bloque tout fetch, y compris les
# routes d'authentification. `allow_credentials` est nécessaire pour que le cookie de session
# parte avec la requête ; il impose une liste d'origines explicite (jamais `*`).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_public_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(images_router)
app.include_router(ai_keys_router)
app.include_router(catalog_router)
app.include_router(profile_router)
app.include_router(uploads_router)
app.include_router(collection_router)
app.include_router(card_insights_router)
app.include_router(export_router)
