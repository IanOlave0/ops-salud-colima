#!/usr/bin/env python3
"""Descarga y filtra el Marco Geoestadístico municipal de Colima."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import requests

URL_MARCO_COLIMA = "https://gaia.inegi.org.mx/wscatgeo/v2/geo/mgem/06"
VERSION_DEFAULT = "2025-12"


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def filtrar_marco(payload: dict) -> dict:
    """Conserva solo propiedades públicas y claves necesarias de los municipios."""
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("el Marco no contiene features")
    salida = []
    for feature in features:
        props = feature.get("properties") or {}
        cvegeo = props.get("cvegeo") or (
            str(props.get("cve_ent", "")).zfill(2)
            + str(props.get("cve_mun", "")).zfill(3)
        )
        geometry = feature.get("geometry")
        if not cvegeo or not geometry:
            raise ValueError("feature del Marco sin clave o geometría")
        salida.append(
            {
                "type": "Feature",
                "properties": {
                    "zona_codigo": str(cvegeo).zfill(5),
                    "municipio": props.get("nomgeo") or props.get("municipio") or "",
                    "pob_total": props.get("pob_total", ""),
                },
                "geometry": geometry,
            }
        )
    return {
        "type": "FeatureCollection",
        "metadata_fuente": payload.get("metadatos", {}),
        "features": salida,
    }


def descargar_marco(
    destino: Path,
    url: str = URL_MARCO_COLIMA,
    version: str = VERSION_DEFAULT,
) -> dict[str, str]:
    respuesta = requests.get(url, timeout=120)
    respuesta.raise_for_status()
    filtrado = filtrar_marco(respuesta.json())
    filtrado["version"] = version
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(filtrado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "path": str(destino),
        "version": version,
        "sha256": _sha256(destino),
        "features": str(len(filtrado["features"])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("datos_crudos/e2/marco_geoestadistico_zonas.geojson"))
    parser.add_argument("--url", default=URL_MARCO_COLIMA)
    parser.add_argument("--version", default=VERSION_DEFAULT)
    args = parser.parse_args(argv)
    datos = descargar_marco(args.output, args.url, args.version)
    print(f"Marco: {datos['path']}")
    print(f"Municipios: {datos['features']} · versión: {datos['version']}")
    print(f"sha256: {datos['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
