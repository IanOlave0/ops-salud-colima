# Relatoría — E1

Se inspeccionaron README, esquema E0, extractores, validador y CSV Bronce. La fuente interna de inventario aún no cuenta con autorización ni registros; no se fabricaron datos reales. Para ejercitar el contrato documentado se genera un fixture determinista, separado y marcado como sintético.

Se implementó un pipeline ejecutable que normaliza tipos, controla calidad con Pandera, integra dengue de Colima y clima de la ciudad de Colima mediante año y semana, produce salidas Plata/Oro y registra la cuarentena. Se conserva E0 sin modificar sus extractores ni datos. La prioridad para duplicados es `extraido_en` más reciente; al no haber conflictos geográficos ni semánticos en columnas superpuestas, la equivalencia territorial queda explícita y se preservan los campos fuente.

Las series tienen distintas coberturas y solo se emparejan semanas exactas. El dengue conserva su cobertura como tabla base, con semanas meteorológicas ausentes identificadas e imputadas por mediana para variables continuas, junto con indicadores de imputación. No se usa Little: la estructura son series públicas agregadas con cobertura diferencial, no una muestra iid multivariada apropiada para inferir mecanismo. Se informa el patrón y la incertidumbre del mecanismo.

Se comparan IQR, modified Z-score e Isolation Forest con semilla fija. Los atípicos se marcan y no se eliminan porque extremos pueden ser meteorología real. Las tablas Oro reducen dimensionalidad mediante agregación semanal y selección de variables relevantes. Las salidas, reportes, escaladores y resumen de puerta permiten reproducir y auditar las transformaciones.

## Supuestos y límites

- `entidad=Colima` y `ciudad=Colima` representan el emparejamiento espacial más defendible disponible en E0; no se extrapolan datos de otras ciudades.
- Conteos de dengue ausentes en filas publicadas se leen como cero reportado.
- El inventario sintético no debe usarse para inferencia o decisiones clínicas/operativas.
- La capa Plata pública no contiene la fuente privada; su integración real requiere autorización y adaptación de la lectura al archivo autorizado.

## Reproducción

`python -m pip install -r requirements-e1.txt && make e1 && make test`.
