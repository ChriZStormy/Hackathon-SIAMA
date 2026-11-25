"""Carga estandarizada de estaciones y series diarias con manejo de faltantes y fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, Settings, load_settings
from src.pipeline.synthetic_data import generate_synthetic_guanajuato_dataset


@dataclass
class LoadedDataset:
    estaciones: pd.DataFrame
    series_diarias: pd.DataFrame
    source: str  # "official" | "synthetic_fallback"
    missing_official_files: list[str]


def _normalize_missing_values(df: pd.DataFrame, missing_codes: list[object]) -> pd.DataFrame:
    cleaned = df.copy()
    numeric_codes = [c for c in missing_codes if isinstance(c, (int, float))]
    str_codes = [str(c) for c in missing_codes if isinstance(c, str)]

    for col in cleaned.columns:
        if pd.api.types.is_numeric_dtype(cleaned[col]):
            if numeric_codes:
                cleaned[col] = cleaned[col].replace(numeric_codes, np.nan)
        elif pd.api.types.is_object_dtype(cleaned[col]) or pd.api.types.is_string_dtype(cleaned[col]):
            if str_codes:
                cleaned[col] = cleaned[col].replace(str_codes, np.nan)
    return cleaned


def load_climate_datasets(
    settings: Settings | None = None,
    root: Path = PROJECT_ROOT,
    allow_synthetic_fallback: bool = True,
) -> LoadedDataset:
    """Carga estaciones y series diarias desde data/raw/ o activa fallback sintético."""
    cfg = settings or load_settings(root=root)
    file_status = cfg.check_official_files(root=root)

    required_keys = ["estaciones", "series_diarias"]
    missing = [k for k in ("estaciones", "series_diarias", "covariables", "test_publico") if not file_status[k]["exists"]]
    missing_required = [k for k in required_keys if not file_status[k]["exists"]]

    if missing_required:
        if not allow_synthetic_fallback:
            missing_paths = [file_status[k]["path"] for k in missing_required]
            raise FileNotFoundError(
                f"Faltan archivos oficiales requeridos en data/raw/: {missing_paths}"
            )
        estaciones, series = generate_synthetic_guanajuato_dataset(
            seed=cfg.baseline.random_seed
        )
        return LoadedDataset(
            estaciones=estaciones,
            series_diarias=series,
            source="synthetic_fallback",
            missing_official_files=missing,
        )

    est_path = Path(file_status["estaciones"]["path"])
    ser_path = Path(file_status["series_diarias"]["path"])

    estaciones = pd.read_csv(est_path)
    series = pd.read_csv(ser_path)

    estaciones = _normalize_missing_values(estaciones, cfg.data_schema.missing_value_codes)
    series = _normalize_missing_values(series, cfg.data_schema.missing_value_codes)

    id_col = cfg.data_schema.station_id_col
    date_col = cfg.data_schema.date_col

    if id_col in estaciones.columns:
        estaciones[id_col] = estaciones[id_col].astype(str).str.strip()
    if id_col in series.columns:
        series[id_col] = series[id_col].astype(str).str.strip()
    if date_col in series.columns:
        series[date_col] = pd.to_datetime(series[date_col], errors="coerce")

    for var in cfg.data_schema.variables:
        if var in series.columns:
            series[var] = pd.to_numeric(series[var], errors="coerce")

    return LoadedDataset(
        estaciones=estaciones,
        series_diarias=series,
        source="official",
        missing_official_files=missing,
    )
