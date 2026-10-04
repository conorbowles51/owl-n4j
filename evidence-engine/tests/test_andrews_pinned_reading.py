"""Held Andrews money cells take the printed reading their agreed controls fix; synthetic corpus only."""
import copy
import json
from pathlib import Path

import fitz
import pytest
from app.pipeline import pdf_extraction as pdf
from app.pipeline import statement_money_verification as verification

ROOT = Path(__file__).resolve().parents[2] / 'backend'
CORPUS = ROOT / 'benchmarks' / 'statement_automation' / 'corpus'
FIXTURE = json.loads((ROOT / 'tests' / 'financial_andrews_pinned_reading_fixture.json').read_text())
P150 = 'andrews-v4-2022-04-scan-150dpi.pdf'
P100 = 'andrews-v4-2022-05-scan-100dpi.pdf'
COMBINED = 'andrews-v4-2022-08-scan-combined.pdf'


def held_tables(name):
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(
        table_source=item['table_source'], geometry_source=item['geometry_source'], table=item['table']))
        for item in copy.deepcopy(FIXTURE[name]['tables'])])


def held_record(name, **changes):
    cells = [dict(table_index=h['cell'][0], row_index=h['cell'][1], column_index=h['cell'][2],
                  original_text=h['page_reading'], status='contradicted', marked_text=h['marked_text'],
                  rect=h['rect'], observations=copy.deepcopy(h['observations']))
             for h in FIXTURE[name]['held']]
    return {**dict(method=verification.METHOD, page=1, decision='held', cells=cells), **changes}


def repair(name, record):
    tables = held_tables(name)
    with fitz.open() as doc:
        repaired, records = verification.repair_pinned_readings(doc.new_page(width=600, height=800), tables, record)
    return tables, repaired, records


@pytest.mark.parametrize('text, digits', [
    ('“61.27', '6127'), ('” 1,210.00', '121000'), ('~0.21', '021'), ('=98.70', '9870'),
    ('61.27', None), ('-61.27', None), ('“-61.27', None), ('““61.27', None), ('“61.2', None), ('x61.27', None),
])
def test_only_an_unsigned_amount_behind_one_sign_lookalike_is_a_garbled_money_cell(text, digits):
    assert verification.sign_garbled_money(text) == digits


def test_a_page_reading_with_an_unreadable_sign_is_never_confirmed():
    six = [dict(dpi=300 if i < 3 else 450, threshold=0, text='61.31') for i in range(6)]
    assert verification.classify('“61.31', six) == ('contradicted', '61.31')
    unreadable = [dict(o, text='“61.31') for o in six]
    assert verification.classify('“61.31', unreadable) == ('unconfirmed', None)


def test_printed_readings_offer_page_and_crop_readings_with_support_at_both_resolutions():
    readings = {tuple(h['cell']): verification._printed_readings(dict(original_text=h['page_reading'],
                rect=h['rect'], observations=h['observations'])) for h in FIXTURE[P100]['held']}
    assert readings == {(0, 15, 2): [('-61.28', 'page_reading'), ('61.28', 'crop_reading')],
                        (0, 17, 3): [('7,150.20', 'page_reading'), ('7,180.20', 'crop_reading')]}
    garbled = FIXTURE[COMBINED]['held'][0]
    assert verification._printed_readings(dict(original_text=garbled['page_reading'], rect=garbled['rect'],
        observations=garbled['observations'])) == [('61.31', 'crop_reading'), ('-61.31', 'crop_digits_signed_by_controls')]
    signed = FIXTURE[P150]['held'][0]
    assert verification._printed_readings(dict(original_text=signed['page_reading'], rect=signed['rect'],
        observations=signed['observations'])) == [('-61.27', 'crop_reading')]


@pytest.mark.parametrize('texts, expected', [
    # The page reading needs crop support at both resolutions.
    (['61.28'] * 3 + ['-61.28'] + ['61.28'] * 2, [('61.28', 'crop_reading')]),
    # Fewer than four agreeing crops, or crops split across one resolution, offer no crop reading.
    (['-61.28', '61.28', '61.28', '-61.28', '61.28', '61.88'], [('-61.28', 'page_reading')]),
    (['61.28'] * 3 + ['-61.28'] * 3, []),
    # A time-out (fewer than six readings) offers nothing.
    (['-61.28'] * 5, []),
])
def test_printed_readings_need_enough_agreement(texts, expected):
    observations = [dict(dpi=300 if i < 3 else 450, threshold=0, text=t) for i, t in enumerate(texts)]
    assert verification._printed_readings(dict(original_text='-61.28', rect=[1, 2, 3, 4],
                                               observations=observations)) == expected


def test_crop_digits_that_differ_from_a_garbled_page_reading_are_not_offered():
    observations = [dict(dpi=300 if i < 3 else 450, threshold=0, text='61.37') for i in range(6)]
    assert verification._printed_readings(dict(original_text='“61.31', rect=[1, 2, 3, 4],
                                               observations=observations)) == []


@pytest.mark.parametrize('name, expected', [
    (P150, {(15, 2): ('“61.27', '-61.27', 'crop_reading')}),
    (P100, {(15, 2): ('-61.28', '-61.28', 'page_reading'), (17, 3): ('7,150.20', '7,150.20', 'page_reading')}),
    (COMBINED, {(15, 2): ('“61.31', '-61.31', 'crop_digits_signed_by_controls')}),
])
def test_held_cells_take_the_reading_the_agreed_controls_pin_with_their_evidence(name, expected):
    tables, repaired, records = repair(name, held_record(name))
    changed = {(c.row, c.column): c.text for a, c in zip(tables[0].geometry.cells, repaired[0].geometry.cells)
               if a.text != c.text}
    assert changed == {key: value[1] for key, value in expected.items()}
    assert all(a.locator == b.locator for a, b in zip(tables[0].geometry.cells, repaired[0].geometry.cells))
    record, = records
    assert (record['method'], record['decision']) == ('statement_money_pinned_reading', 'repaired')
    assert record['controls']['reconciles']
    assert {(c['row_index'], c['column_index']): (c['page_reading'], c['text'], c['accepted_reading'])
            for c in record['cells']} == expected
    assert all(len(c['observations']) == 6 and c['pinned_by'] and c['held_text'] for c in record['cells'])


@pytest.mark.parametrize('changes, reason', [
    (dict(error='Tesseract timed out'), 'verification_incomplete'),
])
def test_incomplete_verification_is_declined(changes, reason):
    tables, repaired, records = repair(P100, held_record(P100, **changes))
    assert repaired is tables and [(r['decision'], r['reason']) for r in records] == [('declined', reason)]


def test_crop_majority_alone_is_declined_when_the_page_reading_lacks_support():
    record = held_record(P100)
    for observation in record['cells'][1]['observations']:
        observation['text'] = '7,180.20'
    tables, repaired, records = repair(P100, record)
    assert repaired is tables
    assert [(r['decision'], r['reason']) for r in records] == [
        ('declined', 'not_every_held_cell_is_pinned_by_agreed_controls')]


def test_unconfirmed_cell_without_any_printed_reading_is_declined():
    record = held_record(P100)
    record['cells'][0]['observations'] = record['cells'][0]['observations'][:4]
    tables, repaired, records = repair(P100, record)
    assert repaired is tables and records[0]['reason'] == 'held_cell_without_printed_reading'


@pytest.mark.parametrize('record', [None, dict(method=verification.METHOD, decision='all_confirmed', cells=[])])
def test_page_not_held_is_not_considered(record):
    tables, repaired, records = repair(P150, record)
    assert repaired is tables and records == []


def _records(result, method):
    return [r for span in result.metadata['page_spans'] for r in span.get('ocr_refinements') or []
            if r.get('method') == method]


@pytest.mark.parametrize('name, expected', [
    (P150, {'“61.27': '-61.27'}),
    (P100, {'-61.28': '-61.28', '7,150.20': '7,150.20'}),
    (COMBINED, {'“61.31': '-61.31'}),
])
def test_corpus_low_resolution_scans_are_repaired_to_the_printed_values(name, expected):
    # Real preparation, rasterisation and Tesseract on the synthetic corpus scans.
    result = pdf._extract_pdf_sync(str(CORPUS / name))
    records = _records(result, verification.PINNED_READING_METHOD)
    assert [r['decision'] for r in records] == ['repaired']
    assert {c['page_reading']: c['text'] for c in records[0]['cells']} == expected


def test_corpus_compensating_andrews_misreads_are_left_to_the_second_reader():
    # Amount, running balance and ending balance disputed together are never
    # pinned one at a time; the independent glyph reader still repairs them.
    result = pdf._extract_pdf_sync(str(CORPUS / 'andrews-2021-05-ocr-valid-but-wrong-consistent.pdf'))
    assert [(r['decision'], r['reason']) for r in _records(result, verification.PINNED_READING_METHOD)] == [
        ('declined', 'not_every_held_cell_is_pinned_by_agreed_controls')]
    assert [r['decision'] for r in _records(result, verification.SECOND_READER_METHOD)] == ['repaired']
