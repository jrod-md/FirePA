from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.dnbr_quicklook import PANEL_KEYS, RGBImage, QuicklookValidationError, encode_png
from fuegopa.dnbr_quicklook_v2 import (
    CALIBRATION_EVENT_IDS,
    COMPARISON_HEIGHT,
    COMPARISON_WIDTH,
    DESCRIPTIVE_WARNING,
    DIAGNOSTIC_UNAVAILABLE_NOTE,
    FALSE_COLOR_DEFERRED_NOTE,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    QUICKLOOK_VERSION,
    RESAMPLING_POLICY,
    _resize_nearest,
    _resize_bilinear,
    build_quicklook_v2_report,
    compose_panel_v2,
    compose_temporal_comparison_sheet,
    decode_png_details,
    resolve_system_font,
    scientific_bundle_integrity,
    source_paths,
    write_quicklook_v2_outputs,
)
from fuegopa.sentinel2_dnbr import DnbrEventInput
from fuegopa.sentinel2_observability import DetectionInput, EventInput


def _pattern(seed: int, width: int = 24, height: int = 18) -> bytes:
    image = RGBImage.solid(width, height, (0, 0, 0))
    for y in range(height):
        for x in range(width):
            image.set_pixel(
                x,
                y,
                (
                    (x * 13 + seed * 5) % 256,
                    (y * 17 + seed * 7) % 256,
                    (x * y + seed * 11) % 256,
                ),
            )
    return encode_png(image)


def _bundle() -> dict[str, bytes]:
    return {key: _pattern(index + 1) for index, key in enumerate(PANEL_KEYS)}


def _event_input() -> DnbrEventInput:
    event_time = datetime(2025, 2, 10, 12, 0, tzinfo=timezone.utc)
    detections = (
        DetectionInput("det-1", event_time, 8.4, -80.2),
        DetectionInput("det-2", event_time, 8.401, -80.199),
    )
    event = EventInput(
        event_id=CALIBRATION_EVENT_IDS[0],
        configuration_id="r1500_t06",
        start_timestamp_utc=event_time,
        end_timestamp_utc=event_time,
        detection_count=2,
        source_count=1,
        sources='["VIIRS"]',
        possible_chain_merge=False,
        month="2025-02",
        event_size_class="multi_detection",
        source_class="single_source",
        chain_class="no_possible_chain_merge",
        detections=detections,
    )
    pre = {"sentinel2_scene_id": "scene-pre", "acquisition_timestamp_utc": "2025-01-20T12:00:00Z"}
    post = {"sentinel2_scene_id": "scene-post", "acquisition_timestamp_utc": "2025-02-20T12:00:00Z"}
    return DnbrEventInput(
        event=event,
        selection={"selected_combination_id": "b0500_pre30_post45", "fallback_rescues": "no"},
        aoi_area_m2=1_000_000.0,
        pre_scene=pre,
        post_scene=post,
        pre_candidates=(pre,),
        post_candidates=(post,),
    )


def _metadata(valid_overlap: float = 0.99) -> dict[str, object]:
    return {
        "event_id": CALIBRATION_EVENT_IDS[0],
        "event_start_utc": "2025-02-10T12:00:00Z",
        "event_end_utc": "2025-02-10T12:00:00Z",
        "pre_timestamp_utc": "2025-01-20T12:00:00Z",
        "post_timestamp_utc": "2025-02-20T12:00:00Z",
        "days_event_to_pre": 21.0,
        "days_event_to_post": 10.0,
        "policy_path": "principal",
        "selected_combination_id": "b0500_pre30_post45",
        "valid_overlap_fraction": valid_overlap,
        "valid_overlap_percent": valid_overlap * 100,
        "dnbr_median": 0.123,
        "dnbr_p90": 0.456,
        "area_ha_dnbr_gt_020": 1.25,
        "metric_status": "usable_overlap",
    }


def _metrics() -> tuple[dict[str, str], dict[str, str]]:
    selected = {
        "event_id": CALIBRATION_EVENT_IDS[0],
        "analysis_mode": "selected_pair",
        "cloud_threshold": "0.5",
        "policy_path": "principal",
        "selected_combination_id": "b0500_pre30_post45",
        "pre_timestamp_utc": "2025-01-20T12:00:00Z",
        "post_timestamp_utc": "2025-02-20T12:00:00Z",
        "valid_overlap_fraction": "0.99",
        "dnbr_median": "0.123",
        "dnbr_p90": "0.456",
        "area_ha_dnbr_gt_020": "1.25",
        "metric_status": "usable_overlap",
    }
    window = dict(selected)
    window.update(
        {
            "analysis_mode": "window_median",
            "valid_overlap_fraction": "0.98",
            "dnbr_median": "0.145",
            "dnbr_p90": "0.47",
            "area_ha_dnbr_gt_020": "1.45",
            "quicklook_path": "",
        }
    )
    return selected, window


def test_quicklook_v2_contract_dimensions_rgb_and_metadata():
    payload = compose_panel_v2(_bundle(), _metadata(), _event_input())
    details = decode_png_details(payload)
    assert QUICKLOOK_VERSION == "fuegopa-dnbr-quicklook-v2"
    assert (details.width, details.height) == (PANEL_WIDTH, PANEL_HEIGHT) == (2048, 1440)
    assert details.mode == "RGB"
    assert details.alpha_present is False
    assert details.unique_pixel_count > 1
    for marker in (
        CALIBRATION_EVENT_IDS[0],
        QUICKLOOK_VERSION,
        b"selected_pair",
        b"2025-01-20T12:00:00Z",
        b"NBR",
        b"500 m",
        b"20 m",
        DESCRIPTIVE_WARNING.encode(),
    ):
        assert (marker if isinstance(marker, bytes) else marker.encode()) in payload


def test_mask_uses_compact_inset_when_valid_fraction_is_high():
    payload = compose_panel_v2(_bundle(), _metadata(0.99), _event_input())
    assert b"compact_inset" in payload
    assert b"COMPACT INSET" in payload


def test_mask_remains_full_when_invalid_fraction_is_material():
    payload = compose_panel_v2(_bundle(), _metadata(0.75), _event_input())
    assert b"full_panel" in payload
    assert b"COMPACT INSET" not in payload


def test_resampling_policy_keeps_scientific_layers_nearest():
    assert RESAMPLING_POLICY["rgb"] == "bilinear_presentation_only"
    assert RESAMPLING_POLICY["mask"] == "nearest_neighbor"
    source = RGBImage.solid(2, 1, (0, 0, 0))
    source.set_pixel(0, 0, (0, 0, 0))
    source.set_pixel(1, 0, (255, 255, 255))
    nearest = _resize_nearest(source, 3, 1)
    bilinear = _resize_bilinear(source, 3, 1)
    assert nearest.get_pixel(1, 0) in {(0, 0, 0), (255, 255, 255)}
    assert bilinear.get_pixel(1, 0) not in {(0, 0, 0), (255, 255, 255)}


def test_reconstruction_is_deterministic():
    first = compose_panel_v2(_bundle(), _metadata(), _event_input())
    second = compose_panel_v2(_bundle(), _metadata(), _event_input())
    assert first == second


def test_true_type_font_is_system_owned_and_not_distributed():
    font = resolve_system_font()
    assert font.path.is_file()
    assert "FirePA" not in str(font.path)
    assert font.backend == "windows-gdi"


def test_missing_font_fails_before_panel_is_saved(monkeypatch, tmp_path: Path):
    import fuegopa.dnbr_quicklook_v2 as module

    monkeypatch.setattr(module, "FONT_PATH_CANDIDATES", (tmp_path / "missing.ttf",))
    with pytest.raises(QuicklookValidationError, match="fuente TrueType"):
        compose_panel_v2(_bundle(), _metadata(), _event_input())


def test_uniform_green_sources_fail_safe():
    green = encode_png(RGBImage.solid(16, 16, (0, 255, 0)))
    with pytest.raises(QuicklookValidationError):
        compose_panel_v2({key: green for key in PANEL_KEYS}, _metadata(), _event_input())


def test_temporal_sheet_keeps_modes_separate_and_marks_metrics_only():
    selected, window = _metrics()
    payload = compose_temporal_comparison_sheet(_metadata(), selected, window)
    details = decode_png_details(payload)
    assert (details.width, details.height) == (COMPARISON_WIDTH, COMPARISON_HEIGHT)
    assert details.mode == "RGB"
    assert b"selected_pair" in payload
    assert b"window_median" in payload
    assert b"metrics only" in payload
    assert b"window_median_quicklook_path" in payload
    assert b"window_median_raster_available" in payload


def test_temporal_sheet_contains_absolute_differences_and_descriptive_flag():
    selected, window = _metrics()
    payload = compose_temporal_comparison_sheet(_metadata(), selected, window)
    assert b"ABSOLUTE DIFFERENCES" in payload
    assert b"FLAG:" in payload
    assert b"descriptive" in payload


def test_diagnostic_range_is_omitted_without_local_numeric_raster():
    payload = compose_panel_v2(_bundle(), _metadata(), _event_input())
    assert DIAGNOSTIC_UNAVAILABLE_NOTE.encode() in payload
    assert b'"diagnostic_dnbr_range":null' in payload


def test_false_color_is_deferred_without_traceable_swir_artifacts():
    payload = compose_panel_v2(_bundle(), _metadata(), _event_input())
    assert FALSE_COLOR_DEFERRED_NOTE.encode() in payload
    assert b"false_color_swir" in payload


def test_source_routes_are_v2_separate_from_v1():
    paths = source_paths(CALIBRATION_EVENT_IDS[0], Path("outputs/figures/sentinel2_dnbr/events"))
    assert all(path.name.endswith(".png") and "panel" not in path.name for path in paths.values())
    main_name = f"{CALIBRATION_EVENT_IDS[0]}_selected_pair_cs050_panel_v2.png"
    assert "v2" in main_name
    assert "sentinel2_dnbr_v2" not in str(paths["rgb_pre"])


def test_v2_writer_does_not_overwrite_v1_and_writes_both_sheets(tmp_path: Path):
    event_input = _event_input()
    source_dir = tmp_path / "v1"
    source_dir.mkdir()
    for key, payload in _bundle().items():
        source_paths(event_input.event_id, source_dir)[key].write_bytes(payload)
    v1_path = source_dir / "legacy_panel.png"
    v1_path.write_bytes(b"v1-preserved")
    selected, window = _metrics()
    result = write_quicklook_v2_outputs(
        event_input,
        selected_metrics=selected,
        window_metrics=window,
        source_dir=source_dir,
        output_dir=tmp_path / "v2-events",
        review_upload_dir=tmp_path / "review_upload_v2",
        root=tmp_path,
    )
    assert v1_path.read_bytes() == b"v1-preserved"
    assert result["status"] == "generated"
    assert Path(tmp_path / result["main_panel_path"]).is_file()
    assert Path(tmp_path / result["temporal_comparison_path"]).is_file()
    assert result["window_median_label"] == "metrics only"
    assert result["scientific_outputs_modified"] is False


def test_v2_writer_preserves_metric_mapping_and_scientific_boundary(tmp_path: Path):
    event_input = _event_input()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    paths = source_paths(event_input.event_id, source_dir)
    for key, payload in _bundle().items():
        paths[key].write_bytes(payload)
    selected, window = _metrics()
    selected_before = dict(selected)
    window_before = dict(window)
    result = write_quicklook_v2_outputs(
        event_input,
        selected_metrics=selected,
        window_metrics=window,
        source_dir=source_dir,
        output_dir=tmp_path / "out",
        review_upload_dir=tmp_path / "upload",
        root=tmp_path,
    )
    assert selected == selected_before
    assert window == window_before
    assert result["earth_engine_queries_made"] is False
    assert result["source_numeric_rasters_read"] is False


def test_report_declares_seven_events_and_no_scientific_mutation():
    results = [{"event_id": event_id, "status": "generated"} for event_id in CALIBRATION_EVENT_IDS]
    report = build_quicklook_v2_report(results, requested_event_ids=CALIBRATION_EVENT_IDS)
    assert report["quicklook_version"] == QUICKLOOK_VERSION
    assert report["generated_count"] == 7
    assert report["failed_count"] == 0
    assert report["scientific_outputs_modified"] is False
    assert report["scientific_csv_json_modified"] is False
    assert report["diagnostic_dnbr_map"] == "omitted"


def test_integrity_snapshot_rechecks_scientific_and_v1_visual_bytes(tmp_path: Path):
    scientific = tmp_path / "science.csv"
    visual = tmp_path / "v1.png"
    scientific.write_bytes(b"scientific")
    visual.write_bytes(b"v1")
    import hashlib
    import json

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "commit_sha": "test",
                "entries": [
                    {
                        "path": "science.csv",
                        "classification": "scientific_output",
                        "sha256": hashlib.sha256(b"scientific").hexdigest(),
                    },
                    {
                        "path": "v1.png",
                        "classification": "visual_output",
                        "sha256": hashlib.sha256(b"v1").hexdigest(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    integrity = scientific_bundle_integrity(manifest, root=tmp_path)
    assert integrity["scientific_changed_count"] == 0
    assert integrity["visual_changed_count"] == 0
    assert integrity["scientific_outputs_unchanged"] is True
    assert integrity["v1_visual_outputs_unchanged"] is True
