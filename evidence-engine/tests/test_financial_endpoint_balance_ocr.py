"""Unreadable printed opening/ending balances on Andrews OCR pages."""
import time
from copy import deepcopy

import fitz

from app.pipeline import financial_amount_ocr as retry
from tests.test_financial_amount_ocr import Reader


def page_data(endpoint, money='2O0.00', money_x=347):
    rows = [
        [(15, 'Andrews', 55), (320, 'Account Statement', 100)],
        [(15, '06/04', 25), (75, 'Withdrawal Debit Card', 190), (312, '-12.00', 23), (347, '300.00', 29)],
        [(x, text, width) for x, text, width in endpoint] + [(money_x, money, 29)],
    ]
    data = dict(text=[''], left=[0], top=[0], width=[0], height=[0], conf=[-1])
    for row, cells in enumerate(rows):
        for x, text, width in cells:
            for k, v in dict(text=text, left=x, top=40 if row == 0 else 200 + row * 20, width=width, height=7, conf=80).items():
                data[k].append(v)
    return data


ENDING = [(15, '06/30', 25), (75, 'Ending', 30), (110, 'Balance', 35)]
OPENING = [(15, '06/01', 25), (45, 'ID', 10), (60, '0040', 20), (85, 'FREE', 20), (110, 'CHECKING', 40),
           (155, 'Previous', 35), (195, 'Balance', 35)]


def run(data, monkeypatch, replies):
    monkeypatch.setattr(retry, '_cleaned_line_readings', lambda *a: [])
    calls = []

    def read(image, **kwargs):
        calls.append(kwargs)
        return next(replies, '')
    monkeypatch.setattr(retry.pytesseract, 'image_to_string', read)
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        result, records = retry.reread_financial_amounts(page, data, rotation=0, image_width=612, image_height=792,
            reader=Reader(), deadline=time.monotonic() + 20, language='eng')
    return result, records, calls


def test_unreadable_ending_and_previous_balances_are_reread_with_provenance(monkeypatch):
    for endpoint in (ENDING, OPENING):
        data = page_data(endpoint)
        before = deepcopy(data)
        result, records, calls = run(data, monkeypatch, iter(['200.00', '200.00']))
        assert data == before
        assert result['text'][-1] == '200.00'
        assert result['text'][:-1] == data['text'][:-1]
        assert records[0]['field'] == 'balance' and records[0]['reason'] == 'unreadable_endpoint_balance'
        assert records[0]['original_text'] == '2O0.00' and records[0]['text'] == '200.00'


def test_disagreeing_or_incomplete_crop_readings_leave_the_balance_unread(monkeypatch):
    for replies in (['200.00', '208.00'], ['200.00', ''], ['', '']):
        result, records, _ = run(page_data(ENDING), monkeypatch, iter(replies))
        assert result['text'][-1] == '2O0.00' and not records


def test_readable_or_unlabelled_or_misplaced_values_are_not_targets(monkeypatch):
    cases = [page_data(ENDING, money='200.00'),
             page_data([(15, '06/30', 25), (75, 'Ending', 30), (110, 'Balances', 35)]),
             page_data([(15, '06/30', 25), (75, 'Balance', 35)]),
             page_data(ENDING, money_x=300)]
    for data in cases:
        result, records, calls = run(data, monkeypatch, iter(['200.00', '200.00']))
        assert result is data and not records and not calls
