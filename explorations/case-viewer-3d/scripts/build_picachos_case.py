"""Case data for Cerro Los Picachos (REFERENCE-001) from the FirePA public package.

Nothing is recomputed: the anchor, the official zero and the 10,400.826 m
nearest contemporary signal come from external-references.geojson. Nearby
events are FirePA v1 provisional events within 15 km of the approximate anchor
that start between 5 and 31 January 2025, shown as context, not as matches.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import build_tiles as bt

WEB = bt.WEB
OUT = WEB / "cases" / "picachos"
SITE = bt.REPO / "site-data"
RADIUS_M = 15000
WINDOW = ("2025-01-05", "2025-01-31")


def dist_m(a, b):
    return math.hypot((b[0] - a[0]) * 111320 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 110574)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dem, lon0, lat0, res = bt.load_dem()
    refs = json.loads((SITE / "external-references.geojson").read_text(encoding="utf-8"))
    events = json.loads((SITE / "events.geojson").read_text(encoding="utf-8"))
    cites = json.loads((SITE / "citations.json").read_text(encoding="utf-8"))
    ref = next(f for f in refs["features"] if f["properties"]["reference_id"] == "REFERENCE-001")
    anchor = ref["geometry"]["coordinates"]
    near = []
    for f in events["features"]:
        p = f["properties"]
        d = dist_m(anchor, f["geometry"]["coordinates"])
        if d <= RADIUS_M and WINDOW[0] <= p["start_time_utc"][:10] <= WINDOW[1]:
            near.append({
                "public_event_id": p["public_event_id"],
                "centroid": f["geometry"]["coordinates"],
                "cluster_start_utc": p["start_time_utc"],
                "cluster_end_utc": p["end_time_utc"],
                "detection_count": p["detection_count"],
                "max_frp_mw": p["frp_max_mw"],
                "mean_frp_mw": p["frp_mean_mw"],
                "satellites": p["satellites"],
                "distance_to_anchor_m": round(d),
                "in_official_window": WINDOW[0] <= p["start_time_utc"][:10] and "2025-01-15" <= p["start_time_utc"][:10] <= "2025-01-17",
                "dsm_elevation_m": round(float(bt.sample(dem, lon0, lat0, res, *f["geometry"]["coordinates"])), 1),
            })
    near.sort(key=lambda e: e["cluster_start_utc"])
    for i, e in enumerate(near, 1):
        e["order"] = i
    case = {
        "case_id": "picachos",
        "aoi": [-80.76, 8.32, -80.54, 8.52],
        "anchor": {"coordinates": anchor, **{k: ref["properties"][k] for k in (
            "reference_name", "anchor_status", "coordinate_claimed_by_source", "official_window_start",
            "official_window_end", "official_matching_radius_m", "official_match_count", "diagnostic",
            "nearest_documented_contemporary_signal_m", "source_document_count")},
            "anchor_dsm_elevation_m": round(float(bt.sample(dem, lon0, lat0, res, *anchor)), 1)},
        "nearby_events": near,
        "summits_near_anchor": [
            {"elevation_m": 581, "coordinates": [-80.66583, 8.39583]},
            {"elevation_m": 505, "coordinates": [-80.66556, 8.40333]},
            {"elevation_m": 490, "coordinates": [-80.67472, 8.41444]},
        ],
        "source": [s for s in cites["external_sources"] if s["incident_id"] == "REFERENCE-001"],
        "provenance": {
            "firepa_files": {n: hashlib.sha256((SITE / n).read_bytes()).hexdigest() for n in ("events.geojson", "external-references.geojson", "citations.json")},
        },
    }
    (OUT / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
    for e in near:
        print(e["order"], e["public_event_id"], e["cluster_start_utc"], e["detection_count"], e["distance_to_anchor_m"])


if __name__ == "__main__":
    main()
