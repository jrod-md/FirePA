# Methodology

## Scope

FirePA is a reproducible remote-sensing pilot for detecting, grouping, and
describing provisional thermal events in Coclé, Panama. The study window is
2025-01-01 through 2025-04-30, inclusive, in UTC. The scientific freeze is
`7694da7df5808911de48de84016759c5fd22f176`.

The scientific unit is a **provisional thermal event**. It is not a confirmed
fire, ignition, burned-area perimeter, severity class, prediction, or alert.

## 1. FIRMS acquisition and audit

The local acquisition used NASA FIRMS VIIRS historical sources. Each requested
source/time fragment was recorded with a manifest and hash. The audit began
with 1,532 raw records and retained 1,185 detections with valid schema,
coordinates, timestamps, study dates, and locations inside the validated Coclé
boundary.

The public repository does not include raw FIRMS rows or credentials. The
processed count and protected input hashes are recorded in the public package
provenance.

## 2. Spatiotemporal grouping

The frozen configuration is `r1500_t06`:

- connected components;
- spatial link distance `<= 1,500 m`;
- temporal link difference `<= 6 h`;
- metric calculations in `EPSG:32617`;
- links determined only from coordinates and UTC timestamps.

FRP, confidence, source, satellite, instrument, and day/night status are
descriptive attributes and do not create links. The 1,185 processed detections
produce 611 provisional thermal events: 344 singletons, 267 multi-detection
events, and 17 events flagged `possible_chain_merge`.

Connected components can chain observations. The flag identifies a review
condition; it is not a confirmed merge error or fire class.

## 3. Sentinel-2 optical follow-up

A frozen structural cohort contains 30 events. Sentinel-2 Surface Reflectance
Harmonized and Cloud Score+ were used under the documented observability
policy. Twenty-eight events were observable and two remained `unobserved`.

`Unobserved` means the policy did not obtain usable optical support. It is not
a negative class and does not mean no fire or no land-surface change.

The optical evidence modes remain distinct:

- `selected_pair`: one selected pre/post pair under the frozen policy;
- `window_median`: a separate seven-case technical pilot using local numeric
  bundles and per-band temporal medians.

The seven-case `window_median` pilot passed its technical integrity checks but
was not connected to formal review assignments and does not replace
`selected_pair`.

## 4. NBR and dNBR boundary

The descriptive indices use:

```text
NBR  = (B8 - B12) / (B8 + B12)
dNBR = NBR_pre - NBR_post
```

The frozen contract evaluates B8/B12 on common 20 m support. NBR/dNBR can be
affected by cloud, haze, phenology, moisture, agriculture, exposed soil, water,
and other land-surface changes. No severity classification,
`significant_burn` label, or truth target was produced.

## 5. Formal review and modeling

The formal 28-event review infrastructure was prepared but execution was
deferred because a qualified reviewer was unavailable:

```text
execution_authorized = false
formal_human_observations = 0
```

No supervised predictive model was trained because the pilot has no defensible
target or ground truth. A seven-case blind model-assisted calibration tested the
review instrument, followed by a two-reviewer control. Both were exploratory:
their outputs remained provisional pseudolabel evidence and were not human
observations, targets, accuracy estimates, model validation, or inputs to the
frozen release. The method, aggregate findings, and public/private boundary are
documented in
[`MODEL_ASSISTED_CALIBRATION.md`](MODEL_ASSISTED_CALIBRATION.md).

## 6. External-reference comparison

The comparison reads the 611 frozen events without reclustering. A match must
satisfy both:

1. inclusive temporal overlap with the reference window; and
2. metric distance `<= 5,000 m` from the approximate reference anchor.

The anchors were provided by the researcher and are explicitly approximate;
the source articles are not claimed to provide those coordinates. The source
registry contains seven documents describing two incidents. It is relational
context, not ground truth.

The official results are:

- Cerro Los Picachos: zero matches, nearest documented contemporary signal
  10,400.826 m, diagnostic `SPATIAL_THRESHOLD_MISS`;
- Cerro Guacamaya: six matches preserved as six separate provisional clusters,
  72.733 h total span, five inter-cluster gaps greater than six hours, and
  `fragmentation_possible = true`.

The Guacamaya result is a representation limitation: a prolonged documented
incident may map to multiple `t06` groups. The comparison does not merge those
groups or prove they form one continuous fire.

## 7. Public projection

The public release maps frozen event identifiers to public IDs, publishes WGS84
centroids, rounds values only for deterministic serialization, and copies the
six scientific figures byte-for-byte. It does not recalculate clusters,
distances, optical metrics, or scientific figures.

Implementation details and protected-artifact hashes are in
[`DATA_AND_REPRODUCIBILITY.md`](DATA_AND_REPRODUCIBILITY.md). The inference
boundary is in [`LIMITATIONS.md`](LIMITATIONS.md).
