# external_reference_check_v1

**Fecha del contrato:** 2026-08-09
**Unidad de análisis:** clusters provisionales ya congelados en
`outputs/clustering/r1500_t06/events.csv`
**Propósito:** chequeo exploratorio de asociación espacio-temporal contra dos
incidentes documentados externamente por el investigador.

Este contrato no crea una capa de clasificación, no convierte un cluster en un
incendio confirmado y no sustituye observaciones humanas. El nombre deliberado
de la capa es `external_reference_check_v1`; no se denomina `ground_truth`,
`validation_dataset` ni `confirmed_labels`.

## Referencias admitidas

Solo se usan las dos referencias proporcionadas en la solicitud de
investigación:

| ID | Nombre | Ubicación | Coordenadas | Fecha(s) | Ventana temporal inclusiva |
|---|---|---|---|---|---|
| `REFERENCE-001` | Cerro Los Picachos | Olá, Coclé | `8.42097, -80.65114` | `2025-01-16` | `2025-01-15` → `2025-01-17` |
| `REFERENCE-002` | Cerro Guacamaya | Penonomé, Coclé | `8.516667, -80.433333` | `2025-01-23` → `2025-01-27` | `2025-01-23` → `2025-01-27` |

La procedencia declarada es `manual_osint_outside_pipeline`. Las fuentes exactas
están registradas en el registry canónico
`references/external_reference_sources_v1.json`, con 7 fuentes para los 2
incidentes, URLs de procedencia, fechas, localizaciones y estados de causa. Las
coordenadas de matching siguen siendo anclas aproximadas proporcionadas por el
investigador y no se atribuyen a las fuentes.

El schema v1 separa incidentes, fuentes y anclas de matching:

| Campo | Uso |
|---|---|
| `incident_id` | `REFERENCE-001` o `REFERENCE-002` |
| `source_id` | Identificador estable `SOURCE-001` a `SOURCE-007` |
| `publisher` / `publisher_type` | Publicador y distinción prensa/institución |
| `publication_date` | Fecha de publicación localizada |
| `reported_event_date*` | Fecha o ventana reportada por la fuente |
| `reported_area_ha` | Afirmación de área por fuente, sin adjudicación |
| `cause_status` | `null` o `suspected_intentional`, sin confirmación |
| `url` | URL de procedencia, no input del pipeline |
| `researcher_summary` | Resumen de trabajo, no cita directa |

## Método de matching

1. Se lee la tabla existente de `r1500_t06` y se exige que contenga exactamente
   611 `event_id` únicos, todos con `configuration_id=r1500_t06`.
2. No se invoca el algoritmo de clustering y no se modifica la tabla de
   eventos. La decisión usa los centroides ya calculados.
3. La distancia entre la coordenada de referencia y el centroide usa la misma
   métrica local del clustering: proyección WGS84 a `EPSG:32617` y distancia
   euclidiana en metros.
4. Se conserva un match cuando `distance_m <= 5000` y los intervalos temporales
   se intersectan. El límite espacial es inclusivo y las fechas finales de las
   ventanas proporcionadas también son inclusivas.
5. Se conservan todos los matches. No se elige solo el más cercano.

Cada fila de `matches.csv`/`matches.json` contiene la relación administrativa
`external_reference_match=true`, el `event_id`, distancia, ventana de cluster,
solapamiento temporal, número de detecciones, FRP máximo/medio/suma,
satélites, composición día/noche, `possible_chain_merge`, duración,
percentiles descriptivos y procedencia. No contiene `fire=true` ni una etiqueta
de incendio.

El percentile de un match es un rango descriptivo contra los 611 clusters:

```text
100 × (número de valores de la cohorte menores o iguales al valor del match) / 611
```

La distribución completa registra `median`, `IQR`, `p90`, `p95` y `p99` para
`max_frp`, `mean_frp`, `n_detections` y duración. Se usa
`statistics.median` para la mediana y nearest-rank para q25, q75, p90, p95 y
p99. No se fabrican pruebas inferenciales con dos referencias.

## Guacamaya y la ventana temporal t06

El incidente de varios días se inspecciona sin cambiar `r1500_t06`. La
clasificación administrativa es `multiple_clusters` cuando hay más de un
cluster matched. Si existen separaciones mayores que seis horas, se registra
`possible_t06_fragmentation=true` y se explica que una actividad térmica
persistentemente conectada podría quedar representada por varios clusters.
Esto es una limitación o comportamiento de representación, no un bug automático
ni una inferencia causal sobre el incidente externo.

## Seguimiento óptico

El análisis consulta únicamente la cohorte óptica local ya existente de 30
eventos. No la amplía. Para un match dentro de esa cohorte, los campos
`selected_pair_available`, `window_median_available` y
`nbr_dnbr_descriptive_available` solo referencian evidencia descriptiva local
ya existente; no producen nuevos assets. Para cualquier match fuera de la
cohorte se registra `optical_followup_available=false`.

## Límites científicos y administrativos

- La asociación espacio-temporal no demuestra causalidad.
- FRP, duración y número de detecciones se comparan descriptivamente.
- No se reportan accuracy, recall, cobertura completa ni validación
  institucional.
- Las revisiones IA existentes siguen siendo `provisional_pseudolabels`.
- La infraestructura `formal_review_28`, blind packages, SQLite, migraciones,
  tests y assets `window_median` se conserva. La revisión humana formal se
  mantiene sin ejecutar.
- `formal_review_status=deferred` por
  `QUALIFIED_REVIEWER_UNAVAILABLE`; `execution_authorized=false`.
- `supervised_modeling_gate=deferred` por
  `NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE`.
- No se generan target, `significant_burn`, modelo ni variables ambientales.
- No hay acceso de red ni consultas Earth Engine.

## Artefactos

El código y las pruebas quedan versionados. Los resultados generados se
mantienen fuera de Git en:

```text
outputs/external_reference_check_v1/
```

Contiene `matches.csv`, `matches.json`, `reference_summary.csv`,
`cohort_distribution.csv`, `report.json`, `report.md`, tres SVG descriptivos y
`manifest.json` con hashes SHA-256. El lanzador es
`scripts/run_external_reference_check.py`; el verificador read-only es
`scripts/verify_external_reference_check.py`.
