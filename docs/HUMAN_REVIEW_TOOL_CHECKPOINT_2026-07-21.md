# Checkpoint de herramienta de revisión humana — 2026-07-21

## Alcance

Esta entrega comienza después de `2387b46a9974d29862ac5d9b11ab9cb1caeabcdf`
(`Prepare blinded human-review calibration protocol`). Añade una herramienta
local y auditable para revisar los siete paneles Level 2 sin abrir una nueva
fase científica.

El commit de esta entrega usará exactamente el mensaje:

    Add structured local human-review tool

El SHA final se verifica con Git después de crear el commit y se reporta fuera
de este archivo; el checkpoint no se auto-referencia.

## Arquitectura y datos

La interfaz es Streamlit (`scripts/run_human_review_app.py`) y el estado es una
base `sqlite3` local creada por `src/fuegopa/human_review_store.py`. El DDL y
los enums están en `src/fuegopa/human_review_schema.py`. La inicialización lee
la cola ciega `calibration_round1_blinded.csv`, su manifest y la tabla
`unobserved_events.csv`; valida el orden congelado y es idempotente.

Tablas implementadas:

- `review_rounds`: ronda, protocolo, quicklook, semilla, creación y estado.
- `review_items`: exactamente siete items observables, sus rutas de panel y
  `randomized_order`; triggers protegen el orden.
- `reviews`: clave primaria `(round_id, event_id, reviewer_id)` y columnas
  separadas `pass_a_*`/`pass_b_*`, timestamps, revisiones, estado y notas.
- `audit_log`: historial append-only por campo con valor anterior/nuevo y
  razón; `UPDATE` y `DELETE` son rechazados por SQLite.
- `unobserved_events`: los dos casos no observables, fuera de la cola y sin
  posibilidad de revisión en la aplicación.

No existe una columna de etiqueta, score, clase o resultado científico en la
base. Los códigos internos son los seis vocabularios definidos por el
protocolo; las etiquetas explicativas de los dropdowns no se almacenan.

## Flujo A/B y restricciones de UI

1. Reviewer ID obligatorio; el progreso y el orden son administrativos.
2. Pass A muestra solamente el panel multiespectral y exige sus cuatro campos
   enumerados más notas opcionales.
3. Al guardar Pass A, sus valores quedan bloqueados. `Amend Pass A` exige una
   razón, incrementa `pass_a_revision` y audita cada cambio.
4. Solo tras guardar Pass A se muestra el panel temporal y se habilita Pass B.
   Pass B registra concordancia, confianza posterior, checkbox de adjudicación
   y notas, sin actualizar Pass A.
5. `needs_adjudication` exige notas; `unobserved` exige confianza
   `not_applicable` y razón explícita. Los dos no observables congelados siguen
   separados y no son negativos.
6. La advertencia permanente de la interfaz declara que dNBR es evidencia
   descriptiva y no una confirmación de incendio.

La interfaz es interna, local y de ciencia. No es dashboard, no ofrece
predicciones, no sugiere respuestas y no edita el `randomized_order`.

## Archivos y dependencia

Código y pruebas:

- `src/fuegopa/human_review_schema.py`
- `src/fuegopa/human_review_store.py`
- `src/fuegopa/human_review_app.py`
- `scripts/run_human_review_app.py`
- `scripts/validate_human_review.py` con `--validate-tool-export`
- `tests/test_human_review_store.py`
- `tests/test_human_review_app_contract.py`
- `docs/HUMAN_REVIEW_TOOL.md`

Streamlit queda fijado como dependencia de desarrollo en
`pyproject.toml`: `streamlit==1.41.1`. La base, exports y auditoría son
artefactos ignorados por `.gitignore` y no entran al commit.

Comandos documentados:

    conda activate fuegopa
    python -m pip install -e ".[dev]"
    streamlit run scripts/run_human_review_app.py --server.address 127.0.0.1

El servidor se mantiene en localhost; no hay despliegue ni push.

## Exportaciones y validación

Cada snapshot genera CSV y JSON normalizados con columnas A/B separadas,
timestamps, revisiones y estado; además genera un JSONL de auditoría ordenado
por `audit_id` y una proyección CSV compatible con el validador histórico. La
validación explícita es:

    python scripts/validate_human_review.py --validate-tool-export <snapshot.csv>

La cola inicial continúa pasando:

    python scripts/validate_human_review.py --check-empty-calibration

## Pruebas e integridad

La suite oficial se ejecutó en el entorno `fuegopa` con:

    powershell -NoProfile -ExecutionPolicy Bypass -Command "& { & '.\scripts\run_tests.ps1' }"

Resultado: **208 passed in 104.00s (0:01:44)**. Las pruebas cubren
inicialización idempotente, siete items y orden, enums, reviewer obligatorio,
compuerta y bloqueo A/B, enmiendas con razón, auditoría append-only,
timestamps/revisiones, adjudicación, exportaciones CSV/JSON/JSONL,
compatibilidad del validador, separación de los dos no observables, rutas de
panel, ausencia de campos auxiliares y conservación de hashes de prueba.

Hashes verificados antes y después de la implementación:

| Artefacto | Antes | Después |
|---|---|---|
| índice científico del bundle activo | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` |
| manifest Level 2 `firepa_quicklook_level2.sha256` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` |
| índice visual v1 | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` |
| snapshot protegido de revisión | `3d91273adc82b7df6fbfd7508363b90f70423b9d11ba65d4b9da70b1156c7793` | `3d91273adc82b7df6fbfd7508363b90f70423b9d11ba65d4b9da70b1156c7793` |

La integridad científica reportó cero cambios en 179 entradas y cero cambios
visuales en 231 entradas. El snapshot protegido ya mostraba la ausencia
preexistente de `outputs/firepa_quicklook_v2_review.zip`; no se recreó.

## Estado final de alcance

- Cero etiquetas creadas.
- Cero definición o almacenamiento de una columna de referencia científica.
- Cero definición o almacenamiento de `significant_burn`.
- Cero uso de datos posteriores a la cohorte.
- Cero consultas Earth Engine en esta entrega.
- Cero cambios en FIRMS, clustering, selección óptica, métricas, rasters o
  paneles Level 2.
- Cero push y cero despliegue.

El siguiente paso sigue siendo humano: revisar los siete eventos en orden,
decidir si el borrador de protocolo necesita cambios y conservar la ronda como
calibración, no como validación ni como dataset etiquetado.
