# FirePA — P1 Public Release Package handoff

> **ARCHIVED PACKAGE HANDOFF — NOT CURRENT PUBLICATION STATUS.** This record
> documents the package state before the bilingual site existed. Current
> publication authority begins at `site-data/manifest.json`,
> `docs/SCIENTIFIC_REPORT.md`, and `docs/README.md`.

**Snapshot:** 2026-08-10
**Gate:** **P1 PASS — remediation complete**
**Checkout:** raíz del repositorio
**Branch:** `master`
**Remediation starting HEAD:** `4b3e1c361082a23046a577cf380ed7a28517ba6d`
**Scientific freeze:** `7694da7df5808911de48de84016759c5fd22f176`
**Push:** no push performed

## Outcome

P1 produced and verified a deterministic, frontend-agnostic public data package
from the frozen FirePA v1 artifacts. The package is publication engineering
only. It does not start P2, choose a frontend, query Earth Engine, rerun
clustering, recompute rasters, extend OSINT, or execute formal human review.

The public scientific unit is **provisional thermal event**. The package
serializes 611 provisional thermal events and preserves the explicit limits that
they are not confirmed wildfire classifications, ground truth, supervised
predictions, severity labels, or operational alerts.

## Preflight and protected state

The preflight recorded root, branch, HEAD and status before implementation. The
only pre-existing untracked paths were preserved without staging or deletion:

~~~text
data/interim/.gitkeep
data/processed/.gitkeep
data/raw/.gitkeep
data/raw/manifests/.gitkeep
data/reference/.gitkeep
data/reference/README.md
docs/HANDOFF_FIREPA_2026-07-21.md
notebooks/.gitkeep
~~~

The generator and verifier rechecked the frozen hashes for the protected
scientific artifacts, including the canonical `r1500_t06` events, membership
and summary, FIRMS processed data, Sentinel-2 cohort/inventory/report/pair and
dNBR artifacts, human-review SQLite/preparation artifacts, window-median
manifest, external-check manifest, and the canonical registry. No protected
hash changed during P1.

## P1 remediation hardening

The independent technical-methodological audit identified four publication
contract issues; the scientific outputs were not reopened or recomputed. The
remediation is limited to the P1 publication layer:

- `provenance.json` now documents `figure_provenance` in its top-level schema,
  and each of the eleven `source_artifacts` records carries a fixed factual
  `role`; contract, generator, verifier and tests enforce the exact schema.
- The verifier scans textual claims in every public JSON/GeoJSON payload. It
  rejects unsupported positive fire, wildfire, classification, prediction,
  probability and severity claims while preserving explicit negative and
  limitation statements.
- Critical freeze expectations, the canonical registry hash, protected hashes,
  frozen count ledger and Picachos/Guacamaya invariants are owned locally by
  the verifier rather than imported from the generator.
- Event verification now requires the exact feature sequence
  `evt-0001` through `evt-0611`; a focused regression test detects reordering.

The verifier and direct post-run hash comparison confirmed all 16 protected
scientific artifacts unchanged.

## Public schema audit decisions

`docs/P1_PUBLIC_SCHEMA_AUDIT.md` records the source ledger and field-level
allowlists. The public projection makes these decisions explicit:

- `events.geojson` contains 611 WGS84 `Point` features at frozen centroids.
- Source event IDs are not published; deterministic IDs `evt-0001` through
  `evt-0611` are assigned after lexical sorting of frozen source IDs.
- Event properties contain only configuration, UTC interval, duration, counts,
  satellite names/count, descriptive FRP aggregates, day/night fractions,
  possible-chain flag and optical cohort status.
- Raw detection rows, FIRMS confidence, source/alias joins, scene IDs and
  paths, raster/quicklook paths, NBR/dNBR metrics, review assignments,
  reviewer/private mappings, model fields and SQLite are excluded.
- Optical status is `observable` for 28 cohort events, `unobserved` for 2, and
  `not_in_cohort` for the remaining 581. Unobserved is not serialized as a
  negative label.
- `external-references.geojson` contains the two registry incidents. The
  public projection excludes the internal match provenance field and preserves
  the canonical registry hash.
- `guacamaya-timeline.json` contains six matched provisional cluster rows,
  72.733 hours of span and five inter-cluster gaps greater than six hours.
- Six existing final-report PNGs are copied byte-identically at 1600x900. No
  figure pixels or scientific content are recomputed.

## Package tree

~~~text
site-data/
  citations.json
  events.geojson
  external-references.geojson
  guacamaya-timeline.json
  manifest.json
  methodology.json
  project-summary.json
  provenance.json
  figures/
    01_pipeline_overview.png
    02_cluster_distribution.png
    03_external_reference_map.png
    04_guacamaya_timeline.png
    05_guacamaya_frp_distribution.png
    06_los_picachos_diagnostic.png
~~~

Package version: `firepa-public-release-v1`. The manifest contains 14 files and
the package size is 657,095 bytes. The size increase is the deterministic
provenance `role` field in eleven source records.

## Reproduction and validation commands

All commands used the bundled `fuegopa` Python environment and ran locally:

~~~powershell
python scripts\build_public_release.py --output site-data
python scripts\verify_public_release_package.py --package site-data
python -m pytest -q tests\test_public_release.py
python scripts\verify_final_scientific_report.py
python scripts\verify_external_reference_check.py
python scripts\verify_formal_review_28.py
python scripts\verify_window_median_review_asset.py --case-set calibration-7
python -m pytest -q
~~~

Observed results:

| Check | Result |
|---|---|
| Public build | `deterministic=true`, `network_access=false`, `earth_engine_queries_made=false`, 611 events, 2 references, 7 sources |
| Public verifier | `ok=true`, 14 files, 611 events, 2 references, zero errors |
| P1 focused tests | `11 passed`, one cache-permission warning |
| Final scientific report validator | `ok=true`, 6 figures, 13 manifest records |
| External reference validator | `ok=true`, 611 clusters, 6 matches, read-only, execution unauthorized |
| Formal review validator | `integrity=OK`, 28 observable, 2 unobserved, execution unauthorized |
| Window-median validator | `status=pass`, 7 cases, read-only, execution unauthorized |
| Full regression suite | `306 passed`, one cache-permission warning, `545.42s` |

The focused deterministic test builds two temporary packages and compares every
file byte-for-byte. The generated JSON has stable ordering, no current
timestamps, and no network or Earth Engine dependency.

## Privacy and scientific-boundary checks

The verifier rejects unexpected package files, manifest hash/size drift,
absolute Windows/Unix paths, private key/credential markers, SQLite/reviewer
fields, forbidden target/prediction/severity fields, and unsupported positive
claims across every public JSON/GeoJSON textual payload. Explicit negative and
scope limitations remain allowed in the summary and methodology. The package
contains no raw detection table, private review database, review manifest,
seed, scene/raster path, or internal match provenance.

The only warning observed is the existing environment permission warning when
pytest attempts to write `.pytest_cache` under the checkout. It did not change
scientific outputs, public package contents, or test status.

## P2 boundary

P2 is not started. No frontend, map library, framework, hosting provider,
domain, visual direction, or runtime data loader was selected. The package is
frontend-agnostic and is the only public-release artifact delivered by this
gate.

## Auditor inputs

The exact inputs for an independent audit are:

~~~text
CONTEXT.md
PLAN.md
PROJECT_STATUS.md
docs/FIREPA_PILOT_V1_FREEZE.md
docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md
docs/FIREPA_PILOT_FINAL_CHECKPOINT.md
references/external_reference_sources_v1.json
docs/P1_PUBLIC_SCHEMA_AUDIT.md
docs/P1_PUBLIC_RELEASE_CONTRACT.md
docs/P1_PUBLIC_RELEASE_HANDOFF.md
scripts/build_public_release.py
scripts/verify_public_release_package.py
tests/test_public_release.py
site-data/manifest.json
site-data/provenance.json
site-data/project-summary.json
site-data/events.geojson
site-data/external-references.geojson
site-data/guacamaya-timeline.json
site-data/methodology.json
site-data/citations.json
site-data/figures/*.png
~~~

P1 is complete and ready for the next explicitly authorized gate. No remote
publication or push is included in this handoff.
