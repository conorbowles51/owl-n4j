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


GENERIC = """doc dgen
done 1-2
issuer acme-bank Acme Bank SA
currency MXN
page 1 stmt 2024-01-01 2024-01-31 no 1 member 4321 holder A COMPANY SA
share - open 1000.00
r 2024-01-05 -200.00 800.00 | SPEI sent
r 01/09 50.25 - | Deposit (no running balance printed)
control credits_total 50.25
control debits_total 200.00
control credits_count 1
control debits_count 1
close 850.25
share USD open 10.00
currency USD
close 10.00
page 2 skip  # tax letter
"""


class GenericIssuerTests(unittest.TestCase):
    def test_issuer_currency_sections_and_rows_without_balances(self):
        result = rv.compile_document(GENERIC, page_count=2)
        self.assertEqual(result['period_status'], {'verified': 2})
        self.assertEqual(result['issuer'], 'acme-bank')
        pesos, dollars = result['periods']
        self.assertEqual((pesos['family'], pesos['institution'], pesos['currency'], pesos['account'], pesos['share']),
                         ('acme-bank', 'Acme Bank SA', 'MXN', '4321', None))
        self.assertEqual([(r['date'], r['amount_minor'], r['direction'], r.get('balance_after')) for r in pesos['rows']],
                         [('2024-01-05', 20000, 'debit', 80000), ('2024-01-09', 5025, 'credit', None)])
        self.assertEqual(pesos['controls'], dict(credits_total=5025, debits_total=20000, credits_count=1,
                                                 debits_count=1))
        self.assertEqual((dollars['currency'], dollars['notes']), ('USD', ['section USD']))
        self.assertEqual(pesos['truth_reasons'], [])  # no share number is needed outside Andrews

    def test_a_printed_total_that_disagrees_is_unverified(self):
        period = rv.compile_document(GENERIC.replace('control debits_total 200.00', 'control debits_total 210.00'),
                                     page_count=2)['periods'][0]
        self.assertEqual((period['truth_status'], period['truth_reasons']),
                         ('unverified', ['debit total differs from printed total']))
        period = rv.compile_document(GENERIC.replace('control credits_count 1', 'control credits_count 2'),
                                     page_count=2)['periods'][0]
        self.assertIn('credit count differs from printed count', period['truth_reasons'])

    def test_card_balances_rise_with_purchases(self):
        text = ('doc dcard\ndone 1\nissuer acme-card Acme Card\nkind card\ncurrency USD\n'
                'page 1 stmt 2024-01-01 2024-01-31 no 1 member 9999\nshare - open 100.00\n'
                'r 01/03 -40.00 - | purchase\nr 01/20 100.00 - | payment\nclose 40.00\n')
        period = rv.compile_document(text, page_count=1)['periods'][0]
        self.assertEqual((period['kind'], period['truth_status']), ('card', 'verified'))

    def test_an_unprinted_account_or_holder_makes_a_decision(self):
        text = GENERIC.replace('member 4321 holder A COMPANY SA', 'member ?')
        period = rv.compile_document(text, page_count=2)['periods'][0]
        self.assertEqual((period['account'], period['truth_status']), (None, 'unverified'))
        text = GENERIC.replace(' holder A COMPANY SA', '')
        period = rv.compile_document(text, page_count=2)['periods'][0]
        self.assertEqual(rt.expected_outcome(rt.Period(**{k: period[k] for k in rt.Period.__dataclass_fields__}),
                                             period['truth_status']), 'decision')

    def test_document_lines_are_refused_after_the_first_page_and_when_malformed(self):
        bad = (GENERIC.replace('close 10.00', 'close 10.00\nissuer other-bank Other'),
               GENERIC.replace('issuer acme-bank Acme Bank SA', 'issuer Acme'),
               GENERIC.replace('currency USD', 'currency dollars'),
               GENERIC.replace('control debits_count 1', 'control debit_rows 1'),
               GENERIC.replace('control debits_count 1', 'control debits_count 1.5'),
               GENERIC.replace('r 01/09', 'r 9 Jan'),
               GENERIC.replace('currency MXN', 'form not_statement letter'))
        for text in bad:
            with self.assertRaises(ValueError):
                rv.Transcription(text)

    def test_andrews_defaults_are_unchanged(self):
        period = rv.compile_document(REVIEWED, page_count=3)['periods'][1]
        self.assertEqual((period['family'], period['institution'], period['currency'], period['kind']),
                         ('andrews-share', 'Andrews Federal Credit Union', 'USD', 'deposit'))


class DocumentStatusTests(unittest.TestCase):
    def status(self, reviewed=False, **counts):
        from collections import Counter
        return rt.document_status(Counter(counts), reviewed=reviewed)

    def test_verified_and_incomplete_periods_settle_the_document_from_any_reader(self):
        for reviewed in (False, True):
            self.assertEqual(self.status(reviewed, verified=3, incomplete=1), 'settled')
            self.assertEqual(self.status(reviewed, verified=3), 'verified')
            self.assertEqual(self.status(reviewed, incomplete=2), 'incomplete')
            self.assertEqual(self.status(reviewed), 'unverified')

    def test_an_unverified_text_layer_period_keeps_the_document_open(self):
        self.assertEqual(self.status(verified=2, unverified=1), 'partly_verified')
        self.assertNotIn('partly_verified', rt.FINAL)
        self.assertEqual(self.status(ocr_reconciled=2, unverified=1), 'ocr_reconciled')
        self.assertEqual(self.status(True, verified=2, unverified=1), 'settled')
        self.assertEqual(self.status(True, unverified=1, incomplete=1), 'unverified')

    def test_settled_documents_leave_the_visual_queue_and_count_as_final(self):
        settled = dict(id='s1', status='settled', issuer='fam', inventory_family='fam', mode='digital', pages=2,
                       reason=None, period_status={'verified': 1, 'incomplete': 1}, period_reasons={},
                       periods=[dict(id='s1#1', family='fam', truth_status='verified', truth_reasons=[]),
                                dict(id='s1#2', family='fam', truth_status='incomplete', truth_reasons=['x'])])
        self.assertEqual(rt.visual_queue([settled])['documents'], 0)
        partly = dict(settled, id='p1', status='partly_verified')
        self.assertEqual(rt.summarise([settled, partly])['documents_final'], 1)


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
        self.assertEqual(merged['status'], 'settled')  # every period final: the document is too
        self.assertIn(merged['status'], rt.FINAL)
        self.assertTrue(merged['statements_complete'])

    def test_a_period_the_image_cannot_settle_still_leaves_the_document_final(self):
        text = REVIEWED.replace('r 03/05 50.00 130.00', 'r 03/05 ?? 130.00')
        merged = rv.apply_visual(self.result(), rv.compile_document(text, page_count=3))
        self.assertEqual((merged['status'], merged['period_status']), ('settled', {'verified': 1, 'unverified': 1}))
        self.assertFalse(merged['statements_complete'])

    def test_not_statement_form_replaces_the_reading_with_no_periods(self):
        text = 'doc dtest\ndone 1-3\nissuer acme-bank Acme Bank\nform not_statement a letter about tax details\n'
        merged = rv.apply_visual(self.result(), rv.compile_document(text, page_count=3))
        self.assertEqual((merged['status'], merged['reason'], merged['periods'], merged['issuer']),
                         ('not_statement', 'a letter about tax details', [], 'acme-bank'))
        self.assertIn(merged['status'], rt.FINAL)

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

    def test_a_queued_document_whose_truth_became_final_by_any_reader_is_done(self):
        first = rt.visual_queue([self.result('a1'), self.result('a2')])
        again = rt.visual_queue([dict(self.result('a1'), status='verified'), self.result('a2')], previous=first)
        self.assertEqual([(d['id'], d['done']) for d in again['shards'][0]['documents']], [('a1', True), ('a2', False)])
        partly = rt.visual_queue([dict(self.result('a1'), status='partly_verified'), self.result('a2')], previous=first)
        self.assertEqual(partly['done'], 0)

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


CARD = """doc dcard
done 2-3
issuer acme-card Acme Card
kind card
currency USD
patch 2
page 2 stmt 2024-01-01 2024-01-31 no 1 member 9999 holder A PERSON
share - open 100.00
group payments
r 2024-01-20 100.00 - | payment
subtotal payments 100.00
page 3 cont
group purchases
r 2024-01-03 -40.00 - | purchase
r 2024-01-09 5.00 - | refund
subtotal purchases -35.00
group interest
r 2024-01-31 -1.25 - | interest
subtotal interest -1.25
subtotal fees 0.00
close 36.25
"""


class CardSectionAndPatchTests(unittest.TestCase):
    def text_layer(self):
        def p(n, status):
            return dict(id=f'dcard#{n}', family='acme-card', truth_status=status, truth_reasons=[] if status == 'verified'
                        else ['amount line without a date'], pages=[n])
        return dict(id='dcard', sha256='x', status='partly_verified', pages=5, mode='digital',
                    periods=[p(1, 'verified'), p(2, 'unverified'), p(3, 'verified')])

    def test_printed_section_totals_are_checked_against_their_rows(self):
        period = rv.compile_document(CARD, page_count=5)['periods'][0]
        self.assertEqual((period['truth_status'], period['id']), ('verified', 'dcard#2'))
        self.assertEqual([c['ok'] for c in period['controls']['other_checks']], [True, True, True, True])
        self.assertNotIn('group', period['rows'][0])
        wrong = rv.compile_document(CARD.replace('subtotal purchases -35.00', 'subtotal purchases -40.00'),
                                    page_count=5)['periods'][0]
        self.assertEqual((wrong['truth_status'], wrong['truth_reasons']),
                         ('unverified', ['purchases rows differ from the printed purchases total']))
        # A row put in the wrong section is caught even though the period still balances.
        moved = CARD.replace('r 2024-01-31 -1.25 - | interest\n', '').replace(
            'r 2024-01-09 5.00 - | refund\n', 'r 2024-01-09 5.00 - | refund\nr 2024-01-31 -1.25 - | interest\n')
        self.assertIn('interest rows differ from the printed interest total',
                      rv.compile_document(moved, page_count=5)['periods'][0]['truth_reasons'])

    def test_a_patch_needs_only_its_own_pages_and_replaces_only_the_periods_it_names(self):
        visual = rv.compile_document(CARD, page_count=5)
        self.assertEqual((visual['complete'], visual['pages_pending'], visual['patch']), (True, [], [2]))
        merged = rv.apply_visual(self.text_layer(), visual)
        self.assertEqual([p['id'] for p in merged['periods']], ['dcard#1', 'dcard#2', 'dcard#3'])
        self.assertEqual([p.get('truth_source') for p in merged['periods']], [None, 'visual', None])
        self.assertEqual((merged['status'], merged['truth_source'], merged['visual_patch']),
                         ('verified', 'visual', ['dcard#2']))
        self.assertTrue(merged['statements_complete'])
        self.assertEqual(rv.apply_visual(merged, visual), merged)  # merging twice changes nothing
        self.assertFalse(rv.compile_document(CARD.replace('done 2-3', 'done 2'), page_count=5)['complete'])

    def test_a_patched_period_the_image_cannot_settle_still_makes_the_document_final(self):
        text = CARD.replace('subtotal fees 0.00\n', 'subtotal fees 0.00\nunverified a digit is cut off\n')
        merged = rv.apply_visual(self.text_layer(), rv.compile_document(text, page_count=5))
        self.assertEqual(merged['status'], 'settled')
        self.assertIn(merged['status'], rt.FINAL)
        left = self.text_layer()
        left['periods'][2]['truth_status'] = 'unverified'  # a second text-layer gap the patch does not cover
        self.assertEqual(rv.apply_visual(left, rv.compile_document(CARD, page_count=5))['status'], 'partly_verified')

    def test_a_patch_naming_a_period_the_text_layer_lacks_is_refused(self):
        visual = rv.compile_document(CARD.replace('patch 2', 'patch 7'), page_count=5)
        self.assertEqual(rv.apply_visual(self.text_layer(), visual), self.text_layer())

    def test_a_statement_that_prints_only_its_closing_date(self):
        text = ('doc dmer\ndone 1\nissuer acme-card Acme Card\nkind card\ncurrency USD\n'
                'page 1 stmt - 2021-01-25 no 1 member 9999 holder A PERSON\nshare - open 0.00\n'
                'r 12/30 -14.00 - | store\nr 01/22 -100.00 - | diner\nclose 114.00\n')
        period = rv.compile_document(text, page_count=1)['periods'][0]
        self.assertEqual((period['period_start'], period['period_end'], period['truth_status']),
                         (None, '2021-01-25', 'verified'))
        self.assertEqual([r['date'] for r in period['rows']], ['2020-12-30', '2021-01-22'])  # year from the close
        self.assertIn(rt.START_UNPRINTED, period['notes'])
        record = rt.manifest_period(dict(period, expected='auto'))
        self.assertEqual((record['start_printed'], record['period_start']), (False, None))
        # Without the marker a missing start is still a gap in the reading, never verified.
        bare = rt.Period(family='f', institution='i', currency='USD', holder='H', account='9999', period_end='2021-01-25',
                         opening_minor=0, closing_minor=0, kind='card')
        self.assertEqual(rt.reconcile(bare), ('unverified', ['period_start not read']))
        # A row far before the closing date is still caught.
        late = text.replace('r 12/30', 'r 2020-08-01')
        self.assertIn('row date outside the printed period',
                      rv.compile_document(late, page_count=1)['periods'][0]['truth_reasons'])
        for bad in ('stmt - - no', 'stmt 2021/01/01 2021-01-25 no', 'stmt - 25.01.2021 no'):
            with self.assertRaises(ValueError):
                rv.Transcription(text.replace('stmt - 2021-01-25 no', bad))

    def test_malformed_patch_and_section_lines_are_refused(self):
        for text in (CARD.replace('patch 2', 'patch 2,3'), CARD.replace('patch 2', 'patch 2,2'),
                     CARD.replace('patch 2', 'patch two'), CARD.replace('group payments', 'group'),
                     CARD.replace('subtotal fees 0.00', 'subtotal fees'),
                     CARD.replace('subtotal fees 0.00', 'subtotal fees 1'),
                     CARD.replace('share - open 100.00\ngroup payments', 'group payments\nshare - open 100.00')):
            with self.assertRaises(ValueError):
                rv.Transcription(text)


if __name__ == '__main__':
    unittest.main()
