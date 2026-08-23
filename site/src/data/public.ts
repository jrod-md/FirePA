import projectSummaryRaw from "../../../site-data/project-summary.json?raw";
import eventsRaw from "../../../site-data/events.geojson?raw";
import externalReferencesRaw from "../../../site-data/external-references.geojson?raw";
import guacamayaTimelineRaw from "../../../site-data/guacamaya-timeline.json?raw";
import methodologyRaw from "../../../site-data/methodology.json?raw";
import citationsRaw from "../../../site-data/citations.json?raw";
import provenanceRaw from "../../../site-data/provenance.json?raw";
import manifestRaw from "../../../site-data/manifest.json?raw";

export interface FrozenCounts {
  configuration_id: string;
  external_incidents: number;
  external_source_documents: number;
  firms_processed_detections: number;
  firms_raw_detections: number;
  formal_human_observations: number;
  multi_detection_events: number;
  optical_cohort_events: number;
  optically_observable_events: number;
  possible_chain_merge_events: number;
  provisional_thermal_events: number;
  singletons: number;
  unobserved_events: number;
}

export interface Period {
  start: string;
  end: string;
  inclusive: boolean;
  timezone: string;
}

export interface ProjectSummary {
  definition: string;
  external_reference_summary: {
    guacamaya: {
      inter_cluster_gaps_gt_6h: number;
      matched_provisional_clusters: number;
      official_matches: number;
      temporal_span_hours: number;
    };
    los_picachos: {
      diagnostic: string;
      nearest_documented_contemporary_signal_m: number;
      official_matches: number;
    };
    registry_sha256: string;
  };
  files: string[];
  frozen_counts: FrozenCounts;
  limitations: string[];
  package_version: string;
  period: Period;
  project: string;
  public_package_scope: {
    backend_required: boolean;
    earth_engine_required: boolean;
    frontend_agnostic: boolean;
    network_required: boolean;
    p2_started: boolean;
    projection: string;
  };
  scientific_freeze_commit: string;
  study_area: string;
}

export interface PublicEventProperties {
  configuration_id: string;
  day_fraction: number | null;
  daynight_known_count: number;
  detection_count: number;
  duration_hours: number;
  end_time_utc: string;
  frp_max_mw: number;
  frp_mean_mw: number;
  frp_median_mw: number;
  frp_min_mw: number;
  frp_sum_mw: number;
  night_fraction: number | null;
  optical_cohort_status: "not_in_cohort" | "observable" | "unobserved";
  possible_chain_merge: boolean;
  public_event_id: string;
  satellite_count: number;
  satellites: string[];
  source_count: number;
  start_time_utc: string;
}

export interface PublicEventFeature {
  type: "Feature";
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  properties: PublicEventProperties;
}

export interface PublicEvents {
  type: "FeatureCollection";
  features: PublicEventFeature[];
}

export interface ExternalReferenceProperties {
  anchor_status: "approximate";
  coordinate_claimed_by_source: boolean;
  diagnostic: string | null;
  fragmentation_possible: boolean;
  inter_cluster_gaps_gt_6h: number;
  matched_cluster_count: number;
  matched_public_event_ids: string[];
  nearest_documented_contemporary_signal_m: number | null;
  official_match_count: number;
  official_matching_radius_m: number;
  official_window_end: string;
  official_window_start: string;
  reference_id: string;
  reference_location: string;
  reference_name: string;
  source_document_count: number;
  source_ids: string[];
  temporal_span_hours: number | null;
}

export interface ExternalReferenceFeature {
  type: "Feature";
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  properties: ExternalReferenceProperties;
}

export interface ExternalReferences {
  type: "FeatureCollection";
  features: ExternalReferenceFeature[];
}

export interface GuacamayaCluster {
  cluster_end_utc: string;
  cluster_start_utc: string;
  day_count: number;
  detection_count: number;
  gap_from_previous_hours: number | null;
  max_frp_mw: number;
  mean_frp_mw: number;
  night_count: number;
  order: number;
  possible_chain_merge: boolean;
  public_event_id: string;
  satellites: string[];
}

export interface GuacamayaTimeline {
  clusters: GuacamayaCluster[];
  inter_cluster_gaps_gt_6h: number;
  package_version: string;
  reference_id: string;
  temporal_span_hours: number;
  timeline_window: Period;
}

export interface MethodologyWorkflowItem {
  algorithm?: string;
  configuration_id?: string;
  cohort_events?: number;
  evidence_modes?: string[];
  matching_rule?: string;
  metric_projection?: string;
  observable_events?: number;
  radius_m?: number;
  reclustered?: boolean;
  result: string;
  source_artifacts?: string[];
  stage: string;
  status: string;
  time_window_hours?: number;
  unobserved_events?: number;
}

export interface Methodology {
  definition: string;
  formal_review: {
    execution_authorized: boolean;
    formal_human_observations: number;
    reason: string;
    status: string;
  };
  limitations: string[];
  package_version: string;
  scientific_freeze_commit: string;
  scientific_unit: string;
  source_artifacts: string[];
  study_period: Period;
  supervised_modeling: {
    model_trained: boolean;
    reason: string;
    status: string;
  };
  workflow: MethodologyWorkflowItem[];
}

export interface CitationSource {
  cause_status: string | null;
  incident_id: string;
  publication_date: string;
  publisher: string;
  publisher_type: string;
  reported_area_ha?: number | null;
  reported_area_qualifier?: string;
  reported_event_date?: string;
  reported_event_date_end?: string;
  reported_event_date_start?: string;
  reported_location: string;
  source_id: string;
  url: string;
}

export interface Citations {
  external_sources: CitationSource[];
  package_version: string;
  registry: {
    incident_count: number;
    path: string;
    sha256: string;
    source_count: number;
  };
  scientific_sources: Array<{
    path: string;
    role: string;
    sha256: string;
  }>;
}

export interface FigureProvenance {
  derivative_path: string;
  derivative_sha256: string;
  height: number;
  scientific_content_recomputed: boolean;
  source_path: string;
  source_sha256: string;
  transformation: string;
  width: number;
}

export interface Provenance {
  earth_engine_queries_made: boolean;
  figure_provenance: FigureProvenance[];
  generator: {
    command: string;
    entry_point: string;
    version: string;
  };
  network_access: boolean;
  output_hashes: Array<{
    path: string;
    sha256: string;
    size_bytes: number;
  }>;
  package_version: string;
  public_private_boundary: Record<string, boolean>;
  scientific_freeze_commit: string;
  source_artifacts: Array<{
    path: string;
    role: string;
    sha256: string;
    size_bytes: number;
  }>;
  transformations: string[];
}

export interface Manifest {
  deterministic: boolean;
  files: Array<{
    path: string;
    sha256: string;
    size_bytes: number;
  }>;
  generator_version: string;
  manifest_excludes: string[];
  package_version: string;
  scientific_freeze_commit: string;
}

export const projectSummary = JSON.parse(projectSummaryRaw) as ProjectSummary;
export const counts = projectSummary.frozen_counts;
export const period = projectSummary.period;
export const events = JSON.parse(eventsRaw) as PublicEvents;
export const externalReferences = JSON.parse(externalReferencesRaw) as ExternalReferences;
export const guacamayaTimeline = JSON.parse(guacamayaTimelineRaw) as GuacamayaTimeline;
export const methodology = JSON.parse(methodologyRaw) as Methodology;
export const citations = JSON.parse(citationsRaw) as Citations;
export const provenance = JSON.parse(provenanceRaw) as Provenance;
export const manifest = JSON.parse(manifestRaw) as Manifest;

export const publicEventFields = Object.keys(events.features[0]?.properties ?? {}) as Array<keyof PublicEventProperties>;

if (events.features.length !== counts.provisional_thermal_events) {
  throw new Error("Public event count does not match the frozen project summary.");
}

if (
  counts.optical_cohort_events !== 30 ||
  counts.optically_observable_events !== 28 ||
  counts.unobserved_events !== 2 ||
  guacamayaTimeline.clusters.length !== 6 ||
  guacamayaTimeline.temporal_span_hours !== 72.733 ||
  guacamayaTimeline.inter_cluster_gaps_gt_6h !== 5
) {
  throw new Error("Public optical or external-reference counts do not match the frozen package.");
}

if (externalReferences.features.length !== counts.external_incidents) {
  throw new Error("Public external-reference count does not match the frozen project summary.");
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatDecimal(value: number, maximumFractionDigits = 3): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits, useGrouping: false }).format(value);
}

export function formatExact(value: number, fractionDigits = 3): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits }).format(value);
}

export function formatMeters(value: number): string {
  return `${formatCount(Math.round(value))} m`;
}

export function formatHours(value: number | null, maximumFractionDigits = 3): string {
  return value === null ? "Not applicable" : `${formatDecimal(value, maximumFractionDigits)} h`;
}

export function formatUtc(value: string): string {
  return value.replace("T", " ").replace("Z", " UTC");
}

export function formatStatus(status: PublicEventProperties["optical_cohort_status"]): string {
  return {
    not_in_cohort: "Not in optical cohort",
    observable: "Observable optical case",
    unobserved: "Unobserved optical case"
  }[status];
}

export function figureUrl(path: string): string {
  return `/${path}`;
}
