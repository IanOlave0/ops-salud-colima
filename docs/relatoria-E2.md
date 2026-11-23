# Relatoría — E2

## 1. Fuente elegida

Se eligió **DENUE + Marco Geoestadístico** para incorporar una fuente
especializada geoespacial. El objetivo es describir la oferta de farmacias
alrededor de las zonas donde podrían ubicarse unidades de salud, no inferir
inventario ni desabasto.

La unidad de análisis pública es el municipio codificado. La relación
`unidad_id → zona_codigo` no se incluye en el repositorio; si los contactos la
autorizan, se usará solo localmente.

## 2. Decisión de acceso

La API DENUE requiere un token que no estaba disponible al iniciar la
implementación. Se optó por la **descarga masiva oficial por entidad** de
INEGI, que no requiere token y contiene el mismo directorio. Esto evita
guardar credenciales y permite reproducir el agregado localmente.

- Archivo: `denue_06_csv.zip`
- Edición: `05/2026`
- Registros de Colima: 42 073
- Campos usados: `cve_ent`, `cve_mun`, `codigo_act`, `per_ocu`

El código conserva la opción de agregar un cliente API en el futuro, pero la
entrega actual no depende de él. La captura real usa el ZIP oficial, cuyo hash
queda en `zip_sha256`; el CSV extraído se procesa en un directorio temporal y
se elimina al terminar.

## 3. Qué se construyó

- Agregado por `(zona_codigo, actividad_scian, estrato)` con conteos no
  negativos.
- Snapshot Bronce mínimo, sin nombres, domicilios, contactos ni coordenadas.
- Metadata con edición, query ID, fecha de ingesta y SHA-256.
- Intersección con polígonos municipales oficiales de Colima.
- Cálculo de área en EPSG:6933 y densidad por km².
- Oro con linaje completo y mapa coroplético.
- Pruebas para códigos con ceros, respuestas incompletas, duplicados,
  geometrías inválidas, linaje y mapa.

## 4. Resultados

- 10 municipios.
- 323 farmacias sin minisúper y 79 con minisúper: 402 en total.
- Colima (114), Manzanillo (97) y Tecomán (65) concentran la mayor oferta.
- No hubo consultas incompletas: la fuente masiva cubre toda la entidad.

Estos números describen establecimientos registrados; no miden existencias ni
capacidad de suministro.

## 5. Aporte de Carlos

Carlos Ramirez aportó la rama `feature/e2-geospatial-carlos` con la primera
integración GeoPandas, el catálogo SCIAN, la ética/fuentes y las pruebas
iniciales. Su trabajo se conserva en el historial. En esta rama se corrigieron
los casos de conteos incompletos, duplicados, geometrías y linaje antes de
producir la entrega final.

## 6. Verificación y límites

La suite E2 se ejecuta sin red con fixtures y cubre los casos críticos. La
corrida real descarga el archivo oficial, agrega 402 farmacias y genera el
mapa. Las limitaciones principales son la granularidad municipal, la
cobertura desigual del DENUE y la ausencia de un vínculo autorizado entre
unidades y zonas.

No se afirma que la densidad de farmacias prediga desabasto. Es una variable
de contexto para E3 o para un análisis exploratorio posterior.
