"""Small, dependency-free GeoJSON validation and point-in-polygon support.

The project intentionally does not draw or approximate a Coclé boundary. A
user-supplied GeoJSON is validated, transformed to EPSG:4326 when its CRS is
explicitly supported, and then used for the definitive spatial filter.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class BoundaryError(ValueError):
    """Raised when a boundary file cannot be trusted for filtering."""


Ring = tuple[tuple[float, float], ...]
Polygon = tuple[Ring, tuple[Ring, ...]]


def _normalized_label(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def _parse_epsg(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?:epsg[^0-9]*|::)([0-9]{4,6})", value, flags=re.IGNORECASE)
    if not match:
        match = re.fullmatch(r"\s*([0-9]{4,6})\s*", value)
    return f"EPSG:{match.group(1)}" if match else None


def _extract_crs(document: dict[str, Any], assume_crs: str | None) -> str:
    crs = document.get("crs")
    raw_name: Any = None
    if isinstance(crs, dict):
        properties = crs.get("properties")
        if isinstance(properties, dict):
            raw_name = properties.get("name") or properties.get("href")
    normalized = _parse_epsg(raw_name)
    if normalized:
        return normalized
    if assume_crs:
        normalized = _parse_epsg(assume_crs)
        if normalized:
            return normalized
        raise BoundaryError(f"CRS explícito no soportado o ilegible: {assume_crs}")
    raise BoundaryError(
        "El GeoJSON no declara un CRS interpretable. Proporcione --boundary-crs "
        "solo después de verificar el CRS original; no se inferirá una geometría."
    )


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise BoundaryError("La geometría contiene una coordenada no numérica.") from exc
    if not math.isfinite(result):
        raise BoundaryError("La geometría contiene una coordenada no finita.")
    return result


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    if abs(_orientation(a, b, point)) > 1e-10:
        return False
    return (
        min(a[0], b[0]) - 1e-10 <= point[0] <= max(a[0], b[0]) + 1e-10
        and min(a[1], b[1]) - 1e-10 <= point[1] <= max(a[1], b[1]) + 1e-10
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    orientations = (_orientation(a, b, c), _orientation(a, b, d), _orientation(c, d, a), _orientation(c, d, b))
    if all(abs(value) <= 1e-10 for value in orientations):
        return any((_on_segment(point, a, b) and _on_segment(point, c, d)) for point in (a, b, c, d))
    return (
        ((orientations[0] > 0) != (orientations[1] > 0))
        and ((orientations[2] > 0) != (orientations[3] > 0))
    )


def _ring_area(ring: Ring) -> float:
    return 0.5 * sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    )


def _validate_ring(ring: Ring) -> None:
    if len(ring) < 4:
        raise BoundaryError("Cada anillo debe tener al menos cuatro coordenadas.")
    if ring[0] != ring[-1]:
        raise BoundaryError("Cada anillo debe estar cerrado repitiendo su primera coordenada.")
    if abs(_ring_area(ring)) <= 1e-12:
        raise BoundaryError("La geometría contiene un anillo de área cero.")

    segment_count = len(ring) - 1
    segments = [
        (
            ring[index],
            ring[index + 1],
            (
                min(ring[index][0], ring[index + 1][0]),
                min(ring[index][1], ring[index + 1][1]),
                max(ring[index][0], ring[index + 1][0]),
                max(ring[index][1], ring[index + 1][1]),
            ),
        )
        for index in range(segment_count)
    ]
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

    for first, second in candidates:
        if second == first + 1 or (first == 0 and second == segment_count - 1):
            continue
        first_bounds, second_bounds = segments[first][2], segments[second][2]
        if (
            first_bounds[2] < second_bounds[0]
            or second_bounds[2] < first_bounds[0]
            or first_bounds[3] < second_bounds[1]
            or second_bounds[3] < first_bounds[1]
        ):
            continue
        if _segments_intersect(segments[first][0], segments[first][1], segments[second][0], segments[second][1]):
            raise BoundaryError("La geometría contiene un auto-cruce en un anillo.")


def _point_in_ring(point: tuple[float, float], ring: Ring) -> int:
    """Return 0 outside, 1 inside, or 2 on the boundary."""

    inside = False
    x, y = point
    for index in range(len(ring) - 1):
        first, second = ring[index], ring[index + 1]
        if _on_segment(point, first, second):
            return 2
        if (first[1] > y) != (second[1] > y):
            x_intersection = (second[0] - first[0]) * (y - first[1]) / (second[1] - first[1]) + first[0]
            if x < x_intersection:
                inside = not inside
    return 1 if inside else 0


def _inverse_web_mercator(x: float, y: float) -> tuple[float, float]:
    radius = 6378137.0
    longitude = math.degrees(x / radius)
    latitude = math.degrees(2 * math.atan(math.exp(y / radius)) - math.pi / 2)
    return longitude, latitude


def _inverse_utm(x: float, y: float, zone: int) -> tuple[float, float]:
    # WGS84 inverse UTM for the northern hemisphere. EPSG:32617 and EPSG:32618
    # cover the CRS documented by the IGN metadata and the adjacent Panama zone.
    semi_major = 6378137.0
    eccentricity_squared = 0.0066943799901413165
    eccentricity_prime_squared = eccentricity_squared / (1 - eccentricity_squared)
    scale = 0.9996
    x -= 500000.0
    meridional_arc = y / scale
    mu = meridional_arc / (
        semi_major
        * (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256)
    )
    e1 = (1 - math.sqrt(1 - eccentricity_squared)) / (1 + math.sqrt(1 - eccentricity_squared))
    footpoint_latitude = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sine = math.sin(footpoint_latitude)
    cosine = math.cos(footpoint_latitude)
    tangent_squared = math.tan(footpoint_latitude) ** 2
    radius_prime = semi_major * (1 - eccentricity_squared) / (1 - eccentricity_squared * sine**2) ** 1.5
    radius_normal = semi_major / math.sqrt(1 - eccentricity_squared * sine**2)
    c1 = eccentricity_prime_squared * cosine**2
    d = x / (radius_normal * scale)

    latitude = footpoint_latitude - (
        radius_normal
        * math.tan(footpoint_latitude)
        / radius_prime
        * (
            d**2 / 2
            - (5 + 3 * tangent_squared + 10 * c1 - 4 * c1**2 - 9 * eccentricity_prime_squared) * d**4 / 24
            + (61 + 90 * tangent_squared + 298 * c1 + 45 * tangent_squared**2 - 252 * eccentricity_prime_squared - 3 * c1**2)
            * d**6
            / 720
        )
    )
    longitude = (
        zone * 6
        - 183
        + math.degrees(
            (
                d
                - (1 + 2 * tangent_squared + c1) * d**3 / 6
                + (5 - 2 * c1 + 28 * tangent_squared - 3 * c1**2 + 8 * eccentricity_prime_squared + 24 * tangent_squared**2)
                * d**5
                / 120
            )
            / cosine
        )
    )
    return longitude, math.degrees(latitude)


def _transform_point(point: tuple[float, float], source_crs: str) -> tuple[float, float]:
    if source_crs == "EPSG:4326":
        return point
    if source_crs == "EPSG:3857":
        return _inverse_web_mercator(*point)
    if source_crs in {"EPSG:32617", "EPSG:32618"}:
        return _inverse_utm(point[0], point[1], int(source_crs.split(":")[1]) - 32600)
    raise BoundaryError(
        f"CRS {source_crs} no está soportado por el validador stdlib. "
        "Use EPSG:4326, EPSG:3857, EPSG:32617 o EPSG:32618."
    )


def _transform_ring(coordinates: Iterable[Any], source_crs: str) -> Ring:
    points: list[tuple[float, float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            raise BoundaryError("La geometría contiene una coordenada incompleta.")
        points.append(_transform_point((_number(coordinate[0]), _number(coordinate[1])), source_crs))
    return tuple(points)


def _geometry_to_polygons(geometry: dict[str, Any], source_crs: str) -> tuple[Polygon, ...]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type not in {"Polygon", "MultiPolygon"} or not isinstance(coordinates, list):
        raise BoundaryError("Se requiere una geometría GeoJSON Polygon o MultiPolygon.")

    polygon_coordinates = [coordinates] if geometry_type == "Polygon" else coordinates
    polygons: list[Polygon] = []
    for raw_polygon in polygon_coordinates:
        if not isinstance(raw_polygon, list) or not raw_polygon:
            raise BoundaryError("La geometría contiene un polígono sin anillos.")
        rings = tuple(_transform_ring(raw_ring, source_crs) for raw_ring in raw_polygon)
        for ring in rings:
            _validate_ring(ring)
        outer, holes = rings[0], rings[1:]
        for hole in holes:
            if any(_point_in_ring(point, outer) != 1 for point in hole[:-1]):
                raise BoundaryError(
                    "Un anillo interior queda fuera o toca el anillo exterior."
                )
            for outer_index in range(len(outer) - 1):
                for hole_index in range(len(hole) - 1):
                    if _segments_intersect(
                        outer[outer_index],
                        outer[outer_index + 1],
                        hole[hole_index],
                        hole[hole_index + 1],
                    ):
                        raise BoundaryError(
                            "Un anillo interior intersecta el anillo exterior."
                        )
        for first_index, first_hole in enumerate(holes):
            for second_hole in holes[first_index + 1 :]:
                if _point_in_ring(first_hole[0], second_hole) != 0:
                    raise BoundaryError("Los anillos interiores se superponen o tocan.")
                for first_segment in range(len(first_hole) - 1):
                    for second_segment in range(len(second_hole) - 1):
                        if _segments_intersect(
                            first_hole[first_segment],
                            first_hole[first_segment + 1],
                            second_hole[second_segment],
                            second_hole[second_segment + 1],
                        ):
                            raise BoundaryError("Los anillos interiores se intersectan.")
        polygons.append((outer, holes))
    return tuple(polygons)


def _feature_geometries(document: dict[str, Any], feature_name: str) -> list[dict[str, Any]]:
    document_type = document.get("type")
    if document_type == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list) or not features:
            raise BoundaryError("El FeatureCollection no contiene features.")
        target = _normalized_label(feature_name)
        matching: list[dict[str, Any]] = []
        for feature in features:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise BoundaryError("El FeatureCollection contiene un feature inválido.")
            properties = feature.get("properties")
            values = properties.values() if isinstance(properties, dict) else []
            if any(_normalized_label(value) == target for value in values if isinstance(value, str)):
                matching.append(feature)
        if not matching:
            if len(features) == 1:
                matching = features
            else:
                raise BoundaryError(f"No se encontró el feature administrativo '{feature_name}'.")
        geometries = [feature.get("geometry") for feature in matching]
    elif document_type == "Feature":
        geometries = [document.get("geometry")]
    elif document_type in {"Polygon", "MultiPolygon"}:
        geometries = [document]
    else:
        raise BoundaryError("El archivo no es un GeoJSON Feature, FeatureCollection o Polygon.")
    if any(not isinstance(geometry, dict) for geometry in geometries):
        raise BoundaryError("El feature seleccionado no contiene geometría.")
    return geometries


@dataclass(frozen=True)
class Boundary:
    """Validated boundary represented as EPSG:4326 polygons."""

    source_path: Path
    feature_name: str
    source_crs: str
    polygons: tuple[Polygon, ...]

    @property
    def normalized_crs(self) -> str:
        return "EPSG:4326"

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        coordinates = [point for outer, holes in self.polygons for ring in (outer, *holes) for point in ring]
        longitudes = [point[0] for point in coordinates]
        latitudes = [point[1] for point in coordinates]
        return min(longitudes), min(latitudes), max(longitudes), max(latitudes)

    def contains(self, longitude: float, latitude: float) -> bool:
        point = (float(longitude), float(latitude))
        for outer, holes in self.polygons:
            outer_state = _point_in_ring(point, outer)
            if outer_state == 0:
                continue
            if any(_point_in_ring(point, hole) in {1, 2} for hole in holes):
                continue
            return True
        return False


def load_boundary(path: Path, feature_name: str = "Coclé", assume_crs: str | None = None) -> Boundary:
    """Load and validate a Coclé boundary without inventing missing geometry."""

    if not path.exists() or not path.is_file():
        raise BoundaryError(
            f"No existe el GeoJSON de referencia: {path}. Incorpore la geometría oficial "
            "descrita en data/reference/README.md."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryError(f"No se pudo leer el GeoJSON de referencia: {path}") from exc
    if not isinstance(document, dict):
        raise BoundaryError("El GeoJSON raíz debe ser un objeto JSON.")

    source_crs = _extract_crs(document, assume_crs)
    geometries = _feature_geometries(document, feature_name)
    polygons = tuple(
        polygon for geometry in geometries for polygon in _geometry_to_polygons(geometry, source_crs)
    )
    if not polygons:
        raise BoundaryError("El GeoJSON no produjo ningún polígono válido.")
    boundary = Boundary(path, feature_name, source_crs, polygons)
    west, south, east, north = boundary.bbox
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise BoundaryError("La geometría reproyectada queda fuera de los límites geográficos.")
    return boundary
