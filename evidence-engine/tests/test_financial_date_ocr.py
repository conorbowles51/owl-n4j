from copy import deepcopy
import time
from types import SimpleNamespace

import fitz
import pytest

from app.pipeline import financial_date_ocr as retry
from app.pipeline import pdf_extraction
from app.pipeline.ocr_geometry import project_ocr_words
from app.services.evidence_document_text import build_canonical_document_text


def fixture(extra=False):
    rows = [
        [(90, 'MERRICK BANK', 100)],
        [(90, 'Transactions, Payments and Credits', 240)],
        [(90, 'Trans Date', 35), (250, 'Item Description', 90), (480, 'Amount', 30)],
        [(90, 'OG/04', 25), (250, 'EXAMPLE SHOP', 110), (480, '10.00', 30)],
        [(90, '06/05', 25), (250, 'OTHER SHOP', 110), (480, '20.00', 30)],
    ]
    if extra:
        rows.append([(90, 'OG/04', 25), (250, 'THIRD SHOP', 110), (480, '30.00', 30)])
    data = dict(text=[''], left=[0], top=[0], width=[0], height=[0], conf=[-1])
    for row, cells in enumerate(rows):
        for x, text, width in cells:
            for key, value in dict(text=text, left=x, top=40+row*20, width=width, height=8, conf=80).items():
                data[key].append(value)
    return data


class Reader:
    def read_positioned_ocr_words(self, words, **kwargs):
        rows = {}
        for x0, y0, x1, y1, text in words:
            row = rows.setdefault(y0, [])
            row.append(dict(row=len(rows)-1, column=len(row), text=text,
                locator=dict(rect=[round(v*1000) for v in (x0,y0,x1,y1)])))
        values = [cell for cells in rows.values() for cell in cells]
        return [SimpleNamespace(to_json=lambda: dict(table=dict(values=values)))]


def andrews_fixture():
    data = dict(text=[''], left=[0], top=[0], width=[0], height=[0], conf=[-1])
    for text, x, y, width in [('Account Statement',430,22,128), ('Andrews',40,34,70),
                             ('123456789',300,65,40), ('LI/GL/20',300,94,33), ('11/30/20',345,94,33),
                             ('LI/GL/20',20,260,33)]:
        for key, value in dict(text=text,left=x,top=y,width=width,height=7,conf=80).items():
            data[key].append(value)
    return data


def test_andrews_period_reread_preserves_readable_date_and_unrelated_identical_text(monkeypatch):
    data = andrews_fixture(); before = deepcopy(data)
    result, records, calls = run(data, monkeypatch, iter(['11/01/20','11/01/20']))
    assert result['text'][4] == '11/01/20'
    assert result['text'][5:] == ['11/30/20','LI/GL/20']
    assert data == before and len(records) == 1 and len(calls) == 2
    assert records[0]['original_text'] == 'LI/GL/20'
    assert records[0]['dpi'] == 600 and '--dpi 600' in calls[0]['config']
    data['text'][4] = '11/01/20'; data['text'][5] = 'II/3O/20'
    result, records, _ = run(data, monkeypatch, iter(['11/30/20','11/30/20']))
    assert result['text'][5] == '11/30/20' and len(records) == 1
    data['text'][5] = '11/30/20'
    result, records, calls = run(data, monkeypatch, iter([]))
    assert result is data and not records and not calls


@pytest.mark.parametrize('damage', ['bank','title','account','body','overlap','baseline','both_dates','other_period'])
def test_andrews_header_reread_requires_one_measured_unambiguous_period(monkeypatch, damage):
    data = andrews_fixture()
    if damage == 'bank': data['text'][2] = 'Different Bank'
    elif damage == 'title': data['text'][1] = 'Other report'
    elif damage == 'account': data['text'][3] = '1234'
    elif damage == 'body': data['top'][4] = 300
    elif damage == 'overlap': data['left'][5] = 310
    elif damage == 'baseline': data['top'][5] = 110
    elif damage == 'both_dates': data['text'][5] = 'II/3O/20'
    elif damage == 'other_period':
        for i in (4,5):
            for key in data: data[key].append(data[key][i] + 30 if key == 'top' else data[key][i])
    result, records, calls = run(data, monkeypatch, iter(['11/01/20','11/01/20']))
    assert result is data and not records and not calls


@pytest.mark.parametrize('text', ['11/01', '12/01/20', '08/01/20', '11/01/21'])
def test_andrews_retry_cannot_return_a_partial_inverted_or_overlong_period(monkeypatch, text):
    data = andrews_fixture()
    result, records, calls = run(data, monkeypatch, iter([text,text]))
    assert result is data and not records


def run(data, monkeypatch, replies, *, deadline=None, reader=None):
    calls = []
    def read(image, **kwargs):
        calls.append(kwargs)
        value = next(replies, '')
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(retry.pytesseract, 'image_to_string', read)
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        result, records = retry.reread_financial_dates(page, data,
            rotation=0, image_width=612, image_height=792,
            reader=reader or Reader(), deadline=deadline or time.monotonic()+20, language='eng')
    return result, records, calls


def test_matching_visual_reads_change_only_unclear_date_and_retain_earlier_text(monkeypatch):
    data = fixture(); before = deepcopy(data)
    result, records, calls = run(data, monkeypatch, iter(['06/04', '06/04']))
    assert data == before and result is not data
    assert result['text'][6] == '06/04'
    assert result['text'][9] == '06/05'  # An already readable date is not retried.
    assert all(result[key] == data[key] for key in data if key != 'text')
    assert records == [dict(method='tesseract_date_crop_consensus', page=1,
        rect=[90000,100000,115000,108000], original_text='OG/04', text='06/04',
        dpi=720, segmentation_modes=[7,13], character_set='0123456789/',
        observations=[dict(dpi=720,segmentation_mode=mode,text='06/04') for mode in (7,13)])]
    assert len(calls) == 2 and all(call['timeout'] <= 10 for call in calls)
    assert '--psm 7' in calls[0]['config'] and '--psm 13' in calls[1]['config']


@pytest.mark.parametrize('replies', [
    ['06/04', '06/05'], ['06/04', 'O6/04'], ['06/04', '06/04,'],
    ['13/04', '13/04'], ['02/30', '02/30'], [RuntimeError('Tesseract timeout')],
])
def test_disagreement_invalid_calendar_and_failed_retry_retain_original(monkeypatch, replies):
    data = fixture()
    result, records, _ = run(data, monkeypatch, iter(replies))
    assert result is data and not records


@pytest.mark.parametrize('damage', ['bank', 'header', 'date_column', 'amount_column', 'baseline'])
def test_uncertain_context_is_not_reread(monkeypatch, damage):
    data = fixture()
    if damage == 'bank': data['text'][1] = 'ANOTHER BANK'
    if damage == 'header': data['text'][3] = 'Unclear heading'
    if damage == 'date_column': data['left'][6] = 150
    if damage == 'amount_column': data['left'][8] = 350
    if damage == 'baseline': data['top'][8] += 10
    result, records, calls = run(data, monkeypatch, iter([]))
    assert result is data and not records and not calls


def test_repeated_bad_text_is_changed_by_location_not_global_replacement(monkeypatch):
    data = fixture(extra=True)
    result, records, _ = run(data, monkeypatch, iter(['06/04','06/04','06/06','06/06']))
    assert result['text'][6] == '06/04' and result['text'][12] == '06/06'
    assert len(records) == 2 and records[0]['rect'] != records[1]['rect']
    text, _ = pdf_extraction._text_and_confidence_from_tesseract(result)
    assert '06/04' in text and '06/06' in text and 'OG/04' not in text
    words = project_ocr_words(result, rotation=0, image_width=612, image_height=792, page_width=612, page_height=792)
    assert words[5][4] == '06/04' and words[11][4] == '06/06'


def test_second_resolution_can_confirm_a_reading_but_cannot_outvote_a_conflicting_date(monkeypatch):
    data = fixture()
    result, records, calls = run(data, monkeypatch, iter(['06/04','604','06/04','604']))
    assert result['text'][6] == '06/04'
    assert [o['dpi'] for o in records[0]['observations']] == [720,720,600,600]
    assert '--dpi 600' in calls[2]['config']
    result, records, calls = run(data, monkeypatch, iter(['06/04','604','06/05','06/04']))
    assert result is data and not records and len(calls) == 4
    result, records, calls = run(data, monkeypatch, iter(['06/04','06/05','06/04','06/04']))
    assert result is data and not records and len(calls) == 2
    # A real scan exposed this failure: raw-line mode repeated 10/14 while
    # the primary line mode only read fragments of the printed 10/11.
    result, records, calls = run(data, monkeypatch, iter(['11','10/14','14','10/14']))
    assert result is data and not records and len(calls) == 2


def test_date_beside_separate_credit_marker_is_read_without_changing_amount_or_sign(monkeypatch):
    data = fixture()
    for key, value in dict(text='-',left=516,top=104,width=3,height=2,conf=80).items():
        data[key].append(value)
    result, records, _ = run(data, monkeypatch, iter(['06/04','06/04']))
    assert result['text'][6] == '06/04' and len(records) == 1
    assert result['text'][8] == '10.00' and result['text'][-1] == '-'


def test_trimmed_line_box_matches_only_the_same_word_at_its_original_location(monkeypatch):
    class TrimmedReader(Reader):
        def read_positioned_ocr_words(self, words, **kwargs):
            tables = super().read_positioned_ocr_words(words, **kwargs)
            values = tables[0].to_json()['table']['values']
            for value in values:
                if value['text'] == 'OG/04':
                    value['locator']['rect'][3] -= 500
            return tables
    result, records, _ = run(fixture(), monkeypatch, iter(['06/04','06/04']), reader=TrimmedReader())
    assert result['text'][6] == '06/04' and len(records) == 1
    assert records[0]['rect'] == [90000,100000,115000,108000]


def test_full_date_requires_explicit_statement_label_and_valid_calendar(monkeypatch):
    for label, accepted in [('Billing Cycle Closing Date', True), ('Payment due', False)]:
        data = fixture()
        data['text'][6] = '06/04'
        for text, x, width in [(label, 250, 140), ('O6/25/21', 480, 40)]:
            for key, value in dict(text=text,left=x,top=160,width=width,height=8,conf=60).items():
                data[key].append(value)
        result, records, calls = run(data, monkeypatch, iter(['06/25/21','06/25/21']))
        assert bool(records) == accepted
        assert result['text'][-1] == ('06/25/21' if accepted else 'O6/25/21')
        if not accepted: assert not calls
    assert not retry._date_text('02/29/21')
    assert retry._date_text('02/29/20')


def test_expired_budget_preserves_successful_page_reading(monkeypatch):
    data = fixture()
    result, records, calls = run(data, monkeypatch, iter([]), deadline=time.monotonic()-1)
    assert result is data and not records and not calls


def test_page_text_geometry_and_saved_provenance_use_the_same_rereading(monkeypatch):
    data = fixture()
    monkeypatch.setattr(pdf_extraction.pytesseract, 'image_to_osd', lambda *a, **kw: dict(rotate=0,orientation_conf=20))
    monkeypatch.setattr(pdf_extraction.pytesseract, 'image_to_data', lambda *a, **kw: data)
    monkeypatch.setattr(pdf_extraction.pytesseract, 'image_to_string', lambda *a, **kw: '06/04')
    monkeypatch.setattr(pdf_extraction, '_load_table_reader', lambda: Reader())
    with fitz.open() as doc:
        page = doc.new_page(width=612,height=792)
        text, confidence, dpi, words, comparisons = pdf_extraction._ocr_page(page)
    assert '06/04' in text and 'OG/04' not in text
    assert any(w[4] == '06/04' for w in words)
    assert comparisons[0]['original_text'] == 'OG/04'
    result = pdf_extraction._PageResult(page_number=1,text=text,extraction_method='tesseract_ocr',
        text_origin='recognised_glyphs',ocr_refinements=comparisons)
    canonical = build_canonical_document_text(SimpleNamespace(text=text,tables=[],
        metadata=dict(file_type='pdf',page_spans=[pdf_extraction._page_span(result,0)])))
    assert canonical.source_locations[0]['ocr_refinements'] == comparisons
    assert canonical.source_locations[0]['text_origin'] == 'recognised_glyphs'


def repeated_heading_fixture():
    data=dict(text=[''],left=[0],top=[0],width=[0],height=[0],conf=[-1])
    for text,x,y,width in [
        ('Statement Date: 09/24/21',420,15,100), ('MERRICK BANK',40,50,100),
        ('Billing Cycle Closing Date',200,230,115), ('09/24/24',340,230,50),
        ('Transactions, Payments and Credits',90,280,250), ('2021 Totals Year-to-Date',90,600,200),
        ('09/24/24',90,630,50),
    ]:
        for key,value in dict(text=text,left=x,top=y,width=width,height=8,conf=80).items():data[key].append(value)
    return data


def test_repeated_closing_date_requires_two_visual_sizes_and_two_printed_anchors(monkeypatch):
    data=repeated_heading_fixture();before=deepcopy(data)
    result,records,calls=run(data,monkeypatch,iter(['/24/21','09/24/21','9/24/21','09/24/21']))
    assert data==before and result['text'][4]=='09/24/21' and len(calls)==4
    assert result['text'][:4]+result['text'][5:]==data['text'][:4]+data['text'][5:]
    assert records[0]['original_text']=='09/24/24'
    assert records[0]['agreement_with']==dict(statement_date='09/24/21',statement_date_rect=[420000,15000,520000,23000],year_to_date_year=2021)


@pytest.mark.parametrize('replies',[
    ['09/24/21']*3+['09/24/24'],
    ['09/24/21']*3+['9/24/24'],
    ['09/24/21']*2+['24/21']*2,
    ['24/21','09/24/21','24/21','24/21'],
    ['09/23/21']*4,
    ['09/24']*4,
    ['09/24/21',RuntimeError('timeout')],
])
def test_repeated_closing_date_cannot_outvote_a_complete_date_or_replace_missing_visual_evidence(monkeypatch,replies):
    data=repeated_heading_fixture();result,records,_=run(data,monkeypatch,iter(replies))
    assert result is data and not records


@pytest.mark.parametrize('damage',['year','missing_year','heading','heading_position','different_line','overlap','duplicate','readable'])
def test_valid_looking_closing_date_is_not_reread_without_unique_measured_anchors(monkeypatch,damage):
    data=repeated_heading_fixture()
    if damage=='year':data['text'][6]='2024 Totals Year-to-Date'
    elif damage=='missing_year':data['text'][6]='Totals Year-to-Date'
    elif damage=='heading':data['text'][1]='Statement Date: O9/24/21'
    elif damage=='heading_position':data['top'][1]=400
    elif damage=='different_line':data['top'][4]=250
    elif damage=='overlap':data['left'][4]=250
    elif damage=='duplicate':
        for k in data:data[k].append(data[k][4])
    elif damage=='readable':data['text'][4]='09/24/21'
    result,records,calls=run(data,monkeypatch,iter(['09/24/21']*4))
    assert result is data and not records and not calls
