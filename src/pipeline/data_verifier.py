"""Inspección diagnóstica de estructura, cobertura temporal, huecos y consistencia física."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.config import Settings, load_settings


def inspect_dataset(
    estaciones: pd.DataFrame,
    series_diarias: pd.DataFrame,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Genera un diagnóstico estructurado de las tablas cargadas y sus huecos."""
    cfg = settings or load_settings()
    id_col = cfg.data_schema.station_id_col
    date_col = cfg.data_schema.date_col
    variables = [v for v in cfg.data_schema.variables if v in series_diarias.columns]

    date_series = pd.to_datetime(series_diarias[date_col], errors="coerce")
    min_date = date_series.min()
    max_date = date_series.max()

    missing_pct: dict[str, float] = {}
    for var in variables:
        missing_pct[var] = round(float(series_diarias[var].isna().mean() * 100.0), 2)

    physical_checks: dict[str, int] = {}
    if "precipitacion" in series_diarias.columns:
        physical_checks["precip_negative_count"] = int(
            (series_diarias["precipitacion"] < cfg.physical_constraints.precip_min).sum()
        )
    if "tmax" in series_diarias.columns and "tmin" in series_diarias.columns:
        both_present = series_diarias["tmax"].notna() & series_diarias["tmin"].notna()
        physical_checks["tmax_le_tmin_count"] = int(
            (both_present & (series_diarias["tmax"] <= series_diarias["tmin"])).sum()
        )

    return {
        "estaciones_count": int(len(estaciones)),
        "estaciones_columns": list(estaciones.columns),
        "series_rows": int(len(series_diarias)),
        "series_columns": list(series_diarias.columns),
        "unique_stations_in_series": int(series_diarias[id_col].nunique()) if id_col in series_diarias.columns else 0,
        "date_min": min_date.strftime("%Y-%m-%d") if pd.notna(min_date) else None,
        "date_max": max_date.strftime("%Y-%m-%d") if pd.notna(max_date) else None,
        "missing_pct_by_variable": missing_pct,
        "physical_constraint_violations": physical_checks,
    }
