"""Pruebas unitarias para el módulo de diagnóstico de vacíos y taxonomía de huecos."""

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, load_settings
from src.pipeline.gap_diagnostics import classify_gap_length, run_gap_diagnostics
from src.pipeline.synthetic_data import generate_guanajuato_diagnostic_benchmark


def test_classify_gap_length_boundaries() -> None:
    assert classify_gap_length(1) == "corto"
    assert classify_gap_length(3) == "corto"
    assert classify_gap_length(4) == "medio"
    assert classify_gap_length(30) == "medio"
    assert classify_gap_length(31) == "largo"
    assert classify_gap_length(60) == "largo"


def test_gap_diagnostics_detects_all_injected_categories() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    bench = generate_guanajuato_diagnostic_benchmark(
        seed=42,
        inject_gaps=True,
        inject_homogeneity_breaks=False,
        inject_qc_anomalies=False,
    )
    res = run_gap_diagnostics(bench.series_diarias, settings=settings)

    assert not res.station_variable_summary.empty
    assert not res.yearly_missing.empty
    assert not res.seasonal_missing.empty
    assert set(res.seasonal_missing["temporada"].unique()) == {"lluvias", "estiaje"}

    summary = res.to_summary_dict()
    counts = summary["gap_taxonomy_counts"]
    assert counts["corto"] == 3
    assert counts["medio"] == 3
    assert counts["largo"] == 3
    assert summary["total_gaps_detected"] == len(bench.ground_truth["injected_gaps"])

    # Verificar que GTO_006 precipitacion tiene exactamente un hueco largo de 45 días en 2022 lluvias
    gto6 = res.gaps_catalog[
        (res.gaps_catalog["id_estacion"] == "GTO_006")
        & (res.gaps_catalog["variable"] == "precipitacion")
    ]
    assert len(gto6) == 1
    assert int(gto6.iloc[0]["length_days"]) == 45
    assert gto6.iloc[0]["category"] == "largo"
    assert gto6.iloc[0]["dominant_season"] == "lluvias"


def test_gap_diagnostics_handles_implicit_missing_dates() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    # 10 días con 5 días completamente omitidos del DataFrame (hueco medio implícito)
    dates = list(pd.date_range("2023-06-01", "2023-06-03")) + list(
        pd.date_range("2023-06-09", "2023-06-11")
    )
    df = pd.DataFrame(
        {
            "id_estacion": ["E_TEST"] * len(dates),
            "fecha": dates,
            "precipitacion": [0.0, 2.0, 0.0, 1.0, 0.0, 0.0],
            "tmax": [28.0] * len(dates),
            "tmin": [14.0] * len(dates),
        }
    )
    res = run_gap_diagnostics(df, settings=settings)
    p_row = res.station_variable_summary[res.station_variable_summary["variable"] == "precipitacion"].iloc[0]
    assert int(p_row["total_days"]) == 11
    assert int(p_row["missing_days"]) == 5
    assert int(p_row["n_medio"]) == 1
    assert int(p_row["max_gap_days"]) == 5
