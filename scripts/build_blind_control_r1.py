"""Build the independent blind control R1 packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_control_round import build_blind_control_packages  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--source-pass-a-zip", type=Path)
    parser.add_argument("--source-pass-b-zip", type=Path)
    args = parser.parse_args(argv)
    result = build_blind_control_packages(
        root=ROOT,
        output_root=args.output_root,
        source_pass_a_zip=args.source_pass_a_zip,
        source_pass_b_zip=args.source_pass_b_zip,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
