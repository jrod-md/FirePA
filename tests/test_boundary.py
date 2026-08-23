from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.boundary import (  # noqa: E402
    BoundarySourceError,
    ShapeRecord,
    ShapefileLayer,
    build_geojson,
    group_rings,
    read_shapefile,
    select_records,
    source_metadata,
    validate_ring,
)


def square(left: float, bottom: float, size: float) -> tuple[tuple[float, float], ...]:
    return (
        (left, bottom),
        (left + size, bottom),
        (left + size, bottom + size),
        (left, bottom + size),
        (left, bottom),
    )


def fake_layer(records: tuple[ShapeRecord, ...], fields: tuple[str, ...] = ("nomb_prov",)) -> ShapefileLayer:
    root = Path("synthetic")
    return ShapefileLayer(
        shp_path=root / "layer.shp",
        dbf_path=root / "layer.dbf",
        shx_path=root / "layer.shx",
        prj_path=root / "layer.prj",
        cpg_path=root / "layer.cpg",
        metadata_path=None,
        encoding="utf-8",
        source_crs="EPSG:4326",
        shape_type=5,
        shape_type_name="Polygon",
        file_bbox=(-1.0, -1.0, 2.0, 2.0),
        fields=fields,
        records=records,
    )


def test_exact_cocle_selection_normalizes_accents_without_fuzzy_matching() -> None:
    records = (
        ShapeRecord(1, False, {"nomb_prov": "COCLÉ"}, (square(-80, 8, 1),), None),
        ShapeRecord(2, False, {"nomb_prov": "Coclé Norte"}, (square(-79, 8, 1),), None),
    )
    selected = select_records(fake_layer(records), target_name="Cocle")
    assert [record.index for record in selected] == [1]


def test_missing_documented_name_field_is_rejected() -> None:
    record = ShapeRecord(1, False, {"province": "Coclé"}, (square(-80, 8, 1),), None)
    with pytest.raises(BoundarySourceError):
        select_records(fake_layer((record,), fields=("province",)))


def test_group_rings_preserves_multipart_and_holes() -> None:
    outer = square(-80, 8, 2)
    hole = square(-79.5, 8.5, 0.25)
    island = square(-77, 8, 1)
    grouped = group_rings((outer, hole, island))
    assert len(grouped) == 2
    assert [len(holes) for _, holes in grouped] == [1, 0]


def test_self_crossing_and_open_rings_are_rejected() -> None:
    crossing = ((0, 0), (1, 1), (1, 0), (0, 1), (0, 0))
    with pytest.raises(BoundarySourceError):
        validate_ring(crossing)
    with pytest.raises(BoundarySourceError):
        validate_ring(((0, 0), (1, 0), (1, 1), (0, 1)))


def test_geojson_output_keeps_explicit_crs_and_multipart_geometry() -> None:
    records = (ShapeRecord(1, False, {"nomb_prov": "Coclé"}, (square(-80, 8, 1), square(-78, 8, 1)), None),)
    document = build_geojson(fake_layer(records), records, "nomb_prov")
    assert document["crs"]["properties"]["name"] == "EPSG:4326"
    assert document["features"][0]["geometry"]["type"] == "MultiPolygon"


def test_source_metadata_extracts_license_and_reference_warning(tmp_path: Path) -> None:
    metadata = tmp_path / "layer.shp.xml"
    metadata.write_text(
        "<root><resTitle>Dataset provincial</resTitle><useLimit>CC BY-NC-SA</useLimit>"
        "<useLimit>La información presentada, sólo puede ser usada como referencia</useLimit></root>",
        encoding="utf-8",
    )
    result = source_metadata(metadata)
    assert result["title"] == "Dataset provincial"
    assert result["license"] == "CC BY-NC-SA"
    assert result["reference_only_warning_present"] is True


def test_official_source_can_be_read_when_present() -> None:
    source = Path("data/reference/source/ign_anati_dpa_2025/limi_prov_a.shp")
    if not source.exists():
        pytest.skip("La fuente oficial local no está disponible en este entorno.")
    layer = read_shapefile(source)
    assert layer.source_crs == "EPSG:32617"
    assert layer.shape_type_name == "Polygon"
    assert len(layer.records) == 20
