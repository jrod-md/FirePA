"""Before/after true-colour thumbnails for scar_search candidates (for choosing cases).

    python candidate_thumbs.py <rank> [<rank> ...]

Reads 4 x 4 km of the Sentinel-2 "visual" (TCI) asset at its 20 m overview from
the clearest scene of each period in the candidate's pair. Output goes to
results/scar_search/thumbs/ and is not used by the viewer.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image

import cog
import s2_guacamaya as g
from scar_search import OUT, PERIODS

HALF = 2000


def main(ranks):
    data = json.loads((OUT / "candidates.json").read_text(encoding="utf-8"))
    used = data["scenes_used"]
    (OUT / "thumbs").mkdir(exist_ok=True)
    for c in data["candidates"]:
        if c["rank"] not in ranks:
            continue
        a, b = c["pair"].split(" → ")
        x, y = g.to_utm.transform(*c["centroid"])
        snap = lambda v: 499980 + round((v - 499980) / 20) * 20
        bbox = (snap(x - HALF), snap(y - HALF), snap(x + HALF), snap(y + HALF))
        tiles = []
        for period in (a, b):
            best = max(used[period], key=lambda s: s["clear_fraction"])
            it = g.item(best["id"])
            img = cog.COG.open(it["assets"]["visual"]["href"], 1).read_bbox(*bbox)
            tiles.append(img[..., :3])
        Image.fromarray(np.hstack([tiles[0], np.full((tiles[0].shape[0], 6, 3), 255, np.uint8), tiles[1]])).save(
            OUT / "thumbs" / f"rank{c['rank']:02d}.png")
        print(c["rank"], c["pair"], c["area_ha_80m"], c["centroid"], flush=True)


if __name__ == "__main__":
    main({int(r) for r in sys.argv[1:]})
