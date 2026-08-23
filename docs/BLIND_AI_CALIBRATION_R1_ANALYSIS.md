# Análisis metodológico de la calibración ciega asistida por IA R1

**Estado:** análisis local de una calibración piloto; no es una ronda científica ni un conjunto de etiquetas finales.

**Ronda:** `round1` / `blind_ai_calibration_r1`
**Grano:** una fila de revisión por `CASE-*`, con `reviewer_type=ai_assisted` y `label_status=provisional_pseudolabel`.
**Cobertura:** 7 casos, 7 ítems de revisión y 1 revisor IA (`gpt_5_6_thinking_calibration_r1`).

## Propósito

La primera calibración ciega se usa para comprobar si el contrato de revisión, sus estados y sus reglas de incertidumbre capturan los casos difíciles antes de considerar la ronda formal de 28 eventos. El análisis identifica ambigüedad, confianza baja, asociaciones indeterminadas, confusores visuales y desacuerdos entre pasadas.

Los valores `yes`, `no`, `ambiguous`, `likely` o similares se reportan aquí como observaciones consignadas por el revisor dentro de un panel. No se convierten en clases científicas, no prueban causalidad y no definen `significant_burn`.

## Metodología

Se leyeron el protocolo v1, los checkpoints del piloto y del paquete ciego, el contrato de la herramienta, el esquema y el store de revisión, el informe de importación, la base SQLite y el mapa privado de casos. La base se abrió mediante una conexión SQLite de solo lectura con `PRAGMA query_only=ON`; el mapa privado se usó únicamente para comprobar que las siete filas importadas corresponden al conjunto `CASE-001` a `CASE-007`.

El resumen reproducible se genera con [`scripts/summarize_blind_ai_calibration.py`](../scripts/summarize_blind_ai_calibration.py). El script no abre Earth Engine, no escribe SQLite y no modifica datos, paneles ni rasters. Los timestamps administrativos de la base no se interpretan como observaciones científicas.

El informe de importación registra `inserted=7`, `unchanged=0`, `errors=[]`, `ground_truth=false` y `final_scientific_labels_created=false`. Las siete filas tienen `label_status=provisional_pseudolabel`; ese valor describe el origen/provisionalidad de la revisión y nunca equivale a ground truth.

## Resumen estadístico

### Distribuciones de Pass A

| Campo | Distribución observada |
|---|---|
| `pass_a_visible_burn_scar` | `yes`: 3; `no`: 1; `ambiguous`: 3; `unobserved`: 0 |
| `pass_a_scar_confidence` | `high`: 1; `medium`: 3; `low`: 3; `not_applicable`: 0 |
| `pass_a_event_association` | `likely`: 3; `possible`: 1; `unlikely`: 1; `indeterminate`: 2 |
| `pass_a_competing_land_change` | `none_visible`: 2; `agriculture_or_harvest`: 2; `cloud_or_haze`: 1; `soil_exposure`: 1; `mixed`: 1; los demás códigos: 0 |

### Distribuciones de Pass B y cambios de confianza

| Campo | Distribución observada |
|---|---|
| `pass_b_mode_agreement` | `agree`: 1; `partially_agree`: 6; `disagree`: 0; `selected_pair_only`: 0; `window_median_only`: 0; `unavailable`: 0 |
| `pass_b_confidence_after` | `high`: 1; `medium`: 4; `low`: 2; `not_applicable`: 0 |
| Cambio `pass_a_scar_confidence -> pass_b_confidence_after` | `high->high`: 1; `medium->medium`: 3; `low->low`: 2; `low->medium`: 1 |

Solo un caso cambió de confianza entre pasadas (`CASE-006`, `low->medium`). Los otros seis mantuvieron su nivel. El cambio de confianza es una señal de revisión especializada, no una corrección automática hacia una clase.

### Incertidumbre, confusores y adjudicación

| Indicador | Conteo |
|---|---:|
| Adjudicaciones ya solicitadas por el campo importado `pass_b_requires_adjudication=true` | 0 |
| Casos que requieren adjudicación bajo las reglas deterministas propuestas | 3 |
| Casos `visible_burn_scar=ambiguous` | 3 |
| Casos con confianza baja en Pass A | 3 |
| Casos con confianza baja en Pass B | 2 |
| Casos `event_association=indeterminate` | 2 |
| Casos con algún competing land change distinto de `none_visible` | 5 |
| Casos con `mode_agreement=partially_agree` | 6 |

Los cinco casos con un competing land change se distribuyen así: `agriculture_or_harvest` en 2, `cloud_or_haze` en 1, `soil_exposure` en 1 y `mixed` en 1. Las categorías describen explicaciones visuales competidoras consignadas en el panel; no son decisiones sobre la causa real.

## Resultados por CASE ID

La columna “estado actual” es el estado que quedó almacenado después de la importación. “Estado propuesto” es el resultado del triage de este análisis; no se escribió en SQLite.

| CASE ID | Pass A: visible / confianza / asociación / competidor | Pass B: confianza / acuerdo | Cambio | Estado actual | Estado propuesto | Revisión adicional |
|---|---|---|---|---|---|---|
| `CASE-001` | `yes` / `high` / `likely` / `none_visible` | `high` / `partially_agree` | no | `pass_b_complete` | `pass_b_complete` | no automática |
| `CASE-002` | `yes` / `medium` / `likely` / `none_visible` | `medium` / `partially_agree` | no | `pass_b_complete` | `pass_b_complete` | no automática |
| `CASE-003` | `ambiguous` / `low` / `indeterminate` / `cloud_or_haze` | `low` / `agree` | no | `pass_b_complete` | `needs_adjudication` | adjudicación + especializada |
| `CASE-004` | `no` / `medium` / `unlikely` / `mixed` | `medium` / `partially_agree` | no | `pass_b_complete` | `pass_b_complete` | especializada |
| `CASE-005` | `ambiguous` / `low` / `indeterminate` / `agriculture_or_harvest` | `low` / `partially_agree` | no | `pass_b_complete` | `needs_adjudication` | adjudicación + especializada |
| `CASE-006` | `ambiguous` / `low` / `possible` / `agriculture_or_harvest` | `medium` / `partially_agree` | `low->medium` | `pass_b_complete` | `needs_adjudication` | adjudicación + especializada |
| `CASE-007` | `yes` / `medium` / `likely` / `soil_exposure` | `medium` / `partially_agree` | no | `pass_b_complete` | `pass_b_complete` | confusor registrado; no trigger automático solicitado |

### Casos que deberían recibir revisión adicional

- **Adjudicación:** `CASE-003`, `CASE-005`, `CASE-006`.
- **Revisión especializada:** `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`.
- **Unión de ambas listas:** `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`.

`CASE-007` conserva `soil_exposure` como confusor explícito. La regla solicitada para revisión especializada nombra agricultura/cosecha, mixto, desconocido, limitaciones de nube/bruma/máscara y cambios de confianza; por eso no se activa automáticamente para `CASE-007`. Si el equipo decide que todo confusor requiere especialista, `soil_exposure` debe agregarse como cambio explícito de protocolo, no inferirse retrospectivamente.

## Evaluación de los problemas del draft-v1

| Problema | Evidencia R1 | Evaluación y corrección propuesta |
|---|---|---|
| 1. Todos terminaron con `pass_b_requires_adjudication=false`. | 0 solicitudes importadas, aunque 3 casos cumplen reglas de incertidumbre. | Es una brecha de captura de triage, no evidencia de que todos sean robustos. v2 separa la decisión del revisor del estado administrativo derivado y activa `needs_adjudication` determinísticamente. |
| 2. Tres casos fueron ambiguos. | `CASE-003`, `CASE-005`, `CASE-006`. | La ambigüedad debe activar adjudicación. Nunca se promueve a `yes` o `no` por defecto. |
| 3. Existen confianzas bajas. | 3 en Pass A; 2 permanecen bajas en Pass B. | `low` expresa incertidumbre del observador, no una clase negativa. Activa adjudicación cuando se encuentra en Pass A, y se conserva como evidencia de robustez limitada en Pass B. |
| 4. Existen asociaciones indeterminadas. | `CASE-003`, `CASE-005`. | La asociación temporal/eventual es distinta de la observación visual. `indeterminate` activa adjudicación y no se resuelve por mayoría textual. |
| 5. Hay confusores. | 5 casos: agricultura/cosecha (2), nube/bruma (1), suelo expuesto (1), mixto (1). | Se mantienen como códigos de competing land change. Agricultura/cosecha, mixto, desconocido y limitaciones de nube/bruma/máscara activan revisión especializada; ningún confusor produce una clase automática. |
| 6. Seis de siete tienen acuerdo parcial. | `partially_agree`: 6; `agree`: 1; `disagree`: 0. | `partially_agree` solo no activa adjudicación, pero siempre se registra como robustez incompleta. Acuerdo entre pasadas no es confirmación científica. |
| 7. `none_visible` puede malinterpretarse como ausencia de explicación. | 2 casos tienen `none_visible`. | v2 define `none_visible` como “no se observó un cambio competidor en el panel revisado”. No significa que otra explicación no exista fuera del panel o que haya sido descartada científicamente. |

## Limitaciones de usar un único revisor IA

Esta R1 no estima exactitud, sensibilidad, especificidad, concordancia interobservador ni calibración probabilística. Hay un único revisor IA y solo siete casos; no existe un adjudicador humano independiente que permita distinguir acuerdo real de repetición de un mismo sesgo. Además, el acuerdo entre Pass A y Pass B puede ser consistencia interna del mismo revisor, no validación externa.

La confianza es ordinal (`high`, `medium`, `low`), no una probabilidad calibrada. Los confusores y las limitaciones de nube, bruma o máscara pueden restringir lo que se ve en el panel. La unión por el mapa privado hace posible el análisis de `CASE-*`, pero los artefactos originales Pass A/Pass B no forman parte del repositorio público de esta revisión.

Por estas razones, `provisional_pseudolabel` describe una salida provisional asistida por IA. No es ground truth, no es una etiqueta científica final y no debe entrar automáticamente en entrenamiento, métricas de desempeño o la ronda formal de 28 eventos.

## Recomendación del siguiente paso

1. Adoptar el contrato operativo de [`LABELING_PROTOCOL_DRAFT_v2.md`](LABELING_PROTOCOL_DRAFT_v2.md) como propuesta, sin declararlo congelado.
2. Revisar/adjudicar `CASE-003`, `CASE-005` y `CASE-006`, y hacer revisión especializada de `CASE-003`, `CASE-004`, `CASE-005` y `CASE-006`.
3. Registrar por separado observación visual, asociación, confusor, limitación y nivel de confianza; permitir mantener `ambiguous`, `indeterminate` o `unobserved` cuando la evidencia no resuelva el caso.
4. Repetir una calibración pequeña con un observador humano o un segundo revisor independiente antes de abrir la ronda formal de 28 eventos.
5. Solo después de revisar el protocolo y aceptar sus límites decidir si la ronda formal puede comenzar. Ningún resultado de esta R1 se promueve automáticamente.

## Declaración de estado científico

En este análisis no se crearon etiquetas científicas finales, `significant_burn` ni ground truth. No se modificaron datos científicos, paneles o rasters; no se usaron datos de 2026; no se consultó Earth Engine; no se entrenó ningún modelo y no se hizo push.
