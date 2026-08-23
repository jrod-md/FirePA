"""Exploratory FIRMS profile before event clustering."""

from __future__ import annotations

import json
import hashlib
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .cocle import DETECTION_FIELDS, FilterResult, SourceScan
from .firms import is_missing


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _counter(values: Iterable[Any]) -> dict[str, int]:
    counts = Counter(str(value).strip() if value not in (None, "") else "__missing__" for value in values)
    return dict(sorted(counts.items()))


def _quantile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _numeric_distribution(values: Iterable[Any]) -> dict[str, Any]:
    numbers: list[float] = []
    missing = 0
    for value in values:
        try:
            parsed = float(value)
            if math.isfinite(parsed):
                numbers.append(parsed)
            else:
                missing += 1
        except (TypeError, ValueError):
            missing += 1
    return {
        "count": len(numbers),
        "missing": missing,
        "min": min(numbers) if numbers else None,
        "max": max(numbers) if numbers else None,
        "p25": _quantile(numbers, 0.25),
        "p50": _quantile(numbers, 0.50),
        "p75": _quantile(numbers, 0.75),
        "p90": _quantile(numbers, 0.90),
    }


def _haversine_km(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    radius = 6371.0088
    lat1, lon1 = math.radians(float(first["latitude"])), math.radians(float(first["longitude"]))
    lat2, lon2 = math.radians(float(second["latitude"])), math.radians(float(second["longitude"]))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(min(1.0, value)))


def _possible_cross_sensor_matches(
    detections: Sequence[Mapping[str, Any]],
    distance_km: float,
    time_minutes: int,
) -> dict[str, Any]:
    if distance_km <= 0 or time_minutes <= 0:
        raise ValueError("Los umbrales diagnósticos de coincidencias deben ser positivos.")
    usable = [
        detection
        for detection in detections
        if detection.get("_datetime") is not None
        and detection.get("_coordinate_valid")
        and detection.get("firms_source")
    ]
    usable.sort(key=lambda detection: detection["_datetime"])
    latitude_cell = distance_km / 111.32
    longitude_cell = max(distance_km / 111.32, 1e-6)
    buckets: defaultdict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    pair_ids: set[tuple[str, str]] = set()
    examples: list[dict[str, Any]] = []
    for current in usable:
        lat = float(current["latitude"])
        lon = float(current["longitude"])
        cell = (math.floor(lat / latitude_cell), math.floor(lon / longitude_cell))
        for lat_index in range(cell[0] - 1, cell[0] + 2):
            for lon_index in range(cell[1] - 1, cell[1] + 2):
                for previous in buckets.get((lat_index, lon_index), []):
                    if previous["firms_source"] == current["firms_source"]:
                        continue
                    delta_minutes = abs(
                        (current["_datetime"] - previous["_datetime"]).total_seconds()
                    ) / 60
                    if delta_minutes > time_minutes:
                        continue
                    distance = _haversine_km(previous, current)
                    if distance > distance_km:
                        continue
                    pair = tuple(sorted((previous["detection_id"], current["detection_id"])))
                    if pair in pair_ids:
                        continue
                    pair_ids.add(pair)
                    if len(examples) < 100:
                        examples.append(
                            {
                                "detection_id_a": pair[0],
                                "detection_id_b": pair[1],
                                "distance_km": round(distance, 6),
                                "time_difference_minutes": round(delta_minutes, 3),
                            }
                        )
        buckets[cell].append(current)
    return {
        "pair_count": len(pair_ids),
        "example_pairs_limit": 100,
        "examples": examples,
        "rule": {
            "distance_km": distance_km,
            "time_minutes": time_minutes,
            "purpose": "diagnóstico de coincidencias entre sensores; no forma eventos ni fija clustering",
        },
    }


def _date_range(start: date, end: date) -> set[date]:
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


def _manifest_coverage(
    manifests: Sequence[Mapping[str, Any]], source: str
) -> tuple[set[date], set[date], set[date], int]:
    imported_or_queried_days: set[date] = set()
    downloaded_days: set[date] = set()
    failed_days: set[date] = set()
    manifest_count = 0
    for manifest in manifests:
        if manifest.get("source") != source:
            continue
        status = manifest.get("status")
        if status not in {"downloaded", "imported", "error"}:
            continue
        try:
            start = date.fromisoformat(str(manifest["start_date"]))
            end = date.fromisoformat(str(manifest["end_date"]))
        except (KeyError, TypeError, ValueError):
            continue
        manifest_count += 1
        fragment_days = _date_range(start, end)
        if status == "downloaded":
            imported_or_queried_days.update(fragment_days)
            downloaded_days.update(fragment_days)
        elif status == "imported":
            imported_or_queried_days.update(fragment_days)
        else:
            failed_days.update(fragment_days)
    return imported_or_queried_days, downloaded_days, failed_days, manifest_count


def _raw_missing_values(scans: Sequence[SourceScan]) -> dict[str, Any]:
    by_source: dict[str, dict[str, int]] = {}
    totals: Counter[str] = Counter()
    for scan in scans:
        counts: dict[str, int] = {}
        for header in scan.headers:
            missing = sum(is_missing(row.get(header)) for row in scan.raw_rows)
            counts[header] = missing
            totals[header] += missing
        by_source.setdefault(scan.source, {})
        for header, count in counts.items():
            by_source[scan.source][header] = by_source[scan.source].get(header, 0) + count
    return {"by_source": by_source, "total": dict(sorted(totals.items()))}


def _coverage_profile(
    result: FilterResult,
    manifests: Sequence[Mapping[str, Any]],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    requested_days = _date_range(start_date, end_date)
    output: dict[str, Any] = {}
    sources = sorted(
        {scan.source for scan in result.scans}
        | {str(manifest.get("source")) for manifest in manifests if manifest.get("source")}
    )
    for source in sources:
        source_scans = [scan for scan in result.scans if scan.source == source]
        bbox_days = {
            detection["_date"]
            for scan in source_scans
            for detection in scan.detections
            if detection["_date"] is not None and start_date <= detection["_date"] <= end_date
        }
        final_days = {
            detection["_date"]
            for detection in result.final_detections
            if detection["firms_source"] == source and detection["_date"] is not None
        }
        imported_or_queried_days, downloaded_days, failed_days, manifest_count = _manifest_coverage(
            manifests, source
        )
        coverage_known = bool(downloaded_days)
        output[source] = {
            "days_with_rows_in_query_bbox": sorted(day.isoformat() for day in bbox_days),
            "days_with_final_cocle_detections": sorted(day.isoformat() for day in final_days),
            "queried_days_without_rows_in_bbox": (
                sorted(day.isoformat() for day in downloaded_days - bbox_days) if coverage_known else None
            ),
            "queried_days_without_cocle_detections": (
                sorted(day.isoformat() for day in downloaded_days - final_days) if coverage_known else None
            ),
            "days_not_queried_or_unavailable": (
                sorted(day.isoformat() for day in requested_days - downloaded_days) if coverage_known else None
            ),
            "days_with_failed_fragments": sorted(day.isoformat() for day in failed_days),
            "manifest_fragment_count": manifest_count,
            "imported_or_queried_days": sorted(day.isoformat() for day in imported_or_queried_days),
            "coverage_known_from_manifests": coverage_known,
            "interpretation_note": (
                "Un día sin filas no equivale a ausencia de incendio; distingue ausencia de filas, "
                "ausencia de detección dentro de Coclé y días no consultados."
            ),
        }
    return output


def _schema_profile(scans: Sequence[SourceScan]) -> dict[str, Any]:
    output: dict[str, list[dict[str, Any]]] = {}
    signatures: set[str] = set()
    for scan in scans:
        signature = hashlib.sha256("\0".join(scan.normalized_headers).encode()).hexdigest()
        signatures.add(signature)
        output.setdefault(scan.source, []).append(
            {
                "raw_file": scan.raw_path.name,
                "schema_valid": scan.schema_valid,
                "schema_error": scan.schema_error,
                "headers": list(scan.headers),
                "schema_fingerprint": signature,
            }
        )
    return {
        "by_source": output,
        "distinct_raw_schema_fingerprints": len(signatures),
        "note": "Cada fuente se valida por separado; las variantes de columnas no se ocultan ni se fuerzan a equivalencia científica.",
    }


def build_profile(
    result: FilterResult,
    manifests: Sequence[Mapping[str, Any]],
    start_date: date,
    end_date: date,
    distance_km: float = 1.0,
    time_minutes: int = 30,
) -> dict[str, Any]:
    final = result.final_detections
    by_source_accumulator: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {
            "raw_records": 0,
            "schema_valid_records": 0,
            "valid_date_coordinate_records": 0,
            "final_cocle_records": 0,
            "schema_invalid_records": 0,
            "raw_fragments": 0,
        }
    )
    for scan in result.scans:
        source_valid = [detection for detection in scan.detections if detection["_date"] is not None and detection["_coordinate_valid"]]
        source_final = [
            detection
            for detection in final
            if detection["firms_source"] == scan.source
            and detection["raw_file"] == scan.raw_path.name
        ]
        accumulated = by_source_accumulator[scan.source]
        accumulated["raw_records"] += scan.raw_record_count
        accumulated["schema_valid_records"] += len(scan.detections) if scan.schema_valid else 0
        accumulated["valid_date_coordinate_records"] += len(source_valid)
        accumulated["final_cocle_records"] += len(source_final)
        accumulated["schema_invalid_records"] += scan.raw_record_count if not scan.schema_valid else 0
        accumulated["raw_fragments"] += 1
    by_source = dict(sorted(by_source_accumulator.items()))

    dates = [detection["_date"] for detection in final if detection["_date"] is not None]
    daynight_counts = _counter(detection.get("daynight") for detection in final)
    known_daynight = sum(count for key, count in daynight_counts.items() if key in {"D", "N"})
    daynight_percentages = {
        key: (count / known_daynight * 100 if known_daynight else None)
        for key, count in daynight_counts.items()
        if key in {"D", "N"}
    }
    missing_final = {
        field: sum(not detection.get(field) for detection in final) for field in DETECTION_FIELDS
    }
    daily_counts = Counter(detection["_date"].isoformat() for detection in final if detection["_date"] is not None)
    weekly_counts = Counter(
        f"{detection['_date'].isocalendar().year}-W{detection['_date'].isocalendar().week:02d}"
        for detection in final
        if detection["_date"] is not None
    )
    bbox = None
    if final:
        bbox = {
            "west": min(float(detection["longitude"]) for detection in final),
            "south": min(float(detection["latitude"]) for detection in final),
            "east": max(float(detection["longitude"]) for detection in final),
            "north": max(float(detection["latitude"]) for detection in final),
        }

    raw_dates = [
        detection["_date"]
        for detection in result.all_detections
        if detection["_date"] is not None
    ]

    profile = {
        "profile_version": "firms-cocle-profile-v1",
        "generated_at_utc": _utc_now_text(),
        "area": "cocle",
        "requested_period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "counts": {
            **result.counts,
            "total_discarded_by_date": result.counts["total_invalid_dates"]
            + result.counts["total_discarded_outside_period"],
        },
        "attrition_flow": [
            {"stage": "raw_records", "count": result.counts["total_raw_records"]},
            {"stage": "schema_valid_records", "count": result.counts["schema_valid_records"]},
            {
                "stage": "valid_date_coordinate_records",
                "count": result.counts["total_valid_date_coordinate_detections"],
            },
            {
                "stage": "inside_requested_period",
                "count": result.counts["total_valid_date_coordinate_detections"]
                - result.counts["total_discarded_outside_period"],
            },
            {
                "stage": "inside_cocle",
                "count": result.counts["total_final_detections"],
            },
        ],
        "by_source": by_source,
        "by_satellite_raw": _counter(detection.get("satellite") for detection in result.all_detections),
        "by_instrument_raw": _counter(detection.get("instrument") for detection in result.all_detections),
        "by_satellite_final": _counter(detection.get("satellite") for detection in final),
        "by_instrument_final": _counter(detection.get("instrument") for detection in final),
        "temporal_range_raw": {
            "min_acq_date": min(raw_dates).isoformat() if raw_dates else None,
            "max_acq_date": max(raw_dates).isoformat() if raw_dates else None,
        },
        "temporal_range_final": {
            "min_acq_date": min(dates).isoformat() if dates else None,
            "max_acq_date": max(dates).isoformat() if dates else None,
        },
        "daily_counts_final": dict(sorted(daily_counts.items())),
        "weekly_counts_final": dict(sorted(weekly_counts.items())),
        "frp_distribution_final": _numeric_distribution(detection.get("frp") for detection in final),
        "confidence_distribution_final": {
            "raw": _counter(detection.get("confidence_raw") for detection in final),
            "normalized": _counter(detection.get("confidence_normalized") for detection in final),
        },
        "missing_values_raw": _raw_missing_values(result.scans),
        "missing_values_final": missing_final,
        "invalid_coordinates": {"rows": result.counts["total_invalid_coordinates"]},
        "exact_duplicates": result.duplicate_summary,
        "possible_cross_sensor_matches": _possible_cross_sensor_matches(final, distance_km, time_minutes),
        "daynight_final": {"counts": daynight_counts, "known_daynight_percentages": daynight_percentages},
        "bounding_box_final": bbox,
        "days_without_observations": _coverage_profile(result, manifests, start_date, end_date),
        "schema_by_source": _schema_profile(result.scans),
        "traceability": {
            "processed_rows_keep_raw_file_and_sha256": True,
            "duplicate_rows_removed": 0,
            "sentinel2_used_for_cohort_filter": False,
            "clustering_used": False,
        },
        "limitations": [
            "El perfil es previo al clustering: las detecciones no son eventos ni incendios independientes.",
            "Las coincidencias entre sensores son un diagnóstico con umbrales explícitos; no forman clusters.",
            "Los días sin filas no demuestran ausencia de incendios ni ausencia de datos del sensor.",
            "No se usaron datos de 2026 para definir la cohorte 2025.",
        ],
    }
    return profile


def write_profile(profile: Mapping[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = profile.get("counts", {})
    lines = [
        "# Perfil FIRMS — Coclé 2025",
        "",
        "Perfil exploratorio generado antes del clustering espacio-temporal.",
        "",
        "## Conteos de atrición",
        "",
        f"- Registros raw: {counts.get('total_raw_records', 0)}",
        f"- Registros con esquema válido: {counts.get('schema_valid_records', 0)}",
        f"- Descartados por esquema inválido: {counts.get('total_discarded_schema_invalid', 0)}",
        f"- Detecciones válidas (fecha + coordenadas): {counts.get('total_valid_date_coordinate_detections', 0)}",
        f"- Descartados por fecha fuera del período: {counts.get('total_discarded_outside_period', 0)}",
        f"- Descartados por estar fuera de Coclé: {counts.get('total_discarded_outside_cocle', 0)}",
        f"- Detecciones finales dentro de Coclé: {counts.get('total_final_detections', 0)}",
        "",
        "## Trazabilidad y límites",
        "",
        "- Cada fila final conserva `raw_file`, `raw_sha256`, `source_row_number` y `detection_id`.",
        "- No se eliminaron duplicados y no se usó Sentinel-2 para formar la cohorte.",
        "- Un día sin filas no equivale automáticamente a un día sin incendios.",
        "- Este perfil no representa clusters ni ground truth.",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
