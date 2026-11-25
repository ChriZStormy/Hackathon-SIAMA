"""Herramientas internas deterministas expuestas a IBM Granite 4.2 vía tool calling."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.db.models import (
    AlertaHomogeneidad,
    DiagnosticoHueco,
    Estacion,
    MetricaModelo,
    SerieImputada,
)

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_diagnostico",
            "description": (
                "Obtiene el diagnóstico de vacíos, conteo de huecos (cortos, medios, largos), "
                "método recomendado y alerta de homogeneidad de una estación climatológica."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "clave_estacion": {
                        "type": "string",
                        "description": "Clave de la estación (ej. '11024').",
                    },
                    "variable": {
                        "type": "string",
                        "enum": ["precipitacion", "tmax", "tmin"],
                        "description": "Variable climatológica a consultar.",
                    },
                },
                "required": ["clave_estacion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_series_stats",
            "description": (
                "Calcula estadísticas reales y porcentajes exactos de registros observados, "
                "estimados (alta/baja confianza) y no estimables para una estación, variable y rango."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "clave_estacion": {
                        "type": "string",
                        "description": "Clave de la estación (ej. '11024').",
                    },
                    "variable": {
                        "type": "string",
                        "enum": ["precipitacion", "tmax", "tmin"],
                    },
                    "desde": {
                        "type": "string",
                        "description": "Fecha inicial opcional YYYY-MM-DD.",
                    },
                    "hasta": {
                        "type": "string",
                        "description": "Fecha final opcional YYYY-MM-DD.",
                    },
                },
                "required": ["clave_estacion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metricas",
            "description": (
                "Consulta métricas comparativas de desempeño (RMSE, MAE, BIAS, KGE, POD, FAR, cobertura_90) "
                "entre líneas base y modelos IBM Granite."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "variable": {
                        "type": "string",
                        "enum": ["precipitacion", "tmax", "tmin"],
                    },
                    "longitud_hueco": {
                        "type": "string",
                        "enum": ["corto", "medio", "largo"],
                    },
                    "temporada": {
                        "type": "string",
                        "enum": ["lluvias", "estiaje"],
                    },
                },
            },
        },
    },
]


def infer_variable_from_question(pregunta: str) -> str:
    """Infere la variable climatológica principal mencionada en la pregunta."""
    q = pregunta.lower()
    if any(tok in q for tok in ("tmax", "temperatura máxima", "temperatura maxima", "calor")):
        return "tmax"
    if any(tok in q for tok in ("tmin", "temperatura mínima", "temperatura minima", "helada", "frío", "frio")):
        return "tmin"
    if "temperatura" in q:
        return "tmax"
    return "precipitacion"


def infer_season_range_from_question(
    pregunta: str,
    db: Session,
    clave_estacion: str,
    variable: str,
) -> tuple[date | None, date | None]:
    """Detecta si la pregunta solicita un periodo específico (ej. último verano o un año)."""
    q = pregunta.lower()
    max_date = db.scalar(
        select(func.max(SerieImputada.fecha)).where(
            SerieImputada.clave_estacion == clave_estacion,
            SerieImputada.variable == variable,
        )
    )
    if max_date is None:
        return None, None

    year_match = re.search(r"\b(20\d{2})\b", q)
    target_year = int(year_match.group(1)) if year_match else max_date.year

    if any(tok in q for tok in ("verano", "lluvias", "temporada húmeda", "temporada humeda")):
        return date(target_year, 6, 1), date(target_year, 10, 31)
    if any(tok in q for tok in ("estiaje", "seca", "invierno")):
        return date(target_year, 1, 1), date(target_year, 5, 31)
    if year_match:
        return date(target_year, 1, 1), date(target_year, 12, 31)
    return None, None


def get_diagnostico(db: Session, clave_estacion: str, variable: str = "precipitacion") -> dict[str, Any]:
    """Recupera el diagnóstico estructural de vacíos y homogeneidad desde BD."""
    estacion = db.get(Estacion, clave_estacion)
    if estacion is None:
        return {"error": f"Estación {clave_estacion} no encontrada."}

    diag = db.scalar(
        select(DiagnosticoHueco).where(
            DiagnosticoHueco.clave_estacion == clave_estacion,
            DiagnosticoHueco.variable == variable,
        )
    )
    alerta = db.scalar(
        select(AlertaHomogeneidad)
        .where(
            AlertaHomogeneidad.clave_estacion == clave_estacion,
            AlertaHomogeneidad.variable == variable,
        )
        .order_by(AlertaHomogeneidad.alerta_homogeneidad.desc(), AlertaHomogeneidad.id.asc())
    )

    return {
        "clave_estacion": clave_estacion,
        "nombre_estacion": estacion.nombre,
        "municipio": estacion.municipio,
        "variable": variable,
        "porcentaje_faltantes": round(diag.porcentaje_faltantes, 2) if diag else 0.0,
        "conteo_huecos": {
            "cortos": diag.huecos_cortos if diag else 0,
            "medios": diag.huecos_medios if diag else 0,
            "largos": diag.huecos_largos if diag else 0,
        },
        "metodo_recomendado": diag.metodo_recomendado if diag else "granite_ttm_hibrido",
        "alerta_homogeneidad": bool(alerta.alerta_homogeneidad) if alerta else False,
        "detalle_homogeneidad": alerta.detalle_homogeneidad if alerta else None,
    }


def get_series_stats(
    db: Session,
    clave_estacion: str,
    variable: str = "precipitacion",
    desde: date | str | None = None,
    hasta: date | str | None = None,
) -> dict[str, Any]:
    """Calcula porcentajes exactos observados vs estimados vs no estimables desde BD."""
    if isinstance(desde, str) and desde:
        desde = date.fromisoformat(desde)
    if isinstance(hasta, str) and hasta:
        hasta = date.fromisoformat(hasta)

    stmt = select(SerieImputada).where(
        SerieImputada.clave_estacion == clave_estacion,
        SerieImputada.variable == variable,
    )
    if isinstance(desde, date):
        stmt = stmt.where(SerieImputada.fecha >= desde)
    if isinstance(hasta, date):
        stmt = stmt.where(SerieImputada.fecha <= hasta)

    rows = db.scalars(stmt.order_by(SerieImputada.fecha.asc())).all()
    total = len(rows)
    if total == 0:
        return {
            "clave_estacion": clave_estacion,
            "variable": variable,
            "desde": desde.isoformat() if isinstance(desde, date) else None,
            "hasta": hasta.isoformat() if isinstance(hasta, date) else None,
            "total_registros": 0,
            "observados": 0,
            "estimados": 0,
            "estimados_alta": 0,
            "estimados_baja": 0,
            "no_estimables": 0,
            "pct_observado": 0.0,
            "pct_estimado": 0.0,
            "pct_no_estimable": 0.0,
            "promedio_valor": None,
        }

    obs = sum(1 for r in rows if r.bandera_calidad == "observado")
    est_alta = sum(1 for r in rows if r.bandera_calidad == "estimado_alta_confianza")
    est_baja = sum(1 for r in rows if r.bandera_calidad == "estimado_baja_confianza")
    no_est = sum(1 for r in rows if r.bandera_calidad == "no_estimable")
    estimados = est_alta + est_baja

    valid_vals = [
        (r.valor_observado if not r.es_estimado else r.valor_estimado)
        for r in rows
        if (r.valor_observado if not r.es_estimado else r.valor_estimado) is not None
    ]
    avg_val = round(sum(valid_vals) / len(valid_vals), 2) if valid_vals else None

    return {
        "clave_estacion": clave_estacion,
        "variable": variable,
        "desde": rows[0].fecha.isoformat(),
        "hasta": rows[-1].fecha.isoformat(),
        "total_registros": total,
        "observados": obs,
        "estimados": estimados,
        "estimados_alta": est_alta,
        "estimados_baja": est_baja,
        "no_estimables": no_est,
        "pct_observado": round((obs / total) * 100.0, 1),
        "pct_estimado": round((estimados / total) * 100.0, 1),
        "pct_no_estimable": round((no_est / total) * 100.0, 1),
        "promedio_valor": avg_val,
    }


def get_metricas(
    db: Session,
    variable: str | None = None,
    longitud_hueco: str | None = None,
    temporada: str | None = None,
) -> list[dict[str, Any]]:
    """Consulta las métricas comparativas de modelos almacenadas en BD."""
    stmt = select(MetricaModelo)
    if variable:
        stmt = stmt.where(MetricaModelo.variable == variable)
    if longitud_hueco:
        stmt = stmt.where(MetricaModelo.longitud_hueco == longitud_hueco)
    if temporada:
        stmt = stmt.where(MetricaModelo.temporada == temporada)

    rows = db.scalars(stmt.order_by(MetricaModelo.kge.desc())).all()
    return [
        {
            "modelo": r.modelo,
            "variable": r.variable,
            "longitud_hueco": r.longitud_hueco,
            "temporada": r.temporada,
            "rmse": r.rmse,
            "mae": r.mae,
            "bias": r.bias,
            "kge": r.kge,
            "pod": r.pod,
            "far": r.far,
            "cobertura_90": r.cobertura_90,
        }
        for r in rows
    ]
