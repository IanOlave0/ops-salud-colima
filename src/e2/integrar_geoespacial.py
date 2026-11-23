# src/e2/integrar_geoespacial.py
"""Integración geoespacial de conteos DENUE con polígonos del Marco Geoestadístico."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

from src.e2.catalogo_scian import CODIGOS_FARMACIA


def _validar_metadatos(metadata: dict[str, Any], claves_requeridas: list[str], nombre: str) -> None:
    """Verifica que los metadatos de linaje estén completos. Falla si faltan."""
    faltantes = [k for k in claves_requeridas if k not in metadata or not metadata[k]]
    if faltantes:
        raise ValueError(f"Metadatos de {nombre} incompletos. Faltan: {faltantes}")


def integrar_zonas(
    conteos: pd.DataFrame,
    zonas: gpd.GeoDataFrame,
    metadata_denue: dict[str, Any],
    metadata_marco: dict[str, Any],
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """
    Une los conteos agregados de DENUE con los polígonos del Marco Geoestadístico.
    """
    # 1. Validar linaje (Trazabilidad estricta)
    _validar_metadatos(metadata_denue, ["edicion", "query_id", "sha256", "ingestado_en"], "DENUE")
    _validar_metadatos(metadata_marco, ["version", "sha256"], "Marco")

    # 2. Validar duplicados en conteos (Llave: zona, actividad, estrato)
    conteos = conteos.copy()
    conteos["zona_codigo"] = conteos["zona_codigo"].astype(str).str.zfill(5)
    
    # Si no viene la columna estrato, la agregamos temporalmente como 0 para la validación
    if "estrato" not in conteos.columns:
        conteos["estrato"] = 0

    if conteos.duplicated(subset=["zona_codigo", "actividad_scian", "estrato"]).any():
        raise ValueError("Duplicados detectados en conteos. La llave zona/actividad/estrato debe ser única.")

    # 3. Validar geometrías duplicadas
    zonas = zonas.copy()
    zonas["zona_codigo"] = zonas["zona_codigo"].astype(str).str.zfill(5)
    if zonas["zona_codigo"].duplicated().any():
        raise ValueError("Duplicados detectados en el GeoDataFrame. 'zona_codigo' debe ser único.")

    # 4. Pivotear actividades. NO usamos fill_value=0 para no inventar ceros.
    plata = (
        conteos.pivot_table(
            index="zona_codigo",
            columns="actividad_scian",
            values="establecimientos",
            aggfunc="sum" # Seguro porque ya validamos que no hay duplicados
        )
        .reset_index()
    )
    
    # Renombrar columnas
    plata = plata.rename(
        columns={
            "464111": "farmacias_464111",
            "464112": "farmacias_464112",
        }
    )
    
    # Si una actividad no existe en absoluto, creamos la columna llena de NA (no de 0)
    for col in ("farmacias_464111", "farmacias_464112"):
        if col not in plata.columns:
            plata[col] = pd.NA
            
    # Sumamos. Si una es NA, el total será NA (lo cual es correcto, no asumimos 0).
    plata["farmacias_total"] = plata["farmacias_464111"] + plata["farmacias_464112"]

    # 5. Unir con polígonos (left join)
    oro = zonas.merge(plata, on="zona_codigo", how="left")

    # 6. Reproyectar a CRS métrico *equal-area* (EPSG:6933)
    crs_metrico = "EPSG:6933"
    oro_proj = oro.to_crs(crs_metrico)

    # 7. Calcular área en km²
    oro["area_km2"] = oro_proj.geometry.area / 1_000_000.0
    oro.loc[oro["area_km2"] <= 0, "area_km2"] = pd.NA

    # 8. Densidad (si hay total y área)
    oro["farmacias_por_km2"] = oro["farmacias_total"] / oro["area_km2"]

    # 9. Linaje: propagar metadatos (ya validados)
    oro["denue_edicion"] = metadata_denue["edicion"]
    oro["denue_query_id"] = metadata_denue["query_id"]
    oro["denue_sha256"] = metadata_denue["sha256"]
    oro["denue_ingestado_en"] = metadata_denue["ingestado_en"]
    oro["marco_version"] = metadata_marco["version"]
    oro["marco_sha256"] = metadata_marco["sha256"]
    oro["transformacion_version"] = "e2-v2"

    return plata, oro


def crear_mapa(
    zonas_oro: gpd.GeoDataFrame,
    output: Path,
) -> None:
    """Genera un mapa coroplético de densidad de farmacias por km²."""
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
    ax.set_title("Densidad de farmacias por zona — Colima")
    ax.set_axis_off()

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