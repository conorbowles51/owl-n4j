"""A synthetic large case for review queue timing: ~1,000 prepared statements, no live data.

One statement is prepared through the real batch machinery (the fixture's
PDF reading); its stored summary is the template for every other statement.
Files are separate evidence rows (distinct bytes), all in one finished batch,
so the queue sees the shape of a large live case: many files, several
statements per file, most held with a reading or detail problem, some ready,
a few with nothing read.
"""
import asyncio
import hashlib
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4, uuid5

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

READING = dict(kind='reading', message='Check this row in the transaction section.', row_id='7:0:3', page=7)
CURRENCY = dict(message='Choose the currency printed on these statements.', row_id=None)


def _template(f):
    from services.financial import import_batches as service
    with f.SessionLocal() as db:
        batch = service.create_batch(db, case_id=f.case.id, request_id=uuid4(), file_ids=[f.file.id],
            folder_ids=[], actor=f.actor)
    process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
    for _ in range(4):
        asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, process))
    with f.SessionLocal() as db:
        record = db.query(Item).filter(Item.batch_id == batch).one()
        summary = {key: value for key, value in deepcopy(record.summary).items() if key != 'readiness'}
        return batch, summary


def build(f, *, files=250, statements=4):
    """Add files x statements prepared statements to the fixture's case. Returns {bucket: expected count}."""
    _, template = _template(f)
    expected = dict(waiting=0, ready=0, unreadable=0)
    with f.SessionLocal() as db:
        batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review',
            actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)), files=[])
        db.add(batch)
        db.flush()
        entries = []
        for index in range(files):
            evidence = EvidenceFile(id=uuid4(), case_id=f.case.id, original_filename=f'synthetic-{index:04d}.pdf',
                stored_path=f'/evidence/synthetic-{index:04d}.pdf', status='processed',
                sha256=hashlib.sha256(f'synthetic {index}'.encode()).hexdigest())
            db.add(evidence)
            entries.append(dict(source_id=str(evidence.id), file_id=str(evidence.id), filename=evidence.original_filename,
                expected_revision='initial', status='checked'))
            for number in range(statements):
                kind = (index * statements + number) % 10
                summary = dict(deepcopy(template), filename=evidence.original_filename, source_id=str(evidence.id),
                    period_start=f'2021-{number + 1:02d}-01', period_end=f'2021-{number + 1:02d}-28',
                    account=f'ACC{index:04d}')
                if kind < 6:
                    summary.update(can_import=False, problems=[READING if kind % 2 else CURRENCY], problem_count=1)
                    status, bucket = 'attention', 'waiting'
                elif kind < 9:
                    summary.update(can_import=True, problems=[], problem_count=0)
                    status, bucket = 'ready', 'ready'
                else:
                    summary.update(can_import=False, problems=[READING], problem_count=1, transaction_count=0,
                        record_count=0, incomplete_count=0, unclassified_count=0, period_start='', period_end='')
                    status, bucket = 'attention', 'unreadable'
                expected[bucket] += 1
                db.add(Item(id=uuid5(batch.id, f'{index}:{number}'), batch_id=batch.id, file_id=evidence.id,
                    statement_key=f's{number}', status=status, summary=summary))
        batch.files = entries
        db.commit()
    return expected
