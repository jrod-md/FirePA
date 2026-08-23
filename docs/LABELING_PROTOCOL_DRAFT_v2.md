# Labeling Protocol — Draft v2

**Estado:** propuesta de trabajo; no congelada.
**Base:** `LABELING_PROTOCOL_DRAFT_v1.md` y análisis de la calibración ciega asistida por IA R1.
**Alcance:** observación visual y control de calidad de revisión; no define una clase científica final.

## 1. Límites que se conservan

Este documento no crea ground truth, no define `significant_burn`, no inicia la ronda formal de 28 eventos, no autoriza entrenamiento de modelos y no convierte observaciones de panel en afirmaciones causales. El dNBR y las salidas visuales siguen siendo descriptivos/provisionales dentro de los límites documentados por el proyecto.

Una fila de revisión puede registrar lo que un observador ve, con qué confianza lo ve y qué asociación considera posible. Eso no equivale a demostrar que un incendio causó el cambio ni a demostrar que no lo causó.

## 2. Separar observación, asociación y causa

### Observación visual

`pass_a_visible_burn_scar` usa únicamente:

- `yes`: se observó una señal visual compatible con una cicatriz en el panel;
- `no`: no se observó esa señal en el panel;
- `ambiguous`: la señal no permite una decisión visual estable;
- `unobserved`: la evidencia no es utilizable para esa observación.

Estos valores describen el panel revisado. No son clases de incendio, severidad o superficie afectada.

### Confianza

`pass_a_scar_confidence` y `pass_b_confidence_after` usan `high`, `medium`, `low` o `not_applicable`. Son niveles ordinales de confianza del observador en la observación consignada; no son probabilidades calibradas ni porcentajes de exactitud.

### Asociación con el evento

`pass_a_event_association` usa `likely`, `possible`, `unlikely` o `indeterminate`. Describe la fuerza de la asociación visual/temporal que el observador puede sostener con el material disponible. `likely` no significa causalidad demostrada y `indeterminate` no debe resolverse como `unlikely` por conveniencia del flujo.

## 3. Competing land change y el significado de `none_visible`

`pass_a_competing_land_change` registra una explicación visual competidora que sí aparece en el panel: `none_visible`, `agriculture_or_harvest`, `soil_exposure`, `vegetation_phenology`, `moisture_or_flooding`, `cloud_or_haze`, `shadow_or_atmosphere`, `water`, `urban_or_construction`, `mixed` o `unknown`.

`none_visible` significa exclusivamente: **no se observó un cambio competidor en el panel revisado**. No significa que no exista otra explicación en la realidad, en otra fecha, fuera del encuadre, debajo de una nube o fuera de la capacidad del sensor. Tampoco convierte la observación en una confirmación de incendio.

Un confusor se registra como evidencia de incertidumbre. Ningún código de competing land change debe producir automáticamente una decisión positiva o negativa.

## 4. Pass B y acuerdo

`pass_b_mode_agreement` usa `agree`, `partially_agree`, `disagree`, `selected_pair_only`, `window_median_only` o `unavailable`.

- `agree` significa que las observaciones comparadas coinciden en el aspecto que se revisó; no significa que sean verdaderas ni confirmadas.
- `partially_agree` significa que hay consistencia solo en una parte del juicio o del panel. Es evidencia de robustez incompleta y se conserva siempre, pero por sí sola no obliga a adjudicación.
- `disagree` significa que la comparación requiere resolución explícita; activa `needs_adjudication`.
- `selected_pair_only`, `window_median_only` y `unavailable` describen cobertura de la comparación, no una clase científica.

La confianza puede cambiar entre Pass A y Pass B. Cualquier cambio de confianza se registra como motivo de revisión especializada; no se interpreta como una mejora verdadera ni como una degradación científica automática.

## 5. Triage determinista

El triage es administrativo y derivado. No cambia los valores de observación ni crea etiquetas finales. Para cada caso, se calcula:

```text
needs_adjudication = (
    pass_a_visible_burn_scar == "ambiguous"
    OR pass_a_scar_confidence == "low"
    OR pass_a_event_association == "indeterminate"
    OR pass_b_mode_agreement == "disagree"
    OR pass_b_requires_adjudication == true
)

specialized_review_required = (
    pass_a_competing_land_change IN {"agriculture_or_harvest", "mixed", "unknown"}
    OR cloud_haze_or_mask_limitation_is_in_notes == true
    OR pass_a_scar_confidence != pass_b_confidence_after
)
```

La condición `specialized_review_required` debe conservar motivos legibles, por ejemplo `competing_land_change=agriculture_or_harvest`, `limitation_in_notes=cloud_haze_or_mask` o `confidence_changed_between_passes`. Es un indicador de revisión, no un `yes`/`no` científico.

El estado administrativo propuesto se deriva así:

1. Si `needs_adjudication` es verdadero, usar `review_status=needs_adjudication`.
2. Si no lo es y Pass B está completo, usar `pass_b_complete` y conservar cualquier motivo de revisión especializada.
3. Si Pass A está completo pero Pass B no, usar `pass_a_complete`.
4. Si no hay evidencia utilizable, usar `unobserved`; si el caso se excluye, usar `excluded_with_reason` con una razón explícita.

`partially_agree` no aparece por sí solo en la condición de adjudicación. Si se combina con una condición de la primera expresión, sí se adjudica por esa otra condición.

La regla propuesta para R1 marca como adjudicación `CASE-003`, `CASE-005` y `CASE-006`. Marca para revisión especializada `CASE-003`, `CASE-004`, `CASE-005` y `CASE-006`. `soil_exposure` se conserva como confusor; si se quiere que todo confusor active especialista, deberá aprobarse y documentarse una ampliación explícita de esta lista.

## 6. Proveniencia y estado de las etiquetas

El esquema debe conservar separados:

- `reviewer_type`: `human` o `ai_assisted`;
- `label_status`: `human_observation` o `provisional_pseudolabel`.

`provisional_pseudolabel` indica una salida provisional asistida por IA. Nunca equivale a `ground_truth`, aunque Pass A y Pass B coincidan. No se promueve automáticamente a `human_observation`, no se incorpora a entrenamiento y no se usa como verdad de referencia.

La adjudicación futura debe mantener la trazabilidad de los motivos y permitir una salida no resuelta (`ambiguous`, `indeterminate` o `unobserved`) cuando la evidencia no sea suficiente. Resolver administrativamente un caso no obliga a fabricar una certeza científica.

## 7. Secuencia antes de la ronda formal

1. Aplicar estas reglas a la calibración piloto y revisar los casos señalados.
2. Obtener una revisión humana o independiente de los casos que requieran adjudicación y de los que requieran especialista.
3. Revisar si el protocolo representa correctamente los desacuerdos y confusores; en particular, mantener explícita la semántica de `none_visible`.
4. Ejecutar una calibración de control y documentar sus límites.
5. Solo tras una decisión explícita del equipo considerar el inicio de la ronda formal de 28 eventos.

Los resultados de la calibración no entran automáticamente en la ronda formal. Este documento sigue siendo un draft y no declara el protocolo congelado.

## 8. No hacer

- No crear `significant_burn` a partir de estas columnas.
- No llamar ground truth a una fila IA, a un acuerdo entre pasadas o a una adjudicación sin un proceso de referencia aprobado.
- No interpretar `none_visible`, `unlikely` o `no` como ausencia científica demostrada.
- No usar la calibración para cambiar paneles, rasters, inventarios o datos científicos.
- No consultar Earth Engine ni incorporar datos de 2026 dentro de esta fase.
