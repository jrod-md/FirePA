# Preflight técnico — FuegoPA

Fecha de esta revisión: 2026-07-19.

Este documento resume el alcance que se desprende de `CONTEXT.md`, `PLAN.md` y
`SOURCES.md`. No reemplaza ni reescribe el historial de correcciones.

## Alcance aprobado para esta fase

- **Zona piloto:** provincia de Coclé; el filtro definitivo requiere una
  geometría local oficial o reconocida y no acepta un bbox como sustituto.
- **Periodo principal:** `2025-01-01..2025-04-30`, fechas inclusivas.
- **Periodo secundario reservado:** `2026-01-01..2026-04-30`; no se consulta ni
  se usa para definir la cohorte actual. El CLI rechaza cambiar a 2026 en esta
  fase.
- **Salida autorizada:** detecciones FIRMS filtradas, manifests, perfil de
  calidad y una sensibilidad reproducible de componentes algorítmicos. No se
  fija aún una tabla final de eventos ni se avanza a Sentinel-2, dNBR,
  variables ambientales, modelado o interfaz.

## Objetivo científico exacto

Determinar si un modelo que integre detecciones térmicas satelitales de NASA
FIRMS con variables meteorológicas, de cobertura vegetal y de topografía puede
predecir qué **eventos FIRMS** producirán posteriormente una cicatriz de quema
significativa observada mediante Sentinel-2 y dNBR, con mejor desempeño que un
baseline FIRMS-only. El data spike comienza con la cohorte de detecciones de
Coclé entre 2025-01-01 y 2025-04-30.

El objetivo es una prueba de factibilidad metodológica en Panamá. No es todavía
un sistema web, un producto operativo para Bomberos ni una promesa de
optimización de despacho. La verdad de referencia propuesta debe ser observable
desde el espacio mediante Sentinel-2, NBR y dNBR, sin depender de registros
institucionales privados.

## Variable objetivo propuesta

La unidad etiquetada debe ser un **evento de fuego agrupado**, no una fila FIRMS
individual. La variable objetivo propuesta es binaria y se puede nombrar
`significant_burn`:

- `1`: el evento queda asociado posteriormente a una cicatriz de quema que
  supera un umbral de significancia definido con área observada y/o dNBR.
- `0`: no se observa esa cicatriz dentro de una ventana de observación válida,
  distinguiendo cuando la ausencia se debe a nubes o falta de observación.

Todavía no existe un umbral numérico de área, dNBR, nube, ventana temporal ni
regla de asociación. Por tanto, esta es una definición de trabajo, no una
etiqueta disponible ni un resultado. Antes de modelar habrá que separar
`negative` de `unobserved` para no convertir nubosidad en un cero falso.

## Baseline propuesto

El baseline propuesto es una regla FIRMS-only basada en mayor potencia
radiativa (`frp`) agregada a nivel de evento. El resultado se comparará contra
la misma partición y la misma métrica que el modelo multivariable. Esta etapa no
calcula el baseline porque todavía no existen eventos ni etiquetas.

La confianza satelital puede reportarse como comparación descriptiva o baseline
secundario, pero debe declararse antes de evaluar resultados. No se mezclará con
FRP ni se elegirá después de observar el desempeño.

## Unidades de análisis

1. **Fila de detección FIRMS:** unidad de ingestión de esta primera etapa; cada
   fila conserva su fecha, coordenadas, satélite, instrumento, confianza y FRP.
2. **Evento agrupado:** unidad científica prevista para etiqueta y predicción;
   se construirá agrupando detecciones cercanas en espacio y tiempo.
3. **Observación de resultado:** evidencia Sentinel-2 pre/post utilizada para
   estimar área de cicatriz y severidad espectral dNBR.

La implementación de adquisición conserva la primera unidad y la sensibilidad
ejecuta componentes provisionales para medir cambios entre parámetros. No
trata cada detección como incendio independiente y no convierte ninguna
configuración en la unidad final.

## Decisiones todavía abiertas

- Mantener trazable la procedencia/licencia del extracto IGN/ANATI cuando se
  replique en otra máquina; el checkout actual ya verificó la capa provincial,
  pero el archivo fuente y el GeoJSON generado permanecen fuera de Git.
- Mantener trazable la snapshot real de disponibilidad ya auditada: para esta
  cohorte se seleccionaron `VIIRS_NOAA20_SP` y `VIIRS_SNPP_SP`; una nueva
  corrida debe reemplazarla solo con una respuesta verificable.
- Regla de clustering espacio-temporal: radio, ventana, conectividad y pruebas
  de sensibilidad; la grilla 375/750/1500/3000 m x 6/12/24/48 h ya fue
  ejecutada. `r1500_t06` quedó aprobado provisionalmente por estabilidad y
  riesgos diagnósticos, no por un conteo conveniente.
- Interpretación de los diagnósticos de encadenamiento y aprobación de una
  semántica de evento antes de asociar cicatrices.
- Definición cuantitativa de `significant_burn`, área mínima y umbral dNBR.
- Ventana pre/post Sentinel-2, tratamiento de nubes, composiciones multi-fecha
  y regla para eventos no observables.
- Regla para asociar una cicatriz a un evento y tratar quemas agrícolas o
  incendios simultáneos.
- Resolución y fecha efectiva de extracción de ERA5-Land, WorldCover y DEM.
- Comparabilidad entre instrumentos/satélites y tratamiento de confianza
  categórica frente a numérica.
- Tamaño final de muestra, partición temporal/espacial y métrica principal.
- Criterio para datos faltantes y exclusiones antes de calcular el baseline.
- Regla previa para aceptar una variante de esquema FIRMS si una fuente real
  entrega columnas adicionales o nombres alternativos no documentados.
- Si la comparación con confianza será un segundo baseline y cómo se fijará
  antes de evaluar.

## Riesgos metodológicos

- Varias detecciones FIRMS pueden ser el mismo incendio; contar filas como
  observaciones independientes produciría pseudorreplicación.
- FIRMS puede incluir quemas agrícolas controladas y anomalías no equivalentes
  a un incendio de vegetación.
- La nubosidad frecuente de Panamá puede ocultar cicatrices; una imagen ausente
  no es automáticamente ausencia de quema.
- Un piloto de 20–30 eventos puede ser insuficiente para estimar desempeño o
  generalización; cualquier resultado sería exploratorio.
- FRP, confianza, resolución espacial y revisita no son comparables sin revisar
  el instrumento y la fuente concreta.
- ERA5-Land es contexto regional y WorldCover puede estar desactualizado frente
  a cambios de uso; no deben presentarse como medición exacta de cada parcela.
- Extraer variables o escoger fechas usando información posterior al evento
  puede introducir leakage.
- Eventos cercanos en espacio o tiempo pueden quedar en train y test, inflando
  la evaluación si la partición no respeta dependencia espacial/temporal.
- La conectividad transitiva puede unir detecciones por una cadena de enlaces;
  la bandera `possible_chain_merge` ayuda a revisar, pero no resuelve por sí
  sola si debe dividirse un componente.
- Cambiar de radio o ventana altera simultáneamente el conteo de eventos,
  singletons y componentes multi-sensor; reportar una sola configuración sin
  la matriz vecina ocultaría sensibilidad metodológica.
- La relación entre un punto térmico y una cicatriz posterior tiene error de
  localización, escala y causalidad; debe documentarse como asociación.
- Un límite administrativo de distinta versión, nivel o CRS puede cambiar la
  cohorte; por eso la geometría se valida y se conserva fuera de Git con su
  procedencia.
- Las ventanas de disponibilidad, errores de red y fragmentos fallidos pueden
  confundirse con días sin detecciones si no se distinguen en los manifests.
- Incluir 2026 durante la selección o ajuste de reglas produciría fuga temporal
  frente a la cohorte 2025 y está bloqueado por configuración.

## Credenciales, claves y accesos externos potenciales

- **FIRMS:** la descarga concreta puede requerir una clave de mapa/API. Si se
  usa, debe llegar por `FIRMS_MAP_KEY` o `--map-key`; nunca debe entrar a Git ni
  al código. La interfaz ya consulta disponibilidad y sanitiza URLs.
- **Límite de Coclé:** no requiere una credencial privada; el checkout actual
  usa el extracto oficial local descrito en `SOURCES.md` y lo regenera con
  `scripts/prepare_cocle_boundary.py`. Si se vuelve a descargar, deben
  conservarse los mismos sidecars, licencia, CRS y hashes.
- **Google Earth Engine:** probablemente requerirá una cuenta/proyecto y
  autenticación para consultar Sentinel-2 y calcular NBR/dNBR. No se configura
  en esta etapa.
- **ERA5-Land, ESA WorldCover y Copernicus DEM:** el mecanismo de acceso y
  credenciales depende de la fuente/plataforma que se elija; todavía no se
  solicita ninguno.
- **Instituciones:** no son necesarias para construir la verdad de referencia
  propuesta. El outreach de Bomberos, MiAmbiente, SINAPROC o terceros sigue
  siendo opcional.

## Implementable inmediatamente

- Estructura mínima de Python, rutas raw/interim/processed, tests y configuración
  por entorno/CLI.
- Importación de un CSV FIRMS local real o descarga oficial por fuente, después
  de consultar disponibilidad.
- Validación del encabezado, normalización de fechas, coordenadas, satélite,
  instrumento, confianza, FRP, día/noche y metadatos disponibles.
- Copia raw byte a byte con SHA-256, manifests por fragmento y protección contra
  sobrescritura.
- Lectura reproducible de la capa provincial IGN/ANATI, selección exacta de
  `Coclé`, validación de partes, reproyección explícita a EPSG:4326, GeoJSON
  reproducido y filtro definitivo punto-en-polígono.
- CSV procesado inicial y perfiles JSON/Markdown con attrition, rango temporal,
  faltantes, coordenadas inválidas, duplicados exactos, instrumento, cobertura y
  coincidencias diagnósticas entre sensores.
- Ejecución local reproducible de 16 configuraciones de clustering, membresías,
  métricas de estabilidad, revisión de extremos y figuras diagnósticas.

## Requiere decisión o datos reales

- Repetir una descarga FIRMS solo si se necesita una nueva snapshot o si una
  auditoría demuestra que el raw local es incompleto; la corrida actual ya usa
  raw y manifests reales conservados localmente.
- Mantener disponibles la respuesta de disponibilidad y sus rangos efectivos;
  la selección 2025 auditada no se infiere por nombre de satélite.
- Revisar los componentes provisionales y aprobar una configuración/semántica
  final antes de hablar de eventos etiquetados.
- Conseguir observaciones Sentinel-2 utilizables y fijar la regla dNBR/área.
- Extraer variables meteorológicas, vegetación y topografía con fechas y
  resoluciones documentadas.
- Fijar baseline, partición, métricas y cualquier modelo predictivo.
- Construir dashboard, demo o interfaz de pitch, que están fuera de esta fase.

## Estado y criterio de salida de esta fase

La base técnica, el límite espacial oficial y la cohorte FIRMS 2025 quedan
preparados y validados localmente. La sensibilidad de clustering ya se ejecutó
sobre 1 185 detecciones y conserva todas las membresías, pero no existe
todavía evidencia científica de cicatrices ni resultado de modelo.
La próxima salida requiere revisar los componentes extremos y aprobar la
semántica de evento documentada en `docs/CLUSTERING_DESIGN.md` antes de usar
Sentinel-2/dNBR.

En la auditoría del 15 de julio de 2026 no se llamó a la red: la snapshot de
disponibilidad, los 48 raw y sus 48 manifests ya estaban presentes y sus hashes
coincidieron. La cohorte procesada resultó reproducible (1 185 filas dentro de
Coclé, sin 2026). `FIRMS_MAP_KEY` sigue siendo necesario únicamente para una
nueva adquisición; nunca se guarda en reportes, manifests, código o Git.

## Actualización de preflight — congelación provisional y observabilidad

La fase de sensibilidad ya tiene una configuración provisional aprobada para
continuar el data spike: `r1500_t06` (1 500 m, 6 h, componentes conexas,
EPSG:32617). La métrica de estabilidad media vecina es aproximadamente
`0.8894`; se preservan `1 185` detecciones en `611` eventos, de los cuales
`344` son singletons (`56.30%`) y `267` tienen múltiples detecciones. Hay `17`
eventos con `possible_chain_merge` (`2.78%`) y no hay mega-clusters según los
diagnósticos de la corrida.

La selección es provisional, no una validación científica. Se descartó
provisionalmente `r3000_t06` por mayor riesgo de fusión espacial (`561` eventos,
`48` posibles cadenas) y `r1500_t12` por mayor riesgo de unir sobrevuelos
separados (`601` eventos, `23` posibles cadenas). Los `611` eventos no son
incendios confirmados. Los singletons se mantienen y FRP/confianza no
participaron en las aristas ni en la formación de clusters. La decisión puede
cambiar tras Sentinel-2, especialmente en casos ambiguos.

### Estado de las tablas congeladas

El script `scripts/freeze_provisional_clustering.py` valida y transforma los
CSV existentes de `outputs/clustering/r1500_t06/`; no vuelve a ejecutar el
algoritmo. Produce las tablas de membresía y eventos provisionales, el piloto
estructural de 30 eventos y los reportes de muestreo. La ruta
`outputs/clustering/configurations/r1500_t06/` indicada en el handoff no existe
en este checkout; se usa la ruta real de los outputs ya generados.

El piloto utiliza la semilla `20260715`, cuotas marginales por tamaño,
cuartil de `detection_count` en multi-eventos, mes, fuente y
`possible_chain_merge`, y se selecciona antes de consultar imágenes. FRP no es
una variable de selección primaria ni directa.

### Qué queda abierto

- AOI Sentinel-2, buffers y ventanas pre/post: el diseño candidato y su pequeña
  sensibilidad están en `docs/SENTINEL2_OBSERVABILITY_DESIGN.md`.
- Autenticación/proyecto de Earth Engine y disponibilidad real de escenas;
  todavía no se ha hecho ninguna consulta.
- Umbrales de nubes, cobertura, criterio de escena utilizable y regla para
  eventos con solapamiento.
- Definición de NBR/dNBR, `significant_burn`, `unobserved` y cualquier etiqueta.
- Variables ERA5-Land, WorldCover y DEM, baseline, partición, métricas y
  modelo predictivo.

### Implementable ahora y lo que requiere datos reales

Ya se puede reproducir la congelación, validar esquemas, generar el muestreo y
mantener el esquema vacío de observabilidad sin red. Requiere decisión y datos
reales consultar Sentinel-2, medir nubes/cobertura, fijar escenas pre/post y
definir una etiqueta óptica. No se debe rellenar la tabla de observabilidad con
ceros o resultados ficticios.

No se consultaron imágenes en esta fase. Tampoco se implementaron Earth Engine,
máscara de nubes, NBR, dNBR, etiquetas, variables ambientales, modelos ni
interfaz.

## Actualización de implementación — observabilidad Sentinel-2

La interfaz técnica de observabilidad ya está preparada para el piloto de 30
eventos, sin producir resultados ópticos ficticios. Usa las colecciones
`COPERNICUS/S2_SR_HARMONIZED` y `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`,
enlace `system:index`, AOI `detection_union_buffer` y las combinaciones de
buffers, ventanas y reglas documentadas en
`docs/SENTINEL2_OBSERVABILITY_DESIGN.md`. La cobertura exige B8/B12 válidos en
conjunto y la claridad usa `cs_cdf`; `cs` y `CLOUDY_PIXEL_PERCENTAGE` quedan
como diagnósticos/metadatos.

La autenticación no se invoca automáticamente ni se guardan credenciales. El
proyecto se lee exclusivamente de `EARTH_ENGINE_PROJECT`. En el entorno usado
para esta validación esa variable no estaba disponible, por lo que el smoke
test y cualquier lote real quedan bloqueados hasta configurarla; no se
hardcodea un proyecto para sortear el bloqueo. Las pruebas unitarias usan
objetos simulados y no hacen llamadas de red.

Ya se puede implementar sin datos ópticos: validación del piloto, construcción
de AOI/ventanas, contratos, caché/checkpoint, reportes y figuras vacías o
descriptivas. Requiere acceso real: conteo de escenas, cobertura, nubosidad,
selección pre/post y cualquier decisión sobre cicatrices. Esta fase no calcula
NBR, dNBR, severidad, etiquetas, variables ambientales, modelos ni interfaz.

## Actualización de preflight — piloto NBR/dNBR

La siguiente etapa técnica queda limitada a las 28 filas procesables de la
selección óptica ya congelada. La política es b0500/pre30/post45/regla A como
principal y b0500/pre30/post90 como fallback temporal para un evento. Los dos
eventos excluidos se mantienen como
optically_unobservable_under_current_policy y no se convierten en negativos.

Se implementó un CLI separado para NBR y dNBR con máscara conjunta B8/B12,
Cloud Score+ enlazado, escala analítica de 20 m, sensibilidades cs_cdf 0.60 y
0.65, los modos selected_pair y window_median, cache, checkpoint y quicklooks
limitados al AOI. El umbral operativo predeterminado para publicar estadísticas
es una fracción común pre/post de 0.50; queda explícito, configurable y
provisional.

Esta fase no crea etiquetas significant_burn, categorías de severidad,
variables ambientales, modelos ni interfaz. La consulta real debe validarse
primero con un evento individual; el lote de 28 queda bloqueado hasta auditar
sus métricas y quicklook. El diseño reproducible está en
docs/SENTINEL2_DNBR_DESIGN.md.

## Actualización de preflight — cierre local Fase A y Level 1 — 21 de julio de 2026

Las secciones históricas anteriores que indicaban que NBR/dNBR no estaba
implementado describen el estado previo a la congelación v3. El estado actual
es un piloto reproducible sobre las 28 filas dNBR ya presentes y un compositor
Quicklook v2 local para siete casos de calibración; no es una validación de
incendios ni una etiqueta de referencia.

El CLI `scripts/run_dnbr_quicklook_v2.py` produjo 7/7 eventos sin modificar
CSV, JSON, cache o checkpoint científicos. Escribe 14 PNG en
`outputs/figures/sentinel2_dnbr_v2/events/` y 14 copias en
`outputs/review_upload_v2/`. El panel principal es RGB 2048 × 1440; la hoja
comparativa deja explícito que `window_median` es solo comparación de métricas.
El compositor usa únicamente datos locales y no realizó consultas Earth Engine.

La integridad revalidada cubre 179 entradas científicas del manifest y 231
entradas visuales v1: los conteos de cambios son cero y los digests de índice
antes/después coinciden. No se hallaron fechas de evento o escena en 2026. Los
casos sin observabilidad permanecen excluidos y no se convierten en negativos.

### Deuda abierta después de este checkpoint

- Revisión humana y protocolo para decidir cicatriz visible, confianza,
  competencia de cambio de uso y estado de revisión.
- Definición independiente de `significant_burn`, severidad y partición de
  evaluación.
- Raster numérico trazable para el rango diagnóstico y false-color SWIR; si se
  necesita obtenerlo desde Earth Engine, debe abrirse una fase y una auditoría
  separadas.
- Variables ERA5-Land, WorldCover y DEM, baseline, modelo, dashboard y pitch.
