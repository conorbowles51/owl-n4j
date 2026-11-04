"""Security rows of a brokerage statement, kept in step with the money ledger.

``sync_document`` is the one writer of ``financial_security_rows`` for a statement in the money ledger. It reads the
statement's admitted cash rows and page tables (``brokerage_reading``) and makes the security rows match:

- a trade per cash row whose printed line moves a security, linked to that cash row (its cash leg), with the cash
  row's proof class, extraction layer, locator and reading origin (a model's reading stays the model's);
- a holding per printed position line and open repurchase agreement.

It never writes a cash row. It is called by every writer of a statement's cash rows (a new reading, a replaced or
recovered reading, a correction, a currency edit) and by the backfill (``scripts/financial_brokerage_rows.py``), so
existing statements are read through the same path as new ones.

A row whose reading changed is superseded, never overwritten: the new reading is a new row. A person's correction
or confirmation carries to the new row only while the value it was made against still reads the same.

Switch: ``LOUPE_FINANCIAL_BROKERAGE_ROWS`` (default on). Off: no security rows are written; the money ledger is
unaffected either way.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from postgres.models.financial import (FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod,
                                       FinancialTransaction)
from postgres.models.financial_securities import FinancialSecurityRow
from services.financial import brokerage_reading as reading

log = logging.getLogger(__name__)

READERS = (reading.READER_MOVEMENTS, reading.READER_HOLDINGS)
FUND_READERS = (reading.READER_FUNDS,)
# Fields a person may correct, and the reading value each correction is held against.
CORRECTABLE = ('instrument', 'quantity', 'price', 'trade_date', 'settlement_date', 'execution_time', 'isin',
               'gross_minor', 'commission_minor', 'premium_minor', 'tax_minor', 'net_minor', 'market_value_minor')


def enabled() -> bool:
    return os.environ.get('LOUPE_FINANCIAL_BROKERAGE_ROWS', '1').strip().lower() not in ('0', 'false', 'off', 'no')


def brokerage_institutions() -> frozenset:
    """Institutions whose statements are read with a brokerage cash-ledger profile (``holdings_currency``)."""
    from services.financial.statement_engine_profiles import PROFILES
    return frozenset(p['institution'] for p in PROFILES if p.get('holdings_currency') and p.get('institution'))


def is_brokerage_document(session, document) -> bool:
    names = brokerage_institutions()
    accounts = session.scalars(select(FinancialAccount.institution_name).join(
        FinancialStatementPeriod, FinancialStatementPeriod.account_id == FinancialAccount.id).where(
        FinancialStatementPeriod.source_document_id == document.id)).all()
    return any(name in names for name in accounts)


def _plain(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')  # 99.9901436300 from the database reads as 99.99014363
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _digest(values: dict) -> str:
    return hashlib.sha256(json.dumps(_plain(values), sort_keys=True, default=str).encode()).hexdigest()


_COLUMNS = ('row_kind', 'operation', 'side', 'holding_kind', 'instrument', 'issuer', 'series', 'isin',
            'quantity_printed', 'quantity', 'price_printed', 'price', 'currency', 'gross_minor', 'commission_minor',
            'premium_minor', 'tax_minor', 'net_minor', 'market_value_minor', 'trade_date', 'trade_date_source',
            'execution_time', 'settlement_date', 'as_of_date', 'term_days', 'rate_printed', 'proof_class',
            'extraction_layer', 'reader', 'account_id', 'statement_period_id', 'cash_transaction_id')


def _cash_key(row) -> str:
    original = (row.provenance or {}).get('statement_import_original') or {}
    if original.get('id'):
        return f"cash:{original['id']}"
    return f'cash-ref:{row.ref_id}'


def _reading_origin(row) -> Optional[dict]:
    confirmed = (row.provenance or {}).get('confirmed_by') or {}
    origin = confirmed.get('origin') if isinstance(confirmed, dict) else None
    return origin if isinstance(origin, dict) and origin.get('kind') == 'model' else None


def desired_rows(session, document) -> list:
    """The security rows the document's current reading prints: [(reading_key, values, provenance)]."""
    cash = session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.ledger_status == 'admitted').order_by(FinancialTransaction.row_index)).all()
    found = []
    currencies = {row.currency for row in cash}
    for row in cash:
        original = (row.provenance or {}).get('statement_import_original') or {}
        trade = reading.trade_from_cash_row(
            cells=original.get('source_cells'), description=row.description or '', settlement=row.transaction_date,
            amount_minor=row.amount_minor, direction=getattr(row.direction, 'value', row.direction))
        if trade is None:
            continue
        values = dict(
            row_kind='trade', operation=trade['operation'], side=trade['side'], holding_kind=None,
            instrument=trade['instrument'], issuer=trade['issuer'], series=trade['series'], isin=None,
            quantity_printed=trade['quantity_printed'], quantity=trade['quantity'],
            price_printed=trade['price_printed'], price=trade['price'], currency=row.currency,
            gross_minor=trade['gross_minor'], commission_minor=trade['commission_minor'],
            premium_minor=trade['premium_minor'], tax_minor=trade['tax_minor'], net_minor=trade['net_minor'],
            market_value_minor=None, trade_date=trade['trade_date'],
            trade_date_source='printed' if trade['trade_date'] else 'absent', execution_time=None,
            settlement_date=trade['settlement_date'], as_of_date=None, term_days=trade['term_days'],
            rate_printed=trade['rate_printed'], proof_class=row.proof_class if row.proof_class != 'p4' else 'p3',
            extraction_layer=row.extraction_layer, reader=reading.READER_MOVEMENTS, account_id=row.account_id,
            statement_period_id=row.statement_period_id, cash_transaction_id=row.id)
        provenance = dict(
            locator=(row.provenance or {}).get('locator'), printed_text=trade['printed_text'], basis=trade['basis'],
            source=dict(page=original.get('page_number'), table=original.get('table_index'),
                        row=original.get('row_index')),
            folio=trade['folio'], coupon=trade['coupon'], trade_day_printed=trade['trade_day_printed'],
            settlement_day_printed=trade['settlement_day_printed'], cash_direction=trade['cash_direction'],
            cash_leg=dict(transaction_id=str(row.id), ref_id=row.ref_id, amount_minor=row.amount_minor,
                          direction=getattr(row.direction, 'value', row.direction)),
            checks=trade['checks'], not_printed=trade['not_printed'], not_read=trade['not_read'],
            unreadable=trade['unreadable'], reading_origin=_reading_origin(row),
            source_document_id=str(document.id))
        found.append((_cash_key(row), values, provenance))
    period = session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id == document.id).order_by(
        FinancialStatementPeriod.period_end)).first()
    for holding in reading.holdings_from_tables(_page_tables(session, document), period_end=period and period.period_end):
        currency = holding.get('currency') or (next(iter(currencies)) if len(currencies) == 1 else None)
        values = dict(
            row_kind='holding', operation=None, side=None, holding_kind=holding['holding_kind'],
            instrument=holding['instrument'], issuer=holding['issuer'], series=holding['series'], isin=None,
            quantity_printed=holding['quantity_printed'], quantity=holding['quantity'],
            price_printed=holding['price_printed'], price=holding['price'], currency=currency,
            gross_minor=None, commission_minor=None, premium_minor=None, tax_minor=None, net_minor=None,
            market_value_minor=holding['market_value_minor'], trade_date=holding.get('trade_date'),
            trade_date_source='printed' if holding.get('trade_date') else 'absent', execution_time=None,
            settlement_date=holding.get('settlement_date'), as_of_date=holding.get('as_of'),
            term_days=holding.get('term_days'), rate_printed=holding.get('rate_printed'),
            proof_class=document.proof_class if document.proof_class != 'p4' else 'p3',
            extraction_layer=1, reader=reading.READER_HOLDINGS, account_id=period and period.account_id,
            statement_period_id=period and period.id, cash_transaction_id=None)
        provenance = dict(
            locator=holding.get('locator'), printed_text=holding['printed_text'], basis='printed_line',
            source=dict(page=holding['page_number'], table=holding['table_index'], row=holding['row_index']),
            folio=holding.get('folio'), coupon=holding.get('coupon'), previous=holding.get('previous'),
            checks={'proof': holding['proof']}, not_printed=['execution_time', 'isin'],
            not_read=holding.get('not_read') or [], unread=holding.get('unread'),
            unreadable=[], reading_origin=None, source_document_id=str(document.id),
            currency_basis='printed' if holding.get('currency') else ('statement' if currency else 'absent'))
        key = f"holding:{holding['page_number']}:{holding['table_index']}:{holding['row_index']}"
        found.append((key, values, provenance))
    return found


def _page_tables(session, document) -> list:
    return _file_tables(session, document.case_id, document.evidence_file_id)


def _file_tables(session, case_id, evidence_file_id) -> list:
    from postgres.models.evidence import EvidenceTableGeometry
    from services.financial.candidate_sources import read_candidate_source
    pages = session.execute(select(EvidenceTableGeometry.page_number, EvidenceTableGeometry.payload).where(
        EvidenceTableGeometry.evidence_file_id == evidence_file_id).order_by(
        EvidenceTableGeometry.page_number)).all()
    sources = []
    for number, payload in pages:
        for index in range(len(payload or [])):
            try:
                sources.append(read_candidate_source(session, case_id=case_id,
                                                     evidence_file_id=evidence_file_id,
                                                     page_number=number, table_index=index))
            except Exception as exc:  # a table the reader refuses is not read; say so in the log
                log.info('brokerage holdings: page %s table %s of %s not read: %s', number, index,
                         evidence_file_id, exc)
    return sources


def _carry(old: FinancialSecurityRow, values: dict):
    """The corrections and confirmation of ``old`` that still hold against the new reading ``values``."""
    corrections = {field: entry for field, entry in (old.corrections or {}).items()
                   if _plain(values.get(field)) == entry.get('read')}
    confirmation = (old.confirmation if old.confirmation and reading_digest(values) ==
                    old.confirmation.get('reading_digest') else None)
    return corrections, confirmation


def reading_digest(row_or_values) -> str:
    """What a confirmation is held against: the reading's values, not the row's identity."""
    get = row_or_values.get if isinstance(row_or_values, dict) else (lambda k: getattr(row_or_values, k))
    return _digest({k: get(k) for k in _COLUMNS if k not in ('cash_transaction_id', 'statement_period_id')})


def sync_document(session, document_id, *, force: bool = False) -> dict:
    """Make the document's security rows match its current reading. Returns counts; writes no cash row."""
    counts = dict(document_id=str(document_id), added=0, superseded=0, unchanged=0, trades=0, holdings=0,
                  lines_not_read=0, carried_corrections=0, dropped_corrections=0, brokerage=False)
    if not enabled() and not force:
        return counts
    document_id = document_id if isinstance(document_id, uuid.UUID) else uuid.UUID(str(document_id))
    document = session.get(FinancialSourceDocument, document_id)
    if document is None or not is_brokerage_document(session, document):
        return counts
    counts['brokerage'] = True
    wanted = {}
    for key, values, provenance in (desired_rows(session, document) if document.status == 'admitted' else []):
        wanted[key] = (values, provenance)
    return _apply(session, case_id=document.case_id, evidence_file_id=document.evidence_file_id,
                  source_document_id=document.id, readers=READERS, wanted=wanted, counts=counts)


def _apply(session, *, case_id, evidence_file_id, source_document_id, readers, wanted, counts):
    """Make the admitted rows of one file (for ``readers``) equal ``wanted``: unchanged rows stay, changed readings
    supersede, lines no longer read are superseded. Never deletes."""
    existing = {row.reading_key: row for row in session.scalars(select(FinancialSecurityRow).where(
        FinancialSecurityRow.evidence_file_id == evidence_file_id,
        # One file can print several statements (source documents): each keeps its own rows.
        (FinancialSecurityRow.source_document_id == source_document_id) if source_document_id is not None
        else FinancialSecurityRow.source_document_id.is_(None),
        FinancialSecurityRow.reader.in_(readers), FinancialSecurityRow.ledger_status == 'admitted'))}
    for key, (values, provenance) in wanted.items():
        # A printed line kept as not read is counted on its own, not as a trade or holding read.
        counts['lines_not_read' if provenance.get('unread') else
               'trades' if values['row_kind'] == 'trade' else 'holdings'] += 1
        digest = _digest(dict(values, provenance=provenance))
        old = existing.pop(key, None)
        if old is not None and old.content_hash == digest:
            counts['unchanged'] += 1
            continue
        corrections, confirmation = _carry(old, values) if old is not None else ({}, None)
        if old is not None:
            counts['carried_corrections'] += len(corrections)
            counts['dropped_corrections'] += len(old.corrections or {}) - len(corrections)
        row = FinancialSecurityRow(id=uuid.uuid4(), case_id=case_id, evidence_file_id=evidence_file_id,
                                   source_document_id=source_document_id, reading_key=key, ledger_status='admitted',
                                   provenance=_plain(provenance), corrections=corrections, confirmation=confirmation,
                                   content_hash=digest, **values)
        if old is not None:
            old.ledger_status = 'superseded'
            old.superseded_by_id = row.id
            counts['superseded'] += 1
            session.flush()
        session.add(row)
        counts['added'] += 1
    for old in existing.values():  # the line no longer reads (its cash leg was set aside, the file removed)
        old.ledger_status = 'superseded'
        counts['superseded'] += 1
    session.flush()
    return counts


def canonical_copy(session, file) -> bool:
    """The one file of a case whose fund-statement rows count, among copies with the same bytes: the earliest
    uploaded file not marked a duplicate. Other copies get no rows (their rows would count the same trades twice)."""
    from postgres.models.evidence import EvidenceFile
    if file.is_duplicate:
        return False
    first = session.execute(select(EvidenceFile.id).where(
        EvidenceFile.case_id == file.case_id, EvidenceFile.sha256 == file.sha256,
        EvidenceFile.is_duplicate.is_(False)).order_by(EvidenceFile.created_at, EvidenceFile.id).limit(1)).scalar()
    return first == file.id


def _text_content(session, evidence_file_id) -> str:
    from postgres.models.evidence import EvidenceDocumentText
    text = session.get(EvidenceDocumentText, evidence_file_id)
    return (text.content or '') if text is not None else ''


def fund_rows(session, file) -> list:
    """[(reading_key, values, provenance)] of an investment-fund statement file (``brokerage_reading``)."""
    sources = _file_tables(session, file.case_id, file.id)
    content = _text_content(session, file.id)
    texts = [t for s in sources for _, _, t in reading._table_rows(s)]
    if not reading.is_fund_statement(texts + [content[:4000]]):
        return []
    read = reading.fund_statement_rows(sources, extra_texts=[content] if content else [])
    found = []
    for item in read['trades'] + read['holdings'] + read['not_read']:
        kind = item['row_kind']
        values = dict(
            row_kind=kind, operation=item.get('operation'), side=item.get('side'), holding_kind=item.get('holding_kind'),
            instrument=item['instrument'], issuer=item['issuer'], series=item['series'], isin=None,
            quantity_printed=item['quantity_printed'], quantity=item['quantity'], price_printed=item['price_printed'],
            price=item['price'], currency=item.get('currency'), gross_minor=item.get('gross_minor'),
            commission_minor=item.get('commission_minor'), premium_minor=item.get('premium_minor'),
            tax_minor=item.get('tax_minor'), net_minor=item.get('net_minor'),
            market_value_minor=item.get('market_value_minor'), trade_date=item.get('trade_date'),
            trade_date_source='printed' if item.get('trade_date') else 'absent', execution_time=None,
            settlement_date=item.get('settlement_date'), as_of_date=item.get('as_of'), term_days=None,
            rate_printed=None, proof_class='p3', extraction_layer=1, reader=reading.READER_FUNDS, account_id=None,
            statement_period_id=None, cash_transaction_id=None)
        provenance = dict(
            locator=item.get('locator'), printed_text=item['printed_text'], basis='printed_line',
            source=dict(page=item['page_number'], table=item['table_index'], row=item['row_index']),
            checks=item.get('checks') or {'proof': item.get('proof')}, not_printed=item.get('not_printed') or
            ['execution_time', 'isin'], not_read=item.get('not_read') or [], unread=item.get('unread'),
            unreadable=[], reading_origin=None,
            previous=item.get('previous'), balance_after=item.get('balance_after'),
            period=[d.isoformat() for d in read['period']] if read['period'] else None,
            outside_money_ledger='An investment-fund statement: set aside from the money ledger (no cash lines); '
                                 'its unit movements and positions are read here.')
        prefix = 'fund' if kind == 'trade' else 'fundpos'
        found.append((f"{prefix}:{item['page_number']}:{item['table_index']}:{item['row_index']}", values, provenance))
    return found


def sync_fund_statement(session, evidence_file_id, *, force: bool = False) -> dict:
    """Make an investment-fund statement file's trades and holdings match its reading. A copy of another file of the
    case (same bytes) gets none. Writes no cash row (a fund statement has none in the money ledger)."""
    from postgres.models.evidence import EvidenceFile
    counts = dict(evidence_file_id=str(evidence_file_id), added=0, superseded=0, unchanged=0, trades=0,
                  holdings=0, lines_not_read=0, carried_corrections=0, dropped_corrections=0, fund_statement=False,
                  copy=False)
    if not enabled() and not force:
        return counts
    file_id = evidence_file_id if isinstance(evidence_file_id, uuid.UUID) else uuid.UUID(str(evidence_file_id))
    file = session.get(EvidenceFile, file_id)
    if file is None:
        return counts
    wanted = {}
    if canonical_copy(session, file):
        for key, values, provenance in fund_rows(session, file):
            wanted[key] = (values, provenance)
    else:
        counts['copy'] = True
    counts['fund_statement'] = bool(wanted)
    return _apply(session, case_id=file.case_id, evidence_file_id=file.id, source_document_id=None,
                  readers=FUND_READERS, wanted=wanted, counts=counts)


def after_fund_statement_assessed(session, evidence_file_id) -> None:
    """Called where a fund statement is set aside or put back (not_payment_statements). Never stops that write."""
    if not enabled() or evidence_file_id is None:
        return
    try:
        if session.get_bind().dialect.name == 'postgresql':
            with session.begin_nested():
                sync_fund_statement(session, evidence_file_id)
        else:
            sync_fund_statement(session, evidence_file_id)
    except Exception:
        log.exception('fund statement rows not updated for file %s', evidence_file_id)


def after_cash_rows_changed(session, document_id) -> None:
    """Called by every writer of a statement's cash rows, inside its transaction. A failure here is logged and never
    stops the cash write: the security rows are re-read by the next sync or the backfill."""
    if not enabled():
        return
    if document_id is None:
        return
    try:
        if session.get_bind().dialect.name == 'postgresql':
            with session.begin_nested():
                sync_document(session, document_id)
        else:
            sync_document(session, document_id)
    except Exception:
        log.exception('brokerage security rows not updated for document %s', document_id)


# ---------------------------------------------------------------------------------------------------------------
# Reading the rows (screen and agent), and a person's corrections and confirmations
# ---------------------------------------------------------------------------------------------------------------

class SecurityRowError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


MAX_PAGE = 200
SORTS = ('date', 'instrument', 'amount')


def _effective(row, field):
    entry = (row.corrections or {}).get(field)
    return entry['value'] if entry else _plain(getattr(row, field))


def label(row) -> dict:
    """Who the reading is: the reader's (a template over printed cells), or a model's until a person confirms it."""
    origin = (row.provenance or {}).get('reading_origin')
    if row.confirmation:
        return dict(kind='confirmed', text=f"Confirmed by {row.confirmation.get('by', {}).get('name') or 'a person'}")
    if origin:
        return dict(kind='model', text=f"Read by {origin.get('model') or 'a model'} · not confirmed",
                    model=origin.get('model'), for_name=(origin.get('for') or {}).get('name'))
    return dict(kind='reader', text='Read from the printed line')


def to_json(row, *, account_names=None, file_names=None) -> dict:
    provenance = row.provenance or {}
    fields = {field: _effective(row, field) for field in CORRECTABLE}
    return dict(
        id=str(row.id), row_kind=row.row_kind, side=row.side, holding_kind=row.holding_kind, operation=row.operation,
        instrument=fields['instrument'], issuer=row.issuer, series=row.series, isin=fields['isin'],
        quantity=fields['quantity'], quantity_printed=row.quantity_printed, price=fields['price'],
        price_printed=row.price_printed, currency=row.currency,
        gross_minor=fields['gross_minor'], commission_minor=fields['commission_minor'],
        premium_minor=fields['premium_minor'], tax_minor=fields['tax_minor'], net_minor=fields['net_minor'],
        market_value_minor=fields['market_value_minor'], trade_date=fields['trade_date'],
        trade_date_source=row.trade_date_source, execution_time=fields['execution_time'],
        settlement_date=fields['settlement_date'], as_of_date=_plain(row.as_of_date), term_days=row.term_days,
        rate_printed=row.rate_printed, proof_class=row.proof_class, extraction_layer=row.extraction_layer,
        account_id=_plain(row.account_id), account=(account_names or {}).get(row.account_id),
        evidence_file_id=str(row.evidence_file_id), file=(file_names or {}).get(row.evidence_file_id),
        source_document_id=_plain(row.source_document_id), cash_transaction_id=_plain(row.cash_transaction_id),
        citation=dict(file_id=str(row.evidence_file_id), page=(provenance.get('source') or {}).get('page'),
                      locator=provenance.get('locator'), printed_text=provenance.get('printed_text'),
                      cash_leg=provenance.get('cash_leg')),
        checks=provenance.get('checks') or {}, not_printed=provenance.get('not_printed') or [],
        not_read=provenance.get('not_read') or [], unread=provenance.get('unread'),
        unreadable=provenance.get('unreadable') or [],
        corrections={field: dict(entry) for field, entry in (row.corrections or {}).items()},
        confirmation=row.confirmation, origin=label(row), reader=row.reader)


def query_rows(session, *, case_id, row_kind='trade', instrument=None, account_id=None, date_from=None,
               date_to=None, side=None, page=1, page_size=50, sort='date'):
    """One page of a case's admitted security rows, with the total. A trade whose cash leg is no longer in the money
    ledger (set aside, superseded and not yet re-read) is not shown: the counts say how many."""
    from sqlalchemy import and_, func, or_
    from postgres.models.evidence import EvidenceFile
    if row_kind not in ROW_KINDS_QUERY:
        raise SecurityRowError('row_kind is trade or holding.')
    if sort not in SORTS:
        raise SecurityRowError('sort is date, instrument or amount.')
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 50), MAX_PAGE))
    cash = FinancialTransaction
    base = select(FinancialSecurityRow).outerjoin(cash, cash.id == FinancialSecurityRow.cash_transaction_id).where(
        FinancialSecurityRow.case_id == case_id, FinancialSecurityRow.row_kind == row_kind,
        FinancialSecurityRow.ledger_status == 'admitted')
    hidden = session.scalar(select(func.count()).select_from(base.where(
        FinancialSecurityRow.cash_transaction_id.is_not(None),
        or_(cash.id.is_(None), cash.ledger_status != 'admitted')).subquery()))
    query = base.where(or_(FinancialSecurityRow.cash_transaction_id.is_(None), cash.ledger_status == 'admitted'))
    if instrument:
        needle = f"%{str(instrument).strip().upper()}%"
        query = query.where(func.upper(FinancialSecurityRow.instrument).like(needle))
    if account_id:
        query = query.where(FinancialSecurityRow.account_id == account_id)
    if side:
        query = query.where(FinancialSecurityRow.side == side)
    day = func.coalesce(FinancialSecurityRow.trade_date, FinancialSecurityRow.settlement_date,
                        FinancialSecurityRow.as_of_date)
    if date_from:
        query = query.where(day >= date_from)
    if date_to:
        query = query.where(day <= date_to)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    order = {'date': (day, FinancialSecurityRow.instrument, FinancialSecurityRow.reading_key),
             'instrument': (FinancialSecurityRow.instrument, day, FinancialSecurityRow.reading_key),
             'amount': (func.coalesce(FinancialSecurityRow.net_minor, FinancialSecurityRow.market_value_minor).desc(),
                        FinancialSecurityRow.reading_key)}[sort]
    rows = session.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    accounts = {a.id: a for a in session.scalars(select(FinancialAccount).where(
        FinancialAccount.id.in_({r.account_id for r in rows if r.account_id})))} if rows else {}
    account_names = {k: ' '.join(x for x in (a.institution_name, a.identifier_as_printed) if x) for k, a in accounts.items()}
    files = dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.id.in_({r.evidence_file_id for r in rows}))).all()) if rows else {}
    items = [to_json(r, account_names=account_names, file_names=files) for r in rows]
    revision = session.scalar(select(func.max(FinancialSecurityRow.updated_at)).where(
        FinancialSecurityRow.case_id == case_id))
    return dict(row_kind=row_kind, total=total, returned=len(items), page=page, page_size=page_size,
                next_page=page + 1 if page * page_size < total else None, items=items,
                not_shown_cash_leg_not_in_ledger=hidden or 0,
                revision=revision.isoformat() if revision else None)


ROW_KINDS_QUERY = ('trade', 'holding')


def _parse(field, value):
    if value is None or value == '':
        return None
    if field in ('quantity', 'price'):
        try:
            return str(Decimal(str(value).replace(',', '')))
        except Exception:
            raise SecurityRowError(f'{field} must be a number.')
    if field in ('trade_date', 'settlement_date'):
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise SecurityRowError(f'{field} must be a date (YYYY-MM-DD).')
    if field.endswith('_minor'):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise SecurityRowError(f'{field} must be a whole number of minor units.')
    text_value = ' '.join(str(value).split())
    if field == 'isin' and text_value and not __import__('re').fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', text_value):
        raise SecurityRowError('An ISIN is 12 characters: two letters, nine letters or digits, one check digit.')
    return text_value[:128]


def _row_for_write(session, case_id, row_id):
    row = session.get(FinancialSecurityRow, row_id if isinstance(row_id, uuid.UUID) else uuid.UUID(str(row_id)))
    if row is None or row.case_id != case_id:
        raise SecurityRowError('Not in this case.', 404)
    if row.ledger_status != 'admitted':
        raise SecurityRowError('This reading was replaced by a newer one; open the current row.', 409)
    return row


def correct_row(session, *, case_id, row_id, field, value, reason, actor, commit=True) -> dict:
    """A person corrects one value. The value as read stays on the row and in the decision; the corrected value is
    the one every view and the agent use. A model may not correct (its work is a proposal, never a correction)."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services.financial.decisions import record
    from services.financial.model_work import is_model
    if is_model(actor):
        raise SecurityRowError('A model reading is recorded as a proposal for a person, never as a correction.', 403)
    if field not in CORRECTABLE:
        raise SecurityRowError(f"{field} cannot be corrected here. Correctable: {', '.join(CORRECTABLE)}.")
    reason = ' '.join(str(reason or '').split())
    if not reason:
        raise SecurityRowError('Say why the value is corrected.')
    row = _row_for_write(session, case_id, row_id)
    read_value = _plain(getattr(row, field))
    new_value = _parse(field, value)
    if new_value == _effective(row, field):
        raise SecurityRowError('That is already the value shown.', 409)
    corrections = dict(row.corrections or {})
    previous = corrections.get(field)
    event = record(session, case_id=case_id, subject=row, subject_type=AdjudicationSubject.security_row,
                   decision=AdjudicationDecision.correct_security_row, reason=reason, actor=actor,
                   before=dict(field=field, read=read_value, value=_effective(row, field)),
                   after=dict(field=field, read=read_value, value=new_value))
    if new_value == read_value:
        corrections.pop(field, None)  # corrected back to the value as read: the reading stands
    else:
        corrections[field] = dict(read=read_value, value=new_value, reason=reason,
                                  by=dict(name=actor.name, email=actor.email,
                                          user_id=str(actor.user_id) if actor.user_id else None),
                                  at=datetime.now(timezone.utc).isoformat(), decision_id=str(event.id),
                                  previous=previous)
    row.corrections = corrections
    session.flush()
    result = to_json(row)
    if commit:
        session.commit()
    return result


def confirm_row(session, *, case_id, row_id, reason, actor, commit=True) -> dict:
    """A person confirms a reading (a model's reading then shows as confirmed by them)."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services.financial.decisions import record
    from services.financial.model_work import is_model
    if is_model(actor):
        raise SecurityRowError('A model cannot confirm a reading; a person does.', 403)
    row = _row_for_write(session, case_id, row_id)
    if row.confirmation:
        raise SecurityRowError('Already confirmed.', 409)
    reason = ' '.join(str(reason or '').split()) or 'Checked against the printed line.'
    event = record(session, case_id=case_id, subject=row, subject_type=AdjudicationSubject.security_row,
                   decision=AdjudicationDecision.confirm_security_row, reason=reason, actor=actor,
                   before=dict(origin=label(row)['kind'], confirmed=False),
                   after=dict(origin='confirmed', confirmed=True), reason_kind='typed')
    row.confirmation = dict(by=dict(name=actor.name, email=actor.email,
                                    user_id=str(actor.user_id) if actor.user_id else None),
                            at=datetime.now(timezone.utc).isoformat(), reason=reason, decision_id=str(event.id),
                            reading_digest=reading_digest(row))
    session.flush()
    result = to_json(row)
    if commit:
        session.commit()
    return result
