"""Pruebas del generador de datos sintéticos de inventario por turno (E1)."""

from __future__ import annotations

import csv
import json
import statistics
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from src.generar_sintetico import (
    COLUMNAS,
    INSUMOS,
    _percentil,
    escribir,
    generar,
    generar_con_verdad,
    main,
)

INICIO = date(2026, 7, 1)
DIAS = 120
UNIDADES = ("U01", "U02")
CAMPOS_EXISTENCIA = ("existencia_inicial", "entradas", "consumo", "existencia_final")


class GenerarSinteticoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.filas, cls.meta = generar(
            seed=42, inicio=INICIO, dias=DIAS, unidades=UNIDADES
        )

    def test_volumen_esperado(self) -> None:
        esperado = DIAS * 3 * len(INSUMOS) * len(UNIDADES)
        self.assertEqual(len(self.filas), esperado)

    def test_llave_unica(self) -> None:
        claves = [
            (f["unidad_id"], f["fecha"], f["turno"], f["insumo_id"])
            for f in self.filas
        ]
        self.assertEqual(len(claves), len(set(claves)))

    def test_esquema_exacto_y_marca_sintetica(self) -> None:
        self.assertEqual(tuple(self.filas[0]), tuple(COLUMNAS))
        self.assertTrue(all(f["es_sintetico"] == 1 for f in self.filas))

    def test_fechas_en_rango(self) -> None:
        fechas = {date.fromisoformat(f["fecha"]) for f in self.filas}
        self.assertEqual(min(fechas), INICIO)
        self.assertEqual(max(fechas), INICIO + timedelta(days=DIAS - 1))
        self.assertEqual(len(fechas), DIAS)

    def test_consistencia_de_existencias_y_no_negativos(self) -> None:
        for f in self.filas:
            if any(f[k] in ("", None) for k in CAMPOS_EXISTENCIA):
                continue
            self.assertEqual(
                f["existencia_final"],
                f["existencia_inicial"] + f["entradas"] - f["consumo"],
                msg=f"fila inconsistente: {f}",
            )
            for campo in CAMPOS_EXISTENCIA:
                self.assertGreaterEqual(f[campo], 0, msg=f"{campo} negativo: {f}")

    def test_determinista_por_semilla(self) -> None:
        otras, _ = generar(seed=42, inicio=INICIO, dias=DIAS, unidades=UNIDADES)
        self.assertEqual(self.filas, otras)

    def test_reporte_sin_marca_de_tiempo(self) -> None:
        self.assertNotIn("generado_en", self.meta)

    def test_reporte_reproducible_byte_a_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "sintetico.csv"
            reporte = Path(tmp) / "_reporte_sintetico.json"
            escribir(self.filas, self.meta, salida, reporte)
            csv_1 = salida.read_bytes()
            json_1 = reporte.read_bytes()
            escribir(self.filas, self.meta, salida, reporte)
            self.assertEqual(csv_1, salida.read_bytes())
            self.assertEqual(json_1, reporte.read_bytes())

    def test_mecanismos_de_faltantes(self) -> None:
        faltantes = self.meta["faltantes"]
        self.assertGreater(faltantes["mcar"], 0)
        self.assertGreater(faltantes["mar"], 0)
        self.assertGreater(faltantes["mnar"], 0)

        vacios = [f for f in self.filas if f["consumo"] in ("", None)]
        self.assertGreaterEqual(len(vacios), faltantes["mcar"] + faltantes["mnar"])

        nocturno = [f for f in self.filas if f["turno"] == "N"]
        diurno = [f for f in self.filas if f["turno"] != "N"]
        tasa_n = sum(f["personal_disponible"] in ("", None) for f in nocturno) / len(nocturno)
        tasa_d = sum(f["personal_disponible"] in ("", None) for f in diurno) / len(diurno)
        self.assertGreater(tasa_n, tasa_d)

    def test_atipicos_inyectados(self) -> None:
        self.assertGreater(self.meta["atipicos"], 0)
        pacientes = [f["pacientes_atendidos"] for f in self.filas]
        self.assertGreater(max(pacientes), 3 * statistics.median(pacientes))

    def test_generar_con_verdad_conserva_los_valores_previos(self) -> None:
        filas, verdad, meta = generar_con_verdad(
            seed=42, inicio=INICIO, dias=10, unidades=("U01",)
        )
        self.assertEqual(len(filas), len(verdad))
        self.assertEqual(meta["faltantes"]["mcar"], 3)

        faltantes = [
            i for i, fila in enumerate(filas) if fila["consumo"] == ""
        ]
        self.assertGreater(len(faltantes), 0)
        for i in faltantes:
            self.assertIsInstance(verdad[i]["consumo"], int)

        atipicos = [
            i
            for i, (fila, original) in enumerate(zip(filas, verdad, strict=True))
            if fila["pacientes_atendidos"] != original["pacientes_atendidos"]
        ]
        self.assertGreater(len(atipicos), 0)
        for i in atipicos:
            self.assertEqual(
                filas[i]["pacientes_atendidos"],
                verdad[i]["pacientes_atendidos"] * 5,
            )

    def test_percentil_se_calcula_una_sola_vez(self) -> None:
        with mock.patch(
            "src.generar_sintetico._percentil", wraps=_percentil
        ) as percentil:
            generar(seed=42, inicio=INICIO, dias=10, unidades=("U01",))
        self.assertEqual(percentil.call_count, 1)

    def test_escribir_csv_y_reporte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "inventario_turno_sintetico.csv"
            reporte = Path(tmp) / "_reporte_sintetico.json"
            escribir(self.filas, self.meta, salida, reporte)

            with salida.open(newline="", encoding="utf-8") as fh:
                leidas = list(csv.DictReader(fh))
            self.assertEqual(len(leidas), len(self.filas))
            self.assertEqual(tuple(leidas[0]), tuple(COLUMNAS))

            datos = json.loads(reporte.read_text(encoding="utf-8"))
            self.assertEqual(datos["seed"], 42)
            self.assertTrue(datos["es_sintetico"])
            self.assertIn("sha256", datos)
            self.assertEqual(datos["filas"], len(self.filas))

    def test_salida_alterna_no_sobrescribe_reporte_versionado(self) -> None:
        raiz = Path(__file__).resolve().parents[1]
        meta_versionado = raiz / "datos_crudos" / "_reporte_sintetico.json"
        antes = meta_versionado.read_bytes() if meta_versionado.exists() else None
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "sintetico.csv"
            self.assertEqual(
                main(["--salida", str(salida), "--dias", "10"]),
                0,
            )
            self.assertTrue(salida.exists())
            self.assertTrue((Path(tmp) / "_reporte_sintetico.json").exists())
        if antes is not None:
            self.assertEqual(meta_versionado.read_bytes(), antes)
        else:
            self.assertFalse(meta_versionado.exists())


if __name__ == "__main__":
    unittest.main()
