# FirePA — protocolo de etiquetado v1

**Versión:** `labeling-protocol-v1`
**Estado:** congelado después de revisión mínima
**Fecha de freeze:** 2026-07-28
**Base Git verificada:** `f302139`
**Unidad de trabajo:** evento provisional observable del piloto Sentinel-2

Este documento congela el contrato observacional de la revisión formal. El
artefacto histórico `docs/LABELING_PROTOCOL_CANDIDATE_v1.md` se conserva sin
reescritura. La revisión fue deliberadamente mínima: eliminó el parsing de
notas, separó prioridades expertas, añadió comparación interrevisor explícita,
reforzó la procedencia y definió cierre administrativo sin convertirlo en
verdad científica.

## Fuentes y alcance

El protocolo se deriva de `CONTEXT.md`, `PLAN.md`, `PROJECT_STATUS.md`, el
candidato v1, la comparación ciega R1, su checkpoint,
`docs/HUMAN_REVIEW_TOOL.md` y el diseño dNBR vigente. Se aplica únicamente a
los 28 eventos observables del piloto de 30 eventos `r1500_t06`. Los dos casos
sin pareja óptica utilizable se mantienen en un registro `unobserved` separado.

FirePA registra observaciones visuales estructuradas y limitaciones de
observación. No fuerza una resolución cuando la evidencia es ambigua o
indeterminada.

## Observación frente a decisión científica

- `visible_burn_scar` es una observación visual estructurada.
- `event_association` es una evaluación observacional de asociación.
- `competing_land_change` registra explicaciones visuales competidoras.
- `observation_limitation` registra restricciones de observabilidad.
- `review_complete` es un estado administrativo.

Ninguno de estos campos es una confirmación de incendio, una medida de
severidad, una predicción o una referencia científica externa. El acuerdo
entre revisores describe concordancia; no establece una verdad independiente.

## Pass A: observación inicial

Pass A se completa antes de revelar la comparación temporal entre modos. Cada
campo es estructurado; las notas solo explican la lectura y nunca se analizan
computacionalmente.

### Campos y enums

`visible_burn_scar`:

- `yes`
- `no`
- `ambiguous`

`scar_confidence`:

- `high`
- `medium`
- `low`

`event_association`:

- `likely`
- `possible`
- `unlikely`
- `indeterminate`

`competing_land_change`:

- `none_visible`
- `agriculture_or_harvest`
- `soil_exposure`
- `moisture_or_flooding`
- `water`
- `urban_or_construction`
- `mixed`
- `unknown`

`observation_limitation`:

- `none`
- `cloud_or_haze`
- `mask_or_nodata`
- `shadow`
- `partial_coverage`
- `insufficient_temporal_separation`
- `mixed`
- `other`

La correspondencia administrativa con el candidato histórico es
`shadow_or_atmosphere → shadow`, `long_temporal_gap →
insufficient_temporal_separation` y `unknown → other` cuando el valor describe
una limitación, no un proceso de superficie. `cloud_or_haze` y
`shadow_or_atmosphere` no son procesos competidores en v1.

## Bloqueo, hash y enmiendas de Pass A

Al guardar Pass A se conserva un payload normalizado, su `payload_sha256`,
`locked_at`, `reviewer_id`, `reviewer_slot`, toda la procedencia, versión del
protocolo, versión de herramienta, `round_id`, `assignment_id`, `event_id`,
`blind_alias`, hash del manifest de entrada visual y una entrada de auditoría.

Una vez bloqueada:

- la UI y el importador no pueden sobrescribir Pass A;
- Pass B no reemplaza ningún campo de Pass A;
- reanudar la ronda no reabre Pass A;
- una corrección excepcional exige una enmienda append-only con valor
  anterior, valor corregido, razón, autor y timestamps.

La inmutabilidad se aplica también en la persistencia, no solo ocultando
botones.

## Pass B: comparación temporal

Pass B solo se abre después del bloqueo de Pass A. Conserva intactos todos los
campos de Pass A y registra únicamente la comparación entre `selected_pair` y
`window_median`:

- `mode_agreement`: `agree`, `partially_agree`, `disagree`;
- `confidence_after_comparison`: `high`, `medium`, `low`;
- `reviewer_requests_adjudication`: `true` o `false`;
- `structured_adjudication_request_reason`;
- `pass_b_notes`.

Los modos no se mezclan: ninguna métrica o raster de uno sustituye al otro.
`partially_agree` no activa adjudicación por sí solo. El cambio de confianza
conserva ambos valores y no sobrescribe la confianza original.

Las razones estructuradas permitidas son `ambiguous_observation`,
`low_confidence`, `indeterminate_association`, `mode_disagreement`,
`association_disagreement` y `other_structured`.

## Procedencia del revisor

Los campos son independientes y obligatorios:

- `reviewer_type`: `human` o `ai_assisted`;
- `reviewer_expertise`: `protocol_trained_reviewer`,
  `remote_sensing_specialist`, `domain_expert` o `not_applicable`;
- `reviewer_model`: modelo y versión cuando corresponda;
- `label_status`: `human_observation` o `provisional_pseudolabel`.

Para una fila humana, el modelo es nulo, la experiencia no es
`not_applicable` y `label_status=human_observation`. Para una fila IA, el
modelo es obligatorio, la experiencia es `not_applicable` y
`label_status=provisional_pseudolabel`. Una fila IA no puede promocionarse a
humana cambiando su estado; una observación humana posterior es una fila nueva
con procedencia propia. La preparación de esta fase no inserta filas IA ni
humanas.

También se registran, cuando aplican, `reviewer_id`, `reviewer_slot`,
`protocol_training_version`, `tool_version`, `review_timestamp`,
`model_provider`, `model_name`, `model_version` y el hash del contrato de
entrada. Un slot no equivale a una persona y debe vincularse a un perfil
humano real antes de revisar.

## Comparación interrevisor

Las dos revisiones se conservan lado a lado. La comparación determinista
produce, por campo, acuerdos exactos, desacuerdos materiales, desacuerdos no
materiales, razones de adjudicación, prioridad experta y estado administrativo.
No produce una columna de consenso ni sustituye las respuestas originales.

Es material un desacuerdo en `visible_burn_scar`, o una diferencia de
`event_association` entre `indeterminate` y un valor determinado, o entre
`likely` y `unlikely`. Diferencias de confianza, competidores o limitaciones se
conservan como desacuerdos no materiales salvo que exista además un disparador
explícito.

## Triage administrativo

El triage usa únicamente campos estructurados, comparación interrevisor y
resoluciones estructuradas. Está prohibido buscar palabras en notas, inferir
estados desde texto libre o editar manualmente `needs_adjudication` o
`expert_review_priority`.

### Adjudicación

`needs_adjudication=true` cuando ocurre al menos una condición:

1. un revisor usa `visible_burn_scar=ambiguous`;
2. un revisor usa `scar_confidence=low`;
3. un revisor usa `event_association=indeterminate`;
4. un revisor usa `mode_agreement=disagree`;
5. un revisor solicita adjudicación con una razón estructurada permitida;
6. existe desacuerdo interrevisor en `visible_burn_scar`;
7. existe desacuerdo material de asociación.

Los reason codes v1 son `ADJ_VISIBLE_AMBIGUOUS`, `ADJ_LOW_CONFIDENCE`,
`ADJ_ASSOCIATION_INDETERMINATE`, `ADJ_MODE_DISAGREEMENT`,
`ADJ_REVIEWER_REQUEST`, `ADJ_VISIBLE_INTERREVIEWER_DISAGREEMENT` y
`ADJ_ASSOCIATION_INTERREVIEWER_DISAGREEMENT`.

No activan adjudicación por sí solos `partially_agree`, diferencias
`high/medium`, diferencias `medium/low` sin otro disparador, competidores,
limitaciones o notas libres.

### Prioridad experta

`expert_review_priority` puede ser `none`, `recommended` o `required`.

`recommended` se deriva, cuando corresponde, por agricultura o cosecha,
mezcla, causa desconocida, competidor fuerte con confianza inferior a alta,
cambio de confianza entre Pass A y Pass B, desacuerdo interrevisor no material
persistente o asociación determinada con competidor fuerte. Un confusor o una
limitación por sí sola no produce `required`.

Durante la comparación inicial, `required` nunca aparece solo por un
confusor. Solo puede aparecer después de una adjudicación estructurada si
permanece un desacuerdo material, la resolución necesita una distinción
especializada y el adjudicador selecciona un `specialist_question_code` válido.
`recommended` no bloquea el cierre administrativo; `required` sí.

La ausencia de información puede conservarse como `ambiguous`,
`indeterminate` o `unobserved`. No se fuerza una revisión experta indefinida.

## Adjudicación y revisión experta

Una adjudicación conserva ambas respuestas iniciales, sus hashes, el motivo,
la resolución estructurada y su estado. Puede mantener `ambiguous` o
`indeterminate`; no debe forzar `yes` o `no`.

Una revisión experta, si se autoriza posteriormente, tiene perfil y
`specialist_question_code` propios. No se ejecuta como parte de la preparación
de la ronda y no se crea una respuesta experta ficticia.

## Estados administrativos

Los estados de asignación formales son `pending`, `pass_a_locked`,
`pending_pair_review`, `pending_adjudication`, `pending_expert_review` y
`review_complete`. El registro separado de los dos casos ópticamente no
observables usa `unobserved`.

Una asignación está completa cuando Pass A está validada y bloqueada, Pass B
es válida, la procedencia y los hashes son completos y la auditoría es válida.
Un evento está `review_complete` cuando las dos asignaciones están completas,
la comparación fue generada y se completaron las acciones bloqueantes de
adjudicación o de experto. Puede estar completo con `ambiguous` o
`indeterminate`. `review_complete` es únicamente un cierre administrativo.

La ronda de esta fase queda `prepared`, `not_started`, con cero revisiones,
cero adjudicaciones, cero revisiones expertas y cero nuevas salidas IA.

## Outputs permitidos y límites

La preparación puede producir manifests canónicos, hashes, aliases ciegos,
órdenes, asignaciones vacías, registros administrativos, migraciones y un
registro separado de `unobserved`. Los paquetes públicos no incluyen el join
alias-evento ni FRP, confianza FIRMS, rankings, scores, clases predichas,
severidad, metadatos de otros revisores o triage futuro. El join privado queda
fuera de Git.

Esta fase no produce observaciones, adjudicaciones, pseudolabels nuevos,
variables ambientales, modelos, predicciones, una interfaz pública ni nuevas
consultas Earth Engine. No crea campos científicos ni usa `unobserved` como
`no`.

## Política de cambios futuros

El SHA-256 del archivo congelado se registra en el checkpoint de preparación.
Cualquier cambio semántico posterior requiere `labeling-protocol-v2` o una
versión mayor explícita. No se edita silenciosamente v1. Cambios puramente
tipográficos deben conservar el hash en el checkpoint y documentarse antes de
modificar cualquier export o revisión.
