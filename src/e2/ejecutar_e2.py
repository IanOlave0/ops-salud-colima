#!/usr/bin/env python3
"""Ejecuta la integración E2: snapshot DENUE + Marco -> Plata, Oro y mapa."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.e2.integrar_geoespacial import crear_mapa, integrar_zonas

DEFAULT_SNAPSHOT = Path("datos_crudos/e2/denue_cuantificar_zona.csv")
DEFAULT_META = Path("datos_crudos/e2/denue_snapshot.json")
DEFAULT_MARCO = Path("datos_crudos/e2/marco_geoestadistico_zonas.geojson")
DEFAULT_MARCO_META = Path("datos_crudos/e2/marco_snapshot.json")
DEFAULT_PLATA = Path("datos_plata/e2/publico/farmacias_zona.csv")
DEFAULT_ORO = Path("datos_oro/e2/publico/indicadores_farmacias_zona.csv")
DEFAULT_MAPA = Path("docs/E2/mapa_farmacias_zona.png")


def _sha256(ruta: Path) -> str:
    import hashlib

    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _verificar_hash(ruta: Path, esperado: str | None, nombre: str) -> None:
    if not esperado:
        raise ValueError(f"metadata {nombre} sin sha256")
    obtenido = _sha256(ruta)
    if obtenido != esperado:
        raise ValueError(
            f"hash de {nombre} no coincide: esperado {esperado}, obtenido {obtenido}"
        )


def ejecutar(
    snapshot: Path = DEFAULT_SNAPSHOT,
    metadata: Path = DEFAULT_META,
    marco: Path = DEFAULT_MARCO,
    marco_metadata: Path = DEFAULT_MARCO_META,
    plata: Path = DEFAULT_PLATA,
    oro: Path = DEFAULT_ORO,
    mapa: Path = DEFAULT_MAPA,
) -> dict:
    conteos = pd.read_csv(snapshot, dtype=str)
    meta_denue = json.loads(metadata.read_text(encoding="utf-8"))
    meta_marco = json.loads(marco_metadata.read_text(encoding="utf-8"))
    _verificar_hash(snapshot, meta_denue.get("sha256"), "snapshot DENUE")
    _verificar_hash(marco, meta_marco.get("sha256"), "Marco")
    if not str(meta_marco.get("version", "")).strip():
        raise ValueError("metadata Marco sin versión")
    zonas = gpd.read_file(marco)

    plata_df, oro_df = integrar_zonas(conteos, zonas, meta_denue, meta_marco)
    plata.parent.mkdir(parents=True, exist_ok=True)
    oro.parent.mkdir(parents=True, exist_ok=True)
    plata_df.to_csv(plata, index=False, encoding="utf-8", lineterminator="\n")
    oro_df.drop(columns="geometry").to_csv(
        oro, index=False, encoding="utf-8", lineterminator="\n", float_format="%.6f"
    )
    crear_mapa(oro_df, mapa)
    return {
        "plata": str(plata),
        "oro": str(oro),
        "mapa": str(mapa),
        "filas_plata": len(plata_df),
        "filas_oro": len(oro_df),
        "marco_version": meta_marco["version"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_META)
    parser.add_argument("--marco", type=Path, default=DEFAULT_MARCO)
    parser.add_argument("--marco-metadata", type=Path, default=DEFAULT_MARCO_META)
    parser.add_argument("--plata", type=Path, default=DEFAULT_PLATA)
    parser.add_argument("--oro", type=Path, default=DEFAULT_ORO)
    parser.add_argument("--mapa", type=Path, default=DEFAULT_MAPA)
    args = parser.parse_args(argv)
    datos = ejecutar(
        snapshot=args.snapshot,
        metadata=args.metadata,
        marco=args.marco,
        marco_metadata=args.marco_metadata,
        plata=args.plata,
        oro=args.oro,
        mapa=args.mapa,
    )
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
