"""Build and validate the anonymized blind AI calibration packages.

The module is intentionally local-only. It consumes the already-frozen Level 2
rasters, metrics, and event inputs, then calls the existing Level 2 compositor
with a public ``CASE-*`` display identifier. It never queries Earth Engine,
creates a review decision, or writes scientific outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .dnbr_quicklook import _parse_png
from .dnbr_quicklook_v2 import scientific_bundle_integrity
from .human_review_schema import (
    CALIBRATION_EVENT_IDS,
    CALIBRATION_ROUND,
    DEFAULT_CALIBRATION_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_UNOBSERVED_PATH,
    LABEL_STATUS_CODES,
    REVIEWER_TYPE_CODES,
    SCHEMA_SQL,
)
from .human_review_store import HumanReviewStore, ReviewStoreError
from .quicklook_level2 import (
    ANALYSIS_SCALE_M,
    COMPARISON_HEIGHT,
    COMPARISON_WIDTH,
    DIAGNOSTIC_DNBR_RANGE,
    GLOBAL_DNBR_RANGE,
    MASK_NODATA,
    NUMERIC_NODATA,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PRIMARY_CLOUD_THRESHOLD,
    REFLECTANCE_NODATA,
    RGB_BANDS,
    FALSE_COLOR_BANDS,
    compute_local_metrics,
    compose_level2_panel,
    compose_level2_temporal_sheet,
    load_dnbr_inputs,
)


ROOT = Path(__file__).resolve().parents[2]
BLIND_ROUND_ID = "blind_ai_calibration_r1"
STORE_ROUND_ID = CALIBRATION_ROUND
BLIND_PROTOCOL_VERSION = "draft-v1"
AI_REVIEWER_ID = "gpt_5_6_thinking_calibration_r1"
AI_REVIEWER_TYPE = "ai_assisted"
AI_LABEL_STATUS = "provisional_pseudolabel"
COMMIT_MESSAGE = "Add anonymized blind AI calibration package"

CASE_MAPPING: tuple[tuple[str, int, str], ...] = (
    ("CASE-001", 1, "event-r1500_t06-0ddd477d24b1364d"),
    ("CASE-002", 2, "event-r1500_t06-ef20fd746737f4ea"),
    ("CASE-003", 3, "event-r1500_t06-040b1a186d857b11"),
    ("CASE-004", 4, "event-r1500_t06-09c2d54e2d8fb5dd"),
    ("CASE-005", 5, "event-r1500_t06-9e5bf1d807f9d61a"),
    ("CASE-006", 6, "event-r1500_t06-84cb252a6877d2d5"),
    ("CASE-007", 7, "event-r1500_t06-548ca9e284d1a330"),
)
CASE_IDS = tuple(item[0] for item in CASE_MAPPING)
CASE_TO_EVENT = {case_id: event_id for case_id, _order, event_id in CASE_MAPPING}
EVENT_TO_CASE = {event_id: case_id for case_id, _order, event_id in CASE_MAPPING}

PRIVATE_MAP_COLUMNS = (
    "case_id",
    "randomized_order",
    "event_id",
    "multispectral_original_path",
    "temporal_original_path",
    "multispectral_blind_path",
    "temporal_blind_path",
    "original_sha256",
    "blind_sha256",
)

PROTOCOL_FILE = "BLIND_REVIEW_PROTOCOL_DRAFT_v1.md"
PASS_A_INSTRUCTIONS_FILE = "AI_BLIND_REVIEW_INSTRUCTIONS_PASS_A.md"
PASS_B_INSTRUCTIONS_FILE = "AI_BLIND_REVIEW_INSTRUCTIONS_PASS_B.md"
PASS_A_SCHEMA_FILE = "AI_REVIEW_OUTPUT_SCHEMA_PASS_A.json"
PASS_B_SCHEMA_FILE = "AI_REVIEW_OUTPUT_SCHEMA_PASS_B.json"
MANIFEST_A_FILE = "blind_manifest_pass_a.json"
MANIFEST_B_FILE = "blind_manifest_pass_b.json"
CHECKSUMS_A_FILE = "checksums_pass_a.sha256"
CHECKSUMS_B_FILE = "checksums_pass_b.sha256"

PASS_A_PANEL_NAMES = tuple(f"{case_id}_multispectral.png" for case_id in CASE_IDS)
PASS_B_PANEL_NAMES = tuple(f"{case_id}_temporal.png" for case_id in CASE_IDS)
PASS_A_FILES = (
    PROTOCOL_FILE,
    PASS_A_INSTRUCTIONS_FILE,
    PASS_A_SCHEMA_FILE,
    *PASS_A_PANEL_NAMES,
    MANIFEST_A_FILE,
    CHECKSUMS_A_FILE,
)
PASS_B_FILES = (
    PROTOCOL_FILE,
    PASS_B_INSTRUCTIONS_FILE,
    PASS_B_SCHEMA_FILE,
    *PASS_B_PANEL_NAMES,
    MANIFEST_B_FILE,
    CHECKSUMS_B_FILE,
)

ORIGINAL_PANEL_ROOT = Path("outputs/review_upload_level2")
RASTER_ROOT = Path("outputs/rasters/sentinel2_level2/events")
METRICS_PATH = Path("data/interim/sentinel2_dnbr_event_metrics.csv")
ACTIVE_BUNDLE_MANIFEST = Path("outputs/manifests/firepa_active_bundle_2026-07-21.json")
LEVEL2_MANIFEST = Path("outputs/manifests/firepa_quicklook_level2.sha256")
CALIBRATION_QUEUE = Path("outputs/human_review/calibration_round1_blinded.csv")
CALIBRATION_MANIFEST = Path("outputs/human_review/calibration_round1_manifest.json")

WINDOW_RASTER_KEYS = (
    "aoi_support",
    "common_valid_mask",
    "dnbr",
    "false_color_post",
    "false_color_pre",
    "nbr_post",
    "nbr_pre",
    "rgb_post",
    "rgb_pre",
)

ORIGINAL_EVENT_RE = re.compile(rb"event-r1500_t06-[0-9a-f]{16}")
WINDOW_ID_RE = re.compile(r"pre(\d+)_post(\d+)")
WINDOW_PATH_RE = re.compile(r"(?:^|[\\/])(?:outputs|data)[\\/]")
WINDOW_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
CASE_RE = re.compile(r"^CASE-[0-9]{3}$")


class BlindCalibrationError(RuntimeError):
    """Raised when a public calibration artifact would violate the contract."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _pair_sha256(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _index_sha256(paths: Iterable[Path], *, base: Path) -> tuple[int, str]:
    entries: list[str] = []
    for path in sorted(paths):
        if not path.is_file():
            continue
        entries.append(f"{path.relative_to(base).as_posix()} {_sha256_file(path)}")
    payload = ("\n".join(entries) + "\n").encode("utf-8") if entries else b"\n"
    return len(entries), _sha256_bytes(payload)


def _snapshot_sqlite(root: Path) -> dict[str, Any]:
    paths = sorted((root / "outputs/human_review").glob("*.sqlite*"))
    if not paths:
        return {"status": "absent", "entry_count": 0, "index_sha256": "absent"}
    count, digest = _index_sha256(paths, base=root / "outputs/human_review")
    return {"status": "present", "entry_count": count, "index_sha256": digest}


def integrity_snapshot(root: Path = ROOT) -> dict[str, Any]:
    """Hash protected scientific and review inputs without writing anything."""

    root = Path(root).resolve()
    active_manifest = root / ACTIVE_BUNDLE_MANIFEST
    scientific = scientific_bundle_integrity(active_manifest, root=root) if active_manifest.is_file() else {}
    raster_dir = root / RASTER_ROOT
    original_dir = root / ORIGINAL_PANEL_ROOT
    raster_count, raster_index = _index_sha256(
        raster_dir.rglob("*") if raster_dir.is_dir() else (),
        base=raster_dir,
    )
    original_count, original_index = _index_sha256(
        original_dir.glob("*.png") if original_dir.is_dir() else (),
        base=original_dir,
    )
    values: dict[str, Any] = {
        "scientific_index_sha256": scientific.get("scientific_index_sha256_after", ""),
        "scientific_entry_count": scientific.get("scientific_entry_count", 0),
        "scientific_visual_index_sha256": scientific.get("visual_index_sha256_after", ""),
        "scientific_visual_entry_count": scientific.get("visual_entry_count", 0),
        "level2_manifest_sha256": _sha256_file(root / LEVEL2_MANIFEST) if (root / LEVEL2_MANIFEST).is_file() else "missing",
        "level2_raster_index_sha256": raster_index,
        "level2_raster_entry_count": raster_count,
        "original_panel_index_sha256": original_index,
        "original_panel_entry_count": original_count,
        "calibration_queue_sha256": _sha256_file(root / CALIBRATION_QUEUE) if (root / CALIBRATION_QUEUE).is_file() else "missing",
        "calibration_manifest_sha256": _sha256_file(root / CALIBRATION_MANIFEST) if (root / CALIBRATION_MANIFEST).is_file() else "missing",
        "sqlite": _snapshot_sqlite(root),
    }
    return values


def compare_integrity(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    checks = {
        key: {
            "before": before.get(key),
            "after": after.get(key),
            "unchanged": before.get(key) == after.get(key),
        }
        for key in keys
    }
    return {
        "status": "pass" if all(item["unchanged"] for item in checks.values()) else "fail",
        "checks": checks,
    }


def _relative_output_path(output_root: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if parts and parts[0].lower() == "outputs":
        return output_root.joinpath(*parts[1:])
    return output_root / Path(relative)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BlindCalibrationError(f"Cannot read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BlindCalibrationError(f"JSON object required: {path}")
    return value


def _resolve_source_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _read_metric_rows(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = root / METRICS_PATH
    if not path.is_file():
        raise BlindCalibrationError(f"Missing frozen metrics: {path}")
    rows: dict[tuple[str, str], dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            event_id = str(row.get("event_id") or "")
            mode = str(row.get("analysis_mode") or "")
            if event_id not in EVENT_TO_CASE or mode not in {"selected_pair", "window_median"}:
                continue
            source_period_fields = {
                key: row.get(key)
                for key in (
                    "pre_scene_id",
                    "post_scene_id",
                    "pre_timestamp_utc",
                    "post_timestamp_utc",
                    "pre_scene_ids_used",
                    "post_scene_ids_used",
                )
            }
            if "2026" in json.dumps(source_period_fields, ensure_ascii=False):
                raise BlindCalibrationError("A frozen metric row contains a disallowed future-period value")
            try:
                cloud = float(row.get("cloud_threshold") or "nan")
            except ValueError:
                continue
            if abs(cloud - PRIMARY_CLOUD_THRESHOLD) > 1e-9:
                continue
            key = (event_id, mode)
            if key in rows:
                raise BlindCalibrationError(f"Duplicate metric row: {event_id}/{mode}")
            rows[key] = dict(row)
    missing = [
        f"{event_id}/{mode}"
        for event_id in CASE_TO_EVENT.values()
        for mode in ("selected_pair", "window_median")
        if (event_id, mode) not in rows
    ]
    if missing:
        raise BlindCalibrationError("Missing frozen metrics: " + ", ".join(missing))
    return rows


def _load_frozen_event_inputs(root: Path) -> dict[str, Any]:
    inputs = load_dnbr_inputs(
        pilot_path=root / "data/processed/sentinel2_observability_pilot_events.csv",
        events_path=root / "data/processed/firms_cocle_2025_events_provisional.csv",
        membership_path=root / "data/processed/firms_cocle_2025_event_membership.csv",
        selection_path=root / "outputs/sentinel2_event_pair_selection.csv",
        scene_inventory_path=root / "data/interim/sentinel2_scene_inventory.csv",
        aoi_inventory_path=root / "data/interim/sentinel2_aoi_inventory.csv",
    )
    by_event = {item.event_id: item for item in inputs.processable}
    missing = sorted(set(CASE_TO_EVENT.values()) - set(by_event))
    if missing:
        raise BlindCalibrationError("Missing processable frozen event inputs: " + ", ".join(missing))
    for event_input in by_event.values():
        if event_input.event_id not in EVENT_TO_CASE:
            continue
        records = (
            event_input.pre_scene,
            event_input.post_scene,
            *event_input.pre_candidates,
            *event_input.post_candidates,
        )
        scene_date_fields = [
            {key: record.get(key) for key in (
                "sentinel2_scene_id",
                "system_index",
                "acquisition_timestamp_utc",
                "window_start_utc",
                "window_end_utc",
            )}
            for record in records
            if isinstance(record, Mapping)
        ]
        if "2026" in json.dumps(scene_date_fields, ensure_ascii=False):
            raise BlindCalibrationError("A selected case references a disallowed future-period scene")
    return by_event


def _event_raster_inputs(root: Path, event_id: str) -> tuple[dict[str, Path], dict[str, Path] | None, dict[str, Any], str]:
    sidecar_path = root / RASTER_ROOT / f"{event_id}_export_metadata.json"
    payload = _read_json(sidecar_path)
    selected_meta = payload.get("selected_pair", {}).get("rasters", {})
    selected_paths = {
        key: _resolve_source_path(root, str(value["path"]))
        for key, value in selected_meta.items()
    }
    missing = [key for key in WINDOW_RASTER_KEYS if key not in selected_paths or not selected_paths[key].is_file()]
    if missing:
        raise BlindCalibrationError(f"Missing selected rasters for {event_id}: {', '.join(missing)}")

    window_meta = payload.get("window_median", {})
    window_available = bool(window_meta.get("available"))
    window_paths: dict[str, Path] | None = None
    if window_available:
        raw_window = window_meta.get("rasters", {})
        window_paths = {
            key: _resolve_source_path(root, str(value["path"]))
            for key, value in raw_window.items()
        }
        missing_window = [key for key in WINDOW_RASTER_KEYS if key not in window_paths or not window_paths[key].is_file()]
        if missing_window:
            raise BlindCalibrationError(f"Missing window rasters for {event_id}: {', '.join(missing_window)}")

    stretch = payload.get("global_false_color_stretch")
    if not isinstance(stretch, dict) or not stretch.get("bands"):
        raise BlindCalibrationError(f"Missing global false-color stretch for {event_id}")
    reason = "local numeric window median available" if window_available else "numeric window median unavailable"
    return selected_paths, window_paths, stretch, reason


def _source_doc_bytes(root: Path, filename: str) -> bytes:
    path = root / "docs" / filename
    if not path.is_file():
        raise BlindCalibrationError(f"Missing public source document: {path}")
    return path.read_bytes()


def _clean_generated_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            raise BlindCalibrationError(f"Refusing to remove unexpected directory: {child}")


def _write_package_zip(directory: Path, zip_path: Path, filenames: Sequence[str]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for filename in filenames:
            info = ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.create_version = 20
            info.extract_version = 20
            info.flag_bits = 0x800
            info.external_attr = 0
            info.internal_attr = 0
            archive.writestr(info, (directory / filename).read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)


def _checksum_text(directory: Path, filenames: Sequence[str], checksum_filename: str) -> str:
    return "".join(
        f"{_sha256_file(directory / filename)}  {filename}\n"
        for filename in filenames
        if filename != checksum_filename
    )


def _public_manifest(
    *,
    pass_name: str,
    panel_names: Sequence[str],
    panel_hashes: Mapping[str, str],
    filenames: Sequence[str],
) -> dict[str, Any]:
    return {
        "manifest_schema_version": "firepa-blind-ai-calibration-manifest-v1",
        "package_id": "firepa_blind_ai_calibration_r1",
        "pass": pass_name,
        "round_id": BLIND_ROUND_ID,
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "cases": [
            {
                "case_id": case_id,
                "randomized_order": order,
                "panel_filename": filename,
                "sha256": panel_hashes[filename],
            }
            for (case_id, order, _event_id), filename in zip(CASE_MAPPING, panel_names)
        ],
        "files": list(filenames),
        "panels_per_case": 1,
        "panel_dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
        "panel_mode": "RGB",
        "scope": {
            "earth_engine_queries_made": False,
            "future_period_data_used": False,
            "final_scientific_labels_created": False,
            "ground_truth": False,
            "source_identifiers_distributed": False,
        },
    }


def _write_package_documents(
    *,
    root: Path,
    directory: Path,
    pass_name: str,
    panel_names: Sequence[str],
    panel_payloads: Mapping[str, bytes],
) -> dict[str, Any]:
    pass_a = pass_name == "A"
    instruction_file = PASS_A_INSTRUCTIONS_FILE if pass_a else PASS_B_INSTRUCTIONS_FILE
    schema_file = PASS_A_SCHEMA_FILE if pass_a else PASS_B_SCHEMA_FILE
    manifest_file = MANIFEST_A_FILE if pass_a else MANIFEST_B_FILE
    checksums_file = CHECKSUMS_A_FILE if pass_a else CHECKSUMS_B_FILE
    filenames = PASS_A_FILES if pass_a else PASS_B_FILES
    _clean_generated_directory(directory)
    (directory / PROTOCOL_FILE).write_bytes(_source_doc_bytes(root, PROTOCOL_FILE))
    (directory / instruction_file).write_bytes(_source_doc_bytes(root, instruction_file))
    (directory / schema_file).write_bytes(_source_doc_bytes(root, schema_file))
    for filename in panel_names:
        (directory / filename).write_bytes(panel_payloads[filename])
    panel_hashes = {filename: _sha256_file(directory / filename) for filename in panel_names}
    manifest = _public_manifest(
        pass_name=pass_name,
        panel_names=panel_names,
        panel_hashes=panel_hashes,
        filenames=filenames,
    )
    (directory / manifest_file).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (directory / checksums_file).write_text(
        _checksum_text(directory, filenames, checksums_file),
        encoding="utf-8",
    )
    zip_path = directory.parents[2] / ("firepa_blind_ai_calibration_r1_pass_a.zip" if pass_a else "firepa_blind_ai_calibration_r1_pass_b.zip")
    _write_package_zip(directory, zip_path, filenames)
    return {
        "directory": directory,
        "zip": zip_path,
        "files": list(filenames),
        "panel_hashes": panel_hashes,
    }


def _render_case_panels(
    *,
    root: Path,
    case_id: str,
    event_id: str,
    event_input: Any,
    metrics: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[bytes, bytes]:
    selected_paths, window_paths, stretch, window_reason = _event_raster_inputs(root, event_id)
    selected_metrics = metrics[(event_id, "selected_pair")]
    window_metrics = metrics[(event_id, "window_median")]
    selected_local = compute_local_metrics(selected_paths)
    window_local = compute_local_metrics(window_paths) if window_paths is not None else None
    multispectral = compose_level2_panel(
        event_input=event_input,
        selected_metrics=selected_metrics,
        raster_paths=selected_paths,
        stretch=stretch,
        root=root,
        display_case_id=case_id,
    )
    temporal = compose_level2_temporal_sheet(
        event_input=event_input,
        selected_metrics=selected_metrics,
        window_metrics=window_metrics,
        selected_local_metrics=selected_local,
        window_local_metrics=window_local,
        selected_raster_paths=selected_paths,
        window_raster_paths=window_paths,
        window_available=window_paths is not None and window_local is not None,
        window_reason=window_reason,
        root=root,
        display_case_id=case_id,
    )
    return multispectral, temporal


def _mapping_rows(root: Path, output_root: Path, panel_payloads: Mapping[str, bytes]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case_id, order, event_id in CASE_MAPPING:
        original_multi = root / ORIGINAL_PANEL_ROOT / f"{event_id}_selected_pair_cs050_level2_panel.png"
        original_temporal = root / ORIGINAL_PANEL_ROOT / f"{event_id}_temporal_robustness_level2.png"
        blind_multi = output_root / "human_review/blind_ai_calibration_r1/pass_a" / f"{case_id}_multispectral.png"
        blind_temporal = output_root / "human_review/blind_ai_calibration_r1/pass_b" / f"{case_id}_temporal.png"
        if not original_multi.is_file() or not original_temporal.is_file():
            raise BlindCalibrationError(f"Missing original panels for {event_id}")
        blind_multi.write_bytes(panel_payloads[f"{case_id}_multispectral.png"])
        blind_temporal.write_bytes(panel_payloads[f"{case_id}_temporal.png"])
        rows.append(
            {
                "case_id": case_id,
                "randomized_order": str(order),
                "event_id": event_id,
                "multispectral_original_path": (ORIGINAL_PANEL_ROOT / original_multi.name).as_posix(),
                "temporal_original_path": (ORIGINAL_PANEL_ROOT / original_temporal.name).as_posix(),
                "multispectral_blind_path": "outputs/human_review/blind_ai_calibration_r1/pass_a/" + blind_multi.name,
                "temporal_blind_path": "outputs/human_review/blind_ai_calibration_r1/pass_b/" + blind_temporal.name,
                "original_sha256": _pair_sha256((original_multi, original_temporal)),
                "blind_sha256": _pair_sha256((blind_multi, blind_temporal)),
            }
        )
    return rows


def _write_private_mapping(output_root: Path, rows: Sequence[Mapping[str, str]]) -> Path:
    path = output_root / "human_review/private/calibration_r1_case_map.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRIVATE_MAP_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({column: str(row[column]) for column in PRIVATE_MAP_COLUMNS} for row in rows)
    return path


def build_blind_packages(
    root: Path = ROOT,
    *,
    output_root: Path | None = None,
    write_checkpoint: bool = False,
) -> dict[str, Any]:
    """Generate both packages and fail if any protected input changes."""

    source_root = Path(root).resolve()
    output_root = (output_root or source_root / "outputs").resolve()
    before = integrity_snapshot(source_root)
    event_inputs = _load_frozen_event_inputs(source_root)
    metrics = _read_metric_rows(source_root)
    panel_payloads: dict[str, bytes] = {}
    for case_id, _order, event_id in CASE_MAPPING:
        multispectral, temporal = _render_case_panels(
            root=source_root,
            case_id=case_id,
            event_id=event_id,
            event_input=event_inputs[event_id],
            metrics=metrics,
        )
        panel_payloads[f"{case_id}_multispectral.png"] = multispectral
        panel_payloads[f"{case_id}_temporal.png"] = temporal

    pass_a_dir = output_root / "human_review/blind_ai_calibration_r1/pass_a"
    pass_b_dir = output_root / "human_review/blind_ai_calibration_r1/pass_b"
    pass_a = _write_package_documents(
        root=source_root,
        directory=pass_a_dir,
        pass_name="A",
        panel_names=PASS_A_PANEL_NAMES,
        panel_payloads=panel_payloads,
    )
    pass_b = _write_package_documents(
        root=source_root,
        directory=pass_b_dir,
        pass_name="B",
        panel_names=PASS_B_PANEL_NAMES,
        panel_payloads=panel_payloads,
    )
    mapping_rows = _mapping_rows(source_root, output_root, panel_payloads)
    mapping_path = _write_private_mapping(output_root, mapping_rows)
    after = integrity_snapshot(source_root)
    integrity = compare_integrity(before, after)
    if integrity["status"] != "pass":
        raise BlindCalibrationError("Protected scientific or review inputs changed during blind package generation")
    validation = validate_blind_packages(source_root, output_root=output_root)
    if validation["status"] != "pass":
        raise BlindCalibrationError(json.dumps(validation, ensure_ascii=False, sort_keys=True, default=str))
    result = {
        "status": "pass",
        "round_id": BLIND_ROUND_ID,
        "case_ids": list(CASE_IDS),
        "pass_a": pass_a,
        "pass_b": pass_b,
        "mapping": mapping_path,
        "integrity_before": before,
        "integrity_after": after,
        "integrity": integrity,
        "validation": validation,
        "review_performed": False,
        "labels_created": False,
        "significant_burn_defined": False,
        "earth_engine_queries_made": False,
        "future_period_data_used": False,
        "push_performed": False,
    }
    if write_checkpoint:
        _write_checkpoint(source_root, result)
    return result


def _public_strings_are_safe(payload: bytes, *, allow_protocol_prohibition: bool) -> list[str]:
    errors: list[str] = []
    for event_id in EVENT_TO_CASE:
        if event_id.encode("ascii") in payload:
            errors.append(f"original event identifier present: {event_id}")
    if b"2026" in payload:
        errors.append("future-period year present")
    if re.search(rb"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]", payload) or b"\\\\" in payload:
        errors.append("absolute Windows path present")
    for token in (b"expected_class", b"predicted_class", b"model_score", b"frp"):
        if token in payload.lower():
            errors.append(f"prohibited token present: {token.decode()}")
    if b"significant_burn" in payload.lower() and not allow_protocol_prohibition:
        errors.append("scientific severity field present")
    return errors


def _png_text_payload(payload: bytes) -> bytes:
    """Extract uncompressed PNG text chunks for safe metadata scanning."""

    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return payload
    pieces: list[bytes] = []
    offset = 8
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(payload):
            break
        if kind == b"tEXt":
            pieces.append(payload[start:end])
        offset = end + 4
        if kind == b"IEND":
            break
    return b"\n".join(pieces)


def _scientific_visual_match(original: bytes, blind: bytes, *, temporal: bool) -> bool:
    original_png = _parse_png(original)
    blind_png = _parse_png(blind)
    original_width, original_height, original_color_type, original_channels, original_rows = original_png[:5]
    blind_width, blind_height, blind_color_type, blind_channels, blind_rows = blind_png[:5]
    if (original_width, original_height, original_color_type, original_channels) != (
        blind_width,
        blind_height,
        blind_color_type,
        blind_channels,
    ) or original_color_type != 2 or original_channels != 3:
        return False
    if temporal:
        regions = ((230, 374), (395, COMPARISON_HEIGHT))
    else:
        regions = ((170, 210), (228, PANEL_HEIGHT))
    return all(original_rows[top:bottom] == blind_rows[top:bottom] for top, bottom in regions)


def _validate_checksums(directory: Path, filenames: Sequence[str], checksum_filename: str) -> list[str]:
    errors: list[str] = []
    path = directory / checksum_filename
    if not path.is_file():
        return [f"missing checksum file: {checksum_filename}"]
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    expected = [filename for filename in filenames if filename != checksum_filename]
    seen: list[str] = []
    for line in rows:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            errors.append(f"malformed checksum line: {line}")
            continue
        digest, filename = parts
        seen.append(filename)
        if filename not in expected:
            errors.append(f"unexpected checksum filename: {filename}")
        elif _sha256_file(directory / filename) != digest:
            errors.append(f"checksum mismatch: {filename}")
    if seen != expected:
        errors.append("checksum file order or membership mismatch")
    return errors


def _validate_zip(directory: Path, zip_path: Path, filenames: Sequence[str]) -> list[str]:
    errors: list[str] = []
    if not zip_path.is_file():
        return [f"missing ZIP: {zip_path}"]
    try:
        with ZipFile(zip_path) as archive:
            names = archive.namelist()
            if names != list(filenames):
                errors.append("ZIP member order or membership mismatch")
            if len(names) != len(set(names)):
                errors.append("ZIP contains duplicate members")
            for name in filenames:
                if name not in names:
                    continue
                if archive.read(name) != (directory / name).read_bytes():
                    errors.append(f"ZIP payload mismatch: {name}")
            for info in archive.infolist():
                if info.date_time != (1980, 1, 1, 0, 0, 0):
                    errors.append(f"non-deterministic ZIP timestamp: {info.filename}")
    except Exception as exc:
        errors.append(f"cannot inspect ZIP: {exc}")
    return errors


def _validate_mapping(source_root: Path, output_root: Path) -> tuple[list[dict[str, str]], list[str]]:
    path = output_root / "human_review/private/calibration_r1_case_map.csv"
    errors: list[str] = []
    if not path.is_file():
        return [], [f"missing private mapping: {path}"]
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        if tuple(reader.fieldnames or ()) != PRIVATE_MAP_COLUMNS:
            errors.append("private mapping columns mismatch")
    if len(rows) != 7:
        errors.append("private mapping must contain exactly seven rows")
    for index, (case_id, order, event_id) in enumerate(CASE_MAPPING):
        row = rows[index] if index < len(rows) else {}
        if row.get("case_id") != case_id or row.get("randomized_order") != str(order) or row.get("event_id") != event_id:
            errors.append(f"private mapping order mismatch at {case_id}")
            continue
        original_multi = source_root / str(row.get("multispectral_original_path"))
        original_temporal = source_root / str(row.get("temporal_original_path"))
        blind_multi = _relative_output_path(output_root, str(row.get("multispectral_blind_path")))
        blind_temporal = _relative_output_path(output_root, str(row.get("temporal_blind_path")))
        if not original_multi.is_file() or not original_temporal.is_file():
            errors.append(f"missing original mapping target for {case_id}")
        if not blind_multi.is_file() or not blind_temporal.is_file():
            errors.append(f"missing blind mapping target for {case_id}")
        if original_multi.is_file() and original_temporal.is_file() and row.get("original_sha256") != _pair_sha256((original_multi, original_temporal)):
            errors.append(f"original pair hash mismatch for {case_id}")
        if blind_multi.is_file() and blind_temporal.is_file() and row.get("blind_sha256") != _pair_sha256((blind_multi, blind_temporal)):
            errors.append(f"blind pair hash mismatch for {case_id}")
    return rows, errors


def validate_blind_packages(source_root: Path = ROOT, *, output_root: Path | None = None) -> dict[str, Any]:
    """Validate public package contents, anonymization, and source equivalence."""

    source_root = Path(source_root).resolve()
    output_root = (output_root or source_root / "outputs").resolve()
    errors: list[str] = []
    mapping_rows, mapping_errors = _validate_mapping(source_root, output_root)
    errors.extend(mapping_errors)
    package_reports: dict[str, Any] = {}
    for pass_name, directory, filenames, manifest_filename, checksum_filename, temporal in (
        (
            "A",
            output_root / "human_review/blind_ai_calibration_r1/pass_a",
            PASS_A_FILES,
            MANIFEST_A_FILE,
            CHECKSUMS_A_FILE,
            False,
        ),
        (
            "B",
            output_root / "human_review/blind_ai_calibration_r1/pass_b",
            PASS_B_FILES,
            MANIFEST_B_FILE,
            CHECKSUMS_B_FILE,
            True,
        ),
    ):
        if not directory.is_dir():
            errors.append(f"missing package directory: {directory}")
            continue
        actual_files = tuple(path.name for path in sorted(directory.iterdir()) if path.is_file())
        if set(actual_files) != set(filenames):
            errors.append(f"{pass_name}: package directory contains unexpected files")
        errors.extend(_validate_checksums(directory, filenames, checksum_filename))
        zip_path = output_root / ("firepa_blind_ai_calibration_r1_pass_a.zip" if pass_name == "A" else "firepa_blind_ai_calibration_r1_pass_b.zip")
        errors.extend(_validate_zip(directory, zip_path, filenames))
        manifest = _read_json(directory / manifest_filename) if (directory / manifest_filename).is_file() else {}
        if manifest.get("files") != list(filenames):
            errors.append(f"{pass_name}: manifest file list mismatch")
        if manifest.get("pass") != pass_name or manifest.get("round_id") != BLIND_ROUND_ID:
            errors.append(f"{pass_name}: manifest identity mismatch")
        if manifest.get("cases") and [item.get("case_id") for item in manifest["cases"]] != list(CASE_IDS):
            errors.append(f"{pass_name}: manifest case order mismatch")
        for filename in filenames:
            path = directory / filename
            if not path.is_file():
                continue
            payload = path.read_bytes()
            scan_payload = _png_text_payload(payload) if filename.endswith(".png") else payload
            errors.extend(f"{pass_name}/{filename}: {error}" for error in _public_strings_are_safe(
                scan_payload,
                allow_protocol_prohibition=filename == PROTOCOL_FILE,
            ))
            if filename.endswith(".json") and b"significant_burn" in payload.lower():
                errors.append(f"{pass_name}/{filename}: prohibited severity field present")
            if filename.endswith(".png"):
                try:
                    width, height, color_type, channels, _rows = _parse_png(payload)[:5]
                except ValueError as exc:
                    errors.append(f"{pass_name}/{filename}: invalid PNG: {exc}")
                    continue
                mode = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}.get(color_type, "unknown")
                alpha_present = color_type in {4, 6}
                if (width, height, mode, alpha_present) != (
                    PANEL_WIDTH,
                    PANEL_HEIGHT,
                    "RGB",
                    False,
                ):
                    errors.append(f"{pass_name}/{filename}: image contract mismatch")
                if temporal and not filename.endswith("_temporal.png"):
                    errors.append(f"{pass_name}: non-temporal panel present")
                if not temporal and not filename.endswith("_multispectral.png"):
                    errors.append(f"{pass_name}: non-multispectral panel present")
        package_reports[pass_name] = {
            "directory": directory,
            "zip": zip_path,
            "files": list(filenames),
            "zip_sha256": _sha256_file(zip_path) if zip_path.is_file() else "missing",
        }

    for row in mapping_rows:
        case_id = str(row.get("case_id") or "")
        original_multi = source_root / str(row.get("multispectral_original_path") or "")
        original_temporal = source_root / str(row.get("temporal_original_path") or "")
        blind_multi = _relative_output_path(output_root, str(row.get("multispectral_blind_path") or ""))
        blind_temporal = _relative_output_path(output_root, str(row.get("temporal_blind_path") or ""))
        if original_multi.is_file() and blind_multi.is_file() and not _scientific_visual_match(original_multi.read_bytes(), blind_multi.read_bytes(), temporal=False):
            errors.append(f"scientific multispectral pixels changed outside identity regions: {case_id}")
        if original_temporal.is_file() and blind_temporal.is_file() and not _scientific_visual_match(original_temporal.read_bytes(), blind_temporal.read_bytes(), temporal=True):
            errors.append(f"scientific temporal pixels changed outside identity regions: {case_id}")

    return {
        "status": "pass" if not errors else "fail",
        "case_count": len(CASE_IDS),
        "multispectral_panel_count": len(PASS_A_PANEL_NAMES),
        "temporal_panel_count": len(PASS_B_PANEL_NAMES),
        "mapping_path": output_root / "human_review/private/calibration_r1_case_map.csv",
        "packages": package_reports,
        "errors": errors,
    }


def _write_checkpoint(root: Path, result: Mapping[str, Any]) -> Path:
    before = result["integrity_before"]
    after = result["integrity_after"]
    lines = [
        "# Blind AI calibration package checkpoint — 2026-07-22",
        "",
        "## Scope",
        "",
        "This checkpoint records a local-only packaging operation after the initial",
        "human-review-tool commit. No review was performed and no scientific data",
        "or source panel was edited.",
        "",
        "- Initial HEAD: `f56bdae9f6c41d587ed3e90d32273b5615350a3f`.",
        f"- Commit created: `{COMMIT_MESSAGE}`; the final SHA is verified by Git after commit and is not embedded here to avoid self-reference.",
        "- Frozen cases: `CASE-001`, `CASE-002`, `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`, `CASE-007`.",
        "- Private mapping: `outputs/human_review/private/calibration_r1_case_map.csv`.",
        "- Pass A package: `outputs/firepa_blind_ai_calibration_r1_pass_a.zip`.",
        "- Pass B package: `outputs/firepa_blind_ai_calibration_r1_pass_b.zip`.",
        "",
        "## Anonymization contract",
        "",
        "Panels were recomposed from the existing local Level 2 GeoTIFFs, frozen",
        "metrics, scene dates, temporal windows, AOI, masks, palettes, stretches,",
        "legends, overlays, and warnings. The compositor emits `CASE-*`, hides scene",
        "identifiers, omits source paths, and writes sanitized PNG metadata. The",
        "private map stores the exact case-to-source join and pair hashes; it is not",
        "copied into either package or public manifest.",
        "",
        "## Integrity before / after",
        "",
        "| Protected artifact | Before | After |",
        "|---|---|---|",
    ]
    labels = {
        "scientific_index_sha256": "scientific bundle index",
        "scientific_visual_index_sha256": "scientific visual index",
        "level2_manifest_sha256": "Level 2 manifest",
        "level2_raster_index_sha256": "Level 2 raster index",
        "original_panel_index_sha256": "original Level 2 panel index",
        "calibration_queue_sha256": "original blind queue",
        "calibration_manifest_sha256": "calibration manifest",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | `{before.get(key)}` | `{after.get(key)}` |")
    lines.extend(
        [
            "",
            f"- Protected-input comparison: `{result['integrity']['status']}`.",
            f"- Existing SQLite snapshot: `{before.get('sqlite')}` -> `{after.get('sqlite')}`.",
            "",
            "## Validation and tests",
            "",
            "- The two package manifests are deterministic and contain only the",
            "  documented twelve files for their pass.",
            "- Checksums cover every package file except the checksum file itself; ZIP members use fixed order and timestamps for reproducibility.",
            "- Validation checks exact case membership, two anonymized panels per",
            "  case, absence of source identifiers and Windows paths in public",
            "  artifacts, pass separation, RGB dimensions, public metadata, pair",
            "  hashes, and byte equality of scientific image regions.",
            "- Test command: `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`.",
            "- Importer command (dry-run only until external responses exist):",
            "  `python scripts/import_blind_ai_calibration.py --pass-a-json <PATH> --pass-b-json <PATH> --dry-run --report <PATH>`.",
            "",
            "## Explicit boundaries",
            "",
            "- Reviews performed: zero.",
            "- Scientific/final labels created: zero.",
            "- `significant_burn` defined: zero.",
            "- Earth Engine queries in this packaging operation: zero.",
            "- Future-period data used: zero.",
            "- Pushes: zero.",
            "- Final Git state: the requested source files are committed locally; pre-existing unrelated `data/`, `notebooks/`, and handoff work remains uncommitted and generated outputs remain ignored.",
        ]
    )
    path = root / "docs/BLIND_AI_CALIBRATION_PACKAGE_CHECKPOINT_2026-07-22.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _walk_values(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_values(child)


def _validate_ai_contract(payload: Any, *, pass_name: str, schema_path: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["review JSON must be an object"]
    try:
        schema = _read_json(schema_path)
    except BlindCalibrationError as exc:
        return [str(exc)]
    expected_root = tuple(schema.get("required", ()))
    if set(payload) != set(expected_root):
        errors.append("review JSON root fields do not match schema")
    constants = {
        "reviewer_id": AI_REVIEWER_ID,
        "reviewer_type": AI_REVIEWER_TYPE,
        "label_status": AI_LABEL_STATUS,
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "round_id": BLIND_ROUND_ID,
    }
    for field, expected in constants.items():
        if payload.get(field) != expected:
            errors.append(f"{field} constant mismatch")
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 7:
        errors.append("reviews must contain exactly seven objects")
        return errors
    expected_fields = (
        "case_id",
        "pass_a_visible_burn_scar",
        "pass_a_scar_confidence",
        "pass_a_event_association",
        "pass_a_competing_land_change",
        "pass_a_notes",
    )
    if pass_name == "B":
        expected_fields += (
            "pass_b_mode_agreement",
            "pass_b_confidence_after",
            "pass_b_requires_adjudication",
            "pass_b_notes",
        )
    seen: list[str] = []
    enums = {
        "pass_a_visible_burn_scar": {"yes", "no", "ambiguous", "unobserved"},
        "pass_a_scar_confidence": {"high", "medium", "low", "not_applicable"},
        "pass_a_event_association": {"likely", "possible", "unlikely", "indeterminate"},
        "pass_a_competing_land_change": {
            "none_visible", "agriculture_or_harvest", "soil_exposure", "vegetation_phenology",
            "moisture_or_flooding", "cloud_or_haze", "shadow_or_atmosphere", "water",
            "urban_or_construction", "mixed", "unknown",
        },
        "pass_b_mode_agreement": {"agree", "partially_agree", "disagree", "selected_pair_only", "window_median_only", "unavailable"},
        "pass_b_confidence_after": {"high", "medium", "low", "not_applicable"},
    }
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, dict):
            errors.append(f"review {index} is not an object")
            continue
        if set(review) != set(expected_fields):
            errors.append(f"review {index} fields do not match schema")
        case_id = review.get("case_id")
        seen.append(str(case_id))
        if case_id not in CASE_IDS:
            errors.append(f"unknown case id: {case_id!r}")
        for field, allowed in enums.items():
            if field in review and review[field] not in allowed:
                errors.append(f"invalid enum for {field}: {review[field]!r}")
        for field in expected_fields:
            if field == "pass_b_requires_adjudication":
                if not isinstance(review.get(field), bool):
                    errors.append(f"{field} must be boolean")
            elif field != "case_id" and (not isinstance(review.get(field), str) or not review.get(field).strip()):
                errors.append(f"{field} must be a non-empty string")
    if sorted(seen) != sorted(CASE_IDS) or len(set(seen)) != 7:
        errors.append("case ids must be the exact seven-case set")
    for key, child in _walk_values(payload):
        if key == "event_id":
            errors.append("AI response may not contain event_id")
        if isinstance(child, str) and re.search(r"(?:^|[^A-Za-z])[A-Za-z]:[\\/]", child):
            errors.append("AI response may not contain Windows paths")
        if isinstance(child, str) and ORIGINAL_EVENT_RE.search(child.encode("utf-8")):
            errors.append("AI response contains an original source identifier")
    return sorted(set(errors))


def _ensure_ai_columns(connection: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(reviews)").fetchall()}
    if "reviewer_type" not in columns:
        connection.execute("ALTER TABLE reviews ADD COLUMN reviewer_type TEXT NOT NULL DEFAULT 'human'")
    if "label_status" not in columns:
        connection.execute("ALTER TABLE reviews ADD COLUMN label_status TEXT NOT NULL DEFAULT 'human_observation'")
    connection.commit()


def _ai_row_from_reviews(
    *,
    case_id: str,
    event_id: str,
    reviewer_id: str,
    pass_a: Mapping[str, Any],
    pass_b: Mapping[str, Any],
    timestamp: str,
) -> dict[str, Any]:
    unobserved = pass_a["pass_a_visible_burn_scar"] == "unobserved"
    requires_adjudication = bool(pass_b["pass_b_requires_adjudication"])
    return {
        "round_id": STORE_ROUND_ID,
        "event_id": event_id,
        "reviewer_id": reviewer_id,
        "reviewer_type": AI_REVIEWER_TYPE,
        "label_status": AI_LABEL_STATUS,
        "pass_a_visible_burn_scar": pass_a["pass_a_visible_burn_scar"],
        "pass_a_scar_confidence": pass_a["pass_a_scar_confidence"],
        "pass_a_event_association": pass_a["pass_a_event_association"],
        "pass_a_competing_land_change": pass_a["pass_a_competing_land_change"],
        "pass_a_notes": pass_a["pass_a_notes"],
        "pass_a_saved_at": timestamp,
        "pass_a_revision": 1,
        "pass_b_mode_agreement": pass_b["pass_b_mode_agreement"],
        "pass_b_confidence_after": pass_b["pass_b_confidence_after"],
        "pass_b_requires_adjudication": 1 if requires_adjudication else 0,
        "pass_b_notes": pass_b["pass_b_notes"],
        "pass_b_saved_at": timestamp,
        "pass_b_revision": 1,
        "review_status": "unobserved" if unobserved else ("needs_adjudication" if requires_adjudication else "pass_b_complete"),
        "exclusion_reason": "AI marked panel unobserved" if unobserved else None,
        "adjudication_notes": pass_b["pass_b_notes"] if requires_adjudication else None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "case_id": case_id,
    }


def import_blind_results(
    pass_a_json: Path,
    pass_b_json: Path,
    *,
    root: Path = ROOT,
    output_root: Path | None = None,
    dry_run: bool = False,
    database: Path | None = None,
    report: Path | None = None,
) -> dict[str, Any]:
    """Validate and optionally import external Pass A/B JSON into SQLite."""

    root = Path(root).resolve()
    pass_a_json = Path(pass_a_json).resolve()
    pass_b_json = Path(pass_b_json).resolve()
    pass_a = _read_json(pass_a_json)
    pass_b = _read_json(pass_b_json)
    errors = _validate_ai_contract(pass_a, pass_name="A", schema_path=root / "docs/AI_REVIEW_OUTPUT_SCHEMA_PASS_A.json")
    errors.extend(_validate_ai_contract(pass_b, pass_name="B", schema_path=root / "docs/AI_REVIEW_OUTPUT_SCHEMA_PASS_B.json"))
    if pass_a.get("reviewer_id") != pass_b.get("reviewer_id"):
        errors.append("Pass A and Pass B reviewer_id differ")
    if pass_a.get("reviews") and pass_b.get("reviews"):
        by_case_a = {item.get("case_id"): item for item in pass_a["reviews"]}
        by_case_b = {item.get("case_id"): item for item in pass_b["reviews"]}
        for case_id in CASE_IDS:
            left = by_case_a.get(case_id)
            right = by_case_b.get(case_id)
            if left is None or right is None:
                continue
            for field in (
                "case_id",
                "pass_a_visible_burn_scar",
                "pass_a_scar_confidence",
                "pass_a_event_association",
                "pass_a_competing_land_change",
                "pass_a_notes",
            ):
                if left.get(field) != right.get(field):
                    errors.append(f"Pass B rewrites Pass A field {field} for {case_id}")
    output_root = (output_root or root / "outputs").resolve()
    mapping_rows, mapping_errors = _validate_mapping(root, output_root)
    errors.extend(mapping_errors)
    mapping_by_case = {row.get("case_id"): row for row in mapping_rows}
    if errors:
        result = {
            "status": "fail",
            "dry_run": dry_run,
            "errors": sorted(set(errors)),
            "reviewer_id": pass_a.get("reviewer_id"),
            "inserted": 0,
            "unchanged": 0,
            "database_written": False,
            "ground_truth": False,
        }
        if report is not None:
            Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    reviewer_id = str(pass_a["reviewer_id"])
    from .human_review_store import utc_timestamp

    timestamp = "1970-01-01T00:00:00Z" if dry_run else utc_timestamp()
    review_by_case = {item["case_id"]: item for item in pass_a["reviews"]}
    expected_rows = [
        _ai_row_from_reviews(
            case_id=case_id,
            event_id=str(mapping_by_case[case_id]["event_id"]),
            reviewer_id=reviewer_id,
            pass_a={key: review_by_case[case_id][key] for key in review_by_case[case_id] if key.startswith("pass_a_")},
            pass_b=next(item for item in pass_b["reviews"] if item["case_id"] == case_id),
            timestamp=timestamp,
        )
        for case_id in CASE_IDS
    ]
    db_path = Path(database).resolve() if database is not None else root / "outputs/human_review/firepa_human_review.sqlite3"
    inserted = 0
    unchanged = 0
    human_rows = 0
    if not dry_run:
        try:
            store = HumanReviewStore.from_frozen_round(db_path=db_path, root=root)
        except (OSError, sqlite3.Error, ReviewStoreError) as exc:
            result = {"status": "fail", "dry_run": False, "errors": [f"database initialization failed: {exc}"], "inserted": 0, "unchanged": 0, "database_written": False}
            if report is not None:
                Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return result
        try:
            _ensure_ai_columns(store.connection)
            for expected in expected_rows:
                active_humans = store.connection.execute(
                    "SELECT COUNT(*) FROM reviews WHERE round_id = ? AND event_id = ? AND reviewer_id <> ?",
                    (STORE_ROUND_ID, expected["event_id"], reviewer_id),
                ).fetchone()[0]
                human_rows += int(active_humans)
                existing = store.connection.execute(
                    "SELECT * FROM reviews WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
                    (STORE_ROUND_ID, expected["event_id"], reviewer_id),
                ).fetchone()
                if existing is not None:
                    compare_fields = [key for key in expected if key not in {"created_at", "updated_at", "case_id"}]
                    if any(existing[key] != expected[key] for key in compare_fields):
                        raise ReviewStoreError(f"Existing AI review conflicts for {expected['case_id']}")
                    unchanged += 1
                    continue
                columns = [
                    "round_id", "event_id", "reviewer_id", "reviewer_type", "label_status",
                    "pass_a_visible_burn_scar", "pass_a_scar_confidence", "pass_a_event_association",
                    "pass_a_competing_land_change", "pass_a_notes", "pass_a_saved_at", "pass_a_revision",
                    "pass_b_mode_agreement", "pass_b_confidence_after", "pass_b_requires_adjudication",
                    "pass_b_notes", "pass_b_saved_at", "pass_b_revision", "review_status",
                    "exclusion_reason", "adjudication_notes", "created_at", "updated_at",
                ]
                values = [expected[column] for column in columns]
                with store.connection:
                    store.connection.execute(
                        f"INSERT INTO reviews ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                        values,
                    )
                    for field_name in (
                        "reviewer_type", "label_status", "pass_a_visible_burn_scar", "pass_a_scar_confidence",
                        "pass_a_event_association", "pass_a_competing_land_change", "pass_a_notes",
                        "pass_b_mode_agreement", "pass_b_confidence_after", "pass_b_requires_adjudication",
                        "pass_b_notes", "review_status",
                    ):
                        store.connection.execute(
                            "INSERT INTO audit_log (round_id, event_id, reviewer_id, action, field_name, previous_value, new_value, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                STORE_ROUND_ID,
                                expected["event_id"],
                                reviewer_id,
                                "import_blind_ai_calibration",
                                field_name,
                                None,
                                None if expected[field_name] is None else str(expected[field_name]),
                                "blind_ai_calibration_r1",
                                timestamp,
                            ),
                        )
                inserted += 1
        finally:
            store.close()
    else:
        inserted = len(expected_rows)
    result = {
        "status": "pass",
        "dry_run": dry_run,
        "reviewer_id": reviewer_id,
        "reviewer_type": AI_REVIEWER_TYPE,
        "label_status": AI_LABEL_STATUS,
        "case_count": len(expected_rows),
        "inserted": inserted,
        "unchanged": unchanged,
        "human_rows_preserved": human_rows,
        "database": db_path,
        "database_written": not dry_run,
        "audit_action": "import_blind_ai_calibration",
        "ground_truth": False,
        "final_scientific_labels_created": False,
        "errors": [],
    }
    if report is not None:
        report_path = Path(report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return result


def cli_import(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Import blinded AI calibration responses into the private review store.")
    parser.add_argument("--pass-a-json", required=True)
    parser.add_argument("--pass-b-json", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", default=str(ROOT / "outputs"))
    parser.add_argument("--database", default=str(ROOT / "outputs/human_review/firepa_human_review.sqlite3"))
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    result = import_blind_results(
        Path(args.pass_a_json),
        Path(args.pass_b_json),
        output_root=Path(args.output_root),
        dry_run=args.dry_run,
        database=Path(args.database),
        report=Path(args.report) if args.report else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "pass" else 1
