"""Pruebas offline del agregado DENUE y del snapshot Bronce E2."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.e2.descargar_denue import (
    COLUMNAS_SNAPSHOT,
    ErrorDenue,
    agregar_farmacias,
    guardar_snapshot,
)


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


if __name__ == "__main__":
    unittest.main()
