# /// script
# requires-python = ">=3.13"
# dependencies = ["reportlab==4.4.9", "mistune==3.2.1"]
# ///
# Global context: render public Markdown reports without loading app config,
# credentials, captures, or other runtime artifacts. Run from the repo root:
# uv run scripts/render_report.py reports/2026-10-13-gpt-6-luna.md
# Script dependencies stay isolated: https://docs.astral.sh/uv/guides/scripts/
import argparse  # Parse an explicit list of Markdown sources to render.
import logging  # Timestamp rendering progress without logging private state.
import re  # Normalize typographic dashes for portable PDF text.
from html import escape  # Prevent source text from injecting Paragraph markup.
from pathlib import Path  # Keep each PDF adjacent to its Markdown source.
from urllib.parse import quote, urljoin  # Resolve links against the source URL.

import mistune  # Parse real Markdown rather than approximating tables with regex.
from reportlab.lib import colors  # Share restrained heading and table colors.
from reportlab.lib.pagesizes import A4  # Use a portable printable page size.
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable, ListFlowable, ListItem, Paragraph, Preformatted,
    SimpleDocTemplate, Table,
)

ROOT = Path(__file__).resolve().parents[1]  # Anchor relative source URLs in Git.
REPOSITORY = "https://github.com/BurnyCoder/deep-work-jarvis-waifu-supervisor/blob/master/"
AUTHOR = "Libor Burian"  # Keep PDF attribution consistent across experiment papers.
ACCENT = colors.HexColor("#163A5F")  # One accent for section hierarchy.


def inline_markup(tokens, source):
    """Convert parsed inline nodes into escaped ReportLab paragraph markup."""
    # Mistune AST: https://mistune.lepture.com/en/latest/upgrade.html#astrenderer
    # Paragraph markup: https://docs.reportlab.com/reportlab/userguide/ch6_paragraphs/
    pieces = []  # Accumulate only supported, explicitly escaped inline content.
    for token in tokens:
        kind = token["type"]  # Dispatch on parser output rather than raw Markdown.
        text = inline_markup(token.get("children", []), source)
        if kind in {"text", "inline_html", "codespan"}:
            text = escape(re.sub("[\u2010-\u2015]", "-", token["raw"]))
            if kind == "codespan":
                text = f'<font name="Courier">{text}</font>'
        elif kind in {"strong", "emphasis"}:
            tag = "b" if kind == "strong" else "i"
            text = f"<{tag}>{text}</{tag}>"
        elif kind == "link":
            base = REPOSITORY + quote(source.resolve().relative_to(ROOT).as_posix())
            target = urljoin(base, token["attrs"]["url"])
            text = f'<link href="{escape(target, quote=True)}" color="#2463A6">{text}</link>'
        elif kind in {"softbreak", "linebreak"}:
            text = " " if kind == "softbreak" else "<br/>"
        else:
            raise ValueError(f"Unsupported inline Markdown: {kind}")
        pieces.append(text)  # Preserve node order, including nested formatting.
    return "".join(pieces)


def report_styles():
    """Reuse ReportLab styles with readable compact body and table spacing."""
    styles = getSampleStyleSheet()  # Standard heading styles keep with next text.
    styles["BodyText"].fontSize, styles["BodyText"].leading = 10, 13.5
    styles["BodyText"].spaceAfter = 6
    for name in ("Title", "Heading1", "Heading2", "Heading3"):
        styles[name].textColor = ACCENT
    styles.add(ParagraphStyle("Cell", parent=styles["BodyText"], fontSize=8.5, leading=11))
    styles.add(ParagraphStyle("CellHead", parent=styles["Cell"], fontName="Helvetica-Bold"))
    return styles


def flowables(tokens, source, styles, width):
    """Map block nodes to native paginating paragraphs, lists, and tables."""
    # Platypus layout: https://docs.reportlab.com/reportlab/userguide/ch5_platypus/
    for token in tokens:
        kind, children = token["type"], token.get("children", [])
        if kind in {"paragraph", "block_text", "heading"}:
            level = token.get("attrs", {}).get("level", 0)
            style = "Title" if level == 1 else f"Heading{min(level - 1, 3)}" if level else "BodyText"
            yield Paragraph(inline_markup(children, source), styles[style])
        elif kind == "list":
            attrs = token["attrs"]  # Preserve ordered starts and nested item flow.
            items = [ListItem(list(flowables(item["children"], source, styles, width - 18))) for item in children]
            yield ListFlowable(items, bulletType="1" if attrs["ordered"] else "bullet",
                               start=attrs.get("start"), leftIndent=18, bulletFontSize=9)
        elif kind == "table":
            # Fixed column widths wrap Paragraph cells; repeat the header on
            # each page: https://docs.reportlab.com/reportlab/userguide/ch7_tables/
            head, body = children
            rows = [head["children"]] + [row["children"] for row in body["children"]]
            data = [[Paragraph(inline_markup(cell["children"], source),
                               styles["CellHead" if index == 0 else "Cell"])
                     for cell in row] for index, row in enumerate(rows)]
            yield Table(data, colWidths=[width / len(data[0])] * len(data[0]),
                        repeatRows=1, spaceAfter=10, style=[
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EFF6")),
                            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ])
        elif kind == "block_code":
            yield Preformatted(token["raw"], styles["Code"], maxLineLength=max(20, int(width / 5.4)))
        elif kind == "block_quote":
            yield from flowables(children, source, styles, width)
        elif kind == "thematic_break":
            yield HRFlowable(width="100%", color=ACCENT, spaceAfter=8)
        elif kind != "blank_line":
            raise ValueError(f"Unsupported block Markdown: {kind}")


def page_footer(canvas, document):
    """Attribute every paper and number pages without a hard-coded report title."""
    canvas.saveState()  # Restore drawing state after the small footer.
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(44, 27, f"Deep Work | {AUTHOR}")
    canvas.drawRightString(A4[0] - 44, 27, str(document.page))
    canvas.restoreState()


def build_report(source):
    """Parse one Markdown source and render its adjacent PDF with real metadata."""
    source = source.resolve()  # Link resolution also verifies repository locality.
    source.relative_to(ROOT)
    if source.suffix.lower() != ".md":
        raise ValueError(f"Expected a Markdown source: {source}")
    tokens = mistune.create_markdown(renderer="ast", plugins=["table"])(source.read_text(encoding="utf-8"))
    heading = next((token for token in tokens if token["type"] == "heading" and token["attrs"]["level"] == 1), None)
    if heading is None:
        raise ValueError(f"Report needs an H1 title: {source}")
    styles = report_styles()
    title = Paragraph(inline_markup(heading["children"], source), styles["Title"]).getPlainText()
    target = source.with_suffix(".pdf")  # The source remains unchanged.
    logging.info("Rendering %s -> %s", source, target)
    document = SimpleDocTemplate(str(target), pagesize=A4, rightMargin=44,
                                 leftMargin=44, topMargin=42, bottomMargin=45,
                                 title=title, author=AUTHOR)
    document.build(list(flowables(tokens, source, styles, A4[0] - 100)),
                   onFirstPage=page_footer, onLaterPages=page_footer)
    logging.info("Rendered %s", target)
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description="Render repository Markdown reports to adjacent PDFs.")
    parser.add_argument("sources", type=Path, nargs="+", help="Markdown files with an H1 title")
    for source in parser.parse_args().sources:
        build_report(source)  # Keep the entry point a readable rendering loop.
