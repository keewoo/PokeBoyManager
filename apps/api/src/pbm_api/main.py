from fastapi import FastAPI

from pbm_api.routers.ai_keys import router as ai_keys_router
from pbm_api.routers.auth import router as auth_router
from pbm_api.routers.health import router as health_router
from pbm_api.routers.images import router as images_router
from pbm_api.security.log_filter import install_api_key_redaction
from pbm_api.security.validation_errors import install_validation_error_redaction

install_api_key_redaction()

app = FastAPI(title="PokeBoyManager API")
install_validation_error_redaction(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(images_router)
app.include_router(ai_keys_router)
