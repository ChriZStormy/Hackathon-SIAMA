"""Routers FastAPI para los endpoints v1 de SIAMA-Clima."""

from src.api.routers import asistente, auth, estaciones, imputacion, modelos

__all__ = ["asistente", "auth", "estaciones", "imputacion", "modelos"]
