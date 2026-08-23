"""Build the local external_reference_check_v1 output bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.external_reference import (  # noqa: E402
    INPUT_EVENTS_RELATIVE,
    OPTICAL_COHORT_RELATIVE,
    OUTPUT_RELATIVE,
    analyze_external_references,
    write_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compara dos referencias externas proporcionadas por el investigador "
            "contra los 611 clusters r1500_t06 congelados, sin reclustering ni red."
        )
    )
    parser.add_argument(
        "--input-events",
        type=Path,
        default=ROOT / INPUT_EVENTS_RELATIVE,
        help="Tabla local congelada de eventos r1500_t06.",
    )
    parser.add_argument(
        "--optical-cohort",
        type=Path,
        default=ROOT / OPTICAL_COHORT_RELATIVE,
        help="Cohorte óptica local existente de 30 eventos.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / OUTPUT_RELATIVE,
        help="Directorio local ignorado por Git para los outputs.",
    )
    parser.add_argument(
        "--no-visualizations",
        action="store_true",
        help="No crear las tres visualizaciones SVG descriptivas.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = analyze_external_references(
            input_events_path=args.input_events,
            optical_cohort_path=args.optical_cohort,
        )
        manifest = write_outputs(
            result,
            output_dir=args.output_dir,
            input_events_path=args.input_events,
            optical_cohort_path=args.optical_cohort,
            include_visualizations=not args.no_visualizations,
        )
        summary = {
            "status": "pass",
            "analysis_version": result["analysis_version"],
            "cluster_count": result["input"]["cluster_count"],
            "reference_match_counts": {
                row["reference_id"]: row["match_count"]
                for row in result["reference_summary"]
            },
            "manifest_file_count": len(manifest["files"]),
            "output_dir": str(args.output_dir),
            "formal_review_status": result["formal_review"]["formal_review_status"],
            "execution_authorized": result["formal_review"]["execution_authorized"],
            "supervised_modeling_gate": result["supervised_modeling"]["supervised_modeling_gate"],
            "earth_engine_queries_made": result["scope"]["earth_engine_queries_made"],
            "network_access": result["scope"]["network_access"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "earth_engine_queries_made": False,
                    "network_access": False,
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
