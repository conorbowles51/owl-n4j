from copy import deepcopy
import time
from types import SimpleNamespace

import fitz
import pytest

from app.pipeline import financial_amount_ocr as retry
from app.pipeline import pdf_extraction
from app.pipeline.ocr_geometry import project_ocr_words
from app.services.evidence_document_text import build_canonical_document_text


def fixture(split=False):
    rows = [
        [(15,'Andrews',55),(320,'Account Statement',100)],
        [(15,'06/04',25),(75,'Withdrawal Debit Card',190),(312,'~12.00',23),(347,'300.00',29)],
        [(15,'06/05',25),(75,'Deposit Online Banking Transfer',190),(312,'20.00',23),(347,'320.00',29)],
    ]
    data = dict(text=[''],left=[0],top=[0],width=[0],height=[0],conf=[-1])
    for row, cells in enumerate(rows):
        for x, text, width in cells:
            for k,v in dict(text=text,left=x,top=40 if row==0 else 200+row*20,width=width,height=7,conf=80).items():
                data[k].append(v)
    if split:
        data['text'][5] = '~12.';data['width'][5] = 15
        for k,v in dict(text='00',left=329,top=220,width=6,height=7,conf=80).items():data[k].append(v)
    return data


class Reader:
    def read_positioned_ocr_words(self, words, **kwargs):
        rows={}
        for w in words: rows.setdefault(w[1],[]).append(w)
        values=[]
        for row, ws in enumerate(rows.values()):
            ws.sort(key=lambda w:w[0]);col=0;i=0
            while i<len(ws):
                group=[ws[i]]
                if ws[i][4]=='~12.' and i+1<len(ws) and ws[i+1][4]=='00':
                    group.append(ws[i+1]);i+=1
                values.append(dict(row=row,column=col,text=' '.join(w[4] for w in group),
                    locator=dict(rect=[round(v*1000) for v in (group[0][0],min(w[1] for w in group),group[-1][2],max(w[3] for w in group))])))
                col+=1;i+=1
        return [SimpleNamespace(to_json=lambda:dict(table=dict(values=values)))]


def run(data,monkeypatch,replies,deadline=None,cleaned=False):
    if not cleaned:
        monkeypatch.setattr(retry,'_cleaned_line_readings',lambda *a:[])
    calls=[]
    def read(image,**kwargs):
        calls.append(kwargs);value=next(replies,'')
        if isinstance(value,Exception):raise value
        return value
    monkeypatch.setattr(retry.pytesseract,'image_to_string',read)
    with fitz.open() as doc:
        page=doc.new_page(width=612,height=792)
        result,records=retry.reread_financial_amounts(page,data,rotation=0,image_width=612,image_height=792,
            reader=Reader(),deadline=deadline or time.monotonic()+20,language='eng')
    return result,records,calls


def test_matching_amount_reread_retains_original_and_other_fields(monkeypatch):
    data=fixture();before=deepcopy(data)
    result,records,calls=run(data,monkeypatch,iter(['-12.00','-12.00']))
    assert data==before and result is not data
    assert result['text'][5]=='-12.00'
    assert all(result[k]==data[k] for k in data if k!='text')
    assert result['text'][:5]+result['text'][6:]==data['text'][:5]+data['text'][6:]
    assert records[0]['original_text']=='~12.00' and records[0]['field']=='amount'
    assert records[0]['original_words']==[dict(text='~12.00',rect=[312000,220000,335000,227000])]
    assert records[0]['text']=='-12.00' and len(calls)==2
    assert all(c['timeout']<=10 for c in calls)


@pytest.mark.parametrize('replies',[
    ['-12.00','-12.01'],['-12.00','12.00'],['12.00','12.00'],
    ['-12.0','-12.0'],['-12,00','-12,00'],['12','-12.00'],
    [RuntimeError('Timed out')],['-12.00','12','-13.00','-12.00'],
])
def test_different_digits_lost_sign_incomplete_primary_and_failures_stay_unresolved(monkeypatch,replies):
    data=fixture();result,records,_=run(data,monkeypatch,iter(replies))
    assert result is data and not records


def test_second_resolution_may_confirm_but_never_outvote(monkeypatch):
    result,records,calls=run(fixture(),monkeypatch,iter(['-12.00','12','-12.00','12']))
    assert result['text'][5]=='-12.00' and len(calls)==4
    assert [o['dpi'] for o in records[0]['observations']]==[720,720,600,600]


def test_compact_crop_recovers_a_fragmented_amount_and_retains_every_observation(monkeypatch):
    data=fixture();before=deepcopy(data)
    result,records,calls=run(data,monkeypatch,iter(['12','1200','-12.00','-12.00','-12.00','-12.00']))
    assert result['text'][5]=='-12.00' and data==before
    assert records[0]['dpi']==300
    assert [o['dpi'] for o in records[0]['observations']]==[720,720,300,300,450,450]
    assert records[0]['observations'][2]['profile']=='compact_white_border'
    assert len(calls)==6


@pytest.mark.parametrize('replies',[
    ['12','-13.00','-12.00','-12.00','-12.00','-12.00'],
    ['12','1200','12.00','12.00','12.00','12.00'],
    ['12','1200','12','-12.00','-12.00','-12.00'],
    ['12','1200','-12.00','-12.00','-12.01','-12.00'],
])
def test_compact_profile_cannot_outvote_prior_or_later_digits_drop_sign_or_use_fragmented_primary(monkeypatch,replies):
    data=fixture();result,records,_=run(data,monkeypatch,iter(replies))
    assert result is data and not records


def test_separate_fragments_in_one_money_column_and_damaged_date_keep_other_fields(monkeypatch):
    data=fixture();data['text'][3]='Lif 23';data['text'][5]='~1';data['width'][5]=10
    for key,value in dict(text='2.00',left=325,top=220,width=10,height=7,conf=70).items():
        data[key].append(value)
    result,records,_=run(data,monkeypatch,iter(['-12.00','-12.00']))
    assert result['text'][5]=='-12.00' and result['text'][-1]==''
    assert result['text'][3]=='Lif 23' and result['text'][6]=='300.00'
    assert [w['text'] for w in records[0]['original_words']]==['~1','2.00']
    assert result['left'][5]==312 and result['width'][5]==23


@pytest.mark.parametrize('damage',['bank','title','date_position','description','amount_position','overlap','baseline','readable'])
def test_uncertain_context_and_existing_valid_money_are_unchanged(monkeypatch,damage):
    data=fixture()
    if damage=='bank':data['text'][1]='Other Bank'
    if damage=='title':data['text'][2]='Payment Slip'
    if damage=='date_position':data['left'][3]=65
    if damage=='description':data['text'][4]='Monthly payment estimate'
    if damage=='amount_position':data['left'][5]=275
    if damage=='overlap':data['left'][6]=328
    if damage=='baseline':data['top'][5]+=12
    if damage=='readable':data['text'][5]='-12.00'
    result,records,calls=run(data,monkeypatch,iter([]))
    assert result is data and not records and not calls


def test_split_cell_keeps_union_geometry_and_original_words(monkeypatch):
    data=fixture(split=True);before=deepcopy(data)
    result,records,_=run(data,monkeypatch,iter(['-12.00','-12.00']))
    assert data==before
    assert result['text'][5]=='-12.00' and result['text'][-1]==''
    assert result['left'][5]==312 and result['width'][5]==23
    assert [w['text'] for w in records[0]['original_words']]==['~12.','00']
    words=project_ocr_words(result,rotation=0,image_width=612,image_height=792,page_width=612,page_height=792)
    assert (312,220,335,227,'-12.00') in words
    assert (347,220,376,227,'300.00') in words


def test_adjustment_credit_and_balance_are_not_forced_to_withdrawal_sign(monkeypatch):
    data=fixture();data['text'][4]='Withdrawal Adjustment Debit Card Credit Voucher'
    result,records,_=run(data,monkeypatch,iter(['12.00','12.00']))
    assert result['text'][5]=='12.00'
    data=fixture();data['text'][5]='-12.00';data['text'][6]='3OO.00'
    result,records,_=run(data,monkeypatch,iter(['300.00','300.00']))
    assert result['text'][6]=='300.00' and records[0]['field']=='balance'
    data=fixture();data['text'][4]='Deposit Online Banking Transfer'
    result,records,_=run(data,monkeypatch,iter(['-12.00','-12.00']))
    assert result is data and not records


def test_expired_deadline_has_no_extra_ocr_calls(monkeypatch):
    data=fixture();result,records,calls=run(data,monkeypatch,iter([]),deadline=time.monotonic()-1)
    assert result is data and not records and not calls


def test_page_text_geometry_and_saved_provenance_agree(monkeypatch):
    data=fixture()
    monkeypatch.setattr(pdf_extraction,'_render_dpi',lambda page:72)
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_osd',lambda *a,**kw:dict(rotate=0,orientation_conf=20))
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_data',lambda *a,**kw:data)
    monkeypatch.setattr(pdf_extraction.pytesseract,'image_to_string',lambda *a,**kw:'-12.00')
    monkeypatch.setattr(pdf_extraction,'_load_table_reader',lambda:Reader())
    with fitz.open() as doc:
        page=doc.new_page(width=612,height=792)
        text,confidence,dpi,words,records=pdf_extraction._ocr_page(page)
    assert '-12.00' in text and '~12.00' not in text
    assert any(w[4]=='-12.00' for w in words)
    result=pdf_extraction._PageResult(page_number=1,text=text,extraction_method='tesseract_ocr',
        text_origin='recognised_glyphs',ocr_refinements=records)
    canonical=build_canonical_document_text(SimpleNamespace(text=text,tables=[],metadata=dict(file_type='pdf',page_spans=[pdf_extraction._page_span(result,0)])))
    assert canonical.source_locations[0]['ocr_refinements']==records
    assert records[0]['method']=='tesseract_amount_crop_consensus'


def test_cleaned_single_line_profile_requires_both_sizes_and_keeps_provenance(monkeypatch):
    data=fixture();before=deepcopy(data)
    result,records,calls=run(data,monkeypatch,iter(['-12.00']*6),cleaned=True)
    assert result['text'][5]=='-12.00' and data==before and len(calls)==6
    assert all('--psm 7 ' in c['config'] for c in calls)
    assert records[0]['profile']=='cleaned_single_line' and records[0]['segmentation_modes']==[7]
    assert [o['threshold'] for o in records[0]['observations']]==[150,190,220,150,190,220]
    assert [o['dpi'] for o in records[0]['observations']]==[300]*3+[450]*3
    assert records[0]['original_words'][0]['text']=='~12.00'
    assert result['text'][:5]+result['text'][6:]==data['text'][:5]+data['text'][6:]


@pytest.mark.parametrize('replies',[
    ['-12.00']*5+['12.00'], ['-12.00']*5+['-12.01'],
    ['12.00']*6, ['12']+['-12.00']*5,
    ['-12.00']*3+['12']*3,
    ['-12.00']*5+[RuntimeError('deadline')],
])
def test_cleaned_profile_never_votes_away_digits_signs_or_incomplete_primary(monkeypatch,replies):
    data=fixture();result,records,_=run(data,monkeypatch,iter(replies),cleaned=True)
    assert result is data and not records


def test_cleaned_profile_allows_nonreadable_attempts_but_requires_four_complete_matches(monkeypatch):
    result,records,calls=run(fixture(),monkeypatch,iter(['-12.00','-12.00','12','-12.00','12','-12.00']),cleaned=True)
    assert result['text'][5]=='-12.00' and len(calls)==6
    assert len(records[0]['observations'])==6


def test_legacy_fallback_cannot_override_a_complete_cleaned_reading(monkeypatch):
    data=fixture();result,records,_=run(data,monkeypatch,iter(['12']*5+['-13.00']+['-12.00']*2),cleaned=True)
    assert result is data and not records


def test_legacy_fallback_can_confirm_an_incomplete_cleaned_profile(monkeypatch):
    result,records,calls=run(fixture(),monkeypatch,iter(['12']*5+['-12.00']+['-12.00']*2),cleaned=True)
    assert result['text'][5]=='-12.00' and len(calls)==8
    assert len(records[0]['observations'])==8 and records[0]['profile']=='original_or_compact'


def test_cleaned_credit_adjustment_keeps_the_positive_sign_and_deposit_cannot_be_negative(monkeypatch):
    data=fixture();data['text'][4]='Withdrawal Adjustment Credit Voucher'
    result,records,_=run(data,monkeypatch,iter(['12.00']*6),cleaned=True)
    assert result['text'][5]=='12.00' and records[0]['profile']=='cleaned_single_line'
    data=fixture();data['text'][4]='Deposit Transfer'
    result,records,_=run(data,monkeypatch,iter(['-12.00']*6),cleaned=True)
    assert result is data and not records
