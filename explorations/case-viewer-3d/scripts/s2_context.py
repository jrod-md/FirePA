"""Display imagery for the viewer (presentation only, no measurements).

- Context mosaics: the same pre/post Sentinel-2 scenes over the whole viewer
  AOI, read from the COGs' internal 20 m overview.
- Detail images: the 10 m pre/post crops re-encoded as WebP with feathered
  edges so they blend into the context mosaic.
The stretch matches s2_guacamaya.rgb_png so both layers read as one image.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

import cog
import s2_guacamaya as s2

WEB = s2.WEB
OUT = s2.OUT
AOI = json.loads((WEB / "data" / "case.json").read_text(encoding="utf-8"))["aoi"]


def utm_bbox(res: float):
    xs, ys = zip(*[s2.to_utm.transform(x, y) for x in (AOI[0], AOI[2]) for y in (AOI[1], AOI[3])])
    lo = lambda v: 499980 + np.floor((v - 499980) / res) * res
    hi = lambda v: 499980 + np.ceil((v - 499980) / res) * res
    return lo(min(xs)), lo(min(ys)), hi(max(xs)), hi(max(ys))


def stretch(rgb: np.ndarray) -> np.ndarray:
    return (np.clip(np.nan_to_num(rgb) / 0.25, 0, 1) ** (1 / 1.6) * 255).astype(np.uint8)


def context(item_id: str, name: str, bbox) -> list:
    it = s2.item(item_id)
    cache = s2.CACHE / f"{item_id}_ctx20_{'_'.join(str(int(v)) for v in bbox)}.npy"
    if cache.exists():
        rgb = np.load(cache)
    else:
        bands = []
        for key in ("red", "green", "blue"):
            c = cog.COG.open(it["assets"][key]["href"], level=1)
            bands.append(c.read_bbox(*bbox).astype(np.float32) * 1e-4)
        rgb = np.stack(bands, axis=-1)
        np.save(cache, rgb)
    Image.fromarray(stretch(rgb), "RGB").save(OUT / f"{name}_context.webp", quality=86, method=6)
    xmin, ymin, xmax, ymax = bbox
    return [[round(a, 6), round(b, 6)] for a, b in (s2.to_ll.transform(x, y) for x, y in ((xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)))]


def feather(name: str, edge_px: int = 70) -> None:
    im = np.asarray(Image.open(OUT / f"{name}.png").convert("RGB"))
    h, w = im.shape[:2]
    yy, xx = np.indices((h, w))
    d = np.minimum.reduce([yy, xx, h - 1 - yy, w - 1 - xx]).astype(np.float32)
    a = np.clip(d / edge_px, 0, 1)
    a = (a * a * (3 - 2 * a) * 255).astype(np.uint8)  # smoothstep
    Image.fromarray(np.dstack([im, a]), "RGBA").save(OUT / f"{name}_detail.webp", quality=88, method=6)


def main():
    summary = json.loads((OUT / "s2.json").read_text(encoding="utf-8"))
    bbox = utm_bbox(20)
    corners = {}
    for side in ("pre", "post"):
        corners[side] = context(summary[side]["id"], side, bbox)
        feather(side)
    summary["context"] = {
        "role": "presentation only; not used for any measurement",
        "resolution_m": 20,
        "source": "internal 20 m overview of the same Sentinel-2 L2A COGs",
        "utm_bbox": [float(v) for v in bbox],
        "corners_lonlat": corners["post"],
    }
    (OUT / "s2.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for f in sorted(OUT.glob("*.webp")):
        print(f.name, f.stat().st_size)
    print("bytes fetched", cog.bytes_fetched)


if __name__ == "__main__":
    main()
