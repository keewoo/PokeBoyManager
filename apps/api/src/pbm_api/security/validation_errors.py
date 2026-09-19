"""Redacte les champs sensibles (`pbm_api.ai.schemas.SENSITIVE_FIELD_NAMES`) dans le corps
d'une réponse 422.

Le comportement par défaut de FastAPI sérialise `input` tel quel dans `detail[]` pour toute
erreur de validation — une clé IA trop courte ou trop longue (`AiKeyUpsertRequest.api_key`)
reviendrait donc en clair dans la réponse. `pydantic.ConfigDict(hide_input_in_errors=True)`
ne suffit pas : il ne redacte que la représentation texte de l'exception (`str(exc)`), pas
les dictionnaires structurés que `RequestValidationError.errors()` renvoie et que FastAPI
sérialise directement.
"""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pbm_api.ai.schemas import SENSITIVE_FIELD_NAMES

REDACTED_INPUT = "***"


async def redact_sensitive_fields_in_validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        error = dict(error)
        loc = error.get("loc") or ()
        if loc and loc[-1] in SENSITIVE_FIELD_NAMES:
            error["input"] = REDACTED_INPUT
        errors.append(error)
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))


def install_validation_error_redaction(app) -> None:
    app.add_exception_handler(RequestValidationError, redact_sensitive_fields_in_validation_errors)
