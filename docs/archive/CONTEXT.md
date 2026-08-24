# FirePA — Contexto maestro después del freeze científico v1

> **ARCHIVED DEVELOPMENT SNAPSHOT — NOT CURRENT PUBLICATION STATUS.** This file
> is retained because frozen scientific protocols cite its historical context.
> The current bilingual publication is complete; use the root
> [`README.md`](../../README.md), [`SCIENTIFIC_REPORT.md`](../SCIENTIFIC_REPORT.md),
> and documentation [`README.md`](../README.md) for current authority.

**Actualizado:** 2026-08-09
**Repositorio:** raíz del repositorio
**Rama observada al iniciar este refresh:** master
**Freeze commit del piloto científico v1:** 7694da7df5808911de48de84016759c5fd22f176
**Estado de este archivo:** orientación maestra para nuevas sesiones

## Cómo leer este repositorio

Este archivo responde qué es FirePA, qué quedó congelado, qué evidencia es
defendible, qué no se puede afirmar y cuál es el siguiente trabajo autorizado.
PLAN.md contiene la hoja de ruta con gates; PROJECT_STATUS.md contiene el
snapshot operativo de este checkpoint.

El trabajo actual tiene dos capas que no deben mezclarse:

| Capa | Estado | Interpretación |
|---|---|---|
| **FIREPA SCIENTIFIC PILOT V1** | **FROZEN / COMPLETE WITHIN DEFINED SCOPE** | El análisis científico definido para v1 terminó y sus resultados no se reabren durante la publicación. |
| **FIREPA PUBLIC RESEARCH EXPERIENCE** | **P1 PACKAGE COMPLETE / P2 NOT STARTED** | El paquete público derivado está listo; la experiencia web sigue sin iniciarse y no es ciencia nueva ni una capacidad operacional. |

**P1 — Public Release Package** está completo con gate PASS. El paquete público
no cambia los resultados congelados y no autoriza todavía frontend, backend,
nueva consulta científica ni despliegue.

## Definición oficial y lenguaje obligatorio

FirePA es:

> FirePA is a reproducible remote-sensing pilot for detecting, grouping and
> analyzing provisional thermal events in Coclé, Panamá using NASA FIRMS and
> Sentinel-2 optical evidence.

En español: **FirePA es un piloto reproducible de teledetección para detectar,
agrupar y analizar eventos térmicos provisionales en Coclé, Panamá, usando NASA
FIRMS y evidencia óptica Sentinel-2.** La inferencia se hace combinando
anomalías FIRMS, agrupación espacio-temporal, seguimiento óptico Sentinel-2 y
referencias externas documentadas.

El número científico es siempre **611 eventos térmicos provisionales**. No se
debe convertir en “611 incendios”, “611 incendios forestales” o “611 fuegos
confirmados”. FirePA no debe presentarse como detector de incendios validado,
sistema de predicción, sistema de IA para incendios, plataforma en tiempo
real, plataforma de emergencias, mapa operativo ni clasificador validado.

## Estado científico congelado

Los siguientes valores pertenecen al piloto científico v1 congelado y deben
permanecer iguales en cualquier paquete público derivado:

| Elemento | Estado congelado |
|---|---:|
| FIRMS raw auditado | 1,532 detecciones |
| FIRMS procesado | 1,185 detecciones |
| Configuración de clustering | r1500_t06 |
| Clusters/eventos térmicos provisionales | 611 |
| Singletones | 344 |
| Multi-detecciones | 267 |
| possible_chain_merge | 17 |
| Cohorte óptica Sentinel-2 | 30 eventos |
| Cohorte óptica observable | 28 eventos |
| Casos ópticamente no observables | 2 eventos, separados como unobserved |
| Observaciones humanas formales | 0 |
| Referencias externas | 2 incidentes |
| Documentos fuente externos registrados | 7 |

El piloto incluye adquisición y auditoría FIRMS, agrupación provisional,
seguimiento óptico, evidencia selected_pair y window_median, NBR/dNBR
descriptivo, infraestructura administrativa de revisión y chequeo externo
exploratorio con procedencia. Los rasters, manifests y bundles locales son
artefactos científicos pre-generados; no se recalculan para publicar.

### Hallazgos externos que sí están congelados

- **Cerro Los Picachos:** 0 coincidencias oficiales dentro de la regla de
  5 km y ventana temporal definida; diagnóstico SPATIAL_THRESHOLD_MISS.
  La señal contemporánea más cercana documentada está a 10,400.826 m. Esto
  no convierte el cero oficial en ausencia de fuego ni en ausencia de señal.
- **Cerro Guacamaya:** 6 clusters provisionales coincidentes, cinco huecos
  inter-cluster mayores que seis horas y un span temporal de 72.733 h. La
  fragmentación posible se conserva como limitación de representación de
  r1500_t06, no como reclustering ni como prueba de continuidad física.
- Las coincidencias externas son relacionales y exploratorias. Las anclas
  geográficas son aproximadas y proporcionadas por el investigador; no se
  presentan como coordenadas reclamadas por las fuentes.

## Revisión formal y modelado

La infraestructura de formal_review_28 está preparada y preservada, pero la
ejecución humana está diferida por
QUALIFIED_REVIEWER_UNAVAILABLE. El estado administrativo es
prepared/not_started, execution_authorized=false, 28 observables, 2
unobserved, 56 asignaciones y cero observaciones Pass A/Pass B.

La revisión formal **no es requisito para publicar v1**. Su infraestructura
terminada no debe confundirse con observaciones realizadas, ground truth o
validación científica.

El modelado supervisado está diferido por
NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE. No existe target, no existe
significant_burn, no existe ground truth y no se entrenó modelo. Tampoco se
han incorporado ERA5-Land, ESA WorldCover o Copernicus DEM a una nueva etapa.

Por tanto, el piloto no ofrece clasificación confirmada, predicción,
estimación de severidad, validación institucional, monitoreo operacional ni
alertas en tiempo real.

## Procedencia externa canónica

La fuente de verdad para la procedencia externa es
references/external_reference_sources_v1.json:

- external_reference_provenance=complete;
- 7 documentos fuente para 2 incidentes;
- 1 fuente para REFERENCE-001 y 6 para REFERENCE-002;
- SHA-256: 6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49;
- cobertura manual localizada: 6 artículos en enero de 2025, 1 en febrero,
  0 en marzo y 0 en abril.

La búsqueda OSINT no fue exhaustiva. No localizar artículos en marzo o abril
no equivale a ausencia de actividad térmica ni de fuego. Las URLs son
procedencia, no inputs del pipeline, y las áreas/causas reportadas por las
fuentes no son adjudicación ni ground truth.

El registry conserva el metadato histórico
freeze_base_commit=22ad92a72a81f3d8bec6938dd625634d731177ee como
base de generación de la procedencia. Ese valor no sustituye al commit del
checkpoint científico v1 (7694da7...) ni al HEAD que debe comprobarse en una
nueva sesión.

## Orden de autoridad documental

Cuando dos textos no coincidan, usar este orden:

1. CONTEXT.md
2. PLAN.md
3. PROJECT_STATUS.md
4. docs/FIREPA_PILOT_V1_FREEZE.md
5. docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md
6. docs/FIREPA_PILOT_FINAL_CHECKPOINT.md
7. references/external_reference_sources_v1.json
8. Documentos especializados y README, según el tema.

Los handoffs y checkpoints históricos sirven para entender decisiones, pero
son contexto solamente cuando entren en conflicto con el freeze de v1. En
particular, el informe científico conserva un Base de lectura histórico y
una serialización antigua de ciertos campos de procedencia; no deben
interpretarse por encima del freeze y del registry canónico. Esos documentos
no se modifican en este refresh.

## Experiencia pública de investigación

La siguiente etapa tiene tres entregables complementarios:

1. un sitio web estático de investigación;
2. un informe científico legible;
3. un repositorio GitHub reproducible.

La experiencia pública debe contar una historia de investigación estática,
académica y técnica, con visualización clara de métodos, límites, evidencia y
procedencia. La dirección conceptual puede combinar NASA Earth Observatory,
publicación científica, data journalism de alta calidad y referencias visuales
de Panamá. No debe parecer un dashboard de operaciones, SaaS, centro de
emergencias, sala de control de NASA, producto de startup de IA o mapa en
tiempo real.

Las decisiones arquitectónicas tomadas para la fase futura son:

- sitio estático primero;
- sin backend necesario, autenticación, base operacional ni Supabase;
- sin inferencia en runtime ni Earth Engine en runtime;
- sin APIs pagadas necesarias;
- resultados científicos pre-generados derivados del freeze;
- el frontend nunca recalcula resultados científicos.

Siguen pendientes, y no deben inventarse ahora, el framework (Astro/React u
otro), la librería cartográfica (MapLibre/Leaflet u otra), basemap,
GeoJSON/PMTiles, hosting, dominio, tipografía, paleta, movimiento y nivel de
detalle de la información por evento. Cloudflare Pages es una opción, no una
decisión tomada.

## Trabajo científico intencionalmente diferido más allá de v1

Estas líneas no son el siguiente paso de publicación y solo pueden abrirse
como **FirePA Scientific Pilot v2** o como una extensión versionada y
autorizada:

- reclutar y ejecutar revisión humana calificada;
- adjudicación experta y validación institucional;
- definir un target defendible y ground truth;
- extraer variables ERA5-Land, ESA WorldCover y Copernicus DEM;
- establecer y comparar un baseline FIRMS-only;
- entrenar regularized logistic regression u otro modelo justificable;
- analizar sensibilidad con configuraciones alternativas de clustering;
- ampliar la cohorte óptica;
- colaborar con instituciones para validar observaciones y usos.

Nada de esa lista es requisito para la experiencia pública v1. El sitio debe
mostrar estas limitaciones, no ocultarlas ni simular que ya fueron resueltas.

## Resultado de P1 y siguiente gate

P1 generó `site-data/` como paquete estático, determinista y privacy-safe desde
los artefactos congelados. `scripts/build_public_release.py` y
`scripts/verify_public_release_package.py` fijan el contrato, hashes,
conteos, privacidad y lenguaje público. El paquete contiene 611 provisional
thermal events, 2 referencias externas, 7 documentos fuente y seis figuras
copiadas byte-identical; el verificador terminó `ok=true`.

La suite focalizada terminó `6 passed`; la suite completa terminó `301 passed`
con un único warning de permisos de `.pytest_cache`. Los validadores científicos,
de referencias, formal-review y window-median también pasaron. El handoff
detallado está en `docs/P1_PUBLIC_RELEASE_HANDOFF.md`.

El siguiente gate es P2, pero permanece **NOT STARTED** y requiere autorización
explícita. No se inicia frontend, framework, mapas, hosting, dominio ni
dirección visual dentro de este checkpoint.

## Barrera de Git y archivos locales preservados

Una nueva sesión debe verificar antes de leer o modificar más archivos:

~~~powershell
git rev-parse --show-toplevel
git branch --show-current
git log -1 --oneline
git status --short --untracked-files=all
~~~

En este refresh se observaron ocho untracked preexistentes. Deben conservarse,
permanecer fuera del staging y no incluirse en commits documentales:

- data/interim/.gitkeep
- data/processed/.gitkeep
- data/raw/.gitkeep
- data/raw/manifests/.gitkeep
- data/reference/.gitkeep
- data/reference/README.md
- docs/HANDOFF_FIREPA_2026-07-21.md
- notebooks/.gitkeep

Para este checkpoint solo se pueden modificar y stagear CONTEXT.md,
PLAN.md y PROJECT_STATUS.md. No usar git add ., git add -A, git clean,
git reset --hard ni git checkout -- .; no hacer push.
