# ops-salud-colima

**Observatorio de presión operativa en salud de primer nivel — Colima**

Repositorio del proyecto integrador. Entrega **E0**.

---

## What this is / Qué es

A reproducible observatory that anticipates **medical supply stockout risk** in primary-care
clinics in Colima, Mexico. The target variable is the probability that a critical item runs out
during the next shift, modelled from inventory, consumption, patient arrivals, staffing and
weather.

Un observatorio reproducible que anticipa el **riesgo de desabasto de insumos médicos** en
clínicas de primer nivel de Colima. La variable objetivo es la probabilidad de que un insumo
crítico se agote en el siguiente turno, a partir de inventario, consumo, afluencia de pacientes,
personal disponible y clima.

**Research question:** Can stockout risk be anticipated one shift ahead using operational records
and exogenous weather signals?

## Data layers / Capas

| Layer | Content | Status |
|---|---|---|
| Bronce | Raw weekly epidemiological surveillance (DGE) and weekly climate (Open-Meteo) | ✅ 42 and 97 periods |
| Bronce (private) | Shift-level inventory, consumption, patients, staffing | ⏳ pending authorization |
| Plata | Clean, typed, validated tables | E1 |
| Oro | Features and model-ready dataset | E1–E2 |

## Repo layout

```
docs/E0/            Entrega E0: propuesta, ficha técnica, esquema de datos
src/                Extractores y validador
datos_crudos/       Capa Bronce (CSV con url y timestamp de origen)
calidad/            Registros PSP: tiempo y defectos por integrante
.github/workflows/  Captura automática diaria
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y poppler-utils

python src/extract_dengue.py
python src/extract_clima.py
python src/validar.py
```

## Synthetic inventory (Plan B de E1)

While the health unit authorizes the real shift-level records, E1 uses a **deterministic
synthetic dataset** with the same schema (`docs/E0/esquema-inventario.md`):

```bash
python src/generar_sintetico.py --seed 42
python -m unittest discover -s tests -v
```

Output: `datos_crudos/inventario_turno_sintetico.csv` (3 600 rows, 2 units, 120 days) and
`datos_crudos/_reporte_sintetico.json` with seed, missingness counters and SHA-256. Every row
carries `es_sintetico=1`. Missingness is injected with three mechanisms (MCAR, MAR by night
shift, MNAR by high consumption) plus capture outliers, so the E1 cleaning stage has documented
defects to diagnose.

### E1 cleaning pipeline

```bash
python src/preprocesar_inventario.py --input datos_crudos/inventario_turno_sintetico.csv
```

The pipeline verifies provenance (uniform `es_sintetico` flag plus a matching SHA-256 for
synthetic sources), validates the Plata contract, quarantines invalid rows with a reason, and
writes source-specific outputs under `datos_plata/<fuente>/` and `cuarentena/<fuente>/`.
Plata and quarantine outputs are **never versioned**: they can be regenerated and may contain
real operational counts. In addition to the public dengue/climate series, only the schema, the
synthetic generator, its provenance report (`datos_crudos/_reporte_sintetico.json`), the synthetic
Bronze CSV marked with `es_sintetico=1`, the tests and the E1 documentation are published. Real
inputs and all Plata/quarantine outputs stay out of Git. See `docs/E1/limpieza.md` for methods and
limitations.

### E1 public integration

```bash
python src/integrar_publicos.py
```

Dengue and climate are joined by an exact `(anio, semana)` key and filtered to
`entidad=Colima` ↔ `ciudad=Colima`. The pipeline validates the full table, resolves duplicate
keys with the most recent `extraido_en`, routes invalid rows to quarantine, and writes only
valid rows to `datos_plata/publico/colima_semanal.csv` and
`datos_oro/indicadores_semanales_colima.csv`. Missing climate values are flagged before
imputation; outliers are marked, not removed. See `docs/E1/integracion.md`, `docs/E1/ENTREGA.md`
and `docs/relatoria-E1.md`.

### E1 prototype history

The original E1 integration prototype by Carlos Ramirez is preserved in the
[`feature/e1`](https://github.com/IanOlave0/ops-salud-colima/tree/feature/e1) branch
(commit `6bd4b2f`). Its documentation and integration ideas were reviewed and are credited in
`docs/E1/ENTREGA.md`; the current hybrid keeps the working parts and corrects the validation and
publication issues. The branch is kept as evidence of that work.

## Automation

`.github/workflows/bronce.yml` runs daily at 13:00 UTC (07:00 America/Mexico_City), validates
that both series have at least 36 periods, and commits new data.

## Data ethics

- Only aggregated, non-identifiable public data is stored in this repository.
- Internal clinic records are used **only** with written authorization and after removing
  identifiers (`docs/E0/esquema-inventario.md`).
- Sources are documented with `robots.txt` and terms-of-use review in
  `docs/E0/propuesta.md` §4.4.

## Attribution

- Epidemiology: Dirección General de Epidemiología, Secretaría de Salud (México).
- Weather: [Open-Meteo](https://open-meteo.com/) — CC-BY 4.0, non-commercial use.

## License

MIT — see `LICENSE`.

## Entrega E0

Ver `docs/E0/ENTREGA.md`.
