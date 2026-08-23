# Checkpoint — Blind Control R1 importación y comparación

Fecha de validación: 2026-07-26.

Commit de partida verificado: `6e9f36dc16be6ea2101356c89abf5b338d27e155` —
`Refine review protocol and add independent control round`.

Este checkpoint documenta únicamente la validación de dos respuestas ciegas
independientes. No congela el protocolo candidato, no crea etiquetas
científicas y no modifica la calibración R1 anterior.

## Entradas

Los cuatro archivos presentes localmente fueron:

- `review-inputs/blind_control_r1_reviewer_a_pass_a.json`
- `review-inputs/blind_control_r1_reviewer_a_pass_b.json`
- `review-inputs/blind_control_r1_reviewer_b_pass_a.json`
- `review-inputs/blind_control_r1_reviewer_b_pass_b.json`

La solicitud refería los dos archivos de Reviewer B con el sufijo literal
`(1)`, pero esas rutas no existen en el estado local. Se usaron los nombres
presentes sin ese sufijo. Ningún JSON fue editado, renombrado ni normalizado.

| Archivo | SHA-256 |
|---|---|
| Reviewer A Pass A | `112c477937a9ef0e78c44298f01bb32c510674458cdbeffd9569448ee782567a` |
| Reviewer A Pass B | `357abc63a1d954d9acae935dc983463c2da6c2868fe1ea7611b15b5e008716bf` |
| Reviewer B Pass A | `590b46e4850620b3792e43a42e5177fba7aeb11f1095c3c13cffa285fbe75039` |
| Reviewer B Pass B | `d622c11ba51c4806511c93a49e80b316488309b4aa21db77f870dfe7651620bf` |

## Validación de schema y anonimato

Los cuatro JSON pasan la validación del contrato `firepa-blind-control-r1-response-v1`:

- `round_id=control_r1`.
- `protocol_version=candidate-v1`.
- Reviewer A: `blind_control_r1_reviewer_a`, modelo `GPT-5.6 Thinking`.
- Reviewer B: `blind_control_r1_reviewer_b`, modelo `GPT-5.5 Thinking`.
- Ambos: `reviewer_type=ai_assisted`, `reviewer_expertise=not_applicable` y `label_status=provisional_pseudolabel`.
- Siete casos exactos por archivo: `CASE-001` a `CASE-007`.
- IDs de reviewer distintos y metadata Pass A/Pass B consistente.
- Pass B conserva exactamente todos los campos de Pass A en cada caso.
- No aparecen `event_id` originales, rutas Windows, `significant_burn` ni `ground_truth`.
- No aparece el año 2026 en el contenido de las respuestas.

## Dry-run

Comando ejecutado antes de escribir SQLite:

```powershell
python scripts/import_blind_control_r1.py `
  --reviewer-a-pass-a review-inputs/blind_control_r1_reviewer_a_pass_a.json `
  --reviewer-a-pass-b review-inputs/blind_control_r1_reviewer_a_pass_b.json `
  --reviewer-b-pass-a review-inputs/blind_control_r1_reviewer_b_pass_a.json `
  --reviewer-b-pass-b review-inputs/blind_control_r1_reviewer_b_pass_b.json `
  --dry-run
```

Resultado: `pass`, cero errores, cero escritura SQLite y `would_insert=14`.

## Importación SQLite

Destino:

`outputs/human_review/firepa_human_review.sqlite3`

Se creó la ronda separada `control_r1`, con items `CASE-*` y sin mapear
identificadores de eventos originales. Se añadieron 14 filas:

| Reviewer | Modelo | Filas | Proveniencia |
|---|---|---:|---|
| `blind_control_r1_reviewer_a` | GPT-5.6 Thinking | 7 | `ai_assisted`, `not_applicable`, `provisional_pseudolabel` |
| `blind_control_r1_reviewer_b` | GPT-5.5 Thinking | 7 | `ai_assisted`, `not_applicable`, `provisional_pseudolabel` |

La tabla conserva explícitamente `reviewer_id`, `reviewer_model`,
`reviewer_type`, `reviewer_expertise`, `label_status` y
`observation_limitation`. Se agregaron 210 entradas de auditoría
`import_blind_control_r1`; el trigger append-only permaneció activo.

La ronda R1 anterior conserva sus 7 filas y su snapshot lógico no cambió.
No hubo sobrescritura entre reviewers ni entre rondas.

## Idempotencia y conflictos

Una segunda importación de los mismos cuatro archivos produjo:

- `inserted=0`;
- `unchanged=14`;
- `sqlite_changed=false`;
- `r1_protected_rows_unchanged=true`.

Una prueba con una respuesta modificada para un reviewer existente fue
rechazada como conflicto y dejó el hash SQLite sin cambios.

## Comparación read-only

Comando ejecutado:

```powershell
python scripts/compare_blind_control_r1.py `
  --reviewer-a-pass-a review-inputs/blind_control_r1_reviewer_a_pass_a.json `
  --reviewer-a-pass-b review-inputs/blind_control_r1_reviewer_a_pass_b.json `
  --reviewer-b-pass-a review-inputs/blind_control_r1_reviewer_b_pass_a.json `
  --reviewer-b-pass-b review-inputs/blind_control_r1_reviewer_b_pass_b.json `
  --database outputs/human_review/firepa_human_review.sqlite3 `
  --markdown-output docs/BLIND_CONTROL_R1_COMPARISON.md
```

La comparación fue `pass`, reconcilió las 14 filas importadas y no escribió
SQLite. El hash fue idéntico antes y después de la comparación:

`454b95873c09883c56e02df7c74bba7ed620ccec8fc47a1fb5aad0ee842239df`

### Sanity checks derivados

Los conteos se derivaron de los JSON, no se codificaron como resultados de
producción:

| Campo | Acuerdos derivados |
|---|---:|
| `pass_a_visible_burn_scar` | 6/7 |
| `pass_a_scar_confidence` | 3/7 |
| `pass_a_event_association` | 4/7 |
| `pass_a_competing_land_change` | 4/7 |
| `observation_limitation` | 7/7 |
| `pass_b_mode_agreement` | 4/7 |
| `pass_b_confidence_after` | 4/7 |
| `pass_b_requires_adjudication` | 6/7 |

La comparación completa está en
[`docs/BLIND_CONTROL_R1_COMPARISON.md`](BLIND_CONTROL_R1_COMPARISON.md).

### Acuerdo exacto por campo

| Campo | Acuerdos | Desacuerdos |
|---|---:|---:|
| `pass_a_visible_burn_scar` | 6 | 1 |
| `pass_a_scar_confidence` | 3 | 4 |
| `pass_a_event_association` | 4 | 3 |
| `pass_a_competing_land_change` | 4 | 3 |
| `observation_limitation` | 7 | 0 |
| `pass_b_mode_agreement` | 4 | 3 |
| `pass_b_confidence_after` | 4 | 3 |
| `pass_b_requires_adjudication` | 6 | 1 |

Las notas Pass A y Pass B no tienen coincidencia textual exacta en los siete
casos; esto no se interpreta como desacuerdo científico automático.

### Diferencias estructuradas

- Confianza: diferencias en `CASE-001`, `CASE-002`, `CASE-003`, `CASE-006` y `CASE-007`.
- Asociación: `CASE-003`, `CASE-005` y `CASE-007`.
- `competing_land_change`: `CASE-002`, `CASE-003` y `CASE-007`.
- `observation_limitation`: ninguna; 7/7 coinciden.
- `mode_agreement`: `CASE-004`, `CASE-005` y `CASE-007`.
- `pass_b_requires_adjudication`: `CASE-007`.

### Triage

- Reviewer A requiere adjudicación en `CASE-003`, `CASE-004`, `CASE-005`.
- Reviewer B requiere adjudicación en `CASE-005`, `CASE-007`.
- Unión de adjudicación: `CASE-003`, `CASE-004`, `CASE-005`, `CASE-007`.
- Intersección de adjudicación: `CASE-005`.
- Reviewer A requiere revisión experta en `CASE-002`, `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`; recomienda `CASE-007`.
- Reviewer B requiere revisión experta en `CASE-001`, `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`, `CASE-007`; recomienda `CASE-002`.
- Unión de prioridad experta requerida: los siete casos.
- Intersección de prioridad experta requerida: `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`.

### Casos destacados

- `CASE-007`: desacuerdo material; no se resuelve por mayoría.
- `CASE-005`: ambigüedad visual compartida y adjudicación por ambos.
- `CASE-006`: patrón `agriculture_or_harvest` compartido.
- `CASE-001` y `CASE-002`: observación positiva compartida (`yes` y `likely`), con diferencias de confianza o competidor.
- `CASE-003` y `CASE-004`: observación negativa compartida en el eje visible (`no`), aunque `CASE-003` conserva diferencia de asociación y `CASE-004` diferencia modal.

Acuerdo entre dos modelos de la misma familia no es ground truth. No se
calcularon exactitud, sensibilidad, especificidad ni una tasa de error contra
un estándar externo.

## Integridad antes/después

Los siguientes hashes permanecieron idénticos entre el snapshot previo y el
posterior a la importación. La única modificación permitida fue SQLite.

| Artefacto | Antes | Después | Estado |
|---|---|---|---|
| Bundle científico, 179 entradas | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | igual |
| Índice visual científico, 231 entradas | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | igual |
| Manifest Level 2 | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | igual |
| Rasters Level 2, 133 entradas | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | igual |
| Paneles originales, 14 entradas | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | igual |
| Cola calibración R1 | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | igual |
| Manifest calibración R1 | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | igual |
| SQLite antes de importar | `42300b9259d6267014ad761b8b6bddf63c07dad1439007f12173d56cedc74bfb` | — | base |
| SQLite después de importar | — | `454b95873c09883c56e02df7c74bba7ed620ccec8fc47a1fb5aad0ee842239df` | importación auditada |
| SQLite durante comparación | `454b95873c09883c56e02df7c74bba7ed620ccec8fc47a1fb5aad0ee842239df` | `454b95873c09883c56e02df7c74bba7ed620ccec8fc47a1fb5aad0ee842239df` | byte-identical |

## Pruebas

- Pruebas específicas de blind control: **11 passed**.
- Suite completa mediante `scripts/run_tests.ps1` en Conda `fuegopa`, Python 3.12: **228 passed in 490.30s**.
- `py_compile` de módulo y scripts modificados: pass.
- No hubo llamadas de red ni Earth Engine.

## Estado Git y límites

- Rama: `master`.
- No se hizo commit ni push.
- Los JSON de `Downloads` no están dentro del repositorio y no fueron copiados a Git.
- El SQLite y los reportes bajo `outputs/` permanecen locales/ignorados.
- Se conservaron los cambios locales preexistentes, incluido el handoff previo.
- Cero etiquetas científicas finales.
- Cero `significant_burn`.
- Cero ground truth.
- Cero datos científicos de 2026.
- Cero modificaciones a rasters, paneles, escenas, cohortes, métricas o resultados R1.

## Reanudación segura

La siguiente sesión puede verificar primero este checkpoint y
`docs/BLIND_CONTROL_R1_COMPARISON.md`. Cualquier adjudicación posterior debe
ser una decisión explícita y separada; no debe convertirse automáticamente en
una etiqueta científica ni retroescribir `control_r1`, R1 o los resultados
ópticos.
