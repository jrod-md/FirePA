# Checkpoint FirePA — dNBR v3 y Quicklook v2 — 21 de julio de 2026

## Alcance y límites

Este checkpoint cierra la congelación científica local dNBR v3 y el Nivel 1
visual para siete casos de calibración. No abre revisión humana, no crea
etiquetas, no cambia clustering, no incorpora datos de 2026, no ejecuta nuevas
consultas Earth Engine y no publica un modelo o dashboard.

## Estado Git y commits

- Rama: `master`.
- HEAD inicial de esta ejecución: `855063de4036f369fd298b0f942adc064ff54df0`.
- Congelación dNBR v3: `13f3b39cdd88d6929e5a7058a1bdfd7f341d294f`,
  `Add reproducible Sentinel-2 dNBR v3 pipeline`.
- Quicklook v2: `9b203bb0f61e5d3dc5f36ca1fc3d8a9343a38e7f`,
  `Add human-review dNBR quicklook v2`.
- La documentación de este checkpoint se cierra en un commit local separado;
  su hash completo queda registrado en el handoff final de Git junto con el
  estado de staging. No se hace push.

## Archivos modificados por esta entrega

El commit v2 contiene únicamente:

- `src/fuegopa/dnbr_quicklook_v2.py`;
- `scripts/run_dnbr_quicklook_v2.py`;
- `tests/test_dnbr_quicklook_v2.py`;
- `docs/QUICKLOOK_V2_DESIGN.md`;
- la sección v2 de `docs/SENTINEL2_DNBR_DESIGN.md`.

El commit documental contiene `PLAN.md`, `CONTEXT.md`, `README.md`,
`docs/PREFLIGHT.md` y este archivo. `docs/HANDOFF_FIREPA_2026-07-21.md`,
datasets, notebooks, `.gitkeep`, caches y outputs previos se preservan fuera
de esos commits.

## Validación ejecutada

- Entorno dedicado: Python 3.12.13 del entorno local `fuegopa`.
- Recolección inicial: 138 pruebas; suite final: 155 pruebas.
- Suite específica v2: `17 passed in 69.01s`.
- Suite completa directa: `155 passed in 81.49s`.
- Wrapper oficial con el entorno dedicado en `PATH`: `155 passed in 84.07s`.
- `git diff --check`: sin errores.
- No se añadieron dependencias Python. La fuente tipográfica es Arial TrueType
  del sistema, rasterizada por GDI en Windows;
  no se copia al repositorio.

## Manifest e integridad

El manifest activo local es:

```text
outputs/manifests/firepa_active_bundle_2026-07-21.sha256
outputs/manifests/firepa_active_bundle_2026-07-21.json
outputs/manifests/firepa_active_bundle_2026-07-21.md
```

Fue capturado con 427 entradas: 179 científicas, 231 visuales v1 y el resto
de código, pruebas y documentación. La revalidación posterior a Quicklook v2
dio:

| Índice | Antes | Después | Cambios |
| --- | --- | --- | ---: |
| científico | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | 0 |
| visual v1 | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | 0 |

También quedaron en cero las entradas científicas cambiadas, las entradas
visuales v1 cambiadas, los archivos científicos modificados y los checkpoints
modificados. La comprobación usa bytes de los archivos enumerados por el
manifest; no interpreta colores PNG como datos científicos.

## Quicklook v2 generado

Los siete `event_id` son:

```text
event-r1500_t06-0ddd477d24b1364d
event-r1500_t06-84cb252a6877d2d5
event-r1500_t06-ef20fd746737f4ea
event-r1500_t06-9e5bf1d807f9d61a
event-r1500_t06-548ca9e284d1a330
event-r1500_t06-040b1a186d857b11
event-r1500_t06-09c2d54e2d8fb5dd
```

Rutas exactas de salida:

```text
outputs/figures/sentinel2_dnbr_v2/events/<event_id>_selected_pair_cs050_panel_v2.png
outputs/figures/sentinel2_dnbr_v2/events/<event_id>_temporal_comparison_v2.png
outputs/review_upload_v2/<event_id>_selected_pair_cs050_panel_v2.png
outputs/review_upload_v2/<event_id>_temporal_comparison_v2.png
outputs/quicklook_v2_report.json
outputs/quicklook_v2_report.md
```

Se verificaron 14 PNG en cada ruta de figuras/subida, todos RGB, sin alpha,
de 2048 × 1440. El panel principal usa `selected_pair`, rangos visuales fijos
`[-1, 1]`, máscara válida, detecciones FIRMS, centroides, AOI, barra de escala,
fechas, política principal o fallback, solapamiento y métricas descriptivas.
La comparación reporta `selected_pair` frente a `window_median`; este último
queda marcado `metrics only` y no tiene un raster numérico local sustituto.

El reporte v2 confirma `requested=7`, `generated=7`, `failed=0`,
`earth_engine_queries_made=false`, `scientific_outputs_modified=false` y
`human_review_started=false`. Los dos casos no observables siguen excluidos:

```text
event-r1500_t06-1f8f72e78d63b0ee
event-r1500_t06-ab8e9016ae0d3154
```

No se detectaron fechas de evento o escena en 2026; las fechas actuales del
reporte son metadatos de ejecución.

## Mejoras locales y decisiones diferidas

Quicklook v2 mejora la legibilidad y auditabilidad del panel, valida las seis
fuentes locales antes de escribir, separa claramente los modos y registra la
integridad de bundle. El remapeo diagnóstico dNBR `[-0.25, 0.50]` se omite
porque no hay raster numérico local trazable. El false-color SWIR se difiere
porque no hay una traza local completa B12/B8A/B4. No se reconstruyen índices a
partir de los colores de los PNG.

Level 2 requiere decidir y auditar una fuente numérica trazable, posiblemente
mediante una nueva ejecución Earth Engine, para producir esas capas. También
requiere revisión humana de los 28 eventos, protocolo de calibración, criterio
de observabilidad, `significant_burn`, severidad, variables ambientales,
baseline, partición, métricas y modelo. Nada de eso se marca como completado en
este checkpoint.

## Reproducción exacta

Desde la raíz del repositorio y el entorno `fuegopa`:

```powershell
python scripts/run_dnbr_quicklook_v2.py
python -m pytest -q -p no:cacheprovider
.\scripts\run_tests.ps1
```

La primera línea recompone solo los siete eventos autorizados y escribe los
outputs v2 ignorados por Git. No ejecutar el CLI dNBR v3 para esta validación:
la congelación científica ya está registrada y sus hashes fueron revalidados.
