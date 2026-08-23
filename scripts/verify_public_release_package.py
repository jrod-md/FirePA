#!/usr/bin/env python3
"""Verify the deterministic, privacy-safe FirePA P1 public package."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_public_release import sha256_bytes, sha256_file  # noqa: E402


# These are verifier-owned expectations. They intentionally do not come from
# build_public_release.py, so generator drift cannot silently redefine the P1
# scientific freeze accepted by this verifier.
PACKAGE_VERSION = "firepa-public-release-v1"
GENERATOR_VERSION = "firepa-public-release-generator-v1"
SCIENTIFIC_FREEZE_COMMIT = "7694da7df5808911de48de84016759c5fd22f176"
REGISTRY_RELATIVE = "references/external_reference_sources_v1.json"
REGISTRY_SHA256 = "6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49"

FIGURE_SOURCES = (
    "01_pipeline_overview.png",
    "02_cluster_distribution.png",
    "03_external_reference_map.png",
    "04_guacamaya_timeline.png",
    "05_guacamaya_frp_distribution.png",
    "06_los_picachos_diagnostic.png",
)

EVENT_PROPERTIES = (
    "public_event_id",
    "configuration_id",
    "start_time_utc",
    "end_time_utc",
    "duration_hours",
    "detection_count",
    "source_count",
    "satellite_count",
    "satellites",
    "frp_min_mw",
    "frp_max_mw",
    "frp_mean_mw",
    "frp_median_mw",
    "frp_sum_mw",
    "day_fraction",
    "night_fraction",
    "daynight_known_count",
    "possible_chain_merge",
    "optical_cohort_status",
)

REFERENCE_PROPERTIES = (
    "reference_id",
    "reference_name",
    "reference_location",
    "anchor_status",
    "coordinate_claimed_by_source",
    "official_window_start",
    "official_window_end",
    "official_matching_radius_m",
    "source_document_count",
    "source_ids",
    "official_match_count",
    "matched_cluster_count",
    "matched_public_event_ids",
    "temporal_span_hours",
    "inter_cluster_gaps_gt_6h",
    "fragmentation_possible",
    "diagnostic",
    "nearest_documented_contemporary_signal_m",
)

PROTECTED_ARTIFACTS = {
    "data/processed/firms_cocle_2025_detections.csv": "3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e",
    "outputs/clustering/r1500_t06/events.csv": "646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844",
    "outputs/clustering/r1500_t06/membership.csv": "e9629fb521ce05d7cf63ad68683c0c79801611102e454c6877e3746977efc504",
    "outputs/clustering/r1500_t06/summary.json": "1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736",
    "data/processed/sentinel2_observability_pilot_events.csv": "a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302",
    "data/interim/sentinel2_scene_inventory.csv": "851beea9b09e19368cf1131e82b0df5de7e5cd98566cf1da4cddeab464c7dcd1",
    "data/interim/sentinel2_aoi_inventory.csv": "fc0b77eb283455d08226152c50017d7cc70e3e0427f59f02788f0ce6d469a5b4",
    "outputs/sentinel2_observability_report.json": "219d6a896c6966118154fc9da3cbc3b18775c07e142e592b7b43c36adc517655",
    "outputs/sentinel2_event_pair_selection.csv": "24ba96aa8ee2a5a45d81e54d724d22c143be66583854764ef6c8919ea6b3dcd1",
    "data/interim/sentinel2_dnbr_event_metrics.csv": "9a1b0043a11ddf1da6e5fb5fe5a08241a28ee7d8e442d3832f4d8345fec30441",
    "outputs/sentinel2_dnbr_report.json": "5d75cd585e2005729ca83056052a71508f54b17ff2f55aa0d85b76175fd38dd9",
    "outputs/human_review/firepa_human_review.sqlite3": "c8f96d1c82bb6948010f796e801735c8786603b1d06390080265a2d324ff2cba",
    "outputs/human_review/formal_review_28/preparation_summary.json": "d5124dbe20bec1f15ff44a6e3e96d5bef73c5f23f149eed168e37a21ab44ddb4",
    "outputs/window_median_review_asset_v1/window_median_review_asset_manifest.json": "f7d9c619cda537800f777523434a4c22925156628ecfad17ad02fac7656c30fd",
    "outputs/external_reference_check_v1/manifest.json": "92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868",
    REGISTRY_RELATIVE: REGISTRY_SHA256,
}

PUBLIC_PROTECTED_ARTIFACTS = (
    "data/processed/firms_cocle_2025_detections.csv",
    "outputs/clustering/r1500_t06/events.csv",
    "outputs/clustering/r1500_t06/summary.json",
    "data/processed/sentinel2_observability_pilot_events.csv",
    REGISTRY_RELATIVE,
)

SOURCE_ARTIFACT_ROLES = {
    "outputs/clustering/r1500_t06/events.csv": "canonical provisional-event table",
    "outputs/clustering/r1500_t06/summary.json": "clustering summary",
    "data/processed/firms_cocle_2025_detections.csv": "processed FIRMS count source",
    "data/processed/sentinel2_observability_pilot_events.csv": "optical cohort membership",
    "outputs/human_review/unobserved_events.csv": "unobserved cohort status",
    "outputs/external_reference_check_v1/matches.csv": "external match rows",
    "outputs/external_reference_check_v1/reference_summary.csv": "external reference summary",
    "outputs/final_scientific_report/guacamaya_timeline.csv": "Guacamaya timeline source",
    "outputs/final_scientific_report/picachos_temporal_top10.csv": "Los Picachos diagnostic source",
    REGISTRY_RELATIVE: "canonical external source registry",
    "outputs/final_scientific_report/manifest.json": "frozen final-report manifest",
}


def public_files() -> list[str]:
    return [
        "project-summary.json",
        "events.geojson",
        "external-references.geojson",
        "guacamaya-timeline.json",
        "methodology.json",
        "citations.json",
        "provenance.json",
        *[f"figures/{name}" for name in FIGURE_SOURCES],
    ]


EXPECTED_FROZEN_COUNTS = {
    "firms_raw_detections": 1532,
    "firms_processed_detections": 1185,
    "configuration_id": "r1500_t06",
    "provisional_thermal_events": 611,
    "singletons": 344,
    "multi_detection_events": 267,
    "possible_chain_merge_events": 17,
    "optical_cohort_events": 30,
    "optically_observable_events": 28,
    "unobserved_events": 2,
    "formal_human_observations": 0,
    "external_incidents": 2,
    "external_source_documents": 7,
}

EXPECTED_PACKAGE_FILES = set(public_files()) | {"manifest.json"}
EXPECTED_EVENT_SEQUENCE = [f"evt-{index:04d}" for index in range(1, 612)]
EXPECTED_EVENT_IDS = set(EXPECTED_EVENT_SEQUENCE)
EXPECTED_REFERENCE_IDS = {"REFERENCE-001", "REFERENCE-002"}
EXPECTED_SOURCE_IDS = {f"SOURCE-{index:03d}" for index in range(1, 8)}
EXPECTED_PROVENANCE_KEYS = {
    "package_version",
    "scientific_freeze_commit",
    "generator",
    "network_access",
    "earth_engine_queries_made",
    "source_artifacts",
    "transformations",
    "output_hashes",
    "figure_provenance",
    "protected_artifacts",
    "public_private_boundary",
}
EXPECTED_SOURCE_RECORD_KEYS = {"path", "role", "size_bytes", "sha256"}
EXPECTED_FIGURE_RECORD_KEYS = {
    "source_path",
    "source_sha256",
    "derivative_path",
    "derivative_sha256",
    "transformation",
    "width",
    "height",
    "size_bytes",
    "scientific_content_recomputed",
}

FORBIDDEN_KEYS = {
    "ground_truth",
    "target",
    "predicted_class",
    "prediction",
    "significant_burn",
    "confirmed_fire",
    "validated_fire",
    "severity",
    "fire_probability",
    "wildfire_probability",
    "confidence_of_fire",
    "model_output",
}
PRIVATE_KEY_NAMES = {
    "private_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "api_key",
    "password",
    "credential",
    "reviewer_id",
    "reviewer_identity",
    "random_seed",
    "seed",
}
WINDOWS_ABSOLUTE = re.compile(
    r"(?i)(?<![a-z])(?:[a-z]:[\\/](?!/)|\\\\(?:users|home|temp|private)[\\/])"
)
UNIX_ABSOLUTE = re.compile(r"(?i)(?:^|[\s\"'([{])/(?:users|home|private|tmp|var|mnt)[/\\]")
PRIVATE_TEXT_MARKERS = re.compile(
    r"(?i)(?:BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|sqlite3|service[_ -]?account|"
    r"client[_ -]?secret|bearer\s+[a-z0-9._-]{12,})"
)
POSITIVE_PUBLIC_CLAIM_PATTERNS = (
    re.compile(r"(?i)\b\d[\d,]*\s+(?:confirmed\s+)?(?:fires?|wildfires?)\b"),
    re.compile(r"(?i)\b(?:confirmed|validated)\s+(?:(?:a|an|the)\s+)?(?:fires?|wildfires?)\b"),
    re.compile(r"(?i)\b(?:confirmed|validated)[_-](?:fires?|wildfires?)\b"),
    re.compile(r"(?i)\bclassified\s+(?:(?:a|an|the)\s+)?(?:event|cluster)\s+as\s+(?:a\s+)?(?:fires?|wildfires?)\b"),
    re.compile(r"(?i)\bpredict(?:s|ed)?\s+(?:a\s+)?(?:fires?|wildfires?)\b"),
    re.compile(r"(?i)\b(?:provides?|reports?)\s+(?:a\s+)?(?:fires?|wildfires?)\s+probability\b"),
    re.compile(r"(?i)\b(?:fires?|wildfires?)\s+probability\b"),
    re.compile(r"(?i)\bprovides?\s+(?:a\s+)?severity(?:\s+(?:class|estimate|prediction))?\b"),
    re.compile(r"(?i)\b(?:fires?|wildfires?)\s+severity\b"),
    re.compile(r"(?i)\bseverity\s+(?:class|estimate|prediction)\b"),
)
NEGATIVE_CLAIM_CONTEXT = re.compile(
    r"(?i)\b(?:does\s+not|do\s+not|did\s+not|not|no|without|never|unsupported|deferred|unobserved)\b"
)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
    )


def is_finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def load_optional_json(package: Path, relative: str, errors: list[str]) -> Any | None:
    path = package / relative
    if not path.is_file():
        errors.append(f"missing JSON file: {relative}")
        return None
    try:
        return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {relative}: {exc}")
        return None


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def verify_file_set(package: Path, errors: list[str]) -> dict[str, Any] | None:
    if not package.is_dir():
        errors.append(f"package directory is missing: {package}")
        return None
    actual_files = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
    }
    check(
        actual_files == EXPECTED_PACKAGE_FILES,
        f"package file set mismatch: unexpected={sorted(actual_files - EXPECTED_PACKAGE_FILES)}, "
        f"missing={sorted(EXPECTED_PACKAGE_FILES - actual_files)}",
        errors,
    )
    manifest = load_optional_json(package, "manifest.json", errors)
    if not isinstance(manifest, dict):
        return None
    check(manifest.get("package_version") == PACKAGE_VERSION, "manifest package version mismatch", errors)
    check(
        manifest.get("scientific_freeze_commit") == SCIENTIFIC_FREEZE_COMMIT,
        "manifest scientific freeze mismatch",
        errors,
    )
    check(manifest.get("generator_version") == GENERATOR_VERSION, "manifest generator version mismatch", errors)
    check(manifest.get("deterministic") is True, "manifest is not marked deterministic", errors)
    check(manifest.get("manifest_excludes") == ["manifest.json"], "manifest exclusion mismatch", errors)
    records = manifest.get("files")
    check(isinstance(records, list), "manifest files is not a list", errors)
    if not isinstance(records, list):
        return manifest
    expected_records: list[dict[str, Any]] = []
    for relative in sorted(EXPECTED_PACKAGE_FILES - {"manifest.json"}):
        path = package / relative
        if not path.is_file():
            continue
        payload = path.read_bytes()
        expected_records.append(
            {"path": relative, "sha256": sha256_bytes(payload), "size_bytes": len(payload)}
        )
    check(records == expected_records, "manifest file hashes, sizes, or ordering do not match", errors)
    return manifest


def verify_project_summary(summary: Any, errors: list[str]) -> None:
    check(isinstance(summary, dict), "project-summary.json is not an object", errors)
    if not isinstance(summary, dict):
        return
    check(summary.get("package_version") == PACKAGE_VERSION, "project package version mismatch", errors)
    check(summary.get("project") == "FirePA", "project name mismatch", errors)
    check(summary.get("scientific_freeze_commit") == SCIENTIFIC_FREEZE_COMMIT, "project freeze mismatch", errors)
    check(summary.get("study_area") == "Coclé, Panamá", "study area mismatch", errors)
    check(
        summary.get("period")
        == {"start": "2025-01-01", "end": "2025-04-30", "timezone": "UTC", "inclusive": True},
        "study period mismatch",
        errors,
    )
    check(summary.get("frozen_counts") == EXPECTED_FROZEN_COUNTS, "frozen count ledger mismatch", errors)
    check(
        summary.get("files") == public_files() + ["manifest.json"],
        "project file index mismatch",
        errors,
    )
    expected_scope = {
        "projection": "frozen FirePA v1 artifacts to public-safe static data",
        "frontend_agnostic": True,
        "network_required": False,
        "earth_engine_required": False,
        "backend_required": False,
        "p2_started": False,
    }
    check(summary.get("public_package_scope") == expected_scope, "public package scope mismatch", errors)
    reference_summary = summary.get("external_reference_summary")
    expected_reference_summary = {
        "registry_sha256": REGISTRY_SHA256,
        "los_picachos": {
            "official_matches": 0,
            "diagnostic": "SPATIAL_THRESHOLD_MISS",
            "nearest_documented_contemporary_signal_m": 10400.826,
        },
        "guacamaya": {
            "official_matches": 6,
            "matched_provisional_clusters": 6,
            "temporal_span_hours": 72.733,
            "inter_cluster_gaps_gt_6h": 5,
        },
    }
    check(reference_summary == expected_reference_summary, "external reference summary mismatch", errors)
    check(isinstance(summary.get("limitations"), list), "project limitations are not a list", errors)


def verify_events(events: Any, errors: list[str]) -> set[str]:
    event_ids: set[str] = set()
    ordered_event_ids: list[str] = []
    check(isinstance(events, dict), "events.geojson is not an object", errors)
    if not isinstance(events, dict):
        return event_ids
    check(events.get("type") == "FeatureCollection", "events is not a FeatureCollection", errors)
    features = events.get("features")
    check(isinstance(features, list), "events features is not a list", errors)
    if not isinstance(features, list):
        return event_ids
    check(len(features) == 611, f"expected 611 public event features, got {len(features)}", errors)
    singleton_count = 0
    multi_count = 0
    chain_count = 0
    optical_counts = {"observable": 0, "unobserved": 0, "not_in_cohort": 0}
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            errors.append(f"event feature {index} is not an object")
            continue
        check(set(feature) == {"type", "geometry", "properties"}, f"event {index} schema drift", errors)
        check(feature.get("type") == "Feature", f"event {index} is not a Feature", errors)
        geometry = feature.get("geometry")
        check(isinstance(geometry, dict), f"event {index} geometry is not an object", errors)
        if isinstance(geometry, dict):
            check(set(geometry) == {"type", "coordinates"}, f"event {index} geometry schema drift", errors)
            check(geometry.get("type") == "Point", f"event {index} is not a Point", errors)
            coordinates = geometry.get("coordinates")
            valid_coordinates = (
                isinstance(coordinates, list)
                and len(coordinates) == 2
                and all(is_finite_number(value) for value in coordinates)
                and -180 <= coordinates[0] <= 180
                and -90 <= coordinates[1] <= 90
            )
            check(valid_coordinates, f"event {index} has invalid coordinates", errors)
        properties = feature.get("properties")
        check(isinstance(properties, dict), f"event {index} properties are not an object", errors)
        if not isinstance(properties, dict):
            continue
        check(set(properties) == set(EVENT_PROPERTIES), f"event {index} property allowlist drifted", errors)
        public_id = properties.get("public_event_id")
        if isinstance(public_id, str):
            event_ids.add(public_id)
            ordered_event_ids.append(public_id)
        else:
            errors.append(f"event {index} public_event_id is not a string")
        check(properties.get("configuration_id") == "r1500_t06", f"event {index} configuration drifted", errors)
        for timestamp_field in ("start_time_utc", "end_time_utc"):
            check(is_utc_timestamp(properties.get(timestamp_field)), f"event {index} has invalid {timestamp_field}", errors)
        start_value = properties.get("start_time_utc")
        end_value = properties.get("end_time_utc")
        if is_utc_timestamp(start_value) and is_utc_timestamp(end_value):
            start = datetime.fromisoformat(start_value[:-1] + "+00:00")
            end = datetime.fromisoformat(end_value[:-1] + "+00:00")
            check(end >= start, f"event {index} ends before it starts", errors)
        integer_fields = ("detection_count", "source_count", "satellite_count", "daynight_known_count")
        for field in integer_fields:
            value = properties.get(field)
            check(type(value) is int and value >= 0, f"event {index} invalid integer {field}", errors)
        for field in (
            "duration_hours",
            "frp_min_mw",
            "frp_max_mw",
            "frp_mean_mw",
            "frp_median_mw",
            "frp_sum_mw",
            "day_fraction",
            "night_fraction",
        ):
            value = properties.get(field)
            check(is_finite_number(value) and value >= 0, f"event {index} invalid number {field}", errors)
        for field in ("day_fraction", "night_fraction"):
            value = properties.get(field)
            if is_finite_number(value):
                check(value <= 1, f"event {index} {field} is above 1", errors)
        satellites = properties.get("satellites")
        valid_satellites = isinstance(satellites, list) and all(isinstance(item, str) for item in satellites)
        check(valid_satellites, f"event {index} satellites is invalid", errors)
        if valid_satellites:
            check(satellites == sorted(set(satellites)), f"event {index} satellites are not canonical", errors)
            check(properties.get("satellite_count") == len(satellites), f"event {index} satellite count mismatch", errors)
        possible_chain_merge = properties.get("possible_chain_merge")
        optical_status = properties.get("optical_cohort_status")
        check(type(possible_chain_merge) is bool, f"event {index} chain flag is invalid", errors)
        check(optical_status in optical_counts, f"event {index} optical status is invalid", errors)
        if type(possible_chain_merge) is bool:
            chain_count += int(possible_chain_merge)
        if properties.get("detection_count") == 1:
            singleton_count += 1
        elif type(properties.get("detection_count")) is int and properties.get("detection_count") > 1:
            multi_count += 1
        if optical_status in optical_counts:
            optical_counts[optical_status] += 1
    check(ordered_event_ids == EXPECTED_EVENT_SEQUENCE, "public event feature order drifted from evt-0001..evt-0611", errors)
    check(event_ids == EXPECTED_EVENT_IDS, "public event ID set does not cover evt-0001..evt-0611", errors)
    check(singleton_count == 344, f"singleton count mismatch: {singleton_count}", errors)
    check(multi_count == 267, f"multi-detection count mismatch: {multi_count}", errors)
    check(chain_count == 17, f"possible chain-merge count mismatch: {chain_count}", errors)
    check(optical_counts == {"observable": 28, "unobserved": 2, "not_in_cohort": 581}, "optical status counts mismatch", errors)
    return event_ids


def verify_references(
    references: Any, event_ids: set[str], errors: list[str]
) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    check(isinstance(references, dict), "external references is not an object", errors)
    if not isinstance(references, dict):
        return by_id
    check(references.get("type") == "FeatureCollection", "external references is not a FeatureCollection", errors)
    features = references.get("features")
    check(isinstance(features, list) and len(features) == 2, "expected exactly 2 external reference features", errors)
    if not isinstance(features, list):
        return by_id
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            errors.append(f"reference feature {index} is not an object")
            continue
        check(set(feature) == {"type", "geometry", "properties"}, f"reference {index} schema drift", errors)
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        check(isinstance(geometry, dict) and geometry.get("type") == "Point", f"reference {index} geometry invalid", errors)
        if isinstance(geometry, dict):
            coordinates = geometry.get("coordinates")
            check(
                isinstance(coordinates, list)
                and len(coordinates) == 2
                and all(is_finite_number(value) for value in coordinates),
                f"reference {index} coordinates invalid",
                errors,
            )
        check(isinstance(properties, dict), f"reference {index} properties invalid", errors)
        if not isinstance(properties, dict):
            continue
        check(set(properties) == set(REFERENCE_PROPERTIES), f"reference {index} property allowlist drifted", errors)
        reference_id = properties.get("reference_id")
        if isinstance(reference_id, str):
            by_id[reference_id] = properties
        matched_ids = properties.get("matched_public_event_ids")
        check(
            isinstance(matched_ids, list)
            and all(isinstance(item, str) and item in event_ids for item in matched_ids)
            and len(matched_ids) == len(set(matched_ids)),
            f"reference {index} matched event IDs invalid",
            errors,
        )
        for field in ("official_match_count", "matched_cluster_count", "source_document_count", "inter_cluster_gaps_gt_6h"):
            value = properties.get(field)
            check(type(value) is int and value >= 0, f"reference {index} invalid integer {field}", errors)
        check(properties.get("official_matching_radius_m") == 5000, f"reference {index} matching radius drifted", errors)
        check(isinstance(properties.get("source_ids"), list), f"reference {index} source IDs invalid", errors)
        check(type(properties.get("coordinate_claimed_by_source")) is bool, f"reference {index} coordinate flag invalid", errors)
        check(type(properties.get("fragmentation_possible")) is bool, f"reference {index} fragmentation flag invalid", errors)
    check(set(by_id) == EXPECTED_REFERENCE_IDS, "external reference ID set mismatch", errors)
    picachos = by_id.get("REFERENCE-001")
    if picachos:
        check(picachos.get("official_match_count") == 0, "Picachos official match count mismatch", errors)
        check(picachos.get("matched_cluster_count") == 0, "Picachos cluster count mismatch", errors)
        check(picachos.get("matched_public_event_ids") == [], "Picachos should have no matched event IDs", errors)
        check(picachos.get("diagnostic") == "SPATIAL_THRESHOLD_MISS", "Picachos diagnostic mismatch", errors)
        check(
            picachos.get("nearest_documented_contemporary_signal_m") == 10400.826,
            "Picachos nearest contemporary signal mismatch",
            errors,
        )
    guacamaya = by_id.get("REFERENCE-002")
    if guacamaya:
        check(guacamaya.get("official_match_count") == 6, "Guacamaya official match count mismatch", errors)
        check(guacamaya.get("matched_cluster_count") == 6, "Guacamaya cluster count mismatch", errors)
        check(guacamaya.get("temporal_span_hours") == 72.733, "Guacamaya span mismatch", errors)
        check(guacamaya.get("inter_cluster_gaps_gt_6h") == 5, "Guacamaya gap count mismatch", errors)
    return by_id


def verify_timeline(timeline: Any, references: dict[str, dict[str, Any]], errors: list[str]) -> None:
    check(isinstance(timeline, dict), "Guacamaya timeline is not an object", errors)
    if not isinstance(timeline, dict):
        return
    check(timeline.get("package_version") == PACKAGE_VERSION, "timeline package version mismatch", errors)
    check(timeline.get("reference_id") == "REFERENCE-002", "timeline reference mismatch", errors)
    check(timeline.get("temporal_span_hours") == 72.733, "timeline span mismatch", errors)
    check(timeline.get("inter_cluster_gaps_gt_6h") == 5, "timeline gap summary mismatch", errors)
    clusters = timeline.get("clusters")
    check(isinstance(clusters, list) and len(clusters) == 6, "timeline cluster count mismatch", errors)
    if not isinstance(clusters, list):
        return
    ids: list[str] = []
    gaps = 0
    for index, cluster in enumerate(clusters, start=1):
        check(isinstance(cluster, dict), f"timeline cluster {index} is invalid", errors)
        if not isinstance(cluster, dict):
            continue
        expected_keys = {
            "order",
            "public_event_id",
            "cluster_start_utc",
            "cluster_end_utc",
            "gap_from_previous_hours",
            "detection_count",
            "max_frp_mw",
            "mean_frp_mw",
            "satellites",
            "day_count",
            "night_count",
            "possible_chain_merge",
        }
        check(set(cluster) == expected_keys, f"timeline cluster {index} schema drift", errors)
        check(cluster.get("order") == index, f"timeline order mismatch at {index}", errors)
        public_id = cluster.get("public_event_id")
        if isinstance(public_id, str):
            ids.append(public_id)
        check(public_id in {item for item in references.get("REFERENCE-002", {}).get("matched_public_event_ids", [])}, f"timeline event mismatch at {index}", errors)
        check(is_utc_timestamp(cluster.get("cluster_start_utc")), f"timeline start invalid at {index}", errors)
        check(is_utc_timestamp(cluster.get("cluster_end_utc")), f"timeline end invalid at {index}", errors)
        gap = cluster.get("gap_from_previous_hours")
        if index == 1:
            check(gap is None, "first timeline gap must be null", errors)
        else:
            check(is_finite_number(gap) and gap > 6, f"timeline gap invalid at {index}", errors)
            if is_finite_number(gap) and gap > 6:
                gaps += 1
        for field in ("detection_count", "day_count", "night_count"):
            check(type(cluster.get(field)) is int and cluster.get(field) >= 0, f"timeline {field} invalid at {index}", errors)
        for field in ("max_frp_mw", "mean_frp_mw"):
            check(is_finite_number(cluster.get(field)) and cluster.get(field) >= 0, f"timeline {field} invalid at {index}", errors)
        check(type(cluster.get("possible_chain_merge")) is bool, f"timeline chain flag invalid at {index}", errors)
        satellites = cluster.get("satellites")
        check(isinstance(satellites, list) and satellites == sorted(set(satellites)), f"timeline satellites invalid at {index}", errors)
    check(len(ids) == len(set(ids)) == 6, "timeline event IDs are not unique", errors)
    check(gaps == 5, f"timeline has {gaps} gaps greater than six hours", errors)


def verify_citations(citations: Any, root: Path, errors: list[str]) -> None:
    check(isinstance(citations, dict), "citations is not an object", errors)
    if not isinstance(citations, dict):
        return
    check(citations.get("package_version") == PACKAGE_VERSION, "citations package version mismatch", errors)
    registry = citations.get("registry")
    check(
        registry
        == {
            "path": REGISTRY_RELATIVE,
            "sha256": REGISTRY_SHA256,
            "source_count": 7,
            "incident_count": 2,
        },
        "citation registry mismatch",
        errors,
    )
    scientific_sources = citations.get("scientific_sources")
    check(isinstance(scientific_sources, list) and len(scientific_sources) == 3, "scientific source list mismatch", errors)
    expected_sources = {
        "docs/FIREPA_PILOT_V1_FREEZE.md": "scientific freeze",
        "docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md": "final scientific report",
        "docs/FIREPA_PILOT_FINAL_CHECKPOINT.md": "final checkpoint",
    }
    if isinstance(scientific_sources, list):
        for source in scientific_sources:
            if not isinstance(source, dict):
                errors.append("scientific citation is not an object")
                continue
            relative = source.get("path")
            check(relative in expected_sources, f"unexpected scientific citation: {relative}", errors)
            if relative in expected_sources:
                check(source.get("role") == expected_sources[relative], f"scientific citation role mismatch: {relative}", errors)
                path = root / relative
                check(path.is_file() and source.get("sha256") == sha256_file(path), f"scientific citation hash mismatch: {relative}", errors)
    external_sources = citations.get("external_sources")
    check(isinstance(external_sources, list) and len(external_sources) == 7, "external source list mismatch", errors)
    if isinstance(external_sources, list):
        source_ids = []
        allowed_source_keys = {
            "source_id",
            "incident_id",
            "publisher",
            "publisher_type",
            "publication_date",
            "reported_event_date",
            "reported_event_date_start",
            "reported_event_date_end",
            "reported_location",
            "reported_area_ha",
            "reported_area_qualifier",
            "cause_status",
            "url",
        }
        for source in external_sources:
            check(isinstance(source, dict), "external citation is not an object", errors)
            if not isinstance(source, dict):
                continue
            check(set(source) <= allowed_source_keys, "external citation exposes non-public fields", errors)
            source_id = source.get("source_id")
            if isinstance(source_id, str):
                source_ids.append(source_id)
        check(set(source_ids) == EXPECTED_SOURCE_IDS and len(source_ids) == 7, "external source ID set mismatch", errors)


def verify_methodology(methodology: Any, errors: list[str]) -> None:
    check(isinstance(methodology, dict), "methodology is not an object", errors)
    if not isinstance(methodology, dict):
        return
    check(methodology.get("package_version") == PACKAGE_VERSION, "methodology package version mismatch", errors)
    check(methodology.get("scientific_freeze_commit") == SCIENTIFIC_FREEZE_COMMIT, "methodology freeze mismatch", errors)
    check(methodology.get("scientific_unit") == "provisional thermal event", "scientific unit mismatch", errors)
    workflow = methodology.get("workflow")
    check(isinstance(workflow, list) and len(workflow) == 5, "methodology workflow mismatch", errors)
    formal_review = methodology.get("formal_review")
    check(
        formal_review
        == {
            "status": "deferred",
            "reason": "QUALIFIED_REVIEWER_UNAVAILABLE",
            "execution_authorized": False,
            "formal_human_observations": 0,
        },
        "formal review boundary mismatch",
        errors,
    )
    modeling = methodology.get("supervised_modeling")
    check(
        modeling
        == {
            "status": "deferred",
            "reason": "NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE",
            "model_trained": False,
        },
        "modeling boundary mismatch",
        errors,
    )


def verify_provenance(provenance: Any, package: Path, root: Path, errors: list[str]) -> None:
    check(isinstance(provenance, dict), "provenance is not an object", errors)
    if not isinstance(provenance, dict):
        return
    check(set(provenance) == EXPECTED_PROVENANCE_KEYS, "provenance top-level allowlist drifted", errors)
    check(provenance.get("package_version") == PACKAGE_VERSION, "provenance package version mismatch", errors)
    check(provenance.get("scientific_freeze_commit") == SCIENTIFIC_FREEZE_COMMIT, "provenance freeze mismatch", errors)
    check(provenance.get("network_access") is False, "provenance network flag is not false", errors)
    check(provenance.get("earth_engine_queries_made") is False, "provenance Earth Engine flag is not false", errors)
    generator = provenance.get("generator")
    check(isinstance(generator, dict), "provenance generator is invalid", errors)
    if isinstance(generator, dict):
        check(generator.get("version") == GENERATOR_VERSION, "provenance generator version mismatch", errors)
        check(generator.get("entry_point") == "scripts/build_public_release.py", "provenance entry point mismatch", errors)
    source_artifacts = provenance.get("source_artifacts")
    check(isinstance(source_artifacts, list) and len(source_artifacts) == 11, "provenance source ledger mismatch", errors)
    if isinstance(source_artifacts, list):
        actual_paths = [record.get("path") if isinstance(record, dict) else None for record in source_artifacts]
        check(
            actual_paths == list(SOURCE_ARTIFACT_ROLES),
            "provenance source ledger paths/order mismatch",
            errors,
        )
        for record in source_artifacts:
            check(isinstance(record, dict), "provenance source record is invalid", errors)
            if not isinstance(record, dict):
                continue
            relative = record.get("path")
            check(set(record) == EXPECTED_SOURCE_RECORD_KEYS, f"provenance source record schema drift: {relative}", errors)
            if isinstance(relative, str) and relative in SOURCE_ARTIFACT_ROLES:
                check(
                    record.get("role") == SOURCE_ARTIFACT_ROLES[relative],
                    f"provenance source role mismatch: {relative}",
                    errors,
                )
            check(isinstance(relative, str) and not Path(relative).is_absolute(), f"absolute provenance source path: {relative}", errors)
            if isinstance(relative, str) and (root / relative).is_file():
                path = root / relative
                check(record.get("sha256") == sha256_file(path), f"provenance source hash mismatch: {relative}", errors)
                check(record.get("size_bytes") == path.stat().st_size, f"provenance source size mismatch: {relative}", errors)
    output_hashes = provenance.get("output_hashes")
    expected_output_paths = sorted(item for item in public_files() if item != "provenance.json")
    check(isinstance(output_hashes, list), "provenance output hash ledger is invalid", errors)
    if isinstance(output_hashes, list):
        expected_output_records = []
        for relative in expected_output_paths:
            path = package / relative
            if path.is_file():
                payload = path.read_bytes()
                expected_output_records.append({"path": relative, "sha256": sha256_bytes(payload), "size_bytes": len(payload)})
        check(output_hashes == expected_output_records, "provenance output hash ledger mismatch", errors)
    figure_provenance = provenance.get("figure_provenance")
    check(isinstance(figure_provenance, list) and len(figure_provenance) == len(FIGURE_SOURCES), "figure provenance count mismatch", errors)
    if isinstance(figure_provenance, list):
        for record in figure_provenance:
            check(isinstance(record, dict), "figure provenance record is invalid", errors)
            if not isinstance(record, dict):
                continue
            source_path = record.get("source_path")
            derivative_path = record.get("derivative_path")
            check(set(record) == EXPECTED_FIGURE_RECORD_KEYS, f"figure provenance schema drift: {derivative_path}", errors)
            check(isinstance(source_path, str) and source_path.startswith("outputs/final_scientific_report/"), "figure source path is not relative", errors)
            check(isinstance(derivative_path, str) and derivative_path.startswith("figures/"), "figure derivative path is invalid", errors)
            if isinstance(source_path, str) and isinstance(derivative_path, str):
                source = root / source_path
                derivative = package / derivative_path
                if source.is_file() and derivative.is_file():
                    source_hash = sha256_file(source)
                    derivative_hash = sha256_file(derivative)
                    check(record.get("source_sha256") == source_hash, f"figure source hash mismatch: {source_path}", errors)
                    check(record.get("derivative_sha256") == derivative_hash, f"figure derivative hash mismatch: {derivative_path}", errors)
                    check(source_hash == derivative_hash, f"figure is not byte-identical: {derivative_path}", errors)
            check(record.get("transformation") == "copy-byte-identical", f"figure transformation drifted: {derivative_path}", errors)
            check(record.get("width") == 1600 and record.get("height") == 900, f"figure dimensions drifted: {derivative_path}", errors)
            check(record.get("scientific_content_recomputed") is False, f"figure recomputation flag drifted: {derivative_path}", errors)
    check(
        provenance.get("protected_artifacts")
        == [
            {"path": path, "sha256": PROTECTED_ARTIFACTS[path]}
            for path in PUBLIC_PROTECTED_ARTIFACTS
        ],
        "public protected-artifact ledger mismatch",
        errors,
    )
    check(
        provenance.get("public_private_boundary")
        == {
            "private_review_mappings_published": False,
            "reviewer_identities_published": False,
            "sqlite_published": False,
            "raw_detection_rows_published": False,
            "absolute_paths_published": False,
            "secrets_published": False,
        },
        "public/private boundary mismatch",
        errors,
    )


def _claim_sentence(value: str, start: int, end: int) -> str:
    boundaries = ".!?;:\n"
    left = max((value.rfind(boundary, 0, start) for boundary in boundaries), default=-1)
    right_candidates = [value.find(boundary, end) for boundary in boundaries]
    right_candidates = [candidate for candidate in right_candidates if candidate >= 0]
    right = min(right_candidates, default=len(value))
    return value[left + 1 : right + 1]


def scan_serialized_value(value: Any, location: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"forbidden serialized field at {location}.{key}")
            if normalized in PRIVATE_KEY_NAMES:
                errors.append(f"private serialized field at {location}.{key}")
            scan_serialized_value(child, f"{location}.{key}", errors)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            scan_serialized_value(child, f"{location}[{index}]", errors)
        return
    if isinstance(value, str):
        if WINDOWS_ABSOLUTE.search(value) or UNIX_ABSOLUTE.search(value):
            errors.append(f"absolute local path serialized at {location}")
        if PRIVATE_TEXT_MARKERS.search(value):
            errors.append(f"private or credential marker serialized at {location}")
        for pattern in POSITIVE_PUBLIC_CLAIM_PATTERNS:
            for match in pattern.finditer(value):
                sentence = _claim_sentence(value, match.start(), match.end())
                if NEGATIVE_CLAIM_CONTEXT.search(sentence):
                    continue
                errors.append(
                    f"unsupported positive public claim serialized at {location}: {match.group(0)}"
                )


def verify_privacy(package: Path, errors: list[str]) -> None:
    for path in sorted(package.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".geojson"}:
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        if WINDOWS_ABSOLUTE.search(text) or UNIX_ABSOLUTE.search(text) or PRIVATE_TEXT_MARKERS.search(text):
            errors.append(f"private path or credential marker found in {path.relative_to(package).as_posix()}")
        if path.suffix.lower() in {".json", ".geojson"}:
            try:
                payload = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            scan_serialized_value(
                payload,
                path.relative_to(package).as_posix(),
                errors,
            )


def verify_package(package_dir: Path, root: Path | None = None) -> dict[str, Any]:
    package = package_dir.resolve()
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    errors: list[str] = []
    verify_file_set(package, errors)
    summary = load_optional_json(package, "project-summary.json", errors)
    events = load_optional_json(package, "events.geojson", errors)
    references = load_optional_json(package, "external-references.geojson", errors)
    timeline = load_optional_json(package, "guacamaya-timeline.json", errors)
    methodology = load_optional_json(package, "methodology.json", errors)
    citations = load_optional_json(package, "citations.json", errors)
    provenance = load_optional_json(package, "provenance.json", errors)
    verify_project_summary(summary, errors)
    event_ids = verify_events(events, errors)
    reference_by_id = verify_references(references, event_ids, errors)
    verify_timeline(timeline, reference_by_id, errors)
    verify_methodology(methodology, errors)
    verify_citations(citations, project_root, errors)
    verify_provenance(provenance, package, project_root, errors)
    verify_privacy(package, errors)
    for relative, expected in PROTECTED_ARTIFACTS.items():
        source = project_root / relative
        check(source.is_file(), f"protected source missing: {relative}", errors)
        if source.is_file():
            check(sha256_file(source) == expected, f"protected source hash mismatch: {relative}", errors)
    return {
        "ok": not errors,
        "package": str(package),
        "package_version": PACKAGE_VERSION,
        "scientific_freeze_commit": SCIENTIFIC_FREEZE_COMMIT,
        "checked_files": len(EXPECTED_PACKAGE_FILES),
        "event_count": len(event_ids),
        "reference_count": len(reference_by_id),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site-data",
        help="public package directory to verify",
    )
    args = parser.parse_args(argv)
    report = verify_package(args.package)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
