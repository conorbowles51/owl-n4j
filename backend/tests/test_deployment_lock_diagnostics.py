"""Lock samples explain a deferred release without exposing database contents."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine


spec = importlib.util.spec_from_file_location(
    'ingestion_lock_diagnostics', Path(__file__).resolve().parents[2] / 'deploy/check_ingestion_idle.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
PRIVATE = 'synthetic-private-query-user-address-or-evidence'


class DiagnosticEngine:
    dialect = SimpleNamespace(name='postgresql')

    def __init__(self, waiters=(), blockers=(), error=None):
        self.waiters, self.blockers, self.error = waiters, blockers, error
        self.statements = []
        self.closed = False

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append((sql, parameters))
        if self.error:
            raise self.error
        rows = self.waiters if 'WITH waiting' in sql else self.blockers if 'FROM pg_stat_activity' in sql else []
        return SimpleNamespace(mappings=lambda: iter(rows))


def activity(pid, **changes):
    return dict(pid=pid, state='active', wait_event_type='Lock', wait_event='transactionid',
        transaction_age_seconds=3600, **changes)


def test_lock_sample_and_blocker_details_are_bounded_read_only_and_current_database():
    waiters = [activity(pid, blocking_pids=list(range(100 + pid, 120 + pid)), blocking_pid_count=20)
               for pid in range(1, 15)]
    blockers = [dict(pid=pid, state='idle in transaction', wait_event_type='Client',
        wait_event='ClientRead', transaction_age_seconds=7200, query=PRIVATE, usename=PRIVATE)
        for pid in range(101, 111)]
    engine = DiagnosticEngine(waiters, blockers)
    report = gate.lock_wait_report(engine)
    assert report['status'] == 'available'
    assert len(report['waiters']) == len(report['blockers']) == 10
    assert report['waiter_limit_reached']
    assert all(len(row['blocking_pids']) == 10 and row['blocking_pids_not_shown'] == 10
               for row in report['waiters'])
    assert report['referenced_blocker_summaries_not_shown'] == 9
    assert all(row['activity_visible'] for row in report['blockers'])
    assert report['blockers'][0]['transaction_age_seconds'] == 7200
    assert PRIVATE not in json.dumps(report)
    assert engine.closed
    assert len(engine.statements) == 4
    assert engine.statements[0][0] == "SET LOCAL statement_timeout = '2000ms'"
    assert engine.statements[1][0] == "SET LOCAL lock_timeout = '500ms'"
    for sql, parameters in engine.statements[2:]:
        assert 'a.datid = (SELECT oid FROM pg_database WHERE datname = current_database())' in sql
        assert 'LIMIT :sample_limit' in sql
        assert parameters['sample_limit'] == 10
        assert not any(forbidden in sql.lower() for forbidden in (
            'query', 'usename', 'client_addr', 'application_name', 'evidence', 'password'))
    assert 'pg_blocking_pids(a.pid)' in engine.statements[2][0]
    assert engine.statements[-1][1]['pids'] == list(range(101, 111))


def test_missing_or_prepared_blocker_activity_is_not_fabricated():
    engine = DiagnosticEngine([activity(10, blocking_pids=[0, 99], blocking_pid_count=2)])
    report = gate.lock_wait_report(engine)
    assert report['blockers'] == [dict(pid=0, activity_visible=False), dict(pid=99, activity_visible=False)]
    assert not report['waiter_limit_reached']


def test_activity_projection_rejects_arbitrary_strings_and_extra_columns():
    safe = gate._safe_activity(dict(pid=PRIVATE, state=PRIVATE, wait_event_type=PRIVATE,
        wait_event=PRIVATE, transaction_age_seconds=PRIVATE, query=PRIVATE, usename=PRIVATE))
    assert safe == dict(pid=None, state='unrecognized', wait_event_type='unrecognized',
        wait_event='unrecognized', transaction_age_seconds=None)
    assert PRIVATE not in json.dumps(safe)


def test_no_waiters_does_not_query_blocker_details_or_assert_no_active_work():
    engine = DiagnosticEngine()
    report = gate.lock_wait_report(engine)
    assert report['waiters'] == report['blockers'] == []
    assert len(engine.statements) == 3
    assert report['status'] == 'available'


def test_sqlite_has_no_postgres_query_and_is_not_applicable():
    assert gate.lock_wait_report(create_engine('sqlite://')) == dict(status='not_applicable')


@pytest.mark.parametrize('error', [PermissionError(PRIVATE), TimeoutError(PRIVATE), RuntimeError(PRIVATE)])
def test_optional_diagnostic_failure_keeps_original_blocking_count_and_exit(error, monkeypatch, capsys):
    engine = DiagnosticEngine(error=error)
    monkeypatch.setattr(gate, '_get_engine', lambda: engine)
    monkeypatch.setattr(gate, 'active_work_report', lambda _: dict(total=3, observed_at='synthetic-time',
        sample_limit=10, categories=[dict(category='recovery_items', count=3, records=[], omitted=3)]))
    assert gate.main() == 75
    output = capsys.readouterr()
    assert not output.out
    assert 'Release deferred: 3 ingestion, recovery or upload records' in output.err
    assert 'recovery_items: 3 blocking records; 0 shown; 3 not shown.' in output.err
    assert f'PostgreSQL lock diagnostics unavailable ({type(error).__name__})' in output.err
    assert 'release remains deferred' in output.err
    assert PRIVATE not in output.err
    assert engine.closed


def test_lock_report_cannot_turn_a_busy_gate_into_success(monkeypatch, capsys):
    engine = DiagnosticEngine()
    monkeypatch.setattr(gate, '_get_engine', lambda: engine)
    monkeypatch.setattr(gate, 'active_work_report', lambda _: dict(total=3, observed_at='synthetic-time',
        sample_limit=10, categories=[]))
    assert gate.main() == 75
    assert '0 waiters shown' in capsys.readouterr().err


def test_idle_gate_preserves_existing_success_without_optional_diagnostics(monkeypatch, capsys):
    engine = DiagnosticEngine(error=AssertionError('Idle gate must not query lock metadata'))
    monkeypatch.setattr(gate, '_get_engine', lambda: engine)
    monkeypatch.setattr(gate, 'active_work_report', lambda _: dict(total=0))
    assert gate.main() == 0
    assert engine.statements == []
    assert capsys.readouterr().err == ''
