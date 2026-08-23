from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_ai_calibration import integrity_snapshot  # noqa: E402
from fuegopa.blind_control_round import (  # noqa: E402
    COMPETING_LAND_CHANGE_CODES,
    CONTROL_CASE_IDS,
    OBSERVATION_LIMITATION_CODES,
    build_blind_control_packages,
    compare_blind_control_results,
    derive_control_triage,
    import_blind_control_results,
    validate_reviewer_provenance,
)
from fuegopa.human_review_schema import CALIBRATION_EVENT_IDS, expected_panel_paths  # noqa: E402
from fuegopa.human_review_store import HumanReviewStore  # noqa: E402


DATABASE = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review(case_id: str, *, visible: str = "yes", confidence: str = "medium", competitor: str = "none_visible", limitation: str = "none") -> dict:
    return {
        "case_id": case_id,
        "pass_a_visible_burn_scar": visible,
        "pass_a_scar_confidence": confidence,
        "pass_a_event_association": "likely",
        "pass_a_competing_land_change": competitor,
        "observation_limitation": limitation,
        "pass_a_notes": "Structured observation note.",
    }


def _response(reviewer_id: str, pass_name: str, *, model: str | None = None, changes: dict | None = None) -> dict:
    model = model or {
        "blind_control_r1_reviewer_a": "GPT-5.6 Thinking",
        "blind_control_r1_reviewer_b": "GPT-5.5 Thinking",
    }.get(reviewer_id, "control-model-v1")
    changes = changes or {}
    reviews = []
    for case_id in CONTROL_CASE_IDS:
        item = _review(case_id, **changes.get(case_id, {}))
        if pass_name == "B":
            item.update(
                {
                    "pass_b_mode_agreement": "partially_agree",
                    "pass_b_confidence_after": item["pass_a_scar_confidence"],
                    "pass_b_requires_adjudication": False,
                    "pass_b_notes": "Temporal robustness note.",
                }
            )
        reviews.append(item)
    return {
        "schema_version": "firepa-blind-control-r1-response-v1",
        "round_id": "control_r1",
        "pass": pass_name,
        "protocol_version": "candidate-v1",
        "reviewer_id": reviewer_id,
        "reviewer_type": "ai_assisted",
        "reviewer_expertise": "not_applicable",
        "reviewer_model": model,
        "label_status": "provisional_pseudolabel",
        "reviews": reviews,
    }


def _write_pair(directory: Path, reviewer_id: str, *, changes: dict | None = None) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pass_a = directory / f"{reviewer_id}_pass_a.json"
    pass_b = directory / f"{reviewer_id}_pass_b.json"
    pass_a.write_text(json.dumps(_response(reviewer_id, "A", changes=changes), indent=2) + "\n", encoding="utf-8")
    pass_b.write_text(json.dumps(_response(reviewer_id, "B", changes=changes), indent=2) + "\n", encoding="utf-8")
    return pass_a, pass_b


def _fresh_database(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for event_id in CALIBRATION_EVENT_IDS:
        for relative in expected_panel_paths(event_id):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"panel:{event_id}:{relative}".encode())
    database = tmp_path / "firepa_human_review.sqlite3"
    store = HumanReviewStore.from_frozen_round(db_path=database, root=root)
    store.close()
    return database


def test_control_packages_reuse_anonymized_panels_and_preserve_integrity(tmp_path: Path) -> None:
    before_integrity = integrity_snapshot(ROOT)
    before_sqlite = _sha256(DATABASE)
    output_root = tmp_path / "outputs"
    result = build_blind_control_packages(root=ROOT, output_root=output_root)
    after_integrity = integrity_snapshot(ROOT)
    after_sqlite = _sha256(DATABASE)

    assert result["status"] == "pass"
    assert result["protected_inputs_unchanged"] is True
    assert result["validation"]["status"] == "pass"
    assert before_integrity == after_integrity
    assert before_sqlite == after_sqlite

    for zip_path in (result["pass_a_zip"], result["pass_b_zip"]):
        assert Path(zip_path).is_file()
    with ZipFile(result["pass_a_zip"]) as archive_a, ZipFile(result["pass_b_zip"]) as archive_b:
        assert archive_a.namelist()[0:3] == [
            "LABELING_PROTOCOL_CANDIDATE_v1.md",
            "BLIND_CONTROL_R1_INSTRUCTIONS_PASS_A.md",
            "BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_A.json",
        ]
        assert len(archive_a.namelist()) == 12
        assert len(archive_b.namelist()) == 12
        for archive in (archive_a, archive_b):
            for name in archive.namelist():
                payload = archive.read(name)
                assert b"2026" not in payload
                if name != "LABELING_PROTOCOL_CANDIDATE_v1.md":
                    lowered = payload.lower()
                    assert b"event_id" not in lowered
                    assert b"significant_burn" not in lowered
                    assert b"ground_truth" not in lowered
                    assert b"sqlite" not in lowered


def test_control_package_generation_is_deterministic(tmp_path: Path) -> None:
    first = build_blind_control_packages(root=ROOT, output_root=tmp_path / "first")
    second = build_blind_control_packages(root=ROOT, output_root=tmp_path / "second")
    assert Path(first["pass_a_zip"]).read_bytes() == Path(second["pass_a_zip"]).read_bytes()
    assert Path(first["pass_b_zip"]).read_bytes() == Path(second["pass_b_zip"]).read_bytes()


def test_candidate_enums_and_triage_do_not_parse_notes() -> None:
    assert "cloud_or_haze" not in COMPETING_LAND_CHANGE_CODES
    assert set(OBSERVATION_LIMITATION_CODES) >= {"none", "cloud_or_haze", "mask_or_nodata"}
    soil_case = {
        "pass_a_visible_burn_scar": "yes",
        "pass_a_scar_confidence": "medium",
        "pass_a_event_association": "likely",
        "pass_a_competing_land_change": "soil_exposure",
        "observation_limitation": "none",
        "pass_a_notes": "cloud haze mask wording must not control triage",
        "pass_b_mode_agreement": "partially_agree",
        "pass_b_confidence_after": "medium",
        "pass_b_requires_adjudication": False,
    }
    triage = derive_control_triage(soil_case)
    assert triage["needs_adjudication"] is False
    assert triage["expert_review_priority"] == "recommended"
    assert triage["expert_review_reasons"] == ["competing_land_change=soil_exposure"]
    limited = {**soil_case, "observation_limitation": "cloud_or_haze"}
    assert derive_control_triage(limited)["expert_review_priority"] == "required"


def test_reviewer_provenance_rules() -> None:
    assert validate_reviewer_provenance("ai_assisted", "not_applicable", "model") == []
    assert validate_reviewer_provenance("ai_assisted", "trained", "model")
    assert validate_reviewer_provenance("human", "not_applicable", "")
    assert validate_reviewer_provenance("human", "domain_expert", "model")


def test_control_import_keeps_reviewers_separate_and_derives_case_007_priority(tmp_path: Path) -> None:
    reviewer_a = _write_pair(tmp_path, "blind_control_r1_reviewer_a")
    reviewer_b = _write_pair(tmp_path, "blind_control_r1_reviewer_b", changes={"CASE-007": {"competitor": "soil_exposure"}})
    result = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], dry_run=True
    )
    assert result["status"] == "pass"
    assert result["reviewer_ids"] == ["blind_control_r1_reviewer_a", "blind_control_r1_reviewer_b"]
    assert len(result["reviewers"]) == 2
    assert result["sqlite_written"] is False
    reviewer_b_cases = next(
        item for item in result["reviewers"] if item["reviewer_id"] == "blind_control_r1_reviewer_b"
    )["cases"]
    case_007 = next(item for item in reviewer_b_cases if item["case_id"] == "CASE-007")
    assert case_007["expert_review_priority"] == "recommended"
    assert case_007["expert_review_reasons"] == ["competing_land_change=soil_exposure"]
    assert "expert_review_priority" not in _response("reviewer_a", "A")["reviews"][0]


def test_control_import_rejects_duplicate_reviewers_and_pass_a_rewrite(tmp_path: Path) -> None:
    reviewer_a = _write_pair(tmp_path / "a", "same-reviewer")
    reviewer_b = _write_pair(tmp_path / "b", "same-reviewer")
    duplicate = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], dry_run=True
    )
    assert duplicate["status"] == "fail"
    assert any("duplicate reviewer_id" in error for error in duplicate["errors"])

    rewrite_dir = tmp_path / "rewrite"
    pass_a, pass_b = _write_pair(rewrite_dir, "reviewer-bad")
    payload = json.loads(pass_b.read_text(encoding="utf-8"))
    payload["reviews"][0]["pass_a_notes"] = "rewritten in Pass B"
    pass_b.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    other = _write_pair(tmp_path / "other", "reviewer-other")
    rewritten = import_blind_control_results(pass_a, pass_b, other[0], other[1], dry_run=True)
    assert rewritten["status"] == "fail"
    assert any("rewrites Pass A field pass_a_notes" in error for error in rewritten["errors"])


def test_control_import_rejects_free_form_derived_fields(tmp_path: Path) -> None:
    pair_a = _write_pair(tmp_path / "a", "reviewer-a")
    pair_b = _write_pair(tmp_path / "b", "reviewer-b")
    payload = json.loads(pair_a[0].read_text(encoding="utf-8"))
    payload["reviews"][0]["expert_review_priority"] = "required"
    pair_a[0].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    result = import_blind_control_results(pair_a[0], pair_a[1], pair_b[0], pair_b[1], dry_run=True)
    assert result["status"] == "fail"
    assert any("expert_review_priority" in error for error in result["errors"])


def test_control_comparator_reports_disagreements_without_performance_metrics(tmp_path: Path) -> None:
    reviewer_a = _write_pair(tmp_path / "a", "blind_control_r1_reviewer_a")
    reviewer_b = _write_pair(
        tmp_path / "b",
        "blind_control_r1_reviewer_b",
        changes={
            "CASE-002": {
                "visible": "ambiguous",
                "confidence": "low",
                "competitor": "soil_exposure",
                "limitation": "cloud_or_haze",
            }
        },
    )
    result = compare_blind_control_results(reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1])
    assert result["status"] == "pass"
    assert result["exact_agreement_by_field"]["pass_a_scar_confidence"] == {"agree": 6, "disagree": 1}
    assert result["exact_agreement_by_field"]["observation_limitation"] == {"agree": 6, "disagree": 1}
    assert result["confounder_differences"][0]["case_id"] == "CASE-002"
    assert result["observation_limitation_differences"][0]["case_id"] == "CASE-002"
    assert result["both_consider_ambiguous"] == []
    assert "accuracy" in result["performance_metrics_not_calculated"]
    serialized = json.dumps(result).lower()
    assert "ground_truth" not in serialized
    assert "significant_burn" not in serialized


def test_control_import_is_separate_audited_and_idempotent(tmp_path: Path) -> None:
    database = _fresh_database(tmp_path)
    before_connection = sqlite3.connect(database)
    try:
        r1_before = before_connection.execute("SELECT COUNT(*) FROM reviews WHERE round_id = 'round1'").fetchone()[0]
    finally:
        before_connection.close()
    reviewer_a = _write_pair(tmp_path / "a", "blind_control_r1_reviewer_a")
    reviewer_b = _write_pair(tmp_path / "b", "blind_control_r1_reviewer_b")
    first = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], dry_run=False, database=database, root=ROOT
    )
    assert first["status"] == "pass"
    assert first["inserted"] == 14
    assert first["r1_protected_rows_unchanged"] is True
    assert first["sqlite_changed"] is True
    second = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], dry_run=False, database=database, root=ROOT
    )
    assert second["status"] == "pass"
    assert second["inserted"] == 0
    assert second["unchanged"] == 14
    assert second["sqlite_changed"] is False
    connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
        counts = connection.execute(
            "SELECT reviewer_id, COUNT(*) FROM reviews WHERE round_id = 'control_r1' GROUP BY reviewer_id ORDER BY reviewer_id"
        ).fetchall()
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE round_id = 'control_r1' AND action = 'import_blind_control_r1'"
        ).fetchone()[0]
        r1_count = connection.execute("SELECT COUNT(*) FROM reviews WHERE round_id = 'round1'").fetchone()[0]
    finally:
        connection.close()
    assert {"reviewer_model", "reviewer_expertise", "observation_limitation"}.issubset(columns)
    assert counts == [("blind_control_r1_reviewer_a", 7), ("blind_control_r1_reviewer_b", 7)]
    assert audit_count == 14 * 15
    assert r1_count == r1_before


def test_control_import_rejects_conflict_without_overwriting_existing_rows(tmp_path: Path) -> None:
    database = _fresh_database(tmp_path)
    reviewer_a = _write_pair(tmp_path / "a", "blind_control_r1_reviewer_a")
    reviewer_b = _write_pair(tmp_path / "b", "blind_control_r1_reviewer_b")
    imported = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], database=database, root=ROOT
    )
    assert imported["status"] == "pass"
    before = _sha256(database)
    conflicting_a = _write_pair(
        tmp_path / "conflict-a",
        "blind_control_r1_reviewer_a",
        changes={"CASE-001": {"visible": "ambiguous"}},
    )
    rejected = import_blind_control_results(
        conflicting_a[0], conflicting_a[1], reviewer_b[0], reviewer_b[1], database=database, root=ROOT
    )
    assert rejected["status"] == "fail"
    assert any("Existing control review conflicts" in error for error in rejected["errors"])
    assert _sha256(database) == before


def test_control_comparison_is_read_only_and_reconciles_sqlite(tmp_path: Path) -> None:
    database = _fresh_database(tmp_path)
    reviewer_a = _write_pair(tmp_path / "a", "blind_control_r1_reviewer_a")
    reviewer_b = _write_pair(tmp_path / "b", "blind_control_r1_reviewer_b")
    imported = import_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], database=database, root=ROOT
    )
    assert imported["status"] == "pass"
    before = _sha256(database)
    compared = compare_blind_control_results(
        reviewer_a[0], reviewer_a[1], reviewer_b[0], reviewer_b[1], database=database
    )
    after = _sha256(database)
    assert compared["status"] == "pass"
    assert compared["sqlite_read_only"] is True
    assert compared["sqlite_rows_match_validated_input"] is True
    assert compared["sqlite_errors"] == []
    assert before == after
