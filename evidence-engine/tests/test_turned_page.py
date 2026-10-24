"""Turning a page's drawings into the frame of the page read upright (no fonts needed)."""
import fitz
import pytest

from app.pipeline import vector_glyph_reading as G


@pytest.mark.parametrize('rotation, point', [(90, (792 - 20, 10)), (180, (612 - 10, 792 - 20)), (270, (20, 612 - 10))])
def test_a_point_is_turned_clockwise_into_the_upright_frame(rotation, point):
    assert G.turn_point(10, 20, rotation, 612, 792) == point


@pytest.mark.parametrize('rotation', [90, 180, 270])
def test_a_drawn_rectangle_and_line_turn_with_the_page(rotation):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(100, 200, 140, 260), color=(0, 0, 0), fill=(0, 0, 0))
    page.draw_line(fitz.Point(300, 400), fitz.Point(350, 400), color=(0, 0, 0))
    turned = G.TurnedPage(page, rotation)
    size = (792, 612) if rotation in (90, 270) else (612, 792)
    assert (turned.rect.width, turned.rect.height) == size and turned.rotation == 0
    drawings = turned.get_drawings()
    rect = G.turn_rect((100, 200, 140, 260), rotation, 612, 792)
    boxes = [tuple(round(v, 3) for v in d['rect']) for d in drawings]
    assert tuple(round(v, 3) for v in rect) in boxes
    for d in drawings:
        for item in d['items']:
            for value in item[1:]:
                if isinstance(value, fitz.Point):
                    assert 0 <= value.x <= size[0] and 0 <= value.y <= size[1]
