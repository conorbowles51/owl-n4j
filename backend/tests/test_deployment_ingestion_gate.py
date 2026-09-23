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
