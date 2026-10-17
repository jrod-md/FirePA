"""Exploratory Sentinel-2 check for Cerro Los Picachos (REFERENCE-001), not FirePA v1.

FirePA v1 found 0 official FIRMS matches (window 2025-01-15..17, <=5 km); the
nearest contemporary signal is 10,400.826 m away. Here we ask a different,
exploratory question: did a new burn scar appear between the last clear scene
before 16 Jan 2025 and the first clear scene after it, and where?

Same index, grid and SCL mask as s2_guacamaya.py. There are no matched FIRMS
clusters to link patches to, so patches are reported as candidates ranked by
area, with distances to the approximate anchor and to the 15 Jan FIRMS signal.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

import cog
import s2_guacamaya as g

WEB = g.WEB
CASE_DIR = WEB / "cases" / "picachos"
OUT = CASE_DIR / "s2"
ANCHOR = (-80.65114, 8.42097)
SIGNAL = (-80.57902, 8.48175)  # evt-0418, 2025-01-15 18:47 UTC, 1 detection
HALF = 11000
# Window centred between the anchor and the 15 Jan FIRMS signal so both sit well inside it.
CENTER = ((ANCHOR[0] + SIGNAL[0]) / 2, (ANCHOR[1] + SIGNAL[1]) / 2)
CLOUD_BUFFER_PX = 15  # 300 m at 20 m: SCL misses soft cloud/shadow edges that mimic burns


def dilate(mask: np.ndarray, n: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(n):
        out = out | np.roll(out, 1, 0) | np.roll(out, -1, 0) | np.roll(out, 1, 1) | np.roll(out, -1, 1)
    return out
# Pre: per-pixel most recent clear observation, newest first (01 Jan and 27 Dec are ~fully cloudy).
PRE_IDS = ["S2A_17PNK_20250111_0_L2A", "S2B_17PNK_20250106_0_L2A", "S2A_17PNK_20241222_0_L2A"]
# Post: first scene after the fire with >= 90 % clear window.
POST_ID = "S2C_17PNK_20250121_0_L2A"
MIN_PATCH_HA = 5.0
THRESHOLDS = (0.10, 0.20, 0.30, 0.40)


def window():
    x, y = g.to_utm.transform(*CENTER)
    snap = lambda v: 499980 + round((v - 499980) / 20) * 20
    return snap(x - HALF), snap(y - HALF), snap(x + HALF), snap(y + HALF)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bbox = window()
    def nbr_of(it):
        b8 = np.clip(g.reflectance(it, "nir", bbox, to20=True), 0, None)
        b12 = np.clip(g.reflectance(it, "swir22", bbox), 0, None)
        den = b8 + b12
        return np.where(den > 0.02, (b8 - b12) / np.where(den > 0.02, den, 1), np.nan)

    cloudy = lambda scl: np.isin(scl, [3, 8, 9, 10])
    ok = lambda scl: np.isin(scl, list(g.SCL_VALID)) & (scl != 6) & ~dilate(cloudy(scl), CLOUD_BUFFER_PX)
    post = g.item(POST_ID)
    scl_post = g.read(post, "scl", bbox)
    nbr = {"post": nbr_of(post)}
    pre_nbr = np.full(scl_post.shape, np.nan, np.float32)
    pre_src = np.full(scl_post.shape, -1, np.int8)
    pre_items, pre_report = [], []
    for k, id_ in enumerate(PRE_IDS):
        it = g.item(id_)
        pre_items.append(it)
        scl = g.read(it, "scl", bbox)
        n_ = nbr_of(it)
        fill = (pre_src < 0) & ok(scl) & np.isfinite(n_)
        pre_nbr[fill] = n_[fill]
        pre_src[fill] = k
        pre_report.append({"id": id_, "datetime": it["properties"]["datetime"], "window_clear_fraction": round(float(ok(scl).mean()), 4), "pixels_used_fraction": round(float(fill.mean()), 4)})
    nbr["pre"] = pre_nbr
    pre = pre_items[0]
    post_report = [{"id": POST_ID, "datetime": post["properties"]["datetime"], "window_clear_fraction": round(float(ok(scl_post).mean()), 4)}]
    valid = (pre_src >= 0) & ok(scl_post) & np.isfinite(nbr["post"])
    dnbr = np.where(valid, nbr["pre"] - nbr["post"], np.nan)
    px_ha = 0.04
    xmin, ymin, xmax, ymax = bbox
    H, W = dnbr.shape
    rr, cc = np.indices((H, W))
    px_x, px_y = xmin + (cc + 0.5) * 20, ymax - (rr + 0.5) * 20
    ax, ay = g.to_utm.transform(*ANCHOR)
    sx, sy = g.to_utm.transform(*SIGNAL)
    dist_anchor = np.hypot(px_x - ax, px_y - ay)

    # Candidate patches at 0.20, the same reference threshold as Guacamaya.
    burned = valid & (np.nan_to_num(dnbr, nan=-9) > 0.20)
    lab, n = g.components(burned)
    ids, counts = np.unique(lab[lab > 0], return_counts=True)
    patches = []
    for pid, cnt in sorted(zip(ids, counts), key=lambda p: -p[1]):
        ha = cnt * px_ha
        if ha < MIN_PATCH_HA:
            break
        m = lab == pid
        cy, cx = np.argwhere(m).mean(axis=0)
        x, y = xmin + (cx + 0.5) * 20, ymax - (cy + 0.5) * 20
        lon, lat = g.to_ll.transform(x, y)
        patches.append({
            "rank": len(patches) + 1,
            "area_ha": round(float(ha), 1),
            "convex_hull_ha": round(g.hull_area_px(m) * px_ha, 1),
            "median_dnbr": round(float(np.nanmedian(dnbr[m])), 3),
            "centroid": [round(lon, 6), round(lat, 6)],
            "min_distance_to_anchor_m": round(float(dist_anchor[m].min())),
            "distance_centroid_to_firms_signal_m": round(math.hypot(x - sx, y - sy)),
            "pre_date_fraction": {PRE_IDS[k][10:18]: round(float((pre_src[m] == k).mean()), 3) for k in range(len(PRE_IDS))},
            "touches_window_edge": bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any()),
            "_mask": m,
        })
    within5 = [p for p in patches if p["min_distance_to_anchor_m"] <= 5000]
    sens = []
    for t in THRESHOLDS:
        b = valid & (np.nan_to_num(dnbr, nan=-9) > t)
        sens.append({"threshold": t, "window_ha": round(float(b.sum()) * px_ha, 1),
                     "within_5km_of_anchor_ha": round(float((b & (dist_anchor <= 5000)).sum()) * px_ha, 1)})

    focus = within5[0] if within5 else None
    cand_mask = np.zeros((H, W), bool)
    for p_ in patches[:12]:
        cand_mask |= p_["_mask"]
    linked = [p_ for p_ in patches if p_["distance_centroid_to_firms_signal_m"] <= 500]
    link_mask = linked[0]["_mask"] if linked else np.zeros((H, W), bool)

    def rgb(it):
        return np.stack([g.reflectance(it, k, bbox) for k in ("red", "green", "blue")], axis=-1)
    src10 = np.repeat(np.repeat(pre_src, 2, 0), 2, 1)
    pre_rgb = np.zeros(src10.shape + (3,), np.float32)
    for k, it in enumerate(pre_items):
        r = rgb(it)
        pre_rgb[src10 == k] = r[src10 == k]
    pre_rgb[src10 < 0] = rgb(pre_items[0])[src10 < 0]  # no clear pre: show the 11 Jan scene as is
    post_rgb = rgb(post)
    st = lambda a: (np.clip(np.nan_to_num(a) / 0.25, 0, 1) ** (1 / 1.6) * 255).astype(np.uint8)
    h10, w10 = src10.shape
    yy, xx = np.indices((h10, w10))
    dd = np.minimum.reduce([yy, xx, h10 - 1 - yy, w10 - 1 - xx]).astype(np.float32)
    al = np.clip(dd / 90, 0, 1)
    al = (al * al * (3 - 2 * al) * 255).astype(np.uint8)
    for name, arr in (("pre", pre_rgb), ("post", post_rgb)):
        Image.fromarray(np.dstack([st(arr), al]), "RGBA").save(OUT / f"{name}_detail.webp", quality=88, method=6)
    g.dnbr_png(dnbr, valid, cand_mask, OUT / "dnbr.png")
    border = link_mask & ~(np.roll(link_mask, 1, 0) & np.roll(link_mask, -1, 0) & np.roll(link_mask, 1, 1) & np.roll(link_mask, -1, 1))
    ol = np.zeros((H, W, 4), dtype=np.uint8)
    ol[border] = (26, 25, 23, 230)
    Image.fromarray(ol, "RGBA").resize((W * 2, H * 2), Image.NEAREST).save(OUT / "outline.png", optimize=True)

    corners = [g.to_ll.transform(x, y) for x, y in ((xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin))]
    summary = {
        "status": "exploratory_v2_spike_not_firepa_v1",
        "question": "Did a new burn scar appear near the approximate Los Picachos anchor between the last clear scene before and the first clear scene after 16 Jan 2025?",
        "method": {
            "index": "NBR=(B8-B12)/(B8+B12); dNBR=NBR_pre-NBR_post",
            "grid": "EPSG:32617, 20 m",
            "cloud_mask": "SCL classes 2,4,5,7 valid, minus a 300 m buffer around SCL cloud/shadow (3,8,9,10) in each date; water excluded. Pre side is a per-pixel latest-clear mosaic (11 Jan, then 6 Jan, then 22 Dec), so a scar may include burns from 22 Dec onward where older scenes fill in",
            "window_m": [xmin, ymin, xmax, ymax],
            "candidate_rule": f"8-connected dNBR>0.20 patches >= {MIN_PATCH_HA} ha; no FIRMS linkage (none within 5 km)",
            "offset_check": "same as s2_guacamaya.py",
        },
        "pre": {"id": pre["id"], "datetime": pre["properties"]["datetime"], "mode": "per-pixel most recent clear of " + ", ".join(PRE_IDS)},
        "post": {"id": post["id"], "datetime": post["properties"]["datetime"]},
        "candidates": {"pre": pre_report, "post": post_report},
        "valid_overlap_fraction": round(float(valid.mean()), 4),
        "valid_fraction_within_5km": round(float(valid[dist_anchor <= 5000].mean()), 4),
        "sensitivity": sens,
        "patches": [{k: v for k, v in p.items() if k != "_mask"} for p in patches[:12]],
        "focus_patch_rank": focus["rank"] if focus else None,
        "firms_linked_patch_rank": linked[0]["rank"] if linked else None,
        "pre_mosaic_fraction": {PRE_IDS[k][10:18]: round(float((pre_src == k).mean()), 4) for k in range(len(PRE_IDS))},
        "corners_lonlat": [[round(a, 6), round(b, 6)] for a, b in corners],
        "attribution": "Contains modified Copernicus Sentinel data 2024-2025",
    }
    (OUT / "s2.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("pre", "post", "valid_overlap_fraction", "valid_fraction_within_5km", "sensitivity", "patches", "focus_patch_rank")}, indent=1))
    print("bytes fetched", cog.bytes_fetched)


if __name__ == "__main__":
    main()
