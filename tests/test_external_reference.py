from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuegopa.clustering import distance_between_coordinates_m
from fuegopa.external_reference import (
    CONFIGURATION_ID,
    DISTANCE_THRESHOLD_M,
    EXPECTED_CLUSTER_COUNT,
    MATCH_COLUMNS,
    REFERENCES,
    _interval_overlap,
    _match_row,
    analyze_external_references,
    load_frozen_cluster_events,
    verify_outputs,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / "outputs/clustering/r1500_t06/events.csv"
OPTICAL_PATH = ROOT / "data/processed/sentinel2_observability_pilot_events.csv"


def _event_row(
    event_id: str,
    *,
    latitude: float = 8.516667,
    longitude: float = -80.433333,
    start: str = "2025-01-24T12:00:00Z",
    end: str = "2025-01-24T12:30:00Z",
) -> dict[str, str]:
    return {
        "configuration_id": CONFIGURATION_ID,
        "event_id": event_id,
        "start_timestamp_utc": start,
        "end_timestamp_utc": end,
        "duration_hours": "0.5",
        "detection_count": "2",
        "satellites": '["N","N20"]',
        "centroid_latitude": str(latitude),
        "centroid_longitude": str(longitude),
        "frp_max": "12.5",
        "frp_mean": "7.5",
        "frp_sum": "15.0",
        "day_fraction": "1",
        "night_fraction": "0",
        "possible_chain_merge": "false",
    }


def test_real_frozen_input_has_exactly_611_events_and_is_not_reclustered() -> None:
    rows = load_frozen_cluster_events(EVENTS_PATH)
    assert len(rows) == EXPECTED_CLUSTER_COUNT
    assert {row["configuration_id"] for row in rows} == {CONFIGURATION_ID}

    source = (ROOT / "src/fuegopa/external_reference.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "cluster_detections" not in called_names
    assert "reclustered" in source


def test_distance_correctness_matches_the_frozen_projection_metric() -> None:
    reference = REFERENCES[1]
    distance = distance_between_coordinates_m(
        reference.latitude,
        reference.longitude,
        8.50952,
        -80.46034667,
    )
    assert distance == pytest.approx(3076.389, abs=0.01)
    assert distance_between_coordinates_m(
        reference.latitude, reference.longitude, reference.latitude, reference.longitude
    ) == pytest.approx(0.0)


def test_five_km_boundary_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = REFERENCES[1]
    row = _event_row("event-boundary")
    monkeypatch.setattr(
        "fuegopa.external_reference.distance_between_coordinates_m",
        lambda *args: DISTANCE_THRESHOLD_M,
    )
    match = _match_row(
        reference,
        row,
        input_path=EVENTS_PATH,
        optical_event_ids=set(),
    )
    assert match is not None
    assert match["distance_m"] == DISTANCE_THRESHOLD_M

    monkeypatch.setattr(
        "fuegopa.external_reference.distance_between_coordinates_m",
        lambda *args: DISTANCE_THRESHOLD_M + 0.001,
    )
    assert _match_row(
        reference,
        row,
        input_path=EVENTS_PATH,
        optical_event_ids=set(),
    ) is None


def test_temporal_overlap_uses_inclusive_reference_dates() -> None:
    reference = REFERENCES[1]
    window_start = reference.window_start
    window_end = reference.window_end_inclusive

    overlaps, start, end, hours = _interval_overlap(window_start, window_start, reference)
    assert overlaps is True
    assert start == window_start
    assert end == window_start
    assert hours == pytest.approx(0.0)

    overlaps, _, _, _ = _interval_overlap(window_end, window_end, reference)
    assert overlaps is True

    outside = datetime(2025, 1, 28, tzinfo=timezone.utc)
    assert _interval_overlap(outside, outside, reference)[0] is False


def test_multiple_matches_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = REFERENCES[1]
    monkeypatch.setattr(
        "fuegopa.external_reference.distance_between_coordinates_m",
        lambda *args: 1000.0,
    )
    rows = [_event_row("event-one"), _event_row("event-two", start="2025-01-25T12:00:00Z", end="2025-01-25T12:10:00Z")]
    matches = [
        _match_row(reference, row, input_path=EVENTS_PATH, optical_event_ids=set())
        for row in rows
    ]
    assert [match["event_id"] for match in matches if match] == ["event-one", "event-two"]
    assert all(match["external_reference_match"] is True for match in matches if match)


def test_actual_external_check_counts_and_guacamaya_fragmentation() -> None:
    result = analyze_external_references(
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    summary = {row["reference_id"]: row for row in result["reference_summary"]}
    assert summary["REFERENCE-001"]["match_count"] == 0
    assert summary["REFERENCE-002"]["match_count"] == 6
    assert result["guacamaya_review"]["match_classification"] == "multiple_clusters"
    assert result["guacamaya_review"]["matched_cluster_count"] == 6
    assert result["guacamaya_review"]["possible_t06_fragmentation"] is True
    assert all(match["optical_followup_available"] is False for match in result["matches"])


def test_structured_output_has_no_label_fields_or_fire_relationship() -> None:
    result = analyze_external_references(
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    assert "fire" not in MATCH_COLUMNS
    assert "ground_truth" not in MATCH_COLUMNS
    assert "significant_burn" not in MATCH_COLUMNS
    assert "target" not in MATCH_COLUMNS
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert "fire=true" not in serialized.casefold()
    assert '"fire"' not in serialized
    assert '"ground_truth"' not in serialized
    assert '"significant_burn"' not in serialized
    assert '"target"' not in serialized


def test_outputs_are_deterministic_and_manifest_hashes_verify(tmp_path: Path) -> None:
    result = analyze_external_references(
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_manifest = write_outputs(
        result,
        output_dir=first_dir,
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    second_manifest = write_outputs(
        result,
        output_dir=second_dir,
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    assert first_manifest == second_manifest
    names = sorted(path.name for path in first_dir.iterdir())
    assert names == sorted(path.name for path in second_dir.iterdir())
    for name in names:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    verified = verify_outputs(first_dir)
    assert verified["ok"] is True, verified
    assert verified["manifest_file_count"] == 9


def test_scope_freeze_state_is_deferred_and_unexecuted() -> None:
    result = analyze_external_references(
        input_events_path=EVENTS_PATH,
        optical_cohort_path=OPTICAL_PATH,
    )
    assert result["formal_review"]["formal_review_status"] == "deferred"
    assert result["formal_review"]["execution_authorized"] is False
    assert result["formal_review"]["pass_a_executed"] is False
    assert result["formal_review"]["pass_b_executed"] is False
    assert result["supervised_modeling"]["supervised_modeling_gate"] == "deferred"
    assert result["supervised_modeling"]["target_created"] is False
    assert result["scope"]["environmental_feature_extraction"] == "not_authorized"
    assert result["scope"]["earth_engine_queries_made"] is False
    assert result["scope"]["network_access"] is False
