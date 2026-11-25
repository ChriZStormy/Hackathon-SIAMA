"""Aplicación principal FastAPI para el Backend SIAMA-Clima (Fase 3B)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.api.db.seed_mock_db import seed_database
from src.api.db.session import SessionLocal, init_db
from src.api.routers import asistente, auth, estaciones, imputacion, modelos
from src.api.schemas import DatasetStatusResponse, HealthResponse
from src.api.settings import get_api_settings
from src.config import load_settings

logger = logging.getLogger(__name__)
project_settings = load_settings()
api_settings = get_api_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Inicializa el esquema PostGIS y datos semilla al arrancar si está habilitado."""
    if get_api_settings().SIAMA_AUTO_INIT_DB:
        try:
            init_db()
            with SessionLocal() as session:
                seed_database(session)
        except SQLAlchemyError as exc:
            logger.warning("No se pudo inicializar la base de datos al arranque: %s", exc)
    yield


app = FastAPI(
    title="SIAMA-Impute API",
    description="Servicio de consulta, completitud climatológica y asistente Granite para Guanajuato (SIAMA Web).",
    version=project_settings.project.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*", "X-API-Key", "Content-Type", "Authorization"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Garantiza formato uniforme {"detail": "..."} en errores HTTP."""
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Normaliza errores de validación Pydantic (422) al formato {"detail": "..."}."""
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(str(part) for part in first.get("loc", []))
        msg = first.get("msg", "Error de validación.")
        detail = f"Validación inválida en '{loc}': {msg}" if loc else msg
    else:
        detail = "Solicitud inválida."
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Captura excepciones no controladas devolviendo JSON uniforme."""
    logger.exception("Error inesperado en API: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


@app.get("/health", response_model=HealthResponse, tags=["system"])
def healthcheck() -> HealthResponse:
    """Endpoint de verificación de salud del servicio."""
    return HealthResponse(
        status="ok",
        service=project_settings.project.name,
        version=project_settings.project.version,
        region=project_settings.project.region,
    )


@app.get("/status/data", response_model=DatasetStatusResponse, tags=["system"])
def data_status() -> DatasetStatusResponse:
    """Informa el estado de disponibilidad de los archivos oficiales en data/raw/."""
    files = project_settings.check_official_files()
    ready = bool(files["estaciones"]["exists"] and files["series_diarias"]["exists"])
    return DatasetStatusResponse(
        project=project_settings.project.name,
        files=files,
        ready_with_official_data=ready,
    )


API_V1_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(estaciones.router, prefix=API_V1_PREFIX)
app.include_router(modelos.router, prefix=API_V1_PREFIX)
app.include_router(imputacion.router, prefix=API_V1_PREFIX)
app.include_router(asistente.router, prefix=API_V1_PREFIX)
