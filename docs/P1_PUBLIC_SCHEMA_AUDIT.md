# P1 — Public Schema Audit

**Audit version:** firepa-public-schema-audit-v2
**Audit date:** 2026-08-10
**Scientific freeze:** 7694da7df5808911de48de84016759c5fd22f176
**Scope:** schema inspection only; no scientific source was recomputed or modified.

## Audit result

The public package uses an allowlist-first projection of frozen local artifacts.
It does not copy rows wholesale. The public event geometry is the frozen event
centroid, represented as a WGS84 GeoJSON Point. No event polygon, raw
detection geometry, raster, private review mapping, or database content is
published.

The frozen event identifier is a deterministic hash-like pipeline identifier.
It contains no user, reviewer, credential, or filesystem information. The
public package does not expose it directly: the generator assigns evt-0001
through evt-0611 after lexical ordering of the frozen source event IDs. This
mapping is deterministic and has no scientific meaning.

## Provenance schema addendum

The P1 provenance contract includes `figure_provenance` in its top-level
allowlist. It contains six exact figure records with source and derivative
paths, both SHA-256 hashes, byte-preserving transformation metadata, dimensions,
size and an explicit `scientific_content_recomputed: false` flag.

`source_artifacts` contains exactly eleven ordered records. Each record has only
`path`, `role`, `size_bytes` and `sha256`; the role is a fixed factual label
defined in `P1_PUBLIC_RELEASE_CONTRACT.md`. The dedicated verifier checks the
top-level provenance allowlist, source-record schema and role/path mapping.

## Inspected source artifacts

| Source artifact | Observed schema/state | P1 use |
|---|---|---|
| outputs/clustering/r1500_t06/events.csv | 611 rows; one row per r1500_t06 cluster; centroid latitude/longitude, UTC bounds, detection counts, source/satellite composition, FRP summaries, day/night fractions, possible_chain_merge. | Canonical event projection and public geometry. |
| outputs/clustering/r1500_t06/summary.json | r1500_t06, 1,185 detections, 611 events, 344 singletones, 267 multi-detection events, 17 possible chain merges; EPSG:32617 is the clustering metric. | Frozen method/count cross-check. |
| data/raw/*.csv | 48 local FIRMS fragments; 1,532 data rows by line-aware CSV parsing. | Raw count only; raw rows are not published. |
| data/processed/firms_cocle_2025_detections.csv | 1,185 processed detections; detection-level identifiers, coordinates, timestamps, source, satellite, FRP and raw-file provenance. | Processed count only; detection-level rows and raw-file fields are excluded. |
| data/processed/sentinel2_observability_pilot_events.csv | 30 event IDs defining the frozen optical cohort. | Cohort membership cross-check. |
| data/interim/sentinel2_observability.csv | 1,440 rule/AOI/combination rows; canonical source includes observability_status and usable_pair_exists. | Not copied. The public status is derived only for the frozen 30-event cohort. |
| outputs/human_review/unobserved_events.csv | Two explicit unobserved event IDs. | Maps two cohort events to unobserved; never treated as negative. |
| data/interim/sentinel2_dnbr_event_metrics.csv | Selected-pair and window-median descriptive metric rows, scene IDs, paths, processing metadata and NBR/dNBR fields. | Not exposed in event records; methodology states the evidence modes and limits. |
| outputs/external_reference_check_v1/matches.csv | Six Guacamaya match rows with distances, time overlap, FRP summaries and an internal provenance JSON containing absolute paths. | Explicit safe fields only; internal provenance field is excluded. |
| outputs/external_reference_check_v1/reference_summary.csv | Two reference rows, zero Picachos matches, six Guacamaya matches, fragmentation note. | Public reference counts/status and Guacamaya invariant. |
| outputs/final_scientific_report/guacamaya_timeline.csv | Six chronologically ordered matched clusters, gaps, counts, FRP summaries and day/night counts. | Public Guacamaya timeline derivative. |
| outputs/final_scientific_report/picachos_temporal_top10.csv | Contemporary Picachos diagnostic candidates; nearest distance is 10,400.82589957 m. | Rounded public diagnostic value 10,400.826 m. |
| references/external_reference_sources_v1.json | Two approximate matching anchors and seven source records; canonical registry SHA-256 is fixed. | Public incident anchors and citation projection. |
| outputs/final_scientific_report/manifest.json | Six final scientific PNGs plus diagnostic data; all local report files are hashed. | Six PNGs copied unchanged; diagnostic JSON/CSV is not copied. |
| docs/FIREPA_PILOT_V1_FREEZE.md and checkpoints | Freeze boundary, protected hashes, methods and limits. | Contract and verifier authority. |

## Public event field ledger

The public event properties are exactly the following keys:

| Public field | Type/unit | Source field(s) | Stored or derived | Decision |
|---|---|---|---|---|
| public_event_id | string | events.csv.event_id | Derived deterministic ordinal after lexical sort | Public. No scientific meaning. |
| configuration_id | string | events.csv.configuration_id | Stored | Public method context; must be r1500_t06. |
| start_time_utc | string, ISO-8601 UTC | start_timestamp_utc | Renamed | Public temporal bound. |
| end_time_utc | string, ISO-8601 UTC | end_timestamp_utc | Renamed | Public temporal bound. |
| duration_hours | number, hours | duration_hours | Stored, rounded to 6 decimals for serialization | Public descriptive duration. |
| detection_count | integer | detection_count | Stored | Public count; not a fire count. |
| source_count | integer | source_count | Stored | Public sensor-source count. |
| satellite_count | integer | satellite_count | Stored | Public composition count. |
| satellites | array of strings | satellites | Parsed JSON array, sorted | Public N/N20 composition. |
| frp_min_mw | number, MW | frp_min | Renamed, rounded to 6 decimals | Public descriptive FIRMS attribute; not severity. |
| frp_max_mw | number, MW | frp_max | Renamed, rounded to 6 decimals | Public descriptive FIRMS attribute; not severity. |
| frp_mean_mw | number, MW | frp_mean | Renamed, rounded to 6 decimals | Public descriptive FIRMS attribute; not severity. |
| frp_median_mw | number, MW | frp_median | Renamed, rounded to 6 decimals | Public descriptive FIRMS attribute; not severity. |
| frp_sum_mw | number, MW | frp_sum | Renamed, rounded to 6 decimals | Public descriptive FIRMS attribute; not severity. |
| day_fraction | number, fraction [0,1] | day_fraction | Stored, rounded to 6 decimals | Public day/night composition. |
| night_fraction | number, fraction [0,1] | night_fraction | Stored, rounded to 6 decimals | Public day/night composition. |
| daynight_known_count | integer | daynight_known_count | Stored | Public denominator context. |
| possible_chain_merge | boolean | possible_chain_merge | Stored | Public representation limitation flag. |
| optical_cohort_status | enum | cohort CSV + unobserved_events.csv | Derived allowlisted join | observable, unobserved, or not_in_cohort. |

### Event fields intentionally excluded

- raw detection rows, detection IDs, raw filenames and raw file hashes;
- raw confidence fields and confidence_counts;
- chain merge reason text and internal graph details;
- bounding boxes and clustering projection coordinates;
- internal source event IDs and any reviewer-facing aliases;
- Sentinel-2 scene IDs, local paths, AOI geometry, raster metadata and NBR/dNBR
  values;
- selected-pair/window-median metrics and review panels;
- formal review assignments, reviewer identities, private seeds and SQLite;
- any target, class, severity, probability, prediction or ground-truth field.

The exclusions keep the package event-level, static-consumable and traceable
without publishing raw detection data or private scientific/administrative
internals.

## External-reference field ledger

external-references.geojson contains exactly two Point features using the
researcher-provided approximate anchors from the canonical registry.

Public properties are:

- reference_id, reference_name, reference_location;
- anchor_status and coordinate_claimed_by_source;
- official_window_start, official_window_end,
  official_matching_radius_m;
- source_document_count and source_ids;
- official_match_count, matched_cluster_count,
  matched_public_event_ids;
- temporal_span_hours, inter_cluster_gaps_gt_6h,
  fragmentation_possible;
- diagnostic and nearest_documented_contemporary_signal_m.

The projection preserves the distinction between an externally reported
incident, an approximate matching anchor, a FirePA provisional event and an
exploratory relational match. It does not call the zero Picachos result
absence of fire.

## Timeline and citation audit

guacamaya-timeline.json contains six separate matched clusters in source
chronological order. It preserves five gaps greater than the frozen six-hour
window and does not merge the clusters.

citations.json includes seven source IDs from the canonical registry with
publisher, publication date, incident, reported location/date fields, source
area qualifiers, cause status and URL. It omits researcher summaries and
internal provenance blobs containing absolute local paths. No new OSINT is
performed.

## Asset audit

The six final scientific report PNGs are safe to publish unchanged:

- 1600 × 900 pixels;
- no PNG text, iTXt or zTXt metadata chunks observed;
- source hashes are recorded in the package provenance and manifest;
- the generator copies bytes; it does not redraw, recolor, crop or recompute.

The following are intentionally excluded:

- raw FIRMS CSV fragments and processed detection-level CSV;
- GeoTIFF rasters and AOI/scene inventories;
- per-event selected-pair/window-median review panels;
- formal-review SQLite, assignments, blind packages, private seeds and mappings;
- external-check SVG diagnostics and JSON reports with local paths;
- the scientific report diagnostic JSON/CSVs, which contain machine-specific
  source strings and internal analytical detail.

## Ambiguity decisions

1. Event geometry is a centroid Point because the frozen event table provides
   centroid coordinates and no public event polygon. The centroid is not a
   burn perimeter.
2. The 30-event optical status is linked by the frozen event ID only inside the
   generator. The public layer uses a deterministic status enum and no source
   event ID.
3. Numeric values are rounded only for stable public serialization; no metric
   is recomputed or reclassified.
4. The package contains presentation-ready scientific figures but no
   event-level review output. selected_pair and window_median remain
   descriptive evidence modes documented in methodology.

## P1 safety conclusion

The selected schema is small, explicit and traceable. The package can be
generated without network, Earth Engine, SQLite, backend services, paid APIs,
scientific recomputation or frontend assumptions.
