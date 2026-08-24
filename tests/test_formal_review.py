from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from fuegopa.formal_review import (
    ASSOCIATION_CODES,
    CONFIDENCE_CODES,
    FORMAL_PROTOCOL_PATH,
    FORMAL_ROUND_ID,
    LIMITATION_CODES,
    MODE_CODES,
    REQUEST_REASON_CODES,
    SURFACE_CODES,
    VISIBLE_CODES,
    FormalReviewError,
    FormalReviewStore,
    build_pairwise_comparison,
    build_slot_assignments,
    derive_formal_triage,
    export_formal_preparation,
    load_formal_inputs,
    prepare_formal_round,
    sha256_file,
    validate_formal_provenance,
)
from fuegopa.human_review_migrations import CURRENT_MIGRATION_VERSION


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FORMAL_QUEUE = ROOT / "outputs/sentinel2_dnbr_review_queue.csv"
PRIVATE_FORMAL_UNOBSERVED = ROOT / "outputs/human_review/unobserved_events.csv"
requires_private_formal_inputs = pytest.mark.skipif(
    not (PRIVATE_FORMAL_QUEUE.is_file() and PRIVATE_FORMAL_UNOBSERVED.is_file()),
    reason="protected formal-review queue and unobserved-case table are not redistributed",
)


def _review(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "visible_burn_scar": "no",
        "scar_confidence": "medium",
        "event_association": "unlikely",
        "competing_land_change": "none_visible",
        "observation_limitation": "none",
        "mode_agreement": "agree",
        "confidence_after": "medium",
        "reviewer_requested_adjudication": False,
        "request_reason": None,
        "notes": "",
    }
    row.update(overrides)
    return row


def _prepared(tmp_path: Path) -> tuple[Path, Path, object]:
    if not (PRIVATE_FORMAL_QUEUE.is_file() and PRIVATE_FORMAL_UNOBSERVED.is_file()):
        pytest.skip("protected formal-review inputs are not redistributed")
    database = tmp_path / "formal.sqlite3"
    output = tmp_path / "formal_packages"
    seed = tmp_path / "private_seed.txt"
    result = prepare_formal_round(
        root=ROOT,
        db_path=database,
        output_dir=output,
        seed_path=seed,
        supplied_seed="test-seed-formal-review-20260728",
        base_head="f302139",
    )
    return database, output, result


def test_protocol_v1_is_frozen_and_hash_is_deterministic():
    payload = FORMAL_PROTOCOL_PATH.read_bytes()
    assert FORMAL_PROTOCOL_PATH.is_file()
    assert b"labeling-protocol-v1" in payload
    assert b"Fecha de freeze" in payload
    assert hashlib.sha256(payload).hexdigest() == sha256_file(FORMAL_PROTOCOL_PATH)
    assert sha256_file(FORMAL_PROTOCOL_PATH) == sha256_file(FORMAL_PROTOCOL_PATH)


def test_formal_enums_are_explicit_and_invalid_values_are_rejected():
    assert VISIBLE_CODES == ("yes", "no", "ambiguous")
    assert CONFIDENCE_CODES == ("high", "medium", "low")
    assert MODE_CODES == ("agree", "partially_agree", "disagree")
    assert "shadow" in LIMITATION_CODES
    assert "insufficient_temporal_separation" in LIMITATION_CODES
    assert "other" in LIMITATION_CODES
    assert "agriculture_or_harvest" in SURFACE_CODES
    assert "other_structured" in REQUEST_REASON_CODES


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reviewer_type": "human", "reviewer_expertise": "not_applicable", "label_status": "human_observation"},
        {"reviewer_type": "human", "reviewer_expertise": "domain_expert", "model_name": "model", "label_status": "human_observation"},
        {"reviewer_type": "ai_assisted", "reviewer_expertise": "not_applicable", "label_status": "provisional_pseudolabel"},
        {"reviewer_type": "ai_assisted", "reviewer_expertise": "not_applicable", "model_name": "m", "model_version": "1", "label_status": "human_observation"},
    ],
)
def test_provenance_rejects_invalid_human_ai_separation(kwargs):
    assert validate_formal_provenance(**kwargs)


def test_provenance_accepts_distinct_human_and_ai_contracts():
    assert validate_formal_provenance(
        reviewer_type="human",
        reviewer_expertise="protocol_trained_reviewer",
        label_status="human_observation",
    ) == []
    assert validate_formal_provenance(
        reviewer_type="ai_assisted",
        reviewer_expertise="not_applicable",
        model_name="model",
        model_version="v1",
        label_status="provisional_pseudolabel",
    ) == []


def test_triage_uses_structured_fields_not_notes():
    plain = derive_formal_triage(_review())
    noisy = derive_formal_triage(_review(notes="cloud agriculture expert adjudication"))
    assert noisy == plain
    assert plain["needs_adjudication"] is False
    assert plain["expert_review_priority"] == "none"


def test_triage_triggers_and_recommended_required_are_separate():
    assert derive_formal_triage(_review(visible_burn_scar="ambiguous"))["needs_adjudication"] is True
    assert derive_formal_triage(_review(scar_confidence="low"))["needs_adjudication"] is True
    assert derive_formal_triage(_review(event_association="indeterminate"))["needs_adjudication"] is True
    assert derive_formal_triage(_review(mode_agreement="disagree"))["needs_adjudication"] is True
    assert derive_formal_triage(_review(mode_agreement="partially_agree"))["needs_adjudication"] is False
    agriculture = derive_formal_triage(_review(competing_land_change="agriculture_or_harvest"))
    assert agriculture["needs_adjudication"] is False
    assert agriculture["expert_review_priority"] == "recommended"
    adjudicated = derive_formal_triage(
        _review(competing_land_change="agriculture_or_harvest"),
        adjudication={
            "resolution_status": "complete",
            "material_disagreement_resolved": False,
            "specialist_question_code": "SPECIALIST_SURFACE_PROCESS",
        },
    )
    assert adjudicated["expert_review_priority"] == "required"
    assert adjudicated["administrative_status"] == "pending_expert_review"


def test_pairwise_comparison_keeps_both_sides_and_no_consensus():
    left = _review(visible_burn_scar="yes", event_association="likely", mode_agreement="partially_agree")
    right = _review(visible_burn_scar="ambiguous", event_association="indeterminate", mode_agreement="disagree")
    comparison = build_pairwise_comparison(left, right)
    assert comparison["needs_adjudication"] is True
    assert "visible_burn_scar" in comparison["material_disagreements"]
    assert "event_association" in comparison["material_disagreements"]
    assert comparison["consensus"] is None


def test_r1_regression_cases_are_structured_and_not_majority_resolved():
    case_007_a = _review(visible_burn_scar="yes", scar_confidence="medium", event_association="possible", competing_land_change="urban_or_construction", mode_agreement="partially_agree")
    case_007_b = _review(visible_burn_scar="ambiguous", scar_confidence="low", event_association="indeterminate", competing_land_change="mixed", mode_agreement="disagree", reviewer_requested_adjudication=True, request_reason="mode_disagreement")
    triage_007 = derive_formal_triage(case_007_a, peer_review=case_007_b)
    assert triage_007["needs_adjudication"] is True
    assert triage_007["expert_review_priority"] == "recommended"
    assert build_pairwise_comparison(case_007_a, case_007_b)["consensus"] is None

    case_005_a = _review(visible_burn_scar="ambiguous", event_association="indeterminate", competing_land_change="mixed", mode_agreement="disagree", reviewer_requested_adjudication=True, request_reason="association_disagreement")
    case_005_b = _review(visible_burn_scar="ambiguous", scar_confidence="low", event_association="possible", competing_land_change="mixed", mode_agreement="partially_agree")
    triage_005 = derive_formal_triage(case_005_a, peer_review=case_005_b)
    assert triage_005["needs_adjudication"] is True
    assert triage_005["expert_review_priority"] == "recommended"

    case_006 = _review(visible_burn_scar="no", event_association="unlikely", competing_land_change="agriculture_or_harvest")
    case_006_peer = _review(visible_burn_scar="no", scar_confidence="high", event_association="unlikely", competing_land_change="agriculture_or_harvest")
    triage_006 = derive_formal_triage(case_006, peer_review=case_006_peer)
    assert triage_006["needs_adjudication"] is False
    assert triage_006["expert_review_priority"] == "recommended"


@requires_private_formal_inputs
def test_real_formal_cohort_is_exactly_28_plus_2_and_has_no_2026():
    events, unobserved = load_formal_inputs(root=ROOT)
    assert len(events) == 28
    assert len({item["event_id"] for item in events}) == 28
    assert len(unobserved) == 2
    assert {item["event_id"] for item in events}.isdisjoint(item["event_id"] for item in unobserved)
    assert all("2026" not in json.dumps(item, ensure_ascii=False) for item in events + unobserved)


def test_slot_order_is_stable_private_and_differs_by_slot_and_seed():
    events = [
        {"event_id": f"event-{index}", "quicklook_path": f"panel-{index}.png", "quicklook_sha256": f"hash-{index}"}
        for index in range(5)
    ]
    first = build_slot_assignments(events, slot_id="HUMAN_SLOT_A", private_seed="seed-1234567890")
    second = build_slot_assignments(events, slot_id="HUMAN_SLOT_A", private_seed="seed-1234567890")
    other_slot = build_slot_assignments(events, slot_id="HUMAN_SLOT_B", private_seed="seed-1234567890")
    other_seed = build_slot_assignments(events, slot_id="HUMAN_SLOT_A", private_seed="seed-0987654321")
    assert first == second
    assert [item["event_id"] for item in first] != [item["event_id"] for item in other_slot]
    assert [item["event_id"] for item in first] != [item["event_id"] for item in other_seed]
    assert all(item["event_id"] not in item["blind_alias"] for item in first)


def test_prepare_formal_round_creates_56_empty_assignments_and_is_idempotent(tmp_path: Path):
    database, output, result = _prepared(tmp_path)
    assert result.observable_count == 28
    assert result.unobserved_count == 2
    assert result.assignment_count == 56
    public_payloads = []
    for slot in ("human_slot_a", "human_slot_b"):
        path = output / slot / "manifest.json"
        payload = path.read_text(encoding="utf-8")
        public_payloads.append(payload)
        assert "event_id" not in payload.lower()
        for forbidden in ("frp", "rank", "score", "predicted_class", "significant_burn", "target", "ground_truth", "severity"):
            assert forbidden not in payload.lower()
    assert public_payloads[0] != public_payloads[1]
    with FormalReviewStore(database) as store:
        store.initialize()
        assert store.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == CURRENT_MIGRATION_VERSION
        assert store.connection.execute("SELECT COUNT(*) FROM formal_assignments").fetchone()[0] == 56
        assert store.connection.execute("SELECT COUNT(*) FROM formal_unobserved_events").fetchone()[0] == 2
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_a").fetchone()[0] == 0
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_b").fetchone()[0] == 0
        assert store.connection.execute("SELECT execution_status FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0] == "not_started"
    before_hashes = {path: sha256_file(path) for path in (output / "human_slot_a" / "manifest.json", output / "human_slot_b" / "manifest.json")}
    again = prepare_formal_round(
        root=ROOT,
        db_path=database,
        output_dir=output,
        seed_path=tmp_path / "private_seed.txt",
        supplied_seed="test-seed-formal-review-20260728",
        base_head="f302139",
    )
    assert again.as_dict() == result.as_dict()
    assert before_hashes == {path: sha256_file(path) for path in before_hashes}


def test_public_package_has_no_private_join_and_unobserved_are_not_assignments(tmp_path: Path):
    database, output, _ = _prepared(tmp_path)
    private_map = json.loads((output / "private" / "assignment_map.json").read_text(encoding="utf-8"))
    assert all(item.get("event_id") for values in private_map["items"].values() for item in values)
    for slot in ("human_slot_a", "human_slot_b"):
        public = json.loads((output / slot / "manifest.json").read_text(encoding="utf-8"))
        assert all("event_id" not in item for item in public["items"])
    with FormalReviewStore(database) as store:
        store.initialize()
        assigned = {row[0] for row in store.connection.execute("SELECT event_id FROM formal_assignments")}
        excluded = {row[0] for row in store.connection.execute("SELECT event_id FROM formal_unobserved_events")}
        assert assigned.isdisjoint(excluded)


def test_migration_is_cumulative_and_audit_is_append_only(tmp_path: Path):
    database, _, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        tables = {row[0] for row in store.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"formal_review_rounds", "formal_review_slots", "formal_assignments", "formal_pass_a", "formal_pass_b", "formal_pairwise_comparisons", "formal_triage", "formal_adjudications", "formal_expert_reviews", "formal_unobserved_events", "formal_package_manifests", "formal_input_manifests", "formal_audit_log", "formal_amendments"}.issubset(tables)
        audit_id = store.connection.execute("SELECT MIN(audit_id) FROM formal_audit_log").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.connection.execute("UPDATE formal_audit_log SET reason = 'changed' WHERE audit_id = ?", (audit_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.connection.execute("DELETE FROM formal_audit_log WHERE audit_id = ?", (audit_id,))


def test_profile_binding_and_pass_a_b_contract(tmp_path: Path):
    database, _, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        store.register_human_profile("human-a", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        store.bind_slot(FORMAL_ROUND_ID, "HUMAN_SLOT_A", "human-a")
        store.connection.execute("UPDATE formal_review_rounds SET execution_authorized = 1 WHERE round_id = ?", (FORMAL_ROUND_ID,))
        store.connection.commit()
        assignment = store.list_assignments(FORMAL_ROUND_ID, "HUMAN_SLOT_A")[0]
        event_id = assignment["event_id"]
        with pytest.raises(sqlite3.IntegrityError, match="requires locked formal_pass_a"):
            store.connection.execute(
                """
                INSERT INTO formal_pass_b
                  (round_id, slot_id, event_id, assignment_id, profile_id, mode_agreement,
                   confidence_after, reviewer_requested_adjudication, payload_sha256,
                   saved_at, created_at, updated_at)
                VALUES (?, 'HUMAN_SLOT_A', ?, ?, 'human-a', 'agree', 'high', 0, 'hash', 't', 't', 't')
                """,
                (FORMAL_ROUND_ID, event_id, assignment["assignment_id"]),
            )
        with pytest.raises(FormalReviewError, match="requiere Pass A"):
            store.save_pass_b(
                round_id=FORMAL_ROUND_ID,
                slot_id="HUMAN_SLOT_A",
                event_id=event_id,
                mode_agreement="agree",
                confidence_after="high",
                reviewer_requested_adjudication=False,
            )
        saved_a = store.save_pass_a(
            round_id=FORMAL_ROUND_ID,
            slot_id="HUMAN_SLOT_A",
            event_id=event_id,
            visible_burn_scar="ambiguous",
            scar_confidence="medium",
            event_association="possible",
            competing_land_change="mixed",
            observation_limitation="none",
            notes="free text with agriculture and expert does not derive triage",
        )
        with pytest.raises(FormalReviewError, match="bloqueada"):
            store.save_pass_a(
                round_id=FORMAL_ROUND_ID,
                slot_id="HUMAN_SLOT_A",
                event_id=event_id,
                visible_burn_scar="no",
                scar_confidence="high",
                event_association="unlikely",
                competing_land_change="none_visible",
                observation_limitation="none",
            )
        current_a = store.get_pass_a(FORMAL_ROUND_ID, "HUMAN_SLOT_A", event_id)
        assert current_a["visible_burn_scar"] == saved_a["visible_burn_scar"]
        assert current_a["scar_confidence"] == saved_a["scar_confidence"]
        with pytest.raises(FormalReviewError, match="selected_pair_reference"):
            store.save_pass_b(
                round_id=FORMAL_ROUND_ID,
                slot_id="HUMAN_SLOT_A",
                event_id=event_id,
                mode_agreement="partially_agree",
                confidence_after="low",
                reviewer_requested_adjudication=True,
                request_reason="ambiguous_observation",
                notes="temporal note",
            )
        with pytest.raises(sqlite3.IntegrityError, match="specific amendment"):
            store.connection.execute(
                "UPDATE formal_pass_a SET notes = 'direct overwrite' WHERE round_id = ? AND slot_id = ? AND event_id = ?",
                (FORMAL_ROUND_ID, "HUMAN_SLOT_A", event_id),
            )
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_a").fetchone()[0] == 1
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_b").fetchone()[0] == 0
        amended = store.save_pass_a(
            round_id=FORMAL_ROUND_ID,
            slot_id="HUMAN_SLOT_A",
            event_id=event_id,
            visible_burn_scar="yes",
            scar_confidence="high",
            event_association="likely",
            competing_land_change="none_visible",
            observation_limitation="none",
            amend=True,
            amendment_reason="Corrección administrativa explícita",
        )
        assert amended["revision"] == 2
        assert store.connection.execute("SELECT COUNT(*) FROM formal_amendments").fetchone()[0] == 1


def test_formal_schema_has_no_prohibited_scientific_table_or_column_names(tmp_path: Path):
    database, _, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        schema_text = "\n".join(str(row[0]) for row in store.connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
        lowered = schema_text.lower()
        for prohibited in ("ground_truth", "significant_burn", "confirmed_fire"):
            assert prohibited not in lowered


def test_preparation_export_is_utf8_empty_and_does_not_create_review_rows(tmp_path: Path):
    database, _, _ = _prepared(tmp_path)
    paths = export_formal_preparation(db_path=database, output_dir=tmp_path / "exports")
    assert set(paths) == {"csv", "json", "jsonl"}
    csv_text = paths["csv"].read_text(encoding="utf-8")
    assert "blind_alias" in csv_text
    assert "event_id" not in csv_text
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["review_rows_exported"] == 0
    assert payload["assignment_count"] == 56
    with FormalReviewStore(database) as store:
        store.initialize()
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_a").fetchone()[0] == 0
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_b").fetchone()[0] == 0


def test_preparation_detects_changed_input_identity_without_overwrite(tmp_path: Path):
    database, output, _ = _prepared(tmp_path)
    changed_queue = tmp_path / "queue.csv"
    original = (ROOT / "outputs/sentinel2_dnbr_review_queue.csv").read_text(encoding="utf-8")
    changed_queue.write_text(original.replace("principal", "principal_changed", 1), encoding="utf-8")
    with pytest.raises(FormalReviewError, match="no coincide"):
        prepare_formal_round(
            root=ROOT,
            db_path=database,
            queue_path=changed_queue,
            output_dir=output,
            seed_path=tmp_path / "private_seed.txt",
            supplied_seed="test-seed-formal-review-20260728",
            base_head="f302139",
        )
