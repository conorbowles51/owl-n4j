"""A period's summary page read with it from its page images (SUMMARY_PAGES, coordinator 2026-10-28).

Each of fdaf956c's 52 held Capital One periods was read from its "Page 2 of N" onwards: the file page before it,
printing "Page 1 of N" with the previous and new balance, the holder and address, sits on no statement's table pages,
so every reading was refused ("The opening or closing balance could not be read from the page images")."""
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from services.financial import vision_reader as vr
from services.financial.field_proposals import CaseKnowledge


from services.financial import summary_pages as sp


def _proposal(pages, summary=None):
    proposal = dict(statement_id='own', statement_page_numbers=list(pages), page_numbers=list(range(1, 11)), sources=[])
    if summary:
        proposal['summary_page_numbers'] = list(summary)
    return proposal


# fdaf956c's file: page 1 "Page 1 of 4" (summary), 2 its reverse side, 3 "Page 2 of 4" (the payments), 4 a notice,
# 5 the next statement's "Page 1 of 4", 7 its "Page 2 of 4".
CAPITAL_ONE = {1: {(1, 4)}, 3: {(2, 4)}, 5: {(1, 4)}, 7: {(2, 4)}}


class SummaryPagesTest(unittest.TestCase):
    def pages(self, pages, labels, file_pages=range(1, 11), taken=(7,)):
        return sp.summary_pages(pages, file_pages, taken, labels)

    def test_the_summary_page_and_its_reverse_side_are_found(self):
        self.assertEqual(self.pages([3], CAPITAL_ONE), [1, 2])
        self.assertEqual(self.pages([7], CAPITAL_ONE, taken=(3,)), [5, 6])
        # Two payment pages, the summary two file pages before them (fdaf956c 21a510b9: 139..142).
        labels = {139: {(1, 3)}, 141: {(2, 3)}, 142: {(3, 3)}}
        self.assertEqual(self.pages([141, 142], labels, file_pages=range(1, 223), taken=()), [139, 140])
        # Page 1 and page 2 both before the period's first page ("Page 3 of 5").
        self.assertEqual(self.pages([3], {1: {(1, 5)}, 2: {(2, 5)}, 3: {(3, 5)}}, taken=()), [1, 2])

    def test_off_none(self):
        with mock.patch.object(sp, 'ENABLED', False):
            self.assertEqual(self.pages([3], CAPITAL_ONE), [])
            self.assertEqual(sp.balance_pages(_proposal([3], [1, 2])), [3])

    def test_a_page_of_another_statement_is_never_taken(self):
        self.assertEqual(self.pages([3], CAPITAL_ONE, taken=(2,)), [])
        self.assertEqual(self.pages([3], CAPITAL_ONE, taken=(1,)), [])

    def test_the_numbering_must_lead_back_to_page_1_of_the_same_count(self):
        # Another count before it: another printing, not its summary.
        self.assertEqual(self.pages([3], {1: {(1, 5)}, 3: {(2, 4)}}, taken=()), [])
        # A number that does not fall towards page 1.
        self.assertEqual(self.pages([3], {1: {(2, 4)}, 3: {(2, 4)}}, taken=()), [])
        self.assertEqual(self.pages([4], {1: {(1, 4)}, 2: {(3, 4)}, 4: {(2, 4)}}, taken=()), [])
        # No "Page 1" within reach (at most two file pages per printed page before it).
        self.assertEqual(self.pages([4], {1: {(1, 4)}, 4: {(2, 4)}}, taken=()), [])
        self.assertEqual(self.pages([3], {3: {(2, 4)}}, taken=()), [])
        # A page printing two numberings, or a first page printing two.
        self.assertEqual(self.pages([3], {1: {(1, 4), (1, 9)}, 3: {(2, 4)}}, taken=()), [])
        self.assertEqual(self.pages([3], {1: {(1, 4)}, 3: {(2, 4), (7, 9)}}, taken=()), [])
        # Its first page is page 1, or prints no numbering: nothing before it.
        self.assertEqual(self.pages([3], {3: {(1, 4)}, 2: {(1, 4)}}, taken=()), [])
        self.assertEqual(self.pages([3], {1: {(1, 4)}}, taken=()), [])

    def test_only_pages_of_the_file(self):
        self.assertEqual(self.pages([3], CAPITAL_ONE, file_pages=[2, 3, 4]), [])
        self.assertEqual(self.pages([2], {1: {(1, 2)}, 2: {(2, 2)}}, file_pages=[2, 3], taken=()), [])

    def test_page_labels_read_the_stored_text_page_by_page(self):
        first, second, third = 'Account Summary Page 1 of 4 New Balance', 'See reverse 002', 'Transactions  Page\n2   of 4'
        content = '\n'.join((first, second, third))
        locations, at = [], 0
        for number, words in enumerate((first, second, third), 1):
            locations.append(dict(kind='page', page_number=number, start_char=at, end_char=at + len(words)))
            at += len(words) + 1
        self.assertEqual(sp.page_labels(content, locations), {1: {(1, 4)}, 3: {(2, 4)}})
        self.assertEqual(sp.page_labels(content, None), {})

    def test_the_period_is_read_with_them_and_its_balances_may_cite_them(self):
        proposal = _proposal([3], [1, 2])
        self.assertEqual(vr.period_pages(proposal), [1, 2, 3])
        self.assertEqual(vr.period_pages(_proposal([3])), [3])
        with mock.patch.object(vr, 'SUMMARY_PAGES', False):
            self.assertEqual(vr.period_pages(proposal), [3])
        self.assertEqual(sp.balance_pages(proposal), [1, 2, 3])
        from services.financial.manual_balances import manual_balance
        from services.financial.pdf_candidates import PdfMappingError
        row = dict(id='manual:opening-balance', excluded=True, manual_page=1, balance_minor='24692')
        self.assertEqual(manual_balance(row, proposal)['page_number'], 1)
        with self.assertRaises(PdfMappingError):
            manual_balance(row, _proposal([3]))
        with self.assertRaises(PdfMappingError):
            manual_balance(dict(row, manual_page=4), proposal)


class FormNumberAndPostingTest(unittest.TestCase):
    """The reverse side of a summary page printing a form number, and a card purchase dated before its cycle."""

    def test_a_form_number_on_a_page_that_is_not_a_statement_page_is_not_its_numbering(self):
        pages = [(1, dict(printed_page_number=1, printed_page_total=4, is_statement_page=True)),
                 (2, dict(printed_page_number=2, printed_page_total=None, is_statement_page=False)),
                 (3, dict(printed_page_number=2, printed_page_total=4, is_statement_page=True))]
        self.assertFalse(vr.check_page_numbering(pages, list(range(1, 11))))
        with mock.patch.object(vr, 'FORM_NUMBERS', False), self.assertRaisesRegex(vr.NotProved, 'same page number'):
            vr.check_page_numbering(pages, list(range(1, 11)))
        # A statement page printing a number without a count is still numbered.
        pages[1] = (2, dict(printed_page_number=2, printed_page_total=None, is_statement_page=True))
        with self.assertRaisesRegex(vr.NotProved, 'same page number'):
            vr.check_page_numbering(pages, list(range(1, 11)))

    def test_a_card_purchase_dated_a_few_days_before_the_cycle_is_of_it(self):
        from tests.test_financial_vision_last4 import _card_pages, _known, _prove
        from tests.test_financial_vision_reader import _page, _row, _section
        from tests.test_financial_vision_last4 import IMAGE
        known = CaseKnowledge(accounts=[_known(holder='ERICA HOPPER')])

        def pages(day):
            return [(1, _page([_section([_row(day, '100.00', 'debit', '1100.00'),
                                         _row('2023-06-15', '30.50', 'credit', '1069.50')],
                                        opening_balance='1000.00', total_debits='100.00', count_debits=1, **IMAGE)], 1, 2)),
                    (2, _page([_section([_row('2023-07-01', '69.50', 'credit', '1000.00')],
                                        closing_balance='1000.00', total_credits='100.00')], 2, 2))]
        self.assertEqual(len(_prove(pages=pages('2023-06-06'), knowledge=known)['rows']), 3)
        with self.assertRaisesRegex(vr.NotProved, 'dated outside the statement period'):
            _prove(pages=pages('2023-06-04'), knowledge=known)
        with mock.patch.object(vr, 'CARD_POSTING', False), \
                self.assertRaisesRegex(vr.NotProved, 'dated outside the statement period'):
            _prove(pages=pages('2023-06-06'), knowledge=known)
        # Not on a statement that is not a card's.
        with self.assertRaisesRegex(vr.NotProved, 'dated outside the statement period'):
            _prove(pages=pages('2023-06-06'), knowledge=known, balance_convention='asset_balance')

    def test_the_proof_version_counts_the_rules(self):
        self.assertTrue(vr.FORM_NUMBERS and vr.CARD_POSTING)
        self.assertEqual(vr.PROOF_VERSION, 22)


class SummaryPagesFlowTest(unittest.TestCase):
    """Through read_item and pending on the batch fixture: an outcome stored from fewer pages is read anew once with
    its summary page; one whose pages are unchanged is only marked, with no request."""

    def setUp(self):
        from tests.test_financial_vision_last4 import LastFourFlowTest
        self.flow = LastFourFlowTest('test_the_first_statement_of_the_card_is_saved_with_its_basis')
        self.flow.setUp()
        self.addCleanup(self.flow.doCleanups)
        self.held = self.flow.held
        # A reading that does not reconcile (a cent off): the statement stays held, not proved.
        account = self.flow.document['accounts'][0]
        whole, cents = account['closing_balance'].split('.')
        account['closing_balance'] = '%s.%02d' % (whole, (int(cents) + 1) % 100)

    def store(self, record):
        from postgres.models.evidence import EvidenceFile
        with self.flow.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.held.file_id)
            metadata = dict(file.metadata_ or {})
            metadata[vr.METADATA_KEY] = dict(metadata.get(vr.METADATA_KEY) or {}, **{self.held.statement_key or '': record})
            file.metadata_ = metadata
            db.commit()

    def pending(self):
        with self.flow.f.SessionLocal() as db:
            return self.held.id in vr.pending(db)

    def test_an_outcome_read_from_fewer_pages_is_read_anew_once_and_one_unchanged_only_marked(self):
        calls = []
        first = self.flow.read(calls=calls)  # read with the pages as assigned
        self.assertEqual((len(calls), first['status']), (1, 'not_proved'), first.get('message'))
        pages = first['pages']
        stored = self.flow.stored()
        self.assertEqual(stored['pages_rule'], vr.PAGES_RULE)
        # An outcome stored before this rule (no pages_rule): not proved, from these same pages.
        old = {k: v for k, v in stored.items() if k != 'pages_rule'}
        old.update(status='not_proved', message='The opening or closing balance could not be read from the page images.')
        self.store(old)
        self.assertTrue(self.pending())
        again = self.flow.read(calls=calls)
        self.assertEqual(len(calls), 1, 'its pages are unchanged: nothing is requested')
        self.assertEqual(again['reason'], 'already_read')
        self.assertEqual(self.flow.stored()['pages_rule'], vr.PAGES_RULE)
        self.assertFalse(self.pending())
        # Its period now has a summary page before it: read anew, once, with it.
        self.store(old)
        wider = lambda proposal: sorted(set(vr.statement_pages(proposal)) | {99})
        with patch.object(vr, 'period_pages', wider):
            self.assertTrue(self.pending())
            self.flow.read(calls=calls)
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.flow.stored()['pages'], sorted(set(pages) | {99}))
            self.assertEqual(self.flow.stored()['pages_rule'], vr.PAGES_RULE)
            self.assertFalse(self.pending())
            self.flow.read(calls=calls)
            self.assertEqual(len(calls), 2)

    def test_an_older_outcome_whose_pages_grew_is_marked_then_read_anew(self):
        calls = []
        first = self.flow.read(calls=calls)
        pages = first['pages']
        stored = self.flow.stored()
        # Judged under older rules, from fewer pages than its period has now (live: proof 17, page 1 missing).
        old = {k: v for k, v in stored.items() if k != 'pages_rule'}
        old.update(status='not_proved', proof=vr.PROOF_VERSION - 1, message='The opening or closing balance could not be read.')
        self.store(old)
        wider = lambda proposal: sorted(set(vr.statement_pages(proposal)) | {99})
        with patch.object(vr, 'period_pages', wider):
            marked = self.flow.read(calls=calls)
            self.assertEqual((len(calls), marked['reason']), (1, 'already_read'))
            stamped = self.flow.stored()
            self.assertTrue(stamped.get('read_anew_at'))
            self.assertNotIn('pages_rule', stamped)
            self.assertTrue(vr._to_read_anew(stamped))
            self.assertTrue(self.pending())
            self.flow.read(calls=calls)
            self.assertEqual(len(calls), 2)
            read = self.flow.stored()
            self.assertEqual((read['pages'], read['pages_rule']), (sorted(set(pages) | {99}), vr.PAGES_RULE))
            self.assertNotIn('read_anew_at', read)
            self.assertFalse(vr._to_read_anew(read))
        # Same pages: re-judged from its stored reading, never marked to be read anew.
        self.store(old)
        self.flow.read(calls=calls)
        self.assertEqual(len(calls), 2)
        self.assertNotIn('read_anew_at', self.flow.stored())

    def test_with_the_rule_off_nothing_is_read_again(self):
        calls = []
        self.flow.read(calls=calls)
        old = {k: v for k, v in self.flow.stored().items() if k != 'pages_rule'}
        old.update(status='not_proved')
        self.store(old)
        with patch.object(vr, 'PAGES_RULE', 0), patch.object(vr, 'SUMMARY_PAGES', False):
            self.assertFalse(self.pending())
            self.assertEqual(self.flow.read(calls=calls)['reason'], 'already_read')
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
