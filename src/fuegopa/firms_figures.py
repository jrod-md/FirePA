"""Dependency-free descriptive FIRMS figures for the audited 2025 cohort."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from .boundary_figure import Canvas
from .geo import Boundary, load_boundary


MAIN_START = date(2025, 1, 1)
MAIN_END = date(2025, 4, 30)
OBSERVATION_NOTE = "FIRMS: ANOMALIAS TERMICAS - NO INCENDIOS INDEPENDIENTES CONFIRMADOS"
PLOT = (100, 150, 1240, 700)
NAVY = (25, 43, 68)
TEXT = (50, 64, 82)
MUTED = (92, 105, 119)
GRID = (220, 226, 232)
BLUE = (45, 111, 168)
ORANGE = (214, 111, 54)
RED = (203, 79, 50)
GREEN = (52, 132, 102)
PALETTE = (BLUE, ORANGE, RED, GREEN)


def _read_processed(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"latitude", "longitude", "acq_date", "frp", "firms_source"}
        headers = set(reader.fieldnames or [])
        missing = sorted(required - headers)
        if missing:
            raise ValueError(f"El CSV procesado no contiene columnas para figuras: {', '.join(missing)}")
        rows = list(reader)
    for row_number, row in enumerate(rows, start=2):
        try:
            parsed_date = date.fromisoformat(row["acq_date"])
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            frp = float(row["frp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Fila procesada inválida para figuras: {row_number}") from exc
        if not MAIN_START <= parsed_date <= MAIN_END:
            raise ValueError(f"El CSV procesado contiene una fecha fuera de 2025-01-01..2025-04-30: fila {row_number}")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"El CSV procesado contiene coordenadas inválidas: fila {row_number}")
        if not math.isfinite(frp) or frp < 0:
            raise ValueError(f"El CSV procesado contiene FRP inválido: fila {row_number}")
    return rows


def _raw_counts(raw_dir: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not raw_dir.exists():
        return counts
    pattern = re.compile(r"^firms_(.+?)_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}$", re.IGNORECASE)
    for path in sorted(raw_dir.glob("*.csv")):
        match = pattern.match(path.stem)
        if not match:
            continue
        source = match.group(1).upper()
        rows = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            rows = sum(1 for _ in reader)
        counts[source] += rows
    return counts


def _projector(boundary: Boundary, plot: tuple[int, int, int, int]):
    west, south, east, north = boundary.bbox
    left, top, right, bottom = plot
    width = max(east - west, 1e-9)
    height = max(north - south, 1e-9)
    scale = min((right - left) / width, (bottom - top) / height)
    map_width = width * scale
    map_height = height * scale
    x_offset = left + ((right - left) - map_width) / 2
    y_offset = top + ((bottom - top) - map_height) / 2

    def project(longitude: float, latitude: float) -> tuple[int, int]:
        return round(x_offset + (longitude - west) * scale), round(y_offset + (north - latitude) * scale)

    return project


def _header(canvas: Canvas, title: str, subtitle: str = "") -> None:
    canvas.rect(0, 0, canvas.width - 1, 82, NAVY)
    canvas.text(38, 22, title, (255, 255, 255), scale=3)
    if subtitle:
        canvas.text(100, 102, subtitle, TEXT, scale=2)


def _footer(canvas: Canvas, count: int) -> None:
    canvas.text(100, 790, OBSERVATION_NOTE, MUTED, scale=1)
    canvas.text(100, 815, f"N = {count} | PERIODO: 2025-01-01 A 2025-04-30 | DESCRIPTIVO", MUTED, scale=1)


def _axes(canvas: Canvas, plot: tuple[int, int, int, int], y_max: int, y_ticks: int = 5) -> None:
    left, top, right, bottom = plot
    canvas.line((left, bottom), (right, bottom), TEXT, width=2)
    canvas.line((left, top), (left, bottom), TEXT, width=2)
    for tick in range(y_ticks + 1):
        value = round(y_max * tick / y_ticks)
        y = bottom - round((bottom - top) * tick / y_ticks)
        canvas.line((left, y), (right, y), GRID, width=1)
        canvas.text(44, y - 5, str(value), MUTED, scale=1)


def _draw_bar(canvas: Canvas, left: int, top: int, right: int, bottom: int, color: tuple[int, int, int]) -> None:
    canvas.rect(left, top, right, bottom, color)


def _draw_daily(rows: list[dict[str, str]], path: Path) -> None:
    counts = Counter(date.fromisoformat(row["acq_date"]) for row in rows)
    days = [MAIN_START + timedelta(days=offset) for offset in range((MAIN_END - MAIN_START).days + 1)]
    maximum = max(counts.values(), default=1)
    y_max = max(10, math.ceil(maximum / 10) * 10)
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - CONTEO DIARIO", "OBSERVACIONES PROCESADAS DENTRO DE COCLE")
    _axes(canvas, PLOT, y_max)
    left, top, right, bottom = PLOT
    bar_width = max(2, (right - left) // len(days) - 2)
    for index, day in enumerate(days):
        x = left + round(index * (right - left) / len(days))
        height = round((bottom - top) * counts[day] / y_max)
        _draw_bar(canvas, x, bottom - height, x + bar_width, bottom - 1, BLUE)
        if day.day == 1:
            canvas.text(x - 3, bottom + 14, day.strftime("%b").upper(), TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _draw_weekly(rows: list[dict[str, str]], path: Path) -> None:
    counts = Counter(_week_start(date.fromisoformat(row["acq_date"])) for row in rows)
    first = _week_start(MAIN_START)
    last = _week_start(MAIN_END)
    weeks = [first + timedelta(days=7 * index) for index in range(((last - first).days // 7) + 1)]
    maximum = max(counts.values(), default=1)
    y_max = max(50, math.ceil(maximum / 50) * 50)
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - CONTEO SEMANAL", "SEMANA INICIADA EN LUNES; AGRUPACION DESCRIPTIVA")
    _axes(canvas, PLOT, y_max)
    left, top, right, bottom = PLOT
    slot = (right - left) / len(weeks)
    bar_width = max(5, round(slot * 0.7))
    for index, week in enumerate(weeks):
        x = left + round(index * slot + (slot - bar_width) / 2)
        height = round((bottom - top) * counts[week] / y_max)
        _draw_bar(canvas, x, bottom - height, x + bar_width, bottom - 1, ORANGE)
        if index % 4 == 0:
            canvas.text(x - 5, bottom + 14, week.strftime("%b-%d").upper(), TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def _draw_frp(rows: list[dict[str, str]], path: Path) -> None:
    values = [float(row["frp"]) for row in rows]
    minimum = min(values, default=0.0)
    maximum = max(values, default=1.0)
    bin_count = 8
    width = (maximum - minimum) / bin_count if maximum > minimum else 1.0
    bins = [0] * bin_count
    for value in values:
        index = min(bin_count - 1, max(0, int((value - minimum) / width)))
        bins[index] += 1
    y_max = max(10, math.ceil(max(bins, default=1) / 10) * 10)
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - DISTRIBUCION DE FRP", "HISTOGRAMA DESCRIPTIVO DEL PRODUCTO PROCESADO")
    _axes(canvas, PLOT, y_max)
    left, top, right, bottom = PLOT
    slot = (right - left) / bin_count
    for index, count in enumerate(bins):
        x = left + round(index * slot + 8)
        x_right = left + round((index + 1) * slot - 8)
        height = round((bottom - top) * count / y_max)
        _draw_bar(canvas, x, bottom - height, x_right, bottom - 1, RED)
        label = f"{minimum + index * width:.0f}"
        canvas.text(x, bottom + 14, label, TEXT, scale=1)
    canvas.text(100, 735, f"FRP MIN={minimum:.1f} MAX={maximum:.1f} | UNIDADES SEGUN EL PRODUCTO FIRMS", TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def _draw_source_comparison(rows: list[dict[str, str]], raw_dir: Path, path: Path) -> None:
    processed = Counter(row["firms_source"] for row in rows)
    raw = _raw_counts(raw_dir)
    sources = sorted(set(processed) | set(raw))
    maximum = max([raw[source] for source in sources] + [processed[source] for source in sources] + [1])
    y_max = max(100, math.ceil(maximum / 100) * 100)
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - COMPARACION POR FUENTE", "FILAS RAW AUDITADAS FRENTE A FILAS FINALES DENTRO DE COCLE")
    _axes(canvas, PLOT, y_max)
    left, top, right, bottom = PLOT
    slot = (right - left) / max(1, len(sources))
    for index, source in enumerate(sources):
        center = left + round((index + 0.5) * slot)
        raw_height = round((bottom - top) * raw[source] / y_max)
        final_height = round((bottom - top) * processed[source] / y_max)
        _draw_bar(canvas, center - 42, bottom - raw_height, center - 8, bottom - 1, BLUE)
        _draw_bar(canvas, center + 8, bottom - final_height, center + 42, bottom - 1, ORANGE)
        canvas.text(center - 70, bottom + 18, source.replace("VIIRS_", ""), TEXT, scale=1)
        canvas.text(center - 42, bottom - raw_height - 18, str(raw[source]), BLUE, scale=1)
        canvas.text(center + 8, bottom - final_height - 18, str(processed[source]), ORANGE, scale=1)
    canvas.rect(1030, 105, 1050, 125, BLUE)
    canvas.text(1060, 107, "RAW", TEXT, scale=1)
    canvas.rect(1160, 105, 1180, 125, ORANGE)
    canvas.text(1190, 107, "COCLE", TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def _draw_boundary_outline(canvas: Canvas, boundary: Boundary, project, color: tuple[int, int, int], width: int = 2) -> None:
    for outer, holes in boundary.polygons:
        for ring in (outer, *holes):
            points = [project(longitude, latitude) for longitude, latitude in ring]
            for first, second in zip(points, points[1:]):
                canvas.line(first, second, color, width=width)


def _points(rows: Iterable[dict[str, str]]) -> list[tuple[float, float, str]]:
    return [(float(row["longitude"]), float(row["latitude"]), row["firms_source"]) for row in rows]


def _draw_detections_map(rows: list[dict[str, str]], boundary: Boundary, path: Path) -> None:
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - DETECCIONES EN COCLE", "PUNTOS PROCESADOS SOBRE EL LIMITE ADMINISTRATIVO")
    canvas.rect(PLOT[0], PLOT[1], PLOT[2], PLOT[3], (248, 250, 252))
    project = _projector(boundary, PLOT)
    _draw_boundary_outline(canvas, boundary, project, RED, width=3)
    source_colors = {source: PALETTE[index % len(PALETTE)] for index, source in enumerate(sorted({row["firms_source"] for row in rows}))}
    for longitude, latitude, source in _points(rows):
        x, y = project(longitude, latitude)
        color = source_colors[source]
        canvas.rect(x - 2, y - 2, x + 2, y + 2, color)
    legend_y = 108
    for source, color in sorted(source_colors.items()):
        canvas.rect(1030, legend_y, 1050, legend_y + 20, color)
        canvas.text(1065, legend_y + 1, source.replace("VIIRS_", ""), TEXT, scale=1)
        legend_y += 28
    canvas.text(100, 735, "LIMITE EN ROJO; LOS PUNTOS SON OBSERVACIONES TERMICAS INDIVIDUALES", TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def _density_color(value: int, maximum: int) -> tuple[int, int, int]:
    if maximum <= 0:
        return (238, 242, 246)
    intensity = value / maximum
    return (255, round(238 - 150 * intensity), round(224 - 150 * intensity))


def _draw_density(rows: list[dict[str, str]], boundary: Boundary, path: Path) -> None:
    canvas = Canvas(1400, 850)
    _header(canvas, "FIRMS - DENSIDAD ESPACIAL", "CELDAS REGULARES DESCRIPTIVAS SOBRE COCLE")
    canvas.rect(PLOT[0], PLOT[1], PLOT[2], PLOT[3], (248, 250, 252))
    project = _projector(boundary, PLOT)
    west, south, east, north = boundary.bbox
    columns, rows_count = 16, 16
    counts: defaultdict[tuple[int, int], int] = defaultdict(int)
    for longitude, latitude, _ in _points(rows):
        column = min(columns - 1, max(0, int((longitude - west) / (east - west) * columns)))
        row_index = min(rows_count - 1, max(0, int((north - latitude) / (north - south) * rows_count)))
        counts[(column, row_index)] += 1
    maximum = max(counts.values(), default=0)
    for row_index in range(rows_count):
        for column in range(columns):
            left_point = project(west + (east - west) * column / columns, north - (north - south) * row_index / rows_count)
            right_point = project(west + (east - west) * (column + 1) / columns, north - (north - south) * (row_index + 1) / rows_count)
            canvas.rect(left_point[0], left_point[1], right_point[0], right_point[1], _density_color(counts[(column, row_index)], maximum))
    _draw_boundary_outline(canvas, boundary, project, RED, width=3)
    canvas.text(1020, 105, f"MAX CELDA = {maximum}", TEXT, scale=1)
    canvas.text(100, 735, "CELDAS DE 16 X 16; NO REPRESENTA EVENTOS NI CICATRICES DE QUEMA", TEXT, scale=1)
    _footer(canvas, len(rows))
    path.write_bytes(canvas.png_bytes())


def write_firms_figures(
    processed_path: Path,
    boundary_path: Path,
    output_dir: Path,
    raw_dir: Path | None = None,
) -> dict[str, Path]:
    """Build six deterministic, descriptive PNGs from existing local artifacts."""

    rows = _read_processed(processed_path)
    boundary = load_boundary(boundary_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = raw_dir or processed_path.parents[1] / "raw"
    paths = {
        "daily_counts": output_dir / "firms_daily_counts_2025.png",
        "weekly_counts": output_dir / "firms_weekly_counts_2025.png",
        "frp_distribution": output_dir / "firms_frp_distribution_2025.png",
        "source_comparison": output_dir / "firms_source_comparison_2025.png",
        "detections_cocle_boundary": output_dir / "firms_detections_cocle_boundary_2025.png",
        "spatial_density": output_dir / "firms_spatial_density_2025.png",
    }
    _draw_daily(rows, paths["daily_counts"])
    _draw_weekly(rows, paths["weekly_counts"])
    _draw_frp(rows, paths["frp_distribution"])
    _draw_source_comparison(rows, raw_dir, paths["source_comparison"])
    _draw_detections_map(rows, boundary, paths["detections_cocle_boundary"])
    _draw_density(rows, boundary, paths["spatial_density"])
    return paths
