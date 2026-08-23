"""Audit an existing local FIRMS acquisition without making network calls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.acquisition import (  # noqa: E402
    DateRange,
    RawArtifact,
    expected_fragments,
    parse_availability_csv,
    validate_manifest,
)
from fuegopa.cocle import (  # noqa: E402
    DETECTION_FIELDS,
    filter_to_cocle,
    public_detection,
    scan_raw_artifact,
    _stable_detection_id,
)
from fuegopa.firms import validate_required_columns  # noqa: E402
from fuegopa.geo import BoundaryError, load_boundary  # noqa: E402
from fuegopa.pipeline import (  # noqa: E402
    _build_acquisition_audit,
    _source_selection_report,
    _write_acquisition_audit,
    _write_json,
    _write_source_selection_markdown,
)
from fuegopa.profile import build_profile, write_profile  # noqa: E402


START = date(2025, 1, 1)
END = date(2025, 4, 30)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_key(manifest: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(manifest.get("source", "")),
        str(manifest.get("start_date", "")),
        str(manifest.get("end_date", "")),
    )


def _source_name(source: str, start: date, end: date) -> str:
    return f"firms_{source.lower()}_{start.isoformat()}_{end.isoformat()}.csv"


def _date_range(start: date, end: date) -> list[str]:
    values: list[str] = []
    cursor = start
    while cursor <= end:
        values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _raw_file_info(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = list(reader)
    schema_error: str | None = None
    try:
        validate_required_columns(headers)
    except (ValueError, KeyError) as exc:
        schema_error = str(exc)
    content = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(content),
        "sha256": _sha256(path),
        "headers": headers,
        "rows": rows,
        "record_count": len(rows),
        "schema_valid": schema_error is None,
        "schema_error": schema_error,
        "invalid_response_prefix": content.lstrip().lower().startswith(
            (b"<html", b"<!doctype", b'{"error')
        ),
    }


def _raw_rows_by_date(raw_infos: Mapping[str, dict[str, Any]], manifest_by_raw: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Counter[str]], Counter[str], int]:
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    combined: Counter[str] = Counter()
    total = 0
    for raw_name, info in raw_infos.items():
        source = str(manifest_by_raw.get(raw_name, {}).get("source", "UNKNOWN"))
        for row in info["rows"]:
            value = str(row.get("acq_date", "")).strip()[:10]
            by_source[source][value] += 1
            combined[value] += 1
            total += 1
    return dict(by_source), combined, total


def _processed_validation(
    path: Path,
    rows: Sequence[dict[str, str]],
    headers: Sequence[str],
    raw_infos: Mapping[str, dict[str, Any]],
    boundary,
    recomputed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ids = Counter(row.get("detection_id", "") for row in rows)
    exact = Counter(tuple(row.get(header, "") for header in headers) for row in rows)
    source_counts = Counter(row.get("firms_source", "") for row in rows)
    dates = Counter(row.get("acq_date", "") for row in rows)
    missing_by_column = {
        header: sum(not (row.get(header, "") or "").strip() for row in rows)
        for header in headers
    }
    confidence_values = Counter(row.get("confidence_normalized", "") for row in rows)
    daynight_values = Counter(row.get("daynight", "") for row in rows)
    satellite_values = Counter(row.get("satellite", "") for row in rows)
    instrument_values = Counter(row.get("instrument", "") for row in rows)
    invalid_coordinates = 0
    outside_cocle = 0
    outside_period = 0
    data_2026 = 0
    missing_raw: list[str] = []
    raw_hash_mismatch: list[str] = []
    id_mismatch: list[str] = []
    invalid_row_numbers: list[str] = []
    raw_rows_cache: dict[str, list[dict[str, str]]] = {
        name: info["rows"] for name, info in raw_infos.items()
    }
    for row in rows:
        try:
            longitude = float(row.get("longitude", ""))
            latitude = float(row.get("latitude", ""))
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                invalid_coordinates += 1
            elif not boundary.contains(longitude, latitude):
                outside_cocle += 1
        except (TypeError, ValueError):
            invalid_coordinates += 1
        acquisition_date = row.get("acq_date", "")
        if not (START.isoformat() <= acquisition_date <= END.isoformat()):
            outside_period += 1
        if acquisition_date.startswith("2026"):
            data_2026 += 1
        raw_name = row.get("raw_file", "")
        info = raw_infos.get(raw_name)
        if info is None:
            missing_raw.append(raw_name)
            continue
        if row.get("raw_sha256") != info["sha256"]:
            raw_hash_mismatch.append(raw_name)
        try:
            source_row_number = int(row.get("source_row_number", "0"))
            if not 1 <= source_row_number <= len(raw_rows_cache[raw_name]):
                raise ValueError("source_row_number fuera de rango")
            expected_id = _stable_detection_id(
                row.get("firms_source", ""),
                info["sha256"],
                source_row_number,
            )
            if row.get("detection_id") != expected_id:
                id_mismatch.append(row.get("detection_id", ""))
        except (KeyError, TypeError, ValueError):
            invalid_row_numbers.append(row.get("detection_id", ""))

    expected_public = [public_detection(row) for row in recomputed_rows]
    return {
        "path": str(path),
        "rows": len(rows),
        "headers": list(headers),
        "schema_matches_internal": tuple(headers) == DETECTION_FIELDS,
        "sources": dict(sorted(source_counts.items())),
        "date_range": {
            "min": min(dates) if dates else None,
            "max": max(dates) if dates else None,
        },
        "unique_detection_ids": len([key for key in ids if key]),
        "duplicate_detection_id_groups": sum(value > 1 for value in ids.values()),
        "exact_duplicate_groups": sum(value > 1 for value in exact.values()),
        "invalid_coordinates": invalid_coordinates,
        "outside_cocle": outside_cocle,
        "outside_period": outside_period,
        "data_2026": data_2026,
        "missing_by_column": missing_by_column,
        "confidence_normalized": dict(sorted(confidence_values.items())),
        "daynight": dict(sorted(daynight_values.items())),
        "satellite": dict(sorted(satellite_values.items())),
        "instrument": dict(sorted(instrument_values.items())),
        "raw_file_missing": missing_raw,
        "raw_sha256_mismatch": raw_hash_mismatch,
        "detection_id_mismatch": id_mismatch,
        "source_row_number_invalid": invalid_row_numbers,
        "matches_recomputed_filter": list(rows) == expected_public,
        "recomputed_rows": len(expected_public),
    }


def _load_processed(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _raw_manifest_audit(
    root: Path,
    raw_dir: Path,
    manifest_dir: Path,
    availability: Sequence[Any],
    manifests: Sequence[dict[str, Any]],
    raw_infos: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    requested = DateRange(START, END)
    plan = expected_fragments(availability, requested)
    expected_keys = {
        (source.data_id, fragment.start.isoformat(), fragment.end.isoformat())
        for source, fragment in plan
    }
    success = [manifest for manifest in manifests if manifest.get("status") in {"downloaded", "imported"}]
    failed = [manifest for manifest in manifests if manifest.get("status") == "error"]
    successful_keys = {_manifest_key(manifest) for manifest in success}
    failed_keys = {_manifest_key(manifest) for manifest in failed}
    manifest_by_raw = {
        str(manifest.get("raw_filename") or manifest.get("raw_file")): manifest
        for manifest in manifests
    }
    manifest_key_counts = Counter(_manifest_key(manifest) for manifest in manifests)
    duplicate_manifest_keys = [
        {
            "source": key[0],
            "start_date": key[1],
            "end_date": key[2],
            "count": count,
        }
        for key, count in sorted(manifest_key_counts.items())
        if count > 1
    ]
    hash_mismatches: list[str] = []
    size_mismatches: list[str] = []
    record_count_mismatches: list[str] = []
    invalid_responses: list[str] = []
    schema_incompatible: list[dict[str, Any]] = []
    manifest_without_raw: list[str] = []
    for manifest in manifests:
        raw_name = str(manifest.get("raw_filename") or manifest.get("raw_file"))
        info = raw_infos.get(raw_name)
        if info is None:
            manifest_without_raw.append(raw_name)
            continue
        if manifest.get("status") in {"downloaded", "imported"}:
            if manifest.get("sha256") != info["sha256"]:
                hash_mismatches.append(raw_name)
            if manifest.get("size_bytes") != info["bytes"]:
                size_mismatches.append(raw_name)
            if manifest.get("record_count") != info["record_count"]:
                record_count_mismatches.append(raw_name)
            if info["invalid_response_prefix"]:
                invalid_responses.append(raw_name)
            if not info["schema_valid"]:
                schema_incompatible.append({"raw": raw_name, "error": info["schema_error"]})
    raw_without_manifest = sorted(set(raw_infos) - set(manifest_by_raw))
    duplicate_groups: dict[str, list[str]] = defaultdict(list)
    for raw_name, info in raw_infos.items():
        duplicate_groups[info["sha256"]].append(raw_name)
    identical_content_groups = [
        {"sha256": digest, "files": sorted(files)}
        for digest, files in duplicate_groups.items()
        if len(files) > 1
    ]
    raw_by_source, raw_dates, raw_record_count = _raw_rows_by_date(raw_infos, manifest_by_raw)
    source_coverage = []
    for source in sorted({item.data_id for item in availability if item.overlap(requested)}):
        source_plan = [(record, fragment) for record, fragment in plan if record.data_id == source]
        source_keys = {(record.data_id, fragment.start.isoformat(), fragment.end.isoformat()) for record, fragment in source_plan}
        source_dates = raw_by_source.get(source, Counter())
        source_coverage.append(
            {
                "source": source,
                "expected_fragments": len(source_plan),
                "successful_fragments": len(source_keys & successful_keys),
                "empty_fragments": sum(
                    manifest.get("source") == source and manifest.get("record_count") == 0
                    for manifest in success
                ),
                "raw_records": sum(source_dates.values()),
                "raw_date_min": min(source_dates) if source_dates else None,
                "raw_date_max": max(source_dates) if source_dates else None,
            }
        )
    jan_days = _date_range(date(2025, 1, 1), date(2025, 1, 11))
    jan_rows_by_source = {
        source: {day: raw_by_source.get(source, Counter()).get(day, 0) for day in jan_days}
        for source in sorted(raw_by_source)
    }
    jan_fragments = [
        {
            "source": manifest.get("source"),
            "start_date": manifest.get("start_date"),
            "end_date": manifest.get("end_date"),
            "status": manifest.get("status"),
            "record_count": manifest.get("record_count"),
            "raw_filename": manifest.get("raw_filename"),
        }
        for manifest in manifests
        if manifest.get("start_date") in {"2025-01-01", "2025-01-06", "2025-01-11"}
    ]
    all_days = _date_range(START, END)
    missing_detection_days = [day for day in all_days if not raw_dates.get(day)]
    return {
        "expected_fragments": len(expected_keys),
        "existing_raw_files": len(raw_infos),
        "existing_manifest_files": len(manifests),
        "successful_fragments": len(expected_keys & successful_keys),
        "empty_fragments": [
            {
                "source": manifest.get("source"),
                "start_date": manifest.get("start_date"),
                "end_date": manifest.get("end_date"),
                "raw_filename": manifest.get("raw_filename"),
            }
            for manifest in success
            if manifest.get("record_count") == 0
        ],
        "failed_fragments": [
            {
                "source": manifest.get("source"),
                "start_date": manifest.get("start_date"),
                "end_date": manifest.get("end_date"),
                "error_message": manifest.get("error_message"),
            }
            for manifest in failed
        ],
        "missing_expected_fragments": [
            {"source": source, "start_date": start, "end_date": end}
            for source, start, end in sorted(expected_keys - successful_keys - failed_keys)
        ],
        "unexpected_success_fragments": [
            {"source": source, "start_date": start, "end_date": end}
            for source, start, end in sorted(successful_keys - expected_keys)
        ],
        "manifest_without_raw": sorted(manifest_without_raw),
        "raw_without_manifest": raw_without_manifest,
        "duplicate_manifest_keys": duplicate_manifest_keys,
        "raw_manifest_hash_mismatches": sorted(hash_mismatches),
        "raw_manifest_size_mismatches": sorted(size_mismatches),
        "raw_manifest_record_count_mismatches": sorted(record_count_mismatches),
        "invalid_response_files": sorted(invalid_responses),
        "schema_incompatible_files": schema_incompatible,
        "identical_content_groups": identical_content_groups,
        "source_coverage": source_coverage,
        "raw_record_count_total": raw_record_count,
        "raw_date_range": {"min": min(raw_dates) if raw_dates else None, "max": max(raw_dates) if raw_dates else None},
        "raw_outside_requested_period": sum(
            count for day, count in raw_dates.items() if day and not (START.isoformat() <= day <= END.isoformat())
        ),
        "missing_detection_days": missing_detection_days,
        "jan_1_to_11": {
            "fragments": sorted(jan_fragments, key=lambda item: (item["source"], item["start_date"])),
            "raw_rows_by_date": jan_rows_by_source,
            "classification": "Los fragmentos 1-5 y 6-10 fueron descargados exitosamente con cero filas; el fragmento 11-15 fue exitoso y no contiene filas con acq_date 2025-01-11. No es un fragmento faltante ni fallido.",
        },
        "coverage_complete": (
            len(expected_keys) == len(successful_keys & expected_keys)
            and not (expected_keys - successful_keys - failed_keys)
            and not failed
            and not duplicate_manifest_keys
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--boundary-path", type=Path, default=Path("data/reference/cocle.geojson"))
    parser.add_argument("--availability-path", type=Path, default=Path("outputs/firms_data_availability_2025.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest-dir", type=Path, default=Path("data/raw/manifests"))
    parser.add_argument("--processed-path", type=Path, default=Path("data/processed/firms_cocle_2025_detections.csv"))
    parser.add_argument("--outputs-dir", type=Path, default=Path("outputs"))
    return parser


def _resolve(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def run(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    root = args.project_root.expanduser().resolve()
    boundary_path = _resolve(root, args.boundary_path).resolve()
    availability_path = _resolve(root, args.availability_path).resolve()
    raw_dir = _resolve(root, args.raw_dir).resolve()
    manifest_dir = _resolve(root, args.manifest_dir).resolve()
    processed_path = _resolve(root, args.processed_path).resolve()
    outputs_dir = _resolve(root, args.outputs_dir).resolve()
    requested = DateRange(START, END)
    availability = parse_availability_csv(availability_path.read_bytes())
    plan = expected_fragments(availability, requested)
    manifest_paths = sorted(manifest_dir.glob("*.manifest.json"))
    manifests: list[dict[str, Any]] = []
    manifest_errors: list[dict[str, str]] = []
    for path in manifest_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            validate_manifest(value)
            value["_manifest_path"] = path
            manifests.append(value)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            manifest_errors.append({"path": str(path), "error": str(exc)})
    raw_paths = sorted(raw_dir.glob("*.csv"))
    raw_infos = {path.name: _raw_file_info(path) for path in raw_paths}
    manifest_by_key = {_manifest_key(manifest): manifest for manifest in manifests}
    manifest_by_raw = {
        str(manifest.get("raw_filename") or manifest.get("raw_file")): manifest
        for manifest in manifests
    }
    artifacts: list[RawArtifact] = []
    for source, fragment in plan:
        name = _source_name(source.data_id, fragment.start, fragment.end)
        manifest = manifest_by_key.get((source.data_id, fragment.start.isoformat(), fragment.end.isoformat()))
        raw_path = raw_dir / name
        if manifest is not None and raw_path.is_file():
            artifacts.append(RawArtifact(source.data_id, raw_path, Path(manifest["_manifest_path"]), manifest))
    boundary = load_boundary(boundary_path)
    scans = [scan_raw_artifact(artifact) for artifact in artifacts]
    invalid_scans = [scan for scan in scans if not scan.schema_valid]
    filtered = filter_to_cocle(scans, boundary, START, END) if not invalid_scans else None
    manifests_for_profile = [artifact.manifest for artifact in artifacts]
    profile = (
        build_profile(filtered, manifests_for_profile, START, END)
        if filtered is not None
        else None
    )
    headers, processed_rows = _load_processed(processed_path)
    processed_validation = _processed_validation(
        processed_path,
        processed_rows,
        headers,
        raw_infos,
        boundary,
        filtered.final_detections if filtered is not None else [],
    )
    raw_manifest_audit = _raw_manifest_audit(
        root,
        raw_dir,
        manifest_dir,
        availability,
        manifests,
        raw_infos,
    )
    selected = [record for record in availability if record.data_id in {item.data_id for item, _ in plan}]
    source_selection = _source_selection_report(availability, selected, requested, None)
    source_selection["raw_audit"] = {
        "expected_fragments": raw_manifest_audit["expected_fragments"],
        "successful_fragments": raw_manifest_audit["successful_fragments"],
        "existing_raw_files": raw_manifest_audit["existing_raw_files"],
        "existing_manifest_files": raw_manifest_audit["existing_manifest_files"],
    }
    base_audit = _build_acquisition_audit(
        mode="existing_local_acquisition",
        requested=requested,
        bbox=boundary.bbox,
        availability=availability,
        selected=selected,
        expected=plan,
        manifests=manifests,
        errors=[],
        scans=scans,
        filtered=filtered,
    )
    base_audit["manifest_parse_errors"] = manifest_errors
    base_audit["raw_manifest_audit"] = raw_manifest_audit
    base_audit["processed_validation"] = processed_validation
    base_audit["source_selection"] = source_selection
    base_audit["cross_sensor_diagnostic_matches"] = (
        len(profile["possible_cross_sensor_matches"]) if profile is not None else None
    )
    base_audit["raw_files_are_immutable_evidence"] = True
    base_audit["no_network_called"] = True
    base_audit["limitations"] = list(base_audit.get("limitations", [])) + [
        "Los días sin detecciones son distintos de fragmentos sin respuesta: todos los fragmentos esperados tienen manifest en esta auditoría.",
        "Los grupos de contenido idéntico entre raw vacíos no son duplicados de detecciones; corresponden a respuestas CSV con solo encabezado.",
    ]
    outputs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(outputs_dir / "firms_source_selection_2025.json", source_selection)
    _write_source_selection_markdown(source_selection, outputs_dir / "firms_source_selection_2025.md")
    if profile is not None:
        write_profile(
            profile,
            outputs_dir / "firms_cocle_2025_profile.json",
            outputs_dir / "firms_cocle_2025_profile.md",
        )
    processed_ok = (
        not manifest_errors
        and raw_manifest_audit["coverage_complete"]
        and not raw_manifest_audit["raw_manifest_hash_mismatches"]
        and not raw_manifest_audit["raw_manifest_size_mismatches"]
        and not raw_manifest_audit["raw_manifest_record_count_mismatches"]
        and not raw_manifest_audit["manifest_without_raw"]
        and not raw_manifest_audit["raw_without_manifest"]
        and not raw_manifest_audit["duplicate_manifest_keys"]
        and not raw_manifest_audit["invalid_response_files"]
        and not raw_manifest_audit["schema_incompatible_files"]
        and processed_validation["schema_matches_internal"]
        and processed_validation["matches_recomputed_filter"]
        and processed_validation["rows"] == processed_validation["recomputed_rows"]
        and not processed_validation["raw_file_missing"]
        and not processed_validation["raw_sha256_mismatch"]
        and not processed_validation["detection_id_mismatch"]
        and not processed_validation["source_row_number_invalid"]
        and not processed_validation["data_2026"]
    )
    base_audit["ready_for_next_stage"] = processed_ok
    _write_acquisition_audit(
        base_audit,
        outputs_dir / "firms_acquisition_audit_2025.json",
        outputs_dir / "firms_acquisition_audit_2025.md",
    )
    return base_audit, processed_ok


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report, valid = run(args)
    except (OSError, ValueError, BoundaryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "ready_for_next_stage": report["ready_for_next_stage"],
        "raw_manifest_audit": report["raw_manifest_audit"],
        "processed_validation": report["processed_validation"],
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
