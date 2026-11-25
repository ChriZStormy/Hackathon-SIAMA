"""Generador determinístico de datos sintéticos para Guanajuato (fallback de verificación)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_guanajuato_dataset(
    n_days: int = 365,
    start_date: str = "2023-01-01",
    missing_rate: float = 0.12,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera estaciones y series diarias sintéticas realistas para Guanajuato.

    Se usa únicamente como fallback verificable cuando los archivos oficiales
    aún no han sido colocados en ``data/raw/``.
    """
    rng = np.random.default_rng(seed)

    estaciones = pd.DataFrame(
        [
            {"id_estacion": "GTO_001", "nombre": "León", "latitud": 21.122, "longitud": -101.682, "altitud_m": 1815.0},
            {"id_estacion": "GTO_002", "nombre": "Guanajuato Capital", "latitud": 21.019, "longitud": -101.257, "altitud_m": 2000.0},
            {"id_estacion": "GTO_003", "nombre": "Irapuato", "latitud": 20.676, "longitud": -101.356, "altitud_m": 1730.0},
            {"id_estacion": "GTO_004", "nombre": "Celaya", "latitud": 20.523, "longitud": -100.815, "altitud_m": 1752.0},
            {"id_estacion": "GTO_005", "nombre": "San Miguel de Allende", "latitud": 20.914, "longitud": -100.744, "altitud_m": 1910.0},
        ]
    )

    fechas = pd.date_range(start=start_date, periods=n_days, freq="D")
    day_of_year = fechas.day_of_year.to_numpy()
    seasonal_temp = 5.5 * np.sin(2.0 * np.pi * (day_of_year - 105) / 365.25)
    rain_prob = np.clip(0.05 + 0.40 * np.exp(-0.5 * ((day_of_year - 215) / 45.0) ** 2), 0.02, 0.65)

    records: list[pd.DataFrame] = []
    for _, row in estaciones.iterrows():
        alt_offset = (1850.0 - float(row["altitud_m"])) * 0.0065
        tmax = 26.5 + seasonal_temp + alt_offset + rng.normal(0.0, 2.0, size=n_days)
        diurnal_range = np.clip(rng.normal(13.0, 2.2, size=n_days), 4.0, 22.0)
        tmin = tmax - diurnal_range

        is_rain = rng.random(n_days) < rain_prob
        precip = np.where(is_rain, rng.gamma(shape=1.4, scale=6.5, size=n_days), 0.0)
        precip = np.round(np.maximum(precip, 0.0), 2)

        df_station = pd.DataFrame(
            {
                "id_estacion": row["id_estacion"],
                "fecha": fechas,
                "precipitacion": precip,
                "tmax": np.round(tmax, 2),
                "tmin": np.round(tmin, 2),
            }
        )

        # Inyectar huecos cortos y medianos de forma realista
        for col in ("precipitacion", "tmax", "tmin"):
            mask = rng.random(n_days) < missing_rate
            df_station.loc[mask, col] = np.nan

        records.append(df_station)

    series_diarias = pd.concat(records, ignore_index=True)
    return estaciones, series_diarias
