#!/usr/bin/env python3
"""Capa Bronce: clima semanal para las ciudades de interés (Open-Meteo).

Fuente: Open-Meteo Historical Weather API (CC-BY 4.0, uso no comercial).
Salida: datos_crudos/clima_ciudades_semanal.csv
"""

from __future__ import annotations

import csv
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API = "https://archive-api.open-meteo.com/v1/archive"
SALIDA = Path("datos_crudos/clima_ciudades_semanal.csv")
INICIO = "2025-01-01"
TIMEOUT = 90
TZ = ZoneInfo("America/Mexico_City")

CIUDADES = {
    "Colima": (19.2433, -103.7250),
    "Manzanillo": (19.1130, -104.3390),
    "Guadalajara": (20.6597, -103.3496),
    "Morelia": (19.7060, -101.1950),
    "Tepic": (21.5039, -104.8946),
}

CAMPOS = [
    "anio", "semana", "ciudad", "lat", "lon",
    "temp_media_c", "precipitacion_mm", "humedad_media_pct",
    "dias_lluvia", "dias_lluvia_intensa", "extraido_en",
]


def descarga(ciudad: str, lat: float, lon: float, intentos: int = 4) -> list[dict]:
    hoy = datetime.now(TZ).date()
    hasta = (hoy - timedelta(days=1)).isoformat()
    semana_actual = hoy.isocalendar()[:2]
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": INICIO,
        "end_date": hasta,
        "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
        "timezone": "America/Mexico_City",
    }
    ultimo_error: Exception | None = None
    for intento in range(intentos):
        try:
            r = requests.get(API, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            datos = r.json()["daily"]
            break
        except Exception as exc:  # noqa: BLE001
            ultimo_error = exc
            time.sleep(5 * (intento + 1))
    else:
        raise RuntimeError(f"fallo tras {intentos} intentos: {ultimo_error}")

    acumulado: dict[tuple[int, int], dict[str, list[float]]] = defaultdict(
        lambda: {"temp": [], "prec": [], "hum": []}
    )
    for i, dia in enumerate(datos["time"]):
        d = date.fromisoformat(dia)
        iso = d.isocalendar()
        clave = (iso.year, iso.week)
        acumulado[clave]["temp"].append(datos["temperature_2m_mean"][i] or 0.0)
        acumulado[clave]["prec"].append(datos["precipitation_sum"][i] or 0.0)
        acumulado[clave]["hum"].append(datos["relative_humidity_2m_mean"][i] or 0.0)

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    filas = []
    for (anio, semana), vals in sorted(acumulado.items()):
        if (anio, semana) == semana_actual:
            continue  # semana en curso: incompleta, no se publica en Bronce
        prec = vals["prec"]
        filas.append({
            "anio": anio,
            "semana": semana,
            "ciudad": ciudad,
            "lat": lat,
            "lon": lon,
            "temp_media_c": round(sum(vals["temp"]) / len(vals["temp"]), 2),
            "precipitacion_mm": round(sum(prec), 2),
            "humedad_media_pct": round(sum(vals["hum"]) / len(vals["hum"]), 2),
            "dias_lluvia": sum(1 for p in prec if p >= 1.0),
            "dias_lluvia_intensa": sum(1 for p in prec if p >= 20.0),
            "extraido_en": ahora,
        })
    return filas


def main() -> int:
    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    # Datos previos: sirven para conservar marcas de tiempo y para no perder
    # una ciudad completa si la API falla de forma transitoria.
    previas: dict[tuple, dict] = {}
    if SALIDA.exists():
        with SALIDA.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                previas[(int(r["anio"]), int(r["semana"]), r["ciudad"])] = r

    filas: list[dict] = []
    fallidas: list[str] = []
    for ciudad, (lat, lon) in CIUDADES.items():
        try:
            propias = descarga(ciudad, lat, lon)
            filas.extend(propias)
            print(f"{ciudad}: {len(propias)} semanas")
        except Exception as exc:  # noqa: BLE001
            fallidas.append(ciudad)
            print(f"{ciudad}: ERROR {exc}", file=sys.stderr)
            rescatadas = [r for (a, s, c), r in previas.items() if c == ciudad]
            filas.extend({k: r[k] for k in CAMPOS} for r in rescatadas)
            print(f"{ciudad}: se conservan {len(rescatadas)} filas previas")

    if not filas:
        return 1

    # Conserva la marca de tiempo si los valores no cambiaron (evita commits vacíos).
    for fila in filas:
        previo = previas.get((fila["anio"], fila["semana"], fila["ciudad"]))
        if previo and all(
            str(previo.get(k)) == str(v) for k, v in fila.items() if k != "extraido_en"
        ):
            fila["extraido_en"] = previo["extraido_en"]

    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(sorted(filas, key=lambda f: (f["anio"], f["semana"], f["ciudad"])))

    semanas = len({(f["anio"], f["semana"]) for f in filas})
    print(f"Total: {len(filas)} filas, {semanas} semanas")
    if fallidas:
        print(f"Ciudades con fallo transitorio: {', '.join(fallidas)}", file=sys.stderr)
        return 1
    return 0 if semanas >= 36 else 1


if __name__ == "__main__":
    raise SystemExit(main())
