"""Pruebas unitarias para SNHT, Pettitt, Curva de Doble Masa y análisis de homogeneidad."""

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, load_settings
from src.pipeline.homogeneity import (
    double_mass_curve_test,
    pettitt_test,
    run_homogeneity_analysis,
    snht_test,
)
from src.pipeline.synthetic_data import generate_guanajuato_diagnostic_benchmark


def test_snht_and_pettitt_detect_clear_step_break() -> None:
    rng = np.random.default_rng(123)
    series = np.concatenate([rng.normal(0.0, 0.5, 30), rng.normal(2.5, 0.5, 30)])

    snht = snht_test(series, min_segment=6, n_simulations=300, seed=42)
    pettitt = pettitt_test(series, min_segment=6)

    assert snht["p_value"] < 0.01
    assert pettitt["p_value"] < 0.01
    assert abs(snht["break_index"] - 30) <= 2
    assert abs(pettitt["break_index"] - 30) <= 2


def test_double_mass_curve_detects_slope_change() -> None:
    rng = np.random.default_rng(7)
    ref = rng.gamma(shape=2.0, scale=30.0, size=60)
    target = np.concatenate(
        [
            ref[:30] * 1.0 + rng.normal(0.0, 2.0, 30),
            ref[30:] * 0.5 + rng.normal(0.0, 2.0, 30),
        ]
    )
    target = np.maximum(target, 0.0)

    dm = double_mass_curve_test(target, ref, min_segment=6)
    assert dm["p_value"] < 0.01
    assert dm["relative_slope_change"] > 0.35
    assert dm["slope_after"] < dm["slope_before"]
    assert abs(dm["break_index"] - 30) <= 2


def test_homogeneity_analysis_on_guanajuato_benchmark() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    bench = generate_guanajuato_diagnostic_benchmark(
        seed=42,
        inject_gaps=True,
        inject_homogeneity_breaks=True,
        inject_qc_anomalies=False,
    )
    report = run_homogeneity_analysis(bench.series_diarias, estaciones=bench.estaciones, settings=settings)
    tbl = report.results_table

    # 1. GTO_002 tmax (+2.8 °C desde 2021-07-01) debe clasificarse como no_homogenea y penalizarse
    r_gto2_tmax = tbl[(tbl["id_estacion"] == "GTO_002") & (tbl["variable"] == "tmax")].iloc[0]
    assert r_gto2_tmax["classification"] == "no_homogenea"
    assert r_gto2_tmax["donor_weight"] < 0.5
    assert r_gto2_tmax["probable_break_date"] is not None
    break_dt_tmax = pd.Timestamp(r_gto2_tmax["probable_break_date"])
    assert abs((break_dt_tmax - pd.Timestamp("2021-07-01")).days) <= 65

    # 2. GTO_004 precipitacion (caída 0.5x desde 2021-06-01) debe clasificarse como no_homogenea
    r_gto4_prec = tbl[(tbl["id_estacion"] == "GTO_004") & (tbl["variable"] == "precipitacion")].iloc[0]
    assert r_gto4_prec["classification"] == "no_homogenea"
    assert r_gto4_prec["donor_weight"] < 0.5
    assert r_gto4_prec["double_mass_p_value"] < 0.05
    assert r_gto4_prec["double_mass_slope_change"] >= 0.15

    # 3. Estación sin quiebre (GTO_001 tmax y precipitacion) debe quedar homogénea con peso 1.0
    r_gto1_tmax = tbl[(tbl["id_estacion"] == "GTO_001") & (tbl["variable"] == "tmax")].iloc[0]
    assert r_gto1_tmax["classification"] == "homogenea"
    assert r_gto1_tmax["donor_weight"] == 1.0
