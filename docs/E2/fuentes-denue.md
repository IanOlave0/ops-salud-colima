# Fuentes de datos — E2 (DENUE + Marco Geoestadístico)

## 1. DENUE
- **Método:** `Cuantificar` (agregado por zona y actividad económica).
- **Parámetros públicos canonizados:**
  - `actividad_scian`: `464111`, `464112`.
  - `zona_codigo`: Claves de municipio (Colima: 06001 a 06010).
  - `estrato`: `0` (todos los estratos).
- **Edición DENUE:** Pendiente de confirmar (05/2026 u 11/2026).
- **`denue_query_id`:** SHA-256 de los parámetros públicos canonizados (sin token).
- **Fecha de ingesta (UTC):** Generada automáticamente en el snapshot por Ian.
- **SHA-256 del snapshot:** Calculado automáticamente en el snapshot por Ian.
- **URL base oficial:** `https://www.inegi.org.mx/servicios/api_denue.html` (sin token).

## 2. Marco Geoestadístico
- **Versión:** 2025 (o la vigente al momento de la descarga).
- **Producto:** `00_mun` (polígonos de municipios) para el estado de Colima.
- **CRS original:** `MEXICO_IRF-2008_LLC` (EPSG:6362) o el que entregue el INEGI.
- **SHA-256 del archivo de polígonos:** Se calculará al integrar el shapefile.
- **Atribución:** “Fuente: INEGI, Marco Geoestadístico”.

## 3. Linaje
Cada fila de la Capa Oro incluye:
- `denue_edicion`, `denue_query_id`, `denue_sha256`, `denue_ingestado_en`.
- `marco_version`, `marco_sha256`.
- `transformacion_version` (hash del commit del pipeline o etiqueta de versión).

Con estos campos, cualquier registro de Oro puede rastrearse hasta el snapshot Bronce y los polígonos del Marco.