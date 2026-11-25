"""Esquemas Pydantic v2 para todos los contratos de la API SIAMA-Clima."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

VariableClima = Literal["precipitacion", "tmax", "tmin"]
BanderaCalidad = Literal[
    "observado",
    "estimado_alta_confianza",
    "estimado_baja_confianza",
    "no_estimable",
]
PerfilApiKey = Literal["investigador", "operador"]
ConfianzaMinima = Literal["todas", "baja", "alta"]
FormatoSerie = Literal["json", "csv"]
LongitudHueco = Literal["corto", "medio", "largo"]
TemporadaClima = Literal["lluvias", "estiaje"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    region: str


class DatasetStatusResponse(BaseModel):
    project: str
    files: dict[str, dict[str, Any]]
    ready_with_official_data: bool


class ErrorResponse(BaseModel):
    detail: str


class CreateApiKeyRequest(BaseModel):
    perfil: PerfilApiKey


class CreateApiKeyResponse(BaseModel):
    api_key: str
    prefijo: str
    perfil: PerfilApiKey


class GeoJSONPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class EstacionMapaProperties(BaseModel):
    clave: str
    nombre: str
    completitud_pct: float
    alerta_homogeneidad: bool
    huecos_totales: int


class EstacionMapaFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPoint
    properties: EstacionMapaProperties


class EstacionesMapaResponse(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[EstacionMapaFeature]


class ConteoHuecos(BaseModel):
    cortos: int
    medios: int
    largos: int


class DiagnosticoResponse(BaseModel):
    clave_estacion: str
    variable: VariableClima
    porcentaje_faltantes: float
    conteo_huecos: ConteoHuecos
    metodo_recomendado: str
    alerta_homogeneidad: bool
    detalle_homogeneidad: str | None = None


class SerieDato(BaseModel):
    fecha: str
    valor_observado: float | None
    valor_estimado: float | None
    es_estimado: bool
    bandera_calidad: BanderaCalidad
    incertidumbre_90: tuple[float, float] | None

    @model_validator(mode="after")
    def _validate_integrity(self) -> SerieDato:
        if self.bandera_calidad == "observado":
            if self.es_estimado:
                raise ValueError("Un registro observado no puede tener es_estimado=true.")
        elif self.bandera_calidad in ("estimado_alta_confianza", "estimado_baja_confianza"):
            if not self.es_estimado:
                raise ValueError("Un registro estimado debe tener es_estimado=true.")
            if self.valor_estimado is None:
                raise ValueError("Un registro estimado debe incluir valor_estimado.")
            if self.incertidumbre_90 is None:
                raise ValueError("Un registro estimado debe incluir incertidumbre_90.")
            if self.incertidumbre_90[0] > self.incertidumbre_90[1]:
                raise ValueError("incertidumbre_90 debe cumplir limite_inferior <= limite_superior.")
        elif self.bandera_calidad == "no_estimable":
            if self.es_estimado:
                raise ValueError("Un registro no_estimable no puede tener es_estimado=true.")
            if self.valor_estimado is not None or self.incertidumbre_90 is not None:
                raise ValueError(
                    "Cuando bandera_calidad es no_estimable, valor_estimado e incertidumbre_90 deben ser null."
                )
        return self


class SeriesResponse(BaseModel):
    clave_estacion: str
    variable: VariableClima
    datos: list[SerieDato]


class MetricaModeloResponse(BaseModel):
    modelo: str
    variable: VariableClima
    longitud_hueco: LongitudHueco
    temporada: TemporadaClima
    rmse: float
    mae: float
    bias: float
    kge: float
    pod: float | None = None
    far: float | None = None
    cobertura_90: float


class RegistroImputacionInput(BaseModel):
    fecha: date
    valor: float | None = None


class ImputarRequest(BaseModel):
    clave_estacion: str = Field(min_length=1)
    variable: VariableClima
    registros: list[RegistroImputacionInput] = Field(min_length=1)


class AsistenteRequest(BaseModel):
    pregunta: str = Field(min_length=3)
    clave_estacion: str | None = None


class ResumenAuditoria(BaseModel):
    pct_observado: float
    pct_estimado: float


class AsistenteResponse(BaseModel):
    respuesta: str
    verificado_guardian: bool
    resumen_auditoria: ResumenAuditoria
