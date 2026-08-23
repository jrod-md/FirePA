from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.sentinel2_observability import ObservabilityValidationError
from fuegopa.sentinel2_policy import (
    DEFAULT_POLICY_RULE,
    default_policy_paths,
    build_policy_analysis,
    load_policy_inputs,
    validate_policy_inputs,
    write_policy_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_EXCLUDED = {
    "event-r1500_t06-1f8f72e78d63b0ee",
    "event-r1500_t06-ab8e9016ae0d3154",
}


@pytest.fixture(scope="module")
def local_policy_inputs():
    paths = default_policy_paths(ROOT)
    required = (paths["pilot"], paths["events"], paths["membership"], paths["observability"], paths["scene_inventory"], paths["aoi_inventory"])
    if not all(path.is_file() for path in required):
        pytest.skip("Los inventarios locales de observabilidad no están disponibles")
    return load_policy_inputs(
        pilot_path=paths["pilot"],
        events_path=paths["events"],
        membership_path=paths["membership"],
        observability_path=paths["observability"],
        scene_inventory_path=paths["scene_inventory"],
        aoi_inventory_path=paths["aoi_inventory"],
    )


@pytest.fixture(scope="module")
def local_analysis(local_policy_inputs):
    events, observation_rows, scene_rows, aoi_rows, _ = local_policy_inputs
    return build_policy_analysis(events, observation_rows, scene_rows, aoi_rows, policy_rule=DEFAULT_POLICY_RULE)


def test_policy_matrix_preserves_30_events_and_48_overall_rows(local_policy_inputs, local_analysis):
    events, _, scene_rows, aoi_rows, _ = local_policy_inputs
    summary = local_analysis["summary"]
    assert len(events) == 30
    assert len(scene_rows) == 10928
    assert summary["unique_sentinel2_scene_count"] == 212
    assert len(local_analysis["overall_rows"]) == 48
    assert summary["global_excluded_event_ids"] == sorted(EXPECTED_EXCLUDED)
    assert summary["earth_engine_queries_made"] is False
    assert summary["raster_downloaded"] is False
    assert summary["spectral_index_computed"] is False
    assert summary["frp_used_for_selection"] is False
    assert len(aoi_rows) == 90


def test_policy_matrix_is_deterministic(local_policy_inputs, local_analysis):
    events, observation_rows, scene_rows, aoi_rows, _ = local_policy_inputs
    repeated = build_policy_analysis(events, observation_rows, scene_rows, aoi_rows, policy_rule=DEFAULT_POLICY_RULE)
    assert repeated["overall_rows"] == local_analysis["overall_rows"]
    assert repeated["event_selection_rows"] == local_analysis["event_selection_rows"]
    assert repeated["fallback_rows"] == local_analysis["fallback_rows"]


def test_policy_matrix_contains_required_segments(local_analysis):
    segments = {
        (row["segment_dimension"], row["segment_value"])
        for row in local_analysis["segment_rows"]
    }
    assert {value for dimension, value in segments if dimension == "event_size_class"} == {"singleton", "multi_detection"}
    assert {value for dimension, value in segments if dimension == "source_class"} == {"single_source", "multiple_sources"}
    assert {value for dimension, value in segments if dimension == "chain_class"} == {"no_possible_chain_merge", "possible_chain_merge"}
    assert {value for dimension, value in segments if dimension == "excluded_event"} == EXPECTED_EXCLUDED
    assert {value for dimension, value in segments if dimension == "event_month"} == {"2025-01", "2025-02", "2025-03", "2025-04"}


def test_hierarchical_policy_rescues_only_with_temporal_fallback(local_analysis):
    selections = local_analysis["event_selection_rows"]
    rescued = [row for row in selections if row["fallback_rescues"] == "yes"]
    excluded = [row for row in selections if row["final_observability_status"] != "usable_pair"]
    assert len(rescued) == 1
    assert rescued[0]["event_id"] == "event-r1500_t06-09c2d54e2d8fb5dd"
    assert rescued[0]["fallback_combination_id"] == "b0500_pre30_post90"
    assert rescued[0]["fallback_type"] == "temporal_extension"
    assert {row["event_id"] for row in excluded} == EXPECTED_EXCLUDED
    assert all(row["fallback_combination_id"] == "" for row in excluded)


def test_selected_pairs_are_in_inventory_and_temporally_ordered(local_policy_inputs, local_analysis):
    events, _, scene_rows, _, _ = local_policy_inputs
    event_by_id = {event.event_id: event for event in events}
    scene_ids = {
        (row["event_id"], row["combination_id"], row["period_role"], row.get("sentinel2_scene_id") or row.get("system_index"))
        for row in scene_rows
    }
    for row in local_analysis["event_selection_rows"]:
        if row["final_observability_status"] != "usable_pair":
            continue
        event = event_by_id[row["event_id"]]
        combo = row["selected_combination_id"]
        assert (row["event_id"], combo, "pre", row["selected_pre_scene_id"]) in scene_ids
        assert (row["event_id"], combo, "post", row["selected_post_scene_id"]) in scene_ids
        pre_time = datetime.fromisoformat(row["pre_scene_acquisition_timestamp"].replace("Z", "+00:00"))
        post_time = datetime.fromisoformat(row["post_scene_acquisition_timestamp"].replace("Z", "+00:00"))
        assert pre_time < event.start_timestamp_utc
        assert post_time > event.end_timestamp_utc
        assert row["minimum_rule_passed"] in {"A", "B", "C", "D"}


def test_policy_rejects_event_outside_pilot(local_policy_inputs):
    events, observation_rows, scene_rows, aoi_rows, _ = local_policy_inputs
    invalid_rows = [dict(row) for row in observation_rows]
    invalid_rows[0]["event_id"] = "event-outside-pilot"
    with pytest.raises(ObservabilityValidationError, match="fuera del piloto"):
        validate_policy_inputs(events, invalid_rows, scene_rows, aoi_rows)


def test_policy_rejects_2026_event(local_policy_inputs):
    events, observation_rows, scene_rows, aoi_rows, _ = local_policy_inputs
    invalid_event = replace(
        events[0],
        start_timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(ObservabilityValidationError, match="2026"):
        validate_policy_inputs([invalid_event, *events[1:]], observation_rows, scene_rows, aoi_rows)


def test_policy_outputs_are_utf8_and_inventory_hashes_stay_unchanged(tmp_path, local_policy_inputs, local_analysis):
    paths = default_policy_paths(ROOT)
    before = {
        key: hashlib.sha256(paths[key].read_bytes()).hexdigest()
        for key in ("scene_inventory", "aoi_inventory", "observability")
    }
    output_paths = {
        "decision": tmp_path / "sentinel2_policy_decision.csv",
        "decision_markdown": tmp_path / "sentinel2_policy_decision.md",
        "event_selection": tmp_path / "sentinel2_event_pair_selection.csv",
        "fallbacks": tmp_path / "sentinel2_policy_fallbacks.csv",
        "figures": tmp_path / "figures",
    }
    figure_paths = write_policy_outputs(local_analysis, output_paths)
    assert len(figure_paths) == 6
    assert "Decisión provisional" in output_paths["decision_markdown"].read_text(encoding="utf-8")
    after = {
        key: hashlib.sha256(paths[key].read_bytes()).hexdigest()
        for key in ("scene_inventory", "aoi_inventory", "observability")
    }
    assert before == after


def test_policy_does_not_expose_frp_as_selection_input(local_analysis):
    assert local_analysis["summary"]["frp_used_for_selection"] is False
    assert all("frp" not in row for row in local_analysis["event_selection_rows"])
