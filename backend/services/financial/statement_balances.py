"""Read-only running-balance diagnostics for one same-case statement period."""
from datetime import datetime, timezone
from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.correction_balances import current_running_balances
from services.financial.money import MoneyError
from services.financial.periods import PeriodError
from services.financial.statement_checks import StatementCheckError


def read_statement_running_balances(session, *, case_id, period_id):
    period = session.get(FinancialStatementPeriod, period_id)
    if period is None or period.case_id != case_id:
        raise StatementCheckError('Statement period not found in this case.')
    account = session.get(FinancialAccount, period.account_id)
    document = session.get(FinancialSourceDocument, period.source_document_id)
    if account is None or document is None or account.case_id != case_id or document.case_id != case_id:
        raise StatementCheckError('Statement ownership is inconsistent.')
    if session.scalar(select(FinancialTransaction.id).where(FinancialTransaction.statement_period_id == period_id,
        or_(FinancialTransaction.case_id != case_id, FinancialTransaction.account_id != account.id,
            FinancialTransaction.source_document_id != document.id)).limit(1)) is not None:
        raise StatementCheckError('Transaction ownership is inconsistent.')
    # Retain excluded and historical rows so ambiguity and interrupted chains remain visible.
    rows = list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.statement_period_id == period_id)
        .order_by(FinancialTransaction.id).limit(1001)))
    try:
        comparison = current_running_balances(period, rows)
    except (MoneyError, PeriodError) as exc:
        comparison = dict(available=False, reason=str(exc), interpretations=[])
    return dict(case_id=str(case_id), period_id=str(period.id), source_document_id=str(document.id),
        source_status=document.status, proof_class=document.proof_class, comparison=comparison, applied=False)


def capture_statement_running_balances(engine, *, case_id, period_id):
    if not isinstance(engine, Engine) or engine.dialect.name != 'postgresql':
        raise StatementCheckError('Consistent running-balance checks require a PostgreSQL engine connection.')
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            with Session(bind=connection, autoflush=False) as session:
                result = read_statement_running_balances(session, case_id=case_id, period_id=period_id)
    return {**result, 'checked_at': datetime.now(timezone.utc).isoformat()}
