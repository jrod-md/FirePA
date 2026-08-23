from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fuegopa.dnbr_quicklook import decode_png_details
from fuegopa.quicklook_level2 import (
    ANALYSIS_CRS,
    ANALYSIS_SCALE_M,
    CALIBRATION_EVENT_IDS,
    DIAGNOSTIC_DNBR_RANGE,
    GLOBAL_DNBR_RANGE,
    METRIC_TOLERANCES,
    NUMERIC_NODATA,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PRIMARY_CLOUD_THRESHOLD,
    RGB_REFLECTANCE_RANGE,
)
from fuegopa.window_median_review_asset import (
    ASSET_CONTRACT_VERSION,
    AssetConflictError,
    FORBIDDEN_FIELDS,
    _check_existing_identity,
    _validate_panel_payload,
    compose_window_median_panel,
    dnbr_from_composites,
    nbr_from_reflectance,
    panel_path_for_event,
    raster_paths_for_event,
    reflectance_median_per_band,
    verify_pilot,
    window_bounds,
)

from test_quicklook_level2 import _write_tiff


def test_window_median_uses_reflectance_median_before_nbr_and_dnbr():
    pre = reflectance_median_per_band(
        [
            {"B8": (0.8, 0.6), "B12": (0.2, 0.2)},
            {"B8": (0.6, 0.7), "B12": (0.4, 0.3)},
            {"B8": (0.7, 0.9), "B12": (0.3, 0.1)},
        ]
    )
    post = {"B8": (0.5, 0.5), "B12": (0.5, 0.25)}
    assert pre == {"B8": (0.7, 0.7), "B12": (0.3, 0.2)}
    assert nbr_from_reflectance(pre) == pytest.approx((0.4, 0.5555555556))
    assert dnbr_from_composites(pre, post) == pytest.approx((0.4, 0.2222222222))


def test_frozen_calibration_cases_and_temporal_fallback():
    assert CALIBRATION_EVENT_IDS == (
        "event-r1500_t06-0ddd477d24b1364d",
        "event-r1500_t06-84cb252a6877d2d5",
        "event-r1500_t06-ef20fd746737f4ea",
        "event-r1500_t06-9e5bf1d807f9d61a",
        "event-r1500_t06-548ca9e284d1a330",
        "event-r1500_t06-040b1a186d857b11",
        "event-r1500_t06-09c2d54e2d8fb5dd",
    )
    event = SimpleNamespace(
        selected_combination_id="b0500_pre30_post90",
        event=SimpleNamespace(
            start_timestamp_utc=datetime(2025, 5, 10, tzinfo=timezone.utc),
            end_timestamp_utc=datetime(2025, 5, 10, 1, tzinfo=timezone.utc),
        ),
    )
    bounds = window_bounds(event)
    assert (bounds.pre_end - bounds.pre_start).days == 25
    assert (bounds.post_end - bounds.post_start).days == 85
    assert event.selected_combination_id == "b0500_pre30_post90"


def test_mode_paths_are_separate():
    event_id = CALIBRATION_EVENT_IDS[0]
    paths = raster_paths_for_event(Path("repo"), event_id)
    assert all("window_median" in path.name for path in paths.values())
    assert panel_path_for_event(Path("repo"), event_id).name.endswith("window_median_cs050_review_panel.png")
    assert all("selected_pair" not in path.name for path in paths.values())


def test_frozen_visual_ranges_and_contract():
    assert ANALYSIS_CRS == "EPSG:32617"
    assert ANALYSIS_SCALE_M == 20
    assert PRIMARY_CLOUD_THRESHOLD == 0.50
    assert RGB_REFLECTANCE_RANGE == (0.0, 3000.0)
    assert GLOBAL_DNBR_RANGE == (-1.0, 1.0)
    assert DIAGNOSTIC_DNBR_RANGE == (-0.25, 0.50)
    assert METRIC_TOLERANCES["dnbr_median"] == 0.005
    assert ASSET_CONTRACT_VERSION == "firepa-window-median-review-asset-v1"


def _panel_fixture(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    values_by_key = {
        "aoi_support": ([1, 1, 1, 1], "uint8", 0),
        "common_valid_mask": ([1, 1, 1, 0], "uint8", 0),
        "rgb_pre": ([100, 200, 300, 500, 600, 700, 800, 900, 1000, 1200, 1300, 1400], "uint16", 0),
        "rgb_post": ([150, 250, 350, 550, 650, 750, 850, 950, 1050, 1250, 1350, 1450], "uint16", 0),
        "false_color_pre": ([700, 1400, 300, 800, 1500, 400, 900, 1600, 500, 1000, 1700, 600], "uint16", 0),
        "false_color_post": ([750, 1450, 350, 850, 1550, 450, 950, 1650, 550, 1050, 1750, 650], "uint16", 0),
        "nbr_pre": ([0.4, 0.5, 0.6, NUMERIC_NODATA], "float32", NUMERIC_NODATA),
        "nbr_post": ([0.2, 0.3, 0.4, NUMERIC_NODATA], "float32", NUMERIC_NODATA),
        "dnbr": ([0.2, 0.2, 0.2, NUMERIC_NODATA], "float32", NUMERIC_NODATA),
    }
    for key, (values, dtype, nodata) in values_by_key.items():
        path = tmp_path / f"{key}.tif"
        _write_tiff(path, width=2, height=2, bands=3 if key.startswith(("rgb", "false_color")) else 1, values=values, dtype=dtype, nodata=nodata)
        paths[key] = path
    return paths


def test_panel_is_self_contained_rgb_nonuniform_and_has_fixed_mode_marker(tmp_path: Path):
    paths = _panel_fixture(tmp_path)
    event_input = SimpleNamespace(
        event_id=CALIBRATION_EVENT_IDS[0],
        selected_combination_id="b0500_pre30_post45",
        policy_path="principal",
        event=SimpleNamespace(
            start_timestamp_utc=datetime(2025, 1, 10, tzinfo=timezone.utc),
            end_timestamp_utc=datetime(2025, 1, 10, 1, tzinfo=timezone.utc),
        ),
        pre_candidates=({"data_coverage_fraction": "1", "clear_fraction_cs_cdf_050": "0.9"},),
        post_candidates=({"data_coverage_fraction": "1", "clear_fraction_cs_cdf_050": "0.9"},),
    )
    stretch = {
        "per_event_recalculation": False,
        "bands": [
            {"band": "B12", "minimum": 700, "maximum": 2700},
            {"band": "B8A", "minimum": 1300, "maximum": 5300},
            {"band": "B4", "minimum": 250, "maximum": 2000},
        ],
    }
    payload = compose_window_median_panel(
        event_input=event_input,
        local_metrics={
            "valid_overlap_fraction": 0.75,
            "dnbr_median": 0.2,
            "dnbr_p90": 0.2,
            "area_ha_dnbr_gt_020": 0.04,
        },
        raster_paths=paths,
        stretch=stretch,
        root=tmp_path,
        warnings=("MASK_OR_NODATA",),
    )
    details = decode_png_details(payload)
    assert details.mode == "RGB"
    assert not details.alpha_present
    assert (details.width, details.height) == (PANEL_WIDTH, PANEL_HEIGHT)
    assert details.unique_pixel_count > 1
    assert b"window_median" in payload
    assert _validate_panel_payload(payload, event_id=event_input.event_id)["mode"] == "RGB"


def test_panel_validation_rejects_uniform_payload():
    from fuegopa.dnbr_quicklook import RGBImage, encode_png

    payload = encode_png(RGBImage.solid(PANEL_WIDTH, PANEL_HEIGHT, (0, 255, 0)))
    with pytest.raises(Exception, match="uniform|#00FF00"):
        _validate_panel_payload(payload, event_id=CALIBRATION_EVENT_IDS[0])


def test_existing_identity_with_different_bytes_is_conflict():
    expected = {
        "asset_id": "asset",
        "analysis_mode": "window_median",
        "panel": {"sha256": "expected"},
        "rasters": {"dnbr": {"sha256": "raster"}},
    }
    with pytest.raises(AssetConflictError):
        _check_existing_identity(
            expected,
            b"different",
            {"asset_id": "asset", "analysis_mode": "window_median", "panel": {"sha256": "expected"}, "rasters": {"dnbr": {"sha256": "raster"}}},
        )


def test_resume_accepts_same_identity_and_bytes():
    import hashlib

    panel_payload = b"stable-panel"
    panel_sha = hashlib.sha256(panel_payload).hexdigest()
    sidecar = {
        "asset_id": ASSET_CONTRACT_VERSION,
        "analysis_mode": "window_median",
        "panel": {"sha256": panel_sha},
        "rasters": {"dnbr": {"sha256": "raster"}},
    }
    _check_existing_identity(sidecar, panel_payload, sidecar)


def test_verify_only_is_read_only_when_package_is_missing(tmp_path: Path):
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    result = verify_pilot(tmp_path)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert result["status"] == "fail"
    assert result["read_only"] is True
    assert result["earth_engine_queries_made"] is False
    assert before == after == []


def test_no_forbidden_scientific_or_review_fields_are_declared():
    assert "significant_burn" in FORBIDDEN_FIELDS
    assert "severity" in FORBIDDEN_FIELDS
    assert "review_status" in FORBIDDEN_FIELDS
