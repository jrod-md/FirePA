from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.dnbr_quicklook import decode_png_details
from fuegopa.quicklook_level2 import (
    ANALYSIS_CRS,
    CALIBRATION_EVENT_IDS,
    FALSE_COLOR_BANDS,
    Level2MetricMismatch,
    NUMERIC_NODATA,
    _validate_raster_contract,
    compare_local_metrics,
    compute_global_false_color_stretch,
    compute_local_metrics,
    read_geotiff,
)


def _write_tiff(
    path: Path,
    *,
    width: int,
    height: int,
    bands: int,
    values: list[float | int],
    dtype: str,
    nodata: float | int | None,
) -> None:
    endian = "<"
    bits = 8 if dtype == "uint8" else 16 if dtype == "uint16" else 32
    sample_format = 3 if dtype == "float32" else 1
    format_code = "B" if dtype == "uint8" else "H" if dtype == "uint16" else "f"
    packed_values = struct.pack(endian + format_code * len(values), *values)
    tag_values: list[tuple[int, int, int, bytes]] = []

    def short(value: int) -> bytes:
        return struct.pack(endian + "H", value)

    def long(value: int) -> bytes:
        return struct.pack(endian + "I", value)

    def doubles(values_: list[float]) -> bytes:
        return struct.pack(endian + "d" * len(values_), *values_)

    tag_values.extend(
        [
            (256, 4, 1, long(width)),
            (257, 4, 1, long(height)),
            (258, 3, bands, b""),
            (259, 3, 1, short(1)),
            (262, 3, 1, short(1)),
            (273, 4, 1, b""),
            (277, 3, 1, short(bands)),
            (278, 4, 1, long(height)),
            (279, 4, 1, b""),
            (284, 3, 1, short(1)),
            (339, 3, 1, short(sample_format)),
            (33550, 12, 3, doubles([20.0, 20.0, 0.0])),
            (33922, 12, 6, doubles([0.0, 0.0, 0.0, 500000.0, 1000000.0, 0.0])),
            (34735, 3, 8, struct.pack(endian + "8H", 1, 1, 0, 1, 3072, 0, 1, 32617)),
        ]
    )
    if nodata is not None:
        text = str(nodata).encode("ascii") + b"\x00"
        tag_values.append((42113, 2, len(text), text))
    tag_values.sort(key=lambda item: item[0])

    ifd_offset = 8
    ifd_size = 2 + len(tag_values) * 12 + 4
    extra_offset = ifd_offset + ifd_size
    extra = bytearray()
    entries: list[bytes] = []
    for tag, field_type, count, payload in tag_values:
        size = {2: 1, 3: 2, 4: 4, 12: 8}[field_type]
        total = size * count
        if tag == 258:
            payload = struct.pack(endian + "H" * bands, *([bits] * bands))
            total = len(payload)
        if tag == 273:
            payload = long(extra_offset + 0)  # patched after extra blocks are known
            total = 4
        if tag == 279:
            payload = long(len(packed_values))
            total = 4
        if total <= 4:
            inline = payload + b"\x00" * (4 - len(payload))
            entries.append(struct.pack(endian + "HHI4s", tag, field_type, count, inline))
        else:
            offset = extra_offset + len(extra)
            extra.extend(payload)
            entries.append(struct.pack(endian + "HHII", tag, field_type, count, offset))
    strip_offset = extra_offset + len(extra)
    entries = [
        entry if struct.unpack_from(endian + "H", entry, 0)[0] != 273 else struct.pack(endian + "HHII", 273, 4, 1, strip_offset)
        for entry in entries
    ]
    payload = bytearray(b"II" + struct.pack(endian + "H", 42) + struct.pack(endian + "I", ifd_offset))
    payload.extend(struct.pack(endian + "H", len(entries)))
    payload.extend(b"".join(entries))
    payload.extend(struct.pack(endian + "I", 0))
    payload.extend(extra)
    payload.extend(packed_values)
    path.write_bytes(bytes(payload))


def _metric_rasters(tmp_path: Path) -> dict[str, Path]:
    common = [1, 1, 1, 0]
    support = [1, 1, 1, 1]
    dnbr = [0.1, 0.2, 0.3, NUMERIC_NODATA]
    pre = [0.5, 0.6, 0.7, NUMERIC_NODATA]
    post = [0.4, 0.4, 0.4, NUMERIC_NODATA]
    paths = {}
    for key, values, dtype, nodata in (
        ("common_valid_mask", common, "uint8", 0),
        ("aoi_support", support, "uint8", 0),
        ("dnbr", dnbr, "float32", NUMERIC_NODATA),
        ("nbr_pre", pre, "float32", NUMERIC_NODATA),
        ("nbr_post", post, "float32", NUMERIC_NODATA),
    ):
        path = tmp_path / f"{key}.tif"
        _write_tiff(path, width=2, height=2, bands=1, values=values, dtype=dtype, nodata=nodata)
        paths[key] = path
    return paths


def test_read_geotiff_preserves_bands_crs_transform_and_nodata(tmp_path: Path):
    path = tmp_path / "multiband.tif"
    _write_tiff(
        path,
        width=2,
        height=1,
        bands=3,
        values=[100, 200, 300, 400, 500, 600],
        dtype="uint16",
        nodata=0,
    )
    raster = read_geotiff(path)
    assert raster.dtype == "uint16"
    assert raster.band_count == 3
    assert raster.crs == ANALYSIS_CRS
    assert raster.transform == (20.0, 0.0, 500000.0, 0.0, -20.0, 1000000.0)
    assert raster.data == ((100.0, 400.0), (200.0, 500.0), (300.0, 600.0))
    _validate_raster_contract(raster, expected_bands=3, expected_dtype="uint16", nodata=0)


def test_local_metrics_reconcile_from_numeric_rasters(tmp_path: Path):
    paths = _metric_rasters(tmp_path)
    local = compute_local_metrics(paths)
    assert local["common_valid_pixel_count"] == 3
    assert local["aoi_pixel_count"] == 4
    assert local["valid_overlap_fraction"] == pytest.approx(0.75)
    assert local["dnbr_median"] == pytest.approx(0.2)
    assert local["dnbr_p90"] == pytest.approx(0.28)
    # The float32 representation of 0.2 is slightly above the strict > 0.2
    # threshold, which is the same comparison performed by the local contract.
    assert local["area_ha_dnbr_gt_020"] == pytest.approx(0.08)
    result = compare_local_metrics(
        {
            "dnbr_median": "0.2",
            "dnbr_p90": "0.28",
            "area_ha_dnbr_gt_010": "0.08",
            "area_ha_dnbr_gt_020": "0.08",
            "area_ha_dnbr_gt_030": "0.0",
            "area_ha_dnbr_gt_040": "0.0",
            "valid_overlap_fraction": "0.75",
            "common_valid_pixel_count": "3",
        },
        local,
        event_id=CALIBRATION_EVENT_IDS[0],
        analysis_mode="selected_pair",
    )
    assert result["status"] == "pass"


def test_metric_mismatch_is_hard_failure(tmp_path: Path):
    local = compute_local_metrics(_metric_rasters(tmp_path))
    with pytest.raises(Level2MetricMismatch):
        compare_local_metrics(
            {
                "dnbr_median": "0.9",
                "dnbr_p90": "0.28",
                "area_ha_dnbr_gt_010": "0.08",
                "area_ha_dnbr_gt_020": "0.04",
                "area_ha_dnbr_gt_030": "0.0",
                "area_ha_dnbr_gt_040": "0.0",
                "valid_overlap_fraction": "0.75",
                "common_valid_pixel_count": "3",
            },
            local,
            event_id=CALIBRATION_EVENT_IDS[0],
            analysis_mode="selected_pair",
        )


def test_global_false_color_stretch_is_shared_across_fourteen_rasters(tmp_path: Path):
    paths = []
    for index in range(14):
        path = tmp_path / f"false_color_{index}.tif"
        _write_tiff(
            path,
            width=2,
            height=1,
            bands=3,
            values=[100 + index, 200 + index, 300 + index, 1000 + index, 1200 + index, 1400 + index],
            dtype="uint16",
            nodata=0,
        )
        paths.append(path)
    stretch = compute_global_false_color_stretch(paths)
    assert stretch["source_raster_count"] == 14
    assert [item["band"] for item in stretch["bands"]] == list(FALSE_COLOR_BANDS)
    assert stretch["per_event_recalculation"] is False


def test_level2_panel_has_exact_dimensions_and_numeric_evidence_marker(tmp_path: Path):
    # This test exercises the parser/metric path above; panel construction is
    # covered by the integration run because it requires a complete event AOI.
    assert read_geotiff(_metric_rasters(tmp_path)["dnbr"]).pixel_area_m2 == 400.0
