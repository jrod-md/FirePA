"""Reproducible NASA FIRMS acquisition and manifest handling."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .firms import RawImmutabilityError


FIRMS_API_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"
FIRMS_SCHEMA_VERSION = "firms-cocle-v1"
MAX_AREA_QUERY_DAYS = 5
TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
MANIFEST_REQUIRED_FIELDS = (
    "acquired_at_utc",
    "source",
    "start_date",
    "end_date",
    "area",
    "bbox",
    "url_sanitized",
    "sha256",
    "size_bytes",
    "record_count",
    "raw_file",
    "raw_filename",
    "schema_version",
    "status",
    "error_message",
)


class AcquisitionError(RuntimeError):
    """Raised when an official FIRMS request or response is unusable."""


class AvailabilityError(AcquisitionError):
    """Raised when source availability cannot be queried or parsed."""


class SourceSelectionError(AcquisitionError):
    """Raised when requested sources are not present in availability metadata."""


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class AvailabilityRange:
    data_id: str
    min_date: date
    max_date: date

    def overlap(self, requested: DateRange) -> DateRange | None:
        start = max(self.min_date, requested.start)
        end = min(self.max_date, requested.end)
        return DateRange(start, end) if start <= end else None


@dataclass(frozen=True)
class RawArtifact:
    source: str
    raw_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def split_date_range(start: date, end: date, max_days: int = MAX_AREA_QUERY_DAYS) -> list[DateRange]:
    """Split an inclusive range deterministically, respecting the FIRMS limit."""

    if start > end:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")
    if not 1 <= max_days <= MAX_AREA_QUERY_DAYS:
        raise ValueError(f"max_days debe estar entre 1 y {MAX_AREA_QUERY_DAYS}.")
    chunks: list[DateRange] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=max_days - 1))
        chunks.append(DateRange(cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _bbox_text(bbox: Sequence[float]) -> str:
    if len(bbox) != 4:
        raise ValueError("El bbox debe tener west,south,east,north.")
    west, south, east, north = (float(value) for value in bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("El bbox está fuera de los límites geográficos o tiene área cero.")
    return ",".join(format(value, ".12g") for value in (west, south, east, north))


def build_availability_url(map_key: str, sensor: str = "ALL") -> str:
    """Build the official availability URL; callers must not log the result."""

    if not map_key:
        raise ValueError("FIRMS_MAP_KEY es obligatorio para consultar disponibilidad.")
    return f"{FIRMS_API_BASE_URL}/data_availability/csv/{urllib.parse.quote(map_key, safe='')}/{sensor}"


def build_area_url(
    map_key: str,
    source: str,
    bbox: Sequence[float],
    date_range: DateRange,
) -> str:
    """Build one official Area API URL for at most five inclusive days."""

    if not map_key:
        raise ValueError("FIRMS_MAP_KEY es obligatorio para consultar FIRMS.")
    day_count = (date_range.end - date_range.start).days + 1
    if not 1 <= day_count <= MAX_AREA_QUERY_DAYS:
        raise ValueError("El fragmento FIRMS debe tener entre 1 y 5 días.")
    source_text = urllib.parse.quote(source, safe="_")
    return (
        f"{FIRMS_API_BASE_URL}/area/csv/{urllib.parse.quote(map_key, safe='')}/"
        f"{source_text}/{_bbox_text(bbox)}/{day_count}/{date_range.start.isoformat()}"
    )


def sanitize_url(url: str, map_key: str | None) -> str:
    """Remove the raw and percent-encoded key before an URL is persisted."""

    sanitized = url
    if map_key:
        for candidate in {map_key, urllib.parse.quote(map_key, safe="")}:
            sanitized = sanitized.replace(candidate, "<MAP_KEY_REDACTED>")
    return sanitized


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip()[:10])
    except (TypeError, ValueError) as exc:
        raise AvailabilityError("La respuesta de disponibilidad contiene una fecha inválida.") from exc


def parse_availability_csv(content: bytes) -> list[AvailabilityRange]:
    """Parse the documented data_id/min_date/max_date availability response."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AvailabilityError("La respuesta de disponibilidad no está en UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise AvailabilityError("La respuesta de disponibilidad no tiene encabezados.")
    normalized = {name.strip().lower(): name for name in reader.fieldnames if name}
    required = {"data_id", "min_date", "max_date"}
    if not required.issubset(normalized):
        raise AvailabilityError("La respuesta de disponibilidad no contiene el esquema oficial esperado.")

    records: list[AvailabilityRange] = []
    for row in reader:
        data_id = (row.get(normalized["data_id"]) or "").strip().upper()
        if not data_id:
            continue
        min_date = _parse_date(row.get(normalized["min_date"]) or "")
        max_date = _parse_date(row.get(normalized["max_date"]) or "")
        if min_date > max_date:
            raise AvailabilityError("La respuesta de disponibilidad contiene un intervalo invertido.")
        records.append(AvailabilityRange(data_id, min_date, max_date))
    if not records:
        raise AvailabilityError("La respuesta de disponibilidad no contiene fuentes.")
    return records


def select_sources(
    availability: Iterable[AvailabilityRange],
    requested: DateRange,
    explicit_sources: Sequence[str] | None = None,
) -> list[AvailabilityRange]:
    """Select sources from the response, preferring historical VIIRS SP only."""

    records = list(availability)
    by_id = {record.data_id.upper(): record for record in records}
    if explicit_sources:
        selected: list[AvailabilityRange] = []
        missing: list[str] = []
        for source in explicit_sources:
            key = source.strip().upper()
            record = by_id.get(key)
            if not (key.startswith("VIIRS_") and key.endswith("_SP")):
                missing.append(key)
            elif record is None or record.overlap(requested) is None:
                missing.append(key)
            elif record not in selected:
                selected.append(record)
        if missing:
            raise SourceSelectionError(
                "Las fuentes solicitadas no aparecen disponibles para el período: "
                + ", ".join(missing)
            )
        return selected

    selected = [
        record
        for record in records
        if record.data_id.startswith("VIIRS_")
        and record.data_id.endswith("_SP")
        and record.overlap(requested) is not None
    ]
    if not selected:
        raise SourceSelectionError(
            "La consulta de disponibilidad no reportó una fuente VIIRS *_SP que cubra el período solicitado. "
            "No se seleccionan fuentes NRT automáticamente."
        )
    return sorted(selected, key=lambda record: record.data_id)


def expected_fragments(
    availability: Sequence[AvailabilityRange],
    requested: DateRange,
    explicit_sources: Sequence[str] | None = None,
    max_query_days: int = MAX_AREA_QUERY_DAYS,
) -> list[tuple[AvailabilityRange, DateRange]]:
    """Return the exact source/fragment plan implied by availability metadata."""

    fragments: list[tuple[AvailabilityRange, DateRange]] = []
    for source_record in select_sources(availability, requested, explicit_sources):
        overlap = source_record.overlap(requested)
        if overlap is None:
            continue
        fragments.extend((source_record, fragment) for fragment in split_date_range(overlap.start, overlap.end, max_query_days))
    return fragments


def _is_transient(error: BaseException) -> bool:
    return isinstance(error, urllib.error.HTTPError) and error.code in TRANSIENT_HTTP_CODES or isinstance(
        error, (urllib.error.URLError, TimeoutError)
    )


class HttpFetcher:
    """Sequential bounded-retry fetcher for official FIRMS responses."""

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0 or max_retries < 0 or backoff_seconds < 0:
            raise ValueError("timeout, reintentos y backoff deben ser no negativos; timeout debe ser positivo.")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.opener = opener
        self.sleeper = sleeper

    def fetch(self, url: str) -> bytes:
        last_error: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            response: Any = None
            try:
                response = self.opener(url, timeout=self.timeout_seconds)
                status = getattr(response, "status", None)
                if status is None and hasattr(response, "getcode"):
                    status = response.getcode()
                if status is not None and int(status) >= 400:
                    raise urllib.error.HTTPError(url, int(status), "HTTP error", hdrs=None, fp=None)
                content = response.read()
                normalized_prefix = content.lstrip().lower()
                if not content or normalized_prefix.startswith(
                    (b"<html", b"<!doctype", b"{\"error", b"{\n  \"error")
                ):
                    raise AcquisitionError("La respuesta HTTP no parece ser un CSV FIRMS válido.")
                return content
            except AcquisitionError:
                raise
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= self.max_retries or not _is_transient(exc):
                    break
                self.sleeper(self.backoff_seconds * (2**attempt))
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        # Do not chain the original HTTP/URL exception: urllib exceptions carry
        # the full request URL, which includes the private MAP_KEY.
        raise AcquisitionError("La solicitud FIRMS falló después de los reintentos permitidos.") from None


def count_csv_records(content: bytes) -> int:
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if not reader.fieldnames or any(not field or not field.strip() for field in reader.fieldnames):
            raise ValueError("missing headers")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("extra fields")
        return len(rows)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise AcquisitionError("La respuesta FIRMS no puede contarse como CSV.") from exc


def persist_raw_bytes(path: Path, content: bytes) -> None:
    """Write once; identical bytes are reusable, different bytes are rejected."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise RawImmutabilityError(f"El raw ya existe con contenido diferente: {path.name}")
        return
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise RawImmutabilityError(f"El raw fue creado concurrentemente: {path.name}") from exc


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "source"


def _manifest_path(manifest_dir: Path, raw_name: str) -> Path:
    return manifest_dir / f"{raw_name}.manifest.json"


def validate_manifest(manifest: Mapping[str, Any], map_key: str | None = None) -> None:
    """Validate the stable manifest contract before it is written or consumed."""

    missing = [field for field in MANIFEST_REQUIRED_FIELDS if field not in manifest]
    if missing:
        raise AcquisitionError("Manifest incompleto; faltan campos: " + ", ".join(missing))
    status = manifest.get("status")
    if status not in {"downloaded", "imported", "error"}:
        raise AcquisitionError("Manifest con estado inválido.")
    if not isinstance(manifest.get("source"), str) or not manifest["source"].strip():
        raise AcquisitionError("Manifest sin fuente.")
    if not isinstance(manifest.get("bbox"), list) or len(manifest["bbox"]) != 4:
        raise AcquisitionError("Manifest con bbox inválido.")
    if status in {"downloaded", "imported"}:
        if not isinstance(manifest.get("sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest["sha256"]
        ):
            raise AcquisitionError("Manifest de éxito sin SHA-256 válido.")
        if not isinstance(manifest.get("size_bytes"), int) or manifest["size_bytes"] < 0:
            raise AcquisitionError("Manifest de éxito sin tamaño válido.")
        if not isinstance(manifest.get("record_count"), int) or manifest["record_count"] < 0:
            raise AcquisitionError("Manifest de éxito sin cantidad de filas válida.")
    if status == "error" and not manifest.get("error_message"):
        raise AcquisitionError("Manifest de error sin descripción del error.")
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    if map_key:
        candidates = {map_key, urllib.parse.quote(map_key, safe="")}
        if any(candidate and candidate in serialized for candidate in candidates):
            raise AcquisitionError("El manifest contiene una credencial sin sanitizar.")


def write_manifest(path: Path, manifest: dict[str, Any], map_key: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_manifest(manifest, map_key=map_key)
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")


def _base_manifest(
    source: str,
    date_range: DateRange,
    area: str,
    bbox: Sequence[float],
    raw_name: str,
    sanitized_url: str | None,
) -> dict[str, Any]:
    return {
        "acquired_at_utc": utc_now_text(),
        "source": source,
        "start_date": date_range.start.isoformat(),
        "end_date": date_range.end.isoformat(),
        "area": area,
        "bbox": list(bbox),
        "url_sanitized": sanitized_url,
        "sha256": None,
        "size_bytes": None,
        "record_count": None,
        "raw_file": raw_name,
        "raw_filename": raw_name,
        "schema_version": FIRMS_SCHEMA_VERSION,
        "status": "error",
        "error_message": None,
    }


def acquire_local_csv(
    input_path: Path,
    raw_path: Path,
    manifest_dir: Path,
    source: str,
    date_range: DateRange,
    area: str,
    bbox: Sequence[float],
    map_key: str | None = None,
) -> RawArtifact:
    if not input_path.exists() or not input_path.is_file():
        raise AcquisitionError(f"No existe el CSV local: {input_path}")
    content = input_path.read_bytes()
    persist_raw_bytes(raw_path, content)
    manifest = _base_manifest(source, date_range, area, bbox, raw_path.name, None)
    manifest.update(
        {
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
            "record_count": count_csv_records(content),
            "status": "imported",
        }
    )
    manifest_path = _manifest_path(manifest_dir, raw_path.name)
    write_manifest(manifest_path, manifest, map_key=map_key)
    return RawArtifact(source, raw_path, manifest_path, manifest)


def download_sources(
    availability: Sequence[AvailabilityRange],
    requested: DateRange,
    bbox: Sequence[float],
    area: str,
    raw_dir: Path,
    manifest_dir: Path,
    map_key: str,
    explicit_sources: Sequence[str] | None = None,
    fetcher: HttpFetcher | None = None,
    max_query_days: int = MAX_AREA_QUERY_DAYS,
) -> tuple[list[RawArtifact], list[Path], list[str]]:
    """Download each source/chunk separately and write success/error manifests."""

    selected = select_sources(availability, requested, explicit_sources)
    fetcher = fetcher or HttpFetcher()
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[RawArtifact] = []
    manifest_paths: list[Path] = []
    errors: list[str] = []

    for source_record in selected:
        overlap = source_record.overlap(requested)
        if overlap is None:
            continue
        for fragment in split_date_range(overlap.start, overlap.end, max_query_days):
            safe_source = _safe_filename(source_record.data_id.lower())
            raw_name = f"firms_{safe_source}_{fragment.start.isoformat()}_{fragment.end.isoformat()}.csv"
            raw_path = raw_dir / raw_name
            manifest_path = _manifest_path(manifest_dir, raw_name)
            url = build_area_url(map_key, source_record.data_id, bbox, fragment)
            manifest = _base_manifest(
                source_record.data_id,
                fragment,
                area,
                bbox,
                raw_name,
                sanitize_url(url, map_key),
            )
            try:
                content = fetcher.fetch(url)
                persist_raw_bytes(raw_path, content)
                manifest.update(
                    {
                        "sha256": sha256_bytes(content),
                        "size_bytes": len(content),
                        "record_count": count_csv_records(content),
                        "status": "downloaded",
                    }
                )
                write_manifest(manifest_path, manifest, map_key=map_key)
                manifest_paths.append(manifest_path)
                artifacts.append(RawArtifact(source_record.data_id, raw_path, manifest_path, manifest))
            except (AcquisitionError, OSError, RawImmutabilityError) as exc:
                manifest["status"] = "error"
                manifest["error_message"] = str(exc)
                write_manifest(manifest_path, manifest, map_key=map_key)
                manifest_paths.append(manifest_path)
                errors.append(f"{source_record.data_id} {fragment.start.isoformat()}..{fragment.end.isoformat()}: {exc}")
    return artifacts, manifest_paths, errors
