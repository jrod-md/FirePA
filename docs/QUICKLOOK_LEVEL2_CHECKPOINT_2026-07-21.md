# Quicklook Level 2 checkpoint — 2026-07-21

## Run status

- Initial HEAD: `ecf54756f99016e449b725ac97fe7223e26082ea`
- Branch: `master`
- Contract: `fuegopa-dnbr-quicklook-level2-v1`
- Earth Engine initialized from the environment only; authentication was not
  called and the project ID was not persisted.
- Final run: `7/7` calibration events generated, `0` errors.
- Final Earth Engine query accounting: `123` total = `2` smoke collection
  queries + `7` frozen UTM geometry queries + `114` GeoTIFF download queries.
- No push was performed.

## Frozen scenes and policies

| Event | Policy | PRE | POST | Window raster |
| --- | --- | --- | --- | --- |
| `event-r1500_t06-0ddd477d24b1364d` | principal | `20250116T155519_20250116T155633_T17PNK` | `20250131T155551_20250131T155550_T17PNK` | available |
| `event-r1500_t06-84cb252a6877d2d5` | principal | `20250307T155529_20250307T155526_T17PNK` | `20250322T155551_20250322T155633_T17PNK` | available |
| `event-r1500_t06-ef20fd746737f4ea` | principal | `20250312T155551_20250312T160013_T17PNK` | `20250327T155529_20250327T160021_T17PNK` | available |
| `event-r1500_t06-9e5bf1d807f9d61a` | principal | `20250401T155551_20250401T160042_T17PNK` | `20250501T155551_20250501T155545_T17PNK` | available |
| `event-r1500_t06-548ca9e284d1a330` | principal | `20250225T155529_20250225T155527_T17PNK` | `20250317T155529_20250317T155525_T17PNK` | available |
| `event-r1500_t06-040b1a186d857b11` | principal | `20250329T154611_20250329T154834_T17PNK` | `20250418T154611_20250418T154735_T17PNK` | available |
| `event-r1500_t06-09c2d54e2d8fb5dd` | fallback | `20250401T155551_20250401T160042_T17PNK` | `20250625T155529_20250625T155525_T17PNK` | available |

The full scene IDs, UTC timestamps, windows, and candidate IDs are retained in
the per-event sidecars under
`outputs/rasters/sentinel2_level2/events/` and in
`outputs/quicklook_level2_report.json`.

## Export and rendering contract

- Bands: RGB `B4/B3/B2`; false-color `B12/B8A/B4`; numeric NBR/dNBR from
  `B8/B12`; common mask from B8/B12 + CS+.
- Source resolutions: B2/B3/B4/B8 are 10 m; B8A/B12 are 20 m.
- Export/anlysis scale: 20 m.
- CRS: `EPSG:32617`.
- Formulas: `(B8 - B12) / (B8 + B12)` and `NBR_pre - NBR_post`.
- Nodata: reflectance `0`, numeric `-9999`, mask `uint8 0`.
- dNBR display ranges: global `[-1.0, 1.0]`, diagnostic `[-0.25, 0.50]`.
- Global false-color P2/P98, shared across all 14 selected-pair images:

  | Band | P2 | P98 | Valid pixels |
  | --- | ---: | ---: | ---: |
  | B12 | 718.0 | 2659.84 | 78,359 |
  | B8A | 1302.0 | 5292.0 | 78,359 |
  | B4 | 254.0 | 1990.0 | 78,359 |

- Bilinear is presentation-only for RGB/false-color; numeric/mask displays are
  nearest-neighbor. No PNG was used as a numeric source.

## Numeric reconciliation

The final run performed `56` selected-pair checks and `56` window checks; all
passed. Explicit tolerances were:

| Metric | Tolerance | Maximum observed absolute difference |
| --- | ---: | ---: |
| dNBR median | 0.005 | 0.0020823 |
| dNBR p90 | 0.005 | 0.0036571 |
| Each threshold area | 0.50 ha | 0.2276915 ha |
| Valid overlap | 0.005 | 0.0010100 |
| Common valid pixels | 16 | 5 |

The area/pixel allowance covers float32 thresholding and 20 m AOI edge/pixel
area representation; it does not change any v3 metric.

## Outputs and window status

- Selected-pair rasters: `63` (`9` per event, including the geometry-only
  `aoi_support` surface).
- Window rasters: `63` (`9` per event).
- Multispectral panels: `7`.
- Temporal robustness sheets: `7`.
- Review-upload PNGs: `14`.
- `window_median`: numeric GeoTIFF available for all seven events, rebuilt only
  from frozen inventory candidates; no selected-pair image was reused.

Exact paths:

```text
outputs/rasters/sentinel2_level2/events/
outputs/figures/sentinel2_dnbr_level2/events/
outputs/review_upload_level2/
outputs/quicklook_level2_report.json
outputs/quicklook_level2_report.md
outputs/manifests/firepa_quicklook_level2.sha256
```

The manifest contains `161` hashed Level 2 evidence artifacts. Manifest file
SHA-256: `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705`.
Manifest content index SHA-256:
`dc9c028985f5affcf618455b5b3600aa2b7bfe1d3b8f70185301ec24d4150db4`.

## Integrity and limitations

- Protected snapshot index before/after:
  `f49bc924d7e11ab963343af920a027c36949af9da1e26fef1fa985bf9c6ee23c`.
- Scientific index before/after:
  `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa`.
- v1 visual index before/after:
  `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401`.
- v2/v2.1 protected outputs remained unchanged.
- No detections, membership, event cohort, inventories, selection, v3
  metrics, sensitivity, review queue, checkpoint, cache, errors, scientific
  reports, or v1/v2/v2.1 quicklooks were modified.
- No labels, ground truth, models, sample expansion, full-scene download, or
  2026 data were used.
- Positive dNBR means spectral vegetation loss and negative dNBR means
  spectral vegetation gain; dNBR remains descriptive and is not confirmation
  of fire.

## Tests and Git

- New Level 2 tests: `5 passed`.
- Pre-existing full suite preflight: `165 passed`.
- Final pre-commit status recorded by the runner contains only the intended
  new code/test paths plus pre-existing untracked `data/`, `notebooks/`, and
  `docs/HANDOFF_FIREPA_2026-07-21.md`.
- The final requested commit is local only and must be:
  `Add Level 2 multispectral review evidence`.
