# FirePA

FirePA is a reproducible remote-sensing research pilot studying provisional
thermal events in Coclé, Panamá, during `2025-01-01 → 2025-04-30`.

This repository contains a public static research experience in `site/` and a
public analytical package in `site-data/`. The experience explains the study
and exposes the approved public evidence; it is **NOT REAL-TIME. NOT
OPERATIONAL.**

The public package contains exactly 611 provisional thermal events as
analytical units. They are not automatically confirmed wildfires, burn
perimeters, ground truth, severity classifications, predictions, or alerts.

## Public release boundary

A clean clone can build and inspect the public static research experience and
the public analytical package. Full regeneration of the research pipeline
requires excluded raw/reference inputs and, for some stages, external services
described in the documentation. Those inputs and services are not silently
replaced with synthetic data.

## Frontend quick start

From the public frontend directory:

```powershell
cd site
npm ci
npm run build
npm run test
```

The build uses the tracked Coclé presentation derivative when the local,
non-redistributed source boundary is absent. If that source is available
locally, the build can deterministically regenerate and verify the derivative.

## Scientific and licensing boundaries

- FirePA-authored source code is covered by [`LICENSE`](LICENSE), subject to
  the exclusions in [`NOTICE.md`](NOTICE.md).
- `site-data/` contains public derived analytical artifacts, not raw FIRMS
  rows or private review mappings.
- NASA FIRMS, Sentinel-2, Coclé boundary data, external references, and other
  scientific materials retain their source-specific conditions. No source
  license is inferred here; see [`SOURCES.md`](SOURCES.md).
- `site/public/assets/mineral-field.png` is a decorative authored/generative
  surface with no scientific meaning. Its provenance is recorded in
  [`docs/ASSET_PROVENANCE.md`](docs/ASSET_PROVENANCE.md).

The remainder of this document records the scientific pipeline, its current
state, and the limits of what the evidence supports.

## Estructura

- `data/raw/`: entradas descargadas, inmutables y fuera de Git.
- `data/raw/manifests/`: manifests por fuente/fragmento, sin claves secretas.
- `data/interim/`: reservado para transformaciones intermedias posteriores.
- `data/processed/`: salida normalizada de esta etapa, fuera de Git.
- `data/reference/`: fuente oficial local y GeoJSON reproducido para el filtro,
  fuera de Git.
- `references/`: registro canónico de procedencia externa, separado de los
  datos y outputs ignorados.
- `scripts/`: puntos de entrada ejecutables.
- `src/fuegopa/`: configuración e implementación Python.
- `tests/`: pruebas unitarias sin datos de producción.
- `outputs/`: reportes generados, fuera de Git.
- `docs/PREFLIGHT.md`: alcance, decisiones abiertas y riesgos antes de avanzar.
- `docs/CLUSTERING_DESIGN.md`: método, grilla, estabilidad y decisiones abiertas
  del experimento de clustering.

## Instalación

Se requiere Python 3.10 o posterior. La implementación de esta etapa usa la
biblioteca estándar; `pytest` se instala como dependencia de desarrollo.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

En el entorno de trabajo del proyecto:

```powershell
conda activate fuegopa
python -m pip install -e ".[dev]"
```

## Ejecutar con un CSV local

Primero extraiga y valide el límite oficial disponible en el checkout:

```powershell
python scripts/prepare_cocle_boundary.py
```

El script selecciona `nomb_prov = Coclé` desde `limi_prov_a.shp`, conserva las
partes, transforma de `EPSG:32617` a `EPSG:4326`, valida el GeoJSON y genera el
reporte `outputs/cocle_boundary_validation.*` junto con la figura de referencia.
El XML de la fuente declara `CC BY-NC-SA`; por eso la fuente y el GeoJSON
generado permanecen ignorados por Git y el reporte conserva sus hashes.

El CSV debe contener estas columnas FIRMS (se aceptan los alias definidos en
`src/fuegopa/firms.py`): `latitude`, `longitude`, `acq_date`, `acq_time`,
`satellite`, `instrument`, `confidence` y `frp`. Las columnas pueden contener
valores faltantes, pero no pueden faltar del encabezado.

Antes de ejecutar, incorpore y verifique el límite en
`data/reference/cocle.geojson`. El pipeline se detiene si la geometría falta o
no puede validarse; no se usa un bbox como sustituto.

```powershell
python scripts/acquire_firms.py `
  --input path/to/firms.csv `
  --boundary-path data/reference/cocle.geojson
```

La ejecución genera, por defecto:

- `data/raw/firms_local_cocle_2025.csv`: copia byte a byte del input.
- `data/raw/manifests/*.manifest.json`: trazabilidad, hash y estado del raw.
- `data/processed/firms_cocle_2025_detections.csv`: detecciones válidas dentro
  de Coclé y del periodo aprobado.
- `outputs/firms_data_availability_2025.csv`: snapshot de disponibilidad usado
  para decidir las fuentes; no contiene la clave.
- `outputs/firms_source_selection_2025.json`: fuentes disponibles, rangos
  devueltos, tipo `SP`/`NRT` y razones de inclusión/exclusión.
- `outputs/firms_acquisition_audit_2025.json` y `.md`: fragmentos esperados,
  errores, cobertura, esquema, bbox, exclusiones, duplicados y estado de
  preparación. Si la adquisición es parcial o el esquema falla, el pipeline no
  escribe la cohorte procesada.
- `outputs/firms_cocle_2025_profile.json` y `.md`: attrition, faltantes,
  duplicados, instrumentos, cobertura y coincidencias diagnósticas entre
  fuentes.

Si el raw ya existe con bytes distintos, la ejecución falla para evitar
sobrescribir evidencia. Use otra ruta con `--raw-path` para otra extracción.

## Ejecutar una descarga proporcionada por el usuario

La ruta estructurada consulta primero la disponibilidad oficial de FIRMS y luego
descarga fuentes VIIRS históricas (`*_SP`) en fragmentos de hasta cinco días.
Las fuentes se seleccionan según la respuesta real de disponibilidad; no se
asume que cada satélite cubre todo el periodo.

```powershell
$env:FIRMS_MAP_KEY = "<CLAVE_LOCAL_NO_COMMITIDA>"
python scripts/acquire_firms.py `
  --boundary-path data/reference/cocle.geojson `
  --source VIIRS_SNPP_SP
```

También puede usar los nombres y rutas de `.env.example` como referencia para
configurar el entorno del proceso. El proyecto no lee `.env` automáticamente y
la clave nunca aparece en URLs guardadas, manifests, errores ni salida normal.
Si no hay clave, use `--input` con un CSV FIRMS local real; no se genera un
dataset de producción sintético.

## Auditar una adquisicion FIRMS ya existente

Cuando `data/raw/`, sus manifests y la cohorte procesada ya estan presentes,
la auditoria reproducible no vuelve a consultar la red ni modifica los raw:

```powershell
python scripts/audit_existing_firms.py
python scripts/build_firms_figures.py
```

La auditoria compara los fragmentos esperados con manifests y hashes, separa
fragmentos vacios de dias sin detecciones, valida la correspondencia raw/
procesado y actualiza los reportes JSON/Markdown de `outputs/`. El generador
produce seis figuras descriptivas en `outputs/figures/`; sus observaciones
FIRMS no deben leerse como incendios independientes confirmados.

## Ejecutar la sensibilidad de clustering

Esta fase usa solamente el CSV procesado local. No descarga datos, no necesita
credenciales y no modifica `data/raw/` ni el CSV de entrada. La grilla fija es:
radios `375, 750, 1500, 3000 m` y ventanas UTC `6, 12, 24, 48 h`.

```powershell
conda activate fuegopa
python scripts/run_clustering_experiment.py `
  --input data/processed/firms_cocle_2025_detections.csv `
  --output-dir outputs/clustering `
  --figures-dir outputs/figures/clustering
```

La frontera GeoJSON es opcional para las figuras; si existe una geometría local
ya verificada puede añadirse con `--boundary data/reference/cocle.geojson`.
Si no existe, los mapas muestran el extent de las detecciones y lo declaran.
El algoritmo usa componentes conexas sobre EPSG:32617 compatible con una
proyección UTM WGS84 implementada con la biblioteca estándar. Una arista solo
usa coordenadas y timestamp UTC; fuente, satélite, instrumento, FRP, confianza
y día/noche son atributos descriptivos.

El experimento genera bajo `outputs/clustering/` un resumen de las 16
configuraciones, los `events.csv` y `membership.csv` por configuración, una
comparación de estabilidad entre vecinos, una revisión de eventos extremos y
una selección provisional de candidatos. Las figuras PNG incluyen cinco
heatmaps, mapas 2x2, eventos grandes y un gráfico de estabilidad. Todos los
artefactos son locales e ignorados por Git.

La corrida actual aprobó provisionalmente `r1500_t06` para preparar la fase de
observabilidad, después de comparar `r3000_t06` y `r1500_t12`. No es una
validación científica ni una confirmación de incendios; las tablas
provisionales se generan de forma reproducible y permanecen fuera de Git.

## Pruebas y validaciones

```powershell
conda activate fuegopa
.\scripts\run_tests.ps1
```

Las pruebas crean CSV y GeoJSON temporales mínimos para contratos unitarios; no
incluyen datos FIRMS de producción ni llaman a la red. La suite heredada de la
primera etapa permanece en `tests/test_firms.py`. La sensibilidad se valida en
`tests/test_clustering.py`; las decisiones de parámetros finales, etiquetas y
baseline siguen pendientes en `docs/CLUSTERING_DESIGN.md` y `docs/PREFLIGHT.md`.

## Configuración provisional y piloto Sentinel-2

La sensibilidad aprobó provisionalmente `r1500_t06` para esta fase: radio
espacial `1500 m`, ventana temporal `6 h`, componentes conexas
espacio-temporales y CRS de cálculo `EPSG:32617`. La configuración no está
validada científicamente: los `611` eventos no son `611` incendios confirmados,
los singletons se conservan y FRP/confianza no forman clusters. Los parámetros
pueden cambiar después de observar cicatrices Sentinel-2 y revisar eventos
ambiguos.

La congelación y el muestreo reproducible se ejecutan con:

```powershell
conda activate fuegopa
python scripts/freeze_provisional_clustering.py
```

El script consume los outputs ya existentes en `outputs/clustering/r1500_t06/`
sin volver a ejecutar el algoritmo. Genera localmente las tablas provisionales,
un piloto de 30 eventos con semilla `20260715`, dos reportes de muestreo y el
encabezado vacío de `data/interim/sentinel2_observability.csv`. Esos artefactos
de datos están ignorados por Git.

La muestra se estratifica por singleton/multi-detección, cuartiles de
`detection_count` entre multi-eventos, mes, fuente única/múltiple y
`possible_chain_merge`. No usa FRP, confianza, tamaño aparente ni selección
visual. El diseño previo a imágenes está en
`docs/SENTINEL2_OBSERVABILITY_DESIGN.md`; aún no se consulta Earth Engine, no
se descargan escenas y no se calculan NBR, dNBR, etiquetas, modelos ni
interfaz operativa ni de alertas.

## Ejecutar la observabilidad Sentinel-2

La siguiente etapa consulta únicamente el piloto estructural de 30 eventos.
Requiere `earthengine-api` y un proyecto configurado en la variable de entorno
`EARTH_ENGINE_PROJECT`; el proyecto, tokens y credenciales no se guardan en el
repositorio. La instalación opcional es:

```powershell
conda activate fuegopa
python -m pip install -e ".[dev,gee]"
```

Validar el acceso sin escribir resultados científicos:

```powershell
python scripts/run_sentinel2_observability.py --smoke-test
```

Ejecutar un evento, la cohorte completa o reanudar desde caché/checkpoint:

```powershell
python scripts/run_sentinel2_observability.py --max-events 1 --overwrite --confirm-overwrite OVERWRITE
python scripts/run_sentinel2_observability.py --overwrite --confirm-overwrite OVERWRITE
python scripts/run_sentinel2_observability.py --resume
```

El pipeline consulta `COPERNICUS/S2_SR_HARMONIZED` enlazado por
`system:index` con Cloud Score+ y evalúa AOI, ventanas, cobertura conjunta de
B8/B12 y las reglas de claridad A-D. Mantiene todas las escenas candidatas y
registra la atrición; no descarga raster, no calcula NBR/dNBR, no inspecciona
manualmente cicatrices y no crea etiquetas o modelos. Los CSV, JSON, cachés y
figuras generados permanecen fuera de Git.

## Piloto NBR/dNBR acotado

La política Sentinel-2 quedó congelada provisionalmente para calcular índices
solo en 28 eventos del piloto: AOI b0500, pre30/post45 como principal,
pre30/post90 como fallback y regla A. El fallback rescata un único evento.
Los dos eventos sin pareja pre utilizable se conservan como no observables y no
son negativos.

El piloto usa NBR=(B8-B12)/(B8+B12) y dNBR=NBR_pre-NBR_post a 20 m con B8, B12,
Cloud Score+ enlazado y cs_cdf 0.50 como máscara primaria. Los umbrales 0.60 y
0.65, además del modo window_median, son sensibilidades descriptivas. No se
crean etiquetas significant_burn, categorías de severidad ni modelos.

Después de validar pruebas y smoke test, ejecutar primero un solo evento con
este comando PowerShell:

    python scripts/run_sentinel2_dnbr.py --event-id event-r1500_t06-548ca9e284d1a330 --overwrite --confirm-overwrite OVERWRITE --debug

La ejecución requiere EARTH_ENGINE_PROJECT en el entorno y no guarda el
proyecto, credenciales ni tokens. Los resultados permanecen en data/interim,
outputs y la carpeta de quicklooks, todas ignoradas por Git. La especificación
completa está en docs/SENTINEL2_DNBR_DESIGN.md.

El contrato dNBR v3 calcula el solapamiento con un único soporte raster AOI
reproyectado a EPSG:32617 y 20 m: `common_valid_pixel_count` y
`aoi_pixel_count` usan la misma geometría, grilla, escala y reducer. El área
vectorial del AOI es descriptiva, no el denominador de la fracción. La versión
v3 invalida cachés, checkpoints y filas v2 para impedir mezclar definiciones.
Cada evento genera además un panel PNG autocontenido con rangos fijos de NBR y
dNBR; `window_median` no reutiliza el quicklook de `selected_pair`.

La composición de quicklooks valida las seis fuentes antes de guardar el PNG.
Los overlays de AOI/detecciones usan fondos transparentes mediante `selfMask()`
y no contaminan RGB, NBR ni dNBR. Para auditar o recomponer desde artefactos
locales, sin Earth Engine ni recálculo científico, usar:

    python scripts/run_sentinel2_dnbr.py --rebuild-quicklooks --event-id <event_id>

La auditoría queda en `outputs/debug/sentinel2_dnbr/`; si un PNG fuente es
uniforme, verde o no corresponde a su capa, la reconstrucción falla sin
reemplazar el panel.

## Estado vigente — Fase A y Nivel 1 Fase B — 21 de julio de 2026

El contrato dNBR v3 está congelado localmente y Quicklook v2 está implementado
como un compositor separado, con la versión `fuegopa-dnbr-quicklook-v2`.
Quicklook v2 no consulta Earth Engine: recompone desde artefactos locales
existentes y deja intactas las salidas científicas y los quicklooks v1.

La corrida autorizada genera exactamente estos siete casos de calibración:

```text
event-r1500_t06-0ddd477d24b1364d
event-r1500_t06-84cb252a6877d2d5
event-r1500_t06-ef20fd746737f4ea
event-r1500_t06-9e5bf1d807f9d61a
event-r1500_t06-548ca9e284d1a330
event-r1500_t06-040b1a186d857b11
event-r1500_t06-09c2d54e2d8fb5dd
```

Para reproducirla en el entorno `fuegopa`:

```powershell
python scripts/run_dnbr_quicklook_v2.py
```

Las rutas locales son:

```text
outputs/figures/sentinel2_dnbr_v2/events/<event_id>_selected_pair_cs050_panel_v2.png
outputs/figures/sentinel2_dnbr_v2/events/<event_id>_temporal_comparison_v2.png
outputs/review_upload_v2/<mismo_nombre>.png
outputs/quicklook_v2_report.json
outputs/quicklook_v2_report.md
```

Cada evento tiene un panel principal y una comparación, todos RGB de 2048 ×
1440. En ese snapshot del 21 de julio, la comparación de `window_median` estaba
marcada `metrics only`: no había un raster numérico local que permitiera
sustituir el panel `selected_pair`.
También quedan diferidos el remapeo diagnóstico dNBR `[-0.25, 0.50]` y el
false-color SWIR; no se invierte información científica desde los colores de
los PNG. El protocolo observacional v1 ya está congelado, pero la revisión
humana de los 28 eventos, las etiquetas, `significant_burn`, las variables
ambientales, el modelo, el dashboard y cualquier consulta nueva de Earth
Engine siguen pendientes.

### Piloto separado `window_median` — 30 de julio de 2026

El piloto técnico posterior reutiliza los bundles numéricos `window_median`
Level 2 ya existentes para exactamente siete casos históricos. El contrato
`firepa-window-median-review-asset-v1` define mediana por píxel y banda de
reflectancia en pre/post, seguida de NBR y dNBR. El resultado fue `pilot_pass`:
7/7 sidecars, 7/7 paneles PNG autocontenidos y reconciliación dentro de las
tolerancias únicas ya congeladas. La generación fue local, sin consultas
Earth Engine y sin descargar o reescribir raster.

Los assets quedan fuera de Git bajo
`outputs/window_median_review_asset_v1/`. Incluyen hashes, ventanas, scene
counts, fallback, grilla, nodata, advertencias estructuradas, referencias
inmutables a los siete paneles `selected_pair`, un contact sheet y reportes.
No se fabrican máscaras pre/post separadas porque no existen en el bundle
local. `window_median` no es ground truth, severidad ni etiqueta, no sustituye
`selected_pair` y no se conectó a las 56 asignaciones de `formal_review_28`.

Para reconstruir/verificar solo el paquete local:

```powershell
conda activate fuegopa
python scripts/build_window_median_review_asset.py --case-set calibration-7 --no-earth-engine
python scripts/verify_window_median_review_asset.py --case-set calibration-7
```

La ronda formal permanece `prepared/not_started` con
`execution_authorized=false`, 0 perfiles, 0 Pass A y 0 Pass B.

## Preparación de la revisión formal

La ronda `formal_review_28` queda preparada, no iniciada: 28 eventos
observables, 2 `unobserved` separados y 56 asignaciones humanas independientes
en `HUMAN_SLOT_A` y `HUMAN_SLOT_B`. La IA no ocupa esos slots y no se han
ejecutado revisiones, adjudicaciones, revisiones expertas ni pseudolabels
nuevos.

El contrato congelado está en
[`docs/LABELING_PROTOCOL_v1.md`](docs/LABELING_PROTOCOL_v1.md); el candidato
histórico permanece en `docs/LABELING_PROTOCOL_CANDIDATE_v1.md`. El diseño y
checkpoint de preparación están en `docs/FORMAL_REVIEW_28_DESIGN.md` y
`docs/FORMAL_REVIEW_28_PREPARATION_CHECKPOINT_2026-07-28.md`.

Preparar de forma idempotente, sin Earth Engine y con una semilla privada fuera
de Git:

```powershell
conda activate fuegopa
python scripts/prepare_formal_review_28.py
```

La preparación genera manifests, hashes, aliases ciegos y asignaciones vacías
en `outputs/`, que permanece ignorado. Los paquetes públicos no incluyen el
join alias-evento ni metadata FIRMS; la aplicación formal exige vincular cada
slot a un perfil humano real antes de permitir una revisión. No se crean
campos científicos, una tabla de entrenamiento, variables ambientales,
modelos, predicciones, interfaz operativa ni nuevas consultas Earth Engine.

La ronda está `prepared/not_started` y mantiene
`execution_authorized=false`: 0 perfiles, 0 bindings, 0 Pass A, 0 Pass B y
`window_median=0/28` en las asignaciones formales. El piloto separado no
autoriza ni conecta esos assets. La reconciliación del hash administrativo obsoleto
`57e7b75dc1e98bf9ec56c9feb52ed99cb4ee43d2e56e00a104046f09e972672d` al hash
canónico actual de `docs/LABELING_PROTOCOL_v1.md`
(`6710d43c7acb12d24b825c35673a8367c51de96ae8268a488069bea0c5e3304c`) no
cambió la semántica del protocolo v1 ni las asignaciones, aliases, órdenes,
semilla o inputs visuales.

Verificación administrativa read-only:

```powershell
python scripts/verify_formal_review_28.py
```

La aplicación futura no ofrece selector libre A/B. El lanzador requiere el
contexto explícito del slot y perfil:

```powershell
streamlit run scripts/run_human_review_app.py -- `
  --formal-round --round-id formal_review_28 `
  --slot-id HUMAN_SLOT_A --profile-id <perfil-humano-real>
```

El servidor valida el binding y carga únicamente el mapa privado de ese slot.
La separación es local y supervisada, no una defensa frente al propietario
directo del filesystem o SQLite. Pass B continúa bloqueada porque el piloto
`window_median` todavía no está conectado a la ronda formal; no se reutiliza
`selected_pair`.

## Freeze científico y chequeo externo — 2026-08-09

La revisión humana formal de los 28 eventos queda **diferida** por falta de
revisores calificados: `formal_review_status=deferred`, razón
`QUALIFIED_REVIEWER_UNAVAILABLE` y `execution_authorized=false`. La
infraestructura formal, SQLite, blind packages, migraciones, tests y assets
`window_median` se conservan; no hay observaciones humanas formales. Las
revisiones IA existentes siguen siendo `provisional_pseudolabels` y no son
referencia científica.

El gate de modelado supervisado es
`supervised_modeling_gate=deferred` por
`NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE`. No se crea target, no se genera
`significant_burn`, no se entrena un modelo, no se agregan ERA5/WorldCover/DEM
y no se construye una UI operativa.

FirePA currently supports:

- reproducible FIRMS acquisition;
- provisional spatiotemporal clustering;
- optical Sentinel-2 follow-up;
- selected_pair/window_median evidence;
- descriptive NBR/dNBR;
- provenance and audit infrastructure;
- exploratory external reference matching.

FirePA currently does NOT support:

- confirmed wildfire classification;
- ground truth;
- supervised prediction;
- operational monitoring;
- real-time alerts;
- severity estimation;
- institutional validation.

### `external_reference_check_v1`

El chequeo exploratorio consume los 611 clusters `r1500_t06` congelados, sin
reclustering, y conserva todos los matches a distancia `<=5 km` con
intersección temporal. Usa exclusivamente las dos referencias proporcionadas
por el investigador y su registro canónico de siete fuentes en
`references/external_reference_sources_v1.json`. El resultado 2025 fue 0
matches para Cerro Los Picachos y 6 para Cerro Guacamaya. Guacamaya aparece en
múltiples clusters; los huecos mayores que t06 se documentan como posible
fragmentación de representación, sin cambiar el clustering.

La procedencia está completa (`external_reference_provenance=complete`): 7
fuentes para 2 incidentes, con una fuente para `REFERENCE-001` y seis para
`REFERENCE-002`. El SHA-256 del registro es
`6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49`.
Las coordenadas de matching son anclas aproximadas proporcionadas por el
investigador, no coordenadas reclamadas por las fuentes. Se preservan las
áreas de Guacamaya de 1,035 a aproximadamente 1,500 ha y los estados `null`/
`suspected_intentional` sin adjudicación; no se crea ground truth, target ni
confirmación de arson.

La búsqueda manual OSINT localizó 6 artículos en enero, 1 en febrero y 0 en
marzo y abril. No qualifying articles were located during the manual OSINT
search for March or April 2025. Esto no afirma ausencia de incendios o de
actividad térmica y la búsqueda no se declara exhaustiva. Las URLs son solo
procedencia y no son inputs del pipeline.

Ninguno de los seis matches pertenece a la cohorte óptica existente de 30
eventos, por lo que no se generaron nuevos assets y
`optical_followup_available=false`. No hubo red ni consultas Earth Engine.

El contrato y el informe están en
[`docs/EXTERNAL_REFERENCE_CHECK_v1.md`](docs/EXTERNAL_REFERENCE_CHECK_v1.md) y
[`docs/EXTERNAL_REFERENCE_CHECK_RESULTS_2025.md`](docs/EXTERNAL_REFERENCE_CHECK_RESULTS_2025.md).
Los CSV/JSON/SVG, reportes y hashes generados están en
`outputs/external_reference_check_v1/`, fuera de Git.

## Final scientific pilot analysis — 2026-08-09

El informe reproducible final está en
[`docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md`](docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md).
Explica el cero oficial de Los Picachos como `SPATIAL_THRESHOLD_MISS` y
caracteriza los seis matches de Guacamaya y sus huecos inter-cluster sin
modificar `r1500_t06` ni las reglas oficiales.

Estado de fase:

```text
DETECTION PIPELINE                 = complete for pilot
OPTICAL FOLLOW-UP                  = complete for pilot
CALIBRATION                        = complete
FORMAL REVIEW INFRASTRUCTURE      = complete; execution deferred
EXTERNAL REFERENCE CHECK           = complete
EXTERNAL REFERENCE PROVENANCE      = complete; 7 sources / 2 incidents
SUPERVISED MODELING                = deferred
ENVIRONMENTAL FEATURES             = deferred
PUBLIC UI                          = static research experience; not operational
```

El bundle estático local, con seis PNG neutrales, tablas diagnósticas y
manifest SHA-256, está en `outputs/final_scientific_report/` y permanece fuera
de Git. Esta fase no crea targets, `significant_burn`, ground truth, modelos,
dashboard ni claims operacionales. El freeze definitivo está en
[`docs/FIREPA_PILOT_V1_FREEZE.md`](docs/FIREPA_PILOT_V1_FREEZE.md); cualquier
cambio científico o de adjudicación externa requiere una nueva versión.
