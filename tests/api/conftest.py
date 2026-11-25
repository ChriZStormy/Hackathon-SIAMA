"""Fixtures compartidas para pruebas del Backend API con SQLite aislado."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# Desactivar auto-inicialización contra Postgres antes de importar la app
os.environ["SIAMA_AUTO_INIT_DB"] = "false"

from src.api.db.seed_mock_db import seed_database
from src.api.db.session import create_db_engine, get_db, init_db
from src.api.main import app
from src.api.settings import get_api_settings


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Crea una base SQLite en memoria poblada con las 7 tablas y datos semilla."""
    get_api_settings.cache_clear()
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with testing_session_local() as session:
        seed_database(session)
        yield session

    engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Cliente FastAPI conectado a la sesión de pruebas aislada."""

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def pub_headers() -> dict[str, str]:
    """Cabeceras con llave demo pública (perfil investigador)."""
    return {"X-API-Key": "siama_pub_demo_2026"}


@pytest.fixture()
def ops_headers() -> dict[str, str]:
    """Cabeceras con llave demo operativa (perfil operador)."""
    return {"X-API-Key": "siama_ops_demo_2026"}
