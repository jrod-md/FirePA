from __future__ import annotations

import csv
import json
import math
import sys
import urllib.error
from datetime import date
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.acquisition import (  # noqa: E402
    AcquisitionError,
    AvailabilityRange,
    DateRange,
    HttpFetcher,
    MAX_AREA_QUERY_DAYS,
    acquire_local_csv,
    build_area_url,
    download_sources,
    parse_availability_csv,
    persist_raw_bytes,
    sanitize_url,
    select_sources,
    split_date_range,
    validate_manifest,
)
from fuegopa.cocle import filter_to_cocle, scan_raw_artifact, write_detections  # noqa: E402
from fuegopa.firms import RawImmutabilityError  # noqa: E402
from fuegopa.geo import BoundaryError, load_boundary  # noqa: E402
from fuegopa.pipeline import main  # noqa: E402
from fuegopa.profile import build_profile  # noqa: E402


REQUIRED_HEADERS = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "frp",
    "daynight",
    "version",
    "type",
]


def write_csv(path: Path, rows: list[dict[str, str]], headers: list[str] | None = None) -> bytes:
    headers = headers or REQUIRED_HEADERS
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def firms_row(**overrides: str) -> dict[str, str]:
    row = {
        "latitude": "8.5",
        "longitude": "-79.5",
        "acq_date": "2025-01-02",
        "acq_time": "0345",
        "satellite": "N20",
        "instrument": "VIIRS",
        "confidence": "nominal",
        "frp": "12.5",
        "daynight": "D",
        "version": "1.0",
        "type": "0",
    }
    row.update(overrides)
    return row


def write_boundary(path: Path, *, crs: str | None = "EPSG:4326", coordinates=None) -> Path:
    coordinates = coordinates or [[[-80.0, 8.0], [-79.0, 8.0], [-79.0, 9.0], [-80.0, 9.0], [-80.0, 8.0]]]
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Coclé"},
                "geometry": {"type": "Polygon", "coordinates": coordinates},
            }
        ],
    }
    if crs is not None:
        document["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def local_artifact(tmp_path: Path, rows: list[dict[str, str]], source: str = "LOCAL_CSV"):
    input_path = tmp_path / "input.csv"
    write_csv(input_path, rows)
    return acquire_local_csv(
        input_path,
        tmp_path / "data" / "raw" / f"{source.lower()}.csv",
        tmp_path / "data" / "raw" / "manifests",
        source,
        DateRange(date(2025, 1, 1), date(2025, 4, 30)),
        "cocle",
        [-80.0, 8.0, -79.0, 9.0],
    )


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content = content
        self.status = status
        self.closed = False

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        self.closed = True


def test_date_splitting_and_sanitized_area_url() -> None:
    chunks = split_date_range(date(2025, 1, 1), date(2025, 1, 12))
    assert [(chunk.start, chunk.end) for chunk in chunks] == [
        (date(2025, 1, 1), date(2025, 1, 5)),
        (date(2025, 1, 6), date(2025, 1, 10)),
        (date(2025, 1, 11), date(2025, 1, 12)),
    ]
    assert all((chunk.end - chunk.start).days + 1 <= MAX_AREA_QUERY_DAYS for chunk in chunks)
    raw_url = build_area_url(
        "secret-map-key",
        "VIIRS_SNPP_SP",
        (-80, 8, -79, 9),
        DateRange(date(2025, 1, 1), date(2025, 1, 5)),
    )
    safe_url = sanitize_url(raw_url, "secret-map-key")
    assert "secret-map-key" in raw_url
    assert "secret-map-key" not in safe_url
    assert "<MAP_KEY_REDACTED>" in safe_url
    assert "/VIIRS_SNPP_SP/-80,8,-79,9/5/2025-01-01" in safe_url


def test_availability_schema_and_source_selection() -> None:
    content = (
        "data_id,min_date,max_date\n"
        "VIIRS_SNPP_SP,2012-01-20,2026-12-31\n"
        "VIIRS_NOAA20_SP,2018-04-01,2026-12-31\n"
        "VIIRS_NOAA21_NRT,2024-01-17,2026-12-31\n"
    ).encode()
    availability = parse_availability_csv(content)
    requested = DateRange(date(2025, 1, 1), date(2025, 4, 30))
    selected = select_sources(availability, requested)
    assert [record.data_id for record in selected] == ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP"]
    assert [record.data_id for record in select_sources(availability, requested, ["VIIRS_SNPP_SP"])] == [
        "VIIRS_SNPP_SP"
    ]
    with pytest.raises(AcquisitionError):
        select_sources(availability, requested, ["MODIS_SP"])


def test_http_fetch_retries_timeout_and_does_not_leak_url() -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def opener(url: str, timeout: float):
        attempts.append(url)
        if len(attempts) == 1:
            raise TimeoutError("timed out")
        return FakeResponse(b"latitude,longitude\n8.5,-79.5\n")

    fetcher = HttpFetcher(
        timeout_seconds=3,
        max_retries=1,
        backoff_seconds=0.25,
        opener=opener,
        sleeper=sleeps.append,
    )
    assert fetcher.fetch("https://example.test/secret-map-key") == b"latitude,longitude\n8.5,-79.5\n"
    assert len(attempts) == 2
    assert sleeps == [0.25]

    def http_error(url: str, timeout: float):
        raise urllib.error.HTTPError(url, 500, "server error", hdrs=None, fp=None)

    failing = HttpFetcher(
        timeout_seconds=3,
        max_retries=1,
        backoff_seconds=0,
        opener=http_error,
        sleeper=lambda _: None,
    )
    with pytest.raises(AcquisitionError) as error:
        failing.fetch("https://example.test/secret-map-key")
    assert "secret-map-key" not in str(error.value)


def test_http_invalid_response_is_rejected() -> None:
    fetcher = HttpFetcher(opener=lambda url, timeout: FakeResponse(b"<html>error</html>"))
    with pytest.raises(AcquisitionError):
        fetcher.fetch("https://example.test/area")


def test_raw_is_immutable_and_manifest_contract_hides_key(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.csv"
    persist_raw_bytes(raw_path, b"header\nvalue\n")
    persist_raw_bytes(raw_path, b"header\nvalue\n")
    with pytest.raises(RawImmutabilityError):
        persist_raw_bytes(raw_path, b"header\nother\n")

    artifact = local_artifact(tmp_path, [firms_row()])
    manifest_text = artifact.manifest_path.read_text(encoding="utf-8")
    assert "secret-map-key" not in manifest_text
    validate_manifest(artifact.manifest)
    unsafe = dict(artifact.manifest)
    unsafe["url_sanitized"] = "https://example.test/secret-map-key"
    with pytest.raises(AcquisitionError):
        validate_manifest(unsafe, map_key="secret-map-key")


def test_download_separates_sources_and_fragments_without_key_in_manifests(tmp_path: Path) -> None:
    csv_by_source = {
        "VIIRS_SNPP_SP": b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n8.5,-79.5,2025-01-01,0300,SNPP,VIIRS,nominal,10\n",
        "VIIRS_NOAA20_SP": b"latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n8.5,-79.5,2025-01-01,0400,N20,VIIRS,nominal,11\n",
    }
    requested = DateRange(date(2025, 1, 1), date(2025, 1, 7))
    availability = [
        AvailabilityRange(source, date(2025, 1, 1), date(2025, 1, 7))
        for source in csv_by_source
    ]
    requested_urls: list[str] = []

    class Fetcher:
        def fetch(self, url: str) -> bytes:
            requested_urls.append(url)
            return next(content for source, content in csv_by_source.items() if source in url)

    artifacts, manifest_paths, errors = download_sources(
        availability,
        requested,
        (-80, 8, -79, 9),
        "cocle",
        tmp_path / "raw",
        tmp_path / "manifests",
        "secret-map-key",
        fetcher=Fetcher(),
    )
    assert not errors
    assert len(artifacts) == 4
    assert len(manifest_paths) == 4
    assert {artifact.source for artifact in artifacts} == set(csv_by_source)
    assert all("secret-map-key" in url for url in requested_urls)
    assert all("secret-map-key" not in path.read_text(encoding="utf-8") for path in manifest_paths)
    assert all("<MAP_KEY_REDACTED>" in path.read_text(encoding="utf-8") for path in manifest_paths)
    assert len({artifact.raw_path.name for artifact in artifacts}) == 4


def test_boundary_point_in_polygon_edges_and_missing_crs(tmp_path: Path) -> None:
    boundary = load_boundary(write_boundary(tmp_path / "cocle.geojson"))
    assert boundary.normalized_crs == "EPSG:4326"
    assert boundary.contains(-79.5, 8.5)
    assert boundary.contains(-80.0, 8.0)
    assert boundary.contains(-79.0, 9.0)
    assert not boundary.contains(-78.9999, 8.5)
    assert boundary.bbox == (-80.0, 8.0, -79.0, 9.0)

    no_crs = write_boundary(tmp_path / "no-crs.geojson", crs=None)
    with pytest.raises(BoundaryError):
        load_boundary(no_crs)
    assert load_boundary(no_crs, assume_crs="EPSG:4326").contains(-79.5, 8.5)


def test_boundary_reprojects_epsg_3857_to_epsg_4326(tmp_path: Path) -> None:
    def mercator(longitude: float, latitude: float) -> list[float]:
        radius = 6378137.0
        return [
            radius * math.radians(longitude),
            radius * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2)),
        ]

    ring = [mercator(-80, 8), mercator(-79, 8), mercator(-79, 9), mercator(-80, 9), mercator(-80, 8)]
    boundary = load_boundary(write_boundary(tmp_path / "web-mercator.geojson", crs="EPSG:3857", coordinates=[ring]))
    assert boundary.source_crs == "EPSG:3857"
    assert boundary.contains(-79.5, 8.5)

    with pytest.raises(BoundaryError):
        load_boundary(write_boundary(tmp_path / "unsupported.geojson", crs="EPSG:32619"))


def test_invalid_boundary_geometry_is_rejected(tmp_path: Path) -> None:
    open_ring = [[[-80, 8], [-79, 8], [-79, 9], [-80, 9]]]
    with pytest.raises(BoundaryError):
        load_boundary(write_boundary(tmp_path / "open.geojson", coordinates=open_ring))

    crossing_ring = [[[-80, 8], [-79, 9], [-79, 8], [-80, 9], [-80, 8]]]
    with pytest.raises(BoundaryError):
        load_boundary(write_boundary(tmp_path / "crossing.geojson", coordinates=crossing_ring))


def test_local_csv_filter_keeps_raw_rows_and_stable_ids(tmp_path: Path) -> None:
    duplicate = firms_row()
    rows = [
        firms_row(),
        duplicate,
        firms_row(acq_date="2025-05-01"),
        firms_row(longitude="-78.0"),
        firms_row(latitude="91"),
        firms_row(acq_date="2026-01-02"),
        firms_row(instrument="", confidence="", frp=""),
    ]
    source = tmp_path / "source.csv"
    source_bytes = write_csv(source, rows)
    artifact = local_artifact(tmp_path, rows)
    boundary = load_boundary(write_boundary(tmp_path / "cocle.geojson"))
    scan_first = scan_raw_artifact(artifact)
    scan_second = scan_raw_artifact(artifact)
    result = filter_to_cocle([scan_first], boundary)

    assert artifact.raw_path.read_bytes() == source_bytes
    assert [row["detection_id"] for row in scan_first.detections] == [
        row["detection_id"] for row in scan_second.detections
    ]
    assert result.counts["total_final_detections"] == 3
    assert result.counts["total_discarded_outside_period"] == 2
    assert result.counts["total_invalid_coordinates"] == 1
    assert result.counts["total_discarded_outside_cocle"] == 1
    assert result.duplicate_summary["within_source_groups"] == 1
    assert result.duplicate_summary["within_source_rows_after_first_occurrence"] == 1
    assert len(result.final_detections) == 3
    assert result.final_detections[-1]["instrument"] == ""
    assert result.final_detections[-1]["confidence_normalized"] == ""
    assert result.final_detections[-1]["frp"] == ""

    processed = tmp_path / "data" / "processed" / "firms_cocle_2025_detections.csv"
    write_detections(processed, result.final_detections)
    text = processed.read_text(encoding="utf-8")
    assert "detection_id" in text.splitlines()[0]
    assert artifact.raw_path.name in text
    assert "source_row_number" in text.splitlines()[0]


def test_profile_aggregates_fragments_and_distinguishes_coverage(tmp_path: Path) -> None:
    first = local_artifact(tmp_path, [firms_row(acq_date="2025-01-02")], source="VIIRS_SNPP_SP")
    second_input = tmp_path / "second.csv"
    write_csv(second_input, [firms_row(acq_date="2025-01-03")])
    second = acquire_local_csv(
        second_input,
        tmp_path / "data" / "raw" / "second.csv",
        tmp_path / "data" / "raw" / "manifests",
        "VIIRS_SNPP_SP",
        DateRange(date(2025, 1, 1), date(2025, 4, 30)),
        "cocle",
        [-80, 8, -79, 9],
    )
    boundary = load_boundary(write_boundary(tmp_path / "cocle.geojson"))
    result = filter_to_cocle(
        [scan_raw_artifact(first), scan_raw_artifact(second)],
        boundary,
    )
    profile = build_profile(
        result,
        [first.manifest, second.manifest],
        date(2025, 1, 1),
        date(2025, 4, 30),
    )
    assert profile["by_source"]["VIIRS_SNPP_SP"]["raw_records"] == 2
    assert profile["by_source"]["VIIRS_SNPP_SP"]["final_cocle_records"] == 2
    assert profile["by_source"]["VIIRS_SNPP_SP"]["raw_fragments"] == 2
    coverage = profile["days_without_observations"]["VIIRS_SNPP_SP"]
    assert coverage["coverage_known_from_manifests"] is False
    assert coverage["queried_days_without_rows_in_bbox"] is None
    assert coverage["days_with_rows_in_query_bbox"] == ["2025-01-02", "2025-01-03"]
    assert profile["temporal_range_raw"] == {
        "min_acq_date": "2025-01-02",
        "max_acq_date": "2025-01-03",
    }


def test_schema_incompatible_input_is_rejected_by_cli(tmp_path: Path) -> None:
    bad_input = tmp_path / "bad.csv"
    write_csv(bad_input, [{"latitude": "8.5", "longitude": "-79.5"}], headers=["latitude", "longitude"])
    boundary_path = write_boundary(tmp_path / "cocle.geojson")
    exit_code = main(
        [
            "--input",
            str(bad_input),
            "--project-root",
            str(tmp_path),
            "--boundary-path",
            str(boundary_path),
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "data" / "processed" / "firms_cocle_2025_detections.csv").exists()
    audit = json.loads((tmp_path / "outputs" / "firms_acquisition_audit_2025.json").read_text(encoding="utf-8"))
    assert audit["ready_for_processed_cohort"] is False


def test_new_cli_processes_local_csv_only_in_approved_period(tmp_path: Path) -> None:
    source = tmp_path / "real-local-input.csv"
    write_csv(source, [firms_row()])
    boundary = write_boundary(tmp_path / "cocle.geojson")
    exit_code = main(
        [
            "--input",
            str(source),
            "--project-root",
            str(tmp_path),
            "--boundary-path",
            str(boundary),
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "data" / "processed" / "firms_cocle_2025_detections.csv").exists()
    assert (tmp_path / "outputs" / "firms_cocle_2025_profile.json").exists()
    audit = json.loads((tmp_path / "outputs" / "firms_acquisition_audit_2025.json").read_text(encoding="utf-8"))
    assert audit["mode"] == "local_csv"
    assert audit["coverage"]["complete"] is True
    assert audit["ready_for_processed_cohort"] is True


def test_cli_blocks_without_boundary(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    write_csv(source, [firms_row()])
    exit_code = main(["--input", str(source), "--project-root", str(tmp_path)])
    assert exit_code == 2


def test_cli_rejects_reserved_secondary_period() -> None:
    assert main(["--start-date", "2026-01-01", "--end-date", "2026-04-30"]) == 2
