from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.earth_engine import EarthEngineQueryError
from fuegopa.sentinel2_dnbr import (
    ANALYSIS_SCALE_M,
    ANALYSIS_MODES,
    AOI_ID,
    CLOUD_THRESHOLDS,
    DNBR_FORMULA,
    DNBR_PIPELINE_VERSION,
    DnbrEventInput,
    DnbrInputs,
    DnbrValidationError,
    EXPECTED_EXCLUDED_EVENT_COUNT,
    EXPECTED_PROCESSABLE_EVENT_COUNT,
    METRICS_COLUMNS,
    NBR_FORMULA,
    OVERLAP_SUPPORT_CONTRACT,
    PRIMARY_CLOUD_THRESHOLD,
    REVIEW_QUEUE_COLUMNS,
    _analysis_aoi_support,
    _analysis_pixel_area,
    _masked_analysis_support,
    _metric_row,
    _thumb_parameters,
    _validate_selection_metadata,
    build_review_queue,
    build_report,
    cache_path,
    cache_signature,
    dnbr_value,
    load_event_cache,
    merge_event_rows,
    nbr_value,
    normalize_overlap_fraction,
    overlap_fraction_tolerance,
    percentile_order_is_valid,
    write_event_cache,
)
from fuegopa.dnbr_quicklook import (
    DNBR_VIS_MAX,
    DNBR_VIS_MIN,
    NBR_VIS_MAX,
    NBR_VIS_MIN,
    PANEL_HEIGHT,
    PANEL_KEYS,
    PANEL_WIDTH,
    VISUALIZATION_PALETTE,
    RGBImage,
    compose_panel_png,
    decode_png,
    encode_png,
    panel_filename,
    quicklook_path_for_mode,
)
from fuegopa.sentinel2_observability import DetectionInput, EventInput


ROOT = Path(__file__).resolve().parents[1]


def _runner_module():
    path = ROOT / "scripts" / "run_sentinel2_dnbr.py"
    spec = importlib.util.spec_from_file_location("fuegopa_dnbr_runner_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event_input() -> DnbrEventInput:
    event = EventInput(
        event_id="event-r1500_t06-test",
        configuration_id="r1500_t06",
        start_timestamp_utc=datetime(2025, 1, 10, 12, tzinfo=timezone.utc),
        end_timestamp_utc=datetime(2025, 1, 10, 13, tzinfo=timezone.utc),
        detection_count=1,
        source_count=1,
        sources='["VIIRS"]',
        possible_chain_merge=False,
        month="2025-01",
        event_size_class="singleton",
        source_class="single_source",
        chain_class="no_possible_chain_merge",
        detections=(
            DetectionInput(
                "det-test",
                datetime(2025, 1, 10, 12, tzinfo=timezone.utc),
                8.4,
                -80.2,
            ),
        ),
    )
    pre = {
        "sentinel2_scene_id": "scene-pre",
        "acquisition_timestamp_utc": "2024-12-20T12:00:00Z",
    }
    post = {
        "sentinel2_scene_id": "scene-post",
        "acquisition_timestamp_utc": "2025-01-20T12:00:00Z",
    }
    selection = {
        "selected_combination_id": "b0500_pre30_post45",
        "fallback_rescues": "no",
    }
    return DnbrEventInput(
        event=event,
        selection=selection,
        aoi_area_m2=1000.0,
        pre_scene=pre,
        post_scene=post,
        pre_candidates=(pre,),
        post_candidates=(post,),
    )


def _selection_row(event_id: str, *, usable: bool) -> dict[str, str]:
    return {
        "event_id": event_id,
        "configuration_id": "r1500_t06",
        "policy_rule": "A",
        "primary_combination_id": "b0500_pre30_post45",
        "primary_sufficient": "yes" if usable else "no",
        "fallback_rescues": "no",
        "selected_combination_id": "b0500_pre30_post45" if usable else "",
        "selected_pre_scene_id": "pre" if usable else "",
        "selected_post_scene_id": "post" if usable else "",
        "pre_scene_acquisition_timestamp": "2024-12-20T00:00:00Z" if usable else "",
        "post_scene_acquisition_timestamp": "2025-01-20T00:00:00Z" if usable else "",
        "final_observability_status": "usable_pair" if usable else "excluded_no_usable_pair",
        "final_exclusion_reason": "not_applicable" if usable else "no_usable_pre_scene_in_any_combination",
    }


def _metric_values(overlap: float = 0.90) -> dict[str, float]:
    values: dict[str, float] = {
        "valid_overlap_fraction_raw": overlap,
        "common_valid_pixel_count": 90,
        "valid_pixel_count": 90,
        "pre_valid_pixel_count": 95,
        "post_valid_pixel_count": 94,
        "aoi_pixel_count": 100,
        "valid_overlap_area_m2": 36000,
        "rasterized_aoi_area_m2": 40000,
        "valid_aoi_area_m2": 40000,
        "pre_nbr_mean": 0.4,
        "pre_nbr_median": 0.4,
        "post_nbr_mean": 0.1,
        "post_nbr_median": 0.1,
        "dnbr_mean": 0.3,
        "dnbr_median": 0.3,
        "dnbr_p10": 0.1,
        "dnbr_p25": 0.2,
        "dnbr_p75": 0.4,
        "dnbr_p90": 0.5,
        "dnbr_p95": 0.6,
        "dnbr_min": -0.1,
        "dnbr_max": 0.8,
    }
    for code, fraction, area in (
        ("010", 0.70, 2.8),
        ("020", 0.60, 2.4),
        ("030", 0.50, 2.0),
        ("040", 0.40, 1.6),
    ):
        values[f"fraction_dnbr_gt_{code}"] = fraction
        values[f"area_ha_dnbr_gt_{code}"] = area
    return values


class _FakeSupportImage:
    def __init__(
        self,
        *,
        value: object = None,
        grid: tuple[str, int] | None = None,
        geometry: object = None,
        source: "_FakeSupportImage | None" = None,
        mask: object = None,
        operations: tuple[str, ...] = (),
    ) -> None:
        self.value = value
        self.grid = grid
        self.geometry = geometry
        self.source = source
        self.mask = mask
        self.operations = operations

    def _copy(self, **updates: object) -> "_FakeSupportImage":
        state = {
            "value": self.value,
            "grid": self.grid,
            "geometry": self.geometry,
            "source": self.source,
            "mask": self.mask,
            "operations": self.operations,
        }
        state.update(updates)
        return _FakeSupportImage(**state)

    def rename(self, name: str) -> "_FakeSupportImage":
        return self._copy(operations=self.operations + (f"rename:{name}",))

    def reproject(self, *, crs: tuple[str, str], scale: int) -> "_FakeSupportImage":
        return self._copy(grid=(crs[1], scale), operations=self.operations + ("reproject",))

    def clip(self, geometry: object) -> "_FakeSupportImage":
        return self._copy(geometry=geometry, operations=self.operations + ("clip",))

    def selfMask(self) -> "_FakeSupportImage":
        return self._copy(operations=self.operations + ("selfMask",))

    def updateMask(self, mask: object) -> "_FakeSupportImage":
        return self._copy(source=self, mask=mask, operations=self.operations + ("updateMask",))


class _FakeSupportImageNamespace:
    @staticmethod
    def constant(value: object) -> _FakeSupportImage:
        return _FakeSupportImage(value=value)

    @staticmethod
    def pixelArea() -> _FakeSupportImage:
        return _FakeSupportImage(value="pixelArea")


class _FakeSupportEe:
    Image = _FakeSupportImageNamespace

    @staticmethod
    def Projection(crs: str) -> tuple[str, str]:
        return ("projection", crs)


def test_formulas_and_threshold_contract_are_explicit():
    assert NBR_FORMULA == "(B8 - B12) / (B8 + B12)"
    assert DNBR_FORMULA == "NBR_pre - NBR_post"
    assert nbr_value(0.6, 0.2) == pytest.approx(0.5)
    assert dnbr_value(0.5, 0.2) == pytest.approx(0.3)
    with pytest.raises(DnbrValidationError):
        nbr_value(1.0, -1.0)
    assert CLOUD_THRESHOLDS == (0.50, 0.60, 0.65)
    assert PRIMARY_CLOUD_THRESHOLD == 0.50
    assert ANALYSIS_MODES == ("selected_pair", "window_median")
    assert AOI_ID == "b0500"


def test_overlap_fraction_one_is_valid_without_clipping():
    result = normalize_overlap_fraction(1.0, aoi_area_m2=1_000_000.0)
    assert result.raw == 1.0
    assert result.value == 1.0
    assert result.was_clipped is False


def test_overlap_fraction_minimal_float_excess_is_normalized_and_raw_is_preserved():
    raw = 1.0 + 0.5e-9
    result = normalize_overlap_fraction(raw, aoi_area_m2=1_629_496.923461914)
    assert result.raw == raw
    assert result.value == 1.0
    assert result.was_clipped is True
    assert raw - 1 < result.tolerance


def test_overlap_fraction_small_negative_is_normalized_to_zero():
    result = normalize_overlap_fraction(-0.5e-9, aoi_area_m2=1_000_000.0)
    assert result.raw == pytest.approx(-0.5e-9)
    assert result.value == 0.0
    assert result.was_clipped is True


def test_overlap_fraction_excess_above_tolerance_is_rejected():
    with pytest.raises(DnbrValidationError, match="Fracción de solapamiento"):
        normalize_overlap_fraction(1.000401, aoi_area_m2=1_000_000.0)


def test_overlap_fraction_negative_below_tolerance_is_rejected():
    with pytest.raises(DnbrValidationError, match="Fracción de solapamiento"):
        normalize_overlap_fraction(-0.000401, aoi_area_m2=1_000_000.0)


def test_overlap_fraction_tolerance_depends_on_area_and_analysis_scale():
    area = 1_000_000.0
    assert overlap_fraction_tolerance(area) == pytest.approx(1e-9)
    assert overlap_fraction_tolerance(area, analysis_scale_m=40) == pytest.approx(1e-9)
    assert overlap_fraction_tolerance(2_000_000.0) == pytest.approx(1e-9)


def test_raster_support_contract_uses_one_grid_for_counts_and_areas():
    aoi = type("Aoi", (), {"geometry_wgs84": "aoi-geometry"})()
    fake_ee = _FakeSupportEe()
    support = _analysis_aoi_support(aoi, fake_ee)
    common = _masked_analysis_support(
        support,
        "pre-valid-and-post-valid",
        band_name="common_valid_support",
    )
    pixel_area = _analysis_pixel_area(fake_ee)

    assert OVERLAP_SUPPORT_CONTRACT == {
        "geometry": "aoi.geometry_wgs84",
        "crs": "EPSG:32617",
        "scale_m": 20,
        "reducer": "sum",
        "support_band": "aoi_support",
        "common_support_band": "common_valid_support",
        "pixel_area_band": "pixel_area",
        "pixel_area_reducer": "sum",
        "common_mask": "pre_valid AND post_valid",
    }
    assert support.grid == ("EPSG:32617", ANALYSIS_SCALE_M)
    assert common.grid == support.grid == pixel_area.grid
    assert support.geometry == "aoi-geometry"
    assert common.source is support
    assert "reproject" in support.operations
    assert "clip" in support.operations
    assert "selfMask" in support.operations


@pytest.mark.parametrize("overlap", [0.0, 0.5, 1.0])
def test_metric_row_accepts_exact_zero_one_and_partial_support(overlap: float):
    values = _metric_values(overlap)
    count = int(overlap * 100)
    area = int(overlap * 40000)
    values.update(
        {
            "common_valid_pixel_count": count,
            "valid_pixel_count": count,
            "valid_overlap_area_m2": area,
            "rasterized_aoi_area_m2": 40000,
            "valid_aoi_area_m2": 40000,
        }
    )
    for code, fraction in (("010", 0.70), ("020", 0.60), ("030", 0.50), ("040", 0.40)):
        values[f"area_ha_dnbr_gt_{code}"] = (area / 10000) * fraction
    row = _metric_row(
        _event_input(),
        analysis_mode="selected_pair",
        cloud_threshold=0.50,
        values=values,
        processing_timestamp_utc="2025-12-31T00:00:00Z",
        min_valid_overlap_fraction=0.50,
    )
    assert row["valid_overlap_fraction_raw"] == overlap
    assert row["valid_overlap_fraction"] == overlap
    assert row["common_valid_pixel_count"] == count
    assert row["aoi_pixel_count"] == 100


def test_common_valid_support_cannot_exceed_aoi_support():
    values = _metric_values(1.0)
    values.update(
        {
            "common_valid_pixel_count": 101,
            "valid_pixel_count": 101,
            "aoi_pixel_count": 100,
        }
    )
    with pytest.raises(DnbrValidationError, match="soporte válido supera"):
        _metric_row(
            _event_input(),
            analysis_mode="selected_pair",
            cloud_threshold=0.50,
            values=values,
            processing_timestamp_utc="2025-12-31T00:00:00Z",
            min_valid_overlap_fraction=0.50,
        )


def test_overlap_excess_not_explained_by_float_tolerance_is_rejected():
    with pytest.raises(DnbrValidationError, match="Fracción de solapamiento"):
        normalize_overlap_fraction(1.0059215887483783, aoi_area_m2=1_000_000.0)


def test_quicklook_ranges_are_fixed_and_invalid_pixels_have_explicit_palette():
    assert (NBR_VIS_MIN, NBR_VIS_MAX) == (-1.0, 1.0)
    assert (DNBR_VIS_MIN, DNBR_VIS_MAX) == (-1.0, 1.0)
    assert DNBR_VIS_MIN < 0 < DNBR_VIS_MAX
    assert _thumb_parameters(None, kind="nbr")["min"] == NBR_VIS_MIN
    assert _thumb_parameters(None, kind="nbr")["max"] == NBR_VIS_MAX
    assert _thumb_parameters(None, kind="dnbr")["min"] == DNBR_VIS_MIN
    assert _thumb_parameters(None, kind="dnbr")["max"] == DNBR_VIS_MAX
    assert _thumb_parameters(None, kind="nbr")["palette"] == list(VISUALIZATION_PALETTE)
    assert _thumb_parameters(None, kind="mask")["palette"] == ["c026d3", "0f766e"]


def test_quicklook_panel_png_is_self_contained_and_embeds_metadata():
    def patterned_png(seed: int) -> bytes:
        image = RGBImage.solid(6, 6, (0, 0, 0))
        for y in range(6):
            for x in range(6):
                image.set_pixel(
                    x,
                    y,
                    ((x * 31 + seed) % 256, (y * 37 + seed * 3) % 256, (x * y + seed * 7) % 256),
                )
        return encode_png(image)

    thumbnails = {
        key: patterned_png(index + 1)
        for index, key in enumerate(PANEL_KEYS)
    }
    payload = compose_panel_png(
        thumbnails,
        {
            "event_id": "event-r1500_t06-test",
            "analysis_mode": "selected_pair",
            "cloud_threshold": 0.5,
            "valid_overlap_fraction": 1.0,
            "pre_timestamp_utc": "2024-12-20T12:00:00Z",
            "post_timestamp_utc": "2025-01-20T12:00:00Z",
            "nbr_range": [NBR_VIS_MIN, NBR_VIS_MAX],
            "dnbr_range": [DNBR_VIS_MIN, DNBR_VIS_MAX],
        },
    )
    decoded = decode_png(payload)
    assert payload.startswith(b"\x89PNG")
    assert (decoded.width, decoded.height) == (PANEL_WIDTH, PANEL_HEIGHT)
    assert b"event-r1500_t06-test" in payload
    assert b"<image" not in payload
    assert b"external" not in payload


def test_selected_pair_and_window_median_quicklook_paths_are_separate():
    path = panel_filename("event-r1500_t06-test", "selected_pair", 0.50)
    assert path == "event-r1500_t06-test_selected_pair_cs050_panel.png"
    assert quicklook_path_for_mode(path, "selected_pair") == path
    assert quicklook_path_for_mode(path, "window_median") == ""


def test_metric_row_exposes_raw_operational_tolerance_and_clip_flag():
    raw = 1.0 + 0.5e-9
    values = _metric_values(raw)
    values["common_valid_pixel_count"] = 100
    values["valid_pixel_count"] = 100
    values["valid_overlap_area_m2"] = 40000
    values["rasterized_aoi_area_m2"] = 40000
    values["valid_aoi_area_m2"] = 40000
    row = _metric_row(
        _event_input(),
        analysis_mode="selected_pair",
        cloud_threshold=0.50,
        values=values,
        processing_timestamp_utc="2025-12-31T00:00:00Z",
        min_valid_overlap_fraction=0.50,
    )
    assert row["valid_overlap_area_m2"] == 40000
    assert row["aoi_area_m2"] == 1000.0
    assert row["valid_overlap_fraction_raw"] == raw
    assert row["valid_overlap_fraction"] == 1.0
    assert row["overlap_fraction_tolerance"] == pytest.approx(1e-9)
    assert row["overlap_fraction_was_clipped"] is True
    assert {
        "valid_overlap_area_m2",
        "aoi_area_m2",
        "valid_overlap_fraction_raw",
        "valid_overlap_fraction",
        "overlap_fraction_tolerance",
        "overlap_fraction_was_clipped",
    }.issubset(METRICS_COLUMNS)


def test_overlap_normalization_does_not_change_nbr_or_dnbr_formulas():
    normalize_overlap_fraction(1.0 + 0.5e-9, aoi_area_m2=1_000_000.0)
    assert nbr_value(0.6, 0.2) == pytest.approx(0.5)
    assert dnbr_value(0.5, 0.2) == pytest.approx(0.3)


def test_report_counts_rows_normalized_by_overlap_tolerance():
    event_input = _event_input()
    inputs = DnbrInputs(
        events=(event_input.event,),
        processable=(event_input,),
        excluded=(),
        scene_rows=(),
        aoi_rows=(),
    )
    report = build_report(
        inputs,
        requested_event_ids=(event_input.event_id,),
        completed_event_ids=(event_input.event_id,),
        failed_event_ids=(),
        metrics_rows=[
            {"event_id": event_input.event_id, "overlap_fraction_was_clipped": True}
        ],
        sensitivity_rows=[
            {"event_id": event_input.event_id, "overlap_fraction_was_clipped": "false"}
        ],
        errors=(),
        min_valid_overlap_fraction=0.50,
        earth_engine_queries_made=False,
    )
    assert report["overlap_fraction_clipped_row_count"] == 1
    assert report["overlap_fraction_clipped_sensitivity_row_count"] == 0
    assert report["overlap_fraction_clipped_total_row_count"] == 1


def test_selection_metadata_preserves_28_processable_and_2_excluded():
    rows = [
        _selection_row(f"event-r1500_t06-{index:02d}", usable=index < 28)
        for index in range(30)
    ]
    processable, excluded = _validate_selection_metadata(rows)
    assert len(processable) == EXPECTED_PROCESSABLE_EVENT_COUNT
    assert len(excluded) == EXPECTED_EXCLUDED_EVENT_COUNT


def test_selection_metadata_rejects_incompatible_configuration():
    rows = [
        _selection_row(f"event-r1500_t06-{index:02d}", usable=index < 28)
        for index in range(30)
    ]
    rows[0]["configuration_id"] = "other"
    with pytest.raises(DnbrValidationError, match="configuración"):
        _validate_selection_metadata(rows)


def test_metric_row_with_insufficient_overlap_does_not_publish_dnbr_metrics():
    values = _metric_values(0.49)
    values.update(
        {
            "common_valid_pixel_count": 49,
            "valid_pixel_count": 49,
            "valid_overlap_area_m2": 19600,
            "rasterized_aoi_area_m2": 40000,
            "valid_aoi_area_m2": 40000,
        }
    )
    row = _metric_row(
        _event_input(),
        analysis_mode="selected_pair",
        cloud_threshold=0.50,
        values=values,
        processing_timestamp_utc="2025-12-31T00:00:00Z",
        min_valid_overlap_fraction=0.50,
    )
    assert row["metric_status"] == "insufficient_valid_overlap"
    assert row["valid_overlap_fraction"] == pytest.approx(0.49)
    assert row["dnbr_median"] == ""
    assert row["fraction_dnbr_gt_020"] == ""


def test_metric_row_validates_percentiles_fractions_and_area():
    row = _metric_row(
        _event_input(),
        analysis_mode="window_median",
        cloud_threshold=0.60,
        values=_metric_values(),
        processing_timestamp_utc="2025-12-31T00:00:00Z",
        min_valid_overlap_fraction=0.50,
    )
    assert row["metric_status"] == "usable_overlap"
    assert percentile_order_is_valid(row)
    assert row["analysis_mode"] == "window_median"
    assert row["cloud_threshold"] == 0.60
    assert row["pre_scene_count_used"] == 1


def test_percentile_order_rejects_inconsistent_row():
    values = _metric_values()
    values["dnbr_p90"] = 0.15
    with pytest.raises(DnbrValidationError, match="Percentiles"):
        _metric_row(
            _event_input(),
            analysis_mode="selected_pair",
            cloud_threshold=0.50,
            values=values,
            processing_timestamp_utc="2025-12-31T00:00:00Z",
            min_valid_overlap_fraction=0.50,
        )


def test_merge_replaces_only_selected_event():
    existing = [
        {"event_id": "event-a", "dnbr_median": "0.1"},
        {"event_id": "event-b", "dnbr_median": "0.2"},
    ]
    replacement = [{"event_id": "event-a", "dnbr_median": "0.9"}]
    merged = merge_event_rows(existing, replacement, {"event-a"})
    assert merged == [
        {"event_id": "event-b", "dnbr_median": "0.2"},
        {"event_id": "event-a", "dnbr_median": "0.9"},
    ]


def test_cache_roundtrip_is_utf8_and_requires_matching_signature(tmp_path):
    cache = tmp_path / "cache" / "event.json"
    signature = {"pipeline_version": DNBR_PIPELINE_VERSION, "event_id": "evento-á"}
    result = {
        "event_id": "evento-á",
        "metrics_rows": [{"event_id": "evento-á", "note": "métrica válida"}],
        "sensitivity_rows": [],
        "quicklook_path": "",
    }
    write_event_cache(cache, signature, result)
    assert load_event_cache(cache, signature) == result
    assert load_event_cache(cache, {"pipeline_version": "other"}) is None
    assert "métrica" in cache.read_text(encoding="utf-8")
    assert cache_signature(_event_input(), 0.50)["overlap_support_contract"] == dict(
        OVERLAP_SUPPORT_CONTRACT
    )


def test_v2_rows_and_checkpoint_are_not_reused_by_v3_contract(tmp_path):
    runner = _runner_module()
    assert runner._current_contract_rows(
        [
            {"event_id": "old", "pipeline_version": "fuegopa-sentinel2-dnbr-v2"},
            {"event_id": "current", "pipeline_version": DNBR_PIPELINE_VERSION},
        ]
    ) == [{"event_id": "current", "pipeline_version": DNBR_PIPELINE_VERSION}]
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "pipeline_version": "fuegopa-sentinel2-dnbr-v2",
                "completed_event_ids": ["old"],
                "failed_event_ids": [],
            }
        ),
        encoding="utf-8",
    )
    assert runner._load_checkpoint(checkpoint) == (set(), set())


def test_resume_uses_success_cache_but_retries_failed_and_overwrite_bypasses(tmp_path):
    runner = _runner_module()
    event_input = _event_input()
    quicklook = tmp_path / "quicklook.svg"
    quicklook.write_text("<svg/>", encoding="utf-8")
    signature = cache_signature(event_input, 0.50)
    result = {
        "event_id": event_input.event_id,
        "metrics_rows": [],
        "sensitivity_rows": [],
        "quicklook_path": str(quicklook),
    }
    cache = cache_path(tmp_path / "cache", event_input.event_id)
    write_event_cache(cache, signature, result)
    assert runner._load_resume_cache(
        event_input,
        cache_dir=tmp_path / "cache",
        resume=True,
        overwrite=False,
        min_valid_overlap_fraction=0.50,
    ) == result
    assert runner._load_resume_cache(
        event_input,
        cache_dir=tmp_path / "cache",
        resume=True,
        overwrite=True,
        min_valid_overlap_fraction=0.50,
    ) is None
    assert runner._load_resume_cache(
        event_input,
        cache_dir=tmp_path / "failed-cache",
        resume=True,
        overwrite=False,
        min_valid_overlap_fraction=0.50,
    ) is None


def test_event_id_selection_limits_execution_scope():
    runner = _runner_module()
    first = _event_input()
    second = DnbrEventInput(
        event=EventInput(
            event_id="event-r1500_t06-second",
            configuration_id=first.event.configuration_id,
            start_timestamp_utc=first.event.start_timestamp_utc,
            end_timestamp_utc=first.event.end_timestamp_utc,
            detection_count=first.event.detection_count,
            source_count=first.event.source_count,
            sources=first.event.sources,
            possible_chain_merge=first.event.possible_chain_merge,
            month=first.event.month,
            event_size_class=first.event.event_size_class,
            source_class=first.event.source_class,
            chain_class=first.event.chain_class,
            detections=first.event.detections,
        ),
        selection=first.selection,
        aoi_area_m2=first.aoi_area_m2,
        pre_scene=first.pre_scene,
        post_scene=first.post_scene,
        pre_candidates=first.pre_candidates,
        post_candidates=first.post_candidates,
    )
    assert runner._select_events(
        [first, second],
        event_id=first.event_id,
        max_events=None,
    ) == [first]


def test_checkpoint_is_atomic_and_failed_event_can_be_replaced(tmp_path):
    runner = _runner_module()
    checkpoint = tmp_path / "checkpoint.json"
    completed, failed = runner._write_checkpoint(
        checkpoint,
        selected_event_ids={"event-a"},
        completed_event_ids=set(),
        failed_event_ids={"event-a"},
    )
    assert completed == set()
    assert failed == {"event-a"}
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["failed_event_ids"] == ["event-a"]
    completed, failed = runner._write_checkpoint(
        checkpoint,
        selected_event_ids={"event-a"},
        completed_event_ids={"event-a"},
        failed_event_ids=set(),
    )
    assert completed == {"event-a"}
    assert failed == set()
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["completed_event_ids"] == ["event-a"]
    assert not checkpoint.with_suffix(".json.tmp").exists()


def test_review_queue_has_28_blank_human_fields_contract():
    rows = [_event_input()]
    metrics = [
        {
            "event_id": rows[0].event_id,
            "analysis_mode": "selected_pair",
            "cloud_threshold": "0.5",
            "metric_status": "usable_overlap",
            "valid_overlap_fraction": "0.9",
            "quicklook_path": "outputs/figures/sentinel2_dnbr/events/test.svg",
        }
    ]
    queue = build_review_queue(rows, metrics)
    assert set(REVIEW_QUEUE_COLUMNS).issubset(queue[0])
    assert queue[0]["visible_burn_scar"] == ""
    assert queue[0]["scar_confidence"] == ""
    assert queue[0]["competing_land_change"] == ""
    assert queue[0]["reviewer_notes"] == ""
    assert queue[0]["review_status"] == ""
    assert "significant_burn" not in METRICS_COLUMNS


def test_retry_preserves_original_cause_and_retries_without_network():
    module = _runner_module()
    calls: list[tuple[int, int]] = []

    def resolver(attempt: int, retry_count: int):
        calls.append((attempt, retry_count))
        raise ValueError("causa original completa")

    with pytest.raises(EarthEngineQueryError) as caught:
        module._safe_error  # keep runner import explicit for this test module
        from fuegopa.sentinel2_dnbr import _resolve_with_retries

        _resolve_with_retries(
            resolver,
            operation="operación de prueba",
            error_stage="test",
            event_id="event-test",
            aoi_id="b0500",
            window_id="b0500_pre30_post45",
            retry_count=2,
            backoff_seconds=0,
        )
    assert calls == [(1, 0), (2, 1), (3, 2)]
    assert isinstance(caught.value.__cause__, ValueError)
    assert "causa original completa" in str(caught.value.__cause__)
    assert caught.value.attempt == 3
    assert caught.value.retry_count == 2
