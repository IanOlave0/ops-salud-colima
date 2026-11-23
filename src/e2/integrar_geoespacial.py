# src/e2/integrar_geoespacial.py
"""Integración geoespacial de conteos DENUE con polígonos del Marco Geoestadístico."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

from src.e2.catalogo_scian import CODIGOS_FARMACIA


def _sha256_file(path: Path) -> str:
    """Calcula el SHA-256 de un archivo para el linaje."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def integrar_zonas(
    conteos: pd.DataFrame,
    zonas: gpd.GeoDataFrame,
    metadata_denue: dict[str, Any],
    metadata_marco: dict[str, Any],
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """
    Une los conteos agregados de DENUE con los polígonos del Marco Geoestadístico.
    """
    # 1. Validar que zona_codigo sea texto y conservar ceros (ej. "06001")
    conteos = conteos.copy()
    conteos["zona_codigo"] = conteos["zona_codigo"].astype(str).str.zfill(5)

    # 2. Pivotear actividades a columnas
    plata = (
        conteos.pivot_table(
            index="zona_codigo",
            columns="actividad_scian",
            values="establecimientos",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    
    # Renombrar columnas de actividad
    plata = plata.rename(
        columns={
            "464111": "farmacias_464111",
            "464112": "farmacias_464112",
        }
    )
    # Asegurar que existan ambas columnas
    for col in ("farmacias_464111", "farmacias_464112"):
        if col not in plata.columns:
            plata[col] = 0
            
    plata["farmacias_total"] = plata["farmacias_464111"] + plata["farmacias_464112"]

    # 3. Unir con polígonos (left join para no perder zonas sin polígono)
    zonas = zonas.copy()
    zonas["zona_codigo"] = zonas["zona_codigo"].astype(str).str.zfill(5)
    oro = zonas.merge(plata, on="zona_codigo", how="left")

    # 4. Marcar zonas sin conteo como faltantes (no convertir a cero automáticamente)
    sin_conteo = oro["farmacias_total"].isna()
    oro.loc[sin_conteo, "farmacias_total"] = pd.NA

    # 5. Reproyectar a CRS métrico *equal-area* (EPSG:6933) para área en km²
    crs_metrico = "EPSG:6933"
    oro_proj = oro.to_crs(crs_metrico)

    # 6. Calcular área en km² (la unidad del CRS métrico es el metro)
    oro["area_km2"] = oro_proj.geometry.area / 1_000_000.0
    oro.loc[oro["area_km2"] <= 0, "area_km2"] = pd.NA

    # 7. Densidad (solo si hay conteo y área válida)
    oro["farmacias_por_km2"] = oro["farmacias_total"] / oro["area_km2"]

    # 8. Linaje: propagar metadatos para trazabilidad
    oro["denue_edicion"] = metadata_denue.get("edicion", "desconocida")
    oro["denue_query_id"] = metadata_denue.get("query_id", "desconocido")
    oro["denue_sha256"] = metadata_denue.get("sha256", "")
    oro["denue_ingestado_en"] = metadata_denue.get("ingestado_en", "")
    oro["marco_version"] = metadata_marco.get("version", "desconocida")
    oro["marco_sha256"] = metadata_marco.get("sha256", "")
    oro["transformacion_version"] = "e2-v1"

    return plata, oro


def crear_mapa(
    zonas_oro: gpd.GeoDataFrame,
    output: Path,
) -> None:
    """
    Genera un mapa coroplético de densidad de farmacias por km².
    """
    # Trabajar en un CRS adecuado para visualización (WGS84)
    gdf = zonas_oro.to_crs("EPSG:4326")

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    
    gdf.plot(
        column="farmacias_por_km2",
        ax=ax,
        legend=True,
        legend_kwds={
            "label": "Farmacias por km²",
            "orientation": "horizontal",
            "shrink": 0.6,
        },
        cmap="YlOrRd",
        missing_kwds={"color": "lightgrey", "label": "Sin dato"},
        edgecolor="black",
        linewidth=0.3,
    )
    ax.set_title("Densidad de farmacias por zona — Colima (DENUE + Marco Geoestadístico)")
    ax.set_axis_off()

    # Atribución obligatoria (Regla de ética)
    fig.text(
        0.5,
        0.02,
        "Fuente: INEGI, DENUE y Marco Geoestadístico. Elaboración propia.",
        ha="center",
        fontsize=8,
        style="italic",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)