# Diseño del piloto NBR/dNBR Sentinel-2

Estado: implementación acotada preparada; la ejecución se debe validar con
un evento individual antes de solicitar tres eventos o los 28 procesables.
Esta fase no crea etiquetas de quema, categorías de severidad ni modelos.

## Cohorte y política congelada

La unidad de análisis es un evento provisional de la configuración FIRMS
r1500_t06. El universo óptico local contiene 30 eventos: 28 tienen una pareja
utilizable bajo la política actual y dos se conservan como
optically_unobservable_under_current_policy. Esos dos eventos no son
negativos.

La política principal usa AOI b0500, ventana pre30, ventana post45 y regla A.
El único fallback aprobado usa AOI b0500, pre30 y post90; rescata únicamente
event-r1500_t06-09c2d54e2d8fb5dd. Las escenas se leen exactamente desde
outputs/sentinel2_event_pair_selection.csv. No se vuelven a seleccionar por
FRP, tamaño aparente, conveniencia visual ni inspección de cicatrices.

## Colecciones y geometría

Se usan las colecciones oficiales:

- COPERNICUS/S2_SR_HARMONIZED
- GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED

El AOI se construye con detection_union_buffer: cada detección miembro se
transforma a EPSG:32617, se genera su buffer de 500 m y se disuelven los
buffers. La geometría de consulta se transforma a EPSG:4326. La reducción
analítica usa CRS EPSG:32617 y escala de 20 m, porque B12 es una banda de 20 m.
Los inventarios existentes no se reescriben.

## Índices y máscara

La implementación usa las fórmulas declaradas:

NBR = (B8 - B12) / (B8 + B12)

dNBR = NBR_pre - NBR_post

Antes del cálculo se exige simultáneamente máscara válida de B8, máscara
válida de B12 y Cloud Score+ enlazado por system:index con cs_cdf igual o
superior al umbral. El umbral primario es 0.50. Se calculan sensibilidades
descriptivas con 0.60 y 0.65. CLOUDY_PIXEL_PERCENTAGE queda fuera de la
decisión de máscara.

La máscara común pre/post se usa para todas las métricas dNBR. El contrato de
solapamiento v3 construye un único soporte raster AOI a 20 m:

```text
aoi_support = constant(1)
    .reproject(EPSG:32617, scale=20 m)
    .clip(aoi.geometry_wgs84)
    .selfMask()
common_valid_support = aoi_support.updateMask(pre_valid AND post_valid)
```

Ambos soportes se reducen con `sum`, la misma geometría `aoi.geometry_wgs84`,
CRS `EPSG:32617`, escala `20 m`, `bestEffort=False`, el mismo `maxPixels` y el
mismo `tileScale`. Por tanto:

```text
aoi_pixel_count = sum(aoi_support)
common_valid_pixel_count = sum(common_valid_support)
valid_overlap_fraction_raw = common_valid_pixel_count / aoi_pixel_count
```

`valid_overlap_area_m2` es la suma de `pixelArea()` enmascarada por
`common_valid_support`; `rasterized_aoi_area_m2` es la suma del mismo
`pixelArea()` enmascarada por `aoi_support`. Ambos comparten la misma grilla,
región, proyección, escala, máscara y reducer. `vector_aoi_area_m2`/`aoi_area_m2`
se conservan como atributos descriptivos y no son el denominador raster.
El contrato valida por construcción `0 <= common_valid_pixel_count <=
aoi_pixel_count`; una violación real aborta el evento.

Se conservan tanto `valid_overlap_fraction_raw` como la fracción operacional.
Solo se normaliza esta última a `[0, 1]` dentro de `1e-9`, una tolerancia
numérica mínima de punto flotante. No se concede tolerancia geométrica basada
en un píxel. Las fracciones descriptivas de dNBR usan también el soporte AOI
común y conservan su validación estricta.

### Corrección v2 → v3

La fórmula observada en los outputs v2 era:

```text
valid_overlap_area_m2 = sum(pixelArea() enmascarada por common_valid_mask)
valid_aoi_area_m2 = aoi_pixel_count × (20 m × 20 m)
valid_overlap_fraction_raw = valid_overlap_area_m2 / valid_aoi_area_m2
```

El numerador dependía de la reducción de `pixelArea()` y el denominador de un
conteo raster multiplicado por `400`; no eran una pareja garantizada sobre el
mismo soporte, aunque ambos se describieran como una escala de 20 m. En los
outputs v2, por ejemplo, `valid_overlap_area_m2 / 400` no coincide exactamente
con `valid_pixel_count`. En bordes y reproyección eso podía producir un raw
mayor que uno. v3 incrementa el contrato y reconstruye ambos términos desde
`aoi_support`/`common_valid_support`; las cachés y filas v2 se excluyen.

El umbral operativo predeterminado para publicar estadísticas dNBR es 0.50 y
se puede cambiar con `--min-valid-overlap-fraction`. Es una puerta de calidad
explícita y provisional, no una conclusión científica. Si no se alcanza, se
conservan conteos y estado, pero los campos de NBR/dNBR y áreas se dejan vacíos.

## Modos

selected_pair es el análisis principal. Usa exactamente la escena pre y la
escena post de la selección congelada. Se calculan las métricas a los tres
umbrales de Cloud Score+.

window_median es sensibilidad separada. Usa todas las escenas del mismo AOI,
ventana y combinación que pasan la usabilidad local de la regla A, con al
menos una escena por lado. Para cada lado se construye una mediana de las
reflectancias B8 y B12 después de la máscara; luego se calcula NBR y dNBR
sobre la máscara común. Cambiar el umbral CS+ no vuelve a seleccionar
silenciosamente la pareja ni sustituye selected_pair.

El archivo principal conserva las filas a 0.50 de ambos modos. El archivo de
sensibilidad conserva ambos modos a 0.50, 0.60 y 0.65 para que los análisis no
se mezclen.

## Métricas y quicklooks

Se guardan medias y medianas de NBR pre/post, estadísticos dNBR, percentiles
p10, p25, p75, p90 y p95, mínimo, máximo, fracción de píxeles dNBR por encima
de 0.10/0.20/0.30/0.40 y área en hectáreas para esos umbrales. Los umbrales
son sensibilidad descriptiva; no son intervalos validados de severidad ni
ground truth.

Cada evento procesado genera seis thumbnails limitados al AOI y un panel PNG
portable con nombre `<event_id>_<analysis_mode>_cs050_panel.png`. El panel
autocontenido incluye RGB pre/post, NBR pre/post, dNBR, máscara válida común,
detecciones FIRMS y límite del AOI, además de fechas, modo, umbral CS+ y
solapamiento válido. NBR y dNBR usan el rango visual fijo global `[-1, 1]`, con
el punto neutro de dNBR en `0`; es una decisión de visualización descriptiva y
no un umbral científico. Los píxeles inválidos se
dibujan con fondo gris o magenta en la máscara y los colorbars muestran sus
rangos. El SVG anterior se conserva como artefacto auxiliar acompañado por el
PNG, no como el vínculo principal.

`quicklook_path` solo se publica para `selected_pair`; las filas
`window_median` quedan sin panel enlazado porque no se genera un panel separado
para ese modo.

Los overlays de AOI y detecciones se dibujan sobre imágenes enmascaradas con
`selfMask()` antes de visualizarse. Esto es necesario porque una imagen
constante de ceros visualizada con una paleta de un solo color pinta también
el fondo; en la ejecución anterior, el overlay de puntos usaba `#00FF00` y
contaminaba los seis thumbnails completos. El color de detección actual es
cian y no se comparte con la máscara válida.

Antes de guardar un panel se registran modo PNG, dimensiones, shape RGB,
dtype, rangos por canal, valores únicos, porcentaje exacto `#00FF00`, alpha y
hashes. El decoder local no depende de PIL, NumPy ni Matplotlib: convierte
explícitamente RGB, P, L y RGBA a RGB; alpha se compone sobre gris neutral y
nunca se trata como banda científica. Se rechazan superficies RGB uniformes,
marcadores verdes, capas científicas idénticas, fuentes ausentes y reutilización
de la máscara.

`--rebuild-quicklooks` recompone únicamente desde los seis PNG locales, no
inicializa Earth Engine, no recalcula índices y no modifica métricas,
inventarios ni checkpoints. Escribe la auditoría en
`outputs/debug/sentinel2_dnbr/`; si las fuentes ya están corruptas, falla antes
de reemplazar el panel y conserva el diagnóstico.

## Outputs, cache y reanudación

El CLI scripts/run_sentinel2_dnbr.py escribe:

- data/interim/sentinel2_dnbr_event_metrics.csv
- data/interim/sentinel2_dnbr_errors.csv
- data/interim/sentinel2_dnbr_checkpoint.json
- outputs/sentinel2_dnbr_report.json
- outputs/sentinel2_dnbr_report.md
- outputs/sentinel2_dnbr_sensitivity.csv
- outputs/sentinel2_dnbr_review_queue.csv
- outputs/figures/sentinel2_dnbr/events/

La cache por evento contiene una firma con versión, escenas, política, AOI,
resolución, umbrales, modos, fórmulas y contrato de soporte. El cambio a
`fuegopa-sentinel2-dnbr-v3` invalida las cachés y filas v2: se reconstruyen con
la definición compartida de soporte y no se mezclan 22 resultados v2 con seis
resultados v3. Solo una cache con quicklook presente
se considera completada. resume omite únicamente éxitos compatibles; un
evento fallido no tiene cache de éxito y vuelve a intentarse. overwrite exige
confirmación y reemplaza solo los event_id seleccionados. Los CSV, JSON,
caches, thumbnails y tracebacks están ignorados por Git. Escrituras de
outputs y checkpoints son atómicas.

El review queue contiene los 28 eventos procesables. Sus campos
visible_burn_scar, scar_confidence, competing_land_change, reviewer_notes y
review_status se dejan vacíos para revisión humana posterior. No se genera
significant_burn.

## Flujo de ejecución

1. Ejecutar pruebas unitarias sin red.
2. Ejecutar el smoke test de Earth Engine.
3. Ejecutar un event_id y auditar métricas y quicklook.
4. Ejecutar tres eventos.
5. Ejecutar los 28 con resume.

La implementación actual no debe saltar del segundo paso al lote completo.

## Limitaciones

dNBR es una medida espectral dependiente de fechas, máscaras, resolución,
fenología, humedad, atmósfera, sombras, mezcla de píxeles, regeneración y
cambios de uso del suelo. No identifica por sí sola causa, perímetro, duración
ni severidad operativa. Una ausencia de solapamiento óptico no es ausencia de
quema. Cualquier futura etiqueta deberá incorporar revisión humana y una
definición independiente de observabilidad, área y evidencia compatible con
quema.

## Quicklook v2 local — 21 de julio de 2026

La composición v2 está separada del compositor v1 y se describe en
`docs/QUICKLOOK_V2_DESIGN.md`. Usa el contrato explícito
`fuegopa-dnbr-quicklook-v2`, paneles RGB de 2048 × 1440, fuente TrueType del
sistema y únicamente los seis PNG y métricas locales ya existentes. No
consulta Earth Engine ni reescribe outputs científicos. `window_median` se
compara en una hoja `metrics only` porque no existe un raster numérico local;
el rango diagnóstico `[-0.25, 0.50]` y false-color SWIR quedan diferidos a
Level 2.
