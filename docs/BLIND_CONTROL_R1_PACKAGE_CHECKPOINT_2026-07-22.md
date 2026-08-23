# Checkpoint — Blind control R1 Candidate v1 — 2026-07-22

## Commit y alcance

Trabajo realizado sobre `master`, con HEAD inicial `d8c775f`, descendiente del estado R1 ya importado. El commit local de cierre usa exactamente el mensaje:

`Refine review protocol and add independent control round`

No se hará push. Los artefactos generados bajo `outputs/` y los ZIP no forman parte del commit.

## Cambios metodológicos

Se creó [`docs/LABELING_PROTOCOL_CANDIDATE_v1.md`](LABELING_PROTOCOL_CANDIDATE_v1.md) como candidato no congelado, derivado de Draft v2, con:

- observación, asociación y causalidad separadas;
- `none_visible` limitado a lo no observado en el panel;
- Pass A antes de Pass B y preservación de Pass A;
- `competing_land_change` limitado a procesos de superficie;
- `observation_limitation` estructurado y separado;
- ninguna regla administrativa basada en parsing de notas;
- `reviewer_type`, `reviewer_expertise`, `reviewer_model` y `label_status` separados;
- `needs_adjudication` y `expert_review_priority` como ejes administrativos distintos;
- `expert_review_reasons` como códigos deterministas;
- `provisional_pseudolabel` sin equivalencia automática a ground truth.

La revaluación read-only de R1 queda en [`docs/BLIND_AI_CALIBRATION_R1_CANDIDATE_REEVALUATION.md`](BLIND_AI_CALIBRATION_R1_CANDIDATE_REEVALUATION.md). Los casos propuestos son:

- adjudicación: `CASE-003`, `CASE-005`, `CASE-006`;
- experto requerido: `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`;
- experto recomendado: `CASE-007` por `soil_exposure`.

El antiguo `cloud_or_haze` de `CASE-003` se representa solo en la vista derivada como `observation_limitation=cloud_or_haze`; no se migró ni se reescribió R1.

## Paquete de control ciego

Se generaron desde los mismos píxeles anonimizados de los paquetes R1, retirando únicamente metadata textual de los PNG para no transportar resultados o referencias internas. El flujo de píxeles se validó idéntico al panel R1 fuente.

- `outputs/firepa_blind_control_r1_pass_a.zip`
- `outputs/firepa_blind_control_r1_pass_b.zip`

Cada ZIP contiene únicamente el protocolo candidato sanitizado, sus instrucciones, schema de la pasada, siete paneles, manifest y checksums. No contiene resultados R1, mapping privado, identificadores de fuente, SQLite ni interpretaciones de casos.

Hashes de los ZIP generados:

| ZIP | SHA-256 |
|---|---|
| Pass A | `2d06c5027e9ed69be5efbb73773f858e2de28145d59c7b579e6d1b0e4720dbad` |
| Pass B | `7ad2aaa3ff42c63d2304a4fac798e8c9504a4d7608a142326c361a97453ed3e2` |

Los hashes de los ZIP R1 fuente permanecieron sin cambio:

- Pass A: `1a502bd8de9ed57ab4e8cdff439e1a56d1b109d106dac58f82df41d2db78a278`.
- Pass B: `074a3a344c7d025c67fe71f300582bec235a6cb642e5d3c01c972b538651ccd7`.

## Código y validación

- [`src/fuegopa/blind_control_round.py`](../src/fuegopa/blind_control_round.py): generación, validación, importación separada y comparación read-only.
- [`scripts/build_blind_control_r1.py`](../scripts/build_blind_control_r1.py): generación de ZIPs.
- [`scripts/import_blind_control_r1.py`](../scripts/import_blind_control_r1.py): validación/dry-run de cuatro JSON.
- [`scripts/compare_blind_control_r1.py`](../scripts/compare_blind_control_r1.py): comparación por campo y CASE.
- [`scripts/summarize_blind_ai_calibration.py`](../scripts/summarize_blind_ai_calibration.py): resumen R1 y revaluación candidata.
- Schemas: `docs/BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_A.json` y `docs/BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_B.json`.

Pruebas ejecutadas:

- pruebas específicas de control: **9 passed**;
- suite completa `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`: **226 passed in 499.05s (0:08:19)**;
- `py_compile`: pass;
- `git diff --check`: pass.

El importador conserva cada revisor por separado, rechaza IDs duplicados y reescrituras de Pass A, valida enums/proveniencia, deriva triage, no escribe SQLite y no interpreta acuerdo como verdad de referencia. El comparador no calcula exactitud, sensibilidad ni especificidad.

## Integridad antes/después

| Artefacto | Hash antes | Hash después | Estado |
|---|---|---|---|
| Bundle científico, 179 entradas | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | igual |
| Índice visual científico, 231 entradas | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | igual |
| Manifest Level 2 | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | igual |
| Rasters Level 2, 133 entradas | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | igual |
| Paneles originales, 14 entradas | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | igual |
| Cola de calibración R1 | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | igual |
| Manifest de calibración R1 | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | igual |
| SQLite R1, SHA-256 directo | `42300B9259D6267014AD761B8B6BDDF63C07DAD1439007F12173D56CEDC74BFB` | `42300B9259D6267014AD761B8B6BDDF63C07DAD1439007F12173D56CEDC74BFB` | byte-identical |

## Límites declarados

- etiquetas finales: **0**;
- `significant_burn`: **0**;
- ground truth: **0**;
- Earth Engine: **0** consultas;
- datos de 2026: **0**;
- cambios en datos, rasters, paneles originales, cohortes o métricas: **0**;
- respuestas de revisores importadas en esta ronda: **0**;
- push: **0**.
