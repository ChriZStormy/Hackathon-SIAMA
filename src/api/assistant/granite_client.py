"""Cliente IBM Granite 4.2 con tool calling y fallback determinista inteligente."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.assistant.guardian import audit_and_verify
from src.api.assistant.tools import (
    TOOLS_SCHEMA,
    get_diagnostico,
    get_metricas,
    get_series_stats,
    infer_season_range_from_question,
    infer_variable_from_question,
)
from src.api.db.models import Estacion
from src.api.schemas import AsistenteResponse, ResumenAuditoria
from src.api.settings import get_api_settings


def _resolve_station_id(db: Session, pregunta: str, clave_estacion: str | None) -> str:
    if clave_estacion:
        est = db.get(Estacion, clave_estacion)
        if est is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Estación '{clave_estacion}' no encontrada.",
            )
        return est.clave

    match = re.search(r"\b(\d{5})\b", pregunta)
    if match and db.get(Estacion, match.group(1)) is not None:
        return match.group(1)

    q_lower = pregunta.lower()
    estaciones = db.scalars(select(Estacion).order_by(Estacion.clave.asc())).all()
    for est in estaciones:
        if est.municipio.lower() in q_lower or est.nombre.lower() in q_lower:
            return est.clave

    if estaciones:
        return estaciones[0].clave

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No existen estaciones registradas para consultar.",
    )


def _execute_tool(db: Session, name: str, arguments: dict[str, Any]) -> str:
    if name == "get_diagnostico":
        res = get_diagnostico(
            db,
            clave_estacion=str(arguments.get("clave_estacion", "")),
            variable=str(arguments.get("variable", "precipitacion")),
        )
        return json.dumps(res, ensure_ascii=False)
    if name == "get_series_stats":
        res = get_series_stats(
            db,
            clave_estacion=str(arguments.get("clave_estacion", "")),
            variable=str(arguments.get("variable", "precipitacion")),
            desde=arguments.get("desde"),
            hasta=arguments.get("hasta"),
        )
        return json.dumps(res, ensure_ascii=False)
    if name == "get_metricas":
        res = get_metricas(
            db,
            variable=arguments.get("variable"),
            longitud_hueco=arguments.get("longitud_hueco"),
            temporada=arguments.get("temporada"),
        )
        return json.dumps(res[:5], ensure_ascii=False)
    return json.dumps({"error": f"Herramienta desconocida: {name}"})


def _build_deterministic_response(
    diagnostico: dict[str, Any],
    stats: dict[str, Any],
    metricas: list[dict[str, Any]],
) -> str:
    clave = diagnostico["clave_estacion"]
    nombre = diagnostico.get("nombre_estacion", clave)
    variable = stats["variable"]
    pct_obs = stats["pct_observado"]
    pct_est = stats["pct_estimado"]
    pct_no_est = stats["pct_no_estimable"]
    desde = stats.get("desde")
    hasta = stats.get("hasta")
    rango_txt = f" del {desde} al {hasta}" if desde and hasta else ""

    huecos = diagnostico["conteo_huecos"]
    metodo = diagnostico["metodo_recomendado"]
    top_model = metricas[0] if metricas else None

    partes = [
        (
            f"En la estación {clave} ({nombre}) para la variable {variable}{rango_txt}, "
            f"el {pct_obs:.1f}% de los datos son observados y el {pct_est:.1f}% son estimados"
            + (
                f" (además de un {pct_no_est:.1f}% declarado como no estimable por falta de respaldo vecinal)."
                if pct_no_est > 0
                else "."
            )
        ),
        (
            f"El diagnóstico global registra {huecos['cortos']} huecos cortos, "
            f"{huecos['medios']} medios y {huecos['largos']} largos, recomendando el método {metodo}."
        ),
    ]

    if diagnostico.get("alerta_homogeneidad"):
        detalle = diagnostico.get("detalle_homogeneidad") or "quiebre detectado"
        partes.append(f"Advertencia de homogeneidad activa: {detalle}.")
    else:
        partes.append("La serie no presenta alertas activas de homogeneidad.")

    if top_model:
        partes.append(
            f"El modelo mejor evaluado ({top_model['modelo']}) alcanza un KGE de {top_model['kge']} "
            f"con cobertura empírica del intervalo al 90% de {top_model['cobertura_90']}%."
        )

    return " ".join(partes)


def _call_granite_with_tools(
    db: Session,
    pregunta: str,
    clave_estacion: str,
    variable: str,
    desde_str: str | None,
    hasta_str: str | None,
    ollama_base_url: str,
    model_name: str,
    timeout: float,
) -> str | None:
    url = f"{ollama_base_url.rstrip('/')}/chat/completions"
    system_prompt = (
        "Eres el asistente técnico de SIAMA-Clima en Guanajuato. "
        "Usa las herramientas disponibles para obtener cifras reales de la base de datos. "
        "Regla obligatoria: declara explícitamente qué porcentaje es observado y qué porcentaje "
        "es estimado sin inventar ningún número."
    )
    user_context = (
        f"Estación: {clave_estacion}. Variable sugerida: {variable}. "
        + (f"Periodo sugerido: {desde_str} a {hasta_str}. " if desde_str and hasta_str else "")
        + f"Pregunta: {pregunta}"
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_context},
    ]

    try:
        with httpx.Client(timeout=timeout) as client:
            for _ in range(3):
                resp = client.post(
                    url,
                    json={
                        "model": model_name,
                        "temperature": 0.1,
                        "messages": messages,
                        "tools": TOOLS_SCHEMA,
                        "tool_choice": "auto",
                    },
                )
                if resp.status_code != 200:
                    return None

                data = resp.json()
                message = data.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls") or []

                if not tool_calls:
                    content = (message.get("content") or "").strip()
                    return content or None

                messages.append(message)
                for call in tool_calls:
                    fn_info = call.get("function", {})
                    fn_name = fn_info.get("name", "")
                    raw_args = fn_info.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args) if raw_args.strip() else {}
                        except json.JSONDecodeError:
                            parsed_args = {}
                    elif isinstance(raw_args, dict):
                        parsed_args = raw_args
                    else:
                        parsed_args = {}

                    tool_result = _execute_tool(db, fn_name, parsed_args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", fn_name),
                            "name": fn_name,
                            "content": tool_result,
                        }
                    )
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None

    return None


def consultar_asistente(
    db: Session,
    pregunta: str,
    clave_estacion: str | None = None,
) -> AsistenteResponse:
    """Orquesta la consulta al asistente IBM Granite 4.2 con auditoría y fallback determinista."""
    settings = get_api_settings()
    station_id = _resolve_station_id(db, pregunta, clave_estacion)
    variable = infer_variable_from_question(pregunta)
    desde, hasta = infer_season_range_from_question(pregunta, db, station_id, variable)

    diagnostico = get_diagnostico(db, station_id, variable=variable)
    db_stats = get_series_stats(db, station_id, variable=variable, desde=desde, hasta=hasta)
    metricas = get_metricas(db, variable=variable)

    fallback_text = _build_deterministic_response(diagnostico, db_stats, metricas)

    candidate_text = _call_granite_with_tools(
        db=db,
        pregunta=pregunta,
        clave_estacion=station_id,
        variable=variable,
        desde_str=desde.isoformat() if desde else None,
        hasta_str=hasta.isoformat() if hasta else None,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        model_name=settings.GRANITE_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )

    verificado, final_text = audit_and_verify(
        candidate_response=candidate_text or "",
        fallback_response=fallback_text,
        db_stats=db_stats,
        diagnostico=diagnostico,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        guardian_model=settings.GRANITE_GUARDIAN_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )

    return AsistenteResponse(
        respuesta=final_text,
        verificado_guardian=verificado,
        resumen_auditoria=ResumenAuditoria(
            pct_observado=float(db_stats["pct_observado"]),
            pct_estimado=float(db_stats["pct_estimado"]),
        ),
    )
