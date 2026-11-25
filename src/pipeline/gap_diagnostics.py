"""Módulo de Diagnóstico de Vacíos y Taxonomía de Huecos para SIAMA-Impute."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.config import Settings, load_settings


@dataclass
class GapDiagnosticsResult:
    station_variable_summary: pd.DataFrame
    yearly_missing: pd.DataFrame
    seasonal_missing: pd.DataFrame
    gaps_catalog: pd.DataFrame

    def to_summary_dict(self) -> dict[str, Any]:
        """Devuelve un resumen serializable en JSON del diagnóstico de vacíos."""
        taxonomy_totals = (
            self.gaps_catalog["category"].value_counts().to_dict()
            if not self.gaps_catalog.empty
            else {}
        )
        return {
            "total_station_variable_pairs": int(len(self.station_variable_summary)),
            "total_gaps_detected": int(len(self.gaps_catalog)),
            "gap_taxonomy_counts": {
                "corto": int(taxonomy_totals.get("corto", 0)),
                "medio": int(taxonomy_totals.get("medio", 0)),
                "largo": int(taxonomy_totals.get("largo", 0)),
            },
            "station_variable_summary": self.station_variable_summary.to_dict(orient="records"),
            "seasonal_missing_overview": (
                self.seasonal_missing.groupby(["variable", "temporada"], as_index=False)
                .agg(total_days=("total_days", "sum"), missing_days=("missing_days", "sum"))
                .assign(
                    missing_pct=lambda d: np.round(
                        d["missing_days"] / np.maximum(d["total_days"], 1) * 100.0, 2
                    )
                )
                .to_dict(orient="records")
                if not self.seasonal_missing.empty
                else []
            ),
        }


def classify_gap_length(
    length_days: int,
    short_max_days: int = 3,
    medium_max_days: int = 30,
) -> str:
    """Clasifica la longitud de un hueco contiguo en corto, medio o largo."""
    if length_days <= short_max_days:
        return "corto"
    if length_days <= medium_max_days:
        return "medio"
    return "largo"


def _assign_season(months: pd.Series, lluvias_months: set[int]) -> pd.Series:
    return pd.Series(
        np.where(months.isin(lluvias_months), "lluvias", "estiaje"),
        index=months.index,
    )


def _extract_contiguous_gaps(
    dates: pd.DatetimeIndex,
    is_missing: np.ndarray,
    lluvias_months: set[int],
    short_max_days: int,
    medium_max_days: int,
) -> list[dict[str, Any]]:
    """Extrae todos los bloques contiguos de días faltantes con su taxonomía."""
    gaps: list[dict[str, Any]] = []
    n = len(is_missing)
    idx = 0
    while idx < n:
        if not is_missing[idx]:
            idx += 1
            continue
        start = idx
        while idx < n and is_missing[idx]:
            idx += 1
        end = idx - 1
        length = end - start + 1
        gap_dates = dates[start : end + 1]
        wet_days = int(np.isin(gap_dates.month, list(lluvias_months)).sum())
        dominant_season = "lluvias" if wet_days >= (length / 2.0) else "estiaje"

        gaps.append(
            {
                "start_date": gap_dates[0].strftime("%Y-%m-%d"),
                "end_date": gap_dates[-1].strftime("%Y-%m-%d"),
                "length_days": int(length),
                "category": classify_gap_length(length, short_max_days, medium_max_days),
                "start_year": int(gap_dates[0].year),
                "dominant_season": dominant_season,
            }
        )
    return gaps


def run_gap_diagnostics(
    series_diarias: pd.DataFrame,
    settings: Settings | None = None,
) -> GapDiagnosticsResult:
    """Ejecuta el perfilado completo de vacíos por estación, variable, año y temporada.

    Reindexa internamente cada estación sobre su calendario diario continuo entre
    su fecha mínima y máxima para capturar también días completamente omitidos.
    """
    cfg = settings or load_settings()
    id_col = cfg.data_schema.station_id_col
    date_col = cfg.data_schema.date_col
    variables = [v for v in cfg.data_schema.variables if v in series_diarias.columns]
    lluvias_months = set(cfg.seasons.lluvias_months)
    short_max = cfg.gap_diagnostics.short_max_days
    medium_max = cfg.gap_diagnostics.medium_max_days

    df = series_diarias.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[id_col, date_col]).sort_values([id_col, date_col])

    summary_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    seasonal_rows: list[dict[str, Any]] = []
    catalog_rows: list[dict[str, Any]] = []

    for station_id, grp in df.groupby(id_col, sort=True):
        grp_dedup = grp.drop_duplicates(subset=[date_col], keep="first").set_index(date_col)
        full_calendar = pd.date_range(grp_dedup.index.min(), grp_dedup.index.max(), freq="D")
        reindexed = grp_dedup.reindex(full_calendar)
        years = pd.Series(full_calendar.year, index=full_calendar)
        seasons = _assign_season(pd.Series(full_calendar.month, index=full_calendar), lluvias_months)

        for var in variables:
            is_na = reindexed[var].isna()
            total_days = int(len(full_calendar))
            missing_days = int(is_na.sum())
            missing_pct = round(missing_days / total_days * 100.0, 2) if total_days else 0.0

            gaps = _extract_contiguous_gaps(
                dates=full_calendar,
                is_missing=is_na.to_numpy(dtype=bool),
                lluvias_months=lluvias_months,
                short_max_days=short_max,
                medium_max_days=medium_max,
            )

            lengths = [g["length_days"] for g in gaps]
            n_corto = sum(1 for g in gaps if g["category"] == "corto")
            n_medio = sum(1 for g in gaps if g["category"] == "medio")
            n_largo = sum(1 for g in gaps if g["category"] == "largo")

            summary_rows.append(
                {
                    id_col: station_id,
                    "variable": var,
                    "date_min": full_calendar[0].strftime("%Y-%m-%d"),
                    "date_max": full_calendar[-1].strftime("%Y-%m-%d"),
                    "total_days": total_days,
                    "missing_days": missing_days,
                    "missing_pct": missing_pct,
                    "n_gaps": len(gaps),
                    "n_corto": n_corto,
                    "n_medio": n_medio,
                    "n_largo": n_largo,
                    "max_gap_days": int(max(lengths)) if lengths else 0,
                    "median_gap_days": float(np.median(lengths)) if lengths else 0.0,
                    "mean_gap_days": round(float(np.mean(lengths)), 2) if lengths else 0.0,
                }
            )

            for g in gaps:
                catalog_rows.append({id_col: station_id, "variable": var, **g})

            # Perfilado anual
            for yr, mask_yr in is_na.groupby(years):
                yr_total = int(len(mask_yr))
                yr_miss = int(mask_yr.sum())
                yearly_rows.append(
                    {
                        id_col: station_id,
                        "variable": var,
                        "anio": int(yr),
                        "total_days": yr_total,
                        "missing_days": yr_miss,
                        "missing_pct": round(yr_miss / yr_total * 100.0, 2) if yr_total else 0.0,
                    }
                )

            # Perfilado por temporada (lluvias vs estiaje)
            for season_name, mask_s in is_na.groupby(seasons):
                s_total = int(len(mask_s))
                s_miss = int(mask_s.sum())
                seasonal_rows.append(
                    {
                        id_col: station_id,
                        "variable": var,
                        "temporada": str(season_name),
                        "total_days": s_total,
                        "missing_days": s_miss,
                        "missing_pct": round(s_miss / s_total * 100.0, 2) if s_total else 0.0,
                    }
                )

    return GapDiagnosticsResult(
        station_variable_summary=pd.DataFrame(summary_rows),
        yearly_missing=pd.DataFrame(yearly_rows),
        seasonal_missing=pd.DataFrame(seasonal_rows),
        gaps_catalog=pd.DataFrame(
            catalog_rows,
            columns=[
                id_col,
                "variable",
                "start_date",
                "end_date",
                "length_days",
                "category",
                "start_year",
                "dominant_season",
            ],
        ),
    )
