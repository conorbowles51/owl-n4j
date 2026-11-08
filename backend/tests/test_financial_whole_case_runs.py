"""Stored, paged whole-case runs: nothing dropped, every count true, nothing partial readable, a stopped run says so."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from postgres.models.enums import TransactionDirection
from services.financial import whole_case_runs as W
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_transfers import ledger_transfer_candidates
from tests import test_financial_ledger_transfers as _transfers


class Store(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        patcher = patch.dict(os.environ, FINANCIAL_VIEW_MEMO_DIR=self.folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        W.root().mkdir(parents=True)
        self.case = uuid4()

    def run_dir(self, sections, status='completed', **state):
        identifier = uuid4().hex
        directory = W.root() / identifier
        directory.mkdir()
        work = directory / W.RESULT
        work.mkdir()
        run = SimpleNamespace(phase=lambda *a, **k: None, done=lambda *a: None)
        counts, digest = W._write_sections(work, sections, run, 3, 3)
        W._write_state(directory, dict(id=identifier, kind='timeline', case_id=str(self.case), status=status, counts=counts, result_sha256=digest, heartbeat=time.time(), **state))
        return identifier, counts, digest

    def test_every_item_is_paged_with_its_true_total(self):
        identifier, counts, _ = self.run_dir(dict(rows=[(dict(n=n), None, None) for n in range(1234)]))
        seen = []
        for offset in range(0, 1234, 200):
            total, _, _, items = W.read_page(self.case, identifier, 'rows', offset=offset, limit=200)
            self.assertEqual(total, 1234)
            seen += [json.loads(i)['n'] for i in items]
        self.assertEqual(seen, list(range(1234)))
        self.assertEqual(counts['rows'], 1234)

    def test_a_page_never_exceeds_its_limit_and_past_the_end_is_empty(self):
        identifier, _, _ = self.run_dir(dict(rows=[(dict(n=n), None, None) for n in range(300)]))
        self.assertEqual(len(W.read_page(self.case, identifier, 'rows', limit=10_000)[3]), W.PAGE_LIMIT)
        total, _, _, items = W.read_page(self.case, identifier, 'rows', offset=999)
        self.assertEqual((total, items), (300, []))

    def test_a_subset_reads_only_its_items_with_its_own_count(self):
        identifier, counts, _ = self.run_dir(dict(graded=[(dict(n=n), 'weak' if n % 3 else 'strong', None) for n in range(9)]))
        total, _, _, items = W.read_page(self.case, identifier, 'graded@strong', limit=50)
        self.assertEqual((total, [json.loads(i)['n'] for i in items]), (3, [0, 3, 6]))
        self.assertEqual(counts['graded@weak'], 6)

    def test_search_counts_every_match_and_reads_values_not_field_names(self):
        rows = [(dict(n=n), '2024-01' if n < 3 else '2024-02', ('Rent paid' if n % 2 else 'Groceries', n)) for n in range(6)]
        identifier, _, _ = self.run_dir(dict(rows=rows))
        self.assertEqual(W.read_page(self.case, identifier, 'rows', search='RENT')[0], 3)
        self.assertEqual(W.read_page(self.case, identifier, 'rows', search='field')[0], 0)
        total, _, _, items = W.read_page(self.case, identifier, 'rows@2024-02', search='rent')
        self.assertEqual((total, [json.loads(i)['n'] for i in items]), (2, [3, 5]))

    def test_another_cases_run_reads_as_absent(self):
        identifier, _, _ = self.run_dir(dict(rows=[(dict(n=1), None, None)]))
        with self.assertRaises(FileNotFoundError):
            W.read_page(uuid4(), identifier, 'rows')
        with self.assertRaises(FileNotFoundError):
            W.read_run(uuid4(), identifier)

    def test_unsafe_names_are_refused(self):
        identifier, _, _ = self.run_dir(dict(rows=[(dict(n=1), None, None)]))
        for section in ('../state', 'rows/../../x', 'ROWS'):
            with self.assertRaises(W.WholeCaseRunError):
                W.read_page(self.case, identifier, section)
        with self.assertRaises(W.WholeCaseRunError):
            W.read_run(self.case, '../' + identifier)
        with self.assertRaises(FileNotFoundError):
            W.read_file(self.case, identifier, '../state.json')

    def test_an_unfinished_run_has_no_pages(self):
        identifier, _, _ = self.run_dir(dict(rows=[(dict(n=1), None, None)]), status='running', pid=os.getpid())
        with self.assertRaisesRegex(W.WholeCaseRunError, 'not finished'):
            W.read_page(self.case, identifier, 'rows')

    def test_a_run_whose_child_is_gone_says_it_stopped(self):
        seen = W.view(dict(id='a' * 32, status='running', pid=2 ** 22 + 7, heartbeat=time.time()))
        self.assertEqual(seen['status'], 'stopped')
        self.assertIn('Nothing partial', seen['error'])
        # The number was given to another process: this test's own, which is not the run's child. That
        # reads the same as a child short of its own program, so only a stale heartbeat settles it.
        stale = time.time() - W.STALE_HEARTBEAT_SECONDS - 1
        self.assertEqual(W.view(dict(id='a' * 32, status='running', pid=os.getpid(), heartbeat=stale))['status'], 'stopped')
        never = W.view(dict(id='a' * 32, status='queued', heartbeat=stale))
        self.assertEqual(never['status'], 'stopped')

    def test_a_child_not_yet_through_exec_is_not_called_stopped(self):
        # Popen can return before the child reaches its own program (posix_spawn); until then its
        # cmdline is the parent's or empty. This test's own process reads exactly that way: alive,
        # without the run id in its cmdline. A fresh heartbeat answers for the run.
        state = dict(id='c' * 32, status='running', pid=os.getpid(), heartbeat=time.time())
        self.assertEqual(W.view(state)['status'], 'running')

    def test_a_slow_living_child_is_not_called_stopped(self):
        identifier = 'b' * 32
        child = subprocess.Popen([sys.executable, '-c', 'import sys, time; print("up", flush=True); time.sleep(600)',
                                  identifier], stdout=subprocess.PIPE)
        try:
            # The line arrives only once the child runs its own program, so the reading below is of a
            # living child whose cmdline carries the run id, at any box load.
            self.assertEqual(child.stdout.readline(), b'up\n')
            state = dict(id=identifier, status='running', pid=child.pid)
            self.assertEqual(W.view({**state, 'heartbeat': time.time() - W.STALE_HEARTBEAT_SECONDS - 1})['status'], 'running')
            self.assertEqual(W.view({**state, 'heartbeat': time.time() - W.HUNG_HEARTBEAT_SECONDS - 1})['status'], 'stopped')
        finally:
            child.kill()
            child.wait()
            child.stdout.close()

    def test_equal_items_store_equal_digests(self):
        rows = [(dict(b=2, a=n), None, None) for n in range(5)]
        self.assertEqual(self.run_dir(dict(rows=rows))[2], self.run_dir(dict(rows=list(rows)))[2])

    def test_identity_follows_inputs_and_code(self):
        one = W.run_id('transfers', self.case, dict(population='working'))
        self.assertEqual(one, W.run_id('transfers', self.case, dict(population='working')))
        self.assertNotEqual(one, W.run_id('transfers', self.case, dict(population='verified')))
        with patch('services.financial.version.code_version', return_value='other'):
            self.assertNotEqual(one, W.run_id('transfers', self.case, dict(population='working')))

    def test_old_finished_runs_are_pruned_and_running_ones_kept(self):
        old, _, _ = self.run_dir(dict(rows=[(dict(n=1), None, None)]))
        live, _, _ = self.run_dir(dict(rows=[(dict(n=1), None, None)]), status='running', pid=os.getpid())
        stale = time.time() - W.KEEP_SECONDS - 10
        os.utime(W.root() / old / W.STATE, (stale, stale))
        W._prune(W.root(), W.root() / 'none')
        self.assertFalse((W.root() / old).exists())
        self.assertTrue((W.root() / live).exists())


class WholeCaseTransfers(_transfers._test_financial_ledger_summary.LedgerSummaryTests):
    capture = _transfers.LedgerTransferTests.capture
    pair = _transfers.LedgerTransferTests.pair

    def split_pair(self):
        """A debit on the last day of a month, its credit on the first of the next."""
        debit, credit = self.pair()
        split = debit.ordering_date.replace(day=28) + timedelta(days=4)
        split = split.replace(day=1)
        for row, day in ((debit, split - timedelta(days=1)), (credit, split)):
            row.ordering_date = row.transaction_date = day
            row.posted_date = row.value_date = row.effective_date = None
        self.db.commit()
        return debit, credit, split

    def test_a_pair_either_side_of_a_split_date_is_found_by_the_whole_case_run(self):
        from services.financial.ledger_snapshot import capture_ledger_snapshot
        debit, credit, split = self.split_pair()
        before = capture_ledger_snapshot(self.db, case_id=self.case.id, end_date=split - timedelta(days=1))
        after = capture_ledger_snapshot(self.db, case_id=self.case.id, start_date=split)
        for side in (before, after):
            keys = {r['row']['key'] for r in json.loads(side.content)['ledger']['readings']}
            self.assertEqual(len(keys & {str(debit.id), str(credit.id)}), 1)  # each narrower range holds one side only
        with patch('services.financial.ledger_transfers.MAX_TRANSFER_ROWS', 1):
            with self.assertRaises(LedgerSummaryError):
                ledger_transfer_candidates(self.capture())  # the old path above its limit: a refusal, no pair
            summary, sections = W.compute_transfers(self.capture(), dict(population='working', tolerance_days=3), None)
        self.assertEqual([(i[0]['debit_id'], i[0]['credit_id']) for i in sections['candidates']], [(str(debit.id), str(credit.id))])
        self.assertEqual(sections['candidates'][0][0]['debit']['key'], str(debit.id))

    def test_graded_pairs_stay_above_every_ceiling(self):
        self.pair()
        account = self._account(self.case.id, identity_key='third-account'); self.db.add(account); self.db.commit()
        doc = self.make_document(); period = self.make_period(doc, account=account)
        self.add_row(period, doc, amount=9007199254740993, account=account)
        with patch('services.financial.ledger_transfers.MAX_TRANSFER_PAIRS', 0):
            _, sections = W.compute_transfers(self.capture(), dict(population='working', tolerance_days=3), None)
        self.assertEqual(len(sections['candidates']), 2)
        self.assertEqual(len(sections['graded']), 2)
        self.assertEqual({i[1] for i in sections['graded']} <= {'strong', 'moderate', 'weak', 'faint'}, True)

    def test_a_whole_case_comparison_equals_the_answer_below_the_limit(self):
        self.pair()
        capture = self.capture()
        plain = ledger_transfer_candidates(capture, grade=True)
        summary, sections = W.compute_transfers(capture, dict(population='working', tolerance_days=3), None)
        strip = lambda item: {k: v for k, v in item[0].items() if k not in ('debit', 'credit')}
        self.assertEqual([strip(i) for i in sections['candidates']], plain['candidates'])
        self.assertEqual([strip(i) for i in sections['graded']], plain['graded']['pairs'])
        self.assertEqual([i[0] for i in sections['rows']], plain['rows'])
        self.assertEqual(summary['by_level'], plain['graded']['by_level'])
        self.assertEqual(summary['snapshot_sha256'], plain['snapshot_sha256'])


class PathWorkLimit(TestCase):
    def test_a_stopped_path_search_states_what_it_did_not_search(self):
        from tests.test_financial_pattern_review import PatternReviewTests
        import services.financial.pattern_review as P
        case = PatternReviewTests('test_optional_paths_retain_every_posting_and_candidate_pair')
        rows, pairs = case.path_fixture(returning=False)
        with patch('services.financial.ledger_transfers.ledger_transfer_candidates', return_value=dict(candidates=pairs)):
            whole = P.screen_ledger_patterns(case.capture(rows), cross_account=True, whole_case=True)
            with patch.object(P, 'MAX_WHOLE_CASE_PATH_EXTENSIONS', 0):
                stopped = P.screen_ledger_patterns(case.capture(rows), cross_account=True, whole_case=True)
        self.assertEqual(whole['paths_not_searched'], 0)
        self.assertIsNone(whole['paths_words'])
        self.assertEqual(stopped['paths_not_searched'], 2)
        self.assertIn('2 of 2 starting transfers were not searched', stopped['paths_words'])


class WholeCaseTimelineAndPatterns(TestCase):
    def capture(self, count):
        from services.financial.ledger_snapshot import LedgerScope
        readings = [dict(included=False, exclusion_reason='proof_class_not_included', account=dict(label='Account A'), source=dict(id='s'), provenance={},
                         row=dict(key='k%04d' % n, account_id='a', ordering_date='2024-01-15', transaction_date='2024-0%d-1%d' % (n % 3 + 1, n % 9), currency='USD',
                                  direction='debit' if n % 2 else 'credit', amount_minor=str(100 + n % 7), description='Payment %d' % n, proof_class='p3',
                                  to_name='DoorDash', from_name='Employer')) for n in range(count)]
        ledger = dict(case_id='case', account_id=None, start_date=None, end_date=None, history_captured=True, readings=readings)
        return LedgerScope(document=dict(ledger=ledger, decisions=[], export_ready=True), sha256='0' * 64)

    def test_timeline_keeps_every_payment_and_each_month_opens_to_its_rows(self):
        summary, sections = W.compute_timeline(self.capture(1500), dict(population='working'), None)
        self.assertEqual(len(sections['rows']), 1500)
        self.assertEqual(sum(m['payments'] for m in summary['months']), 1500)
        months = {m['month']: m['payments'] for m in summary['months']}
        for month, payments in months.items():
            self.assertEqual(sum(1 for _, subset, _ in sections['rows'] if subset == month), payments)
        credits = sum(int(m['totals']['USD']['credits_minor']) for m in summary['months'])
        self.assertEqual(credits, sum(int(i[0]['amount_minor']) for i in sections['rows'] if i[0]['direction'] == 'credit'))

    def test_patterns_page_every_group_above_the_old_limits(self):
        summary, sections = W.compute_patterns(self.capture(1500), dict(population='working', window_days=3), None)
        hypotheses = [i[0] for i in sections['hypotheses']]
        self.assertGreater(len(hypotheses), 200)
        self.assertEqual(sum(summary['by_kind'].values()), len(hypotheses))
        named = [h for h in hypotheses if h['kind'] == 'repeated_counterparty']
        self.assertEqual(sorted(h['counterparty_label'] for h in named), ['DoorDash', 'Employer'])
        for item in named:
            self.assertEqual(len(item['transaction_ids']), 750)  # above the old 50 per name
            self.assertEqual(item['sources_total'], 750)
            self.assertEqual(len(item['sources']), W.SOURCES_SHOWN)
            members = [m[0]['row']['key'] for m in sections['sources'][item['sources_start']:item['sources_start'] + item['sources_total']]]
            self.assertEqual(members, item['transaction_ids'])


from tests import test_financial_network_tracing as _network


class TraceWalk(_network.NetworkTracingTests):
    """The bounded trace: the same figures as the full calculation, read from the reached accounts only."""

    def walk_request(self, request, **changes):
        keep = ('expected_snapshot_sha256', 'population', 'tolerance_days', 'start_date', 'end_date', 'currency', 'pairs', 'openings',
                'basis', 'order_basis', 'attributions', 'doctrines', 'ordered_transaction_ids')
        return {**{key: request[key] for key in keep}, 'steps': 5, **changes}

    def test_every_reached_account_gives_the_full_calculations_figures(self):
        from services.financial.network_tracing import evaluate_network_trace
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        full = json.loads(evaluate_network_trace(export, request)['scenario_json'])
        summary, report = trace_walk(export, self.walk_request(request))
        walked = json.loads(report)
        for method, outcome in full['results'].items():
            self.assertEqual(walked['results'][method]['claims'], outcome['claims'])
            self.assertEqual(walked['results'][method]['hops'], outcome['hops'])
            self.assertEqual(walked['results'][method]['accounts'], outcome['accounts'])
        self.assertFalse(summary['stopped'])
        self.assertIsNone(summary['stop_words'])
        self.assertEqual(hashlib.sha256(report).hexdigest(), summary['scenario_sha256'])

    def test_a_stopped_trace_says_where_and_one_more_step_continues_it(self):
        from services.financial.trace_walk import trace_walk
        export, request, rows = self.network()
        keep = [o for o in request['openings']]
        summary, report = trace_walk(export, self.walk_request(request, steps=1, ordered_transaction_ids=None, openings=keep))
        self.assertTrue(summary['stopped'])
        self.assertEqual(summary['not_followed'], 1)
        self.assertEqual(summary['continue_with_steps'], 2)
        self.assertIn('Stopped after 1 step: 1 selected transfer out of', summary['stop_words'])
        self.assertEqual(len(summary['accounts']), 2)
        fifo = summary['methods']['first_in_first_out']['stops'][0]
        self.assertEqual(fifo['debit_id'], str(rows[4].id))
        self.assertEqual(fifo['claim_shares_minor'], {'claim': '6000'})
        further, _ = trace_walk(export, self.walk_request(request, steps=2, ordered_transaction_ids=None, openings=keep))
        self.assertFalse(further['stopped'])
        self.assertEqual(further['methods']['first_in_first_out']['claims'], self.fifo_claims(export, request))

    def test_a_claim_larger_than_its_payment_is_refused_in_words(self):
        from services.financial.ledger_summary import LedgerSummaryError
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        over = [{**a, 'amount_minor': '999999999'} for a in request['attributions']]
        with self.assertRaisesRegex(LedgerSummaryError, 'cannot be traceable to more'):
            trace_walk(export, self.walk_request(request, attributions=over))

    def fifo_claims(self, export, request):
        from services.financial.network_tracing import evaluate_network_trace
        return json.loads(evaluate_network_trace(export, request)['scenario_json'])['results']['first_in_first_out']['claims']

    def test_an_account_no_selected_transfer_reaches_is_not_read_and_needs_no_opening(self):
        from services.financial.trace_walk import trace_walk
        export, request, rows = self.network()
        summary, _ = trace_walk(export, self.walk_request(request, pairs=[], steps=3, ordered_transaction_ids=None, basis=''))
        self.assertEqual(len(summary['accounts']), 1)
        self.assertLess(summary['readings'], len(rows))

    def test_an_opening_is_required_for_every_reached_account(self):
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        with self.assertRaisesRegex(LedgerSummaryError, 'Declare an opening balance'):
            trace_walk(export, self.walk_request(request, openings=request['openings'][:1], ordered_transaction_ids=None))

    def test_a_same_day_credit_recorded_first_is_placed_after_its_debit_and_named(self):
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        ordered = list(request['ordered_transaction_ids'])
        ordered[2], ordered[3] = ordered[3], ordered[2]  # the first receipt before its debit, same day
        summary, report = trace_walk(export, self.walk_request(request, ordered_transaction_ids=ordered))
        self.assertEqual(summary['same_day_moves'], 1)
        self.assertEqual(json.loads(report)['same_day_moves'][0]['placed_after'], request['pairs'][0]['debit_id'])

    def test_reused_or_unproposed_pairs_are_refused(self):
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        with self.assertRaises(LedgerSummaryError):
            trace_walk(export, self.walk_request(request, pairs=request['pairs'] * 2))
        with self.assertRaises(LedgerSummaryError):
            trace_walk(export, self.walk_request(request, expected_snapshot_sha256='0' * 64))

    def test_an_asset_use_is_annotated_per_method_like_the_cross_account_trace_and_replays(self):
        from services.financial.network_tracing import evaluate_network_trace
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, rows = self.network()
        use = dict(transaction_id=str(rows[-1].id), asset_label='Synthetic equipment', basis='Explicit synthetic whole-payment use')
        full = json.loads(evaluate_network_trace(export, {**request, 'asset_uses': [use]})['scenario_json'])
        summary, report = trace_walk(export, self.walk_request(request, asset_uses=[use]))
        walked = json.loads(report)
        self.assertEqual(summary['asset_uses'], 1)
        for method, outcome in full['results'].items():
            self.assertEqual(walked['results'][method]['asset_uses'], outcome['asset_uses'])
            self.assertEqual(summary['methods'][method]['asset_uses'], outcome['asset_uses'])
        self.assertIn('asset-use hypotheses', ' '.join(walked['limitations']))
        self.assertEqual(replay_trace(report)['status'], 'matching_calculations')
        with self.assertRaisesRegex(LedgerSummaryError, 'not paired transfers'):
            trace_walk(export, self.walk_request(request, asset_uses=[{**use, 'transaction_id': request['pairs'][0]['debit_id']}]))

    def test_the_step_trace_takes_the_same_backward_timing_as_the_cross_account_trace(self):
        from datetime import date as _date
        from services.financial.network_tracing import evaluate_network_trace
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, rows = self.network()
        for row, day in zip(rows, [4, 4, 5, 1, 2, 2, 3]):
            row.transaction_date = row.ordering_date = _date(2026, 1, day)
            row.value_date = row.posted_date = row.effective_date = None
        self.db.commit()
        export = self.recapture()
        request.update(expected_snapshot_sha256=export.snapshot.sha256, tolerance_days=7,
                       ordered_transaction_ids=[str(rows[i].id) for i in (3, 4, 5, 6, 0, 1, 2)])
        with self.assertRaisesRegex(LedgerSummaryError, 'Forward tracing'):
            trace_walk(export, self.walk_request(request))
        with self.assertRaisesRegex(LedgerSummaryError, 'Explain the basis'):
            trace_walk(export, self.walk_request(request, allow_backward=True))
        basis = 'Synthetic earlier receiving credit linked explicitly to a later payer debit.'
        full = json.loads(evaluate_network_trace(export, {**request, 'allow_backward': True, 'backward_basis': basis})['scenario_json'])
        summary, report = trace_walk(export, self.walk_request(request, allow_backward=True, backward_basis=basis))
        walked = json.loads(report)
        self.assertTrue(walked['backward_timing_used'])
        self.assertTrue(summary['backward_timing_used'])
        self.assertEqual(walked['calculation_account_order'], full['calculation_account_order'])
        for method, outcome in full['results'].items():
            self.assertEqual(walked['results'][method]['claims'], outcome['claims'])
            self.assertEqual(walked['results'][method]['hops'], outcome['hops'])
            self.assertEqual(walked['results'][method]['accounts'], outcome['accounts'])
        self.assertEqual(replay_trace(report)['status'], 'matching_calculations')

    def test_a_backward_account_cycle_is_refused_without_a_partial_trace(self):
        from services.financial.trace_walk import trace_walk
        export, request, rows = self.network()
        rows[1].amount_minor = 2000  # the clean credit, so the cycle never touches the root attribution
        self.db.commit()
        export = self.recapture()
        request.update(expected_snapshot_sha256=export.snapshot.sha256)
        request['pairs'].append(dict(debit_id=str(rows[6].id), credit_id=str(rows[1].id)))
        with self.assertRaisesRegex(LedgerSummaryError, 'circular account dependency'):
            trace_walk(export, self.walk_request(request, allow_backward=True, backward_basis='Synthetic circular dependency',
                                                 ordered_transaction_ids=None))

    def test_enabling_backward_without_using_it_keeps_the_forward_figures(self):
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        _, forward = trace_walk(export, self.walk_request(request))
        summary, enabled = trace_walk(export, self.walk_request(request, allow_backward=True,
                                                                backward_basis='No backward pair is actually selected.'))
        self.assertFalse(summary['backward_timing_used'])
        self.assertEqual(json.loads(forward)['results'], json.loads(enabled)['results'])

    def test_a_step_trace_report_replays_with_identical_figures(self):
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        # steps=1 stops the trace, so the report must carry the rows its pairs name beyond the reached accounts.
        summary, report = trace_walk(export, self.walk_request(request, steps=1, ordered_transaction_ids=None))
        self.assertTrue(summary['stopped'])
        replay = replay_trace(report, expected_sha256=summary['scenario_sha256'])
        self.assertEqual(replay['status'], 'matching_calculations')
        self.assertEqual(replay['difference_count'], 0)
        self.assertEqual(replay['recalculated_sha256'], summary['scenario_sha256'])
        self.assertEqual(replay['snapshot_sha256'], summary['snapshot_sha256'])
        self.assertTrue(replay['independently_supplied_digest_checked'])
        whole, _ = trace_walk(export, self.walk_request(request))
        self.assertFalse(whole['stopped'])

    def test_a_complete_step_trace_report_also_replays(self):
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        summary, report = trace_walk(export, self.walk_request(request))
        replay = replay_trace(report)
        self.assertEqual(replay['status'], 'matching_calculations')
        self.assertEqual(replay['recalculated_sha256'], summary['scenario_sha256'])

    def test_a_tampered_step_trace_figure_is_reported_at_its_path(self):
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        _, report = trace_walk(export, self.walk_request(request))
        captured = json.loads(report)
        claim = sorted(captured['results']['first_in_first_out']['claims'])[0]
        captured['results']['first_in_first_out']['claims'][claim]['reported_remaining_minor'] = '1'
        replay = replay_trace(json.dumps(captured).encode())
        self.assertEqual(replay['status'], 'different_replay_output')
        self.assertEqual(replay['difference_paths'],
                         ['/results/first_in_first_out/claims/%s/reported_remaining_minor' % claim])

    def test_a_report_saved_before_replay_support_is_refused_in_words(self):
        from services.financial.trace_replay import replay_trace
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        _, report = trace_walk(export, self.walk_request(request))
        captured = json.loads(report)
        del captured['pair_rows']
        with self.assertRaisesRegex(LedgerSummaryError, 'before replay support'):
            replay_trace(json.dumps(captured).encode())

    def test_a_step_trace_report_is_not_a_support_archive_scenario_and_says_why(self):
        from services.financial.trace_support_archive import build_trace_support_archive
        from services.financial.trace_walk import trace_walk
        export, request, _ = self.network()
        _, report = trace_walk(export, self.walk_request(request))
        with self.assertRaisesRegex(LedgerSummaryError, 'Attach a ledger export'):
            build_trace_support_archive([report])


class TraceSources(_network.NetworkTracingTests):
    """The backward walk: every credit of a reached account is a followed transfer, a stated stop, or an outside source."""

    def sources_request(self, request, accounts, **changes):
        keep = ('expected_snapshot_sha256', 'population', 'tolerance_days', 'start_date', 'end_date', 'currency', 'pairs', 'basis')
        return {**{key: request[key] for key in keep}, 'account_ids': accounts, 'steps': 2, **changes}

    def test_every_credit_of_a_reached_account_is_counted_exactly_once(self):
        from services.financial.trace_walk import trace_sources
        export, request, rows = self.network()
        summary, sections = trace_sources(export, self.sources_request(request, [rows[5].account_id]))
        by_id = {a['account_id']: a for a in summary['accounts']}
        self.assertEqual(len(by_id), 3)
        start = by_id[str(rows[5].account_id)]
        self.assertEqual((start['steps_back'], start['transfers_in'], start['transfers_in_minor']), (0, 1, '6000'))
        middle = by_id[str(rows[3].account_id)]
        self.assertEqual((middle['steps_back'], middle['transfers_in'], middle['transfers_in_minor']), (1, 1, '10000'))
        origin = by_id[str(rows[0].account_id)]
        self.assertEqual((origin['steps_back'], origin['outside_credits'], origin['outside_credits_minor']), (2, 2, '20000'))
        self.assertEqual(summary['outside_credits'], 2)
        self.assertEqual(summary['transfers_in'], 2)
        self.assertEqual(summary['not_followed'], 0)
        self.assertFalse(summary['stopped'])
        self.assertIsNone(summary['stop_words'])
        credits = [r for r in (rows[0], rows[1], rows[3], rows[5])]
        self.assertEqual(summary['outside_credits'] + summary['transfers_in'] + summary['not_followed'], len(credits))
        self.assertEqual({row['key'] for row in sections['sources']}, {str(rows[0].id), str(rows[1].id)})
        self.assertEqual([t['from_account_label'] is not None for t in sections['transfers']], [True, True])

    def test_a_stopped_backward_walk_counts_and_states_what_it_did_not_follow(self):
        from services.financial.trace_walk import trace_sources
        export, request, rows = self.network()
        summary, sections = trace_sources(export, self.sources_request(request, [rows[5].account_id], steps=1))
        self.assertTrue(summary['stopped'])
        self.assertEqual(summary['not_followed'], 1)
        self.assertEqual(summary['continue_with_steps'], 2)
        self.assertIn('Stopped after 1 step back: 1 selected transfer into', summary['stop_words'])
        self.assertIn('Add one step to continue.', summary['stop_words'])
        self.assertEqual(summary['stops'][0]['debit_id'], request['pairs'][0]['debit_id'])
        self.assertEqual(len(summary['accounts']), 2)
        self.assertEqual(sections['sources'], [])
        self.assertEqual(len(sections['transfers']), 1)

    def test_unknown_accounts_reused_pairs_and_a_missing_basis_are_refused(self):
        from services.financial.trace_walk import trace_sources
        export, request, rows = self.network()
        with self.assertRaisesRegex(LedgerSummaryError, 'current readings'):
            trace_sources(export, self.sources_request(request, [str(uuid4())]))
        with self.assertRaises(LedgerSummaryError):
            trace_sources(export, self.sources_request(request, [rows[5].account_id], pairs=request['pairs'] * 2))
        with self.assertRaisesRegex(LedgerSummaryError, 'basis for transfer pairings'):
            trace_sources(export, self.sources_request(request, [rows[5].account_id], basis=''))
        with self.assertRaisesRegex(LedgerSummaryError, 'each account once'):
            trace_sources(export, self.sources_request(request, [rows[5].account_id, rows[5].account_id]))

    def test_the_stored_run_sections_page_sources_by_account(self):
        from services.financial.whole_case_runs import compute_sources
        export, request, rows = self.network()
        params = self.sources_request(request, [rows[5].account_id])
        summary, sections = compute_sources(export, {**params, 'case_id': str(self.case.id), 'run_id': 'x' * 32}, None)
        self.assertEqual(len(sections['sources']), 2)
        for row, subset, words in sections['sources']:
            self.assertEqual(subset, str(rows[0].account_id))
            self.assertIn(row['amount_minor'], ' '.join(str(w) for w in words))
        self.assertEqual(len(sections['transfers']), 2)


class ComputeTraceRequest(TestCase):
    def test_the_run_ids_do_not_reach_the_trace_input(self):
        from services.financial.trace_walk import TraceWalkInput
        request = dict(expected_snapshot_sha256='0' * 64, population='working', tolerance_days=3, currency='USD', order_basis='Recorded.',
                       doctrines=['lowest_intermediate_balance'], attributions=[dict(transaction_id=str(uuid4()), claim_id='claim', amount_minor='100', basis='Check.')])
        def walk(capture, given):
            TraceWalkInput.model_validate(given)
            return dict(ok=True), b'{}'
        with patch('services.financial.trace_walk.trace_walk', walk):
            summary, sections = W.compute_trace(None, {**request, 'case_id': 'case', 'run_id': 'a' * 32}, None)
        self.assertEqual(summary, dict(ok=True))

class ExportRun(Store):
    def state(self, status, **more):
        identifier = uuid4().hex
        directory = W.root() / identifier
        directory.mkdir()
        W._write_state(directory, dict(id=identifier, kind='export', case_id=str(self.case), status=status, params={}, heartbeat=time.time(), **more))
        return identifier, directory

    def test_a_stopped_or_failed_run_offers_nothing(self):
        for status in ('stopped', 'failed', 'running', 'queued'):
            identifier, directory = self.state(status, pid=os.getpid())
            (directory / '.export-x').mkdir()
            (directory / '.export-x' / W.EXPORT_FILE).write_bytes(b'part of an archive')
            with self.assertRaises(W.WholeCaseRunError):
                W.read_file(self.case, identifier, W.EXPORT_FILE)

    def test_a_run_whose_child_is_gone_says_it_stopped_and_offers_nothing(self):
        identifier, _ = self.state('running', pid=999999999)
        self.assertEqual(W.read_run(self.case, identifier)['status'], 'stopped')
        with self.assertRaises(W.WholeCaseRunError):
            W.read_file(self.case, identifier, W.EXPORT_FILE)

    def test_a_refusal_while_writing_publishes_nothing(self):
        identifier, directory = self.state('running')
        run = W._Run(directory, W._read_state(directory))
        capture = SimpleNamespace(snapshot=SimpleNamespace(sha256='s', byte_count=1), ledger_scope_sha256='l')
        with patch('services.financial.ledger_snapshot.ledger_export_archive', side_effect=LedgerSummaryError('Readable report exceeds 16 MiB')):
            with self.assertRaises(LedgerSummaryError):
                W.compute_export(capture, dict(case_id=str(self.case)), run)
        self.assertFalse((directory / W.RESULT).exists())

    def test_an_export_keeps_to_its_own_line_and_names_what_a_restart_keeps(self):
        self.assertIn('export', W.KINDS)
        self.assertIn('continues from them', W.RESTARTED[True])
        self.assertNotIn('continues', W.RESTARTED[False])
        self.assertNotEqual(W.EXPORT_LOCK_NAME, W.LOCK_NAME)

    def test_the_archive_is_described_from_its_own_bytes(self):
        import zipfile
        identifier, directory = self.state('running')
        run = W._Run(directory, W._read_state(directory))
        capture = SimpleNamespace(snapshot=SimpleNamespace(sha256='s', byte_count=1), ledger_scope_sha256='l')
        manifest = dict(generated_at='2026-11-05T10:00:00+00:00', included_rows=3, excluded_rows=1,
                        expert_support=dict(completeness='incomplete_expert_packet', parts=[], sentence='s'))
        def package(export, *, include_pdf, archive):
            archive.writestr('manifest.json', '{}')
            return manifest
        with patch('services.financial.ledger_snapshot.ledger_export_archive', side_effect=package):
            summary, sections = W.compute_export(capture, dict(case_id=str(self.case)), run)
        path = sections['paths'][W.EXPORT_FILE]
        self.assertEqual(summary['archive_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(summary['archive_bytes'], path.stat().st_size)
        self.assertEqual(summary['audit_events'], None)
        self.assertEqual(zipfile.ZipFile(path).namelist(), ['manifest.json'])

    def test_a_fresh_reading_replaces_a_stored_run_of_unchanged_rows(self):
        params = dict(privilege_marking='unmarked')
        directory = W.root() / W.run_id('export', self.case, params)
        directory.mkdir()
        W._write_state(directory, dict(id=directory.name, kind='export', case_id=str(self.case), status='completed', params=params, heartbeat=time.time()))
        with patch.object(W, '_current', return_value=True), patch.object(W.subprocess, 'Popen') as child:
            self.assertEqual(W.start_run(None, kind='export', case_id=self.case, params=params)['status'], 'completed')
            child.assert_not_called()
            child.return_value.pid = os.getpid()
            W.start_run(None, kind='export', case_id=self.case, params=params, fresh=True)
            child.assert_called_once()
            self.assertNotEqual(W._read_state(directory)['status'], 'completed')


class NumberedPdfParts(TestCase):
    def test_a_stopped_report_keeps_its_finished_parts(self):
        import zipfile
        from services.financial.ledger_pdf import MAX_PDF_READINGS
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, FINANCIAL_VIEW_MEMO_DIR=folder):
            capture = SimpleNamespace(snapshot=self.snapshot(MAX_PDF_READINGS + 5), ledger_scope_sha256='0' * 64)
            run = SimpleNamespace(phase=lambda *a, **k: None, after_publish=None)
            calls = []
            def render(part, html, part_words):
                calls.append(part_words)
                if len(calls) == 2:
                    raise RuntimeError('the server restarted')
                return b'%PDF-' + part_words.encode()
            params = dict(case_id='case', run_id='a' * 32)
            with patch('services.financial.ledger_snapshot.render_ledger_report', return_value='<h1>x</h1>'), patch('services.financial.ledger_pdf.render_ledger_pdf', render):
                with self.assertRaises(RuntimeError):
                    W.compute_pdf(capture, params, run)
                # A release changes the code version and so the run's name: the finished part is still found.
                summary, sections = W.compute_pdf(capture, {**params, 'run_id': 'b' * 32}, run)
            self.assertEqual(len(calls), 3)  # part 1 once, part 2 failed then written; never part 1 again
            self.assertEqual((summary['parts'], summary['readings']), (2, MAX_PDF_READINGS + 5))
            stream = __import__('io').BytesIO(sections['files']['ledger-report-parts.zip'])
            with zipfile.ZipFile(stream) as archive:
                manifest = json.loads(archive.read('parts-manifest.json'))
                self.assertTrue(manifest['covers_every_reading'])
                self.assertEqual(sorted(archive.namelist())[0], 'ledger-report-part-001-of-002.pdf')
            run.after_publish()
            self.assertEqual(list((W.root() / 'resume').iterdir()), [])

    def snapshot(self, count):
        from services.financial.ledger_snapshot import LedgerSnapshot
        readings = [dict(row=dict(key='k%05d' % n, ordering_date='2024-%02d-01' % (n % 12 + 1))) for n in range(count)]
        decisions = [dict(subject_type='transaction', subject_id='k00003', decision='d'), dict(subject_type='account', subject_id='a', decision='e')]
        content = json.dumps(dict(ledger=dict(readings=readings), decisions=decisions, investigation_notes=[1], exhibit_assessment=dict(a=1)))
        return LedgerSnapshot(content, 'x', len(content))

    def test_parts_cover_every_reading_exactly_once_in_date_order(self):
        from services.financial.ledger_pdf import MAX_PDF_READINGS, numbered_report_parts
        parts = list(numbered_report_parts(self.snapshot(MAX_PDF_READINGS * 2 + 7)))
        self.assertEqual([(p[0], p[1]) for p in parts], [(1, 3), (2, 3), (3, 3)])
        keys = [r['row']['key'] for p in parts for r in p[2]['ledger']['readings']]
        self.assertEqual(len(keys), MAX_PDF_READINGS * 2 + 7)
        self.assertEqual(len(set(keys)), len(keys))
        dates = [r['row']['ordering_date'] for p in parts for r in p[2]['ledger']['readings']]
        self.assertEqual(dates, sorted(dates))
        self.assertTrue(all(len(p[2]['ledger']['readings']) <= MAX_PDF_READINGS for p in parts))
        self.assertIn('Part 2 of 3: payments 2,001 to 4,000 of 4,007', parts[1][3])

    def test_a_decision_goes_with_its_payment_and_case_material_with_part_one(self):
        from services.financial.ledger_pdf import numbered_report_parts
        parts = list(numbered_report_parts(self.snapshot(2500)))
        decisions = [d for p in parts for d in p[2]['decisions']]
        self.assertEqual(sorted(d['subject_id'] for d in decisions), ['a', 'k00003'])
        self.assertIn('investigation_notes', parts[0][2])
        self.assertNotIn('investigation_notes', parts[1][2])
        self.assertIn('are in part 1', parts[1][3])
