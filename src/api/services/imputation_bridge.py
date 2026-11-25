"""Puente desacoplado entre el Backend FastAPI y el motor ML de imputación."""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime
from typing import Any

# TODO(Fase 4): Reemplazar stub con importación real de src.pipeline.inference.predict_on_demand


def _parse_date(raw_fecha: Any) -> date:
    if isinstance(raw_fecha, datetime):
        return raw_fecha.date()
    if isinstance(raw_fecha, date):
        return raw_fecha
    return date.fromisoformat(str(raw_fecha))


def _station_bias(station_id: str) -> float:
    digest = hashlib.sha256(station_id.encode("utf-8")).hexdigest()
    return (int(digest[:4], 16) % 200 - 100) / 100.0  # [-1.0, 0.99]


def enforce_physical_bounds(
    variable: str,
    value: float,
    reference_tmax: float | None = None,
    reference_tmin: float | None = None,
) -> float:
    """Garantiza restricciones físicas: precipitación >= 0 y Tmax > Tmin."""
    if variable == "precipitacion":
        return round(max(0.0, value), 2)
    if variable == "tmax":
        floor_val = (reference_tmin + 2.0) if reference_tmin is not None else 18.0
        return round(min(46.0, max(floor_val, value)), 2)
    if variable == "tmin":
        ceil_val = (reference_tmax - 2.0) if reference_tmax is not None else 17.0
        return round(max(-8.0, min(ceil_val, value)), 2)
    return round(value, 2)


def _climatology_estimate(station_id: str, variable: str, day: date) -> float:
    doy = day.timetuple().tm_yday
    season = math.sin(2.0 * math.pi * (doy - 30) / 365.0)
    bias = _station_bias(station_id)
    is_wet = 6 <= day.month <= 10

    if variable == "precipitacion":
        base = (4.8 + 3.2 * math.cos(doy / 7.0)) if is_wet else (0.6 + 0.4 * max(0.0, math.sin(doy / 5.0)))
        return enforce_physical_bounds("precipitacion", base + 0.5 * bias)
    if variable == "tmax":
        return enforce_physical_bounds("tmax", 26.5 + 3.8 * season + bias)
    if variable == "tmin":
        return enforce_physical_bounds("tmin", 10.2 + 4.0 * season + 0.6 * bias)
    return 0.0


def _gap_run_lengths(sorted_records: list[tuple[date, float | None]]) -> list[int]:
    n = len(sorted_records)
    lengths = [0] * n
    i = 0
    while i < n:
        if sorted_records[i][1] is not None:
            i += 1
            continue
        j = i
        while j < n and sorted_records[j][1] is None:
            j += 1
        run_len = j - i
        for k in range(i, j):
            lengths[k] = run_len
        i = j
    return lengths


def predict_on_demand(station_id: str, variable: str, records: list[dict]) -> list[dict]:
    """Simula imputaciones diarias realistas respetando restricciones físicas e incertidumbre."""
    if not records:
        return []

    parsed: list[tuple[date, float | None]] = sorted(
        ((_parse_date(rec["fecha"]), rec.get("valor")) for rec in records),
        key=lambda item: item[0],
    )
    run_lengths = _gap_run_lengths(parsed)
    observed_indices = [idx for idx, (_, val) in enumerate(parsed) if val is not None]

    results: list[dict] = []
    for idx, (day, raw_val) in enumerate(parsed):
        fecha_str = day.isoformat()
        if raw_val is not None:
            obs_val = round(float(raw_val), 2)
            if variable == "precipitacion":
                obs_val = max(0.0, obs_val)
            results.append(
                {
                    "fecha": fecha_str,
                    "valor_observado": obs_val,
                    "valor_estimado": None,
                    "es_estimado": False,
                    "bandera_calidad": "observado",
                    "incertidumbre_90": None,
                }
            )
            continue

        run_len = run_lengths[idx]
        if run_len > 30:
            results.append(
                {
                    "fecha": fecha_str,
                    "valor_observado": None,
                    "valor_estimado": None,
                    "es_estimado": False,
                    "bandera_calidad": "no_estimable",
                    "incertidumbre_90": None,
                }
            )
            continue

        bandera = "estimado_alta_confianza" if run_len <= 3 else "estimado_baja_confianza"

        left_idx = max((i for i in observed_indices if i < idx), default=None)
        right_idx = min((i for i in observed_indices if i > idx), default=None)

        clim_est = _climatology_estimate(station_id, variable, day)
        if left_idx is not None and right_idx is not None:
            left_val = float(parsed[left_idx][1])  # type: ignore[arg-type]
            right_val = float(parsed[right_idx][1])  # type: ignore[arg-type]
            weight = (idx - left_idx) / (right_idx - left_idx)
            interp = left_val + weight * (right_val - left_val)
            est = 0.65 * interp + 0.35 * clim_est
        elif left_idx is not None:
            est = 0.55 * float(parsed[left_idx][1]) + 0.45 * clim_est  # type: ignore[arg-type]
        elif right_idx is not None:
            est = 0.55 * float(parsed[right_idx][1]) + 0.45 * clim_est  # type: ignore[arg-type]
        else:
            est = clim_est

        est = enforce_physical_bounds(variable, est)

        if variable == "precipitacion":
            half_width = 2.8 if bandera == "estimado_alta_confianza" else 5.2
            inf = round(max(0.0, est - half_width), 2)
            sup = round(est + half_width, 2)
        else:
            half_width = 1.5 if bandera == "estimado_alta_confianza" else 3.1
            inf = round(est - half_width, 2)
            sup = round(est + half_width, 2)

        results.append(
            {
                "fecha": fecha_str,
                "valor_observado": None,
                "valor_estimado": est,
                "es_estimado": True,
                "bandera_calidad": bandera,
                "incertidumbre_90": [inf, sup],
            }
        )

    return results
