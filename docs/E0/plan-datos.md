# Plan de Recopilación de Datos — Capa Bronce

## 1. Fuentes y esquemas

### Fuente A — Registros internos de la unidad (fuente primaria, privada)
- **Contenido:** inventario por turno, entradas, consumo, existencia final, bandera de desabasto, pacientes atendidos, personal disponible.
- **Granularidad:** turno × insumo.
- **Estado:** pendiente de autorización formal.
- **Tratamiento:** no se publican datos crudos. Esquema detallado en `docs/E0/esquema-inventario.md`.

### Fuente B — Vigilancia epidemiológica (pública)
- **Fuente:** Dirección General de Epidemiología (DGE).
- **Cobertura capturada:** 42 semanas epidemiológicas.
- **Archivo destino:** `datos_crudos/dengue_estados_semanal.csv`.

### Fuente C — Clima (pública)
- **Fuente:** Open-Meteo Historical Weather API.
- **Cobertura capturada:** 97 semanas.
- **Archivo destino:** `datos_crudos/clima_ciudades_semanal.csv`.

## 2. Esquema de salida (Bronce)
Cada archivo conserva trazabilidad: `url, extraido_en, fecha, periodo, entidad, variable, valor`.

## 3. Automatización
- **Workflow:** `.github/workflows/bronce.yml`
- **Scripts:** `src/extract_dengue.py`, `src/extract_clima.py`, `src/validar.py`
- **Frecuencia:** diaria a las 07:00 (America/Mexico_City).