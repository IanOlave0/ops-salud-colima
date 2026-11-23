# Declaración de Ética y Legalidad — Entrega E2

## 1. Fuentes integradas y licencias

### 1.1. DENUE (INEGI)
- **Licencia:** Términos de Libre Uso de la Información del INEGI.
- **Permisos:** copiar, distribuir, difundir, publicar, adaptar, reordenar y extraer la información, incluso con fines comerciales, **siempre que se otorgue el crédito correspondiente al INEGI** y no se alteren ni supriman los metadatos.
- **Obligación de atribución:** “Fuente: INEGI, Directorio Estadístico Nacional de Unidades Económicas (DENUE)”.
- **Restricción:** no presentar el análisis como una postura oficial del INEGI ni sugerir que el INEGI avala, patrocina o apoya el proyecto.

### 1.2. Marco Geoestadístico (INEGI)
- Misma licencia de libre uso que el DENUE.
- **Atribución:** “Fuente: INEGI, Marco Geoestadístico”.
- Los polígonos se usan únicamente como base cartográfica; no se modifican ni se redistribuyen como producto independiente.

### 1.3. Análisis de `robots.txt`
- El sitio `inegi.org.mx` no bloquea a los rastreadores en su `robots.txt`.
- **No obstante**, el consumo de DENUE se realiza mediante la **API oficial** con token, no mediante scraping masivo. Se respetan los límites de peticiones documentados por el INEGI.
- El `robots.txt` **no sustituye** los Términos de Libre Uso; la API se rige por estos últimos.

## 2. Privacidad y minimización
- **Datos personales:** el proyecto **no maneja datos personales de pacientes**.
- **Datos de establecimientos:** el snapshot Bronce es **agregado por zona** y **no contiene** nombres, razones sociales, calles, teléfonos, correos ni coordenadas de establecimientos individuales.
- **Cruce unidad ↔ zona:** la relación `unidad_id → zona_codigo` es **privada**. No se versiona en Git, no se publica y no se usa en los productos de la Capa Oro.
- **Token DENUE:** se gestiona como secreto (variable de entorno). No se imprime, no se guarda en logs ni en metadata, y no se comparte por chat o correo.

## 3. Mitigación de sesgos
- **Cobertura geográfica:** el DENUE puede sobrerrepresentar zonas urbanas y subrepresentar localidades rurales o dispersas. La capa por zona es **descriptiva** y no debe interpretarse como una verdad absoluta sobre la oferta real.
- **Actualización:** el DENUE se actualiza periódicamente; la edición usada se documenta en cada snapshot. Los conteos pueden no reflejar la situación exacta del turno en que se predice el desabasto.
- **Subregistro:** algunos establecimientos informales o de reciente apertura pueden no estar en el DENUE. El análisis no corrige ese sesgo; se declara como limitación.
- **DENUE no mide inventario:** el conteo de farmacias **no indica** cuánto inventario tienen ni si pueden abastecer a una clínica. Se usa solo como **contexto descriptivo**, no como variable predictiva directa de desabasto.

## 4. Análisis propio y no oficial
- Cualquier transformación, agregación o modelo es **responsabilidad del equipo** y **no representa una postura oficial del INEGI**.
- Las decisiones basadas en estos datos excluyen al INEGI de responsabilidad alguna.

## 5. Cumplimiento normativo
- Se respeta la **Ley del Sistema Nacional de Información Estadística y Geográfica**.
- En caso de obtener datos reales de inventario en etapas posteriores, se requerirá autorización institucional y se aplicarán los principios de minimización y confidencialidad correspondientes.