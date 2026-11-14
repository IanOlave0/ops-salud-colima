# Relatoría — E1

## 1. Punto de partida

Se revisaron README, esquema E0, extractores, validador, series Bronce y el
estado de la fuente primaria. El inventario por turno sigue sin autorización y
sin registros reales; por eso se construyó un conjunto sintético determinista
con el mismo contrato, marcado explícitamente en el nombre, en la columna
`es_sintetico` y en su reporte de procedencia.

También se revisó una implementación alternativa de E1, desarrollada por Carlos
Ramirez en la rama `feature/e1` (commit `6bd4b2f`). Se conservaron sus
entregables documentales y la idea de integrar dengue con clima, pero se
descartaron las partes que no cumplían el contrato: validación de unicidad fila
por fila, escritura del CSV antes de la validación final y banderas de
imputación calculadas después de imputar. Su rama queda intacta como evidencia
del trabajo original.

## 2. Inventario por turno

- El generador produce 3 600 filas (2 unidades, 120 días, 3 turnos, 5 insumos)
  con faltantes MCAR, MAR y MNAR, atípicos y una tasa de desabasto cercana al
  6 %.
- La limpieza separa filas inválidas con motivo, imputa `consumo` por balance
  de inventario y `personal_disponible` por mediana agrupada, conserva banderas
  y marca atípicos con MAD robusto sin eliminar filas.
- La procedencia se verifica con SHA-256; una fuente real no hereda metadatos
  sintéticos y sus derivados quedan fuera de Git.
- La publicación es transaccional: si falla un reemplazo, se restauran los
  destinos anteriores.

## 3. Integración pública

- Dengue define la cobertura semanal de Colima; el clima se une por
  `(anio, semana)` con coincidencia exacta.
- `entidad=Colima` ↔ `ciudad=Colima` es una correspondencia territorial
  explícita. No se extrapola a Manzanillo ni a otras entidades.
- Los duplicados se resuelven por `extraido_en` más reciente y se reportan.
- Los faltantes climáticos se marcan antes de imputar; el valor original y el
  de análisis se conservan por separado.
- Los atípicos se marcan con IQR y modified Z; no se recortan.
- Plata contiene solo filas válidas; Oro agrega una fila semanal con
  indicadores seleccionados.

## 4. Verificación

La suite cubre procedencia, rutas seguras, rollback, esquema, cuarentena,
duplicados, imputación, atípicos, transformaciones, integración, orden semanal,
faltantes y reproducibilidad. La validación de cobertura Bronce sigue en
`src/validar.py`.

## 5. Supuestos y límites

- El inventario sintético sirve para probar la tubería; no para inferencia
  clínica ni operativa.
- La unidad pública es semanal; el inventario es por turno y no se fuerza una
  unión entre granularidades distintas.
- El clima faltante se imputa con mediana solo para permitir análisis; el
  mecanismo no se afirma como certeza.
- Min-Max y Z-Score se ajustan con toda la tabla en E1; E2 debe ajustarlos solo
  con train.
- La autorización de la unidad de salud sigue siendo el requisito para usar
  datos reales.

## 6. Reproducción

```bash
python3 src/generar_sintetico.py
python3 src/preprocesar_inventario.py --input datos_crudos/inventario_turno_sintetico.csv
python3 src/integrar_publicos.py
python3 src/validar.py
python3 -m unittest discover -s tests -v
```
