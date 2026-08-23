"""Read-only summary and deterministic triage for imported blind AI calibration."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.human_review_schema import (  # noqa: E402
    CALIBRATION_ROUND,
    COMPETING_LAND_CHANGE_CODES,
    EVENT_ASSOCIATION_CODES,
    MODE_AGREEMENT_CODES,
    SCAR_CONFIDENCE_CODES,
    VISIBLE_BURN_SCAR_CODES,
)
from fuegopa.blind_control_round import candidate_view_from_r1_row  # noqa: E402


DEFAULT_DATABASE = ROOT / "outputs/human_review/firepa_human_review.sqlite3"
DEFAULT_MAPPING = ROOT / "outputs/human_review/private/calibration_r1_case_map.csv"
DEFAULT_IMPORT_REPORT = ROOT / "outputs/human_review/blind_ai_calibration_r1_import.json"
EXPECTED_CASE_IDS = tuple(f"CASE-{index:03d}" for index in range(1, 8))
AI_REVIEWER_TYPE = "ai_assisted"
AI_LABEL_STATUS = "provisional_pseudolabel"
ADJUDICATION_COMPETITOR_CODES = {
    "agriculture_or_harvest",
    "mixed",
    "unknown",
}
EXPLICIT_CONFOUNDER_CODES = {
    "agriculture_or_harvest",
    "cloud_or_haze",
    "soil_exposure",
    "mixed",
}
OBSERVATION_FIELDS = (
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "pass_a_notes",
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
    "pass_b_notes",
    "adjudication_notes",
)


class CalibrationSummaryError(ValueError):
    """Raised when the imported calibration cannot be profiled safely."""


def _read_mapping(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(EXPECTED_CASE_IDS):
        raise CalibrationSummaryError("The private mapping must contain exactly seven cases")
    mapping = {str(row.get("event_id") or ""): str(row.get("case_id") or "") for row in rows}
    if set(mapping.values()) != set(EXPECTED_CASE_IDS) or "" in mapping:
        raise CalibrationSummaryError("The private mapping does not contain the exact CASE set")
    return mapping


def _read_import_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "present": True,
        "status": payload.get("status"),
        "case_count": payload.get("case_count"),
        "inserted": payload.get("inserted"),
        "unchanged": payload.get("unchanged"),
        "database_written": payload.get("database_written"),
        "ground_truth": payload.get("ground_truth"),
        "final_scientific_labels_created": payload.get("final_scientific_labels_created"),
        "errors": list(payload.get("errors") or []),
    }


def _read_rows(database: Path) -> tuple[list[dict[str, Any]], list[str], int]:
    if not database.is_file():
        raise CalibrationSummaryError(f"SQLite database not found: {database}")
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(reviews)")]
        required = {
            "reviewer_type",
            "label_status",
            "pass_a_visible_burn_scar",
            "pass_a_scar_confidence",
            "pass_a_event_association",
            "pass_a_competing_land_change",
            "pass_b_mode_agreement",
            "pass_b_confidence_after",
            "pass_b_requires_adjudication",
            "review_status",
        }
        if not required.issubset(columns):
            raise CalibrationSummaryError("SQLite reviews table does not contain the imported AI contract")
        total_items = int(
            connection.execute(
                "SELECT COUNT(*) FROM review_items WHERE round_id = ?",
                (CALIBRATION_ROUND,),
            ).fetchone()[0]
        )
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM reviews WHERE round_id = ? AND reviewer_type = ? AND label_status = ? "
                "ORDER BY event_id",
                (CALIBRATION_ROUND, AI_REVIEWER_TYPE, AI_LABEL_STATUS),
            )
        ]
        return rows, columns, total_items
    finally:
        connection.close()


def _distribution(rows: Iterable[Mapping[str, Any]], field: str, allowed: Iterable[str]) -> dict[str, int]:
    counts = Counter(str(row.get(field) or "") for row in rows)
    return {value: int(counts.get(value, 0)) for value in allowed}


def _as_bool(value: Any) -> bool:
    return value in (True, 1, "1", "true", "True")


def _case_sort(case_id: str) -> tuple[int, str]:
    match = re.fullmatch(r"CASE-(\d{3})", case_id)
    return (int(match.group(1)), case_id) if match else (999, case_id)


def _case_analysis(row: Mapping[str, Any], event_to_case: Mapping[str, str]) -> dict[str, Any]:
    case_id = event_to_case.get(str(row.get("event_id") or ""), "")
    visible = str(row.get("pass_a_visible_burn_scar") or "")
    pass_a_confidence = str(row.get("pass_a_scar_confidence") or "")
    association = str(row.get("pass_a_event_association") or "")
    competitor = str(row.get("pass_a_competing_land_change") or "")
    agreement = str(row.get("pass_b_mode_agreement") or "")
    pass_b_confidence = str(row.get("pass_b_confidence_after") or "")
    requires_adjudication = _as_bool(row.get("pass_b_requires_adjudication"))
    adjudication_reasons: list[str] = []
    if visible == "ambiguous":
        adjudication_reasons.append("pass_a_visible_burn_scar=ambiguous")
    if pass_a_confidence == "low":
        adjudication_reasons.append("pass_a_scar_confidence=low")
    if association == "indeterminate":
        adjudication_reasons.append("pass_a_event_association=indeterminate")
    if agreement == "disagree":
        adjudication_reasons.append("pass_b_mode_agreement=disagree")
    if requires_adjudication:
        adjudication_reasons.append("pass_b_requires_adjudication=true")

    specialized_reasons: list[str] = []
    if competitor in ADJUDICATION_COMPETITOR_CODES:
        specialized_reasons.append(f"competing_land_change={competitor}")
    if competitor == "cloud_or_haze":
        specialized_reasons.append("competing_land_change=cloud_or_haze")
    if pass_a_confidence and pass_b_confidence and pass_a_confidence != pass_b_confidence:
        specialized_reasons.append("confidence_changed_between_passes")

    needs_adjudication = bool(adjudication_reasons)
    if needs_adjudication:
        proposed_status = "needs_adjudication"
    elif row.get("pass_b_mode_agreement") and row.get("pass_b_confidence_after"):
        proposed_status = "pass_b_complete"
    elif row.get("pass_a_visible_burn_scar"):
        proposed_status = "pass_a_complete"
    else:
        proposed_status = "pending"

    return {
        "case_id": case_id,
        "pass_a_visible_burn_scar": visible,
        "pass_a_scar_confidence": pass_a_confidence,
        "pass_a_event_association": association,
        "pass_a_competing_land_change": competitor,
        "pass_b_mode_agreement": agreement,
        "pass_b_confidence_after": pass_b_confidence,
        "pass_b_requires_adjudication": requires_adjudication,
        "current_review_status": str(row.get("review_status") or ""),
        "proposed_review_status": proposed_status,
        "adjudication_reasons": adjudication_reasons,
        "specialized_review_reasons": specialized_reasons,
        "confidence_changed": pass_a_confidence != pass_b_confidence,
        "limitation_in_notes": False,
        "notes_used_for_triage": False,
    }


def summarize(
    *,
    database: Path = DEFAULT_DATABASE,
    mapping_path: Path = DEFAULT_MAPPING,
    import_report_path: Path = DEFAULT_IMPORT_REPORT,
) -> dict[str, Any]:
    """Return a deterministic, read-only summary of the imported calibration."""

    event_to_case = _read_mapping(mapping_path)
    rows, review_columns, total_items = _read_rows(database)
    if total_items != len(EXPECTED_CASE_IDS) or len(rows) != len(EXPECTED_CASE_IDS):
        raise CalibrationSummaryError("The imported calibration must contain exactly seven review items and AI rows")
    cases = sorted((_case_analysis(row, event_to_case) for row in rows), key=lambda item: _case_sort(item["case_id"]))
    if [case["case_id"] for case in cases] != list(EXPECTED_CASE_IDS):
        raise CalibrationSummaryError("Imported AI rows do not map to the exact CASE set")

    confidence_changes = Counter(
        f"{case['pass_a_scar_confidence']}->{case['pass_b_confidence_after']}"
        for case in cases
    )
    confidence_change_cases: dict[str, list[str]] = {}
    for case in cases:
        transition = f"{case['pass_a_scar_confidence']}->{case['pass_b_confidence_after']}"
        confidence_change_cases.setdefault(transition, []).append(case["case_id"])

    candidate_cases = sorted(
        (
            candidate_view_from_r1_row(row, case_id=event_to_case[str(row.get("event_id") or "")])
            for row in rows
        ),
        key=lambda item: _case_sort(item["case_id"]),
    )
    candidate_adjudication_cases = [
        case["case_id"] for case in candidate_cases if case["needs_adjudication"]
    ]
    candidate_expert_required_cases = [
        case["case_id"] for case in candidate_cases if case["expert_review_priority"] == "required"
    ]
    candidate_expert_recommended_cases = [
        case["case_id"] for case in candidate_cases if case["expert_review_priority"] == "recommended"
    ]

    confounder_cases = {
        code: [case["case_id"] for case in cases if case["pass_a_competing_land_change"] == code]
        for code in EXPLICIT_CONFOUNDER_CODES
    }
    any_competing_cases = [
        case["case_id"]
        for case in cases
        if case["pass_a_competing_land_change"] not in {"", "none_visible"}
    ]
    ambiguous_cases = [case["case_id"] for case in cases if case["pass_a_visible_burn_scar"] == "ambiguous"]
    low_confidence_pass_a_cases = [case["case_id"] for case in cases if case["pass_a_scar_confidence"] == "low"]
    low_confidence_pass_b_cases = [case["case_id"] for case in cases if case["pass_b_confidence_after"] == "low"]
    indeterminate_cases = [case["case_id"] for case in cases if case["pass_a_event_association"] == "indeterminate"]
    partial_agreement_cases = [case["case_id"] for case in cases if case["pass_b_mode_agreement"] == "partially_agree"]
    adjudication_cases = [case["case_id"] for case in cases if case["proposed_review_status"] == "needs_adjudication"]
    specialized_cases = [case["case_id"] for case in cases if case["specialized_review_reasons"]]
    additional_review_cases = sorted(set(adjudication_cases) | set(specialized_cases), key=_case_sort)

    observation_values = [
        str(row.get(field) or "")
        for row in rows
        for field in OBSERVATION_FIELDS
    ]
    future_values = sorted({value for value in observation_values if "2026" in value})
    if future_values:
        raise CalibrationSummaryError("A scientific observation field contains a disallowed future-period value")

    import_report = _read_import_report(import_report_path)
    prohibited_schema_fields = sorted(
        field for field in review_columns if field in {"significant_burn", "ground_truth"}
    )
    return {
        "case_count": len(cases),
        "review_item_count": total_items,
        "reviewer_count": len({str(row.get("reviewer_id") or "") for row in rows}),
        "reviewer_type_distribution": dict(sorted(Counter(str(row.get("reviewer_type") or "") for row in rows).items())),
        "label_status_distribution": dict(sorted(Counter(str(row.get("label_status") or "") for row in rows).items())),
        "distributions": {
            "pass_a_visible_burn_scar": _distribution(rows, "pass_a_visible_burn_scar", VISIBLE_BURN_SCAR_CODES),
            "pass_a_scar_confidence": _distribution(rows, "pass_a_scar_confidence", SCAR_CONFIDENCE_CODES),
            "pass_a_event_association": _distribution(rows, "pass_a_event_association", EVENT_ASSOCIATION_CODES),
            "pass_a_competing_land_change": _distribution(rows, "pass_a_competing_land_change", COMPETING_LAND_CHANGE_CODES),
            "pass_b_mode_agreement": _distribution(rows, "pass_b_mode_agreement", MODE_AGREEMENT_CODES),
            "pass_b_confidence_after": _distribution(rows, "pass_b_confidence_after", SCAR_CONFIDENCE_CODES),
        },
        "confidence_changes": {
            "distribution": {key: int(confidence_changes[key]) for key in sorted(confidence_changes)},
            "cases": {key: sorted(value, key=_case_sort) for key, value in sorted(confidence_change_cases.items())},
            "changed_case_count": sum(1 for case in cases if case["confidence_changed"]),
        },
        "counts": {
            "adjudications_requested": sum(case["pass_b_requires_adjudication"] for case in cases),
            "ambiguous_cases": len(ambiguous_cases),
            "low_confidence_pass_a_cases": len(low_confidence_pass_a_cases),
            "low_confidence_pass_b_cases": len(low_confidence_pass_b_cases),
            "indeterminate_association_cases": len(indeterminate_cases),
            "confounder_cases": len(any_competing_cases),
            "explicit_confounder_cases": len({case_id for values in confounder_cases.values() for case_id in values}),
            "partial_agreement_cases": len(partial_agreement_cases),
        },
        "case_sets": {
            "ambiguous_cases": ambiguous_cases,
            "low_confidence_pass_a_cases": low_confidence_pass_a_cases,
            "low_confidence_pass_b_cases": low_confidence_pass_b_cases,
            "indeterminate_association_cases": indeterminate_cases,
            "confounder_cases": confounder_cases,
            "any_competing_land_change_cases": any_competing_cases,
            "partial_agreement_cases": partial_agreement_cases,
            "needs_adjudication_cases": adjudication_cases,
            "specialized_review_cases": specialized_cases,
            "recommended_additional_review_cases": additional_review_cases,
        },
        "candidate_reevaluation": {
            "cases": candidate_cases,
            "case_sets": {
                "needs_adjudication_cases": candidate_adjudication_cases,
                "expert_review_required_cases": candidate_expert_required_cases,
                "expert_review_recommended_cases": candidate_expert_recommended_cases,
                "expert_review_any_cases": sorted(
                    set(candidate_expert_required_cases) | set(candidate_expert_recommended_cases),
                    key=_case_sort,
                ),
            },
            "changes_from_draft_v2": {
                "adjudication_cases_unchanged": candidate_adjudication_cases == adjudication_cases,
                "legacy_cloud_or_haze_reclassified_as_limitation": [
                    case["case_id"] for case in candidate_cases if case["legacy_competing_land_change"] == "cloud_or_haze"
                ],
                "new_expert_recommended_cases": candidate_expert_recommended_cases,
                "notes_used_for_limitation": False,
            },
            "triage_rules": {
                "needs_adjudication_when": [
                    "pass_a_visible_burn_scar=ambiguous",
                    "pass_a_scar_confidence=low",
                    "pass_a_event_association=indeterminate",
                    "pass_b_mode_agreement=disagree",
                    "pass_b_requires_adjudication=true",
                ],
                "expert_required_when": [
                    "needs_adjudication=true",
                    "competing_land_change in agriculture_or_harvest, mixed, or unknown",
                    "observation_limitation != none",
                    "confidence changes between Pass A and Pass B",
                ],
                "expert_recommended_when": [
                    "competing_land_change in soil_exposure, vegetation_phenology, moisture_or_flooding, water, or urban_or_construction",
                ],
                "notes_control_administrative_rules": False,
            },
        },
        "triage_rules": {
            "needs_adjudication_when": [
                "pass_a_visible_burn_scar=ambiguous",
                "pass_a_scar_confidence=low",
                "pass_a_event_association=indeterminate",
                "pass_b_mode_agreement=disagree",
                "pass_b_requires_adjudication=true",
            ],
            "specialized_review_when": [
                "competing_land_change in agriculture_or_harvest, mixed, or unknown",
                "legacy R1 cloud_or_haze is handled only in the candidate reevaluation view",
                "confidence changes between Pass A and Pass B",
            ],
            "partially_agree_alone_requires_adjudication": False,
        },
        "cases": cases,
        "contract": {
            "import_report": import_report,
            "review_columns_include_scientific_label_fields": bool(prohibited_schema_fields),
            "review_columns_with_prohibited_label_fields": prohibited_schema_fields,
            "ground_truth_present": False,
            "final_scientific_labels_created": False,
            "significant_burn_present": False,
            "future_period_data_used": False,
            "scientific_observation_fields_checked_for_2026": list(OBSERVATION_FIELDS),
        },
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    distributions = summary["distributions"]
    counts = summary["counts"]
    lines = [
        "# Blind AI calibration R1 summary",
        "",
        "Read-only deterministic summary of the imported seven-case calibration.",
        "The values are observations and administrative triage evidence, not scientific classes.",
        "",
        "## Counts",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Adjudications requested by Pass B: {counts['adjudications_requested']}",
        f"- Ambiguous visual observations: {counts['ambiguous_cases']}",
        f"- Low Pass A confidence: {counts['low_confidence_pass_a_cases']}",
        f"- Low Pass B confidence: {counts['low_confidence_pass_b_cases']}",
        f"- Indeterminate association: {counts['indeterminate_association_cases']}",
        f"- Cases with a competing land-change code: {counts['confounder_cases']}",
        f"- Partial agreement: {counts['partial_agreement_cases']}",
        "",
        "## Distributions",
        "",
    ]
    for field, values in distributions.items():
        lines.append(f"- `{field}`: " + ", ".join(f"{key}={value}" for key, value in values.items() if value))
    lines.extend(
        [
            "",
            "## Proposed triage",
            "",
            "- Needs adjudication: " + ", ".join(summary["case_sets"]["needs_adjudication_cases"]),
            "- Specialized review: " + ", ".join(summary["case_sets"]["specialized_review_cases"]),
            "- Additional review union: " + ", ".join(summary["case_sets"]["recommended_additional_review_cases"]),
            "",
            "The proposal does not create final labels, ground truth, or a formal 28-event round.",
            "",
            "## Candidate v1 reevaluation",
            "",
            "- Needs adjudication: " + ", ".join(summary["candidate_reevaluation"]["case_sets"]["needs_adjudication_cases"]),
            "- Expert review required: " + ", ".join(summary["candidate_reevaluation"]["case_sets"]["expert_review_required_cases"]),
            "- Expert review recommended: " + ", ".join(summary["candidate_reevaluation"]["case_sets"]["expert_review_recommended_cases"]),
            "- Legacy `cloud_or_haze` reclassified as structured limitation: "
            + ", ".join(summary["candidate_reevaluation"]["changes_from_draft_v2"]["legacy_cloud_or_haze_reclassified_as_limitation"]),
            "- Notes used to control administrative rules: no",
            "",
            "| CASE ID | candidate competing | limitation | adjudication | expert priority | reasons |",
            "|---|---|---|---|---|---|",
        ]
    )
    for case in summary["candidate_reevaluation"]["cases"]:
        lines.append(
            "| {case_id} | {candidate_competing_land_change} | {observation_limitation} | {needs_adjudication} | {expert_review_priority} | {reasons} |".format(
                case_id=case["case_id"],
                candidate_competing_land_change=case["candidate_competing_land_change"],
                observation_limitation=case["observation_limitation"],
                needs_adjudication=case["needs_adjudication"],
                expert_review_priority=case["expert_review_priority"],
                reasons=", ".join(case["expert_review_reasons"]),
            )
        )
    lines.extend(
        [
            "",
            "The candidate view is read-only and does not migrate or rewrite R1 SQLite rows.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--import-report", type=Path, default=DEFAULT_IMPORT_REPORT)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path, help="Optional report path; SQLite remains read-only")
    args = parser.parse_args(argv)
    summary = summarize(
        database=args.database,
        mapping_path=args.mapping,
        import_report_path=args.import_report,
    )
    rendered = _markdown(summary) if args.format == "markdown" else json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
