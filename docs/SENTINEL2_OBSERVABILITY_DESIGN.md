# Diseño de observabilidad Sentinel-2

Estado: contrato e interfaz de consulta implementados para el piloto; la
consulta real queda pendiente de un `EARTH_ENGINE_PROJECT` disponible. No
descarga escenas, no calcula NBR o dNBR y no asigna etiquetas de quema.

## Propósito y unidad de análisis

La unidad de análisis será un evento provisional `r1500_t06`, no una detección
FIRMS aislada y tampoco un incendio confirmado. El universo congelado contiene
611 eventos que agrupan 1.185 detecciones. Los singletons se mantienen en el
universo porque pueden representar un evento real observado una sola vez o una
limitación de observación; no se convierten en negativos.

El objetivo inmediato es medir si cada evento tiene una observación óptica
pre/post técnicamente utilizable. La observabilidad no equivale a una cicatriz
de quema ni a `significant_burn`.

## Área de interés (AOI)

### Método candidato

Para cada evento se usarán todas sus detecciones de la tabla de membresía. En
EPSG:32617 se transformarán sus coordenadas, se generará un buffer alrededor
de cada punto y se calculará la unión geométrica. El AOI se guardará después en
el CRS de consulta requerido por la fuente, junto con el método y el buffer
usado. No se usará solamente el centroide: eso perdería la dispersión espacial
interna del evento.

El método inicial candidato será `detection_union_buffer`. Antes de consultar
imágenes se compararán tres radios:

| Candidato | Uso en la sensibilidad |
|---:|---|
| 150 m | AOI compacto, sensible a cicatrices pequeñas |
| 300 m | punto intermedio |
| 750 m | AOI amplio, útil para eventos con dispersión mayor |

Estos radios son candidatos de diseño, no una decisión científica ni una
extensión de la regla de clustering. No se seleccionará un radio por mirar una
cicatriz.

### Control de tamaño

Para cada candidato se registrarán área, ancho, alto, número de detecciones
incluidas y proporción de solapamiento con los AOI de otros eventos. Se
rechazará solamente una geometría inválida, vacía o imposible de transformar;
un AOI grande o pequeño se conservará como diagnóstico y se comparará en la
sensibilidad. La elección provisional deberá balancear:

- suficiente margen espacial alrededor de las detecciones;
- no incorporar un área desproporcionada respecto del evento;
- cobertura óptica suficiente para evaluar el AOI;
- bajo solapamiento ambiguo con otro evento.

Si la distribución de áreas muestra casos extremos, se documentarán antes de
seleccionar el candidato operativo. No se impondrá retrospectivamente un
umbral derivado de qué eventos parecen quemados.

## Ventanas temporales candidatas

Las fechas se calcularán en UTC a partir del inicio y el final del evento. Para
evitar que la escena pre esté contaminada por el evento, y para permitir un
retraso de adquisición post, se propone comparar tres paquetes antes de fijar
una ventana:

| Paquete | Ventana pre | Ventana post |
|---|---|---|
| A, corta | `start - 30 d` a `start - 1 d` | `end + 1 d` a `end + 30 d` |
| B, balanceada | `start - 60 d` a `start - 5 d` | `end + 5 d` a `end + 65 d` |
| C, amplia | `start - 90 d` a `start - 10 d` | `end + 10 d` a `end + 100 d` |

Son ventanas candidatas para una sensibilidad pequeña. No se elegirá la que
produzca más cicatrices aparentes. La comparación debe usar primero métricas
de observabilidad definidas antes de ver resultados de quema: número de
escenas, fracción de nubes, cobertura del AOI y atrición. La ventana de trabajo
se registrará en `pre_window_*` y `post_window_*` para cada evento.

Un evento cuya fecha quede fuera del periodo disponible de la colección no se
tratará como ausencia de quema. Se registrará la causa de atrición como falta
de escena o ventana fuera de cobertura temporal, según corresponda.

## Colecciones y evaluación de escenas

La colección prevista es **Sentinel-2 Surface Reflectance Harmonized**
`COPERNICUS/S2_SR_HARMONIZED`, descrita en `SOURCES.md`. Para apoyar la
evaluación de nubes se prevé asociar `COPERNICUS/S2_CLOUD_PROBABILITY` y
contrastar la información de clasificación disponible en la colección. Esto
requiere autenticación y un proyecto de Earth Engine; no se configura ni se
consulta en esta fase.

Para cada escena candidata se calcularán, en una futura etapa y solamente
dentro del AOI:

1. fracción de píxeles con probabilidad de nube por encima del umbral elegido;
2. fracción de AOI con píxeles válidos y observados;
3. presencia de sombras, nubes o píxeles no utilizables según la información
   de calidad disponible;
4. identificador de escena, fecha de adquisición y motivo de descarte.

Los umbrales se probarán como sensibilidad predefinida, por ejemplo
probabilidad de nube `{0.10, 0.20, 0.40}` y cobertura mínima del AOI
`{0.70, 0.85, 0.95}`. No hay un umbral final fijado. Una escena puede existir y
seguir siendo no utilizable para el AOI por nubosidad o cobertura parcial.

Una escena pre utilizable deberá estar dentro de la ventana pre, intersectar
el AOI, superar el criterio de cobertura y quedar bajo el criterio de nubes
para el candidato evaluado. La escena post utilizable deberá cumplir los
mismos requisitos dentro de la ventana post. Si hay varias, la regla futura se
declarará antes de revisar cicatrices; una opción reproducible es seleccionar
la escena utilizable temporalmente más cercana al inicio o final del evento,
con desempate por identificador de escena. También puede evaluarse una
composición, pero no se mezclará con la regla de escena única sin registrarlo.

La tabla futura conservará conteos de escenas candidatas y utilizables,
identificadores seleccionados, fracciones de nube y fracciones de cobertura.
La ausencia de escenas, una escena presente pero no utilizable y una cobertura
parcial son estados distintos; nunca se codificarán todos como cero.

## Eventos cercanos y solapamientos

Los eventos provisionales no se volverán a fusionar durante la etapa óptica.
Dos AOI pueden solaparse y un periodo post de un evento puede coincidir con el
periodo pre de otro. Se hará lo siguiente:

- conservar ambos `event_id` y calcular observabilidad por evento;
- registrar solapamiento espacial y temporal en una extensión futura del
  esquema o en un archivo de auditoría;
- marcar `spatial_overlap_ambiguous` o `temporal_overlap_ambiguous` cuando el
  solapamiento impida atribuir una futura señal a un solo evento;
- no usar una inspección visual para decidir cuál evento merece conservarse;
- comparar, si hace falta, el resultado con el paquete temporal alternativo
  más corto o con un AOI candidato más compacto.

La proximidad no es por sí misma evidencia de que dos eventos sean el mismo
incendio. La decisión de clustering queda congelada provisionalmente y podrá
revisarse después de observar casos ambiguos, pero no se modificará durante la
consulta de escenas como reacción a una imagen concreta.

## Cohorte y prevención de selección retrospectiva

La muestra piloto de 30 eventos se seleccionó antes de consultar Sentinel-2
con semilla `20260715`, usando únicamente estructura del evento: singleton o
multi-detección, cuartil de `detection_count` entre multi-detecciones, mes,
fuente única/múltiple y `possible_chain_merge`. Las cuotas marginales logradas
se registran en el reporte de muestreo. FRP, confianza, tamaño aparente y
conveniencia visual no participan en la selección.

El orden operativo será:

1. congelar el universo y la semilla;
2. construir los AOI candidatos con las coordenadas de las detecciones;
3. declarar paquetes de ventanas y umbrales de calidad;
4. consultar metadatos y píxeles de Sentinel-2;
5. registrar escenas, nubes, cobertura y atrición;
6. cerrar la cohorte observable y sus limitaciones;
7. solamente después, diseñar y validar la medición espectral y las etiquetas.

No se hará inspección manual previa para reemplazar eventos poco convenientes
ni para escoger escenas que hagan más clara una cicatriz.

## Flujo de atrición

```text
611 eventos r1500_t06
        |
        v
30 eventos del piloto estructural
        |
        v
AOI válido por método y buffer candidato
        |
        v
escenas candidatas pre/post dentro de cada paquete temporal
        |
        v
escenas con calidad y cobertura evaluadas
        |
        +--> no hay escena pre/post
        +--> hay escena pero no es utilizable
        +--> cobertura parcial o solapamiento ambiguo
        |
        v
estado de observabilidad registrado, sin convertir atrición en negativo
        |
        v
fase posterior: NBR/dNBR y definición de etiqueta, aún fuera de esta fase
```

Los conteos de cada flecha deberán poder reconstruirse desde los CSV y el
reporte de ejecución. En particular, `no_pre_scene`, `no_post_scene`,
`no_usable_pre_scene` y `no_usable_post_scene` no significan `no_burn`.

## Vocabularios controlados

`observability_status` usará inicialmente:

- `not_assessed`
- `no_pre_scene`
- `no_post_scene`
- `no_usable_pre_scene`
- `no_usable_post_scene`
- `usable_both`
- `partial_coverage`
- `ambiguous`
- `excluded`

`exclusion_reason` usará inicialmente:

- `not_applicable`
- `no_pre_scene`
- `no_post_scene`
- `no_usable_pre_scene`
- `no_usable_post_scene`
- `cloud_score_unavailable`
- `coverage_below_threshold`
- `clear_fraction_below_threshold`
- `no_valid_b8_b12_pixels`
- `partial_coverage`
- `invalid_aoi`
- `spatial_overlap_ambiguous`
- `temporal_overlap_ambiguous`
- `query_error`
- `other`

El archivo vacío `data/interim/sentinel2_observability.csv` contiene el
encabezado de este contrato y ninguna observación ficticia.

## Riesgos de sesgo

- **Nubosidad no aleatoria:** la atrición puede concentrarse en temporada,
  región o tipo de evento; la cohorte observable no representa automáticamente
  los 611 eventos.
- **Confusión temporal:** agricultura, quemas previas, lluvia o regeneración
  pueden cambiar la reflectancia dentro de una ventana.
- **Resolución y mezcla:** una cicatriz pequeña puede quedar por debajo de la
  escala efectiva o mezclada con vegetación, suelo y agua.
- **Solapamiento de eventos:** la misma zona puede contribuir a más de un AOI o
  a ventanas pre/post de eventos cercanos.
- **Sesgo de disponibilidad:** elegir la escena más cercana puede favorecer
  fechas o trayectorias con mejor cobertura.
- **Dependencia de parámetros:** buffer, ventana, umbral de nube, cobertura y
  criterio espectral pueden cambiar la cohorte y el resultado.

Estos riesgos se reportarán junto con la atrición y no se ocultarán con una
eliminación silenciosa de casos difíciles.

## Límites de dNBR como ground truth

dNBR será, como máximo, una medida remota y dependiente de la definición de
pre/post; no es una observación directa del perímetro, de la causa, de la
duración ni de la severidad operativa de un incendio. Puede responder a cambios
de vegetación no causados por fuego, diferencias fenológicas, humedad,
atmósfera, sombras, nubes, geometría, regeneración o selección de escenas.
Los umbrales de área y dNBR también pueden producir etiquetas sensibles a la
resolución y a la escala del AOI.

Por ello, una futura etiqueta deberá separar al menos evidencia utilizable,
ausencia de evidencia y señal de cambio compatible con quema. Un evento sin
escena adecuada no se convertirá en un negativo. La definición de
`significant_burn`, NBR, dNBR y cualquier baseline predictivo queda fuera de
este diseño y requerirá una decisión metodológica posterior.

## Contrato implementado para el piloto

Esta sección fija el contrato operativo de la primera consulta; sustituye los
radios y paquetes de ventanas candidatos anteriores para esta ejecución, pero
no los convierte en parámetros científicamente validados. La unidad sigue
siendo cada evento provisional `r1500_t06` y la cohorte se selecciona antes de
consultar escenas.

### AOI y sensibilidad espacial

Para cada evento se genera `detection_union_buffer`: cada detección miembro se
transforma a `EPSG:32617`, se le aplica un buffer y se unen los buffers. La
geometría de consulta se transforma a `EPSG:4326`. Se evalúan conjuntamente
`b0500` (500 m), `b1000` (1.000 m) y `b1500` (1.500 m). El área, el hash de
geometría, la validez y el número de detecciones miembro se registran para
detectar AOI extremos sin excluirlos retrospectivamente.

### Ventanas y escenas

Se consulta `COPERNICUS/S2_SR_HARMONIZED` enlazado mediante `system:index` con
`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`. Los paquetes son:

| Identificador | Ventana pre | Ventana post |
|---|---|---|
| `pre30_post45` | inicio -30 a inicio -5 días | final +5 a final +45 días |
| `pre30_post90` | inicio -30 a inicio -5 días | final +5 a final +90 días |
| `pre60_post45` | inicio -60 a inicio -5 días | final +5 a final +45 días |
| `pre60_post90` | inicio -60 a inicio -5 días | final +5 a final +90 días |

Los extremos se calculan en UTC. La fecha final de una consulta se hace
exclusiva de forma reproducible; no se incluyen datos posteriores al periodo
2025 del piloto ni fechas de 2026. Se conservan todas las escenas devueltas,
incluidas las que no resulten utilizables.

### Calidad server-side

La cobertura válida requiere simultáneamente la máscara de B8 y B12, agregada
a escala de 20 m dentro del AOI. `CLOUDY_PIXEL_PERCENTAGE` se conserva como
metadato, pero no decide la claridad. El criterio principal usa `cs_cdf`; `cs`
se registra como diagnóstico. Se guardan cobertura total, píxeles válidos,
fracciones claras en `0.50`, `0.60` y `0.65`, y ausencia o disponibilidad de
Cloud Score+.

Las reglas predeclaradas son:

| Regla | Cobertura mínima | Fracción clara | Umbral `cs_cdf` |
|---|---:|---:|---:|
| A | 0.90 | 0.70 | 0.50 |
| B | 0.90 | 0.70 | 0.60 |
| C | 0.90 | 0.70 | 0.65 |
| D | 0.95 | 0.80 | 0.60 |

Las cuatro reglas son sensibilidad de observabilidad, no etiquetas de quema ni
ground truth. Para cada combinación se prioriza una escena utilizable por
cobertura, claridad, cercanía temporal al evento y finalmente ID estable; el
inventario no elimina candidatas.

### Ejecución, caché y atrición

El script construye una consulta server-side combinada por evento para los tres
AOI y cuatro pares de ventanas, en lugar de solicitar un `getInfo` por píxel o
por métrica. La ejecución es secuencial (`concurrency=1`), con reintentos,
backoff, caché por firma de contrato y checkpoint. `--resume` reutiliza una
caché compatible; `--overwrite` exige confirmación explícita.

Se generan inventario de escenas, inventario AOI, observabilidad por
combinación/regla, errores, atrición, sensibilidad y figuras descriptivas. Los
estados controlados son `not_assessed`, `no_pre_scene`, `no_post_scene`,
`no_usable_pre_scene`, `no_usable_post_scene`, `usable_both`,
`partial_coverage`, `ambiguous` y `excluded`. Las razones incluyen ausencia de
escena, cobertura o claridad insuficiente, Cloud Score+ no disponible, AOI
inválido, solapamiento ambiguo y error de consulta. Ninguna razón de atrición
se interpreta como ausencia de quema.

No se descargan rasters, no se inspeccionan visualmente las cicatrices y no se
calculan bandas derivadas, NBR, dNBR, severidad o etiquetas. La interfaz exige
`EARTH_ENGINE_PROJECT` desde el entorno; nunca escribe el ID, tokens o
credenciales en archivos de salida.
