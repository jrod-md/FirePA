from __future__ import annotations

import shutil
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "docs" / "FirePA_Scientific_Pilot_v1.pdf"
OUT = ROOT / "tmp" / "pdfs" / "firepa_report_qa"
DPI = 190


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    pages_dir = OUT / "pages"
    sheets_dir = OUT / "contact-sheets"
    pages_dir.mkdir(parents=True)
    sheets_dir.mkdir(parents=True)

    document = pdfium.PdfDocument(str(PDF))
    rendered = []
    scale = DPI / 72
    for index in range(len(document)):
        page = document[index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("RGB")
        path = pages_dir / f"page-{index + 1:02d}.png"
        image.save(path, format="PNG", optimize=True)
        rendered.append(path)

    thumb_width = 520
    for sheet_index in range(0, len(rendered), 4):
        batch = rendered[sheet_index : sheet_index + 4]
        thumbs = []
        for page_number, path in enumerate(batch, start=sheet_index + 1):
            image = Image.open(path).convert("RGB")
            ratio = thumb_width / image.width
            thumb = image.resize(
                (thumb_width, round(image.height * ratio)), Image.Resampling.LANCZOS
            )
            labelled = Image.new("RGB", (thumb.width, thumb.height + 38), "#ded7ca")
            labelled.paste(thumb, (0, 38))
            draw = ImageDraw.Draw(labelled)
            draw.text((14, 12), f"PAGE {page_number:02d}", fill="#282622")
            thumbs.append(labelled)

        sheet_width = max(image.width for image in thumbs) * 2 + 24
        row_heights = []
        for row in range(0, len(thumbs), 2):
            row_heights.append(max(item.height for item in thumbs[row : row + 2]))
        sheet_height = sum(row_heights) + 24 * (len(row_heights) + 1)
        sheet = Image.new("RGB", (sheet_width, sheet_height), "#bcb4a7")
        y = 24
        for row_index, row in enumerate(range(0, len(thumbs), 2)):
            x = 0
            for item in thumbs[row : row + 2]:
                sheet.paste(item, (x, y))
                x += item.width + 24
            y += row_heights[row_index] + 24
        sheet.save(
            sheets_dir / f"pages-{sheet_index + 1:02d}-{sheet_index + len(batch):02d}.png",
            format="PNG",
            optimize=True,
        )

    print(f"Rendered {len(rendered)} pages at {DPI} DPI")
    print(OUT)


if __name__ == "__main__":
    main()
