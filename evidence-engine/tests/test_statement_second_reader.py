"""The glyph second reader on synthetic scanned statements; real rasterisation and Tesseract.

The page image prints the true statement. The recognised text layer carries
compensating misreads (an amount, its running balance and the next amount),
so the page reading reconciles with every printed control exactly as the
printed values do. Every invented value here is synthetic.
"""
import copy
from pathlib import Path

import fitz
import pytest
from app.config import settings
from app.pipeline import pdf_extraction as pdf
from app.pipeline import statement_glyph_reader as glyphs
from app.pipeline import statement_money_verification as verification

FONT = 7
CORPUS = Path(__file__).resolve().parents[2] / 'backend' / 'benchmarks' / 'statement_automation' / 'corpus'
PRINTED = dict(amount_b='85.13', balance_b='11,663.87', amount_c='143.20')
MISREAD = dict(amount_b='88.13', balance_b='11,660.87', amount_c='140.20')


def _width(text):
    return fitz.get_text_length(text, fontname='helv', fontsize=FONT)


def lines(amount_b, balance_b, amount_c):
    return [
        [(40, 'left', 'Bank: Example Synthetic Bank')],
        [(40, 'left', 'Account Name: Example Holder LLC')],
        [(40, 'left', 'Account Number: 11112222')],
        [(40, 'left', 'Currency: USD')],
        [(40, 'left', 'Statement Period: March 1, 2023 - March 31, 2023')],
        [(40, 'left', 'Date'), (120, 'left', 'Description'), (380, 'right', 'Credit'),
         (460, 'right', 'Debit'), (560, 'right', 'Balance')],
        [(40, 'left', '2023-03-01'), (120, 'left', 'Opening Balance'), (560, 'right', '10,502.00')],
        [(40, 'left', '2023-03-02'), (120, 'left', 'Transfer in A'), (380, 'right', '1,247.00'),
         (560, 'right', '11,749.00')],
        [(40, 'left', '2023-03-08'), (120, 'left', 'Card purchase B'), (460, 'right', amount_b),
         (560, 'right', balance_b)],
        [(40, 'left', '2023-03-16'), (120, 'left', 'Utility C'), (460, 'right', amount_c),
         (560, 'right', '11,520.67')],
        [(40, 'left', '2023-03-29'), (120, 'left', 'Deposit D'), (380, 'right', '963.49'),
         (560, 'right', '12,484.16')],
        [(40, 'left', '2023-03-31'), (120, 'left', 'Closing Balance'), (560, 'right', '12,484.16')],
    ]


def _y(row):
    return 40 + row * 14


def tables(**reading):
    def locator(x0, y0, x1, y1):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x0, y0, x1, y1)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = []
    for row, line in enumerate(lines(**{**MISREAD, **reading})):
        for column, (x, align, text) in enumerate(line):
            left = x - _width(text) if align == 'right' else x
            values.append(dict(row=row, column=column, text=text,
                locator=locator(left, _y(row), left + _width(text), _y(row) + 9.6)))
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0, 0, 600, 800), values=values,
        unlocated_values=0)))])


def scanned_page(doc, **printed):
    """A raster image of the printed page, as a scan beneath a recognised text layer is."""
    with fitz.open() as source:
        drawn = source.new_page(width=600, height=800)
        for row, line in enumerate(lines(**{**PRINTED, **printed})):
            for x, align, text in line:
                left = x - _width(text) if align == 'right' else x
                drawn.insert_text((left, _y(row) + FONT), text, fontsize=FONT, fontname='helv')
        image = drawn.get_pixmap(dpi=200, colorspace=fitz.csGRAY, alpha=False).tobytes('png')
    page = doc.new_page(width=600, height=800)
    page.insert_image(page.rect, stream=image)
    return page


def verify(page, held_tables):
    return pdf._verify_recognised_money(page, held_tables, [t.chunk for t in held_tables],
        text_origin='recognised_glyphs', extraction_method='native')


def cell_text(result_tables, row, column):
    return next(c.text for c in result_tables[0].geometry.cells if (c.row, c.column) == (row, column))


def test_compensating_misreads_are_repaired_when_both_readers_agree_and_controls_reconcile():
    misread = tables()
    with fitz.open() as doc:
        _, verified, records = verify(scanned_page(doc), misread)
    held, *rest = records
    assert held['decision'] == 'held' and held['contradicted'] == 3
    assert [r['method'] for r in rest] == [verification.SECOND_READER_METHOD]
    repair = rest[0]
    assert repair['decision'] == 'repaired' and repair['controls']['reconciles']
    assert [(cell_text(verified, 8, 2), cell_text(verified, 8, 3), cell_text(verified, 9, 2))] == [
        ('85.13', '11,663.87', '143.20')]
    by_cell = {(c['row_index'], c['column_index']): c for c in repair['cells']}
    assert {k: (c['page_reading'], c['text']) for k, c in by_cell.items()} == {
        (8, 2): ('88.13', '85.13'), (8, 3): ('11,660.87', '11,663.87'), (9, 2): ('140.20', '143.20')}
    for cell in repair['cells']:
        assert '?' in cell['held_text'] and len(cell['observations']) == 6
        second = cell['second_reading']
        assert second['method'] == glyphs.METHOD and second['text'] == cell['text'].replace(' ', '')
        assert all(g['score'] >= glyphs.MIN_SCORE for g in second['glyphs'])
    # Every other cell keeps its reading and its locator.
    for before, after in zip(misread[0].geometry.cells, verified[0].geometry.cells):
        assert before.locator == after.locator
        if (before.row, before.column) not in by_cell:
            assert before.text == after.text


def test_value_the_printed_controls_contradict_stays_held():
    # The image prints 85.13 but its own balances only reconcile with 88.13. Both
    # readers see 85.13; the page's controls refuse it, so a person decides.
    misread = tables()
    with fitz.open() as doc:
        page = scanned_page(doc, amount_b='85.13', balance_b='11,660.87', amount_c='140.20')
        _, verified, records = verify(page, misread)
    assert records[0]['contradicted'] == 1
    assert records[-1]['method'] == verification.SECOND_READER_METHOD
    assert records[-1]['decision'] == 'declined' and records[-1]['reason'] == 'printed_controls_do_not_reconcile'
    assert '?' in cell_text(verified, 8, 2)


def test_switched_off_reader_leaves_the_page_held(monkeypatch):
    monkeypatch.setattr(settings, 'statement_glyph_second_reader', False)
    with fitz.open() as doc:
        _, verified, records = verify(scanned_page(doc), tables())
    assert [r['method'] for r in records] == [verification.METHOD]
    assert all('?' in cell_text(verified, *key) for key in ((8, 2), (8, 3), (9, 2)))


@pytest.fixture(scope='module')
def held_page():
    """A real held verification of the scanned page, and the held tables."""
    doc = fitz.open()
    page = scanned_page(doc)
    held_tables, [record] = verification.verify_money_cells(page, tables(), deadline=10 ** 12, language='eng')
    assert record['decision'] == 'held' and record['contradicted'] == 3
    yield page, held_tables, record
    doc.close()


def _repair(held_page, record):
    page, held_tables, _ = held_page
    return verification.repair_with_second_reader(page, held_tables, record, deadline=10 ** 12, language='eng')


def _with_observations(record, row, column, texts):
    changed = copy.deepcopy(record)
    cell = next(c for c in changed['cells'] if (c['row_index'], c['column_index']) == (row, column))
    for observation, text in zip(cell['observations'], texts):
        observation['text'] = text
    return changed


def test_crop_reading_the_glyph_reader_does_not_give_stays_held(held_page):
    # Tesseract (here forced) says 86.13; the glyphs on the page say 85.13.
    record = _with_observations(held_page[2], 8, 2, ['86.13'] * 6)
    result, [declined] = _repair(held_page, record)
    assert result is held_page[1]
    assert declined['decision'] == 'declined'
    assert declined['reason'] == 'second_reader_does_not_confirm_crop_reading'
    assert declined['glyph_text'] == '85.13'


@pytest.mark.parametrize('texts, reason', [
    (['85.13'] * 5 + ['88.13'], 'not_every_held_cell_is_contradicted'),   # a crop reading supports the page
    (['85.13'] * 3 + ['86.13'] * 3, 'not_every_held_cell_is_contradicted'),  # no majority
    (['85.13'] * 3 + ['8513'] * 3, 'not_every_held_cell_is_contradicted'),   # one resolution only
])
def test_anything_short_of_a_clear_contradiction_stays_held(held_page, texts, reason):
    record = _with_observations(held_page[2], 8, 2, texts)
    result, [declined] = _repair(held_page, record)
    assert result is held_page[1] and declined['reason'] == reason


def test_one_dissenting_crop_reading_is_tolerated_when_the_glyph_reader_agrees(held_page):
    record = _with_observations(held_page[2], 8, 2, ['85.13'] * 5 + ['89.13'])
    result, [repair] = _repair(held_page, record)
    assert repair['decision'] == 'repaired' and cell_text(result, 8, 2) == '85.13'


def test_unconfirmed_cell_or_failed_verification_is_not_considered(held_page):
    record = copy.deepcopy(held_page[2])
    record['cells'][-1]['status'] = 'unconfirmed'
    assert _repair(held_page, record)[1][0]['reason'] == 'not_every_held_cell_is_contradicted'
    assert _repair(held_page, {**held_page[2], 'error': 'Tesseract timed out'})[1][0]['reason'] == \
        'not_every_held_cell_is_contradicted'
    assert _repair(held_page, {**held_page[2], 'decision': 'all_confirmed'}) == (held_page[1], [])
    assert _repair(held_page, None) == (held_page[1], [])


def test_page_without_templates_for_a_disputed_character_stays_held(held_page, monkeypatch):
    # Only the money cells without an 8 may serve as templates: 8 versus 5 cannot be compared.
    record = copy.deepcopy(held_page[2])
    for cell in record['cells']:
        if cell['status'] == 'confirmed' and '8' in cell['original_text']:
            cell['rect'] = None
    monkeypatch.setattr(verification, '_TEMPLATE_TEXT', verification.re.compile(r'(?!)'))
    result, [declined] = _repair(held_page, record)
    assert declined['reason'] == 'no_templates_for_disputed_characters' and '8' in declined['missing']
    assert result is held_page[1]


def _cells(page, record):
    return [((c['table_index'], c['row_index'], c['column_index']), verification._darkness(page, c['rect'], 0),
             c['original_text']) for c in record['cells'] if c['status'] == 'confirmed']


def test_a_glyph_whose_class_has_no_template_is_not_read_as_the_nearest_class(held_page):
    page, _, record = held_page
    cells = _cells(page, record)
    reader = glyphs.PageGlyphs([c for c in cells if '6' not in c[2]])
    assert '6' not in reader.classes
    target = next(c for c in cells if c[2] == '11,520.67')
    result = reader.read(target[1], 9)
    assert result['text'] is None and result['reason'] == 'glyph_not_distinguished'
    # Every character of 1,247.00 has templates from two other cells: it is read exactly.
    transfer = next(c for c in cells if c[2] == '1,247.00')
    full = glyphs.PageGlyphs([c for c in cells if c is not transfer])
    assert full.read(transfer[1], 8)['text'] == '1,247.00'
    # Holding out the closing balance leaves one other cell with an 8: that glyph is not read.
    closing = next(c for c in cells if c[0][1] == 11)
    without = glyphs.PageGlyphs([c for c in cells if c is not closing])
    assert '8' not in without.classes and without.read(closing[1], 9)['text'] is None


def test_a_mislabelled_template_makes_the_page_untrusted(held_page):
    page, _, record = held_page
    cells = _cells(page, record)
    wrong = [(key, darkness, '10,502.00' if text == '12,484.16' else text) for key, darkness, text in cells]
    reader = glyphs.PageGlyphs(wrong)
    assert reader.inconsistent
    assert reader.read(cells[0][1], len(cells[0][2]))['reason'] == 'templates_inconsistent'


def test_cell_whose_ink_does_not_separate_into_its_characters_is_not_read(held_page):
    page, _, record = held_page
    cells = _cells(page, record)
    reader = glyphs.PageGlyphs(cells[1:])
    assert reader.read(cells[0][1], len(cells[0][2]) + 1)['reason'] == 'glyphs_not_separable'


@pytest.mark.parametrize('name, expected', [
    ('merrick-2021-08-ocr-valid-but-wrong-cancelling.pdf', {'18.48': '15.48', '100.34': '103.34'}),
    ('credit-one-cycle-7-ocr_valid_but_wrong_amounts_cancelling_7_1_0_6.pdf', {'11.11': '17.11', '36.62': '30.62'}),
])
def test_corpus_compensating_card_misreads_are_repaired_to_the_printed_values(name, expected):
    result = pdf._extract_pdf_sync(str(CORPUS / name))
    records = [r for span in result.metadata['page_spans'] for r in span.get('ocr_refinements') or []
               if r.get('method') == verification.SECOND_READER_METHOD]
    assert [r['decision'] for r in records] == ['repaired']
    assert {c['page_reading']: c['text'] for c in records[0]['cells']} == expected


def test_corpus_card_page_that_never_prints_the_needed_digits_stays_held():
    # Credit One cycle 6 prints 18.79; no other digit-only text on the page shows a 7 or a 9.
    result = pdf._extract_pdf_sync(str(CORPUS / 'credit-one-cycle-6-ocr-valid-but-wrong-cancelling.pdf'))
    records = [r for span in result.metadata['page_spans'] for r in span.get('ocr_refinements') or []
               if r.get('method') == verification.SECOND_READER_METHOD]
    assert [r['decision'] for r in records] == ['declined']
    assert records[0]['reason'] == 'second_reader_does_not_confirm_crop_reading'
    assert '7' not in records[0]['reader']['classes'] and '9' not in records[0]['reader']['classes']
