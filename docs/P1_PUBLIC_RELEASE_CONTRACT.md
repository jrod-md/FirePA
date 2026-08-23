# FirePA Public Release Contract v1

**Contract version:** firepa-public-release-v1
**Scientific product:** FirePA Scientific Pilot v1
**Scientific freeze commit:** 7694da7df5808911de48de84016759c5fd22f176
**Generator:** scripts/build_public_release.py
**Verifier:** scripts/verify_public_release_package.py
**Network/Earth Engine:** not used by generation or consumption

## Purpose and boundary

This contract defines a deterministic, frontend-agnostic public projection of
the frozen FirePA v1 artifacts. It is suitable for a later static research
website, scientific report and public repository.

It is not a new scientific result, operational map, alerting system, predictor,
validated classifier or emergency dashboard. The scientific unit is always
provisional thermal event. The frozen total is 611 provisional thermal events.

The package has no backend, database server, SQLite dependency, Earth Engine
dependency, network dependency, paid API dependency or secret environment
variable at consumption time.

## Public package tree

~~~text
site-data/
  project-summary.json
  events.geojson
  external-references.geojson
  guacamaya-timeline.json
  methodology.json
  citations.json
  provenance.json
  manifest.json
  figures/
    01_pipeline_overview.png
    02_cluster_distribution.png
    03_external_reference_map.png
    04_guacamaya_timeline.png
    05_guacamaya_frp_distribution.png
    06_los_picachos_diagnostic.png
~~~

The manifest lists every file except manifest.json itself. The manifest is
generated last and records path, byte size and SHA-256 for each listed file.

## Common serialization rules

- JSON is UTF-8, pretty-printed with stable sorted keys and a final LF.
- No wall-clock generation timestamp is written into deterministic payloads.
- JSON arrays are sorted when their order has no scientific meaning.
- Event records are ordered by the deterministic public event ID.
- Guacamaya timeline records follow the frozen source chronology.
- Dates and timestamps are ISO-8601 strings.
- Timestamps from FIRMS/Sentinel-2 source tables retain UTC semantics and end
  in Z.
- Public numbers are JSON numbers. Descriptive decimal values are serialized
  to six decimal places where the generator rounds them; the operation does
  not recalculate the metric.
- Null means the frozen source has no applicable value; it is not converted to
  zero, false or a negative.
- GeoJSON coordinates are WGS84 longitude/latitude in [longitude, latitude]
  order, with six decimal places.
- All public paths are repository-relative package paths. Absolute filesystem
  paths are forbidden.

## project-summary.json

Top-level allowlist:

- package_version
- project
- definition
- scientific_freeze_commit
- study_area
- period
- frozen_counts
- external_reference_summary
- public_package_scope
- limitations
- files

frozen_counts contains exactly:

~~~text
firms_raw_detections
firms_processed_detections
configuration_id
provisional_thermal_events
singletons
multi_detection_events
possible_chain_merge_events
optical_cohort_events
optically_observable_events
unobserved_events
formal_human_observations
external_incidents
external_source_documents
~~~

external_reference_summary contains the two incident-level invariants and
their public-safe values. public_package_scope states that this is a static
derived projection and that P2/frontend work has not started.

The limitations array may explain unsupported capabilities, including that
FirePA does not provide confirmed wildfire classification, ground truth,
supervised prediction, severity estimation, operational monitoring or realtime
alerts. Those phrases are limitations, never data fields or positive claims.

## events.geojson

The file is an RFC 7946-style FeatureCollection with exactly 611 Features.
Each feature has a Point geometry derived from the frozen centroid fields:

- source: outputs/clustering/r1500_t06/events.csv;
- longitude: centroid_longitude;
- latitude: centroid_latitude;
- coordinate semantics: WGS84 display point, not a burn perimeter.

Every feature has exactly these properties:

~~~text
public_event_id
configuration_id
start_time_utc
end_time_utc
duration_hours
detection_count
source_count
satellite_count
satellites
frp_min_mw
frp_max_mw
frp_mean_mw
frp_median_mw
frp_sum_mw
day_fraction
night_fraction
daynight_known_count
possible_chain_merge
optical_cohort_status
~~~

public_event_id is assigned as evt-0001 through evt-0611 by lexical ordering
of the frozen source event IDs. The source event ID is not published. This
mapping is stable for the same frozen source table and has no scientific
meaning.

optical_cohort_status has only:

- not_in_cohort for the 581 events outside the frozen optical cohort;
- observable for the 28 cohort events with optical support;
- unobserved for the 2 explicitly unobserved cohort events.

The event layer does not include raw detections, confidence, source filenames,
private hashes, scene IDs, AOI/raster information, NBR/dNBR metrics, review
fields, target fields, predictions, severity, fire probability or ground truth.

## external-references.geojson

The file is a FeatureCollection with exactly two Point Features. Geometry is
the approximate researcher-provided matching anchor, not a coordinate claimed
by a source article.

Every feature has exactly these properties:

~~~text
reference_id
reference_name
reference_location
anchor_status
coordinate_claimed_by_source
official_window_start
official_window_end
official_matching_radius_m
source_document_count
source_ids
official_match_count
matched_cluster_count
matched_public_event_ids
temporal_span_hours
inter_cluster_gaps_gt_6h
fragmentation_possible
diagnostic
nearest_documented_contemporary_signal_m
~~~

Required invariant values:

- Los Picachos: 0 official matches, matched_cluster_count 0,
  diagnostic SPATIAL_THRESHOLD_MISS, nearest signal 10400.826 m.
- Guacamaya: 6 official matches, 6 matched clusters, 72.733 hours,
  5 inter-cluster gaps greater than 6 hours, fragmentation_possible true.

The six Guacamaya clusters remain separate. The layer does not claim physical
continuity and does not say that zero Picachos matches means no fire.

## guacamaya-timeline.json

Top-level allowlist:

- package_version
- reference_id
- timeline_window
- temporal_span_hours
- inter_cluster_gaps_gt_6h
- clusters

clusters contains exactly six objects with:

~~~text
order
public_event_id
cluster_start_utc
cluster_end_utc
gap_from_previous_hours
detection_count
max_frp_mw
mean_frp_mw
satellites
day_count
night_count
possible_chain_merge
~~~

The objects remain ordered by the frozen timeline. No intermediate activity is
invented and no cluster is merged.

## methodology.json

methodology.json is a concise structured presentation of frozen method and
limits. It includes:

- the FirePA definition and scientific unit;
- study period and area;
- FIRMS acquisition/audit;
- r1500_t06 provisional clustering;
- Sentinel-2 cohort and observable/unobserved semantics;
- selected_pair and window_median as distinct descriptive evidence modes;
- NBR/dNBR descriptive role;
- external reference matching rule;
- formal review deferred state;
- supervised modeling deferred state;
- source-relative artifact references;
- limitations.

It does not serialize a new scientific report, new target, class, severity,
model output, ground truth or operational capability.

## citations.json

Top-level allowlist:

- package_version
- registry
- scientific_sources
- external_sources

registry contains the exact canonical registry path, source count, incident
count and SHA-256. scientific_sources contain source-relative frozen document
paths and hashes where used. external_sources contain the seven canonical
source records with safe publication metadata:

- source_id
- incident_id
- publisher
- publisher_type
- publication_date
- reported event date fields
- reported_location
- reported_area_ha
- reported_area_qualifier
- cause_status
- url

Researcher summaries and internal provenance JSON blobs are excluded.

## provenance.json

Top-level allowlist:

- package_version
- scientific_freeze_commit
- generator
- network_access
- earth_engine_queries_made
- source_artifacts
- transformations
- output_hashes
- figure_provenance
- protected_artifacts
- public_private_boundary

source_artifacts is an ordered array of exactly eleven records. Each record has
exactly `path`, `role`, `size_bytes` and `sha256`; paths are repository-relative
and roles are fixed, concise, non-sensitive labels:

- `outputs/clustering/r1500_t06/events.csv` — canonical provisional-event table
- `outputs/clustering/r1500_t06/summary.json` — clustering summary
- `data/processed/firms_cocle_2025_detections.csv` — processed FIRMS count source
- `data/processed/sentinel2_observability_pilot_events.csv` — optical cohort membership
- `outputs/human_review/unobserved_events.csv` — unobserved cohort status
- `outputs/external_reference_check_v1/matches.csv` — external match rows
- `outputs/external_reference_check_v1/reference_summary.csv` — external reference summary
- `outputs/final_scientific_report/guacamaya_timeline.csv` — Guacamaya timeline source
- `outputs/final_scientific_report/picachos_temporal_top10.csv` — Los Picachos diagnostic source
- `references/external_reference_sources_v1.json` — canonical external source registry
- `outputs/final_scientific_report/manifest.json` — frozen final-report manifest

transformations explain allowlist projection, public ID mapping, optical status
join, numeric serialization, external-reference projection and byte-preserving
figure copy.

output_hashes covers public files other than provenance.json and manifest.json.
The manifest records provenance.json and all other package output hashes. This
avoids a self-hash cycle while preserving complete machine-readable output
integrity.

protected_artifacts records expected frozen source hashes used by the verifier.
A mismatch fails P1 verification; the generator never repairs or rewrites the
source.

figure_provenance is an array of six records, one per public figure. Each record
has exactly `source_path`, `source_sha256`, `derivative_path`,
`derivative_sha256`, `transformation`, `width`, `height`, `size_bytes` and
`scientific_content_recomputed`. The transformation is
`copy-byte-identical`, dimensions are 1600 by 900, and the recomputation flag
is false.

## figures

The six final scientific report PNGs are copied byte-for-byte from the frozen
local report bundle. Their source path, source SHA-256, derivative path,
derivative SHA-256, dimensions, size and transformation type are recorded in
provenance.

The transformation type is copy-byte-identical. No scientific figure is
redrawn, cropped, recolored, retouched, resized or numerically recomputed.

Rasters, review panels, SQLite, formal assignments, blind packages, private
mappings, raw detection exports and internal SVG/JSON diagnostics are not
public package files.

## Determinism

A build from the same frozen checkout and the same output path-independent
inputs must produce byte-identical files. The generator has no random UUID,
current timestamp, hostname, username, current-working-directory value,
network request or filesystem-order dependency.

Focused tests build two independent temporary packages and compare every file
hash and byte sequence. The verifier is read-only and checks the resulting
manifest; it does not rebuild the package.

## Privacy and security

The public package must fail verification if it contains likely user paths,
home paths, usernames in paths, secrets, tokens, credentials, private keys,
service-account material, private seeds, reviewer identity/mapping, SQLite,
private databases, unexpected manifests or environment dumps.

## Scientific wording

Data fields and positive public claims must use provisional thermal event.
The package must never serialize 611 as fires, wildfires or confirmed fires.
Forbidden scientific concepts such as ground truth, target, prediction,
significant_burn, confirmed_fire, validated_fire, severity,
fire_probability, wildfire_probability and model_output are not public schema
keys. Negative limitation wording is allowed only in explicitly labelled
limitations or scope fields.
