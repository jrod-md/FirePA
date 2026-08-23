"""Verify the ignored final FirePA scientific diagnostics bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.final_scientific_report import verify_final_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica hashes y figuras del bundle científico final.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/final_scientific_report",
    )
    args = parser.parse_args(argv)
    result = verify_final_bundle(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
