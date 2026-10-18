"""Rank scar_search candidates for the viewer: large, FIRMS-corroborated, on relief.

Adds to each candidate the DSM relief under its centroid neighbourhood (elevation
range within 1.5 km), then prints a shortlist. Field-shaped patches (high bbox
fill on flat ground) are flagged, since they are often cane or rice harvest burns.
"""

from __future__ import annotations

import json
import math

import numpy as np

import build_tiles as bt

PATH = bt.ROOT / "results" / "scar_search" / "candidates.json"


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    dem, lon0, lat0, res = bt.load_dem()
    for c in data["candidates"]:
        lon, lat = c["centroid"]
        k = 1500 / 111_320
        lo = np.linspace(lon - k / math.cos(math.radians(lat)), lon + k / math.cos(math.radians(lat)), 31)
        la = np.linspace(lat - k, lat + k, 31)
        LO, LA = np.meshgrid(lo, la)
        e = bt.sample(dem, lon0, lat0, res, LO, LA)
        c["relief_m_3km"] = round(float(e.max() - e.min()))
        c["elev_centroid_m"] = round(float(bt.sample(dem, lon0, lat0, res, lon, lat)))
        c["field_like"] = c["bbox_fill"] > 0.55 and c["relief_m_3km"] < 60
        c["score"] = round(c["area_ha_80m"] * (1 + min(c["relief_m_3km"], 400) / 200) * (1.5 if c["firms_events"] else 0.5) * (0.4 if c["field_like"] else 1), 0)
    data["candidates"].sort(key=lambda c: -c["score"])
    PATH.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("rank score   ha  dNBR relief  elev FIRMS(ev/det) fill  pair          centroid")
    for c in data["candidates"][:30]:
        print(f"{c['rank']:>4} {c['score']:>5.0f} {c['area_ha_80m']:>5.0f} {c['median_dnbr']:>5.2f} {c['relief_m_3km']:>5} {c['elev_centroid_m']:>5}"
              f"  {c['firms_events']:>3}/{c['firms_detections']:<4} {c['bbox_fill']:.2f} {'FIELD' if c['field_like'] else '     '} {c['pair']:<10} {c['centroid']}")


if __name__ == "__main__":
    main()
