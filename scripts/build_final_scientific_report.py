"""Build the ignored final FirePA scientific diagnostics bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.final_scientific_report import (  # noqa: E402
    analyze_final_pilot,
    write_final_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Construye los diagnósticos científicos finales del piloto FirePA "
            "usando únicamente artefactos locales congelados."
        )
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/final_scientific_report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        analysis = analyze_final_pilot(root)
        manifest = write_final_bundle(analysis, args.output_dir)
        result = {
            "status": "pass",
            "analysis_version": analysis["analysis_version"],
            "output_dir": str(args.output_dir.resolve()),
            "counts": analysis["counts"],
            "picachos_category": analysis["picachos_diagnostics"]["classification"]["category"],
            "manifest_file_count": len(manifest["files"]),
            "figures": [row["path"] for row in manifest["files"] if row["path"].endswith(".png")],
            "network_access": False,
            "earth_engine_queries_made": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "network_access": False,
                    "earth_engine_queries_made": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
