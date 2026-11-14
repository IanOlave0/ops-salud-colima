#!/usr/bin/env python3
"""Pipeline E1: de Bronce a Plata validada, diagnosticada y reducida.

El pipeline **solo lee** la capa Bronce. Toda salida se escribe en rutas nuevas,
derivadas de la fuente verificada cuando no se especifican:

- ``datos_plata/{fuente}/inventario_turno_plata.csv``
- ``datos_plata/{fuente}/inventario_turno_reducido.csv``
- ``cuarentena/{fuente}/inventario_turno_invalido.csv``
- ``cuarentena/{fuente}/_reporte.json``

La procedencia se verifica antes de procesar: la marca ``es_sintetico`` debe ser
uniforme y, si la fuente es sintética, su reporte debe existir y declarar el
SHA-256 exacto de la entrada. La puerta de calidad es un validador explícito de
esquema, tipos, rangos y claves. Se justifica la alternativa a Pandera en
``docs/E1/limpieza.md``: el entorno no la tiene instalada y agregarla no es
necesario para cubrir el contrato de E1 de forma estricta y reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

VERSION = "1.0"

ENTRADA = Path("datos_crudos/inventario_turno_sintetico.csv")
FUENTES = {"auto", "sintetico", "real"}
FUENTE_POR_DEFECTO = "auto"
RAIZ_REPO = Path(__file__).resolve().parents[1]
METADATO_PROCEDENCIA = "_reporte_sintetico.json"

COLUMNAS_ENTRADA = [
    "unidad_id",
    "fecha",
    "turno",
    "insumo_id",
    "insumo_nombre",
    "familia",
    "existencia_inicial",
    "entradas",
    "consumo",
    "existencia_final",
    "desabasto",
    "pacientes_atendidos",
    "personal_disponible",
    "es_sintetico",
]

CLAVES = ["unidad_id", "fecha", "turno", "insumo_id"]
TURNOS = {"M", "V", "N"}
FAMILIAS = {"medicamento", "material_curacion"}
JORNADAS = {"M": "diurno", "V": "diurno", "N": "nocturno"}

COLUMNAS_NUMERICAS = [
    "existencia_inicial",
    "entradas",
    "consumo",
    "existencia_final",
    "desabasto",
    "pacientes_atendidos",
    "personal_disponible",
    "es_sintetico",
]

COLUMNAS_DERIVADAS = [
    "fuente",
    "imputado_consumo",
    "imputado_personal",
    "atipico_pacientes",
    "atipico_consumo",
    "consumo_analisis",
    "pacientes_analisis",
    "consumo_minmax",
    "consumo_zscore",
    "pacientes_minmax",
    "pacientes_zscore",
    "jornada",
    "dias_cobertura",
    "nivel_stock",
]
COLUMNAS_PLATA = COLUMNAS_ENTRADA + COLUMNAS_DERIVADAS

COLUMNAS_REDUCIDAS = [
    "unidad_id",
    "fecha",
    "turno",
    "insumo_id",
    "familia",
    "existencia_inicial",
    "entradas",
    "consumo",
    "existencia_final",
    "desabasto",
    "pacientes_atendidos",
    "personal_disponible",
    "es_sintetico",
    "fuente",
    "imputado_consumo",
    "imputado_personal",
    "atipico_pacientes",
    "atipico_consumo",
    "consumo_analisis",
    "pacientes_analisis",
    "consumo_minmax",
    "consumo_zscore",
    "pacientes_minmax",
    "pacientes_zscore",
    "jornada",
    "dias_cobertura",
    "nivel_stock",
]

UMBRAL_MAD = 3.5
FACTOR_MAD = 1.4826
NIVEL_STOCK_UMBRALES = [1.0, 3.0]
NIVEL_STOCK_ETIQUETAS = {
    0: "sin_stock",
    1: "critico",
    2: "bajo",
    3: "adecuado",
}

_RE_ENTERO = re.compile(r"^-?\d+$")


class ErrorEsquema(ValueError):
    """La tabla no cumple el contrato de la capa Plata."""


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _leer_entrada(ruta: Path) -> pd.DataFrame:
    """Lee Bronce como texto para validar sin imputaciones implícitas."""
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[])
    if list(df.columns) != COLUMNAS_ENTRADA:
        faltan = [c for c in COLUMNAS_ENTRADA if c not in df.columns]
        sobran = [c for c in df.columns if c not in COLUMNAS_ENTRADA]
        detalle = []
        if faltan:
            detalle.append(f"faltan columnas: {', '.join(faltan)}")
        if sobran:
            detalle.append(f"columnas inesperadas: {', '.join(sobran)}")
        if not detalle:
            detalle.append("el orden de columnas no coincide")
        raise ErrorEsquema("Contrato de entrada roto: " + "; ".join(detalle))
    return df


def _parse_entero(valor: object) -> tuple[int | None, str | None]:
    """Devuelve (entero, error). ``""`` se trata como faltante."""
    texto = str(valor).strip()
    if texto == "":
        return None, "falta"
    if not _RE_ENTERO.match(texto):
        return None, "invalido"
    return int(texto), None


def _validar_y_separar(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Valida fila a fila y separa válidas de cuarentena.

    Las claves duplicadas se detectan sobre **todas** las filas con los cuatro
    campos de clave no vacíos, antes de decidir validez. Todas las filas
    implicadas se rechazan, aunque una fuera válida por lo demás.

    Devuelve (válidas, cuarentena, metadatos). Las filas inválidas conservan
    sus valores originales y reciben una columna ``motivo`` no vacía.
    """
    registros = df.to_dict("records")
    parsed_rows: list[dict[str, Any] | None] = []
    motivos: dict[int, list[str]] = {}

    for i, fila in enumerate(registros):
        razones: list[str] = []
        parsed: dict[str, Any] = {}

        # Texto y claves.
        for columna in ("unidad_id", "insumo_id", "insumo_nombre"):
            valor = str(fila[columna]).strip()
            if valor == "":
                razones.append(f"falta {columna}")
            parsed[columna] = valor

        turno = str(fila["turno"]).strip()
        parsed["turno"] = turno
        if turno not in TURNOS:
            razones.append(f"turno inválido: {turno or '(vacío)'}")

        familia = str(fila["familia"]).strip()
        parsed["familia"] = familia
        if familia not in FAMILIAS:
            razones.append(f"familia inválida: {familia or '(vacío)'}")

        fecha_texto = str(fila["fecha"]).strip()
        parsed["fecha"] = fecha_texto
        try:
            fecha = date.fromisoformat(fecha_texto)
            if fecha.isoformat() != fecha_texto:
                raise ValueError
        except ValueError:
            razones.append(f"fecha inválida: {fecha_texto or '(vacío)'}")

        # Numéricas obligatorias.
        for columna in (
            "existencia_inicial",
            "entradas",
            "existencia_final",
            "desabasto",
            "pacientes_atendidos",
        ):
            valor, error = _parse_entero(fila[columna])
            if error == "falta":
                razones.append(f"falta {columna}")
            elif error == "invalido":
                razones.append(f"{columna} no es entero")
            if valor is not None:
                parsed[columna] = valor
                if valor < 0:
                    razones.append(f"{columna} negativo: {valor}")

        es_sintetico, error = _parse_entero(fila["es_sintetico"])
        if error == "falta":
            razones.append("falta es_sintetico")
        elif error == "invalido":
            razones.append("es_sintetico no es entero")
        if es_sintetico is not None:
            parsed["es_sintetico"] = es_sintetico
            if es_sintetico not in (0, 1):
                razones.append(f"es_sintetico inválido: {es_sintetico}")
        if parsed.get("desabasto") not in (None, 0, 1):
            razones.append(f"desabasto inválido: {parsed['desabasto']}")

        # Imputables: faltantes permitidos, valores inválidos no.
        consumo, error = _parse_entero(fila["consumo"])
        if error == "invalido":
            razones.append("consumo no es entero")
        elif error is None:
            parsed["consumo"] = consumo
            if consumo is not None and consumo < 0:
                razones.append(f"consumo negativo: {consumo}")

        personal, error = _parse_entero(fila["personal_disponible"])
        if error == "invalido":
            razones.append("personal_disponible no es entero")
        elif error is None:
            parsed["personal_disponible"] = personal
            if personal is not None and personal < 0:
                razones.append(f"personal_disponible negativo: {personal}")

        # Consistencia contable cuando los cuatro componentes están presentes.
        componentes = (
            parsed.get("existencia_inicial"),
            parsed.get("entradas"),
            parsed.get("existencia_final"),
            parsed.get("consumo"),
        )
        if all(v is not None for v in componentes):
            inicial, entradas, final, consumo_val = componentes
            if final != inicial + entradas - consumo_val:
                razones.append(
                    "consistencia: existencia_final != "
                    "existencia_inicial + entradas - consumo"
                )
        elif parsed.get("consumo") is None and all(
            parsed.get(k) is not None
            for k in ("existencia_inicial", "entradas", "existencia_final")
        ):
            derivado = (
                parsed["existencia_inicial"]
                + parsed["entradas"]
                - parsed["existencia_final"]
            )
            if derivado < 0:
                razones.append(
                    "consistencia: el balance implica consumo negativo "
                    f"({derivado})"
                )

        if razones:
            motivos[i] = razones
            parsed_rows.append(None)
        else:
            parsed_rows.append(parsed)

    # Claves duplicadas: se revisan todas las filas con los cuatro campos de
    # clave no vacíos, sin importar si la fila es válida por lo demás.
    claves: dict[tuple[str, str, str, str], list[int]] = {}
    for i, fila in enumerate(registros):
        if not all(str(fila[columna]).strip() for columna in CLAVES):
            continue
        clave = tuple(str(fila[columna]).strip() for columna in CLAVES)
        claves.setdefault(clave, []).append(i)  # type: ignore[arg-type]
    duplicadas = {
        i for indices in claves.values() if len(indices) > 1 for i in indices
    }
    for i in duplicadas:
        motivos.setdefault(i, []).append(
            "clave duplicada (unidad_id, fecha, turno, insumo_id)"
        )

    # Reconstruir válidas sin duplicadas y cuarentena con motivo.
    validos_finales: list[dict[str, Any]] = []
    for i, fila in enumerate(parsed_rows):
        if fila is not None and i not in motivos:
            validos_finales.append(fila)

    filas_cuarentena: list[dict[str, Any]] = []
    for i, fila in enumerate(registros):
        if i in motivos:
            salida = dict(fila)
            salida["motivo"] = "; ".join(motivos[i])
            filas_cuarentena.append(salida)

    plata = pd.DataFrame(validos_finales, columns=COLUMNAS_ENTRADA)
    cuarentena = pd.DataFrame(
        filas_cuarentena, columns=COLUMNAS_ENTRADA + ["motivo"]
    )
    meta = {
        "n_entrada": len(registros),
        "n_validas": len(plata),
        "n_cuarentena": len(cuarentena),
        "motivos": motivos,
    }
    return plata, cuarentena, meta


def _imputar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Imputa solo variables predictoras, con reglas agrupadas y banderas.

    ``consumo`` se recupera primero por balance de inventario; si no fuera
    posible, por mediana de (unidad, insumo, turno). ``personal_disponible`` se
    imputa por mediana de (unidad, turno). Claves y ``desabasto`` no se tocan.
    """
    df = df.copy()
    df["consumo"] = pd.to_numeric(df["consumo"], errors="coerce")
    df["personal_disponible"] = pd.to_numeric(
        df["personal_disponible"], errors="coerce"
    )
    df["imputado_consumo"] = 0
    df["imputado_personal"] = 0

    # --- consumo ---------------------------------------------------------
    faltan_consumo = df["consumo"].isna()
    n_consumo_balance = 0
    n_consumo_mediana = 0
    if faltan_consumo.any():
        balance = (
            df["existencia_inicial"]
            + df["entradas"]
            - df["existencia_final"]
        )
        por_balance = faltan_consumo & balance.notna() & (balance >= 0)
        df.loc[por_balance, "consumo"] = balance.loc[por_balance]
        df.loc[por_balance, "imputado_consumo"] = 1
        n_consumo_balance = int(por_balance.sum())

        restantes = df["consumo"].isna()
        if restantes.any():
            mediana_grupo = df.groupby(
                ["unidad_id", "insumo_id", "turno"], sort=True
            )["consumo"].transform("median")
            df.loc[restantes, "consumo"] = mediana_grupo.loc[restantes]
            df.loc[restantes, "imputado_consumo"] = 1
            n_consumo_mediana = int(df.loc[restantes, "consumo"].notna().sum())

            restantes2 = df["consumo"].isna()
            if restantes2.any():
                mediana_global = df["consumo"].median()
                if pd.isna(mediana_global):
                    mediana_global = 0.0
                df.loc[restantes2, "consumo"] = mediana_global
                n_consumo_mediana += int(restantes2.sum())

    df["consumo"] = np.floor(
        pd.to_numeric(df["consumo"], errors="coerce") + 0.5
    ).astype(int)

    # --- personal_disponible --------------------------------------------
    faltan_personal = df["personal_disponible"].isna()
    n_personal_grupo = 0
    n_personal_turno = 0
    n_personal_global = 0
    if faltan_personal.any():
        mediana_grupo = df.groupby(
            ["unidad_id", "turno"], sort=True
        )["personal_disponible"].transform("median")
        llenados_grupo = faltan_personal & mediana_grupo.notna()
        df.loc[llenados_grupo, "personal_disponible"] = mediana_grupo.loc[
            llenados_grupo
        ]
        n_personal_grupo = int(llenados_grupo.sum())

        restantes_turno = df["personal_disponible"].isna()
        if restantes_turno.any():
            mediana_turno = df.groupby("turno", sort=True)[
                "personal_disponible"
            ].transform("median")
            llenados_turno = restantes_turno & mediana_turno.notna()
            df.loc[llenados_turno, "personal_disponible"] = mediana_turno.loc[
                llenados_turno
            ]
            n_personal_turno = int(llenados_turno.sum())

            restantes_global = df["personal_disponible"].isna()
            if restantes_global.any():
                mediana_global = df["personal_disponible"].median()
                if pd.isna(mediana_global):
                    mediana_global = 1.0
                df.loc[restantes_global, "personal_disponible"] = mediana_global
                n_personal_global = int(restantes_global.sum())

        df.loc[faltan_personal, "imputado_personal"] = 1

    df["personal_disponible"] = np.floor(
        pd.to_numeric(df["personal_disponible"], errors="coerce") + 0.5
    ).astype(int)

    detalle = {
        "consumo": {
            "n": int(faltan_consumo.sum()),
            "n_balance": n_consumo_balance,
            "n_mediana_grupo": n_consumo_mediana,
            "metodo": (
                "balance de inventario "
                "(existencia_inicial + entradas - existencia_final); "
                "respaldo: mediana por (unidad_id, insumo_id, turno)"
            ),
            "bandera": "imputado_consumo",
        },
        "personal_disponible": {
            "n": int(faltan_personal.sum()),
            "n_mediana_grupo": n_personal_grupo,
            "n_mediana_turno": n_personal_turno,
            "n_global": n_personal_global,
            "metodo": (
                "mediana por (unidad_id, turno); respaldo: mediana por turno "
                "y mediana global"
            ),
            "bandera": "imputado_personal",
        },
    }
    return df, detalle


def _limites_robustos(serie: pd.Series) -> tuple[float, float] | None:
    """Límites median ± 3.5·1.4826·MAD; respaldo IQR si MAD=0."""
    valores = pd.to_numeric(serie, errors="coerce").dropna().astype(float)
    if valores.empty:
        return None
    mediana = float(valores.median())
    mad = float((valores - mediana).abs().median())
    if mad > 0:
        escala = FACTOR_MAD * mad
    else:
        q1 = float(valores.quantile(0.25))
        q3 = float(valores.quantile(0.75))
        iqr = q3 - q1
        if iqr <= 0:
            return None
        escala = iqr / 1.349
    return max(0.0, mediana - UMBRAL_MAD * escala), mediana + UMBRAL_MAD * escala


def _tratar_atipicos(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Marca atípicos por grupo y winsoriza solo la variable de análisis."""
    df = df.copy()
    df["atipico_pacientes"] = 0
    df["atipico_consumo"] = 0
    df["pacientes_analisis"] = df["pacientes_atendidos"].astype(float)
    df["consumo_analisis"] = df["consumo"].astype(float)

    def procesar(
        columna: str,
        grupos: list[str],
        bandera: str,
        analisis: str,
    ) -> dict[str, Any]:
        marcados = pd.Series(False, index=df.index)
        n_altos = 0
        n_bajos = 0
        for _, indices in df.groupby(grupos, sort=True).groups.items():
            serie = df.loc[indices, columna].astype(float)
            limites = _limites_robustos(serie)
            if limites is None:
                continue
            inferior, superior = limites
            altos = serie > superior
            bajos = serie < inferior
            n_altos += int(altos.sum())
            n_bajos += int(bajos.sum())
            marcados.loc[indices] = altos | bajos
            df.loc[indices, analisis] = serie.clip(inferior, superior)
        df[bandera] = marcados.astype(int)
        return {
            "n": int(marcados.sum()),
            "n_altos": n_altos,
            "n_bajos": n_bajos,
            "metodo": (
                "MAD robusto por grupo (|x - mediana| > 3.5·1.4826·MAD); "
                "respaldo IQR/1.349 si MAD=0"
            ),
            "umbral_mad": UMBRAL_MAD,
            "grupos": grupos,
            "tratamiento": (
                f"winsorización en {analisis}; la variable original "
                f"{columna} no se sobrescribe ni se elimina"
            ),
            "bandera": bandera,
            "columna_analisis": analisis,
        }

    detalle = {
        "pacientes_atendidos": procesar(
            "pacientes_atendidos",
            ["unidad_id", "turno"],
            "atipico_pacientes",
            "pacientes_analisis",
        ),
        "consumo": procesar(
            "consumo",
            ["unidad_id", "insumo_id", "turno"],
            "atipico_consumo",
            "consumo_analisis",
        ),
    }
    return df, detalle


def _minmax(serie: pd.Series) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce").astype(float)
    if valores.empty:
        return pd.Series(dtype=float, index=serie.index)
    minimo = float(valores.min())
    maximo = float(valores.max())
    if not np.isfinite(minimo) or not np.isfinite(maximo) or maximo == minimo:
        return pd.Series(0.0, index=serie.index)
    return (valores - minimo) / (maximo - minimo)


def _zscore(serie: pd.Series) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce").astype(float)
    if valores.empty:
        return pd.Series(dtype=float, index=serie.index)
    media = float(valores.mean())
    desviacion = float(valores.std(ddof=0))
    if not np.isfinite(desviacion) or desviacion == 0:
        return pd.Series(0.0, index=serie.index)
    return (valores - media) / desviacion


def _transformar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Agrega transformaciones derivadas sin tocar las variables originales."""
    df = df.copy()
    if df.empty:
        for columna in (
            "consumo_minmax",
            "consumo_zscore",
            "pacientes_minmax",
            "pacientes_zscore",
            "dias_cobertura",
        ):
            df[columna] = pd.Series(dtype=float)
        df["jornada"] = pd.Series(dtype=str)
        df["nivel_stock"] = pd.Series(dtype=int)
        return df, _detalle_transformaciones()

    df["consumo_minmax"] = _minmax(df["consumo_analisis"])
    df["consumo_zscore"] = _zscore(df["consumo_analisis"])
    df["pacientes_minmax"] = _minmax(df["pacientes_analisis"])
    df["pacientes_zscore"] = _zscore(df["pacientes_analisis"])
    df["jornada"] = df["turno"].map(JORNADAS)

    denominador = df["consumo_analisis"].astype(float).clip(lower=1.0)
    df["dias_cobertura"] = df["existencia_final"].astype(float) / denominador
    df["nivel_stock"] = np.select(
        [
            df["existencia_final"] <= 0,
            df["dias_cobertura"] < NIVEL_STOCK_UMBRALES[0],
            df["dias_cobertura"] < NIVEL_STOCK_UMBRALES[1],
        ],
        [0, 1, 2],
        default=3,
    ).astype(int)
    return df, _detalle_transformaciones()


def _detalle_transformaciones() -> dict[str, Any]:
    return {
        "minmax": {
            "variables": ["consumo", "pacientes_atendidos"],
            "columnas": ["consumo_minmax", "pacientes_minmax"],
            "base": ["consumo_analisis", "pacientes_analisis"],
            "rango": [0.0, 1.0],
            "advertencia": (
                "En E2 los mínimos y máximos deben ajustarse solo con train "
                "y aplicarse a validación/prueba sin recalcular."
            ),
        },
        "zscore": {
            "variables": ["consumo", "pacientes_atendidos"],
            "columnas": ["consumo_zscore", "pacientes_zscore"],
            "base": ["consumo_analisis", "pacientes_analisis"],
            "ddof": 0,
            "advertencia": (
                "En E2 la media y desviación deben estimarse solo con train."
            ),
        },
        "discretizacion": {
            "jornada": {
                "columna": "jornada",
                "turno": JORNADAS,
                "jerarquia": "turno operativo -> jornada diurna/nocturna",
            },
            "nivel_stock": {
                "columna": "nivel_stock",
                "variable": "dias_cobertura",
                "formula": "existencia_final / max(consumo_analisis, 1)",
                "umbrales": NIVEL_STOCK_UMBRALES,
                "etiquetas": {str(k): v for k, v in NIVEL_STOCK_ETIQUETAS.items()},
                "regla": (
                    "0 si existencia_final=0; 1 si 0<dias<1; "
                    "2 si 1<=dias<3; 3 si dias>=3"
                ),
            },
            "familia": {
                "columna": "familia",
                "categorias": sorted(FAMILIAS),
                "jerarquia": "insumo_id -> familia",
            },
        },
    }


def _validar_plata_detalle(df: pd.DataFrame) -> list[str]:
    errores: list[str] = []
    if list(df.columns) != COLUMNAS_PLATA:
        faltan = [c for c in COLUMNAS_PLATA if c not in df.columns]
        sobran = [c for c in df.columns if c not in COLUMNAS_PLATA]
        detalle = []
        if faltan:
            detalle.append(f"faltan {', '.join(faltan)}")
        if sobran:
            detalle.append(f"sobran {', '.join(sobran)}")
        if not detalle:
            detalle.append("orden distinto")
        errores.append("columnas de Plata: " + "; ".join(detalle))

    # Claves y nulos.
    for columna in COLUMNAS_PLATA:
        if columna not in df.columns:
            continue
        serie = df[columna]
        if serie.isna().any():
            errores.append(f"{columna} tiene nulos")
        if serie.dtype == object and serie.astype(str).str.strip().eq("").any():
            errores.append(f"{columna} tiene cadenas vacías")

    if all(c in df.columns for c in CLAVES):
        duplicadas = int(df.duplicated(subset=CLAVES).sum())
        if duplicadas:
            errores.append(f"clave duplicada: {duplicadas} filas")

    # Tipos numéricos y rangos.
    for columna in COLUMNAS_NUMERICAS:
        if columna not in df.columns:
            continue
        valores = pd.to_numeric(df[columna], errors="coerce")
        if valores.isna().any():
            errores.append(f"{columna} no es numérico o tiene nulos")
            continue
        if (valores < 0).any():
            errores.append(f"{columna} tiene valores negativos")
    for columna in (
        "imputado_consumo",
        "imputado_personal",
        "atipico_pacientes",
        "atipico_consumo",
    ):
        if columna not in df.columns:
            continue
        valores = pd.to_numeric(df[columna], errors="coerce")
        if valores.isna().any() or not valores.isin([0, 1]).all():
            errores.append(f"{columna} debe ser binaria (0/1)")
    for columna in ("desabasto", "es_sintetico"):
        if columna in df.columns:
            valores = pd.to_numeric(df[columna], errors="coerce")
            if valores.isna().any() or not valores.isin([0, 1]).all():
                errores.append(f"{columna} inválido: debe ser 0/1")

    # Procedencia: fuente válida y coherente con una marca sintética uniforme.
    if "fuente" in df.columns:
        fuentes = df["fuente"].astype(str)
        if not fuentes.isin({"sintetico", "real"}).all():
            errores.append("fuente inválida: debe ser sintetico o real")
        if fuentes.nunique() > 1:
            errores.append("fuente no uniforme")
        if "es_sintetico" in df.columns:
            marcas = pd.to_numeric(df["es_sintetico"], errors="coerce")
            if marcas.nunique() > 1:
                errores.append("es_sintetico no uniforme")
            coherencia = (fuentes == "sintetico") == (marcas == 1)
            if not bool(coherencia.all()):
                errores.append("fuente incoherente con es_sintetico")

    # Categorías y fechas.
    if "turno" in df.columns and not df["turno"].isin(TURNOS).all():
        errores.append("turno inválido: valores fuera de M/V/N")
    if "familia" in df.columns and not df["familia"].isin(FAMILIAS).all():
        errores.append("familia inválida")
    if "jornada" in df.columns and not df["jornada"].isin({"diurno", "nocturno"}).all():
        errores.append("jornada inválida")
    if "fecha" in df.columns:
        fechas = pd.to_datetime(df["fecha"], format="%Y-%m-%d", errors="coerce")
        if fechas.isna().any():
            errores.append("fecha inválida")

    # Consistencia contable.
    if all(
        c in df.columns
        for c in ("existencia_inicial", "entradas", "consumo", "existencia_final")
    ):
        calculado = (
            pd.to_numeric(df["existencia_inicial"], errors="coerce")
            + pd.to_numeric(df["entradas"], errors="coerce")
            - pd.to_numeric(df["consumo"], errors="coerce")
        )
        observado = pd.to_numeric(df["existencia_final"], errors="coerce")
        if not np.allclose(
            calculado.to_numpy(dtype=float),
            observado.to_numpy(dtype=float),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        ):
            errores.append(
                "consistencia: existencia_final != "
                "existencia_inicial + entradas - consumo"
            )

    # Transformaciones.
    for columna in ("consumo_minmax", "pacientes_minmax"):
        if columna in df.columns:
            valores = pd.to_numeric(df[columna], errors="coerce")
            if valores.isna().any() or not valores.between(0, 1).all():
                errores.append(f"{columna} fuera de [0, 1]")
    for columna in ("consumo_zscore", "pacientes_zscore"):
        if columna in df.columns:
            valores = pd.to_numeric(df[columna], errors="coerce")
            if valores.isna().any() or not np.isfinite(valores).all():
                errores.append(f"{columna} no es finito")
    if "nivel_stock" in df.columns:
        valores = pd.to_numeric(df["nivel_stock"], errors="coerce")
        if valores.isna().any() or not valores.isin([0, 1, 2, 3]).all():
            errores.append("nivel_stock inválido")
    if "dias_cobertura" in df.columns:
        valores = pd.to_numeric(df["dias_cobertura"], errors="coerce")
        if valores.isna().any() or (valores < 0).any():
            errores.append("dias_cobertura inválida")
    for columna in ("consumo_analisis", "pacientes_analisis"):
        if columna in df.columns:
            valores = pd.to_numeric(df[columna], errors="coerce")
            if valores.isna().any() or (valores < 0).any():
                errores.append(f"{columna} inválida")
    return errores


def validar_plata(df: pd.DataFrame) -> list[str]:
    """Valida el contrato de Plata y devuelve la lista de errores."""
    return _validar_plata_detalle(df)


def exigir_plata(df: pd.DataFrame) -> None:
    errores = validar_plata(df)
    if errores:
        raise ErrorEsquema("Contrato de Plata roto:\n- " + "\n- ".join(errores))


def _resumen_nulos(
    nula: pd.Series, df: pd.DataFrame, grupo: str
) -> dict[str, dict[str, Any]]:
    salida: dict[str, dict[str, Any]] = {}
    for valor, indices in df.groupby(grupo, sort=True).groups.items():
        sub = nula.loc[indices]
        total = int(len(sub))
        nulos = int(sub.sum())
        salida[str(valor)] = {
            "nulos": nulos,
            "total": total,
            "tasa": (nulos / total) if total else 0.0,
        }
    return salida


def _leer_meta_sintetico(
    entrada: Path,
) -> tuple[dict[str, Any] | None, bool, str | None]:
    """Devuelve (metadato, existe, error). No confunde ausencia con invalidez."""
    ruta = entrada.with_name("_reporte_sintetico.json")
    if not ruta.exists():
        return None, False, None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, True, f"metadato ilegible: {exc}"
    if not isinstance(datos, dict):
        return None, True, "el metadato no es un objeto JSON"
    return datos, True, None


def _verificar_procedencia(
    df: pd.DataFrame,
    entrada: Path,
    sha_entrada: str,
    fuente_solicitada: str,
) -> tuple[str, bool, dict[str, Any], dict[str, Any] | None]:
    """Verifica la marca sintética y el hash declarado antes de procesar.

    Devuelve ``(fuente_verificada, es_sintetico, procedencia, meta_usado)``.
    """
    if fuente_solicitada not in FUENTES:
        raise ErrorEsquema(
            f"fuente inválida: {fuente_solicitada!r}; use auto, sintetico o real"
        )

    marcas = df["es_sintetico"].astype(str).str.strip()
    valores = set(marcas.unique())
    if not valores or not valores.issubset({"0", "1"}):
        raise ErrorEsquema(
            "es_sintetico debe contener solo 0 o 1; se encontró: "
            + ", ".join(sorted(valores))
        )
    if len(valores) != 1:
        raise ErrorEsquema(
            "es_sintetico no es uniforme en la entrada: mezcla de "
            + ", ".join(sorted(valores))
        )

    datos_sinteticos = valores == {"1"}
    meta, existe_meta, error_meta = _leer_meta_sintetico(entrada)
    declarado = meta.get("sha256") if meta is not None else None
    coincide = bool(declarado) and declarado == sha_entrada

    if fuente_solicitada == "auto":
        fuente = "sintetico" if datos_sinteticos else "real"
    else:
        fuente = fuente_solicitada

    if fuente == "sintetico":
        if not datos_sinteticos:
            raise ErrorEsquema(
                "fuente sintetica solicitada, pero es_sintetico no es 1 en "
                "todas las filas"
            )
        if not existe_meta:
            raise ErrorEsquema(
                "fuente sintetica sin _reporte_sintetico.json junto a la entrada"
            )
        if error_meta is not None:
            raise ErrorEsquema(
                "fuente sintetica con metadatos inválidos: " + error_meta
            )
        if not coincide:
            raise ErrorEsquema(
                "el sha256 declarado por _reporte_sintetico.json no coincide "
                "con el sha256 de la entrada"
            )
        usado = True
        advertencia = ""
        meta_usado = meta
    else:
        if datos_sinteticos:
            raise ErrorEsquema(
                "fuente real solicitada, pero es_sintetico=1 en la entrada"
            )
        usado = False
        meta_usado = None
        advertencia = (
            "ADVERTENCIA: fuente real. Los datos no son sintéticos y sus "
            "derivados no deben publicarse sin autorización; los metadatos "
            "sintéticos, si existen, no se usan."
        )

    procedencia = {
        "fuente_solicitada": fuente_solicitada,
        "fuente_verificada": fuente,
        "es_sintetico_datos": 1 if datos_sinteticos else 0,
        "sha256_entrada": sha_entrada,
        "metadatos_sinteticos": {
            "ruta": entrada.with_name("_reporte_sintetico.json").as_posix(),
            "existe": existe_meta,
            "usado": usado,
            "sha256_declarado": declarado,
            "coincide": coincide if declarado is not None else None,
            "error": error_meta,
        },
        "advertencia": advertencia,
    }
    return fuente, datos_sinteticos, procedencia, meta_usado


def _p_valor_chi2(estadistico: float, gl: int) -> float | None:
    """Supervivencia chi-cuadrado para gl=1 (erfc) y gl=2 (exp)."""
    if estadistico < 0 or gl <= 0:
        return None
    if gl == 1:
        return math.erfc(math.sqrt(estadistico / 2.0))
    if gl == 2:
        return math.exp(-estadistico / 2.0)
    return None


def _prueba_chi2(nula: pd.Series, grupos: pd.Series) -> dict[str, Any]:
    """Chi-cuadrado de Pearson para faltante vs categoría, sin dependencias."""
    estados = nula.fillna(False).astype(int)
    etiquetas = grupos.astype(str)
    categorias = sorted(etiquetas.unique())

    tabla: list[list[int]] = []
    filas: list[str] = []
    for estado in (0, 1):
        fila = [
            int(((estados == estado) & (etiquetas == categoria)).sum())
            for categoria in categorias
        ]
        if sum(fila):
            tabla.append(fila)
            filas.append(str(estado))

    # Eliminar categorías sin observaciones.
    if tabla:
        conservar = [
            j for j in range(len(categorias)) if sum(fila[j] for fila in tabla)
        ]
        categorias = [categorias[j] for j in conservar]
        tabla = [[fila[j] for j in conservar] for fila in tabla]

    if len(tabla) < 2 or len(categorias) < 2:
        return {
            "estadistico": None,
            "gl": 0,
            "p_valor": None,
            "tabla": tabla,
            "filas": filas,
            "columnas": categorias,
            "advertencia": (
                "No hay suficientes categorías u observaciones para la prueba; "
                "no prueba causalidad."
            ),
        }

    total = sum(sum(fila) for fila in tabla)
    totales_fila = [sum(fila) for fila in tabla]
    totales_col = [sum(tabla[i][j] for i in range(len(tabla))) for j in range(len(categorias))]
    esperados = [
        [totales_fila[i] * totales_col[j] / total for j in range(len(categorias))]
        for i in range(len(tabla))
    ]
    if any(valor <= 0 for fila in esperados for valor in fila):
        return {
            "estadistico": None,
            "gl": 0,
            "p_valor": None,
            "tabla": tabla,
            "filas": filas,
            "columnas": categorias,
            "advertencia": (
                "Hay frecuencias esperadas nulas; la prueba no es calculable. "
                "No prueba causalidad."
            ),
        }

    estadistico = sum(
        (tabla[i][j] - esperados[i][j]) ** 2 / esperados[i][j]
        for i in range(len(tabla))
        for j in range(len(categorias))
    )
    gl = (len(tabla) - 1) * (len(categorias) - 1)
    p_valor = _p_valor_chi2(estadistico, gl)
    return {
        "estadistico": estadistico,
        "gl": gl,
        "p_valor": p_valor,
        "tabla": tabla,
        "filas": filas,
        "columnas": categorias,
        "esperados_minimos": min(valor for fila in esperados for valor in fila),
        "advertencia": (
            "Prueba chi-cuadrado descriptiva; no prueba causalidad. Con "
            "frecuencias esperadas menores a 5 el p-valor es aproximado."
        ),
    }


def _formato_p(prueba: dict[str, Any]) -> str:
    p = prueba.get("p_valor")
    if p is None:
        return "no calculable"
    return f"{p:.3f}"


def _formato_estadistico(prueba: dict[str, Any]) -> str:
    valor = prueba.get("estadistico")
    if valor is None:
        return "no calculable"
    return f"{valor:.3f}"


def _lectura_consumo(
    detalle: dict[str, Any], pruebas: dict[str, Any], fuente: str
) -> str:
    por_turno = detalle["por_turno"]
    turno_min = min(por_turno.items(), key=lambda par: par[1]["tasa"])
    turno_max = max(por_turno.items(), key=lambda par: par[1]["tasa"])
    por_des = detalle["por_desabasto"]
    tasa_0 = por_des.get("0", {}).get("tasa", 0.0)
    tasa_1 = por_des.get("1", {}).get("tasa", 0.0)
    p_turno = pruebas["consumo_vs_turno"]
    p_des = pruebas["consumo_vs_desabasto"]
    texto = (
        f"La tasa de consumo faltante va de {turno_min[1]['tasa']:.1%} en "
        f"{turno_min[0]} a {turno_max[1]['tasa']:.1%} en {turno_max[0]}; "
        f"con desabasto=0 es {tasa_0:.1%} y con desabasto=1 es {tasa_1:.1%}. "
        f"Chi-cuadrado vs turno: estadístico={_formato_estadistico(p_turno)}, "
        f"gl={p_turno['gl']}, p={_formato_p(p_turno)}; vs desabasto: "
        f"estadístico={_formato_estadistico(p_des)}, gl={p_des['gl']}, "
        f"p={_formato_p(p_des)}."
    )
    if fuente == "sintetico":
        texto += (
            " El generador sintético declara un componente MCAR y uno MNAR; "
            "la evidencia observada no permite separarlos."
        )
    texto += (
        " Las diferencias son descriptivas y no prueban causalidad; no se "
        "afirma MCAR/MAR/MNAR como certeza."
    )
    return texto


def _lectura_personal(
    detalle: dict[str, Any], pruebas: dict[str, Any], fuente: str
) -> str:
    por_turno = detalle["por_turno"]
    tasa_n = por_turno.get("N", {}).get("tasa", 0.0)
    resto = [datos["tasa"] for turno, datos in por_turno.items() if turno != "N"]
    tasa_resto = max(resto) if resto else 0.0
    prueba = pruebas["personal_vs_turno_nocturno"]
    texto = (
        f"La tasa de personal faltante es {tasa_n:.1%} en el turno N y "
        f"{tasa_resto:.1%} en el resto. Chi-cuadrado N vs resto: "
        f"estadístico={_formato_estadistico(prueba)}, gl={prueba['gl']}, "
        f"p={_formato_p(prueba)}."
    )
    if fuente == "sintetico":
        texto += (
            " Es compatible con el mecanismo declarado MAR por turno "
            "nocturno, sin que la observación pruebe causalidad."
        )
    texto += (
        " La diferencia es descriptiva y no prueba causalidad; no se afirma "
        "MCAR/MAR/MNAR como certeza."
    )
    return texto


def _diagnostico_mecanismos(
    df_entrada: pd.DataFrame,
    fuente: str,
    meta_sintetico: dict[str, Any] | None,
) -> dict[str, Any]:
    """Diagnóstico dinámico; separa metadatos verificados de evidencia observada."""
    if fuente == "sintetico" and meta_sintetico is not None:
        faltantes = meta_sintetico.get("faltantes", {})
        conocidos: dict[str, Any] = {
            "disponible": True,
            "fuente": "datos_crudos/_reporte_sintetico.json",
            "mcar": {
                "n": faltantes.get("mcar"),
                "columnas": ["consumo"],
                "descripcion": (
                    "pérdida aleatoria de consumo, independiente de "
                    "covariables observadas"
                ),
            },
            "mar": {
                "n": faltantes.get("mar"),
                "columnas": ["personal_disponible"],
                "descripcion": (
                    "pérdida de personal_disponible condicionada al turno "
                    "nocturno observado"
                ),
            },
            "mnar": {
                "n": faltantes.get("mnar"),
                "columnas": ["consumo"],
                "descripcion": (
                    "pérdida de consumo condicionada al propio valor: se "
                    "ocultan consumos altos"
                ),
            },
            "sha256_declarado": meta_sintetico.get("sha256"),
        }
    else:
        conocidos = {
            "disponible": False,
            "fuente": "no aplica: fuente real o sin metadatos verificados",
        }

    nula_consumo = df_entrada["consumo"].eq("")
    nula_personal = df_entrada["personal_disponible"].eq("")
    pruebas = {
        "consumo_vs_turno": _prueba_chi2(
            nula_consumo, df_entrada["turno"]
        ),
        "consumo_vs_desabasto": _prueba_chi2(
            nula_consumo, df_entrada["desabasto"]
        ),
        "personal_vs_turno_nocturno": _prueba_chi2(
            nula_personal,
            df_entrada["turno"].map(lambda t: "N" if t == "N" else "resto"),
        ),
    }

    evidencia: dict[str, Any] = {}
    for columna, nula in (
        ("consumo", nula_consumo),
        ("personal_disponible", nula_personal),
    ):
        total = int(len(df_entrada))
        nulos = int(nula.sum())
        detalle: dict[str, Any] = {
            "nulos": nulos,
            "total": total,
            "tasa": (nulos / total) if total else 0.0,
            "por_turno": _resumen_nulos(nula, df_entrada, "turno"),
            "por_unidad": _resumen_nulos(nula, df_entrada, "unidad_id"),
            "por_insumo": _resumen_nulos(nula, df_entrada, "insumo_id"),
            "por_desabasto": _resumen_nulos(nula, df_entrada, "desabasto"),
        }
        if columna == "consumo":
            detalle["lectura"] = _lectura_consumo(detalle, pruebas, fuente)
        else:
            detalle["lectura"] = _lectura_personal(detalle, pruebas, fuente)
        evidencia[columna] = detalle

    evidencia["pruebas_estadisticas"] = pruebas
    evidencia["advertencia"] = (
        "La evidencia observada es descriptiva y no prueba causalidad. En "
        "datos reales no se afirmará MCAR/MAR/MNAR como certeza: solo se "
        "reportarán patrones compatibles y la necesidad de análisis o "
        "sensibilidad adicionales."
    )

    comparacion: dict[str, Any] = {}
    for columna, clave in (
        ("consumo", ("mcar", "mnar")),
        ("personal_disponible", ("mar",)),
    ):
        observados = evidencia[columna]["nulos"]
        if fuente != "sintetico" or meta_sintetico is None:
            comparacion[columna] = {
                "nulos_observados": observados,
                "nulos_declarados_generador": None,
                "coincide": None,
            }
            continue
        declarados = 0
        for nombre in clave:
            valor = conocidos.get(nombre, {}).get("n")
            if valor is not None:
                declarados += int(valor)
        comparacion[columna] = {
            "nulos_observados": observados,
            "nulos_declarados_generador": declarados,
            "coincide": observados == declarados,
        }

    return {
        "conocidos_sintetico": conocidos,
        "evidencia_observada": evidencia,
        "comparacion": comparacion,
    }


def _contar_motivos(cuarentena: pd.DataFrame) -> dict[str, int]:
    contador: Counter[str] = Counter()
    if "motivo" in cuarentena.columns:
        for motivo in cuarentena["motivo"].fillna(""):
            for parte in str(motivo).split("; "):
                if parte:
                    contador[parte] += 1
    return dict(sorted(contador.items()))


def _resolver_rutas(
    entrada: Path,
    fuente: str,
    plata: Path | None,
    reducido: Path | None,
    cuarentena: Path | None,
    reporte: Path | None,
) -> dict[str, Path]:
    """Deriva/valida rutas antes de escribir y bloquea destinos inseguros.

    Las rutas explícitas fuera del repositorio se permiten (útil para pruebas
    y ejecuciones temporales). Dentro del repositorio solo se aceptan las
    carpetas derivadas de la fuente; así los derivados reales no caen en
    directorios versionados ni se mezclan con los sintéticos.
    """
    entrada_resuelta = Path(entrada).resolve()
    raiz = RAIZ_REPO.resolve()
    crudos = (raiz / "datos_crudos").resolve()

    nombres = {
        "plata": "inventario_turno_plata.csv",
        "reducido": "inventario_turno_reducido.csv",
        "cuarentena": "inventario_turno_invalido.csv",
        "reporte": "_reporte.json",
    }
    valores: dict[str, Path | None] = {
        "plata": plata,
        "reducido": reducido,
        "cuarentena": cuarentena,
        "reporte": reporte,
    }
    permitidas = {
        "plata": (raiz / "datos_plata" / fuente).resolve(),
        "reducido": (raiz / "datos_plata" / fuente).resolve(),
        "cuarentena": (raiz / "cuarentena" / fuente).resolve(),
        "reporte": (raiz / "cuarentena" / fuente).resolve(),
    }
    salidas: dict[str, Path] = {}
    for nombre, valor in valores.items():
        if valor is not None:
            salida = Path(valor).resolve()
        else:
            carpeta = "datos_plata" if nombre in {"plata", "reducido"} else "cuarentena"
            salida = (Path(carpeta) / fuente / nombres[nombre]).resolve()

        if salida == entrada_resuelta:
            raise ErrorEsquema(f"la salida {nombre} no puede ser la entrada")
        if salida.name == METADATO_PROCEDENCIA:
            raise ErrorEsquema(
                f"la salida {nombre} no puede sobrescribir el reporte de procedencia"
            )
        if salida == crudos or crudos in salida.parents:
            raise ErrorEsquema(
                f"la salida {nombre} cae dentro del árbol datos_crudos/: {salida}"
            )

        dentro_repo = salida == raiz or raiz in salida.parents
        if dentro_repo:
            base = permitidas[nombre]
            if salida != base and base not in salida.parents:
                raise ErrorEsquema(
                    f"la salida {nombre} debe estar bajo {base} o fuera del "
                    f"repositorio; se pidió {salida}"
                )
        salidas[nombre] = salida

    if len(set(salidas.values())) != len(salidas):
        raise ErrorEsquema("dos o más salidas comparten la misma ruta")
    return salidas


def _temporal_en_destino(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, nombre = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    os.close(descriptor)
    return Path(nombre)


def _preparar_csv_temporal(
    df: pd.DataFrame, ruta: Path, columnas: list[str] | None = None
) -> Path:
    temporal = _temporal_en_destino(ruta)
    df.to_csv(
        temporal,
        index=False,
        columns=columnas,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.6f",
    )
    return temporal


def _preparar_json_temporal(datos: dict[str, Any], ruta: Path) -> Path:
    temporal = _temporal_en_destino(ruta)
    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return temporal


def _publicar_temporales(
    temporales: list[tuple[Path, Path]], entrada: Path, sha_esperado: str
) -> None:
    """Verifica Bronce y publica el conjunto con rollback si algo falla.

    Antes de reemplazar cada destino se guarda una copia de seguridad. Si
    cualquier reemplazo o la verificación final del SHA falla, se restauran
    todos los destinos y se eliminan los temporales, de modo que no queden
    salidas mezcladas.
    """
    respaldos: list[tuple[Path, Path | None]] = []
    publicados: list[Path] = []
    try:
        sha_verificado = _sha256(entrada)
        if sha_verificado != sha_esperado:
            raise ErrorEsquema(
                "La capa Bronce cambió antes de publicar: "
                f"{sha_esperado} != {sha_verificado}"
            )

        for temporal, destino in temporales:
            if destino.exists():
                respaldo = _temporal_en_destino(destino)
                try:
                    shutil.copy2(destino, respaldo)
                except Exception:
                    respaldo.unlink(missing_ok=True)
                    raise
                shutil.copymode(destino, temporal)
            else:
                respaldo = None
                os.chmod(temporal, 0o644)
            respaldos.append((destino, respaldo))
            os.replace(temporal, destino)
            publicados.append(destino)

        sha_final = _sha256(entrada)
        if sha_final != sha_esperado:
            raise ErrorEsquema(
                "La capa Bronce cambió durante la publicación: "
                f"{sha_esperado} != {sha_final}"
            )
    except Exception as exc:
        fallos: list[str] = []
        for destino, respaldo in reversed(respaldos):
            try:
                if respaldo is not None and respaldo.exists():
                    os.replace(respaldo, destino)
                elif destino in publicados and destino.exists():
                    destino.unlink()
            except OSError as error:
                fallos.append(f"{destino}: {error}")
        if fallos:
            raise ErrorEsquema(
                "La publicación falló y no se pudieron restaurar todos los "
                "destinos: " + "; ".join(fallos)
            ) from exc
        raise
    finally:
        for temporal, _ in temporales:
            if temporal.exists():
                temporal.unlink()
        for _, respaldo in respaldos:
            if respaldo is not None and respaldo.exists():
                respaldo.unlink()


def ejecutar(
    entrada: Path = ENTRADA,
    plata: Path | None = None,
    reducido: Path | None = None,
    cuarentena: Path | None = None,
    reporte: Path | None = None,
    fuente: str = FUENTE_POR_DEFECTO,
) -> dict[str, Any]:
    """Ejecuta el pipeline completo y devuelve el reporte de diagnóstico."""
    entrada = Path(entrada)

    sha_antes = _sha256(entrada)
    df_entrada = _leer_entrada(entrada)
    fuente_verificada, es_sintetico, procedencia, meta_usado = (
        _verificar_procedencia(
            df_entrada, entrada, sha_antes, fuente
        )
    )
    rutas = _resolver_rutas(
        entrada, fuente_verificada, plata, reducido, cuarentena, reporte
    )

    validas, filas_cuarentena, meta_validacion = _validar_y_separar(df_entrada)
    validas, detalle_imputacion = _imputar(validas)
    validas, detalle_atipicos = _tratar_atipicos(validas)
    validas, detalle_transformaciones = _transformar(validas)

    # Orden determinista, procedencia y tipos finales.
    validas["fuente"] = fuente_verificada
    validas = validas.sort_values(CLAVES, kind="mergesort").reset_index(drop=True)
    validas = validas[COLUMNAS_PLATA]
    exigir_plata(validas)

    tabla_reducida = validas[COLUMNAS_REDUCIDAS].copy()

    if not filas_cuarentena.empty:
        filas_cuarentena = filas_cuarentena.sort_values(
            CLAVES, kind="mergesort"
        ).reset_index(drop=True)

    sha_despues = _sha256(entrada)
    diagnostico = _diagnostico_mecanismos(
        df_entrada, fuente_verificada, meta_usado
    )

    nulos_entrada = {
        columna: int(df_entrada[columna].eq("").sum())
        for columna in COLUMNAS_ENTRADA
    }
    nulos_plata = {
        columna: int(validas[columna].isna().sum()) for columna in COLUMNAS_PLATA
    }
    nulos_por_grupo = {
        "personal_disponible": {
            "por_turno": _resumen_nulos(
                df_entrada["personal_disponible"].eq(""),
                df_entrada,
                "turno",
            ),
            "por_unidad": _resumen_nulos(
                df_entrada["personal_disponible"].eq(""),
                df_entrada,
                "unidad_id",
            ),
            "por_insumo": _resumen_nulos(
                df_entrada["personal_disponible"].eq(""),
                df_entrada,
                "insumo_id",
            ),
            "por_desabasto": _resumen_nulos(
                df_entrada["personal_disponible"].eq(""),
                df_entrada,
                "desabasto",
            ),
        },
        "consumo": {
            "por_turno": _resumen_nulos(
                df_entrada["consumo"].eq(""), df_entrada, "turno"
            ),
            "por_unidad": _resumen_nulos(
                df_entrada["consumo"].eq(""), df_entrada, "unidad_id"
            ),
            "por_insumo": _resumen_nulos(
                df_entrada["consumo"].eq(""), df_entrada, "insumo_id"
            ),
            "por_desabasto": _resumen_nulos(
                df_entrada["consumo"].eq(""), df_entrada, "desabasto"
            ),
        },
    }

    datos_reporte: dict[str, Any] = {
        "version": VERSION,
        "archivo_entrada": entrada.as_posix(),
        "fuente": fuente_verificada,
        "es_sintetico": es_sintetico,
        "sha256_entrada": sha_antes,
        "sha256_bronce_antes": sha_antes,
        "sha256_bronce_despues": sha_despues,
        "bronce_intacto": sha_antes == sha_despues,
        "procedencia": procedencia,
        "advertencia_fuente": procedencia["advertencia"],
        "filas_entrada": meta_validacion["n_entrada"],
        "filas_plata": len(validas),
        "filas_reducido": len(tabla_reducida),
        "filas_cuarentena": len(filas_cuarentena),
        "esquema": {
            "validador": (
                "validador explícito propio (alternativa justificada a "
                "Pandera; ver docs/E1/limpieza.md)"
            ),
            "columnas_plata": COLUMNAS_PLATA,
            "errores": [],
        },
        "nulos": {
            "por_columna_entrada": nulos_entrada,
            "por_columna_plata": nulos_plata,
            "por_grupo": nulos_por_grupo,
        },
        "mecanismos": diagnostico,
        "imputacion": {
            **detalle_imputacion,
            "regla": (
                "No se imputan claves ni desabasto; toda imputación deja "
                "bandera binaria y se documenta el método."
            ),
        },
        "atipicos": detalle_atipicos,
        "transformaciones": detalle_transformaciones,
        "reduccion": {
            "columnas": COLUMNAS_REDUCIDAS,
            "n_columnas": len(COLUMNAS_REDUCIDAS),
            "n_columnas_plata": len(COLUMNAS_PLATA),
            "criterio": (
                "Selección explícita de columnas: se conservan claves, "
                "variables originales, procedencia, banderas, tratamiento de "
                "atípicos, transformaciones y jerarquías; se excluye "
                "insumo_nombre por ser texto descriptivo redundante con "
                "insumo_id."
            ),
        },
        "cuarentena": {
            "n": len(filas_cuarentena),
            "motivos": _contar_motivos(filas_cuarentena),
        },
    }

    temporales: list[tuple[Path, Path]] = []
    try:
        temporales.append(
            (
                _preparar_csv_temporal(validas, rutas["plata"], COLUMNAS_PLATA),
                rutas["plata"],
            )
        )
        temporales.append(
            (
                _preparar_csv_temporal(
                    tabla_reducida, rutas["reducido"], COLUMNAS_REDUCIDAS
                ),
                rutas["reducido"],
            )
        )
        temporales.append(
            (
                _preparar_csv_temporal(filas_cuarentena, rutas["cuarentena"]),
                rutas["cuarentena"],
            )
        )
        temporales.append(
            (
                _preparar_json_temporal(datos_reporte, rutas["reporte"]),
                rutas["reporte"],
            )
        )
        _publicar_temporales(temporales, entrada, sha_antes)
    except Exception:
        for temporal, _ in temporales:
            if temporal.exists():
                temporal.unlink()
        raise
    return datos_reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ENTRADA)
    parser.add_argument("--fuente", choices=sorted(FUENTES), default=FUENTE_POR_DEFECTO)
    parser.add_argument("--plata", type=Path, default=None)
    parser.add_argument("--reducido", type=Path, default=None)
    parser.add_argument("--cuarentena", type=Path, default=None)
    parser.add_argument("--reporte", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        datos = ejecutar(
            entrada=args.input,
            fuente=args.fuente,
            plata=args.plata,
            reducido=args.reducido,
            cuarentena=args.cuarentena,
            reporte=args.reporte,
        )
    except ErrorEsquema as exc:
        print(f"FALLA: {exc}")
        return 1

    print(f"Entrada: {datos['archivo_entrada']} ({datos['fuente']})")
    print(f"Plata: {datos['filas_plata']} filas")
    print(f"Reducido: {datos['filas_reducido']} filas")
    print(f"Cuarentena: {datos['filas_cuarentena']} filas")
    print(f"Bronce intacto: {datos['bronce_intacto']} ({datos['sha256_entrada']})")
    if datos["advertencia_fuente"]:
        print(datos["advertencia_fuente"])
    print(
        "Imputados: consumo={n} personal={p}".format(
            n=datos["imputacion"]["consumo"]["n"],
            p=datos["imputacion"]["personal_disponible"]["n"],
        )
    )
    print(
        "Atípicos: pacientes={n} (altos={a}, bajos={b})".format(
            n=datos["atipicos"]["pacientes_atendidos"]["n"],
            a=datos["atipicos"]["pacientes_atendidos"]["n_altos"],
            b=datos["atipicos"]["pacientes_atendidos"]["n_bajos"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
