# FirePA — final scientific pilot report

**Fecha del cierre:** 2026-08-09
**Checkout:** raíz del repositorio
**Base de lectura:** `851550c086c70b558f0ff913e2b3422932cd26f0`
**Versión del análisis:** `firepa_pilot_scientific_report_v1`

Este informe documenta el cierre analítico del piloto local. Lee las tablas
congeladas y el chequeo externo ya generado; no reclusteriza, no crea etiquetas,
no ejecuta revisión humana formal y no hace nuevas consultas de red o Earth
Engine.

## Abstract

El piloto parte de 1,532 registros FIRMS crudos, conserva 1,185 detecciones
válidas dentro de Coclé y utiliza la tabla congelada `r1500_t06` de 611 eventos
espacio-temporales provisionales. El seguimiento Sentinel-2 existente contiene
30 eventos: 28 observables bajo la política vigente y 2 `unobserved`, que no se
interpretan como negativos. La capa externa conserva sus reglas originales:
Los Picachos, 2025-01-15–17 y `<=5 km`, produjo 0 matches; Guacamaya,
2025-01-23–27 y `<=5 km`, produjo 6 matches.

El diagnóstico final explica que el cero de Los Picachos es un
`SPATIAL_THRESHOLD_MISS`: hubo actividad FIRMS en las fechas oficiales, pero
la detección procesada más cercana quedó a 10,400.826 m; no hubo detecciones a
5 ni a 10 km y hubo una a 15 km. La ventana ampliada 2025-01-13–19 no cambia el
resultado de 5 km. Los seis matches de Guacamaya ocupan seis clusters distintos
en un intervalo de 72.733 h; sus cinco huecos inter-cluster son mayores que la
ventana temporal congelada de 6 h. Esto se reporta como una posible
fragmentación de representación, no como un bug automático.

El resultado es descriptivo y reproducible. No establece ground truth,
clasificación confirmada, severidad, precisión, validación institucional ni
desempeño operacional.

## 1. Research motivation

La motivación de esta fase fue resolver dos ambigüedades administrativas sin
alterar el método científico congelado: por qué la referencia de Los Picachos
no tiene coincidencias oficiales y cómo se distribuyen temporalmente las seis
coincidencias de Guacamaya. El análisis busca hacer explícita la diferencia
entre “cero dentro del umbral” y “cero señal en la región”, y entre “varios
clusters” y “varios incendios confirmados”.

## 2. Study area and period

El área de adquisición y procesamiento es Coclé, Panamá, con el periodo FIRMS
2025-01-01–2025-04-30. La comparación externa usa dos anclas administrativas
proporcionadas por el investigador:

| Referencia | Coordenadas usadas | Ventana inclusiva | Regla espacial |
|---|---:|---|---:|
| `REFERENCE-001` — Cerro Los Picachos, Olá | `8.420970, -80.651140` | 2025-01-15–17 | `<=5,000 m` |
| `REFERENCE-002` — Cerro Guacamaya, Penonomé | `8.516667, -80.433333` | 2025-01-23–27 | `<=5,000 m` |

Las distancias oficiales reutilizan la métrica del contrato de clustering:
proyección `EPSG:32617` y distancia euclidiana en metros. Los anillos de 5 km
de la figura cartográfica son únicamente aproximaciones visuales.

## 3. Data sources

Las fuentes locales y sus límites son:

- fragmentos FIRMS VIIRS ya presentes en `data/raw/`, con 1,532 registros
  originales y sus manifests;
- `data/processed/firms_cocle_2025_detections.csv`, con 1,185 detecciones
  dentro de Coclé;
- `outputs/clustering/r1500_t06/events.csv` y `membership.csv`, ya congelados;
- el piloto Sentinel-2 existente, sus inventarios y métricas NBR/dNBR;
- el paquete local `window_median` de siete casos de calibración;
- el registro canónico de procedencia externa en
  `references/external_reference_sources_v1.json`: siete artículos o
  comunicados localizados que documentan dos incidentes. El registro distingue
  prensa de instituciones públicas y conserva las afirmaciones de cada fuente;
  no convierte esas referencias en ground truth ni en una validación
  independiente.

La fase final solo lee estos artefactos. No se incorporan ERA5, WorldCover,
DEM, datos de 2026, modelos, targets ni nuevas fuentes ambientales.

## External reference sources

El registro canónico `references/external_reference_sources_v1.json` tiene
`external_reference_provenance=complete`, siete fuentes y dos incidentes. Las
cinco fuentes de prensa y los dos comunicados institucionales se mantienen
como registros separados; los campos `researcher_summary` son resúmenes de
trabajo y no transcripciones ni citas directas.

| source_id | Publisher | Publication date | Incident | Reported date/window | Reported area | Cause status | URL |
|---|---|---|---|---|---:|---|---|
| `SOURCE-001` | TVN Noticias | 2025-01-17 | `REFERENCE-001` — Los Picachos | 2025-01-16 | — | not reported | [TVN](https://www.tvn-2.com/nacionales/incendio-picachos-ola-afecto-extensa-area-investigan-causas_1_2173253.html) |
| `SOURCE-002` | TVN Noticias | 2025-01-26 | `REFERENCE-002` — Guacamaya | 2025-01-25 | ~1,035 ha | not reported | [TVN](https://www.tvn-2.com/nacionales/provincias/cerro-guacamaya-mil-hectareas-afectadas-incendio-reserva-hidrica_1_2174469.html) |
| `SOURCE-003` | TVN Noticias | 2025-01-27 | `REFERENCE-002` — Guacamaya | 2025-01-23 (start) | >1,050 ha | suspected_intentional | [TVN](https://www.tvn-2.com/nacionales/siguen-trabajos-controlar-incendio-cerro_1_2174481.html) |
| `SOURCE-004` | EcoTV Panamá | 2025-01-27 | `REFERENCE-002` — Guacamaya | 2025-01-23–27 | ~1,500 ha | suspected_intentional | [EcoTV](https://www.ecotvpanama.com/nacionales/autoridades-extinguen-incendio-cerro-guacamaya-penonome-n6026325) |
| `SOURCE-005` | Telemetro Noticias | 2025-01-27 | `REFERENCE-002` — Guacamaya | 2025-01-26 | — | suspected_intentional | [Telemetro](https://www.telemetro.com/nacionales/noticias/2025/01/27/incendio-cerro-guacamaya-3000.html) |
| `SOURCE-006` | Benemérito Cuerpo de Bomberos de la República de Panamá | 2025-01-28 | `REFERENCE-002` — Guacamaya | 2025-01-26 | ~1,500 ha | not reported | [Bomberos](https://www.bomberos.gob.pa/2025/01/28/incendios-en-cerro-guacamaya-y-tubuala-control-prevencion-y-nuevas-alianzas-internacionales/) |
| `SOURCE-007` | Ministerio de Ambiente de Panamá (MiAMBIENTE) | 2025-02-07 | `REFERENCE-002` — Guacamaya | 2025-01-23–27 | — | suspected_intentional | [MiAMBIENTE](https://miambiente.gob.pa/avanzan-investigaciones-sobre-incendio-en-la-reserva-hidrica-cerro-guacamaya-y-reiteran-recompensa-para-encontrar-a-los-responsables/) |

Las coordenadas usadas para el matching no se atribuyen a las noticias: son
anclas aproximadas proporcionadas por el investigador (`coordinate_status=approximate`,
`coordinate_source=researcher_provided_approximate_anchor`), y cada fuente
registra `coordinate_claimed_by_news_source=false`. Para Guacamaya se conserva
la discrepancia de áreas reportadas, de 1,035 a 1,500 ha, con las
calificaciones `around`, `more_than`, `about` y `near` por fuente. FirePA no
elige un área verdadera, mejor o verificada, y la discrepancia no participa en
el matching ni en la selección de targets. `null` y `suspected_intentional`
también se conservan como estados de causa distintos; la intencionalidad queda
como sospechada/no confirmada.

La cobertura de la búsqueda manual OSINT quedó documentada así:

| Mes | Artículos localizados |
|---|---:|
| 2025-01 | 6 |
| 2025-02 | 1 |
| 2025-03 | 0 |
| 2025-04 | 0 |

No qualifying articles were located during the manual OSINT search for March or April 2025.
Esta ausencia de artículos localizados no equivale a ausencia de actividad
térmica ni a ausencia de incendios, y la búsqueda no se declara exhaustiva.
Las URLs del registro son solo procedencia; no son inputs del pipeline, no se
requiere disponibilidad de red para reproducir los resultados científicos y
ninguna fuente externa se usa como ground truth.

## 4. FIRMS acquisition and audit

El flujo de atrición observado en el perfil local es:

| Etapa | Conteo |
|---|---:|
| Registros crudos | 1,532 |
| Registros válidos de esquema | 1,532 |
| Fecha/coordenadas válidas | 1,532 |
| Dentro del periodo pedido | 1,532 |
| Dentro de Coclé | 1,185 |

La cohorte procesada contiene 625 detecciones de `N` y 560 de `N20`; 945 son
de día y 240 de noche. El filtro espacial de Coclé explica la diferencia entre
el conteo crudo y el procesado. La auditoría de Los Picachos usa los 1,185
registros procesados originales, sin reclustering y sin sustituirlos por una
consulta nueva.

## 5. Spatiotemporal clustering

`r1500_t06` permanece congelado con radio espacial de 1,500 m, ventana UTC de
6 h, componentes conexas y `EPSG:32617`. Sus 1,185 detecciones producen 611
clusters provisionales:

| Medida | Conteo |
|---|---:|
| Clusters totales | 611 |
| Singletons | 344 |
| Multi-detección | 267 |
| `possible_chain_merge=true` | 17 |

Las aristas usan solo coordenadas y tiempo. FRP, satélite, instrumento,
confianza y día/noche son atributos descriptivos. Un cluster no prueba una
ignición única ni un incendio confirmado. El hash de `events.csv` es
`646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844`.

## 6. Sentinel-2 follow-up

La cohorte óptica existente conserva 30 eventos. Bajo la política local, 28
son observables y 2 permanecen `unobserved`. El informe de observabilidad no
descarga raster durante esta fase final y el análisis externo no amplía la
cohorte: ninguno de los seis matches de Guacamaya pertenece a esos 30 eventos.

Las fases históricas que produjeron los artefactos Sentinel-2 tienen sus
propios checkpoints; este cierre no vuelve a ejecutarlas ni cambia sus
inventarios, parejas, métricas o quicklooks.

## 7. NBR and dNBR

El artefacto existente usa `NBR=(B8-B12)/(B8+B12)` y
`dNBR=NBR_pre-NBR_post` bajo el contrato Sentinel-2 v3. Hay métricas para 28
eventos. Son índices descriptivos sujetos a nubosidad, bruma, agricultura,
fenología, humedad, suelo expuesto, agua y otras señales competidoras.

No se crean categorías de severidad, `significant_burn`, targets ni etiquetas
de verdad de terreno. Un valor dNBR no confirma por sí solo que una anomalía
térmica sea un incendio.

## 8. `selected_pair` and `window_median`

`selected_pair` y `window_median` se mantienen como modos separados. El paquete
local `window_median` reutilizado en esta fase corresponde exactamente a
`calibration-7`, con 7/7 sidecars y paneles QA en estado `pilot_pass`. El
paquete no se conecta a las 56 asignaciones de la ronda formal y no sustituye
los artefactos `selected_pair`.

La tabla `window_median` es evidencia técnica local para revisión futura, no
ground truth, severidad ni pseudolabel científico.

## 9. Optical observability

La atrición óptica del piloto es 30 → 28 observables + 2 `unobserved`.
`unobserved` significa que la política no obtuvo soporte óptico utilizable; no
significa ausencia de incendio ni clase negativa. La cohorte fue congelada
antes del chequeo externo y no se re-muestrea para favorecer las referencias.

## 10. Formal review deferred

La infraestructura `formal_review_28` queda preparada, pero no iniciada:

```text
formal_review_status = deferred
formal_review_reason = QUALIFIED_REVIEWER_UNAVAILABLE
execution_authorized = false
execution_status = not_started
formal_human_observations = 0
observable_events = 28
unobserved_events = 2
assignments = 56
Pass A = 0
Pass B = 0
```

La SQLite, los paquetes ciegos, migraciones, manifests y assets de revisión no
se modifican. La falta de ejecución es una decisión científica y administrativa,
no un resultado de revisión humana.

## 11. AI pseudolabel calibration limitations

Las salidas IA históricas siguen marcadas como `provisional_pseudolabels`.
No son observaciones humanas, no son ground truth y no se usan como target.
No se entrena un modelo, no se evalúa exactitud y no se convierte el acuerdo
entre revisores IA en una métrica de desempeño.

## 12. External reference methodology

El chequeo externo local lee los 611 clusters congelados y conserva todos los
matches que satisfacen simultáneamente:

1. distancia `<=5,000 m`, inclusiva;
2. intersección temporal con la ventana de fechas inclusiva de la referencia.

No se selecciona únicamente el match más cercano, no se reclusteriza, no se
realiza una nueva búsqueda OSINT y no se conecta la salida con revisión formal
o Sentinel-2. La procedencia queda cerrada en el registro canónico de siete
fuentes; sus URLs solo documentan origen y no son inputs del pipeline. Los
resultados oficiales permanecen:

| Referencia | Ventana oficial | Matches oficiales |
|---|---|---:|
| Los Picachos | 2025-01-15–17, `<=5 km` | **0** |
| Guacamaya | 2025-01-23–27, `<=5 km` | **6** |

## 13. Los Picachos: diagnosis of the official zero

### 13.1 Nearest spatial clusters without temporal filter

Los diez clusters más cercanos espacialmente no están restringidos a enero. Se
reportan para distinguir proximidad espacial de contemporaneidad:

| # | Event ID | Distancia m | Inicio UTC | Fin UTC | n | Max FRP | Mean FRP | Satélites | Chain |
|---:|---|---:|---|---|---:|---:|---:|---|---|
| 1 | `event-r1500_t06-dbeab5bcc9613d47` | 2,093.597 | 2025-03-26 18:11 | 2025-03-26 18:34 | 2 | 7.03 | 5.925 | N/N20 | no |
| 2 | `event-r1500_t06-c577392559a8ec2d` | 2,535.586 | 2025-04-21 18:47 | 2025-04-21 18:47 | 1 | 3.26 | 3.26 | N20 | no |
| 3 | `event-r1500_t06-1bceeb68c355a3ba` | 2,543.944 | 2025-04-16 18:41 | 2025-04-16 18:41 | 1 | 10.62 | 10.62 | N20 | no |
| 4 | `event-r1500_t06-534911df03ada64f` | 3,354.011 | 2025-04-14 18:56 | 2025-04-14 18:56 | 1 | 4.50 | 4.50 | N | no |
| 5 | `event-r1500_t06-ce4fc2185602279d` | 3,360.986 | 2025-02-11 18:18 | 2025-02-11 18:18 | 1 | 3.95 | 3.95 | N | no |
| 6 | `event-r1500_t06-9656e1b58b213e9d` | 3,891.589 | 2025-03-01 06:36 | 2025-03-01 06:58 | 3 | 3.09 | 1.577 | N/N20 | no |
| 7 | `event-r1500_t06-fe79c8594f8dcaec` | 3,921.372 | 2025-04-26 18:53 | 2025-04-26 18:53 | 1 | 2.67 | 2.67 | N20 | no |
| 8 | `event-r1500_t06-193af5c15005c444` | 4,249.382 | 2025-04-23 19:28 | 2025-04-23 19:28 | 1 | 3.30 | 3.30 | N | no |
| 9 | `event-r1500_t06-34eff2b7a8e22d29` | 4,489.819 | 2025-02-28 18:22 | 2025-02-28 18:22 | 2 | 5.05 | 3.215 | N20 | no |
| 10 | `event-r1500_t06-2116a13f413a2b28` | 5,022.445 | 2025-04-15 19:00 | 2025-04-15 19:00 | 2 | 5.59 | 5.585 | N20 | no |

La cercanía espacial general existe en otras fechas; eso no cambia el cero
oficial porque la regla exige intersección temporal.

### 13.2 Temporally relevant clusters

Solo cinco clusters `r1500_t06` intersectan la ventana 2025-01-15–17. El más
cercano queda a 10,400.826 m, por lo que no existe un cluster contemporáneo
dentro de 5 km:

| # | Event ID | Distancia m | Inicio UTC | Fin UTC | n | Max FRP | Mean FRP | Satélites |
|---:|---|---:|---|---|---:|---:|---:|---|
| 1 | `event-r1500_t06-a8063ddbdc48a401` | 10,400.826 | 2025-01-15 18:47 | 2025-01-15 18:47 | 1 | 7.47 | 7.47 | N20 |
| 2 | `event-r1500_t06-89cc709095d312c8` | 19,967.149 | 2025-01-15 06:02 | 2025-01-15 07:20 | 2 | 1.73 | 1.64 | N/N20 |
| 3 | `event-r1500_t06-73f387ddb59c27bb` | 21,670.077 | 2025-01-15 18:47 | 2025-01-15 18:47 | 1 | 3.53 | 3.53 | N20 |
| 4 | `event-r1500_t06-63b59e62c26d40aa` | 27,330.925 | 2025-01-16 18:28 | 2025-01-16 18:28 | 1 | 4.35 | 4.35 | N20 |
| 5 | `event-r1500_t06-d254fa9ed0e3eaf9` | 31,998.498 | 2025-01-15 18:25 | 2025-01-15 18:47 | 5 | 10.12 | 8.228 | N/N20 |

Por tanto, sí existió señal FIRMS contemporánea fuera de 5 km; el cero
oficial no debe describirse como `NO_FIRMS_SIGNAL_NEAR_REFERENCE`.

### 13.3 Raw FIRMS audit and classification

La auditoría usa los 1,185 registros procesados originales, con conteo de
detecciones en radios concéntricos y sin reemplazar el resultado oficial:

| Ventana | Registros en ventana | <=5 km | <=10 km | <=15 km | Detección más cercana |
|---|---:|---:|---:|---:|---|
| Oficial 2025-01-15–17 | 10 | 0 | 0 | 1 | 10,400.826 m; 2025-01-15 18:47Z; FRP 7.47; N20; día |
| Diagnóstica 2025-01-13–19 | 13 | 0 | 0 | 1 | 10,400.826 m; 2025-01-15 18:47Z; FRP 7.47; N20; día |

La clasificación administrativa sustentada es:

```text
SPATIAL_THRESHOLD_MISS
reference_location_uncertainty_used = false
```

La evidencia es compatible con una señal FIRMS contemporánea a más de 10 km y
fuera del umbral de 5 km. No hay evidencia local suficiente para invocar
incertidumbre de la ubicación de referencia, y no se inventa dicha
incertidumbre.

## 14. Guacamaya: official matches

Los seis matches oficiales se conservan, en orden cronológico. La columna
`possible_chain_merge` es un atributo del cluster y no una etiqueta de incendio.

| # | Event ID | Distancia m | Inicio UTC | Fin UTC | n | Max FRP | Mean FRP | Satélites | Día/Noche | Chain |
|---:|---|---:|---|---|---:|---:|---:|---|---|---|
| 1 | `event-r1500_t06-e56bcec4b33a68c1` | 4,680.024 | 2025-01-24 06:11 | 2025-01-24 06:33 | 2 | 7.69 | 5.850 | N/N20 | 0/2 | no |
| 2 | `event-r1500_t06-62fb92c99f6df90e` | 4,780.810 | 2025-01-24 18:56 | 2025-01-24 19:19 | 4 | 5.05 | 4.885 | N/N20 | 4/0 | no |
| 3 | `event-r1500_t06-22d8da58d584e847` | 3,076.389 | 2025-01-25 18:37 | 2025-01-25 19:00 | 3 | 13.67 | 10.243 | N/N20 | 3/0 | no |
| 4 | `event-r1500_t06-9d569e8c7453d3ef` | 3,954.607 | 2025-01-26 05:56 | 2025-01-26 07:13 | 5 | 7.92 | 4.334 | N/N20 | 0/5 | **yes** |
| 5 | `event-r1500_t06-846683c14a5c5d27` | 3,958.667 | 2025-01-26 18:18 | 2025-01-26 18:18 | 1 | 4.49 | 4.490 | N | 1/0 | no |
| 6 | `event-r1500_t06-76a3f8054858a779` | 3,337.361 | 2025-01-27 06:55 | 2025-01-27 06:55 | 4 | 2.91 | 1.263 | N | 0/4 | no |

Los conteos y la regla oficial no se alteran por los diagnósticos de esta
sección.

## 15. Guacamaya fragmentation under `t06`

La primera observación emparejada comienza 2025-01-24 06:11Z y la última
termina 2025-01-27 06:55Z: span de **72.733 h**. Hay seis clusters distintos,
con 2, 4, 3, 5, 1 y 4 detecciones. Los huecos entre el fin de un cluster y el
inicio del siguiente son:

| Transición | Hueco h | Mayor que 6 h |
|---|---:|---|
| C1 → C2 | 12.383 | sí |
| C2 → C3 | 23.300 | sí |
| C3 → C4 | 10.933 | sí |
| C4 → C5 | 11.083 | sí |
| C5 → C6 | 12.617 | sí |

La cronología de las detecciones crudas dentro de cada cluster es:

| Cluster | Detecciones UTC / FRP MW / sensor-día-noche |
|---|---|
| C1 | 06:11 / 4.01 / N-N; 06:33 / 7.69 / N20-N |
| C2 | 18:56 / 4.83 / N-D; 18:56 / 4.83 / N-D; 18:56 / 4.83 / N-D; 19:19 / 5.05 / N20-D |
| C3 | 18:37 / 10.02 / N-D; 19:00 / 7.04 / N20-D; 19:00 / 13.67 / N20-D |
| C4 | 05:56 / 3.83 / N20-N; 05:56 / 7.92 / N20-N; 05:56 / 7.25 / N20-N; 07:13 / 1.67 / N-N; 07:13 / 1.00 / N-N |
| C5 | 18:18 / 4.49 / N-D |
| C6 | 06:55 / 0.30, 1.11, 2.91, 0.73 / N-N |

La evolución de FRP es descriptiva: máximos `[7.69, 5.05, 13.67, 7.92,
4.49, 2.91] MW` y medias `[5.85, 4.885, 10.243, 4.334, 4.49, 1.263] MW`.
El máximo de la secuencia está en C3 y los dos últimos máximos son menores; no
se infiere una trayectoria causal.

La interpretación congelada se expresa exactamente así:

> "r1500_t06 represents temporally separated thermal observations as distinct provisional events; prolonged documented incidents may therefore correspond to multiple FirePA events."

La fragmentación es una limitación de representación posible si la actividad
documentada fue persistente durante esos huecos; no demuestra que `t06` sea
incorrecto y no autoriza cambiar el clustering en este cierre.

## 16. Distributional comparison

Se reutiliza la distribución completa de 611 clusters. Los estadísticos son
descriptivos y no se combinan en un índice o score:

| Métrica | Mediana | IQR | P90 | P95 | P99 |
|---|---:|---:|---:|---:|---:|
| `max_frp` MW | 4.79 | 5.02 | 13.94 | 20.90 | 42.25 |
| `mean_frp` MW | 4.52 | 4.09 | 11.1467 | 15.65 | 37.365 |
| `n_detections` | 1 | 1 | 4 | 5 | 7 |
| `duration` h | 0 | 0 | 0.3833 | 0.3833 | 1.3 |

Los percentiles oficiales de cada match Guacamaya y el rango inclusivo dentro
de 611 (`rank = número de valores <= al valor observado`) son:

| Event ID | Max FRP p / rank | Mean FRP p / rank | n p / rank | Duration p / rank |
|---|---:|---:|---:|---:|
| `...-e56bcec4b33a68c1` | 73.813 / 451 | 67.594 / 413 | 77.578 / 474 | 82.488 / 466 |
| `...-62fb92c99f6df90e` | 53.355 / 326 | 55.810 / 341 | 93.126 / 569 | 97.545 / 596 |
| `...-22d8da58d584e847` | 89.198 / 545 | 88.380 / 540 | 87.561 / 535 | 97.545 / 596 |
| `...-9d569e8c7453d3ef` | 74.468 / 455 | 46.645 / 285 | 96.236 / 588 | 98.036 / 599 |
| `...-846683c14a5c5d27` | 45.499 / 278 | 48.773 / 298 | 56.301 / 344 | 75.123 / 459 |
| `...-76a3f8054858a779` | 23.568 / 144 | 7.529 / 46 | 93.126 / 569 | 75.123 / 459 |

No se construye un percentile composite y no se usa esta tabla para afirmar
severidad, importancia operacional o desempeño.

## 17. Scientific limitations

- FIRMS registra anomalías térmicas y tiene resolución, hora de paso y
  limitaciones de detección propias; no prueba un incendio.
- La ubicación externa es una ancla administrativa y no tiene una fuente
  externa registrada en el checkout.
- La clasificación `SPATIAL_THRESHOLD_MISS` describe la relación entre los
  datos y el umbral; no juzga la verdad de la referencia ni la cobertura total
  del sensor.
- Un cluster no equivale a una ignición, incendio o cicatriz única.
- Una ausencia óptica `unobserved` no es un negativo.
- Los percentiles y rangos describen la cohorte de 611 y no son métricas de
  precisión.
- `possible_chain_merge` es un indicador de revisión del cluster, no una clase
  de incendio.
- La revisión formal no tiene observaciones humanas, por lo que no hay target
  defendible para aprendizaje supervisado.

## 18. What FirePA supports at this checkpoint

El checkout soporta adquisición FIRMS reproducible, clustering espacio-temporal
provisional, seguimiento óptico Sentinel-2, evidencia `selected_pair` y
`window_median`, NBR/dNBR descriptivo, procedencia/auditoría y comparación
exploratoria con referencias externas.

## 19. What this pilot cannot support

No soporta clasificación confirmada de incendios, ground truth, predicción
supervisada, monitoreo operacional, alertas en tiempo real, estimación validada
de severidad, validación institucional, generalización a toda la región ni
afirmaciones de exactitud o sensibilidad.

## 20. Reproducibility and integrity

La reconstrucción local del bundle ignorado es:

```powershell
python scripts/build_final_scientific_report.py
python scripts/verify_final_scientific_report.py
python scripts/verify_external_reference_check.py
python scripts/verify_formal_review_28.py
python scripts/verify_window_median_review_asset.py --case-set calibration-7
python -m pytest -q
```

El bundle generado está en `outputs/final_scientific_report/` y contiene seis
PNG estáticos, diagnósticos JSON/CSV y `manifest.json` con SHA-256. Las figuras
son:

1. `01_pipeline_overview.png`
2. `02_cluster_distribution.png`
3. `03_external_reference_map.png`
4. `04_guacamaya_timeline.png`
5. `05_guacamaya_frp_distribution.png`
6. `06_los_picachos_diagnostic.png`

Hashes de inputs/protegidos verificados para este cierre:

| Artefacto | SHA-256 |
|---|---|
| processed FIRMS | `3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e` |
| `r1500_t06/events.csv` | `646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844` |
| `r1500_t06/membership.csv` | `e9629fb521ce05d7cf63ad68683c0c79801611102e454c6877e3746977efc504` |
| `r1500_t06/summary.json` | `1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736` |
| optical pilot cohort | `a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302` |
| Sentinel-2 observability inventory | `851beea9b09e19368cf1131e82b0df5de7e5cd98566cf1da4cddeab464c7dcd1` |
| Sentinel-2 AOI inventory | `fc0b77eb283455d08226152c50017d7cc70e3e0427f59f02788f0ce6d469a5b4` |
| selected-pair table | `24ba96aa8ee2a5a45d81e54d724d22c143be66583854764ef6c8919ea6b3dcd1` |
| dNBR metrics | `9a1b0043a11ddf1da6e5fb5fe5a08241a28ee7d8e442d3832f4d8345fec30441` |
| formal SQLite | `c8f96d1c82bb6948010f796e801735c8786603b1d06390080265a2d324ff2cba` |
| formal preparation summary | `d5124dbe20bec1f15ff44a6e3e96d5bef73c5f23f149eed168e37a21ab44ddb4` |
| `window_median` manifest | `f7d9c619cda537800f777523434a4c22925156628ecfad17ad02fac7656c30fd` |
| external-check manifest | `92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868` |
| external source registry (`references/external_reference_sources_v1.json`) | `6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49` |

La tabla de conteos reproducibles requerida para el handoff es:

| Elemento | Conteo |
|---|---:|
| FIRMS raw | 1,532 |
| FIRMS processed | 1,185 |
| `r1500_t06` | 611 |
| singletons | 344 |
| multi | 267 |
| `possible_chain_merge` | 17 |
| pilot events | 30 |
| observable | 28 |
| unobserved | 2 |
| formal human observations | 0 |
| external references | 2 |
| external source documents | 7 |
| official Picachos matches | 0 |
| official Guacamaya matches | 6 |

La auditoría final confirmó `changed_count=0` para inputs FIRMS, clustering,
inventarios Sentinel-2, `selected_pair`, métricas dNBR, SQLite formal, bundle
científico y visual index. Los ocho archivos no rastreados preexistentes se
conservan fuera del commit.

## 21. Future work

Una siguiente fase solo puede abrirse explícitamente. Requiere, como mínimo,
una nueva versión del registro si se agregan o corrigen fuentes, revisores
calificados, observaciones humanas trazables y una decisión metodológica sobre
qué salida científica se permite. Cualquier cambio de clustering, variables ambientales,
target, modelo o UI debe pasar su propio gate y no se infiere desde este
chequeo. La posible fragmentación de Guacamaya es una hipótesis descriptiva
para revisar, no autorización para cambiar `t06`.

## 22. Conclusion

El piloto queda cerrado analíticamente dentro de su alcance. El cero oficial de
Los Picachos se explica como `SPATIAL_THRESHOLD_MISS`, con señal FIRMS
contemporánea a 10,400.826 m y ninguna detección a 5 km. Guacamaya tiene seis
matches oficiales distribuidos en seis clusters y cinco huecos mayores que la
ventana `t06`, compatibles con fragmentación de representación si la actividad
documentada persistió. Ambos resultados son relaciones descriptivas sobre
artefactos locales congelados; no son ground truth, clasificación de incendios
ni validación de desempeño.
