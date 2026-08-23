"""Prepare the empty, blinded formal review round for 28 observable events."""

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
    FORMAL_QUEUE_PATH,
    FORMAL_UNOBSERVED_PATH,
    FormalReviewError,
    prepare_formal_round,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara sin ejecutar la ronda formal ciega de revisión humana de 28 eventos."
    )
    parser.add_argument("--database", type=Path, default=ROOT / "outputs/human_review/firepa_human_review.sqlite3")
    parser.add_argument("--queue", type=Path, default=FORMAL_QUEUE_PATH)
    parser.add_argument("--unobserved", type=Path, default=FORMAL_UNOBSERVED_PATH)
    parser.add_argument("--protocol", type=Path, default=FORMAL_PROTOCOL_PATH)
    parser.add_argument("--output-dir", type=Path, default=FORMAL_OUTPUT_DIR)
    parser.add_argument("--seed-file", type=Path, default=None)
    parser.add_argument("--private-seed", default=None, help="Semilla administrativa; no se imprime ni se versiona.")
    parser.add_argument("--base-head", default="f302139")
    parser.add_argument(
        "--reconcile-protocol-hash",
        action="store_true",
        help="Autoriza únicamente la reconciliación auditada del hash obsoleto con cero resultados formales.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = prepare_formal_round(
            root=ROOT,
            db_path=args.database,
            queue_path=args.queue,
            unobserved_path=args.unobserved,
            protocol_path=args.protocol,
            output_dir=args.output_dir,
            seed_path=args.seed_file,
            supplied_seed=args.private_seed,
            base_head=args.base_head,
            reconcile_protocol_hash=args.reconcile_protocol_hash,
        )
    except FormalReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"round_id={result.round_id}")
    print(f"observable_count={result.observable_count}")
    print(f"unobserved_count={result.unobserved_count}")
    print(f"assignment_count={result.assignment_count}")
    print(f"protocol_sha256={result.protocol_sha256}")
    print(f"input_manifest_sha256={result.input_manifest_sha256}")
    print(f"private_seed_sha256={result.private_seed_sha256}")
    for path, digest in zip(result.package_paths, result.package_hashes):
        print(f"package={path} sha256={digest}")
    print("formal_review_executed=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
