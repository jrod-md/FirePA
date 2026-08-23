"""Extract and validate the official IGN/ANATI province polygon for Cocle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.boundary import (  # noqa: E402
    BoundarySourceError,
    area_centroid,
    build_geojson,
    group_rings,
    normalize_admin_name,
    read_shapefile,
    record_geometry,
    record_polygons,
    select_records,
    sha256_file,
    source_metadata,
    transform_ring,
    transformed_bbox,
    write_geojson,
)
from fuegopa.boundary_figure import write_validation_figure  # noqa: E402
from fuegopa.geo import BoundaryError, load_boundary  # noqa: E402


PROVIDER = "Instituto Geográfico Nacional Tommy Guardia / ANATI"
DEFAULT_SOURCE = Path("data/reference/source/ign_anati_dpa_2025/limi_prov_a.shp")
DEFAULT_OUTPUT = Path("data/reference/cocle.geojson")
DEFAULT_REPORT_JSON = Path("outputs/cocle_boundary_validation.json")
DEFAULT_REPORT_MD = Path("outputs/cocle_boundary_validation.md")
DEFAULT_FIGURE = Path("outputs/figures/cocle_boundary_validation.png")


def _rooted(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _first_inside(boundary) -> tuple[float, float]:
    west, south, east, north = boundary.bbox
    centroid_candidate = (
        sum(point[0] for outer, _ in boundary.polygons for point in outer[:-1])
        / sum(len(outer) - 1 for outer, _ in boundary.polygons),
        sum(point[1] for outer, _ in boundary.polygons for point in outer[:-1])
        / sum(len(outer) - 1 for outer, _ in boundary.polygons),
    )
    candidates = [centroid_candidate]
    for row in range(1, 20):
        for column in range(1, 20):
            candidates.append(
                (
                    west + (east - west) * column / 20,
                    south + (north - south) * row / 20,
                )
            )
    for candidate in candidates:
        if boundary.contains(*candidate):
            return candidate
    raise BoundarySourceError("No se pudo encontrar un punto interior determinista para el smoke test.")


def _smoke_points(boundary) -> dict[str, Any]:
    inside = _first_inside(boundary)
    west, south, east, north = boundary.bbox
    margin = max((east - west) * 0.1, 0.01)
    outside = (east + margin, north + margin)
    edge = boundary.polygons[0][0][0]
    checks = {
        "inside": {"longitude": inside[0], "latitude": inside[1], "contains": boundary.contains(*inside)},
        "outside_bbox": {"longitude": outside[0], "latitude": outside[1], "contains": boundary.contains(*outside)},
        "edge": {"longitude": edge[0], "latitude": edge[1], "contains": boundary.contains(*edge)},
    }
    checks["passed"] = (
        checks["inside"]["contains"] is True
        and checks["outside_bbox"]["contains"] is False
        and checks["edge"]["contains"] is True
    )
    return checks


def _sidecar_report(layer, root: Path) -> dict[str, Any]:
    files = {
        "shp": layer.shp_path,
        "dbf": layer.dbf_path,
        "shx": layer.shx_path,
        "prj": layer.prj_path,
        "cpg": layer.cpg_path,
    }
    if layer.metadata_path is not None:
        files["shp_xml"] = layer.metadata_path
    return {
        kind: {
            "path": _display_path(path, root),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for kind, path in files.items()
    }


def _write_markdown(report: dict[str, Any], path: Path, report_json_path: Path) -> None:
    source = report["source"]
    output = report["output"]
    validation = report["validation"]
    selected = source["selected_entities"]
    lines = [
        "# Validación del límite oficial de Coclé",
        "",
        f"Fecha de ejecución: `{report['run_date']}`.",
        "",
        "## Fuente y selección",
        "",
        f"- Proveedor: {source['provider']}",
        f"- Dataset: {source['metadata'].get('title') or 'título no disponible en el XML'}",
        f"- Capa: `{source['layer']}`; registros en la capa: {source['total_records']}",
        f"- Campo de selección: `{source['name_field']}`; valor exacto: `{source['target_value']}`",
        f"- Entidades administrativas seleccionadas: {len(selected)}",
        f"- Registros SHP seleccionados: {len(selected)} (índices de registro en la capa: {', '.join(str(item['record_index']) for item in selected)})",
        f"- SHP: `{source['files']['shp']['path']}`",
        f"- CRS original: `{source['original_crs']}`; encoding: `{source['encoding']}`",
        f"- Geometría original: `{source['geometry_type']}`; partes seleccionadas: {source['selected_parts']}",
        "",
        "## Validación y transformación",
        "",
        f"- Geometría original válida: `{validation['original_geometry_valid']}`",
        f"- Geometría final válida: `{validation['final_geometry_valid']}`",
        f"- Reparaciones aplicadas: `{validation['repairs']}`",
        f"- CRS final: `{output['crs']}`; tipo final: `{output['geometry_type']}`",
        f"- Bbox final: `{output['bbox']}`",
        f"- Área descriptiva aproximada en {source['original_crs']}: `{validation['area_m2_approx']} m²`",
        f"- Centroide descriptivo en EPSG:4326: `{validation['centroid_epsg4326']}`",
        f"- Smoke test punto-en-polígono: `{validation['point_in_polygon_smoke']['passed']}`",
        "",
        "## Trazabilidad y restricciones",
        "",
        f"- GeoJSON generado: `{output['path']}`; SHA-256: `{output['sha256']}`",
        f"- Restricción declarada por el XML: `{source['metadata'].get('license')}`",
        "- El archivo generado queda fuera del commit por la política de datos de referencia y la licencia declarada; se regenera con el script.",
        "- El XML declara que la información es de referencia y de representación cartográfica; este límite solo se usa para filtrar espacialmente FIRMS.",
        "- No se simplificaron, disolvieron ni corrigieron anillos; un error geométrico habría detenido la extracción.",
        "",
        "## Artefactos",
        "",
        f"- Reporte JSON: `{_display_path(report_json_path, Path(report['project_root']))}`",
        f"- Figura: `{report['figure_path']}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-shp", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--name-field", default="nomb_prov")
    parser.add_argument("--target-name", default="Coclé")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.project_root.expanduser().resolve()
    source_path = _rooted(root, args.source_shp).resolve()
    output_path = _rooted(root, args.output).resolve()
    report_json_path = _rooted(root, args.report_json).resolve()
    report_md_path = _rooted(root, args.report_md).resolve()
    figure_path = _rooted(root, args.figure).resolve()

    layer = read_shapefile(source_path)
    name_field = next(field for field in layer.fields if field.casefold() == args.name_field.casefold())
    selected = select_records(layer, name_field=name_field, target_name=args.target_name)
    selected_polygons_source = tuple(
        polygon for record in selected for polygon in group_rings(record.parts)
    )
    area_m2, centroid_source = area_centroid(selected_polygons_source)
    centroid_epsg4326 = transform_ring((centroid_source,), layer.source_crs)[0]

    document = build_geojson(layer, selected, name_field)
    temporary_output = output_path.with_name(output_path.name + ".tmp")
    write_geojson(document, temporary_output)
    target_value = selected[0].attributes[name_field]
    try:
        final_boundary = load_boundary(temporary_output, feature_name=target_value)
    except (BoundaryError, OSError) as exc:
        raise BoundarySourceError(f"El GeoJSON generado no pasó la validación final: {exc}") from exc
    temporary_output.replace(output_path)

    smoke = _smoke_points(final_boundary)
    write_validation_figure(layer, selected, figure_path)
    metadata = source_metadata(layer.metadata_path)
    output_hash = sha256_file(output_path)
    selected_entities = [
        {
            "record_index": record.index,
            "name": record.attributes.get(name_field, ""),
            "parts": len(record.parts),
            "points": sum(len(ring) for ring in record.parts),
            "geometry_type": record_geometry(record, layer.source_crs)["type"],
        }
        for record in selected
    ]
    final_geometry_type = document["features"][0]["geometry"]["type"] if len(document["features"]) == 1 else "FeatureCollection"
    report = {
        "project_root": str(root),
        "run_date": date.today().isoformat(),
        "source": {
            "provider": PROVIDER,
            "layer": source_path.stem,
            "metadata": metadata,
            "files": _sidecar_report(layer, root),
            "original_crs": layer.source_crs,
            "prj_name": "WGS_1984_UTM_Zone_17N",
            "encoding": layer.encoding,
            "geometry_type": layer.shape_type_name,
            "total_records": len(layer.records),
            "active_records": len(layer.active_records),
            "name_field": name_field,
            "target_value": target_value,
            "target_normalized": normalize_admin_name(target_value),
            "selected_entities": selected_entities,
            "selected_parts": sum(len(record.parts) for record in selected),
            "selected_points": sum(sum(len(ring) for ring in record.parts) for record in selected),
            "source_bbox": list(layer.file_bbox),
        },
        "validation": {
            "original_geometry_valid": True,
            "final_geometry_valid": True,
            "repairs": [],
            "area_m2_approx": round(area_m2, 3),
            "area_crs": layer.source_crs,
            "centroid_original_crs": [round(centroid_source[0], 3), round(centroid_source[1], 3)],
            "centroid_epsg4326": [round(centroid_epsg4324326, 8) for centroid_epsg4324326 in centroid_epsg4326],
            "point_in_polygon_smoke": smoke,
            "final_polygon_count": len(final_boundary.polygons),
            "final_bbox": list(final_boundary.bbox),
        },
        "output": {
            "path": _display_path(output_path, root),
            "bytes": output_path.stat().st_size,
            "sha256": output_hash,
            "crs": "EPSG:4326",
            "geometry_type": final_geometry_type,
            "feature_count": len(document["features"]),
            "bbox": list(final_boundary.bbox),
        },
        "figure_path": _display_path(figure_path, root),
        "limitations": [
            "El límite se utiliza únicamente para el filtro espacial de FIRMS; no define eventos ni etiquetas de quema.",
            "El área y centroide son descriptivos y se calculan en el CRS proyectado original.",
            "La cobertura de la capa incluye registros de provincia y comarca según el metadata; el filtro exacto seleccionó solo el valor documentado de Coclé.",
        ],
    }
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(report, report_md_path, report_json_path)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run(args)
    except (BoundarySourceError, OSError, StopIteration) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "output": report["output"],
        "report_json": report["validation"],
        "figure": report["figure_path"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
