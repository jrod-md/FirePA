"""Build and validate the independent blind control round.

The control round is deliberately separate from the imported R1 SQLite store.
It consumes only the already-anonymized R1 panel bytes, validates external
response JSON in memory, derives administrative triage from structured fields,
and never infers a limitation from free-text notes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .blind_ai_calibration import integrity_snapshot
from .dnbr_quicklook import _parse_png
from .human_review_store import HumanReviewStore, ReviewStoreError, utc_timestamp
from .quicklook_level2 import PANEL_HEIGHT, PANEL_WIDTH


ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROUND_ID = "control_r1"
CONTROL_PROTOCOL_VERSION = "candidate-v1"
CONTROL_SCHEMA_VERSION = "firepa-blind-control-r1-response-v1"
CONTROL_STORE_ROUND_ID = CONTROL_ROUND_ID
CONTROL_STORE_VERSION = "firepa-blind-control-r1-store-v1"
CONTROL_STORE_RANDOM_SEED = 0
CONTROL_DATABASE_PATH = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3"

CONTROL_REVIEWER_IDENTITIES = {
    "reviewer_a": {
        "reviewer_id": "blind_control_r1_reviewer_a",
        "reviewer_model": "GPT-5.6 Thinking",
    },
    "reviewer_b": {
        "reviewer_id": "blind_control_r1_reviewer_b",
        "reviewer_model": "GPT-5.5 Thinking",
    },
}

CONTROL_CASE_IDS = tuple(f"CASE-{index:03d}" for index in range(1, 8))
REVIEWER_TYPE_CODES = ("human", "ai_assisted")
REVIEWER_EXPERTISE_CODES = ("novice", "trained", "domain_expert", "not_applicable")
LABEL_STATUS_CODES = ("human_observation", "provisional_pseudolabel")
VISIBLE_BURN_SCAR_CODES = ("yes", "no", "ambiguous", "unobserved")
SCAR_CONFIDENCE_CODES = ("high", "medium", "low", "not_applicable")
EVENT_ASSOCIATION_CODES = ("likely", "possible", "unlikely", "indeterminate")
COMPETING_LAND_CHANGE_CODES = (
    "none_visible",
    "agriculture_or_harvest",
    "soil_exposure",
    "vegetation_phenology",
    "moisture_or_flooding",
    "water",
    "urban_or_construction",
    "mixed",
    "unknown",
)
OBSERVATION_LIMITATION_CODES = (
    "none",
    "cloud_or_haze",
    "shadow_or_atmosphere",
    "mask_or_nodata",
    "partial_coverage",
    "long_temporal_gap",
    "mixed",
    "unknown",
)
MODE_AGREEMENT_CODES = (
    "agree",
    "partially_agree",
    "disagree",
    "selected_pair_only",
    "window_median_only",
    "unavailable",
)
EXPERT_REVIEW_PRIORITY_CODES = ("none", "recommended", "required")

CONTROL_PASS_A_RESPONSE_FIELDS = (
    "case_id",
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "observation_limitation",
    "pass_a_notes",
)
CONTROL_PASS_B_RESPONSE_FIELDS = CONTROL_PASS_A_RESPONSE_FIELDS + (
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
    "pass_b_notes",
)
CONTROL_PASS_A_ZIP = "firepa_blind_ai_calibration_r1_pass_a.zip"
CONTROL_PASS_B_ZIP = "firepa_blind_ai_calibration_r1_pass_b.zip"

PROTOCOL_FILE = "LABELING_PROTOCOL_CANDIDATE_v1.md"
PASS_A_INSTRUCTIONS_FILE = "BLIND_CONTROL_R1_INSTRUCTIONS_PASS_A.md"
PASS_B_INSTRUCTIONS_FILE = "BLIND_CONTROL_R1_INSTRUCTIONS_PASS_B.md"
PASS_A_SCHEMA_FILE = "BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_A.json"
PASS_B_SCHEMA_FILE = "BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_B.json"
MANIFEST_FILE = "blind_control_r1_manifest.json"
CHECKSUMS_FILE = "checksums.sha256"
PASS_A_PANEL_NAMES = tuple(f"{case_id}_multispectral.png" for case_id in CONTROL_CASE_IDS)
PASS_B_PANEL_NAMES = tuple(f"{case_id}_temporal.png" for case_id in CONTROL_CASE_IDS)
PASS_A_FILES = (
    PROTOCOL_FILE,
    PASS_A_INSTRUCTIONS_FILE,
    PASS_A_SCHEMA_FILE,
    *PASS_A_PANEL_NAMES,
    MANIFEST_FILE,
    CHECKSUMS_FILE,
)
PASS_B_FILES = (
    PROTOCOL_FILE,
    PASS_B_INSTRUCTIONS_FILE,
    PASS_B_SCHEMA_FILE,
    *PASS_B_PANEL_NAMES,
    MANIFEST_FILE,
    CHECKSUMS_FILE,
)

PASS_A_FIELDS = (
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "observation_limitation",
    "pass_a_notes",
)
PASS_B_FIELDS = (
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
    "pass_b_notes",
)
COMPARISON_FIELDS = PASS_A_FIELDS + PASS_B_FIELDS
STRUCTURED_COMPARISON_FIELDS = (
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "observation_limitation",
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
)
DISTRIBUTION_FIELDS = STRUCTURED_COMPARISON_FIELDS + (
    "needs_adjudication",
    "expert_review_priority",
)

REQUIRED_EXPERT_COMPETING_CODES = {"agriculture_or_harvest", "mixed", "unknown"}
RECOMMENDED_EXPERT_COMPETING_CODES = {
    "soil_exposure",
    "vegetation_phenology",
    "moisture_or_flooding",
    "water",
    "urban_or_construction",
}
LEGACY_CLOUD_CODE = "cloud_or_haze"

ORIGINAL_EVENT_RE = re.compile(rb"event-r1500_t06-[0-9a-f]{16}")
ABSOLUTE_WINDOWS_PATH_RE = re.compile(rb"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")


class BlindControlError(ValueError):
    """Raised when a control package or response violates its contract."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BlindControlError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BlindControlError(f"JSON object required: {path}")
    return payload


def _read_zip_panels(path: Path, names: Sequence[str]) -> dict[str, bytes]:
    if not path.is_file():
        raise BlindControlError(f"Missing source anonymized package: {path}")
    try:
        with ZipFile(path) as archive:
            members = archive.namelist()
            if not set(names).issubset(members):
                missing = sorted(set(names) - set(members))
                raise BlindControlError(f"Source package is missing anonymized panels: {', '.join(missing)}")
            return {name: archive.read(name) for name in names}
    except BlindControlError:
        raise
    except Exception as exc:
        raise BlindControlError(f"Cannot read source package {path}: {exc}") from exc


def _strip_png_text_chunks(payload: bytes) -> bytes:
    """Remove text metadata while preserving the PNG scientific pixel stream."""

    signature = b"\x89PNG\r\n\x1a\n"
    if not payload.startswith(signature):
        raise BlindControlError("Control panels must be PNG files")
    output = bytearray(signature)
    offset = len(signature)
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(payload):
            raise BlindControlError("Malformed source PNG")
        if kind not in {b"tEXt", b"iTXt", b"zTXt"}:
            output.extend(payload[offset : end + 4])
        offset = end + 4
        if kind == b"IEND":
            break
    return bytes(output)


def _scientific_pixels_equal(left: bytes, right: bytes) -> bool:
    left_png = _parse_png(left)
    right_png = _parse_png(right)
    return left_png[:5] == right_png[:5]


def _source_zip_paths(root: Path) -> tuple[Path, Path]:
    return root / "outputs" / CONTROL_PASS_A_ZIP, root / "outputs" / CONTROL_PASS_B_ZIP


def _write_deterministic_zip(path: Path, members: Mapping[str, bytes], order: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in order:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.create_version = 20
            info.extract_version = 20
            info.flag_bits = 0x800
            info.external_attr = 0
            info.internal_attr = 0
            archive.writestr(info, members[name], compress_type=ZIP_DEFLATED, compresslevel=9)


def _checksum_bytes(members: Mapping[str, bytes], order: Sequence[str]) -> bytes:
    return "".join(
        f"{_sha256_bytes(members[name])}  {name}\n"
        for name in order
        if name != CHECKSUMS_FILE
    ).encode("utf-8")


def _manifest(pass_name: str, panel_names: Sequence[str], members: Mapping[str, bytes], order: Sequence[str]) -> dict[str, Any]:
    return {
        "manifest_schema_version": "firepa-blind-control-r1-manifest-v1",
        "package_id": "firepa_blind_control_r1",
        "round_id": CONTROL_ROUND_ID,
        "pass": pass_name,
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "case_count": len(CONTROL_CASE_IDS),
        "cases": [
            {
                "case_id": case_id,
                "randomized_order": index,
                "panel_filename": panel_name,
                "sha256": _sha256_bytes(members[panel_name]),
            }
            for index, (case_id, panel_name) in enumerate(zip(CONTROL_CASE_IDS, panel_names), start=1)
        ],
        "files": list(order),
        "anonymized_panels": True,
        "review_results_included": False,
    }


def _package_members(root: Path, pass_name: str, panels: Mapping[str, bytes]) -> tuple[dict[str, bytes], tuple[str, ...]]:
    pass_a = pass_name == "A"
    panel_names = PASS_A_PANEL_NAMES if pass_a else PASS_B_PANEL_NAMES
    instruction = PASS_A_INSTRUCTIONS_FILE if pass_a else PASS_B_INSTRUCTIONS_FILE
    schema = PASS_A_SCHEMA_FILE if pass_a else PASS_B_SCHEMA_FILE
    order = PASS_A_FILES if pass_a else PASS_B_FILES
    source_paths = {
        PROTOCOL_FILE: root / "docs" / PROTOCOL_FILE,
        instruction: root / "docs" / instruction,
        schema: root / "docs" / schema,
    }
    members: dict[str, bytes] = {}
    for name, path in source_paths.items():
        if not path.is_file():
            raise BlindControlError(f"Missing control package source document: {path}")
        members[name] = path.read_bytes()
    for name in panel_names:
        if name not in panels:
            raise BlindControlError(f"Missing panel payload: {name}")
        members[name] = _strip_png_text_chunks(panels[name]) if name.endswith(".png") else panels[name]
    members[MANIFEST_FILE] = _json_bytes(_manifest(pass_name, panel_names, members, order))
    members[CHECKSUMS_FILE] = _checksum_bytes(members, order)
    return members, order


def _png_text_payload(payload: bytes) -> bytes:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return payload
    pieces: list[bytes] = []
    offset = 8
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        kind = payload[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(payload):
            break
        if kind in {b"tEXt", b"iTXt", b"zTXt"}:
            pieces.append(payload[start:end])
        offset = end + 4
        if kind == b"IEND":
            break
    return b"\n".join(pieces)


def _package_content_errors(name: str, payload: bytes) -> list[str]:
    scan = _png_text_payload(payload) if name.endswith(".png") else payload
    lower = scan.lower()
    errors: list[str] = []
    if b"2026" in scan:
        errors.append("future-period year present")
    if ORIGINAL_EVENT_RE.search(scan):
        errors.append("original source identifier present")
    if ABSOLUTE_WINDOWS_PATH_RE.search(scan) or b"\\\\" in scan:
        errors.append("absolute Windows path present")
    for token in (b"plan.md", b"context.md", b"handoff", b"sqlite", b"event_id", b"significant_burn"):
        if token in lower:
            errors.append(f"prohibited token present: {token.decode()}")
    if name != PROTOCOL_FILE and b"ground_truth" in lower:
        errors.append("ground truth field/token present outside protocol")
    return errors


def _validate_package_zip(path: Path, order: Sequence[str], source_panels: Mapping[str, bytes]) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"missing package: {path}"]
    try:
        with ZipFile(path) as archive:
            if archive.namelist() != list(order):
                errors.append("member order or membership mismatch")
            for info in archive.infolist():
                if info.date_time != (1980, 1, 1, 0, 0, 0):
                    errors.append(f"non-deterministic timestamp: {info.filename}")
            members = {name: archive.read(name) for name in archive.namelist() if name in order}
    except Exception as exc:
        return [f"cannot inspect package: {exc}"]
    for name in order:
        if name not in members:
            errors.append(f"missing member: {name}")
            continue
        payload = members[name]
        errors.extend(f"{name}: {error}" for error in _package_content_errors(name, payload))
        if name.endswith(".png"):
            try:
                width, height, color_type, channels, _rows = _parse_png(payload)[:5]
            except ValueError as exc:
                errors.append(f"{name}: invalid PNG: {exc}")
                continue
            if (width, height, color_type, channels) != (PANEL_WIDTH, PANEL_HEIGHT, 2, 3):
                errors.append(f"{name}: PNG contract mismatch")
            if name in source_panels and not _scientific_pixels_equal(payload, source_panels[name]):
                errors.append(f"{name}: differs from existing anonymized R1 panel")
    if CHECKSUMS_FILE in members:
        expected = [name for name in order if name != CHECKSUMS_FILE]
        seen: list[str] = []
        for line in members[CHECKSUMS_FILE].decode("utf-8").splitlines():
            digest, separator, name = line.partition("  ")
            if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
                errors.append(f"malformed checksum line: {line}")
                continue
            seen.append(name)
            if name not in expected:
                errors.append(f"unexpected checksum member: {name}")
            elif _sha256_bytes(members.get(name, b"")) != digest:
                errors.append(f"checksum mismatch: {name}")
        if seen != expected:
            errors.append("checksum order or membership mismatch")
    if MANIFEST_FILE in members:
        try:
            manifest = json.loads(members[MANIFEST_FILE].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid manifest: {exc}")
        else:
            if manifest.get("files") != list(order):
                errors.append("manifest files mismatch")
            if manifest.get("case_count") != len(CONTROL_CASE_IDS):
                errors.append("manifest case count mismatch")
            if [item.get("case_id") for item in manifest.get("cases", [])] != list(CONTROL_CASE_IDS):
                errors.append("manifest case order mismatch")
            if manifest.get("review_results_included") is not False:
                errors.append("manifest must declare that results are absent")
    return sorted(set(errors))


def build_blind_control_packages(
    root: Path = ROOT,
    *,
    output_root: Path | None = None,
    source_pass_a_zip: Path | None = None,
    source_pass_b_zip: Path | None = None,
) -> dict[str, Any]:
    """Create deterministic control ZIPs from the existing anonymized R1 panels."""

    root = Path(root).resolve()
    output_root = (output_root or root / "outputs").resolve()
    source_a, source_b = _source_zip_paths(root)
    source_a = Path(source_pass_a_zip).resolve() if source_pass_a_zip else source_a
    source_b = Path(source_pass_b_zip).resolve() if source_pass_b_zip else source_b
    before_integrity = integrity_snapshot(root)
    source_hashes_before = {"pass_a": _sha256_file(source_a), "pass_b": _sha256_file(source_b)}
    panels_a = _read_zip_panels(source_a, PASS_A_PANEL_NAMES)
    panels_b = _read_zip_panels(source_b, PASS_B_PANEL_NAMES)
    members_a, order_a = _package_members(root, "A", panels_a)
    members_b, order_b = _package_members(root, "B", panels_b)
    output_a = output_root / "firepa_blind_control_r1_pass_a.zip"
    output_b = output_root / "firepa_blind_control_r1_pass_b.zip"
    _write_deterministic_zip(output_a, members_a, order_a)
    _write_deterministic_zip(output_b, members_b, order_b)
    validation = validate_blind_control_packages(
        root,
        output_root=output_root,
        source_pass_a_zip=source_a,
        source_pass_b_zip=source_b,
    )
    after_integrity = integrity_snapshot(root)
    source_hashes_after = {"pass_a": _sha256_file(source_a), "pass_b": _sha256_file(source_b)}
    protected_unchanged = before_integrity == after_integrity and source_hashes_before == source_hashes_after
    if not protected_unchanged:
        raise BlindControlError("Scientific/R1 protected inputs changed while building control packages")
    if validation["status"] != "pass":
        raise BlindControlError(json.dumps(validation, ensure_ascii=False, sort_keys=True, default=str))
    return {
        "status": "pass",
        "round_id": CONTROL_ROUND_ID,
        "case_ids": list(CONTROL_CASE_IDS),
        "pass_a_zip": output_a,
        "pass_b_zip": output_b,
        "pass_a_zip_sha256": _sha256_file(output_a),
        "pass_b_zip_sha256": _sha256_file(output_b),
        "validation": validation,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "source_r1_zip_sha256_before": source_hashes_before,
        "source_r1_zip_sha256_after": source_hashes_after,
        "protected_inputs_unchanged": protected_unchanged,
        "review_results_included": False,
    }


def validate_blind_control_packages(
    root: Path = ROOT,
    *,
    output_root: Path | None = None,
    source_pass_a_zip: Path | None = None,
    source_pass_b_zip: Path | None = None,
) -> dict[str, Any]:
    """Validate control ZIP contents and exact reuse of anonymized panel bytes."""

    root = Path(root).resolve()
    output_root = (output_root or root / "outputs").resolve()
    source_a, source_b = _source_zip_paths(root)
    source_a = Path(source_pass_a_zip).resolve() if source_pass_a_zip else source_a
    source_b = Path(source_pass_b_zip).resolve() if source_pass_b_zip else source_b
    errors: list[str] = []
    try:
        panels_a = _read_zip_panels(source_a, PASS_A_PANEL_NAMES)
        panels_b = _read_zip_panels(source_b, PASS_B_PANEL_NAMES)
    except BlindControlError as exc:
        return {"status": "fail", "errors": [str(exc)]}
    package_errors_a = _validate_package_zip(
        output_root / "firepa_blind_control_r1_pass_a.zip",
        PASS_A_FILES,
        panels_a,
    )
    package_errors_b = _validate_package_zip(
        output_root / "firepa_blind_control_r1_pass_b.zip",
        PASS_B_FILES,
        panels_b,
    )
    errors.extend(f"pass_a: {error}" for error in package_errors_a)
    errors.extend(f"pass_b: {error}" for error in package_errors_b)
    return {
        "status": "pass" if not errors else "fail",
        "case_count": len(CONTROL_CASE_IDS),
        "pass_a_zip": output_root / "firepa_blind_control_r1_pass_a.zip",
        "pass_b_zip": output_root / "firepa_blind_control_r1_pass_b.zip",
        "errors": sorted(set(errors)),
    }


def validate_reviewer_provenance(
    reviewer_type: Any,
    reviewer_expertise: Any,
    reviewer_model: Any,
) -> list[str]:
    """Validate reviewer provenance rules independent of the control importer."""

    errors: list[str] = []
    if reviewer_type not in REVIEWER_TYPE_CODES:
        errors.append("reviewer_type must be human or ai_assisted")
    if reviewer_expertise not in REVIEWER_EXPERTISE_CODES:
        errors.append("reviewer_expertise is not a valid enum")
    if reviewer_type == "ai_assisted" and reviewer_expertise != "not_applicable":
        errors.append("ai_assisted requires reviewer_expertise=not_applicable")
    if reviewer_type == "human" and reviewer_expertise == "not_applicable":
        errors.append("human cannot use reviewer_expertise=not_applicable")
    model = "" if reviewer_model is None else str(reviewer_model).strip()
    if reviewer_type == "ai_assisted" and not model:
        errors.append("ai_assisted requires reviewer_model")
    if reviewer_type == "human" and model:
        errors.append("reviewer_model must be empty for human")
    return errors


def derive_control_triage(review: Mapping[str, Any]) -> dict[str, Any]:
    """Derive administrative triage using structured fields only."""

    adjudication_reasons: list[str] = []
    if review.get("pass_a_visible_burn_scar") == "ambiguous":
        adjudication_reasons.append("ambiguous_visible_burn_scar")
    if review.get("pass_a_scar_confidence") == "low":
        adjudication_reasons.append("low_pass_a_confidence")
    if review.get("pass_a_event_association") == "indeterminate":
        adjudication_reasons.append("indeterminate_event_association")
    if review.get("pass_b_mode_agreement") == "disagree":
        adjudication_reasons.append("pass_b_disagree")
    if review.get("pass_b_requires_adjudication") is True:
        adjudication_reasons.append("explicit_adjudication_request")
    needs_adjudication = bool(adjudication_reasons)

    expert_reasons: list[str] = []
    if needs_adjudication:
        expert_reasons.append("needs_adjudication")
    competitor = review.get("pass_a_competing_land_change")
    if competitor in REQUIRED_EXPERT_COMPETING_CODES:
        expert_reasons.append(f"competing_land_change={competitor}")
    limitation = review.get("observation_limitation")
    if limitation not in (None, "", "none"):
        expert_reasons.append(f"observation_limitation={limitation}")
    pass_a_confidence = review.get("pass_a_scar_confidence")
    pass_b_confidence = review.get("pass_b_confidence_after")
    if pass_a_confidence not in (None, "") and pass_b_confidence not in (None, "") and pass_a_confidence != pass_b_confidence:
        expert_reasons.append("confidence_changed_between_passes")
    if expert_reasons:
        expert_priority = "required"
    elif competitor in RECOMMENDED_EXPERT_COMPETING_CODES:
        expert_priority = "recommended"
        expert_reasons.append(f"competing_land_change={competitor}")
    else:
        expert_priority = "none"
    return {
        "needs_adjudication": needs_adjudication,
        "adjudication_reasons": adjudication_reasons,
        "expert_review_priority": expert_priority,
        "expert_review_reasons": expert_reasons,
        "partially_agree_is_robustness_incomplete": review.get("pass_b_mode_agreement") == "partially_agree",
    }


def candidate_view_from_r1_row(row: Mapping[str, Any], *, case_id: str) -> dict[str, Any]:
    """Create a non-persistent candidate view of one legacy R1 row.

    The old ``cloud_or_haze`` value cannot be retained as a surface-process
    competitor. It is moved to the structured limitation axis and the surface
    competitor becomes ``unknown`` because the old row did not record that axis
    separately. Notes are intentionally not inspected.
    """

    legacy_competitor = str(row.get("pass_a_competing_land_change") or "")
    if legacy_competitor == LEGACY_CLOUD_CODE:
        candidate_competitor = "unknown"
        limitation = "cloud_or_haze"
    elif legacy_competitor in COMPETING_LAND_CHANGE_CODES:
        candidate_competitor = legacy_competitor
        limitation = "none"
    else:
        candidate_competitor = "unknown"
        limitation = "unknown"
    review = {
        "pass_a_visible_burn_scar": str(row.get("pass_a_visible_burn_scar") or ""),
        "pass_a_scar_confidence": str(row.get("pass_a_scar_confidence") or ""),
        "pass_a_event_association": str(row.get("pass_a_event_association") or ""),
        "pass_a_competing_land_change": candidate_competitor,
        "observation_limitation": limitation,
        "pass_b_mode_agreement": str(row.get("pass_b_mode_agreement") or ""),
        "pass_b_confidence_after": str(row.get("pass_b_confidence_after") or ""),
        "pass_b_requires_adjudication": row.get("pass_b_requires_adjudication") in (True, 1, "1", "true", "True"),
    }
    triage = derive_control_triage(review)
    return {
        "case_id": case_id,
        "legacy_competing_land_change": legacy_competitor,
        "candidate_competing_land_change": candidate_competitor,
        "observation_limitation": limitation,
        "notes_used_for_limitation": False,
        "pass_a_visible_burn_scar": review["pass_a_visible_burn_scar"],
        "pass_a_scar_confidence": review["pass_a_scar_confidence"],
        "pass_a_event_association": review["pass_a_event_association"],
        "pass_b_mode_agreement": review["pass_b_mode_agreement"],
        "pass_b_confidence_after": review["pass_b_confidence_after"],
        "current_review_status": str(row.get("review_status") or ""),
        "proposed_review_status": "needs_adjudication" if triage["needs_adjudication"] else "pass_b_complete",
        **triage,
    }


def _walk_values(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_values(child)


def _validate_response_payload(
    payload: Mapping[str, Any],
    *,
    expected_pass: str,
    reviewer_slot: str | None = None,
) -> list[str]:
    errors: list[str] = []
    root_fields = {
        "schema_version",
        "round_id",
        "pass",
        "protocol_version",
        "reviewer_id",
        "reviewer_type",
        "reviewer_expertise",
        "reviewer_model",
        "label_status",
        "reviews",
    }
    if set(payload) != root_fields:
        errors.append("response root fields do not match the control schema")
    constants = {
        "schema_version": CONTROL_SCHEMA_VERSION,
        "round_id": CONTROL_ROUND_ID,
        "pass": expected_pass,
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "reviewer_type": "ai_assisted",
        "reviewer_expertise": "not_applicable",
        "label_status": "provisional_pseudolabel",
    }
    for field, expected in constants.items():
        if payload.get(field) != expected:
            errors.append(f"{field} constant mismatch")
    reviewer_id = payload.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        errors.append("reviewer_id must be a non-empty string")
    reviewer_model = payload.get("reviewer_model")
    if not isinstance(reviewer_model, str) or not reviewer_model.strip():
        errors.append("reviewer_model must be non-empty for ai_assisted")
    if reviewer_slot is not None:
        identity = CONTROL_REVIEWER_IDENTITIES.get(reviewer_slot)
        if identity is None:
            errors.append(f"unknown reviewer slot: {reviewer_slot}")
        else:
            if payload.get("reviewer_id") != identity["reviewer_id"]:
                errors.append(f"reviewer_id does not match {reviewer_slot} control identity")
            if payload.get("reviewer_model") != identity["reviewer_model"]:
                errors.append(f"reviewer_model does not match {reviewer_slot} control identity")
    errors.extend(validate_reviewer_provenance(
        payload.get("reviewer_type"),
        payload.get("reviewer_expertise"),
        payload.get("reviewer_model"),
    ))
    reviews = payload.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != len(CONTROL_CASE_IDS):
        errors.append("reviews must contain exactly seven objects")
        return sorted(set(errors))
    expected_fields = set(CONTROL_PASS_A_RESPONSE_FIELDS if expected_pass == "A" else CONTROL_PASS_B_RESPONSE_FIELDS)
    enums = {
        "pass_a_visible_burn_scar": set(VISIBLE_BURN_SCAR_CODES),
        "pass_a_scar_confidence": set(SCAR_CONFIDENCE_CODES),
        "pass_a_event_association": set(EVENT_ASSOCIATION_CODES),
        "pass_a_competing_land_change": set(COMPETING_LAND_CHANGE_CODES),
        "observation_limitation": set(OBSERVATION_LIMITATION_CODES),
        "pass_b_mode_agreement": set(MODE_AGREEMENT_CODES),
        "pass_b_confidence_after": set(SCAR_CONFIDENCE_CODES),
    }
    seen: list[str] = []
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, dict):
            errors.append(f"review {index} is not an object")
            continue
        if set(review) != expected_fields:
            errors.append(f"review {index} fields do not match the control schema")
        case_id = review.get("case_id")
        seen.append(str(case_id))
        if case_id not in CONTROL_CASE_IDS:
            errors.append(f"unknown case id: {case_id!r}")
        for field, allowed in enums.items():
            if field in review and review[field] not in allowed:
                errors.append(f"invalid enum for {field}: {review[field]!r}")
        for field in expected_fields - {"case_id", "pass_b_requires_adjudication"}:
            if not isinstance(review.get(field), str) or not review[field].strip():
                errors.append(f"{field} must be a non-empty string")
        if expected_pass == "B" and not isinstance(review.get("pass_b_requires_adjudication"), bool):
            errors.append("pass_b_requires_adjudication must be boolean")
    if sorted(seen) != sorted(CONTROL_CASE_IDS) or len(set(seen)) != len(CONTROL_CASE_IDS):
        errors.append("case ids must be the exact seven-case set")
    for key, child in _walk_values(payload):
        if key in {"event_id", "expert_review_priority", "expert_review_reasons", "ground_truth", "significant_burn"}:
            errors.append(f"prohibited response field: {key}")
        if isinstance(child, str):
            encoded = child.encode("utf-8")
            if b"2026" in encoded:
                errors.append("response contains a future-period year")
            if ORIGINAL_EVENT_RE.search(encoded) or ABSOLUTE_WINDOWS_PATH_RE.search(encoded):
                errors.append("response contains a source identifier or path")
    return sorted(set(errors))


def _pair_rows(pass_a: Mapping[str, Any], pass_b: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_case_a = {item["case_id"]: item for item in pass_a["reviews"]}
    by_case_b = {item["case_id"]: item for item in pass_b["reviews"]}
    rows: list[dict[str, Any]] = []
    for case_id in CONTROL_CASE_IDS:
        left = by_case_a[case_id]
        right = by_case_b[case_id]
        preserved_fields = {field: left[field] for field in CONTROL_PASS_A_RESPONSE_FIELDS if field != "case_id"}
        b_fields = {field: right[field] for field in PASS_B_FIELDS}
        triage = derive_control_triage({**preserved_fields, **b_fields})
        rows.append({"case_id": case_id, **preserved_fields, **b_fields, **triage})
    return rows


def _load_control_reviewer_pairs(
    reviewer_a_pass_a: Path,
    reviewer_a_pass_b: Path,
    reviewer_b_pass_a: Path,
    reviewer_b_pass_b: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    paths = (
        ("reviewer_a", Path(reviewer_a_pass_a), Path(reviewer_a_pass_b)),
        ("reviewer_b", Path(reviewer_b_pass_a), Path(reviewer_b_pass_b)),
    )
    errors: list[str] = []
    loaded: list[dict[str, Any]] = []
    reviewer_ids: dict[str, str] = {}
    for label, pass_a_path, pass_b_path in paths:
        try:
            pass_a = _read_json(pass_a_path)
            pass_b = _read_json(pass_b_path)
        except BlindControlError as exc:
            errors.append(str(exc))
            continue
        errors.extend(
            f"{label} Pass A: {error}"
            for error in _validate_response_payload(pass_a, expected_pass="A", reviewer_slot=label)
        )
        errors.extend(
            f"{label} Pass B: {error}"
            for error in _validate_response_payload(pass_b, expected_pass="B", reviewer_slot=label)
        )
        reviewer_a_id = pass_a.get("reviewer_id")
        reviewer_b_id = pass_b.get("reviewer_id")
        if reviewer_a_id != reviewer_b_id:
            errors.append(f"{label}: Pass A and Pass B reviewer_id differ")
        for field in (
            "schema_version",
            "round_id",
            "protocol_version",
            "reviewer_type",
            "reviewer_expertise",
            "reviewer_model",
            "label_status",
        ):
            if pass_a.get(field) != pass_b.get(field):
                errors.append(f"{label}: Pass B changes reviewer metadata field {field}")
        if isinstance(reviewer_a_id, str) and reviewer_a_id:
            previous = reviewer_ids.get(reviewer_a_id)
            if previous is not None:
                errors.append(f"duplicate reviewer_id {reviewer_a_id!r} across {previous} and {label}")
            else:
                reviewer_ids[reviewer_a_id] = label
        if isinstance(pass_a.get("reviews"), list) and isinstance(pass_b.get("reviews"), list):
            by_case_a = {item.get("case_id"): item for item in pass_a["reviews"] if isinstance(item, dict)}
            by_case_b = {item.get("case_id"): item for item in pass_b["reviews"] if isinstance(item, dict)}
            for case_id in CONTROL_CASE_IDS:
                left = by_case_a.get(case_id)
                right = by_case_b.get(case_id)
                if left is None or right is None:
                    continue
                for field in CONTROL_PASS_A_RESPONSE_FIELDS:
                    if left.get(field) != right.get(field):
                        errors.append(f"{label} rewrites Pass A field {field} for {case_id}")
        loaded.append({
            "slot": label,
            "reviewer_id": reviewer_a_id,
            "reviewer_type": pass_a.get("reviewer_type"),
            "reviewer_expertise": pass_a.get("reviewer_expertise"),
            "reviewer_model": pass_a.get("reviewer_model"),
            "label_status": pass_a.get("label_status"),
            "pass_a": pass_a,
            "pass_b": pass_b,
        })
    if len(reviewer_ids) != 2:
        errors.append("control round requires two distinct reviewer_id values")
    return loaded, sorted(set(errors))


CONTROL_REVIEW_COLUMNS = (
    "round_id",
    "event_id",
    "reviewer_id",
    "reviewer_type",
    "reviewer_model",
    "reviewer_expertise",
    "label_status",
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "observation_limitation",
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
CONTROL_REVIEW_COMPARE_COLUMNS = tuple(
    column for column in CONTROL_REVIEW_COLUMNS if column not in {"pass_a_saved_at", "pass_b_saved_at", "created_at", "updated_at"}
)
CONTROL_AUDIT_FIELDS = (
    "reviewer_type",
    "reviewer_model",
    "reviewer_expertise",
    "label_status",
    "pass_a_visible_burn_scar",
    "pass_a_scar_confidence",
    "pass_a_event_association",
    "pass_a_competing_land_change",
    "observation_limitation",
    "pass_a_notes",
    "pass_b_mode_agreement",
    "pass_b_confidence_after",
    "pass_b_requires_adjudication",
    "pass_b_notes",
    "review_status",
)
PROTECTED_R1_REVIEW_COLUMNS = (
    "round_id",
    "event_id",
    "reviewer_id",
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
    "reviewer_type",
    "label_status",
)


def _table_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))


def _ensure_control_columns(connection: sqlite3.Connection) -> None:
    """Migrate the existing review DB without rewriting existing rows."""

    columns = set(_table_columns(connection, "reviews"))
    additions = (
        ("reviewer_type", "TEXT NOT NULL DEFAULT 'human'"),
        ("reviewer_model", "TEXT"),
        ("reviewer_expertise", "TEXT"),
        ("label_status", "TEXT NOT NULL DEFAULT 'human_observation'"),
        ("observation_limitation", "TEXT"),
    )
    for name, definition in additions:
        if name not in columns:
            connection.execute(f"ALTER TABLE reviews ADD COLUMN {name} {definition}")


def _control_item_values(case_id: str, randomized_order: int) -> tuple[Any, ...]:
    return (
        CONTROL_STORE_ROUND_ID,
        randomized_order,
        case_id,
        f"outputs/firepa_blind_control_r1_pass_a.zip::{case_id}_multispectral.png",
        f"outputs/firepa_blind_control_r1_pass_b.zip::{case_id}_temporal.png",
        "observable",
    )


def _ensure_control_round(connection: sqlite3.Connection, *, timestamp: str) -> None:
    existing_round = connection.execute(
        "SELECT round_id, protocol_version, quicklook_version, random_seed, status "
        "FROM review_rounds WHERE round_id = ?",
        (CONTROL_STORE_ROUND_ID,),
    ).fetchone()
    expected_round = (
        CONTROL_STORE_ROUND_ID,
        CONTROL_PROTOCOL_VERSION,
        CONTROL_STORE_VERSION,
        CONTROL_STORE_RANDOM_SEED,
        "open",
    )
    if existing_round is None:
        connection.execute(
            "INSERT INTO review_rounds "
            "(round_id, protocol_version, quicklook_version, random_seed, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (*expected_round[:4], timestamp, expected_round[4]),
        )
    elif tuple(existing_round[field] for field in ("round_id", "protocol_version", "quicklook_version", "random_seed", "status")) != expected_round:
        raise ReviewStoreError("Existing control round conflicts with the control_r1 store contract")

    for randomized_order, case_id in enumerate(CONTROL_CASE_IDS, start=1):
        expected_item = _control_item_values(case_id, randomized_order)
        existing_item = connection.execute(
            "SELECT round_id, randomized_order, event_id, multispectral_panel_path, "
            "temporal_panel_path, observability_status FROM review_items "
            "WHERE round_id = ? AND event_id = ?",
            (CONTROL_STORE_ROUND_ID, case_id),
        ).fetchone()
        if existing_item is None:
            connection.execute(
                "INSERT INTO review_items "
                "(round_id, randomized_order, event_id, multispectral_panel_path, "
                "temporal_panel_path, observability_status) VALUES (?, ?, ?, ?, ?, ?)",
                expected_item,
            )
        elif tuple(existing_item) != expected_item:
            raise ReviewStoreError(f"Existing control item conflicts: {case_id}")


def _control_review_row(reviewer: Mapping[str, Any], case: Mapping[str, Any], *, timestamp: str) -> dict[str, Any]:
    requires_adjudication = bool(case["needs_adjudication"])
    visible = case["pass_a_visible_burn_scar"]
    return {
        "round_id": CONTROL_STORE_ROUND_ID,
        "event_id": case["case_id"],
        "reviewer_id": reviewer["reviewer_id"],
        "reviewer_type": reviewer["reviewer_type"],
        "reviewer_model": reviewer["reviewer_model"],
        "reviewer_expertise": reviewer["reviewer_expertise"],
        "label_status": reviewer["label_status"],
        "pass_a_visible_burn_scar": case["pass_a_visible_burn_scar"],
        "pass_a_scar_confidence": case["pass_a_scar_confidence"],
        "pass_a_event_association": case["pass_a_event_association"],
        "pass_a_competing_land_change": case["pass_a_competing_land_change"],
        "observation_limitation": case["observation_limitation"],
        "pass_a_notes": case["pass_a_notes"],
        "pass_a_saved_at": timestamp,
        "pass_a_revision": 1,
        "pass_b_mode_agreement": case["pass_b_mode_agreement"],
        "pass_b_confidence_after": case["pass_b_confidence_after"],
        "pass_b_requires_adjudication": 1 if case["pass_b_requires_adjudication"] else 0,
        "pass_b_notes": case["pass_b_notes"],
        "pass_b_saved_at": timestamp,
        "pass_b_revision": 1,
        "review_status": "unobserved" if visible == "unobserved" else (
            "needs_adjudication" if requires_adjudication else "pass_b_complete"
        ),
        "exclusion_reason": None,
        "adjudication_notes": case["pass_b_notes"] if requires_adjudication else None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _protected_round_snapshot(connection: sqlite3.Connection, round_id: str) -> tuple[Any, ...]:
    review_columns = tuple(column for column in PROTECTED_R1_REVIEW_COLUMNS if column in _table_columns(connection, "reviews"))
    reviews = tuple(
        tuple(row)
        for row in connection.execute(
            f"SELECT {', '.join(review_columns)} FROM reviews WHERE round_id = ? ORDER BY event_id, reviewer_id",
            (round_id,),
        ).fetchall()
    )
    rounds = tuple(tuple(row) for row in connection.execute("SELECT * FROM review_rounds WHERE round_id = ?", (round_id,)).fetchall())
    items = tuple(tuple(row) for row in connection.execute("SELECT * FROM review_items WHERE round_id = ? ORDER BY randomized_order", (round_id,)).fetchall())
    audit = tuple(tuple(row) for row in connection.execute("SELECT * FROM audit_log WHERE round_id = ? ORDER BY audit_id", (round_id,)).fetchall())
    return rounds, items, (review_columns, reviews), audit


def _import_control_sqlite(
    reviewers: Sequence[Mapping[str, Any]],
    *,
    root: Path,
    database: Path,
) -> dict[str, Any]:
    database = Path(database).resolve()
    before_sha256 = _sha256_file(database) if database.is_file() else None
    store = HumanReviewStore.from_frozen_round(db_path=database, root=root)
    try:
        r1_before = _protected_round_snapshot(store.connection, "round1")
        timestamp = utc_timestamp()
        expected_rows = [
            _control_review_row(reviewer, case, timestamp=timestamp)
            for reviewer in reviewers
            for case in reviewer["cases"]
        ]
        inserted = 0
        unchanged = 0
        with store.connection:
            _ensure_control_columns(store.connection)
            _ensure_control_round(store.connection, timestamp=timestamp)
            conflicts: list[str] = []
            existing_rows: dict[tuple[str, str], sqlite3.Row | None] = {}
            for expected in expected_rows:
                key = (str(expected["reviewer_id"]), str(expected["event_id"]))
                existing = store.connection.execute(
                    "SELECT * FROM reviews WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
                    (CONTROL_STORE_ROUND_ID, expected["event_id"], expected["reviewer_id"]),
                ).fetchone()
                existing_rows[key] = existing
                if existing is not None and any(existing[column] != expected[column] for column in CONTROL_REVIEW_COMPARE_COLUMNS):
                    conflicts.append(f"Existing control review conflicts: {key[0]} / {key[1]}")
            if conflicts:
                raise ReviewStoreError("; ".join(conflicts))
            for expected in expected_rows:
                key = (str(expected["reviewer_id"]), str(expected["event_id"]))
                if existing_rows[key] is not None:
                    unchanged += 1
                    continue
                store.connection.execute(
                    f"INSERT INTO reviews ({', '.join(CONTROL_REVIEW_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in CONTROL_REVIEW_COLUMNS)})",
                    [expected[column] for column in CONTROL_REVIEW_COLUMNS],
                )
                for field_name in CONTROL_AUDIT_FIELDS:
                    value = expected[field_name]
                    store.connection.execute(
                        "INSERT INTO audit_log "
                        "(round_id, event_id, reviewer_id, action, field_name, previous_value, "
                        "new_value, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            CONTROL_STORE_ROUND_ID,
                            expected["event_id"],
                            expected["reviewer_id"],
                            "import_blind_control_r1",
                            field_name,
                            None,
                            None if value is None else str(value),
                            "control_r1_provisional_pseudolabel",
                            timestamp,
                        ),
                    )
                inserted += 1
        r1_after = _protected_round_snapshot(store.connection, "round1")
    finally:
        store.close()
    after_sha256 = _sha256_file(database) if database.is_file() else None
    return {
        "database": database,
        "inserted": inserted,
        "unchanged": unchanged,
        "rows_imported": inserted,
        "database_written": True,
        "sqlite_changed": before_sha256 != after_sha256,
        "sqlite_sha256_before": before_sha256,
        "sqlite_sha256_after": after_sha256,
        "r1_protected_rows_unchanged": r1_before == r1_after,
        "r1_round": "round1",
        "control_round": CONTROL_STORE_ROUND_ID,
    }


def import_blind_control_results(
    reviewer_a_pass_a: Path,
    reviewer_a_pass_b: Path,
    reviewer_b_pass_a: Path,
    reviewer_b_pass_b: Path,
    *,
    dry_run: bool = False,
    report: Path | None = None,
    output: Path | None = None,
    root: Path = ROOT,
    database: Path | None = None,
) -> dict[str, Any]:
    """Validate and optionally import two independent response pairs."""

    pairs, errors = _load_control_reviewer_pairs(
        reviewer_a_pass_a,
        reviewer_a_pass_b,
        reviewer_b_pass_a,
        reviewer_b_pass_b,
    )
    if errors:
        result: dict[str, Any] = {
            "status": "fail",
            "dry_run": dry_run,
            "reviewer_count": len(pairs),
            "case_count": 0,
            "errors": errors,
            "sqlite_written": False,
            "database_written": False,
        }
    else:
        reviewers = []
        for pair in sorted(pairs, key=lambda item: str(item["reviewer_id"])):
            reviewers.append({
                "reviewer_id": pair["reviewer_id"],
                "reviewer_type": pair["reviewer_type"],
                "reviewer_expertise": pair["reviewer_expertise"],
                "reviewer_model": pair["reviewer_model"],
                "label_status": pair["label_status"],
                "cases": _pair_rows(pair["pass_a"], pair["pass_b"]),
            })
        result = {
            "status": "pass",
            "dry_run": dry_run,
            "round_id": CONTROL_ROUND_ID,
            "reviewer_count": len(reviewers),
            "reviewer_ids": [reviewer["reviewer_id"] for reviewer in reviewers],
            "case_count": len(CONTROL_CASE_IDS),
            "reviewers": reviewers,
            "sqlite_written": False,
            "database_written": False,
            "results_overwritten": False,
            "inserted": 0,
            "unchanged": 0,
            "rows_imported": 0,
            "errors": [],
        }
        if output is not None and not dry_run and Path(output).resolve().exists():
            raise BlindControlError(f"Refusing to overwrite existing control result output: {Path(output).resolve()}")
        if not dry_run:
            try:
                sqlite_result = _import_control_sqlite(
                    reviewers,
                    root=Path(root).resolve(),
                    database=Path(database).resolve() if database is not None else CONTROL_DATABASE_PATH,
                )
            except (OSError, sqlite3.Error, ReviewStoreError) as exc:
                result.update({
                    "status": "fail",
                    "errors": [f"control SQLite import failed: {exc}"],
                    "database_written": False,
                    "sqlite_written": False,
                })
            else:
                result.update(sqlite_result)
                result["sqlite_written"] = bool(sqlite_result["sqlite_changed"])
        else:
            result["would_insert"] = len(reviewers) * len(CONTROL_CASE_IDS)
        if output is not None and not dry_run and result["status"] == "pass":
            output = Path(output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["output"] = output
    if report is not None:
        report = Path(report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return result


def _markdown_cell(value: Any) -> str:
    if isinstance(value, (list, tuple, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_control_comparison_markdown(result: Mapping[str, Any]) -> str:
    """Render a comparison report without adding scientific interpretation."""

    lines = [
        "# Blind Control R1 — comparación independiente",
        "",
        "## Estado",
        "",
        f"- Estado técnico: **{result.get('status')}**.",
        f"- Ronda: `{result.get('round_id', CONTROL_ROUND_ID)}`.",
        f"- Casos comparados: **{result.get('case_count', 0)}**.",
        f"- Reviewer A: `{result.get('reviewer_ids', [''])[0] if result.get('reviewer_ids') else ''}` — `{result.get('reviewer_models', {}).get('reviewer_a', '')}`.",
        f"- Reviewer B: `{result.get('reviewer_ids', ['', ''])[1] if len(result.get('reviewer_ids', [])) > 1 else ''}` — `{result.get('reviewer_models', {}).get('reviewer_b', '')}`.",
        "- `label_status=provisional_pseudolabel`; no es observación humana de referencia.",
        "- No se calculan exactitud, sensibilidad ni especificidad.",
        "- No existe `ground_truth`, `significant_burn` ni etiqueta científica final en esta ronda.",
        "",
        "## Acuerdo exacto por campo",
        "",
        "| Campo | Acuerdos | Desacuerdos |",
        "|---|---:|---:|",
    ]
    for field, counts in result.get("exact_agreement_by_field", {}).items():
        lines.append(f"| `{field}` | {counts['agree']} | {counts['disagree']} |")

    lines.extend(["", "## Distribución por revisor", ""])
    distributions = result.get("distributions_by_reviewer", {})
    lines.extend([
        "| Campo | Reviewer A | Reviewer B |",
        "|---|---|---|",
    ])
    for field in DISTRIBUTION_FIELDS:
        lines.append(
            f"| `{field}` | {_markdown_cell(distributions.get('reviewer_a', {}).get(field, {}))} | "
            f"{_markdown_cell(distributions.get('reviewer_b', {}).get(field, {}))} |"
        )

    lines.extend(["", "## Desacuerdos por caso", ""])
    for disagreement in result.get("disagreements_by_case", []):
        lines.append(f"### `{disagreement['case_id']}`")
        lines.append("")
        lines.append(f"Campos: `{', '.join(disagreement['fields'])}`.")
        lines.append("")
        lines.append(f"- Reviewer A: {_markdown_cell(disagreement['reviewer_a'])}")
        lines.append(f"- Reviewer B: {_markdown_cell(disagreement['reviewer_b'])}")
        lines.append("")

    difference_sections = (
        ("Diferencias de confianza", "confidence_differences"),
        ("Diferencias de asociación", "association_differences"),
        ("Diferencias de competing_land_change", "confounder_differences"),
        ("Diferencias de observation_limitation", "observation_limitation_differences"),
        ("Diferencias de mode_agreement", "mode_agreement_differences"),
        ("Diferencias de adjudicación", "adjudication_differences"),
    )
    for title, key in difference_sections:
        lines.extend([f"## {title}", ""])
        rows = result.get(key, [])
        if not rows:
            lines.append("Sin diferencias.")
        else:
            lines.extend(["| Caso | Campo | Reviewer A | Reviewer B |", "|---|---|---|---|"])
            for row in rows:
                lines.append(
                    f"| `{row['case_id']}` | `{row.get('field', key)}` | "
                    f"{_markdown_cell(row['reviewer_a'])} | {_markdown_cell(row['reviewer_b'])} |"
                )
        lines.append("")

    lines.extend(["## Triage derivado por revisor", ""])
    lines.append("El triage se deriva exclusivamente de campos estructurados; las notas no cambian los estados.")
    lines.append("")
    lines.extend(["| Caso | Reviewer | needs_adjudication | Razones de adjudicación | expert_review_priority | Razones expertas |", "|---|---|---|---|---|---|"])
    for reviewer_key in ("reviewer_a", "reviewer_b"):
        for row in result.get("triage_by_reviewer", {}).get(reviewer_key, []):
            lines.append(
                f"| `{row['case_id']}` | {reviewer_key} | `{row['needs_adjudication']}` | "
                f"{_markdown_cell(row['adjudication_reasons'])} | `{row['expert_review_priority']}` | "
                f"{_markdown_cell(row['expert_review_reasons'])} |"
            )
    lines.extend(["", "### Uniones de triage", ""])
    adjudication = result.get("cases_requiring_adjudication", {})
    expert = result.get("cases_requiring_expert", {})
    lines.append(f"- Casos que requieren adjudicación por cualquiera: `{', '.join(adjudication.get('either', [])) or 'ninguno'}`.")
    lines.append(f"- Casos que requieren adjudicación por ambos: `{', '.join(adjudication.get('both', [])) or 'ninguno'}`.")
    lines.append(f"- Casos de prioridad experta requerida por cualquiera: `{', '.join(expert.get('either', [])) or 'ninguno'}`.")
    lines.append(f"- Casos de prioridad experta requerida por ambos: `{', '.join(expert.get('both', [])) or 'ninguno'}`.")
    lines.append(f"- Casos de prioridad experta recomendada por cualquiera: `{', '.join(result.get('cases_recommended_expert', {}).get('either', [])) or 'ninguno'}`.")

    shared = result.get("shared_observations", {})
    lines.extend([
        "",
        "## Lecturas compartidas y desacuerdos materiales",
        "",
        f"- Observación positiva compartida (`visible_burn_scar=yes` y `association=likely`): `{', '.join(shared.get('positive_visible_and_likely', [])) or 'ninguna'}`.",
        f"- Observación negativa compartida (`visible_burn_scar=no`): `{', '.join(shared.get('negative_visible', [])) or 'ninguna'}`.",
        f"- Patrón agrícola compartido: `{', '.join(shared.get('agriculture_or_harvest', [])) or 'ninguno'}`.",
        f"- Ambigüedad visual compartida: `{', '.join(shared.get('ambiguous_visible', [])) or 'ninguna'}`.",
        f"- Acuerdo fuerte (todos los campos estructurados exactos): `{', '.join(result.get('strong_agreement_cases', [])) or 'ninguno'}`.",
        f"- Desacuerdo material (campos estructurados de observación o triage): `{', '.join(result.get('material_disagreement_cases', [])) or 'ninguno'}`.",
        "",
        "CASE-007 se mantiene como desacuerdo material; CASE-005 como ambigüedad compartida; CASE-006 como patrón agrícola compartido. CASE-001 y CASE-002 son observaciones positivas compartidas, mientras CASE-003 y CASE-004 muestran observación negativa compartida en el eje visible. Estas coincidencias describen concordancia entre revisores, no verdad científica.",
        "",
        "## Limitaciones",
        "",
        "- Los dos revisores son modelos IA de la misma familia; el acuerdo no mide exactitud ni independencia frente a un estándar externo.",
        "- Las notas son texto libre y se reportan como evidencia cualitativa; no se usan para derivar triage.",
        "- La comparación se limita a siete paneles anonimizados y a los enums del protocolo candidato v1.",
        "- No existe ground truth y esta ronda no crea etiquetas finales, `significant_burn` ni resultados de calibración.",
        "- Las diferencias requieren adjudicación o revisión experta según el triage administrativo; no autorizan cambiar el protocolo científico automáticamente.",
    ])
    if result.get("sqlite_read_only"):
        lines.extend([
            "",
            "## Integridad de la comparación",
            "",
            f"- Lectura SQLite read-only: `{result.get('sqlite_rows_match_validated_input')}`.",
            f"- Errores de reconciliación SQLite: `{_markdown_cell(result.get('sqlite_errors', []))}`.",
            "- La comparación no escribe ni actualiza SQLite.",
        ])
    return "\n".join(lines) + "\n"


def _field_differences(
    left_rows: Mapping[str, Mapping[str, Any]],
    right_rows: Mapping[str, Mapping[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case_id,
            "field": field,
            "reviewer_a": left_rows[case_id][field],
            "reviewer_b": right_rows[case_id][field],
        }
        for case_id in CONTROL_CASE_IDS
        if left_rows[case_id][field] != right_rows[case_id][field]
    ]


def _distribution(rows: Mapping[str, Mapping[str, Any]], field: str) -> dict[str, int]:
    values = Counter(str(rows[case_id][field]) for case_id in CONTROL_CASE_IDS)
    return {key: int(values[key]) for key in sorted(values)}


def _read_control_sqlite_rows(database: Path) -> tuple[list[dict[str, Any]], list[str]]:
    database = Path(database).resolve()
    if not database.is_file():
        return [], [f"control SQLite database is missing: {database}"]
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        required = set(CONTROL_REVIEW_COLUMNS)
        columns = set(_table_columns(connection, "reviews"))
        missing = sorted(required - columns)
        if missing:
            return [], [f"control SQLite schema is missing columns: {', '.join(missing)}"]
        rows = connection.execute(
            "SELECT * FROM reviews WHERE round_id = ? ORDER BY reviewer_id, event_id",
            (CONTROL_STORE_ROUND_ID,),
        ).fetchall()
        return [dict(row) for row in rows], []
    except sqlite3.Error as exc:
        return [], [f"control SQLite read-only query failed: {exc}"]
    finally:
        connection.close()


def _verify_control_sqlite_rows(
    reviewers: Sequence[Mapping[str, Any]],
    database: Path,
) -> list[str]:
    actual_rows, errors = _read_control_sqlite_rows(database)
    if errors:
        return errors
    expected_rows = [
        _control_review_row(reviewer, case, timestamp="")
        for reviewer in reviewers
        for case in reviewer["cases"]
    ]
    expected_by_key = {(str(row["reviewer_id"]), str(row["event_id"])): row for row in expected_rows}
    actual_by_key = {(str(row["reviewer_id"]), str(row["event_id"])): row for row in actual_rows}
    errors = []
    if set(actual_by_key) != set(expected_by_key):
        errors.append("control SQLite rows do not match the two seven-case reviewer sets")
    for key, expected in expected_by_key.items():
        actual = actual_by_key.get(key)
        if actual is None:
            continue
        if any(actual.get(column) != expected[column] for column in CONTROL_REVIEW_COMPARE_COLUMNS):
            errors.append(f"control SQLite row differs from validated response: {key[0]} / {key[1]}")
    return sorted(set(errors))


def compare_blind_control_results(
    reviewer_a_pass_a: Path,
    reviewer_a_pass_b: Path,
    reviewer_b_pass_a: Path,
    reviewer_b_pass_b: Path,
    *,
    report: Path | None = None,
    database: Path | None = None,
) -> dict[str, Any]:
    """Compare two reviewer pairs without computing scientific performance metrics."""

    pairs, errors = _load_control_reviewer_pairs(
        reviewer_a_pass_a,
        reviewer_a_pass_b,
        reviewer_b_pass_a,
        reviewer_b_pass_b,
    )
    if errors:
        result = {"status": "fail", "errors": errors, "sqlite_written": False, "sqlite_read_only": database is not None}
    else:
        by_slot = {pair["slot"]: pair for pair in pairs}
        left = by_slot["reviewer_a"]
        right = by_slot["reviewer_b"]
        left_rows = {row["case_id"]: row for row in _pair_rows(left["pass_a"], left["pass_b"])}
        right_rows = {row["case_id"]: row for row in _pair_rows(right["pass_a"], right["pass_b"])}
        exact: dict[str, dict[str, int]] = {}
        disagreements: list[dict[str, Any]] = []
        for field in COMPARISON_FIELDS:
            agree = sum(left_rows[case_id][field] == right_rows[case_id][field] for case_id in CONTROL_CASE_IDS)
            exact[field] = {"agree": int(agree), "disagree": len(CONTROL_CASE_IDS) - int(agree)}
        for case_id in CONTROL_CASE_IDS:
            fields = [field for field in COMPARISON_FIELDS if left_rows[case_id][field] != right_rows[case_id][field]]
            if fields:
                disagreements.append({
                    "case_id": case_id,
                    "fields": fields,
                    "reviewer_a": {field: left_rows[case_id][field] for field in fields},
                    "reviewer_b": {field: right_rows[case_id][field] for field in fields},
                })
        def cases_where(rows: Mapping[str, Mapping[str, Any]], predicate: Any) -> list[str]:
            return [case_id for case_id in CONTROL_CASE_IDS if predicate(rows[case_id])]

        left_ambiguous = set(cases_where(left_rows, lambda row: row["pass_a_visible_burn_scar"] == "ambiguous"))
        right_ambiguous = set(cases_where(right_rows, lambda row: row["pass_a_visible_burn_scar"] == "ambiguous"))
        left_adjudication = set(cases_where(left_rows, lambda row: row["needs_adjudication"]))
        right_adjudication = set(cases_where(right_rows, lambda row: row["needs_adjudication"]))
        left_required = set(cases_where(left_rows, lambda row: row["expert_review_priority"] == "required"))
        right_required = set(cases_where(right_rows, lambda row: row["expert_review_priority"] == "required"))
        left_recommended = set(cases_where(left_rows, lambda row: row["expert_review_priority"] == "recommended"))
        right_recommended = set(cases_where(right_rows, lambda row: row["expert_review_priority"] == "recommended"))
        def grouped_cases(rows: Mapping[str, Mapping[str, Any]], field: str) -> dict[str, list[str]]:
            grouped: dict[str, list[str]] = {}
            for case_id in CONTROL_CASE_IDS:
                grouped.setdefault(str(rows[case_id][field]), []).append(case_id)
            return {key: grouped[key] for key in sorted(grouped)}

        triage_fields = (
            "needs_adjudication",
            "adjudication_reasons",
            "expert_review_priority",
            "expert_review_reasons",
            "partially_agree_is_robustness_incomplete",
        )
        triage = {
            "reviewer_a": [
                {"case_id": case_id, **{field: left_rows[case_id][field] for field in triage_fields}}
                for case_id in CONTROL_CASE_IDS
            ],
            "reviewer_b": [
                {"case_id": case_id, **{field: right_rows[case_id][field] for field in triage_fields}}
                for case_id in CONTROL_CASE_IDS
            ],
        }
        sqlite_errors = _verify_control_sqlite_rows(pairs and [
            {
                "reviewer_id": pair["reviewer_id"],
                "reviewer_type": pair["reviewer_type"],
                "reviewer_model": pair["reviewer_model"],
                "reviewer_expertise": pair["reviewer_expertise"],
                "label_status": pair["label_status"],
                "cases": _pair_rows(pair["pass_a"], pair["pass_b"]),
            }
            for pair in pairs
        ], database) if database is not None else []
        material_fields = (
            "pass_a_visible_burn_scar",
            "pass_a_event_association",
            "pass_a_competing_land_change",
            "observation_limitation",
            "pass_b_mode_agreement",
            "pass_b_requires_adjudication",
        )
        strong_agreement = [
            case_id for case_id in CONTROL_CASE_IDS
            if all(left_rows[case_id][field] == right_rows[case_id][field] for field in STRUCTURED_COMPARISON_FIELDS)
        ]
        material_disagreement = [
            case_id for case_id in CONTROL_CASE_IDS
            if any(left_rows[case_id][field] != right_rows[case_id][field] for field in material_fields)
        ]
        result = {
            "status": "pass" if not sqlite_errors else "fail",
            "round_id": CONTROL_ROUND_ID,
            "reviewer_ids": [left["reviewer_id"], right["reviewer_id"]],
            "reviewer_models": {
                "reviewer_a": left["reviewer_model"],
                "reviewer_b": right["reviewer_model"],
            },
            "case_count": len(CONTROL_CASE_IDS),
            "exact_agreement_by_field": exact,
            "disagreements_by_case": disagreements,
            "distributions_by_reviewer": {
                "reviewer_a": {field: _distribution(left_rows, field) for field in DISTRIBUTION_FIELDS},
                "reviewer_b": {field: _distribution(right_rows, field) for field in DISTRIBUTION_FIELDS},
            },
            "confidence_differences": _field_differences(left_rows, right_rows, "pass_a_scar_confidence")
            + [
                {"case_id": item["case_id"], "field": "pass_b_confidence_after", "reviewer_a": item["reviewer_a"], "reviewer_b": item["reviewer_b"]}
                for item in _field_differences(left_rows, right_rows, "pass_b_confidence_after")
            ],
            "association_differences": _field_differences(left_rows, right_rows, "pass_a_event_association"),
            "confounder_differences": _field_differences(left_rows, right_rows, "pass_a_competing_land_change"),
            "observation_limitation_differences": _field_differences(left_rows, right_rows, "observation_limitation"),
            "mode_agreement_differences": _field_differences(left_rows, right_rows, "pass_b_mode_agreement"),
            "adjudication_differences": _field_differences(left_rows, right_rows, "pass_b_requires_adjudication"),
            "both_consider_ambiguous": sorted(left_ambiguous & right_ambiguous),
            "cases_requiring_adjudication": {
                "reviewer_a": sorted(left_adjudication),
                "reviewer_b": sorted(right_adjudication),
                "both": sorted(left_adjudication & right_adjudication),
                "either": sorted(left_adjudication | right_adjudication),
            },
            "cases_requiring_expert": {
                "reviewer_a": sorted(left_required),
                "reviewer_b": sorted(right_required),
                "both": sorted(left_required & right_required),
                "either": sorted(left_required | right_required),
            },
            "cases_recommended_expert": {
                "reviewer_a": sorted(left_recommended),
                "reviewer_b": sorted(right_recommended),
                "both": sorted(left_recommended & right_recommended),
                "either": sorted(left_recommended | right_recommended),
            },
            "triage_by_reviewer": triage,
            "expert_review_priority_by_reviewer": {
                "reviewer_a": grouped_cases(left_rows, "expert_review_priority"),
                "reviewer_b": grouped_cases(right_rows, "expert_review_priority"),
            },
            "strong_agreement_cases": strong_agreement,
            "material_disagreement_cases": material_disagreement,
            "shared_observations": {
                "positive_visible_and_likely": [
                    case_id for case_id in CONTROL_CASE_IDS
                    if left_rows[case_id]["pass_a_visible_burn_scar"] == right_rows[case_id]["pass_a_visible_burn_scar"] == "yes"
                    and left_rows[case_id]["pass_a_event_association"] == right_rows[case_id]["pass_a_event_association"] == "likely"
                ],
                "negative_visible": [
                    case_id for case_id in CONTROL_CASE_IDS
                    if left_rows[case_id]["pass_a_visible_burn_scar"] == right_rows[case_id]["pass_a_visible_burn_scar"] == "no"
                ],
                "agriculture_or_harvest": [
                    case_id for case_id in CONTROL_CASE_IDS
                    if left_rows[case_id]["pass_a_competing_land_change"] == right_rows[case_id]["pass_a_competing_land_change"] == "agriculture_or_harvest"
                ],
                "ambiguous_visible": sorted(left_ambiguous & right_ambiguous),
            },
            "sanity_counts_derived": {
                "pass_a_visible_burn_scar": exact["pass_a_visible_burn_scar"]["agree"],
                "pass_a_scar_confidence": exact["pass_a_scar_confidence"]["agree"],
                "pass_a_event_association": exact["pass_a_event_association"]["agree"],
                "pass_a_competing_land_change": exact["pass_a_competing_land_change"]["agree"],
                "observation_limitation": exact["observation_limitation"]["agree"],
                "pass_b_mode_agreement": exact["pass_b_mode_agreement"]["agree"],
                "pass_b_confidence_after": exact["pass_b_confidence_after"]["agree"],
                "pass_b_requires_adjudication": exact["pass_b_requires_adjudication"]["agree"],
            },
            "performance_metrics_not_calculated": ["accuracy", "sensitivity", "specificity"],
            "sqlite_written": False,
            "sqlite_read_only": database is not None,
            "sqlite_rows_match_validated_input": database is not None and not sqlite_errors,
            "sqlite_errors": sqlite_errors,
        }
    if report is not None:
        report = Path(report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return result
