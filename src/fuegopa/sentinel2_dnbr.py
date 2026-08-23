"""Reproducible NBR/dNBR pilot for the frozen Sentinel-2 policy.

This module operates only on the 28 events with a usable pair in the frozen
policy selection. It does not alter Sentinel-2 inventories, create burn
labels, classify severity, or train a model.
"""

from __future__ import annotations

import csv
import html
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .earth_engine import (
    CLOUD_SCORE_PLUS_COLLECTION,
    SENTINEL2_SR_COLLECTION,
    EarthEngineClient,
    EarthEngineQueryError,
)
from .dnbr_quicklook import (
    DNBR_VIS_MAX,
    DNBR_VIS_MIN,
    NBR_VIS_MAX,
    NBR_VIS_MIN,
    PANEL_HEIGHT,
    PANEL_THUMB_DIMENSION,
    PANEL_WIDTH,
    QuicklookValidationError,
    VISUALIZATION_PALETTE,
    compose_panel_png,
    panel_filename,
    quicklook_path_for_mode,
    validate_thumbnail_sources,
)
from .provisional import FROZEN_CONFIGURATION_ID, read_csv_rows
from .sentinel2_observability import (
    AOI_METHOD,
    CALCULATION_CRS,
    EventInput,
    build_aoi,
    load_pilot_events,
    normalize_inventory_rows,
    parse_utc_timestamp,
    scene_is_usable,
)


DNBR_PIPELINE_VERSION = "fuegopa-sentinel2-dnbr-v3"
ANALYSIS_SCALE_M = 20
AOI_BUFFER_M = 500
AOI_ID = "b0500"
PRIMARY_CLOUD_THRESHOLD = 0.50
CLOUD_THRESHOLDS = (0.50, 0.60, 0.65)
DNBR_THRESHOLDS = (0.10, 0.20, 0.30, 0.40)
OVERLAP_FLOAT_TOLERANCE = 1e-9
DEFAULT_MIN_VALID_OVERLAP_FRACTION = 0.50
EXPECTED_PILOT_EVENT_COUNT = 30
EXPECTED_PROCESSABLE_EVENT_COUNT = 28
EXPECTED_EXCLUDED_EVENT_COUNT = 2
PRIMARY_COMBINATIONS = {"b0500_pre30_post45", "b0500_pre30_post90"}
ANALYSIS_MODES = ("selected_pair", "window_median")
OPTICAL_EXCLUSION_STATUS = "optically_unobservable_under_current_policy"

NBR_FORMULA = "(B8 - B12) / (B8 + B12)"
DNBR_FORMULA = "NBR_pre - NBR_post"

OVERLAP_SUPPORT_CONTRACT = {
    "geometry": "aoi.geometry_wgs84",
    "crs": CALCULATION_CRS,
    "scale_m": ANALYSIS_SCALE_M,
    "reducer": "sum",
    "support_band": "aoi_support",
    "common_support_band": "common_valid_support",
    "pixel_area_band": "pixel_area",
    "pixel_area_reducer": "sum",
    "common_mask": "pre_valid AND post_valid",
}

METRICS_COLUMNS = (
    "event_id",
    "configuration_id",
    "policy_path",
    "selected_combination_id",
    "pre_scene_id",
    "post_scene_id",
    "pre_timestamp_utc",
    "post_timestamp_utc",
    "analysis_mode",
    "cloud_threshold",
    "aoi_method",
    "aoi_id",
    "aoi_buffer_m",
    "aoi_area_m2",
    "vector_aoi_area_m2",
    "valid_overlap_area_m2",
    "valid_overlap_fraction_raw",
    "valid_overlap_fraction",
    "overlap_fraction_tolerance",
    "overlap_fraction_was_clipped",
    "common_valid_pixel_count",
    "valid_pixel_count",
    "pre_valid_pixel_count",
    "post_valid_pixel_count",
    "aoi_pixel_count",
    "rasterized_aoi_area_m2",
    "valid_aoi_area_m2",
    "pre_nbr_mean",
    "pre_nbr_median",
    "post_nbr_mean",
    "post_nbr_median",
    "dnbr_mean",
    "dnbr_median",
    "dnbr_p10",
    "dnbr_p25",
    "dnbr_p75",
    "dnbr_p90",
    "dnbr_p95",
    "dnbr_min",
    "dnbr_max",
    "fraction_dnbr_gt_010",
    "fraction_dnbr_gt_020",
    "fraction_dnbr_gt_030",
    "fraction_dnbr_gt_040",
    "area_ha_dnbr_gt_010",
    "area_ha_dnbr_gt_020",
    "area_ha_dnbr_gt_030",
    "area_ha_dnbr_gt_040",
    "pre_scene_count_used",
    "post_scene_count_used",
    "pre_scene_ids_used",
    "post_scene_ids_used",
    "quicklook_path",
    "metric_status",
    "processing_timestamp_utc",
    "pipeline_version",
)

ERROR_COLUMNS = (
    "event_id",
    "configuration_id",
    "error_type",
    "error_message",
    "error_stage",
    "operation",
    "cause_type",
    "cause_message",
    "aoi_id",
    "window_id",
    "attempt",
    "retry_count",
    "max_retries",
    "traceback_file",
    "processing_timestamp_utc",
    "pipeline_version",
)

REVIEW_QUEUE_COLUMNS = (
    "event_id",
    "configuration_id",
    "policy_path",
    "selected_combination_id",
    "pre_scene_id",
    "post_scene_id",
    "pre_timestamp_utc",
    "post_timestamp_utc",
    "selected_pair_metric_status",
    "selected_pair_valid_overlap_fraction",
    "quicklook_path",
    "visible_burn_scar",
    "scar_confidence",
    "competing_land_change",
    "reviewer_notes",
    "review_status",
)

SENSITIVITY_COLUMNS = METRICS_COLUMNS


class DnbrValidationError(ValueError):
    """Raised when frozen policy inputs or dNBR results are unsafe."""


@dataclass(frozen=True)
class NormalizedAreaFraction:
    """Raw and operational values for an area-derived bounded fraction."""

    raw: float | None
    value: float | None
    tolerance: float
    was_clipped: bool


@dataclass(frozen=True)
class DnbrEventInput:
    """One processable event joined to its policy-selected scenes."""

    event: EventInput
    selection: Mapping[str, Any]
    aoi_area_m2: float
    pre_scene: Mapping[str, Any]
    post_scene: Mapping[str, Any]
    pre_candidates: tuple[Mapping[str, Any], ...]
    post_candidates: tuple[Mapping[str, Any], ...]

    @property
    def event_id(self) -> str:
        return self.event.event_id

    @property
    def selected_combination_id(self) -> str:
        return str(self.selection["selected_combination_id"])

    @property
    def policy_path(self) -> str:
        return "fallback" if _bool(self.selection.get("fallback_rescues")) else "principal"

    @property
    def pre_scene_id(self) -> str:
        return _scene_id(self.pre_scene)

    @property
    def post_scene_id(self) -> str:
        return _scene_id(self.post_scene)


@dataclass(frozen=True)
class DnbrInputs:
    events: tuple[EventInput, ...]
    processable: tuple[DnbrEventInput, ...]
    excluded: tuple[Mapping[str, Any], ...]
    scene_rows: tuple[Mapping[str, Any], ...]
    aoi_rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class AnalysisGraph:
    pre_source: Any
    post_source: Any
    pre_valid_mask: Any
    post_valid_mask: Any
    common_valid_mask: Any
    pre_nbr: Any
    post_nbr: Any
    dnbr: Any


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return _text(value).casefold() in {"true", "1", "yes", "si", "sí"}


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> int | None:
    parsed = _float(value)
    return int(parsed) if parsed is not None else None


def _scene_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("sentinel2_scene_id") or row.get("system_index"))


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _threshold_code(value: float) -> str:
    return f"{int(round(value * 100)):03d}"


def default_dnbr_paths(root: Path | str) -> dict[str, Path]:
    base = Path(root)
    return {
        "pilot": base / "data" / "processed" / "sentinel2_observability_pilot_events.csv",
        "membership": base / "data" / "processed" / "firms_cocle_2025_event_membership.csv",
        "events": base / "data" / "processed" / "firms_cocle_2025_events_provisional.csv",
        "selection": base / "outputs" / "sentinel2_event_pair_selection.csv",
        "scene_inventory": base / "data" / "interim" / "sentinel2_scene_inventory.csv",
        "aoi_inventory": base / "data" / "interim" / "sentinel2_aoi_inventory.csv",
        "metrics": base / "data" / "interim" / "sentinel2_dnbr_event_metrics.csv",
        "errors": base / "data" / "interim" / "sentinel2_dnbr_errors.csv",
        "checkpoint": base / "data" / "interim" / "sentinel2_dnbr_checkpoint.json",
        "report_json": base / "outputs" / "sentinel2_dnbr_report.json",
        "report_markdown": base / "outputs" / "sentinel2_dnbr_report.md",
        "sensitivity": base / "outputs" / "sentinel2_dnbr_sensitivity.csv",
        "review_queue": base / "outputs" / "sentinel2_dnbr_review_queue.csv",
        "cache": base / "data" / "interim" / "sentinel2_dnbr_cache",
        "figures": base / "outputs" / "figures" / "sentinel2_dnbr" / "events",
    }


def _required_columns(rows: Sequence[Mapping[str, Any]], required: Sequence[str], context: str) -> None:
    if not rows:
        raise DnbrValidationError(f"{context}: no contiene filas")
    missing = [column for column in required if column not in rows[0]]
    if missing:
        raise DnbrValidationError(f"{context}: faltan columnas {', '.join(missing)}")


def _validate_selection_metadata(selection_rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    required = (
        "event_id",
        "configuration_id",
        "policy_rule",
        "primary_combination_id",
        "primary_sufficient",
        "fallback_rescues",
        "selected_combination_id",
        "selected_pre_scene_id",
        "selected_post_scene_id",
        "pre_scene_acquisition_timestamp",
        "post_scene_acquisition_timestamp",
        "final_observability_status",
        "final_exclusion_reason",
    )
    _required_columns(selection_rows, required, "selección de parejas")
    if len(selection_rows) != EXPECTED_PILOT_EVENT_COUNT:
        raise DnbrValidationError(
            f"La selección debe contener {EXPECTED_PILOT_EVENT_COUNT} eventos; recibió {len(selection_rows)}"
        )
    event_ids = [_text(row.get("event_id")) for row in selection_rows]
    if any(not event_id for event_id in event_ids) or len(set(event_ids)) != len(event_ids):
        raise DnbrValidationError("La selección contiene event_id vacíos o duplicados")
    if any(_text(row.get("configuration_id")) != FROZEN_CONFIGURATION_ID for row in selection_rows):
        raise DnbrValidationError(f"La selección contiene una configuración diferente de {FROZEN_CONFIGURATION_ID}")
    processable = [dict(row) for row in selection_rows if _text(row.get("final_observability_status")) == "usable_pair"]
    excluded = [dict(row) for row in selection_rows if _text(row.get("final_observability_status")) != "usable_pair"]
    if len(processable) != EXPECTED_PROCESSABLE_EVENT_COUNT:
        raise DnbrValidationError(
            f"Se esperaban {EXPECTED_PROCESSABLE_EVENT_COUNT} eventos procesables; recibió {len(processable)}"
        )
    if len(excluded) != EXPECTED_EXCLUDED_EVENT_COUNT:
        raise DnbrValidationError(
            f"Se esperaban {EXPECTED_EXCLUDED_EVENT_COUNT} eventos excluidos; recibió {len(excluded)}"
        )
    for row in processable:
        if _text(row.get("policy_rule")) != "A":
            raise DnbrValidationError(f"La política óptica no usa regla A: {row['event_id']}")
        if _text(row.get("primary_combination_id")) != "b0500_pre30_post45":
            raise DnbrValidationError(f"Combinación principal incompatible: {row['event_id']}")
        selected_combo = _text(row.get("selected_combination_id"))
        if selected_combo not in PRIMARY_COMBINATIONS:
            raise DnbrValidationError(f"Combinación seleccionada incompatible: {row['event_id']}/{selected_combo}")
        if _bool(row.get("primary_sufficient")) and selected_combo != "b0500_pre30_post45":
            raise DnbrValidationError(f"Evento principal con combinación no principal: {row['event_id']}")
        if _bool(row.get("fallback_rescues")) and selected_combo != "b0500_pre30_post90":
            raise DnbrValidationError(f"Evento fallback con combinación no temporal: {row['event_id']}")
        if not _text(row.get("selected_pre_scene_id")) or not _text(row.get("selected_post_scene_id")):
            raise DnbrValidationError(f"Pareja seleccionada incompleta: {row['event_id']}")
    return processable, excluded


def _scene_index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        key = (_text(row.get("event_id")), _text(row.get("combination_id")), _text(row.get("period_role")).casefold())
        index.setdefault(key, []).append(row)
    return index


def _find_scene(
    rows: Sequence[Mapping[str, Any]],
    *,
    event_id: str,
    combination_id: str,
    period_role: str,
    scene_id: str,
) -> dict[str, Any]:
    matches = [
        dict(row)
        for row in rows
        if _text(row.get("event_id")) == event_id
        and _text(row.get("combination_id")) == combination_id
        and _text(row.get("period_role")).casefold() == period_role
        and _scene_id(row) == scene_id
    ]
    if not matches:
        raise DnbrValidationError(
            f"Escena seleccionada no existe en el inventario: {event_id}/{combination_id}/{period_role}/{scene_id}"
        )
    return matches[0]


def load_dnbr_inputs(
    *,
    pilot_path: Path | str,
    events_path: Path | str,
    membership_path: Path | str,
    selection_path: Path | str,
    scene_inventory_path: Path | str,
    aoi_inventory_path: Path | str,
) -> DnbrInputs:
    """Load and validate the frozen optical pilot without Earth Engine."""

    events = load_pilot_events(pilot_path, events_path, membership_path)
    if len(events) != EXPECTED_PILOT_EVENT_COUNT:
        raise DnbrValidationError(f"El piloto debe contener {EXPECTED_PILOT_EVENT_COUNT} eventos")
    processable_rows, excluded_rows = _validate_selection_metadata(read_csv_rows(selection_path))
    scene_rows_raw = read_csv_rows(scene_inventory_path)
    aoi_rows_raw = read_csv_rows(aoi_inventory_path)
    normalized_scenes, normalized_aois = normalize_inventory_rows(scene_rows_raw, aoi_rows_raw)
    event_ids = {event.event_id for event in events}
    if not {_text(row.get("event_id")) for row in normalized_scenes}.issubset(event_ids):
        raise DnbrValidationError("El inventario de escenas contiene eventos fuera del piloto")
    if not {_text(row.get("event_id")) for row in normalized_aois}.issubset(event_ids):
        raise DnbrValidationError("El inventario AOI contiene eventos fuera del piloto")
    aoi_lookup = {(_text(row.get("event_id")), _text(row.get("aoi_id"))): row for row in normalized_aois}
    scene_rows_by_event = _scene_index(normalized_scenes)
    event_by_id = {event.event_id: event for event in events}
    processable: list[DnbrEventInput] = []
    for selection in sorted(processable_rows, key=lambda row: _text(row.get("event_id"))):
        event_id = _text(selection["event_id"])
        event = event_by_id.get(event_id)
        if event is None:
            raise DnbrValidationError(f"Selección contiene evento fuera del piloto: {event_id}")
        combo = _text(selection["selected_combination_id"])
        pre_id = _text(selection["selected_pre_scene_id"])
        post_id = _text(selection["selected_post_scene_id"])
        pre_scene = _find_scene(normalized_scenes, event_id=event_id, combination_id=combo, period_role="pre", scene_id=pre_id)
        post_scene = _find_scene(normalized_scenes, event_id=event_id, combination_id=combo, period_role="post", scene_id=post_id)
        pre_time = parse_utc_timestamp(pre_scene.get("acquisition_timestamp_utc"), f"{event_id}.pre_scene")
        post_time = parse_utc_timestamp(post_scene.get("acquisition_timestamp_utc"), f"{event_id}.post_scene")
        if pre_time >= event.start_timestamp_utc:
            raise DnbrValidationError(f"Escena pre no es anterior al evento: {event_id}")
        if post_time <= event.end_timestamp_utc:
            raise DnbrValidationError(f"Escena post no es posterior al evento: {event_id}")
        if not scene_is_usable(pre_scene, "A") or not scene_is_usable(post_scene, "A"):
            raise DnbrValidationError(f"Pareja seleccionada debajo de regla A: {event_id}")
        aoi_row = aoi_lookup.get((event_id, AOI_ID))
        if aoi_row is None:
            raise DnbrValidationError(f"No existe AOI {AOI_ID} para {event_id}")
        aoi_area = _float(aoi_row.get("aoi_area_m2"))
        if aoi_area is None or aoi_area <= 0:
            raise DnbrValidationError(f"Área AOI inválida para {event_id}")
        pre_candidates = tuple(
            sorted(
                {
                    _scene_id(row): dict(row)
                    for row in scene_rows_by_event.get((event_id, combo, "pre"), [])
                    if _scene_id(row) and scene_is_usable(row, "A")
                }.values(),
                key=_scene_id,
            )
        )
        post_candidates = tuple(
            sorted(
                {
                    _scene_id(row): dict(row)
                    for row in scene_rows_by_event.get((event_id, combo, "post"), [])
                    if _scene_id(row) and scene_is_usable(row, "A")
                }.values(),
                key=_scene_id,
            )
        )
        if not pre_candidates or not post_candidates:
            raise DnbrValidationError(f"No hay escenas utilizables para window_median: {event_id}")
        processable.append(
            DnbrEventInput(
                event=event,
                selection=dict(selection),
                aoi_area_m2=aoi_area,
                pre_scene=pre_scene,
                post_scene=post_scene,
                pre_candidates=pre_candidates,
                post_candidates=post_candidates,
            )
        )
    return DnbrInputs(
        events=tuple(events),
        processable=tuple(processable),
        excluded=tuple(sorted(excluded_rows, key=lambda row: _text(row.get("event_id")))),
        scene_rows=tuple(normalized_scenes),
        aoi_rows=tuple(normalized_aois),
    )


def nbr_value(b8: float, b12: float) -> float:
    """Compute the declared NBR formula for unit tests and audit code."""

    denominator = b8 + b12
    if denominator == 0:
        raise DnbrValidationError("NBR indefinido: B8+B12 es cero")
    return (b8 - b12) / denominator


def dnbr_value(nbr_pre: float, nbr_post: float) -> float:
    """Compute the declared dNBR formula without assigning severity."""

    return nbr_pre - nbr_post


def overlap_fraction_tolerance(
    aoi_area_m2: float | None = None,
    analysis_scale_m: float = ANALYSIS_SCALE_M,
) -> float:
    """Return the minimal floating-point tolerance for the raster ratio.

    ``aoi_area_m2`` and ``analysis_scale_m`` remain accepted for compatibility
    with v2 callers, but neither is used to grant geometric tolerance. The
    numerator and denominator now share one explicit raster support.
    """

    del aoi_area_m2, analysis_scale_m
    return OVERLAP_FLOAT_TOLERANCE


def normalize_overlap_fraction(
    raw: float | None,
    *,
    aoi_area_m2: float,
    analysis_scale_m: float = ANALYSIS_SCALE_M,
) -> NormalizedAreaFraction:
    """Validate and, only within floating-point tolerance, normalize an AOI fraction.

    The raw value is retained for auditing. Values outside the tolerance are
    rejected instead of being clipped indiscriminately.
    """

    tolerance = overlap_fraction_tolerance(aoi_area_m2, analysis_scale_m)
    if raw is None:
        return NormalizedAreaFraction(None, None, tolerance, False)
    try:
        raw_value = float(raw)
    except (TypeError, ValueError) as exc:
        raise DnbrValidationError(f"Fracción de solapamiento inválida: {raw!r}") from exc
    if (
        not math.isfinite(raw_value)
        or raw_value < -tolerance
        or raw_value > 1 + tolerance
    ):
        raise DnbrValidationError(
            "Fracción de solapamiento inválida: "
            f"{raw_value} (tolerancia={tolerance}; "
            f"aoi_area_m2={aoi_area_m2}; analysis_scale_m={analysis_scale_m})"
        )
    normalized = min(1.0, max(0.0, raw_value))
    return NormalizedAreaFraction(
        raw=raw_value,
        value=normalized,
        tolerance=tolerance,
        was_clipped=normalized != raw_value,
    )


def validate_overlap_fraction(
    value: float | None,
    *,
    aoi_area_m2: float | None = None,
    analysis_scale_m: float = ANALYSIS_SCALE_M,
) -> float | None:
    """Validate an overlap fraction, preserving the legacy strict call form."""

    if aoi_area_m2 is None:
        if value is None:
            return None
        if not math.isfinite(value) or value < 0 or value > 1:
            raise DnbrValidationError(f"Fracción de solapamiento inválida: {value}")
        return value
    return normalize_overlap_fraction(
        value,
        aoi_area_m2=aoi_area_m2,
        analysis_scale_m=analysis_scale_m,
    ).value


def percentile_order_is_valid(row: Mapping[str, Any]) -> bool:
    values = [
        _float(row.get("dnbr_p10")),
        _float(row.get("dnbr_p25")),
        _float(row.get("dnbr_median")),
        _float(row.get("dnbr_p75")),
        _float(row.get("dnbr_p90")),
        _float(row.get("dnbr_p95")),
    ]
    return all(value is not None for value in values) and all(
        left <= right + 1e-9 for left, right in zip(values, values[1:])
    )


def cache_path(cache_dir: Path | str, event_id: str) -> Path:
    return Path(cache_dir) / f"{_safe_id(event_id)}.json"


def cache_signature(event_input: DnbrEventInput, min_valid_overlap_fraction: float) -> dict[str, Any]:
    return {
        "pipeline_version": DNBR_PIPELINE_VERSION,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "event_id": event_input.event_id,
        "selected_combination_id": event_input.selected_combination_id,
        "pre_scene_id": event_input.pre_scene_id,
        "post_scene_id": event_input.post_scene_id,
        "aoi_method": AOI_METHOD,
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "cloud_thresholds": list(CLOUD_THRESHOLDS),
        "analysis_modes": list(ANALYSIS_MODES),
        "dnbr_thresholds": list(DNBR_THRESHOLDS),
        "overlap_support_contract": dict(OVERLAP_SUPPORT_CONTRACT),
        "min_valid_overlap_fraction": min_valid_overlap_fraction,
        "sentinel2_collection": SENTINEL2_SR_COLLECTION,
        "cloud_score_plus_collection": CLOUD_SCORE_PLUS_COLLECTION,
        "nbr_formula": NBR_FORMULA,
        "dnbr_formula": DNBR_FORMULA,
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def write_event_cache(path: Path | str, signature: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"signature": _canonical(signature), "result": _canonical(dict(result))}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def load_event_cache(
    path: Path | str,
    signature: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any] | None:
    input_path = Path(path)
    if not input_path.is_file():
        return None
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if payload.get("signature") != _canonical(signature):
        return None
    result = payload.get("result")
    if not isinstance(result, Mapping):
        return None
    quicklook = _text(result.get("quicklook_path"))
    if quicklook:
        quicklook_path = Path(quicklook)
        if root is not None and not quicklook_path.is_absolute():
            quicklook_path = root / quicklook_path
        if not quicklook_path.is_file():
            return None
    return dict(result)


def _ee_linked_scene(client: EarthEngineClient, scene_id: str) -> Any:
    ee = client.ee_module
    image = ee.Image(scene_id)
    return image.linkCollection(
        client.image_collection(CLOUD_SCORE_PLUS_COLLECTION),
        linkedBands=["cs", "cs_cdf"],
        linkedProperties=["MODEL_VERSION", "NO_CONTEXT_FRACTION"],
        matchPropertyName="system:index",
    )


def _masked_reflectance(image: Any, threshold: float, ee: Any) -> tuple[Any, Any]:
    bands = image.select(["B8", "B12"])
    b8_b12_valid = bands.mask().reduce(ee.Reducer.min()).gt(0)
    cs_cdf = image.select("cs_cdf")
    cs_valid = cs_cdf.mask().And(cs_cdf.gte(threshold))
    valid = b8_b12_valid.And(cs_valid).rename("valid")
    return bands.updateMask(valid), valid.selfMask()


def _nbr_image(bands: Any, ee: Any) -> Any:
    b8 = bands.select("B8")
    b12 = bands.select("B12")
    denominator = b8.add(b12)
    return b8.subtract(b12).divide(denominator).updateMask(denominator.neq(0)).rename("nbr")


def _composite_from_candidates(
    client: EarthEngineClient,
    scene_ids: Sequence[str],
    threshold: float,
) -> tuple[Any, Any]:
    if not scene_ids:
        raise DnbrValidationError("window_median requiere al menos una escena por lado")
    ee = client.ee_module
    masked_images = []
    for scene_id in scene_ids:
        linked = _ee_linked_scene(client, scene_id)
        bands, _ = _masked_reflectance(linked, threshold, ee)
        masked_images.append(bands)
    composite = ee.ImageCollection.fromImages(masked_images).median()
    return composite, composite.mask().reduce(ee.Reducer.min()).rename("valid").selfMask()


def build_analysis_graph(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    *,
    analysis_mode: str,
    cloud_threshold: float,
) -> AnalysisGraph:
    """Build an EE graph; this function itself performs no network request."""

    if analysis_mode not in ANALYSIS_MODES:
        raise DnbrValidationError(f"Modo de análisis inválido: {analysis_mode}")
    if cloud_threshold not in CLOUD_THRESHOLDS:
        raise DnbrValidationError(f"Umbral Cloud Score+ inválido: {cloud_threshold}")
    ee = client.ee_module
    if analysis_mode == "selected_pair":
        pre_source = _ee_linked_scene(client, event_input.pre_scene_id)
        post_source = _ee_linked_scene(client, event_input.post_scene_id)
        pre_bands, pre_valid = _masked_reflectance(pre_source, cloud_threshold, ee)
        post_bands, post_valid = _masked_reflectance(post_source, cloud_threshold, ee)
    else:
        pre_source = None
        post_source = None
        pre_bands, pre_valid = _composite_from_candidates(
            client,
            [_scene_id(row) for row in event_input.pre_candidates],
            cloud_threshold,
        )
        post_bands, post_valid = _composite_from_candidates(
            client,
            [_scene_id(row) for row in event_input.post_candidates],
            cloud_threshold,
        )
    common_valid = pre_valid.And(post_valid).rename("common").selfMask()
    pre_nbr = _nbr_image(pre_bands, ee).updateMask(common_valid)
    post_nbr = _nbr_image(post_bands, ee).updateMask(common_valid)
    dnbr = pre_nbr.subtract(post_nbr).rename("dnbr").updateMask(common_valid)
    return AnalysisGraph(
        pre_source=pre_source,
        post_source=post_source,
        pre_valid_mask=pre_valid,
        post_valid_mask=post_valid,
        common_valid_mask=common_valid,
        pre_nbr=pre_nbr,
        post_nbr=post_nbr,
        dnbr=dnbr,
    )


def _reduce_region(image: Any, reducer: Any, aoi: Any) -> Any:
    return image.reduceRegion(
        reducer=reducer,
        geometry=aoi.geometry_wgs84,
        scale=ANALYSIS_SCALE_M,
        crs=CALCULATION_CRS,
        maxPixels=100000000,
        bestEffort=False,
        tileScale=4,
    )


def _sum(image: Any, band_name: str, aoi: Any, ee: Any) -> Any:
    reduced = _reduce_region(image, ee.Reducer.sum(), aoi)
    return ee.Number(ee.Dictionary(reduced).get(band_name, 0))


def _analysis_aoi_support(aoi: Any, ee: Any) -> Any:
    """Build the single 20 m raster support used by both overlap counts."""

    projection = ee.Projection(CALCULATION_CRS)
    return (
        ee.Image.constant(1)
        .rename("aoi_support")
        .reproject(crs=projection, scale=ANALYSIS_SCALE_M)
        .clip(aoi.geometry_wgs84)
        .selfMask()
    )


def _masked_analysis_support(
    aoi_support: Any,
    valid_mask: Any,
    *,
    band_name: str,
) -> Any:
    """Apply a validity mask without changing the AOI support/grid."""

    return aoi_support.updateMask(valid_mask).rename(band_name)


def _analysis_pixel_area(ee: Any) -> Any:
    """Return pixel area explicitly evaluated on the analysis grid."""

    return (
        ee.Image.pixelArea()
        .rename("pixel_area")
        .reproject(crs=ee.Projection(CALCULATION_CRS), scale=ANALYSIS_SCALE_M)
    )


def _stat_reducer(ee: Any) -> Any:
    reducer = ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True)
    reducer = reducer.combine(
        ee.Reducer.percentile([10, 25, 50, 75, 90, 95]),
        sharedInputs=True,
    )
    reducer = reducer.combine(ee.Reducer.minMax(), sharedInputs=True)
    return reducer


def build_metric_graph(graph: AnalysisGraph, aoi: Any, ee: Any) -> dict[str, Any]:
    """Return server-side metric values for one mode and cloud threshold."""

    pre_stats = ee.Dictionary(_reduce_region(graph.pre_nbr, _stat_reducer(ee), aoi))
    post_stats = ee.Dictionary(_reduce_region(graph.post_nbr, _stat_reducer(ee), aoi))
    dnbr_stats = ee.Dictionary(_reduce_region(graph.dnbr, _stat_reducer(ee), aoi))
    aoi_support = _analysis_aoi_support(aoi, ee)
    common_valid_support = _masked_analysis_support(
        aoi_support,
        graph.common_valid_mask,
        band_name="common_valid_support",
    )
    pre_valid_support = _masked_analysis_support(
        aoi_support,
        graph.pre_valid_mask,
        band_name="pre_valid_support",
    )
    post_valid_support = _masked_analysis_support(
        aoi_support,
        graph.post_valid_mask,
        band_name="post_valid_support",
    )
    common_count = _sum(common_valid_support, "common_valid_support", aoi, ee)
    pre_count = _sum(pre_valid_support, "pre_valid_support", aoi, ee)
    post_count = _sum(post_valid_support, "post_valid_support", aoi, ee)
    aoi_count = _sum(aoi_support, "aoi_support", aoi, ee)
    pixel_area = _analysis_pixel_area(ee)
    valid_overlap_area_m2 = _sum(
        pixel_area.updateMask(common_valid_support),
        "pixel_area",
        aoi,
        ee,
    )
    rasterized_aoi_area_m2 = _sum(
        pixel_area.updateMask(aoi_support),
        "pixel_area",
        aoi,
        ee,
    )
    result: dict[str, Any] = {
        "valid_overlap_fraction_raw": ee.Algorithms.If(
            aoi_count.gt(0),
            common_count.divide(aoi_count),
            None,
        ),
        "common_valid_pixel_count": common_count,
        "valid_pixel_count": common_count,
        "pre_valid_pixel_count": pre_count,
        "post_valid_pixel_count": post_count,
        "aoi_pixel_count": aoi_count,
        "valid_overlap_area_m2": valid_overlap_area_m2,
        "rasterized_aoi_area_m2": rasterized_aoi_area_m2,
        "valid_aoi_area_m2": rasterized_aoi_area_m2,
        "pre_nbr_mean": pre_stats.get("nbr_mean"),
        "pre_nbr_median": pre_stats.get("nbr_median"),
        "post_nbr_mean": post_stats.get("nbr_mean"),
        "post_nbr_median": post_stats.get("nbr_median"),
        "dnbr_mean": dnbr_stats.get("dnbr_mean"),
        "dnbr_median": dnbr_stats.get("dnbr_median"),
        "dnbr_p10": dnbr_stats.get("dnbr_p10"),
        "dnbr_p25": dnbr_stats.get("dnbr_p25"),
        "dnbr_p75": dnbr_stats.get("dnbr_p75"),
        "dnbr_p90": dnbr_stats.get("dnbr_p90"),
        "dnbr_p95": dnbr_stats.get("dnbr_p95"),
        "dnbr_min": dnbr_stats.get("dnbr_min"),
        "dnbr_max": dnbr_stats.get("dnbr_max"),
    }
    threshold_pixel_area = _analysis_pixel_area(ee).rename("area")
    for threshold in DNBR_THRESHOLDS:
        code = _threshold_code(threshold)
        exceed = graph.dnbr.gt(threshold).selfMask()
        exceed_support = _masked_analysis_support(
            aoi_support,
            exceed,
            band_name="exceed_support",
        )
        exceed_count = _sum(exceed_support, "exceed_support", aoi, ee)
        area_reduced = _reduce_region(
            threshold_pixel_area.updateMask(exceed_support),
            ee.Reducer.sum(),
            aoi,
        )
        area_ha = ee.Number(ee.Dictionary(area_reduced).get("area", 0)).divide(10000)
        result[f"fraction_dnbr_gt_{code}"] = ee.Algorithms.If(
            common_count.gt(0),
            exceed_count.divide(common_count),
            None,
        )
        result[f"area_ha_dnbr_gt_{code}"] = area_ha
    return result


def _metric_server_payload(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    aoi: Any,
) -> tuple[Any, dict[tuple[str, float], AnalysisGraph]]:
    ee = client.ee_module
    values: dict[str, Any] = {}
    graphs: dict[tuple[str, float], AnalysisGraph] = {}
    for mode in ANALYSIS_MODES:
        for threshold in CLOUD_THRESHOLDS:
            graph = build_analysis_graph(
                client,
                event_input,
                analysis_mode=mode,
                cloud_threshold=threshold,
            )
            graphs[(mode, threshold)] = graph
            values[f"{mode}|{threshold:.2f}"] = ee.Dictionary(build_metric_graph(graph, aoi, ee))
    return ee.Dictionary(values), graphs


def _resolve_with_retries(
    resolver: Callable[[int, int], Any],
    *,
    operation: str,
    error_stage: str,
    event_id: str,
    aoi_id: str,
    window_id: str,
    retry_count: int,
    backoff_seconds: float,
) -> Any:
    last_error: EarthEngineQueryError | None = None
    for attempt_index in range(retry_count + 1):
        attempt = attempt_index + 1
        try:
            return resolver(attempt, attempt_index)
        except EarthEngineQueryError as exc:
            last_error = exc
        except Exception as exc:
            last_error = EarthEngineQueryError.from_exception(
                exc,
                operation=operation,
                error_stage=error_stage,
                event_id=event_id,
                aoi_id=aoi_id,
                window_id=window_id,
                attempt=attempt,
                retry_count=attempt_index,
                max_retries=retry_count,
            )
            if attempt_index >= retry_count:
                raise last_error from exc
        if attempt_index < retry_count:
            time.sleep(backoff_seconds * (2**attempt_index))
    if last_error is not None:
        raise last_error
    raise DnbrValidationError("La operación server-side no produjo resultado ni error")


def _number_from_mapping(values: Mapping[str, Any], key: str) -> float | None:
    return _float(values.get(key))


def _overlap_raw_from_mapping(values: Mapping[str, Any]) -> float | None:
    """Read the overlap raw value without converting non-finite values to null."""

    key = "valid_overlap_fraction_raw"
    if key not in values:
        key = "valid_overlap_fraction"
    value = values.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DnbrValidationError(f"Fracción de solapamiento inválida: {value!r}") from exc


def _metric_row(
    event_input: DnbrEventInput,
    *,
    analysis_mode: str,
    cloud_threshold: float,
    values: Mapping[str, Any],
    processing_timestamp_utc: str,
    min_valid_overlap_fraction: float,
) -> dict[str, Any]:
    raw_overlap = _overlap_raw_from_mapping(values)
    overlap_normalization = normalize_overlap_fraction(
        raw_overlap,
        aoi_area_m2=event_input.aoi_area_m2,
        analysis_scale_m=ANALYSIS_SCALE_M,
    )
    overlap = overlap_normalization.value
    common_count = _number_from_mapping(values, "common_valid_pixel_count")
    if common_count is None and "common_valid_pixel_count" not in values:
        common_count = _number_from_mapping(values, "valid_pixel_count")
    aoi_count = _number_from_mapping(values, "aoi_pixel_count")
    if common_count is not None and common_count < -OVERLAP_FLOAT_TOLERANCE:
        raise DnbrValidationError(
            f"common_valid_pixel_count negativo: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    if aoi_count is not None and aoi_count < -OVERLAP_FLOAT_TOLERANCE:
        raise DnbrValidationError(
            f"aoi_pixel_count negativo: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    if (
        common_count is not None
        and aoi_count is not None
        and common_count > aoi_count + OVERLAP_FLOAT_TOLERANCE
    ):
        raise DnbrValidationError(
            "El soporte válido supera el soporte AOI: "
            f"common_valid_pixel_count={common_count}; "
            f"aoi_pixel_count={aoi_count}; "
            f"{event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    if common_count is not None and aoi_count is not None and aoi_count > 0 and raw_overlap is not None:
        expected_raw = common_count / aoi_count
        if abs(raw_overlap - expected_raw) > OVERLAP_FLOAT_TOLERANCE:
            raise DnbrValidationError(
                "Fracción de solapamiento inconsistente con el soporte raster: "
                f"raw={raw_overlap}; expected={expected_raw}; "
                f"{event_input.event_id}/{analysis_mode}/{cloud_threshold}"
            )
    valid_overlap_area = _number_from_mapping(values, "valid_overlap_area_m2")
    rasterized_aoi_area = _number_from_mapping(values, "rasterized_aoi_area_m2")
    if rasterized_aoi_area is None:
        rasterized_aoi_area = _number_from_mapping(values, "valid_aoi_area_m2")
    if valid_overlap_area is not None and valid_overlap_area < -1e-6:
        raise DnbrValidationError(
            f"valid_overlap_area_m2 negativo: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    if rasterized_aoi_area is not None and rasterized_aoi_area < -1e-6:
        raise DnbrValidationError(
            f"rasterized_aoi_area_m2 negativo: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    if (
        valid_overlap_area is not None
        and rasterized_aoi_area is not None
        and valid_overlap_area > rasterized_aoi_area + 1e-6
    ):
        raise DnbrValidationError(
            "El área válida supera el área AOI rasterizada: "
            f"valid_overlap_area_m2={valid_overlap_area}; "
            f"rasterized_aoi_area_m2={rasterized_aoi_area}; "
            f"{event_input.event_id}/{analysis_mode}/{cloud_threshold}"
        )
    metric_status = "usable_overlap"
    if overlap is None or (common_count or 0) <= 0:
        metric_status = "no_valid_overlap"
    elif overlap < min_valid_overlap_fraction:
        metric_status = "insufficient_valid_overlap"
    row: dict[str, Any] = {column: "" for column in METRICS_COLUMNS}
    row.update(
        {
            "event_id": event_input.event_id,
            "configuration_id": FROZEN_CONFIGURATION_ID,
            "policy_path": event_input.policy_path,
            "selected_combination_id": event_input.selected_combination_id,
            "pre_scene_id": event_input.pre_scene_id,
            "post_scene_id": event_input.post_scene_id,
            "pre_timestamp_utc": _text(event_input.pre_scene.get("acquisition_timestamp_utc")),
            "post_timestamp_utc": _text(event_input.post_scene.get("acquisition_timestamp_utc")),
            "analysis_mode": analysis_mode,
            "cloud_threshold": cloud_threshold,
            "aoi_method": AOI_METHOD,
            "aoi_id": AOI_ID,
            "aoi_buffer_m": AOI_BUFFER_M,
            "aoi_area_m2": event_input.aoi_area_m2,
            "vector_aoi_area_m2": event_input.aoi_area_m2,
            "valid_overlap_area_m2": _number_from_mapping(values, "valid_overlap_area_m2"),
            "valid_overlap_fraction_raw": overlap_normalization.raw,
            "valid_overlap_fraction": overlap,
            "overlap_fraction_tolerance": overlap_normalization.tolerance,
            "overlap_fraction_was_clipped": overlap_normalization.was_clipped,
            "common_valid_pixel_count": _int(values.get("common_valid_pixel_count", values.get("valid_pixel_count"))),
            "valid_pixel_count": _int(values.get("valid_pixel_count", values.get("common_valid_pixel_count"))),
            "pre_valid_pixel_count": _int(values.get("pre_valid_pixel_count")),
            "post_valid_pixel_count": _int(values.get("post_valid_pixel_count")),
            "aoi_pixel_count": _int(values.get("aoi_pixel_count")),
            "rasterized_aoi_area_m2": _number_from_mapping(values, "rasterized_aoi_area_m2")
            if "rasterized_aoi_area_m2" in values
            else _number_from_mapping(values, "valid_aoi_area_m2"),
            "valid_aoi_area_m2": _number_from_mapping(values, "valid_aoi_area_m2"),
            "pre_scene_count_used": len(event_input.pre_candidates) if analysis_mode == "window_median" else 1,
            "post_scene_count_used": len(event_input.post_candidates) if analysis_mode == "window_median" else 1,
            "pre_scene_ids_used": (
                ";".join(_scene_id(row) for row in event_input.pre_candidates)
                if analysis_mode == "window_median"
                else event_input.pre_scene_id
            ),
            "post_scene_ids_used": (
                ";".join(_scene_id(row) for row in event_input.post_candidates)
                if analysis_mode == "window_median"
                else event_input.post_scene_id
            ),
            "metric_status": metric_status,
            "processing_timestamp_utc": processing_timestamp_utc,
            "pipeline_version": DNBR_PIPELINE_VERSION,
        }
    )
    if metric_status == "usable_overlap":
        for field in (
            "pre_nbr_mean",
            "pre_nbr_median",
            "post_nbr_mean",
            "post_nbr_median",
            "dnbr_mean",
            "dnbr_median",
            "dnbr_p10",
            "dnbr_p25",
            "dnbr_p75",
            "dnbr_p90",
            "dnbr_p95",
            "dnbr_min",
            "dnbr_max",
        ):
            row[field] = _number_from_mapping(values, field)
        for threshold in DNBR_THRESHOLDS:
            code = _threshold_code(threshold)
            row[f"fraction_dnbr_gt_{code}"] = _number_from_mapping(values, f"fraction_dnbr_gt_{code}")
            row[f"area_ha_dnbr_gt_{code}"] = _number_from_mapping(values, f"area_ha_dnbr_gt_{code}")
        if not percentile_order_is_valid(row):
            raise DnbrValidationError(
                f"Percentiles dNBR fuera de orden: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
            )
        for threshold in DNBR_THRESHOLDS:
            area = _number_from_mapping(values, f"area_ha_dnbr_gt_{_threshold_code(threshold)}")
            if area is not None and valid_overlap_area is not None and area * 10000 > valid_overlap_area + 1e-6:
                raise DnbrValidationError(
                    f"Área dNBR superior al AOI válido: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
                )
        for threshold in DNBR_THRESHOLDS:
            fraction = _number_from_mapping(values, f"fraction_dnbr_gt_{_threshold_code(threshold)}")
            if fraction is None or fraction < 0 or fraction > 1:
                raise DnbrValidationError(
                    f"Fracción dNBR inválida: {event_input.event_id}/{analysis_mode}/{cloud_threshold}"
                )
    return row


def _thumbnail_bytes(image: Any, parameters: Mapping[str, Any]) -> bytes:
    url = image.getThumbURL(dict(parameters))
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read()
    if not payload.startswith(b"\x89PNG"):
        raise DnbrValidationError("Earth Engine no devolvió un thumbnail PNG")
    return payload


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _thumb_parameters(region: Any, *, kind: str) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "region": region,
        "dimensions": PANEL_THUMB_DIMENSION,
        "format": "png",
    }
    if kind == "rgb":
        parameters.update({"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.2})
    elif kind in {"nbr", "dnbr"}:
        parameters.update(
            {
                "min": NBR_VIS_MIN if kind == "nbr" else DNBR_VIS_MIN,
                "max": NBR_VIS_MAX if kind == "nbr" else DNBR_VIS_MAX,
                "palette": list(VISUALIZATION_PALETTE),
            }
        )
    elif kind == "mask":
        parameters.update({"min": 0, "max": 1, "palette": ["c026d3", "0f766e"]})
    else:
        raise DnbrValidationError(f"Tipo de thumbnail inválido: {kind}")
    return parameters


def _svg_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _write_quicklook_svg(
    path: Path,
    *,
    event_input: DnbrEventInput,
    thumbnail_names: Mapping[str, str],
    overlap_fraction: float | None,
    cloud_threshold: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 900
    panels = (
        ("rgb_pre", "RGB pre"),
        ("rgb_post", "RGB post"),
        ("nbr_pre", "NBR pre"),
        ("nbr_post", "NBR post"),
        ("dnbr", "dNBR"),
        ("mask", "Máscara válida común"),
    )
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="32" y="34" font-family="Arial,sans-serif" font-size="20" font-weight="700" fill="#0f172a">{_svg_text(event_input.event_id)}</text>',
        f'<text x="32" y="58" font-family="Arial,sans-serif" font-size="12" fill="#334155">pre {_svg_text(event_input.pre_scene.get("acquisition_timestamp_utc"))} · post {_svg_text(event_input.post_scene.get("acquisition_timestamp_utc"))} · política {_svg_text(event_input.policy_path)} · AOI b0500 · CS+ ≥ {cloud_threshold:.2f}</text>',
        f'<text x="32" y="78" font-family="Arial,sans-serif" font-size="12" fill="#334155">solapamiento válido: {_svg_text("n/a" if overlap_fraction is None else f"{overlap_fraction * 100:.2f}%")} · visualización descriptiva, sin conclusión automática</text>',
    ]
    panel_width, panel_height = 360, 360
    for index, (key, label) in enumerate(panels):
        column, row = index % 3, index // 3
        x, y = 32 + column * 390, 100 + row * 390
        lines.extend(
            [
                f'<rect x="{x}" y="{y}" width="{panel_width}" height="{panel_height}" rx="5" fill="#ffffff" stroke="#cbd5e1"/>',
                f'<image href="{_svg_text(thumbnail_names[key])}" x="{x + 8}" y="{y + 8}" width="{panel_width - 16}" height="{panel_height - 40}" preserveAspectRatio="xMidYMid slice"/>',
                f'<text x="{x + 12}" y="{y + panel_height - 12}" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#0f172a">{_svg_text(label)}</text>',
            ]
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _quicklook_overlay(event_input: DnbrEventInput, aoi: Any, ee: Any) -> Any:
    """Return an EE RGB overlay with the AOI outline and FIRMS detections."""

    detection_features = [
        ee.Feature(
            ee.Geometry.Point([detection.longitude, detection.latitude]),
            {"detection_id": detection.detection_id},
        )
        for detection in event_input.event.detections
    ]
    detections = ee.FeatureCollection(detection_features)
    boundary = (
        ee.Image.constant(0)
        .byte()
        .paint(aoi.geometry_wgs84, 1, 3)
        .selfMask()
        .visualize(min=0, max=1, palette=["ffd166"])
    )
    points = (
        ee.Image.constant(0)
        .byte()
        .paint(detections, 1, 5)
        .selfMask()
        .visualize(min=0, max=1, palette=["00e5ff"])
    )
    return boundary.blend(points)


def _quicklook_render_image(
    image: Any,
    kind: str,
    valid_mask: Any,
    overlay: Any,
    ee: Any,
) -> Any:
    """Render one panel with a fixed scale and explicit invalid-pixel background."""

    visual = _thumb_parameters(None, kind=kind)
    visual.pop("region", None)
    visual.pop("dimensions", None)
    visual.pop("format", None)
    if kind == "mask":
        base = image.unmask(0).rename("mask").visualize(**visual)
    else:
        invalid_background = ee.Image.constant(1).visualize(
            min=0,
            max=1,
            palette=["94a3b8"],
        )
        valid_image = image.updateMask(valid_mask).visualize(**visual)
        base = invalid_background.blend(valid_image)
    return base.blend(overlay)


def _quicklook(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    graph: AnalysisGraph,
    aoi: Any,
    *,
    output_dir: Path,
    overlap_fraction: float | None,
    cloud_threshold: float,
    retry_count: int,
    backoff_seconds: float,
) -> str:
    if graph.pre_source is None or graph.post_source is None:
        raise DnbrValidationError("El quicklook se define para selected_pair, no para window_median")
    prefix = f"{_safe_id(event_input.event_id)}_selected_pair_cs{_threshold_code(cloud_threshold)}"
    overlay = _quicklook_overlay(event_input, aoi, client.ee_module)
    thumbnail_specs = {
        "rgb_pre": (
            graph.pre_source.select(["B4", "B3", "B2"]),
            "rgb",
            graph.pre_valid_mask,
        ),
        "rgb_post": (
            graph.post_source.select(["B4", "B3", "B2"]),
            "rgb",
            graph.post_valid_mask,
        ),
        "nbr_pre": (graph.pre_nbr, "nbr", graph.common_valid_mask),
        "nbr_post": (graph.post_nbr, "nbr", graph.common_valid_mask),
        "dnbr": (graph.dnbr, "dnbr", graph.common_valid_mask),
        "mask": (graph.common_valid_mask, "mask", graph.common_valid_mask),
    }
    names: dict[str, str] = {}
    panel_payloads: dict[str, bytes] = {}
    pending_outputs: dict[Path, bytes] = {}
    thumbnail_parameters = {
        "region": aoi.geometry_wgs84,
        "dimensions": PANEL_THUMB_DIMENSION,
        "format": "png",
    }
    for key, (image, kind, valid_mask) in thumbnail_specs.items():
        output_path = output_dir / f"{prefix}_{key}.png"
        rendered = _quicklook_render_image(
            image,
            kind,
            valid_mask,
            overlay,
            client.ee_module,
        )
        payload = _resolve_with_retries(
            lambda _attempt, _retry, rendered=rendered: _thumbnail_bytes(
                rendered,
                thumbnail_parameters,
            ),
            operation=f"thumbnail {key} del evento {event_input.event_id}",
            error_stage="quicklook",
            event_id=event_input.event_id,
            aoi_id=AOI_ID,
            window_id=event_input.selected_combination_id,
            retry_count=retry_count,
            backoff_seconds=backoff_seconds,
        )
        pending_outputs[output_path] = payload
        names[key] = output_path.name
        panel_payloads[key] = payload
    validate_thumbnail_sources(
        panel_payloads,
        filenames=names,
    )
    for output_path, payload in pending_outputs.items():
        _write_bytes_atomic(output_path, payload)
    svg_path = output_dir / f"{prefix}.svg"
    _write_quicklook_svg(
        svg_path,
        event_input=event_input,
        thumbnail_names=names,
        overlap_fraction=overlap_fraction,
        cloud_threshold=cloud_threshold,
    )
    panel_path = output_dir / panel_filename(
        event_input.event_id,
        "selected_pair",
        cloud_threshold,
    )
    panel_metadata = {
        "event_id": event_input.event_id,
        "analysis_mode": "selected_pair",
        "cloud_threshold": cloud_threshold,
        "valid_overlap_fraction": overlap_fraction,
        "pre_timestamp_utc": event_input.pre_scene.get("acquisition_timestamp_utc"),
        "post_timestamp_utc": event_input.post_scene.get("acquisition_timestamp_utc"),
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "analysis_crs": CALCULATION_CRS,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "nbr_range": [NBR_VIS_MIN, NBR_VIS_MAX],
        "dnbr_range": [DNBR_VIS_MIN, DNBR_VIS_MAX],
        "invalid_pixel_color": "#94a3b8",
        "common_mask_invalid_color": "#c026d3",
        "overlay": "FIRMS detections and AOI boundary",
        "pipeline_version": DNBR_PIPELINE_VERSION,
    }
    _write_bytes_atomic(panel_path, compose_panel_png(panel_payloads, panel_metadata))
    return str(panel_path)


def rebuild_quicklook_from_artifacts(
    event_input: DnbrEventInput,
    *,
    output_dir: Path,
    metrics_row: Mapping[str, Any] | None = None,
    cloud_threshold: float = PRIMARY_CLOUD_THRESHOLD,
) -> dict[str, Any]:
    """Recompose one selected-pair panel using existing PNGs only.

    This function deliberately cannot repair invalid source thumbnails. It
    audits and rejects them before replacing the panel, so a local rebuild
    never turns a corrupted source into a plausible-looking scientific image.
    """

    prefix = f"{_safe_id(event_input.event_id)}_selected_pair_cs{_threshold_code(cloud_threshold)}"
    source_paths = {
        key: output_dir / f"{prefix}_{key}.png"
        for key in ("rgb_pre", "rgb_post", "nbr_pre", "nbr_post", "dnbr", "mask")
    }
    missing = [key for key, path in source_paths.items() if not path.is_file()]
    if missing:
        raise QuicklookValidationError(
            f"Faltan fuentes locales para {event_input.event_id}: {', '.join(missing)}",
            stats={
                "event_id": event_input.event_id,
                "missing_sources": missing,
                "source_files": {key: str(path) for key, path in source_paths.items()},
            },
        )
    thumbnails = {key: path.read_bytes() for key, path in source_paths.items()}
    details, source_stats = validate_thumbnail_sources(
        thumbnails,
        filenames={key: path.name for key, path in source_paths.items()},
    )
    overlap = _text((metrics_row or {}).get("valid_overlap_fraction")) or "n/a"
    metadata = {
        "event_id": event_input.event_id,
        "analysis_mode": "selected_pair",
        "cloud_threshold": cloud_threshold,
        "valid_overlap_fraction": overlap,
        "pre_timestamp_utc": event_input.pre_scene.get("acquisition_timestamp_utc"),
        "post_timestamp_utc": event_input.post_scene.get("acquisition_timestamp_utc"),
        "aoi_id": AOI_ID,
        "aoi_buffer_m": AOI_BUFFER_M,
        "analysis_crs": CALCULATION_CRS,
        "analysis_scale_m": ANALYSIS_SCALE_M,
        "nbr_range": [NBR_VIS_MIN, NBR_VIS_MAX],
        "dnbr_range": [DNBR_VIS_MIN, DNBR_VIS_MAX],
        "invalid_pixel_color": "#94a3b8",
        "common_mask_invalid_color": "#c026d3",
        "overlay": "FIRMS detections and AOI boundary (preserved in source thumbnails)",
        "pipeline_version": DNBR_PIPELINE_VERSION,
        "rebuild_source": "existing_local_png_artifacts",
    }
    panel_path = output_dir / panel_filename(
        event_input.event_id,
        "selected_pair",
        cloud_threshold,
    )
    panel_payload = compose_panel_png(thumbnails, metadata)
    _write_bytes_atomic(panel_path, panel_payload)
    return {
        "event_id": event_input.event_id,
        "status": "generated",
        "panel_path": str(panel_path),
        "source_stats": source_stats,
        "metadata": metadata,
        "source_detail_modes": {key: detail.mode for key, detail in details.items()},
    }


def execute_event(
    client: EarthEngineClient,
    event_input: DnbrEventInput,
    *,
    output_dir: Path,
    min_valid_overlap_fraction: float = DEFAULT_MIN_VALID_OVERLAP_FRACTION,
    retry_count: int = 2,
    backoff_seconds: float = 2.0,
    root: Path | None = None,
) -> dict[str, Any]:
    """Query one event, write its quicklook, and return auditable rows."""

    if not 0 < min_valid_overlap_fraction <= 1:
        raise DnbrValidationError("min_valid_overlap_fraction debe estar entre 0 y 1")
    processing_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        aoi = build_aoi(event_input.event, AOI_BUFFER_M, client)
    except EarthEngineQueryError:
        raise
    except Exception as exc:
        error = EarthEngineQueryError.from_exception(
            exc,
            operation=f"construcción AOI {AOI_ID} del evento {event_input.event_id}",
            error_stage="build_aoi",
            event_id=event_input.event_id,
            aoi_id=AOI_ID,
            window_id=event_input.selected_combination_id,
            attempt=1,
            retry_count=0,
            max_retries=0,
        )
        raise error from exc
    try:
        payload, graphs = _metric_server_payload(client, event_input, aoi)
    except EarthEngineQueryError:
        raise
    except Exception as exc:
        error = EarthEngineQueryError.from_exception(
            exc,
            operation=f"construcción del grafo NBR/dNBR del evento {event_input.event_id}",
            error_stage="build_nbr_dnbr_graph",
            event_id=event_input.event_id,
            aoi_id=AOI_ID,
            window_id=event_input.selected_combination_id,
            attempt=1,
            retry_count=0,
            max_retries=0,
        )
        raise error from exc
    resolved = _resolve_with_retries(
        lambda attempt, retry: client.get_info(
            payload,
            f"métricas NBR/dNBR del evento {event_input.event_id}",
            error_stage="nbr_dnbr_metrics",
            event_id=event_input.event_id,
            aoi_id=AOI_ID,
            window_id=event_input.selected_combination_id,
            attempt=attempt,
            retry_count=retry,
            max_retries=retry_count,
        ),
        operation=f"métricas NBR/dNBR del evento {event_input.event_id}",
        error_stage="nbr_dnbr_metrics",
        event_id=event_input.event_id,
        aoi_id=AOI_ID,
        window_id=event_input.selected_combination_id,
        retry_count=retry_count,
        backoff_seconds=backoff_seconds,
    )
    if not isinstance(resolved, Mapping):
        raise DnbrValidationError(f"Respuesta NBR/dNBR inválida para {event_input.event_id}")
    sensitivity_rows: list[dict[str, Any]] = []
    metrics_rows: list[dict[str, Any]] = []
    for mode in ANALYSIS_MODES:
        for threshold in CLOUD_THRESHOLDS:
            key = f"{mode}|{threshold:.2f}"
            values = resolved.get(key, {})
            if not isinstance(values, Mapping):
                values = {}
            row = _metric_row(
                event_input,
                analysis_mode=mode,
                cloud_threshold=threshold,
                values=values,
                processing_timestamp_utc=processing_timestamp,
                min_valid_overlap_fraction=min_valid_overlap_fraction,
            )
            sensitivity_rows.append(row)
            if threshold == PRIMARY_CLOUD_THRESHOLD:
                metrics_rows.append(row)
    selected_primary = next(row for row in metrics_rows if row["analysis_mode"] == "selected_pair")
    quicklook_path = _quicklook(
        client,
        event_input,
        graphs[("selected_pair", PRIMARY_CLOUD_THRESHOLD)],
        aoi,
        output_dir=output_dir,
        overlap_fraction=_float(selected_primary.get("valid_overlap_fraction")),
        cloud_threshold=PRIMARY_CLOUD_THRESHOLD,
        retry_count=retry_count,
        backoff_seconds=backoff_seconds,
    )
    relative_quicklook = quicklook_path
    if root is not None:
        try:
            relative_quicklook = str(Path(quicklook_path).resolve().relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            relative_quicklook = quicklook_path
    for row in metrics_rows:
        row["quicklook_path"] = quicklook_path_for_mode(relative_quicklook, row["analysis_mode"])
    for row in sensitivity_rows:
        row["quicklook_path"] = quicklook_path_for_mode(relative_quicklook, row["analysis_mode"])
    return {
        "event_id": event_input.event_id,
        "metrics_rows": metrics_rows,
        "sensitivity_rows": sensitivity_rows,
        "quicklook_path": relative_quicklook,
        "thumbnail_downloaded": True,
        "processing_timestamp_utc": processing_timestamp,
    }


def read_utf8_csv(path: Path | str) -> list[dict[str, str]]:
    input_path = Path(path)
    if not input_path.is_file():
        return []
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_utf8_csv_atomic(
    path: Path | str,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: "" if row.get(field) is None else row.get(field, "")
                    for field in fieldnames
                }
            )
    temporary.replace(output)


def write_json_atomic(path: Path | str, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def merge_event_rows(
    existing: Sequence[Mapping[str, Any]],
    replacement: Sequence[Mapping[str, Any]],
    replace_event_ids: set[str],
) -> list[dict[str, Any]]:
    """Replace only selected event rows; other event results survive."""

    kept = [
        dict(row)
        for row in existing
        if _text(row.get("event_id")) not in replace_event_ids
    ]
    return kept + [dict(row) for row in replacement]


def build_review_queue(
    processable: Sequence[DnbrEventInput],
    metrics_rows: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    selected_metrics = {
        _text(row.get("event_id")): row
        for row in metrics_rows
        if _text(row.get("analysis_mode")) == "selected_pair"
        and _float(row.get("cloud_threshold")) == PRIMARY_CLOUD_THRESHOLD
    }
    rows: list[dict[str, Any]] = []
    for event_input in sorted(processable, key=lambda item: item.event_id):
        metric = selected_metrics.get(event_input.event_id, {})
        quicklook = _text(metric.get("quicklook_path"))
        if root is not None and quicklook:
            try:
                quicklook = str(
                    Path(quicklook).resolve().relative_to(root.resolve())
                ).replace("\\", "/")
            except ValueError:
                pass
        rows.append(
            {
                "event_id": event_input.event_id,
                "configuration_id": FROZEN_CONFIGURATION_ID,
                "policy_path": event_input.policy_path,
                "selected_combination_id": event_input.selected_combination_id,
                "pre_scene_id": event_input.pre_scene_id,
                "post_scene_id": event_input.post_scene_id,
                "pre_timestamp_utc": _text(
                    event_input.pre_scene.get("acquisition_timestamp_utc")
                ),
                "post_timestamp_utc": _text(
                    event_input.post_scene.get("acquisition_timestamp_utc")
                ),
                "selected_pair_metric_status": _text(metric.get("metric_status")),
                "selected_pair_valid_overlap_fraction": metric.get(
                    "valid_overlap_fraction", ""
                ),
                "quicklook_path": quicklook,
                "visible_burn_scar": "",
                "scar_confidence": "",
                "competing_land_change": "",
                "reviewer_notes": "",
                "review_status": "",
            }
        )
    return rows


def build_report(
    inputs: DnbrInputs,
    *,
    requested_event_ids: Sequence[str],
    completed_event_ids: Sequence[str],
    failed_event_ids: Sequence[str],
    metrics_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    min_valid_overlap_fraction: float,
    earth_engine_queries_made: bool,
) -> dict[str, Any]:
    processable_ids = {item.event_id for item in inputs.processable}
    completed = sorted(set(completed_event_ids) & processable_ids)
    failed = sorted(set(failed_event_ids) & processable_ids)
    pending = sorted(processable_ids - set(completed) - set(failed))
    metric_event_ids = {_text(row.get("event_id")) for row in metrics_rows}
    quicklook_paths = sorted(
        {
            _text(row.get("quicklook_path"))
            for row in metrics_rows
            if _text(row.get("quicklook_path"))
        }
    )
    outside_metrics = sorted(metric_event_ids - processable_ids)
    clipped_metric_rows = sum(
        1 for row in metrics_rows if _bool(row.get("overlap_fraction_was_clipped"))
    )
    clipped_sensitivity_rows = sum(
        1 for row in sensitivity_rows if _bool(row.get("overlap_fraction_was_clipped"))
    )
    excluded = [
        {
            "event_id": _text(row.get("event_id")),
            "status": OPTICAL_EXCLUSION_STATUS,
            "reason": _text(row.get("final_exclusion_reason")),
        }
        for row in inputs.excluded
    ]
    return {
        "stage": "sentinel2_dnbr_pilot",
        "pipeline_version": DNBR_PIPELINE_VERSION,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "pilot_universe_count": len(inputs.events),
        "processable_event_count": len(inputs.processable),
        "excluded_event_count": len(inputs.excluded),
        "requested_event_count": len(set(requested_event_ids)),
        "completed_event_count": len(completed),
        "failed_event_count": len(failed),
        "pending_event_count": len(pending),
        "completed_event_ids": completed,
        "failed_event_ids": failed,
        "pending_event_ids": pending,
        "metric_event_count": len(metric_event_ids),
        "metric_row_count": len(metrics_rows),
        "sensitivity_row_count": len(sensitivity_rows),
        "overlap_fraction_clipped_row_count": clipped_metric_rows,
        "overlap_fraction_clipped_sensitivity_row_count": clipped_sensitivity_rows,
        "overlap_fraction_clipped_total_row_count": clipped_metric_rows + clipped_sensitivity_rows,
        "errors": [dict(row) for row in errors],
        "excluded_events": excluded,
        "collections": {
            "sentinel2_surface_reflectance": SENTINEL2_SR_COLLECTION,
            "cloud_score_plus": CLOUD_SCORE_PLUS_COLLECTION,
        },
        "policy": {
            "configuration_id": FROZEN_CONFIGURATION_ID,
            "aoi_id": AOI_ID,
            "aoi_buffer_m": AOI_BUFFER_M,
            "primary_combination_ids": ["b0500_pre30_post45"],
            "fallback_combination_ids": ["b0500_pre30_post90"],
            "policy_rule": "A",
            "selected_pair_source": "outputs/sentinel2_event_pair_selection.csv",
        },
        "analysis": {
            "modes": list(ANALYSIS_MODES),
            "primary_mode": "selected_pair",
            "sensitivity_mode": "window_median",
            "analysis_scale_m": ANALYSIS_SCALE_M,
            "cloud_threshold_primary": PRIMARY_CLOUD_THRESHOLD,
            "cloud_threshold_sensitivity": [0.60, 0.65],
            "dnbr_thresholds_descriptive": list(DNBR_THRESHOLDS),
            "min_valid_overlap_fraction": min_valid_overlap_fraction,
            "overlap_fraction_tolerance_formula": "1e-9 (floating-point only; no pixel tolerance)",
            "overlap_support_contract": dict(OVERLAP_SUPPORT_CONTRACT),
            "nbr_formula": NBR_FORMULA,
            "dnbr_formula": DNBR_FORMULA,
            "b8_b12_required": True,
            "cloud_score_plus_required": True,
            "cloudy_pixel_percentage_used_for_mask": False,
        },
        "quicklooks": {
            "count": len(quicklook_paths),
            "paths": quicklook_paths,
            "full_scenes_downloaded": False,
            "aoi_only": True,
            "automatic_conclusion_drawn": False,
        },
        "earth_engine_queries_made": earth_engine_queries_made,
        "full_raster_downloaded": False,
        "nbr_dnbr_computed": bool(metric_event_ids),
        "significant_burn_labels_created": False,
        "severity_labels_created": False,
        "models_trained": False,
        "manual_review_fields_filled": False,
        "invariants": {
            "pilot_count_30": len(inputs.events) == EXPECTED_PILOT_EVENT_COUNT,
            "processable_count_28": len(inputs.processable) == EXPECTED_PROCESSABLE_EVENT_COUNT,
            "excluded_count_2": len(inputs.excluded) == EXPECTED_EXCLUDED_EVENT_COUNT,
            "no_2026_event": all(
                event.start_timestamp_utc.year != 2026
                and event.end_timestamp_utc.year != 2026
                for event in inputs.events
            ),
            "metrics_only_processable_events": not outside_metrics,
            "excluded_retained_as_nonobservable": all(
                item["status"] == OPTICAL_EXCLUSION_STATUS for item in excluded
            ),
            "selected_pair_and_window_median_separate": set(
                row.get("analysis_mode") for row in sensitivity_rows
            ) <= set(ANALYSIS_MODES),
            "no_automatic_burn_label": True,
        },
    }


def write_report_markdown(
    path: Path | str,
    report: Mapping[str, Any],
    metrics_rows: Sequence[Mapping[str, Any]],
) -> None:
    lines = [
        "# Piloto NBR/dNBR Sentinel-2",
        "",
        "> Medición espectral descriptiva para la política óptica congelada. No es una etiqueta significant_burn ni ground truth de severidad.",
        "",
        f"- Universo FIRMS piloto: {report['pilot_universe_count']} eventos.",
        f"- Procesables bajo la política actual: {report['processable_event_count']}.",
        f"- Excluidos como no observables: {report['excluded_event_count']}.",
        f"- Solicitados en esta ejecución: {report['requested_event_count']}.",
        f"- Completados: {report['completed_event_count']}; fallidos: {report['failed_event_count']}; pendientes: {report['pending_event_count']}.",
        f"- Escala analítica: {report['analysis']['analysis_scale_m']} m; AOI: {report['policy']['aoi_id']} ({report['policy']['aoi_buffer_m']} m).",
        f"- Umbral de solapamiento válido operativo: {report['analysis']['min_valid_overlap_fraction']}; es configurable y provisional.",
        f"- Filas normalizadas por tolerancia flotante 1e-9: {report['overlap_fraction_clipped_row_count']} principales y {report['overlap_fraction_clipped_sensitivity_row_count']} de sensibilidad.",
        "- Fórmulas: NBR=(B8-B12)/(B8+B12); dNBR=NBR_pre-NBR_post.",
        "- CLOUDY_PIXEL_PERCENTAGE no decide la máscara; se exige B8, B12 y Cloud Score+ enlazado.",
        "- No se crean etiquetas de quema/severidad ni se entrenan modelos.",
        "",
        "## Eventos excluidos",
        "",
        "Los siguientes eventos se conservan como optically_unobservable_under_current_policy; no son negativos.",
        "",
        "| event_id | estado | motivo |",
        "|---|---|---|",
    ]
    for item in report["excluded_events"]:
        lines.append(f"| {item['event_id']} | {item['status']} | {item['reason']} |")
    lines.extend(
        [
            "",
            "## Resultados por evento y modo",
            "",
            "Los umbrales dNBR 0.10–0.40 son fracciones y áreas descriptivas; no son categorías de severidad.",
            "",
            "| event_id | modo | CS+ | solapamiento | estado | dNBR mediana | área >0.20 ha | quicklook |",
            "|---|---|---:|---:|---|---:|---:|---|",
        ]
    )
    for row in sorted(
        metrics_rows,
        key=lambda item: (
            _text(item.get("event_id")),
            _text(item.get("analysis_mode")),
            _float(item.get("cloud_threshold")) or 0,
        ),
    ):
        overlap = _float(row.get("valid_overlap_fraction"))
        median_value = _float(row.get("dnbr_median"))
        area_value = _float(row.get("area_ha_dnbr_gt_020"))
        lines.append(
            f"| {_text(row.get('event_id'))} | {_text(row.get('analysis_mode'))} | {_text(row.get('cloud_threshold'))} | {'n/a' if overlap is None else f'{overlap:.4f}'} | {_text(row.get('metric_status'))} | {'n/a' if median_value is None else f'{median_value:.5f}'} | {'n/a' if area_value is None else f'{area_value:.4f}'} | {_text(row.get('quicklook_path'))} |"
        )
    lines.extend(
        [
            "",
            "## Sensibilidad y límites",
            "",
            "- selected_pair usa exactamente las escenas seleccionadas antes de calcular índices.",
            "- window_median es una mediana de reflectancias en las escenas utilizables del mismo AOI y ventana; queda separado de la política principal.",
            "- Los umbrales CS+ 0.60 y 0.65 son sensibilidad descriptiva; no sustituyen silenciosamente el umbral primario 0.50.",
            "- La fracción válida común usa como denominador los píxeles de AOI a 20 m; si queda por debajo del umbral operativo, los campos de NBR/dNBR se dejan vacíos.",
            "- Se conserva valid_overlap_fraction_raw. Solo se normaliza a [0,1] dentro de una tolerancia flotante de 1e-9; no se concede tolerancia geométrica basada en el tamaño de un píxel.",
            "- Los quicklooks son thumbnails del AOI b0500 dentro de un panel PNG autocontenido; NBR/dNBR usan rango visual fijo [-1,1] con dNBR centrado en 0.",
            "- No se descargan escenas completas y los paneles no contienen conclusiones automáticas.",
            "- dNBR puede responder a fenología, humedad, agricultura, regeneración, mezcla de píxeles y otras alteraciones; no es por sí solo ground truth.",
            "",
        ]
    )
    if report.get("errors"):
        lines.extend(
            [
                "## Errores",
                "",
                "| event_id | etapa | causa | mensaje | traceback |",
                "|---|---|---|---|---|",
            ]
        )
        for error in report["errors"]:
            lines.append(
                f"| {_text(error.get('event_id'))} | {_text(error.get('error_stage'))} | {_text(error.get('cause_type'))} | {_text(error.get('cause_message') or error.get('error_message'))} | {_text(error.get('traceback_file'))} |"
            )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_dnbr_outputs(
    paths: Mapping[str, Path | str],
    inputs: DnbrInputs,
    *,
    metrics_rows: Sequence[Mapping[str, Any]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    requested_event_ids: Sequence[str],
    completed_event_ids: Sequence[str],
    failed_event_ids: Sequence[str],
    min_valid_overlap_fraction: float,
    earth_engine_queries_made: bool,
) -> dict[str, Any]:
    report = build_report(
        inputs,
        requested_event_ids=requested_event_ids,
        completed_event_ids=completed_event_ids,
        failed_event_ids=failed_event_ids,
        metrics_rows=metrics_rows,
        sensitivity_rows=sensitivity_rows,
        errors=errors,
        min_valid_overlap_fraction=min_valid_overlap_fraction,
        earth_engine_queries_made=earth_engine_queries_made,
    )
    write_utf8_csv_atomic(paths["metrics"], METRICS_COLUMNS, metrics_rows)
    write_utf8_csv_atomic(paths["errors"], ERROR_COLUMNS, errors)
    write_utf8_csv_atomic(paths["sensitivity"], SENSITIVITY_COLUMNS, sensitivity_rows)
    queue = build_review_queue(inputs.processable, metrics_rows)
    write_utf8_csv_atomic(paths["review_queue"], REVIEW_QUEUE_COLUMNS, queue)
    write_json_atomic(paths["report_json"], report)
    write_report_markdown(paths["report_markdown"], report, metrics_rows)
    return report
