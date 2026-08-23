from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fuegopa.dnbr_quicklook import PANEL_KEYS, RGBImage, encode_png
from fuegopa.dnbr_quicklook_v2_1 import (
    CALIBRATION_EVENT_IDS,
    COMPARISON_HEIGHT,
    COMPARISON_WIDTH,
    DESCRIPTIVE_WARNING,
    MASK_LEGEND,
    MASK_SOURCE_CATEGORICAL_COLORS,
    NEGATIVE_DNBR_NOTE,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    POSITIVE_DNBR_NOTE,
    QUICKLOOK_VERSION,
    SPECTRAL_NODATA_NOTE,
    _event_summary,
    _window_composite_metadata,
    build_quicklook_v2_1_report,
    compare_protected_integrity,
    compose_panel_v2_1,
    compose_temporal_comparison_sheet_v2_1,
    decode_png_details,
    protected_integrity_snapshot,
    source_paths,
    write_quicklook_v2_1_outputs,
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


def _event_input(*, with_window_metadata: bool = True) -> DnbrEventInput:
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
    pre = {
        "sentinel2_scene_id": "scene-pre",
        "acquisition_timestamp_utc": "2025-01-20T12:00:00Z",
    }
    post = {
        "sentinel2_scene_id": "scene-post",
        "acquisition_timestamp_utc": "2025-02-20T12:00:00Z",
    }
    if with_window_metadata:
        pre_candidates = (
            {**pre, "window_start_utc": "2025-01-01T00:00:00Z", "window_end_utc": "2025-01-31T23:59:59Z"},
            {"sentinel2_scene_id": "scene-pre-2", "window_start_utc": "2025-01-01T00:00:00Z", "window_end_utc": "2025-01-31T23:59:59Z"},
        )
        post_candidates = (
            {**post, "window_start_utc": "2025-02-11T00:00:00Z", "window_end_utc": "2025-03-01T23:59:59Z"},
            {"sentinel2_scene_id": "scene-post-2", "window_start_utc": "2025-02-11T00:00:00Z", "window_end_utc": "2025-03-01T23:59:59Z"},
        )
    else:
        pre_candidates = (pre,)
        post_candidates = (post,)
    return DnbrEventInput(
        event=event,
        selection={"selected_combination_id": "b0500_pre30_post45", "fallback_rescues": "no"},
        aoi_area_m2=1_000_000.0,
        pre_scene=pre,
        post_scene=post,
        pre_candidates=pre_candidates,
        post_candidates=post_candidates,
    )


def _metadata(valid_overlap: float = 0.99) -> dict[str, object]:
    return {
        "event_id": CALIBRATION_EVENT_IDS[0],
        "event_start_utc": "2025-02-10T12:00:00Z",
        "event_end_utc": "2025-02-10T12:00:00Z",
        "pre_timestamp_utc": "2025-01-20T12:00:00Z",
        "post_timestamp_utc": "2025-02-20T12:00:00Z",
        "pre_lead_days": 21.0,
        "post_lag_days": 10.0,
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
            "pre_scene_count_used": "2",
            "post_scene_count_used": "2",
            "pre_scene_ids_used": "scene-pre;scene-pre-2",
            "post_scene_ids_used": "scene-post;scene-post-2",
            "quicklook_path": "",
        }
    )
    return selected, window


def test_mask_palette_keeps_gray_out_of_categorical_source_palette():
    assert MASK_SOURCE_CATEGORICAL_COLORS == ("#c026d3", "#0f766e", "#ffd166", "#00e5ff")
    assert MASK_LEGEND[-1]["color"] == "#94a3b8"
    assert "not a mask class" in MASK_LEGEND[-1]["meaning"]
    assert "spectral layers only" in SPECTRAL_NODATA_NOTE


def test_event_summary_uses_pre_lead_post_lag_and_local_window_metadata():
    selected, window = _metrics()
    summary = _event_summary(_event_input(), selected, window)
    window_metadata = summary["window_composite_metadata"]
    assert summary["pre_lead_days"] == 21.0
    assert summary["post_lag_days"] == 10.0
    assert summary["temporal_semantics"]["pre_label"] == "PRE LEAD"
    assert summary["temporal_semantics"]["post_label"] == "POST LAG"
    assert window_metadata["available_locally"] is True
    assert window_metadata["pre_window_start_utc"] == "2025-01-01T00:00:00Z"
    assert window_metadata["post_window_end_utc"] == "2025-03-01T23:59:59Z"
    assert window_metadata["pre_scene_count_used"] == 2
    assert window_metadata["post_scene_ids_used"] == "scene-post;scene-post-2"
    assert window_metadata["pre_window_start_utc"] != selected["pre_timestamp_utc"]


def test_panel_metadata_contains_exact_mask_semantics_and_sign_notes():
    payload = compose_panel_v2_1(_bundle(), _metadata(), _event_input())
    details = decode_png_details(payload)
    assert (details.width, details.height) == (PANEL_WIDTH, PANEL_HEIGHT) == (2048, 1440)
    assert details.mode == "RGB"
    assert details.alpha_present is False
    for marker in (
        QUICKLOOK_VERSION.encode(),
        b"PRE LEAD",
        b"POST LAG",
        b"#c026d3",
        b"#0f766e",
        b"#ffd166",
        b"#00e5ff",
        b"#94a3b8",
        POSITIVE_DNBR_NOTE.encode(),
        NEGATIVE_DNBR_NOTE.encode(),
        DESCRIPTIVE_WARNING.encode(),
    ):
        assert marker in payload
    assert b'"mask_semantics"' in payload
    assert b'"spectral_nodata_note"' in payload


def test_panel_reconstruction_is_deterministic():
    first = compose_panel_v2_1(_bundle(), _metadata(), _event_input())
    second = compose_panel_v2_1(_bundle(), _metadata(), _event_input())
    assert first == second


def test_temporal_sheet_exposes_window_metadata_without_selected_pair_window_dates():
    selected, window = _metrics()
    summary = _event_summary(_event_input(), selected, window)
    payload = compose_temporal_comparison_sheet_v2_1(summary, selected, window)
    details = decode_png_details(payload)
    assert (details.width, details.height) == (COMPARISON_WIDTH, COMPARISON_HEIGHT)
    assert details.mode == "RGB"
    assert details.alpha_present is False
    assert b"PRE SCENE: 2025-01-20T12:00:00Z" in payload
    assert b"PRE WINDOW: 2025-01-01T00:00:00Z to 2025-01-31T23:59:59Z" in payload
    assert b"POST WINDOW: 2025-02-11T00:00:00Z to 2025-03-01T23:59:59Z" in payload
    assert b"SCENES USED: PRE 2 / POST 2" in payload
    assert b"PRE: 2025-01-20T12:00:00Z" not in payload
    assert b"window_composite_metadata" in payload
    assert b"metrics only; no local window_median raster is available" in payload


def test_temporal_sheet_has_explicit_unavailable_window_fallback():
    selected, window = _metrics()
    metadata = _metadata()
    payload = compose_temporal_comparison_sheet_v2_1(metadata, selected, window)
    assert b"COMPOSITE WINDOW METADATA: unavailable locally" in payload
    assert b"metrics only; no local window_median raster is available" in payload
    assert b"PRE: 2025-01-20T12:00:00Z" not in payload


def test_window_metadata_without_candidates_is_unavailable():
    selected, window = _metrics()
    metadata = _window_composite_metadata(_event_input(with_window_metadata=False), window)
    assert metadata["available_locally"] is False
    assert metadata["pre_window_start_utc"] is None
    assert metadata["pre_scene_count_used"] is None


def test_v2_1_writer_uses_new_routes_and_preserves_v1_and_v2(tmp_path: Path):
    event_input = _event_input()
    source_dir = tmp_path / "v1"
    source_dir.mkdir()
    for key, payload in _bundle().items():
        source_paths(event_input.event_id, source_dir)[key].write_bytes(payload)
    v1_path = source_dir / "legacy_panel.png"
    v1_path.write_bytes(b"v1-preserved")
    old_v2_path = tmp_path / "v2" / "old.png"
    old_v2_path.parent.mkdir()
    old_v2_path.write_bytes(b"v2-preserved")
    selected, window = _metrics()
    result = write_quicklook_v2_1_outputs(
        event_input,
        selected_metrics=selected,
        window_metrics=window,
        source_dir=source_dir,
        output_dir=tmp_path / "v2_1-events",
        review_upload_dir=tmp_path / "review_upload_v2_1",
        root=tmp_path,
    )
    assert v1_path.read_bytes() == b"v1-preserved"
    assert old_v2_path.read_bytes() == b"v2-preserved"
    assert result["status"] == "generated"
    assert result["quicklook_version"] == QUICKLOOK_VERSION
    assert "v2_1" in result["main_panel_path"]
    assert Path(tmp_path / result["main_panel_path"]).is_file()
    assert Path(tmp_path / result["temporal_comparison_path"]).is_file()
    assert result["window_median_label"] == "metrics only"
    assert result["scientific_outputs_modified"] is False
    assert result["earth_engine_queries_made"] is False


def test_protected_snapshot_comparison_is_stable(tmp_path: Path):
    protected = tmp_path / "outputs" / "sentinel2_dnbr_report.json"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"protected")
    before = protected_integrity_snapshot(tmp_path)
    after = protected_integrity_snapshot(tmp_path)
    comparison = compare_protected_integrity(before, after)
    assert comparison["all_unchanged"] is True
    assert comparison["changed_count"] == 0


def test_v2_1_report_declares_visual_only_boundary():
    results = [{"event_id": event_id, "status": "generated"} for event_id in CALIBRATION_EVENT_IDS]
    report = build_quicklook_v2_1_report(results, requested_event_ids=CALIBRATION_EVENT_IDS)
    assert report["quicklook_version"] == QUICKLOOK_VERSION
    assert report["generated_count"] == 7
    assert report["failed_count"] == 0
    assert report["scientific_outputs_modified"] is False
    assert report["scientific_csv_json_modified"] is False
    assert report["scene_selection_modified"] is False
    assert report["cohort_modified"] is False
    assert report["human_review_started"] is False
    assert report["significant_burn_labels_created"] is False
