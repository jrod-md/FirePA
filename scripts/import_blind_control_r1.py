"""Validate two independent blind control R1 response pairs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_control_round import import_blind_control_results  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-a-pass-a", type=Path, required=True)
    parser.add_argument("--reviewer-a-pass-b", type=Path, required=True)
    parser.add_argument("--reviewer-b-pass-a", type=Path, required=True)
    parser.add_argument("--reviewer-b-pass-b", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--database", type=Path, default=ROOT / "outputs" / "human_review" / "firepa_human_review.sqlite3")
    parser.add_argument("--output", type=Path, help="Optional new normalized result path; never SQLite")
    args = parser.parse_args(argv)
    result = import_blind_control_results(
        args.reviewer_a_pass_a,
        args.reviewer_a_pass_b,
        args.reviewer_b_pass_a,
        args.reviewer_b_pass_b,
        dry_run=args.dry_run,
        report=args.report,
        output=args.output,
        database=args.database,
        root=ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
