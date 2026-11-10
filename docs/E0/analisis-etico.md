# Análisis Ético y Legal — E0

## Tabla resumen

| Fuente | `robots.txt` | Términos de uso | Datos personales | Decisión |
|---|---|---|---|---|
| `www.gob.mx` (DGE) | Solo contiene reglas para `Googlebot` con `Disallow:` vacío; **no restringe** agentes genéricos | Documentos públicos de la Secretaría de Salud; datos abiertos de vigilancia, sin identificadores | No contiene datos personales: son conteos agregados por entidad | **Uso permitido**. Se descarga con agente identificado, una vez por semana y con pausa entre solicitudes |
| `archive-api.open-meteo.com` | `Disallow: /` para rastreadores | API oficial: uso **no comercial**, licencia **CC-BY 4.0**, límites de 10 000 llamadas/día, 5 000/hora y 600/minuto | No aplica | **Uso permitido con atribución**. No se hace *crawling*: se consume la API documentada, dentro de los límites |
| Registros internos de la unidad | No aplica (sistema interno) | Autorización escrita de la administración | Contiene datos operativos, no clínicos; aun así se codifican identificadores | **Uso condicionado a autorización**. Sin nombres de pacientes ni de personal; solo conteos por turno |

## Principios aplicados
1. **Minimización:** solo se solicita lo necesario para el modelo.
2. **Finalidad:** uso académico, sin publicación de datos identificables.
3. **Anonimización:** `unidad_id`, `insumo_id` y `turno_id` codificados.
4. **Trazabilidad:** cada archivo conserva URL de origen y marca de tiempo.
5. **Atribución:** Open-Meteo se cita en README y en cualquier figura derivada.

## Declaración de cumplimiento
El equipo se compromete a respetar `robots.txt`, los Términos de Uso y los límites de las APIs, no extraer datos personales, identificar el agente en cada solicitud y aplicar pausas entre peticiones.