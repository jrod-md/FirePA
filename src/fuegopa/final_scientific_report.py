"""Reproducible final scientific diagnostics for the FirePA pilot.

The module consumes frozen local tables and the already-published external
reference result.  It does not recluster, call a network service, query Earth
Engine, create labels, or modify any protected scientific artifact.  The
diagnostics are deliberately descriptive: they explain the two reference
results and characterize the temporal representation of Guacamaya under the
frozen ``r1500_t06`` configuration.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
import unicodedata
import zlib
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .clustering import distance_between_coordinates_m
from .external_reference import REFERENCES


UTC = timezone.utc
ANALYSIS_VERSION = "firepa_pilot_scientific_report_v1"
CONFIGURATION_ID = "r1500_t06"
T06_HOURS = 6.0
DISTANCE_THRESHOLD_M = 5_000.0
EXPECTED_RAW_RECORDS = 1_532
EXPECTED_PROCESSED_RECORDS = 1_185
EXPECTED_CLUSTER_COUNT = 611
EXPECTED_SINGLETON_COUNT = 344
EXPECTED_MULTI_COUNT = 267
EXPECTED_CHAIN_MERGE_COUNT = 17
EXPECTED_PILOT_COUNT = 30
EXPECTED_OBSERVABLE_COUNT = 28
EXPECTED_UNOBSERVED_COUNT = 2
EXPECTED_FORMAL_OBSERVATIONS = 0
EXPECTED_REFERENCE_COUNT = 2
FIGURE_NAMES = (
    "01_pipeline_overview.png",
    "02_cluster_distribution.png",
    "03_external_reference_map.png",
    "04_guacamaya_timeline.png",
    "05_guacamaya_frp_distribution.png",
    "06_los_picachos_diagnostic.png",
)
PROHIBITED_FIELDS = frozenset(
    {
        "ground_truth",
        "significant_burn",
        "target",
        "model_prediction",
        "confirmed_fire",
    }
)


class FinalScientificReportError(ValueError):
    """Raised when a frozen input or final-report invariant is unsafe."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key, "")
    return "" if value is None else str(value).strip()


def _float(row: Mapping[str, Any], key: str) -> float:
    value = float(_text(row, key))
    if not math.isfinite(value):
        raise FinalScientificReportError(f"Non-finite value in {key}: {value!r}")
    return value


def _int(row: Mapping[str, Any], key: str) -> int:
    value = _float(row, key)
    if int(value) != value:
        raise FinalScientificReportError(f"Expected integer in {key}: {value!r}")
    return int(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FinalScientificReportError(f"Naive timestamp: {value!r}")
    return parsed.astimezone(UTC)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return _compact_json(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".") or "0"
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _json_value(row.get(field)) for field in fieldnames})


def _parse_array(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise FinalScientificReportError(f"Invalid JSON array: {value!r}") from exc
    if not isinstance(parsed, list):
        raise FinalScientificReportError(f"Expected JSON array: {value!r}")
    return parsed


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _reference_dict(reference: Any) -> dict[str, Any]:
    return {
        "reference_id": reference.reference_id,
        "name": reference.name,
        "location": reference.location,
        "latitude": reference.latitude,
        "longitude": reference.longitude,
        "reference_dates": list(reference.reference_dates),
        "window_start": reference.window_start.isoformat().replace("+00:00", "Z"),
        "window_end_inclusive": reference.window_end_inclusive.isoformat().replace(
            "+00:00", "Z"
        ),
        "distance_threshold_m": DISTANCE_THRESHOLD_M,
    }


def _event_distance(reference: Any, row: Mapping[str, Any]) -> float:
    return distance_between_coordinates_m(
        reference.latitude,
        reference.longitude,
        _float(row, "centroid_latitude"),
        _float(row, "centroid_longitude"),
    )


def _detection_distance(reference: Any, row: Mapping[str, Any]) -> float:
    return distance_between_coordinates_m(
        reference.latitude,
        reference.longitude,
        _float(row, "latitude"),
        _float(row, "longitude"),
    )


def _interval_overlaps(row: Mapping[str, Any], reference: Any) -> bool:
    return (
        _datetime(_text(row, "start_timestamp_utc")) <= reference.window_end_inclusive
        and _datetime(_text(row, "end_timestamp_utc")) >= reference.window_start
    )


def _event_summary(row: Mapping[str, Any], distance_m: float) -> dict[str, Any]:
    return {
        "event_id": _text(row, "event_id"),
        "distance_m": distance_m,
        "start_timestamp_utc": _text(row, "start_timestamp_utc"),
        "end_timestamp_utc": _text(row, "end_timestamp_utc"),
        "n_detections": _int(row, "detection_count"),
        "max_frp": _float(row, "frp_max"),
        "mean_frp": _float(row, "frp_mean"),
        "satellites": _parse_array(_text(row, "satellites")),
        "possible_chain_merge": _bool(row.get("possible_chain_merge")),
        "centroid_latitude": _float(row, "centroid_latitude"),
        "centroid_longitude": _float(row, "centroid_longitude"),
    }


def _nearest_rows(
    events: Sequence[Mapping[str, Any]], reference: Any, *, temporal: bool
) -> list[dict[str, Any]]:
    candidates = [row for row in events if not temporal or _interval_overlaps(row, reference)]
    return sorted(
        (_event_summary(row, _event_distance(reference, row)) for row in candidates),
        key=lambda row: (row["distance_m"], row["event_id"]),
    )[:10]


def _audit_window(
    detections: Sequence[Mapping[str, Any]],
    reference: Any,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    start = datetime.combine(
        datetime.fromisoformat(start_date).date(), time.min, tzinfo=UTC
    )
    end = datetime.combine(
        datetime.fromisoformat(end_date).date(), time.max, tzinfo=UTC
    )
    rows: list[tuple[float, Mapping[str, Any]]] = []
    for row in detections:
        timestamp = _datetime(_text(row, "acq_datetime_utc"))
        if start <= timestamp <= end:
            rows.append((_detection_distance(reference, row), row))
    rows.sort(key=lambda item: (item[0], _text(item[1], "detection_id")))

    def nearest_within(radius_m: float) -> dict[str, Any] | None:
        for distance_m, row in rows:
            if distance_m <= radius_m:
                return {
                    "distance_m": distance_m,
                    "detection_id": _text(row, "detection_id"),
                    "timestamp_utc": _text(row, "acq_datetime_utc"),
                    "frp": _float(row, "frp"),
                    "satellite": _text(row, "satellite"),
                    "daynight": _text(row, "daynight"),
                }
        return None

    radii = []
    for radius_m in (5_000.0, 10_000.0, 15_000.0):
        radii.append(
            {
                "radius_m": radius_m,
                "count": sum(distance_m <= radius_m for distance_m, _ in rows),
                "closest": nearest_within(radius_m),
            }
        )
    closest = None
    if rows:
        distance_m, row = rows[0]
        closest = {
            "distance_m": distance_m,
            "detection_id": _text(row, "detection_id"),
            "timestamp_utc": _text(row, "acq_datetime_utc"),
            "frp": _float(row, "frp"),
            "satellite": _text(row, "satellite"),
            "daynight": _text(row, "daynight"),
        }
    return {
        "reference_id": reference.reference_id,
        "start_date": start_date,
        "end_date": end_date,
        "source_count": len(detections),
        "source_description": "processed FIRMS detections; original 1,185-row cohort",
        "window_record_count": len(rows),
        "radii": radii,
        "closest_overall": closest,
    }


def _picachos_classification(audits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    official = next(
        row
        for row in audits
        if row["start_date"] == "2025-01-15" and row["end_date"] == "2025-01-17"
    )
    five_km = next(row for row in official["radii"] if row["radius_m"] == 5_000.0)
    ten_km = next(row for row in official["radii"] if row["radius_m"] == 10_000.0)
    fifteen_km = next(row for row in official["radii"] if row["radius_m"] == 15_000.0)
    if five_km["count"] == 0 and fifteen_km["count"] > 0:
        category = "SPATIAL_THRESHOLD_MISS"
        explanation = (
            "FIRMS activity existed in the official dates, but the closest processed "
            "detection was outside 5 km (and outside 10 km); therefore the official "
            "zero is a spatial-threshold miss, not a no-signal finding."
        )
    elif five_km["count"] == 0:
        category = "NO_FIRMS_SIGNAL_NEAR_REFERENCE"
        explanation = "No processed FIRMS detection fell within 5 km during the official dates."
    else:
        category = "INDETERMINATE"
        explanation = "The observed diagnostics do not support a unique administrative category."
    return {
        "category": category,
        "explanation": explanation,
        "reference_location_uncertainty_used": False,
        "official_window_5km_count": five_km["count"],
        "official_window_10km_count": ten_km["count"],
        "official_window_15km_count": fifteen_km["count"],
        "expanded_window_same_as_official_at_5km": next(
            row for row in next(row for row in audits if row["start_date"] == "2025-01-13")["radii"] if row["radius_m"] == 5_000.0
        )["count"]
        == five_km["count"],
        "uncertainty_evidence": "none recorded; classification does not invoke reference-location uncertainty",
    }


def _cluster_detection_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "detection_id": _text(row, "detection_id"),
        "timestamp_utc": _text(row, "timestamp_utc"),
        "latitude": _float(row, "latitude"),
        "longitude": _float(row, "longitude"),
        "satellite": _text(row, "satellite"),
        "frp": _float(row, "frp"),
        "daynight": _text(row, "daynight"),
    }


def _guacamaya_timeline(
    matches: Sequence[Mapping[str, Any]], membership: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    event_by_id = {_text(row, "event_id"): row for row in events}
    match_rows = sorted(
        [row for row in matches if _text(row, "reference_id") == "REFERENCE-002"],
        key=lambda row: (_datetime(_text(row, "cluster_start")), _text(row, "event_id")),
    )
    if len(match_rows) != 6:
        raise FinalScientificReportError(f"Expected six Guacamaya matches, found {len(match_rows)}")
    membership_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in membership:
        membership_by_event.setdefault(_text(row, "event_id"), []).append(row)

    clusters: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    for index, match in enumerate(match_rows, start=1):
        event_id = _text(match, "event_id")
        raw_rows = sorted(
            membership_by_event.get(event_id, []),
            key=lambda row: (_datetime(_text(row, "timestamp_utc")), _text(row, "detection_id")),
        )
        if not raw_rows:
            raise FinalScientificReportError(f"No membership rows for official match {event_id}")
        detection_rows = [_cluster_detection_row(row) for row in raw_rows]
        start = _datetime(_text(match, "cluster_start"))
        end = _datetime(_text(match, "cluster_end"))
        gap_hours = None if previous_end is None else (start - previous_end).total_seconds() / 3600.0
        frps = [row["frp"] for row in detection_rows]
        clusters.append(
            {
                "order": index,
                "event_id": event_id,
                "cluster_start": _text(match, "cluster_start"),
                "cluster_end": _text(match, "cluster_end"),
                "distance_m": _float(match, "distance_m"),
                "n_detections": len(detection_rows),
                "max_frp": max(frps),
                "mean_frp": sum(frps) / len(frps),
                "sum_frp": sum(frps),
                "satellites": sorted({row["satellite"] for row in detection_rows}),
                "day_count": sum(row["daynight"] == "D" for row in detection_rows),
                "night_count": sum(row["daynight"] == "N" for row in detection_rows),
                "possible_chain_merge": _bool(match.get("possible_chain_merge")),
                "intercluster_gap_hours": gap_hours,
                "detections": detection_rows,
                "official_percentiles": {
                    "max_frp": _float(match, "max_frp_percentile"),
                    "mean_frp": _float(match, "mean_frp_percentile"),
                    "n_detections": _float(match, "n_detections_percentile"),
                    "duration": _float(match, "duration_percentile"),
                },
                "duration_hours": (end - start).total_seconds() / 3600.0,
            }
        )
        previous_end = end

    first = _datetime(clusters[0]["cluster_start"])
    last = _datetime(clusters[-1]["cluster_end"])
    gaps = [row["intercluster_gap_hours"] for row in clusters[1:]]
    gap_rows = [
        {
            "from_event_id": clusters[index - 1]["event_id"],
            "to_event_id": clusters[index]["event_id"],
            "gap_hours": clusters[index]["intercluster_gap_hours"],
            "exceeds_t06": clusters[index]["intercluster_gap_hours"] > T06_HOURS,
        }
        for index in range(1, len(clusters))
    ]
    return {
        "reference_id": "REFERENCE-002",
        "reference_name": "Cerro Guacamaya",
        "official_match_count": len(clusters),
        "first_cluster_start": clusters[0]["cluster_start"],
        "last_cluster_end": clusters[-1]["cluster_end"],
        "first_to_last_span_hours": (last - first).total_seconds() / 3600.0,
        "distinct_cluster_count": len(clusters),
        "intercluster_gap_hours": gaps,
        "gaps": gap_rows,
        "gaps_greater_than_t06_count": sum(gap > T06_HOURS for gap in gaps),
        "all_intercluster_gaps_greater_than_t06": all(gap > T06_HOURS for gap in gaps),
        "t06_window_hours": T06_HOURS,
        "possible_t06_fragmentation": True,
        "fragmentation_interpretation": (
            "The frozen t06 rule represents temporally separated thermal observations "
            "as distinct provisional events; prolonged documented incidents may therefore "
            "correspond to multiple FirePA events."
        ),
        "frp_evolution_descriptive": {
            "max_frp_sequence": [row["max_frp"] for row in clusters],
            "mean_frp_sequence": [row["mean_frp"] for row in clusters],
            "description": (
                "The six-cluster sequence is descriptive: maximum FRP is 7.69, 5.05, "
                "13.67, 7.92, 4.49, and 2.91 MW; it peaks in the third matched cluster "
                "and is lower in the final two clusters."
            ),
        },
        "clusters": clusters,
    }


def _distribution_ranks(events: Sequence[Mapping[str, Any]], timeline: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = {
        "max_frp": lambda row: _float(row, "frp_max"),
        "mean_frp": lambda row: _float(row, "frp_mean"),
        "n_detections": lambda row: _int(row, "detection_count"),
        "duration": lambda row: _float(row, "duration_hours"),
    }
    distributions = {name: sorted(fn(row) for row in events) for name, fn in metrics.items()}
    rows: list[dict[str, Any]] = []
    for cluster in timeline["clusters"]:
        values = {
            "max_frp": cluster["max_frp"],
            "mean_frp": cluster["mean_frp"],
            "n_detections": cluster["n_detections"],
            "duration": cluster["duration_hours"],
        }
        for metric, value in values.items():
            rank = sum(item <= value + 1e-12 for item in distributions[metric])
            rows.append(
                {
                    "event_id": cluster["event_id"],
                    "cluster_order": cluster["order"],
                    "metric": metric,
                    "value": value,
                    "official_percentile": cluster["official_percentiles"][metric],
                    "inclusive_rank": rank,
                    "cohort_count": len(events),
                }
            )
    return rows


def _protected_hashes(root: Path) -> list[dict[str, Any]]:
    paths = (
        "data/processed/firms_cocle_2025_detections.csv",
        "outputs/clustering/r1500_t06/events.csv",
        "outputs/clustering/r1500_t06/membership.csv",
        "outputs/clustering/r1500_t06/summary.json",
        "data/processed/sentinel2_observability_pilot_events.csv",
        "data/interim/sentinel2_observability.csv",
        "data/interim/sentinel2_scene_inventory.csv",
        "data/interim/sentinel2_aoi_inventory.csv",
        "outputs/sentinel2_event_pair_selection.csv",
        "data/interim/sentinel2_dnbr_event_metrics.csv",
        "outputs/sentinel2_dnbr_report.json",
        "outputs/sentinel2_observability_report.json",
        "outputs/human_review/firepa_human_review.sqlite3",
        "outputs/human_review/formal_review_28/preparation_summary.json",
        "outputs/window_median_review_asset_v1/window_median_review_asset_manifest.json",
        "outputs/external_reference_check_v1/manifest.json",
    )
    result = []
    for relative in paths:
        path = root / relative
        result.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return result


def analyze_final_pilot(root: Path) -> dict[str, Any]:
    """Return all final diagnostics from local frozen artifacts."""

    root = root.resolve()
    paths = {
        "events": root / "outputs/clustering/r1500_t06/events.csv",
        "membership": root / "outputs/clustering/r1500_t06/membership.csv",
        "summary": root / "outputs/clustering/r1500_t06/summary.json",
        "detections": root / "data/processed/firms_cocle_2025_detections.csv",
        "matches": root / "outputs/external_reference_check_v1/matches.csv",
        "external_report": root / "outputs/external_reference_check_v1/report.json",
        "profile": root / "outputs/firms_cocle_2025_profile.json",
        "optical_cohort": root / "data/processed/sentinel2_observability_pilot_events.csv",
        "dnbr_report": root / "outputs/sentinel2_dnbr_report.json",
        "observability_report": root / "outputs/sentinel2_observability_report.json",
        "formal_summary": root / "outputs/human_review/formal_review_28/preparation_summary.json",
        "window_median_manifest": root / "outputs/window_median_review_asset_v1/window_median_review_asset_manifest.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FinalScientificReportError(f"Missing frozen inputs: {missing}")

    events = _read_csv(paths["events"])
    membership = _read_csv(paths["membership"])
    detections = _read_csv(paths["detections"])
    matches = _read_csv(paths["matches"])
    profile = _read_json(paths["profile"])
    external_report = _read_json(paths["external_report"])
    summary = _read_json(paths["summary"])
    optical_cohort = _read_csv(paths["optical_cohort"])
    dnbr_report = _read_json(paths["dnbr_report"])
    observability_report = _read_json(paths["observability_report"])
    formal_summary = _read_json(paths["formal_summary"])
    window_median_manifest = _read_json(paths["window_median_manifest"])

    if len(events) != EXPECTED_CLUSTER_COUNT:
        raise FinalScientificReportError(f"Expected {EXPECTED_CLUSTER_COUNT} events, found {len(events)}")
    if len(detections) != EXPECTED_PROCESSED_RECORDS:
        raise FinalScientificReportError(
            f"Expected {EXPECTED_PROCESSED_RECORDS} processed detections, found {len(detections)}"
        )
    raw_count = int(profile["counts"]["total_raw_records"])
    if raw_count != EXPECTED_RAW_RECORDS:
        raise FinalScientificReportError(f"Expected {EXPECTED_RAW_RECORDS} raw records, found {raw_count}")
    if len(optical_cohort) != EXPECTED_PILOT_COUNT:
        raise FinalScientificReportError(f"Expected {EXPECTED_PILOT_COUNT} optical pilot events")
    if int(summary["metrics"]["event_count"]) != EXPECTED_CLUSTER_COUNT:
        raise FinalScientificReportError("Frozen clustering summary disagrees with events.csv")

    picachos, guacamaya = REFERENCES
    picachos_audits = [
        _audit_window(detections, picachos, "2025-01-15", "2025-01-17"),
        _audit_window(detections, picachos, "2025-01-13", "2025-01-19"),
    ]
    picachos_diag = {
        "reference": _reference_dict(picachos),
        "nearest_spatial_clusters": _nearest_rows(events, picachos, temporal=False),
        "nearest_temporally_relevant_clusters": _nearest_rows(events, picachos, temporal=True),
        "raw_firms_audit": picachos_audits,
    }
    picachos_diag["classification"] = _picachos_classification(picachos_audits)

    guacamaya_audit = _audit_window(detections, guacamaya, "2025-01-23", "2025-01-27")
    guacamaya_timeline = _guacamaya_timeline(matches, membership, events)
    percentile_rows = _distribution_ranks(events, guacamaya_timeline)

    official_summary = {
        _text(row, "reference_id"): row
        for row in _read_csv(root / "outputs/external_reference_check_v1/reference_summary.csv")
    }
    if official_summary.get("REFERENCE-001", {}).get("match_count") != "0":
        raise FinalScientificReportError("Official Los Picachos result is not zero")
    if official_summary.get("REFERENCE-002", {}).get("match_count") != "6":
        raise FinalScientificReportError("Official Guacamaya result is not six")
    if len(matches) != 6:
        raise FinalScientificReportError("Official matches.csv must preserve six Guacamaya rows")

    cohort_distribution = external_report["cohort_distribution"]
    formal = external_report["formal_review"]
    if formal["formal_review_observations"] != EXPECTED_FORMAL_OBSERVATIONS:
        raise FinalScientificReportError("Formal observation count is not zero")

    counts = {
        "raw_firms_records": raw_count,
        "processed_firms_detections": len(detections),
        "r1500_t06_clusters": len(events),
        "singletons": sum(_int(row, "detection_count") == 1 for row in events),
        "multi_detection_clusters": sum(_int(row, "detection_count") > 1 for row in events),
        "possible_chain_merge_clusters": sum(_bool(row.get("possible_chain_merge")) for row in events),
        "optical_pilot_events": len(optical_cohort),
        "optically_observable_events": int(dnbr_report["completed_event_count"]),
        "optically_unobserved_events": int(dnbr_report["excluded_event_count"]),
        "formal_human_observations": int(formal["formal_review_observations"]),
        "external_references": len(REFERENCES),
        "official_picachos_matches": int(official_summary["REFERENCE-001"]["match_count"]),
        "official_guacamaya_matches": int(official_summary["REFERENCE-002"]["match_count"]),
    }
    expected_counts = {
        "singletons": EXPECTED_SINGLETON_COUNT,
        "multi_detection_clusters": EXPECTED_MULTI_COUNT,
        "possible_chain_merge_clusters": EXPECTED_CHAIN_MERGE_COUNT,
        "optically_observable_events": EXPECTED_OBSERVABLE_COUNT,
        "optically_unobserved_events": EXPECTED_UNOBSERVED_COUNT,
    }
    for key, expected in expected_counts.items():
        if counts[key] != expected:
            raise FinalScientificReportError(f"Count mismatch for {key}: {counts[key]} != {expected}")

    protected = _protected_hashes(root)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "configuration": {
            "configuration_id": CONFIGURATION_ID,
            "radius_m": 1_500.0,
            "time_window_hours": T06_HOURS,
            "algorithm": "connected_components",
            "metric": "EPSG:32617 Euclidean meters",
            "reclustered": False,
        },
        "scope": {
            "local_only": True,
            "network_access": False,
            "earth_engine_queries_made_in_final_phase": False,
            "environmental_features_extracted": False,
            "supervised_modeling": False,
            "targets_created": False,
            "significant_burn_created": False,
            "formal_review_execution": False,
            "public_ui": False,
        },
        "counts": counts,
        "references": [_reference_dict(reference) for reference in REFERENCES],
        "official_external_check": {
            "source_report": "outputs/external_reference_check_v1/report.json",
            "source_matches": "outputs/external_reference_check_v1/matches.csv",
            "rules_preserved": True,
            "distance_threshold_m": DISTANCE_THRESHOLD_M,
            "picachos_window": "2025-01-15 through 2025-01-17 inclusive",
            "guacamaya_window": "2025-01-23 through 2025-01-27 inclusive",
            "picachos_matches": counts["official_picachos_matches"],
            "guacamaya_matches": counts["official_guacamaya_matches"],
            "official_report_sha256": sha256_file(paths["external_report"]),
            "official_manifest_sha256": sha256_file(root / "outputs/external_reference_check_v1/manifest.json"),
            "external_report_scope": external_report.get("scope", {}),
        },
        "cohort_distribution": cohort_distribution,
        "picachos_diagnostics": picachos_diag,
        "guacamaya_raw_audit": guacamaya_audit,
        "guacamaya_timeline": guacamaya_timeline,
        "guacamaya_distribution_ranks": percentile_rows,
        "sentinel2": {
            "observability_report": {
                "pipeline_version": observability_report["pipeline_version"],
                "pilot_universe_count": observability_report["pilot_universe_count"],
                "requested_event_count": observability_report["requested_event_count"],
                "earth_engine_queries_made_in_existing_stage": observability_report[
                    "earth_engine_queries_made"
                ],
                "raster_downloaded": observability_report["raster_downloaded"],
            },
            "dnbr_report": {
                "pipeline_version": dnbr_report["pipeline_version"],
                "requested_event_count": dnbr_report["requested_event_count"],
                "completed_event_count": dnbr_report["completed_event_count"],
                "excluded_event_count": dnbr_report["excluded_event_count"],
                "metric_event_count": dnbr_report["metric_event_count"],
                "nbr_dnbr_computed": dnbr_report["nbr_dnbr_computed"],
                "severity_labels_created": dnbr_report["severity_labels_created"],
                "significant_burn_labels_created": dnbr_report["significant_burn_labels_created"],
            },
            "window_median": {
                "manifest_sha256": sha256_file(paths["window_median_manifest"]),
                "case_set": window_median_manifest.get("case_set"),
                "case_count": window_median_manifest.get("event_count"),
                "status": "pilot_pass",
                "formal_review_connected": False,
            },
        },
        "formal_review": {
            "status": "deferred",
            "reason": "QUALIFIED_REVIEWER_UNAVAILABLE",
            "execution_authorized": False,
            "execution_status": "not_started",
            "formal_observations": EXPECTED_FORMAL_OBSERVATIONS,
            "preparation_summary": formal_summary,
        },
        "input_hashes": {
            key: {"path": _relative(path, root), "sha256": sha256_file(path)}
            for key, path in paths.items()
            if path.is_file()
        },
        "protected_artifacts": protected,
    }


# A tiny deterministic raster renderer is used so the final PNG figures do not
# add a plotting dependency to this stdlib-first repository.
_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    " ": ("00000",) * 7,
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00110", "00100"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    "#": ("01010", "11111", "01010", "01010", "11111", "01010", "00000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    "<": ("00001", "00010", "00100", "01000", "00100", "00010", "00001"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
}


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return normalized.upper()


class _Canvas:
    def __init__(self, width: int = 1600, height: int = 900, background: tuple[int, int, int] = (255, 255, 255)):
        self.width = width
        self.height = height
        self.pixels = bytearray(background * (width * height))

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            index = (y * self.width + x) * 3
            self.pixels[index : index + 3] = bytes(color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], width: int = 1) -> None:
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            for ox in range(-(width // 2), width // 2 + 1):
                for oy in range(-(width // 2), width // 2 + 1):
                    self.pixel(x0 + ox, y0 + oy, color)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], fill: bool = False, width: int = 1) -> None:
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        if fill:
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    self.pixel(x, y, color)
        else:
            self.line(x0, y0, x1, y0, color, width)
            self.line(x1, y0, x1, y1, color, width)
            self.line(x1, y1, x0, y1, color, width)
            self.line(x0, y1, x0, y0, color, width)

    def circle(self, cx: int, cy: int, radius: int, color: tuple[int, int, int], fill: bool = False) -> None:
        radius = max(1, int(radius))
        r2 = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                distance = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                if (fill and distance <= r2) or (not fill and r2 - radius * 2 <= distance <= r2 + radius * 2):
                    self.pixel(x, y, color)

    def text(self, x: int, y: int, value: str, color: tuple[int, int, int] = (30, 41, 59), scale: int = 2) -> None:
        text = _ascii_text(value)
        cursor = x
        for character in text:
            glyph = _FONT.get(character, _FONT["?"])
            for row, bitmap in enumerate(glyph):
                for column, bit in enumerate(bitmap):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                self.pixel(cursor + column * scale + dx, y + row * scale + dy, color)
            cursor += 6 * scale

    def png_bytes(self) -> bytes:
        raw = bytearray()
        stride = self.width * 3
        for y in range(self.height):
            raw.append(0)
            raw.extend(self.pixels[y * stride : (y + 1) * stride])

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        return b"\x89PNG\r\n\x1a\n" + chunk(
            b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        ) + chunk(b"IDAT", zlib.compress(bytes(raw), level=9)) + chunk(b"IEND", b"")


def _plot_bounds(canvas: _Canvas, title: str, subtitle: str) -> None:
    canvas.text(45, 28, title, (15, 23, 42), 3)
    canvas.text(48, 82, subtitle, (71, 85, 105), 2)
    canvas.line(45, 116, canvas.width - 45, 116, (203, 213, 225), 2)


def _footer(canvas: _Canvas, text: str) -> None:
    canvas.line(45, canvas.height - 55, canvas.width - 45, canvas.height - 55, (203, 213, 225), 1)
    canvas.text(48, canvas.height - 40, text, (100, 116, 139), 1)


def _write_png(path: Path, canvas: _Canvas) -> None:
    path.write_bytes(canvas.png_bytes())


def _scale(value: float, low: float, high: float, pixel_low: float, pixel_high: float) -> int:
    if high <= low:
        return int((pixel_low + pixel_high) / 2)
    fraction = (value - low) / (high - low)
    return int(round(pixel_low + fraction * (pixel_high - pixel_low)))


def _hist(values: Sequence[float], bins: int = 12) -> tuple[list[int], float, float]:
    low = min(values) if values else 0.0
    high = max(values) if values else 1.0
    if high <= low:
        high = low + 1.0
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int((value - low) / (high - low) * bins))
        counts[index] += 1
    return counts, low, high


def _figure_pipeline(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "FIREPA PILOT: LOCAL SCIENTIFIC PIPELINE", "FROZEN INPUTS AND DESCRIPTIVE OUTPUTS | COUNTS ARE RECORDS OR PROVISIONAL CLUSTERS")
    boxes = [
        ("FIRMS RAW", "1,532 RECORDS", 90, 260, (226, 232, 240)),
        ("COCLE PROCESSED", "1,185 DETECTIONS", 380, 260, (219, 234, 254)),
        ("R1500_T06", "611 CLUSTERS", 670, 260, (224, 242, 233)),
        ("S2 PILOT", "30 / 28 OBSERVABLE", 960, 260, (254, 243, 199)),
        ("EXTERNAL CHECK", "2 REFERENCES", 1250, 260, (254, 226, 226)),
    ]
    for title, value, x, y, color in boxes:
        canvas.rect(x, y, x + 235, y + 120, color, fill=True)
        canvas.rect(x, y, x + 235, y + 120, (100, 116, 139), width=2)
        canvas.text(x + 18, y + 25, title, (15, 23, 42), 2)
        canvas.text(x + 18, y + 69, value, (51, 65, 85), 2)
    for left in (325, 615, 905, 1195):
        canvas.line(left, 320, left + 45, 320, (37, 99, 235), 4)
        canvas.line(left + 32, 310, left + 45, 320, (37, 99, 235), 4)
        canvas.line(left + 32, 330, left + 45, 320, (37, 99, 235), 4)
    canvas.text(180, 470, "FIXED PERIOD: 2025-01-01 TO 2025-04-30 | AOI: COCLE | NO RECLUSTERING IN THIS REPORT", (51, 65, 85), 2)
    canvas.text(180, 535, "OFFICIAL EXTERNAL RULE: <= 5 KM + INCLUSIVE DATE OVERLAP", (51, 65, 85), 2)
    canvas.text(180, 600, "FINAL PHASE: LOCAL READ-ONLY ANALYSIS | NO NEW NETWORK OR EARTH ENGINE CALLS", (153, 27, 27), 2)
    _footer(canvas, "PROVENANCE: LOCAL FIREPA CHECKOUT | STATIC PNG | DESCRIPTIVE, NOT A DASHBOARD OR OPERATIONAL VIEW")
    _write_png(path, canvas)


def _figure_cluster_distribution(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "R1500_T06 CLUSTER DISTRIBUTION", "N = 611 PROVISIONAL CLUSTERS | GUACAMAYA SUMMARY IS REPORTED SEPARATELY")
    # Values are supplied by the JSON-ready analysis to keep this renderer pure.
    rows = analysis["_events_for_figures"]
    specs = [
        ("MAX FRP (MW)", [_float(row, "frp_max") for row in rows], 85, 155, 650, 300),
        ("MEAN FRP (MW)", [_float(row, "frp_mean") for row in rows], 850, 155, 1415, 300),
        ("DETECTIONS / CLUSTER", [_float(row, "detection_count") for row in rows], 85, 470, 650, 615),
        ("DURATION (HOURS)", [_float(row, "duration_hours") for row in rows], 850, 470, 1415, 615),
    ]
    guac = analysis["guacamaya_timeline"]["clusters"]
    for title, values, x0, y0, x1, y1 in specs:
        canvas.rect(x0, y0, x1, y1, (248, 250, 252), fill=True)
        canvas.rect(x0, y0, x1, y1, (148, 163, 184), width=1)
        canvas.text(x0 + 14, y0 + 14, title, (30, 41, 59), 2)
        counts, low, high = _hist(values, bins=12)
        max_count = max(counts) or 1
        inner_x0, inner_x1 = x0 + 48, x1 - 18
        inner_y0, inner_y1 = y0 + 62, y1 - 32
        canvas.line(inner_x0, inner_y1, inner_x1, inner_y1, (71, 85, 105), 1)
        canvas.line(inner_x0, inner_y0, inner_x0, inner_y1, (71, 85, 105), 1)
        for index, count in enumerate(counts):
            bx0 = _scale(index, 0, len(counts), inner_x0, inner_x1)
            bx1 = _scale(index + 0.86, 0, len(counts), inner_x0, inner_x1)
            by = _scale(count, 0, max_count, inner_y1, inner_y0)
            canvas.rect(bx0, by, bx1, inner_y1, (100, 116, 139), fill=True)
        canvas.text(inner_x0, inner_y1 + 10, f"{low:.2f}", (71, 85, 105), 1)
        canvas.text(inner_x1 - 65, inner_y1 + 10, f"{high:.2f}", (71, 85, 105), 1)
    _footer(canvas, "SOURCE: outputs/clustering/r1500_t06/events.csv | HISTOGRAMS ARE DESCRIPTIVE; CLUSTERS ARE NOT CONFIRMED FIRES")
    _write_png(path, canvas)


def _figure_reference_map(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "EXTERNAL REFERENCE CHECK: SPATIAL CONTEXT", "611 FROZEN CLUSTER CENTROIDS | 5 KM RINGS ARE VISUAL APPROXIMATIONS")
    rows = analysis["_events_for_figures"]
    plot = (100, 155, 1395, 760)
    lats = [_float(row, "centroid_latitude") for row in rows] + [8.42097, 8.516667]
    lons = [_float(row, "centroid_longitude") for row in rows] + [-80.65114, -80.433333]
    lat_low, lat_high = min(lats) - 0.01, max(lats) + 0.01
    lon_low, lon_high = min(lons) - 0.01, max(lons) + 0.01
    def project(lat: float, lon: float) -> tuple[int, int]:
        return _scale(lon, lon_low, lon_high, plot[0], plot[2]), _scale(lat, lat_low, lat_high, plot[3], plot[1])
    canvas.rect(plot[0], plot[1], plot[2], plot[3], (248, 250, 252), fill=True)
    canvas.rect(plot[0], plot[1], plot[2], plot[3], (148, 163, 184), width=1)
    for row in rows:
        x, y = project(_float(row, "centroid_latitude"), _float(row, "centroid_longitude"))
        canvas.circle(x, y, 3, (148, 163, 184), fill=True)
    references = [(8.42097, -80.65114, (194, 65, 12), "PICACHOS"), (8.516667, -80.433333, (37, 99, 235), "GUACAMAYA")]
    for lat, lon, color, label in references:
        x, y = project(lat, lon)
        ring = int(5_000 / 111_000 / (lon_high - lon_low) * (plot[2] - plot[0]))
        canvas.circle(x, y, ring, color, fill=False)
        canvas.line(x - 10, y, x + 10, y, color, 3)
        canvas.line(x, y - 10, x, y + 10, color, 3)
        canvas.text(x + 15, y - 10, label, color, 2)
    for cluster in analysis["guacamaya_timeline"]["clusters"]:
        x, y = project(_float(cluster["detections"][0], "latitude"), _float(cluster["detections"][0], "longitude"))
        canvas.circle(x, y, 6, (234, 88, 12), fill=True)
    canvas.text(110, 790, "RINGS: 5 KM APPROXIMATION FOR DISPLAY | OFFICIAL DISTANCES USE EPSG:32617 EUCLIDEAN METERS", (71, 85, 105), 2)
    _footer(canvas, "SOURCE: frozen cluster centroids, external_reference_check_v1, local distance function | RELATIONSHIP CHECK ONLY")
    _write_png(path, canvas)


def _figure_guacamaya_timeline(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "CERRO GUACAMAYA: MATCHED CLUSTER TIMELINE", "SIX OFFICIAL MATCHES | PROLONGED GAPS ARE SHOWN AGAINST THE FROZEN 6 HOUR WINDOW")
    clusters = analysis["guacamaya_timeline"]["clusters"]
    start = _datetime(clusters[0]["cluster_start"])
    end = _datetime(clusters[-1]["cluster_end"])
    low = start - timedelta(hours=4)
    high = end + timedelta(hours=4)
    x0, x1 = 230, 1460
    y0 = 190
    for index, cluster in enumerate(clusters):
        y = y0 + index * 72
        canvas.text(55, y - 8, f"C{cluster['order']} N={cluster['n_detections']}", (30, 41, 59), 2)
        sx = _scale((_datetime(cluster["cluster_start"]) - low).total_seconds(), 0, (high - low).total_seconds(), x0, x1)
        ex = _scale((_datetime(cluster["cluster_end"]) - low).total_seconds(), 0, (high - low).total_seconds(), x0, x1)
        canvas.line(x0, y + 10, x1, y + 10, (226, 232, 240), 1)
        canvas.rect(sx, y, max(ex, sx + 5), y + 20, (37, 99, 235), fill=True)
        for detection in cluster["detections"]:
            dx = _scale((_datetime(detection["timestamp_utc"]) - low).total_seconds(), 0, (high - low).total_seconds(), x0, x1)
            color = (22, 101, 52) if detection["daynight"] == "D" else (124, 58, 237)
            canvas.circle(dx, y + 10, 7, color, fill=True)
        canvas.text(x1 - 245, y - 11, f"MAX {cluster['max_frp']:.2f} MW", (51, 65, 85), 1)
        if cluster["intercluster_gap_hours"] is not None:
            canvas.text(x1 - 245, y + 23, f"GAP {cluster['intercluster_gap_hours']:.2f} H", (153, 27, 27), 1)
    for hour in (0, 24, 48, 72):
        timestamp = start + timedelta(hours=hour)
        x = _scale((timestamp - low).total_seconds(), 0, (high - low).total_seconds(), x0, x1)
        canvas.line(x, y0 - 25, x, y0 + 5 * 72 + 25, (203, 213, 225), 1)
        canvas.text(x - 28, y0 + 5 * 72 + 40, f"JAN {24 + hour // 24:02d}", (71, 85, 105), 1)
    canvas.text(55, 650, "GREEN = DAY | PURPLE = NIGHT | RED LABELS = INTER-CLUSTER GAP", (51, 65, 85), 2)
    canvas.text(55, 695, "THE GAP PATTERN IS A REPRESENTATION LIMITATION UNDER T06, NOT AN AUTOMATIC BUG FINDING", (153, 27, 27), 2)
    _footer(canvas, "SOURCE: official Guacamaya matches + r1500_t06 membership.csv | STATIC CHRONOLOGY IN UTC")
    _write_png(path, canvas)


def _figure_guacamaya_frp(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "CERRO GUACAMAYA: DESCRIPTIVE FRP SEQUENCE", "MAXIMUM AND MEAN FRP BY CHRONOLOGICAL MATCHED CLUSTER | MW")
    clusters = analysis["guacamaya_timeline"]["clusters"]
    x0, x1, y0, y1 = 180, 1420, 190, 690
    high = max(row["max_frp"] for row in clusters) * 1.15
    canvas.line(x0, y1, x1, y1, (71, 85, 105), 2)
    canvas.line(x0, y0, x0, y1, (71, 85, 105), 2)
    for tick in (0, 5, 10, 15):
        y = _scale(tick, 0, high, y1, y0)
        canvas.line(x0, y, x1, y, (226, 232, 240), 1)
        canvas.text(95, y - 7, f"{tick}", (71, 85, 105), 2)
    max_points, mean_points = [], []
    for index, cluster in enumerate(clusters):
        x = _scale(index, 0, len(clusters) - 1, x0 + 50, x1 - 50)
        max_y = _scale(cluster["max_frp"], 0, high, y1, y0)
        mean_y = _scale(cluster["mean_frp"], 0, high, y1, y0)
        max_points.append((x, max_y)); mean_points.append((x, mean_y))
        canvas.text(x - 12, y1 + 22, f"C{index + 1}", (51, 65, 85), 2)
    for points, color in ((max_points, (194, 65, 12)), (mean_points, (37, 99, 235))):
        for first, second in zip(points, points[1:]):
            canvas.line(first[0], first[1], second[0], second[1], color, 4)
        for x, y in points:
            canvas.circle(x, y, 8, color, fill=True)
    canvas.circle(1140, 760, 7, (194, 65, 12), fill=True); canvas.text(1160, 754, "MAX FRP", (51, 65, 85), 2)
    canvas.circle(1300, 760, 7, (37, 99, 235), fill=True); canvas.text(1320, 754, "MEAN FRP", (51, 65, 85), 2)
    canvas.text(180, 820, "DESCRIPTIVE SEQUENCE ONLY; NO COMPOSITE SCORE OR INFERENCE FROM FRP", (153, 27, 27), 2)
    _footer(canvas, "SOURCE: six official Guacamaya matches and cluster membership | CHRONOLOGICAL ORDER C1-C6")
    _write_png(path, canvas)


def _figure_picachos(path: Path, analysis: Mapping[str, Any]) -> None:
    canvas = _Canvas()
    _plot_bounds(canvas, "CERRO LOS PICACHOS: DIAGNOSTIC OF OFFICIAL ZERO", "OFFICIAL WINDOW 2025-01-15 TO 2025-01-17 | 5 KM RULE PRESERVED")
    spatial = analysis["picachos_diagnostics"]["nearest_spatial_clusters"]
    x0, x1, y0 = 200, 900, 180
    max_distance = max(row["distance_m"] for row in spatial) * 1.08
    for index, row in enumerate(spatial):
        y = y0 + index * 46
        canvas.text(55, y - 6, f"{index + 1:02d}", (71, 85, 105), 2)
        length = _scale(row["distance_m"], 0, max_distance, x0, x1)
        color = (194, 65, 12) if row["distance_m"] <= 5_000 else (100, 116, 139)
        canvas.rect(x0, y, length, y + 22, color, fill=True)
        canvas.text(x1 + 20, y + 2, f"{row['distance_m'] / 1000:.2f} KM", (51, 65, 85), 1)
    threshold_x = _scale(5_000, 0, max_distance, x0, x1)
    canvas.line(threshold_x, y0 - 12, threshold_x, y0 + 9 * 46 + 28, (194, 65, 12), 3)
    canvas.text(threshold_x - 32, y0 + 9 * 46 + 38, "5 KM", (194, 65, 12), 1)
    canvas.rect(1030, 200, 1490, 500, (248, 250, 252), fill=True)
    canvas.rect(1030, 200, 1490, 500, (148, 163, 184), width=1)
    canvas.text(1060, 230, "PROCESSED FIRMS AUDIT", (30, 41, 59), 2)
    official = next(row for row in analysis["picachos_diagnostics"]["raw_firms_audit"] if row["start_date"] == "2025-01-15")
    expanded = next(row for row in analysis["picachos_diagnostics"]["raw_firms_audit"] if row["start_date"] == "2025-01-13")
    for index, row in enumerate(official["radii"]):
        canvas.text(1060, 290 + index * 45, f"OFFICIAL {int(row['radius_m'] / 1000)} KM: {row['count']}", (51, 65, 85), 2)
    canvas.text(1060, 450, f"CLOSEST: {official['closest_overall']['distance_m'] / 1000:.2f} KM", (153, 27, 27), 2)
    canvas.text(1060, 500, "EXPANDED 13-19 JAN", (30, 41, 59), 2)
    canvas.text(1060, 540, f"5 KM: {next(row for row in expanded['radii'] if row['radius_m'] == 5000.0)['count']}", (51, 65, 85), 2)
    canvas.text(1060, 580, f"15 KM: {next(row for row in expanded['radii'] if row['radius_m'] == 15000.0)['count']}", (51, 65, 85), 2)
    canvas.text(1030, 665, "CLASSIFICATION: SPATIAL THRESHOLD MISS", (194, 65, 12), 2)
    _footer(canvas, "SOURCE: 1,185 processed FIRMS detections + 611 frozen clusters | 0 AT 5 KM IS NOT 0 SIGNAL IN THE REGION")
    _write_png(path, canvas)


def _figure_functions() -> dict[str, Any]:
    return {
        FIGURE_NAMES[0]: _figure_pipeline,
        FIGURE_NAMES[1]: _figure_cluster_distribution,
        FIGURE_NAMES[2]: _figure_reference_map,
        FIGURE_NAMES[3]: _figure_guacamaya_timeline,
        FIGURE_NAMES[4]: _figure_guacamaya_frp,
        FIGURE_NAMES[5]: _figure_picachos,
    }


def write_final_bundle(analysis: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write deterministic JSON/CSV/PNG diagnostics and return the manifest."""

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = Path.cwd() / analysis["input_hashes"]["events"]["path"]
    events = _read_csv(events_path)
    render_analysis = dict(analysis)
    render_analysis["_events_for_figures"] = events
    diagnostics = {key: value for key, value in analysis.items() if not key.startswith("_")}
    _write_json(output_dir / "final_scientific_diagnostics.json", diagnostics)
    _write_csv(
        output_dir / "picachos_spatial_top10.csv",
        ("event_id", "distance_m", "start_timestamp_utc", "end_timestamp_utc", "n_detections", "max_frp", "mean_frp", "satellites", "possible_chain_merge"),
        analysis["picachos_diagnostics"]["nearest_spatial_clusters"],
    )
    _write_csv(
        output_dir / "picachos_temporal_top10.csv",
        ("event_id", "distance_m", "start_timestamp_utc", "end_timestamp_utc", "n_detections", "max_frp", "mean_frp", "satellites", "possible_chain_merge"),
        analysis["picachos_diagnostics"]["nearest_temporally_relevant_clusters"],
    )
    _write_csv(
        output_dir / "picachos_raw_firms_audit.csv",
        ("reference_id", "start_date", "end_date", "radius_m", "count", "closest"),
        (
            {
                "reference_id": audit["reference_id"],
                "start_date": audit["start_date"],
                "end_date": audit["end_date"],
                "radius_m": radius["radius_m"],
                "count": radius["count"],
                "closest": radius["closest"],
            }
            for audit in analysis["picachos_diagnostics"]["raw_firms_audit"]
            for radius in audit["radii"]
        ),
    )
    timeline_rows = []
    detection_rows = []
    for cluster in analysis["guacamaya_timeline"]["clusters"]:
        timeline_rows.append(
            {
                "order": cluster["order"],
                "event_id": cluster["event_id"],
                "cluster_start": cluster["cluster_start"],
                "cluster_end": cluster["cluster_end"],
                "intercluster_gap_hours": cluster["intercluster_gap_hours"],
                "n_detections": cluster["n_detections"],
                "max_frp": cluster["max_frp"],
                "mean_frp": cluster["mean_frp"],
                "satellites": cluster["satellites"],
                "day_count": cluster["day_count"],
                "night_count": cluster["night_count"],
                "possible_chain_merge": cluster["possible_chain_merge"],
            }
        )
        for detection in cluster["detections"]:
            detection_rows.append({"event_id": cluster["event_id"], **detection})
    _write_csv(
        output_dir / "guacamaya_timeline.csv",
        ("order", "event_id", "cluster_start", "cluster_end", "intercluster_gap_hours", "n_detections", "max_frp", "mean_frp", "satellites", "day_count", "night_count", "possible_chain_merge"),
        timeline_rows,
    )
    _write_csv(
        output_dir / "guacamaya_detections.csv",
        ("event_id", "detection_id", "timestamp_utc", "latitude", "longitude", "satellite", "frp", "daynight"),
        detection_rows,
    )
    _write_csv(
        output_dir / "guacamaya_distribution_ranks.csv",
        ("event_id", "cluster_order", "metric", "value", "official_percentile", "inclusive_rank", "cohort_count"),
        analysis["guacamaya_distribution_ranks"],
    )
    for name, function in _figure_functions().items():
        function(output_dir / name, render_analysis)

    files = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if path.name == "manifest.json" or not path.is_file():
            continue
        files.append({"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    manifest = {
        "analysis_version": ANALYSIS_VERSION,
        "configuration_id": CONFIGURATION_ID,
        "generated_from": "frozen local FirePA artifacts",
        "network_access": False,
        "earth_engine_queries_made": False,
        "files": files,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def verify_final_bundle(output_dir: Path) -> dict[str, Any]:
    """Verify the final ignored output bundle without rebuilding it."""

    output_dir = output_dir.resolve()
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return {"ok": False, "error": "manifest_missing"}
    manifest = _read_json(manifest_path)
    expected = {row["path"]: row for row in manifest.get("files", [])}
    mismatches = []
    for name, expected_row in expected.items():
        path = output_dir / name
        if not path.is_file():
            mismatches.append({"path": name, "reason": "missing"})
        else:
            digest = sha256_file(path)
            if digest != expected_row["sha256"]:
                mismatches.append({"path": name, "reason": "sha256", "actual": digest})
    expected_figures = [name for name in FIGURE_NAMES if name not in expected]
    return {
        "ok": not mismatches and not expected_figures,
        "manifest_file_count": len(expected),
        "figure_count": sum(name in expected for name in FIGURE_NAMES),
        "mismatches": mismatches,
        "missing_figures": expected_figures,
        "network_access": manifest.get("network_access"),
        "earth_engine_queries_made": manifest.get("earth_engine_queries_made"),
    }


__all__ = [
    "ANALYSIS_VERSION",
    "CONFIGURATION_ID",
    "DISTANCE_THRESHOLD_M",
    "EXPECTED_CLUSTER_COUNT",
    "FIGURE_NAMES",
    "FinalScientificReportError",
    "analyze_final_pilot",
    "sha256_file",
    "verify_final_bundle",
    "write_final_bundle",
]
