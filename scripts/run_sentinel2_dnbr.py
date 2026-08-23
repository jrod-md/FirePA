"""Run the bounded Sentinel-2 NBR/dNBR pilot.

The CLI is intentionally separate from the observability inventory runner.
It consumes the frozen local policy selection, processes only its 28 usable
events, and keeps full-scene downloads and automatic labels out of scope.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fuegopa.earth_engine import (  # noqa: E402
    EarthEngineConfigurationError,
    EarthEngineQueryError,
    exception_diagnostics,
    initialize_earth_engine,
    smoke_test,
)
from fuegopa.sentinel2_dnbr import (  # noqa: E402
    DEFAULT_MIN_VALID_OVERLAP_FRACTION,
    DNBR_PIPELINE_VERSION,
    DnbrValidationError,
    cache_path,
    cache_signature,
    default_dnbr_paths,
    execute_event,
    load_dnbr_inputs,
    load_event_cache,
    merge_event_rows,
    read_utf8_csv,
    rebuild_quicklook_from_artifacts,
    write_dnbr_outputs,
    write_event_cache,
    write_json_atomic,
)


def _path(value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else ROOT / candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Piloto acotado de NBR/dNBR sobre 28 eventos Sentinel-2 utilizables."
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Inicializa EE y confirma acceso a las dos colecciones.",
    )
    parser.add_argument("--event-id", help="Procesa un único evento procesable.")
    parser.add_argument("--max-events", type=int, help="Límite determinista para una prueba parcial.")
    parser.add_argument("--resume", action="store_true", help="Reutiliza caches exitosas compatibles.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ignora la cache de los eventos seleccionados y reemplaza sus outputs.",
    )
    parser.add_argument(
        "--confirm-overwrite",
        help="Debe ser exactamente OVERWRITE junto con --overwrite.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Requiere --event-id, conserva traceback seguro y detiene el lote en el primer fallo.",
    )
    parser.add_argument(
        "--rebuild-quicklooks",
        action="store_true",
        help="Reconstruye paneles desde los seis PNG locales sin inicializar Earth Engine.",
    )
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)
    parser.add_argument(
        "--min-valid-overlap-fraction",
        type=float,
        default=DEFAULT_MIN_VALID_OVERLAP_FRACTION,
        help="Umbral operativo explícito para publicar métricas dNBR.",
    )
    parser.add_argument(
        "--pilot-events",
        default="data/processed/sentinel2_observability_pilot_events.csv",
    )
    parser.add_argument(
        "--membership",
        default="data/processed/firms_cocle_2025_event_membership.csv",
    )
    parser.add_argument(
        "--events",
        default="data/processed/firms_cocle_2025_events_provisional.csv",
    )
    parser.add_argument(
        "--selection",
        default="outputs/sentinel2_event_pair_selection.csv",
    )
    parser.add_argument(
        "--scene-inventory",
        default="data/interim/sentinel2_scene_inventory.csv",
    )
    parser.add_argument(
        "--aoi-inventory",
        default="data/interim/sentinel2_aoi_inventory.csv",
    )
    return parser


_SECRET_RE = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)
_PROJECT_RE = re.compile(r"(?i)(\bprojects/)([A-Za-z0-9._-]+)")
_PROJECT_ASSIGNMENT_RE = re.compile(
    r"(?i)(\bproject(?:[_ -]?id)?\b\s*[:=]\s*)([A-Za-z0-9._-]+)"
)
_GEOMETRY_RE = re.compile(
    r"(?im)^([^\r\n]*(?:coordinates|geometry|geojson|polygon|multipolygon)\s*[:=]).*$"
)


def _sanitize_diagnostic(value: Any) -> str:
    text = str(value) or ""
    project = os.environ.get("EARTH_ENGINE_PROJECT", "")
    if project:
        text = text.replace(project, "<PROJECT_REDACTED>")
    text = _PROJECT_RE.sub(r"\1<PROJECT_REDACTED>", text)
    text = _PROJECT_ASSIGNMENT_RE.sub(r"\1<PROJECT_REDACTED>", text)
    text = _SECRET_RE.sub(r"\1<SECRET_REDACTED>", text)
    text = _GEOMETRY_RE.sub(r"\1<GEOMETRY_REDACTED>", text)
    return text


def _safe_error(exc: BaseException) -> str:
    return _sanitize_diagnostic(str(exc) or exc.__class__.__name__)


def _safe_traceback(exc: BaseException) -> str:
    raw = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return _sanitize_diagnostic(raw)


def _write_traceback(debug_dir: Path, event_id: str, exc: BaseException) -> str:
    safe_event_id = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in event_id
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = debug_dir / f"{safe_event_id}_{timestamp}.traceback.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(_safe_traceback(exc), encoding="utf-8")
    temporary.replace(output_path)
    return output_path.relative_to(ROOT).as_posix()


def _error_record(
    event: Any,
    exc: BaseException,
    *,
    traceback_file: str = "",
) -> dict[str, Any]:
    details = exception_diagnostics(exc)
    return {
        "event_id": details.get("event_id") or event.event_id,
        "configuration_id": event.event.configuration_id,
        "error_type": details.get("error_type") or type(exc).__name__,
        "error_message": _sanitize_diagnostic(details.get("error_message", str(exc))),
        "error_stage": details.get("error_stage", "runner"),
        "operation": _sanitize_diagnostic(details.get("operation", "")),
        "cause_type": details.get("cause_type", type(exc).__name__),
        "cause_message": _sanitize_diagnostic(details.get("cause_message", str(exc))),
        "aoi_id": details.get("aoi_id", "") or "",
        "window_id": details.get("window_id", "") or "",
        "attempt": details.get("attempt", "") if details.get("attempt") is not None else "",
        "retry_count": details.get("retry_count", "")
        if details.get("retry_count") is not None
        else "",
        "max_retries": details.get("max_retries", "")
        if details.get("max_retries") is not None
        else "",
        "traceback_file": traceback_file,
        "processing_timestamp_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "pipeline_version": DNBR_PIPELINE_VERSION,
    }


def _current_contract_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only rows produced by the active dNBR contract version."""

    return [
        row
        for row in rows
        if str(row.get("pipeline_version", "")).strip() == DNBR_PIPELINE_VERSION
    ]


def _load_checkpoint(path: Path) -> tuple[set[str], set[str]]:
    if not path.is_file():
        return set(), set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set(), set()
    if str(payload.get("pipeline_version", "")).strip() != DNBR_PIPELINE_VERSION:
        return set(), set()
    return (
        {str(value) for value in payload.get("completed_event_ids", [])},
        {str(value) for value in payload.get("failed_event_ids", [])},
    )


def _write_checkpoint(
    path: Path,
    *,
    selected_event_ids: set[str],
    completed_event_ids: set[str],
    failed_event_ids: set[str],
) -> tuple[set[str], set[str]]:
    existing_completed, existing_failed = _load_checkpoint(path)
    merged_completed = (
        (existing_completed - selected_event_ids) | completed_event_ids
    )
    merged_failed = (existing_failed - selected_event_ids) | failed_event_ids
    write_json_atomic(
        path,
        {
            "pipeline_version": DNBR_PIPELINE_VERSION,
            "checkpoint_timestamp_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "completed_event_ids": sorted(merged_completed),
            "failed_event_ids": sorted(merged_failed),
        },
    )
    return merged_completed, merged_failed


def _write_current_outputs(
    paths: dict[str, Path],
    inputs: Any,
    *,
    replace_event_ids: set[str],
    result_by_event: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    completed_event_ids: set[str],
    failed_event_ids: set[str],
    requested_event_ids: list[str],
    min_valid_overlap_fraction: float,
    earth_engine_queries_made: bool,
) -> dict[str, Any]:
    replacement_metrics = [
        row
        for event_id, result in result_by_event.items()
        if event_id in replace_event_ids
        for row in result.get("metrics_rows", [])
    ]
    replacement_sensitivity = [
        row
        for event_id, result in result_by_event.items()
        if event_id in replace_event_ids
        for row in result.get("sensitivity_rows", [])
    ]
    existing_metrics = _current_contract_rows(read_utf8_csv(paths["metrics"]))
    existing_sensitivity = _current_contract_rows(read_utf8_csv(paths["sensitivity"]))
    existing_errors = _current_contract_rows(read_utf8_csv(paths["errors"]))
    merged_metrics = merge_event_rows(
        existing_metrics,
        replacement_metrics,
        replace_event_ids,
    )
    merged_sensitivity = merge_event_rows(
        existing_sensitivity,
        replacement_sensitivity,
        replace_event_ids,
    )
    merged_errors = merge_event_rows(existing_errors, errors, replace_event_ids)
    merged_metrics.sort(
        key=lambda row: (
            str(row.get("event_id", "")),
            str(row.get("analysis_mode", "")),
            str(row.get("cloud_threshold", "")),
        )
    )
    merged_sensitivity.sort(
        key=lambda row: (
            str(row.get("event_id", "")),
            str(row.get("analysis_mode", "")),
            str(row.get("cloud_threshold", "")),
        )
    )
    merged_errors.sort(key=lambda row: str(row.get("event_id", "")))
    return write_dnbr_outputs(
        paths,
        inputs,
        metrics_rows=merged_metrics,
        sensitivity_rows=merged_sensitivity,
        errors=merged_errors,
        requested_event_ids=requested_event_ids,
        completed_event_ids=sorted(completed_event_ids),
        failed_event_ids=sorted(failed_event_ids),
        min_valid_overlap_fraction=min_valid_overlap_fraction,
        earth_engine_queries_made=earth_engine_queries_made,
    )


def _select_events(
    processable_events: list[Any],
    *,
    event_id: str | None,
    max_events: int | None,
) -> list[Any]:
    events = processable_events
    if event_id:
        events = [event for event in events if event.event_id == event_id]
        if not events:
            raise DnbrValidationError(
                "event_id no pertenece a los 28 eventos procesables"
            )
    if max_events is not None:
        events = events[:max_events]
    if not events:
        raise DnbrValidationError("no hay eventos seleccionados para procesar")
    return events


def _load_resume_cache(
    event_input: Any,
    *,
    cache_dir: Path,
    resume: bool,
    overwrite: bool,
    min_valid_overlap_fraction: float,
) -> dict[str, Any] | None:
    if not resume or overwrite:
        return None
    return load_event_cache(
        cache_path(cache_dir, event_input.event_id),
        cache_signature(event_input, min_valid_overlap_fraction),
        root=ROOT,
    )


def _safe_local_id(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in value
    )


def _rebuild_local_quicklooks(
    events: list[Any],
    *,
    inputs: Any,
    paths: dict[str, Path],
) -> int:
    """Rebuild only panels from local PNG artifacts; never touches EE/science outputs."""

    debug_dir = ROOT / "outputs" / "debug" / "sentinel2_dnbr"
    debug_dir.mkdir(parents=True, exist_ok=True)
    metric_rows = _current_contract_rows(read_utf8_csv(paths["metrics"]))
    results: list[dict[str, Any]] = []
    for event_input in events:
        metric_row = next(
            (
                row
                for row in metric_rows
                if row.get("event_id") == event_input.event_id
                and row.get("analysis_mode") == "selected_pair"
                and str(row.get("cloud_threshold")) in {"0.5", "0.50", "0.500"}
            ),
            None,
        )
        try:
            result = rebuild_quicklook_from_artifacts(
                event_input,
                output_dir=paths["figures"],
                metrics_row=metric_row,
            )
            results.append(result)
            audit = {
                "event_id": event_input.event_id,
                "status": "generated",
                "earth_engine_queries_made": False,
                "scientific_outputs_modified": False,
                "result": result,
            }
            print(f"quicklook_generated={event_input.event_id}")
        except Exception as exc:
            stats = getattr(exc, "stats", {})
            failure = {
                "event_id": event_input.event_id,
                "status": "failed_validation",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "source_stats": stats,
                "earth_engine_queries_made": False,
                "scientific_outputs_modified": False,
            }
            results.append(failure)
            audit = failure
            print(f"quicklook_failed={event_input.event_id}: {str(exc)}", file=sys.stderr)
        write_json_atomic(
            debug_dir / f"{_safe_local_id(event_input.event_id)}_quicklook_source_audit.json",
            audit,
        )
    report = {
        "mode": "rebuild_quicklooks",
        "requested_event_count": len(events),
        "generated_count": sum(item.get("status") == "generated" for item in results),
        "failed_validation_count": sum(item.get("status") == "failed_validation" for item in results),
        "events": results,
        "earth_engine_queries_made": False,
        "scientific_outputs_modified": False,
        "metrics_and_inventories_modified": False,
        "pipeline_version": DNBR_PIPELINE_VERSION,
    }
    write_json_atomic(debug_dir / "quicklook_rebuild_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["failed_validation_count"] else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.retry_count < 0 or args.backoff_seconds < 0:
        print("ERROR: retry-count y backoff-seconds no pueden ser negativos.", file=sys.stderr)
        return 2
    if args.max_events is not None and args.max_events <= 0:
        print("ERROR: max-events debe ser positivo.", file=sys.stderr)
        return 2
    if not 0 < args.min_valid_overlap_fraction <= 1:
        print("ERROR: min-valid-overlap-fraction debe estar entre 0 y 1.", file=sys.stderr)
        return 2
    if args.overwrite and args.confirm_overwrite != "OVERWRITE":
        print(
            "ERROR: --overwrite requiere --confirm-overwrite OVERWRITE.",
            file=sys.stderr,
        )
        return 2
    if args.debug and not args.event_id:
        print("ERROR: --debug requiere --event-id.", file=sys.stderr)
        return 2
    if args.rebuild_quicklooks and (args.smoke_test or args.resume or args.overwrite):
        print(
            "ERROR: --rebuild-quicklooks no se combina con --smoke-test, --resume ni --overwrite.",
            file=sys.stderr,
        )
        return 2
    if args.smoke_test:
        try:
            client = initialize_earth_engine()
            print(json.dumps(smoke_test(client), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except (EarthEngineConfigurationError, EarthEngineQueryError) as exc:
            print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
            if args.debug:
                print(_safe_traceback(exc), file=sys.stderr)
            return 2

    defaults = default_dnbr_paths(ROOT)
    paths = {
        "pilot": _path(args.pilot_events),
        "membership": _path(args.membership),
        "events": _path(args.events),
        "selection": _path(args.selection),
        "scene_inventory": _path(args.scene_inventory),
        "aoi_inventory": _path(args.aoi_inventory),
        **{
            key: value
            for key, value in defaults.items()
            if key
            not in {
                "pilot",
                "membership",
                "events",
                "selection",
                "scene_inventory",
                "aoi_inventory",
            }
        },
    }
    if args.rebuild_quicklooks:
        try:
            inputs = load_dnbr_inputs(
                pilot_path=paths["pilot"],
                events_path=paths["events"],
                membership_path=paths["membership"],
                selection_path=paths["selection"],
                scene_inventory_path=paths["scene_inventory"],
                aoi_inventory_path=paths["aoi_inventory"],
            )
            events = _select_events(
                list(inputs.processable),
                event_id=args.event_id,
                max_events=args.max_events,
            )
        except (OSError, ValueError, DnbrValidationError) as exc:
            print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
            return 2
        return _rebuild_local_quicklooks(events, inputs=inputs, paths=paths)
    protected_outputs = (
        paths["metrics"],
        paths["errors"],
        paths["checkpoint"],
        paths["report_json"],
        paths["report_markdown"],
        paths["sensitivity"],
        paths["review_queue"],
    )
    if not args.resume and not args.overwrite and any(path.exists() for path in protected_outputs):
        print(
            "ERROR: ya existen outputs de NBR/dNBR. Use --resume o --overwrite --confirm-overwrite OVERWRITE.",
            file=sys.stderr,
        )
        return 2
    try:
        inputs = load_dnbr_inputs(
            pilot_path=paths["pilot"],
            events_path=paths["events"],
            membership_path=paths["membership"],
            selection_path=paths["selection"],
            scene_inventory_path=paths["scene_inventory"],
            aoi_inventory_path=paths["aoi_inventory"],
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
        return 2

    try:
        events = _select_events(
            list(inputs.processable),
            event_id=args.event_id,
            max_events=args.max_events,
        )
    except DnbrValidationError as exc:
        print(f"ERROR: {_safe_error(exc)}.", file=sys.stderr)
        return 2

    try:
        client = initialize_earth_engine()
    except EarthEngineConfigurationError as exc:
        print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
        return 2

    selected_event_ids = {event.event_id for event in events}
    paths["cache"].mkdir(parents=True, exist_ok=True)
    result_by_event: dict[str, dict[str, Any]] = {}
    current_errors: list[dict[str, Any]] = []
    current_completed: set[str] = set()
    current_failed: set[str] = set()
    earth_engine_queries_made = False
    debug_failure = False
    completed_checkpoint, failed_checkpoint = _load_checkpoint(paths["checkpoint"])

    for event_input in events:
        signature = cache_signature(event_input, args.min_valid_overlap_fraction)
        cached = _load_resume_cache(
            event_input,
            cache_dir=paths["cache"],
            resume=args.resume,
            overwrite=args.overwrite,
            min_valid_overlap_fraction=args.min_valid_overlap_fraction,
        )
        if cached is not None:
            result_by_event[event_input.event_id] = cached
            current_completed.add(event_input.event_id)
        else:
            earth_engine_queries_made = True
            try:
                result = execute_event(
                    client,
                    event_input,
                    output_dir=paths["figures"],
                    min_valid_overlap_fraction=args.min_valid_overlap_fraction,
                    retry_count=args.retry_count,
                    backoff_seconds=args.backoff_seconds,
                    root=ROOT,
                )
                write_event_cache(
                    cache_path(paths["cache"], event_input.event_id),
                    signature,
                    result,
                )
                result_by_event[event_input.event_id] = result
                current_completed.add(event_input.event_id)
            except Exception as exc:
                current_failed.add(event_input.event_id)
                traceback_file = (
                    _write_traceback(
                        ROOT / "outputs" / "debug" / "sentinel2_dnbr",
                        event_input.event_id,
                        exc,
                    )
                    if args.debug
                    else ""
                )
                current_errors.append(
                    _error_record(
                        event_input,
                        exc,
                        traceback_file=traceback_file,
                    )
                )
                if args.debug:
                    print(_safe_traceback(exc), file=sys.stderr)
                    debug_failure = True

        completed_checkpoint, failed_checkpoint = _write_checkpoint(
            paths["checkpoint"],
            selected_event_ids={event_input.event_id},
            completed_event_ids=current_completed,
            failed_event_ids=current_failed,
        )
        _write_current_outputs(
            paths,
            inputs,
            replace_event_ids={event_input.event_id},
            result_by_event=result_by_event,
            errors=current_errors,
            completed_event_ids=completed_checkpoint,
            failed_event_ids=failed_checkpoint,
            requested_event_ids=[item.event_id for item in events],
            min_valid_overlap_fraction=args.min_valid_overlap_fraction,
            earth_engine_queries_made=earth_engine_queries_made,
        )
        if debug_failure:
            break

    report = _write_current_outputs(
        paths,
        inputs,
        replace_event_ids=set(result_by_event) | current_failed,
        result_by_event=result_by_event,
        errors=current_errors,
        completed_event_ids=completed_checkpoint,
        failed_event_ids=failed_checkpoint,
        requested_event_ids=[item.event_id for item in events],
        min_valid_overlap_fraction=args.min_valid_overlap_fraction,
        earth_engine_queries_made=earth_engine_queries_made,
    )
    print(
        json.dumps(
            {
                "events_requested": len(events),
                "processable_events": len(inputs.processable),
                "excluded_events": len(inputs.excluded),
                "events_completed_this_run": len(current_completed),
                "events_failed_this_run": len(current_failed),
                "debug": bool(args.debug),
                "earth_engine_queries_made": earth_engine_queries_made,
                "metrics": str(paths["metrics"]),
                "report": str(paths["report_json"]),
                "quicklook_directory": str(paths["figures"]),
                "report_completed_event_count": report["completed_event_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if current_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
