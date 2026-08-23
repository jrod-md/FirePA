#!/usr/bin/env python3
"""Validate the blinded human-review calibration contract.

The validator is deliberately read-only with respect to calibration inputs. It
checks schemas, enums, exact event membership, panel routes and explicit
review-state invariants. It never infers, fills, reorders or corrects labels.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = ROOT / "outputs" / "human_review" / "calibration_round1_blinded.csv"
MANIFEST_PATH = ROOT / "outputs" / "human_review" / "calibration_round1_manifest.json"
UNOBSERVED_PATH = ROOT / "outputs" / "human_review" / "unobserved_events.csv"

CALIBRATION_ROUND = "round1"
PROTOCOL_VERSION = "draft-v1"
QUICKLOOK_VERSION = "fuegopa-dnbr-quicklook-level2-v1"
RANDOMIZATION_SEED = 20260721

EXPECTED_EVENT_IDS = (
    "event-r1500_t06-0ddd477d24b1364d",
    "event-r1500_t06-84cb252a6877d2d5",
    "event-r1500_t06-ef20fd746737f4ea",
    "event-r1500_t06-9e5bf1d807f9d61a",
    "event-r1500_t06-548ca9e284d1a330",
    "event-r1500_t06-040b1a186d857b11",
    "event-r1500_t06-09c2d54e2d8fb5dd",
)
EXPECTED_EVENT_ID_SET = frozenset(EXPECTED_EVENT_IDS)
UNOBSERVED_EVENT_IDS = (
    "event-r1500_t06-1f8f72e78d63b0ee",
    "event-r1500_t06-ab8e9016ae0d3154",
)
UNOBSERVED_EVENT_ID_SET = frozenset(UNOBSERVED_EVENT_IDS)

CALIBRATION_COLUMNS = (
    "calibration_round",
    "randomized_order",
    "event_id",
    "reviewer_id",
    "reviewed_at",
    "protocol_version",
    "quicklook_version",
    "multispectral_panel_path",
    "temporal_panel_path",
    "visible_burn_scar",
    "scar_confidence",
    "event_association",
    "competing_land_change",
    "mode_agreement",
    "reviewer_notes",
    "review_status",
    "exclusion_reason",
    "adjudication_notes",
)
NORMALIZED_EXPORT_COLUMNS = (
    "schema_version",
    "round_id",
    "event_id",
    "randomized_order",
    "reviewer_id",
    "protocol_version",
    "quicklook_version",
    "observability_status",
    "multispectral_panel_path",
    "temporal_panel_path",
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "pass_a_notes",
    "pass_a_saved_at",
    "pass_a_revision",
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
    "pass_b_notes",
    "pass_b_saved_at",
    "pass_b_revision",
    "review_status",
    "exclusion_reason",
    "adjudication_notes",
    "created_at",
    "updated_at",
)
TOOL_REVIEW_STATUS = frozenset(
    {
        "pending",
        "pass_a_complete",
        "pass_b_complete",
        "needs_adjudication",
        "unobserved",
        "excluded_with_reason",
    }
)
UNOBSERVED_COLUMNS = (
    "event_id",
    "observability_status",
    "exclusion_reason",
    "protocol_version",
    "significant_burn",
)

ENUMS: dict[str, frozenset[str]] = {
    "visible_burn_scar": frozenset({"yes", "no", "ambiguous", "unobserved"}),
    "scar_confidence": frozenset({"high", "medium", "low", "not_applicable"}),
    "event_association": frozenset(
        {"likely", "possible", "unlikely", "indeterminate"}
    ),
    "competing_land_change": frozenset(
        {
            "none_visible",
            "agriculture_or_harvest",
            "soil_exposure",
            "vegetation_phenology",
            "moisture_or_flooding",
            "cloud_or_haze",
            "shadow_or_atmosphere",
            "water",
            "urban_or_construction",
            "mixed",
            "unknown",
        }
    ),
    "mode_agreement": frozenset(
        {
            "agree",
            "partially_agree",
            "disagree",
            "selected_pair_only",
            "window_median_only",
            "unavailable",
        }
    ),
    "review_status": frozenset(
        {
            "pending",
            "reviewed",
            "needs_adjudication",
            "unobserved",
            "excluded_with_reason",
        }
    ),
}

REVIEW_FIELDS = (
    "visible_burn_scar",
    "scar_confidence",
    "event_association",
    "competing_land_change",
    "mode_agreement",
    "reviewer_notes",
    "exclusion_reason",
    "adjudication_notes",
)
REQUIRED_FOR_REVIEWED = (
    "reviewer_id",
    "reviewed_at",
    "visible_burn_scar",
    "scar_confidence",
    "event_association",
    "competing_land_change",
    "mode_agreement",
)
DATA_PATH_FIELDS = (
    "event_id",
    "multispectral_panel_path",
    "temporal_panel_path",
)
PROHIBITED_COLUMN_NAMES = frozenset(
    {
        "frp",
        "frp_value",
        "firms_confidence",
        "confidence_firms",
        "dnbr_median",
        "dnbr_p90",
        "area",
        "area_ha",
        "model_score",
        "predicted_class",
        "expected_class",
        "significant_burn",
    }
)


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _error(errors: list[dict[str, str]], code: str, message: str) -> None:
    errors.append({"code": code, "message": message})


def _read_csv(path: Path, errors: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        _error(errors, "missing_file", f"CSV not found: {path}")
        return [], []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows: list[dict[str, str]] = []
            for index, raw_row in enumerate(reader, start=2):
                if None in raw_row:
                    _error(
                        errors,
                        "malformed_row",
                        f"{path}: row {index} has more values than its header",
                    )
                rows.append(
                    {
                        str(key): _text(value)
                        for key, value in raw_row.items()
                        if key is not None
                    }
                )
            return fieldnames, rows
    except (OSError, UnicodeError, csv.Error) as exc:
        _error(errors, "csv_read_error", f"{path}: {exc}")
        return [], []


def _validate_header(
    fieldnames: Sequence[str],
    expected: Sequence[str],
    *,
    label: str,
    errors: list[dict[str, str]],
    check_prohibited: bool = True,
) -> None:
    if len(fieldnames) != len(set(fieldnames)):
        _error(errors, "duplicate_columns", f"{label}: duplicate column names")
    missing = sorted(set(expected) - set(fieldnames))
    extra = sorted(set(fieldnames) - set(expected))
    if missing:
        _error(errors, "missing_columns", f"{label}: missing columns: {', '.join(missing)}")
    if extra:
        _error(errors, "extra_columns", f"{label}: unexpected columns: {', '.join(extra)}")
    if list(fieldnames) != list(expected):
        _error(errors, "column_order", f"{label}: columns are not in the required order")
    if check_prohibited:
        prohibited = sorted(
            column
            for column in fieldnames
            if _normalise_column(column) in PROHIBITED_COLUMN_NAMES
        )
        if prohibited:
            _error(
                errors,
                "prohibited_columns",
                f"{label}: prohibited columns present: {', '.join(prohibited)}",
            )


def deterministic_randomized_order(seed: int = RANDOMIZATION_SEED) -> tuple[str, ...]:
    """Return the only order allowed for a given calibration seed."""

    values = sorted(EXPECTED_EVENT_IDS)
    random.Random(seed).shuffle(values)
    return tuple(values)


def expected_panel_paths(event_id: str) -> tuple[str, str]:
    base = f"outputs/review_upload_level2/{event_id}"
    return (
        f"{base}_selected_pair_cs050_level2_panel.png",
        f"{base}_temporal_robustness_level2.png",
    )


def _safe_repo_path(root: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved


def _validate_panel_paths(
    row: Mapping[str, str],
    *,
    root: Path,
    row_label: str,
    errors: list[dict[str, str]],
) -> None:
    event_id = _text(row.get("event_id"))
    expected_multispectral, expected_temporal = expected_panel_paths(event_id)
    for field, expected in (
        ("multispectral_panel_path", expected_multispectral),
        ("temporal_panel_path", expected_temporal),
    ):
        actual = _text(row.get(field))
        if actual != expected:
            _error(
                errors,
                "panel_route_mismatch",
                f"{row_label}: {field} must be {expected!r}",
            )
            continue
        resolved = _safe_repo_path(root, actual)
        if resolved is None or not resolved.is_file():
            _error(
                errors,
                "missing_panel",
                f"{row_label}: panel path does not exist: {actual}",
            )


def _validate_no_2026_data(
    row: Mapping[str, str],
    *,
    row_label: str,
    errors: list[dict[str, str]],
) -> None:
    for field in DATA_PATH_FIELDS:
        value = _text(row.get(field))
        if "2026" in value:
            _error(
                errors,
                "data_2026",
                f"{row_label}: 2026 data is not allowed in {field}",
            )


def _validate_enums(
    row: Mapping[str, str],
    *,
    row_label: str,
    errors: list[dict[str, str]],
) -> None:
    for field, allowed in ENUMS.items():
        value = _text(row.get(field))
        if value and value not in allowed:
            _error(
                errors,
                "invalid_enum",
                f"{row_label}: {field}={value!r} is not in the allowed enum",
            )


def _validate_state(
    row: Mapping[str, str],
    *,
    row_label: str,
    require_empty: bool,
    errors: list[dict[str, str]],
) -> None:
    status = _text(row.get("review_status"))
    visible = _text(row.get("visible_burn_scar"))
    confidence = _text(row.get("scar_confidence"))
    mode = _text(row.get("mode_agreement"))

    if not status:
        _error(errors, "missing_review_status", f"{row_label}: review_status is required")
    if require_empty:
        if status != "pending":
            _error(
                errors,
                "non_empty_calibration",
                f"{row_label}: an empty calibration row must be pending",
            )
        for field in (
            "reviewer_id",
            "reviewed_at",
            *REVIEW_FIELDS,
        ):
            if not _blank(row.get(field)):
                _error(
                    errors,
                    "non_empty_calibration",
                    f"{row_label}: {field} must be blank in the empty calibration queue",
                )
    elif status == "pending":
        for field in REVIEW_FIELDS:
            if not _blank(row.get(field)):
                _error(
                    errors,
                    "pending_has_review_data",
                    f"{row_label}: pending rows must not contain {field}",
                )

    if visible == "unobserved" and confidence != "not_applicable":
        _error(
            errors,
            "incoherent_confidence",
            f"{row_label}: unobserved requires scar_confidence=not_applicable",
        )
    if confidence == "not_applicable" and visible not in {"", "unobserved"}:
        _error(
            errors,
            "incoherent_confidence",
            f"{row_label}: not_applicable confidence requires visible_burn_scar=unobserved",
        )
    if status == "unobserved":
        if visible != "unobserved":
            _error(
                errors,
                "incoherent_unobserved",
                f"{row_label}: unobserved status requires visible_burn_scar=unobserved",
            )
        if confidence != "not_applicable":
            _error(
                errors,
                "incoherent_unobserved",
                f"{row_label}: unobserved status requires scar_confidence=not_applicable",
            )
        if mode != "unavailable":
            _error(
                errors,
                "incoherent_unobserved",
                f"{row_label}: unobserved status requires mode_agreement=unavailable",
            )

    if status == "reviewed":
        for field in REQUIRED_FOR_REVIEWED:
            if _blank(row.get(field)):
                _error(
                    errors,
                    "reviewed_missing_field",
                    f"{row_label}: reviewed rows require {field}",
                )
        reviewed_at = _text(row.get("reviewed_at"))
        if reviewed_at:
            try:
                datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            except ValueError:
                _error(
                    errors,
                    "invalid_reviewed_at",
                    f"{row_label}: reviewed_at must be ISO-8601",
                )
    if status == "needs_adjudication" and _blank(row.get("adjudication_notes")):
        _error(
            errors,
            "missing_adjudication_notes",
            f"{row_label}: needs_adjudication requires adjudication_notes",
        )
    if status == "excluded_with_reason" and _blank(row.get("exclusion_reason")):
        _error(
            errors,
            "missing_exclusion_reason",
            f"{row_label}: excluded_with_reason requires exclusion_reason",
        )


def validate_calibration_rows(
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
    require_empty: bool = False,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    _validate_header(
        fieldnames,
        CALIBRATION_COLUMNS,
        label="calibration",
        errors=errors,
    )
    if len(rows) != len(EXPECTED_EVENT_IDS):
        _error(
            errors,
            "wrong_event_count",
            f"calibration must contain exactly {len(EXPECTED_EVENT_IDS)} rows",
        )

    seen: list[str] = []
    orders: list[int] = []
    for index, row in enumerate(rows, start=2):
        row_label = f"calibration row {index}"
        event_id = _text(row.get("event_id"))
        seen.append(event_id)
        if event_id not in EXPECTED_EVENT_ID_SET:
            _error(errors, "unexpected_event", f"{row_label}: unexpected event_id={event_id!r}")
        if event_id in seen[:-1]:
            _error(errors, "duplicate_event", f"{row_label}: duplicate event_id={event_id!r}")
        try:
            randomized_order = int(_text(row.get("randomized_order")))
            orders.append(randomized_order)
        except ValueError:
            _error(errors, "invalid_order", f"{row_label}: randomized_order must be an integer")
        if _text(row.get("calibration_round")) != CALIBRATION_ROUND:
            _error(errors, "wrong_round", f"{row_label}: calibration_round must be {CALIBRATION_ROUND}")
        if _text(row.get("protocol_version")) != PROTOCOL_VERSION:
            _error(errors, "wrong_protocol", f"{row_label}: protocol_version must be {PROTOCOL_VERSION}")
        if _text(row.get("quicklook_version")) != QUICKLOOK_VERSION:
            _error(errors, "wrong_quicklook_version", f"{row_label}: quicklook_version is invalid")
        _validate_no_2026_data(row, row_label=row_label, errors=errors)
        _validate_panel_paths(row, root=root, row_label=row_label, errors=errors)
        _validate_enums(row, row_label=row_label, errors=errors)
        _validate_state(
            row,
            row_label=row_label,
            require_empty=require_empty,
            errors=errors,
        )

    if frozenset(seen) != EXPECTED_EVENT_ID_SET:
        _error(errors, "wrong_event_set", "calibration event IDs do not match the seven frozen IDs")
    if len(orders) == len(rows) and sorted(orders) != list(range(1, len(EXPECTED_EVENT_IDS) + 1)):
        _error(errors, "wrong_randomized_order", "randomized_order must be a unique permutation of 1..7")
    if any(event_id in UNOBSERVED_EVENT_ID_SET for event_id in seen):
        _error(errors, "unobserved_in_main_queue", "unobserved events must remain outside calibration")
    return errors


def _validate_iso_timestamp(
    value: Any,
    *,
    row_label: str,
    field_name: str,
    errors: list[dict[str, str]],
    required: bool,
) -> None:
    text = _text(value)
    if not text:
        if required:
            _error(errors, "missing_timestamp", f"{row_label}: {field_name} is required")
        return
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _error(errors, "invalid_timestamp", f"{row_label}: {field_name} must be ISO-8601")


def _validate_revision(
    value: Any,
    *,
    row_label: str,
    field_name: str,
    errors: list[dict[str, str]],
    minimum: int,
) -> int | None:
    text = _text(value)
    try:
        revision = int(text)
    except ValueError:
        _error(errors, "invalid_revision", f"{row_label}: {field_name} must be an integer")
        return None
    if revision < minimum:
        _error(errors, "invalid_revision", f"{row_label}: {field_name} must be >= {minimum}")
    return revision


def validate_tool_export_rows(
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    *,
    root: Path,
) -> list[dict[str, str]]:
    """Validate the normalized SQLite export without changing the old mode.

    This is an explicit validator mode for the two-pass tool.  The original
    queue/completed-review contract above remains unchanged for older CSVs.
    """

    errors: list[dict[str, str]] = []
    _validate_header(
        fieldnames,
        NORMALIZED_EXPORT_COLUMNS,
        label="normalized tool export",
        errors=errors,
    )
    if len(rows) != len(EXPECTED_EVENT_IDS):
        _error(
            errors,
            "wrong_event_count",
            f"normalized tool export must contain exactly {len(EXPECTED_EVENT_IDS)} rows",
        )

    seen: list[str] = []
    orders: list[int] = []
    for index, row in enumerate(rows, start=2):
        row_label = f"normalized row {index}"
        event_id = _text(row.get("event_id"))
        seen.append(event_id)
        if event_id not in EXPECTED_EVENT_ID_SET:
            _error(errors, "unexpected_event", f"{row_label}: unexpected event_id={event_id!r}")
        if event_id in seen[:-1]:
            _error(errors, "duplicate_event", f"{row_label}: duplicate event_id={event_id!r}")
        try:
            randomized_order = int(_text(row.get("randomized_order")))
            orders.append(randomized_order)
        except ValueError:
            _error(errors, "invalid_order", f"{row_label}: randomized_order must be an integer")
        if _text(row.get("schema_version")) != "fuegopa-human-review-v1":
            _error(errors, "wrong_schema_version", f"{row_label}: schema_version is invalid")
        if _text(row.get("round_id")) != CALIBRATION_ROUND:
            _error(errors, "wrong_round", f"{row_label}: round_id must be {CALIBRATION_ROUND}")
        if _text(row.get("reviewer_id")) == "":
            _error(errors, "missing_reviewer", f"{row_label}: reviewer_id is required")
        if _text(row.get("protocol_version")) != PROTOCOL_VERSION:
            _error(errors, "wrong_protocol", f"{row_label}: protocol_version must be {PROTOCOL_VERSION}")
        if _text(row.get("quicklook_version")) != QUICKLOOK_VERSION:
            _error(errors, "wrong_quicklook_version", f"{row_label}: quicklook_version is invalid")
        if _text(row.get("observability_status")) != "observable":
            _error(errors, "wrong_observability_status", f"{row_label}: exported queue item must be observable")
        _validate_no_2026_data(row, row_label=row_label, errors=errors)
        _validate_panel_paths(row, root=root, row_label=row_label, errors=errors)

        status = _text(row.get("review_status"))
        if status not in TOOL_REVIEW_STATUS:
            _error(errors, "invalid_enum", f"{row_label}: review_status={status!r} is not allowed for the tool")
            continue

        a_fields = (
            "pass_a_visible_burn_scar",
            "pass_a_scar_confidence",
            "pass_a_event_association",
            "pass_a_competing_land_change",
        )
        b_fields = ("pass_b_mode_agreement", "pass_b_confidence_after")
        for field, allowed in (
            ("pass_a_visible_burn_scar", ENUMS["visible_burn_scar"]),
            ("pass_a_scar_confidence", ENUMS["scar_confidence"]),
            ("pass_a_event_association", ENUMS["event_association"]),
            ("pass_a_competing_land_change", ENUMS["competing_land_change"]),
            ("pass_b_mode_agreement", ENUMS["mode_agreement"]),
            ("pass_b_confidence_after", ENUMS["scar_confidence"]),
        ):
            value = _text(row.get(field))
            if value and value not in allowed:
                _error(errors, "invalid_enum", f"{row_label}: {field}={value!r} is not allowed")

        required_a = status in {
            "pass_a_complete",
            "pass_b_complete",
            "needs_adjudication",
            "unobserved",
            "excluded_with_reason",
        }
        if required_a:
            for field in a_fields:
                if _blank(row.get(field)):
                    _error(errors, "missing_pass_a_field", f"{row_label}: {field} is required")
            _validate_iso_timestamp(
                row.get("pass_a_saved_at"),
                row_label=row_label,
                field_name="pass_a_saved_at",
                errors=errors,
                required=True,
            )
            _validate_revision(
                row.get("pass_a_revision"),
                row_label=row_label,
                field_name="pass_a_revision",
                errors=errors,
                minimum=1,
            )
            visible = _text(row.get("pass_a_visible_burn_scar"))
            confidence = _text(row.get("pass_a_scar_confidence"))
            if visible == "unobserved" and confidence != "not_applicable":
                _error(errors, "incoherent_confidence", f"{row_label}: unobserved requires not_applicable confidence")
            if confidence == "not_applicable" and visible != "unobserved":
                _error(errors, "incoherent_confidence", f"{row_label}: not_applicable requires unobserved")
        else:
            for field in (
                *a_fields,
                "pass_a_notes",
                "pass_a_saved_at",
                "pass_b_mode_agreement",
                "pass_b_confidence_after",
                "pass_b_requires_adjudication",
                "pass_b_notes",
                "pass_b_saved_at",
                "adjudication_notes",
            ):
                if not _blank(row.get(field)):
                    _error(errors, "pending_has_review_data", f"{row_label}: pending rows must not contain {field}")
            _validate_revision(
                row.get("pass_a_revision"),
                row_label=row_label,
                field_name="pass_a_revision",
                errors=errors,
                minimum=0,
            )
            _validate_revision(
                row.get("pass_b_revision"),
                row_label=row_label,
                field_name="pass_b_revision",
                errors=errors,
                minimum=0,
            )

        if status in {"pass_b_complete", "needs_adjudication"}:
            for field in b_fields:
                if _blank(row.get(field)):
                    _error(errors, "missing_pass_b_field", f"{row_label}: {field} is required")
            _validate_iso_timestamp(
                row.get("pass_b_saved_at"),
                row_label=row_label,
                field_name="pass_b_saved_at",
                errors=errors,
                required=True,
            )
            _validate_revision(
                row.get("pass_b_revision"),
                row_label=row_label,
                field_name="pass_b_revision",
                errors=errors,
                minimum=1,
            )
            adjudication_flag = _text(row.get("pass_b_requires_adjudication"))
            if adjudication_flag not in {"0", "1"}:
                _error(errors, "invalid_adjudication_flag", f"{row_label}: pass_b_requires_adjudication must be 0 or 1")
            if status == "needs_adjudication":
                if adjudication_flag != "1":
                    _error(errors, "incoherent_status", f"{row_label}: needs_adjudication requires flag 1")
                if _blank(row.get("pass_b_notes")) and _blank(row.get("adjudication_notes")):
                    _error(errors, "missing_adjudication_notes", f"{row_label}: needs_adjudication requires notes")
            elif adjudication_flag != "0":
                _error(errors, "incoherent_status", f"{row_label}: pass_b_complete requires flag 0")
        elif status == "unobserved":
            if _text(row.get("pass_a_visible_burn_scar")) != "unobserved":
                _error(errors, "incoherent_unobserved", f"{row_label}: unobserved requires pass A unobserved")
            if _blank(row.get("exclusion_reason")):
                _error(errors, "missing_exclusion_reason", f"{row_label}: unobserved requires exclusion_reason")
            if not _blank(row.get("pass_b_saved_at")) or not _blank(row.get("pass_b_mode_agreement")):
                _error(errors, "incoherent_unobserved", f"{row_label}: unobserved rows cannot contain Pass B")
            _validate_revision(
                row.get("pass_b_revision"),
                row_label=row_label,
                field_name="pass_b_revision",
                errors=errors,
                minimum=0,
            )
        elif status == "excluded_with_reason" and _blank(row.get("exclusion_reason")):
            _error(errors, "missing_exclusion_reason", f"{row_label}: excluded_with_reason requires exclusion_reason")
        elif status == "pass_a_complete":
            if not _blank(row.get("pass_b_saved_at")) or not _blank(row.get("pass_b_mode_agreement")):
                _error(errors, "pass_b_before_complete", f"{row_label}: Pass B must remain blank after Pass A only")
            _validate_revision(
                row.get("pass_b_revision"),
                row_label=row_label,
                field_name="pass_b_revision",
                errors=errors,
                minimum=0,
            )

        _validate_iso_timestamp(
            row.get("updated_at"),
            row_label=row_label,
            field_name="updated_at",
            errors=errors,
            required=required_a,
        )

    if frozenset(seen) != EXPECTED_EVENT_ID_SET:
        _error(errors, "wrong_event_set", "normalized export event IDs do not match the seven frozen IDs")
    if len(orders) == len(rows) and sorted(orders) != list(range(1, len(EXPECTED_EVENT_IDS) + 1)):
        _error(errors, "wrong_randomized_order", "randomized_order must be a unique permutation of 1..7")
    return errors


def validate_tool_export(
    path: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    fieldnames, rows = _read_csv(path, errors)
    errors.extend(validate_tool_export_rows(fieldnames, rows, root=root))
    return {
        "status": "pass" if not errors else "fail",
        "mode": "tool_export",
        "path": str(path),
        "row_count": len(rows),
        "errors": errors,
    }


def validate_unobserved_rows(
    fieldnames: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    _validate_header(
        fieldnames,
        UNOBSERVED_COLUMNS,
        label="unobserved",
        errors=errors,
        check_prohibited=False,
    )
    if len(rows) != len(UNOBSERVED_EVENT_IDS):
        _error(
            errors,
            "wrong_unobserved_count",
            f"unobserved table must contain exactly {len(UNOBSERVED_EVENT_IDS)} rows",
        )
    seen: list[str] = []
    for index, row in enumerate(rows, start=2):
        row_label = f"unobserved row {index}"
        event_id = _text(row.get("event_id"))
        seen.append(event_id)
        if event_id not in UNOBSERVED_EVENT_ID_SET:
            _error(errors, "unexpected_unobserved_event", f"{row_label}: unexpected event_id={event_id!r}")
        if event_id in seen[:-1]:
            _error(errors, "duplicate_unobserved_event", f"{row_label}: duplicate event_id={event_id!r}")
        if _text(row.get("observability_status")) != "unobserved":
            _error(errors, "wrong_observability_status", f"{row_label}: status must be unobserved")
        if _blank(row.get("exclusion_reason")):
            _error(errors, "missing_exclusion_reason", f"{row_label}: exclusion_reason is required")
        if _text(row.get("protocol_version")) != PROTOCOL_VERSION:
            _error(errors, "wrong_protocol", f"{row_label}: protocol_version must be {PROTOCOL_VERSION}")
        significant_burn = _text(row.get("significant_burn")).lower()
        if significant_burn not in {"", "null"}:
            _error(
                errors,
                "significant_burn_defined",
                f"{row_label}: significant_burn must remain blank or null",
            )
        if "2026" in event_id or "2026" in _text(row.get("exclusion_reason")):
            _error(errors, "data_2026", f"{row_label}: 2026 data is not allowed")
    if frozenset(seen) != UNOBSERVED_EVENT_ID_SET:
        _error(errors, "wrong_unobserved_set", "unobserved event IDs do not match the two frozen exclusions")
    if any(event_id in EXPECTED_EVENT_ID_SET for event_id in seen):
        _error(errors, "calibration_event_in_unobserved", "calibration events must remain in the main queue")
    return errors


def build_manifest_from_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    seed: int = RANDOMIZATION_SEED,
) -> dict[str, Any]:
    ordered_rows = sorted(rows, key=lambda row: int(_text(row.get("randomized_order")) or "0"))
    return {
        "calibration_round": CALIBRATION_ROUND,
        "data_2026_used": False,
        "earth_engine_queries_made": False,
        "event_count": len(EXPECTED_EVENT_IDS),
        "events": [
            {
                "event_id": _text(row.get("event_id")),
                "multispectral_panel_path": _text(row.get("multispectral_panel_path")),
                "randomized_order": int(_text(row.get("randomized_order")) or "0"),
                "temporal_panel_path": _text(row.get("temporal_panel_path")),
            }
            for row in ordered_rows
        ],
        "labels_created": False,
        "manifest_schema_version": "human-review-calibration-manifest-v1",
        "prohibited_calibration_columns": [
            "frp",
            "firms_confidence",
            "dnbr_median",
            "dnbr_p90",
            "area",
            "model_score",
            "predicted_class",
            "significant_burn",
        ],
        "protocol_version": PROTOCOL_VERSION,
        "randomization": {
            "algorithm": "random.Random(seed).shuffle",
            "seed": seed,
            "source_event_ids": sorted(EXPECTED_EVENT_IDS),
        },
        "review_completed": False,
        "significant_burn_defined": False,
        "scientific_fields_initially_blank": [
            "reviewer_id",
            "reviewed_at",
            "visible_burn_scar",
            "scar_confidence",
            "event_association",
            "competing_land_change",
            "mode_agreement",
            "reviewer_notes",
            "exclusion_reason",
            "adjudication_notes",
        ],
        "quicklook_version": QUICKLOOK_VERSION,
    }


def validate_manifest(
    path: Path,
    *,
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not path.is_file():
        _error(errors, "missing_file", f"manifest not found: {path}")
        return errors
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _error(errors, "manifest_read_error", f"{path}: {exc}")
        return errors
    expected = build_manifest_from_rows(rows)
    if actual != expected:
        _error(errors, "manifest_mismatch", "manifest does not match the deterministic calibration rows")
    for flag in ("labels_created", "review_completed", "significant_burn_defined", "data_2026_used", "earth_engine_queries_made"):
        if actual.get(flag) is not False:
            _error(errors, "manifest_scope_violation", f"manifest {flag} must be false")
    return errors


def validate_artifacts(
    *,
    root: Path = ROOT,
    calibration_path: Path = CALIBRATION_PATH,
    unobserved_path: Path = UNOBSERVED_PATH,
    manifest_path: Path = MANIFEST_PATH,
    require_empty: bool = False,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    calibration_fields, calibration_rows = _read_csv(calibration_path, errors)
    errors.extend(
        validate_calibration_rows(
            calibration_fields,
            calibration_rows,
            root=root,
            require_empty=require_empty,
        )
    )
    unobserved_fields, unobserved_rows = _read_csv(unobserved_path, errors)
    errors.extend(validate_unobserved_rows(unobserved_fields, unobserved_rows))
    errors.extend(validate_manifest(manifest_path, rows=calibration_rows))
    return {
        "status": "pass" if not errors else "fail",
        "calibration_row_count": len(calibration_rows),
        "unobserved_row_count": len(unobserved_rows),
        "event_ids": [_text(row.get("event_id")) for row in calibration_rows],
        "randomized_order": [
            int(_text(row.get("randomized_order")))
            for row in calibration_rows
            if _text(row.get("randomized_order")).isdigit()
        ],
        "labels_created": False,
        "significant_burn_defined": False,
        "earth_engine_queries_made": False,
        "data_2026_used": False,
        "errors": errors,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the FirePA blinded human-review calibration contract."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check-empty-calibration",
        action="store_true",
        help="validate the repository's empty round1 calibration queue",
    )
    modes.add_argument(
        "--validate-completed-review",
        metavar="CSV",
        help="validate a completed review CSV without changing it",
    )
    modes.add_argument(
        "--validate-tool-export",
        metavar="CSV",
        help="validate the normalized CSV exported by the local two-pass tool",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="write the validation result as JSON to PATH",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.check_empty_calibration and not args.validate_completed_review and not args.validate_tool_export:
        parser.error(
            "choose --check-empty-calibration, --validate-completed-review CSV, "
            "or --validate-tool-export CSV"
        )

    if args.validate_tool_export:
        tool_path = Path(args.validate_tool_export).expanduser()
        if not tool_path.is_absolute():
            tool_path = (Path.cwd() / tool_path).resolve()
        result = validate_tool_export(tool_path, root=ROOT)
        result["calibration_path"] = str(tool_path)
        mode = "tool_export"
    elif args.validate_completed_review:
        calibration_path = Path(args.validate_completed_review).expanduser()
        if not calibration_path.is_absolute():
            calibration_path = (Path.cwd() / calibration_path).resolve()
        require_empty = False
        mode = "completed_review"
    else:
        calibration_path = CALIBRATION_PATH
        require_empty = True
        mode = "empty_calibration"

    if not args.validate_tool_export:
        result = validate_artifacts(
            root=ROOT,
            calibration_path=calibration_path,
            require_empty=require_empty,
        )
        result["mode"] = mode
        result["calibration_path"] = str(calibration_path)
    if args.report:
        report_path = Path(args.report).expanduser()
        if not report_path.is_absolute():
            report_path = (Path.cwd() / report_path).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
