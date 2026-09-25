"""Synthetic measured card cells; no client documents or extracted values."""
from dataclasses import replace
import time
from unittest.mock import Mock

import fitz
import pytest

from app.pipeline import financial_amount_ocr as cells
from app.pipeline import pdf_extraction as pdf


def tables(amount='2O.00'):
    reader = pdf._load_table_reader()
    lines = [
        (10, [(200, 'CREDIT ONE BANK CREDIT CARD STATEMENT')]),
        (22, [(200, 'Account Number 4111 1111 1111 1111')]),
        (34, [(200, 'January 01, 2024 to January 31, 2024')]),
        (60, [(150, 'SUMMARY OF ACCOUNT ACTIVITY'), (345, 'PAYMENT INFORMATION')]),
        (72, [(140, 'Previous Balance'), (260, '$100.00')]),
        (120, [(140, 'New Balance'), (260, '$115.00')]),
        (245, [(275, 'TRANSACTIONS')]),
        (257, [(140, 'Reference Number'), (218, 'Trans Date Post Date Description of Transaction or Credit'), (445, 'Amount')]),
        (270, [(140, 'SYNTHETIC1'), (225, '01/04'), (255, '01/04'), (278, 'EXAMPLE SHOP'), (452, amount)]),
        (282, [(140, 'SYNTHETIC2'), (225, '01/05'), (255, '01/05'), (278, 'PAYMENT - MOBILE APP'), (447, '-5.00')]),
        (378, [(270, '2024 Totals Year-to-Date')]),
    ]
    def locator(x, y, width=20, height=8):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x, y, x + width, y + height)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=i, column=j, text=text, locator=locator(x,y,470-x if x>=440 else min(140,len(text)*2.5)))
        for i,(y,row) in enumerate(lines) for j,(x,text) in enumerate(row)]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles',table=dict(page=1,table=locator(0,0,600,800),values=values,unlocated_values=0)))])


def observations(values):
    return [dict(text=value,dpi=300 if i<3 else 450,threshold=(150,190,220)[i%3]) for i,value in enumerate(values)]


def refine(monkeypatch, values, amount='2O.00'):
    original=tables(amount)
    monkeypatch.setattr(cells,'_cleaned_line_readings',lambda *args:observations(values))
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=800)
        result,records=cells.refine_credit_one_native_cells(page,original,deadline=time.monotonic()+30,language='eng')
    return original,result,records


def test_recovers_only_missing_value_and_retains_every_cell_and_its_original_provenance(monkeypatch):
    original,result,records=refine(monkeypatch,['20.00']*6)
    before=original[0].geometry.cells;after=result[0].geometry.cells
    assert len(before)==len(after)
    assert [(a.row,a.column) for a,b in zip(before,after) if a.text!=b.text]==[(8,4)]
    assert all(a.locator==b.locator for a,b in zip(before,after))
    assert records[0]['original_text']=='2O.00' and records[0]['text']=='20.00'
    assert records[0]['source_locator']==next(c.locator.to_json() for c in before if (c.row,c.column)==(8,4))
    assert records[0]['original_quality']['payments']==records[0]['refined_quality']['payments']==2
    assert records[0]['refined_quality']['unreadable']==0
    assert '20.00' in result[0].chunk
    assert next(c.text for c in before if (c.row,c.column)==(8,4))=='2O.00'


@pytest.mark.parametrize('values',[
    ['20.00']*5+['28.00'], ['']*6, ['20.00']*3+['']*3,
    ['20.00']*4, ['2e1']*6, ['20,00']*6, ['1.000,00']*6,
    ['2O.00']*6, ['']+['20.00']*5,
])
def test_conflicting_incomplete_or_nonliteral_crop_results_are_retained_for_review(monkeypatch,values):
    original,result,records=refine(monkeypatch,values)
    assert result is original and records==[]


def test_complete_existing_value_is_never_replaced_to_fit_controls(monkeypatch):
    original,result,records=refine(monkeypatch,['20.00']*6,amount='21.00')
    assert result is original and records==[]


def test_unrecognised_identity_is_not_eligible_for_cell_repair(monkeypatch):
    original=tables(); table=original[0]
    original=[replace(table,geometry=replace(table.geometry,cells=tuple(replace(c,text='Another bank') if c.row==0 else c for c in table.geometry.cells)))]
    read=Mock()
    monkeypatch.setattr(cells,'_cleaned_line_readings',read)
    with fitz.open() as doc:
        page=doc.new_page(width=600,height=800)
        result,records=cells.refine_credit_one_native_cells(page,original,deadline=time.monotonic()+30,language='eng')
    assert result is original and records==[]
    read.assert_not_called()


def test_full_page_ocr_losing_a_row_uses_only_the_safe_native_cell_fallback(tmp_path,monkeypatch):
    path=tmp_path/'synthetic.pdf'
    with fitz.open() as doc:
        doc.new_page(width=600,height=800);doc.save(path)
    native=tables();table=native[0]
    missing=[replace(table,geometry=replace(table.geometry,cells=tuple(c for c in table.geometry.cells if c.row!=8)))]
    reader=pdf._load_table_reader()
    monkeypatch.setattr(pdf,'_ocr_detection_reason',lambda *args:None)
    monkeypatch.setattr(pdf,'_extract_native_tables',lambda *args:(reader.chunks_of(native),native))
    monkeypatch.setattr(pdf,'_ocr_page',lambda *args:('Synthetic image reading',90,300,[],[]))
    monkeypatch.setattr(reader,'read_positioned_ocr_words',lambda *args,**kwargs:missing)
    monkeypatch.setattr(cells,'_cleaned_line_readings',lambda *args:observations(['20.00']*6))
    result=pdf._extract_pdf_sync(str(path))
    quality=__import__('services.financial.statement_reading_quality',fromlist=['assess_statement_reading']).assess_statement_reading(result.metadata['table_geometry']['per_table'])
    assert quality['payments']==2 and quality['unreadable']==0
    refinements=result.metadata['page_spans'][0]['ocr_refinements']
    assert any(r.get('method')=='tesseract_native_statement_cell_consensus' for r in refinements)
    assert any(r.get('decision')=='native_retained' for r in refinements)
