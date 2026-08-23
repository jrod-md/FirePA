# Checkpoint de calibración humana — 2026-07-21

## Alcance ejecutado

Esta sesión comenzó después de:

    aecd56be0595c8765a8cff286a8733e5a34ae64f

La entrega prepara un borrador de protocolo, una cola ciega vacía, una tabla
separada de no observables, un manifest, instrucciones, un validador y pruebas.
No consulta Earth Engine y no cambia datos científicos.

El commit creado para esta entrega tiene el mensaje exacto:

    Prepare blinded human-review calibration protocol

El SHA final se verifica con git después de crear el commit. El checkpoint forma
parte del mismo commit y por eso no se inserta una referencia auto-referencial
a su propio SHA.

## Orden ciego

Semilla: 20260721.

Algoritmo: random.Random(seed).shuffle sobre los siete IDs congelados en orden
lexicográfico antes de mezclar.

| randomized_order | event_id |
|---:|---|
| 1 | event-r1500_t06-0ddd477d24b1364d |
| 2 | event-r1500_t06-ef20fd746737f4ea |
| 3 | event-r1500_t06-040b1a186d857b11 |
| 4 | event-r1500_t06-09c2d54e2d8fb5dd |
| 5 | event-r1500_t06-9e5bf1d807f9d61a |
| 6 | event-r1500_t06-84cb252a6877d2d5 |
| 7 | event-r1500_t06-548ca9e284d1a330 |

Cada fila referencia exactamente un panel
selected_pair_cs050_level2_panel.png y un panel
temporal_robustness_level2.png bajo outputs/review_upload_level2/.

## Esquema y valores

La cola usa estos campos:

    calibration_round
    randomized_order
    event_id
    reviewer_id
    reviewed_at
    protocol_version
    quicklook_version
    multispectral_panel_path
    temporal_panel_path
    visible_burn_scar
    scar_confidence
    event_association
    competing_land_change
    mode_agreement
    reviewer_notes
    review_status
    exclusion_reason
    adjudication_notes

Los enums completos están en docs/LABELING_PROTOCOL_DRAFT_v1.md. La cola
inicial contiene siete filas, todas pending, con los campos de revisión vacíos.
No contiene FRP, confianza FIRMS, dNBR median/p90, áreas, expected class,
model_score, predicted_class ni significant_burn.

La tabla outputs/human_review/unobserved_events.csv contiene únicamente:

    event_id
    observability_status
    exclusion_reason
    protocol_version
    significant_burn

Sus dos filas son event-r1500_t06-1f8f72e78d63b0ee y
event-r1500_t06-ab8e9016ae0d3154, ambas unobserved por
no_usable_pre_scene_in_any_combination;clear_fraction_below_threshold.
significant_burn permanece vacío. No están en la cola principal y no se
interpretan como negativos. En la semántica del protocolo, unobserved equivale
a visible_burn_scar=unobserved y review_status=unobserved para este registro
separado; no se duplican esas dos columnas porque su esquema está limitado a
los cinco campos indicados.

## Archivos creados

Documentación:

- docs/LABELING_PROTOCOL_DRAFT_v1.md
- docs/HUMAN_REVIEW_CALIBRATION_CHECKPOINT_2026-07-21.md

Cola y esquema locales, fuera del commit por la política de outputs ignorados:

- outputs/human_review/calibration_round1_blinded.csv
- outputs/human_review/calibration_round1_manifest.json
- outputs/human_review/calibration_round1_instructions.md
- outputs/human_review/unobserved_events.csv

Código y pruebas:

- scripts/validate_human_review.py
- tests/test_human_review_protocol.py

## Preflight, pruebas e integridad

- Branch inicial: master.
- HEAD inicial: aecd56be0595c8765a8cff286a8733e5a34ae64f.
- Estado inicial: sin diff ni staged; solo permanecían archivos no relacionados
  sin seguimiento en data/, docs/HANDOFF_FIREPA_2026-07-21.md y notebooks/.
- Suite completa preflight: 170 passed en el entorno fuegopa.
- Pruebas nuevas de protocolo y validador: 20 passed.
- La cola vacía pasó:
  scripts/validate_human_review.py --check-empty-calibration.
- Earth Engine: cero consultas en esta sesión.

Hashes registrados antes de modificar el árbol y confirmados después de la
implementación:

| Artefacto | Antes | Después |
|---|---|---|
| índice científico del bundle activo | 249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa | 249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa |
| manifest Level 2 firepa_quicklook_level2.sha256 | 9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705 | 9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705 |
| índice visual v1 | ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401 | ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401 |
| snapshot protegido de revisión | 3d91273adc82b7df6fbfd7508363b90f70423b9d11ba65d4b9da70b1156c7793 | 3d91273adc82b7df6fbfd7508363b90f70423b9d11ba65d4b9da70b1156c7793 |

La comprobación científica reportó cero cambios en 179 entradas y cero cambios
visuales en 231 entradas. El snapshot protegido ya mostraba antes de esta
sesión la ausencia de outputs/firepa_quicklook_v2_review.zip; no se recreó ni
se modificó ese ZIP histórico.

No se modificaron FIRMS, clustering, piloto, inventarios, selección de escenas,
métricas dNBR, sensibilidad, caches, checkpoints, errores, rasters Level 2 ni
paneles Level 2. No se usaron datos 2026, no se crearon etiquetas, no se
definió significant_burn y no se hizo push.

## Estado Git y siguiente paso humano

Después del commit deben permanecer únicamente los archivos no relacionados
preexistentes en data/, docs/HANDOFF_FIREPA_2026-07-21.md y notebooks/. Los
artefactos de outputs/human_review siguen fuera del commit por ser outputs
ignorados.

El siguiente paso humano es revisar los siete eventos en randomized_order,
completar una copia de la cola, ejecutar el validador y decidir si el borrador
debe revisarse. El protocolo no está congelado, la ronda no es validación y
todavía no corresponde crear significant_burn, baseline, predictores, modelo ni
pitch.
