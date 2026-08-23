"""Local-only visual and metadata correction for Sentinel-2 dNBR Quicklook v2.

Quicklook v2.1 intentionally lives beside v2.  It reads the existing v1 PNG
bundle and local CSV/scene-inventory metadata, then writes a new output tree.
It does not recompute dNBR, change scene selection, query Earth Engine, or
write any scientific artifact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import dnbr_quicklook_v2 as _v2
from .dnbr_quicklook import (
    DNBR_VIS_MAX,
    DNBR_VIS_MIN,
    PANEL_KEYS,
    RGBImage,
    QuicklookValidationError,
    decode_png_details,
    encode_png,
    validate_thumbnail_sources,
)


QUICKLOOK_VERSION = "fuegopa-dnbr-quicklook-v2.1"
PIPELINE_VERSION = _v2.PIPELINE_VERSION
PANEL_WIDTH = _v2.PANEL_WIDTH
PANEL_HEIGHT = _v2.PANEL_HEIGHT
COMPARISON_WIDTH = _v2.COMPARISON_WIDTH
COMPARISON_HEIGHT = _v2.COMPARISON_HEIGHT
ANALYSIS_SCALE_M = _v2.ANALYSIS_SCALE_M
AOI_ID = _v2.AOI_ID
AOI_BUFFER_M = _v2.AOI_BUFFER_M
PRIMARY_CLOUD_THRESHOLD = _v2.PRIMARY_CLOUD_THRESHOLD
NBR_VIS_MIN = _v2.NBR_VIS_MIN
NBR_VIS_MAX = _v2.NBR_VIS_MAX
DIAGNOSTIC_UNAVAILABLE_NOTE = _v2.DIAGNOSTIC_UNAVAILABLE_NOTE
FALSE_COLOR_DEFERRED_NOTE = _v2.FALSE_COLOR_DEFERRED_NOTE
DESCRIPTIVE_WARNING = _v2.DESCRIPTIVE_WARNING
RESAMPLING_POLICY = dict(_v2.RESAMPLING_POLICY)
CALIBRATION_EVENT_IDS = _v2.CALIBRATION_EVENT_IDS

# These colors are the palette emitted by the v1 mask renderer and its local
# overlays.  The gray color is deliberately documented as spectral-only.
MASK_INVALID = (192, 38, 211)  # #c026d3, mask value 0 after unmask(0)
MASK_VALID = (15, 118, 110)  # #0f766e, mask value 1
AOI_BOUNDARY = (255, 209, 102)  # #ffd166
FIRMS_DETECTION = (0, 229, 255)  # #00e5ff
SPECTRAL_NODATA = (148, 163, 184)  # #94a3b8

POSITIVE_DNBR_NOTE = "Positive dNBR: spectral vegetation loss"
NEGATIVE_DNBR_NOTE = "Negative dNBR: spectral vegetation gain"
SPECTRAL_NODATA_NOTE = "Gray #94a3b8: nodata/background in spectral layers only; not a mask class"
MASK_SEMANTICS = (
    "Mask source is categorical: value 0 is invalid/unavailable after unmask(0), "
    "value 1 is valid; yellow and cyan are overlays, not mask categories."
)
WINDOW_METADATA_AVAILABLE = "COMPOSITE WINDOW METADATA: available locally"
WINDOW_METADATA_UNAVAILABLE = "COMPOSITE WINDOW METADATA: unavailable locally"
WINDOW_METRICS_ONLY = "metrics only; no local window_median raster is available"

MASK_LEGEND = (
    {
        "label": "INVALID MASK",
        "color": "#c026d3",
        "meaning": "mask value 0 / unmask(0); invalid or unavailable mask pixels",
    },
    {
        "label": "VALID MASK",
        "color": "#0f766e",
        "meaning": "mask value 1",
    },
    {
        "label": "AOI BOUNDARY",
        "color": "#ffd166",
        "meaning": "AOI boundary overlay",
    },
    {
        "label": "FIRMS DETECTION",
        "color": "#00e5ff",
        "meaning": "FIRMS detection overlay",
    },
    {
        "label": "GRAY: SPECTRAL NODATA/BG ONLY",
        "color": "#94a3b8",
        "meaning": "nodata/background in RGB/NBR/dNBR layers; not a mask class",
    },
)
# Only the first four colors occur in the mask source/overlay imagery.  Gray
# is intentionally kept out of this tuple because it belongs to spectral
# nodata/background rendering, not to the mask categorical palette.
MASK_SOURCE_CATEGORICAL_COLORS = tuple(item["color"] for item in MASK_LEGEND[:4])

# Explicit paths and output trees protected by the v2.1 run.  The snapshot is
# intentionally independent from the pre-v2 manifest so it also catches an
# accidental overwrite of an existing v1/v2 review artifact.
PROTECTED_FILE_PATHS = (
    "data/interim/sentinel2_dnbr_event_metrics.csv",
    "data/interim/sentinel2_dnbr_errors.csv",
    "data/interim/sentinel2_dnbr_checkpoint.json",
    "data/interim/sentinel2_scene_inventory.csv",
    "data/interim/sentinel2_aoi_inventory.csv",
    "data/interim/sentinel2_observability.csv",
    "data/interim/sentinel2_observability_checkpoint.json",
    "outputs/sentinel2_dnbr_sensitivity.csv",
    "outputs/sentinel2_dnbr_review_queue.csv",
    "outputs/sentinel2_dnbr_report.json",
    "outputs/sentinel2_dnbr_report.md",
    "outputs/sentinel2_event_pair_selection.csv",
    "outputs/sentinel2_policy_decision.csv",
    "outputs/sentinel2_policy_decision.md",
    "outputs/quicklook_v2_report.json",
    "outputs/quicklook_v2_report.md",
    "outputs/firepa_quicklook_v2_review.zip",
)
PROTECTED_DIRECTORY_PATHS = (
    "data/interim/sentinel2_dnbr_cache",
    "outputs/figures/sentinel2_dnbr/events",
    "outputs/figures/sentinel2_dnbr_v2",
    "outputs/review_upload_v2",
)

# Reuse the stable v2 drawing primitives without changing the v2 module or
# its byte-identical outputs.
_renderer = _v2._renderer
_text = _v2._text
_fill_rect = _v2._fill_rect
_stroke_rect = _v2._stroke_rect
_draw_firms_overlay = _v2._draw_firms_overlay
_draw_colorbar = _v2._draw_colorbar
_tile_source = _v2._tile_source
_format_float = _v2._format_float
_metric_float = _v2._metric_float
_format_timestamp = _v2._format_timestamp
_event_timestamp = _v2._event_timestamp
_comparison_status = _v2._comparison_status
_difference = _v2._difference
_hash_index = _v2._hash_index
_relative = _v2._relative
source_paths = _v2.source_paths
resolve_system_font = _v2.resolve_system_font
scientific_bundle_integrity = _v2.scientific_bundle_integrity


def _parse_utc(value: Any) -> datetime | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: Any) -> str | None:
    parsed = _parse_utc(value)
    return None if parsed is None else parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def _scene_id(row: Mapping[str, Any]) -> str:
    for key in ("sentinel2_scene_id", "scene_id", "system_index"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _numeric_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _window_bounds(rows: Sequence[Mapping[str, Any]]) -> tuple[str | None, str | None]:
    starts = [parsed for parsed in (_parse_utc(row.get("window_start_utc")) for row in rows) if parsed]
    ends = [parsed for parsed in (_parse_utc(row.get("window_end_utc")) for row in rows) if parsed]
    start = min(starts).strftime("%Y-%m-%dT%H:%M:%SZ") if starts else None
    end = max(ends).strftime("%Y-%m-%dT%H:%M:%SZ") if ends else None
    return start, end


def _window_side(
    candidates: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any] | None,
    side: str,
) -> dict[str, Any]:
    metrics = metrics or {}
    ids = _split_ids(metrics.get(f"{side}_scene_ids_used"))
    if not ids:
        ids = [_scene_id(row) for row in candidates if _scene_id(row)]
    count = _numeric_int(metrics.get(f"{side}_scene_count_used"))
    if count is None:
        count = len(ids)
    start, end = _window_bounds(candidates)
    start = _format_utc(metrics.get(f"{side}_window_start_utc")) or start
    end = _format_utc(metrics.get(f"{side}_window_end_utc")) or end
    return {
        "window_start_utc": start,
        "window_end_utc": end,
        "scene_count_used": count,
        "scene_ids_used": ids,
    }


def _unavailable_window_metadata(reason: str = "No local scene-inventory window boundaries were supplied") -> dict[str, Any]:
    return {
        "available_locally": False,
        "source": "local_scene_inventory_and_metrics",
        "availability_reason": reason,
        "pre_window_start_utc": None,
        "pre_window_end_utc": None,
        "post_window_start_utc": None,
        "post_window_end_utc": None,
        "pre_scene_count_used": None,
        "post_scene_count_used": None,
        "pre_scene_ids_used": "",
        "post_scene_ids_used": "",
        "pre_scene_ids": [],
        "post_scene_ids": [],
        "display": WINDOW_METADATA_UNAVAILABLE,
    }


def _window_composite_metadata(event_input: Any, window_metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    """Describe the local composite windows without inventing raster output."""

    if event_input is None:
        return _unavailable_window_metadata("No DnbrEventInput was supplied")
    pre = _window_side(tuple(getattr(event_input, "pre_candidates", ()) or ()), window_metrics, "pre")
    post = _window_side(tuple(getattr(event_input, "post_candidates", ()) or ()), window_metrics, "post")
    available = bool(
        pre["window_start_utc"]
        and pre["window_end_utc"]
        and post["window_start_utc"]
        and post["window_end_utc"]
        and pre["scene_count_used"] is not None
        and post["scene_count_used"] is not None
        and pre["scene_ids_used"]
        and post["scene_ids_used"]
    )
    if not available:
        return _unavailable_window_metadata(
            "Local candidates or window_median scene metadata are incomplete"
        )
    return {
        "available_locally": True,
        "source": "local_scene_inventory_and_metrics",
        "availability_reason": "Window boundaries, counts and scene IDs came from local candidates/metrics",
        "pre_window_start_utc": pre["window_start_utc"],
        "pre_window_end_utc": pre["window_end_utc"],
        "post_window_start_utc": post["window_start_utc"],
        "post_window_end_utc": post["window_end_utc"],
        "pre_scene_count_used": pre["scene_count_used"],
        "post_scene_count_used": post["scene_count_used"],
        "pre_scene_ids_used": ";".join(pre["scene_ids_used"]),
        "post_scene_ids_used": ";".join(post["scene_ids_used"]),
        "pre_scene_ids": list(pre["scene_ids_used"]),
        "post_scene_ids": list(post["scene_ids_used"]),
        "display": WINDOW_METADATA_AVAILABLE,
    }


def _event_summary(
    event_input: Any,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event = event_input.event
    event_start = _event_timestamp(event, "start_timestamp_utc")
    event_end = _event_timestamp(event, "end_timestamp_utc")
    pre_text = _format_timestamp(selected_metrics.get("pre_timestamp_utc"))
    post_text = _format_timestamp(selected_metrics.get("post_timestamp_utc"))
    pre = _parse_utc(pre_text)
    post = _parse_utc(post_text)
    pre_lead_days = None if pre is None else (event_start - pre).total_seconds() / 86400
    post_lag_days = None if post is None else (post - event_end).total_seconds() / 86400
    overlap = _metric_float(selected_metrics, "valid_overlap_fraction")
    window_metadata = _window_composite_metadata(event_input, window_metrics)
    return {
        "event_id": event_input.event_id,
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "analysis_mode": "selected_pair",
        "event_start_utc": event_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_end_utc": event_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pre_timestamp_utc": pre_text,
        "post_timestamp_utc": post_text,
        # Retained as machine-readable compatibility fields; all display text
        # uses PRE LEAD and POST LAG to make the temporal direction explicit.
        "days_event_to_pre": pre_lead_days,
        "days_event_to_post": post_lag_days,
        "pre_lead_days": pre_lead_days,
        "post_lag_days": post_lag_days,
        "temporal_semantics": {
            "pre_label": "PRE LEAD",
            "post_label": "POST LAG",
            "pre_definition": "days from selected pre scene acquisition to event start",
            "post_definition": "days from event end to selected post scene acquisition",
        },
        "policy_path": str(selected_metrics.get("policy_path") or event_input.policy_path),
        "selected_combination_id": str(
            selected_metrics.get("selected_combination_id") or event_input.selected_combination_id
        ),
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "cloud_score_plus_threshold": PRIMARY_CLOUD_THRESHOLD,
        "valid_overlap_fraction": overlap,
        "valid_overlap_percent": None if overlap is None else overlap * 100,
        "dnbr_median": _metric_float(selected_metrics, "dnbr_median"),
        "dnbr_p90": _metric_float(selected_metrics, "dnbr_p90"),
        "area_ha_dnbr_gt_020": _metric_float(selected_metrics, "area_ha_dnbr_gt_020"),
        "metric_status": str(selected_metrics.get("metric_status") or ""),
        "diagnostic_dnbr_range": None,
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "false_color_swir": "deferred_level_2",
        "false_color_note": FALSE_COLOR_DEFERRED_NOTE,
        "positive_dnbr_note": POSITIVE_DNBR_NOTE,
        "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        "interpretation_boundary": "descriptive_spectral_change_only; no fire confirmation or severity label",
        "window_composite_metadata": window_metadata,
        "scientific_outputs_modified": False,
        "earth_engine_queries_made": False,
        "source_raster_numeric_data": False,
        "warning": DESCRIPTIVE_WARNING,
        "resampling_policy": dict(RESAMPLING_POLICY),
    }


def _hex_color(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def _draw_mask_legend(renderer: Any, canvas: RGBImage, left: int, top: int) -> None:
    """Draw all source mask/overlay colors, including the spectral-only note."""

    coordinates = (
        (left + 24, top, MASK_LEGEND[0]),
        (left + 315, top, MASK_LEGEND[1]),
        (left + 24, top + 34, MASK_LEGEND[2]),
        (left + 315, top + 34, MASK_LEGEND[3]),
        (left + 24, top + 68, MASK_LEGEND[4]),
    )
    for item_left, item_top, item in coordinates:
        color = _hex_color(item["color"])
        _fill_rect(canvas, item_left, item_top + 3, 22, 18, color)
        _stroke_rect(canvas, item_left, item_top + 3, 22, 18, _v2._BORDER)
        _text(renderer, canvas, item["label"], item_left + 30, item_top, 14, _v2._MUTED, True)


def compose_panel_v2_1(
    thumbnails: Mapping[str, bytes],
    metadata: Mapping[str, Any],
    event_input: Any | None = None,
) -> bytes:
    """Compose the corrected v2.1 panel from the existing six PNG sources."""

    font, renderer = _renderer()
    details, source_stats = validate_thumbnail_sources(thumbnails)
    canvas = RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, _v2._BACKGROUND)
    event_id = str(metadata.get("event_id", ""))
    values = _v2._panel_metadata_text(metadata)
    _text(renderer, canvas, event_id, 42, 28, 44, _v2._INK, True)
    _text(
        renderer,
        canvas,
        f"{QUICKLOOK_VERSION}  |  MODE: selected_pair  |  LOCAL ARTIFACT REBUILD",
        44,
        86,
        24,
        _v2._ACCENT_DARK,
        True,
    )
    _text(
        renderer,
        canvas,
        f"EVENT UTC: {metadata.get('event_start_utc', '')} to {metadata.get('event_end_utc', '')}   PRE SCENE: {metadata.get('pre_timestamp_utc', '')}   POST SCENE: {metadata.get('post_timestamp_utc', '')}",
        44,
        119,
        20,
        _v2._MUTED,
    )
    _text(
        renderer,
        canvas,
        f"PRE LEAD: {_format_float(metadata.get('pre_lead_days', metadata.get('days_event_to_pre')), 2)} d   POST LAG: {_format_float(metadata.get('post_lag_days', metadata.get('days_event_to_post')), 2)} d   POLICY: {metadata.get('policy_path', '')}   AOI: b0500 / 500 m   SCALE: 20 m   CS+: >= 0.50",
        44,
        148,
        20,
        _v2._MUTED,
    )
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}  |  {NEGATIVE_DNBR_NOTE}", 44, 178, 17, _v2._ACCENT_DARK, True)

    tile_width, tile_height = 632, 500
    tile_gap_x, tile_gap_y = 22, 22
    left_margin, top_margin = 36, 210
    image_width, image_height = 534, 394
    valid_fraction = metadata.get("valid_overlap_fraction")
    compact_mask = valid_fraction is not None and float(valid_fraction) >= 0.98
    labels = {
        "rgb_pre": "RGB PRE  |  RGB presentation",
        "rgb_post": "RGB POST  |  RGB presentation",
        "nbr_pre": "NBR PRE  |  fixed visual range [-1, 1]",
        "nbr_post": "NBR POST  |  fixed visual range [-1, 1]",
        "dnbr": "dNBR  |  fixed visual range [-1, 1]  |  descriptive sign",
        "mask": "COMMON VALID MASK / OVERLAYS  |  nearest-neighbor",
    }
    for index, key in enumerate(PANEL_KEYS):
        column, row = index % 3, index // 3
        left = left_margin + column * (tile_width + tile_gap_x)
        top = top_margin + row * (tile_height + tile_gap_y)
        _fill_rect(canvas, left, top, tile_width, tile_height, _v2._WHITE)
        _stroke_rect(canvas, left, top, tile_width, tile_height, _v2._BORDER, 2)
        _text(renderer, canvas, labels[key], left + 18, top + 17, 22, _v2._INK, True)
        if key == "mask" and compact_mask:
            local_width, local_height = 300, 220
            image_left = left + 26
            image_top = top + 108
            _fill_rect(canvas, image_left - 8, image_top - 8, local_width + 16, local_height + 16, (235, 240, 242))
            _stroke_rect(canvas, image_left - 8, image_top - 8, local_width + 16, local_height + 16, _v2._BORDER)
            _text(renderer, canvas, "COMPACT INSET: >= 98% VALID", left + 360, top + 148, 18, _v2._VALID, True)
            legend_top = top + 350
        elif key == "mask":
            # Reserve the lower part of this tile for the complete categorical
            # legend instead of hiding invalid pixels behind a gray swatch.
            local_width, local_height = image_width, 280
            image_left = left + 20
            image_top = top + 62
            legend_top = top + 366
        else:
            local_width, local_height = image_width, image_height
            image_left = left + 20
            image_top = top + 62
            legend_top = None
        tile = _tile_source(details[key], key, local_width, local_height)
        canvas.paste(tile, image_left, image_top)
        if key in {"rgb_pre", "rgb_post"} and event_input is not None:
            _draw_firms_overlay(canvas, event_input, image_left, image_top, local_width, local_height)
            if key == "rgb_post":
                _text(renderer, canvas, "FIRMS halo + centroid   |   scale bar: 500 m", image_left + 10, image_top + local_height - 28, 17, _v2._WHITE, True)
        if key in {"nbr_pre", "nbr_post", "dnbr"}:
            _draw_colorbar(
                renderer,
                canvas,
                left + 568,
                image_top + 30,
                local_height - 40,
                NBR_VIS_MIN if key != "dnbr" else DNBR_VIS_MIN,
                NBR_VIS_MAX if key != "dnbr" else DNBR_VIS_MAX,
                "NBR" if key != "dnbr" else "dNBR",
            )
        if key == "mask" and legend_top is not None:
            _draw_mask_legend(renderer, canvas, left, legend_top)

    metric_top = 1268
    metric_width = 365
    metric_gap = 12
    metric_labels = (
        ("VALID OVERLAP", values["overlap"], _v2._ACCENT),
        ("dNBR MEDIAN", values["dnbr_median"], _v2._ACCENT_DARK),
        ("dNBR P90", values["dnbr_p90"], _v2._ACCENT_DARK),
        ("AREA > 0.20", f"{values['area']} ha", _v2._ACCENT_DARK),
        ("METRIC STATUS", str(metadata.get("metric_status") or "n/a"), _v2._ACCENT),
    )
    for index, (label, value, color) in enumerate(metric_labels):
        left = 36 + index * (metric_width + metric_gap)
        _fill_rect(canvas, left, metric_top, metric_width, 74, _v2._WHITE)
        _stroke_rect(canvas, left, metric_top, metric_width, 74, _v2._BORDER)
        _text(renderer, canvas, label, left + 16, metric_top + 10, 16, _v2._MUTED, True)
        _text(renderer, canvas, value, left + 16, metric_top + 34, 27, color, True)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 42, 1364, 22, _v2._WARNING, True)
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}; {NEGATIVE_DNBR_NOTE}.", 42, 1392, 17, _v2._MUTED)
    _text(renderer, canvas, SPECTRAL_NODATA_NOTE, 42, 1416, 17, _v2._MUTED)
    metadata_payload = {
        **dict(metadata),
        "quicklook_version": QUICKLOOK_VERSION,
        "analysis_mode": "selected_pair",
        "font_path": str(font.path),
        "font_family": font.family,
        "font_distributed": False,
        "font_backend": font.backend,
        "panel_dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
        "final_format": "RGB",
        "alpha_scientific": False,
        "source_stats": source_stats,
        "diagnostic_dnbr_range": None,
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "descriptive_warning": DESCRIPTIVE_WARNING,
        "false_color_swir": "deferred_level_2",
        "false_color_note": FALSE_COLOR_DEFERRED_NOTE,
        "positive_dnbr_note": POSITIVE_DNBR_NOTE,
        "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        "mask_display": "compact_inset" if compact_mask else "full_panel",
        "mask_annotation": "COMPACT INSET: >= 98% VALID" if compact_mask else "FULL MASK PANEL: INVALID PIXELS REMAIN VISIBLE",
        "mask_source_palette": list(MASK_SOURCE_CATEGORICAL_COLORS),
        "mask_legend": [dict(item) for item in MASK_LEGEND],
        "mask_semantics": MASK_SEMANTICS,
        "spectral_nodata_note": SPECTRAL_NODATA_NOTE,
        "panel_display_contract": {
            "selected_pair_dates": f"PRE SCENE: {metadata.get('pre_timestamp_utc', '')}   POST SCENE: {metadata.get('post_timestamp_utc', '')}",
            "temporal_spacing": f"PRE LEAD: {_format_float(metadata.get('pre_lead_days', metadata.get('days_event_to_pre')), 2)} d   POST LAG: {_format_float(metadata.get('post_lag_days', metadata.get('days_event_to_post')), 2)} d",
        },
        "scale_bar_label": "500 m",
        "analysis_scale_label": "20 m",
        "nbr_range": [NBR_VIS_MIN, NBR_VIS_MAX],
        "dnbr_range": [DNBR_VIS_MIN, DNBR_VIS_MAX],
        "colorbar_ticks": {"NBR": [-1.0, 0.0, 1.0], "dNBR": [-1.0, 0.0, 1.0]},
        "source_raster_numeric_data": False,
        "scientific_outputs_modified": False,
    }
    return encode_png(canvas, metadata_payload)


def _window_display_lines(window_metadata: Mapping[str, Any]) -> tuple[str, ...]:
    if not window_metadata.get("available_locally"):
        return (WINDOW_METADATA_UNAVAILABLE, WINDOW_METRICS_ONLY)
    return (
        WINDOW_METADATA_AVAILABLE,
        f"PRE WINDOW: {window_metadata.get('pre_window_start_utc')} to {window_metadata.get('pre_window_end_utc')}",
        f"POST WINDOW: {window_metadata.get('post_window_start_utc')} to {window_metadata.get('post_window_end_utc')}",
        f"SCENES USED: PRE {window_metadata.get('pre_scene_count_used')} / POST {window_metadata.get('post_scene_count_used')}",
        "SCENE IDS: recorded in PNG metadata",
    )


def compose_temporal_comparison_sheet_v2_1(
    metadata: Mapping[str, Any],
    selected_metrics: Mapping[str, Any] | None,
    window_metrics: Mapping[str, Any] | None,
) -> bytes:
    """Compose a metrics-only sheet with truthful local window metadata."""

    font, renderer = _renderer()
    canvas = RGBImage.solid(COMPARISON_WIDTH, COMPARISON_HEIGHT, _v2._BACKGROUND)
    event_id = str(metadata.get("event_id", ""))
    _text(renderer, canvas, event_id, 48, 36, 44, _v2._INK, True)
    _text(
        renderer,
        canvas,
        f"{QUICKLOOK_VERSION}  |  TEMPORAL ROBUSTNESS  |  selected_pair vs window_median",
        50,
        96,
        24,
        _v2._ACCENT_DARK,
        True,
    )
    _text(
        renderer,
        canvas,
        "This sheet compares tabular metrics only. It does not link window_median to the selected_pair image.",
        50,
        132,
        22,
        _v2._MUTED,
    )
    _text(
        renderer,
        canvas,
        f"POLICY: {metadata.get('policy_path', '')}   COMBINATION: {metadata.get('selected_combination_id', '')}   CS+: >= 0.50   AOI: b0500 / 500 m   SCALE: 20 m",
        50,
        165,
        20,
        _v2._MUTED,
    )
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}  |  {NEGATIVE_DNBR_NOTE}", 50, 195, 18, _v2._ACCENT_DARK, True)

    window_metadata = dict(metadata.get("window_composite_metadata") or _unavailable_window_metadata())
    cards = (("SELECTED_PAIR", selected_metrics, 52, _v2._ACCENT), ("WINDOW_MEDIAN", window_metrics, 1050, _v2._ACCENT_DARK))
    card_width, card_height = 946, 710
    for title, row, left, color in cards:
        _fill_rect(canvas, left, 230, card_width, card_height, _v2._WHITE)
        _stroke_rect(canvas, left, 230, card_width, card_height, _v2._BORDER, 2)
        _fill_rect(canvas, left, 230, card_width, 80, color)
        _text(renderer, canvas, title, left + 26, 251, 28, _v2._WHITE, True)
        if row is None:
            _text(renderer, canvas, "No local metric row available", left + 28, 350, 26, _v2._WARNING, True)
            if title == "WINDOW_MEDIAN":
                for line_index, line in enumerate(_window_display_lines(window_metadata)):
                    line_color = _v2._WARNING if "unavailable" in line or line == WINDOW_METRICS_ONLY else _v2._MUTED
                    _text(renderer, canvas, line, left + 28, 400 + line_index * 27, 17, line_color, line_index == 0)
            else:
                _text(renderer, canvas, WINDOW_METRICS_ONLY, left + 28, 400, 18, _v2._MUTED)
            continue
        _text(
            renderer,
            canvas,
            f"STATUS: {row.get('metric_status', 'n/a')}   POLICY: {row.get('policy_path', metadata.get('policy_path', ''))}",
            left + 28,
            342,
            20,
            _v2._MUTED,
            True,
        )
        if title == "SELECTED_PAIR":
            _text(
                renderer,
                canvas,
                f"PRE SCENE: {_format_timestamp(row.get('pre_timestamp_utc'))}   POST SCENE: {_format_timestamp(row.get('post_timestamp_utc'))}",
                left + 28,
                374,
                19,
                _v2._MUTED,
            )
            metric_base = 438
        else:
            display_lines = _window_display_lines(window_metadata)
            for line_index, line in enumerate(display_lines):
                line_color = _v2._WARNING if "unavailable" in line or line == WINDOW_METRICS_ONLY else _v2._MUTED
                _text(renderer, canvas, line, left + 28, 374 + line_index * 27, 17, line_color, line_index == 0)
            metric_base = 520 if window_metadata.get("available_locally") else 465
        metrics = (
            ("dNBR median", _format_float(_metric_float(row, "dnbr_median"), 4)),
            ("dNBR p90", _format_float(_metric_float(row, "dnbr_p90"), 4)),
            ("area > 0.20", f"{_format_float(_metric_float(row, 'area_ha_dnbr_gt_020'), 3)} ha"),
            (
                "valid overlap",
                "n/a"
                if _metric_float(row, "valid_overlap_fraction") is None
                else f"{_metric_float(row, 'valid_overlap_fraction') * 100:.1f}%",
            ),
        )
        for index, (label, value) in enumerate(metrics):
            y = metric_base + index * 43
            _text(renderer, canvas, label.upper(), left + 28, y, 17, _v2._MUTED, True)
            _text(renderer, canvas, value, left + 360, y - 5, 26, color, True)
        if title == "WINDOW_MEDIAN":
            _text(renderer, canvas, WINDOW_METRICS_ONLY, left + 28, 720, 17, _v2._WARNING, True)
        else:
            _text(renderer, canvas, "Image source: selected_pair local PNG bundle", left + 28, 720, 20, _v2._MUTED)

    _fill_rect(canvas, 52, 980, 1944, 246, _v2._WHITE)
    _stroke_rect(canvas, 52, 980, 1944, 246, _v2._BORDER, 2)
    _text(renderer, canvas, "ABSOLUTE DIFFERENCES / DESCRIPTIVE FLAG", 80, 1008, 24, _v2._INK, True)
    difference_rows = (
        ("dNBR median", _difference(selected_metrics, window_metrics, "dnbr_median")),
        ("dNBR p90", _difference(selected_metrics, window_metrics, "dnbr_p90")),
        ("area > 0.20 ha", _difference(selected_metrics, window_metrics, "area_ha_dnbr_gt_020")),
        ("valid overlap", _difference(selected_metrics, window_metrics, "valid_overlap_fraction")),
    )
    for index, (label, value) in enumerate(difference_rows):
        left = 82 + index * 455
        _text(renderer, canvas, label.upper(), left, 1060, 17, _v2._MUTED, True)
        _text(renderer, canvas, value, left, 1090, 30, _v2._ACCENT_DARK, True)
    flag = _comparison_status(selected_metrics, window_metrics)
    _text(renderer, canvas, f"FLAG: {flag}", 82, 1160, 23, _v2._WARNING if "disagreement" in flag else _v2._VALID, True)
    _text(renderer, canvas, "The flag is descriptive only; it is not an automatic burn or severity label.", 82, 1192, 18, _v2._MUTED)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 52, 1302, 22, _v2._WARNING, True)
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}; {NEGATIVE_DNBR_NOTE}.", 52, 1334, 17, _v2._MUTED)
    _text(renderer, canvas, SPECTRAL_NODATA_NOTE, 52, 1360, 17, _v2._MUTED)
    _text(renderer, canvas, _v2.FALSE_COLOR_DEFERRED_NOTE, 52, 1386, 17, _v2._MUTED)
    comparison_metadata = {
        **dict(metadata),
        "quicklook_version": QUICKLOOK_VERSION,
        "sheet": "temporal_robustness",
        "comparison_section": "ABSOLUTE DIFFERENCES / DESCRIPTIVE FLAG",
        "window_composite_metadata": window_metadata,
        "window_metadata_display": list(_window_display_lines(window_metadata)),
        "selected_pair_display": (
            f"PRE SCENE: {_format_timestamp((selected_metrics or {}).get('pre_timestamp_utc'))}   "
            f"POST SCENE: {_format_timestamp((selected_metrics or {}).get('post_timestamp_utc'))}"
        ),
        "window_median_raster_available": False,
        "window_median_label": "metrics only",
        "window_median_display": WINDOW_METRICS_ONLY,
        "window_median_quicklook_path": "",
        "selected_pair_quicklook_path": "",
        "comparison_flag": flag,
        "comparison_flag_display": f"FLAG: {flag}",
        "absolute_differences": {key: value for key, value in difference_rows},
        "font_path": str(font.path),
        "font_family": font.family,
        "font_distributed": False,
        "font_backend": font.backend,
        "panel_dimensions": [COMPARISON_WIDTH, COMPARISON_HEIGHT],
        "final_format": "RGB",
        "alpha_scientific": False,
        "diagnostic_dnbr_range": None,
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "positive_dnbr_note": POSITIVE_DNBR_NOTE,
        "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        "spectral_nodata_note": SPECTRAL_NODATA_NOTE,
        "scientific_outputs_modified": False,
        "earth_engine_queries_made": False,
    }
    return encode_png(canvas, comparison_metadata)


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def write_quicklook_v2_1_outputs(
    event_input: Any,
    *,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any] | None,
    source_dir: Path | str,
    output_dir: Path | str,
    review_upload_dir: Path | str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate v1 sources and write only the separate v2.1 output tree."""

    source_map = source_paths(event_input.event_id, source_dir)
    missing = [key for key, path in source_map.items() if not path.is_file()]
    if missing:
        raise QuicklookValidationError(
            f"Faltan fuentes locales v1 para {event_input.event_id}: {', '.join(missing)}",
            stats={"missing_sources": missing, "source_files": {key: str(path) for key, path in source_map.items()}},
        )
    thumbnails = {key: path.read_bytes() for key, path in source_map.items()}
    metadata = _event_summary(event_input, selected_metrics, window_metrics)
    main_payload = compose_panel_v2_1(thumbnails, metadata, event_input)
    comparison_payload = compose_temporal_comparison_sheet_v2_1(metadata, selected_metrics, window_metrics)
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_input.event_id)
    main_name = f"{safe}_selected_pair_cs050_panel_v2_1.png"
    comparison_name = f"{safe}_temporal_comparison_v2_1.png"
    main_path = Path(output_dir) / main_name
    comparison_path = Path(output_dir) / comparison_name
    upload_main_path = Path(review_upload_dir) / main_name
    upload_comparison_path = Path(review_upload_dir) / comparison_name
    _write_bytes_atomic(main_path, main_payload)
    _write_bytes_atomic(comparison_path, comparison_payload)
    _write_bytes_atomic(upload_main_path, main_payload)
    _write_bytes_atomic(upload_comparison_path, comparison_payload)
    main_details = decode_png_details(main_payload)
    comparison_details = decode_png_details(comparison_payload)
    return {
        "event_id": event_input.event_id,
        "status": "generated",
        "quicklook_version": QUICKLOOK_VERSION,
        "main_panel_path": _relative(main_path, root),
        "temporal_comparison_path": _relative(comparison_path, root),
        "review_upload_main_path": _relative(upload_main_path, root),
        "review_upload_comparison_path": _relative(upload_comparison_path, root),
        "dimensions": [main_details.width, main_details.height],
        "comparison_dimensions": [comparison_details.width, comparison_details.height],
        "format": main_details.mode,
        "alpha_present": main_details.alpha_present,
        "source_paths": {key: _relative(path, root) for key, path in source_map.items()},
        "metadata": metadata,
        "window_composite_metadata": metadata["window_composite_metadata"],
        "window_median_raster_available": False,
        "window_median_label": "metrics only",
        "diagnostic_dnbr_available": False,
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "false_color_swir": "deferred_level_2",
        "mask_legend": [dict(item) for item in MASK_LEGEND],
        "font": {
            "path": str(resolve_system_font().path),
            "family": resolve_system_font().family,
            "distributed": False,
        },
        "scientific_outputs_modified": False,
        "earth_engine_queries_made": False,
        "source_numeric_rasters_read": False,
        "deterministic_payload_sha256": hashlib.sha256(main_payload + comparison_payload).hexdigest(),
    }


def _protected_snapshot(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    relative_paths: set[str] = set(PROTECTED_FILE_PATHS)
    missing_paths: list[str] = []
    for relative in PROTECTED_DIRECTORY_PATHS:
        directory = root_path / relative
        if not directory.is_dir():
            missing_paths.append(relative + "/")
            continue
        relative_paths.update(
            path.relative_to(root_path).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        )
    entries: list[dict[str, str]] = []
    for relative in sorted(relative_paths):
        path = root_path / relative
        if not path.is_file():
            if relative in PROTECTED_FILE_PATHS:
                missing_paths.append(relative)
            continue
        entries.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    return {
        "index_sha256": _hash_index(lines),
        "entry_count": len(entries),
        "entries": entries,
        "missing_paths": sorted(set(missing_paths)),
    }


def protected_integrity_snapshot(root: Path | str) -> dict[str, Any]:
    """Public wrapper used by the CLI and tests for before/after capture."""

    return _protected_snapshot(root)


def compare_protected_integrity(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_map = {str(item["path"]): str(item["sha256"]) for item in before.get("entries", [])}
    after_map = {str(item["path"]): str(item["sha256"]) for item in after.get("entries", [])}
    changed: list[str] = []
    created: list[str] = []
    deleted: list[str] = []
    for path in sorted(set(before_map) | set(after_map)):
        if path not in before_map:
            created.append(path)
        elif path not in after_map:
            deleted.append(path)
        elif before_map[path] != after_map[path]:
            changed.append(path)
    return {
        "before_index_sha256": before.get("index_sha256", ""),
        "after_index_sha256": after.get("index_sha256", ""),
        "before_entry_count": before.get("entry_count", 0),
        "after_entry_count": after.get("entry_count", 0),
        "before_missing_paths": list(before.get("missing_paths", [])),
        "after_missing_paths": list(after.get("missing_paths", [])),
        "changed_count": len(changed),
        "changed_paths": changed,
        "created_count": len(created),
        "created_paths": created,
        "deleted_count": len(deleted),
        "deleted_paths": deleted,
        "all_unchanged": not changed and not created and not deleted,
    }


def build_quicklook_v2_1_report(
    results: Sequence[Mapping[str, Any]],
    *,
    requested_event_ids: Sequence[str],
    scientific_integrity: Mapping[str, Any] | None = None,
    protected_integrity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    failures = [dict(item) for item in results if item.get("status") != "generated"]
    return {
        "stage": "sentinel2_dnbr_quicklook_v2_1",
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "requested_event_ids": list(requested_event_ids),
        "requested_event_count": len(requested_event_ids),
        "generated_count": sum(item.get("status") == "generated" for item in results),
        "failed_count": len(failures),
        "results": [dict(item) for item in results],
        "source_mode": "local_v1_png_and_csv_scene_inventory_only",
        "earth_engine_queries_made": False,
        "scientific_outputs_modified": False,
        "scientific_csv_json_modified": False,
        "scene_selection_modified": False,
        "cohort_modified": False,
        "cache_modified": False,
        "checkpoint_modified": False,
        "aoi_modified": False,
        "sentinel2_policy_modified": False,
        "diagnostic_dnbr_map": "omitted",
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "false_color_swir": "deferred_level_2",
        "human_review_started": False,
        "significant_burn_labels_created": False,
        "models_trained": False,
        "visual_correction": {
            "mask_invalid_color": "#c026d3",
            "mask_valid_color": "#0f766e",
            "aoi_boundary_color": "#ffd166",
            "firms_detection_color": "#00e5ff",
            "spectral_nodata_color": "#94a3b8",
            "spectral_nodata_note": SPECTRAL_NODATA_NOTE,
            "mask_legend": [dict(item) for item in MASK_LEGEND],
            "positive_dnbr_note": POSITIVE_DNBR_NOTE,
            "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        },
        "scientific_integrity": dict(scientific_integrity or {}),
        "protected_integrity": dict(protected_integrity or {}),
    }


def quicklook_v2_1_report_markdown(report: Mapping[str, Any]) -> str:
    integrity = report.get("scientific_integrity", {})
    protected = report.get("protected_integrity", {})
    lines = [
        "# FirePA Quicklook v2.1 checkpoint report",
        "",
        f"- Quicklook version: `{report['quicklook_version']}`",
        f"- Pipeline version: `{report['pipeline_version']}`",
        f"- Generated: `{report['generated_count']}/{report['requested_event_count']}`",
        "- Source mode: existing v1 PNGs plus local CSV/scene-inventory metadata; Earth Engine queries: `false`.",
        "- Scientific CSV/JSON, scene selection, cohort, cache, checkpoint, AOI and Sentinel-2 policy modified: `false`.",
        f"- Protected before/after changed entries: `{protected.get('changed_count', 'n/a')}`; created: `{protected.get('created_count', 'n/a')}`; deleted: `{protected.get('deleted_count', 'n/a')}`.",
        f"- Scientific manifest changed entries: `{integrity.get('scientific_changed_count', 'n/a')}`.",
        "- Final PNGs: RGB, 2048 x 1440, no scientific alpha channel.",
        "",
        "## Visual correction contract",
        "",
        f"- Invalid mask: `#c026d3` (mask value 0 after `unmask(0)`).",
        f"- Valid mask: `#0f766e` (mask value 1).",
        f"- AOI boundary overlay: `#ffd166`; FIRMS detection overlay: `#00e5ff`.",
        f"- Gray `#94a3b8`: spectral nodata/background only; it is not a mask category.",
        f"- `{POSITIVE_DNBR_NOTE}`; `{NEGATIVE_DNBR_NOTE}`.",
        f"- {DESCRIPTIVE_WARNING}",
        "",
        "## Temporal metadata contract",
        "",
        "- Selected-pair dates are displayed as `PRE SCENE` and `POST SCENE`.",
        "- Temporal semantics are displayed as `PRE LEAD` and `POST LAG`, measured toward/away from the event boundary.",
        "- The window_median card never reuses selected-pair timestamps.",
        "- When local candidate metadata is complete, the card shows window start/end, scene counts and IDs from the local scene inventory/metrics.",
        f"- When it is not complete, the card states `{WINDOW_METADATA_UNAVAILABLE}` and `{WINDOW_METRICS_ONLY}`.",
        "",
        "## Calibration outputs",
        "",
        "| event_id | main panel | temporal comparison | review main | review comparison | window metadata |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["results"]:
        if item.get("status") != "generated":
            lines.append(f"| `{item.get('event_id', '')}` | FAILED | {item.get('error', '')} |  |  |  |")
            continue
        window = item.get("window_composite_metadata", {})
        lines.append(
            f"| `{item['event_id']}` | `{item['main_panel_path']}` | `{item['temporal_comparison_path']}` | `{item['review_upload_main_path']}` | `{item['review_upload_comparison_path']}` | {'available locally' if window.get('available_locally') else 'unavailable locally'} |"
        )
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Scientific index before: `{integrity.get('scientific_index_sha256_before', 'n/a')}`",
            f"- Scientific index after: `{integrity.get('scientific_index_sha256_after', 'n/a')}`",
            f"- Scientific outputs unchanged: `{integrity.get('scientific_outputs_unchanged', 'n/a')}`",
            f"- v1 visual outputs unchanged: `{integrity.get('v1_visual_outputs_unchanged', 'n/a')}`",
            f"- Protected index before: `{protected.get('before_index_sha256', 'n/a')}`",
            f"- Protected index after: `{protected.get('after_index_sha256', 'n/a')}`",
            f"- Protected files unchanged: `{protected.get('all_unchanged', 'n/a')}`",
            "",
            "No human calibration, significant_burn label creation, model training, 2026 data use, cohort expansion, Earth Engine query or scientific recomputation occurred.",
            "",
        ]
    )
    return "\n".join(lines)


def write_quicklook_v2_1_report(path_json: Path | str, path_markdown: Path | str, report: Mapping[str, Any]) -> None:
    json_path = Path(path_json)
    markdown_path = Path(path_markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_temp = json_path.with_suffix(json_path.suffix + ".tmp")
    markdown_temp = markdown_path.with_suffix(markdown_path.suffix + ".tmp")
    json_temp.write_text(json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_temp.write_text(quicklook_v2_1_report_markdown(report), encoding="utf-8")
    json_temp.replace(json_path)
    markdown_temp.replace(markdown_path)
