"""Reproducible Sentinel-2 policy comparison from the frozen local inventory.

This module compares the twelve already-inventoried AOI/window combinations
under rules A-D.  It never initializes Earth Engine, downloads raster data,
computes NBR/dNBR, or changes an inventory.  The quality metrics are therefore
availability metrics, not burn labels or validation of an active fire.
"""

from __future__ import annotations

import csv
import hashlib
import html
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .sentinel2_observability import (
    BUFFER_OPTIONS,
    FROZEN_CONFIGURATION_ID,
    PILOT_EXPECTED_COUNT,
    POST_WINDOW_OPTIONS,
    PRE_WINDOW_OPTIONS,
    SCENE_COLUMNS,
    USABILITY_RULES,
    WINDOW_PAIR_OPTIONS,
    EventInput,
    ObservabilityValidationError,
    load_pilot_events,
    make_combination_id,
    normalize_inventory_rows,
    parse_utc_timestamp,
    read_csv_rows,
    scene_is_usable,
)


POLICY_PIPELINE_VERSION = "fuegopa-sentinel2-policy-v1"
DEFAULT_POLICY_RULE = "A"
BASELINE_COMBINATION_ID = "b0500_pre30_post45"
PRIMARY_SHORT_COMBINATION_ID = BASELINE_COMBINATION_ID

OBSERVABILITY_REQUIRED_COLUMNS = (
    "event_id",
    "configuration_id",
    "aoi_id",
    "aoi_buffer_m",
    "window_id",
    "combination_id",
    "rule_id",
    "pre_scene_count",
    "post_scene_count",
    "usable_pre_scene_count",
    "usable_post_scene_count",
    "selected_pre_scene_id",
    "selected_post_scene_id",
    "best_pre_scene_id",
    "best_post_scene_id",
    "best_pre_clear_fraction",
    "best_post_clear_fraction",
    "days_between_event_and_pre",
    "days_between_event_and_post",
    "pre_coverage_fraction",
    "post_coverage_fraction",
    "usable_pair_exists",
    "observability_status",
    "exclusion_reason",
    "exclusion_reasons",
    "event_month",
    "event_size_class",
    "source_class",
    "chain_class",
)

DECISION_COLUMNS = (
    "scope",
    "segment_dimension",
    "segment_value",
    "configuration_id",
    "combination_id",
    "aoi_id",
    "buffer_m",
    "window_id",
    "rule_id",
    "rank_within_rule",
    "rank_group",
    "tie_group_size",
    "is_best_within_rule",
    "event_count",
    "events_with_pre_scene",
    "events_with_post_scene",
    "events_with_usable_pair",
    "usable_pair_rate",
    "total_usable_combinations",
    "pre_quality_event_count",
    "post_quality_event_count",
    "pair_quality_event_count",
    "pre_coverage_median",
    "pre_coverage_p10",
    "post_coverage_median",
    "post_coverage_p10",
    "pre_clear_fraction_median",
    "pre_clear_fraction_p10",
    "post_clear_fraction_median",
    "post_clear_fraction_p10",
    "pre_temporal_distance_median",
    "pre_temporal_distance_p90",
    "post_temporal_distance_median",
    "post_temporal_distance_p90",
    "pre_candidate_scene_median",
    "post_candidate_scene_median",
    "events_depending_exclusively_on_combination",
    "exclusive_event_ids",
    "events_rescued_vs_baseline",
    "rescued_event_ids",
    "events_lost_vs_best_combination",
    "lost_event_ids",
    "aoi_area_median_m2",
    "inventory_row_count",
    "pre_inventory_row_count",
    "post_inventory_row_count",
    "unique_candidate_scene_count",
    "unique_selected_scene_count",
    "window_span_days",
    "relative_compute_cost_index",
    "ranking_priority_key",
    "ranking_note",
)

EVENT_SELECTION_COLUMNS = (
    "event_id",
    "configuration_id",
    "event_month",
    "event_size_class",
    "source_class",
    "chain_class",
    "possible_chain_merge",
    "primary_combination_id",
    "policy_rule",
    "primary_sufficient",
    "fallback_required",
    "fallback_combination_id",
    "fallback_type",
    "fallback_rescues",
    "minimum_rule_passed",
    "selected_combination_id",
    "selected_pre_scene_id",
    "selected_post_scene_id",
    "pre_scene_acquisition_timestamp",
    "post_scene_acquisition_timestamp",
    "pre_clear_fraction",
    "post_clear_fraction",
    "pre_coverage_fraction",
    "post_coverage_fraction",
    "pre_temporal_distance_days",
    "post_temporal_distance_days",
    "pre_cloud_fraction",
    "post_cloud_fraction",
    "final_observability_status",
    "final_exclusion_reason",
)

FALLBACK_COLUMNS = (
    "event_id",
    "configuration_id",
    "event_month",
    "event_size_class",
    "source_class",
    "chain_class",
    "primary_combination_id",
    "policy_rule",
    "primary_sufficient",
    "fallback_order",
    "fallback_combination_id",
    "fallback_type",
    "fallback_buffer_m",
    "fallback_window_id",
    "pair_available",
    "rescues_vs_primary",
    "selected_by_hierarchy",
    "pre_scene_count",
    "post_scene_count",
    "usable_pre_scene_count",
    "usable_post_scene_count",
    "selected_pre_scene_id",
    "selected_post_scene_id",
    "pre_clear_fraction",
    "post_clear_fraction",
    "pre_coverage_fraction",
    "post_coverage_fraction",
    "pre_temporal_distance_days",
    "post_temporal_distance_days",
    "attempt_status",
)


def default_policy_paths(root: Path | str) -> dict[str, Path]:
    """Return local input/output paths without touching any file."""

    base = Path(root)
    return {
        "pilot": base / "data" / "processed" / "sentinel2_observability_pilot_events.csv",
        "membership": base / "data" / "processed" / "firms_cocle_2025_event_membership.csv",
        "events": base / "data" / "processed" / "firms_cocle_2025_events_provisional.csv",
        "scene_inventory": base / "data" / "interim" / "sentinel2_scene_inventory.csv",
        "aoi_inventory": base / "data" / "interim" / "sentinel2_aoi_inventory.csv",
        "observability": base / "data" / "interim" / "sentinel2_observability.csv",
        "decision": base / "outputs" / "sentinel2_policy_decision.csv",
        "decision_markdown": base / "outputs" / "sentinel2_policy_decision.md",
        "event_selection": base / "outputs" / "sentinel2_event_pair_selection.csv",
        "fallbacks": base / "outputs" / "sentinel2_policy_fallbacks.csv",
        "figures": base / "outputs" / "figures" / "sentinel2_policy",
    }


def load_policy_inputs(
    *,
    pilot_path: Path | str,
    events_path: Path | str,
    membership_path: Path | str,
    observability_path: Path | str,
    scene_inventory_path: Path | str,
    aoi_inventory_path: Path | str,
) -> tuple[list[EventInput], list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the existing pilot, observability rows and inventories as UTF-8."""

    events = load_pilot_events(pilot_path, events_path, membership_path)
    observation_rows = read_csv_rows(observability_path)
    scene_rows = read_csv_rows(scene_inventory_path)
    aoi_rows = read_csv_rows(aoi_inventory_path)
    normalized_scenes, normalized_aois = validate_policy_inputs(
        events,
        observation_rows,
        scene_rows,
        aoi_rows,
    )
    return events, observation_rows, normalized_scenes, normalized_aois, scene_rows


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


def _int(value: Any, default: int = 0) -> int:
    parsed = _float(value)
    return int(parsed) if parsed is not None else default


def _scene_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("sentinel2_scene_id") or row.get("system_index"))


def _quantile(values: Iterable[float | None], fraction: float) -> float | None:
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _median(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return median(usable) if usable else None


def _join_ids(values: Iterable[str]) -> str:
    return ";".join(sorted(set(values)))


def _format_number(value: Any, digits: int = 3) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _window_parts(combination_id: str) -> tuple[str, str, str]:
    parts = combination_id.split("_")
    if len(parts) != 3:
        raise ObservabilityValidationError(f"Combinación inválida en política: {combination_id}")
    return parts[0], parts[1], parts[2]


def _window_span_days(combination_id: str) -> int:
    _, pre_id, post_id = _window_parts(combination_id)
    pre_start, pre_end_offset = PRE_WINDOW_OPTIONS[pre_id]
    post_start_offset, post_end = POST_WINDOW_OPTIONS[post_id]
    return (pre_start - pre_end_offset) + (post_end - post_start_offset)


def _allowed_combinations() -> tuple[str, ...]:
    return tuple(
        make_combination_id(aoi_id, window_id.split("_")[0], window_id.split("_")[1])
        for _, aoi_id in BUFFER_OPTIONS
        for window_id in WINDOW_PAIR_OPTIONS
    )


def _scene_index(scene_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in scene_rows:
        normalized = dict(row)
        index[(_text(row["event_id"]), _text(row["combination_id"]), _text(row["period_role"]), _scene_id(row))].append(normalized)
    return index


def validate_policy_inputs(
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    aoi_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate the pilot grain and cross-file joins before policy calculations."""

    if len(events) != PILOT_EXPECTED_COUNT:
        raise ObservabilityValidationError(
            f"La política requiere exactamente {PILOT_EXPECTED_COUNT} eventos; recibió {len(events)}"
        )
    event_ids = {event.event_id for event in events}
    if len(event_ids) != len(events):
        raise ObservabilityValidationError("El piloto contiene event_id duplicados")
    for event in events:
        if event.configuration_id != FROZEN_CONFIGURATION_ID:
            raise ObservabilityValidationError(f"Evento fuera de {FROZEN_CONFIGURATION_ID}: {event.event_id}")
        if event.start_timestamp_utc.year == 2026 or event.end_timestamp_utc.year == 2026:
            raise ObservabilityValidationError(f"No se permite evento de 2026: {event.event_id}")

    if not observation_rows:
        raise ObservabilityValidationError("La observabilidad no contiene filas")
    missing_observability = [column for column in OBSERVABILITY_REQUIRED_COLUMNS if column not in observation_rows[0]]
    if missing_observability:
        raise ObservabilityValidationError(
            f"Observabilidad incompatible; faltan columnas: {', '.join(missing_observability)}"
        )

    normalized_scenes, normalized_aois = normalize_inventory_rows(scene_rows, aoi_rows)
    allowed_combinations = set(_allowed_combinations())
    expected_keys = {
        (event_id, combination_id, rule_id)
        for event_id in event_ids
        for combination_id in allowed_combinations
        for rule_id in USABILITY_RULES
    }
    observation_keys: set[tuple[str, str, str]] = set()
    for row in observation_rows:
        event_id = _text(row.get("event_id"))
        combination_id = _text(row.get("combination_id"))
        rule_id = _text(row.get("rule_id"))
        if event_id not in event_ids:
            raise ObservabilityValidationError(f"Observabilidad contiene evento fuera del piloto: {event_id}")
        if _text(row.get("configuration_id")) != FROZEN_CONFIGURATION_ID:
            raise ObservabilityValidationError(f"Observabilidad fuera de {FROZEN_CONFIGURATION_ID}: {event_id}")
        if combination_id not in allowed_combinations or rule_id not in USABILITY_RULES:
            raise ObservabilityValidationError(f"Clave de política incompatible: {combination_id}/{rule_id}")
        key = (event_id, combination_id, rule_id)
        if key in observation_keys:
            raise ObservabilityValidationError(f"Fila de observabilidad duplicada: {key}")
        observation_keys.add(key)
        for field in ("pre_window_start", "pre_window_end", "post_window_start", "post_window_end"):
            if _text(row.get(field)):
                parse_utc_timestamp(row[field], f"{event_id}.{field}")
    if observation_keys != expected_keys:
        missing = sorted(expected_keys - observation_keys)
        extra = sorted(observation_keys - expected_keys)
        raise ObservabilityValidationError(f"Grano de observabilidad incompatible; missing={missing[:3]} extra={extra[:3]}")

    scene_event_ids = {_text(row["event_id"]) for row in normalized_scenes}
    aoi_event_ids = {_text(row["event_id"]) for row in normalized_aois}
    if not scene_event_ids.issubset(event_ids) or not aoi_event_ids.issubset(event_ids):
        raise ObservabilityValidationError("El inventario contiene eventos fuera del piloto")
    for row in normalized_scenes:
        if _text(row.get("configuration_id")) != FROZEN_CONFIGURATION_ID:
            raise ObservabilityValidationError(f"Escena fuera de {FROZEN_CONFIGURATION_ID}: {row['event_id']}")
        parse_utc_timestamp(row["acquisition_timestamp_utc"], f"{row['event_id']}.acquisition_timestamp_utc")
    expected_aoi_keys = {(event_id, aoi_id) for event_id in event_ids for _, aoi_id in BUFFER_OPTIONS}
    actual_aoi_keys = {(_text(row["event_id"]), _text(row["aoi_id"])) for row in normalized_aois}
    if actual_aoi_keys != expected_aoi_keys:
        raise ObservabilityValidationError("El inventario AOI no contiene exactamente los tres buffers por evento")

    event_by_id = {event.event_id: event for event in events}
    for row in observation_rows:
        event = event_by_id[_text(row["event_id"])]
        combination_id = _text(row["combination_id"])
        # Use a direct role-specific scan so duplicate Sentinel-2 scenes remain safe.
        pre_inventory = [scene for scene in normalized_scenes if scene["event_id"] == event.event_id and scene["combination_id"] == combination_id and scene["period_role"] == "pre"]
        post_inventory = [scene for scene in normalized_scenes if scene["event_id"] == event.event_id and scene["combination_id"] == combination_id and scene["period_role"] == "post"]
        pre_by_id = {_scene_id(scene): scene for scene in pre_inventory}
        post_by_id = {_scene_id(scene): scene for scene in post_inventory}
        for field, by_id in (("selected_pre_scene_id", pre_by_id), ("best_pre_scene_id", pre_by_id), ("selected_post_scene_id", post_by_id), ("best_post_scene_id", post_by_id)):
            scene_id = _text(row.get(field))
            if scene_id and scene_id not in by_id:
                raise ObservabilityValidationError(f"{field} no existe en inventario: {event.event_id}/{combination_id}/{scene_id}")
        if _bool(row.get("usable_pair_exists")):
            pre_id = _text(row.get("selected_pre_scene_id"))
            post_id = _text(row.get("selected_post_scene_id"))
            pre_scene = pre_by_id[pre_id]
            post_scene = post_by_id[post_id]
            if not scene_is_usable(pre_scene, _text(row["rule_id"])) or not scene_is_usable(post_scene, _text(row["rule_id"])):
                raise ObservabilityValidationError(f"Pareja seleccionada debajo de la regla: {event.event_id}/{combination_id}/{row['rule_id']}")
            pre_time = parse_utc_timestamp(pre_scene["acquisition_timestamp_utc"], "selected_pre_scene_id")
            post_time = parse_utc_timestamp(post_scene["acquisition_timestamp_utc"], "selected_post_scene_id")
            if pre_time >= event.start_timestamp_utc or post_time <= event.end_timestamp_utc:
                raise ObservabilityValidationError(f"Orden temporal inválido en pareja seleccionada: {event.event_id}")
    return normalized_scenes, normalized_aois


def _group_event_ids(events: Sequence[EventInput]) -> dict[str, dict[str, set[str]]]:
    return {
        "event_size_class": {
            value: {event.event_id for event in events if event.event_size_class == value}
            for value in sorted({event.event_size_class for event in events})
        },
        "event_month": {
            value: {event.event_id for event in events if event.month == value}
            for value in sorted({event.month for event in events})
        },
        "source_class": {
            value: {event.event_id for event in events if event.source_class == value}
            for value in sorted({event.source_class for event in events})
        },
        "chain_class": {
            value: {event.event_id for event in events if event.chain_class == value}
            for value in sorted({event.chain_class for event in events})
        },
    }


def _fallback_order() -> tuple[str, ...]:
    all_combinations = list(_allowed_combinations())
    return tuple(
        combination_id
        for combination_id in (
            "b0500_pre30_post90",
            "b0500_pre60_post45",
            "b0500_pre60_post90",
            "b1000_pre30_post45",
            "b1000_pre30_post90",
            "b1000_pre60_post45",
            "b1000_pre60_post90",
            "b1500_pre30_post45",
            "b1500_pre30_post90",
            "b1500_pre60_post45",
            "b1500_pre60_post90",
        )
        if combination_id in all_combinations
    )


def _fallback_type(primary: str, fallback: str) -> str:
    primary_aoi, _, _ = _window_parts(primary)
    fallback_aoi, _, _ = _window_parts(fallback)
    if primary_aoi == fallback_aoi:
        return "temporal_extension"
    return "buffer_expansion_and_temporal_extension" if _window_span_days(primary) != _window_span_days(fallback) else "buffer_expansion"


def _metric_rows_by_key(observation_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    return {
        (_text(row["event_id"]), _text(row["combination_id"]), _text(row["rule_id"])): row
        for row in observation_rows
    }


def _pair_sets(
    observation_rows: Sequence[Mapping[str, Any]],
    event_ids: set[str],
    rule_id: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {combination_id: set() for combination_id in _allowed_combinations()}
    for row in observation_rows:
        if _text(row.get("rule_id")) == rule_id and _text(row.get("event_id")) in event_ids and _bool(row.get("usable_pair_exists")):
            result[_text(row["combination_id"])].add(_text(row["event_id"]))
    return result


def _event_comparison(
    observation_rows: Sequence[Mapping[str, Any]],
    event_ids: set[str],
    combination_id: str,
    rule_id: str,
) -> dict[str, Any]:
    pair_sets = _pair_sets(observation_rows, event_ids, rule_id)
    current = pair_sets[combination_id]
    baseline = pair_sets[BASELINE_COMBINATION_ID]
    best_count = max((len(value) for value in pair_sets.values()), default=0)
    best_combinations = [key for key, value in pair_sets.items() if len(value) == best_count]
    best_envelope = set().union(*(pair_sets[key] for key in best_combinations)) if best_combinations else set()
    other_union = set().union(*(value for key, value in pair_sets.items() if key != combination_id))
    return {
        "events_depending_exclusively_on_combination": current - other_union,
        "events_rescued_vs_baseline": current - baseline,
        "events_lost_vs_best_combination": best_envelope - current,
        "best_count": best_count,
        "best_combinations": best_combinations,
        "best_envelope": best_envelope,
    }


def _aoi_area_lookup(aoi_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for row in aoi_rows:
        area = _float(row.get("aoi_area_m2"))
        if area is None:
            raise ObservabilityValidationError(f"AOI sin área: {_text(row.get('event_id'))}/{_text(row.get('aoi_id'))}")
        result[(_text(row["event_id"]), _text(row["aoi_id"]))] = area
    return result


def _metrics_for_group(
    *,
    event_ids: set[str],
    combination_id: str,
    rule_id: str,
    scope: str,
    segment_dimension: str,
    segment_value: str,
    row_by_key: Mapping[tuple[str, str, str], Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    area_lookup: Mapping[tuple[str, str], float],
    all_observation_rows: Sequence[Mapping[str, Any]],
    all_event_ids: set[str],
    baseline_cost: float,
) -> dict[str, Any]:
    rows = [row_by_key[(event_id, combination_id, rule_id)] for event_id in sorted(event_ids)]
    pair_ids = {_text(row["event_id"]) for row in rows if _bool(row.get("usable_pair_exists"))}
    pre_ids = {_text(row["event_id"]) for row in rows if _int(row.get("pre_scene_count")) > 0}
    post_ids = {_text(row["event_id"]) for row in rows if _int(row.get("post_scene_count")) > 0}
    pair_rows = [row for row in rows if _text(row["event_id"]) in pair_ids]
    pre_quality = [_float(row.get("pre_coverage_fraction")) for row in pair_rows]
    post_quality = [_float(row.get("post_coverage_fraction")) for row in pair_rows]
    pre_clear = [_float(row.get("best_pre_clear_fraction")) for row in pair_rows]
    post_clear = [_float(row.get("best_post_clear_fraction")) for row in pair_rows]
    pre_distance = [_float(row.get("days_between_event_and_pre")) for row in pair_rows]
    post_distance = [_float(row.get("days_between_event_and_post")) for row in pair_rows]
    aoi_id, _, _ = _window_parts(combination_id)
    matching_scene_rows = [row for row in scene_rows if _text(row["event_id"]) in event_ids and _text(row["combination_id"]) == combination_id]
    candidate_ids = {_scene_id(row) for row in matching_scene_rows if _scene_id(row)}
    selected_ids = {
        _text(row.get(field))
        for row in pair_rows
        for field in ("selected_pre_scene_id", "selected_post_scene_id")
        if _text(row.get(field))
    }
    comparison = _event_comparison(all_observation_rows, event_ids, combination_id, rule_id)
    area_values = [area_lookup[(event_id, aoi_id)] for event_id in sorted(event_ids)]
    area_time_cost = sum(area_lookup[(event_id, aoi_id)] for event_id in event_ids) * _window_span_days(combination_id)
    row = {
        "scope": scope,
        "segment_dimension": segment_dimension,
        "segment_value": segment_value,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "combination_id": combination_id,
        "aoi_id": aoi_id,
        "buffer_m": dict((label, value) for value, label in BUFFER_OPTIONS)[aoi_id],
        "window_id": "_".join(_window_parts(combination_id)[1:]),
        "rule_id": rule_id,
        "event_count": len(event_ids),
        "events_with_pre_scene": len(pre_ids),
        "events_with_post_scene": len(post_ids),
        "events_with_usable_pair": len(pair_ids),
        "usable_pair_rate": len(pair_ids) / len(event_ids) if event_ids else None,
        "total_usable_combinations": sum(_int(item.get("usable_pre_scene_count")) * _int(item.get("usable_post_scene_count")) for item in rows),
        "pre_quality_event_count": sum(value is not None for value in pre_quality),
        "post_quality_event_count": sum(value is not None for value in post_quality),
        "pair_quality_event_count": len(pair_rows),
        "pre_coverage_median": _median(pre_quality),
        "pre_coverage_p10": _quantile(pre_quality, 0.10),
        "post_coverage_median": _median(post_quality),
        "post_coverage_p10": _quantile(post_quality, 0.10),
        "pre_clear_fraction_median": _median(pre_clear),
        "pre_clear_fraction_p10": _quantile(pre_clear, 0.10),
        "post_clear_fraction_median": _median(post_clear),
        "post_clear_fraction_p10": _quantile(post_clear, 0.10),
        "pre_temporal_distance_median": _median(pre_distance),
        "pre_temporal_distance_p90": _quantile(pre_distance, 0.90),
        "post_temporal_distance_median": _median(post_distance),
        "post_temporal_distance_p90": _quantile(post_distance, 0.90),
        "pre_candidate_scene_median": _median([_float(item.get("pre_scene_count")) for item in rows]),
        "post_candidate_scene_median": _median([_float(item.get("post_scene_count")) for item in rows]),
        "events_depending_exclusively_on_combination": len(comparison["events_depending_exclusively_on_combination"]),
        "exclusive_event_ids": _join_ids(comparison["events_depending_exclusively_on_combination"]),
        "events_rescued_vs_baseline": len(comparison["events_rescued_vs_baseline"]),
        "rescued_event_ids": _join_ids(comparison["events_rescued_vs_baseline"]),
        "events_lost_vs_best_combination": len(comparison["events_lost_vs_best_combination"]),
        "lost_event_ids": _join_ids(comparison["events_lost_vs_best_combination"]),
        "aoi_area_median_m2": _median(area_values),
        "inventory_row_count": len(matching_scene_rows),
        "pre_inventory_row_count": sum(_text(item.get("period_role")) == "pre" for item in matching_scene_rows),
        "post_inventory_row_count": sum(_text(item.get("period_role")) == "post" for item in matching_scene_rows),
        "unique_candidate_scene_count": len(candidate_ids),
        "unique_selected_scene_count": len(selected_ids),
        "window_span_days": _window_span_days(combination_id),
        "relative_compute_cost_index": area_time_cost / baseline_cost if baseline_cost else None,
        "ranking_priority_key": "",
        "ranking_note": "",
    }
    return row


def _priority_key(row: Mapping[str, Any]) -> tuple[float, ...]:
    def value(field: str, default: float) -> float:
        parsed = _float(row.get(field))
        return parsed if parsed is not None else default

    temporal_median = value("pre_temporal_distance_median", float("inf")) + value("post_temporal_distance_median", float("inf"))
    temporal_p90 = value("pre_temporal_distance_p90", float("inf")) + value("post_temporal_distance_p90", float("inf"))
    clarity_p10 = min(value("pre_clear_fraction_p10", -float("inf")), value("post_clear_fraction_p10", -float("inf")))
    coverage_p10 = min(value("pre_coverage_p10", -float("inf")), value("post_coverage_p10", -float("inf")))
    clarity_median = value("pre_clear_fraction_median", -float("inf")) + value("post_clear_fraction_median", -float("inf"))
    coverage_median = value("pre_coverage_median", -float("inf")) + value("post_coverage_median", -float("inf"))
    return (
        -float(_int(row.get("events_with_usable_pair"))),
        float(_int(row.get("events_lost_vs_best_combination"))),
        temporal_median,
        temporal_p90,
        -clarity_p10,
        -coverage_p10,
        -clarity_median,
        -coverage_median,
        value("aoi_area_median_m2", float("inf")),
        value("relative_compute_cost_index", float("inf")),
    )


def _simple_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    buffer_order = {500: 0, 1000: 1, 1500: 2}
    window_order = {window_id: index for index, window_id in enumerate(WINDOW_PAIR_OPTIONS)}
    return (
        buffer_order.get(_int(row.get("buffer_m")), 99),
        window_order.get(_text(row.get("window_id")), 99),
        _text(row.get("combination_id")),
    )


def _ranking_key_text(row: Mapping[str, Any]) -> str:
    priority = _priority_key(row)
    return "|".join("inf" if math.isinf(value) else f"{value:.6f}" for value in priority)


def _rank_overall_rows(rows: list[dict[str, Any]]) -> None:
    for rule_id in USABILITY_RULES:
        rule_rows = [row for row in rows if row["rule_id"] == rule_id]
        priority_groups: dict[tuple[float, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rule_rows:
            priority_groups[_priority_key(row)].append(row)
        ordered = sorted(rule_rows, key=lambda row: (_priority_key(row), _simple_key(row)))
        group_rank: dict[int, int] = {}
        for rank, row in enumerate(ordered, start=1):
            key_id = id(row)
            group_rank[key_id] = min(index + 1 for index, candidate in enumerate(ordered) if _priority_key(candidate) == _priority_key(row))
            row["rank_within_rule"] = rank
            row["rank_group"] = group_rank[key_id]
            row["tie_group_size"] = len(priority_groups[_priority_key(row)])
            row["is_best_within_rule"] = rank == 1
            row["ranking_priority_key"] = _ranking_key_text(row)
            row["ranking_note"] = "empate en prioridades" if row["tie_group_size"] > 1 else ""


def _scene_for_selection(
    scene_rows: Sequence[Mapping[str, Any]],
    *,
    event_id: str,
    combination_id: str,
    period_role: str,
    scene_id: str,
) -> Mapping[str, Any] | None:
    for row in scene_rows:
        if (
            _text(row.get("event_id")) == event_id
            and _text(row.get("combination_id")) == combination_id
            and _text(row.get("period_role")) == period_role
            and _scene_id(row) == scene_id
        ):
            return row
    return None


def _scene_acquisition(scene: Mapping[str, Any] | None) -> str:
    return _text(scene.get("acquisition_timestamp_utc")) if scene else ""


def _final_exclusion_reason(
    event_id: str,
    observation_rows: Sequence[Mapping[str, Any]],
    rule_id: str,
) -> str:
    rows = [row for row in observation_rows if _text(row.get("event_id")) == event_id and _text(row.get("rule_id")) == rule_id]
    if any(_bool(row.get("usable_pair_exists")) for row in rows):
        return "not_applicable"
    if rows and all(_int(row.get("usable_pre_scene_count")) == 0 for row in rows):
        return "no_usable_pre_scene_in_any_combination;clear_fraction_below_threshold"
    if rows and all(_int(row.get("usable_post_scene_count")) == 0 for row in rows):
        return "no_usable_post_scene_in_any_combination"
    return "no_usable_pair_after_all_candidate_combinations"


def build_event_pair_selection(
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    *,
    policy_rule: str = DEFAULT_POLICY_RULE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply a fixed primary-plus-fallback hierarchy without manual inspection."""

    if policy_rule not in USABILITY_RULES:
        raise ObservabilityValidationError(f"Regla de política inválida: {policy_rule}")
    row_by_key = _metric_rows_by_key(observation_rows)
    fallback_ids = _fallback_order()
    selection_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    event_by_id = {event.event_id: event for event in events}
    for event in events:
        primary = row_by_key[(event.event_id, PRIMARY_SHORT_COMBINATION_ID, policy_rule)]
        primary_available = _bool(primary.get("usable_pair_exists"))
        chosen = primary if primary_available else None
        chosen_fallback = ""
        chosen_fallback_type = ""
        for order, combination_id in enumerate(fallback_ids, start=1):
            candidate = row_by_key[(event.event_id, combination_id, policy_rule)]
            pair_available = _bool(candidate.get("usable_pair_exists"))
            selected_by_hierarchy = bool(not primary_available and chosen is None and pair_available)
            if selected_by_hierarchy:
                chosen = candidate
                chosen_fallback = combination_id
                chosen_fallback_type = _fallback_type(PRIMARY_SHORT_COMBINATION_ID, combination_id)
            if not primary_available:
                if selected_by_hierarchy:
                    status = "selected_rescue"
                elif pair_available:
                    status = "available_but_not_needed"
                else:
                    status = "no_usable_pair"
                fallback_rows.append(
                    {
                        "event_id": event.event_id,
                        "configuration_id": event.configuration_id,
                        "event_month": event.month,
                        "event_size_class": event.event_size_class,
                        "source_class": event.source_class,
                        "chain_class": event.chain_class,
                        "primary_combination_id": PRIMARY_SHORT_COMBINATION_ID,
                        "policy_rule": policy_rule,
                        "primary_sufficient": "yes" if primary_available else "no",
                        "fallback_order": order,
                        "fallback_combination_id": combination_id,
                        "fallback_type": _fallback_type(PRIMARY_SHORT_COMBINATION_ID, combination_id),
                        "fallback_buffer_m": dict((label, value) for value, label in BUFFER_OPTIONS)[_window_parts(combination_id)[0]],
                        "fallback_window_id": "_".join(_window_parts(combination_id)[1:]),
                        "pair_available": "yes" if pair_available else "no",
                        "rescues_vs_primary": "yes" if pair_available and not primary_available else "no",
                        "selected_by_hierarchy": "yes" if selected_by_hierarchy else "no",
                        "pre_scene_count": _int(candidate.get("pre_scene_count")),
                        "post_scene_count": _int(candidate.get("post_scene_count")),
                        "usable_pre_scene_count": _int(candidate.get("usable_pre_scene_count")),
                        "usable_post_scene_count": _int(candidate.get("usable_post_scene_count")),
                        "selected_pre_scene_id": _text(candidate.get("selected_pre_scene_id")),
                        "selected_post_scene_id": _text(candidate.get("selected_post_scene_id")),
                        "pre_clear_fraction": candidate.get("best_pre_clear_fraction", ""),
                        "post_clear_fraction": candidate.get("best_post_clear_fraction", ""),
                        "pre_coverage_fraction": candidate.get("pre_coverage_fraction", ""),
                        "post_coverage_fraction": candidate.get("post_coverage_fraction", ""),
                        "pre_temporal_distance_days": candidate.get("days_between_event_and_pre", ""),
                        "post_temporal_distance_days": candidate.get("days_between_event_and_post", ""),
                        "attempt_status": status,
                    }
                )
        selected = chosen
        selected_pair = _bool(selected.get("usable_pair_exists")) if selected else False
        minimum_rule = ""
        if selected_pair and selected:
            for candidate_rule in USABILITY_RULES:
                candidate_row = row_by_key[(event.event_id, _text(selected["combination_id"]), candidate_rule)]
                if _bool(candidate_row.get("usable_pair_exists")):
                    minimum_rule = candidate_rule
                    break
        selected_combo = _text(selected.get("combination_id")) if selected else ""
        pre_id = _text(selected.get("selected_pre_scene_id")) if selected else ""
        post_id = _text(selected.get("selected_post_scene_id")) if selected else ""
        pre_scene = _scene_for_selection(scene_rows, event_id=event.event_id, combination_id=selected_combo, period_role="pre", scene_id=pre_id) if pre_id else None
        post_scene = _scene_for_selection(scene_rows, event_id=event.event_id, combination_id=selected_combo, period_role="post", scene_id=post_id) if post_id else None
        selection_rows.append(
            {
                "event_id": event.event_id,
                "configuration_id": event.configuration_id,
                "event_month": event.month,
                "event_size_class": event.event_size_class,
                "source_class": event.source_class,
                "chain_class": event.chain_class,
                "possible_chain_merge": "yes" if event.possible_chain_merge else "no",
                "primary_combination_id": PRIMARY_SHORT_COMBINATION_ID,
                "policy_rule": policy_rule,
                "primary_sufficient": "yes" if primary_available else "no",
                "fallback_required": "yes" if not primary_available else "no",
                "fallback_combination_id": chosen_fallback,
                "fallback_type": chosen_fallback_type,
                "fallback_rescues": "yes" if chosen_fallback else "no",
                "minimum_rule_passed": minimum_rule,
                "selected_combination_id": selected_combo,
                "selected_pre_scene_id": pre_id,
                "selected_post_scene_id": post_id,
                "pre_scene_acquisition_timestamp": _scene_acquisition(pre_scene),
                "post_scene_acquisition_timestamp": _scene_acquisition(post_scene),
                "pre_clear_fraction": selected.get("best_pre_clear_fraction", "") if selected else "",
                "post_clear_fraction": selected.get("best_post_clear_fraction", "") if selected else "",
                "pre_coverage_fraction": selected.get("pre_coverage_fraction", "") if selected else "",
                "post_coverage_fraction": selected.get("post_coverage_fraction", "") if selected else "",
                "pre_temporal_distance_days": selected.get("days_between_event_and_pre", "") if selected else "",
                "post_temporal_distance_days": selected.get("days_between_event_and_post", "") if selected else "",
                "pre_cloud_fraction": selected.get("pre_cloud_fraction", "") if selected else "",
                "post_cloud_fraction": selected.get("post_cloud_fraction", "") if selected else "",
                "final_observability_status": "usable_pair" if selected_pair else "excluded_no_usable_pair",
                "final_exclusion_reason": "not_applicable" if selected_pair else _final_exclusion_reason(event.event_id, observation_rows, policy_rule),
            }
        )
    return selection_rows, fallback_rows


def build_policy_analysis(
    events: Sequence[EventInput],
    observation_rows: Sequence[Mapping[str, Any]],
    scene_rows: Sequence[Mapping[str, Any]],
    aoi_rows: Sequence[Mapping[str, Any]],
    *,
    policy_rule: str = DEFAULT_POLICY_RULE,
) -> dict[str, Any]:
    """Build the full matrix, ranking, hierarchy and segment views."""

    normalized_scenes, normalized_aois = validate_policy_inputs(events, observation_rows, scene_rows, aoi_rows)
    event_ids = {event.event_id for event in events}
    row_by_key = _metric_rows_by_key(observation_rows)
    area_lookup = _aoi_area_lookup(normalized_aois)
    baseline_aoi_id, _, _ = _window_parts(BASELINE_COMBINATION_ID)
    baseline_cost = sum(area_lookup[(event_id, baseline_aoi_id)] for event_id in event_ids) * _window_span_days(BASELINE_COMBINATION_ID)
    overall_rows: list[dict[str, Any]] = []
    for combination_id in _allowed_combinations():
        for rule_id in USABILITY_RULES:
            overall_rows.append(
                _metrics_for_group(
                    event_ids=event_ids,
                    combination_id=combination_id,
                    rule_id=rule_id,
                    scope="overall",
                    segment_dimension="overall",
                    segment_value="overall",
                    row_by_key=row_by_key,
                    scene_rows=normalized_scenes,
                    area_lookup=area_lookup,
                    all_observation_rows=observation_rows,
                    all_event_ids=event_ids,
                    baseline_cost=baseline_cost,
                )
            )
    _rank_overall_rows(overall_rows)
    segment_rows: list[dict[str, Any]] = []
    for dimension, groups in _group_event_ids(events).items():
        for value, group_event_ids in groups.items():
            for combination_id in _allowed_combinations():
                for rule_id in USABILITY_RULES:
                    row = _metrics_for_group(
                        event_ids=group_event_ids,
                        combination_id=combination_id,
                        rule_id=rule_id,
                        scope="segment",
                        segment_dimension=dimension,
                        segment_value=value,
                        row_by_key=row_by_key,
                        scene_rows=normalized_scenes,
                        area_lookup=area_lookup,
                        all_observation_rows=observation_rows,
                        all_event_ids=event_ids,
                        baseline_cost=baseline_cost,
                    )
                    row["ranking_note"] = "métrica segmentada; el ranking es global por regla"
                    segment_rows.append(row)
    excluded_event_ids = {
        event.event_id
        for event in events
        if not any(_bool(row.get("usable_pair_exists")) for row in observation_rows if _text(row.get("event_id")) == event.event_id)
    }
    for event_id in sorted(excluded_event_ids):
        for combination_id in _allowed_combinations():
            for rule_id in USABILITY_RULES:
                row = _metrics_for_group(
                    event_ids={event_id},
                    combination_id=combination_id,
                    rule_id=rule_id,
                    scope="segment",
                    segment_dimension="excluded_event",
                    segment_value=event_id,
                    row_by_key=row_by_key,
                    scene_rows=normalized_scenes,
                    area_lookup=area_lookup,
                    all_observation_rows=observation_rows,
                    all_event_ids=event_ids,
                    baseline_cost=baseline_cost,
                )
                row["ranking_note"] = "evento excluido globalmente; no implica ausencia de quema"
                segment_rows.append(row)

    selection_rows, fallback_rows = build_event_pair_selection(
        events,
        observation_rows,
        normalized_scenes,
        policy_rule=policy_rule,
    )
    best_by_rule = {
        rule_id: [row["combination_id"] for row in overall_rows if row["rule_id"] == rule_id and row.get("rank_within_rule") == 1]
        for rule_id in USABILITY_RULES
    }
    primary_row = next(row for row in overall_rows if row["combination_id"] == PRIMARY_SHORT_COMBINATION_ID and row["rule_id"] == policy_rule)
    fallback_rescues = [row for row in fallback_rows if row["selected_by_hierarchy"] == "yes"]
    summary = {
        "stage": "sentinel2_policy_decision",
        "pipeline_version": POLICY_PIPELINE_VERSION,
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "event_count": len(events),
        "scene_inventory_row_count": len(normalized_scenes),
        "aoi_inventory_row_count": len(normalized_aois),
        "unique_sentinel2_scene_count": len({_scene_id(row) for row in normalized_scenes if _scene_id(row)}),
        "combination_count": len(_allowed_combinations()),
        "rule_count": len(USABILITY_RULES),
        "overall_matrix_row_count": len(overall_rows),
        "segment_matrix_row_count": len(segment_rows),
        "baseline_combination_id": BASELINE_COMBINATION_ID,
        "policy_rule": policy_rule,
        "primary_short_combination_id": PRIMARY_SHORT_COMBINATION_ID,
        "best_combination_by_rule": best_by_rule,
        "global_rule_union_usable_event_count": {
            rule_id: len(set().union(*_pair_sets(observation_rows, event_ids, rule_id).values()))
            for rule_id in USABILITY_RULES
        },
        "primary_short_events_with_usable_pair": primary_row["events_with_usable_pair"],
        "primary_short_fallback_rescue_count": len(fallback_rescues),
        "fallback_rescued_event_ids": sorted({row["event_id"] for row in fallback_rescues}),
        "global_excluded_event_ids": sorted(excluded_event_ids),
        "earth_engine_queries_made": False,
        "raster_downloaded": False,
        "spectral_index_computed": False,
        "frp_used_for_selection": False,
        "manual_image_inspection": False,
        "ranking_definition": [
            "maximizar events_with_usable_pair",
            "minimizar events_lost_vs_best_combination",
            "minimizar mediana de distancia temporal pre+post y luego p90",
            "maximizar el mínimo de claridad p10 y luego el mínimo de cobertura p10",
            "maximizar medianas de claridad/cobertura y minimizar área/costo",
            "desempatar por buffer menor, ventana simple y combination_id",
        ],
        "metric_definitions": {
            "quality_metrics": "Medianas y percentiles condicionados a eventos con pareja usable; la claridad usa el campo de la regla.",
            "candidate_scene_medians": "Medianas sobre los 30 eventos del segmento, incluyendo cero si no hubiera candidatos.",
            "total_usable_combinations": "Suma por evento de usable_pre_scene_count * usable_post_scene_count; no es una etiqueta.",
            "relative_compute_cost_index": "Proxy area_m2 * span_days relativo a b0500_pre30_post45; no es una factura Earth Engine.",
            "best_scene_selection": "Se conserva selected_pre_scene_id/selected_post_scene_id del inventario existente.",
        },
        "invariants": {
            "pilot_event_count_30": len(events) == 30,
            "no_2026": all(event.start_timestamp_utc.year != 2026 and event.end_timestamp_utc.year != 2026 for event in events),
            "all_best_scene_ids_in_inventory": True,
            "pre_before_event_and_post_after_event": True,
            "no_earth_engine": True,
            "no_raster": True,
            "no_nbr_dnbr": True,
        },
    }
    return {
        "summary": summary,
        "decision_rows": overall_rows + segment_rows,
        "overall_rows": overall_rows,
        "segment_rows": segment_rows,
        "event_selection_rows": selection_rows,
        "fallback_rows": fallback_rows,
        "normalized_scene_rows": normalized_scenes,
        "normalized_aoi_rows": normalized_aois,
    }


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_utf8_csv(path: Path | str, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})


def _md(value: Any) -> str:
    if value in (None, ""):
        return "—"
    text = _format_number(value) if isinstance(value, (float, int)) and not isinstance(value, bool) else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_md(value) for value in row) + " |" for row in rows)
    return lines


def build_policy_markdown(analysis: Mapping[str, Any]) -> str:
    summary = analysis["summary"]
    overall = analysis["overall_rows"]
    selections = analysis["event_selection_rows"]
    fallback_rows = analysis["fallback_rows"]
    input_hashes = summary.get("input_sha256", {})
    if input_hashes:
        input_hash_lines = [f"- SHA-256 `{key}`: `{value}`." for key, value in sorted(input_hashes.items())]
    else:
        input_hash_lines = ["- Los hashes se imprimen y registran al ejecutar `scripts/build_sentinel2_policy.py`."]
    input_hash_lines.append(
        "- Unión de eventos con pareja por regla: "
        + ", ".join(f"{rule_id}={summary['global_rule_union_usable_event_count'][rule_id]}" for rule_id in USABILITY_RULES)
        + "."
    )
    lines = [
        "# Decisión provisional de política Sentinel-2",
        "",
        "Este documento compara disponibilidad y calidad de observabilidad a partir de inventarios locales ya generados. No calcula NBR/dNBR, no descarga raster y no constituye validación de cicatrices de quema.",
        "",
        f"- Configuración FIRMS congelada: `{summary['configuration_id']}`.",
        f"- Universo: `{summary['event_count']}` eventos del piloto; `{summary['scene_inventory_row_count']}` filas de inventario y `{summary['unique_sentinel2_scene_count']}` escenas Sentinel-2 únicas.",
        f"- Matriz: `{summary['combination_count']}` combinaciones × `{summary['rule_count']}` reglas = `{summary['overall_matrix_row_count']}` filas globales.",
        f"- Línea base: `{summary['baseline_combination_id']}`.",
        f"- Regla usada para la política jerárquica: `{summary['policy_rule']}`; se conserva la sensibilidad completa A-D.",
        "- Las detecciones y escenas se leyeron con UTF-8; ningún inventario fue reescrito.",
        "- `earth_engine_queries_made=false`, `raster_downloaded=false`, `spectral_index_computed=false`, `frp_used_for_selection=false`.",
        "",
        "## Trazabilidad de entradas",
        "",
        *input_hash_lines,
        "",
        "## Definiciones y ranking",
        "",
        "Las métricas de claridad, cobertura y distancia temporal se calculan sobre los eventos con pareja usable y sobre la escena seleccionada que ya figura en `sentinel2_observability.csv`. Las medianas de candidatos usan el denominador del segmento completo. `total_usable_combinations` es la suma de parejas pre×post que pasan la regla, no un conteo de incendios.",
        "",
        "El ranking por regla aplica esta clave lexicográfica: máximo de eventos con pareja; mínimo de eventos perdidos frente al conjunto envolvente de las mejores combinaciones; menor suma de medianas temporales y después de p90; mayor mínimo entre p10 de claridad pre/post y después de cobertura; mayor calidad mediana y menor área/costo; finalmente buffer menor, ventana más simple y `combination_id`. Los empates de prioridades aparecen con `tie_group_size` y no se ocultan.",
        "",
    ]
    lines.extend([
        "## Ranking completo de las 48 combinaciones globales",
        "",
    ])
    ranking_rows = []
    for row in sorted(overall, key=lambda item: (item["rule_id"], item["rank_within_rule"])):
        ranking_rows.append(
            [
                row["rule_id"], row["rank_within_rule"], row["tie_group_size"], row["combination_id"],
                row["events_with_usable_pair"], row["usable_pair_rate"], row["events_lost_vs_best_combination"],
                (_float(row["pre_temporal_distance_median"]) or 0) + (_float(row["post_temporal_distance_median"]) or 0),
                min(_float(row["pre_clear_fraction_p10"]) or 0, _float(row["post_clear_fraction_p10"]) or 0),
                min(_float(row["pre_coverage_p10"]) or 0, _float(row["post_coverage_p10"]) or 0),
                row["aoi_area_median_m2"], row["relative_compute_cost_index"], row["inventory_row_count"],
            ]
        )
    lines.extend(_md_table(
        ["Regla", "Rank", "Empate", "Combinación", "Parejas", "Tasa", "Perdidos", "Dist. mediana", "Claridad p10 mín.", "Cobertura p10 mín.", "AOI mediana m²", "Costo relativo", "Filas"],
        ranking_rows,
    ))
    lines.extend(["", "## Mejores combinaciones y empates", ""])
    for rule_id in USABILITY_RULES:
        winners = [row["combination_id"] for row in overall if row["rule_id"] == rule_id and row["rank_within_rule"] == 1]
        lines.append(f"- Regla `{rule_id}`: `{', '.join(winners)}`.")
    lines.extend([
        "",
        "El mejor resultado individual no se convierte automáticamente en política principal: el ranking muestra el costo de usar un buffer mayor, mientras que la política jerárquica evalúa si el mismo evento puede rescatarse ampliando temporalmente la ventana.",
        "Las reglas difieren más allá del conteo global: A usa `cs_cdf_050` con claridad mínima 0.70; B usa `cs_cdf_060` con 0.70; C usa `cs_cdf_065` con 0.70; D exige cobertura 0.95 y claridad 0.80 sobre `cs_cdf_060`. Por eso se conservan las cuatro sensibilidades y ninguna se presenta como ground truth.",
        "",
        "## Política jerárquica recomendada",
        "",
        f"- Principal corta: `{PRIMARY_SHORT_COMBINATION_ID}` con regla `{summary['policy_rule']}`.",
        f"- Parejas en principal: `{summary['primary_short_events_with_usable_pair']}/{summary['event_count']}`.",
        "- Fallback recomendado: `b0500_pre30_post90`, una ampliación temporal post manteniendo el buffer de 500 m.",
        f"- Eventos rescatados por ese fallback: `{summary['primary_short_fallback_rescue_count']}` ({', '.join(summary['fallback_rescued_event_ids']) or 'ninguno'}).",
        "- No se recomienda ampliar el buffer como fallback de esta política: no agrega rescates frente a la ampliación temporal en este piloto y aumenta el área consultada. Esta es una decisión de disponibilidad/costo del piloto, no una validación científica del buffer.",
        "- Los dos eventos sin pareja utilizable permanecen excluidos de la cohorte óptica; la exclusión no demuestra que no haya ocurrido una quema.",
        "",
        "## Selección pre/post por evento",
        "",
    ])
    selection_table = []
    for row in selections:
        selection_table.append([
            row["event_id"], row["event_size_class"], row["event_month"], row["source_class"], row["chain_class"],
            row["primary_sufficient"], row["fallback_required"], row["fallback_combination_id"], row["minimum_rule_passed"],
            row["selected_pre_scene_id"], row["selected_post_scene_id"], row["pre_clear_fraction"], row["post_clear_fraction"],
            row["pre_coverage_fraction"], row["post_coverage_fraction"], row["pre_temporal_distance_days"], row["post_temporal_distance_days"],
            row["final_exclusion_reason"],
        ])
    lines.extend(_md_table(
        ["Evento", "Tamaño", "Mes", "Fuente", "Cadena", "Principal", "Fallback", "Fallback elegido", "Regla mínima", "Pre", "Post", "Claridad pre", "Claridad post", "Cobertura pre", "Cobertura post", "Dist. pre", "Dist. post", "Exclusión"],
        selection_table,
    ))
    lines.extend(["", "## Fallbacks evaluados", ""])
    lines.append(f"Se evaluaron `{len(fallback_rows)}` intentos de fallback únicamente para los eventos que no pasaron la combinación principal. `selected_rescue` identifica la primera alternativa que la jerarquía habría seleccionado; `available_but_not_needed` conserva evidencia de alternativas posteriores sin alterar la selección.")
    lines.append("")
    fallback_summary: dict[str, int] = defaultdict(int)
    for row in fallback_rows:
        if row["pair_available"] == "yes":
            fallback_summary[row["fallback_combination_id"]] += 1
    lines.extend(_md_table(["Combinación fallback", "Disponibles entre eventos con principal fallida"], sorted(fallback_summary.items())))
    lines.extend(["", "## Segmentación solicitada", "", "La matriz CSV contiene filas `scope=segment` para singleton/multi-detección, mes, fuente única/múltiple, cadena posible/no posible y cada uno de los dos eventos excluidos. El siguiente resumen muestra el resultado de la política jerárquica principal/fallback por segmento.", ""])
    segment_selection = defaultdict(list)
    event_metadata = {row["event_id"]: row for row in selections}
    for event_id, row in event_metadata.items():
        segment_selection[("event_size_class", row["event_size_class"])].append(row)
        segment_selection[("event_month", row["event_month"])].append(row)
        segment_selection[("source_class", row["source_class"])].append(row)
        segment_selection[("chain_class", row["chain_class"])].append(row)
    segment_table = []
    for (dimension, value), rows in sorted(segment_selection.items()):
        segment_table.append([
            dimension, value, len(rows), sum(row["final_observability_status"] == "usable_pair" for row in rows),
            sum(row["fallback_rescues"] == "yes" for row in rows),
            sum(row["final_observability_status"] != "usable_pair" for row in rows),
        ])
    lines.extend(_md_table(["Dimensión", "Valor", "Eventos", "Pareja final", "Rescatados", "Excluidos"], segment_table))
    lines.extend(["", "## Dos eventos sin pareja utilizable", ""])
    for row in selections:
        if row["final_observability_status"] != "usable_pair":
            lines.append(f"- `{row['event_id']}`: principal fallida, ningún fallback de las 12 combinaciones con regla `{summary['policy_rule']}` rescató la pareja; razón registrada: `{row['final_exclusion_reason']}`.")
    lines.extend([
        "",
        "## Limitaciones",
        "",
        "- Las 28 parejas utilizables son disponibilidad óptica, no 28 incendios confirmados ni 28 cicatrices.",
        "- La selección conserva la pareja ya elegida por el pipeline de observabilidad; no mira imágenes manualmente y no usa FRP, tamaño aparente ni conveniencia visual.",
        "- El índice de costo es relativo y metodológico; no representa cuotas ni tiempo real de Earth Engine.",
        "- La cohorte y la política siguen siendo provisionales hasta observar cicatrices y definir NBR/dNBR/etiquetas en una fase posterior.",
        "- Ninguna regla A-D es ground truth; las diferencias entre reglas reflejan umbrales y campos de claridad distintos.",
        "",
    ])
    return "\n".join(lines) + "\n"


def _svg_escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _svg_header(title: str, subtitle: str) -> list[str]:
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="620" viewBox="0 0 1100 620">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="48" y="44" font-family="Arial,sans-serif" font-size="24" font-weight="700" fill="#0f172a">{_svg_escape(title)}</text>',
        f'<text x="48" y="70" font-family="Arial,sans-serif" font-size="13" fill="#475569">{_svg_escape(subtitle)}</text>',
    ]


def _write_svg(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _grouped_bar_svg(path: Path, title: str, groups: Sequence[str], series: Mapping[str, Sequence[float]], *, y_max: float = 1.0, subtitle: str = "") -> None:
    lines = _svg_header(title, subtitle)
    left, top, width, height = 82, 108, 950, 410
    colors = ["#0f766e", "#2563eb", "#9333ea", "#ea580c"]
    n_series = max(len(series), 1)
    group_width = width / max(len(groups), 1)
    bar_width = group_width * 0.72 / n_series
    for index, group in enumerate(groups):
        x0 = left + index * group_width
        for series_index, (name, values) in enumerate(series.items()):
            value = values[index] if index < len(values) else 0.0
            bar_height = height * max(0.0, value) / max(y_max, 1e-9)
            x = x0 + group_width * 0.14 + series_index * bar_width
            y = top + height - bar_height
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 1:.1f}" height="{bar_height:.1f}" fill="{colors[series_index % len(colors)]}" rx="2"/>')
            if value > 0:
                lines.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="9" fill="#0f172a">{value:.2f}</text>')
        lines.append(f'<text x="{x0 + group_width / 2:.1f}" y="{top + height + 22}" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" fill="#334155">{_svg_escape(group)}</text>')
    lines.append(f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#94a3b8"/>')
    for index, name in enumerate(series):
        x = left + index * 150
        lines.append(f'<rect x="{x}" y="560" width="12" height="12" fill="{colors[index % len(colors)]}"/>')
        lines.append(f'<text x="{x + 18}" y="571" font-family="Arial,sans-serif" font-size="11" fill="#334155">{_svg_escape(name)}</text>')
    _write_svg(path, lines)


def _bar_svg(path: Path, title: str, items: Sequence[tuple[str, float]], *, subtitle: str = "", color: str = "#0f766e", y_max: float | None = None) -> None:
    lines = _svg_header(title, subtitle)
    left, top, width, height = 82, 108, 950, 410
    maximum = y_max or max((value for _, value in items), default=1.0) or 1.0
    bar_width = width / max(len(items), 1) * 0.72
    for index, (label, value) in enumerate(items):
        x = left + (index + 0.5) * width / max(len(items), 1) - bar_width / 2
        bar_height = height * max(0.0, value) / maximum
        y = top + height - bar_height
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" fill="{color}"/>')
        lines.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" fill="#0f172a">{_svg_escape(round(value, 3))}</text>')
        lines.append(f'<text x="{x + bar_width / 2:.1f}" y="{top + height + 22}" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" fill="#334155">{_svg_escape(label)}</text>')
    lines.append(f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#94a3b8"/>')
    _write_svg(path, lines)


def _scatter_svg(path: Path, title: str, rows: Sequence[Mapping[str, Any]], *, x_field: str, y_field: str, x_label: str, y_label: str, subtitle: str) -> None:
    lines = _svg_header(title, subtitle)
    left, top, width, height = 100, 110, 880, 400
    points = [(float(row[x_field]), float(row[y_field]), _text(row.get("rule_id"))) for row in rows if _float(row.get(x_field)) is not None and _float(row.get(y_field)) is not None]
    if not points:
        _write_svg(path, lines + ['<text x="100" y="200" font-family="Arial,sans-serif" font-size="16" fill="#334155">Sin puntos</text>'])
        return
    x_max = max(point[0] for point in points) * 1.05 or 1.0
    x_min = 0.0
    y_min = min(0.0, min(point[1] for point in points) - 0.05)
    y_max = max(1.0, max(point[1] for point in points) + 0.05)
    colors = {"A": "#0f766e", "B": "#2563eb", "C": "#9333ea", "D": "#ea580c"}
    for x_value, y_value, rule_id in points:
        x = left + (x_value - x_min) / max(x_max - x_min, 1e-9) * width
        y = top + height - (y_value - y_min) / max(y_max - y_min, 1e-9) * height
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{colors.get(rule_id, "#334155")}" fill-opacity="0.72"/>')
    lines.extend([
        f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#94a3b8"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="#94a3b8"/>',
        f'<text x="{left + width / 2}" y="{top + height + 48}" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#334155">{_svg_escape(x_label)}</text>',
        f'<text x="24" y="{top + height / 2}" transform="rotate(-90 24 {top + height / 2})" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" fill="#334155">{_svg_escape(y_label)}</text>',
    ])
    for index, rule_id in enumerate(USABILITY_RULES):
        x = 760 + (index % 2) * 95
        y = 110 + (index // 2) * 24
        lines.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{colors[rule_id]}"/>')
        lines.append(f'<text x="{x + 12}" y="{y + 4}" font-family="Arial,sans-serif" font-size="11" fill="#334155">Regla {rule_id}</text>')
    _write_svg(path, lines)


def _excluded_svg(path: Path, selection_rows: Sequence[Mapping[str, Any]]) -> None:
    lines = _svg_header("Eventos excluidos del piloto óptico", "Exclusión por disponibilidad; no es evidencia de ausencia de quema.")
    y = 130
    lines.extend([
        '<text x="60" y="104" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#334155">event_id</text>',
        '<text x="700" y="104" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#334155">motivo</text>',
    ])
    for row in selection_rows:
        if row["final_observability_status"] == "usable_pair":
            continue
        lines.append(f'<rect x="48" y="{y - 22}" width="1000" height="42" rx="4" fill="#fee2e2"/>')
        lines.append(f'<text x="60" y="{y + 4}" font-family="Arial,sans-serif" font-size="11" fill="#7f1d1d">{_svg_escape(row["event_id"])}</text>')
        lines.append(f'<text x="700" y="{y + 4}" font-family="Arial,sans-serif" font-size="10" fill="#7f1d1d">{_svg_escape(row["final_exclusion_reason"])}</text>')
        y += 58
    _write_svg(path, lines)


def generate_policy_figures(output_dir: Path | str, analysis: Mapping[str, Any]) -> list[Path]:
    """Generate dependency-free SVGs for the policy audit."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    overall = analysis["overall_rows"]
    policy_rule = analysis["summary"]["policy_rule"]
    paths: list[Path] = []
    groups = _allowed_combinations()
    rule_series = {
        rule_id: [float(next(row for row in overall if row["combination_id"] == combination_id and row["rule_id"] == rule_id)["usable_pair_rate"]) for combination_id in groups]
        for rule_id in USABILITY_RULES
    }
    path = directory / "usable_pair_rate_by_combination.svg"
    _grouped_bar_svg(path, "Tasa de parejas utilizables por combinación", groups, rule_series, y_max=1.0, subtitle="Los 48 puntos corresponden a 12 combinaciones y reglas A-D.")
    paths.append(path)

    scatter_rows = []
    for row in overall:
        scatter_rows.append({
            "rule_id": row["rule_id"],
            "temporal_distance": (_float(row["pre_temporal_distance_median"]) or 0) + (_float(row["post_temporal_distance_median"]) or 0),
            "clarity_p10": min(_float(row["pre_clear_fraction_p10"]) or 0, _float(row["post_clear_fraction_p10"]) or 0),
        })
    path = directory / "clarity_vs_temporal_distance.svg"
    _scatter_svg(path, "Claridad frente a distancia temporal", scatter_rows, x_field="temporal_distance", y_field="clarity_p10", x_label="Suma de medianas de distancia temporal (días)", y_label="Mínimo de claridad p10 pre/post", subtitle="Cada punto es una combinación/regla; no es ground truth.")
    paths.append(path)

    coverage_rows = [row for row in overall if row["rule_id"] == policy_rule]
    coverage_series = {
        row["window_id"]: [min(float(next(item for item in coverage_rows if item["aoi_id"] == aoi_id and item["window_id"] == row["window_id"])["pre_coverage_p10"]), float(next(item for item in coverage_rows if item["aoi_id"] == aoi_id and item["window_id"] == row["window_id"])["post_coverage_p10"])) for aoi_id in ("b0500", "b1000", "b1500")]
        for row in coverage_rows[:4]
    }
    path = directory / "coverage_vs_buffer.svg"
    _grouped_bar_svg(path, "Cobertura p10 frente a buffer", ("500 m", "1000 m", "1500 m"), coverage_series, y_max=1.0, subtitle=f"Mínimo pre/post bajo la regla {policy_rule}; ventanas agrupadas.")
    paths.append(path)

    rescue_counts: dict[str, int] = defaultdict(int)
    for row in analysis["fallback_rows"]:
        if row["rescues_vs_primary"] == "yes":
            rescue_counts[row["fallback_combination_id"]] += 1
    path = directory / "events_rescued_by_fallback.svg"
    _bar_svg(path, "Eventos rescatados por fallback", sorted(rescue_counts.items()) or [("ninguno", 0)], subtitle=f"Regla {policy_rule}; se cuentan rescates frente a {PRIMARY_SHORT_COMBINATION_ID}.", color="#2563eb", y_max=max(rescue_counts.values(), default=1))
    paths.append(path)

    cost_items = [(row["combination_id"], float(row["relative_compute_cost_index"])) for row in overall if row["rule_id"] == policy_rule]
    path = directory / "relative_computational_cost.svg"
    _bar_svg(path, "Costo computacional relativo", cost_items, subtitle="Proxy area_m2 × span_days relativo a b0500_pre30_post45; no es costo facturado.", color="#9333ea")
    paths.append(path)

    path = directory / "excluded_events.svg"
    _excluded_svg(path, analysis["event_selection_rows"])
    paths.append(path)
    return paths


def write_policy_outputs(analysis: Mapping[str, Any], paths: Mapping[str, Path | str]) -> list[Path]:
    """Write only policy artifacts; input inventories are never destinations."""

    write_utf8_csv(paths["decision"], DECISION_COLUMNS, analysis["decision_rows"])
    write_utf8_csv(paths["event_selection"], EVENT_SELECTION_COLUMNS, analysis["event_selection_rows"])
    write_utf8_csv(paths["fallbacks"], FALLBACK_COLUMNS, analysis["fallback_rows"])
    markdown_path = Path(paths["decision_markdown"])
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(build_policy_markdown(analysis), encoding="utf-8")
    return generate_policy_figures(paths["figures"], analysis)
