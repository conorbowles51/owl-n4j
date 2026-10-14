"""Per-statement comparison (real_compare): truth periods against processor proposals,
field by field, with a disagreement class per difference. Synthetic data only."""
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.statement_automation import harness, real_compare as rc


def truth_row(date, amount, direction, balance=None, description='row'):
    return dict(date=date, amount_minor=amount, direction=direction, balance_after=balance, description=description)


def truth(**fields):
    base = dict(id='doc1.pdf#1', family='andrews-share', institution='I', account='1234', holder='A PERSON',
                currency='USD', period_start='2021-03-01', period_end='2021-03-31', start_printed=True,
                opening_minor=10000, closing_minor=13000, expected='auto', truth_status='verified',
                rows=[truth_row('2021-03-02', 2000, 'debit', 8000), truth_row('2021-03-05', 5000, 'credit', 13000)])
    base.update(fields)
    return base


def proposal(rows=None, balances=(('Opening Balance', '10000'), ('Closing Balance', '13000')), **metadata):
    meta = dict(period_start='2021-03-01', period_end='2021-03-31', holder='A PERSON', account_number='xx1234')
    meta.update(metadata)
    built = [dict(id=f'b{i}', kind='balance', excluded=False, fields=dict(description=d, balance=v))
             for i, (d, v) in enumerate(balances)]
    for i, (date, amount, direction, balance) in enumerate(rows if rows is not None else
                                                          [('2021-03-02', '2000', 'debit', '8000'),
                                                           ('2021-03-05', '5000', 'credit', '13000')]):
        built.append(dict(id=f'r{i}', kind='transaction', excluded=False,
                          fields=dict(date=date, amount_minor=amount, direction=direction, balance=balance,
                                      description='Withdrawal')))
    built.append(dict(id='x', kind='transaction', excluded=True, fields=dict(amount_minor='999')))
    return dict(metadata=meta, currency='USD', rows=built)


class ViewAndCompareTests(unittest.TestCase):
    def test_view_reads_balances_rows_and_skips_excluded(self):
        view = rc.proposal_view(proposal())
        self.assertEqual((view['opening_minor'], view['closing_minor'], view['account']), (10000, 13000, 'xx1234'))
        self.assertEqual([r['amount_minor'] for r in view['rows']], [2000, 5000])

    def test_agreement_has_no_class(self):
        result = rc.compare_period(truth(), rc.proposal_view(proposal()))
        self.assertEqual(result['classes'], {})
        self.assertEqual(result['rows']['matched'], 2)
        self.assertTrue(all(f['agree'] for f in result['fields'].values()))

    def test_every_field_difference_has_its_class(self):
        view = rc.proposal_view(proposal(rows=[('2021-03-03', '2000', 'debit', '8000'),
                                               ('2021-03-05', '5100', 'credit', '13100'),
                                               ('2021-03-09', '700', 'debit', '12400')],
                                         balances=(('Opening Balance', '10000'),),
                                         period_end='2021-03-30', account_number='9999', holder=''))
        classes = rc.compare_period(truth(), view)['classes']
        self.assertEqual(classes, {'account_differs': 1, 'closing_balance_missing': 1, 'holder_missing': 1,
                                   'period_end_differs': 1, 'row_amount_differs': 1, 'row_balance_differs': 1,
                                   'row_date_differs': 1, 'row_extra': 1})

    def test_missing_row_and_direction(self):
        view = rc.proposal_view(proposal(rows=[('2021-03-02', '2000', 'credit', '8000')]))
        result = rc.compare_period(truth(), view)
        self.assertEqual(result['classes'], {'row_direction_differs': 1, 'row_missing': 1})
        self.assertEqual(result['rows']['missing'][0]['truth_row'], 2)

    def test_unprinted_facts_are_not_compared(self):
        view = rc.proposal_view(proposal(holder='', period_start=''))
        result = rc.compare_period(truth(holder='', start_printed=False), view)
        self.assertEqual(result['classes'], {})
        self.assertNotIn('holder', result['fields'])

    def test_card_balance_owed_kept_negative_is_a_convention(self):
        view = rc.proposal_view(proposal(balances=(('Opening Balance', '-10000'), ('Closing Balance', '-13000'))))
        classes = rc.compare_period(truth(family='capital-one-card'), view, card=True)['classes']
        self.assertEqual(classes, {'balance_sign_convention': 2})

    def test_not_detected(self):
        self.assertEqual(rc.compare_period(truth(), None)['classes'], {'not_detected': 1})


class BuildAndWriteTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(synthetic=False, files=[dict(filename='doc1.pdf', truth_complete=True, periods=[
            truth(), truth(id='doc1.pdf#2', period_start='2021-04-01', period_end='2021-04-30', expected='hold',
                           truth_status='incomplete')])])
        self.periods = [
            dict(item_id='i1', filename='doc1.pdf', truth_id='doc1.pdf#1', status='attention', can_import=False),
            dict(item_id='i2', filename='doc1.pdf', truth_id='doc1.pdf#2', status='ready', can_import=True),
            dict(item_id='i3', filename='doc1.pdf', truth_id=None, status='ready', can_import=True)]
        self.views = {'i1': rc.proposal_view(proposal()), 'i2': rc.proposal_view(proposal(
            period_start='2021-04-01', period_end='2021-04-30')), 'i3': rc.proposal_view(proposal())}

    def test_outcome_classes_and_unmatched_items(self):
        record = rc.build(self.periods, {}, self.manifest, self.views)['doc1']
        first, second = record['periods']
        self.assertEqual(first['classes'], {'not_ready': 1})
        self.assertIn('held_period_offered', second['classes'])
        self.assertEqual(record['unmatched_items'][0]['classes'], {'unmatched_item': 1, 'unmatched_item_offered': 1})

    def test_not_detected_period(self):
        record = rc.build(self.periods[:1], {}, self.manifest, self.views)['doc1']
        self.assertEqual(record['periods'][1]['classes'], {'not_detected': 1})
        self.assertEqual(record['periods'][1]['processor_status'], 'not_detected')

    def test_summary_is_counts_only_and_files_are_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / 'truth'
            corpus.mkdir()
            (corpus / 'status.json').write_text(json.dumps([dict(id='doc1', status='verified'),
                                                            dict(id='doc2', status='needs_visual'),
                                                            dict(id='doc3', status='not_statement')]))
            out = Path(tmp) / 'compare'
            summary = rc.write(out, rc.build(self.periods, {}, self.manifest, self.views), corpus)
            self.assertEqual((summary['statements_compared'], summary['statement_documents']), (1, 2))
            self.assertEqual(oct((out).stat().st_mode & 0o777), '0o700')
            text = (out / 'summary.md').read_text()
            self.assertIn('Statements compared: 1 / 2 statement documents', text)
            for private in ('doc1', 'A PERSON', '1234', '2021-03'):
                self.assertNotIn(private, text)
            record = json.loads((out / 'doc1.json').read_text())
            self.assertEqual(record['periods'][0]['fields']['closing_minor']['truth'], 13000)

    def test_harness_writes_compare_only_for_real_corpora(self):
        self.assertIsNone(harness._default_compare(dict(files=[]), Path('/x/corpus')))
        self.assertEqual(harness._default_compare(dict(synthetic=False), Path('/x/truth')), Path('/x/compare'))


if __name__ == '__main__':
    unittest.main()
