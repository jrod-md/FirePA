# FirePA — Estado del proyecto

**Snapshot:** 2026-08-09
**Checkout de trabajo:** raíz del repositorio
**Rama observada al iniciar el refresh:** master
**Base HEAD antes de P1:** c4b6f30907491e9eeeab85538beaa905e8fd5150
**Commit de freeze científico v1:** 7694da7df5808911de48de84016759c5fd22f176
**Push/remoto:** no se afirma estado remoto ni se hizo push

## Resumen ejecutivo

| Área | Estado actual |
|---|---|
| FirePA Scientific Pilot v1 | **COMPLETE / FROZEN WITHIN DEFINED SCOPE** |
| FirePA Public Research Experience | **P1 PACKAGE COMPLETE / P2 NOT STARTED** |
| Fase actual | **P1 — Public Release Package: PASS** |
| Próxima acción | Mantener P2 sin iniciar hasta autorización explícita. |
| Frontend público | No creado |
| Paquete site-data/ | **Creado y verificado: 14 archivos, 656.607 bytes** |
| Deployment/hosting | No configurado |

La publicación pública es presentación y empaquetado de resultados existentes.
No es una continuación científica automática, no es una plataforma operacional y
no cambia el freeze.

## Conteos científicos congelados

| Medida | Valor |
|---|---:|
| FIRMS raw auditado | 1,532 |
| FIRMS procesado | 1,185 |
| Clustering | r1500_t06 |
| Eventos térmicos provisionales | 611 |
| Singletones | 344 |
| Multi-detecciones | 267 |
| possible_chain_merge | 17 |
| Cohorte óptica | 30 |
| Observables ópticos | 28 |
| No observables | 2 |
| Observaciones humanas formales | 0 |

La unidad correcta es **evento térmico provisional**. Los 611 eventos no son
611 incendios confirmados, ni ground truth, ni una etiqueta operacional.

## Hallazgos y límites

### Referencias externas

- 2 incidentes externos y 7 documentos fuente registrados.
- Cerro Los Picachos: 0 matches oficiales dentro del umbral; diagnóstico
  SPATIAL_THRESHOLD_MISS; señal contemporánea más cercana documentada a
  10,400.826 m.
- Cerro Guacamaya: 6 clusters coincidentes, 5 gaps mayores que 6 h y span de
  72.733 h; posible fragmentación descriptiva por r1500_t06.
- Las anclas de matching son aproximadas y proporcionadas por el investigador.
  Las áreas y las declaraciones de causa de las fuentes no son áreas
  adjudicadas, ground truth ni confirmación de intencionalidad.

La procedencia canónica es
references/external_reference_sources_v1.json:

~~~text
external_reference_provenance = complete
source documents               = 7
incidents                      = 2
REFERENCE-001 sources          = 1
REFERENCE-002 sources          = 6
registry SHA-256               = 6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49
~~~

La búsqueda manual localizó 6 artículos en enero de 2025, 1 en febrero y 0
en marzo/abril. No fue exhaustiva; ausencia de artículos no equivale a
ausencia de fuego o de actividad térmica. Las URLs no son inputs del pipeline.

### Revisión formal

La infraestructura de formal_review_28 está completa y preservada. La
ejecución humana formal está diferida por
QUALIFIED_REVIEWER_UNAVAILABLE:

~~~text
formal_review_status = deferred
execution_status     = not_started
execution_authorized = false
observable_count     = 28
unobserved_count     = 2
assignment_count     = 56
formal observations  = 0
Pass A / Pass B      = 0 / 0
~~~

La revisión formal no es necesaria para publicar v1. La infraestructura
administrativa no crea observaciones ni ground truth.

### Modelado y capacidad operacional

~~~text
supervised_modeling_gate = deferred
reason                   = NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE
target                   = none
significant_burn         = none
model trained            = false
environmental features   = deferred / not authorized
~~~

No existe clasificación confirmada, predicción supervisada, estimación de
severidad, validación institucional, monitoreo operacional, alerta en tiempo
real ni UI científica pública.

## Qué está completo en v1

- adquisición y auditoría de FIRMS;
- agrupación espacio-temporal provisional;
- seguimiento óptico Sentinel-2 para la cohorte definida;
- evidencia selected_pair y window_median descriptiva;
- NBR/dNBR descriptivo;
- calibración local window_median calibration-7 con 7/7 casos aprobados;
- infraestructura y contratos de revisión formal, sin ejecución;
- chequeo de referencias externas y procedencia reproducible;
- informe científico y freeze de v1.

## Qué queda fuera de v1

- observación humana formal y adjudicación experta;
- ground truth, target y significant_burn;
- modelo supervisado y variables ERA5/WorldCover/DEM;
- validación institucional;
- operación, alertas, tiempo real o clasificación confirmada;
- experiencia web pública y paquete derivado site-data/.

Las extensiones científicas solo pueden abrirse como FirePA Scientific Pilot v2
o como una extensión versionada. No son el siguiente paso de publicación.

## Integridad, validadores y pruebas

### Baseline antes de este refresh

Se ejecutó en el entorno fuegopa:

~~~text
python -m pytest -q
295 passed, 1 warning in 544.16s
~~~

La advertencia fue PytestCacheWarning por permiso denegado al escribir
.pytest_cache; no produjo fallo de tests. El checkpoint de freeze también
registra el baseline histórico de 288 tests y el cierre de procedencia de 295
tests en 542.20 s.

### Estado de outputs protegidos

~~~text
scientific_changed_count post-freeze = 0
visual_changed_count                  = 0
Earth Engine queries                  = 0
network access                        = false
~~~

El protected_changed_count=0 del asset window_median se refiere a los
artefactos científicos/visuales protegidos. Los únicos archivos intencionales
de este refresh son los tres documentos maestros indicados al final.

### Verificación post-refresh

La suite completa volvió a pasar después de editar los tres documentos:

~~~text
python -m pytest -q
295 passed, 1 warning in 541.17s
~~~

La advertencia continuó siendo PytestCacheWarning por acceso denegado a
.pytest_cache; no produjo fallo de tests.

Los cuatro validadores read-only también pasaron después del refresh:

~~~text
verify_final_scientific_report.py                   = OK; 6 figures; 13 manifest files; no network
verify_external_reference_check.py                  = OK; 611 clusters; 6 matches; formal deferred; no network
verify_formal_review_28.py                          = OK; 28 observable; 2 unobserved; 56 assignments; execution false
verify_window_median_review_asset.py calibration-7  = PASS; 7 cases; Pass A/B 0/0; execution false
~~~

La suite y estos validadores son read-only para el estado científico; no
regeneraron outputs ni ejecutaron red o Earth Engine.

## Fase pública: estado y arquitectura

La **Public Research Experience** sigue NOT STARTED. La intención aprobada
es una experiencia estática de investigación/portfolio con tres entregables:
sitio estático, informe científico y repositorio GitHub. El sitio debe exponer
la cadena 1532 → 1185 → 611 → 30 → 28, mapas y casos derivados, metodología,
procedencia, reproducibilidad y limitaciones.

La arquitectura futura es static-first: no requiere backend, auth, DB
operacional, Supabase, inferencia en runtime, Earth Engine en runtime ni APIs
pagadas. Framework, mapas, basemap, formato GeoJSON/PMTiles, hosting,
dominio, tipografía, paleta y motion permanecen pendientes. No hay código
frontend en este checkpoint.

## P1 — resultado del gate

P1 creó y verificó el paquete público mínimo desde el freeze:

~~~text
project-summary.json
events.geojson
external-references.geojson
guacamaya-timeline.json
methodology.json
citations.json
figures/ públicos
~~~

El paquete cuenta con un verificador que comprueba counts, procedencia,
lenguaje, privacidad, ausencia de rutas locales/secretos/SQLite/manifests
privados y cero cambio científico. El build reportó 611 eventos, 2 referencias,
7 fuentes, `network_access=false` y `earth_engine_queries_made=false`. El
detalle reproducible está en `docs/P1_PUBLIC_RELEASE_HANDOFF.md`.

No habrá frontend dentro de este checkpoint. P2 sigue **NOT STARTED** y requiere
autorización explícita.

La secuencia posterior es P2 IA/visual, P3 implementación estática, P4
auditoría de publicación y P5 release. Ningún gate público requiere ejecutar
la revisión formal o entrenar un modelo; esas tareas están fuera de v1.

## Orden de autoridad

Cuando haya conflicto, usar:

1. CONTEXT.md
2. PLAN.md
3. PROJECT_STATUS.md
4. docs/FIREPA_PILOT_V1_FREEZE.md
5. docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md
6. docs/FIREPA_PILOT_FINAL_CHECKPOINT.md
7. references/external_reference_sources_v1.json
8. documentación especializada y README.

Los handoffs históricos son contexto, no un nuevo roadmap. El report científico
mantiene un Base de lectura anterior y una representación histórica de
procedencia que no se edita aquí; el freeze y el registry canónico gobiernan
la interpretación actual.

## Archivos modificados y untracked preservados

El checkpoint P1 está limitado a:

~~~text
CONTEXT.md
PLAN.md
PROJECT_STATUS.md
docs/P1_PUBLIC_SCHEMA_AUDIT.md
docs/P1_PUBLIC_RELEASE_CONTRACT.md
docs/P1_PUBLIC_RELEASE_HANDOFF.md
scripts/build_public_release.py
scripts/verify_public_release_package.py
tests/test_public_release.py
site-data/
~~~

Los siguientes ocho untracked preexistentes se preservan sin stagear ni borrar:

~~~text
data/interim/.gitkeep
data/processed/.gitkeep
data/raw/.gitkeep
data/raw/manifests/.gitkeep
data/reference/.gitkeep
data/reference/README.md
docs/HANDOFF_FIREPA_2026-07-21.md
notebooks/.gitkeep
~~~

No usar git add ., git add -A, git clean, git reset --hard ni
git checkout -- .. No se cambia ciencia, no se implementa frontend, no se
consulta red/Earth Engine, no se inicia P2 y no se hace push en este
checkpoint.
