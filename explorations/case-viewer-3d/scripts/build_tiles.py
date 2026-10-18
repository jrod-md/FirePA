"""Build the terrain tiles and the Guacamaya case from real inputs only.

Inputs
  - Copernicus DEM GLO-30 tiles N08 W081 and N09 W081 (DSM, EPSG:4326, pixel-is-point).
  - FirePA public package (repo/site-data): six Guacamaya clusters and the
    approximate external-reference anchor. Nothing is recomputed.

Outputs (in ../web)
  - tiles/dem/{z}/{x}/{y}.png      Terrarium-encoded elevation for MapLibre terrain.
  - tiles/relief/{z}/{x}/{y}.webp  Shaded relief texture (neutral tint, not land cover).
  - data/case.json                 Clusters, anchor, timeline and provenance.
  - data/validation.json           Elevation sanity checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from case_registry import CASES

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]  # explorations/case-viewer-3d -> repository root
RAW_DIR = ROOT / "data" / "raw"
RAW = RAW_DIR / "Copernicus_DSM_COG_10_N08_00_W081_00_DEM.tif"
RAW_N = RAW_DIR / "Copernicus_DSM_COG_10_N09_00_W081_00_DEM.tif"
WEB = ROOT / "web"

# Area of interest around Cerro Guacamaya (lon/lat, WGS84).
AOI = (-80.62, 8.38, -80.30, 8.66)
# Terrain covers all of Coclé and out to the edge of the downloaded DEM, so the
# horizon shows real relief instead of the mesh smearing at the data edge.
TILE_AOI = (-80.995, 8.005, -80.005, 9.30)
# Detailed relief (z12-14) only around each case; elsewhere z8-11 is enough.
# Each case's viewer camera stays inside its box.
CASE_AOIS = {"guacamaya": AOI, **{k: tuple(v["view_aoi"]) for k, v in CASES.items()}}
DEM_ZOOMS = range(8, 13)  # ~38 m/px at z12, close to the 30 m source.
RELIEF_ZOOMS = range(8, 12)
RELIEF_HI_ZOOMS = range(12, 15)
TILE = 256
GUACAMAYA_IDS = ["evt-0557", "evt-0230", "evt-0078", "evt-0383", "evt-0320", "evt-0284"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_dem(path: Path) -> tuple[np.ndarray, float, float, float]:
    im = Image.open(path)
    scale = im.tag_v2[33550]
    tie = im.tag_v2[33922]
    geokeys = im.tag_v2[34735]
    # GeoKey 1025 (GTRasterTypeGeoKey) == 2 means pixel-is-point.
    keys = {geokeys[i]: geokeys[i + 3] for i in range(4, len(geokeys), 4)}
    if keys.get(1025) != 2 or keys.get(2048) != 4326:
        sys.exit("Unexpected DEM georeferencing")
    return np.asarray(im, dtype=np.float32), tie[3], tie[4], scale[0]


def load_dem() -> tuple[np.ndarray, float, float, float]:
    south, lon0, lat0, res = _read_dem(RAW)
    north, nlon0, nlat0, nres = _read_dem(RAW_N)
    # N09 ends one row above N08's first row (pixel-is-point), so they stack exactly.
    if (nlon0, nres) != (lon0, res) or abs(nlat0 - north.shape[0] * res - lat0) > 1e-9:
        sys.exit("DEM tiles do not share a grid")
    dem, lat0 = np.vstack([north, south]), nlat0
    # Crop with a margin so hillshade edges and tile sampling stay valid.
    m = 0.02
    c0 = int(math.floor((TILE_AOI[0] - m - lon0) / res))
    c1 = int(math.ceil((TILE_AOI[2] + m - lon0) / res)) + 1
    r0 = int(math.floor((lat0 - (TILE_AOI[3] + m)) / res))
    r1 = int(math.ceil((lat0 - (TILE_AOI[1] - m)) / res)) + 1
    c0, r0 = max(c0, 0), max(r0, 0)
    c1, r1 = min(c1, dem.shape[1]), min(r1, dem.shape[0])
    crop = dem[r0:r1, c0:c1].copy()
    return crop, lon0 + c0 * res, lat0 - r0 * res, res


def sample(grid: np.ndarray, lon0: float, lat0: float, res: float, lon, lat):
    """Bilinear sample; grid[r, c] centre is (lon0 + c*res, lat0 - r*res)."""
    c = (np.asarray(lon) - lon0) / res
    r = (lat0 - np.asarray(lat)) / res
    c = np.clip(c, 0, grid.shape[1] - 1.001)
    r = np.clip(r, 0, grid.shape[0] - 1.001)
    c0 = np.floor(c).astype(int)
    r0 = np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    if grid.ndim == 3:
        fc, fr = fc[..., None], fr[..., None]
    a = grid[r0, c0] * (1 - fc) + grid[r0, c0 + 1] * fc
    b = grid[r0 + 1, c0] * (1 - fc) + grid[r0 + 1, c0 + 1] * fc
    return a * (1 - fr) + b * fr


def shaded_relief(dem: np.ndarray, lat_mid: float, res: float) -> np.ndarray:
    dy = res * 110_574.0
    dx = res * 111_320.0 * math.cos(math.radians(lat_mid))
    gy, gx = np.gradient(dem, dy, dx)
    gy = -gy  # rows go south; make +y north
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = np.zeros_like(dem)
    # Multi-directional hillshade, weighted toward the classic NW light.
    for az, w in ((315, 0.45), (270, 0.2), (360, 0.2), (225, 0.15)):
        azr = math.radians(az)
        alt = math.radians(42)
        hs = math.sin(alt) * np.cos(slope) + math.cos(alt) * np.sin(slope) * np.cos(azr - aspect)
        shade += w * np.clip(hs, 0, 1)

    # Neutral, paper-toned hypsometric tint: encodes height only, never vegetation.
    stops = np.array([0, 80, 220, 420, 700, 1200], dtype=np.float32)
    colors = np.array(
        [[232, 226, 213], [222, 213, 196], [207, 194, 172], [190, 174, 150], [214, 204, 188], [240, 236, 228]],
        dtype=np.float32,
    )
    e = np.clip(dem, stops[0], stops[-1])
    tint = np.stack([np.interp(e, stops, colors[:, k]) for k in range(3)], axis=-1)
    light = 0.38 + 0.82 * shade[..., None]
    rgb = np.clip(tint * light, 0, 255)
    water = dem <= 0.5
    rgb[water] = (172, 190, 200)
    return rgb.astype(np.float32)


def tile_lonlat(z: int, x: int, y: int):
    n = 2**z
    px = (np.arange(TILE) + 0.5) / TILE
    lon = (x + px) / n * 360.0 - 180.0
    merc = math.pi * (1 - 2 * (y + px) / n)
    lat = np.degrees(np.arctan(np.sinh(merc)))
    return np.meshgrid(lon, lat)


def tile_range(z: int, aoi=TILE_AOI):
    def tx(lon):
        return int((lon + 180) / 360 * 2**z)

    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2**z)

    return range(tx(aoi[0]), tx(aoi[2]) + 1), range(ty(aoi[3]), ty(aoi[1]) + 1)


def inside_aoi(lon, lat):
    return (lon >= TILE_AOI[0]) & (lon <= TILE_AOI[2]) & (lat >= TILE_AOI[1]) & (lat <= TILE_AOI[3])


def tile_jobs():
    for z in DEM_ZOOMS:
        xs, ys = tile_range(z)
        yield from (("dem", z, x, y) for x in xs for y in ys)
    for z in RELIEF_ZOOMS:
        xs, ys = tile_range(z)
        yield from (("relief", z, x, y) for x in xs for y in ys)
    hi = set()
    for aoi in CASE_AOIS.values():
        for z in RELIEF_HI_ZOOMS:
            xs, ys = tile_range(z, aoi)
            hi.update((z, x, y) for x in xs for y in ys)
    yield from (("relief", z, x, y) for z, x, y in sorted(hi))


def write_tiles(dem, relief, lon0, lat0, res) -> dict:
    counts = {"dem": 0, "relief": 0}
    if (WEB / "tiles").exists():
        shutil.rmtree(WEB / "tiles")  # no stale tiles from an earlier extent
    for kind, z, x, y in tile_jobs():
        lon, lat = tile_lonlat(z, x, y)
        out = WEB / "tiles" / kind / str(z) / str(x)
        out.mkdir(parents=True, exist_ok=True)
        if kind == "dem":
            h = sample(dem, lon0, lat0, res, lon, lat).astype(np.float64)
            # Whole metres: sub-metre noise in a 30 m DSM is invisible but defeats PNG compression.
            v = np.round(np.clip(h, -100, 9000)) + 32768.0
            r = np.floor(v / 256)
            g = np.floor(v - r * 256)
            b = np.floor((v - np.floor(v)) * 256)
            img = np.stack([r, g, b], axis=-1).astype(np.uint8)
            Image.fromarray(img, "RGB").save(out / f"{y}.png", optimize=True)
        else:
            rgb = sample(relief, lon0, lat0, res, lon, lat)
            alpha = np.where(inside_aoi(lon, lat), 255, 0)[..., None]
            img = np.concatenate([rgb, alpha], axis=-1).astype(np.uint8)
            Image.fromarray(img, "RGBA").save(out / f"{y}.webp", quality=82, method=6)
        counts[kind] += 1
    return counts


def build_case(dem, lon0, lat0, res) -> tuple[dict, dict]:
    site = REPO / "site-data"
    events = json.loads((site / "events.geojson").read_text(encoding="utf-8"))
    timeline = json.loads((site / "guacamaya-timeline.json").read_text(encoding="utf-8"))
    refs = json.loads((site / "external-references.geojson").read_text(encoding="utf-8"))

    by_id = {f["properties"]["public_event_id"]: f for f in events["features"]}
    clusters = []
    for c in timeline["clusters"]:
        f = by_id[c["public_event_id"]]
        lon, lat = f["geometry"]["coordinates"]
        clusters.append(
            {
                **c,
                "centroid": [lon, lat],
                "optical_cohort_status": f["properties"]["optical_cohort_status"],
                "duration_hours": f["properties"]["duration_hours"],
                "dsm_elevation_m": round(float(sample(dem, lon0, lat0, res, lon, lat)), 1),
            }
        )
    anchor = next(f for f in refs["features"] if f["properties"]["reference_name"] == "Cerro Guacamaya")

    case = {
        "aoi": AOI,
        "tile_aoi": TILE_AOI,
        "detail_aoi": CASE_AOIS["guacamaya"],
        "clusters": clusters,
        "anchor": {
            "coordinates": anchor["geometry"]["coordinates"],
            **{k: anchor["properties"][k] for k in (
                "reference_name", "anchor_status", "coordinate_claimed_by_source",
                "official_window_start", "official_window_end", "official_matching_radius_m",
                "official_match_count", "temporal_span_hours", "inter_cluster_gaps_gt_6h",
                "source_document_count",
            )},
        },
        "timeline_window": timeline["timeline_window"],
        "temporal_span_hours": timeline["temporal_span_hours"],
        "provenance": {
            "firepa_package": timeline["package_version"],
            "firepa_files": {
                p: sha256(site / p)
                for p in ("events.geojson", "guacamaya-timeline.json", "external-references.geojson")
            },
            "dem": {
                "product": "Copernicus DEM GLO-30 (DSM)",
                "file": RAW.name,
                "sha256": sha256(RAW),
                "files": {p.name: sha256(p) for p in (RAW, RAW_N)},
                "source": "https://copernicus-dem-30m.s3.amazonaws.com/",
                "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved",
            },
        },
    }

    aoi_mask = dem  # crop already ~AOI + margin
    validation = {
        "dem_shape": list(dem.shape),
        "dem_min_m": round(float(aoi_mask.min()), 1),
        "dem_max_m": round(float(aoi_mask.max()), 1),
        "nodata_or_nan": int(np.isnan(dem).sum()),
        "cluster_elevations_m": {c["public_event_id"]: c["dsm_elevation_m"] for c in clusters},
        "anchor_elevation_m": round(
            float(sample(dem, lon0, lat0, res, *anchor["geometry"]["coordinates"])), 1
        ),
        "notes": [
            "Copernicus DEM is a surface model: values include canopy and buildings.",
            "Cluster points are FirePA display centroids, not fire locations or perimeters.",
        ],
    }
    return case, validation


def main() -> None:
    dem, lon0, lat0, res = load_dem()
    relief = shaded_relief(dem, (TILE_AOI[1] + TILE_AOI[3]) / 2, res)
    counts = write_tiles(dem, relief, lon0, lat0, res)
    case, validation = build_case(dem, lon0, lat0, res)
    validation["tile_counts"] = counts
    (WEB / "data").mkdir(parents=True, exist_ok=True)
    # Presentation-only Coclé outline, the same one the publication site uses.
    (WEB / "data" / "cocle.geojson").write_bytes((REPO / "site" / "src" / "data" / "cocle-presentation.geojson").read_bytes())
    (WEB / "data" / "case.json").write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    (WEB / "data" / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
