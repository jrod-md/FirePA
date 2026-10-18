# Public asset provenance

This document covers visual assets delivered by the public static publication.
It does not replace the scientific data provenance in
`site-data/provenance.json` or the source register in `SOURCES.md`.

## Frozen scientific figures

The six PNG files under `site-data/figures/` were copied byte-for-byte from the
frozen scientific report bundle. The website copies them without recompression,
cropping, relabeling, recoloring, or translation. Their SHA-256 values and
dimensions are recorded in `site-data/manifest.json` and
`site-data/provenance.json`.

## Coclé presentation geometry

`site/src/data/cocle-presentation.geojson` is a deterministic presentation
derivative used by the static site. Its local source is the validated Coclé
province geometry described in `SOURCES.md`. The original boundary files and
the local `data/reference/cocle.geojson` are not redistributed.

The derivative provides geographic context only. It is not a thermal-event
observation, burn perimeter, satellite raster, or inferred scientific layer.
The build validates the tracked derivative when the non-redistributed source is
absent and regenerates it only when that source is explicitly available.

## Exploratory 3D case viewer (`/explorar/`)

`site/public/explorar/` is a generated copy of
`explorations/case-viewer-3d/web/`, written by
`explorations/case-viewer-3d/scripts/export_to_site.py`. Its
`manifest.json` lists every file with its SHA-256, and the site contract test
checks the built copy against it. The viewer is exploratory and outside
FirePA Scientific Pilot v1: it does not change `site-data/`, the frozen
figures or the report.

Its rasters are display derivatives of open data:

- Terrain and shaded-relief tiles derive from Copernicus DEM GLO-30
  (© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018,
  provided under COPERNICUS by the European Union and ESA). The DEM is a
  surface model and the tint encodes elevation only, not land cover.
- Before/after images and dNBR overlays derive from Copernicus Sentinel-2 L2A
  scenes ("contains modified Copernicus Sentinel data 2024-2025"), read through
  Earth Search (Element84) on AWS. The scene IDs are recorded in each case's
  `s2.json`.
- Point and timeline data are FirePA v1 public events, shown without
  recomputation.

The viewer loads MapLibre GL JS 5.6.0 and Google Fonts from their CDNs at view
time. Those libraries keep their own licenses.

## Fonts and dependencies

The frontend uses Source Serif 4 and IBM Plex packages declared in
`site/package.json`. Those packages and Astro retain their own licenses and are
not relicensed by FirePA.

## Excluded decorative artwork

The unused mineral-field raster evaluated during development is not included in
the final public repository. It was never scientific evidence, is not rendered
by the publication, and is not part of the clean-clone build. Exclusion avoids
publishing an asset with an unresolved redistribution boundary.
