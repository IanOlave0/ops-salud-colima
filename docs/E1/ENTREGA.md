# Ficha técnica — Entrega E1

**Proyecto:** Observatorio de presión operativa en salud de primer nivel — Colima
**Repositorio:** <https://github.com/IanOlave0/ops-salud-colima>
**Capa:** Bronce → Plata → Oro
**Estado de la fuente primaria:** pendiente de autorización; el inventario de
demostración es sintético y está marcado como tal.

## 1. Alcance

E1 tiene dos componentes que comparten la misma política de calidad:

1. **Inventario por turno:** limpieza y preprocesamiento del contrato privado
   usando un conjunto sintético determinista mientras llega la autorización.
2. **Series públicas:** integración semanal dengue + clima para Colima, con
   reportes de cobertura, conflictos, faltantes, atípicos y transformaciones.

No se usan datos reales de la unidad de salud. Los derivados no se versionan.

## 2. Entregables

| # | Entregable | Ruta |
|---|---|---|
| 1 | Generador sintético de inventario | `src/generar_sintetico.py` |
| 2 | Pipeline de limpieza y preprocesamiento | `src/preprocesar_inventario.py` |
| 3 | Integración pública dengue + clima | `src/integrar_publicos.py` |
| 4 | Decisiones de limpieza del inventario | `docs/E1/limpieza.md` |
| 5 | Decisiones de integración pública | `docs/E1/integracion.md` |
| 6 | Puerta de calidad y cuarentena | `cuarentena/{sintetico,publico}/` |
| 7 | Salidas Plata y Oro | `datos_plata/`, `datos_oro/` |
| 8 | Pruebas automatizadas | `tests/` |
| 9 | Relatoría | `docs/relatoria-E1.md` |

## 3. Evidencia de la capa Bronce

| Serie | Archivo | Semanas | Filas |
|---|---|---:|---:|
| Dengue por entidad | `datos_crudos/dengue_estados_semanal.csv` | 43 | 1 376 |
| Clima por ciudad | `datos_crudos/clima_ciudades_semanal.csv` | 97 | 485 |
| Inventario sintético | `datos_crudos/inventario_turno_sintetico.csv` | 120 días × 3 turnos | 3 600 |

## 4. Ejecución

```bash
python3 src/generar_sintetico.py
python3 src/preprocesar_inventario.py \
  --input datos_crudos/inventario_turno_sintetico.csv
python3 src/integrar_publicos.py
python3 src/validar.py
python3 -m unittest discover -s tests -v
```

## 5. Resultados actuales

### Inventario sintético

- 3 600 filas, 2 unidades, 120 días, 5 insumos.
- 108 faltantes de `consumo` recuperados por balance de inventario.
- 96 faltantes de `personal_disponible` imputados por mediana agrupada.
- 46 atípicos de pacientes (39 altos, 7 bajos); 34 de consumo.
- 0 filas en cuarentena en la fuente sintética; la prueba de cuarentena
  construye defectos deliberados.
- Bronce intacto: SHA-256
  `42a410e47814903be196e7f1f2a658cb6fee7bb0b0e60b9010a18cbc85751aac`.

### Integración pública

- 43 semanas de Colima en Plata y Oro.
- 0 semanas sin clima para las 43 semanas de dengue de Colima.
- 0 filas en cuarentena en la corrida actual.
- Atípicos climáticos: 2 IQR, 3 modified Z, 3 en la unión.

## 6. Decisiones de calidad

- La puerta valida la tabla completa, no solo fila por fila. La unicidad se
  comprueba después de resolver conflictos; los duplicados se resuelven por
  `extraido_en` más reciente y se reportan.
- Las cuatro salidas se publican con respaldo y rollback; no se dejan archivos
  de ejecuciones mezcladas.
- Solo se escriben filas válidas en Plata y Oro. Las rechazadas van a
  cuarentena con `motivo`.
- Las banderas de imputación se crean antes de rellenar y los valores
  originales se conservan.
- Los atípicos se marcan sin eliminar; los extremos climáticos pueden ser
  eventos reales.
- La integración no crea semanas ni extrapola ciudades.

## 7. Limitaciones

- El inventario es sintético; no valida supuestos de la operación real.
- La integración pública es semanal y no sustituye el análisis por turno.
- El mecanismo MNAR no es identificable con los agregados observados.
- Min-Max y Z-Score se ajustan con toda la tabla en E1; E2 debe usar solo
  train.
- La autorización de la unidad de salud sigue pendiente.

## 8. Checklist de cierre

- [x] Generador sintético determinista y marcado.
- [x] Pipeline de limpieza con banderas y cuarentena.
- [x] Integración dengue + clima con reporte de conflictos.
- [x] Puerta de calidad y cuarentena.
- [x] Pruebas automatizadas.
- [x] Ficha técnica y relatoría.
- [ ] Tag `e1` reubicado al commit final de la entrega.
- [ ] Enlace registrado en el formulario oficial.
