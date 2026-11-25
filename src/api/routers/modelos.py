"""Router de métricas comparativas de modelos de imputación."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.auth.api_keys import require_reader
from src.api.db.models import ApiKey, MetricaModelo
from src.api.db.session import get_db
from src.api.schemas import (
    LongitudHueco,
    MetricaModeloResponse,
    TemporadaClima,
    VariableClima,
)

router = APIRouter(prefix="/modelos", tags=["modelos"])


@router.get("/metricas", response_model=list[MetricaModeloResponse])
def obtener_metricas_modelos(
    _: Annotated[ApiKey, Depends(require_reader)],
    db: Annotated[Session, Depends(get_db)],
    variable: Annotated[VariableClima | None, Query()] = None,
    longitud_hueco: Annotated[LongitudHueco | None, Query()] = None,
    temporada: Annotated[TemporadaClima | None, Query()] = None,
) -> list[MetricaModeloResponse]:
    """Devuelve la comparativa de métricas entre líneas base, Hurdle/DTR e IBM Granite TTM."""
    stmt = select(MetricaModelo)
    if variable is not None:
        stmt = stmt.where(MetricaModelo.variable == variable)
    if longitud_hueco is not None:
        stmt = stmt.where(MetricaModelo.longitud_hueco == longitud_hueco)
    if temporada is not None:
        stmt = stmt.where(MetricaModelo.temporada == temporada)

    rows = db.scalars(
        stmt.order_by(
            MetricaModelo.variable.asc(),
            MetricaModelo.longitud_hueco.asc(),
            MetricaModelo.temporada.asc(),
            MetricaModelo.kge.desc(),
        )
    ).all()

    return [
        MetricaModeloResponse(
            modelo=r.modelo,
            variable=r.variable,  # type: ignore[arg-type]
            longitud_hueco=r.longitud_hueco,  # type: ignore[arg-type]
            temporada=r.temporada,  # type: ignore[arg-type]
            rmse=r.rmse,
            mae=r.mae,
            bias=r.bias,
            kge=r.kge,
            pod=r.pod,
            far=r.far,
            cobertura_90=r.cobertura_90,
        )
        for r in rows
    ]
