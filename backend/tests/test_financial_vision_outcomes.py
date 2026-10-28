"""Page-image reader decision logging (fin-holes A): every outcome is a journal line, an entry in the statement's
own outcome history (never overwriting the one before) and, for a held statement, a plain line in the queue."""
import logging
import unittest
from types import SimpleNamespace
from unittest import mock

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import vision_reader as vr
from services.financial.journal import journal


class FakeDb:
    """One evidence file, one batch, one item; ``scalar``/``get`` by the selected model."""

    def __init__(self, item, batch, file):
        self.objects = {Item: item, Batch: batch, EvidenceFile: file}
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def scalar(self, statement):
        return self.objects[statement.column_descriptions[0]['entity']]

    def get(self, model, key):
        return self.objects.get(model)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _setup(summary=None, metadata=None, status='attention'):
    item = SimpleNamespace(id='i1', batch_id='b1', file_id='f1', statement_key='k1', status=status,
                           summary=dict(summary or {}), review_request=None)
    batch = SimpleNamespace(id='b1', case_id='case-0001', status='review', files=[])
    file = SimpleNamespace(id='f1', metadata_=dict(metadata or {}))
    return FakeDb(item, batch, file)


class OutcomeLineTest(unittest.TestCase):
    def test_plain_words_for_every_kind(self):
        self.assertEqual(vr.outcome_line(dict(status='skipped', reason='investigator_work')),
                         'Not read from page images: you have saved work on it.')
        self.assertEqual(vr.outcome_line(dict(status='not_proved', message='This account has no saved statement.')),
                         'Read from page images: not accepted, because this account has no saved statement.')
        self.assertTrue(vr.outcome_line(dict(status='proved')).startswith('Read from page images: accepted.'))
        self.assertIn('budget', vr.outcome_line(dict(status='budget')))
        self.assertEqual(vr.outcome_line(dict(status='skipped', reason='something_new')),
                         'Not read from page images: something new.')
        for reason in vr.SKIP_WORDS:
            self.assertNotIn('_', vr.outcome_line(dict(status='skipped', reason=reason)))


class HistoryTest(unittest.TestCase):
    def test_outcomes_append_never_overwrite_and_repeats_count_up(self):
        db = _setup()
        first = dict(status='not_proved', message='A', at='2026-10-27T10:00:00', revision='r1', model='m')
        self.assertTrue(vr._record_outcome(db, 'f1', 'k1', first))
        self.assertFalse(vr._record_outcome(db, 'f1', 'k1', dict(first, at='2026-10-27T11:00:00')))
        self.assertTrue(vr._record_outcome(db, 'f1', 'k1', dict(status='skipped', reason='investigator_work',
                                                                 at='2026-10-27T12:00:00')))
        history = vr.outcomes(SimpleNamespace(metadata_=db.objects[EvidenceFile].metadata_), 'k1')
        self.assertEqual([h['status'] for h in history], ['not_proved', 'skipped'])
        self.assertEqual(history[0]['times'], 2)
        self.assertEqual(history[0]['at'], '2026-10-27T10:00:00')
        self.assertEqual(history[0]['last_at'], '2026-10-27T11:00:00')
        self.assertEqual(history[1]['line'], 'Not read from page images: you have saved work on it.')

    def test_history_is_bounded(self):
        db = _setup()
        for n in range(vr.OUTCOME_HISTORY + 5):
            vr._record_outcome(db, 'f1', 'k1', dict(status='not_proved', message=str(n), at=str(n)))
        history = db.objects[EvidenceFile].metadata_[vr.OUTCOMES_KEY]['k1']
        self.assertEqual(len(history), vr.OUTCOME_HISTORY)
        self.assertEqual(history[-1]['message'], str(vr.OUTCOME_HISTORY + 4))

    def test_the_reading_record_itself_is_untouched(self):
        db = _setup(metadata={vr.METADATA_KEY: {'k1': {'status': 'not_proved', 'raw': {}}}})
        vr._record_outcome(db, 'f1', 'k1', dict(status='skipped', reason='budget'))
        self.assertEqual(db.objects[EvidenceFile].metadata_[vr.METADATA_KEY], {'k1': {'status': 'not_proved', 'raw': {}}})


class ReadItemRecordsTest(unittest.TestCase):
    def test_a_skip_is_logged_recorded_and_shown_on_the_held_statement(self):
        db = _setup()
        with mock.patch.object(vr, '_read_item', return_value=dict(status='skipped', reason='investigator_work', at='t')), \
                self.assertLogs(vr.log, level='INFO') as logs:
            vr.read_item(lambda: db, 'i1', None)
        self.assertIn('Page-image reader: case case-000 file f1 statement k1: Not read from page images: you have '
                      'saved work on it. (investigator_work)', logs.output[0])
        self.assertEqual(vr.outcomes(db.objects[EvidenceFile], 'k1')[0]['reason'], 'investigator_work')
        shown = db.objects[Item].summary['vision_reading']
        self.assertEqual(shown['line'], 'Not read from page images: you have saved work on it.')
        self.assertEqual(db.commits, 1)

    def test_the_same_skip_again_writes_no_new_note(self):
        db = _setup()
        skip = dict(status='skipped', reason='prepared_by_older_reader', at='t')
        with mock.patch.object(vr, '_read_item', return_value=skip), self.assertLogs(vr.log, level='INFO'):
            vr.read_item(lambda: db, 'i1', None)
            db.objects[Item].summary = {'vision_reading': dict(db.objects[Item].summary['vision_reading'], marker=1)}
            vr.read_item(lambda: db, 'i1', None)
        self.assertEqual(db.objects[Item].summary['vision_reading'].get('marker'), 1)
        self.assertEqual(vr.outcomes(db.objects[EvidenceFile], 'k1')[0]['times'], 2)

    def test_a_final_outcome_is_recorded_but_its_note_left_to_finish(self):
        db = _setup(summary={'vision_reading': {'status': 'not_proved', 'message': 'kept'}})
        with mock.patch.object(vr, '_read_item', return_value=dict(status='not_proved', message='Other', at='t')), \
                self.assertLogs(vr.log, level='INFO') as logs:
            vr.read_item(lambda: db, 'i1', None)
        self.assertIn('not accepted, because other', logs.output[0])
        self.assertEqual(db.objects[Item].summary['vision_reading']['message'], 'kept')
        self.assertEqual(vr.outcomes(db.objects[EvidenceFile], 'k1')[0]['status'], 'not_proved')

    def test_a_failure_is_a_warning(self):
        db = _setup()
        with mock.patch.object(vr, '_read_item', return_value=dict(status='failed', message='timeout', at='t')), \
                self.assertLogs(vr.log, level='WARNING') as logs:
            vr.read_item(lambda: db, 'i1', None)
        self.assertTrue(logs.records[0].levelno == logging.WARNING)

    def test_measuring_records_nothing(self):
        db = _setup()
        with mock.patch.object(vr, '_read_item', return_value=dict(status='skipped', reason='not_held')):
            vr.read_item(lambda: db, 'i1', None, apply=False)
            vr.read_item(lambda: db, 'i1', None, apply=False, force=True)
        self.assertEqual(db.objects[EvidenceFile].metadata_, {})
        self.assertEqual(db.commits, 0)

    def test_passing_outcomes_are_not_recorded(self):
        db = _setup()
        with mock.patch.object(vr, '_read_item', return_value=dict(status='not_proved', reason='already_read')):
            vr.read_item(lambda: db, 'i1', None)
        self.assertEqual(db.objects[EvidenceFile].metadata_, {})

    def test_recording_never_raises(self):
        def broken():
            raise RuntimeError('db down')
        with mock.patch.object(vr, '_read_item', return_value=dict(status='skipped', reason='not_held')), \
                self.assertLogs(vr.log, level='ERROR'):
            self.assertEqual(vr.read_item(broken, 'i1', None)['reason'], 'not_held')


class SweepRoundTest(unittest.TestCase):
    def test_a_round_that_only_skipped_is_still_logged(self):
        outcomes = iter([dict(status='skipped', reason='investigator_work'), dict(status='skipped', reason='investigator_work'),
                         dict(status='not_proved', message='x', cost_usd=0.5), dict(status='budget')])

        class Factory:
            def __call__(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['a', 'b', 'c', 'd']), \
                mock.patch.object(vr, 'read_item', side_effect=lambda *a, **k: next(outcomes)), \
                self.assertLogs(vr.log, level='INFO') as logs:
            report = vr.sweep(Factory(), None)
        vr._skip_until.clear()
        self.assertEqual(report['skipped'], {'investigator_work': 2, 'budget': 1})
        self.assertEqual(report['not_proved'], 1)
        self.assertIn('Page-image reading round:', logs.output[-1])


class JournalTest(unittest.TestCase):
    def test_info_reaches_its_own_handler(self):
        logger = journal('services.financial.vision_reader')
        self.assertIs(logger, vr.log)
        self.assertEqual(logger.level, logging.INFO)
        self.assertFalse(logger.propagate)
        self.assertEqual(sum(getattr(h, '_loupe_journal', False) for h in logger.handlers), 1)
        journal('services.financial.vision_reader')  # idempotent
        self.assertEqual(sum(getattr(h, '_loupe_journal', False) for h in logger.handlers), 1)


class QueueLineTest(unittest.TestCase):
    def test_the_held_statement_shows_the_latest_outcome(self):
        from services.financial.review_queue import _entry
        item = SimpleNamespace(id='i1', file_id='f1', statement_key='k1', status='attention', summary={
            'filename': 'x.pdf', 'vision_reading': {'status': 'skipped', 'reason': 'investigator_work', 'message': '',
                                                    'line': 'Not read from page images: you have saved work on it.'}})
        entry = _entry(item, 'b1')
        self.assertEqual(entry['vision_reading']['line'], 'Not read from page images: you have saved work on it.')
        older = SimpleNamespace(**dict(vars(item), summary={'filename': 'x.pdf', 'vision_reading': {
            'status': 'not_proved', 'message': 'The statement period could not be read from the page images.'}}))
        self.assertEqual(_entry(older, 'b1')['vision_reading']['line'],
                         'Read from page images: not accepted, because the statement period could not be read from the page images.')


if __name__ == '__main__':
    unittest.main()


class SweepConcurrencyTest(unittest.TestCase):
    """A round reads a few statements at once (DeepSeek takes minutes each), never one twice, and starts none after
    its time is used."""

    class Factory:
        def __call__(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_reads_at_most_the_limit_at_once_and_each_once(self):
        import threading
        import time as real_time
        lock, live, seen = threading.Lock(), [0], []
        peak = [0]

        def read(factory, item_id, resolve_path):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
                seen.append(item_id)
            real_time.sleep(0.05)
            with lock:
                live[0] -= 1
            return dict(status='not_proved', message='x', cost_usd=0.01)
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), \
                mock.patch.object(vr, 'pending', return_value=[f'i{n}' for n in range(7)]), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            report = vr.sweep(self.Factory(), None, concurrency=3)
        vr._skip_until.clear()
        self.assertEqual(peak[0], 3)
        self.assertEqual(sorted(seen), sorted(f'i{n}' for n in range(7)))
        self.assertEqual(report['read'], 7)
        self.assertEqual(report['not_proved'], 7)

    def test_no_reading_starts_after_the_round_time_and_unavailable_stops_it(self):
        seen = []

        def read(factory, item_id, resolve_path):
            seen.append(item_id)
            return dict(status='unavailable', reason='unavailable')
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['a', 'b', 'c', 'd']), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            vr.sweep(self.Factory(), None, concurrency=1)
        self.assertEqual(seen, ['a'])
        seen.clear()
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['a', 'b']), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            vr.sweep(self.Factory(), None, budget_seconds=0, concurrency=2)
        vr._skip_until.clear()
        self.assertEqual(seen, [])

    def test_one_failing_statement_does_not_stop_the_round(self):
        def read(factory, item_id, resolve_path):
            if item_id == 'a':
                raise RuntimeError('boom')
            return dict(status='proved', cost_usd=0.01)
        vr._skip_until.clear()
        with mock.patch.object(vr, 'ENABLED', True), mock.patch.object(vr, 'pending', return_value=['a', 'b']), \
                mock.patch.object(vr, 'read_item', side_effect=read):
            report = vr.sweep(self.Factory(), None, concurrency=2)
        vr._skip_until.clear()
        self.assertEqual(report['proved'], 1)
