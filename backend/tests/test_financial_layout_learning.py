"""Layout learning: proved page-image examples teach the text reader a layout, decided by exact re-reading and gates."""
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from services.financial import layout_learning as ll
from services.financial import learned_profiles as lp
from services.financial import statement_engine_profiles as sep

FIXTURES = Path(__file__).resolve().parent


def fixture(name):
    with open(FIXTURES / name) as handle:
        return json.load(handle)


def raw_document(rows, opening='100.00', closing='150.00', **values):
    account = dict(section_name='CHECKING', institution='Example Bank', holder='A PERSON', account_number='12345678',
                   currency='USD', currency_as_printed='$', period_start='2024-01-01', period_end='2024-01-31',
                   opening_balance=opening, closing_balance=closing, total_credits=None, total_debits=None,
                   count_credits=None, count_debits=None, rows=rows)
    account.update(values)
    return dict(pages=[dict(page=1, printed_page_number=1, printed_page_total=1, is_statement_page=True)],
                accounts=[account])


def row(day, amount, direction, **extra):
    return dict(dict(date='2024-01-%02d' % day, description='PAYMENT', amount=amount, direction=direction,
                     balance_after=None, unreadable=False, page=1, charge_kind=''), **extra)


class ExampleProofTests(unittest.TestCase):
    """Only the reading's own arithmetic makes an example; nothing from the text reader is used."""

    def examples(self, document):
        return ll.examples_of(dict(raw=document, pages=[1]), [1])

    def test_balanced_reading_is_an_example(self):
        (example, reason), = self.examples(raw_document([row(3, '70.00', 'credit'), row(9, '20.00', 'debit')]))
        self.assertEqual(reason, 'proved')
        self.assertEqual((example['opening_minor'], example['closing_minor'], len(example['rows'])), (10000, 15000, 2))
        self.assertEqual(example['convention'], 'asset_balance')
        self.assertEqual(example['account_digits'], '12345678')

    def test_a_cent_off_is_not_an_example(self):
        (example, reason), = self.examples(raw_document([row(3, '70.01', 'credit'), row(9, '20.00', 'debit')]))
        self.assertIsNone(example)
        self.assertIn('to the cent', reason)

    def test_printed_total_or_count_disagreeing_is_not_an_example(self):
        rows = [row(3, '70.00', 'credit'), row(9, '20.00', 'debit')]
        (example, reason), = self.examples(raw_document(rows, total_credits='71.00'))
        self.assertIsNone(example)
        (example, reason), = self.examples(raw_document(rows, count_debits='2'))
        self.assertIsNone(example)

    def test_uncertain_or_out_of_period_row_is_not_an_example(self):
        (example, _), = self.examples(raw_document([row(3, '70.00', 'credit', unreadable=True), row(9, '20.00', 'debit')]))
        self.assertIsNone(example)
        rows = [row(3, '70.00', 'credit'), dict(row(9, '20.00', 'debit'), date='2024-02-02')]
        (example, _), = self.examples(raw_document(rows))
        self.assertIsNone(example)


def example_from(values, file_id='f1', start_shift=0, pages=()):
    """A proved example as the page images would give it, built from a text reading's values."""
    start = values['period_start']
    if start_shift:
        start = (date.fromisoformat(start) + timedelta(days=start_shift)).isoformat()
    return dict(account_number=values['account'], account_digits=ll.vr._digits(values['account']),
                institution=values['institution'], holder=values['holder'], currency=values['currency'],
                currency_as_printed='$', period_start=start, period_end=values['period_end'],
                opening_minor=values['opening_minor'], closing_minor=values['closing_minor'],
                convention='asset_balance', pages=list(pages), exponent=2, printed_totals={},
                rows=[dict(date=d, direction=k, amount_minor=a, page=p) for d, k, a, p in values['rows']])


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(account='1470015292431', period_start='2023-10-14', period_end='2023-11-10',
                           opening_minor=100, closing_minor=50, holder='A PERSON', institution='Truist Bank',
                           currency='USD', proved=True, reason='proved',
                           rows=sorted([('2023-10-20', 'debit', 30, 1), ('2023-10-22', 'debit', 20, 1)]))

    def test_exact(self):
        self.assertEqual(ll.compare_example(example_from(self.values), [self.values]), 'exact')

    def test_start_the_day_after_the_previous_balance_is_reported(self):
        outcome = ll.compare_example(example_from(self.values, start_shift=-1), [self.values])
        self.assertEqual(outcome, 'exact (period starts the day after the printed previous balance)')
        # Not when a proved row is dated on the image's start day, nor for any other shift.
        example = example_from(self.values, start_shift=-1)
        example['rows'][0]['date'] = example['period_start']
        self.assertEqual(ll.compare_example(example, [self.values]), 'period not read')
        self.assertEqual(ll.compare_example(example_from(self.values, start_shift=-2), [self.values]), 'period not read')

    def test_amounts_must_agree_and_a_misread_image_date_is_reported(self):
        example = example_from(self.values)
        example['rows'][0]['amount_minor'] = 31
        self.assertTrue(ll.compare_example(example, [self.values]).startswith('rows differ'))
        # Two rows: 2% of them is no row, so even one differing date is a difference.
        example = example_from(self.values)
        example['rows'][0]['date'] = '2023-10-21'
        self.assertEqual(ll.compare_example(example, [self.values]), 'dates differ (1 rows)')
        # Fifty rows: one date may differ, by at most DATE_DAYS and inside the period.
        rows = sorted(('2023-10-%02d' % (15 + i % 10), 'debit', 100 + i, 1) for i in range(50))
        values = dict(self.values, rows=rows)
        example = example_from(values)
        example['rows'][0]['date'] = '2023-10-17' if example['rows'][0]['date'] != '2023-10-17' else '2023-10-18'
        self.assertEqual(ll.compare_example(example, [values]), 'exact (1 image date differ from the text)')
        example['rows'][0]['date'] = '2024-10-15'  # a year away: never a misread digit
        self.assertEqual(ll.compare_example(example, [values]), 'dates differ (1 rows)')

    def test_currency_comes_from_the_example_or_the_text_never_the_draft(self):
        example = dict(example_from(self.values), currency='')
        self.assertEqual(ll.compare_example(example, [self.values], 'USD'), 'exact')
        self.assertTrue(ll.compare_example(example, [dict(self.values, currency='MXN')], 'USD').startswith('currency differs'))
        self.assertTrue(ll.compare_example(example, [self.values], None).startswith('currency not proved'))
        self.assertEqual(ll.compare_example(example, [dict(self.values, currency='')], 'USD'), 'currency not read')
        self.assertEqual(ll.compare_example(example_from(self.values), [dict(self.values, closing_minor=None)]),
                         'closing not read')

    def test_balances_holder_and_unproved_are_differences(self):
        for key, value, outcome in (('closing_minor', 51, 'closing differs'), ('opening_minor', 1, 'opening differs'),
                                    ('holder', 'SOMEONE ELSE', 'holder differs'), ('proved', False, 'not proved')):
            read = dict(self.values, **{key: value})
            self.assertTrue(ll.compare_example(example_from(self.values), [read]).startswith(outcome), key)
        self.assertEqual(ll.compare_example(example_from(self.values), [dict(self.values, account='999')]), 'account not read')
        self.assertEqual(ll.compare_example(example_from(self.values), [self.values, self.values]), 'read twice')


class PickTests(unittest.TestCase):
    """A learned profile never displaces a written profile the document prints."""

    def test_written_profile_printed_in_the_furniture_wins(self):
        written = (dict(name='w', match=dict(all=['acme bank'])),)
        learned = (dict(name='l', match=dict(all=['statement of acme']), learned=True),)
        self.assertEqual(lp.pick('acme bank statement of acme', 'acme bank statement of acme', written, learned)['name'], 'w')

    def test_written_profile_matched_only_by_a_movement_line_gives_way(self):
        written = (dict(name='capital', match=dict(all=['capital one'])),)
        learned = (dict(name='l', match=dict(all=['truist.com', 'your previous balance as of']), learned=True),)
        text = 'truist.com your previous balance as of 10/13 | 10/20 | capital one payment'
        furniture = 'truist.com your previous balance as of'
        self.assertEqual(lp.pick(text, furniture, written, learned)['name'], 'l')
        self.assertEqual(lp.pick(text, furniture, written, ())['name'], 'capital')

    def test_no_learned_profile_is_today(self):
        written = (dict(name='w', match=dict(all=['acme bank'])),)
        self.assertEqual(lp.pick('acme bank', None, written, ())['name'], 'w')
        self.assertIsNone(lp.pick('other', None, written, ()))


class KeyedTests(unittest.TestCase):
    def test_two_drafts_never_share_a_reading(self):
        """The engine keeps readings by (file, profile name): each draft is read under a name carrying its rules."""
        a = ll.keyed(dict(name='learned-x', match=dict(all=['x'])))
        b = ll.keyed(dict(name='learned-x', match=dict(all=['x']), direction_headings=True))
        self.assertNotEqual(a['name'], b['name'])
        self.assertEqual(ll.keyed(a)['name'], a['name'])
        self.assertTrue(a['name'].startswith('learned-x~'))


class TruistLearnedFromExamplesTests(unittest.TestCase):
    """The written Truist profile off, the loop learns the layout back from proved examples alone."""

    @classmethod
    def setUpClass(cls):
        cls.sources = fixture('financial_truist_consolidated_fixture.json')
        hand = [ll.statement_values(s) for s in ll.text_reading(cls.sources)[0]]
        cls.hand = [v for v in hand if v['proved']]
        # The page images print the previous balance's date as the start (the day before the text reader's).
        cls.files = [dict(file_id='truist-fixture', sources=cls.sources, lines=ll.text_lines(cls.sources),
                          examples=[dict(example_from(v, start_shift=-1, pages=sorted({s['page_number'] for s in cls.sources})),
                                         institution='Truist') for v in cls.hand])]
        other = fixture('financial_truist_checks_fixture.json')
        cls.corpus_phrases = {'other-bank': ll.cell_phrases(ll.text_lines(fixture('financial_truist_business_fixture.json'))),
                              'truist-checks': ll.cell_phrases(ll.text_lines(other))}
        cls.off = mock.patch.object(sep, 'PROFILES_OFF', set(sep.PROFILES_OFF) | {'truist-consolidated'})
        cls.off.start()

    @classmethod
    def tearDownClass(cls):
        cls.off.stop()

    def test_hand_profile_off_reads_nothing_proved(self):
        self.assertTrue(self.hand)
        plain = [ll.statement_values(s) for s in ll.text_reading(self.sources)[0]]
        self.assertFalse(any(v['proved'] for v in plain))

    def test_learned_profile_reads_every_example_exactly(self):
        profile, result, notes = ll.draft(self.files, self.files, self.corpus_phrases, 'learned-truist-test')
        self.assertEqual(result['exact'], result['total'], result['examples'])
        self.assertTrue(profile.get('account_number_heading'))
        self.assertTrue(profile.get('direction_headings'))
        self.assertEqual(profile.get('currency'), 'USD')
        with ll.candidate(profile):
            learned = [ll.statement_values(s) for s in ll.text_reading(self.sources)[0]]
        for h in self.hand:
            same = [v for v in learned if (v['account'], v['period_start'], v['period_end']) ==
                    (h['account'], h['period_start'], h['period_end'])]
            self.assertEqual(len(same), 1)
            self.assertTrue(same[0]['proved'])
            for key in ('rows', 'opening_minor', 'closing_minor', 'holder', 'currency'):
                self.assertEqual(same[0][key], h[key], key)

    def test_corpus_gate_counts_changes_only_where_the_pick_changes(self):
        profile, _, _ = ll.draft(self.files, self.files, self.corpus_phrases, 'learned-truist-test')
        other = fixture('financial_truist_checks_fixture.json')
        result = ll.corpus_gate(profile, [('truist', 'case', self.sources), ('other', 'case', other)])
        self.assertEqual(result['files'], 2)
        self.assertTrue(result['passed'])
        self.assertEqual([e['file'] for e in result['rematched']], ['truist'])
        self.assertEqual(len(result['gained']), len(self.hand))

    def test_a_written_profile_the_file_prints_keeps_the_file(self):
        sep.PROFILES_OFF.discard('truist-consolidated')
        try:
            other = dict(name='learned-other', match=dict(all=['truist.com']), currency='EUR')
            result = ll.corpus_gate(other, [('truist', 'case', self.sources)])
            self.assertTrue(result['passed'])
            self.assertEqual(result['rematched'], [])
        finally:
            sep.PROFILES_OFF.add('truist-consolidated')


class GateRefusalTests(unittest.TestCase):
    def test_empty_truth_set_is_never_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ll.truth_gate([], lambda f: [], directory, dict(documents=[]))
        self.assertFalse(result['passed'])
        self.assertIn('No tier-A truth', result['reason'])

    def test_incomplete_or_stale_corpus_is_refused(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('learn_cli', Path(__file__).resolve().parents[1] / 'scripts' /
                                                      'financial_learn_layouts.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('no manifest', cli.manifest_problem(directory))
            now = datetime.now(timezone.utc)
            Path(directory, 'a.pkl').write_bytes(b'')
            Path(directory, 'manifest.json').write_text(json.dumps(dict(dumped_at=now.isoformat(), expected=3,
                                                                        errors={'b': 'PdfMappingError: x'})))
            self.assertIn('2 of 3', cli.manifest_problem(directory))
            Path(directory, 'c.pkl').write_bytes(b'')
            self.assertIsNone(cli.manifest_problem(directory))
            self.assertIn('hours ago', cli.manifest_problem(directory, now=now + timedelta(hours=25)))
            Path(directory, 'manifest.json').write_text(json.dumps(dict(dumped_at=now.isoformat(), expected=3,
                                                                        errors={'b': 'OperationalError: x'})))
            self.assertIn('could not be dumped', cli.manifest_problem(directory))


class OverlapTests(unittest.TestCase):
    def test_the_same_money_under_another_start_or_currency_overlaps(self):
        a = dict(account_reference='1470015292431', period_start='2023-10-13', period_end='2023-11-10')
        self.assertTrue(ll._overlaps(a, dict(a, period_start='2023-10-14')))
        self.assertTrue(ll._overlaps(a, dict(a, account_reference='****2431')))
        self.assertFalse(ll._overlaps(a, dict(a, period_start='2023-11-11', period_end='2023-12-12')))
        self.assertFalse(ll._overlaps(a, dict(a, account_reference='4470005569061')))

    def test_a_second_served_copy_of_a_period_fails_the_gate(self):
        sources = fixture('financial_truist_consolidated_fixture.json')
        served = ['{"account_reference": "1470015292431", "period_end": "2024-05-13", "period_start": "2024-04-12"}']
        calls = iter([served, served + ['{"account_reference": "1470015292431", "period_end": "2024-05-13", '
                                        '"period_start": "2024-04-11", "currency": "EUR"}']])
        with mock.patch.object(ll, '_matched', side_effect=[None, 'learned-x']), \
                mock.patch.object(ll, '_read_with', return_value=[]), \
                mock.patch.object(ll, '_catalog_with', side_effect=lambda *a: next(calls)):
            result = ll.corpus_gate(dict(name='learned-x', match=dict(all=['x'])), [('f', 'c', sources)])
        self.assertFalse(result['passed'])
        self.assertEqual(result['served_changed'][0]['overlapping'], 1)

    def test_two_new_overlapping_statements_fail_the_gate(self):
        new = ['{"account_reference": "", "period_end": "2024-01-31", "period_start": "2024-01-01"}',
               '{"account_reference": "1234", "period_end": "2024-01-31", "period_start": "2024-01-02"}']
        calls = iter([[], new])
        with mock.patch.object(ll, '_matched', side_effect=[None, 'learned-x']), \
                mock.patch.object(ll, '_read_with', return_value=[]), \
                mock.patch.object(ll, '_catalog_with', side_effect=lambda *a: next(calls)):
            result = ll.corpus_gate(dict(name='learned-x', match=dict(all=['x'])), [('f', 'c', [])])
        self.assertFalse(result['passed'])

    def test_an_unreadable_file_fails_the_gate_with_its_reason(self):
        with mock.patch.object(ll, '_matched', side_effect=[None, 'learned-x']), \
                mock.patch.object(ll, '_read_with', side_effect=RuntimeError('boom')):
            result = ll.corpus_gate(dict(name='learned-x', match=dict(all=['x'])), [('f', 'c', [])])
        self.assertFalse(result['passed'])
        self.assertIn('boom', result['lost'][0]['error'])


class CostTests(unittest.TestCase):
    def test_an_answer_without_usage_is_charged_its_reservation(self):
        file = mock.Mock(id='f1', stored_path='/x.pdf', metadata_={})
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(ll.vr, 'approved', return_value=True), \
                mock.patch.object(ll.vr, 'render_pages', return_value=[(1, [b'png'])]), \
                mock.patch.object(ll.vr, '_reserve', return_value=True), \
                mock.patch.object(ll.vr, '_add_spend') as spend:
            reading, cost = ll.read_file_images(None, 'case', file, [1], budget=5, resolve_path=Path, directory=directory,
                                                page_reader=lambda db, case: ('gpt-5.6-terra', lambda images: ({}, {})))
        reserved = ll.vr.reserve_usd('gpt-5.6-terra', [(1, [b'png'])])
        self.assertEqual(cost, reserved)
        spend.assert_called_once_with('case', 0)
        self.assertTrue(reading['requested'])


class LlmDraftTests(unittest.TestCase):
    def test_proposals_are_tested_and_answered_with_the_misses(self):
        files = [dict(file_id='f', sources=[], lines=[dict(page=1, text='A | B')],
                      examples=[example_from(dict(account='1', period_start='2024-01-01', period_end='2024-01-31',
                                                  opening_minor=0, closing_minor=0, holder='', institution='',
                                                  currency='USD', rows=[]))])]
        prompts = []
        answers = iter([{'profile': {'match': {'all': ['a']}, 'nonsense_key': 1}},
                        {'profile': {'match': {'all': ['a']}}}])

        def ask(provider, model, prompt, api_key):
            prompts.append(prompt)
            return next(answers), dict(prompt_tokens=10, completion_tokens=5, cost_usd=0.001), 0.1
        with mock.patch.object(ll, 'check', return_value=dict(examples=[('f', '1', 's', 'e', 'account not read')],
                                                             exact=0, total=1)):
            profile, result, log = ll.llm_draft(files, 'learned-x', 'deepseek', 'deepseek-v4-pro', 'k',
                                                attempts=3, ask=ask)
        self.assertEqual([e['outcome'] for e in log][:2], ['invalid', '0/1 exact'])
        self.assertIn('rejected', prompts[1])
        self.assertEqual(profile['name'], 'learned-x')
        self.assertIn('account not read', prompts[2]) if len(prompts) > 2 else None
        self.assertIn(sep.__doc__.splitlines()[0], prompts[0])


class RegistryTests(unittest.TestCase):
    def test_live_entries_only_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'learned_profiles.json'
            a = dict(name='learned-a-' + lp.rules_hash(dict(match=dict(all=['a'])))[:12], match=dict(all=['a']))
            passed = dict(gates=dict(corpus_passed=True, truth_passed=True, rules_hash=lp.rules_hash(a), profiles_off=[],
                                     corpus_dumped_at='2026-10-28T00:00:00+00:00'), review='PASS', fingerprint='fa')
            path.write_text(json.dumps(dict(version=2, profiles=[
                dict(a, learned=dict(passed, state='live', version=1, rules_hash=lp.rules_hash(a))),
                dict(name='learned-b', match=dict(all=['b']), learned=dict(state='draft_failed', version=1)),
                dict(name='learned-c', match=dict(all=['c']))])))
            with mock.patch.object(lp, 'REGISTRY', path):
                lp._LOADED.clear()
                self.assertEqual([p['name'] for p in lp.live()], [a['name']])
                with mock.patch.object(lp, 'LEARNED_OFF', {a['name']}):
                    self.assertEqual(lp.profiles(), ())
            for broken in (dict(a, learned=dict(state='live', rules_hash=lp.rules_hash(a))),  # no gates on record
                           dict(a, learned=dict(passed, gates=['x'], state='live', rules_hash=lp.rules_hash(a))),
                           dict(a, match=dict(all=['edited']), learned=dict(passed, state='live',
                                                                            rules_hash=lp.rules_hash(a))),
                           dict(a, unknown_rule=True, learned=dict(passed, state='live',
                                                                   rules_hash=lp.rules_hash(dict(a, unknown_rule=True))))):
                # One refused entry is never served; the registry's other entries still are.
                path.write_text(json.dumps(dict(version=3, profiles=[broken, dict(a, learned=dict(
                    passed, state='live', rules_hash=lp.rules_hash(a)))])))
                with mock.patch.object(lp, 'REGISTRY', path), self.assertLogs('services.financial.learned_profiles', 'ERROR'):
                    lp._LOADED.clear()
                    self.assertEqual([p['name'] for p in lp.live()], [a['name']])
                self.assertEqual(len(lp.problems(path)), 1)
            renamed = dict(a, name='learned-a')  # a name without its rules' hash
            path.write_text(json.dumps(dict(profiles=[dict(renamed, learned=dict(passed, state='live',
                                                                                 rules_hash=lp.rules_hash(renamed)))])))
            self.assertIn('rules hash', lp.problems(path)[0][1])
            # A gate result from a backtest (a profile switched off) never releases an entry.
            backtest = dict(passed, gates=dict(passed['gates'], profiles_off=['truist-consolidated']))
            path.write_text(json.dumps(dict(profiles=[dict(a, learned=dict(backtest, state='live',
                                                                           rules_hash=lp.rules_hash(a)))])))
            self.assertIn('every profile on', lp.problems(path)[0][1])
            # A match printing nothing would match every document.
            empty = dict(name='learned-e-' + lp.rules_hash(dict(match={}))[:12], match={})
            path.write_text(json.dumps(dict(profiles=[dict(empty, learned=dict(
                passed, gates=dict(passed['gates'], rules_hash=lp.rules_hash(empty)), state='live',
                rules_hash=lp.rules_hash(empty)))])))
            self.assertIn('non-empty list', lp.problems(path)[0][1])
            # Two live versions of one layout: neither is served.
            b = dict(name='learned-b-' + lp.rules_hash(dict(match=dict(all=['b'])))[:12], match=dict(all=['b']))
            entry = lambda x: dict(x, learned=dict(passed, gates=dict(passed['gates'], rules_hash=lp.rules_hash(x)),
                                                   state='live', rules_hash=lp.rules_hash(x)))
            path.write_text(json.dumps(dict(profiles=[entry(a), entry(b)])))
            with mock.patch.object(lp, 'REGISTRY', path), self.assertLogs('services.financial.learned_profiles', 'ERROR'):
                lp._LOADED.clear()
                self.assertEqual(lp.live(), ())
            # An unreadable registry serves no learned profile and raises nothing.
            path.write_text('{not json')
            with mock.patch.object(lp, 'REGISTRY', path), self.assertLogs('services.financial.learned_profiles', 'ERROR'):
                lp._LOADED.clear()
                self.assertEqual(lp.live(), ())
        lp._LOADED.clear()

    def test_shipped_registry_is_valid(self):
        self.assertEqual(lp.problems(), [])


if __name__ == '__main__':
    unittest.main()


class EngineHookTests(unittest.TestCase):
    """The engine consults the registry through statement_engine_profiles.matching_profile and profile_named."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'learned_profiles.json'
        patcher = mock.patch.object(lp, 'REGISTRY', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        lp._LOADED.clear()
        self.addCleanup(lp._LOADED.clear)

    def entry(self, phrase, state='live', fingerprint='f1'):
        rules = dict(match=dict(all=[phrase]), currency='USD')
        name = 'learned-%s-%s' % (fingerprint, lp.rules_hash(rules)[:12])
        rules = dict(rules, name=name)
        return dict(rules, learned=dict(state=state, fingerprint=fingerprint, rules_hash=lp.rules_hash(rules), review='PASS',
                                        gates=dict(corpus_passed=True, truth_passed=True, rules_hash=lp.rules_hash(rules),
                                                   profiles_off=[], corpus_dumped_at='2026-10-28T00:00:00+00:00')))

    def write(self, *entries):
        self.path.write_text(json.dumps(dict(version=1, profiles=list(entries))))
        lp._LOADED.clear()

    def test_without_learned_profiles_the_pick_is_the_written_rule(self):
        for path in sorted(FIXTURES.glob('financial_*fixture*.json')):
            sources = json.loads(path.read_text())
            if not (isinstance(sources, list) and sources and isinstance(sources[0], dict) and 'rows' in sources[0]):
                continue
            text, furniture = sep.profile_text(sources), sep.furniture_text(sources)
            self.assertEqual(sep.matching_profile(text, furniture), sep.written_matching_profile(text, furniture), path.name)

    def test_a_live_learned_profile_reads_and_resolves_by_name(self):
        live = self.entry('zz learned bank statement')
        self.write(live)
        self.assertEqual(sep.matching_profile('zz learned bank statement page 1')['name'], live['name'])
        self.assertEqual(sep.profile_named(live['name'])['name'], live['name'])
        self.assertIsNone(sep.written_matching_profile('zz learned bank statement page 1'))

    def test_retired_or_switched_off_profiles_no_longer_match(self):
        retired = self.entry('zz retired layout', state='retired')
        self.write(retired)
        self.assertIsNone(sep.matching_profile('zz retired layout'))
        self.assertEqual(sep.profile_named(retired['name'])['name'], retired['name'])  # saved choices still resolve
        live = self.entry('zz switched layout', fingerprint='f2')
        self.write(live)
        with mock.patch.object(lp, 'LEARNED_OFF', {live['name']}):
            self.assertIsNone(sep.matching_profile('zz switched layout'))

    def test_a_malformed_registry_leaves_the_written_profiles_reading(self):
        sources = fixture('financial_truist_consolidated_fixture.json')
        text, furniture = sep.profile_text(sources), sep.furniture_text(sources)
        self.path.write_text('{"profiles": [ {"name": 1}, ')
        lp._LOADED.clear()
        with self.assertLogs('services.financial.learned_profiles', 'ERROR'):
            self.assertEqual(sep.matching_profile(text, furniture)['name'], 'truist-consolidated')

    def test_concurrent_matching_never_changes_the_written_profiles(self):
        import threading
        self.write(self.entry('zz concurrent layout'))
        written, results, errors = sep.PROFILES, [], []

        def work():
            try:
                for _ in range(200):
                    results.append(sep.matching_profile('zz concurrent layout')['name'])
                    lp._LOADED.clear() if len(results) % 50 == 0 else None
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertIs(sep.PROFILES, written)
