"""The reader recovery dry run selects like the campaign and writes nothing live."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as BatchItem
from postgres.models.financial_recovery import FinancialRecoveryItem, FinancialRecoveryRun
from tests.test_financial_deployment_recovery import f  # noqa: F401  (fixture)
from tests.test_financial_recovery_readers import held_batch, set_reader

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/financial_reader_recovery_estimate.py'


def load():
    spec = importlib.util.spec_from_file_location('reader_recovery_estimate_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_state(f):
    with f.SessionLocal() as db:
        return dict(
            files=[(row.id, row.status, json.dumps(row.metadata_, sort_keys=True, default=str))
                   for row in db.scalars(select(EvidenceFile).order_by(EvidenceFile.id))],
            batches=[(row.id, row.status, json.dumps(row.files, sort_keys=True)) for row in db.scalars(select(Batch))],
            items=[(row.id, row.status, json.dumps(row.summary, sort_keys=True, default=str))
                   for row in db.scalars(select(BatchItem).order_by(BatchItem.id))],
            runs=db.scalar(select(func.count()).select_from(FinancialRecoveryRun)),
            recovery_items=db.scalar(select(func.count()).select_from(FinancialRecoveryItem)),
            logs=db.scalar(select(func.count()).select_from(IngestionLog)))


def test_read_only_session_refuses_any_write(f):
    estimate = load()
    with f.SessionLocal() as db:
        estimate.read_only(db)
        db.get(EvidenceFile, f.file.id).status = 'failed'
        with pytest.raises(estimate.ReadOnlyViolation):
            db.flush()
        db.rollback()
    with f.SessionLocal() as db:
        assert db.get(EvidenceFile, f.file.id).status == 'processed'


def test_dry_run_reports_selection_and_both_readings_without_touching_the_case(f, tmp_path):
    estimate = load()
    set_reader(f, f.file.id)
    held_batch(f, statuses=('attention',))
    before = live_state(f)
    seen = {}

    def reader(paths, scratch, python, concurrency):
        # Stand-in for the engine: the "new" reading is the retained one.
        seen.update(paths)
        with f.SessionLocal() as db:
            live = estimate.select_live(db, f.case.id, Path)
            db.rollback()
        return {file['key']: deepcopy(file['retained']) for file in live['files']}

    report = estimate.estimate(f.SessionLocal, f.case.id, scratch_root=tmp_path / 'scratch',
        resolve_path=Path, reader=reader)
    assert live_state(f) == before
    assert report['selection'] == {'eligible': 1}
    assert report['live_held_periods'] == 1
    assert list(seen.values()) == [Path(f.file.stored_path)]
    reread = report['reread']
    assert reread['verified'] == 1 and reread['problems'] == {}
    assert reread['retained']['periods'] >= 1
    assert reread['retained'] == reread['current']
    assert not list((tmp_path / 'scratch').iterdir())  # scratch removed
    text = estimate.render(report)
    assert f.file.original_filename not in text and str(f.file.id) not in text
    assert f.file.original_filename not in json.dumps(report) and str(f.file.id) not in json.dumps(report)


def test_changed_original_is_not_reread(f, tmp_path):
    estimate = load()
    set_reader(f, f.file.id)
    held_batch(f)
    Path(f.file.stored_path).write_bytes(b'%PDF-1.4\nchanged')
    report = estimate.estimate(f.SessionLocal, f.case.id, scratch_root=tmp_path, resolve_path=Path,
        reader=lambda *args: pytest.fail('a changed original must not be read'))
    assert report['reread']['verified'] == 0 and report['reread']['problems'] == {'original_changed': 1}


def test_select_only_skips_the_reread(f):
    estimate = load()
    set_reader(f, f.file.id, None)
    held_batch(f)
    report = estimate.estimate(f.SessionLocal, f.case.id, reread=False, resolve_path=Path)
    assert report['selection'] == {'unrecorded_reader': 1} and 'reread' not in report
