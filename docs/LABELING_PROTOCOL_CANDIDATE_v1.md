# Labeling Protocol — Candidate v1

**Estado:** candidato de control; no es un protocolo formal congelado.
**Uso:** una ronda ciega independiente con dos revisores IA sobre paneles anonimizados.

## Alcance

El protocolo registra observación visual, asociación con el evento y condiciones de revisión. No convierte una observación en causalidad, no crea una clase científica y no fuerza una resolución cuando la evidencia es `ambiguous`, `indeterminate` o `unobserved`.

`provisional_pseudolabel` describe la procedencia provisional de una salida asistida por IA. No equivale automáticamente a `ground_truth` ni a una observación humana de referencia.

Cada revisor completa Pass A antes de iniciar Pass B. Pass B debe conservar todos los valores de Pass A y añadir únicamente sus campos de comparación. La salida de un revisor no se comparte con el otro durante la revisión independiente.

## Ejes de observación

### Observación visual

`pass_a_visible_burn_scar` usa `yes`, `no`, `ambiguous` o `unobserved`. Describe lo que se observa en el panel; no es una clase de incendio, severidad o superficie afectada.

`pass_a_scar_confidence` y `pass_b_confidence_after` usan `high`, `medium`, `low` o `not_applicable`. Son niveles ordinales de confianza del observador, no probabilidades calibradas.

`pass_a_event_association` usa `likely`, `possible`, `unlikely` o `indeterminate`. Es una asociación visual/temporal; `likely` no demuestra causalidad.

### Procesos competidores de superficie

`pass_a_competing_land_change` representa únicamente un proceso o cambio posible en la superficie:

- `none_visible`
- `agriculture_or_harvest`
- `soil_exposure`
- `vegetation_phenology`
- `moisture_or_flooding`
- `water`
- `urban_or_construction`
- `mixed`
- `unknown`

`none_visible` significa solamente que no se observó un proceso competidor en el panel revisado. No significa que otra explicación no exista fuera del panel, en otra fecha o bajo una limitación de observación.

### Limitaciones de observación

`observation_limitation` es un campo estructurado separado de los procesos de superficie y usa:

- `none`
- `cloud_or_haze`
- `shadow_or_atmosphere`
- `mask_or_nodata`
- `partial_coverage`
- `long_temporal_gap`
- `mixed`
- `unknown`

Las notas son texto libre explicativo. No se buscan palabras en las notas para derivar una limitación ni para cambiar estados administrativos.

## Proveniencia del revisor

Los campos obligatorios son:

- `reviewer_type`: `human` o `ai_assisted`;
- `reviewer_expertise`: `novice`, `trained`, `domain_expert` o `not_applicable`;
- `reviewer_model`: nombre del modelo cuando `reviewer_type=ai_assisted`, vacío para humanos;
- `label_status`: `human_observation` o `provisional_pseudolabel`.

`ai_assisted` requiere `reviewer_expertise=not_applicable`. Un revisor humano no puede usar `not_applicable` y una fila humana no se interpreta automáticamente como `domain_expert`. Ninguno de los dos valores de `label_status` equivale por sí mismo a `ground_truth`.

## Triage administrativo

`needs_adjudication` se activa si se cumple al menos una condición:

- `pass_a_visible_burn_scar=ambiguous`;
- `pass_a_scar_confidence=low`;
- `pass_a_event_association=indeterminate`;
- `pass_b_mode_agreement=disagree`;
- `pass_b_requires_adjudication=true`.

`expert_review_priority` es un segundo eje, con `none`, `recommended` o `required`:

- `required` si `needs_adjudication=true`;
- `required` si el competidor es `agriculture_or_harvest`, `mixed` o `unknown`;
- `required` si `observation_limitation` es distinto de `none`;
- `required` si cambia la confianza entre Pass A y Pass B;
- `recommended`, si nada anterior aplica, cuando el competidor es `soil_exposure`, `vegetation_phenology`, `moisture_or_flooding`, `water` o `urban_or_construction`;
- `none` en los demás casos.

El importador deriva `expert_review_priority` y `expert_review_reasons`. El revisor no puede escoger libremente esos campos. Las razones se guardan como códigos deterministas, por ejemplo `needs_adjudication`, `competing_land_change=soil_exposure`, `observation_limitation=cloud_or_haze` y `confidence_changed_between_passes`.

`partially_agree` no activa por sí solo `needs_adjudication` ni `required`; se conserva como evidencia de robustez incompleta.

## Independencia y límites

Los dos revisores deben usar identificadores distintos y conservar sus respuestas separadas. Pass B no puede reescribir Pass A. Un acuerdo exacto entre revisores solo describe concordancia de campos; no es confirmación ni ground truth. No se calculan exactitud, sensibilidad ni especificidad en esta ronda.

Los resultados de control no se insertan automáticamente en una ronda formal, no modifican la calibración R1 existente y no se escriben en la base de revisión existente.
