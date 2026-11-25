"""Router geoespacial y de series climatológicas por estación."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.auth.api_keys import require_reader
from src.api.db.models import (
    AlertaHomogeneidad,
    ApiKey,
    DiagnosticoHueco,
    Estacion,
    SerieImputada,
)
from src.api.db.session import get_db
from src.api.schemas import (
    ConfianzaMinima,
    ConteoHuecos,
    DiagnosticoResponse,
    EstacionesMapaResponse,
    EstacionMapaFeature,
    EstacionMapaProperties,
    FormatoSerie,
    GeoJSONPoint,
    SerieDato,
    SeriesResponse,
    VariableClima,
)

router = APIRouter(prefix="/estaciones", tags=["estaciones"])


def _get_station_or_404(db: Session, clave: str) -> Estacion:
    estacion = db.get(Estacion, clave)
    if estacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Estación '{clave}' no encontrada.",
        )
    return estacion


@router.get("/mapa", response_model=EstacionesMapaResponse)
def obtener_mapa_estaciones(
    _: Annotated[ApiKey, Depends(require_reader)],
    db: Annotated[Session, Depends(get_db)],
) -> EstacionesMapaResponse:
    """Devuelve un GeoJSON FeatureCollection de todas las estaciones listo para Leaflet."""
    estaciones = db.scalars(select(Estacion).order_by(Estacion.clave.asc())).all()
    diags = db.scalars(select(DiagnosticoHueco)).all()
    alertas = db.scalars(select(AlertaHomogeneidad)).all()

    diags_by_station: dict[str, list[DiagnosticoHueco]] = {}
    for d in diags:
        diags_by_station.setdefault(d.clave_estacion, []).append(d)

    alert_by_station: dict[str, bool] = {}
    for a in alertas:
        if a.alerta_homogeneidad:
            alert_by_station[a.clave_estacion] = True

    features: list[EstacionMapaFeature] = []
    for est in estaciones:
        st_diags = diags_by_station.get(est.clave, [])
        precip_diag = next((d for d in st_diags if d.variable == "precipitacion"), None)
        ref_diag = precip_diag or (st_diags[0] if st_diags else None)

        if ref_diag is not None:
            completitud = round(max(0.0, min(100.0, 100.0 - ref_diag.porcentaje_faltantes)), 1)
            huecos_totales = (
                ref_diag.huecos_cortos + ref_diag.huecos_medios + ref_diag.huecos_largos
            )
        else:
            completitud = 100.0
            huecos_totales = 0

        features.append(
            EstacionMapaFeature(
                geometry=GeoJSONPoint(coordinates=(est.longitud, est.latitud)),
                properties=EstacionMapaProperties(
                    clave=est.clave,
                    nombre=est.nombre,
                    completitud_pct=completitud,
                    alerta_homogeneidad=alert_by_station.get(est.clave, False),
                    huecos_totales=huecos_totales,
                ),
            )
        )

    return EstacionesMapaResponse(features=features)


@router.get("/{clave}/diagnostico", response_model=DiagnosticoResponse)
def obtener_diagnostico_estacion(
    clave: str,
    _: Annotated[ApiKey, Depends(require_reader)],
    db: Annotated[Session, Depends(get_db)],
    variable: Annotated[VariableClima, Query()] = "precipitacion",
) -> DiagnosticoResponse:
    """Devuelve el diagnóstico de vacíos, clasificación de huecos y estado de homogeneidad."""
    _get_station_or_404(db, clave)

    diag = db.scalar(
        select(DiagnosticoHueco).where(
            DiagnosticoHueco.clave_estacion == clave,
            DiagnosticoHueco.variable == variable,
        )
    )
    alerta = db.scalar(
        select(AlertaHomogeneidad)
        .where(
            AlertaHomogeneidad.clave_estacion == clave,
            AlertaHomogeneidad.variable == variable,
        )
        .order_by(AlertaHomogeneidad.alerta_homogeneidad.desc(), AlertaHomogeneidad.id.asc())
    )

    return DiagnosticoResponse(
        clave_estacion=clave,
        variable=variable,
        porcentaje_faltantes=round(diag.porcentaje_faltantes, 2) if diag else 0.0,
        conteo_huecos=ConteoHuecos(
            cortos=diag.huecos_cortos if diag else 0,
            medios=diag.huecos_medios if diag else 0,
            largos=diag.huecos_largos if diag else 0,
        ),
        metodo_recomendado=diag.metodo_recomendado if diag else "granite_ttm_hibrido",
        alerta_homogeneidad=bool(alerta.alerta_homogeneidad) if alerta else False,
        detalle_homogeneidad=alerta.detalle_homogeneidad if alerta else None,
    )


def _allowed_flags(incluir_estimados: bool, confianza_minima: ConfianzaMinima) -> set[str]:
    if not incluir_estimados:
        return {"observado"}
    if confianza_minima == "alta":
        return {"observado", "estimado_alta_confianza"}
    if confianza_minima == "baja":
        return {"observado", "estimado_alta_confianza", "estimado_baja_confianza"}
    return {
        "observado",
        "estimado_alta_confianza",
        "estimado_baja_confianza",
        "no_estimable",
    }


def _stream_csv(datos: list[SerieDato]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "fecha",
            "valor_observado",
            "valor_estimado",
            "es_estimado",
            "bandera_calidad",
            "incertidumbre_90_inf",
            "incertidumbre_90_sup",
        ]
    )
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in datos:
        inf = row.incertidumbre_90[0] if row.incertidumbre_90 else ""
        sup = row.incertidumbre_90[1] if row.incertidumbre_90 else ""
        writer.writerow(
            [
                row.fecha,
                "" if row.valor_observado is None else row.valor_observado,
                "" if row.valor_estimado is None else row.valor_estimado,
                str(row.es_estimado).lower(),
                row.bandera_calidad,
                inf,
                sup,
            ]
        )
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


@router.get("/{clave}/series", response_model=SeriesResponse)
def obtener_series_estacion(
    clave: str,
    variable: Annotated[VariableClima, Query()],
    _: Annotated[ApiKey, Depends(require_reader)],
    db: Annotated[Session, Depends(get_db)],
    desde: Annotated[date | None, Query()] = None,
    hasta: Annotated[date | None, Query()] = None,
    incluir_estimados: Annotated[bool, Query()] = True,
    confianza_minima: Annotated[ConfianzaMinima, Query()] = "todas",
    formato: Annotated[FormatoSerie, Query()] = "json",
) -> SeriesResponse | StreamingResponse:
    """Devuelve la serie diaria en JSON o CSV garantizando trazabilidad e incertidumbre."""
    _get_station_or_404(db, clave)

    if desde and hasta and desde > hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro 'desde' no puede ser posterior a 'hasta'.",
        )

    allowed = _allowed_flags(incluir_estimados, confianza_minima)
    stmt = select(SerieImputada).where(
        SerieImputada.clave_estacion == clave,
        SerieImputada.variable == variable,
        SerieImputada.bandera_calidad.in_(allowed),
    )
    if desde is not None:
        stmt = stmt.where(SerieImputada.fecha >= desde)
    if hasta is not None:
        stmt = stmt.where(SerieImputada.fecha <= hasta)

    rows = db.scalars(stmt.order_by(SerieImputada.fecha.asc())).all()

    datos: list[SerieDato] = []
    for r in rows:
        if r.bandera_calidad in ("no_estimable", "observado"):
            incertidumbre = None
            val_est = None
            es_est = False
        else:
            incertidumbre = (
                (r.incertidumbre_90_inf, r.incertidumbre_90_sup)
                if r.incertidumbre_90_inf is not None and r.incertidumbre_90_sup is not None
                else None
            )
            val_est = r.valor_estimado
            es_est = True

        datos.append(
            SerieDato(
                fecha=r.fecha.isoformat(),
                valor_observado=r.valor_observado,
                valor_estimado=val_est,
                es_estimado=es_est,
                bandera_calidad=r.bandera_calidad,  # type: ignore[arg-type]
                incertidumbre_90=incertidumbre,
            )
        )

    if formato == "csv":
        filename = f"siama_{clave}_{variable}.csv"
        return StreamingResponse(
            _stream_csv(datos),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return SeriesResponse(
        clave_estacion=clave,
        variable=variable,
        datos=datos,
    )
