# Propuesta del Observatorio — Entrega E0

**Proyecto:** Observatorio de presión operativa en salud de primer nivel — Colima
**Repositorio:** <https://github.com/IanOlave0/ops-salud-colima>
**Autor:** Ian Olave — Ingeniería en Sistemas Computacionales, TecNM IT Colima
**Fecha:** 9 de noviembre de 2026

---

## 1. Ficha del observatorio

| Campo | Definición |
|---|---|
| **Nombre** | Observatorio de presión operativa en salud de primer nivel — Colima (OPS-Colima) |
| **Sector económico** | Salud: servicios de atención primaria y su cadena de suministro |
| **Región** | Colima, México. Zona conurbada Colima–Villa de Álvarez y Manzanillo |
| **Pregunta detonadora** | ¿Podemos anticipar el riesgo de desabasto de medicamentos e insumos médicos en los próximos turnos, a partir del inventario, el consumo, la afluencia de pacientes y el personal disponible? |
| **Cliente potencial** | Administración de la unidad de salud; jefaturas de área que reciben el reporte en junta |
| **Usuario de la decisión** | Administración (reabastecimiento) y jefaturas de área (reprogramación de turnos y espacio) |
| **Unidad de análisis** | Turno × insumo × unidad de salud |
| **Horizonte de pronóstico** | Siguiente turno (corto plazo) y siguiente semana (planeación de pedidos) |
| **Cobertura temporal disponible** | ≈ 4 meses de registros internos por turno; 42 semanas de vigilancia epidemiológica pública; 97 semanas de clima |

### 1.1 Justificación del sector

El desabasto de insumos es un problema operativo con consecuencias medibles: suspensión de
curaciones, retraso de tratamientos y compras de emergencia a sobreprecio. A diferencia de
problemas clínicos, **no requiere datos personales de pacientes**: se resuelve con conteos
agregados por turno. Esto lo hace viable académicamente y defendible éticamente.

---

## 2. Problema validado en campo

### 2.1 Entrevista de campo

**Perfil del informante:** enfermera en servicio activo en una unidad de salud de primer nivel
en Colima. **Modalidad:** conversación exploratoria presencial, 9 de noviembre de 2026.
**Nota de transparencia:** la sesión formal de 15 minutos con registro completo de las cinco
preguntas se anexa al cierre de E0; este documento registra los hallazgos ya obtenidos.

| # | Pregunta | Respuesta obtenida | Aprendizaje |
|---|---|---|---|
| 1 | ¿Qué problemas operativos enfrentan con más frecuencia? | Sí, existen problemas operativos recurrentes | El problema es real y no anecdótico |
| 2 | ¿Qué es lo que más les afecta? | **Falta de insumos médicos "pasa muchísimo"**; falta de espacio para pacientes; la temporada de huracanes afecta al personal disponible para atender | El dolor principal es **abasto**, no la vigilancia epidemiológica |
| 3 | ¿Qué registros existen y con qué frecuencia? | Inventario y consumo **por turno**; pacientes que llegan por turno; personal disponible por turno. No se registran tiempos de espera ni pacientes no atendidos | Existe la materia prima para un modelo supervisado |
| 4 | ¿Qué insumos son críticos? | Medicamentos (prioridad), cubrebocas, guantes, jeringas, catéteres periféricos | El alcance se puede acotar a 5 familias |
| 5 | ¿Quién decide y con qué información? | **Administración**, que distribuye la información a jefaturas en junta | Hay un usuario identificable para el producto |

**Hallazgo que cambió el diseño:** la hipótesis inicial era pronosticar dengue. La informante
señaló que **la temporada de lluvias ya funciona como regla operativa** y que no percibe
utilidad clara en un pronóstico de casos. En cambio, el desabasto sí es un problema frecuente.
El observatorio se reorientó al abasto, que además tiene una decisión asociada: **cuándo y
cuánto pedir**.

### 2.2 Restricción detectada

La ventana de registros internos es de **aproximadamente 4 meses**. Con tres turnos diarios
equivale a un orden de 300–360 observaciones por insumo: suficiente para un piloto supervisado,
insuficiente para afirmar estacionalidad anual. El diseño se plantea como **estudio piloto
reproducible**, no como modelo de producción.

---

## 3. Las tres preguntas analíticas

### E1 — Variable a pronosticar

> **¿Cuál es la probabilidad de que un insumo crítico se agote durante el siguiente turno?**

- **Variable principal:** `riesgo_desabasto_siguiente_turno` (binaria: 0/1).
- **Variables auxiliares de regresión:** consumo esperado del turno y días de inventario restante.
- **Métrica:** recall de la clase "desabasto" (falso negativo = paciente sin insumo) y F1;
  precisión como métrica secundaria.
- **Justificación:** el costo de no anticipar es mayor que el de sobre-pedir.

### E2 — Factores a experimentar

> **¿Qué variables explican mejor el riesgo: consumo previo, afluencia de pacientes, personal
> disponible, turno o clima?**

| Grupo | Variables | Hipótesis |
|---|---|---|
| Inercia | consumo y existencia del turno anterior | El consumo es autorregresivo |
| Demanda | pacientes atendidos por turno | Más pacientes → más consumo |
| Capacidad | personal disponible por turno | Menos personal puede reducir procedimientos |
| Calendario | turno, día de la semana, quincena | Patrones administrativos de pedido |
| Clima | lluvia, temperatura, días de lluvia intensa | Eventos extremos alteran demanda y surtido |

**Experimento:** comparar un modelo base (solo inercia) contra el modelo completo y medir la
ganancia incremental de cada grupo mediante validación temporal y ablación.

### E3 — Grupos multivariados a comparar

> **¿El riesgo se comporta distinto entre insumos, turnos y unidades?**

1. **Familia de insumo:** medicamentos vs material de curación (cubrebocas, guantes, jeringas,
   catéteres).
2. **Turno:** matutino, vespertino, nocturno.
3. **Unidad:** Colima vs Manzanillo (sujeto a autorización de la segunda unidad).

**Comparación multivariada:** perfiles de riesgo por grupo (frecuencia de desabasto, consumo
medio, variabilidad y sensibilidad al clima), con intervalos de confianza y prueba de
diferencia entre grupos.

---

## 4. Plan de recopilación de datos

### 4.1 Fuente A — Registros internos de la unidad (fuente primaria, privada)

- **Contenido:** inventario inicial por turno, entradas, consumo, existencia final, bandera de
  desabasto, pacientes atendidos, personal disponible.
- **Granularidad:** turno × insumo.
- **Ventana:** ≈ 4 meses.
- **Estado:** esquema verificado por la informante; **pendiente de autorización formal** de la
  administración y de confirmación de completitud.
- **Tratamiento:** no se publican datos crudos. Se usará una tabla agregada o anonimizada
  (`unidad_id` codificado), y el repositorio solo contendrá el **esquema** y los scripts.
- **Esquema:** ver `docs/E0/esquema-inventario.md`.

### 4.2 Fuente B — Vigilancia epidemiológica (fuente secundaria, pública)

- **Fuente:** Dirección General de Epidemiología, *Panorama Epidemiológico de Dengue* 2026.
- **Uso:** contexto de demanda asistencial y estacionalidad; variable de control, no objetivo.
- **Cobertura capturada:** 42 semanas epidemiológicas × 32 entidades (1 344 registros).
- **Acceso:** PDFs publicados semanalmente en `gob.mx`, descargados vía HTTPS con
  identificación de agente.

### 4.3 Fuente C — Clima (fuente secundaria, pública)

- **Fuente:** Open-Meteo Historical Weather API.
- **Uso:** lluvia, temperatura, humedad y días de lluvia intensa para Colima y Manzanillo.
- **Cobertura capturada:** 97 semanas × 5 ciudades (485 registros).
- **Acceso:** API documentada, sin autenticación.

### 4.4 Análisis ético y legal

| Fuente | `robots.txt` | Términos de uso | Datos personales | Decisión |
|---|---|---|---|---|
| `www.gob.mx` (DGE) | Solo contiene reglas para `Googlebot` con `Disallow:` vacío; **no restringe** agentes genéricos | Documentos públicos de la Secretaría de Salud; datos abiertos de vigilancia, sin identificadores | No contiene datos personales: son conteos agregados por entidad | **Uso permitido**. Se descarga con agente identificado, una vez por semana y con pausa entre solicitudes |
| `archive-api.open-meteo.com` | `Disallow: /` para rastreadores | API oficial: uso **no comercial**, licencia **CC-BY 4.0**, límites de 10 000 llamadas/día, 5 000/hora y 600/minuto | No aplica | **Uso permitido con atribución**. No se hace *crawling*: se consume la API documentada, dentro de los límites |
| Registros internos de la unidad | No aplica (sistema interno) | Autorización escrita de la administración | Contiene datos operativos, no clínicos; aun así se codifican identificadores | **Uso condicionado a autorización**. Sin nombres de pacientes ni de personal; solo conteos por turno |

**Principios aplicados:**

1. **Minimización:** solo se solicita lo necesario para el modelo (conteos y existencias).
2. **Finalidad:** uso académico, sin publicación de datos identificables.
3. **Anonimización:** `unidad_id`, `insumo_id` y `turno_id` codificados; sin fechas exactas de
   atención individual.
4. **Trazabilidad:** cada archivo de la capa Bronce conserva URL de origen y marca de tiempo.
5. **Atribución:** Open-Meteo se cita en README y en cualquier figura derivada.

---

## 5. Arquitectura de la capa Bronce

```
Fuente pública          Extractor               Capa Bronce
─────────────────       ─────────────           ─────────────────────────────
DGE (PDF semanal)  →  extract_dengue.py  →  datos_crudos/dengue_estados_semanal.csv
Open-Meteo (API)   →  extract_clima.py   →  datos_crudos/clima_ciudades_semanal.csv
Registros internos →  (pendiente auth.)  →  datos_crudos/inventario_turno.csv
```

- **Orquestación:** GitHub Actions, ejecución diaria a las 07:00 (America/Mexico_City) y
  ejecución manual (`workflow_dispatch`).
- **Idempotencia:** el extractor de dengue descarga solo semanas nuevas y refresca las últimas
  tres para capturar revisiones de vigilancia.
- **Control de calidad automatizado:** `src/validar.py` falla la corrida si hay menos de 36
  periodos.
- **Trazabilidad:** cada fila guarda `url` y `extraido_en`.

---

## 6. Sistema de calidad (PSP)

Registros abiertos por integrante en `calidad/`:

- `calidad/tiempo-ian.csv` — tiempo por actividad.
- `calidad/defectos-ian.csv` — defectos encontrados, fase, causa y tiempo de corrección.

### Objetivos de calidad medibles

| # | Objetivo | Meta | Medición | Estado actual |
|---|---|---|---|---|
| OC-1 | Cobertura de la serie | ≥ 95 % de las semanas publicadas por la fuente | semanas con datos / semanas publicadas | **42/43 = 97.7 %** |
| OC-2 | Exactitud de extracción | 100 % de coincidencia en auditoría manual (3 semanas × 5 entidades) | comparación contra PDF | Pendiente de auditoría |
| OC-3 | Disponibilidad de la captura | ≥ 95 % de corridas exitosas en 30 días; latencia ≤ 24 h | historial de Actions | En medición |

---

## 7. Limitaciones y riesgos

1. **Ventana corta (4 meses):** no permite modelar estacionalidad anual; el modelo es un piloto.
2. **Autorización pendiente:** sin permiso formal no hay datos internos; el plan B es usar datos
   sintéticos con el mismo esquema para validar la tubería, declarándolo explícitamente.
3. **Registro manual:** el inventario por turno puede tener errores de captura; se requiere
   depuración y detección de valores atípicos.
4. **Desbalance de clases:** el desabasto es poco frecuente; se reportará recall y no solo
   exactitud.
5. **Generalización:** los resultados de una unidad no se extrapolan automáticamente a otra.

---

## 8. Siguientes hitos

| Entrega | Producto |
|---|---|
| E1 | Serie limpia por turno, análisis exploratorio y línea base del riesgo de desabasto |
| E2 | Comparación de modelos con ablación de factores (clima, personal, demanda) |
| E3 | Comparación multivariada por insumo, turno y unidad, con reporte reproducible |

---

## 9. Referencias

- Dirección General de Epidemiología. *Panorama Epidemiológico de Dengue 2026*. Secretaría de
  Salud. <https://www.gob.mx/salud/documentos/panorama-epidemiologico-de-dengue-2026>
- Open-Meteo. *Historical Weather API — Terms and licence* (CC-BY 4.0, uso no comercial).
  <https://open-meteo.com/en/terms>
- `https://www.gob.mx/robots.txt` (consultado el 9 de noviembre de 2026).
- Secretaría de Salud. *Términos de libre uso de la información*.
  <http://www.dgis.salud.gob.mx/contenidos/basesdedatos/BD_Cubos_gobmx.html>
