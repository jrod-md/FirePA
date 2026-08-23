# FirePA Quicklook v2.1 checkpoint — 2026-07-21

## Alcance congelado

Quicklook v2.1 es una corrección visual y de metadata sobre el bundle PNG v1 existente. No modifica métricas científicas, CSV, selección de escenas, cache, checkpoint, cohorte, fórmula, AOI, política Sentinel-2 ni el contrato dNBR. No ejecuta Earth Engine, no crea `significant_burn`, no inicia calibración humana, no sobrescribe v1/v2 y no hace push.

La ejecución local cubre exactamente los siete eventos de calibración y escribe 14 PNG nuevos: un panel principal y una hoja temporal por evento.

## Causa visual confirmada

La auditoría del código local confirma que la máscara v1 se renderiza con `unmask(0)` y la paleta `['c026d3', '0f766e']`:

- `#c026d3` — valor 0: máscara inválida/no disponible.
- `#0f766e` — valor 1: máscara válida.
- `#ffd166` — borde del AOI.
- `#00e5ff` — overlay de detección FIRMS.
- `#94a3b8` — nodata/fondo de capas RGB/NBR/dNBR; no es una categoría de máscara.

El panel v2.1 conserva la máscara con nearest-neighbor y muestra la leyenda completa. La leyenda ya no presenta el gris como `INVALID`.

## Correcciones de metadata y terminología

- Las distancias de la pareja seleccionada se muestran como `PRE LEAD` y `POST LAG`, con sus definiciones temporales explícitas.
- El card `SELECTED_PAIR` muestra `PRE SCENE` y `POST SCENE`.
- El card `WINDOW_MEDIAN` no reutiliza las fechas de la pareja seleccionada.
- Cuando están disponibles localmente, el card de ventana muestra inicio/fin de cada ventana, conteo de escenas y la existencia de IDs en metadata PNG. Los límites se derivan de los candidatos del inventario local y los conteos/IDs de la fila `window_median`.
- Si faltan límites o metadata local completa, el card usa exactamente: `COMPOSITE WINDOW METADATA: unavailable locally` y `metrics only; no local window_median raster is available`.
- La interpretación permanece descriptiva: `Positive dNBR: spectral vegetation loss` y `Negative dNBR: spectral vegetation gain`. Esto no constituye confirmación de fuego ni etiqueta de severidad.

## Salidas nuevas

- `outputs/figures/sentinel2_dnbr_v2_1/events/`
- `outputs/review_upload_v2_1/`
- `outputs/quicklook_v2_1_report.json`
- `outputs/quicklook_v2_1_report.md`

El código reproducible es `scripts/run_dnbr_quicklook_v2_1.py` y el compositor es `src/fuegopa/dnbr_quicklook_v2_1.py`. Las rutas v1 y v2 quedan fuera de escritura.

## Integridad registrada

Reporte generado con `fuegopa-dnbr-quicklook-v2.1`:

- Generados: `7/7`; fallidos: `0`.
- Cambios en bundle científico según manifest: `0`.
- Cambios en outputs protegidos (CSV, selección, cache, checkpoint, v1/v2): `0`.
- Consultas Earth Engine: `false`.
- Métricas/CSV/JSON científicos modificados: `false`.
- Human review iniciado: `false`.
- `significant_burn` creado: `false`.

Índices SHA-256 before/after:

| índice | before | after |
|---|---|---|
| bundle científico | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` |
| visual v1 del manifest | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` |
| artefactos protegidos | `de2e2072431b7b1f64e6ef50dae043ca624473a988eeb245bcd6558224620723` | `de2e2072431b7b1f64e6ef50dae043ca624473a988eeb245bcd6558224620723` |

El manifest científico usado fue `outputs/manifests/firepa_active_bundle_2026-07-21.json`, con commit base `855063de4036f369fd298b0f942adc064ff54df0`.

## Validación

- `tests/test_dnbr_quicklook_v2_1.py`: 10 pruebas dirigidas pasaron.
- Suite completa: `165 passed in 105.62s (0:01:45)`.
- La inspección visual de los eventos con máscara inválida confirmó magenta visible, teal válido, borde amarillo y leyenda gris limitada a capas espectrales.
- La inspección visual de la hoja temporal confirmó ventanas locales `PRE WINDOW`/`POST WINDOW`, conteos de escenas y ausencia de fechas de pareja seleccionada dentro del card de ventana.
- La calibración humana sigue pendiente y no fue iniciada por este checkpoint.

## Entrega Git

La entrega solicitada es un commit local, sin push, con mensaje `Fix Quicklook v2 review metadata and mask legend`. El hash final se reporta en el handoff después de crear el commit.
