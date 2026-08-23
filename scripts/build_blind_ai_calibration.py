"""Generate and validate the local anonymized blind AI calibration packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fuegopa.blind_ai_calibration import build_blind_packages  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--write-checkpoint", action="store_true")
    args = parser.parse_args()
    result = build_blind_packages(
        root=ROOT,
        output_root=args.output_root,
        write_checkpoint=args.write_checkpoint,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
