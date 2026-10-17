"""Pages whose text is printed as vector outlines are read from the outlines; synthetic pages only."""
from pathlib import Path

import fitz
import pytest

from app.pipeline import pdf_extraction as pdf
from app.pipeline import vector_glyph_reading as G
from app.pipeline.statement_money_verification import verify_money_cells

FONT = Path('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf')
pytestmark = pytest.mark.skipif(not FONT.exists(), reason='Liberation Sans is needed to draw outline text')


def _font():
    from fontTools.ttLib import TTFont
    font = TTFont(str(FONT))
    return font.getBestCmap(), font.getGlyphSet(), font['head'].unitsPerEm


def _pen(shape, origin, scale):
    from fontTools.pens.basePen import BasePen

    class Pen(BasePen):
        def __init__(self):
            super().__init__(None)
            self.current = self.start = None

        def _point(self, p):
            return fitz.Point(origin[0] + p[0] * scale, origin[1] - p[1] * scale)

        def _moveTo(self, p):
            self.current = self.start = self._point(p)

        def _lineTo(self, p):
            point = self._point(p)
            shape.draw_line(self.current, point)
            self.current = point

        def _curveToOne(self, p1, p2, p3):
            end = self._point(p3)
            shape.draw_bezier(self.current, self._point(p1), self._point(p2), end)
            self.current = end

        def _closePath(self):
            if self.current != self.start:
                shape.draw_line(self.current, self.start)

    return Pen()


def draw_outlined(page, lines, size=9.0):
    """Print ``[(x, baseline, text)]`` as filled outlines, one path per line (no text layer)."""
    cmap, glyphs, units = _font()
    scale = size / units
    placed = []
    for x, y, text in lines:
        shape = page.new_shape()
        for character in text:
            glyph = glyphs[cmap[ord(character)]]
            if not character.isspace():
                glyph.draw(_pen(shape, (x, y), scale))
            placed.append((character, x, y))
            x += glyph.width * scale
        shape.finish(fill=(0, 0, 0), color=None, closePath=False)
        shape.commit()
    return placed


def _page(lines, size=9.0):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    placed = draw_outlined(page, lines, size)
    return doc, page, placed


def _word_boxes(page, text_lines):
    """OCR-like words ``(text, box)``: each printed word with the box of the outlines it covers."""
    glyphs = G.page_glyphs(page)
    words = []
    for x, y, text in text_lines:
        line = sorted((g for g in glyphs if g.y0 < y + 1 and g.y1 > y - 8), key=lambda g: g.x0)
        position = 0
        for word in text.split():
            under = line[position:position + len(word)]
            position += len(word)
            words.append((word, (min(g.x0 for g in under) - .3, min(g.y0 for g in under) - .3,
                                 max(g.x1 for g in under) + .3, max(g.y1 for g in under) + .3)))
    return words


LINES = [(40, 100 + 14 * i, f'0{i % 9 + 1}/ENE  SPEI ENVIADO  {i + 1},5{i % 7}9.{i % 4}5  25,{i}55.00')
         for i in range(12)]


def test_outline_text_page_is_classed_vector_text_and_a_blank_page_is_not():
    doc, page, _ = _page(LINES)
    assert page.get_text().strip() == ''
    assert pdf._ocr_detection_reason(page, '') == 'vector_text'
    blank = doc.new_page()
    assert pdf._ocr_detection_reason(blank, '') == 'no_native_text'


def test_each_printed_character_is_one_glyph_and_equal_characters_share_one_shape():
    doc, page, placed = _page(LINES)
    glyphs = G.page_glyphs(page)
    printed = [(c, x, y) for c, x, y in placed if not c.isspace()]
    assert len(glyphs) == len(printed)
    by_character = {}
    for character, x, y in printed:
        glyph, = [g for g in glyphs if x <= g.centre[0] < x + 4 and abs(g.y1 - y) < 3]
        by_character.setdefault(character, set()).add(glyph.shape)
    assert all(len(shapes) == 1 for shapes in by_character.values())
    assert len({next(iter(s)) for s in by_character.values()}) == len(by_character)


def test_an_i_is_one_character_and_a_word_with_a_colon_keeps_its_ocr_reading():
    lines = [(40, 100, 'Saldo: inicial 12.53')] + [(40, 114 + 14 * i, 'Saldo inicial 12.53') for i in range(3)]
    doc, page, _ = _page(lines)
    glyphs = G.page_glyphs(page)
    assert len(glyphs) == len('Saldo:inicial12.53') + 1 + 3 * len('Saldoinicial12.53')
    words = _word_boxes(page, [(40, 114 + 14 * i, 'Saldo inicial 12.53') for i in range(3)])
    labels = G.shape_labels(glyphs, words)
    x0, y0, x1, y1 = words[0][1]
    colon = ('Saldo:', (x0, y0 - 14, x1 + 3, y1 - 14))
    assert G.read_words(glyphs, labels, [colon]) == [None]


def test_the_page_majority_labels_a_shape_and_corrects_a_misread_figure():
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, LINES)
    misread = next(i for i, (text, _) in enumerate(words) if text == '1,509.05')
    words[misread] = ('1,909.05', words[misread][1])
    labels = G.shape_labels(glyphs, words)
    readings = G.read_words(glyphs, labels, words)
    assert readings[misread] == '1,509.05'
    assert all(reading in (None, text) for i, (reading, (text, _)) in enumerate(zip(readings, words)) if i != misread)


def test_letters_keep_their_ocr_reading_in_an_aligned_word():
    doc, page, _ = _page([(40, 100, 'Saldo 25.07')])
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, [(40, 100, 'Saldo 25.07')])
    shape_of = {g.x0: g.shape for g in glyphs}
    letter_l = sorted(shape_of.items())[2][1]
    labels = {g.shape: ('I' if g.shape == letter_l else '?', 9, 9) for g in glyphs}
    assert G.read_words(glyphs, labels, words[:1]) == ['Saldo']


def test_an_unaligned_word_only_loses_characters_that_are_not_letters_or_figures():
    lines = [(40, 100 + 14 * i, '18/DIC TERCEROS') for i in range(3)]
    doc, page, _ = _page(lines)
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, lines)
    labels = G.shape_labels(glyphs, words)
    noisy = ('18/DIC_', words[0][1])
    x0, y0, x1, y1 = words[1][1]
    cut = ('TERCEROS', (x0 + 7, y0, x1, y1))  # the box lost the first letter
    assert G.read_words(glyphs, labels, [noisy, cut]) == ['18/DIC', None]


def test_a_shape_the_ocr_reads_inconsistently_has_no_label():
    doc, page, _ = _page([(40, 100, '11 11 11 11')])
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, [(40, 100, '11 11 11 11')])
    words = [('ll' if i % 2 else text, box) for i, (text, box) in enumerate(words)]
    assert G.shape_labels(glyphs, words) == {}


def test_a_cell_is_read_with_its_marks_and_gaps():
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    labels = G.shape_labels(glyphs, _word_boxes(page, LINES))
    words = _word_boxes(page, LINES)
    box = next(b for t, b in words if t == '25,055.00')
    assert G.read_rect(glyphs, labels, box) == '25,055.00'
    first, second = words[1][1], words[2][1]
    assert G.read_rect(glyphs, labels, (first[0], first[1], second[2], second[3])) == 'SPEI ENVIADO'


class _Cell:
    def __init__(self, text, row, column, rect, page_number=1):
        self.text, self.row, self.column = text, row, column
        self.locator = type('L', (), {'to_json': lambda s: dict(kind='page_rectangle', page=page_number,
            rect=[round(v * 1000) for v in rect], page_size=[612000, 792000])})()


class _Table:
    def __init__(self, cells):
        self.geometry = type('Geo', (), {'cells': tuple(cells)})()
        self.chunk = ''


def test_the_money_check_confirms_a_cell_from_its_outlines_and_holds_a_contradicted_one(monkeypatch):
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    labels = G.shape_labels(glyphs, _word_boxes(page, LINES))
    words = _word_boxes(page, LINES)
    right = next(b for t, b in words if t == '25,055.00')
    wrong = next(b for t, b in words if t == '25,155.00')
    cells = [_Cell('25,055.00', 0, 0, right), _Cell('25,958.00', 1, 0, wrong)]
    cropped = []
    monkeypatch.setattr('app.pipeline.statement_money_verification.stacked_readings',
                        lambda page, rects, **kw: cropped.append(rects) or {})
    monkeypatch.setattr('app.pipeline.statement_money_verification._with_cells',
                        lambda page, tables, replacements, chunk: replacements)
    refined, (record,) = verify_money_cells(page, [_Table(cells)], deadline=0, language='eng',
        chunk=lambda grid, page: '', outline_reading=lambda rect: G.read_rect(glyphs, labels, rect))
    assert cropped == []
    assert [(c['status'], c['reason']) for c in record['cells']] == [
        ('confirmed', 'vector_outlines_confirm_page_reading'),
        ('contradicted', 'vector_outlines_contradict_page_reading')]
    assert record['decision'] == 'held' and '?' in refined[(0, 1, 0)]


def test_a_vector_text_statement_page_is_read_from_its_outlines_end_to_end(tmp_path):
    # Real rendering and Tesseract; the page has no text layer at all.
    lines = [(40, 60, 'ESTADO DE CUENTA'), (40, 80, 'FECHA  DESCRIPCION  CARGOS  ABONOS  SALDO')]
    lines += [(40, 100 + 14 * i, f'{i + 2:02d}/ENE  PAGO SERVICIO {i + 1}  {i + 1},{i % 9}5{i % 7}.{i % 9}5')
              for i in range(20)]
    doc, page, _ = _page(lines)
    path = tmp_path / 'outlines.pdf'
    doc.save(path)
    result = pdf._extract_pdf_sync(str(path))
    span = result.metadata['page_spans'][0]
    assert (span['extraction_method'], span['detection_reason']) == ('tesseract_ocr', 'vector_text')
    record = next(r for r in span['ocr_refinements'] if r.get('field') == 'vector_glyph_reading')
    assert record['method'] == G.METHOD and record['characters'] > 500 and record['labels']
    for i in range(20):
        assert f'{i + 1},{i % 9}5{i % 7}.{i % 9}5' in result.text


@pytest.mark.parametrize('text, reading, accepted', [
    ('18/DIC_', '18/DIC', True),       # a mark OCR added at the end
    ('O2/IMAY', '02/MAY', True),       # a letter OCR added inside, and the zero it read as O
    ('29/DIC.', '29/DIC', True),
    ('TERCEROS', 'ERCEROS', False),    # the box cut the printed first letter: never lose it
    ('SALDOS', 'SALDO', False),        # nor the last
    ('SPE', 'SPEI', False),            # outlines OCR did not cover are not added
    ('ABONO', 'ABONQ', False),         # a letter label never replaces an OCR letter
    ('1,2xx34.5O', '1,234.50', True),  # at most two dropped inside
    ('1,2xxx34.5O', '1,234.50', False),
])
def test_an_outline_reading_reconciles_with_the_ocr_text_only_up_to_what_ocr_adds(text, reading, accepted):
    assert G._reconciled(text, reading) is accepted


def test_a_word_over_blank_paper_is_inkless_and_a_word_over_ink_is_not():
    doc, page, _ = _page(LINES)
    page.draw_rect(fitz.Rect(400, 300, 500, 302), color=(0, 0, 0), width=1)
    drawings = page.get_drawings()
    glyphs, ink = G.page_glyphs(page, drawings), G.other_ink(page, drawings)
    x0, y0, x1, y1 = _word_boxes(page, LINES)[0][1]
    assert not G.inkless(glyphs, ink, (x0, y0, x1, y1))
    assert G.inkless(glyphs, ink, (300, 30, 320, 38))       # blank paper
    assert not G.inkless(glyphs, ink, (420, 296, 440, 304))  # over a rule


def test_shapes_snapped_to_a_device_grid_are_one_shape():
    # A producer that snaps outline points to a 600 dpi grid moves every point by up to 0.06 pt, differently for
    # each instance of a character (measured: instances 0.12 pt apart). Each point is moved here by a fixed
    # offset of up to 0.06 pt derived from its position; instances are still one shape.
    import hashlib
    doc, page, placed = _page(LINES)
    jittered = fitz.open().new_page(width=612, height=792)

    def moved(p):
        digest = hashlib.sha256(f'{p.x:.3f},{p.y:.3f}'.encode()).digest()
        return fitz.Point(p.x + (digest[0] / 255 - .5) * .12, p.y + (digest[1] / 255 - .5) * .12)

    for path in page.get_drawings():
        shape = jittered.new_shape()
        for item in path['items']:
            points = [moved(p) for p in item[1:] if hasattr(p, 'x')]
            (shape.draw_line if item[0] == 'l' else shape.draw_bezier)(*points)
        shape.finish(fill=(0, 0, 0), color=None, closePath=False)
        shape.commit()
    exact = {g.shape for g in G.page_glyphs(page)}
    assert len({g.shape for g in G.page_glyphs(jittered)}) == len(exact)
    G_tolerance = G.SHAPE_TOLERANCE
    try:
        G.SHAPE_TOLERANCE = 0.01
        assert len({g.shape for g in G.page_glyphs(jittered)}) > len(exact)  # the jitter is real
    finally:
        G.SHAPE_TOLERANCE = G_tolerance


def test_an_amount_ocr_skipped_is_added_from_its_outlines_and_nothing_else_is():
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, LINES)
    labels = G.shape_labels(glyphs, words)
    skipped = {'25,355.00', 'SPEI', '04/ENE'}
    kept = [(t, b) for t, b in words if not (t in skipped and b[1] < 145 and b[1] > 135)]
    assert len(kept) == len(words) - 3
    added = G.unread_words(glyphs, labels, kept)
    assert [t for t, _ in added] == ['25,355.00']  # never a date or a word
    box = next(b for t, b in words if t == '25,355.00')
    assert all(abs(a - b) < .5 for a, b in zip(added[0][1], box))


def test_an_unread_part_of_a_word_ocr_read_in_part_is_not_added():
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, LINES)
    labels = G.shape_labels(glyphs, words)
    index = next(i for i, (t, b) in enumerate(words) if t == '25,355.00')
    x0, y0, x1, y1 = words[index][1]
    partial = list(words)
    partial[index] = ('25,3', (x0, y0, x0 + (x1 - x0) * .4, y1))  # OCR read only the left of the amount
    assert G.unread_words(glyphs, labels, partial) == []


def _split_amount_page(gap_share):
    """LINES plus, at y=320, '7,355' and '.40' drawn ``gap_share`` of the digit height apart."""
    doc, page, _ = _page(LINES)
    draw_outlined(page, [(300, 320, '7,355')])
    left = max(g.x1 for g in G.page_glyphs(page) if g.y1 > 310)
    height = max(g.y1 - g.y0 for g in G.page_glyphs(page) if g.y1 > 310)
    probe = fitz.open().new_page()
    draw_outlined(probe, [(0, 320, '.40')])
    bearing = min(g.x0 for g in G.page_glyphs(probe))
    draw_outlined(page, [(left + gap_share * height - bearing, 320, '.40')])
    return page


def test_two_pieces_of_one_amount_split_by_a_wide_side_bearing_are_rejoined():
    # Measured: a narrow figure's side bearing leaves up to 0.49 of the height before a decimal point.
    for gap_share, expected in ((0.45, ['7,355.40']), (0.6, [])):
        page = _split_amount_page(gap_share)
        glyphs = G.page_glyphs(page)
        labels = G.shape_labels(glyphs, _word_boxes(page, LINES))
        assert [t for t, _ in G.unread_words(glyphs, labels, _word_boxes(page, LINES))] == expected, gap_share


SUMMARY_LINES = [(72, 100 + 14 * n, text) for n, text in enumerate([
    'SALDO FINAL DEL PERIODO ANTERIOR 1,234,567.89', 'TOTAL 2,345.67 345,678.90',
    'SALDO FINAL DEL PERIODO 891,234.66', 'Pagina 4 de 7 estado de cuenta',
    'Comisiones cobradas 500.00 Abonos 2,345.67', 'Fecha Folio Descripcion Deposito Retiro Saldo'])]


def _turned(source_page, rotate):
    """The same outlines placed on a new page turned by ``rotate`` degrees (sideways or upside down)."""
    target = fitz.open()
    page = target.new_page(width=792 if rotate in (90, 270) else 612, height=612 if rotate in (90, 270) else 792)
    page.show_pdf_page(page.rect, source_page.parent, source_page.number, rotate=rotate)
    return target, page


def test_outlines_drawn_left_to_right_read_upright_and_turned_ones_do_not():
    """Live: orientation detection turned upright vector pages 90 or 180 degrees and lost their closing balance."""
    doc, page, _ = _page(SUMMARY_LINES)
    votes = G.drawing_directions(page.get_drawings())
    assert votes[0] >= G.UPRIGHT_MIN_STEPS and votes[180] == 0
    assert G.drawn_upright(page.get_drawings())
    for rotate in (90, 180, 270):
        turned_doc, turned = _turned(page, rotate)
        assert not G.drawn_upright(turned.get_drawings()), rotate
    # Too little text to judge: orientation detection decides as before.
    small, small_page, _ = _page([(72, 100, 'TOTAL 5.00')])
    assert not G.drawn_upright(small_page.get_drawings())


def test_a_column_rule_read_after_every_amount_still_labels_and_is_dropped():
    """Live (Kapital): amounts set against a column rule were all read '1,234.56)', so no figure was labelled."""
    doc, page, _ = _page(LINES)
    glyphs = G.page_glyphs(page)
    words = [(text + ')' if G._AMOUNT.fullmatch(text) else text, box) for text, box in _word_boxes(page, LINES)]
    amounts = [i for i, (text, _) in enumerate(words) if text.endswith(')')]
    assert len(amounts) >= 10
    labels = G.shape_labels(glyphs, words)
    assert {labels[g.shape][0] for g in glyphs if g.shape in labels} >= set('0123456789,.')
    readings = G.read_words(glyphs, labels, words)
    assert [readings[i] for i in amounts] == [words[i][0][:-1] for i in amounts]
    # A word with as many characters as outlines is never trimmed.
    assert G._without_added_marks('(1.00)', [None] * 6) == '(1.00)'
    assert G._without_added_marks('1.00)', [None] * 4) == '1.00'
    assert G._without_added_marks('1.00))', [None] * 5) == '1.00))'


def _wide_one_date_page(gap_share=0.4):
    """LINES plus, at y=320, the date '11/05/2021' whose two 1s stand ``gap_share`` of the height apart."""
    doc, page, _ = _page(LINES)
    draw_outlined(page, [(300, 320, '1')])
    left = max(g.x1 for g in G.page_glyphs(page) if g.y1 > 310)
    height = max(g.y1 - g.y0 for g in G.page_glyphs(page) if g.y1 > 310)
    probe = fitz.open().new_page()
    draw_outlined(probe, [(0, 320, '1/05/2021')])
    bearing = min(g.x0 for g in G.page_glyphs(probe))
    draw_outlined(page, [(left + gap_share * height - bearing, 320, '1/05/2021')])
    return page


def test_a_figure_token_whose_ones_stand_a_space_wide_bearing_apart_is_reread_from_its_outlines():
    # Measured on a real statement: OCR read every '11/05/2021' of a date column as '41/05/2021'; the
    # first 1 is the page's 1 shape, but the gap between the two 1s is wider than a space share.
    page = _wide_one_date_page()
    glyphs = G.page_glyphs(page)
    date = sorted((g for g in glyphs if g.y1 > 310), key=lambda g: g.x0)
    assert G._has_space(date)
    box = (date[0].x0 - .3, date[0].y0 - .5, date[-1].x1 + .3, max(g.y1 for g in date) + .3)
    words = _word_boxes(page, LINES)
    labels = G.shape_labels(glyphs, words + [('41/05/2021', box)])
    assert labels[date[0].shape][0] == '1'
    assert G.read_words(glyphs, labels, [('41/05/2021', box)]) == ['11/05/2021']
    # A word with letters keeps its reading, and so does a token whose pieces stand an amount gap apart.
    assert G.read_words(glyphs, labels, [('A1/05/2021X', box)]) == [None]
    wide = _wide_one_date_page(0.6)
    glyphs = G.page_glyphs(wide)
    date = sorted((g for g in glyphs if g.y1 > 310), key=lambda g: g.x0)
    box = (date[0].x0 - .3, date[0].y0 - .5, date[-1].x1 + .3, max(g.y1 for g in date) + .3)
    assert G.read_words(glyphs, G.shape_labels(glyphs, _word_boxes(wide, LINES)), [('41/05/2021', box)]) == [None]


def test_a_printed_line_no_word_covers_is_returned_and_a_line_read_in_part_is_not():
    lines = LINES + [(40, 300, 'EXAMPLE N HOLDER JR'), (300, 314, 'OPENING BALANCE  1,234.56')]
    doc, page, _ = _page(lines)
    glyphs = G.page_glyphs(page)
    words = _word_boxes(page, lines)
    assert G.unread_lines(glyphs, words) == []
    missing = [(t, b) for t, b in words if not (b[1] > 290 and b[0] < 200)]
    found = G.unread_lines(glyphs, missing)
    assert len(found) == 1
    (x0, y0, x1, y1), run = found[0]
    assert len(run) == len('EXAMPLENHOLDERJR') and 35 < x0 < 45 and x1 < 200 and 290 < y0 < y1 < 302
    # One word of the line read: the rest of it is not offered as a line of its own.
    partial = [(t, b) for t, b in words if not (b[1] > 290 and b[0] < 200 and t != 'EXAMPLE')]
    assert G.unread_lines(glyphs, partial) == []


def test_a_line_page_ocr_skipped_is_read_from_its_own_crop_and_recorded():
    # Real rendering and Tesseract on the line's crop; the page OCR is simulated by dropping the line.
    import time
    from PIL import Image
    lines = LINES + [(40, 300, 'EXAMPLE N HOLDER JR')]
    doc, page, _ = _page(lines)
    dpi = 300
    pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
    scale = 72.0 / dpi
    words = [(t, b) for t, b in _word_boxes(page, lines) if b[1] < 290]
    data = dict(text=[t for t, _ in words], conf=[95] * len(words), block_num=[1] * len(words),
                par_num=[1] * len(words), line_num=list(range(len(words))), word_num=[1] * len(words),
                level=[5] * len(words), page_num=[1] * len(words),
                left=[round(b[0] / scale) for _, b in words], top=[round(b[1] / scale) for _, b in words],
                width=[round((b[2] - b[0]) / scale) for _, b in words],
                height=[round((b[3] - b[1]) / scale) for _, b in words])
    glyphs = G.page_glyphs(page)
    read, record = pdf._read_unread_lines(image, data, words, glyphs, dpi, time.monotonic() + 60)
    assert [r['text'] for r in record] == ['EXAMPLE N HOLDER JR']
    assert read['text'][len(words):] == ['EXAMPLE', 'N', 'HOLDER', 'JR']
    assert all(len(values) == len(read['text']) for values in read.values() if isinstance(values, list))
    # Through the outline reading: the line is recorded as read and no printed line is left unread.
    full, outlines = pdf._read_vector_outlines(page, data, dpi, image=image, deadline=time.monotonic() + 60)
    assert [r['text'] for r in outlines['lines_read']] == ['EXAMPLE N HOLDER JR']
    assert outlines['lines_checked'] is True and outlines['lines_unread'] == []
    # Without the image (no crop to read) the line stays unread and is recorded so.
    plain, outlines = pdf._read_vector_outlines(page, data, dpi)
    assert outlines['lines_read'] == [] and len(outlines['lines_unread']) == 1


def _tess(words):
    """Tesseract-shaped data for (text, block, (left, top, width, height)) words."""
    return dict(text=[t for t, _, _ in words], conf=[95] * len(words), block_num=[b for _, b, _ in words],
                par_num=[1] * len(words), line_num=[1] * len(words), word_num=list(range(1, len(words) + 1)),
                level=[5] * len(words), page_num=[1] * len(words),
                left=[r[0] for _, _, r in words], top=[r[1] for _, _, r in words],
                width=[r[2] for _, _, r in words], height=[r[3] for _, _, r in words], note='kept')


def test_the_skipped_line_layer_is_held_aside_and_put_back_whole():
    page = _tess([('MOVEMENTS', 1, (10, 10, 80, 10)), ('TOTAL', 1, (10, 200, 40, 10)),
                  # The layer: two lines read from their own crops.
                  ('SALDO', 7, (10, 300, 40, 10)), ('FINAL:', 7, (55, 300, 40, 10)),
                  ('JANE', 8, (10, 50, 40, 10)), ('EXAMPLE', 8, (55, 50, 60, 10))])
    base, layer = pdf._withhold_layer(page, [2, 3, 4, 5])
    assert base['text'] == ['MOVEMENTS', 'TOTAL'] and base['note'] == 'kept'
    assert all(len(v) == 2 for v in base.values() if isinstance(v, list))
    assert [row['text'] for row in layer] == ['SALDO', 'FINAL:', 'JANE', 'EXAMPLE']
    # No targeted re-read added anything: every layer line comes back, each its own block.
    restored, left_out = pdf._restore_layer(base, layer, base)
    assert restored['text'] == ['MOVEMENTS', 'TOTAL', 'SALDO', 'FINAL:', 'JANE', 'EXAMPLE'] and left_out == []
    assert all(len(v) == 6 for v in restored.values() if isinstance(v, list))
    assert len(set(restored['block_num'][2:4])) == 1 and restored['block_num'][2] != restored['block_num'][4]


def test_a_layer_line_never_replaces_what_a_targeted_reread_recovered():
    # v20 read the closing label alone (its amount refused); with the layer held aside the Santander
    # closing-strip re-read runs and recovers label and amount. The partial layer line is left out
    # whole; the holder line elsewhere on the page still comes back.
    page = _tess([('TOTAL', 1, (10, 200, 40, 10)),
                  ('SALDO', 7, (10, 300, 40, 10)), ('FINAL:', 7, (55, 300, 40, 10)),
                  ('JANE', 8, (10, 50, 40, 10)), ('EXAMPLE', 8, (55, 50, 60, 10))])
    base, layer = pdf._withhold_layer(page, [1, 2, 3, 4])
    reread = _tess([('TOTAL', 1, (10, 200, 40, 10)), ('SALDO FINAL DEL PERIODO:', 9, (10, 299, 150, 12)),
                    ('1,234.56', 9, (200, 299, 60, 12))])
    restored, left_out = pdf._restore_layer(reread, layer, base)
    assert restored['text'] == ['TOTAL', 'SALDO FINAL DEL PERIODO:', '1,234.56', 'JANE', 'EXAMPLE']
    assert left_out == [dict(text='SALDO FINAL:', rect=[10, 300, 95, 310])]


def test_the_layer_guard_lets_the_targeted_rereads_see_the_page_without_the_layer(monkeypatch):
    # Through _ocr_page: the re-reads are handed the page without the layer's words, and the
    # layer comes back afterwards where they added nothing.
    lines = LINES + [(40, 300, 'EXAMPLE N HOLDER JR')]
    doc, page, _ = _page(lines)
    seen = []
    import app.pipeline.financial_santander_ocr as santander
    def reread(page_, data, **kwargs):
        seen.append(list(data['text']))
        return data, []
    monkeypatch.setattr(santander, 'reread_santander_closing', reread)
    real = pdf._read_vector_outlines
    def outlines(page_, data, dpi, **kwargs):
        # The page OCR reads everything except the holder line, which the layer then reads.
        texts = data['text']
        keep = [i for i, t in enumerate(texts) if str(t).strip() not in ('EXAMPLE', 'N', 'HOLDER', 'JR')]
        data = {k: ([v[i] for i in keep] if isinstance(v, list) and len(v) == len(texts) else v) for k, v in data.items()}
        return real(page_, data, dpi, **kwargs)
    monkeypatch.setattr(pdf, '_read_vector_outlines', outlines)
    text, _, _, _, refinements = pdf._ocr_page(page, vector_text=True)
    assert seen and not any(word in ('HOLDER', 'JR') for word in seen[0])
    record = next(r for r in refinements if r.get('field') == 'vector_glyph_reading')
    assert [r['text'] for r in record['lines_read']] == ['EXAMPLE N HOLDER JR']
    assert pdf.LAYER_ROWS not in record and 'lines_left_to_rereads' not in record
    assert 'HOLDER' in text
