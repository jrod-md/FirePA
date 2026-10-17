"""Minimal Cloud-Optimized GeoTIFF window reader over HTTP Range requests.

Only fetches the internal tiles that intersect the requested pixel window.
Supports what Sentinel-2 COGs on AWS use: tiled, DEFLATE or none, predictor 1/2,
uint8/uint16, chunky planar config.
"""

from __future__ import annotations

import struct
import urllib.request
import zlib
from dataclasses import dataclass

import numpy as np

TYPES = {1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4), 12: ("d", 8), 16: ("Q", 8)}
bytes_fetched = 0


def fetch(url: str, start: int, length: int) -> bytes:
    global bytes_fetched
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{start + length - 1}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    bytes_fetched += len(data)
    return data


@dataclass
class COG:
    url: str
    width: int
    height: int
    tile_w: int
    tile_h: int
    offsets: list[int]
    counts: list[int]
    compression: int
    predictor: int
    dtype: np.dtype
    samples: int
    origin: tuple[float, float]  # upper-left corner (x, y)
    res: tuple[float, float]

    @classmethod
    def open(cls, url: str, level: int = 0) -> "COG":
        """level 0 is full resolution; 1, 2, ... are the internal overviews."""
        head = fetch(url, 0, 65536)
        bo = "<" if head[:2] == b"II" else ">"
        bigtiff = struct.unpack(bo + "H", head[2:4])[0] == 43
        if bigtiff:
            ifd = struct.unpack(bo + "Q", head[8:16])[0]
            entry, cfmt, nfmt = 20, "Q", "Q"
        else:
            ifd = struct.unpack(bo + "I", head[4:8])[0]
            entry, cfmt, nfmt = 12, "I", "H"
        nsize = struct.calcsize(nfmt)
        full_scale = None
        for lvl in range(level + 1):
            n = struct.unpack(bo + nfmt, head[ifd : ifd + nsize])[0]
            start = ifd + nsize
            if lvl < level:
                ifd = struct.unpack(bo + cfmt, head[start + n * entry : start + n * entry + struct.calcsize(cfmt)])[0]
                if not ifd:
                    raise ValueError("Overview level not present")
        tags = {}
        for i in range(n):
            e = head[start + i * entry : start + (i + 1) * entry]
            tag, typ = struct.unpack(bo + "HH", e[:4])
            count = struct.unpack(bo + cfmt, e[4 : 4 + struct.calcsize(cfmt)])[0]
            fmt, size = TYPES[typ]
            raw_off = 4 + struct.calcsize(cfmt)
            total = size * count
            inline = 8 if bigtiff else 4
            if total <= inline:
                payload = e[raw_off : raw_off + total]
            else:
                off = struct.unpack(bo + cfmt, e[raw_off : raw_off + struct.calcsize(cfmt)])[0]
                payload = head[off : off + total] if off + total <= len(head) else fetch(url, off, total)
            tags[tag] = struct.unpack(bo + fmt * count, payload) if fmt != "c" else payload
        bits = tags[258][0]
        fmt = tags.get(339, (1,))[0]
        dtype = np.dtype({(8, 1): "u1", (16, 1): "u2", (16, 2): "i2", (32, 3): "f4"}[(bits, fmt)]).newbyteorder(bo)
        if tags.get(259, (1,))[0] not in (1, 8, 32946):
            raise ValueError(f"Unsupported compression {tags[259]}")
        if level:
            base = cls.open(url, 0)
            f = base.width / tags[256][0]
            scale, tie = (base.res[0] * f, base.res[1] * f), (0, 0, 0, base.origin[0], base.origin[1])
        else:
            scale, tie = tags[33550], tags[33922]
        return cls(url, tags[256][0], tags[257][0], tags[322][0], tags[323][0], list(tags[324]),
                   list(tags[325]), tags.get(259, (1,))[0], tags.get(317, (1,))[0], dtype,
                   tags.get(277, (1,))[0], (tie[3], tie[4]), (scale[0], scale[1]))

    def read(self, col0: int, row0: int, cols: int, rows: int) -> np.ndarray:
        out = np.zeros((rows, cols, self.samples), dtype=self.dtype.newbyteorder("="))
        tiles_x = (self.width + self.tile_w - 1) // self.tile_w
        for ty in range(row0 // self.tile_h, (row0 + rows - 1) // self.tile_h + 1):
            for tx in range(col0 // self.tile_w, (col0 + cols - 1) // self.tile_w + 1):
                i = ty * tiles_x + tx
                if not self.counts[i]:
                    continue
                buf = fetch(self.url, self.offsets[i], self.counts[i])
                if self.compression != 1:
                    buf = zlib.decompress(buf)
                t = np.frombuffer(buf, dtype=self.dtype).reshape(self.tile_h, self.tile_w, self.samples)
                if self.predictor == 2:
                    t = np.cumsum(t, axis=1, dtype=self.dtype)
                t = t.astype(self.dtype.newbyteorder("="))
                y0, x0 = ty * self.tile_h, tx * self.tile_w
                ys, ye = max(row0, y0), min(row0 + rows, y0 + self.tile_h)
                xs, xe = max(col0, x0), min(col0 + cols, x0 + self.tile_w)
                out[ys - row0 : ye - row0, xs - col0 : xe - col0] = t[ys - y0 : ye - y0, xs - x0 : xe - x0]
        return out[..., 0] if self.samples == 1 else out

    def read_bbox(self, xmin: float, ymin: float, xmax: float, ymax: float) -> np.ndarray:
        """Read a projected-coordinate bbox that is aligned to this raster's grid."""
        c0 = round((xmin - self.origin[0]) / self.res[0])
        r0 = round((self.origin[1] - ymax) / self.res[1])
        c1 = round((xmax - self.origin[0]) / self.res[0])
        r1 = round((self.origin[1] - ymin) / self.res[1])
        return self.read(c0, r0, c1 - c0, r1 - r0)
