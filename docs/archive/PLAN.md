# FirePA — Plan maestro: del freeze científico a la publicación

> **ARCHIVED DEVELOPMENT SNAPSHOT — NOT A CURRENT ROADMAP.** This file records
> the phase plan used before the bilingual publication existed. Use the root
> [`README.md`](../../README.md) and documentation [`README.md`](../README.md)
> for current release status and authority.

**Actualizado:** 2026-08-09
**Estado científico:** FIREPA SCIENTIFIC PILOT V1 = FROZEN / COMPLETE WITHIN DEFINED SCOPE
**Estado público:** P1 PACKAGE COMPLETE / P2 NOT STARTED
**Fase actual:** **P1 — PUBLIC RELEASE PACKAGE (COMPLETE / PASS)**

## Resultado actual y siguiente gate

P1 ya produjo y verificó un contrato público derivado de resultados congelados.
El siguiente gate es P2, que permanece **NOT STARTED** y requiere autorización
explícita. P2 no se inicia en este checkpoint.

## Roadmap finito y gates

| Fase | Nombre | Estado | Gate de salida |
|---|---|---|---|
| P0 | Scientific Pilot v1 | **COMPLETE / FROZEN** | Resultados, límites, procedencia y freeze reproducibles y protegidos. |
| P1 | Public Release Package | **COMPLETE / PASS** | Paquete público determinista, privacy-safe, verificado y fiel al freeze. |
| P2 | IA + visual direction | **NOT STARTED / REQUIRES AUTHORIZATION** | Arquitectura de información y dirección visual aprobadas. |
| P3 | Static website implementation | BLOCKED BY P2 | Sitio estático trazable, accesible, responsive y técnicamente validado. |
| P4 | Publication audit | BLOCKED BY P3 | Auditoría final de claims, datos, enlaces, secretos, assets y reproducción. |
| P5 | Release | BLOCKED BY P4 | Sitio, repositorio, informe y release/tag publicables; después, mantenimiento v1. |

## P0 — Scientific Pilot v1: cerrado

P0 ya contiene y no se reabre durante la publicación:

- adquisición y auditoría de 1,532 detecciones FIRMS raw y 1,185 procesadas;
- clustering oficial r1500_t06 con 611 eventos térmicos provisionales,
  344 singletones, 267 multi-detecciones y 17 posibles cadenas;
- cohorte Sentinel-2 de 30 casos: 28 observables y 2 unobserved;
- evidencia selected_pair, NBR/dNBR descriptivo y asset
  window_median de calibración calibration-7 con 7/7 casos aprobados;
- infraestructura administrativa de formal_review_28, sin ejecutar revisión;
- chequeo externo sin reclustering: 0 matches oficiales para Los Picachos y 6
  para Guacamaya;
- procedencia externa canónica: 7 fuentes para 2 incidentes;
- informe científico, manifests y freeze documentados.

El commit de freeze científico v1 es
7694da7df5808911de48de84016759c5fd22f176. La publicación puede empaquetar
estos artefactos, pero no cambiar los conteos, reglas, rasters, diagnósticos,
fuentes, hashes o lenguaje científico que los describe.

### Límites de P0

No hay observaciones humanas formales, ground truth, target, significant_burn,
modelo supervisado, variables ambientales agregadas, validación institucional,
monitoreo operacional, alertas en tiempo real ni UI científica pública.

La revisión formal se mantiene prepared/not_started con
execution_authorized=false y está diferida por
QUALIFIED_REVIEWER_UNAVAILABLE. La infraestructura está completa y la
ejecución diferida **no es un requisito de publicación v1**.

El modelado está diferido por
NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE. No se debe presentar el piloto
como clasificador, predictor o sistema de IA.

## P1 — Public Release Package: completado

### Alcance

El paquete público mínimo, determinista y seguro fue construido desde artefactos
congelados. El contrato aprobado y el resultado están documentados en
`docs/P1_PUBLIC_RELEASE_CONTRACT.md` y `docs/P1_PUBLIC_RELEASE_HANDOFF.md`:

~~~text
site-data/
  project-summary.json
  events.geojson
  external-references.geojson
  guacamaya-timeline.json
  methodology.json
  citations.json
  figures/ públicos
~~~

La implementación es una proyección pública, no una copia de datos privados.
Excluye rutas absolutas locales, secretos, credenciales, SQLite, semillas
privadas, joins de aliases con eventos, metadata privada de FIRMS, manifests de
revisión y cualquier campo que parezca un target o una clase predicha.

### Verificador dedicado de P1

El verificador read-only comprueba:

1. counts públicos = counts congelados;
2. configuración y definiciones = r1500_t06 y contratos v1;
3. cero rutas locales, secretos o dependencias privadas;
4. cero cambios en outputs científicos protegidos;
5. referencias, enlaces y hash del registry trazables;
6. el texto usa “provisional thermal events” y no “confirmed fires”;
7. figuras y geometrías son derivados públicos reproducibles;
8. frontend futuro no necesita recalcular resultados.

### Gate de salida de P1

P1 terminó con PASS: el paquete es determinista, privacy-safe, verificable,
completo para la narrativa pública y fiel al freeze. P1 no produce una UI.

## P2 — IA y dirección visual

P2 es el siguiente gate, pero sigue **NOT STARTED** y requiere autorización
explícita. Definirá, sin reabrir la ciencia:

- narrativa y sitemap;
- jerarquía de secciones y orden de lectura;
- hero con pregunta de investigación y límites;
- secuencia cuantitativa 1532 → 1185 → 611 → 30 → 28;
- mapa de eventos térmicos provisionales;
- evidencia Sentinel-2, caso Guacamaya y diagnóstico Los Picachos;
- metodología, reproducibilidad, fuentes, informe y GitHub;
- tipografía, color, ritmo, interacción y responsive behavior.

La dirección visual puede inspirarse en NASA Earth Observatory, publicación
científica, data journalism y Panamá, pero el resultado debe ser un sitio de
investigación, no una interfaz operativa. No se escribe producción en P2,
salvo prototipos explícitamente autorizados.

## P3 — Implementación del sitio estático

P3 queda bloqueada por P2. La implementación deberá ser static-first,
accesible, responsive y rápida. Las páginas presentarán los datos públicos
pre-generados, mapas, casos, citas, metodología y limitaciones sin depender de
backend, base operacional, inferencia en runtime o Earth Engine.

Gate de salida: claims trazables al paquete P1/freeze, build reproducible,
pruebas relevantes, revisión de accesibilidad, revisión de responsive layout y
revisión básica de performance.

## P4 — Auditoría de publicación

P4 comprobará, antes de cualquier release:

- wording de todas las afirmaciones y unidades (“provisional thermal events”);
- enlaces, citas, atribución y licencia de assets/basemap;
- conteos, hashes, procedencia y ausencia de drift científico;
- secretos, tokens, rutas locales, assets privados y SQLite;
- README, estructura GitHub y reproducibilidad desde un checkout limpio;
- navegación desktop/mobile, browser smoke, accesibilidad y performance;
- que ninguna pantalla parezca un sistema operacional o de alertas.

Gate de salida: candidato público aprobado con evidencia de auditoría.

## P5 — Release

P5 publica, solo después de P4, el sitio, repositorio, informe científico y
release/tag correspondiente. Tras el release se mantiene v1 con cambios de
presentación y correcciones trazables; cualquier cambio científico requiere una
nueva versión explícita.

No se hace push en este checkpoint. La configuración de hosting, dominio y
proveedor sigue pendiente; Cloudflare Pages es una opción, no una obligación.

## Decisiones arquitectónicas y decisiones pendientes

### Decidido

- publicación static-first;
- resultados pre-generados y frontend sin recomputación;
- no backend, auth, operational DB ni Supabase necesarios;
- no Earth Engine en runtime y no APIs pagadas necesarias;
- separación explícita entre análisis congelado y experiencia pública.

### Pendiente después de P1

- Astro, React u otro framework;
- MapLibre, Leaflet u otra librería;
- basemap y formato de geometría (GeoJSON, PMTiles u otro);
- hosting, dominio y estrategia de build;
- tipografía, paleta, movimiento y densidad de detalle por evento;
- nivel de interacción sin transformarlo en dashboard operacional.

## Trabajo científico intencionalmente diferido más allá de v1

Estas tareas no son parte de P1–P5. Solo se pueden abrir como FirePA
Scientific Pilot v2 o extensión versionada:

- revisión humana calificada y adjudicación experta;
- ground truth y target defendible;
- validación institucional;
- ERA5-Land, ESA WorldCover y Copernicus DEM;
- baseline FIRMS-only;
- regularized logistic regression u otro modelo defendible;
- sensibilidad con clustering alternativo;
- ampliación de la cohorte óptica;
- colaboración institucional y nueva evidencia externa autorizada.

No mover estas tareas a “next” por inercia histórica. P1 no dependió de
completar la revisión formal o entrenar un modelo; P2 permanece sin iniciar.

## Reglas de ejecución y Git

Antes de cada sesión, verificar root, rama, HEAD y status. Trabajar solo en
la raíz del repositorio. Para este checkpoint, el commit P1 debe
contener exclusivamente estos paths solicitados y generados:

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

Los siguientes ocho untracked ya existían y deben permanecer intactos, sin
stagear ni borrar:

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
git checkout -- .. No ejecutar Earth Engine, consultas de red, nueva generación
científica, frontend, P2 ni push como parte de este checkpoint. El paquete P1
se genera solo desde los artefactos congelados y el commit es local.

## Historia del plan

Los roadmaps anteriores reflejaban etapas de factibilidad científica,
revisión, modelado y variables ambientales. Esas notas se conservan en los
documentos históricos para contexto, pero ya no son la secuencia inmediata.
Después del freeze de 2026-08-09, la publicación pública es una fase separada
y finita. P1 está completo; P2 es el siguiente gate, todavía no iniciado.
