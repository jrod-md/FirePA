"""Run the prespecified FIRMS spatiotemporal sensitivity experiment.

The command consumes an already processed local FIRMS CSV.  It never calls a
remote service and never writes to the raw or input processed file.  All
generated artifacts are diagnostic outputs under ``outputs/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from fuegopa.clustering import (
    DEFAULT_CONFIGURATIONS,
    EVENT_COLUMNS,
    MEMBERSHIP_COLUMNS,
    PERIOD_END,
    PERIOD_START,
    PROJECTION,
    PROJECTION_DESCRIPTION,
    SUMMARY_COLUMNS,
    ClusterResult,
    ClusteringValidationError,
    build_stability_rows,
    cluster_detections,
    csv_value,
    format_markdown_value,
    load_detections_csv,
    summary_metrics,
    write_csv,
    write_json,
)
from fuegopa.geo import Boundary, BoundaryError, load_boundary


STABILITY_COLUMNS = (
    "configuration_id_a",
    "configuration_id_b",
    "axis",
    "event_count_a",
    "event_count_b",
    "event_count_change",
    "singleton_rate_pct_a",
    "singleton_rate_pct_b",
    "largest_event_count_a",
    "largest_event_count_b",
    "pair_retention_rate",
    "jaccard_coassignment",
)

EXTREME_COLUMNS = (
    "configuration_id",
    "event_id",
    "criterion",
    "rank",
    "criterion_value",
    "detection_count",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "duration_hours",
    "max_pairwise_distance_m",
    "max_consecutive_gap_hours",
    "possible_chain_merge",
    "chain_merge_reasons",
    "notes",
)


def _resolve_path(root: Path, value: str | None, default: Path) -> Path:
    if not value:
        return default
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else root / candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta la sensibilidad de clustering FIRMS de Cocl\u00e9 2025 "
            "sin red y sin crear etiquetas de quema."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=os.environ.get("FUEGOPA_CLUSTERING_INPUT"),
        help="CSV local de detecciones FIRMS ya procesado.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=os.environ.get("FUEGOPA_CLUSTERING_OUTPUT_DIR"),
        help="Directorio de artefactos de sensibilidad.",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=os.environ.get("FUEGOPA_CLUSTERING_FIGURES_DIR"),
        help="Directorio de figuras PNG; use --no-figures para omitirlas.",
    )
    parser.add_argument(
        "--boundary",
        type=Path,
        default=os.environ.get("FUEGOPA_CLUSTERING_BOUNDARY"),
        help="GeoJSON local opcional de Cocl\u00e9; no se infiere ni descarga.",
    )
    parser.add_argument(
        "--boundary-crs",
        default=os.environ.get("FUEGOPA_CLUSTERING_BOUNDARY_CRS"),
        help="CRS expl\u00edcito solo si el GeoJSON local lo requiere y fue verificado.",
    )
    parser.add_argument("--project-root", type=Path, default=os.environ.get("FUEGOPA_PROJECT_ROOT"))
    parser.add_argument("--no-figures", action="store_true", help="No generar PNG de diagn\u00f3stico.")
    return parser


def _options(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path | None]:
    root = Path(args.project_root or Path.cwd()).expanduser().resolve()
    input_path = _resolve_path(
        root,
        str(args.input) if args.input else None,
        root / "data" / "processed" / "firms_cocle_2025_detections.csv",
    )
    output_dir = _resolve_path(
        root,
        str(args.output_dir) if args.output_dir else None,
        root / "outputs" / "clustering",
    )
    figures_dir = _resolve_path(
        root,
        str(args.figures_dir) if args.figures_dir else None,
        root / "outputs" / "figures" / "clustering",
    )
    boundary = (
        _resolve_path(root, str(args.boundary), root / "data" / "reference" / "cocle.geojson")
        if args.boundary
        else None
    )
    return root, input_path, output_dir, figures_dir, boundary


def _input_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_period(detections: Iterable[Any]) -> None:
    for detection in detections:
        if not PERIOD_START <= detection.timestamp.date() <= PERIOD_END:
            raise ClusteringValidationError(
                "El input contiene timestamps fuera del periodo aprobado "
                f"{PERIOD_START.isoformat()}..{PERIOD_END.isoformat()}: "
                f"{detection.detection_id} ({detection.timestamp_utc})"
            )


def _write_event_outputs(output_dir: Path, results: Mapping[str, ClusterResult]) -> None:
    for configuration_id, result in results.items():
        configuration_dir = output_dir / configuration_id
        write_csv(configuration_dir / "events.csv", EVENT_COLUMNS, result.events)
        write_csv(configuration_dir / "membership.csv", MEMBERSHIP_COLUMNS, result.membership)
        write_json(
            configuration_dir / "summary.json",
            {
                "configuration": {
                    "configuration_id": result.configuration.configuration_id,
                    "radius_m": result.configuration.radius_m,
                    "time_window_hours": result.configuration.time_window_hours,
                },
                "metrics": summary_metrics(result),
                "method": {
                    "graph": "connected components; edge iff distance <= radius and UTC gap <= time window",
                    "thresholds_inclusive": True,
                    "projection": PROJECTION,
                    "projection_description": PROJECTION_DESCRIPTION,
                    "edge_fields": ["latitude", "longitude", "acq_datetime_utc"],
                    "descriptive_only_fields": [
                        "firms_source",
                        "satellite",
                        "instrument",
                        "frp",
                        "confidence_raw",
                        "daynight",
                    ],
                    "no_confirmed_fire_label": True,
                },
            },
        )


def _summary_markdown(
    input_path: Path,
    input_sha256: str,
    detections: Iterable[Any],
    summary_rows: list[dict[str, Any]],
    boundary: Boundary | None,
) -> str:
    rows = list(detections)
    sources = sorted(
        {
            str(detection.row.get("firms_source", "")).strip()
            for detection in rows
            if str(detection.row.get("firms_source", "")).strip()
        }
    )
    lines = [
        "# Sensibilidad de clustering FIRMS — Cocl\u00e9 2025",
        "",
        "> PROVISIONAL ALGORITHMIC CLUSTERS - NOT CONFIRMED FIRES",
        "> FIRMS OBSERVATIONS ARE THERMAL ANOMALIES - NOT INDEPENDENT FIRES",
        "",
        "Este reporte compara una grilla prespecificada de radios y ventanas temporales. No fija todavía una unidad final de evento ni genera etiquetas de quema.",
        "",
        "## Input y método",
        "",
        f"- Input local: `{input_path}`.",
        f"- SHA-256 del input: `{input_sha256}`.",
        f"- Filas validadas: `{len(rows)}`; fuentes: `{', '.join(sources) or 'no especificadas'}`.",
        f"- Periodo exigido: `{PERIOD_START.isoformat()}..{PERIOD_END.isoformat()}`; timestamps interpretados en UTC.",
        f"- Proyección espacial: `{PROJECTION}` ({PROJECTION_DESCRIPTION}).",
        "- Arista: distancia espacial inclusiva y diferencia temporal UTC inclusiva; los componentes conexos conservan singletons.",
        "- FRP, confianza, fuente, satélite, instrumento y día/noche son descriptivos; no crean aristas.",
        f"- Frontera local: `{boundary.source_path}`." if boundary else "- Frontera local: no proporcionada; los mapas se dibujan sobre el extent de las detecciones.",
        "",
        "## Resumen de las 16 configuraciones",
        "",
        "| Configuración | Radio m | Ventana h | Eventos | Singletons % | Mediana tamaño | P95 duración h | Mediana extent m | Chain-merge posibles | Mayor share % | Mega cluster |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            "| {configuration_id} | {radius_m} | {time_window_hours} | {event_count} | {singleton_rate_pct} | {median_detection_count} | {p95_duration_hours} | {median_spatial_extent_m} | {events_possible_chain_merge} | {largest_event_detection_share_pct} | {mega_cluster_detected} |".format(
                **{key: format_markdown_value(row.get(key)) for key in SUMMARY_COLUMNS}
            )
        )
    lines.extend(
        [
            "",
            "`singleton_rate_pct`, las duraciones, extensiones y los diagnósticos describen la sensibilidad del algoritmo. No son métricas de precisión de incendios porque todavía no existe una etiqueta observada Sentinel-2/dNBR en esta fase.",
            "",
            "## Lectura y límites",
            "",
            "- Un componente puede encadenar observaciones que no son simultáneas ni contiguas; `possible_chain_merge` identifica casos para revisión, pero no divide el grafo de forma automática.",
            "- La estabilidad se calcula en `stability.csv` usando pares de detecciones coasignados entre configuraciones vecinas; no se selecciona el número de eventos objetivo.",
            "- El experimento no usa Sentinel-2, dNBR, variables ambientales, modelos predictivos, red ni datos de 2026.",
            "- La ausencia de frontera local no cambia la pertenencia del input: este script no vuelve a filtrar ni reescribe la cohorte.",
            "",
        ]
    )
    return "\n".join(lines)


def _stability_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Estabilidad entre configuraciones",
        "",
        "> Comparación descriptiva de clusters provisionales; no es validación contra incendios observados.",
        "",
        "Se comparan solo vecinos de la grilla: una ventana temporal adyacente con el mismo radio, o un radio adyacente con la misma ventana. `pair_retention_rate` es direccional (A → B) y `jaccard_coassignment` es simétrico sobre pares de detecciones coasignados.",
        "",
        "| A | B | Eje | Eventos A | Eventos B | Cambio | Singleton A % | Singleton B % | Mayor A | Mayor B | Retención A→B | Jaccard |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {configuration_id_a} | {configuration_id_b} | {axis} | {event_count_a} | {event_count_b} | {event_count_change} | {singleton_rate_pct_a} | {singleton_rate_pct_b} | {largest_event_count_a} | {largest_event_count_b} | {pair_retention_rate} | {jaccard_coassignment} |".format(
                **{key: format_markdown_value(row.get(key)) for key in STABILITY_COLUMNS}
            )
        )
    lines.extend(
        [
            "",
            "Una retención o similitud alta solo indica que el particionado cambia menos entre esos dos parámetros. No demuestra que los grupos sean incendios independientes ni que una configuración sea correcta para una etiqueta futura.",
            "",
        ]
    )
    return "\n".join(lines)


def _extreme_rows(results: Mapping[str, ClusterResult]) -> list[dict[str, Any]]:
    criteria = (
        ("detection_count", "detection_count", True),
        ("duration_hours", "duration_hours", True),
        ("spatial_extent_m", "max_pairwise_distance_m", True),
        ("frp_sum", "frp_sum", True),
        ("max_temporal_gap_hours", "max_consecutive_gap_hours", True),
        ("possible_chain_merge", "possible_chain_merge", True),
    )
    output: list[dict[str, Any]] = []
    for configuration_id in sorted(results):
        result = results[configuration_id]
        for criterion, field, descending in criteria:
            eligible = [
                event
                for event in result.events
                if event.get(field) is not None
                and (criterion != "possible_chain_merge" or bool(event.get(field)))
            ]
            eligible.sort(
                key=lambda event: (
                    -(float(event.get(field) or 0)) if descending and field != "possible_chain_merge" else 0,
                    str(event.get("event_id", "")),
                )
            )
            for rank, event in enumerate(eligible[:5], start=1):
                value = event.get(field)
                note = {
                    "detection_count": "revisar tamaño del componente",
                    "duration_hours": "revisar duración temporal",
                    "spatial_extent_m": "revisar extensión espacial",
                    "frp_sum": "FRP agregado descriptivo, no etiqueta de severidad",
                    "max_temporal_gap_hours": "revisar salto entre detecciones consecutivas",
                    "possible_chain_merge": "revisar razones diagnósticas sin dividir automáticamente",
                }[criterion]
                output.append(
                    {
                        "configuration_id": configuration_id,
                        "event_id": event["event_id"],
                        "criterion": criterion,
                        "rank": rank,
                        "criterion_value": value,
                        "detection_count": event["detection_count"],
                        "start_timestamp_utc": event["start_timestamp_utc"],
                        "end_timestamp_utc": event["end_timestamp_utc"],
                        "duration_hours": event["duration_hours"],
                        "max_pairwise_distance_m": event["max_pairwise_distance_m"],
                        "max_consecutive_gap_hours": event["max_consecutive_gap_hours"],
                        "possible_chain_merge": event["possible_chain_merge"],
                        "chain_merge_reasons": event["chain_merge_reasons"],
                        "notes": note,
                    }
                )
    return output


def _write_extreme_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Revisión de eventos extremos",
        "",
        "> Lista algorítmica para control de calidad; no confirma incendios ni define etiquetas.",
        "",
        "Se conservan hasta cinco eventos por criterio y configuración. Los criterios son tamaño, duración, extensión, FRP agregado descriptivo, salto temporal máximo y la bandera de posible encadenamiento.",
        "",
        "| Configuración | Evento | Criterio | Rank | Valor | N | Inicio | Fin | Duración h | Extent m | Gap h | Chain merge | Razones |",
        "|---|---|---|---:|---:|---:|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {configuration_id} | {event_id} | {criterion} | {rank} | {criterion_value} | {detection_count} | {start_timestamp_utc} | {end_timestamp_utc} | {duration_hours} | {max_pairwise_distance_m} | {max_consecutive_gap_hours} | {possible_chain_merge} | {chain_merge_reasons} |".format(
                **{key: format_markdown_value(row.get(key)) for key in EXTREME_COLUMNS}
            )
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _provisional_candidates(
    results: Mapping[str, ClusterResult], stability_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    stability_by_config: dict[str, list[float]] = defaultdict(list)
    for row in stability_rows:
        value = row.get("jaccard_coassignment")
        if value is None:
            continue
        stability_by_config[str(row["configuration_id_a"])].append(float(value))
        stability_by_config[str(row["configuration_id_b"])].append(float(value))
    candidates: list[dict[str, Any]] = []
    for configuration_id, result in results.items():
        metrics = summary_metrics(result)
        chain_rate = (
            metrics["events_possible_chain_merge"] / metrics["event_count"]
            if metrics["event_count"]
            else 0.0
        )
        values = stability_by_config.get(configuration_id, [])
        candidates.append(
            {
                "configuration_id": configuration_id,
                "mean_neighbor_jaccard": sum(values) / len(values) if values else None,
                "mega_cluster_detected": metrics["mega_cluster_detected"],
                "possible_chain_merge_rate": chain_rate,
                "events_possible_chain_merge": metrics["events_possible_chain_merge"],
                "event_count": metrics["event_count"],
                "singleton_rate_pct": metrics["singleton_rate_pct"],
            }
        )
    candidates.sort(
        key=lambda row: (
            bool(row["mega_cluster_detected"]),
            -(row["mean_neighbor_jaccard"] if row["mean_neighbor_jaccard"] is not None else -1.0),
            row["possible_chain_merge_rate"],
            str(row["configuration_id"]),
        )
    )
    return candidates[:3]


def _write_provisional_markdown(
    path: Path, candidates: list[dict[str, Any]], boundary: Boundary | None
) -> None:
    lines = [
        "# Selección provisional de parámetros",
        "",
        "> No se adopta una configuración final ni se escribe una tabla final de eventos en `data/processed/`.",
        "",
        "Esta salida reporta hasta tres candidatos para revisión humana. El orden usa únicamente la similitud media con configuraciones vecinas, penaliza la presencia de un mega-cluster y después muestra la tasa de diagnósticos de posible encadenamiento. Es un filtro de revisión, no una decisión científica ni una optimización contra una etiqueta.",
        "",
        "| Candidato | Jaccard medio vecinos | Mega cluster | Chain merge posibles / eventos | Eventos | Singletons % |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in candidates:
        lines.append(
            "| {configuration_id} | {mean_neighbor_jaccard} | {mega_cluster_detected} | {possible_chain_merge_rate} | {event_count} | {singleton_rate_pct} |".format(
                **{key: format_markdown_value(row.get(key)) for key in row}
            )
        )
    lines.extend(
        [
            "",
            "Conclusión de esta fase: los candidatos quedan abiertos. Hace falta revisar los eventos extremos, discutir la semántica de evento con el equipo y, posteriormente, contrastar una cohorte etiquetada con Sentinel-2/dNBR antes de fijar parámetros o entrenar un modelo.",
            "",
            "La frontera usada para figuras fue "
            + (f"`{boundary.source_path}`." if boundary else "no proporcionada; no se inventó una geometría."),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _run(args: argparse.Namespace) -> int:
    root, input_path, output_dir, figures_dir, boundary_path = _options(args)
    if not input_path.exists():
        raise ClusteringValidationError(f"No existe el input local: {input_path}")
    detections = load_detections_csv(input_path)
    _check_period(detections)
    input_sha256 = _input_sha256(input_path)
    boundary = None
    if boundary_path:
        try:
            boundary = load_boundary(boundary_path, feature_name="Cocl\u00e9", assume_crs=args.boundary_crs)
        except BoundaryError as exc:
            raise ClusteringValidationError(str(exc)) from exc

    results: dict[str, ClusterResult] = {}
    for configuration in DEFAULT_CONFIGURATIONS:
        result = cluster_detections(detections, configuration)
        results[configuration.configuration_id] = result

    summary_rows = [summary_metrics(results[configuration.configuration_id]) for configuration in DEFAULT_CONFIGURATIONS]
    stability_rows = build_stability_rows(results)
    extreme_rows = _extreme_rows(results)
    candidates = _provisional_candidates(results, stability_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_event_outputs(output_dir, results)
    write_csv(output_dir / "sensitivity_summary.csv", SUMMARY_COLUMNS, summary_rows)
    write_csv(output_dir / "stability.csv", STABILITY_COLUMNS, stability_rows)
    write_csv(output_dir / "extreme_events_review.csv", EXTREME_COLUMNS, extreme_rows)
    (output_dir / "sensitivity_summary.md").write_text(
        _summary_markdown(input_path, input_sha256, detections, summary_rows, boundary),
        encoding="utf-8",
    )
    (output_dir / "stability.md").write_text(_stability_markdown(stability_rows), encoding="utf-8")
    _write_extreme_markdown(output_dir / "extreme_events_review.md", extreme_rows)
    _write_provisional_markdown(output_dir / "provisional_selection.md", candidates, boundary)
    write_json(
        output_dir / "sensitivity_summary.json",
        {
            "input": {
                "path": str(input_path),
                "sha256": input_sha256,
                "row_count": len(detections),
                "period_start": PERIOD_START.isoformat(),
                "period_end": PERIOD_END.isoformat(),
                "sources": sorted(
                    {
                        str(detection.row.get("firms_source", "")).strip()
                        for detection in detections
                        if str(detection.row.get("firms_source", "")).strip()
                    }
                ),
                "first_timestamp_utc": min(detection.timestamp_utc for detection in detections),
                "last_timestamp_utc": max(detection.timestamp_utc for detection in detections),
            },
            "method": {
                "algorithm": "connected components on a spatiotemporal threshold graph",
                "thresholds_inclusive": True,
                "projection": PROJECTION,
                "projection_description": PROJECTION_DESCRIPTION,
                "configurations": [
                    {
                        "configuration_id": configuration.configuration_id,
                        "radius_m": configuration.radius_m,
                        "time_window_hours": configuration.time_window_hours,
                    }
                    for configuration in DEFAULT_CONFIGURATIONS
                ],
                "edge_fields": ["latitude", "longitude", "acq_datetime_utc"],
                "descriptive_only_fields": [
                    "firms_source",
                    "satellite",
                    "instrument",
                    "frp",
                    "confidence_raw",
                    "daynight",
                ],
                "diagnostics_do_not_split_events": True,
                "no_network": True,
                "no_sentinel2_or_dnbr": True,
                "no_predictive_model": True,
            },
            "boundary": str(boundary.source_path) if boundary else None,
            "outputs": {
                "per_configuration": "<configuration_id>/events.csv and membership.csv",
                "summary_csv": "sensitivity_summary.csv",
                "stability_csv": "stability.csv",
                "extreme_review_csv": "extreme_events_review.csv",
                "provisional_selection": "provisional_selection.md",
            },
        },
    )

    if not args.no_figures:
        from fuegopa.clustering_figures import write_clustering_figures

        write_clustering_figures(
            figures_dir=figures_dir,
            results=results,
            summary_rows=summary_rows,
            stability_rows=stability_rows,
            detections=detections,
            boundary=boundary,
        )

    print(f"input: {input_path}")
    print(f"rows: {len(detections)}")
    print(f"configurations: {len(results)}")
    print(f"summary: {output_dir / 'sensitivity_summary.csv'}")
    print(f"stability: {output_dir / 'stability.csv'}")
    print(f"figures: {'omitted' if args.no_figures else figures_dir}")
    print(f"project_root: {root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (ClusteringValidationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
