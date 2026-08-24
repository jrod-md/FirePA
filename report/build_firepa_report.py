from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    LongTable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "FirePA_Scientific_Pilot_v1.pdf"
DATA = ROOT / "site-data"
FIGURES = DATA / "figures"

PAPER = colors.HexColor("#F4EFE5")
PAPER_ALT = colors.HexColor("#EEE6D8")
INK = colors.HexColor("#20201E")
INK_SOFT = colors.HexColor("#5B5750")
CLAY = colors.HexColor("#A34E31")
CLAY_DARK = colors.HexColor("#783722")
RULE = colors.HexColor("#CFC5B5")
PALE_CLAY = colors.HexColor("#E8D3C5")

PORTRAIT = A4
LANDSCAPE = landscape(A4)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def citation_author() -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^\s*-\s+name:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("CITATION.cff does not contain an author name")
    return match.group(1).strip().strip('"\'')


def register_fonts() -> None:
    fonts = Path("C:/Windows/Fonts")
    required = {
        "Georgia": "georgia.ttf",
        "Georgia-Bold": "georgiab.ttf",
        "Georgia-Italic": "georgiai.ttf",
        "Arial": "arial.ttf",
        "Arial-Bold": "arialbd.ttf",
        "Consolas": "consola.ttf",
        "Consolas-Bold": "consolab.ttf",
    }
    for name, filename in required.items():
        path = fonts / filename
        if not path.exists():
            raise FileNotFoundError(f"Required system font not found: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "Georgia", normal="Georgia", bold="Georgia-Bold", italic="Georgia-Italic"
    )
    pdfmetrics.registerFontFamily(
        "Arial", normal="Arial", bold="Arial-Bold"
    )
    pdfmetrics.registerFontFamily(
        "Consolas", normal="Consolas", bold="Consolas-Bold"
    )


def p(text: str, style, **kwargs) -> Paragraph:
    return Paragraph(text, style, **kwargs)


def link(url: str, label: str | None = None) -> str:
    shown = escape(label or url)
    return f'<link href="{escape(url)}" color="#783722">{shown}</link>'


def long_reference_link(url: str) -> str:
    """Keep the full URI target while giving the longest reference a clean wrap."""
    split_marker = "reserva-hidrica-cerro-guacamaya"
    if split_marker not in url:
        return link(url, url)
    split_at = url.index(split_marker)
    first = url[:split_at]
    second = url[split_at:]
    return f"{link(url, first)}<br/>{link(url, second)}"


class Rule(Flowable):
    def __init__(self, width=1, color=RULE, space_before=2, space_after=8):
        super().__init__()
        self.line_width = width
        self.color = color
        self.spaceBefore = space_before
        self.spaceAfter = space_after

    def wrap(self, avail_width, avail_height):
        self.width = avail_width
        self.height = 1
        return self.width, self.height

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.line_width)
        self.canv.line(0, 0, self.width, 0)


class ReductionGraphic(Flowable):
    def __init__(self, stage_values, width=470, height=112):
        super().__init__()
        self.stage_values = stage_values
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        col_w = self.width / 3
        y = 62
        for index, (value, label) in enumerate(self.stage_values):
            x = index * col_w
            c.setFillColor(CLAYS[index] if index < len(CLAYS) else CLAY)
            c.setFont("Georgia", 28)
            c.drawString(x, y, value)
            c.setFillColor(INK_SOFT)
            c.setFont("Arial", 7.2)
            c.drawString(x, y - 18, label.upper())
            if index < 2:
                start = x + col_w * 0.67
                end = (index + 1) * col_w - 14
                c.setStrokeColor(CLAYS[index])
                c.setLineWidth(0.8)
                c.line(start, y + 9, end, y + 9)
                c.line(end - 5, y + 12, end, y + 9)
                c.line(end - 5, y + 6, end, y + 9)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(0, 24, self.width, 24)
        c.setFillColor(INK_SOFT)
        c.setFont("Consolas", 7.2)
        c.drawString(0, 8, "FROZEN REDUCTION / RECORDS -> DETECTIONS -> ANALYTICAL GROUPS")


CLAYS = [colors.HexColor("#7E3A25"), colors.HexColor("#995039"), CLAY]


class StudyFrameGraphic(Flowable):
    def __init__(self, width=470, height=360):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        w = self.width
        c.setStrokeColor(RULE)
        c.setLineWidth(0.7)
        c.line(0, self.height - 2, w, self.height - 2)
        top = self.height - 72
        values = [
            ("1,532", "AUDITED FIRMS RAW DETECTIONS"),
            ("1,185", "PROCESSED DETECTIONS IN COCLÉ"),
            ("611", "PROVISIONAL THERMAL EVENTS"),
        ]
        col = w / 3
        for i, (value, label) in enumerate(values):
            x = i * col
            c.setFillColor(INK)
            c.setFont("Georgia", 27)
            c.drawString(x, top, value)
            c.setFillColor(CLAYS[i])
            c.rect(x, top - 16, col * (0.86 - i * 0.08), 2, fill=1, stroke=0)
            c.setFillColor(INK_SOFT)
            c.setFont("Arial", 6.7)
            c.drawString(x, top - 33, label)

        rows = [
            ("r1500_t06", "1,500 m / 6 h", "FROZEN CONFIGURATION"),
            ("30 / 28 / 2", "selected / observable / unobserved", "OPTICAL COHORT"),
            ("7 / 2", "documents / incidents", "EXTERNAL REGISTRY"),
        ]
        y = top - 100
        for code, detail, label in rows:
            c.setStrokeColor(RULE)
            c.line(0, y + 27, w, y + 27)
            c.setFillColor(CLAYS[1])
            c.setFont("Consolas-Bold", 11)
            c.drawString(0, y + 7, code)
            c.setFillColor(INK)
            c.setFont("Arial", 8.2)
            c.drawString(w * 0.31, y + 7, detail)
            c.setFillColor(INK_SOFT)
            c.setFont("Arial", 6.6)
            c.drawRightString(w, y + 7, label)
            y -= 48

        c.setFillColor(PALE_CLAY)
        c.rect(0, 8, w, 56, fill=1, stroke=0)
        c.setFillColor(CLAYS[0])
        c.setFont("Consolas-Bold", 8)
        c.drawString(12, 43, "EVIDENCE BOUNDARY")
        c.setFillColor(INK)
        c.setFont("Arial", 8.3)
        c.drawString(12, 27, "No ground truth / no predictive model / not operational")


class DistanceGraphic(Flowable):
    def __init__(self, width=470, height=120):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        start = 18
        end = self.width - 18
        scale = (end - start) / 12000
        y = 55
        threshold = start + 5000 * scale
        signal = start + 10400.826 * scale
        c.setStrokeColor(RULE)
        c.setLineWidth(2)
        c.line(start, y, end, y)
        c.setStrokeColor(CLAYS[0])
        c.setLineWidth(2)
        c.line(start, y, threshold, y)
        c.setFillColor(CLAYS[0])
        c.circle(threshold, y, 4, fill=1, stroke=0)
        c.setFillColor(INK)
        c.circle(signal, y, 5, fill=1, stroke=0)
        c.setFont("Consolas-Bold", 8)
        c.setFillColor(CLAYS[0])
        c.drawCentredString(threshold, y + 18, "5,000 m")
        c.setFillColor(INK)
        c.drawCentredString(signal, y + 18, "10,400.826 m")
        c.setFont("Arial", 6.8)
        c.setFillColor(INK_SOFT)
        c.drawCentredString(threshold, y - 20, "OFFICIAL INCLUSIVE THRESHOLD")
        c.drawCentredString(signal, y - 20, "NEAREST DOCUMENTED CONTEMPORARY SIGNAL")
        c.setFont("Consolas-Bold", 8.5)
        c.setFillColor(CLAYS[0])
        c.drawString(18, 8, "SPATIAL_THRESHOLD_MISS")


class ArchitectureGraphic(Flowable):
    def __init__(self, width=470, height=195):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        pipeline = [
            ("SCIENTIFIC PYTHON", "local analytical pipeline"),
            ("SITE-DATA", "frozen public package"),
            ("ASTRO", "bilingual static publication"),
            ("GITHUB", "public source repository"),
        ]
        gap = 14
        box_w = (self.width - gap * 3) / 4
        y = 118
        for i, (head, sub) in enumerate(pipeline):
            x = i * (box_w + gap)
            c.setFillColor(PAPER_ALT if i % 2 == 0 else colors.HexColor("#F8F4EC"))
            c.setStrokeColor(RULE)
            c.rect(x, y, box_w, 48, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont("Consolas-Bold", 6.7)
            c.drawCentredString(x + box_w / 2, y + 30, head)
            c.setFillColor(INK_SOFT)
            c.setFont("Arial", 5.8)
            c.drawCentredString(x + box_w / 2, y + 15, sub)
            if i < len(pipeline) - 1:
                x1 = x + box_w
                x2 = x + box_w + gap
                c.setStrokeColor(CLAYS[1])
                c.line(x1 + 2, y + 24, x2 - 2, y + 24)
                c.line(x2 - 5, y + 27, x2 - 2, y + 24)
                c.line(x2 - 5, y + 21, x2 - 2, y + 24)

        branch_gap = 14
        branch_w = 126
        branch_total = branch_w * 2 + branch_gap
        branch_x = self.width - branch_total
        branch_y = 48
        branches = [
            ("GITHUB ACTIONS", "public validation"),
            ("CLOUDFLARE", "Pages distribution"),
        ]
        source_x = 3 * (box_w + gap) + box_w / 2
        junction_y = 104
        c.setStrokeColor(CLAYS[1])
        c.line(source_x, y, source_x, junction_y)
        for i, (head, sub) in enumerate(branches):
            x = branch_x + i * (branch_w + branch_gap)
            center_x = x + branch_w / 2
            c.line(source_x, junction_y, center_x, junction_y)
            c.line(center_x, junction_y, center_x, branch_y + 48)
            c.line(center_x - 3, branch_y + 51, center_x, branch_y + 48)
            c.line(center_x + 3, branch_y + 51, center_x, branch_y + 48)
            c.setFillColor(PAPER_ALT if i == 0 else colors.HexColor("#F8F4EC"))
            c.setStrokeColor(RULE)
            c.rect(x, branch_y, branch_w, 42, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont("Consolas-Bold", 6.7)
            c.drawCentredString(center_x, branch_y + 26, head)
            c.setFillColor(INK_SOFT)
            c.setFont("Arial", 5.8)
            c.drawCentredString(center_x, branch_y + 12, sub)
        c.setFillColor(INK_SOFT)
        c.setFont("Arial", 7.5)
        c.drawString(0, 23, "GitHub Actions verifies the clean-clone public contract.")
        c.drawString(0, 10, "Cloudflare Pages distributes the publication; neither service is scientific evidence.")


class FigurePlate(Flowable):
    def __init__(self, path: Path, caption: str, source: str, width=732):
        super().__init__()
        self.path = path
        self.caption = caption
        self.source = source
        self.width = width
        with PILImage.open(path) as im:
            self.image_width, self.image_height = im.size
        self.image_draw_height = self.width * self.image_height / self.image_width
        self.height = self.image_draw_height + 70

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        self.image_draw_height = self.width * self.image_height / self.image_width
        self.height = self.image_draw_height + 70
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.drawImage(
            str(self.path),
            0,
            70,
            self.width,
            self.image_draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(0, 58, self.width, 58)
        caption_style = ParagraphStyle(
            "plate_caption",
            fontName="Arial",
            fontSize=7.7,
            leading=10.2,
            textColor=INK_SOFT,
        )
        cap = Paragraph(
            f"<b>{escape(self.caption)}</b> {escape(self.source)}",
            caption_style,
        )
        cap.wrapOn(c, self.width, 48)
        cap.drawOn(c, 0, 18)


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "BodyFirePA",
            parent=styles["BodyText"],
            fontName="Georgia",
            fontSize=9.25,
            leading=14.1,
            textColor=INK,
            spaceAfter=7,
            allowWidows=0,
            allowOrphans=0,
        )
    )
    styles.add(
        ParagraphStyle(
            "SmallBody",
            parent=styles["BodyFirePA"],
            fontSize=8.2,
            leading=12.1,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "Kicker",
            fontName="Consolas-Bold",
            fontSize=7.2,
            leading=9,
            textColor=CLAY,
            tracking=1.6,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionNumber",
            fontName="Consolas",
            fontSize=8,
            leading=10,
            textColor=CLAY,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionTitle",
            fontName="Georgia",
            fontSize=24,
            leading=27,
            textColor=INK,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subhead",
            fontName="Arial-Bold",
            fontSize=9.2,
            leading=11,
            textColor=INK,
            spaceBefore=7,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "Quote",
            fontName="Georgia-Italic",
            fontSize=15,
            leading=20,
            textColor=CLAY_DARK,
            leftIndent=16,
            rightIndent=18,
            borderColor=CLAY,
            borderWidth=0,
            borderPadding=(0, 0, 0, 12),
            spaceBefore=9,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "Caption",
            fontName="Arial",
            fontSize=7.2,
            leading=9.4,
            textColor=INK_SOFT,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "Mono",
            fontName="Consolas",
            fontSize=7.6,
            leading=11,
            textColor=INK,
            backColor=colors.HexColor("#EAE3D7"),
            borderPadding=(6, 7, 6, 7),
            spaceBefore=5,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "BulletFirePA",
            parent=styles["BodyFirePA"],
            leftIndent=13,
            firstLineIndent=-8,
            bulletIndent=0,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "Reference",
            fontName="Arial",
            fontSize=7.2,
            leading=9.2,
            textColor=INK,
            leftIndent=14,
            firstLineIndent=-14,
            spaceAfter=5,
        )
    )
    return styles


def draw_background(canvas, page_size, page_number=True):
    width, height = page_size
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    if page_number:
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.55)
        canvas.line(20 * mm, height - 16 * mm, width - 20 * mm, height - 16 * mm)
        canvas.setFillColor(INK_SOFT)
        canvas.setFont("Consolas", 6.7)
        canvas.drawString(20 * mm, height - 12.8 * mm, "FIREPA / SCIENTIFIC PILOT V1")
        canvas.drawRightString(width - 20 * mm, 11 * mm, f"{canvas.getPageNumber():02d}")
        canvas.setStrokeColor(RULE)
        canvas.line(20 * mm, 15 * mm, width - 20 * mm, 15 * mm)
    canvas.restoreState()


def on_cover(canvas, doc):
    width, height = PORTRAIT
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(PALE_CLAY)
    canvas.rect(width - 16 * mm, 0, 16 * mm, height, fill=1, stroke=0)
    canvas.setFillColor(CLAYS[0])
    canvas.rect(width - 17.5 * mm, 0, 1.5 * mm, height, fill=1, stroke=0)
    canvas.restoreState()


def on_portrait(canvas, doc):
    draw_background(canvas, PORTRAIT, page_number=True)


def on_landscape(canvas, doc):
    draw_background(canvas, LANDSCAPE, page_number=True)


def section_header(styles, number: str, title: str, kicker: str):
    return [
        p(f"SECTION {number}", styles["SectionNumber"]),
        p(escape(title), styles["SectionTitle"]),
        Rule(width=0.8, color=CLAY, space_after=8),
        p(escape(kicker.upper()), styles["Kicker"]),
    ]


def bullet(text: str, styles):
    return p(f"<bullet>&bull;</bullet>{text}", styles["BulletFirePA"])


def academic_table(data, col_widths, styles, header=True, font_size=7.6):
    formatted = []
    for row_index, row in enumerate(data):
        row_style = ParagraphStyle(
            f"table_{row_index}_{font_size}",
            fontName="Arial-Bold" if header and row_index == 0 else "Arial",
            fontSize=font_size,
            leading=font_size + 2.2,
            textColor=INK,
        )
        formatted.append([Paragraph(str(cell), row_style) for cell in row])
    table = LongTable(formatted, colWidths=col_widths, repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, CLAY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, RULE),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), PAPER_ALT))
    table.setStyle(TableStyle(commands))
    return table


def start_portrait(story):
    story.extend([NextPageTemplate("portrait"), PageBreak()])


def add_figure_page(story, styles, figure_number, filename, title, caption):
    story.extend([NextPageTemplate("landscape"), PageBreak()])
    story.append(FigurePlate(
        FIGURES / filename,
        f"Figure {figure_number}. {title}.",
        caption,
    ))


def build_report() -> None:
    register_fonts()
    styles = build_styles()
    summary = read_json(DATA / "project-summary.json")
    manifest = read_json(DATA / "manifest.json")
    provenance = read_json(DATA / "provenance.json")
    timeline = read_json(DATA / "guacamaya-timeline.json")
    citations = read_json(DATA / "citations.json")
    author = citation_author()

    provenance_figure_hashes = {
        entry["derivative_path"].split("/")[-1]: entry["derivative_sha256"]
        for entry in provenance["figure_provenance"]
    }
    expected_figure_hashes = {
        entry["path"].split("/")[-1]: entry["sha256"]
        for entry in manifest["files"]
        if entry["path"].startswith("figures/")
    }
    if expected_figure_hashes != provenance_figure_hashes:
        raise RuntimeError("Manifest and provenance figure ledgers disagree")
    for filename, expected in expected_figure_hashes.items():
        actual = sha256(FIGURES / filename)
        if actual != expected:
            raise RuntimeError(f"Frozen figure hash mismatch before build: {filename}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUT),
        pagesize=PORTRAIT,
        leftMargin=21 * mm,
        rightMargin=21 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title="FirePA: A Reproducible Remote-Sensing Pilot for Provisional Thermal Events in Coclé, Panama",
        author=author,
        subject="FirePA Scientific Pilot v1 academic report",
        creator="FirePA reproducible ReportLab pipeline",
    )
    portrait_frame = Frame(
        21 * mm, 20 * mm, PORTRAIT[0] - 42 * mm, PORTRAIT[1] - 43 * mm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="portrait_frame"
    )
    landscape_frame = Frame(
        16 * mm, 18 * mm, LANDSCAPE[0] - 32 * mm, LANDSCAPE[1] - 38 * mm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="landscape_frame"
    )
    cover_frame = Frame(
        22 * mm, 20 * mm, PORTRAIT[0] - 48 * mm, PORTRAIT[1] - 40 * mm,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="cover_frame"
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", pagesize=PORTRAIT, frames=[cover_frame], onPage=on_cover),
        PageTemplate(id="portrait", pagesize=PORTRAIT, frames=[portrait_frame], onPage=on_portrait),
        PageTemplate(id="landscape", pagesize=LANDSCAPE, frames=[landscape_frame], onPage=on_landscape),
    ])

    body = styles["BodyFirePA"]
    small = styles["SmallBody"]
    story = []

    # Cover
    story.extend([
        Spacer(1, 18 * mm),
        p("A REPRODUCIBLE REMOTE-SENSING PILOT", styles["Kicker"]),
        Spacer(1, 7 * mm),
        p("FirePA", ParagraphStyle(
            "CoverTitle", fontName="Georgia", fontSize=54, leading=56,
            textColor=INK, spaceAfter=12
        )),
        p("A Reproducible Remote-Sensing Pilot for Provisional Thermal Events in Coclé, Panama",
          ParagraphStyle("CoverSubtitle", fontName="Georgia", fontSize=21,
                         leading=27, textColor=INK, spaceAfter=18)),
        Rule(width=1.1, color=CLAY, space_after=13),
        p("FIREPA SCIENTIFIC PILOT V1", styles["Kicker"]),
        Spacer(1, 25 * mm),
        p(escape(author), ParagraphStyle("CoverAuthor", fontName="Georgia", fontSize=13,
                                         leading=17, textColor=INK, spaceAfter=14)),
        p("Study window<br/>1 January - 30 April 2025",
          ParagraphStyle("CoverMeta", fontName="Arial", fontSize=8.5, leading=13,
                         textColor=INK_SOFT, spaceAfter=12)),
        p("Scientific freeze<br/><font name='Consolas'>7694da7df5808911de48de84016759c5fd22f176</font>",
          ParagraphStyle("CoverFreeze", fontName="Arial", fontSize=8.5, leading=13,
                         textColor=INK_SOFT, spaceAfter=12)),
        p(f"Public website<br/>{link('https://firepa.pages.dev/')}",
          ParagraphStyle("CoverURL1", fontName="Arial", fontSize=8.3, leading=12,
                         textColor=INK_SOFT, spaceAfter=8)),
        p(f"Source repository<br/>{link('https://github.com/jrod-md/FirePA')}",
          ParagraphStyle("CoverURL2", fontName="Arial", fontSize=8.3, leading=12,
                         textColor=INK_SOFT, spaceAfter=18)),
        p("PUBLICATION / AUGUST 2026", styles["Kicker"]),
    ])

    # Abstract
    start_portrait(story)
    story.extend(section_header(styles, "00", "Abstract", "Scope, method, and evidence boundary"))
    story.extend([
        p("FirePA evaluates how satellite thermal detections can be reduced into reproducible provisional analytical units and compared with descriptive optical and external evidence without converting those signals into confirmed wildfire claims. The pilot audits 1,532 NASA FIRMS raw detections, retains 1,185 valid detections inside Coclé, and groups them with the frozen <font name='Consolas'>r1500_t06</font> spatiotemporal connected-components configuration. The result is 611 provisional thermal events: 344 singletons, 267 multi-detection events, and 17 cases flagged <font name='Consolas'>possible_chain_merge</font>.", body),
        p("A frozen Sentinel-2 cohort contains 30 events. Twenty-eight are observable under the optical policy and two remain <font name='Consolas'>unobserved</font>; those two are not negative cases. NBR and dNBR are retained as descriptive evidence only. Formal human observations equal zero, no ground truth exists, and no supervised model or severity classification was produced.", body),
        p("Two external-reference comparisons preserve an inclusive 5,000 m rule. Cerro Guacamaya has six matched provisional clusters separated by five gaps greater than six hours over 72.733 hours, supporting <font name='Consolas'>fragmentation_possible = true</font> while preserving all six clusters separately. Cerro Los Picachos has zero official matches; the nearest documented contemporary signal is 10,400.826 m away, so the result is <font name='Consolas'>SPATIAL_THRESHOLD_MISS</font>, not absence of fire, activity, or thermal signal.", body),
        p("The pilot is static, descriptive, and reproducible within its public boundary. It is not real-time, operational, predictive, or validated ground truth.", body),
        Spacer(1, 8 * mm),
        p("Keywords", styles["Subhead"]),
        p("remote sensing / thermal anomalies / NASA FIRMS / Sentinel-2 / spatiotemporal grouping / reproducible research / Coclé, Panama", styles["Caption"]),
    ])

    # Resumen
    start_portrait(story)
    story.extend(section_header(styles, "00", "Resumen", "Alcance, método y límite de la evidencia"))
    story.extend([
        p("FirePA evalúa cómo las detecciones térmicas satelitales pueden reducirse a unidades analíticas provisionales y reproducibles, y compararse con evidencia óptica y referencias externas descriptivas sin convertir esas señales en incendios forestales confirmados. El piloto audita 1.532 detecciones crudas de NASA FIRMS, conserva 1.185 detecciones válidas dentro de Coclé y las agrupa mediante la configuración congelada de componentes conexos espaciotemporales <font name='Consolas'>r1500_t06</font>. El resultado son 611 eventos térmicos provisionales: 344 eventos de una sola detección, 267 eventos de múltiples detecciones y 17 casos marcados con la bandera técnica <font name='Consolas'>possible_chain_merge</font>.", body),
        p("Una cohorte congelada de Sentinel-2 contiene 30 eventos. Veintiocho son observables según la política óptica y dos permanecen sin observación óptica bajo esa política (estado técnico: <font name='Consolas'>unobserved</font>); esos dos casos no son negativos. NBR y dNBR se conservan solo como evidencia descriptiva. Las observaciones humanas formales son cero, no existe verdad de terreno y no se produjo ningún modelo supervisado ni clasificación de severidad validada.", body),
        p("Dos comparaciones con referencias externas conservan una regla inclusiva de 5.000 m. Cerro Guacamaya presenta seis conglomerados provisionales emparejados, separados por cinco intervalos mayores de seis horas a lo largo de 72,733 horas. Esto respalda la interpretación registrada como <font name='Consolas'>fragmentation_possible = true</font>, manteniendo separados los seis conglomerados. Cerro Los Picachos presenta cero coincidencias oficiales; la señal contemporánea documentada más cercana está a 10.400,826 m, por lo que el diagnóstico técnico registrado es <font name='Consolas'>SPATIAL_THRESHOLD_MISS</font>; no implica ausencia de incendio, actividad o señal térmica.", body),
        p("El piloto es estático, descriptivo y reproducible dentro de su límite público. No es un sistema en tiempo real, operativo, predictivo ni validado como verdad de terreno.", body),
        Spacer(1, 8 * mm),
        p("Términos clave", styles["Subhead"]),
        p("teledetección / anomalías térmicas / NASA FIRMS / Sentinel-2 / agrupamiento espaciotemporal / investigación reproducible / Coclé, Panamá", styles["Caption"]),
    ])

    # Study frame
    start_portrait(story)
    story.extend(section_header(styles, "00", "Key results and study frame", "The frozen analytical record at a glance"))
    story.append(StudyFrameGraphic())
    story.extend([
        p("The values above are frozen records, processed detections, provisional groups, and descriptive cohorts. They do not form a sequence of confirmed wildfire counts.", body),
        p("Scientific unit: <font name='Consolas'>provisional thermal event</font>. Study area: Coclé, Panama. Study window: 2025-01-01 through 2025-04-30, inclusive, UTC.", styles["Caption"]),
    ])

    # 1 Research question
    start_portrait(story)
    story.extend(section_header(styles, "01", "Research question and objectives", "A question about signals and their limits"))
    story.extend([
        p("Can thermal signals tell us what happened on the ground?", styles["Quote"]),
        p("FirePA treats this as a bounded research question rather than an operational promise. Satellite thermal anomalies provide repeatable observations, but they do not independently establish ignition, cause, perimeter, severity, duration, or incident identity. The pilot therefore studies the evidence boundary as deliberately as it studies the detections.", body),
        p("The work has four objectives:", body),
        bullet("audit and spatially filter a historical NASA FIRMS cohort;", styles),
        bullet("construct reproducible provisional thermal-event units;", styles),
        bullet("describe a frozen optical follow-up cohort without creating labels; and", styles),
        bullet("compare frozen units with limited external incident references while exposing threshold and representation failures.", styles),
        Spacer(1, 8 * mm),
        p("The objective is not to prove event truth, build a classifier, or deliver an alerting system. The contribution is a reproducible way to preserve the distinction between detection, grouping, observation, and interpretation.", body),
    ])

    # 2 Study area
    start_portrait(story)
    story.extend(section_header(styles, "02", "Study area and study window", "Coclé, Panama / 1 January - 30 April 2025"))
    story.extend([
        p("The study area is the province of Coclé, Panama. The acquisition and processing window is 2025-01-01 through 2025-04-30, inclusive, in UTC. This boundary and period constrain every frozen count and finding in this report.", body),
        p("The validated local administrative boundary originated from the Instituto Geográfico Nacional Tommy Guardia / ANATI province layer <font name='Consolas'>limi_prov_a</font>, documented at 1:25,000 scale in <font name='Consolas'>EPSG:32617</font>. The Coclé geometry was selected locally and transformed to <font name='Consolas'>EPSG:4326</font> for filtering and public presentation.", body),
        p("The original boundary source and generated local <font name='Consolas'>data/reference/cocle.geojson</font> are not redistributed because the source metadata declares CC BY-NC-SA. The public website uses a tracked deterministic presentation derivative when the local source boundary is absent. That derivative is contextual geometry, not a scientific result, a burn perimeter, or synthetic geography.", body),
        Spacer(1, 9 * mm),
        p("Scope boundary", styles["Subhead"]),
        bullet("Geographic generalization beyond Coclé is not claimed.", styles),
        bullet("Temporal generalization beyond the frozen four-month window is not claimed.", styles),
        bullet("Public event coordinates are centroids for inspection, not precision ground observations.", styles),
    ])

    # 3 Data sources
    start_portrait(story)
    story.extend(section_header(styles, "03", "Data sources and provenance", "Scientific inputs separated from relational references"))
    source_rows = [
        ["Source", "Role in FirePA", "Boundary"],
        ["NASA FIRMS / LANCE", "VIIRS thermal-anomaly detections for the frozen cohort", "Detection is not confirmed wildfire"],
        ["Sentinel-2 SR Harmonized", "Descriptive optical follow-up for 30 frozen events", "No severity class or truth label"],
        ["Cloud Score+", "Optical clarity assessment for linked scenes", "Clarity is not evidence of fire"],
        ["IGN Tommy Guardia / ANATI", "Validated Coclé administrative boundary", "Original source not redistributed"],
        ["7 external documents", "Relational context for two documented incidents", "Not pipeline inputs or ground truth"],
    ]
    story.extend([
        p("FirePA maintains a provenance boundary between scientific inputs, derived public artifacts, and external incident references. A source URL documents provenance; it does not transfer licensing rights and does not become a truth label.", body),
        academic_table(source_rows, [105, 205, 145], styles, font_size=7.3),
        Spacer(1, 6 * mm),
        p("External references", styles["Subhead"]),
        p("The external registry contains seven manually located documents describing Cerro Los Picachos and Cerro Guacamaya. Publisher claims about dates, affected area, and cause are preserved per source rather than adjudicated into a single value. Matching coordinates are approximate researcher-provided anchors; FirePA does not claim that the source articles supplied those coordinates.", body),
        p("The manual search was not exhaustive. No qualifying articles were located in March or April 2025, but absence of a located article is not absence of fire, activity, or thermal signal.", body),
    ])

    # 4 FIRMS
    start_portrait(story)
    story.extend(section_header(styles, "04", "FIRMS acquisition and audit", "From 1,532 raw records to 1,185 detections in Coclé"))
    story.append(ReductionGraphic([
        ("1,532", "audited raw detections"),
        ("1,185", "processed detections"),
        ("611", "provisional events"),
    ]))
    firms_rows = [
        ["Audit stage", "Count"],
        ["Audited raw detections", "1,532"],
        ["Valid schema/date/coordinate records", "1,532"],
        ["Detections inside the requested period", "1,532"],
        ["Processed detections inside Coclé", "1,185"],
    ]
    story.extend([
        academic_table(firms_rows, [365, 90], styles, font_size=8),
        Spacer(1, 5 * mm),
        p("The local workflow used NASA FIRMS VIIRS historical detections. It checked source availability, split requests into bounded temporal fragments, retained raw bytes and manifests locally, validated required fields, and filtered records by time and the validated Coclé geometry.", body),
        p("The difference between 1,532 and 1,185 is the spatial study-area filter. FIRMS rows are satellite-observed thermal anomalies. Multiple rows may describe the same analytical event, and a single row is not automatically a confirmed fire.", body),
    ])
    add_figure_page(
        story, styles, 1, "01_pipeline_overview.png", "Frozen scientific pipeline",
        "The byte-frozen pipeline plate records the local descriptive sequence and the official external-reference rule. It is reproduced proportionally from site-data/figures/01_pipeline_overview.png without pixel-level modification."
    )

    # 5 Grouping
    start_portrait(story)
    story.extend(section_header(styles, "05", "Spatiotemporal grouping", "Connected components under r1500_t06"))
    group_rows = [
        ["Frozen result", "Count"],
        ["Provisional thermal events", "611"],
        ["Singleton events", "344"],
        ["Multi-detection events", "267"],
        ["possible_chain_merge", "17"],
    ]
    story.extend([
        p("The frozen configuration <font name='Consolas'>r1500_t06</font> applies connected components with a spatial link distance of 1,500 m or less, a temporal link difference of six hours or less, and metric distance calculations in <font name='Consolas'>EPSG:32617</font>. Links use coordinates and UTC timestamps only.", body),
        academic_table(group_rows, [365, 90], styles, font_size=8),
        Spacer(1, 5 * mm),
        p("FRP, confidence, source, satellite, instrument, and day/night status remain descriptive attributes and do not create graph edges. A provisional event is therefore a connected analytical group, not a claim of one ignition, one continuous incident, a burn-scar perimeter, or a confirmed wildfire.", body),
        p("Connected components can join observations through chains or split prolonged activity when temporal gaps exceed six hours. The <font name='Consolas'>possible_chain_merge</font> field is a review flag, not a corrected class or an automatic merge instruction.", body),
        p("The term provisional is essential: the pilot has no ground-truth adjudication.", styles["Quote"]),
    ])
    add_figure_page(
        story, styles, 2, "02_cluster_distribution.png", "Descriptive cluster distribution",
        "Frozen descriptive histograms for the 611 r1500_t06 clusters. The figure does not establish confirmed-fire classes or infer severity. Source artifact: site-data/figures/02_cluster_distribution.png."
    )

    # 6 and 7 Optical
    start_portrait(story)
    story.extend(section_header(styles, "06", "Sentinel-2 follow-up", "A frozen 30-event optical cohort"))
    story.extend([
        p("The structural optical cohort contains 30 frozen events. Sentinel-2 Surface Reflectance Harmonized and Cloud Score+ were used under the documented observability policy. Twenty-eight events are observable and two remain <font name='Consolas'>unobserved</font>.", body),
        p("Unobserved means that the policy did not obtain usable optical support. It does not mean no fire, no event, or no land-surface change. The two cases are not negative examples.", body),
        p("Evidence modes remain separate", styles["Subhead"]),
        bullet("<font name='Consolas'>selected_pair</font>: one selected pre/post pair under the frozen policy;", styles),
        bullet("<font name='Consolas'>window_median</font>: a separate seven-case technical pilot using local numeric bundles and per-band temporal medians.", styles),
        p("The window-median pilot passed technical integrity checks but was never connected to formal review assignments and does not replace selected-pair evidence.", body),
        Spacer(1, 5 * mm),
        p("SECTION 07", styles["SectionNumber"]),
        p("NBR / dNBR evidence boundary", ParagraphStyle(
            "SubSectionTitle", fontName="Georgia", fontSize=17, leading=20,
            textColor=INK, spaceAfter=7
        )),
        p("NBR  = (B8 - B12) / (B8 + B12)<br/>dNBR = NBR_pre - NBR_post", styles["Mono"]),
        p("B8 and B12 are evaluated on common 20 m support. These indices are descriptive and may respond to cloud, haze, phenology, moisture, agriculture, exposed soil, water, and other land-surface changes. FirePA produced no <font name='Consolas'>significant_burn</font> target, validated burn-scar label, severity class, or causal attribution.", body),
    ])

    # 8 Review and model
    start_portrait(story)
    story.extend(section_header(styles, "08", "Review and model-assisted calibration", "Exploratory instrument testing, not validation"))
    story.extend([
        p("execution_authorized = false<br/>formal_human_observations = 0", styles["Mono"]),
        p("Formal review infrastructure was prepared, but execution was deferred because a qualified reviewer was unavailable. No supervised predictive model was trained because the pilot has no defensible target or ground truth.", body),
        p("A blind seven-case model-assisted calibration tested whether a proposed two-pass review contract preserved ambiguity, confidence, temporal robustness, observation limitations, and competing land-surface explanations. Pass A examined selected multispectral pre/post evidence. Pass B examined a separate temporal-robustness view while preserving the Pass A fields. Responses were recorded as <font name='Consolas'>provisional_pseudolabel</font>.", body),
        p("A later control used the same seven anonymized cases with two independently returned model-assisted reviews. The comparison contained 14 provisional rows. There was no case with exact agreement across every structured field. Agreement between models from the same family is not independence from a reference standard and is not an accuracy measure.", body),
        p("The calibration affected none of the 1,532 raw records, 1,185 processed detections, 611 provisional events, 30-event optical cohort, external-reference results, frozen figures, or public-package artifacts. It produced no human observation, ground truth, training target, confirmed-fire label, severity class, model-performance estimate, or predictive model.", body),
        p("Public reproducibility is limited to the aggregate methodological record. The case-to-event mapping, response JSON, review database, source panels, local review packages, and protected optical inputs are not redistributed.", body),
    ])

    # 9 external methodology
    start_portrait(story)
    story.extend(section_header(styles, "09", "External-reference methodology", "Relational evidence under a fixed inclusive rule"))
    story.extend([
        p("The frozen registry contains seven documents describing two incidents. Each source preserves its own publication date, event date, location, area, and cause claim where available. FirePA does not adjudicate a single true area or cause.", body),
        p("The comparison reads the 611 frozen event centroids without reclustering. A match must satisfy both conditions:", body),
        bullet("inclusive temporal overlap with the incident reference window; and", styles),
        bullet("Euclidean metric distance of 5,000 m or less from an approximate reference anchor in <font name='Consolas'>EPSG:32617</font>.", styles),
        p("The two matching anchors were supplied by the researcher and are explicitly approximate. They are not claimed to have been published by the articles. The reference URLs are provenance records only; they were not inputs to the FIRMS pipeline, clustering, optical analysis, or modeling.", body),
        Spacer(1, 6 * mm),
        p("Official frozen comparisons", styles["Subhead"]),
        academic_table([
            ["Reference", "Window", "Official result"],
            ["Cerro Guacamaya", "23-27 Jan 2025", "6 matches within 5,000 m"],
            ["Cerro Los Picachos", "15-17 Jan 2025", "0 matches within 5,000 m"],
        ], [145, 120, 190], styles, font_size=7.7),
        Spacer(1, 5 * mm),
        p("These comparisons are relational evidence, not ground truth, institutional validation, labels, or accuracy tests.", styles["Quote"]),
    ])
    add_figure_page(
        story, styles, 3, "03_external_reference_map.png", "External-reference spatial context",
        "Frozen spatial context for 611 event centroids and the two approximate reference anchors. The displayed 5 km rings are visual approximations; official distances use Euclidean meters in EPSG:32617. Source artifact: site-data/figures/03_external_reference_map.png."
    )

    # 10 Guacamaya
    start_portrait(story)
    story.extend(section_header(styles, "10", "Case study: Cerro Guacamaya", "Six clusters, five gaps, one representation warning"))
    guac_rows = [["Cluster", "Detections", "Gap from prior (h)", "Max FRP (MW)"]]
    for cluster in timeline["clusters"]:
        gap = "-" if cluster["gap_from_previous_hours"] is None else f"{cluster['gap_from_previous_hours']:.3f}"
        guac_rows.append([
            f"C{cluster['order']}", str(cluster["detection_count"]), gap,
            f"{cluster['max_frp_mw']:.2f}",
        ])
    story.extend([
        p("The official 2025-01-23 to 2025-01-27 comparison returns six matched provisional clusters within the inclusive 5,000 m radius. They contain 2, 4, 3, 5, 1, and 4 detections. One cluster is flagged <font name='Consolas'>possible_chain_merge</font>; that review flag does not change the six-unit result.", body),
        academic_table(guac_rows, [80, 95, 160, 120], styles, font_size=7.7),
        Spacer(1, 4 * mm),
        p("The first cluster begins at 2025-01-24 06:11Z and the last ends at 2025-01-27 06:55Z, producing a 72.733 h overall span. The five inter-cluster gaps are 12.383 h, 23.300 h, 10.933 h, 11.083 h, and 12.617 h. Every gap exceeds the frozen six-hour link window.", body),
        p("The frozen interpretation is <font name='Consolas'>fragmentation_possible = true</font>. A prolonged documented incident may correspond to multiple FirePA events. This is a representation limitation, not proof that the clustering is wrong and not authorization to merge the six provisional units into one continuous spreading fire.", body),
    ])
    add_figure_page(
        story, styles, 4, "04_guacamaya_timeline.png", "Cerro Guacamaya matched-cluster timeline",
        "Six official matches are shown separately against the frozen six-hour window. Red labels mark inter-cluster gaps. The gap pattern is a representation limitation under t06, not an automatic merge or confirmed continuous incident. Source artifact: site-data/figures/04_guacamaya_timeline.png."
    )
    add_figure_page(
        story, styles, 5, "05_guacamaya_frp_distribution.png", "Cerro Guacamaya descriptive FRP sequence",
        "Maximum and mean FRP are shown by chronological matched cluster. FRP remains descriptive; the sequence is not a composite score, severity estimate, or causal inference. Source artifact: site-data/figures/05_guacamaya_frp_distribution.png."
    )

    # 11 Picachos
    start_portrait(story)
    story.extend(section_header(styles, "11", "Case study: Cerro Los Picachos", "A threshold-specific zero, not zero signal"))
    story.extend([
        DistanceGraphic(),
        p("The official 2025-01-15 to 2025-01-17 comparison returns zero matches within the inclusive 5,000 m radius. The nearest documented contemporary frozen event is 10,400.826 m from the approximate anchor. The correct frozen diagnosis is <font name='Consolas'>SPATIAL_THRESHOLD_MISS</font>.", body),
        p("The processed-detection audit records zero detections within 5 km, zero within 10 km, and one within 15 km. Extending the diagnostic date window to 2025-01-13 through 2025-01-19 does not change the 5 km result. These 10 km and 15 km checks are diagnostic context only; they do not alter the official 5,000 m rule.", body),
        p("Zero at 5 km must not be translated into no fire, no activity, no thermal signal, or absence of an event. It states only that no frozen event met the official temporal-overlap and distance rule.", styles["Quote"]),
    ])
    add_figure_page(
        story, styles, 6, "06_los_picachos_diagnostic.png", "Cerro Los Picachos diagnostic of the official zero",
        "The frozen plate preserves the official 5 km rule and shows the nearest documented contemporary signal at approximately 10.40 km. Wider-distance checks remain diagnostic context, not a changed matching rule. Source artifact: site-data/figures/06_los_picachos_diagnostic.png."
    )

    # 12 limitations
    start_portrait(story)
    story.extend(section_header(styles, "12", "Scientific and interpretive limitations", "The inference boundary is a primary result"))
    limitations = [
        "A FIRMS anomaly does not independently confirm a wildfire.",
        "A provisional event is an analytical group, not necessarily one physical incident.",
        "An event centroid is not a burn perimeter or precision ground location.",
        "An unobserved optical case is not a negative case.",
        "NBR and dNBR are descriptive indices, not validated severity.",
        "Formal human observations equal zero.",
        "No ground truth or institutional validation exists.",
        "No accuracy estimate, supervised predictive model, or generalization claim exists.",
        "The external-reference search is limited and non-exhaustive.",
        "Guacamaya may expose temporal fragmentation under the six-hour convention.",
        "The Picachos zero is specific to the inclusive 5,000 m rule.",
        "Findings are limited to Coclé and the frozen study period.",
    ]
    story.extend([
        p("FirePA is a descriptive research pilot. Its restraint is methodological, not rhetorical: each analytical stage records what the evidence supports and where interpretation must stop.", body),
        Rule(width=0.8, color=CLAY, space_after=8),
    ])
    for item in limitations:
        story.append(bullet(item, styles))
    story.extend([
        Spacer(1, 6 * mm),
        p("FirePA does not provide real-time monitoring, alerts, emergency guidance, forecasting, validated decision support, causal attribution, or operational wildfire classification.", styles["Quote"]),
    ])

    # 13 reproducibility
    start_portrait(story)
    story.extend(section_header(styles, "13", "Reproducibility and public package", "A deterministic package with an explicit protected-source boundary"))
    story.extend([
        p("The machine-readable <font name='Consolas'>site-data/</font> package is the highest public authority. It contains exactly 611 WGS84 event centroids, two approximate reference anchors, the Guacamaya chronology, methodology, citations, provenance, six byte-frozen figures, and a manifest SHA-256 ledger.", body),
        p("A clean clone can build and test the bilingual Astro publication and verify the complete public package without a backend, network access, Earth Engine, or the non-redistributed Coclé source boundary.", body),
        p("cd site<br/>npm ci<br/>npm run build<br/>npm run test", styles["Mono"]),
        p("python scripts/verify_public_release_package.py --package site-data<br/>python -m pytest -q", styles["Mono"]),
        p("A clean clone cannot fully regenerate the scientific history. Raw FIRMS rows and local manifests, processed/interim research tables, Sentinel-2 rasters and Earth Engine outputs, the original administrative boundary, private review mappings and databases, historical model-assisted responses, and generated review bundles are intentionally excluded.", body),
        p("When every protected artifact is available, the explicit full-source gate verifies their hashes. It is expected to fail in a clean public clone rather than fabricate substitutes:", body),
        p("python scripts/verify_public_release_package.py --package site-data --full-source", styles["Mono"]),
    ])

    # 14 architecture
    start_portrait(story)
    story.extend(section_header(styles, "14", "Software and publication architecture", "Current infrastructure, separated from scientific evidence"))
    story.extend([
        ArchitectureGraphic(),
        p("The analytical implementation is a local Python package with verification tests. Its approved outputs are projected into the frontend-agnostic <font name='Consolas'>site-data/</font> package. The public publication is a bilingual static Astro site in English and Latin American Spanish. Source is hosted in the public GitHub repository and the static site is distributed through Cloudflare Pages.", body),
        p("The website can be built from the public package without private inputs. Its Coclé presentation geometry falls back only to a tracked deterministic derivative; it does not invent replacement cartography.", body),
        p("On pushes and pull requests targeting <font name='Consolas'>main</font>, GitHub Actions runs two clean-clone jobs: the public package verifier and public Python test suite; and <font name='Consolas'>npm ci</font>, the Astro build, and the Astro publication contract. It does not run the <font name='Consolas'>--full-source</font> gate or validate protected/private inputs. Cloudflare Pages publishes the static site from the public repository; it is distribution infrastructure, not scientific evidence or an operational wildfire platform.", body),
        Spacer(1, 5 * mm),
        p("Public endpoints", styles["Subhead"]),
        p(f"Website: {link('https://firepa.pages.dev/')}<br/>Repository: {link('https://github.com/jrod-md/FirePA')}", body),
    ])

    # 15 conclusion
    start_portrait(story)
    story.extend(section_header(styles, "15", "Conclusion", "A bounded evidence structure, not a classifier"))
    story.extend([
        p("FirePA demonstrates a reproducible reduction from satellite thermal signals to provisional analytical events while preserving uncertainty. It audits 1,532 FIRMS detections, retains 1,185 records in the study area, and groups them into 611 provisional events under a frozen and inspectable convention. Optical follow-up and external references add context without becoming labels.", body),
        p("The two case studies expose complementary limits. Cerro Guacamaya shows that prolonged documented activity can align with six separate groups when every inter-cluster gap exceeds the six-hour link window. Cerro Los Picachos shows that zero matches within an official 5 km threshold can coexist with a documented contemporary signal 10,400.826 m from the approximate anchor.", body),
        p("Neither case provides ground truth. Together, they show why threshold results and analytical units must be reported in the language of the procedure that produced them.", body),
        Spacer(1, 9 * mm),
        p("The principal contribution is not a wildfire classifier.<br/>It is a bounded evidence structure.", styles["Quote"]),
        p("Within that structure, provisional units remain provisional, unobserved cases remain unresolved, optical indices remain descriptive, model-assisted calibration remains exploratory, and external references remain relational. This restraint makes the publication reproducible without claiming more than its sources can support.", body),
    ])

    # References
    start_portrait(story)
    story.extend(section_header(styles, "R", "References", "Scientific sources and external incident documents"))
    scientific_refs = [
        ("[S1]", "NASA FIRMS / LANCE. Area API, data availability service, and API documentation.", "https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html"),
        ("[S2]", "Copernicus Sentinel-2 Surface Reflectance Harmonized. Google Earth Engine data catalog.", "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED"),
        ("[S3]", "Google Cloud Score+ S2 Harmonized. Google Earth Engine data catalog.", "https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED"),
        ("[S4]", "Instituto Geográfico Nacional Tommy Guardia / ANATI. Administrative divisions source page.", "https://ignpanama.anati.gob.pa/index.php/divisionpolitica-administrativa"),
    ]
    for label, text_value, url in scientific_refs:
        story.append(p(f"<b>{label}</b> {escape(text_value)} {link(url, url)}", styles["Reference"]))
    story.append(Spacer(1, 4 * mm))
    story.append(p("External incident source registry", styles["Subhead"]))
    incidents = {"REFERENCE-001": "Cerro Los Picachos", "REFERENCE-002": "Cerro Guacamaya"}
    for item in citations["external_sources"]:
        source_id = item["source_id"].replace("SOURCE-", "E")
        label = f"[{source_id}]"
        publisher = item["publisher"]
        date = item["publication_date"]
        incident = incidents[item["incident_id"]]
        text_value = f"{publisher}. {date}. {incident}."
        url_markup = (
            long_reference_link(item["url"])
            if source_id == "E007"
            else link(item["url"], item["url"])
        )
        story.append(p(f"<b>{label}</b> {escape(text_value)} {url_markup}", styles["Reference"]))
    story.extend([
        Spacer(1, 4 * mm),
        p("Reference boundary", styles["Subhead"]),
        p("No missing authors, DOIs, issue numbers, access dates, venues, or publication metadata have been inferred. The seven external URLs are provenance records and relational context, not scientific truth labels.", small),
    ])

    # Appendix A
    start_portrait(story)
    story.extend(section_header(styles, "A", "Public package inventory", "Compact file and purpose register"))
    inventory = [
        ["Path", "Purpose"],
        ["project-summary.json", "Frozen counts, scope, period, and findings"],
        ["events.geojson", "Exactly 611 public WGS84 event centroids"],
        ["external-references.geojson", "Two approximate comparison anchors"],
        ["guacamaya-timeline.json", "Six-cluster chronology and five gaps"],
        ["methodology.json", "Machine-readable workflow and limits"],
        ["citations.json", "Scientific-document and external-source registry"],
        ["provenance.json", "Inputs, transformations, hashes, and privacy boundary"],
        ["figures/01_pipeline_overview.png", "Byte-frozen scientific pipeline plate"],
        ["figures/02_cluster_distribution.png", "Byte-frozen descriptive cluster distributions"],
        ["figures/03_external_reference_map.png", "Byte-frozen external-reference context"],
        ["figures/04_guacamaya_timeline.png", "Byte-frozen Guacamaya chronology"],
        ["figures/05_guacamaya_frp_distribution.png", "Byte-frozen Guacamaya FRP description"],
        ["figures/06_los_picachos_diagnostic.png", "Byte-frozen Picachos threshold diagnostic"],
        ["manifest.json", "Deterministic public-package SHA-256 ledger"],
    ]
    story.extend([
        p("Package version: <font name='Consolas'>firepa-public-release-v1</font>. Scientific freeze: <font name='Consolas'>7694da7df5808911de48de84016759c5fd22f176</font>.", body),
        academic_table(inventory, [210, 245], styles, font_size=6.8),
        Spacer(1, 5 * mm),
        p("Public event properties are descriptive. None is a confirmed-fire, severity, ground-truth, or predictive-model field.", styles["Caption"]),
    ])

    # Appendix B
    start_portrait(story)
    story.extend(section_header(styles, "B", "Frozen figure integrity", "Dimensions and SHA-256 ledger"))
    hash_rows = [["Figure", "Dimensions", "SHA-256"]]
    for entry in provenance["figure_provenance"]:
        hash_rows.append([
            entry["derivative_path"].split("/")[-1],
            f"{entry['width']} x {entry['height']}",
            entry["derivative_sha256"],
        ])
    hash_table = academic_table(hash_rows, [157, 68, 230], styles, font_size=5.7)
    story.extend([
        p("All six figures are public derivatives copied byte-for-byte from the frozen final scientific report. Their scientific content was not recomputed. They were placed proportionally in this PDF without cropping, recoloring, relabeling, sharpening, or destructive resizing.", body),
        hash_table,
        Spacer(1, 8 * mm),
        p("Integrity rule", styles["Subhead"]),
        p("The generation script verifies every source PNG against the public provenance ledger before creating the PDF. Publication QA repeats the check after generation. A mismatch blocks report generation.", body),
    ])

    # Appendix C
    start_portrait(story)
    story.extend(section_header(styles, "C", "Reproducibility commands", "Clean-clone verification and protected-source boundary"))
    story.extend([
        p("Website verification", styles["Subhead"]),
        p("cd site<br/>npm ci<br/>npm run build<br/>npm run test", styles["Mono"]),
        p("The Astro build creates the English and Latin American Spanish static routes. The site contract verifies the public data and all six frozen figures.", small),
        p("Public Python verification", styles["Subhead"]),
        p("python scripts/verify_public_release_package.py --package site-data<br/>python -m pytest -q", styles["Mono"]),
        p("The default verifier checks the deterministic public package. Self-contained tests run; tests whose named protected inputs are absent skip explicitly.", small),
        p("Full-source gate", styles["Subhead"]),
        p("python scripts/verify_public_release_package.py --package site-data --full-source", styles["Mono"]),
        p("This stricter mode requires every excluded source artifact and compares its frozen hash. It is expected to fail in a clean public clone. The pipeline must fail rather than fabricate a scientific substitute.", small),
        Rule(width=0.8, color=CLAY, space_after=8),
        p("Report regeneration", styles["Subhead"]),
        p("python report/build_firepa_report.py", styles["Mono"]),
        p("The report source reads only the public package, the citation author, and the six frozen PNGs. It does not recalculate events, distances, optical metrics, or scientific figures.", small),
    ])

    doc.build(story)

    for filename, expected in expected_figure_hashes.items():
        actual = sha256(FIGURES / filename)
        if actual != expected:
            raise RuntimeError(f"Frozen figure hash mismatch after build: {filename}")

    print(f"Created {OUT}")
    print(f"Author: {author}")
    print(f"Frozen figures verified: {len(expected_figure_hashes)}")


if __name__ == "__main__":
    build_report()
