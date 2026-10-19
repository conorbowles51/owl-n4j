"""Replay a reader release on the synthetic corpus: what reaches ready with no click.

    cd backend && python -m benchmarks.statement_automation.release_replay --readings ENGINE_READINGS.json --out DIR

1. Every corpus PDF is uploaded and prepared in one batch, as the harness does,
   but by an "old reader": today's reader with the last printed payment of
   every statement missed, under an old reader stamp. Those statements do not
   reconcile and wait.
2. The current reader is deployed (the real stamp). The batch loop's sweep
   (reader_release.sweep) finds the prepared files, reads them again read-only,
   and hands those that read differently back to the batch; worker turns
   prepare them again. Nobody clicks anything.
3. Counts before and after: statements ready (or saved by the system) and
   waiting, files re-prepared, files left as they were.

Counts only; writes only to DIR. The automatic save runs as in the product
(FINANCIAL_AUTO_SAVE_READY=0 turns it off).
"""
import argparse
import asyncio
import json
import sys
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from benchmarks.statement_automation import harness

OLD_STAMP = 'replay-old-reader'


def _old_reader(current):
    def read(*args, **kwargs):
        proposal = current(*args, **kwargs)
        if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
            return proposal
        rows = [row for row in proposal.get('rows', []) if row['kind'] == 'transaction' and not row['excluded']]
        if not rows:
            return proposal
        proposal = deepcopy(proposal)
        proposal['rows'] = [row for row in proposal['rows'] if row['id'] != rows[-1]['id']]
        proposal['revision'] = 'old-' + proposal['revision']
        return proposal
    return read


def replay(out, readings_path, corpus=harness.CORPUS):
    from sqlalchemy import select
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((corpus / 'manifest.json').read_text())
    readings = {Path(path).name: value for path, value in json.loads(Path(readings_path).read_text())['readings'].items()}
    from postgres.models.user import User
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial import import_batches as batches, queue_save, reader_release
    from services.financial.decisions import Actor
    engine, factory, _ = harness._database(out / 'replay.db')
    with factory() as db:
        user = User(id=uuid.uuid4(), email='replay@example.test', name='Replay investigator', password_hash='not-used',
                    global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Reader release replay', created_by_user_id=user.id, owner_user_id=user.id)
        folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='Synthetic statements')
        db.add_all([user, case, folder])
        db.commit()
        EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=f['filename'],
            stored_path=str(corpus / f['filename']), sha256=f['sha256'], size=f['size']) for f in manifest['files']],
            folder_id=folder.id, created_by_id=user.id)
        db.commit()
        case_id, folder_id, actor = case.id, folder.id, Actor(user.name, user.email, user.id)

    async def process_files(session, *, case_id, file_ids, **_):
        jobs = []
        for file_id in file_ids:
            record = session.get(EvidenceFile, file_id)
            reading = readings[Path(record.stored_path).name]
            job = uuid.uuid4()
            if 'error' in reading:
                record.status, record.last_error = 'failed', reading['error']
            else:
                session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=reading['content'],
                    content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                    source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
                for page, entries in reading['geometry'].items():
                    session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=int(page),
                                                      engine_job_id=job, payload=entries))
                record.status, record.engine_job_id = 'processed', str(job)
            jobs.append(str(job))
        session.commit()
        return dict(job_ids=jobs)

    with factory() as db:
        batch_id = batches.create_batch(db, case_id=case_id, request_id=uuid.uuid4(), file_ids=[],
                                        folder_ids=[folder_id], actor=actor)

    def progress():
        with factory() as db:
            batch = batches.batch_for(db, case_id, batch_id)
            items = Counter(db.scalars(select(Item.status).where(Item.batch_id == batch_id)))
            return batch.status, (tuple(sorted(items.items())), tuple(f['status'] for f in batch.files))

    def drain(label):
        return harness.drain_batch(lambda: asyncio.run(batches.advance_batch(factory, batch_id, Path, process_files)),
                                   progress, label)

    def counts():
        with factory() as db:
            saved = harness.saved_by_system(db, batch_id, Item, queue_save.SYSTEM_ACTOR)
            status = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=10_000)
        ready = sum(1 for i in status['items'] if i.get('can_import') or i['id'] in saved)
        return dict(statements=len(status['items']), ready_or_saved_by_system=ready,
                    saved_by_system=len(saved), waiting=sum(i['status'] == 'attention' for i in status['items']),
                    by_status=dict(Counter(i['status'] for i in status['items'])))

    with patch.object(batches, 'read_statement_import', _old_reader(batches.read_statement_import)), \
            patch.object(reader_release, 'reader_stamp', return_value=OLD_STAMP):
        prepared = drain('old reader preparation')
    before = counts()
    # The batch loop's rounds: a sweep (bounded, as in production), then the
    # worker runs the batch it handed back; until no file is left to compare.
    sweeps, rechecked, left, drains = 0, 0, Counter(), []
    while True:
        outcome = reader_release.sweep(factory)
        sweeps += 1
        rechecked += outcome['rechecked']
        left.update(outcome['left'])
        if not outcome['files']:
            break
        if outcome['rechecked']:
            drains.append(drain('re-preparation after the release'))
    after_drain = dict(runs=len(drains), turns=sum(d['turns'] for d in drains),
                       seconds=sum(d['seconds'] for d in drains), stalled=any(d['stalled'] for d in drains))
    after = counts()
    result = dict(auto_save_ready=queue_save.AUTO_SAVE_READY, before_release=before, after_release=after,
                  moved_to_ready_without_a_click=after['ready_or_saved_by_system'] - before['ready_or_saved_by_system'],
                  files_rechecked=rechecked, files_left=dict(left), sweeps=sweeps,
                  timing=dict(preparation=prepared, re_preparation=after_drain))
    (out / 'release-replay.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    engine.dispose()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Replay a reader release on the synthetic corpus (counts only).')
    parser.add_argument('--readings', required=True, help='engine-readings.json of a synthetic benchmark run')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    result = replay(Path(args.out), args.readings)
    print(json.dumps({k: v for k, v in result.items() if k != 'timing'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
