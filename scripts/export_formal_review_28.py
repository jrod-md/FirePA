"""Export empty formal-review preparation projections without executing review."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.formal_review import export_formal_preparation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta únicamente la preparación vacía de formal_review_28.")
    parser.add_argument("--database", type=Path, default=ROOT / "outputs/human_review/firepa_human_review.sqlite3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/human_review/formal_review_28/exports")
    args = parser.parse_args(argv)
    paths = export_formal_preparation(db_path=args.database, output_dir=args.output_dir)
    for kind, path in paths.items():
        print(f"{kind}={path}")
    print("review_rows_exported=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
