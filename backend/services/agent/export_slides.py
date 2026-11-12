"""PDF companion drawn from the generated PPTX's exact slide composition.

The product generates text, rectangles, raster exhibits and tables. Unsupported
shapes fail explicitly, rather than disappearing from the companion export.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache


@lru_cache(maxsize=2)
def font_bytes(bold=False):
    from services.agent.export_documents import ASSETS
    path=ASSETS / 'fonts/loupe/IBMPlexSans.ttf'
    if not bold:return path.read_bytes()
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    font=TTFont(path)
    if 'fvar' in font:font=instantiateVariableFont(font,{'wght':700})
    out=io.BytesIO();font.save(out);font.close();return out.getvalue()


@lru_cache(maxsize=2)
def body_font(bold=False):
    import pymupdf
    return pymupdf.Font(fontbuffer=font_bytes(bold))


@lru_cache(maxsize=8192)
def _advance(character):
    return body_font().glyph_advance(ord(character))


def wrap_text(value, width, size):
    """Use the bundled font's measured widths for both Office and PDF line breaks."""
    lines = []
    for paragraph in str(value).split("\n"):
        line = ""
        line_width = 0
        for token in re.findall(r"\S+\s*", paragraph):
            if line and line_width + sum(_advance(c) for c in token.rstrip()) * size > width:
                lines.append(line.rstrip())
                line = ""
                line_width = 0
            for character in token:
                advance = _advance(character) * size
                if line and line_width + advance > width:
                    lines.append(line.rstrip())
                    line = ""
                    line_width = 0
                line += character
                line_width += advance
        lines.append(line.rstrip())
    return lines or [""]


def presentation_pdf(pptx_content):
    import pymupdf
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    presentation = Presentation(io.BytesIO(pptx_content))
    scale = 914400 / 72
    width, height = presentation.slide_width / scale, presentation.slide_height / scale
    pdf = pymupdf.open()

    def color(fill, default=(1, 1, 1)):
        try:
            rgb = fill.fore_color.rgb
            return tuple(v / 255 for v in rgb) if rgb else default
        except (AttributeError, TypeError):
            return default

    def text_frame(page, frame, bounds):
        left, top, right, bottom = bounds
        left += frame.margin_left / scale
        right -= frame.margin_right / scale
        top += frame.margin_top / scale
        bottom -= frame.margin_bottom / scale
        y = top
        for paragraph in frame.paragraphs:
            size = paragraph.font.size.pt if paragraph.font.size else 20
            bold=bool(paragraph.font.bold)
            font = body_font(bold)
            leading = size * 1.2
            lines = wrap_text(paragraph.text, right - left, size)
            try:
                ink = tuple(v / 255 for v in paragraph.font.color.rgb)
            except (AttributeError, TypeError):
                ink = (0.125, 0.129, 0.149)
            for line in lines:
                baseline = y + size * font.ascender
                if baseline - size * font.descender > bottom + 1:
                    raise ValueError("A slide text box would overflow; revise its content or split it across slides.")
                page.insert_text((left, baseline), line, fontname="LoupeBold" if bold else "Loupe", fontsize=size, color=ink)
                y += leading
            if paragraph.space_after:
                y += paragraph.space_after.pt

    for slide in presentation.slides:
        page = pdf.new_page(width=width, height=height)
        page.insert_font(fontname="Loupe", fontbuffer=font_bytes())
        page.insert_font(fontname="LoupeBold", fontbuffer=font_bytes(True))
        page.draw_rect(page.rect, fill=color(slide.background.fill), color=None)
        for shape in slide.shapes:
            bounds = pymupdf.Rect(shape.left / scale, shape.top / scale,
                                  (shape.left + shape.width) / scale, (shape.top + shape.height) / scale)
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                page.insert_image(bounds, stream=shape.image.blob, keep_proportion=False)
            elif shape.has_table:
                table = shape.table
                top = bounds.y0
                for ri, row in enumerate(table.rows):
                    left = bounds.x0
                    for ci, column in enumerate(table.columns):
                        cell = table.cell(ri, ci)
                        rect = pymupdf.Rect(left, top, left + column.width / scale, top + row.height / scale)
                        page.draw_rect(rect, fill=color(cell.fill), color=(.85, .86, .88), width=.4)
                        # Cell text frames expose margins through the cell, unlike shape frames.
                        proxy = type("CellFrame", (), {"paragraphs": cell.text_frame.paragraphs,
                            "margin_left": cell.margin_left, "margin_right": cell.margin_right,
                            "margin_top": cell.margin_top, "margin_bottom": cell.margin_bottom})()
                        text_frame(page, proxy, rect)
                        left = rect.x1
                    top += row.height / scale
            elif shape.has_text_frame:
                if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                    page.draw_rect(bounds, fill=color(shape.fill), color=None)
                if shape.text:
                    text_frame(page, shape.text_frame, bounds)
            else:
                raise ValueError("A generated presentation contains an unsupported PDF shape; no partial export was returned.")
    pdf.set_metadata({"title": presentation.core_properties.title or "Loupe presentation", "producer": "Loupe slide renderer"})
    content = pdf.tobytes(garbage=4, deflate=True)
    pdf.close()
    return content
