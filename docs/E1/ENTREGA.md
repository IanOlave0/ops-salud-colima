# Ficha técnica — Entrega E1

**Proyecto:** Observatorio de presión operativa en salud de primer nivel — Colima  
**Capa:** Plata y Oro  
**Estado de fuente primaria:** pendiente de autorización; el inventario de demostración es sintético.

## Objetivo y alcance

Automatizar la normalización, validación, unión y agregación de las dos series públicas E0. La unidad de análisis pública es la semana epidemiológica. La vigilancia de dengue está por entidad y el clima por ciudad. Se filtran ambas a Colima y se unen por `anio, semana`. El esquema de inventario por turno de `docs/E0/esquema-inventario.md` se prueba con registros generados determinísticamente, marcados `sintetico_para_pruebas`; no son datos clínicos observados.

## Fuentes reales inspeccionadas

| Archivo | Unidad / llaves | Variables relevantes |
|---|---|---|
| `datos_crudos/dengue_estados_semanal.csv` | entidad × año × semana; llave `entidad, anio, semana` | casos probables, confirmados, defunciones por año de comparación; URL y extracción |
| `datos_crudos/clima_ciudades_semanal.csv` | ciudad × año × semana; llave `ciudad, anio, semana` | temperatura, precipitación, humedad, días de lluvia; coordenadas y extracción |
| Inventario privado | no hay fuente real autorizada | contrato en `docs/E0/esquema-inventario.md`; fixture sintética solo para pruebas |

## Transformaciones y decisiones estadísticas

- Pandera valida esquema, tipos coercionables, rangos, categorías y unicidad antes de escribir Plata. Lo rechazado se conserva en cuarentena con motivo, regla, timestamp, archivo e índice de origen.
- La unión conserva las semanas con dengue observadas y agrega clima por llave exacta. Las semanas sin clima no se inventan. Colima (entidad) ↔ Colima (ciudad) es la correspondencia territorial explícita.
- Conflictos/duplicados de una misma llave se resuelven con el registro de `extraido_en` más reciente; el reporte cuantifica duplicados, intersección y cobertura. Columnas fuente se preservan con sufijos/atributos trazables.
- Faltantes: se informa patrón por variable. La falta de clima puede depender de disponibilidad de semana (MAR plausible); el mecanismo no es identificable con los agregados observacionales. Little no se aplica porque no hay una muestra iid multivariada adecuada. Se conservan banderas de imputación; valores meteorológicos ausentes se imputan con mediana solo para permitir escalado/modelado. Semanas ausentes no se sintetizan. Conteos de dengue nulos en filas publicadas se interpretan como cero reportado.
- MNAR: no hay evidencia para afirmarlo ni descartarlo. Si la ausencia depende del valor meteorológico no observado, la mediana puede sesgar; se preservan banderas y no se crean semanas para reducir el ocultamiento. Hace falta sensibilidad con más observaciones.
- Atípicos: se comparan límites IQR (1.5×), modified Z (>3.5) e Isolation Forest (semilla fija). La salida marca unión de IQR y modified Z, sin eliminar ni recortar posibles extremos meteorológicos reales. Isolation Forest queda como diagnóstico.
- Variables climáticas continuas se transforman con Min-Max y Z-Score. Parámetros ajustados quedan en `data/plata/reportes/scaler_*.json`.
- La banda `riesgo_dengue` sigue jerarquía fija por casos probables 2026: sin reportes (0), bajo (1–10), medio (11–50), alto (>50).
- Reducción: Plata integrada contiene Colima; Oro agrega a una fila semanal con indicadores seleccionados. El inventario sintético se agrega aparte por fecha e insumo.

## Puerta de calidad y cuarentena

El proceso valida cada registro antes de publicar Plata. Rechazos van a `data/cuarentena/e1_registros_invalidos.csv`; el resumen con conteos y motivos queda en `data/plata/reportes/resumen_validacion.json`. El pipeline nunca descarta silenciosamente. Las pruebas incluyen registro inválido con motivo de rechazo.

## Salidas

- `data/plata/colima_semanal_limpio.parquet` y `.csv`: serie pública integrada y transformada.
- `data/oro/indicadores_semanales_colima.parquet`: agregados semanales.
- `data/plata/inventario_sintetico_para_pruebas.parquet` y `data/oro/inventario_sintetico_para_pruebas.parquet`: fixture, expresamente sintética.
- `data/plata/reportes/`: faltantes, atípicos, conflictos, escaladores y resumen de la puerta.
- `data/cuarentena/`: registros inválidos y su contexto.

## Ejecución

```bash
python -m pip install -r requirements-e1.txt
make e1
make test
```
