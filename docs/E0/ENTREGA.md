# Ficha de entrega técnica — E0

**Proyecto:** Observatorio de presión operativa en salud de primer nivel — Colima
**Repositorio:** <https://github.com/IanOlave0/ops-salud-colima>
**Tag:** `e0`
**Fecha de entrega:** 9 de noviembre de 2026
**Responsable:** Ian Olave

---

## 1. Entregables

| # | Entregable | Ruta | Estado |
|---|---|---|---|
| 1 | Propuesta del observatorio | `docs/E0/propuesta.md` | ✅ |
| 2 | Esquema de la fuente primaria (inventario) | `docs/E0/esquema-inventario.md` | ✅ |
| 3 | Extractor ético de dengue (DGE) | `src/extract_dengue.py` | ✅ |
| 4 | Extractor ético de clima (Open-Meteo) | `src/extract_clima.py` | ✅ |
| 5 | Validador de cobertura mínima | `src/validar.py` | ✅ |
| 6 | Automatización diaria | `.github/workflows/bronce.yml` | ✅ |
| 7 | Serie histórica Bronce | `datos_crudos/*.csv` | ✅ |
| 8 | Registros PSP | `calidad/tiempo-ian.csv`, `calidad/defectos-ian.csv` | ✅ |
| 9 | Entrevista de campo formal (15 min) | `docs/E0/propuesta.md` §2.1 | ⏳ pendiente |

---

## 2. Evidencia de la capa Bronce

| Serie | Archivo | Periodos | Filas | Fuente |
|---|---|---:|---:|---|
| Dengue por entidad | `datos_crudos/dengue_estados_semanal.csv` | **42** | 1 344 | DGE / Secretaría de Salud |
| Clima por ciudad | `datos_crudos/clima_ciudades_semanal.csv` | **97** | 485 | Open-Meteo |

Requisito E0: **≥ 36 periodos**. Se cumple en ambas series.

Reporte de extracción: `datos_crudos/_reporte_dengue.json`
(semanas publicadas: 43 · semanas con datos: 42 · fallos: 1).

### Ejecución local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y poppler-utils   # pdftotext

python src/extract_dengue.py            # incremental
python src/extract_clima.py
python src/validar.py                   # falla si < 36 periodos
```

### Ejecución automática

- Workflow: `.github/workflows/bronce.yml`
- Frecuencia: diaria, 13:00 UTC (07:00 America/Mexico_City)
- Manual: pestaña *Actions* → *Captura Bronce* → *Run workflow*
- Si hay cambios, el bot hace commit en `datos_crudos/`.

---

## 3. Sistema de calidad (PSP)

| Archivo | Contenido |
|---|---|
| `calidad/tiempo-ian.csv` | Fecha, actividad, minutos, nota |
| `calidad/defectos-ian.csv` | Fecha, fase, tipo, descripción, causa, severidad, minutos de corrección |

Objetivos definidos en `docs/E0/propuesta.md` §6:

1. **OC-1 Cobertura:** ≥ 95 % de semanas publicadas → actual 97.7 %.
2. **OC-2 Exactitud:** 100 % en auditoría manual de 3 semanas × 5 entidades.
3. **OC-3 Disponibilidad:** ≥ 95 % de corridas exitosas en 30 días, latencia ≤ 24 h.

---

## 4. Checklist de entrega

- [x] Repositorio creado en GitHub
- [x] Propuesta (`docs/E0/propuesta.md`)
- [x] Extractor ético + workflow de Actions
- [x] Serie histórica ≥ 36 periodos en `datos_crudos/`
- [x] Registros PSP de tiempo y defectos
- [x] 3 objetivos de calidad medibles
- [x] Ficha técnica (`docs/E0/ENTREGA.md`)
- [ ] Entrevista formal de 15 min documentada
- [ ] Agregar a los 3 profesores como colaboradores
- [ ] Registrar el enlace en el formulario oficial
- [ ] Crear el tag `e0`

### Comandos pendientes

```bash
# Colaboradores (repetir por profesor)
gh api -X PUT repos/IanOlave0/ops-salud-colima/collaborators/<usuario> -f permission=push

# Tag de entrega
git tag -a e0 -m "Entrega E0: propuesta, captura Bronce y sistema de calidad"
git push origin e0
```

---

## 5. Nota de alcance

La fuente primaria (inventario por turno) está **pendiente de autorización** por la
administración de la unidad de salud. Mientras se autoriza:

- La capa Bronce opera con las dos fuentes públicas (dengue y clima).
- El esquema de la fuente primaria está documentado en `docs/E0/esquema-inventario.md`.
- El plan B es generar datos sintéticos con ese esquema para probar la tubería, declarándolo
  como tal en todo reporte.
