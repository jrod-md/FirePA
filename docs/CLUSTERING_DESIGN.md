# Diseño de clustering espacio-temporal — sensibilidad ejecutada, selección provisional aprobada

Este documento define el experimento para estudiar cómo pasar de filas FIRMS a
eventos provisionales. La implementación ejecuta la matriz de sensibilidad y
asigna identificadores algorítmicos por configuración, pero no confirma
incendios, no fija todavía un evento científico definitivo, no consulta Sentinel-2 y no crea
etiquetas. La adquisición conserva las detecciones individuales y sus
duplicados para que la decisión pueda auditarse.

## Pregunta y unidades

- **Fila FIRMS:** unidad observacional de entrada. Puede ser una detección del
  mismo fenómeno observada por otro sensor, otra pasada o una fila duplicada.
- **Evento candidato:** conjunto de filas que una regla explícita considera
  compatible con una misma actividad de fuego. Será la unidad de predicción y
  de asociación con una cicatriz, si la evidencia posterior lo permite.
- **Etiqueta posterior:** `significant_burn` solo se podrá calcular después de
  definir observabilidad Sentinel-2, asociación espacial y temporal, umbral de
  área y umbral de dNBR.

Una fila nunca se interpretará como un incendio independiente. Tampoco se
eliminarán duplicados en la etapa de adquisición: eliminar o fusionar filas es
una decisión del diseño de eventos y debe dejar trazabilidad a las filas raw.

## Variables de agrupación candidatas

1. Tiempo de adquisición en UTC, con una regla explícita para fechas u horas
   faltantes.
2. Latitud/longitud válidas dentro de la geometría de Coclé.
3. Fuente, satélite e instrumento, para poder auditar diferencias de resolución
   o de producto.
4. FRP, confianza y día/noche como atributos descriptivos; no deben crear por
   sí solos un evento ni sustituir el vínculo espacial-temporal.

El bbox utilizado para la consulta FIRMS no sustituye el punto-en-polígono.
Solo las detecciones dentro de la geometría validada entran al futuro
experimento.

## Diseño del experimento ejecutado, sin parámetros finales

Antes de escoger una regla se genera una matriz de sensibilidad. La siguiente
cuadrícula es la **grilla de exploración ejecutada**, no una decisión
científica ni un valor final usado para etiquetar eventos:

| Eje | Valores candidatos | Motivo para explorarlos |
|---|---|---|
| Distancia espacial máxima | 375, 750, 1500 y 3000 m | Grilla fija de sensibilidad para la cohorte real; no se selecciona por producir un conteo conveniente. |
| Ventana temporal máxima | 6, 12, 24 y 48 h | Grilla fija de sensibilidad en UTC; no se agrega una ventana fuera de la corrida sin documentarla. |
| Conectividad | componentes conexas de un grafo | Una arista exige simultáneamente distancia `<= radio` y tiempo `<= ventana`; los diagnósticos no dividen automáticamente. |
| Regla de duración | sin límite impuesto por el algoritmo | La duración se reporta y se marca cuando es diagnóstica; imponer un corte sería una decisión posterior. |

La cuadrícula fue ejecutada sobre la cohorte local auditada de 1 185 detecciones
de la provincia piloto en 2025. No se seleccionará el resultado que produzca el número de
eventos más conveniente para el pitch. La revisión actual aprobó `r1500_t06`
como configuración provisional de trabajo; la validación óptica y la semántica
científica definitiva siguen abiertas.

Cada corrida deberá registrar:

- versión del código y configuración;
- fuentes, fragmentos raw y hashes utilizados;
- radio, ventana, conectividad y regla de duración;
- número de eventos, tamaño por evento, duración y extensión espacial;
- detecciones que quedan solas y detecciones absorbidas por cada evento;
- sensibilidad de cada evento a cambios pequeños de parámetros.

## Comparaciones que deben resolverse

Se deben comparar al menos una regla de grafo espacio-temporal y una alternativa
que controle el efecto de encadenamiento. La comparación debe considerar
eventos estables, no solamente el conteo total. También debe separar:

- coincidencias entre sensores que probablemente representan una misma
  actividad;
- detecciones consecutivas del mismo sensor;
- posibles quemas agrícolas o fuentes no equivalentes a una cicatriz de
  vegetación;
- puntos cercanos pero temporalmente incompatibles.

El perfil actual calcula coincidencias entre fuentes con umbrales diagnósticos
explícitos. Esa salida sirve para inspección y no forma eventos.

## Validación antes de etiquetar

No se debe asociar todavía una cicatriz Sentinel-2 a ningún grupo. Una vez
aprobada la regla de eventos, la validación debe revisar manualmente una muestra
de eventos grandes, pequeños, aislados, multi-sensor y cercanos entre sí. Debe
quedar documentado qué grupos son ambiguos y qué proporción no puede observarse
por nubes, revisita o resolución.

La etiqueta futura debe distinguir al menos `significant_burn`, `no_significant_burn`
y `unobserved`/`ambiguous`. `unobserved` no puede convertirse en cero por
conveniencia.

## Decisiones aún abiertas

- métrica de distancia y tratamiento de la geodesia;
- radio y ventana finales después de la sensibilidad;
- conectividad y control del encadenamiento;
- tratamiento de filas exactas duplicadas y coincidencias multi-sensor;
- mínimo de detecciones o duración, si alguno, y justificación;
- regla de asociación con la cicatriz y la ventana Sentinel-2;
- umbrales de área y dNBR para `significant_burn`;
- partición temporal/espacial y baseline FRP-only a nivel de evento.

Hasta cerrar estas decisiones, el repositorio debe permanecer en una etapa de
propuestas algorítmicas y perfil descriptivo. La corrida de sensibilidad no
autoriza a tratar un componente como incendio confirmado ni a avanzar a
Sentinel-2, dNBR o modelado.

## Especificación implementada en esta fase

### Entrada, normalización y grafo

- El script `scripts/run_clustering_experiment.py` acepta un CSV local, un
  directorio de outputs y una frontera GeoJSON opcional. No hace solicitudes
  de red y rechaza timestamps fuera de `2025-01-01..2025-04-30`.
- Las columnas mínimas para formar el grafo son `detection_id`, `latitude`,
  `longitude` y `acq_datetime_utc`. Se validan rangos WGS84, IDs únicos y
  timestamps con zona horaria; los timestamps se normalizan a UTC canónico.
- La proyección es EPSG:32617 (WGS84/UTM zona 17N), implementada con la serie
  UTM de la biblioteca estándar. La distancia de arista es euclidiana en
  metros proyectados; no se usan distancias en grados.
- Para cada configuración hay un nodo por detección. Se crea una arista si y
  solo si se cumplen simultáneamente `distancia <= radio` y `abs(tiempo UTC) <=
  ventana`. Los umbrales son inclusivos, la conectividad es por componentes
  conexas y los singletons se conservan.
- Fuente, satélite, instrumento, FRP, confianza y día/noche no crean aristas.
  Se conservan como atributos para auditar coincidencias multi-sensor y
  faltantes. Cada `event_id` incluye la configuración y un hash estable de sus
  IDs de detección ordenados.

### Estadísticas y diagnósticos

Cada componente registra inicio/fin, duración, conteo, fuentes, satélites,
centro descriptivo, bounding box, extensión espacial, salto temporal máximo,
FRP descriptivo, confianza, fracciones día/noche y cobertura de días. La
bandera `possible_chain_merge` no separa el grafo. Sus razones se generan con
reglas explícitas:

- duración mayor que 72 h o mayor que 168 h;
- extensión mayor que tres veces el radio;
- salto consecutivo mayor o igual que 0.8 veces la ventana;
- componente con al menos 25 % de las detecciones;
- componente multi-día;
- extensión excepcional frente a la mediana de la configuración.

Se marca `mega_cluster_detected` si algún componente contiene al menos 50 %
de las detecciones, dura más de 168 h o supera diez veces el radio. Es una
alarma descriptiva, no un criterio de eliminación ni de partición.

### Estabilidad y artefactos

La estabilidad compara las 24 parejas vecinas de la grilla. Para cada pareja
se reportan cambio de conteo, singleton rate, mayor componente, retención
direccional de pares coasignados y Jaccard de pares coasignados. La retención
no es una exactitud contra una verdad de campo.

Cada configuración escribe `events.csv`, `membership.csv` y `summary.json`.
El directorio raíz escribe `sensitivity_summary.csv/.json/.md`,
`stability.csv/.md`, `extreme_events_review.csv/.md` y
`provisional_selection.md`. Los outputs y figuras se ignoran por Git; el CSV
de entrada, raw y processed no se modifican.

### Resultado observado sin selección final

En la corrida local sobre 1 185 detecciones, las 16 configuraciones conservaron
las 1 185 membresías y ninguna marcó `mega_cluster_detected`. El reporte
provisional dejó `r1500_t06`, `r3000_t06` y `r1500_t12` como candidatos para
revisión, con Jaccard medio de vecinos aproximado de 0.889, 0.877 y 0.873,
respectivamente. Esta clasificación es una ayuda de inspección; no fija un
radio, una ventana ni una etiqueta `significant_burn`.

## Decisión provisional congelada — `r1500_t06`

La revisión de la matriz aprobó provisionalmente `r1500_t06` como configuración
de trabajo para la siguiente fase: radio espacial `1500 m`, ventana temporal
UTC `6 h`, componentes conexas espacio-temporales y CRS de cálculo `EPSG:32617`.
La palabra provisional es importante: la configuración se eligió por
estabilidad y riesgos diagnósticos de esta cohorte, pero todavía no está
validada contra cicatrices Sentinel-2/dNBR.

Las métricas que sustentan la decisión son:

- estabilidad media vecina aproximada `0.8894`;
- `611` eventos provisionales formados a partir de `1 185` detecciones;
- `344` singletons (`56.30%`) y `267` eventos multi-detección;
- `17` eventos marcados `possible_chain_merge` (`2.78%`);
- ningún `mega_cluster_detected` bajo los diagnósticos definidos.

Se descartó provisionalmente `r3000_t06` porque el radio mayor eleva el riesgo
de fusionar actividad espacialmente distinta: produjo `561` eventos y `48`
posibles encadenamientos (`8.56%`), además de una estabilidad media vecina
menor aproximada (`0.8774`). Se descartó provisionalmente `r1500_t12` porque
la ventana de 12 horas aumenta el riesgo de unir sobrevuelos separados:
produjo `601` eventos y `23` posibles encadenamientos (`3.83%`), con
estabilidad aproximada `0.8734`. No son descartes universales; son decisiones
para esta cohorte y podrán cambiar al observar resultados ópticos.

`611` no significa `611` incendios confirmados. Un `event_id` es un componente
provisional de la regla congelada. Los singletons se conservan para que una
sola detección no sea descartada por definición. Fuente, satélite,
instrumento, FRP, confianza y día/noche son atributos de auditoría: FRP y
confianza no participaron en la formación de aristas ni en la conectividad.

### Tablas congeladas y siguiente límite

Las tablas finales provisionales se generan desde los outputs ya existentes en
`outputs/clustering/r1500_t06/` mediante
`scripts/freeze_provisional_clustering.py`. El script valida que se preserven
1 185 `detection_id`, que cada uno aparezca una sola vez, que haya 611
`event_id`, que los IDs coincidan con la corrida y que no entren fechas de
2026. No ejecuta `cluster_detections` de nuevo.

El siguiente paso es el diseño de observabilidad descrito en
`docs/SENTINEL2_OBSERVABILITY_DESIGN.md`. En esta etapa no se consulta
Sentinel-2, no se fija un buffer o ventana única, no se calcula NBR/dNBR y no
se produce `significant_burn`. La definición del evento, el buffer, la ventana
y la asociación óptica podrán revisarse con un protocolo reproducible después
de revisar cicatrices y casos ambiguos.
