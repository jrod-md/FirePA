from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fuegopa.earth_engine import (
    CLOUD_SCORE_PLUS_COLLECTION,
    EarthEngineQueryError,
    SENTINEL2_SR_COLLECTION,
    EarthEngineConfigurationError,
    EarthEngineClient,
    exception_diagnostics,
    initialize_earth_engine,
    smoke_test,
)
from fuegopa.sentinel2_observability import (
    AOI_METHOD,
    AOI_COLUMNS,
    BUFFER_OPTIONS,
    CALCULATION_CRS,
    ERROR_COLUMNS,
    OBSERVABILITY_COLUMNS,
    PIPELINE_VERSION,
    PROJECTED_ERROR_MARGIN_UNIT,
    TRANSFORM_ERROR_MARGIN_UNIT,
    USABILITY_RULES,
    ObservabilityValidationError,
    SCENE_COLUMNS,
    DetectionInput,
    EventInput,
    build_report,
    build_aoi,
    build_window_specs,
    build_sensitivity_rows,
    cache_signature,
    cache_path,
    evaluate_event_result,
    load_event_cache,
    load_pilot_events,
    make_combination_id,
    normalize_aoi_id,
    parse_utc_timestamp,
    rank_scenes,
    rebuild_observability_from_inventory,
    scene_is_usable,
    validate_observability_invariants,
    write_csv,
    write_event_cache,
    write_json,
    write_report_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "processed" / "sentinel2_observability_pilot_events.csv"
MEMBERSHIP = ROOT / "data" / "processed" / "firms_cocle_2025_event_membership.csv"
EVENTS = ROOT / "data" / "processed" / "firms_cocle_2025_events_provisional.csv"


def _runner_module():
    path = ROOT / "scripts" / "run_sentinel2_observability.py"
    spec = importlib.util.spec_from_file_location("fuegopa_observability_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(multi: bool = False) -> EventInput:
    detections = [
        DetectionInput("det-1", datetime(2025, 1, 10, 12, tzinfo=timezone.utc), 8.4, -80.2)
    ]
    if multi:
        detections.append(DetectionInput("det-2", datetime(2025, 1, 10, 12, 30, tzinfo=timezone.utc), 8.41, -80.21))
    return EventInput(
        event_id="event-r1500_t06-test",
        configuration_id="r1500_t06",
        start_timestamp_utc=datetime(2025, 1, 10, 12, tzinfo=timezone.utc),
        end_timestamp_utc=datetime(2025, 1, 10, 13, tzinfo=timezone.utc),
        detection_count=len(detections),
        source_count=1,
        sources="[\"VIIRS\"]",
        possible_chain_merge=False,
        month="2025-01",
        event_size_class="multi_detection" if multi else "singleton",
        source_class="single_source",
        chain_class="no_possible_chain_merge",
        detections=tuple(detections),
    )


def _scene(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "event_id": _event().event_id,
        "aoi_id": "b0500",
        "aoi_buffer_m": 500,
        "window_id": "pre30",
        "period_role": "pre",
        "combination_id": "b0500_pre30_post45",
        "sentinel2_scene_id": "scene-1",
        "system_index": "scene-1",
        "acquisition_timestamp_utc": "2024-12-20T12:00:00Z",
        "cloud_score_linked": True,
        "data_coverage_fraction": 0.95,
        "clear_fraction_cs_cdf_050": 0.80,
        "clear_fraction_cs_cdf_060": 0.75,
        "clear_fraction_cs_cdf_065": 0.70,
        "valid_pixel_count": 100,
        "cloud_score_pixel_count": 100,
    }
    row.update(overrides)
    return row


def _inventory_scene(
    event: EventInput,
    *,
    aoi_id: object,
    buffer_m: object,
    period_role: str,
    window_id: str,
    combination_id: str,
    scene_id: str,
    acquisition_timestamp_utc: str,
    **overrides: object,
) -> dict[str, object]:
    row: dict[str, object] = {column: "" for column in SCENE_COLUMNS}
    row.update(
        {
            "event_id": event.event_id,
            "configuration_id": "r1500_t06",
            "aoi_id": aoi_id,
            "aoi_buffer_m": buffer_m,
            "aoi_area_m2": 1000,
            "aoi_area_km2": 0.001,
            "geometry_hash": "fixture-hash",
            "member_detection_count": event.detection_count,
            "geometry_valid": "True",
            "period_role": period_role,
            "window_id": window_id,
            "window_start_utc": "2025-01-01T00:00:00Z",
            "window_end_utc": "2025-01-02T00:00:00Z",
            "combination_id": combination_id,
            "sentinel2_scene_id": scene_id,
            "system_index": scene_id,
            "acquisition_timestamp_utc": acquisition_timestamp_utc,
            "cloud_score_linked": "1",
            "data_coverage_fraction": 0.98,
            "clear_fraction_cs_cdf_050": 0.90,
            "clear_fraction_cs_cdf_060": 0.90,
            "clear_fraction_cs_cdf_065": 0.90,
            "valid_pixel_count": 100,
            "cloud_score_pixel_count": 100,
            "query_timestamp_utc": "2025-12-31T00:00:00Z",
            "pipeline_version": "fuegopa-sentinel2-observability-v1",
        }
    )
    row.update(overrides)
    return row


def _inventory_aoi(event: EventInput, *, aoi_id: object, buffer_m: object) -> dict[str, object]:
    row: dict[str, object] = {column: "" for column in AOI_COLUMNS}
    row.update(
        {
            "event_id": event.event_id,
            "configuration_id": "r1500_t06",
            "aoi_id": aoi_id,
            "aoi_method": "detection_union_buffer",
            "buffer_m": buffer_m,
            "aoi_area_m2": 1000,
            "aoi_area_km2": 0.001,
            "geometry_hash": "fixture-hash",
            "member_detection_count": event.detection_count,
            "geometry_valid": "True",
            "pipeline_version": "fuegopa-sentinel2-observability-v1",
        }
    )
    return row


def _fixture_inventory() -> tuple[EventInput, list[dict[str, object]], list[dict[str, object]]]:
    event = _event()
    scene_rows: list[dict[str, object]] = []
    aoi_rows: list[dict[str, object]] = []
    aoi_specs = ((500, 500), ("B1000", "1000"), (1500, 1500))
    for aoi_alias, buffer_value in aoi_specs:
        aoi_rows.append(_inventory_aoi(event, aoi_id=aoi_alias, buffer_m=buffer_value))
        normalized_aoi = normalize_aoi_id(aoi_alias, buffer_value)
        combo_3045 = f"{aoi_alias}_PRE30_POST45"
        combo_3090 = f"{aoi_alias}_PRE30_POST90"
        combo_6045 = f"{aoi_alias}_PRE60_POST45"
        combo_6090 = f"{aoi_alias}_PRE60_POST90"
        scene_rows.extend(
            [
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="PRE",
                    window_id="PRE30",
                    combination_id=combo_3045,
                    scene_id=f"{normalized_aoi}-pre30-a",
                    acquisition_timestamp_utc="2024-12-20T12:00:00Z",
                    data_coverage_fraction=0.96,
                    clear_fraction_cs_cdf_050=0.80,
                    clear_fraction_cs_cdf_060=0.80,
                    clear_fraction_cs_cdf_065=0.80,
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="PRE",
                    window_id="PRE30",
                    combination_id=combo_3045,
                    scene_id=f"{normalized_aoi}-pre30-b",
                    acquisition_timestamp_utc="2024-12-25T12:00:00Z",
                    data_coverage_fraction=0.99,
                    clear_fraction_cs_cdf_050=0.75,
                    clear_fraction_cs_cdf_060=0.75,
                    clear_fraction_cs_cdf_065=0.75,
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="PRE",
                    window_id="PRE30",
                    combination_id=combo_3090,
                    scene_id=f"{normalized_aoi}-pre30-a",
                    acquisition_timestamp_utc="2024-12-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="PRE",
                    window_id="PRE60",
                    combination_id=combo_6045,
                    scene_id=f"{normalized_aoi}-pre60",
                    acquisition_timestamp_utc="2024-11-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="PRE",
                    window_id="PRE60",
                    combination_id=combo_6090,
                    scene_id=f"{normalized_aoi}-pre60",
                    acquisition_timestamp_utc="2024-11-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="POST",
                    window_id="POST45",
                    combination_id=combo_3045,
                    scene_id=f"{normalized_aoi}-post45",
                    acquisition_timestamp_utc="2025-01-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="POST",
                    window_id="POST45",
                    combination_id=combo_6045,
                    scene_id=f"{normalized_aoi}-post45",
                    acquisition_timestamp_utc="2025-01-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="POST",
                    window_id="POST90",
                    combination_id=combo_3090,
                    scene_id=f"{normalized_aoi}-post90",
                    acquisition_timestamp_utc="2025-02-20T12:00:00Z",
                ),
                _inventory_scene(
                    event,
                    aoi_id=aoi_alias,
                    buffer_m=buffer_value,
                    period_role="POST",
                    window_id="POST90",
                    combination_id=combo_6090,
                    scene_id=f"{normalized_aoi}-post90",
                    acquisition_timestamp_utc="2025-02-20T12:00:00Z",
                ),
            ]
        )
    return event, scene_rows, aoi_rows


class _FakeNumber:
    def __init__(self, value: int):
        self.value = value

    def getInfo(self) -> int:
        return self.value


class _FakeCollection:
    def limit(self, _value: int) -> "_FakeCollection":
        return self

    def size(self) -> _FakeNumber:
        return _FakeNumber(1)


class _FakeErrorMargin:
    def __init__(self, value: float, unit: str = "meters") -> None:
        self.value = value
        self.unit = unit

    def serialize(self) -> dict[str, object]:
        return {"value": self.value, "unit": self.unit}


class _FakeProjection:
    def __init__(self, crs: str) -> None:
        self.crs = crs

    def serialize(self) -> str:
        return self.crs


class _FakeServerGeometry:
    def __init__(self, calls: list[dict[str, object]], operation: str, payload: object) -> None:
        self.calls = calls
        self.operation = operation
        self.payload = payload

    def buffer(self, distance: int, *, maxError: _FakeErrorMargin, proj: _FakeProjection) -> "_FakeServerGeometry":
        self.calls.append({"operation": "buffer", "distance": distance, "maxError": maxError, "proj": proj})
        return _FakeServerGeometry(self.calls, "buffer", {"source": self.payload, "distance": distance})

    def union(self, right: "_FakeServerGeometry", *, maxError: _FakeErrorMargin, proj: _FakeProjection) -> "_FakeServerGeometry":
        self.calls.append({"operation": "union", "maxError": maxError, "proj": proj})
        return _FakeServerGeometry(self.calls, "union", {"left": self.payload, "right": right.payload})

    def transform(self, proj: str, *, maxError: _FakeErrorMargin) -> "_FakeServerGeometry":
        self.calls.append({"operation": "transform", "maxError": maxError, "proj": proj})
        return _FakeServerGeometry(self.calls, "transform", {"source": self.payload, "proj": proj})

    def area(self, *, maxError: _FakeErrorMargin, proj: _FakeProjection) -> _FakeNumber:
        self.calls.append({"operation": "area", "maxError": maxError, "proj": proj})
        return _FakeNumber(1000)

    def serialize(self) -> dict[str, object]:
        def serialize_value(value: object) -> object:
            if isinstance(value, _FakeServerGeometry):
                return value.serialize()
            if isinstance(value, (_FakeErrorMargin, _FakeProjection)):
                return value.serialize()
            if isinstance(value, dict):
                return {key: serialize_value(item) for key, item in value.items()}
            if isinstance(value, list):
                return [serialize_value(item) for item in value]
            return value

        return {"operation": self.operation, "payload": serialize_value(self.payload)}


class _FakeGeometryNamespace:
    def __init__(self, calls: list[dict[str, object]]) -> None:
        self.calls = calls

    def Point(self, coords: list[float], *, proj: _FakeProjection) -> _FakeServerGeometry:
        return _FakeServerGeometry(self.calls, "point", {"coords": coords, "proj": proj})


class _FakeEE:
    def __init__(self) -> None:
        self.initialized_with: str | None = None
        self.geometry_calls: list[dict[str, object]] = []
        self.Geometry = _FakeGeometryNamespace(self.geometry_calls)

    def Initialize(self, *, project: str) -> None:
        self.initialized_with = project

    def ImageCollection(self, _collection_id: str) -> _FakeCollection:
        return _FakeCollection()

    def Projection(self, crs: str) -> _FakeProjection:
        return _FakeProjection(crs)

    def ErrorMargin(self, value: float, unit: str = "meters") -> _FakeErrorMargin:
        return _FakeErrorMargin(value, unit)


def test_missing_project_fails_without_authentication() -> None:
    fake = _FakeEE()
    with pytest.raises(EarthEngineConfigurationError, match="EARTH_ENGINE_PROJECT"):
        initialize_earth_engine(environ={}, ee_module=fake)
    assert fake.initialized_with is None


def test_initialization_reads_project_and_never_authenticates() -> None:
    fake = _FakeEE()
    client = initialize_earth_engine(environ={"EARTH_ENGINE_PROJECT": "test-project"}, ee_module=fake)
    assert isinstance(client, EarthEngineClient)
    assert client.project == "test-project"
    assert fake.initialized_with == "test-project"
    assert not hasattr(fake, "Authenticate")


def test_smoke_test_checks_both_collections_without_scientific_outputs() -> None:
    fake = _FakeEE()
    client = initialize_earth_engine(environ={"EARTH_ENGINE_PROJECT": "test-project"}, ee_module=fake)
    result = smoke_test(client)
    assert result["earth_engine_initialized"] is True
    assert result["scientific_results_written"] is False
    assert result["project_id_stored"] is False
    assert result["collections"][SENTINEL2_SR_COLLECTION]["accessible"] is True
    assert result["collections"][CLOUD_SCORE_PLUS_COLLECTION]["accessible"] is True


def test_get_info_preserves_original_exception_context_and_chain() -> None:
    class FailingServerObject:
        def getInfo(self) -> object:
            raise RuntimeError("original EE failure with full detail")

    client = EarthEngineClient(ee_module=object(), project="test-project")
    with pytest.raises(EarthEngineQueryError) as caught:
        client.get_info(
            FailingServerObject(),
            "inventario del evento event-r1500_t06-debug",
            event_id="event-r1500_t06-debug",
            attempt=3,
            retry_count=2,
            max_retries=2,
        )
    error = caught.value
    assert isinstance(error.__cause__, RuntimeError)
    assert error.cause_type == "RuntimeError"
    assert error.cause_message == "original EE failure with full detail"
    assert error.event_id == "event-r1500_t06-debug"
    assert error.attempt == 3
    assert error.retry_count == 2
    details = exception_diagnostics(error)
    assert details["cause_type"] == "RuntimeError"
    assert details["cause_message"] == "original EE failure with full detail"


def test_debug_error_record_redacts_project_secrets_and_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_module()
    monkeypatch.setenv("EARTH_ENGINE_PROJECT", "real-project")
    cause = RuntimeError(
        "project=real-project token=super-secret geometry={'coordinates': [[-80.2, 8.4]]}"
    )
    error = EarthEngineQueryError.from_exception(
        cause,
        operation="inventario del evento event-r1500_t06-debug",
        error_stage="get_info",
        event_id="event-r1500_t06-debug",
        aoi_id="b0500",
        window_id="pre30_post45",
        attempt=3,
        retry_count=2,
        max_retries=2,
    )
    record = runner._error_record(_event(), error, query_timestamp_utc="2025-01-01T00:00:00Z")
    serialized = json.dumps(record, ensure_ascii=False)
    assert "real-project" not in serialized
    assert "super-secret" not in serialized
    assert "-80.2" not in serialized
    assert record["cause_type"] == "RuntimeError"
    assert record["aoi_id"] == "b0500"
    assert record["window_id"] == "pre30_post45"
    assert record["attempt"] == 3
    assert record["retry_count"] == 2


def test_debug_requires_one_explicit_event() -> None:
    runner = _runner_module()
    assert runner.main(["--debug"]) == 2


def test_resume_skips_cached_event_and_retries_missing_failed_event(tmp_path: Path) -> None:
    runner = _runner_module()
    first = _event()
    second = EventInput(**{**first.__dict__, "event_id": "event-r1500_t06-second"})
    signature = cache_signature(first)
    first_path = cache_path(tmp_path, first.event_id)
    result = {"event_id": first.event_id, "event_hash": first.event_hash, "aoi_records": [], "scene_records": []}
    write_event_cache(first_path, signature, result)
    assert runner._load_cached_result(first, tmp_path, resume=True, overwrite=False) == result
    assert runner._load_cached_result(second, tmp_path, resume=True, overwrite=False) is None
    assert runner._load_cached_result(first, tmp_path, resume=True, overwrite=True) is None


def test_checkpoint_is_atomic_and_narrow_runs_preserve_other_events(tmp_path: Path) -> None:
    runner = _runner_module()
    checkpoint = tmp_path / "checkpoint.json"
    runner._checkpoint(checkpoint, ["event-a"], ["event-b"], replace_event_ids={"event-a", "event-b"})
    assert checkpoint.is_file()
    assert not checkpoint.with_suffix(".json.tmp").exists()
    runner._checkpoint(checkpoint, [], ["event-c"], replace_event_ids={"event-c"})
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["completed_event_ids"] == ["event-a"]
    assert payload["failed_event_ids"] == ["event-b", "event-c"]


def test_overwrite_replaces_only_selected_event_rows() -> None:
    runner = _runner_module()
    existing = [{"event_id": "event-a", "value": "old"}, {"event_id": "event-b", "value": "valid"}]
    replacement = [{"event_id": "event-a", "value": "new"}]
    merged = runner._replace_event_rows(existing, replacement, {"event-a"})
    assert merged == [{"event_id": "event-b", "value": "valid"}, {"event_id": "event-a", "value": "new"}]


def test_error_schema_and_outputs_are_explicit_utf8(tmp_path: Path) -> None:
    assert {"error_stage", "cause_type", "cause_message", "aoi_id", "window_id", "retry_count", "traceback_file"}.issubset(ERROR_COLUMNS)
    csv_path = tmp_path / "diagnóstico.csv"
    json_path = tmp_path / "diagnóstico.json"
    markdown_path = tmp_path / "diagnóstico.md"
    write_csv(csv_path, ["mensaje"], [{"mensaje": "validación mínima"}])
    write_json(json_path, {"mensaje": "índice válido"})
    report = {
        "pilot_universe_count": 1,
        "requested_event_count": 1,
        "events_processed": 0,
        "events_failed": 1,
        "events_with_at_least_one_pre_scene": 0,
        "events_with_at_least_one_post_scene": 0,
        "events_with_any_usable_pair": 0,
        "events_without_any_usable_pair": 1,
        "scenes_pre_found": 0,
        "scenes_post_found": 0,
        "cloud_score_missing_scene_count": 0,
        "rules": {
            rule_id: {"coverage_min": 0.9, "clear_field": "clear", "clear_min": 0.7, "events_with_usable_pair": 0}
            for rule_id in ("A", "B", "C", "D")
        },
        "errors": [],
    }
    write_report_markdown(markdown_path, report)
    assert "validación mínima" in csv_path.read_text(encoding="utf-8")
    assert "índice válido" in json_path.read_text(encoding="utf-8")
    assert "claridad" in markdown_path.read_text(encoding="utf-8")


def test_aoi_ids_hashes_and_singleton_geometry_contract() -> None:
    singleton = _event()
    aoi_500 = build_aoi(singleton, 500)
    assert aoi_500.aoi_id == "b0500"
    assert aoi_500.geometry_valid is True
    assert aoi_500.member_detection_count == 1
    assert aoi_500.geometry_hash == build_aoi(singleton, 500).geometry_hash
    assert aoi_500.geometry_hash != build_aoi(singleton, 1000).geometry_hash


def test_multi_detection_aoi_uses_all_members_and_allowed_buffers() -> None:
    event = _event(multi=True)
    assert [buffer_m for buffer_m, _ in BUFFER_OPTIONS] == [500, 1000, 1500]
    for buffer_m, aoi_id in BUFFER_OPTIONS:
        aoi = build_aoi(event, buffer_m)
        assert aoi.aoi_id == aoi_id
        assert aoi.member_detection_count == 2
        assert aoi.geometry_valid is True


def test_server_side_aoi_serializes_with_projected_error_margins_without_network() -> None:
    fake = _FakeEE()
    client = EarthEngineClient(ee_module=fake, project="test-project")

    for event in (_event(), _event(multi=True)):
        for buffer_m, _ in BUFFER_OPTIONS:
            fake.geometry_calls.clear()
            aoi = build_aoi(event, buffer_m, client)

            assert aoi.geometry_utm is not None
            assert aoi.geometry_wgs84 is not None
            json.dumps(aoi.geometry_utm.serialize(), sort_keys=True)
            json.dumps(aoi.geometry_wgs84.serialize(), sort_keys=True)

            buffer_calls = [call for call in fake.geometry_calls if call["operation"] == "buffer"]
            union_calls = [call for call in fake.geometry_calls if call["operation"] == "union"]
            transform_calls = [call for call in fake.geometry_calls if call["operation"] == "transform"]
            area_calls = [call for call in fake.geometry_calls if call["operation"] == "area"]

            assert len(buffer_calls) == len(event.detections)
            assert {call["distance"] for call in buffer_calls} == {buffer_m}
            assert all(call["proj"].crs == CALCULATION_CRS for call in buffer_calls)
            assert all(call["maxError"].unit == PROJECTED_ERROR_MARGIN_UNIT for call in buffer_calls)
            assert len(union_calls) == max(len(event.detections) - 1, 0)
            assert all(call["proj"].crs == CALCULATION_CRS for call in union_calls)
            assert all(call["maxError"].unit == PROJECTED_ERROR_MARGIN_UNIT for call in union_calls)
            assert len(area_calls) == 1
            assert area_calls[0]["proj"].crs == CALCULATION_CRS
            assert area_calls[0]["maxError"].unit == PROJECTED_ERROR_MARGIN_UNIT
            assert len(transform_calls) == 1
            assert transform_calls[0]["proj"] == "EPSG:4326"
            assert transform_calls[0]["maxError"].unit == TRANSFORM_ERROR_MARGIN_UNIT


def test_window_boundaries_are_inclusive_in_record_and_exclusive_plus_one_in_query() -> None:
    windows = build_window_specs(_event())
    pre, post = windows["pre30_post45"]
    assert pre.start_utc == datetime(2024, 12, 11, 12, tzinfo=timezone.utc)
    assert pre.end_utc == datetime(2025, 1, 5, 12, tzinfo=timezone.utc)
    assert post.start_utc == datetime(2025, 1, 15, 13, tzinfo=timezone.utc)
    assert post.end_utc == datetime(2025, 2, 24, 13, tzinfo=timezone.utc)
    assert post.query_end_utc == post.end_utc + timedelta(seconds=1)


def test_timestamp_parser_rejects_2026() -> None:
    with pytest.raises(ObservabilityValidationError, match="2026"):
        parse_utc_timestamp("2026-01-01T00:00:00Z")


def test_scene_coverage_and_clarity_metrics_drive_rules() -> None:
    scene = _scene()
    assert all(scene_is_usable(scene, rule_id) for rule_id in ("A", "B", "C"))
    assert scene_is_usable({**scene, "data_coverage_fraction": 0.89}, "A") is False
    assert scene_is_usable({**scene, "cloud_score_linked": False}, "A") is False
    assert scene_is_usable({**scene, "clear_fraction_cs_cdf_060": None}, "B") is False
    assert scene_is_usable({**scene, "data_coverage_fraction": 0.94, "clear_fraction_cs_cdf_060": 0.75}, "D") is False
    assert scene_is_usable({**scene, "data_coverage_fraction": 0.95, "clear_fraction_cs_cdf_060": 0.80}, "D") is True
    assert set(USABILITY_RULES) == {"A", "B", "C", "D"}


def test_ranking_prioritizes_coverage_then_clarity_then_time() -> None:
    event = _event()
    first = _scene(sentinel2_scene_id="coverage", data_coverage_fraction=0.98, clear_fraction_cs_cdf_050=0.71)
    second = _scene(sentinel2_scene_id="clarity", data_coverage_fraction=0.95, clear_fraction_cs_cdf_050=0.95)
    ranked = rank_scenes([second, first], event, "A")
    assert [row["sentinel2_scene_id"] for row in ranked] == ["coverage", "clarity"]


def test_evaluate_event_result_preserves_missing_cloud_score_and_rule_rows() -> None:
    event = _event()
    aoi_record = {
        "aoi_id": "b0500",
        "buffer_m": 500,
        "aoi_area_m2": 1000,
        "aoi_area_km2": 0.001,
        "geometry_hash": "hash",
        "member_detection_count": 1,
        "geometry_valid": True,
    }
    pre = _scene(period_role="pre", sentinel2_scene_id="pre-scene")
    post = _scene(period_role="post", window_id="post45", sentinel2_scene_id="post-scene", acquisition_timestamp_utc="2025-01-20T12:00:00Z")
    missing_score = _scene(period_role="pre", window_id="pre30", sentinel2_scene_id="missing-score", cloud_score_linked=False)
    result = {"query_timestamp_utc": "2026-07-19T00:00:00Z", "aoi_records": [aoi_record], "scene_records": [pre, post, missing_score]}
    aoi_rows, scene_rows, observation_rows = evaluate_event_result(event, result)
    assert len(aoi_rows) == 1
    assert len(scene_rows) == 3
    assert len(observation_rows) == 16
    rule_a = next(row for row in observation_rows if row["rule_id"] == "A")
    assert rule_a["pre_scene_count"] == 2
    assert rule_a["post_scene_count"] == 1
    assert rule_a["usable_pair_exists"] is True
    assert rule_a["selected_pre_scene_id"] == "pre-scene"
    assert all(row["cloud_score_linked"] is not None for row in scene_rows)


def test_rebuild_joins_component_windows_with_exact_combination_and_three_buffers() -> None:
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    rebuilt = rebuild_observability_from_inventory([event], scene_inventory, aoi_inventory)
    rows = rebuilt["observation_rows"]

    assert len(rows) == 3 * 4 * 4
    assert {row["event_id"] for row in rows} == {event.event_id}
    assert {row["aoi_id"] for row in rows} == {"b0500", "b1000", "b1500"}
    assert {row["combination_id"] for row in rows if row["rule_id"] == "A"} == {
        make_combination_id(aoi_id, pre_id, post_id)
        for aoi_id in ("b0500", "b1000", "b1500")
        for pre_id in ("pre30", "pre60")
        for post_id in ("post45", "post90")
    }

    pre30_post45 = next(
        row for row in rows if row["aoi_id"] == "b0500" and row["combination_id"] == "b0500_pre30_post45" and row["rule_id"] == "A"
    )
    pre60_post90 = next(
        row for row in rows if row["aoi_id"] == "b0500" and row["combination_id"] == "b0500_pre60_post90" and row["rule_id"] == "A"
    )
    assert (pre30_post45["pre_scene_count"], pre30_post45["post_scene_count"]) == (2, 1)
    assert (pre60_post90["pre_scene_count"], pre60_post90["post_scene_count"]) == (1, 1)
    assert pre30_post45["usable_pair_exists"] is True
    assert pre60_post90["usable_pair_exists"] is True


def test_rebuild_normalizes_string_int_ids_and_preserves_rows_vs_unique_scene_metrics() -> None:
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    rebuilt = rebuild_observability_from_inventory([event], scene_inventory, aoi_inventory)
    report = build_report(
        [event],
        rebuilt["observation_rows"],
        rebuilt["scene_rows"],
        [],
        requested_event_count=1,
    )

    assert normalize_aoi_id(500) == "b0500"
    assert normalize_aoi_id("B1000", "1000") == "b1000"
    assert report["scene_inventory_row_count"] == len(scene_inventory) == 27
    assert report["unique_sentinel2_scene_count"] == 15
    assert report["unique_pre_scene_count"] == 9
    assert report["unique_post_scene_count"] == 6
    assert report["unique_scene_count_by_event"] == {event.event_id: 15}
    assert report["unique_scene_count_by_aoi"] == {"b0500": 5, "b1000": 5, "b1500": 5}
    assert report["unique_scene_count_by_window"] == {
        "post:post45": 3,
        "post:post90": 3,
        "pre:pre30": 6,
        "pre:pre60": 3,
    }
    sensitivity = build_sensitivity_rows(rebuilt["observation_rows"])
    sensitivity_row = next(
        row for row in sensitivity if row["aoi_id"] == "b0500" and row["window_id"] == "pre30_post45" and row["rule_id"] == "A"
    )
    assert sensitivity_row["buffer_m"] == 500
    assert sensitivity_row["event_combination_count"] == 1
    assert sensitivity_row["events_with_pre_scene"] == 1
    assert sensitivity_row["events_with_post_scene"] == 1


def test_rebuild_selects_best_scene_and_evaluates_rules_a_through_d() -> None:
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    rebuilt = rebuild_observability_from_inventory([event], scene_inventory, aoi_inventory)
    rows = [
        row
        for row in rebuilt["observation_rows"]
        if row["combination_id"] == "b0500_pre30_post45"
    ]

    assert {row["rule_id"] for row in rows} == set(USABILITY_RULES)
    assert all(row["usable_pair_exists"] is True for row in rows)
    selected_by_rule = {row["rule_id"]: row["selected_pre_scene_id"] for row in rows}
    assert selected_by_rule["A"] == "b0500-pre30-b"
    assert selected_by_rule["B"] == "b0500-pre30-b"
    assert selected_by_rule["C"] == "b0500-pre30-b"
    assert selected_by_rule["D"] == "b0500-pre30-a"


def test_observability_invariants_reject_contradictions_and_invalid_scene_ids() -> None:
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    rebuilt = rebuild_observability_from_inventory([event], scene_inventory, aoi_inventory)
    observation_rows = rebuilt["observation_rows"]
    scene_rows = rebuilt["scene_rows"]
    validate_observability_invariants([event], observation_rows, scene_rows)

    wrong_event_id = [dict(row) for row in observation_rows]
    wrong_event_id[0]["event_id"] = "event-r1500_t06-not-in-pilot"
    with pytest.raises(ObservabilityValidationError, match="fuera del piloto"):
        validate_observability_invariants([event], wrong_event_id, scene_rows)

    zero_rows = [dict(row, pre_scene_count=0, post_scene_count=0, usable_pre_scene_count=0, usable_post_scene_count=0, selected_pre_scene_id="", selected_post_scene_id="", best_pre_scene_id="", best_post_scene_id="", usable_pair_exists=False) for row in observation_rows]
    with pytest.raises(ObservabilityValidationError, match="Contradicción"):
        validate_observability_invariants([event], zero_rows, scene_rows)

    too_many_usable = [dict(row) for row in observation_rows]
    too_many_usable[0]["usable_pre_scene_count"] = too_many_usable[0]["pre_scene_count"] + 1
    with pytest.raises(ObservabilityValidationError, match="usable_pre_scene_count"):
        validate_observability_invariants([event], too_many_usable, scene_rows)

    missing_post_usable = [dict(row) for row in observation_rows]
    missing_post_usable[0]["usable_post_scene_count"] = missing_post_usable[0]["post_scene_count"] + 1
    with pytest.raises(ObservabilityValidationError, match="usable_post_scene_count"):
        validate_observability_invariants([event], missing_post_usable, scene_rows)

    missing_selection = [dict(row) for row in observation_rows]
    missing_selection[0]["selected_pre_scene_id"] = ""
    with pytest.raises(ObservabilityValidationError, match="escenas seleccionadas"):
        validate_observability_invariants([event], missing_selection, scene_rows)

    unknown_best = [dict(row) for row in observation_rows]
    unknown_best[0]["best_pre_scene_id"] = "not-in-inventory"
    with pytest.raises(ObservabilityValidationError, match="best_pre_scene_id"):
        validate_observability_invariants([event], unknown_best, scene_rows)


def test_rebuild_rejects_empty_or_incompatible_inventory_schema() -> None:
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    with pytest.raises(ObservabilityValidationError, match="inventario de escenas: no contiene filas"):
        rebuild_observability_from_inventory([event], [], aoi_inventory)
    incompatible = [dict(scene_inventory[0])]
    incompatible[0].pop("combination_id")
    with pytest.raises(ObservabilityValidationError, match="faltan columnas"):
        rebuild_observability_from_inventory([event], incompatible, aoi_inventory)


def test_local_rebuild_writes_derived_outputs_without_earth_engine_and_preserves_inventories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner_module()
    event, scene_inventory, aoi_inventory = _fixture_inventory()
    scene_path = tmp_path / "scene_inventory.csv"
    aoi_path = tmp_path / "aoi_inventory.csv"
    write_csv(scene_path, SCENE_COLUMNS, scene_inventory)
    write_csv(aoi_path, AOI_COLUMNS, aoi_inventory)
    original_scene = scene_path.read_bytes()
    original_aoi = aoi_path.read_bytes()
    paths = {
        "scene_inventory": scene_path,
        "aoi_inventory": aoi_path,
        "errors": tmp_path / "errors.csv",
        "observability": tmp_path / "observability.csv",
        "report_json": tmp_path / "report.json",
        "report_markdown": tmp_path / "report.md",
        "attrition": tmp_path / "attrition.csv",
        "sensitivity": tmp_path / "sensitivity.csv",
        "figures": tmp_path / "figures",
    }
    monkeypatch.setattr(runner, "initialize_earth_engine", lambda: pytest.fail("Earth Engine no debe inicializarse"))
    report, figures = runner._rebuild_from_inventory(paths, [event])
    assert report["earth_engine_queries_made"] is False
    assert report["rebuild_from_inventory"] is True
    assert report["events_processed"] == 1
    assert report["events_failed"] == 0
    assert len(figures) == 9
    assert scene_path.read_bytes() == original_scene
    assert aoi_path.read_bytes() == original_aoi
    assert len(list(csv.DictReader(paths["observability"].open(encoding="utf-8", newline="")))) == 48


def test_cache_round_trip_and_signature_invalidation(tmp_path: Path) -> None:
    event = _event()
    signature = cache_signature(event)
    path = cache_path(tmp_path, event.event_id)
    result = {"event_id": event.event_id, "event_hash": event.event_hash, "aoi_records": [], "scene_records": []}
    write_event_cache(path, signature, result)
    assert load_event_cache(path, signature) == result
    changed = {**signature, "pipeline_version": "changed"}
    assert load_event_cache(path, changed) is None


@pytest.mark.skipif(not PILOT.exists(), reason="cohorte piloto no disponible")
def test_real_pilot_contains_only_30_r1500_t06_events_and_2025(tmp_path: Path) -> None:
    events = load_pilot_events(PILOT, EVENTS, MEMBERSHIP)
    assert len(events) == 30
    assert len({event.event_id for event in events}) == 30
    assert {event.configuration_id for event in events} == {"r1500_t06"}
    assert all(event.start_timestamp_utc.year == 2025 for event in events)
    assert all(detection.timestamp_utc.year == 2025 for event in events for detection in event.detections)


def test_real_pilot_rejects_event_not_in_pilot(tmp_path: Path) -> None:
    if not PILOT.exists():
        pytest.skip("cohorte piloto no disponible")
    rows = list(csv.DictReader(PILOT.open(encoding="utf-8", newline="")))
    rows[0]["event_id"] = "event-r1500_t06-not-in-events"
    altered = tmp_path / "pilot.csv"
    with altered.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ObservabilityValidationError, match="no existe"):
        load_pilot_events(altered, EVENTS, MEMBERSHIP)


def test_observability_schema_keeps_required_fields_and_controlled_version() -> None:
    required = {
        "event_id",
        "configuration_id",
        "aoi_method",
        "aoi_buffer_m",
        "pre_window_start",
        "pre_window_end",
        "post_window_start",
        "post_window_end",
        "pre_scene_count",
        "post_scene_count",
        "usable_pre_scene_count",
        "usable_post_scene_count",
        "selected_pre_scene_id",
        "selected_post_scene_id",
        "pre_cloud_fraction",
        "post_cloud_fraction",
        "pre_coverage_fraction",
        "post_coverage_fraction",
        "observability_status",
        "exclusion_reason",
        "processing_timestamp_utc",
        "pipeline_version",
    }
    assert required.issubset(OBSERVABILITY_COLUMNS)
    assert PIPELINE_VERSION == "fuegopa-sentinel2-observability-v1"
    assert AOI_METHOD == "detection_union_buffer"


def test_no_spectral_index_or_raster_download_code_is_present() -> None:
    source = (ROOT / "src" / "fuegopa" / "sentinel2_observability.py").read_text(encoding="utf-8")
    assert ".getDownloadURL" not in source
    assert "calculate_nbr" not in source.casefold()
    assert "dnbr" not in source.casefold()
