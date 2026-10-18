"""Build a viewer case from a scar found by scar_search.py (exploratory, not FirePA v1).

    python build_scar_case.py <case_id>

For the case in case_registry.CASES it measures the scar again at 20 m with one
Sentinel-2 scene pair (same method as s2_guacamaya.py, plus the 300 m cloud
buffer from s2_picachos.py), links FIRMS events from the FirePA v1 package, and
writes everything the viewer loads into web/cases/<case_id>/.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

import build_tiles as bt
import cog
import s2_context as ctx
import s2_guacamaya as g
import scar_style
from case_registry import CASES

SCL_CLOUD = {3, 8, 9, 10}
CLOUD_BUFFER_PX = 15  # 300 m at 20 m
THRESHOLDS = (0.10, 0.20, 0.30, 0.40)
LINK_M = 1000


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def disk_dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx <= r * r:
                out |= g.shift(mask, dy, dx)
    return out


def window(center, half):
    x, y = g.to_utm.transform(*center)
    snap = lambda v: 499980 + round((v - 499980) / 20) * 20
    return snap(x - half), snap(y - half), snap(x + half), snap(y + half)


def nbr(it, bbox):
    b8 = np.clip(g.reflectance(it, "nir", bbox, to20=True), 0, None)
    b12 = np.clip(g.reflectance(it, "swir22", bbox), 0, None)
    den = b8 + b12
    return np.where(den > 0.02, (b8 - b12) / np.where(den > 0.02, den, 1), np.nan)


def lonlat_corners(bbox):
    xmin, ymin, xmax, ymax = bbox
    return [[round(a, 6), round(b, 6)] for a, b in (g.to_ll.transform(x, y) for x, y in ((xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)))]


def events_for(cfg, bbox):
    feats = json.loads((bt.REPO / "site-data" / "events.geojson").read_text(encoding="utf-8"))["features"]
    xmin, ymin, xmax, ymax = bbox
    out = []
    for f in feats:
        p = f["properties"]
        x, y = g.to_utm.transform(*f["geometry"]["coordinates"])
        if xmin <= x <= xmax and ymin <= y <= ymax and cfg["firms_window"][0] <= p["start_time_utc"][:10] <= cfg["firms_window"][1]:
            out.append((f, x, y))
    return sorted(out, key=lambda e: e[0]["properties"]["start_time_utc"])


def main(case_id: str) -> None:
    cfg = CASES[case_id]
    out = bt.WEB / "cases" / case_id
    s2dir = out / "s2"
    s2dir.mkdir(parents=True, exist_ok=True)
    bbox = window(cfg["center"], cfg["half_m"])
    pre, post = g.item(cfg["pre"]), g.item(cfg["post"])
    scl = {k: g.read(it, "scl", bbox) for k, it in (("pre", pre), ("post", post))}
    n = {"pre": nbr(pre, bbox), "post": nbr(post, bbox)}
    cloud = disk_dilate(np.isin(scl["pre"], list(SCL_CLOUD)) | np.isin(scl["post"], list(SCL_CLOUD)), CLOUD_BUFFER_PX)
    valid = (np.isin(scl["pre"], list(g.SCL_VALID)) & np.isin(scl["post"], list(g.SCL_VALID))
             & (scl["pre"] != 6) & (scl["post"] != 6) & ~cloud & np.isfinite(n["pre"]) & np.isfinite(n["post"]))
    dnbr = np.where(valid, n["pre"] - n["post"], np.nan)
    # Water (sea, ponds, rivers) is excluded but is not missing data; report gaps over land only.
    water = (scl["pre"] == 6) | (scl["post"] == 6)
    land = ~water
    H, W = dnbr.shape
    xmin, ymin, xmax, ymax = bbox
    rr, cc = np.indices((H, W))
    px_x, px_y = xmin + (cc + 0.5) * 20, ymax - (rr + 0.5) * 20

    evs = events_for(cfg, bbox)
    seeds = np.zeros((H, W), dtype=bool)
    for _, ex, ey in evs:
        seeds |= np.hypot(px_x - ex, px_y - ey) <= LINK_M
    px_ha = 0.04
    areas, linked_masks = [], {}
    for t in THRESHOLDS:
        burned = valid & (np.nan_to_num(dnbr, nan=-9) > t)
        lab, _ = g.components(burned)
        ids = set(np.unique(lab[seeds & burned])) - {0}
        linked = np.isin(lab, list(ids))
        linked_masks[t] = linked
        u, cnt = np.unique(lab[linked], return_counts=True)
        main_ = lab == u[np.argmax(cnt)] if u.size else np.zeros_like(linked)
        ring = disk_dilate(main_, 25) & ~main_  # 500 m around the main patch
        areas.append({
            "threshold": t,
            "linked_ha": round(float(linked.sum()) * px_ha, 1),
            "linked_patches": len(ids),
            "main_patch_ha": round(float(main_.sum()) * px_ha, 1),
            "main_patch_convex_hull_ha": round(g.hull_area_px(main_) * px_ha, 1) if main_.any() else 0.0,
            "main_patch_median_dnbr": round(float(np.nanmedian(dnbr[main_])), 3) if main_.any() else None,
            "main_touches_window_edge": bool(main_[0].any() or main_[-1].any() or main_[:, 0].any() or main_[:, -1].any()),
            "no_data_within_500m_ha": round(float((ring & ~valid & land).sum()) * px_ha, 1),
        })
        if t == 0.20:
            main20 = main_

    g.rgb_png(pre, bbox, s2dir / "pre.png")
    g.rgb_png(post, bbox, s2dir / "post.png")
    # Draw the main patch only, so the map matches the area the viewer reports;
    # other linked patches fall into the faint "other change" layer.
    scar_style.fill_webp(dnbr, valid, main20, s2dir / "scar.webp", water)
    scar_style.outline_geojson(main20, bbox, s2dir / "scar.geojson")

    # Presentation imagery: feathered 10 m detail and a 20 m context mosaic.
    ctx.OUT = s2dir
    ctx.AOI = cfg["view_aoi"]
    cbbox = ctx.utm_bbox(20)
    ctx_corners = {}
    for side, it in (("pre", pre), ("post", post)):
        ctx_corners[side] = ctx.context(it["id"], side, cbbox)
        ctx.feather(side)

    dem, lon0, lat0, res = bt.load_dem()
    clusters, prev_end = [], None
    # Show only the events that tie to the measured scar: within LINK_M of a linked
    # patch and before the "after" image. Others in the window are unrelated fires.
    lk20 = linked_masks[0.20]
    post_t = post["properties"]["datetime"]
    evs = [(f, ex, ey) for f, ex, ey in evs if lk20.any() and f["properties"]["start_time_utc"] < post_t
           and float(np.min(np.hypot(px_x[lk20] - ex, px_y[lk20] - ey))) <= LINK_M]
    for i, (f, ex, ey) in enumerate(evs, 1):
        p = f["properties"]
        st, en = p["start_time_utc"], p["end_time_utc"]
        dist = float(np.min(np.hypot(px_x[main20] - ex, px_y[main20] - ey))) if main20.any() else None
        gap = None if prev_end is None else round((datetime.fromisoformat(st.replace("Z", "+00:00")) - prev_end).total_seconds() / 3600, 2)
        prev_end = datetime.fromisoformat(en.replace("Z", "+00:00"))
        lon, lat = f["geometry"]["coordinates"]
        nk = p.get("daynight_known_count") or p["detection_count"]
        clusters.append({
            "order": i, "public_event_id": p["public_event_id"], "cluster_start_utc": st, "cluster_end_utc": en,
            "detection_count": p["detection_count"], "max_frp_mw": p["frp_max_mw"], "mean_frp_mw": p["frp_mean_mw"],
            "satellites": p["satellites"], "day_count": round(p["day_fraction"] * nk), "night_count": round(p["night_fraction"] * nk),
            "gap_from_previous_hours": gap, "possible_chain_merge": p["possible_chain_merge"],
            "centroid": [lon, lat], "dsm_elevation_m": round(float(bt.sample(dem, lon0, lat0, res, lon, lat)), 1),
            "distance_to_main_scar_m": None if dist is None else round(dist),
        })

    summit_rc = None
    if main20.any():
        sx, sy = px_x[main20], px_y[main20]
        elev = bt.sample(dem, lon0, lat0, res, *g.to_ll.transform(sx, sy))
        k = int(np.argmax(elev))
        summit_rc = {"coordinates": [round(v, 5) for v in g.to_ll.transform(float(sx[k]), float(sy[k]))], "elevation_m": round(float(elev[k]))}
        e_lo = round(float(np.min(elev)))

    s2 = {
        "status": "exploratory; outside FirePA Scientific Pilot v1",
        "method": {"index": "NBR=(B8-B12)/(B8+B12); dNBR=NBR_pre-NBR_post", "grid": "EPSG:32617, 20 m",
                   "cloud_mask": "SCL 2,4,5,7 valid in both dates, water excluded, 300 m disk buffer around SCL 3,8,9,10",
                   "linked_rule": f"8-connected dNBR patches with a pixel within {LINK_M} m of a FIRMS event centroid in the case window",
                   "window_m": list(bbox), "found_by": "scar_search.py (80 m screening)"},
        "pre": {"id": pre["id"], "datetime": pre["properties"]["datetime"]},
        "post": {"id": post["id"], "datetime": post["properties"]["datetime"]},
        "valid_overlap_fraction": round(float(valid[land].mean()), 4),
        "valid_fraction_basis": "land pixels (water excluded from the denominator)",
        "areas": areas,
        "corners_lonlat": lonlat_corners(bbox),
        "context": {"role": "presentation only", "resolution_m": 20, "utm_bbox": [float(v) for v in cbbox], "corners_lonlat": ctx_corners["post"]},
        "outputs": {p.name: sha(p) for p in sorted(s2dir.glob("*.webp"))},
        "attribution": "Contains modified Copernicus Sentinel data 2025",
    }
    (s2dir / "s2.json").write_text(json.dumps(s2, indent=2) + "\n", encoding="utf-8", newline="\n")
    case = {
        "id": case_id, **{k: cfg[k] for k in ("title", "place", "view_aoi", "firms_window", "views", "story")},
        "tile_aoi": bt.TILE_AOI, "summit": summit_rc, "scar_low_elevation_m": e_lo if main20.any() else None,
        "clusters": clusters,
        "provenance": {"firepa_files": {"events.geojson": sha(bt.REPO / "site-data" / "events.geojson")},
                       "dem": {p.name: sha(p) for p in (bt.RAW, bt.RAW_N)}},
    }
    (out / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    a20 = next(a for a in areas if a["threshold"] == 0.2)
    print(json.dumps({"valid": s2["valid_overlap_fraction"], "a20": a20, "events": len(clusters), "summit": summit_rc}, indent=1))
    print(f"downloaded {cog.bytes_fetched / 1e6:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1])
