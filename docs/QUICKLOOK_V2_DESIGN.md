# Quicklook v2 — contrato local de revisión visual

Estado: implementado localmente para siete casos de calibración; todavía no
inicia la revisión humana ni crea etiquetas.

## Alcance

Quicklook v2 es una composición nueva y separada de los paneles v1. Lee
únicamente los seis PNG locales de cada evento, las filas dNBR v3 de
`data/interim/sentinel2_dnbr_event_metrics.csv` y los inventarios ya validados
a través de `load_dnbr_inputs`. No consulta Earth Engine, no descarga escenas,
no reconstruye valores científicos desde colores y no escribe CSV, JSON
científico, cache ni checkpoint.

El contrato explícito es:

```text
quicklook_version = "fuegopa-dnbr-quicklook-v2"
pipeline_version = "fuegopa-sentinel2-dnbr-v3"
panel = 2048 × 1440 RGB PNG
```

La fuente tipográfica es Arial TrueType instalada en Windows, rasterizada por
GDI. La ruta del sistema se registra en el reporte, pero no se copia ni se
distribuye dentro del repositorio. No se añadió una dependencia Python nueva:
Pillow, Matplotlib y NumPy no forman parte del entorno dedicado.

## Composición

- El panel principal representa `selected_pair` y conserva el rango visual
  fijo dNBR `[-1.0, 1.0]`.
- RGB usa interpolación bilineal solo para presentación; NBR, dNBR y la máscara
  usan nearest-neighbor.
- Los seis PNG se validan antes de escribir cualquier salida v2. Se rechazan
  fuentes faltantes, uniformes, verdes históricas o con capas reutilizadas.
- El panel muestra evento, fechas/horas UTC, días hasta pre/post, política o
  fallback, AOI b0500, escala analítica 20 m, CS+ `0.50`, solapamiento válido,
  dNBR mediana/p90, área sobre 0.20 y porcentaje válido.
- RGB incluye halos FIRMS, centroide diferenciado, leyenda compacta y barra de
  escala visual de 500 m. Los overlays ya incluidos en los PNG v1 no se
  reinterpretan como datos numéricos.
- Si la fracción válida es `>= 0.98`, la máscara pasa a un inset compacto; si
  es menor, conserva un panel grande para que la distribución de inválidos sea
  visible.
- Los píxeles inválidos se conservan identificables con la paleta neutral de
  los artefactos fuente y la leyenda `INVALID`/`VALID`.

## Robustez temporal

Cada evento recibe una hoja independiente que compara, a CS+ `0.50`:

- `selected_pair`;
- `window_median`;
- dNBR mediana, p90, área `> 0.20 ha`, solapamiento y diferencias absolutas;
- una bandera de acuerdo/desacuerdo descriptiva;
- la indicación de política principal o fallback.

No existe un raster numérico local para `window_median`. Por eso la hoja lo
marca literalmente como `metrics only`, no enlaza una imagen
`selected_pair` como si fuera `window_median` y no genera un segundo mapa.

No hay raster numérico local suficientemente preciso para reconstruir el rango
diagnóstico `[-0.25, 0.50]`. No se invierten paletas ni se recupera dNBR desde
RGB; el reporte y los paneles contienen:

> Diagnostic dNBR remap unavailable from local numeric data; deferred to Level 2.

False-color SWIR también queda diferido a Level 2 porque no existe un artefacto
local trazable con B12/B8A/B4. No se simula desde RGB.

## Reproducción

Para generar exactamente los siete eventos aprobados:

```powershell
conda activate fuegopa
python scripts/run_dnbr_quicklook_v2.py
```

Para un smoke test local acotado:

```powershell
python scripts/run_dnbr_quicklook_v2.py --max-events 1
```

Salidas nuevas, ignoradas por Git:

- `outputs/figures/sentinel2_dnbr_v2/events/` — panel principal y hoja de
  comparación por evento;
- `outputs/review_upload_v2/` — copias de las dos hojas para los siete casos;
- `outputs/quicklook_v2_report.json` y `.md` — contrato, rutas, fuentes y
  límites de la reconstrucción.

Quicklook v1 permanece en
`outputs/figures/sentinel2_dnbr/events/` y `outputs/review_upload/`; v2 no lo
sobrescribe ni lo borra.

## Límite científico

`dNBR` es descriptivo y no confirma un incendio. No se define
`significant_burn`, no se etiqueta severidad, no se llena `review_queue`, no se
amplía la cohorte, no se usa 2026, no se cambia clustering y no se entrena un
modelo en esta fase.
