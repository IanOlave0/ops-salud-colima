# tests/test_e2_geoespacial.py
import unittest
from pathlib import Path
import tempfile

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from src.e2.integrar_geoespacial import integrar_zonas, crear_mapa


class TestIntegracionGeoespacial(unittest.TestCase):
    def setUp(self):
        # 1. Conteos DENUE simulados
        self.conteos = pd.DataFrame(
            {
                "zona_codigo": ["06001", "06002", "06001"],
                "actividad_scian": ["464111", "464111", "464112"],
                "establecimientos": [5, 2, 3],
            }
        )
        # 2. Polígonos simulados (municipios de Colima)
        self.zonas = gpd.GeoDataFrame(
            {
                "zona_codigo": ["06001", "06002", "06003"],
                "geometry": [
                    Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
                    Polygon([(1, 0), (1, 1), (2, 1), (2, 0)]),
                    Polygon([(2, 0), (2, 1), (3, 1), (3, 0)]),
                ],
            },
            crs="EPSG:4326",
        )
        # 3. Metadatos
        self.meta_denue = {
            "edicion": "05/2026",
            "query_id": "abc123",
            "sha256": "deadbeef",
            "ingestado_en": "2026-11-23T00:00:00Z",
        }
        self.meta_marco = {"version": "2025", "sha256": "cafebabe"}

    def test_integrar_zonas_columnas_esperadas(self):
        plata, oro = integrar_zonas(
            self.conteos, self.zonas, self.meta_denue, self.meta_marco
        )
        # Plata debe tener una fila por zona
        self.assertEqual(len(plata), 2)  # 06001 y 06002
        # Oro debe tener una fila por polígono (incluye 06003 sin conteo)
        self.assertEqual(len(oro), 3)

        columnas_oro = {
            "zona_codigo", "farmacias_464111", "farmacias_464112",
            "farmacias_total", "area_km2", "farmacias_por_km2",
            "denue_edicion", "denue_query_id", "denue_sha256",
            "denue_ingestado_en", "marco_version", "marco_sha256",
            "transformacion_version",
        }
        self.assertTrue(columnas_oro.issubset(set(oro.columns)))

    def test_zona_sin_conteo_marcada_como_faltante(self):
        _, oro = integrar_zonas(
            self.conteos, self.zonas, self.meta_denue, self.meta_marco
        )
        fila_06003 = oro[oro["zona_codigo"] == "06003"].iloc[0]
        self.assertTrue(pd.isna(fila_06003["farmacias_total"]))

    def test_areas_positivas_y_densidad(self):
        _, oro = integrar_zonas(
            self.conteos, self.zonas, self.meta_denue, self.meta_marco
        )
        self.assertTrue((oro["area_km2"].dropna() > 0).all())
        filas_con_datos = oro.dropna(subset=["farmacias_total", "area_km2"])
        self.assertFalse(filas_con_datos["farmacias_por_km2"].isna().any())

    def test_crear_mapa_genera_archivo(self):
        _, oro = integrar_zonas(
            self.conteos, self.zonas, self.meta_denue, self.meta_marco
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "mapa_test.png"
            crear_mapa(oro, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()