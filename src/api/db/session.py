"""Gestión de motor SQLAlchemy, sesiones y creación de esquema PostGIS."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.settings import get_api_settings


class Base(DeclarativeBase):
    """Clase base declarativa para los modelos ORM de SIAMA."""


def create_db_engine(database_url: str | None = None) -> Engine:
    """Crea un Engine SQLAlchemy compatible con PostgreSQL/PostGIS y SQLite en pruebas."""
    url = database_url or get_api_settings().effective_database_url
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Retorna el Engine singleton lazily inicializado."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine()
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, class_=Session)
    return _engine


def SessionLocal() -> Session:
    """Abre una nueva sesión de base de datos."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI que entrega una sesión por petición y la cierra al finalizar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(engine: Engine | None = None) -> None:
    """Crea las tablas ORM y habilita PostGIS e índice espacial cuando usa PostgreSQL."""
    # Importar modelos para asegurar su registro en Base.metadata
    import src.api.db.models  # noqa: F401

    target_engine = engine or get_engine()
    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

    Base.metadata.create_all(bind=target_engine)

    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_estaciones_geom "
                    "ON estaciones USING GIST (geom);"
                )
            )
