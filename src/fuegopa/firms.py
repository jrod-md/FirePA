"""First-stage FIRMS CSV acquisition, validation and normalization.

This module deliberately stops at a row-level normalized FIRMS table. It does
not infer events, cluster detections, create labels, or train a model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import Settings


class SchemaError(ValueError):
    """Raised when an input CSV cannot satisfy the FIRMS import contract."""


class SourceError(RuntimeError):
    """Raised when a local or remote source cannot be acquired safely."""


class RawImmutabilityError(RuntimeError):
    """Raised when a raw path already contains different bytes."""


REQUIRED_FIELDS: tuple[str, ...] = (
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "frp",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
    "acq_date": ("acq_date", "acquisition_date", "date"),
    "acq_time": ("acq_time", "acquisition_time", "time"),
    "satellite": ("satellite", "platform"),
    "instrument": ("instrument", "sensor"),
    "confidence": ("confidence", "conf"),
    "frp": ("frp", "fire_radiative_power"),
}

OUTPUT_FIELDS: tuple[str, ...] = (
    "source_row_number",
    "latitude",
    "longitude",
    "coordinate_valid",
    "acq_date",
    "acq_time",
    "acq_datetime_utc",
    "satellite",
    "instrument",
    "confidence",
    "confidence_numeric",
    "frp",
    "raw_sha256",
)

MISSING_TOKENS = frozenset({"", "na", "n/a", "nan", "none", "null", "no data"})


def _normalize_header(value: str) -> str:
    text = value.lstrip("\ufeff").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def is_missing(value: Any) -> bool:
    return _clean(value).lower() in MISSING_TOKENS


def validate_required_columns(headers: Sequence[str]) -> dict[str, str]:
    """Return canonical-to-source column mapping or reject the schema."""

    if not headers:
        raise SchemaError("El CSV no contiene encabezados.")

    normalized: dict[str, str] = {}
    duplicates: list[str] = []
    for header in headers:
        key = _normalize_header(header)
        if not key:
            raise SchemaError("El CSV contiene un encabezado vacío.")
        if key in normalized:
            duplicates.append(header)
        normalized[key] = header
    if duplicates:
        raise SchemaError(
            "El CSV contiene encabezados duplicados después de normalizar: "
            + ", ".join(duplicates)
        )

    mapping: dict[str, str] = {}
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        candidates = [normalized[alias] for alias in FIELD_ALIASES[field] if alias in normalized]
        if not candidates:
            missing.append(field)
        elif len(candidates) > 1:
            raise SchemaError(
                f"El campo lógico '{field}' es ambiguo; se recibieron: {candidates}."
            )
        else:
            mapping[field] = candidates[0]

    if missing:
        raise SchemaError(
            "Esquema FIRMS incompatible. Faltan columnas obligatorias: "
            + ", ".join(missing)
            + ". Se aceptan alias explícitos definidos por el importador."
        )
    return mapping


def _parse_number(value: Any) -> float | None:
    if is_missing(value):
        return None
    try:
        parsed = float(_clean(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def validate_coordinates(latitude: Any, longitude: Any) -> bool:
    """Return whether both coordinates are numeric and globally valid."""

    lat = _parse_number(latitude)
    lon = _parse_number(longitude)
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    return format(value, ".15g")


def parse_acquisition_date(value: Any) -> date | None:
    """Parse common FIRMS date spellings without guessing a timezone."""

    if is_missing(value):
        return None
    text = _clean(value)
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    text = text.replace("/", "-")
    for candidate, fmt in ((text, None), (text, "%Y%m%d")):
        try:
            if fmt:
                return datetime.strptime(candidate, fmt).date()
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _parse_acquisition_time(value: Any) -> time | None:
    if is_missing(value):
        return None
    text = _clean(value)
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) not in (2, 3):
                return None
            hour, minute = int(parts[0]), int(parts[1])
            second = int(parts[2]) if len(parts) == 3 else 0
            return time(hour, minute, second)
        if not text.isdigit():
            return None
        if len(text) <= 4:
            digits = text.zfill(4)
            return time(int(digits[:2]), int(digits[2:]))
        if len(text) == 6:
            return time(int(text[:2]), int(text[2:4]), int(text[4:]))
    except ValueError:
        return None
    return None


def parse_acquisition_datetime(acq_date: Any, acq_time: Any) -> datetime | None:
    """Parse a FIRMS acquisition date/time as a naive UTC datetime.

    The importer does not convert timezones. The FIRMS input contract is
    expected to provide acquisition time in UTC; this assumption remains
    visible in the output field name and must be confirmed for any alternate
    source export.
    """

    parsed_date = parse_acquisition_date(acq_date)
    parsed_time = _parse_acquisition_time(acq_time)
    if parsed_date is None or parsed_time is None:
        return None
    return datetime.combine(parsed_date, parsed_time)


def _normalize_time(value: Any) -> str:
    parsed = _parse_acquisition_time(value)
    return parsed.strftime("%H:%M:%S") if parsed else ""


def _normalize_text(value: Any, uppercase: bool = False) -> str:
    if is_missing(value):
        return ""
    text = _clean(value)
    return text.upper() if uppercase else text.lower()


def _normalize_confidence(value: Any) -> tuple[str, str]:
    if is_missing(value):
        return "", ""
    numeric = _parse_number(value)
    if numeric is not None:
        formatted = _format_number(numeric)
        return formatted, formatted
    return _normalize_text(value), ""


def _read_raw_rows(raw_path: Path) -> tuple[list[str], dict[str, str], list[dict[str, str]]]:
    try:
        with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames
            if headers is None:
                raise SchemaError("El CSV no contiene encabezados.")
            mapping = validate_required_columns(headers)
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise SchemaError("El CSV no está codificado como UTF-8 compatible.") from exc

    if any(None in row for row in rows):
        raise SchemaError("El CSV contiene filas con más campos que sus encabezados.")
    return headers, mapping, rows


def _missing_counts(rows: Iterable[Mapping[str, Any]], mapping: Mapping[str, str]) -> dict[str, int]:
    return {
        field: sum(is_missing(row.get(source_column)) for row in rows)
        for field, source_column in mapping.items()
    }


def _instrument_key(value: str) -> str:
    return value or "__missing__"


def normalize_csv(raw_path: Path, processed_path: Path, report_path: Path, raw_sha256: str) -> dict[str, Any]:
    """Validate and normalize a copied raw CSV, returning the quality report."""

    headers, mapping, rows = _read_raw_rows(raw_path)
    exact_counts = Counter(tuple(row.get(header, "") for header in headers) for row in rows)
    duplicate_groups = sum(count > 1 for count in exact_counts.values())
    duplicate_rows = sum(count - 1 for count in exact_counts.values() if count > 1)

    processed_rows: list[dict[str, str]] = []
    invalid_coordinate_rows = 0
    invalid_date_rows = 0
    invalid_time_rows = 0
    date_values: list[str] = []
    instrument_counts: Counter[str] = Counter()

    for row_number, row in enumerate(rows, start=1):
        raw_lat = row.get(mapping["latitude"])
        raw_lon = row.get(mapping["longitude"])
        lat = _parse_number(raw_lat)
        lon = _parse_number(raw_lon)
        coordinate_valid = validate_coordinates(raw_lat, raw_lon)
        if (not is_missing(raw_lat) or not is_missing(raw_lon)) and not coordinate_valid:
            invalid_coordinate_rows += 1

        parsed_date = parse_acquisition_date(row.get(mapping["acq_date"]))
        parsed_time = _parse_acquisition_time(row.get(mapping["acq_time"]))
        if not is_missing(row.get(mapping["acq_date"])) and parsed_date is None:
            invalid_date_rows += 1
        if not is_missing(row.get(mapping["acq_time"])) and parsed_time is None:
            invalid_time_rows += 1
        normalized_date = parsed_date.isoformat() if parsed_date else ""
        normalized_time = parsed_time.strftime("%H:%M:%S") if parsed_time else ""
        if normalized_date:
            date_values.append(normalized_date)

        satellite = _normalize_text(row.get(mapping["satellite"]), uppercase=True)
        instrument = _normalize_text(row.get(mapping["instrument"]), uppercase=True)
        confidence, confidence_numeric = _normalize_confidence(row.get(mapping["confidence"]))
        frp = _format_number(_parse_number(row.get(mapping["frp"])))
        parsed_datetime = (
            datetime.combine(parsed_date, parsed_time).strftime("%Y-%m-%dT%H:%M:%SZ")
            if parsed_date and parsed_time
            else ""
        )
        instrument_counts[_instrument_key(instrument)] += 1

        processed_rows.append(
            {
                "source_row_number": str(row_number),
                "latitude": _format_number(lat) if coordinate_valid else "",
                "longitude": _format_number(lon) if coordinate_valid else "",
                "coordinate_valid": "true" if coordinate_valid else "false",
                "acq_date": normalized_date,
                "acq_time": normalized_time,
                "acq_datetime_utc": parsed_datetime,
                "satellite": satellite,
                "instrument": instrument,
                "confidence": confidence,
                "confidence_numeric": confidence_numeric,
                "frp": frp,
                "raw_sha256": raw_sha256,
            }
        )

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    with processed_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(processed_rows)

    report: dict[str, Any] = {
        "stage": "firms_import_normalization",
        "row_count": len(rows),
        "raw_sha256": raw_sha256,
        "temporal_range": {
            "min_acq_date": min(date_values) if date_values else None,
            "max_acq_date": max(date_values) if date_values else None,
            "valid_date_rows": len(date_values),
        },
        "missing_values": _missing_counts(rows, mapping),
        "invalid_coordinates": {"rows": invalid_coordinate_rows},
        "invalid_dates": {"rows": invalid_date_rows},
        "invalid_times": {"rows": invalid_time_rows},
        "exact_duplicates": {
            "groups": duplicate_groups,
            "rows_after_first_occurrence": duplicate_rows,
        },
        "instrument_distribution": dict(sorted(instrument_counts.items())),
        "notes": [
            "Las coordenadas inválidas se conservan como coordinate_valid=false y valores vacíos en el procesado.",
            "Las categorías de confidence se normalizan a minúsculas; no se asignan puntajes inventados a low/nominal/high.",
            "El archivo raw se identifica por SHA-256 y no se sobrescribe con bytes diferentes.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return report


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _persist_raw(raw_path: Path, content: bytes) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        if not raw_path.is_file():
            raise RawImmutabilityError(f"La ruta raw no es un archivo: {raw_path}")
        if raw_path.read_bytes() != content:
            raise RawImmutabilityError(
                f"El archivo raw ya existe con bytes diferentes: {raw_path}. "
                "Use otra ruta raw; el importador no sobrescribe raw."
            )
        return
    try:
        with raw_path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise RawImmutabilityError(
            f"La ruta raw fue creada concurrentemente; no se sobrescribe: {raw_path}"
        ) from exc


def _resolve_remote_url(url: str, map_key: str | None) -> str:
    if "{map_key}" in url:
        if not map_key:
            raise SourceError(
                "La URL FIRMS contiene {map_key}, pero no hay FIRMS_MAP_KEY ni --map-key. "
                "Proporcione la clave por entorno/CLI o use --input con un CSV local."
            )
        return url.replace("{map_key}", urllib.parse.quote(map_key, safe=""))
    return url


def _acquire_bytes(input_path: Path | None, url: str | None, map_key: str | None) -> tuple[bytes, str]:
    if input_path and url:
        raise SourceError("Proporcione solo --input o --url, no ambos.")
    if not input_path and not url:
        raise SourceError(
            "No hay fuente de entrada. Use --input para un CSV local o --url para una descarga FIRMS."
        )
    if input_path:
        if not input_path.exists() or not input_path.is_file():
            raise SourceError(f"No existe el CSV local: {input_path}")
        try:
            return input_path.read_bytes(), "local_csv"
        except OSError as exc:
            raise SourceError(f"No se pudo leer el CSV local: {input_path}") from exc

    resolved_url = _resolve_remote_url(url or "", map_key)
    try:
        with urllib.request.urlopen(resolved_url, timeout=30) as response:
            return response.read(), "url"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(
            "No se pudo descargar la URL FIRMS proporcionada; revise la URL, conectividad y credenciales."
        ) from exc


@dataclass(frozen=True)
class PipelineResult:
    raw_path: Path
    processed_path: Path
    report_path: Path
    report: dict[str, Any]


def run_pipeline(
    settings: Settings,
    input_path: Path | None = None,
    url: str | None = None,
    map_key: str | None = None,
) -> PipelineResult:
    """Acquire, preserve, validate and normalize one FIRMS CSV."""

    settings.create_directories()
    content, source_kind = _acquire_bytes(
        input_path or settings.input_path,
        url or settings.firms_url,
        map_key or settings.firms_map_key,
    )
    _persist_raw(settings.raw_path, content)
    digest = _sha256(content)
    report = normalize_csv(settings.raw_path, settings.processed_path, settings.report_path, digest)
    report["source_kind"] = source_kind
    report["raw_file"] = settings.raw_path.name
    report["processed_file"] = settings.processed_path.name
    with settings.report_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return PipelineResult(
        raw_path=settings.raw_path,
        processed_path=settings.processed_path,
        report_path=settings.report_path,
        report=report,
    )


def _path_override(value: str | None, project_root: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Adquiere/importa CSV FIRMS, conserva raw y genera normalización + calidad."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="CSV FIRMS local; no se modifica.")
    source.add_argument("--url", help="URL CSV FIRMS proporcionada por el usuario.")
    parser.add_argument(
        "--map-key",
        help="Clave para sustituir literalmente {map_key} en --url; preferir FIRMS_MAP_KEY.",
    )
    parser.add_argument("--project-root", type=Path, help="Raíz del proyecto para rutas relativas.")
    parser.add_argument("--raw-path", help="Ruta del raw inmutable.")
    parser.add_argument("--processed-path", help="Ruta del CSV normalizado.")
    parser.add_argument("--report-path", help="Ruta del reporte JSON de calidad.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env(project_root=args.project_root)
    overrides: dict[str, Any] = {}
    raw_path = _path_override(args.raw_path, settings.project_root)
    processed_path = _path_override(args.processed_path, settings.project_root)
    report_path = _path_override(args.report_path, settings.project_root)
    if raw_path:
        overrides["raw_path"] = raw_path
    if processed_path:
        overrides["processed_path"] = processed_path
    if report_path:
        overrides["report_path"] = report_path
    if overrides:
        settings = replace(settings, **overrides)

    # Explicit CLI source selection takes precedence over a source configured
    # in the environment; this keeps CLI and environment configuration
    # composable without accidentally sending two sources to the pipeline.
    input_path = args.input.resolve() if args.input else (None if args.url else settings.input_path)
    source_url = args.url if args.url else (None if args.input else settings.firms_url)
    try:
        result = run_pipeline(
            settings,
            input_path=input_path,
            url=source_url,
            map_key=args.map_key or settings.firms_map_key,
        )
    except (RawImmutabilityError, SchemaError, SourceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"raw: {result.raw_path}")
    print(f"processed: {result.processed_path}")
    print(f"quality_report: {result.report_path}")
    print(f"rows: {result.report['row_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
