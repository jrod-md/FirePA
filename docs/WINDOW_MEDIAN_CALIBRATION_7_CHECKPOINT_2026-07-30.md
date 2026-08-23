# Checkpoint: piloto `window_median` de siete casos

**Estado:** `pilot_pass`
**Base HEAD verificado:** `e2c50e2428fe94cf9db283a5bcf95c7fd9edc449`
**Commit de código registrado en los sidecars:** el mismo Base HEAD
**Fecha del checkpoint:** 2026-07-30
**Earth Engine:** 0 consultas; 0 descargas en esta fase.

## Alcance

Se congeló el contrato `firepa-window-median-review-asset-v1` para los siete
casos históricos de calibración. El paquete es local, separado de los
outputs científicos, y no está conectado a `formal_review_28`. La ronda sigue
`prepared/not_started` con `execution_authorized=false`, 0 perfiles, 0
revisiones, 0 Pass A y 0 Pass B.

No se modificaron escenas, AOI, ventanas, máscara, Cloud Score+, colección,
clustering, cohorte, métricas dNBR v3 ni paneles `selected_pair`. No se
calcularon nuevos NBR/dNBR: se reutilizaron los nueve GeoTIFF
`window_median` locales ya exportados y reconciliados.

## Método congelado

La unidad de análisis es el evento provisional `r1500_t06`. Para pre y post
se utilizan todas las escenas utilizables de la ventana existente, con la
misma máscara B8/B12 y Cloud Score+ `cs_cdf >= 0.50`. La mediana se toma por
píxel y banda de reflectancia; luego NBR y finalmente `dNBR = NBR_pre -
NBR_post`. No se toma la mediana de dNBR individuales.

La política conserva periodo 2025, AOI `b0500`/500 m, 20 m, `EPSG:32617`,
regla A, `pre30/post45` principal y `pre30/post90` como fallback temporal
único. `event-r1500_t06-09c2d54e2d8fb5dd` es el único caso con fallback. Las
escenas pre/post son 2025.

## Casos y escenas

| Alias | Evento | Pre | Post | Fallback | Advertencias estructuradas |
|---|---|---:|---:|---|---|
| CASE-001 | `event-r1500_t06-0ddd477d24b1364d` | 2 | 5 | no | `CLOUD_OR_HAZE` |
| CASE-002 | `event-r1500_t06-84cb252a6877d2d5` | 2 | 6 | no | `CLOUD_OR_HAZE` |
| CASE-003 | `event-r1500_t06-ef20fd746737f4ea` | 4 | 7 | no | `CLOUD_OR_HAZE` |
| CASE-004 | `event-r1500_t06-9e5bf1d807f9d61a` | 4 | 2 | no | `MASK_OR_NODATA`, `CLOUD_OR_HAZE` |
| CASE-005 | `event-r1500_t06-548ca9e284d1a330` | 3 | 5 | no | `CLOUD_OR_HAZE` |
| CASE-006 | `event-r1500_t06-040b1a186d857b11` | 5 | 1 | no | `SCENE_COUNTS_LOW`, `MASK_OR_NODATA`, `CLOUD_OR_HAZE` |
| CASE-007 | `event-r1500_t06-09c2d54e2d8fb5dd` | 3 | 4 | sí | `FALLBACK_TEMPORAL`, `CLOUD_OR_HAZE` |

Las advertencias derivan únicamente de campos estructurados de inventario y
métricas. No se escogió ningún caso por FRP, contraste, tamaño aparente o
conveniencia visual.

## Reconciliación histórica

La referencia son las 28 filas históricas `window_median` del pipeline v3,
no ground truth. Tolerancias únicas y predeclaradas:

| Métrica | Tolerancia |
|---|---:|
| `valid_overlap_fraction` | 0.005 |
| `common_valid_pixel_count` | 16 píxeles |
| `dnbr_median`, `dnbr_p90` | 0.005 |
| cuatro áreas dNBR | 0.50 ha |
| `pre_nbr_median`, `post_nbr_median` | 0.005 |

La tabla siguiente muestra histórico → recalculado local y la diferencia
principal; el JSON contiene todas las áreas, diferencias relativas y estados.

| Alias | Overlap | Common pixels | dNBR median (diff) | dNBR p90 (diff) | Máx. diff/tolerancia |
|---|---|---|---|---|---:|
| CASE-001 | 1.000000 → 1.000000 | 2971 → 2973 | 0.205108 → 0.204557 (0.000551) | 0.341518 → 0.339986 (0.001532) | 0.527899 |
| CASE-002 | 1.000000 → 1.000000 | 4496 → 4498 | 0.302662 → 0.304029 (0.001367) | 0.668309 → 0.668637 (0.000328) | 0.334182 |
| CASE-003 | 1.000000 → 1.000000 | 8598 → 8599 | 0.079873 → 0.080358 (0.000485) | 0.244131 → 0.243717 (0.000414) | 0.455383 |
| CASE-004 | 0.935670 → 0.935237 | 1834 → 1834 | 0.037424 → 0.038627 (0.001203) | 0.162176 → 0.163489 (0.001313) | 0.294721 |
| CASE-005 | 1.000000 → 1.000000 | 4073 → 4074 | 0.091811 → 0.092100 (0.000290) | 0.200897 → 0.200134 (0.000763) | 0.282330 |
| CASE-006 | 0.937192 → 0.938202 | 1837 → 1837 | -0.009982 → -0.008125 (0.001857) | 0.134844 → 0.133941 (0.000902) | 0.371412 |
| CASE-007 | 1.000000 → 1.000000 | 1960 → 1965 | -0.107522 → -0.108139 (0.000617) | 0.041220 → 0.042113 (0.000893) | 0.320542 |

Todas las áreas descriptivas, NBR medians, overlap y conteos también pasan.
El máximo cociente observado es 0.527899, menor que 1. No hubo cambio
material de cobertura, signo principal u orden de magnitud.

## Hashes de paneles y bundles

| Alias | Panel PNG SHA-256 | Bundle raster SHA-256 |
|---|---|---|
| CASE-001 | `e153c34a9581d3483928955796aa4fe696018742c909bae7215f2fd52373e780` | `f30da6af616d1e3a8f7e5a1d3893fd12ffc4f6c95f468046b8f6ca94b65a9ab3` |
| CASE-002 | `48f708b6de158214aa2aeff6839c1c18b5af6be9ccce6ea6fa81e8a952045ea5` | `194759930a7be628a9b01646a1b65eb957c4c136431a812ad7e4362037eb080b` |
| CASE-003 | `aed79bc266e13f85817098cce84f37d6bfc2bed935d9e51abb0e38b849dd1227` | `cb25989ab4eb3f05e4cf9f43dbdb20f17d05709de2220a87dd2ed530bb8ba30d` |
| CASE-004 | `cd2531f549a05a5e73dad165ee81c46cfcea392ee767091ce76aaebec2eb5dd6` | `363be74e5734383a472f6d75ee06f6c78701d15d16bb8612181b8fb8f83f08ef` |
| CASE-005 | `d4d5a6434e09f76d543ad7f04a0a914499aa96554eb83e2e0640e846e814d940` | `ef016553b06a4de47d40622e3caa6d20a716c5484d89ae61dd0cefce89b1ae03` |
| CASE-006 | `fc989136ee018e979c6f3b1a0185debf7842f1973b786dd04bc8e6f8df2f0ca1` | `6be4d48160ad1de8ad5eec7c3a8344c012102fc3bd7c3d5a0f95ec38dfb8b27c` |
| CASE-007 | `c7cc94eaeb08be1604980e4be6dcd816cb8aaaa2b2251d010fb27b69146cc12a` | `73808b702322a0967fc60188f2aec3545471b33d5575081a1e27672d797d432f` |

Los siete sidecars incluyen hashes individuales de las nueve piezas raster,
hash de procedencia, AOI, grilla y `earth_engine_project_identifier=null`.

## QA e integridad

Outputs locales:

```text
outputs/window_median_review_asset_v1/window_median_review_asset_manifest.json
outputs/window_median_review_asset_v1/qa/calibration_7/manifest.json
outputs/window_median_review_asset_v1/qa/calibration_7/report.json
outputs/window_median_review_asset_v1/qa/calibration_7/report.md
outputs/window_median_review_asset_v1/qa/calibration_7/calibration_7_selected_pair_vs_window_median_contact_sheet.png
```

El panel PNG es RGB autocontenido, no usa alpha científico, conserva rangos
fijos, colorbars, nodata gris y etiquetas explícitas de modo. El contact sheet
compara los siete paneles `selected_pair` existentes con los siete nuevos a la
misma escala visual; los paneles existentes solo se referencian por path/hash.

Hashes protegidos antes/después:

| Índice | SHA-256 | changed_count |
|---|---|---:|
| Bundle científico | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | 0 |
| Índice visual científico v1 | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | 0 |

El verificador read-only devolvió `status=pass`, 7 eventos, 0 errores,
`earth_engine_queries_made=false`, `execution_authorized=false`, Pass A=0 y
Pass B=0.

## Pruebas y Git

Antes de modificar había `262 passed`. El nuevo módulo añade diez pruebas
unitarias en `tests/test_window_median_review_asset.py`; esa prueba específica
pasó `10 passed`. La suite completa posterior pasó `272 passed` en 8:26.
`git diff --check` permanece sin errores.

Se versionan solamente código, tests y documentación. `data/`, `outputs/`,
rasters, PNG, caches, SQLite y los ocho untracked históricos quedan fuera de
Git. No se hace push. El commit solo es válido si el estado sigue siendo
`pilot_pass` y la lista staged es explícita.

## Limitaciones

El paquete demuestra reproducibilidad local de siete bundles ya existentes, no
valida que dNBR sea ground truth ni prueba capacidad predictiva. La ausencia
de máscaras pre/post separadas limita esa auditoría específica. La muestra de
siete no representa automáticamente los 28 ni los 611 eventos. Nubes, bruma,
agricultura, fenología, humedad, suelo expuesto, agua, sombras y cambios de uso
pueden producir señales competidoras. Cualquier uso reviewer-facing futuro
requiere una decisión separada y no queda autorizado por este checkpoint.
