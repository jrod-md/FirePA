from __future__ import annotations

import inspect
from pathlib import Path

from fuegopa import human_review_app as app
from fuegopa.human_review_schema import (
    COMPETING_LAND_CHANGE_CODES,
    EVENT_ASSOCIATION_CODES,
    MODE_AGREEMENT_CODES,
    REVIEW_STATUS_CODES,
    SCAR_CONFIDENCE_CODES,
    VISIBLE_BURN_SCAR_CODES,
)


ROOT = Path(__file__).resolve().parents[1]


def test_app_is_importable_without_streamlit_and_has_local_entrypoint():
    assert callable(app.run_app)
    wrapper = (ROOT / "scripts" / "run_human_review_app.py").read_text(encoding="utf-8")
    assert "run_app()" in wrapper
    assert "localhost" not in wrapper or "streamlit" in wrapper


def test_stable_codes_are_exact_and_ui_labels_are_not_storage_codes():
    assert set(VISIBLE_BURN_SCAR_CODES) == {"yes", "no", "ambiguous", "unobserved"}
    assert set(SCAR_CONFIDENCE_CODES) == {"high", "medium", "low", "not_applicable"}
    assert set(EVENT_ASSOCIATION_CODES) == {"likely", "possible", "unlikely", "indeterminate"}
    assert set(COMPETING_LAND_CHANGE_CODES) == {
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
    assert set(MODE_AGREEMENT_CODES) == {
        "agree",
        "partially_agree",
        "disagree",
        "selected_pair_only",
        "window_median_only",
        "unavailable",
    }
    assert set(REVIEW_STATUS_CODES) == {
        "pending",
        "pass_a_complete",
        "pass_b_complete",
        "needs_adjudication",
        "unobserved",
        "excluded_with_reason",
    }
    assert all(code in app.CODE_LABELS["visible_burn_scar"] for code in VISIBLE_BURN_SCAR_CODES)
    assert app.CODE_LABELS["visible_burn_scar"]["yes"] != "yes"


def test_pass_a_only_shows_multispectral_and_pass_b_is_gated_after_a():
    source = inspect.getsource(app.run_app)
    temporal_call = 'st.image(str(root_path / item["temporal_panel_path"])'
    gate = 'if review and review.get("pass_a_saved_at") and review.get("review_status") != "unobserved":'
    assert temporal_call in source
    assert gate in source
    assert source.index(gate) < source.index(temporal_call)
    assert "pass_a_saved_at" in source
    assert 'item["multispectral_panel_path"]' in source


def test_pass_a_is_locked_and_amendment_is_explicit_and_audited():
    source = inspect.getsource(app)
    assert "Amend Pass A" in source
    assert "disabled=True" in source
    assert "amendment_reason" in source
    assert "audit" in source.lower()
    assert "st.selectbox" in source
    assert "st.text_input(\"Reviewer ID (obligatorio)\"" in source


def test_ui_and_persistence_are_science_only():
    source = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "src/fuegopa/human_review_schema.py",
            "src/fuegopa/human_review_store.py",
            "src/fuegopa/human_review_app.py",
        )
    ).lower()
    for prohibited in ("significant_burn", "model_score", "predicted_class", "expected_class", "frp"):
        assert prohibited not in source
    assert "st.metric" not in source
    assert "st.dataframe" not in source


def test_sqlite_outputs_are_ignored_and_command_is_local_only():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/*" in gitignore
    docs_path = ROOT / "docs" / "HUMAN_REVIEW_TOOL.md"
    if docs_path.exists():
        docs = docs_path.read_text(encoding="utf-8")
        assert "streamlit run scripts/run_human_review_app.py" in docs
        assert "127.0.0.1" in docs or "localhost" in docs
