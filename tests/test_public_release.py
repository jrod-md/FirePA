from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_public_release as build_public_release_module  # noqa: E402
from build_public_release import build_package, public_files, sha256_file  # noqa: E402
from verify_public_release_package import verify_package  # noqa: E402


@pytest.fixture()
def public_package(tmp_path: Path) -> Path:
    output = tmp_path / "public-package"
    result = build_package(output, ROOT)
    assert result["deterministic"] is True
    return output


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_public_package_build_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = build_package(first, ROOT)
    second_result = build_package(second, ROOT)

    comparable_first = {key: value for key, value in first_result.items() if key != "output_dir"}
    comparable_second = {key: value for key, value in second_result.items() if key != "output_dir"}
    assert comparable_first == comparable_second
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    assert first_files == second_files == sorted(public_files() + ["manifest.json"])
    for relative in first_files:
        assert (first / relative).read_bytes() == (second / relative).read_bytes(), relative


def test_clean_public_package_passes_full_verifier(public_package: Path) -> None:
    report = verify_package(public_package, ROOT)
    assert report["ok"], report["errors"]
    assert report["event_count"] == 611
    assert report["reference_count"] == 2


def test_existing_negative_limitations_pass(public_package: Path) -> None:
    report = verify_package(public_package, ROOT)
    assert report["ok"], report["errors"]


def test_verifier_rejects_positive_project_summary_fire_claim(public_package: Path) -> None:
    path = public_package / "project-summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["definition"] = "FirePA detected 611 fires."
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("unsupported positive public claim" in error for error in report["errors"])


def test_verifier_rejects_positive_methodology_wildfire_claim(public_package: Path) -> None:
    path = public_package / "methodology.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["workflow"][0]["result"] = "FirePA confirmed wildfire classification."
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("unsupported positive public claim" in error for error in report["errors"])


def test_verifier_rejects_forbidden_event_field(public_package: Path) -> None:
    path = public_package / "events.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["features"][0]["properties"]["confirmed_fire"] = False
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("forbidden serialized field" in error for error in report["errors"])


def test_verifier_rejects_absolute_private_path(public_package: Path) -> None:
    path = public_package / "provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_artifacts"][0]["path"] = str(Path(Path.cwd().anchor) / "private" / "review.sqlite3")
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("absolute" in error for error in report["errors"])


def test_verifier_rejects_external_invariant_drift(public_package: Path) -> None:
    path = public_package / "external-references.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    guacamaya = next(
        feature for feature in payload["features"] if feature["properties"]["reference_id"] == "REFERENCE-002"
    )
    guacamaya["properties"]["official_match_count"] = 5
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("Guacamaya official match count mismatch" in error for error in report["errors"])


def test_verifier_rejects_event_order_drift(public_package: Path) -> None:
    path = public_package / "events.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["features"][0], payload["features"][1] = payload["features"][1], payload["features"][0]
    write_json(path, payload)

    report = verify_package(public_package, ROOT)
    assert not report["ok"]
    assert any("public event feature order drifted" in error for error in report["errors"])


def test_verifier_freeze_expectation_is_independent_of_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    incorrect_freeze = "0" * 40
    monkeypatch.setattr(build_public_release_module, "SCIENTIFIC_FREEZE_COMMIT", incorrect_freeze)
    drifted_package = tmp_path / "generator-with-freeze-drift"
    build_package(drifted_package, ROOT)

    report = verify_package(drifted_package, ROOT)
    assert not report["ok"]
    assert any("project freeze mismatch" in error for error in report["errors"])


def test_public_figures_match_frozen_sources(public_package: Path) -> None:
    for name in (
        "01_pipeline_overview.png",
        "02_cluster_distribution.png",
        "03_external_reference_map.png",
        "04_guacamaya_timeline.png",
        "05_guacamaya_frp_distribution.png",
        "06_los_picachos_diagnostic.png",
    ):
        assert sha256_file(public_package / "figures" / name) == sha256_file(
            ROOT / "outputs" / "final_scientific_report" / name
        )
