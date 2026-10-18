"""Display layers for a measured dNBR scar: a smooth raster fill and a vector outline.

Measurement stays on the 20 m grid. These layers only change how the same
cells are drawn: the fill is upsampled bilinearly so the 20 m steps do not
read as blocks, and the outline is the exact union of the linked cells,
lightly rounded for display (corners only; the area is reported from cells).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

to_ll = Transformer.from_crs(32617, 4326, always_xy=True)
UP = 4  # display upsampling: 20 m cells drawn at 5 m


def _resize(a: np.ndarray, w: int, h: int) -> np.ndarray:
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((w, h), Image.BILINEAR))


def fill_webp(dnbr: np.ndarray, valid: np.ndarray, linked: np.ndarray, path: Path, water: np.ndarray | None = None) -> None:
    """Warm ramp on the linked scar, faint grey for other change, flat grey where no data (water is not 'no data')."""
    h, w = dnbr.shape
    W, H = w * UP, h * UP
    d = _resize(np.nan_to_num(dnbr, nan=0.0), W, H)
    lk = _resize(linked.astype(np.float32), W, H)
    other = _resize((valid & (np.nan_to_num(dnbr, nan=-1) > 0.20) & ~linked).astype(np.float32), W, H)
    nod = _resize((~valid & (~water if water is not None else True)).astype(np.float32), W, H)
    # Charred ramp: light change reads as scorched amber, strong change as charcoal.
    stops = np.array([0.20, 0.35, 0.55, 0.85])
    cols = np.array([[205, 118, 58], [150, 56, 32], [86, 30, 22], [38, 18, 16]], dtype=float)
    img = np.zeros((H, W, 4), dtype=np.float32)
    for k in range(3):
        img[..., k] = np.interp(d, stops, cols[:, k])
    # Edge softness comes from the bilinear mask; 0.5 is the cell boundary.
    a_link = np.clip((lk - 0.25) / 0.5, 0, 1)
    img[..., 3] = (150 + 70 * np.clip((d - 0.2) / 0.5, 0, 1)) * a_link
    a_other = np.clip((other - 0.25) / 0.5, 0, 1) * (1 - a_link)
    img[..., :3] = img[..., :3] * (1 - a_other[..., None]) + np.array([96, 92, 86]) * a_other[..., None]
    img[..., 3] = np.maximum(img[..., 3], 70 * a_other)
    a_nod = np.clip((nod - 0.25) / 0.5, 0, 1) * (1 - a_link)
    img[..., :3] = img[..., :3] * (1 - a_nod[..., None]) + 128 * a_nod[..., None]
    img[..., 3] = np.maximum(img[..., 3], 120 * a_nod)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA").save(path, quality=88, method=6)


def _chaikin(coords, n=2):
    pts = np.asarray(coords[:-1], dtype=float)
    for _ in range(n):
        nxt = np.roll(pts, -1, axis=0)
        pts = np.stack([0.75 * pts + 0.25 * nxt, 0.25 * pts + 0.75 * nxt], axis=1).reshape(-1, 2)
    return np.vstack([pts, pts[:1]])


def outline_geojson(mask: np.ndarray, bbox, path: Path, min_ha: float = 1.0) -> dict:
    """Union of the mask's 20 m cells as rounded polygons in lon/lat."""
    xmin, _, _, ymax = bbox
    rows, cols = np.nonzero(mask)
    cells = [box(xmin + c * 20, ymax - (r + 1) * 20, xmin + (c + 1) * 20, ymax - r * 20) for r, c in zip(rows, cols)]
    geom = unary_union(cells)
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    feats = []
    for p in sorted(polys, key=lambda g: -g.area):
        if p.area / 1e4 < min_ha:
            continue
        area_ha = round(p.area / 1e4, 1)
        p = p.simplify(8)
        rings = [_chaikin(list(p.exterior.coords))] + [_chaikin(list(i.coords)) for i in p.interiors if Polygon(i).area / 1e4 >= 0.5]
        ll = [[[round(a, 6), round(b, 6)] for a, b in zip(*to_ll.transform(r[:, 0], r[:, 1]))] for r in rings]
        feats.append({"type": "Feature", "properties": {"cell_area_ha": area_ha},
                      "geometry": {"type": "Polygon", "coordinates": ll}})
    fc = {"type": "FeatureCollection", "features": feats}
    path.write_text(json.dumps(fc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    return fc
