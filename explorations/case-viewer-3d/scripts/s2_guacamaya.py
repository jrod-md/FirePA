"""Exploratory Sentinel-2 burned-area estimate for Cerro Guacamaya (not FirePA v1).

Mirrors the repo's dNBR design where possible (B8/B12, NBR_pre - NBR_post,
EPSG:32617 at 20 m, common pre/post valid mask, 0.10-0.40 descriptive
thresholds, 0.50 valid-overlap gate). Differences, stated in the output:
  - Cloud mask uses the Sentinel-2 Scene Classification (SCL), not Cloud Score+.
  - The analysis window is a fixed 12 x 12 km box around the burned massif,
    not the 500 m detection-buffer AOI, because the goal is the whole scar.
Only the internal COG tiles covering the window are downloaded.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

import cog

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = WEB / "data" / "s2"
STAC = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/"
PRE_IDS = ["S2C_17PNK_20250121_0_L2A", "S2B_17PNK_20250116_0_L2A", "S2A_17PNK_20250111_0_L2A", "S2B_17PNK_20250106_0_L2A"]
POST_IDS = ["S2C_17PNK_20250131_0_L2A", "S2B_17PNK_20250205_0_L2A", "S2C_17PNK_20250210_0_L2A", "S2B_17PNK_20250215_0_L2A"]
CENTER = (-80.467, 8.513)  # highest DSM point among the six clusters
HALF = 6000  # m
THRESHOLDS = (0.10, 0.20, 0.30, 0.40)
LINK_RADIUS = 1000  # m from a cluster centroid for a burned patch to count as linked
SCL_VALID = {2, 4, 5, 6, 7}  # dark, vegetation, bare, water, unclassified
CLEAR_TARGET = 0.95
REPORTED_HA = (1035, 1500)

to_utm = Transformer.from_crs(4326, 32617, always_xy=True)
to_ll = Transformer.from_crs(32617, 4326, always_xy=True)


def item(id_: str) -> dict:
    with urllib.request.urlopen(STAC + id_, timeout=60) as r:
        return json.load(r)


def band_scale(it: dict, key: str) -> tuple[float, float]:
    b = it["assets"][key].get("raster:bands", [{}])[0]
    return b.get("scale", 1e-4), b.get("offset", 0.0)


def window() -> tuple[float, float, float, float]:
    x, y = to_utm.transform(*CENTER)
    snap = lambda v: 499980 + round((v - 499980) / 20) * 20
    return snap(x - HALF), snap(y - HALF), snap(x + HALF), snap(y + HALF)


CACHE = ROOT / "data" / "s2_cache"
OFFSET_USED: dict = {}


def read(it: dict, key: str, bbox) -> np.ndarray:
    """Read the window once; later runs reuse the local crop."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{it['id']}_{key}_{'_'.join(str(int(v)) for v in bbox)}.npy"
    if f.exists():
        return np.load(f)
    a = cog.COG.open(it["assets"][key]["href"]).read_bbox(*bbox)
    np.save(f, a)
    return a


def reflectance(it, key, bbox, to20=False):
    dn = read(it, key, bbox).astype(np.float32)
    s, o = band_scale(it, key)
    # Empirical check: the STAC metadata advertises offset -0.1 (BOA_ADD_OFFSET),
    # but these COGs already have it removed (blue p5 ~190 DN; subtracting 1000
    # would make most vegetation negative). Apply the offset only if the data
    # still carries it.
    if o and np.percentile(dn[dn > 0], 5) < -o / s:
        o = 0.0
    OFFSET_USED[(it["id"], key)] = o
    r = dn * s + o
    r[dn == 0] = np.nan
    if to20:
        r = r.reshape(r.shape[0] // 2, 2, r.shape[1] // 2, 2).mean(axis=(1, 3))
    return r


def pick(ids, bbox, label):
    report = []
    for id_ in ids:
        it = item(id_)
        scl = read(it, "scl", bbox)
        frac = float(np.isin(scl, list(SCL_VALID)).mean())
        report.append({"id": id_, "datetime": it["properties"]["datetime"], "window_clear_fraction": round(frac, 4)})
        print(f"{label} {id_} clear={frac:.3f}")
        if frac >= CLEAR_TARGET:
            return it, scl, report
    best = max(report, key=lambda r: r["window_clear_fraction"])
    it = item(best["id"])
    return it, read(it, "scl", bbox), report


def components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    lab = np.zeros(mask.shape, dtype=np.int32)
    n = 0
    H, W = mask.shape
    for r0, c0 in zip(*np.nonzero(mask)):
        if lab[r0, c0]:
            continue
        n += 1
        lab[r0, c0] = n
        q = deque([(r0, c0)])
        while q:
            r, c = q.popleft()
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < H and 0 <= cc < W and mask[rr, cc] and not lab[rr, cc]:
                        lab[rr, cc] = n
                        q.append((rr, cc))
    return lab, n


def shift(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Shift a boolean mask without wrapping; cells shifted in from outside are False."""
    out = np.zeros_like(mask)
    h, w = mask.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = mask[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def border(mask: np.ndarray) -> np.ndarray:
    """Cells of mask with at least one 4-neighbour outside it (the window edge counts as outside)."""
    inner = shift(mask, 1, 0) & shift(mask, -1, 0) & shift(mask, 0, 1) & shift(mask, 0, -1)
    return mask & ~inner


def hull_area_px(mask: np.ndarray) -> float:
    """Convex-hull area, in pixel units, of the raster cells' full footprints (all cell corners)."""
    rc = np.argwhere(mask)
    corners = np.concatenate([rc[:, ::-1] + d for d in ((0, 0), (1, 0), (0, 1), (1, 1))])
    pts = sorted(set(map(tuple, corners.tolist())))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    h = lo[:-1] + up[:-1]
    return 0.5 * abs(sum(h[i][0] * h[(i + 1) % len(h)][1] - h[(i + 1) % len(h)][0] * h[i][1] for i in range(len(h))))


def rgb_png(it, bbox, path):
    bands = [reflectance(it, k, bbox) for k in ("red", "green", "blue")]
    rgb = np.stack(bands, axis=-1)
    rgb = np.clip(np.nan_to_num(rgb) / 0.25, 0, 1) ** (1 / 1.6)
    Image.fromarray((rgb * 255).astype(np.uint8), "RGB").save(path, optimize=True)


def dnbr_png(dnbr, valid, linked, path):
    """Linked scar (0.20) in a warm ramp; other change >0.20 as faint grey; invalid hatched."""
    h, w = dnbr.shape
    img = np.zeros((h, w, 4), dtype=np.uint8)
    stops = np.array([0.20, 0.30, 0.45, 0.70])
    cols = np.array([[222, 150, 80], [196, 87, 47], [140, 42, 28], [70, 18, 16]], dtype=float)
    d = np.nan_to_num(dnbr, nan=-1)
    m = linked
    for k in range(3):
        img[..., k][m] = np.interp(d[m], stops, cols[:, k]).astype(np.uint8)
    img[..., 3][m] = 215
    other = valid & (d > 0.20) & ~linked
    img[other] = (90, 88, 84, 70)
    img[~valid] = (128, 128, 128, 120)  # no valid data: flat translucent grey
    Image.fromarray(img, "RGBA").save(path, optimize=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bbox = window()
    pre, scl_pre, pre_report = pick(PRE_IDS, bbox, "pre")
    post, scl_post, post_report = pick(POST_IDS, bbox, "post")

    nbr = {}
    for name, it in (("pre", pre), ("post", post)):
        b8 = reflectance(it, "nir", bbox, to20=True)
        b12 = reflectance(it, "swir22", bbox)
        b8, b12 = np.clip(b8, 0, None), np.clip(b12, 0, None)
        denom = b8 + b12
        nbr[name] = np.where(denom > 0.02, (b8 - b12) / np.where(denom > 0.02, denom, 1), np.nan)
    valid = (np.isin(scl_pre, list(SCL_VALID)) & np.isin(scl_post, list(SCL_VALID))
             & np.isfinite(nbr["pre"]) & np.isfinite(nbr["post"])
             & (scl_pre != 6) & (scl_post != 6))
    dnbr = np.where(valid, nbr["pre"] - nbr["post"], np.nan)
    overlap = float(valid.mean())
    px_ha = 20 * 20 / 10_000

    case = json.loads((WEB / "data" / "case.json").read_text(encoding="utf-8"))
    xmin, ymin, xmax, ymax = bbox
    H, W = dnbr.shape
    seeds = np.zeros((H, W), dtype=bool)
    rr, cc = np.indices((H, W))
    px_x, px_y = xmin + (cc + 0.5) * 20, ymax - (rr + 0.5) * 20
    for c in case["clusters"]:
        x, y = to_utm.transform(*c["centroid"])
        seeds |= np.hypot(px_x - x, px_y - y) <= LINK_RADIUS

    areas = []
    linked_masks = {}
    for t in THRESHOLDS:
        burned = valid & (np.nan_to_num(dnbr, nan=-9) > t)
        lab, n = components(burned)
        linked_ids = set(np.unique(lab[seeds & burned])) - {0}
        linked = np.isin(lab, list(linked_ids))
        linked_masks[t] = linked
        ids, counts = np.unique(lab[linked], return_counts=True)
        main = lab == ids[np.argmax(counts)] if ids.size else np.zeros_like(linked)
        touches_edge = bool(linked[0].any() or linked[-1].any() or linked[:, 0].any() or linked[:, -1].any())
        areas.append({
            "threshold": t,
            "window_ha": round(float(burned.sum()) * px_ha, 1),
            "linked_ha": round(float(linked.sum()) * px_ha, 1),
            "linked_patches": len(linked_ids),
            "linked_touches_window_edge": touches_edge,
            "main_patch_ha": round(float(main.sum()) * px_ha, 1),
            "main_patch_convex_hull_ha": round(hull_area_px(main) * px_ha, 1) if main.any() else 0.0,
            "main_patch_median_dnbr": round(float(np.nanmedian(dnbr[main])), 3) if main.any() else None,
        })

    rgb_png(pre, bbox, OUT / "pre.png")
    rgb_png(post, bbox, OUT / "post.png")
    dnbr_png(dnbr, valid, linked_masks[0.20], OUT / "dnbr.png")
    # Outline of the linked area at 0.20 as a separate overlay for crisp display.
    edge = linked_masks[0.20]
    ol = np.zeros((H, W, 4), dtype=np.uint8)
    ol[border(edge)] = (26, 25, 23, 230)
    Image.fromarray(ol, "RGBA").resize((W * 2, H * 2), Image.NEAREST).save(OUT / "outline.png", optimize=True)

    corners = [to_ll.transform(x, y) for x, y in ((xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin))]
    d = dnbr[valid]
    summary = {
        "status": "exploratory_v2_spike_not_firepa_v1",
        "method": {
            "index": "NBR=(B8-B12)/(B8+B12); dNBR=NBR_pre-NBR_post",
            "grid": "EPSG:32617, 20 m (B8 averaged 2x2 from 10 m)",
            "cloud_mask": "Sentinel-2 SCL classes 2,4,5,7 valid in both dates; water (6) excluded; differs from repo's Cloud Score+",
            "window_m": [xmin, ymin, xmax, ymax],
            "linked_rule": f"8-connected dNBR patches with at least one pixel within {LINK_RADIUS} m of a FirePA cluster centroid",
            "thresholds_role": "descriptive sensitivity, not validated severity classes",
            "offset_check": "STAC advertises offset -0.1 but DN percentiles show it is already removed; reflectance = DN * 1e-4",
            "source": "Earth Search STAC (Element84), sentinel-2-l2a COGs on AWS; only intersecting COG tiles fetched",
        },
        "pre": {"id": pre["id"], "datetime": pre["properties"]["datetime"], "processing_baseline": pre["properties"].get("s2:processing_baseline")},
        "post": {"id": post["id"], "datetime": post["properties"]["datetime"], "processing_baseline": post["properties"].get("s2:processing_baseline")},
        "candidates": {"pre": pre_report, "post": post_report},
        "valid_overlap_fraction": round(overlap, 4),
        "passes_overlap_gate_0_50": overlap >= 0.5,
        "dnbr_stats": {k: round(float(v), 4) for k, v in zip(("p10", "p50", "p90", "p95", "max"), np.percentile(d, [10, 50, 90, 95, 100]))},
        "areas": areas,
        "reported_area_ha": list(REPORTED_HA),
        "corners_lonlat": [[round(a, 6), round(b, 6)] for a, b in corners],
        "outputs": {p.name: sha(p) for p in sorted(OUT.glob("*.png"))},
        "attribution": "Contains modified Copernicus Sentinel data 2025",
    }
    (OUT / "s2.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("bytes fetched", cog.bytes_fetched)
    print(json.dumps({k: summary[k] for k in ("pre", "post", "valid_overlap_fraction", "areas")}, indent=2))


if __name__ == "__main__":
    main()
