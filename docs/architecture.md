# Arquitectura Base — SIAMA-Impute

## Visión general

**SIAMA-Impute** es un módulo desacoplado de completitud climatológica diaria (precipitación, $T_{\max}$ y $T_{\min}$) para las estaciones meteorológicas de Guanajuato, diseñado para integrarse de forma transparente con **SIAMA Web**.

## Capas del sistema

1. **Almacenamiento y Datos (`data/` + PostgreSQL/PostGIS)**
   - `data/raw/`: archivos oficiales de entrada (`estaciones.csv`, `series_diarias.csv`, `covariables.gpkg`, `test_publico.csv`), ignorados por Git.
   - `data/processed/`: salidas intermedias, reportes de diagnóstico y resultados de imputación.
   - `PostGIS`: motor espacial para almacenar geometrías de estaciones (EPSG:4326), series observadas, estimaciones con banderas de procedencia y covariables fisiográficas.

2. **Pipeline de Datos y Modelado (`src/pipeline/`)**
   - `data_loader.py`: carga tipada y normalización de códigos de valores faltantes.
   - `data_verifier.py`: diagnóstico de cobertura, rango temporal, porcentaje de huecos y validación de restricciones físicas.
   - `baseline.py`: línea base reproducible (interpolación lineal con límite de abstención y sin fuga de datos).
   - *Fases siguientes*: modelos espacio-temporales, cuantificación de incertidumbre y criterios avanzados de abstención.

3. **API de Servicio (`src/api/`)**
   - Construida en **FastAPI**, expone endpoints de salud (`/health`), estado de insumos (`/status/data`) y, en pasos posteriores, consulta de series completas con metadatos de procedencia e incertidumbre.

4. **Frontend Demo (`frontend/`)**
   - Aplicación **React + Vite + TypeScript** preparada con dependencias para **Leaflet** (cartografía de estaciones) y **Recharts** (visualización de series temporales diferenciando claramente observado vs. estimado vs. abstenido).
