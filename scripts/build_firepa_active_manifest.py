"""Build the local, hash-only manifest for the active FirePA bundle.

The manifest records paths and metadata only. It never copies, rewrites, or
opens generated scientific files for anything other than hashing/metadata.
Generated manifests belong under ``outputs/manifests`` and are ignored by Git.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "outputs" / "manifests"
MANIFEST_STEM = "firepa_active_bundle_2026-07-21"


ACTIVE_PATTERNS = (
    "data/raw/**/*.csv",
    "data/raw/manifests/**/*.json",
    "data/processed/firms_cocle_2025_detections.csv",
    "data/processed/firms_cocle_2025_event_membership.csv",
    "data/processed/firms_cocle_2025_events_provisional.csv",
    "data/processed/sentinel2_observability_pilot_events.csv",
    "data/interim/sentinel2_*.csv",
    "data/interim/sentinel2_*.json",
    "data/interim/sentinel2_dnbr_cache/*.json",
    "data/interim/sentinel2_observability_cache/*.json",
    "outputs/clustering/r1500_t06/*.csv",
    "outputs/clustering/r1500_t06/*.json",
    "outputs/clustering/r1500_t06/*.md",
    "outputs/sentinel2_*.csv",
    "outputs/sentinel2_*.json",
    "outputs/sentinel2_*.md",
    "outputs/figures/sentinel2_dnbr/events/*",
    "outputs/review_upload/*.png",
    "scripts/run_sentinel2_dnbr.py",
    "scripts/build_firepa_active_manifest.py",
    "src/fuegopa/sentinel2_dnbr.py",
    "src/fuegopa/dnbr_quicklook.py",
    "tests/test_sentinel2_dnbr.py",
    "tests/test_dnbr_quicklook.py",
    "docs/SENTINEL2_DNBR_DESIGN.md",
    "README.md",
    "docs/PREFLIGHT.md",
    "PLAN.md",
    "CONTEXT.md",
    "docs/HANDOFF_FIREPA_2026-07-21.md",
    ".gitignore",
)


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _classification(relative_path: str) -> str:
    path = Path(relative_path)
    parts = path.parts
    if "tests" in parts:
        return "test"
    if path.suffix == ".py" or path.suffix == ".ps1":
        return "code"
    if path.suffix in {".md", ".gitignore"}:
        return "documentation"
    if parts and parts[0] == "data":
        if parts[1] == "raw":
            return "scientific_input"
        if parts[1] == "interim" and "cache" not in relative_path:
            if path.name in {
                "sentinel2_scene_inventory.csv",
                "sentinel2_aoi_inventory.csv",
                "sentinel2_observability.csv",
            }:
                return "scientific_input"
        return "scientific_output"
    if parts and parts[0] == "outputs":
        if "figures" in parts or "review_upload" in parts:
            return "visual_output"
        return "scientific_output"
    return "documentation"


def _iter_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in ACTIVE_PATTERNS:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: Path, timestamp: str) -> dict[str, object]:
    relative = path.relative_to(ROOT).as_posix()
    stat = path.stat()
    return {
        "path": relative,
        "size_bytes": stat.st_size,
        "sha256": _sha256(path),
        "timestamp_utc": timestamp,
        "classification": _classification(relative),
    }


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_manifest() -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = [_entry(path, timestamp) for path in _iter_paths()]
    return {
        "manifest_version": "firepa-active-bundle-v1",
        "generated_at_utc": timestamp,
        "repository": "FirePA/FuegoPA",
        "root_relative_to_checkout": ".",
        "commit_sha": _git_sha(),
        "pipeline_version": "fuegopa-sentinel2-dnbr-v3",
        "quicklook_version": "legacy-current-panel-v1 (source had no explicit version constant)",
        "scope": "Active scientific inputs/outputs and dNBR v3 code before Quicklook v2; no files copied.",
        "entry_count": len(entries),
        "entries": entries,
    }


def _sha_lines(manifest: dict[str, object]) -> Iterable[str]:
    for entry in manifest["entries"]:  # type: ignore[index]
        yield f"{entry['sha256']}  {entry['path']}"  # type: ignore[index]


def _markdown(manifest: dict[str, object]) -> str:
    entries = manifest["entries"]  # type: ignore[assignment]
    lines = [
        "# FirePA active bundle manifest",
        "",
        f"- Generated UTC: `{manifest['generated_at_utc']}`",
        f"- Commit SHA at capture: `{manifest['commit_sha']}`",
        f"- Pipeline version: `{manifest['pipeline_version']}`",
        f"- Current quicklook contract: `{manifest['quicklook_version']}`",
        f"- Entries: `{manifest['entry_count']}`",
        "",
        "This is a hash-only inventory. It does not copy or rewrite datasets, caches, checkpoints, images, CSVs, or JSON scientific outputs.",
        "",
        "| Path | Classification | Bytes | SHA-256 | Timestamp UTC |",
        "|---|---|---:|---|---|",
    ]
    for entry in entries:  # type: ignore[union-attr]
        lines.append(
            f"| `{entry['path']}` | `{entry['classification']}` | {entry['size_bytes']} | `{entry['sha256']}` | `{entry['timestamp_utc']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    manifest = build_manifest()
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    _write_text(
        MANIFEST_DIR / f"{MANIFEST_STEM}.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_text(
        MANIFEST_DIR / f"{MANIFEST_STEM}.sha256",
        "\n".join(_sha_lines(manifest)) + "\n",
    )
    _write_text(
        MANIFEST_DIR / f"{MANIFEST_STEM}.md",
        _markdown(manifest),
    )
    print(json.dumps({key: manifest[key] for key in ("generated_at_utc", "commit_sha", "entry_count", "pipeline_version", "quicklook_version")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
