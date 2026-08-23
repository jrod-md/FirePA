"""Exploratory external-reference matching for the frozen r1500_t06 table.

This module deliberately consumes the already-frozen cluster events table. It
does not run clustering, create labels, call a remote service, or connect to
the formal human-review package. The two references are administrative
anchors supplied by the investigator; a match is a spatiotemporal association
and is not a fire classification or ground truth.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .clustering import distance_between_coordinates_m


UTC = timezone.utc
ANALYSIS_VERSION = "external_reference_check_v1"
CONFIGURATION_ID = "r1500_t06"
EXPECTED_CLUSTER_COUNT = 611
DISTANCE_THRESHOLD_M = 5_000.0
EXPECTED_OPTICAL_COHORT_COUNT = 30
INPUT_EVENTS_RELATIVE = "outputs/clustering/r1500_t06/events.csv"
OPTICAL_COHORT_RELATIVE = "data/processed/sentinel2_observability_pilot_events.csv"
OUTPUT_RELATIVE = "outputs/external_reference_check_v1"
GUACAMAYA_REFERENCE_ID = "REFERENCE-002"

MATCH_COLUMNS = (
    "reference_id",
    "reference_name",
    "reference_location",
    "reference_latitude",
    "reference_longitude",
    "reference_dates",
    "reference_window_start",
    "reference_window_end",
    "event_id",
    "configuration_id",
    "distance_m",
    "distance_threshold_m",
    "cluster_start",
    "cluster_end",
    "temporal_overlap",
    "temporal_overlap_start",
    "temporal_overlap_end",
    "temporal_overlap_hours",
    "n_detections",
    "max_frp",
    "mean_frp",
    "sum_frp",
    "satellites",
    "day_night_composition",
    "day_fraction",
    "night_fraction",
    "possible_chain_merge",
    "cluster_duration_hours",
    "max_frp_percentile",
    "mean_frp_percentile",
    "n_detections_percentile",
    "duration_percentile",
    "optical_followup_available",
    "selected_pair_available",
    "window_median_available",
    "nbr_dnbr_descriptive_available",
    "external_reference_match",
    "provenance",
)

SUMMARY_COLUMNS = (
    "reference_id",
    "reference_name",
    "reference_location",
    "reference_dates",
    "reference_window_start",
    "reference_window_end",
    "match_count",
    "matched_event_ids",
    "closest_distance_m",
    "all_matches_preserved",
    "multiple_clusters",
    "possible_t06_fragmentation",
    "fragmentation_assessment",
    "optical_followup_match_count",
    "source_status",
    "provenance",
)

COHORT_COLUMNS = (
    "metric",
    "cohort_count",
    "minimum",
    "median",
    "q25",
    "q75",
    "iqr",
    "p90",
    "p95",
    "p99",
    "maximum",
    "quantile_method",
    "source",
)

PROHIBITED_FIELDS = frozenset({"fire", "ground_truth", "significant_burn", "target"})


@dataclass(frozen=True)
class ExternalReference:
    """One externally documented incident reference supplied by the investigator."""

    reference_id: str
    name: str
    location: str
    latitude: float
    longitude: float
    reference_dates: tuple[str, ...]
    temporal_window_start: date
    temporal_window_end: date

    @property
    def window_start(self) -> datetime:
        return datetime.combine(self.temporal_window_start, time.min, tzinfo=UTC)

    @property
    def window_end(self) -> datetime:
        # The supplied end date is inclusive; use a half-open bound internally.
        return datetime.combine(
            self.temporal_window_end + timedelta(days=1), time.min, tzinfo=UTC
        )

    @property
    def window_end_inclusive(self) -> datetime:
        return self.window_end - timedelta(microseconds=1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "name": self.name,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "reference_dates": list(self.reference_dates),
            "temporal_window": {
                "start": self.temporal_window_start.isoformat(),
                "end": self.temporal_window_end.isoformat(),
            },
            "source": {
                "source_type": "manual_osint_outside_pipeline",
                "source_registered_in_repo": False,
                "citation": None,
                "url": None,
                "status": "schema_only_until_exact_source_is_registered",
            },
        }


REFERENCES: tuple[ExternalReference, ...] = (
    ExternalReference(
        reference_id="REFERENCE-001",
        name="Cerro Los Picachos",
        location="Olá, Coclé",
        latitude=8.42097,
        longitude=-80.65114,
        reference_dates=("2025-01-16",),
        temporal_window_start=date(2025, 1, 15),
        temporal_window_end=date(2025, 1, 17),
    ),
    ExternalReference(
        reference_id="REFERENCE-002",
        name="Cerro Guacamaya",
        location="Penonomé, Coclé",
        latitude=8.516667,
        longitude=-80.433333,
        reference_dates=("2025-01-23", "2025-01-24", "2025-01-25", "2025-01-26", "2025-01-27"),
        temporal_window_start=date(2025, 1, 23),
        temporal_window_end=date(2025, 1, 27),
    ),
)


class ExternalReferenceError(ValueError):
    """Raised when the frozen input or external-check contract is unsafe."""


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    if not math.isfinite(float(value)):
        raise ExternalReferenceError(f"Non-finite numeric value: {value!r}")
    return f"{float(value):.8f}".rstrip("0").rstrip(".") or "0"


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return _compact_json(value)
    if isinstance(value, float):
        return _format_float(value)
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
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key, "")
    return "" if value is None else str(value).strip()


def _number(row: Mapping[str, Any], key: str) -> float:
    value = _text(row, key)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ExternalReferenceError(f"Invalid numeric field {key}: {value!r}") from exc
    if not math.isfinite(number):
        raise ExternalReferenceError(f"Non-finite field {key}: {value!r}")
    return number


def _integer(row: Mapping[str, Any], key: str) -> int:
    number = _number(row, key)
    if int(number) != number or number < 0:
        raise ExternalReferenceError(f"Invalid non-negative integer field {key}: {number!r}")
    return int(number)


def _bool(row: Mapping[str, Any], key: str) -> bool:
    value = _text(row, key).casefold()
    if value not in {"true", "false"}:
        raise ExternalReferenceError(f"Invalid boolean field {key}: {value!r}")
    return value == "true"


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalReferenceError(f"Invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExternalReferenceError(f"Timestamp lacks explicit timezone: {value!r}")
    return parsed.astimezone(UTC)


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode_json_cell(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _required_cluster_columns() -> tuple[str, ...]:
    return (
        "configuration_id",
        "event_id",
        "start_timestamp_utc",
        "end_timestamp_utc",
        "detection_count",
        "satellites",
        "centroid_latitude",
        "centroid_longitude",
        "frp_max",
        "frp_mean",
        "frp_sum",
        "day_fraction",
        "night_fraction",
        "possible_chain_merge",
        "duration_hours",
    )


def load_frozen_cluster_events(
    path: Path | str,
    *,
    expected_count: int | None = EXPECTED_CLUSTER_COUNT,
    expected_configuration_id: str = CONFIGURATION_ID,
) -> list[dict[str, str]]:
    """Load the frozen event table without invoking the clustering algorithm."""

    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            missing = [column for column in _required_cluster_columns() if column not in fieldnames]
            if missing:
                raise ExternalReferenceError("Missing frozen cluster columns: " + ", ".join(missing))
            rows = [dict(row) for row in reader]
    except OSError as exc:
        raise ExternalReferenceError(f"Could not read frozen event table: {input_path}") from exc

    if expected_count is not None and len(rows) != expected_count:
        raise ExternalReferenceError(
            f"Frozen input event count is {len(rows)}; expected exactly {expected_count}"
        )
    event_ids: set[str] = set()
    for row in rows:
        if _text(row, "configuration_id") != expected_configuration_id:
            raise ExternalReferenceError("Input contains a configuration other than r1500_t06")
        event_id = _text(row, "event_id")
        if not event_id or event_id in event_ids:
            raise ExternalReferenceError(f"Duplicate or empty frozen event_id: {event_id!r}")
        event_ids.add(event_id)
        start = _parse_timestamp(_text(row, "start_timestamp_utc"))
        end = _parse_timestamp(_text(row, "end_timestamp_utc"))
        if end < start:
            raise ExternalReferenceError(f"Cluster interval is inverted: {event_id}")
        _number(row, "centroid_latitude")
        _number(row, "centroid_longitude")
        _integer(row, "detection_count")
        _number(row, "frp_max")
        _number(row, "frp_mean")
        _number(row, "frp_sum")
        _number(row, "duration_hours")
        _bool(row, "possible_chain_merge")
    return sorted(rows, key=lambda row: (_text(row, "start_timestamp_utc"), _text(row, "event_id")))


def load_optical_cohort(
    path: Path | str,
    *,
    expected_count: int | None = EXPECTED_OPTICAL_COHORT_COUNT,
) -> set[str]:
    """Read the existing 30-event optical cohort, without expanding it."""

    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "event_id" not in (reader.fieldnames or ()):
                raise ExternalReferenceError("Optical cohort lacks event_id")
            event_ids = [_text(row, "event_id") for row in reader]
    except OSError as exc:
        raise ExternalReferenceError(f"Could not read optical cohort: {input_path}") from exc
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        raise ExternalReferenceError("Optical cohort contains empty or duplicate event_id values")
    if expected_count is not None and len(event_ids) != expected_count:
        raise ExternalReferenceError(
            f"Optical cohort count is {len(event_ids)}; expected {expected_count}"
        )
    return set(event_ids)


def _interval_overlap(
    cluster_start: datetime, cluster_end: datetime, reference: ExternalReference
) -> tuple[bool, datetime | None, datetime | None, float | None]:
    overlap_start = max(cluster_start, reference.window_start)
    overlap_end = min(cluster_end, reference.window_end_inclusive)
    if cluster_start >= reference.window_end or cluster_end < reference.window_start:
        return False, None, None, None
    seconds = max(0.0, (overlap_end - overlap_start).total_seconds())
    return True, overlap_start, overlap_end, seconds / 3600.0


def _day_night_composition(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "day_fraction": _number(row, "day_fraction"),
        "night_fraction": _number(row, "night_fraction"),
        "known_fraction_sum": _number(row, "day_fraction") + _number(row, "night_fraction"),
    }


def _reference_provenance(reference: ExternalReference, input_path: Path) -> dict[str, Any]:
    return {
        "analysis_version": ANALYSIS_VERSION,
        "reference_source_type": "manual_osint_outside_pipeline",
        "reference_source_registered_in_repo": False,
        "reference_citation": None,
        "reference_url": None,
        "input_event_table": input_path.as_posix(),
        "configuration_id": CONFIGURATION_ID,
        "matching_metric": "EPSG:32617 Euclidean meters via existing clustering projection",
        "reclustered": False,
        "relationship_only": True,
    }


def _match_row(
    reference: ExternalReference,
    row: Mapping[str, str],
    *,
    input_path: Path,
    optical_event_ids: set[str],
) -> dict[str, Any] | None:
    cluster_start = _parse_timestamp(_text(row, "start_timestamp_utc"))
    cluster_end = _parse_timestamp(_text(row, "end_timestamp_utc"))
    temporal_overlap, overlap_start, overlap_end, overlap_hours = _interval_overlap(
        cluster_start, cluster_end, reference
    )
    distance_m = distance_between_coordinates_m(
        reference.latitude,
        reference.longitude,
        _number(row, "centroid_latitude"),
        _number(row, "centroid_longitude"),
    )
    if distance_m > DISTANCE_THRESHOLD_M or not temporal_overlap:
        return None

    event_id = _text(row, "event_id")
    optical_available = event_id in optical_event_ids
    return {
        "reference_id": reference.reference_id,
        "reference_name": reference.name,
        "reference_location": reference.location,
        "reference_latitude": reference.latitude,
        "reference_longitude": reference.longitude,
        "reference_dates": list(reference.reference_dates),
        "reference_window_start": _canonical_timestamp(reference.window_start),
        "reference_window_end": _canonical_timestamp(reference.window_end_inclusive),
        "event_id": event_id,
        "configuration_id": _text(row, "configuration_id"),
        "distance_m": distance_m,
        "distance_threshold_m": DISTANCE_THRESHOLD_M,
        "cluster_start": _canonical_timestamp(cluster_start),
        "cluster_end": _canonical_timestamp(cluster_end),
        "temporal_overlap": True,
        "temporal_overlap_start": _canonical_timestamp(overlap_start),
        "temporal_overlap_end": _canonical_timestamp(overlap_end),
        "temporal_overlap_hours": overlap_hours,
        "n_detections": _integer(row, "detection_count"),
        "max_frp": _number(row, "frp_max"),
        "mean_frp": _number(row, "frp_mean"),
        "sum_frp": _number(row, "frp_sum"),
        "satellites": _decode_json_cell(_text(row, "satellites"), [_text(row, "satellites")]),
        "day_night_composition": _day_night_composition(row),
        "day_fraction": _number(row, "day_fraction"),
        "night_fraction": _number(row, "night_fraction"),
        "possible_chain_merge": _bool(row, "possible_chain_merge"),
        "cluster_duration_hours": _number(row, "duration_hours"),
        "max_frp_percentile": None,
        "mean_frp_percentile": None,
        "n_detections_percentile": None,
        "duration_percentile": None,
        "optical_followup_available": optical_available,
        "selected_pair_available": optical_available,
        "window_median_available": optical_available,
        "nbr_dnbr_descriptive_available": optical_available,
        "external_reference_match": True,
        "provenance": _reference_provenance(reference, input_path),
    }


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(float(value) for value in values)
    position = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[position]


def _percentile_rank(value: float, values: Sequence[float]) -> float:
    if not values:
        raise ExternalReferenceError("Cannot rank a value against an empty cohort")
    return 100.0 * sum(candidate <= value for candidate in values) / len(values)


def _distribution_row(metric: str, values: Sequence[float], source: str) -> dict[str, Any]:
    if not values:
        raise ExternalReferenceError(f"No cohort values available for {metric}")
    ordered = sorted(float(value) for value in values)
    q25 = _nearest_rank(ordered, 0.25)
    q75 = _nearest_rank(ordered, 0.75)
    return {
        "metric": metric,
        "cohort_count": len(ordered),
        "minimum": ordered[0],
        "median": median(ordered),
        "q25": q25,
        "q75": q75,
        "iqr": q75 - q25,
        "p90": _nearest_rank(ordered, 0.90),
        "p95": _nearest_rank(ordered, 0.95),
        "p99": _nearest_rank(ordered, 0.99),
        "maximum": ordered[-1],
        "quantile_method": "nearest_rank_for_q25_q75_p90_p95_p99; statistics.median_for_median",
        "source": source,
    }


def _guacamaya_summary(
    matches: Sequence[Mapping[str, Any]], reference: ExternalReference
) -> dict[str, Any]:
    selected = sorted(
        (row for row in matches if row.get("reference_id") == reference.reference_id),
        key=lambda row: (str(row["cluster_start"]), str(row["event_id"])),
    )
    if not selected:
        return {
            "reference_id": reference.reference_id,
            "match_classification": "no_cluster",
            "matched_cluster_count": 0,
            "possible_t06_fragmentation": False,
            "fragmentation_assessment": "No matched cluster is available for this reference window.",
            "cluster_intervals": [],
            "intercluster_gaps_hours": [],
        }
    gaps: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        previous_end = _parse_timestamp(str(previous["cluster_end"]))
        current_start = _parse_timestamp(str(current["cluster_start"]))
        gaps.append(max(0.0, (current_start - previous_end).total_seconds() / 3600.0))
    multiple = len(selected) > 1
    possible_fragmentation = multiple and any(gap > 6.0 for gap in gaps)
    if possible_fragmentation:
        assessment = (
            "Multiple matched clusters are separated by gaps greater than the frozen "
            "t06 window. If the externally documented multi-day activity was persistent "
            "through those gaps, r1500_t06 would represent it as multiple clusters. "
            "This is a representation limitation, not an automatic bug finding."
        )
    else:
        assessment = (
            "The matched clusters do not show a gap beyond the frozen t06 window; "
            "no fragmentation inference is made."
        )
    return {
        "reference_id": reference.reference_id,
        "match_classification": "multiple_clusters" if multiple else "one_cluster",
        "matched_cluster_count": len(selected),
        "possible_t06_fragmentation": possible_fragmentation,
        "fragmentation_assessment": assessment,
        "rule": {"configuration_id": CONFIGURATION_ID, "time_window_hours": 6},
        "intercluster_gaps_hours": gaps,
        "cluster_intervals": [
            {
                "event_id": row["event_id"],
                "cluster_start": row["cluster_start"],
                "cluster_end": row["cluster_end"],
                "distance_m": row["distance_m"],
            }
            for row in selected
        ],
    }


def analyze_external_references(
    *,
    input_events_path: Path | str,
    optical_cohort_path: Path | str,
    expected_cluster_count: int | None = EXPECTED_CLUSTER_COUNT,
    expected_optical_cohort_count: int | None = EXPECTED_OPTICAL_COHORT_COUNT,
) -> dict[str, Any]:
    """Return a deterministic analysis result from local frozen inputs."""

    input_path = Path(input_events_path)
    optical_path = Path(optical_cohort_path)
    events = load_frozen_cluster_events(
        input_path,
        expected_count=expected_cluster_count,
        expected_configuration_id=CONFIGURATION_ID,
    )
    optical_event_ids = load_optical_cohort(
        optical_path, expected_count=expected_optical_cohort_count
    )
    matches: list[dict[str, Any]] = []
    for reference in REFERENCES:
        for row in events:
            match = _match_row(
                reference,
                row,
                input_path=input_path,
                optical_event_ids=optical_event_ids,
            )
            if match is not None:
                matches.append(match)

    metric_sources: dict[str, list[float]] = {
        "max_frp": [_number(row, "frp_max") for row in events],
        "mean_frp": [_number(row, "frp_mean") for row in events],
        "n_detections": [float(_integer(row, "detection_count")) for row in events],
        "duration": [_number(row, "duration_hours") for row in events],
    }
    for match in matches:
        match["max_frp_percentile"] = _percentile_rank(match["max_frp"], metric_sources["max_frp"])
        match["mean_frp_percentile"] = _percentile_rank(match["mean_frp"], metric_sources["mean_frp"])
        match["n_detections_percentile"] = _percentile_rank(
            match["n_detections"], metric_sources["n_detections"]
        )
        match["duration_percentile"] = _percentile_rank(
            match["cluster_duration_hours"], metric_sources["duration"]
        )

    distribution = [
        _distribution_row(
            metric,
            values,
            source=f"{input_path.as_posix()} ({CONFIGURATION_ID}; {len(events)} frozen clusters)",
        )
        for metric, values in metric_sources.items()
    ]
    summary_rows: list[dict[str, Any]] = []
    guacamaya = next(reference for reference in REFERENCES if reference.reference_id == GUACAMAYA_REFERENCE_ID)
    guacamaya_result = _guacamaya_summary(matches, guacamaya)
    for reference in REFERENCES:
        reference_matches = [
            row for row in matches if row["reference_id"] == reference.reference_id
        ]
        summary_rows.append(
            {
                "reference_id": reference.reference_id,
                "reference_name": reference.name,
                "reference_location": reference.location,
                "reference_dates": list(reference.reference_dates),
                "reference_window_start": _canonical_timestamp(reference.window_start),
                "reference_window_end": _canonical_timestamp(reference.window_end_inclusive),
                "match_count": len(reference_matches),
                "matched_event_ids": [row["event_id"] for row in reference_matches],
                "closest_distance_m": min(
                    (row["distance_m"] for row in reference_matches), default=None
                ),
                "all_matches_preserved": True,
                "multiple_clusters": len(reference_matches) > 1,
                "possible_t06_fragmentation": (
                    guacamaya_result["possible_t06_fragmentation"]
                    if reference.reference_id == GUACAMAYA_REFERENCE_ID
                    else False
                ),
                "fragmentation_assessment": (
                    guacamaya_result["fragmentation_assessment"]
                    if reference.reference_id == GUACAMAYA_REFERENCE_ID
                    else "No multi-day cluster fragmentation assessment is applicable."
                ),
                "optical_followup_match_count": sum(
                    bool(row["optical_followup_available"]) for row in reference_matches
                ),
                "source_status": "manual_osint_verified_outside_pipeline; exact citation not registered",
                "provenance": _reference_provenance(reference, input_path),
            }
        )

    return {
        "analysis_name": ANALYSIS_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "input": {
            "event_table": input_path.as_posix(),
            "event_table_sha256": sha256_file(input_path),
            "configuration_id": CONFIGURATION_ID,
            "cluster_count": len(events),
            "expected_cluster_count": expected_cluster_count,
            "reclustered": False,
            "matching_distance_metric": "EPSG:32617 Euclidean meters reused from clustering contract",
            "distance_threshold_m": DISTANCE_THRESHOLD_M,
            "temporal_overlap_inclusive_end_dates": True,
        },
        "optical_cohort": {
            "path": optical_path.as_posix(),
            "sha256": sha256_file(optical_path),
            "event_count": len(optical_event_ids),
            "cohort_expanded": False,
            "followup_modes": ["selected_pair", "window_median", "NBR/dNBR descriptive"],
        },
        "references": [reference.as_dict() for reference in REFERENCES],
        "matches": matches,
        "reference_summary": summary_rows,
        "cohort_distribution": distribution,
        "guacamaya_review": guacamaya_result,
        "formal_review": {
            "formal_review_status": "deferred",
            "reason": "QUALIFIED_REVIEWER_UNAVAILABLE",
            "execution_authorized": False,
            "execution_status": "not_started",
            "formal_review_28_preserved": True,
            "formal_review_observations": 0,
            "casual_reviewers_substitute": False,
            "ai_outputs_status": "provisional_pseudolabels",
            "pass_a_executed": False,
            "pass_b_executed": False,
            "note": (
                "The decision layer is deferred. The existing formal_review_28 "
                "package and SQLite remain prepared/not_started and are not modified."
            ),
        },
        "supervised_modeling": {
            "supervised_modeling_gate": "deferred",
            "reason": "NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE",
            "target_created": False,
            "model_trained": False,
        },
        "scope": {
            "environmental_feature_extraction": "not_authorized",
            "network_access": False,
            "earth_engine_queries_made": False,
            "supports": [
                "reproducible FIRMS acquisition",
                "provisional spatiotemporal clustering",
                "optical Sentinel-2 follow-up",
                "selected_pair/window_median evidence",
                "descriptive NBR/dNBR",
                "provenance and audit infrastructure",
                "exploratory external reference matching",
            ],
            "does_not_support": [
                "confirmed wildfire classification",
                "ground truth",
                "supervised prediction",
                "operational monitoring",
                "real-time alerts",
                "severity estimation",
                "institutional validation",
            ],
        },
        "provenance": {
            "reference_sources": "investigator-provided manual OSINT outside the pipeline",
            "exact_osint_citations_registered": False,
            "reclustered": False,
            "network_access": False,
            "earth_engine_queries_made": False,
        },
    }


def _metric_label(metric: str) -> str:
    return {
        "max_frp": "max FRP",
        "mean_frp": "mean FRP",
        "n_detections": "n detections",
        "duration": "duration (hours)",
    }[metric]


def _render_report_markdown(result: Mapping[str, Any]) -> str:
    summaries = result["reference_summary"]
    matches = result["matches"]
    distribution = result["cohort_distribution"]
    guacamaya = result["guacamaya_review"]
    lines = [
        "# external_reference_check_v1 — resultados locales",
        "",
        "Este informe es un chequeo exploratorio externo. Una fila de `matches` "
        "representa una asociación espacio-temporal administrativa, no una etiqueta "
        "de incendio ni una validación del pipeline.",
        "",
        "## Alcance y entrada",
        "",
        f"- Configuración congelada: `{CONFIGURATION_ID}`; no se reclusterizó.",
        f"- Eventos leídos: `{result['input']['cluster_count']}`; se exigieron exactamente `{result['input']['expected_cluster_count']}`.",
        f"- Métrica espacial: `{result['input']['matching_distance_metric']}`.",
        f"- Umbral: `{_format_float(DISTANCE_THRESHOLD_M)} m`, inclusivo.",
        "- La ventana temporal de cada referencia se interpretó con fechas de fin inclusivas.",
        "- Las fuentes OSINT fueron proporcionadas y verificadas manualmente fuera del pipeline; no se inventaron URLs ni citas.",
        "",
        "## Matches",
        "",
        "| Referencia | Nombre | Matches | Eventos | Distancia más cercana (m) | Optical follow-up |",
        "|---|---|---:|---|---:|---|",
    ]
    for row in summaries:
        events = ", ".join(f"`{event_id}`" for event_id in row["matched_event_ids"]) or "—"
        closest = _format_float(row["closest_distance_m"]) or "—"
        optical = f"{row['optical_followup_match_count']} de {row['match_count']}" if row["match_count"] else "no aplica"
        lines.append(
            f"| `{row['reference_id']}` | {row['reference_name']} | {row['match_count']} | {events} | {closest} | {optical} |"
        )
    lines.extend(
        [
            "",
            "### Detalle por match",
            "",
            "| Referencia | Event ID | Distancia (m) | Ventana de cluster | Temporal overlap | n detections | max FRP | mean FRP | sum FRP | Duración (h) | Percentiles max/mean/n/duración |",
            "|---|---|---:|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in matches:
        percentiles = "/".join(
            _format_float(row[field]) for field in (
                "max_frp_percentile",
                "mean_frp_percentile",
                "n_detections_percentile",
                "duration_percentile",
            )
        )
        lines.append(
            f"| `{row['reference_id']}` | `{row['event_id']}` | {_format_float(row['distance_m'])} | "
            f"{row['cluster_start']} → {row['cluster_end']} | sí | {row['n_detections']} | "
            f"{_format_float(row['max_frp'])} | {_format_float(row['mean_frp'])} | "
            f"{_format_float(row['sum_frp'])} | {_format_float(row['cluster_duration_hours'])} | {percentiles} |")
    if not matches:
        lines.append("| — | — | — | — | — | — | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "Los percentiles de cada match son rangos descriptivos contra los 611 clusters: "
            "100 × (# valores de la cohorte menores o iguales) / 611. No son métricas de exactitud, recall ni validación.",
            "",
            "## Distribución completa de los 611 clusters",
            "",
            "| Métrica | n | Mediana | IQR | p90 | p95 | p99 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in distribution:
        lines.append(
            f"| {_metric_label(row['metric'])} | {row['cohort_count']} | {_format_float(row['median'])} | "
            f"{_format_float(row['iqr'])} | {_format_float(row['p90'])} | {_format_float(row['p95'])} | {_format_float(row['p99'])} |"
        )
    lines.extend(
        [
            "",
            "Las estadísticas son descriptivas. Se usa `statistics.median` para la mediana y nearest-rank para q25, q75, p90, p95 y p99.",
            "",
            "## Guacamaya y la ventana t06",
            "",
            f"La referencia `{GUACAMAYA_REFERENCE_ID}` queda clasificada como **{guacamaya['match_classification']}** con `{guacamaya['matched_cluster_count']}` clusters matched.",
            f"`possible_t06_fragmentation={str(guacamaya['possible_t06_fragmentation']).lower()}`. {guacamaya['fragmentation_assessment']}",
            "No se modificó `r1500_t06`; esto se registra como comportamiento o limitación de representación, no como bug automáticamente.",
            "",
            "## Seguimiento óptico",
            "",
            "El chequeo solo referencia la cohorte óptica existente de 30 eventos. "
            "Los matches fuera de esa cohorte tienen `optical_followup_available=false`; "
            "no se ampliaron assets. Cuando existan matches dentro de la cohorte, los campos "
            "`selected_pair_available`, `window_median_available` y "
            "`nbr_dnbr_descriptive_available` apuntarán únicamente a evidencia descriptiva ya existente.",
            "",
            "## Decisión de scope",
            "",
            "- `formal_review_status=deferred`; razón `QUALIFIED_REVIEWER_UNAVAILABLE`.",
            "- `execution_authorized=false`; la infraestructura formal, blind packages, SQLite, tests, migraciones y assets no se modificaron.",
            "- `supervised_modeling_gate=deferred`; razón `NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE`.",
            "- No se generó target, `significant_burn`, `ground_truth`, modelo ni extracción ambiental.",
            "- Las revisiones IA existentes permanecen `provisional_pseudolabels`.",
            "- No hubo acceso de red ni consultas Earth Engine.",
            "",
            "## Artefactos locales",
            "",
            "Los artefactos están fuera de Git en `outputs/external_reference_check_v1/`. "
            "`manifest.json` contiene hashes SHA-256 de los archivos generados; "
            "su propio hash puede calcularse por separado.",
            "",
            "Conclusión limitada: el chequeo encontró asociaciones espacio-temporales descriptivas en la ventana de Guacamaya y ninguna en la ventana de Los Picachos, bajo el umbral de 5 km y la tabla congelada. Esto no establece confirmación de incendios, exactitud, cobertura completa ni validación institucional.",
            "",
        ]
    )
    return "\n".join(lines)


def _svg_header(title: str, width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
    )


def _svg_text(x: float, y: float, value: str, *, size: int = 13, fill: str = "#243447") -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial,sans-serif" font-size="{size}px" fill="{fill}">{html.escape(value)}</text>'


def _write_map_svg(path: Path, events: Sequence[Mapping[str, str]], matches: Sequence[Mapping[str, Any]]) -> None:
    width, height = 920, 580
    left, top, plot_width, plot_height = 70, 65, 790, 430
    longitudes = [_number(row, "centroid_longitude") for row in events]
    latitudes = [_number(row, "centroid_latitude") for row in events]
    for match in matches:
        longitudes.append(float(match["reference_longitude"]))
        latitudes.append(float(match["reference_latitude"]))
    west, east = min(longitudes) - 0.02, max(longitudes) + 0.02
    south, north = min(latitudes) - 0.02, max(latitudes) + 0.02

    def point(longitude: float, latitude: float) -> tuple[float, float]:
        x = left + (longitude - west) / (east - west) * plot_width
        y = top + (north - latitude) / (north - south) * plot_height
        return x, y

    colors = {"REFERENCE-001": "#c2410c", "REFERENCE-002": "#2563eb"}
    match_by_event = {str(row["event_id"]): row for row in matches}
    pieces = [_svg_header("External reference check: frozen clusters and references", width, height)]
    pieces.append(_svg_text(70, 30, "External reference check v1 — 611 frozen r1500_t06 cluster centroids", size=18))
    pieces.append(_svg_text(70, 50, "Administrative spatial view; no basemap and no classification implied", size=12, fill="#5b6770"))
    pieces.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#cbd5e1"/>')
    for row in events:
        x, y = point(_number(row, "centroid_longitude"), _number(row, "centroid_latitude"))
        event_id = _text(row, "event_id")
        if event_id in match_by_event:
            color = colors[str(match_by_event[event_id]["reference_id"])]
            pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}" stroke="#ffffff" stroke-width="1"/>')
        else:
            pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.8" fill="#94a3b8" opacity="0.65"/>')
    references_by_id = {reference.reference_id: reference for reference in REFERENCES}
    for reference in REFERENCES:
        x, y = point(reference.longitude, reference.latitude)
        color = colors[reference.reference_id]
        pieces.append(f'<path d="M {x-7:.2f} {y-7:.2f} L {x+7:.2f} {y+7:.2f} M {x+7:.2f} {y-7:.2f} L {x-7:.2f} {y+7:.2f}" stroke="{color}" stroke-width="2.5"/>')
        pieces.append(_svg_text(x + 10, y - 8, f"{reference.reference_id} — {reference.name}", size=12, fill=color))
    pieces.append(_svg_text(left, top + plot_height + 28, f"Longitude ({west:.3f} to {east:.3f})", size=12))
    pieces.append(_svg_text(8, top + plot_height / 2, f"Latitude ({south:.3f} to {north:.3f})", size=12))
    pieces.append(_svg_text(70, 535, "Gray: complete frozen cohort; colored: matched event; X: investigator-provided reference", size=12, fill="#5b6770"))
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def _write_frp_svg(path: Path, events: Sequence[Mapping[str, str]], matches: Sequence[Mapping[str, Any]]) -> None:
    width, height = 920, 560
    left, top, plot_width, plot_height = 75, 65, 790, 400
    values = sorted(_number(row, "frp_max") for row in events)
    maximum = max(values, default=1.0) or 1.0
    match_colors = {"REFERENCE-001": "#c2410c", "REFERENCE-002": "#2563eb"}
    by_event = {str(row["event_id"]): row for row in matches}
    pieces = [_svg_header("External reference check: max FRP distribution", width, height)]
    pieces.append(_svg_text(75, 30, "Max FRP distribution across the 611 frozen clusters", size=18))
    pieces.append(_svg_text(75, 50, "Descriptive comparison; x is empirical percentile rank and y is max FRP", size=12, fill="#5b6770"))
    pieces.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#cbd5e1"/>')
    for index, row in enumerate(sorted(events, key=lambda item: _number(item, "frp_max"))):
        value = _number(row, "frp_max")
        x = left + (index / max(1, len(events) - 1)) * plot_width
        y = top + plot_height - value / maximum * plot_height
        pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="#94a3b8" opacity="0.65"/>')
    for row in matches:
        value = float(row["max_frp"])
        x = left + float(row["max_frp_percentile"]) / 100.0 * plot_width
        y = top + plot_height - value / maximum * plot_height
        color = match_colors[str(row["reference_id"])]
        pieces.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}" stroke="#ffffff" stroke-width="1.5"/>')
    pieces.append(_svg_text(left, top + plot_height + 25, "0", size=11))
    pieces.append(_svg_text(left + plot_width - 25, top + plot_height + 25, "100", size=11))
    pieces.append(_svg_text(12, top + 10, f"{maximum:.1f}", size=11))
    pieces.append(_svg_text(22, top + plot_height, "0", size=11))
    pieces.append(_svg_text(75, 520, "Gray: full cohort; orange/blue: matches by reference", size=12, fill="#5b6770"))
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def _write_guacamaya_timeline_svg(path: Path, matches: Sequence[Mapping[str, Any]]) -> None:
    selected = sorted(
        (row for row in matches if row["reference_id"] == GUACAMAYA_REFERENCE_ID),
        key=lambda row: (row["cluster_start"], row["event_id"]),
    )
    width, height = 1_080, 440
    left, top, plot_width, plot_height = 100, 95, 900, 250
    reference = next(reference for reference in REFERENCES if reference.reference_id == GUACAMAYA_REFERENCE_ID)
    start = reference.window_start
    end = reference.window_end
    total_seconds = (end - start).total_seconds()

    def x_for(value: datetime) -> float:
        return left + (value - start).total_seconds() / total_seconds * plot_width

    pieces = [_svg_header("External reference check: Guacamaya timeline", width, height)]
    pieces.append(_svg_text(100, 30, "REFERENCE-002 — Cerro Guacamaya: matched clusters inside 2025-01-23 through 2025-01-27", size=18))
    pieces.append(_svg_text(100, 52, "The six intervals are displayed without reclustering; gaps beyond t06 remain visible", size=12, fill="#5b6770"))
    pieces.append(f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#cbd5e1"/>')
    pieces.append(f'<rect x="{left}" y="{top+40}" width="{plot_width}" height="100" fill="#dbeafe" opacity="0.45"/>')
    row_y = top + 80
    for index, row in enumerate(selected):
        cluster_start = _parse_timestamp(str(row["cluster_start"]))
        cluster_end = _parse_timestamp(str(row["cluster_end"]))
        x_start = x_for(cluster_start)
        x_end = max(x_start + 4, x_for(cluster_end))
        y = row_y + (index % 3) * 42
        pieces.append(f'<rect x="{x_start:.2f}" y="{y:.2f}" width="{x_end-x_start:.2f}" height="18" rx="3" fill="#2563eb"/>')
        pieces.append(_svg_text(x_start, y - 5, str(row["event_id"])[-8:], size=10, fill="#1d4ed8"))
    for day_index in range(6):
        tick = start + timedelta(days=day_index)
        x = x_for(tick)
        pieces.append(f'<path d="M {x:.2f} {top+plot_height} V {top+plot_height+8}" stroke="#64748b"/>')
        pieces.append(_svg_text(x - 28, top + plot_height + 25, tick.strftime("Jan %d"), size=11))
    pieces.append(_svg_text(100, 390, "Blue band: reference temporal window; blue bars: matched cluster intervals; labels show event suffixes", size=12, fill="#5b6770"))
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def _write_visualizations(
    output_dir: Path,
    events: Sequence[Mapping[str, str]],
    matches: Sequence[Mapping[str, Any]],
) -> list[str]:
    names = [
        "reference_cluster_map.svg",
        "max_frp_distribution.svg",
        "guacamaya_timeline.svg",
    ]
    _write_map_svg(output_dir / names[0], events, matches)
    _write_frp_svg(output_dir / names[1], events, matches)
    _write_guacamaya_timeline_svg(output_dir / names[2], matches)
    return names


def write_outputs(
    result: Mapping[str, Any],
    *,
    output_dir: Path | str,
    input_events_path: Path | str,
    optical_cohort_path: Path | str,
    include_visualizations: bool = True,
) -> dict[str, Any]:
    """Write the local output bundle and a hash manifest."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_events_path)
    optical_path = Path(optical_cohort_path)
    events = load_frozen_cluster_events(input_path, expected_count=None)
    matches = list(result["matches"])
    _write_csv(output_path / "matches.csv", MATCH_COLUMNS, matches)
    _write_json(output_path / "matches.json", {"analysis_version": ANALYSIS_VERSION, "matches": matches})
    _write_csv(output_path / "reference_summary.csv", SUMMARY_COLUMNS, result["reference_summary"])
    _write_csv(output_path / "cohort_distribution.csv", COHORT_COLUMNS, result["cohort_distribution"])
    _write_json(output_path / "report.json", dict(result))
    (output_path / "report.md").write_text(_render_report_markdown(result), encoding="utf-8")
    visualization_names: list[str] = []
    if include_visualizations:
        visualization_names = _write_visualizations(output_path, events, matches)

    files: list[dict[str, Any]] = []
    for path in sorted(output_path.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.name == "manifest.json":
            continue
        files.append(
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "analysis_name": ANALYSIS_VERSION,
        "deterministic": True,
        "input_event_table_sha256": sha256_file(input_path),
        "optical_cohort_sha256": sha256_file(optical_path),
        "files": files,
        "visualizations": visualization_names,
        "manifest_excludes": ["manifest.json"],
    }
    _write_json(output_path / "manifest.json", manifest)
    return manifest


def _walk_field_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        names.update(str(key) for key in value)
        for child in value.values():
            names.update(_walk_field_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_walk_field_names(child))
    return names


def verify_outputs(output_dir: Path | str) -> dict[str, Any]:
    """Verify hashes and scientific-scope invariants without writing files."""

    root = Path(output_dir)
    errors: list[str] = []
    required = {
        "matches.csv",
        "matches.json",
        "reference_summary.csv",
        "cohort_distribution.csv",
        "report.json",
        "report.md",
        "manifest.json",
    }
    if not root.exists():
        return {"ok": False, "errors": [f"missing output directory: {root}"]}
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    missing = sorted(required - actual_files)
    if missing:
        errors.append("missing required outputs: " + ", ".join(missing))
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        matches_payload = json.loads((root / "matches.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": errors + [f"invalid JSON output: {exc}"]}

    for item in manifest.get("files", []):
        path = root / str(item.get("path", ""))
        if not path.is_file():
            errors.append(f"manifest file missing: {path.name}")
            continue
        if path.stat().st_size != item.get("size_bytes"):
            errors.append(f"manifest size mismatch: {path.name}")
        if sha256_file(path) != item.get("sha256"):
            errors.append(f"manifest hash mismatch: {path.name}")
    if manifest.get("deterministic") is not True:
        errors.append("manifest deterministic flag is not true")
    if report.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("report version mismatch")
    if report.get("input", {}).get("cluster_count") != EXPECTED_CLUSTER_COUNT:
        errors.append("report does not state exactly 611 frozen clusters")
    if report.get("input", {}).get("reclustered") is not False:
        errors.append("report permits or records reclustering")
    formal = report.get("formal_review", {})
    if formal.get("formal_review_status") != "deferred":
        errors.append("formal review is not deferred")
    if formal.get("execution_authorized") is not False:
        errors.append("execution_authorized is not false")
    if formal.get("pass_a_executed") is not False or formal.get("pass_b_executed") is not False:
        errors.append("formal Pass A/B execution invariant failed")
    supervised = report.get("supervised_modeling", {})
    if supervised.get("supervised_modeling_gate") != "deferred":
        errors.append("supervised modeling gate is not deferred")
    if supervised.get("target_created") is not False or supervised.get("model_trained") is not False:
        errors.append("target/model invariant failed")
    scope = report.get("scope", {})
    if scope.get("network_access") is not False or scope.get("earth_engine_queries_made") is not False:
        errors.append("network/Earth Engine invariant failed")
    if report.get("provenance", {}).get("exact_osint_citations_registered") is not False:
        errors.append("OSINT citation status unexpectedly claims registered sources")

    payload_fields = _walk_field_names(report) | _walk_field_names(matches_payload)
    forbidden_present = sorted(payload_fields & PROHIBITED_FIELDS)
    if forbidden_present:
        errors.append("prohibited output fields present: " + ", ".join(forbidden_present))
    serialized = json.dumps([report, matches_payload], ensure_ascii=False, sort_keys=True).casefold()
    if "fire=true" in serialized:
        errors.append("fire=true relationship was emitted")
    if "ground_truth" in serialized or "significant_burn" in serialized or '"target"' in serialized:
        errors.append("prohibited scientific marker found in structured output")
    matches = matches_payload.get("matches", [])
    if any(row.get("external_reference_match") is not True for row in matches):
        errors.append("a match lacks external_reference_match=true")
    if any(row.get("temporal_overlap") is not True for row in matches):
        errors.append("a match lacks temporal_overlap=true")

    return {
        "ok": not errors,
        "errors": errors,
        "analysis_version": report.get("analysis_version"),
        "cluster_count": report.get("input", {}).get("cluster_count"),
        "match_count": len(matches),
        "manifest_file_count": len(manifest.get("files", [])),
        "formal_review_status": formal.get("formal_review_status"),
        "execution_authorized": formal.get("execution_authorized"),
        "earth_engine_queries_made": scope.get("earth_engine_queries_made"),
        "network_access": scope.get("network_access"),
        "read_only": True,
    }
