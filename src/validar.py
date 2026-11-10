#!/usr/bin/env python3
"""Valida que la capa Bronce tenga la cobertura mínima exigida en E0."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

MIN_PERIODOS = 36

DENGUE = Path("datos_crudos/dengue_estados_semanal.csv")
CLIMA = Path("datos_crudos/clima_ciudades_semanal.csv")


def periodos(ruta: Path) -> set[tuple[int, int]]:
    with ruta.open(newline="", encoding="utf-8") as fh:
        return {(int(r["anio"]), int(r["semana"])) for r in csv.DictReader(fh)}


def main() -> int:
    fallos = 0
    for ruta in (DENGUE, CLIMA):
        if not ruta.exists():
            print(f"FALLA: no existe {ruta}")
            fallos += 1
            continue
        n = len(periodos(ruta))
        estado = "OK" if n >= MIN_PERIODOS else "FALLA"
        print(f"{estado}: {ruta.name} -> {n} periodos (mínimo {MIN_PERIODOS})")
        if n < MIN_PERIODOS:
            fallos += 1
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
