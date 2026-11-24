"""Pruebas de integración geoespacial con contrato E2 estricto."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from src.e2.integrar_geoespacial import crear_mapa, integrar_zonas


def _zonas() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "zona_codigo": ["06001", "06002", "06003"],
            "municipio": ["Colima", "Manzanillo", "Tecomán"],
            "geometry": [
                Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
                Polygon([(1, 0), (1, 1), (2, 1), (2, 0)]),
                Polygon([(2, 0), (2, 1), (3, 1), (3, 0)]),
            ],
        },
        crs="EPSG:4326",
    )


def _conteos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"zona_codigo": "06001", "actividad_scian": "464111", "estrato": "0", "establecimientos": 5, "estado_query": "completo"},
            {"zona_codigo": "06001", "actividad_scian": "464112", "estrato": "0", "establecimientos": 3, "estado_query": "completo"},
            {"zona_codigo": "06002", "actividad_scian": "464111", "estrato": "0", "establecimientos": 2, "estado_query": "completo"},
            {"zona_codigo": "06003", "actividad_scian": "464111", "estrato": "0", "establecimientos": 0, "estado_query": "completo"},
            {"zona_codigo": "06003", "actividad_scian": "464112", "estrato": "0", "establecimientos": 0, "estado_query": "completo"},
        ]
    )


def _meta_denue() -> dict[str, str]:
    return {
        "edicion": "05/2026",
        "query_id": "a" * 64,
        "sha256": "b" * 64,
        "zip_sha256": "d" * 64,
        "ingestado_en": "2026-11-23T00:00:00+00:00",
        "estado_query": "completo",
    }


def _meta_marco() -> dict[str, str]:
    return {"version": "2025-12", "sha256": "c" * 64, "fuente_sha256": "e" * 64}


class IntegracionGeoespacialTest(unittest.TestCase):
    def test_oro_tiene_una_fila_por_zona_y_columnas_de_linaje(self) -> None:
        plata, oro = integrar_zonas(_conteos(), _zonas(), _meta_denue(), _meta_marco())
        self.assertEqual(len(plata), 3)
        self.assertEqual(len(oro), 3)
        self.assertEqual(oro["zona_codigo"].nunique(), len(oro))
        for columna in (
            "denue_edicion", "denue_query_id", "denue_sha256", "denue_ingestado_en",
            "marco_version", "marco_sha256", "transformacion_version",
        ):
            self.assertIn(columna, oro.columns)
            self.assertTrue(oro[columna].notna().all())
        self.assertEqual(set(oro["denue_edicion"]), {"05/2026"})

    def test_conteos_completos_y_ceros_explicitos(self) -> None:
        plata, oro = integrar_zonas(_conteos(), _zonas(), _meta_denue(), _meta_marco())
        fila = oro.loc[oro["zona_codigo"] == "06001"].iloc[0]
        self.assertEqual(int(fila["farmacias_464111"]), 5)
        self.assertEqual(int(fila["farmacias_464112"]), 3)
        self.assertEqual(int(fila["farmacias_total"]), 8)
        sin_filas = oro.loc[oro["zona_codigo"] == "06003"].iloc[0]
        self.assertEqual(int(sin_filas["farmacias_total"]), 0)
        self.assertEqual(sin_filas["estado_query"], "completo")

    def test_zona_sin_filas_se_marca_sin_respuesta(self) -> None:
        conteos = _conteos()
        conteos = conteos[conteos["zona_codigo"] != "06003"]
        _, oro = integrar_zonas(conteos, _zonas(), _meta_denue(), _meta_marco())
        fila = oro.loc[oro["zona_codigo"] == "06003"].iloc[0]
        self.assertTrue(pd.isna(fila["farmacias_total"]))
        self.assertEqual(fila["estado_query"], "sin_respuesta")

    def test_respuesta_incompleta_no_se_convierte_en_cero(self) -> None:
        conteos = _conteos().copy()
        mask = (conteos["zona_codigo"] == "06003") & (
            conteos["actividad_scian"] == "464111"
        )
        conteos.loc[mask, "estado_query"] = "sin_respuesta"
        _, oro = integrar_zonas(conteos, _zonas(), _meta_denue(), _meta_marco())
        fila = oro.loc[oro["zona_codigo"] == "06003"].iloc[0]
        self.assertTrue(pd.isna(fila["farmacias_464111"]))
        self.assertEqual(fila["estado_query"], "incompleto")

    def test_rechaza_duplicados_en_conteos(self) -> None:
        conteos = pd.concat([_conteos(), _conteos().iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            integrar_zonas(conteos, _zonas(), _meta_denue(), _meta_marco())

    def test_rechaza_zonas_duplicadas_o_sin_crs(self) -> None:
        zonas = _zonas()
        duplicadas = pd.concat([zonas, zonas.iloc[[0]]], ignore_index=True)
        with self.assertRaises(ValueError):
            integrar_zonas(_conteos(), gpd.GeoDataFrame(duplicadas, crs="EPSG:4326"), _meta_denue(), _meta_marco())

        sin_crs = _zonas().set_crs(None, allow_override=True)
        with self.assertRaises(ValueError):
            integrar_zonas(_conteos(), sin_crs, _meta_denue(), _meta_marco())

    def test_rechaza_area_cero(self) -> None:
        zonas = _zonas().copy()
        zonas.loc[0, "geometry"] = LineString([(0, 0), (1, 1), (2, 2)])
        with self.assertRaises(ValueError):
            integrar_zonas(_conteos(), zonas, _meta_denue(), _meta_marco())

    def test_rechaza_zona_conteo_sin_poligono(self) -> None:
        conteos = pd.concat(
            [
                _conteos(),
                pd.DataFrame(
                    [{"zona_codigo": "06999", "actividad_scian": "464111", "estrato": "0", "establecimientos": 0, "estado_query": "completo"}]
                ),
            ],
            ignore_index=True,
        )
        with self.assertRaises(ValueError):
            integrar_zonas(conteos, _zonas(), _meta_denue(), _meta_marco())

    def test_rechaza_linaje_incompleto(self) -> None:
        with self.assertRaises(ValueError):
            integrar_zonas(_conteos(), _zonas(), {"edicion": "05/2026"}, _meta_marco())

    def test_densidad_usa_area_metrica(self) -> None:
        _, oro = integrar_zonas(_conteos(), _zonas(), _meta_denue(), _meta_marco())
        fila = oro.loc[oro["zona_codigo"] == "06001"].iloc[0]
        self.assertGreater(fila["area_km2"], 0)
        self.assertAlmostEqual(
            fila["farmacias_por_km2"], fila["farmacias_total"] / fila["area_km2"], places=9
        )

    def test_rechaza_geometria_degenerada(self) -> None:
        zonas = _zonas().copy()
        zonas.loc[0, "geometry"] = Polygon([(0, 0), (0, 0), (0, 0)])
        with self.assertRaises(ValueError):
            integrar_zonas(_conteos(), zonas, _meta_denue(), _meta_marco())

    def test_mapa_se_genera_sin_puntos_de_unidades(self) -> None:
        _, oro = integrar_zonas(_conteos(), _zonas(), _meta_denue(), _meta_marco())
        self.assertIn("geometry", oro.columns)
        self.assertTrue(oro.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "mapa.png"
            crear_mapa(oro, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)
        self.assertNotIn("unidad_id", oro.columns)


if __name__ == "__main__":
    unittest.main()
