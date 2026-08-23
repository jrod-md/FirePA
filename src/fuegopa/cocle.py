"""Cohort preparation for the approved Coclé FIRMS season."""

from __future__ import annotations

import csv
import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .acquisition import FIRMS_SCHEMA_VERSION, RawArtifact, sha256_bytes
from .firms import (
    FIELD_ALIASES,
    _format_number,
    _normalize_confidence,
    _normalize_header,
    _normalize_text,
    _parse_acquisition_time,
    _parse_number,
    is_missing,
    parse_acquisition_date,
    parse_acquisition_datetime,
    validate_coordinates,
    validate_required_columns,
)
from .geo import Boundary


MAIN_START = date(2025, 1, 1)
MAIN_END = date(2025, 4, 30)
SECONDARY_START = date(2026, 1, 1)
SECONDARY_END = date(2026, 4, 30)

OPTIONAL_ALIASES: dict[str, tuple[str, ...]] = {
    "daynight": ("daynight", "day_night"),
    "version": ("version", "processing_version"),
    "type": ("type", "fire_type"),
}

DETECTION_FIELDS: tuple[str, ...] = (
    "detection_id",
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "acq_datetime_utc",
    "satellite",
    "instrument",
    "firms_source",
    "confidence_raw",
    "confidence_normalized",
    "confidence_numeric",
    "frp",
    "daynight",
    "version",
    "type",
    "raw_file",
    "raw_sha256",
    "source_row_number",
    "schema_version",
)


@dataclass
class SourceScan:
    source: str
    raw_path: Path
    raw_sha256: str
    raw_record_count: int
    headers: tuple[str, ...]
    normalized_headers: tuple[str, ...]
    raw_rows: list[dict[str, str]]
    schema_valid: bool
    schema_error: str | None
    detections: list[dict[str, Any]]


@dataclass
class FilterResult:
    scans: list[SourceScan]
    all_detections: list[dict[str, Any]]
    final_detections: list[dict[str, Any]]
    counts: dict[str, int]
    duplicate_summary: dict[str, int]


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]], str | None]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [], [], f"No se pudo leer el CSV raw: {type(exc).__name__}"
    if any(None in row for row in rows):
        return headers, rows, "El CSV contiene filas con más campos que sus encabezados."
    return headers, rows, None


def _optional_mapping(headers: Sequence[str]) -> dict[str, str]:
    normalized = {_normalize_header(header): header for header in headers}
    result: dict[str, str] = {}
    for field, aliases in OPTIONAL_ALIASES.items():
        matches = [normalized[alias] for alias in aliases if alias in normalized]
        if len(matches) == 1:
            result[field] = matches[0]
        elif len(matches) > 1:
            raise ValueError(f"El campo opcional '{field}' es ambiguo.")
    return result


def _stable_detection_id(source: str, raw_sha256: str, row_number: int) -> str:
    token = f"{source}\0{raw_sha256}\0{row_number}".encode("utf-8")
    return f"firms-{hashlib.sha256(token).hexdigest()}"


def _clean_value(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _to_detection(
    row: Mapping[str, Any],
    mapping: Mapping[str, str],
    optional: Mapping[str, str],
    source: str,
    raw_path: Path,
    raw_sha256: str,
    row_number: int,
    headers: Sequence[str],
) -> dict[str, Any]:
    raw_date = row.get(mapping["acq_date"])
    raw_time = row.get(mapping["acq_time"])
    parsed_date = parse_acquisition_date(raw_date)
    parsed_time = _parse_acquisition_time(raw_time)
    parsed_datetime = parse_acquisition_datetime(raw_date, raw_time)
    raw_latitude = row.get(mapping["latitude"])
    raw_longitude = row.get(mapping["longitude"])
    coordinate_valid = validate_coordinates(raw_latitude, raw_longitude)
    confidence_normalized, confidence_numeric = _normalize_confidence(row.get(mapping["confidence"]))
    daynight = _normalize_text(row.get(optional["daynight"]), uppercase=True) if "daynight" in optional else ""
    version = _clean_value(row.get(optional["version"])) if "version" in optional else ""
    fire_type = _clean_value(row.get(optional["type"])) if "type" in optional else ""
    raw_values = tuple(row.get(header, "") for header in headers)
    return {
        "detection_id": _stable_detection_id(source, raw_sha256, row_number),
        "latitude": _format_number(_parse_number(raw_latitude)) if coordinate_valid else "",
        "longitude": _format_number(_parse_number(raw_longitude)) if coordinate_valid else "",
        "acq_date": parsed_date.isoformat() if parsed_date else "",
        "acq_time": parsed_time.strftime("%H:%M:%S") if parsed_time else "",
        "acq_datetime_utc": parsed_datetime.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed_datetime else "",
        "satellite": _normalize_text(row.get(mapping["satellite"]), uppercase=True),
        "instrument": _normalize_text(row.get(mapping["instrument"]), uppercase=True),
        "firms_source": source,
        "confidence_raw": _clean_value(row.get(mapping["confidence"])),
        "confidence_normalized": confidence_normalized,
        "confidence_numeric": confidence_numeric,
        "frp": _format_number(_parse_number(row.get(mapping["frp"]))),
        "daynight": daynight,
        "version": version,
        "type": fire_type,
        "raw_file": raw_path.name,
        "raw_sha256": raw_sha256,
        "source_row_number": str(row_number),
        "schema_version": FIRMS_SCHEMA_VERSION,
        "_date": parsed_date,
        "_datetime": parsed_datetime,
        "_coordinate_valid": coordinate_valid,
        "_date_missing": is_missing(raw_date),
        "_time_invalid": not is_missing(raw_time) and parsed_time is None,
        "_raw_values": raw_values,
    }


def scan_raw_artifact(artifact: RawArtifact) -> SourceScan:
    """Read one raw artifact and reject its schema independently."""

    content = artifact.raw_path.read_bytes()
    raw_sha256 = sha256_bytes(content)
    headers, rows, read_error = _read_csv_rows(artifact.raw_path)
    normalized_headers = tuple(_normalize_header(header) for header in headers)
    manifest_sha256 = artifact.manifest.get("sha256")
    if manifest_sha256 and manifest_sha256 != raw_sha256:
        return SourceScan(
            artifact.source,
            artifact.raw_path,
            raw_sha256,
            len(rows),
            tuple(headers),
            normalized_headers,
            rows,
            False,
            "El SHA-256 del raw no coincide con su manifest.",
            [],
        )
    if read_error:
        return SourceScan(
            artifact.source,
            artifact.raw_path,
            raw_sha256,
            len(rows),
            tuple(headers),
            normalized_headers,
            rows,
            False,
            read_error,
            [],
        )
    try:
        mapping = validate_required_columns(headers)
        optional = _optional_mapping(headers)
    except (ValueError, KeyError) as exc:
        return SourceScan(
            artifact.source,
            artifact.raw_path,
            raw_sha256,
            len(rows),
            tuple(headers),
            normalized_headers,
            rows,
            False,
            str(exc),
            [],
        )

    detections = [
        _to_detection(row, mapping, optional, artifact.source, artifact.raw_path, raw_sha256, index, headers)
        for index, row in enumerate(rows, start=1)
    ]
    return SourceScan(
        artifact.source,
        artifact.raw_path,
        raw_sha256,
        len(rows),
        tuple(headers),
        normalized_headers,
        rows,
        True,
        None,
        detections,
    )


def _duplicate_summary(scans: Iterable[SourceScan]) -> dict[str, int]:
    within_source_groups = 0
    within_source_rows = 0
    all_rows: Counter[tuple[str, ...]] = Counter()
    source_sets: dict[tuple[str, ...], set[str]] = {}
    for scan in scans:
        counts = Counter(tuple(row.get(header, "") for header in scan.headers) for row in scan.raw_rows)
        within_source_groups += sum(count > 1 for count in counts.values())
        within_source_rows += sum(count - 1 for count in counts.values() if count > 1)
        for raw_values in counts:
            all_rows[raw_values] += counts[raw_values]
            source_sets.setdefault(raw_values, set()).add(scan.source)
    across_source_groups = sum(
        len(sources) > 1 and all_rows[raw_values] > 1 for raw_values, sources in source_sets.items()
    )
    return {
        "within_source_groups": within_source_groups,
        "within_source_rows_after_first_occurrence": within_source_rows,
        "across_source_exact_groups": across_source_groups,
    }


def filter_to_cocle(
    scans: Sequence[SourceScan],
    boundary: Boundary,
    start_date: date = MAIN_START,
    end_date: date = MAIN_END,
) -> FilterResult:
    if (start_date, end_date) != (MAIN_START, MAIN_END):
        raise ValueError("Esta fase solo permite la temporada principal 2025-01-01..2025-04-30.")

    all_detections = [detection for scan in scans if scan.schema_valid for detection in scan.detections]
    final_detections: list[dict[str, Any]] = []
    invalid_dates = 0
    invalid_times = 0
    invalid_coordinates = 0
    valid_date_coordinate = 0
    outside_period = 0
    outside_cocle = 0
    for detection in all_detections:
        if detection["_time_invalid"]:
            invalid_times += 1
        if detection["_date"] is None:
            invalid_dates += 1
            continue
        if not detection["_coordinate_valid"]:
            invalid_coordinates += 1
            continue
        valid_date_coordinate += 1
        if detection["_date"] < start_date or detection["_date"] > end_date:
            outside_period += 1
            continue
        if not boundary.contains(float(detection["longitude"]), float(detection["latitude"])):
            outside_cocle += 1
            continue
        final_detections.append(detection)

    schema_invalid_rows = sum(scan.raw_record_count for scan in scans if not scan.schema_valid)
    counts = {
        "total_raw_records": sum(scan.raw_record_count for scan in scans),
        "schema_valid_records": sum(scan.raw_record_count for scan in scans if scan.schema_valid),
        "total_discarded_schema_invalid": schema_invalid_rows,
        "total_invalid_dates": invalid_dates,
        "total_invalid_times": invalid_times,
        "total_invalid_coordinates": invalid_coordinates,
        "total_valid_date_coordinate_detections": valid_date_coordinate,
        "total_discarded_outside_period": outside_period,
        "total_discarded_outside_cocle": outside_cocle,
        "total_final_detections": len(final_detections),
    }
    return FilterResult(
        list(scans),
        all_detections,
        final_detections,
        counts,
        _duplicate_summary(scans),
    )


def public_detection(detection: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(detection.get(field, "") or "") for field in DETECTION_FIELDS}


def write_detections(path: Path, detections: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETECTION_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(public_detection(detection) for detection in detections)
