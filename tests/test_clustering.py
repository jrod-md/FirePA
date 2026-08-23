from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fuegopa.clustering import (
    DEFAULT_CONFIGURATIONS,
    ClusteringConfig,
    ClusteringValidationError,
    build_stability_rows,
    cluster_detections,
    distance_between_coordinates_m,
    parse_timestamp_utc,
    sensitivity_neighbor_pairs,
    summary_metrics,
    validate_coordinate,
    validate_required_columns,
    validate_detection_rows,
    load_detections_csv,
)


def _row(
    detection_id: str,
    *,
    latitude: float = 8.5,
    longitude: float = -80.2,
    timestamp: str = "2025-01-10T12:00:00Z",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "detection_id": detection_id,
        "latitude": str(latitude),
        "longitude": str(longitude),
        "acq_datetime_utc": timestamp,
        "firms_source": "VIIRS_NOAA20_SP",
        "satellite": "NOAA-20",
        "instrument": "VIIRS",
        "frp": "10.5",
        "confidence_raw": "n",
        "confidence_normalized": "nominal",
        "daynight": "D",
        "raw_file": "fragment.csv",
        "raw_sha256": "a" * 64,
    }
    row.update(overrides)
    return row


def _near_spatial_boundary(radius_m: float, *, outside: bool = False) -> float:
    base_latitude = 8.5
    longitude = -80.2
    low, high = base_latitude, base_latitude + 0.01
    for _ in range(70):
        middle = (low + high) / 2
        distance = distance_between_coordinates_m(base_latitude, longitude, middle, longitude)
        if distance < radius_m:
            low = middle
        else:
            high = middle
    boundary_latitude = (low + high) / 2
    return boundary_latitude + (1e-9 if outside else 0.0)


def test_coordinate_validation_accepts_wgs84_and_rejects_invalid_values() -> None:
    assert validate_coordinate("8.5", "latitude") == pytest.approx(8.5)
    assert validate_coordinate(-80.2, "longitude") == pytest.approx(-80.2)
    with pytest.raises(ClusteringValidationError):
        validate_coordinate("91", "latitude")
    with pytest.raises(ClusteringValidationError):
        validate_coordinate("not-a-number", "longitude")


def test_timestamp_parser_normalizes_offsets_to_canonical_utc() -> None:
    parsed, canonical = parse_timestamp_utc("2025-01-10T07:00:00-05:00")
    assert parsed.tzinfo == timezone.utc
    assert canonical == "2025-01-10T12:00:00Z"
    with pytest.raises(ClusteringValidationError):
        parse_timestamp_utc("2025-01-10 12:00:00")


def test_required_columns_are_detected_before_graph_construction() -> None:
    with pytest.raises(ClusteringValidationError, match="longitude"):
        validate_required_columns(["detection_id", "latitude", "acq_datetime_utc"])
    with pytest.raises(ClusteringValidationError, match="Timestamp UTC"):
        validate_detection_rows([_row("a", timestamp="")])


def test_missing_descriptive_values_are_preserved_as_missing_not_graph_edges() -> None:
    row = _row("a", frp="", confidence_raw="", confidence_normalized="", daynight="")
    result = cluster_detections([row], ClusteringConfig(375, 6))
    event = result.events[0]
    assert event["frp_min"] is None
    assert event["daynight_known_count"] == 0
    assert result.membership[0]["frp"] == ""


def test_singletons_are_preserved_and_all_detection_ids_are_unique() -> None:
    result = cluster_detections(
        [_row("b"), _row("a", latitude=8.7, longitude=-80.5)],
        ClusteringConfig(375, 6),
    )
    assert len(result.events) == 2
    assert all(event["detection_count"] == 1 for event in result.events)
    assert summary_metrics(result)["all_detections_preserved"] is True
    assert {row["detection_id"] for row in result.membership} == {"a", "b"}


def test_exact_spatial_threshold_is_inclusive() -> None:
    radius = 375
    second_latitude = _near_spatial_boundary(radius)
    distance = distance_between_coordinates_m(8.5, -80.2, second_latitude, -80.2)
    assert distance <= radius * (1 + 1e-9)
    result = cluster_detections(
        [_row("a"), _row("b", latitude=second_latitude)],
        ClusteringConfig(radius, 6),
    )
    assert len(result.events) == 1


def test_spatial_threshold_just_outside_is_not_an_edge() -> None:
    second_latitude = _near_spatial_boundary(375, outside=True)
    assert distance_between_coordinates_m(8.5, -80.2, second_latitude, -80.2) > 375
    result = cluster_detections(
        [_row("a"), _row("b", latitude=second_latitude)],
        ClusteringConfig(375, 6),
    )
    assert len(result.events) == 2


def test_exact_temporal_threshold_is_inclusive() -> None:
    result = cluster_detections(
        [
            _row("a"),
            _row("b", timestamp="2025-01-10T18:00:00Z"),
        ],
        ClusteringConfig(375, 6),
    )
    assert len(result.events) == 1


def test_temporal_threshold_just_outside_is_not_an_edge() -> None:
    result = cluster_detections(
        [
            _row("a"),
            _row("b", timestamp="2025-01-10T18:00:01Z"),
        ],
        ClusteringConfig(375, 6),
    )
    assert len(result.events) == 2


def test_graph_is_transitive_and_does_not_require_direct_connection_to_first_node() -> None:
    result = cluster_detections(
        [
            _row("a", longitude=-80.2000, timestamp="2025-01-10T12:00:00Z"),
            _row("b", longitude=-80.2020, timestamp="2025-01-10T13:00:00Z"),
            _row("c", longitude=-80.2040, timestamp="2025-01-10T14:00:00Z"),
        ],
        ClusteringConfig(375, 6),
    )
    assert len(result.events) == 1
    assert result.events[0]["detection_count"] == 3


def test_row_order_does_not_change_event_membership_or_event_id() -> None:
    rows = [_row("c"), _row("a"), _row("b", timestamp="2025-01-10T13:00:00Z")]
    first = cluster_detections(rows, ClusteringConfig(750, 12))
    second = cluster_detections(list(reversed(rows)), ClusteringConfig(750, 12))
    assert [event["event_id"] for event in first.events] == [event["event_id"] for event in second.events]
    assert list(first.membership) == list(second.membership)


def test_descriptive_fields_do_not_change_graph_edges() -> None:
    first = _row("a", firms_source="VIIRS_NOAA20_SP", frp="1")
    second = _row(
        "b",
        firms_source="VIIRS_SNPP_SP",
        satellite="SNPP",
        frp="999",
        confidence_raw="h",
        daynight="N",
    )
    result = cluster_detections([first, second], ClusteringConfig(375, 6))
    assert len(result.events) == 1
    assert result.events[0]["both_sensors"] is True
    assert result.events[0]["multi_source"] is True


def test_invalid_coordinate_timestamp_and_duplicate_id_are_rejected() -> None:
    with pytest.raises(ClusteringValidationError):
        cluster_detections([_row("a", latitude=100)], ClusteringConfig(375, 6))
    with pytest.raises(ClusteringValidationError):
        cluster_detections([_row("a", timestamp="not-a-timestamp")], ClusteringConfig(375, 6))
    with pytest.raises(ClusteringValidationError, match="duplicado"):
        cluster_detections([_row("a"), _row("a", longitude=-80.3)], ClusteringConfig(375, 6))


def test_event_statistics_include_duration_extent_and_confidence_counts() -> None:
    result = cluster_detections(
        [
            _row("a", frp="2", confidence_normalized="nominal"),
            _row("b", frp="4", confidence_normalized="high", timestamp="2025-01-11T00:00:00Z"),
        ],
        ClusteringConfig(375, 24),
    )
    event = result.events[0]
    assert event["duration_hours"] == pytest.approx(12)
    assert event["frp_sum"] == pytest.approx(6)
    assert event["confidence_counts"] == {"high": 1, "nominal": 1}
    assert event["crosses_midnight"] is True
    assert event["multi_day"] is True


def test_stability_grid_has_exactly_twenty_four_adjacent_comparisons() -> None:
    assert len(sensitivity_neighbor_pairs()) == 24
    results = {
        configuration.configuration_id: cluster_detections([_row("a")], configuration)
        for configuration in DEFAULT_CONFIGURATIONS
    }
    rows = build_stability_rows(results)
    assert len(rows) == 24
    assert all(row["jaccard_coassignment"] == 1.0 for row in rows)


def test_incompatible_csv_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "incompatible.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["detection_id", "latitude", "longitude"])
        writer.writeheader()
        writer.writerow({"detection_id": "a", "latitude": "8.5", "longitude": "-80.2"})
    with pytest.raises(ClusteringValidationError, match="acq_datetime_utc"):
        load_detections_csv(path)


def test_input_without_optional_columns_is_accepted() -> None:
    rows = [
        {
            "detection_id": "a",
            "latitude": "8.5",
            "longitude": "-80.2",
            "acq_datetime_utc": "2025-01-10T12:00:00Z",
        }
    ]
    parsed = validate_detection_rows(rows)
    result = cluster_detections(parsed, ClusteringConfig(375, 6))
    assert len(result.events) == 1
    assert result.events[0]["source_count"] == 0


def test_event_id_and_membership_schema_are_configuration_specific() -> None:
    result = cluster_detections([_row("a")], ClusteringConfig(750, 12))
    event_id = result.events[0]["event_id"]
    assert event_id.startswith("event-r0750_t12-")
    assert tuple(result.membership[0]) == (
        "configuration_id",
        "event_id",
        "detection_id",
        "timestamp_utc",
        "latitude",
        "longitude",
        "firms_source",
        "satellite",
        "instrument",
        "frp",
        "confidence_raw",
        "daynight",
        "raw_file",
        "raw_sha256",
    )


def test_chain_diagnostic_marks_long_component_without_dropping_membership() -> None:
    result = cluster_detections(
        [
            _row("a", timestamp="2025-01-10T00:00:00Z"),
            _row("b", timestamp="2025-01-12T00:00:00Z"),
            _row("c", timestamp="2025-01-14T00:00:00Z"),
        ],
        ClusteringConfig(375, 48),
    )
    assert len(result.events) == 1
    assert result.events[0]["possible_chain_merge"] is True
    assert "duration_over_72h" in result.events[0]["chain_merge_reasons"]
    assert len(result.membership) == 3
