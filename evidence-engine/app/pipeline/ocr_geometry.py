"""Project measured OCR word rectangles back onto the displayed PDF page."""
from __future__ import annotations
import math


def project_ocr_words(data, *, rotation, image_width, image_height, page_width, page_height):
    """Undo OCR orientation, then scale pixels to PDF points; never guess boxes."""
    if type(rotation) is not int or rotation not in (0, 90, 180, 270):
        raise ValueError('Unsupported OCR orientation')
    dimensions = (image_width, image_height, page_width, page_height)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in dimensions):
        raise ValueError('Invalid OCR page dimensions')
    texts = data.get('text')
    if not isinstance(texts, list) or len(texts) > 100000:
        raise ValueError('OCR words are unavailable or exceed the geometry limit')
    fields = ('left', 'top', 'width', 'height')
    if any(not isinstance(data.get(k), list) or len(data[k]) != len(texts) for k in fields):
        raise ValueError('OCR word rectangles are unavailable')
    oriented_width, oriented_height = ((image_height, image_width) if rotation in (90, 270) else (image_width, image_height))
    def original(x, y):
        if rotation == 90:
            return y, image_height - x
        if rotation == 180:
            return image_width - x, image_height - y
        if rotation == 270:
            return image_width - y, x
        return x, y
    words = []
    for i, text in enumerate(texts):
        if not isinstance(text, str):
            raise ValueError('Invalid OCR word text')
        if not text.strip():
            continue
        x, y, width, height = (data[k][i] for k in fields)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x,y,width,height)):
            raise ValueError('Invalid OCR rectangle')
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > oriented_width or y + height > oriented_height:
            raise ValueError('OCR rectangle is outside the rendered page')
        corners = [original(a,b) for a in (x,x+width) for b in (y,y+height)]
        xs, ys = zip(*corners)
        words.append((min(xs)*page_width/image_width, min(ys)*page_height/image_height,
                      max(xs)*page_width/image_width, max(ys)*page_height/image_height, text.strip()))
    return words
