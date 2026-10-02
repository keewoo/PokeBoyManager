"""Route de supervision : signale que l'API répond, sans dépendance externe."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Corps de réponse de `/health` : statut fixe à `"ok"`."""

    status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Répond systématiquement `ok`, pour les sondes de disponibilité (load balancer, CI)."""
    return HealthResponse(status="ok")
