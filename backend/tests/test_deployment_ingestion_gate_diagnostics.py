"""Release logs identify active work without exposing the evidence it processes."""
import importlib.util
import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, text


spec = importlib.util.spec_from_file_location(
    'ingestion_gate_diagnostics', Path(__file__).resolve().parents[2] / 'deploy/check_ingestion_idle.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def identifier(value):
    return str(UUID(int=value))


CASE_ID = identifier(100)
CREATED = '2026-09-25T09:00:00'
UPDATED = '2026-09-25T09:30:00'
PRIVATE = 'private-filename-content-or-credential'


@pytest.fixture
def active_engine():
    engine = create_engine('sqlite://')
    tables = {
        'jobs': 'id TEXT, case_id TEXT, batch_id TEXT, status TEXT, paused BOOLEAN',
        'financial_import_batches': 'id TEXT, case_id TEXT, status TEXT, worker_token TEXT, lease_until TEXT',
        'financial_import_batch_items': 'id TEXT, batch_id TEXT, status TEXT',
        'financial_recovery_runs': 'id TEXT, case_id TEXT, status TEXT',
        'financial_recovery_items': 'id TEXT, run_id TEXT, status TEXT',
        'evidence_upload_groups': 'id TEXT, case_id TEXT, status TEXT',
        'evidence_upload_sessions': 'id TEXT, case_id TEXT, group_id TEXT, status TEXT',
    }
    with engine.begin() as db:
        for table, columns in tables.items():
            db.execute(text(f'CREATE TABLE {table} ({columns}, created_at TEXT, updated_at TEXT, filename TEXT, error_message TEXT)'))

        def add(table, **values):
            values.update(created_at=CREATED, updated_at=UPDATED, filename=PRIVATE, error_message=PRIVATE)
            columns = ', '.join(values)
            parameters = ', '.join(':' + name for name in values)
            db.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({parameters})'), values)

        add('jobs', id=identifier(1), case_id=CASE_ID, batch_id=identifier(10), status='extracting_text', paused=False)
        add('jobs', id=identifier(11), case_id=CASE_ID, status='pending', paused=True)
        add('jobs', id=identifier(12), case_id=CASE_ID, status='completed', paused=False)
        add('financial_import_batches', id=identifier(2), case_id=CASE_ID, status='preparing',
            worker_token=PRIVATE, lease_until='2099-01-01T00:00:00')
        add('financial_import_batches', id=identifier(21), case_id=CASE_ID, status='preparing',
            worker_token=PRIVATE, lease_until='2000-01-01T00:00:00')
        add('financial_import_batches', id=identifier(22), case_id=CASE_ID, status='preparing',
            worker_token=None, lease_until='2099-01-01T00:00:00')
        add('financial_import_batch_items', id=identifier(3), batch_id=identifier(2), status='pending_import')
        add('financial_import_batch_items', id=identifier(31), batch_id=identifier(2), status='attention')
        add('financial_recovery_runs', id=identifier(40), case_id=CASE_ID, status='running')
        add('financial_recovery_runs', id=identifier(41), case_id=CASE_ID, status='paused')
        add('financial_recovery_items', id=identifier(4), run_id=identifier(40), status='waiting')
        add('financial_recovery_items', id=identifier(42), run_id=identifier(40), status='review')
        add('financial_recovery_items', id=identifier(43), run_id=identifier(41), status='reading')
        add('evidence_upload_groups', id=identifier(5), case_id=CASE_ID, status='dispatching')
        add('evidence_upload_groups', id=identifier(51), case_id=CASE_ID, status='paused')
        add('evidence_upload_sessions', id=identifier(6), case_id=CASE_ID, group_id=None, status='uploading')
        add('evidence_upload_sessions', id=identifier(61), case_id=CASE_ID, group_id=identifier(5), status='staged')
        add('evidence_upload_sessions', id=identifier(62), case_id=CASE_ID, group_id=identifier(51), status='uploading')
        add('evidence_upload_sessions', id=identifier(63), case_id=CASE_ID, group_id=None, status='completed')
    return engine


@pytest.mark.parametrize('category,record_id,status,extra', [
    ('engine_jobs', 1, 'extracting_text', {'batch_id': identifier(10)}),
    ('financial_batch_leases', 2, 'preparing', {'lease_until': '2099-01-01T00:00:00'}),
    ('pending_financial_imports', 3, 'pending_import', {'batch_id': identifier(2)}),
    ('recovery_items', 4, 'waiting', {'run_id': identifier(40), 'run_status': 'running', 'run_updated_at': UPDATED}),
    ('upload_groups', 5, 'dispatching', {}),
    ('upload_sessions', 6, 'uploading', {'group_id': None}),
])
def test_each_category_has_only_blocking_references(active_engine, category, record_id, status, extra):
    report = gate.active_work_report(active_engine)
    assert report['total'] == gate.active_work(active_engine) == 6
    result = next(item for item in report['categories'] if item['category'] == category)
    assert result['count'] == 1
    assert result['omitted'] == 0
    assert result['records'] == [dict(record_id=identifier(record_id), case_id=CASE_ID,
        status=status, created_at=CREATED, updated_at=UPDATED, **extra)]
    assert PRIVATE not in json.dumps(report)


def test_orphan_pending_import_still_blocks_and_keeps_its_reference(active_engine):
    with active_engine.begin() as db:
        db.execute(text("INSERT INTO financial_import_batch_items (id,batch_id,status) VALUES (:id,:batch,'pending_import')"),
            {'id': identifier(80), 'batch': identifier(81)})
    report = gate.active_work_report(active_engine)
    assert report['total'] == 7
    result = next(item for item in report['categories'] if item['category'] == 'pending_financial_imports')
    orphan = next(item for item in result['records'] if item['record_id'] == identifier(80))
    assert orphan['batch_id'] == identifier(81)
    assert orphan['case_id'] is None


@pytest.mark.parametrize('limit', [0, 3, gate.SAMPLE_LIMIT])
def test_samples_are_bounded_without_reducing_counts_and_oldest_first(limit):
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (id TEXT, status TEXT, updated_at TEXT)'))
        for value in reversed(range(1, 26)):
            db.execute(text("INSERT INTO jobs VALUES (:id, 'pending', :updated)"),
                {'id': identifier(value), 'updated': f'2026-09-25T10:{value:02d}:00'})
    report = gate.active_work_report(engine, sample_limit=limit)
    assert report['total'] == 25
    result = report['categories'][0]
    assert result['count'] == 25
    assert len(result['records']) == limit
    assert result['omitted'] == 25 - limit
    assert [row['record_id'] for row in result['records']] == [identifier(value) for value in range(1, limit + 1)]


@pytest.mark.parametrize('limit', [-1, 11, 1.5, True, '10'])
def test_sample_limit_cannot_be_unbounded(limit):
    with pytest.raises(ValueError, match='sample limit'):
        gate.active_work_report(create_engine('sqlite://'), sample_limit=limit)


def test_legacy_missing_diagnostic_columns_and_group_table_do_not_lose_work():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (status TEXT)'))
        db.execute(text("INSERT INTO jobs VALUES ('processing')"))
        db.execute(text('CREATE TABLE financial_import_batches (worker_token TEXT, lease_until TEXT)'))
        db.execute(text("INSERT INTO financial_import_batches VALUES ('private', '2099-01-01')"))
        db.execute(text('CREATE TABLE evidence_upload_sessions (group_id TEXT, status TEXT)'))
        db.execute(text("INSERT INTO evidence_upload_sessions VALUES (:group, 'staged')"), {'group': identifier(9)})
    report = gate.active_work_report(engine)
    assert report['total'] == gate.active_work(engine) == 3
    for category in report['categories']:
        assert category['count'] == 1
        assert category['records'][0]['record_id'] is None
        assert category['records'][0]['case_id'] is None
        assert category['records'][0]['updated_at'] is None


def test_log_never_includes_arbitrary_legacy_strings_or_exception_messages(monkeypatch, capsys):
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (id TEXT, case_id TEXT, status TEXT, created_at TEXT, updated_at TEXT)'))
        db.execute(text('INSERT INTO jobs VALUES (:private,:private,:private,:private,:private)'), {'private': PRIVATE})
    monkeypatch.setattr(gate, '_get_engine', lambda: engine)
    assert gate.main() == 75
    output = capsys.readouterr().err
    assert 'engine_jobs: 1 blocking records' in output
    assert PRIVATE not in output
    assert output.count('unrecognized') == 5

    def unavailable():
        raise RuntimeError('postgres://user:private-secret@host/database')

    monkeypatch.setattr(gate, '_get_engine', unavailable)
    assert gate.main() == 75
    assert capsys.readouterr().err == 'Release deferred: ingestion state could not be verified (RuntimeError).\n'


def test_cli_reports_category_counts_safe_references_and_no_evidence(active_engine, monkeypatch, capsys):
    monkeypatch.setattr(gate, '_get_engine', lambda: active_engine)
    assert gate.main() == 75
    result = capsys.readouterr()
    assert not result.out
    assert 'Release deferred: 6 ingestion, recovery or upload records are queued or running.' in result.err
    assert 'at most 10 references per category' in result.err
    assert result.err.count('1 blocking records; 1 shown; 0 not shown.') == 6
    assert CASE_ID in result.err
    assert UPDATED in result.err
    assert PRIVATE not in result.err
    assert 'filename' not in result.err
    assert 'worker_token' not in result.err
    assert 'error_message' not in result.err


def test_idle_cli_success_and_broken_schema_fail_closed(monkeypatch, capsys):
    engine = create_engine('sqlite://')
    monkeypatch.setattr(gate, '_get_engine', lambda: engine)
    assert gate.main() == 0
    assert capsys.readouterr().out == 'Ingestion gate: no queued or running ingestion, recovery or uploads.\n'
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (unexpected TEXT)'))
    assert gate.main() == 75
    assert capsys.readouterr().err == 'Release deferred: ingestion state could not be verified (OperationalError).\n'


def test_report_performs_only_reads_and_count_api_does_not_fetch_samples(active_engine):
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(active_engine, 'before_cursor_execute', observe)
    try:
        assert gate.active_work_report(active_engine)['total'] == 6
        assert all(sql.lstrip().upper().startswith(('SELECT', 'PRAGMA')) for sql in statements)
        assert not any(name in sql for sql in statements for name in ('filename', 'error_message'))
        statements.clear()
        assert gate.active_work(active_engine) == 6
        assert not any(' AS record_id' in sql for sql in statements)
    finally:
        event.remove(active_engine, 'before_cursor_execute', observe)
