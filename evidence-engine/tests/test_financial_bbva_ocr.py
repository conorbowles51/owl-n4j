"""Synthetic scans and crop disagreements; no client evidence in fixtures."""
from copy import deepcopy
import time

import fitz
import pytest

from app.pipeline import financial_bbva_ocr as retry
from tests.test_financial_transaction_date_ocr import Reader


def fixture(kind='transaction_date'):
    cells = [('CASH MANAGEMENT DLLS C INT',420,20,170), ('PAGINA 2/6',535,36,55),
             ('COD. DESCRIPCION',86,140,90), ('OPER LIQ',18,140,46),
             ('O6/AGO',10,160,30), ('06/AGO',52,160,30), ('TRANSFER',86,160,90),
             ('123.45',390,160,28), ('BBVA MEXICO, S.A.',10,760,130)]
    if kind == 'page_number':
        cells[1] = ('se',535,36,55)
        cells[4] = ('06/AGO',10,160,30)
    data = dict(text=[''],left=[0],top=[0],width=[0],height=[0],conf=[-1])
    for value,x,y,width in cells:
        for key,v in dict(text=value,left=x,top=y,width=width,height=7,conf=80).items():
            data[key].append(v)
    return data


def run(data, monkeypatch, replies, deadline=None):
    calls = []
    def read(*args, **kwargs):
        calls.append(kwargs)
        value = next(replies, '')
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(retry.pytesseract,'image_to_string',read)
    with fitz.open() as doc:
        page = doc.new_page(width=612,height=792)
        result, records = retry.reread_bbva_fields(page,data,rotation=0,image_width=612,image_height=792,
            reader=Reader(),deadline=deadline or time.monotonic()+20,language='eng')
    return result, records, calls


@pytest.mark.parametrize('kind,target,text', [('transaction_date',5,'06/AGO'), ('page_number',2,'PAGINA 2/6')])
def test_consensus_preserves_original_words_rectangles_and_unrelated_money(monkeypatch,kind,target,text):
    data = fixture(kind); original = deepcopy(data)
    result, records, calls = run(data,monkeypatch,iter([text]*4))
    assert data == original and result['text'][target] == text
    assert result['text'][:target]+result['text'][target+1:] == data['text'][:target]+data['text'][target+1:]
    assert records[0]['original_text'] == data['text'][target]
    assert records[0]['field'] == kind and records[0]['original_words']
    assert len(records[0]['observations']) == 4 and len(calls) == 4
    assert all(call['timeout'] <= 5 for call in calls)


@pytest.mark.parametrize('replies', [
    ['06/AGO','07/AGO','06/AGO','06/AGO'], ['32/AGO']*4,
    ['06/AGO','','',''], ['06/AGO',RuntimeError('timeout')],
    ['06/INVALID']*4,
])
def test_conflicting_unreadable_or_interrupted_crops_keep_original(monkeypatch,replies):
    data = fixture()
    result, records, _ = run(data,monkeypatch,iter(replies))
    assert result is data and not records


@pytest.mark.parametrize('damage',['bank','product','date_header','description_header','readable_date','reference'])
def test_no_guessing_without_the_printed_bank_and_transaction_headings(monkeypatch,damage):
    data = fixture()
    if damage == 'bank':data['text'][9] = 'Other bank'
    elif damage == 'product':data['text'][1] = 'Other product'
    elif damage == 'date_header':data['text'][4] = 'Other label'
    elif damage == 'description_header':data['text'][3] = 'Other label'
    elif damage == 'readable_date':data['text'][5] = '06/AGO'
    elif damage == 'reference':data['left'][5] = 300
    result, records, calls = run(data,monkeypatch,iter(['06/AGO']*4))
    assert result is data and not records and not calls


def test_expired_budget_keeps_original(monkeypatch):
    data = fixture()
    result, records, calls = run(data,monkeypatch,iter([]),deadline=time.monotonic()-1)
    assert result is data and not records and not calls


@pytest.mark.parametrize('text', ['PAGINA 0/6','PAGINA 7/6','PAGINA 2/501'])
def test_invalid_page_sequences_are_never_substituted(monkeypatch,text):
    data = fixture('page_number')
    result, records, _ = run(data,monkeypatch,iter([text]*4))
    assert result is data and not records


@pytest.mark.parametrize('numeric', [('6/', '06/'), ('06/', '06/')])
def test_numeric_day_consensus_retains_printed_month_and_audits_pixels(monkeypatch, numeric):
    data = fixture(); original = deepcopy(data)
    result, records, calls = run(data, monkeypatch, iter(['O6/AGO'] * 4 + list(numeric)))
    assert data == original and result['text'][5] == '06/AGO'
    assert len(calls) == 6 and len(records[0]['observations']) == 6
    assert all('tessedit_char_whitelist=0123456789/' in call['config'] for call in calls[-2:])
    assert records[0]['original_text'] == 'O6/AGO'


@pytest.mark.parametrize('replies', [
    ['O6/AGO']*4 + ['06/', '07/'],
    ['O6/AGO']*4 + ['32/', '32/'],
    ['O6/AGO']*4 + ['06/', RuntimeError('interrupted')],
    ['06/AGO', '', '', ''] + ['07/', '07/'],
    ['06/AGO', '07/AGO', '', ''] + ['06/', '06/'],
])
def test_numeric_fallback_never_overrides_a_conflict_or_invalid_day(monkeypatch, replies):
    data = fixture()
    result, records, _ = run(data, monkeypatch, iter(replies))
    assert result is data and not records
