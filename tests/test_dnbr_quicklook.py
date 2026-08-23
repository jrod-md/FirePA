from __future__ import annotations

import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.dnbr_quicklook import (
    PANEL_KEYS,
    QuicklookValidationError,
    RGBImage,
    decode_png_details,
    encode_png,
    validate_thumbnail_sources,
)
from fuegopa.sentinel2_dnbr import (
    DnbrEventInput,
    _quicklook_overlay,
    rebuild_quicklook_from_artifacts,
)
from fuegopa.sentinel2_observability import DetectionInput, EventInput


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _raw_png(
    width: int,
    height: int,
    color_type: int,
    rows: list[bytes],
    *,
    palette: bytes = b"",
    transparency: bytes = b"",
) -> bytes:
    channels = {2: 3, 3: 1, 6: 4}[color_type]
    assert all(len(row) == width * channels for row in rows)
    scanlines = b"".join(b"\x00" + row for row in rows)
    chunks = [
        _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)),
    ]
    if palette:
        chunks.append(_chunk(b"PLTE", palette))
    if transparency:
        chunks.append(_chunk(b"tRNS", transparency))
    chunks.extend((_chunk(b"IDAT", zlib.compress(scanlines)), _chunk(b"IEND", b"")))
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


def _pattern(seed: int, width: int = 8, height: int = 8) -> bytes:
    image = RGBImage.solid(width, height, (0, 0, 0))
    for y in range(height):
        for x in range(width):
            image.set_pixel(
                x,
                y,
                ((x * 17 + seed) % 256, (y * 23 + seed * 3) % 256, (x * y + seed * 5) % 256),
            )
    return encode_png(image)


def _valid_bundle() -> dict[str, bytes]:
    return {key: _pattern(index + 1) for index, key in enumerate(PANEL_KEYS)}


def _event_input() -> DnbrEventInput:
    timestamp = datetime(2025, 1, 10, 12, tzinfo=timezone.utc)
    detection = DetectionInput("det-1", timestamp, 8.4, -80.2)
    event = EventInput(
        event_id="event-r1500_t06-quicklook-test",
        configuration_id="r1500_t06",
        start_timestamp_utc=timestamp,
        end_timestamp_utc=timestamp,
        detection_count=1,
        source_count=1,
        sources='["VIIRS"]',
        possible_chain_merge=False,
        month="2025-01",
        event_size_class="singleton",
        source_class="single_source",
        chain_class="no_possible_chain_merge",
        detections=(detection,),
    )
    pre = {
        "sentinel2_scene_id": "scene-pre",
        "acquisition_timestamp_utc": "2024-12-20T12:00:00Z",
    }
    post = {
        "sentinel2_scene_id": "scene-post",
        "acquisition_timestamp_utc": "2025-01-20T12:00:00Z",
    }
    return DnbrEventInput(
        event=event,
        selection={"selected_combination_id": "b0500_pre30_post45", "fallback_rescues": "no"},
        aoi_area_m2=1000.0,
        pre_scene=pre,
        post_scene=post,
        pre_candidates=(pre,),
        post_candidates=(post,),
    )


def test_rgb_source_is_preserved_without_scientific_colormap():
    payload = _pattern(9)
    details = decode_png_details(payload)
    assert details.mode == "RGB"
    assert details.array_shape == (8, 8, 3)
    assert details.raw_array_shape == (8, 8, 3)
    assert details.image.get_pixel(0, 0) == (9, 27, 45)
    assert details.channel_unique_counts[0] > 1


def test_rgba_is_composited_over_neutral_and_alpha_is_not_a_band():
    payload = _raw_png(
        3,
        1,
        6,
        [bytes((255, 0, 0, 255, 0, 0, 0, 0, 0, 0, 255, 128))],
    )
    details = decode_png_details(payload)
    assert details.mode == "RGBA"
    assert details.raw_array_shape == (1, 3, 4)
    assert details.array_shape == (1, 3, 3)
    assert details.alpha_present is True
    assert details.alpha_min == 0
    assert details.alpha_max == 255
    assert details.image.get_pixel(1, 0) == (148, 163, 184)
    assert details.image.get_pixel(0, 0) == (255, 0, 0)


def test_palette_png_is_converted_explicitly_to_rgb():
    payload = _raw_png(
        2,
        1,
        3,
        [bytes((0, 1))],
        palette=bytes((255, 0, 0, 0, 0, 255)),
    )
    details = decode_png_details(payload)
    assert details.mode == "P"
    assert details.image.get_pixel(0, 0) == (255, 0, 0)
    assert details.image.get_pixel(1, 0) == (0, 0, 255)
    assert details.array_shape == (1, 2, 3)


def test_nbr_and_dnbr_sources_remain_distinct_and_mask_does_not_contaminate():
    details, _stats = validate_thumbnail_sources(_valid_bundle())
    assert details["nbr_pre"].pixel_sha256 != details["dnbr"].pixel_sha256
    assert details["mask"].pixel_sha256 not in {
        details["rgb_pre"].pixel_sha256,
        details["rgb_post"].pixel_sha256,
        details["nbr_pre"].pixel_sha256,
        details["nbr_post"].pixel_sha256,
        details["dnbr"].pixel_sha256,
    }


def test_green_uniform_source_is_rejected_after_stats_are_recorded():
    green = encode_png(RGBImage.solid(8, 8, (0, 255, 0)))
    sources = {key: green for key in PANEL_KEYS}
    with pytest.raises(QuicklookValidationError) as caught:
        validate_thumbnail_sources(sources, filenames={key: f"{key}.png" for key in PANEL_KEYS})
    assert caught.value.stats["rgb_pre"]["exact_00FF00_percent"] == 100.0
    assert caught.value.stats["rgb_pre"]["unique_pixel_count"] == 1


class _FakeOverlayImage:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def byte(self) -> "_FakeOverlayImage":
        self.calls.append(("byte", None))
        return self

    def paint(self, target: object, color: int, width: int) -> "_FakeOverlayImage":
        self.calls.append(("paint", (target, color, width)))
        return self

    def selfMask(self) -> "_FakeOverlayImage":
        self.calls.append(("selfMask", None))
        return self

    def visualize(self, **parameters: object) -> "_FakeOverlayImage":
        self.calls.append(("visualize", parameters))
        return self

    def blend(self, other: "_FakeOverlayImage") -> "_FakeOverlayImage":
        self.calls.append(("blend", other))
        return self


class _FakeOverlayImageNamespace:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls

    def constant(self, _value: int) -> _FakeOverlayImage:
        return _FakeOverlayImage(self.calls)


class _FakeOverlayGeometry:
    @staticmethod
    def Point(coordinates: list[float]) -> tuple[str, list[float]]:
        return ("point", coordinates)


class _FakeOverlayEe:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.Image = _FakeOverlayImageNamespace(self.calls)
        self.Geometry = _FakeOverlayGeometry

    @staticmethod
    def Feature(geometry: object, properties: dict[str, str]) -> tuple[object, dict[str, str]]:
        return geometry, properties

    @staticmethod
    def FeatureCollection(features: list[object]) -> tuple[str, list[object]]:
        return "feature-collection", features


def test_overlay_masks_background_and_does_not_use_chroma_green():
    fake_ee = _FakeOverlayEe()
    event_input = _event_input()
    _quicklook_overlay(event_input, type("Aoi", (), {"geometry_wgs84": "aoi"})(), fake_ee)
    visualizations = [parameters for name, parameters in fake_ee.calls if name == "visualize"]
    assert len(visualizations) == 2
    assert all("00ff00" not in str(parameters).lower() for parameters in visualizations)
    assert sum(name == "selfMask" for name, _value in fake_ee.calls) == 2


def test_rebuild_from_local_pngs_does_not_need_earth_engine(tmp_path: Path):
    event_input = _event_input()
    prefix = "event-r1500_t06-quicklook-test_selected_pair_cs050"
    for key, payload in _valid_bundle().items():
        (tmp_path / f"{prefix}_{key}.png").write_bytes(payload)
    result = rebuild_quicklook_from_artifacts(
        event_input,
        output_dir=tmp_path,
        metrics_row={"valid_overlap_fraction": "0.75"},
    )
    assert result["status"] == "generated"
    assert Path(result["panel_path"]).is_file()
    assert result["metadata"]["rebuild_source"] == "existing_local_png_artifacts"


def test_invalid_local_sources_fail_before_panel_is_saved(tmp_path: Path):
    event_input = _event_input()
    prefix = "event-r1500_t06-quicklook-test_selected_pair_cs050"
    green = encode_png(RGBImage.solid(8, 8, (0, 255, 0)))
    for key in PANEL_KEYS:
        (tmp_path / f"{prefix}_{key}.png").write_bytes(green)
    panel_path = tmp_path / f"{prefix}_panel.png"
    with pytest.raises(QuicklookValidationError):
        rebuild_quicklook_from_artifacts(event_input, output_dir=tmp_path)
    assert not panel_path.exists()
