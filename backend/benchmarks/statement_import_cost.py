"""Time one import of one period of a synthetic many-period statement file.

Synthetic data only (a card statement printed once per month on its own page,
like the long productions that hold one account's whole history). Runs on the
test fixture's SQLite database, so absolute times are not the live server's;
what it measures is how each step grows with the number of periods.

    CHROMADB_PORT=1 CHROMA_PORT=1 python3 benchmarks/statement_import_cost.py --periods 60 --imports 5

Prints, per step, seconds for: the cold file reading, preparing every period in
a batch, then for each import: the import itself, the readiness sweep that
follows it, and the identity graph plan of the case.
"""
import argparse
import calendar
import hashlib
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _month(year, month, day):
    return date(year, month, day)


def period_grid(index, first_year=2004):
    """One printed card period: start the 12th of a month, end the 11th of the next."""
    from tests.test_financial_statement_import_card import source
    from services.financial.statement_layout_context import statement_layout_context
    year, month = first_year + index // 12, index % 12 + 1
    start = _month(year, month, 12)
    end = _month(year + (month == 12), month % 12 + 1, 11)
    label = lambda value: calendar.month_abbr[value.month] + ('.' if value.month == 6 else '')
    printed = lambda value: f'{label(value)} {value.day}, {value.year}'
    days = (end - start).days + 1
    paid, bought = start + timedelta(days=8), start + timedelta(days=7)
    result = source([
        ['Platinum MasterCard Account Ending in 1234'],
        [f'{printed(start)} - {printed(end)} | {days} days in Billing Cycle'],
        ['Visit www.capitalone.com to see detailed transactions.'],
        ['SAMPLE HOLDER #1234: Payments, Credits and Adjustments'],
        ['Date', 'Description', 'Amount'], [f'{label(paid)} {paid.day}', 'PAYMENT', '- $180.00'],
        ['SAMPLE HOLDER #1234: Transactions'], ['Date', 'Description', 'Amount'],
        [f'{label(bought)} {bought.day}', 'EXAMPLE SHOP', '$61.62'], ['Total Transactions for This Period', '$61.62'],
        ['Interest Charged'], ['Interest Charge on Purchases', '$56.16'],
        ['Interest Charge on Cash Advances', '$0.00'], ['Total Interest for This Period', '$56.16']])
    result['layout_context'] = statement_layout_context(result['rows'])
    return result


def install(fixture, periods):
    """Replace the fixture file's reading with `periods` printed periods, one per page."""
    from sqlalchemy import delete
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from tests.test_financial_pdf_geometry_candidates import rectangle
    db = fixture.db
    job = db.get(EvidenceDocumentText, fixture.file.id).engine_job_id
    db.execute(delete(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == fixture.file.id))
    contents = []
    for index in range(periods):
        page = index + 1
        grid = period_grid(index)
        db.add(EvidenceTableGeometry(evidence_file_id=fixture.file.id, page_number=page, engine_job_id=job, payload=[dict(
            table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=page, table=dict(rectangle(0, x=0, width=600, height=600), page=page), unlocated_values=0,
                values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                    locator=dict(rectangle(20 + r['row_index'] * 20, x=20 + c['column_index'] * 100, width=90, height=15), page=page))
                    for r in grid['rows'] for c in r['cells']]))]))
        contents.append('\n'.join(c['expected_text'] for r in grid['rows'] for c in r['cells']))
    text = db.get(EvidenceDocumentText, fixture.file.id)
    text.content = '\n'.join(contents)
    text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
    text.character_count = len(text.content)
    locations, offset = [], 0
    for index, content in enumerate(contents):
        locations.append(dict(kind='page', page_number=index + 1, start_char=offset, end_char=offset + len(content),
                              text_origin='digital_text_layer'))
        offset += len(content) + 1
    text.source_locations = locations
    db.commit()


PROFILE_IMPORTS = False


class SqlCounter:
    """SQL statements one step sends: reads, and per table the writes, rows and bytes of bound values."""

    def __init__(self, engine):
        from sqlalchemy import event
        self.engine, self.event = engine, event
        self.reset()

    def reset(self):
        self.statements, self.reads, self.writes = 0, 0, {}

    def _after(self, conn, cursor, statement, parameters, context, executemany):
        import re
        self.statements += 1
        verb = statement.lstrip().split(None, 1)[0].upper()
        if verb not in ('INSERT', 'UPDATE', 'DELETE'):
            self.reads += verb == 'SELECT'
            return
        match = re.search(r'(?:INTO|UPDATE|FROM)\s+"?(\w+)"?', statement, re.I)
        table = f"{verb.lower()} {match.group(1) if match else '?'}"
        entry = self.writes.setdefault(table, dict(statements=0, rows=0, bytes=0))
        entry['statements'] += 1
        batches = parameters if executemany else [parameters]
        # SQLite reports no row count for inserts: one row per bound value set.
        entry['rows'] += len(batches) if verb == 'INSERT' else max(cursor.rowcount or 0, 0)
        entry['bytes'] += sum(len(str(value)) for values in batches for value in
                              (values.values() if isinstance(values, dict) else values or ()))

    def __enter__(self):
        self.reset()
        self.event.listen(self.engine, 'after_cursor_execute', self._after)
        return self

    def __exit__(self, *_):
        self.event.remove(self.engine, 'after_cursor_execute', self._after)

    def report(self):
        return dict(statements=self.statements, reads=self.reads,
                    written_rows=sum(entry['rows'] for entry in self.writes.values()),
                    written_bytes=sum(entry['bytes'] for entry in self.writes.values()),
                    writes=dict(sorted(self.writes.items())))


def run(periods, imports):
    import asyncio
    from unittest.mock import AsyncMock
    from postgres.base import Base
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from postgres.models.evidence import IngestionLog
    from services.financial import import_batches as service
    from services.financial.statement_import import read_statement_import
    from services.financial.identity_graph import identity_graph_plan
    from sqlalchemy import select
    from tests.test_financial_statement_import import StatementImportTests
    fixture = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
    fixture.setUp()
    timings = dict(periods=periods)
    try:
        fixture.file.status = 'processed'
        Base.metadata.create_all(fixture.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__])
        fixture.db.commit()
        install(fixture, periods)
        started = time.perf_counter()
        with fixture.SessionLocal() as db:
            choices = read_statement_import(db, case_id=fixture.case.id, evidence_file_id=fixture.file.id)['statement_choices']
        timings['file_reading_cold'] = time.perf_counter() - started
        timings['choices'] = len(choices)
        with fixture.SessionLocal() as db:
            batch = service.create_batch(db, case_id=fixture.case.id, request_id=__import__('uuid').uuid4(),
                file_ids=[fixture.file.id], folder_ids=[], actor=fixture.actor)
        process = AsyncMock(side_effect=AssertionError('stored reading only'))
        started = time.perf_counter()
        for _ in range(4):
            asyncio.run(service.advance_batch(fixture.SessionLocal, batch, Path, process))
            with fixture.SessionLocal() as db:
                if db.get(Batch, batch).status != 'preparing':
                    break
        timings['prepare_all_periods'] = time.perf_counter() - started
        with fixture.SessionLocal() as db:
            items = list(db.scalars(select(Item).where(Item.batch_id == batch).order_by(Item.id)))
            timings['items'] = len(items)
            timings['items_ready'] = sum(item.status == 'ready' for item in items)
            timings['first_problems'] = [p.get('message') for p in items[0].summary.get('problems', [])][:5]
        # One receipt for every period, as the automatic save claims a file's
        # ready statements together: each import records its own outcome on it.
        from postgres.models.financial_import_batches import FinancialImportOperation as Operation
        operation_id = __import__('uuid').uuid4()
        with fixture.SessionLocal() as db:
            db.add(Operation(id=operation_id, case_id=fixture.case.id, batch_id=batch, expected_revision='benchmark',
                actor=dict(name='System', user_id=None), outcomes=[dict(item_id=str(i.id), file_id=str(i.file_id),
                    filename=i.summary.get('filename', ''), period_start=i.summary.get('period_start', ''),
                    period_end=i.summary.get('period_end', ''), status='queued') for i in items]))
            db.commit()
        steps = []
        # The synthetic periods print no account summary, so they never reconcile:
        # they are imported through the same writer with the admission policy
        # bypassed, as the tests seed historical data (confirm_legacy).
        from unittest.mock import patch
        from services.financial.statement_admission import assess_admission
        for item in items[:imports]:
            step = {}
            with fixture.SessionLocal() as db:
                proposal = read_statement_import(db, case_id=fixture.case.id, evidence_file_id=fixture.file.id,
                    currency='USD', statement_id=item.statement_key)
                record = db.get(Item, item.id)
                request = service.initial_request(proposal)
                request.update(currency='USD', holder=proposal['metadata']['holder'] or 'SAMPLE HOLDER')
                for row in request['rows']:
                    row['reason'] = row.get('reason') or 'Synthetic benchmark.'
                    if row.get('direction') is None and not row.get('excluded'):
                        row['direction'] = 'debit'
                record.status = 'pending_import'
                record.review_request = request
                record.summary = {**record.summary, 'revision': proposal['revision'], 'import_operation_id': str(operation_id),
                    'import_actor': dict(name=fixture.actor.name,
                    email=fixture.actor.email, user_id=str(fixture.actor.user_id))}
                db.commit()
            started = time.perf_counter()
            if PROFILE_IMPORTS:
                import cProfile
                profiler = cProfile.Profile(); profiler.enable()
            import logging
            lines = []
            handler = logging.Handler()
            handler.emit = lambda record: lines.append(record.getMessage())
            logger = logging.getLogger(service.__name__)
            logger.addHandler(handler)
            level = logger.level
            logger.setLevel(logging.INFO)
            try:
                with patch('services.financial.statement_admission.require_admission', side_effect=assess_admission), \
                        SqlCounter(fixture.db.get_bind()) as sql:
                    service._import_item(fixture.SessionLocal, fixture.case.id, batch, item.id, Path)
            finally:
                logger.removeHandler(handler)
                logger.setLevel(level)
            step['import'] = time.perf_counter() - started
            step['sql'] = sql.report()
            step['timing_line'] = [line for line in lines if line.startswith('Financial import timing')]
            if PROFILE_IMPORTS:
                profiler.disable()
                import io, pstats
                out = io.StringIO()
                pstats.Stats(profiler, stream=out).sort_stats('cumulative').print_stats(45)
                step['profile'] = out.getvalue().splitlines()
            with fixture.SessionLocal() as db:
                done = db.get(Item, item.id)
                step['imported'] = done.status == 'imported' or (done.summary.get('problems') or [{}])[0].get('message')
            started = time.perf_counter()
            swept = service.refresh_stale_readiness(fixture.SessionLocal, budget_seconds=600.0)
            step['readiness_sweep'] = time.perf_counter() - started
            step['swept'] = swept
            started = time.perf_counter()
            with fixture.SessionLocal() as db:
                identity_graph_plan(db, fixture.case.id)
            step['identity_plan'] = time.perf_counter() - started
            steps.append(step)
        timings['imports'] = steps
    finally:
        fixture.tearDown()
    return timings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--periods', type=int, default=60)
    parser.add_argument('--imports', type=int, default=5)
    parser.add_argument('--profile', action='store_true', help='cProfile each import (cumulative, top 45)')
    args = parser.parse_args(argv)
    global PROFILE_IMPORTS
    PROFILE_IMPORTS = args.profile
    print(json.dumps(run(args.periods, args.imports), indent=1, default=str))


if __name__ == '__main__':
    main()
