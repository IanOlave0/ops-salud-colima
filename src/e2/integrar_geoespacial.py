#!/usr/bin/env python3
"""Integración geoespacial de conteos DENUE con polígonos del Marco Geoestadístico."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

from src.e2.catalogo_scian import CODIGOS_FARMACIA

COLUMNAS_CONTEO = [
    "zona_codigo",
    "actividad_scian",
    "estrato",
    "establecimientos",
    "estado_query",
]
ESTADOS_QUERY = {"completo", "incompleto", "sin_respuesta"}
_RE_ZONA = re.compile(r"^\d{5}$")
_RE_SHA = re.compile(r"^[0-9a-f]{64}$")
META_DENUE = ("edicion", "query_id", "sha256", "zip_sha256", "ingestado_en", "estado_query")
META_MARCO = ("version", "sha256", "fuente_sha256")
TRANSFORMACION_VERSION = "e2-v1"
CRS_METRICO = "EPSG:6933"


def _validar_metadata(
    metadata: dict[str, Any], requeridas: tuple[str, ...], nombre: str
) -> None:
    faltan = [clave for clave in requeridas if not str(metadata.get(clave, "")).strip()]
    if faltan:
        raise ValueError(f"metadata {nombre} incompleta: faltan {', '.join(faltan)}")
    for clave in ("sha256", "zip_sha256", "fuente_sha256"):
        if clave in requeridas and not _RE_SHA.match(str(metadata[clave])):
            raise ValueError(f"metadata {nombre}: {clave} no es SHA-256 hexadecimal")


def _normalizar_conteos(conteos: pd.DataFrame) -> pd.DataFrame:
    faltan = [c for c in COLUMNAS_CONTEO if c not in conteos.columns]
    if faltan:
        raise ValueError(f"faltan columnas de conteos: {', '.join(faltan)}")
    df = conteos[COLUMNAS_CONTEO].copy()
    for columna in ("zona_codigo", "actividad_scian", "estrato", "estado_query"):
        df[columna] = df[columna].astype(str).str.strip()
    if not df["zona_codigo"].str.match(_RE_ZONA).all():
        raise ValueError("zona_codigo debe tener cinco dígitos y conservarse como texto")
    if not set(df["actividad_scian"]).issubset(set(CODIGOS_FARMACIA)):
        raise ValueError("actividad_scian fuera del catálogo auditado 464111/464112")
    if not set(df["estado_query"]).issubset(ESTADOS_QUERY):
        raise ValueError("estado_query inválido")
    df["establecimientos"] = pd.to_numeric(df["establecimientos"], errors="coerce")
    if df["establecimientos"].isna().any() or (df["establecimientos"] < 0).any():
        raise ValueError("establecimientos debe ser entero no negativo")
    if df.duplicated(["zona_codigo", "actividad_scian", "estrato"]).any():
        raise ValueError("conteos duplicados por zona/actividad/estrato")
    return df


def _validar_zonas(zonas: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if not isinstance(zonas, gpd.GeoDataFrame):
        raise ValueError("zonas debe ser un GeoDataFrame")
    if zonas.crs is None:
        raise ValueError("zonas debe declarar CRS")
    if "zona_codigo" not in zonas.columns or "geometry" not in zonas.columns:
        raise ValueError("zonas requiere zona_codigo y geometry")
    gdf = zonas.copy()
    gdf["zona_codigo"] = gdf["zona_codigo"].astype(str).str.strip()
    if not gdf["zona_codigo"].str.match(_RE_ZONA).all():
        raise ValueError("zona_codigo de polígonos debe tener cinco dígitos")
    if gdf["zona_codigo"].duplicated().any():
        raise ValueError("zona_codigo duplicada en polígonos")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise ValueError("hay geometrías nulas o vacías")
    if not gdf.geometry.is_valid.all():
        raise ValueError("hay geometrías inválidas")
    return gdf


def integrar_zonas(
    conteos: pd.DataFrame,
    zonas: gpd.GeoDataFrame,
    metadata_denue: dict[str, Any],
    metadata_marco: dict[str, Any],
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Une conteos DENUE agregados con polígonos y produce Plata/Oro.

    Una consulta incompleta deja el valor como faltante; no se convierte a
    cero. Los ceros solo se rellenan cuando la metadata declara una cobertura
    completa y la zona no tiene consultas incompletas.
    """
    _validar_metadata(metadata_denue, META_DENUE, "DENUE")
    _validar_metadata(metadata_marco, META_MARCO, "Marco")
    df = _normalizar_conteos(conteos)
    gdf = _validar_zonas(zonas)
    faltan_poligonos = set(df["zona_codigo"]) - set(gdf["zona_codigo"])
    if faltan_poligonos:
        raise ValueError(
            "zonas con conteo sin polígono: " + ", ".join(sorted(faltan_poligonos))
        )

    actividades = sorted(set(df["actividad_scian"]) | set(CODIGOS_FARMACIA))
    pivot = df.pivot_table(
        index="zona_codigo",
        columns="actividad_scian",
        values="establecimientos",
        aggfunc="sum",
    )
    no_completas = df.loc[
        df["estado_query"].ne("completo"), ["zona_codigo", "actividad_scian"]
    ].drop_duplicates()
    zonas_incompletas = set(no_completas["zona_codigo"])
    for _, fila in no_completas.iterrows():
        if fila["zona_codigo"] in pivot.index and fila["actividad_scian"] in pivot.columns:
            pivot.loc[fila["zona_codigo"], fila["actividad_scian"]] = pd.NA

    pivot = pivot.reindex(index=sorted(gdf["zona_codigo"]), columns=actividades)
    zonas_conteo = set(df["zona_codigo"])
    zonas_ausentes = set(pivot.index) - zonas_conteo
    if metadata_denue.get("estado_query") == "completo":
        for zona in pivot.index:
            if zona not in zonas_incompletas and zona not in zonas_ausentes:
                pivot.loc[zona] = pivot.loc[zona].fillna(0)

    plata = pivot.reset_index().rename(
        columns={
            "464111": "farmacias_464111",
            "464112": "farmacias_464112",
        }
    )
    for columna in ("farmacias_464111", "farmacias_464112"):
        if columna not in plata.columns:
            plata[columna] = float("nan")
    plata["farmacias_total"] = plata[
        ["farmacias_464111", "farmacias_464112"]
    ].sum(axis=1, min_count=2)
    plata["estado_query"] = [
        "sin_respuesta" if z in zonas_ausentes
        else "incompleto" if z in zonas_incompletas
        else "completo"
        for z in plata["zona_codigo"]
    ]

    oro = gdf.merge(plata, on="zona_codigo", how="left", validate="one_to_one")
    proyeccion = oro.to_crs(CRS_METRICO)
    oro["area_km2"] = proyeccion.geometry.area / 1_000_000.0
    if (oro["area_km2"] <= 0).any():
        raise ValueError("hay zonas con área cero o negativa")
    oro["farmacias_por_km2"] = oro["farmacias_total"] / oro["area_km2"]

    oro["denue_edicion"] = str(metadata_denue["edicion"])
    oro["denue_query_id"] = str(metadata_denue["query_id"])
    oro["denue_sha256"] = str(metadata_denue["sha256"])
    oro["denue_zip_sha256"] = str(metadata_denue["zip_sha256"])
    oro["denue_ingestado_en"] = str(metadata_denue["ingestado_en"])
    oro["marco_version"] = str(metadata_marco["version"])
    oro["marco_sha256"] = str(metadata_marco["sha256"])
    oro["marco_fuente_sha256"] = str(metadata_marco["fuente_sha256"])
    oro["transformacion_version"] = TRANSFORMACION_VERSION
    oro = oro.sort_values("zona_codigo", kind="mergesort").reset_index(drop=True)
    return plata, oro


def crear_mapa(zonas_oro: gpd.GeoDataFrame, output: Path) -> None:
    """Genera un mapa coroplético agregado, sin ubicaciones de unidades."""
    if zonas_oro.crs is None:
        raise ValueError("zonas_oro debe declarar CRS")
    gdf = zonas_oro.to_crs("EPSG:4326")
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    try:
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
        edicion = gdf["denue_edicion"].iloc[0] if len(gdf) else "sin dato"
        marco = gdf["marco_version"].iloc[0] if len(gdf) else "sin dato"
        ax.set_title(
            f"Densidad de farmacias por zona — Colima\n"
            f"DENUE {edicion} · Marco {marco}"
        )
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
    finally:
        plt.close(fig)
