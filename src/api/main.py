"""Esqueleto inicial de la API FastAPI para SIAMA-Impute."""

from __future__ import annotations

from fastapi import FastAPI

from src.api.schemas import DatasetStatusResponse, HealthResponse
from src.config import load_settings

settings = load_settings()

app = FastAPI(
    title="SIAMA-Impute API",
    description="Servicio de consulta y completitud climatológica para Guanajuato (SIAMA Web).",
    version=settings.project.version,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def healthcheck() -> HealthResponse:
    """Endpoint de verificación de salud del servicio."""
    return HealthResponse(
        status="ok",
        service=settings.project.name,
        version=settings.project.version,
        region=settings.project.region,
    )


@app.get("/status/data", response_model=DatasetStatusResponse, tags=["system"])
def data_status() -> DatasetStatusResponse:
    """Informa el estado de disponibilidad de los archivos oficiales en data/raw/."""
    files = settings.check_official_files()
    ready = bool(files["estaciones"]["exists"] and files["series_diarias"]["exists"])
    return DatasetStatusResponse(
        project=settings.project.name,
        files=files,
        ready_with_official_data=ready,
    )
