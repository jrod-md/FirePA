"""Configuration for the reproducible FuegoPA pipeline.

The module intentionally reads configuration from explicit arguments or the
process environment. It does not load secrets from source files and does not
provide a default external endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _resolve_path(value: str | None, default: Path, project_root: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


@dataclass(frozen=True)
class Settings:
    """Filesystem and optional FIRMS acquisition settings."""

    project_root: Path
    raw_dir: Path
    interim_dir: Path
    processed_dir: Path
    outputs_dir: Path
    raw_path: Path
    processed_path: Path
    report_path: Path
    input_path: Path | None
    firms_url: str | None
    firms_map_key: str | None

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        project_root: str | Path | None = None,
    ) -> "Settings":
        env = os.environ if environ is None else environ
        root_value = env.get("FUEGOPA_PROJECT_ROOT")
        root = Path(project_root or root_value or Path.cwd()).expanduser().resolve()

        raw_dir = _resolve_path(env.get("FUEGOPA_RAW_DIR"), root / "data" / "raw", root)
        interim_dir = _resolve_path(
            env.get("FUEGOPA_INTERIM_DIR"), root / "data" / "interim", root
        )
        processed_dir = _resolve_path(
            env.get("FUEGOPA_PROCESSED_DIR"), root / "data" / "processed", root
        )
        outputs_dir = _resolve_path(env.get("FUEGOPA_OUTPUTS_DIR"), root / "outputs", root)

        raw_path = _resolve_path(
            env.get("FUEGOPA_RAW_PATH"), raw_dir / "firms_input.csv", root
        )
        processed_path = _resolve_path(
            env.get("FUEGOPA_PROCESSED_PATH"),
            processed_dir / "firms_normalized.csv",
            root,
        )
        report_path = _resolve_path(
            env.get("FUEGOPA_REPORT_PATH"),
            outputs_dir / "firms_quality_report.json",
            root,
        )
        input_value = env.get("FIRMS_INPUT_PATH")
        input_path = _resolve_path(input_value, root / "__no_local_input__.csv", root)
        if not input_value:
            input_path = None

        return cls(
            project_root=root,
            raw_dir=raw_dir,
            interim_dir=interim_dir,
            processed_dir=processed_dir,
            outputs_dir=outputs_dir,
            raw_path=raw_path,
            processed_path=processed_path,
            report_path=report_path,
            input_path=input_path,
            firms_url=env.get("FIRMS_URL") or None,
            firms_map_key=env.get("FIRMS_MAP_KEY") or None,
        )

    def create_directories(self) -> None:
        """Create the pipeline directories without creating data files."""

        for directory in (
            self.raw_dir,
            self.interim_dir,
            self.processed_dir,
            self.outputs_dir,
            self.raw_path.parent,
            self.processed_path.parent,
            self.report_path.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)
