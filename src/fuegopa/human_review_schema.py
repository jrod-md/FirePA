"""SQLite schema and stable vocabularies for the local human-review tool.

The schema deliberately contains observation and review-administration fields
only.  It is not a scientific results table and it never derives values from
the panel pixels.
"""

from __future__ import annotations

from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3"
DEFAULT_EXPORT_DIR = ROOT / "outputs" / "human_review" / "exports"
DEFAULT_AUDIT_DIR = ROOT / "outputs" / "human_review" / "audit"
DEFAULT_CALIBRATION_PATH = ROOT / "outputs" / "human_review" / "calibration_round1_blinded.csv"
DEFAULT_MANIFEST_PATH = ROOT / "outputs" / "human_review" / "calibration_round1_manifest.json"
DEFAULT_UNOBSERVED_PATH = ROOT / "outputs" / "human_review" / "unobserved_events.csv"

SCHEMA_VERSION = "fuegopa-human-review-v1"
CALIBRATION_ROUND = "round1"
PROTOCOL_VERSION = "draft-v1"
QUICKLOOK_VERSION = "fuegopa-dnbr-quicklook-level2-v1"
RANDOMIZATION_SEED = 20260721

CALIBRATION_EVENT_IDS = (
    "event-r1500_t06-0ddd477d24b1364d",
    "event-r1500_t06-84cb252a6877d2d5",
    "event-r1500_t06-ef20fd746737f4ea",
    "event-r1500_t06-9e5bf1d807f9d61a",
    "event-r1500_t06-548ca9e284d1a330",
    "event-r1500_t06-040b1a186d857b11",
    "event-r1500_t06-09c2d54e2d8fb5dd",
)
FROZEN_CALIBRATION_ORDER = (
    "event-r1500_t06-0ddd477d24b1364d",
    "event-r1500_t06-ef20fd746737f4ea",
    "event-r1500_t06-040b1a186d857b11",
    "event-r1500_t06-09c2d54e2d8fb5dd",
    "event-r1500_t06-9e5bf1d807f9d61a",
    "event-r1500_t06-84cb252a6877d2d5",
    "event-r1500_t06-548ca9e284d1a330",
)
UNOBSERVED_EVENT_IDS = (
    "event-r1500_t06-1f8f72e78d63b0ee",
    "event-r1500_t06-ab8e9016ae0d3154",
)

VISIBLE_BURN_SCAR_CODES = (
    "yes",
    "no",
    "ambiguous",
    "unobserved",
)
SCAR_CONFIDENCE_CODES = (
    "high",
    "medium",
    "low",
    "not_applicable",
)
EVENT_ASSOCIATION_CODES = (
    "likely",
    "possible",
    "unlikely",
    "indeterminate",
)
COMPETING_LAND_CHANGE_CODES = (
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
)
MODE_AGREEMENT_CODES = (
    "agree",
    "partially_agree",
    "disagree",
    "selected_pair_only",
    "window_median_only",
    "unavailable",
)
REVIEW_STATUS_CODES = (
    "pending",
    "pass_a_complete",
    "pass_b_complete",
    "needs_adjudication",
    "unobserved",
    "excluded_with_reason",
)
REVIEWER_TYPE_CODES = ("human", "ai_assisted")
REVIEWER_EXPERTISE_CODES = ("novice", "trained", "domain_expert", "not_applicable")
LABEL_STATUS_CODES = ("human_observation", "provisional_pseudolabel")
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
ROUND_STATUS_CODES = ("open", "closed")
OBSERVABILITY_STATUS_CODES = ("observable", "unobserved")

CALIBRATION_SEED_COLUMNS = (
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
UNOBSERVED_SEED_COLUMNS = (
    "event_id",
    "observability_status",
    "exclusion_reason",
    "protocol_version",
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

LEGACY_EXPORT_COLUMNS = (
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


def deterministic_calibration_order(seed: int = RANDOMIZATION_SEED) -> tuple[str, ...]:
    """Return the frozen order used by the seed queue."""

    if seed == RANDOMIZATION_SEED:
        return FROZEN_CALIBRATION_ORDER
    values = sorted(CALIBRATION_EVENT_IDS)
    random.Random(seed).shuffle(values)
    return tuple(values)


def expected_panel_paths(event_id: str) -> tuple[str, str]:
    base = f"outputs/review_upload_level2/{event_id}"
    return (
        f"{base}_selected_pair_cs050_level2_panel.png",
        f"{base}_temporal_robustness_level2.png",
    )


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS review_rounds (
    round_id TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    quicklook_version TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ({_sql_values(ROUND_STATUS_CODES)}))
);

CREATE TABLE IF NOT EXISTS review_items (
    round_id TEXT NOT NULL,
    randomized_order INTEGER NOT NULL CHECK (randomized_order >= 1),
    event_id TEXT NOT NULL,
    multispectral_panel_path TEXT NOT NULL,
    temporal_panel_path TEXT NOT NULL,
    observability_status TEXT NOT NULL
        CHECK (observability_status IN ({_sql_values(OBSERVABILITY_STATUS_CODES)})),
    PRIMARY KEY (round_id, event_id),
    UNIQUE (round_id, randomized_order),
    FOREIGN KEY (round_id) REFERENCES review_rounds(round_id)
);

CREATE TABLE IF NOT EXISTS unobserved_events (
    event_id TEXT PRIMARY KEY,
    observability_status TEXT NOT NULL
        CHECK (observability_status = 'unobserved'),
    exclusion_reason TEXT NOT NULL CHECK (length(trim(exclusion_reason)) > 0),
    protocol_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL CHECK (length(trim(reviewer_id)) > 0),
    reviewer_type TEXT NOT NULL DEFAULT 'human'
        CHECK (reviewer_type IN ({_sql_values(REVIEWER_TYPE_CODES)})),
    reviewer_model TEXT,
    reviewer_expertise TEXT
        CHECK (reviewer_expertise IS NULL OR reviewer_expertise IN ({_sql_values(REVIEWER_EXPERTISE_CODES)})),
    label_status TEXT NOT NULL DEFAULT 'human_observation'
        CHECK (label_status IN ({_sql_values(LABEL_STATUS_CODES)})),
    pass_a_visible_burn_scar TEXT
        CHECK (pass_a_visible_burn_scar IS NULL OR pass_a_visible_burn_scar IN ({_sql_values(VISIBLE_BURN_SCAR_CODES)})),
    pass_a_scar_confidence TEXT
        CHECK (pass_a_scar_confidence IS NULL OR pass_a_scar_confidence IN ({_sql_values(SCAR_CONFIDENCE_CODES)})),
    pass_a_event_association TEXT
        CHECK (pass_a_event_association IS NULL OR pass_a_event_association IN ({_sql_values(EVENT_ASSOCIATION_CODES)})),
    pass_a_competing_land_change TEXT
        CHECK (pass_a_competing_land_change IS NULL OR pass_a_competing_land_change IN ({_sql_values(COMPETING_LAND_CHANGE_CODES)})),
    observation_limitation TEXT
        CHECK (observation_limitation IS NULL OR observation_limitation IN ({_sql_values(OBSERVATION_LIMITATION_CODES)})),
    pass_a_notes TEXT,
    pass_a_saved_at TEXT,
    pass_a_revision INTEGER NOT NULL DEFAULT 0 CHECK (pass_a_revision >= 0),
    pass_b_mode_agreement TEXT
        CHECK (pass_b_mode_agreement IS NULL OR pass_b_mode_agreement IN ({_sql_values(MODE_AGREEMENT_CODES)})),
    pass_b_confidence_after TEXT
        CHECK (pass_b_confidence_after IS NULL OR pass_b_confidence_after IN ({_sql_values(SCAR_CONFIDENCE_CODES)})),
    pass_b_requires_adjudication INTEGER
        CHECK (pass_b_requires_adjudication IS NULL OR pass_b_requires_adjudication IN (0, 1)),
    pass_b_notes TEXT,
    pass_b_saved_at TEXT,
    pass_b_revision INTEGER NOT NULL DEFAULT 0 CHECK (pass_b_revision >= 0),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ({_sql_values(REVIEW_STATUS_CODES)})),
    exclusion_reason TEXT,
    adjudication_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (round_id, event_id, reviewer_id),
    FOREIGN KEY (round_id, event_id) REFERENCES review_items(round_id, event_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS review_items_no_update
BEFORE UPDATE ON review_items
BEGIN
    SELECT RAISE(ABORT, 'review_items are frozen');
END;

CREATE TRIGGER IF NOT EXISTS review_items_no_delete
BEFORE DELETE ON review_items
BEGIN
    SELECT RAISE(ABORT, 'review_items are frozen');
END;
"""
