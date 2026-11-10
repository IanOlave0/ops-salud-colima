#!/usr/bin/env python3
"""Capa Bronce: extrae el Panorama Epidemiológico de Dengue (DGE, Secretaría de Salud).

Fuente: https://www.gob.mx/salud/documentos/panorama-epidemiologico-de-dengue-2026
Salida: datos_crudos/dengue_estados_semanal.csv

El script es idempotente: descarga solo las semanas que faltan y refresca las
últimas REFRESH_WEEKS para capturar las actualizaciones de la vigilancia.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

INDICE = "https://www.gob.mx/salud/documentos/panorama-epidemiologico-de-dengue-2026"
ANIO = 2026
SALIDA = Path("datos_crudos/dengue_estados_semanal.csv")
REPORTE = Path("datos_crudos/_reporte_dengue.json")
REFRESH_WEEKS = 3
TIMEOUT = 90
UA = "ops-salud-colima/0.1 (proyecto academico; contacto: iolave0646@gmail.com)"

# La tabla estatal del panorama tiene 11 columnas numéricas.
COLUMNAS = [
    "probables_2025",
    "probables_2026",
    "dng_2025",
    "dng_2026",
    "dcsa_dg_2025",
    "dcsa_dg_2026",
    "confirmados_2025",
    "confirmados_2026",
    "defunciones_2025",
    "defunciones_2026",
]

ENTIDADES = [
    "AGUASCALIENTES", "BAJA CALIFORNIA", "BAJA CALIFORNIA SUR", "CAMPECHE",
    "CHIAPAS", "CHIHUAHUA", "CIUDAD DE MEXICO", "COAHUILA", "COLIMA",
    "DURANGO", "GUANAJUATO", "GUERRERO", "HIDALGO", "JALISCO", "MEXICO",
    "MICHOACAN", "MORELOS", "NAYARIT", "NUEVO LEON", "OAXACA", "PUEBLA",
    "QUERETARO", "QUINTANA ROO", "SAN LUIS POTOSI", "SINALOA", "SONORA",
    "TABASCO", "TAMAULIPAS", "TLAXCALA", "VERACRUZ", "YUCATAN", "ZACATECAS",
]

# Nombre oficial para la salida (con acentos).
MOSTRAR = {
    "MEXICO": "México",
    "MICHOACAN": "Michoacán",
    "NUEVO LEON": "Nuevo León",
    "QUERETARO": "Querétaro",
    "SAN LUIS POTOSI": "San Luis Potosí",
    "YUCATAN": "Yucatán",
    "CIUDAD DE MEXICO": "Ciudad de México",
}

NUM_RE = re.compile(r"^[\d,]+$")


def normaliza(texto: str) -> str:
    """Mayúsculas sin acentos para comparar nombres de entidades."""
    texto = unicodedata.normalize("NFD", texto.upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def lista_pdfs(html: str) -> dict[int, str]:
    """Devuelve {semana: url} a partir de los enlaces del índice."""
    enlaces = re.findall(r'href="(/cms/uploads/attachment/file/[^"]+\.pdf)"', html)
    semanas: dict[int, str] = {}
    for rel in enlaces:
        numeros = re.findall(r"(\d+)", rel.rsplit("/", 1)[-1])
        if not numeros:
            continue
        semana = int(numeros[-1])
        if 1 <= semana <= 53 and semana not in semanas:
            semanas[semana] = "https://www.gob.mx" + rel
    return dict(sorted(semanas.items()))


def pdf_a_texto(pdf: Path) -> str:
    salida = pdf.with_suffix(".txt")
    subprocess.run(
        ["pdftotext", "-layout", str(pdf), str(salida)],
        check=True, capture_output=True,
    )
    return salida.read_text(encoding="utf-8", errors="ignore")


def squash(texto: str) -> str:
    """Quita todos los espacios: los PDFs escriben 'COLI M A'."""
    return re.sub(r"\s+", "", normaliza(texto))


ENTIDADES_SQUASH = {squash(e): e for e in ENTIDADES}


def extrae_filas(texto: str) -> dict[str, list[int]]:
    """Extrae {entidad: [11 valores]} de la tabla estatal.

    En algunos PDFs el nombre de la entidad llega con espacios internos
    ('COLI M A'), por eso se separa nombre y números por el primer dígito.
    """
    filas: dict[str, list[int]] = {}
    for linea in texto.splitlines():
        norm = normaliza(linea)
        if not norm:
            continue
        pos = re.search(r"\d", norm)
        if not pos:
            continue
        nombre = squash(norm[: pos.start()])
        entidad = ENTIDADES_SQUASH.get(nombre)
        if not entidad:
            continue
        tokens = norm[pos.start():].split()
        if len(tokens) != len(COLUMNAS) or not all(NUM_RE.match(t) for t in tokens):
            continue
        filas[MOSTRAR.get(entidad, entidad.title())] = [int(t.replace(",", "")) for t in tokens]
    return filas


def lee_existente() -> dict[tuple[int, int, str], dict[str, str]]:
    if not SALIDA.exists():
        return {}
    with SALIDA.open(newline="", encoding="utf-8") as fh:
        return {
            (int(r["anio"]), int(r["semana"]), r["entidad"]): r
            for r in csv.DictReader(fh)
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-descarga todas las semanas")
    args = parser.parse_args()

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": UA})

    resp = sesion.get(INDICE, timeout=TIMEOUT)
    resp.raise_for_status()
    semanas = lista_pdfs(resp.text)
    if not semanas:
        print("ERROR: no se encontraron PDFs en el índice", file=sys.stderr)
        return 1

    existentes = {} if args.force else lee_existente()
    max_semana = max((s for (_, s, _) in existentes), default=0)
    objetivo = [
        s for s in semanas
        if args.force or s > max_semana - REFRESH_WEEKS
    ]

    nuevas, fallidas, reporte = 0, [], {}
    for semana in objetivo:
        url = semanas[semana]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pdf = Path(tmp) / f"semana_{semana}.pdf"
                r = sesion.get(url, timeout=TIMEOUT)
                r.raise_for_status()
                pdf.write_bytes(r.content)
                filas = extrae_filas(pdf_a_texto(pdf))
            if len(filas) < 30:
                raise ValueError(f"solo {len(filas)} entidades extraídas")
            for entidad, valores in filas.items():
                existentes[(ANIO, semana, entidad)] = {
                    "anio": ANIO,
                    "semana": semana,
                    "entidad": entidad,
                    **dict(zip(COLUMNAS, valores)),
                    "url": url,
                    "extraido_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                nuevas += 1
            reporte[semana] = {"entidades": len(filas), "estado": "ok"}
            print(f"SE {semana:02d}: {len(filas)} entidades")
        except Exception as exc:  # noqa: BLE001
            fallidas.append({"semana": semana, "error": str(exc)})
            reporte[semana] = {"estado": "error", "error": str(exc)}
            print(f"SE {semana:02d}: ERROR {exc}", file=sys.stderr)

    campos = ["anio", "semana", "entidad", *COLUMNAS, "url", "extraido_en"]
    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for clave in sorted(existentes):
            writer.writerow(existentes[clave])

    cobertura = len({s for (_, s, _) in existentes})
    REPORTE.write_text(json.dumps({
        "fuente": INDICE,
        "semanas_publicadas": len(semanas),
        "semanas_con_datos": cobertura,
        "filas": len(existentes),
        "fallidas": fallidas,
        "detalle": reporte,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nTotal: {len(existentes)} filas, {cobertura} semanas, {len(fallidas)} fallos")
    return 0 if cobertura >= 36 else 1


if __name__ == "__main__":
    raise SystemExit(main())
