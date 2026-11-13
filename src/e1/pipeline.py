#!/usr/bin/env python3
"""E1: integración reproducible de dengue y clima semanal para Colima."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pandera.pandas as pa
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler, StandardScaler

ROOT = Path(__file__).resolve().parents[2]


def schemas():
    dengue = pa.DataFrameSchema({
        "anio": pa.Column(int, pa.Check.in_range(2000, 2100)),
        "semana": pa.Column(int, pa.Check.in_range(1, 53)),
        "entidad": pa.Column(str, pa.Check.str_length(min_value=1)),
        **{c: pa.Column(float, nullable=False, checks=pa.Check.ge(0), coerce=True)
           for c in ("probables_2025", "probables_2026", "dng_2025", "dng_2026", "dcsa_dg_2025", "dcsa_dg_2026", "confirmados_2025", "confirmados_2026", "defunciones_2025", "defunciones_2026")},
    }, strict=False, coerce=True, unique=["anio", "semana", "entidad"])
    clima = pa.DataFrameSchema({
        "anio": pa.Column(int, pa.Check.in_range(2000, 2100)),
        "semana": pa.Column(int, pa.Check.in_range(1, 53)),
        "ciudad": pa.Column(str, pa.Check.str_length(min_value=1)),
        "lat": pa.Column(float, pa.Check.in_range(-90, 90), coerce=True),
        "lon": pa.Column(float, pa.Check.in_range(-180, 180), coerce=True),
        "temp_media_c": pa.Column(float, pa.Check.in_range(-90, 65), coerce=True),
        "precipitacion_mm": pa.Column(float, pa.Check.ge(0), coerce=True),
        "humedad_media_pct": pa.Column(float, pa.Check.in_range(0, 100), coerce=True),
        "dias_lluvia": pa.Column(int, pa.Check.in_range(0, 7), coerce=True),
        "dias_lluvia_intensa": pa.Column(int, pa.Check.in_range(0, 7), coerce=True),
    }, strict=False, coerce=True, unique=["anio", "semana", "ciudad"])
    integrated = pa.DataFrameSchema({
        "anio": pa.Column(int, pa.Check.in_range(2000, 2100)),
        "semana": pa.Column(int, pa.Check.in_range(1, 53)),
        "entidad": pa.Column(str),
        "ciudad": pa.Column(str),
        **{c: pa.Column(float, nullable=True, coerce=True) for c in ["probables_2025", "probables_2026", "confirmados_2025", "confirmados_2026", "defunciones_2025", "defunciones_2026", "temp_media_c", "precipitacion_mm", "humedad_media_pct"]},
    }, strict=False, coerce=True, unique=["anio", "semana"])
    return dengue, clima, integrated


def validate_rows(frame: pd.DataFrame, schema: pa.DataFrameSchema, source: str):
    valid, rejected = [], []
    # Row granularity preserves every rejected source record and its exact reason.
    for idx, row in frame.iterrows():
        one = row.to_frame().T
        try:
            schema.validate(one, lazy=True)
            valid.append(row)
        except pa.errors.SchemaErrors as exc:
            failures = exc.failure_cases
            for _, failure in failures.iterrows():
                rejected.append({**row.to_dict(), "motivo_rechazo": str(failure.get("failure_case", "validación")),
                                 "regla_incumplida": str(failure.get("check", failure.get("column", "esquema"))),
                                 "timestamp": datetime.now(timezone.utc).isoformat(), "archivo_origen": source,
                                 "indice_origen": int(idx)})
    return pd.DataFrame(valid, columns=frame.columns), pd.DataFrame(rejected)


def run(root: Path = ROOT):
    plata = root / "data/plata"
    oro = root / "data/oro"
    reportes = plata / "reportes"
    quarantine_dir = root / "data/cuarentena"
    for path in (plata, oro, reportes, quarantine_dir):
        path.mkdir(parents=True, exist_ok=True)

    d_schema, c_schema, final_schema = schemas()
    dengue_raw = pd.read_csv(root / "datos_crudos/dengue_estados_semanal.csv")
    clima_raw = pd.read_csv(root / "datos_crudos/clima_ciudades_semanal.csv")
    dengue, dq = validate_rows(dengue_raw, d_schema, "datos_crudos/dengue_estados_semanal.csv")
    clima, cq = validate_rows(clima_raw, c_schema, "datos_crudos/clima_ciudades_semanal.csv")
    q = pd.concat([dq, cq], ignore_index=True, sort=False)

    # Homologación explícita: misma llave semanal, ciudad Colima ↔ entidad Colima.
    d = dengue[dengue.entidad.eq("Colima")].copy()
    c = clima[clima.ciudad.eq("Colima")].copy()
    d = d.rename(columns={"extraido_en": "extraido_en_dengue", "url": "url_dengue"})
    c = c.rename(columns={"extraido_en": "extraido_en_clima"})
    conflicts = {
        "llave": ["anio", "semana"], "entidad_en_dengue": "Colima", "ciudad_en_clima": "Colima",
        "duplicados_dengue": int(d.duplicated(["anio", "semana"]).sum()),
        "duplicados_clima": int(c.duplicated(["anio", "semana"]).sum()),
        "regla": "Se conserva el registro de origen único; si se repite llave, el registro con extraido_en más reciente prevalece.",
        "interseccion_semanas": int(len(set(zip(d.anio, d.semana)) & set(zip(c.anio, c.semana)))),
        "cobertura_dengue": int(len(d)), "cobertura_clima_colima": int(len(c)),
    }
    for frame, ts in ((d, "extraido_en_dengue"), (c, "extraido_en_clima")):
        frame.sort_values(ts, inplace=True)
        frame.drop_duplicates(["anio", "semana"], keep="last", inplace=True)
    merged = d.merge(c, on=["anio", "semana"], how="left", validate="one_to_one", suffixes=("_dengue", "_clima"))
    conflicts["semanas_sin_clima"] = int(merged.temp_media_c.isna().sum())
    conflicts["semanas_sin_dengue"] = int(len(set(zip(c.anio, c.semana)) - set(zip(d.anio, d.semana))))
    conflicts["resumen"] = "Dengue define la cobertura de Plata integrada; clima se incorpora por llave exacta, sin extrapolar semanas."

    numeric = ["probables_2025", "probables_2026", "confirmados_2025", "confirmados_2026", "defunciones_2025", "defunciones_2026", "temp_media_c", "precipitacion_mm", "humedad_media_pct"]
    missing = {col: int(merged[col].isna().sum()) for col in numeric}
    # Missingness report: with this observational snapshot, mechanism is not identifiable;
    # no Little test is defensible because the population is not an iid multivariate sample.
    missing_report = {"n_filas": len(merged), "faltantes_por_variable": missing,
                      "mecanismo": "No identificable con datos observacionales agregados y fuente con cobertura desigual (posible MAR por disponibilidad de semana).",
                      "little_test": "No aplicado: los indicadores/clases no son una muestra iid apropiada; se informa patrón por variable.",
                      "tratamiento": "Mediana meteorológica entre semanas con observación para columnas numéricas; guardar bandera antes de imputar. No imputar ni crear semanas ausentes.",
                      "decision_MNAR": "No hay evidencia para afirmar MNAR. Si la falta depende del valor meteorológico no observado, mediana puede sesgar; conservar banderas y no imputar periodos completos evita ocultar esa limitación. Requiere análisis de sensibilidad con más observaciones."}
    merged["clima_disponible"] = merged.temp_media_c.notna()
    # Three comparable anomaly screens for climate features, only among observed weeks.
    outlier_report = {}
    features = [col for col in ("temp_media_c", "precipitacion_mm", "humedad_media_pct") if merged[col].notna().sum() >= 8]
    x = merged[features].copy()
    med = x.median()
    mad = (x - med).abs().median().replace(0, np.nan)
    modified_z = 0.6745 * (x - med) / mad
    iqr_mask = pd.Series(False, index=x.index)
    robust_mask = pd.Series(False, index=x.index)
    for col in features:
        q1, q3 = x[col].quantile([.25, .75]); spread = q3 - q1
        iqr_mask |= (x[col] < q1 - 1.5 * spread) | (x[col] > q3 + 1.5 * spread)
        robust_mask |= modified_z[col].abs().gt(3.5).fillna(False)
    if len(x.dropna()) >= 10:
        forest = IsolationForest(contamination="auto", random_state=42)
        forest_mask = pd.Series(forest.fit_predict(x.fillna(x.median())) == -1, index=x.index)
    else:
        forest_mask = pd.Series(False, index=x.index)
    for name, mask in (("IQR", iqr_mask), ("modified_z_3_5", robust_mask), ("isolation_forest", forest_mask)):
        outlier_report[name] = int(mask.sum())
    merged["posible_atipico"] = iqr_mask | robust_mask
    outlier_report["criterio_final"] = "Marcar (sin eliminar) la unión IQR y modified Z > 3.5; Isolation Forest se compara como diagnóstico. Series climáticas cortas y extremos reales no se recortan."

    # Honest imputation rule: only missing numeric attributes use median; seasonal periods are never synthesized.
    for col in numeric:
        if merged[col].isna().any() and col.startswith(("probables", "confirmados", "defunciones")):
            merged[col] = merged[col].fillna(0)  # absent disease counts mean no reported cases in the published extract
        elif merged[col].isna().any() and col in features:
            merged[col] = merged[col].fillna(merged[col].median())
    for col in ("temp_media_c", "precipitacion_mm", "humedad_media_pct"):
        merged[f"{col}_imputado"] = merged[col].isna()
    # Transform data are stored separately as fitted artifacts and columns.
    continuous = [col for col in ("temp_media_c", "precipitacion_mm", "humedad_media_pct") if col in merged]
    if len(merged):
        for method, scaler in (("minmax", MinMaxScaler()), ("zscore", StandardScaler())):
            transformed = scaler.fit_transform(merged[continuous])
            for i, col in enumerate(continuous): merged[f"{col}_{method}"] = transformed[:, i]
            (reportes / f"scaler_{method}.json").write_text(json.dumps({"variables": continuous, "min": getattr(scaler, "data_min_", None).tolist() if method == "minmax" else None,
                "max": getattr(scaler, "data_max_", None).tolist() if method == "minmax" else None,
                "mean": getattr(scaler, "mean_", None).tolist() if method == "zscore" else None,
                "scale": getattr(scaler, "scale_", None).tolist()}, ensure_ascii=False, indent=2), encoding="utf-8")
    merged["riesgo_dengue"] = pd.cut(merged.get("probables_2026", pd.Series(index=merged.index, dtype=float)),
        bins=[-1, 0, 10, 50, np.inf], labels=["sin_reportes", "bajo", "medio", "alto"])
    merged["riesgo_dengue"] = merged.riesgo_dengue.astype("string")
    # Feature reduction and aggregation: keep Colima only; weekly total and seasonal climatology in Gold.
    gold = merged.groupby(["anio", "semana"], as_index=False).agg(
        entidad=("entidad", "first"), probables_2026=("probables_2026", "sum"), confirmados_2026=("confirmados_2026", "sum"),
        defunciones_2026=("defunciones_2026", "sum"), temp_media_c=("temp_media_c", "mean"),
        precipitacion_mm=("precipitacion_mm", "mean"), humedad_media_pct=("humedad_media_pct", "mean"),
        clima_disponible=("clima_disponible", "max"), riesgo_dengue=("riesgo_dengue", "first"))

    # Output gate runs before Plata write; invalid final rows are routed to quarantine.
    final_valid, fq = validate_rows(merged, final_schema, "integracion:dengue+clima")
    q = pd.concat([q, fq], ignore_index=True, sort=False)

    # The E0 internal inventory is not authorized/available. This clearly labeled fixture
    # exercises its documented contract so the E1 end-to-end flow is runnable without real PHI.
    fixture = make_synthetic_inventory()
    inventory_schema = pa.DataFrameSchema({
        "unidad_id": pa.Column(str, pa.Check.str_matches(r"^U\d{2}$")),
        "fecha": pa.Column(str, pa.Check.str_matches(r"^2026-")),
        "turno": pa.Column(str, pa.Check.isin(["M", "V", "N"])),
        "insumo_id": pa.Column(str), "insumo_nombre": pa.Column(str),
        "familia": pa.Column(str, pa.Check.isin(["medicamento", "material_curacion"])),
        **{c: pa.Column(int, pa.Check.ge(0), coerce=True) for c in ("existencia_inicial", "entradas", "consumo", "existencia_final", "desabasto", "pacientes_atendidos", "personal_disponible")},
    }, strict=True, coerce=True, unique=["unidad_id", "fecha", "turno", "insumo_id"])
    inv_valid, inv_q = validate_rows(fixture, inventory_schema, "datos_sinteticos_para_pruebas/inventario_sintetico.csv")
    # Cross-field consistency is a separate strict gate.
    bad_balance = inv_valid.existencia_final.ne(inv_valid.existencia_inicial + inv_valid.entradas - inv_valid.consumo)
    if bad_balance.any():
        for idx in inv_valid.index[bad_balance]:
            rec = inv_valid.loc[idx].to_dict()
            inv_q = pd.concat([inv_q, pd.DataFrame([{**rec, "motivo_rechazo": "existencia_final no reconcilia", "regla_incumplida": "balance_inventario",
                "timestamp": datetime.now(timezone.utc).isoformat(), "archivo_origen": "datos_sinteticos_para_pruebas/inventario_sintetico.csv", "indice_origen": int(idx)}])], ignore_index=True)
        inv_valid = inv_valid.loc[~bad_balance]
    q = pd.concat([q, inv_q], ignore_index=True, sort=False)
    inventory_gold = inv_valid.groupby(["fecha", "insumo_id", "insumo_nombre", "familia"], as_index=False).agg(
        consumo_total=("consumo", "sum"), pacientes_atendidos=("pacientes_atendidos", "sum"),
        desabastos=("desabasto", "sum"), existencia_media=("existencia_final", "mean"))
    inventory_gold["tipo_dato"] = "sintetico_para_pruebas"
    inventory_plata = inv_valid.copy()
    inventory_plata["tipo_dato"] = "sintetico_para_pruebas"
    if len(q): q.to_csv(quarantine_dir / "e1_registros_invalidos.csv", index=False)
    else: pd.DataFrame(columns=["motivo_rechazo", "regla_incumplida", "timestamp", "archivo_origen"]).to_csv(quarantine_dir / "e1_registros_invalidos.csv", index=False)
    final_valid.to_parquet(plata / "colima_semanal_limpio.parquet", index=False)
    gold.to_parquet(oro / "indicadores_semanales_colima.parquet", index=False)
    inventory_plata.to_parquet(plata / "inventario_sintetico_para_pruebas.parquet", index=False)
    inventory_gold.to_parquet(oro / "inventario_sintetico_para_pruebas.parquet", index=False)
    merged.to_csv(plata / "colima_semanal_limpio.csv", index=False)
    (reportes / "conflictos_resueltos.json").write_text(json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8")
    (reportes / "diagnostico_faltantes.json").write_text(json.dumps(missing_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (reportes / "atipicos.json").write_text(json.dumps(outlier_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"fuentes": {"dengue": len(dengue_raw), "clima": len(clima_raw)}, "integradas": len(merged),
               "validos_plata": len(final_valid) + len(inventory_plata), "validos_plata_publicos": len(final_valid), "validos_plata_sinteticos": len(inventory_plata), "cuarentena": len(q),
               "motivos_cuarentena": q.get("regla_incumplida", pd.Series(dtype=str)).value_counts().to_dict(),
               "salidas": [p.relative_to(root).as_posix() for p in (plata / "colima_semanal_limpio.parquet", oro / "indicadores_semanales_colima.parquet", quarantine_dir / "e1_registros_invalidos.csv")]}
    (reportes / "resumen_validacion.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def make_synthetic_inventory() -> pd.DataFrame:
    """Deterministic synthetic fixture, never represented as observed clinic data."""
    records = []
    for day in pd.date_range("2026-01-05", periods=14, freq="D"):
        for shift, shift_delta in zip(("M", "V", "N"), (0, 2, 4)):
            for item, name, family, start in (("I01", "paracetamol", "medicamento", 40), ("I02", "gasas", "material_curacion", 55)):
                use = 3 + (day.day + shift_delta) % 6
                incoming = (day.day + shift_delta) % 3
                initial = start + day.day % 5
                records.append({"unidad_id": "U01", "fecha": day.strftime("%Y-%m-%d"), "turno": shift,
                    "insumo_id": item, "insumo_nombre": name, "familia": family,
                    "existencia_inicial": initial, "entradas": incoming, "consumo": use,
                    "existencia_final": initial + incoming - use, "desabasto": int(initial + incoming < use),
                    "pacientes_atendidos": 18 + day.day + shift_delta, "personal_disponible": 4 if shift != "N" else 3})
    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.root)


if __name__ == "__main__": main()
