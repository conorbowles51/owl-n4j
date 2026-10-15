"""The statement benchmark measures what the product does: automatic saves, copies, drains.

Synthetic values only; no corpus, engine or database is needed.
"""
import uuid
from collections import Counter
from types import SimpleNamespace
from unittest import TestCase

from benchmarks.statement_automation import harness


class _Column:
    def __eq__(self, value):
        return ('source', value)


class _Query:
    def __init__(self, condition=None):
        self.condition = condition

    def where(self, condition):
        return _Query(condition)


class _Ledger:
    """verify_ledger's database: transactions by source document, one account."""

    def __init__(self, rows):
        self.rows = rows

    def scalars(self, query):
        return list(self.rows.get(query.condition[1], []))

    def get(self, _model, _identifier):
        return SimpleNamespace(identifier_normalised='55501234', identifier_as_printed='55501234')


TRANSACTION = SimpleNamespace(source_document_id=_Column())


def _truth(truth_id, filename, expected='auto', **extra):
    rows = [dict(amount_minor=100 * n, direction='credit', date=f'2023-01-0{n}', description=f'Payment {n}')
            for n in (1, 2, 3)]
    return dict(dict(id=truth_id, filename=filename, family='generic', account='55501234', currency='USD',
                     period_start='2023-01-01', period_end='2023-01-31', opening_minor=0, closing_minor=600,
                     expected=expected, defects=[], rows=rows), **extra)


def _rows(truth):
    return [SimpleNamespace(amount_minor=r['amount_minor'], direction=r['direction'], currency='USD',
                            transaction_date=r['date'], posted_date=None, account_id='a', description=r['description'])
            for r in truth['rows']]


def _period(item_id, truth, **extra):
    return dict(dict(item_id=item_id, truth_id=truth['id'], filename=truth['filename'], status='ready',
                     can_import=True, expected=truth['expected'], family='generic', defects=[], reasons={},
                     scored=True), **extra)


class VerifyLedgerTests(TestCase):
    def setUp(self):
        self.original = _truth('a.pdf#1', 'a.pdf')
        self.copy = _truth('b.pdf#1', 'b.pdf', expected='duplicate', duplicate_of='a.pdf')
        self.truths = {t['id']: t for t in (self.original, self.copy)}

    def verify(self, periods, final_items, rows):
        return harness.verify_ledger(_Ledger(rows), periods, final_items, self.truths, TRANSACTION, object,
                                     lambda _model: _Query())

    def test_a_copy_shown_as_saved_through_the_originals_import_is_not_counted_twice(self):
        saved = str(uuid.uuid4())
        periods = [_period('i1', self.original), _period('i2', self.copy, can_import=False)]
        final = {'i1': dict(status='imported', source_document_id=saved),
                 'i2': dict(status='imported', source_document_id=saved)}
        ledger = self.verify(periods, final, {uuid.UUID(saved): _rows(self.original)})
        self.assertEqual((ledger['transactions'], ledger['admitted_periods']), (3, 1))
        self.assertEqual((ledger['duplicate_contributions'], ledger['items_sharing_a_saved_statement']), (0, 1))
        # Not a ledger copy, but the copy reads as saved: the run still fails.
        result = dict(ledger=ledger, periods=periods, environment={})
        result['metrics'] = harness.metrics(result)
        self.assertEqual(result['metrics']['overall']['duplicate_copies_saved'], 1)
        self.assertEqual(len(harness.safety_failures(result)), 1)

    def test_a_printed_period_saved_through_two_statements_is_a_duplicate_contribution(self):
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        periods = [_period('i1', self.original), _period('i2', self.copy)]
        final = {'i1': dict(status='imported', source_document_id=first),
                 'i2': dict(status='imported', source_document_id=second)}
        ledger = self.verify(periods, final, {uuid.UUID(first): _rows(self.original),
                                              uuid.UUID(second): _rows(self.copy)})
        self.assertEqual((ledger['duplicate_contributions'], ledger['printed_periods_saved_twice']), (3, 1))
        result = dict(ledger=ledger, periods=periods, environment={})
        result['metrics'] = harness.metrics(result)
        self.assertTrue(any('saved twice' in f for f in harness.safety_failures(result)))

    def test_repeated_payments_in_different_periods_are_not_duplicate_contributions(self):
        later = _truth('c.pdf#1', 'c.pdf', period_start='2023-02-01', period_end='2023-02-28')
        self.truths[later['id']] = later
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        periods = [_period('i1', self.original), _period('i3', later)]
        final = {'i1': dict(status='imported', source_document_id=first),
                 'i3': dict(status='imported', source_document_id=second)}
        ledger = self.verify(periods, final, {uuid.UUID(first): _rows(self.original),
                                              uuid.UUID(second): _rows(later)})
        self.assertEqual(ledger['duplicate_contributions'], 0)
        self.assertEqual(ledger['repeated_amount_date_rows'], 3)  # the coarse figure, informational


class MetricsTests(TestCase):
    def test_a_statement_saved_by_the_system_is_ready_and_judged_like_an_offered_one(self):
        auto = _truth('a.pdf#1', 'a.pdf')
        held = _truth('h.pdf#1', 'h.pdf', expected='hold')
        copy = _truth('b.pdf#1', 'b.pdf', expected='duplicate')
        periods = [_period('i1', auto, status='imported', auto_saved=True),
                   _period('i2', held, status='ready', can_import=False),
                   _period('i3', copy, status='duplicate_ignored', can_import=False)]
        result = dict(periods=periods, ledger=dict(wrongly_admitted=[], duplicate_contributions=0),
                      environment=dict(auto_save_ready=True))
        result['metrics'] = harness.metrics(result)
        overall = result['metrics']['overall']
        self.assertEqual((overall['ready_without_edits'], overall['saved_automatically']), (1, 1))
        self.assertEqual((overall['duplicate_copies_held_automatically'], overall['duplicate_copies_saved']), (1, 0))
        self.assertEqual(harness.safety_failures(result), [])
        # A held period the system saved is a wrong one, like any offered one.
        periods[1].update(status='imported', auto_saved=True, can_import=True)
        self.assertEqual(harness.metrics(result)['overall']['wrongly_ready'], ['h.pdf#1'])


class DrainTests(TestCase):
    def run_drain(self, states, **kwargs):
        clock = iter(range(0, 100000, 10))
        sequence = iter(states)
        turns = Counter()
        return harness.drain_batch(lambda: turns.update(['turn']), lambda: next(sequence), 'import',
                                   clock=lambda: next(clock), pause=lambda: turns.update(['pause']), **kwargs), turns['turn']

    def test_drains_until_the_batch_leaves_preparing_however_many_turns_it_takes(self):
        states = [('preparing', n) for n in range(5000)] + [('review', 'done')]
        result, turns = self.run_drain(states)
        self.assertEqual((result['final_status'], result['stalled'], turns), ('review', False, 5000))
        self.assertEqual(result['quiet_turns'], 0)

    def test_a_turn_that_moves_nothing_pauses_and_a_lease_length_quiet_spell_is_not_a_stall(self):
        # 31 quiet turns at 10 s each (310 s, longer than a 5-minute lease), then progress.
        states = [('preparing', 'a')] * 32 + [('preparing', 'b'), ('review', 'done')]
        result, turns = self.run_drain(states)
        self.assertEqual((result['final_status'], result['stalled'], result['quiet_turns']), ('review', False, 31))
        self.assertGreater(harness.STALL_SECONDS, 300)

    def test_stops_when_nothing_moves_for_enough_turns_and_time(self):
        states = [('preparing', 'same')] * 1000
        result, turns = self.run_drain(states, stall_turns=5, stall_seconds=200)
        self.assertTrue(result['stalled'])
        self.assertEqual(result['final_status'], 'preparing')
        self.assertLess(turns, 1000)
        # Five quiet turns are not enough while too little time has passed.
        self.assertGreater(turns, 5)


class SavedBySystemTests(TestCase):
    def test_only_items_claimed_by_the_system_actor(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        from services.financial.queue_save import SYSTEM_ACTOR
        items = [SimpleNamespace(id='s', summary=dict(import_actor=dict(name='System', email=SYSTEM_ACTOR.email))),
                 SimpleNamespace(id='p', summary=dict(import_actor=dict(name='Investigator', email='i@example.test'))),
                 SimpleNamespace(id='c', summary={})]
        db = SimpleNamespace(scalars=lambda _query: items)
        self.assertEqual(harness.saved_by_system(db, uuid.uuid4(), Item, SYSTEM_ACTOR), {'s'})
