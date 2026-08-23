#!/usr/bin/env python3
"""Build the deterministic, frontend-agnostic FirePA P1 public package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(encoded)


def parse_json_cell(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON cell: {value!r}") from exc


def parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer in {field}: {value!r}") from exc


def parse_float(value: str | None, field: str, allow_null: bool = False) -> float | None:
    if value in (None, "") and allow_null:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid number in {field}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite number in {field}: {value!r}")
    return parsed


def rounded(value: str | float | int | None, field: str, places: int = 6) -> float | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite number in {field}: {value!r}")
    return round(parsed, places)


def parse_bool(value: str, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"invalid boolean in {field}: {value!r}")


def parse_timestamp(value: str, field: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError(f"{field} is not UTC: {value!r}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid timestamp in {field}: {value!r}") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"{field} is not UTC: {value!r}")
    return parsed


def public_timestamp(value: str, field: str) -> str:
    parsed = parse_timestamp(value, field)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("public figure is not a PNG with an IHDR chunk")
    return struct.unpack(">II", data[16:24])


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


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


def file_records(output: Path, paths: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in sorted(paths):
        path = output / relative
        if not path.is_file():
            raise ValueError(f"expected public file is missing: {relative}")
        data = path.read_bytes()
        records.append(
            {
                "path": relative,
                "size_bytes": len(data),
                "sha256": sha256_bytes(data),
            }
        )
    return records


def count_raw_rows(root: Path) -> int:
    count = 0
    for path in sorted((root / "data" / "raw").glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            count += sum(1 for _ in csv.DictReader(handle))
    return count


def verify_protected_artifacts(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative, expected in PROTECTED_ARTIFACTS.items():
        path = root / relative
        if not path.is_file():
            raise ValueError(f"protected artifact is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"protected artifact hash mismatch: {relative}; "
                f"expected {expected}, got {actual}"
            )
        records.append({"path": relative, "sha256": actual})
    return records


def load_optical_status(root: Path, event_ids: set[str]) -> dict[str, str]:
    cohort_rows = read_csv(root / "data" / "processed" / "sentinel2_observability_pilot_events.csv")
    cohort_ids = {row["event_id"] for row in cohort_rows}
    unobserved_rows = read_csv(root / "outputs" / "human_review" / "unobserved_events.csv")
    unobserved_ids = {row["event_id"] for row in unobserved_rows}
    if len(cohort_ids) != 30:
        raise ValueError(f"expected 30 optical cohort IDs, got {len(cohort_ids)}")
    if len(unobserved_ids) != 2:
        raise ValueError(f"expected 2 unobserved IDs, got {len(unobserved_ids)}")
    if not unobserved_ids.issubset(cohort_ids):
        raise ValueError("unobserved IDs are not a subset of the optical cohort")
    if not cohort_ids.issubset(event_ids):
        raise ValueError("optical cohort contains an event absent from r1500_t06")
    return {
        event_id: (
            "unobserved"
            if event_id in unobserved_ids
            else "observable"
            if event_id in cohort_ids
            else "not_in_cohort"
        )
        for event_id in event_ids
    }


def load_events(root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = read_csv(root / "outputs" / "clustering" / "r1500_t06" / "events.csv")
    rows.sort(key=lambda row: row["event_id"])
    if len(rows) != 611:
        raise ValueError(f"expected 611 frozen event rows, got {len(rows)}")
    event_ids = {row["event_id"] for row in rows}
    optical_status = load_optical_status(root, event_ids)
    source_to_public = {
        row["event_id"]: f"evt-{index:04d}" for index, row in enumerate(rows, start=1)
    }
    features: list[dict[str, Any]] = []
    for row in rows:
        source_id = row["event_id"]
        satellites = parse_json_cell(row["satellites"], [])
        if not isinstance(satellites, list) or not all(isinstance(item, str) for item in satellites):
            raise ValueError(f"invalid satellites list for {source_id}")
        properties = {
            "public_event_id": source_to_public[source_id],
            "configuration_id": row["configuration_id"],
            "start_time_utc": public_timestamp(row["start_timestamp_utc"], "start_timestamp_utc"),
            "end_time_utc": public_timestamp(row["end_timestamp_utc"], "end_timestamp_utc"),
            "duration_hours": rounded(row["duration_hours"], "duration_hours"),
            "detection_count": parse_int(row["detection_count"], "detection_count"),
            "source_count": parse_int(row["source_count"], "source_count"),
            "satellite_count": parse_int(row["satellite_count"], "satellite_count"),
            "satellites": sorted(set(satellites)),
            "frp_min_mw": rounded(row["frp_min"], "frp_min"),
            "frp_max_mw": rounded(row["frp_max"], "frp_max"),
            "frp_mean_mw": rounded(row["frp_mean"], "frp_mean"),
            "frp_median_mw": rounded(row["frp_median"], "frp_median"),
            "frp_sum_mw": rounded(row["frp_sum"], "frp_sum"),
            "day_fraction": rounded(row["day_fraction"], "day_fraction"),
            "night_fraction": rounded(row["night_fraction"], "night_fraction"),
            "daynight_known_count": parse_int(row["daynight_known_count"], "daynight_known_count"),
            "possible_chain_merge": parse_bool(row["possible_chain_merge"], "possible_chain_merge"),
            "optical_cohort_status": optical_status[source_id],
        }
        if tuple(properties) != EVENT_PROPERTIES:
            raise ValueError("event property allowlist order drifted")
        longitude = rounded(row["centroid_longitude"], "centroid_longitude", places=6)
        latitude = rounded(row["centroid_latitude"], "centroid_latitude", places=6)
        if longitude is None or latitude is None:
            raise ValueError(f"missing centroid for {source_id}")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError(f"invalid centroid coordinates for {source_id}")
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "properties": properties,
            }
        )
    return features, source_to_public


def load_external_projection(
    root: Path, source_to_public: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    registry = read_json(root / REGISTRY_RELATIVE)
    incidents = {item["incident_id"]: item for item in registry["incidents"]}
    anchors = {item["incident_id"]: item for item in registry["matching_anchors"]}
    matches = read_csv(root / "outputs" / "external_reference_check_v1" / "matches.csv")
    summaries = read_csv(root / "outputs" / "external_reference_check_v1" / "reference_summary.csv")
    summary_by_id = {row["reference_id"]: row for row in summaries}
    timeline_rows = read_csv(root / "outputs" / "final_scientific_report" / "guacamaya_timeline.csv")
    timeline_rows.sort(key=lambda row: int(row["order"]))
    picachos_rows = read_csv(root / "outputs" / "final_scientific_report" / "picachos_temporal_top10.csv")
    if not picachos_rows:
        raise ValueError("Picachos diagnostic table is empty")
    nearest_picachos_m = rounded(picachos_rows[0]["distance_m"], "Picachos distance", 3)

    timeline: list[dict[str, Any]] = []
    for row in timeline_rows:
        source_event_id = row["event_id"]
        if source_event_id not in source_to_public:
            raise ValueError(f"Guacamaya timeline event is absent: {source_event_id}")
        timeline.append(
            {
                "order": parse_int(row["order"], "timeline order"),
                "public_event_id": source_to_public[source_event_id],
                "cluster_start_utc": public_timestamp(row["cluster_start"], "cluster_start"),
                "cluster_end_utc": public_timestamp(row["cluster_end"], "cluster_end"),
                "gap_from_previous_hours": rounded(
                    row["intercluster_gap_hours"],
                    "intercluster_gap_hours",
                ),
                "detection_count": parse_int(row["n_detections"], "timeline n_detections"),
                "max_frp_mw": rounded(row["max_frp"], "timeline max_frp"),
                "mean_frp_mw": rounded(row["mean_frp"], "timeline mean_frp"),
                "satellites": sorted(set(parse_json_cell(row["satellites"], []))),
                "day_count": parse_int(row["day_count"], "timeline day_count"),
                "night_count": parse_int(row["night_count"], "timeline night_count"),
                "possible_chain_merge": parse_bool(
                    row["possible_chain_merge"], "timeline possible_chain_merge"
                ),
            }
        )
    if len(timeline) != 6:
        raise ValueError(f"expected 6 Guacamaya timeline rows, got {len(timeline)}")
    first = parse_timestamp(timeline[0]["cluster_start_utc"], "timeline start")
    last = parse_timestamp(timeline[-1]["cluster_end_utc"], "timeline end")
    span_hours = round((last - first).total_seconds() / 3600, 3)
    gaps_gt_six = sum(
        1
        for item in timeline
        if item["gap_from_previous_hours"] is not None
        and item["gap_from_previous_hours"] > 6
    )

    public_features: list[dict[str, Any]] = []
    for incident_id in sorted(incidents):
        incident = incidents[incident_id]
        anchor = anchors[incident_id]
        summary = summary_by_id[incident_id]
        matched_source_ids = sorted(
            {
                row["event_id"]
                for row in matches
                if row["reference_id"] == incident_id and row["external_reference_match"].lower() == "true"
            }
        )
        matched_public_ids = [source_to_public[item] for item in matched_source_ids]
        official_match_count = parse_int(summary["match_count"], "reference match_count")
        if official_match_count != len(matched_public_ids):
            raise ValueError(f"match count mismatch for {incident_id}")
        is_picachos = incident_id == "REFERENCE-001"
        properties = {
            "reference_id": incident_id,
            "reference_name": incident["canonical_name"],
            "reference_location": incident["location_text"],
            "anchor_status": anchor["coordinate_status"],
            "coordinate_claimed_by_source": anchor["coordinate_claimed_by_news_source"],
            "official_window_start": incident["official_matching_window"]["start"],
            "official_window_end": incident["official_matching_window"]["end"],
            "official_matching_radius_m": incident["official_matching_radius_m"],
            "source_document_count": len(incident["source_ids"]),
            "source_ids": sorted(incident["source_ids"]),
            "official_match_count": official_match_count,
            "matched_cluster_count": len(matched_public_ids),
            "matched_public_event_ids": matched_public_ids,
            "temporal_span_hours": None if is_picachos else span_hours,
            "inter_cluster_gaps_gt_6h": 0 if is_picachos else gaps_gt_six,
            "fragmentation_possible": False if is_picachos else True,
            "diagnostic": "SPATIAL_THRESHOLD_MISS" if is_picachos else None,
            "nearest_documented_contemporary_signal_m": nearest_picachos_m if is_picachos else None,
        }
        if tuple(properties) != REFERENCE_PROPERTIES:
            raise ValueError("reference property allowlist order drifted")
        longitude = rounded(anchor["longitude"], "anchor longitude")
        latitude = rounded(anchor["latitude"], "anchor latitude")
        public_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": properties,
            }
        )
    return public_features, {
        "package_version": PACKAGE_VERSION,
        "reference_id": "REFERENCE-002",
        "timeline_window": {
            "start": "2025-01-23",
            "end": "2025-01-27",
            "timezone": "UTC",
            "inclusive": True,
        },
        "temporal_span_hours": span_hours,
        "inter_cluster_gaps_gt_6h": gaps_gt_six,
        "clusters": timeline,
    }, registry["sources"]


def public_source_record(source: dict[str, Any]) -> dict[str, Any]:
    allowed = (
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
    )
    return {key: source[key] for key in allowed if key in source}


def source_artifact_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative, role in SOURCE_ARTIFACT_ROLES.items():
        path = root / relative
        if not path.is_file():
            raise ValueError(f"source artifact is missing: {relative}")
        records.append(
            {
                "path": relative,
                "role": role,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def build_package(output_dir: Path, root: Path) -> dict[str, Any]:
    protected_records = verify_protected_artifacts(root)
    event_features, source_to_public = load_events(root)
    external_features, guacamaya_timeline, sources = load_external_projection(
        root, source_to_public
    )
    raw_count = count_raw_rows(root)
    processed_count = len(read_csv(root / "data" / "processed" / "firms_cocle_2025_detections.csv"))
    if raw_count != 1532 or processed_count != 1185:
        raise ValueError(f"FIRMS count mismatch: raw={raw_count}, processed={processed_count}")

    event_properties = [feature["properties"] for feature in event_features]
    singletons = sum(item["detection_count"] == 1 for item in event_properties)
    multi = sum(item["detection_count"] > 1 for item in event_properties)
    chain_merges = sum(item["possible_chain_merge"] for item in event_properties)
    optical_counts = {
        status: sum(item["optical_cohort_status"] == status for item in event_properties)
        for status in ("observable", "unobserved", "not_in_cohort")
    }
    if (singletons, multi, chain_merges) != (344, 267, 17):
        raise ValueError("frozen event partition mismatch")
    if optical_counts != {"observable": 28, "unobserved": 2, "not_in_cohort": 581}:
        raise ValueError(f"optical status mismatch: {optical_counts}")

    output_dir = output_dir.resolve()
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path is not a directory: {output_dir}")
        expected_existing = set(public_files()) | {"manifest.json"}
        unexpected = [
            relative_path(output_dir, path)
            for path in output_dir.rglob("*")
            if path.is_file() and relative_path(output_dir, path) not in expected_existing
        ]
        if unexpected:
            raise ValueError(f"unexpected existing public files: {sorted(unexpected)}")
    else:
        output_dir.mkdir(parents=True)

    (output_dir / "figures").mkdir(exist_ok=True)
    for name in FIGURE_SOURCES:
        source = root / "outputs" / "final_scientific_report" / name
        destination = output_dir / "figures" / name
        if not source.is_file():
            raise ValueError(f"scientific figure is missing: {source}")
        destination.write_bytes(source.read_bytes())
        png_dimensions(destination.read_bytes())

    project_summary = {
        "package_version": PACKAGE_VERSION,
        "project": "FirePA",
        "definition": (
            "FirePA is a reproducible remote-sensing pilot for detecting, grouping "
            "and analyzing provisional thermal events in Coclé, Panamá using NASA "
            "FIRMS and Sentinel-2 optical evidence."
        ),
        "scientific_freeze_commit": SCIENTIFIC_FREEZE_COMMIT,
        "study_area": "Coclé, Panamá",
        "period": {"start": "2025-01-01", "end": "2025-04-30", "timezone": "UTC", "inclusive": True},
        "frozen_counts": {
            "firms_raw_detections": raw_count,
            "firms_processed_detections": processed_count,
            "configuration_id": "r1500_t06",
            "provisional_thermal_events": len(event_features),
            "singletons": singletons,
            "multi_detection_events": multi,
            "possible_chain_merge_events": chain_merges,
            "optical_cohort_events": optical_counts["observable"] + optical_counts["unobserved"],
            "optically_observable_events": optical_counts["observable"],
            "unobserved_events": optical_counts["unobserved"],
            "formal_human_observations": 0,
            "external_incidents": len(external_features),
            "external_source_documents": len(sources),
        },
        "external_reference_summary": {
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
        },
        "public_package_scope": {
            "projection": "frozen FirePA v1 artifacts to public-safe static data",
            "frontend_agnostic": True,
            "network_required": False,
            "earth_engine_required": False,
            "backend_required": False,
            "p2_started": False,
        },
        "limitations": [
            "FirePA does not provide confirmed wildfire classification.",
            "FirePA does not provide ground truth or institutional validation.",
            "FirePA does not provide supervised prediction or severity estimation.",
            "FirePA does not provide operational monitoring, realtime alerts or an emergency dashboard.",
            "Unobserved optical cases are not negative cases.",
            "External references are relational evidence, not ground truth.",
        ],
        "files": public_files() + ["manifest.json"],
    }

    methodology = {
        "package_version": PACKAGE_VERSION,
        "scientific_unit": "provisional thermal event",
        "definition": project_summary["definition"],
        "scientific_freeze_commit": SCIENTIFIC_FREEZE_COMMIT,
        "study_period": project_summary["period"],
        "workflow": [
            {
                "stage": "firms_acquisition_and_audit",
                "status": "frozen_descriptive",
                "source_artifacts": [
                    "data/raw/*.csv",
                    "data/processed/firms_cocle_2025_detections.csv",
                ],
                "result": "1,532 raw detections and 1,185 processed detections.",
            },
            {
                "stage": "provisional_clustering",
                "status": "frozen",
                "configuration_id": "r1500_t06",
                "algorithm": "connected_components",
                "radius_m": 1500,
                "time_window_hours": 6,
                "metric_projection": "EPSG:32617",
                "result": "611 provisional thermal events; clusters remain provisional.",
            },
            {
                "stage": "sentinel2_optical_followup",
                "status": "frozen_descriptive",
                "cohort_events": 30,
                "observable_events": 28,
                "unobserved_events": 2,
                "evidence_modes": ["selected_pair", "window_median"],
                "result": "Optical evidence is descriptive and does not create labels.",
            },
            {
                "stage": "nbr_dnbr",
                "status": "frozen_descriptive",
                "result": "NBR/dNBR metrics exist for the observable optical subset; no severity class is created.",
            },
            {
                "stage": "external_reference_check",
                "status": "complete_exploratory",
                "matching_rule": "inclusive temporal overlap and distance <= 5,000 m",
                "reclustered": False,
                "result": "0 official Picachos matches and 6 official Guacamaya matches.",
            },
        ],
        "formal_review": {
            "status": "deferred",
            "reason": "QUALIFIED_REVIEWER_UNAVAILABLE",
            "execution_authorized": False,
            "formal_human_observations": 0,
        },
        "supervised_modeling": {
            "status": "deferred",
            "reason": "NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE",
            "model_trained": False,
        },
        "limitations": project_summary["limitations"],
        "source_artifacts": [
            "docs/FIREPA_PILOT_V1_FREEZE.md",
            "docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md",
            "docs/FIREPA_PILOT_FINAL_CHECKPOINT.md",
        ],
    }

    citations = {
        "package_version": PACKAGE_VERSION,
        "registry": {
            "path": REGISTRY_RELATIVE,
            "sha256": REGISTRY_SHA256,
            "source_count": 7,
            "incident_count": 2,
        },
        "scientific_sources": [
            {
                "path": relative,
                "sha256": sha256_file(root / relative),
                "role": role,
            }
            for relative, role in (
                ("docs/FIREPA_PILOT_V1_FREEZE.md", "scientific freeze"),
                ("docs/FIREPA_PILOT_SCIENTIFIC_REPORT.md", "final scientific report"),
                ("docs/FIREPA_PILOT_FINAL_CHECKPOINT.md", "final checkpoint"),
            )
        ],
        "external_sources": [
            public_source_record(source) for source in sorted(sources, key=lambda item: item["source_id"])
        ],
    }

    write_json(output_dir / "project-summary.json", project_summary)
    write_json(
        output_dir / "events.geojson",
        {"type": "FeatureCollection", "features": event_features},
    )
    write_json(
        output_dir / "external-references.geojson",
        {"type": "FeatureCollection", "features": external_features},
    )
    write_json(output_dir / "guacamaya-timeline.json", guacamaya_timeline)
    write_json(output_dir / "methodology.json", methodology)
    write_json(output_dir / "citations.json", citations)

    source_records = source_artifact_records(root)
    figure_records = []
    for name in FIGURE_SOURCES:
        source = root / "outputs" / "final_scientific_report" / name
        destination = output_dir / "figures" / name
        source_bytes = source.read_bytes()
        derivative_bytes = destination.read_bytes()
        width, height = png_dimensions(derivative_bytes)
        figure_records.append(
            {
                "source_path": f"outputs/final_scientific_report/{name}",
                "source_sha256": sha256_bytes(source_bytes),
                "derivative_path": f"figures/{name}",
                "derivative_sha256": sha256_bytes(derivative_bytes),
                "transformation": "copy-byte-identical",
                "width": width,
                "height": height,
                "size_bytes": len(derivative_bytes),
                "scientific_content_recomputed": False,
            }
        )

    pre_provenance_paths = [relative for relative in public_files() if relative not in {"provenance.json"}]
    output_hashes = file_records(output_dir, pre_provenance_paths)
    provenance = {
        "package_version": PACKAGE_VERSION,
        "scientific_freeze_commit": SCIENTIFIC_FREEZE_COMMIT,
        "generator": {
            "version": GENERATOR_VERSION,
            "entry_point": "scripts/build_public_release.py",
            "command": "python scripts/build_public_release.py --output site-data",
        },
        "network_access": False,
        "earth_engine_queries_made": False,
        "source_artifacts": source_records,
        "transformations": [
            "event rows sorted by frozen source event_id and mapped to public_event_id",
            "frozen centroid fields projected to WGS84 GeoJSON Points",
            "optical cohort status joined from frozen cohort and unobserved tables",
            "external references projected from the canonical registry and frozen check outputs",
            "numeric values rounded only for deterministic public serialization",
            "six final scientific figures copied byte-for-byte",
        ],
        "output_hashes": output_hashes,
        "figure_provenance": figure_records,
        "protected_artifacts": [
            item for item in protected_records if item["path"] in PUBLIC_PROTECTED_ARTIFACTS
        ],
        "public_private_boundary": {
            "private_review_mappings_published": False,
            "reviewer_identities_published": False,
            "sqlite_published": False,
            "raw_detection_rows_published": False,
            "absolute_paths_published": False,
            "secrets_published": False,
        },
    }
    write_json(output_dir / "provenance.json", provenance)

    manifest_records = file_records(output_dir, public_files())
    manifest = {
        "package_version": PACKAGE_VERSION,
        "scientific_freeze_commit": SCIENTIFIC_FREEZE_COMMIT,
        "generator_version": GENERATOR_VERSION,
        "deterministic": True,
        "manifest_excludes": ["manifest.json"],
        "files": manifest_records,
    }
    write_json(output_dir / "manifest.json", manifest)
    return {
        "package_version": PACKAGE_VERSION,
        "output_dir": str(output_dir),
        "file_count": len(manifest_records) + 1,
        "event_count": len(event_features),
        "reference_count": len(external_features),
        "source_count": len(sources),
        "total_bytes": sum(record["size_bytes"] for record in manifest_records)
        + (output_dir / "manifest.json").stat().st_size,
        "deterministic": True,
        "network_access": False,
        "earth_engine_queries_made": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site-data",
        help="output directory for the public package",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = build_package(args.output, root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P1_PUBLIC_RELEASE_BUILD_ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
