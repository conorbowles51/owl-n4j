"""Synthetic closing strips only; never client documents or extracted values."""
from copy import deepcopy
import time

import fitz
import pytest

from app.pipeline import financial_santander_ocr as retry
from tests.test_financial_transaction_date_ocr import Reader


def fixture():
    cells = [('Banco Santander Mexico, S.A.',30,25,190),
        ('CODIGO DE CLIENTE NO. 12345678',350,65,210),
        ('PERIODO DEL 01-SEP-2024 AL 30-SEP-2024',320,85,260),
        ('FECHA',30,130,45),('DEPOSITO',370,130,50),('RETIRO',435,130,50),('SALDO',500,130,50),
        ('TOTAL',120,300,70),('40.00',380,300,40),('10.00',445,300,40),
        ('NEXT SECTION',30,350,120),('Page 1',530,760,50)]
    data = dict(text=[],left=[],top=[],width=[],height=[],conf=[])
    for value,x,y,width in cells:
        for key,v in dict(text=value,left=x,top=y,width=width,height=7,conf=80).items():
            data[key].append(v)
    return data


def crop(amount='$130.00', *, confidence=90, label='SALDO FINAL DEL PERIODO:'):
    words=label.split()+[amount]
    return dict(text=words,left=[15+i*80 for i in range(len(words))],
        top=[20]*len(words),width=[70]*len(words),height=[20]*len(words),conf=[confidence]*len(words))


def run(monkeypatch, data, replies, *, rotation=0, deadline=None):
    calls=[]
    def read(*args,**kwargs):
        calls.append(kwargs)
        value=next(replies)
        if isinstance(value,Exception):raise value
        return value
    monkeypatch.setattr(retry.pytesseract,'image_to_data',read)
    with fitz.open() as document:
        page=document.new_page(width=612,height=792)
        result,records=retry.reread_santander_closing(page,data,rotation=rotation,
            image_width=612,image_height=792,reader=Reader(),
            deadline=deadline or time.monotonic()+20,language='eng')
    return result,records,calls


def test_complete_consensus_adds_only_measured_control_and_retains_original(monkeypatch):
    data=fixture();original=deepcopy(data)
    result,records,calls=run(monkeypatch,data,iter([crop() for _ in range(4)]))
    assert data==original
    assert result['text'][:len(data['text'])]==data['text']
    assert result['text'][-2:]==['SALDO FINAL DEL PERIODO:','$130.00']
    assert all(len(values)==len(result['text']) for values in result.values())
    assert len(records)==1 and records[0]['original_text'] is None
    assert len(records[0]['observations'])==4
    assert [o['dpi'] for o in records[0]['observations']]==[300,300,450,450]
    assert all(call['timeout']<=5 for call in calls)
    assert records[0]['rect'][1]>=307000


@pytest.mark.parametrize('replies', [
    [crop(),crop('$131.00'),crop(),crop()],
    [crop(),crop('1e3')], [crop(confidence=20)],
    [crop(label='OPENING BALANCE:')], [crop('$130,00')],
    [crop(),RuntimeError('timeout')],
])
def test_conflicting_unreadable_or_incomplete_crops_do_not_add_balance(monkeypatch,replies):
    data=fixture();original=deepcopy(data)
    result,records,_=run(monkeypatch,data,iter(replies))
    assert result is data and result==original and not records


@pytest.mark.parametrize('damage',['bank','customer','period','columns','totals','existing','rotation','budget'])
def test_only_explicit_layout_missing_strip_is_reread(monkeypatch,damage):
    data=fixture()
    index={'bank':0,'customer':1,'period':2,'columns':4,'totals':7}.get(damage)
    if index is not None:data['text'][index]='UNREADABLE'
    if damage=='existing':
        for k,v in dict(text='SALDO FINAL DEL PERIODO: $999.00',left=350,top=313,width=230,height=7,conf=80).items():
            data[k].append(v)
    result,records,calls=run(monkeypatch,data,iter([]),rotation=90 if damage=='rotation' else 0,
        deadline=time.monotonic()-1 if damage=='budget' else None)
    assert result is data and not records and not calls


def test_border_glyph_is_not_an_amount_or_label_correction():
    data=crop();data={key:(["|"] if key=='text' else [90] if key=='conf' else [0])+values for key,values in data.items()}
    reading=retry._observation(data,[350,310,590,330],300,None)
    assert reading and reading['amount']=='$130.00'
    data['text'][1]='5ALDO'
    assert retry._observation(data,[350,310,590,330],300,None) is None
