"""Import externally returned blind AI calibration JSON files."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_ai_calibration import cli_import  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(cli_import())
