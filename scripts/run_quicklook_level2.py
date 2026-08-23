"""Run the controlled Level 2 multispectral evidence batch.

This runner is intentionally separate from ``run_sentinel2_dnbr.py``.  It
loads the frozen v3 inputs, performs read-only Earth Engine downloads into the
new Level 2 tree, validates numeric outputs against the frozen metrics, and
does not write any scientific CSV, JSON, cache, checkpoint, queue, or label.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fuegopa.dnbr_quicklook_v2 import scientific_bundle_integrity  # noqa: E402
from fuegopa.earth_engine import (  # noqa: E402
    exception_diagnostics,
    initialize_earth_engine,
    smoke_test,
)
from fuegopa.quicklook_level2 import (  # noqa: E402
    ANALYSIS_CRS,
    ANALYSIS_SCALE_M,
    CALIBRATION_EVENT_IDS,
    FIGURE_DIR,
    MANIFEST_PATH,
    METRIC_TOLERANCES,
    PRIMARY_CLOUD_THRESHOLD,
    QUICKLOOK_VERSION,
    RASTER_DIR,
    REPORT_JSON,
    REPORT_MARKDOWN,
    REVIEW_UPLOAD_DIR,
    EventExport,
    Level2MetricMismatch,
    Level2ValidationError,
    QueryTracker,
    _format_timestamp,
    _hash_file,
    _relative,
    _safe_id,
    _write_json_atomic,
    build_level2_report_markdown,
    compare_protected_snapshots,
    compose_level2_panel,
    compose_level2_temporal_sheet,
    compute_global_false_color_stretch,
    export_event_level2,
    level2_visual_snapshot,
    load_dnbr_inputs,
    preflight_git,
    protected_snapshot,
    read_utf8_csv,
    write_level2_manifest,
)


ACTIVE_MANIFEST = "outputs/manifests/firepa_active_bundle_2026-07-21.json"
PILOT_EVENTS = "data/processed/sentinel2_observability_pilot_events.csv"
MEMBERSHIP = "data/processed/firms_cocle_2025_event_membership.csv"
EVENTS = "data/processed/firms_cocle_2025_events_provisional.csv"
SELECTION = "outputs/sentinel2_event_pair_selection.csv"
SCENE_INVENTORY = "data/interim/sentinel2_scene_inventory.csv"
AOI_INVENTORY = "data/interim/sentinel2_aoi_inventory.csv"
METRICS = "data/interim/sentinel2_dnbr_event_metrics.csv"


_SECRET_RE = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)
_PROJECT_RE = re.compile(r"(?i)(\bprojects/)([A-Za-z0-9._-]+)")
_PROJECT_ASSIGNMENT_RE = re.compile(
    r"(?i)(\bproject(?:[_ -]?id)?\b\s*[:=]\s*)([A-Za-z0-9._-]+)"
)


def _path(value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else ROOT / candidate


def _safe_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    project = os.environ.get("EARTH_ENGINE_PROJECT", "")
    if project:
        text = text.replace(project, "<PROJECT_REDACTED>")
    text = _PROJECT_RE.sub(r"\1<PROJECT_REDACTED>", text)
    text = _PROJECT_ASSIGNMENT_RE.sub(r"\1<PROJECT_REDACTED>", text)
    text = _SECRET_RE.sub(r"\1<SECRET_REDACTED>", text)
    return text


def _error_record(event_id: str, exc: BaseException) -> dict[str, Any]:
    diagnostics = exception_diagnostics(exc)
    return {
        "event_id": event_id,
        "error_type": diagnostics.get("error_type") or type(exc).__name__,
        "message": _safe_error(diagnostics.get("error_message") or exc),
        "details": {
            key: value
            for key, value in diagnostics.items()
            if key not in {"error_message", "event_id"} and value not in (None, "")
        },
    }


def _metric_rows(path: Path, event_ids: Sequence[str]) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_utf8_csv(path)
    required = {
        "event_id",
        "analysis_mode",
        "cloud_threshold",
        "dnbr_median",
        "dnbr_p90",
        "area_ha_dnbr_gt_010",
        "area_ha_dnbr_gt_020",
        "area_ha_dnbr_gt_030",
        "area_ha_dnbr_gt_040",
        "valid_overlap_fraction",
        "common_valid_pixel_count",
    }
    if not rows or not required.issubset(rows[0]):
        missing = sorted(required - set(rows[0] if rows else {}))
        raise Level2ValidationError(f"Frozen metrics missing columns: {', '.join(missing)}")
    selected: dict[tuple[str, str], dict[str, str]] = {}
    requested = set(event_ids)
    for row in rows:
        event_id = str(row.get("event_id") or "")
        mode = str(row.get("analysis_mode") or "")
        try:
            cloud = float(row.get("cloud_threshold") or "nan")
        except ValueError:
            continue
        if event_id in requested and mode in {"selected_pair", "window_median"} and abs(cloud - PRIMARY_CLOUD_THRESHOLD) < 1e-9:
            key = (event_id, mode)
            if key in selected:
                raise Level2ValidationError(f"Duplicate frozen metric row: {event_id}/{mode}/0.50")
            selected[key] = dict(row)
    missing_keys = [
        f"{event_id}/{mode}"
        for event_id in event_ids
        for mode in ("selected_pair", "window_median")
        if (event_id, mode) not in selected
    ]
    if missing_keys:
        raise Level2ValidationError("Frozen metric rows missing: " + ", ".join(missing_keys))
    return selected


def _event_summary(
    event_export: EventExport,
    *,
    event_input: Any,
    root: Path,
    panel_paths: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "event_id": event_export.event_id,
        "status": "generated",
        "policy_path": event_input.policy_path,
        "selected_combination_id": event_input.selected_combination_id,
        "scene_ids": {"pre": event_input.pre_scene_id, "post": event_input.post_scene_id},
        "dates_utc": {
            "pre": _format_timestamp(event_input.pre_scene.get("acquisition_timestamp_utc")),
            "post": _format_timestamp(event_input.post_scene.get("acquisition_timestamp_utc")),
        },
        "raster_dir": _relative(next(iter(event_export.raster_paths.values())).parent, root),
        "raster_count_selected_pair": len(event_export.raster_paths),
        "raster_count_window_median": (
            len(json.loads(event_export.export_metadata_path.read_text(encoding="utf-8"))["window_median"]["rasters"])
            if event_export.window_available
            else 0
        ),
        "selected_pair_panel": _relative(panel_paths["selected_pair"], root),
        "temporal_sheet": _relative(panel_paths["temporal"], root),
        "selected_pair_panel_sha256": _hash_file(panel_paths["selected_pair"]),
        "temporal_sheet_sha256": _hash_file(panel_paths["temporal"]),
        "selected_pair_metric_reconciliation": dict(event_export.selected_comparison),
        "window_median_metric_reconciliation": (
            None if event_export.window_comparison is None else dict(event_export.window_comparison)
        ),
        "window_median_status": {
            "available": event_export.window_available,
            "reason": event_export.window_reason,
            "label": "numeric GeoTIFF" if event_export.window_available else "metrics only",
        },
        "export_metadata": _relative(event_export.export_metadata_path, root),
        "raster_paths": {
            key: _relative(path, root) for key, path in sorted(event_export.raster_paths.items())
        },
        "no_labels_or_ground_truth": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export FirePA Level 2 multispectral evidence for seven frozen events.")
    parser.add_argument("--pilot-events", default=PILOT_EVENTS)
    parser.add_argument("--membership", default=MEMBERSHIP)
    parser.add_argument("--events", default=EVENTS)
    parser.add_argument("--selection", default=SELECTION)
    parser.add_argument("--scene-inventory", default=SCENE_INVENTORY)
    parser.add_argument("--aoi-inventory", default=AOI_INVENTORY)
    parser.add_argument("--metrics", default=METRICS)
    parser.add_argument(
        "--event-id",
        action="append",
        dest="event_ids",
        help="Optional repeatable subset for a controlled diagnostic run; default is exactly the seven calibration events.",
    )
    return parser


def _write_panels(
    event_export: EventExport,
    *,
    event_input: Any,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any],
    stretch: Mapping[str, Any],
    root: Path,
) -> dict[str, Path]:
    safe = _safe_id(event_export.event_id)
    figure_dir = root / FIGURE_DIR
    review_dir = root / REVIEW_UPLOAD_DIR
    panel_name = f"{safe}_selected_pair_cs050_level2_panel.png"
    temporal_name = f"{safe}_temporal_robustness_level2.png"
    panel_payload = compose_level2_panel(
        event_input=event_input,
        selected_metrics=selected_metrics,
        raster_paths=event_export.raster_paths,
        stretch=stretch,
        root=root,
    )
    # The comparison sheet receives the frozen row plus local metrics and,
    # when available, the separately exported window rasters.
    metadata_path = event_export.export_metadata_path
    sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
    window_rasters = sidecar.get("window_median", {}).get("rasters", {})
    window_paths = None
    if event_export.window_available and window_rasters:
        window_paths = {
            key: root / str(value["path"])
            for key, value in window_rasters.items()
        }
    temporal_payload = compose_level2_temporal_sheet(
        event_input=event_input,
        selected_metrics=selected_metrics,
        window_metrics=window_metrics,
        selected_local_metrics=event_export.selected_local_metrics,
        window_local_metrics=event_export.window_local_metrics,
        selected_raster_paths=event_export.raster_paths,
        window_raster_paths=window_paths,
        window_available=event_export.window_available,
        window_reason=event_export.window_reason,
        root=root,
    )
    panel_path = figure_dir / panel_name
    temporal_path = figure_dir / temporal_name
    review_panel_path = review_dir / panel_name
    review_temporal_path = review_dir / temporal_name
    for path, payload in (
        (panel_path, panel_payload),
        (temporal_path, temporal_payload),
        (review_panel_path, panel_payload),
        (review_temporal_path, temporal_payload),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return {"selected_pair": panel_path, "temporal": temporal_path}


def _attach_global_stretch(root: Path, event_exports: Sequence[EventExport], stretch: Mapping[str, Any]) -> None:
    for event_export in event_exports:
        path = event_export.export_metadata_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["global_false_color_stretch"] = dict(stretch)
        payload["global_false_color_stretch_scope"] = "14 selected-pair false-color rasters across seven calibration events"
        _write_json_atomic(path, payload)


def _report_payload(
    *,
    git_start: Mapping[str, Any],
    git_end: Mapping[str, Any],
    event_ids: Sequence[str],
    event_results: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    tracker: QueryTracker,
    smoke: Mapping[str, Any] | None,
    stretch: Mapping[str, Any] | None,
    protected_check: Mapping[str, Any],
    scientific_check: Mapping[str, Any],
    visual_before: Mapping[str, Any],
    visual_after: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    window_count = sum(
        1
        for result in event_results
        if result.get("window_median_status", {}).get("available")
    )
    metric_failures = [
        result["event_id"]
        for result in event_results
        if result.get("selected_pair_metric_reconciliation", {}).get("status") != "pass"
    ]
    return {
        "stage": "sentinel2_dnbr_quicklook_level2",
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": "fuegopa-sentinel2-dnbr-v3",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "requested_event_ids": list(event_ids),
        "requested_event_count": len(event_ids),
        "generated_count": len(event_results),
        "failed_count": len(errors),
        "results": [dict(result) for result in event_results],
        "earth_engine": {
            "initialized": smoke is not None,
            "authentication_called": False,
            "project_id_stored": False,
            "smoke_test": None if smoke is None else dict(smoke),
        },
        "earth_engine_queries": {
            "smoke": tracker.smoke_queries,
            "download": tracker.download_queries,
            "geometry": tracker.geometry_queries,
            "total": tracker.total_queries,
        },
        "artifacts": {
            "selected_pair_panel_count": len(event_results),
            "temporal_sheet_count": len(event_results),
            "selected_pair_raster_count": len(event_results) * 9,
            "window_median_event_count": window_count,
            "window_median_label": "numeric GeoTIFF when available; metrics only when deferred",
        },
        "global_false_color_stretch": None if stretch is None else dict(stretch),
        "metric_tolerances": dict(METRIC_TOLERANCES),
        "metric_reconciliation": {
            "status": "pass" if not metric_failures and len(event_results) == len(event_ids) else "failed_or_incomplete",
            "failed_event_ids": metric_failures,
            "selected_pair_checks": sum(
                len(result.get("selected_pair_metric_reconciliation", {}).get("checks", []))
                for result in event_results
            ),
            "window_checks": sum(
                len((result.get("window_median_metric_reconciliation") or {}).get("checks", []))
                for result in event_results
            ),
        },
        "protected_integrity": {
            "status": "pass" if protected_check.get("all_unchanged") else "failed",
            **dict(protected_check),
            "scientific_bundle": dict(scientific_check),
        },
        "visual_snapshot": {
            "before": dict(visual_before),
            "after": dict(visual_after),
        },
        "errors": [dict(error) for error in errors],
        "scope": {
            "cohort_changed": False,
            "event_selection_changed": False,
            "selected_scene_ids_changed": False,
            "policy_changed": False,
            "aoi_changed": False,
            "scale_changed": False,
            "formulas_changed": False,
            "existing_metrics_changed": False,
            "review_queue_changed": False,
            "significant_burn_labels_created": False,
            "data_2026_used": False,
            "models_trained": False,
            "sample_expansion": False,
            "full_scene_downloads": False,
            "push_performed": False,
        },
        "manifest": dict(manifest),
        "git": {
            "start_branch": git_start.get("branch", ""),
            "start_head": git_start.get("head", ""),
            "start_status": git_start.get("status_porcelain", ""),
            "end_status": git_end.get("status_porcelain", ""),
        },
    }


def run_batch(args: argparse.Namespace) -> int:
    event_ids = tuple(args.event_ids or CALIBRATION_EVENT_IDS)
    unknown = sorted(set(event_ids) - set(CALIBRATION_EVENT_IDS))
    if unknown:
        raise Level2ValidationError("Event IDs outside the frozen calibration set: " + ", ".join(unknown))
    if not event_ids:
        raise Level2ValidationError("At least one calibration event is required")

    git_start = preflight_git(ROOT)
    visual_before = level2_visual_snapshot(ROOT)
    protected_before = protected_snapshot(ROOT)
    active_manifest = _path(ACTIVE_MANIFEST)
    scientific_before = scientific_bundle_integrity(active_manifest, root=ROOT) if active_manifest.is_file() else {}
    inputs = load_dnbr_inputs(
        pilot_path=_path(args.pilot_events),
        events_path=_path(args.events),
        membership_path=_path(args.membership),
        selection_path=_path(args.selection),
        scene_inventory_path=_path(args.scene_inventory),
        aoi_inventory_path=_path(args.aoi_inventory),
    )
    by_event = {item.event_id: item for item in inputs.processable}
    missing_inputs = sorted(set(event_ids) - set(by_event))
    if missing_inputs:
        raise Level2ValidationError("Calibration events not processable under frozen inputs: " + ", ".join(missing_inputs))
    metrics = _metric_rows(_path(args.metrics), event_ids)

    raster_root = ROOT / RASTER_DIR
    tracker = QueryTracker()
    event_exports: list[EventExport] = []
    event_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    smoke: Mapping[str, Any] | None = None
    stretch: Mapping[str, Any] | None = None
    try:
        client = initialize_earth_engine()
        smoke = smoke_test(client)
        tracker.smoke_queries = 2
        for event_id in event_ids:
            event_input = by_event[event_id]
            try:
                event_export = export_event_level2(
                    client,
                    event_input,
                    selected_metrics=metrics[(event_id, "selected_pair")],
                    window_metrics=metrics[(event_id, "window_median")],
                    raster_root=raster_root,
                    tracker=tracker,
                    root=ROOT,
                )
                event_exports.append(event_export)
            except Exception as exc:
                errors.append(_error_record(event_id, exc))
                # A metric mismatch is a hard boundary: do not create panels or
                # continue downloading another event after the mismatch.
                break
        if event_exports and len(event_exports) == len(event_ids) and not errors:
            false_color_paths = [
                path
                for event_export in event_exports
                for path in (
                    ROOT / str(json.loads(event_export.export_metadata_path.read_text(encoding="utf-8"))["selected_pair"]["rasters"]["false_color_pre"]["path"]),
                    ROOT / str(json.loads(event_export.export_metadata_path.read_text(encoding="utf-8"))["selected_pair"]["rasters"]["false_color_post"]["path"]),
                )
            ]
            stretch = compute_global_false_color_stretch(false_color_paths)
            _attach_global_stretch(ROOT, event_exports, stretch)
            for event_export in event_exports:
                panel_paths = _write_panels(
                    event_export,
                    event_input=by_event[event_export.event_id],
                    selected_metrics=metrics[(event_export.event_id, "selected_pair")],
                    window_metrics=metrics[(event_export.event_id, "window_median")],
                    stretch=stretch,
                    root=ROOT,
                )
                event_results.append(
                    _event_summary(
                        event_export,
                        event_input=by_event[event_export.event_id],
                        root=ROOT,
                        panel_paths=panel_paths,
                    )
                )
    except Exception as exc:
        errors.append(_error_record("batch", exc))

    protected_after = protected_snapshot(ROOT)
    protected_check = compare_protected_snapshots(protected_before, protected_after)
    scientific_after = scientific_bundle_integrity(active_manifest, root=ROOT) if active_manifest.is_file() else {}
    scientific_check = {
        "before": scientific_before,
        "after": scientific_after,
        "scientific_outputs_unchanged": bool(scientific_after.get("scientific_outputs_unchanged", True)),
        "v1_visual_outputs_unchanged": bool(scientific_after.get("v1_visual_outputs_unchanged", True)),
        "v2_and_v2_1_protected": bool(protected_check.get("all_unchanged")),
    }
    manifest = write_level2_manifest(ROOT)
    visual_after = level2_visual_snapshot(ROOT)
    git_end = preflight_git(ROOT)
    report = _report_payload(
        git_start=git_start,
        git_end=git_end,
        event_ids=event_ids,
        event_results=event_results,
        errors=errors,
        tracker=tracker,
        smoke=smoke,
        stretch=stretch,
        protected_check=protected_check,
        scientific_check=scientific_check,
        visual_before=visual_before,
        visual_after=visual_after,
        manifest=manifest,
    )
    _write_json_atomic(ROOT / REPORT_JSON, report)
    (ROOT / REPORT_MARKDOWN).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / REPORT_MARKDOWN).write_text(build_level2_report_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["generated_count"] == report["requested_event_count"] and not errors and protected_check.get("all_unchanged") else 1


def main() -> int:
    try:
        return run_batch(build_parser().parse_args())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "message": _safe_error(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
