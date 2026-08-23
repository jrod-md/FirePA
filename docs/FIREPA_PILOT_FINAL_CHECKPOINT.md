# FirePA — final pilot checkpoint

**Fecha:** 2026-08-09
**Checkout:** raíz del repositorio
**Base commit:** `22ad92a72a81f3d8bec6938dd625634d731177ee`
**Commit solicitado:** `Complete FirePA pilot scientific analysis`

## Dataset and method versions

| Capa | Versión/contrato | Estado |
|---|---|---|
| FIRMS | `firms-cocle-v1` | 1,532 raw → 1,185 processed |
| Clustering | `r1500_t06` | 1,500 m, 6 h, EPSG:32617, 611 clusters |
| Sentinel-2 observability | `fuegopa-sentinel2-observability-v1` | pilot estructural de 30 |
| NBR/dNBR | `fuegopa-sentinel2-dnbr-v3` | 28 métricas, 2 excluidos como `unobserved` |
| `window_median` | `firepa-window-median-review-asset-v1` | `calibration-7`, `pilot_pass`, 7/7 |
| External check | `external_reference_check_v1` | 2 incidentes, 7 fuentes, sin reclustering |
| External provenance | `firepa-external-reference-sources-v1` | completo; registry SHA-256 registrado abajo |
| Formal review | `firepa-human-review-tool-v2`, protocol v1 | preparado/no iniciado |

## Critical hashes

| Artefacto | SHA-256 |
|---|---|
| processed FIRMS | `3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e` |
| `r1500_t06/events.csv` | `646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844` |
| `r1500_t06/membership.csv` | `e9629fb521ce05d7cf63ad68683c0c79801611102e454c6877e3746977efc504` |
| `r1500_t06/summary.json` | `1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736` |
| optical pilot cohort | `a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302` |
| Sentinel-2 scene inventory | `851beea9b09e19368cf1131e82b0df5de7e5cd98566cf1da4cddeab464c7dcd1` |
| selected-pair table | `24ba96aa8ee2a5a45d81e54d724d22c143be66583854764ef6c8919ea6b3dcd1` |
| dNBR event metrics | `9a1b0043a11ddf1da6e5fb5fe5a08241a28ee7d8e442d3832f4d8345fec30441` |
| formal SQLite | `c8f96d1c82bb6948010f796e801735c8786603b1d06390080265a2d324ff2cba` |
| `window_median` manifest | `f7d9c619cda537800f777523434a4c22925156628ecfad17ad02fac7656c30fd` |
| external-check manifest | `92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868` |
| external source registry | `6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49` |

## Reproducible counts

```text
raw FIRMS                       = 1532
processed FIRMS                 = 1185
r1500_t06                       = 611
singletons                      = 344
multi                           = 267
possible_chain_merge            = 17
pilot events                    = 30
observable                      = 28
unobserved                      = 2
formal human observations       = 0
external references             = 2
external source documents       = 7
official Picachos matches       = 0
official Guacamaya matches      = 6
```

## External results

- Los Picachos: official window 2025-01-15–17, `<=5 km`, **0 matches**.
- Guacamaya: official window 2025-01-23–27, `<=5 km`, **6 matches**.
- Los Picachos diagnostic category: `SPATIAL_THRESHOLD_MISS`.
- Closest contemporaneous processed detection: 10,400.826 m, 2025-01-15
  18:47Z, FRP 7.47 MW, satellite N20, day.
- Guacamaya: six distinct clusters, first-to-last span 72.733 h, and five
  inter-cluster gaps greater than the frozen 6 h window.

## Validation evidence

```text
targeted post-edit tests              = 23 passed in 3.65 s
new provenance tests                   = 7 passed
full suite before edits                = 288 passed in 546.15 s
full suite after edits                 = 295 passed in 542.20 s
external verifier                     = OK; read_only=true
formal verifier                      = OK; 28 observable, 2 unobserved, 56 assignments
window_median verifier               = pass; 7 events, Pass A=0, Pass B=0
final bundle verifier                 = OK; 13 manifest files, 6 PNGs
git diff --check                      = clean
protected artifact changed_count     = 0
```

The protected comparison covered FIRMS inputs/processed tables, frozen
clustering outputs, Sentinel-2 inventories, selected-pair and dNBR metrics,
formal SQLite and manifests, the `window_median` bundle and the external-check
bundle. No visual-index file exists in this checkout; no visual index was
created or changed.

## Freeze state

```text
DETECTION PIPELINE                 = complete for pilot
OPTICAL FOLLOW-UP                  = complete for pilot
CALIBRATION                        = complete
FORMAL REVIEW INFRASTRUCTURE      = complete; execution deferred
EXTERNAL REFERENCE CHECK           = complete
EXTERNAL REFERENCE PROVENANCE      = complete; 7 sources / 2 incidents
SUPERVISED MODELING                = deferred
ENVIRONMENTAL FEATURES             = deferred
PUBLIC UI                          = not part of pilot
```

## Limitations and stopping condition

This checkpoint does not create ground truth, targets, `significant_burn`, a
model, an operational alert, severity validation or institutional accuracy.
FIRMS detections and clusters remain provisional; `unobserved` is not a
negative; Guacamaya fragmentation is a representation hypothesis; and the
external references now have a canonical seven-source registry but remain
administrative evidence, not ground truth or institutional validation. The
Guacamaya area discrepancy (1,035 to 1,500 ha) and suspected intentionality
are preserved without adjudication. Matching coordinates remain approximate
researcher-provided anchors and are not claimed by the source articles. The
formal review remains deferred because a qualified reviewer is unavailable.
The requested commit is the stopping point; no push or publication is
performed.
