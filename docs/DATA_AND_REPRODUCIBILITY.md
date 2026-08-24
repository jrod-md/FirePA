# Data and reproducibility

## Authority and freeze

The public machine-readable package in `site-data/` is the primary publication
authority. Its package version is `firepa-public-release-v1`; its scientific
freeze commit is `7694da7df5808911de48de84016759c5fd22f176`.

`site-data/manifest.json` records file sizes and SHA-256 values. The package is
deterministic and excludes its own manifest from the hash list.

The scientific-document hashes embedded in `citations.json` identify the
frozen analytical snapshots used when the package was generated. Current
publication-facing Markdown may add boundary explanations without claiming to
be byte-identical to those snapshots. The verifier checks that citation ledger
against verifier-owned frozen expectations, while canonical scientific
statements are cross-checked separately.

`project-summary.json` retains `p2_started: false` as frozen metadata from the
package-generation checkpoint. It describes the state when the analytical
projection was produced, not the current website status. The current bilingual
publication is implemented in `site/`; the frozen field is not rewritten
without a full authorized package regeneration.

## Public package inventory

| Path | Purpose |
|---|---|
| `project-summary.json` | Frozen counts, scope, period, and key findings |
| `events.geojson` | Exactly 611 public WGS84 event centroids |
| `external-references.geojson` | Two approximate comparison anchors |
| `guacamaya-timeline.json` | Six-cluster chronology and five gaps |
| `methodology.json` | Machine-readable workflow and limits |
| `citations.json` | Scientific-document and external-source registry |
| `provenance.json` | Inputs, transformations, hashes, and privacy boundary |
| `figures/*.png` | Six byte-frozen scientific figures |
| `manifest.json` | Deterministic public-package ledger |

Public event coordinates are centroids for presentation and inspection. They
are not burn perimeters or precision ground observations.

Each event exposes 19 public properties:

```text
public_event_id, configuration_id, start_time_utc, end_time_utc,
duration_hours, detection_count, source_count, satellite_count, satellites,
frp_min_mw, frp_max_mw, frp_mean_mw, frp_median_mw, frp_sum_mw,
day_fraction, night_fraction, daynight_known_count, possible_chain_merge,
optical_cohort_status
```

These are public descriptive fields. None is a confirmed-fire, severity,
ground-truth, or predictive-model field.

## Frozen figure hashes

| Figure | SHA-256 |
|---|---|
| `01_pipeline_overview.png` | `f818cc2f0ebe93a450c6dff5c505849a91c71bf013e597bdc6852a8cc7b94d1c` |
| `02_cluster_distribution.png` | `5941c237f74a4ad95809aa7a0430a70269337560aa4cbabc62601d03edf2c2ea` |
| `03_external_reference_map.png` | `3f0bcd569a0d762bb1c2435fe25158bf9ecbdedb1ada682c04c1a299a32916e7` |
| `04_guacamaya_timeline.png` | `d248bdda6b88eee52dc27f2567a29ec3bcf494a72b139ffc1340bed7db4566d0` |
| `05_guacamaya_frp_distribution.png` | `973ef4f72e0f15873a11007359a6dba5aae419d4b83a78a855f428227a4c777b` |
| `06_los_picachos_diagnostic.png` | `8fa486e16e97063ad5f55b76165a3c671c2b1acd6b6c5c717a838ef56d4176a2` |

These files must not be edited, regenerated, cropped, recolored, relabeled, or
translated at pixel level. Every frozen PNG is 1600 × 900 pixels; dimensions
and byte hashes are also recorded in `site-data/provenance.json`.

## Clean-clone contract

The public website can be built and tested from a clean clone without private
data, a backend, network access, Earth Engine, or the local source boundary:

```powershell
cd site
npm ci
npm run build
npm run test
```

The cartography preparation step uses the tracked Coclé presentation derivative
when `data/reference/cocle.geojson` is absent. It validates that derivative and
does not substitute a bounding box or synthetic geography.

The public package verifier can be run from the repository root:

```powershell
python scripts/verify_public_release_package.py --package site-data
python -m pytest -q
```

The verifier is the clean-clone public scientific contract. The pytest suite
also runs from a clean clone: self-contained tests execute, while tests whose
named protected inputs are absent report explicit skips. When those inputs are
present, the same tests execute normally; scientific assertion failures are
not converted into skips.

## Full-regeneration boundary

A clean clone does not promise full scientific regeneration. The following are
intentionally excluded:

- raw FIRMS downloads and manifests containing local acquisition records;
- processed and interim research tables;
- Sentinel-2 rasters, caches, quicklooks, and Earth Engine outputs;
- the local administrative-boundary source;
- private reviewer identities, alias mappings, assignments, and SQLite;
- historical model-assisted response JSON, anonymized case packages, and the
  private case-to-event mapping;
- credentials, tokens, and `.env` values; and
- generated reports and review bundles under `outputs/`.

Regeneration of those stages requires the actual excluded inputs and, for
remote optical acquisition, authorized external services. The pipeline must
fail rather than fabricate scientific substitutes.

The historical blind model-assisted calibration is therefore reproducible only
inside the protected source boundary. Its public aggregate record and its
explicit non-effect on released outputs are documented in
[`MODEL_ASSISTED_CALIBRATION.md`](MODEL_ASSISTED_CALIBRATION.md).

When every excluded artifact is available, run the stricter source gate:

```powershell
python scripts/verify_public_release_package.py --package site-data --full-source
```

This mode fails on any missing or hash-drifted protected source. It is not the
default clean-clone contract.

## Protected source hashes

The public provenance records protected local input hashes without publishing
their contents, including:

- processed FIRMS: `3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e`;
- frozen events: `646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844`;
- clustering summary: `1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736`;
- optical cohort: `a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302`;
- external registry: `6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49`.

## Public/private boundary

The public package contains no raw detection rows, private review mappings,
reviewer identities, SQLite, secrets, or absolute local paths. Its figures were
copied byte-for-byte, and its event rows were deterministically projected to
public IDs and WGS84 centroids.

Changes to documentation metadata may update package document hashes and the
manifest without changing any scientific event, count, metric, figure, or
protected source hash. Any scientific change requires a new version beyond the
frozen pilot.
