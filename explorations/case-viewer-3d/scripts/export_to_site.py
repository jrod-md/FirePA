"""Copy the built viewer into the publication site as /explorar/.

Run after the build scripts (see README). The destination is replaced as a
whole so removed files do not linger. Only files the viewer loads are copied;
intermediate PNG crops are left out. A manifest with SHA-256 per file is
written last so the published assets can be traced to this export.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
REPO = ROOT.parents[1]
DEST = REPO / "site" / "public" / "explorar"

# Intermediate crops used only to build the feathered WebP images.
SKIP = {"data/s2/pre.png", "data/s2/post.png"}
REQUIRED = [
    "index.html", "viewer.js", "viewer.css", "cases.js",
    "data/case.json", "data/validation.json", "data/cocle.geojson", "data/s2/s2.json",
    "data/s2/pre_context.webp", "data/s2/post_context.webp", "data/s2/pre_detail.webp", "data/s2/post_detail.webp",
    "data/s2/dnbr.png", "data/s2/outline.png",
    "cases/picachos/case.json", "cases/picachos/s2/s2.json",
    "cases/picachos/s2/pre_detail.webp", "cases/picachos/s2/post_detail.webp",
    "cases/picachos/s2/dnbr.png", "cases/picachos/s2/outline.png",
]


def main() -> None:
    missing = [p for p in REQUIRED if not (WEB / p).is_file()]
    if missing or not (WEB / "tiles" / "dem").is_dir() or not (WEB / "tiles" / "relief").is_dir():
        raise SystemExit(f"Build the viewer first; missing: {missing or 'tiles/'}")
    if DEST.exists():
        shutil.rmtree(DEST)
    files = []
    for src in sorted(WEB.rglob("*")):
        rel = src.relative_to(WEB).as_posix()
        if not src.is_file() or rel in SKIP or "__pycache__" in rel:
            continue
        out = DEST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
        files.append({"path": rel, "bytes": src.stat().st_size, "sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
    manifest = {
        "generator": "explorations/case-viewer-3d/scripts/export_to_site.py",
        "status": "exploratory; outside FirePA Scientific Pilot v1",
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files, {manifest['total_bytes'] / 1e6:.1f} MB -> {DEST.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    main()
