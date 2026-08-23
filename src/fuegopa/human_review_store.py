"""Auditable SQLite persistence for the local human-review calibration round."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Iterable, Mapping, Sequence

from .human_review_schema import (
    CALIBRATION_EVENT_IDS,
    CALIBRATION_ROUND,
    CALIBRATION_SEED_COLUMNS,
    DEFAULT_AUDIT_DIR,
    DEFAULT_CALIBRATION_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_UNOBSERVED_PATH,
    EVENT_ASSOCIATION_CODES,
    LEGACY_EXPORT_COLUMNS,
    MODE_AGREEMENT_CODES,
    NORMALIZED_EXPORT_COLUMNS,
    OBSERVABILITY_STATUS_CODES,
    PROTOCOL_VERSION,
    QUICKLOOK_VERSION,
    RANDOMIZATION_SEED,
    REVIEW_STATUS_CODES,
    SCAR_CONFIDENCE_CODES,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    UNOBSERVED_EVENT_IDS,
    VISIBLE_BURN_SCAR_CODES,
    COMPETING_LAND_CHANGE_CODES,
    deterministic_calibration_order,
    expected_panel_paths,
)
from .human_review_migrations import apply_migrations


ROOT = Path(__file__).resolve().parents[2]
_NOW = Callable[[], datetime]


class ReviewStoreError(ValueError):
    """Raised when a review operation would violate the review contract."""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text if text else None


def _dict_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def _safe_relative_path(root: Path, relative: str) -> Path | None:
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


class HumanReviewStore:
    """Small, explicit repository around the review SQLite database."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        *,
        now_fn: _NOW | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 3000")

    def __enter__(self) -> "HumanReviewStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        self.connection.executescript(SCHEMA_SQL)
        apply_migrations(self.connection, now=self._now())

    @classmethod
    def from_frozen_round(
        cls,
        db_path: Path | str = DEFAULT_DB_PATH,
        *,
        root: Path | str = ROOT,
        calibration_path: Path | str = DEFAULT_CALIBRATION_PATH,
        manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
        unobserved_path: Path | str = DEFAULT_UNOBSERVED_PATH,
        now_fn: _NOW | None = None,
    ) -> "HumanReviewStore":
        store = cls(db_path, now_fn=now_fn)
        store.initialize()
        store.seed_frozen_round(
            root=Path(root),
            calibration_path=Path(calibration_path),
            manifest_path=Path(manifest_path),
            unobserved_path=Path(unobserved_path),
        )
        return store

    def _now(self) -> str:
        return _as_timestamp(self._now_fn())

    @staticmethod
    def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                rows = [
                    {str(key): _text(value) for key, value in row.items() if key is not None}
                    for row in reader
                ]
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ReviewStoreError(f"No se pudo leer {path}: {exc}") from exc
        return fieldnames, rows

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewStoreError(f"No se pudo leer {path}: {exc}") from exc

    def _validate_seed(
        self,
        *,
        root: Path,
        calibration_path: Path,
        manifest_path: Path,
        unobserved_path: Path,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
        fields, rows = self._read_csv(calibration_path)
        if tuple(fields) != CALIBRATION_SEED_COLUMNS:
            raise ReviewStoreError("La cola de calibración no coincide con el esquema congelado")
        if len(rows) != len(CALIBRATION_EVENT_IDS):
            raise ReviewStoreError("La cola de calibración debe contener exactamente siete eventos")

        ordered = sorted(rows, key=lambda row: int(_text(row.get("randomized_order")) or "0"))
        expected_order = deterministic_calibration_order()
        for index, row in enumerate(ordered, start=1):
            event_id = _text(row.get("event_id"))
            if event_id != expected_order[index - 1]:
                raise ReviewStoreError("El orden de calibración no coincide con la semilla congelada")
            if _text(row.get("calibration_round")) != CALIBRATION_ROUND:
                raise ReviewStoreError("La ronda de calibración no coincide")
            if _text(row.get("protocol_version")) != PROTOCOL_VERSION:
                raise ReviewStoreError("La versión de protocolo no coincide")
            if _text(row.get("quicklook_version")) != QUICKLOOK_VERSION:
                raise ReviewStoreError("La versión de quicklook no coincide")
            expected_multispectral, expected_temporal = expected_panel_paths(event_id)
            if _text(row.get("multispectral_panel_path")) != expected_multispectral:
                raise ReviewStoreError(f"Ruta multiespectral inesperada para {event_id}")
            if _text(row.get("temporal_panel_path")) != expected_temporal:
                raise ReviewStoreError(f"Ruta temporal inesperada para {event_id}")
            for relative in (expected_multispectral, expected_temporal):
                resolved = _safe_relative_path(root, relative)
                if resolved is None or not resolved.is_file():
                    raise ReviewStoreError(f"No existe el panel congelado: {relative}")
            if _text(row.get("review_status")) != "pending":
                raise ReviewStoreError("La cola inicial debe permanecer pending")
            if any(_text(row.get(field)) for field in fields if field not in {
                "calibration_round",
                "randomized_order",
                "event_id",
                "protocol_version",
                "quicklook_version",
                "multispectral_panel_path",
                "temporal_panel_path",
                "review_status",
            }):
                raise ReviewStoreError("La cola inicial debe conservar sus campos de revisión vacíos")

        if {row["event_id"] for row in rows} != set(CALIBRATION_EVENT_IDS):
            raise ReviewStoreError("Los IDs de la cola de calibración no coinciden")

        manifest = self._read_json(manifest_path)
        if manifest.get("calibration_round") != CALIBRATION_ROUND:
            raise ReviewStoreError("El manifest no coincide con la ronda")
        if manifest.get("protocol_version") != PROTOCOL_VERSION:
            raise ReviewStoreError("El manifest no coincide con el protocolo")
        if manifest.get("quicklook_version") != QUICKLOOK_VERSION:
            raise ReviewStoreError("El manifest no coincide con el quicklook")
        randomization = manifest.get("randomization") or {}
        if randomization.get("seed") != RANDOMIZATION_SEED:
            raise ReviewStoreError("La semilla del manifest no coincide")
        manifest_events = sorted(manifest.get("events") or [], key=lambda item: int(item.get("randomized_order", 0)))
        expected_manifest_events = [
            {
                "event_id": row["event_id"],
                "multispectral_panel_path": row["multispectral_panel_path"],
                "randomized_order": int(row["randomized_order"]),
                "temporal_panel_path": row["temporal_panel_path"],
            }
            for row in ordered
        ]
        if manifest_events != expected_manifest_events:
            raise ReviewStoreError("Los eventos del manifest no coinciden con la cola")

        unobserved_fields, unobserved_rows = self._read_csv(unobserved_path)
        required_unobserved = {"event_id", "observability_status", "exclusion_reason", "protocol_version"}
        if len(unobserved_fields) != 5 or not required_unobserved.issubset(unobserved_fields):
            raise ReviewStoreError("La tabla de no observables no coincide con el esquema congelado")
        if len(unobserved_rows) != len(UNOBSERVED_EVENT_IDS):
            raise ReviewStoreError("La tabla de no observables debe contener exactamente dos eventos")
        for row in unobserved_rows:
            if _text(row.get("event_id")) not in UNOBSERVED_EVENT_IDS:
                raise ReviewStoreError("ID inesperado en la tabla de no observables")
            if _text(row.get("observability_status")) != "unobserved":
                raise ReviewStoreError("El estado de los no observables debe ser unobserved")
            if not _text(row.get("exclusion_reason")):
                raise ReviewStoreError("Los no observables requieren una razón")
            if _text(row.get("protocol_version")) != PROTOCOL_VERSION:
                raise ReviewStoreError("La versión de protocolo de los no observables no coincide")
        if {row["event_id"] for row in unobserved_rows} != set(UNOBSERVED_EVENT_IDS):
            raise ReviewStoreError("Los IDs de los no observables no coinciden")
        return rows, unobserved_rows, manifest

    def seed_frozen_round(
        self,
        *,
        root: Path = ROOT,
        calibration_path: Path = DEFAULT_CALIBRATION_PATH,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
        unobserved_path: Path = DEFAULT_UNOBSERVED_PATH,
    ) -> None:
        rows, unobserved_rows, manifest = self._validate_seed(
            root=root,
            calibration_path=calibration_path,
            manifest_path=manifest_path,
            unobserved_path=unobserved_path,
        )
        ordered = sorted(rows, key=lambda row: int(row["randomized_order"]))
        now = self._now()
        with self.connection:
            existing_round = self.connection.execute(
                "SELECT * FROM review_rounds WHERE round_id = ?",
                (CALIBRATION_ROUND,),
            ).fetchone()
            if existing_round is None:
                self.connection.execute(
                    """
                    INSERT INTO review_rounds
                        (round_id, protocol_version, quicklook_version, random_seed, created_at, status)
                    VALUES (?, ?, ?, ?, ?, 'open')
                    """,
                    (CALIBRATION_ROUND, PROTOCOL_VERSION, QUICKLOOK_VERSION, RANDOMIZATION_SEED, now),
                )
            elif (
                existing_round["protocol_version"] != PROTOCOL_VERSION
                or existing_round["quicklook_version"] != QUICKLOOK_VERSION
                or existing_round["random_seed"] != RANDOMIZATION_SEED
            ):
                raise ReviewStoreError("La ronda existente no coincide con el contrato congelado")

            for row in ordered:
                item_values = (
                    CALIBRATION_ROUND,
                    int(row["randomized_order"]),
                    row["event_id"],
                    row["multispectral_panel_path"],
                    row["temporal_panel_path"],
                    "observable",
                )
                existing_item = self.connection.execute(
                    "SELECT * FROM review_items WHERE round_id = ? AND event_id = ?",
                    (CALIBRATION_ROUND, row["event_id"]),
                ).fetchone()
                if existing_item is None:
                    self.connection.execute(
                        """
                        INSERT INTO review_items
                            (round_id, randomized_order, event_id, multispectral_panel_path,
                             temporal_panel_path, observability_status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        item_values,
                    )
                elif tuple(existing_item[field] for field in (
                    "round_id", "randomized_order", "event_id", "multispectral_panel_path",
                    "temporal_panel_path", "observability_status",
                )) != item_values:
                    raise ReviewStoreError(f"El item existente no coincide: {row['event_id']}")

            for row in unobserved_rows:
                values = (
                    row["event_id"],
                    "unobserved",
                    row["exclusion_reason"],
                    PROTOCOL_VERSION,
                )
                existing = self.connection.execute(
                    "SELECT event_id, observability_status, exclusion_reason, protocol_version "
                    "FROM unobserved_events WHERE event_id = ?",
                    (row["event_id"],),
                ).fetchone()
                if existing is None:
                    self.connection.execute(
                        """
                        INSERT INTO unobserved_events
                            (event_id, observability_status, exclusion_reason, protocol_version)
                        VALUES (?, ?, ?, ?)
                        """,
                        values,
                    )
                elif tuple(existing[field] for field in (
                    "event_id", "observability_status", "exclusion_reason", "protocol_version",
                )) != values:
                    raise ReviewStoreError(f"El no observable existente no coincide: {row['event_id']}")

            item_count = self.connection.execute(
                "SELECT COUNT(*) FROM review_items WHERE round_id = ?",
                (CALIBRATION_ROUND,),
            ).fetchone()[0]
            if item_count != len(CALIBRATION_EVENT_IDS):
                raise ReviewStoreError("La ronda debe conservar exactamente siete items")
            unobserved_count = self.connection.execute("SELECT COUNT(*) FROM unobserved_events").fetchone()[0]
            if unobserved_count != len(UNOBSERVED_EVENT_IDS):
                raise ReviewStoreError("La tabla separada debe conservar exactamente dos no observables")

    def list_items(self, round_id: str = CALIBRATION_ROUND) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM review_items WHERE round_id = ? ORDER BY randomized_order",
            (round_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_item(self, round_id: str, event_id: str) -> dict[str, Any] | None:
        return _dict_row(self.connection.execute(
            "SELECT * FROM review_items WHERE round_id = ? AND event_id = ?",
            (round_id, event_id),
        ).fetchone())

    def get_item_by_order(self, round_id: str, randomized_order: int) -> dict[str, Any] | None:
        return _dict_row(self.connection.execute(
            "SELECT * FROM review_items WHERE round_id = ? AND randomized_order = ?",
            (round_id, randomized_order),
        ).fetchone())

    def get_review(self, round_id: str, event_id: str, reviewer_id: str) -> dict[str, Any] | None:
        reviewer = _text(reviewer_id)
        if not reviewer:
            return None
        return _dict_row(self.connection.execute(
            "SELECT * FROM reviews WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
            (round_id, event_id, reviewer),
        ).fetchone())

    def list_unobserved(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM unobserved_events ORDER BY event_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def round_summary(self, round_id: str = CALIBRATION_ROUND, reviewer_id: str | None = None) -> dict[str, Any]:
        if reviewer_id is None:
            counts = self.connection.execute(
                """
                SELECT COALESCE(r.review_status, 'pending') AS review_status, COUNT(*) AS count
                FROM review_items i
                LEFT JOIN reviews r
                  ON r.round_id = i.round_id AND r.event_id = i.event_id
                WHERE i.round_id = ?
                GROUP BY COALESCE(r.review_status, 'pending')
                """,
                (round_id,),
            ).fetchall()
        else:
            counts = self.connection.execute(
                """
                SELECT COALESCE(r.review_status, 'pending') AS review_status, COUNT(*) AS count
                FROM review_items i
                LEFT JOIN reviews r
                  ON r.round_id = i.round_id
                 AND r.event_id = i.event_id
                 AND r.reviewer_id = ?
                WHERE i.round_id = ?
                GROUP BY COALESCE(r.review_status, 'pending')
                """,
                (_text(reviewer_id), round_id),
            ).fetchall()
        result = {status: 0 for status in REVIEW_STATUS_CODES}
        for row in counts:
            result[row["review_status"]] = row["count"]
        result["total"] = len(self.list_items(round_id))
        return result

    def _require_reviewer(self, reviewer_id: str) -> str:
        reviewer = _text(reviewer_id)
        if not reviewer:
            raise ReviewStoreError("reviewer_id es obligatorio")
        return reviewer

    def _require_item(self, round_id: str, event_id: str) -> dict[str, Any]:
        item = self.get_item(round_id, event_id)
        if item is None:
            raise ReviewStoreError("El evento no pertenece a la ronda congelada")
        if item["observability_status"] != "observable":
            raise ReviewStoreError("Los no observables se mantienen fuera de la cola revisable")
        return item

    @staticmethod
    def _require_code(field_name: str, value: str, allowed: Sequence[str]) -> str:
        code = _text(value)
        if code not in allowed:
            raise ReviewStoreError(f"{field_name} no es un código permitido: {value!r}")
        return code

    def _ensure_review(self, round_id: str, event_id: str, reviewer_id: str, now: str) -> dict[str, Any]:
        existing = self.get_review(round_id, event_id, reviewer_id)
        if existing is not None:
            return existing
        self.connection.execute(
            """
            INSERT INTO reviews (round_id, event_id, reviewer_id, review_status, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (round_id, event_id, reviewer_id, now, now),
        )
        return self.get_review(round_id, event_id, reviewer_id) or {}

    def _audit_fields(
        self,
        *,
        round_id: str,
        event_id: str,
        reviewer_id: str,
        action: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        fields: Iterable[str],
        reason: str | None,
        created_at: str,
    ) -> None:
        for field_name in fields:
            previous = before.get(field_name)
            new = after.get(field_name)
            if previous == new:
                continue
            self.connection.execute(
                """
                INSERT INTO audit_log
                    (round_id, event_id, reviewer_id, action, field_name,
                     previous_value, new_value, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_id,
                    event_id,
                    reviewer_id,
                    action,
                    field_name,
                    None if previous is None else str(previous),
                    None if new is None else str(new),
                    reason,
                    created_at,
                ),
            )

    def save_pass_a(
        self,
        *,
        round_id: str,
        event_id: str,
        reviewer_id: str,
        pass_a_visible_burn_scar: str,
        pass_a_scar_confidence: str,
        pass_a_event_association: str,
        pass_a_competing_land_change: str,
        pass_a_notes: str = "",
        exclusion_reason: str | None = None,
        amend: bool = False,
        amendment_reason: str | None = None,
    ) -> dict[str, Any]:
        reviewer = self._require_reviewer(reviewer_id)
        self._require_item(round_id, event_id)
        visible = self._require_code("pass_a_visible_burn_scar", pass_a_visible_burn_scar, VISIBLE_BURN_SCAR_CODES)
        confidence = self._require_code("pass_a_scar_confidence", pass_a_scar_confidence, SCAR_CONFIDENCE_CODES)
        association = self._require_code("pass_a_event_association", pass_a_event_association, EVENT_ASSOCIATION_CODES)
        competing = self._require_code("pass_a_competing_land_change", pass_a_competing_land_change, COMPETING_LAND_CHANGE_CODES)
        reason = _optional_text(amendment_reason)
        exclusion = _optional_text(exclusion_reason)
        if visible == "unobserved":
            if confidence != "not_applicable":
                raise ReviewStoreError("unobserved requiere pass_a_scar_confidence=not_applicable")
            if not exclusion:
                raise ReviewStoreError("unobserved requiere una razón explícita de exclusión")
        elif confidence == "not_applicable":
            raise ReviewStoreError("not_applicable solo es válido con visible_burn_scar=unobserved")
        elif exclusion:
            raise ReviewStoreError("exclusion_reason solo se usa para una observación unobserved")
        if amend and not reason:
            raise ReviewStoreError("Una enmienda de Pass A requiere una razón")

        now = self._now()
        with self.connection:
            before = self._ensure_review(round_id, event_id, reviewer, now)
            if before.get("pass_a_saved_at") and not amend:
                raise ReviewStoreError("Pass A está bloqueada; use una enmienda explícita")
            if amend and not before.get("pass_a_saved_at"):
                raise ReviewStoreError("No existe una Pass A previa para enmendar")
            if amend and before.get("review_status") == "unobserved":
                raise ReviewStoreError("Una observación unobserved explícita no es revisable de nuevo")

            status = "unobserved" if visible == "unobserved" else "pass_a_complete"
            if amend and before.get("pass_b_saved_at"):
                status = "needs_adjudication"
            revision = int(before.get("pass_a_revision") or 0) + 1
            after = dict(before)
            after.update(
                {
                    "pass_a_visible_burn_scar": visible,
                    "pass_a_scar_confidence": confidence,
                    "pass_a_event_association": association,
                    "pass_a_competing_land_change": competing,
                    "pass_a_notes": _optional_text(pass_a_notes),
                    "pass_a_saved_at": now,
                    "pass_a_revision": revision,
                    "review_status": status,
                    "exclusion_reason": exclusion,
                    "updated_at": now,
                }
            )
            if amend and before.get("pass_b_saved_at"):
                after["adjudication_notes"] = reason
            self.connection.execute(
                """
                UPDATE reviews SET
                    pass_a_visible_burn_scar = ?,
                    pass_a_scar_confidence = ?,
                    pass_a_event_association = ?,
                    pass_a_competing_land_change = ?,
                    pass_a_notes = ?,
                    pass_a_saved_at = ?,
                    pass_a_revision = ?,
                    review_status = ?,
                    exclusion_reason = ?,
                    adjudication_notes = ?,
                    updated_at = ?
                WHERE round_id = ? AND event_id = ? AND reviewer_id = ?
                """,
                (
                    after["pass_a_visible_burn_scar"],
                    after["pass_a_scar_confidence"],
                    after["pass_a_event_association"],
                    after["pass_a_competing_land_change"],
                    after["pass_a_notes"],
                    after["pass_a_saved_at"],
                    after["pass_a_revision"],
                    after["review_status"],
                    after["exclusion_reason"],
                    after.get("adjudication_notes"),
                    after["updated_at"],
                    round_id,
                    event_id,
                    reviewer,
                ),
            )
            self._audit_fields(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer,
                action="amend_pass_a" if amend else "save_pass_a",
                before=before,
                after=after,
                fields=(
                    "pass_a_visible_burn_scar",
                    "pass_a_scar_confidence",
                    "pass_a_event_association",
                    "pass_a_competing_land_change",
                    "pass_a_notes",
                    "pass_a_saved_at",
                    "pass_a_revision",
                    "review_status",
                    "exclusion_reason",
                    "adjudication_notes",
                    "updated_at",
                ),
                reason=reason,
                created_at=now,
            )
            return self.get_review(round_id, event_id, reviewer) or {}

    def save_pass_b(
        self,
        *,
        round_id: str,
        event_id: str,
        reviewer_id: str,
        pass_b_mode_agreement: str,
        pass_b_confidence_after: str,
        pass_b_requires_adjudication: bool,
        pass_b_notes: str = "",
        adjudication_notes: str | None = None,
    ) -> dict[str, Any]:
        reviewer = self._require_reviewer(reviewer_id)
        self._require_item(round_id, event_id)
        mode = self._require_code("pass_b_mode_agreement", pass_b_mode_agreement, MODE_AGREEMENT_CODES)
        confidence = self._require_code("pass_b_confidence_after", pass_b_confidence_after, SCAR_CONFIDENCE_CODES)
        notes = _optional_text(pass_b_notes)
        if pass_b_requires_adjudication and not notes:
            raise ReviewStoreError("needs_adjudication requiere notas de Pass B")

        now = self._now()
        with self.connection:
            before = self._ensure_review(round_id, event_id, reviewer, now)
            if not before.get("pass_a_saved_at"):
                raise ReviewStoreError("Pass B permanece oculta hasta guardar Pass A")
            if before.get("review_status") in {"unobserved", "excluded_with_reason"}:
                raise ReviewStoreError("El estado actual no permite una Pass B")
            revision = int(before.get("pass_b_revision") or 0) + 1
            status = "needs_adjudication" if pass_b_requires_adjudication else "pass_b_complete"
            explicit_adjudication = _optional_text(adjudication_notes)
            if pass_b_requires_adjudication:
                explicit_adjudication = explicit_adjudication or notes
            after = dict(before)
            after.update(
                {
                    "pass_b_mode_agreement": mode,
                    "pass_b_confidence_after": confidence,
                    "pass_b_requires_adjudication": 1 if pass_b_requires_adjudication else 0,
                    "pass_b_notes": notes,
                    "pass_b_saved_at": now,
                    "pass_b_revision": revision,
                    "review_status": status,
                    "adjudication_notes": explicit_adjudication if explicit_adjudication is not None else before.get("adjudication_notes"),
                    "updated_at": now,
                }
            )
            self.connection.execute(
                """
                UPDATE reviews SET
                    pass_b_mode_agreement = ?,
                    pass_b_confidence_after = ?,
                    pass_b_requires_adjudication = ?,
                    pass_b_notes = ?,
                    pass_b_saved_at = ?,
                    pass_b_revision = ?,
                    review_status = ?,
                    adjudication_notes = ?,
                    updated_at = ?
                WHERE round_id = ? AND event_id = ? AND reviewer_id = ?
                """,
                (
                    after["pass_b_mode_agreement"],
                    after["pass_b_confidence_after"],
                    after["pass_b_requires_adjudication"],
                    after["pass_b_notes"],
                    after["pass_b_saved_at"],
                    after["pass_b_revision"],
                    after["review_status"],
                    after["adjudication_notes"],
                    after["updated_at"],
                    round_id,
                    event_id,
                    reviewer,
                ),
            )
            self._audit_fields(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer,
                action="save_pass_b",
                before=before,
                after=after,
                fields=(
                    "pass_b_mode_agreement",
                    "pass_b_confidence_after",
                    "pass_b_requires_adjudication",
                    "pass_b_notes",
                    "pass_b_saved_at",
                    "pass_b_revision",
                    "review_status",
                    "adjudication_notes",
                    "updated_at",
                ),
                reason=None,
                created_at=now,
            )
            return self.get_review(round_id, event_id, reviewer) or {}

    def update_adjudication_notes(
        self,
        *,
        round_id: str,
        event_id: str,
        reviewer_id: str,
        notes: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        reviewer = self._require_reviewer(reviewer_id)
        self._require_item(round_id, event_id)
        note = _optional_text(notes)
        if not note:
            raise ReviewStoreError("adjudication_notes no puede estar vacío")
        now = self._now()
        with self.connection:
            before = self.get_review(round_id, event_id, reviewer)
            if before is None:
                raise ReviewStoreError("No existe una revisión para actualizar")
            if before.get("review_status") != "needs_adjudication":
                raise ReviewStoreError("Solo una revisión needs_adjudication admite esa nota")
            after = dict(before)
            after.update({"adjudication_notes": note, "updated_at": now})
            self.connection.execute(
                "UPDATE reviews SET adjudication_notes = ?, updated_at = ? "
                "WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
                (note, now, round_id, event_id, reviewer),
            )
            self._audit_fields(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer,
                action="update_adjudication_notes",
                before=before,
                after=after,
                fields=("adjudication_notes", "updated_at"),
                reason=_optional_text(reason),
                created_at=now,
            )
            return self.get_review(round_id, event_id, reviewer) or {}

    def set_exclusion(
        self,
        *,
        round_id: str,
        event_id: str,
        reviewer_id: str,
        reason: str,
        status: str = "excluded_with_reason",
    ) -> dict[str, Any]:
        reviewer = self._require_reviewer(reviewer_id)
        self._require_item(round_id, event_id)
        if status not in {"excluded_with_reason", "unobserved"}:
            raise ReviewStoreError("Estado de exclusión no permitido")
        exclusion = _optional_text(reason)
        if not exclusion:
            raise ReviewStoreError("Una exclusión requiere una razón")
        now = self._now()
        with self.connection:
            before = self._ensure_review(round_id, event_id, reviewer, now)
            if not before.get("pass_a_saved_at"):
                raise ReviewStoreError("La exclusión requiere una Pass A guardada")
            if status == "unobserved" and (
                before.get("pass_a_visible_burn_scar") != "unobserved"
                or before.get("pass_a_scar_confidence") != "not_applicable"
            ):
                raise ReviewStoreError("unobserved requiere una Pass A coherente y no observable")
            after = dict(before)
            after.update({"review_status": status, "exclusion_reason": exclusion, "updated_at": now})
            self.connection.execute(
                "UPDATE reviews SET review_status = ?, exclusion_reason = ?, updated_at = ? "
                "WHERE round_id = ? AND event_id = ? AND reviewer_id = ?",
                (status, exclusion, now, round_id, event_id, reviewer),
            )
            self._audit_fields(
                round_id=round_id,
                event_id=event_id,
                reviewer_id=reviewer,
                action="set_exclusion",
                before=before,
                after=after,
                fields=("review_status", "exclusion_reason", "updated_at"),
                reason=exclusion,
                created_at=now,
            )
            return self.get_review(round_id, event_id, reviewer) or {}

    def audit_entries(self, round_id: str, event_id: str, reviewer_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM audit_log
            WHERE round_id = ? AND event_id = ? AND reviewer_id = ?
            ORDER BY audit_id
            """,
            (round_id, event_id, _text(reviewer_id)),
        ).fetchall()
        return [dict(row) for row in rows]

    def _normalized_rows(self, round_id: str, reviewer_id: str) -> list[dict[str, Any]]:
        reviewer = self._require_reviewer(reviewer_id)
        rows = self.connection.execute(
            """
            SELECT i.*, r.reviewer_id AS stored_reviewer_id,
                   r.pass_a_visible_burn_scar, r.pass_a_scar_confidence,
                   r.pass_a_event_association, r.pass_a_competing_land_change,
                   r.pass_a_notes, r.pass_a_saved_at, r.pass_a_revision,
                   r.pass_b_mode_agreement, r.pass_b_confidence_after,
                   r.pass_b_requires_adjudication, r.pass_b_notes,
                   r.pass_b_saved_at, r.pass_b_revision, r.review_status,
                   r.exclusion_reason, r.adjudication_notes,
                   r.created_at, r.updated_at
            FROM review_items i
            LEFT JOIN reviews r
              ON r.round_id = i.round_id
             AND r.event_id = i.event_id
             AND r.reviewer_id = ?
            WHERE i.round_id = ?
            ORDER BY i.randomized_order
            """,
            (reviewer, round_id),
        ).fetchall()
        normalized: list[dict[str, Any]] = []
        for row in rows:
            raw = dict(row)
            item = {
                "schema_version": SCHEMA_VERSION,
                "round_id": raw["round_id"],
                "event_id": raw["event_id"],
                "randomized_order": raw["randomized_order"],
                "reviewer_id": reviewer,
                "protocol_version": PROTOCOL_VERSION,
                "quicklook_version": QUICKLOOK_VERSION,
                "observability_status": raw["observability_status"],
                "multispectral_panel_path": raw["multispectral_panel_path"],
                "temporal_panel_path": raw["temporal_panel_path"],
                "pass_a_visible_burn_scar": raw["pass_a_visible_burn_scar"],
                "pass_a_scar_confidence": raw["pass_a_scar_confidence"],
                "pass_a_event_association": raw["pass_a_event_association"],
                "pass_a_competing_land_change": raw["pass_a_competing_land_change"],
                "pass_a_notes": raw["pass_a_notes"],
                "pass_a_saved_at": raw["pass_a_saved_at"],
                "pass_a_revision": raw["pass_a_revision"] if raw["pass_a_revision"] is not None else 0,
                "pass_b_mode_agreement": raw["pass_b_mode_agreement"],
                "pass_b_confidence_after": raw["pass_b_confidence_after"],
                "pass_b_requires_adjudication": raw["pass_b_requires_adjudication"],
                "pass_b_notes": raw["pass_b_notes"],
                "pass_b_saved_at": raw["pass_b_saved_at"],
                "pass_b_revision": raw["pass_b_revision"] if raw["pass_b_revision"] is not None else 0,
                "review_status": raw["review_status"] or "pending",
                "exclusion_reason": raw["exclusion_reason"],
                "adjudication_notes": raw["adjudication_notes"],
                "created_at": raw["created_at"],
                "updated_at": raw["updated_at"],
            }
            normalized.append({column: item.get(column) for column in NORMALIZED_EXPORT_COLUMNS})
        if len(normalized) != len(CALIBRATION_EVENT_IDS):
            raise ReviewStoreError("La exportación requiere exactamente siete items")
        return normalized

    @staticmethod
    def _filename_component(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", _text(value)).strip("._")
        if not safe:
            raise ReviewStoreError("reviewer_id no genera un nombre de archivo seguro")
        return safe

    @staticmethod
    def _csv_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _legacy_rows(self, normalized: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in normalized:
            status = _text(row.get("review_status")) or "pending"
            complete = status in {"pass_b_complete", "needs_adjudication", "unobserved", "excluded_with_reason"}
            if not complete:
                result.append(
                    {
                        "calibration_round": row["round_id"],
                        "randomized_order": row["randomized_order"],
                        "event_id": row["event_id"],
                        "reviewer_id": "",
                        "reviewed_at": "",
                        "protocol_version": row["protocol_version"],
                        "quicklook_version": row["quicklook_version"],
                        "multispectral_panel_path": row["multispectral_panel_path"],
                        "temporal_panel_path": row["temporal_panel_path"],
                        "visible_burn_scar": "",
                        "scar_confidence": "",
                        "event_association": "",
                        "competing_land_change": "",
                        "mode_agreement": "",
                        "reviewer_notes": "",
                        "review_status": "pending",
                        "exclusion_reason": "",
                        "adjudication_notes": "",
                    }
                )
                continue
            pass_a_notes = _text(row.get("pass_a_notes"))
            pass_b_notes = _text(row.get("pass_b_notes"))
            reviewer_notes = pass_a_notes
            if pass_b_notes:
                reviewer_notes = f"{pass_a_notes}\n[pass_b] {pass_b_notes}" if pass_a_notes else f"[pass_b] {pass_b_notes}"
            legacy_status = "reviewed" if status == "pass_b_complete" else status
            result.append(
                {
                    "calibration_round": row["round_id"],
                    "randomized_order": row["randomized_order"],
                    "event_id": row["event_id"],
                    "reviewer_id": row["reviewer_id"],
                    "reviewed_at": row.get("pass_b_saved_at") or row.get("pass_a_saved_at") or "",
                    "protocol_version": row["protocol_version"],
                    "quicklook_version": row["quicklook_version"],
                    "multispectral_panel_path": row["multispectral_panel_path"],
                    "temporal_panel_path": row["temporal_panel_path"],
                    "visible_burn_scar": row.get("pass_a_visible_burn_scar") or "",
                    "scar_confidence": row.get("pass_a_scar_confidence") or "",
                    "event_association": row.get("pass_a_event_association") or "",
                    "competing_land_change": row.get("pass_a_competing_land_change") or "",
                    "mode_agreement": row.get("pass_b_mode_agreement") or ("unavailable" if status == "unobserved" else ""),
                    "reviewer_notes": reviewer_notes,
                    "review_status": legacy_status,
                    "exclusion_reason": row.get("exclusion_reason") or "",
                    "adjudication_notes": row.get("adjudication_notes") or (pass_b_notes if status == "needs_adjudication" else ""),
                }
            )
        return result

    def export_snapshot(
        self,
        *,
        round_id: str = CALIBRATION_ROUND,
        reviewer_id: str,
        export_dir: Path | str = DEFAULT_EXPORT_DIR,
        audit_dir: Path | str = DEFAULT_AUDIT_DIR,
    ) -> dict[str, Path]:
        normalized = self._normalized_rows(round_id, reviewer_id)
        component = self._filename_component(reviewer_id)
        export_root = Path(export_dir)
        audit_root = Path(audit_dir)
        export_root.mkdir(parents=True, exist_ok=True)
        audit_root.mkdir(parents=True, exist_ok=True)

        csv_path = export_root / f"calibration_round1_{component}_snapshot.csv"
        json_path = export_root / f"calibration_round1_{component}_snapshot.json"
        legacy_path = export_root / f"calibration_round1_{component}_validator.csv"
        audit_path = audit_root / f"calibration_round1_{component}_audit.jsonl"

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=NORMALIZED_EXPORT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows({column: self._csv_value(row.get(column)) for column in NORMALIZED_EXPORT_COLUMNS} for row in normalized)

        round_row = self.connection.execute(
            "SELECT round_id, protocol_version, quicklook_version, random_seed, created_at, status "
            "FROM review_rounds WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "round": dict(round_row) if round_row is not None else {"round_id": round_id},
            "reviewer_id": _text(reviewer_id),
            "items": normalized,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        legacy_rows = self._legacy_rows(normalized)
        with legacy_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LEGACY_EXPORT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows({column: self._csv_value(row.get(column)) for column in LEGACY_EXPORT_COLUMNS} for row in legacy_rows)

        audit_rows = self.connection.execute(
            "SELECT * FROM audit_log WHERE round_id = ? AND reviewer_id = ? ORDER BY audit_id",
            (round_id, _text(reviewer_id)),
        ).fetchall()
        with audit_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in audit_rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
        return {
            "csv": csv_path,
            "json": json_path,
            "legacy_csv": legacy_path,
            "audit_jsonl": audit_path,
        }
