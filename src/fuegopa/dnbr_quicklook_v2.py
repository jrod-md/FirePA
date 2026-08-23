"""Local-only Sentinel-2 dNBR Quicklook v2 compositor.

Quicklook v2 is deliberately separate from the v1 compositor. It reads the
six already-rendered local PNG artifacts and tabular metrics; it never queries
Earth Engine, reconstructs scientific values from colors, or writes a
scientific CSV/JSON. RGB inputs may be resized bilinearly for presentation.
Scientific rasters and the categorical mask use nearest-neighbor resizing.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import struct
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .dnbr_quicklook import (
    DNBR_VIS_MAX,
    DNBR_VIS_MIN,
    PANEL_KEYS,
    RGBImage,
    QuicklookValidationError,
    VISUALIZATION_PALETTE,
    decode_png_details,
    encode_png,
    validate_thumbnail_sources,
)


QUICKLOOK_VERSION = "fuegopa-dnbr-quicklook-v2"
PIPELINE_VERSION = "fuegopa-sentinel2-dnbr-v3"
PANEL_WIDTH = 2048
PANEL_HEIGHT = 1440
COMPARISON_WIDTH = PANEL_WIDTH
COMPARISON_HEIGHT = PANEL_HEIGHT
ANALYSIS_SCALE_M = 20
AOI_ID = "b0500"
AOI_BUFFER_M = 500
PRIMARY_CLOUD_THRESHOLD = 0.50
NBR_VIS_MIN = -1.0
NBR_VIS_MAX = 1.0
DIAGNOSTIC_DNBR_RANGE = (-0.25, 0.50)
DIAGNOSTIC_UNAVAILABLE_NOTE = (
    "Diagnostic dNBR remap unavailable from local numeric data; deferred to Level 2."
)
FALSE_COLOR_DEFERRED_NOTE = (
    "False-color SWIR deferred to Level 2; no local B12/B8A/B4 traceable raster."
)
DESCRIPTIVE_WARNING = "dNBR is descriptive and not a confirmation of fire."
RESAMPLING_POLICY = {
    "rgb": "bilinear_presentation_only",
    "nbr": "nearest_neighbor",
    "dnbr": "nearest_neighbor",
    "mask": "nearest_neighbor",
}

CALIBRATION_EVENT_IDS = (
    "event-r1500_t06-0ddd477d24b1364d",
    "event-r1500_t06-84cb252a6877d2d5",
    "event-r1500_t06-ef20fd746737f4ea",
    "event-r1500_t06-9e5bf1d807f9d61a",
    "event-r1500_t06-548ca9e284d1a330",
    "event-r1500_t06-040b1a186d857b11",
    "event-r1500_t06-09c2d54e2d8fb5dd",
)

_BACKGROUND = (244, 247, 249)
_WHITE = (255, 255, 255)
_INK = (15, 23, 42)
_MUTED = (71, 85, 105)
_BORDER = (148, 163, 184)
_ACCENT = (14, 116, 144)
_ACCENT_DARK = (15, 78, 95)
_WARNING = (154, 52, 18)
_INVALID = (148, 163, 184)
_VALID = (15, 118, 110)
_FIRMS = (0, 229, 255)
_FIRMS_HALO = (255, 255, 255)
_CENTROID = (255, 209, 102)
_BLACK = (15, 23, 42)

FONT_PATH_CANDIDATES = (
    Path(os.environ.get("WINDIR", ".")) / "Fonts" / "arial.ttf",
    Path(os.environ.get("WINDIR", ".")) / "Fonts" / "segoeui.ttf",
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


@dataclass(frozen=True)
class TrueTypeFontSpec:
    path: Path
    family: str
    backend: str


def resolve_system_font() -> TrueTypeFontSpec:
    """Resolve a readable system TrueType font without copying it."""

    for candidate in FONT_PATH_CANDIDATES:
        if candidate.is_file():
            family = "Arial" if candidate.name.casefold().startswith("arial") else "Segoe UI"
            if "Liberation" in candidate.name:
                family = "Liberation Sans"
            if "DejaVu" in candidate.name:
                family = "DejaVu Sans"
            backend = "windows-gdi" if sys.platform == "win32" else "unavailable"
            if backend == "unavailable":
                raise QuicklookValidationError(
                    "Quicklook v2 requiere un backend TrueType del entorno; no se distribuyen fuentes."
                )
            return TrueTypeFontSpec(candidate, family, backend)
    raise QuicklookValidationError(
        "No se encontró una fuente TrueType legible del sistema; Quicklook v2 no se guarda."
    )


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class _TrueTypeRenderer:
    """Small Windows GDI text rasterizer used only for local panel labels."""

    def __init__(self, font: TrueTypeFontSpec) -> None:
        if font.backend != "windows-gdi":
            raise QuicklookValidationError("Quicklook v2 TrueType renderer is unavailable in this environment.")
        self.font = font
        self.gdi = ctypes.windll.gdi32

    def _mask(self, text: str, size: int, bold: bool) -> tuple[int, int, bytes]:
        if not text:
            return 0, max(1, size), b""
        width = max(32, int(len(text) * size * 1.1) + 32)
        height = max(32, int(size * 1.8) + 16)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        dc = self.gdi.CreateCompatibleDC(0)
        if not dc:
            raise QuicklookValidationError("No se pudo crear el DC GDI para la fuente TrueType.")
        bitmap = self.gdi.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), 0, 0)
        if not bitmap or not bits.value:
            self.gdi.DeleteDC(dc)
            raise QuicklookValidationError("No se pudo crear el bitmap GDI para la fuente TrueType.")
        old_bitmap = self.gdi.SelectObject(dc, bitmap)
        font_handle = self.gdi.CreateFontW(
            -int(size),
            0,
            0,
            0,
            700 if bold else 400,
            0,
            0,
            0,
            1,
            0,
            0,
            4,
            0,
            self.font.family,
        )
        if not font_handle:
            self.gdi.SelectObject(dc, old_bitmap)
            self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(dc)
            raise QuicklookValidationError("No se pudo crear la fuente TrueType del sistema.")
        try:
            ctypes.memset(bits.value, 0, width * height * 4)
            old_font = self.gdi.SelectObject(dc, font_handle)
            self.gdi.SetBkMode(dc, 1)
            self.gdi.SetTextColor(dc, 0x00FFFFFF)
            encoded = str(text)
            self.gdi.TextOutW(dc, 0, 0, encoded, len(encoded))
            self.gdi.SelectObject(dc, old_font)
            raw = ctypes.string_at(bits.value, width * height * 4)
        finally:
            self.gdi.SelectObject(dc, old_bitmap)
            self.gdi.DeleteObject(font_handle)
            self.gdi.DeleteObject(bitmap)
            self.gdi.DeleteDC(dc)
        return width, height, raw

    def draw(
        self,
        image: RGBImage,
        text: str,
        left: int,
        top: int,
        *,
        size: int,
        color: tuple[int, int, int],
        bold: bool = False,
    ) -> None:
        width, height, raw = self._mask(text, size, bold)
        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 4
                alpha = max(raw[offset], raw[offset + 1], raw[offset + 2])
                if alpha == 0:
                    continue
                target_x = left + x
                target_y = top + y
                if not (0 <= target_x < image.width and 0 <= target_y < image.height):
                    continue
                previous = image.get_pixel(target_x, target_y)
                blended = tuple(
                    (color[index] * alpha + previous[index] * (255 - alpha) + 127) // 255
                    for index in range(3)
                )
                image.set_pixel(target_x, target_y, blended)  # type: ignore[arg-type]


def _renderer() -> tuple[TrueTypeFontSpec, _TrueTypeRenderer]:
    font = resolve_system_font()
    return font, _TrueTypeRenderer(font)


def _text(renderer: _TrueTypeRenderer, image: RGBImage, value: Any, x: int, y: int, size: int, color: tuple[int, int, int] = _INK, bold: bool = False) -> None:
    renderer.draw(image, "" if value is None else str(value), x, y, size=size, color=color, bold=bold)


def _fill_rect(image: RGBImage, left: int, top: int, width: int, height: int, color: tuple[int, int, int]) -> None:
    for y in range(max(0, top), min(image.height, top + height)):
        start_x = max(0, left)
        end_x = min(image.width, left + width)
        if end_x > start_x:
            start = (y * image.width + start_x) * 3
            end = (y * image.width + end_x) * 3
            image.pixels[start:end] = bytes(color) * (end_x - start_x)


def _stroke_rect(image: RGBImage, left: int, top: int, width: int, height: int, color: tuple[int, int, int], thickness: int = 1) -> None:
    for offset in range(max(1, thickness)):
        for x in range(left + offset, left + width - offset):
            image.set_pixel(x, top + offset, color)
            image.set_pixel(x, top + height - 1 - offset, color)
        for y in range(top + offset, top + height - offset):
            image.set_pixel(left + offset, y, color)
            image.set_pixel(left + width - 1 - offset, y, color)


def _line(image: RGBImage, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], thickness: int = 1) -> None:
    dx = abs(x2 - x1)
    sx = 1 if x1 < x2 else -1
    dy = -abs(y2 - y1)
    sy = 1 if y1 < y2 else -1
    error = dx + dy
    while True:
        for offset in range(-max(0, thickness // 2), max(0, thickness // 2) + 1):
            image.set_pixel(x1 + offset, y1, color)
            image.set_pixel(x1, y1 + offset, color)
        if x1 == x2 and y1 == y2:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x1 += sx
        if twice <= dx:
            error += dx
            y1 += sy


def _circle(image: RGBImage, center_x: int, center_y: int, radius: int, color: tuple[int, int, int]) -> None:
    radius = max(1, radius)
    for y in range(center_y - radius, center_y + radius + 1):
        for x in range(center_x - radius, center_x + radius + 1):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2:
                image.set_pixel(x, y, color)


def _diamond(image: RGBImage, center_x: int, center_y: int, radius: int, color: tuple[int, int, int]) -> None:
    for y in range(center_y - radius, center_y + radius + 1):
        span = radius - abs(y - center_y)
        for x in range(center_x - span, center_x + span + 1):
            image.set_pixel(x, y, color)


def _resize_nearest(image: RGBImage, width: int, height: int) -> RGBImage:
    resized = RGBImage.solid(width, height, _INVALID)
    for y in range(height):
        source_y = min(image.height - 1, int(y * image.height / height))
        for x in range(width):
            source_x = min(image.width - 1, int(x * image.width / width))
            resized.set_pixel(x, y, image.get_pixel(source_x, source_y))
    return resized


def _resize_bilinear(image: RGBImage, width: int, height: int) -> RGBImage:
    """Presentation-only RGB interpolation; never used for scientific layers."""

    resized = RGBImage.solid(width, height, _INVALID)
    for y in range(height):
        source_y = (y + 0.5) * image.height / height - 0.5
        y0 = max(0, min(image.height - 1, math.floor(source_y)))
        y1 = max(0, min(image.height - 1, y0 + 1))
        fy = max(0.0, min(1.0, source_y - y0))
        for x in range(width):
            source_x = (x + 0.5) * image.width / width - 0.5
            x0 = max(0, min(image.width - 1, math.floor(source_x)))
            x1 = max(0, min(image.width - 1, x0 + 1))
            fx = max(0.0, min(1.0, source_x - x0))
            top = image.get_pixel(x0, y0)
            top_right = image.get_pixel(x1, y0)
            bottom = image.get_pixel(x0, y1)
            bottom_right = image.get_pixel(x1, y1)
            pixel = tuple(
                round(
                    (top[channel] * (1 - fx) + top_right[channel] * fx) * (1 - fy)
                    + (bottom[channel] * (1 - fx) + bottom_right[channel] * fx) * fy
                )
                for channel in range(3)
            )
            resized.set_pixel(x, y, pixel)  # type: ignore[arg-type]
    return resized


def _crop_scientific_colorbar(image: RGBImage, key: str) -> RGBImage:
    if key not in {"nbr_pre", "nbr_post", "dnbr"} or image.width < 80:
        return image
    crop_width = image.width - min(32, image.width // 8)
    cropped = RGBImage.solid(crop_width, image.height, _INVALID)
    cropped.paste(image, 0, 0)
    return cropped


def _hex_color(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _palette_color(position: float) -> tuple[int, int, int]:
    position = max(0.0, min(1.0, position))
    scaled = position * (len(VISUALIZATION_PALETTE) - 1)
    lower = min(len(VISUALIZATION_PALETTE) - 2, int(scaled))
    fraction = scaled - lower
    first = _hex_color(VISUALIZATION_PALETTE[lower])
    second = _hex_color(VISUALIZATION_PALETTE[lower + 1])
    return tuple(round(first[index] + (second[index] - first[index]) * fraction) for index in range(3))  # type: ignore[return-value]


def _draw_colorbar(renderer: _TrueTypeRenderer, image: RGBImage, left: int, top: int, height: int, minimum: float, maximum: float, label: str) -> None:
    width = 26
    for y in range(height):
        _fill_rect(image, left, top + y, width, 1, _palette_color(1 - y / max(1, height - 1)))
    _stroke_rect(image, left, top, width, height, _BORDER)
    _text(renderer, image, label, left - 4, top - 32, 20, _MUTED, True)
    _text(renderer, image, f"{maximum:g}", left + width + 8, top - 6, 18, _MUTED)
    _text(renderer, image, "0", left + width + 8, top + height // 2 - 10, 18, _MUTED)
    _text(renderer, image, f"{minimum:g}", left + width + 8, top + height - 18, 18, _MUTED)


def _metric_float(row: Mapping[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format_float(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _format_timestamp(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("+00:00", "Z")


def _event_timestamp(event: Any, attribute: str) -> datetime:
    value = getattr(event, attribute)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_summary(event_input: Any, selected_metrics: Mapping[str, Any]) -> dict[str, Any]:
    event = event_input.event
    event_start = _event_timestamp(event, "start_timestamp_utc")
    event_end = _event_timestamp(event, "end_timestamp_utc")
    pre_text = _format_timestamp(selected_metrics.get("pre_timestamp_utc"))
    post_text = _format_timestamp(selected_metrics.get("post_timestamp_utc"))
    try:
        pre = datetime.fromisoformat(pre_text.replace("Z", "+00:00"))
        post = datetime.fromisoformat(post_text.replace("Z", "+00:00"))
        pre_days = (event_start - pre).total_seconds() / 86400
        post_days = (post - event_end).total_seconds() / 86400
    except (TypeError, ValueError):
        pre_days = None
        post_days = None
    overlap = _metric_float(selected_metrics, "valid_overlap_fraction")
    return {
        "event_id": event_input.event_id,
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "analysis_mode": "selected_pair",
        "event_start_utc": event_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_end_utc": event_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pre_timestamp_utc": pre_text,
        "post_timestamp_utc": post_text,
        "days_event_to_pre": pre_days,
        "days_event_to_post": post_days,
        "policy_path": str(selected_metrics.get("policy_path") or event_input.policy_path),
        "selected_combination_id": str(selected_metrics.get("selected_combination_id") or event_input.selected_combination_id),
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
        "scientific_outputs_modified": False,
        "earth_engine_queries_made": False,
        "source_raster_numeric_data": False,
        "warning": DESCRIPTIVE_WARNING,
        "resampling_policy": dict(RESAMPLING_POLICY),
    }


def _source_prefix(event_id: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_id)
    return f"{safe}_selected_pair_cs050"


def source_paths(event_id: str, source_dir: Path | str) -> dict[str, Path]:
    directory = Path(source_dir)
    prefix = _source_prefix(event_id)
    return {key: directory / f"{prefix}_{key}.png" for key in PANEL_KEYS}


def _event_positions(event_input: Any, width: int, height: int) -> tuple[list[tuple[int, int]], tuple[int, int], float]:
    detections = list(getattr(event_input.event, "detections", ()) or ())
    if not detections:
        return [], (width // 2, height // 2), 1000.0
    latitudes = [float(item.latitude) for item in detections]
    longitudes = [float(item.longitude) for item in detections]
    center_lat = sum(latitudes) / len(latitudes)
    center_lon = sum(longitudes) / len(longitudes)
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = meters_per_degree_lat * max(0.1, math.cos(math.radians(center_lat)))
    points_m = [
        (
            (float(item.longitude) - center_lon) * meters_per_degree_lon,
            (float(item.latitude) - center_lat) * meters_per_degree_lat,
        )
        for item in detections
    ]
    min_x = min(point[0] for point in points_m) - AOI_BUFFER_M
    max_x = max(point[0] for point in points_m) + AOI_BUFFER_M
    min_y = min(point[1] for point in points_m) - AOI_BUFFER_M
    max_y = max(point[1] for point in points_m) + AOI_BUFFER_M
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    output = [
        (
            int((point[0] - min_x) / span_x * max(1, width - 1)),
            int((max_y - point[1]) / span_y * max(1, height - 1)),
        )
        for point in points_m
    ]
    centroid = (
        int((0 - min_x) / span_x * max(1, width - 1)),
        int((max_y - 0) / span_y * max(1, height - 1)),
    )
    return output, centroid, span_x


def _draw_firms_overlay(image: RGBImage, event_input: Any, left: int, top: int, width: int, height: int) -> None:
    points, centroid, span_x = _event_positions(event_input, width, height)
    for x, y in points:
        _circle(image, left + x, top + y, 13, _FIRMS_HALO)
        _circle(image, left + x, top + y, 7, _FIRMS)
    centroid_x, centroid_y = centroid
    _diamond(image, left + centroid_x, top + centroid_y, 11, _CENTROID)
    _line(image, left + centroid_x - 15, top + centroid_y, left + centroid_x + 15, top + centroid_y, _BLACK, 2)
    _line(image, left + centroid_x, top + centroid_y - 15, left + centroid_x, top + centroid_y + 15, _BLACK, 2)
    scale_length = max(80, min(220, int(width * AOI_BUFFER_M / max(span_x, 1.0))))
    bar_left = left + width - scale_length - 16
    bar_top = top + height - 38
    _line(image, bar_left, bar_top, bar_left + scale_length, bar_top, _WHITE, 8)
    _line(image, bar_left, bar_top, bar_left + scale_length, bar_top, _BLACK, 4)


def _tile_source(details: Any, key: str, width: int, height: int) -> RGBImage:
    source = _crop_scientific_colorbar(details.image, key)
    if key in {"rgb_pre", "rgb_post"}:
        return _resize_bilinear(source, width, height)
    return _resize_nearest(source, width, height)


def _panel_metadata_text(metadata: Mapping[str, Any]) -> dict[str, str]:
    overlap = metadata.get("valid_overlap_percent")
    return {
        "overlap": "n/a" if overlap is None else f"{float(overlap):.1f}%",
        "dnbr_median": _format_float(metadata.get("dnbr_median"), 3),
        "dnbr_p90": _format_float(metadata.get("dnbr_p90"), 3),
        "area": _format_float(metadata.get("area_ha_dnbr_gt_020"), 2),
    }


def compose_panel_v2(thumbnails: Mapping[str, bytes], metadata: Mapping[str, Any], event_input: Any | None = None) -> bytes:
    """Compose the main v2 panel; all six sources are validated before output."""

    font, renderer = _renderer()
    details, source_stats = validate_thumbnail_sources(thumbnails)
    canvas = RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, _BACKGROUND)
    event_id = str(metadata.get("event_id", ""))
    values = _panel_metadata_text(metadata)
    _text(renderer, canvas, event_id, 42, 28, 44, _INK, True)
    _text(renderer, canvas, f"{QUICKLOOK_VERSION}  |  MODE: selected_pair  |  LOCAL ARTIFACT REBUILD", 44, 86, 24, _ACCENT_DARK, True)
    _text(renderer, canvas, f"EVENT UTC: {metadata.get('event_start_utc', '')} to {metadata.get('event_end_utc', '')}   PRE: {metadata.get('pre_timestamp_utc', '')}   POST: {metadata.get('post_timestamp_utc', '')}", 44, 119, 20, _MUTED)
    _text(renderer, canvas, f"DELAY PRE: {_format_float(metadata.get('days_event_to_pre'), 2)} d   DELAY POST: {_format_float(metadata.get('days_event_to_post'), 2)} d   POLICY: {metadata.get('policy_path', '')}   AOI: b0500 / 500 m   SCALE: 20 m   CS+: >= 0.50", 44, 148, 20, _MUTED)

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
        "dnbr": "dNBR  |  fixed visual range [-1, 1]",
        "mask": "COMMON VALID MASK  |  nearest-neighbor",
    }
    for index, key in enumerate(PANEL_KEYS):
        column, row = index % 3, index // 3
        left = left_margin + column * (tile_width + tile_gap_x)
        top = top_margin + row * (tile_height + tile_gap_y)
        _fill_rect(canvas, left, top, tile_width, tile_height, _WHITE)
        _stroke_rect(canvas, left, top, tile_width, tile_height, _BORDER, 2)
        _text(renderer, canvas, labels[key], left + 18, top + 17, 23, _INK, True)
        if key == "mask" and compact_mask:
            local_width, local_height = 300, 220
            image_left = left + 26
            image_top = top + 108
            _fill_rect(canvas, image_left - 8, image_top - 8, local_width + 16, local_height + 16, (235, 240, 242))
            _stroke_rect(canvas, image_left - 8, image_top - 8, local_width + 16, local_height + 16, _BORDER)
            _text(renderer, canvas, "COMPACT INSET: >= 98% VALID", left + 360, top + 148, 19, _VALID, True)
        else:
            local_width, local_height = image_width, image_height
            image_left = left + 20
            image_top = top + 62
        tile = _tile_source(details[key], key, local_width, local_height)
        canvas.paste(tile, image_left, image_top)
        if key in {"rgb_pre", "rgb_post"} and event_input is not None:
            _draw_firms_overlay(canvas, event_input, image_left, image_top, local_width, local_height)
            if key == "rgb_post":
                _text(renderer, canvas, "FIRMS halo + centroid   |   scale bar: 500 m", image_left + 10, image_top + local_height - 28, 17, _WHITE, True)
        if key in {"nbr_pre", "nbr_post", "dnbr"}:
            _draw_colorbar(renderer, canvas, left + 568, image_top + 30, local_height - 40, NBR_VIS_MIN if key != "dnbr" else DNBR_VIS_MIN, NBR_VIS_MAX if key != "dnbr" else DNBR_VIS_MAX, "NBR" if key != "dnbr" else "dNBR")
        if key == "mask":
            legend_y = top + tile_height - 46
            _fill_rect(canvas, left + 24, legend_y, 22, 18, _INVALID)
            _text(renderer, canvas, "INVALID", left + 54, legend_y - 5, 17, _MUTED)
            _fill_rect(canvas, left + 168, legend_y, 22, 18, _VALID)
            _text(renderer, canvas, "VALID", left + 198, legend_y - 5, 17, _MUTED)

    metric_top = 1268
    metric_width = 365
    metric_gap = 12
    metric_labels = (
        ("VALID OVERLAP", values["overlap"], _ACCENT),
        ("dNBR MEDIAN", values["dnbr_median"], _ACCENT_DARK),
        ("dNBR P90", values["dnbr_p90"], _ACCENT_DARK),
        ("AREA > 0.20", f"{values['area']} ha", _ACCENT_DARK),
        ("METRIC STATUS", str(metadata.get("metric_status") or "n/a"), _ACCENT),
    )
    for index, (label, value, color) in enumerate(metric_labels):
        left = 36 + index * (metric_width + metric_gap)
        _fill_rect(canvas, left, metric_top, metric_width, 74, _WHITE)
        _stroke_rect(canvas, left, metric_top, metric_width, 74, _BORDER)
        _text(renderer, canvas, label, left + 16, metric_top + 10, 16, _MUTED, True)
        _text(renderer, canvas, value, left + 16, metric_top + 34, 27, color, True)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 42, 1364, 22, _WARNING, True)
    _text(renderer, canvas, DIAGNOSTIC_UNAVAILABLE_NOTE, 42, 1392, 18, _MUTED)
    _text(renderer, canvas, FALSE_COLOR_DEFERRED_NOTE, 42, 1416, 18, _MUTED)
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
        "mask_display": "compact_inset" if compact_mask else "full_panel",
        "mask_annotation": "COMPACT INSET: >= 98% VALID" if compact_mask else "FULL MASK PANEL: INVALID PIXELS REMAIN VISIBLE",
        "scale_bar_label": "500 m",
        "analysis_scale_label": "20 m",
        "nbr_range": [NBR_VIS_MIN, NBR_VIS_MAX],
        "dnbr_range": [DNBR_VIS_MIN, DNBR_VIS_MAX],
        "colorbar_ticks": {"NBR": [-1.0, 0.0, 1.0], "dNBR": [-1.0, 0.0, 1.0]},
        "source_raster_numeric_data": False,
        "scientific_outputs_modified": False,
    }
    return encode_png(canvas, metadata_payload)


def _comparison_status(selected: Mapping[str, Any] | None, window: Mapping[str, Any] | None) -> str:
    if not selected or not window:
        return "insufficient local metrics"
    values = [
        (_metric_float(selected, "dnbr_median"), _metric_float(window, "dnbr_median")),
        (_metric_float(selected, "dnbr_p90"), _metric_float(window, "dnbr_p90")),
        (_metric_float(selected, "valid_overlap_fraction"), _metric_float(window, "valid_overlap_fraction")),
    ]
    if any(left is None or right is None for left, right in values):
        return "insufficient local metrics"
    if all(abs(left - right) <= tolerance for (left, right), tolerance in zip(values, (0.05, 0.05, 0.05))):
        return "agreement (descriptive)"
    return "disagreement (descriptive)"


def _difference(selected: Mapping[str, Any] | None, window: Mapping[str, Any] | None, key: str) -> str:
    left = _metric_float(selected, key)
    right = _metric_float(window, key)
    if left is None or right is None:
        return "n/a"
    return f"{abs(left - right):.3f}"


def compose_temporal_comparison_sheet(
    metadata: Mapping[str, Any],
    selected_metrics: Mapping[str, Any] | None,
    window_metrics: Mapping[str, Any] | None,
) -> bytes:
    """Compose a metrics-only temporal robustness sheet."""

    font, renderer = _renderer()
    canvas = RGBImage.solid(COMPARISON_WIDTH, COMPARISON_HEIGHT, _BACKGROUND)
    event_id = str(metadata.get("event_id", ""))
    _text(renderer, canvas, event_id, 48, 36, 44, _INK, True)
    _text(renderer, canvas, f"{QUICKLOOK_VERSION}  |  TEMPORAL ROBUSTNESS  |  selected_pair vs window_median", 50, 96, 24, _ACCENT_DARK, True)
    _text(renderer, canvas, "This sheet compares tabular metrics only. It does not link window_median to the selected_pair image.", 50, 132, 22, _MUTED)
    _text(renderer, canvas, f"POLICY: {metadata.get('policy_path', '')}   COMBINATION: {metadata.get('selected_combination_id', '')}   CS+: >= 0.50   AOI: b0500 / 500 m   SCALE: 20 m", 50, 165, 20, _MUTED)

    cards = (("SELECTED_PAIR", selected_metrics, 52, _ACCENT), ("WINDOW_MEDIAN", window_metrics, 1050, _ACCENT_DARK))
    card_width, card_height = 946, 710
    for title, row, left, color in cards:
        _fill_rect(canvas, left, 230, card_width, card_height, _WHITE)
        _stroke_rect(canvas, left, 230, card_width, card_height, _BORDER, 2)
        _fill_rect(canvas, left, 230, card_width, 80, color)
        _text(renderer, canvas, title, left + 26, 251, 28, _WHITE, True)
        if row is None:
            _text(renderer, canvas, "No local metric row available", left + 28, 350, 26, _WARNING, True)
            _text(renderer, canvas, "metrics only", left + 28, 400, 22, _MUTED)
            continue
        _text(renderer, canvas, f"STATUS: {row.get('metric_status', 'n/a')}   POLICY: {row.get('policy_path', metadata.get('policy_path', ''))}", left + 28, 342, 20, _MUTED, True)
        _text(renderer, canvas, f"PRE: {_format_timestamp(row.get('pre_timestamp_utc'))}   POST: {_format_timestamp(row.get('post_timestamp_utc'))}", left + 28, 374, 19, _MUTED)
        metrics = (
            ("dNBR median", _format_float(_metric_float(row, "dnbr_median"), 4)),
            ("dNBR p90", _format_float(_metric_float(row, "dnbr_p90"), 4)),
            ("area > 0.20", f"{_format_float(_metric_float(row, 'area_ha_dnbr_gt_020'), 3)} ha"),
            ("valid overlap", "n/a" if _metric_float(row, "valid_overlap_fraction") is None else f"{_metric_float(row, 'valid_overlap_fraction') * 100:.1f}%"),
        )
        for index, (label, value) in enumerate(metrics):
            y = 438 + index * 70
            _text(renderer, canvas, label.upper(), left + 28, y, 18, _MUTED, True)
            _text(renderer, canvas, value, left + 360, y - 5, 28, color, True)
        if title == "WINDOW_MEDIAN":
            _text(renderer, canvas, "metrics only", left + 28, 672, 23, _WARNING, True)
            _text(renderer, canvas, "No local window_median raster is available; no image is substituted.", left + 28, 708, 18, _MUTED)
        else:
            _text(renderer, canvas, "Image source: selected_pair local PNG bundle", left + 28, 672, 20, _MUTED)

    _fill_rect(canvas, 52, 980, 1944, 246, _WHITE)
    _stroke_rect(canvas, 52, 980, 1944, 246, _BORDER, 2)
    _text(renderer, canvas, "ABSOLUTE DIFFERENCES / DESCRIPTIVE FLAG", 80, 1008, 24, _INK, True)
    difference_rows = (
        ("dNBR median", _difference(selected_metrics, window_metrics, "dnbr_median")),
        ("dNBR p90", _difference(selected_metrics, window_metrics, "dnbr_p90")),
        ("area > 0.20 ha", _difference(selected_metrics, window_metrics, "area_ha_dnbr_gt_020")),
        ("valid overlap", _difference(selected_metrics, window_metrics, "valid_overlap_fraction")),
    )
    for index, (label, value) in enumerate(difference_rows):
        left = 82 + index * 455
        _text(renderer, canvas, label.upper(), left, 1060, 17, _MUTED, True)
        _text(renderer, canvas, value, left, 1090, 30, _ACCENT_DARK, True)
    flag = _comparison_status(selected_metrics, window_metrics)
    _text(renderer, canvas, f"FLAG: {flag}", 82, 1160, 23, _WARNING if "disagreement" in flag else _VALID, True)
    _text(renderer, canvas, "The flag is descriptive only; it is not an automatic burn or severity label.", 82, 1192, 18, _MUTED)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 52, 1302, 22, _WARNING, True)
    _text(renderer, canvas, DIAGNOSTIC_UNAVAILABLE_NOTE, 52, 1334, 18, _MUTED)
    _text(renderer, canvas, FALSE_COLOR_DEFERRED_NOTE, 52, 1360, 18, _MUTED)
    comparison_metadata = {
        **dict(metadata),
        "quicklook_version": QUICKLOOK_VERSION,
        "sheet": "temporal_robustness",
        "comparison_section": "ABSOLUTE DIFFERENCES / DESCRIPTIVE FLAG",
        "window_median_raster_available": False,
        "window_median_label": "metrics only",
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
        "scientific_outputs_modified": False,
        "earth_engine_queries_made": False,
    }
    return encode_png(canvas, comparison_metadata)


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _relative(path: Path, root: Path | None) -> str:
    if root is None:
        return path.as_posix()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def write_quicklook_v2_outputs(
    event_input: Any,
    *,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any] | None,
    source_dir: Path | str,
    output_dir: Path | str,
    review_upload_dir: Path | str,
    root: Path | None = None,
) -> dict[str, Any]:
    """Validate and write one main sheet plus one temporal comparison sheet."""

    source_map = source_paths(event_input.event_id, source_dir)
    missing = [key for key, path in source_map.items() if not path.is_file()]
    if missing:
        raise QuicklookValidationError(
            f"Faltan fuentes locales v1 para {event_input.event_id}: {', '.join(missing)}",
            stats={"missing_sources": missing, "source_files": {key: str(path) for key, path in source_map.items()}},
        )
    thumbnails = {key: path.read_bytes() for key, path in source_map.items()}
    metadata = _event_summary(event_input, selected_metrics)
    main_payload = compose_panel_v2(thumbnails, metadata, event_input)
    comparison_payload = compose_temporal_comparison_sheet(metadata, selected_metrics, window_metrics)
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_input.event_id)
    main_name = f"{safe}_selected_pair_cs050_panel_v2.png"
    comparison_name = f"{safe}_temporal_comparison_v2.png"
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
        "window_median_raster_available": False,
        "window_median_label": "metrics only",
        "diagnostic_dnbr_available": False,
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "false_color_swir": "deferred_level_2",
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


def build_quicklook_v2_report(
    results: Sequence[Mapping[str, Any]],
    *,
    requested_event_ids: Sequence[str],
    scientific_integrity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    failures = [dict(item) for item in results if item.get("status") != "generated"]
    return {
        "stage": "sentinel2_dnbr_quicklook_v2",
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "requested_event_ids": list(requested_event_ids),
        "requested_event_count": len(requested_event_ids),
        "generated_count": sum(item.get("status") == "generated" for item in results),
        "failed_count": len(failures),
        "results": [dict(item) for item in results],
        "source_mode": "local_png_and_csv_json_only",
        "earth_engine_queries_made": False,
        "scientific_outputs_modified": False,
        "scientific_csv_json_modified": False,
        "cache_modified": False,
        "checkpoint_modified": False,
        "diagnostic_dnbr_map": "omitted",
        "diagnostic_dnbr_note": DIAGNOSTIC_UNAVAILABLE_NOTE,
        "false_color_swir": "deferred_level_2",
        "human_review_started": False,
        "significant_burn_labels_created": False,
        "models_trained": False,
        "scientific_integrity": dict(scientific_integrity or {}),
    }


def _hash_index(lines: Sequence[str]) -> str:
    payload = ("\n".join(sorted(lines)) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scientific_bundle_integrity(manifest_path: Path | str, *, root: Path | str) -> dict[str, Any]:
    """Compare current scientific/visual bytes with the pre-v2 hash manifest."""

    manifest_file = Path(manifest_path)
    root_path = Path(root)
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    entries = list(payload.get("entries", []))
    scientific = [
        entry for entry in entries if entry.get("classification") in {"scientific_input", "scientific_output"}
    ]
    visual = [entry for entry in entries if entry.get("classification") == "visual_output"]

    def compare(selected: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        before: list[str] = []
        after: list[str] = []
        changed: list[str] = []
        for entry in selected:
            relative = str(entry["path"])
            path = root_path / relative
            before.append(f"{entry['sha256']}  {relative}")
            if not path.is_file():
                current = "MISSING"
            else:
                current = hashlib.sha256(path.read_bytes()).hexdigest()
            after.append(f"{current}  {relative}")
            if current != entry["sha256"]:
                changed.append(relative)
        return before, after, changed

    scientific_before, scientific_after, scientific_changed = compare(scientific)
    visual_before, visual_after, visual_changed = compare(visual)
    return {
        "manifest_path": str(manifest_file),
        "manifest_commit_sha": payload.get("commit_sha", ""),
        "manifest_entry_count": len(entries),
        "scientific_entry_count": len(scientific),
        "scientific_changed_count": len(scientific_changed),
        "scientific_changed_paths": scientific_changed,
        "scientific_index_sha256_before": _hash_index(scientific_before),
        "scientific_index_sha256_after": _hash_index(scientific_after),
        "visual_entry_count": len(visual),
        "visual_changed_count": len(visual_changed),
        "visual_changed_paths": visual_changed,
        "visual_index_sha256_before": _hash_index(visual_before),
        "visual_index_sha256_after": _hash_index(visual_after),
        "scientific_outputs_unchanged": not scientific_changed,
        "v1_visual_outputs_unchanged": not visual_changed,
    }


def quicklook_v2_report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# FirePA Quicklook v2 report",
        "",
        f"- Quicklook version: `{report['quicklook_version']}`",
        f"- Pipeline version: `{report['pipeline_version']}`",
        f"- Generated: `{report['generated_count']}/{report['requested_event_count']}`",
        "- Source mode: local PNG/CSV/JSON only; Earth Engine queries: `false`.",
        "- Scientific CSV/JSON, cache and checkpoint modified: `false`.",
        f"- Scientific bundle changed entries: `{report.get('scientific_integrity', {}).get('scientific_changed_count', 'n/a')}`.",
        "- Final PNG: RGB, 2048 × 1440, no scientific alpha channel.",
        "- Font: system Arial TrueType via Windows GDI; no font file copied to the repository.",
        "",
        "## Calibration events",
        "",
        "| event_id | main panel | temporal comparison | upload main | upload comparison | mask | diagnostic dNBR |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in report["results"]:
        if item.get("status") == "generated":
            mask = item.get("metadata", {}).get("valid_overlap_percent")
            mask_label = "compact inset" if mask is not None and float(mask) >= 98 else "full panel"
            lines.append(
                f"| `{item['event_id']}` | `{item['main_panel_path']}` | `{item['temporal_comparison_path']}` | `{item['review_upload_main_path']}` | `{item['review_upload_comparison_path']}` | {mask_label} | omitted: no local numeric raster |"
            )
        else:
            lines.append(f"| `{item.get('event_id', '')}` | FAILED | {item.get('error', '')} |  |  |  |  |")
    lines.extend(
        [
            "",
            "## Scientific boundary",
            "",
            "## Hash integrity",
            "",
            f"- Scientific index before: `{report.get('scientific_integrity', {}).get('scientific_index_sha256_before', 'n/a')}`",
            f"- Scientific index after: `{report.get('scientific_integrity', {}).get('scientific_index_sha256_after', 'n/a')}`",
            f"- Scientific outputs unchanged: `{report.get('scientific_integrity', {}).get('scientific_outputs_unchanged', 'n/a')}`",
            f"- v1 visual outputs unchanged: `{report.get('scientific_integrity', {}).get('v1_visual_outputs_unchanged', 'n/a')}`",
            "",
            f"{DESCRIPTIVE_WARNING}",
            "",
            f"{DIAGNOSTIC_UNAVAILABLE_NOTE}",
            "",
            f"{FALSE_COLOR_DEFERRED_NOTE}",
            "",
            "The temporal comparison keeps `selected_pair` and `window_median` separate. Because no local numeric `window_median` raster exists, that sheet is explicitly `metrics only`; it does not reuse or relink the selected-pair image.",
            "",
            "No human review, label creation, cohort expansion, 2026 data use, clustering change, or Earth Engine query occurred in this compositor run.",
            "",
        ]
    )
    return "\n".join(lines)


def write_quicklook_v2_report(path_json: Path | str, path_markdown: Path | str, report: Mapping[str, Any]) -> None:
    json_path = Path(path_json)
    markdown_path = Path(path_markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_temp = json_path.with_suffix(json_path.suffix + ".tmp")
    markdown_temp = markdown_path.with_suffix(markdown_path.suffix + ".tmp")
    json_temp.write_text(json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_temp.write_text(quicklook_v2_report_markdown(report), encoding="utf-8")
    json_temp.replace(json_path)
    markdown_temp.replace(markdown_path)
