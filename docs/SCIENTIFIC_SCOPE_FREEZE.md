# FirePA — scientific scope freeze

**Fecha:** 2026-08-09
**Base de trabajo:** `22ad92a72a81f3d8bec6938dd625634d731177ee`
**Estado:** cierre analítico vigente para el checkout local

Este documento cierra por ahora la decisión de no ejecutar la revisión humana
formal de los 28 eventos. No hay acceso a revisores humanos con formación
suficiente en teledetección e incendios para producir observaciones
científicamente defendibles. El propietario del proyecto no se considera un
reviewer experto por defecto y dos revisores casuales no son un sustituto
válido.

## Gates actuales

```text
formal_review_status       = deferred
formal_review_reason       = QUALIFIED_REVIEWER_UNAVAILABLE
execution_authorized       = false
formal_review_executed     = false
supervised_modeling_gate   = deferred
modeling_gate_reason       = NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE
environmental_extraction   = not_authorized
```

La infraestructura formal existente permanece preparada para una reapertura
profesional futura sin alterar los resultados actuales. Se conservan
`LABELING_PROTOCOL_v1`, `formal_review_28`, SQLite, blind packages, assets
`window_median`, tests, migraciones y la infraestructura de auditoría. El
paquete administrativo local sigue `prepared/not_started`; esa representación
no se muta para cerrar la decisión científica. No hay observaciones humanas
formales, perfiles vinculados, Pass A ni Pass B.

Las salidas IA existentes permanecen `provisional_pseudolabels`. No son
observaciones humanas ni una referencia científica. No se genera target, no se
genera `significant_burn` y no se entrena ningún modelo.

## Capacidad que FirePA sí soporta actualmente

- adquisición FIRMS reproducible;
- clustering espacio-temporal provisional;
- seguimiento óptico Sentinel-2;
- evidencia `selected_pair`/`window_median`;
- NBR/dNBR descriptivo;
- procedencia e infraestructura de auditoría;
- matching exploratorio contra referencias externas.

El último punto corresponde a `external_reference_check_v1`: una relación
administrativa espacio-temporal contra dos referencias proporcionadas por el
investigador. La procedencia externa quedó completa en
`references/external_reference_sources_v1.json`: 7 fuentes para 2 incidentes,
con hash `6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49`.
No es una clasificación, una etiqueta ni una métrica de desempeño.

## Capacidad que FirePA no soporta actualmente

- clasificación confirmada de incendios forestales;
- ground truth;
- predicción supervisada;
- monitoreo operacional;
- alertas en tiempo real;
- estimación de severidad;
- validación institucional.

## Decisiones congeladas

- `r1500_t06` permanece congelado para este análisis: radio de 1,500 m,
  ventana temporal de 6 h, componentes conexas y `EPSG:32617`.
- No se cambian clustering, Sentinel-2, dNBR, AOI, máscaras ni políticas
  ópticas.
- No se consultan Earth Engine y no se agregan ERA5, WorldCover, DEM ni otras
  variables ambientales.
- No se construye UI pública ni dashboard interactivo.
- El análisis externo conserva todos los matches dentro de 5 km con
  intersección temporal; no selecciona solo el más cercano.
- `possible_chain_merge` se conserva como atributo del cluster; no se convierte
  en una etiqueta de incendio.

## Chequeo externo de enero de 2025

El chequeo local sobre los 611 clusters encontró 0 asociaciones que cumplieran
simultáneamente la distancia y la ventana de `REFERENCE-001` (Cerro Los
Picachos), y 6 asociaciones para `REFERENCE-002` (Cerro Guacamaya). Guacamaya
queda representada por múltiples clusters; la separación mayor que t06 se
registra como posible limitación de representación, no como bug automático.

Ninguno de los seis matches pertenece a la cohorte óptica existente de 30
eventos, por lo que no se amplían assets y el seguimiento óptico queda
`optical_followup_available=false` para todos ellos.

Las fuentes se distribuyen como 1 para `REFERENCE-001` y 6 para
`REFERENCE-002`. Las coordenadas de matching son anclas aproximadas
proporcionadas por el investigador, no coordenadas reclamadas por las fuentes.
Para Guacamaya se conservan por separado las áreas 1,035, >1,050 y alrededor
de 1,500 ha, además de los estados `null` y `suspected_intentional`; no se
elige un área verdadera ni se confirma arson. La cobertura manual OSINT fue
6 artículos en enero, 1 en febrero y 0 localizados en marzo y abril. No
qualifying articles were located during the manual OSINT search for March or
April 2025. Esto no afirma ausencia de incendios ni de actividad térmica, y la
búsqueda no se declara exhaustiva.

Los resultados completos, hashes y limitaciones están en
`docs/EXTERNAL_REFERENCE_CHECK_RESULTS_2025.md` y en los outputs locales
ignorados por Git.

## Reapertura futura

Una revisión profesional futura puede reabrir esta extensión si se registran
revisores calificados, el protocolo vigente, la trazabilidad de observaciones y
un target defendible. Esa reapertura debe ser una decisión explícita y no puede
inferirse desde este chequeo exploratorio, desde pseudolabels IA ni desde
percentiles descriptivos.

## Estado final del piloto científico — 2026-08-09

```text
DETECTION PIPELINE                 = complete for pilot
OPTICAL FOLLOW-UP                  = complete for pilot
CALIBRATION                        = complete
FORMAL REVIEW INFRASTRUCTURE      = complete; execution deferred
EXTERNAL REFERENCE CHECK           = complete
EXTERNAL REFERENCE PROVENANCE      = complete; 7 sources / 2 incidents
SUPERVISED MODELING                = deferred
ENVIRONMENTAL FEATURES             = deferred
PUBLIC UI                          = not part of pilot
```

El informe reproducible final está en
`docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md`. El diagnóstico de Los Picachos
clasifica el cero oficial como `SPATIAL_THRESHOLD_MISS`: hubo señal FIRMS
contemporánea, pero la detección más cercana quedó a 10,400.826 m. El chequeo
oficial permanece en 0 matches para Los Picachos y 6 para Guacamaya; los
diagnósticos no modifican `external_reference_check_v1` ni `r1500_t06`.

Los outputs estáticos y su manifest SHA-256 están en
`outputs/final_scientific_report/`, fuera de Git. La fase final fue local y no
realizó nuevas consultas de red o Earth Engine. No hay target, modelo,
`significant_burn`, ground truth ni afirmación operacional. El cierre v1 está
descrito en `docs/FIREPA_PILOT_V1_FREEZE.md`; cualquier cambio científico o de
adjudicación externa requiere una nueva versión.
