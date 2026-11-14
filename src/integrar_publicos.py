#!/usr/bin/env python3
"""E1: integración semanal dengue + clima para Colima.

La fuente pública de dengue define la cobertura semanal; el clima se incorpora
por la llave exacta ``(anio, semana)``. La correspondencia territorial es
explícita: ``entidad=Colima`` ↔ ``ciudad=Colima``. No se crean semanas ni se
extrapolan datos de otras entidades o ciudades.

El pipeline separa filas inválidas con motivo, resuelve duplicados por
``extraido_en`` más reciente, marca faltantes antes de imputar y deja el clima
original junto a su versión de análisis. Las salidas son deterministas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

RAIZ_REPO = Path(__file__).resolve().parents[1]

DENGUE = Path("datos_crudos/dengue_estados_semanal.csv")
CLIMA = Path("datos_crudos/clima_ciudades_semanal.csv")
PLATA = Path("datos_plata/publico/colima_semanal.csv")
ORO = Path("datos_oro/indicadores_semanales_colima.csv")
CUARENTENA = Path("cuarentena/publico/registros_invalidos.csv")
REPORTE = Path("cuarentena/publico/_reporte.json")

COLUMNAS_DENGUE = [
    "anio", "semana", "entidad",
    "probables_2025", "probables_2026", "dng_2025", "dng_2026",
    "dcsa_dg_2025", "dcsa_dg_2026", "confirmados_2025", "confirmados_2026",
    "defunciones_2025", "defunciones_2026", "url", "extraido_en",
]
COLUMNAS_CLIMA = [
    "anio", "semana", "ciudad", "lat", "lon",
    "temp_media_c", "precipitacion_mm", "humedad_media_pct",
    "dias_lluvia", "dias_lluvia_intensa", "extraido_en",
]
NUM_DENGUE = COLUMNAS_DENGUE[3:13]
NUM_CLIMA = [
    "lat", "lon", "temp_media_c", "precipitacion_mm",
    "humedad_media_pct", "dias_lluvia", "dias_lluvia_intensa",
]
CLIMA_VARIABLES = ["temp_media_c", "precipitacion_mm", "humedad_media_pct"]
CLIMA_NULABLES = set(CLIMA_VARIABLES)
_RE_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class ErrorEsquema(ValueError):
    """La tabla no cumple el contrato de la capa pública."""


def _leer_csv(ruta: Path, columnas: list[str]) -> pd.DataFrame:
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[])
    if list(df.columns) != columnas:
        faltan = [c for c in columnas if c not in df.columns]
        sobran = [c for c in df.columns if c not in columnas]
        detalle = []
        if faltan:
            detalle.append(f"faltan columnas: {', '.join(faltan)}")
        if sobran:
            detalle.append(f"columnas inesperadas: {', '.join(sobran)}")
        if not detalle:
            detalle.append("el orden de columnas no coincide")
        raise ErrorEsquema(f"Contrato de entrada roto en {ruta}: " + "; ".join(detalle))
    return df


def _validar_generica(
    df: pd.DataFrame,
    columnas: list[str],
    numericas: list[str],
    requeridas_texto: list[str],
    rangos: dict[str, tuple[float, float]],
    nulables: set[str],
    enteras: set[str] | None = None,
    fechas: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valida una tabla completa y separa filas válidas de cuarentena.

    La validación es por fila para los tipos/rangos, pero la unicidad se
    comprueba después sobre la tabla completa (no dentro de una fila).
    """
    enteras = enteras or set()
    fechas = fechas or []
    if list(df.columns) != columnas:
        raise ErrorEsquema(
            "Contrato de tabla roto: se esperaban " + ", ".join(columnas)
        )

    raw = df.copy()
    limpio = df.copy()
    motivos: dict[int, list[str]] = {i: [] for i in range(len(df))}

    for columna in requeridas_texto:
        serie = limpio[columna].astype(str).str.strip()
        limpio[columna] = serie
        for i in limpio.index[serie.eq("")]:
            motivos[i].append(f"falta {columna}")

    for columna in fechas:
        texto_fecha = limpio[columna].astype(str).str.strip()
        formato = texto_fecha.str.match(_RE_ISO)
        marcas = pd.to_datetime(
            texto_fecha, errors="coerce", utc=True, format="ISO8601"
        )
        invalidas = ~formato | marcas.isna()
        for i in limpio.index[invalidas]:
            motivos[i].append(
                f"{columna} inválido: se requiere fecha ISO 8601 con zona"
            )

    for columna in numericas:
        texto = limpio[columna].astype(str).str.strip()
        vacio = texto.eq("")
        valores = pd.to_numeric(texto.replace("", np.nan), errors="coerce")
        no_numerico = valores.isna() & ~vacio
        for i in limpio.index[no_numerico]:
            motivos[i].append(f"{columna} no es numérico")

        no_finito = valores.notna() & ~np.isfinite(valores)
        for i in limpio.index[no_finito]:
            motivos[i].append(f"{columna} no es finito")

        if columna in enteras:
            no_entero = valores.notna() & np.isfinite(valores) & (valores % 1 != 0)
            for i in limpio.index[no_entero]:
                motivos[i].append(f"{columna} no es entero: {valores.loc[i]}")

        if columna in nulables:
            for i in limpio.index[vacio]:
                motivos[i].append(f"falta {columna} (permitido: se marca e imputa)")
        else:
            for i in limpio.index[vacio]:
                motivos[i].append(f"falta {columna}")

        if columna in rangos:
            minimo, maximo = rangos[columna]
            fuera = valores.notna() & np.isfinite(valores) & (
                (valores < minimo) | (valores > maximo)
            )
            for i in limpio.index[fuera]:
                valor = valores.loc[i]
                if valor < 0:
                    motivos[i].append(f"{columna} negativo: {valor}")
                else:
                    motivos[i].append(
                        f"{columna} fuera de rango [{minimo}, {maximo}]: {valor}"
                    )
        limpio[columna] = valores

    # La nulabilidad meteorológica se marca como bandera, no como rechazo.
    for i in limpio.index:
        motivos[i] = [
            m for m in motivos[i]
            if not m.startswith("falta temp_media_c (permitido")
            and not m.startswith("falta precipitacion_mm (permitido")
            and not m.startswith("falta humedad_media_pct (permitido")
        ]

    invalidas = [i for i, razones in motivos.items() if razones]
    validas = limpio.drop(index=invalidas).copy()
    cuarentena = raw.loc[invalidas].copy()
    cuarentena["motivo"] = ["; ".join(motivos[i]) for i in invalidas]
    return validas.reset_index(drop=True), cuarentena.reset_index(drop=True)


def validar_dengue(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _validar_generica(
        df,
        COLUMNAS_DENGUE,
        ["anio", "semana", *NUM_DENGUE],
        ["entidad", "url", "extraido_en"],
        {
            "anio": (2000, 2100),
            "semana": (1, 53),
            **{col: (0, float("inf")) for col in NUM_DENGUE},
        },
        set(),
        {"anio", "semana", *NUM_DENGUE},
        ["extraido_en"],
    )


def validar_clima(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _validar_generica(
        df,
        COLUMNAS_CLIMA,
        ["anio", "semana", *NUM_CLIMA],
        ["ciudad", "extraido_en"],
        {
            "anio": (2000, 2100),
            "semana": (1, 53),
            "lat": (-90, 90),
            "lon": (-180, 180),
            "temp_media_c": (-90, 65),
            "precipitacion_mm": (0, float("inf")),
            "humedad_media_pct": (0, 100),
            "dias_lluvia": (0, 7),
            "dias_lluvia_intensa": (0, 7),
        },
        CLIMA_NULABLES,
        {"anio", "semana", "dias_lluvia", "dias_lluvia_intensa"},
        ["extraido_en"],
    )


def _resolver_duplicados(
    df: pd.DataFrame, claves: list[str], ts: str
) -> tuple[pd.DataFrame, int]:
    """Resuelve conflictos conservando el registro con ``extraido_en`` más reciente."""
    duplicados = int(df.duplicated(claves, keep="first").sum())
    if not duplicados:
        return df.copy(), 0
    ordenado = df.assign(
        _ts=pd.to_datetime(
            df[ts], errors="coerce", utc=True, format="ISO8601"
        )
    )
    if ordenado["_ts"].isna().any():
        raise ErrorEsquema(f"{ts} inválido al resolver duplicados")
    ordenado = ordenado.sort_values(claves + ["_ts"], kind="mergesort")
    ordenado = ordenado.drop_duplicates(claves, keep="last").drop(columns="_ts")
    return ordenado.reset_index(drop=True), duplicados


def _minmax(serie: pd.Series) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce").astype(float)
    minimo, maximo = float(valores.min()), float(valores.max())
    if not np.isfinite(minimo) or not np.isfinite(maximo) or maximo == minimo:
        return pd.Series(0.0, index=serie.index)
    return (valores - minimo) / (maximo - minimo)


def _zscore(serie: pd.Series) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce").astype(float)
    desviacion = float(valores.std(ddof=0))
    if not np.isfinite(desviacion) or desviacion == 0:
        return pd.Series(0.0, index=serie.index)
    return (valores - float(valores.mean())) / desviacion


def _marcar_atipicos(merged: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Marca atípicos con IQR y modified Z; no elimina ni recorta."""
    merged = merged.copy()
    iqr_mask = pd.Series(False, index=merged.index)
    z_mask = pd.Series(False, index=merged.index)

    for columna in CLIMA_VARIABLES:
        serie = merged[f"{columna}_analisis"].astype(float)
        q1, q3 = serie.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr > 0:
            iqr_mask |= (serie < q1 - 1.5 * iqr) | (serie > q3 + 1.5 * iqr)

        mediana = float(serie.median())
        mad = float((serie - mediana).abs().median())
        if mad > 0:
            modified_z = 0.6745 * (serie - mediana) / mad
            z_mask |= modified_z.abs() > 3.5

    merged["posible_atipico"] = (iqr_mask | z_mask).astype(int)
    return merged, {
        "iqr": int(iqr_mask.sum()),
        "modified_z": int(z_mask.sum()),
        "union": int((iqr_mask | z_mask).sum()),
        "tratamiento": (
            "Marcar sin eliminar ni recortar: los extremos climáticos pueden "
            "ser eventos reales. La bandera es una advertencia de calidad."
        ),
    }


def integrar(
    dengue: pd.DataFrame, clima: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Integra dengue y clima de Colima por la llave exacta (anio, semana)."""
    d = dengue.loc[dengue["entidad"].eq("Colima")].copy()
    c = clima.loc[clima["ciudad"].eq("Colima")].copy()
    d, dup_d = _resolver_duplicados(d, ["anio", "semana"], "extraido_en")
    c, dup_c = _resolver_duplicados(c, ["anio", "semana"], "extraido_en")

    if d.duplicated(["anio", "semana"]).any():
        raise ErrorEsquema("quedaron duplicados de dengue tras resolver conflictos")
    if c.duplicated(["anio", "semana"]).any():
        raise ErrorEsquema("quedaron duplicados de clima tras resolver conflictos")

    merged = d.merge(
        c, on=["anio", "semana"], how="left", validate="one_to_one",
        suffixes=("_dengue", "_clima"), indicator="_clima_existe",
    )

    # "Disponible" significa que existe registro climático para la semana,
    # aunque falte una variable concreta como la temperatura.
    merged["clima_disponible"] = merged["_clima_existe"].eq("both").astype(int)
    merged = merged.drop(columns="_clima_existe")
    faltantes = {
        columna: int(merged[columna].isna().sum())
        for columna in [*NUM_DENGUE, *CLIMA_VARIABLES]
    }

    # Las banderas se crean ANTES de imputar; el original se conserva.
    for columna in CLIMA_VARIABLES:
        merged[f"{columna}_imputado"] = merged[columna].isna().astype(int)
        mediana = merged[columna].median()
        if pd.isna(mediana):
            mediana = 0.0
        merged[f"{columna}_analisis"] = merged[columna].fillna(mediana).astype(float)
        merged[f"{columna}_minmax"] = _minmax(merged[f"{columna}_analisis"])
        merged[f"{columna}_zscore"] = _zscore(merged[f"{columna}_analisis"])

    merged["probables_2026_minmax"] = _minmax(merged["probables_2026"])
    merged["probables_2026_zscore"] = _zscore(merged["probables_2026"])

    merged, atipicos = _marcar_atipicos(merged)
    merged["riesgo_dengue"] = pd.cut(
        merged["probables_2026"],
        bins=[-1, 0, 10, 50, np.inf],
        labels=["sin_reportes", "bajo", "medio", "alto"],
    ).astype("string")
    merged = merged.sort_values(["anio", "semana"], kind="mergesort").reset_index(drop=True)

    interseccion = len(
        set(zip(d["anio"], d["semana"])) & set(zip(c["anio"], c["semana"]))
    )
    reporte: dict[str, Any] = {
        "fuente": "publica",
        "integracion": {
            "llave": ["anio", "semana"],
            "mapeo_territorial": {"entidad": "Colima", "ciudad": "Colima"},
            "cobertura_dengue": int(len(d)),
            "cobertura_clima": int(len(c)),
            "interseccion_semanas": int(interseccion),
            "semanas_sin_clima": int(merged["clima_disponible"].eq(0).sum()),
            "duplicados_dengue_resueltos": int(dup_d),
            "duplicados_clima_resueltos": int(dup_c),
            "regla_duplicados": (
                "Se conserva el registro con extraido_en más reciente; el "
                "conteo de conflictos se reporta."
            ),
        },
        "faltantes": faltantes,
        "faltantes_tratamiento": (
            "Se marca *_imputado antes de rellenar; el valor original queda "
            "en la columna sin sufijo y el valor de análisis en *_analisis. "
            "No se crean semanas ausentes."
        ),
        "atipicos": atipicos,
        "transformaciones": {
            "minmax": [f"{c}_minmax" for c in CLIMA_VARIABLES]
            + ["probables_2026_minmax"],
            "zscore": [f"{c}_zscore" for c in CLIMA_VARIABLES]
            + ["probables_2026_zscore"],
            "advertencia": (
                "En E2 los parámetros de Min-Max y Z-Score deben ajustarse "
                "solo con train."
            ),
        },
        "plata_filas": int(len(merged)),
    }
    return merged, reporte


def construir_oro(plata: pd.DataFrame) -> pd.DataFrame:
    oro = (
        plata.groupby(["anio", "semana"], as_index=False)
        .agg(
            entidad=("entidad", "first"),
            probables_2026=("probables_2026", "sum"),
            confirmados_2026=("confirmados_2026", "sum"),
            defunciones_2026=("defunciones_2026", "sum"),
            temp_media_c=("temp_media_c_analisis", "mean"),
            precipitacion_mm=("precipitacion_mm_analisis", "mean"),
            humedad_media_pct=("humedad_media_pct_analisis", "mean"),
            clima_disponible=("clima_disponible", "max"),
            posible_atipico=("posible_atipico", "max"),
            riesgo_dengue=("riesgo_dengue", "first"),
        )
        .sort_values(["anio", "semana"], kind="mergesort")
        .reset_index(drop=True)
    )
    return oro


def _resolver_rutas(
    plata: Path | None,
    oro: Path | None,
    cuarentena: Path | None,
    reporte: Path | None,
) -> dict[str, Path]:
    raiz = RAIZ_REPO.resolve()
    crudos = (raiz / "datos_crudos").resolve()
    permitidas = {
        "plata": (raiz / "datos_plata" / "publico").resolve(),
        "oro": (raiz / "datos_oro").resolve(),
        "cuarentena": (raiz / "cuarentena" / "publico").resolve(),
        "reporte": (raiz / "cuarentena" / "publico").resolve(),
    }
    valores = {
        "plata": plata,
        "oro": oro,
        "cuarentena": cuarentena,
        "reporte": reporte,
    }
    salidas: dict[str, Path] = {}
    for nombre, valor in valores.items():
        salida = Path(valor).resolve() if valor is not None else (
            permitidas[nombre] / (
                "colima_semanal.csv" if nombre == "plata"
                else "indicadores_semanales_colima.csv" if nombre == "oro"
                else "registros_invalidos.csv" if nombre == "cuarentena"
                else "_reporte.json"
            )
        ).resolve()
        if salida == crudos or crudos in salida.parents:
            raise ErrorEsquema(f"la salida {nombre} cae en datos_crudos/")
        dentro_repo = salida == raiz or raiz in salida.parents
        if dentro_repo:
            base = permitidas[nombre]
            if salida != base and base not in salida.parents:
                raise ErrorEsquema(
                    f"la salida {nombre} debe estar bajo {base} o fuera del repo"
                )
        salidas[nombre] = salida
    if len(set(salidas.values())) != len(salidas):
        raise ErrorEsquema("dos salidas comparten la misma ruta")
    return salidas


def _temporal_en_destino(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, nombre = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    os.close(descriptor)
    return Path(nombre)


def _preparar_csv(df: pd.DataFrame, ruta: Path) -> Path:
    temporal = _temporal_en_destino(ruta)
    df.to_csv(
        temporal, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.6f",
    )
    return temporal


def _preparar_json(datos: dict[str, Any], ruta: Path) -> Path:
    temporal = _temporal_en_destino(ruta)
    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return temporal


def _publicar_salidas(
    plata_df: pd.DataFrame,
    oro_df: pd.DataFrame,
    invalidas: pd.DataFrame,
    reporte_datos: dict[str, Any],
    rutas: dict[str, Path],
) -> None:
    """Publica las cuatro salidas con respaldo y rollback."""
    temporales = [
        (_preparar_csv(plata_df, rutas["plata"]), rutas["plata"]),
        (_preparar_csv(oro_df, rutas["oro"]), rutas["oro"]),
        (_preparar_csv(invalidas, rutas["cuarentena"]), rutas["cuarentena"]),
        (_preparar_json(reporte_datos, rutas["reporte"]), rutas["reporte"]),
    ]
    respaldos: list[tuple[Path, Path | None]] = []
    publicados: list[Path] = []
    try:
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
    dengue: Path = DENGUE,
    clima: Path = CLIMA,
    plata: Path | None = None,
    oro: Path | None = None,
    cuarentena: Path | None = None,
    reporte: Path | None = None,
) -> dict[str, Any]:
    """Ejecuta la integración pública y devuelve el reporte."""
    dengue = Path(dengue)
    clima = Path(clima)
    rutas = _resolver_rutas(plata, oro, cuarentena, reporte)

    d_raw = _leer_csv(dengue, COLUMNAS_DENGUE)
    c_raw = _leer_csv(clima, COLUMNAS_CLIMA)
    d_valid, d_inv = validar_dengue(d_raw)
    c_valid, c_inv = validar_clima(c_raw)
    if d_valid.empty:
        raise ErrorEsquema("no quedaron filas válidas de dengue")

    plata_df, reporte_datos = integrar(d_valid, c_valid)
    oro_df = construir_oro(plata_df)

    invalidas = pd.concat([d_inv, c_inv], ignore_index=True, sort=False)
    reporte_datos.update(
        {
            "filas_dengue_entrada": int(len(d_raw)),
            "filas_clima_entrada": int(len(c_raw)),
            "filas_dengue_validas": int(len(d_valid)),
            "filas_clima_validas": int(len(c_valid)),
            "filas_cuarentena": int(len(invalidas)),
            "filas_plata": int(len(plata_df)),
            "filas_oro": int(len(oro_df)),
            "salidas": {k: v.name for k, v in rutas.items()},
        }
    )

    _publicar_salidas(plata_df, oro_df, invalidas, reporte_datos, rutas)
    return reporte_datos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dengue", type=Path, default=DENGUE)
    parser.add_argument("--clima", type=Path, default=CLIMA)
    parser.add_argument("--plata", type=Path, default=None)
    parser.add_argument("--oro", type=Path, default=None)
    parser.add_argument("--cuarentena", type=Path, default=None)
    parser.add_argument("--reporte", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        datos = ejecutar(
            dengue=args.dengue,
            clima=args.clima,
            plata=args.plata,
            oro=args.oro,
            cuarentena=args.cuarentena,
            reporte=args.reporte,
        )
    except ErrorEsquema as exc:
        print(f"FALLA: {exc}")
        return 1

    print(f"Dengue: {datos['filas_dengue_validas']} filas válidas")
    print(f"Clima Colima: {datos['filas_clima_validas']} filas válidas")
    print(f"Plata: {datos['filas_plata']} filas -> {datos['salidas']['plata']}")
    print(f"Oro: {datos['filas_oro']} filas -> {datos['salidas']['oro']}")
    print(f"Cuarentena: {datos['filas_cuarentena']} filas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
