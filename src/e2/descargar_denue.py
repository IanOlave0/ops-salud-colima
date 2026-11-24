#!/usr/bin/env python3
"""E2: agrega la descarga oficial DENUE de Colima sin publicar registros individuales.

La fuente elegida es el archivo masivo oficial por entidad (DENUE 05/2026),
que no requiere token. El resultado público es un conteo por zona municipal,
actividad SCIAN y estrato; nunca conserva nombres, domicilios, contactos ni
coordenadas de establecimientos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.e2.catalogo_scian import CODIGOS_FARMACIA

URL_BULK_COLIMA = "https://www.inegi.org.mx/contenidos/masiva/denue/denue_06_csv.zip"
EDICION_DEFAULT = "05/2026"
MAX_BYTES = 100 * 1024 * 1024
ZIP_SHA256_POR_EDICION = {
    "05/2026": "948e292e567ce16a8b7485f15846ddaaf9c9cda6fda9be07334bb6afc5480af6",
}
ZIP_SHA256_05_2026 = ZIP_SHA256_POR_EDICION[EDICION_DEFAULT]
ARCHIVO_CSV = "conjunto_de_datos/denue_inegi_06_.csv"
COLUMNAS_SNAPSHOT = [
    "zona_codigo",
    "actividad_scian",
    "estrato",
    "establecimientos",
    "estado_query",
    "denue_edicion",
    "denue_query_id",
    "ingestado_en",
]
COLUMNAS_ENTRADA = ["cve_ent", "cve_mun", "codigo_act", "per_ocu"]


class ErrorDenue(ValueError):
    """La fuente DENUE no cumple el contrato esperado."""


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _query_id(edicion: str, actividades: list[str]) -> str:
    parametros = {
        "fuente": "DENUE",
        "metodo": "descarga_masiva_entidad",
        "edicion": edicion,
        "entidad": "06",
        "actividades": sorted(actividades),
    }
    return hashlib.sha256(
        json.dumps(parametros, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def leer_csv_denue(ruta: Path) -> pd.DataFrame:
    """Lee el CSV oficial de la entidad; DENUE usa Latin-1."""
    return pd.read_csv(ruta, dtype=str, encoding="latin-1", low_memory=False)


def descargar_bulk(destino: Path, url: str = URL_BULK_COLIMA) -> Path:
    """Descarga el ZIP oficial por entidad sin token ni scraping."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    respuesta = requests.get(url, timeout=120, stream=True)
    try:
        respuesta.raise_for_status()
        declarado = respuesta.headers.get("Content-Length")
        if declarado and int(declarado) > MAX_BYTES:
            raise ErrorDenue("el ZIP oficial excede el límite de tamaño permitido")
        contenido = bytearray()
        for bloque in respuesta.iter_content(chunk_size=8192):
            contenido.extend(bloque)
            if len(contenido) > MAX_BYTES:
                raise ErrorDenue("el ZIP oficial excede el límite de tamaño permitido")
    finally:
        respuesta.close()
    destino.write_bytes(bytes(contenido))
    return destino


def extraer_csv(zip_path: Path, destino_dir: Path) -> Path:
    """Extrae únicamente el CSV de datos del ZIP oficial."""
    with zipfile.ZipFile(zip_path) as archivo:
        try:
            archivo.extract(ARCHIVO_CSV, destino_dir)
        except KeyError as exc:
            raise ErrorDenue(f"el ZIP no contiene {ARCHIVO_CSV}") from exc
    return destino_dir / ARCHIVO_CSV


def agregar_farmacias(
    df: pd.DataFrame,
    edicion: str = EDICION_DEFAULT,
    ingestado_en: str | None = None,
) -> pd.DataFrame:
    """Agrega farmacias por municipio, clase SCIAN y estrato.

    La descarga masiva cubre toda la entidad, por lo que una combinación
    ausente se registra como cero observado (`estado_query="completo"`). No
    se conserva ningún campo individual.
    """
    faltan = [c for c in COLUMNAS_ENTRADA if c not in df.columns]
    if faltan:
        raise ErrorDenue(f"faltan columnas DENUE: {', '.join(faltan)}")

    limpio = df[COLUMNAS_ENTRADA].copy()
    for columna in ("cve_ent", "cve_mun", "codigo_act", "per_ocu"):
        limpio[columna] = limpio[columna].astype(str).str.strip()
    limpio = limpio[limpio["cve_ent"].eq("06")]
    if limpio.empty:
        raise ErrorDenue("la fuente no contiene registros de Colima")

    permitidas = set(CODIGOS_FARMACIA)
    limpio["zona_codigo"] = limpio["cve_ent"].str.zfill(2) + limpio["cve_mun"].str.zfill(3)
    todas_las_zonas = sorted(limpio["zona_codigo"].unique())
    limpio = limpio[limpio["codigo_act"].isin(permitidas)].copy()
    if limpio.empty:
        raise ErrorDenue("la fuente no contiene farmacias del catálogo auditado")

    conteos = (
        limpio.groupby(
            ["zona_codigo", "codigo_act", "per_ocu"], sort=True, as_index=False
        )
        .size()
        .rename(
            columns={
                "codigo_act": "actividad_scian",
                "per_ocu": "estrato",
                "size": "establecimientos",
            }
        )
    )

    # Completar combinaciones ausentes con cero observado: el archivo masivo
    # cubre todos los municipios de la entidad, incluso los que no tienen
    # farmacias del catálogo.
    zonas = todas_las_zonas
    actividades = sorted(permitidas)
    completo = pd.MultiIndex.from_product(
        [zonas, actividades], names=["zona_codigo", "actividad_scian"]
    ).to_frame(index=False)
    presentes = conteos[["zona_codigo", "actividad_scian"]].drop_duplicates()
    faltantes = completo.merge(
        presentes, on=["zona_codigo", "actividad_scian"], how="left", indicator=True
    )
    faltantes = faltantes[faltantes["_merge"] == "left_only"][
        ["zona_codigo", "actividad_scian"]
    ].copy()
    if not faltantes.empty:
        faltantes["estrato"] = "0"
        faltantes["establecimientos"] = 0
        conteos = pd.concat([conteos, faltantes], ignore_index=True)

    ahora = ingestado_en or datetime.now(timezone.utc).isoformat(timespec="seconds")
    conteos["estado_query"] = "completo"
    conteos["denue_edicion"] = edicion
    conteos["denue_query_id"] = _query_id(edicion, actividades)
    conteos["ingestado_en"] = ahora
    conteos["establecimientos"] = conteos["establecimientos"].astype(int)
    return (
        conteos[COLUMNAS_SNAPSHOT]
        .sort_values(["zona_codigo", "actividad_scian", "estrato"], kind="mergesort")
        .reset_index(drop=True)
    )


def guardar_snapshot(
    df: pd.DataFrame, metadata: dict, output_dir: Path
) -> dict[str, str]:
    """Guarda CSV agregado y metadata con SHA; nunca guarda token."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "denue_cuantificar_zona.csv"
    json_path = output_dir / "denue_snapshot.json"
    df.to_csv(csv_path, index=False, encoding="utf-8", lineterminator="\n")
    datos = {
        **metadata,
        "archivo_csv": csv_path.name,
        "sha256": _sha256(csv_path),
        "columnas": COLUMNAS_SNAPSHOT,
        "filas": len(df),
        "url_fuente": URL_BULK_COLIMA,
    }
    json_path.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "csv": str(csv_path),
        "metadata": str(json_path),
        "sha256": datos["sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("datos_crudos/e2"))
    parser.add_argument("--edicion", default=EDICION_DEFAULT)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        zip_path = args.zip or descargar_bulk(tmpdir / "denue_06_csv.zip")
        zip_sha256 = _sha256(zip_path)
        esperado = ZIP_SHA256_POR_EDICION.get(args.edicion)
        if not esperado:
            raise ErrorDenue(
                f"edición {args.edicion} no autorizada; agrega su SHA a "
                "ZIP_SHA256_POR_EDICION tras verificarla en INEGI"
            )
        if zip_sha256 != esperado:
            raise ErrorDenue(
                "el ZIP descargado no coincide con el SHA esperado para la edición "
                f"{args.edicion}"
            )
        csv_path = extraer_csv(zip_path, tmpdir / "denue06")

        df = leer_csv_denue(csv_path)
        ingestado_en = datetime.now(timezone.utc).isoformat(timespec="seconds")
        agregado = agregar_farmacias(
            df, edicion=args.edicion, ingestado_en=ingestado_en
        )
        destinos = guardar_snapshot(
            agregado,
            {
                "edicion": args.edicion,
                "metodo": "descarga_masiva_entidad",
                "entidad": "06",
                "actividades": sorted(CODIGOS_FARMACIA),
                "estado_query": "completo",
                "query_id": _query_id(args.edicion, sorted(CODIGOS_FARMACIA)),
                "ingestado_en": ingestado_en,
                "zip_sha256": zip_sha256,
            },
            args.output_dir,
        )
    print(f"Snapshot: {destinos['csv']}")
    print(f"Metadata: {destinos['metadata']}")
    print(f"Filas: {len(agregado)} · sha256: {destinos['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
