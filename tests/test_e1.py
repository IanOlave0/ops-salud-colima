import pandas as pd
import pandera.pandas as pa

from src.e1.pipeline import make_synthetic_inventory, schemas, validate_rows


def test_quality_gate_accepts_valid_public_rows():
    schema, _, _ = schemas()
    row = pd.DataFrame([{"anio": 2026, "semana": 1, "entidad": "Colima", "probables_2025": 0,
                         "probables_2026": 3, "dng_2025": 0, "dng_2026": 0, "dcsa_dg_2025": 0,
                         "dcsa_dg_2026": 0, "confirmados_2025": 1, "confirmados_2026": 2,
                         "defunciones_2025": 0, "defunciones_2026": 0}])
    valid, rejected = validate_rows(row, schema, "fixture.csv")
    assert len(valid) == 1
    assert rejected.empty


def test_invalid_inventory_is_quarantined_with_reason():
    frame = make_synthetic_inventory().head(1)
    frame.loc[frame.index[0], "turno"] = "X"
    schema = pa.DataFrameSchema({"turno": pa.Column(str, pa.Check.isin(["M", "V", "N"]))}, strict=False)
    valid, rejected = validate_rows(frame, schema, "sintetico.csv")
    assert valid.empty
    assert len(rejected) >= 1
    assert rejected.iloc[0]["motivo_rechazo"]
    assert rejected.iloc[0]["regla_incumplida"]
    assert rejected.iloc[0]["archivo_origen"] == "sintetico.csv"


def test_synthetic_inventory_obeys_balance_and_is_labeled_by_pipeline():
    frame = make_synthetic_inventory()
    assert (frame.existencia_final == frame.existencia_inicial + frame.entradas - frame.consumo).all()
    assert frame.unidad_id.eq("U01").all()
