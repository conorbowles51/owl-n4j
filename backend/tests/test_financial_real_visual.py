"""Reviewed visual truth (real_visual): transcription, reconciliation, OCR-layer misread
counts, and the merge into real_truth results. Synthetic data only."""
import unittest

from benchmarks.statement_automation import harness, real_truth as rt, real_visual as rv


def line(top, text):
    return rt.Line(top, [dict(text=w, x0=10.0 * i, x1=10.0 * i + 8, top=top, bottom=top + 8)
                         for i, w in enumerate(text.split())])


def page(number, texts):
    lines = [line(10.0 * i, t) for i, t in enumerate(texts)]
    return rt.Page(number, 600.0, lines, '\n'.join(l.text for l in lines))


REVIEWED = """doc dtest
done 1-3
page 1 stmt 2021-03-01 2021-03-31 no 1 member 123456789 holder A PERSON
share 0000 open 0.00
close 0.00
share 0040 open 100.00
r 03/02 -20.00 80.00 | Withdrawal Debit Card
r 03/05 50.00 130.00 | Deposit ACH
# continued on following page
page 2 stmt 2021-03-01 2021-03-31 no 2 member 123456789
r 03/30 -30.00 100.00 | Withdrawal Debit Card
close 100.00
page 3 skip  # a check image
"""

OCR = """doc dtest
done
page 1 stmt 2021-03-01 2021-03-31 no 1 member 123456789 holder A PERSON
share 0000 open 0.00
share 0040 open 100.00
r 03/02 20.00 80.00 | Withdrawal Debit Card
r 03/05 ?? ?? | Deposit ACH
page 2 stmt 2021-03-01 2021-03-31 no ? member 123456789
close 100.00
page 3 skip
"""


class TranscriptionTests(unittest.TestCase):
    def test_reviewed_periods_reconcile_like_tier_a_truth(self):
        result = rv.compile_document(REVIEWED, page_count=3)
        self.assertTrue(result['complete'])
        self.assertEqual(result['period_status'], {'verified': 2})
        checking = result['periods'][1]
        self.assertEqual((checking['share'], checking['opening_minor'], checking['closing_minor']), ('0040', 10000, 10000))
        self.assertEqual([(r['date'], r['amount_minor'], r['direction'], r['balance_after']) for r in checking['rows']],
                         [('2021-03-02', 2000, 'debit', 8000), ('2021-03-05', 5000, 'credit', 13000),
                          ('2021-03-30', 3000, 'debit', 10000)])
        self.assertEqual(checking['pages'], [1, 2])
        self.assertEqual(checking['holder'], 'A PERSON')
        self.assertEqual(checking['truth_source'], 'visual')

    def test_pages_not_done_leave_the_document_incomplete(self):
        result = rv.compile_document(REVIEWED.replace('done 1-3', 'done 1,3'), page_count=3)
        self.assertFalse(result['complete'])
        self.assertEqual(result['pages_pending'], [2])

    def test_a_value_left_unread_never_verifies(self):
        text = REVIEWED.replace('r 03/05 50.00 130.00', 'r 03/05 ?? ??')
        status = rv.compile_document(text, page_count=3)['periods'][1]
        self.assertEqual(status['truth_status'], 'unverified')
        self.assertIn('value not legible on the page image', status['truth_reasons'])

    def test_a_wrong_reading_breaks_the_running_balance(self):
        text = REVIEWED.replace('r 03/05 50.00 130.00', 'r 03/05 60.00 130.00')
        period = rv.compile_document(text, page_count=3)['periods'][1]
        self.assertEqual(period['truth_status'], 'unverified')

    def test_hold_and_expectation_lines(self):
        text = REVIEWED.replace('close 100.00\n', 'hold printed page 3 is not in the file\nclose 100.00\n')
        text = text.replace('share 0000 open 0.00\nclose 0.00\n',
                            'share 0000 open 0.00\nclose 0.00\nexpect hold another printed statement contradicts it\n')
        result = rv.compile_document(text, page_count=3)
        saving, checking = result['periods']
        self.assertEqual((checking['truth_status'], checking['truth_reasons']),
                         ('incomplete', ['printed page 3 is not in the file']))
        self.assertEqual((saving['truth_status'], saving['expected_override']), ('verified', 'hold'))

    def test_malformed_lines_are_refused_with_their_line_number(self):
        for bad in ('r 03/02 -20.00 | x', 'r 03/02 -20 80.00 | x', 'expect maybe because', 'frobnicate'):
            with self.assertRaisesRegex(ValueError, 'line'):
                rv.Transcription(REVIEWED.replace('close 0.00', bad, 1))

    def test_misread_classes_counted_page_by_page(self):
        counts = rv.compile_document(REVIEWED, OCR, page_count=3)['misreads']
        self.assertEqual(counts, {'amount_sign_misread': 1, 'amount_unread': 1, 'balance_unread': 1,
                                  'ending_line_unread': 1, 'line_lost_by_layer': 1})

    def test_misread_counts_name_no_value(self):
        counts = rv.compile_document(REVIEWED, OCR, page_count=3)['misreads']
        self.assertTrue(all(isinstance(v, int) for v in counts.values()))
        self.assertNotIn('PERSON', repr(counts))


class DraftTests(unittest.TestCase):
    def test_draft_keeps_every_movement_line_and_marks_unread_values(self):
        pages = [page(1, ['Account Statement', '123456789', '03/01/21 03/31/21', '1', '>2000<', 'A PERSON',
                          '03/01 ID 0040 FREE CHECKING Previous Balance 100.00',
                          '03/02 Withdrawal Debit Card -20.00 80.00',
                          '03/05 Deposit ACH 5O.OO', '03/31 Ending Balance 130.00',
                          '--- Continued on following page ---']),
                 page(2, ['a membership application with no statement header'])]
        text = rv.draft_andrews('dtest', pages)
        self.assertIn('page 1 stmt 2021-03-01 2021-03-31 no 1 member 123456789 holder A PERSON', text)
        self.assertIn('share 0040 open 100.00', text)
        self.assertIn('r 03/02 -20.00 80.00 | Withdrawal Debit Card', text)
        self.assertIn('r 03/05 ?? ?? | Deposit ACH 5O.OO', text)
        self.assertIn('close 130.00', text)
        self.assertIn('page 2 skip', text)
        rv.Transcription(text, strict=False)  # the draft parses


class MergeTests(unittest.TestCase):
    def result(self):
        return dict(id='dtest', sha256='x', status='ocr_reconciled', pages=3, mode='scan_text_layer',
                    periods=[dict(id='dtest#1', truth_status='ocr_reconciled')])

    def test_complete_review_replaces_the_text_layer_reading(self):
        merged = rv.apply_visual(self.result(), rv.compile_document(REVIEWED, page_count=3))
        self.assertEqual((merged['status'], merged['truth_source'], len(merged['periods'])), ('verified', 'visual', 2))
        self.assertTrue(merged['statements_complete'])

    def test_partial_review_changes_nothing(self):
        partial = rv.compile_document(REVIEWED.replace('done 1-3', 'done 1'), page_count=3)
        self.assertEqual(rv.apply_visual(self.result(), partial), self.result())

    def test_review_of_another_document_changes_nothing(self):
        other = rv.compile_document(REVIEWED.replace('doc dtest', 'doc dother'), page_count=3)
        self.assertEqual(rv.apply_visual(self.result(), other), self.result())

    def test_incomplete_period_keeps_the_document_truth_complete(self):
        text = REVIEWED.replace('close 100.00\n', 'hold printed page 3 is not in the file\nclose 100.00\n')
        merged = rv.apply_visual(self.result(), rv.compile_document(text, page_count=3))
        self.assertEqual(merged['status'], 'partly_verified')
        self.assertTrue(merged['statements_complete'])

    def test_incomplete_truth_is_scored_so_its_admission_is_wrong(self):
        self.assertTrue(harness._scored(dict(truth_status='incomplete')))


class QueueAndDuplicateTests(unittest.TestCase):
    def result(self, doc, status='needs_visual', family='fam', source=None):
        r = dict(id=doc, status=status, issuer=family, inventory_family=family, mode='scan', pages=2, reason=None,
                 periods=[dict(id=f'{doc}#1', family=family, truth_status='ocr_reconciled', truth_reasons=[])])
        if source:
            r['truth_source'] = source
        return r

    def test_shards_keep_their_numbers_and_reviewed_documents_are_done(self):
        big = [self.result(f'b{i:02d}', family='big') for i in range(10)]  # 10+ documents: a shard of its own
        first = rt.visual_queue(big + [self.result('a1')])
        self.assertEqual([(s['shard'], s['families']) for s in first['shards']], [('v01', ['big']), ('v02', ['fam'])])
        reviewed = [dict(r, status='verified', truth_source='visual') for r in big]
        again = rt.visual_queue(reviewed + [self.result('a1'), self.result('a3', family='new')], previous=first)
        self.assertEqual([(s['shard'], s['done']) for s in again['shards']], [('v01', True), ('v02', False),
                                                                              ('v03', False)])
        self.assertEqual(again['done'], 10)
        self.assertEqual([d['id'] for d in again['shards'][2]['documents']], ['a3'])
        mixed = rt.visual_queue(reviewed[:9] + big[9:] + [self.result('a1')], previous=first)
        self.assertFalse(mixed['shards'][0]['done'])  # a shard is done only when every document is

    def test_reviewed_documents_never_enter_a_fresh_queue(self):
        queue = rt.visual_queue([self.result('a1', source='visual'), self.result('a2')])
        self.assertEqual(queue['documents'], 1)

    def test_two_shares_of_one_member_are_not_duplicates(self):
        def p(share):
            return dict(id=f'd#{share}', family='andrews-share', account='1', share=share, period_start='2021-01-01',
                        period_end='2021-01-31', opening_minor=0, closing_minor=0, rows=[], truth_status='verified',
                        expected='auto')
        results = [dict(id='d', periods=[p('0000'), p('0011')])]
        rt.mark_duplicates(results)
        self.assertEqual([x['expected'] for x in results[0]['periods']], ['auto', 'auto'])


if __name__ == '__main__':
    unittest.main()
