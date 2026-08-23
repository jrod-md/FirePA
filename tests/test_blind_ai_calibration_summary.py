from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summarize_blind_ai_calibration import summarize  # noqa: E402
from fuegopa.blind_ai_calibration import integrity_snapshot  # noqa: E402


DATABASE = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def calibration_summary() -> dict:
    return summarize()


def test_summary_counts_distributions_and_contract(calibration_summary: dict) -> None:
    assert calibration_summary["case_count"] == 7
    assert calibration_summary["review_item_count"] == 7
    assert calibration_summary["reviewer_count"] == 1
    assert calibration_summary["reviewer_type_distribution"] == {"ai_assisted": 7}
    assert calibration_summary["label_status_distribution"] == {"provisional_pseudolabel": 7}

    for distribution in calibration_summary["distributions"].values():
        assert sum(distribution.values()) == 7

    assert calibration_summary["confidence_changes"]["distribution"] == {
        "high->high": 1,
        "low->low": 2,
        "low->medium": 1,
        "medium->medium": 3,
    }
    assert calibration_summary["confidence_changes"]["changed_case_count"] == 1
    assert calibration_summary["counts"] == {
        "adjudications_requested": 0,
        "ambiguous_cases": 3,
        "low_confidence_pass_a_cases": 3,
        "low_confidence_pass_b_cases": 2,
        "indeterminate_association_cases": 2,
        "confounder_cases": 5,
        "explicit_confounder_cases": 5,
        "partial_agreement_cases": 6,
    }

    contract = calibration_summary["contract"]
    assert contract["ground_truth_present"] is False
    assert contract["final_scientific_labels_created"] is False
    assert contract["significant_burn_present"] is False
    assert contract["future_period_data_used"] is False
    assert contract["review_columns_with_prohibited_label_fields"] == []
    assert contract["import_report"]["inserted"] == 7
    assert contract["import_report"]["errors"] == []


def test_summary_triage_is_deterministic_and_partial_agreement_is_not_enough(
    calibration_summary: dict,
) -> None:
    assert calibration_summary["case_sets"]["needs_adjudication_cases"] == [
        "CASE-003",
        "CASE-005",
        "CASE-006",
    ]
    assert calibration_summary["case_sets"]["specialized_review_cases"] == [
        "CASE-003",
        "CASE-004",
        "CASE-005",
        "CASE-006",
    ]
    assert calibration_summary["case_sets"]["recommended_additional_review_cases"] == [
        "CASE-003",
        "CASE-004",
        "CASE-005",
        "CASE-006",
    ]

    by_case = {case["case_id"]: case for case in calibration_summary["cases"]}
    assert by_case["CASE-001"]["pass_b_mode_agreement"] == "partially_agree"
    assert by_case["CASE-001"]["proposed_review_status"] == "pass_b_complete"
    assert by_case["CASE-004"]["proposed_review_status"] == "pass_b_complete"
    assert by_case["CASE-004"]["specialized_review_reasons"] == [
        "competing_land_change=mixed"
    ]
    assert by_case["CASE-006"]["confidence_changed"] is True
    assert by_case["CASE-006"]["proposed_review_status"] == "needs_adjudication"


def test_summary_candidate_reevaluation_separates_limitations_and_promotes_case_007(
    calibration_summary: dict,
) -> None:
    candidate = calibration_summary["candidate_reevaluation"]
    assert candidate["case_sets"]["needs_adjudication_cases"] == [
        "CASE-003",
        "CASE-005",
        "CASE-006",
    ]
    assert candidate["case_sets"]["expert_review_required_cases"] == [
        "CASE-003",
        "CASE-004",
        "CASE-005",
        "CASE-006",
    ]
    assert candidate["case_sets"]["expert_review_recommended_cases"] == ["CASE-007"]
    assert candidate["changes_from_draft_v2"] == {
        "adjudication_cases_unchanged": True,
        "legacy_cloud_or_haze_reclassified_as_limitation": ["CASE-003"],
        "new_expert_recommended_cases": ["CASE-007"],
        "notes_used_for_limitation": False,
    }
    by_case = {case["case_id"]: case for case in candidate["cases"]}
    assert by_case["CASE-003"]["candidate_competing_land_change"] == "unknown"
    assert by_case["CASE-003"]["observation_limitation"] == "cloud_or_haze"
    assert by_case["CASE-007"]["expert_review_priority"] == "recommended"


def test_summary_does_not_write_sqlite_or_protected_outputs() -> None:
    before_file_hash = _sha256(DATABASE)
    before_integrity = integrity_snapshot(ROOT)
    summarize()
    after_file_hash = _sha256(DATABASE)
    after_integrity = integrity_snapshot(ROOT)

    assert before_file_hash == after_file_hash
    assert before_integrity == after_integrity

    connection = sqlite3.connect(f"file:{DATABASE.resolve().as_posix()}?mode=ro", uri=True)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
    finally:
        connection.close()
    assert "ground_truth" not in columns
    assert "significant_burn" not in columns
