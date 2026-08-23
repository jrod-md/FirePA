"""Streamlit entry point for the local FirePA human-review tool."""

from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.human_review_app import run_app  # noqa: E402


def build_formal_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lanzador local de un único slot formal autorizado.")
    parser.add_argument("--formal-round", action="store_true")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--slot-id", required=True, choices=("HUMAN_SLOT_A", "HUMAN_SLOT_B"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--database", type=Path, default=ROOT / "outputs/human_review/firepa_human_review.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/human_review/formal_review_28")
    return parser


def _run_formal_from_cli(argv: list[str]) -> None:
    args = build_formal_parser().parse_args(argv)
    from fuegopa.formal_review_app import run_formal_app  # noqa: E402

    # The token is process-local, generated in memory, never logged and never
    # persisted.  It is only a local supervised session nonce.
    run_formal_app(
        round_id=args.round_id,
        slot_id=args.slot_id,
        profile_id=args.profile_id,
        session_token=secrets.token_urlsafe(32),
        db_path=args.database,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    if "--formal-round" in sys.argv:
        marker = sys.argv.index("--formal-round")
        _run_formal_from_cli(sys.argv[marker:])
    else:
        run_app()
