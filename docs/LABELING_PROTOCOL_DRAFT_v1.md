# FirePA — borrador de protocolo de revisión humana draft-v1

## Estado y propósito

Este documento es un borrador operativo para una primera ronda de calibración
humana sobre siete eventos Level 2. Su propósito es hacer auditable la
observación de los paneles, registrar ambigüedades y descubrir qué debe
aclararse antes de congelar un protocolo formal.

La ronda no crea una verdad de referencia, no genera etiquetas para el dataset
final y no decide qué evento contiene una cicatriz. Los siete casos son una
calibración del instrumento de revisión, no una muestra de validación. El
protocolo puede cambiar después de revisar estos siete eventos. Cuando exista
una versión final congelada, cualquier ronda formal deberá reiniciarse desde
cero con esa versión y una nueva identificación de ronda.

La revisión usa únicamente las dos hojas visuales Level 2 por evento:

- hoja de evidencia multiespectral del par seleccionado;
- hoja de robustez temporal que compara selected_pair con window_median.

Los archivos y las rutas de los paneles son los que figuran en la cola ciega y
en su manifest. La cola inicial contiene exactamente siete filas pendientes y
no contiene resultados científicos auxiliares.

## Límites científicos

FIRMS representa anomalías térmicas detectadas por satélite; no representa
incendios confirmados. Una detección agrupada conserva incertidumbre de
asociación, cobertura y causa.

dNBR es evidencia espectral descriptiva. Un cambio dNBR no confirma fuego, no
define severidad, no es ground truth y no puede transformarse por sí mismo en
una clase.

Agricultura, cosecha, fenología, humedad, suelo expuesto, nubes, sombra, agua,
atmósfera y urbanización o construcción pueden producir cambios competidores.
La revisión debe registrar esas posibilidades en vez de atribuirlas
silenciosamente al evento FIRMS.

No se permite en esta ronda:

- consultar o transcribir FRP, confianza FIRMS, ranking, score de modelo o
  clase sugerida;
- definir significant_burn o cualquier umbral de severidad;
- derivar clases desde dNBR;
- entrenar modelos, crear predictores o ampliar la muestra;
- incorporar etiquetas de calibración automáticamente al dataset final;
- usar datos de 2026 como datos de observación o decisión metodológica.

Los paneles pueden mostrar sus métricas visuales existentes para conservar la
trazabilidad del artefacto. La cola no repite esas métricas ni añade scores
externos que induzcan una respuesta.

## Esquema de revisión

La cola de calibración usa exactamente estos campos administrativos y de
revisión, en este orden:

| Campo | Uso |
|---|---|
| calibration_round | Identificador de la ronda; en esta entrega es round1. |
| randomized_order | Posición ciega determinista, de 1 a 7. |
| event_id | Identificador congelado del evento. |
| reviewer_id | Identificador del revisor humano; vacío mientras esté pendiente. |
| reviewed_at | Timestamp administrativo de revisión; vacío mientras esté pendiente. |
| protocol_version | En esta cola es draft-v1. |
| quicklook_version | En esta cola es fuegopa-dnbr-quicklook-level2-v1. |
| multispectral_panel_path | Ruta exacta de la hoja multiespectral. |
| temporal_panel_path | Ruta exacta de la hoja de robustez temporal. |
| visible_burn_scar | Observación visual, sin inferirla de dNBR. |
| scar_confidence | Confianza del revisor sobre esa observación visual. |
| event_association | Fuerza de asociación visual entre la anomalía FIRMS y el cambio observado. |
| competing_land_change | Cambio alternativo visible o desconocido. |
| mode_agreement | Concordancia descriptiva entre selected_pair y window_median. |
| reviewer_notes | Notas auditables, no una clase automática. |
| review_status | Estado administrativo de la fila. |
| exclusion_reason | Motivo si la fila se excluye con razón. |
| adjudication_notes | Registro de una futura adjudicación; vacío inicialmente. |

### Valores permitidos

visible_burn_scar:

- yes
- no
- ambiguous
- unobserved

scar_confidence:

- high
- medium
- low
- not_applicable

event_association:

- likely
- possible
- unlikely
- indeterminate

competing_land_change:

- none_visible
- agriculture_or_harvest
- soil_exposure
- vegetation_phenology
- moisture_or_flooding
- cloud_or_haze
- shadow_or_atmosphere
- water
- urban_or_construction
- mixed
- unknown

mode_agreement:

- agree
- partially_agree
- disagree
- selected_pair_only
- window_median_only
- unavailable

review_status:

- pending
- reviewed
- needs_adjudication
- unobserved
- excluded_with_reason

Una observación unobserved no es una observación negativa. Cuando
visible_burn_scar sea unobserved, scar_confidence debe ser not_applicable. Si
review_status sea unobserved, mode_agreement debe ser unavailable. Las dos
filas ópticamente no observables del piloto se conservan en una tabla separada
y no entran en la cola ciega de siete eventos.

## Procedimiento de dos pasadas

### Pasada A — evidencia multiespectral

1. Tome la fila en randomized_order y abra solo
   multispectral_panel_path.
2. Observe RGB pre/post, false-color pre/post, dNBR descriptivo, máscara,
   halo FIRMS y el contexto visual del panel.
3. Registre únicamente:
   - visible_burn_scar;
   - scar_confidence;
   - event_association;
   - competing_land_change;
   - reviewer_notes.
4. No consulte FRP, confianza FIRMS, ranking, score de modelo, clase sugerida
   ni otras columnas externas durante esta pasada.
5. No use el valor numérico de dNBR para convertir la observación en una
   clase. Si la escena es ambigua, conserve ambiguous o indeterminate y
   explique la ambigüedad.

### Pasada B — robustez temporal

1. Después de cerrar la observación de la Pasada A, abra
   temporal_panel_path.
2. Registre:
   - mode_agreement;
   - cualquier cambio de confianza que el revisor quiera documentar;
   - necesidad de adjudicación;
   - notas sobre selected_pair frente a window_median.
3. No cambie silenciosamente ningún valor de la Pasada A. Si la hoja
   temporal cambia la interpretación, conserve el valor original y describa
   el motivo en reviewer_notes o adjudication_notes.
4. Una diferencia entre modos es una señal de robustez temporal, no una
   etiqueta de incendio o de ausencia de incendio.

### Reglas administrativas

- La cola inicial permanece pending y con los campos científicos vacíos.
- Una fila reviewed requiere reviewer_id, reviewed_at, las observaciones de
  ambas pasadas y todos los valores dentro de los enums.
- Una fila needs_adjudication debe conservar la decisión original y explicar
  la disputa en adjudication_notes.
- Una fila excluded_with_reason requiere exclusion_reason.
- La fecha reviewed_at es administrativa; no convierte datos de 2026 en datos
  científicos del estudio.
- Ninguna función de validación debe inferir, completar o corregir etiquetas.

## Ronda de calibración

La semilla de randomized_order es 20260721. El algoritmo es
random.Random(seed).shuffle aplicado a los siete IDs congelados y la posición
resultante queda registrada en la cola y el manifest. El orden es reproducible
y no se decide por FRP, confianza FIRMS, dNBR, facilidad visual o conveniencia.

Los artefactos de esta entrega son:

- outputs/human_review/calibration_round1_blinded.csv
- outputs/human_review/calibration_round1_manifest.json
- outputs/human_review/calibration_round1_instructions.md
- outputs/human_review/unobserved_events.csv

La cola principal no contiene FRP, confianza FIRMS, median, p90, áreas,
expected class, model score, predicted class ni significant_burn. La tabla
separada de no observables contiene solo el esquema definido para ese caso y
mantiene significant_burn vacío.

## Próximo paso humano

Una persona autorizada puede revisar los siete pares de paneles en el orden
ciego y devolver una copia completada al validador. Después de esa calibración
se debe decidir si el esquema, los enums y las instrucciones son adecuados.
Solo una decisión explícita puede congelar una versión posterior del
protocolo. Hasta entonces no se crea significant_burn, no se incorporan
etiquetas al dataset final y no se entrena ningún modelo.
