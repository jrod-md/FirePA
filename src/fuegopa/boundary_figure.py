"""Dependency-free PNG figure for the Cocle boundary validation artifact."""

from __future__ import annotations

import math
import struct
import unicodedata
import zlib
from pathlib import Path
from typing import Iterable

from .boundary import Point, Ring, ShapeRecord, ShapefileLayer, record_polygons, transform_ring


Color = tuple[int, int, int]


FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00110", "00100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
}


class Canvas:
    def __init__(self, width: int, height: int, background: Color = (255, 255, 255)) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(background * (width * height))

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.pixels[offset : offset + 3] = bytes(color)

    def rect(self, left: int, top: int, right: int, bottom: int, color: Color) -> None:
        for y in range(max(0, top), min(self.height, bottom + 1)):
            start = (y * self.width + max(0, left)) * 3
            end = (y * self.width + min(self.width, right + 1)) * 3
            self.pixels[start:end] = bytes(color) * ((end - start) // 3)

    def line(self, first: tuple[int, int], second: tuple[int, int], color: Color, width: int = 1) -> None:
        x0, y0 = first
        x1, y1 = second
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        radius = max(0, width // 2)
        while True:
            for offset_x in range(-radius, radius + 1):
                for offset_y in range(-radius, radius + 1):
                    self.pixel(x0 + offset_x, y0 + offset_y, color)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy

    def polygon_fill(self, points: list[tuple[int, int]], color: Color, clip: tuple[int, int, int, int]) -> None:
        if len(points) < 3:
            return
        left, top, right, bottom = clip
        for y in range(max(top, min(point[1] for point in points)), min(bottom, max(point[1] for point in points)) + 1):
            intersections: list[float] = []
            for index in range(len(points)):
                first = points[index]
                second = points[(index + 1) % len(points)]
                if (first[1] > y) != (second[1] > y):
                    intersections.append(first[0] + (y - first[1]) * (second[0] - first[0]) / (second[1] - first[1]))
            intersections.sort()
            for start, end in zip(intersections[::2], intersections[1::2]):
                for x in range(max(left, math.ceil(start)), min(right, math.floor(end)) + 1):
                    self.pixel(x, y, color)

    def text(self, x: int, y: int, value: str, color: Color, scale: int = 2) -> None:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").upper()
        cursor = x
        for character in normalized:
            if character == " ":
                cursor += 4 * scale
                continue
            glyph = FONT.get(character, FONT["_"])
            for row, pattern in enumerate(glyph):
                for column, enabled in enumerate(pattern):
                    if enabled == "1":
                        self.rect(cursor + column * scale, y + row * scale, cursor + (column + 1) * scale - 1, y + (row + 1) * scale - 1, color)
            cursor += 6 * scale

    def png_bytes(self) -> bytes:
        raw = b"".join(
            b"\x00" + bytes(self.pixels[row * self.width * 3 : (row + 1) * self.width * 3])
            for row in range(self.height)
        )

        def chunk(kind: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _map_points(layer: ShapefileLayer) -> list[tuple[ShapeRecord, list[Ring]]]:
    mapped: list[tuple[ShapeRecord, list[Ring]]] = []
    for record in layer.active_records:
        mapped.append((record, [transform_ring(ring, layer.source_crs) for ring in record.parts]))
    return mapped


def _projector(points: Iterable[Point], plot: tuple[int, int, int, int]):
    points = list(points)
    west = min(point[0] for point in points)
    south = min(point[1] for point in points)
    east = max(point[0] for point in points)
    north = max(point[1] for point in points)
    left, top, right, bottom = plot
    width = max(east - west, 1e-9)
    height = max(north - south, 1e-9)
    scale = min((right - left) / width, (bottom - top) / height)
    map_width = width * scale
    map_height = height * scale
    x_offset = left + ((right - left) - map_width) / 2
    y_offset = top + ((bottom - top) - map_height) / 2

    def project(point: Point) -> tuple[int, int]:
        return round(x_offset + (point[0] - west) * scale), round(y_offset + (north - point[1]) * scale)

    return project, (west, south, east, north)


def write_validation_figure(layer: ShapefileLayer, selected: Iterable[ShapeRecord], path: Path) -> None:
    """Render all provincial outlines and highlight the exact selected record."""

    mapped = _map_points(layer)
    all_points = [point for _, rings in mapped for ring in rings for point in ring]
    project, geo_bbox = _projector(all_points, (70, 120, 950, 785))
    selected_indices = {record.index for record in selected}
    canvas = Canvas(1400, 900, (255, 255, 255))
    canvas.rect(0, 0, 1399, 79, (25, 43, 68))
    canvas.text(42, 23, "FUEGOPA - LIMITE DE COCLE", (255, 255, 255), scale=3)
    canvas.text(70, 92, "PANAMA PROVINCES / SELECTED OFFICIAL RECORD", (50, 64, 82), scale=2)

    plot_background = (248, 250, 252)
    canvas.rect(70, 120, 950, 785, plot_background)
    for record, rings in mapped:
        for ring in rings:
            points = [project(point) for point in ring]
            for first, second in zip(points, points[1:]):
                canvas.line(first, second, (170, 178, 188), width=1)

    selected_records = [record for record, _ in mapped if record.index in selected_indices]
    for record in selected_records:
        for outer, holes in record_polygons(record, layer.source_crs):
            outer_points = [project(point) for point in outer]
            canvas.polygon_fill(outer_points, (255, 224, 188), (70, 120, 950, 785))
            for hole in holes:
                canvas.polygon_fill([project(point) for point in hole], plot_background, (70, 120, 950, 785))

    for record, rings in mapped:
        if record.index not in selected_indices:
            continue
        for ring in rings:
            points = [project(point) for point in ring]
            for first, second in zip(points, points[1:]):
                canvas.line(first, second, (203, 79, 50), width=3)

    panel_x = 1045
    canvas.text(panel_x, 150, "VALIDATION", (25, 43, 68), scale=3)
    canvas.rect(panel_x, 208, panel_x + 38, 246, (203, 79, 50))
    canvas.text(panel_x + 55, 214, "COCLE", (50, 64, 82), scale=2)
    canvas.rect(panel_x, 275, panel_x + 38, 313, (170, 178, 188))
    canvas.text(panel_x + 55, 281, "OTHER PROVINCES", (50, 64, 82), scale=2)
    canvas.text(panel_x, 360, "SOURCE: IGN / ANATI", (50, 64, 82), scale=2)
    canvas.text(panel_x, 390, "LAYER: LIMI_PROV_A", (50, 64, 82), scale=2)
    canvas.text(panel_x, 420, "ORIGINAL: EPSG:32617", (50, 64, 82), scale=2)
    canvas.text(panel_x, 450, "OUTPUT: EPSG:4326", (50, 64, 82), scale=2)
    canvas.text(panel_x, 500, "NO WEB BASEMAP", (50, 64, 82), scale=2)
    canvas.text(panel_x, 530, "REFERENCE MAP ONLY", (50, 64, 82), scale=2)
    west, south, east, north = geo_bbox
    canvas.text(panel_x, 600, f"BBOX {west:.2f},{south:.2f}", (50, 64, 82), scale=2)
    canvas.text(panel_x, 630, f"TO {east:.2f},{north:.2f}", (50, 64, 82), scale=2)
    canvas.text(70, 855, "Source geometry preserved; no dissolve, simplify, or web basemap used.", (75, 86, 99), scale=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canvas.png_bytes())
