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
