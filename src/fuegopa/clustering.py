"""Deterministic spatiotemporal sensitivity analysis for FIRMS detections.

This module deliberately implements only the event-proposal experiment.  It
does not decide which group is a confirmed fire, does not use environmental
variables, and does not create labels for Sentinel-2 or dNBR.

The graph has one node per FIRMS detection.  Two nodes are connected when
their projected distance is within the configured radius *and* their UTC time
difference is within the configured window.  Connected components are kept,
including singletons, so the result is an auditable proposal of provisional
algorithmic events rather than a claim about independent fires.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
PERIOD_START = date(2025, 1, 1)
PERIOD_END = date(2025, 4, 30)
PROJECTION = "EPSG:32617"
PROJECTION_DESCRIPTION = "WGS84 / UTM zone 17N; stdlib forward projection; Euclidean meters"

REQUIRED_COLUMNS = ("detection_id", "latitude", "longitude", "acq_datetime_utc")

MEMBERSHIP_COLUMNS = (
    "configuration_id",
    "event_id",
    "detection_id",
    "timestamp_utc",
    "latitude",
    "longitude",
    "firms_source",
    "satellite",
    "instrument",
    "frp",
    "confidence_raw",
    "daynight",
    "raw_file",
    "raw_sha256",
)

EVENT_COLUMNS = (
    "configuration_id",
    "event_id",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "duration_hours",
    "detection_count",
    "source_count",
    "firms_sources",
    "satellite_count",
    "satellites",
    "centroid_latitude",
    "centroid_longitude",
    "bbox_west",
    "bbox_south",
    "bbox_east",
    "bbox_north",
    "max_pairwise_distance_m",
    "max_distance_to_centroid_m",
    "max_consecutive_gap_hours",
    "calendar_days_covered",
    "frp_min",
    "frp_max",
    "frp_mean",
    "frp_median",
    "frp_sum",
    "confidence_counts",
    "day_fraction",
    "night_fraction",
    "daynight_known_count",
    "possible_chain_merge",
    "chain_merge_reasons",
    "multi_source",
    "multi_sensor",
    "both_sensors",
    "crosses_midnight",
    "multi_day",
)

SUMMARY_COLUMNS = (
    "configuration_id",
    "radius_m",
    "time_window_hours",
    "event_count",
    "singleton_count",
    "singleton_rate_pct",
    "min_detection_count",
    "median_detection_count",
    "mean_detection_count",
    "p95_detection_count",
    "max_detection_count",
    "median_duration_hours",
    "p95_duration_hours",
    "max_duration_hours",
    "median_spatial_extent_m",
    "p95_spatial_extent_m",
    "max_spatial_extent_m",
    "events_multiple_sources",
    "events_both_sensors",
    "events_cross_midnight",
    "events_multi_day",
    "events_possible_chain_merge",
    "largest_event_detection_share_pct",
    "largest_event_detection_count",
    "all_detections_preserved",
    "detection_count_total",
    "mega_cluster_detected",
)


class ClusteringValidationError(ValueError):
    """Raised when the clustering input is not safe to interpret."""


@dataclass(frozen=True)
class ClusteringConfig:
    """One point in the prespecified radius/time-window sensitivity grid."""

    radius_m: int
    time_window_hours: int

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if self.time_window_hours <= 0:
            raise ValueError("time_window_hours must be positive")

    @property
    def configuration_id(self) -> str:
        return f"r{self.radius_m:04d}_t{self.time_window_hours:02d}"


RADIUS_GRID = (375, 750, 1500, 3000)
TIME_WINDOW_GRID = (6, 12, 24, 48)
DEFAULT_CONFIGURATIONS = tuple(
    ClusteringConfig(radius_m=radius, time_window_hours=hours)
    for radius in RADIUS_GRID
    for hours in TIME_WINDOW_GRID
)


@dataclass(frozen=True)
class Detection:
    """Validated detection plus the original row for descriptive fields."""

    detection_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    timestamp_utc: str
    x_m: float
    y_m: float
    row: Mapping[str, Any]


@dataclass(frozen=True)
class ClusterResult:
    """One deterministic connected-components result."""

    configuration: ClusteringConfig
    events: tuple[dict[str, Any], ...]
    membership: tuple[dict[str, Any], ...]
    detection_count: int
    mega_cluster_detected: bool


def _raw_value(row: Mapping[str, Any], column: str) -> str:
    value = row.get(column, "")
    return "" if value is None else str(value).strip()


def validate_required_columns(columns: Iterable[str]) -> None:
    """Reject an input whose mandatory graph fields are absent."""

    available = {str(column).strip() for column in columns if column is not None}
    missing = [column for column in REQUIRED_COLUMNS if column not in available]
    if missing:
        raise ClusteringValidationError(
            "Faltan columnas obligatorias para clustering: " + ", ".join(missing)
        )


def validate_coordinate(value: Any, axis: str = "latitude") -> float:
    """Parse and validate one WGS84 coordinate in degrees."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ClusteringValidationError(f"Coordenada {axis} no numérica: {value!r}") from exc
    if not math.isfinite(number):
        raise ClusteringValidationError(f"Coordenada {axis} no finita: {value!r}")
    if axis == "latitude" and not -90.0 <= number <= 90.0:
        raise ClusteringValidationError(f"Latitud fuera de rango: {number}")
    if axis == "longitude" and not -180.0 <= number <= 180.0:
        raise ClusteringValidationError(f"Longitud fuera de rango: {number}")
    return number


def parse_timestamp_utc(value: Any) -> tuple[datetime, str]:
    """Parse an ISO timestamp and normalize it to a canonical UTC string."""

    text = "" if value is None else str(value).strip()
    if not text:
        raise ClusteringValidationError("Timestamp UTC vacío")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClusteringValidationError(f"Timestamp ISO inválido: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClusteringValidationError(
            f"Timestamp sin zona horaria explícita; se requiere UTC: {value!r}"
        )
    normalized = parsed.astimezone(UTC)
    canonical = normalized.strftime("%Y-%m-%dT%H:%M:%SZ")
    return normalized, canonical


def _project_wgs84_to_utm17(latitude: float, longitude: float) -> tuple[float, float]:
    """Project WGS84 degrees to EPSG:32617 using the standard UTM series."""

    semi_major = 6378137.0
    eccentricity_squared = 0.0066943799901413165
    eccentricity_prime_squared = eccentricity_squared / (1.0 - eccentricity_squared)
    scale = 0.9996
    central_meridian = math.radians(-81.0)

    latitude_radians = math.radians(latitude)
    longitude_radians = math.radians(longitude)
    sine = math.sin(latitude_radians)
    cosine = math.cos(latitude_radians)
    tangent_squared = math.tan(latitude_radians) ** 2
    radius_normal = semi_major / math.sqrt(1.0 - eccentricity_squared * sine**2)
    c_term = eccentricity_prime_squared * cosine**2
    a_term = cosine * (longitude_radians - central_meridian)
    meridional_arc = semi_major * (
        (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256)
        * latitude_radians
        - (3 * eccentricity_squared / 8 + 3 * eccentricity_squared**2 / 32 + 45 * eccentricity_squared**3 / 1024)
        * math.sin(2 * latitude_radians)
        + (15 * eccentricity_squared**2 / 256 + 45 * eccentricity_squared**3 / 1024)
        * math.sin(4 * latitude_radians)
        - (35 * eccentricity_squared**3 / 3072) * math.sin(6 * latitude_radians)
    )

    x = scale * radius_normal * (
        a_term
        + (1 - tangent_squared + c_term) * a_term**3 / 6
        + (5 - 18 * tangent_squared + tangent_squared**2 + 72 * c_term - 58 * eccentricity_prime_squared)
        * a_term**5
        / 120
    ) + 500000.0
    y = scale * (
        meridional_arc
        + radius_normal
        * math.tan(latitude_radians)
        * (
            a_term**2 / 2
            + (5 - tangent_squared + 9 * c_term + 4 * c_term**2) * a_term**4 / 24
            + (61 - 58 * tangent_squared + tangent_squared**2 + 600 * c_term - 330 * eccentricity_prime_squared)
            * a_term**6
            / 720
        )
    )
    return x, y


def projected_distance_m(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    """Return Euclidean distance between two EPSG:32617 coordinates."""

    return math.hypot(first[0] - second[0], first[1] - second[1])


def distance_between_coordinates_m(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """Project two WGS84 points and return their distance in meters."""

    first = _project_wgs84_to_utm17(first_latitude, first_longitude)
    second = _project_wgs84_to_utm17(second_latitude, second_longitude)
    return projected_distance_m(first, second)


def validate_detection_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Detection, ...]:
    """Validate mandatory fields and return stable, parsed detection objects."""

    if not rows:
        raise ClusteringValidationError("El CSV de clustering no contiene filas de datos")
    first = rows[0]
    if not isinstance(first, Mapping):
        raise ClusteringValidationError("Cada fila debe ser un mapping de columnas")
    validate_required_columns(first.keys())

    parsed: list[Detection] = []
    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        if not isinstance(row, Mapping):
            raise ClusteringValidationError(f"Fila {row_number} no es un mapping")
        detection_id = _raw_value(row, "detection_id")
        if not detection_id:
            raise ClusteringValidationError(f"Fila {row_number} tiene detection_id vacío")
        if detection_id in seen_ids:
            raise ClusteringValidationError(f"detection_id duplicado: {detection_id}")
        seen_ids.add(detection_id)
        latitude = validate_coordinate(_raw_value(row, "latitude"), "latitude")
        longitude = validate_coordinate(_raw_value(row, "longitude"), "longitude")
        timestamp, timestamp_utc = parse_timestamp_utc(_raw_value(row, "acq_datetime_utc"))
        x_m, y_m = _project_wgs84_to_utm17(latitude, longitude)
        parsed.append(
            Detection(
                detection_id=detection_id,
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
                timestamp_utc=timestamp_utc,
                x_m=x_m,
                y_m=y_m,
                row=dict(row),
            )
        )
    return tuple(parsed)


def load_detections_csv(path: Path | str) -> tuple[Detection, ...]:
    """Read, validate, and parse a local processed FIRMS CSV."""

    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            validate_required_columns(reader.fieldnames or ())
            rows = list(reader)
    except OSError as exc:
        raise ClusteringValidationError(f"No se pudo leer el CSV: {input_path}") from exc
    return validate_detection_rows(rows)


def _as_detections(rows: Sequence[Detection | Mapping[str, Any]]) -> tuple[Detection, ...]:
    if all(isinstance(row, Detection) for row in rows):
        return tuple(row for row in rows if isinstance(row, Detection))
    if any(isinstance(row, Detection) for row in rows):
        raise ClusteringValidationError("No se pueden mezclar Detection y mappings")
    return validate_detection_rows(rows)  # type: ignore[arg-type]


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        if self.rank[first_root] < self.rank[second_root]:
            first_root, second_root = second_root, first_root
        self.parent[second_root] = first_root
        if self.rank[first_root] == self.rank[second_root]:
            self.rank[first_root] += 1


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    if not math.isfinite(value):
        return ""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _optional_float(row: Mapping[str, Any], column: str) -> float | None:
    raw = _raw_value(row, column)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _daynight_value(row: Mapping[str, Any]) -> str:
    value = _raw_value(row, "daynight").upper()
    if value in {"D", "DAY"}:
        return "D"
    if value in {"N", "NIGHT"}:
        return "N"
    return ""


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _event_id(configuration: ClusteringConfig, detections: Sequence[Detection]) -> str:
    detection_ids = "\0".join(sorted(detection.detection_id for detection in detections))
    payload = f"{configuration.configuration_id}\0{detection_ids}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"event-{configuration.configuration_id}-{digest[:16]}"


def _event_membership(
    configuration: ClusteringConfig,
    event_id: str,
    detections: Sequence[Detection],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for detection in sorted(detections, key=lambda item: item.detection_id):
        result.append(
            {
                "configuration_id": configuration.configuration_id,
                "event_id": event_id,
                "detection_id": detection.detection_id,
                "timestamp_utc": detection.timestamp_utc,
                "latitude": _format_float(detection.latitude),
                "longitude": _format_float(detection.longitude),
                "firms_source": _raw_value(detection.row, "firms_source"),
                "satellite": _raw_value(detection.row, "satellite"),
                "instrument": _raw_value(detection.row, "instrument"),
                "frp": _raw_value(detection.row, "frp"),
                "confidence_raw": _raw_value(detection.row, "confidence_raw"),
                "daynight": _raw_value(detection.row, "daynight"),
                "raw_file": _raw_value(detection.row, "raw_file"),
                "raw_sha256": _raw_value(detection.row, "raw_sha256"),
            }
        )
    return result


def _event_record(
    configuration: ClusteringConfig,
    event_id: str,
    detections: Sequence[Detection],
) -> dict[str, Any]:
    ordered = sorted(detections, key=lambda item: (item.timestamp, item.detection_id))
    timestamps = [item.timestamp for item in ordered]
    latitudes = [item.latitude for item in ordered]
    longitudes = [item.longitude for item in ordered]
    projected = [(item.x_m, item.y_m) for item in ordered]
    centroid_x = mean(point[0] for point in projected)
    centroid_y = mean(point[1] for point in projected)
    pairwise_distances = [
        projected_distance_m(projected[first], projected[second])
        for first in range(len(projected))
        for second in range(first + 1, len(projected))
    ]
    consecutive_gaps = [
        (timestamps[index] - timestamps[index - 1]).total_seconds() / 3600.0
        for index in range(1, len(timestamps))
    ]
    frp_values = [
        value
        for detection in ordered
        if (value := _optional_float(detection.row, "frp")) is not None
    ]
    confidence_values = [
        value
        for detection in ordered
        if (value := (_raw_value(detection.row, "confidence_normalized") or _raw_value(detection.row, "confidence_raw")))
    ]
    confidence_counts = dict(sorted(Counter(confidence_values).items()))
    daynight_values = [_daynight_value(detection.row) for detection in ordered]
    known_daynight = [value for value in daynight_values if value in {"D", "N"}]
    source_values = sorted(
        {
            _raw_value(detection.row, "firms_source")
            for detection in ordered
            if _raw_value(detection.row, "firms_source")
        }
    )
    satellite_values = sorted(
        {
            _raw_value(detection.row, "satellite")
            for detection in ordered
            if _raw_value(detection.row, "satellite")
        }
    )
    start, end = timestamps[0], timestamps[-1]
    calendar_days = (end.date() - start.date()).days + 1
    return {
        "configuration_id": configuration.configuration_id,
        "event_id": event_id,
        "start_timestamp_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_timestamp_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_hours": (end - start).total_seconds() / 3600.0,
        "detection_count": len(ordered),
        "source_count": len(source_values),
        "firms_sources": source_values,
        "satellite_count": len(satellite_values),
        "satellites": satellite_values,
        "centroid_latitude": mean(latitudes),
        "centroid_longitude": mean(longitudes),
        "bbox_west": min(longitudes),
        "bbox_south": min(latitudes),
        "bbox_east": max(longitudes),
        "bbox_north": max(latitudes),
        "max_pairwise_distance_m": max(pairwise_distances, default=0.0),
        "max_distance_to_centroid_m": max(
            (math.hypot(x - centroid_x, y - centroid_y) for x, y in projected),
            default=0.0,
        ),
        "max_consecutive_gap_hours": max(consecutive_gaps, default=0.0),
        "calendar_days_covered": calendar_days,
        "frp_min": min(frp_values) if frp_values else None,
        "frp_max": max(frp_values) if frp_values else None,
        "frp_mean": mean(frp_values) if frp_values else None,
        "frp_median": median(frp_values) if frp_values else None,
        "frp_sum": sum(frp_values) if frp_values else None,
        "confidence_counts": confidence_counts,
        "day_fraction": (
            known_daynight.count("D") / len(known_daynight) if known_daynight else None
        ),
        "night_fraction": (
            known_daynight.count("N") / len(known_daynight) if known_daynight else None
        ),
        "daynight_known_count": len(known_daynight),
        "possible_chain_merge": False,
        "chain_merge_reasons": [],
        "multi_source": len(source_values) > 1,
        "multi_sensor": len(satellite_values) > 1,
        "both_sensors": {"VIIRS_NOAA20_SP", "VIIRS_SNPP_SP"}.issubset(source_values),
        "crosses_midnight": start.date() != end.date(),
        "multi_day": calendar_days > 1,
    }


def _apply_chain_diagnostics(
    events: list[dict[str, Any]],
    configuration: ClusteringConfig,
    total_detections: int,
) -> bool:
    nonzero_extents = [
        float(event["max_pairwise_distance_m"])
        for event in events
        if float(event["max_pairwise_distance_m"]) > 0
    ]
    median_extent = median(nonzero_extents) if nonzero_extents else None
    mega_cluster = False
    for event in events:
        reasons: list[str] = []
        duration = float(event["duration_hours"])
        extent = float(event["max_pairwise_distance_m"])
        max_gap = float(event["max_consecutive_gap_hours"])
        share = event["detection_count"] / total_detections if total_detections else 0.0
        if duration > 72:
            reasons.append("duration_over_72h")
        if duration > 168:
            reasons.append("duration_over_168h")
        if extent > 3 * configuration.radius_m:
            reasons.append("spatial_extent_over_3x_radius")
        if max_gap >= 0.8 * configuration.time_window_hours:
            reasons.append("near_temporal_gap_limit")
        if share >= 0.25:
            reasons.append("large_cohort_share")
        if event["multi_day"]:
            reasons.append("multi_day_event")
        if median_extent is not None and extent > 3 * median_extent:
            reasons.append("exceptional_extent_vs_configuration_median")
        event["chain_merge_reasons"] = reasons
        event["possible_chain_merge"] = bool(reasons)
        if share >= 0.50 or duration > 168 or extent > 10 * configuration.radius_m:
            mega_cluster = True
    return mega_cluster


def cluster_detections(
    rows: Sequence[Detection | Mapping[str, Any]], configuration: ClusteringConfig
) -> ClusterResult:
    """Cluster rows using inclusive spatial and temporal graph thresholds."""

    detections = tuple(sorted(_as_detections(rows), key=lambda item: item.detection_id))
    if not detections:
        raise ClusteringValidationError("No hay detecciones válidas para clustering")
    union_find = _UnionFind(len(detections))
    time_order = sorted(range(len(detections)), key=lambda index: (detections[index].timestamp, detections[index].detection_id))
    max_delta = timedelta(hours=configuration.time_window_hours)
    radius_with_tolerance = configuration.radius_m * (1.0 + 1e-12)
    for left_position, left_index in enumerate(time_order):
        left = detections[left_index]
        for right_index in time_order[left_position + 1 :]:
            right = detections[right_index]
            delta = right.timestamp - left.timestamp
            if delta > max_delta:
                break
            if projected_distance_m((left.x_m, left.y_m), (right.x_m, right.y_m)) <= radius_with_tolerance:
                union_find.union(left_index, right_index)

    groups: dict[int, list[Detection]] = {}
    for index, detection in enumerate(detections):
        groups.setdefault(union_find.find(index), []).append(detection)
    events: list[dict[str, Any]] = []
    membership: list[dict[str, Any]] = []
    for group in groups.values():
        event_id = _event_id(configuration, group)
        events.append(_event_record(configuration, event_id, group))
        membership.extend(_event_membership(configuration, event_id, group))
    events.sort(key=lambda event: (event["start_timestamp_utc"], event["event_id"]))
    membership.sort(key=lambda row: (row["event_id"], row["detection_id"]))
    mega_cluster_detected = _apply_chain_diagnostics(events, configuration, len(detections))
    return ClusterResult(
        configuration=configuration,
        events=tuple(events),
        membership=tuple(membership),
        detection_count=len(detections),
        mega_cluster_detected=mega_cluster_detected,
    )


def _nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[position]


def summary_metrics(result: ClusterResult) -> dict[str, Any]:
    """Build the stable summary row for one configuration."""

    events = list(result.events)
    detection_counts = [int(event["detection_count"]) for event in events]
    durations = [float(event["duration_hours"]) for event in events]
    extents = [float(event["max_pairwise_distance_m"]) for event in events]
    largest_count = max(detection_counts, default=0)
    event_count = len(events)
    total = result.detection_count
    return {
        "configuration_id": result.configuration.configuration_id,
        "radius_m": result.configuration.radius_m,
        "time_window_hours": result.configuration.time_window_hours,
        "event_count": event_count,
        "singleton_count": sum(count == 1 for count in detection_counts),
        "singleton_rate_pct": (100.0 * sum(count == 1 for count in detection_counts) / event_count if event_count else None),
        "min_detection_count": min(detection_counts, default=0),
        "median_detection_count": median(detection_counts) if detection_counts else None,
        "mean_detection_count": mean(detection_counts) if detection_counts else None,
        "p95_detection_count": _nearest_rank(detection_counts, 0.95),
        "max_detection_count": max(detection_counts, default=0),
        "median_duration_hours": median(durations) if durations else None,
        "p95_duration_hours": _nearest_rank(durations, 0.95),
        "max_duration_hours": max(durations, default=0.0),
        "median_spatial_extent_m": median(extents) if extents else None,
        "p95_spatial_extent_m": _nearest_rank(extents, 0.95),
        "max_spatial_extent_m": max(extents, default=0.0),
        "events_multiple_sources": sum(bool(event["multi_source"]) for event in events),
        "events_both_sensors": sum(bool(event["both_sensors"]) for event in events),
        "events_cross_midnight": sum(bool(event["crosses_midnight"]) for event in events),
        "events_multi_day": sum(bool(event["multi_day"]) for event in events),
        "events_possible_chain_merge": sum(bool(event["possible_chain_merge"]) for event in events),
        "largest_event_detection_share_pct": (100.0 * largest_count / total if total else None),
        "largest_event_detection_count": largest_count,
        "all_detections_preserved": (
            len(result.membership) == total
            and len({row["detection_id"] for row in result.membership}) == total
        ),
        "detection_count_total": total,
        "mega_cluster_detected": result.mega_cluster_detected,
    }


def coassignment_pairs(result: ClusterResult) -> set[tuple[str, str]]:
    """Return unordered detection pairs assigned to the same event."""

    by_event: dict[str, list[str]] = {}
    for row in result.membership:
        by_event.setdefault(str(row["event_id"]), []).append(str(row["detection_id"]))
    pairs: set[tuple[str, str]] = set()
    for detection_ids in by_event.values():
        ordered = sorted(detection_ids)
        pairs.update(
            (ordered[first], ordered[second])
            for first in range(len(ordered))
            for second in range(first + 1, len(ordered))
        )
    return pairs


def sensitivity_neighbor_pairs(
    configurations: Sequence[ClusteringConfig] = DEFAULT_CONFIGURATIONS,
) -> tuple[tuple[ClusteringConfig, ClusteringConfig, str], ...]:
    """Return adjacent grid cells along time and radius axes."""

    by_key = {(config.radius_m, config.time_window_hours): config for config in configurations}
    pairs: list[tuple[ClusteringConfig, ClusteringConfig, str]] = []
    for radius in RADIUS_GRID:
        for left_hours, right_hours in zip(TIME_WINDOW_GRID, TIME_WINDOW_GRID[1:]):
            left = by_key.get((radius, left_hours))
            right = by_key.get((radius, right_hours))
            if left and right:
                pairs.append((left, right, "time_window"))
    for hours in TIME_WINDOW_GRID:
        for left_radius, right_radius in zip(RADIUS_GRID, RADIUS_GRID[1:]):
            left = by_key.get((left_radius, hours))
            right = by_key.get((right_radius, hours))
            if left and right:
                pairs.append((left, right, "radius"))
    return tuple(pairs)


def build_stability_rows(
    results: Mapping[str, ClusterResult],
    configurations: Sequence[ClusteringConfig] = DEFAULT_CONFIGURATIONS,
) -> list[dict[str, Any]]:
    """Compare adjacent configurations using co-assignment retention/Jaccard."""

    rows: list[dict[str, Any]] = []
    for left_config, right_config, axis in sensitivity_neighbor_pairs(configurations):
        left_result = results[left_config.configuration_id]
        right_result = results[right_config.configuration_id]
        left_pairs = coassignment_pairs(left_result)
        right_pairs = coassignment_pairs(right_result)
        intersection = len(left_pairs & right_pairs)
        union = len(left_pairs | right_pairs)
        rows.append(
            {
                "configuration_id_a": left_config.configuration_id,
                "configuration_id_b": right_config.configuration_id,
                "axis": axis,
                "event_count_a": len(left_result.events),
                "event_count_b": len(right_result.events),
                "event_count_change": len(right_result.events) - len(left_result.events),
                "singleton_rate_pct_a": summary_metrics(left_result)["singleton_rate_pct"],
                "singleton_rate_pct_b": summary_metrics(right_result)["singleton_rate_pct"],
                "largest_event_count_a": summary_metrics(left_result)["largest_event_detection_count"],
                "largest_event_count_b": summary_metrics(right_result)["largest_event_detection_count"],
                "pair_retention_rate": (intersection / len(left_pairs) if left_pairs else None),
                "jaccard_coassignment": (intersection / union if union else 1.0),
            }
        )
    return rows


def csv_value(value: Any) -> Any:
    """Convert nested/boolean values to deterministic CSV-safe values."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return _compact_json(value)
    if isinstance(value, float):
        return _format_float(value)
    return value


def write_csv(path: Path | str, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    """Write a UTF-8 CSV with stable field order and no index column."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path | str, value: Mapping[str, Any]) -> None:
    """Write deterministic UTF-8 JSON with a trailing newline."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def format_markdown_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, bool):
        return "sí" if value else "no"
    return str(value)
