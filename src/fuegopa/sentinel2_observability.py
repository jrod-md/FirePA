"""Reproducible Sentinel-2 observability inventory for the 30-event pilot.

The module inventories scenes, valid B8/B12 pixel coverage and Cloud Score+
clarity only.  It does not download raster data, inspect images manually, or
compute a spectral index or burn label.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .clustering import _project_wgs84_to_utm17
from .earth_engine import (
    CLOUD_SCORE_PLUS_COLLECTION,
    SENTINEL2_SR_COLLECTION,
    EarthEngineClient,
    EarthEngineQueryError,
)
from .provisional import (
    FROZEN_CONFIGURATION_ID,
    PILOT_COLUMNS,
    ProvisionalValidationError,
    read_csv_rows,
)


CALCULATION_CRS = "EPSG:32617"
OUTPUT_CRS = "EPSG:4326"
AOI_METHOD = "detection_union_buffer"
AOI_ERROR_MARGIN_VALUE = 1
PROJECTED_ERROR_MARGIN_UNIT = "projected"
TRANSFORM_ERROR_MARGIN_UNIT = "meters"
PIPELINE_VERSION = "fuegopa-sentinel2-observability-v1"
PILOT_EXPECTED_COUNT = 30
BUFFER_OPTIONS = ((500, "b0500"), (1000, "b1000"), (1500, "b1500"))
PRE_WINDOW_OPTIONS = {
    "pre30": (30, 5),
    "pre60": (60, 5),
}
POST_WINDOW_OPTIONS = {
    "post45": (5, 45),
    "post90": (5, 90),
}
WINDOW_PAIR_OPTIONS = tuple(
    f"{pre_id}_{post_id}"
    for pre_id in PRE_WINDOW_OPTIONS
    for post_id in POST_WINDOW_OPTIONS
)
CLEAR_THRESHOLDS = (0.50, 0.60, 0.65)
USABILITY_RULES = {
    "A": {"coverage_min": 0.90, "clear_field": "clear_fraction_cs_cdf_050", "clear_min": 0.70, "clear_threshold": 0.50},
    "B": {"coverage_min": 0.90, "clear_field": "clear_fraction_cs_cdf_060", "clear_min": 0.70, "clear_threshold": 0.60},
    "C": {"coverage_min": 0.90, "clear_field": "clear_fraction_cs_cdf_065", "clear_min": 0.70, "clear_threshold": 0.65},
    "D": {"coverage_min": 0.95, "clear_field": "clear_fraction_cs_cdf_060", "clear_min": 0.80, "clear_threshold": 0.60},
}

SCENE_COLUMNS = (
    "event_id",
    "configuration_id",
    "aoi_id",
    "aoi_buffer_m",
    "aoi_area_m2",
    "aoi_area_km2",
    "geometry_hash",
    "member_detection_count",
    "geometry_valid",
    "period_role",
    "window_id",
    "window_start_utc",
    "window_end_utc",
    "combination_id",
    "sentinel2_scene_id",
    "system_index",
    "acquisition_timestamp_utc",
    "mgrs_tile",
    "spacecraft_name",
    "processing_baseline",
    "cloudy_pixel_percentage",
    "data_coverage_fraction",
    "cloud_score_linked",
    "cloud_score_model_version",
    "no_context_fraction",
    "cs_mean",
    "cs_median",
    "cs_cdf_mean",
    "cs_cdf_median",
    "clear_fraction_cs_cdf_050",
    "clear_fraction_cs_cdf_060",
    "clear_fraction_cs_cdf_065",
    "valid_pixel_count",
    "total_expected_pixel_count",
    "cloud_score_pixel_count",
    "valid_cloud_score_pixel_count",
    "query_timestamp_utc",
    "pipeline_version",
)

AOI_COLUMNS = (
    "event_id",
    "configuration_id",
    "aoi_id",
    "aoi_method",
    "buffer_m",
    "aoi_area_m2",
    "aoi_area_km2",
    "geometry_hash",
    "member_detection_count",
    "geometry_valid",
    "pipeline_version",
)

OBSERVABILITY_COLUMNS = (
    "event_id",
    "configuration_id",
    "aoi_method",
    "aoi_id",
    "aoi_buffer_m",
    "aoi_area_m2",
    "aoi_area_km2",
    "geometry_hash",
    "window_id",
    "combination_id",
    "rule_id",
    "data_coverage_threshold",
    "clear_fraction_threshold",
    "pre_window_start",
    "pre_window_end",
    "post_window_start",
    "post_window_end",
    "pre_scene_count",
    "post_scene_count",
    "usable_pre_scene_count",
    "usable_post_scene_count",
    "selected_pre_scene_id",
    "selected_post_scene_id",
    "best_pre_scene_id",
    "best_post_scene_id",
    "best_pre_clear_fraction",
    "best_post_clear_fraction",
    "days_between_event_and_pre",
    "days_between_event_and_post",
    "pre_cloud_fraction",
    "post_cloud_fraction",
    "pre_coverage_fraction",
    "post_coverage_fraction",
    "usable_pair_exists",
    "observability_status",
    "exclusion_reason",
    "exclusion_reasons",
    "event_month",
    "event_size_class",
    "source_class",
    "chain_class",
    "processing_timestamp_utc",
    "pipeline_version",
)

ERROR_COLUMNS = (
    "event_id",
    "configuration_id",
    "error_type",
    "error_message",
    "error_stage",
    "operation",
    "cause_type",
    "cause_message",
    "aoi_id",
    "window_id",
    "attempt",
    "retry_count",
    "max_retries",
    "traceback_file",
    "query_timestamp_utc",
    "pipeline_version",
)

ATTRITION_COLUMNS = ("stage", "count", "notes")
SENSITIVITY_COLUMNS = (
    "aoi_id",
    "buffer_m",
    "window_id",
    "rule_id",
    "event_combination_count",
    "events_with_pre_scene",
    "events_with_post_scene",
    "events_with_usable_pair",
    "usable_pair_rate",
)

OBSERVABILITY_STATUS_VALUES = (
    "not_assessed",
    "no_pre_scene",
    "no_post_scene",
    "no_usable_pre_scene",
    "no_usable_post_scene",
    "usable_both",
    "partial_coverage",
    "ambiguous",
    "excluded",
)

EXCLUSION_REASON_VALUES = (
    "not_applicable",
    "no_pre_scene",
    "no_post_scene",
    "no_usable_pre_scene",
    "no_usable_post_scene",
    "cloud_score_unavailable",
    "coverage_below_threshold",
    "clear_fraction_below_threshold",
    "no_valid_b8_b12_pixels",
    "partial_coverage",
    "invalid_aoi",
    "spatial_overlap_ambiguous",
    "temporal_overlap_ambiguous",
    "query_error",
    "other",
)


class ObservabilityValidationError(ValueError):
    """Raised when the pilot or an observation record is unsafe to process."""


@dataclass(frozen=True)
class DetectionInput:
    detection_id: str
    timestamp_utc: datetime
    latitude: float
    longitude: float


@dataclass(frozen=True)
class EventInput:
    event_id: str
    configuration_id: str
    start_timestamp_utc: datetime
    end_timestamp_utc: datetime
    detection_count: int
    source_count: int
    sources: str
    possible_chain_merge: bool
    month: str
    event_size_class: str
    source_class: str
    chain_class: str
    detections: tuple[DetectionInput, ...]

    @property
    def event_hash(self) -> str:
        payload = {
            "event_id": self.event_id,
            "configuration_id": self.configuration_id,
            "start_timestamp_utc": _format_timestamp(self.start_timestamp_utc),
            "end_timestamp_utc": _format_timestamp(self.end_timestamp_utc),
            "detection_count": self.detection_count,
            "source_count": self.source_count,
            "sources": self.sources,
            "possible_chain_merge": self.possible_chain_merge,
            "detections": [
                {
                    "detection_id": detection.detection_id,
                    "timestamp_utc": _format_timestamp(detection.timestamp_utc),
                    "latitude": detection.latitude,
                    "longitude": detection.longitude,
                }
                for detection in self.detections
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WindowSpec:
    window_id: str
    period_role: str
    start_utc: datetime
    end_utc: datetime

    @property
    def query_end_utc(self) -> datetime:
        # Earth Engine filterDate uses an exclusive end. Include a scene exactly
        # on the documented boundary without changing the recorded window.
        return self.end_utc + timedelta(seconds=1)


@dataclass(frozen=True)
class AOI:
    event_id: str
    aoi_id: str
    buffer_m: int
    geometry_hash: str
    member_detection_count: int
    geometry_valid: bool
    geometry_utm: Any = field(default=None, repr=False, compare=False)
    geometry_wgs84: Any = field(default=None, repr=False, compare=False)
    area_server_m2: Any = field(default=None, repr=False, compare=False)


def _format_timestamp(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_timestamp(value: Any, field: str = "timestamp_utc") -> datetime:
    text = "" if value is None else str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ObservabilityValidationError(f"Timestamp inválido en {field}: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ObservabilityValidationError(f"Timestamp sin zona horaria en {field}: {value!r}")
    normalized = parsed.astimezone(timezone.utc)
    if normalized.year == 2026:
        raise ObservabilityValidationError(f"No se permite dato de 2026 en {field}: {value!r}")
    return normalized


def _number(value: Any, field: str, *, integer: bool = False) -> float | int:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ObservabilityValidationError(f"Valor numérico inválido en {field}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ObservabilityValidationError(f"Valor no finito en {field}: {value!r}")
    return int(parsed) if integer else parsed


def _bool_value(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "si", "sí"}


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def _required_key_text(value: Any, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ObservabilityValidationError(f"Clave vacía en {field}")
    return text


def normalize_buffer_m(value: Any, field: str = "buffer_m") -> int:
    parsed = int(_number(value, field, integer=True))
    allowed = {buffer_m for buffer_m, _ in BUFFER_OPTIONS}
    if parsed not in allowed:
        raise ObservabilityValidationError(f"Buffer no permitido en {field}: {value!r}")
    return parsed


def normalize_aoi_id(value: Any, buffer_m: Any = None, field: str = "aoi_id") -> str:
    text = "" if value is None else str(value).strip().casefold()
    if not text and buffer_m not in (None, ""):
        return dict(BUFFER_OPTIONS)[normalize_buffer_m(buffer_m, "aoi_buffer_m")]
    labels = {buffer: label for buffer, label in BUFFER_OPTIONS}
    if text in set(labels.values()):
        return text
    candidate = text[1:] if text.startswith("b") else text
    try:
        parsed = int(float(candidate))
    except (TypeError, ValueError) as exc:
        raise ObservabilityValidationError(f"AOI inválido en {field}: {value!r}") from exc
    if parsed not in labels:
        raise ObservabilityValidationError(f"AOI inválido en {field}: {value!r}")
    return labels[parsed]


def normalize_period_role(value: Any, field: str = "period_role") -> str:
    text = _required_key_text(value, field).casefold()
    if text not in {"pre", "post"}:
        raise ObservabilityValidationError(f"period_role inválido en {field}: {value!r}")
    return text


def normalize_window_component_id(value: Any, field: str = "window_id") -> str:
    text = _required_key_text(value, field).casefold().replace("-", "").replace("_", "")
    allowed = set(PRE_WINDOW_OPTIONS) | set(POST_WINDOW_OPTIONS)
    if text not in allowed:
        raise ObservabilityValidationError(f"window_id inválido en {field}: {value!r}")
    return text


def make_window_pair_id(pre_window_id: Any, post_window_id: Any) -> str:
    pre_id = normalize_window_component_id(pre_window_id, "pre_window_id")
    post_id = normalize_window_component_id(post_window_id, "post_window_id")
    if not pre_id.startswith("pre") or not post_id.startswith("post"):
        raise ObservabilityValidationError(f"Pareja de ventanas inválida: {pre_id}_{post_id}")
    return f"{pre_id}_{post_id}"


def parse_window_pair_id(value: Any, field: str = "window_pair_id") -> tuple[str, str]:
    text = _required_key_text(value, field).casefold()
    parts = text.split("_")
    if len(parts) != 2:
        raise ObservabilityValidationError(f"window_pair_id inválido en {field}: {value!r}")
    return (
        normalize_window_component_id(parts[0], f"{field}.pre"),
        normalize_window_component_id(parts[1], f"{field}.post"),
    )


def make_combination_id(aoi_id: Any, pre_window_id: Any, post_window_id: Any) -> str:
    return f"{normalize_aoi_id(aoi_id)}_{make_window_pair_id(pre_window_id, post_window_id)}"


def normalize_combination_id(value: Any, field: str = "combination_id") -> str:
    text = _required_key_text(value, field).casefold()
    parts = text.split("_")
    if len(parts) != 3:
        raise ObservabilityValidationError(f"combination_id inválido en {field}: {value!r}")
    return make_combination_id(parts[0], parts[1], parts[2])


def normalize_scene_record(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    buffer_value = row.get("aoi_buffer_m", row.get("buffer_m"))
    normalized["event_id"] = _required_key_text(row.get("event_id"), "event_id")
    normalized["aoi_id"] = normalize_aoi_id(row.get("aoi_id"), buffer_value)
    normalized["aoi_buffer_m"] = normalize_buffer_m(buffer_value, "aoi_buffer_m")
    normalized["period_role"] = normalize_period_role(row.get("period_role"))
    normalized["window_id"] = normalize_window_component_id(row.get("window_id"))
    normalized["combination_id"] = normalize_combination_id(row.get("combination_id"))
    for field in ("configuration_id", "sentinel2_scene_id", "system_index"):
        if row.get(field) not in (None, ""):
            normalized[field] = str(row[field]).strip()
    return normalized


def normalize_aoi_record(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    buffer_value = row.get("buffer_m", row.get("aoi_buffer_m"))
    buffer = normalize_buffer_m(buffer_value, "buffer_m")
    normalized["event_id"] = _required_key_text(row.get("event_id"), "event_id")
    normalized["aoi_id"] = normalize_aoi_id(row.get("aoi_id"), buffer)
    normalized["buffer_m"] = buffer
    normalized["aoi_buffer_m"] = buffer
    if row.get("configuration_id") not in (None, ""):
        normalized["configuration_id"] = str(row["configuration_id"]).strip()
    return normalized


def normalize_inventory_rows(
    scene_rows: Sequence[Mapping[str, Any]],
    aoi_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_columns(scene_rows, SCENE_COLUMNS, "inventario de escenas")
    _validate_columns(aoi_rows, AOI_COLUMNS, "inventario de AOI")
    normalized_scenes = [normalize_scene_record(row) for row in scene_rows]
    normalized_aois = [normalize_aoi_record(row) for row in aoi_rows]
    for row in (*normalized_scenes, *normalized_aois):
        if str(row.get("configuration_id", "")).strip() != FROZEN_CONFIGURATION_ID:
            raise ObservabilityValidationError(
                f"Inventario fuera de {FROZEN_CONFIGURATION_ID}: {row.get('event_id', '')}"
            )
    for row in normalized_scenes:
        if not _scene_id(row):
            raise ObservabilityValidationError(
                f"Inventario de escenas sin sentinel2_scene_id/system_index: {row['event_id']}"
            )
    return normalized_scenes, normalized_aois


def _validate_columns(rows: Sequence[Mapping[str, Any]], required: Sequence[str], context: str) -> None:
    if not rows:
        raise ObservabilityValidationError(f"{context}: no contiene filas")
    missing = [column for column in required if column not in rows[0]]
    if missing:
        raise ObservabilityValidationError(f"{context}: faltan columnas {', '.join(missing)}")


def load_pilot_events(
    pilot_path: Path | str,
    events_path: Path | str,
    membership_path: Path | str,
    *,
    expected_count: int = PILOT_EXPECTED_COUNT,
) -> list[EventInput]:
    """Load only the preselected pilot and its member detections."""

    pilot_rows = read_csv_rows(pilot_path)
    _validate_columns(pilot_rows, PILOT_COLUMNS, "piloto")
    if len(pilot_rows) != expected_count:
        raise ObservabilityValidationError(
            f"El piloto debe contener {expected_count} eventos; recibió {len(pilot_rows)}"
        )
    pilot_ids = [str(row["event_id"]).strip() for row in pilot_rows]
    if len(set(pilot_ids)) != len(pilot_ids):
        raise ObservabilityValidationError("El piloto contiene event_id duplicados")
    if any(str(row.get("configuration_id", "")).strip() != FROZEN_CONFIGURATION_ID for row in pilot_rows):
        raise ObservabilityValidationError("El piloto contiene una configuración diferente de r1500_t06")

    event_rows = read_csv_rows(events_path)
    membership_rows = read_csv_rows(membership_path)
    _validate_columns(
        event_rows,
        ("event_id", "configuration_id", "start_timestamp_utc", "end_timestamp_utc", "detection_count", "source_count", "sources", "possible_chain_merge"),
        "eventos provisionales",
    )
    _validate_columns(
        membership_rows,
        ("event_id", "configuration_id", "detection_id", "timestamp_utc", "latitude", "longitude"),
        "membresía",
    )
    events_by_id = {str(row["event_id"]): row for row in event_rows}
    members_by_event: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in membership_rows:
        members_by_event[str(row["event_id"])].append(row)

    output: list[EventInput] = []
    for pilot_row in sorted(pilot_rows, key=lambda row: int(row["sampling_rank"])):
        event_id = str(pilot_row["event_id"])
        event_row = events_by_id.get(event_id)
        if event_row is None:
            raise ObservabilityValidationError(f"El event_id del piloto no existe en eventos: {event_id}")
        if str(event_row["configuration_id"]).strip() != FROZEN_CONFIGURATION_ID:
            raise ObservabilityValidationError(f"Evento fuera de r1500_t06: {event_id}")
        start = parse_utc_timestamp(event_row["start_timestamp_utc"], f"{event_id}.start_timestamp_utc")
        end = parse_utc_timestamp(event_row["end_timestamp_utc"], f"{event_id}.end_timestamp_utc")
        if end < start:
            raise ObservabilityValidationError(f"El evento tiene fin anterior al inicio: {event_id}")
        expected_members = int(_number(event_row["detection_count"], f"{event_id}.detection_count", integer=True))
        member_rows = members_by_event.get(event_id, [])
        if len(member_rows) != expected_members:
            raise ObservabilityValidationError(
                f"Membresía inconsistente para {event_id}: {len(member_rows)} != {expected_members}"
            )
        detections: list[DetectionInput] = []
        for member in member_rows:
            if str(member["configuration_id"]).strip() != FROZEN_CONFIGURATION_ID:
                raise ObservabilityValidationError(f"Detección fuera de r1500_t06: {member['detection_id']}")
            detections.append(
                DetectionInput(
                    detection_id=str(member["detection_id"]),
                    timestamp_utc=parse_utc_timestamp(member["timestamp_utc"], f"{event_id}.timestamp_utc"),
                    latitude=float(_number(member["latitude"], f"{event_id}.latitude")),
                    longitude=float(_number(member["longitude"], f"{event_id}.longitude")),
                )
            )
        detection_ids = [detection.detection_id for detection in detections]
        if len(set(detection_ids)) != len(detection_ids):
            raise ObservabilityValidationError(f"Detecciones duplicadas dentro de {event_id}")
        output.append(
            EventInput(
                event_id=event_id,
                configuration_id=FROZEN_CONFIGURATION_ID,
                start_timestamp_utc=start,
                end_timestamp_utc=end,
                detection_count=expected_members,
                source_count=int(_number(event_row["source_count"], f"{event_id}.source_count", integer=True)),
                sources=str(event_row.get("sources", "")),
                possible_chain_merge=_bool_value(event_row.get("possible_chain_merge")),
                month=str(pilot_row.get("month", start.strftime("%Y-%m"))),
                event_size_class=str(pilot_row.get("event_size_class", "")),
                source_class=str(pilot_row.get("source_class", "")),
                chain_class=str(pilot_row.get("chain_class", "")),
                detections=tuple(sorted(detections, key=lambda detection: detection.detection_id)),
            )
        )
    return output


def make_aoi_geometry_hash(event: EventInput, buffer_m: int) -> str:
    if buffer_m not in {option[0] for option in BUFFER_OPTIONS}:
        raise ObservabilityValidationError(f"Buffer no permitido: {buffer_m}")
    projected = [
        {
            "detection_id": detection.detection_id,
            "x_m": round(_project_wgs84_to_utm17(detection.latitude, detection.longitude)[0], 6),
            "y_m": round(_project_wgs84_to_utm17(detection.latitude, detection.longitude)[1], 6),
        }
        for detection in event.detections
    ]
    payload = {
        "method": AOI_METHOD,
        "crs": CALCULATION_CRS,
        "buffer_m": buffer_m,
        "members": projected,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_aoi(event: EventInput, buffer_m: int, client: EarthEngineClient | None = None) -> AOI:
    """Build dissolved point buffers in UTM, then transform the query AOI to WGS84."""

    label = dict(BUFFER_OPTIONS).get(buffer_m)
    if label is None:
        raise ObservabilityValidationError(f"Buffer no permitido: {buffer_m}")
    if not event.detections:
        raise ObservabilityValidationError(f"Evento sin detecciones: {event.event_id}")
    geometry_hash = make_aoi_geometry_hash(event, buffer_m)
    if client is None:
        return AOI(
            event_id=event.event_id,
            aoi_id=label,
            buffer_m=buffer_m,
            geometry_hash=geometry_hash,
            member_detection_count=len(event.detections),
            geometry_valid=True,
        )

    ee = client.ee_module
    projection = ee.Projection(CALCULATION_CRS)
    projected_error_margin = ee.ErrorMargin(AOI_ERROR_MARGIN_VALUE, PROJECTED_ERROR_MARGIN_UNIT)
    transform_error_margin = ee.ErrorMargin(AOI_ERROR_MARGIN_VALUE, TRANSFORM_ERROR_MARGIN_UNIT)
    geometry_utm = None
    for detection in event.detections:
        x_m, y_m = _project_wgs84_to_utm17(detection.latitude, detection.longitude)
        point = ee.Geometry.Point([x_m, y_m], proj=projection)
        buffered = point.buffer(buffer_m, maxError=projected_error_margin, proj=projection)
        geometry_utm = (
            buffered
            if geometry_utm is None
            else geometry_utm.union(buffered, maxError=projected_error_margin, proj=projection)
        )
    geometry_wgs84 = geometry_utm.transform(OUTPUT_CRS, maxError=transform_error_margin)
    area_server_m2 = geometry_utm.area(maxError=projected_error_margin, proj=projection)
    return AOI(
        event_id=event.event_id,
        aoi_id=label,
        buffer_m=buffer_m,
        geometry_hash=geometry_hash,
        member_detection_count=len(event.detections),
        geometry_valid=True,
        geometry_utm=geometry_utm,
        geometry_wgs84=geometry_wgs84,
        area_server_m2=area_server_m2,
    )


def build_window_specs(event: EventInput) -> dict[str, tuple[WindowSpec, WindowSpec]]:
    result: dict[str, tuple[WindowSpec, WindowSpec]] = {}
    for pre_id, (pre_days, pre_gap_days) in PRE_WINDOW_OPTIONS.items():
        pre = WindowSpec(
            window_id=pre_id,
            period_role="pre",
            start_utc=event.start_timestamp_utc - timedelta(days=pre_days),
            end_utc=event.start_timestamp_utc - timedelta(days=pre_gap_days),
        )
        for post_id, (post_gap_days, post_days) in POST_WINDOW_OPTIONS.items():
            post = WindowSpec(
                window_id=post_id,
                period_role="post",
                start_utc=event.end_timestamp_utc + timedelta(days=post_gap_days),
                end_utc=event.end_timestamp_utc + timedelta(days=post_days),
            )
            result[f"{pre_id}_{post_id}"] = (pre, post)
    return result


def _server_default(value: Any, default: Any = 0) -> Any:
    return value if value is not None else default


def _scene_feature(
    image: Any,
    *,
    event: EventInput,
    aoi: AOI,
    window: WindowSpec,
    combination_id: str,
    query_timestamp_utc: str,
    ee: Any,
) -> Any:
    geometry = aoi.geometry_wgs84
    valid_mask = image.select(["B8", "B12"]).mask().reduce(ee.Reducer.min()).rename("valid")
    score_mask = image.select("cs_cdf").mask().rename("score")
    joint_mask = valid_mask.And(score_mask).rename("joint")
    total_image = ee.Image.constant(1).rename("total")

    def reduce_sum(mask: Any, band_name: str) -> Any:
        reduced = mask.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=20,
            maxPixels=100000000,
            bestEffort=True,
            tileScale=4,
        )
        return ee.Dictionary(reduced).get(band_name, 0)

    valid_count = ee.Number(reduce_sum(valid_mask, "valid"))
    score_count = ee.Number(reduce_sum(score_mask, "score"))
    joint_count = ee.Number(reduce_sum(joint_mask, "joint"))
    total_count = ee.Number(
        ee.Dictionary(
            total_image.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=geometry,
                scale=20,
                maxPixels=100000000,
                bestEffort=True,
                tileScale=4,
            )
        ).get("total", 0)
    )
    score_stats = image.select(["cs", "cs_cdf"]).updateMask(joint_mask).reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True),
        geometry=geometry,
        scale=20,
        maxPixels=100000000,
        bestEffort=True,
        tileScale=4,
    )

    def clear_fraction(threshold: float, name: str) -> Any:
        clear_mask = joint_mask.And(image.select("cs_cdf").gte(threshold)).rename(name)
        clear_count = ee.Number(reduce_sum(clear_mask, name))
        return ee.Algorithms.If(joint_count.gt(0), clear_count.divide(joint_count), None)

    properties = {
        "record_type": "scene",
        "event_id": event.event_id,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "aoi_id": aoi.aoi_id,
        "aoi_buffer_m": aoi.buffer_m,
        "aoi_area_m2": aoi.area_server_m2,
        "aoi_area_km2": ee.Number(aoi.area_server_m2).divide(1000000),
        "geometry_hash": aoi.geometry_hash,
        "member_detection_count": aoi.member_detection_count,
        "geometry_valid": aoi.geometry_valid,
        "period_role": window.period_role,
        "window_id": window.window_id,
        "window_start_utc": _format_timestamp(window.start_utc),
        "window_end_utc": _format_timestamp(window.end_utc),
        "combination_id": combination_id,
        "sentinel2_scene_id": image.get("system:id"),
        "system_index": image.get("system:index"),
        "acquisition_timestamp_utc": ee.Date(image.get("system:time_start")).format("YYYY-MM-dd'T'HH:mm:ss'Z'"),
        "mgrs_tile": image.get("MGRS_TILE"),
        "spacecraft_name": image.get("SPACECRAFT_NAME"),
        "processing_baseline": image.get("PROCESSING_BASELINE"),
        "cloudy_pixel_percentage": image.get("CLOUDY_PIXEL_PERCENTAGE"),
        "data_coverage_fraction": ee.Algorithms.If(total_count.gt(0), valid_count.divide(total_count), None),
        "cloud_score_linked": score_count.gt(0),
        "cloud_score_model_version": image.get("MODEL_VERSION"),
        "no_context_fraction": image.get("NO_CONTEXT_FRACTION"),
        "cs_mean": ee.Dictionary(score_stats).get("cs_mean"),
        "cs_median": ee.Dictionary(score_stats).get("cs_median"),
        "cs_cdf_mean": ee.Dictionary(score_stats).get("cs_cdf_mean"),
        "cs_cdf_median": ee.Dictionary(score_stats).get("cs_cdf_median"),
        "clear_fraction_cs_cdf_050": clear_fraction(0.50, "clear_050"),
        "clear_fraction_cs_cdf_060": clear_fraction(0.60, "clear_060"),
        "clear_fraction_cs_cdf_065": clear_fraction(0.65, "clear_065"),
        "valid_pixel_count": valid_count,
        "total_expected_pixel_count": total_count,
        "cloud_score_pixel_count": score_count,
        "valid_cloud_score_pixel_count": joint_count,
        "query_timestamp_utc": query_timestamp_utc,
        "pipeline_version": PIPELINE_VERSION,
    }
    return ee.Feature(None, properties)


def _aoi_feature(aoi: AOI, event: EventInput, ee: Any) -> Any:
    return ee.Feature(
        None,
        {
            "record_type": "aoi",
            "event_id": event.event_id,
            "configuration_id": FROZEN_CONFIGURATION_ID,
            "aoi_id": aoi.aoi_id,
            "aoi_method": AOI_METHOD,
            "buffer_m": aoi.buffer_m,
            "aoi_area_m2": aoi.area_server_m2,
            "aoi_area_km2": ee.Number(aoi.area_server_m2).divide(1000000),
            "geometry_hash": aoi.geometry_hash,
            "member_detection_count": aoi.member_detection_count,
            "geometry_valid": aoi.geometry_valid,
            "pipeline_version": PIPELINE_VERSION,
        },
    )


def build_event_query(
    client: EarthEngineClient,
    event: EventInput,
    query_timestamp_utc: str,
) -> tuple[Any, list[AOI]]:
    """Build one server-side feature collection for all 12 combinations."""

    ee = client.ee_module
    windows = build_window_specs(event)
    aoi_features: list[Any] = []
    scene_collections: list[Any] = []
    aois: list[AOI] = []
    sr_collection = client.image_collection(SENTINEL2_SR_COLLECTION)
    cloud_collection = client.image_collection(CLOUD_SCORE_PLUS_COLLECTION)
    for buffer_m, aoi_id in BUFFER_OPTIONS:
        try:
            aoi = build_aoi(event, buffer_m, client)
        except EarthEngineQueryError:
            raise
        except Exception as exc:
            operation = f"construcción del AOI {aoi_id} del evento {event.event_id}"
            raise EarthEngineQueryError.from_exception(
                exc,
                operation=operation,
                error_stage="build_aoi",
                event_id=event.event_id,
                aoi_id=aoi_id,
                attempt=1,
                retry_count=0,
                max_retries=0,
            ) from exc
        aois.append(aoi)
        aoi_features.append(_aoi_feature(aoi, event, ee))
        for window_id, (pre_window, post_window) in windows.items():
            pre_window_id, post_window_id = parse_window_pair_id(window_id)
            for window in (pre_window, post_window):
                combination_id = make_combination_id(aoi.aoi_id, pre_window_id, post_window_id)
                try:
                    linked = (
                        sr_collection.filterBounds(aoi.geometry_wgs84)
                        .filterDate(_format_timestamp(window.start_utc), _format_timestamp(window.query_end_utc))
                        .linkCollection(
                            cloud_collection.filterBounds(aoi.geometry_wgs84).filterDate(
                                _format_timestamp(window.start_utc), _format_timestamp(window.query_end_utc)
                            ),
                            linkedBands=["cs", "cs_cdf"],
                            linkedProperties=["MODEL_VERSION", "NO_CONTEXT_FRACTION"],
                            matchPropertyName="system:index",
                        )
                    )
                    scene_collections.append(
                        linked.map(
                            lambda image, event=event, aoi=aoi, window=window, combination_id=combination_id: _scene_feature(
                                image,
                                event=event,
                                aoi=aoi,
                                window=window,
                                combination_id=combination_id,
                                query_timestamp_utc=query_timestamp_utc,
                                ee=ee,
                            )
                        )
                    )
                except EarthEngineQueryError:
                    raise
                except Exception as exc:
                    operation = f"construcción de consulta {combination_id} del evento {event.event_id}"
                    raise EarthEngineQueryError.from_exception(
                        exc,
                        operation=operation,
                        error_stage="build_query",
                        event_id=event.event_id,
                        aoi_id=aoi.aoi_id,
                        window_id=window_id,
                        attempt=1,
                        retry_count=0,
                        max_retries=0,
                    ) from exc
    all_features = ee.FeatureCollection(aoi_features)
    for collection in scene_collections:
        all_features = all_features.merge(collection)
    return all_features, aois


def _parse_server_feature(feature: Mapping[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties", {}) if isinstance(feature, Mapping) else {}
    return dict(properties) if isinstance(properties, Mapping) else {}


def query_event(
    client: EarthEngineClient,
    event: EventInput,
    *,
    retry_count: int = 2,
    backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    """Resolve one event's combined AOI and scene inventory query."""

    query_timestamp = _format_timestamp(datetime.now(timezone.utc))
    try:
        server_collection, aois = build_event_query(client, event, query_timestamp)
    except EarthEngineQueryError:
        raise
    except Exception as exc:
        operation = f"construcción de consulta combinada del evento {event.event_id}"
        raise EarthEngineQueryError.from_exception(
            exc,
            operation=operation,
            error_stage="build_query",
            event_id=event.event_id,
            attempt=1,
            retry_count=0,
            max_retries=retry_count,
        ) from exc
    last_error: EarthEngineQueryError | None = None
    retries_used = 0
    operation = f"inventario del evento {event.event_id}"
    for attempt_index in range(retry_count + 1):
        attempt = attempt_index + 1
        try:
            response = client.get_info(
                server_collection,
                operation,
                error_stage="get_info",
                event_id=event.event_id,
                attempt=attempt,
                retry_count=attempt_index,
                max_retries=retry_count,
            )
            last_error = None
            retries_used = attempt_index
            break
        except Exception as exc:
            if isinstance(exc, EarthEngineQueryError):
                last_error = exc
            else:
                last_error = EarthEngineQueryError.from_exception(
                    exc,
                    operation=operation,
                    error_stage="get_info",
                    event_id=event.event_id,
                    attempt=attempt,
                    retry_count=attempt_index,
                    max_retries=retry_count,
                )
            retries_used = attempt_index
            if attempt_index >= retry_count:
                break
            time.sleep(backoff_seconds * (2**attempt_index))
    if last_error is not None:
        raise last_error
    features = response.get("features", []) if isinstance(response, Mapping) else []
    aoi_records: list[dict[str, Any]] = []
    scene_records: list[dict[str, Any]] = []
    for feature in features:
        properties = _parse_server_feature(feature)
        if properties.get("record_type") == "aoi":
            aoi_records.append(properties)
        elif properties.get("record_type") == "scene":
            scene_records.append(properties)
    # An absent AOI feature is a query error rather than an empty scene result.
    expected_aoi_ids = {aoi.aoi_id for aoi in aois}
    actual_aoi_ids = {str(row.get("aoi_id")) for row in aoi_records}
    if len(aoi_records) != len(aois) or actual_aoi_ids != expected_aoi_ids:
        cause = ValueError(f"La consulta no devolvió los AOI esperados: {sorted(actual_aoi_ids)}")
        raise EarthEngineQueryError.from_exception(
            cause,
            operation=operation,
            error_stage="validate_response",
            event_id=event.event_id,
            attempt=1,
            retry_count=retries_used,
            max_retries=retry_count,
        ) from cause
    return {
        "event_id": event.event_id,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "event_hash": event.event_hash,
        "query_timestamp_utc": query_timestamp,
        "retry_count": retries_used,
        "aoi_records": aoi_records,
        "scene_records": scene_records,
    }


def cache_signature(event: EventInput) -> dict[str, Any]:
    return {
        "event_hash": event.event_hash,
        "aoi_method": AOI_METHOD,
        "buffers_m": [value for value, _ in BUFFER_OPTIONS],
        "pre_windows": PRE_WINDOW_OPTIONS,
        "post_windows": POST_WINDOW_OPTIONS,
        "clear_thresholds": CLEAR_THRESHOLDS,
        "usability_rules": USABILITY_RULES,
        "sentinel2_collection": SENTINEL2_SR_COLLECTION,
        "cloud_score_collection": CLOUD_SCORE_PLUS_COLLECTION,
        "pipeline_version": PIPELINE_VERSION,
    }


def cache_path(cache_dir: Path | str, event_id: str) -> Path:
    safe_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_id)
    return Path(cache_dir) / f"{safe_id}.json"


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def write_event_cache(path: Path | str, signature: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"signature": _canonical(signature), "result": dict(result)}
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)


def load_event_cache(path: Path | str, signature: Mapping[str, Any]) -> dict[str, Any] | None:
    input_path = Path(path)
    if not input_path.is_file():
        return None
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if payload.get("signature") != _canonical(signature):
        return None
    result = payload.get("result")
    return dict(result) if isinstance(result, Mapping) else None


def _scene_id(scene: Mapping[str, Any]) -> str:
    return str(scene.get("sentinel2_scene_id") or scene.get("system_index") or "")


def select_scene_records_for_combination(
    scene_records: Sequence[Mapping[str, Any]],
    *,
    event_id: Any,
    aoi_id: Any,
    period_role: Any,
    window_id: Any,
    combination_id: Any,
) -> list[dict[str, Any]]:
    """Select inventory rows using the canonical event/AOI/role/window/combination key."""

    expected = (
        _required_key_text(event_id, "event_id"),
        normalize_aoi_id(aoi_id),
        normalize_period_role(period_role),
        normalize_window_component_id(window_id),
        normalize_combination_id(combination_id),
    )
    selected: list[dict[str, Any]] = []
    for scene in scene_records:
        normalized = normalize_scene_record(scene)
        key = (
            normalized["event_id"],
            normalized["aoi_id"],
            normalized["period_role"],
            normalized["window_id"],
            normalized["combination_id"],
        )
        if key == expected:
            selected.append(normalized)
    return selected


def _acquisition_time(scene: Mapping[str, Any]) -> datetime | None:
    value = scene.get("acquisition_timestamp_utc")
    if not value:
        return None
    try:
        return parse_utc_timestamp(value, "acquisition_timestamp_utc")
    except ObservabilityValidationError:
        return None


def _clear_field_for_threshold(threshold: float) -> str:
    return {
        0.50: "clear_fraction_cs_cdf_050",
        0.60: "clear_fraction_cs_cdf_060",
        0.65: "clear_fraction_cs_cdf_065",
    }[threshold]


def scene_is_usable(scene: Mapping[str, Any], rule_id: str) -> bool:
    rule = USABILITY_RULES[rule_id]
    if not _bool_value(scene.get("cloud_score_linked")):
        return False
    coverage = _optional_float(scene.get("data_coverage_fraction"))
    clear_fraction = _optional_float(scene.get(rule["clear_field"]))
    valid_pixels = _optional_int(scene.get("valid_pixel_count"))
    score_pixels = _optional_int(scene.get("cloud_score_pixel_count"))
    return (
        coverage is not None
        and coverage >= rule["coverage_min"]
        and clear_fraction is not None
        and clear_fraction >= rule["clear_min"]
        and (valid_pixels or 0) > 0
        and (score_pixels or 0) > 0
    )


def rank_scenes(scenes: Sequence[Mapping[str, Any]], event: EventInput, rule_id: str) -> list[dict[str, Any]]:
    """Rank usable scenes by coverage, clarity, then temporal proximity."""

    rule = USABILITY_RULES[rule_id]

    def key(scene: Mapping[str, Any]) -> tuple[float, float, float, str]:
        coverage = _optional_float(scene.get("data_coverage_fraction")) or 0.0
        clear_fraction = _optional_float(scene.get(rule["clear_field"])) or 0.0
        acquisition = _acquisition_time(scene)
        if acquisition is None:
            temporal_gap = float("inf")
        elif scene.get("period_role") == "pre":
            temporal_gap = max(0.0, (event.start_timestamp_utc - acquisition).total_seconds() / 86400)
        else:
            temporal_gap = max(0.0, (acquisition - event.end_timestamp_utc).total_seconds() / 86400)
        return (-coverage, -clear_fraction, temporal_gap, _scene_id(scene))

    return [dict(scene) for scene in sorted((scene for scene in scenes if scene_is_usable(scene, rule_id)), key=key)]


def _failure_reason(scenes: Sequence[Mapping[str, Any]], rule_id: str, role: str) -> str:
    if not scenes:
        return "no_pre_scene" if role == "pre" else "no_post_scene"
    if not any(_bool_value(scene.get("cloud_score_linked")) for scene in scenes):
        return "cloud_score_unavailable"
    if not any((_optional_int(scene.get("valid_pixel_count")) or 0) > 0 for scene in scenes):
        return "no_valid_b8_b12_pixels"
    rule = USABILITY_RULES[rule_id]
    if not any((_optional_float(scene.get("data_coverage_fraction")) or 0.0) >= rule["coverage_min"] for scene in scenes):
        return "coverage_below_threshold"
    return "clear_fraction_below_threshold"


def _cloud_fraction(scene: Mapping[str, Any] | None) -> float | None:
    if scene is None:
        return None
    clear = _optional_float(scene.get("clear_fraction_cs_cdf_060"))
    return 1.0 - clear if clear is not None else None


def _scene_days_from_event(scene: Mapping[str, Any] | None, event: EventInput) -> float | None:
    if scene is None:
        return None
    acquisition = _acquisition_time(scene)
    if acquisition is None:
        return None
    if scene.get("period_role") == "pre":
        return (event.start_timestamp_utc - acquisition).total_seconds() / 86400
    return (acquisition - event.end_timestamp_utc).total_seconds() / 86400


def evaluate_event_result(event: EventInput, result: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand one cached event result into AOI, scene and rule-sensitivity rows."""

    scene_records = [
        normalize_scene_record(row)
        for row in result.get("scene_records", [])
        if str(row.get("event_id", "")).strip() == event.event_id
    ]
    aoi_records: dict[str, dict[str, Any]] = {}
    for row in result.get("aoi_records", []):
        aoi_row = dict(row)
        aoi_row.setdefault("event_id", event.event_id)
        normalized = normalize_aoi_record(aoi_row)
        if normalized["event_id"] == event.event_id:
            aoi_records[normalized["aoi_id"]] = normalized
    windows = build_window_specs(event)
    aoi_rows: list[dict[str, Any]] = []
    for aoi_id, record in sorted(aoi_records.items()):
        aoi_rows.append(
            {
                "event_id": event.event_id,
                "configuration_id": FROZEN_CONFIGURATION_ID,
                "aoi_id": aoi_id,
                "aoi_method": AOI_METHOD,
                "buffer_m": record.get("buffer_m", record.get("aoi_buffer_m", "")),
                "aoi_area_m2": record.get("aoi_area_m2"),
                "aoi_area_km2": record.get("aoi_area_km2"),
                "geometry_hash": record.get("geometry_hash", ""),
                "member_detection_count": record.get("member_detection_count", len(event.detections)),
                "geometry_valid": record.get("geometry_valid", False),
                "pipeline_version": PIPELINE_VERSION,
            }
        )

    scene_rows: list[dict[str, Any]] = []
    for scene in scene_records:
        scene_rows.append({column: scene.get(column, "") for column in SCENE_COLUMNS})

    observation_rows: list[dict[str, Any]] = []
    for aoi_id, aoi_record in sorted(aoi_records.items()):
        for window_pair_id, (pre_window, post_window) in windows.items():
            pre_window_id, post_window_id = parse_window_pair_id(window_pair_id)
            combination_id = make_combination_id(aoi_id, pre_window_id, post_window_id)
            pre_scenes = select_scene_records_for_combination(
                scene_records,
                event_id=event.event_id,
                aoi_id=aoi_id,
                period_role="pre",
                window_id=pre_window_id,
                combination_id=combination_id,
            )
            post_scenes = select_scene_records_for_combination(
                scene_records,
                event_id=event.event_id,
                aoi_id=aoi_id,
                period_role="post",
                window_id=post_window_id,
                combination_id=combination_id,
            )
            for rule_id, rule in USABILITY_RULES.items():
                usable_pre = rank_scenes(pre_scenes, event, rule_id)
                usable_post = rank_scenes(post_scenes, event, rule_id)
                best_pre = usable_pre[0] if usable_pre else None
                best_post = usable_post[0] if usable_post else None
                pre_reason = _failure_reason(pre_scenes, rule_id, "pre") if not best_pre else "not_applicable"
                post_reason = _failure_reason(post_scenes, rule_id, "post") if not best_post else "not_applicable"
                reasons = [reason for reason in (pre_reason, post_reason) if reason != "not_applicable"]
                if best_pre and best_post:
                    status = "usable_both"
                elif not pre_scenes:
                    status = "no_pre_scene"
                elif not post_scenes:
                    status = "no_post_scene"
                elif not best_pre:
                    status = "no_usable_pre_scene"
                else:
                    status = "no_usable_post_scene"
                row = {
                    "event_id": event.event_id,
                    "configuration_id": FROZEN_CONFIGURATION_ID,
                    "aoi_method": AOI_METHOD,
                    "aoi_id": aoi_id,
                    "aoi_buffer_m": aoi_record.get("buffer_m", aoi_record.get("aoi_buffer_m", "")),
                    "aoi_area_m2": aoi_record.get("aoi_area_m2"),
                    "aoi_area_km2": aoi_record.get("aoi_area_km2"),
                    "geometry_hash": aoi_record.get("geometry_hash", ""),
                    "window_id": window_pair_id,
                    "combination_id": combination_id,
                    "rule_id": rule_id,
                    "data_coverage_threshold": rule["coverage_min"],
                    "clear_fraction_threshold": rule["clear_threshold"],
                    "pre_window_start": _format_timestamp(pre_window.start_utc),
                    "pre_window_end": _format_timestamp(pre_window.end_utc),
                    "post_window_start": _format_timestamp(post_window.start_utc),
                    "post_window_end": _format_timestamp(post_window.end_utc),
                    "pre_scene_count": len(pre_scenes),
                    "post_scene_count": len(post_scenes),
                    "usable_pre_scene_count": len(usable_pre),
                    "usable_post_scene_count": len(usable_post),
                    "selected_pre_scene_id": _scene_id(best_pre) if best_pre else "",
                    "selected_post_scene_id": _scene_id(best_post) if best_post else "",
                    "best_pre_scene_id": _scene_id(best_pre) if best_pre else "",
                    "best_post_scene_id": _scene_id(best_post) if best_post else "",
                    "best_pre_clear_fraction": _optional_float(best_pre.get(rule["clear_field"])) if best_pre else None,
                    "best_post_clear_fraction": _optional_float(best_post.get(rule["clear_field"])) if best_post else None,
                    "days_between_event_and_pre": _scene_days_from_event(best_pre, event),
                    "days_between_event_and_post": _scene_days_from_event(best_post, event),
                    "pre_cloud_fraction": _cloud_fraction(best_pre),
                    "post_cloud_fraction": _cloud_fraction(best_post),
                    "pre_coverage_fraction": _optional_float(best_pre.get("data_coverage_fraction")) if best_pre else None,
                    "post_coverage_fraction": _optional_float(best_post.get("data_coverage_fraction")) if best_post else None,
                    "usable_pair_exists": bool(best_pre and best_post),
                    "observability_status": status,
                    "exclusion_reason": reasons[0] if reasons else "not_applicable",
                    "exclusion_reasons": ";".join(reasons),
                    "event_month": event.month,
                    "event_size_class": event.event_size_class,
                    "source_class": event.source_class,
                    "chain_class": event.chain_class,
                    "processing_timestamp_utc": result.get("query_timestamp_utc", ""),
                    "pipeline_version": PIPELINE_VERSION,
                }
                observation_rows.append(row)
    return aoi_rows, scene_rows, observation_rows


def _count_field(row: Mapping[str, Any], field: str) -> int:
    parsed = _optional_int(row.get(field))
    if parsed is None or parsed < 0:
        raise ObservabilityValidationError(f"Conteo inválido en {field}: {row.get(field)!r}")
    return parsed


def validate_observability_invariants(
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Fail loudly when inventory rows and derived combinations cannot agree."""

    expected_event_ids = {event.event_id for event in events}
    observed_event_ids = {str(row.get("event_id", "")).strip() for row in observation_rows}
    unknown_observation_event_ids = observed_event_ids - expected_event_ids
    if unknown_observation_event_ids:
        raise ObservabilityValidationError(
            f"Observabilidad contiene eventos fuera del piloto: {sorted(unknown_observation_event_ids)}"
        )
    normalized_scene_rows = [normalize_scene_record(row) for row in scene_rows]
    scene_index: dict[tuple[str, str, str, str, str], set[str]] = defaultdict(set)
    for scene in normalized_scene_rows:
        scene_index[
            (
                scene["event_id"],
                scene["aoi_id"],
                scene["period_role"],
                scene["window_id"],
                scene["combination_id"],
            )
        ].add(_scene_id(scene))

    pre_scene_event_ids = _event_ids_with(
        observation_rows,
        lambda row: _count_field(row, "pre_scene_count") > 0,
    )
    post_scene_event_ids = _event_ids_with(
        observation_rows,
        lambda row: _count_field(row, "post_scene_count") > 0,
    )
    inventory_pre_rows = [row for row in normalized_scene_rows if row["period_role"] == "pre"]
    inventory_post_rows = [row for row in normalized_scene_rows if row["period_role"] == "post"]
    if normalized_scene_rows and not pre_scene_event_ids and not post_scene_event_ids:
        raise ObservabilityValidationError(
            "Contradicción de agregación: hay filas de inventario, pero todos los eventos tienen cero escenas pre/post"
        )
    if inventory_pre_rows and not pre_scene_event_ids:
        raise ObservabilityValidationError(
            "Contradicción de agregación: hay escenas pre en el inventario, pero ningún evento tiene escena pre"
        )
    if inventory_post_rows and not post_scene_event_ids:
        raise ObservabilityValidationError(
            "Contradicción de agregación: hay escenas post en el inventario, pero ningún evento tiene escena post"
        )

    for row in observation_rows:
        event_id = _required_key_text(row.get("event_id"), "observation.event_id")
        aoi_id = normalize_aoi_id(row.get("aoi_id"), row.get("aoi_buffer_m"))
        pre_window_id, post_window_id = parse_window_pair_id(row.get("window_id"), "observation.window_id")
        expected_combination_id = make_combination_id(aoi_id, pre_window_id, post_window_id)
        if row.get("combination_id") not in (None, ""):
            actual_combination_id = normalize_combination_id(row["combination_id"], "observation.combination_id")
            if actual_combination_id != expected_combination_id:
                raise ObservabilityValidationError(
                    f"Clave de combinación inconsistente: {row.get('combination_id')!r} != {expected_combination_id}"
                )
        pre_ids = scene_index.get((event_id, aoi_id, "pre", pre_window_id, expected_combination_id), set())
        post_ids = scene_index.get((event_id, aoi_id, "post", post_window_id, expected_combination_id), set())
        pre_count = _count_field(row, "pre_scene_count")
        post_count = _count_field(row, "post_scene_count")
        usable_pre_count = _count_field(row, "usable_pre_scene_count")
        usable_post_count = _count_field(row, "usable_post_scene_count")
        if usable_pre_count > pre_count:
            raise ObservabilityValidationError(
                f"usable_pre_scene_count excede pre_scene_count en {expected_combination_id}/{row.get('rule_id')}"
            )
        if usable_post_count > post_count:
            raise ObservabilityValidationError(
                f"usable_post_scene_count excede post_scene_count en {expected_combination_id}/{row.get('rule_id')}"
            )
        selected_pre = str(row.get("selected_pre_scene_id") or "").strip()
        selected_post = str(row.get("selected_post_scene_id") or "").strip()
        best_pre = str(row.get("best_pre_scene_id") or "").strip()
        best_post = str(row.get("best_post_scene_id") or "").strip()
        if _bool_value(row.get("usable_pair_exists")) and (not selected_pre or not selected_post):
            raise ObservabilityValidationError(
                f"usable_pair_exists sin escenas seleccionadas en {expected_combination_id}/{row.get('rule_id')}"
            )
        if selected_pre and selected_pre not in pre_ids:
            raise ObservabilityValidationError(
                f"selected_pre_scene_id no pertenece al inventario de {expected_combination_id}: {selected_pre}"
            )
        if selected_post and selected_post not in post_ids:
            raise ObservabilityValidationError(
                f"selected_post_scene_id no pertenece al inventario de {expected_combination_id}: {selected_post}"
            )
        if best_pre and best_pre not in pre_ids:
            raise ObservabilityValidationError(
                f"best_pre_scene_id no pertenece al inventario de {expected_combination_id}: {best_pre}"
            )
        if best_post and best_post not in post_ids:
            raise ObservabilityValidationError(
                f"best_post_scene_id no pertenece al inventario de {expected_combination_id}: {best_post}"
            )


def _unique_scene_metrics(
    events: Sequence[EventInput],
    scene_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Count unique scene IDs; window keys are ``<period_role>:<component window_id>``."""

    normalized_rows = [normalize_scene_record(row) for row in scene_rows]
    all_ids = {_scene_id(row) for row in normalized_rows if _scene_id(row)}
    pre_ids = {_scene_id(row) for row in normalized_rows if row["period_role"] == "pre" and _scene_id(row)}
    post_ids = {_scene_id(row) for row in normalized_rows if row["period_role"] == "post" and _scene_id(row)}
    by_event: dict[str, set[str]] = {event.event_id: set() for event in events}
    by_aoi: dict[str, set[str]] = {aoi_id: set() for _, aoi_id in BUFFER_OPTIONS}
    by_window: dict[str, set[str]] = {
        f"pre:{window_id}": set() for window_id in PRE_WINDOW_OPTIONS
    } | {
        f"post:{window_id}": set() for window_id in POST_WINDOW_OPTIONS
    }
    for row in normalized_rows:
        scene_id = _scene_id(row)
        if not scene_id:
            continue
        by_event.setdefault(row["event_id"], set()).add(scene_id)
        by_aoi.setdefault(row["aoi_id"], set()).add(scene_id)
        by_window.setdefault(f"{row['period_role']}:{row['window_id']}", set()).add(scene_id)
    return {
        "scene_inventory_row_count": len(normalized_rows),
        "unique_sentinel2_scene_count": len(all_ids),
        "unique_pre_scene_count": len(pre_ids),
        "unique_post_scene_count": len(post_ids),
        "unique_scene_count_by_event": {key: len(value) for key, value in sorted(by_event.items())},
        "unique_scene_count_by_aoi": {key: len(value) for key, value in sorted(by_aoi.items())},
        "unique_scene_count_by_window": {key: len(value) for key, value in sorted(by_window.items())},
        "scene_uniqueness_key": "sentinel2_scene_id (fallback system_index)",
    }


def _event_ids_with(rows: Sequence[Mapping[str, Any]], predicate: Any) -> set[str]:
    return {str(row["event_id"]) for row in rows if predicate(row)}


def _aggregate_rows(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, ""))].append(row)
    result: dict[str, Any] = {}
    for group, group_rows in sorted(groups.items()):
        result[group] = {
            "combination_count": len(group_rows),
            "event_count": len({str(row["event_id"]) for row in group_rows}),
            "events_with_pre_scene": len(_event_ids_with(group_rows, lambda row: int(row.get("pre_scene_count", 0)) > 0)),
            "events_with_post_scene": len(_event_ids_with(group_rows, lambda row: int(row.get("post_scene_count", 0)) > 0)),
            "events_with_usable_pair": len(_event_ids_with(group_rows, lambda row: _bool_value(row.get("usable_pair_exists")))),
        }
    return result


def rebuild_observability_from_inventory(
    events: Sequence[EventInput],
    scene_inventory_rows: Sequence[Mapping[str, Any]],
    aoi_inventory_rows: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Rebuild derived rows from local inventories without initializing Earth Engine."""

    normalized_scenes, normalized_aois = normalize_inventory_rows(scene_inventory_rows, aoi_inventory_rows)
    event_ids = {event.event_id for event in events}
    inventory_event_ids = {
        row["event_id"] for row in (*normalized_scenes, *normalized_aois)
    }
    unknown_event_ids = inventory_event_ids - event_ids
    if unknown_event_ids:
        raise ObservabilityValidationError(
            f"El inventario contiene eventos fuera del piloto: {sorted(unknown_event_ids)}"
        )

    scenes_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    aois_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized_scenes:
        scenes_by_event[row["event_id"]].append(row)
    for row in normalized_aois:
        aois_by_event[row["event_id"]].append(row)

    all_aoi_rows: list[dict[str, Any]] = []
    all_scene_rows: list[dict[str, Any]] = []
    all_observation_rows: list[dict[str, Any]] = []
    for event in events:
        event_scenes = scenes_by_event.get(event.event_id, [])
        event_aois = aois_by_event.get(event.event_id, [])
        query_timestamp = next(
            (
                str(row.get("query_timestamp_utc", ""))
                for row in event_scenes
                if row.get("query_timestamp_utc") not in (None, "")
            ),
            "",
        )
        aoi_rows, scene_rows, observation_rows = evaluate_event_result(
            event,
            {
                "query_timestamp_utc": query_timestamp,
                "aoi_records": event_aois,
                "scene_records": event_scenes,
            },
        )
        all_aoi_rows.extend(aoi_rows)
        all_scene_rows.extend(scene_rows)
        all_observation_rows.extend(observation_rows)

    validate_observability_invariants(events, all_observation_rows, all_scene_rows)
    return {
        "aoi_rows": all_aoi_rows,
        "scene_rows": all_scene_rows,
        "observation_rows": all_observation_rows,
        "errors": [dict(error) for error in errors],
    }


def build_report(
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    *,
    requested_event_count: int,
) -> dict[str, Any]:
    normalized_scene_rows = [normalize_scene_record(row) for row in scene_rows]
    validate_observability_invariants(events, observation_rows, normalized_scene_rows)
    scene_metrics = _unique_scene_metrics(events, normalized_scene_rows)
    processed_ids = {str(row["event_id"]) for row in observation_rows}
    failed_ids = {str(row["event_id"]) for row in errors}
    pre_scene_ids = _event_ids_with(observation_rows, lambda row: int(row.get("pre_scene_count", 0)) > 0)
    post_scene_ids = _event_ids_with(observation_rows, lambda row: int(row.get("post_scene_count", 0)) > 0)
    pair_ids = _event_ids_with(observation_rows, lambda row: _bool_value(row.get("usable_pair_exists")))
    rule_results: dict[str, Any] = {}
    for rule_id in USABILITY_RULES:
        rows = [row for row in observation_rows if row.get("rule_id") == rule_id]
        rule_results[rule_id] = {
            "combination_count": len(rows),
            "events_with_usable_pair": len(_event_ids_with(rows, lambda row: _bool_value(row.get("usable_pair_exists")))),
            "events_without_usable_pair": len({event.event_id for event in events} - _event_ids_with(rows, lambda row: _bool_value(row.get("usable_pair_exists")))),
        }
    missing_cloud_rows = [row for row in normalized_scene_rows if not _bool_value(row.get("cloud_score_linked"))]
    report = {
        "stage": "sentinel2_observability",
        "pipeline_version": PIPELINE_VERSION,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "pilot_universe_count": PILOT_EXPECTED_COUNT,
        "requested_event_count": requested_event_count,
        "events_processed": len(processed_ids),
        "events_failed": len(failed_ids),
        "processed_event_ids": sorted(processed_ids),
        "failed_event_ids": sorted(failed_ids),
        "scenes_pre_found": sum(row.get("period_role") == "pre" for row in normalized_scene_rows),
        "scenes_post_found": sum(row.get("period_role") == "post" for row in normalized_scene_rows),
        "events_with_at_least_one_pre_scene": len(pre_scene_ids),
        "events_with_at_least_one_post_scene": len(post_scene_ids),
        "events_with_any_usable_pair": len(pair_ids),
        "events_without_any_usable_pair": len(set(event.event_id for event in events) - pair_ids),
        "cloud_score_missing_scene_count": len(missing_cloud_rows),
        "cloud_score_missing_event_count": len({str(row["event_id"]) for row in missing_cloud_rows}),
        **scene_metrics,
        "rules": rule_results,
        "by_buffer": {
            aoi_id: {
                rule_id: _aggregate_summary([row for row in observation_rows if row.get("aoi_id") == aoi_id and row.get("rule_id") == rule_id])
                for rule_id in USABILITY_RULES
            }
            for _, aoi_id in BUFFER_OPTIONS
        },
        "by_window": {
            window_id: {
                rule_id: _aggregate_summary([row for row in observation_rows if row.get("window_id") == window_id and row.get("rule_id") == rule_id])
                for rule_id in USABILITY_RULES
            }
            for window_id in WINDOW_PAIR_OPTIONS
        },
        "by_month": _dimension_report(observation_rows, "event_month", events),
        "by_event_size": _dimension_report(observation_rows, "event_size_class", events),
        "by_source_class": _dimension_report(observation_rows, "source_class", events),
        "by_chain_class": _dimension_report(observation_rows, "chain_class", events),
        "errors": [dict(error) for error in errors],
        "retry_count_total": sum(int(error.get("retry_count", 0)) for error in errors),
        "collections": {
            "sentinel2_surface_reflectance": SENTINEL2_SR_COLLECTION,
            "cloud_score_plus": CLOUD_SCORE_PLUS_COLLECTION,
        },
        "aoi_method": AOI_METHOD,
        "buffers_m": [value for value, _ in BUFFER_OPTIONS],
        "window_pairs": list(WINDOW_PAIR_OPTIONS),
        "clear_thresholds": list(CLEAR_THRESHOLDS),
        "usability_rules": USABILITY_RULES,
        "raster_downloaded": False,
        "manual_visual_inspection": False,
        "spectral_index_computed": False,
        "project_id_stored": False,
    }
    return report


def _aggregate_summary(group_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "combination_count": len(group_rows),
        "event_count": len({str(row["event_id"]) for row in group_rows}),
        "events_with_pre_scene": len(_event_ids_with(group_rows, lambda row: int(row.get("pre_scene_count", 0)) > 0)),
        "events_with_post_scene": len(_event_ids_with(group_rows, lambda row: int(row.get("post_scene_count", 0)) > 0)),
        "events_with_usable_pair": len(_event_ids_with(group_rows, lambda row: _bool_value(row.get("usable_pair_exists")))),
    }


def _dimension_report(rows: Sequence[Mapping[str, Any]], dimension: str, events: Sequence[EventInput]) -> dict[str, Any]:
    event_values = {
        "event_month": lambda event: event.month,
        "event_size_class": lambda event: event.event_size_class,
        "source_class": lambda event: event.source_class,
        "chain_class": lambda event: event.chain_class,
    }
    if dimension not in event_values:
        raise ObservabilityValidationError(f"Dimensión de reporte no soportada: {dimension}")
    result: dict[str, Any] = {}
    for value in sorted({str(event_values[dimension](event)) for event in events}):
        subset = [row for row in rows if str(row.get(dimension, "")) == value]
        result[value] = {
            "event_count": len({str(row["event_id"]) for row in subset}),
            "events_with_any_usable_pair": len(_event_ids_with(subset, lambda row: _bool_value(row.get("usable_pair_exists")))),
            "by_rule": {
                rule_id: len(_event_ids_with([row for row in subset if row.get("rule_id") == rule_id], lambda row: _bool_value(row.get("usable_pair_exists"))))
                for rule_id in USABILITY_RULES
            },
        }
    return result


def build_attrition_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    scene_row_count = report.get("scene_inventory_row_count", report.get("scenes_pre_found", 0) + report.get("scenes_post_found", 0))
    rows = [
        ("pilot_universe", report["pilot_universe_count"], "Eventos preseleccionados antes de consultar imágenes."),
        ("requested_events", report["requested_event_count"], "Eventos solicitados en esta ejecución."),
        ("events_processed", report["events_processed"], "Eventos con inventario o resultado cacheado."),
        ("events_failed", report["events_failed"], "Eventos con error registrado."),
        ("events_with_pre_scene", report["events_with_at_least_one_pre_scene"], "Al menos una escena SR dentro de alguna ventana pre."),
        ("events_with_post_scene", report["events_with_at_least_one_post_scene"], "Al menos una escena SR dentro de alguna ventana post."),
        ("events_with_any_usable_pair", report["events_with_any_usable_pair"], "Pareja usable en alguna combinación y regla."),
        ("events_without_any_usable_pair", report["events_without_any_usable_pair"], "No implica ausencia de quema."),
        ("scene_rows", scene_row_count, "Filas de inventario SR; puede incluir repeticiones por AOI/ventana."),
        ("scene_rows_without_cloud_score", report["cloud_score_missing_scene_count"], "Se conservaron, no se eliminaron silenciosamente."),
    ]
    if "unique_sentinel2_scene_count" in report:
        rows.extend(
            [
                ("unique_scenes", report["unique_sentinel2_scene_count"], "Escenas únicas por sentinel2_scene_id; fallback system_index."),
                ("unique_pre_scenes", report["unique_pre_scene_count"], "Escenas únicas en filas pre."),
                ("unique_post_scenes", report["unique_post_scene_count"], "Escenas únicas en filas post."),
            ]
        )
    for rule_id, values in report["rules"].items():
        rows.append((f"usable_pair_rule_{rule_id}", values["events_with_usable_pair"], "Eventos con pareja según la regla descriptiva."))
    return [{"stage": stage, "count": count, "notes": notes} for stage, count, notes in rows]


def build_sensitivity_rows(observation_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for buffer_m, aoi_id in BUFFER_OPTIONS:
        for window_id in WINDOW_PAIR_OPTIONS:
            for rule_id in USABILITY_RULES:
                subset = [row for row in observation_rows if row.get("aoi_id") == aoi_id and row.get("window_id") == window_id and row.get("rule_id") == rule_id]
                event_count = len({str(row["event_id"]) for row in subset})
                pair_count = len(_event_ids_with(subset, lambda row: _bool_value(row.get("usable_pair_exists"))))
                rows.append(
                    {
                        "aoi_id": aoi_id,
                        "buffer_m": buffer_m,
                        "window_id": window_id,
                        "rule_id": rule_id,
                        "event_combination_count": event_count,
                        "events_with_pre_scene": len(_event_ids_with(subset, lambda row: int(row.get("pre_scene_count", 0)) > 0)),
                        "events_with_post_scene": len(_event_ids_with(subset, lambda row: int(row.get("post_scene_count", 0)) > 0)),
                        "events_with_usable_pair": pair_count,
                        "usable_pair_rate": pair_count / event_count if event_count else None,
                    }
                )
    return rows


def write_csv(path: Path | str, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})


def write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def write_report_markdown(path: Path | str, report: Mapping[str, Any]) -> None:
    lines = [
        "# Reporte de observabilidad Sentinel-2",
        "",
        "> Inventario de disponibilidad, cobertura B8/B12 y claridad Cloud Score+. No es validación de incendios.",
        "",
        f"- Universo piloto: `{report['pilot_universe_count']}` eventos.",
        f"- Eventos solicitados: `{report['requested_event_count']}`.",
        f"- Procesados/cacheados: `{report['events_processed']}`.",
        f"- Fallidos: `{report['events_failed']}`.",
        f"- Escenas pre/post: `{report['scenes_pre_found']}` / `{report['scenes_post_found']}`.",
        f"- Filas de inventario de escenas: `{report.get('scene_inventory_row_count', report['scenes_pre_found'] + report['scenes_post_found'])}`.",
        f"- Escenas únicas: `{report.get('unique_sentinel2_scene_count', '')}`; pre: `{report.get('unique_pre_scene_count', '')}`; post: `{report.get('unique_post_scene_count', '')}`.",
        f"- Eventos con alguna pareja usable: `{report['events_with_any_usable_pair']}`.",
        f"- Escenas sin Cloud Score+ enlazado: `{report['cloud_score_missing_scene_count']}`.",
        "- Descarga raster: `no`; inspección visual manual: `no`.",
        "- Índice espectral o etiqueta: `no`.",
        "",
        "## Reglas de usabilidad",
        "",
    ]
    lines.extend(_markdown_table(
        ["Regla", "Cobertura mínima", "Campo de claridad", "Claridad mínima", "Eventos con pareja"],
        [[rule_id, rule["coverage_min"], rule["clear_field"], rule["clear_min"], report["rules"][rule_id]["events_with_usable_pair"]] for rule_id, rule in USABILITY_RULES.items()],
    ))
    lines.extend(["", "## Atrición", ""])
    lines.extend(_markdown_table(["Etapa", "Cantidad", "Nota"], [[row["stage"], row["count"], row["notes"]] for row in build_attrition_rows(report)]))
    lines.extend(["", "## Errores", ""])
    if report["errors"]:
        lines.extend(_markdown_table(
            ["Evento", "Etapa", "Causa", "AOI", "Ventana", "Intento", "Reintentos", "Mensaje", "Traceback"],
            [
                [
                    row["event_id"],
                    row.get("error_stage", ""),
                    row.get("cause_type", ""),
                    row.get("aoi_id", ""),
                    row.get("window_id", ""),
                    row.get("attempt", ""),
                    row.get("retry_count", ""),
                    row.get("cause_message") or row.get("error_message", ""),
                    row.get("traceback_file", ""),
                ]
                for row in report["errors"]
            ],
        ))
    else:
        lines.append("No se registraron errores por evento.")
    lines.extend([
        "",
        "## Limitaciones",
        "",
        "- `CLOUDY_PIXEL_PERCENTAGE` se conserva solo como atributo de escena; la claridad del AOI usa `cs_cdf`.",
        "- La cobertura válida exige máscara conjunta de B8 y B12 y se calcula server-side a escala de 20 m.",
        "- La ausencia de Cloud Score+ no se convierte en claridad cero ni en ausencia de quema.",
        "- Las reglas A-D son una sensibilidad descriptiva; ninguna es una etiqueta ni ground truth.",
    ])
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_observability_outputs(
    output_paths: Mapping[str, Path | str],
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    aoi_rows: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    *,
    requested_event_count: int,
    write_inventories: bool = True,
) -> dict[str, Any]:
    report = build_report(events, observation_rows, scene_rows, errors, requested_event_count=requested_event_count)
    if write_inventories:
        write_csv(output_paths["scene_inventory"], SCENE_COLUMNS, scene_rows)
        write_csv(output_paths["aoi_inventory"], AOI_COLUMNS, aoi_rows)
    write_csv(output_paths["observability"], OBSERVABILITY_COLUMNS, observation_rows)
    write_csv(output_paths["errors"], ERROR_COLUMNS, errors)
    write_csv(output_paths["attrition"], ATTRITION_COLUMNS, build_attrition_rows(report))
    write_csv(output_paths["sensitivity"], SENSITIVITY_COLUMNS, build_sensitivity_rows(observation_rows))
    write_json(output_paths["report_json"], report)
    write_report_markdown(output_paths["report_markdown"], report)
    return report
