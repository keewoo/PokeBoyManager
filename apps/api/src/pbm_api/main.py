from fastapi import FastAPI

from pbm_api.routers.auth import router as auth_router
from pbm_api.routers.health import router as health_router
from pbm_api.routers.images import router as images_router

app = FastAPI(title="PokeBoyManager API")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(images_router)
