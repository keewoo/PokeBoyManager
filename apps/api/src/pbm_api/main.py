from fastapi import FastAPI

from pbm_api.routers.health import router as health_router

app = FastAPI(title="PokeBoyManager API")

app.include_router(health_router)
