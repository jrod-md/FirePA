# Revaluación read-only de la calibración R1 bajo Candidate v1

**Estado:** vista derivada para control metodológico; no migra ni reescribe R1.
**Fuente:** las siete filas IA ya importadas en SQLite, leídas en modo `ro`.
**Resultado:** no se modificó SQLite ni se produjeron etiquetas.

## Propósito

Mostrar cómo se separarían los antiguos códigos de confusores y las limitaciones de observación si se aplica Candidate v1. Esta tabla no constituye una nueva revisión de paneles ni una reinterpretación persistida de la calibración R1.

El lector usa solo campos estructurados. No busca palabras en `pass_a_notes`, `pass_b_notes` ni `adjudication_notes`; por tanto, una mención textual de nube, bruma o máscara no cambia la prioridad administrativa.

## Cambios de contrato

En Candidate v1, `competing_land_change` queda limitado a procesos de superficie. `cloud_or_haze` deja de ser un valor válido en ese eje y pasa a `observation_limitation` cuando existe como señal estructurada. Como R1 no tenía ese campo separado, el valor antiguo de `CASE-003` se representa en esta vista como:

- `legacy_competing_land_change=cloud_or_haze`;
- `candidate_competing_land_change=unknown`, porque no se puede afirmar retrospectivamente `none_visible`;
- `observation_limitation=cloud_or_haze`.

Esto es una vista de control, no una migración. En particular, las menciones de limitación que estaban solo en notas no se promueven a un campo estructurado.

## Reglas aplicadas

`needs_adjudication` se activa por ambigüedad visual, confianza baja en Pass A, asociación indeterminada, desacuerdo Pass B o solicitud explícita del revisor.

`expert_review_priority` se calcula en un segundo eje:

- `required`: adjudicación requerida, competidor `agriculture_or_harvest`/`mixed`/`unknown`, limitación distinta de `none` o cambio de confianza;
- `recommended`: sin regla `required` y competidor `soil_exposure`, `vegetation_phenology`, `moisture_or_flooding`, `water` o `urban_or_construction`;
- `none`: ninguna condición anterior.

Las razones se expresan como códigos deterministas. `partially_agree` solo permanece como evidencia de robustez incompleta.

## Resultado por caso

| CASE ID | Competidor candidato | Limitación estructurada | Adjudicación propuesta | Prioridad experta | Razones expertas |
|---|---|---|---|---|---|
| `CASE-001` | `none_visible` | `none` | no | `none` | — |
| `CASE-002` | `none_visible` | `none` | no | `none` | — |
| `CASE-003` | `unknown` | `cloud_or_haze` | sí | `required` | `needs_adjudication`; `competing_land_change=unknown`; `observation_limitation=cloud_or_haze` |
| `CASE-004` | `mixed` | `none` | no | `required` | `competing_land_change=mixed` |
| `CASE-005` | `agriculture_or_harvest` | `none` | sí | `required` | `needs_adjudication`; `competing_land_change=agriculture_or_harvest` |
| `CASE-006` | `agriculture_or_harvest` | `none` | sí | `required` | `needs_adjudication`; `competing_land_change=agriculture_or_harvest`; `confidence_changed_between_passes` |
| `CASE-007` | `soil_exposure` | `none` | no | `recommended` | `competing_land_change=soil_exposure` |

## Diferencias respecto a Draft v2

- Los casos de adjudicación propuestos permanecen iguales: `CASE-003`, `CASE-005` y `CASE-006`.
- `CASE-007` pasa a tener `expert_review_priority=recommended` por `soil_exposure`; antes quedaba fuera del disparador especializado de Draft v2.
- `CASE-003` ya no se describe como un proceso competidor `cloud_or_haze`: el concepto queda en el eje estructurado de limitación y el eje de superficie queda como `unknown`.
- `CASE-005` no recibe `observation_limitation=cloud_or_haze` por sus notas previas. Sin un campo estructurado importado, la limitación queda sin promover.
- No se usa `partially_agree` como disparador autónomo.

## Integridad de R1

La revaluación no escribe `review_status`, no agrega columnas a SQLite, no modifica las notas importadas y no crea una segunda copia de las filas dentro de la base. R1 conserva su `reviewer_id`, `reviewer_type=ai_assisted`, `label_status=provisional_pseudolabel` y sus valores originales.

## Límites

La prioridad experta y la adjudicación son estados administrativos derivados. No son clases científicas y no convierten acuerdo, confianza o una limitación de panel en ground truth. Esta revaluación no calcula exactitud, sensibilidad ni especificidad, no inicia la ronda formal y no consulta Earth Engine.
