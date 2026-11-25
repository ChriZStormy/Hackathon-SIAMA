#!/usr/bin/env sh
set -eu

echo "[siama-api] Inicializando esquema PostGIS y datos semilla..."
python -m src.api.db.seed_mock_db

echo "[siama-api] Levantando servidor FastAPI en puerto ${API_PORT:-8000}..."
exec uvicorn src.api.main:app --host 0.0.0.0 --port "${API_PORT:-8000}"
