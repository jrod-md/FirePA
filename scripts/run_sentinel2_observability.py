"""Run the Sentinel-2 observability inventory for the frozen 30-event pilot."""

from __future__ import annotations

import argparse
import csv
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
from fuegopa.sentinel2_figures import generate_observability_figures  # noqa: E402
from fuegopa.sentinel2_observability import (  # noqa: E402
    ObservabilityValidationError,
    PIPELINE_VERSION,
    cache_path,
    cache_signature,
    evaluate_event_result,
    load_event_cache,
    load_pilot_events,
    query_event,
    rebuild_observability_from_inventory,
    write_event_cache,
    write_json,
    write_observability_outputs,
    write_report_markdown,
)


def _path(value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else ROOT / candidate


def _default_paths() -> dict[str, Path]:
    return {
        "pilot": ROOT / "data" / "processed" / "sentinel2_observability_pilot_events.csv",
        "membership": ROOT / "data" / "processed" / "firms_cocle_2025_event_membership.csv",
        "events": ROOT / "data" / "processed" / "firms_cocle_2025_events_provisional.csv",
        "cache": ROOT / "data" / "interim" / "sentinel2_observability_cache",
        "scene_inventory": ROOT / "data" / "interim" / "sentinel2_scene_inventory.csv",
        "aoi_inventory": ROOT / "data" / "interim" / "sentinel2_aoi_inventory.csv",
        "observability": ROOT / "data" / "interim" / "sentinel2_observability.csv",
        "errors": ROOT / "data" / "interim" / "sentinel2_observability_errors.csv",
        "report_json": ROOT / "outputs" / "sentinel2_observability_report.json",
        "report_markdown": ROOT / "outputs" / "sentinel2_observability_report.md",
        "attrition": ROOT / "outputs" / "sentinel2_observability_attrition.csv",
        "sensitivity": ROOT / "outputs" / "sentinel2_observability_sensitivity.csv",
        "figures": ROOT / "outputs" / "figures" / "sentinel2_observability",
        "debug": ROOT / "outputs" / "debug" / "sentinel2",
        "checkpoint": ROOT / "data" / "interim" / "sentinel2_observability_checkpoint.json",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventario Sentinel-2/Cloud Score+ sin descargar raster ni calcular índices.")
    parser.add_argument("--smoke-test", action="store_true", help="Inicializa EE y confirma acceso mínimo a ambas colecciones.")
    parser.add_argument("--pilot-events", default="data/processed/sentinel2_observability_pilot_events.csv")
    parser.add_argument("--membership", default="data/processed/firms_cocle_2025_event_membership.csv")
    parser.add_argument("--events", default="data/processed/firms_cocle_2025_events_provisional.csv")
    parser.add_argument("--cache-dir", default="data/interim/sentinel2_observability_cache")
    parser.add_argument("--event-id", help="Procesa un único event_id del piloto.")
    parser.add_argument("--max-events", type=int, help="Límite de eventos para una prueba parcial.")
    parser.add_argument("--resume", action="store_true", help="Reutiliza cachés cuyo contrato no cambió.")
    parser.add_argument("--overwrite", action="store_true", help="Ignora cachés y reemplaza outputs existentes.")
    parser.add_argument("--confirm-overwrite", help="Debe ser exactamente OVERWRITE junto con --overwrite.")
    parser.add_argument("--debug", action="store_true", help="Procesa un solo evento y conserva traceback diagnóstico seguro.")
    parser.add_argument(
        "--rebuild-from-inventory",
        action="store_true",
        help="Reconstruye observabilidad y reportes desde inventarios locales, sin inicializar Earth Engine.",
    )
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--backoff-seconds", type=float, default=2.0)
    return parser


_SECRET_RE = re.compile(
    r"(?i)(\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\b\s*[:=]\s*)([^\s,;]+)"
)
_PROJECT_RE = re.compile(r"(?i)(\bprojects/)([A-Za-z0-9._-]+)")
_PROJECT_ASSIGNMENT_RE = re.compile(r"(?i)(\bproject(?:[_ -]?id)?\b\s*[:=]\s*)([A-Za-z0-9._-]+)")
_GEOMETRY_RE = re.compile(r"(?im)^([^\r\n]*(?:coordinates|geometry|geojson|polygon|multipolygon)\s*[:=]).*$")


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
    safe_event_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in event_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = debug_dir / f"{safe_event_id}_{timestamp}.traceback.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(_safe_traceback(exc), encoding="utf-8")
    temporary.replace(output_path)
    return output_path.relative_to(ROOT).as_posix()


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _replace_event_rows(
    existing: list[dict[str, Any]],
    replacement: list[dict[str, Any]],
    replace_event_ids: set[str],
) -> list[dict[str, Any]]:
    kept = [row for row in existing if str(row.get("event_id", "")) not in replace_event_ids]
    return kept + replacement


def _load_cached_result(
    event: Any,
    cache_dir: Path,
    *,
    resume: bool,
    overwrite: bool,
) -> dict[str, Any] | None:
    """Resume only compatible successful caches; missing/failed events retry."""

    if overwrite or not resume:
        return None
    return load_event_cache(cache_path(cache_dir, event.event_id), cache_signature(event))


def _error_record(
    event: Any,
    exc: BaseException,
    *,
    query_timestamp_utc: str,
    traceback_file: str = "",
) -> dict[str, Any]:
    details = exception_diagnostics(exc)
    return {
        "event_id": details.get("event_id") or event.event_id,
        "configuration_id": event.configuration_id,
        "error_type": details.get("error_type") or type(exc).__name__,
        "error_message": _sanitize_diagnostic(details.get("error_message", str(exc))),
        "error_stage": details.get("error_stage", "runner"),
        "operation": _sanitize_diagnostic(details.get("operation", "")),
        "cause_type": details.get("cause_type", type(exc).__name__),
        "cause_message": _sanitize_diagnostic(details.get("cause_message", str(exc))),
        "aoi_id": details.get("aoi_id", "") or "",
        "window_id": details.get("window_id", "") or "",
        "attempt": details.get("attempt", "") if details.get("attempt") is not None else "",
        "retry_count": details.get("retry_count", "") if details.get("retry_count") is not None else "",
        "max_retries": details.get("max_retries", "") if details.get("max_retries") is not None else "",
        "traceback_file": traceback_file,
        "query_timestamp_utc": query_timestamp_utc,
        "pipeline_version": PIPELINE_VERSION,
    }


def _checkpoint(
    path: Path,
    completed: list[str],
    failed: list[str],
    *,
    replace_event_ids: set[str] | None = None,
) -> None:
    replace_ids = replace_event_ids or set(completed) | set(failed)
    existing_completed: set[str] = set()
    existing_failed: set[str] = set()
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing_completed = {str(value) for value in payload.get("completed_event_ids", [])}
            existing_failed = {str(value) for value in payload.get("failed_event_ids", [])}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
            existing_completed = set()
            existing_failed = set()
    merged_completed = (existing_completed - replace_ids) | set(completed)
    merged_failed = (existing_failed - replace_ids) | set(failed)
    write_json(
        path,
        {
            "pipeline_version": PIPELINE_VERSION,
            "checkpoint_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed_event_ids": sorted(merged_completed),
            "failed_event_ids": sorted(merged_failed),
        },
    )


def _write_current_outputs(
    paths: dict[str, Path],
    report_events: list[Any],
    replace_event_ids: set[str],
    replace_error_ids: set[str],
    result_by_event: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    *,
    requested_event_count: int,
) -> dict[str, Any]:
    all_aoi: list[dict[str, Any]] = []
    all_scenes: list[dict[str, Any]] = []
    all_observations: list[dict[str, Any]] = []
    for event in report_events:
        result = result_by_event.get(event.event_id)
        if result is None:
            continue
        aoi_rows, scene_rows, observation_rows = evaluate_event_result(event, result)
        all_aoi.extend(aoi_rows)
        all_scenes.extend(scene_rows)
        all_observations.extend(observation_rows)
    existing_aoi = _read_csv_rows(paths["aoi_inventory"])
    existing_scenes = _read_csv_rows(paths["scene_inventory"])
    existing_observations = _read_csv_rows(paths["observability"])
    existing_errors = _read_csv_rows(paths["errors"])
    merged_aoi = _replace_event_rows(existing_aoi, all_aoi, replace_event_ids)
    merged_scenes = _replace_event_rows(existing_scenes, all_scenes, replace_event_ids)
    merged_observations = _replace_event_rows(existing_observations, all_observations, replace_event_ids)
    merged_errors = _replace_event_rows(existing_errors, errors, replace_error_ids)
    return write_observability_outputs(
        paths,
        report_events,
        merged_observations,
        merged_scenes,
        merged_aoi,
        merged_errors,
        requested_event_count=requested_event_count,
    )


def _rebuild_from_inventory(
    paths: dict[str, Path],
    events: list[Any],
) -> tuple[dict[str, Any], list[Path]]:
    """Rebuild derived outputs while leaving both local inventories untouched."""

    scene_inventory_rows = _read_csv_rows(paths["scene_inventory"])
    aoi_inventory_rows = _read_csv_rows(paths["aoi_inventory"])
    existing_errors = _read_csv_rows(paths["errors"])
    rebuilt = rebuild_observability_from_inventory(
        events,
        scene_inventory_rows,
        aoi_inventory_rows,
        existing_errors,
    )
    report = write_observability_outputs(
        paths,
        events,
        rebuilt["observation_rows"],
        rebuilt["scene_rows"],
        rebuilt["aoi_rows"],
        rebuilt["errors"],
        requested_event_count=len(events),
        write_inventories=False,
    )
    figures = generate_observability_figures(
        paths["figures"],
        report,
        rebuilt["observation_rows"],
        rebuilt["scene_rows"],
    )
    report["figure_files"] = [str(path) for path in figures]
    report["rebuild_from_inventory"] = True
    report["earth_engine_queries_made"] = False
    report["scene_inventory_preserved"] = True
    report["aoi_inventory_preserved"] = True
    write_json(paths["report_json"], report)
    write_report_markdown(paths["report_markdown"], report)
    return report, figures


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.retry_count < 0 or args.backoff_seconds < 0:
        print("ERROR: retry-count y backoff-seconds no pueden ser negativos.", file=sys.stderr)
        return 2
    if args.max_events is not None and args.max_events <= 0:
        print("ERROR: max-events debe ser positivo.", file=sys.stderr)
        return 2
    if args.overwrite and args.confirm_overwrite != "OVERWRITE":
        print("ERROR: --overwrite requiere --confirm-overwrite OVERWRITE.", file=sys.stderr)
        return 2
    if args.debug and args.smoke_test:
        print("ERROR: --debug requiere procesar un evento, no puede combinarse con --smoke-test.", file=sys.stderr)
        return 2
    if args.rebuild_from_inventory and args.smoke_test:
        print("ERROR: --rebuild-from-inventory no puede combinarse con --smoke-test.", file=sys.stderr)
        return 2
    if args.rebuild_from_inventory and args.debug:
        print("ERROR: --rebuild-from-inventory no necesita --debug ni consultas Earth Engine.", file=sys.stderr)
        return 2
    if args.debug and not args.event_id:
        print("ERROR: --debug requiere --event-id para limitar la ejecución a un solo evento.", file=sys.stderr)
        return 2
    if args.smoke_test:
        try:
            client = initialize_earth_engine()
            print(json.dumps(smoke_test(client), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except (EarthEngineConfigurationError, EarthEngineQueryError) as exc:
            print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
            return 2

    defaults = _default_paths()
    paths = {
        "pilot": _path(args.pilot_events),
        "membership": _path(args.membership),
        "events": _path(args.events),
        "cache": _path(args.cache_dir),
        **{key: value for key, value in defaults.items() if key not in {"pilot", "membership", "events", "cache"}},
    }
    protected_outputs = (
        paths["scene_inventory"],
        paths["aoi_inventory"],
        paths["observability"],
        paths["errors"],
        paths["report_json"],
        paths["report_markdown"],
        paths["attrition"],
        paths["sensitivity"],
    )
    if not args.rebuild_from_inventory and not args.resume and not args.overwrite and any(path.exists() for path in protected_outputs):
        print(
            "ERROR: ya existen outputs de observabilidad. Use --resume o "
            "--overwrite --confirm-overwrite OVERWRITE.",
            file=sys.stderr,
        )
        return 2
    try:
        all_events = load_pilot_events(paths["pilot"], paths["events"], paths["membership"])
    except (OSError, ValueError) as exc:
        print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
        return 2
    if args.rebuild_from_inventory:
        if args.event_id or args.max_events is not None:
            print("ERROR: --rebuild-from-inventory reconstruye el piloto completo; no admite --event-id ni --max-events.", file=sys.stderr)
            return 2
        try:
            report, figures = _rebuild_from_inventory(paths, all_events)
        except (OSError, ObservabilityValidationError, ValueError) as exc:
            print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
            return 2
        print(json.dumps({
            "events_requested": len(all_events),
            "events_processed": report["events_processed"],
            "events_failed": report["events_failed"],
            "scene_inventory_row_count": report["scene_inventory_row_count"],
            "unique_sentinel2_scene_count": report["unique_sentinel2_scene_count"],
            "earth_engine_queries_made": False,
            "figures": len(figures),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    events = all_events
    if args.event_id:
        events = [event for event in events if event.event_id == args.event_id]
        if not events:
            print("ERROR: --event-id no pertenece al piloto preseleccionado.", file=sys.stderr)
            return 2
    if args.max_events is not None:
        events = events[: args.max_events]

    try:
        client = initialize_earth_engine()
    except EarthEngineConfigurationError as exc:
        print(f"ERROR: {_safe_error(exc)}", file=sys.stderr)
        return 2

    paths["cache"].mkdir(parents=True, exist_ok=True)
    result_by_event: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    completed: list[str] = []
    failed: list[str] = []
    selected_event_ids = {event.event_id for event in events}
    debug_failure = False
    for event in events:
        event_cache = cache_path(paths["cache"], event.event_id)
        signature = cache_signature(event)
        result = _load_cached_result(
            event,
            paths["cache"],
            resume=args.resume,
            overwrite=args.overwrite,
        )
        if result is not None:
            result_by_event[event.event_id] = result
            completed.append(event.event_id)
        else:
            try:
                result = query_event(
                    client,
                    event,
                    retry_count=args.retry_count,
                    backoff_seconds=args.backoff_seconds,
                )
                write_event_cache(event_cache, signature, result)
                result_by_event[event.event_id] = result
                completed.append(event.event_id)
            except Exception as exc:  # keep the batch auditable and continue to the next event
                failed.append(event.event_id)
                traceback_file = _write_traceback(paths["debug"], event.event_id, exc) if args.debug else ""
                errors.append(
                    _error_record(
                        event,
                        exc,
                        query_timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        traceback_file=traceback_file,
                    )
                )
                if args.debug:
                    print(_safe_traceback(exc), file=sys.stderr)
                    debug_failure = True
        _checkpoint(paths["checkpoint"], completed, failed, replace_event_ids=selected_event_ids)
        _write_current_outputs(
            paths,
            all_events,
            set(result_by_event),
            selected_event_ids,
            result_by_event,
            errors,
            requested_event_count=len(events),
        )
        if debug_failure:
            break

    report = _write_current_outputs(
        paths,
        all_events,
        set(result_by_event),
        selected_event_ids,
        result_by_event,
        errors,
        requested_event_count=len(events),
    )
    figure_observations = _read_csv_rows(paths["observability"])
    figure_scenes = _read_csv_rows(paths["scene_inventory"])
    figures = generate_observability_figures(paths["figures"], report, figure_observations, figure_scenes)
    report["figure_files"] = [str(path) for path in figures]
    report["resume_enabled"] = bool(args.resume)
    report["overwrite_enabled"] = bool(args.overwrite)
    write_json(paths["report_json"], report)
    write_report_markdown(paths["report_markdown"], report)
    print(json.dumps({
        "events_requested": len(events),
        "events_completed": len(completed),
        "events_failed": len(failed),
        "debug": bool(args.debug),
        "scene_inventory": str(paths["scene_inventory"]),
        "observability": str(paths["observability"]),
        "report": str(paths["report_json"]),
        "figures": len(figures),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
