# FirePA

FirePA is a reproducible remote-sensing research pilot studying **provisional
thermal events** in Coclé, Panama, from **2025-01-01 through 2025-04-30**. It
asks a bounded question: what can satellite thermal signals tell us about what
happened on the ground, and where does that evidence stop?

[Website](https://firepa.pages.dev/) ·
[Source repository](https://github.com/jrod-md/FirePA) ·
[Scientific report](docs/FirePA_Scientific_Pilot_v1.pdf)

[![Public validation](https://github.com/jrod-md/FirePA/actions/workflows/public-validation.yml/badge.svg)](https://github.com/jrod-md/FirePA/actions/workflows/public-validation.yml)

The repository contains:

- a bilingual English/Latin American Spanish static publication in `site/`;
- a deterministic, public-safe analytical package in `site-data/`;
- the scientific pipeline and its verification tests; and
- a canonical scientific report in [`docs/SCIENTIFIC_REPORT.md`](docs/SCIENTIFIC_REPORT.md),
  with the publication PDF at
  [`docs/FirePA_Scientific_Pilot_v1.pdf`](docs/FirePA_Scientific_Pilot_v1.pdf).

FirePA is **not real-time, not operational, and not a wildfire confirmation or
alert system**. The 611 analytical units are provisional thermal events, not
611 confirmed fires.

## Frozen pilot at a glance

| Item | Frozen result |
|---|---:|
| Audited FIRMS raw detections | 1,532 |
| Processed detections in Coclé | 1,185 |
| Clustering configuration | `r1500_t06` |
| Provisional thermal events | 611 |
| Singleton events | 344 |
| Multi-detection events | 267 |
| `possible_chain_merge` events | 17 |
| Sentinel-2 optical cohort | 30 |
| Observable / unobserved | 28 / 2 |
| Formal human observations | 0 |
| External source documents / incidents | 7 / 2 |

Scientific freeze commit:
`7694da7df5808911de48de84016759c5fd22f176`.

## Methodological pipeline

1. Audit 1,532 NASA FIRMS VIIRS records.
2. Retain 1,185 valid detections inside Coclé and the inclusive study window.
3. Group detections with connected components under `r1500_t06`: 1,500 m,
   six hours, and `EPSG:32617` metric distance.
4. Preserve 611 groups as provisional thermal events.
5. Follow a frozen 30-event cohort with Sentinel-2: 28 observable and two
   `unobserved` cases.
6. Treat NBR and dNBR as descriptive optical evidence, not labels or severity.
7. Compare the frozen events with two approximate external-reference anchors
   using inclusive temporal overlap and distance `<= 5,000 m`.

See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the method and
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for the inference boundary.
The exploratory blind model-assisted review calibration is documented
separately in
[`docs/MODEL_ASSISTED_CALIBRATION.md`](docs/MODEL_ASSISTED_CALIBRATION.md); it
did not affect any frozen output.

## External-reference findings

### Cerro Guacamaya

The official comparison returns six matched provisional clusters. They remain
six separate analytical units. Five inter-cluster gaps exceed six hours, the
overall span is 72.733 hours, and `fragmentation_possible = true`. This supports
a representation warning: a prolonged documented incident may correspond to
multiple FirePA events. It does not authorize merging the six clusters into one
continuous incident.

### Cerro Los Picachos

The official inclusive 5,000 m comparison returns zero matches. The nearest
documented contemporary signal is 10,400.826 m away, so the frozen diagnostic
is `SPATIAL_THRESHOLD_MISS`. The zero describes a threshold result; it does not
mean no fire, no activity, no thermal signal, or absence of an event.

## What FirePA is not

The pilot provides no ground truth, institutional validation, supervised
predictive model, severity classification, operational monitoring, or
real-time alerting. Two optically `unobserved` cases are not negative cases.
External references are relational evidence, not truth labels.

## Public package

`site-data/` is the highest-level public machine-readable authority. It
contains:

- `events.geojson`: exactly 611 public event centroids;
- `external-references.geojson`: two approximate comparison anchors;
- `guacamaya-timeline.json`: the six-cluster chronology;
- `methodology.json`, `project-summary.json`, `provenance.json`, and
  `citations.json`;
- six byte-frozen scientific figures; and
- `manifest.json`, with deterministic SHA-256 records.

The package excludes raw FIRMS rows, private reviewer mappings, SQLite,
credentials, Sentinel-2 rasters, Earth Engine outputs, and local reference
geometry. See
[`docs/DATA_AND_REPRODUCIBILITY.md`](docs/DATA_AND_REPRODUCIBILITY.md).

## Repository structure

```text
docs/          Canonical report, methodology, limitations, and technical records
references/    Frozen external-source registry
scripts/       Reproducible pipeline and package verification entry points
site/          Bilingual Astro static publication
site-data/     Public machine-readable package and frozen figures
src/fuegopa/   Python implementation
tests/         Scientific and publication-contract tests
```

Downloaded inputs and generated research outputs are intentionally excluded
from Git. The tracked `.gitkeep` files document those local directories.

## Run the public website

Node.js and npm are required. From a clean clone:

```powershell
cd site
npm ci
npm run build
npm run test
```

For local development:

```powershell
cd site
npm run dev
```

The Astro project is inside `site/`; running `npm run dev` from the repository
root will fail because there is no root `package.json`.

The build uses the tracked Coclé presentation derivative when the
non-redistributed local source boundary is unavailable. It does not fabricate a
replacement boundary.

## Python environment

Python 3.10 or later is required for the scientific code:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/verify_public_release_package.py --package site-data
python -m pytest -q
```

The verifier and pytest suite form the clean-clone public validation contract.
Self-contained tests run normally. Tests that require specifically named,
excluded source artifacts skip only when those preconditions are absent.

Full scientific regeneration is intentionally not a clean-clone promise. It
requires excluded source inputs and, for Sentinel-2 acquisition, external
credentials and services. Historical model-assisted calibration additionally
requires non-redistributed panels, response JSON, a private case mapping, and a
local review store. The public package remains inspectable and the site remains
buildable without them.

The stricter full-source gate is explicit:

```powershell
python scripts/verify_public_release_package.py --package site-data --full-source
```

It requires every protected local source and compares its frozen hash. The
command is expected to fail in a clean public clone because those inputs are
intentionally absent.

## Documentation authority

When descriptions differ, use this order:

1. `site-data/manifest.json` and the machine-readable public package;
2. [`docs/SCIENTIFIC_REPORT.md`](docs/SCIENTIFIC_REPORT.md);
3. methodology, reproducibility, limitations, provenance, and source records;
4. this README;
5. website presentation.

Detailed historical protocols retained under `docs/` are supporting evidence,
not parallel current-state summaries. Start with [`docs/README.md`](docs/README.md).

## Citation, sources, and licensing

Citation metadata is in [`CITATION.cff`](CITATION.cff). Cite the repository
title, named author, versioned public package, and scientific freeze commit.
No DOI or publication venue is claimed.

Source provenance and redistribution boundaries are documented in
[`SOURCES.md`](SOURCES.md), [`NOTICE.md`](NOTICE.md), and
[`docs/ASSET_PROVENANCE.md`](docs/ASSET_PROVENANCE.md). FirePA-authored source
code is available under [`LICENSE`](LICENSE); third-party data and source
materials retain their own terms.

Public access: [website](https://firepa.pages.dev/),
[source repository](https://github.com/jrod-md/FirePA), and
[scientific report](docs/FirePA_Scientific_Pilot_v1.pdf).
