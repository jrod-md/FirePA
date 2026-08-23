"""Build the Sentinel-2 policy matrix from local inventories only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from fuegopa.sentinel2_policy import (  # noqa: E402
    DEFAULT_POLICY_RULE,
    default_policy_paths,
    load_policy_inputs,
    build_policy_analysis,
    sha256_file,
    write_policy_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compara las políticas Sentinel-2 del piloto desde inventarios locales; no consulta Earth Engine."
    )
    parser.add_argument("--root", default=str(ROOT), help="Raíz del repositorio.")
    parser.add_argument("--policy-rule", choices=("A", "B", "C", "D"), default=DEFAULT_POLICY_RULE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    paths = default_policy_paths(root)
    events, observation_rows, scene_rows, aoi_rows, _ = load_policy_inputs(
        pilot_path=paths["pilot"],
        events_path=paths["events"],
        membership_path=paths["membership"],
        observability_path=paths["observability"],
        scene_inventory_path=paths["scene_inventory"],
        aoi_inventory_path=paths["aoi_inventory"],
    )
    analysis = build_policy_analysis(events, observation_rows, scene_rows, aoi_rows, policy_rule=args.policy_rule)
    analysis["summary"]["input_sha256"] = {
        "scene_inventory": sha256_file(paths["scene_inventory"]),
        "aoi_inventory": sha256_file(paths["aoi_inventory"]),
        "observability": sha256_file(paths["observability"]),
    }
    figure_paths = write_policy_outputs(analysis, paths)
    summary = analysis["summary"]
    print(f"policy_rule={summary['policy_rule']}")
    print(f"events={summary['event_count']} scene_rows={summary['scene_inventory_row_count']} unique_scenes={summary['unique_sentinel2_scene_count']}")
    print(f"primary={summary['primary_short_combination_id']} usable={summary['primary_short_events_with_usable_pair']}")
    print(f"fallback_rescues={summary['primary_short_fallback_rescue_count']} excluded={','.join(summary['global_excluded_event_ids'])}")
    print(f"decision={paths['decision']}")
    print(f"markdown={paths['decision_markdown']}")
    print(f"figures={len(figure_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
