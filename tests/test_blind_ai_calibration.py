from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from fuegopa.blind_ai_calibration import (
    AI_LABEL_STATUS,
    AI_REVIEWER_ID,
    AI_REVIEWER_TYPE,
    BLIND_PROTOCOL_VERSION,
    BLIND_ROUND_ID,
    CASE_IDS,
    CASE_MAPPING,
    PASS_A_FILES,
    PASS_B_FILES,
    build_blind_packages,
    import_blind_results,
    validate_blind_packages,
)
from fuegopa.human_review_schema import CALIBRATION_ROUND
from fuegopa.human_review_store import HumanReviewStore


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def generated_packages(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    output_root = tmp_path_factory.mktemp("blind-ai-packages")
    result = build_blind_packages(root=ROOT, output_root=output_root)
    assert result["status"] == "pass"
    return output_root, result


def _response_payload(pass_name: str) -> dict:
    reviews = []
    for case_id in CASE_IDS:
        review = {
            "case_id": case_id,
            "pass_a_visible_burn_scar": "ambiguous",
            "pass_a_scar_confidence": "medium",
            "pass_a_event_association": "possible",
            "pass_a_competing_land_change": "unknown",
            "pass_a_notes": f"Conservative calibration note for {case_id}.",
        }
        if pass_name == "B":
            review.update(
                {
                    "pass_b_mode_agreement": "partially_agree",
                    "pass_b_confidence_after": "low",
                    "pass_b_requires_adjudication": False,
                    "pass_b_notes": f"Temporal comparison note for {case_id}.",
                }
            )
        reviews.append(review)
    return {
        "reviewer_id": AI_REVIEWER_ID,
        "reviewer_type": AI_REVIEWER_TYPE,
        "label_status": AI_LABEL_STATUS,
        "protocol_version": BLIND_PROTOCOL_VERSION,
        "round_id": BLIND_ROUND_ID,
        "reviews": reviews,
    }


def _write_responses(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pass_a = directory / "pass_a.json"
    pass_b = directory / "pass_b.json"
    pass_a.write_text(json.dumps(_response_payload("A"), indent=2) + "\n", encoding="utf-8")
    pass_b.write_text(json.dumps(_response_payload("B"), indent=2) + "\n", encoding="utf-8")
    return pass_a, pass_b


def test_case_mapping_and_public_package_contract(generated_packages: tuple[Path, dict]) -> None:
    output_root, result = generated_packages
    assert tuple(row[0] for row in CASE_MAPPING) == CASE_IDS
    assert result["validation"]["status"] == "pass"
    assert (output_root / "firepa_blind_ai_calibration_r1_pass_a.zip").is_file()
    assert (output_root / "firepa_blind_ai_calibration_r1_pass_b.zip").is_file()

    for pass_name, filenames in (("pass_a", PASS_A_FILES), ("pass_b", PASS_B_FILES)):
        directory = output_root / f"human_review/blind_ai_calibration_r1/{pass_name}"
        assert tuple(sorted(path.name for path in directory.iterdir())) == tuple(sorted(filenames))
        for path in directory.iterdir():
            payload = path.read_bytes()
            assert b"2026" not in payload
            assert b"event-r1500_t06-" not in payload
            assert b"Users" not in payload
            if path.suffix == ".json":
                assert b"significant_burn" not in payload
        zip_path = output_root / f"firepa_blind_ai_calibration_r1_{pass_name}.zip"
        with ZipFile(zip_path) as archive:
            assert archive.namelist() == list(filenames)

    mapping_path = output_root / "human_review/private/calibration_r1_case_map.csv"
    with mapping_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["case_id"] for row in rows] == list(CASE_IDS)
    assert all(row["event_id"].startswith("event-r1500_t06-") for row in rows)


def test_generation_is_deterministic(generated_packages: tuple[Path, dict], tmp_path_factory: pytest.TempPathFactory) -> None:
    first_root, _ = generated_packages
    second_root = tmp_path_factory.mktemp("blind-ai-packages-repeat")
    build_blind_packages(root=ROOT, output_root=second_root)
    relative_files = [
        Path("firepa_blind_ai_calibration_r1_pass_a.zip"),
        Path("firepa_blind_ai_calibration_r1_pass_b.zip"),
        Path("human_review/private/calibration_r1_case_map.csv"),
    ]
    relative_files.extend(Path("human_review/blind_ai_calibration_r1/pass_a") / filename for filename in PASS_A_FILES)
    relative_files.extend(Path("human_review/blind_ai_calibration_r1/pass_b") / filename for filename in PASS_B_FILES)
    for relative in relative_files:
        assert (first_root / relative).read_bytes() == (second_root / relative).read_bytes()


def test_importer_dry_run_and_idempotence(generated_packages: tuple[Path, dict], tmp_path: Path) -> None:
    output_root, _ = generated_packages
    pass_a, pass_b = _write_responses(tmp_path / "responses")
    database = tmp_path / "firepa_human_review.sqlite3"
    dry_run = import_blind_results(
        pass_a,
        pass_b,
        root=ROOT,
        output_root=output_root,
        dry_run=True,
        database=database,
        report=tmp_path / "dry-run.json",
    )
    assert dry_run["status"] == "pass"
    assert dry_run["inserted"] == 7
    assert dry_run["database_written"] is False
    assert not database.exists()

    with HumanReviewStore.from_frozen_round(database, root=ROOT) as store:
        first_item = store.list_items()[0]
        human = store.save_pass_a(
            round_id=CALIBRATION_ROUND,
            event_id=first_item["event_id"],
            reviewer_id="human-reviewer",
            pass_a_visible_burn_scar="ambiguous",
            pass_a_scar_confidence="medium",
            pass_a_event_association="possible",
            pass_a_competing_land_change="unknown",
            pass_a_notes="Human observation is retained.",
        )
        assert human["reviewer_type"] == "human"
        assert human["label_status"] == "human_observation"

    imported = import_blind_results(
        pass_a,
        pass_b,
        root=ROOT,
        output_root=output_root,
        database=database,
    )
    assert imported["status"] == "pass"
    assert imported["inserted"] == 7
    assert imported["human_rows_preserved"] == 1

    repeated = import_blind_results(
        pass_a,
        pass_b,
        root=ROOT,
        output_root=output_root,
        database=database,
    )
    assert repeated["status"] == "pass"
    assert repeated["inserted"] == 0
    assert repeated["unchanged"] == 7
    with HumanReviewStore(database) as store:
        first_event = store.list_items()[0]["event_id"]
        retained = store.get_review(CALIBRATION_ROUND, first_event, "human-reviewer")
        ai_review = store.get_review(CALIBRATION_ROUND, first_event, AI_REVIEWER_ID)
        audit_count = store.connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = ?",
            ("import_blind_ai_calibration",),
        ).fetchone()[0]
    assert retained is not None
    assert retained["pass_a_notes"] == "Human observation is retained."
    assert ai_review is not None
    assert ai_review["reviewer_type"] == "ai_assisted"
    assert ai_review["label_status"] == "provisional_pseudolabel"
    assert audit_count == 84


def test_importer_rejects_extra_source_fields(generated_packages: tuple[Path, dict], tmp_path: Path) -> None:
    output_root, _ = generated_packages
    pass_a, pass_b = _write_responses(tmp_path / "responses")
    invalid = json.loads(pass_a.read_text(encoding="utf-8"))
    invalid["reviews"][0]["event_id"] = "event-r1500_t06-0ddd477d24b1364d"
    invalid_path = tmp_path / "invalid_a.json"
    invalid_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
    result = import_blind_results(invalid_path, pass_b, root=ROOT, output_root=output_root, dry_run=True)
    assert result["status"] == "fail"
    assert any("event_id" in error for error in result["errors"])


def test_direct_validation_of_generated_packages(generated_packages: tuple[Path, dict]) -> None:
    output_root, _ = generated_packages
    validation = validate_blind_packages(ROOT, output_root=output_root)
    assert validation["status"] == "pass"
    assert validation["errors"] == []
