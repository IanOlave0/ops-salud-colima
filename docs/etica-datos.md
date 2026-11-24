# Declaración de Ética y Legalidad — Entrega E2

## 1. Fuentes y licencias

### 1.1 DENUE (INEGI)

- **Producto:** Directorio Estadístico Nacional de Unidades Económicas, edición
  05/2026.
- **Licencia:** Términos de Libre Uso de la Información del INEGI.
- **Permisos:** copiar, distribuir, difundir, publicar, adaptar, reordenar y
  extraer la información, incluso con fines comerciales, siempre que se
  otorgue crédito al INEGI y no se alteren ni supriman los metadatos.
- **Atribución:** “Fuente: INEGI, Directorio Estadístico Nacional de Unidades
  Económicas (DENUE) 05/2026”.
- **Restricción:** no presentar el análisis como una postura oficial del INEGI
  ni sugerir que el INEGI avala, patrocina o apoya el proyecto.

### 1.2 Marco Geoestadístico (INEGI)

- Misma licencia de libre uso.
- **Atribución:** “Fuente: INEGI, Marco Geoestadístico”.
- Se publica únicamente un subconjunto municipal de Colima, con atribución y
  sin alterar la geometría de origen. Las propiedades se reducen a las
  necesarias para la unión y el mapa.
- La versión usada es la publicada por el servicio oficial como diciembre de
  2025.

### 1.3 Descarga y `robots.txt`

- La fuente se obtuvo del **archivo masivo oficial por entidad** de INEGI, no
  mediante scraping de fichas ni consultas masivas al mapa interactivo.
- El `robots.txt` consultado permite rutas generales como `/app`, `/temas` y
  `/servicios`; eso orienta a rastreadores, pero **no sustituye** los Términos
  de Libre Uso ni constituye por sí solo una autorización de uso.
- No se usó la API con token en esta entrega. La descarga masiva evita
  almacenar o compartir credenciales.
- No se localizó una cuota pública de consultas en la documentación revisada;
  por eso no se automatiza una extracción recurrente. La captura es manual y
  reproducible.

## 2. Privacidad y minimización

- **Pacientes:** el proyecto no maneja datos personales de pacientes.
- **Establecimientos:** el snapshot Bronce es agregado por zona y actividad.
  No contiene nombres, razones sociales, calles, teléfonos, correos ni
  coordenadas de establecimientos individuales.
- **Unidades de salud:** la relación `unidad_id → zona_codigo` es privada y no
  se versiona, publica ni usa en los productos Oro.
- **Salidas:** el mapa representa polígonos municipales y densidades
  agregadas; no marca clínicas ni establecimientos individuales.
- **Secretos:** esta entrega no requiere token. Si se usara la API en el
  futuro, el token se manejaría como secreto y no se incluiría en logs,
  reportes ni Git.

## 3. Mitigación de sesgos

- **Cobertura:** DENUE puede sobrerrepresentar zonas urbanas y subrepresentar
  localidades rurales o dispersas. El mapa es descriptivo.
- **Actualización:** la edición se documenta en cada snapshot; los conteos
  pueden no reflejar la situación del turno en que se analiza el desabasto.
- **Subregistro:** establecimientos informales o de reciente apertura pueden
  no estar en el directorio. No se corrige ese sesgo; se declara.
- **Definición:** el conteo de farmacias no indica existencias, surtido ni
  capacidad de abastecer una clínica. Es contexto de oferta, no una variable
  causal ni una medida de inventario.
- **Granularidad:** municipios con varias unidades comparten indicadores. No
  se infieren diferencias entre unidades a partir de esta capa.
- **Reidentificación:** una celda con `establecimientos=1` en una combinación
  zona/actividad/estrato podría cruzarse con el DENUE público para inferir un
  establecimiento. No publicamos nombre, domicilio ni coordenadas, pero el
  riesgo residual se declara; para análisis sensibles se agregará por zona y
  actividad sin estrato.

## 4. Análisis propio y no oficial

Cualquier transformación, agregación o modelo es responsabilidad del equipo y
no representa una postura oficial del INEGI. Las decisiones basadas en estos
datos excluyen al INEGI de responsabilidad alguna.

## 5. Cumplimiento

Se respeta la Ley del Sistema Nacional de Información Estadística y Geográfica
y los Términos de Libre Uso del INEGI. Cualquier dato real de inventario de una
unidad de salud requerirá autorización institucional, minimización y
confidencialidad, y quedará fuera del repositorio público.
