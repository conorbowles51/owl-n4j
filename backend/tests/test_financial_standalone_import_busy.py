"""A held statement lock answers a single-statement submission promptly."""
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from services.financial import standalone_import_jobs as jobs


class _Busy(Exception):
    sqlstate = '55P03'


class _Session:
    def __init__(self, existing=None, dialect='sqlite'):
        self.existing, self.dialect, self.statements, self.rolled_back = existing, dialect, [], False

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self.dialect))

    def execute(self, statement):
        self.statements.append(str(statement))

    def scalar(self, statement):
        raise OperationalError('SELECT ... FOR UPDATE', {}, _Busy())

    def rollback(self):
        self.rolled_back = True

    def get(self, model, identifier):
        return self.existing


class _Request:
    def model_dump(self, mode='json'):
        return dict(statement_id=None, rows=[])


def test_held_statement_lock_returns_a_definite_busy_answer_without_writing():
    session = _Session(dialect='postgresql')
    result = jobs.queue_statement(session, case_id=uuid4(), evidence_file_id=uuid4(),
        request=_Request(), actor=None)
    assert result['busy'] is True and result['operation'] is None and result['receipt'] is None
    assert 'Nothing was submitted' in result['message']
    assert session.rolled_back
    # The wait is bounded inside the transaction, never on the pooled session.
    assert session.statements == [f"SET LOCAL lock_timeout = '{jobs.QUEUE_LOCK_TIMEOUT}'"]


def test_held_lock_reports_an_already_accepted_identical_submission(monkeypatch):
    operation = object()
    monkeypatch.setattr(jobs, 'operation_view', lambda op: dict(status='in_progress', batch_id='b', outcomes=[]))
    result = jobs.queue_statement(_Session(existing=operation), case_id=uuid4(), evidence_file_id=uuid4(),
        request=_Request(), actor=None)
    assert result['busy'] is False and result['operation']['status'] == 'in_progress'


def test_other_database_errors_are_not_reported_as_busy():
    class _Other(Exception):
        sqlstate = '40001'
    session = _Session()
    session.scalar = lambda statement: (_ for _ in ()).throw(OperationalError('x', {}, _Other()))
    try:
        jobs.queue_statement(session, case_id=uuid4(), evidence_file_id=uuid4(), request=_Request(), actor=None)
    except OperationalError:
        pass
    else:
        raise AssertionError('A non-lock failure must propagate.')
