"""Pruebas de la integración pública E1: dengue + clima para Colima."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from src.integrar_publicos import (
    COLUMNAS_CLIMA,
    COLUMNAS_DENGUE,
    ErrorEsquema,
    construir_oro,
    ejecutar,
    integrar,
    validar_clima,
    validar_dengue,
)


def _dengue(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "anio": 2026,
        "semana": 1,
        "entidad": "Colima",
        "probables_2025": 10,
        "probables_2026": 12,
        "dng_2025": 0,
        "dng_2026": 0,
        "dcsa_dg_2025": 0,
        "dcsa_dg_2026": 0,
        "confirmados_2025": 1,
        "confirmados_2026": 2,
        "defunciones_2025": 0,
        "defunciones_2026": 0,
        "url": "https://example.org/se01.pdf",
        "extraido_en": "2026-11-10T00:00:00+00:00",
    }
    base.update(cambios)
    return base


def _clima(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "anio": 2026,
        "semana": 1,
        "ciudad": "Colima",
        "lat": 19.2433,
        "lon": -103.725,
        "temp_media_c": 25.0,
        "precipitacion_mm": 0.0,
        "humedad_media_pct": 60.0,
        "dias_lluvia": 0,
        "dias_lluvia_intensa": 0,
        "extraido_en": "2026-11-10T00:00:00+00:00",
    }
    base.update(cambios)
    return base


def _tabla(filas: list[dict[str, object]], columnas: list[str]) -> pd.DataFrame:
    return pd.DataFrame(filas, columns=columnas)


class ValidacionPublicaTest(unittest.TestCase):
    def test_dengue_rechaza_negativos_con_motivo(self) -> None:
        entrada = _tabla([_dengue(), _dengue(semana=2, probables_2026=-1)], COLUMNAS_DENGUE)
        validas, cuarentena = validar_dengue(entrada)
        self.assertEqual(len(validas), 1)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("negativo", cuarentena.iloc[0]["motivo"].lower())

    def test_dengue_rechaza_columnas_faltantes(self) -> None:
        entrada = _tabla([_dengue()], [c for c in COLUMNAS_DENGUE if c != "url"])
        with self.assertRaises(ErrorEsquema):
            validar_dengue(entrada)

    def test_dengue_rechaza_semana_no_entera(self) -> None:
        entrada = _tabla([_dengue(semana=1.5)], COLUMNAS_DENGUE)
        validas, cuarentena = validar_dengue(entrada)
        self.assertEqual(len(validas), 0)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("entero", cuarentena.iloc[0]["motivo"].lower())

    def test_dengue_rechaza_extraido_en_invalido(self) -> None:
        entrada = _tabla([_dengue(extraido_en="no-es-fecha")], COLUMNAS_DENGUE)
        validas, cuarentena = validar_dengue(entrada)
        self.assertEqual(len(validas), 0)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("fecha", cuarentena.iloc[0]["motivo"].lower())

    def test_dengue_rechaza_fecha_no_iso_con_barras(self) -> None:
        entrada = _tabla([_dengue(extraido_en="2026/11/10")], COLUMNAS_DENGUE)
        validas, cuarentena = validar_dengue(entrada)
        self.assertEqual(len(validas), 0)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("fecha", cuarentena.iloc[0]["motivo"].lower())

    def test_clima_permite_faltantes_solo_en_variables_meteorologicas(self) -> None:
        entrada = _tabla(
            [
                _clima(temp_media_c="", precipitacion_mm="", humedad_media_pct=""),
                _clima(semana=2, dias_lluvia=""),
            ],
            COLUMNAS_CLIMA,
        )
        validas, cuarentena = validar_clima(entrada)
        self.assertEqual(len(validas), 1)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("dias_lluvia", cuarentena.iloc[0]["motivo"])


class IntegracionTest(unittest.TestCase):
    def _dengue_dos_semanas(self) -> pd.DataFrame:
        return _tabla([_dengue(), _dengue(semana=2)], COLUMNAS_DENGUE)

    def test_filtra_colima_y_ordena_semanas(self) -> None:
        dengue = _tabla(
            [
                _dengue(semana=10),
                _dengue(semana=2),
                _dengue(semana=1),
                _dengue(entidad="Jalisco", semana=1),
            ],
            COLUMNAS_DENGUE,
        )
        clima = _tabla(
            [
                _clima(semana=10),
                _clima(semana=2),
                _clima(semana=1),
                _clima(ciudad="Manzanillo", semana=1),
            ],
            COLUMNAS_CLIMA,
        )
        plata, reporte = integrar(dengue, clima)
        self.assertEqual(plata["semana"].tolist(), [1, 2, 10])
        self.assertEqual(set(plata["entidad"]), {"Colima"})
        self.assertEqual(set(plata["ciudad"]), {"Colima"})
        self.assertEqual(reporte["integracion"]["semanas_sin_clima"], 0)

    def test_resuelve_duplicados_con_extraido_en_mas_reciente(self) -> None:
        dengue = _tabla(
            [
                _dengue(probables_2026=10, extraido_en="2026-11-10T00:00:00+00:00"),
                _dengue(probables_2026=99, extraido_en="2026-11-11T00:00:00+00:00"),
            ],
            COLUMNAS_DENGUE,
        )
        clima = _tabla([_clima()], COLUMNAS_CLIMA)
        plata, reporte = integrar(dengue, clima)
        self.assertEqual(len(plata), 1)
        self.assertEqual(int(plata.iloc[0]["probables_2026"]), 99)
        self.assertEqual(reporte["integracion"]["duplicados_dengue_resueltos"], 1)

    def test_marca_faltantes_antes_de_imputar(self) -> None:
        dengue = self._dengue_dos_semanas()
        clima = _tabla([_clima()], COLUMNAS_CLIMA)
        plata, reporte = integrar(dengue, clima)
        faltante = plata.loc[plata["semana"] == 2].iloc[0]
        self.assertEqual(int(faltante["clima_disponible"]), 0)
        self.assertTrue(pd.isna(faltante["temp_media_c"]))
        self.assertTrue(pd.notna(faltante["temp_media_c_analisis"]))
        self.assertEqual(int(faltante["temp_media_c_imputado"]), 1)
        self.assertEqual(reporte["faltantes"]["temp_media_c"], 1)

    def test_clima_disponible_si_existe_registro_aunque_falte_temperatura(self) -> None:
        dengue = _tabla([_dengue()], COLUMNAS_DENGUE)
        clima = _tabla([_clima(temp_media_c=np.nan)], COLUMNAS_CLIMA)
        plata, reporte = integrar(dengue, clima)
        fila = plata.iloc[0]
        self.assertEqual(int(fila["clima_disponible"]), 1)
        self.assertEqual(int(fila["temp_media_c_imputado"]), 1)
        self.assertEqual(reporte["integracion"]["semanas_sin_clima"], 0)

    def test_oro_agrega_una_fila_por_semana(self) -> None:
        plata, _ = integrar(
            self._dengue_dos_semanas(), _tabla([_clima()], COLUMNAS_CLIMA)
        )
        oro = construir_oro(plata)
        self.assertEqual(len(oro), 2)
        self.assertEqual(oro["semana"].tolist(), [1, 2])
        self.assertIn("probables_2026", oro.columns)


class EjecucionTest(unittest.TestCase):
    def _escribir(self, raiz: Path, dengue: list[dict], clima: list[dict]) -> tuple[Path, Path]:
        d = raiz / "dengue.csv"
        c = raiz / "clima.csv"
        _tabla(dengue, COLUMNAS_DENGUE).to_csv(d, index=False)
        _tabla(clima, COLUMNAS_CLIMA).to_csv(c, index=False)
        return d, c

    def test_no_publica_invalidos_y_los_manda_a_cuarentena(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            d, c = self._escribir(
                raiz,
                [_dengue(), _dengue(semana=2, probables_2026=-5)],
                [_clima()],
            )
            rutas = {
                "plata": raiz / "plata.csv",
                "oro": raiz / "oro.csv",
                "cuarentena": raiz / "cuarentena.csv",
                "reporte": raiz / "reporte.json",
            }
            reporte = ejecutar(dengue=d, clima=c, **rutas)
            plata = pd.read_csv(rutas["plata"])
            cuarentena = pd.read_csv(rutas["cuarentena"], dtype=str)
        self.assertEqual(len(plata), 1)
        self.assertEqual(len(cuarentena), 1)
        self.assertIn("negativo", cuarentena.iloc[0]["motivo"].lower())
        self.assertEqual(reporte["filas_plata"], 1)

    def test_ejecutar_marca_clima_faltante_sin_rechazar_la_semana(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            d, c = self._escribir(
                raiz, [_dengue(), _dengue(semana=2)], [_clima()]
            )
            rutas = {
                "plata": raiz / "plata.csv",
                "oro": raiz / "oro.csv",
                "cuarentena": raiz / "cuarentena.csv",
                "reporte": raiz / "reporte.json",
            }
            reporte = ejecutar(dengue=d, clima=c, **rutas)
            plata = pd.read_csv(rutas["plata"])
            cuarentena = pd.read_csv(rutas["cuarentena"], dtype=str)
        semana_2 = plata.loc[plata["semana"] == 2].iloc[0]
        self.assertEqual(len(plata), 2)
        self.assertEqual(len(cuarentena), 0)
        self.assertEqual(int(semana_2["clima_disponible"]), 0)
        self.assertEqual(int(semana_2["temp_media_c_imputado"]), 1)
        self.assertTrue(pd.isna(semana_2["temp_media_c"]))
        self.assertTrue(pd.notna(semana_2["temp_media_c_analisis"]))
        self.assertEqual(reporte["faltantes"]["temp_media_c"], 1)

    def test_salida_determinista(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            d, c = self._escribir(raiz, [_dengue(), _dengue(semana=2)], [_clima()])
            datos = {}
            for nombre in ("uno", "dos"):
                sub = raiz / nombre
                sub.mkdir()
                rutas = {
                    "plata": sub / "plata.csv",
                    "oro": sub / "oro.csv",
                    "cuarentena": sub / "cuarentena.csv",
                    "reporte": sub / "reporte.json",
                }
                ejecutar(dengue=d, clima=c, **rutas)
                datos[nombre] = {
                    k: (sub / v).read_bytes()
                    for k, v in {
                        "plata": "plata.csv",
                        "oro": "oro.csv",
                        "reporte": "reporte.json",
                    }.items()
                }
        self.assertEqual(datos["uno"], datos["dos"])

    def test_rechaza_salida_dentro_de_datos_crudos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            d, c = self._escribir(raiz, [_dengue()], [_clima()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    dengue=d,
                    clima=c,
                    plata=Path("datos_crudos/plata.csv"),
                    oro=raiz / "oro.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )

    def test_falla_de_publicacion_restaura_salidas_previas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            d, c = self._escribir(raiz, [_dengue()], [_clima()])
            rutas = {
                "plata": raiz / "plata.csv",
                "oro": raiz / "oro.csv",
                "cuarentena": raiz / "cuarentena.csv",
                "reporte": raiz / "reporte.json",
            }
            for i, ruta in enumerate(rutas.values(), 1):
                ruta.write_text(f"viejo{i}", encoding="utf-8")

            real_replace = os.replace
            llamadas = {"n": 0}

            def replace_falla(src: object, dst: object) -> None:
                llamadas["n"] += 1
                if llamadas["n"] == 3:
                    raise OSError("fallo simulado")
                real_replace(src, dst)

            with mock.patch(
                "src.integrar_publicos.os.replace", side_effect=replace_falla
            ):
                with self.assertRaises(OSError):
                    ejecutar(dengue=d, clima=c, **rutas)

            for i, ruta in enumerate(rutas.values(), 1):
                self.assertEqual(
                    ruta.read_text(encoding="utf-8"),
                    f"viejo{i}",
                    msg=f"no se restauró {ruta}",
                )
            self.assertEqual(list(raiz.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
