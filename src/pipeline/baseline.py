"""Línea base inicial (interpolación lineal temporal) con trazabilidad y restricciones físicas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config import Settings, load_settings


def _enforce_physical_constraints(df: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    """Aplica restricciones físicas no negociables: P >= 0 y Tmax > Tmin."""
    out = df.copy()
    if "precipitacion" in out.columns:
        out["precipitacion"] = out["precipitacion"].clip(lower=cfg.physical_constraints.precip_min)

    if cfg.physical_constraints.enforce_tmax_gt_tmin and {"tmax", "tmin"}.issubset(out.columns):
        invalid = out["tmax"].notna() & out["tmin"].notna() & (out["tmax"] <= out["tmin"])
        if invalid.any():
            # Si una estimación viola Tmax > Tmin, nos abstenemos en los valores imputados conflictivos
            if "tmax_flag" in out.columns:
                imputed_tmax = invalid & (out["tmax_flag"] == "imputado_baseline")
                out.loc[imputed_tmax, "tmax"] = np.nan
                out.loc[imputed_tmax, "tmax_flag"] = "abstenido_fisica"
            if "tmin_flag" in out.columns:
                imputed_tmin = invalid & (out["tmin_flag"] == "imputado_baseline")
                out.loc[imputed_tmin, "tmin"] = np.nan
                out.loc[imputed_tmin, "tmin_flag"] = "abstenido_fisica"
    return out


def run_linear_baseline(
    series_diarias: pd.DataFrame,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Ejecuta interpolación lineal por estación con límite de hueco (abstención) y banderas."""
    cfg = settings or load_settings()
    id_col = cfg.data_schema.station_id_col
    date_col = cfg.data_schema.date_col
    variables = [v for v in cfg.data_schema.variables if v in series_diarias.columns]
    max_gap = cfg.baseline.max_gap_days

    df = series_diarias.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values([id_col, date_col]).reset_index(drop=True)

    result_frames: list[pd.DataFrame] = []
    for _, grp in df.groupby(id_col, sort=False):
        g = grp.copy()
        for var in variables:
            was_missing = g[var].isna()
            interpolated = g[var].interpolate(
                method="linear",
                limit=max_gap,
                limit_area="inside",
            )
            flag_col = f"{var}_flag"
            flags = np.where(
                ~was_missing,
                "observado",
                np.where(interpolated.notna(), "imputado_baseline", "abstenido"),
            )
            g[var] = interpolated
            g[flag_col] = flags
        result_frames.append(g)

    combined = pd.concat(result_frames, ignore_index=True)
    return _enforce_physical_constraints(combined, cfg)


def evaluate_linear_baseline_no_leakage(
    series_diarias: pd.DataFrame,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Evalúa la línea base enmascarando observaciones reales sin fuga de datos.

    Enmascara aleatoriamente una fracción configurable de valores observados,
    ejecuta la interpolación lineal únicamente sobre los datos no enmascarados
    y calcula MAE, RMSE y tasa de cobertura/abstención por variable.
    """
    cfg = settings or load_settings()
    rng = np.random.default_rng(cfg.baseline.random_seed)
    mask_frac = cfg.baseline.validation_mask_fraction
    variables = [v for v in cfg.data_schema.variables if v in series_diarias.columns]

    masked_df = series_diarias.copy()
    ground_truth_masks: dict[str, pd.Series] = {}

    for var in variables:
        obs_idx = masked_df.index[masked_df[var].notna()].to_numpy()
        n_mask = max(1, int(len(obs_idx) * mask_frac)) if len(obs_idx) > 0 else 0
        chosen = rng.choice(obs_idx, size=n_mask, replace=False) if n_mask > 0 else np.array([], dtype=int)
        eval_mask = pd.Series(False, index=masked_df.index)
        eval_mask.iloc[chosen] = True
        ground_truth_masks[var] = eval_mask
        masked_df.loc[eval_mask, var] = np.nan

    imputed_df = run_linear_baseline(masked_df, settings=cfg)

    metrics: dict[str, dict[str, Any]] = {}
    for var in variables:
        eval_mask = ground_truth_masks[var]
        y_true = series_diarias.loc[eval_mask, var]
        y_pred = imputed_df.loc[eval_mask, var]

        valid = y_pred.notna() & y_true.notna()
        n_total = int(eval_mask.sum())
        n_imputed = int(valid.sum())
        n_abstained = n_total - n_imputed

        if n_imputed > 0:
            err = y_pred[valid] - y_true[valid]
            mae = float(np.mean(np.abs(err)))
            rmse = float(np.sqrt(np.mean(err**2)))
        else:
            mae = float("nan")
            rmse = float("nan")

        metrics[var] = {
            "n_eval": n_total,
            "n_imputed": n_imputed,
            "n_abstained": n_abstained,
            "coverage_pct": round((n_imputed / n_total * 100.0) if n_total else 0.0, 2),
            "mae": round(mae, 4) if not np.isnan(mae) else None,
            "rmse": round(rmse, 4) if not np.isnan(rmse) else None,
        }

    return {
        "method": cfg.baseline.method,
        "max_gap_days": cfg.baseline.max_gap_days,
        "validation_mask_fraction": mask_frac,
        "random_seed": cfg.baseline.random_seed,
        "metrics_by_variable": metrics,
    }
