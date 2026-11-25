"""Script idempotente de inicialización y poblamiento realista para Guanajuato (SIAMA-Clima)."""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.db.models import (
    AlertaHomogeneidad,
    ApiKey,
    DiagnosticoHueco,
    Estacion,
    MetricaModelo,
    SerieCruda,
    SerieImputada,
)
from src.api.db.session import SessionLocal, init_db

DEMO_KEYS = (
    ("siama_pub_demo_2026", "siama_pub_demo", "investigador"),
    ("siama_ops_demo_2026", "siama_ops_demo", "operador"),
)

STATIONS_SEED = [
    {
        "clave": "11024",
        "nombre": "Guanajuato (DGE)",
        "municipio": "Guanajuato",
        "latitud": 21.0190,
        "longitud": -101.2574,
        "altitud": 2012.0,
        "cuenca": "Río Guanajuato",
        "estado_operativo": "operando",
        "alerta": True,
        "estado_homog": "no_homogenea",
        "fecha_quiebre": date(2018, 6, 15),
        "prueba": "SNHT + Pettitt",
        "detalle": "Posible quiebre detectado en 2018-06",
    },
    {
        "clave": "11036",
        "nombre": "León (SMN)",
        "municipio": "León",
        "latitud": 21.1250,
        "longitud": -101.6860,
        "altitud": 1815.0,
        "cuenca": "Río Turbio",
        "estado_operativo": "operando",
        "alerta": False,
        "estado_homog": "homogenea",
        "fecha_quiebre": None,
        "prueba": "SNHT + Pettitt",
        "detalle": "Serie homogénea sin quiebres significativos (p > 0.05)",
    },
    {
        "clave": "11012",
        "nombre": "Celaya (INIFAP)",
        "municipio": "Celaya",
        "latitud": 20.5235,
        "longitud": -100.8157,
        "altitud": 1752.0,
        "cuenca": "Río Laja",
        "estado_operativo": "operando",
        "alerta": True,
        "estado_homog": "sospechosa",
        "fecha_quiebre": date(2021, 3, 10),
        "prueba": "Doble Masa + Pettitt",
        "detalle": "Posible quiebre detectado en 2021-03 por reubicación de sensor",
    },
    {
        "clave": "11058",
        "nombre": "Dolores Hidalgo",
        "municipio": "Dolores Hidalgo Cuna de la Independencia Nacional",
        "latitud": 21.1561,
        "longitud": -100.9344,
        "altitud": 1918.0,
        "cuenca": "Río Laja",
        "estado_operativo": "operando",
        "alerta": False,
        "estado_homog": "homogenea",
        "fecha_quiebre": None,
        "prueba": "SNHT + Pettitt",
        "detalle": "Serie homogénea dentro de tolerancia estadística",
    },
    {
        "clave": "11079",
        "nombre": "Irapuato (Presa La Purísima)",
        "municipio": "Irapuato",
        "latitud": 20.6767,
        "longitud": -101.3563,
        "altitud": 1728.0,
        "cuenca": "Río Guanajuato",
        "estado_operativo": "operando",
        "alerta": False,
        "estado_homog": "homogenea",
        "fecha_quiebre": None,
        "prueba": "SNHT + Pettitt",
        "detalle": "Serie homogénea validada contra vecinos de la cuenca",
    },
]

# Ventanas de huecos por estación para cubrir cortos (1-3d), medios (4-30d) y largos (>30d)
STATION_GAPS: dict[str, list[tuple[date, int, str]]] = {
    "11024": [
        (date(2023, 2, 10), 2, "estimado_alta_confianza"),
        (date(2023, 4, 3), 3, "estimado_alta_confianza"),
        (date(2023, 7, 14), 8, "estimado_alta_confianza"),
        (date(2023, 10, 5), 2, "estimado_alta_confianza"),
        (date(2024, 1, 10), 35, "no_estimable"),
        (date(2024, 5, 13), 3, "estimado_alta_confianza"),  # Incluye 2024-05-14
        (date(2024, 8, 2), 14, "estimado_baja_confianza"),
        (date(2024, 11, 18), 2, "estimado_alta_confianza"),
    ],
    "11036": [
        (date(2023, 3, 12), 2, "estimado_alta_confianza"),
        (date(2023, 8, 18), 6, "estimado_alta_confianza"),
        (date(2024, 4, 9), 3, "estimado_alta_confianza"),
        (date(2024, 9, 20), 10, "estimado_baja_confianza"),
    ],
    "11012": [
        (date(2023, 1, 20), 3, "estimado_alta_confianza"),
        (date(2023, 6, 4), 12, "estimado_baja_confianza"),
        (date(2023, 11, 2), 34, "no_estimable"),
        (date(2024, 7, 25), 9, "estimado_alta_confianza"),
        (date(2024, 10, 14), 2, "estimado_alta_confianza"),
    ],
    "11058": [
        (date(2023, 5, 1), 2, "estimado_alta_confianza"),
        (date(2023, 9, 10), 15, "estimado_baja_confianza"),
        (date(2024, 3, 22), 3, "estimado_alta_confianza"),
        (date(2024, 6, 15), 32, "estimado_baja_confianza"),
    ],
    "11079": [
        (date(2023, 4, 17), 3, "estimado_alta_confianza"),
        (date(2023, 7, 28), 7, "estimado_alta_confianza"),
        (date(2024, 2, 14), 2, "estimado_alta_confianza"),
        (date(2024, 8, 25), 11, "estimado_baja_confianza"),
    ],
}


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def ensure_demo_api_keys(session: Session) -> None:
    """Asegura que las llaves demo investigador y operador estén presentes y activas."""
    for raw_key, prefijo, perfil in DEMO_KEYS:
        key_hash = _hash_key(raw_key)
        existing = session.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))
        if existing is None:
            session.add(
                ApiKey(
                    key_hash=key_hash,
                    prefijo=prefijo,
                    perfil=perfil,
                    activa=True,
                )
            )
        elif not existing.activa:
            existing.activa = True
    session.flush()


def _gap_lookup(clave: str) -> dict[date, str]:
    mapping: dict[date, str] = {}
    for start, length, flag in STATION_GAPS.get(clave, []):
        for offset in range(length):
            mapping[start + timedelta(days=offset)] = flag
    return mapping


def _classify_gaps(flags_by_day: list[tuple[date, bool]]) -> tuple[float, int, int, int]:
    """Calcula porcentaje de faltantes y conteo exacto de huecos cortos/medios/largos."""
    total = len(flags_by_day)
    if total == 0:
        return 0.0, 0, 0, 0

    missing_count = 0
    short_gaps = 0
    medium_gaps = 0
    long_gaps = 0
    current_run = 0

    for _, is_missing in flags_by_day:
        if is_missing:
            missing_count += 1
            current_run += 1
        elif current_run > 0:
            if current_run <= 3:
                short_gaps += 1
            elif current_run <= 30:
                medium_gaps += 1
            else:
                long_gaps += 1
            current_run = 0

    if current_run > 0:
        if current_run <= 3:
            short_gaps += 1
        elif current_run <= 30:
            medium_gaps += 1
        else:
            long_gaps += 1

    pct = round((missing_count / total) * 100.0, 2)
    return pct, short_gaps, medium_gaps, long_gaps


def _seed_stations_and_series(session: Session) -> None:
    existing_stations = session.scalar(select(func.count()).select_from(Estacion)) or 0
    if existing_stations >= len(STATIONS_SEED):
        return

    rng = random.Random(42)
    start_date = date(2023, 1, 1)
    end_date = date(2024, 12, 31)
    total_days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=i) for i in range(total_days)]

    for idx, st in enumerate(STATIONS_SEED):
        clave = st["clave"]
        if session.get(Estacion, clave) is None:
            session.add(
                Estacion(
                    clave=clave,
                    nombre=st["nombre"],
                    municipio=st["municipio"],
                    latitud=st["latitud"],
                    longitud=st["longitud"],
                    altitud=st["altitud"],
                    cuenca=st["cuenca"],
                    estado_operativo=st["estado_operativo"],
                    geom=(st["longitud"], st["latitud"]),
                )
            )
            session.flush()

        # Alertas de homogeneidad por variable
        for variable in ("precipitacion", "tmax", "tmin"):
            has_alert = st["alerta"] and variable in ("precipitacion", "tmax")
            session.add(
                AlertaHomogeneidad(
                    clave_estacion=clave,
                    variable=variable,
                    alerta_homogeneidad=has_alert,
                    estado=st["estado_homog"] if has_alert else "homogenea",
                    fecha=st["fecha_quiebre"] if has_alert else None,
                    prueba=st["prueba"],
                    detalle_homogeneidad=st["detalle"] if has_alert else None,
                )
            )

        gaps = _gap_lookup(clave)
        alt_offset = (st["altitud"] - 1850.0) * -0.005

        raw_rows: list[SerieCruda] = []
        imp_rows: list[SerieImputada] = []
        gap_tracker: dict[str, list[tuple[date, bool]]] = {
            "precipitacion": [],
            "tmax": [],
            "tmin": [],
        }

        for d in dates:
            doy = d.timetuple().tm_yday
            season_rad = 2.0 * math.pi * (doy - 30) / 365.0
            is_wet_season = 6 <= d.month <= 10

            # Clima base físicamente consistente (Tmax siempre > Tmin por >= 7 C)
            tmin_true = round(9.5 + alt_offset + 5.2 * math.sin(season_rad) + rng.gauss(0, 1.4), 2)
            dtr_true = round(max(6.5, 14.2 - (2.8 if is_wet_season else 0.0) + rng.gauss(0, 1.3)), 2)
            tmax_true = round(tmin_true + dtr_true, 2)

            rain_prob = 0.42 if is_wet_season else 0.06
            if rng.random() < rain_prob:
                precip_true = round(max(0.2, rng.gammavariate(1.4, 8.5 if is_wet_season else 3.2)), 2)
            else:
                precip_true = 0.0

            # Caso determinista para 11024 en 2024-05-14 (alineado con ejemplo del contrato)
            if clave == "11024" and d == date(2024, 5, 14):
                precip_true = 12.4

            flag = gaps.get(d, "observado")
            # Para temperaturas dejamos observados en parte del hueco largo de lluvia en 11058,
            # pero en general mantenemos la misma máscara realista por estación.
            values = {
                "precipitacion": precip_true,
                "tmax": tmax_true,
                "tmin": tmin_true,
            }

            for variable, true_val in values.items():
                is_missing = flag != "observado"
                gap_tracker[variable].append((d, is_missing))

                if not is_missing:
                    raw_rows.append(
                        SerieCruda(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_crudo=true_val,
                            bandera_qc="ok",
                        )
                    )
                    imp_rows.append(
                        SerieImputada(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_observado=true_val,
                            valor_estimado=None,
                            es_estimado=False,
                            bandera_calidad="observado",
                            incertidumbre_90_inf=None,
                            incertidumbre_90_sup=None,
                            metodo_usado=None,
                            vecinos_activos=None,
                        )
                    )
                elif flag == "no_estimable":
                    raw_rows.append(
                        SerieCruda(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_crudo=None,
                            bandera_qc="faltante",
                        )
                    )
                    imp_rows.append(
                        SerieImputada(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_observado=None,
                            valor_estimado=None,
                            es_estimado=False,
                            bandera_calidad="no_estimable",
                            incertidumbre_90_inf=None,
                            incertidumbre_90_sup=None,
                            metodo_usado="abstenido_sin_vecinos",
                            vecinos_activos=1,
                        )
                    )
                else:
                    if variable == "precipitacion":
                        if clave == "11024" and d == date(2024, 5, 14):
                            est_val, inf_val, sup_val = 12.4, 8.1, 16.9
                        else:
                            est_val = round(max(0.0, true_val + rng.gauss(0, 1.1)), 2)
                            margin = 3.2 if flag == "estimado_alta_confianza" else 6.4
                            inf_val = round(max(0.0, est_val - margin), 2)
                            sup_val = round(est_val + margin, 2)
                        metodo = "granite_ttm_hibrido" if flag == "estimado_alta_confianza" else "gcidw_espacial"
                    else:
                        est_val = round(true_val + rng.gauss(0, 0.6), 2)
                        if variable == "tmax":
                            est_val = max(est_val, tmin_true + 2.0)
                        else:
                            est_val = min(est_val, tmax_true - 2.0)
                        est_val = round(est_val, 2)
                        margin = 1.6 if flag == "estimado_alta_confianza" else 3.4
                        inf_val = round(est_val - margin, 2)
                        sup_val = round(est_val + margin, 2)
                        metodo = "granite_ttm_hibrido" if flag == "estimado_alta_confianza" else "random_forest_secuencial"

                    raw_rows.append(
                        SerieCruda(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_crudo=None,
                            bandera_qc="faltante",
                        )
                    )
                    imp_rows.append(
                        SerieImputada(
                            clave_estacion=clave,
                            variable=variable,
                            fecha=d,
                            valor_observado=None,
                            valor_estimado=est_val,
                            es_estimado=True,
                            bandera_calidad=flag,
                            incertidumbre_90_inf=inf_val,
                            incertidumbre_90_sup=sup_val,
                            metodo_usado=metodo,
                            vecinos_activos=4 if flag == "estimado_alta_confianza" else 2,
                        )
                    )

        session.bulk_save_objects(raw_rows)
        session.bulk_save_objects(imp_rows)

        for variable in ("precipitacion", "tmax", "tmin"):
            pct, cortos, medios, largos = _classify_gaps(gap_tracker[variable])
            metodo_rec = (
                "granite_ttm_hibrido"
                if variable == "precipitacion" or idx % 2 == 0
                else "dtr_lightgbm_granite"
            )
            session.add(
                DiagnosticoHueco(
                    clave_estacion=clave,
                    variable=variable,
                    porcentaje_faltantes=pct,
                    huecos_cortos=cortos,
                    huecos_medios=medios,
                    huecos_largos=largos,
                    metodo_recomendado=metodo_rec,
                )
            )


def _seed_model_metrics(session: Session) -> None:
    existing_metrics = session.scalar(select(func.count()).select_from(MetricaModelo)) or 0
    if existing_metrics > 0:
        return

    modelos_base = [
        ("Interpolación Lineal", 1.35, 1.32, 0.35, 0.42, 0.54, 0.44, 72.0),
        ("GCIDW", 1.05, 1.03, 0.14, 0.68, 0.72, 0.25, 84.5),
        ("Razón Normal", 1.15, 1.12, 0.21, 0.61, 0.68, 0.31, 80.2),
        ("Hurdle/DTR", 0.88, 0.87, 0.06, 0.79, 0.84, 0.16, 89.4),
        ("IBM Granite TTM", 0.84, 0.83, 0.04, 0.82, 0.86, 0.14, 90.6),
    ]

    rows: list[MetricaModelo] = []
    hueco_mult = {"corto": 0.85, "medio": 1.0, "largo": 1.25}
    temp_mult = {"lluvias": 1.15, "estiaje": 0.88}

    for variable in ("precipitacion", "tmax", "tmin"):
        var_scale = 3.2 if variable == "precipitacion" else (1.4 if variable == "tmax" else 1.2)
        for hueco in ("corto", "medio", "largo"):
            for temporada in ("lluvias", "estiaje"):
                factor = var_scale * hueco_mult[hueco] * temp_mult[temporada]
                for nombre, rmse_b, mae_b, bias_b, kge_b, pod_b, far_b, cob_b in modelos_base:
                    kge_adj = round(max(0.2, min(0.95, kge_b - (0.06 if hueco == "largo" else 0.0))), 3)
                    cob_adj = round(min(95.0, max(65.0, cob_b - (1.5 if hueco == "largo" else 0.0))), 1)
                    rows.append(
                        MetricaModelo(
                            modelo=nombre,
                            variable=variable,
                            longitud_hueco=hueco,
                            temporada=temporada,
                            rmse=round(rmse_b * factor, 3),
                            mae=round(mae_b * factor * 0.72, 3),
                            bias=round(bias_b * (1.0 if variable == "precipitacion" else 0.5), 3),
                            kge=kge_adj,
                            pod=round(pod_b, 3) if variable == "precipitacion" else None,
                            far=round(far_b, 3) if variable == "precipitacion" else None,
                            cobertura_90=cob_adj,
                        )
                    )

    session.bulk_save_objects(rows)


def seed_database(session: Session) -> None:
    """Ejecuta el poblamiento completo de forma idempotente."""
    ensure_demo_api_keys(session)
    _seed_stations_and_series(session)
    _seed_model_metrics(session)
    session.commit()


def main() -> None:
    """Punto de entrada CLI para inicializar tablas PostGIS y poblar datos mock."""
    init_db()
    with SessionLocal() as session:
        seed_database(session)
    print("SIAMA DB inicializada y poblada correctamente.")


if __name__ == "__main__":
    main()
