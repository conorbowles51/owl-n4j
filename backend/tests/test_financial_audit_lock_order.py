"""The import writer takes the case audit-append lock before any row lock."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from services.financial.audit_chain import lock_case_audit_chain


def session_on(dialect):
    session = MagicMock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    return session


def test_postgres_takes_the_trigger_lock_key():
    case_id = uuid4()
    session = session_on('postgresql')
    lock_case_audit_chain(session, case_id)
    statement, params = session.execute.call_args.args
    # Same key as append_financial_audit_event, or the order buys nothing.
    assert "pg_advisory_xact_lock(hashtextextended('loupe.financial.audit:' ||" in str(statement)
    assert params == dict(case_id=str(case_id))


def test_sqlite_has_no_advisory_lock():
    session = session_on('sqlite')
    lock_case_audit_chain(session, uuid4())
    session.execute.assert_not_called()
