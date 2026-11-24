# Ficha técnica — Entrega E2

**Proyecto:** Observatorio de presión operativa en salud de primer nivel — Colima
**Fuente especializada:** DENUE (INEGI) + Marco Geoestadístico
**Capa:** Bronce → Plata → Oro
**Estado:** E2 implementado; tag pendiente de revisión final.

## 1. Alcance

Se integró una fuente geoespacial agregada de farmacias por municipio de
Colima. La unidad pública es el municipio codificado; no se publican
establecimientos individuales ni ubicaciones de unidades de salud.

El producto responde:

- número de farmacias por municipio;
- densidad de farmacias por km²;
- diferencias descriptivas entre municipios.

No se usa como evidencia causal de desabasto ni como medida de inventario.

## 2. Entregables

| # | Entregable | Ruta |
|---|---|---|
| 1 | Descarga y agregado DENUE | `src/e2/descargar_denue.py` |
| 2 | Descarga del Marco municipal | `src/e2/descargar_marco.py` |
| 3 | Integración geoespacial | `src/e2/integrar_geoespacial.py` |
| 4 | Orquestador E2 | `src/e2/ejecutar_e2.py` |
| 5 | Catálogo SCIAN | `src/e2/catalogo_scian.py` |
| 6 | Snapshot Bronce agregado | `datos_crudos/e2/denue_cuantificar_zona.csv` |
| 7 | Metadata y linaje | `datos_crudos/e2/denue_snapshot.json` |
| 8 | Polígonos municipales | `datos_crudos/e2/marco_geoestadistico_zonas.geojson` |
| 9 | Plata | `datos_plata/e2/publico/farmacias_zona.csv` |
| 10 | Oro | `datos_oro/e2/publico/indicadores_farmacias_zona.csv` |
| 11 | Mapa | `docs/E2/mapa_farmacias_zona.png` |
| 12 | Ética y fuentes | `docs/etica-datos.md`, `docs/E2/fuentes-denue.md` |
| 13 | Pruebas | `tests/test_e2_*.py` |

## 3. Fuente y edición

- **DENUE:** edición `05/2026`, modificada el `2026-05-20`.
- **Acceso:** descarga masiva oficial por entidad, sin token:
  <https://www.inegi.org.mx/contenidos/masiva/denue/denue_06_csv.zip>
- **Archivo:** `conjunto_de_datos/denue_inegi_06_.csv`, 42 073 registros de
  Colima.
- **Marco:** servicio oficial municipal de Colima,
  <https://gaia.inegi.org.mx/wscatgeo/v2/geo/mgem/06>, versión diciembre 2025.
- **Clases:** SCIAN `464111` (farmacias sin minisúper) y `464112` (con
  minisúper).

No se conservó ningún campo individual del DENUE.

## 4. Resultados actuales

- 10 municipios en Plata y Oro.
- 323 farmacias `464111` y 79 `464112`; **402 farmacias** en total.
- El municipio con más farmacias es Colima (114), seguido de Manzanillo (97)
  y Tecomán (65).
- La densidad más alta es Villa de Álvarez (0.219 farmacias/km²), seguida de
  Colima (0.153).
- Ninguna consulta quedó incompleta: la descarga masiva cubre toda la entidad.
- El mapa se generó en `docs/E2/mapa_farmacias_zona.png`.

## 5. Linaje

Cada fila de Oro contiene:

```text
denue_edicion, denue_query_id, denue_sha256, denue_ingestado_en,
marco_version, marco_sha256, transformacion_version
```

- `denue_query_id` es SHA-256 de los parámetros públicos, sin token.
- `denue_sha256` es SHA-256 del CSV agregado.
- `marco_sha256` es SHA-256 del GeoJSON filtrado.
- El snapshot y el GeoJSON están en `datos_crudos/e2/`.

## 6. Ejecución

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-e2.txt

python3 src/e2/descargar_denue.py
python3 src/e2/descargar_marco.py
python3 src/e2/ejecutar_e2.py
python3 -m unittest discover -s tests -v
```

Las salidas Plata/Oro se regeneran localmente y están ignoradas por Git. El
Bronce agregado y el GeoJSON público sí se versionan por ser productos
mínimos, agregados y atribuidos.

## 7. Decisiones de calidad

- La zona se conserva como texto de cinco dígitos (`06001`), no como entero.
- Se valida una fila por `(zona, actividad, estrato)`; duplicados fallan.
- Las geometrías deben tener CRS, ser válidas, no vacías y con clave única.
- El área se calcula en `EPSG:6933` antes de obtener km².
- Un estado de consulta incompleto se conserva como faltante; no se imputa a
  cero.
- La metadata de DENUE y Marco es obligatoria; sin hashes/versiones no se
  genera Oro.
- El mapa no dibuja puntos de establecimientos ni de unidades de salud.

## 8. Verificación

- Pruebas E2: 27 tests.
- Suite E1/E2: 100 tests OK.
- El snapshot Bronce conserva el SHA del CSV agregado y el SHA del ZIP de origen.
- Los hashes de Bronce E0 no se modifican.

## 9. Limitaciones

- El DENUE es una fotografía del directorio, no inventario ni surtido.
- La unidad municipal oculta diferencias entre unidades de una misma zona.
- La relación `unidad_id → zona_codigo` sigue siendo privada y no se incluye.
- No se afirma causalidad ni se usa la densidad como predictor validado.
- La edición 05/2026 es la disponible; debe revisarse cuando INEGI publique
  11/2026.
- La primera versión no usa AGEB, manzanas ni buffers de 5 km.

## 10. Checklist

- [x] Fuente geoespacial integrada.
- [x] Catálogo SCIAN verificado.
- [x] Snapshot Bronce agregado y con hash.
- [x] Plata/Oro y linaje.
- [x] Mapa y atribución.
- [x] Ética y fuentes.
- [x] Pruebas offline.
- [ ] Revisión final de calidad/seguridad.
- [ ] Merge y tag `e2`.
- [ ] Registro en el formulario oficial.
