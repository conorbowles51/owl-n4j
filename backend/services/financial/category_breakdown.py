"""Money in, money out, net and count per category, under the ledger's filters, as one SQL aggregate.

The category is the one the ledger shows: a person's label first, then the stored category
(services.financial.payment_categories); '' is Uncategorized. Amounts are never added across currencies, so every
row of the answer is one category, one group and one currency.

Group by: nothing ('all'), account holder ('holder'), account ('account'), statement ('statement', the saved source
document) or month of the ledger ordering date ('month').
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, and_, case, cast, func, literal, or_, select

GROUPS = ('all', 'holder', 'account', 'statement', 'month')


class BreakdownFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    group_by: str = Field(default='all', pattern='^(all|holder|account|statement|month)$')
    start_date: date | None = None
    end_date: date | None = None
    account_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    account_holders: list[str] = Field(default_factory=list, max_length=500)
    source_document_ids: list[UUID] = Field(default_factory=list, max_length=5000)
    direction: str = Field(default='', pattern='^(|credit|debit)$')
    currency: str = Field(default='', pattern=r'^$|^[A-Z]{3}$')
    minimum_minor: int | None = Field(default=None, ge=0)
    maximum_minor: int | None = Field(default=None, ge=0)
    search: str = Field(default='', max_length=256)
    categories: list[str] = Field(default_factory=list, max_length=1000)
    judgement: str = Field(default='', pattern='^(|any|none)$')


def category_expression():
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    person = T.metadata_['investigation_labels']['category'].as_string()
    return func.coalesce(person, C.category, literal(''))


def breakdown(session, case_id, filters: BreakdownFilters):
    from postgres.models.financial import FinancialAccount as A, FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    from services.financial.account_selection import apply_account_selection
    category = category_expression().label('category')
    if filters.group_by == 'holder':
        group = func.coalesce(A.holder_name, literal('')).label('group_key')
        label = group
    elif filters.group_by == 'account':
        group = cast(T.account_id, String).label('group_key')
        label = (func.coalesce(A.holder_name, literal('')) + literal(' · ') + func.coalesce(A.institution_name, literal(''))
                 + literal(' · ') + func.coalesce(A.identifier_as_printed, literal('')))
    elif filters.group_by == 'statement':
        group = cast(T.source_document_id, String).label('group_key')
        label = literal('')
    elif filters.group_by == 'month':
        group = func.substr(cast(T.ordering_date, String), 1, 7).label('group_key')
        label = group
    else:
        group = literal('all').label('group_key')
        label = literal('All payments')
    money_in = func.sum(case((T.direction == 'credit', T.amount_minor), else_=0))
    money_out = func.sum(case((T.direction == 'debit', T.amount_minor), else_=0))
    query = (select(category, group, func.max(label).label('group_label'), T.currency, money_in.label('money_in'),
                    money_out.label('money_out'), func.count().label('count'))
             .select_from(T).outerjoin(C, C.transaction_id == T.id)
             .outerjoin(A, and_(A.id == T.account_id, A.case_id == T.case_id))
             .where(T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None)))
    query = apply_account_selection(query, session, case_id, filters.account_ids or None,
                                    filters.account_holders or None)
    if filters.start_date:
        query = query.where(T.ordering_date >= filters.start_date)
    if filters.end_date:
        query = query.where(T.ordering_date <= filters.end_date)
    if filters.source_document_ids:
        query = query.where(T.source_document_id.in_(filters.source_document_ids))
    if filters.direction:
        query = query.where(T.direction == filters.direction)
    if filters.currency:
        query = query.where(T.currency == filters.currency)
    if filters.minimum_minor is not None:
        query = query.where(T.amount_minor >= filters.minimum_minor)
    if filters.maximum_minor is not None:
        query = query.where(T.amount_minor <= filters.maximum_minor)
    if filters.search.strip():
        for word in filters.search.split():
            pattern = f'%{word}%'
            query = query.where(or_(T.description.ilike(pattern), T.counterparty_raw.ilike(pattern),
                                    T.bank_reference.ilike(pattern), category_expression().ilike(pattern)))
    if filters.categories:
        names = ['' if name == 'Uncategorized' else name for name in filters.categories]
        query = query.where(category_expression().in_(names))
    if filters.judgement:
        from postgres.models.financial_judgements import FinancialJudgement as J
        called = select(J.subject_id).where(J.case_id == case_id, J.subject_type == 'transaction')
        query = query.where(T.id.in_(called) if filters.judgement == 'any' else T.id.not_in(called))
    query = query.group_by(category, group, T.currency)
    rows = []
    for name, key, group_label, currency, credit, debit, count in session.execute(query):
        credit, debit = int(credit or 0), int(debit or 0)
        rows.append(dict(category=name or 'Uncategorized', group_key=key or '', group_label=group_label or key or '',
                         currency=currency, money_in_minor=str(credit), money_out_minor=str(debit),
                         net_minor=str(credit - debit), count=count))
    if filters.group_by == 'statement':
        _statement_labels(session, rows)
    rows.sort(key=lambda r: (r['currency'], r['group_key'], -(int(r['money_in_minor']) + int(r['money_out_minor']))))
    return rows


def _statement_labels(session, rows):
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument as D
    ids = list({UUID(row['group_key']) for row in rows if row['group_key']})
    names = {}
    for offset in range(0, len(ids), 1000):
        for doc_id, filename in session.execute(select(D.id, EvidenceFile.original_filename).outerjoin(
                EvidenceFile, EvidenceFile.id == D.evidence_file_id).where(D.id.in_(ids[offset:offset + 1000]))):
            names[str(doc_id)] = filename or ''
    for row in rows:
        row['group_label'] = names.get(row['group_key'], '') or row['group_key'][:8]
