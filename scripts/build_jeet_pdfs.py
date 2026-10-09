"""Build and audit review PDFs from the frozen JEET manuscript sources.

This is a renderer-independent fallback for workstations without Microsoft Word or
LibreOffice.  It consumes the same Markdown, BibTeX, figures, caption registry, and
citation-order logic as ``build_jeet_submission.py``.  The generated PDFs are review
copies; the editable DOCX files remain the submission source files required by JEET.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_jeet_submission as jeet

FONT_DIR = Path("C:/Windows/Fonts")
FONT_FILES = {
    "TimesNewRoman": FONT_DIR / "times.ttf",
    "TimesNewRoman-Bold": FONT_DIR / "timesbd.ttf",
    "TimesNewRoman-Italic": FONT_DIR / "timesi.ttf",
    "TimesNewRoman-BoldItalic": FONT_DIR / "timesbi.ttf",
    "CourierNew": FONT_DIR / "cour.ttf",
}


def register_fonts() -> None:
    """Register Windows fonts and their bold/italic family mapping."""
    missing = [str(path) for path in FONT_FILES.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required fonts are missing: {missing}")
    for name, path in FONT_FILES.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "TimesNewRoman",
        normal="TimesNewRoman",
        bold="TimesNewRoman-Bold",
        italic="TimesNewRoman-Italic",
        boldItalic="TimesNewRoman-BoldItalic",
    )


def make_styles(*, supplement: bool) -> dict[str, ParagraphStyle]:
    """Create compact, monochrome journal-review styles."""
    base = getSampleStyleSheet()
    body_size = 8.5 if supplement else 10
    return {
        "body": ParagraphStyle(
            "JEETBody",
            parent=base["BodyText"],
            fontName="TimesNewRoman",
            fontSize=body_size,
            leading=body_size * 1.15,
            alignment=TA_LEFT if supplement else TA_JUSTIFY,
            spaceAfter=4 if supplement else 6,
            textColor=colors.black,
            allowWidows=0,
            allowOrphans=0,
        ),
        "title": ParagraphStyle(
            "JEETTitle",
            parent=base["Title"],
            fontName="TimesNewRoman-Bold",
            fontSize=14 if supplement else 15,
            leading=16 if supplement else 17,
            alignment=TA_CENTER,
            spaceAfter=8 if supplement else 11,
            textColor=colors.black,
        ),
        "subtitle": ParagraphStyle(
            "JEETSubtitle",
            parent=base["BodyText"],
            fontName="TimesNewRoman-Italic",
            fontSize=8.5,
            leading=10,
            alignment=TA_CENTER,
            spaceAfter=8,
            textColor=colors.black,
        ),
        "h1": ParagraphStyle(
            "JEETH1",
            parent=base["Heading1"],
            fontName="TimesNewRoman-Bold",
            fontSize=11 if supplement else 12,
            leading=13 if supplement else 14,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
            textColor=colors.black,
        ),
        "h2": ParagraphStyle(
            "JEETH2",
            parent=base["Heading2"],
            fontName="TimesNewRoman-Bold",
            fontSize=10 if supplement else 11,
            leading=12 if supplement else 13,
            spaceBefore=8,
            spaceAfter=3,
            keepWithNext=True,
            textColor=colors.black,
        ),
        "h3": ParagraphStyle(
            "JEETH3",
            parent=base["Heading3"],
            fontName="TimesNewRoman-BoldItalic",
            fontSize=9 if supplement else 10,
            leading=11 if supplement else 12,
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
            textColor=colors.black,
        ),
        "caption": ParagraphStyle(
            "JEETCaption",
            parent=base["BodyText"],
            fontName="TimesNewRoman",
            fontSize=8 if supplement else 9,
            leading=9.5 if supplement else 10.5,
            alignment=TA_LEFT,
            spaceBefore=2,
            spaceAfter=6,
            textColor=colors.black,
        ),
        "table_caption": ParagraphStyle(
            "JEETTableCaption",
            parent=base["BodyText"],
            fontName="TimesNewRoman-Bold",
            fontSize=8 if supplement else 9,
            leading=9.5 if supplement else 10.5,
            alignment=TA_LEFT,
            spaceBefore=5,
            spaceAfter=3,
            keepWithNext=True,
            textColor=colors.black,
        ),
        "table": ParagraphStyle(
            "JEETTableCell",
            parent=base["BodyText"],
            fontName="TimesNewRoman",
            fontSize=6.1 if supplement else 7.4,
            leading=7.1 if supplement else 8.5,
            alignment=TA_LEFT,
            spaceAfter=0,
            textColor=colors.black,
            splitLongWords=True,
        ),
        "table_header": ParagraphStyle(
            "JEETTableHeader",
            parent=base["BodyText"],
            fontName="TimesNewRoman-Bold",
            fontSize=6.1 if supplement else 7.4,
            leading=7.1 if supplement else 8.5,
            alignment=TA_CENTER,
            spaceAfter=0,
            textColor=colors.black,
            splitLongWords=True,
        ),
        "reference": ParagraphStyle(
            "JEETReference",
            parent=base["BodyText"],
            fontName="TimesNewRoman",
            fontSize=8.3,
            leading=9.5,
            leftIndent=18,
            firstLineIndent=-18,
            spaceAfter=3,
            textColor=colors.black,
        ),
        "quote": ParagraphStyle(
            "JEETQuote",
            parent=base["BodyText"],
            fontName="TimesNewRoman-Italic",
            fontSize=8.2,
            leading=9.5,
            leftIndent=14,
            rightIndent=14,
            spaceAfter=6,
            textColor=colors.black,
        ),
        "equation": ParagraphStyle(
            "JEETEquation",
            parent=base["BodyText"],
            fontName="TimesNewRoman-Italic",
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=6,
            textColor=colors.black,
        ),
        "bullet": ParagraphStyle(
            "JEETBullet",
            parent=base["BodyText"],
            fontName="TimesNewRoman",
            fontSize=body_size,
            leading=body_size * 1.15,
            leftIndent=18,
            firstLineIndent=-9,
            bulletIndent=5,
            spaceAfter=3,
            textColor=colors.black,
        ),
    }


def inline_markup(text: str, cite_state: dict[str, int] | None = None) -> str:
    """Convert the small Markdown subset used by the paper to ReportLab markup."""
    if cite_state is not None:
        text = jeet.replace_citations(text, cite_state)
    text = text.replace(r"\(", "$ ").replace(r"\)", " $")
    text = jeet.normalize_text(text)
    token_re = re.compile(r"(\*\*.+?\*\*|`.+?`|\$.*?\$|\*[^*]+?\*)")
    fragments: list[str] = []
    cursor = 0
    for match in token_re.finditer(text):
        fragments.append(html.escape(text[cursor : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            fragments.append(f"<b>{html.escape(token[2:-2])}</b>")
        elif token.startswith("`"):
            fragments.append(
                f'<font name="CourierNew" size="7.5">{html.escape(token[1:-1])}</font>'
            )
        elif token.startswith("$"):
            math = jeet.latex_to_unicode(token[1:-1].strip())
            fragments.append(f"<i>{html.escape(math)}</i>")
        else:
            fragments.append(f"<i>{html.escape(token[1:-1])}</i>")
        cursor = match.end()
    fragments.append(html.escape(text[cursor:]))
    return "".join(fragments).replace("\n", "<br/>")


def weighted_widths(rows: list[list[str]], total_width: float) -> list[float]:
    """Allocate table width by bounded content weights."""
    columns = len(rows[0])
    weights = []
    for column in range(columns):
        longest = max(len(re.sub(r"[*`]", "", row[column])) for row in rows)
        weights.append(max(4.0, min(22.0, longest**0.5 * 2.2)))
    minimum = 31 if columns >= 9 else 45
    if minimum * columns > total_width:
        minimum = total_width / columns * 0.45
    remainder = total_width - minimum * columns
    total_weight = sum(weights)
    widths = [minimum + remainder * weight / total_weight for weight in weights]
    widths[-1] += total_width - sum(widths)
    return widths


def make_table(
    rows: list[list[str]],
    *,
    width: float,
    styles: dict[str, ParagraphStyle],
    cite_state: dict[str, int],
) -> LongTable:
    """Build a page-splitting table with a repeated header."""
    data: list[list[Paragraph]] = []
    for row_index, row in enumerate(rows):
        cells = []
        for value in row:
            style = styles["table_header"] if row_index == 0 else styles["table"]
            cells.append(Paragraph(inline_markup(value, cite_state), style))
        data.append(cells)
    table = LongTable(
        data,
        colWidths=weighted_widths(rows, width),
        repeatRows=1,
        splitByRow=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7E6E6")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#707070")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.2),
                ("TOPPADDING", (0, 0), (-1, -1), 2.0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
            ]
        )
    )
    return table


def figure_flowables(
    source: Path,
    caption: str,
    number: int,
    *,
    max_width: float,
    max_height: float,
    style: ParagraphStyle,
) -> KeepTogether:
    """Create a proportionally scaled image with its numbered caption."""
    png = source.with_suffix(".png")
    if not png.exists():
        raise FileNotFoundError(png)
    with PILImage.open(png) as image:
        width_px, height_px = image.size
    ratio = min(max_width / width_px, max_height / height_px)
    figure = Image(str(png), width=width_px * ratio, height=height_px * ratio)
    figure.hAlign = "CENTER"
    caption_text = f"<b>Fig. {number}</b>  {inline_markup(caption.rstrip('.'))}"
    return KeepTogether([figure, Paragraph(caption_text, style)])


def add_references(story: list[object], cite_state: dict[str, int], styles) -> None:
    """Append references in first-citation order."""
    entries = jeet.parse_bibtex(jeet.BIBLIOGRAPHY)
    missing = [key for key in cite_state if key not in entries]
    if missing:
        raise KeyError(f"Missing bibliography entries: {missing}")
    story.append(Paragraph("References", styles["h1"]))
    for key, number in sorted(cite_state.items(), key=lambda item: item[1]):
        reference = jeet.format_reference(entries[key])
        story.append(Paragraph(f"[{number}] {html.escape(reference)}", styles["reference"]))


def build_story(
    source: Path,
    *,
    supplement: bool,
    content_width: float,
    content_height: float,
) -> tuple[list[object], dict[str, int]]:
    """Parse the constrained paper Markdown into ReportLab flowables."""
    lines = source.read_text(encoding="utf-8").splitlines()
    title, index = jeet.extract_front_title(lines)
    styles = make_styles(supplement=supplement)
    story: list[object] = [Paragraph(inline_markup(title), styles["title"])]
    if supplement:
        story.append(
            Paragraph(
                f"Online Resource 1 for {jeet.JOURNAL} - anonymous review copy",
                styles["subtitle"],
            )
        )

    cite_state: dict[str, int] = {}
    figures = 0
    tables = 0
    in_equation = False
    equation_lines: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        if in_equation:
            if stripped == r"\]":
                equation = jeet.latex_to_unicode(" ".join(equation_lines).rstrip("."))
                story.append(Paragraph(html.escape(equation), styles["equation"]))
                equation_lines = []
                in_equation = False
            else:
                equation_lines.append(stripped)
            index += 1
            continue
        if stripped == r"\[":
            in_equation = True
            index += 1
            continue
        if not stripped:
            index += 1
            continue
        if stripped.startswith(">"):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            if supplement:
                story.append(
                    Paragraph(inline_markup(" ".join(quote_lines), cite_state), styles["quote"])
                )
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            if level > 1:
                style_name = "h1" if level == 2 else ("h2" if level == 3 else "h3")
                story.append(
                    Paragraph(inline_markup(heading.group(2), cite_state), styles[style_name])
                )
            index += 1
            continue
        image_match = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
        if image_match:
            figures += 1
            image_path = (source.parent / Path(image_match.group(2))).resolve()
            story.append(
                figure_flowables(
                    image_path,
                    image_match.group(1),
                    figures,
                    max_width=content_width,
                    max_height=min(content_height * 0.72, 7.0 * inch),
                    style=styles["caption"],
                )
            )
            index += 1
            continue
        if stripped.startswith("|"):
            rows, index = jeet.parse_table(lines, index)
            tables += 1
            if not supplement:
                caption = jeet.TABLE_CAPTIONS[tables - 1]
                story.append(
                    Paragraph(f"Table {tables}  {html.escape(caption)}", styles["table_caption"])
                )
            story.append(
                make_table(rows, width=content_width, styles=styles, cite_state=cite_state)
            )
            story.append(Spacer(1, 4))
            continue
        if stripped.startswith("- "):
            while index < len(lines) and lines[index].strip().startswith("- "):
                bullet_parts = [lines[index].strip()[2:]]
                index += 1
                while index < len(lines):
                    continuation = lines[index].strip()
                    if (
                        not continuation
                        or continuation.startswith(("#", "!", "|", "- ", ">"))
                        or continuation == r"\["
                    ):
                        break
                    bullet_parts.append(continuation)
                    index += 1
                story.append(
                    Paragraph(
                        inline_markup(" ".join(bullet_parts), cite_state),
                        styles["bullet"],
                        bulletText="•",
                    )
                )
            continue

        block = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line.startswith(("#", "!", "|", "- ", ">"))
                or next_line == r"\["
            ):
                break
            block.append(next_line)
            index += 1
        paragraph_text = " ".join(block)
        if paragraph_text.startswith("**Keywords:**"):
            keywords = paragraph_text[len("**Keywords:**") :].strip()
            story.append(
                Paragraph(f"<b>Keywords:</b> {inline_markup(keywords, cite_state)}", styles["body"])
            )
        else:
            story.append(Paragraph(inline_markup(paragraph_text, cite_state), styles["body"]))

    if not supplement:
        add_references(story, cite_state, styles)
    return story, {"figures": figures, "tables": tables, "citations": len(cite_state)}


def page_callback(*, supplement: bool):
    """Return a canvas callback that supplies anonymous metadata and page numbers."""
    header = "Online Resource 1" if supplement else jeet.SHORT_TITLE

    def draw_page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setAuthor("Anonymous")
        canvas.setTitle("Supplementary Material" if supplement else jeet.TITLE)
        canvas.setSubject(f"Anonymous review copy for {jeet.JOURNAL}")
        canvas.setKeywords("PMSM, stator fault, cross-dataset evaluation, negative transfer")
        canvas.setFont("TimesNewRoman-Italic", 7.5)
        canvas.setFillColor(colors.HexColor("#444444"))
        canvas.drawString(doc.leftMargin, doc.pagesize[1] - 0.36 * inch, header)
        canvas.setFont("TimesNewRoman", 8)
        canvas.drawCentredString(doc.pagesize[0] / 2, 0.36 * inch, str(doc.page))
        canvas.restoreState()

    return draw_page


def audit_pdf(path: Path, *, supplement: bool) -> dict[str, object]:
    """Check PDF metadata, extractability, page geometry, anonymity, and blank pages."""
    reader = PdfReader(str(path))
    if not reader.pages:
        raise AssertionError(f"PDF has no pages: {path}")
    texts = [(page.extract_text() or "").strip() for page in reader.pages]
    blank_pages = [index + 1 for index, text in enumerate(texts) if len(text) < 40]
    if blank_pages:
        raise AssertionError(f"Near-blank PDF pages in {path.name}: {blank_pages}")
    merged = "\n".join(texts)
    forbidden = ["C:\\Users", "lkcfq", "AUTHOR INPUT REQUIRED", "[AUTHOR", "Changwon"]
    leaked = [token for token in forbidden if token.lower() in merged.lower()]
    if leaked:
        raise AssertionError(f"Anonymous PDF contains forbidden tokens: {leaked}")
    author = str((reader.metadata or {}).get("/Author", ""))
    if author != "Anonymous":
        raise AssertionError(f"Unexpected PDF author metadata: {author!r}")
    expected = landscape(letter) if supplement else letter
    page_sizes = []
    for page in reader.pages:
        size = (round(float(page.mediabox.width), 2), round(float(page.mediabox.height), 2))
        page_sizes.append(size)
        if abs(size[0] - expected[0]) > 0.5 or abs(size[1] - expected[1]) > 0.5:
            raise AssertionError(f"Unexpected page size {size} in {path.name}")
    return {
        "output": str(path.relative_to(jeet.ROOT)),
        "sha256": jeet.sha256(path),
        "pages": len(reader.pages),
        "page_size_points": list(page_sizes[0]),
        "author": author,
        "minimum_extracted_characters_per_page": min(len(text) for text in texts),
    }


def build_pdf(source: Path, output: Path, *, supplement: bool) -> dict[str, object]:
    """Build one PDF and return its structural audit."""
    pagesize = landscape(letter) if supplement else letter
    margin = 0.55 * inch if supplement else inch
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=pagesize,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=0.62 * inch if supplement else 0.68 * inch,
        bottomMargin=0.58 * inch,
        title="Supplementary Material" if supplement else jeet.TITLE,
        author="Anonymous",
        subject=f"Anonymous review copy for {jeet.JOURNAL}",
        allowSplitting=1,
    )
    story, counts = build_story(
        source,
        supplement=supplement,
        content_width=doc.width,
        content_height=doc.height,
    )
    callback = page_callback(supplement=supplement)
    doc.build(story, onFirstPage=callback, onLaterPages=callback)
    audit = audit_pdf(output, supplement=supplement)
    audit.update(counts)
    return audit


def build() -> dict[str, object]:
    """Build both review PDFs and merge their hashes into the package metadata."""
    register_fonts()
    jeet.audit_sources()
    manuscript = build_pdf(
        jeet.MANUSCRIPT,
        jeet.OUT_DIR / "Manuscript_Anonymous.pdf",
        supplement=False,
    )
    supplement = build_pdf(
        jeet.SUPPLEMENT,
        jeet.OUT_DIR / "ESM_1_Supplementary_Material.pdf",
        supplement=True,
    )
    metadata_path = jeet.OUT_DIR / "build_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["pdfs"] = {"manuscript": manuscript, "supplement": supplement}
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata["pdfs"]


def check() -> dict[str, object]:
    """Audit existing review PDFs without rebuilding them."""
    register_fonts()
    return {
        "manuscript": audit_pdf(
            jeet.OUT_DIR / "Manuscript_Anonymous.pdf",
            supplement=False,
        ),
        "supplement": audit_pdf(
            jeet.OUT_DIR / "ESM_1_Supplementary_Material.pdf",
            supplement=True,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Audit existing PDFs")
    args = parser.parse_args()
    result = check() if args.check else build()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
