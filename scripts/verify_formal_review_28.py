"""Read-only verifier for the prepared formal_review_28 administrative package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.formal_review import (  # noqa: E402
    FORMAL_OUTPUT_DIR,
    FORMAL_PROTOCOL_PATH,
    FormalReviewError,
    verify_formal_review_round,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verifica formal_review_28 sin escribir SQLite ni artefactos.")
    parser.add_argument("--database", type=Path, default=ROOT / "outputs/human_review/firepa_human_review.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=FORMAL_OUTPUT_DIR)
    parser.add_argument("--protocol", type=Path, default=FORMAL_PROTOCOL_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_formal_review_round(
            root=ROOT,
            db_path=args.database,
            output_dir=args.output_dir,
            protocol_path=args.protocol,
        )
    except (FormalReviewError, OSError, ValueError) as exc:
        print(f"verification_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not result.get("ok"):
        print("formal_review_28_integrity=FAIL")
        for error in result.get("errors", []):
            print(f"error={error}")
        return 1
    print("formal_review_28_integrity=OK")
    print(f"observable_count={result['observable_count']}")
    print(f"unobserved_count={result['unobserved_count']}")
    print(f"assignment_count={result['assignment_count']}")
    print(f"execution_authorized={result['execution_authorized']}")
    print(f"artifact_count={result.get('artifact_count', 'verified')}")
    print("read_only=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
