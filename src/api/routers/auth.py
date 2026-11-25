"""Router de autenticación y emisión de API Keys."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.api.auth.api_keys import generate_api_key
from src.api.db.models import ApiKey
from src.api.db.session import get_db
from src.api.schemas import CreateApiKeyRequest, CreateApiKeyResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/keys",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(
    payload: CreateApiKeyRequest,
    db: Annotated[Session, Depends(get_db)],
) -> CreateApiKeyResponse:
    """Genera una nueva API Key (almacenando únicamente su hash SHA-256 en BD)."""
    raw_key, prefijo, key_hash = generate_api_key(payload.perfil)
    db.add(
        ApiKey(
            key_hash=key_hash,
            prefijo=prefijo,
            perfil=payload.perfil,
            activa=True,
        )
    )
    db.commit()
    return CreateApiKeyResponse(
        api_key=raw_key,
        prefijo=prefijo,
        perfil=payload.perfil,
    )
