#!/usr/bin/env python3
"""Render a Loupe markdown document to a branded PDF.

Usage:
    make_loupe_pdf.py <input.md> <output.pdf> ["Cover title"] [--alternate]

Light ground throughout by default — these are portrait documents meant to be
read and printed, and dark pages cost legibility and toner for no reading
benefit. Pass `--alternate` to alternate light / dark ground per top-level
section (first section light), which suits a screen-read deck-style document.

Top-level `## ` headings become sections. Anything before the first `## `
renders on the cover page with the title. The `# ` H1, if present, is dropped in
favour of the cover title (which defaults to the H1 text).

Each section is rendered independently, then composited over a background page
drawn with reportlab. This is deliberate: xhtml2pdf's named `@page` templates
discard the first content flow, and `@page { background-color }` is not honoured,
so per-page ground has to be painted underneath rather than declared in CSS.

Requires xhtml2pdf, markdown, pypdf and reportlab. These are not in the system
interpreter — use a virtualenv:

    python3 -m venv /tmp/loupe-pdf && /tmp/loupe-pdf/bin/pip install xhtml2pdf markdown
    /tmp/loupe-pdf/bin/python scripts/make_loupe_pdf.py in.md out.pdf
"""

import io
import re
import sys

import markdown
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa

# Loupe brand palette — mirrors build_deck.py and loupe-brand/brand/loupe-brand.css
OBSIDIAN = "#0B0C0F"   # dark ground
PAPER = "#FFFFFF"      # light ground
INK = "#16171C"        # body copy on light
INK_SOFT = "#C6C8CE"   # body copy on dark
RED_DEEP = "#B41624"   # accent on light ground
RED_SIGNAL = "#E33B4C" # accent on dark ground
LINE_LIGHT = "#D4D5DA"
LINE_DARK = "#33353C"
MUTED_LIGHT = "#7C7F87"
MUTED_DARK = "#8A8D95"

THEMES = {
    "light": dict(ground=PAPER, body=INK, head=OBSIDIAN, accent=RED_DEEP,
                  line=LINE_LIGHT, muted=MUTED_LIGHT),
    "dark": dict(ground=OBSIDIAN, body=INK_SOFT, head=PAPER, accent=RED_SIGNAL,
                 line=LINE_DARK, muted=MUTED_DARK),
}


def css(t, cover=False):
    return f"""
@page {{ size: A4; margin: {'24mm' if cover else '20mm'} 18mm 20mm 18mm; }}
body {{ font-family: Helvetica, sans-serif; font-size: 9.6pt; line-height: 1.52;
        color: {t['body']}; }}
p {{ margin: 0 0 7pt 0; }}
strong, b {{ color: {t['head']}; }}
em {{ color: {t['body']}; }}
h1.cover {{ font-size: 25pt; line-height: 1.14; color: {t['head']};
            margin: 0 0 7pt 0; font-weight: bold; }}
p.kicker {{ font-size: 8pt; letter-spacing: 1.7pt; color: {t['accent']};
            margin: 0 0 11pt 0; font-weight: bold; }}
div.rule {{ border-bottom: 2pt solid {t['accent']}; width: 72pt; margin: 0 0 15pt 0; }}
h2 {{ font-size: 15pt; color: {t['head']}; margin: 0 0 9pt 0; padding-bottom: 4pt;
      border-bottom: 0.7pt solid {t['line']}; font-weight: bold; }}
h3 {{ font-size: 11.2pt; color: {t['accent']}; margin: 15pt 0 5pt 0; font-weight: bold; }}
h4 {{ font-size: 9.8pt; color: {t['head']}; margin: 12pt 0 4pt 0; font-weight: bold; }}
ul, ol {{ margin: 0 0 8pt 13pt; }}
li {{ margin-bottom: 4.5pt; }}
hr {{ border: none; border-bottom: 0.7pt solid {t['line']}; margin: 15pt 0; }}
table {{ margin: 6pt 0 9pt 0; }}
td, th {{ padding: 3pt 6pt 3pt 0; font-size: 9pt; }}
th {{ color: {t['head']}; border-bottom: 0.7pt solid {t['line']}; text-align: left; }}
"""


def render(html_body, theme, cover_html=""):
    """Render one section to PDF bytes."""
    html = (f'<html><head><meta charset="utf-8"><style>{css(THEMES[theme], bool(cover_html))}'
            f"</style></head><body>{cover_html}{html_body}</body></html>")
    buf = io.BytesIO()
    status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    if status.err:
        raise RuntimeError(f"xhtml2pdf failed on a {theme} section")
    buf.seek(0)
    return buf


def background(theme, footer_left, page_no, total):
    """Draw the page ground and footer; content composites on top of this."""
    t = THEMES[theme]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFillColor(HexColor(t["ground"]))
    c.rect(0, 0, w, h, stroke=0, fill=1)
    # hairline above the footer, then the footer itself
    c.setStrokeColor(HexColor(t["line"]))
    c.setLineWidth(0.5)
    c.line(51, 40, w - 51, 40)
    c.setFont("Helvetica", 7.2)
    c.setFillColor(HexColor(t["muted"]))
    c.drawString(51, 30, footer_left)
    c.setFillColor(HexColor(t["accent"]))
    c.drawRightString(w - 51, 30, f"{page_no} / {total}")
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def split_sections(md_text):
    """Split markdown into (preamble, [(heading_line, body), ...]) on `## `."""
    parts = re.split(r"^(## .*)$", md_text, flags=re.MULTILINE)
    preamble = parts[0]
    sections = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    return preamble, sections


def main():
    argv = [a for a in sys.argv[1:] if a != "--alternate"]
    alternate = "--alternate" in sys.argv
    if len(argv) < 2:
        sys.exit(__doc__)
    src, out = argv[0], argv[1]
    md_text = open(src, encoding="utf-8").read()

    h1 = re.match(r"^# (.*?)\n", md_text)
    title = argv[2] if len(argv) > 2 else (h1.group(1) if h1 else "Loupe")
    md_text = re.sub(r"^# .*?\n", "", md_text, count=1)

    preamble, sections = split_sections(md_text)
    if not sections:
        sys.exit("no `## ` sections found — nothing to alternate")

    md_ext = ["tables", "sane_lists"]
    cover = (f'<p class="kicker">LOUPE &middot; MARKET FIT</p>'
             f'<h1 class="cover">{title}</h1><div class="rule"></div>'
             f"{markdown.markdown(preamble, extensions=md_ext)}")

    # First pass: render each section, note its theme and page count.
    rendered = []
    for i, (heading, body) in enumerate(sections):
        theme = "dark" if (alternate and i % 2) else "light"
        html = markdown.markdown(heading + "\n" + body, extensions=md_ext)
        buf = render(html, theme, cover_html=cover if i == 0 else "")
        reader = PdfReader(buf)
        rendered.append((theme, reader))
        cover = ""
    total = sum(len(r.pages) for _, r in rendered)

    # Second pass: composite each content page over its painted ground.
    writer = PdfWriter()
    footer = f"Loupe — {title}"
    n = 0
    for theme, reader in rendered:
        for page in reader.pages:
            n += 1
            ground = background(theme, footer, n, total)
            ground.merge_page(page)
            writer.add_page(ground)
    with open(out, "wb") as f:
        writer.write(f)
    themes = " ".join(f"{t[0]}{len(r.pages)}" for t, r in rendered)
    print(f"wrote {out} — {total} pages, {len(rendered)} sections ({themes})")


if __name__ == "__main__":
    main()
