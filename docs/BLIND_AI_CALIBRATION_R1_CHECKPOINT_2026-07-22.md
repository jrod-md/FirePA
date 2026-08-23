# Checkpoint — Blind AI Calibration R1 analysis — 2026-07-22

## Alcance y punto de partida

Trabajo realizado en FirePA después de `f56bdae9f6c41d587ed3e90d32273b5615350a3f`. El repositorio estaba en la rama `master`, con cambios locales no relacionados ya presentes en `data/`, `docs/HANDOFF_FIREPA_2026-07-21.md` y `notebooks/`; se conservaron sin stage ni modificación.

La calibración ciega R1 ya estaba importada antes de este turno. El informe registra 7 filas insertadas, sin errores, sin filas humanas preservadas, sin `ground_truth` y sin etiquetas científicas finales.

## Archivos leídos

- `PLAN.md`
- `CONTEXT.md`
- `docs/LABELING_PROTOCOL_DRAFT_v1.md`
- `docs/HUMAN_REVIEW_CALIBRATION_CHECKPOINT_2026-07-21.md`
- `docs/HUMAN_REVIEW_TOOL.md`
- `docs/BLIND_AI_CALIBRATION_PACKAGE_CHECKPOINT_2026-07-22.md`
- `scripts/import_blind_ai_calibration.py`
- `src/fuegopa/human_review_schema.py`
- `src/fuegopa/human_review_store.py`
- `outputs/human_review/blind_ai_calibration_r1_import.json`
- `outputs/human_review/firepa_human_review.sqlite3`, en modo lectura
- `outputs/human_review/private/calibration_r1_case_map.csv`, solo para validar el join `CASE-*`

## Método y entregables

Se añadió [`scripts/summarize_blind_ai_calibration.py`](../scripts/summarize_blind_ai_calibration.py), un lector determinista que:

- exige exactamente los 7 casos R1 y el conjunto `CASE-001` a `CASE-007`;
- abre SQLite con `mode=ro` y `PRAGMA query_only=ON`;
- calcula las distribuciones, transiciones de confianza, conjuntos de triage y comprobaciones de contrato;
- comprueba que los campos de observación no contienen valores de 2026;
- no llama Earth Engine y no escribe la base.

Los documentos creados son:

- [`docs/BLIND_AI_CALIBRATION_R1_ANALYSIS.md`](BLIND_AI_CALIBRATION_R1_ANALYSIS.md)
- [`docs/LABELING_PROTOCOL_DRAFT_v2.md`](LABELING_PROTOCOL_DRAFT_v2.md)
- este checkpoint

La propuesta de triage produce 3 casos para `needs_adjudication` (`CASE-003`, `CASE-005`, `CASE-006`) y 4 para revisión especializada (`CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`). Es una propuesta derivada; no se escribió ese estado en SQLite.

## Integridad antes/después

La instantánea se tomó antes de editar documentación y pruebas y se repitió después. Los conteos y hashes no deben variar por este trabajo.

| Artefacto protegido | Antes | Después | Resultado |
|---|---|---|---|
| Bundle científico, índice (179 entradas) | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | byte/index unchanged |
| Índice visual científico (231 entradas) | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | unchanged |
| Manifest Level 2 | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | unchanged |
| Rasters Level 2, índice (133 entradas) | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | unchanged |
| Paneles originales, índice (14 entradas) | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | unchanged |
| Cola original de calibración | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | unchanged |
| Manifest de calibración | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | unchanged |
| SQLite, SHA-256 directo del archivo | `42300B9259D6267014AD761B8B6BDDF63C07DAD1439007F12173D56CEDC74BFB` | `42300B9259D6267014AD761B8B6BDDF63C07DAD1439007F12173D56CEDC74BFB` | byte-identical |

La instantánea SQLite del índice local también se mantuvo en `5199137e68e95d6190c67515b0a5420afb8f747666e3bb11cb2ce1ac00b32873` antes y después. La comparación directa del archivo es la comprobación de byte-identidad exigida.

## Declaraciones de frontera

- Etiquetas científicas finales: **0**.
- `significant_burn`: **0**; no se creó ni se definió.
- `ground_truth`: **0**.
- Earth Engine: **0** consultas.
- Cambios científicos: **0**; no se modificaron bundle, manifest, paneles ni rasters.
- Datos de 2026: **0** en los campos de observación analizados.
- Modelos entrenados: **0**.
- Push: **0**.
- Commit nuevo en este turno: **0**, tal como se solicitó.

## Validación ejecutada

- `python -m pytest -q -p no:cacheprovider tests/test_blind_ai_calibration_summary.py`: **3 passed in 0.32s**.
- `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`: **216 passed in 337.94s (0:05:37)**.
- `python -m py_compile scripts/summarize_blind_ai_calibration.py`: **pass**.
- `git diff --check`: **pass**.
- El resumen JSON y Markdown del lector se generaron sin escribir SQLite.

## Estado Git al cierre

Rama: `master`. No se creó commit, no se hizo stage y no se hizo push. Los nuevos archivos de análisis, protocolo, checkpoint, lector y prueba permanecen sin seguimiento junto con los artefactos locales preexistentes `data/`, `docs/HANDOFF_FIREPA_2026-07-21.md` y `notebooks/`.
