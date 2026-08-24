from __future__ import annotations

import json
from pathlib import Path

import pytest

from fuegopa.clustering import distance_between_coordinates_m
from fuegopa.external_reference import REFERENCES
from fuegopa.final_scientific_report import (
    ANALYSIS_VERSION,
    FIGURE_NAMES,
    analyze_final_pilot,
    verify_final_bundle,
    write_final_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FINAL_INPUT = ROOT / "outputs/clustering/r1500_t06/events.csv"
requires_private_final_inputs = pytest.mark.skipif(
    not PRIVATE_FINAL_INPUT.is_file(),
    reason=f"protected final-analysis input is not redistributed: {PRIVATE_FINAL_INPUT.relative_to(ROOT)}",
)


@requires_private_final_inputs
def test_final_analysis_preserves_real_counts_and_official_results() -> None:
    analysis = analyze_final_pilot(ROOT)
    assert analysis["analysis_version"] == ANALYSIS_VERSION
    assert analysis["counts"] == {
        "external_references": 2,
        "formal_human_observations": 0,
        "multi_detection_clusters": 267,
        "official_guacamaya_matches": 6,
        "official_picachos_matches": 0,
        "optical_pilot_events": 30,
        "optically_observable_events": 28,
        "optically_unobserved_events": 2,
        "possible_chain_merge_clusters": 17,
        "processed_firms_detections": 1185,
        "r1500_t06_clusters": 611,
        "raw_firms_records": 1532,
        "singletons": 344,
    }
    assert analysis["official_external_check"]["rules_preserved"] is True
    assert analysis["official_external_check"]["picachos_matches"] == 0
    assert analysis["official_external_check"]["guacamaya_matches"] == 6


@requires_private_final_inputs
def test_picachos_diagnostics_classify_spatial_threshold_miss() -> None:
    analysis = analyze_final_pilot(ROOT)
    diagnostics = analysis["picachos_diagnostics"]
    assert diagnostics["classification"]["category"] == "SPATIAL_THRESHOLD_MISS"
    official = next(
        row for row in diagnostics["raw_firms_audit"] if row["start_date"] == "2025-01-15"
    )
    assert [row["count"] for row in official["radii"]] == [0, 0, 1]
    assert official["closest_overall"]["distance_m"] == pytest.approx(10400.8258995668, abs=1e-6)
    temporal = diagnostics["nearest_temporally_relevant_clusters"]
    assert len(temporal) == 5
    assert temporal[0]["distance_m"] == pytest.approx(10400.8258995668, abs=1e-6)


def test_distance_diagnostic_reuses_frozen_metric() -> None:
    reference = REFERENCES[1]
    distance = distance_between_coordinates_m(reference.latitude, reference.longitude, 8.50952, -80.46034667)
    assert distance == pytest.approx(3076.3886870861247, abs=1e-6)


@requires_private_final_inputs
def test_guacamaya_timeline_is_ordered_and_interprets_t06_gaps() -> None:
    analysis = analyze_final_pilot(ROOT)
    timeline = analysis["guacamaya_timeline"]
    clusters = timeline["clusters"]
    assert [row["order"] for row in clusters] == [1, 2, 3, 4, 5, 6]
    assert [row["event_id"] for row in clusters] == sorted(
        [row["event_id"] for row in clusters],
        key=lambda event_id: next(row["cluster_start"] for row in clusters if row["event_id"] == event_id),
    )
    assert timeline["first_to_last_span_hours"] == pytest.approx(72.73333333333333)
    assert timeline["gaps_greater_than_t06_count"] == 5
    assert timeline["all_intercluster_gaps_greater_than_t06"] is True
    assert timeline["possible_t06_fragmentation"] is True
    assert timeline["fragmentation_interpretation"] == (
        "The frozen t06 rule represents temporally separated thermal observations "
        "as distinct provisional events; prolonged documented incidents may therefore "
        "correspond to multiple FirePA events."
    )


@requires_private_final_inputs
def test_guacamaya_percentiles_and_inclusive_ranks_use_611_unchanged() -> None:
    analysis = analyze_final_pilot(ROOT)
    rows = analysis["guacamaya_distribution_ranks"]
    assert len(rows) == 24
    assert {row["cohort_count"] for row in rows} == {611}
    assert rows[0]["official_percentile"] == pytest.approx(73.81342062)
    assert rows[0]["inclusive_rank"] == 451
    assert rows[-1]["metric"] == "duration"


@requires_private_final_inputs
def test_final_scope_has_no_network_or_prohibited_label_keys() -> None:
    analysis = analyze_final_pilot(ROOT)
    assert analysis["scope"]["network_access"] is False
    assert analysis["scope"]["earth_engine_queries_made_in_final_phase"] is False
    assert analysis["scope"]["formal_review_execution"] is False
    assert analysis["scope"]["targets_created"] is False
    assert analysis["scope"]["significant_burn_created"] is False

    def keys(value: object) -> list[str]:
        if isinstance(value, dict):
            result = list(value.keys())
            for nested in value.values():
                result.extend(keys(nested))
            return result
        if isinstance(value, list):
            result: list[str] = []
            for nested in value:
                result.extend(keys(nested))
            return result
        return []

    assert not {"ground_truth", "significant_burn", "target", "model_prediction", "confirmed_fire"}.intersection(
        keys(analysis)
    )


@requires_private_final_inputs
def test_final_bundle_is_deterministic_and_does_not_touch_official_outputs(tmp_path: Path) -> None:
    analysis = analyze_final_pilot(ROOT)
    official_paths = [
        ROOT / "outputs/external_reference_check_v1/matches.csv",
        ROOT / "outputs/external_reference_check_v1/report.json",
        ROOT / "outputs/external_reference_check_v1/manifest.json",
    ]
    before = {path: path.read_bytes() for path in official_paths}
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = write_final_bundle(analysis, first)
    second_manifest = write_final_bundle(analysis, second)
    assert first_manifest == second_manifest
    assert sorted(path.name for path in first.iterdir()) == sorted(path.name for path in second.iterdir())
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    assert verify_final_bundle(first)["ok"] is True
    assert sum(path.name in FIGURE_NAMES for path in first.iterdir()) == 6
    assert {path: path.read_bytes() for path in official_paths} == before
