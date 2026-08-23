# FirePA scientific pilot report

**Scientific version:** FirePA Scientific Pilot v1
**Study area:** Coclé, Panama
**Study window:** 2025-01-01 to 2025-04-30, inclusive, UTC
**Scientific freeze:** `7694da7df5808911de48de84016759c5fd22f176`

## Abstract

FirePA evaluates how satellite thermal detections can be reduced into
reproducible provisional analytical units and compared with descriptive optical
and external evidence without converting those signals into confirmed wildfire
claims. The pilot audits 1,532 NASA FIRMS raw detections, retains 1,185 valid
detections inside Coclé, and groups them with the frozen `r1500_t06`
spatiotemporal connected-components configuration. The result is 611
provisional thermal events: 344 singletons, 267 multi-detection events, and 17
cases flagged `possible_chain_merge`.

A frozen Sentinel-2 cohort contains 30 events. Twenty-eight are observable
under the optical policy and two remain `unobserved`; those two are not
negative cases. NBR and dNBR are retained as descriptive evidence only. Formal
human observations equal zero, no ground truth exists, and no supervised model
or severity classification was produced.

Two external-reference comparisons preserve an inclusive 5,000 m rule. Cerro
Guacamaya has six matched provisional clusters separated by five gaps greater
than six hours over 72.733 hours, supporting
`fragmentation_possible = true` while preserving all six clusters separately.
Cerro Los Picachos has zero official matches; the nearest documented
contemporary signal is 10,400.826 m away, so the result is
`SPATIAL_THRESHOLD_MISS`, not absence of fire, activity, or thermal signal.

The pilot is static, descriptive, and reproducible within its public boundary.
It is not real-time, operational, predictive, or validated ground truth.

## 1. Research question and objectives

The research question is: **Can thermal signals tell us what happened on the
ground?** The pilot addresses that question through four bounded objectives:

1. audit and spatially filter a historical FIRMS cohort;
2. construct reproducible provisional thermal-event units;
3. describe a frozen optical follow-up cohort without creating labels; and
4. compare the frozen units with limited external incident references while
   making threshold and representation failures explicit.

The objective is not to build an operational fire product or prove event truth.

## 2. Study area and study window

The study area is Coclé, Panama. The FIRMS acquisition and processing window is
2025-01-01 through 2025-04-30, inclusive, in UTC. The validated local
administrative boundary was transformed from `EPSG:32617` to `EPSG:4326` for
spatial filtering and presentation. The source boundary is not redistributed;
the public site uses a deterministic presentation derivative.

## 3. FIRMS acquisition and audit

The local workflow used NASA FIRMS VIIRS historical detections. It verified
source availability, split requests into bounded temporal fragments, preserved
raw bytes and manifests locally, validated required fields, and filtered by
time and the Coclé geometry.

| Stage | Count |
|---|---:|
| Audited raw detections | 1,532 |
| Valid schema/date/coordinate records | 1,532 |
| Detections inside the requested period | 1,532 |
| Processed detections inside Coclé | 1,185 |

The difference between 1,532 and 1,185 is the spatial study-area filter. FIRMS
rows are thermal-anomaly observations; multiple rows can describe the same
analytical event, and one row is not automatically one confirmed fire.

## 4. Spatiotemporal processing

The frozen configuration `r1500_t06` applies connected components with a
1,500 m spatial threshold, a six-hour UTC temporal threshold, and metric
distance in `EPSG:32617`. Edges use coordinates and time only. FRP, satellite,
instrument, confidence, source, and day/night status remain descriptive.

| Result | Count |
|---|---:|
| Provisional thermal events | 611 |
| Singleton events | 344 |
| Multi-detection events | 267 |
| `possible_chain_merge` | 17 |

## 5. Provisional event definition

A provisional thermal event is a connected group under `r1500_t06`. It is an
analytical unit, not a claim that a single ignition, continuous incident, burn
scar, or confirmed wildfire occurred. The term remains provisional because the
pilot has no ground-truth adjudication.

Connected components can join observations through chains or split prolonged
activity when temporal gaps exceed six hours. The
`possible_chain_merge` field is a review flag, not a corrected class.

## 6. Sentinel-2 follow-up and optical observability

The structural optical cohort contains 30 frozen events. Under the Sentinel-2
and Cloud Score+ policy, 28 are observable and two remain `unobserved`.
`Unobserved` means no usable support under the policy; it does not mean no fire
or no land-surface change.

The project retains `selected_pair` and `window_median` as separate evidence
modes. The seven-case `window_median` technical pilot passed its integrity
checks, but it was not connected to formal review assignments and does not
replace `selected_pair`.

## 7. NBR and dNBR boundary

The optical contract uses:

```text
NBR  = (B8 - B12) / (B8 + B12)
dNBR = NBR_pre - NBR_post
```

B8 and B12 are evaluated on common 20 m support. The indices are descriptive
and may respond to cloud, haze, phenology, moisture, agriculture, soil, water,
and other changes. No `significant_burn` target, severity class, or validated
burn-scar label was created.

## 8. Formal review and predictive modeling

Formal review infrastructure was prepared, but execution was deferred because
a qualified reviewer was unavailable:

```text
execution_authorized = false
formal_human_observations = 0
```

Historical automated-review calibration outputs remain provisional
pseudolabel evidence. They are not human observations, ground truth, training
targets, or accuracy estimates. No supervised predictive model was trained.

## 9. External-reference methodology

The external registry contains seven documents describing two incidents. It
preserves each publisher's date, area, and cause claims without adjudicating a
single true value. Matching coordinates are approximate researcher-provided
anchors and are not attributed to the articles.

The comparison reads the 611 frozen events without reclustering. A match must
satisfy inclusive temporal overlap and distance `<= 5,000 m`. External sources
are relational context, not ground truth, pipeline inputs, or model targets.

## 10. Quantitative results

The complete frozen reduction is:

```text
1,532 raw FIRMS detections
  -> 1,185 processed detections
  -> 611 provisional thermal events
  -> 30-event optical cohort
  -> 28 observable + 2 unobserved
```

Formal human observations remain zero. The external registry contains seven
documents and two incidents.

## 11. Cerro Guacamaya

The official 2025-01-23 to 2025-01-27 comparison returns six matched
provisional clusters within the inclusive 5,000 m radius. They contain 2, 4,
3, 5, 1, and 4 detections. One cluster is flagged
`possible_chain_merge`; that flag does not change the six-unit result.

The first matched cluster begins 2025-01-24 06:11Z and the last ends
2025-01-27 06:55Z, an overall span of 72.733 hours. The five inter-cluster gaps
are 12.383, 23.300, 10.933, 11.083, and 12.617 hours; every gap exceeds the
six-hour clustering window.

The frozen interpretation is `fragmentation_possible = true`: prolonged
documented activity may correspond to multiple FirePA events. This is a
representation limitation, not proof that the clustering is wrong and not
authorization to merge the six provisional units into one continuous incident.

## 12. Cerro Los Picachos

The official 2025-01-15 to 2025-01-17 comparison returns zero matches within
the inclusive 5,000 m radius. The nearest contemporary frozen event is
10,400.826 m from the approximate anchor. The processed detection audit finds
zero detections within 5 km, zero within 10 km, and one within 15 km; extending
the date window to 2025-01-13 through 2025-01-19 does not change the 5 km
result.

The frozen diagnosis is `SPATIAL_THRESHOLD_MISS`. It means the available
contemporary signal falls outside the official threshold. It must not be
translated into no fire, no activity, no thermal signal, or absence of an
event.

## 13. Scientific limitations

- FIRMS anomalies do not independently confirm wildfires.
- `r1500_t06` is an analytical convention, not ground truth.
- Event centroids are not burn perimeters or precision ground locations.
- Optical observability and NBR/dNBR do not create negative cases or severity.
- Formal human observations equal zero.
- There is no ground truth, institutional validation, predictive model, or
  accuracy estimate.
- External references are limited, manually located, and non-exhaustive.
- The Guacamaya comparison may expose temporal fragmentation.
- The Picachos zero is a threshold result only.
- Findings are limited to Coclé and the frozen 2025 study window.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the full inference boundary.

## 14. Reproducibility and public package

The public package in `site-data/` exposes 611 event centroids, two reference
anchors, the Guacamaya timeline, methodology, citations, provenance, and six
byte-frozen figures. `manifest.json` records deterministic hashes. The public
package excludes raw detection rows, local rasters, private review identities
and mappings, SQLite, secrets, and absolute paths.

A clean clone can build and test the bilingual static publication and verify
the public package. Full scientific regeneration requires excluded source
inputs and, for remote optical acquisition, authorized external services. No
synthetic replacement is permitted. See
[`DATA_AND_REPRODUCIBILITY.md`](DATA_AND_REPRODUCIBILITY.md).

## 15. Provenance

Scientific source and transformation records are in
`site-data/provenance.json`; external source claims are in
`references/external_reference_sources_v1.json`; source and licensing
boundaries are in root `SOURCES.md` and `NOTICE.md`. The six frozen figures are
copied byte-for-byte and their hashes are verified by the public site contract.

## 16. Conclusion

FirePA demonstrates a reproducible reduction from thermal signals to
provisional analytical events while preserving uncertainty. Its principal
result is not a wildfire classifier: it is a bounded evidence structure.
Guacamaya shows that a prolonged documented incident can align with multiple
six-hour provisional groups. Los Picachos shows that zero matches within a
threshold is not zero signal. These findings are descriptive relationships
over frozen artifacts, not ground truth, severity, prediction, or operational
validation.

## References

- NASA FIRMS / LANCE Area API and documentation, listed in root `SOURCES.md`.
- Copernicus Sentinel-2 Surface Reflectance Harmonized catalog.
- Google Cloud Score+ catalog.
- Instituto Geografico Nacional Tommy Guardia / ANATI administrative boundary
  source record.
- Seven incident source documents in
  `references/external_reference_sources_v1.json` and
  `site-data/citations.json`.
