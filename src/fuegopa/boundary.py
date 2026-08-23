"""Read, validate, and extract the official Cocle polygon layer.

The reference layer supplied for this data spike is an ESRI Shapefile in
EPSG:32617.  This module intentionally implements only the small subset of
the Shapefile and DBF formats needed for that documented source.  It does not
repair, simplify, dissolve, or invent geometry.  Invalid selected geometry
stops the extraction.
"""

from __future__ import annotations

import codecs
import hashlib
import html
import json
import math
import re
import struct
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .geo import _inverse_utm


class BoundarySourceError(ValueError):
    """Raised when the official source cannot be safely extracted."""


Point = tuple[float, float]
Ring = tuple[Point, ...]
PolygonRings = tuple[Ring, tuple[Ring, ...]]

SHP_POLYGON_TYPES = {5: "Polygon", 15: "PolygonZ", 25: "PolygonM"}


@dataclass(frozen=True)
class ShapeRecord:
    """One SHP record joined to its same-index DBF row."""

    index: int
    deleted: bool
    attributes: Mapping[str, str]
    parts: tuple[Ring, ...]
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class ShapefileLayer:
    """The source files and decoded records needed by the extractor."""

    shp_path: Path
    dbf_path: Path
    shx_path: Path
    prj_path: Path
    cpg_path: Path
    metadata_path: Path | None
    encoding: str
    source_crs: str
    shape_type: int
    shape_type_name: str
    file_bbox: tuple[float, float, float, float]
    fields: tuple[str, ...]
    records: tuple[ShapeRecord, ...]

    @property
    def active_records(self) -> tuple[ShapeRecord, ...]:
        return tuple(record for record in self.records if not record.deleted)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest without exposing file content."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_admin_name(value: Any) -> str:
    """Normalize accents and case for the exact Cocle name comparison."""

    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(text.casefold().split())


def _decode_cpg(path: Path) -> str:
    try:
        label = path.read_text(encoding="ascii").strip()
        return codecs.lookup(label).name
    except (OSError, UnicodeError, LookupError) as exc:
        raise BoundarySourceError(f"No se pudo interpretar el CPG UTF-8: {path}") from exc


def _read_dbf(path: Path, encoding: str) -> tuple[tuple[str, ...], list[tuple[bool, dict[str, str]]]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BoundarySourceError(f"No se pudo leer el DBF: {path}") from exc
    if len(data) < 33:
        raise BoundarySourceError(f"El DBF es demasiado corto: {path}")

    record_count = struct.unpack_from("<I", data, 4)[0]
    header_length = struct.unpack_from("<H", data, 8)[0]
    record_length = struct.unpack_from("<H", data, 10)[0]
    if header_length < 33 or record_length < 1 or header_length > len(data):
        raise BoundarySourceError(f"La cabecera DBF es incompatible: {path}")

    descriptors: list[tuple[str, int]] = []
    offset = 32
    while offset + 32 <= len(data) and data[offset] != 0x0D:
        descriptor = data[offset : offset + 32]
        raw_name = descriptor[:11].split(b"\x00", 1)[0]
        try:
            name = raw_name.decode(encoding).strip()
        except UnicodeDecodeError as exc:
            raise BoundarySourceError(f"Un nombre de campo DBF no decodifica con {encoding}.") from exc
        length = descriptor[16]
        if not name or length == 0:
            raise BoundarySourceError(f"El DBF contiene un campo inválido: {path}")
        if name in {field_name for field_name, _ in descriptors}:
            raise BoundarySourceError(f"El DBF contiene nombres de campo duplicados: {name}")
        descriptors.append((name, length))
        offset += 32

    if not descriptors or data[offset : offset + 1] != b"\x0D":
        raise BoundarySourceError(f"No se encontraron los campos DBF: {path}")
    if header_length < offset + 1:
        raise BoundarySourceError(f"La longitud de cabecera DBF no coincide: {path}")

    rows: list[tuple[bool, dict[str, str]]] = []
    cursor = header_length
    for _ in range(record_count):
        end = cursor + record_length
        if end > len(data):
            raise BoundarySourceError(f"El DBF termina antes de sus registros: {path}")
        row = data[cursor:end]
        deleted = row[:1] == b"*"
        field_offset = 1
        attributes: dict[str, str] = {}
        for name, length in descriptors:
            raw_value = row[field_offset : field_offset + length]
            try:
                value = raw_value.decode(encoding).strip()
            except UnicodeDecodeError as exc:
                raise BoundarySourceError(f"Un valor DBF no decodifica con {encoding}.") from exc
            attributes[name] = value
            field_offset += length
        rows.append((deleted, attributes))
        cursor = end
    return tuple(name for name, _ in descriptors), rows


def _read_shp(path: Path) -> tuple[int, tuple[float, float, float, float], list[tuple[int, tuple[Ring, ...], tuple[float, float, float, float] | None]]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BoundarySourceError(f"No se pudo leer el SHP: {path}") from exc
    if len(data) < 100:
        raise BoundarySourceError(f"El SHP es demasiado corto: {path}")
    if struct.unpack_from(">i", data, 0)[0] != 9994:
        raise BoundarySourceError(f"El código de archivo SHP no es 9994: {path}")
    declared_length = struct.unpack_from(">i", data, 24)[0] * 2
    if declared_length > len(data):
        raise BoundarySourceError(f"El SHP está truncado según su cabecera: {path}")
    version = struct.unpack_from("<i", data, 28)[0]
    if version != 1000:
        raise BoundarySourceError(f"La versión SHP no es 1000: {path}")
    shape_type = struct.unpack_from("<i", data, 32)[0]
    if shape_type not in SHP_POLYGON_TYPES:
        raise BoundarySourceError(f"El SHP no es de polígonos: tipo {shape_type}")
    file_bbox = struct.unpack_from("<4d", data, 36)

    records: list[tuple[int, tuple[Ring, ...], tuple[float, float, float, float] | None]] = []
    offset = 100
    while offset < declared_length:
        if offset + 8 > len(data):
            raise BoundarySourceError(f"La cabecera de un registro SHP está truncada: {path}")
        record_number = struct.unpack_from(">i", data, offset)[0]
        content_length = struct.unpack_from(">i", data, offset + 4)[0] * 2
        content_start = offset + 8
        content_end = content_start + content_length
        if content_end > len(data) or content_length < 4:
            raise BoundarySourceError(f"Un registro SHP tiene longitud incompatible: {path}")
        content = data[content_start:content_end]
        record_type = struct.unpack_from("<i", content, 0)[0]
        if record_type == 0:
            records.append((record_number, tuple(), None))
            offset = content_end
            continue
        if record_type not in SHP_POLYGON_TYPES:
            raise BoundarySourceError(f"El registro SHP {record_number} cambia de tipo: {record_type}")
        if len(content) < 44:
            raise BoundarySourceError(f"El registro SHP {record_number} es demasiado corto.")
        record_bbox = struct.unpack_from("<4d", content, 4)
        part_count = struct.unpack_from("<i", content, 36)[0]
        point_count = struct.unpack_from("<i", content, 40)[0]
        if part_count < 1 or point_count < 4:
            raise BoundarySourceError(f"El registro SHP {record_number} no tiene partes válidas.")
        parts_offset = 44
        points_offset = parts_offset + 4 * part_count
        points_end = points_offset + 16 * point_count
        if points_end > len(content):
            raise BoundarySourceError(f"El registro SHP {record_number} está truncado.")
        starts = struct.unpack_from(f"<{part_count}i", content, parts_offset)
        if starts[0] != 0 or any(start < 0 or start >= point_count for start in starts):
            raise BoundarySourceError(f"Las partes SHP del registro {record_number} no son válidas.")
        if any(first >= second for first, second in zip(starts, starts[1:])):
            raise BoundarySourceError(f"Las partes SHP del registro {record_number} no están ordenadas.")
        points = tuple(
            struct.unpack_from("<2d", content, points_offset + 16 * index)
            for index in range(point_count)
        )
        parts = tuple(
            tuple(points[start : (starts[index + 1] if index + 1 < len(starts) else point_count)])
            for index, start in enumerate(starts)
        )
        records.append((record_number, parts, record_bbox))
        offset = content_end
    return shape_type, tuple(file_bbox), records


def _extract_epsg(prj_text: str) -> str:
    authority_match = re.search(
        r'AUTHORITY\s*\[\s*"EPSG"\s*,\s*"(\d+)"\s*\]',
        prj_text,
        flags=re.IGNORECASE,
    )
    if authority_match:
        return f"EPSG:{authority_match.group(1)}"
    code_match = re.search(r"(?:idCode|EPSG)[^0-9]{0,20}(\d{4,6})", prj_text, flags=re.IGNORECASE)
    if code_match:
        return f"EPSG:{code_match.group(1)}"
    if (
        'PROJCS["WGS_1984_UTM_Zone_17N"' in prj_text
        and 'PARAMETER["Central_Meridian",-81.0]' in prj_text
        and 'PARAMETER["Scale_Factor",0.9996]' in prj_text
    ):
        return "EPSG:32617"
    raise BoundarySourceError("El PRJ no contiene un código EPSG legible.")


def read_shapefile(path: Path) -> ShapefileLayer:
    """Read a polygon SHP and its required, matching sidecars."""

    shp_path = path.expanduser().resolve()
    if shp_path.suffix.casefold() != ".shp":
        raise BoundarySourceError(f"La ruta de origen debe terminar en .shp: {shp_path}")
    sidecars = {suffix: shp_path.with_suffix(suffix) for suffix in (".dbf", ".shx", ".prj", ".cpg")}
    missing = [str(file_path) for file_path in sidecars.values() if not file_path.is_file()]
    if missing:
        raise BoundarySourceError("Faltan sidecars obligatorios: " + ", ".join(missing))

    encoding = _decode_cpg(sidecars[".cpg"])
    try:
        prj_text = sidecars[".prj"].read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BoundarySourceError(f"No se pudo leer el PRJ: {sidecars['.prj']}") from exc
    source_crs = _extract_epsg(prj_text)
    shape_type, file_bbox, shapes = _read_shp(shp_path)
    fields, dbf_rows = _read_dbf(sidecars[".dbf"], encoding)
    if len(shapes) != len(dbf_rows):
        raise BoundarySourceError(
            f"El SHP tiene {len(shapes)} registros y el DBF tiene {len(dbf_rows)}."
        )
    records = tuple(
        ShapeRecord(
            index=index + 1,
            deleted=deleted,
            attributes=attributes,
            parts=parts,
            bbox=bbox,
        )
        for index, ((_, parts, bbox), (deleted, attributes)) in enumerate(zip(shapes, dbf_rows))
    )
    metadata_path = shp_path.with_suffix(".shp.xml")
    return ShapefileLayer(
        shp_path=shp_path,
        dbf_path=sidecars[".dbf"].resolve(),
        shx_path=sidecars[".shx"].resolve(),
        prj_path=sidecars[".prj"].resolve(),
        cpg_path=sidecars[".cpg"].resolve(),
        metadata_path=metadata_path.resolve() if metadata_path.is_file() else None,
        encoding=encoding,
        source_crs=source_crs,
        shape_type=shape_type,
        shape_type_name=SHP_POLYGON_TYPES[shape_type],
        file_bbox=file_bbox,
        fields=fields,
        records=records,
    )


def find_name_field(fields: Iterable[str], expected: str = "nomb_prov") -> str:
    """Find the documented administrative-name field without fuzzy matching."""

    expected_key = expected.casefold()
    matches = [field for field in fields if field.casefold() == expected_key]
    if len(matches) != 1:
        raise BoundarySourceError(
            f"No se encontró exactamente el campo obligatorio {expected!r}; campos: {list(fields)!r}"
        )
    return matches[0]


def select_records(
    layer: ShapefileLayer,
    *,
    name_field: str = "nomb_prov",
    target_name: str = "Coclé",
) -> tuple[ShapeRecord, ...]:
    """Select only exact normalized administrative-name matches."""

    field = find_name_field(layer.fields, name_field)
    target = normalize_admin_name(target_name)
    selected = tuple(
        record
        for record in layer.active_records
        if normalize_admin_name(record.attributes.get(field, "")) == target
    )
    if not selected:
        available = sorted({record.attributes.get(field, "") for record in layer.active_records})
        raise BoundarySourceError(
            f"No se encontró {target_name!r} en {field!r}. Valores disponibles: {available!r}"
        )
    return selected


def _signed_area(ring: Ring) -> float:
    return 0.5 * sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    )


def _orientation(first: Point, second: Point, third: Point) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])


def _on_segment(point: Point, first: Point, second: Point) -> bool:
    return (
        abs(_orientation(first, second, point)) <= 1e-8
        and min(first[0], second[0]) - 1e-8 <= point[0] <= max(first[0], second[0]) + 1e-8
        and min(first[1], second[1]) - 1e-8 <= point[1] <= max(first[1], second[1]) + 1e-8
    )


def _segments_intersect(first: Point, second: Point, third: Point, fourth: Point) -> bool:
    orientations = (
        _orientation(first, second, third),
        _orientation(first, second, fourth),
        _orientation(third, fourth, first),
        _orientation(third, fourth, second),
    )
    if all(abs(value) <= 1e-8 for value in orientations):
        return any(
            _on_segment(point, first, second) and _on_segment(point, third, fourth)
            for point in (first, second, third, fourth)
        )
    return ((orientations[0] > 0) != (orientations[1] > 0)) and (
        (orientations[2] > 0) != (orientations[3] > 0)
    )


def _bbox(ring: Ring) -> tuple[float, float, float, float]:
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlaps(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return not (
        first[2] < second[0]
        or second[2] < first[0]
        or first[3] < second[1]
        or second[3] < first[1]
    )


def validate_ring(ring: Ring) -> None:
    """Validate closure, area, and non-adjacent segment intersections."""

    if len(ring) < 4 or ring[0] != ring[-1]:
        raise BoundarySourceError("Cada anillo seleccionado debe estar cerrado.")
    if abs(_signed_area(ring)) <= 1e-6:
        raise BoundarySourceError("Un anillo seleccionado tiene área cero.")

    segments = [
        (ring[index], ring[index + 1], _bbox((ring[index], ring[index + 1])))
        for index in range(len(ring) - 1)
    ]
    segment_count = len(segments)
    # A spatial grid keeps validation inspectable while avoiding an O(n²)
    # comparison for the detailed official coastline.
    min_x = min(segment[2][0] for segment in segments)
    min_y = min(segment[2][1] for segment in segments)
    max_x = max(segment[2][2] for segment in segments)
    max_y = max(segment[2][3] for segment in segments)
    grid_size = max(8, min(256, int(math.sqrt(segment_count)) or 8))
    cell_width = (max_x - min_x) / grid_size or 1.0
    cell_height = (max_y - min_y) / grid_size or 1.0
    buckets: dict[tuple[int, int], list[int]] = {}
    long_segments: list[int] = []
    for index, (_, _, bounds) in enumerate(segments):
        x_start = max(0, min(grid_size - 1, int((bounds[0] - min_x) / cell_width)))
        x_end = max(0, min(grid_size - 1, int((bounds[2] - min_x) / cell_width)))
        y_start = max(0, min(grid_size - 1, int((bounds[1] - min_y) / cell_height)))
        y_end = max(0, min(grid_size - 1, int((bounds[3] - min_y) / cell_height)))
        if (x_end - x_start + 1) * (y_end - y_start + 1) > grid_size * 2:
            long_segments.append(index)
            continue
        for x_cell in range(x_start, x_end + 1):
            for y_cell in range(y_start, y_end + 1):
                buckets.setdefault((x_cell, y_cell), []).append(index)

    candidates: set[tuple[int, int]] = set()
    for bucket in buckets.values():
        for left_position, first in enumerate(bucket):
            for second in bucket[left_position + 1 :]:
                candidates.add((min(first, second), max(first, second)))
    for first in long_segments:
        for second in range(segment_count):
            if first != second:
                candidates.add((min(first, second), max(first, second)))

    for first_index, second_index in candidates:
        if second_index == first_index + 1 or (first_index == 0 and second_index == segment_count - 1):
            continue
        first = segments[first_index]
        second = segments[second_index]
        if _bbox_overlaps(first[2], second[2]) and _segments_intersect(first[0], first[1], second[0], second[1]):
            raise BoundarySourceError("Un anillo seleccionado contiene un auto-cruce.")


def _point_in_ring(point: Point, ring: Ring) -> int:
    inside = False
    for index in range(len(ring) - 1):
        first, second = ring[index], ring[index + 1]
        if _on_segment(point, first, second):
            return 2
        if (first[1] > point[1]) != (second[1] > point[1]):
            x_intersection = (second[0] - first[0]) * (point[1] - first[1]) / (second[1] - first[1]) + first[0]
            if point[0] < x_intersection:
                inside = not inside
    return 1 if inside else 0


def _representative_point(ring: Ring) -> Point:
    for point in ring[:-1]:
        return point
    return ring[0]


def group_rings(parts: Iterable[Ring]) -> tuple[PolygonRings, ...]:
    """Group SHP parts into outer rings and contained holes without dissolving."""

    rings = tuple(parts)
    if not rings:
        raise BoundarySourceError("El registro seleccionado no contiene partes.")
    for ring in rings:
        validate_ring(ring)

    containers: list[tuple[int, ...]] = []
    for index, ring in enumerate(rings):
        point = _representative_point(ring)
        containing = tuple(
            other_index
            for other_index, other_ring in enumerate(rings)
            if other_index != index and _point_in_ring(point, other_ring) == 1
        )
        containers.append(containing)

    depth = [len(container) for container in containers]
    outer_indices = [index for index, value in enumerate(depth) if value % 2 == 0]
    if not outer_indices:
        raise BoundarySourceError("No se encontró un anillo exterior válido.")

    grouped: list[PolygonRings] = []
    for outer_index in outer_indices:
        hole_candidates = [
            index
            for index, value in enumerate(depth)
            if value == depth[outer_index] + 1 and outer_index in containers[index]
        ]
        grouped.append((rings[outer_index], tuple(rings[index] for index in hole_candidates)))
    return tuple(grouped)


def _transform_point(point: Point, source_crs: str) -> Point:
    if source_crs == "EPSG:4326":
        return point
    if source_crs == "EPSG:32617":
        longitude, latitude = _inverse_utm(point[0], point[1], 17)
        return longitude, latitude
    raise BoundarySourceError(
        f"No hay una transformación estándar implementada para {source_crs}; se requiere EPSG:32617 o EPSG:4326."
    )


def transform_ring(ring: Ring, source_crs: str) -> Ring:
    return tuple(_transform_point(point, source_crs) for point in ring)


def record_polygons(record: ShapeRecord, source_crs: str) -> tuple[PolygonRings, ...]:
    grouped = group_rings(record.parts)
    return tuple(
        (transform_ring(outer, source_crs), tuple(transform_ring(hole, source_crs) for hole in holes))
        for outer, holes in grouped
    )


def record_geometry(record: ShapeRecord, source_crs: str) -> dict[str, Any]:
    polygons = record_polygons(record, source_crs)
    serialized = [
        [
            [[float(x), float(y)] for x, y in ring]
            for ring in (outer, *holes)
        ]
        for outer, holes in polygons
    ]
    if len(serialized) == 1:
        return {"type": "Polygon", "coordinates": serialized[0]}
    return {"type": "MultiPolygon", "coordinates": serialized}


def build_geojson(layer: ShapefileLayer, selected: Iterable[ShapeRecord], name_field: str) -> dict[str, Any]:
    features = []
    for record in selected:
        properties = dict(record.attributes)
        properties["_source_record_index"] = record.index
        properties["_source_name_field"] = name_field
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": record_geometry(record, layer.source_crs),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "cocle_boundary_ign_anati_2025",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


def write_geojson(document: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ring_centroid(ring: Ring) -> tuple[float, Point]:
    signed = _signed_area(ring)
    if abs(signed) <= 1e-12:
        raise BoundarySourceError("No se puede calcular el centroide de un anillo de área cero.")
    x_sum = 0.0
    y_sum = 0.0
    for index in range(len(ring) - 1):
        first, second = ring[index], ring[index + 1]
        cross = first[0] * second[1] - second[0] * first[1]
        x_sum += (first[0] + second[0]) * cross
        y_sum += (first[1] + second[1]) * cross
    return signed, (x_sum / (6 * signed), y_sum / (6 * signed))


def area_centroid(polygons: Iterable[PolygonRings]) -> tuple[float, Point]:
    """Return descriptive area in source square metres and centroid in source CRS."""

    total_area = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    for outer, holes in polygons:
        outer_signed, outer_centroid = _ring_centroid(outer)
        outer_area = abs(outer_signed)
        total_area += outer_area
        weighted_x += outer_area * outer_centroid[0]
        weighted_y += outer_area * outer_centroid[1]
        for hole in holes:
            hole_signed, hole_centroid = _ring_centroid(hole)
            hole_area = abs(hole_signed)
            total_area -= hole_area
            weighted_x -= hole_area * hole_centroid[0]
            weighted_y -= hole_area * hole_centroid[1]
    if total_area <= 0:
        raise BoundarySourceError("El área neta seleccionada no es positiva.")
    return total_area, (weighted_x / total_area, weighted_y / total_area)


def source_metadata(path: Path | None) -> dict[str, Any]:
    """Extract only auditable metadata fields from the supplied XML sidecar."""

    if path is None:
        return {"present": False}
    try:
        raw_text = path.read_text(encoding="utf-8", errors="strict")
        root = ET.fromstring(raw_text)
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise BoundarySourceError(f"No se pudo leer el XML de metadatos: {path}") from exc

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    title = None
    for element in root.iter():
        if local_name(element.tag) == "resTitle" and element.text:
            title = element.text.strip()
            break
    text = html.unescape(" ".join(root.itertext()))
    text = re.sub(r"<[^>]+>", " ", text)
    compact = " ".join(text.split())
    return {
        "present": True,
        "title": title,
        "license": "CC BY-NC-SA" if "CC BY-NC-SA" in compact else None,
        "reference_only_warning_present": "sólo puede ser usada como referencia" in compact,
        "cartographic_warning_present": "meramente, cartográfica" in compact,
        "path": str(path),
    }


def transformed_bbox(polygons: Iterable[PolygonRings]) -> tuple[float, float, float, float]:
    points = [point for outer, holes in polygons for ring in (outer, *holes) for point in ring]
    if not points:
        raise BoundarySourceError("No hay puntos para calcular el bbox.")
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )
