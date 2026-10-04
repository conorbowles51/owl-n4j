"""The statement census covers every batch file of a case, on the synthetic corpus, and writes nothing live."""
import asyncio
import hashlib
import importlib.util
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / 'scripts/financial_statement_census.py'
CORPUS = BACKEND / 'benchmarks/statement_automation/corpus'
# auto, auto, decision (holder not printed).
FILES = ('generic-01-clean.pdf', 'generic-02-clean.pdf', 'generic-05-holder_not_printed.pdf')


def load():
    spec = importlib.util.spec_from_file_location('statement_census_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def corpus(tmp_path_factory):
    """The three corpus PDFs, read once by the real engine into a census cache."""
    census = load()
    root = tmp_path_factory.mktemp('census-corpus')
    originals = {}
    for name in FILES:
        target = root / 'originals' / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(CORPUS / name, target)
        originals[hashlib.sha256(target.read_bytes()).hexdigest()] = target
    cache = root / 'cache'
    done = census.cached_reread(originals, cache, sys.executable, workers=2, chunk=2)
    readings = {sha: json.loads(path.read_text()) for sha, path in done.items()}
    assert not [sha for sha, reading in readings.items() if 'error' in reading]
    return dict(root=root, originals=originals, cache=cache, readings=readings)


def live_case(tmp_path, corpus):
    """A live-like case: every file prepared in one batch, one period imported, one source gone."""
    from benchmarks.statement_automation.harness import _database
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFolder, EvidenceTableGeometry
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from postgres.models.user import User
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial import import_batches as batches
    from services.financial.decisions import Actor
    engine, factory, _ = _database(tmp_path / 'live.db')
    with factory() as db:
        user = User(id=uuid.uuid4(), email='live@example.test', name='Live investigator', password_hash='x',
            global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Live', created_by_user_id=user.id, owner_user_id=user.id)
        folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='Statements')
        db.add_all([user, case, folder])
        db.flush()
        created = EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=path.name, stored_path=str(path),
            sha256=sha, size=path.stat().st_size) for sha, path in corpus['originals'].items()],
            folder_id=folder.id, created_by_id=user.id)
        db.flush()
        for record in created:
            reading = corpus['readings'][record.sha256]
            job = uuid.uuid4()
            db.add(EvidenceDocumentText(evidence_file_id=record.id, engine_job_id=job, content=reading['content'],
                content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
            for page, payload in reading['geometry'].items():
                db.add(EvidenceTableGeometry(evidence_file_id=record.id, page_number=int(page), engine_job_id=job,
                    payload=payload))
            record.status, record.engine_job_id = 'processed', str(job)
        db.commit()
        case_id, folder_id, actor = case.id, folder.id, Actor(user.name, user.email, user.id)
        names = {record.original_filename: record.id for record in created}
    with factory() as db:
        batch_id = batches.create_batch(db, case_id=case_id, request_id=uuid.uuid4(), file_ids=[],
            folder_ids=[folder_id], actor=actor)

    async def refuse(*_args, **_kwargs):
        raise RuntimeError('no engine job in tests')
    for _ in range(20):
        asyncio.run(batches.advance_batch(factory, batch_id, Path, refuse))
    with factory() as db:
        batch = db.get(Batch, batch_id)
        # A file whose evidence record no longer exists in the case.
        batch.files = [*batch.files, dict(source_id=str(uuid.uuid4()), file_id=str(uuid.uuid4()),
            filename='gone.pdf', status='error', error='The PDF reading failed.')]
        imported = db.scalar(select(Item).where(Item.file_id == names['generic-02-clean.pdf']))
        imported.status = 'imported'
        db.commit()
    return engine, factory, case_id, names


def snapshot(factory):
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    with factory() as db:
        return dict(files=[(f.id, f.status, json.dumps(f.metadata_, sort_keys=True, default=str))
                           for f in db.scalars(select(EvidenceFile).order_by(EvidenceFile.id))],
            batches=[(b.id, b.status, json.dumps(b.files, sort_keys=True)) for b in db.scalars(select(Batch))],
            items=[(i.id, i.status, json.dumps(i.summary, sort_keys=True, default=str))
                   for i in db.scalars(select(Item).order_by(Item.id))])


def test_census_covers_every_batch_file_without_writing(tmp_path, corpus, monkeypatch):
    census = load()
    engine, factory, case_id, names = live_case(tmp_path, corpus)
    before = snapshot(factory)
    # Every original is already in the cache: the census must not start the engine again.
    monkeypatch.setattr(census, '_read_chunk', lambda *a, **k: pytest.fail('cached readings were read again'))
    out = tmp_path / 'census'
    report = census.census(factory, case_id, out, cache=corpus['cache'], resolve_path=Path, log=lambda *_: None,
        scratch_root=tmp_path / 'scratch')
    assert snapshot(factory) == before
    assert not list((tmp_path / 'scratch').iterdir())

    assert report['files'] == 4
    assert report['file_states'] == {'listed': 3, 'unavailable': 1}
    assert report['file_problems'] == {'original_unavailable': 1}
    rows = [json.loads(line) for line in (out / str(case_id) / 'periods.jsonl').open()]
    files = {json.loads(line)['original_filename']: json.loads(line)['key']
             for line in (out / str(case_id) / 'files.jsonl').open() if 'original_filename' in line}
    by_file = {}
    for row in rows:
        by_file.setdefault(row['file'], []).append(row)
    clean2 = by_file[files['generic-02-clean.pdf']]
    assert [(r['current']['ready'], r['live']['state']) for r in clean2] == [(True, 'imported')]
    holder = by_file[files['generic-05-holder_not_printed.pdf']]
    assert [r['current']['ready'] for r in holder] == [False]
    assert 'holder' in holder[0]['current']['coarse'] and holder[0]['live']['state'] == 'held'
    clean1 = by_file[files['generic-01-clean.pdf']]
    assert [(r['current']['ready'], r['retained']['ready'], r['live']['state']) for r in clean1] == [
        (True, True, 'ready_no_edits')]
    gone = [row for key, rows_ in by_file.items() if key not in files.values() for row in rows_]
    assert [(row['current'], row['current_file_state']) for row in gone] == [(None, 'original_unavailable')]
    # The retained readings are the same engine's: both sides agree.
    assert report['ready_current'] == report['ready_retained']
    assert report['live_states']['imported'] == 1
    assert report['audit']['considered'] == 0  # nothing admitted in this case

    # A rerun with unchanged inputs reuses both stored preparations.
    estimate = census._estimate()
    monkeypatch.setattr(estimate, 'scratch_batch', lambda *a, **k: pytest.fail('stored preparation not reused'))
    monkeypatch.setattr(census, '_estimate', lambda: estimate)
    again = census.census(factory, case_id, out, cache=corpus['cache'], resolve_path=Path, log=lambda *_: None,
        scratch_root=tmp_path / 'scratch', audit=False)
    assert (again['periods'], again['ready_current'], again['ready_retained']) == (
        report['periods'], report['ready_current'], report['ready_retained'])

    summary = census.summarize(out, tmp_path / 'summary.md')
    shared = summary + json.dumps(report)
    for name, file_id in names.items():
        assert name not in shared and str(file_id) not in shared
    assert '| holder |' in summary
    engine.dispose()


def test_cache_resumes_and_failed_reads_are_measured(tmp_path, corpus, monkeypatch):
    census = load()
    (sha, path), = list(corpus['originals'].items())[:1]
    calls = []

    def failing(chunk, workdir, python, timeout):
        calls.append(len(chunk))
        return None, 'engine_process_failed: boom'
    monkeypatch.setattr(census, '_read_chunk', failing)
    other = list(corpus['originals'].items())[1]
    done = census.cached_reread(dict([(sha, path), other]), tmp_path / 'cache', chunk=2)
    assert calls == [2, 1, 1]  # the failed pair is retried one file at a time
    assert all('error' in json.loads(p.read_text()) for p in done.values())
    calls.clear()
    census.cached_reread(dict([(sha, path), other]), tmp_path / 'cache', chunk=2)
    assert calls == []  # a measured failure is not repeated on resume
    census.cached_reread(dict([(sha, path), other]), tmp_path / 'cache', chunk=2, retry_errors=True)
    assert calls == [2, 1, 1]


def test_workers_are_capped_at_two(tmp_path, corpus, monkeypatch):
    census = load()
    seen = {}

    class Pool:
        def __init__(self, max_workers):
            seen['workers'] = max_workers

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, function, groups):
            return []
    monkeypatch.setattr(census, 'ThreadPoolExecutor', Pool)
    census.cached_reread(corpus['originals'], tmp_path / 'cache', workers=6)
    assert seen['workers'] == 2


def test_problem_templates_mask_digits():
    census = load()
    identifier, masked = census.template('Closing balance 1,234.56 differs by 10.00')
    assert masked == 'Closing balance #,###.## differs by ##.##'
    assert census.template('Closing balance 9,999.99 differs by 11.00')[0] == identifier


def _item(key, status, start='', end='', review=False, problems=(), account='1'):
    return dict(statement_key=key, status=status, can_import=status == 'ready', saved_review=review,
        period_start=start, period_end=end, account=account, problems=list(problems))


def test_live_periods_count_each_statement_period_once():
    census = load()
    items = [
        _item('', 'imported'),  # an earlier whole-file preparation of the same original
        _item('a', 'imported', '2021-01-01', '2021-01-31'),
        _item('b', 'attention', '2021-01-01', '2021-01-31'),  # a later reading keys the same period anew
        _item('c', 'imported'),  # a summary stored without dates
        _item('c', 'attention', '2021-02-01', '2021-02-28', problems=[dict(message='x')]),
        _item('d', 'superseded_reading', '2021-03-01', '2021-03-31'),  # history
    ]
    periods, legacy = census.live_periods(items)
    assert legacy == 1
    assert sorted((p['period_start'], p['status'], p['items']) for p in periods) == [
        ('2021-01-01', 'imported', 2), ('2021-02-01', 'imported', 2)]
    only_blank, legacy = census.live_periods([_item('', 'imported'), _item('', 'attention')])
    assert [(p['status'], p['items']) for p in only_blank] == [('imported', 2)] and legacy == 0
    # One statement holding several accounts over the same dates is several periods.
    shares, _ = census.live_periods([_item('s1', 'ready', '2021-01-01', '2021-01-31', account='1'),
        _item('s2', 'attention', '2021-01-01', '2021-01-31', account='2')])
    assert sorted(p['status'] for p in shares) == ['attention', 'ready']
    held, _ = census.live_periods([_item('e', 'ready', review=True)])
    assert held[0]['state'] == 'ready_after_edits'


def test_a_system_set_aside_is_not_a_held_period():
    census = load()
    base = dict(ready=False, problems=[], status='duplicate_ignored')
    assert census.prepared_outcome(base) == 'duplicate_set_aside'
    assert census.prepared_outcome(dict(base, status='attention')) == 'held'
    assert census.prepared_outcome(dict(base, ready=True, status='ready')) == 'ready'


def test_a_retained_reading_without_its_original_is_still_prepared(tmp_path, corpus):
    census = load()
    estimate = census._estimate()
    sha = next(sha for sha, path in corpus['originals'].items() if path.name == 'generic-01-clean.pdf')
    prepared = estimate.scratch_batch(tmp_path, 'retained', [dict(key='gone', sha256=None, currency=None)],
        {'gone': corpus['readings'][sha]}, retained_currency=False)
    assert prepared['files'] == 1 and [item['ready'] for item in prepared['items']] == [True]


def test_an_undivided_file_matches_its_live_period():
    census = load()
    files = [dict(key='k1', retained=False, live_items=[_item('', 'imported', '2021-01-01', '2021-01-31')])]
    prepared = dict(items=[dict(key='k1', statement_key='', status='attention', ready=False, family='generic-statement',
        problems=[dict(message='Enter the account holder shown on the statement.')], period_start='', period_end='',
        account='', transaction_count=3)], file_errors=[])
    rows = census.join(files, prepared, dict(items=[], file_errors=[]), {})
    assert [(r['current']['outcome'], r['live']['state']) for r in rows] == [('held', 'imported')]


def test_summary_labels_only_product_text():
    census = load()
    code = 'Check the printed fee total. It could not be compared with the selected payments. Loupe could not read  as an amount.'
    assert census._label('x', 'Check the printed fee total. It could not be compared with the selected payments.', code).startswith('Check')
    assert census._label('x', 'Loupe could not read "SMITH #,###" as an amount.', code) == 'Loupe could not read "…" as an amount.'
    assert census._label('x', 'Paid to SMITHERSON on ##/##.', code) == 'template x'
    assert census._label('x', 'Check the printed interest total.', code + ' interest') == 'Check the printed interest total.'
