# Blind Control R1 — comparación independiente

## Estado

- Estado técnico: **pass**.
- Ronda: `control_r1`.
- Casos comparados: **7**.
- Reviewer A: `blind_control_r1_reviewer_a` — `GPT-5.6 Thinking`.
- Reviewer B: `blind_control_r1_reviewer_b` — `GPT-5.5 Thinking`.
- `label_status=provisional_pseudolabel`; no es observación humana de referencia.
- No se calculan exactitud, sensibilidad ni especificidad.
- No existe `ground_truth`, `significant_burn` ni etiqueta científica final en esta ronda.

## Acuerdo exacto por campo

| Campo | Acuerdos | Desacuerdos |
|---|---:|---:|
| `pass_a_visible_burn_scar` | 6 | 1 |
| `pass_a_scar_confidence` | 3 | 4 |
| `pass_a_event_association` | 4 | 3 |
| `pass_a_competing_land_change` | 4 | 3 |
| `observation_limitation` | 7 | 0 |
| `pass_a_notes` | 0 | 7 |
| `pass_b_mode_agreement` | 4 | 3 |
| `pass_b_confidence_after` | 4 | 3 |
| `pass_b_requires_adjudication` | 6 | 1 |
| `pass_b_notes` | 0 | 7 |

## Distribución por revisor

| Campo | Reviewer A | Reviewer B |
|---|---|---|
| `pass_a_visible_burn_scar` | {"ambiguous": 1, "no": 3, "yes": 3} | {"ambiguous": 2, "no": 3, "yes": 2} |
| `pass_a_scar_confidence` | {"high": 1, "low": 2, "medium": 4} | {"high": 1, "low": 2, "medium": 4} |
| `pass_a_event_association` | {"indeterminate": 2, "likely": 2, "possible": 1, "unlikely": 2} | {"indeterminate": 1, "likely": 2, "possible": 1, "unlikely": 3} |
| `pass_a_competing_land_change` | {"agriculture_or_harvest": 1, "mixed": 1, "none_visible": 2, "soil_exposure": 1, "urban_or_construction": 1, "vegetation_phenology": 1} | {"agriculture_or_harvest": 1, "mixed": 2, "none_visible": 1, "vegetation_phenology": 2, "water": 1} |
| `observation_limitation` | {"cloud_or_haze": 1, "mask_or_nodata": 1, "mixed": 2, "none": 3} | {"cloud_or_haze": 1, "mask_or_nodata": 1, "mixed": 2, "none": 3} |
| `pass_b_mode_agreement` | {"agree": 1, "disagree": 2, "partially_agree": 4} | {"agree": 1, "disagree": 1, "partially_agree": 5} |
| `pass_b_confidence_after` | {"high": 2, "low": 3, "medium": 2} | {"high": 2, "low": 2, "medium": 3} |
| `pass_b_requires_adjudication` | {"False": 6, "True": 1} | {"False": 5, "True": 2} |
| `needs_adjudication` | {"False": 4, "True": 3} | {"False": 5, "True": 2} |
| `expert_review_priority` | {"none": 1, "recommended": 1, "required": 5} | {"recommended": 1, "required": 6} |

## Desacuerdos por caso

### `CASE-001`

Campos: `pass_a_scar_confidence, pass_a_notes, pass_b_notes`.

- Reviewer A: {"pass_a_notes": "Se observa un cambio oscuro, continuo e irregular entre pre y post, coherente entre RGB y falso color y centrado en la zona marcada; no destaca un patrón competidor específico.", "pass_a_scar_confidence": "high", "pass_b_notes": "Ambos modos conservan una anomalía positiva extensa, continua y de morfología similar; la diferencia principal está en la intensidad alta, por lo que la robustez es parcial pero no contradice Pass A ni confirma causalidad."}
- Reviewer B: {"pass_a_notes": "El panel post muestra una zona amplia, continua y más oscura/marrón alrededor del centro, con aumento espectral de pérdida de vegetación respecto al pre. No se aprecia una parcelación agrícola u otra geometría competidora dominante dentro del patrón principal.", "pass_a_scar_confidence": "medium", "pass_b_notes": "Ambos modos conservan un patrón espacial positivo amplio y una extensión por encima de 0.20 casi idéntica. La diferencia en el extremo superior de la distribución indica variación de intensidad, pero no contradice materialmente la observación de Pass A."}

### `CASE-002`

Campos: `pass_a_competing_land_change, pass_a_notes, pass_b_confidence_after, pass_b_notes`.

- Reviewer A: {"pass_a_competing_land_change": "soil_exposure", "pass_a_notes": "El contraste multispectral post forma una zona extensa e irregular coincidente con las marcas, aunque la superficie ya era ampliamente expuesta en pre y reduce la especificidad visual.", "pass_b_confidence_after": "low", "pass_b_notes": "El patrón espacial general persiste en la mediana de ventana, pero aparece claramente atenuado y con menor extensión que en el par seleccionado; esto reduce la confianza respecto de Pass A sin invertir la interpretación, y la exposición de suelo sigue siendo una alternativa."}
- Reviewer B: {"pass_a_competing_land_change": "vegetation_phenology", "pass_a_notes": "Se observa una pérdida de vegetación post amplia e irregular cerca del centro y de los halos, con patrón no rectangular. La vegetación ya era heterogénea en pre, por lo que el cambio fenológico sigue siendo una explicación competidora parcial.", "pass_b_confidence_after": "medium", "pass_b_notes": "El patrón positivo irregular persiste en ambos modos, aunque la mediana de ventana reduce de forma marcada la intensidad y la extensión por encima de 0.20. La variación temporal limita la robustez completa y mantiene vigente la fenología de la vegetación como cambio competidor."}

### `CASE-003`

Campos: `pass_a_scar_confidence, pass_a_event_association, pass_a_competing_land_change, pass_a_notes, pass_b_confidence_after, pass_b_notes`.

- Reviewer A: {"pass_a_competing_land_change": "none_visible", "pass_a_event_association": "indeterminate", "pass_a_notes": "La pequeña anomalía central ya es visible en pre y no aparece una cicatriz nueva discernible; bruma, nubes y sectores sin datos reducen la comparabilidad.", "pass_a_scar_confidence": "low", "pass_b_confidence_after": "low", "pass_b_notes": "Los dos modos muestran una distribución muy similar, con la misma cobertura parcial y sin una anomalía nueva robusta en el centro; la concordancia temporal es consistente con Pass A, pero las limitaciones de observación mantienen la confianza baja."}
- Reviewer B: {"pass_a_competing_land_change": "water", "pass_a_event_association": "unlikely", "pass_a_notes": "No se ve una cicatriz post continua; el pequeño parche de alta respuesta en falso color aparece ya en pre y post. La lectura local está limitada por agua, píxeles enmascarados y nubes o bruma dispersa.", "pass_a_scar_confidence": "medium", "pass_b_confidence_after": "medium", "pass_b_notes": "Los dos modos muestran medianas cercanas a cero o ligeramente negativas, áreas positivas pequeñas y una distribución espacial muy similar. Esto es consistente con Pass A; las zonas de agua, máscara y cobertura atmosférica siguen limitando la observación."}

### `CASE-004`

Campos: `pass_a_notes, pass_b_mode_agreement, pass_b_notes`.

- Reviewer A: {"pass_a_notes": "Predomina un reverdecimiento general entre escenas, sin una cicatriz oscura localizada; la bruma pre y la separación temporal larga limitan la interpretación.", "pass_b_mode_agreement": "disagree", "pass_b_notes": "Los modos difieren de forma apreciable en magnitud y en la distribución local de la señal, aunque ambos carecen de una anomalía positiva localizada y persistente; la discrepancia modal no contradice el valor conservado de Pass A, pero indica robustez temporal incompleta."}
- Reviewer B: {"pass_a_notes": "El post muestra más verdor y respuesta espectral compatible con ganancia o recuperación de vegetación, no una pérdida oscura continua cerca del centro. Hay una brecha temporal larga y efectos atmosféricos o sombras que reducen la confianza visual.", "pass_b_mode_agreement": "partially_agree", "pass_b_notes": "Ambos modos mantienen una respuesta central negativa y área nula por encima de 0.20, consistente con Pass A. La mediana de ventana atenúa la ganancia espectral y desplaza el extremo superior hacia valores levemente positivos, por lo que el acuerdo no es completo y persisten las limitaciones mixtas."}

### `CASE-005`

Campos: `pass_a_event_association, pass_a_notes, pass_b_mode_agreement, pass_b_notes`.

- Reviewer A: {"pass_a_event_association": "indeterminate", "pass_a_notes": "Los cambios siguen parcelas y corredores de drenaje o agua alrededor del centro, con varias áreas enmascaradas; no se distingue una cicatriz separable de esos procesos.", "pass_b_mode_agreement": "disagree", "pass_b_notes": "El par seleccionado muestra una señal positiva mucho más extendida que la mediana de ventana, que la atenúa de forma marcada; junto con las zonas sin datos y los procesos competidores, esta discrepancia impide una lectura temporal estable, por lo que se solicita adjudicación sin modificar Pass A."}
- Reviewer B: {"pass_a_event_association": "possible", "pass_a_notes": "Hay cambio post amplio en falso color alrededor del centro, pero sigue bordes de campos, drenajes y cuerpos de agua enmascarados. El patrón puede corresponder a mezcla de manejo agrícola, exposición de suelo y humedad, por lo que no es una cicatriz visualmente aislada.", "pass_b_mode_agreement": "partially_agree", "pass_b_notes": "La mediana de ventana reduce fuertemente la respuesta positiva y el área por encima de 0.20 respecto al par seleccionado, mientras las máscaras y los bordes de campos o agua continúan condicionando el patrón. La evidencia temporal no resuelve la ambigüedad de Pass A y requiere adjudicación."}

### `CASE-006`

Campos: `pass_a_scar_confidence, pass_a_notes, pass_b_notes`.

- Reviewer A: {"pass_a_notes": "Los cambios son rectilíneos y coinciden con límites de parcelas en casi todo el panel; la bruma post reduce el contraste, pero domina un patrón agrícola.", "pass_a_scar_confidence": "medium", "pass_b_notes": "Ambos modos reproducen un patrón intenso alineado con límites rectilíneos de parcelas, aunque cambian algunos máximos locales; la persistencia del patrón agrícola refuerza la interpretación competidora de Pass A sin convertir la señal dNBR en evidencia causal de fuego."}
- Reviewer B: {"pass_a_notes": "Los cambios post están organizados por parcelas rectangulares y franjas agrícolas, con fuerte exposición de suelo o cosecha. La imagen post presenta bruma ligera, pero la geometría agrícola domina la interpretación.", "pass_a_scar_confidence": "high", "pass_b_notes": "Ambos modos conservan una respuesta positiva extensa y organizada por parcelas, con áreas por encima de 0.20 muy similares; la diferencia principal aparece en la intensidad del extremo superior. La geometría agrícola sigue dominando la interpretación y no hay contradicción material con Pass A."}

### `CASE-007`

Campos: `pass_a_visible_burn_scar, pass_a_scar_confidence, pass_a_event_association, pass_a_competing_land_change, pass_a_notes, pass_b_mode_agreement, pass_b_confidence_after, pass_b_requires_adjudication, pass_b_notes`.

- Reviewer A: {"pass_a_competing_land_change": "urban_or_construction", "pass_a_event_association": "possible", "pass_a_notes": "Hay una anomalía oscura pequeña y localizada bajo la zona marcada, visible en la comparación multispectral; el entorno construido mantiene una alternativa de cambio urbano.", "pass_a_scar_confidence": "medium", "pass_a_visible_burn_scar": "yes", "pass_b_confidence_after": "medium", "pass_b_mode_agreement": "partially_agree", "pass_b_notes": "Una anomalía localizada persiste en ambos modos cerca del centro, pero la mediana de ventana la muestra más intensa y extensa; la coincidencia espacial es parcial, no contradice Pass A y mantiene vigente la alternativa urbana o de construcción.", "pass_b_requires_adjudication": false}
- Reviewer B: {"pass_a_competing_land_change": "mixed", "pass_a_event_association": "indeterminate", "pass_a_notes": "El RGB pre y post es en gran parte estable, con un cambio espectral pequeño y localizado cerca del centro dentro de un mosaico de vegetación, suelo expuesto y asentamiento. No hay una cicatriz continua suficiente para sostener una asociación visual firme.", "pass_a_scar_confidence": "low", "pass_a_visible_burn_scar": "ambiguous", "pass_b_confidence_after": "low", "pass_b_mode_agreement": "disagree", "pass_b_notes": "La mediana de ventana amplía e intensifica de forma material la respuesta positiva respecto al par seleccionado, pasando de un cambio pequeño y localizado a una extensión mayor. Esta discrepancia contradice parcialmente la caracterización espacial de Pass A, pero no resuelve la asociación dentro del mosaico de cambios competidores; requiere adjudicación.", "pass_b_requires_adjudication": true}

## Diferencias de confianza

| Caso | Campo | Reviewer A | Reviewer B |
|---|---|---|---|
| `CASE-001` | `pass_a_scar_confidence` | high | medium |
| `CASE-003` | `pass_a_scar_confidence` | low | medium |
| `CASE-006` | `pass_a_scar_confidence` | medium | high |
| `CASE-007` | `pass_a_scar_confidence` | medium | low |
| `CASE-002` | `pass_b_confidence_after` | low | medium |
| `CASE-003` | `pass_b_confidence_after` | low | medium |
| `CASE-007` | `pass_b_confidence_after` | medium | low |

## Diferencias de asociación

| Caso | Campo | Reviewer A | Reviewer B |
|---|---|---|---|
| `CASE-003` | `pass_a_event_association` | indeterminate | unlikely |
| `CASE-005` | `pass_a_event_association` | indeterminate | possible |
| `CASE-007` | `pass_a_event_association` | possible | indeterminate |

## Diferencias de competing_land_change

| Caso | Campo | Reviewer A | Reviewer B |
|---|---|---|---|
| `CASE-002` | `pass_a_competing_land_change` | soil_exposure | vegetation_phenology |
| `CASE-003` | `pass_a_competing_land_change` | none_visible | water |
| `CASE-007` | `pass_a_competing_land_change` | urban_or_construction | mixed |

## Diferencias de observation_limitation

Sin diferencias.

## Diferencias de mode_agreement

| Caso | Campo | Reviewer A | Reviewer B |
|---|---|---|---|
| `CASE-004` | `pass_b_mode_agreement` | disagree | partially_agree |
| `CASE-005` | `pass_b_mode_agreement` | disagree | partially_agree |
| `CASE-007` | `pass_b_mode_agreement` | partially_agree | disagree |

## Diferencias de adjudicación

| Caso | Campo | Reviewer A | Reviewer B |
|---|---|---|---|
| `CASE-007` | `pass_b_requires_adjudication` | False | True |

## Triage derivado por revisor

El triage se deriva exclusivamente de campos estructurados; las notas no cambian los estados.

| Caso | Reviewer | needs_adjudication | Razones de adjudicación | expert_review_priority | Razones expertas |
|---|---|---|---|---|---|
| `CASE-001` | reviewer_a | `False` | [] | `none` | [] |
| `CASE-002` | reviewer_a | `False` | [] | `required` | ["confidence_changed_between_passes"] |
| `CASE-003` | reviewer_a | `True` | ["low_pass_a_confidence", "indeterminate_event_association"] | `required` | ["needs_adjudication", "observation_limitation=mixed"] |
| `CASE-004` | reviewer_a | `True` | ["pass_b_disagree"] | `required` | ["needs_adjudication", "observation_limitation=mixed"] |
| `CASE-005` | reviewer_a | `True` | ["ambiguous_visible_burn_scar", "low_pass_a_confidence", "indeterminate_event_association", "pass_b_disagree", "explicit_adjudication_request"] | `required` | ["needs_adjudication", "competing_land_change=mixed", "observation_limitation=mask_or_nodata"] |
| `CASE-006` | reviewer_a | `False` | [] | `required` | ["competing_land_change=agriculture_or_harvest", "observation_limitation=cloud_or_haze", "confidence_changed_between_passes"] |
| `CASE-007` | reviewer_a | `False` | [] | `recommended` | ["competing_land_change=urban_or_construction"] |
| `CASE-001` | reviewer_b | `False` | [] | `required` | ["confidence_changed_between_passes"] |
| `CASE-002` | reviewer_b | `False` | [] | `recommended` | ["competing_land_change=vegetation_phenology"] |
| `CASE-003` | reviewer_b | `False` | [] | `required` | ["observation_limitation=mixed"] |
| `CASE-004` | reviewer_b | `False` | [] | `required` | ["observation_limitation=mixed"] |
| `CASE-005` | reviewer_b | `True` | ["ambiguous_visible_burn_scar", "low_pass_a_confidence", "explicit_adjudication_request"] | `required` | ["needs_adjudication", "competing_land_change=mixed", "observation_limitation=mask_or_nodata"] |
| `CASE-006` | reviewer_b | `False` | [] | `required` | ["competing_land_change=agriculture_or_harvest", "observation_limitation=cloud_or_haze"] |
| `CASE-007` | reviewer_b | `True` | ["ambiguous_visible_burn_scar", "low_pass_a_confidence", "indeterminate_event_association", "pass_b_disagree", "explicit_adjudication_request"] | `required` | ["needs_adjudication", "competing_land_change=mixed"] |

### Uniones de triage

- Casos que requieren adjudicación por cualquiera: `CASE-003, CASE-004, CASE-005, CASE-007`.
- Casos que requieren adjudicación por ambos: `CASE-005`.
- Casos de prioridad experta requerida por cualquiera: `CASE-001, CASE-002, CASE-003, CASE-004, CASE-005, CASE-006, CASE-007`.
- Casos de prioridad experta requerida por ambos: `CASE-003, CASE-004, CASE-005, CASE-006`.
- Casos de prioridad experta recomendada por cualquiera: `CASE-002, CASE-007`.

## Lecturas compartidas y desacuerdos materiales

- Observación positiva compartida (`visible_burn_scar=yes` y `association=likely`): `CASE-001, CASE-002`.
- Observación negativa compartida (`visible_burn_scar=no`): `CASE-003, CASE-004, CASE-006`.
- Patrón agrícola compartido: `CASE-006`.
- Ambigüedad visual compartida: `CASE-005`.
- Acuerdo fuerte (todos los campos estructurados exactos): `ninguno`.
- Desacuerdo material (campos estructurados de observación o triage): `CASE-002, CASE-003, CASE-004, CASE-005, CASE-007`.

CASE-007 se mantiene como desacuerdo material; CASE-005 como ambigüedad compartida; CASE-006 como patrón agrícola compartido. CASE-001 y CASE-002 son observaciones positivas compartidas, mientras CASE-003 y CASE-004 muestran observación negativa compartida en el eje visible. Estas coincidencias describen concordancia entre revisores, no verdad científica.

## Limitaciones

- Los dos revisores son modelos IA de la misma familia; el acuerdo no mide exactitud ni independencia frente a un estándar externo.
- Las notas son texto libre y se reportan como evidencia cualitativa; no se usan para derivar triage.
- La comparación se limita a siete paneles anonimizados y a los enums del protocolo candidato v1.
- No existe ground truth y esta ronda no crea etiquetas finales, `significant_burn` ni resultados de calibración.
- Las diferencias requieren adjudicación o revisión experta según el triage administrativo; no autorizan cambiar el protocolo científico automáticamente.

## Integridad de la comparación

- Lectura SQLite read-only: `True`.
- Errores de reconciliación SQLite: `[]`.
- La comparación no escribe ni actualiza SQLite.
