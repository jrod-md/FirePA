"""Build the local calibration-7 window_median review asset package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.window_median_review_asset import (  # noqa: E402
    CASE_SET,
    build_pilot,
    verify_pilot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the frozen seven-case window_median review asset pilot locally.")
    parser.add_argument("--case-set", choices=(CASE_SET,), default=CASE_SET)
    parser.add_argument("--dry-run", action="store_true", help="Validate sources and compose in memory without writing outputs.")
    parser.add_argument("--verify-only", action="store_true", help="Read and verify the existing package without writing anything.")
    parser.add_argument("--resume", action="store_true", help="Reuse only existing assets whose hashes and identity still match.")
    parser.add_argument("--no-earth-engine", action="store_true", help="Assert that this pilot must remain local-only (the default implementation is local-only).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.verify_only:
            result = verify_pilot(ROOT)
        else:
            result = build_pilot(ROOT, resume=args.resume, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("status") in {"pass", "pilot_pass", "dry_run_pass"} else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "earth_engine_queries_made": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
