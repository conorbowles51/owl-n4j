"""One active saved copy per statement: constraint definition and error mapping.

The constraint itself is PostgreSQL only (see the _postgres test file).  Here
SQLite stands in for it with a commit hook that refuses exactly what the
deferred constraint refuses, raising the same SQLSTATE and constraint name,
so the writer's handling of a losing commit is exercised without a server.

The race is reproduced deterministically: the losing writer's first attempt
reads as if the winner had not committed yet, which is what a writer that read
before the winner committed would see without the Case row lock.
"""
import importlib.util
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from postgres.models.financial import (
    FinancialIngestionRun as Run, FinancialSourceDocument as Source, FinancialTransaction as Payment,
    ONE_ACTIVE_STATEMENT_CONSTRAINT)
from services.financial import import_batches as batches
from services.financial import statement_import
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import active_statement_conflict
from tests.test_financial_batch_import_finalization import accepted, run, state  # noqa: F401  (fixture)

MIGRATION = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261002_one_active_statement.py'


def migration():
    spec = importlib.util.spec_from_file_location('one_active_statement_migration', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExclusionViolation(Exception):
    """Shape of psycopg.errors.ExclusionViolation as SQLAlchemy wraps it."""
    sqlstate = '23P01'

    def __init__(self, constraint=ONE_ACTIVE_STATEMENT_CONSTRAINT, sqlstate='23P01'):
        super().__init__(f'conflicting key value violates exclusion constraint "{constraint}"')
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(constraint_name=constraint)


def violation(**kwargs):
    return IntegrityError('COMMIT', {}, ExclusionViolation(**kwargs))


def active_groups(session):
    groups = {}
    for document in session.scalars(select(Source).where(Source.document_type == 'statement_review',
                                                         Source.status == 'admitted')):
        metadata = document.metadata_ or {}
        if 'financial_import_removal' in metadata:
            continue
        key = (document.case_id, document.evidence_file_id, metadata.get('statement_import_statement_id') or '')
        groups.setdefault(key, []).append(document.id)
    return {key: ids for key, ids in groups.items() if len(ids) > 1}


@contextmanager
def emulated_constraint(factory):
    """Refuse a commit that would leave two active copies, as PostgreSQL does at commit."""
    refused = []

    def check(session):
        session.flush()
        if active_groups(session):
            refused.append(True)
            raise violation()
    event.listen(factory, 'before_commit', check)
    try:
        yield refused
    finally:
        event.remove(factory, 'before_commit', check)


@contextmanager
def stale_first_attempt(attempts=1):
    """The first writer attempt(s) read as if the winner had not yet committed.

    Every existence check made during those attempts, including the ones in
    the statement reading, misses the committed copy.  Later attempts see it.
    """
    actual_existing, actual_once = statement_import._existing_statement, statement_import._write_statement_import_once
    started = []

    def existing(*args, **kwargs):
        return None if len(started) <= attempts else actual_existing(*args, **kwargs)

    def once(**kwargs):
        started.append(True)
        return actual_once(**kwargs)
    with patch.object(statement_import, '_existing_statement', side_effect=existing), \
            patch.object(statement_import, '_write_statement_import_once', side_effect=once):
        yield started


def committed_winner(ctx):
    """Commit the import as another worker would, leaving this item still pending."""
    actual = batches.confirm_statement_import
    captured = {}

    def winner(**kwargs):
        captured.update(kwargs)
        captured['receipt'] = actual(**kwargs)
        raise SystemExit('Synthetic: the other worker owns this outcome')
    with patch.object(batches, 'confirm_statement_import', side_effect=winner), pytest.raises(SystemExit):
        run(ctx)
    return captured


def active_copies(ctx):
    with ctx['f'].SessionLocal() as db:
        return [d.id for d in db.scalars(select(Source).where(Source.document_type == 'statement_review',
                                                              Source.status == 'admitted'))]


def normalized(sql):
    return re.sub(r'\s+', ' ', sql).strip()


# --- constraint definition -------------------------------------------------

def test_model_and_migration_define_the_same_constraint():
    from postgres.models.financial import FinancialSourceDocument
    ddl = str(CreateTable(FinancialSourceDocument.__table__).compile(dialect=postgresql.psycopg.dialect()))
    clause = next(line for line in ddl.splitlines() if ONE_ACTIVE_STATEMENT_CONSTRAINT in line)
    m = migration()
    assert m.CONSTRAINT == ONE_ACTIVE_STATEMENT_CONSTRAINT
    assert normalized(clause).rstrip(',') == normalized(f'CONSTRAINT {m.CONSTRAINT} {m.CONSTRAINT_DDL}')
    assert 'DEFERRABLE INITIALLY DEFERRED' in m.CONSTRAINT_DDL and 'USING btree' in m.CONSTRAINT_DDL


def test_migration_follows_the_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config()
    config.set_main_option('script_location', str(MIGRATION.parents[1]))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ['20261002_one_active_statement']
    assert scripts.get_revision('20261002_one_active_statement').down_revision == '20260924_statement_recovery'


def test_sqlite_schema_omits_the_postgres_only_constraint():
    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateTable as Create
    from postgres.models.financial import FinancialSourceDocument
    ddl = str(Create(FinancialSourceDocument.__table__).compile(dialect=create_engine('sqlite://').dialect))
    assert ONE_ACTIVE_STATEMENT_CONSTRAINT not in ddl and 'EXCLUDE' not in ddl


class FakeBind:
    def __init__(self, offenders):
        self.offenders, self.statements = offenders, []

    def execute(self, statement):
        self.statements.append(str(statement))
        return SimpleNamespace(all=lambda: self.offenders)


def test_upgrade_refuses_and_lists_every_offending_group():
    m = migration()
    bind = FakeBind([('case-a', 'file-a', '', 'doc-1, doc-2'), ('case-a', 'file-b', 'stmt-9', 'doc-3, doc-4')])
    executed = []
    with patch.object(m, 'op', SimpleNamespace(get_bind=lambda: bind, execute=executed.append)):
        with pytest.raises(RuntimeError) as refused:
            m.upgrade()
    message = str(refused.value)
    assert ONE_ACTIVE_STATEMENT_CONSTRAINT in message
    assert 'case case-a, evidence file file-a, statement (whole file): documents doc-1, doc-2' in message
    assert 'case case-a, evidence file file-b, statement stmt-9: documents doc-3, doc-4' in message
    assert executed == []  # Nothing was added.
    assert bind.statements[0].startswith('LOCK TABLE financial_source_documents')


def test_upgrade_adds_and_downgrade_drops_the_constraint():
    m = migration()
    executed = []
    with patch.object(m, 'op', SimpleNamespace(get_bind=lambda: FakeBind([]), execute=executed.append)):
        m.upgrade()
        m.downgrade()
    assert executed == [
        f'ALTER TABLE financial_source_documents ADD CONSTRAINT {m.CONSTRAINT} {m.CONSTRAINT_DDL}',
        f'ALTER TABLE financial_source_documents DROP CONSTRAINT IF EXISTS {m.CONSTRAINT}']


# --- recognising the violation ---------------------------------------------

def test_only_this_exclusion_violation_counts_as_a_concurrent_save():
    assert active_statement_conflict(violation())
    assert not active_statement_conflict(violation(constraint='uq_financial_source_documents_run_file'))
    assert not active_statement_conflict(violation(sqlstate='23505'))
    assert not active_statement_conflict(ExclusionViolation())  # Not wrapped by SQLAlchemy.
    assert not active_statement_conflict(RuntimeError(ONE_ACTIVE_STATEMENT_CONSTRAINT))
    nameless = ExclusionViolation()
    nameless.diag = SimpleNamespace(constraint_name=None)
    assert active_statement_conflict(IntegrityError('COMMIT', {}, nameless))  # Name only in the message.


# --- the writer and the batch worker ---------------------------------------

def test_without_a_database_guarantee_the_stale_writer_admits_a_second_copy(accepted):
    """Control: what the constraint exists to stop (shown on SQLite in b-gate)."""
    winner = committed_winner(accepted)
    kwargs = {k: v for k, v in winner.items() if k != 'receipt'}
    with stale_first_attempt():
        second = statement_import.confirm_statement_import(**kwargs)
    assert second['created'] and second['source_document_id'] != winner['receipt']['source_document_id']
    assert len(active_copies(accepted)) == 2


def test_losing_writer_returns_the_winners_receipt_and_writes_nothing(accepted):
    winner = committed_winner(accepted)
    kwargs = {k: v for k, v in winner.items() if k != 'receipt'}
    payments = state(accepted)['payments']
    assert len(payments) == 12
    with emulated_constraint(accepted['f'].SessionLocal) as refused, stale_first_attempt() as attempts:
        receipt = statement_import.confirm_statement_import(**kwargs)
    assert refused == [True] and len(attempts) == 2
    assert receipt['created'] is False
    assert receipt['source_document_id'] == winner['receipt']['source_document_id']
    assert receipt['transaction_count'] == 12
    assert active_copies(accepted) == [statement_import.UUID(receipt['source_document_id'])]
    assert state(accepted)['payments'] == payments
    with accepted['f'].SessionLocal() as db:
        runs = list(db.scalars(select(Run).order_by(Run.started_at)))
    statement_runs = [r for r in runs if (r.config or {}).get('operation') == 'statement_import']
    # Winner completed; the loser declined and says so; the retry completed with no new rows.
    assert [r.status for r in statement_runs] == ['completed', 'aborted', 'completed']
    assert 'Another save of this statement committed first' in statement_runs[1].error
    assert [r.transactions_admitted for r in statement_runs] == [12, 0, 0]


def test_losing_batch_worker_records_already_present_not_a_failure(accepted):
    winner = committed_winner(accepted)
    before = state(accepted)
    assert before['status'] == 'pending_import'
    with emulated_constraint(accepted['f'].SessionLocal) as refused, stale_first_attempt():
        run(accepted)
    after = state(accepted)
    assert refused == [True]
    assert after['status'] == 'imported'
    assert after['outcomes'][0]['status'] == 'already_present'
    assert after['summary']['source_document_id'] == winner['receipt']['source_document_id']
    assert after['payments'] == before['payments'] and len(after['payments']) == 12
    assert len(active_copies(accepted)) == 1
    run(accepted)
    assert state(accepted) == after


def test_losing_writer_with_a_different_request_is_refused_cleanly(accepted):
    winner = committed_winner(accepted)
    kwargs = {k: v for k, v in winner.items() if k != 'receipt'}
    kwargs['request'] = kwargs['request'].model_copy(update={'holder': 'A different synthetic holder'})
    payments = state(accepted)['payments']
    with emulated_constraint(accepted['f'].SessionLocal) as refused, stale_first_attempt():
        with pytest.raises(PdfMappingError) as error:
            statement_import.confirm_statement_import(**kwargs)
    assert refused == [True]
    assert error.value.status_code == 409
    assert 'already has imported transactions' in str(error.value)
    assert len(active_copies(accepted)) == 1 and state(accepted)['payments'] == payments


def test_writer_that_keeps_losing_is_refused_with_409_not_500(accepted):
    winner = committed_winner(accepted)
    kwargs = {k: v for k, v in winner.items() if k != 'receipt'}
    payments = state(accepted)['payments']
    with emulated_constraint(accepted['f'].SessionLocal) as refused, stale_first_attempt(attempts=2):
        with pytest.raises(PdfMappingError) as error:
            statement_import.confirm_statement_import(**kwargs)
    assert refused == [True, True]
    assert error.value.status_code == 409 and 'committed at the same time' in str(error.value)
    assert len(active_copies(accepted)) == 1 and state(accepted)['payments'] == payments


def test_other_integrity_failures_are_not_mistaken_for_a_concurrent_save(accepted):
    winner = committed_winner(accepted)
    kwargs = {k: v for k, v in winner.items() if k != 'receipt'}

    def other(session):
        raise violation(constraint='uq_financial_source_documents_run_file', sqlstate='23505')
    factory = accepted['f'].SessionLocal
    event.listen(factory, 'before_commit', other)
    try:
        with stale_first_attempt(), pytest.raises(IntegrityError):
            statement_import.confirm_statement_import(**kwargs)
    finally:
        event.remove(factory, 'before_commit', other)
    assert len(active_copies(accepted)) == 1


# --- other paths that can make a copy active --------------------------------

class RefusingSession:
    def __init__(self):
        self.rolled_back = False

    def execute(self, *args, **kwargs):
        raise violation()

    def rollback(self):
        self.rolled_back = True


def test_duplicate_restore_refused_by_the_constraint_is_a_409():
    from services.financial.duplicate_decisions import DuplicateDecisionError, decide_duplicate
    session = RefusingSession()
    with patch('services.financial.duplicate_decisions._decide', side_effect=violation()):
        with pytest.raises(DuplicateDecisionError) as error:
            decide_duplicate(session, case_id=None, document_id=None, action='restore',
                             expected_revision='x', actor=None, reason='r')
    assert session.rolled_back and error.value.status_code == 409


def test_recovery_split_refused_by_the_constraint_is_a_409():
    from services.financial.saved_statement_recovery import save_recovery
    session = RefusingSession()
    with pytest.raises(PdfMappingError) as error:
        save_recovery(session, case_id=None, source_id=None, request=None, actor=None)
    assert session.rolled_back and error.value.status_code == 409
