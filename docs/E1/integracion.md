# E1 — Integración pública dengue + clima para Colima

Este documento describe la integración de las dos series públicas de E0. Es
independiente del inventario por turno, que se documenta en
`docs/E1/limpieza.md`. Ambos pipelines comparten la misma política: Bronce se
lee, los derivados no se versionan y los registros inválidos se aíslan con
motivo.

## 1. Comando

```bash
python3 src/integrar_publicos.py
```

Salidas:

| Ruta | Contenido |
|---|---|
| `datos_plata/publico/colima_semanal.csv` | Serie semanal integrada de Colima, solo filas válidas |
| `datos_oro/indicadores_semanales_colima.csv` | Agregados semanales para análisis |
| `cuarentena/publico/registros_invalidos.csv` | Filas rechazadas con `motivo` |
| `cuarentena/publico/_reporte.json` | Cobertura, conflictos, faltantes, atípicos y transformaciones |

`datos_plata/`, `datos_oro/` y `cuarentena/` están en `.gitignore`.

## 2. Fuentes y llave

- **Dengue:** `datos_crudos/dengue_estados_semanal.csv`, unidad
  entidad × año × semana. Se filtra `entidad = Colima`.
- **Clima:** `datos_crudos/clima_ciudades_semanal.csv`, unidad ciudad × año ×
  semana. Se filtra `ciudad = Colima`.
- **Correspondencia territorial:** `entidad=Colima` ↔ `ciudad=Colima` es una
  decisión explícita, no una inferencia automática.
- **Llave de unión:** `(anio, semana)`, coincidencia exacta. No se crean
  semanas ni se extrapolan datos de otras ciudades.

## 3. Puerta de calidad y cuarentena

Antes de integrar se valida la tabla completa, no solo fila por fila:

- columnas exactas y en orden;
- `anio` y `semana` numéricos, con rangos `2000–2100` y `1–53`;
- conteos de dengue no negativos y numéricos;
- `entidad`/`ciudad` no vacías;
- coordenadas y variables meteorológicas dentro de rango;
- `dias_lluvia` y `dias_lluvia_intensa` entre 0 y 7;
- `url` y `extraido_en` presentes en dengue; `extraido_en` presente en clima.

Cada fila inválida se conserva en cuarentena con el motivo concatenado. Las
variables meteorológicas `temp_media_c`, `precipitacion_mm` y
`humedad_media_pct` pueden faltar: no se rechazan, se marcan y se imputan solo
para el análisis. Un esquema global roto (columna faltante o inesperada) aborta
la corrida con `ErrorEsquema`.

La puerta es un validador explícito propio, equivalente al usado en
`docs/E1/limpieza.md`. No se agregó Pandera para no introducir una dependencia
que el entorno del proyecto no tiene; la validación cubre esquema, tipos,
enteros, fechas ISO, rangos, categorías y la integridad de la llave después de
resolver conflictos.

Las cuatro salidas se publican con respaldo y rollback: si falla un reemplazo,
se restauran los archivos anteriores y se eliminan los temporales. La prueba
`test_falla_de_publicacion_restaura_salidas_previas` fuerza un fallo intermedio
y verifica que no queden salidas mezcladas.

## 4. Conflictos y duplicados

Si una llave `(anio, semana)` aparece más de una vez en dengue o clima, se
conserva el registro con `extraido_en` más reciente. El número de filas
resueltas queda en `integracion.duplicados_*_resueltos`. Después de resolver se
verifica que la llave sea única; si no lo fuera, el pipeline falla. No se
eliminan filas en silencio: el conflicto se reporta y la regla queda escrita.

## 5. Faltantes

El reporte calcula faltantes por variable antes de imputar. Para el clima:

1. `clima_disponible = 0` solo si no existe registro climático para la semana;
2. si existe el registro pero falta una variable, `clima_disponible = 1` y esa
   variable se marca con `*_imputado = 1`;
3. la bandera se crea **antes** de rellenar;
4. el valor original queda en la columna sin sufijo (puede ser nulo);
5. `*_analisis` contiene el valor imputado con la mediana observada;
6. Min-Max y Z-Score se calculan sobre `*_analisis`.

No se inventan semanas. La mediana no modela la distribución condicional y
puede sesgar si la ausencia depende del valor no observado (MNAR); por eso las
banderas se conservan y el mecanismo no se afirma como certeza.

## 6. Atípicos y transformaciones

- Se comparan IQR (1.5×) y modified Z (>3.5) sobre las variables climáticas.
- `posible_atipico` marca la unión; **no se elimina ni se recorta** ningún
  valor, porque los extremos meteorológicos pueden ser eventos reales.
- Min-Max y Z-Score se agregan como columnas derivadas para clima y
  `probables_2026`; los originales se conservan.
- `riesgo_dengue` discretiza `probables_2026`: `sin_reportes` (0), `bajo`
  (1–10), `medio` (11–50), `alto` (>50).
- Oro agrega una fila por semana con indicadores seleccionados; es reducción
  por agregación, no muestreo destructivo.

## 7. Resultado actual

- 1 376 filas de dengue válidas (todas las entidades).
- 485 filas de clima válidas (todas las ciudades).
- 43 semanas de Colima en ambas series; 43 filas en Plata y Oro.
- 0 filas en cuarentena en la corrida actual.
- 0 semanas sin clima para las 43 semanas de dengue de Colima.
- Atípicos climáticos: 2 por IQR, 3 por modified Z, 3 en la unión.

## 8. Pruebas

`tests/test_integrar_publicos.py` cubre:

- rechazo de valores negativos, fechas no ISO y columnas faltantes;
- faltantes meteorológicos permitidos y faltantes estructurales rechazados;
- filtro territorial, unión por llave y orden numérico de semanas;
- resolución de duplicados por `extraido_en` más reciente;
- banderas de imputación creadas antes de rellenar;
- Oro con una fila por semana;
- que el CSV publicado no contenga filas rechazadas;
- publicación transaccional con rollback;
- reproducibilidad y protección de rutas.

## 9. Limitaciones

- La unidad pública es semanal; no sustituye el análisis por turno del
  inventario.
- La integración solo cubre Colima; no se extrapola a Manzanillo ni a otras
  entidades.
- El clima faltante se imputa con mediana solo para permitir análisis; no se
  afirma el mecanismo.
- Min-Max y Z-Score se ajustan con toda la tabla en E1; en E2 deben ajustarse
  solo con train.
- La fuente privada de inventario sigue pendiente de autorización.
