"""Dependency-free SVG figures for the observability report."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .sentinel2_observability import USABILITY_RULES, WINDOW_PAIR_OPTIONS


WIDTH = 960
HEIGHT = 540


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _svg_start(title: str, subtitle: str = "") -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="48" y="48" font-family="Arial,sans-serif" font-size="24" font-weight="700" fill="#0f172a">{_esc(title)}</text>',
        f'<text x="48" y="76" font-family="Arial,sans-serif" font-size="13" fill="#475569">{_esc(subtitle)}</text>',
    ]


def _svg_end(lines: list[str]) -> str:
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_svg_end(lines), encoding="utf-8")


def _bar_chart(path: Path, title: str, items: Sequence[tuple[str, float]], *, subtitle: str = "", color: str = "#0f766e") -> None:
    lines = _svg_start(title, subtitle)
    max_value = max((value for _, value in items), default=1.0) or 1.0
    chart_left, chart_top, chart_width, chart_height = 72, 112, 840, 350
    bar_width = chart_width / max(len(items), 1) * 0.72
    for index, (label, value) in enumerate(items):
        x = chart_left + (index + 0.5) * chart_width / max(len(items), 1) - bar_width / 2
        height = chart_height * value / max_value
        y = chart_top + chart_height - height
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{height:.1f}" rx="4" fill="{color}"/>')
        lines.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#0f172a">{_esc(round(value, 2))}</text>')
        lines.append(f'<text x="{x + bar_width / 2:.1f}" y="{chart_top + chart_height + 24}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" fill="#334155">{_esc(label)}</text>')
    lines.append(f'<line x1="{chart_left}" y1="{chart_top + chart_height}" x2="{chart_left + chart_width}" y2="{chart_top + chart_height}" stroke="#94a3b8"/>')
    _write(path, lines)


def _heatmap(path: Path, title: str, rows: Sequence[Mapping[str, Any]], rule_id: str) -> None:
    lines = _svg_start(title, f"Eventos con pareja usable; regla {rule_id}. Cada celda resume los 30 eventos.")
    aoi_ids = ["b0500", "b1000", "b1500"]
    cell_w, cell_h, left, top = 190, 62, 190, 130
    values: dict[tuple[str, str], int] = {}
    for aoi_id in aoi_ids:
        for window_id in WINDOW_PAIR_OPTIONS:
            values[(aoi_id, window_id)] = sum(
                1
                for row in rows
                if row.get("aoi_id") == aoi_id
                and row.get("window_id") == window_id
                and row.get("rule_id") == rule_id
                and str(row.get("usable_pair_exists")).casefold() == "true"
            )
    maximum = max(values.values(), default=1) or 1
    for column, window_id in enumerate(WINDOW_PAIR_OPTIONS):
        x = left + column * cell_w
        lines.append(f'<text x="{x + cell_w / 2}" y="{top - 16}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" fill="#334155">{_esc(window_id)}</text>')
    for row_index, aoi_id in enumerate(aoi_ids):
        y = top + row_index * cell_h
        lines.append(f'<text x="{left - 18}" y="{y + cell_h / 2 + 4}" text-anchor="end" font-family="Arial,sans-serif" font-size="12" fill="#334155">{_esc(aoi_id)}</text>')
        for column, window_id in enumerate(WINDOW_PAIR_OPTIONS):
            value = values[(aoi_id, window_id)]
            opacity = 0.15 + 0.8 * value / maximum
            x = left + column * cell_w
            lines.append(f'<rect x="{x}" y="{y}" width="{cell_w - 8}" height="{cell_h - 8}" rx="4" fill="#0f766e" fill-opacity="{opacity:.2}"/>')
            lines.append(f'<text x="{x + (cell_w - 8) / 2}" y="{y + 31}" text-anchor="middle" font-family="Arial,sans-serif" font-size="17" font-weight="700" fill="#0f172a">{value}</text>')
    _write(path, lines)


def generate_observability_figures(
    output_dir: Path | str,
    report: Mapping[str, Any],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
) -> list[Path]:
    """Write compact SVG charts without downloading imagery or requiring matplotlib."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    attrition = [
        ("pilot", float(report.get("pilot_universe_count", 0))),
        ("requested", float(report.get("requested_event_count", 0))),
        ("processed", float(report.get("events_processed", 0))),
        ("pre scene", float(report.get("events_with_at_least_one_pre_scene", 0))),
        ("post scene", float(report.get("events_with_at_least_one_post_scene", 0))),
        ("usable pair", float(report.get("events_with_any_usable_pair", 0))),
    ]
    path = directory / "attrition_flow.svg"
    _bar_chart(path, "Flujo de atrición", attrition, subtitle="Conteos de eventos; la atrición no es una etiqueta negativa.", color="#0f766e")
    generated.append(path)

    path = directory / "usable_pair_heatmap_buffer_window_rule_B.svg"
    _heatmap(path, "Parejas utilizables por AOI y ventana", observation_rows, "B")
    generated.append(path)

    rule_items = [(rule_id, float(report.get("rules", {}).get(rule_id, {}).get("events_with_usable_pair", 0))) for rule_id in USABILITY_RULES]
    path = directory / "comparison_rules_A_D.svg"
    _bar_chart(path, "Comparación de reglas A-D", rule_items, subtitle="Eventos con al menos una pareja utilizable en alguna combinación.", color="#2563eb")
    generated.append(path)

    clear_values = [float(row["clear_fraction_cs_cdf_060"]) for row in scene_rows if row.get("clear_fraction_cs_cdf_060") not in (None, "")]
    clear_bins = Counter(min(4, max(0, int(value * 5))) for value in clear_values)
    path = directory / "clear_fraction_distribution.svg"
    _bar_chart(path, "Distribución de claridad AOI", [(f"{index / 5:.1f}-{(index + 1) / 5:.1f}", clear_bins[index]) for index in range(5)], subtitle="Barras por cs_cdf; no es una clasificación de quema.", color="#7c3aed")
    generated.append(path)

    coverage_values = [float(row["data_coverage_fraction"]) for row in scene_rows if row.get("data_coverage_fraction") not in (None, "")]
    coverage_bins = Counter(min(4, max(0, int(value * 5))) for value in coverage_values)
    path = directory / "data_coverage_fraction_distribution.svg"
    _bar_chart(path, "Distribución de cobertura B8/B12", [(f"{index / 5:.1f}-{(index + 1) / 5:.1f}", coverage_bins[index]) for index in range(5)], subtitle="Fracción con máscara válida conjunta de B8 y B12.", color="#ea580c")
    generated.append(path)

    scene_counts: dict[str, int] = Counter(str(row["event_id"]) for row in scene_rows)
    path = directory / "scenes_available_per_event.svg"
    _bar_chart(path, "Escenas disponibles por evento", [(event_id[-8:], value) for event_id, value in sorted(scene_counts.items())], subtitle="Últimos 8 caracteres del event_id; pre y post combinados.", color="#0891b2")
    generated.append(path)

    size_pair: dict[str, set[str]] = defaultdict(set)
    for row in observation_rows:
        if str(row.get("usable_pair_exists")).casefold() == "true":
            size_pair[str(row.get("event_size_class", "unknown"))].add(str(row["event_id"]))
    size_total = Counter(str(row.get("event_size_class", "unknown")) for row in observation_rows)
    path = directory / "singleton_vs_multi_detection.svg"
    _bar_chart(path, "Singleton frente a multi-detección", [(key, len(value)) for key, value in sorted(size_pair.items())], subtitle="Eventos con alguna pareja; la tabla de sensibilidad conserva el denominador completo.", color="#be123c")
    generated.append(path)

    month_pair: dict[str, set[str]] = defaultdict(set)
    for row in observation_rows:
        if str(row.get("usable_pair_exists")).casefold() == "true":
            month_pair[str(row.get("event_month", "unknown"))].add(str(row["event_id"]))
    path = directory / "availability_by_month.svg"
    _bar_chart(path, "Disponibilidad por mes", [(month, len(events)) for month, events in sorted(month_pair.items())], subtitle="Eventos con alguna pareja utilizable.", color="#65a30d")
    generated.append(path)

    gaps = Counter()
    for row in observation_rows:
        for key in ("days_between_event_and_pre", "days_between_event_and_post"):
            value = row.get(key)
            if value not in (None, ""):
                gaps[min(9, max(0, int(float(value) // 10)))] += 1
    path = directory / "event_scene_gaps.svg"
    _bar_chart(path, "Días entre evento y escena seleccionada", [(f"{index * 10}-{index * 10 + 10}d", gaps[index]) for index in range(10)], subtitle="Distribución descriptiva de escenas seleccionadas por regla.", color="#9333ea")
    generated.append(path)

    return generated
