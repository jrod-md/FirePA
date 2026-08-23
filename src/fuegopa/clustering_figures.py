"""Dependency-free PNG diagnostics for the clustering sensitivity run."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

from .clustering import (
    DEFAULT_CONFIGURATIONS,
    RADIUS_GRID,
    TIME_WINDOW_GRID,
    ClusterResult,
    Detection,
)
from .boundary_figure import Canvas
from .geo import Boundary


Color = tuple[int, int, int]

NAVY: Color = (25, 43, 68)
INK: Color = (50, 64, 82)
MUTED: Color = (95, 108, 122)
BACKGROUND: Color = (248, 250, 252)
GRID: Color = (220, 226, 232)
ORANGE: Color = (203, 79, 50)
BLUE: Color = (42, 116, 170)
PALETTE: tuple[Color, ...] = (
    (203, 79, 50),
    (42, 116, 170),
    (43, 140, 105),
    (144, 93, 169),
    (221, 147, 43),
    (68, 121, 189),
    (142, 87, 62),
    (80, 151, 155),
    (160, 90, 128),
    (101, 125, 55),
    (185, 105, 45),
    (85, 85, 150),
)


def _value(row: Mapping[str, Any], key: str) -> float | None:
    raw = row.get(key)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _display(value: Any) -> str:
    if value is None or value == "":
        return "NA"
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _header(canvas: Canvas, title: str, subtitle: str, width: int) -> None:
    canvas.rect(0, 0, width - 1, 78, NAVY)
    canvas.text(36, 20, "FUEGOPA - FIRMS CLUSTERING", (255, 255, 255), scale=3)
    canvas.text(38, 95, title, NAVY, scale=3)
    canvas.text(38, 137, subtitle, INK, scale=2)


def _footer(canvas: Canvas, width: int, height: int, boundary: Boundary | None = None) -> None:
    canvas.text(
        38,
        height - 86,
        "PROVISIONAL ALGORITHMIC CLUSTERS - NOT CONFIRMED FIRES",
        ORANGE,
        scale=2,
    )
    canvas.text(
        38,
        height - 54,
        "FIRMS OBSERVATIONS ARE THERMAL ANOMALIES - NOT INDEPENDENT FIRES",
        MUTED,
        scale=2,
    )
    canvas.text(
        width - 600,
        height - 54,
        "2025-01-01..2025-04-30 | VIIRS NOAA20 SP + SNPP SP",
        MUTED,
        scale=2,
    )
    if boundary is None:
        canvas.text(width - 600, height - 86, "BOUNDARY NOT PROVIDED - EXTENT ONLY", MUTED, scale=2)


def _mix(first: Color, second: Color, ratio: float) -> Color:
    ratio = min(1.0, max(0.0, ratio))
    return tuple(round(first[index] + (second[index] - first[index]) * ratio) for index in range(3))  # type: ignore[return-value]


def _write_heatmap(
    path: Path,
    summary_rows: Iterable[Mapping[str, Any]],
    metric: str,
    title: str,
    unit: str,
    boundary: Boundary | None,
) -> None:
    rows_by_id = {str(row["configuration_id"]): row for row in summary_rows}
    values = [_value(row, metric) for row in rows_by_id.values()]
    numeric = [value for value in values if value is not None]
    low = min(numeric, default=0.0)
    high = max(numeric, default=1.0)
    canvas = Canvas(1600, 950, (255, 255, 255))
    _header(
        canvas,
        title,
        f"Grid: radius 375/750/1500/3000 m x window 6/12/24/48 h | unit: {unit}",
        1600,
    )
    left, top = 260, 205
    cell_width, cell_height = 280, 112
    canvas.text(58, top - 42, "RADIUS M", INK, scale=2)
    for column, hours in enumerate(TIME_WINDOW_GRID):
        x = left + column * cell_width
        canvas.text(x + 76, top - 42, f"{hours} H", INK, scale=2)
    for row_index, radius in enumerate(RADIUS_GRID):
        y = top + row_index * cell_height
        canvas.text(70, y + 42, str(radius), INK, scale=2)
        for column, hours in enumerate(TIME_WINDOW_GRID):
            configuration_id = f"r{radius:04d}_t{hours:02d}"
            x = left + column * cell_width
            value = _value(rows_by_id.get(configuration_id, {}), metric)
            ratio = (value - low) / (high - low) if value is not None and high > low else 0.5
            canvas.rect(x, y, x + cell_width - 10, y + cell_height - 10, _mix((226, 239, 247), ORANGE, ratio))
            canvas.text(x + 26, y + 28, _display(value), NAVY, scale=3)
            canvas.text(x + 26, y + 76, configuration_id, INK, scale=1)
    canvas.text(260, 700, f"LOW {_display(low)}", BLUE, scale=2)
    canvas.rect(400, 696, 740, 723, _mix((226, 239, 247), ORANGE, 0.5))
    canvas.text(770, 700, f"HIGH {_display(high)}", ORANGE, scale=2)
    canvas.text(260, 760, "Higher values are darker/oranger; the scale is descriptive within this run.", MUTED, scale=2)
    _footer(canvas, 1600, 950, boundary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canvas.png_bytes())


def _map_bounds(detections: Iterable[Detection], boundary: Boundary | None) -> tuple[float, float, float, float]:
    points = [(detection.longitude, detection.latitude) for detection in detections]
    if boundary is not None:
        points.extend(
            point
            for outer, holes in boundary.polygons
            for ring in (outer, *holes)
            for point in ring
        )
    if not points:
        return (-81.0, 8.0, -80.0, 9.0)
    west = min(point[0] for point in points)
    south = min(point[1] for point in points)
    east = max(point[0] for point in points)
    north = max(point[1] for point in points)
    longitude_padding = max((east - west) * 0.06, 0.01)
    latitude_padding = max((north - south) * 0.06, 0.01)
    return west - longitude_padding, south - latitude_padding, east + longitude_padding, north + latitude_padding


def _projector(bounds: tuple[float, float, float, float], plot: tuple[int, int, int, int]):
    west, south, east, north = bounds
    left, top, right, bottom = plot
    width = max(east - west, 1e-9)
    height = max(north - south, 1e-9)
    scale = min((right - left) / width, (bottom - top) / height)
    map_width = width * scale
    map_height = height * scale
    x_offset = left + ((right - left) - map_width) / 2
    y_offset = top + ((bottom - top) - map_height) / 2

    def project(point: tuple[float, float]) -> tuple[int, int]:
        return round(x_offset + (point[0] - west) * scale), round(y_offset + (north - point[1]) * scale)

    return project


def _color_for(value: str) -> Color:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return PALETTE[int.from_bytes(digest[:2], "big") % len(PALETTE)]


def _draw_boundary(canvas: Canvas, boundary: Boundary | None, project, plot: tuple[int, int, int, int]) -> None:
    if boundary is None:
        return
    for outer, holes in boundary.polygons:
        outer_points = [project(point) for point in outer]
        canvas.polygon_fill(outer_points, (238, 242, 245), plot)
        for hole in holes:
            canvas.polygon_fill([project(point) for point in hole], BACKGROUND, plot)
        for ring in (outer, *holes):
            points = [project(point) for point in ring]
            for first, second in zip(points, points[1:]):
                canvas.line(first, second, (135, 150, 163), width=2)


def _draw_map_panel(
    canvas: Canvas,
    result: ClusterResult,
    detections: Iterable[Detection],
    boundary: Boundary | None,
    plot: tuple[int, int, int, int],
    title: str,
    highlight_event_ids: set[str] | None = None,
) -> None:
    detections = tuple(detections)
    bounds = _map_bounds(detections, boundary)
    project = _projector(bounds, plot)
    canvas.rect(plot[0], plot[1], plot[2], plot[3], BACKGROUND)
    _draw_boundary(canvas, boundary, project, plot)
    event_by_detection = {
        str(row["detection_id"]): str(row["event_id"]) for row in result.membership
    }
    event_color = {event["event_id"]: _color_for(str(event["event_id"])) for event in result.events}
    for detection in detections:
        event_id = event_by_detection.get(detection.detection_id)
        if highlight_event_ids is not None and event_id not in highlight_event_ids:
            color = (183, 191, 199)
            size = 2
        else:
            color = event_color.get(event_id, (100, 110, 120))
            size = 4 if event_id in (highlight_event_ids or {event_id}) else 3
        x, y = project((detection.longitude, detection.latitude))
        canvas.rect(x - size, y - size, x + size, y + size, color)
    canvas.text(plot[0] + 12, plot[1] + 14, title, NAVY, scale=2)
    canvas.text(plot[0] + 12, plot[1] + 48, result.configuration.configuration_id, INK, scale=1)


def _write_representative_maps(
    path: Path,
    results: Mapping[str, ClusterResult],
    detections: Iterable[Detection],
    boundary: Boundary | None,
) -> None:
    selected_ids = ("r0375_t06", "r0750_t12", "r1500_t24", "r3000_t48")
    canvas = Canvas(1800, 1400, (255, 255, 255))
    _header(canvas, "Representative provisional clusters", "Four corners of the prespecified sensitivity grid; visualization only", 1800)
    plots = ((50, 200, 840, 800), (900, 200, 1690, 800), (50, 840, 840, 1280), (900, 840, 1690, 1280))
    for configuration_id, plot in zip(selected_ids, plots):
        _draw_map_panel(
            canvas,
            results[configuration_id],
            detections,
            boundary,
            plot,
            configuration_id,
        )
    _footer(canvas, 1800, 1400, boundary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canvas.png_bytes())


def _write_largest_events_map(
    path: Path,
    results: Mapping[str, ClusterResult],
    detections: Iterable[Detection],
    boundary: Boundary | None,
) -> None:
    all_events = [
        (configuration_id, event)
        for configuration_id, result in results.items()
        for event in result.events
    ]
    all_events.sort(
        key=lambda item: (-int(item[1]["detection_count"]), str(item[0]), str(item[1]["event_id"]))
    )
    selected = all_events[:10]
    selected_keys = {(configuration_id, str(event["event_id"])) for configuration_id, event in selected}
    canvas = Canvas(1800, 1100, (255, 255, 255))
    _header(
        canvas,
        "Largest algorithmic components across the grid",
        "Top 10 by detection count; each configuration/event remains distinct",
        1800,
    )
    bounds = _map_bounds(detections, boundary)
    plot = (50, 190, 1250, 960)
    project = _projector(bounds, plot)
    canvas.rect(plot[0], plot[1], plot[2], plot[3], BACKGROUND)
    _draw_boundary(canvas, boundary, project, plot)
    membership_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for configuration_id, result in results.items():
        selected_event_ids = {
            str(event["event_id"])
            for selected_configuration, event in selected
            if selected_configuration == configuration_id
        }
        for row in result.membership:
            if str(row["event_id"]) in selected_event_ids:
                membership_by_key[(configuration_id, str(row["event_id"]))].add(str(row["detection_id"]))
    detection_by_id = {detection.detection_id: detection for detection in detections}
    for selected_index, (configuration_id, event) in enumerate(selected):
        color = PALETTE[selected_index % len(PALETTE)]
        for detection_id in membership_by_key[(configuration_id, str(event["event_id"]))]:
            detection = detection_by_id.get(detection_id)
            if detection is None:
                continue
            x, y = project((detection.longitude, detection.latitude))
            canvas.rect(x - 5, y - 5, x + 5, y + 5, color)
    canvas.text(1310, 205, "TOP 10", NAVY, scale=3)
    for index, (configuration_id, event) in enumerate(selected):
        y = 270 + index * 62
        color = PALETTE[index % len(PALETTE)]
        canvas.rect(1310, y, 1348, y + 38, color)
        canvas.text(1370, y + 3, f"{index + 1} {configuration_id}", INK, scale=1)
        canvas.text(1370, y + 28, f"N={event['detection_count']} {event['event_id'][-8:]}", MUTED, scale=1)
    _footer(canvas, 1800, 1100, boundary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canvas.png_bytes())


def _write_stability_graph(path: Path, stability_rows: Iterable[Mapping[str, Any]], boundary: Boundary | None) -> None:
    values: dict[str, list[float]] = defaultdict(list)
    for row in stability_rows:
        value = _value(row, "jaccard_coassignment")
        if value is None:
            continue
        values[str(row["configuration_id_a"])].append(value)
        values[str(row["configuration_id_b"])].append(value)
    means = {
        configuration.configuration_id: (mean(values[configuration.configuration_id]) if values[configuration.configuration_id] else None)
        for configuration in DEFAULT_CONFIGURATIONS
    }
    canvas = Canvas(1800, 1000, (255, 255, 255))
    _header(canvas, "Configuration stability graph", "Mean co-assignment Jaccard with adjacent grid configurations", 1800)
    plot = (100, 210, 1680, 800)
    canvas.rect(plot[0], plot[1], plot[2], plot[3], BACKGROUND)
    canvas.line((plot[0], plot[3]), (plot[2], plot[3]), GRID, width=2)
    for tick in range(0, 6):
        y = plot[3] - round((plot[3] - plot[1]) * tick / 5)
        canvas.line((plot[0], y), (plot[2], y), GRID, width=1)
        canvas.text(24, y - 7, f"{tick / 5:.1f}", MUTED, scale=1)
    bar_width = 88
    gap = 16
    for index, configuration in enumerate(DEFAULT_CONFIGURATIONS):
        value = means[configuration.configuration_id]
        height = round((plot[3] - plot[1]) * (value or 0.0))
        left = plot[0] + 18 + index * (bar_width + gap)
        right = left + bar_width
        canvas.rect(left, plot[3] - height, right, plot[3], _mix((226, 239, 247), BLUE, value or 0.0))
        canvas.text(left + 7, plot[3] + 16, f"r{configuration.radius_m}", INK, scale=1)
        canvas.text(left + 7, plot[3] + 39, f"t{configuration.time_window_hours}", INK, scale=1)
        canvas.text(left + 7, plot[3] - height - 24, _display(value), NAVY, scale=1)
    canvas.text(100, 850, "Higher Jaccard = less change in pair co-assignment across immediate neighbors.", MUTED, scale=2)
    _footer(canvas, 1800, 1000, boundary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canvas.png_bytes())


def write_clustering_figures(
    figures_dir: Path,
    results: Mapping[str, ClusterResult],
    summary_rows: Iterable[Mapping[str, Any]],
    stability_rows: Iterable[Mapping[str, Any]],
    detections: Iterable[Detection],
    boundary: Boundary | None = None,
) -> None:
    """Render all requested diagnostic figures without plotting dependencies."""

    figures_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = list(summary_rows)
    stability_rows = list(stability_rows)
    detections = tuple(detections)
    heatmaps = (
        ("event_count", "Event count heatmap", "events", "event_count"),
        ("singleton_rate_pct", "Singleton rate heatmap", "% events", "singleton_rate_pct"),
        ("median_duration_hours", "Median duration heatmap", "hours", "median_duration_hours"),
        ("median_spatial_extent_m", "Median spatial extent heatmap", "meters", "median_spatial_extent_m"),
        ("events_possible_chain_merge", "Possible chain-merge count heatmap", "events", "events_possible_chain_merge"),
    )
    for filename, title, unit, metric in heatmaps:
        _write_heatmap(figures_dir / f"{filename}.png", summary_rows, metric, title, unit, boundary)
    _write_representative_maps(figures_dir / "representative_maps_2x2.png", results, detections, boundary)
    _write_largest_events_map(figures_dir / "largest_events_map.png", results, detections, boundary)
    _write_stability_graph(figures_dir / "configuration_stability.png", stability_rows, boundary)
