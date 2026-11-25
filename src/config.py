"""Cargador centralizado y tipado de configuración para SIAMA-Impute."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FilesConfig(BaseModel):
    estaciones: str = "estaciones.csv"
    series_diarias: str = "series_diarias.csv"
    covariables: str = "covariables.gpkg"
    test_publico: str = "test_publico.csv"


class PathsConfig(BaseModel):
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    external_dir: str = "data/external"
    files: FilesConfig = Field(default_factory=FilesConfig)
    starter_notebook: str = "notebooks/01_starter_and_baseline.ipynb"

    def resolve_dir(self, relative_or_abs: str, root: Path = PROJECT_ROOT) -> Path:
        p = Path(relative_or_abs)
        return p if p.is_absolute() else (root / p).resolve()

    def raw_path(self, root: Path = PROJECT_ROOT) -> Path:
        override = os.getenv("SIAMA_DATA_RAW_DIR")
        return self.resolve_dir(override or self.raw_dir, root)

    def processed_path(self, root: Path = PROJECT_ROOT) -> Path:
        override = os.getenv("SIAMA_DATA_PROCESSED_DIR")
        return self.resolve_dir(override or self.processed_dir, root)

    def external_path(self, root: Path = PROJECT_ROOT) -> Path:
        override = os.getenv("SIAMA_DATA_EXTERNAL_DIR")
        return self.resolve_dir(override or self.external_dir, root)

    def file_paths(self, root: Path = PROJECT_ROOT) -> dict[str, Path]:
        raw = self.raw_path(root)
        return {
            "estaciones": raw / self.files.estaciones,
            "series_diarias": raw / self.files.series_diarias,
            "covariables": raw / self.files.covariables,
            "test_publico": raw / self.files.test_publico,
            "starter_notebook": self.resolve_dir(self.starter_notebook, root),
        }


class ProjectConfig(BaseModel):
    name: str = "SIAMA-Impute"
    version: str = "0.2.0"
    region: str = "Guanajuato, México"
    crs_epsg: int = 4326


class DataSchemaConfig(BaseModel):
    station_id_col: str = "id_estacion"
    date_col: str = "fecha"
    lat_col: str = "latitud"
    lon_col: str = "longitud"
    alt_col: str = "altitud_m"
    variables: list[str] = Field(default_factory=lambda: ["precipitacion", "tmax", "tmin"])
    missing_value_codes: list[Any] = Field(
        default_factory=lambda: [-999, -999.0, -9999, -99.9, "NA", "N/A", "null", ""]
    )


class SeasonsConfig(BaseModel):
    lluvias_months: list[int] = Field(default_factory=lambda: [5, 6, 7, 8, 9, 10])
    estiaje_months: list[int] = Field(default_factory=lambda: [11, 12, 1, 2, 3, 4])


class PhysicalConstraintsConfig(BaseModel):
    precip_min: float = 0.0
    precip_max_plausible_mm: float = 350.0
    enforce_tmax_gt_tmin: bool = True
    temp_min_plausible_c: float = -20.0
    temp_max_plausible_c: float = 55.0
    diurnal_range_min_c: float = 0.5
    diurnal_range_max_c: float = 35.0


class GapDiagnosticsConfig(BaseModel):
    short_max_days: int = 3
    medium_max_days: int = 30


class QCConfig(BaseModel):
    stuck_temp_min_days: int = 5
    wet_zero_precip_min_days: int = 10
    wet_zero_neighbor_min_rain_days: int = 4
    wet_zero_neighbor_min_cum_mm: float = 20.0
    neighbor_top_k: int = 4
    neighbor_min_corr: float = 0.25
    max_daily_temp_jump_c: float = 15.0
    temp_mad_z_threshold: float = 6.0


class HomogeneityConfig(BaseModel):
    alpha: float = 0.05
    min_months: int = 24
    min_segment_months: int = 6
    snht_mc_simulations: int = 500
    double_mass_slope_change_threshold: float = 0.15
    neighbor_top_k: int = 4
    donor_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "homogenea": 1.0,
            "sospechosa": 0.5,
            "no_homogenea": 0.1,
        }
    )
    random_seed: int = 42


class BaselineConfig(BaseModel):
    method: str = "linear_interpolation"
    max_gap_days: int = 7
    validation_mask_fraction: float = 0.10
    random_seed: int = 42


class DatabaseConfig(BaseModel):
    user: str = "siama_user"
    password: str = "siama_dev_password"
    db: str = "siama_impute"
    host: str = "localhost"
    port: int = 5432

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class Settings(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    data_schema: DataSchemaConfig = Field(default_factory=DataSchemaConfig)
    seasons: SeasonsConfig = Field(default_factory=SeasonsConfig)
    physical_constraints: PhysicalConstraintsConfig = Field(
        default_factory=PhysicalConstraintsConfig
    )
    gap_diagnostics: GapDiagnosticsConfig = Field(default_factory=GapDiagnosticsConfig)
    qc: QCConfig = Field(default_factory=QCConfig)
    homogeneity: HomogeneityConfig = Field(default_factory=HomogeneityConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    def check_official_files(self, root: Path = PROJECT_ROOT) -> dict[str, dict[str, Any]]:
        """Verifica la presencia de los archivos oficiales en data/raw/."""
        paths = self.paths.file_paths(root)
        status: dict[str, dict[str, Any]] = {}
        for key, path in paths.items():
            status[key] = {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        return status


def load_settings(
    config_path: str | Path | None = None,
    root: Path = PROJECT_ROOT,
) -> Settings:
    """Carga la configuración desde YAML y sobrescribe valores de DB con .env."""
    load_dotenv(root / ".env", override=False)

    env_cfg = os.getenv("SIAMA_CONFIG_PATH")
    target = Path(config_path or env_cfg or "config/settings.yaml")
    if not target.is_absolute():
        target = (root / target).resolve()

    raw_data: dict[str, Any] = {}
    if target.exists():
        with target.open("r", encoding="utf-8") as fh:
            raw_data = yaml.safe_load(fh) or {}

    db_cfg = DatabaseConfig(
        user=os.getenv("POSTGRES_USER", "siama_user"),
        password=os.getenv("POSTGRES_PASSWORD", "siama_dev_password"),
        db=os.getenv("POSTGRES_DB", "siama_impute"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )
    raw_data["database"] = db_cfg.model_dump()
    return Settings(**raw_data)
