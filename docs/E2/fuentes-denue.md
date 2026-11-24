# Fuentes de datos — E2 (DENUE + Marco Geoestadístico)

## 1. DENUE

- **Producto:** Directorio Estadístico Nacional de Unidades Económicas.
- **Edición usada:** `05/2026`, modificada el `2026-05-20`.
- **Vía de acceso:** descarga masiva oficial por entidad federativa, archivo
  `denue_06_csv.zip` (Colima). No requiere token.
- **URL:** <https://www.inegi.org.mx/contenidos/masiva/denue/denue_06_csv.zip>
- **Archivo interno usado:** `conjunto_de_datos/denue_inegi_06_.csv`.
- **Codificación:** Latin-1 (ISO-8859-1).
- **Cobertura:** 42 073 establecimientos de Colima en el archivo oficial.
- **Catálogo SCIAN:** estructura oficial México 2023,
  <https://www.inegi.org.mx/contenidos/app/scian/estructura2023.pdf>,
  consultada el 2026-11-23. Se usan las clases `464111` y `464112`.
- **SHA-256 del ZIP descargado:**
  `948e292e567ce16a8b7485f15846ddaaf9c9cda6fda9be07334bb6afc5480af6`.
  Se registra en `denue_snapshot.json` como `zip_sha256` para verificar el
  insumo de origen.

### Campos utilizados

| Campo | Uso |
|---|---|
| `cve_ent` | Entidad `06`; forma parte de `zona_codigo`. |
| `cve_mun` | Municipio; forma parte de `zona_codigo` de cinco dígitos. |
| `codigo_act` | Clase SCIAN; se conservan solo `464111` y `464112`. |
| `per_ocu` | Estrato de personal ocupado; se conserva como `estrato`. |

No se conservan `nom_estab`, `raz_social`, domicilio, teléfono, correo,
coordenadas ni ningún otro campo individual.

### Agregación

Se cuenta cada combinación:

```text
(zona_codigo, actividad_scian, estrato)
```

La descarga masiva cubre toda la entidad. Por eso, si una combinación
zona/actividad no aparece, se registra como **cero observado** con
`estado_query="completo"`. Una respuesta de API incompleta, en cambio, se
mantiene como `sin_respuesta`/`incompleto` y no se convierte en cero.

### Snapshot y linaje

- `datos_crudos/e2/denue_cuantificar_zona.csv`
- `datos_crudos/e2/denue_snapshot.json`
- `datos_crudos/e2/marco_geoestadistico_zonas.geojson`
- `datos_crudos/e2/marco_snapshot.json`

El snapshot contiene:

```text
zona_codigo, actividad_scian, estrato, establecimientos, estado_query,
denue_edicion, denue_query_id, ingestado_en
```

`denue_query_id` es el SHA-256 de los parámetros públicos de la consulta
—fuente, método, edición, entidad y actividades—; no incluye token. El
`sha256` del CSV agregado queda en el JSON de snapshot.

## 2. Marco Geoestadístico

- **Servicio:** `https://gaia.inegi.org.mx/wscatgeo/v2/geo/mgem/06`
- **Producto:** polígonos municipales de Colima.
- **Versión de la fuente:** Marco Geoestadístico, diciembre de 2025
  (`2025-12` en el pipeline).
- **CRS original:** EPSG:4326 (coordenadas geográficas).
- **Subconjunto publicado:** `datos_crudos/e2/marco_geoestadistico_zonas.geojson`
  con `zona_codigo`, `municipio`, `pob_total` y geometría.
- **Atribución:** “Fuente: INEGI, Marco Geoestadístico”.

El pipeline reproyecta a `EPSG:6933` para calcular áreas en km² y vuelve a
`EPSG:4326` solo para el mapa.

## 3. Linaje de Oro

Cada fila de `datos_oro/e2/publico/indicadores_farmacias_zona.csv` contiene:

- `denue_edicion`, `denue_query_id`, `denue_sha256`, `denue_ingestado_en`;
- `marco_version`, `marco_sha256`;
- `transformacion_version`.

Con esos campos se puede reconstruir el agregado desde el snapshot DENUE y
el GeoJSON del Marco, sin acceder a registros individuales ni a unidades de
salud.
