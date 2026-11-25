"""Pruebas para la carga de configuración centralizada y resolución de rutas."""

from pathlib import Path

from src.config import PROJECT_ROOT, load_settings


def test_load_settings_defaults() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    assert settings.project.name == "SIAMA-Impute"
    assert settings.project.crs_epsg == 4326
    assert "precipitacion" in settings.data_schema.variables
    assert "tmax" in settings.data_schema.variables
    assert "tmin" in settings.data_schema.variables
    assert settings.physical_constraints.precip_min == 0.0
    assert settings.physical_constraints.enforce_tmax_gt_tmin is True


def test_file_paths_are_resolved_under_project_root() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    paths = settings.paths.file_paths(root=PROJECT_ROOT)
    for key in ("estaciones", "series_diarias", "covariables", "test_publico", "starter_notebook"):
        assert key in paths
        assert isinstance(paths[key], Path)
        assert paths[key].is_absolute()
        assert str(PROJECT_ROOT) in str(paths[key])


def test_check_official_files_structure() -> None:
    settings = load_settings(root=PROJECT_ROOT)
    status = settings.check_official_files(root=PROJECT_ROOT)
    assert "estaciones" in status
    assert "series_diarias" in status
    assert status["starter_notebook"]["exists"] is True
