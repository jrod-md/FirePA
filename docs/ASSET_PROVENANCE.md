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

## Fonts and dependencies

The frontend uses Source Serif 4 and IBM Plex packages declared in
`site/package.json`. Those packages and Astro retain their own licenses and are
not relicensed by FirePA.

## Excluded decorative artwork

The unused mineral-field raster evaluated during development is not included in
the final public repository. It was never scientific evidence, is not rendered
by the publication, and is not part of the clean-clone build. Exclusion avoids
publishing an asset with an unresolved redistribution boundary.
