"""Freeze r1500_t06 outputs and prepare the Sentinel-2 observability pilot.

This script consumes existing clustering CSVs.  It does not rerun the
clustering algorithm and does not make network or Sentinel-2 requests.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fuegopa.provisional import (  # noqa: E402
    EXPECTED_DETECTION_COUNT,
    EXPECTED_EVENT_COUNT,
    FROZEN_CONFIGURATION_ID,
    PILOT_SAMPLE_SEED,
    PILOT_COLUMNS,
    freeze_from_outputs,
    read_csv_rows,
    select_observability_pilot,
    write_csv,
    write_empty_observability_schema,
    write_json,
    write_sampling_markdown,
)


def _path_from_cli(value: str | None, default: Path) -> Path:
    return (ROOT / value).resolve() if value else default


def _default_source_dir() -> Path:
    configured = os.getenv("FUEGOPA_PROVISIONAL_SOURCE_DIR")
    if configured:
        return _path_from_cli(configured, ROOT / configured)
    candidates = (
        ROOT / "outputs" / "clustering" / "configurations" / FROZEN_CONFIGURATION_ID,
        ROOT / "outputs" / "clustering" / FROZEN_CONFIGURATION_ID,
    )
    for candidate in candidates:
        if (candidate / "membership.csv").exists() and (candidate / "events.csv").exists():
            return candidate
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Congela las tablas existentes de r1500_t06 y genera el piloto "
            "estructural de observabilidad Sentinel-2."
        )
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Directorio que contiene membership.csv y events.csv; también FUEGOPA_PROVISIONAL_SOURCE_DIR.",
    )
    parser.add_argument(
        "--membership-output",
        default="data/processed/firms_cocle_2025_event_membership.csv",
    )
    parser.add_argument(
        "--events-output",
        default="data/processed/firms_cocle_2025_events_provisional.csv",
    )
    parser.add_argument(
        "--pilot-output",
        default="data/processed/sentinel2_observability_pilot_events.csv",
    )
    parser.add_argument(
        "--sampling-json-output",
        default="outputs/sentinel2_observability_sampling_report.json",
    )
    parser.add_argument(
        "--sampling-markdown-output",
        default="outputs/sentinel2_observability_sampling_report.md",
    )
    parser.add_argument(
        "--observability-schema-output",
        default="data/interim/sentinel2_observability.csv",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=int(os.getenv("FUEGOPA_PROVISIONAL_SAMPLE_SIZE", "30")),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.getenv("FUEGOPA_PROVISIONAL_SEED", str(PILOT_SAMPLE_SEED))),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_dir = _path_from_cli(args.source_dir, _default_source_dir())
    membership_output = _path_from_cli(args.membership_output, ROOT / args.membership_output)
    events_output = _path_from_cli(args.events_output, ROOT / args.events_output)
    pilot_output = _path_from_cli(args.pilot_output, ROOT / args.pilot_output)
    sampling_json_output = _path_from_cli(
        args.sampling_json_output, ROOT / args.sampling_json_output
    )
    sampling_markdown_output = _path_from_cli(
        args.sampling_markdown_output, ROOT / args.sampling_markdown_output
    )
    observability_schema_output = _path_from_cli(
        args.observability_schema_output, ROOT / args.observability_schema_output
    )

    try:
        freeze_report = freeze_from_outputs(
            source_dir,
            membership_output,
            events_output,
            expected_detection_count=EXPECTED_DETECTION_COUNT,
            expected_event_count=EXPECTED_EVENT_COUNT,
        )
        frozen_events = read_csv_rows(events_output)
        pilot_rows, sampling_report = select_observability_pilot(
            frozen_events,
            sample_size=args.sample_size,
            seed=args.seed,
        )
        sampling_report = {
            **sampling_report,
            "frozen_outputs": {
                "membership_output": str(membership_output),
                "events_output": str(events_output),
                **freeze_report,
            },
        }
        write_csv(pilot_output, PILOT_COLUMNS, pilot_rows)
        write_json(sampling_json_output, sampling_report)
        write_sampling_markdown(sampling_markdown_output, sampling_report)
        write_empty_observability_schema(observability_schema_output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"configuration_id={freeze_report['configuration_id']}")
    print(f"source_dir={source_dir}")
    print(f"event_count={freeze_report['event_count']}")
    print(f"detection_count={freeze_report['detection_count']}")
    print(f"singleton_count={freeze_report['singleton_count']}")
    print(f"multi_detection_event_count={freeze_report['multi_detection_event_count']}")
    print(f"pilot_count={len(pilot_rows)}")
    print(f"membership_output={membership_output}")
    print(f"events_output={events_output}")
    print(f"pilot_output={pilot_output}")
    print(f"sampling_json_output={sampling_json_output}")
    print(f"sampling_markdown_output={sampling_markdown_output}")
    print(f"observability_schema_output={observability_schema_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
