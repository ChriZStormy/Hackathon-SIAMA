"""Router de imputación al vuelo reservado exclusivamente al perfil operador."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth.api_keys import require_operator
from src.api.db.models import ApiKey
from src.api.schemas import ImputarRequest, SerieDato, SeriesResponse
from src.api.services.imputation_bridge import predict_on_demand

router = APIRouter(tags=["imputacion"])


@router.post("/imputar", response_model=SeriesResponse)
def imputar_al_vuelo(
    payload: ImputarRequest,
    _: Annotated[ApiKey, Depends(require_operator)],
) -> SeriesResponse:
    """Ejecuta imputación bajo demanda sobre registros enviados (perfil operador)."""
    records = [{"fecha": r.fecha, "valor": r.valor} for r in payload.registros]
    raw_output = predict_on_demand(
        station_id=payload.clave_estacion,
        variable=payload.variable,
        records=records,
    )
    datos = [SerieDato(**item) for item in raw_output]
    return SeriesResponse(
        clave_estacion=payload.clave_estacion,
        variable=payload.variable,
        datos=datos,
    )
