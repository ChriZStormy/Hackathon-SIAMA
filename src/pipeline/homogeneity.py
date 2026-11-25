"""Módulo de Análisis de Homogeneidad (SNHT, Pettitt y Curva de Doble Masa relativa).

Evalúa la homogeneidad de series mensuales/anuales respecto a una serie de referencia
construida a partir de estaciones vecinas correlacionadas, clasificando cada serie en
``homogenea``, ``sospechosa`` o ``no_homogenea`` y asignando un peso de penalización
para evitar que estaciones con quiebres contaminen a vecinas como donadoras.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from src.config import Settings, load_settings


@dataclass
class HomogeneityReport:
    results_table: pd.DataFrame
    donor_weights: dict[str, dict[str, float]]

    def to_summary_dict(self) -> dict[str, Any]:
        counts = (
            self.results_table["classification"].value_counts().to_dict()
            if not self.results_table.empty
            else {}
        )
        return {
            "total_series_evaluated": int(len(self.results_table)),
            "classification_counts": {
                "homogenea": int(counts.get("homogenea", 0)),
                "sospechosa": int(counts.get("sospechosa", 0)),
                "no_homogenea": int(counts.get("no_homogenea", 0)),
                "insuficiente": int(counts.get("insuficiente", 0)),
            },
            "donor_weights": self.donor_weights,
            "details": self.results_table.to_dict(orient="records"),
        }


def snht_test(
    values: np.ndarray,
    min_segment: int = 6,
    n_simulations: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Standard Normal Homogeneity Test (Alexandersson, 1986) con p-valor Monte Carlo."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 2 * min_segment + 1 or np.nanstd(x) < 1e-12:
        return {"statistic": 0.0, "p_value": 1.0, "break_index": None}

    z = (x - np.mean(x)) / np.std(x, ddof=1)
    cumsum = np.cumsum(z)
    total = cumsum[-1]

    ks = np.arange(min_segment, n - min_segment + 1)
    z1 = cumsum[ks - 1] / ks
    z2 = (total - cumsum[ks - 1]) / (n - ks)
    t_vals = ks * (z1**2) + (n - ks) * (z2**2)

    best_pos = int(np.argmax(t_vals))
    t0 = float(t_vals[best_pos])
    break_idx = int(ks[best_pos])

    # Simulación Monte Carlo vectorizada bajo H0 (normal estándar i.i.d.)
    rng = np.random.default_rng(seed)
    sim = rng.standard_normal((n_simulations, n))
    sim = (sim - sim.mean(axis=1, keepdims=True)) / np.maximum(
        sim.std(axis=1, ddof=1, keepdims=True), 1e-12
    )
    sim_cs = np.cumsum(sim, axis=1)
    sim_total = sim_cs[:, -1:]
    sim_z1 = sim_cs[:, ks - 1] / ks[None, :]
    sim_z2 = (sim_total - sim_cs[:, ks - 1]) / (n - ks)[None, :]
    sim_t = ks[None, :] * (sim_z1**2) + (n - ks)[None, :] * (sim_z2**2)
    sim_t0 = sim_t.max(axis=1)

    p_value = float((np.sum(sim_t0 >= t0) + 1) / (n_simulations + 1))
    return {"statistic": round(t0, 4), "p_value": round(p_value, 4), "break_index": break_idx}


def pettitt_test(values: np.ndarray, min_segment: int = 6) -> dict[str, Any]:
    """Prueba no paramétrica de cambio de punto de Pettitt (1979)."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 2 * min_segment + 1 or np.nanstd(x) < 1e-12:
        return {"statistic": 0.0, "p_value": 1.0, "break_index": None}

    # Matriz de signos sgn(x_i - x_j)
    diff = x[:, None] - x[None, :]
    sgn = np.sign(diff)
    # U_t = sum_{i=0..t-1} sum_{j=t..n-1} sgn(x_i - x_j)
    # Se calcula de forma exacta y eficiente usando sumas acumuladas por fila
    row_sums = sgn.sum(axis=1)
    # Nota matemática: sum_{i<t, j>=t} sgn(x_i - x_j) = sum_{i<t} sum_{j=0..n-1} sgn(x_i - x_j)
    # ya que la submatriz superior izquierda (i<t, j<t) es antisimétrica y suma 0.
    u_all = np.cumsum(row_sums)[:-1]

    valid_slice = slice(min_segment - 1, n - min_segment)
    u_valid = u_all[valid_slice]
    best_rel = int(np.argmax(np.abs(u_valid)))
    k_stat = float(np.abs(u_valid[best_rel]))
    break_idx = int(min_segment + best_rel)

    p_value = float(min(1.0, 2.0 * np.exp((-6.0 * (k_stat**2)) / (n**3 + n**2))))
    return {"statistic": round(k_stat, 4), "p_value": round(p_value, 4), "break_index": break_idx}


def double_mass_curve_test(
    target_monthly: np.ndarray,
    ref_monthly: np.ndarray,
    min_segment: int = 6,
) -> dict[str, Any]:
    """Curva de doble masa automatizada para precipitación frente a vecinos de referencia.

    Calcula las pendientes acumuladas antes y después del punto óptimo de ruptura
    y evalúa la significancia del cambio de pendiente mediante prueba F de Chow
    sobre los incrementos mensuales (evitando inflación artificial por autocorrelación).
    """
    y = np.asarray(target_monthly, dtype=float)
    x = np.asarray(ref_monthly, dtype=float)
    n = len(y)
    if n < 2 * min_segment + 2 or np.sum(x) <= 0:
        return {
            "break_index": None,
            "slope_before": None,
            "slope_after": None,
            "slope_ratio": None,
            "relative_slope_change": 0.0,
            "f_statistic": 0.0,
            "p_value": 1.0,
        }

    # Filtrar meses con lluvia de referencia para la regresión incremental sin división por 0
    # manteniendo el mapeo al índice original.
    y_cum = np.cumsum(y)
    x_cum = np.cumsum(x)

    # Búsqueda del punto de quiebre óptimo minimizando RSS en la relación incremental y = b * x
    # bajo dos pendientes (b1 antes de k, b2 desde k).
    b_full = float(np.dot(x, y) / max(np.dot(x, x), 1e-12))
    rss_full = float(np.sum((y - b_full * x) ** 2))

    best_k: int | None = None
    best_rss = np.inf
    best_b1 = b_full
    best_b2 = b_full

    for k in range(min_segment, n - min_segment + 1):
        x1, y1 = x[:k], y[:k]
        x2, y2 = x[k:], y[k:]
        denom1 = float(np.dot(x1, x1))
        denom2 = float(np.dot(x2, x2))
        if denom1 <= 1e-9 or denom2 <= 1e-9:
            continue
        b1 = float(np.dot(x1, y1) / denom1)
        b2 = float(np.dot(x2, y2) / denom2)
        rss_split = float(np.sum((y1 - b1 * x1) ** 2) + np.sum((y2 - b2 * x2) ** 2))
        if rss_split < best_rss:
            best_rss = rss_split
            best_k = k
            best_b1 = b1
            best_b2 = b2

    if best_k is None or best_rss <= 0.0:
        return {
            "break_index": None,
            "slope_before": round(b_full, 4),
            "slope_after": round(b_full, 4),
            "slope_ratio": 1.0,
            "relative_slope_change": 0.0,
            "f_statistic": 0.0,
            "p_value": 1.0,
        }

    # Estadístico F de Chow (df1 = 1 parámetro extra de pendiente, df2 = n - 2)
    df2 = max(n - 2, 1)
    f_stat = max(0.0, ((rss_full - best_rss) / 1.0) / (best_rss / df2))
    p_value = float(1.0 - stats.f.cdf(f_stat, 1, df2))

    # Pendientes sobre la curva acumulada (razón acumulada en cada segmento)
    cum_b1 = float(y_cum[best_k - 1] / max(x_cum[best_k - 1], 1e-12))
    cum_b2 = float((y_cum[-1] - y_cum[best_k - 1]) / max(x_cum[-1] - x_cum[best_k - 1], 1e-12))
    rel_change = abs(cum_b2 - cum_b1) / max(abs(cum_b1), 1e-12)
    slope_ratio = cum_b2 / max(cum_b1, 1e-12)

    return {
        "break_index": int(best_k),
        "slope_before": round(cum_b1, 4),
        "slope_after": round(cum_b2, 4),
        "slope_ratio": round(slope_ratio, 4),
        "relative_slope_change": round(rel_change, 4),
        "f_statistic": round(f_stat, 4),
        "p_value": round(p_value, 6),
    }


def _build_monthly_pivot(
    series_diarias: pd.DataFrame,
    variable: str,
    id_col: str,
    date_col: str,
    min_valid_days: int = 20,
) -> pd.DataFrame:
    df = series_diarias[[id_col, date_col, variable]].copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[id_col, date_col])
    df["ym"] = df[date_col].dt.to_period("M").dt.to_timestamp()

    agg_func = "sum" if variable == "precipitacion" else "mean"
    grouped = df.groupby([id_col, "ym"])[variable].agg(val=agg_func, count="count").reset_index()
    grouped.loc[grouped["count"] < min_valid_days, "val"] = np.nan
    pivot = grouped.pivot(index="ym", columns=id_col, values="val").sort_index()
    return pivot


def _build_reference_series(
    pivot: pd.DataFrame,
    target_station: str,
    variable: str,
    top_k: int = 4,
) -> tuple[pd.Series, list[str]]:
    """Construye una serie mensual de referencia robusta (mediana) con vecinos correlacionados."""
    target = pivot[target_station]
    candidates = [c for c in pivot.columns if c != target_station]
    if not candidates:
        return pd.Series(dtype=float), []

    corrs: list[tuple[str, float]] = []
    for cand in candidates:
        common = pd.concat([target, pivot[cand]], axis=1).dropna()
        if len(common) < 12:
            continue
        r = float(common.iloc[:, 0].corr(common.iloc[:, 1]))
        if np.isfinite(r) and r > 0.2:
            corrs.append((cand, r))

    corrs.sort(key=lambda item: item[1], reverse=True)
    selected = [c for c, _ in corrs[:top_k]]
    if not selected:
        selected = candidates[:top_k]

    if variable == "precipitacion":
        # Escalar cada vecino a la media del objetivo para preservar escala y usar mediana robusta
        target_mean = float(target.mean()) if pd.notna(target.mean()) else 1.0
        scaled_cols = []
        for s in selected:
            s_mean = float(pivot[s].mean()) if pd.notna(pivot[s].mean()) else 1.0
            scaled_cols.append(pivot[s] * (target_mean / max(s_mean, 1e-6)))
        ref = pd.concat(scaled_cols, axis=1).median(axis=1)
    else:
        # Centrar cada vecino al sesgo del objetivo y tomar mediana (robusto ante 1 vecino con quiebre)
        target_mean = float(target.mean()) if pd.notna(target.mean()) else 0.0
        shifted_cols = [pivot[s] - float(pivot[s].mean()) + target_mean for s in selected]
        ref = pd.concat(shifted_cols, axis=1).median(axis=1)

    return ref, selected


def run_homogeneity_analysis(
    series_diarias: pd.DataFrame,
    estaciones: pd.DataFrame | None = None,
    settings: Settings | None = None,
) -> HomogeneityReport:
    """Ejecuta SNHT, Pettitt y Curva de Doble Masa relativa por estación y variable."""
    _ = estaciones  # Reservado para ponderación geográfica adicional cuando haya covariables
    cfg = settings or load_settings()
    hcfg = cfg.homogeneity
    id_col = cfg.data_schema.station_id_col
    date_col = cfg.data_schema.date_col
    variables = [v for v in cfg.data_schema.variables if v in series_diarias.columns]

    rows: list[dict[str, Any]] = []
    donor_weights: dict[str, dict[str, float]] = {}

    for var in variables:
        pivot = _build_monthly_pivot(series_diarias, var, id_col=id_col, date_col=date_col)
        for st_id in pivot.columns:
            ref_series, ref_neighbors = _build_reference_series(
                pivot,
                target_station=st_id,
                variable=var,
                top_k=hcfg.neighbor_top_k,
            )
            pair = pd.concat([pivot[st_id].rename("target"), ref_series.rename("ref")], axis=1).dropna()

            if len(pair) < hcfg.min_months:
                rows.append(
                    {
                        id_col: st_id,
                        "variable": var,
                        "n_months": int(len(pair)),
                        "reference_neighbors": ",".join(ref_neighbors),
                        "snht_stat": None,
                        "snht_p_value": None,
                        "snht_break_date": None,
                        "pettitt_stat": None,
                        "pettitt_p_value": None,
                        "pettitt_break_date": None,
                        "double_mass_p_value": None,
                        "double_mass_slope_change": None,
                        "double_mass_break_date": None,
                        "probable_break_date": None,
                        "significant_tests": 0,
                        "classification": "insuficiente",
                        "donor_weight": hcfg.donor_weights.get("sospechosa", 0.5),
                    }
                )
                donor_weights.setdefault(st_id, {})[var] = hcfg.donor_weights.get("sospechosa", 0.5)
                continue

            if var == "precipitacion":
                # Para SNHT y Pettitt en lluvia usamos razón logarítmica sobre meses con lluvia de referencia (> 5 mm)
                wet_pair = pair[pair["ref"] > 5.0]
                if len(wet_pair) >= 2 * hcfg.min_segment_months + 1:
                    rel_index = wet_pair.index
                    rel_values = np.log((wet_pair["target"].to_numpy() + 1.0) / (wet_pair["ref"].to_numpy() + 1.0))
                else:
                    rel_index = pair.index
                    rel_values = np.log((pair["target"].to_numpy() + 1.0) / (pair["ref"].to_numpy() + 1.0))

                dm = double_mass_curve_test(
                    target_monthly=pair["target"].to_numpy(),
                    ref_monthly=pair["ref"].to_numpy(),
                    min_segment=hcfg.min_segment_months,
                )
                dm_break_date = (
                    pair.index[dm["break_index"]].strftime("%Y-%m-%d")
                    if dm["break_index"] is not None and dm["break_index"] < len(pair.index)
                    else None
                )
                dm_sig = bool(
                    dm["p_value"] < hcfg.alpha
                    and dm["relative_slope_change"] >= hcfg.double_mass_slope_change_threshold
                )
            else:
                rel_index = pair.index
                rel_values = (pair["target"] - pair["ref"]).to_numpy()
                dm = {
                    "p_value": None,
                    "relative_slope_change": None,
                    "break_index": None,
                }
                dm_break_date = None
                dm_sig = False

            snht = snht_test(
                rel_values,
                min_segment=hcfg.min_segment_months,
                n_simulations=hcfg.snht_mc_simulations,
                seed=hcfg.random_seed,
            )
            pettitt = pettitt_test(rel_values, min_segment=hcfg.min_segment_months)

            snht_break_date = (
                rel_index[snht["break_index"]].strftime("%Y-%m-%d")
                if snht["break_index"] is not None and snht["break_index"] < len(rel_index)
                else None
            )
            pettitt_break_date = (
                rel_index[pettitt["break_index"]].strftime("%Y-%m-%d")
                if pettitt["break_index"] is not None and pettitt["break_index"] < len(rel_index)
                else None
            )

            snht_sig = bool(snht["p_value"] < hcfg.alpha)
            pettitt_sig = bool(pettitt["p_value"] < hcfg.alpha)

            n_sig = int(snht_sig) + int(pettitt_sig) + int(dm_sig)
            if n_sig >= 2:
                classification = "no_homogenea"
            elif n_sig == 1:
                classification = "sospechosa"
            else:
                classification = "homogenea"

            # Fecha probable de ruptura (solo si es sospechosa o no_homogenea)
            probable_break: str | None = None
            if classification != "homogenea":
                candidates_dates = [
                    d
                    for sig, d in (
                        (snht_sig, snht_break_date),
                        (pettitt_sig, pettitt_break_date),
                        (dm_sig, dm_break_date),
                    )
                    if sig and d is not None
                ]
                if candidates_dates:
                    ts_sorted = sorted(pd.Timestamp(d) for d in candidates_dates)
                    probable_break = ts_sorted[len(ts_sorted) // 2].strftime("%Y-%m-%d")

            weight = float(hcfg.donor_weights.get(classification, 0.5))
            donor_weights.setdefault(st_id, {})[var] = weight

            rows.append(
                {
                    id_col: st_id,
                    "variable": var,
                    "n_months": int(len(pair)),
                    "reference_neighbors": ",".join(ref_neighbors),
                    "snht_stat": snht["statistic"],
                    "snht_p_value": snht["p_value"],
                    "snht_break_date": snht_break_date if snht_sig else None,
                    "pettitt_stat": pettitt["statistic"],
                    "pettitt_p_value": pettitt["p_value"],
                    "pettitt_break_date": pettitt_break_date if pettitt_sig else None,
                    "double_mass_p_value": dm["p_value"],
                    "double_mass_slope_change": dm["relative_slope_change"],
                    "double_mass_break_date": dm_break_date if dm_sig else None,
                    "probable_break_date": probable_break,
                    "significant_tests": n_sig,
                    "classification": classification,
                    "donor_weight": weight,
                }
            )

    return HomogeneityReport(
        results_table=pd.DataFrame(rows),
        donor_weights=donor_weights,
    )
