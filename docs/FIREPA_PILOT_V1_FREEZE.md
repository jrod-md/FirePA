# FirePA Scientific Pilot v1 — freeze

**Freeze date:** 2026-08-09
**Freeze commit parent:** `22ad92a72a81f3d8bec6938dd625634d731177ee`
**Checkout:** raíz del repositorio
**Status:** `FirePA Scientific Pilot v1 = frozen`

## Frozen scope

This freeze covers the local Coclé, Panamá pilot for 2025-01-01 through
2025-04-30. It includes the audited FIRMS input and processed detections, the
frozen `r1500_t06` provisional clustering table, the existing Sentinel-2
observability and NBR/dNBR artifacts, the separate seven-case `window_median`
review-asset pilot, the exploratory external-reference matching, and the
formal-review preparation state.

The freeze does not change FIRMS detections, clustering, official matching
coordinates, official windows or radius, Sentinel-2 scenes, `selected_pair`,
`window_median`, NBR/dNBR metrics, statistics, figures, or conclusions.

## External provenance

The canonical registry is
`references/external_reference_sources_v1.json`.

```text
external_reference_provenance = complete
source_count                  = 7
incident_count                = 2
REFERENCE-001 source_count    = 1
REFERENCE-002 source_count    = 6
registry_sha256               = 6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49
```

The registry separates `INCIDENT`, `SOURCE` and `MATCHING_ANCHOR` records.
The two matching anchors are approximate researcher-provided coordinates, not
coordinates claimed by the news or institutional sources. The official rules
remain `REFERENCE-001=2025-01-15..17`, `REFERENCE-002=2025-01-23..27`, both
inclusive, and `5,000 m`.

Guacamaya preserves the source-area discrepancy from 1,035 to approximately
1,500 ha, including the `>1,050` claim; FirePA does not adjudicate a true,
best or verified area. Cause status preserves `null` and
`suspected_intentional` separately, with intentionality still
suspected/unconfirmed. The registry URLs are provenance only: they are not
pipeline inputs, matching inputs, ground truth, targets, model data or human
review labels.

The manual OSINT search located six articles in January 2025, one in February,
and none in March or April. No qualifying articles were located during the
manual OSINT search for March or April 2025. This is not a claim that no fire
or thermal activity occurred in those months, and the search is not declared
exhaustive.

## Frozen scientific state

```text
official Picachos matches       = 0
official Guacamaya matches      = 6
Picachos diagnosis              = SPATIAL_THRESHOLD_MISS
Guacamaya representation        = 6 provisional clusters; 5 gaps > t06
formal_review_status             = deferred
formal_review_execution          = false
supervised_modeling_gate         = deferred
target_created                   = false
significant_burn_created         = false
earth_engine_queries_made        = false
network_access                   = false
institutional_validation         = false
ground_truth                     = false
```

The six Guacamaya matches remain associations between the frozen cluster table
and the official reference window; they are not confirmed fires. The Picachos
zero remains the official result under the unchanged `<=5 km` rule and is
explained diagnostically by the existing `SPATIAL_THRESHOLD_MISS` evidence.

## Integrity hashes

The following protected artifacts were compared before and after the freeze;
their SHA-256 values remain unchanged.

| Artifact | SHA-256 |
|---|---|
| processed FIRMS | `3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e` |
| `r1500_t06/events.csv` | `646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844` |
| `r1500_t06/membership.csv` | `e9629fb521ce05d7cf63ad68683c0c79801611102e454c6877e3746977efc504` |
| `r1500_t06/summary.json` | `1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736` |
| Sentinel-2 pilot cohort | `a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302` |
| Sentinel-2 observability inventory | `851beea9b09e19368cf1131e82b0df5de7e5cd98566cf1da4cddeab464c7dcd1` |
| Sentinel-2 AOI inventory | `fc0b77eb283455d08226152c50017d7cc70e3e0427f59f02788f0ce6d469a5b4` |
| selected-pair table | `24ba96aa8ee2a5a45d81e54d724d22c143be66583854764ef6c8919ea6b3dcd1` |
| dNBR event metrics | `9a1b0043a11ddf1da6e5fb5fe5a08241a28ee7d8e442d3832f4d8345fec30441` |
| dNBR report | `5d75cd585e2005729ca83056052a71508f54b17ff2f55aa0d85b76175fd38dd9` |
| observability report | `219d6a896c6966118154fc9da3cbc3b18775c07e142e592b7b43c36adc517655` |
| formal SQLite | `c8f96d1c82bb6948010f796e801735c8786603b1d06390080265a2d324ff2cba` |
| formal preparation summary | `d5124dbe20bec1f15ff44a6e3e96d5bef73c5f23f149eed168e37a21ab44ddb4` |
| `window_median` manifest | `f7d9c619cda537800f777523434a4c22925156628ecfad17ad02fac7656c30fd` |
| external-check manifest | `92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868` |
| external source registry | `6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49` |

## Reproducibility and validation

Run these commands from the checkout using the local `fuegopa` environment:

```powershell
python scripts/verify_final_scientific_report.py
python scripts/verify_external_reference_check.py
python scripts/verify_formal_review_28.py
python scripts/verify_window_median_review_asset.py --case-set calibration-7
python -m pytest -q
```

The pre-edit baseline was `288 passed` in `546.15s`. The provenance additions
contribute seven static tests, and the post-edit suite completed with
`295 passed` in `542.20s`. The validators continue to report no network
access, no Earth Engine queries, deferred formal review and
`execution_authorized=false`.

## Limits and version boundary

This freeze provides no ground truth, confirmed wildfire classification,
institutional accuracy validation, supervised target, model, operational
monitoring, severity estimate or public UI. `unobserved` is not a negative;
Guacamaya's fragmentation remains a representation hypothesis; and external
area/cause claims remain source-level claims.

Any change to scientific inputs, clustering, matching rules, coordinates,
windows, optical policy, metrics, figures, conclusions, labels, models or
external-source adjudication requires a new pilot version and a new explicit
scope decision. The requested commit is the stopping point: no Earth Engine,
network access, model execution, human review, push or publication is part of
this freeze.
