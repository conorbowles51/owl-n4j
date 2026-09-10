"""Guided, source-referenced indirect workpapers; never a tax or guilt finding."""
import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.money import get_currency

REFERENCE = 'https://www.irs.gov/irm/part9/irm_09-005-009'
# Signs describe only the selected worksheet arithmetic, not source classification.
METHODS = {
    'net_worth': dict(label='Net worth', reference_section='9.5.9.5.4', terms=[
        ('closing_assets','Closing assets at cost or applicable basis',1,False),
        ('closing_liabilities','Closing liabilities and accumulated depreciation',-1,False),
        ('opening_assets','Opening assets at cost or applicable basis',-1,False),
        ('opening_liabilities','Opening liabilities and accumulated depreciation',1,False),
        ('personal_outlays','Personal expenditure and nondeductible losses',1,False),
        ('nontaxable','Adjustments for non-taxable items',-1,False),
        ('deductions','Applicable deductions and exemptions',-1,False),
        ('reported_income','Reported taxable income',-1,True)]),
    'bank_deposits': dict(label='Bank deposits',reference_section='9.5.9.7',terms=[
        ('deposits','Total deposits across the reviewed accounts',1,False),
        ('currency_expenditure','Currency expenditure outside those deposits',1,False),
        ('cash_change','Increase or decrease in cash on hand',1,True),
        ('nonincome','Non-income deposits and items, including transfers',-1,False),
        ('cost_of_goods','Cost of goods sold',-1,False),
        ('business_expenses','Business and rental expenses',-1,False),
        ('income_adjustments','Adjustments to income',-1,False),
        ('deductions','Applicable personal deductions and exemptions',-1,False),
        ('reported_income','Reported taxable income',-1,True)]),
    'expenditure': dict(label='Expenditure',reference_section='9.5.9.6.3',terms=[
        ('money_applied','Money spent or applied, including asset/liability changes',1,False),
        ('nontaxable','Non-taxable funding sources',-1,False),
        ('deductions','Applicable deductions and exemptions',-1,False),
        ('reported_income','Reported taxable income',-1,True)]),
    'cash_t': dict(label='Cash-T',reference_section='9.5.9.8.4',terms=[
        ('cash_uses','All reviewed cash uses',1,False),
        ('cash_sources','Known cash sources, including opening cash and non-taxable sources',-1,False)]),
}
REQUIREMENTS = {
    'starting_position':'Establish the starting assets, liabilities and cash on hand; explain any converted assets.',
    'nonincome_sources':'Investigate loans, gifts, inheritance, transfers, capital returns and other non-income sources.',
    'leads':'Record follow-up of reasonable explanations, alternative funding sources and unresolved leads.',
    'applicability':'Explain the period, subject, accounting basis and applicable rules, including deductions; establish the income-source basis.',
}


def indirect_methods():
    return dict(reference=REFERENCE,methods=[dict(id=key,label=value['label'],reference_section=value['reference_section'],
        terms=[dict(id=i,label=label,sign=sign,signed=signed) for i,label,sign,signed in value['terms']]) for key,value in METHODS.items()],
        requirements=[dict(id=key,label=value) for key,value in REQUIREMENTS.items()])


class IndirectEntry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    amount_minor: str | None = Field(default=None,pattern=r'^(0|-?[1-9][0-9]{0,18})$')
    basis: str = Field(default='',max_length=4096)
    source_file_id: UUID | None = None
    source_location: str = Field(default='',max_length=1024)


class IndirectRequirement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status: Literal['unresolved','reviewed'] = 'unresolved'
    basis: str = Field(default='',max_length=4096)
    source_file_id: UUID | None = None
    source_location: str = Field(default='',max_length=1024)


class IndirectReviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    method: Literal['net_worth','bank_deposits','expenditure','cash_t']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    start_date: date
    end_date: date
    subject: str = Field(min_length=1,max_length=512)
    entries: dict[str,IndirectEntry] = Field(default_factory=dict,max_length=20)
    requirements: dict[str,IndirectRequirement] = Field(default_factory=dict,max_length=4)


def evaluate_indirect_review(case_id, request, sources):
    request=IndirectReviewInput.model_validate(request)
    get_currency(request.currency)
    if request.start_date>request.end_date or not request.subject.strip():
        raise LedgerSummaryError('Choose an ordered period and identify the subject of this review.')
    method=METHODS[request.method]
    allowed={key for key,_,_,_ in method['terms']}
    if set(request.entries)-allowed or set(request.requirements)-set(REQUIREMENTS):
        raise LedgerSummaryError('The workpaper contains fields for a different method.')
    requested_ids={str(item.source_file_id) for item in [*request.entries.values(),*request.requirements.values()] if item.source_file_id}
    indexed={source['id']:source for source in sources}
    if len(indexed)!=len(sources) or set(indexed)!=requested_ids or any(source['case_id']!=str(case_id) for source in sources):
        raise LedgerSummaryError('Workpaper sources do not match the selected case files.')
    missing=[];lines=[];total=0
    for key,label,sign,signed in method['terms']:
        entry=request.entries.get(key,IndirectEntry())
        if entry.amount_minor is not None:
            amount=int(entry.amount_minor)
            if abs(amount)>9223372036854775807 or (not signed and amount<0):
                raise LedgerSummaryError('A workpaper amount is outside its supported range or sign.')
            total+=sign*amount
        if entry.amount_minor is None or not entry.basis.strip() or not entry.source_file_id or not entry.source_location.strip():
            missing.append(dict(kind='amount',id=key,label=label))
        lines.append(dict(id=key,label=label,sign=sign,**entry.model_dump(mode='json')))
    for key,label in REQUIREMENTS.items():
        item=request.requirements.get(key,IndirectRequirement())
        if item.status!='reviewed' or not item.basis.strip() or not item.source_file_id or not item.source_location.strip():
            missing.append(dict(kind='review',id=key,label=label))
    value=dict(schema='loupe.financial.indirect_review/1',case_id=str(case_id),applied=False,
        reference=REFERENCE,reference_section=method['reference_section'],inputs=request.model_dump(mode='json'),
        method_label=method['label'],lines=lines,sources=sorted(sources,key=lambda s:s['id']),missing=missing,
        review_fields_complete=not missing,difference_minor=str(total) if not missing else None,
        limitation='Conditional arithmetic from investigator-entered amounts and recorded source references. Review fields being complete does not independently verify the sources, coverage, accounting treatment, tax liability, undeclared income or wrongdoing. No source or ledger classification is changed. Unknown amounts are not zero; investigate remaining leads before drawing conclusions.')
    content=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    encoded=content.encode()
    return dict(case_id=str(case_id),applied=False,scenario_json=content,scenario_sha256=hashlib.sha256(encoded).hexdigest(),scenario_byte_count=len(encoded))
