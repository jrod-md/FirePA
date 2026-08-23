from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_human_review as validator  # noqa: E402


def _panel_root(tmp_path: Path) -> Path:
    for event_id in validator.EXPECTED_EVENT_IDS:
        for relative in validator.expected_panel_paths(event_id):
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"panel-placeholder")
    return tmp_path


def _empty_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for order, event_id in enumerate(validator.deterministic_randomized_order(), start=1):
        multispectral, temporal = validator.expected_panel_paths(event_id)
        row = {column: "" for column in validator.CALIBRATION_COLUMNS}
        row.update(
            {
                "calibration_round": validator.CALIBRATION_ROUND,
                "randomized_order": str(order),
                "event_id": event_id,
                "protocol_version": validator.PROTOCOL_VERSION,
                "quicklook_version": validator.QUICKLOOK_VERSION,
                "multispectral_panel_path": multispectral,
                "temporal_panel_path": temporal,
                "review_status": "pending",
            }
        )
        rows.append(row)
    return rows


def test_empty_schema_ids_order_and_panel_routes(tmp_path: Path):
    root = _panel_root(tmp_path)
    rows = _empty_rows()
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=root,
        require_empty=True,
    )

    assert errors == []
    assert len(rows) == 7
    assert {row["event_id"] for row in rows} == validator.EXPECTED_EVENT_ID_SET
    assert [int(row["randomized_order"]) for row in rows] == list(range(1, 8))


def test_deterministic_order_and_manifest_bytes():
    first = validator.deterministic_randomized_order(validator.RANDOMIZATION_SEED)
    second = validator.deterministic_randomized_order(validator.RANDOMIZATION_SEED)
    manifest_a = validator.build_manifest_from_rows(_empty_rows())
    manifest_b = validator.build_manifest_from_rows(_empty_rows())

    assert first == second
    assert first == tuple(row["event_id"] for row in _empty_rows())
    bytes_a = (json.dumps(manifest_a, indent=2, sort_keys=True) + "\n").encode()
    bytes_b = (json.dumps(manifest_b, indent=2, sort_keys=True) + "\n").encode()
    assert bytes_a == bytes_b
    assert hashlib.sha256(bytes_a).hexdigest() == hashlib.sha256(bytes_b).hexdigest()


def test_prohibited_columns_are_rejected(tmp_path: Path):
    rows = _empty_rows()
    fields = list(validator.CALIBRATION_COLUMNS) + ["FRP", "model_score"]
    errors = validator.validate_calibration_rows(fields, rows, root=_panel_root(tmp_path))

    assert any(error["code"] == "prohibited_columns" for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("visible_burn_scar", "maybe"),
        ("scar_confidence", "certain"),
        ("event_association", "confirmed"),
        ("competing_land_change", "unknown_class"),
        ("mode_agreement", "same"),
        ("review_status", "automatic"),
    ],
)
def test_invalid_enum_is_rejected(tmp_path: Path, field: str, value: str):
    rows = _empty_rows()
    rows[0][field] = value
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
        require_empty=False,
    )

    assert any(error["code"] == "invalid_enum" for error in errors)


def test_pending_rows_are_valid_only_when_review_fields_are_blank(tmp_path: Path):
    rows = _empty_rows()
    rows[0]["reviewer_notes"] = "partial note"
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
        require_empty=False,
    )

    assert any(error["code"] == "pending_has_review_data" for error in errors)


def test_reviewed_requires_reviewer_and_timestamp(tmp_path: Path):
    rows = _empty_rows()
    rows[0].update(
        {
            "visible_burn_scar": "ambiguous",
            "scar_confidence": "medium",
            "event_association": "possible",
            "competing_land_change": "unknown",
            "mode_agreement": "partially_agree",
            "review_status": "reviewed",
        }
    )
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
    )

    missing = {
        error["message"]
        for error in errors
        if error["code"] == "reviewed_missing_field"
    }
    assert any("reviewer_id" in message for message in missing)
    assert any("reviewed_at" in message for message in missing)


def test_excluded_with_reason_requires_reason(tmp_path: Path):
    rows = _empty_rows()
    rows[0]["review_status"] = "excluded_with_reason"
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
    )

    assert any(error["code"] == "missing_exclusion_reason" for error in errors)


def test_unobserved_events_are_separate_and_significant_burn_is_blank():
    rows = [
        {
            "event_id": event_id,
            "observability_status": "unobserved",
            "exclusion_reason": "no_usable_pre_scene_in_any_combination;clear_fraction_below_threshold",
            "protocol_version": validator.PROTOCOL_VERSION,
            "significant_burn": "",
        }
        for event_id in validator.UNOBSERVED_EVENT_IDS
    ]
    assert validator.validate_unobserved_rows(validator.UNOBSERVED_COLUMNS, rows) == []

    main_rows = _empty_rows()
    main_rows[0]["event_id"] = validator.UNOBSERVED_EVENT_IDS[0]
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        main_rows,
        root=Path.cwd(),
    )
    assert any(error["code"] == "unobserved_in_main_queue" for error in errors)


def test_significant_burn_is_forbidden_in_calibration():
    rows = _empty_rows()
    fields = list(validator.CALIBRATION_COLUMNS) + ["significant_burn"]
    errors = validator.validate_calibration_rows(fields, rows, root=Path.cwd())

    assert any(error["code"] == "prohibited_columns" for error in errors)


def test_2026_data_is_rejected(tmp_path: Path):
    rows = _empty_rows()
    rows[0]["multispectral_panel_path"] = (
        "outputs/review_upload_level2/2026_event_selected_pair_cs050_level2_panel.png"
    )
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
    )

    assert any(error["code"] == "data_2026" for error in errors)


def test_missing_panel_route_is_rejected(tmp_path: Path):
    root = _panel_root(tmp_path)
    missing = root / validator.expected_panel_paths(validator.EXPECTED_EVENT_IDS[0])[0]
    missing.unlink()
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        _empty_rows(),
        root=root,
        require_empty=True,
    )

    assert any(error["code"] == "missing_panel" for error in errors)


def test_unobserved_schema_rejects_extra_columns():
    rows = [
        {
            "event_id": validator.UNOBSERVED_EVENT_IDS[0],
            "observability_status": "unobserved",
            "exclusion_reason": "reason",
            "protocol_version": validator.PROTOCOL_VERSION,
            "significant_burn": "",
        },
        {
            "event_id": validator.UNOBSERVED_EVENT_IDS[1],
            "observability_status": "unobserved",
            "exclusion_reason": "reason",
            "protocol_version": validator.PROTOCOL_VERSION,
            "significant_burn": "",
        },
    ]
    fields = list(validator.UNOBSERVED_COLUMNS) + ["review_status"]
    errors = validator.validate_unobserved_rows(fields, rows)

    assert any(error["code"] == "extra_columns" for error in errors)


def test_validator_does_not_modify_metric_or_raster_bytes(tmp_path: Path):
    root = _panel_root(tmp_path)
    metric = root / "data/interim/sentinel2_dnbr_event_metrics.csv"
    raster = root / "outputs/rasters/sentinel2_level2/events/sentinel.tif"
    metric.parent.mkdir(parents=True, exist_ok=True)
    raster.parent.mkdir(parents=True, exist_ok=True)
    metric.write_bytes(b"scientific metric sentinel")
    raster.write_bytes(b"raster sentinel")
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (metric, raster)
    }

    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        _empty_rows(),
        root=root,
        require_empty=True,
    )

    after = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (metric, raster)
    }
    assert errors == []
    assert before == after


def test_completed_review_validates_without_inference(tmp_path: Path):
    rows = _empty_rows()
    rows[0].update(
        {
            "reviewer_id": "reviewer-1",
            "reviewed_at": "2025-07-21T12:00:00Z",
            "visible_burn_scar": "ambiguous",
            "scar_confidence": "low",
            "event_association": "indeterminate",
            "competing_land_change": "mixed",
            "mode_agreement": "selected_pair_only",
            "reviewer_notes": "Ambiguity retained for human adjudication.",
            "review_status": "reviewed",
        }
    )
    errors = validator.validate_calibration_rows(
        validator.CALIBRATION_COLUMNS,
        rows,
        root=_panel_root(tmp_path),
    )

    assert errors == []


def test_manifest_validation_uses_exact_deterministic_schema(tmp_path: Path):
    rows = _empty_rows()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(validator.build_manifest_from_rows(rows), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    assert validator.validate_manifest(manifest, rows=rows) == []
