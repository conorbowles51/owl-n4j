"""Current statement balance checks, without changing stored findings or admission."""
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from postgres.models.financial import (
    FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
)
from postgres.models.evidence import EvidenceFile
from services.financial.statement_delta_hints import statement_delta_hints
from services.financial.printed_totals import compare_printed_totals, retained_total_controls
from services.financial.ledger_source import LedgerSourceError
from services.financial.money import MoneyError
from services.financial.periods import PeriodError, read_opening, read_closing
from services.financial.reconcile import ReconciliationError, evaluate_identity, total_transactions


class StatementCheckError(ValueError):
    pass


def list_statement_checks(session, *, case_id, offset=0, limit=25, include_native=False, resolve_path=None, account_id=None):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 25:
        raise StatementCheckError('Invalid statement check page limits.')
    period_query = select(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id == case_id)
    if account_id is not None:
        account = session.get(FinancialAccount, account_id)
        if account is None or account.case_id != case_id:
            raise StatementCheckError('Account not found in this case.')
        period_query = period_query.where(FinancialStatementPeriod.account_id == account_id)
    periods = list(session.scalars(period_query
        .order_by(FinancialStatementPeriod.period_start.asc().nullslast(), FinancialStatementPeriod.id)
        .offset(offset).limit(limit + 1)))
    # Count zero readings for the same admitted population, in one bounded
    # query for this page. They remain source readings, not nonzero payments.
    zero_counts = dict(session.execute(select(
        FinancialTransaction.statement_period_id, func.count())
        .where(FinancialTransaction.statement_period_id.in_([p.id for p in periods[:limit]]),
               FinancialTransaction.ledger_status == 'admitted',
               FinancialTransaction.amount_minor == 0)
        .group_by(FinancialTransaction.statement_period_id)).all()) if periods else {}
    items = []
    native_by_document = {}
    for period in periods[:limit]:
        account = session.get(FinancialAccount, period.account_id)
        document = session.get(FinancialSourceDocument, period.source_document_id)
        if account is None or document is None or account.case_id != case_id or document.case_id != case_id:
            raise StatementCheckError('Statement ownership is inconsistent; no check was returned.')
        evidence = session.get(EvidenceFile, document.evidence_file_id) if document.evidence_file_id else None
        if document.evidence_file_id and (evidence is None or evidence.case_id != case_id):
            raise StatementCheckError('Statement file ownership is inconsistent; no check was returned.')
        foreign_row = session.scalar(select(FinancialTransaction.id).where(
            FinancialTransaction.statement_period_id == period.id,
            or_(FinancialTransaction.case_id != case_id,
                FinancialTransaction.account_id != account.id,
                FinancialTransaction.source_document_id != document.id)).limit(1))
        if foreign_row is not None:
            raise StatementCheckError('Transaction ownership is inconsistent; no check was returned.')
        item = dict(period_id=str(period.id), account_id=str(account.id),
            account_label=(account.metadata_ or {}).get('display_label') or account.identifier_as_printed or account.holder_name or 'Unidentified account',
            source_document_id=str(document.id), source_status=document.status,
            proof_class=document.proof_class, currency=period.currency,
            filename=evidence.original_filename if evidence else None, balance_convention=None,
            start=period.period_start.isoformat() if period.period_start else None,
            end=period.period_end.isoformat() if period.period_end else None,
            opening_source=period.opening_balance_source, closing_source=period.closing_balance_source,
            recorded_status=period.reconciliation_status,
            recorded_at=period.reconciled_at.isoformat() if period.reconciled_at else None,
            status='refused', reason=None, amounts=None, counted_rows=None, excluded_rows=None,
            independent=None, zero_amount_rows=None, printed_totals=None, printed_totals_error=None, delta_hints=None)
        try:
            outcome = evaluate_identity(opening=read_opening(period), closing=read_closing(period),
                totals=total_transactions(session, period_id=period.id, currency=period.currency), currency=period.currency)
            item.update(status=outcome.status.value, reason=outcome.unavailable_reason,
                amounts={name: None if money is None else str(money.minor_units) for name, money in (
                    ('opening', outcome.opening), ('credits', outcome.totals.credits),
                    ('debits', outcome.totals.debits), ('computed_closing', outcome.computed_closing),
                    ('closing', outcome.printed_closing), ('difference', outcome.delta))},
                counted_rows=outcome.totals.counted, excluded_rows=outcome.totals.excluded_count,
                independent=outcome.independent, zero_amount_rows=zero_counts.get(period.id, 0))
            item["delta_hints"] = statement_delta_hints(session, period, outcome)
        except (MoneyError, PeriodError, ReconciliationError) as exc:
            item['reason'] = str(exc)
        if item['amounts'] is not None:
            try:
                controls = retained_total_controls(session, period, document)
                # The saved review explicitly records how card balances are
                # signed. Never infer this from the bank name or account type.
                item['balance_convention'] = controls['balance_convention'] if controls else None
                item['printed_totals'] = compare_printed_totals(controls,
                    credits=int(item['amounts']['credits']), debits=int(item['amounts']['debits']))
            except (LedgerSourceError, ValueError) as exc:
                item['printed_totals_error'] = str(exc)
        if include_native and document.extraction_layer == 0:
            if document.id not in native_by_document:
                from services.financial.correction_native import correction_native_controls
                rows = list(session.scalars(select(FinancialTransaction).where(
                    FinancialTransaction.source_document_id == document.id).order_by(FinancialTransaction.row_index, FinancialTransaction.id).limit(2001)))
                current = next((r for r in rows if not r.superseded_by_id and r.ledger_status != 'superseded'), None)
                if current is None:
                    native = dict(available=False, reason='No current native readings are retained.')
                else:
                    native = correction_native_controls(session,document,rows,
                        transaction_id=current.id,amount_minor=current.amount_minor,direction=current.direction,
                        resolve_path=resolve_path,lock_source=False)
                    if native and native.get('available'):
                        native.pop('proposed')
                        native['limitation'] += ' These are whole-source controls, including other accounts or periods in the same native file. Held current readings remain in source-control arithmetic; this is not an admitted-ledger total.'
                native_by_document[document.id] = native
            item['native_controls'] = native_by_document[document.id]
        items.append(item)
    return dict(case_id=str(case_id), account_id=str(account_id) if account_id else None, offset=offset, has_more=len(periods) > limit, items=items,
        applied=False, native_controls_requested=include_native, limitation='Current opening + admitted row credits − admitted row debits compared with the recorded closing balance. This does not check every printed control, prove complete extraction, or change proof class or admission. Source exclusions still apply.')


def capture_statement_checks(engine, *, case_id, offset=0, include_native=False, resolve_path=None, account_id=None):
    """Balances and transaction totals come from the same read-only database snapshot."""
    if not isinstance(engine, Engine) or engine.dialect.name != 'postgresql':
        raise StatementCheckError('Consistent statement checks require a PostgreSQL engine connection.')
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            with Session(bind=connection, autoflush=False) as session:
                result = list_statement_checks(session, case_id=case_id, offset=offset, include_native=include_native, resolve_path=resolve_path, account_id=account_id)
    return {**result, 'checked_at': datetime.now(timezone.utc).isoformat()}
