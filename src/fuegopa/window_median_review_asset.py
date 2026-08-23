"""Local, read-only packaging of the seven ``window_median`` review assets.

This module deliberately does not build an Earth Engine graph.  The calibration
rasters already exported by the Level 2 pipeline are the only scientific input
to this pilot.  The module validates those artifacts, reconciles their numeric
metrics with the historical v3 rows, and writes a separate, ignored review
asset package.  It never rewrites the v3 metrics, inventories, checkpoints,
selected-pair panels, or formal-review assignments.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .dnbr_quicklook import RGBImage, decode_png_details, encode_png
from .quicklook_level2 import (
    ANALYSIS_CRS,
    ANALYSIS_SCALE_M,
    CALIBRATION_EVENT_IDS,
    DIAGNOSTIC_DNBR_RANGE,
    GLOBAL_DNBR_RANGE,
    MASK_NODATA,
    METRIC_TOLERANCES,
    NUMERIC_NODATA,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PRIMARY_CLOUD_THRESHOLD,
    QUICKLOOK_VERSION,
    REFLECTANCE_NODATA,
    RGB_GAMMA,
    RGB_REFLECTANCE_RANGE,
    RGB_BANDS,
    FALSE_COLOR_BANDS,
    _ACCENT,
    _ACCENT_DARK,
    _BACKGROUND,
    _BORDER,
    _INK,
    _INVALID,
    _MUTED,
    _WARNING,
    _WHITE,
    _draw_colorbar,
    _draw_firms_overlay,
    _draw_mask_inset_legend,
    _fill_rect,
    _format_timestamp,
    _hash_file,
    _palette_color,
    _raster_to_mask,
    _raster_to_rgb,
    _raster_to_scalar,
    _renderer,
    _resize_bilinear,
    _resize_nearest,
    _relative,
    _stroke_rect,
    _text,
    compare_local_metrics,
    compute_local_metrics,
    level2_visual_snapshot,
    load_dnbr_inputs,
    protected_snapshot,
    read_geotiff,
)
from .dnbr_quicklook_v2 import scientific_bundle_integrity
from .sentinel2_dnbr import (
    DNBR_FORMULA,
    FROZEN_CONFIGURATION_ID,
    NBR_FORMULA,
    default_dnbr_paths,
    read_utf8_csv,
)
from .sentinel2_observability import POST_WINDOW_OPTIONS, PRE_WINDOW_OPTIONS


ASSET_CONTRACT_VERSION = "firepa-window-median-review-asset-v1"
ASSET_ROOT = Path("outputs/window_median_review_asset_v1")
ASSET_DIR = ASSET_ROOT / "assets"
QA_DIR = ASSET_ROOT / "qa" / "calibration_7"
CANONICAL_MANIFEST = ASSET_ROOT / "window_median_review_asset_manifest.json"
QA_MANIFEST = QA_DIR / "manifest.json"
QA_REPORT_JSON = QA_DIR / "report.json"
QA_REPORT_MARKDOWN = QA_DIR / "report.md"
CONTACT_SHEET = QA_DIR / "calibration_7_selected_pair_vs_window_median_contact_sheet.png"
PANEL_SUFFIX = "_window_median_cs050_review_panel.png"
SIDECAR_SUFFIX = "_window_median_cs050_sidecar.json"
WINDOW_MODE = "window_median"
CASE_SET = "calibration-7"

RASTER_KEYS = (
    "aoi_support",
    "common_valid_mask",
    "rgb_pre",
    "rgb_post",
    "false_color_pre",
    "false_color_post",
    "nbr_pre",
    "nbr_post",
    "dnbr",
)
REFLECTANCE_KEYS = ("rgb_pre", "rgb_post", "false_color_pre", "false_color_post")
NUMERIC_KEYS = ("nbr_pre", "nbr_post", "dnbr")
MASK_KEYS = ("aoi_support", "common_valid_mask")
EXTENDED_METRIC_TOLERANCES = {
    **METRIC_TOLERANCES,
    # The Level 2 contract explicitly freezes the same 0.005 scalar tolerance
    # for dNBR medians.  It is reused for the two NBR medians rather than
    # introducing an event-specific allowance.
    "pre_nbr_median": METRIC_TOLERANCES["dnbr_median"],
    "post_nbr_median": METRIC_TOLERANCES["dnbr_median"],
}
METRIC_TOLERANCE_KEYS = {
    "common_valid_pixel_count": "pixel_count",
    "area_ha_dnbr_gt_010": "area_ha",
    "area_ha_dnbr_gt_020": "area_ha",
    "area_ha_dnbr_gt_030": "area_ha",
    "area_ha_dnbr_gt_040": "area_ha",
}
METRIC_KEYS = (
    "valid_overlap_fraction",
    "common_valid_pixel_count",
    "dnbr_median",
    "dnbr_p90",
    "area_ha_dnbr_gt_010",
    "area_ha_dnbr_gt_020",
    "area_ha_dnbr_gt_030",
    "area_ha_dnbr_gt_040",
    "pre_nbr_median",
    "post_nbr_median",
)
FORBIDDEN_FIELDS = {
    "frp",
    "confidence",
    "ranking",
    "selection_score",
    "model_score",
    "predicted_class",
    "target",
    "significant_burn",
    "severity",
    "triage",
    "review_status",
    "reviewer_notes",
    "ai_review",
}


class WindowMedianAssetError(RuntimeError):
    """Raised when a local asset cannot satisfy the frozen contract."""


class AssetConflictError(WindowMedianAssetError):
    """Raised when an existing identity has different bytes or provenance."""


@dataclass(frozen=True)
class WindowBounds:
    pre_start: datetime
    pre_end: datetime
    post_start: datetime
    post_end: datetime


@dataclass(frozen=True)
class SourceBundle:
    event_id: str
    raster_paths: Mapping[str, Path]
    raster_records: Mapping[str, Mapping[str, Any]]
    export_metadata_path: Path
    export_metadata_sha256: str
    raster_bundle_sha256: str
    selected_pair_panel_path: Path
    selected_pair_panel_sha256: str
    false_color_stretch: Mapping[str, Any]
    source_manifest_sha256: str
    active_manifest_sha256: str | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class CaseBuild:
    event_id: str
    case_alias: str
    sidecar_path: Path
    panel_path: Path
    sidecar: Mapping[str, Any]
    panel_payload: bytes
    selected_pair_panel_path: Path
    selected_pair_panel_sha256: str
    metrics: Mapping[str, Any]
    warnings: tuple[str, ...]
    status: str


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WindowMedianAssetError(f"Cannot read UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise WindowMedianAssetError(f"Expected JSON object: {path}")
    return value


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_event_path(event_id: str) -> str:
    if not re.fullmatch(r"event-r1500_t06-[0-9a-f]+", event_id):
        raise WindowMedianAssetError(f"Unexpected calibration event identifier: {event_id}")
    return event_id


def case_alias(index: int) -> str:
    if index < 1:
        raise ValueError("case aliases start at one")
    return f"CASE-{index:03d}"


def raster_paths_for_event(root: Path, event_id: str) -> dict[str, Path]:
    event_id = _safe_event_path(event_id)
    prefix = root / "outputs" / "rasters" / "sentinel2_level2" / "events" / f"{event_id}_window_median_cs050"
    return {key: prefix.with_name(prefix.name + f"_{key}.tif") for key in RASTER_KEYS}


def panel_path_for_event(root: Path, event_id: str) -> Path:
    return root / ASSET_ROOT / "qa" / "calibration_7" / f"{_safe_event_path(event_id)}{PANEL_SUFFIX}"


def sidecar_path_for_event(root: Path, event_id: str) -> Path:
    return root / ASSET_DIR / _safe_event_path(event_id) / f"{_safe_event_path(event_id)}{SIDECAR_SUFFIX}"


def selected_pair_panel_path_for_event(root: Path, event_id: str) -> Path:
    return (
        root
        / "outputs"
        / "figures"
        / "sentinel2_dnbr_level2"
        / "events"
        / f"{_safe_event_path(event_id)}_selected_pair_cs050_level2_panel.png"
    )


def _combination_parts(combination_id: str) -> tuple[str, str]:
    match = re.fullmatch(r"b0500_(pre30|pre60)_(post45|post90)", combination_id)
    if match is None:
        raise WindowMedianAssetError(f"Frozen temporal combination is invalid: {combination_id}")
    return match.group(1), match.group(2)


def window_bounds(event_input: Any) -> WindowBounds:
    pre_id, post_id = _combination_parts(str(event_input.selected_combination_id))
    pre_days, pre_gap_days = PRE_WINDOW_OPTIONS[pre_id]
    post_gap_days, post_days = POST_WINDOW_OPTIONS[post_id]
    return WindowBounds(
        pre_start=event_input.event.start_timestamp_utc - timedelta(days=pre_days),
        pre_end=event_input.event.start_timestamp_utc - timedelta(days=pre_gap_days),
        post_start=event_input.event.end_timestamp_utc + timedelta(days=post_gap_days),
        post_end=event_input.event.end_timestamp_utc + timedelta(days=post_days),
    )


def reflectance_median_per_band(
    scenes: Sequence[Mapping[str, Sequence[float]]],
    *,
    bands: Sequence[str] = ("B8", "B12"),
) -> dict[str, tuple[float, ...]]:
    """Compute a per-pixel median for each reflectance band.

    This small pure function is the contract test seam.  It intentionally
    accepts reflectance arrays and has no operation for median dNBR values.
    The production pilot reuses the already-exported local composites whose
    provenance records this same order of operations.
    """

    if not scenes:
        raise WindowMedianAssetError("At least one reflectance scene is required")
    lengths = {len(scenes[0].get(band, ())) for band in bands}
    if len(lengths) != 1 or not lengths:
        raise WindowMedianAssetError("Reflectance bands must share a non-empty pixel shape")
    pixel_count = next(iter(lengths))
    for scene in scenes:
        for band in bands:
            values = scene.get(band)
            if values is None or len(values) != pixel_count:
                raise WindowMedianAssetError("Reflectance scenes have incompatible band shapes")
    result: dict[str, tuple[float, ...]] = {}
    for band in bands:
        pixels: list[float] = []
        for index in range(pixel_count):
            values = sorted(float(scene[band][index]) for scene in scenes)
            middle = len(values) // 2
            if len(values) % 2:
                pixels.append(values[middle])
            else:
                pixels.append((values[middle - 1] + values[middle]) / 2.0)
        result[band] = tuple(pixels)
    return result


def nbr_from_reflectance(composite: Mapping[str, Sequence[float]]) -> tuple[float, ...]:
    """Apply the frozen NBR formula to one reflectance composite."""

    b8 = composite.get("B8")
    b12 = composite.get("B12")
    if b8 is None or b12 is None or len(b8) != len(b12):
        raise WindowMedianAssetError("B8 and B12 are required for NBR")
    values: list[float] = []
    for left, right in zip(b8, b12):
        denominator = float(left) + float(right)
        values.append((float(left) - float(right)) / denominator if denominator else float("nan"))
    return tuple(values)


def dnbr_from_composites(pre: Mapping[str, Sequence[float]], post: Mapping[str, Sequence[float]]) -> tuple[float, ...]:
    """Apply dNBR = NBR(pre median reflectance) - NBR(post median reflectance)."""

    pre_nbr = nbr_from_reflectance(pre)
    post_nbr = nbr_from_reflectance(post)
    if len(pre_nbr) != len(post_nbr):
        raise WindowMedianAssetError("Pre and post composites have incompatible shapes")
    return tuple(left - right for left, right in zip(pre_nbr, post_nbr))


def _source_metadata_path(root: Path, event_id: str) -> Path:
    return (
        root
        / "outputs"
        / "rasters"
        / "sentinel2_level2"
        / "events"
        / f"{_safe_event_path(event_id)}_export_metadata.json"
    )


def _check_raster_contract(key: str, raster: Any) -> None:
    if raster.width <= 0 or raster.height <= 0 or raster.transform is None:
        raise WindowMedianAssetError(f"{key}: invalid dimensions or missing transform")
    if raster.crs != ANALYSIS_CRS:
        raise WindowMedianAssetError(f"{key}: expected {ANALYSIS_CRS}, received {raster.crs}")
    if key in MASK_KEYS:
        expected_bands, expected_dtype, expected_nodata = 1, "uint8", 0.0
    elif key in REFLECTANCE_KEYS:
        expected_bands, expected_dtype, expected_nodata = 3, "uint16", 0.0
    else:
        expected_bands, expected_dtype, expected_nodata = 1, "float32", NUMERIC_NODATA
    if raster.band_count != expected_bands or raster.dtype != expected_dtype:
        raise WindowMedianAssetError(
            f"{key}: expected {expected_dtype}/{expected_bands} bands; "
            f"received {raster.dtype}/{raster.band_count}"
        )
    if raster.nodata is None or not math.isclose(float(raster.nodata), expected_nodata, abs_tol=1e-6):
        raise WindowMedianAssetError(f"{key}: nodata is not the documented value {expected_nodata}")


def _bundle_hash(records: Mapping[str, Mapping[str, Any]]) -> str:
    lines = [
        f"{key}\t{record['path']}\t{record['sha256']}"
        for key, record in sorted(records.items())
    ]
    return _sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _active_manifest_sha256(root: Path) -> str | None:
    path = root / "outputs" / "manifests" / "firepa_active_bundle_2026-07-21.json"
    return _hash_file(path) if path.is_file() else None


def _source_bundle(root: Path, event_input: Any) -> SourceBundle:
    event_id = event_input.event_id
    metadata_path = _source_metadata_path(root, event_id)
    if not metadata_path.is_file():
        raise WindowMedianAssetError(f"Missing Level 2 export metadata: {metadata_path}")
    metadata = _read_json(metadata_path)
    window = metadata.get("window_median")
    analysis = metadata.get("analysis")
    event_meta = metadata.get("event")
    if not isinstance(window, Mapping) or not window.get("available"):
        raise WindowMedianAssetError(f"window_median raster provenance is unavailable: {event_id}")
    if not isinstance(analysis, Mapping) or not isinstance(event_meta, Mapping):
        raise WindowMedianAssetError(f"Incomplete Level 2 provenance: {event_id}")
    if event_meta.get("event_id") != event_id or event_meta.get("configuration_id") != FROZEN_CONFIGURATION_ID:
        raise WindowMedianAssetError(f"Event/configuration provenance mismatch: {event_id}")
    if analysis.get("analysis_crs") != ANALYSIS_CRS or analysis.get("analysis_scale_m") != ANALYSIS_SCALE_M:
        raise WindowMedianAssetError(f"Analysis CRS/scale mismatch: {event_id}")
    if analysis.get("cloud_score_plus_threshold") != PRIMARY_CLOUD_THRESHOLD:
        raise WindowMedianAssetError(f"Cloud Score+ threshold mismatch: {event_id}")
    if analysis.get("nbr_formula") != NBR_FORMULA or analysis.get("dnbr_formula") != DNBR_FORMULA:
        raise WindowMedianAssetError(f"NBR/dNBR formula mismatch: {event_id}")
    raster_meta = window.get("rasters")
    if not isinstance(raster_meta, Mapping) or set(raster_meta) != set(RASTER_KEYS):
        raise WindowMedianAssetError(f"window_median raster bundle is incomplete: {event_id}")
    paths = raster_paths_for_event(root, event_id)
    records: dict[str, dict[str, Any]] = {}
    reference_rasters: dict[str, Any] = {}
    for key in RASTER_KEYS:
        record = raster_meta.get(key)
        if not isinstance(record, Mapping):
            raise WindowMedianAssetError(f"Missing raster metadata: {event_id}/{key}")
        path = paths[key]
        recorded_path = Path(str(record.get("path", "")))
        if not recorded_path.is_absolute():
            recorded_path = root / recorded_path
        if recorded_path.resolve() != path.resolve():
            raise WindowMedianAssetError(f"Raster path is not the frozen local path: {event_id}/{key}")
        if not path.is_file() or path.stat().st_size == 0:
            raise WindowMedianAssetError(f"Missing or empty raster: {path}")
        actual_sha = _hash_file(path)
        if actual_sha != str(record.get("sha256")):
            raise WindowMedianAssetError(f"Raster hash mismatch: {event_id}/{key}")
        raster = read_geotiff(path, nodata=MASK_NODATA if key in MASK_KEYS else NUMERIC_NODATA if key in NUMERIC_KEYS else REFLECTANCE_NODATA)
        _check_raster_contract(key, raster)
        reference_rasters[key] = raster
        records[key] = {
            "path": _relative(path, root),
            "sha256": actual_sha,
            "width": raster.width,
            "height": raster.height,
            "bands": raster.band_count,
            "dtype": raster.dtype,
            "nodata": raster.nodata,
            "crs": raster.crs,
            "transform": list(raster.transform or ()),
        }
    first = reference_rasters[RASTER_KEYS[0]]
    for key, raster in reference_rasters.items():
        if (raster.width, raster.height) != (first.width, first.height):
            raise WindowMedianAssetError(f"Raster dimensions differ inside bundle: {event_id}/{key}")
        if raster.transform != first.transform or raster.crs != first.crs:
            raise WindowMedianAssetError(f"Raster grid differs inside bundle: {event_id}/{key}")
    support = reference_rasters["aoi_support"].data[0]
    common = reference_rasters["common_valid_mask"].data[0]
    if any(value not in {0.0, 1.0} for value in support) or any(value not in {0.0, 1.0} for value in common):
        raise WindowMedianAssetError(f"Support/mask is not binary: {event_id}")
    # The frozen Level 2 ``common_valid_mask`` is a binary validity raster on
    # the export grid.  It is intentionally not clipped to the support tile;
    # the metric contract defines the common valid support as
    # ``common_valid_mask AND aoi_support``.  Checking that intersection is
    # what prevents the numerator from exceeding the denominator without
    # rewriting the existing raster.
    source_scene_ids = window.get("scene_ids") or metadata.get("event", {}).get("window_scene_ids")
    if not isinstance(source_scene_ids, Mapping):
        raise WindowMedianAssetError(f"Window scene IDs are absent: {event_id}")
    expected_pre_ids = sorted(str(row.get("sentinel2_scene_id") or row.get("system_index")) for row in event_input.pre_candidates)
    expected_post_ids = sorted(str(row.get("sentinel2_scene_id") or row.get("system_index")) for row in event_input.post_candidates)
    actual_pre_ids = sorted(str(value) for value in source_scene_ids.get("pre", []))
    actual_post_ids = sorted(str(value) for value in source_scene_ids.get("post", []))
    if actual_pre_ids != expected_pre_ids or actual_post_ids != expected_post_ids:
        raise WindowMedianAssetError(f"Scene provenance mismatch: {event_id}")
    for scene_id in [*actual_pre_ids, *actual_post_ids]:
        if "2026" in scene_id:
            raise WindowMedianAssetError(f"2026 scene is not permitted: {event_id}")
    stretch = metadata.get("global_false_color_stretch")
    if not isinstance(stretch, Mapping) or stretch.get("per_event_recalculation"):
        raise WindowMedianAssetError(f"A frozen global false-color stretch is absent: {event_id}")
    records_for_hash = {key: records[key] for key in RASTER_KEYS}
    source_payload = {
        "export_metadata_path": _relative(metadata_path, root),
        "export_metadata_sha256": _hash_file(metadata_path),
        "raster_bundle": records_for_hash,
        "metrics_path": _relative(root / "data" / "interim" / "sentinel2_dnbr_event_metrics.csv", root),
        "metrics_sha256": _hash_file(root / "data" / "interim" / "sentinel2_dnbr_event_metrics.csv"),
        "selection_path": _relative(root / "outputs" / "sentinel2_event_pair_selection.csv", root),
        "selection_sha256": _hash_file(root / "outputs" / "sentinel2_event_pair_selection.csv"),
        "scene_inventory_path": _relative(root / "data" / "interim" / "sentinel2_scene_inventory.csv", root),
        "scene_inventory_sha256": _hash_file(root / "data" / "interim" / "sentinel2_scene_inventory.csv"),
        "method": "local_exact_frozen_level2_window_median_bundle",
    }
    return SourceBundle(
        event_id=event_id,
        raster_paths=paths,
        raster_records=records,
        export_metadata_path=metadata_path,
        export_metadata_sha256=_hash_file(metadata_path),
        raster_bundle_sha256=_bundle_hash(records),
        selected_pair_panel_path=selected_pair_panel_path_for_event(root, event_id),
        selected_pair_panel_sha256=(
            _hash_file(selected_pair_panel_path_for_event(root, event_id))
            if selected_pair_panel_path_for_event(root, event_id).is_file()
            else ""
        ),
        false_color_stretch=dict(stretch),
        source_manifest_sha256=_canonical_hash(source_payload),
        active_manifest_sha256=_active_manifest_sha256(root),
        metadata=metadata,
    )


def _historical_metrics(root: Path, event_id: str) -> dict[str, str]:
    path = root / "data" / "interim" / "sentinel2_dnbr_event_metrics.csv"
    matches = []
    for row in read_utf8_csv(path):
        if (
            row.get("event_id") == event_id
            and row.get("analysis_mode") == WINDOW_MODE
            and _as_float(row.get("cloud_threshold")) == PRIMARY_CLOUD_THRESHOLD
        ):
            matches.append(dict(row))
    if len(matches) != 1:
        raise WindowMedianAssetError(f"Expected one historical window_median metric row: {event_id}")
    return matches[0]


def _metric_comparison(historical: Mapping[str, Any], local: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for key in METRIC_KEYS:
        expected = _as_float(historical.get(key))
        actual = _as_float(local.get(key))
        tolerance = EXTENDED_METRIC_TOLERANCES[METRIC_TOLERANCE_KEYS.get(key, key)]
        if expected is None or actual is None:
            checks.append({"metric": key, "status": "not_comparable", "expected": expected, "actual": actual, "tolerance": tolerance})
            continue
        difference = abs(actual - expected)
        relative = difference / abs(expected) if expected else (0.0 if difference == 0 else None)
        checks.append(
            {
                "metric": key,
                "status": "pass" if difference <= tolerance else "fail",
                "expected": expected,
                "actual": actual,
                "absolute_difference": difference,
                "relative_difference": relative,
                "tolerance": tolerance,
            }
        )
    failed = [item for item in checks if item.get("status") == "fail"]
    max_abs = max((float(item.get("absolute_difference", 0.0)) for item in checks if item.get("absolute_difference") is not None), default=0.0)
    max_ratio = max(
        (
            float(item["absolute_difference"]) / float(item["tolerance"])
            for item in checks
            if item.get("absolute_difference") is not None and item.get("tolerance")
        ),
        default=0.0,
    )
    return {
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "tolerances": dict(EXTENDED_METRIC_TOLERANCES),
        "maximum_absolute_difference": max_abs,
        "maximum_tolerance_ratio": max_ratio,
    }


def _structured_warnings(event_input: Any, local_metrics: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    if event_input.policy_path == "fallback":
        warnings.append("FALLBACK_TEMPORAL")
    if len(event_input.pre_candidates) < 2 or len(event_input.post_candidates) < 2:
        warnings.append("SCENE_COUNTS_LOW")
    overlap = _as_float(local_metrics.get("valid_overlap_fraction"))
    if overlap is not None and overlap < 0.98:
        warnings.append("MASK_OR_NODATA")
    coverage_values = [
        _as_float(row.get("data_coverage_fraction"))
        for row in [*event_input.pre_candidates, *event_input.post_candidates]
    ]
    if any(value is not None and value < 0.95 for value in coverage_values):
        warnings.append("PARTIAL_COVERAGE")
    clear_values = [
        _as_float(row.get("clear_fraction_cs_cdf_050"))
        for row in [*event_input.pre_candidates, *event_input.post_candidates]
    ]
    cloudy_values = [_as_float(row.get("cloudy_pixel_percentage")) for row in [*event_input.pre_candidates, *event_input.post_candidates]]
    if any(value is not None and value < 0.80 for value in clear_values) or any(value is not None and value > 20.0 for value in cloudy_values):
        warnings.append("CLOUD_OR_HAZE")
    return tuple(dict.fromkeys(warnings))


def _panel_metric_row(local_metrics: Mapping[str, Any], comparison: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(local_metrics),
        "metric_status": comparison.get("status", "unknown"),
        "area_ha_dnbr_gt_020": local_metrics.get("area_ha_dnbr_gt_020"),
    }


def compose_window_median_panel(
    *,
    event_input: Any,
    local_metrics: Mapping[str, Any],
    raster_paths: Mapping[str, Path],
    stretch: Mapping[str, Any],
    root: Path,
    warnings: Sequence[str] = (),
) -> bytes:
    """Render the Level 2 layout using only the window-median rasters."""

    font, renderer = _renderer()
    del font
    mask = read_geotiff(raster_paths["common_valid_mask"], nodata=MASK_NODATA)
    support = read_geotiff(raster_paths["aoi_support"], nodata=MASK_NODATA)
    rgb_pre = read_geotiff(raster_paths["rgb_pre"], nodata=REFLECTANCE_NODATA)
    rgb_post = read_geotiff(raster_paths["rgb_post"], nodata=REFLECTANCE_NODATA)
    fc_pre = read_geotiff(raster_paths["false_color_pre"], nodata=REFLECTANCE_NODATA)
    fc_post = read_geotiff(raster_paths["false_color_post"], nodata=REFLECTANCE_NODATA)
    dnbr = read_geotiff(raster_paths["dnbr"], nodata=NUMERIC_NODATA)
    common_dimensions = (mask.width, mask.height)
    for raster in (support, rgb_pre, rgb_post, fc_pre, fc_post, dnbr):
        if (raster.width, raster.height) != common_dimensions:
            raise WindowMedianAssetError("Window panel rasters do not share dimensions")
    by_band = {str(item["band"]): item for item in stretch.get("bands", [])}
    false_color_ranges = tuple(
        (float(by_band[band]["minimum"]), float(by_band[band]["maximum"]))
        for band in FALSE_COLOR_BANDS
    )
    tiles = {
        "rgb_pre": _raster_to_rgb(rgb_pre, mask=mask, band_indices=(0, 1, 2), ranges=(RGB_REFLECTANCE_RANGE,) * 3, gamma=RGB_GAMMA),
        "rgb_post": _raster_to_rgb(rgb_post, mask=mask, band_indices=(0, 1, 2), ranges=(RGB_REFLECTANCE_RANGE,) * 3, gamma=RGB_GAMMA),
        "false_color_pre": _raster_to_rgb(fc_pre, mask=None, band_indices=(0, 1, 2), ranges=false_color_ranges),
        "false_color_post": _raster_to_rgb(fc_post, mask=None, band_indices=(0, 1, 2), ranges=false_color_ranges),
        "dnbr_global": _raster_to_scalar(dnbr, mask=mask, minimum=GLOBAL_DNBR_RANGE[0], maximum=GLOBAL_DNBR_RANGE[1]),
        "dnbr_diagnostic": _raster_to_scalar(dnbr, mask=mask, minimum=DIAGNOSTIC_DNBR_RANGE[0], maximum=DIAGNOSTIC_DNBR_RANGE[1]),
        "mask": _raster_to_mask(mask, support),
    }
    canvas = RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, _BACKGROUND)
    bounds = window_bounds(event_input)
    event_id = event_input.event_id
    _text(renderer, canvas, event_id, 42, 28, 44, _INK, True)
    _text(renderer, canvas, f"{ASSET_CONTRACT_VERSION}  |  WINDOW MEDIAN  |  DESCRIPTIVE EVIDENCE", 44, 86, 24, _ACCENT_DARK, True)
    _text(
        renderer,
        canvas,
        f"EVENT UTC: {_format_dt(event_input.event.start_timestamp_utc)} to {_format_dt(event_input.event.end_timestamp_utc)}   PRE COMPOSITE: {_format_dt(bounds.pre_start)} to {_format_dt(bounds.pre_end)}   POST COMPOSITE: {_format_dt(bounds.post_start)} to {_format_dt(bounds.post_end)}",
        44,
        119,
        16,
        _MUTED,
    )
    _text(
        renderer,
        canvas,
        f"MEDIAN REFLECTANCE PER PIXEL/BAND   SCENES PRE: {len(event_input.pre_candidates)}   POST: {len(event_input.post_candidates)}   POLICY: {event_input.policy_path}   AOI: b0500 / 500 m   SCALE: 20 m   CRS: EPSG:32617   CS+: >= {PRIMARY_CLOUD_THRESHOLD:.2f}",
        44,
        148,
        16,
        _MUTED,
    )
    stretch_line = "  ".join(
        f"{item['band']} P2-P98={float(item['minimum']):.1f}/{float(item['maximum']):.1f}"
        for item in stretch.get("bands", [])
    )
    _text(renderer, canvas, f"FALSE-COLOR GLOBAL STRETCH: {stretch_line}", 44, 176, 16, _ACCENT_DARK, True)
    warning_text = "FLAGS: " + (" | ".join(warnings) if warnings else "NONE") + "   PRE/POST INDIVIDUAL MASKS: NOT EXPORTED; COMMON MASK SHOWN"
    _text(renderer, canvas, warning_text, 44, 201, 14, _WARNING if warnings else _ACCENT_DARK, True)

    tile_width, tile_height = 632, 500
    gap_x, gap_y = 22, 22
    left_margin, top_margin = 36, 228
    labels = {
        "rgb_pre": "RGB PRE COMPOSITE  |  B4/B3/B2",
        "rgb_post": "RGB POST COMPOSITE  |  B4/B3/B2",
        "false_color_pre": "FALSE-COLOR PRE COMPOSITE  |  B12/B8A/B4",
        "false_color_post": "FALSE-COLOR POST COMPOSITE  |  B12/B8A/B4",
        "dnbr_global": "dNBR WINDOW MEDIAN  |  fixed [-1.0, 1.0]",
        "dnbr_diagnostic": "dNBR DIAGNOSTIC  |  fixed [-0.25, 0.50]",
    }
    order = ("rgb_pre", "rgb_post", "false_color_pre", "false_color_post", "dnbr_global", "dnbr_diagnostic")
    for index, key in enumerate(order):
        column, row = index % 3, index // 3
        left = left_margin + column * (tile_width + gap_x)
        top = top_margin + row * (tile_height + gap_y)
        _fill_rect(canvas, left, top, tile_width, tile_height, _WHITE)
        _stroke_rect(canvas, left, top, tile_width, tile_height, _BORDER, 2)
        _text(renderer, canvas, labels[key], left + 18, top + 17, 20, _INK, True)
        if key == "dnbr_diagnostic":
            local_width, local_height = 534, 280
            image_left, image_top = left + 20, top + 62
        else:
            local_width, local_height = 534, 394
            image_left, image_top = left + 20, top + 62
        local = tiles[key]
        tile = _resize_bilinear(local, local_width, local_height) if key.startswith(("rgb", "false_color")) else _resize_nearest(local, local_width, local_height)
        canvas.paste(tile, image_left, image_top)
        if key == "rgb_post":
            _draw_firms_overlay(canvas, event_input, image_left, image_top, local_width, local_height)
            _text(renderer, canvas, "FIRMS detections + centroid   |   scale bar: 500 m", image_left + 10, image_top + local_height - 28, 16, _WHITE, True)
        if key == "dnbr_global":
            _draw_colorbar(renderer, canvas, left + 568, image_top + 30, local_height - 40, -1.0, 1.0, "dNBR")
        if key == "dnbr_diagnostic":
            _draw_colorbar(renderer, canvas, left + 568, image_top + 30, local_height - 40, -0.25, 0.50, "dNBR DIAG")
            mask_inset = _resize_nearest(tiles["mask"], 210, 105)
            _fill_rect(canvas, left + 20, top + 362, 226, 135, (235, 240, 242))
            _stroke_rect(canvas, left + 20, top + 362, 226, 135, _BORDER)
            _text(renderer, canvas, "COMMON VALID MASK", left + 30, top + 369, 13, _MUTED, True)
            canvas.paste(mask_inset, left + 30, top + 388)
            _draw_mask_inset_legend(renderer, canvas, left + 270, top + 374)

    overlap = _as_float(local_metrics.get("valid_overlap_fraction"))
    overlap_text = "n/a" if overlap is None else f"{overlap * 100:.1f}%"
    metric_values = (
        ("VALID OVERLAP", overlap_text, _ACCENT),
        ("dNBR MEDIAN", "n/a" if _as_float(local_metrics.get("dnbr_median")) is None else f"{float(local_metrics['dnbr_median']):.3f}", _ACCENT_DARK),
        ("dNBR P90", "n/a" if _as_float(local_metrics.get("dnbr_p90")) is None else f"{float(local_metrics['dnbr_p90']):.3f}", _ACCENT_DARK),
        ("AREA > 0.20", "n/a" if _as_float(local_metrics.get("area_ha_dnbr_gt_020")) is None else f"{float(local_metrics['area_ha_dnbr_gt_020']):.2f} ha", _ACCENT_DARK),
        ("RECONCILIATION", "PASS", _ACCENT),
    )
    metric_top, metric_width, metric_gap = 1286, 365, 12
    for index, (label, value, color) in enumerate(metric_values):
        left = 36 + index * (metric_width + metric_gap)
        _fill_rect(canvas, left, metric_top, metric_width, 70, _WHITE)
        _stroke_rect(canvas, left, metric_top, metric_width, 70, _BORDER)
        _text(renderer, canvas, label, left + 16, metric_top + 8, 15, _MUTED, True)
        _text(renderer, canvas, value, left + 16, metric_top + 32, 25, color, True)
    _text(renderer, canvas, "dNBR is descriptive evidence; it is not ground truth, severity, a label, or a fire confirmation.", 42, 1370, 20, _WARNING, True)
    _text(renderer, canvas, "Numeric sources: existing local float32 NBR/dNBR GeoTIFFs; RGB and false-color are fixed-range reflectance presentations; no Earth Engine query was made.", 42, 1397, 15, _MUTED)
    metadata = {
        "asset_contract_version": ASSET_CONTRACT_VERSION,
        "analysis_mode": WINDOW_MODE,
        "event_id": event_id,
        "panel_dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
        "final_format": "RGB",
        "global_dnbr_range": list(GLOBAL_DNBR_RANGE),
        "diagnostic_dnbr_range": list(DIAGNOSTIC_DNBR_RANGE),
        "false_color_stretch": dict(stretch),
        "rgb_range": list(RGB_REFLECTANCE_RANGE),
        "nodata": {"reflectance": REFLECTANCE_NODATA, "numeric": NUMERIC_NODATA, "mask": MASK_NODATA},
        "resampling_visual": {"rgb": "bilinear_presentation_only", "numeric": "nearest_neighbor", "mask": "nearest_neighbor"},
        "source_numeric_rasters": True,
        "earth_engine_queries_made": False,
        "warnings": list(warnings),
    }
    return encode_png(canvas, metadata)


def _validate_panel_payload(payload: bytes, *, event_id: str) -> dict[str, Any]:
    if not payload:
        raise WindowMedianAssetError(f"Empty panel payload: {event_id}")
    try:
        details = decode_png_details(payload)
    except Exception as exc:
        raise WindowMedianAssetError(f"Panel is not a readable self-contained PNG: {event_id}") from exc
    if details.mode != "RGB" or details.alpha_present:
        raise WindowMedianAssetError(f"Panel must be RGB without alpha: {event_id}")
    if (details.width, details.height) != (PANEL_WIDTH, PANEL_HEIGHT):
        raise WindowMedianAssetError(f"Panel dimensions are not frozen: {event_id}")
    if details.unique_pixel_count <= 1:
        raise WindowMedianAssetError(f"Panel is uniform: {event_id}")
    if details.exact_green_fraction > 0.95:
        raise WindowMedianAssetError(f"Panel is predominantly #00FF00: {event_id}")
    return {
        "mode": details.mode,
        "width": details.width,
        "height": details.height,
        "alpha_present": details.alpha_present,
        "unique_pixel_count": details.unique_pixel_count,
        "pixel_sha256": details.pixel_sha256,
        "sha256": details.source_sha256,
    }


def _forbidden_fields(value: Any, *, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold()
            if key_text in FORBIDDEN_FIELDS:
                found.append(f"{path}.{key}" if path else str(key))
            found.extend(_forbidden_fields(item, path=f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_fields(item, path=f"{path}[{index}]"))
    return found


def _sidecar_payload(
    *,
    root: Path,
    event_input: Any,
    source: SourceBundle,
    historical: Mapping[str, Any],
    local_metrics: Mapping[str, Any],
    comparison: Mapping[str, Any],
    panel_path: Path,
    panel_payload: bytes,
    warnings: Sequence[str],
    code_commit: str,
    case_alias_value: str,
) -> dict[str, Any]:
    bounds = window_bounds(event_input)
    event = event_input.event
    pre_ids = sorted(str(row.get("sentinel2_scene_id") or row.get("system_index")) for row in event_input.pre_candidates)
    post_ids = sorted(str(row.get("sentinel2_scene_id") or row.get("system_index")) for row in event_input.post_candidates)
    first_raster = source.raster_records["aoi_support"]
    return {
        "asset_id": f"{event_input.event_id}_window_median_cs050_review_asset_v1",
        "asset_contract_version": ASSET_CONTRACT_VERSION,
        "event_id": event_input.event_id,
        "case_alias": case_alias_value,
        "analysis_mode": WINDOW_MODE,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "scientific_role": "descriptive_window_median_evidence_not_ground_truth_or_severity_or_label",
        "policy": {
            "period_year": 2025,
            "aoi_id": "b0500",
            "aoi_buffer_m": 500,
            "policy_rule": "A",
            "policy_path": event_input.policy_path,
            "selected_combination_id": event_input.selected_combination_id,
            "fallback_temporal": event_input.policy_path == "fallback",
            "fallback_buffer": False,
            "cloud_score_plus_threshold": PRIMARY_CLOUD_THRESHOLD,
        },
        "windows": {
            "pre_window_start": _format_dt(bounds.pre_start),
            "pre_window_end": _format_dt(bounds.pre_end),
            "post_window_start": _format_dt(bounds.post_start),
            "post_window_end": _format_dt(bounds.post_end),
        },
        "scenes": {
            "pre_scene_ids": pre_ids,
            "post_scene_ids": post_ids,
            "pre_scene_count": len(pre_ids),
            "post_scene_count": len(post_ids),
            "all_source_scene_timestamps_year": 2025,
        },
        "composition": {
            "method": "median_per_pixel_per_reflectance_band_then_NBR_then_dNBR",
            "reflectance_bands": list(("B2", "B3", "B4", "B8A", "B8", "B12")),
            "rgb_bands": list(RGB_BANDS),
            "false_color_bands": list(FALSE_COLOR_BANDS),
            "nbr_formula": NBR_FORMULA,
            "dnbr_formula": DNBR_FORMULA,
            "cloud_score_plus_collection": "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED",
            "sentinel2_collection": "COPERNICUS/S2_SR_HARMONIZED",
            "mask_policy": "B8/B12 valid mask AND Cloud Score+ cs_cdf >= 0.50; common mask is pre_valid AND post_valid",
            "pre_post_valid_masks": {
                "pre": None,
                "post": None,
                "reason": "The frozen local Level 2 export contains the common mask but no separate pre/post mask rasters; no mask was fabricated.",
            },
            "common_valid_mask": _relative(source.raster_paths["common_valid_mask"], root),
        },
        "aoi": {
            "aoi_id": "b0500",
            "buffer_m": 500,
            "method": "detection_union_buffer",
            "area_m2": event_input.aoi_area_m2,
            "geometry_source": "existing_frozen_local_Level2_export",
        },
        "grid": {
            "crs": ANALYSIS_CRS,
            "analysis_scale_m": ANALYSIS_SCALE_M,
            "transform": first_raster["transform"],
            "width": first_raster["width"],
            "height": first_raster["height"],
            "nodata": {"reflectance": REFLECTANCE_NODATA, "numeric": NUMERIC_NODATA, "mask": MASK_NODATA},
        },
        "rasters": dict(source.raster_records),
        "panel": {
            "path": _relative(panel_path, root),
            "sha256": _sha256_bytes(panel_payload),
            "format": "PNG",
            "mode": "RGB",
            "dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
            "global_dnbr_range": list(GLOBAL_DNBR_RANGE),
            "diagnostic_dnbr_range": list(DIAGNOSTIC_DNBR_RANGE),
            "rgb_range": list(RGB_REFLECTANCE_RANGE),
            "false_color_stretch": dict(source.false_color_stretch),
            "resampling": {"rgb": "bilinear_presentation_only", "numeric": "nearest_neighbor", "mask": "nearest_neighbor"},
        },
        "metrics": {
            "historical_reference_not_ground_truth": True,
            "historical_row": {key: historical.get(key) for key in METRIC_KEYS},
            "recalculated_local": {key: local_metrics.get(key) for key in METRIC_KEYS},
            "comparison": dict(comparison),
        },
        "qa": {
            "status": "pass" if comparison.get("status") == "pass" else "fail",
            "structured_warnings": list(warnings),
            "selected_pair_used_as_window_median": False,
            "earth_engine_queries_made": False,
            "formal_review_connected": False,
        },
        "provenance": {
            "source_manifest_sha256": source.source_manifest_sha256,
            "active_scientific_manifest_sha256": source.active_manifest_sha256,
            "source_export_metadata_path": _relative(source.export_metadata_path, root),
            "source_export_metadata_sha256": source.export_metadata_sha256,
            "raster_bundle_sha256": source.raster_bundle_sha256,
            "source_selection_path": "outputs/sentinel2_event_pair_selection.csv",
            "source_metrics_path": "data/interim/sentinel2_dnbr_event_metrics.csv",
            "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "code_commit": code_commit,
            "earth_engine_project_identifier": None,
            "earth_engine_queries_made": False,
        },
        "limitations": [
            "window_median is not ground truth, severity, a label, or a confirmed fire.",
            "window_median does not replace selected_pair; the two modes remain separate evidence.",
            "This pilot references existing exact local Level 2 rasters and does not duplicate large GeoTIFFs.",
        ],
    }


def _check_existing_identity(sidecar: Mapping[str, Any], panel_payload: bytes, expected: Mapping[str, Any]) -> None:
    if sidecar.get("asset_id") != expected.get("asset_id") or sidecar.get("analysis_mode") != WINDOW_MODE:
        raise AssetConflictError("Existing asset identity does not match the requested window_median asset")
    expected_panel_sha = str(expected.get("panel", {}).get("sha256", ""))
    actual_panel_sha = _sha256_bytes(panel_payload)
    if expected_panel_sha != actual_panel_sha or sidecar.get("panel", {}).get("sha256") != actual_panel_sha:
        raise AssetConflictError("Existing window_median asset has the same identity but different panel bytes")
    for key, record in expected.get("rasters", {}).items():
        if sidecar.get("rasters", {}).get(key, {}).get("sha256") != record.get("sha256"):
            raise AssetConflictError(f"Existing window_median asset has different raster bytes: {key}")


def _build_case(
    *,
    root: Path,
    event_input: Any,
    case_index: int,
    code_commit: str,
) -> CaseBuild:
    source = _source_bundle(root, event_input)
    if not source.selected_pair_panel_path.is_file() or source.selected_pair_panel_path.stat().st_size == 0:
        raise WindowMedianAssetError(f"Existing selected_pair panel is missing: {event_input.event_id}")
    historical = _historical_metrics(root, event_input.event_id)
    local_metrics = compute_local_metrics(source.raster_paths)
    existing_comparison = compare_local_metrics(
        historical,
        local_metrics,
        event_id=event_input.event_id,
        analysis_mode=WINDOW_MODE,
    )
    comparison = _metric_comparison(historical, local_metrics)
    if existing_comparison.get("status") != "pass" or comparison.get("status") != "pass":
        raise WindowMedianAssetError(f"Historical metric reconciliation failed: {event_input.event_id}")
    warnings = _structured_warnings(event_input, local_metrics)
    panel_path = panel_path_for_event(root, event_input.event_id)
    panel_payload = compose_window_median_panel(
        event_input=event_input,
        local_metrics=local_metrics,
        raster_paths=source.raster_paths,
        stretch=source.false_color_stretch,
        root=root,
        warnings=warnings,
    )
    _validate_panel_payload(panel_payload, event_id=event_input.event_id)
    sidecar = _sidecar_payload(
        root=root,
        event_input=event_input,
        source=source,
        historical=historical,
        local_metrics=local_metrics,
        comparison=comparison,
        panel_path=panel_path,
        panel_payload=panel_payload,
        warnings=warnings,
        code_commit=code_commit,
        case_alias_value=case_alias(case_index),
    )
    if _forbidden_fields(sidecar):
        raise WindowMedianAssetError(f"Forbidden review/label fields in sidecar: {event_input.event_id}")
    return CaseBuild(
        event_id=event_input.event_id,
        case_alias=case_alias(case_index),
        sidecar_path=sidecar_path_for_event(root, event_input.event_id),
        panel_path=panel_path,
        sidecar=sidecar,
        panel_payload=panel_payload,
        selected_pair_panel_path=source.selected_pair_panel_path,
        selected_pair_panel_sha256=source.selected_pair_panel_sha256,
        metrics={"historical": historical, "local": local_metrics, "comparison": comparison},
        warnings=warnings,
        status="generated",
    )


def _manifest_payload(root: Path, cases: Sequence[CaseBuild], *, status: str, integrity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": ASSET_CONTRACT_VERSION,
        "case_set": CASE_SET,
        "analysis_mode": WINDOW_MODE,
        "status": status,
        "event_count": len(cases),
        "events": [
            {
                "event_id": case.event_id,
                "case_alias": case.case_alias,
                "mode": WINDOW_MODE,
                "sidecar_path": _relative(case.sidecar_path, root),
                "panel_path": _relative(case.panel_path, root),
                "panel_sha256": _sha256_bytes(case.panel_payload),
                "raster_bundle_sha256": case.sidecar["provenance"]["raster_bundle_sha256"],
                "source_manifest_sha256": case.sidecar["provenance"]["source_manifest_sha256"],
                "scene_ids": case.sidecar["scenes"],
                "policy": case.sidecar["policy"],
                "selected_pair_panel_reference": {
                    "path": _relative(case.selected_pair_panel_path, root),
                    "sha256": case.selected_pair_panel_sha256,
                    "modified": False,
                },
                "qa_status": case.sidecar["qa"]["status"],
                "warnings": list(case.warnings),
            }
            for case in cases
        ],
        "source": {
            "local_exact_level2_rasters": True,
            "earth_engine_queries_made": False,
            "no_raster_download": True,
            "historical_metrics_are_reproducibility_reference_not_ground_truth": True,
        },
        "formal_review": {
            "connected": False,
            "execution_authorized": False,
            "pass_a_count": 0,
            "pass_b_count": 0,
            "profiles_linked": 0,
            "reviews_started": 0,
        },
        "integrity": dict(integrity),
    }


def _markdown_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Window median review asset pilot",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Contract: `{ASSET_CONTRACT_VERSION}`",
        f"- Cases: {payload.get('generated_count', 0)}/{payload.get('requested_count', 0)}",
        "- Earth Engine queries: 0 (local exact Level 2 raster reuse)",
        "- Historical metric rows are reproducibility references, not ground truth.",
        "- Formal review connected: no; execution_authorized=false; Pass A/B=0.",
        "",
        "## Case results",
        "",
        "| Alias | Event | Pre scenes | Post scenes | Fallback | Overlap | dNBR median | Max diff/tolerance | Warnings |",
        "|---|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for case in payload.get("cases", []):
        metrics = case.get("metrics", {})
        local = metrics.get("local", {})
        comparison = metrics.get("comparison", {})
        policy = case.get("policy", {})
        lines.append(
            "| {alias} | {event} | {pre} | {post} | {fallback} | {overlap:.3f} | {dnbr:.3f} | {diff:.6f} | {warnings} |".format(
                alias=case.get("case_alias", ""),
                event=case.get("event_id", ""),
                pre=case.get("pre_scene_count", 0),
                post=case.get("post_scene_count", 0),
                fallback="yes" if policy.get("fallback_temporal") else "no",
                overlap=float(local.get("valid_overlap_fraction", 0.0)),
                dnbr=float(local.get("dnbr_median", 0.0)),
                diff=float(comparison.get("maximum_tolerance_ratio", 0.0)),
                warnings=", ".join(case.get("warnings", [])) or "none",
            )
        )
    lines.extend(
        [
            "",
            "## Frozen method",
            "",
            "Usable scenes are taken from the existing pre/post window. The historical method masks B8/B12 and Cloud Score+ cs_cdf >= 0.50, computes a per-pixel/per-band reflectance median independently for pre and post, then computes NBR and dNBR = NBR_pre - NBR_post. No median of individual dNBR values is used.",
            "",
            "The PNG is a Level 2-comparable descriptive panel with fixed RGB, false-color, global dNBR [-1, 1], and diagnostic dNBR [-0.25, 0.50] ranges. Nodata is neutral gray; numeric rasters remain scientific sources and alpha is not scientific data.",
            "",
            "## Integrity and limitations",
            "",
            f"- Preexisting scientific changed count: {payload.get('integrity', {}).get('scientific_changed_count', 'n/a')}",
            f"- Preexisting visual changed count: {payload.get('integrity', {}).get('visual_changed_count', 'n/a')}",
            "- Separate individual pre/post valid masks were not present in the frozen local Level 2 bundle; the sidecars record this explicitly and show only the common valid mask.",
            "- The new package references existing local GeoTIFFs; it does not duplicate, rewrite, or register them in the v1 scientific manifest.",
            "",
        ]
    )
    return "\n".join(lines)


def _contact_sheet(root: Path, cases: Sequence[CaseBuild]) -> bytes:
    font, renderer = _renderer()
    del font
    thumb_width, thumb_height = 780, 549
    margin, label_height, row_gap = 24, 44, 22
    sheet_width = margin * 3 + thumb_width * 2
    row_height = label_height + thumb_height + row_gap
    sheet_height = margin * 2 + row_height * len(cases)
    canvas = RGBImage.solid(sheet_width, sheet_height, _BACKGROUND)
    for index, case in enumerate(cases):
        row_top = margin + index * row_height
        for column, (mode, path) in enumerate(
            (("SELECTED_PAIR (EXISTING)", case.selected_pair_panel_path), ("WINDOW MEDIAN", case.panel_path))
        ):
            left = margin + column * (thumb_width + margin)
            _text(renderer, canvas, f"{case.case_alias}  |  {mode}", left, row_top, 18, _INK, True)
            if mode == "WINDOW MEDIAN" and case.warnings:
                _text(renderer, canvas, "FLAGS: " + " | ".join(case.warnings), left + 315, row_top + 2, 13, _WARNING, True)
            if not path.is_file():
                raise WindowMedianAssetError(f"Contact sheet source is missing: {path}")
            image = decode_png_details(path.read_bytes()).image
            tile = _resize_bilinear(image, thumb_width, thumb_height)
            canvas.paste(tile, left, row_top + label_height)
            _stroke_rect(canvas, left, row_top + label_height, thumb_width, thumb_height, _BORDER, 2)
    return encode_png(
        canvas,
        {
            "asset_contract_version": ASSET_CONTRACT_VERSION,
            "case_set": CASE_SET,
            "comparison": "selected_pair_vs_window_median",
            "same_visual_scale": True,
            "earth_engine_queries_made": False,
        },
    )


def _integrity_summary(root: Path, before_visual: Mapping[str, Any], after_visual: Mapping[str, Any]) -> dict[str, Any]:
    changed = [
        path
        for path in sorted(
            {item["path"] for item in before_visual.get("entries", [])}
            | {item["path"] for item in after_visual.get("entries", [])}
        )
        if {
            item["path"]: item["sha256"] for item in before_visual.get("entries", [])
        }.get(path)
        != {
            item["path"]: item["sha256"] for item in after_visual.get("entries", [])
        }.get(path)
    ]
    active = root / "outputs" / "manifests" / "firepa_active_bundle_2026-07-21.json"
    scientific = scientific_bundle_integrity(active, root=root) if active.is_file() else {}
    scientific_hash = _hash_file(active) if active.is_file() else None
    return {
        "scientific_bundle_manifest_sha256": scientific_hash,
        "scientific_index_sha256": "249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa",
        "visual_index_sha256": "ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401",
        "scientific_changed_count": int(scientific.get("scientific_changed_count", 0)),
        "visual_changed_count": int(scientific.get("visual_changed_count", len(changed))),
        "visual_changed_paths": list(scientific.get("visual_changed_paths", changed)),
        "selected_pair_level2_unchanged": not changed,
        "protected_snapshot": protected_snapshot(root),
    }


def build_pilot(
    root: Path,
    *,
    resume: bool = False,
    dry_run: bool = False,
    event_ids: Sequence[str] = CALIBRATION_EVENT_IDS,
) -> dict[str, Any]:
    requested = tuple(event_ids)
    if requested != tuple(CALIBRATION_EVENT_IDS):
        raise WindowMedianAssetError("This pilot accepts exactly the frozen calibration-7 event set")
    before_visual = level2_visual_snapshot(root)
    before_protected = protected_snapshot(root)
    active_before = _active_manifest_sha256(root)
    source_paths = default_dnbr_paths(root)
    inputs = load_dnbr_inputs(
        pilot_path=source_paths["pilot"],
        events_path=source_paths["events"],
        membership_path=source_paths["membership"],
        selection_path=source_paths["selection"],
        scene_inventory_path=source_paths["scene_inventory"],
        aoi_inventory_path=source_paths["aoi_inventory"],
    )
    by_event = {item.event_id: item for item in inputs.processable}
    missing = sorted(set(requested) - set(by_event))
    if missing:
        raise WindowMedianAssetError("Calibration event missing from frozen processable inputs: " + ", ".join(missing))
    code_commit = _git_head(root)
    cases: list[CaseBuild] = []
    errors: list[dict[str, str]] = []
    for index, event_id in enumerate(requested, start=1):
        try:
            case = _build_case(root=root, event_input=by_event[event_id], case_index=index, code_commit=code_commit)
            existing_sidecar = case.sidecar_path
            existing_panel = case.panel_path
            if existing_sidecar.exists() or existing_panel.exists():
                if not existing_sidecar.is_file() or not existing_panel.is_file():
                    raise AssetConflictError(f"Partial existing asset for {event_id}")
                existing = _read_json(existing_sidecar)
                _check_existing_identity(existing, existing_panel.read_bytes(), case.sidecar)
                if not resume:
                    raise AssetConflictError(f"Existing valid asset requires --resume: {event_id}")
                case = CaseBuild(**{**case.__dict__, "status": "resumed"})
            elif not dry_run:
                _write_bytes_atomic(case.panel_path, case.panel_payload)
                _write_json_atomic(case.sidecar_path, case.sidecar)
            cases.append(case)
        except Exception as exc:
            errors.append({"event_id": event_id, "error_type": type(exc).__name__, "message": str(exc)})
            break
    if dry_run:
        return {
            "status": "dry_run_pass" if len(cases) == len(requested) and not errors else "dry_run_fail",
            "requested_count": len(requested),
            "generated_count": len(cases),
            "cases": [
                {
                    "event_id": case.event_id,
                    "case_alias": case.case_alias,
                    "status": case.status,
                    "pre_scene_count": case.sidecar["scenes"]["pre_scene_count"],
                    "post_scene_count": case.sidecar["scenes"]["post_scene_count"],
                    "warnings": list(case.warnings),
                    "metrics": dict(case.metrics),
                }
                for case in cases
            ],
            "errors": errors,
            "earth_engine_queries_made": False,
            "writes_performed": False,
        }
    after_visual = level2_visual_snapshot(root)
    integrity = _integrity_summary(root, before_visual, after_visual)
    integrity["preexisting_protected_changed_count"] = len(
        [
            path
            for path in sorted(
                {item["path"] for item in before_protected.get("entries", [])}
                | {item["path"] for item in integrity["protected_snapshot"].get("entries", [])}
            )
            if {
                item["path"]: item["sha256"] for item in before_protected.get("entries", [])
            }.get(path)
            != {
                item["path"]: item["sha256"] for item in integrity["protected_snapshot"].get("entries", [])
            }.get(path)
        ]
    )
    status = "pilot_pass" if len(cases) == len(requested) and not errors and integrity["selected_pair_level2_unchanged"] else "pilot_fail"
    if status == "pilot_pass":
        contact_payload = _contact_sheet(root, cases)
        _write_bytes_atomic(root / CONTACT_SHEET, contact_payload)
        manifest = _manifest_payload(root, cases, status=status, integrity=integrity)
        _write_json_atomic(root / CANONICAL_MANIFEST, manifest)
        _write_json_atomic(root / QA_MANIFEST, manifest)
        report = {
            "status": status,
            "asset_contract_version": ASSET_CONTRACT_VERSION,
            "case_set": CASE_SET,
            "requested_count": len(requested),
            "generated_count": len(cases),
            "cases": [
                {
                    "event_id": case.event_id,
                    "case_alias": case.case_alias,
                    "status": case.status,
                    "panel_path": _relative(case.panel_path, root),
                    "panel_sha256": _sha256_bytes(case.panel_payload),
                    "sidecar_path": _relative(case.sidecar_path, root),
                    "raster_bundle_sha256": case.sidecar["provenance"]["raster_bundle_sha256"],
                    "source_manifest_sha256": case.sidecar["provenance"]["source_manifest_sha256"],
                    "selected_pair_panel_path": _relative(case.selected_pair_panel_path, root),
                    "selected_pair_panel_sha256": case.selected_pair_panel_sha256,
                    "pre_scene_count": case.sidecar["scenes"]["pre_scene_count"],
                    "post_scene_count": case.sidecar["scenes"]["post_scene_count"],
                    "policy": case.sidecar["policy"],
                    "warnings": list(case.warnings),
                    "metrics": dict(case.metrics),
                }
                for case in cases
            ],
            "errors": errors,
            "earth_engine_queries_made": False,
            "source_classification": {"A_local_exact": len(cases), "B_earth_engine_required": 0, "C_missing_provenance": 0},
            "integrity": integrity,
            "historical_metrics_are_not_ground_truth": True,
            "formal_review": {"execution_authorized": False, "pass_a_count": 0, "pass_b_count": 0, "profiles_linked": 0, "reviews_started": 0, "connected": False},
            "contact_sheet_path": _relative(root / CONTACT_SHEET, root),
            "manifest_path": _relative(root / CANONICAL_MANIFEST, root),
            "qa_manifest_path": _relative(root / QA_MANIFEST, root),
        }
        report["markdown"] = _markdown_report(report)
        _write_json_atomic(root / QA_REPORT_JSON, report)
        _write_text_atomic(root / QA_REPORT_MARKDOWN, report["markdown"])
        return report
    return {
        "status": status,
        "requested_count": len(requested),
        "generated_count": len(cases),
        "cases": [
            {"event_id": case.event_id, "case_alias": case.case_alias, "status": case.status}
            for case in cases
        ],
        "errors": errors,
        "earth_engine_queries_made": False,
        "integrity": integrity,
        "active_manifest_sha256_before": active_before,
    }


def verify_pilot(root: Path) -> dict[str, Any]:
    """Read-only verification of the separate calibration-7 package."""

    manifest_path = root / CANONICAL_MANIFEST
    if not manifest_path.is_file():
        return {
            "status": "fail",
            "errors": [f"Missing manifest: {_relative(manifest_path, root)}"],
            "read_only": True,
            "earth_engine_queries_made": False,
        }
    manifest = _read_json(manifest_path)
    errors: list[str] = []
    if manifest.get("asset_id") != ASSET_CONTRACT_VERSION or manifest.get("analysis_mode") != WINDOW_MODE:
        errors.append("manifest contract or analysis mode mismatch")
    events = manifest.get("events")
    if not isinstance(events, list) or {item.get("event_id") for item in events} != set(CALIBRATION_EVENT_IDS):
        errors.append("manifest does not contain exactly the seven calibration events")
    for item in events if isinstance(events, list) else []:
        event_id = str(item.get("event_id"))
        sidecar_path = root / str(item.get("sidecar_path", ""))
        panel_path = root / str(item.get("panel_path", ""))
        if not sidecar_path.is_file() or not panel_path.is_file():
            errors.append(f"missing sidecar or panel: {event_id}")
            continue
        sidecar = _read_json(sidecar_path)
        panel_payload = panel_path.read_bytes()
        try:
            _validate_panel_payload(panel_payload, event_id=event_id)
        except WindowMedianAssetError as exc:
            errors.append(str(exc))
        if _sha256_bytes(panel_payload) != sidecar.get("panel", {}).get("sha256"):
            errors.append(f"panel hash mismatch: {event_id}")
        if _sha256_bytes(panel_payload) != item.get("panel_sha256"):
            errors.append(f"manifest panel hash mismatch: {event_id}")
        if sidecar.get("analysis_mode") != WINDOW_MODE or sidecar.get("configuration_id") != FROZEN_CONFIGURATION_ID:
            errors.append(f"sidecar mode/configuration mismatch: {event_id}")
        if sidecar.get("policy", {}).get("cloud_score_plus_threshold") != PRIMARY_CLOUD_THRESHOLD:
            errors.append(f"sidecar Cloud Score+ threshold mismatch: {event_id}")
        if sidecar.get("grid", {}).get("crs") != ANALYSIS_CRS or sidecar.get("grid", {}).get("analysis_scale_m") != ANALYSIS_SCALE_M:
            errors.append(f"sidecar grid mismatch: {event_id}")
        if any("2026" in str(value) for value in sidecar.get("scenes", {}).get("pre_scene_ids", []) + sidecar.get("scenes", {}).get("post_scene_ids", [])):
            errors.append(f"2026 scene present: {event_id}")
        forbidden = _forbidden_fields(sidecar)
        if forbidden:
            errors.append(f"forbidden fields in sidecar {event_id}: {forbidden}")
        for key, record in sidecar.get("rasters", {}).items():
            path = root / str(record.get("path", ""))
            if not path.is_file() or _hash_file(path) != record.get("sha256"):
                errors.append(f"raster hash/path mismatch: {event_id}/{key}")
        selected_ref = item.get("selected_pair_panel_reference", {})
        selected_path = root / str(selected_ref.get("path", ""))
        if not selected_path.is_file() or _hash_file(selected_path) != selected_ref.get("sha256"):
            errors.append(f"selected_pair reference changed or missing: {event_id}")
        if _sha256_bytes(panel_payload) == selected_ref.get("sha256"):
            errors.append(f"selected_pair and window_median panel hashes are identical: {event_id}")
        if sidecar.get("qa", {}).get("earth_engine_queries_made") is not False:
            errors.append(f"Earth Engine query flag is not false: {event_id}")
    integrity = manifest.get("integrity", {})
    if integrity.get("scientific_changed_count") != 0 or integrity.get("visual_changed_count") != 0:
        errors.append("preexisting integrity counts are non-zero")
    if manifest.get("formal_review", {}).get("execution_authorized") is not False:
        errors.append("formal review execution is authorized")
    return {
        "status": "pass" if not errors else "fail",
        "contract": ASSET_CONTRACT_VERSION,
        "event_count": len(events) if isinstance(events, list) else 0,
        "errors": errors,
        "read_only": True,
        "earth_engine_queries_made": False,
        "execution_authorized": False,
        "pass_a_count": 0,
        "pass_b_count": 0,
    }
