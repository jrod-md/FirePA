from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from fuegopa.provisional import (
    FROZEN_CONFIGURATION_ID,
    FROZEN_EVENT_COLUMNS,
    FROZEN_MEMBERSHIP_COLUMNS,
    OBSERVABILITY_COLUMNS,
    PILOT_COLUMNS,
    ProvisionalValidationError,
    freeze_from_outputs,
    read_csv_rows,
    select_observability_pilot,
    write_csv,
    write_empty_observability_schema,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_SOURCE = ROOT / "outputs" / "clustering" / "r1500_t06"


def _write_rows(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(path, fieldnames, rows)


def _source_fixture(
    root: Path,
    *,
    configuration_id: str = FROZEN_CONFIGURATION_ID,
    event_year: int = 2025,
    duplicate_detection: bool = False,
) -> Path:
    source = root / "source"
    membership_rows = [
        {
            "configuration_id": configuration_id,
            "event_id": "evt_001",
            "detection_id": "det_001",
            "timestamp_utc": f"{event_year}-01-01T12:00:00Z",
            "latitude": "8.40",
            "longitude": "-80.20",
            "firms_source": "source_a",
            "satellite": "NOAA-20",
            "instrument": "VIIRS",
            "frp": "12.5",
            "confidence_raw": "80",
            "daynight": "D",
            "raw_file": "sample.csv",
            "raw_sha256": "abc",
        },
        {
            "configuration_id": configuration_id,
            "event_id": "evt_002",
            "detection_id": "det_002",
            "timestamp_utc": f"{event_year}-01-01T12:05:00Z",
            "latitude": "8.41",
            "longitude": "-80.21",
            "firms_source": "source_b",
            "satellite": "Suomi-NPP",
            "instrument": "VIIRS",
            "frp": "20.0",
            "confidence_raw": "nominal",
            "daynight": "N",
            "raw_file": "sample.csv",
            "raw_sha256": "abc",
        },
        {
            "configuration_id": configuration_id,
            "event_id": "evt_002",
            "detection_id": "det_003" if not duplicate_detection else "det_002",
            "timestamp_utc": f"{event_year}-01-01T12:10:00Z",
            "latitude": "8.42",
            "longitude": "-80.22",
            "firms_source": "source_b",
            "satellite": "Suomi-NPP",
            "instrument": "VIIRS",
            "frp": "30.0",
            "confidence_raw": "high",
            "daynight": "N",
            "raw_file": "sample.csv",
            "raw_sha256": "abc",
        },
    ]
    event_rows = [
        {
            "configuration_id": configuration_id,
            "event_id": "evt_001",
            "start_timestamp_utc": f"{event_year}-01-01T12:00:00Z",
            "end_timestamp_utc": f"{event_year}-01-01T12:00:00Z",
            "duration_hours": "0",
            "detection_count": "1",
            "source_count": "1",
            "firms_sources": "source_a",
            "satellite_count": "1",
            "satellites": "NOAA-20",
            "centroid_latitude": "8.40",
            "centroid_longitude": "-80.20",
            "bbox_south": "8.40",
            "bbox_west": "-80.20",
            "bbox_north": "8.40",
            "bbox_east": "-80.20",
            "max_pairwise_distance_m": "0",
            "max_distance_to_centroid_m": "0",
            "max_consecutive_gap_hours": "0",
            "calendar_days_covered": "1",
            "frp_min": "12.5",
            "frp_max": "12.5",
            "frp_mean": "12.5",
            "frp_median": "12.5",
            "frp_sum": "12.5",
            "confidence_counts": '{"high": 1}',
            "day_fraction": "1",
            "night_fraction": "0",
            "possible_chain_merge": "False",
            "chain_merge_reasons": "",
        },
        {
            "configuration_id": configuration_id,
            "event_id": "evt_002",
            "start_timestamp_utc": f"{event_year}-01-01T12:05:00Z",
            "end_timestamp_utc": f"{event_year}-01-01T12:10:00Z",
            "duration_hours": "0.083333",
            "detection_count": "2",
            "source_count": "1",
            "firms_sources": "source_b",
            "satellite_count": "1",
            "satellites": "Suomi-NPP",
            "centroid_latitude": "8.415",
            "centroid_longitude": "-80.215",
            "bbox_south": "8.41",
            "bbox_west": "-80.22",
            "bbox_north": "8.42",
            "bbox_east": "-80.21",
            "max_pairwise_distance_m": "1500",
            "max_distance_to_centroid_m": "750",
            "max_consecutive_gap_hours": "0.083333",
            "calendar_days_covered": "1",
            "frp_min": "20",
            "frp_max": "30",
            "frp_mean": "25",
            "frp_median": "25",
            "frp_sum": "50",
            "confidence_counts": '{"high": 1, "nominal": 1}',
            "day_fraction": "0",
            "night_fraction": "1",
            "possible_chain_merge": "False",
            "chain_merge_reasons": "",
        },
    ]
    _write_rows(source / "membership.csv", FROZEN_MEMBERSHIP_COLUMNS, membership_rows)
    _write_rows(
        source / "events.csv",
        (
            "configuration_id",
            "event_id",
            "start_timestamp_utc",
            "end_timestamp_utc",
            "duration_hours",
            "detection_count",
            "source_count",
            "firms_sources",
            "satellite_count",
            "satellites",
            "centroid_latitude",
            "centroid_longitude",
            "bbox_south",
            "bbox_west",
            "bbox_north",
            "bbox_east",
            "max_pairwise_distance_m",
            "max_distance_to_centroid_m",
            "max_consecutive_gap_hours",
            "calendar_days_covered",
            "frp_min",
            "frp_max",
            "frp_mean",
            "frp_median",
            "frp_sum",
            "confidence_counts",
            "day_fraction",
            "night_fraction",
            "possible_chain_merge",
            "chain_merge_reasons",
        ),
        event_rows,
    )
    return source


def _synthetic_events(count: int = 40) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        detection_count = 1 if index < count // 2 else 2 + ((index - count // 2) % 4)
        rows.append(
            {
                "event_id": f"evt_{index:03d}",
                "configuration_id": FROZEN_CONFIGURATION_ID,
                "start_timestamp_utc": f"2025-{index % 4 + 1:02d}-01T12:00:00Z",
                "end_timestamp_utc": f"2025-{index % 4 + 1:02d}-01T12:05:00Z",
                "detection_count": str(detection_count),
                "source_count": str(1 + (index % 2)),
                "sources": "a;b" if index % 2 else "a",
                "possible_chain_merge": "True" if index % 3 == 0 else "False",
                "frp_sum": str(1000 - index),
            }
        )
    return rows


def test_freeze_maps_source_fields_and_preserves_ids(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    membership_output = tmp_path / "processed" / "membership.csv"
    events_output = tmp_path / "processed" / "events.csv"

    report = freeze_from_outputs(
        source,
        membership_output,
        events_output,
        expected_detection_count=3,
        expected_event_count=2,
    )

    with membership_output.open(encoding="utf-8", newline="") as handle:
        membership = list(csv.DictReader(handle))
    with events_output.open(encoding="utf-8", newline="") as handle:
        events = list(csv.DictReader(handle))
    assert report["event_count"] == 2
    assert [row["detection_id"] for row in membership] == ["det_001", "det_002", "det_003"]
    assert membership[0]["raw_sha256"] == "abc"
    assert events[0]["event_id"] == "evt_001"
    assert events[1]["sources"] == "source_b"
    assert events[1]["min_latitude"] == "8.41"
    assert tuple(membership[0]) == FROZEN_MEMBERSHIP_COLUMNS
    assert tuple(events[0]) == FROZEN_EVENT_COLUMNS


def test_freeze_rejects_event_from_another_configuration(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path, configuration_id="r3000_t06")
    with pytest.raises(ProvisionalValidationError, match="r1500_t06"):
        freeze_from_outputs(source, tmp_path / "membership.csv", tmp_path / "events.csv")


def test_freeze_rejects_2026_data(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path, event_year=2026)
    with pytest.raises(ProvisionalValidationError, match="2026"):
        freeze_from_outputs(
            source,
            tmp_path / "membership.csv",
            tmp_path / "events.csv",
            expected_detection_count=3,
            expected_event_count=2,
        )


def test_freeze_rejects_duplicate_detection_id(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path, duplicate_detection=True)
    with pytest.raises(ProvisionalValidationError, match="detection_id duplicados"):
        freeze_from_outputs(
            source,
            tmp_path / "membership.csv",
            tmp_path / "events.csv",
            expected_detection_count=3,
            expected_event_count=2,
        )


@pytest.mark.skipif(not REAL_SOURCE.exists(), reason="outputs de clustering no disponibles")
def test_real_r1500_t06_preserves_1185_detections_and_611_events(tmp_path: Path) -> None:
    membership_output = tmp_path / "membership.csv"
    events_output = tmp_path / "events.csv"
    report = freeze_from_outputs(
        REAL_SOURCE,
        membership_output,
        events_output,
    )
    membership = read_csv_rows(membership_output)
    events = read_csv_rows(events_output)
    assert report["configuration_id"] == FROZEN_CONFIGURATION_ID
    assert report["detection_count"] == 1185
    assert report["event_count"] == 611
    assert report["sum_detection_count"] == 1185
    assert report["singleton_count"] == 344
    assert report["multi_detection_event_count"] == 267
    assert len({row["detection_id"] for row in membership}) == 1185
    assert all(count == 1 for count in Counter(row["detection_id"] for row in membership).values())
    event_counts = Counter(row["event_id"] for row in membership)
    assert all(event_counts[row["event_id"]] == int(row["detection_count"]) for row in events)


def test_sampling_is_deterministic() -> None:
    events = _synthetic_events()
    first, first_report = select_observability_pilot(events, sample_size=20, seed=1234)
    second, second_report = select_observability_pilot(list(reversed(events)), sample_size=20, seed=1234)
    assert [row["event_id"] for row in first] == [row["event_id"] for row in second]
    assert first_report["selected_event_ids"] == second_report["selected_event_ids"]
    assert len(first) == 20
    assert tuple(first[0]) == PILOT_COLUMNS


def test_sampling_respects_size_and_multi_quartile_strata() -> None:
    selected, report = select_observability_pilot(_synthetic_events(), sample_size=20, seed=1234)
    assert report["quota_achieved"]["event_size_class"] == report["quota_targets"]["event_size_class"]
    quartile_targets = report["quota_targets"]["multi_detection_quartile"]
    quartile_achieved = report["quota_achieved"]["multi_detection_quartile"]
    assert {key: quartile_achieved[key] for key in quartile_targets} == quartile_targets
    assert report["quota_achieved"]["month"] == report["quota_targets"]["month"]
    assert report["quota_achieved"]["source_class"] == report["quota_targets"]["source_class"]
    assert report["quota_achieved"]["chain_class"] == report["quota_targets"]["chain_class"]
    assert len({row["event_id"] for row in selected}) == 20


def test_sampling_does_not_use_frp_directly() -> None:
    events = _synthetic_events()
    altered = [{**event, "frp_sum": str((index + 1) * 999999)} for index, event in enumerate(events)]
    selected, report = select_observability_pilot(events, sample_size=20, seed=1234)
    altered_selected, altered_report = select_observability_pilot(altered, sample_size=20, seed=1234)
    assert report["frp_used_for_selection"] is False
    assert altered_report["frp_used_for_selection"] is False
    assert report["selected_event_ids"] == altered_report["selected_event_ids"]
    assert [row["event_id"] for row in selected] == [row["event_id"] for row in altered_selected]


def test_sampling_rejects_event_from_another_configuration() -> None:
    events = _synthetic_events()
    events[0] = {**events[0], "configuration_id": "r3000_t06"}
    with pytest.raises(ProvisionalValidationError, match="r1500_t06"):
        select_observability_pilot(events, sample_size=20, seed=1234)


def test_empty_observability_schema_has_no_fictitious_rows(tmp_path: Path) -> None:
    output = tmp_path / "sentinel2_observability.csv"
    write_empty_observability_schema(output)
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == OBSERVABILITY_COLUMNS
        assert list(reader) == []
