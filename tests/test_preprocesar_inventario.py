"""Pruebas del pipeline E1 de limpieza y preprocesamiento del inventario.

El contrato cubre: procedencia verificable, rutas seguras y escritura atómica,
Bronce intacto, puerta de calidad estricta, cuarentena con motivo, duplicados
transversales, imputación con banderas, atípicos robustos, transformaciones,
reducción explícita, diagnóstico dinámico y reproducibilidad byte a byte.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from src.generar_sintetico import escribir, generar_con_verdad
from src.preprocesar_inventario import (
    CLAVES,
    COLUMNAS_ENTRADA,
    COLUMNAS_PLATA,
    COLUMNAS_REDUCIDAS,
    ErrorEsquema,
    _imputar,
    _publicar_temporales,
    ejecutar,
    validar_plata,
)

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "datos_crudos" / "inventario_turno_sintetico.csv"
META = ENTRADA.with_name("_reporte_sintetico.json")


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _fila(
    unidad: str = "U01",
    fecha: str = "2026-07-01",
    turno: str = "M",
    insumo: str = "INS01",
    **cambios: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "unidad_id": unidad,
        "fecha": fecha,
        "turno": turno,
        "insumo_id": insumo,
        "insumo_nombre": "Paracetamol 500 mg",
        "familia": "medicamento",
        "existencia_inicial": 100,
        "entradas": 0,
        "consumo": 10,
        "existencia_final": 90,
        "desabasto": 0,
        "pacientes_atendidos": 40,
        "personal_disponible": 7,
        "es_sintetico": 1,
    }
    base.update(cambios)
    return base


def _escribir_fuente(
    raiz: Path,
    filas: list[dict[str, object]],
    *,
    sintetico: bool = True,
    escribir_meta: bool = True,
    sha_declarado: str | None = None,
    faltantes: dict[str, int] | None = None,
) -> Path:
    """Escribe una fuente temporal y, si aplica, su reporte de procedencia."""
    raiz.mkdir(parents=True, exist_ok=True)
    entrada = raiz / "entrada.csv"
    pd.DataFrame(filas, columns=COLUMNAS_ENTRADA).to_csv(entrada, index=False)
    if escribir_meta:
        meta = {
            "es_sintetico": sintetico,
            "sha256": sha_declarado or _sha256(entrada),
            "faltantes": faltantes or {"mcar": 0, "mar": 0, "mnar": 0},
        }
        (raiz / "_reporte_sintetico.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
    return entrada


def _rutas(raiz: Path) -> dict[str, Path]:
    return {
        "plata": raiz / "plata.csv",
        "reducido": raiz / "reducido.csv",
        "cuarentena": raiz / "cuarentena.csv",
        "reporte": raiz / "reporte.json",
    }


class PipelineSinteticoTest(unittest.TestCase):
    """Ejecuta el pipeline una vez sobre la fuente sintética real."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        raiz = Path(cls._tmp.name)
        cls.sha_antes = _sha256(ENTRADA)
        cls.fuente = pd.read_csv(ENTRADA, dtype=str, keep_default_na=False)
        cls.meta = json.loads(META.read_text(encoding="utf-8"))
        cls.nulos_consumo = int((cls.fuente["consumo"] == "").sum())
        cls.nulos_personal = int((cls.fuente["personal_disponible"] == "").sum())
        cls.rutas = {
            "plata": raiz / "plata.csv",
            "reducido": raiz / "reducido.csv",
            "cuarentena": raiz / "cuarentena.csv",
            "reporte": raiz / "reporte.json",
        }
        cls.reporte = ejecutar(entrada=ENTRADA, **cls.rutas)
        cls.sha_despues = _sha256(ENTRADA)
        cls.plata = pd.read_csv(cls.rutas["plata"], dtype={"fecha": str})
        cls.reducido = pd.read_csv(cls.rutas["reducido"], dtype={"fecha": str})
        cls.cuarentena = pd.read_csv(cls.rutas["cuarentena"], dtype=str)

    def test_bronce_intacto_byte_a_byte(self) -> None:
        self.assertEqual(self.sha_antes, self.sha_despues)
        self.assertTrue(self.reporte["bronce_intacto"])
        self.assertEqual(self.reporte["sha256_bronce_antes"], self.sha_antes)
        self.assertEqual(self.reporte["sha256_bronce_despues"], self.sha_despues)
        self.assertEqual(self.reporte["procedencia"]["sha256_entrada"], self.sha_antes)

    def test_salidas_generadas(self) -> None:
        for ruta in self.rutas.values():
            self.assertTrue(ruta.exists(), msg=f"no se generó {ruta}")

    def test_plata_cumple_esquema_estricto_y_procedencia(self) -> None:
        self.assertEqual(validar_plata(self.plata), [])
        self.assertEqual(tuple(self.plata.columns), tuple(COLUMNAS_PLATA))
        self.assertEqual(len(self.plata), len(self.fuente))
        self.assertEqual(len(self.plata), self.reporte["filas_plata"])
        self.assertEqual(set(self.plata["fuente"]), {"sintetico"})
        self.assertEqual(set(self.plata["es_sintetico"]), {1})
        self.assertEqual(self.reporte["fuente"], "sintetico")
        self.assertTrue(self.reporte["es_sintetico"])

    def test_plata_sin_claves_duplicadas(self) -> None:
        claves = self.plata[CLAVES].astype(str).agg("|".join, axis=1)
        self.assertEqual(claves.nunique(), len(self.plata))

    def test_sin_faltantes_en_variables_imputadas(self) -> None:
        for columna in ("consumo", "personal_disponible"):
            self.assertFalse(
                self.plata[columna].isna().any(), msg=f"quedaron nulos en {columna}"
            )
        self.assertTrue((self.plata["consumo"] >= 0).all())
        self.assertTrue((self.plata["personal_disponible"] > 0).all())

    def test_imputacion_documentada_y_banderas(self) -> None:
        self.assertEqual(
            int(self.plata["imputado_consumo"].sum()), self.nulos_consumo
        )
        self.assertEqual(
            int(self.plata["imputado_personal"].sum()), self.nulos_personal
        )
        self.assertEqual(
            self.reporte["imputacion"]["consumo"]["n"], self.nulos_consumo
        )
        self.assertEqual(
            self.reporte["imputacion"]["personal_disponible"]["n"],
            self.nulos_personal,
        )
        self.assertEqual(
            self.reporte["imputacion"]["consumo"]["n_balance"], self.nulos_consumo
        )
        self.assertEqual(
            self.reporte["imputacion"]["personal_disponible"]["n_mediana_grupo"],
            self.nulos_personal,
        )
        self.assertEqual(
            self.reporte["imputacion"]["personal_disponible"]["n_global"], 0
        )

        # El balance de inventario permite recuperar el consumo exacto.
        imputado = self.plata.loc[self.plata["imputado_consumo"] == 1]
        balance = (
            imputado["existencia_inicial"]
            + imputado["entradas"]
            - imputado["existencia_final"]
        )
        self.assertTrue((imputado["consumo"] == balance).all())
        self.assertTrue(
            (self.plata["existencia_final"]
             == self.plata["existencia_inicial"]
             + self.plata["entradas"]
             - self.plata["consumo"]).all()
        )

        # La mediana agrupada por unidad y turno es el respaldo documentado.
        for _, grupo in self.plata.groupby(["unidad_id", "turno"]):
            observados = grupo.loc[
                grupo["imputado_personal"] == 0, "personal_disponible"
            ]
            imputados = grupo.loc[
                grupo["imputado_personal"] == 1, "personal_disponible"
            ]
            if len(observados) and len(imputados):
                esperado = int(np.floor(observados.median() + 0.5))
                self.assertTrue((imputados == esperado).all())

        for clave in (*CLAVES, "desabasto"):
            self.assertFalse(self.plata[clave].isna().any())

    def test_atipicos_marcados_y_tratados_sin_eliminar(self) -> None:
        detalle = self.reporte["atipicos"]["pacientes_atendidos"]
        self.assertGreater(detalle["n"], 0)
        self.assertEqual(int(self.plata["atipico_pacientes"].sum()), detalle["n"])
        self.assertIn("n_altos", detalle)
        self.assertIn("n_bajos", detalle)
        self.assertEqual(detalle["n_altos"] + detalle["n_bajos"], detalle["n"])
        self.assertGreater(detalle["n_altos"], 0)

        marcados = self.plata["atipico_pacientes"] == 1
        self.assertTrue((self.plata.loc[marcados, "pacientes_analisis"]
                         != self.plata.loc[marcados, "pacientes_atendidos"]).all())
        self.assertTrue((self.plata.loc[marcados, "pacientes_analisis"]
                         < self.plata.loc[marcados, "pacientes_atendidos"]).any())
        self.assertTrue((self.plata.loc[~marcados, "pacientes_analisis"]
                         == self.plata.loc[~marcados, "pacientes_atendidos"]).all())
        self.assertTrue((self.plata["pacientes_analisis"] >= 0).all())
        self.assertIn("pacientes_atendidos", self.plata.columns)
        self.assertEqual(len(self.plata), self.reporte["filas_entrada"])

    def test_transformaciones_minmax_zscore_y_discretizacion(self) -> None:
        for columna in ("consumo_minmax", "pacientes_minmax"):
            self.assertTrue(self.plata[columna].between(0, 1).all())
        for columna in ("consumo_zscore", "pacientes_zscore"):
            self.assertAlmostEqual(float(self.plata[columna].mean()), 0.0, places=6)
            self.assertAlmostEqual(
                float(self.plata[columna].std(ddof=0)), 1.0, places=6
            )

        for columna in ("consumo", "pacientes_atendidos"):
            self.assertIn(columna, self.plata.columns)

        self.assertTrue(
            self.plata["jornada"].isin({"diurno", "nocturno"}).all()
        )
        self.assertTrue(self.plata["nivel_stock"].isin({0, 1, 2, 3}).all())
        self.assertTrue((self.plata["dias_cobertura"] >= 0).all())
        self.assertTrue(
            (self.plata["nivel_stock"] == 0).equals(
                self.plata["existencia_final"] == 0
            )
        )

    def test_reduccion_es_seleccion_explicita(self) -> None:
        self.assertEqual(tuple(self.reducido.columns), tuple(COLUMNAS_REDUCIDAS))
        self.assertEqual(len(self.reducido), len(self.plata))
        self.assertEqual(
            self.reducido[CLAVES].astype(str).agg("|".join, axis=1).tolist(),
            self.plata[CLAVES].astype(str).agg("|".join, axis=1).tolist(),
        )
        self.assertEqual(set(self.reducido["fuente"]), {"sintetico"})
        self.assertNotIn("insumo_nombre", self.reducido.columns)
        self.assertEqual(self.reporte["reduccion"]["columnas"], list(COLUMNAS_REDUCIDAS))

    def test_reporte_de_diagnostico_y_estadisticas(self) -> None:
        self.assertEqual(self.reporte["filas_entrada"], len(self.fuente))
        self.assertEqual(self.reporte["filas_cuarentena"], 0)
        self.assertEqual(
            self.reporte["nulos"]["por_columna_entrada"]["consumo"],
            self.nulos_consumo,
        )
        self.assertEqual(
            self.reporte["nulos"]["por_columna_entrada"]["personal_disponible"],
            self.nulos_personal,
        )
        self.assertIn("por_grupo", self.reporte["nulos"])
        self.assertIn("personal_disponible", self.reporte["nulos"]["por_grupo"])

        conocidos = self.reporte["mecanismos"]["conocidos_sintetico"]
        self.assertEqual(conocidos["mcar"]["n"], self.meta["faltantes"]["mcar"])
        self.assertEqual(conocidos["mar"]["n"], self.meta["faltantes"]["mar"])
        self.assertEqual(conocidos["mnar"]["n"], self.meta["faltantes"]["mnar"])

        observado = self.reporte["mecanismos"]["evidencia_observada"]
        for columna in ("personal_disponible", "consumo"):
            self.assertIn(columna, observado)
            self.assertIn("por_turno", observado[columna])
            self.assertIn("por_unidad", observado[columna])
            self.assertIn("lectura", observado[columna])
            self.assertIn("%", observado[columna]["lectura"])
        self.assertIn("por_insumo", observado["consumo"])
        self.assertIn("por_desabasto", observado["consumo"])
        self.assertIn("no prueba causalidad", observado["advertencia"].lower())

        pruebas = observado["pruebas_estadisticas"]
        for nombre in (
            "consumo_vs_turno",
            "consumo_vs_desabasto",
            "personal_vs_turno_nocturno",
        ):
            self.assertIn(nombre, pruebas)
            self.assertIn("estadistico", pruebas[nombre])
            self.assertIn("gl", pruebas[nombre])
            self.assertIn("p_valor", pruebas[nombre])
            self.assertIn("advertencia", pruebas[nombre])

        self.assertEqual(self.reporte["cuarentena"]["n"], 0)
        self.assertEqual(
            self.reporte["transformaciones"]["discretizacion"]["nivel_stock"]["umbrales"],
            [1.0, 3.0],
        )

    def test_reproducibilidad_byte_a_byte(self) -> None:
        with tempfile.TemporaryDirectory() as otro:
            rutas = _rutas(Path(otro))
            ejecutar(entrada=ENTRADA, **rutas)
            for nombre, ruta in self.rutas.items():
                self.assertEqual(
                    ruta.read_bytes(),
                    rutas[nombre].read_bytes(),
                    msg=f"{nombre} no es reproducible byte a byte",
                )

    def test_rutas_por_defecto_derivadas_de_la_fuente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz, [_fila(), _fila(insumo="INS02")]
            )
            with contextlib.chdir(raiz):
                reporte = ejecutar(entrada=entrada)
            self.assertEqual(reporte["fuente"], "sintetico")
            for relativa in (
                "datos_plata/sintetico/inventario_turno_plata.csv",
                "datos_plata/sintetico/inventario_turno_reducido.csv",
                "cuarentena/sintetico/inventario_turno_invalido.csv",
                "cuarentena/sintetico/_reporte.json",
            ):
                self.assertTrue((raiz / relativa).exists(), msg=relativa)


class ProcedenciaTest(unittest.TestCase):
    """La fuente debe verificarse; no se hereda una marca sintética falsa."""

    def test_auto_sintetico_verificado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila(), _fila(insumo="INS02")])
            rutas = _rutas(raiz)
            sha_esperado = _sha256(entrada)
            reporte = ejecutar(entrada=entrada, **rutas)
            plata = pd.read_csv(rutas["plata"], dtype={"fecha": str})
        procedencia = reporte["procedencia"]
        self.assertEqual(reporte["fuente"], "sintetico")
        self.assertTrue(reporte["es_sintetico"])
        self.assertEqual(reporte["sha256_entrada"], sha_esperado)
        self.assertTrue(procedencia["metadatos_sinteticos"]["usado"])
        self.assertTrue(procedencia["metadatos_sinteticos"]["coincide"])
        self.assertEqual(set(plata["fuente"]), {"sintetico"})

    def test_auto_sintetico_sin_metadatos_falla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz, [_fila()], escribir_meta=False
            )
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, **_rutas(raiz))

    def test_auto_sintetico_con_hash_incorrecto_falla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz, [_fila()], sha_declarado="0" * 64
            )
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, **_rutas(raiz))

    def test_marca_sintetica_mezclada_falla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz,
                [_fila(insumo="INS01"), _fila(insumo="INS02", es_sintetico=0)],
            )
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, **_rutas(raiz))

    def test_marca_sintetica_fuera_de_rango_falla(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila(es_sintetico=2)])
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, **_rutas(raiz))

    def test_sintetico_explicito_exige_metadatos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()], escribir_meta=False)
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, fuente="sintetico", **_rutas(raiz))

    def test_sintetico_explicito_rechaza_fuente_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz,
                [_fila(es_sintetico=0)],
                sintetico=False,
                escribir_meta=False,
            )
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, fuente="sintetico", **_rutas(raiz))

    def test_real_explicito_con_metadatos_no_los_usa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            filas = [
                _fila(es_sintetico=0, insumo="INS01"),
                _fila(es_sintetico=0, insumo="INS02"),
            ]
            entrada = _escribir_fuente(
                raiz, filas, sintetico=False, escribir_meta=True
            )
            rutas = _rutas(raiz)
            reporte = ejecutar(entrada=entrada, fuente="real", **rutas)
            plata = pd.read_csv(rutas["plata"], dtype={"fecha": str})
        self.assertEqual(reporte["fuente"], "real")
        self.assertFalse(reporte["es_sintetico"])
        self.assertIn("real", reporte["procedencia"]["advertencia"].lower())
        self.assertFalse(
            reporte["mecanismos"]["conocidos_sintetico"]["disponible"]
        )
        self.assertNotIn("mcar", reporte["mecanismos"]["conocidos_sintetico"])
        self.assertNotIn("mar", reporte["mecanismos"]["conocidos_sintetico"])
        self.assertNotIn("mnar", reporte["mecanismos"]["conocidos_sintetico"])
        self.assertFalse(
            reporte["procedencia"]["metadatos_sinteticos"]["usado"]
        )
        self.assertTrue(
            reporte["procedencia"]["metadatos_sinteticos"]["existe"]
        )
        self.assertEqual(set(plata["fuente"]), {"real"})
        self.assertEqual(set(plata["es_sintetico"]), {0})
        for columna in ("consumo", "personal_disponible"):
            lectura = reporte["mecanismos"]["evidencia_observada"][columna][
                "lectura"
            ].lower()
            self.assertNotIn("generador", lectura)

    def test_real_explicito_rechaza_marca_sintetica(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(entrada=entrada, fuente="real", **_rutas(raiz))

    def test_auto_real_sin_metadatos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz,
                [_fila(es_sintetico=0)],
                sintetico=False,
                escribir_meta=False,
            )
            reporte = ejecutar(entrada=entrada, **_rutas(raiz))
        self.assertEqual(reporte["fuente"], "real")
        self.assertFalse(reporte["es_sintetico"])
        self.assertFalse(
            reporte["mecanismos"]["conocidos_sintetico"]["disponible"]
        )


class RutasSegurasTest(unittest.TestCase):
    """No se puede escribir sobre Bronce ni publicar salidas parciales."""

    def test_rechaza_salida_igual_a_entrada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            sha_antes = _sha256(entrada)
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=entrada,
                    reducido=raiz / "reducido.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )
            self.assertEqual(_sha256(entrada), sha_antes)

    def test_rechaza_cualquier_salida_en_datos_crudos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=RAIZ / "datos_crudos" / "plata.csv",
                    reducido=raiz / "reducido.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )

    def test_rechaza_salida_explicita_en_directorio_versionado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=RAIZ / "reportes" / "plata.csv",
                    reducido=raiz / "reducido.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )
            self.assertFalse((RAIZ / "reportes" / "plata.csv").exists())

    def test_rechaza_sobrescribir_metadatos_de_procedencia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            meta = entrada.with_name("_reporte_sintetico.json")
            antes = meta.read_bytes()
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=raiz / "plata.csv",
                    reducido=raiz / "reducido.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=meta,
                )
            self.assertEqual(meta.read_bytes(), antes)

    def test_rechaza_mezclar_fuente_en_directorio_equivocado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=RAIZ / "datos_plata" / "real" / "plata.csv",
                    reducido=raiz / "reducido.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )

    def test_rechaza_dos_salidas_con_la_misma_ruta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila()])
            with self.assertRaises(ErrorEsquema):
                ejecutar(
                    entrada=entrada,
                    plata=raiz / "salida.csv",
                    reducido=raiz / "salida.csv",
                    cuarentena=raiz / "cuarentena.csv",
                    reporte=raiz / "reporte.json",
                )

    def test_falla_de_sha_no_deja_salidas_ni_temporales(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, [_fila(), _fila(insumo="INS02")])
            rutas = _rutas(raiz)
            sha_real = _sha256(entrada)
            llamadas = {"n": 0}

            def sha_falso(_ruta: Path) -> str:
                llamadas["n"] += 1
                if llamadas["n"] == 3:
                    return "0" * 64
                return sha_real

            with mock.patch(
                "src.preprocesar_inventario._sha256", side_effect=sha_falso
            ):
                with self.assertRaises(ErrorEsquema):
                    ejecutar(entrada=entrada, **rutas)

            for ruta in rutas.values():
                self.assertFalse(ruta.exists(), msg=f"quedó {ruta}")
            self.assertEqual(list(raiz.rglob("*.tmp")), [])

    def test_publicacion_falla_a_mitad_y_restaura_destinos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = raiz / "entrada.csv"
            entrada.write_text("origen\n", encoding="utf-8")
            destinos = [raiz / "plata.csv", raiz / "reporte.json"]
            for i, destino in enumerate(destinos, 1):
                destino.write_text(f"viejo{i}", encoding="utf-8")
            temporales = [raiz / ".t1.tmp", raiz / ".t2.tmp"]
            for i, temporal in enumerate(temporales, 1):
                temporal.write_text(f"nuevo{i}", encoding="utf-8")

            real_replace = os.replace
            llamadas = {"n": 0}

            def replace_falla(src: object, dst: object) -> None:
                llamadas["n"] += 1
                if llamadas["n"] == 2:
                    raise OSError("fallo simulado")
                real_replace(src, dst)

            with mock.patch(
                "src.preprocesar_inventario.os.replace", side_effect=replace_falla
            ):
                with self.assertRaises(OSError):
                    _publicar_temporales(
                        list(zip(temporales, destinos)),
                        entrada,
                        _sha256(entrada),
                    )

            self.assertEqual(destinos[0].read_text(encoding="utf-8"), "viejo1")
            self.assertEqual(destinos[1].read_text(encoding="utf-8"), "viejo2")
            self.assertEqual(list(raiz.glob("*.tmp")), [])

    def test_publicacion_falla_y_elimina_destino_nuevo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = raiz / "entrada.csv"
            entrada.write_text("origen\n", encoding="utf-8")
            destino_nuevo = raiz / "plata.csv"
            destino_existente = raiz / "reporte.json"
            destino_existente.write_text("viejo", encoding="utf-8")
            temporales = [raiz / ".t1.tmp", raiz / ".t2.tmp"]
            temporal_nuevo, temporal_existente = temporales
            temporal_nuevo.write_text("nuevo1", encoding="utf-8")
            temporal_existente.write_text("nuevo2", encoding="utf-8")

            real_replace = os.replace
            llamadas = {"n": 0}

            def replace_falla(src: object, dst: object) -> None:
                llamadas["n"] += 1
                if llamadas["n"] == 2:
                    raise OSError("fallo simulado")
                real_replace(src, dst)

            with mock.patch(
                "src.preprocesar_inventario.os.replace", side_effect=replace_falla
            ):
                with self.assertRaises(OSError):
                    _publicar_temporales(
                        [
                            (temporal_nuevo, destino_nuevo),
                            (temporal_existente, destino_existente),
                        ],
                        entrada,
                        _sha256(entrada),
                    )

            self.assertFalse(destino_nuevo.exists())
            self.assertEqual(
                destino_existente.read_text(encoding="utf-8"), "viejo"
            )
            self.assertEqual(list(raiz.glob("*.tmp")), [])


class DiagnosticoDinamicoTest(unittest.TestCase):
    """Las lecturas y pruebas deben salir de las cifras, no de texto fijo."""

    def _filas(self, **cambios: object) -> list[dict[str, object]]:
        return [
            _fila(insumo="INS01", consumo=10, desabasto=1, personal_disponible=7, **cambios),
            _fila(
                insumo="INS02", consumo="", existencia_final=90,
                personal_disponible=7, **cambios,
            ),
            _fila(
                fecha="2026-07-02", turno="V", insumo="INS01", consumo=10,
                personal_disponible=6, **cambios,
            ),
            _fila(
                fecha="2026-07-02", turno="V", insumo="INS02", consumo=10,
                personal_disponible=6, **cambios,
            ),
            _fila(
                fecha="2026-07-03", turno="N", insumo="INS01", consumo="",
                existencia_final=90, personal_disponible="", **cambios,
            ),
            _fila(
                fecha="2026-07-03", turno="N", insumo="INS02", consumo="",
                existencia_final=90, personal_disponible=4, **cambios,
            ),
        ]

    def test_lecturas_y_chi_cuadrado_se_calculan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, self._filas())
            reporte = ejecutar(entrada=entrada, **_rutas(raiz))
        observado = reporte["mecanismos"]["evidencia_observada"]
        self.assertIn("100.0%", observado["consumo"]["lectura"])
        self.assertIn("50.0%", observado["personal_disponible"]["lectura"])
        pruebas = observado["pruebas_estadisticas"]
        self.assertEqual(pruebas["consumo_vs_turno"]["gl"], 2)
        self.assertEqual(pruebas["consumo_vs_desabasto"]["gl"], 1)
        self.assertEqual(pruebas["personal_vs_turno_nocturno"]["gl"], 1)
        for prueba in pruebas.values():
            self.assertGreaterEqual(prueba["p_valor"], 0.0)
            self.assertLessEqual(prueba["p_valor"], 1.0)
            self.assertIn("no prueba causalidad", prueba["advertencia"].lower())

    def test_fuente_real_no_menciona_al_generador(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            filas = self._filas(es_sintetico=0)
            entrada = _escribir_fuente(
                raiz, filas, sintetico=False, escribir_meta=False
            )
            reporte = ejecutar(entrada=entrada, fuente="real", **_rutas(raiz))
        observado = reporte["mecanismos"]["evidencia_observada"]
        for columna in ("consumo", "personal_disponible"):
            self.assertNotIn("generador", observado[columna]["lectura"].lower())
        self.assertNotIn("mcar", reporte["mecanismos"]["conocidos_sintetico"])


class DuplicadosTest(unittest.TestCase):
    """Un duplicado contamina a todas las filas implicadas, aunque una sea válida."""

    def test_valida_y_gemela_invalida_van_a_cuarentena(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz,
                [
                    _fila(insumo="INS01"),
                    _fila(
                        insumo="INS01",
                        consumo=-1,
                        existencia_final=101,
                    ),
                    _fila(insumo="INS02"),
                ],
            )
            rutas = _rutas(raiz)
            reporte = ejecutar(entrada=entrada, **rutas)
            plata = pd.read_csv(rutas["plata"], dtype=str)
            cuarentena = pd.read_csv(rutas["cuarentena"], dtype=str)
        self.assertEqual(len(plata), 1)
        self.assertEqual(set(plata["insumo_id"]), {"INS02"})
        self.assertEqual(len(cuarentena), 2)
        self.assertEqual(reporte["filas_cuarentena"], 2)
        duplicadas = cuarentena[
            cuarentena["motivo"].str.contains("clave duplicada", case=False)
        ]
        self.assertEqual(len(duplicadas), 2)
        self.assertIn("negativo", " ".join(cuarentena["motivo"]).lower())


class ConteosTest(unittest.TestCase):
    """Conteos de imputación y atípicos deben ser exactos, no aproximados."""

    def test_n_global_cuenta_solo_rellenos_globales(self) -> None:
        filas = [
            _fila(insumo="INS01", personal_disponible=7),
            _fila(insumo="INS02", personal_disponible=""),
            _fila(
                turno="N", insumo="INS02", personal_disponible=4,
                fecha="2026-07-02",
            ),
            _fila(
                unidad="U02", turno="N", insumo="INS01",
                personal_disponible="", fecha="2026-07-02",
            ),
            _fila(
                turno="V", insumo="INS01", personal_disponible="",
                fecha="2026-07-03",
            ),
            _fila(
                unidad="U02", turno="V", insumo="INS02",
                personal_disponible="", fecha="2026-07-03",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(raiz, filas)
            rutas = _rutas(raiz)
            reporte = ejecutar(entrada=entrada, **rutas)
            plata = pd.read_csv(rutas["plata"])
        detalle = reporte["imputacion"]["personal_disponible"]
        self.assertEqual(detalle["n_mediana_grupo"], 1)
        self.assertEqual(detalle["n_mediana_turno"], 1)
        self.assertEqual(detalle["n_global"], 2)
        self.assertEqual(int(plata["imputado_personal"].sum()), 4)

    def test_n_altos_y_n_bajos_suman_el_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            reporte = ejecutar(entrada=ENTRADA, **_rutas(raiz))
        detalle = reporte["atipicos"]
        for nombre in ("pacientes_atendidos", "consumo"):
            self.assertEqual(
                detalle[nombre]["n_altos"] + detalle[nombre]["n_bajos"],
                detalle[nombre]["n"],
            )
            self.assertGreaterEqual(detalle[nombre]["n_altos"], 0)
            self.assertGreaterEqual(detalle[nombre]["n_bajos"], 0)

    def test_consumo_imputado_por_balance_igual_a_verdad_del_generador(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = raiz / "sintetico.csv"
            meta_path = raiz / "_reporte_sintetico.json"
            filas, verdad, meta = generar_con_verdad(
                seed=7, dias=10, unidades=("U01",)
            )
            escribir(filas, meta, entrada, meta_path)
            rutas = _rutas(raiz)
            ejecutar(entrada=entrada, **rutas)
            plata = pd.read_csv(rutas["plata"], dtype={"fecha": str})

        verdad_por_clave = {
            (f["unidad_id"], f["fecha"], f["turno"], f["insumo_id"]): f["consumo"]
            for f in verdad
        }
        imputados = plata.loc[plata["imputado_consumo"] == 1]
        self.assertGreater(len(imputados), 0)
        for _, fila in imputados.iterrows():
            clave = (
                fila["unidad_id"],
                fila["fecha"],
                fila["turno"],
                fila["insumo_id"],
            )
            self.assertEqual(int(fila["consumo"]), verdad_por_clave[clave])

    def test_respaldo_por_mediana_cuando_el_balance_no_es_calculable(self) -> None:
        base = {
            "unidad_id": "U01",
            "fecha": "2026-07-01",
            "turno": "M",
            "insumo_id": "INS02",
            "insumo_nombre": "Jeringa 5 ml",
            "familia": "material_curacion",
            "existencia_inicial": 100,
            "entradas": 0,
            "consumo": 20,
            "existencia_final": 80,
            "desabasto": 0,
            "pacientes_atendidos": 40,
            "personal_disponible": 7,
            "es_sintetico": 1,
        }
        df = pd.DataFrame(
            [
                base,
                {**base, "consumo": np.nan, "existencia_final": np.nan},
            ],
            columns=COLUMNAS_ENTRADA,
        )
        imputado, detalle = _imputar(df)
        self.assertEqual(detalle["consumo"]["n_balance"], 0)
        self.assertEqual(detalle["consumo"]["n_mediana_grupo"], 1)
        self.assertEqual(int(imputado.loc[1, "consumo"]), 20)
        self.assertEqual(int(imputado.loc[1, "imputado_consumo"]), 1)


class ValidacionEstrictaTest(unittest.TestCase):
    """El validador de Plata debe rechazar violaciones del contrato."""

    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            entrada = _escribir_fuente(
                raiz, [_fila(), _fila(insumo="INS02")]
            )
            rutas = _rutas(raiz)
            ejecutar(entrada=entrada, **rutas)
            cls.valida = pd.read_csv(rutas["plata"], dtype={"fecha": str})

    def _errores(self, df: pd.DataFrame) -> str:
        return " | ".join(validar_plata(df)).lower()

    def test_plata_valida_no_tiene_errores(self) -> None:
        self.assertEqual(validar_plata(self.valida), [])

    def test_rechaza_nulo_en_imputada(self) -> None:
        df = self.valida.copy()
        df.loc[0, "consumo"] = np.nan
        self.assertIn("consumo", self._errores(df))

    def test_rechaza_clave_duplicada(self) -> None:
        df = pd.concat([self.valida, self.valida.iloc[[0]]], ignore_index=True)
        self.assertIn("duplicada", self._errores(df))

    def test_rechaza_rango_y_categoria(self) -> None:
        df = self.valida.copy()
        df.loc[0, "consumo_minmax"] = 1.5
        self.assertIn("minmax", self._errores(df))
        df = self.valida.copy()
        df.loc[0, "turno"] = "X"
        self.assertIn("turno", self._errores(df))
        df = self.valida.copy()
        df.loc[0, "es_sintetico"] = 2
        self.assertIn("es_sintetico", self._errores(df))
        df = self.valida.copy()
        df.loc[0, "existencia_final"] = df.loc[0, "existencia_final"] + 1
        self.assertIn("consistencia", self._errores(df))

    def test_rechaza_fuente_invalida_e_incoherente(self) -> None:
        df = self.valida.copy()
        df["fuente"] = "otra"
        self.assertIn("fuente", self._errores(df))

        df = self.valida.copy()
        df["fuente"] = "real"
        self.assertIn("fuente", self._errores(df))

        df = self.valida.copy()
        df.loc[1, "es_sintetico"] = 0
        self.assertIn("uniforme", self._errores(df))


if __name__ == "__main__":
    unittest.main()
