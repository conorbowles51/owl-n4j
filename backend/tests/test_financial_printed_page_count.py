"""Printed page numbering that shows pages absent from the file holds the statement (any bank)."""
import importlib
import os
import unittest

from services.financial import printed_page_count as gate


def numbered(total, present, word='PAGINA {n} / {t}'):
    return {i + 1: f'MOVIMIENTOS {word.format(n=n, t=total)}' for i, n in enumerate(present)}


class MissingPagesTests(unittest.TestCase):
    def test_first_page_absent_is_held(self):
        pages = numbered(7, range(2, 8))
        gap = gate.missing_pages(pages, list(pages))
        self.assertEqual(gap, dict(printed_total=7, missing=[1], held=6))
        self.assertIn('Page 1 of 7', gate.message(gap))

    def test_complete_file_is_not_held(self):
        pages = numbered(5, range(1, 6))
        self.assertIsNone(gate.missing_pages(pages, list(pages)))

    def test_spanish_and_english_forms(self):
        for word in ('Página {n} de {t}', 'Page {n} of {t}', 'HOJA {n} DE {t}'):
            pages = numbered(3, (1, 3), word)
            self.assertEqual(gate.missing_pages(pages, list(pages))['missing'], [2], word)

    def test_unread_page_number_counts_against_the_gap(self):
        pages = numbered(4, (1, 2, 4))
        pages[4] = 'MOVIMIENTOS SIN NUMERO'
        self.assertIsNone(gate.missing_pages(pages, list(pages)))

    def test_neighbouring_pages_of_the_same_printing_count(self):
        pages = numbered(4, (1, 2, 3, 4))
        self.assertIsNone(gate.missing_pages(pages, [2, 3]))

    def test_unread_cover_next_to_the_statement_counts(self):
        pages = numbered(6, range(1, 7))
        pages[6] = 'COVER WITHOUT A READ NUMBER'
        self.assertIsNone(gate.missing_pages(pages, [1, 2, 3, 4, 5]))
        pages = numbered(7, range(2, 8))
        self.assertEqual(gate.missing_pages(pages, [2, 3])['missing'], [1])

    def test_pages_between_the_statement_pages_count(self):
        pages = numbered(6, range(1, 7))
        self.assertIsNone(gate.missing_pages(pages, [1, 3]))

    def test_another_printed_sequence_is_not_borrowed(self):
        pages = {1: 'PAGINA 1 / 2', 2: 'PAGINA 1 / 3', 3: 'PAGINA 2 / 3', 4: 'PAGINA 3 / 3'}
        self.assertIsNone(gate.missing_pages(pages, [2, 3, 4]))
        # Page 2 of 2 is missing only after the last page read: not proved (see the trailing-pages test).
        self.assertIsNone(gate.missing_pages(pages, [1]))
        pages = {1: 'PAGINA 2 / 3', 2: 'PAGINA 1 / 2'}
        self.assertEqual(gate.missing_pages(pages, [1])['missing'], [1, 3])

    def test_unnumbered_page_between_the_statement_pages_counts(self):
        # Card statement: numbered fronts, unnumbered backs; the backs may carry the missing numbers.
        pages = {1: 'Page 1 of 4', 2: 'terms', 3: 'Page 2 of 4', 4: 'notice', 5: 'Page 1 of 2'}
        self.assertIsNone(gate.missing_pages(pages, [1, 3]))

    def test_pages_missing_only_after_the_last_page_read_are_not_held(self):
        # Some banks count inserts in the printed total that the download never carries.
        pages = {1: 'Page 1 of 5', 2: '', 3: 'Page 2 of 5', 4: '', 5: 'Page 1 of 2'}
        self.assertIsNone(gate.missing_pages(pages, [1, 3]))

    def test_gap_between_pages_read_is_held(self):
        pages = numbered(6, (1, 2, 5, 6))
        self.assertEqual(gate.missing_pages(pages, list(pages))['missing'], [3, 4])

    def test_ambiguous_or_impossible_numbering_is_ignored(self):
        self.assertIsNone(gate.page_numbering('PAGINA 9 / 7'))
        self.assertIsNone(gate.page_numbering('PAGINA 1 / 7 PAGINA 1 / 8'))
        self.assertIsNone(gate.missing_pages({1: 'no numbering'}, [1]))

    def test_switch_off(self):
        os.environ['LOUPE_FINANCIAL_PRINTED_PAGE_COUNT_GATE'] = '0'
        try:
            off = importlib.reload(gate)
            pages = numbered(7, range(2, 8))
            self.assertIsNone(off.missing_pages(pages, list(pages)))
        finally:
            del os.environ['LOUPE_FINANCIAL_PRINTED_PAGE_COUNT_GATE']
            importlib.reload(gate)


class BlockerTests(unittest.TestCase):
    def proposal(self, gap):
        return dict(rows=[], metadata={}, printed_pages_missing=gap)

    def request(self, note=''):
        from services.financial.statement_import import StatementReviewDraft
        fields = {name: field.default for name, field in StatementReviewDraft.model_fields.items()
                  if not field.is_required()}
        return StatementReviewDraft.model_construct(**{**fields, **dict(rows=[], coverage_review_reason=note, holder='A',
            account_number='1', institution='B', currency='MXN', period_start='2026-01-01', period_end='2026-01-31')})

    def test_gap_blocks_until_a_person_notes_it(self):
        from services.financial.import_issues import retained_issues
        gap = dict(printed_total=7, missing=[1], held=6)
        issues = retained_issues(self.proposal(gap), self.request())
        self.assertEqual([i['kind'] for i in issues if i['kind'] == 'printed_pages_missing'], ['printed_pages_missing'])
        noted = retained_issues(self.proposal(gap), self.request('Checked the original: page 1 is the cover only'))
        self.assertFalse(any(i['kind'] == 'printed_pages_missing' for i in noted))

    def test_pages_printing_zero_movement_counts_need_no_note(self):
        # 2026-10-25 fin-queue: BBVA one-page files of a "PAGINA 2/6" summary printing TOTAL MOVIMIENTOS 0 / 0.
        from unittest import mock
        from services.financial import import_issues
        gap = dict(printed_total=6, missing=[1, 3, 4, 5, 6], held=1)
        total = lambda direction, count: dict(id=direction, kind='statement_total', excluded=True, fields=dict(
            total_direction=direction, printed_transaction_count=count, balance='0'))
        balance = lambda name, value: dict(id=name, kind='balance', excluded=True, fields=dict(description=name, balance=value))
        quiet = dict(self.proposal(gap), rows=[total('credit', '0'), total('debit', '0'),
                     balance('Opening Balance', '6025'), balance('Closing Balance', '6025')])
        held = lambda proposal: [i['kind'] for i in import_issues.retained_issues(proposal, self.request())
                                 if i['kind'] == 'printed_pages_missing']
        self.assertEqual(held(quiet), [])
        with mock.patch.object(import_issues, 'PAGES_MISSING_PRINTED_QUIET', False):
            self.assertEqual(held(quiet), ['printed_pages_missing'])
        # A count that is not zero, a missing count, or balances that differ still hold.
        for rows in ([total('credit', '0'), total('debit', '1'), *quiet['rows'][2:]],
                     [total('credit', '0'), *quiet['rows'][2:]],
                     [*quiet['rows'][:2], balance('Opening Balance', '6025'), balance('Closing Balance', '6000')]):
            self.assertEqual(held(dict(quiet, rows=rows)), ['printed_pages_missing'])

    def test_queue_names_the_missing_pages(self):
        from services.financial.batch_review_summary import reason
        from services.financial.review_queue import issue_sentence
        problem = dict(kind='printed_pages_missing', message=gate.message(dict(printed_total=7, missing=[1], held=6)))
        self.assertEqual(reason(problem), 'pages_missing')
        self.assertTrue(issue_sentence('pages_missing', [problem], {}).startswith('Page 1 of 7 printed pages'))


if __name__ == '__main__':
    unittest.main()
