"""CLI orchestration for the approved FIRMS -> Coclé pre-clustering stage."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .acquisition import (
    AcquisitionError,
    AvailabilityRange,
    DateRange,
    HttpFetcher,
    acquire_local_csv,
    build_availability_url,
    download_sources,
    expected_fragments,
    parse_availability_csv,
    persist_raw_bytes,
    select_sources,
    validate_manifest,
)
from .cocle import (
    MAIN_END,
    MAIN_START,
    FilterResult,
    SourceScan,
    filter_to_cocle,
    scan_raw_artifact,
    write_detections,
)
from .firms import main as legacy_main
from .firms import RawImmutabilityError
from .geo import BoundaryError, load_boundary
from .profile import build_profile, write_profile


class ConfigurationError(ValueError):
    """Raised when a run would violate the approved phase scope."""


@dataclass(frozen=True)
class RunOptions:
    project_root: Path
    start_date: date
    end_date: date
    area: str
    input_path: Path | None
    source_label: str
    sources: tuple[str, ...]
    boundary_path: Path
    boundary_crs: str | None
    raw_dir: Path
    raw_path: Path | None
    manifest_dir: Path
    output_path: Path
    profile_json: Path
    profile_markdown: Path
    availability_output: Path
    source_selection_output: Path
    source_selection_markdown: Path
    acquisition_audit_json: Path
    acquisition_audit_markdown: Path
    timeout_seconds: float
    max_retries: int
    sensor_match_distance_km: float
    sensor_match_time_minutes: int
    map_key: str | None


@dataclass(frozen=True)
class RunResult:
    output_path: Path
    profile_json: Path
    profile_markdown: Path
    raw_paths: tuple[Path, ...]
    manifest_paths: tuple[Path, ...]
    profile: dict[str, Any]
    errors: tuple[str, ...]
    acquisition_audit_json: Path


def _resolve_path(root: Path, value: str | None, default: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else root / candidate


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(f"{field} debe usar YYYY-MM-DD.") from exc


def _env_sources(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _default_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adquiere FIRMS por fuente/fecha, filtra Coclé y crea perfil previo al clustering."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="CSV FIRMS local; se conserva como raw separado.")
    source.add_argument("--url", help=argparse.SUPPRESS)
    parser.add_argument("--start-date", default=os.environ.get("FIRMS_START_DATE", MAIN_START.isoformat()))
    parser.add_argument("--end-date", default=os.environ.get("FIRMS_END_DATE", MAIN_END.isoformat()))
    parser.add_argument("--area", default=os.environ.get("FIRMS_AREA", "cocle"))
    parser.add_argument("--source", dest="sources", action="append", help="Fuente FIRMS; se puede repetir.")
    parser.add_argument("--source-label", default=os.environ.get("FIRMS_SOURCE_LABEL", "LOCAL_CSV"))
    parser.add_argument(
        "--map-key",
        help="Clave FIRMS opcional; se recomienda FIRMS_MAP_KEY y nunca se imprime ni persiste.",
    )
    parser.add_argument("--project-root", type=Path, default=os.environ.get("FUEGOPA_PROJECT_ROOT"))
    parser.add_argument("--boundary-path", help="GeoJSON oficial local de Coclé.")
    parser.add_argument("--boundary-crs", default=os.environ.get("FIRMS_BOUNDARY_CRS"))
    parser.add_argument("--raw-dir", help="Directorio de archivos raw por fuente/fragmento.")
    parser.add_argument("--raw-path", help="Ruta raw específica para --input local.")
    parser.add_argument("--manifest-dir", help="Directorio de manifests JSON.")
    parser.add_argument("--output", dest="output_path", help="CSV final de detecciones dentro de Coclé.")
    parser.add_argument("--profile-json")
    parser.add_argument("--profile-md", dest="profile_markdown")
    parser.add_argument("--availability-output", help="Snapshot local de la respuesta data_availability.")
    parser.add_argument("--source-selection-output", help="Reporte de fuentes incluidas/excluidas.")
    parser.add_argument("--source-selection-md", help="Resumen Markdown de fuentes incluidas/excluidas.")
    parser.add_argument("--acquisition-audit-json", help="Auditoría de completitud y calidad de adquisición.")
    parser.add_argument("--acquisition-audit-md", help="Resumen Markdown de la auditoría de adquisición.")
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("FIRMS_TIMEOUT_SECONDS", "30")))
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("FIRMS_MAX_RETRIES", "2")))
    parser.add_argument("--sensor-match-distance-km", type=float, default=1.0)
    parser.add_argument("--sensor-match-time-minutes", type=int, default=30)
    return parser


def _options_from_args(args: argparse.Namespace) -> RunOptions:
    root = Path(args.project_root or Path.cwd()).expanduser().resolve()
    start_date = _parse_date(args.start_date, "--start-date")
    end_date = _parse_date(args.end_date, "--end-date")
    if (start_date, end_date) != (MAIN_START, MAIN_END):
        raise ConfigurationError(
            "Esta fase solo permite 2025-01-01..2025-04-30. La temporada 2026 está reservada "
            "para evaluación posterior y no se usa ahora."
        )
    if args.area.casefold() != "cocle":
        raise ConfigurationError("Esta fase solo implementa el área aprobada 'cocle'.")
    if args.timeout <= 0 or args.max_retries < 0:
        raise ConfigurationError("--timeout debe ser positivo y --max-retries no puede ser negativo.")
    if args.sensor_match_distance_km <= 0 or args.sensor_match_time_minutes <= 0:
        raise ConfigurationError("Los umbrales de coincidencia diagnóstica deben ser positivos.")

    raw_dir = _resolve_path(root, args.raw_dir or os.environ.get("FIRMS_RAW_DIR"), root / "data" / "raw")
    raw_path = _resolve_path(root, args.raw_path or os.environ.get("FIRMS_LOCAL_RAW_PATH"), raw_dir / "firms_local_cocle_2025.csv")
    input_path = (
        _resolve_path(root, str(args.input), root / "data" / "input.csv") if args.input else None
    )
    sources = tuple(args.sources or _env_sources(os.environ.get("FIRMS_SOURCES")))
    return RunOptions(
        project_root=root,
        start_date=start_date,
        end_date=end_date,
        area="cocle",
        input_path=input_path,
        source_label=args.source_label.strip() or "LOCAL_CSV",
        sources=sources,
        boundary_path=_resolve_path(root, args.boundary_path or os.environ.get("FIRMS_BOUNDARY_PATH"), root / "data" / "reference" / "cocle.geojson"),
        boundary_crs=args.boundary_crs,
        raw_dir=raw_dir,
        raw_path=raw_path if input_path else None,
        manifest_dir=_resolve_path(root, args.manifest_dir or os.environ.get("FIRMS_MANIFEST_DIR"), raw_dir / "manifests"),
        output_path=_resolve_path(root, args.output_path or os.environ.get("FIRMS_OUTPUT_PATH"), root / "data" / "processed" / "firms_cocle_2025_detections.csv"),
        profile_json=_resolve_path(root, args.profile_json or os.environ.get("FIRMS_PROFILE_JSON"), root / "outputs" / "firms_cocle_2025_profile.json"),
        profile_markdown=_resolve_path(root, args.profile_markdown or os.environ.get("FIRMS_PROFILE_MD"), root / "outputs" / "firms_cocle_2025_profile.md"),
        availability_output=_resolve_path(root, args.availability_output or os.environ.get("FIRMS_AVAILABILITY_OUTPUT"), root / "outputs" / "firms_data_availability_2025.csv"),
        source_selection_output=_resolve_path(root, args.source_selection_output or os.environ.get("FIRMS_SOURCE_SELECTION_OUTPUT"), root / "outputs" / "firms_source_selection_2025.json"),
        source_selection_markdown=_resolve_path(root, args.source_selection_md or os.environ.get("FIRMS_SOURCE_SELECTION_MD"), root / "outputs" / "firms_source_selection_2025.md"),
        acquisition_audit_json=_resolve_path(root, args.acquisition_audit_json or os.environ.get("FIRMS_ACQUISITION_AUDIT_JSON"), root / "outputs" / "firms_acquisition_audit_2025.json"),
        acquisition_audit_markdown=_resolve_path(root, args.acquisition_audit_md or os.environ.get("FIRMS_ACQUISITION_AUDIT_MD"), root / "outputs" / "firms_acquisition_audit_2025.md"),
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
        sensor_match_distance_km=args.sensor_match_distance_km,
        sensor_match_time_minutes=args.sensor_match_time_minutes,
        map_key=(args.map_key or os.environ.get("FIRMS_MAP_KEY") or "").strip() or None,
    )


def _read_manifests(paths: Sequence[Path], map_key: str | None = None) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AcquisitionError(f"No se pudo leer el manifest generado: {path.name}") from exc
        if not isinstance(value, dict):
            raise AcquisitionError(f"El manifest generado no contiene un objeto JSON: {path.name}")
        validate_manifest(value, map_key=map_key)
        manifests.append(value)
    return manifests


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _processing_type(data_id: str) -> str:
    if data_id.endswith("_SP"):
        return "SP"
    if data_id.endswith("_NRT"):
        return "NRT"
    return "other"


def _source_selection_report(
    availability: Sequence[AvailabilityRange],
    selected: Sequence[AvailabilityRange],
    requested: DateRange,
    explicit_sources: Sequence[str] | None,
) -> dict[str, Any]:
    selected_ids = {record.data_id for record in selected}
    rows: list[dict[str, Any]] = []
    for record in availability:
        overlap = record.overlap(requested)
        is_historical_viirs = record.data_id.startswith("VIIRS_") and record.data_id.endswith("_SP")
        if record.data_id in selected_ids:
            reason = "included: VIIRS *_SP with availability overlap"
        elif explicit_sources:
            reason = "excluded: not requested explicitly"
        elif not is_historical_viirs:
            reason = "excluded: not a historical VIIRS *_SP source"
        elif overlap is None:
            reason = "excluded: no overlap with requested period"
        else:
            reason = "excluded: not selected by the historical VIIRS *_SP policy"
        rows.append(
            {
                "data_id": record.data_id,
                "processing_type": _processing_type(record.data_id),
                "min_date": record.min_date.isoformat(),
                "max_date": record.max_date.isoformat(),
                "overlap_start": overlap.start.isoformat() if overlap else None,
                "overlap_end": overlap.end.isoformat() if overlap else None,
                "included": record.data_id in selected_ids,
                "reason": reason,
            }
        )
    return {
        "requested_period": {"start_date": requested.start.isoformat(), "end_date": requested.end.isoformat()},
        "selection_policy": "Historical VIIRS *_SP only; MODIS and *_NRT are not selected for this cohort.",
        "priority_order": ["VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "other VIIRS *_SP"],
        "explicit_sources": list(explicit_sources or []),
        "available_sources": rows,
        "selected_sources": [
            {
                "data_id": record.data_id,
                "processing_type": _processing_type(record.data_id),
                "min_date": record.min_date.isoformat(),
                "max_date": record.max_date.isoformat(),
                "overlap_start": (record.overlap(requested).start.isoformat() if record.overlap(requested) else None),
                "overlap_end": (record.overlap(requested).end.isoformat() if record.overlap(requested) else None),
            }
            for record in selected
        ],
    }


def _write_source_selection_markdown(report: dict[str, Any], path: Path) -> None:
    selected = report.get("selected_sources", [])
    lines = [
        "# Selección de fuentes FIRMS — Coclé 2025",
        "",
        f"Periodo solicitado: `{report['requested_period']['start_date']}..{report['requested_period']['end_date']}`.",
        "",
        report["selection_policy"],
        "",
        "## Fuentes seleccionadas",
        "",
    ]
    if selected:
        lines.extend(
            f"- `{item['data_id']}` ({item['processing_type']}): disponibilidad `{item['min_date']}..{item['max_date']}`, solapamiento solicitado `{item['overlap_start']}..{item['overlap_end']}`."
            for item in selected
        )
    else:
        lines.append("- Ninguna.")
    lines.extend(["", "## Fuentes evaluadas", ""])
    for item in report.get("available_sources", []):
        state = "incluida" if item["included"] else "excluida"
        lines.append(
            f"- `{item['data_id']}`: {state}; rango `{item['min_date']}..{item['max_date']}`; tipo `{item['processing_type']}`; razón: {item['reason']}."
        )
    lines.extend(
        [
            "",
            "La selección documenta cobertura de fuentes, no define eventos ni elimina coincidencias potenciales entre sensores.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _manifest_key(manifest: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(manifest.get("source", "")),
        str(manifest.get("start_date", "")),
        str(manifest.get("end_date", "")),
    )


def _bbox_contains(bbox: Sequence[float], longitude: float, latitude: float) -> bool:
    west, south, east, north = (float(value) for value in bbox)
    return west <= longitude <= east and south <= latitude <= north


def _build_acquisition_audit(
    *,
    mode: str,
    requested: DateRange,
    bbox: Sequence[float],
    availability: Sequence[AvailabilityRange],
    selected: Sequence[AvailabilityRange],
    expected: Sequence[tuple[AvailabilityRange, DateRange]],
    manifests: Sequence[Mapping[str, Any]],
    errors: Sequence[str],
    scans: Sequence[SourceScan],
    filtered: FilterResult | None,
) -> dict[str, Any]:
    expected_keys = {
        (source.data_id, fragment.start.isoformat(), fragment.end.isoformat())
        for source, fragment in expected
    }
    successful = [manifest for manifest in manifests if manifest.get("status") in {"downloaded", "imported"}]
    failed = [manifest for manifest in manifests if manifest.get("status") == "error"]
    successful_keys = {_manifest_key(manifest) for manifest in successful}
    failed_keys = {_manifest_key(manifest) for manifest in failed}
    missing_keys = sorted(expected_keys - successful_keys - failed_keys)
    unexpected_success_keys = sorted(successful_keys - expected_keys) if mode == "api" else []
    rows_by_fragment = [
        {
            "source": manifest.get("source"),
            "start_date": manifest.get("start_date"),
            "end_date": manifest.get("end_date"),
            "status": manifest.get("status"),
            "record_count": manifest.get("record_count"),
            "raw_filename": manifest.get("raw_filename"),
        }
        for manifest in sorted(manifests, key=lambda item: _manifest_key(item))
    ]
    schema_invalid = [scan for scan in scans if not scan.schema_valid]
    valid_detections = [
        detection
        for scan in scans
        if scan.schema_valid
        for detection in scan.detections
    ]
    outside_query_bbox = 0
    for detection in valid_detections:
        if not detection.get("_coordinate_valid"):
            continue
        if not _bbox_contains(bbox, float(detection["longitude"]), float(detection["latitude"])):
            outside_query_bbox += 1

    source_overlaps: list[dict[str, str]] = []
    for first_index, first in enumerate(selected):
        first_overlap = first.overlap(requested)
        if first_overlap is None:
            continue
        for second in selected[first_index + 1 :]:
            second_overlap = second.overlap(requested)
            if second_overlap is None:
                continue
            overlap_start = max(first_overlap.start, second_overlap.start)
            overlap_end = min(first_overlap.end, second_overlap.end)
            if overlap_start <= overlap_end:
                source_overlaps.append(
                    {
                        "source_a": first.data_id,
                        "source_b": second.data_id,
                        "overlap_start": overlap_start.isoformat(),
                        "overlap_end": overlap_end.isoformat(),
                    }
                )

    if mode == "local_csv":
        coverage_complete = not errors
    else:
        coverage_complete = bool(expected_keys) and not errors and not missing_keys and expected_keys.issubset(successful_keys)
    schema_complete = not schema_invalid
    counts = filtered.counts if filtered is not None else {}
    instrument_counts = Counter(
        str(detection.get("instrument", "")) or "<MISSING>" for detection in valid_detections
    )
    source_counts = Counter(str(detection.get("firms_source", "")) for detection in valid_detections)
    return {
        "mode": mode,
        "requested_period": {"start_date": requested.start.isoformat(), "end_date": requested.end.isoformat()},
        "query_bbox_wgs84": list(bbox),
        "availability": [
            {"data_id": record.data_id, "min_date": record.min_date.isoformat(), "max_date": record.max_date.isoformat()}
            for record in availability
        ],
        "selected_sources": [record.data_id for record in selected],
        "coverage": {
            "expected_fragments": len(expected_keys),
            "successful_fragments": len(expected_keys & successful_keys),
            "failed_fragments": len(expected_keys & failed_keys),
            "missing_fragments": [
                {"source": source, "start_date": start, "end_date": end}
                for source, start, end in missing_keys
            ],
            "error_fragments": [
                {"source": source, "start_date": start, "end_date": end}
                for source, start, end in sorted(failed_keys & expected_keys)
            ],
            "unexpected_success_fragments": [
                {"source": source, "start_date": start, "end_date": end}
                for source, start, end in unexpected_success_keys
            ],
            "zero_row_fragments": [
                {
                    "source": row["source"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                }
                for row in rows_by_fragment
                if row["status"] in {"downloaded", "imported"} and row["record_count"] == 0
            ],
            "rows_by_fragment": rows_by_fragment,
            "source_date_overlaps": source_overlaps,
            "complete": coverage_complete,
            "download_errors": list(errors),
        },
        "schema": {
            "scanned_sources": len(scans),
            "invalid_sources": len(schema_invalid),
            "invalid_raw_rows": sum(scan.raw_record_count for scan in schema_invalid),
            "invalid_details": [
                {"source": scan.source, "raw_filename": scan.raw_path.name, "error": scan.schema_error}
                for scan in schema_invalid
            ],
            "all_scanned_sources_compatible": schema_complete,
        },
        "quality": {
            "raw_records_scanned": sum(scan.raw_record_count for scan in scans),
            "valid_schema_records_scanned": len(valid_detections),
            "outside_query_bbox_rows": outside_query_bbox,
            "invalid_coordinates": counts.get("total_invalid_coordinates"),
            "outside_requested_period": counts.get("total_discarded_outside_period"),
            "outside_cocle_polygon": counts.get("total_discarded_outside_cocle"),
            "final_cocle_rows": counts.get("total_final_detections"),
            "exact_duplicates": filtered.duplicate_summary if filtered is not None else None,
            "by_instrument": dict(sorted(instrument_counts.items())),
            "by_source": dict(sorted(source_counts.items())),
        },
        "ready_for_processed_cohort": coverage_complete and schema_complete,
        "limitations": [
            "Un fragmento descargado sin filas demuestra una respuesta vacía para esa consulta, no ausencia de fuego.",
            "Los solapamientos entre sensores son cobertura potencial y no son clusters ni eventos.",
            "El bbox es una preselección; el polígono de Coclé determina la salida final.",
            "Un archivo local puede contener filas fuera del bbox o del periodo; se auditan y no se presentan como cohorte final.",
        ],
    }


def _write_acquisition_audit(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    _write_json(json_path, report)
    coverage = report["coverage"]
    schema = report["schema"]
    quality = report["quality"]
    lines = [
        "# Auditoría de adquisición FIRMS",
        "",
        f"- Modo: `{report['mode']}`",
        f"- Periodo: `{report['requested_period']['start_date']}..{report['requested_period']['end_date']}`",
        f"- Fuentes seleccionadas: `{', '.join(report['selected_sources']) or 'ninguna'}`",
        f"- Fragmentos esperados/exitosos/fallidos: `{coverage['expected_fragments']}/{coverage['successful_fragments']}/{coverage['failed_fragments']}`",
        f"- Cobertura de adquisición completa: `{coverage['complete']}`",
        f"- Esquemas compatibles: `{schema['all_scanned_sources_compatible']}`",
        f"- Lista para generar cohorte procesada: `{report['ready_for_processed_cohort']}`",
        "",
        "## Calidad y exclusiones",
        "",
        f"- Filas raw escaneadas: `{quality['raw_records_scanned']}`",
        f"- Filas con esquema válido: `{quality['valid_schema_records_scanned']}`",
        f"- Coordenadas fuera del bbox de consulta: `{quality['outside_query_bbox_rows']}`",
        f"- Coordenadas inválidas: `{quality['invalid_coordinates']}`",
        f"- Fuera del periodo: `{quality['outside_requested_period']}`",
        f"- Fuera del polígono de Coclé: `{quality['outside_cocle_polygon']}`",
        f"- Filas finales dentro de Coclé: `{quality['final_cocle_rows']}`",
        f"- Duplicados exactos: `{quality['exact_duplicates']}`",
        "",
        "No se presenta este reporte como resultado científico ni como eventos de fuego; documenta solamente la adquisición y sus filtros previos.",
    ]
    raw_audit = report.get("raw_manifest_audit")
    if isinstance(raw_audit, dict):
        lines.extend(
            [
                "",
                "## Integridad de raw y manifests",
                "",
                f"- Archivos raw existentes: `{raw_audit.get('existing_raw_files')}`",
                f"- Manifests existentes: `{raw_audit.get('existing_manifest_files')}`",
                f"- Fragmentos vacios exitosos: `{len(raw_audit.get('empty_fragments', []))}`",
                f"- Fragmentos faltantes: `{len(raw_audit.get('missing_expected_fragments', []))}`",
                f"- Fragmentos fallidos: `{len(raw_audit.get('failed_fragments', []))}`",
                f"- Claves de manifest duplicadas: `{len(raw_audit.get('duplicate_manifest_keys', []))}`",
                f"- Hashes raw/manifest discordantes: `{len(raw_audit.get('raw_manifest_hash_mismatches', []))}`",
                f"- Archivos con esquema incompatible: `{len(raw_audit.get('schema_incompatible_files', []))}`",
                f"- Dias cubiertos sin detecciones: `{len(raw_audit.get('missing_detection_days', []))}`",
            ]
        )
        jan_audit = raw_audit.get("jan_1_to_11")
        if isinstance(jan_audit, dict):
            lines.extend(["", f"- Enero 1-11: {jan_audit.get('classification', '')}"])
    processed = report.get("processed_validation")
    if isinstance(processed, dict):
        missing = processed.get("missing_by_column", {})
        lines.extend(
            [
                "",
                "## Validacion del CSV procesado",
                "",
                f"- Filas procesadas: `{processed.get('rows')}`",
                f"- IDs unicos / grupos de IDs duplicados: `{processed.get('unique_detection_ids')}` / `{processed.get('duplicate_detection_id_groups')}`",
                f"- Duplicados exactos: `{processed.get('exact_duplicate_groups')}`",
                f"- Fuera de Cocle / fuera del periodo / filas 2026: `{processed.get('outside_cocle')}` / `{processed.get('outside_period')}` / `{processed.get('data_2026')}`",
                f"- Coincide con el filtro reproducido: `{processed.get('matches_recomputed_filter')}`",
                f"- FRP faltante / dia-noche faltante: `{missing.get('frp')}` / `{missing.get('daynight')}`",
            ]
        )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_cocle(options: RunOptions) -> RunResult:
    boundary = load_boundary(options.boundary_path, assume_crs=options.boundary_crs)
    bbox = boundary.bbox
    requested = DateRange(options.start_date, options.end_date)
    manifest_paths: list[Path] = []
    artifacts = []
    errors: list[str] = []
    availability: list[AvailabilityRange] = []
    selected_sources: list[AvailabilityRange] = []
    expected: list[tuple[AvailabilityRange, DateRange]] = []
    mode = "local_csv" if options.input_path else "api"

    if options.input_path:
        artifact = acquire_local_csv(
            options.input_path,
            options.raw_path or (options.raw_dir / "firms_local_cocle_2025.csv"),
            options.manifest_dir,
            options.source_label,
            requested,
            options.area,
            bbox,
            map_key=options.map_key,
        )
        artifacts.append(artifact)
        manifest_paths.append(artifact.manifest_path)
    else:
        if not options.map_key:
            raise AcquisitionError(
                "FIRMS_MAP_KEY no está disponible. Configure la variable de entorno o use --input con un CSV local."
            )
        fetcher = HttpFetcher(options.timeout_seconds, options.max_retries)
        availability_url = build_availability_url(options.map_key)
        availability_content = fetcher.fetch(availability_url)
        persist_raw_bytes(options.availability_output, availability_content)
        availability = parse_availability_csv(availability_content)
        selected_sources = select_sources(availability, requested, options.sources or None)
        expected = expected_fragments(availability, requested, options.sources or None)
        source_selection = _source_selection_report(availability, selected_sources, requested, options.sources or None)
        _write_json(options.source_selection_output, source_selection)
        _write_source_selection_markdown(source_selection, options.source_selection_markdown)
        downloaded, downloaded_manifests, download_errors = download_sources(
            availability,
            requested,
            bbox,
            options.area,
            options.raw_dir,
            options.manifest_dir,
            options.map_key,
            explicit_sources=options.sources or None,
            fetcher=fetcher,
        )
        artifacts.extend(downloaded)
        manifest_paths.extend(downloaded_manifests)
        errors.extend(download_errors)
    manifests = _read_manifests(manifest_paths, map_key=options.map_key)
    scans: list[SourceScan] = [scan_raw_artifact(artifact) for artifact in artifacts]
    invalid_scans = [scan for scan in scans if not scan.schema_valid]
    filtered: FilterResult | None = None
    if not errors and not invalid_scans:
        filtered = filter_to_cocle(scans, boundary, options.start_date, options.end_date)
    audit = _build_acquisition_audit(
        mode=mode,
        requested=requested,
        bbox=bbox,
        availability=availability,
        selected=selected_sources,
        expected=expected,
        manifests=manifests,
        errors=errors,
        scans=scans,
        filtered=filtered,
    )
    _write_acquisition_audit(audit, options.acquisition_audit_json, options.acquisition_audit_markdown)
    if errors:
        raise AcquisitionError(
            "La adquisición FIRMS quedó incompleta; no se genera una cohorte procesada. "
            "Revise la auditoría y los manifests de error."
        )
    if invalid_scans:
        details = "; ".join(
            f"{scan.source}/{scan.raw_path.name}: {scan.schema_error}" for scan in invalid_scans
        )
        raise AcquisitionError(f"Se rechazó el input FIRMS por esquema incompatible: {details}")
    if not audit["ready_for_processed_cohort"] or filtered is None:
        raise AcquisitionError(
            "La adquisición FIRMS no alcanzó cobertura completa y validación de esquema; no se genera una cohorte procesada."
        )
    write_detections(options.output_path, filtered.final_detections)
    profile = build_profile(
        filtered,
        manifests,
        options.start_date,
        options.end_date,
        distance_km=options.sensor_match_distance_km,
        time_minutes=options.sensor_match_time_minutes,
    )
    write_profile(profile, options.profile_json, options.profile_markdown)
    return RunResult(
        options.output_path,
        options.profile_json,
        options.profile_markdown,
        tuple(artifact.raw_path for artifact in artifacts),
        tuple(manifest_paths),
        profile,
        tuple(errors),
        options.acquisition_audit_json,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _default_parser()
    args = parser.parse_args(argv)
    # Preserve the first-stage complete-URL interface for existing users while
    # making structured date/source acquisition the documented path.
    if args.url:
        legacy_args = ["--url", args.url]
        if args.map_key:
            legacy_args.extend(["--map-key", args.map_key])
        return legacy_main(legacy_args)
    try:
        options = _options_from_args(args)
        result = run_cocle(options)
    except (AcquisitionError, BoundaryError, ConfigurationError, OSError, RawImmutabilityError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"processed: {result.output_path}")
    print(f"profile_json: {result.profile_json}")
    print(f"profile_markdown: {result.profile_markdown}")
    print(f"acquisition_audit: {result.acquisition_audit_json}")
    print(f"raw_files: {len(result.raw_paths)}")
    print(f"manifests: {len(result.manifest_paths)}")
    print(f"final_detections: {result.profile['counts']['total_final_detections']}")
    if result.errors:
        print(f"errors: {len(result.errors)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
