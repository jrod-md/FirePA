from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fuegopa.human_review_schema import (  # noqa: E402
    CALIBRATION_EVENT_IDS,
    CALIBRATION_ROUND,
    CALIBRATION_SEED_COLUMNS,
    DEFAULT_CALIBRATION_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_UNOBSERVED_PATH,
    NORMALIZED_EXPORT_COLUMNS,
    QUICKLOOK_VERSION,
    REVIEW_STATUS_CODES,
    SCHEMA_VERSION,
    deterministic_calibration_order,
    expected_panel_paths,
)
from fuegopa.human_review_store import HumanReviewStore, ReviewStoreError  # noqa: E402
import validate_human_review as validator  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2025, 7, 21, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def _prepared_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for event_id in CALIBRATION_EVENT_IDS:
        for relative in expected_panel_paths(event_id):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"panel:{event_id}:{relative}".encode())
    return root


@pytest.fixture
def store_fixture(tmp_path: Path) -> tuple[HumanReviewStore, Path, Path]:
    root = _prepared_root(tmp_path)
    db_path = tmp_path / "firepa_human_review.sqlite3"
    clock = Clock()
    store = HumanReviewStore.from_frozen_round(
        db_path=db_path,
        root=root,
        calibration_path=DEFAULT_CALIBRATION_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
        unobserved_path=DEFAULT_UNOBSERVED_PATH,
        now_fn=clock,
    )
    yield store, root, db_path
    store.close()


def _first_item(store: HumanReviewStore) -> dict[str, object]:
    return store.list_items(CALIBRATION_ROUND)[0]


def _save_a(store: HumanReviewStore, *, reviewer_id: str = "reviewer-1", event_id: str | None = None) -> dict[str, object]:
    item = _first_item(store)
    return store.save_pass_a(
        round_id=CALIBRATION_ROUND,
        event_id=event_id or str(item["event_id"]),
        reviewer_id=reviewer_id,
        pass_a_visible_burn_scar="ambiguous",
        pass_a_scar_confidence="medium",
        pass_a_event_association="possible",
        pass_a_competing_land_change="unknown",
        pass_a_notes="La forma es ambigua; se conserva la incertidumbre.",
    )


def _save_b(
    store: HumanReviewStore,
    *,
    reviewer_id: str = "reviewer-1",
    event_id: str | None = None,
    needs: bool = False,
) -> dict[str, object]:
    item = _first_item(store)
    return store.save_pass_b(
        round_id=CALIBRATION_ROUND,
        event_id=event_id or str(item["event_id"]),
        reviewer_id=reviewer_id,
        pass_b_mode_agreement="partially_agree",
        pass_b_confidence_after="low",
        pass_b_requires_adjudication=needs,
        pass_b_notes="La comparación temporal requiere discusión." if needs else "La diferencia es pequeña.",
    )


def test_initialization_is_idempotent_and_preserves_frozen_order(store_fixture):
    store, _, _ = store_fixture
    first_items = store.list_items(CALIBRATION_ROUND)
    store.seed_frozen_round(
        root=Path(store_fixture[1]),
        calibration_path=DEFAULT_CALIBRATION_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
        unobserved_path=DEFAULT_UNOBSERVED_PATH,
    )
    second_items = store.list_items(CALIBRATION_ROUND)
    assert len(first_items) == len(second_items) == 7
    assert [item["event_id"] for item in first_items] == list(deterministic_calibration_order())
    assert [item["randomized_order"] for item in second_items] == list(range(1, 8))
    assert store.connection.execute("SELECT COUNT(*) FROM review_rounds").fetchone()[0] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 7
    assert store.connection.execute("SELECT COUNT(*) FROM unobserved_events").fetchone()[0] == 2


def test_schema_rejects_invalid_enum_and_reviewer_is_required(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            """
            INSERT INTO reviews (round_id, event_id, reviewer_id, pass_a_visible_burn_scar, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (CALIBRATION_ROUND, item["event_id"], "reviewer-1", "not-a-code", "t", "t"),
        )
    with pytest.raises(ReviewStoreError, match="reviewer_id"):
        _save_a(store, reviewer_id=" ")


def test_pass_b_is_blocked_until_pass_a_and_never_overwrites_pass_a(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    with pytest.raises(ReviewStoreError, match="Pass B"):
        _save_b(store, event_id=str(item["event_id"]))
    saved_a = _save_a(store, event_id=str(item["event_id"]))
    with pytest.raises(ReviewStoreError, match="requiere notas"):
        store.save_pass_b(
            round_id=CALIBRATION_ROUND,
            event_id=str(item["event_id"]),
            reviewer_id="reviewer-1",
            pass_b_mode_agreement="agree",
            pass_b_confidence_after="high",
            pass_b_requires_adjudication=True,
            pass_b_notes="",
        )
    saved_b = _save_b(store, event_id=str(item["event_id"]))
    assert saved_b["review_status"] == "pass_b_complete"
    current = store.get_review(CALIBRATION_ROUND, str(item["event_id"]), "reviewer-1")
    assert current["pass_a_visible_burn_scar"] == saved_a["pass_a_visible_burn_scar"]
    assert current["pass_a_scar_confidence"] == saved_a["pass_a_scar_confidence"]
    assert current["pass_a_revision"] == 1
    assert current["pass_b_revision"] == 1


def test_pass_a_is_locked_and_amendment_requires_reason_and_audit(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    event_id = str(item["event_id"])
    _save_a(store, event_id=event_id)
    with pytest.raises(ReviewStoreError, match="bloqueada"):
        _save_a(store, event_id=event_id)
    with pytest.raises(ReviewStoreError, match="razón"):
        store.save_pass_a(
            round_id=CALIBRATION_ROUND,
            event_id=event_id,
            reviewer_id="reviewer-1",
            pass_a_visible_burn_scar="yes",
            pass_a_scar_confidence="high",
            pass_a_event_association="likely",
            pass_a_competing_land_change="none_visible",
            amend=True,
        )
    amended = store.save_pass_a(
        round_id=CALIBRATION_ROUND,
        event_id=event_id,
        reviewer_id="reviewer-1",
        pass_a_visible_burn_scar="yes",
        pass_a_scar_confidence="high",
        pass_a_event_association="likely",
        pass_a_competing_land_change="none_visible",
        pass_a_notes="Revisé el panel con una enmienda explícita.",
        amend=True,
        amendment_reason="La primera lectura omitió un borde visible.",
    )
    assert amended["pass_a_revision"] == 2
    audit = store.audit_entries(CALIBRATION_ROUND, event_id, "reviewer-1")
    assert any(
        entry["field_name"] == "pass_a_visible_burn_scar"
        and entry["previous_value"] == "ambiguous"
        and entry["new_value"] == "yes"
        and entry["reason"] == "La primera lectura omitió un borde visible."
        for entry in audit
    )


def test_audit_log_is_append_only(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    _save_a(store, event_id=str(item["event_id"]))
    audit_id = store.connection.execute("SELECT MIN(audit_id) FROM audit_log").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.connection.execute("UPDATE audit_log SET reason = 'changed' WHERE audit_id = ?", (audit_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.connection.execute("DELETE FROM audit_log WHERE audit_id = ?", (audit_id,))


def test_needs_adjudication_has_notes_and_adjudication_field(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    event_id = str(item["event_id"])
    _save_a(store, event_id=event_id)
    review = _save_b(store, event_id=event_id, needs=True)
    assert review["review_status"] == "needs_adjudication"
    assert review["adjudication_notes"] == review["pass_b_notes"]
    updated = store.update_adjudication_notes(
        round_id=CALIBRATION_ROUND,
        event_id=event_id,
        reviewer_id="reviewer-1",
        notes="Confirmar si la diferencia entre modos cambia la lectura.",
    )
    assert updated["adjudication_notes"].startswith("Confirmar")


def test_unobserved_events_are_separate_and_not_revisable(store_fixture):
    store, _, _ = store_fixture
    unobserved = store.list_unobserved()
    assert len(unobserved) == 2
    assert {row["event_id"] for row in unobserved}.isdisjoint(CALIBRATION_EVENT_IDS)
    schema_text = "\n".join(
        str(row[0])
        for row in store.connection.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"
        ).fetchall()
    ).lower()
    assert "significant_burn" not in schema_text
    assert store.get_review(CALIBRATION_ROUND, str(unobserved[0]["event_id"]), "reviewer-1") is None
    with pytest.raises(ReviewStoreError):
        store.save_pass_a(
            round_id=CALIBRATION_ROUND,
            event_id=str(unobserved[0]["event_id"]),
            reviewer_id="reviewer-1",
            pass_a_visible_burn_scar="unobserved",
            pass_a_scar_confidence="not_applicable",
            pass_a_event_association="indeterminate",
            pass_a_competing_land_change="unknown",
            exclusion_reason="reason",
        )


def test_panel_routes_exist_and_frozen_hashes_survive_store_operations(store_fixture, tmp_path: Path):
    store, root, _ = store_fixture
    metric = root / "data/interim/descriptive_metric.csv"
    raster = root / "outputs/rasters/diagnostic.tif"
    metric.parent.mkdir(parents=True, exist_ok=True)
    raster.parent.mkdir(parents=True, exist_ok=True)
    metric.write_bytes(b"metric bytes")
    raster.write_bytes(b"raster bytes")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (metric, raster)}
    for item in store.list_items():
        assert (root / str(item["multispectral_panel_path"])).is_file()
        assert (root / str(item["temporal_panel_path"])).is_file()
    _save_a(store)
    paths = store.export_snapshot(
        reviewer_id="reviewer-1",
        export_dir=tmp_path / "exports",
        audit_dir=tmp_path / "audit",
    )
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (metric, raster)}
    assert before == after
    assert paths["csv"].is_file()


def test_actual_scientific_and_level2_hashes_survive_human_review(store_fixture, tmp_path: Path):
    store, _, _ = store_fixture
    protected = [
        ROOT / "outputs/manifests/firepa_active_bundle_2026-07-21.json",
        ROOT / "outputs/manifests/firepa_quicklook_level2.sha256",
        ROOT / "outputs/review_upload_level2" / f"{CALIBRATION_EVENT_IDS[0]}_selected_pair_cs050_level2_panel.png",
    ]
    assert all(path.is_file() for path in protected)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    _save_a(store)
    store.export_snapshot(
        reviewer_id="reviewer-1",
        export_dir=tmp_path / "exports",
        audit_dir=tmp_path / "audit",
    )
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    assert before == after


def test_exports_are_normalized_deterministic_and_validator_compatible(store_fixture, tmp_path: Path):
    store, root, _ = store_fixture
    item = _first_item(store)
    _save_a(store, event_id=str(item["event_id"]))
    _save_b(store, event_id=str(item["event_id"]))
    first = store.export_snapshot(
        reviewer_id="reviewer-1",
        export_dir=tmp_path / "exports",
        audit_dir=tmp_path / "audit",
    )
    bytes_first = {key: path.read_bytes() for key, path in first.items()}
    second = store.export_snapshot(
        reviewer_id="reviewer-1",
        export_dir=tmp_path / "exports",
        audit_dir=tmp_path / "audit",
    )
    assert {key: path.read_bytes() for key, path in second.items()} == bytes_first

    with first["csv"].open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert tuple(reader.fieldnames or ()) == NORMALIZED_EXPORT_COLUMNS
    assert len(rows) == 7
    assert [int(row["randomized_order"]) for row in rows] == list(range(1, 8))
    forbidden = {"significant_burn", "frp", "model_score", "predicted_class", "expected_class"}
    assert forbidden.isdisjoint({field.lower() for field in reader.fieldnames or ()})
    payload = json.loads(first["json"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert len(payload["items"]) == 7
    audit_lines = [line for line in first["audit_jsonl"].read_text(encoding="utf-8").splitlines() if line]
    assert audit_lines
    assert all("significant_burn" not in line for line in audit_lines)

    validation = validator.validate_tool_export(first["csv"], root=root)
    assert validation["status"] == "pass", validation
    legacy_validation = validator.validate_artifacts(
        root=root,
        calibration_path=first["legacy_csv"],
        unobserved_path=DEFAULT_UNOBSERVED_PATH,
        manifest_path=DEFAULT_MANIFEST_PATH,
    )
    assert legacy_validation["status"] == "pass", legacy_validation


def test_unique_active_review_per_round_event_reviewer(store_fixture):
    store, _, _ = store_fixture
    item = _first_item(store)
    event_id = str(item["event_id"])
    _save_a(store, event_id=event_id)
    with pytest.raises(ReviewStoreError):
        _save_a(store, event_id=event_id)
    assert store.connection.execute(
        "SELECT COUNT(*) FROM reviews WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
        (CALIBRATION_ROUND, event_id, "reviewer-1"),
    ).fetchone()[0] == 1


def test_unobserved_coherence_and_exclusion_reason(store_fixture):
    store, _, _ = store_fixture
    event_id = str(_first_item(store)["event_id"])
    with pytest.raises(ReviewStoreError, match="not_applicable"):
        store.save_pass_a(
            round_id=CALIBRATION_ROUND,
            event_id=event_id,
            reviewer_id="reviewer-1",
            pass_a_visible_burn_scar="unobserved",
            pass_a_scar_confidence="low",
            pass_a_event_association="indeterminate",
            pass_a_competing_land_change="unknown",
            exclusion_reason="reason",
        )
    with pytest.raises(ReviewStoreError, match="razón"):
        store.save_pass_a(
            round_id=CALIBRATION_ROUND,
            event_id=event_id,
            reviewer_id="reviewer-1",
            pass_a_visible_burn_scar="unobserved",
            pass_a_scar_confidence="not_applicable",
            pass_a_event_association="indeterminate",
            pass_a_competing_land_change="unknown",
        )
