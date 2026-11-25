"""Generador determinístico de datos sintéticos para Guanajuato.

Incluye:
1. ``generate_synthetic_guanajuato_dataset``: fallback ligero compatible con Paso 1.
2. ``generate_guanajuato_diagnostic_benchmark``: dataset multianual realista con
   correlación espacial entre estaciones, huecos cortos/medios/largos, quiebres de
   homogeneidad inyectados y anomalías controladas de QC (con ground truth trazable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SyntheticBenchmark:
    estaciones: pd.DataFrame
    series_diarias: pd.DataFrame
    ground_truth: dict[str, Any]


GUANAJUATO_STATIONS_CATALOG = [
    {
        "id_estacion": "GTO_001",
        "nombre": "León",
        "latitud": 21.122,
        "longitud": -101.682,
        "altitud_m": 1815.0,
        "region_climatica": "Bajio_Oeste",
        "rain_factor": 1.00,
        "temp_bias_c": 0.4,
    },
    {
        "id_estacion": "GTO_002",
        "nombre": "Guanajuato Capital",
        "latitud": 21.019,
        "longitud": -101.257,
        "altitud_m": 2000.0,
        "region_climatica": "Sierra_Central",
        "rain_factor": 1.12,
        "temp_bias_c": -0.6,
    },
    {
        "id_estacion": "GTO_003",
        "nombre": "Irapuato",
        "latitud": 20.676,
        "longitud": -101.356,
        "altitud_m": 1730.0,
        "region_climatica": "Bajio_Centro",
        "rain_factor": 1.05,
        "temp_bias_c": 0.9,
    },
    {
        "id_estacion": "GTO_004",
        "nombre": "Celaya",
        "latitud": 20.523,
        "longitud": -100.815,
        "altitud_m": 1752.0,
        "region_climatica": "Bajio_Este",
        "rain_factor": 0.95,
        "temp_bias_c": 0.7,
    },
    {
        "id_estacion": "GTO_005",
        "nombre": "San Miguel de Allende",
        "latitud": 20.914,
        "longitud": -100.744,
        "altitud_m": 1910.0,
        "region_climatica": "Altiplano_Centro",
        "rain_factor": 0.88,
        "temp_bias_c": -0.2,
    },
    {
        "id_estacion": "GTO_006",
        "nombre": "Dolores Hidalgo",
        "latitud": 21.156,
        "longitud": -100.934,
        "altitud_m": 1920.0,
        "region_climatica": "Norte_Semiarido",
        "rain_factor": 0.78,
        "temp_bias_c": -0.5,
    },
    {
        "id_estacion": "GTO_007",
        "nombre": "Acámbaro",
        "latitud": 20.031,
        "longitud": -100.722,
        "altitud_m": 1860.0,
        "region_climatica": "Sur_Humedo",
        "rain_factor": 1.25,
        "temp_bias_c": 0.3,
    },
    {
        "id_estacion": "GTO_008",
        "nombre": "San Luis de la Paz",
        "latitud": 21.298,
        "longitud": -100.516,
        "altitud_m": 2020.0,
        "region_climatica": "Sierra_Gorda_Noreste",
        "rain_factor": 0.72,
        "temp_bias_c": -1.1,
    },
]


def generate_synthetic_guanajuato_dataset(
    n_days: int = 365,
    start_date: str = "2023-01-01",
    missing_rate: float = 0.12,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera estaciones y series diarias sintéticas ligeras para verificación del Paso 1."""
    rng = np.random.default_rng(seed)

    estaciones = pd.DataFrame(GUANAJUATO_STATIONS_CATALOG[:5])[
        ["id_estacion", "nombre", "latitud", "longitud", "altitud_m"]
    ].copy()

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

        for col in ("precipitacion", "tmax", "tmin"):
            mask = rng.random(n_days) < missing_rate
            df_station.loc[mask, col] = np.nan

        records.append(df_station)

    series_diarias = pd.concat(records, ignore_index=True)
    return estaciones, series_diarias


def generate_guanajuato_diagnostic_benchmark(
    start_date: str = "2019-01-01",
    end_date: str = "2023-12-31",
    seed: int = 42,
    inject_gaps: bool = True,
    inject_homogeneity_breaks: bool = True,
    inject_qc_anomalies: bool = True,
) -> SyntheticBenchmark:
    """Genera un benchmark multianual reproducible para Paso 2 (huecos, homogeneidad y QC).

    Características físicas y estadísticas:
    - 8 estaciones distribuidas en Guanajuato con distintos regímenes de lluvia y altitud.
    - Señal sinóptica regional compartida (alta correlación espacial realista en lluvia y T).
    - Estacionalidad marcada de Guanajuato (lluvias mayo–octubre, estiaje noviembre–abril).
    - Inyección trazable de huecos cortos (1–3d), medios (4–30d) y largos (>30d),
      quiebres de homogeneidad y anomalías de QC.
    """
    rng = np.random.default_rng(seed)
    fechas = pd.date_range(start=start_date, end=end_date, freq="D")
    n_days = len(fechas)
    doy = fechas.day_of_year.to_numpy()
    months = fechas.month.to_numpy()

    estaciones = pd.DataFrame(GUANAJUATO_STATIONS_CATALOG)[
        ["id_estacion", "nombre", "latitud", "longitud", "altitud_m", "region_climatica"]
    ].copy()

    # Señal sinóptica regional compartida (AR(1) para persistencia térmica natural)
    synoptic_tmax = np.zeros(n_days)
    synoptic_tmin = np.zeros(n_days)
    for t in range(1, n_days):
        synoptic_tmax[t] = 0.65 * synoptic_tmax[t - 1] + rng.normal(0.0, 1.35)
        synoptic_tmin[t] = 0.65 * synoptic_tmin[t - 1] + rng.normal(0.0, 1.25)

    # Ciclo estacional de temperatura en Guanajuato (máximo en mayo, mínimo en enero)
    seasonal_tmax = 4.8 * np.sin(2.0 * np.pi * (doy - 60) / 365.25)
    seasonal_tmin = 5.2 * np.sin(2.0 * np.pi * (doy - 95) / 365.25)

    # Señal sinóptica de lluvia: temporada húmeda (may–oct) vs estiaje seco (nov–abr)
    is_wet_season = np.isin(months, [5, 6, 7, 8, 9, 10])
    wet_envelope = np.where(
        is_wet_season,
        0.22 + 0.38 * np.exp(-0.5 * ((doy - 210) / 42.0) ** 2),
        0.025,
    )
    regional_rain_event = rng.random(n_days) < wet_envelope
    regional_rain_intensity = np.where(
        regional_rain_event,
        rng.gamma(shape=1.6, scale=7.5, size=n_days),
        0.0,
    )

    records: list[pd.DataFrame] = []
    for meta in GUANAJUATO_STATIONS_CATALOG:
        alt_lapse = (1850.0 - float(meta["altitud_m"])) * 0.0065
        t_bias = float(meta["temp_bias_c"])
        r_factor = float(meta["rain_factor"])

        tmax = (
            27.0
            + seasonal_tmax
            + alt_lapse
            + t_bias
            + synoptic_tmax
            + rng.normal(0.0, 0.55, size=n_days)
        )
        tmin = (
            12.0
            + seasonal_tmin
            + alt_lapse
            + t_bias
            + synoptic_tmin
            + rng.normal(0.0, 0.50, size=n_days)
        )
        # Garantizar base limpia Tmax > Tmin + 2.5 °C antes de inyectar anomalías
        tmin = np.minimum(tmin, tmax - 3.0)

        # Precipitación con fuerte componente regional + variabilidad convectiva local
        local_hit = regional_rain_event & (rng.random(n_days) < 0.85)
        local_convective = (~regional_rain_event) & is_wet_season & (rng.random(n_days) < 0.05)
        precip = np.zeros(n_days)
        precip[local_hit] = (
            regional_rain_intensity[local_hit]
            * r_factor
            * np.clip(rng.normal(1.0, 0.22, size=int(local_hit.sum())), 0.2, 2.2)
        )
        precip[local_convective] = rng.gamma(shape=1.2, scale=4.0, size=int(local_convective.sum())) * r_factor

        # Asegurar bloque seco natural en febrero 2022 para todas las estaciones (estiaje normal)
        feb_2022_mask = (fechas >= "2022-02-01") & (fechas <= "2022-02-25")
        precip[feb_2022_mask] = 0.0

        # Asegurar lluvias regionales reales en julio 2022 para poder probar bloque de ceros sospechoso
        jul_2022_rain_days = pd.date_range("2022-07-05", "2022-07-22", freq="2D")
        jul_mask = fechas.isin(jul_2022_rain_days)
        precip[jul_mask] = np.maximum(precip[jul_mask], np.round(8.5 * r_factor, 2))

        df_st = pd.DataFrame(
            {
                "id_estacion": meta["id_estacion"],
                "fecha": fechas,
                "precipitacion": np.round(np.maximum(precip, 0.0), 2),
                "tmax": np.round(tmax, 2),
                "tmin": np.round(tmin, 2),
            }
        )
        records.append(df_st)

    series = pd.concat(records, ignore_index=True)

    ground_truth: dict[str, Any] = {
        "injected_gaps": [],
        "injected_homogeneity_breaks": [],
        "injected_qc_anomalies": [],
        "dry_season_normal_zero_window": {
            "id_estacion": "GTO_005",
            "start": "2022-02-01",
            "end": "2022-02-25",
        },
    }

    # 1. Quiebres de homogeneidad inyectados (antes de huecos y QC)
    if inject_homogeneity_breaks:
        # Cambio de escalón en Tmax de GTO_002 (+2.8 °C desde 2021-07-01)
        m_tmax = (series["id_estacion"] == "GTO_002") & (series["fecha"] >= "2021-07-01")
        series.loc[m_tmax, "tmax"] = np.round(series.loc[m_tmax, "tmax"] + 2.8, 2)
        ground_truth["injected_homogeneity_breaks"].append(
            {
                "id_estacion": "GTO_002",
                "variable": "tmax",
                "break_date": "2021-07-01",
                "type": "additive_step",
                "magnitude": 2.8,
            }
        )

        # Caída de captación de lluvia en GTO_004 (factor 0.50 desde 2021-06-01 -> doble masa + SNHT/Pettitt)
        m_prec = (series["id_estacion"] == "GTO_004") & (series["fecha"] >= "2021-06-01")
        series.loc[m_prec, "precipitacion"] = np.round(series.loc[m_prec, "precipitacion"] * 0.50, 2)
        ground_truth["injected_homogeneity_breaks"].append(
            {
                "id_estacion": "GTO_004",
                "variable": "precipitacion",
                "break_date": "2021-06-01",
                "type": "multiplicative_catch_drop",
                "factor": 0.50,
            }
        )

    # 2. Huecos controlados: cortos (1-3d), medios (4-30d) y largos (>30d)
    if inject_gaps:
        gap_specs = [
            # Cortos (1-3 días)
            ("GTO_001", "precipitacion", "2020-07-10", 2, "corto"),
            ("GTO_001", "tmax", "2021-03-14", 3, "corto"),
            ("GTO_003", "tmin", "2022-11-05", 1, "corto"),
            # Medios (4-30 días)
            ("GTO_001", "precipitacion", "2021-08-01", 12, "medio"),
            ("GTO_006", "tmax", "2020-05-10", 18, "medio"),
            ("GTO_007", "tmin", "2023-01-15", 10, "medio"),
            # Largos (>30 días)
            ("GTO_006", "precipitacion", "2022-06-01", 45, "largo"),
            ("GTO_008", "tmax", "2021-09-01", 50, "largo"),
            ("GTO_008", "tmin", "2021-09-01", 50, "largo"),
        ]
        for st_id, var, start_str, length, cat in gap_specs:
            start_dt = pd.Timestamp(start_str)
            end_dt = start_dt + pd.Timedelta(days=length - 1)
            mask = (
                (series["id_estacion"] == st_id)
                & (series["fecha"] >= start_dt)
                & (series["fecha"] <= end_dt)
            )
            series.loc[mask, var] = np.nan
            ground_truth["injected_gaps"].append(
                {
                    "id_estacion": st_id,
                    "variable": var,
                    "start_date": start_dt.strftime("%Y-%m-%d"),
                    "end_date": end_dt.strftime("%Y-%m-%d"),
                    "length_days": length,
                    "category": cat,
                }
            )

    # 3. Anomalías controladas de Control de Calidad (QC)
    if inject_qc_anomalies:
        def _set_val(st_id: str, date_str: str, col: str, val: float) -> None:
            m = (series["id_estacion"] == st_id) & (series["fecha"] == pd.Timestamp(date_str))
            series.loc[m, col] = val

        # 3a. Precipitación negativa
        _set_val("GTO_001", "2020-06-15", "precipitacion", -4.5)
        ground_truth["injected_qc_anomalies"].append(
            {"id_estacion": "GTO_001", "fecha": "2020-06-15", "variable": "precipitacion", "rule": "PRECIP_NEGATIVE"}
        )

        # 3b. Inversión térmica Tmax <= Tmin
        _set_val("GTO_001", "2020-04-10", "tmax", 12.0)
        _set_val("GTO_001", "2020-04-10", "tmin", 18.5)
        ground_truth["injected_qc_anomalies"].append(
            {"id_estacion": "GTO_001", "fecha": "2020-04-10", "variable": "tmax", "rule": "TEMP_INVERSION"}
        )

        # 3c. Valores físicamente imposibles / fuera de rango
        _set_val("GTO_003", "2020-05-20", "tmax", 64.0)
        _set_val("GTO_003", "2020-12-12", "tmin", -28.0)
        _set_val("GTO_007", "2020-08-18", "precipitacion", 420.0)
        ground_truth["injected_qc_anomalies"].extend(
            [
                {"id_estacion": "GTO_003", "fecha": "2020-05-20", "variable": "tmax", "rule": "OUT_OF_RANGE"},
                {"id_estacion": "GTO_003", "fecha": "2020-12-12", "variable": "tmin", "rule": "OUT_OF_RANGE"},
                {"id_estacion": "GTO_007", "fecha": "2020-08-18", "variable": "precipitacion", "rule": "OUT_OF_RANGE"},
            ]
        )

        # 3d. Amplitud térmica diurna implausible (> 35 °C y < 0.5 °C)
        _set_val("GTO_005", "2021-04-02", "tmax", 41.0)
        _set_val("GTO_005", "2021-04-02", "tmin", 2.0)
        _set_val("GTO_005", "2021-04-12", "tmax", 20.1)
        _set_val("GTO_005", "2021-04-12", "tmin", 20.0)
        ground_truth["injected_qc_anomalies"].extend(
            [
                {"id_estacion": "GTO_005", "fecha": "2021-04-02", "variable": "tmax", "rule": "DIURNAL_RANGE_IMPLAUSIBLE"},
                {"id_estacion": "GTO_005", "fecha": "2021-04-12", "variable": "tmax", "rule": "DIURNAL_RANGE_IMPLAUSIBLE"},
            ]
        )

        # 3e. Sensor atascado en temperatura (6 días consecutivos idénticos en GTO_003)
        stuck_dates = pd.date_range("2021-10-10", periods=6, freq="D")
        m_stuck = (series["id_estacion"] == "GTO_003") & (series["fecha"].isin(stuck_dates))
        series.loc[m_stuck, "tmax"] = 24.30
        ground_truth["injected_qc_anomalies"].append(
            {
                "id_estacion": "GTO_003",
                "start_date": "2021-10-10",
                "end_date": "2021-10-15",
                "variable": "tmax",
                "rule": "STUCK_SENSOR_TEMP",
            }
        )

        # 3f. Bloque sospechoso de ceros en precipitación en temporada húmeda (julio 2022 en GTO_005)
        wet_zero_dates = pd.date_range("2022-07-05", "2022-07-22", freq="D")
        m_wz = (series["id_estacion"] == "GTO_005") & (series["fecha"].isin(wet_zero_dates))
        series.loc[m_wz, "precipitacion"] = 0.0
        ground_truth["injected_qc_anomalies"].append(
            {
                "id_estacion": "GTO_005",
                "start_date": "2022-07-05",
                "end_date": "2022-07-22",
                "variable": "precipitacion",
                "rule": "SUSPICIOUS_ZERO_PRECIP_WET",
            }
        )

        # 3g. Salto térmico extremo de un día a otro (+19 °C en tmin de GTO_001, manteniendo tmax > tmin)
        _set_val("GTO_001", "2022-03-15", "tmax", 34.0)
        _set_val("GTO_001", "2022-03-15", "tmin", 29.0)
        ground_truth["injected_qc_anomalies"].append(
            {"id_estacion": "GTO_001", "fecha": "2022-03-15", "variable": "tmin", "rule": "EXTREME_JUMP_OUTLIER"}
        )

    return SyntheticBenchmark(
        estaciones=estaciones,
        series_diarias=series,
        ground_truth=ground_truth,
    )
