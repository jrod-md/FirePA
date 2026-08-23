# FirePA sources and provenance register

This register distinguishes scientific inputs, public derived artifacts,
external narrative references, and sources considered but not used. A URL is a
provenance record, not a transfer of licensing rights or a scientific truth
label.

The machine-readable external-source registry is
`references/external_reference_sources_v1.json` (seven documents, two
incidents). Its frozen SHA-256 is
`6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49`.

## Sources used in the frozen pilot

### NASA FIRMS / LANCE

- Official service: <https://firms.modaps.eosdis.nasa.gov/api/area/>
- Availability service: <https://firms.modaps.eosdis.nasa.gov/api/data_availability/>
- API documentation: <https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html>
- Role: VIIRS thermal-anomaly detections for the 2025 Coclé cohort.
- Frozen result: 1,532 audited raw detections and 1,185 processed detections.
- Boundary: a FIRMS detection is not a confirmed independent wildfire.

Historical downloads require a local `FIRMS_MAP_KEY`. No key, raw FIRMS row,
or request URL containing credentials is published.

### Sentinel-2 Surface Reflectance Harmonized

- Catalog: <https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED>
- Role: descriptive optical follow-up for the frozen 30-event cohort.
- Frozen result: 28 observable cases and two `unobserved` cases.
- Bands used by the NBR/dNBR contract: B8 and B12, evaluated at 20 m support.
- Boundary: imagery and indices are descriptive evidence; no severity class,
  target, or ground-truth label was created.

### Cloud Score+

- Catalog: <https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED>
- Role: optical clarity assessment for linked Sentinel-2 scenes.
- Boundary: clarity scores are not evidence of fire or burn severity.

### Administrative boundary of Coclé

- Preferred source: Instituto Geografico Nacional Tommy Guardia / ANATI.
- Source page: <https://ignpanama.anati.gob.pa/index.php/divisionpolitica-administrativa>
- Local source metadata: Panama administrative boundary, province layer
  `limi_prov_a`, 2025, scale 1:25,000, `EPSG:32617`, UTF-8.
- Use: select the Coclé geometry, transform it to `EPSG:4326`, and spatially
  filter detections.
- Redistribution boundary: the source metadata declares `CC BY-NC-SA`; the
  original shapefile and generated local `data/reference/cocle.geojson` remain
  outside Git. The website uses a tracked deterministic presentation derivative.

The presentation derivative is contextual geometry, not a scientific output,
burn perimeter, or synthetic geography.

## External incident references

The source registry preserves claims separately and does not adjudicate a
single true area or cause. Matching coordinates are approximate anchors
provided by the researcher and are not claimed to come from the articles.

| ID | Publisher | Date | Incident | URL |
|---|---|---|---|---|
| `SOURCE-001` | TVN Noticias | 2025-01-17 | Cerro Los Picachos | <https://www.tvn-2.com/nacionales/incendio-picachos-ola-afecto-extensa-area-investigan-causas_1_2173253.html> |
| `SOURCE-002` | TVN Noticias | 2025-01-26 | Cerro Guacamaya | <https://www.tvn-2.com/nacionales/provincias/cerro-guacamaya-mil-hectareas-afectadas-incendio-reserva-hidrica_1_2174469.html> |
| `SOURCE-003` | TVN Noticias | 2025-01-27 | Cerro Guacamaya | <https://www.tvn-2.com/nacionales/siguen-trabajos-controlar-incendio-cerro_1_2174481.html> |
| `SOURCE-004` | EcoTV Panama | 2025-01-27 | Cerro Guacamaya | <https://www.ecotvpanama.com/nacionales/autoridades-extinguen-incendio-cerro-guacamaya-penonome-n6026325> |
| `SOURCE-005` | Telemetro Noticias | 2025-01-27 | Cerro Guacamaya | <https://www.telemetro.com/nacionales/noticias/2025/01/27/incendio-cerro-guacamaya-3000.html> |
| `SOURCE-006` | Benemerito Cuerpo de Bomberos de la Republica de Panama | 2025-01-28 | Cerro Guacamaya | <https://www.bomberos.gob.pa/2025/01/28/incendios-en-cerro-guacamaya-y-tubuala-control-prevencion-y-nuevas-alianzas-internacionales/> |
| `SOURCE-007` | Ministerio de Ambiente de Panama | 2025-02-07 | Cerro Guacamaya | <https://miambiente.gob.pa/avanzan-investigaciones-sobre-incendio-en-la-reserva-hidrica-cerro-guacamaya-y-reiteran-recompensa-para-encontrar-a-los-responsables/> |

The manual search located six records published in January and one in
February 2025; none qualifying were located for March or April. The search was
not exhaustive. Absence of a located article is not absence of fire, activity,
or thermal signal.

External references are relational evidence only. Their URLs are not pipeline
inputs, are not required to reproduce the frozen result, and do not provide
ground truth or institutional validation.

## Considered but not used

ERA5-Land, ESA WorldCover, and Copernicus DEM were considered as possible
future contextual covariates. They were not incorporated into the frozen
pilot, no environmental-feature model was built, and they are not scientific
dependencies of the published result.

## Public derived package

`site-data/` contains derived, public-safe records: 611 provisional thermal
event centroids, two reference anchors, methodology/provenance metadata, and
six frozen figures. It excludes raw data, local rasters, private review
mappings, SQLite, credentials, and Earth Engine outputs.

The MIT software license does not automatically relicense NASA, Copernicus,
ANATI, publisher content, or other third-party material. See `NOTICE.md` and
`docs/ASSET_PROVENANCE.md`.

## Excluded decorative artwork

An unused decorative mineral-field raster was evaluated during development but
is not part of this public repository. It had no scientific role, was not
rendered by the final publication, and had an unresolved redistribution
boundary. No decorative raster is required for the clean-clone build.
