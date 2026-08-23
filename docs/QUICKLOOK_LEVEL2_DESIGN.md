# FirePA Quicklook Level 2 design

## Contract and scope

The Level 2 contract is:

```text
fuegopa-dnbr-quicklook-level2-v1
```

This is a controlled visual-evidence layer for human review. It does not
change the frozen `r1500_t06` cohort, event selection, selected scene IDs,
policy path, AOI, Cloud Score+ threshold, dNBR formulas, v3 metrics, review
queue, `significant_burn`, or any 2026 data. It does not train models, create
labels, expand the sample, download full scenes, or produce ground truth.

## Frozen analysis contract

| Item | Contract |
| --- | --- |
| AOI | `b0500`, 500 m detection-union buffer |
| Policy | Frozen principal or fallback path from `outputs/sentinel2_event_pair_selection.csv` |
| Cloud mask | Cloud Score+ `cs_cdf >= 0.50` |
| Analysis scale | 20 m |
| Analysis CRS | `EPSG:32617` |
| NBR | `(B8 - B12) / (B8 + B12)` |
| dNBR | `NBR_pre - NBR_post` |
| Numeric nodata | `-9999` |
| Reflectance nodata | `0` |
| Mask nodata | `0` (`uint8`) |
| dNBR global display | fixed `[-1.0, 1.0]` |
| dNBR diagnostic display | fixed `[-0.25, 0.50]` |

Sentinel-2 source resolutions are preserved in the source graph: B2, B3, B4
and B8 are 10 m; B8A and B12 are 20 m. All Level 2 exports are requested at
the frozen 20 m analysis scale so B12, NBR, dNBR, masks, and false-color
evidence use the same review grid.

The RGB presentation uses `B4/B3/B2`. The SWIR false-color presentation uses
`R=B12`, `G=B8A`, `B=B4`. Bilinear resampling is presentation-only for RGB and
false-color tiles; numeric rasters and masks use nearest-neighbor display.

The common-valid mask is the v3 support contract: B8/B12 spectral validity
plus the CS+ threshold. The additional RGB/SWIR bands are carried on that
same support and are never used to redefine dNBR validity.

## Frozen selected scenes

| Event | Policy | PRE scene | POST scene |
| --- | --- | --- | --- |
| `event-r1500_t06-0ddd477d24b1364d` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250116T155519_20250116T155633_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250131T155551_20250131T155550_T17PNK` |
| `event-r1500_t06-84cb252a6877d2d5` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250307T155529_20250307T155526_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250322T155551_20250322T155633_T17PNK` |
| `event-r1500_t06-ef20fd746737f4ea` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250312T155551_20250312T160013_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250327T155529_20250327T160021_T17PNK` |
| `event-r1500_t06-9e5bf1d807f9d61a` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250401T155551_20250401T160042_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250501T155551_20250501T155545_T17PNK` |
| `event-r1500_t06-548ca9e284d1a330` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250225T155529_20250225T155527_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250317T155529_20250317T155525_T17PNK` |
| `event-r1500_t06-040b1a186d857b11` | principal | `COPERNICUS/S2_SR_HARMONIZED/20250329T154611_20250329T154834_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250418T154611_20250418T154735_T17PNK` |
| `event-r1500_t06-09c2d54e2d8fb5dd` | fallback | `COPERNICUS/S2_SR_HARMONIZED/20250401T155551_20250401T160042_T17PNK` | `COPERNICUS/S2_SR_HARMONIZED/20250625T155529_20250625T155525_T17PNK` |

## Outputs

The runner creates new, ignored Level 2 paths only:

- `outputs/rasters/sentinel2_level2/events/`: 9 TIFF/support surfaces per
  selected/window mode plus one export metadata sidecar per event.
- `outputs/figures/sentinel2_dnbr_level2/events/`: one multispectral panel and
  one temporal robustness sheet per event.
- `outputs/review_upload_level2/`: the same 14 RGB PNGs for review upload.
- `outputs/quicklook_level2_report.json` and `.md`.
- `outputs/manifests/firepa_quicklook_level2.sha256`.

The eight spectral/numeric/mask surfaces are controlled Earth Engine downloads.
The `aoi_support.tif` is a geometry-only local rasterization of the exact
frozen `build_aoi(...).geometry_utm` payload onto the returned export grid; it
exists to reproduce the v3 support edge without changing the AOI or creating a
new scientific metric. Its source and geometry query are recorded in each
sidecar.

The temporal sheet uses a separate numeric `window_median` export whenever the
frozen candidate scenes can be reconstructed. It never substitutes the
selected-pair image for a window raster.

## Global false-color stretch

The stretch is computed once from all 14 selected-pair false-color rasters,
using valid pixels only and global P2/P98 per band. The final run recorded:

| Band | P2 | P98 | Valid values |
| --- | ---: | ---: | ---: |
| B12 | 718.0 | 2659.84 | 78,359 |
| B8A | 1302.0 | 5292.0 | 78,359 |
| B4 | 254.0 | 1990.0 | 78,359 |

No per-event recalculation is allowed.

## Validation and limitations

Local float32 NBR/dNBR rasters are the numeric source for the reconciliation;
PNG color is never read back as science. The final explicit tolerances are:

- dNBR median and p90: `0.005`;
- each threshold area: `0.50 ha`;
- valid overlap: `0.005`;
- common valid pixels: `16`.

The area/pixel allowance is intentionally compatible with 20 m AOI boundary
pixels (`0.04 ha` nominally), float32 thresholding, projection edge behavior,
nodata, and pixel-area representation. It is not an invitation to reinterpret
the outputs as labels. Positive dNBR is described as spectral vegetation loss;
negative dNBR as spectral vegetation gain. `dNBR is descriptive and not a
confirmation of fire.` No panel encodes severity, a positive/negative case,
strong burn, confirmed fire, ground truth, or causal attribution.

## Integrity boundary

Before and after hashes cover the inherited scientific inputs/outputs, v1,
v2, and v2.1 artifacts. Only Level 2 code, tests, documentation, and new
ignored Level 2 artifacts are in scope. No credentials, token, or Earth Engine
project ID is persisted in code, sidecars, reports, or PNG metadata. No push is
performed by the Level 2 runner.
