# FirePA — registro de fuentes

Fecha de verificación documental: 2026-07-19.

Este registro distingue fuentes planeadas, datos efectivamente descargados y
artefactos públicos derivados. Las URLs se documentan para que una adquisición
futura sea reproducible y auditable; no son por sí mismas una autorización para
redistribuir los materiales de cada proveedor.

## Alcance de publicación y límites de licencia

Este archivo distingue la procedencia científica de los artefactos que el
repositorio expone públicamente. La presencia de un archivo en Git no convierte
sus fuentes externas en material relicenciado por FirePA.

### 1. Software autoría FirePA

El código fuente escrito para este repositorio —incluidos `src/`, `scripts/`,
`tests/` y el frontend en `site/`— se ofrece bajo la licencia indicada en
[`LICENSE`](LICENSE), sujeto a las exclusiones de [`NOTICE.md`](NOTICE.md).
Las dependencias conservan sus propias licencias.

### 2. Artefactos analíticos derivados públicos

`site-data/` es un paquete público derivado de artefactos congelados del piloto.
Incluye 611 unidades analíticas de eventos térmicos provisionales, dos anclas
de referencia externa, metodología, procedencia, manifiestos y seis figuras
congeladas. No incluye filas raw FIRMS, claves, joins privados, asignaciones de
revisión humana, SQLite, escenas Sentinel-2 ni resultados locales de Earth
Engine. Un evento provisional no equivale automáticamente a un incendio
confirmado, perímetro de quema, ground truth, severidad o alerta.

### 3. Datos científicos y referencias externas

NASA FIRMS, Sentinel-2/Copernicus, ERA5-Land, ESA WorldCover, Copernicus DEM,
el límite administrativo de Coclé y las referencias externas conservan las
condiciones de sus proveedores o fuentes. Las secciones siguientes registran
esas condiciones sin inventar una licencia común para todos los materiales.
Cuando una condición de redistribución no está resuelta, se declara y el input
permanece fuera de Git.

### 4. Inputs locales excluidos

Las descargas raw, outputs de investigación, la fuente boundary local de Coclé,
cachés, paquetes de revisión y credenciales permanecen excluidos mediante
`.gitignore`. El frontend público usa un derivado de presentación versionado;
la ausencia del boundary local no debe impedir construir ese frontend.

### 5. Activos visuales decorativos

`site/public/assets/mineral-field.png` es una superficie visual suministrada
para el proyecto con carácter authored/generative. Es
decorativa, no es evidencia científica, no es terreno medido, no es imagery de
satélite y no es una capa geográfica. Su procedencia está documentada en
[`docs/ASSET_PROVENANCE.md`](docs/ASSET_PROVENANCE.md). La licencia MIT del
software no se extiende automáticamente a este activo ni a los materiales
científicos externos.

## 1. NASA FIRMS — detecciones térmicas

- **Proveedor:** NASA FIRMS / LANCE.
- **Fuente oficial:** [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/).
- **Disponibilidad oficial:** [Data Availability API](https://firms.modaps.eosdis.nasa.gov/api/data_availability/).
- **Documentación de uso:** [FIRMS API tutorial](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- **Papel:** fuente de detecciones candidatas para la cohorte 2025 de Coclé.
- **Fuentes VIIRS candidatas:** `VIIRS_SNPP_SP`, `VIIRS_NOAA20_SP` y
  `VIIRS_NOAA21_SP`, siempre que la respuesta de disponibilidad confirme que
  cubren el intervalo solicitado. El pipeline no supone disponibilidad por el
  nombre: consulta primero `data_availability` y selecciona las fuentes
  `VIIRS_*_SP` con solapamiento. Las fuentes `*_NRT` no se seleccionan por
  defecto para este análisis histórico.
- **Campos esperados:** `latitude`, `longitude`, `acq_date`, `acq_time`,
  `satellite`, `instrument`, `confidence` y `frp`; también se conservan, si
  están presentes, `daynight`, `version` y `type`.
- **Acceso:** la API requiere `FIRMS_MAP_KEY`. La clave solo puede llegar por
  `FIRMS_MAP_KEY` o `--map-key`; nunca se escribe en código, logs o manifests.
- **Contrato temporal:** el Area API se consulta en fragmentos inclusivos de
  como máximo cinco días. Cada fuente y fragmento tiene su propio raw y
  manifest.
- **Producto y limitaciones:** FIRMS es una detección de anomalía térmica, no
  una etiqueta de incendio independiente ni una cicatriz de quema. Diferentes
  filas pueden pertenecer al mismo evento. La respuesta de disponibilidad y la
  fuente concreta deben conservarse para interpretar cobertura.
- **Estado en este checkout:** la snapshot de disponibilidad y la adquisición
  histórica local de 2025 ya fueron auditadas sin red: 48 fragmentos y 48
  manifests para `VIIRS_NOAA20_SP` y `VIIRS_SNPP_SP`, con raw inmutable y
  cohorte procesada reproducible. Una nueva descarga todavía requiere
  `FIRMS_MAP_KEY`; un CSV local real sigue siendo una vía alternativa.

## 2. Sentinel-2 Surface Reflectance Harmonized

- **Proveedor:** Copernicus / ESA; catálogo de Google Earth Engine.
- **Fuente oficial:** [COPERNICUS/S2_SR_HARMONIZED](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED?hl=en).
- **Papel previsto:** observación posterior para construir la evidencia de
  cicatriz, NBR y dNBR después de que se definan eventos.
- **Cobertura documentada:** el catálogo indica disponibilidad desde 2017-03-28
  y revisita nominal de cinco días; la disponibilidad efectiva depende de la
  ubicación, adquisición y nubes.
- **Variables relevantes:** bandas de reflectancia que incluyen NIR y SWIR,
  además de la clasificación de escena (`SCL`). La resolución de banda no es
  uniforme; el catálogo documenta B8 a 10 m y B12 a 20 m.
- **Acceso/condiciones:** requiere autenticación y un proyecto de Earth Engine;
  aplican los términos de datos de Copernicus Sentinel.
- **Estado:** no utilizado en esta fase; no se descargan imágenes ni se calcula
  NBR/dNBR.

## 3. Probabilidad de nubes Sentinel-2

- **Proveedor:** Copernicus / ESA / Sentinel Hub; catálogo de Google Earth
  Engine.
- **Fuente oficial:** [COPERNICUS/S2_CLOUD_PROBABILITY](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_CLOUD_PROBABILITY?hl=en).
- **Papel previsto:** apoyo a la regla de observabilidad y al descarte o
  marcado de composiciones Sentinel-2 no utilizables.
- **Variable documentada:** probabilidad por píxel de 0 a 100 (`UINT8`),
  producida por un modelo s2cloudless/LightGBM según el catálogo.
- **Acceso/condiciones:** requiere Earth Engine autenticado; no se fija aún un
  umbral de nube.
- **Estado:** no utilizado en esta fase.

## 4. ERA5-Land hourly

- **Proveedor:** ECMWF / Copernicus Climate Change Service; catálogo de Earth
  Engine.
- **Fuente oficial:** [ECMWF/ERA5_LAND/HOURLY](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY?hl=en).
- **Papel previsto:** variables meteorológicas de contexto alrededor de un
  evento ya definido.
- **Variables candidatas documentadas:** temperatura y punto de rocío a 2 m,
  componentes del viento a 10 m, precipitación total horaria y presión de
  superficie.
- **Resolución y tiempo:** el catálogo describe datos horarios y una escala de
  aproximadamente 11.1 km; no es una medición puntual de cada parcela.
- **Acceso/condiciones:** la extracción concreta dependerá de Earth Engine o
  del mecanismo elegido del Climate Data Store y sus condiciones de licencia y
  atribución.
- **Limitaciones:** se debe revisar el aviso del catálogo sobre las bandas de
  evaporación antes de usar cualquiera de ellas.
- **Estado:** no utilizado en esta fase; no se extraen variables.

## 5. ESA WorldCover

- **Proveedor:** ESA WorldCover Consortium; catálogo de Earth Engine.
- **Fuente oficial:** [ESA/WorldCover/v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200?hl=en).
- **Papel previsto:** covariable de vegetación/cobertura del suelo para un
  evento, solo después de definir cómo se extraerá y con qué fecha se alineará.
- **Resolución y tiempo:** clasificación global a 10 m; la versión v200
  documentada corresponde a 2021 y contiene 11 clases.
- **Licencia:** el catálogo identifica CC-BY-4.0; cualquier producto derivado
  debe mantener la atribución correspondiente.
- **Limitación:** una clasificación de 2021 puede no representar el uso del
  suelo el día de una detección posterior.
- **Estado:** no utilizado en esta fase.

## 6. Copernicus DEM GLO-30

- **Proveedor:** Copernicus; catálogo de Earth Engine.
- **Fuente oficial:** [COPERNICUS/DEM/GLO30](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30?hl=en).
- **Papel previsto:** elevación y derivados topográficos definidos antes del
  modelado.
- **Resolución y referencia:** DSM global de 30 m; el catálogo documenta el
  datum vertical EGM2008 y restricciones de disponibilidad para determinados
  territorios.
- **Condiciones:** usar la licencia mundial gratuita y sus excepciones según la
  documentación del producto; conservar la atribución.
- **Estado:** no utilizado en esta fase.

## 7. Límite administrativo de Coclé

- **Fuente preferida:** Instituto Geográfico Nacional Tommy Guardia / ANATI.
- **Página oficial:** [División político-administrativa de Panamá](https://ignpanama.anati.gob.pa/index.php/divisionpolitica-administrativa).
- **Registro oficial incorporado localmente:** conjunto de datos de límites
  político-administrativos de la República de Panamá, escala 1:25 000, año 2025
  (provincia), capa `limi_prov_a`, obtenido y descomprimido localmente desde la
  fuente oficial. El XML declara 20 registros tipo polígono, de los cuales 7
  son masas de agua y 13 son de uso tierra; el extractor conserva la capa y
  selecciona por el campo `nomb_prov`.
- **CRS y encoding verificados:** el `.prj` declara `WGS_1984_UTM_Zone_17N`,
  equivalente a `EPSG:32617`; el `.cpg` declara UTF-8. La geometría seleccionada
  se reproyecta explícitamente a `EPSG:4326` en
  `data/reference/cocle.geojson`.
- **Selección y validación local:** el registro activo con valor exacto
  normalizado `Coclé` es uno, con geometría `Polygon` multipart de cinco partes
  que se serializa como `MultiPolygon`. La validación no aplicó reparaciones,
  simplificación ni disolución; el reporte y la figura se generan con
  `python scripts/prepare_cocle_boundary.py`.
- **Licencia y limitación:** el XML de metadatos declara `CC BY-NC-SA` y una
  advertencia de uso como referencia/representación cartográfica. Por esa
  restricción, el SHP original y el GeoJSON generado se mantienen fuera de Git;
  se registran rutas y hashes en `outputs/cocle_boundary_validation.json`.
- **Contrato local:** el importador exige GeoJSON `Feature`, `FeatureCollection`,
  `Polygon` o `MultiPolygon`, un CRS explícito o `--boundary-crs`, anillos
  cerrados sin auto-cruces y coordenadas transformables a `EPSG:4326`. Filtra
  por punto dentro del polígono; el bbox solo reduce la consulta FIRMS.
- **Fallback reconocido documentado, no seleccionado:** [geoBoundaries API](https://www.geoboundaries.org/api.html)
  ofrece límites abiertos y una capa ADM1 para Panamá bajo CC-BY 4.0. Si se
  utiliza, debe registrarse el archivo, versión y licencia en el manifest o
  documentación de la corrida; no se mezcla silenciosamente con el límite
  oficial.
- **Estado:** la extracción y validación local están implementadas y pasan el
  smoke test de punto interior, punto exterior y punto en el borde. La
  geometría permanece como artefacto local ignorado por Git; no se afirma que
  sea un resultado científico ni una verdad de incendio.

## 8. Accesos que no son dependencias

No se requiere información privada de Bomberos, MiAmbiente, SINAPROC ni de
terceros para construir la etiqueta propuesta. El contacto institucional puede
ser útil para contexto, pero no es un prerrequisito técnico ni una fuente de
ground truth de esta fase.

## 9. Cloud Score+ para observabilidad Sentinel-2

- **Catálogo oficial:** [GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED?hl=en).
- **Papel en esta fase:** evaluar claridad por píxel de escenas SR enlazadas por
  `system:index`; no es una etiqueta de quema.
- **Bandas utilizadas:** `cs` como diagnóstico y `cs_cdf` como criterio primario
  de claridad. El pipeline conserva ambas estadísticas y evalúa los umbrales
  `0.50`, `0.60` y `0.65`.
- **Propiedades registradas:** `MODEL_VERSION` y `NO_CONTEXT_FRACTION`, cuando
  están disponibles en la imagen enlazada. La ausencia se registra y no se
  convierte silenciosamente en una escena limpia.
- **Estado:** la interfaz Earth Engine está implementada de forma segura, pero
  una corrida real requiere `EARTH_ENGINE_PROJECT` en el entorno local. No se
  descargan rasters ni se calcula NBR/dNBR en esta fase.
