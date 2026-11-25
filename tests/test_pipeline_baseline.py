"""Pruebas de carga con fallback, diagnóstico, restricciones físicas y baseline sin fuga."""

import pandas as pd

from src.config import PROJECT_ROOT, load_settings
from src.pipeline.baseline import evaluate_linear_baseline_no_leakage, run_linear_baseline
from src.pipeline.data_loader import load_climate_datasets
from src.pipeline.data_verifier import inspect_dataset


def test_loader_fallback_and_inspection() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    loaded = load_climate_datasets(settings=settings, root=PROJECT_ROOT, allow_synthetic_fallback=True)
    assert loaded.source in ("official", "synthetic_fallback")
    assert not loaded.estaciones.empty
    assert not loaded.series_diarias.empty

    report = inspect_dataset(loaded.estaciones, loaded.series_diarias, settings=settings)
    assert report["estaciones_count"] >= 1
    assert report["series_rows"] >= 1
    assert "precipitacion" in report["missing_pct_by_variable"]


def test_baseline_enforces_physical_constraints_and_flags() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    df = pd.DataFrame(
        {
            "id_estacion": ["E1"] * 5,
            "fecha": pd.date_range("2024-01-01", periods=5, freq="D"),
            "precipitacion": [0.0, None, 4.0, None, 2.0],
            "tmax": [25.0, None, 27.0, 20.0, 26.0],
            "tmin": [10.0, None, 12.0, 11.0, 10.0],
        }
    )
    out = run_linear_baseline(df, settings=settings)
    assert (out["precipitacion"].dropna() >= 0.0).all()
    both = out["tmax"].notna() & out["tmin"].notna()
    assert (out.loc[both, "tmax"] > out.loc[both, "tmin"]).all()
    assert out.loc[0, "precipitacion_flag"] == "observado"
    assert out.loc[1, "precipitacion_flag"] == "imputado_baseline"


def test_baseline_evaluation_no_leakage() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    loaded = load_climate_datasets(settings=settings, root=PROJECT_ROOT, allow_synthetic_fallback=True)
    metrics = evaluate_linear_baseline_no_leakage(loaded.series_diarias, settings=settings)
    assert metrics["method"] == "linear_interpolation"
    for var in ("precipitacion", "tmax", "tmin"):
        var_m = metrics["metrics_by_variable"][var]
        assert var_m["n_eval"] > 0
        assert var_m["mae"] is not None
        assert var_m["rmse"] is not None
