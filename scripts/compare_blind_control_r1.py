"""Compare two independent blind control R1 response pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_control_round import (  # noqa: E402
    compare_blind_control_results,
    render_control_comparison_markdown,
)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-a-pass-a", type=Path, required=True)
    parser.add_argument("--reviewer-a-pass-b", type=Path, required=True)
    parser.add_argument("--reviewer-b-pass-a", type=Path, required=True)
    parser.add_argument("--reviewer-b-pass-b", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)
    sqlite_before = _sha256(args.database) if args.database is not None else None
    result = compare_blind_control_results(
        args.reviewer_a_pass_a,
        args.reviewer_a_pass_b,
        args.reviewer_b_pass_a,
        args.reviewer_b_pass_b,
        report=args.report,
        database=args.database,
    )
    sqlite_after = _sha256(args.database) if args.database is not None else None
    if args.database is not None:
        result["sqlite_sha256_before"] = sqlite_before
        result["sqlite_sha256_after"] = sqlite_after
        result["sqlite_byte_identical"] = sqlite_before == sqlite_after
        if not result["sqlite_byte_identical"]:
            result["status"] = "fail"
            result.setdefault("errors", []).append("SQLite changed during read-only comparison")
    if args.markdown_output is not None and result["status"] == "pass":
        markdown_path = args.markdown_output.resolve()
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_control_comparison_markdown(result), encoding="utf-8", newline="\n")
        result["markdown_output"] = markdown_path
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
