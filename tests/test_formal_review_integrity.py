from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from fuegopa.formal_review import (
    FORMAL_PROTOCOL_PATH,
    FORMAL_ROUND_ID,
    PROTOCOL_HASH_RECONCILIATION_REASON,
    STALE_PROTOCOL_SHA256,
    FormalReviewError,
    FormalReviewStore,
    build_slot_assignments,
    prepare_formal_round,
    sha256_file,
    verify_formal_review_round,
)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FORMAL_QUEUE = ROOT / "outputs/sentinel2_dnbr_review_queue.csv"
PRIVATE_FORMAL_UNOBSERVED = ROOT / "outputs/human_review/unobserved_events.csv"


def _prepared(tmp_path: Path, *, seed_inside_output: bool = False) -> tuple[Path, Path]:
    if not (PRIVATE_FORMAL_QUEUE.is_file() and PRIVATE_FORMAL_UNOBSERVED.is_file()):
        pytest.skip("protected formal-review inputs are not redistributed")
    database = tmp_path / "formal.sqlite3"
    output = tmp_path / "formal_packages"
    kwargs = {"seed_path": None if seed_inside_output else tmp_path / "private_seed.txt"}
    prepare_formal_round(
        root=ROOT,
        db_path=database,
        output_dir=output,
        supplied_seed="test-seed-formal-review-20260728",
        base_head="f302139",
        **kwargs,
    )
    return database, output


def _authorize_slot(database: Path, slot_id: str = "HUMAN_SLOT_A", profile_id: str = "human-a") -> str:
    with FormalReviewStore(database) as store:
        store.initialize()
        store.register_human_profile(profile_id, "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        store.bind_slot(FORMAL_ROUND_ID, slot_id, profile_id)
        store.connection.execute(
            "UPDATE formal_review_rounds SET execution_authorized = 1 WHERE round_id = ?",
            (FORMAL_ROUND_ID,),
        )
        store.connection.commit()
        return store.list_assignments(FORMAL_ROUND_ID, slot_id)[0]["event_id"]


def test_profile_registration_is_insert_only_and_does_not_convert_ai(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        store.register_human_profile("human-a", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        store.register_human_profile("human-a", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        assert store.connection.execute("SELECT COUNT(*) FROM reviewer_profiles WHERE profile_id = 'human-a'").fetchone()[0] == 1
        with pytest.raises(FormalReviewError, match="Conflicto explícito"):
            store.register_human_profile("human-a", "domain_expert", training_version="labeling-protocol-v1")
        store.connection.execute(
            "INSERT INTO reviewer_profiles (profile_id, reviewer_type, reviewer_expertise, model_name, model_version, protocol_training_version, label_status, created_at, updated_at) VALUES ('ai-1', 'ai_assisted', 'not_applicable', 'model', 'v1', 'model-contract', 'provisional_pseudolabel', 't', 't')"
        )
        store.connection.commit()
        with pytest.raises(FormalReviewError, match="Conflicto explícito"):
            store.register_human_profile("ai-1", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute("UPDATE reviewer_profiles SET reviewer_type = 'human' WHERE profile_id = 'ai-1'")


def test_same_profile_cannot_bind_both_slots_and_exact_rerun_is_idempotent(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        store.register_human_profile("human-a", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        store.bind_slot(FORMAL_ROUND_ID, "HUMAN_SLOT_A", "human-a")
        store.bind_slot(FORMAL_ROUND_ID, "HUMAN_SLOT_A", "human-a")
        with pytest.raises(FormalReviewError, match="ambos slots"):
            store.bind_slot(FORMAL_ROUND_ID, "HUMAN_SLOT_B", "human-a")
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "UPDATE formal_review_slots SET profile_id = 'human-a', status = 'bound' WHERE round_id = ? AND slot_id = 'HUMAN_SLOT_B'",
                (FORMAL_ROUND_ID,),
            )


def test_round_and_assignment_identity_are_immutable(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        assignment = store.list_assignments(FORMAL_ROUND_ID, "HUMAN_SLOT_A")[0]
        with pytest.raises(sqlite3.IntegrityError, match="identity"):
            store.connection.execute(
                "UPDATE formal_assignments SET event_id = 'other-event' WHERE assignment_id = ?",
                (assignment["assignment_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.connection.execute("DELETE FROM formal_assignments WHERE assignment_id = ?", (assignment["assignment_id"],))
        with pytest.raises(sqlite3.IntegrityError, match="identity"):
            store.connection.execute(
                "UPDATE formal_review_rounds SET protocol_sha256 = 'other' WHERE round_id = ?",
                (FORMAL_ROUND_ID,),
            )


def test_execution_authorization_blocks_real_pass_a_and_pass_b_until_explicit_test_auth(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    with FormalReviewStore(database) as store:
        store.initialize()
        store.register_human_profile("human-a", "protocol_trained_reviewer", training_version="labeling-protocol-v1")
        store.bind_slot(FORMAL_ROUND_ID, "HUMAN_SLOT_A", "human-a")
        event_id = store.list_assignments(FORMAL_ROUND_ID, "HUMAN_SLOT_A")[0]["event_id"]
        with pytest.raises(FormalReviewError, match="autorizada"):
            store.save_pass_a(
                round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
                visible_burn_scar="no", scar_confidence="high", event_association="unlikely",
                competing_land_change="none_visible", observation_limitation="none",
            )
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_a").fetchone()[0] == 0


def test_pass_a_amendment_keeps_exact_payload_hashes_and_no_generic_update(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    event_id = _authorize_slot(database)
    with FormalReviewStore(database) as store:
        store.initialize()
        saved = store.save_pass_a(
            round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
            visible_burn_scar="ambiguous", scar_confidence="medium", event_association="possible",
            competing_land_change="mixed", observation_limitation="none", notes="observación",
        )
        with pytest.raises(sqlite3.IntegrityError, match="specific amendment"):
            store.connection.execute("UPDATE formal_pass_a SET notes = 'direct overwrite' WHERE event_id = ?", (event_id,))
        amended = store.save_pass_a(
            round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
            visible_burn_scar="yes", scar_confidence="high", event_association="likely",
            competing_land_change="none_visible", observation_limitation="none", amend=True,
            amendment_reason="Corrección administrativa específica",
        )
        amendment = store.connection.execute("SELECT * FROM formal_amendments WHERE event_id = ?", (event_id,)).fetchone()
        assert saved["revision"] == 1
        assert amended["revision"] == 2
        assert amendment["previous_payload_sha256"] == saved["payload_sha256"]
        assert amendment["corrected_payload_sha256"] == amended["payload_sha256"]
        assert "profile_id" not in amendment["previous_payload_json"]


def test_pass_b_requires_two_distinct_frozen_references_and_stays_blocked(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    event_id = _authorize_slot(database)
    with FormalReviewStore(database) as store:
        store.initialize()
        assignment = store.list_assignments(FORMAL_ROUND_ID, "HUMAN_SLOT_A")[0]
        store.save_pass_a(
            round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
            visible_burn_scar="no", scar_confidence="high", event_association="unlikely",
            competing_land_change="none_visible", observation_limitation="none",
        )
        with pytest.raises(FormalReviewError, match="window_median_reference"):
            store.save_pass_b(
                round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
                mode_agreement="agree", confidence_after="high", reviewer_requested_adjudication=False,
                selected_pair_reference={
                    "path": assignment["visual_input_reference"],
                    "sha256": assignment["visual_input_sha256"],
                    "manifest_sha256": assignment["visual_input_manifest_sha256"],
                    "mode": "selected_pair", "provenance": "formal_review_28_visual_inputs",
                },
            )
        assert store.connection.execute("SELECT COUNT(*) FROM formal_pass_b").fetchone()[0] == 0


def test_pass_b_valid_contract_stores_both_frozen_input_identities(tmp_path: Path):
    database, _ = _prepared(tmp_path)
    event_id = _authorize_slot(database)
    with FormalReviewStore(database) as store:
        store.initialize()
        assignment = store.list_assignments(FORMAL_ROUND_ID, "HUMAN_SLOT_A")[0]
        temporal_path = "outputs/human_review/formal_review_28/human_slot_b/manifest.json"
        temporal_sha = sha256_file(ROOT / temporal_path)
        temporal_manifest_sha = "window-manifest-v1"
        # This test simulates a future frozen temporal input in a temporary
        # database only; the real round has no such reference and remains blocked.
        store.connection.execute("DROP TRIGGER formal_assignments_identity_no_update")
        store.connection.execute(
            "UPDATE formal_assignments SET temporal_input_reference = ?, temporal_input_sha256 = ?, temporal_input_manifest_sha256 = ?, temporal_input_mode = 'window_median', temporal_input_provenance = 'frozen-temporal-test' WHERE event_id = ?",
            (temporal_path, temporal_sha, temporal_manifest_sha, event_id),
        )
        store.connection.commit()
        store.save_pass_a(
            round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
            visible_burn_scar="no", scar_confidence="high", event_association="unlikely",
            competing_land_change="none_visible", observation_limitation="none",
        )
        saved_b = store.save_pass_b(
            round_id=FORMAL_ROUND_ID, slot_id="HUMAN_SLOT_A", event_id=event_id,
            mode_agreement="agree", confidence_after="high", reviewer_requested_adjudication=False,
            selected_pair_reference={
                "path": assignment["visual_input_reference"], "sha256": assignment["visual_input_sha256"],
                "manifest_sha256": assignment["visual_input_manifest_sha256"], "mode": "selected_pair",
                "provenance": "formal_review_28_visual_inputs",
            },
            window_median_reference={
                "path": temporal_path, "sha256": temporal_sha, "manifest_sha256": temporal_manifest_sha,
                "mode": "window_median", "provenance": "frozen-temporal-test",
            },
        )
        assert saved_b["selected_pair_mode"] == "selected_pair"
        assert saved_b["window_median_mode"] == "window_median"
        assert saved_b["selected_pair_sha256"] != saved_b["window_median_sha256"]


def test_verifier_is_read_only_and_checks_prepared_empty_contract(tmp_path: Path):
    database, output = _prepared(tmp_path, seed_inside_output=True)
    public_path = output / "human_slot_a" / "manifest.json"
    before = public_path.read_bytes()
    result = verify_formal_review_round(root=ROOT, db_path=database, output_dir=output, protocol_path=FORMAL_PROTOCOL_PATH)
    assert result["ok"] is True
    assert result["assignment_count"] == 56
    assert result["execution_authorized"] is False
    assert public_path.read_bytes() == before


def test_verifier_detects_changed_public_artifact_without_rewriting_it(tmp_path: Path):
    database, output = _prepared(tmp_path, seed_inside_output=True)
    public_path = output / "human_slot_a" / "manifest.json"
    original = public_path.read_bytes()
    public_path.write_bytes(original + b"\n")
    result = verify_formal_review_round(root=ROOT, db_path=database, output_dir=output, protocol_path=FORMAL_PROTOCOL_PATH)
    assert result["ok"] is False
    assert public_path.read_bytes() == original + b"\n"


def test_prepare_rerun_refuses_same_identity_with_different_bytes(tmp_path: Path):
    database, output = _prepared(tmp_path)
    manifest = output / "human_slot_a" / "manifest.json"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b"tampered")
    with pytest.raises(FormalReviewError, match="Conflicto de bytes"):
        prepare_formal_round(
            root=ROOT, db_path=database, output_dir=output,
            supplied_seed="test-seed-formal-review-20260728", seed_path=tmp_path / "private_seed.txt",
            base_head="f302139",
        )
    assert manifest.read_bytes() == original + b"tampered"


def test_protocol_reconciliation_contract_constants_and_audit_shape():
    assert STALE_PROTOCOL_SHA256 != ""
    assert PROTOCOL_HASH_RECONCILIATION_REASON == "PROTOCOL_HASH_PREPARATION_RECONCILIATION"
    assert len(__import__("hashlib").sha256(FORMAL_PROTOCOL_PATH.read_bytes()).hexdigest()) == 64


def test_slot_private_map_loader_never_accepts_combined_a_plus_b_map(tmp_path: Path):
    module_path = ROOT / "src" / "fuegopa" / "formal_review_app.py"
    spec = importlib.util.spec_from_file_location("formal_review_app_isolation", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Relative imports are not needed to exercise the pure loader; load via the
    # package instead when available.
    from fuegopa.formal_review_app import _slot_private_map

    path = tmp_path / "slot.json"
    path.write_text(json.dumps({"slot_id": "HUMAN_SLOT_A", "items": {"HUMAN_SLOT_A": []}}, ensure_ascii=False), encoding="utf-8")
    assert _slot_private_map(path, "HUMAN_SLOT_A")["slot_id"] == "HUMAN_SLOT_A"
    path.write_text(json.dumps({"items": {"HUMAN_SLOT_A": [], "HUMAN_SLOT_B": []}}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(FormalReviewError, match="exclusivamente"):
        _slot_private_map(path, "HUMAN_SLOT_A")


def test_launcher_requires_round_slot_and_profile():
    module_path = ROOT / "scripts" / "run_human_review_app.py"
    spec = importlib.util.spec_from_file_location("run_human_review_app_contract", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit):
        module.build_formal_parser().parse_args(["--formal-round"])
    args = module.build_formal_parser().parse_args([
        "--formal-round", "--round-id", FORMAL_ROUND_ID,
        "--slot-id", "HUMAN_SLOT_A", "--profile-id", "human-a",
    ])
    assert (args.round_id, args.slot_id, args.profile_id) == (FORMAL_ROUND_ID, "HUMAN_SLOT_A", "human-a")


def test_assignment_generation_has_no_frp_selection_path():
    events = [{"event_id": "e1", "quicklook_path": "x.png", "quicklook_sha256": "h"}]
    assignment = build_slot_assignments(events, slot_id="HUMAN_SLOT_A", private_seed="test-seed-formal-review-20260728")[0]
    assert "frp" not in json.dumps(assignment).lower()
