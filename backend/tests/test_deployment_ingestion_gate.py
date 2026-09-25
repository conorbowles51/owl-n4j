"""Release must defer for both engine work and accepted financial imports."""
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

spec = importlib.util.spec_from_file_location('ingestion_gate', Path(__file__).resolve().parents[2] / 'deploy/check_ingestion_idle.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_empty_install_and_paused_or_finished_work_are_idle():
    engine = create_engine('sqlite://')
    assert gate.active_work(engine) == 0
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (status TEXT, paused BOOLEAN)'))
        db.execute(text("INSERT INTO jobs VALUES ('completed',false),('failed',false),('pending',true)"))
    assert gate.active_work(engine) == 0
    with engine.begin() as db:
        db.execute(text("INSERT INTO jobs VALUES ('processing',false),('pending',false)"))
    assert gate.active_work(engine) == 2


def test_legacy_worker_and_financial_import_cannot_be_missed():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (status TEXT)'))
        db.execute(text("INSERT INTO jobs VALUES ('processing')"))
        db.execute(text('CREATE TABLE financial_import_batch_items (status TEXT)'))
        db.execute(text("INSERT INTO financial_import_batch_items VALUES ('pending_import'),('imported'),('attention')"))
        db.execute(text('CREATE TABLE financial_import_batches (worker_token TEXT, lease_until TIMESTAMP)'))
        db.execute(text("INSERT INTO financial_import_batches VALUES ('active','2099-01-01'),('expired','2000-01-01')"))
    assert gate.active_work(engine) == 3


def test_unknown_schema_does_not_assert_idle():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE jobs (unexpected TEXT)'))
    with pytest.raises(Exception):
        gate.active_work(engine)


def test_recovery_units_without_engine_job_defer_but_review_and_pause_do_not():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE financial_recovery_runs (id TEXT, status TEXT)'))
        db.execute(text('CREATE TABLE financial_recovery_items (run_id TEXT, status TEXT)'))
        db.execute(text("INSERT INTO financial_recovery_runs VALUES ('active','running'),('paused','paused'),('finished','complete')"))
        db.execute(text("INSERT INTO financial_recovery_items VALUES ('active','review'),('active','recovered'),('active','unchanged'),('paused','pending'),('paused','reading'),('finished','pending')"))
    assert gate.active_work(engine) == 0
    with engine.begin() as db:
        db.execute(text("INSERT INTO financial_recovery_items VALUES ('active','pending'),('active','waiting'),('active','reading')"))
    assert gate.active_work(engine) == 3
    with engine.begin() as db:
        db.execute(text("UPDATE financial_recovery_runs SET status = 'paused' WHERE id = 'active'"))
    assert gate.active_work(engine) == 0


@pytest.mark.parametrize('table', ['financial_recovery_runs', 'financial_recovery_items'])
def test_partial_recovery_schema_cannot_silently_report_idle(table):
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text(f'CREATE TABLE {table} (id TEXT, status TEXT)'))
    with pytest.raises(RuntimeError, match='Incomplete financial recovery schema'):
        gate.active_work(engine)


def test_upload_registration_and_dispatch_block_without_counting_paused_group_members():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE evidence_upload_groups (id TEXT, status TEXT)'))
        db.execute(text('CREATE TABLE evidence_upload_sessions (group_id TEXT, status TEXT)'))
        db.execute(text("INSERT INTO evidence_upload_groups VALUES ('paused','paused'),('done','completed')"))
        db.execute(text("INSERT INTO evidence_upload_sessions VALUES ('paused','staged'),('paused','paused'),('done','completed'),(NULL,'paused'),(NULL,'completed')"))
    assert gate.active_work(engine) == 0
    with engine.begin() as db:
        db.execute(text("INSERT INTO evidence_upload_groups VALUES ('folder','uploading'),('registration','dispatching')"))
        db.execute(text("INSERT INTO evidence_upload_sessions VALUES ('folder','uploading'),('folder','staged'),('registration','staged'),(NULL,'uploading')"))
    assert gate.active_work(engine) == 3
    with engine.begin() as db:
        db.execute(text("UPDATE evidence_upload_groups SET status = 'completed'"))
        db.execute(text("UPDATE evidence_upload_sessions SET status = 'completed'"))
    assert gate.active_work(engine) == 0


def test_legacy_uploads_and_unknown_unfinished_states_defer_conservatively():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE evidence_upload_sessions (status TEXT)'))
        db.execute(text("INSERT INTO evidence_upload_sessions VALUES ('uploading'),('staged'),('paused'),('completed'),('new_unfinished_state')"))
    assert gate.active_work(engine) == 3
