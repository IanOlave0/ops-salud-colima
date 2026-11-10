# Esquema de la fuente primaria — inventario por turno

Documento de especificación. **No contiene datos reales.** La unidad de salud aún no autoriza
la extracción; este esquema fija el contrato de datos para la capa Bronce.

## 1. Granularidad

Una fila = **un insumo en un turno de una unidad**.

Claves: `unidad_id`, `fecha`, `turno`, `insumo_id`.

## 2. Columnas

| Columna | Tipo | Descripción | Obligatoria |
|---|---|---|---|
| `unidad_id` | texto | Identificador codificado de la unidad (`U01`, `U02`) | Sí |
| `fecha` | fecha (ISO 8601) | Día del turno | Sí |
| `turno` | categórica | `M` matutino, `V` vespertino, `N` nocturno | Sí |
| `insumo_id` | texto | Identificador codificado del insumo | Sí |
| `insumo_nombre` | texto | Nombre genérico (sin marca comercial) | Sí |
| `familia` | categórica | `medicamento` o `material_curacion` | Sí |
| `existencia_inicial` | entero | Piezas disponibles al iniciar el turno | Sí |
| `entradas` | entero | Piezas recibidas durante el turno | Sí |
| `consumo` | entero | Piezas utilizadas durante el turno | Sí |
| `existencia_final` | entero | Piezas al cerrar el turno | Sí |
| `desabasto` | binaria | 1 si hubo falta declarada, 0 si no | Sí |
| `pacientes_atendidos` | entero | Personas atendidas en el turno | Sí |
| `personal_disponible` | entero | Personal presente en el turno | Sí |

## 3. Reglas de consistencia

1. `existencia_final = existencia_inicial + entradas − consumo`.
2. `desabasto = 1` solo si existe registro explícito de falta.
3. Ningún valor negativo.
4. `fecha` + `turno` no se repite para el mismo `insumo_id`.
5. Si falta un dato, se deja vacío; **no se imputa en la capa Bronce**.

## 4. Privacidad

- Sin nombres de pacientes ni de personal.
- Sin números de expediente, CURP, diagnóstico individual ni fecha de nacimiento.
- `unidad_id` e `insumo_id` codificados antes de salir del sistema de la unidad.

## 5. Volumen esperado

- 4 meses ≈ 120 días × 3 turnos = 360 turnos por unidad.
- 5 insumos críticos → ≈ 1 800 filas por unidad.

## 6. Plan B

Si la autorización no llega antes de E1, se generará un conjunto sintético con este mismo
esquema (`src/generar_sintetico.py`), marcado explícitamente como sintético en nombre de
archivo y en todo reporte.
