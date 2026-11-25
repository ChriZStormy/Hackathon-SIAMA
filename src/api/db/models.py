"""Modelos ORM SQLAlchemy + GeoAlchemy2 para las 7 tablas del backend SIAMA."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from geoalchemy2 import Geometry, WKTElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.api.db.session import Base

BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class PostGISPoint(TypeDecorator):
    """Columna espacial POINT SRID 4326 en PostGIS con fallback limpio a WKT Text en SQLite."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
            )
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (tuple, list)) and len(value) == 2:
            lon, lat = float(value[0]), float(value[1])
            wkt = f"POINT({lon} {lat})"
        elif isinstance(value, WKTElement):
            wkt = value.desc
        else:
            wkt = str(value)

        if dialect.name == "postgresql":
            return WKTElement(wkt, srid=4326)
        return wkt

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return value


class Estacion(Base):
    """Catálogo geoespacial de estaciones climatológicas de Guanajuato."""

    __tablename__ = "estaciones"

    clave: Mapped[str] = mapped_column(String(20), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    municipio: Mapped[str] = mapped_column(String(100), nullable=False)
    latitud: Mapped[float] = mapped_column(Float, nullable=False)
    longitud: Mapped[float] = mapped_column(Float, nullable=False)
    altitud: Mapped[float] = mapped_column(Float, nullable=False)
    cuenca: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estado_operativo: Mapped[str] = mapped_column(String(40), nullable=False, default="operando")
    geom: Mapped[Any] = mapped_column(PostGISPoint(), nullable=True)


class SerieCruda(Base):
    """Histórico diario original preservado sin destrucción junto con bandera de QC."""

    __tablename__ = "series_crudas"
    __table_args__ = (
        Index("ix_series_crudas_est_var_fecha", "clave_estacion", "variable", "fecha", unique=True),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    clave_estacion: Mapped[str] = mapped_column(
        String(20), ForeignKey("estaciones.clave", ondelete="CASCADE"), nullable=False
    )
    variable: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    valor_crudo: Mapped[float | None] = mapped_column(Float, nullable=True)
    bandera_qc: Mapped[str] = mapped_column(String(40), nullable=False, default="ok")


class SerieImputada(Base):
    """Series diarias completadas con trazabilidad estricta, bandera de calidad e incertidumbre al 90%."""

    __tablename__ = "series_imputadas"
    __table_args__ = (
        Index(
            "ix_series_imputadas_est_var_fecha",
            "clave_estacion",
            "variable",
            "fecha",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    clave_estacion: Mapped[str] = mapped_column(
        String(20), ForeignKey("estaciones.clave", ondelete="CASCADE"), nullable=False
    )
    variable: Mapped[str] = mapped_column(String(30), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    valor_observado: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    es_estimado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bandera_calidad: Mapped[str] = mapped_column(String(40), nullable=False)
    incertidumbre_90_inf: Mapped[float | None] = mapped_column(Float, nullable=True)
    incertidumbre_90_sup: Mapped[float | None] = mapped_column(Float, nullable=True)
    metodo_usado: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vecinos_activos: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DiagnosticoHueco(Base):
    """Resumen estructural de vacíos y método recomendado por estación y variable."""

    __tablename__ = "diagnostico_huecos"
    __table_args__ = (
        Index("ix_diagnostico_huecos_est_var", "clave_estacion", "variable", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave_estacion: Mapped[str] = mapped_column(
        String(20), ForeignKey("estaciones.clave", ondelete="CASCADE"), nullable=False
    )
    variable: Mapped[str] = mapped_column(String(30), nullable=False)
    porcentaje_faltantes: Mapped[float] = mapped_column(Float, nullable=False)
    huecos_cortos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    huecos_medios: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    huecos_largos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metodo_recomendado: Mapped[str] = mapped_column(String(80), nullable=False)
    calculado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AlertaHomogeneidad(Base):
    """Alertas de quiebres abruptos y homogeneidad relativa (SNHT / Pettitt / Doble Masa)."""

    __tablename__ = "alertas_homogeneidad"
    __table_args__ = (
        Index("ix_alertas_homogeneidad_est_var_fecha", "clave_estacion", "variable", "fecha"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave_estacion: Mapped[str] = mapped_column(
        String(20), ForeignKey("estaciones.clave", ondelete="CASCADE"), nullable=False
    )
    variable: Mapped[str] = mapped_column(String(30), nullable=False)
    alerta_homogeneidad: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="homogenea")
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    prueba: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detalle_homogeneidad: Mapped[str | None] = mapped_column(Text, nullable=True)


class MetricaModelo(Base):
    """Tabla comparativa de desempeño entre líneas base, ML tabular e IBM Granite TTM."""

    __tablename__ = "metricas_modelos"
    __table_args__ = (
        Index("ix_metricas_modelos_var_hueco_temp", "variable", "longitud_hueco", "temporada"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    modelo: Mapped[str] = mapped_column(String(100), nullable=False)
    variable: Mapped[str] = mapped_column(String(30), nullable=False)
    longitud_hueco: Mapped[str] = mapped_column(String(20), nullable=False)
    temporada: Mapped[str] = mapped_column(String(20), nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    bias: Mapped[float] = mapped_column(Float, nullable=False)
    kge: Mapped[float] = mapped_column(Float, nullable=False)
    pod: Mapped[float | None] = mapped_column(Float, nullable=True)
    far: Mapped[float | None] = mapped_column(Float, nullable=True)
    cobertura_90: Mapped[float] = mapped_column(Float, nullable=False)


class ApiKey(Base):
    """Llaves de autenticación X-API-Key almacenadas exclusivamente como hash SHA-256."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefijo: Mapped[str] = mapped_column(String(32), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
