"""Synthetic regressions for real-file date and description-splitting failures."""
import unittest
from copy import deepcopy

from services.financial.statement_import_card import propose_card_table
from services.financial.statement_layout_context import statement_layout_context
from tests.test_financial_statement_import_card import card_source, fee_source
from tests.test_financial_pdf_geometry_candidates import rectangle


def split_card():
    source = card_source()
    for index, texts in ((7, ['Trans Date', 'Post Date', 'Description', 'Amount']),
                         (8, ['May 11', 'May 12', 'EXAMPLE', 'SHOP 555-0100', '$31.79'])):
        positions = [(40, 40), (100, 40), (160, 45), (540, 40)] if index == 7 else [
            (40, 30), (100, 30), (160, 45), (215, 120), (550, 30)]
        source['rows'][index]['cells'] = [dict(column_index=column, expected_text=text,
            locator=rectangle(index*20, x=x, width=width)) for column, (text, (x, width)) in enumerate(zip(texts, positions))]
    return source


def propose(source):
    source['layout_context'] = statement_layout_context(source['rows'])
    return propose_card_table(source, 'USD', dict(period_start='2020-05-12', period_end='2020-06-11', account_reference='****1234'))


class CardSplitColumnsTests(unittest.TestCase):
    def test_split_description_preserves_exact_cells_and_amount_location(self):
        source = split_card()
        source['layout_context'] = statement_layout_context(source['rows'])
        before = deepcopy(source)
        row = propose(source)['rows'][8]
        self.assertEqual(row['fields']['description'], 'EXAMPLE SHOP 555-0100')
        self.assertEqual(row['fields']['amount_minor'], '3179')
        self.assertEqual(row['issues'], [])
        self.assertEqual(row['layout_context']['amount_source']['column_index'], 4)
        self.assertEqual(row['source_cells'], before['rows'][8]['cells'])
        self.assertEqual([c['expected_text'] for c in row['layout_context']['description_sources']], ['EXAMPLE', 'SHOP 555-0100'])
        self.assertEqual(source, before)

    def test_unreadable_aligned_amount_is_not_repaired(self):
        source = split_card()
        source['rows'][8]['cells'][4]['expected_text'] = '$3?.79'
        row = propose(source)['rows'][8]
        self.assertNotIn('amount_minor', row['fields'])
        self.assertTrue(row['issues'])
        self.assertEqual(row['fields']['description'], 'EXAMPLE SHOP 555-0100')

    def test_separate_advertisement_does_not_become_payment_description(self):
        source = split_card()
        cells = source['rows'][8]['cells']
        source['rows'][7]['cells'][3]['locator'] = rectangle(140, x=350, width=40)
        cells[4]['locator'] = rectangle(160, x=360, width=30)
        cells.append(dict(column_index=5, expected_text='Manage your card online', locator=rectangle(160, x=420, width=150)))
        row = propose(source)['rows'][8]
        self.assertEqual(row['fields']['amount_minor'], '3179')
        self.assertEqual(row['fields']['description'], 'EXAMPLE SHOP 555-0100')
        self.assertEqual(row['source_cells'][-1], cells[-1])
        self.assertEqual(row['issues'], [])

    def test_ambiguous_or_unmeasured_split_stays_an_explicit_unresolved_row(self):
        for damage in ('unmeasured', 'page', 'vertical', 'amount-alignment', 'overlap', 'two-amounts'):
            source = split_card()
            cells = source['rows'][8]['cells']
            if damage == 'unmeasured':
                cells[3]['locator'] = {'kind': 'page_only', 'page': 1}
            elif damage == 'page':
                cells[3]['locator']['page'] = 2
            elif damage == 'vertical':
                cells[3]['locator'] = rectangle(500, x=215, width=120)
            elif damage == 'amount-alignment':
                cells[4]['locator'] = rectangle(160, x=490, width=30)
            elif damage == 'overlap':
                cells[3]['locator'] = rectangle(160, x=200, width=120)
            else:
                cells.append(dict(column_index=5, expected_text='$12.00', locator=deepcopy(cells[4]['locator'])))
            with self.subTest(damage=damage):
                row = propose(source)['rows'][8]
                self.assertEqual(row['kind'], 'unresolved')
                self.assertFalse(row['excluded'])
                self.assertEqual(row['fields'], {})
                self.assertTrue(row['issues'])

    def test_recent_transaction_uses_posting_year_across_year_boundary(self):
        source = split_card()
        source['rows'][1]['cells'][0]['expected_text'] = 'Jan 01, 2021 - Jan 31, 2021 | 31 days in Billing Cycle'
        cells = source['rows'][8]['cells']
        cells[0]['expected_text'] = 'Dec 31'
        cells[1]['expected_text'] = 'Jan 02'
        row = propose(source)['rows'][8]
        self.assertEqual((row['fields']['date'], row['fields']['booking_date']), ('2020-12-31', '2021-01-02'))
        self.assertEqual(row['layout_context']['date_basis'], 'printed_posting_date')
        self.assertEqual(row['issues'], [])

    def test_posting_does_not_resolve_distant_invalid_or_reversed_dates(self):
        for trans, post, missing in [('Apr 1', 'May 12', 'date'), ('May 13', 'May 12', 'date'),
                                     ('May ?', 'May 12', 'date'), ('May 11', 'Jul 1', 'date'),
                                     ('May 20', 'Jul 1', 'booking_date')]:
            source = split_card()
            source['rows'][8]['cells'][0]['expected_text'] = trans
            source['rows'][8]['cells'][1]['expected_text'] = post
            with self.subTest(trans=trans, post=post):
                row = propose(source)['rows'][8]
                self.assertNotIn(missing, row['fields'])
                self.assertTrue(row['issues'])
                self.assertFalse(row['excluded'])

    def test_fee_transaction_also_retains_earlier_date_separate_from_posting(self):
        source = fee_source()
        source['rows'][7]['cells'][0]['expected_text'] = 'Feb 11'
        source['rows'][7]['cells'][1]['expected_text'] = 'Feb 12'
        row = propose_card_table(source, 'USD', dict(period_start='2022-02-12', period_end='2022-03-14', account_reference='****1234'))['rows'][7]
        self.assertEqual((row['fields']['date'], row['fields']['booking_date']), ('2022-02-11', '2022-02-12'))
        self.assertEqual(row['fields']['amount_minor'], '2500')
        self.assertEqual(row['issues'], [])
