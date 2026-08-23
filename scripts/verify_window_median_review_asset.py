"""Read-only verifier for the separate calibration-7 window_median package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.window_median_review_asset import CASE_SET, verify_pilot  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the local window_median calibration package without writing.")
    parser.add_argument("--case-set", choices=(CASE_SET,), default=CASE_SET)
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    result = verify_pilot(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
