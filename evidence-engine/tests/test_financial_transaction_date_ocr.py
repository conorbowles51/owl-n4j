from copy import deepcopy
from types import SimpleNamespace
import time

import fitz
import pytest

from app.pipeline import financial_transaction_date_ocr as retry
from app.pipeline import pdf_extraction
from app.pipeline.ocr_geometry import project_ocr_words
from app.services.evidence_document_text import build_canonical_document_text


def fixture(split=False):
    cells = [('Account Statement',430,22,128), ('Andrews',40,34,70), ('123456789',300,65,40),
             ('06/01/20',300,94,33), ('06/30/20',345,94,33),
             ('OG/04',15,220,25), ('Withdrawal Debit Card',75,220,170), ('-12.00',312,220,23), ('88.00',347,220,29),
             ('06/05',15,240,25), ('Deposit Transfer',75,240,170), ('20.00',312,240,23), ('108.00',347,240,29)]
    data = dict(text=[''],left=[0],top=[0],width=[0],height=[0],conf=[-1])
    for text,x,y,width in cells:
        for key,value in dict(text=text,left=x,top=y,width=width,height=7,conf=80).items():
            data[key].append(value)
    if split:
        data['text'][6]='OG';data['width'][6]=10
        for key,value in dict(text='/04',left=26,top=220,width=14,height=7,conf=60).items():
            data[key].append(value)
    return data


class Reader:
    def read_positioned_ocr_words(self,words,**kwargs):
        rows={}
        for word in words:rows.setdefault(word[1],[]).append(word)
        values=[]
        for row,ws in enumerate(rows.values()):
            for col,w in enumerate(sorted(ws,key=lambda w:w[0])):
                values.append(dict(row=row,column=col,text=w[4],locator=dict(rect=[round(v*1000) for v in w[:4]])))
        return [SimpleNamespace(to_json=lambda:dict(table=dict(values=values)))]


def run(data,monkeypatch,replies,deadline=None):
    calls=[]
    def read(image,**kwargs):
        calls.append(kwargs);value=next(replies,'')
        if isinstance(value,Exception):raise value
        return value
    monkeypatch.setattr(retry.pytesseract,'image_to_string',read)
    with fitz.open() as d:
        page=d.new_page(width=612,height=792)
        result,records=retry.reread_financial_transaction_dates(page,data,rotation=0,image_width=612,image_height=792,
            reader=Reader(),deadline=deadline or time.monotonic()+20,language='eng')
    return result,records,calls


def test_matching_dates_retain_raw_words_money_and_period_context(monkeypatch):
    data=fixture();before=deepcopy(data)
    result,records,calls=run(data,monkeypatch,iter(['06/04']*4))
    assert data==before and result['text'][6]=='06/04'
    assert result['text'][:6]+result['text'][7:]==data['text'][:6]+data['text'][7:]
    assert records[0]['original_text']=='OG/04'
    assert records[0]['period_start']=='2020-06-01' and records[0]['period_end']=='2020-06-30'
    assert [o['dpi'] for o in records[0]['observations']]==[300,300,450,450]
    assert len(calls)==4 and all(c['timeout']<=5 for c in calls)


@pytest.mark.parametrize('replies',[
    ['06/04','06/04','06/05','06/04'], ['07/04']*4, ['02/30']*4,
    ['6/04','06/04','06/04','06/04'], ['06/04','','',''],
    ['06/04',RuntimeError('timeout')], ['06/04','07/04','06/04','06/04'],
])
def test_conflicts_partial_primary_invalid_dates_and_timeout_stay_flagged(monkeypatch,replies):
    data=fixture();result,records,_=run(data,monkeypatch,iter(replies))
    assert result is data and not records


@pytest.mark.parametrize('damage',['bank','period','reversed','account','date_position','description','money_position','baseline','readable','two_dates'])
def test_unclear_context_and_readable_in_period_dates_do_not_trigger_a_retry(monkeypatch,damage):
    data=fixture()
    if damage=='bank':data['text'][2]='Other bank'
    elif damage=='period':data['text'][4]='OG/01/20'
    elif damage=='reversed':data['text'][4]='06/30/20';data['text'][5]='06/01/20'
    elif damage=='account':data['text'][3]='1234'
    elif damage=='date_position':data['left'][6]=65
    elif damage=='description':data['text'][7]='Payment summary'
    elif damage=='money_position':data['left'][8]=200
    elif damage=='baseline':data['top'][8]+=10
    elif damage=='readable':data['text'][6]='06/04'
    elif damage=='two_dates':data['text'][6]='06/04 06/03'
    result,records,calls=run(data,monkeypatch,iter(['06/04']*4))
    assert result is data and not records and not calls


def test_complete_but_out_of_period_date_needs_new_visual_agreement(monkeypatch):
    data=fixture();data['text'][6]='07/04'
    result,records,_=run(data,monkeypatch,iter(['06/04']*4))
    assert result['text'][6]=='06/04' and records[0]['original_text']=='07/04'
    result,records,_=run(data,monkeypatch,iter(['07/04']*4))
    assert result is data and not records


def test_split_date_merges_only_its_original_words_and_rectangles(monkeypatch):
    data=fixture(split=True);before=deepcopy(data)
    result,records,_=run(data,monkeypatch,iter(['06/04']*4))
    assert data==before and result['text'][6]=='06/04' and result['text'][-1]==''
    assert result['left'][6]==15 and result['width'][6]==25
    assert [w['text'] for w in records[0]['original_words']]==['OG','/04']
    assert result['text'][7:14]==data['text'][7:14]


def test_expired_budget_keeps_original(monkeypatch):
    data=fixture();result,records,calls=run(data,monkeypatch,iter([]),deadline=time.monotonic()-1)
    assert result is data and not records and not calls


def test_canonical_page_text_geometry_and_provenance_keep_the_same_date(monkeypatch):
    data=fixture()
    monkeypatch.setattr(pdf_extraction,'_render_dpi',lambda page:72)
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_osd',lambda *a,**kw:dict(rotate=0,orientation_conf=20))
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_data',lambda *a,**kw:data)
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_string',lambda *a,**kw:'06/04')
    monkeypatch.setattr(pdf_extraction,'_load_table_reader',lambda:Reader())
    with fitz.open() as d:
        page=d.new_page(width=612,height=792)
        text,confidence,dpi,words,records=pdf_extraction._ocr_page(page)
    assert 'OG/04' not in text and '06/04' in text and any(w[4]=='06/04' for w in words)
    page_result=pdf_extraction._PageResult(page_number=1,text=text,extraction_method='tesseract_ocr',text_origin='recognised_glyphs',ocr_refinements=records)
    canonical=build_canonical_document_text(SimpleNamespace(text=text,tables=[],metadata=dict(file_type='pdf',page_spans=[pdf_extraction._page_span(page_result,0)])))
    assert canonical.source_locations[0]['ocr_refinements']==records
    assert records[0]['method']=='tesseract_transaction_date_crop_consensus'
