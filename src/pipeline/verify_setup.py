"""Script CLI de verificación de entorno, archivos oficiales y línea base inicial."""

from __future__ import annotations

import json
from pathlib import Path

from src.config import PROJECT_ROOT, load_settings
from src.pipeline.baseline import evaluate_linear_baseline_no_leakage
from src.pipeline.data_loader import load_climate_datasets
from src.pipeline.data_verifier import inspect_dataset


def main() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    print(f"=== Verificación {settings.project.name} v{settings.project.version} ===")

    file_status = settings.check_official_files(root=PROJECT_ROOT)
    print("\n1. Estado de archivos configurados:")
    for name, info in file_status.items():
        mark = "[OK]" if info["exists"] else "[FALTA]"
        print(f"  {mark:7s} {name:18s} -> {info['path']}")

    loaded = load_climate_datasets(settings=settings, root=PROJECT_ROOT, allow_synthetic_fallback=True)
    print(f"\n2. Fuente de datos utilizada: {loaded.source}")
    if loaded.missing_official_files:
        print(
            "   Aviso: faltan archivos oficiales en data/raw/: "
            + ", ".join(loaded.missing_official_files)
        )

    report = inspect_dataset(loaded.estaciones, loaded.series_diarias, settings=settings)
    print("\n3. Diagnóstico inicial:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    baseline_metrics = evaluate_linear_baseline_no_leakage(loaded.series_diarias, settings=settings)
    print("\n4. Métricas de línea base (interpolación lineal sin fuga de datos):")
    print(json.dumps(baseline_metrics, indent=2, ensure_ascii=False))

    out_dir = settings.paths.processed_path(root=PROJECT_ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = Path(out_dir) / "baseline_verification_report.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "data_source": loaded.source,
                "missing_official_files": loaded.missing_official_files,
                "dataset_report": report,
                "baseline_metrics": baseline_metrics,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nReporte guardado en: {summary_path}")


if __name__ == "__main__":
    main()
