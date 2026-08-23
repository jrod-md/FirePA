"""Rebuild the seven calibration Quicklook v2 sheets from local artifacts only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fuegopa.dnbr_quicklook_v2 import (  # noqa: E402
    CALIBRATION_EVENT_IDS,
    QUICKLOOK_VERSION,
    build_quicklook_v2_report,
    scientific_bundle_integrity,
    write_quicklook_v2_outputs,
    write_quicklook_v2_report,
)
from fuegopa.sentinel2_dnbr import (  # noqa: E402
    DnbrValidationError,
    load_dnbr_inputs,
    read_utf8_csv,
)


def _path(value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else ROOT / candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconstrucción local de Quicklook v2 para siete eventos de calibración."
    )
    parser.add_argument(
        "--event-id",
        action="append",
        dest="event_ids",
        help="Event ID de calibración; se puede repetir. Por defecto usa exactamente los siete aprobados.",
    )
    parser.add_argument("--max-events", type=int, help="Límite dentro de la lista de calibración, para una prueba local.")
    parser.add_argument("--source-dir", default="outputs/figures/sentinel2_dnbr/events")
    parser.add_argument("--output-dir", default="outputs/figures/sentinel2_dnbr_v2/events")
    parser.add_argument("--review-upload-dir", default="outputs/review_upload_v2")
    parser.add_argument("--report-json", default="outputs/quicklook_v2_report.json")
    parser.add_argument("--report-markdown", default="outputs/quicklook_v2_report.md")
    parser.add_argument("--pre-manifest", default="outputs/manifests/firepa_active_bundle_2026-07-21.json")
    parser.add_argument("--pilot-events", default="data/processed/sentinel2_observability_pilot_events.csv")
    parser.add_argument("--membership", default="data/processed/firms_cocle_2025_event_membership.csv")
    parser.add_argument("--events", default="data/processed/firms_cocle_2025_events_provisional.csv")
    parser.add_argument("--selection", default="outputs/sentinel2_event_pair_selection.csv")
    parser.add_argument("--scene-inventory", default="data/interim/sentinel2_scene_inventory.csv")
    parser.add_argument("--aoi-inventory", default="data/interim/sentinel2_aoi_inventory.csv")
    parser.add_argument("--metrics", default="data/interim/sentinel2_dnbr_event_metrics.csv")
    return parser


def _metrics_by_event(rows: list[dict[str, str]], event_id: str, mode: str) -> dict[str, str] | None:
    for row in rows:
        if (
            row.get("event_id") == event_id
            and row.get("analysis_mode") == mode
            and str(row.get("cloud_threshold", "")) in {"0.5", "0.50", "0.500"}
        ):
            return row
    return None


def _selected_events(requested: list[str] | None, max_events: int | None) -> list[str]:
    selected = list(requested or CALIBRATION_EVENT_IDS)
    unknown = sorted(set(selected) - set(CALIBRATION_EVENT_IDS))
    if unknown:
        raise DnbrValidationError(
            "Quicklook v2 solo admite los siete event_id de calibración: " + ", ".join(unknown)
        )
    if max_events is not None:
        if max_events <= 0:
            raise DnbrValidationError("max-events debe ser positivo")
        selected = selected[:max_events]
    if not selected:
        raise DnbrValidationError("no hay eventos de calibración seleccionados")
    return selected


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event_ids = _selected_events(args.event_ids, args.max_events)
        inputs = load_dnbr_inputs(
            pilot_path=_path(args.pilot_events),
            events_path=_path(args.events),
            membership_path=_path(args.membership),
            selection_path=_path(args.selection),
            scene_inventory_path=_path(args.scene_inventory),
            aoi_inventory_path=_path(args.aoi_inventory),
        )
        event_lookup = {event.event_id: event for event in inputs.processable}
        missing_inputs = sorted(set(event_ids) - set(event_lookup))
        if missing_inputs:
            raise DnbrValidationError(
                "Los eventos de calibración no son procesables bajo la selección local: "
                + ", ".join(missing_inputs)
            )
        metrics_rows = read_utf8_csv(_path(args.metrics))
        if len(metrics_rows) != 56:
            raise DnbrValidationError(f"Las métricas dNBR activas deben tener 56 filas; recibidas {len(metrics_rows)}")
        results: list[dict[str, object]] = []
        for event_id in event_ids:
            selected_metrics = _metrics_by_event(metrics_rows, event_id, "selected_pair")
            window_metrics = _metrics_by_event(metrics_rows, event_id, "window_median")
            if selected_metrics is None or window_metrics is None:
                raise DnbrValidationError(f"Faltan filas métricas 0.50 para {event_id}")
            try:
                results.append(
                    write_quicklook_v2_outputs(
                        event_lookup[event_id],
                        selected_metrics=selected_metrics,
                        window_metrics=window_metrics,
                        source_dir=_path(args.source_dir),
                        output_dir=_path(args.output_dir),
                        review_upload_dir=_path(args.review_upload_dir),
                        root=ROOT,
                    )
                )
                print(f"quicklook_v2_generated={event_id}")
            except Exception as exc:
                result = {
                    "event_id": event_id,
                    "status": "failed",
                    "quicklook_version": QUICKLOOK_VERSION,
                    "error": f"{type(exc).__name__}: {exc}",
                    "scientific_outputs_modified": False,
                    "earth_engine_queries_made": False,
                }
                results.append(result)
                print(f"quicklook_v2_failed={event_id}: {exc}", file=sys.stderr)
        integrity = scientific_bundle_integrity(_path(args.pre_manifest), root=ROOT)
        report = build_quicklook_v2_report(
            results,
            requested_event_ids=event_ids,
            scientific_integrity=integrity,
        )
        write_quicklook_v2_report(_path(args.report_json), _path(args.report_markdown), report)
        print(f"quicklook_v2_report={_path(args.report_json)}")
        return 1 if report["failed_count"] else 0
    except (OSError, ValueError, DnbrValidationError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
