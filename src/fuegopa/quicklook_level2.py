"""Controlled Level 2 multispectral evidence for the frozen FirePA pilot.

This module is deliberately separate from the v3 scientific pipeline and all
previous Quicklook versions.  It consumes the already-frozen local selection,
builds Earth Engine graphs for those exact scene IDs, downloads only the AOI,
validates the numeric GeoTIFFs locally, and writes Level 2 artifacts under new
paths.  It never updates v3 CSVs, caches, checkpoints, review queues, or
labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import struct
import subprocess
import time
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile
from io import BytesIO
from urllib.error import HTTPError

from . import dnbr_quicklook_v2 as _v2
from .dnbr_quicklook_v2 import scientific_bundle_integrity
from .dnbr_quicklook import RGBImage, encode_png
from .earth_engine import (
    CLOUD_SCORE_PLUS_COLLECTION,
    SENTINEL2_SR_COLLECTION,
    EarthEngineClient,
    EarthEngineQueryError,
)
from .sentinel2_dnbr import (
    ANALYSIS_MODES,
    AOI_ID,
    AOI_BUFFER_M,
    CLOUD_THRESHOLDS,
    DNBR_PIPELINE_VERSION,
    DNBR_THRESHOLDS,
    DnbrEventInput,
    DnbrValidationError,
    _scene_id,
    build_aoi,
    load_dnbr_inputs,
    read_utf8_csv,
)


QUICKLOOK_VERSION = "fuegopa-dnbr-quicklook-level2-v1"
PIPELINE_VERSION = DNBR_PIPELINE_VERSION
ANALYSIS_SCALE_M = 20
ANALYSIS_CRS = "EPSG:32617"
OUTPUT_CRS = "EPSG:4326"
PRIMARY_CLOUD_THRESHOLD = 0.50
GLOBAL_DNBR_RANGE = (-1.0, 1.0)
DIAGNOSTIC_DNBR_RANGE = (-0.25, 0.50)
RGB_REFLECTANCE_RANGE = (0.0, 3000.0)
RGB_GAMMA = 1.2
FALSE_COLOR_PERCENTILES = (2.0, 98.0)
REFLECTANCE_NODATA = 0.0
NUMERIC_NODATA = -9999.0
MASK_NODATA = 0
PANEL_WIDTH = 2048
PANEL_HEIGHT = 1440
COMPARISON_WIDTH = PANEL_WIDTH
COMPARISON_HEIGHT = PANEL_HEIGHT
RASTER_DIR = "outputs/rasters/sentinel2_level2/events"
FIGURE_DIR = "outputs/figures/sentinel2_dnbr_level2/events"
REVIEW_UPLOAD_DIR = "outputs/review_upload_level2"
REPORT_JSON = "outputs/quicklook_level2_report.json"
REPORT_MARKDOWN = "outputs/quicklook_level2_report.md"
MANIFEST_PATH = "outputs/manifests/firepa_quicklook_level2.sha256"

RGB_BANDS = ("B4", "B3", "B2")
FALSE_COLOR_BANDS = ("B12", "B8A", "B4")
MULTISPECTRAL_BANDS = ("B2", "B3", "B4", "B8A", "B8", "B12")
NUMERIC_BANDS = ("nbr_pre", "nbr_post", "dnbr")

POSITIVE_DNBR_NOTE = "Positive dNBR: spectral vegetation loss"
NEGATIVE_DNBR_NOTE = "Negative dNBR: spectral vegetation gain"
DESCRIPTIVE_WARNING = "dNBR is descriptive and not a confirmation of fire."
WINDOW_METRICS_ONLY = "metrics only; no local window_median raster is available"
FALSE_COLOR_DEFERRED_NOTE = (
    "Window false-color is deferred: selected-pair SWIR evidence is the controlled visual reference."
)

MASK_LEGEND = (
    {"label": "INVALID MASK", "color": "#c026d3", "meaning": "common valid mask value 0"},
    {"label": "VALID MASK", "color": "#0f766e", "meaning": "common valid mask value 1"},
    {"label": "AOI BOUNDARY", "color": "#ffd166", "meaning": "AOI boundary overlay"},
    {"label": "FIRMS DETECTION", "color": "#00e5ff", "meaning": "FIRMS detection overlay"},
    {
        "label": "GRAY: SPECTRAL NODATA/BG ONLY",
        "color": "#94a3b8",
        "meaning": "nodata/background in spectral layers; not a mask class",
    },
)

METRIC_TOLERANCES = {
    "dnbr_median": 0.005,
    "dnbr_p90": 0.005,
    # A 20 m boundary pixel is 0.04 ha.  The explicit 0.50 ha allowance
    # covers float32 thresholding plus the conservative AOI edge rasterization
    # while remaining a small fraction of the b0500 area.
    "area_ha": 0.50,
    "valid_overlap_fraction": 0.005,
    "pixel_count": 16,
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

# Protected paths are read and hashed only.  Level 2 paths are deliberately
# absent: they are the only generated artifact tree this module may create.
PROTECTED_FILES = (
    "data/processed/firms_cocle_2025_event_membership.csv",
    "data/processed/firms_cocle_2025_events_provisional.csv",
    "data/processed/sentinel2_observability_pilot_events.csv",
    "data/interim/sentinel2_scene_inventory.csv",
    "data/interim/sentinel2_aoi_inventory.csv",
    "data/interim/sentinel2_observability.csv",
    "data/interim/sentinel2_observability_checkpoint.json",
    "data/interim/sentinel2_dnbr_event_metrics.csv",
    "data/interim/sentinel2_dnbr_errors.csv",
    "data/interim/sentinel2_dnbr_checkpoint.json",
    "outputs/sentinel2_event_pair_selection.csv",
    "outputs/sentinel2_dnbr_sensitivity.csv",
    "outputs/sentinel2_dnbr_review_queue.csv",
    "outputs/sentinel2_dnbr_report.json",
    "outputs/sentinel2_dnbr_report.md",
    "outputs/quicklook_v2_report.json",
    "outputs/quicklook_v2_report.md",
    "outputs/quicklook_v2_1_report.json",
    "outputs/quicklook_v2_1_report.md",
    "outputs/manifests/firepa_active_bundle_2026-07-21.json",
)
PROTECTED_DIRS = (
    "data/interim/sentinel2_dnbr_cache",
    "data/interim/sentinel2_observability_cache",
    "outputs/figures/sentinel2_dnbr/events",
    "outputs/figures/sentinel2_dnbr_v2",
    "outputs/review_upload_v2",
    "outputs/figures/sentinel2_dnbr_v2_1",
    "outputs/review_upload_v2_1",
)


class Level2ValidationError(RuntimeError):
    """Raised when a Level 2 export or local reconciliation is unsafe."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.details = dict(details or {})
        super().__init__(message)


class Level2MetricMismatch(Level2ValidationError):
    """Raised when a local GeoTIFF metric exceeds the declared tolerance."""


@dataclass(frozen=True)
class Level2Graph:
    pre_source: Any
    post_source: Any
    pre_bands: Any
    post_bands: Any
    pre_valid_mask: Any
    post_valid_mask: Any
    common_valid_mask: Any
    pre_nbr: Any
    post_nbr: Any
    dnbr: Any


@dataclass(frozen=True)
class GeoTiffRaster:
    path: Path
    width: int
    height: int
    band_count: int
    bits_per_sample: int
    sample_format: int
    compression: int
    dtype: str
    data: tuple[tuple[float, ...], ...]
    transform: tuple[float, float, float, float, float, float] | None
    crs: str | None
    nodata: float | int | None

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    @property
    def pixel_area_m2(self) -> float:
        if self.transform is None:
            return float(ANALYSIS_SCALE_M * ANALYSIS_SCALE_M)
        return abs(float(self.transform[0]) * float(self.transform[4]))


@dataclass
class QueryTracker:
    smoke_queries: int = 0
    download_queries: int = 0
    geometry_queries: int = 0

    @property
    def total_queries(self) -> int:
        return self.smoke_queries + self.download_queries + self.geometry_queries


@dataclass(frozen=True)
class EventExport:
    event_id: str
    raster_paths: Mapping[str, Path]
    window_available: bool
    window_reason: str
    export_metadata_path: Path
    selected_local_metrics: Mapping[str, Any]
    window_local_metrics: Mapping[str, Any] | None
    selected_comparison: Mapping[str, Any]
    window_comparison: Mapping[str, Any] | None


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _format_timestamp(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_index(lines: Iterable[str]) -> str:
    payload = ("\n".join(sorted(lines)) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _git_value(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def preflight_git(root: Path) -> dict[str, Any]:
    status = _git_value(root, "status", "--porcelain")
    return {
        "branch": _git_value(root, "branch", "--show-current"),
        "head": _git_value(root, "rev-parse", "HEAD"),
        "status_clean": not bool(status),
        "status_porcelain": status,
        "staged_diff": _git_value(root, "diff", "--cached", "--name-only"),
        "unstaged_diff": _git_value(root, "diff", "--name-only"),
    }


def protected_snapshot(root: Path) -> dict[str, Any]:
    relative_paths: set[str] = set(PROTECTED_FILES)
    missing: list[str] = []
    for relative in PROTECTED_DIRS:
        directory = root / relative
        if not directory.is_dir():
            missing.append(relative + "/")
            continue
        relative_paths.update(
            path.relative_to(root).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        )
    entries: list[dict[str, str]] = []
    for relative in sorted(relative_paths):
        path = root / relative
        if not path.is_file():
            if relative in PROTECTED_FILES:
                missing.append(relative)
            continue
        entries.append({"path": relative, "sha256": _hash_file(path)})
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    return {
        "index_sha256": _hash_index(lines),
        "entry_count": len(entries),
        "entries": entries,
        "missing_paths": sorted(set(missing)),
    }


def compare_protected_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
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


def level2_visual_snapshot(root: Path) -> dict[str, Any]:
    paths = (
        "outputs/figures/sentinel2_dnbr_level2",
        "outputs/review_upload_level2",
        REPORT_JSON,
        REPORT_MARKDOWN,
        MANIFEST_PATH,
    )
    entries: list[dict[str, str]] = []
    missing: list[str] = []
    for relative in paths:
        path = root / relative
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    rel = child.relative_to(root).as_posix()
                    entries.append({"path": rel, "sha256": _hash_file(child)})
        elif path.is_file():
            entries.append({"path": relative, "sha256": _hash_file(path)})
        else:
            missing.append(relative)
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    return {
        "index_sha256": _hash_index(lines),
        "entry_count": len(entries),
        "entries": entries,
        "missing_paths": sorted(missing),
    }


def _compare_index_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_map = {str(item["path"]): str(item["sha256"]) for item in before.get("entries", [])}
    after_map = {str(item["path"]): str(item["sha256"]) for item in after.get("entries", [])}
    changed = [
        path for path in sorted(set(before_map) | set(after_map)) if before_map.get(path) != after_map.get(path)
    ]
    return {
        "before_index_sha256": before.get("index_sha256", ""),
        "after_index_sha256": after.get("index_sha256", ""),
        "before_entry_count": before.get("entry_count", 0),
        "after_entry_count": after.get("entry_count", 0),
        "before_missing_paths": list(before.get("missing_paths", [])),
        "after_missing_paths": list(after.get("missing_paths", [])),
        "changed_count": len(changed),
        "changed_paths": changed,
        "all_unchanged": not changed,
    }


# TIFF field types used by Earth Engine's small GeoTIFF downloads.
_TIFF_TYPES: dict[int, tuple[int, str | None]] = {
    1: (1, "B"),      # BYTE
    2: (1, None),     # ASCII
    3: (2, "H"),      # SHORT
    4: (4, "I"),      # LONG
    5: (8, None),     # RATIONAL
    6: (1, "b"),      # SBYTE
    7: (1, "B"),      # UNDEFINED
    8: (2, "h"),      # SSHORT
    9: (4, "i"),      # SLONG
    10: (8, None),     # SRATIONAL
    11: (4, "f"),     # FLOAT
    12: (8, "d"),     # DOUBLE
    16: (8, "Q"),     # LONG8
    17: (8, "q"),     # SLONG8
    18: (8, "Q"),     # IFD8
}

_TAG_IMAGE_WIDTH = 256
_TAG_IMAGE_LENGTH = 257
_TAG_BITS_PER_SAMPLE = 258
_TAG_COMPRESSION = 259
_TAG_PHOTOMETRIC = 262
_TAG_STRIP_OFFSETS = 273
_TAG_SAMPLES_PER_PIXEL = 277
_TAG_ROWS_PER_STRIP = 278
_TAG_STRIP_BYTE_COUNTS = 279
_TAG_PLANAR_CONFIGURATION = 284
_TAG_PREDICTOR = 317
_TAG_TILE_WIDTH = 322
_TAG_TILE_LENGTH = 323
_TAG_TILE_OFFSETS = 324
_TAG_TILE_BYTE_COUNTS = 325
_TAG_MODEL_PIXEL_SCALE = 33550
_TAG_MODEL_TIEPOINT = 33922
_TAG_MODEL_TRANSFORMATION = 34264
_TAG_GEO_KEY_DIRECTORY = 34735
_TAG_GDAL_NODATA = 42113
_TAG_SAMPLE_FORMAT = 339


def _tiff_unpack(raw: bytes, endian: str, field_type: int, count: int, offset: int) -> list[Any]:
    if field_type not in _TIFF_TYPES:
        raise Level2ValidationError(f"Unsupported GeoTIFF field type: {field_type}")
    size, format_code = _TIFF_TYPES[field_type]
    total = size * count
    if offset < 0 or offset + total > len(raw):
        raise Level2ValidationError("GeoTIFF field points outside the downloaded payload")
    payload = raw[offset : offset + total]
    if field_type == 2:
        return [payload.rstrip(b"\x00").decode("ascii", errors="replace")]
    if field_type in {5, 10}:
        values: list[Any] = []
        for index in range(count):
            numerator, denominator = struct.unpack_from(endian + ("II" if field_type == 5 else "ii"), payload, index * size)
            values.append((numerator, denominator))
        return values
    if format_code is None:
        return [payload]
    return list(struct.unpack(endian + (format_code * count), payload))


def _tiff_ifd(raw: bytes) -> tuple[str, dict[int, list[Any]]]:
    if len(raw) < 8 or raw[:2] not in {b"II", b"MM"}:
        raise Level2ValidationError("Downloaded payload is not a TIFF")
    endian = "<" if raw[:2] == b"II" else ">"
    if struct.unpack_from(endian + "H", raw, 2)[0] != 42:
        raise Level2ValidationError("GeoTIFF magic number is invalid")
    ifd_offset = struct.unpack_from(endian + "I", raw, 4)[0]
    if ifd_offset + 2 > len(raw):
        raise Level2ValidationError("GeoTIFF IFD is outside the downloaded payload")
    entry_count = struct.unpack_from(endian + "H", raw, ifd_offset)[0]
    entries: dict[int, list[Any]] = {}
    cursor = ifd_offset + 2
    for _ in range(entry_count):
        if cursor + 12 > len(raw):
            raise Level2ValidationError("GeoTIFF IFD is truncated")
        tag, field_type = struct.unpack_from(endian + "HH", raw, cursor)
        count = struct.unpack_from(endian + "I", raw, cursor + 4)[0]
        size = _TIFF_TYPES.get(field_type, (0, None))[0]
        total = size * count
        value_offset = cursor + 8 if total <= 4 else struct.unpack_from(endian + "I", raw, cursor + 8)[0]
        entries[tag] = _tiff_unpack(raw, endian, field_type, count, value_offset)
        cursor += 12
    return endian, entries


def _tag_one(tags: Mapping[int, Sequence[Any]], tag: int, default: Any = None) -> Any:
    values = tags.get(tag)
    if not values:
        return default
    return values[0]


def _geo_key_crs(tags: Mapping[int, Sequence[Any]]) -> str | None:
    values = tags.get(_TAG_GEO_KEY_DIRECTORY)
    if not values or len(values) < 4:
        return None
    number_of_keys = int(values[3])
    for index in range(number_of_keys):
        start = 4 + index * 4
        if start + 4 > len(values):
            break
        key_id, tiff_tag, count, value_offset = (int(item) for item in values[start : start + 4])
        if key_id not in {2048, 3072} or count < 1:
            continue
        value: Any = value_offset
        if tiff_tag:
            selected = tags.get(tiff_tag, [])
            if selected:
                value = selected[min(value_offset, len(selected) - 1)]
        try:
            code = int(value)
        except (TypeError, ValueError):
            continue
        if code > 0:
            return f"EPSG:{code}"
    return None


def _dtype(sample_format: int, bits: int) -> str:
    if sample_format == 3 and bits == 32:
        return "float32"
    if sample_format == 3 and bits == 64:
        return "float64"
    if sample_format == 1 and bits == 8:
        return "uint8"
    if sample_format == 1 and bits == 16:
        return "uint16"
    if sample_format == 1 and bits == 32:
        return "uint32"
    if sample_format == 2 and bits == 16:
        return "int16"
    if sample_format == 2 and bits == 32:
        return "int32"
    return f"sample_format_{sample_format}_bits_{bits}"


def _decode_strip_values(payload: bytes, endian: str, sample_format: int, bits: int, count: int) -> list[float]:
    if bits not in {8, 16, 32, 64}:
        raise Level2ValidationError(f"Unsupported GeoTIFF sample width: {bits}")
    if sample_format == 1:
        code = {8: "B", 16: "H", 32: "I", 64: "Q"}[bits]
    elif sample_format == 2:
        code = {8: "b", 16: "h", 32: "i", 64: "q"}[bits]
    elif sample_format == 3:
        code = {32: "f", 64: "d"}.get(bits, "")
        if not code:
            raise Level2ValidationError(f"Unsupported float GeoTIFF sample width: {bits}")
    else:
        raise Level2ValidationError(f"Unsupported GeoTIFF sample format: {sample_format}")
    size = bits // 8
    expected = count * size
    if len(payload) < expected:
        raise Level2ValidationError("GeoTIFF strip is shorter than its declared samples")
    return [float(value) for value in struct.unpack(endian + code * count, payload[:expected])]


def read_geotiff(path: Path, *, nodata: float | int | None = None) -> GeoTiffRaster:
    """Read the tiled/striped deflate GeoTIFFs returned by EE downloads."""

    raw = path.read_bytes()
    endian, tags = _tiff_ifd(raw)
    width = int(_tag_one(tags, _TAG_IMAGE_WIDTH, 0))
    height = int(_tag_one(tags, _TAG_IMAGE_LENGTH, 0))
    bands = int(_tag_one(tags, _TAG_SAMPLES_PER_PIXEL, 1))
    bits_values = [int(value) for value in tags.get(_TAG_BITS_PER_SAMPLE, [])]
    bits = bits_values[0] if bits_values else 0
    if width <= 0 or height <= 0 or not bits or any(value != bits for value in bits_values):
        raise Level2ValidationError(f"Invalid GeoTIFF dimensions or BitsPerSample: {path}")
    compression = int(_tag_one(tags, _TAG_COMPRESSION, 1))
    sample_format = int(_tag_one(tags, _TAG_SAMPLE_FORMAT, 1))
    planar = int(_tag_one(tags, _TAG_PLANAR_CONFIGURATION, 1))
    if planar != 1:
        raise Level2ValidationError("Only chunky GeoTIFF planar configuration is supported")
    data = [[0.0] * (width * height) for _ in range(bands)]
    predictor = int(_tag_one(tags, _TAG_PREDICTOR, 1))
    if _TAG_TILE_OFFSETS in tags or _TAG_TILE_BYTE_COUNTS in tags:
        offsets = [int(value) for value in tags.get(_TAG_TILE_OFFSETS, [])]
        byte_counts = [int(value) for value in tags.get(_TAG_TILE_BYTE_COUNTS, [])]
        tile_width = int(_tag_one(tags, _TAG_TILE_WIDTH, 0))
        tile_height = int(_tag_one(tags, _TAG_TILE_LENGTH, 0))
        if not offsets or len(offsets) != len(byte_counts) or tile_width <= 0 or tile_height <= 0:
            raise Level2ValidationError(f"GeoTIFF tile metadata is incomplete: {path}")
        tiles_across = (width + tile_width - 1) // tile_width
        tiles_down = (height + tile_height - 1) // tile_height
        expected_tiles = tiles_across * tiles_down
        if len(offsets) != expected_tiles:
            raise Level2ValidationError(
                f"GeoTIFF tile count is inconsistent: {len(offsets)} != {expected_tiles}"
            )
        tile_sample_count = tile_width * bands
        for tile_index, (tile_offset, byte_count) in enumerate(zip(offsets, byte_counts)):
            if tile_offset + byte_count > len(raw):
                raise Level2ValidationError("GeoTIFF tile points outside downloaded payload")
            tile = raw[tile_offset : tile_offset + byte_count]
            if compression in {8, 32946}:
                tile = zlib.decompress(tile)
            elif compression != 1:
                raise Level2ValidationError(f"Unsupported GeoTIFF compression: {compression}")
            values = _decode_strip_values(
                tile,
                endian,
                sample_format,
                bits,
                tile_width * tile_height * bands,
            )
            if predictor == 2:
                for row in range(tile_height):
                    row_start = row * tile_sample_count
                    for offset in range(bands, tile_sample_count):
                        values[row_start + offset] += values[row_start + offset - bands]
            elif predictor != 1:
                raise Level2ValidationError(f"Unsupported GeoTIFF predictor: {predictor}")
            tile_x = (tile_index % tiles_across) * tile_width
            tile_y = (tile_index // tiles_across) * tile_height
            for local_y in range(tile_height):
                target_y = tile_y + local_y
                if target_y >= height:
                    continue
                source_start = local_y * tile_sample_count
                for local_x in range(tile_width):
                    target_x = tile_x + local_x
                    if target_x >= width:
                        continue
                    for band in range(bands):
                        data[band][target_y * width + target_x] = values[
                            source_start + local_x * bands + band
                        ]
    else:
        offsets = [int(value) for value in tags.get(_TAG_STRIP_OFFSETS, [])]
        byte_counts = [int(value) for value in tags.get(_TAG_STRIP_BYTE_COUNTS, [])]
        rows_per_strip = int(_tag_one(tags, _TAG_ROWS_PER_STRIP, height))
        if not offsets or len(offsets) != len(byte_counts) or rows_per_strip <= 0:
            raise Level2ValidationError(f"GeoTIFF strip metadata is incomplete: {path}")
        row_sample_count = width * bands
        row_index = 0
        for strip_offset, byte_count in zip(offsets, byte_counts):
            if strip_offset + byte_count > len(raw):
                raise Level2ValidationError("GeoTIFF strip points outside downloaded payload")
            strip = raw[strip_offset : strip_offset + byte_count]
            if compression in {8, 32946}:
                strip = zlib.decompress(strip)
            elif compression != 1:
                raise Level2ValidationError(f"Unsupported GeoTIFF compression: {compression}")
            rows = min(rows_per_strip, height - row_index)
            values = _decode_strip_values(strip, endian, sample_format, bits, rows * row_sample_count)
            if predictor == 2:
                for row in range(rows):
                    row_start = row * row_sample_count
                    for offset in range(bands, row_sample_count):
                        values[row_start + offset] += values[row_start + offset - bands]
            elif predictor != 1:
                raise Level2ValidationError(f"Unsupported GeoTIFF predictor: {predictor}")
            for row in range(rows):
                source_start = row * row_sample_count
                target_row = row_index + row
                for x in range(width):
                    for band in range(bands):
                        data[band][target_row * width + x] = values[source_start + x * bands + band]
            row_index += rows
        if row_index != height:
            raise Level2ValidationError("GeoTIFF strips do not cover the declared image height")
    scale_values = [float(value) for value in tags.get(_TAG_MODEL_PIXEL_SCALE, [])]
    tie_values = [float(value) for value in tags.get(_TAG_MODEL_TIEPOINT, [])]
    transform = None
    if len(scale_values) >= 2 and len(tie_values) >= 6:
        transform = (
            scale_values[0],
            0.0,
            tie_values[3],
            0.0,
            -abs(scale_values[1]),
            tie_values[4],
        )
    if transform is None:
        matrix_values = [float(value) for value in tags.get(_TAG_MODEL_TRANSFORMATION, [])]
        if len(matrix_values) >= 16:
            transform = (
                matrix_values[0],
                matrix_values[1],
                matrix_values[3],
                matrix_values[4],
                matrix_values[5],
                matrix_values[7],
            )
    nodata_value: float | int | None = nodata
    if _TAG_GDAL_NODATA in tags:
        try:
            text_value = str(_tag_one(tags, _TAG_GDAL_NODATA)).strip()
            parsed_nodata = float(text_value)
            if math.isfinite(parsed_nodata):
                nodata_value = parsed_nodata
            elif nodata is not None:
                # Earth Engine can serialize the float32 fill metadata as
                # -Infinity even when the downloaded pixels contain the
                # requested -9999 fill.  Keep the explicit Level 2 contract
                # value for validation and metric filtering.
                nodata_value = nodata
            else:
                nodata_value = NUMERIC_NODATA
        except (TypeError, ValueError):
            pass
    return GeoTiffRaster(
        path=path,
        width=width,
        height=height,
        band_count=bands,
        bits_per_sample=bits,
        sample_format=sample_format,
        compression=compression,
        dtype=_dtype(sample_format, bits),
        data=tuple(tuple(channel) for channel in data),
        transform=transform,
        crs=_geo_key_crs(tags),
        nodata=nodata_value,
    )


def _extract_tiff_payload(payload: bytes) -> bytes:
    if payload[:2] != b"PK":
        return payload
    with ZipFile(BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.casefold().endswith((".tif", ".tiff"))]
        if len(names) != 1:
            raise Level2ValidationError(f"Expected one GeoTIFF in Earth Engine ZIP, found {len(names)}")
        return archive.read(names[0])


def _validate_raster_contract(
    raster: GeoTiffRaster,
    *,
    expected_bands: int,
    expected_dtype: str,
    nodata: float | int,
) -> None:
    if raster.band_count != expected_bands:
        raise Level2ValidationError(
            f"{raster.path.name}: expected {expected_bands} bands, received {raster.band_count}"
        )
    if expected_dtype == "float32" and raster.dtype != "float32":
        raise Level2ValidationError(f"{raster.path.name}: expected float32, received {raster.dtype}")
    if expected_dtype == "uint8" and raster.dtype != "uint8":
        raise Level2ValidationError(f"{raster.path.name}: expected uint8, received {raster.dtype}")
    if expected_dtype == "uint16" and raster.dtype != "uint16":
        raise Level2ValidationError(f"{raster.path.name}: expected uint16, received {raster.dtype}")
    if raster.crs not in {None, ANALYSIS_CRS}:
        raise Level2ValidationError(f"{raster.path.name}: expected {ANALYSIS_CRS}, received {raster.crs}")
    if raster.transform is None:
        raise Level2ValidationError(f"{raster.path.name}: CRS transform is absent")
    if raster.width <= 0 or raster.height <= 0:
        raise Level2ValidationError(f"{raster.path.name}: invalid dimensions")
    # Earth Engine may omit GDAL_NODATA in its download tag; the sidecar
    # contract still records the exact fill value used in the request.
    nodata_compatible = (
        expected_dtype == "float32"
        and float(nodata) == 0.0
        and raster.nodata is not None
        and math.isclose(float(raster.nodata), NUMERIC_NODATA, abs_tol=1e-6)
    )
    if (
        raster.nodata is not None
        and not nodata_compatible
        and not math.isclose(float(raster.nodata), float(nodata), abs_tol=1e-6)
    ):
        raise Level2ValidationError(
            f"{raster.path.name}: nodata mismatch {raster.nodata} != {nodata}"
        )


def _ee_linked_scene(client: EarthEngineClient, scene_id: str) -> Any:
    ee = client.ee_module
    image = ee.Image(scene_id)
    return image.linkCollection(
        client.image_collection(CLOUD_SCORE_PLUS_COLLECTION),
        linkedBands=["cs", "cs_cdf"],
        linkedProperties=["MODEL_VERSION", "NO_CONTEXT_FRACTION"],
        matchPropertyName="system:index",
    )


def _masked_multispectral(image: Any, threshold: float, ee: Any) -> tuple[Any, Any]:
    bands = image.select(list(MULTISPECTRAL_BANDS))
    # Keep the v3 scientific support contract: validity is defined by B8/B12
    # plus CS+, while the additional RGB/SWIR bands are carried as visual
    # evidence on that same support.
    spectral_valid = image.select(["B8", "B12"]).mask().reduce(ee.Reducer.min()).gt(0)
    cs_cdf = image.select("cs_cdf")
    cs_valid = cs_cdf.mask().And(cs_cdf.gte(threshold))
    valid = spectral_valid.And(cs_valid).rename("valid")
    return bands.updateMask(valid), valid.selfMask()


def _nbr_from_bands(bands: Any, ee: Any) -> Any:
    b8 = bands.select("B8")
    b12 = bands.select("B12")
    denominator = b8.add(b12)
    return b8.subtract(b12).divide(denominator).updateMask(denominator.neq(0)).rename("nbr")


def _composite_multispectral(
    client: EarthEngineClient,
    scene_ids: Sequence[str],
    threshold: float,
) -> tuple[Any, Any]:
    if not scene_ids:
        raise DnbrValidationError("window_median requiere al menos una escena por lado")
    ee = client.ee_module
    masked_images = []
    for scene_id in scene_ids:
        linked = _ee_linked_scene(client, scene_id)
        bands, _ = _masked_multispectral(linked, threshold, ee)
        masked_images.append(bands)
    composite = ee.ImageCollection.fromImages(masked_images).median()
    valid = composite.mask().reduce(ee.Reducer.min()).rename("valid").selfMask()
    return composite, valid


def build_level2_graph(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    *,
    analysis_mode: str,
    cloud_threshold: float = PRIMARY_CLOUD_THRESHOLD,
) -> Level2Graph:
    """Build selected-pair or frozen-window graph without resolving it."""

    if analysis_mode not in ANALYSIS_MODES:
        raise Level2ValidationError(f"Unsupported Level 2 analysis mode: {analysis_mode}")
    if cloud_threshold not in CLOUD_THRESHOLDS:
        raise Level2ValidationError(f"Unsupported Cloud Score+ threshold: {cloud_threshold}")
    ee = client.ee_module
    if analysis_mode == "selected_pair":
        pre_source = _ee_linked_scene(client, event_input.pre_scene_id)
        post_source = _ee_linked_scene(client, event_input.post_scene_id)
        pre_bands, pre_valid = _masked_multispectral(pre_source, cloud_threshold, ee)
        post_bands, post_valid = _masked_multispectral(post_source, cloud_threshold, ee)
    else:
        pre_source = None
        post_source = None
        pre_bands, pre_valid = _composite_multispectral(
            client,
            [_scene_id(row) for row in event_input.pre_candidates],
            cloud_threshold,
        )
        post_bands, post_valid = _composite_multispectral(
            client,
            [_scene_id(row) for row in event_input.post_candidates],
            cloud_threshold,
        )
    common_valid = pre_valid.And(post_valid).rename("common").selfMask()
    pre_nbr = _nbr_from_bands(pre_bands, ee).updateMask(common_valid)
    post_nbr = _nbr_from_bands(post_bands, ee).updateMask(common_valid)
    dnbr = pre_nbr.subtract(post_nbr).rename("dnbr").updateMask(common_valid)
    return Level2Graph(
        pre_source=pre_source,
        post_source=post_source,
        pre_bands=pre_bands,
        post_bands=post_bands,
        pre_valid_mask=pre_valid,
        post_valid_mask=post_valid,
        common_valid_mask=common_valid,
        pre_nbr=pre_nbr,
        post_nbr=post_nbr,
        dnbr=dnbr,
    )


def _download_url_payload(
    client: EarthEngineClient,
    image: Any,
    *,
    name: str,
    region: Any,
    tracker: QueryTracker,
) -> bytes:
    parameters = {
        "name": name,
        "region": region,
        "scale": ANALYSIS_SCALE_M,
        "crs": ANALYSIS_CRS,
        "format": "GEO_TIFF",
        "filePerBand": False,
    }
    payload: bytes | None = None
    for attempt in range(3):
        try:
            url = image.getDownloadURL(parameters)
            tracker.download_queries += 1
            with urllib.request.urlopen(url, timeout=240) as response:
                payload = response.read()
            break
        except EarthEngineQueryError:
            raise
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= 2:
                raise EarthEngineQueryError.from_exception(
                    exc,
                    operation=f"Level 2 GeoTIFF export {name}",
                    error_stage="level2_export",
                ) from exc
            time.sleep(2.0 * (attempt + 1))
        except Exception as exc:
            raise EarthEngineQueryError.from_exception(
                exc,
                operation=f"Level 2 GeoTIFF export {name}",
                error_stage="level2_export",
            ) from exc
    if payload is None:
        raise Level2ValidationError(f"No payload returned for Level 2 export {name}")
    payload = _extract_tiff_payload(payload)
    if payload[:2] not in {b"II", b"MM"}:
        raise Level2ValidationError(f"Earth Engine returned a non-TIFF payload for {name}")
    return payload


def _download_raster(
    client: EarthEngineClient,
    image: Any,
    *,
    path: Path,
    name: str,
    region: Any,
    tracker: QueryTracker,
) -> GeoTiffRaster:
    payload = _download_url_payload(client, image, name=name, region=region, tracker=tracker)
    _write_bytes_atomic(path, payload)
    return read_geotiff(path)


def _point_in_ring(x: float, y: float, ring: Sequence[Sequence[float]]) -> bool:
    """Return a boundary-inclusive point-in-ring result for UTM coordinates."""

    inside = False
    for index, current in enumerate(ring):
        previous = ring[index - 1]
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) <= 1e-7 and min(x1, x2) - 1e-7 <= x <= max(x1, x2) + 1e-7 and min(y1, y2) - 1e-7 <= y <= max(y1, y2) + 1e-7:
            return True
        intersects = (y1 > y) != (y2 > y)
        if intersects:
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= crossing_x:
                inside = not inside
    return inside


def _point_in_polygon(x: float, y: float, polygon: Sequence[Sequence[Sequence[float]]]) -> bool:
    if not polygon or not _point_in_ring(x, y, polygon[0]):
        return False
    return not any(_point_in_ring(x, y, ring) for ring in polygon[1:])


def _point_in_geometry(x: float, y: float, geometry: Mapping[str, Any]) -> bool:
    geometry_type = str(geometry.get("type") or "")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return _point_in_polygon(x, y, coordinates)
    if geometry_type == "MultiPolygon":
        return any(_point_in_polygon(x, y, polygon) for polygon in coordinates)
    raise Level2ValidationError(f"Unsupported frozen AOI geometry type: {geometry_type}")


def _local_aoi_support_values(geometry: Mapping[str, Any], raster: GeoTiffRaster) -> list[int]:
    """Rasterize the exact frozen EE UTM geometry on the returned analysis grid."""

    if raster.transform is None:
        raise Level2ValidationError("Cannot rasterize AOI support without a GeoTIFF transform")
    a, b, c, d, e, f = raster.transform
    values: list[int] = []
    for y in range(raster.height):
        for x in range(raster.width):
            pixel_x = a * (x + 0.5) + b * (y + 0.5) + c
            pixel_y = d * (x + 0.5) + e * (y + 0.5) + f
            values.append(1 if _point_in_geometry(pixel_x, pixel_y, geometry) else 0)
    return values


def _write_uint8_geotiff(
    path: Path,
    *,
    width: int,
    height: int,
    values: Sequence[int],
    transform: tuple[float, float, float, float, float, float] | None,
) -> None:
    """Write the small one-band AOI support surface without a raster library."""

    if len(values) != width * height or transform is None:
        raise Level2ValidationError("Invalid local AOI support dimensions or transform")
    endian = "<"
    pixel_scale = [abs(float(transform[0])), abs(float(transform[4])), 0.0]
    tiepoint = [0.0, 0.0, 0.0, float(transform[2]), float(transform[5]), 0.0]
    geokeys = [1, 1, 0, 1, 3072, 0, 1, 32617]
    tags: list[tuple[int, int, int, bytes]] = [
        (256, 4, 1, struct.pack(endian + "I", width)),
        (257, 4, 1, struct.pack(endian + "I", height)),
        (258, 3, 1, struct.pack(endian + "H", 8)),
        (259, 3, 1, struct.pack(endian + "H", 1)),
        (262, 3, 1, struct.pack(endian + "H", 1)),
        (273, 4, 1, b""),
        (277, 3, 1, struct.pack(endian + "H", 1)),
        (278, 4, 1, struct.pack(endian + "I", height)),
        (279, 4, 1, struct.pack(endian + "I", width * height)),
        (284, 3, 1, struct.pack(endian + "H", 1)),
        (33550, 12, 3, struct.pack(endian + "3d", *pixel_scale)),
        (339, 3, 1, struct.pack(endian + "H", 1)),
        (33922, 12, 6, struct.pack(endian + "6d", *tiepoint)),
        (34735, 3, len(geokeys), struct.pack(endian + "8H", *geokeys)),
        (42113, 2, 4, b"0.0\x00"),
    ]
    tags.sort(key=lambda item: item[0])
    ifd_offset = 8
    ifd_size = 2 + len(tags) * 12 + 4
    extra_offset = ifd_offset + ifd_size
    extra = bytearray()
    entries: list[bytes] = []
    for tag, field_type, count, field_payload in tags:
        field_size = {2: 1, 3: 2, 4: 4, 12: 8}[field_type]
        total = field_size * count
        if total <= 4:
            inline = field_payload + b"\x00" * (4 - len(field_payload))
            entries.append(struct.pack(endian + "HHI4s", tag, field_type, count, inline))
        else:
            field_offset = extra_offset + len(extra)
            extra.extend(field_payload)
            entries.append(struct.pack(endian + "HHII", tag, field_type, count, field_offset))
    strip_offset = extra_offset + len(extra)
    entries = [
        entry
        if struct.unpack_from(endian + "H", entry, 0)[0] != 273
        else struct.pack(endian + "HHII", 273, 4, 1, strip_offset)
        for entry in entries
    ]
    raw = bytearray(b"II" + struct.pack(endian + "H", 42) + struct.pack(endian + "I", ifd_offset))
    raw.extend(struct.pack(endian + "H", len(entries)))
    raw.extend(b"".join(entries))
    raw.extend(struct.pack(endian + "I", 0))
    raw.extend(extra)
    raw.extend(bytes(max(0, min(255, int(value))) for value in values))
    _write_bytes_atomic(path, bytes(raw))


def _download_images_for_event(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    graph: Level2Graph,
    *,
    output_dir: Path,
    prefix: str,
    tracker: QueryTracker,
    aoi: Any | None = None,
    aoi_geometry_utm: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    aoi = aoi or build_aoi(event_input.event, AOI_BUFFER_M, client)
    if aoi_geometry_utm is None:
        raise Level2ValidationError("Exact frozen AOI UTM geometry is required for Level 2 support")
    ee = client.ee_module
    region = aoi.geometry_wgs84
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def export(key: str, image: Any, *, bands: int, dtype: str, nodata: float | int) -> None:
        path = output_dir / f"{prefix}_{key}.tif"
        prepared = image
        raster = _download_raster(
            client,
            prepared,
            path=path,
            name=f"{prefix}_{key}",
            region=region,
            tracker=tracker,
        )
        _validate_raster_contract(raster, expected_bands=bands, expected_dtype=dtype, nodata=nodata)
        paths[key] = path

    pre_valid = graph.pre_valid_mask
    post_valid = graph.post_valid_mask
    common = graph.common_valid_mask
    export(
        "rgb_pre",
        graph.pre_bands.select(list(RGB_BANDS)).updateMask(pre_valid).unmask(REFLECTANCE_NODATA).toUint16(),
        bands=3,
        dtype="uint16",
        nodata=REFLECTANCE_NODATA,
    )
    export(
        "rgb_post",
        graph.post_bands.select(list(RGB_BANDS)).updateMask(post_valid).unmask(REFLECTANCE_NODATA).toUint16(),
        bands=3,
        dtype="uint16",
        nodata=REFLECTANCE_NODATA,
    )
    export(
        "false_color_pre",
        graph.pre_bands.select(list(FALSE_COLOR_BANDS)).updateMask(pre_valid).unmask(REFLECTANCE_NODATA).toUint16(),
        bands=3,
        dtype="uint16",
        nodata=REFLECTANCE_NODATA,
    )
    export(
        "false_color_post",
        graph.post_bands.select(list(FALSE_COLOR_BANDS)).updateMask(post_valid).unmask(REFLECTANCE_NODATA).toUint16(),
        bands=3,
        dtype="uint16",
        nodata=REFLECTANCE_NODATA,
    )
    export("nbr_pre", graph.pre_nbr.unmask(NUMERIC_NODATA).toFloat(), bands=1, dtype="float32", nodata=NUMERIC_NODATA)
    export("nbr_post", graph.post_nbr.unmask(NUMERIC_NODATA).toFloat(), bands=1, dtype="float32", nodata=NUMERIC_NODATA)
    export("dnbr", graph.dnbr.unmask(NUMERIC_NODATA).toFloat(), bands=1, dtype="float32", nodata=NUMERIC_NODATA)
    export("common_valid_mask", common.unmask(MASK_NODATA).byte(), bands=1, dtype="uint8", nodata=MASK_NODATA)
    # The EE AOI support is used by the frozen v3 reduceRegion contract.  A
    # direct getDownloadURL of a clipped constant can rasterize the polygon on
    # the export bounding box with a different edge convention, so the Level 2
    # support is rasterized locally onto the exact returned EPSG:32617 grid.
    # This is a geometry-only support surface; all spectral/numeric surfaces
    # above remain controlled EE downloads.
    reference = read_geotiff(paths["rgb_pre"], nodata=REFLECTANCE_NODATA)
    support_values = _local_aoi_support_values(aoi_geometry_utm, reference)
    support_path = output_dir / f"{prefix}_aoi_support.tif"
    _write_uint8_geotiff(
        support_path,
        width=reference.width,
        height=reference.height,
        values=support_values,
        transform=reference.transform,
    )
    support_raster = read_geotiff(support_path, nodata=0)
    _validate_raster_contract(support_raster, expected_bands=1, expected_dtype="uint8", nodata=0)
    paths["aoi_support"] = support_path
    return paths


def export_selected_and_window(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    *,
    raster_root: Path,
    tracker: QueryTracker,
) -> tuple[dict[str, Path], dict[str, Path] | None, str]:
    """Export selected pair and, when possible, the frozen window composites."""

    safe = _safe_id(event_input.event_id)
    aoi = build_aoi(event_input.event, AOI_BUFFER_M, client)
    try:
        aoi_geometry_utm = aoi.geometry_utm.getInfo()
        tracker.geometry_queries += 1
    except Exception as exc:
        raise EarthEngineQueryError.from_exception(
            exc,
            operation=f"Level 2 frozen AOI geometry {event_input.event_id}",
            error_stage="level2_geometry",
            event_id=event_input.event_id,
            aoi_id=AOI_ID,
        ) from exc
    selected_graph = build_level2_graph(
        client,
        event_input,
        analysis_mode="selected_pair",
        cloud_threshold=PRIMARY_CLOUD_THRESHOLD,
    )
    selected_paths = _download_images_for_event(
        client,
        event_input,
        selected_graph,
        output_dir=raster_root,
        prefix=f"{safe}_selected_pair_cs050",
        tracker=tracker,
        aoi=aoi,
        aoi_geometry_utm=aoi_geometry_utm,
    )
    try:
        window_graph = build_level2_graph(
            client,
            event_input,
            analysis_mode="window_median",
            cloud_threshold=PRIMARY_CLOUD_THRESHOLD,
        )
        window_paths = _download_images_for_event(
            client,
            event_input,
            window_graph,
            output_dir=raster_root,
            prefix=f"{safe}_window_median_cs050",
            tracker=tracker,
            aoi=aoi,
            aoi_geometry_utm=aoi_geometry_utm,
        )
        return selected_paths, window_paths, "window_median reconstructed from frozen scene candidates"
    except Exception as exc:
        # A window raster is optional to the temporal sheet.  The selected pair
        # remains usable; exact failure metadata is retained without exposing
        # credentials or project identifiers.
        return selected_paths, None, f"window_median deferred: {type(exc).__name__}: {exc}"


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise Level2ValidationError("Cannot calculate percentile from an empty valid-pixel set")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(position))
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def compute_global_false_color_stretch(
    raster_paths: Sequence[Path],
    *,
    nodata: float = REFLECTANCE_NODATA,
) -> dict[str, Any]:
    """Compute one P2/P98 range per SWIR false-color band over all 14 images."""

    if len(raster_paths) != 14:
        raise Level2ValidationError(f"Global false-color stretch requires 14 rasters; received {len(raster_paths)}")
    values: list[list[float]] = [[], [], []]
    for path in raster_paths:
        raster = read_geotiff(path, nodata=nodata)
        _validate_raster_contract(raster, expected_bands=3, expected_dtype="uint16", nodata=nodata)
        for index in range(raster.pixel_count):
            pixels = [raster.data[band][index] for band in range(3)]
            if all(math.isfinite(value) and value != nodata and value > 0 for value in pixels):
                for band, value in enumerate(pixels):
                    values[band].append(value)
    minimum_percentile, maximum_percentile = FALSE_COLOR_PERCENTILES
    stretches = []
    band_names = list(FALSE_COLOR_BANDS)
    for band, name in enumerate(band_names):
        if not values[band]:
            raise Level2ValidationError(f"No valid false-color pixels available for {name}")
        minimum = _percentile(values[band], minimum_percentile)
        maximum = _percentile(values[band], maximum_percentile)
        if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
            raise Level2ValidationError(f"Invalid global false-color stretch for {name}: {minimum}/{maximum}")
        stretches.append(
            {
                "band": name,
                "minimum": minimum,
                "maximum": maximum,
                "valid_pixel_count": len(values[band]),
            }
        )
    return {
        "method": "global_percentile",
        "percentiles": {"minimum": minimum_percentile, "maximum": maximum_percentile},
        "source_raster_count": len(raster_paths),
        "source_paths": [path.as_posix() for path in raster_paths],
        "bands": stretches,
        "per_event_recalculation": False,
    }


def _raster_values_for_metric(raster: GeoTiffRaster, mask: GeoTiffRaster, support: GeoTiffRaster) -> list[float]:
    if (raster.width, raster.height) != (mask.width, mask.height) or (raster.width, raster.height) != (support.width, support.height):
        raise Level2ValidationError("Level 2 rasters do not share dimensions")
    return [
        value
        for value, mask_value, support_value in zip(raster.data[0], mask.data[0], support.data[0])
        if support_value > 0 and mask_value > 0 and math.isfinite(value) and value != NUMERIC_NODATA
    ]


def compute_local_metrics(raster_paths: Mapping[str, Path]) -> dict[str, Any]:
    """Recalculate v3-comparable metrics from numeric Level 2 rasters."""

    mask = read_geotiff(raster_paths["common_valid_mask"], nodata=MASK_NODATA)
    support = read_geotiff(raster_paths["aoi_support"], nodata=0)
    dnbr = read_geotiff(raster_paths["dnbr"], nodata=NUMERIC_NODATA)
    nbr_pre = read_geotiff(raster_paths["nbr_pre"], nodata=NUMERIC_NODATA)
    nbr_post = read_geotiff(raster_paths["nbr_post"], nodata=NUMERIC_NODATA)
    for raster in (mask, support):
        _validate_raster_contract(raster, expected_bands=1, expected_dtype="uint8", nodata=0)
    for raster in (dnbr, nbr_pre, nbr_post):
        _validate_raster_contract(raster, expected_bands=1, expected_dtype="float32", nodata=NUMERIC_NODATA)
    if (mask.width, mask.height) != (support.width, support.height) or (mask.width, mask.height) != (dnbr.width, dnbr.height):
        raise Level2ValidationError("Level 2 numeric rasters do not share dimensions")
    aoi_pixel_count = sum(1 for value in support.data[0] if value > 0)
    valid_indices = [
        index
        for index, (mask_value, support_value, value) in enumerate(zip(mask.data[0], support.data[0], dnbr.data[0]))
        if mask_value > 0 and support_value > 0 and math.isfinite(value) and value != NUMERIC_NODATA
    ]
    values = [dnbr.data[0][index] for index in valid_indices]
    if not values or not aoi_pixel_count:
        raise Level2ValidationError("Level 2 rasters contain no common valid AOI pixels")
    pixel_area_m2 = float(ANALYSIS_SCALE_M * ANALYSIS_SCALE_M)
    valid_pixel_count = len(values)
    threshold_counts = {
        threshold: sum(1 for value in values if value > threshold)
        for threshold in DNBR_THRESHOLDS
    }
    return {
        "valid_overlap_fraction": valid_pixel_count / aoi_pixel_count,
        "valid_overlap_area_m2": valid_pixel_count * pixel_area_m2,
        "aoi_pixel_count": aoi_pixel_count,
        "common_valid_pixel_count": valid_pixel_count,
        "valid_pixel_count": valid_pixel_count,
        "pixel_area_m2": pixel_area_m2,
        "pre_nbr_median": _percentile(_raster_values_for_metric(nbr_pre, mask, support), 50),
        "post_nbr_median": _percentile(_raster_values_for_metric(nbr_post, mask, support), 50),
        "dnbr_median": _percentile(values, 50),
        "dnbr_p90": _percentile(values, 90),
        "area_ha_dnbr_gt_010": threshold_counts[0.10] * pixel_area_m2 / 10000.0,
        "area_ha_dnbr_gt_020": threshold_counts[0.20] * pixel_area_m2 / 10000.0,
        "area_ha_dnbr_gt_030": threshold_counts[0.30] * pixel_area_m2 / 10000.0,
        "area_ha_dnbr_gt_040": threshold_counts[0.40] * pixel_area_m2 / 10000.0,
        "threshold_pixel_counts": {f"{threshold:.2f}": count for threshold, count in threshold_counts.items()},
        "raster_dimensions": [dnbr.width, dnbr.height],
        "crs": dnbr.crs or ANALYSIS_CRS,
        "transform": list(dnbr.transform or (ANALYSIS_SCALE_M, 0, 0, 0, -ANALYSIS_SCALE_M, 0)),
        "nodata": NUMERIC_NODATA,
    }


def _metric_value(row: Mapping[str, Any], key: str) -> float | None:
    return _float(row.get(key))


def compare_local_metrics(
    existing: Mapping[str, Any],
    local: Mapping[str, Any],
    *,
    event_id: str,
    analysis_mode: str,
) -> dict[str, Any]:
    """Compare numeric downloads to the frozen v3 row without rewriting it."""

    checks: list[dict[str, Any]] = []

    def check(name: str, existing_key: str, local_key: str, tolerance: float) -> None:
        expected = _metric_value(existing, existing_key)
        actual = _metric_value(local, local_key)
        if expected is None or actual is None:
            checks.append({"metric": name, "status": "not_comparable", "expected": expected, "actual": actual})
            return
        difference = abs(actual - expected)
        checks.append(
            {
                "metric": name,
                "status": "pass" if difference <= tolerance else "fail",
                "expected": expected,
                "actual": actual,
                "absolute_difference": difference,
                "tolerance": tolerance,
            }
        )

    check("dnbr_median", "dnbr_median", "dnbr_median", METRIC_TOLERANCES["dnbr_median"])
    check("dnbr_p90", "dnbr_p90", "dnbr_p90", METRIC_TOLERANCES["dnbr_p90"])
    for threshold in DNBR_THRESHOLDS:
        code = f"{int(threshold * 100):03d}"
        check(
            f"area_ha_dnbr_gt_{code}",
            f"area_ha_dnbr_gt_{code}",
            f"area_ha_dnbr_gt_{code}",
            METRIC_TOLERANCES["area_ha"],
        )
    check(
        "valid_overlap_fraction",
        "valid_overlap_fraction",
        "valid_overlap_fraction",
        METRIC_TOLERANCES["valid_overlap_fraction"],
    )
    expected_count = _metric_value(existing, "common_valid_pixel_count")
    actual_count = _metric_value(local, "common_valid_pixel_count")
    if expected_count is not None and actual_count is not None:
        difference = abs(actual_count - expected_count)
        checks.append(
            {
                "metric": "common_valid_pixel_count",
                "status": "pass" if difference <= METRIC_TOLERANCES["pixel_count"] else "fail",
                "expected": expected_count,
                "actual": actual_count,
                "absolute_difference": difference,
                "tolerance": METRIC_TOLERANCES["pixel_count"],
            }
        )
    failed = [item for item in checks if item.get("status") == "fail"]
    result = {
        "event_id": event_id,
        "analysis_mode": analysis_mode,
        "status": "pass" if not failed else "fail",
        "checks": checks,
        "tolerances": dict(METRIC_TOLERANCES),
    }
    if failed:
        raise Level2MetricMismatch(
            f"Level 2 metric mismatch for {event_id}/{analysis_mode}",
            details=result,
        )
    return result


_renderer = _v2._renderer
_text = _v2._text
_fill_rect = _v2._fill_rect
_stroke_rect = _v2._stroke_rect
_draw_firms_overlay = _v2._draw_firms_overlay
_draw_colorbar = _v2._draw_colorbar
_resize_nearest = _v2._resize_nearest
_resize_bilinear = _v2._resize_bilinear
_palette_color = _v2._palette_color

_BACKGROUND = _v2._BACKGROUND
_WHITE = _v2._WHITE
_INK = _v2._INK
_MUTED = _v2._MUTED
_BORDER = _v2._BORDER
_ACCENT = _v2._ACCENT
_ACCENT_DARK = _v2._ACCENT_DARK
_WARNING = _v2._WARNING
_INVALID = _v2._INVALID
_VALID = _v2._VALID


def _color_from_hex(value: str) -> tuple[int, int, int]:
    text = value.removeprefix("#")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _scale_reflectance(value: float, minimum: float, maximum: float, gamma: float = 1.0) -> int:
    if not math.isfinite(value) or maximum <= minimum:
        return 0
    position = max(0.0, min(1.0, (value - minimum) / (maximum - minimum)))
    return _clamp_byte((position ** (1.0 / gamma)) * 255.0)


def _raster_to_rgb(
    raster: GeoTiffRaster,
    *,
    mask: GeoTiffRaster | None,
    band_indices: tuple[int, int, int],
    ranges: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    gamma: float = 1.0,
) -> RGBImage:
    output = RGBImage.solid(raster.width, raster.height, _INVALID)
    for index in range(raster.pixel_count):
        if mask is not None and mask.data[0][index] <= 0:
            continue
        channels = [raster.data[band][index] for band in band_indices]
        if any(not math.isfinite(value) or value == REFLECTANCE_NODATA for value in channels):
            continue
        output.set_pixel(
            index % raster.width,
            index // raster.width,
            tuple(
                _scale_reflectance(value, minimum, maximum, gamma)
                for value, (minimum, maximum) in zip(channels, ranges)
            ),
        )
    return output


def _raster_to_scalar(
    raster: GeoTiffRaster,
    *,
    mask: GeoTiffRaster,
    minimum: float,
    maximum: float,
    invalid_color: tuple[int, int, int] = _INVALID,
) -> RGBImage:
    output = RGBImage.solid(raster.width, raster.height, invalid_color)
    for index, value in enumerate(raster.data[0]):
        if mask.data[0][index] <= 0 or not math.isfinite(value) or value == NUMERIC_NODATA:
            continue
        output.set_pixel(
            index % raster.width,
            index // raster.width,
            _palette_color((value - minimum) / (maximum - minimum)),
        )
    return output


def _raster_to_mask(raster: GeoTiffRaster, support: GeoTiffRaster) -> RGBImage:
    output = RGBImage.solid(raster.width, raster.height, _INVALID)
    invalid_color = _color_from_hex("#c026d3")
    valid_color = _color_from_hex("#0f766e")
    for index, value in enumerate(raster.data[0]):
        if support.data[0][index] <= 0:
            color = _INVALID
        else:
            color = valid_color if value > 0 else invalid_color
        output.set_pixel(index % raster.width, index // raster.width, color)
    return output


def _stretch_ranges(stretch: Mapping[str, Any]) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    by_band = {str(item["band"]): item for item in stretch.get("bands", [])}
    return tuple(
        (float(by_band[band]["minimum"]), float(by_band[band]["maximum"]))
        for band in FALSE_COLOR_BANDS
    )  # type: ignore[return-value]


def _draw_level2_mask_legend(renderer: Any, canvas: RGBImage, left: int, top: int) -> None:
    coordinates = (
        (left + 24, top, MASK_LEGEND[0]),
        (left + 315, top, MASK_LEGEND[1]),
        (left + 24, top + 34, MASK_LEGEND[2]),
        (left + 315, top + 34, MASK_LEGEND[3]),
        (left + 24, top + 68, MASK_LEGEND[4]),
    )
    for item_left, item_top, item in coordinates:
        color = _color_from_hex(item["color"])
        _fill_rect(canvas, item_left, item_top + 3, 22, 18, color)
        _stroke_rect(canvas, item_left, item_top + 3, 22, 18, _BORDER)
        _text(renderer, canvas, item["label"], item_left + 30, item_top, 14, _MUTED, True)


def _draw_mask_inset_legend(renderer: Any, canvas: RGBImage, left: int, top: int) -> None:
    """Compact legend used beside the diagnostic dNBR mask inset."""

    entries = (
        ("INVALID", MASK_LEGEND[0]),
        ("VALID", MASK_LEGEND[1]),
        ("AOI", MASK_LEGEND[2]),
        ("FIRMS", MASK_LEGEND[3]),
        ("GRAY: SPECTRAL ONLY", MASK_LEGEND[4]),
    )
    for index, (label, item) in enumerate(entries):
        column = 0 if index in {0, 2} else 1
        row = 0 if index < 2 else 1 if index < 4 else 2
        item_left = left + column * 150
        item_top = top + row * 27
        _fill_rect(canvas, item_left, item_top + 3, 16, 14, _color_from_hex(item["color"]))
        _stroke_rect(canvas, item_left, item_top + 3, 16, 14, _BORDER)
        _text(renderer, canvas, label, item_left + 22, item_top, 12, _MUTED, True)


def _panel_values(row: Mapping[str, Any]) -> dict[str, str]:
    overlap = _float(row.get("valid_overlap_fraction"))
    return {
        "overlap": "n/a" if overlap is None else f"{overlap * 100:.1f}%",
        "dnbr_median": "n/a" if _float(row.get("dnbr_median")) is None else f"{float(row['dnbr_median']):.3f}",
        "dnbr_p90": "n/a" if _float(row.get("dnbr_p90")) is None else f"{float(row['dnbr_p90']):.3f}",
        "area": "n/a" if _float(row.get("area_ha_dnbr_gt_020")) is None else f"{float(row['area_ha_dnbr_gt_020']):.2f}",
    }


def _blind_window_days(event_input: DnbrEventInput) -> tuple[int | None, int | None]:
    """Return the frozen temporal-window widths without exposing its ID."""

    match = re.search(r"pre(\d+)_post(\d+)", event_input.selected_combination_id)
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _blind_window_line(event_input: DnbrEventInput) -> str:
    pre_days, post_days = _blind_window_days(event_input)
    if pre_days is None or post_days is None:
        return "WINDOWS: frozen pre/post observation windows"
    return f"WINDOWS: PRE {pre_days} d / POST {post_days} d"


def _blind_stretch(stretch: Mapping[str, Any]) -> dict[str, Any]:
    """Retain display stretch values while excluding source-path metadata."""

    return {
        "method": stretch.get("method"),
        "per_event_recalculation": bool(stretch.get("per_event_recalculation", False)),
        "percentiles": dict(stretch.get("percentiles") or {}),
        "bands": [
            {
                key: item[key]
                for key in ("band", "minimum", "maximum", "valid_pixel_count")
                if key in item
            }
            for item in (stretch.get("bands") or [])
            if isinstance(item, Mapping)
        ],
    }


def _require_blind_case_id(value: str) -> str:
    if re.fullmatch(r"CASE-[0-9]{3}", value) is None:
        raise Level2ValidationError(f"Invalid blind case identifier: {value!r}")
    return value


def compose_level2_panel(
    *,
    event_input: DnbrEventInput,
    selected_metrics: Mapping[str, Any],
    raster_paths: Mapping[str, Path],
    stretch: Mapping[str, Any],
    root: Path,
    display_case_id: str | None = None,
) -> bytes:
    """Compose the multiespectral panel only after metric validation passes."""

    if display_case_id is not None:
        display_case_id = _require_blind_case_id(display_case_id)
    font, renderer = _renderer()
    mask = read_geotiff(raster_paths["common_valid_mask"], nodata=0)
    support = read_geotiff(raster_paths["aoi_support"], nodata=0)
    rgb_pre = read_geotiff(raster_paths["rgb_pre"], nodata=0)
    rgb_post = read_geotiff(raster_paths["rgb_post"], nodata=0)
    fc_pre = read_geotiff(raster_paths["false_color_pre"], nodata=0)
    fc_post = read_geotiff(raster_paths["false_color_post"], nodata=0)
    dnbr = read_geotiff(raster_paths["dnbr"], nodata=NUMERIC_NODATA)
    common_dimensions = (mask.width, mask.height)
    for raster in (support, rgb_pre, rgb_post, fc_pre, fc_post, dnbr):
        if (raster.width, raster.height) != common_dimensions:
            raise Level2ValidationError("Level 2 panel rasters do not share dimensions")
    false_color_ranges = _stretch_ranges(stretch)
    tiles = {
        "rgb_pre": _raster_to_rgb(
            rgb_pre,
            mask=mask,
            band_indices=(0, 1, 2),
            ranges=(RGB_REFLECTANCE_RANGE,) * 3,
            gamma=RGB_GAMMA,
        ),
        "rgb_post": _raster_to_rgb(
            rgb_post,
            mask=mask,
            band_indices=(0, 1, 2),
            ranges=(RGB_REFLECTANCE_RANGE,) * 3,
            gamma=RGB_GAMMA,
        ),
        "false_color_pre": _raster_to_rgb(
            fc_pre,
            mask=None,
            band_indices=(0, 1, 2),
            ranges=false_color_ranges,
        ),
        "false_color_post": _raster_to_rgb(
            fc_post,
            mask=None,
            band_indices=(0, 1, 2),
            ranges=false_color_ranges,
        ),
        "dnbr_global": _raster_to_scalar(dnbr, mask=mask, minimum=GLOBAL_DNBR_RANGE[0], maximum=GLOBAL_DNBR_RANGE[1]),
        "dnbr_diagnostic": _raster_to_scalar(
            dnbr,
            mask=mask,
            minimum=DIAGNOSTIC_DNBR_RANGE[0],
            maximum=DIAGNOSTIC_DNBR_RANGE[1],
        ),
        "mask": _raster_to_mask(mask, support),
    }
    canvas = RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, _BACKGROUND)
    event_id = event_input.event_id
    pre_timestamp = _format_timestamp(event_input.pre_scene.get("acquisition_timestamp_utc"))
    post_timestamp = _format_timestamp(event_input.post_scene.get("acquisition_timestamp_utc"))
    event_start = event_input.event.start_timestamp_utc
    event_end = event_input.event.end_timestamp_utc
    pre_dt = datetime.fromisoformat(pre_timestamp.replace("Z", "+00:00"))
    post_dt = datetime.fromisoformat(post_timestamp.replace("Z", "+00:00"))
    pre_lead = (event_start - pre_dt).total_seconds() / 86400.0
    post_lag = (post_dt - event_end).total_seconds() / 86400.0
    _text(renderer, canvas, display_case_id or event_id, 42, 28, 44, _INK, True)
    _text(renderer, canvas, f"{QUICKLOOK_VERSION}  |  MULTISPECTRAL EVIDENCE  |  selected_pair", 44, 86, 24, _ACCENT_DARK, True)
    if display_case_id is None:
        _text(
            renderer,
            canvas,
            f"PRE SCENE: {event_input.pre_scene_id}   POST SCENE: {event_input.post_scene_id}",
            44,
            119,
            18,
            _MUTED,
        )
        _text(
            renderer,
            canvas,
            f"DATES UTC: {pre_timestamp} to {post_timestamp}   PRE LEAD: {pre_lead:.2f} d   POST LAG: {post_lag:.2f} d   POLICY: {event_input.policy_path}   AOI: {AOI_ID} / {AOI_BUFFER_M} m   SCALE: {ANALYSIS_SCALE_M} m   CS+: >= {PRIMARY_CLOUD_THRESHOLD:.2f}",
            44,
            148,
            17,
            _MUTED,
        )
    else:
        _text(renderer, canvas, "PRE/POST SCENE IDS: WITHHELD FOR BLIND REVIEW", 44, 119, 18, _MUTED)
        _text(
            renderer,
            canvas,
            f"DATES UTC: {pre_timestamp} to {post_timestamp}   PRE LEAD: {pre_lead:.2f} d   POST LAG: {post_lag:.2f} d   {_blind_window_line(event_input)}   AOI: {AOI_ID} / {AOI_BUFFER_M} m   SCALE: {ANALYSIS_SCALE_M} m   CS+: >= {PRIMARY_CLOUD_THRESHOLD:.2f}",
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
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}  |  {NEGATIVE_DNBR_NOTE}", 44, 201, 16, _ACCENT_DARK, True)

    tile_width, tile_height = 632, 500
    gap_x, gap_y = 22, 22
    left_margin, top_margin = 36, 228
    labels = {
        "rgb_pre": "RGB PRE  |  B4/B3/B2",
        "rgb_post": "RGB POST  |  B4/B3/B2",
        "false_color_pre": "FALSE-COLOR PRE  |  B12/B8A/B4",
        "false_color_post": "FALSE-COLOR POST  |  B12/B8A/B4",
        "dnbr_global": "dNBR GLOBAL  |  fixed [-1.0, 1.0]",
        "dnbr_diagnostic": "dNBR DIAGNOSTIC  |  fixed [-0.25, 0.50]",
        "mask": "COMMON VALID MASK  |  uint8 / 20 m",
    }
    # Seven required visual layers fit into six tiles by placing the valid
    # mask as a clearly labelled inset in the diagnostic dNBR tile.
    order = ("rgb_pre", "rgb_post", "false_color_pre", "false_color_post", "dnbr_global", "dnbr_diagnostic")
    valid_fraction = _float(selected_metrics.get("valid_overlap_fraction")) or 0.0
    compact_mask = valid_fraction >= 0.98
    for index, key in enumerate(order):
        column, row = index % 3, index // 3
        left = left_margin + column * (tile_width + gap_x)
        top = top_margin + row * (tile_height + gap_y)
        _fill_rect(canvas, left, top, tile_width, tile_height, _WHITE)
        _stroke_rect(canvas, left, top, tile_width, tile_height, _BORDER, 2)
        _text(renderer, canvas, labels[key], left + 18, top + 17, 21, _INK, True)
        local = tiles[key]
        if key == "dnbr_diagnostic":
            local_width, local_height = 534, 280
            image_left, image_top = left + 20, top + 62
        else:
            local_width, local_height = 534, 394
            image_left, image_top = left + 20, top + 62
        if key in {"rgb_pre", "rgb_post", "false_color_pre", "false_color_post"}:
            tile = _resize_bilinear(local, local_width, local_height)
        else:
            tile = _resize_nearest(local, local_width, local_height)
        canvas.paste(tile, image_left, image_top)
        if key == "rgb_post":
            _draw_firms_overlay(canvas, event_input, image_left, image_top, local_width, local_height)
            _text(renderer, canvas, "FIRMS halo + centroid   |   scale bar: 500 m", image_left + 10, image_top + local_height - 28, 17, _WHITE, True)
        if key == "dnbr_global":
            _draw_colorbar(renderer, canvas, left + 568, image_top + 30, local_height - 40, -1.0, 1.0, "dNBR")
        if key == "dnbr_diagnostic":
            _draw_colorbar(renderer, canvas, left + 568, image_top + 30, local_height - 40, -0.25, 0.50, "dNBR DIAG")
            mask_inset = _resize_nearest(tiles["mask"], 210, 105)
            _fill_rect(canvas, left + 20, top + 362, 226, 135, (235, 240, 242))
            _stroke_rect(canvas, left + 20, top + 362, 226, 135, _BORDER)
            _text(renderer, canvas, "MASK INSET", left + 30, top + 369, 13, _MUTED, True)
            canvas.paste(mask_inset, left + 30, top + 388)
            _draw_mask_inset_legend(renderer, canvas, left + 270, top + 374)

    values = _panel_values(selected_metrics)
    metric_top = 1286
    metric_width = 365
    metric_gap = 12
    metric_labels = (
        ("VALID OVERLAP", values["overlap"], _ACCENT),
        ("dNBR MEDIAN", values["dnbr_median"], _ACCENT_DARK),
        ("dNBR P90", values["dnbr_p90"], _ACCENT_DARK),
        ("AREA > 0.20", f"{values['area']} ha", _ACCENT_DARK),
        ("METRIC STATUS", str(selected_metrics.get("metric_status") or "n/a"), _ACCENT),
    )
    for index, (label, value, color) in enumerate(metric_labels):
        left = 36 + index * (metric_width + metric_gap)
        _fill_rect(canvas, left, metric_top, metric_width, 70, _WHITE)
        _stroke_rect(canvas, left, metric_top, metric_width, 70, _BORDER)
        _text(renderer, canvas, label, left + 16, metric_top + 8, 15, _MUTED, True)
        _text(renderer, canvas, value, left + 16, metric_top + 32, 25, color, True)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 42, 1370, 21, _WARNING, True)
    _text(renderer, canvas, "Numeric sources: local float32 NBR/dNBR GeoTIFFs; dNBR diagnostic is a visual remap only.", 42, 1397, 16, _MUTED)
    metadata = {
        "event_id": event_id,
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "analysis_mode": "selected_pair",
        "scene_ids": {"pre": event_input.pre_scene_id, "post": event_input.post_scene_id},
        "dates_utc": {"pre": pre_timestamp, "post": post_timestamp},
        "pre_lead_days": pre_lead,
        "post_lag_days": post_lag,
        "policy_path": event_input.policy_path,
        "selected_combination_id": event_input.selected_combination_id,
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "analysis_crs": ANALYSIS_CRS,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "cloud_score_plus_threshold": PRIMARY_CLOUD_THRESHOLD,
        "bands": {
            "rgb": list(RGB_BANDS),
            "false_color_swir": list(FALSE_COLOR_BANDS),
            "nbr": ["B8", "B12"],
            "dnbr": "NBR_pre - NBR_post",
        },
        "resampling_visual": {"rgb": "bilinear_presentation_only", "numeric": "nearest_neighbor"},
        "global_dnbr_range": list(GLOBAL_DNBR_RANGE),
        "diagnostic_dnbr_range": list(DIAGNOSTIC_DNBR_RANGE),
        "false_color_stretch": dict(stretch),
        "nodata": {"reflectance": REFLECTANCE_NODATA, "numeric": NUMERIC_NODATA, "mask": MASK_NODATA},
        "mask_legend": [dict(item) for item in MASK_LEGEND],
        "positive_dnbr_note": POSITIVE_DNBR_NOTE,
        "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        "warning": DESCRIPTIVE_WARNING,
        "raster_paths": {key: _relative(path, root) for key, path in raster_paths.items()},
        "source_numeric_rasters": True,
        "full_scenes_downloaded": False,
        "automatic_label_created": False,
        "ground_truth": False,
        "earth_engine_project_stored": False,
        "earth_engine_authentication_called": False,
        "earth_engine_queries_made": True,
        "panel_dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
        "final_format": "RGB",
    }
    if display_case_id is not None:
        pre_window_days, post_window_days = _blind_window_days(event_input)
        metadata = {
            "case_id": display_case_id,
            "quicklook_version": QUICKLOOK_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "analysis_mode": "selected_pair",
            "dates_utc": {"pre": pre_timestamp, "post": post_timestamp},
            "pre_lead_days": pre_lead,
            "post_lag_days": post_lag,
            "window_days": {"pre": pre_window_days, "post": post_window_days},
            "window_scene_counts": {
                "pre": len(event_input.pre_candidates),
                "post": len(event_input.post_candidates),
            },
            "aoi_id": AOI_ID,
            "aoi_buffer_m": AOI_BUFFER_M,
            "analysis_crs": ANALYSIS_CRS,
            "analysis_scale_m": ANALYSIS_SCALE_M,
            "cloud_score_plus_threshold": PRIMARY_CLOUD_THRESHOLD,
            "bands": {
                "rgb": list(RGB_BANDS),
                "false_color_swir": list(FALSE_COLOR_BANDS),
                "nbr": ["B8", "B12"],
                "dnbr": "NBR_pre - NBR_post",
            },
            "resampling_visual": {"rgb": "bilinear_presentation_only", "numeric": "nearest_neighbor"},
            "global_dnbr_range": list(GLOBAL_DNBR_RANGE),
            "diagnostic_dnbr_range": list(DIAGNOSTIC_DNBR_RANGE),
            "false_color_stretch": _blind_stretch(stretch),
            "nodata": {"reflectance": REFLECTANCE_NODATA, "numeric": NUMERIC_NODATA, "mask": MASK_NODATA},
            "mask_legend": [dict(item) for item in MASK_LEGEND],
            "positive_dnbr_note": POSITIVE_DNBR_NOTE,
            "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
            "warning": DESCRIPTIVE_WARNING,
            "metric_status": str(selected_metrics.get("metric_status") or "n/a"),
            "source_numeric_rasters": True,
            "generated_from_existing_local_rasters": True,
            "full_scenes_downloaded": False,
            "automatic_label_created": False,
            "ground_truth": False,
            "earth_engine_queries_made": False,
            "panel_dimensions": [PANEL_WIDTH, PANEL_HEIGHT],
            "final_format": "RGB",
        }
    return encode_png(canvas, metadata)


def _comparison_status(selected: Mapping[str, Any] | None, window: Mapping[str, Any] | None) -> str:
    if not selected or not window:
        return "insufficient local metrics"
    values = (
        (_float(selected.get("dnbr_median")), _float(window.get("dnbr_median"))),
        (_float(selected.get("dnbr_p90")), _float(window.get("dnbr_p90"))),
        (_float(selected.get("valid_overlap_fraction")), _float(window.get("valid_overlap_fraction"))),
    )
    if any(left is None or right is None for left, right in values):
        return "insufficient local metrics"
    return "agreement (descriptive)" if all(abs(left - right) <= 0.05 for left, right in values) else "disagreement (descriptive)"


def _difference(selected: Mapping[str, Any] | None, window: Mapping[str, Any] | None, key: str) -> str:
    left = _float((selected or {}).get(key))
    right = _float((window or {}).get(key))
    if left is None or right is None:
        return "n/a"
    return f"{abs(left - right):.3f}"


def compose_level2_temporal_sheet(
    *,
    event_input: DnbrEventInput,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any] | None,
    selected_local_metrics: Mapping[str, Any],
    window_local_metrics: Mapping[str, Any] | None,
    selected_raster_paths: Mapping[str, Path],
    window_raster_paths: Mapping[str, Path] | None,
    window_available: bool,
    window_reason: str,
    root: Path,
    display_case_id: str | None = None,
) -> bytes:
    """Compose selected/window dNBR evidence without image substitution."""

    if display_case_id is not None:
        display_case_id = _require_blind_case_id(display_case_id)
    font, renderer = _renderer()
    canvas = RGBImage.solid(COMPARISON_WIDTH, COMPARISON_HEIGHT, _BACKGROUND)
    event_id = event_input.event_id
    _text(renderer, canvas, display_case_id or event_id, 48, 36, 44, _INK, True)
    _text(renderer, canvas, f"{QUICKLOOK_VERSION}  |  TEMPORAL ROBUSTNESS  |  selected_pair vs window_median", 50, 96, 24, _ACCENT_DARK, True)
    _text(renderer, canvas, "Numeric Level 2 dNBR exports are compared locally; no selected-pair image is reused for a window.", 50, 132, 21, _MUTED)
    _text(
        renderer,
        canvas,
        (
            f"POLICY: {event_input.policy_path}   COMBINATION: {event_input.selected_combination_id}   AOI: {AOI_ID} / {AOI_BUFFER_M} m   SCALE: {ANALYSIS_SCALE_M} m   CS+: >= {PRIMARY_CLOUD_THRESHOLD:.2f}"
            if display_case_id is None
            else f"{_blind_window_line(event_input)}   AOI: {AOI_ID} / {AOI_BUFFER_M} m   SCALE: {ANALYSIS_SCALE_M} m   CS+: >= {PRIMARY_CLOUD_THRESHOLD:.2f}"
        ),
        50,
        165,
        19,
        _MUTED,
    )
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}  |  {NEGATIVE_DNBR_NOTE}", 50, 194, 18, _ACCENT_DARK, True)

    cards = (("SELECTED_PAIR", selected_metrics, selected_local_metrics, 52, _ACCENT), ("WINDOW_MEDIAN", window_metrics, window_local_metrics, 1050, _ACCENT_DARK))
    card_width, card_height = 946, 710
    for title, row, local_row, left, color in cards:
        _fill_rect(canvas, left, 230, card_width, card_height, _WHITE)
        _stroke_rect(canvas, left, 230, card_width, card_height, _BORDER, 2)
        _fill_rect(canvas, left, 230, card_width, 80, color)
        _text(renderer, canvas, title, left + 26, 251, 28, _WHITE, True)
        if title == "WINDOW_MEDIAN" and not window_available:
            _text(renderer, canvas, "WINDOW MEDIAN RASTER DEFERRED", left + 28, 350, 23, _WARNING, True)
            _text(renderer, canvas, WINDOW_METRICS_ONLY, left + 28, 390, 17, _MUTED)
            _text(renderer, canvas, window_reason, left + 28, 422, 15, _MUTED)
            display_local = False
        else:
            _text(renderer, canvas, f"STATUS: {row.get('metric_status', 'n/a') if row else 'n/a'}   LOCAL: numeric GeoTIFF", left + 28, 342, 19, _MUTED, True)
            if title == "SELECTED_PAIR":
                _text(
                    renderer,
                    canvas,
                    (
                        f"PRE SCENE: {event_input.pre_scene_id}   POST SCENE: {event_input.post_scene_id}"
                        if display_case_id is None
                        else "SCENE ROLES: PRE / POST (identifiers withheld)"
                    ),
                    left + 28,
                    374,
                    18,
                    _MUTED,
                )
            else:
                _text(renderer, canvas, f"WINDOWS: PRE {len(event_input.pre_candidates)} scenes   POST {len(event_input.post_candidates)} scenes", left + 28, 374, 18, _MUTED)
            display_local = True
        if display_local and local_row is not None:
            local_values = (
                ("dNBR median", f"{float(local_row['dnbr_median']):.4f}"),
                ("dNBR p90", f"{float(local_row['dnbr_p90']):.4f}"),
                ("area > 0.20", f"{float(local_row['area_ha_dnbr_gt_020']):.3f} ha"),
                ("valid overlap", f"{float(local_row['valid_overlap_fraction']) * 100:.1f}%"),
            )
            for index, (label, value) in enumerate(local_values):
                y = 430 + index * 53
                _text(renderer, canvas, label.upper(), left + 28, y, 17, _MUTED, True)
                _text(renderer, canvas, value, left + 360, y - 5, 27, color, True)
            raster = read_geotiff((selected_raster_paths if title == "SELECTED_PAIR" else window_raster_paths)["dnbr"], nodata=NUMERIC_NODATA)  # type: ignore[index]
            mask = read_geotiff((selected_raster_paths if title == "SELECTED_PAIR" else window_raster_paths)["common_valid_mask"], nodata=0)  # type: ignore[index]
            tile = _resize_nearest(
                _raster_to_scalar(raster, mask=mask, minimum=GLOBAL_DNBR_RANGE[0], maximum=GLOBAL_DNBR_RANGE[1]),
                420,
                235,
            )
            canvas.paste(tile, left + 28, 680)
            _text(renderer, canvas, "dNBR raster | fixed [-1.0, 1.0]", left + 28, 924, 16, _MUTED)

    _fill_rect(canvas, 52, 980, 1944, 246, _WHITE)
    _stroke_rect(canvas, 52, 980, 1944, 246, _BORDER, 2)
    _text(renderer, canvas, "ABSOLUTE DIFFERENCES / DESCRIPTIVE FLAG", 80, 1008, 24, _INK, True)
    differences = (
        ("dNBR median", _difference(selected_metrics, window_metrics, "dnbr_median")),
        ("dNBR p90", _difference(selected_metrics, window_metrics, "dnbr_p90")),
        ("area > 0.20 ha", _difference(selected_metrics, window_metrics, "area_ha_dnbr_gt_020")),
        ("valid overlap", _difference(selected_metrics, window_metrics, "valid_overlap_fraction")),
    )
    for index, (label, value) in enumerate(differences):
        left = 82 + index * 455
        _text(renderer, canvas, label.upper(), left, 1060, 17, _MUTED, True)
        _text(renderer, canvas, value, left, 1090, 30, _ACCENT_DARK, True)
    flag = _comparison_status(selected_metrics, window_metrics) if window_available else "metrics only"
    _text(renderer, canvas, f"FLAG: {flag}", 82, 1160, 23, _WARNING if "disagreement" in flag else _VALID, True)
    _text(renderer, canvas, "The flag is descriptive only; it is not an automatic burn or severity label.", 82, 1192, 18, _MUTED)
    _text(renderer, canvas, DESCRIPTIVE_WARNING, 52, 1302, 22, _WARNING, True)
    _text(renderer, canvas, f"{POSITIVE_DNBR_NOTE}; {NEGATIVE_DNBR_NOTE}.", 52, 1334, 17, _MUTED)
    _text(renderer, canvas, WINDOW_METRICS_ONLY if not window_available else FALSE_COLOR_DEFERRED_NOTE, 52, 1360, 17, _MUTED)
    _text(renderer, canvas, "No ground truth, severity label, or causal conclusion is encoded.", 52, 1386, 17, _MUTED)
    metadata = {
        "event_id": event_id,
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "sheet": "temporal_robustness",
        "selected_pair_raster_paths": {key: _relative(path, root) for key, path in selected_raster_paths.items()},
        "window_median_raster_available": window_available,
        "window_median_label": "numeric GeoTIFF" if window_available else "metrics only",
        "window_median_reason": window_reason,
        "window_median_raster_paths": {}
        if window_raster_paths is None
        else {key: _relative(path, root) for key, path in window_raster_paths.items()},
        "window_scene_ids": {
            "pre": [_scene_id(row) for row in event_input.pre_candidates],
            "post": [_scene_id(row) for row in event_input.post_candidates],
        },
        "window_counts": {"pre": len(event_input.pre_candidates), "post": len(event_input.post_candidates)},
        "comparison_flag": flag,
        "absolute_differences": {key: value for key, value in differences},
        "positive_dnbr_note": POSITIVE_DNBR_NOTE,
        "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
        "warning": DESCRIPTIVE_WARNING,
        "earth_engine_project_stored": False,
        "earth_engine_queries_made": True,
        "source_numeric_rasters": True,
        "final_format": "RGB",
        "panel_dimensions": [COMPARISON_WIDTH, COMPARISON_HEIGHT],
    }
    if display_case_id is not None:
        pre_window_days, post_window_days = _blind_window_days(event_input)
        metadata = {
            "case_id": display_case_id,
            "quicklook_version": QUICKLOOK_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "sheet": "temporal_robustness",
            "window_median_raster_available": window_available,
            "window_median_label": "numeric GeoTIFF" if window_available else "metrics only",
            "window_median_reason": "local numeric window median available" if window_available else "numeric window median unavailable",
            "window_counts": {
                "pre": len(event_input.pre_candidates),
                "post": len(event_input.post_candidates),
            },
            "window_days": {"pre": pre_window_days, "post": post_window_days},
            "comparison_flag": flag,
            "absolute_differences": {key: value for key, value in differences},
            "positive_dnbr_note": POSITIVE_DNBR_NOTE,
            "negative_dnbr_note": NEGATIVE_DNBR_NOTE,
            "warning": DESCRIPTIVE_WARNING,
            "source_numeric_rasters": True,
            "generated_from_existing_local_rasters": True,
            "earth_engine_queries_made": False,
            "ground_truth": False,
            "panel_dimensions": [COMPARISON_WIDTH, COMPARISON_HEIGHT],
            "final_format": "RGB",
        }
    return encode_png(canvas, metadata)


def _event_metadata(event_input: DnbrEventInput, *, root: Path) -> dict[str, Any]:
    """Return non-secret frozen selection metadata for one calibration event."""

    return {
        "event_id": event_input.event_id,
        "configuration_id": event_input.event.configuration_id,
        "policy_path": event_input.policy_path,
        "selected_combination_id": event_input.selected_combination_id,
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "aoi_area_m2": _float(event_input.aoi_area_m2),
        "pre_scene": {
            "scene_id": event_input.pre_scene_id,
            "acquisition_timestamp_utc": _format_timestamp(
                event_input.pre_scene.get("acquisition_timestamp_utc")
            ),
        },
        "post_scene": {
            "scene_id": event_input.post_scene_id,
            "acquisition_timestamp_utc": _format_timestamp(
                event_input.post_scene.get("acquisition_timestamp_utc")
            ),
        },
        "window_scene_ids": {
            "pre": [_scene_id(row) for row in event_input.pre_candidates],
            "post": [_scene_id(row) for row in event_input.post_candidates],
        },
        "window_counts": {
            "pre": len(event_input.pre_candidates),
            "post": len(event_input.post_candidates),
        },
        "source_selection_path": _relative(
            root / "outputs/sentinel2_event_pair_selection.csv", root
        ),
        "source_metrics_path": _relative(
            root / "data/interim/sentinel2_dnbr_event_metrics.csv", root
        ),
    }


def _raster_metadata(path: Path, *, root: Path) -> dict[str, Any]:
    raster = read_geotiff(path, nodata=None)
    return {
        "path": _relative(path, root),
        "sha256": _hash_file(path),
        "width": raster.width,
        "height": raster.height,
        "bands": raster.band_count,
        "dtype": raster.dtype,
        "bits_per_sample": raster.bits_per_sample,
        "sample_format": raster.sample_format,
        "compression": raster.compression,
        "crs": raster.crs or ANALYSIS_CRS,
        "transform": list(raster.transform or (ANALYSIS_SCALE_M, 0, 0, 0, -ANALYSIS_SCALE_M, 0)),
        "nodata": raster.nodata,
    }


def _raster_metadata_map(paths: Mapping[str, Path], *, root: Path) -> dict[str, Any]:
    return {key: _raster_metadata(path, root=root) for key, path in sorted(paths.items())}


def _sidecar_payload(
    *,
    event_input: DnbrEventInput,
    selected_paths: Mapping[str, Path],
    selected_local_metrics: Mapping[str, Any],
    selected_comparison: Mapping[str, Any],
    window_paths: Mapping[str, Path] | None,
    window_local_metrics: Mapping[str, Any] | None,
    window_comparison: Mapping[str, Any] | None,
    window_reason: str,
    root: Path,
) -> dict[str, Any]:
    return {
        "quicklook_version": QUICKLOOK_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "contract": QUICKLOOK_VERSION,
        "event": _event_metadata(event_input, root=root),
        "analysis": {
            "analysis_mode": "selected_pair",
            "cloud_score_plus_threshold": PRIMARY_CLOUD_THRESHOLD,
            "analysis_scale_m": ANALYSIS_SCALE_M,
            "analysis_crs": ANALYSIS_CRS,
            "nbr_formula": "(B8 - B12) / (B8 + B12)",
            "dnbr_formula": "NBR_pre - NBR_post",
            "rgb_bands": list(RGB_BANDS),
            "false_color_bands": list(FALSE_COLOR_BANDS),
            "numeric_bands": list(NUMERIC_BANDS),
            "reflectance_nodata": REFLECTANCE_NODATA,
            "numeric_nodata": NUMERIC_NODATA,
            "mask_nodata": MASK_NODATA,
            "aoi_support_source": "local_exact_frozen_ee_utm_geometry_rasterization_on_ee_export_grid",
            "aoi_support_geometry_query": "build_aoi.geometry_utm.getInfo",
        },
        "selected_pair": {
            "rasters": _raster_metadata_map(selected_paths, root=root),
            "local_metrics": dict(selected_local_metrics),
            "comparison": dict(selected_comparison),
        },
        "window_median": {
            "available": window_paths is not None,
            "reason": window_reason,
            "rasters": {} if window_paths is None else _raster_metadata_map(window_paths, root=root),
            "local_metrics": None if window_local_metrics is None else dict(window_local_metrics),
            "comparison": None if window_comparison is None else dict(window_comparison),
        },
        "scope": {
            "full_scenes_downloaded": False,
            "earth_engine_project_stored": False,
            "earth_engine_authentication_called": False,
            "automatic_label_created": False,
            "ground_truth": False,
            "significant_burn_labels_created": False,
            "models_trained": False,
            "data_2026_used": False,
        },
    }


def export_event_level2(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    *,
    selected_metrics: Mapping[str, Any],
    window_metrics: Mapping[str, Any] | None,
    raster_root: Path,
    tracker: QueryTracker,
    root: Path,
) -> EventExport:
    """Export, validate, and reconcile one event without touching v3 outputs."""

    selected_paths, window_paths, window_reason = export_selected_and_window(
        client,
        event_input,
        raster_root=raster_root,
        tracker=tracker,
    )
    selected_local_metrics = compute_local_metrics(selected_paths)
    selected_comparison: Mapping[str, Any]
    window_local_metrics: Mapping[str, Any] | None = None
    window_comparison: Mapping[str, Any] | None = None
    try:
        selected_comparison = compare_local_metrics(
            selected_metrics,
            selected_local_metrics,
            event_id=event_input.event_id,
            analysis_mode="selected_pair",
        )
        if window_paths is not None:
            if window_metrics is None:
                raise Level2ValidationError(
                    f"No frozen window_median row for {event_input.event_id}"
                )
            window_local_metrics = compute_local_metrics(window_paths)
            window_comparison = compare_local_metrics(
                window_metrics,
                window_local_metrics,
                event_id=event_input.event_id,
                analysis_mode="window_median",
            )
    except Level2ValidationError as exc:
        sidecar_path = raster_root / f"{_safe_id(event_input.event_id)}_export_metadata.json"
        failure_payload = _sidecar_payload(
            event_input=event_input,
            selected_paths=selected_paths,
            selected_local_metrics=selected_local_metrics,
            selected_comparison=dict(getattr(exc, "details", {})),
            window_paths=window_paths,
            window_local_metrics=window_local_metrics,
            window_comparison=window_comparison,
            window_reason=window_reason,
            root=root,
        )
        failure_payload["status"] = "failed_metric_reconciliation"
        failure_payload["error"] = {"type": type(exc).__name__, "message": str(exc)}
        _write_json_atomic(sidecar_path, failure_payload)
        raise

    sidecar_path = raster_root / f"{_safe_id(event_input.event_id)}_export_metadata.json"
    _write_json_atomic(
        sidecar_path,
        {
            **_sidecar_payload(
                event_input=event_input,
                selected_paths=selected_paths,
                selected_local_metrics=selected_local_metrics,
                selected_comparison=selected_comparison,
                window_paths=window_paths,
                window_local_metrics=window_local_metrics,
                window_comparison=window_comparison,
                window_reason=window_reason,
                root=root,
            ),
            "status": "validated",
        },
    )
    return EventExport(
        event_id=event_input.event_id,
        raster_paths=selected_paths,
        window_available=window_paths is not None and window_local_metrics is not None,
        window_reason=window_reason,
        export_metadata_path=sidecar_path,
        selected_local_metrics=selected_local_metrics,
        window_local_metrics=window_local_metrics,
        selected_comparison=selected_comparison,
        window_comparison=window_comparison,
    )


def _level2_artifact_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in (RASTER_DIR, FIGURE_DIR, REVIEW_UPLOAD_DIR):
        directory = root / relative
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(paths)


def write_level2_manifest(root: Path) -> dict[str, Any]:
    """Hash only the new Level 2 evidence artifacts, excluding the manifest itself."""

    entries = [
        {
            "path": _relative(path, root),
            "sha256": _hash_file(path),
            "bytes": path.stat().st_size,
        }
        for path in _level2_artifact_paths(root)
    ]
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    manifest_path = root / MANIFEST_PATH
    _write_text_atomic(
        manifest_path,
        "# FirePA Level 2 evidence manifest\n"
        f"# contract: {QUICKLOOK_VERSION}\n"
        + "\n".join(lines)
        + "\n",
    )
    return {
        "path": MANIFEST_PATH,
        "sha256": _hash_file(manifest_path),
        "index_sha256": _hash_index(lines),
        "entry_count": len(entries),
        "entries": entries,
    }


def build_level2_report_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact, source-backed handoff report."""

    lines = [
        "# FirePA Quicklook Level 2 report",
        "",
        f"- Contract: `{report.get('quicklook_version', QUICKLOOK_VERSION)}`",
        f"- Pipeline: `{report.get('pipeline_version', PIPELINE_VERSION)}`",
        f"- Calibration events: `{report.get('generated_count', 0)}/{report.get('requested_event_count', 0)}`",
        f"- Earth Engine queries: `{report.get('earth_engine_queries', {}).get('total', 0)}` total; `{report.get('earth_engine_queries', {}).get('download', 0)}` downloads.",
        f"- Selected-pair PNG panels: `{report.get('artifacts', {}).get('selected_pair_panel_count', 0)}`; temporal sheets: `{report.get('artifacts', {}).get('temporal_sheet_count', 0)}`.",
        "",
        "## Scientific boundary",
        "",
        "- Frozen cohort, selected scene IDs, b0500 AOI, 20 m scale, EPSG:32617, CS+ threshold 0.50, formulas, v3 metrics, review queue, and 2026 data were not rewritten.",
        "- No models, labels, ground truth, sample expansion, full-scene downloads, or push were performed.",
        "",
        "## Evidence",
        "",
        "- Numeric sources: local float32 NBR/dNBR GeoTIFFs plus uint16 multispectral layers.",
        "- False-color bands: `B12/B8A/B4`; one global P2/P98 stretch is shared across the 14 selected-pair rasters.",
        "- dNBR global range: `[-1.0, 1.0]`; diagnostic range: `[-0.25, 0.50]`; resampling is presentation-only.",
        "- Positive dNBR is shown as spectral vegetation loss; negative dNBR as spectral vegetation gain. The evidence is descriptive and is not a confirmation of fire.",
        "",
        "## Metric reconciliation",
        "",
        "- Tolerances: dNBR median/p90 `0.005`, threshold areas `0.50 ha`, valid overlap `0.005`, common valid pixels `16`.",
        f"- Result: `{report.get('metric_reconciliation', {}).get('status', 'not_run')}`.",
        "",
        "## Protected output check",
        "",
        f"- Protected scientific/v1/v2/v2.1 integrity: `{report.get('protected_integrity', {}).get('status', 'not_run')}`.",
        f"- Level 2 manifest: `{report.get('manifest', {}).get('path', MANIFEST_PATH)}` (`{report.get('manifest', {}).get('sha256', '')}`).",
        "",
        "## Errors",
        "",
    ]
    errors = list(report.get("errors", []))
    if errors:
        lines.extend(f"- `{item.get('event_id', 'batch')}`: {item.get('error_type', 'error')}: {item.get('message', '')}" for item in errors)
    else:
        lines.append("- None.")
    lines.extend(["", "## Git", "", f"- Start HEAD: `{report.get('git', {}).get('start_head', '')}`.", f"- End status: `{report.get('git', {}).get('end_status', '')}`.", "- No push performed.", ""])
    return "\n".join(lines)
