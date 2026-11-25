"""Esquemas Pydantic iniciales para los endpoints de SIAMA-Impute."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    region: str


class DatasetStatusResponse(BaseModel):
    project: str
    files: dict[str, dict[str, Any]]
    ready_with_official_data: bool
