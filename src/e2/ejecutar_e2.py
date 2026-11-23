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
DEFAULT_PLATA = Path("datos_plata/e2/publico/farmacias_zona.csv")
DEFAULT_ORO = Path("datos_oro/e2/publico/indicadores_farmacias_zona.csv")
DEFAULT_MAPA = Path("docs/E2/mapa_farmacias_zona.png")


def ejecutar(
    snapshot: Path = DEFAULT_SNAPSHOT,
    metadata: Path = DEFAULT_META,
    marco: Path = DEFAULT_MARCO,
    plata: Path = DEFAULT_PLATA,
    oro: Path = DEFAULT_ORO,
    mapa: Path = DEFAULT_MAPA,
) -> dict:
    conteos = pd.read_csv(snapshot, dtype=str)
    meta_denue = json.loads(metadata.read_text(encoding="utf-8"))
    zonas = gpd.read_file(marco)
    meta_marco = {
        "version": zonas.attrs.get("version") or meta_denue.get("marco_version") or "2025-12",
        "sha256": _sha256(marco),
    }
    # El GeoJSON de descargar_marco guarda version en el JSON, no en attrs de GeoPandas.
    if not meta_marco["version"] or meta_marco["version"] == "2025-12":
        payload = json.loads(marco.read_text(encoding="utf-8"))
        meta_marco["version"] = payload.get("version", "2025-12")

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


def _sha256(ruta: Path) -> str:
    import hashlib

    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_META)
    parser.add_argument("--marco", type=Path, default=DEFAULT_MARCO)
    parser.add_argument("--plata", type=Path, default=DEFAULT_PLATA)
    parser.add_argument("--oro", type=Path, default=DEFAULT_ORO)
    parser.add_argument("--mapa", type=Path, default=DEFAULT_MAPA)
    args = parser.parse_args(argv)
    datos = ejecutar(
        snapshot=args.snapshot,
        metadata=args.metadata,
        marco=args.marco,
        plata=args.plata,
        oro=args.oro,
        mapa=args.mapa,
    )
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
