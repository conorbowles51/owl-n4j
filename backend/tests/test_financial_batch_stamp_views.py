"""Three cached Financial views read statement batches, but not what the release sweeps stamp on them.

After every release the reader-stamp and held-file sweeps rewrite batch rows for an hour or more (measured on live
2026-10-31 15:12-18:16: 228 of 236 batch writes on d5b330d1 and 49494305 changed only files[i].reader_stamp or
files[i].held_reprepare, plus updated_at). Each such write made the batch list (d5b330d1: 15.7 s to compute), the
financial evidence list and the ledger accounts compute again, so the next visitor waited or saw "updating" for a
change that shows nothing. These views are now fingerprinted by exactly the batch columns (and files keys) they read
(view_cache ``columns`` with ``Without``). This module proves the reads, three ways, on a real prepared batch:
- the batch columns each view reads (SQLite's authorizer for column reads; attribute reads on loaded batch rows),
- the keys it reads of any stored JSON (every JSON value is loaded as a dict that records key reads),
- and a mutation per unwatched column and key: the view's answer is byte-identical after it."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from sqlalchemy.orm.attributes import InstrumentedAttribute

from postgres.models.financial_import_batches import FinancialImportBatch as Batch
from services.financial import view_cache
import tests.test_financial_import_batches as batch_tests

STAMPED = ('reader_stamp', 'held_reprepare')
UNWATCHED_COLUMNS = ('updated_at', 'worker_token', 'lease_until')


class _Recorded(dict):
    """A stored JSON object that records every key read by name; reads of a batch file entry (the fixture stamps
    every one with reader_stamp) are also recorded on their own."""
    keys_read = set()
    file_keys_read = set()

    def _note(self, key):
        _Recorded.keys_read.add(key)
        if dict.__contains__(self, 'reader_stamp'):
            _Recorded.file_keys_read.add(key)

    def __getitem__(self, key):
        self._note(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._note(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._note(key)
        return super().__contains__(key)

    def pop(self, key, *default):
        self._note(key)
        return super().pop(key, *default)

    def setdefault(self, key, default=None):
        self._note(key)
        return super().setdefault(key, default)


def _views():
    from routers.evidence import list_evidence
    from routers.financial_ledger import get_candidate_accounts
    from routers.financial_statement_import import list_financial_batches
    return {
        'batches-list': lambda db, case: list_financial_batches.__wrapped__(case_id=case, db=db),
        'evidence-list': lambda db, case: list_evidence.__wrapped__(
            case_id=str(case), status_filter=None, include_cellebrite_artifacts=False, include_reading_versions=True,
            financial_only=True, db=db),
        'ledger-accounts': lambda db, case: get_candidate_accounts.__wrapped__(case_id=case, search='', offset=0, db=db),
    }


def _body(result):
    from fastapi.encoders import jsonable_encoder
    content = getattr(result, 'content', result)
    if isinstance(content, (bytes, bytearray)):
        content = json.loads(content)
    return json.dumps(jsonable_encoder(content), sort_keys=True, default=str)


class BatchStampViewTests(TestCase):
    def setUp(self):
        self.batches = batch_tests.BatchImportTests()
        self.batches.setUp()
        batch = self.batches.create()
        self.batches.advance(batch)
        self.f = self.batches.f
        from postgres.base import Base
        import postgres.models  # noqa: F401 - every model registered
        from postgres.models.activity_event import ActivityEvent  # noqa: F401
        from postgres.models.financial_candidates import FinancialCandidateMapping  # noqa: F401
        # The tables these views read that the batch fixture does not make (each a table SQLite can hold).
        for table in Base.metadata.sorted_tables:
            try:
                table.create(self.f.engine, checkfirst=True)
            except Exception:  # noqa: BLE001 - a PostgreSQL-only table no view here reads
                pass
        with self.f.SessionLocal() as db:
            row = db.get(Batch, batch)
            self.assertTrue(row.files and row.files[0].get('file_id'), 'a prepared batch file')
            # As the sweeps leave them on live: both stamps on every file.
            row.files = [{**entry, 'reader_stamp': 'reader-a', 'held_reprepare': {'stamp': 'a', 'state': 'done'}}
                         for entry in row.files]
            db.commit()
        self.batch = batch

    def tearDown(self):
        self.batches.tearDown()

    def compute(self, name):
        with self.f.SessionLocal() as db:
            return _body(_views()[name](db, self.f.case.id))

    @contextmanager
    def recording(self):
        """(columns read by SQL, attributes read on loaded batch rows); every JSON value loads as _Recorded."""
        engine = self.f.engine
        dialect = engine.dialect
        saved = dialect._json_deserializer
        dialect._json_deserializer = lambda value: json.loads(value, object_hook=_Recorded)
        dialect._type_memos.clear()
        engine.clear_compiled_cache()
        _Recorded.keys_read = set()
        _Recorded.file_keys_read = set()
        columns, attributes = set(), set()
        original_get = InstrumentedAttribute.__get__

        def get(attribute, instance, owner):
            if instance is not None and isinstance(instance, Batch):
                attributes.add(attribute.key)
            return original_get(attribute, instance, owner)

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table == 'financial_import_batches':
                columns.add(column)
            return sqlite3.SQLITE_OK

        @contextmanager
        def session():
            with self.f.SessionLocal() as db:
                raw = db.connection().connection.dbapi_connection
                raw.set_authorizer(authorize)
                try:
                    yield db
                finally:
                    raw.set_authorizer(None)
        InstrumentedAttribute.__get__ = get
        try:
            yield session, columns, attributes
        finally:
            InstrumentedAttribute.__get__ = original_get
            dialect._json_deserializer = saved
            dialect._type_memos.clear()
            engine.clear_compiled_cache()

    def watched(self, name):
        return view_cache._COLUMNS[name]['financial_import_batches']

    def test_each_view_reads_only_the_batch_columns_and_keys_it_is_fingerprinted_by(self):
        for name, view in _views().items():
            with self.subTest(view=name), self.recording() as (session, columns, attributes):
                with session() as db:
                    view(db, self.f.case.id)
                keys = set(_Recorded.keys_read)
                watched = self.watched(name)
                plain = {column for column in watched if isinstance(column, str)}
                files = [column for column in watched if isinstance(column, view_cache.Without)]
                allowed = plain | {column.column for column in files}
                self.assertTrue(columns, 'the view reads the batches')
                # A view that loads whole batch rows names every column in SQL; what it uses is what it reads of them.
                self.assertLessEqual(attributes, allowed, name)
                if not attributes:
                    self.assertLessEqual(columns, allowed, name)
                # The recorder is live (the views read files' ids), and no view reads a stamped key of any JSON.
                if name == 'batches-list':  # it loads whole rows: the attribute recorder is live
                    self.assertIn('files', attributes)
                if 'files' in attributes | columns:
                    # Read from the batches' own files entries, not some other stored JSON.
                    self.assertTrue(_Recorded.file_keys_read & {'file_id', 'source_id'}, _Recorded.file_keys_read)
                    self.assertFalse(_Recorded.file_keys_read & set(STAMPED))
                self.assertFalse(keys & set(STAMPED), (name, keys & set(STAMPED)))
                for column in files:
                    self.assertEqual(set(column.keys), set(STAMPED))

    def test_the_reads_are_as_recorded_here(self):
        # Any change in what these views read of a batch shows up here, so their watched columns are reconsidered.
        self.assertEqual(self.watched('ledger-accounts'), ('id', 'case_id', 'status'))
        self.assertEqual(self.watched('evidence-list'), ('id', 'case_id', view_cache.BATCH_FILES_UNSTAMPED))
        self.assertEqual(self.watched('batches-list'),
                         ('id', 'case_id', 'status', 'created_at', 'actor', view_cache.BATCH_FILES_UNSTAMPED))
        self.assertEqual(view_cache.BATCH_FILES_UNSTAMPED, view_cache.Without('files', *STAMPED))

    def mutate(self, change):
        with self.f.SessionLocal() as db:
            row = db.get(Batch, self.batch)
            change(row)
            db.commit()

    def test_a_write_to_an_unwatched_column_or_stamped_key_leaves_every_answer_byte_identical(self):
        later = datetime.now(timezone.utc) + timedelta(hours=1)
        mutations = {
            'updated_at': lambda row: setattr(row, 'updated_at', later),
            'worker_token': lambda row: setattr(row, 'worker_token', 'another-worker'),
            'lease_until': lambda row: setattr(row, 'lease_until', later),
            'files[].reader_stamp': lambda row: setattr(row, 'files', [
                {**entry, 'reader_stamp': 'reader-b'} for entry in row.files]),
            'files[].held_reprepare': lambda row: setattr(row, 'files', [
                {**entry, 'held_reprepare': {'stamp': 'b', 'state': 'left', 'reason': 'investigator_edits'}}
                for entry in row.files]),
            'files[] without the stamps': lambda row: setattr(row, 'files', [
                {key: value for key, value in entry.items() if key not in STAMPED} for entry in row.files]),
        }
        self.assertEqual(set(UNWATCHED_COLUMNS) | {'files'} | set(self.watched('batches-list')) - {
            view_cache.BATCH_FILES_UNSTAMPED} | {'created_by'},
            {column.name for column in Batch.__table__.columns}, 'every batch column is either watched or mutated here')
        for label, change in mutations.items():
            before = {name: self.compute(name) for name in _views()}
            self.mutate(change)
            for name in _views():
                with self.subTest(write=label, view=name):
                    self.assertEqual(self.compute(name), before[name])

    def test_a_watched_change_still_shows(self):
        # The control: the batch list counts a file whose prepared reading is gone as failed.
        before = self.compute('batches-list')
        self.mutate(lambda row: setattr(row, 'files', [{**entry, 'file_id': None} for entry in row.files]))
        self.assertNotEqual(self.compute('batches-list'), before)
