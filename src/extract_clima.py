#!/usr/bin/env python3
"""Capa Bronce: clima semanal para las ciudades de interés (Open-Meteo).

Fuente: Open-Meteo Historical Weather API (CC-BY 4.0, uso no comercial).
Salida: datos_crudos/clima_ciudades_semanal.csv
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

API = "https://archive-api.open-meteo.com/v1/archive"
SALIDA = Path("datos_crudos/clima_ciudades_semanal.csv")
INICIO = "2025-01-01"
TIMEOUT = 90

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


def descarga(ciudad: str, lat: float, lon: float) -> list[dict]:
    hasta = (date.today() - timedelta(days=1)).isoformat()
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": INICIO,
        "end_date": hasta,
        "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean",
        "timezone": "America/Mexico_City",
    }
    r = requests.get(API, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    datos = r.json()["daily"]

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
    filas: list[dict] = []
    for ciudad, (lat, lon) in CIUDADES.items():
        try:
            propias = descarga(ciudad, lat, lon)
            filas.extend(propias)
            print(f"{ciudad}: {len(propias)} semanas")
        except Exception as exc:  # noqa: BLE001
            print(f"{ciudad}: ERROR {exc}", file=sys.stderr)

    if not filas:
        return 1

    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(sorted(filas, key=lambda f: (f["anio"], f["semana"], f["ciudad"])))

    semanas = len({(f["anio"], f["semana"]) for f in filas})
    print(f"Total: {len(filas)} filas, {semanas} semanas")
    return 0 if semanas >= 36 else 1


if __name__ == "__main__":
    raise SystemExit(main())
