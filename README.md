# SIAMA-Impute

Módulo de completitud climatológica diaria (**precipitación**, $T_{\max}$ y $T_{\min}$) para la red de estaciones de **Guanajuato**, diseñado para integrarse con **SIAMA Web** en el marco del **Hackatón SIAMA**.

## Principios no negociables

1. **Transparencia entre dato observado y estimado**: cada valor diario incluye una etiqueta explícita de procedencia (`observado`, `imputado_baseline`, `abstenido`) para garantizar trazabilidad total en SIAMA Web y análisis posteriores.
2. **Restricciones físicas estrictas**:
   - Precipitación no negativa: $P \ge 0$.
   - Coherencia térmica diaria: $T_{\max} > T_{\min}$.
3. **Abstención ante falta de rigor**: si un hueco supera el umbral de confianza o viola consistencia física, el sistema se abstiene explícitamente en lugar de inventar registros.
4. **Reproducibilidad y cero fuga de datos**: rutas centralizadas sin rutas absolutas quemadas, semillas fijas y validación estricta sobre máscaras independientes.

---

## Estructura del repositorio

```text
.
├── config/
│   └── settings.yaml              # Configuración centralizada (rutas, esquema, restricciones, baseline)
├── data/
│   ├── raw/                       # Insumos oficiales (ignorados en Git; conserva .gitkeep)
│   ├── processed/                 # Reportes y salidas procesadas (ignorados en Git)
│   └── external/                  # Datos auxiliares externos
├── docker/
│   ├── init/01-init-postgis.sql   # Habilita extensión PostGIS y esquema siama
│   ├── Dockerfile.api             # Imagen FastAPI
│   ├── Dockerfile.pipeline        # Imagen del pipeline Python
│   └── Dockerfile.frontend        # Imagen demo React + Vite
├── docs/
│   ├── architecture.md            # Arquitectura general del sistema
│   └── technical_sheet.md         # Ficha técnica y principios del reto
├── frontend/                      # Esqueleto React + Vite + TypeScript (Leaflet + Recharts)
├── notebooks/
│   └── 01_starter_and_baseline.ipynb  # Notebook parametrizado de arranque y línea base
├── src/
│   ├── config.py                  # Cargador tipado (YAML + .env)
│   ├── api/                       # Esqueleto FastAPI (/health, /status/data)
│   └── pipeline/                  # Carga, verificación, fallback sintético y baseline lineal
├── tests/                         # Pruebas unitarias (pytest)
├── docker-compose.yml             # Orquestación PostGIS + perfiles para api/pipeline/web-demo
├── pyproject.toml                 # Metadatos y dependencias del proyecto
├── requirements.txt               # Dependencias Python reproducibles
├── .env.example                   # Plantilla de variables de entorno
└── LICENSE                        # Licencia MIT
```

---

## Inicio rápido (Paso 1)

### 1. Crear entorno virtual e instalar dependencias

En **Windows (PowerShell)**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

En **Linux / macOS**:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configurar variables de entorno y colocar datos oficiales

```powershell
Copy-Item .env.example .env
```

Coloca los archivos oficiales del reto en `data/raw/`:
- `estaciones.csv`
- `series_diarias.csv`
- `covariables.gpkg`
- `test_publico.csv`

> **Nota**: Si los archivos oficiales aún no están en `data/raw/`, el cargador y el notebook informan exactamente qué archivos faltan y activan un **fallback sintético reproducible de Guanajuato** para verificar el flujo completo sin romper la ejecución.

### 3. Levantar PostgreSQL + PostGIS con Docker

```powershell
docker compose up -d postgis
docker compose ps
```

Para levantar el resto de servicios acoplables en fases posteriores:

```powershell
docker compose --profile full up --build
```

### 4. Verificar línea base, API y pruebas

```powershell
# Verificación CLI de configuración, diagnóstico de datos y línea base sin fuga
python -m src.pipeline.verify_setup

# Ejecutar pruebas unitarias
pytest

# Levantar API localmente
uvicorn src.api.main:app --reload
```

### 5. Ejecutar el notebook de arranque

```powershell
jupyter notebook notebooks/01_starter_and_baseline.ipynb
```
