"""Autenticación con X-API-Key, hashing SHA-256 y control de acceso por perfil."""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.db.models import ApiKey
from src.api.db.session import get_db

PerfilTipo = Literal["investigador", "operador"]


def hash_api_key(raw_key: str) -> str:
    """Genera el digest SHA-256 hexadecimal de una API Key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key(perfil: PerfilTipo) -> tuple[str, str, str]:
    """Genera una nueva llave con prefijo por perfil y retorna (raw_key, prefijo, key_hash)."""
    base_prefix = "siama_pub_" if perfil == "investigador" else "siama_ops_"
    token = secrets.token_hex(16)
    raw_key = f"{base_prefix}{token}"
    prefijo = raw_key[:14]
    return raw_key, prefijo, hash_api_key(raw_key)


def get_current_api_key(
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiKey:
    """Valida la cabecera X-API-Key contra los hashes activos en base de datos."""
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera X-API-Key.",
        )

    key_hash = hash_api_key(x_api_key.strip())
    api_key = db.scalar(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.activa.is_(True))
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida o revocada.",
        )
    return api_key


def require_reader(api_key: Annotated[ApiKey, Depends(get_current_api_key)]) -> ApiKey:
    """Permite acceso de lectura a perfiles investigador (siama_pub_) y operador (siama_ops_)."""
    if api_key.perfil not in ("investigador", "operador"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El perfil de la API Key no tiene permisos de lectura.",
        )
    return api_key


def require_operator(api_key: Annotated[ApiKey, Depends(get_current_api_key)]) -> ApiKey:
    """Restringe acceso exclusivo a llaves con perfil operador (siama_ops_)."""
    if api_key.perfil != "operador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Se requiere una API Key de perfil operador (siama_ops_) "
                "para ejecutar imputaciones al vuelo."
            ),
        )
    return api_key
