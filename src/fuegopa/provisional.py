"""Freeze provisional clustering outputs and select an optical-observability pilot.

The functions in this module intentionally do not import or execute the
clustering algorithm.  They consume the already generated CSVs for the
approved provisional configuration and create auditable downstream artifacts.
No Sentinel-2 query, spectral index, label, or environmental variable is
computed here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FROZEN_CONFIGURATION_ID = "r1500_t06"
FROZEN_RADIUS_M = 1500
FROZEN_TIME_WINDOW_HOURS = 6
EXPECTED_DETECTION_COUNT = 1185
EXPECTED_EVENT_COUNT = 611
PILOT_SAMPLE_SIZE = 30
PILOT_SAMPLE_SEED = 20260715
PIPELINE_VERSION = "fuegopa-provisional-observability-v1"

FROZEN_MEMBERSHIP_COLUMNS = (
    "configuration_id",
    "event_id",
    "detection_id",
    "timestamp_utc",
    "latitude",
    "longitude",
    "firms_source",
    "satellite",
    "instrument",
    "frp",
    "confidence_raw",
    "daynight",
    "raw_file",
    "raw_sha256",
)

FROZEN_EVENT_COLUMNS = (
    "event_id",
    "configuration_id",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "duration_hours",
    "detection_count",
    "source_count",
    "sources",
    "satellite_count",
    "satellites",
    "centroid_latitude",
    "centroid_longitude",
    "min_latitude",
    "min_longitude",
    "max_latitude",
    "max_longitude",
    "spatial_extent_m",
    "maximum_centroid_distance_m",
    "maximum_temporal_gap_hours",
    "calendar_day_count",
    "frp_min",
    "frp_max",
    "frp_mean",
    "frp_median",
    "frp_sum",
    "confidence_category_counts",
    "day_fraction",
    "night_fraction",
    "possible_chain_merge",
    "chain_merge_reasons",
)

PILOT_COLUMNS = (
    "sampling_rank",
    "event_id",
    "configuration_id",
    "start_timestamp_utc",
    "end_timestamp_utc",
    "detection_count",
    "source_count",
    "sources",
    "possible_chain_merge",
    "month",
    "event_size_class",
    "multi_detection_quartile",
    "source_class",
    "chain_class",
)

OBSERVABILITY_COLUMNS = (
    "event_id",
    "configuration_id",
    "aoi_method",
    "aoi_buffer_m",
    "pre_window_start",
    "pre_window_end",
    "post_window_start",
    "post_window_end",
    "pre_scene_count",
    "post_scene_count",
    "usable_pre_scene_count",
    "usable_post_scene_count",
    "selected_pre_scene_id",
    "selected_post_scene_id",
    "pre_cloud_fraction",
    "post_cloud_fraction",
    "pre_coverage_fraction",
    "post_coverage_fraction",
    "observability_status",
    "exclusion_reason",
    "processing_timestamp_utc",
    "pipeline_version",
)

OBSERVABILITY_STATUS_VALUES = (
    "not_assessed",
    "no_pre_scene",
    "no_post_scene",
    "no_usable_pre_scene",
    "no_usable_post_scene",
    "usable_both",
    "partial_coverage",
    "ambiguous",
    "excluded",
)

EXCLUSION_REASON_VALUES = (
    "not_assessed",
    "no_pre_scene",
    "no_post_scene",
    "no_usable_pre_scene",
    "no_usable_post_scene",
    "cloud_fraction_above_threshold",
    "coverage_below_threshold",
    "partial_coverage",
    "invalid_aoi",
    "spatial_overlap_ambiguous",
    "temporal_overlap_ambiguous",
    "other",
)


class ProvisionalValidationError(ValueError):
    """Raised when a supposedly frozen output is incompatible or unsafe."""


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    """Read a UTF-8 CSV without changing any source values."""

    input_path = Path(path)
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ProvisionalValidationError(f"CSV sin encabezado: {input_path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise ProvisionalValidationError(f"No se pudo leer el CSV: {input_path}") from exc


def write_csv(path: Path | str, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    """Write a deterministic UTF-8 CSV with an explicit schema."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})


def write_json(path: Path | str, value: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required(row: Mapping[str, Any], fields: Sequence[str], context: str) -> None:
    missing = [field for field in fields if field not in row]
    if missing:
        raise ProvisionalValidationError(f"{context}: faltan columnas {', '.join(missing)}")


def _bool_value(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "si", "sí"}


def _utc_year(value: Any, field: str) -> int:
    text = "" if value is None else str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProvisionalValidationError(f"Timestamp inválido en {field}: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProvisionalValidationError(f"Timestamp sin zona horaria en {field}: {value!r}")
    normalized = parsed.astimezone(timezone.utc)
    if normalized.year == 2026:
        raise ProvisionalValidationError(f"No se permite dato de 2026 en {field}: {value!r}")
    return normalized.year


def _validate_configuration(rows: Sequence[Mapping[str, Any]], context: str) -> None:
    if not rows:
        raise ProvisionalValidationError(f"{context}: no contiene filas")
    configurations = {str(row.get("configuration_id", "")).strip() for row in rows}
    if configurations != {FROZEN_CONFIGURATION_ID}:
        raise ProvisionalValidationError(
            f"{context}: se requiere únicamente {FROZEN_CONFIGURATION_ID}; recibido {sorted(configurations)}"
        )


def _event_id_hash(event_ids: Iterable[str]) -> str:
    payload = "\n".join(sorted(event_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def freeze_from_outputs(
    source_dir: Path | str,
    membership_output: Path | str,
    events_output: Path | str,
    *,
    expected_detection_count: int | None = EXPECTED_DETECTION_COUNT,
    expected_event_count: int | None = EXPECTED_EVENT_COUNT,
) -> dict[str, Any]:
    """Freeze r1500_t06 source CSVs without rerunning clustering."""

    source_path = Path(source_dir)
    source_membership_path = source_path / "membership.csv"
    source_events_path = source_path / "events.csv"
    membership = read_csv_rows(source_membership_path)
    events = read_csv_rows(source_events_path)
    _validate_configuration(membership, "membership.csv")
    _validate_configuration(events, "events.csv")
    for row in membership:
        _required(row, FROZEN_MEMBERSHIP_COLUMNS, "membership.csv")
        _utc_year(row["timestamp_utc"], "membership.timestamp_utc")
    for row in events:
        _required(
            row,
            (
                "configuration_id",
                "event_id",
                "start_timestamp_utc",
                "end_timestamp_utc",
                "detection_count",
                "source_count",
                "firms_sources",
                "satellite_count",
                "satellites",
                "bbox_south",
                "bbox_west",
                "bbox_north",
                "bbox_east",
                "max_pairwise_distance_m",
                "max_distance_to_centroid_m",
                "max_consecutive_gap_hours",
                "calendar_days_covered",
                "confidence_counts",
                "possible_chain_merge",
                "chain_merge_reasons",
            ),
            "events.csv",
        )
        _utc_year(row["start_timestamp_utc"], "events.start_timestamp_utc")
        _utc_year(row["end_timestamp_utc"], "events.end_timestamp_utc")

    event_ids = [row["event_id"] for row in events]
    detection_ids = [row["detection_id"] for row in membership]
    if len(event_ids) != len(set(event_ids)):
        raise ProvisionalValidationError("events.csv contiene event_id duplicados")
    if len(detection_ids) != len(set(detection_ids)):
        raise ProvisionalValidationError("membership.csv contiene detection_id duplicados")
    event_id_set = set(event_ids)
    membership_event_ids = {row["event_id"] for row in membership}
    if membership_event_ids != event_id_set:
        raise ProvisionalValidationError("La membresía no coincide con el universo de event_id")

    membership_counts = Counter(row["event_id"] for row in membership)
    for row in events:
        try:
            expected_count = int(row["detection_count"])
        except ValueError as exc:
            raise ProvisionalValidationError(f"detection_count inválido en {row['event_id']}") from exc
        if membership_counts[row["event_id"]] != expected_count:
            raise ProvisionalValidationError(
                f"Conteo inconsistente para {row['event_id']}: "
                f"events.csv={expected_count}, membership.csv={membership_counts[row['event_id']]}"
            )

    if expected_detection_count is not None and len(membership) != expected_detection_count:
        raise ProvisionalValidationError(
            f"Se esperaban {expected_detection_count} detecciones; se recibieron {len(membership)}"
        )
    if expected_event_count is not None and len(events) != expected_event_count:
        raise ProvisionalValidationError(
            f"Se esperaban {expected_event_count} eventos; se recibieron {len(events)}"
        )

    frozen_membership = [
        {field: row.get(field, "") for field in FROZEN_MEMBERSHIP_COLUMNS} for row in membership
    ]
    frozen_events = [
        {
            "event_id": row["event_id"],
            "configuration_id": row["configuration_id"],
            "start_timestamp_utc": row["start_timestamp_utc"],
            "end_timestamp_utc": row["end_timestamp_utc"],
            "duration_hours": row.get("duration_hours", ""),
            "detection_count": row["detection_count"],
            "source_count": row["source_count"],
            "sources": row["firms_sources"],
            "satellite_count": row["satellite_count"],
            "satellites": row["satellites"],
            "centroid_latitude": row.get("centroid_latitude", ""),
            "centroid_longitude": row.get("centroid_longitude", ""),
            "min_latitude": row["bbox_south"],
            "min_longitude": row["bbox_west"],
            "max_latitude": row["bbox_north"],
            "max_longitude": row["bbox_east"],
            "spatial_extent_m": row["max_pairwise_distance_m"],
            "maximum_centroid_distance_m": row["max_distance_to_centroid_m"],
            "maximum_temporal_gap_hours": row["max_consecutive_gap_hours"],
            "calendar_day_count": row["calendar_days_covered"],
            "frp_min": row.get("frp_min", ""),
            "frp_max": row.get("frp_max", ""),
            "frp_mean": row.get("frp_mean", ""),
            "frp_median": row.get("frp_median", ""),
            "frp_sum": row.get("frp_sum", ""),
            "confidence_category_counts": row["confidence_counts"],
            "day_fraction": row.get("day_fraction", ""),
            "night_fraction": row.get("night_fraction", ""),
            "possible_chain_merge": row["possible_chain_merge"],
            "chain_merge_reasons": row["chain_merge_reasons"],
        }
        for row in events
    ]
    write_csv(membership_output, FROZEN_MEMBERSHIP_COLUMNS, frozen_membership)
    write_csv(events_output, FROZEN_EVENT_COLUMNS, frozen_events)

    singleton_count = sum(int(row["detection_count"]) == 1 for row in events)
    return {
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "radius_m": FROZEN_RADIUS_M,
        "time_window_hours": FROZEN_TIME_WINDOW_HOURS,
        "source_dir": str(source_path),
        "source_membership_sha256": sha256_file(source_membership_path),
        "source_events_sha256": sha256_file(source_events_path),
        "event_count": len(events),
        "detection_count": len(membership),
        "sum_detection_count": sum(int(row["detection_count"]) for row in events),
        "singleton_count": singleton_count,
        "multi_detection_event_count": len(events) - singleton_count,
        "possible_chain_merge_event_count": sum(_bool_value(row["possible_chain_merge"]) for row in events),
        "event_id_sha256": _event_id_hash(event_ids),
        "detection_id_sha256": _event_id_hash(detection_ids),
    }


def _allocate_proportional(counts: Mapping[str, int], target: int) -> dict[str, int]:
    """Allocate a target using largest remainders and deterministic ties."""

    positive = {key: int(value) for key, value in counts.items() if int(value) > 0}
    total = sum(positive.values())
    if not positive or target <= 0 or target > total:
        raise ProvisionalValidationError("No se puede asignar una cuota proporcional")
    raw = {key: target * value / total for key, value in positive.items()}
    quotas = {key: min(positive[key], math.floor(raw[key])) for key in positive}
    if target >= len(quotas):
        for key in sorted(quotas):
            if quotas[key] == 0:
                quotas[key] = 1
    while sum(quotas.values()) > target:
        candidates = [key for key in quotas if quotas[key] > 1]
        if not candidates:
            break
        key = min(candidates, key=lambda item: (raw[item] - quotas[item], item))
        quotas[key] -= 1
    while sum(quotas.values()) < target:
        candidates = [key for key in quotas if quotas[key] < positive[key]]
        if not candidates:
            raise ProvisionalValidationError("No hay capacidad para completar la cuota")
        key = max(candidates, key=lambda item: (raw[item] - quotas[item], item))
        quotas[key] += 1
    return quotas


def _add_strata(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    enriched = [dict(event) for event in events]
    multi = [event for event in enriched if int(event["detection_count"]) > 1]
    multi.sort(key=lambda event: (int(event["detection_count"]), str(event["event_id"])))
    quartile_by_event: dict[str, str] = {}
    for rank, event in enumerate(multi, start=1):
        quartile = min(4, math.ceil(rank * 4 / len(multi)))
        quartile_by_event[str(event["event_id"])] = f"Q{quartile}"
    for event in enriched:
        try:
            start = datetime.fromisoformat(str(event["start_timestamp_utc"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProvisionalValidationError(
                f"start_timestamp_utc inválido para {event.get('event_id')}"
            ) from exc
        _utc_year(event["start_timestamp_utc"], "events.start_timestamp_utc")
        detection_count = int(event["detection_count"])
        event["month"] = start.strftime("%Y-%m")
        event["event_size_class"] = "singleton" if detection_count == 1 else "multi_detection"
        event["multi_detection_quartile"] = (
            "not_applicable" if detection_count == 1 else quartile_by_event[str(event["event_id"])]
        )
        event["source_class"] = (
            "multiple_sources" if int(event.get("source_count", 0)) > 1 else "single_source"
        )
        event["chain_class"] = (
            "possible_chain_merge" if _bool_value(event.get("possible_chain_merge")) else "no_possible_chain_merge"
        )
    return enriched


def _dimension_counts(events: Sequence[Mapping[str, Any]], field: str) -> Counter[str]:
    return Counter(str(event[field]) for event in events)


def select_observability_pilot(
    events: Sequence[Mapping[str, Any]],
    *,
    sample_size: int = PILOT_SAMPLE_SIZE,
    seed: int = PILOT_SAMPLE_SEED,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a deterministic structural pilot sample without using FRP."""

    if len(events) < sample_size:
        raise ProvisionalValidationError("El universo no alcanza el tamaño de muestra solicitado")
    _validate_configuration(events, "eventos para muestreo")
    enriched = _add_strata(events)
    size_quotas = _allocate_proportional(_dimension_counts(enriched, "event_size_class"), sample_size)
    multi_events = [event for event in enriched if event["event_size_class"] == "multi_detection"]
    multi_target = size_quotas.get("multi_detection", 0)
    quartile_quotas = (
        _allocate_proportional(_dimension_counts(multi_events, "multi_detection_quartile"), multi_target)
        if multi_target
        else {}
    )
    global_quotas = {
        field: _allocate_proportional(_dimension_counts(enriched, field), sample_size)
        for field in ("month", "source_class", "chain_class")
    }

    ordered_ids = sorted(str(event["event_id"]) for event in enriched)
    shuffled_ids = list(ordered_ids)
    random.Random(seed).shuffle(shuffled_ids)
    tie_rank = {event_id: rank for rank, event_id in enumerate(shuffled_ids)}
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    counters = {
        "event_size_class": Counter[str](),
        "multi_detection_quartile": Counter[str](),
        "month": Counter[str](),
        "source_class": Counter[str](),
        "chain_class": Counter[str](),
    }
    weight = {
        "event_size_class": 3.0,
        "multi_detection_quartile": 2.0,
        "month": 2.0,
        "source_class": 2.0,
        "chain_class": 2.0,
    }

    while len(selected) < sample_size:
        candidates: list[dict[str, Any]] = []
        for event in enriched:
            event_id = str(event["event_id"])
            if event_id in selected_ids:
                continue
            size_class = str(event["event_size_class"])
            if counters["event_size_class"][size_class] >= size_quotas[size_class]:
                continue
            if size_class == "multi_detection":
                quartile = str(event["multi_detection_quartile"])
                if counters["multi_detection_quartile"][quartile] >= quartile_quotas[quartile]:
                    continue
            candidates.append(event)
        if not candidates:
            raise ProvisionalValidationError("La estratificación no pudo completar la muestra")

        def score(event: Mapping[str, Any]) -> tuple[float, int, str]:
            total_score = 0.0
            for field, quotas in (
                ("event_size_class", size_quotas),
                ("multi_detection_quartile", quartile_quotas),
                ("month", global_quotas["month"]),
                ("source_class", global_quotas["source_class"]),
                ("chain_class", global_quotas["chain_class"]),
            ):
                category = str(event[field])
                target = quotas.get(category, 0)
                current = counters[field][category]
                if target > current:
                    total_score += weight[field] * (target - current) / target
            event_id = str(event["event_id"])
            return (-total_score, tie_rank[event_id], event_id)

        chosen = min(candidates, key=score)
        chosen_id = str(chosen["event_id"])
        selected.append(dict(chosen))
        selected_ids.add(chosen_id)
        for field in counters:
            counters[field][str(chosen[field])] += 1

    controlled_fields = (
        "event_size_class",
        "multi_detection_quartile",
        "month",
        "source_class",
        "chain_class",
    )

    def repair_field(field: str, quotas: Mapping[str, int]) -> bool:
        """Repair one marginal quota with a deterministic one-for-one swap."""

        outgoing_candidates = sorted(
            enumerate(selected),
            key=lambda item: (tie_rank[str(item[1]["event_id"])], str(item[1]["event_id"])),
        )
        incoming_candidates = sorted(
            (event for event in enriched if str(event["event_id"]) not in selected_ids),
            key=lambda event: (tie_rank[str(event["event_id"])], str(event["event_id"])),
        )
        for outgoing_index, outgoing in outgoing_candidates:
            outgoing_category = str(outgoing[field])
            if outgoing_category not in quotas or counters[field][outgoing_category] <= quotas[outgoing_category]:
                continue
            for incoming in incoming_candidates:
                incoming_category = str(incoming[field])
                if incoming_category not in quotas or counters[field][incoming_category] >= quotas[incoming_category]:
                    continue
                if any(
                    str(incoming[other]) != str(outgoing[other])
                    for other in controlled_fields
                    if other != field
                ):
                    continue
                outgoing_id = str(outgoing["event_id"])
                incoming_id = str(incoming["event_id"])
                selected[outgoing_index] = dict(incoming)
                selected_ids.remove(outgoing_id)
                selected_ids.add(incoming_id)
                for counter_field in counters:
                    counters[counter_field][str(outgoing[counter_field])] -= 1
                    counters[counter_field][str(incoming[counter_field])] += 1
                return True
        return False

    for field, quotas in (
        ("event_size_class", size_quotas),
        ("multi_detection_quartile", quartile_quotas),
        ("month", global_quotas["month"]),
        ("source_class", global_quotas["source_class"]),
        ("chain_class", global_quotas["chain_class"]),
    ):
        while any(counters[field][category] != target for category, target in quotas.items()):
            if not repair_field(field, quotas):
                raise ProvisionalValidationError(
                    f"No se pudo satisfacer la cuota estratificada de {field}"
                )

    output_rows: list[dict[str, Any]] = []
    for rank, event in enumerate(selected, start=1):
        output_rows.append(
            {
                "sampling_rank": rank,
                **{field: event.get(field, "") for field in PILOT_COLUMNS if field != "sampling_rank"},
            }
        )
    report = {
        "configuration_id": FROZEN_CONFIGURATION_ID,
        "universe_count": len(enriched),
        "sample_size": len(output_rows),
        "seed": seed,
        "selection_method": "proportional marginal quotas, deterministic deficit-greedy selection, and deterministic one-for-one quota repair; seeded tie-break only",
        "selection_fields": [
            "event_size_class",
            "multi_detection_quartile",
            "month",
            "source_class",
            "chain_class",
            "event_id_tie_break",
        ],
        "frp_used_for_selection": False,
        "manual_visual_selection": False,
        "images_consulted": False,
        "network_called": False,
        "quota_targets": {
            "event_size_class": dict(size_quotas),
            "multi_detection_quartile": dict(quartile_quotas),
            **global_quotas,
        },
        "quota_achieved": {
            field: dict(_dimension_counts(output_rows, field))
            for field in ("event_size_class", "multi_detection_quartile", "month", "source_class", "chain_class")
        },
        "selected_event_ids": [str(row["event_id"]) for row in output_rows],
        "excluded_event_count": len(enriched) - len(output_rows),
        "excluded_event_ids": sorted(set(ordered_ids) - selected_ids),
        "limitations": [
            "La muestra estratifica marginalmente; no representa todas las combinaciones del producto cartesiano de estratos.",
            "La cuota proporcional no corrige sesgos de detección FIRMS, nubosidad ni disponibilidad óptica.",
            "Los eventos excluidos no son negativos de quema y no se convierten en cero.",
        ],
    }
    return output_rows, report


def write_sampling_markdown(path: Path | str, report: Mapping[str, Any]) -> None:
    lines = [
        "# Muestreo piloto de observabilidad Sentinel-2",
        "",
        "> Diseño estructural congelado antes de consultar imágenes. No es una etiqueta de quema.",
        "",
        f"- Configuración: `{report['configuration_id']}`.",
        f"- Universo: `{report['universe_count']}` eventos provisionales.",
        f"- Muestra: `{report['sample_size']}` eventos.",
        f"- Semilla: `{report['seed']}`.",
        "- FRP usado para seleccionar: `no`.",
        "- Selección visual/manual: `no`.",
        "- Imágenes consultadas durante esta selección: `no`.",
        "",
        "## Cuotas objetivo y logradas",
        "",
        "| Dimensión | Objetivo | Logrado |",
        "|---|---|---|",
    ]
    targets = report["quota_targets"]
    achieved = report["quota_achieved"]
    for dimension in targets:
        lines.append(f"| `{dimension}` | `{json.dumps(targets[dimension], ensure_ascii=False, sort_keys=True)}` | `{json.dumps(achieved.get(dimension, {}), ensure_ascii=False, sort_keys=True)}` |")
    lines.extend(
        [
            "",
            "## Eventos elegidos",
            "",
            "| Rank | Event ID |",
            "|---:|---|",
        ]
    )
    for rank, event_id in enumerate(report["selected_event_ids"], start=1):
        lines.append(f"| {rank} | `{event_id}` |")
    lines.extend(
        [
            "",
            f"Eventos excluidos del piloto: `{report['excluded_event_count']}`. La exclusión solo significa que no entran en esta muestra de observabilidad; no implica ausencia de quema ni falta de interés científico.",
            "",
            "## Limitaciones",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_empty_observability_schema(path: Path | str) -> None:
    """Create the header-only future observation table; no fake rows."""

    write_csv(path, OBSERVABILITY_COLUMNS, [])
