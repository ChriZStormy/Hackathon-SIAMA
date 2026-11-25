"""Router del asistente conversacional SIAMA respaldado por IBM Granite 4.2."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.assistant.granite_client import consultar_asistente
from src.api.auth.api_keys import require_reader
from src.api.db.models import ApiKey
from src.api.db.session import get_db
from src.api.schemas import AsistenteRequest, AsistenteResponse

router = APIRouter(prefix="/asistente", tags=["asistente"])


@router.post("/consultar", response_model=AsistenteResponse)
def consultar_asistente_siama(
    payload: AsistenteRequest,
    _: Annotated[ApiKey, Depends(require_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> AsistenteResponse:
    """Responde consultas sobre confiabilidad y completitud usando tool calling + auditoría."""
    return consultar_asistente(
        db=db,
        pregunta=payload.pregunta,
        clave_estacion=payload.clave_estacion,
    )
