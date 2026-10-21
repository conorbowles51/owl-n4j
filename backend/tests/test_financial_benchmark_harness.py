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

    def test_two_statements_the_truth_tells_apart_are_not_saved_twice_even_with_equal_values(self):
        # Two quiet sections of one member: same account, dates and balances, no
        # payments, two printed statements (the real set has 16 such pairs).
        first_share = _truth('q.pdf#1', 'q.pdf', rows=[])
        second_share = _truth('q.pdf#2', 'q.pdf', rows=[])
        self.truths.update({t['id']: t for t in (first_share, second_share)})
        one, two = str(uuid.uuid4()), str(uuid.uuid4())
        periods = [_period('i1', first_share), _period('i2', second_share)]
        final = {'i1': dict(status='imported', source_document_id=one),
                 'i2': dict(status='imported', source_document_id=two)}
        ledger = self.verify(periods, final, {})
        self.assertEqual((ledger['printed_periods_saved_twice'], ledger['duplicate_contributions']), (0, 0))

    def test_a_saved_holder_other_than_the_printed_one_is_counted_apart_from_the_same_entity(self):
        names = dict(a='EJEMPLO SERVICIOS SA DE CV', b='EJEMPLO SERVICIOS S.A. DE C.V.', c='CALLE FALSA 12, CENTRO',
                     d='EJEMPLO SERVICIOS', e='')
        truths, periods, final, rows = {}, [], {}, {}
        for key in names:
            truth = _truth(key + '.pdf#1', key + '.pdf', holder='EJEMPLO SERVICIOS SA DE CV', holder_printed=True)
            truths[truth['id']] = truth
            periods.append(_period('i' + key, truth))
            final['i' + key] = dict(status='imported', source_document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, key)))
            rows[uuid.uuid5(uuid.NAMESPACE_URL, key)] = _rows(truth)
        unprinted = _truth('f.pdf#1', 'f.pdf', holder='OTRA PERSONA', holder_printed=False)
        truths[unprinted['id']] = unprinted
        periods.append(_period('if', unprinted))
        final['if'] = dict(status='imported', source_document_id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'f')))
        rows[uuid.uuid5(uuid.NAMESPACE_URL, 'f')] = _rows(unprinted)
        saved = {str(uuid.uuid5(uuid.NAMESPACE_URL, k)): v for k, v in dict(names, f='SOMEONE ELSE').items()}
        ledger = harness.verify_ledger(_Ledger(rows), periods, final, truths, TRANSACTION, object,
                                       lambda _model: _Query(), holder_of=saved.get)
        h = ledger['saved_holders']
        self.assertEqual((h['compared'], h['differs'], h['same_entity'], h['not_recorded']),
                         (5, ['c.pdf#1'], ['b.pdf#1', 'd.pdf#1'], ['e.pdf#1']))
        self.assertEqual(h['by_family'], {'generic': {'differs': 1, 'same_entity': 2, 'not_recorded': 1}})
        line = harness._holder_line(h)
        self.assertIn('differs from the printed holder 1: c.pdf#1', line)
        self.assertNotIn('CALLE', line)
        # A wrong holder is reported, not (yet) a safety failure: Neil decides the exit rule.
        result = dict(ledger=ledger, periods=periods, environment={})
        result['metrics'] = harness.metrics(result)
        self.assertEqual(harness.safety_failures(result), [])
        # Without a lookup (an older run) nothing is measured or reported.
        self.assertFalse(self.verify(periods[:1], final, rows)['saved_holders']['measured'])

    def test_a_real_truth_copy_names_its_original_period(self):
        copy = _truth('r.pdf#1', 'r.pdf', expected='duplicate', duplicate_of='a.pdf#1')
        self.assertEqual(harness.printed_statement(copy, {**self.truths, copy['id']: copy}), 'a.pdf#1')
        self.assertEqual(harness.printed_statement(self.copy, self.truths), 'a.pdf#1')

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


class ReadinessDrainTests(TestCase):
    """Scoring waits for the background readiness refresh, as the service's worker sweep would run it."""

    def drain(self, counts):
        counts, calls = iter(counts), []
        result = harness.drain_readiness(lambda: calls.append(1), lambda: next(counts), clock=lambda: 0.0)
        return result, len(calls)

    def test_refreshes_run_while_the_pending_count_falls(self):
        self.assertEqual(self.drain([35, 20, 3, 0]), (dict(before=35, after=0, rounds=3, quiet_rounds=0,
                                                          stopped='drained', seconds=0.0), 3))

    def test_a_round_that_settles_nothing_under_load_does_not_end_the_drain(self):
        # r10-copies under load: budgeted rounds that settle nothing between rounds that do.
        self.assertEqual(self.drain([44, 42, 42, 40, 40, 40, 37, 0]),
                         (dict(before=44, after=0, rounds=7, quiet_rounds=3, stopped='drained', seconds=0.0), 7))

    def test_only_consecutive_quiet_rounds_end_the_drain_and_what_is_left_is_reported(self):
        self.assertEqual(self.drain([5, 2, 2, 2, 2, 2, 2, 1]),
                         (dict(before=5, after=2, rounds=6, quiet_rounds=5, stopped='no_progress', seconds=0.0), 6))

    def test_a_count_that_grows_is_a_quiet_round(self):
        self.assertEqual(self.drain([3, 4, 0])[0]['quiet_rounds'], 1)

    def test_nothing_pending_runs_no_refresh(self):
        self.assertEqual(self.drain([0]), (dict(before=0, after=0, rounds=0, quiet_rounds=0, stopped='drained',
                                                seconds=0.0), 0))


class DrainSweepSaveTests(TestCase):
    def test_rounds_run_until_one_claims_nothing(self):
        rounds = iter([dict(queued=2, item_ids=['a', 'b']), dict(queued=1, item_ids=['c']), dict(queued=0, item_ids=[])])
        self.assertEqual(harness.drain_sweep_save(lambda: next(rounds), clock=lambda: 0.0),
                         dict(queued=3, item_ids=['a', 'b', 'c'], rounds=3, seconds=0.0))

    def test_bounded_by_rounds(self):
        result = harness.drain_sweep_save(lambda: dict(queued=1, item_ids=['x']), max_rounds=4, clock=lambda: 0.0)
        self.assertEqual((result['queued'], result['rounds']), (4, 4))


class SavedBySystemTests(TestCase):
    def test_only_items_claimed_by_the_system_actor(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        from services.financial.queue_save import SYSTEM_ACTOR
        items = [SimpleNamespace(id='s', summary=dict(import_actor=dict(name='System', email=SYSTEM_ACTOR.email))),
                 SimpleNamespace(id='p', summary=dict(import_actor=dict(name='Investigator', email='i@example.test'))),
                 SimpleNamespace(id='c', summary={})]
        db = SimpleNamespace(scalars=lambda _query: items)
        self.assertEqual(harness.saved_by_system(db, uuid.uuid4(), Item, SYSTEM_ACTOR), {'s'})


class SimulatedCorrectionTests(TestCase):
    """The simulation follows the product: a statement is read again once its currency is chosen."""

    truth = dict(currency='MXN', holder='EXAMPLE HOLDER', holder_printed=True, account='1234', account_printed=True,
                 institution='Example Bank', period_end='2024-01-31', period_start='2024-01-01', start_printed=True,
                 opening_minor=0, closing_minor=500, added_in='real',
                 rows=[dict(date='2024-01-10', amount_minor=500, direction='credit', description='EXAMPLE DEPOSIT')])

    @staticmethod
    def proposal(readable):
        row = dict(id='1:0:5', kind='transaction', excluded=False, issues=[] if readable else ['currency'],
                   fields=dict(description='EXAMPLE DEPOSIT', date='2024-01-10',
                               **(dict(amount_minor='500', direction='credit') if readable else {})))
        return dict(rows=[row] if readable else [], currency='' if not readable else 'MXN')

    @staticmethod
    def initial_request(proposal):
        return dict(currency=proposal['currency'], holder='EXAMPLE HOLDER', account_number='1234',
                    institution='Example Bank', period_start='2024-01-01', period_end='2024-01-31',
                    rows=[dict(id=r['id'], excluded=False, **{k: r['fields'].get(k) for k in
                          ('date', 'amount_minor', 'direction')}) for r in proposal['rows']])

    @staticmethod
    def assess(proposal, raw):
        ready = bool(raw['currency']) and len(raw['rows']) == 1
        return ('ready' if ready else 'attention'), dict(can_import=ready, problems=[])

    def test_rows_the_chosen_currency_makes_readable_are_not_counted_as_typed(self):
        asked = []

        def reread(currency):
            asked.append(currency)
            return self.proposal(readable=True)

        result = harness.simulate_correction(self.proposal(readable=False), self.truth, self.assess,
                                             self.initial_request, reread=reread)
        self.assertEqual(asked, ['MXN'])
        self.assertEqual([(a['kind'], a['field']) for a in result['actions']], [('decision', 'currency')])
        self.assertEqual((result['missing_rows'], result['resolved']), (0, True))

    def test_without_a_reread_or_when_it_fails_the_first_reading_is_kept(self):
        def failing(currency):
            raise ValueError('unreadable')

        for reread in (None, failing):
            with self.subTest(reread=reread):
                result = harness.simulate_correction(self.proposal(readable=False), self.truth, self.assess,
                                                     self.initial_request, reread=reread)
                self.assertEqual([(a['kind'], a['field']) for a in result['actions']],
                                 [('decision', 'currency'), ('add_row', 'missing_row')])
                self.assertEqual(result['missing_rows'], 1)

    def test_a_statement_that_has_its_currency_is_not_read_again(self):
        result = harness.simulate_correction(self.proposal(readable=True), self.truth, self.assess,
                                             self.initial_request, reread=lambda currency: self.fail('read again'))
        self.assertEqual(result['actions'], [])
