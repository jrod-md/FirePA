# Contrato `window_median` para asset de revisión v1

**Versión:** `firepa-window-median-review-asset-v1`
**Estado:** congelado para el piloto técnico `calibration-7` después de
`pilot_pass`
**Fecha:** 2026-07-30
**Unidad de análisis:** un evento provisional `r1500_t06`.

## Propósito y límites

Este contrato define un asset visual y numérico descriptivo para inspeccionar
la estabilidad temporal de la evidencia Sentinel-2 en siete casos de
calibración. `window_median` no es ground truth, no es severidad, no es una
etiqueta de quema y no confirma un incendio. Tampoco sustituye
`selected_pair`: ambos son modos de evidencia separados y no se pueden
intercambiar por sus nombres de archivo, métricas o paneles.

El piloto no inicia la revisión formal de 28 eventos, no crea asignaciones, no
calcula `significant_burn`, no entrena modelos y no cambia la cohorte, la
política Sentinel-2 ni el contrato dNBR v3.

## Definición científica congelada

Para cada ventana se reúnen todas las escenas utilizables que ya están en el
inventario congelado. Se aplica la misma máscara de B8/B12 y Cloud Score+
`cs_cdf >= 0.50`. La composición se calcula como mediana por píxel y por banda
de reflectancia, de forma independiente para pre y post. Después se calcula:

```text
NBR = (B8 - B12) / (B8 + B12)
dNBR = NBR_pre - NBR_post
```

No se calcula una mediana de dNBR individuales ni una mediana posterior de
varios NBR si antes se dispone de la mediana de reflectancias. Las funciones
puras `reflectance_median_per_band`, `nbr_from_reflectance` y
`dnbr_from_composites` en `src/fuegopa/window_median_review_asset.py` dejan
esta secuencia testeable. Los siete GeoTIFF usados por el piloto son los
bundles Level 2 ya exportados y reconciliados; este paso no los reescribe ni
vuelve a consultar Earth Engine.

## Política y procedencia

La política es exactamente la ya vigente:

- periodo científico: 2025;
- Sentinel-2: `COPERNICUS/S2_SR_HARMONIZED`;
- Cloud Score+: `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`;
- AOI: `detection_union_buffer`, `b0500`, 500 m;
- escala analítica: 20 m;
- CRS: `EPSG:32617`;
- regla A, `pre30_post45` como combinación principal;
- fallback temporal único: `pre30_post90`, regla A;
- no existe fallback adicional de buffer;
- bandas: reflectancia B2, B3, B4, B8A, B8 y B12; RGB B4/B3/B2;
  false-color B12/B8A/B4;
- resampling científico no se cambia; el panel usa bilinear solo para la
  presentación RGB y vecino más cercano para capas numéricas y máscara.

Los siete eventos son, en el orden de alias QA, los siete IDs históricos de
calibración definidos en `quicklook_level2.CALIBRATION_EVENT_IDS`. El caso
`CASE-007` (`event-r1500_t06-09c2d54e2d8fb5dd`) conserva el fallback temporal.
Todos los scene IDs usados son de 2025. Las fechas de creación de archivos de
auditoría no son datos de observación.

La clasificación previa a la generación fue `A_local_exact` para los siete
casos: existen los nueve GeoTIFF `window_median` por evento, sus sidecars
Level 2, las filas históricas, los inventarios y los paneles `selected_pair`
de referencia. No se hicieron consultas Earth Engine ni descargas raster en
esta fase.

## Bundle raster y máscaras

Cada sidecar enumera y hashea estas nueve piezas, sin duplicarlas bajo el
output nuevo:

```text
aoi_support
common_valid_mask
rgb_pre
rgb_post
false_color_pre
false_color_post
nbr_pre
nbr_post
dnbr
```

Los rasters comparten CRS, transform, dimensiones y grilla de 20 m. Las capas
de reflectancia son `uint16` con nodata 0; NBR/dNBR son `float32` con nodata
-9999; soporte y máscara son `uint8` con nodata 0. El soporte AOI es la base
del denominador. La métrica `common_valid_pixel_count` se calcula sobre la
intersección `common_valid_mask AND aoi_support`, por lo que el numerador y el
denominador permanecen en el mismo soporte raster.

La exportación local disponible contiene una máscara válida común, pero no
rasters separados de validez pre y post. El contrato lo registra como
`pre_post_valid_masks.pre=null` y `.post=null`; no se fabrican máscaras a
partir de la común. El panel muestra la máscara común y distingue nodata en
gris. La geometría AOI y su área se conservan como procedencia descriptiva.

## Sidecar y nombres

El sidecar por caso está en:

```text
outputs/window_median_review_asset_v1/assets/<event_id>/
  <event_id>_window_median_cs050_sidecar.json
```

Registra identidad privada del evento y alias QA, modo, configuración, policy
path/fallback, ventanas, scene IDs y counts, colección, Cloud Score+, AOI,
escala, CRS, transform, dimensiones, nodata, dtype, bandas, fórmula, hashes
de cada raster, hash del bundle, hash de procedencia, timestamp de creación,
commit de código y `earth_engine_project_identifier=null`. No contiene
tokens, credenciales ni claves.

El panel obligatorio está en:

```text
outputs/window_median_review_asset_v1/qa/calibration_7/
  <event_id>_window_median_cs050_review_panel.png
```

El PNG es RGB autocontenido de 2048 x 1440. Tiene las dimensiones, tipografía,
layout, orientación, overlay de detecciones y escala del panel Level 2. Usa
rangos fijos compartidos: RGB reflectancia `[0, 3000]`, false-color stretch
global P2/P98 ya congelado, dNBR global `[-1, 1]` y dNBR diagnóstico
`[-0.25, 0.50]`, centrado en cero en la paleta. No hace auto-stretch por
evento. Las etiquetas `WINDOW MEDIAN`, `PRE COMPOSITE` y `POST COMPOSITE` son
obligatorias. No muestra FRP, confianza, ranking, scores, clase predicha,
target, `significant_burn`, severidad ni resultados de revisión humana o IA.

## QA y comparación histórica

El generador rechaza raster ausente/vacío, hash incorrecto, CRS, transform,
grilla, dimensiones, bandas, dtype o nodata incompatibles; masks no binarias;
datos de 2026; scene counts cero; hashes o rutas confundidas entre modos; PNG
uniforme, predominantemente verde, con alpha o ilegible; y campos prohibidos.
El verificador `scripts/verify_window_median_review_asset.py` es read-only.

La referencia numérica son las filas históricas `window_median` del pipeline
dNBR v3, no ground truth. Se usa una sola tabla de tolerancias para los siete
casos:

| Métrica | Tolerancia |
|---|---:|
| `valid_overlap_fraction` | 0.005 |
| `common_valid_pixel_count` | 16 píxeles |
| `dnbr_median`, `dnbr_p90` | 0.005 |
| áreas dNBR > 0.10/0.20/0.30/0.40 | 0.50 ha |
| `pre_nbr_median`, `post_nbr_median` | 0.005, reutilizada de la tolerancia escalar dNBR |

Se reportan valor histórico, valor local, diferencia absoluta, diferencia
relativa, tolerancia y estado por métrica. Cualquier discrepancia material
detendría la congelación. El piloto real produjo `pilot_pass`: 7/7 bundles y
paneles pasaron, con máximo cociente diferencia/tolerancia 0.527899 para
`event-r1500_t06-0ddd477d24b1364d`; no hubo fallos.

## QA visual y versionado

El paquete separado contiene un manifest canónico, sidecars, siete paneles
`window_median`, las siete referencias `selected_pair` por ruta y hash, un
contact sheet comparativo, y reportes JSON/Markdown. Los outputs están
ignorados por Git. El manifest no se registra en `formal_review_28`, no cambia
el índice científico v1 y no autoriza ejecución.

El estado administrativo continúa siendo `prepared/not_started` con
`execution_authorized=false`, cero perfiles, cero revisiones y cero Pass A/B.
La próxima fase deberá decidir explícitamente si se conectan assets reviewer-
facing a una ronda formal; este piloto no lo hace.

Comandos reproducibles, siempre en el entorno `fuegopa`:

```powershell
python scripts/build_window_median_review_asset.py --case-set calibration-7 --no-earth-engine
python scripts/verify_window_median_review_asset.py --case-set calibration-7
python scripts/build_window_median_review_asset.py --case-set calibration-7 --verify-only --no-earth-engine
```

`--dry-run` compone y valida en memoria sin escribir; `--resume` omite solo
identidades existentes cuyos hashes coinciden. Una identidad con bytes
distintos produce un conflicto explícito.
