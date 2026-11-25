"""Pruebas unitarias e integración para todos los contratos del Backend SIAMA-Clima."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Any, Self

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.auth.api_keys import hash_api_key
from src.api.db.models import ApiKey


def test_auth_missing_and_invalid_api_key_returns_401(client: TestClient) -> None:
    protected_gets = [
        "/api/v1/estaciones/mapa",
        "/api/v1/estaciones/11024/diagnostico",
        "/api/v1/estaciones/11024/series?variable=precipitacion",
        "/api/v1/modelos/metricas",
    ]
    for path in protected_gets:
        resp = client.get(path)
        assert resp.status_code == 401
        assert list(resp.json().keys()) == ["detail"]

        bad_resp = client.get(path, headers={"X-API-Key": "siama_pub_invalida"})
        assert bad_resp.status_code == 401
        assert list(bad_resp.json().keys()) == ["detail"]

    post_resp = client.post(
        "/api/v1/imputar",
        json={
            "clave_estacion": "11024",
            "variable": "precipitacion",
            "registros": [{"fecha": "2024-05-14", "valor": None}],
        },
    )
    assert post_resp.status_code == 401
    assert list(post_resp.json().keys()) == ["detail"]


def test_create_api_keys_hashes_sha256_and_enforces_roles(
    client: TestClient,
    db_session: Session,
) -> None:
    pub_res = client.post("/api/v1/auth/keys", json={"perfil": "investigador"})
    assert pub_res.status_code == 201
    pub_body = pub_res.json()
    assert pub_body["api_key"].startswith("siama_pub_")
    assert pub_body["prefijo"].startswith("siama_pub_")
    assert pub_body["perfil"] == "investigador"

    ops_res = client.post("/api/v1/auth/keys", json={"perfil": "operador"})
    assert ops_res.status_code == 201
    ops_body = ops_res.json()
    assert ops_body["api_key"].startswith("siama_ops_")
    assert ops_body["prefijo"].startswith("siama_ops_")
    assert ops_body["perfil"] == "operador"

    # En BD solo se almacena el hash SHA-256, nunca texto plano
    stored_pub = db_session.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(pub_body["api_key"]))
    )
    assert stored_pub is not None
    assert stored_pub.key_hash != pub_body["api_key"]
    assert len(stored_pub.key_hash) == 64

    # Investigador puede leer pero recibe 403 en /imputar
    assert (
        client.get("/api/v1/estaciones/mapa", headers={"X-API-Key": pub_body["api_key"]}).status_code
        == 200
    )
    forbidden = client.post(
        "/api/v1/imputar",
        headers={"X-API-Key": pub_body["api_key"]},
        json={
            "clave_estacion": "11024",
            "variable": "precipitacion",
            "registros": [{"fecha": "2024-05-14", "valor": None}],
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "detail": (
            "Se requiere una API Key de perfil operador (siama_ops_) "
            "para ejecutar imputaciones al vuelo."
        )
    }


def test_demo_keys_permissions(
    client: TestClient,
    pub_headers: dict[str, str],
    ops_headers: dict[str, str],
) -> None:
    assert client.get("/api/v1/estaciones/mapa", headers=pub_headers).status_code == 200

    forbidden = client.post(
        "/api/v1/imputar",
        headers=pub_headers,
        json={
            "clave_estacion": "11024",
            "variable": "precipitacion",
            "registros": [{"fecha": "2024-05-14", "valor": None}],
        },
    )
    assert forbidden.status_code == 403
    assert "siama_ops_" in forbidden.json()["detail"]

    allowed = client.post(
        "/api/v1/imputar",
        headers=ops_headers,
        json={
            "clave_estacion": "11024",
            "variable": "precipitacion",
            "registros": [{"fecha": "2024-05-14", "valor": None}],
        },
    )
    assert allowed.status_code == 200


def test_cors_and_uniform_error_format(
    client: TestClient,
    pub_headers: dict[str, str],
) -> None:
    preflight = client.options(
        "/api/v1/estaciones/mapa",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-API-Key",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") in (
        "http://localhost:5173",
        "*",
    )
    allow_headers = (preflight.headers.get("access-control-allow-headers") or "").lower()
    assert "x-api-key" in allow_headers or "*" in allow_headers

    # 404 uniforme
    not_found = client.get("/api/v1/estaciones/99999/diagnostico", headers=pub_headers)
    assert not_found.status_code == 404
    assert isinstance(not_found.json()["detail"], str)

    # 422 uniforme (detail debe ser string)
    invalid_var = client.get(
        "/api/v1/estaciones/11024/series?variable=humedad",
        headers=pub_headers,
    )
    assert invalid_var.status_code == 422
    assert isinstance(invalid_var.json()["detail"], str)

    # 400 rango de fechas invertido
    bad_range = client.get(
        "/api/v1/estaciones/11024/series?variable=precipitacion&desde=2024-06-01&hasta=2024-05-01",
        headers=pub_headers,
    )
    assert bad_range.status_code == 400
    assert isinstance(bad_range.json()["detail"], str)


def test_mapa_geojson_contract(client: TestClient, pub_headers: dict[str, str]) -> None:
    resp = client.get("/api/v1/estaciones/mapa", headers=pub_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    features = body["features"]
    assert len(features) >= 5

    claves = set()
    for feat in features:
        assert feat["type"] == "Feature"
        geom = feat["geometry"]
        assert geom["type"] == "Point"
        lon, lat = geom["coordinates"]
        assert -102.5 <= lon <= -99.5
        assert 19.8 <= lat <= 22.0

        props = feat["properties"]
        assert set(props.keys()) == {
            "clave",
            "nombre",
            "completitud_pct",
            "alerta_homogeneidad",
            "huecos_totales",
        }
        assert 0.0 <= props["completitud_pct"] <= 100.0
        assert isinstance(props["alerta_homogeneidad"], bool)
        assert isinstance(props["huecos_totales"], int)
        claves.add(props["clave"])

    assert "11024" in claves


def test_diagnostico_contract(client: TestClient, pub_headers: dict[str, str]) -> None:
    resp = client.get("/api/v1/estaciones/11024/diagnostico", headers=pub_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "clave_estacion",
        "variable",
        "porcentaje_faltantes",
        "conteo_huecos",
        "metodo_recomendado",
        "alerta_homogeneidad",
        "detalle_homogeneidad",
    }
    assert body["clave_estacion"] == "11024"
    assert body["variable"] == "precipitacion"
    assert set(body["conteo_huecos"].keys()) == {"cortos", "medios", "largos"}
    assert body["conteo_huecos"]["cortos"] >= 1
    assert body["conteo_huecos"]["medios"] >= 1
    assert body["conteo_huecos"]["largos"] >= 1
    assert body["alerta_homogeneidad"] is True
    assert "2018-06" in (body["detalle_homogeneidad"] or "")

    tmax_resp = client.get(
        "/api/v1/estaciones/11036/diagnostico?variable=tmax",
        headers=pub_headers,
    )
    assert tmax_resp.status_code == 200
    assert tmax_resp.json()["variable"] == "tmax"


def test_series_filters_integrity_and_csv_download(
    client: TestClient,
    pub_headers: dict[str, str],
) -> None:
    # Serie completa con ventana que incluye observado, estimado_alta_confianza,
    # estimado_baja_confianza y no_estimable
    resp = client.get(
        "/api/v1/estaciones/11024/series?variable=precipitacion&desde=2024-01-01&hasta=2024-09-01",
        headers=pub_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["clave_estacion"] == "11024"
    assert body["variable"] == "precipitacion"
    datos = body["datos"]
    assert len(datos) > 200

    flags_seen = set()
    for row in datos:
        flags_seen.add(row["bandera_calidad"])
        if row["bandera_calidad"] == "observado":
            assert row["es_estimado"] is False
            assert row["valor_observado"] is not None
            assert row["valor_observado"] >= 0.0
        elif row["bandera_calidad"] in ("estimado_alta_confianza", "estimado_baja_confianza"):
            assert row["es_estimado"] is True
            assert row["valor_estimado"] is not None
            assert row["valor_estimado"] >= 0.0
            assert row["incertidumbre_90"] is not None
            inf, sup = row["incertidumbre_90"]
            assert 0.0 <= inf <= row["valor_estimado"] <= sup
        elif row["bandera_calidad"] == "no_estimable":
            assert row["es_estimado"] is False
            assert row["valor_estimado"] is None
            assert row["incertidumbre_90"] is None

    assert flags_seen == {
        "observado",
        "estimado_alta_confianza",
        "estimado_baja_confianza",
        "no_estimable",
    }

    # Filtro incluir_estimados=false -> cero estimados
    only_obs = client.get(
        "/api/v1/estaciones/11024/series?variable=precipitacion&incluir_estimados=false",
        headers=pub_headers,
    ).json()["datos"]
    assert len(only_obs) > 0
    assert all(r["bandera_calidad"] == "observado" and not r["es_estimado"] for r in only_obs)

    # Filtro confianza_minima=alta
    alta_only = client.get(
        "/api/v1/estaciones/11024/series?variable=precipitacion&confianza_minima=alta",
        headers=pub_headers,
    ).json()["datos"]
    assert {r["bandera_calidad"] for r in alta_only}.issubset(
        {"observado", "estimado_alta_confianza"}
    )

    # Descarga CSV
    csv_resp = client.get(
        "/api/v1/estaciones/11024/series?variable=precipitacion&desde=2024-05-12&hasta=2024-05-16&formato=csv",
        headers=pub_headers,
    )
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert (
        csv_resp.headers["content-disposition"]
        == 'attachment; filename="siama_11024_precipitacion.csv"'
    )
    reader = list(csv.reader(io.StringIO(csv_resp.text)))
    assert reader[0] == [
        "fecha",
        "valor_observado",
        "valor_estimado",
        "es_estimado",
        "bandera_calidad",
        "incertidumbre_90_inf",
        "incertidumbre_90_sup",
    ]
    assert len(reader) == 6  # header + 5 días


def test_series_physical_consistency_tmax_gt_tmin(
    client: TestClient,
    pub_headers: dict[str, str],
) -> None:
    tmax_data = client.get(
        "/api/v1/estaciones/11024/series?variable=tmax&desde=2024-05-01&hasta=2024-06-01",
        headers=pub_headers,
    ).json()["datos"]
    tmin_data = client.get(
        "/api/v1/estaciones/11024/series?variable=tmin&desde=2024-05-01&hasta=2024-06-01",
        headers=pub_headers,
    ).json()["datos"]

    assert len(tmax_data) == len(tmin_data)
    for r_max, r_min in zip(tmax_data, tmin_data, strict=True):
        val_max = r_max["valor_estimado"] if r_max["es_estimado"] else r_max["valor_observado"]
        val_min = r_min["valor_estimado"] if r_min["es_estimado"] else r_min["valor_observado"]
        if val_max is not None and val_min is not None:
            assert val_max > val_min


def test_modelos_metricas_filters(client: TestClient, pub_headers: dict[str, str]) -> None:
    all_resp = client.get("/api/v1/modelos/metricas", headers=pub_headers)
    assert all_resp.status_code == 200
    rows = all_resp.json()
    modelos = {r["modelo"] for r in rows}
    assert modelos == {
        "Interpolación Lineal",
        "GCIDW",
        "Razón Normal",
        "Hurdle/DTR",
        "IBM Granite TTM",
    }

    filtered = client.get(
        "/api/v1/modelos/metricas?variable=precipitacion&longitud_hueco=corto&temporada=lluvias",
        headers=pub_headers,
    )
    assert filtered.status_code == 200
    f_rows = filtered.json()
    assert len(f_rows) == 5
    for r in f_rows:
        assert r["variable"] == "precipitacion"
        assert r["longitud_hueco"] == "corto"
        assert r["temporada"] == "lluvias"
        assert r["pod"] is not None
        assert r["far"] is not None


def test_imputar_on_demand_schema_and_physical_bounds(
    client: TestClient,
    ops_headers: dict[str, str],
) -> None:
    resp = client.post(
        "/api/v1/imputar",
        headers=ops_headers,
        json={
            "clave_estacion": "11024",
            "variable": "precipitacion",
            "registros": [
                {"fecha": "2024-05-13", "valor": 5.2},
                {"fecha": "2024-05-14", "valor": None},
                {"fecha": "2024-05-15", "valor": 0.0},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["clave_estacion"] == "11024"
    assert body["variable"] == "precipitacion"
    datos = body["datos"]
    assert len(datos) == 3
    assert datos[0]["bandera_calidad"] == "observado"
    assert datos[0]["valor_observado"] == 5.2
    assert datos[1]["bandera_calidad"] == "estimado_alta_confianza"
    assert datos[1]["es_estimado"] is True
    assert datos[1]["valor_estimado"] >= 0.0
    assert datos[1]["incertidumbre_90"][0] >= 0.0
    assert datos[2]["bandera_calidad"] == "observado"

    # Hueco largo (>30 días) debe marcarse no_estimable con nulos
    long_gap = [
        {"fecha": (date(2024, 1, 1) + timedelta(days=i)).isoformat(), "valor": None}
        for i in range(32)
    ]
    long_resp = client.post(
        "/api/v1/imputar",
        headers=ops_headers,
        json={"clave_estacion": "11024", "variable": "tmax", "registros": long_gap},
    )
    assert long_resp.status_code == 200
    for item in long_resp.json()["datos"]:
        assert item["bandera_calidad"] == "no_estimable"
        assert item["valor_estimado"] is None
        assert item["incertidumbre_90"] is None
        assert item["es_estimado"] is False


def test_asistente_deterministic_fallback_and_audited_response(
    client: TestClient,
    pub_headers: dict[str, str],
    monkeypatch: Any,
) -> None:
    # Forzar URL inalcanzable para validar fallback determinista sin Ollama
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:59999/v1")
    from src.api.settings import get_api_settings

    get_api_settings.cache_clear()

    resp = client.post(
        "/api/v1/asistente/consultar",
        headers=pub_headers,
        json={
            "pregunta": "¿Puedo confiar en las lluvias del último verano?",
            "clave_estacion": "11024",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verificado_guardian"] is True
    assert "11024" in body["respuesta"]
    assert "observad" in body["respuesta"].lower()
    assert "estimad" in body["respuesta"].lower()
    aud = body["resumen_auditoria"]
    assert 0.0 <= aud["pct_observado"] <= 100.0
    assert 0.0 <= aud["pct_estimado"] <= 100.0
    assert aud["pct_observado"] + aud["pct_estimado"] <= 100.1


def test_asistente_granite_tool_calling_and_guardian_override(
    client: TestClient,
    pub_headers: dict[str, str],
    monkeypatch: Any,
) -> None:
    calls_made: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict[str, Any]:
            return self._payload

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            calls_made.append(json)
            messages = json.get("messages", [])
            # 1a llamada (con tools): Granite solicita get_series_stats
            if "tools" in json and not any(m.get("role") == "tool" for m in messages):
                return FakeResponse(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "get_series_stats",
                                                "arguments": '{"clave_estacion": "11036", "variable": "precipitacion"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                )
            # Llamada del Guardian
            if messages and "Evalúa si la respuesta" in messages[0].get("content", ""):
                return FakeResponse(
                    {"choices": [{"message": {"role": "assistant", "content": "PASS"}}]}
                )
            # 2a llamada tras tool result: respuesta alucinada que debe ser bloqueada por Guardian
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "La estación tiene 99.9% de datos observados y 0.1% estimados.",
                            }
                        }
                    ]
                }
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)

    resp = client.post(
        "/api/v1/asistente/consultar",
        headers=pub_headers,
        json={
            "pregunta": "¿Qué tan completa está la estación 11036?",
            "clave_estacion": "11036",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verificado_guardian"] is True
    # Guardian debe haber bloqueado el 99.9% alucinado y devuelto el dato auditado real
    assert "99.9%" not in body["respuesta"]
    assert f"{body['resumen_auditoria']['pct_observado']:.1f}%" in body["respuesta"]
    assert len(calls_made) >= 2
