"""Capa de auditoría determinista y verificación Granite Guardian."""

from __future__ import annotations

import re
from typing import Any

import httpx


def _validate_numbers_and_transparency(
    respuesta: str,
    db_stats: dict[str, Any],
    diagnostico: dict[str, Any],
) -> bool:
    """Verifica que la respuesta no alucine porcentajes y declare observados vs estimados."""
    if not respuesta or not respuesta.strip():
        return False

    lower = respuesta.lower()
    pct_obs = float(db_stats.get("pct_observado", 0.0))
    pct_est = float(db_stats.get("pct_estimado", 0.0))
    pct_no_est = float(db_stats.get("pct_no_estimable", 0.0))
    pct_missing = float(diagnostico.get("porcentaje_faltantes", 0.0))

    if pct_est > 0 and ("observad" not in lower or ("estimad" not in lower and "imputad" not in lower)):
        return False

    # Verificar que todos los porcentajes citados correspondan a cifras reales de BD
    # (se permiten referencias estándar a intervalos del 90% o umbrales 90.0%)
    allowed_pcts = [pct_obs, pct_est, pct_no_est, pct_missing, 90.0]
    cited_pcts = [float(match) for match in re.findall(r"(\d+(?:\.\d+)?)\s*%", respuesta)]
    for cited in cited_pcts:
        if not any(abs(cited - ref) <= 0.6 for ref in allowed_pcts):
            return False

    return True


def _check_with_granite_guardian(
    respuesta: str,
    context_summary: str,
    ollama_base_url: str,
    guardian_model: str,
    timeout: float,
) -> bool | None:
    """Consulta opcionalmente a Granite Guardian vía API OpenAI-compatible en Ollama."""
    url = f"{ollama_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": guardian_model,
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Evalúa si la respuesta es completamente fiel al contexto de base de datos. "
                    "Responde únicamente 'PASS' o 'FAIL'."
                ),
            },
            {
                "role": "user",
                "content": f"Contexto BD:\n{context_summary}\n\nRespuesta:\n{respuesta}",
            },
        ],
    }
    try:
        with httpx.Client(timeout=min(timeout, 4.0)) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()
            verdict = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .upper()
            )
            if "FAIL" in verdict:
                return False
            if "PASS" in verdict:
                return True
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None
    return None


def audit_and_verify(
    candidate_response: str,
    fallback_response: str,
    db_stats: dict[str, Any],
    diagnostico: dict[str, Any],
    ollama_base_url: str,
    guardian_model: str,
    timeout: float,
) -> tuple[bool, str]:
    """Aplica validación determinista y verificación opcional Granite Guardian."""
    is_valid = _validate_numbers_and_transparency(candidate_response, db_stats, diagnostico)
    if not is_valid:
        return True, fallback_response

    context_summary = (
        f"estacion={diagnostico.get('clave_estacion')}, "
        f"pct_observado={db_stats.get('pct_observado')}%, "
        f"pct_estimado={db_stats.get('pct_estimado')}%, "
        f"pct_no_estimable={db_stats.get('pct_no_estimable')}%, "
        f"alerta_homogeneidad={diagnostico.get('alerta_homogeneidad')}"
    )
    guardian_verdict = _check_with_granite_guardian(
        candidate_response,
        context_summary,
        ollama_base_url,
        guardian_model,
        timeout,
    )
    if guardian_verdict is False:
        return True, fallback_response

    return True, candidate_response
