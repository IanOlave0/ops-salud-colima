"""Pruebas offline del agregado DENUE y del snapshot Bronce E2."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import pandas as pd

from src.e2.descargar_denue import (
    COLUMNAS_SNAPSHOT,
    ErrorDenue,
    agregar_farmacias,
    extraer_csv,
    guardar_snapshot,
    main as main_denue,
)
from src.e2.descargar_marco import (
    _version_metadatos,
    descargar_marco,
    filtrar_marco,
)
from src.e2.ejecutar_e2 import _verificar_hash


def _fila(
    cve_mun: str = "001",
    codigo_act: str = "464111",
    per_ocu: str = "0 a 5 personas",
    **cambios: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "cve_ent": "06",
        "cve_mun": cve_mun,
        "municipio": "Armería",
        "codigo_act": codigo_act,
        "per_ocu": per_ocu,
    }
    base.update(cambios)
    return base


class AgregadoDenueTest(unittest.TestCase):
    def test_conserva_zona_como_texto_y_genera_cero_completo(self) -> None:
        entrada = pd.DataFrame([_fila(), _fila(per_ocu="6 a 10 personas")])
        salida = agregar_farmacias(entrada, edicion="05/2026")
        self.assertEqual(set(salida["zona_codigo"]), {"06001"})
        self.assertEqual(int(salida["establecimientos"].sum()), 2)
        self.assertEqual(set(salida["estado_query"]), {"completo"})

    def test_agrega_cero_en_categoria_ausente_solo_si_fuente_completa(self) -> None:
        entrada = pd.DataFrame([_fila()])
        salida = agregar_farmacias(entrada, edicion="05/2026")
        fila = salida.loc[salida["actividad_scian"] == "464112"].iloc[0]
        self.assertEqual(int(fila["establecimientos"]), 0)
        self.assertEqual(fila["estado_query"], "completo")

    def test_rechaza_columnas_faltantes(self) -> None:
        with self.assertRaises(ErrorDenue):
            agregar_farmacias(pd.DataFrame([{"cve_ent": "06"}]))

    def test_ignora_actividades_fuera_del_catalogo(self) -> None:
        salida = agregar_farmacias(
            pd.DataFrame([_fila(), _fila(codigo_act="621111")])
        )
        self.assertEqual(set(salida["actividad_scian"]), {"464111", "464112"})
        self.assertEqual(int(salida.loc[salida["actividad_scian"] == "464111", "establecimientos"].sum()), 1)

    def test_snapshot_guarda_csv_metadata_hash_y_sin_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            salida = agregar_farmacias(pd.DataFrame([_fila()]), edicion="05/2026")
            destinos = guardar_snapshot(
                salida,
                {
                    "edicion": "05/2026",
                    "query_id": "a" * 64,
                    "ingestado_en": "2026-11-23T00:00:00+00:00",
                },
                Path(tmp),
            )
            csv = Path(destinos["csv"])
            meta = json.loads(Path(destinos["metadata"]).read_text(encoding="utf-8"))
            columnas = tuple(pd.read_csv(csv, dtype=str).columns)
            hash_csv = hashlib.sha256(csv.read_bytes()).hexdigest()
        self.assertEqual(columnas, tuple(COLUMNAS_SNAPSHOT))
        self.assertEqual(meta["edicion"], "05/2026")
        self.assertEqual(meta["sha256"], hash_csv)
        self.assertNotIn("token", json.dumps(meta).lower())

    def test_extrae_solo_csv_del_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            zip_path = raiz / "denue.zip"
            with zipfile.ZipFile(zip_path, "w") as archivo:
                archivo.writestr(
                    "conjunto_de_datos/denue_inegi_06_.csv",
                    "cve_ent,cve_mun,codigo_act,per_ocu\n06,001,464111,0 a 5 personas\n",
                )
            ruta = extraer_csv(zip_path, raiz / "extraido")
            self.assertTrue(ruta.exists())
            self.assertEqual(ruta.name, "denue_inegi_06_.csv")

    def test_filtra_marco_a_claves_publicas(self) -> None:
        payload = {
            "metadatos": {"Fuente_informacion_vectorial": "INEGI"},
            "features": [
                {
                    "type": "Feature",
                    "properties": {"cvegeo": "06001", "nomgeo": "Armería", "pob_total": "27626"},
                    "geometry": {"type": "Point", "coordinates": [-103.0, 19.0]},
                }
            ],
        }
        salida = filtrar_marco(payload)
        props = salida["features"][0]["properties"]
        self.assertEqual(props["zona_codigo"], "06001")
        self.assertEqual(props["municipio"], "Armería")
        self.assertNotIn("nom_estab", props)

    def test_verificar_hash_rechaza_snapshot_alterado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "snapshot.csv"
            ruta.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                _verificar_hash(ruta, "0" * 64, "snapshot")
            _verificar_hash(ruta, hashlib.sha256(ruta.read_bytes()).hexdigest(), "snapshot")

    def test_main_rechaza_csv_sin_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ErrorDenue):
                main_denue(
                    [
                        "--csv", str(Path(tmp) / "denue.csv"),
                        "--output-dir", str(Path(tmp) / "out"),
                    ]
                )

    def test_version_metadatos(self) -> None:
        self.assertEqual(
            _version_metadatos({"metadatos": {"Fuente_informacion_vectorial": "INEGI, Marco Geoestadístico, diciembre de 2025"}}),
            "2025-12",
        )
        self.assertIsNone(
            _version_metadatos({"metadatos": {"Fuente_informacion_vectorial": "sin fecha"}})
        )

    def test_descargar_marco_falla_sin_version(self) -> None:
        respuesta = mock.Mock()
        respuesta.raise_for_status.return_value = None
        respuesta.json.return_value = {
            "metadatos": {"Fuente_informacion_vectorial": "sin fecha"},
            "features": [
                {
                    "type": "Feature",
                    "properties": {"cvegeo": "06001", "nomgeo": "Armería"},
                    "geometry": {"type": "Point", "coordinates": [-103.0, 19.0]},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("src.e2.descargar_marco.requests.get", return_value=respuesta):
                with self.assertRaises(ValueError):
                    descargar_marco(Path(tmp) / "marco.geojson")


if __name__ == "__main__":
    unittest.main()
