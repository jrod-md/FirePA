"""Formal-review v1 contract and preparation helpers.

This module prepares an empty, blind, two-human round.  It never reads
Earth Engine and it never derives a scientific class from a panel or metric.
The seven-case AI control round remains implemented by its historical module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from .human_review_migrations import CURRENT_MIGRATION_VERSION, apply_migrations
from .human_review_schema import ROOT, SCHEMA_SQL


FORMAL_ROUND_ID = "formal_review_28"
FORMAL_PROTOCOL_VERSION = "labeling-protocol-v1"
FORMAL_SCHEMA_VERSION = "firepa-formal-review-v1"
FORMAL_TOOL_VERSION = "firepa-human-review-tool-v2"
FORMAL_PROTOCOL_PATH = ROOT / "docs" / "LABELING_PROTOCOL_v1.md"
FORMAL_QUEUE_PATH = ROOT / "outputs" / "sentinel2_dnbr_review_queue.csv"
FORMAL_UNOBSERVED_PATH = ROOT / "outputs" / "human_review" / "unobserved_events.csv"
FORMAL_OUTPUT_DIR = ROOT / "outputs" / "human_review" / "formal_review_28"
FORMAL_SEED_ENV = "FIREPA_FORMAL_REVIEW_SEED"
FORMAL_SLOT_IDS = ("HUMAN_SLOT_A", "HUMAN_SLOT_B")
FORMAL_OBSERVABLE_COUNT = 28
FORMAL_UNOBSERVED_COUNT = 2
STALE_PROTOCOL_SHA256 = "57e7b75dc1e98bf9ec56c9feb52ed99cb4ee43d2e56e00a104046f09e972672d"
PROTOCOL_HASH_RECONCILIATION_REASON = "PROTOCOL_HASH_PREPARATION_RECONCILIATION"
FORMAL_ADMIN_ARTIFACT_KINDS = (
    "private_combined",
    "private_slot",
    "public_manifest",
    "preparation_summary",
    "export_csv",
    "export_json",
    "export_jsonl",
)
FORMAL_FORBIDDEN_FIELDS = (
    "event_id",
    "frp",
    "rank",
    "score",
    "predicted_class",
    "significant_burn",
    "target",
    "ground_truth",
    "severity",
)

VISIBLE_CODES = ("yes", "no", "ambiguous")
CONFIDENCE_CODES = ("high", "medium", "low")
ASSOCIATION_CODES = ("likely", "possible", "unlikely", "indeterminate")
SURFACE_CODES = (
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
LIMITATION_CODES = (
    "none",
    "cloud_or_haze",
    "mask_or_nodata",
    "shadow",
    "partial_coverage",
    "insufficient_temporal_separation",
    "mixed",
    "other",
)
MODE_CODES = ("agree", "partially_agree", "disagree")
REQUEST_REASON_CODES = (
    "ambiguous_observation",
    "low_confidence",
    "indeterminate_association",
    "mode_disagreement",
    "association_disagreement",
    "other_structured",
)
FORMAL_REVIEW_STATUSES = (
    "pending",
    "pass_a_locked",
    "pending_pair_review",
    "pending_adjudication",
    "pending_expert_review",
    "review_complete",
)
EXPERT_PRIORITIES = ("none", "recommended", "required")
REVIEWER_EXPERTISE = ("protocol_trained_reviewer", "remote_sensing_specialist", "domain_expert", "not_applicable")

PASS_A_FIELDS = (
    "visible_burn_scar",
    "scar_confidence",
    "event_association",
    "competing_land_change",
    "observation_limitation",
)
PASS_B_FIELDS = (
    "mode_agreement",
    "confidence_after",
    "reviewer_requested_adjudication",
    "request_reason",
)
MATERIAL_PAIR_FIELDS = ("visible_burn_scar", "event_association", "mode_agreement")
NONMATERIAL_PAIR_FIELDS = ("scar_confidence", "competing_land_change", "observation_limitation")


class FormalReviewError(ValueError):
    """Raised when formal-review preparation or persistence is incompatible."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise FormalReviewError(f"No se pudo calcular SHA-256 de {path}: {exc}") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise FormalReviewError(f"No se pudo escribir atómicamente {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> str:
    payload = (_canonical_json(value) + "\n").encode("utf-8")
    _atomic_write(path, payload)
    return sha256_bytes(payload)


def _json_bytes(value: Any) -> bytes:
    return (_canonical_json(value) + "\n").encode("utf-8")


def _write_checked(path: Path, payload: bytes, *, allow_replace: bool = False) -> str:
    """Write an administrative artifact only when identity and bytes agree."""

    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise FormalReviewError(f"No se pudo leer el artefacto administrativo {path}") from exc
        if existing == payload:
            return sha256_bytes(existing)
        if not allow_replace:
            raise FormalReviewError(f"Conflicto de bytes para el artefacto administrativo: {path}")
    _atomic_write(path, payload)
    return sha256_bytes(payload)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [{str(key): "" if value is None else str(value).strip() for key, value in row.items() if key}
                    for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FormalReviewError(f"No se pudo leer {path}: {exc}") from exc
    if not fields:
        raise FormalReviewError(f"CSV sin encabezado: {path}")
    return fields, rows


def _require_relative_path(root: Path, raw: str, *, field: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FormalReviewError(f"{field} debe ser una ruta relativa segura: {raw}")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise FormalReviewError(f"{field} sale del repositorio: {raw}") from exc
    if not resolved.is_file():
        raise FormalReviewError(f"No existe la entrada visual {raw}")
    return resolved


def load_formal_inputs(
    *,
    root: Path | str = ROOT,
    queue_path: Path | str = FORMAL_QUEUE_PATH,
    unobserved_path: Path | str = FORMAL_UNOBSERVED_PATH,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Load and validate the existing 28/2 administrative inputs only."""

    root_path = Path(root).resolve()
    queue = Path(queue_path)
    unobserved = Path(unobserved_path)
    queue_fields, queue_rows = _read_csv(queue)
    required = {"event_id", "quicklook_path", "pre_timestamp_utc", "post_timestamp_utc", "review_status"}
    missing = sorted(required - set(queue_fields))
    if missing:
        raise FormalReviewError(f"Colas formal incompatible; faltan columnas: {missing}")
    if len(queue_rows) != FORMAL_OBSERVABLE_COUNT:
        raise FormalReviewError(f"Se esperaban {FORMAL_OBSERVABLE_COUNT} observables; llegaron {len(queue_rows)}")
    event_ids = [row["event_id"] for row in queue_rows]
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        raise FormalReviewError("La cola formal tiene event_id vacío o duplicado")
    if any("2026" in "|".join(row.values()) for row in queue_rows):
        raise FormalReviewError("La cola formal contiene datos de 2026")
    if any(row.get("review_status", "") for row in queue_rows):
        raise FormalReviewError("La cola formal no está vacía; no se ejecuta una revisión sobre datos existentes")

    events: list[dict[str, Any]] = []
    for row in queue_rows:
        panel = _require_relative_path(root_path, row["quicklook_path"], field="quicklook_path")
        events.append(
            {
                "event_id": row["event_id"],
                "quicklook_path": row["quicklook_path"],
                "quicklook_sha256": sha256_file(panel),
                "pre_timestamp_utc": row["pre_timestamp_utc"],
                "post_timestamp_utc": row["post_timestamp_utc"],
                "selected_combination_id": row.get("selected_combination_id", ""),
                "policy_path": row.get("policy_path", ""),
            }
        )

    unobserved_fields, unobserved_rows = _read_csv(unobserved)
    if not {"event_id", "observability_status", "exclusion_reason", "protocol_version"}.issubset(unobserved_fields):
        raise FormalReviewError("Registro unobserved incompatible")
    if len(unobserved_rows) != FORMAL_UNOBSERVED_COUNT:
        raise FormalReviewError(f"Se esperaban {FORMAL_UNOBSERVED_COUNT} no observables; llegaron {len(unobserved_rows)}")
    unobserved_ids = [row["event_id"] for row in unobserved_rows]
    if len(set(unobserved_ids)) != len(unobserved_ids) or set(unobserved_ids) & set(event_ids):
        raise FormalReviewError("Los observables y no observables no son disjuntos")
    if any(row.get("observability_status") != "unobserved" or not row.get("exclusion_reason") for row in unobserved_rows):
        raise FormalReviewError("Registro unobserved incompleto")
    if any("2026" in "|".join(row.values()) for row in unobserved_rows):
        raise FormalReviewError("El registro unobserved contiene datos de 2026")
    unobserved_clean = [
        {
            "event_id": row["event_id"],
            "observability_status": "unobserved",
            "exclusion_reason": row["exclusion_reason"],
            "protocol_version": row["protocol_version"],
        }
        for row in unobserved_rows
    ]
    return events, unobserved_clean


def resolve_private_seed(seed_path: Path, supplied_seed: str | None = None) -> tuple[str, str]:
    """Return a private seed and its hash without placing the seed in Git."""

    seed = (supplied_seed or os.environ.get(FORMAL_SEED_ENV) or "").strip()
    if seed:
        if len(seed) < 16:
            raise FormalReviewError("La semilla privada debe tener al menos 16 caracteres")
        if not seed_path.exists():
            _atomic_write(seed_path, (seed + "\n").encode("utf-8"))
        else:
            stored = seed_path.read_text(encoding="utf-8").strip()
            if stored != seed:
                raise FormalReviewError("La semilla suministrada no coincide con la semilla privada local")
    else:
        if seed_path.exists():
            seed = seed_path.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_hex(32)
            _atomic_write(seed_path, (seed + "\n").encode("utf-8"))
    if len(seed) < 16:
        raise FormalReviewError("La semilla privada local es demasiado corta")
    return seed, sha256_bytes(seed.encode("utf-8"))


def build_slot_assignments(
    events: Sequence[Mapping[str, Any]],
    *,
    slot_id: str,
    private_seed: str,
    protocol_version: str = FORMAL_PROTOCOL_VERSION,
) -> list[dict[str, Any]]:
    if slot_id not in FORMAL_SLOT_IDS:
        raise FormalReviewError(f"Slot formal inválido: {slot_id}")
    sortable: list[tuple[str, Mapping[str, Any]]] = []
    for event in events:
        event_id = str(event["event_id"])
        digest = hashlib.sha256(
            f"{FORMAL_ROUND_ID}|{protocol_version}|{slot_id}|{private_seed}|{event_id}".encode("utf-8")
        ).hexdigest()
        sortable.append((digest, event))
    assignments: list[dict[str, Any]] = []
    for order, (digest, event) in enumerate(sorted(sortable, key=lambda item: (item[0], str(item[1]["event_id"]))), start=1):
        alias = f"{slot_id}_ITEM_{order:03d}_{digest[:12]}"
        assignments.append(
            {
                "assignment_id": digest[12:44],
                "event_id": str(event["event_id"]),
                "blind_alias": alias,
                "randomized_order": order,
                "visual_reference_key": f"panel://{alias}",
                "visual_input_reference": str(event["quicklook_path"]),
                "quicklook_path": str(event["quicklook_path"]),
                "quicklook_sha256": str(event["quicklook_sha256"]),
                "temporal_input_reference": event.get("temporal_input_reference"),
                "temporal_input_sha256": event.get("temporal_input_sha256"),
                "temporal_input_manifest_sha256": event.get("temporal_input_manifest_sha256"),
                "temporal_input_mode": event.get("temporal_input_mode"),
                "temporal_input_provenance": event.get("temporal_input_provenance"),
            }
        )
    return assignments


def build_pairwise_comparison(review_a: Mapping[str, Any], review_b: Mapping[str, Any]) -> dict[str, Any]:
    """Compare two structured observations without producing a consensus."""

    field_agreements: dict[str, bool] = {}
    material: list[str] = []
    nonmaterial: list[str] = []
    for field in PASS_A_FIELDS + PASS_B_FIELDS:
        if field not in review_a or field not in review_b:
            continue
        same = review_a.get(field) == review_b.get(field)
        field_agreements[field] = same
        if not same:
            if field in MATERIAL_PAIR_FIELDS:
                material.append(field)
            elif field in NONMATERIAL_PAIR_FIELDS or field == "confidence_after":
                nonmaterial.append(field)
    association_a = review_a.get("event_association")
    association_b = review_b.get("event_association")
    association_material = (
        association_a != association_b
        and ((association_a == "indeterminate") != (association_b == "indeterminate")
             or {association_a, association_b} == {"likely", "unlikely"})
    )
    reasons: list[str] = []
    if review_a.get("visible_burn_scar") != review_b.get("visible_burn_scar"):
        reasons.append("interreview_visible_disagreement")
    if association_material and "event_association" not in material:
        material.append("event_association")
        reasons.append("interreview_material_association_disagreement")
    if review_a.get("mode_agreement") == "disagree" or review_b.get("mode_agreement") == "disagree":
        reasons.append("interreview_mode_disagreement")
    return {
        "field_agreements": field_agreements,
        "material_disagreements": sorted(set(material)),
        "nonmaterial_disagreements": sorted(set(nonmaterial)),
        "needs_adjudication": bool(material or reasons),
        "reason_codes": sorted(set(reasons)),
        "consensus": None,
    }


def _reviewer_request(review: Mapping[str, Any]) -> bool:
    if not review.get("reviewer_requested_adjudication"):
        return False
    return review.get("request_reason") in REQUEST_REASON_CODES


def derive_formal_triage(
    review: Mapping[str, Any],
    *,
    peer_review: Mapping[str, Any] | None = None,
    pairwise: Mapping[str, Any] | None = None,
    adjudication: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive administrative triage from structured fields only.

    Confounders and limitations can recommend an expert; neither alone makes
    an expert review mandatory.  Mandatory expert priority requires a later
    adjudication with a specialist question code.
    """

    adjudication_reasons: list[str] = []
    if review.get("visible_burn_scar") == "ambiguous":
        adjudication_reasons.append("ambiguous_observation")
    if review.get("scar_confidence") == "low":
        adjudication_reasons.append("low_confidence")
    if review.get("event_association") == "indeterminate":
        adjudication_reasons.append("indeterminate_association")
    if review.get("mode_agreement") == "disagree":
        adjudication_reasons.append("mode_disagreement")
    if _reviewer_request(review):
        adjudication_reasons.append("structured_reviewer_request")
    if peer_review is not None:
        pairwise = pairwise or build_pairwise_comparison(review, peer_review)
    if pairwise:
        adjudication_reasons.extend(pairwise.get("reason_codes", []))
        if pairwise.get("needs_adjudication") and pairwise.get("material_disagreements"):
            adjudication_reasons.append("material_interreview_disagreement")

    expert_reasons: list[str] = []
    surface = review.get("competing_land_change")
    if surface in {"agriculture_or_harvest", "mixed", "unknown"}:
        expert_reasons.append(f"strong_competing_surface={surface}")
    if surface in {"soil_exposure", "vegetation_phenology", "moisture_or_flooding", "water", "urban_or_construction"}:
        expert_reasons.append(f"competing_surface={surface}")
    limitation = review.get("observation_limitation")
    if limitation and limitation != "none":
        expert_reasons.append(f"observation_limitation={limitation}")
    if review.get("confidence_after") and review.get("scar_confidence") and review.get("confidence_after") != review.get("scar_confidence"):
        expert_reasons.append("confidence_changed_between_passes")
    if peer_review is not None and review.get("scar_confidence") != peer_review.get("scar_confidence"):
        expert_reasons.append("persistent_interreview_confidence_difference")
    if pairwise and pairwise.get("nonmaterial_disagreements"):
        expert_reasons.append("persistent_nonmaterial_interreview_difference")
    if review.get("event_association") in {"likely", "possible"} and surface in {"agriculture_or_harvest", "mixed", "unknown"}:
        expert_reasons.append("determined_association_with_strong_competitor")

    expert_priority = "none"
    if expert_reasons:
        expert_priority = "recommended"
    if adjudication:
        specialist_code = str(adjudication.get("specialist_question_code") or "").strip()
        unresolved = adjudication.get("material_disagreement_resolved") in {False, 0, "0", "false"}
        complete = adjudication.get("resolution_status") == "complete"
        if specialist_code and complete and unresolved:
            expert_priority = "required"
            expert_reasons.append("adjudication_requires_specialist_question")

    unique_adjudication = sorted(set(adjudication_reasons))
    unique_expert = sorted(set(expert_reasons))
    needs = bool(unique_adjudication)
    if expert_priority == "required":
        administrative_status = "pending_expert_review"
    elif needs:
        administrative_status = "pending_adjudication"
    elif expert_priority == "recommended":
        administrative_status = "pending_expert_review"
    else:
        administrative_status = "pending"
    return {
        "needs_adjudication": needs,
        "adjudication_reason_codes": unique_adjudication,
        "expert_review_priority": expert_priority,
        "expert_review_reason_codes": unique_expert,
        "administrative_status": administrative_status,
    }


def _formal_profile_errors(
    *,
    reviewer_type: str,
    reviewer_expertise: str,
    model_name: str | None,
    model_version: str | None,
    label_status: str,
) -> list[str]:
    errors: list[str] = []
    if reviewer_type not in {"human", "ai_assisted"}:
        errors.append("reviewer_type inválido")
    if reviewer_expertise not in REVIEWER_EXPERTISE:
        errors.append("reviewer_expertise inválido")
    if reviewer_type == "human":
        if reviewer_expertise == "not_applicable":
            errors.append("un humano requiere expertise")
        if model_name or model_version:
            errors.append("un humano no puede tener modelo")
        if label_status != "human_observation":
            errors.append("proveniencia humana inválida")
    elif reviewer_type == "ai_assisted":
        if not model_name or not model_version:
            errors.append("un revisor IA requiere modelo y versión")
        if reviewer_expertise != "not_applicable":
            errors.append("un revisor IA requiere expertise not_applicable")
        if label_status != "provisional_pseudolabel":
            errors.append("proveniencia IA inválida")
    return errors


def validate_formal_provenance(
    *,
    reviewer_type: str,
    reviewer_expertise: str,
    model_name: str | None = None,
    model_version: str | None = None,
    label_status: str,
) -> list[str]:
    return _formal_profile_errors(
        reviewer_type=reviewer_type,
        reviewer_expertise=reviewer_expertise,
        model_name=model_name,
        model_version=model_version,
        label_status=label_status,
    )


def _pass_a_payload(
    row: Mapping[str, Any],
    *,
    revision: int | None = None,
) -> dict[str, Any]:
    return {
        "visible_burn_scar": row.get("visible_burn_scar"),
        "scar_confidence": row.get("scar_confidence"),
        "event_association": row.get("event_association"),
        "competing_land_change": row.get("competing_land_change"),
        "observation_limitation": row.get("observation_limitation"),
        "notes": row.get("notes") or "",
        "revision": int(row.get("revision") if revision is None else revision),
    }


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _profile_identity(
    *,
    profile_id: str,
    reviewer_type: str,
    reviewer_expertise: str,
    model_name: str | None,
    model_version: str | None,
    training_version: str,
    label_status: str,
    active: int,
) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "reviewer_type": reviewer_type,
        "reviewer_expertise": reviewer_expertise,
        "model_name": model_name,
        "model_version": model_version,
        "protocol_training_version": training_version,
        "label_status": label_status,
        "active": int(active),
    }


def _public_manifest(
    *,
    slot_id: str,
    assignments: Sequence[Mapping[str, Any]],
    protocol_sha256: str,
    input_manifest_sha256: str,
    private_seed_sha256: str,
) -> dict[str, Any]:
    return {
        "manifest_version": "formal-review-package-v1",
        "round_id": FORMAL_ROUND_ID,
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "tool_version": FORMAL_TOOL_VERSION,
        "slot_id": slot_id,
        "protocol_sha256": protocol_sha256,
        "input_manifest_sha256": input_manifest_sha256,
        "private_seed_sha256": private_seed_sha256,
        "image_copies_included": False,
        "items": [
            {
                "blind_alias": item["blind_alias"],
                "randomized_order": item["randomized_order"],
                "visual_reference_key": item["visual_reference_key"],
                "visual_input_sha256": item["quicklook_sha256"],
            }
            for item in assignments
        ],
    }


@dataclass(frozen=True)
class PreparationResult:
    round_id: str
    database_path: Path
    output_dir: Path
    observable_count: int
    unobserved_count: int
    assignment_count: int
    protocol_sha256: str
    input_manifest_sha256: str
    private_seed_sha256: str
    package_paths: tuple[Path, ...]
    package_hashes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "database_path": str(self.database_path),
            "output_dir": str(self.output_dir),
            "observable_count": self.observable_count,
            "unobserved_count": self.unobserved_count,
            "assignment_count": self.assignment_count,
            "protocol_sha256": self.protocol_sha256,
            "input_manifest_sha256": self.input_manifest_sha256,
            "private_seed_sha256": self.private_seed_sha256,
            "package_paths": [str(path) for path in self.package_paths],
            "package_hashes": list(self.package_hashes),
        }


class FormalReviewStore:
    """Persistence API for the formal round; no data is created on import."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 3000")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "FormalReviewStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def initialize(self) -> None:
        self.connection.executescript(SCHEMA_SQL)
        apply_migrations(self.connection)

    def _now(self) -> str:
        return utc_timestamp()

    def register_human_profile(self, profile_id: str, expertise: str, *, training_version: str) -> None:
        profile_id = profile_id.strip()
        training_version = training_version.strip()
        errors = validate_formal_provenance(
            reviewer_type="human",
            reviewer_expertise=expertise,
            label_status="human_observation",
        )
        if errors or not profile_id or not training_version:
            raise FormalReviewError("Perfil humano inválido: " + "; ".join(errors or ["faltan identificadores"]))
        proposed = _profile_identity(
            profile_id=profile_id,
            reviewer_type="human",
            reviewer_expertise=expertise,
            model_name=None,
            model_version=None,
            training_version=training_version,
            label_status="human_observation",
            active=1,
        )
        existing = self.connection.execute(
            "SELECT profile_id, reviewer_type, reviewer_expertise, model_name, model_version, "
            "protocol_training_version, label_status, active FROM reviewer_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if existing is not None:
            actual = _profile_identity(
                profile_id=existing["profile_id"],
                reviewer_type=existing["reviewer_type"],
                reviewer_expertise=existing["reviewer_expertise"],
                model_name=existing["model_name"],
                model_version=existing["model_version"],
                training_version=existing["protocol_training_version"],
                label_status=existing["label_status"],
                active=existing["active"],
            )
            if actual == proposed:
                return
            raise FormalReviewError("Conflicto explícito: el profile_id ya existe con otro contrato")
        now = self._now()
        self.connection.execute(
            """
            INSERT INTO reviewer_profiles
              (profile_id, reviewer_type, reviewer_expertise, model_name, model_version,
               protocol_training_version, label_status, created_at, updated_at)
            VALUES (?, 'human', ?, NULL, NULL, ?, 'human_observation', ?, ?)
            """,
            (profile_id, expertise, training_version, now, now),
        )
        self.connection.commit()

    def bind_slot(self, round_id: str, slot_id: str, profile_id: str) -> None:
        profile_id = profile_id.strip()
        if slot_id not in FORMAL_SLOT_IDS:
            raise FormalReviewError("Slot inválido")
        round_row = self.connection.execute(
            "SELECT status, execution_status, execution_authorized FROM formal_review_rounds WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        if round_row is None:
            raise FormalReviewError("La ronda formal no existe")
        if round_row["status"] != "prepared" or round_row["execution_status"] != "not_started":
            raise FormalReviewError("Solo se puede vincular un slot en una ronda prepared/not_started")
        profile = self.connection.execute(
            "SELECT profile_id, reviewer_type, label_status, active FROM reviewer_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if profile is None or profile["reviewer_type"] != "human" or profile["label_status"] != "human_observation" or not profile["active"]:
            raise FormalReviewError("El slot solo puede vincularse a un perfil humano activo")
        slot = self.connection.execute(
            "SELECT profile_id, status FROM formal_review_slots WHERE round_id = ? AND slot_id = ?",
            (round_id, slot_id),
        ).fetchone()
        if slot is None:
            raise FormalReviewError("La ronda/slot no existe")
        if slot["profile_id"] is not None:
            if slot["profile_id"] == profile_id and slot["status"] in {"bound", "active"}:
                return
            raise FormalReviewError("El slot ya está vinculado a otro perfil")
        other_slot = self.connection.execute(
            "SELECT slot_id FROM formal_review_slots WHERE round_id = ? AND profile_id = ? AND slot_id <> ?",
            (round_id, profile_id, slot_id),
        ).fetchone()
        if other_slot is not None:
            raise FormalReviewError("Un mismo perfil no puede ocupar ambos slots de la ronda")
        now = self._now()
        updated = self.connection.execute(
            "UPDATE formal_review_slots SET profile_id = ?, status = 'bound', updated_at = ? WHERE round_id = ? AND slot_id = ? AND status = 'unbound'",
            (profile_id, now, round_id, slot_id),
        ).rowcount
        if updated != 1:
            raise FormalReviewError("La ronda/slot no existe o ya está vinculado")
        self.connection.commit()

    def list_assignments(self, round_id: str, slot_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM formal_assignments WHERE round_id = ? AND slot_id = ? ORDER BY randomized_order",
            (round_id, slot_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_pass_a(self, round_id: str, slot_id: str, event_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM formal_pass_a WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            (round_id, slot_id, event_id),
        ).fetchone()
        return None if row is None else dict(row)

    def get_pass_b(self, round_id: str, slot_id: str, event_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM formal_pass_b WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            (round_id, slot_id, event_id),
        ).fetchone()
        return None if row is None else dict(row)

    def _bound_profile(self, round_id: str, slot_id: str, profile_id: str | None = None) -> sqlite3.Row:
        row = self.connection.execute(
            """
            SELECT s.profile_id, s.status AS slot_status, p.reviewer_type, p.reviewer_expertise, p.label_status, p.active,
                   r.status AS round_status, r.execution_status, r.execution_authorized
            FROM formal_review_slots AS s JOIN reviewer_profiles AS p ON p.profile_id = s.profile_id
            JOIN formal_review_rounds AS r ON r.round_id = s.round_id
            WHERE s.round_id = ? AND s.slot_id = ? AND s.status IN ('bound', 'active')
            """,
            (round_id, slot_id),
        ).fetchone()
        if row is None:
            raise FormalReviewError("El slot no está vinculado a un perfil humano")
        if profile_id is not None and row["profile_id"] != profile_id:
            raise FormalReviewError("El perfil no está vinculado al slot solicitado")
        if row["reviewer_type"] != "human" or row["label_status"] != "human_observation" or not row["active"]:
            raise FormalReviewError("El slot no está vinculado a un perfil humano activo")
        if row["round_status"] != "prepared" or row["execution_status"] != "not_started":
            raise FormalReviewError("La ronda no está en estado prepared/not_started")
        if not row["execution_authorized"]:
            raise FormalReviewError("La ejecución formal aún no está autorizada")
        return row

    def validate_slot_session(self, round_id: str, slot_id: str, profile_id: str) -> sqlite3.Row:
        """Validate the server-side slot/profile binding without exposing other slots."""

        if slot_id not in FORMAL_SLOT_IDS or not profile_id.strip():
            raise FormalReviewError("Identidad formal de slot inválida")
        other = self.connection.execute(
            "SELECT slot_id FROM formal_review_slots WHERE round_id = ? AND profile_id = ? AND slot_id <> ?",
            (round_id, profile_id, slot_id),
        ).fetchone()
        if other is not None:
            raise FormalReviewError("El perfil está vinculado a otro slot")
        return self._bound_profile(round_id, slot_id, profile_id)

    def save_pass_a(
        self,
        *,
        round_id: str,
        slot_id: str,
        event_id: str,
        visible_burn_scar: str,
        scar_confidence: str,
        event_association: str,
        competing_land_change: str,
        observation_limitation: str,
        notes: str = "",
        amend: bool = False,
        amendment_reason: str | None = None,
    ) -> dict[str, Any]:
        profile = self._bound_profile(round_id, slot_id)
        assignment = self.connection.execute(
            "SELECT assignment_id FROM formal_assignments WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            (round_id, slot_id, event_id),
        ).fetchone()
        if assignment is None:
            raise FormalReviewError("Asignación formal inexistente")
        values = {
            "visible_burn_scar": visible_burn_scar,
            "scar_confidence": scar_confidence,
            "event_association": event_association,
            "competing_land_change": competing_land_change,
            "observation_limitation": observation_limitation,
        }
        if visible_burn_scar not in VISIBLE_CODES or scar_confidence not in CONFIDENCE_CODES or event_association not in ASSOCIATION_CODES or competing_land_change not in SURFACE_CODES or observation_limitation not in LIMITATION_CODES:
            raise FormalReviewError("Código de Pass A fuera del protocolo congelado")
        existing = self.get_pass_a(round_id, slot_id, event_id)
        if existing and not amend:
            raise FormalReviewError("Pass A está bloqueada; una enmienda requiere razón")
        if amend and (not existing or not (amendment_reason or "").strip()):
            raise FormalReviewError("La enmienda requiere una razón explícita")
        now = self._now()
        payload = _pass_a_payload({**values, "notes": notes or ""}, revision=int(existing["revision"]) + 1 if existing else 1)
        payload_hash = _payload_sha256(payload)
        if existing:
            existing_payload = _pass_a_payload(existing)
            if existing["payload_sha256"] != _payload_sha256(existing_payload):
                raise FormalReviewError("La Pass A existente tiene un hash incompatible; integridad comprometida")
            self.connection.execute(
                """
                INSERT INTO formal_amendments
                  (round_id, slot_id, event_id, pass_name, revision, previous_payload_json,
                   corrected_payload_json, previous_payload_sha256, corrected_payload_sha256,
                   amendment_reason, actor_profile_id, created_at)
                VALUES (?, ?, ?, 'pass_a', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_id,
                    slot_id,
                    event_id,
                    payload["revision"],
                    _canonical_json(existing_payload),
                    _canonical_json(payload),
                    existing["payload_sha256"],
                    payload_hash,
                    amendment_reason.strip(),
                    profile["profile_id"],
                    now,
                ),
            )
            self.connection.execute(
                """
                UPDATE formal_pass_a SET profile_id = ?, visible_burn_scar = ?, scar_confidence = ?,
                    event_association = ?, competing_land_change = ?, observation_limitation = ?,
                    notes = ?, payload_sha256 = ?, revision = ?, locked_at = ?, updated_at = ?
                WHERE round_id = ? AND slot_id = ? AND event_id = ?
                """,
                (profile["profile_id"], visible_burn_scar, scar_confidence, event_association, competing_land_change, observation_limitation, notes or "", payload_hash, payload["revision"], now, now, round_id, slot_id, event_id),
            )
        else:
            self.connection.execute(
                """
                INSERT INTO formal_pass_a
                  (round_id, slot_id, event_id, assignment_id, profile_id, reviewer_type, reviewer_expertise,
                   label_status, visible_burn_scar, scar_confidence, event_association, competing_land_change,
                   observation_limitation, notes, payload_sha256, locked_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'human', ?, 'human_observation', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (round_id, slot_id, event_id, assignment["assignment_id"], profile["profile_id"], profile["reviewer_expertise"], visible_burn_scar, scar_confidence, event_association, competing_land_change, observation_limitation, notes or "", payload_hash, now, now, now),
            )
        self.connection.execute(
            "UPDATE formal_assignments SET status = 'pass_a_locked' WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            (round_id, slot_id, event_id),
        )
        self.connection.execute(
            "INSERT INTO formal_audit_log (round_id, slot_id, event_id, actor_profile_id, action, object_type, object_id, new_payload_sha256, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (round_id, slot_id, event_id, profile["profile_id"], "amend_pass_a" if existing else "save_pass_a", "formal_pass_a", event_id, payload_hash, amendment_reason or "", now),
        )
        self.connection.commit()
        return dict(self.connection.execute("SELECT * FROM formal_pass_a WHERE round_id = ? AND slot_id = ? AND event_id = ?", (round_id, slot_id, event_id)).fetchone())

    def save_pass_b(
        self,
        *,
        round_id: str,
        slot_id: str,
        event_id: str,
        mode_agreement: str,
        confidence_after: str,
        reviewer_requested_adjudication: bool,
        request_reason: str | None = None,
        notes: str = "",
        selected_pair_reference: Mapping[str, Any] | None = None,
        window_median_reference: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.get_pass_a(round_id, slot_id, event_id) is None:
            raise FormalReviewError("Pass B requiere Pass A bloqueada")
        profile = self._bound_profile(round_id, slot_id)
        existing = self.get_pass_b(round_id, slot_id, event_id)
        if existing is not None:
            raise FormalReviewError("Pass B es insert-once; una enmienda formal futura debe conservar la fila original")
        if mode_agreement not in MODE_CODES or confidence_after not in CONFIDENCE_CODES:
            raise FormalReviewError("Código de Pass B fuera del protocolo congelado")
        if reviewer_requested_adjudication and request_reason not in REQUEST_REASON_CODES:
            raise FormalReviewError("La solicitud de adjudicación requiere un motivo estructurado")
        if not reviewer_requested_adjudication:
            request_reason = None
        assignment = self.connection.execute(
            "SELECT * FROM formal_assignments WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            (round_id, slot_id, event_id),
        ).fetchone()
        if assignment is None:
            raise FormalReviewError("Asignación formal inexistente")
        selected = self._validate_pass_b_reference(
            selected_pair_reference,
            assignment=assignment,
            mode="selected_pair",
            field_name="selected_pair_reference",
            expected_path=assignment["visual_input_reference"],
            expected_sha=assignment["visual_input_sha256"],
            expected_manifest=assignment["visual_input_manifest_sha256"],
        )
        temporal = self._validate_pass_b_reference(
            window_median_reference,
            assignment=assignment,
            mode="window_median",
            field_name="window_median_reference",
            expected_path=assignment["temporal_input_reference"],
            expected_sha=assignment["temporal_input_sha256"],
            expected_manifest=assignment["temporal_input_manifest_sha256"],
        )
        if selected["path"] == temporal["path"] or selected["sha256"] == temporal["sha256"]:
            raise FormalReviewError("Las referencias selected_pair y window_median deben ser distintas")
        now = self._now()
        payload = {
            "mode_agreement": mode_agreement,
            "confidence_after": confidence_after,
            "reviewer_requested_adjudication": bool(reviewer_requested_adjudication),
            "request_reason": request_reason,
            "notes": notes or "",
            "selected_pair_reference": selected,
            "window_median_reference": temporal,
        }
        payload_hash = _payload_sha256(payload)
        self.connection.execute(
            """
            INSERT INTO formal_pass_b
              (round_id, slot_id, event_id, assignment_id, profile_id, mode_agreement, confidence_after,
               reviewer_requested_adjudication, request_reason, notes, payload_sha256,
               selected_pair_reference, selected_pair_sha256, selected_pair_manifest_sha256,
               selected_pair_mode, selected_pair_provenance,
               window_median_reference, window_median_sha256, window_median_manifest_sha256,
               window_median_mode, window_median_provenance, saved_at, created_at, updated_at)
             SELECT round_id, slot_id, event_id, assignment_id, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            FROM formal_pass_a WHERE round_id = ? AND slot_id = ? AND event_id = ?
            """,
            (
                profile["profile_id"],
                mode_agreement,
                confidence_after,
                int(reviewer_requested_adjudication),
                request_reason,
                notes or "",
                payload_hash,
                selected["path"],
                selected["sha256"],
                selected["manifest_sha256"],
                selected["mode"],
                selected["provenance"],
                temporal["path"],
                temporal["sha256"],
                temporal["manifest_sha256"],
                temporal["mode"],
                temporal["provenance"],
                now,
                now,
                now,
                round_id,
                slot_id,
                event_id,
            ),
        )
        self.connection.execute(
            "UPDATE formal_assignments SET status = ? WHERE round_id = ? AND slot_id = ? AND event_id = ?",
            ("pending_adjudication" if reviewer_requested_adjudication else "pending_pair_review", round_id, slot_id, event_id),
        )
        self.connection.execute(
            "INSERT INTO formal_audit_log (round_id, slot_id, event_id, actor_profile_id, action, object_type, object_id, new_payload_sha256, reason, created_at) VALUES (?, ?, ?, ?, 'save_pass_b', 'formal_pass_b', ?, ?, ?, ?)",
            (round_id, slot_id, event_id, profile["profile_id"], event_id, payload_hash, request_reason or "", now),
        )
        self.connection.commit()
        return dict(self.get_pass_b(round_id, slot_id, event_id) or {})

    def _validate_pass_b_reference(
        self,
        reference: Mapping[str, Any] | None,
        *,
        assignment: sqlite3.Row,
        mode: str,
        field_name: str,
        expected_path: str | None,
        expected_sha: str | None,
        expected_manifest: str | None,
    ) -> dict[str, str]:
        if reference is None:
            raise FormalReviewError(f"Pass B requiere {field_name} trazable")
        path = str(reference.get("path") or "").strip().replace("\\", "/")
        sha = str(reference.get("sha256") or "").strip().lower()
        manifest_sha = str(reference.get("manifest_sha256") or "").strip().lower()
        reference_mode = str(reference.get("mode") or "").strip()
        provenance = str(reference.get("provenance") or "").strip()
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise FormalReviewError(f"{field_name} debe ser una ruta relativa segura")
        if reference_mode != mode or not provenance:
            raise FormalReviewError(f"{field_name} tiene modo o proveniencia incompatible")
        if not expected_path or not expected_sha or not expected_manifest:
            raise FormalReviewError(f"{field_name} no está congelada en el manifest de la asignación")
        expected_normalized = str(expected_path).replace("\\", "/")
        if path != expected_normalized or sha != str(expected_sha).lower() or manifest_sha != str(expected_manifest).lower():
            raise FormalReviewError(f"{field_name} no coincide con la asignación formal")
        absolute = (ROOT / path).resolve()
        try:
            absolute.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise FormalReviewError(f"{field_name} sale del repositorio") from exc
        if not absolute.is_file():
            raise FormalReviewError(f"No existe el artefacto referenciado por {field_name}")
        actual_sha = sha256_file(absolute)
        if actual_sha != sha:
            raise FormalReviewError(f"Hash de archivo incompatible para {field_name}")
        return {
            "path": path,
            "sha256": sha,
            "manifest_sha256": manifest_sha,
            "mode": reference_mode,
            "provenance": provenance,
        }


def _legacy_prepare_formal_round(
    *,
    root: Path | str = ROOT,
    db_path: Path | str = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3",
    queue_path: Path | str = FORMAL_QUEUE_PATH,
    unobserved_path: Path | str = FORMAL_UNOBSERVED_PATH,
    protocol_path: Path | str = FORMAL_PROTOCOL_PATH,
    output_dir: Path | str = FORMAL_OUTPUT_DIR,
    seed_path: Path | str | None = None,
    supplied_seed: str | None = None,
    base_head: str = "f302139",
) -> PreparationResult:
    """Prepare both blind packages and the empty formal round idempotently."""

    root_path = Path(root).resolve()
    database_path = Path(db_path)
    output_path = Path(output_dir)
    protocol = Path(protocol_path)
    if not protocol.is_file():
        raise FormalReviewError(f"No existe el protocolo congelado: {protocol}")
    protocol_sha = sha256_file(protocol)
    events, unobserved = load_formal_inputs(root=root_path, queue_path=queue_path, unobserved_path=unobserved_path)
    queue_sha = sha256_file(Path(queue_path))
    unobserved_sha = sha256_file(Path(unobserved_path))
    source_manifest = {
        "round_id": FORMAL_ROUND_ID,
        "queue_sha256": queue_sha,
        "unobserved_sha256": unobserved_sha,
        "observable_count": len(events),
        "unobserved_count": len(unobserved),
    }
    source_manifest_sha = sha256_bytes(_canonical_json(source_manifest).encode("utf-8"))
    visual_manifest = {
        "events": [
            {"event_id": item["event_id"], "visual_input_sha256": item["quicklook_sha256"], "visual_reference": item["quicklook_path"]}
            for item in events
        ]
    }
    input_manifest_sha = sha256_bytes(_canonical_json({"source": source_manifest_sha, "visual": visual_manifest}).encode("utf-8"))
    output_path.mkdir(parents=True, exist_ok=True)
    seed_file = Path(seed_path) if seed_path else output_path / "private_seed.txt"
    private_seed, private_seed_sha = resolve_private_seed(seed_file, supplied_seed)
    comparable_round = {
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "schema_version": FORMAL_SCHEMA_VERSION,
        "tool_version": FORMAL_TOOL_VERSION,
        "status": "prepared",
        "base_head": base_head,
        "pilot_event_count": 30,
        "observable_event_count": len(events),
        "unobserved_event_count": len(unobserved),
        "protocol_sha256": protocol_sha,
        "source_manifest_sha256": source_manifest_sha,
        "input_manifest_sha256": input_manifest_sha,
        "private_seed_sha256": private_seed_sha,
    }
    # Validate an existing identity before writing any package bytes.  A
    # changed input must fail without overwriting a valid prepared package.
    with FormalReviewStore(database_path) as existing_store:
        existing_store.initialize()
        existing_round = existing_store.connection.execute(
            "SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)
        ).fetchone()
        if existing_round is not None and any(existing_round[key] != value for key, value in comparable_round.items()):
            raise FormalReviewError("La ronda formal existente no coincide; no se sobreescribe")
    assignments_by_slot = {
        slot: build_slot_assignments(events, slot_id=slot, private_seed=private_seed)
        for slot in FORMAL_SLOT_IDS
    }
    private_map = {
        "round_id": FORMAL_ROUND_ID,
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "private_seed_sha256": private_seed_sha,
        "items": {
            slot: [
                {
                    "assignment_id": item["assignment_id"],
                    "blind_alias": item["blind_alias"],
                    "randomized_order": item["randomized_order"],
                    "event_id": item["event_id"],
                    "quicklook_path": item["quicklook_path"],
                    "quicklook_sha256": item["quicklook_sha256"],
                }
                for item in assignments
            ]
            for slot, assignments in assignments_by_slot.items()
        },
    }
    private_path = output_path / "private" / "assignment_map.json"
    private_sha = _write_checked(private_path, _json_bytes(private_map), allow_replace=False)
    package_paths: list[Path] = []
    package_hashes: list[str] = []
    public_manifests: dict[str, tuple[Path, str, dict[str, Any]]] = {}
    for slot, assignments in assignments_by_slot.items():
        manifest = _public_manifest(
            slot_id=slot,
            assignments=assignments,
            protocol_sha256=protocol_sha,
            input_manifest_sha256=input_manifest_sha,
            private_seed_sha256=private_seed_sha,
        )
        package_path = output_path / slot.lower() / "manifest.json"
        package_sha = _write_checked(package_path, _json_bytes(manifest), allow_replace=False)
        public_manifests[slot] = (package_path, package_sha, manifest)
        package_paths.append(package_path)
        package_hashes.append(package_sha)
    summary_path = output_path / "preparation_summary.json"
    summary = {
        "round_id": FORMAL_ROUND_ID,
        "status": "prepared",
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "schema_version": FORMAL_SCHEMA_VERSION,
        "tool_version": FORMAL_TOOL_VERSION,
        "migration_version": CURRENT_MIGRATION_VERSION,
        "base_head": base_head,
        "observable_count": len(events),
        "unobserved_count": len(unobserved),
        "assignment_count": len(events) * len(FORMAL_SLOT_IDS),
        "protocol_sha256": protocol_sha,
        "source_manifest_sha256": source_manifest_sha,
        "input_manifest_sha256": input_manifest_sha,
        "private_seed_sha256": private_seed_sha,
        "package_hashes": {slot: public_manifests[slot][1] for slot in FORMAL_SLOT_IDS},
        "formal_review_executed": False,
    }
    _write_checked(summary_path, _json_bytes(summary), allow_replace=False)
    with FormalReviewStore(database_path) as store:
        store.initialize()
        now = store._now()
        existing = store.connection.execute("SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()
        if existing is not None:
            if any(existing[key] != value for key, value in comparable_round.items()):
                raise FormalReviewError("La ronda formal existente no coincide; no se sobreescribe")
        else:
            store.connection.execute(
                """
                INSERT INTO formal_review_rounds
                  (round_id, protocol_version, schema_version, tool_version, status, base_head,
                   pilot_event_count, observable_event_count, unobserved_event_count, protocol_sha256,
                   source_manifest_sha256, input_manifest_sha256, private_seed_sha256, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'prepared', ?, 30, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (FORMAL_ROUND_ID, FORMAL_PROTOCOL_VERSION, FORMAL_SCHEMA_VERSION, FORMAL_TOOL_VERSION, base_head, len(events), len(unobserved), protocol_sha, source_manifest_sha, input_manifest_sha, private_seed_sha, now, now),
            )
            for slot in FORMAL_SLOT_IDS:
                order_hash = sha256_bytes(_canonical_json([item["blind_alias"] for item in assignments_by_slot[slot]]).encode("utf-8"))
                store.connection.execute(
                    "INSERT INTO formal_review_slots (round_id, slot_id, status, order_manifest_sha256, private_seed_sha256, created_at, updated_at) VALUES (?, ?, 'unbound', ?, ?, ?, ?)",
                    (FORMAL_ROUND_ID, slot, order_hash, private_seed_sha, now, now),
                )
                for item in assignments_by_slot[slot]:
                    store.connection.execute(
                        """
                        INSERT INTO formal_assignments
                          (assignment_id, round_id, slot_id, event_id, blind_alias, randomized_order,
                           visual_reference_key, visual_input_sha256, visual_input_manifest_sha256, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (item["assignment_id"], FORMAL_ROUND_ID, slot, item["event_id"], item["blind_alias"], item["randomized_order"], item["visual_reference_key"], item["quicklook_sha256"], input_manifest_sha, now),
                    )
            for item in unobserved:
                store.connection.execute(
                    "INSERT INTO formal_unobserved_events (event_id, observability_status, exclusion_reason, protocol_version, source_manifest_sha256, recorded_at) VALUES (?, 'unobserved', ?, ?, ?, ?)",
                    (item["event_id"], item["exclusion_reason"], FORMAL_PROTOCOL_VERSION, source_manifest_sha, now),
                )
            manifests = (
                ("formal_review_28_event_queue", "event_queue", str(Path(queue_path)), queue_sha, len(events), {"sha256": queue_sha, "count": len(events)}),
                ("formal_review_28_unobserved", "unobserved_registry", str(Path(unobserved_path)), unobserved_sha, len(unobserved), {"sha256": unobserved_sha, "count": len(unobserved)}),
                ("formal_review_28_visual_inputs", "visual_input", "existing quicklook paths", input_manifest_sha, len(events), visual_manifest),
                ("formal_review_28_protocol", "protocol", str(protocol), protocol_sha, 1, {"sha256": protocol_sha}),
            )
            for manifest_id, kind, path, file_sha, count, payload in manifests:
                store.connection.execute(
                    "INSERT INTO formal_input_manifests (manifest_id, manifest_kind, source_path, sha256, item_count, manifest_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (manifest_id, kind, path, file_sha, count, _canonical_json(payload), now),
                )
            for slot in FORMAL_SLOT_IDS:
                package_path, package_sha, _ = public_manifests[slot]
                try:
                    stored_package_path = str(package_path.relative_to(root_path))
                except ValueError:
                    stored_package_path = str(package_path)
                store.connection.execute(
                    "INSERT INTO formal_package_manifests (round_id, slot_id, package_id, package_path, manifest_sha256, input_manifest_sha256, private_manifest_sha256, item_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (FORMAL_ROUND_ID, slot, f"{FORMAL_ROUND_ID}_{slot.lower()}", stored_package_path, package_sha, input_manifest_sha, private_sha, len(events), now),
                )
            store.connection.execute(
                "INSERT INTO formal_audit_log (round_id, action, object_type, object_id, new_payload_sha256, reason, created_at) VALUES (?, 'prepare_round', 'formal_review_round', ?, ?, 'empty round; no reviews executed', ?)",
                (FORMAL_ROUND_ID, summary_path.name, sha256_file(summary_path), now),
            )
            store.connection.commit()
    return PreparationResult(
        round_id=FORMAL_ROUND_ID,
        database_path=database_path,
        output_dir=output_path,
        observable_count=len(events),
        unobserved_count=len(unobserved),
        assignment_count=len(events) * len(FORMAL_SLOT_IDS),
        protocol_sha256=protocol_sha,
        input_manifest_sha256=input_manifest_sha,
        private_seed_sha256=private_seed_sha,
        package_paths=tuple(package_paths),
        package_hashes=tuple(package_hashes),
    )


def prepared_round_summary(db_path: Path | str) -> dict[str, Any]:
    with FormalReviewStore(db_path) as store:
        store.initialize()
        round_row = store.connection.execute("SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()
        if round_row is None:
            raise FormalReviewError("No existe la ronda formal preparada")
        result = dict(round_row)
        result["assignment_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_assignments WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        result["pass_a_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_pass_a WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        result["pass_b_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_pass_b WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        result["package_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_package_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        return result


def _legacy_export_formal_preparation(
    *,
    db_path: Path | str,
    output_dir: Path | str,
) -> dict[str, Path]:
    """Export only empty preparation/admin projections; never review rows."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with FormalReviewStore(db_path) as store:
        store.initialize()
        summary = prepared_round_summary(db_path)
        assignments = store.connection.execute(
            """
            SELECT round_id, slot_id, blind_alias, randomized_order,
                   visual_reference_key, visual_input_sha256,
                   visual_input_manifest_sha256, status
            FROM formal_assignments
            WHERE round_id = ?
            ORDER BY slot_id, randomized_order
            """,
            (FORMAL_ROUND_ID,),
        ).fetchall()
        audit = store.connection.execute(
            """
            SELECT audit_id, round_id, slot_id, action, object_type, object_id,
                   new_payload_sha256, reason, created_at
            FROM formal_audit_log
            WHERE round_id = ?
            ORDER BY audit_id
            """,
            (FORMAL_ROUND_ID,),
        ).fetchall()
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=(
            "round_id",
            "slot_id",
            "blind_alias",
            "randomized_order",
            "visual_reference_key",
            "visual_input_sha256",
            "visual_input_manifest_sha256",
            "status",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in assignments:
        writer.writerow(dict(row))
    csv_path = destination / "formal_review_28_assignments.csv"
    _write_checked(csv_path, csv_buffer.getvalue().encode("utf-8"), allow_replace=False)
    json_path = destination / "formal_review_28_preparation.json"
    _write_checked(json_path, _json_bytes({"summary": summary, "assignment_count": len(assignments), "review_rows_exported": 0}), allow_replace=False)
    jsonl_path = destination / "formal_review_28_audit.jsonl"
    audit_payload = "".join(_canonical_json(dict(row)) + "\n" for row in audit)
    _write_checked(jsonl_path, audit_payload.encode("utf-8"), allow_replace=False)
    return {"csv": csv_path, "json": json_path, "jsonl": jsonl_path}


# ---------------------------------------------------------------------------
# Hardened administrative implementation.
#
# The first implementation above is retained as historical code context for
# the original preparation checkpoint.  The public functions are redefined
# below so every current caller uses the checked, cumulative implementation.
# ---------------------------------------------------------------------------


def _hardened_private_map(assignments_by_slot: Mapping[str, Sequence[Mapping[str, Any]]], private_seed_sha: str) -> dict[str, Any]:
    return {
        "round_id": FORMAL_ROUND_ID,
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "private_seed_sha256": private_seed_sha,
        "items": {
            slot: [
                {
                    "assignment_id": item["assignment_id"],
                    "blind_alias": item["blind_alias"],
                    "randomized_order": item["randomized_order"],
                    "event_id": item["event_id"],
                    "quicklook_path": item["quicklook_path"],
                    "quicklook_sha256": item["quicklook_sha256"],
                }
                for item in assignments
            ]
            for slot, assignments in assignments_by_slot.items()
        },
    }


def _hardened_summary(
    *,
    base_head: str,
    events: Sequence[Mapping[str, Any]],
    unobserved: Sequence[Mapping[str, Any]],
    protocol_sha: str,
    source_manifest_sha: str,
    input_manifest_sha: str,
    private_seed_sha: str,
    package_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "round_id": FORMAL_ROUND_ID,
        "status": "prepared",
        "execution_status": "not_started",
        "execution_authorized": False,
        "protocol_version": FORMAL_PROTOCOL_VERSION,
        "schema_version": FORMAL_SCHEMA_VERSION,
        "tool_version": FORMAL_TOOL_VERSION,
        "migration_version": CURRENT_MIGRATION_VERSION,
        "base_head": base_head,
        "observable_count": len(events),
        "unobserved_count": len(unobserved),
        "assignment_count": len(events) * len(FORMAL_SLOT_IDS),
        "protocol_sha256": protocol_sha,
        "source_manifest_sha256": source_manifest_sha,
        "input_manifest_sha256": input_manifest_sha,
        "private_seed_sha256": private_seed_sha,
        "package_hashes": dict(package_hashes),
        "formal_review_executed": False,
        "pass_a_authorized": False,
        "pass_b_blocked": True,
        "window_median_count": 0,
    }


def _hardened_artifacts(
    *,
    output_path: Path,
    assignments_by_slot: Mapping[str, Sequence[Mapping[str, Any]]],
    protocol_sha: str,
    source_manifest_sha: str,
    input_manifest_sha: str,
    private_seed_sha: str,
    base_head: str,
    events: Sequence[Mapping[str, Any]],
    unobserved: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, tuple[Path, bytes, str]], dict[str, str], dict[str, Any]]:
    artifacts: dict[str, tuple[Path, bytes, str]] = {}
    private_payload = _hardened_private_map(assignments_by_slot, private_seed_sha)
    artifacts["private_combined"] = (
        output_path / "private" / "assignment_map.json",
        _json_bytes(private_payload),
        "private_combined",
    )
    package_hashes: dict[str, str] = {}
    for slot, assignments in assignments_by_slot.items():
        slot_payload = {
            "round_id": FORMAL_ROUND_ID,
            "protocol_version": FORMAL_PROTOCOL_VERSION,
            "slot_id": slot,
            "private_seed_sha256": private_seed_sha,
            "items": {slot: private_payload["items"][slot]},
        }
        artifacts[f"{slot}_private"] = (
            output_path / "private" / slot.lower() / "assignment_map.json",
            _json_bytes(slot_payload),
            "private_slot",
        )
        manifest = _public_manifest(
            slot_id=slot,
            assignments=assignments,
            protocol_sha256=protocol_sha,
            input_manifest_sha256=input_manifest_sha,
            private_seed_sha256=private_seed_sha,
        )
        manifest_bytes = _json_bytes(manifest)
        package_hashes[slot] = sha256_bytes(manifest_bytes)
        artifacts[f"{slot}_public"] = (
            output_path / slot.lower() / "manifest.json",
            manifest_bytes,
            "public_manifest",
        )
    summary = _hardened_summary(
        base_head=base_head,
        events=events,
        unobserved=unobserved,
        protocol_sha=protocol_sha,
        source_manifest_sha=source_manifest_sha,
        input_manifest_sha=input_manifest_sha,
        private_seed_sha=private_seed_sha,
        package_hashes=package_hashes,
    )
    artifacts["preparation_summary"] = (
        output_path / "preparation_summary.json",
        _json_bytes(summary),
        "preparation_summary",
    )
    return artifacts, package_hashes, summary


def _hardened_write_artifacts(
    artifacts: Mapping[str, tuple[Path, bytes, str]],
    *,
    allow_replace: bool,
    require_existing: bool = False,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for artifact_id, (path, payload, _kind) in artifacts.items():
        if require_existing and not path.is_file():
            raise FormalReviewError(f"Falta artefacto administrativo esperado: {path}")
        result[artifact_id] = _write_checked(path, payload, allow_replace=allow_replace)
    return result


def _hardened_assignment_tuple(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row[field] for field in (
        "assignment_id", "round_id", "slot_id", "event_id", "blind_alias",
        "randomized_order", "visual_reference_key", "visual_input_sha256",
        "visual_input_manifest_sha256",
    ))


def _hardened_expected_assignment(item: Mapping[str, Any], slot: str, input_manifest_sha: str) -> tuple[Any, ...]:
    return (
        item["assignment_id"], FORMAL_ROUND_ID, slot, item["event_id"], item["blind_alias"],
        item["randomized_order"], item["visual_reference_key"], item["quicklook_sha256"],
        input_manifest_sha,
    )


def _hardened_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = {
        "pass_a": "formal_pass_a",
        "pass_b": "formal_pass_b",
        "pairwise": "formal_pairwise_comparisons",
        "triage": "formal_triage",
        "adjudication": "formal_adjudications",
        "expert": "formal_expert_reviews",
        "amendments": "formal_amendments",
    }
    return {
        key: int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0])
        for key, table in tables.items()
    }


def _hardened_register_artifact(
    connection: sqlite3.Connection,
    *,
    root: Path,
    artifact_id: str,
    artifact_kind: str,
    path: Path,
    digest: str,
    now: str,
) -> None:
    existing = connection.execute(
        "SELECT sha256 FROM formal_artifact_manifests WHERE round_id = ? AND artifact_id = ?",
        (FORMAL_ROUND_ID, artifact_id),
    ).fetchone()
    if existing is not None and existing[0] != sha256_file(path):
        raise FormalReviewError(f"El manifest del artefacto {artifact_id} no coincide con los bytes actuales")
    try:
        relative = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        relative = str(path.resolve())
    connection.execute(
        """
        INSERT INTO formal_artifact_manifests
          (round_id, artifact_id, artifact_kind, artifact_path, sha256, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(round_id, artifact_id) DO UPDATE SET
          artifact_kind = excluded.artifact_kind,
          artifact_path = excluded.artifact_path,
          sha256 = excluded.sha256,
          updated_at = excluded.updated_at
        """,
        (FORMAL_ROUND_ID, artifact_id, artifact_kind, relative, digest, now, now),
    )


def _hardened_export_safety(export_dir: Path, connection: sqlite3.Connection | None = None) -> None:
    csv_path = export_dir / "formal_review_28_assignments.csv"
    if csv_path.exists():
        text = csv_path.read_text(encoding="utf-8")
        if "event_id" in text.lower() or text.count("\n") != 57:
            raise FormalReviewError("El export administrativo existente no coincide con 56 asignaciones sin join")
        if connection is not None:
            expected_buffer = io.StringIO(newline="")
            writer = csv.DictWriter(
                expected_buffer,
                fieldnames=("round_id", "slot_id", "blind_alias", "randomized_order", "visual_reference_key", "visual_input_sha256", "visual_input_manifest_sha256", "status"),
                lineterminator="\n",
            )
            writer.writeheader()
            for row in connection.execute(
                "SELECT round_id, slot_id, blind_alias, randomized_order, visual_reference_key, visual_input_sha256, visual_input_manifest_sha256, status FROM formal_assignments WHERE round_id = ? ORDER BY slot_id, randomized_order",
                (FORMAL_ROUND_ID,),
            ).fetchall():
                writer.writerow(dict(row))
            if csv_path.read_bytes() != expected_buffer.getvalue().encode("utf-8"):
                raise FormalReviewError("El export CSV existente difiere de la proyección registrada")
    json_path = export_dir / "formal_review_28_preparation.json"
    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if payload.get("review_rows_exported") != 0 or payload.get("assignment_count") != 56:
            raise FormalReviewError("El export administrativo existente no está vacío")
    jsonl_path = export_dir / "formal_review_28_audit.jsonl"
    if jsonl_path.exists():
        existing_jsonl = jsonl_path.read_text(encoding="utf-8")
        if connection is not None:
            expected_jsonl = "".join(
                _canonical_json(dict(row)) + "\n"
                for row in connection.execute(
                    "SELECT audit_id, round_id, slot_id, action, object_type, object_id, new_payload_sha256, reason, created_at FROM formal_audit_log WHERE round_id = ? ORDER BY audit_id",
                    (FORMAL_ROUND_ID,),
                ).fetchall()
            )
            if existing_jsonl != expected_jsonl:
                raise FormalReviewError("El audit export existente difiere de la auditoría registrada")


def _hardened_result(
    *,
    database_path: Path,
    output_path: Path,
    events: Sequence[Mapping[str, Any]],
    unobserved: Sequence[Mapping[str, Any]],
    protocol_sha: str,
    input_manifest_sha: str,
    private_seed_sha: str,
    package_hashes: Mapping[str, str],
) -> PreparationResult:
    return PreparationResult(
        round_id=FORMAL_ROUND_ID,
        database_path=database_path,
        output_dir=output_path,
        observable_count=len(events),
        unobserved_count=len(unobserved),
        assignment_count=len(events) * len(FORMAL_SLOT_IDS),
        protocol_sha256=protocol_sha,
        input_manifest_sha256=input_manifest_sha,
        private_seed_sha256=private_seed_sha,
        package_paths=tuple(output_path / slot.lower() / "manifest.json" for slot in FORMAL_SLOT_IDS),
        package_hashes=tuple(package_hashes[slot] for slot in FORMAL_SLOT_IDS),
    )


def _hardened_prepare_inputs(
    *,
    root_path: Path,
    queue_path: Path,
    unobserved_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, str, str, dict[str, Any]]:
    events, unobserved = load_formal_inputs(root=root_path, queue_path=queue_path, unobserved_path=unobserved_path)
    queue_sha = sha256_file(queue_path)
    unobserved_sha = sha256_file(unobserved_path)
    source_manifest = {
        "round_id": FORMAL_ROUND_ID,
        "queue_sha256": queue_sha,
        "unobserved_sha256": unobserved_sha,
        "observable_count": len(events),
        "unobserved_count": len(unobserved),
    }
    source_manifest_sha = sha256_bytes(_canonical_json(source_manifest).encode("utf-8"))
    visual_manifest = {
        "events": [
            {"event_id": item["event_id"], "visual_input_sha256": item["quicklook_sha256"], "visual_reference": item["quicklook_path"]}
            for item in events
        ]
    }
    input_manifest_sha = sha256_bytes(_canonical_json({"source": source_manifest_sha, "visual": visual_manifest}).encode("utf-8"))
    return events, unobserved, queue_sha, unobserved_sha, source_manifest_sha, input_manifest_sha, visual_manifest


def _hardened_old_manifest_assignments(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "blind_alias": row["blind_alias"],
            "randomized_order": row["randomized_order"],
            "visual_reference_key": row["visual_reference_key"],
            "quicklook_sha256": row["visual_input_sha256"],
        }
        for row in rows
    ]


def _hardened_reconcile(
    *,
    root_path: Path,
    database_path: Path,
    output_path: Path,
    existing_round: sqlite3.Row,
    events: Sequence[Mapping[str, Any]],
    unobserved: Sequence[Mapping[str, Any]],
    queue_path: Path,
    unobserved_path: Path,
    queue_sha: str,
    unobserved_sha: str,
    source_manifest_sha: str,
    input_manifest_sha: str,
    visual_manifest: Mapping[str, Any],
    private_seed_sha: str,
    assignments_by_slot: Mapping[str, Sequence[Mapping[str, Any]]],
    current_protocol_sha: str,
    protocol_path: Path,
    base_head: str,
) -> PreparationResult:
    old_protocol_sha = str(existing_round["protocol_sha256"])
    if old_protocol_sha != STALE_PROTOCOL_SHA256:
        raise FormalReviewError("Solo se puede reconciliar el hash protocolario obsoleto conocido")
    with FormalReviewStore(database_path) as store:
        store.initialize()
        if any(_hardened_counts(store.connection).values()):
            raise FormalReviewError("La reconciliación exige cero resultados formales")
        packages = {
            row["slot_id"]: dict(row)
            for row in store.connection.execute("SELECT * FROM formal_package_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall()
        }
        if set(packages) != set(FORMAL_SLOT_IDS):
            raise FormalReviewError("Los dos manifests públicos son obligatorios para reconciliar")
        private_payload = _hardened_private_map(assignments_by_slot, private_seed_sha)
        private_path = output_path / "private" / "assignment_map.json"
        if not private_path.is_file() or private_path.read_bytes() != _json_bytes(private_payload):
            raise FormalReviewError("El mapa privado existente difiere de la asignación congelada")
        for slot in FORMAL_SLOT_IDS:
            rows = store.connection.execute(
                "SELECT * FROM formal_assignments WHERE round_id = ? AND slot_id = ? ORDER BY randomized_order",
                (FORMAL_ROUND_ID, slot),
            ).fetchall()
            old_manifest = _public_manifest(
                slot_id=slot,
                assignments=_hardened_old_manifest_assignments(rows),
                protocol_sha256=old_protocol_sha,
                input_manifest_sha256=input_manifest_sha,
                private_seed_sha256=private_seed_sha,
            )
            path = output_path / slot.lower() / "manifest.json"
            if not path.is_file() or path.read_bytes() != _json_bytes(old_manifest):
                raise FormalReviewError("El manifest público existente difiere de su identidad registrada")
            if packages[slot]["manifest_sha256"] != sha256_file(path):
                raise FormalReviewError("El hash DB del manifest público no coincide")
        summary_path = output_path / "preparation_summary.json"
        summary_hash_mismatch = False
        summary_actual_sha = ""
        audit_row = store.connection.execute(
            "SELECT new_payload_sha256 FROM formal_audit_log WHERE round_id = ? AND action = 'prepare_round' ORDER BY audit_id LIMIT 1",
            (FORMAL_ROUND_ID,),
        ).fetchone()
        if audit_row is not None:
            if not summary_path.is_file():
                raise FormalReviewError("Falta el resumen previo administrativo")
            if sha256_file(summary_path) != audit_row[0]:
                summary_hash_mismatch = True
                summary_actual_sha = sha256_file(summary_path)
                # This is an explicit, authorized protocol reconciliation.  A
                # stale summary may have been regenerated by the prior
                # preparation tooling, but its logical identity must still be
                # exact before the controlled replacement is allowed.
                try:
                    old_summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise FormalReviewError("El resumen previo no se puede auditar") from exc
                expected_old_packages = {slot: packages[slot]["manifest_sha256"] for slot in FORMAL_SLOT_IDS}
                if any(old_summary.get(key) != value for key, value in {
                    "round_id": FORMAL_ROUND_ID,
                    "status": "prepared",
                    "protocol_version": FORMAL_PROTOCOL_VERSION,
                    "protocol_sha256": old_protocol_sha,
                    "input_manifest_sha256": input_manifest_sha,
                    "private_seed_sha256": private_seed_sha,
                    "package_hashes": expected_old_packages,
                    "observable_count": len(events),
                    "unobserved_count": len(unobserved),
                    "assignment_count": len(events) * len(FORMAL_SLOT_IDS),
                    "formal_review_executed": False,
                }.items()):
                    raise FormalReviewError("El resumen previo tiene identidad incompatible; no se sobrescribe")
        _hardened_export_safety(output_path / "exports", store.connection)

        artifacts, package_hashes, _summary = _hardened_artifacts(
            output_path=output_path,
            assignments_by_slot=assignments_by_slot,
            protocol_sha=current_protocol_sha,
            source_manifest_sha=source_manifest_sha,
            input_manifest_sha=input_manifest_sha,
            private_seed_sha=private_seed_sha,
            base_head=base_head,
            events=events,
            unobserved=unobserved,
        )
        _write_checked(private_path, artifacts["private_combined"][1], allow_replace=False)
        replacement = {key: value for key, value in artifacts.items() if key != "private_combined"}
        _hardened_write_artifacts(replacement, allow_replace=True)
        now = store._now()
        old_package_hashes = {slot: packages[slot]["manifest_sha256"] for slot in FORMAL_SLOT_IDS}
        if summary_hash_mismatch:
            old_package_hashes["preparation_summary_actual_sha256"] = summary_actual_sha
        new_package_hashes = {slot: package_hashes[slot] for slot in FORMAL_SLOT_IDS}
        store.connection.execute(
            """
            INSERT INTO formal_protocol_reconciliations
              (round_id, old_protocol_sha256, new_protocol_sha256, reason_code, timestamp_utc,
               tool_version, base_commit, old_package_hashes_json, new_package_hashes_json,
               seed_preserved, aliases_preserved, orders_preserved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?)
            """,
            (
                FORMAL_ROUND_ID, old_protocol_sha, current_protocol_sha,
                PROTOCOL_HASH_RECONCILIATION_REASON, now, FORMAL_TOOL_VERSION,
                base_head, _canonical_json(old_package_hashes), _canonical_json(new_package_hashes), now,
            ),
        )
        store.connection.execute(
            "UPDATE formal_review_rounds SET protocol_sha256 = ?, updated_at = ? WHERE round_id = ?",
            (current_protocol_sha, now, FORMAL_ROUND_ID),
        )
        store.connection.execute(
            "UPDATE formal_input_manifests SET sha256 = ?, manifest_json = ? WHERE manifest_id = 'formal_review_28_protocol'",
            (current_protocol_sha, _canonical_json({"sha256": current_protocol_sha})),
        )
        for slot in FORMAL_SLOT_IDS:
            store.connection.execute(
                "UPDATE formal_package_manifests SET manifest_sha256 = ? WHERE round_id = ? AND slot_id = ?",
                (package_hashes[slot], FORMAL_ROUND_ID, slot),
            )
        store.connection.execute(
            """
            INSERT INTO formal_audit_log
              (round_id, action, object_type, object_id, previous_payload_sha256,
               new_payload_sha256, reason, created_at)
            VALUES (?, 'reconcile_protocol_hash', 'formal_review_round', ?, ?, ?, ?, ?)
            """,
            (
                FORMAL_ROUND_ID, protocol_path.name, old_protocol_sha, current_protocol_sha,
                PROTOCOL_HASH_RECONCILIATION_REASON, now,
            ),
        )
        for artifact_id, (path, _payload, kind) in artifacts.items():
            _hardened_register_artifact(
                store.connection, root=root_path, artifact_id=artifact_id, artifact_kind=kind,
                path=path, digest=sha256_file(path), now=now,
            )
        store.connection.commit()
    export_formal_preparation(
        db_path=database_path,
        output_dir=output_path / "exports",
        allow_replace=True,
        reconciliation_authorized=True,
        root=root_path,
    )
    return _hardened_result(
        database_path=database_path,
        output_path=output_path,
        events=events,
        unobserved=unobserved,
        protocol_sha=current_protocol_sha,
        input_manifest_sha=input_manifest_sha,
        private_seed_sha=private_seed_sha,
        package_hashes=package_hashes,
    )


def prepare_formal_round(
    *,
    root: Path | str = ROOT,
    db_path: Path | str = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3",
    queue_path: Path | str = FORMAL_QUEUE_PATH,
    unobserved_path: Path | str = FORMAL_UNOBSERVED_PATH,
    protocol_path: Path | str = FORMAL_PROTOCOL_PATH,
    output_dir: Path | str = FORMAL_OUTPUT_DIR,
    seed_path: Path | str | None = None,
    supplied_seed: str | None = None,
    base_head: str = "f302139",
    reconcile_protocol_hash: bool = False,
) -> PreparationResult:
    """Prepare the empty round or perform one explicitly authorized hash reconciliation."""

    root_path = Path(root).resolve()
    database_path = Path(db_path)
    output_path = Path(output_dir)
    protocol = Path(protocol_path)
    if not protocol.is_file():
        raise FormalReviewError(f"No existe el protocolo congelado: {protocol}")
    current_protocol_sha = sha256_file(protocol)
    queue_path = Path(queue_path)
    unobserved_path = Path(unobserved_path)
    events, unobserved, queue_sha, unobserved_sha, source_manifest_sha, input_manifest_sha, visual_manifest = _hardened_prepare_inputs(
        root_path=root_path, queue_path=queue_path, unobserved_path=unobserved_path,
    )
    output_path.mkdir(parents=True, exist_ok=True)
    seed_file = Path(seed_path) if seed_path else output_path / "private_seed.txt"
    private_seed, private_seed_sha = resolve_private_seed(seed_file, supplied_seed)
    assignments_by_slot = {
        slot: build_slot_assignments(events, slot_id=slot, private_seed=private_seed)
        for slot in FORMAL_SLOT_IDS
    }
    with FormalReviewStore(database_path) as store:
        store.initialize()
        existing = store.connection.execute("SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()
        if existing is not None:
            identity_fields = {
                "protocol_version": FORMAL_PROTOCOL_VERSION,
                "schema_version": FORMAL_SCHEMA_VERSION,
                "tool_version": FORMAL_TOOL_VERSION,
                "status": "prepared",
                "base_head": base_head,
                "pilot_event_count": 30,
                "observable_event_count": len(events),
                "unobserved_event_count": len(unobserved),
                "source_manifest_sha256": source_manifest_sha,
                "input_manifest_sha256": input_manifest_sha,
                "private_seed_sha256": private_seed_sha,
            }
            if any(existing[key] != value for key, value in identity_fields.items()):
                raise FormalReviewError("La identidad administrativa existente no coincide; no se sobreescribe")
            if existing["status"] != "prepared" or existing["execution_status"] != "not_started" or bool(existing["execution_authorized"]):
                raise FormalReviewError("La ronda existente no está en prepared/not_started/unauthorized")
            if any(_hardened_counts(store.connection).values()):
                raise FormalReviewError("La ronda contiene resultados formales; no se puede reconciliar")
            for slot in FORMAL_SLOT_IDS:
                rows = store.connection.execute(
                    "SELECT * FROM formal_assignments WHERE round_id = ? AND slot_id = ? ORDER BY randomized_order",
                    (FORMAL_ROUND_ID, slot),
                ).fetchall()
                expected = assignments_by_slot[slot]
                if len(rows) != len(expected) or any(
                    _hardened_assignment_tuple(row) != _hardened_expected_assignment(item, slot, input_manifest_sha)
                    for row, item in zip(rows, expected)
                ):
                    raise FormalReviewError("Las asignaciones existentes no coinciden; no se reconstruyen")
            if existing["protocol_sha256"] != current_protocol_sha:
                if not reconcile_protocol_hash:
                    raise FormalReviewError("El hash protocolario difiere; use --reconcile-protocol-hash para reconciliarlo")
                return _hardened_reconcile(
                    root_path=root_path, database_path=database_path, output_path=output_path,
                    existing_round=existing, events=events, unobserved=unobserved,
                    queue_path=queue_path, unobserved_path=unobserved_path,
                    queue_sha=queue_sha, unobserved_sha=unobserved_sha,
                    source_manifest_sha=source_manifest_sha, input_manifest_sha=input_manifest_sha,
                    visual_manifest=visual_manifest, private_seed_sha=private_seed_sha,
                    assignments_by_slot=assignments_by_slot, current_protocol_sha=current_protocol_sha,
                    protocol_path=protocol, base_head=base_head,
                )
            artifacts, package_hashes, _summary = _hardened_artifacts(
                output_path=output_path, assignments_by_slot=assignments_by_slot,
                protocol_sha=current_protocol_sha, source_manifest_sha=source_manifest_sha,
                input_manifest_sha=input_manifest_sha, private_seed_sha=private_seed_sha,
                base_head=base_head, events=events, unobserved=unobserved,
            )
            _hardened_write_artifacts(artifacts, allow_replace=False, require_existing=True)
            return _hardened_result(
                database_path=database_path, output_path=output_path, events=events,
                unobserved=unobserved, protocol_sha=current_protocol_sha,
                input_manifest_sha=input_manifest_sha, private_seed_sha=private_seed_sha,
                package_hashes=package_hashes,
            )

        artifacts, package_hashes, _summary = _hardened_artifacts(
            output_path=output_path, assignments_by_slot=assignments_by_slot,
            protocol_sha=current_protocol_sha, source_manifest_sha=source_manifest_sha,
            input_manifest_sha=input_manifest_sha, private_seed_sha=private_seed_sha,
            base_head=base_head, events=events, unobserved=unobserved,
        )
        artifact_hashes = _hardened_write_artifacts(artifacts, allow_replace=False)
        now = store._now()
        store.connection.execute(
            """
            INSERT INTO formal_review_rounds
              (round_id, protocol_version, schema_version, tool_version, status, execution_status,
               execution_authorized, base_head, pilot_event_count, observable_event_count,
               unobserved_event_count, protocol_sha256, source_manifest_sha256,
               input_manifest_sha256, private_seed_sha256, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'prepared', 'not_started', 0, ?, 30, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                FORMAL_ROUND_ID, FORMAL_PROTOCOL_VERSION, FORMAL_SCHEMA_VERSION, FORMAL_TOOL_VERSION,
                base_head, len(events), len(unobserved), current_protocol_sha,
                source_manifest_sha, input_manifest_sha, private_seed_sha, now, now,
            ),
        )
        for slot in FORMAL_SLOT_IDS:
            order_hash = sha256_bytes(_canonical_json([item["blind_alias"] for item in assignments_by_slot[slot]]).encode("utf-8"))
            store.connection.execute(
                "INSERT INTO formal_review_slots (round_id, slot_id, status, order_manifest_sha256, private_seed_sha256, created_at, updated_at) VALUES (?, ?, 'unbound', ?, ?, ?, ?)",
                (FORMAL_ROUND_ID, slot, order_hash, private_seed_sha, now, now),
            )
            for item in assignments_by_slot[slot]:
                store.connection.execute(
                    """
                    INSERT INTO formal_assignments
                      (assignment_id, round_id, slot_id, event_id, blind_alias, randomized_order,
                       visual_reference_key, visual_input_reference, visual_input_sha256,
                       visual_input_manifest_sha256, temporal_input_reference, temporal_input_sha256,
                       temporal_input_manifest_sha256, temporal_input_mode, temporal_input_provenance,
                       created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["assignment_id"], FORMAL_ROUND_ID, slot, item["event_id"], item["blind_alias"],
                        item["randomized_order"], item["visual_reference_key"], item["visual_input_reference"],
                        item["quicklook_sha256"], input_manifest_sha,
                        item.get("temporal_input_reference"), item.get("temporal_input_sha256"),
                        item.get("temporal_input_manifest_sha256"), item.get("temporal_input_mode"),
                        item.get("temporal_input_provenance"), now,
                    ),
                )
        for item in unobserved:
            store.connection.execute(
                "INSERT INTO formal_unobserved_events (event_id, observability_status, exclusion_reason, protocol_version, source_manifest_sha256, recorded_at) VALUES (?, 'unobserved', ?, ?, ?, ?)",
                (item["event_id"], item["exclusion_reason"], FORMAL_PROTOCOL_VERSION, source_manifest_sha, now),
            )
        manifests = (
            ("formal_review_28_event_queue", "event_queue", str(queue_path), queue_sha, len(events), {"sha256": queue_sha, "count": len(events)}),
            ("formal_review_28_unobserved", "unobserved_registry", str(unobserved_path), unobserved_sha, len(unobserved), {"sha256": unobserved_sha, "count": len(unobserved)}),
            ("formal_review_28_visual_inputs", "visual_input", "existing quicklook paths", input_manifest_sha, len(events), visual_manifest),
            ("formal_review_28_protocol", "protocol", str(protocol), current_protocol_sha, 1, {"sha256": current_protocol_sha}),
        )
        for manifest_id, kind, path, file_sha, count, payload in manifests:
            store.connection.execute(
                "INSERT INTO formal_input_manifests (manifest_id, manifest_kind, source_path, sha256, item_count, manifest_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (manifest_id, kind, path, file_sha, count, _canonical_json(payload), now),
            )
        for slot in FORMAL_SLOT_IDS:
            package_path = output_path / slot.lower() / "manifest.json"
            try:
                stored_path = str(package_path.resolve().relative_to(root_path.resolve()))
            except ValueError:
                stored_path = str(package_path.resolve())
            store.connection.execute(
                "INSERT INTO formal_package_manifests (round_id, slot_id, package_id, package_path, manifest_sha256, input_manifest_sha256, private_manifest_sha256, item_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (FORMAL_ROUND_ID, slot, f"{FORMAL_ROUND_ID}_{slot.lower()}", stored_path, package_hashes[slot], input_manifest_sha, artifact_hashes["private_combined"], len(events), now),
            )
        store.connection.execute(
            "INSERT INTO formal_audit_log (round_id, action, object_type, object_id, new_payload_sha256, reason, created_at) VALUES (?, 'prepare_round', 'formal_review_round', ?, ?, 'empty round; no reviews executed', ?)",
            (FORMAL_ROUND_ID, "preparation_summary.json", artifact_hashes["preparation_summary"], now),
        )
        for artifact_id, (path, _payload, kind) in artifacts.items():
            _hardened_register_artifact(
                store.connection, root=root_path, artifact_id=artifact_id, artifact_kind=kind,
                path=path, digest=artifact_hashes[artifact_id], now=now,
            )
        store.connection.commit()
    return _hardened_result(
        database_path=database_path, output_path=output_path, events=events,
        unobserved=unobserved, protocol_sha=current_protocol_sha,
        input_manifest_sha=input_manifest_sha, private_seed_sha=private_seed_sha,
        package_hashes=package_hashes,
    )


def _hardened_export_payloads(db_path: Path | str) -> dict[str, bytes]:
    with FormalReviewStore(db_path) as store:
        store.initialize()
        round_row = store.connection.execute("SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()
        if round_row is None:
            raise FormalReviewError("No existe la ronda formal preparada")
        summary = dict(round_row)
        summary["assignment_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_assignments WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        summary["pass_a_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_pass_a WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        summary["pass_b_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_pass_b WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        summary["package_count"] = store.connection.execute("SELECT COUNT(*) FROM formal_package_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0]
        assignments = store.connection.execute(
            "SELECT round_id, slot_id, blind_alias, randomized_order, visual_reference_key, visual_input_sha256, visual_input_manifest_sha256, status FROM formal_assignments WHERE round_id = ? ORDER BY slot_id, randomized_order",
            (FORMAL_ROUND_ID,),
        ).fetchall()
        audit = store.connection.execute(
            "SELECT audit_id, round_id, slot_id, action, object_type, object_id, previous_payload_sha256, new_payload_sha256, reason, created_at FROM formal_audit_log WHERE round_id = ? ORDER BY audit_id",
            (FORMAL_ROUND_ID,),
        ).fetchall()
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=("round_id", "slot_id", "blind_alias", "randomized_order", "visual_reference_key", "visual_input_sha256", "visual_input_manifest_sha256", "status"),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in assignments:
        writer.writerow(dict(row))
    return {
        "csv": csv_buffer.getvalue().encode("utf-8"),
        "json": _json_bytes({"summary": summary, "assignment_count": len(assignments), "review_rows_exported": 0}),
        "jsonl": "".join(_canonical_json(dict(row)) + "\n" for row in audit).encode("utf-8"),
    }


def export_formal_preparation(
    *,
    db_path: Path | str,
    output_dir: Path | str,
    allow_replace: bool = False,
    reconciliation_authorized: bool = False,
    root: Path | str = ROOT,
) -> dict[str, Path]:
    """Export empty administrative projections with explicit byte checks."""

    if allow_replace and not reconciliation_authorized:
        raise FormalReviewError("Reemplazar un export requiere reconciliación autorizada")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    payloads = _hardened_export_payloads(db_path)
    paths = {
        "csv": destination / "formal_review_28_assignments.csv",
        "json": destination / "formal_review_28_preparation.json",
        "jsonl": destination / "formal_review_28_audit.jsonl",
    }
    hashes = {key: _write_checked(path, payloads[key], allow_replace=allow_replace) for key, path in paths.items()}
    with FormalReviewStore(db_path) as store:
        store.initialize()
        now = store._now()
        kinds = {"csv": "export_csv", "json": "export_json", "jsonl": "export_jsonl"}
        for key, path in paths.items():
            _hardened_register_artifact(
                store.connection, root=Path(root).resolve(), artifact_id=f"export_{key}",
                artifact_kind=kinds[key], path=path, digest=hashes[key], now=now,
            )
        store.connection.commit()
    return paths


def _hardened_read_only_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FormalReviewError("No existe la base formal para verificar")
    connection = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def verify_formal_review_round(
    *,
    root: Path | str = ROOT,
    db_path: Path | str = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3",
    output_dir: Path | str = FORMAL_OUTPUT_DIR,
    protocol_path: Path | str = FORMAL_PROTOCOL_PATH,
) -> dict[str, Any]:
    """Verify the formal package read-only; this function never initializes SQLite."""

    root_path = Path(root).resolve()
    output_path = Path(output_dir)
    errors: list[str] = []
    protocol_sha = sha256_file(Path(protocol_path))
    try:
        events, unobserved = load_formal_inputs(root=root_path)
    except FormalReviewError as exc:
        return {"ok": False, "errors": [str(exc)]}
    connection = _hardened_read_only_connection(Path(db_path))
    try:
        round_row = connection.execute("SELECT * FROM formal_review_rounds WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()
        if round_row is None:
            return {"ok": False, "errors": ["missing formal round"]}
        if round_row["protocol_sha256"] != protocol_sha:
            errors.append("protocol hash mismatch")
        if (round_row["status"], round_row["execution_status"], int(round_row["execution_authorized"])) != ("prepared", "not_started", 0):
            errors.append("round state is not prepared/not_started/unauthorized")
        if (int(round_row["observable_event_count"]), int(round_row["unobserved_event_count"])) != (28, 2):
            errors.append("cohort counts mismatch")
        counts = _hardened_counts(connection)
        if any(counts.values()):
            errors.append("formal result rows are present")
        assignments = connection.execute("SELECT * FROM formal_assignments WHERE round_id = ? ORDER BY slot_id, randomized_order", (FORMAL_ROUND_ID,)).fetchall()
        if len(assignments) != 56 or len({row["assignment_id"] for row in assignments}) != 56:
            errors.append("assignment count or uniqueness mismatch")
        if len({row["event_id"] for row in assignments}) != 28:
            errors.append("event assignment coverage mismatch")
        packages = {row["slot_id"]: row for row in connection.execute("SELECT * FROM formal_package_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall()}
        if set(packages) != set(FORMAL_SLOT_IDS):
            errors.append("package manifest count mismatch")
        for slot in FORMAL_SLOT_IDS:
            path = output_path / slot.lower() / "manifest.json"
            try:
                text = path.read_text(encoding="utf-8")
                payload = json.loads(text)
                if sha256_file(path) != packages[slot]["manifest_sha256"] or payload.get("protocol_sha256") != protocol_sha or len(payload.get("items") or []) != 28:
                    errors.append("public package integrity mismatch")
                expected_public = [
                    (row["blind_alias"], row["randomized_order"], row["visual_reference_key"], row["visual_input_sha256"])
                    for row in assignments if row["slot_id"] == slot
                ]
                actual_public = [
                    (item.get("blind_alias"), item.get("randomized_order"), item.get("visual_reference_key"), item.get("visual_input_sha256"))
                    for item in payload.get("items", [])
                ]
                if actual_public != expected_public:
                    errors.append("public package aliases/order/visual hashes mismatch")
                if any(f'"{field}"' in text.lower() for field in FORMAL_FORBIDDEN_FIELDS):
                    errors.append("forbidden field in public package")
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
                errors.append("public package unreadable")
        private_path = output_path / "private" / "assignment_map.json"
        private_text = private_path.read_text(encoding="utf-8")
        private_payload = json.loads(private_text)
        if any(row["private_manifest_sha256"] != sha256_file(private_path) for row in packages.values()):
            errors.append("private map hash mismatch")
        for slot in FORMAL_SLOT_IDS:
            rows = [row for row in assignments if row["slot_id"] == slot]
            items = private_payload.get("items", {}).get(slot, [])
            expected_private = [
                (row["assignment_id"], row["event_id"], row["blind_alias"], row["randomized_order"], row["visual_input_sha256"])
                for row in rows
            ]
            actual_private = [
                (item.get("assignment_id"), item.get("event_id"), item.get("blind_alias"), item.get("randomized_order"), item.get("quicklook_sha256"))
                for item in items
            ]
            if len(items) != 28 or actual_private != expected_private:
                errors.append("private join mismatch")
            slot_private = output_path / "private" / slot.lower() / "assignment_map.json"
            try:
                slot_payload = json.loads(slot_private.read_text(encoding="utf-8"))
                if slot_payload.get("slot_id") != slot or len(slot_payload.get("items", {}).get(slot, [])) != 28:
                    errors.append("slot private map mismatch")
            except (OSError, UnicodeError, json.JSONDecodeError):
                errors.append("slot private map unreadable")
        seed_path = output_path / "private_seed.txt"
        if not seed_path.is_file() or sha256_bytes(seed_path.read_text(encoding="utf-8").strip().encode("utf-8")) != round_row["private_seed_sha256"]:
            errors.append("seed hash mismatch")
        protocol_manifest = connection.execute(
            "SELECT sha256 FROM formal_input_manifests WHERE manifest_id = 'formal_review_28_protocol'"
        ).fetchone()
        visual_manifest = connection.execute(
            "SELECT sha256 FROM formal_input_manifests WHERE manifest_id = 'formal_review_28_visual_inputs'"
        ).fetchone()
        if protocol_manifest is None or protocol_manifest[0] != protocol_sha or visual_manifest is None or visual_manifest[0] != round_row["input_manifest_sha256"]:
            errors.append("input manifest hashes mismatch")
        for row in connection.execute("SELECT * FROM formal_artifact_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall():
            raw_path = Path(row["artifact_path"])
            path = (raw_path if raw_path.is_absolute() else root_path / raw_path).resolve()
            try:
                try:
                    path.relative_to(root_path)
                except ValueError:
                    path.relative_to(output_path.resolve())
                if not path.is_file() or sha256_file(path) != row["sha256"]:
                    errors.append("administrative artifact hash mismatch")
            except (ValueError, OSError):
                errors.append("administrative artifact path mismatch")
        for row in connection.execute("SELECT * FROM formal_pass_a WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall():
            payload = _pass_a_payload(row)
            if row["payload_sha256"] != _payload_sha256(payload):
                errors.append("Pass A hash mismatch")
        for amendment in connection.execute("SELECT * FROM formal_amendments WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall():
            original = connection.execute(
                "SELECT payload_sha256 FROM formal_pass_a WHERE round_id = ? AND slot_id = ? AND event_id = ?",
                (amendment["round_id"], amendment["slot_id"], amendment["event_id"]),
            ).fetchone()
            if original is None:
                errors.append("orphan amendment")
            try:
                previous = json.loads(amendment["previous_payload_json"])
                corrected = json.loads(amendment["corrected_payload_json"])
                if amendment["previous_payload_sha256"] != _payload_sha256(previous) or amendment["corrected_payload_sha256"] != _payload_sha256(corrected):
                    errors.append("amendment hash mismatch")
            except (TypeError, json.JSONDecodeError):
                errors.append("invalid amendment payload")
        for row in connection.execute("SELECT * FROM formal_pass_b WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchall():
            required = (
                "selected_pair_reference", "selected_pair_sha256", "selected_pair_manifest_sha256",
                "selected_pair_mode", "selected_pair_provenance", "window_median_reference",
                "window_median_sha256", "window_median_manifest_sha256", "window_median_mode",
                "window_median_provenance",
            )
            if any(not row[field] for field in required) or row["selected_pair_mode"] != "selected_pair" or row["window_median_mode"] != "window_median":
                errors.append("Pass B reference contract mismatch")
            assignment = connection.execute("SELECT * FROM formal_assignments WHERE assignment_id = ?", (row["assignment_id"],)).fetchone()
            if assignment is None or row["selected_pair_reference"] != assignment["visual_input_reference"] or row["selected_pair_sha256"] != assignment["visual_input_sha256"] or row["selected_pair_manifest_sha256"] != assignment["visual_input_manifest_sha256"] or row["window_median_reference"] != assignment["temporal_input_reference"] or row["window_median_sha256"] != assignment["temporal_input_sha256"] or row["window_median_manifest_sha256"] != assignment["temporal_input_manifest_sha256"]:
                errors.append("Pass B assignment provenance mismatch")
            if row["selected_pair_reference"] == row["window_median_reference"] or row["selected_pair_sha256"] == row["window_median_sha256"]:
                errors.append("Pass B references are not distinct")
            for field, sha_field in (("selected_pair_reference", "selected_pair_sha256"), ("window_median_reference", "window_median_sha256")):
                reference = Path(row[field])
                if reference.is_absolute() or ".." in reference.parts:
                    errors.append("Pass B reference path is unsafe")
                    continue
                reference_path = (root_path / reference).resolve()
                try:
                    reference_path.relative_to(root_path)
                    if not reference_path.is_file() or sha256_file(reference_path) != row[sha_field]:
                        errors.append("Pass B reference file hash mismatch")
                except (ValueError, OSError):
                    errors.append("Pass B reference path is invalid")
        if connection.execute("SELECT COUNT(*) FROM reviewer_profiles").fetchone()[0] != 0:
            errors.append("reviewer profiles are not empty")
        bindings = connection.execute(
            "SELECT profile_id, COUNT(*) AS count FROM formal_review_slots WHERE round_id = ? AND profile_id IS NOT NULL GROUP BY profile_id HAVING COUNT(*) > 1",
            (FORMAL_ROUND_ID,),
        ).fetchall()
        if bindings:
            errors.append("profile is bound to both slots")
        schema_text = "\n".join(str(row[0]) for row in connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
        if any(term in schema_text.lower() for term in ("ground_truth", "significant_burn", "confirmed_fire")):
            errors.append("forbidden scientific schema field")
        reconciliation = connection.execute(
            "SELECT old_protocol_sha256, new_protocol_sha256, reason_code FROM formal_protocol_reconciliations WHERE round_id = ? ORDER BY reconciliation_id DESC LIMIT 1",
            (FORMAL_ROUND_ID,),
        ).fetchone()
        if reconciliation is not None and (
            reconciliation["new_protocol_sha256"] != protocol_sha
            or reconciliation["old_protocol_sha256"] == reconciliation["new_protocol_sha256"]
            or reconciliation["reason_code"] != PROTOCOL_HASH_RECONCILIATION_REASON
        ):
            errors.append("protocol reconciliation audit mismatch")
        return {
            "ok": not errors,
            "errors": errors,
            "observable_count": len(events),
            "unobserved_count": len(unobserved),
            "assignment_count": len(assignments),
            "protocol_sha256": protocol_sha,
            "execution_authorized": bool(round_row["execution_authorized"]),
            "formal_result_counts": counts,
            "artifact_count": connection.execute("SELECT COUNT(*) FROM formal_artifact_manifests WHERE round_id = ?", (FORMAL_ROUND_ID,)).fetchone()[0],
        }
    finally:
        connection.close()
