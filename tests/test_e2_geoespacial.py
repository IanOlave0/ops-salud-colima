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
        # 1. Conteos DENUE simulados (Incluye estrato)
        self.conteos = pd.DataFrame(
            {
                "zona_codigo": ["06001", "06002", "06001"],
                "actividad_scian": ["464111", "464111", "464112"],
                "estrato": [0, 0, 0],
                "establecimientos": [5, 2, 3],
            }
        )
        # 2. Polígonos simulados
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
        # 3. Metadatos completos
        self.meta_denue = {
            "edicion": "05/2026",
            "query_id": "abc123",
            "sha256": "deadbeef",
            "ingestado_en": "2026-11-23T00:00:00Z",
        }
        self.meta_marco = {"version": "2025", "sha256": "cafebabe"}

    def test_integrar_zonas_columnas_esperadas(self):
        plata, oro = integrar_zonas(self.conteos, self.zonas, self.meta_denue, self.meta_marco)
        self.assertEqual(len(oro), 3)
        
        # La zona 06003 no tiene datos. Debe quedar como NA, no como 0.
        fila_sin_datos = oro[oro["zona_codigo"] == "06003"].iloc[0]
        self.assertTrue(pd.isna(fila_sin_datos["farmacias_total"]))

    def test_falla_si_hay_duplicados_en_conteos(self):
        conteos_dup = pd.concat([self.conteos, self.conteos.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Duplicados detectados en conteos"):
            integrar_zonas(conteos_dup, self.zonas, self.meta_denue, self.meta_marco)

    def test_falla_si_hay_geometrias_duplicadas(self):
        zonas_dup = pd.concat([self.zonas, self.zonas.iloc[[0]]], ignore_index=True)
        zonas_dup = gpd.GeoDataFrame(zonas_dup, crs="EPSG:4326")
        with self.assertRaisesRegex(ValueError, "Duplicados detectados en el GeoDataFrame"):
            integrar_zonas(self.conteos, zonas_dup, self.meta_denue, self.meta_marco)

    def test_falla_si_faltan_metadatos_de_linaje(self):
        meta_incompleta = self.meta_denue.copy()
        del meta_incompleta["sha256"]
        with self.assertRaisesRegex(ValueError, "Metadatos de DENUE incompletos"):
            integrar_zonas(self.conteos, self.zonas, meta_incompleta, self.meta_marco)

    def test_crear_mapa_genera_archivo(self):
        _, oro = integrar_zonas(self.conteos, self.zonas, self.meta_denue, self.meta_marco)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "mapa_test.png"
            crear_mapa(oro, output)
            self.assertTrue(output.exists())