# E1 — Limpieza y preprocesamiento del inventario por turno

Documento de decisiones del pipeline que transforma la capa **Bronce** sintética
(`datos_crudos/inventario_turno_sintetico.csv`) en una capa **Plata** validada.
La fuente Bronce se lee, nunca se modifica. Los datos reales solo se procesan si
se declaran explícitamente como tales y sus derivados no se versionan.

## 1. Comando reproducible

```bash
python3 src/preprocesar_inventario.py \
  --input datos_crudos/inventario_turno_sintetico.csv \
  --fuente auto
```

`--fuente` acepta `auto` (por defecto), `sintetico` o `real`. Las salidas se
derivan de la fuente verificada:

| Ruta | Contenido |
|---|---|
| `datos_plata/{fuente}/inventario_turno_plata.csv` | Tabla limpia, tipada, validada y con columnas derivadas |
| `datos_plata/{fuente}/inventario_turno_reducido.csv` | Selección explícita de columnas para E1 |
| `cuarentena/{fuente}/inventario_turno_invalido.csv` | Filas rechazadas con `motivo` |
| `cuarentena/{fuente}/_reporte.json` | Diagnóstico, conteos, reglas y trazabilidad SHA-256 |

`datos_plata/` y `cuarentena/` están en `.gitignore`: son artefactos
regenerables y, si algún día contienen datos reales, no deben publicarse. Se
versionan el esquema, el generador sintético, su reporte de procedencia
(`datos_crudos/_reporte_sintetico.json`), el CSV sintético marcado, las pruebas
y esta documentación. El generador deriva el reporte junto al CSV de salida; una
`--salida` alterna no sobrescribe el reporte versionado.

## 2. Procedencia verificable

Antes de procesar, el pipeline exige que `es_sintetico` sea uniforme (todas las
filas 1 o todas 0). No se aceptan mezclas, vacíos ni valores fuera de `{0, 1}`:
son un **fallo global de procedencia** que aborta la corrida antes de la
cuarentena, porque sin una fuente verificable no se puede etiquetar ninguna
salida. No se reetiquetan filas individuales.

- **Sintético:** debe existir `_reporte_sintetico.json` junto a la entrada y su
  `sha256` debe coincidir exactamente con el SHA-256 del CSV. Si falta o no
  coincide, el pipeline falla; no se etiqueta como sintético por vecindad.
- **Real:** todas las filas deben tener `es_sintetico=0`. Los metadatos
  sintéticos que existan se ignoran y el reporte lo advierte.
- **Auto:** infiere la fuente de la marca uniforme, aplicando las reglas
  anteriores.

Plata y la tabla reducida incorporan la columna `fuente`
(`sintetico`/`real`), y el validador exige que sea coherente con
`es_sintetico`. El reporte registra `fuente`, `sha256_entrada`, la ruta y el
hash declarado por los metadatos, si se usaron y si coincidieron.

## 3. Contrato de capa Plata

La puerta de calidad valida:

- columnas exactas y en orden (`COLUMNAS_PLATA`);
- ausencia de nulos en claves, variables originales, banderas y derivadas;
- claves únicas `(unidad_id, fecha, turno, insumo_id)`;
- fechas ISO `YYYY-MM-DD`, turnos `M/V/N`, familias `medicamento` y
  `material_curacion`, fuente `sintetico`/`real`;
- enteros no negativos, `desabasto` y `es_sintetico` binarios y uniformes;
- consistencia contable
  `existencia_final = existencia_inicial + entradas - consumo`;
- Min-Max dentro de `[0, 1]`, Z-Score finito, `nivel_stock ∈ {0,1,2,3}` y
  `dias_cobertura ≥ 0`.

**Alternativa justificada a Pandera.** El entorno de ejecución no tiene Pandera
instalada y el Python del sistema está gestionado por PEP 668. Para E1 no se
agregó la dependencia: el validador explícito de
`src/preprocesar_inventario.py` cubre esquema, tipos, rangos, claves y
coherencia de procedencia, y las pruebas verifican que rechaza nulos,
duplicados, rangos inválidos, categorías inválidas e inconsistencias. Si en E2
se requiere validación declarativa más amplia, Pandera puede incorporarse con un
entorno virtual y pruebas de compatibilidad.

## 4. Rutas seguras y escritura atómica

Antes de escribir, el pipeline resuelve todas las rutas y rechaza:

- una salida igual a la entrada;
- cualquier salida dentro del árbol `datos_crudos/` del repositorio;
- cualquier salida dentro del repositorio que no esté bajo
  `datos_plata/{fuente}/` o `cuarentena/{fuente}/`;
- una salida llamada `_reporte_sintetico.json`, para no sobrescribir la
  procedencia de la fuente;
- dos salidas con la misma ruta.

Las rutas explícitas fuera del repositorio se permiten para ejecuciones
temporales o pruebas; nunca se publican. Los archivos se escriben primero como
temporales en el directorio destino. Se recalcula el SHA-256 de Bronce antes de
publicar y se guarda una copia de seguridad de cada destino. Los reemplazos se
hacen con `os.replace`; si uno falla o el SHA final cambia, se restauran los
destinos ya publicados y se eliminan los temporales. La prueba
`test_publicacion_falla_a_mitad_y_restaura_destinos` fuerza un fallo intermedio
y verifica el rollback; `test_publicacion_falla_y_elimina_destino_nuevo` cubre
el caso en que el destino no existía. Si la restauración misma falla, el error
se reporta con la lista de destinos no restaurados, no se silencia.

## 5. Cuarentena

Cada fila estructuralmente inválida se separa de Plata y conserva sus valores
originales más una columna `motivo` no vacía. Se rechazan, entre otros:

- turno, familia o fecha inválidos;
- faltantes en columnas no imputables (claves, `desabasto`, existencias,
  pacientes, nombre de insumo);
- enteros negativos o no enteros;
- inconsistencias del balance de inventario;
- claves duplicadas, detectadas antes de separar: **todas** las filas
  implicadas van a cuarentena, aunque una de ellas fuera válida por los demás
  criterios.

La uniformidad de `es_sintetico` no se resuelve fila a fila: es una compuerta
global de procedencia (sección 2). Un esquema global roto (columna faltante o
inesperada) tampoco se puede resolver fila a fila: el pipeline falla con
`ErrorEsquema` y no genera Plata.

## 6. Diagnóstico de faltantes: generador vs evidencia

El reporte separa dos cosas que no deben confundirse.

### 6.1 Mecanismo declarado por el generador

Solo aparece si la fuente es sintética verificada por SHA-256. Para la fuente
actual: MCAR 72 (`consumo`), MAR por turno nocturno 96
(`personal_disponible`) y MNAR por consumo alto 36 (`consumo`). Con fuente real,
esta sección queda como no disponible y no se copian esos conteos.

### 6.2 Evidencia observada y pruebas

El reporte calcula tasas de faltantes por turno, unidad, insumo y desabasto, y
tres pruebas chi-cuadrado de Pearson sin dependencias adicionales:

| Prueba | Estadístico | gl | p-valor |
|---|---:|---:|---:|
| `consumo` faltante vs turno | 1.203 | 2 | 0.548 |
| `consumo` faltante vs desabasto | 0.078 | 1 | 0.780 |
| `personal_disponible` faltante vs turno N/resto | 197.260 | 1 | < 0.001 |

Las lecturas se generan con las cifras de la tabla; no son texto fijo. En la
fuente actual, `consumo` falta entre 2.6 % (V) y 3.3 % (N) y la diferencia no es
estadísticamente notable; `personal_disponible` falta 8.0 % en N y 0 % en el
resto, un patrón compatible con dependencia del turno. La prueba es descriptiva
y **no prueba causalidad**: MCAR/MAR/MNAR no se afirman como certeza. Con fuente
real, las lecturas no mencionan al generador sintético.

## 7. Imputación

Solo se imputan variables predictoras; **claves y `desabasto` nunca se imputan**.
Toda imputación deja una bandera binaria.

| Variable | Regla | Bandera | Resultado |
|---|---|---|---:|
| `consumo` | Balance de inventario: `existencia_inicial + entradas - existencia_final` | `imputado_consumo` | 108 |
| `personal_disponible` | Mediana por `(unidad_id, turno)` | `imputado_personal` | 96 |

Para `consumo`, el balance recupera el valor exacto cuando las otras tres
componentes están presentes. El respaldo es la mediana por
`(unidad_id, insumo_id, turno)` y, si tampoco fuera calculable, la mediana
global. Para `personal_disponible`, el respaldo es la mediana por turno y luego
la mediana global; el reporte separa cuántos rellenos usó cada nivel. Las
pruebas comparan el consumo imputado por balance contra los valores verdaderos
del generador, no solo contra la identidad contable.

Limitación: la mediana reduce la variabilidad del grupo y no reproduce la
distribución de los valores faltantes; las banderas permiten excluir o ponderar
esas filas en E2.

## 8. Atípicos robustos

- Método: mediana ± `3.5 · 1.4826 · MAD` por grupo; si `MAD = 0`, respaldo
  `IQR / 1.349`. La detección es bilateral.
- Grupos:
  - `pacientes_atendidos`: `(unidad_id, turno)`;
  - `consumo`: `(unidad_id, insumo_id, turno)`.
- Tratamiento: winsorización en `pacientes_analisis` y `consumo_analisis`.
  Las variables originales se conservan sin cambios y **no se elimina ninguna
  fila**.
- Banderas y conteos actuales: `atipico_pacientes` = 46 (39 altos, 7 bajos);
  `atipico_consumo` = 34 (30 altos, 4 bajos).

El generador inyecta 36 atípicos altos en `pacientes_atendidos` (factor 5). El
detector robusto marca 46 porque la regla también detecta extremos bajos
legítimos de días con evento. La bandera es una advertencia, no una verdad de
negocio; el reporte separa altos y bajos para poder auditar esa diferencia.

## 9. Transformaciones y jerarquías

Se aplican sobre las variables de análisis (`*_analisis`), nunca sobre las
originales:

- **Min-Max**: `consumo_minmax`, `pacientes_minmax`, en `[0, 1]`.
- **Z-Score**: `consumo_zscore`, `pacientes_zscore`, con desviación poblacional
  (`ddof=0`).
- **Cobertura**: `dias_cobertura = existencia_final / max(consumo_analisis, 1)`.
- **Nivel de stock** (`nivel_stock`): `0` sin stock (`existencia_final = 0`),
  `1` crítico (`0 < días < 1`), `2` bajo (`1 ≤ días < 3`), `3` adecuado
  (`días ≥ 3`). Umbrales registrados: `[1.0, 3.0]`.
- **Jornada** (`jornada`): `M/V → diurno`, `N → nocturno`.
- **Familia**: jerarquía `insumo_id → familia`, con categorías
  `medicamento` y `material_curacion`.

**Advertencia para E2:** Min-Max y Z-Score se ajustaron con toda la tabla porque
E1 solo describe. En E2 los parámetros deben estimarse **solo con train** y
aplicarse a validación/prueba sin recalcular, para evitar fuga de información.

## 10. Reducción

La reducción es selección explícita de columnas, no muestreo destructivo. Se
conservan claves, variables originales, procedencia, banderas, variables de
análisis, transformaciones y jerarquías; se excluye `insumo_nombre` por ser
texto descriptivo redundante con `insumo_id`. Plata tiene 28 columnas y la tabla
reducida 27.

## 11. Reproducibilidad y trazabilidad

- Orden determinista por `(unidad_id, fecha, turno, insumo_id)`.
- CSV en UTF-8, fin de línea `\n` y flotantes con 6 decimales.
- Reporte JSON sin marcas de tiempo y con claves ordenadas.
- SHA-256 de Bronce antes y después; la publicación se bloquea si cambia.
- Dos ejecuciones con la misma entrada producen archivos byte a byte iguales
  (prueba `test_reproducibilidad_byte_a_byte`).

SHA-256 de la fuente actual:
`42a410e47814903be196e7f1f2a658cb6fee7bb0b0e60b9010a18cbc85751aac`.

## 12. Limitaciones

- Todo el análisis es sobre datos **sintéticos**; no valida supuestos de una
  operación real ni sustituye la autorización de la unidad de salud.
- El mecanismo MNAR no es identificable solo con los valores observados; el
  reporte no lo presenta como certeza.
- La imputación por balance depende de que la identidad contable sea correcta en
  la fuente; si en datos reales hay errores de captura, el balance propagará
  ese error. Las banderas permiten auditar las filas afectadas.
- La mediana agrupada no modela la distribución condicional completa.
- El detector de atípicos es sensible al tamaño y dispersión de cada grupo; con
  grupos pequeños o MAD cero puede no marcar nada (respaldo IQR).
- Min-Max y Z-Score globales son solo para E1; E2 debe reajustarlos con train.
- La procedencia sintética es autodeclarada: quien tenga control de escritura
  sobre la carpeta de entrada puede fabricar un CSV y un reporte con SHA
  coincidente. Para E2 conviene fijar hashes autorizados o firmar el reporte si
  se requiere una garantía fuerte.
- La lista blanca de `.gitignore` confía en los nombres publicados. Un archivo
  real renombrado como `inventario_turno_sintetico.csv` sería versionable; un
  chequeo de CI que exija `es_sintetico=1` en ese archivo reduce el riesgo.
- La guarda de rutas se diseñó para un checkout Linux sin symlinks dentro de
  `datos_plata/` o `cuarentena/`. En sistemas case-insensitive o con enlaces
  simbólicos conviene revisar las rutas antes de ejecutar con datos reales.
- E1 no integra clima o dengue, no entrena modelos y no construye la capa Oro.

## 13. Verificación

```bash
python3 -m unittest discover -s tests -v
python3 src/generar_sintetico.py
python3 src/preprocesar_inventario.py --input datos_crudos/inventario_turno_sintetico.csv
python3 src/validar.py
```

La suite cubre procedencia y hashes, fuente real junto a metadatos sintéticos,
rutas peligrosas, mezcla de fuentes y escritura transaccional con rollback,
Bronce intacto, esquema estricto, claves únicas, cuarentena con motivo,
duplicados válido/inválido, imputación y banderas, comparación con la verdad del
generador, atípicos, transformaciones, reducción, diagnóstico dinámico con
chi-cuadrado y reproducibilidad byte a byte. La integración pública se cubre en
`tests/test_integrar_publicos.py` y se documenta en `docs/E1/integracion.md`.
