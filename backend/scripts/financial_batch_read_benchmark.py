"""Time the financial batch read path on synthetic batches.

Builds a disposable SQLite case from the synthetic statement fixture used by the
backend tests, clones it into N statement files (no client data is involved),
and measures `import_batches.batch_status` stage by stage.

Usage, from `backend/`:

    python3 scripts/financial_batch_read_benchmark.py --items 250 1000

Scenarios:

* ``legacy``  - item summaries written before bank/product identity and
  reconciliation fields were stored (the state of older live batches).
* ``current`` - item summaries carrying every field the read path needs.
* ``refreshed`` - the legacy batch after `refresh_batch_readiness` has run on
  the write side (only when that function exists).

Each statement belongs to an account group of ``--group`` files so that the
coverage comparison has real overlaps and duplicate holds to evaluate.
"""
import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LEGACY_FIELDS = ('institution', 'account_type', 'review_model', 'can_import')


class Stages:
    """Wrap read-path functions and accumulate their wall time per call."""

    def __init__(self):
        self.seconds = defaultdict(float)
        self.calls = defaultdict(int)

    def wrap(self, label, function):
        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.seconds[label] += time.perf_counter() - started
                self.calls[label] += 1
        return timed


def _patches(stages):
    from services.financial import import_batches, statement_import, statement_import_overlap
    from services.financial import batch_import_history, batch_review_summary, import_operations
    reader = statement_import.read_statement_import
    timed_reader = stages.wrap('read_statement_import (PDF reparse)', reader)
    targets = [
        (statement_import_overlap, 'comparison_sources'),
        (statement_import_overlap, 'coverage_review'),
        (batch_import_history, 'current_imports'),
        (import_batches, '_sort_statements'),
        (batch_review_summary, 'review_summary'),
        (batch_review_summary, 'statement_summary'),
        (import_operations, 'operations_for'),
        (import_batches, 'assess'),
    ]
    managers = [patch.object(import_batches, 'read_statement_import', timed_reader),
                patch.object(statement_import, 'read_statement_import', timed_reader)]
    for module, name in targets:
        managers.append(patch.object(module, name, stages.wrap(name, getattr(module, name))))
    return managers


def build(items, group, legacy):
    """Return (fixture, batch_id) for a synthetic batch of `items` statements."""
    import hashlib
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from tests import test_financial_import_batches as fixtures

    fixture = fixtures.BatchImportTests()
    fixture.setUp()
    f = fixture.f
    batch_id = fixture.create()
    fixture.advance(batch_id)
    with f.SessionLocal() as db:
        file = db.get(EvidenceFile, f.file.id)
        text = db.get(EvidenceDocumentText, file.id)
        geometry = db.get(EvidenceTableGeometry, (file.id, 1))
        original = db.scalar(select(Item).where(Item.batch_id == batch_id))
        template = deepcopy(original.summary)
        if legacy:
            template = {k: v for k, v in template.items() if k not in LEGACY_FIELDS}
            original.summary = deepcopy(template)
        batch = db.get(Batch, batch_id)
        files = deepcopy(batch.files)
        for index in range(1, items):
            identifier = uuid4()
            account = f'TEST{1000 + index // group}'
            content = text.content.replace('Account Number: TEST123', f'Account Number: {account}')
            name = f'synthetic-statement-{index:04d}.pdf'
            db.add(EvidenceFile(id=identifier, case_id=file.case_id, original_filename=name,
                stored_path=file.stored_path, sha256=file.sha256, status='processed', metadata_={}))
            db.add(EvidenceDocumentText(evidence_file_id=identifier, content=content,
                content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
                engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
            db.add(EvidenceTableGeometry(evidence_file_id=identifier, page_number=1,
                engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
            db.add(Item(id=uuid4(), batch_id=batch.id, file_id=identifier, statement_key=original.statement_key,
                status=original.status, summary={**deepcopy(template), 'filename': name,
                    'source_id': str(identifier), 'account': account}))
            files.append({**files[0], 'source_id': str(identifier), 'file_id': str(identifier),
                'filename': name, 'status': 'checked'})
        batch.files = files
        db.commit()
    return fixture, batch_id


def measure(fixture, batch_id, repeats):
    from services.financial import import_batches
    runs = []
    for _ in range(repeats):
        stages = Stages()
        with fixture.f.SessionLocal() as db, ExitStack() as stack:
            for manager in _patches(stages):
                stack.enter_context(manager)
            started = time.perf_counter()
            state = import_batches.batch_status(db, case_id=fixture.f.case.id, batch_id=batch_id)
            total = time.perf_counter() - started
            wrote = bool(db.new or db.dirty or db.deleted)
        runs.append(dict(total=total, stages=dict(stages.seconds), calls=dict(stages.calls),
                         counts=state['counts'], wrote=wrote))
    return runs


def refresh(fixture, batch_id):
    from services.financial import import_batches
    function = getattr(import_batches, 'refresh_batch_readiness', None)
    if function is None:
        return None
    started = time.perf_counter()
    with fixture.f.SessionLocal() as db:
        result = function(db, case_id=fixture.f.case.id, batch_id=batch_id)
    return dict(seconds=time.perf_counter() - started, result=result)


def report(label, items, runs):
    totals = [run['total'] for run in runs]
    last = runs[-1]
    print(f'\n== {label}: {items} items, {len(runs)} run(s)')
    print(f'   batch_status wall: median {statistics.median(totals):.3f}s  max {max(totals):.3f}s')
    print(f'   counts: {last["counts"]}  session wrote state: {last["wrote"]}')
    for name in sorted(last['stages'], key=lambda key: -last['stages'][key]):
        print(f'   {name:<40} {last["stages"][name]:9.3f}s  calls={last["calls"][name]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--items', type=int, nargs='+', default=[250, 1000])
    parser.add_argument('--group', type=int, default=4, help='statements sharing one account (overlap density)')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--scenarios', nargs='+', default=['legacy', 'current'])
    parser.add_argument('--json', help='write raw results to this path')
    args = parser.parse_args()
    import logging
    logging.disable(logging.WARNING)
    results = []
    for items in args.items:
        for scenario in args.scenarios:
            started = time.perf_counter()
            fixture, batch_id = build(items, args.group, legacy=scenario == 'legacy')
            print(f'\n(built {scenario} batch of {items} in {time.perf_counter() - started:.1f}s)')
            try:
                runs = measure(fixture, batch_id, args.repeats)
                report(scenario, items, runs)
                results.append(dict(scenario=scenario, items=items, runs=runs))
                if scenario == 'legacy':
                    refreshed = refresh(fixture, batch_id)
                    if refreshed is not None:
                        print(f'\n   write-side refresh_batch_readiness: {refreshed["seconds"]:.3f}s {refreshed["result"]}')
                        runs = measure(fixture, batch_id, args.repeats)
                        report('legacy after write-side refresh', items, runs)
                        results.append(dict(scenario='refreshed', items=items, runs=runs,
                                            refresh_seconds=refreshed['seconds']))
            finally:
                fixture.tearDown()
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump(results, handle, indent=2, default=str)


if __name__ == '__main__':
    main()
