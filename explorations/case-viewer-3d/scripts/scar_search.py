"""Satellite-first screening for 2025 dry-season burn scars in Coclé (exploratory, not FirePA v1).

Sentinel-2 tile 17PNK covers almost all of Coclé. Every scene from mid-December
2024 to mid-May 2025 is read at the COGs' internal ~80 m overview (only that
level is downloaded, and nothing is cached to disk). Clear pixels (SCL 2, 4,
5, 7, at least 160 m from cloud or shadow) are combined into a per-pixel
median NBR for each period, and consecutive periods are differenced.

A candidate scar is an 8-connected patch inside Coclé where dNBR > 0.27 and the
later NBR < 0.10, of at least 40 ha. This is a screening rule to find cases,
not an area estimate: chosen cases are measured again at 20 m with a scene pair.
FIRMS events from the FirePA v1 package are counted as independent
corroboration (centroid within 1 km of the patch, start inside the period pair).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.prepared import prep

import cog
from s2_guacamaya import components, shift

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = ROOT / "results" / "scar_search"
SEARCH = "https://earth-search.aws.element84.com/v1/search"
TILE = "17PNK"
PERIODS = [  # inclusive start, exclusive end (UTC dates)
    ("dic–ene", "2024-12-10", "2025-01-21"),
    ("ene–feb", "2025-01-21", "2025-02-21"),
    ("feb–mar", "2025-02-21", "2025-03-21"),
    ("mar–abr", "2025-03-21", "2025-04-21"),
    ("abr–may", "2025-04-21", "2025-05-21"),
]
SCL_VALID = {2, 4, 5, 7}
SCL_CLOUD = {3, 8, 9, 10}
DNBR_T, NBR_POST_T, MIN_HA = 0.27, 0.10, 40.0
LINK_M = 1000

to_utm = Transformer.from_crs(4326, 32617, always_xy=True)
to_ll = Transformer.from_crs(32617, 4326, always_xy=True)


def scenes() -> list[dict]:
    body = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [-80.5, 8.6]},
            "datetime": f"{PERIODS[0][1]}T00:00:00Z/{PERIODS[-1][2]}T00:00:00Z",
            "query": {"eo:cloud_cover": {"lt": 75}}, "limit": 200}
    req = urllib.request.Request(SEARCH, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        feats = [f for f in json.load(r)["features"] if f"_{TILE}_" in f["id"]]
    # One scene per date (duplicates are reprocessings); keep the latest processing.
    by_date = {}
    for f in sorted(feats, key=lambda f: f["properties"].get("updated", "")):
        by_date[f["properties"]["datetime"][:10]] = f
    return [by_date[d] for d in sorted(by_date)]


def read_level(it, key, level):
    c = cog.COG.open(it["assets"][key]["href"], level)
    return c.read(0, 0, c.width, c.height), c


def scene_nbr(it):
    nir, c = read_level(it, "nir", 3)
    sw, _ = read_level(it, "swir22", 2)
    scl, _ = read_level(it, "scl", 2)
    n = min(nir.shape[0], sw.shape[0], scl.shape[0])
    nir, sw, scl = nir[:n, :n].astype(np.float32), sw[:n, :n].astype(np.float32), scl[:n, :n]
    # Same empirical offset rule as s2_guacamaya.reflectance: these COGs already carry it.
    b8, b12 = np.clip(nir * 1e-4, 0, None), np.clip(sw * 1e-4, 0, None)
    den = b8 + b12
    nbr = np.where(den > 0.02, (b8 - b12) / np.where(den > 0.02, den, 1), np.nan)
    cloud = np.isin(scl, list(SCL_CLOUD))
    near = cloud.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dy * dy + dx * dx <= 4:
                near |= shift(cloud, dy, dx)
    valid = np.isin(scl, list(SCL_VALID)) & ~near & (nir > 0) & np.isfinite(nbr)
    return np.where(valid, nbr, np.nan).astype(np.float32), c


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cocle = shape(json.loads((ROOT / "web" / "data" / "cocle.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
    items = scenes()
    print(len(items), "scenes", [i["properties"]["datetime"][:10] for i in items])
    stacks = {p[0]: [] for p in PERIODS}
    used = {p[0]: [] for p in PERIODS}
    grid = None
    # Period medians are kept in the local cache so a rerun downloads nothing.
    cache = ROOT / "data" / "s2_cache" / f"scar_search_{TILE}_medians.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        med_cached, used, grid = {k: z[k] for k in stacks}, z["used"].item(), z["grid"].item()
        items = []
    for it in items:
        d = it["properties"]["datetime"][:10]
        period = next((p[0] for p in PERIODS if p[1] <= d < p[2]), None)
        if not period:
            continue
        nbr, c = scene_nbr(it)
        frac = float(np.isfinite(nbr).mean())
        print(d, period, f"clear {frac:.2f}", f"{cog.bytes_fetched / 1e6:.0f} MB", flush=True)
        if frac < 0.05:
            continue
        grid = grid or c
        stacks[period].append(nbr)
        used[period].append({"id": it["id"], "clear_fraction": round(frac, 3)})

    if items:
        med_cached = None
        grid = {"res": grid.res[0], "origin": grid.origin}
    res = grid["res"]
    x0, y0 = grid["origin"]
    n = (med_cached[PERIODS[0][0]] if med_cached is not None else stacks[PERIODS[0][0]][0]).shape[0]
    rr, cc = np.indices((n, n))
    lon, lat = to_ll.transform(x0 + (cc + 0.5) * res, y0 - (rr + 0.5) * res)
    pc = prep(cocle)
    bx = cocle.bounds
    inside = (lon >= bx[0]) & (lon <= bx[2]) & (lat >= bx[1]) & (lat <= bx[3])
    idx = np.argwhere(inside)
    in_cocle = np.zeros((n, n), dtype=bool)
    for r, c_ in idx:
        in_cocle[r, c_] = pc.contains(Point(lon[r, c_], lat[r, c_]))

    med = {}
    for name, arrs in stacks.items():
        if med_cached is not None:
            med[name] = med_cached[name]
        else:
            with np.errstate(all="ignore"):
                med[name] = np.nanmedian(np.stack(arrs), axis=0) if arrs else np.full((n, n), np.nan)
        print(name, len(used[name]), f"valid in Coclé {np.isfinite(med[name])[in_cocle].mean():.2f}")
    if med_cached is None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, **med, used=np.array(used, dtype=object), grid=np.array(grid, dtype=object))

    events = json.loads((REPO / "site-data" / "events.geojson").read_text(encoding="utf-8"))["features"]
    ev = [(e["properties"]["public_event_id"], e["properties"]["start_time_utc"][:10], *to_utm.transform(*e["geometry"]["coordinates"]),
           e["properties"]["detection_count"], e["properties"]["frp_max_mw"]) for e in events]
    px_ha = res * res / 1e4
    candidates = []
    cum = np.zeros((n, n), dtype=bool)
    for (a, a0, _), (b, b0, b1) in zip(PERIODS, PERIODS[1:]):
        d = med[a] - med[b]
        burned = in_cocle & np.isfinite(d) & (d > DNBR_T) & (med[b] < NBR_POST_T)
        cum |= burned
        lab, k = components(burned)
        ids, counts = np.unique(lab[lab > 0], return_counts=True)
        for i, cnt in zip(ids, counts):
            ha = cnt * px_ha
            if ha < MIN_HA:
                continue
            m = lab == i
            r, c_ = np.nonzero(m)
            ux, uy = x0 + (c_ + 0.5) * res, y0 - (r + 0.5) * res
            linked = []
            for eid, day, ex, ey, det, frp in ev:
                if a0 <= day < b1 and np.min(np.hypot(ux - ex, uy - ey)) <= LINK_M:
                    linked.append({"id": eid, "date": day, "detections": det, "frp_max_mw": frp})
            h, w = np.ptp(r) + 1, np.ptp(c_) + 1
            clon, clat = to_ll.transform(float(ux.mean()), float(uy.mean()))
            candidates.append({
                "pair": f"{a} → {b}", "area_ha_80m": round(ha, 0), "median_dnbr": round(float(np.median(d[m])), 2),
                "centroid": [round(clon, 5), round(clat, 5)],
                "bbox_fill": round(cnt / (h * w), 2),
                "firms_events": len(linked), "firms_detections": sum(e["detections"] for e in linked),
                "firms_max_frp_mw": max((e["frp_max_mw"] for e in linked), default=None), "firms": linked,
            })
    candidates.sort(key=lambda c: -c["area_ha_80m"])
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    # Quick-look map: Coclé mask, cumulative candidate pixels, FIRMS events.
    img = np.full((n, n, 3), 235, dtype=np.uint8)
    img[in_cocle] = (205, 210, 196)
    img[cum] = (178, 40, 24)
    Image.fromarray(img).save(OUT / "quicklook.png", optimize=True)
    summary = {
        "status": "exploratory screening; outside FirePA Scientific Pilot v1",
        "tile": TILE, "grid_m": round(res, 2), "periods": PERIODS, "scenes_used": used,
        "rule": {"dnbr_gt": DNBR_T, "nbr_post_lt": NBR_POST_T, "min_area_ha": MIN_HA, "scl_valid": sorted(SCL_VALID),
                 "cloud_buffer_m": 160, "firms_link_m": LINK_M, "composite": "per-pixel median NBR per period"},
        "valid_fraction_in_cocle": {k: round(float(np.isfinite(v)[in_cocle].mean()), 3) for k, v in med.items()},
        "candidates": candidates,
    }
    (OUT / "candidates.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(candidates)} candidates; downloaded {cog.bytes_fetched / 1e6:.0f} MB")
    for c in candidates[:25]:
        print(c["rank"], c["pair"], c["area_ha_80m"], c["median_dnbr"], c["centroid"], "fill", c["bbox_fill"], "FIRMS", c["firms_events"], c["firms_detections"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
