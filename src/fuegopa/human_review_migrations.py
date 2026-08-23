"""Versioned, cumulative SQLite migrations for formal human review.

The original calibration schema remains intact.  The formal round uses a
separate namespace so that the historical calibration and blind-control rows
cannot be mistaken for formal human observations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import sqlite3


CURRENT_MIGRATION_VERSION = 4
MIGRATION_NAMES = {
    1: "legacy_schema_baseline",
    2: "formal_review_v1",
    3: "formal_review_integrity_triggers",
    4: "formal_review_integrity_hardening",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _migration_checksum(version: int) -> str:
    return hashlib.sha256(f"fuegopa-migration:{version}:{MIGRATION_NAMES[version]}".encode("utf-8")).hexdigest()


FORMAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS formal_review_rounds (
    round_id TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('prepared', 'active', 'closed', 'cancelled')),
    execution_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (execution_status IN ('not_started', 'in_progress', 'closed')),
    base_head TEXT NOT NULL,
    pilot_event_count INTEGER NOT NULL CHECK (pilot_event_count >= 0),
    observable_event_count INTEGER NOT NULL CHECK (observable_event_count >= 0),
    unobserved_event_count INTEGER NOT NULL CHECK (unobserved_event_count >= 0),
    protocol_sha256 TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL,
    input_manifest_sha256 TEXT NOT NULL,
    private_seed_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviewer_profiles (
    profile_id TEXT PRIMARY KEY,
    reviewer_type TEXT NOT NULL CHECK (reviewer_type IN ('human', 'ai_assisted')),
    reviewer_expertise TEXT NOT NULL CHECK (reviewer_expertise IN ('protocol_trained_reviewer', 'remote_sensing_specialist', 'domain_expert', 'not_applicable')),
    model_name TEXT,
    model_version TEXT,
    protocol_training_version TEXT NOT NULL,
    label_status TEXT NOT NULL CHECK (label_status IN ('human_observation', 'provisional_pseudolabel')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (reviewer_type = 'human' AND coalesce(model_name, '') = ''
            AND coalesce(model_version, '') = ''
            AND reviewer_expertise IN ('protocol_trained_reviewer', 'remote_sensing_specialist', 'domain_expert')
            AND label_status = 'human_observation')
        OR
        (reviewer_type = 'ai_assisted' AND length(trim(coalesce(model_name, ''))) > 0
            AND length(trim(coalesce(model_version, ''))) > 0
            AND reviewer_expertise = 'not_applicable'
            AND label_status = 'provisional_pseudolabel')
    )
);

CREATE TABLE IF NOT EXISTS formal_review_slots (
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL CHECK (slot_id IN ('HUMAN_SLOT_A', 'HUMAN_SLOT_B')),
    profile_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('unbound', 'bound', 'active', 'closed')),
    order_manifest_sha256 TEXT NOT NULL,
    private_seed_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, slot_id),
    FOREIGN KEY (round_id) REFERENCES formal_review_rounds(round_id),
    FOREIGN KEY (profile_id) REFERENCES reviewer_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS formal_assignments (
    assignment_id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    blind_alias TEXT NOT NULL,
    randomized_order INTEGER NOT NULL CHECK (randomized_order >= 1),
    visual_reference_key TEXT NOT NULL,
    visual_input_sha256 TEXT NOT NULL,
    visual_input_manifest_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'pass_a_locked', 'pending_pair_review', 'pending_adjudication', 'pending_expert_review', 'review_complete')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (round_id, slot_id) REFERENCES formal_review_slots(round_id, slot_id),
    UNIQUE (round_id, slot_id, event_id),
    UNIQUE (round_id, slot_id, blind_alias),
    UNIQUE (round_id, slot_id, randomized_order)
);

CREATE TABLE IF NOT EXISTS formal_pass_a (
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    reviewer_type TEXT NOT NULL CHECK (reviewer_type = 'human'),
    reviewer_expertise TEXT NOT NULL CHECK (reviewer_expertise IN ('protocol_trained_reviewer', 'remote_sensing_specialist', 'domain_expert')),
    label_status TEXT NOT NULL CHECK (label_status = 'human_observation'),
    visible_burn_scar TEXT NOT NULL CHECK (visible_burn_scar IN ('yes', 'no', 'ambiguous')),
    scar_confidence TEXT NOT NULL CHECK (scar_confidence IN ('high', 'medium', 'low')),
    event_association TEXT NOT NULL CHECK (event_association IN ('likely', 'possible', 'unlikely', 'indeterminate')),
    competing_land_change TEXT NOT NULL CHECK (competing_land_change IN ('none_visible', 'agriculture_or_harvest', 'soil_exposure', 'vegetation_phenology', 'moisture_or_flooding', 'water', 'urban_or_construction', 'mixed', 'unknown')),
    observation_limitation TEXT NOT NULL CHECK (observation_limitation IN ('none', 'cloud_or_haze', 'mask_or_nodata', 'shadow', 'partial_coverage', 'insufficient_temporal_separation', 'mixed', 'other')),
    notes TEXT,
    payload_sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    locked_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, slot_id, event_id),
    FOREIGN KEY (assignment_id) REFERENCES formal_assignments(assignment_id),
    FOREIGN KEY (profile_id) REFERENCES reviewer_profiles(profile_id)
);

CREATE TABLE IF NOT EXISTS formal_pass_b (
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    mode_agreement TEXT NOT NULL CHECK (mode_agreement IN ('agree', 'partially_agree', 'disagree')),
    confidence_after TEXT NOT NULL CHECK (confidence_after IN ('high', 'medium', 'low')),
    reviewer_requested_adjudication INTEGER NOT NULL CHECK (reviewer_requested_adjudication IN (0, 1)),
    request_reason TEXT,
    notes TEXT,
    payload_sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    saved_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, slot_id, event_id),
    FOREIGN KEY (assignment_id) REFERENCES formal_assignments(assignment_id),
    FOREIGN KEY (profile_id) REFERENCES reviewer_profiles(profile_id),
    CHECK ((reviewer_requested_adjudication = 0 AND coalesce(request_reason, '') = '') OR reviewer_requested_adjudication = 1)
);

CREATE TABLE IF NOT EXISTS formal_pairwise_comparisons (
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    slot_a TEXT NOT NULL,
    slot_b TEXT NOT NULL,
    field_agreements_json TEXT NOT NULL,
    material_disagreements_json TEXT NOT NULL,
    nonmaterial_disagreements_json TEXT NOT NULL,
    needs_adjudication INTEGER NOT NULL CHECK (needs_adjudication IN (0, 1)),
    reason_codes_json TEXT NOT NULL,
    source_payload_sha256 TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, event_id, slot_a, slot_b),
    FOREIGN KEY (round_id, slot_a, event_id) REFERENCES formal_pass_a(round_id, slot_id, event_id),
    FOREIGN KEY (round_id, slot_b, event_id) REFERENCES formal_pass_a(round_id, slot_id, event_id)
);

CREATE TABLE IF NOT EXISTS formal_triage (
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    triage_scope TEXT NOT NULL CHECK (triage_scope IN ('reviewer_a', 'reviewer_b', 'pairwise', 'adjudication')),
    needs_adjudication INTEGER NOT NULL CHECK (needs_adjudication IN (0, 1)),
    adjudication_reason_codes_json TEXT NOT NULL,
    expert_review_priority TEXT NOT NULL CHECK (expert_review_priority IN ('none', 'recommended', 'required')),
    expert_review_reason_codes_json TEXT NOT NULL,
    administrative_status TEXT NOT NULL CHECK (administrative_status IN ('pending', 'pending_adjudication', 'pending_expert_review', 'complete')),
    source_payload_sha256 TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, event_id, triage_scope)
);

CREATE TABLE IF NOT EXISTS formal_adjudications (
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    adjudication_id TEXT NOT NULL,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('pending', 'complete')),
    structured_resolution_code TEXT,
    material_disagreement_resolved INTEGER NOT NULL CHECK (material_disagreement_resolved IN (0, 1)),
    specialist_question_code TEXT,
    resolution_notes TEXT,
    profile_id TEXT,
    payload_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, event_id, adjudication_id)
);

CREATE TABLE IF NOT EXISTS formal_expert_reviews (
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    expert_review_id TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('recommended', 'required')),
    specialist_question_code TEXT NOT NULL,
    profile_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
    outcome_notes TEXT,
    payload_sha256 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, event_id, expert_review_id)
);

CREATE TABLE IF NOT EXISTS formal_unobserved_events (
    event_id TEXT PRIMARY KEY,
    observability_status TEXT NOT NULL CHECK (observability_status = 'unobserved'),
    exclusion_reason TEXT NOT NULL CHECK (length(trim(exclusion_reason)) > 0),
    protocol_version TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formal_input_manifests (
    manifest_id TEXT PRIMARY KEY,
    manifest_kind TEXT NOT NULL CHECK (manifest_kind IN ('event_queue', 'unobserved_registry', 'visual_input', 'protocol')),
    source_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formal_package_manifests (
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    package_id TEXT NOT NULL,
    package_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    input_manifest_sha256 TEXT NOT NULL,
    private_manifest_sha256 TEXT NOT NULL,
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (round_id, slot_id),
    FOREIGN KEY (round_id, slot_id) REFERENCES formal_review_slots(round_id, slot_id)
);

CREATE TABLE IF NOT EXISTS formal_audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    slot_id TEXT,
    event_id TEXT,
    actor_profile_id TEXT,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    previous_payload_sha256 TEXT,
    new_payload_sha256 TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formal_amendments (
    amendment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    pass_name TEXT NOT NULL CHECK (pass_name IN ('pass_a', 'pass_b', 'adjudication', 'expert_review')),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    previous_payload_json TEXT NOT NULL,
    corrected_payload_json TEXT NOT NULL,
    amendment_reason TEXT NOT NULL CHECK (length(trim(amendment_reason)) > 0),
    actor_profile_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_formal_assignments_round_slot_order
    ON formal_assignments(round_id, slot_id, randomized_order);
CREATE INDEX IF NOT EXISTS idx_formal_pass_a_profile
    ON formal_pass_a(round_id, slot_id, profile_id);
CREATE INDEX IF NOT EXISTS idx_formal_triage_status
    ON formal_triage(round_id, administrative_status);

CREATE TRIGGER IF NOT EXISTS formal_audit_no_update
BEFORE UPDATE ON formal_audit_log
BEGIN
    SELECT RAISE(ABORT, 'formal_audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS formal_audit_no_delete
BEFORE DELETE ON formal_audit_log
BEGIN
    SELECT RAISE(ABORT, 'formal_audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS formal_amendments_no_update
BEFORE UPDATE ON formal_amendments
BEGIN
    SELECT RAISE(ABORT, 'formal_amendments is append-only');
END;

CREATE TRIGGER IF NOT EXISTS formal_amendments_no_delete
BEFORE DELETE ON formal_amendments
BEGIN
    SELECT RAISE(ABORT, 'formal_amendments is append-only');
END;
"""


FORMAL_INTEGRITY_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS formal_pass_b_requires_pass_a
BEFORE INSERT ON formal_pass_b
WHEN NOT EXISTS (
    SELECT 1 FROM formal_pass_a
    WHERE round_id = NEW.round_id AND slot_id = NEW.slot_id AND event_id = NEW.event_id
)
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_b requires locked formal_pass_a');
END;

CREATE TRIGGER IF NOT EXISTS formal_pairwise_requires_pass_b
BEFORE INSERT ON formal_pairwise_comparisons
WHEN NOT EXISTS (
    SELECT 1 FROM formal_pass_b
    WHERE round_id = NEW.round_id AND slot_id = NEW.slot_a AND event_id = NEW.event_id
)
OR NOT EXISTS (
    SELECT 1 FROM formal_pass_b
    WHERE round_id = NEW.round_id AND slot_id = NEW.slot_b AND event_id = NEW.event_id
)
BEGIN
    SELECT RAISE(ABORT, 'pairwise comparison requires both formal_pass_b rows');
END;

CREATE TRIGGER IF NOT EXISTS formal_pass_a_update_requires_amendment
BEFORE UPDATE ON formal_pass_a
WHEN NOT EXISTS (
    SELECT 1 FROM formal_amendments
    WHERE round_id = OLD.round_id AND slot_id = OLD.slot_id AND event_id = OLD.event_id
      AND pass_name = 'pass_a' AND revision = NEW.revision
)
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_a is locked; amendment required');
END;

CREATE TRIGGER IF NOT EXISTS formal_pass_a_no_delete
BEFORE DELETE ON formal_pass_a
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_a is immutable');
END;
"""


FORMAL_INTEGRITY_HARDENING_SQL = """
CREATE TABLE IF NOT EXISTS formal_protocol_reconciliations (
    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    old_protocol_sha256 TEXT NOT NULL,
    new_protocol_sha256 TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    old_package_hashes_json TEXT NOT NULL,
    new_package_hashes_json TEXT NOT NULL,
    seed_preserved INTEGER NOT NULL CHECK (seed_preserved IN (0, 1)),
    aliases_preserved INTEGER NOT NULL CHECK (aliases_preserved IN (0, 1)),
    orders_preserved INTEGER NOT NULL CHECK (orders_preserved IN (0, 1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (round_id) REFERENCES formal_review_rounds(round_id),
    UNIQUE (round_id, old_protocol_sha256, new_protocol_sha256, reason_code)
);

CREATE TABLE IF NOT EXISTS formal_artifact_manifests (
    round_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, artifact_id),
    FOREIGN KEY (round_id) REFERENCES formal_review_rounds(round_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_formal_slots_round_profile
    ON formal_review_slots(round_id, profile_id)
    WHERE profile_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS formal_reviewer_profiles_no_update
BEFORE UPDATE ON reviewer_profiles
BEGIN
    SELECT RAISE(ABORT, 'reviewer_profiles are immutable; register a new profile id');
END;

CREATE TRIGGER IF NOT EXISTS formal_reviewer_profiles_no_delete
BEFORE DELETE ON reviewer_profiles
BEGIN
    SELECT RAISE(ABORT, 'reviewer_profiles are append-only');
END;

CREATE TRIGGER IF NOT EXISTS formal_review_round_identity_no_update
BEFORE UPDATE ON formal_review_rounds
WHEN OLD.round_id <> NEW.round_id
  OR OLD.protocol_version <> NEW.protocol_version
  OR OLD.schema_version <> NEW.schema_version
  OR OLD.tool_version <> NEW.tool_version
  OR OLD.base_head <> NEW.base_head
  OR OLD.pilot_event_count <> NEW.pilot_event_count
  OR OLD.observable_event_count <> NEW.observable_event_count
  OR OLD.unobserved_event_count <> NEW.unobserved_event_count
  OR OLD.source_manifest_sha256 <> NEW.source_manifest_sha256
  OR OLD.input_manifest_sha256 <> NEW.input_manifest_sha256
  OR OLD.private_seed_sha256 <> NEW.private_seed_sha256
  OR (
      OLD.protocol_sha256 <> NEW.protocol_sha256
      AND NOT EXISTS (
          SELECT 1 FROM formal_protocol_reconciliations r
          WHERE r.round_id = OLD.round_id
            AND r.old_protocol_sha256 = OLD.protocol_sha256
            AND r.new_protocol_sha256 = NEW.protocol_sha256
      )
  )
BEGIN
    SELECT RAISE(ABORT, 'formal_review_round identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS formal_assignments_identity_no_update
BEFORE UPDATE ON formal_assignments
WHEN OLD.assignment_id <> NEW.assignment_id
  OR OLD.round_id <> NEW.round_id
  OR OLD.slot_id <> NEW.slot_id
  OR OLD.event_id <> NEW.event_id
  OR OLD.blind_alias <> NEW.blind_alias
  OR OLD.randomized_order <> NEW.randomized_order
  OR OLD.visual_reference_key <> NEW.visual_reference_key
  OR coalesce(OLD.visual_input_reference, '') <> coalesce(NEW.visual_input_reference, '')
  OR OLD.visual_input_sha256 <> NEW.visual_input_sha256
  OR OLD.visual_input_manifest_sha256 <> NEW.visual_input_manifest_sha256
  OR coalesce(OLD.temporal_input_reference, '') <> coalesce(NEW.temporal_input_reference, '')
  OR coalesce(OLD.temporal_input_sha256, '') <> coalesce(NEW.temporal_input_sha256, '')
  OR coalesce(OLD.temporal_input_manifest_sha256, '') <> coalesce(NEW.temporal_input_manifest_sha256, '')
  OR coalesce(OLD.temporal_input_mode, '') <> coalesce(NEW.temporal_input_mode, '')
  OR coalesce(OLD.temporal_input_provenance, '') <> coalesce(NEW.temporal_input_provenance, '')
BEGIN
    SELECT RAISE(ABORT, 'formal_assignments identity is immutable');
END;

CREATE TRIGGER IF NOT EXISTS formal_assignments_no_delete
BEFORE DELETE ON formal_assignments
BEGIN
    SELECT RAISE(ABORT, 'formal_assignments are append-only');
END;

DROP TRIGGER IF EXISTS formal_pass_a_update_requires_amendment;
CREATE TRIGGER formal_pass_a_update_requires_amendment
BEFORE UPDATE ON formal_pass_a
WHEN NOT EXISTS (
    SELECT 1 FROM formal_amendments
    WHERE round_id = OLD.round_id AND slot_id = OLD.slot_id AND event_id = OLD.event_id
      AND pass_name = 'pass_a' AND revision = NEW.revision
      AND previous_payload_sha256 = OLD.payload_sha256
      AND corrected_payload_sha256 = NEW.payload_sha256
)
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_a is locked; specific amendment with hashes required');
END;

CREATE TRIGGER IF NOT EXISTS formal_pass_b_traceable_inputs
BEFORE INSERT ON formal_pass_b
WHEN EXISTS (
    SELECT 1 FROM formal_pass_a
    WHERE round_id = NEW.round_id AND slot_id = NEW.slot_id AND event_id = NEW.event_id
)
  AND (coalesce(trim(NEW.selected_pair_reference), '') = ''
  OR coalesce(trim(NEW.selected_pair_sha256), '') = ''
  OR coalesce(trim(NEW.selected_pair_manifest_sha256), '') = ''
  OR coalesce(trim(NEW.selected_pair_mode), '') <> 'selected_pair'
  OR coalesce(trim(NEW.selected_pair_provenance), '') = ''
  OR coalesce(trim(NEW.window_median_reference), '') = ''
  OR coalesce(trim(NEW.window_median_sha256), '') = ''
  OR coalesce(trim(NEW.window_median_manifest_sha256), '') = ''
  OR coalesce(trim(NEW.window_median_mode), '') <> 'window_median'
  OR coalesce(trim(NEW.window_median_provenance), '') = ''
  OR NEW.selected_pair_reference = NEW.window_median_reference
  OR NEW.selected_pair_sha256 = NEW.window_median_sha256
  OR NOT EXISTS (
      SELECT 1 FROM formal_assignments a
      WHERE a.assignment_id = NEW.assignment_id
        AND a.round_id = NEW.round_id
        AND a.slot_id = NEW.slot_id
        AND a.event_id = NEW.event_id
        AND a.visual_input_sha256 = NEW.selected_pair_sha256
        AND a.visual_input_manifest_sha256 = NEW.selected_pair_manifest_sha256
        AND a.temporal_input_reference = NEW.window_median_reference
        AND a.temporal_input_sha256 = NEW.window_median_sha256
        AND a.temporal_input_manifest_sha256 = NEW.window_median_manifest_sha256
        AND a.temporal_input_mode = NEW.window_median_mode
        AND a.temporal_input_provenance = NEW.window_median_provenance
  ))
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_b requires two distinct frozen traceable inputs');
END;

CREATE TRIGGER IF NOT EXISTS formal_pass_b_no_update
BEFORE UPDATE ON formal_pass_b
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_b is insert-once; use a formal amendment');
END;

CREATE TRIGGER IF NOT EXISTS formal_pass_b_no_delete
BEFORE DELETE ON formal_pass_b
BEGIN
    SELECT RAISE(ABORT, 'formal_pass_b is immutable');
END;

CREATE TRIGGER IF NOT EXISTS formal_protocol_reconciliations_no_update
BEFORE UPDATE ON formal_protocol_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'formal_protocol_reconciliations is append-only');
END;

CREATE TRIGGER IF NOT EXISTS formal_protocol_reconciliations_no_delete
BEFORE DELETE ON formal_protocol_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'formal_protocol_reconciliations is append-only');
END;
"""


def _add_column_if_missing(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _apply_integrity_hardening(connection: sqlite3.Connection) -> None:
    """Add only cumulative columns/tables/triggers; never rewrite review rows."""

    _add_column_if_missing(
        connection,
        "formal_review_rounds",
        "execution_authorized",
        "INTEGER NOT NULL DEFAULT 0 CHECK (execution_authorized IN (0, 1))",
    )
    for column in ("previous_payload_sha256", "corrected_payload_sha256"):
        _add_column_if_missing(connection, "formal_amendments", column, "TEXT")
    for column, definition in (
        ("visual_input_reference", "TEXT"),
        ("temporal_input_reference", "TEXT"),
        ("temporal_input_sha256", "TEXT"),
        ("temporal_input_manifest_sha256", "TEXT"),
        ("temporal_input_mode", "TEXT"),
        ("temporal_input_provenance", "TEXT"),
    ):
        _add_column_if_missing(connection, "formal_assignments", column, definition)
    for column, definition in (
        ("selected_pair_reference", "TEXT"),
        ("selected_pair_sha256", "TEXT"),
        ("selected_pair_manifest_sha256", "TEXT"),
        ("selected_pair_mode", "TEXT"),
        ("selected_pair_provenance", "TEXT"),
        ("window_median_reference", "TEXT"),
        ("window_median_sha256", "TEXT"),
        ("window_median_manifest_sha256", "TEXT"),
        ("window_median_mode", "TEXT"),
        ("window_median_provenance", "TEXT"),
    ):
        _add_column_if_missing(connection, "formal_pass_b", column, definition)
    connection.executescript(FORMAL_INTEGRITY_HARDENING_SQL)


def apply_migrations(connection: sqlite3.Connection, *, now: str | None = None) -> None:
    """Apply all migrations exactly once, preserving existing rows."""

    timestamp = now or _utc_now()
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL UNIQUE,
            migration_checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    for version in range(1, CURRENT_MIGRATION_VERSION + 1):
        existing = connection.execute(
            "SELECT migration_name, migration_checksum FROM schema_migrations WHERE migration_version = ?",
            (version,),
        ).fetchone()
        if existing is not None:
            expected_name = MIGRATION_NAMES[version]
            expected_checksum = _migration_checksum(version)
            if existing[0] != expected_name or existing[1] != expected_checksum:
                raise RuntimeError(f"Migración SQLite incompatible para versión {version}")
            continue
        if version == 2:
            connection.executescript(FORMAL_SCHEMA_SQL)
        elif version == 3:
            connection.executescript(FORMAL_INTEGRITY_TRIGGERS_SQL)
        elif version == 4:
            _apply_integrity_hardening(connection)
        connection.execute(
            "INSERT INTO schema_migrations (migration_version, migration_name, migration_checksum, applied_at) VALUES (?, ?, ?, ?)",
            (version, MIGRATION_NAMES[version], _migration_checksum(version), timestamp),
        )
    connection.commit()
