#!/usr/bin/env python3
"""Capa Bronce sintética: inventario por turno (Plan B de E1).

Genera un conjunto **sintético** con el esquema de `docs/E0/esquema-inventario.md`
para poder construir y probar la tubería de limpieza mientras la unidad de salud
autoriza los registros reales. El archivo de salida se marca explícitamente como
sintético en el nombre, en la columna `es_sintetico` y en el reporte JSON.

El generador es determinista para una semilla dada.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np

SALIDA = Path("datos_crudos/inventario_turno_sintetico.csv")
REPORTE = Path("datos_crudos/_reporte_sintetico.json")
VERSION = "1.0"

# (id, nombre genérico, familia, consumo base por turno matutino)
INSUMOS: list[tuple[str, str, str, int]] = [
    ("INS01", "Paracetamol 500 mg", "medicamento", 18),
    ("INS02", "Jeringa 5 ml", "material_curacion", 25),
    ("INS03", "Catéter periférico 20G", "material_curacion", 8),
    ("INS04", "Guante de nitrilo (par)", "material_curacion", 40),
    ("INS05", "Cubrebocas tricapa", "material_curacion", 30),
]

TURNOS = ("M", "V", "N")
PACIENTES_BASE = {"M": 45, "V": 35, "N": 15}
PERSONAL_BASE = {"M": 7, "V": 6, "N": 4}

COLUMNAS = [
    "unidad_id",
    "fecha",
    "turno",
    "insumo_id",
    "insumo_nombre",
    "familia",
    "existencia_inicial",
    "entradas",
    "consumo",
    "existencia_final",
    "desabasto",
    "pacientes_atendidos",
    "personal_disponible",
    "es_sintetico",
]

# Parámetros de inyección de defectos (documentados para la etapa de limpieza).
TASA_MCAR = 0.02
TASA_MAR_NOCTURNO = 0.08
TASA_MNAR = 0.10
TASA_ATIPICOS = 0.01
FACTOR_ATIPICO = 5

DIAS_OBJETIVO_STOCK = 9.6
FALLA_PEDIDO = 0.08


def _fecha_fin(inicio: date, dias: int) -> date:
    return inicio + timedelta(days=dias - 1)


def _generar_base(
    seed: int,
    inicio: date,
    dias: int,
    unidades: tuple[str, ...],
) -> tuple[list[dict], np.random.Generator]:
    """Construye las filas antes de inyectar defectos y devuelve el RNG usado."""
    if dias <= 0:
        raise ValueError("dias debe ser mayor que cero")
    if not unidades:
        raise ValueError("se requiere al menos una unidad")

    rng = np.random.default_rng(seed)
    filas: list[dict] = []

    for unidad in unidades:
        # Días con evento hidrometeorológico: menos pacientes y menos personal.
        eventos = set(rng.choice(dias, size=3, replace=False).tolist())

        for insumo_id, nombre, familia, base in INSUMOS:
            objetivo = round(base * 3 * DIAS_OBJETIVO_STOCK)
            existencia = float(objetivo)
            factor_semana = 1.0
            falla_semana = False

            for i in range(dias):
                fecha = inicio + timedelta(days=i)
                if fecha.weekday() == 0:  # lunes: pedido semanal
                    factor_semana = float(rng.lognormal(0.0, 0.22))
                    falla_semana = bool(rng.random() < FALLA_PEDIDO)
                    pedido = 0 if falla_semana else max(0, round(objetivo - existencia))
                else:
                    pedido = 0

                for turno in TURNOS:
                    pacientes = int(rng.poisson(PACIENTES_BASE[turno]))
                    personal = PERSONAL_BASE[turno]
                    if i in eventos:
                        pacientes = max(1, int(pacientes * 0.6))
                        personal = max(1, personal - 2)
                    if fecha.day in (15, 1) or (fecha + timedelta(days=1)).day == 1:
                        pacientes = int(round(pacientes * 1.15))

                    entradas = pedido if turno == "M" else 0
                    disponible = existencia + entradas
                    demanda = (
                        base
                        * (pacientes / PACIENTES_BASE[turno])
                        * factor_semana
                        * float(rng.lognormal(0.0, 0.18))
                    )
                    demanda = max(0, int(round(demanda)))
                    consumo = min(demanda, int(disponible))
                    existencia_final = int(disponible) - consumo
                    desabasto = 1 if demanda > disponible else 0
                    existencia = float(existencia_final)

                    filas.append(
                        {
                            "unidad_id": unidad,
                            "fecha": fecha.isoformat(),
                            "turno": turno,
                            "insumo_id": insumo_id,
                            "insumo_nombre": nombre,
                            "familia": familia,
                            "existencia_inicial": int(disponible) - entradas,
                            "entradas": int(entradas),
                            "consumo": consumo,
                            "existencia_final": existencia_final,
                            "desabasto": desabasto,
                            "pacientes_atendidos": pacientes,
                            "personal_disponible": personal,
                            "es_sintetico": 1,
                        }
                    )

    return filas, rng


def _construir_meta(
    filas: list[dict],
    seed: int,
    inicio: date,
    dias: int,
    unidades: tuple[str, ...],
    faltantes: dict[str, int],
    atipicos: int,
) -> dict:
    """Metadato determinista, sin marcas de tiempo, para reproducción byte a byte."""
    return {
        "es_sintetico": True,
        "version": VERSION,
        "seed": seed,
        "inicio": inicio.isoformat(),
        "fin": _fecha_fin(inicio, dias).isoformat(),
        "dias": dias,
        "unidades": list(unidades),
        "insumos": [
            {"insumo_id": i, "insumo_nombre": n, "familia": f, "consumo_base": b}
            for i, n, f, b in INSUMOS
        ],
        "filas": len(filas),
        "faltantes": faltantes,
        "atipicos": atipicos,
        "reglas": [
            "existencia_final = existencia_inicial + entradas - consumo",
            "sin valores negativos",
            "llave única (unidad_id, fecha, turno, insumo_id)",
            "faltantes inyectados: MCAR, MAR (turno nocturno) y MNAR (consumo alto)",
            "bronce no imputa: los vacíos se conservan",
        ],
    }


def generar_con_verdad(
    seed: int = 42,
    inicio: date = date(2026, 7, 1),
    dias: int = 120,
    unidades: tuple[str, ...] = ("U01", "U02"),
) -> tuple[list[dict], list[dict], dict]:
    """Genera filas y devuelve también los valores previos a inyectar defectos.

    El tercer elemento es el metadato reproducible. ``verdad`` conserva los
    valores completos de ``consumo`` y ``pacientes_atendidos`` antes de MCAR,
    MAR, MNAR y atípicos, para auditar la imputación del pipeline.
    """
    filas, rng = _generar_base(seed, inicio, dias, unidades)
    verdad = [dict(fila) for fila in filas]
    faltantes = _inyectar_faltantes(filas, rng)
    atipicos = _inyectar_atipicos(filas, rng)
    meta = _construir_meta(
        filas, seed, inicio, dias, unidades, faltantes, atipicos
    )
    return filas, verdad, meta


def generar(
    seed: int = 42,
    inicio: date = date(2026, 7, 1),
    dias: int = 120,
    unidades: tuple[str, ...] = ("U01", "U02"),
) -> tuple[list[dict], dict]:
    """Genera las filas sintéticas y su metadato reproducible."""
    filas, rng = _generar_base(seed, inicio, dias, unidades)
    faltantes = _inyectar_faltantes(filas, rng)
    atipicos = _inyectar_atipicos(filas, rng)
    meta = _construir_meta(
        filas, seed, inicio, dias, unidades, faltantes, atipicos
    )
    return filas, meta


def _inyectar_faltantes(filas: list[dict], rng: np.random.Generator) -> dict[str, int]:
    """Inyecta vacíos con tres mecanismos distintos y documentados."""
    n = len(filas)
    indices = np.arange(n)

    # MCAR: falta aleatoria en consumo, independiente de todo.
    mcar = rng.choice(indices, size=round(n * TASA_MCAR), replace=False)
    for i in mcar:
        filas[int(i)]["consumo"] = ""

    # MAR: la falta de personal depende del turno observado (nocturno).
    nocturnos = np.array([i for i, f in enumerate(filas) if f["turno"] == "N"])
    mar = rng.choice(nocturnos, size=round(len(nocturnos) * TASA_MAR_NOCTURNO), replace=False)
    for i in mar:
        filas[int(i)]["personal_disponible"] = ""

    # MNAR: la falta de consumo depende del propio valor (los más altos).
    # El percentil se calcula una sola vez, no dentro de la comprensión.
    p90 = _percentil(filas, 90)
    candidatos = [
        i for i, f in enumerate(filas)
        if f["consumo"] != "" and f["consumo"] >= p90
    ]
    if candidatos:
        k = max(1, round(len(candidatos) * TASA_MNAR))
        mnar = rng.choice(np.array(candidatos), size=k, replace=False)
    else:
        mnar = []
    for i in mnar:
        filas[int(i)]["consumo"] = ""

    return {"mcar": len(mcar), "mar": len(mar), "mnar": len(mnar)}


def _percentil(filas: list[dict], p: float) -> float:
    valores = [f["consumo"] for f in filas if f["consumo"] != ""]
    return float(np.percentile(valores, p))


def _inyectar_atipicos(filas: list[dict], rng: np.random.Generator) -> int:
    """Simula errores de captura en pacientes (p. ej. jornadas masivas)."""
    n = len(filas)
    indices = rng.choice(n, size=round(n * TASA_ATIPICOS), replace=False)
    for i in indices:
        fila = filas[int(i)]
        fila["pacientes_atendidos"] = fila["pacientes_atendidos"] * FACTOR_ATIPICO
    return len(indices)


def _temporal_en_destino(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, nombre = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    os.close(descriptor)
    return Path(nombre)


def escribir(
    filas: list[dict],
    meta: dict,
    salida: Path = SALIDA,
    reporte: Path | None = None,
) -> str:
    """Escribe CSV y reporte juntos; por defecto el reporte va junto al CSV.

    La escritura es transaccional: si falla un reemplazo, se restauran los
    archivos previos para no dejar un CSV nuevo con un reporte viejo (o
    viceversa). Devuelve el sha256 del CSV publicado.
    """
    salida = Path(salida)
    reporte = Path(reporte) if reporte is not None else salida.with_name(
        "_reporte_sintetico.json"
    )
    if salida.resolve() == reporte.resolve():
        raise ValueError("la salida y el reporte no pueden ser el mismo archivo")

    salida.parent.mkdir(parents=True, exist_ok=True)
    reporte.parent.mkdir(parents=True, exist_ok=True)

    temporal_csv = _temporal_en_destino(salida)
    temporal_json = _temporal_en_destino(reporte)
    respaldos: list[tuple[Path, Path | None]] = []
    publicados: list[Path] = []
    try:
        with temporal_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNAS)
            writer.writeheader()
            writer.writerows(filas)

        digest = hashlib.sha256(temporal_csv.read_bytes()).hexdigest()
        datos = {**meta, "archivo": salida.as_posix(), "sha256": digest}
        temporal_json.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        for temporal, destino in ((temporal_csv, salida), (temporal_json, reporte)):
            if destino.exists():
                respaldo = _temporal_en_destino(destino)
                shutil.copy2(destino, respaldo)
                shutil.copymode(destino, temporal)
            else:
                respaldo = None
                os.chmod(temporal, 0o644)
            respaldos.append((destino, respaldo))
            os.replace(temporal, destino)
            publicados.append(destino)

        return digest
    except Exception:
        for destino, respaldo in reversed(respaldos):
            try:
                if respaldo is not None and respaldo.exists():
                    os.replace(respaldo, destino)
                elif destino in publicados and destino.exists():
                    destino.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporal in (temporal_csv, temporal_json):
            if temporal.exists():
                temporal.unlink()
        for _, respaldo in respaldos:
            if respaldo is not None and respaldo.exists():
                respaldo.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inicio", type=date.fromisoformat, default=date(2026, 7, 1))
    parser.add_argument("--dias", type=int, default=120)
    parser.add_argument("--unidades", default="U01,U02")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    parser.add_argument("--reporte", type=Path, default=None)
    args = parser.parse_args(argv)

    unidades = tuple(u.strip() for u in args.unidades.split(",") if u.strip())
    filas, meta = generar(
        seed=args.seed, inicio=args.inicio, dias=args.dias, unidades=unidades
    )
    reporte = args.reporte or args.salida.with_name("_reporte_sintetico.json")
    digest = escribir(filas, meta, args.salida, reporte)

    desabasto = sum(f["desabasto"] for f in filas) / len(filas)
    print(f"Archivo: {args.salida}")
    print(f"Reporte: {reporte}")
    print(f"Filas: {len(filas)} · unidades: {len(unidades)} · días: {args.dias}")
    print(f"Tasa de desabasto: {desabasto:.2%}")
    print(f"Faltantes: {meta['faltantes']} · atípicos: {meta['atipicos']}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
