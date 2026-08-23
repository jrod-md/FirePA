from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from fuegopa.external_reference import REFERENCES


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "references/external_reference_sources_v1.json"


def _load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _all_mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(_all_mapping_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_all_mapping_keys(nested))
        return keys
    return set()


def test_registry_has_seven_sources_and_two_incidents() -> None:
    registry = _load_registry()
    assert registry["schema_version"] == "firepa-external-reference-sources-v1"
    assert registry["research_scope"] == {
        "place": "Coclé, Panamá",
        "period_start": "2025-01-01",
        "period_end": "2025-04-30",
        "inclusive": True,
    }
    assert registry["source_count"] == 7
    assert registry["incident_count"] == 2
    assert len(registry["sources"]) == registry["source_count"]
    assert len(registry["incidents"]) == registry["incident_count"]
    assert [source["source_id"] for source in registry["sources"]] == [
        "SOURCE-001",
        "SOURCE-002",
        "SOURCE-003",
        "SOURCE-004",
        "SOURCE-005",
        "SOURCE-006",
        "SOURCE-007",
    ]


def test_registry_preserves_matching_anchors_and_official_rules() -> None:
    registry = _load_registry()
    incidents = {incident["incident_id"]: incident for incident in registry["incidents"]}
    anchors = {anchor["incident_id"]: anchor for anchor in registry["matching_anchors"]}
    expected = {
        "REFERENCE-001": {
            "latitude": 8.42097,
            "longitude": -80.65114,
            "window": ("2025-01-15", "2025-01-17"),
            "source_ids": ["SOURCE-001"],
        },
        "REFERENCE-002": {
            "latitude": 8.516667,
            "longitude": -80.433333,
            "window": ("2025-01-23", "2025-01-27"),
            "source_ids": [
                "SOURCE-002",
                "SOURCE-003",
                "SOURCE-004",
                "SOURCE-005",
                "SOURCE-006",
                "SOURCE-007",
            ],
        },
    }
    assert set(incidents) == set(expected)
    for reference_id, values in expected.items():
        incident = incidents[reference_id]
        anchor = anchors[reference_id]
        assert incident["official_matching_radius_m"] == 5000
        assert incident["official_matching_window"] == {
            "start": values["window"][0],
            "end": values["window"][1],
            "inclusive": True,
        }
        assert incident["source_ids"] == values["source_ids"]
        assert anchor["latitude"] == values["latitude"]
        assert anchor["longitude"] == values["longitude"]
        assert anchor["coordinate_status"] == "approximate"
        assert anchor["coordinate_source"] == "researcher_provided_approximate_anchor"
        assert anchor["coordinate_claimed_by_news_source"] is False
    assert [(reference.latitude, reference.longitude) for reference in REFERENCES] == [
        (8.42097, -80.65114),
        (8.516667, -80.433333),
    ]
    assert [
        (reference.temporal_window_start.isoformat(), reference.temporal_window_end.isoformat())
        for reference in REFERENCES
    ] == [
        ("2025-01-15", "2025-01-17"),
        ("2025-01-23", "2025-01-27"),
    ]


def test_registry_keeps_source_area_and_cause_claims_separate() -> None:
    registry = _load_registry()
    sources = {source["source_id"]: source for source in registry["sources"]}
    assert len([source for source in sources.values() if source["incident_id"] == "REFERENCE-001"]) == 1
    assert len([source for source in sources.values() if source["incident_id"] == "REFERENCE-002"]) == 6
    assert registry["incidents"][1]["reported_area_range_ha"] == {
        "min": 1035,
        "max": 1500,
        "claims_preserved": [
            {"source_id": "SOURCE-002", "reported_area_ha": 1035, "qualifier": "around"},
            {"source_id": "SOURCE-003", "reported_area_ha": 1050, "qualifier": "more_than"},
            {"source_id": "SOURCE-004", "reported_area_ha": 1500, "qualifier": "about"},
            {"source_id": "SOURCE-006", "reported_area_ha": 1500, "qualifier": "near"},
        ],
    }
    assert [sources[source_id]["reported_area_ha"] for source_id in sources] == [
        None,
        1035,
        1050,
        1500,
        None,
        1500,
        None,
    ]
    assert [sources[source_id].get("reported_area_qualifier") for source_id in sources] == [
        None,
        "around",
        "more_than",
        "about",
        None,
        "near",
        None,
    ]
    assert [sources[source_id]["cause_status"] for source_id in sources] == [
        None,
        None,
        "suspected_intentional",
        "suspected_intentional",
        "suspected_intentional",
        None,
        "suspected_intentional",
    ]
    assert registry["incidents"][1]["intentionality_status"] == "suspected_unconfirmed"
    assert not {
        "true_area",
        "best_area",
        "verified_area",
        "confirmed_arson",
    }.intersection(_all_mapping_keys(registry))


def test_registry_records_manual_osint_coverage_without_no_fire_claims() -> None:
    registry = _load_registry()
    coverage = registry["search_coverage"]
    assert coverage["method"] == "manual OSINT search"
    assert coverage["monthly_article_counts"] == {
        "2025-01": 6,
        "2025-02": 1,
        "2025-03": 0,
        "2025-04": 0,
    }
    assert coverage["total_located_articles"] == 7
    assert coverage["manual_search_exhaustiveness_claimed"] is False
    assert coverage["exact_caution"] == (
        "No qualifying articles were located during the manual OSINT search for March or April 2025."
    )
    assert coverage["absence_of_media_report_is_not_absence_of_thermal_activity"] is True
    assert coverage["absence_of_media_report_is_not_absence_of_fire"] is True
    serialized = json.dumps(registry, ensure_ascii=False).casefold()
    assert "no fires in march" not in serialized
    assert "no fires in april" not in serialized
    assert "no fire in march" not in serialized
    assert "no fire in april" not in serialized
    assert "sin incendios en marzo" not in serialized
    assert "sin incendios en abril" not in serialized


def test_registry_urls_are_syntactically_valid_and_not_pipeline_inputs() -> None:
    registry = _load_registry()
    for source in registry["sources"]:
        parsed = urlparse(source["url"])
        assert parsed.scheme == "https"
        assert parsed.netloc
        assert parsed.path
    assert registry["provenance_limits"]["urls_are_provenance_only"] is True
    assert registry["provenance_limits"]["source_urls_used_as_pipeline_inputs"] is False
    assert registry["provenance_limits"]["source_urls_used_for_matching"] is False
    assert registry["provenance_limits"]["external_references_are_ground_truth"] is False
    assert registry["provenance_limits"]["used_as_target"] is False
    assert registry["provenance_limits"]["used_for_supervised_modeling"] is False
    assert registry["provenance_limits"]["used_for_human_review"] is False


def test_official_match_counts_remain_in_existing_local_output() -> None:
    summary_path = ROOT / "outputs/external_reference_check_v1/reference_summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = {row["reference_id"]: row for row in csv.DictReader(handle)}
    assert rows["REFERENCE-001"]["match_count"] == "0"
    assert rows["REFERENCE-002"]["match_count"] == "6"


def test_protected_scientific_artifacts_keep_the_frozen_sha256() -> None:
    expected_hashes = {
        "data/processed/firms_cocle_2025_detections.csv": "3f166e8c2417e9ea875105f313bb3048498688af4c477c356d689ce1a212aa6e",
        "outputs/clustering/r1500_t06/events.csv": "646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844",
        "outputs/clustering/r1500_t06/membership.csv": "e9629fb521ce05d7cf63ad68683c0c79801611102e454c6877e3746977efc504",
        "outputs/clustering/r1500_t06/summary.json": "1e36f363ffd5560d580c47b260c34e8758635d1f5b76ed1882e5153abbf13736",
        "data/processed/sentinel2_observability_pilot_events.csv": "a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302",
        "data/interim/sentinel2_observability.csv": "b023837848220b94f16337e8c06bc3be078b5a2b6792925263a9fd42b23dc058",
        "data/interim/sentinel2_scene_inventory.csv": "851beea9b09e19368cf1131e82b0df5de7e5cd98566cf1da4cddeab464c7dcd1",
        "data/interim/sentinel2_aoi_inventory.csv": "fc0b77eb283455d08226152c50017d7cc70e3e0427f59f02788f0ce6d469a5b4",
        "outputs/sentinel2_event_pair_selection.csv": "24ba96aa8ee2a5a45d81e54d724d22c143be66583854764ef6c8919ea6b3dcd1",
        "data/interim/sentinel2_dnbr_event_metrics.csv": "9a1b0043a11ddf1da6e5fb5fe5a08241a28ee7d8e442d3832f4d8345fec30441",
        "outputs/sentinel2_dnbr_report.json": "5d75cd585e2005729ca83056052a71508f54b17ff2f55aa0d85b76175fd38dd9",
        "outputs/sentinel2_observability_report.json": "219d6a896c6966118154fc9da3cbc3b18775c07e142e592b7b43c36adc517655",
        "outputs/human_review/firepa_human_review.sqlite3": "c8f96d1c82bb6948010f796e801735c8786603b1d06390080265a2d324ff2cba",
        "outputs/human_review/formal_review_28/preparation_summary.json": "d5124dbe20bec1f15ff44a6e3e96d5bef73c5f23f149eed168e37a21ab44ddb4",
        "outputs/window_median_review_asset_v1/window_median_review_asset_manifest.json": "f7d9c619cda537800f777523434a4c22925156628ecfad17ad02fac7656c30fd",
        "outputs/external_reference_check_v1/manifest.json": "92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868",
    }
    for relative_path, expected in expected_hashes.items():
        digest = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert digest == expected, relative_path
