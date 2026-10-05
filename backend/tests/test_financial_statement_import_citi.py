"""Synthetic Citi card statements: many billing cycles in one PDF.

The structure (summary page, "Page n of N" pages, left transaction column
beside a rewards column, two-line entries, totals printed on their own row)
follows real Citi card productions; every name, number and amount is
invented. No client records in fixtures.
"""
from copy import deepcopy
from unittest import TestCase

from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_import_citi import citi_catalog, citi_no_activity_evidence, propose_citi_statement
from services.financial.statement_review_checks import check_statement_rows

HOLDER = 'EXAMPLE CARDHOLDER'
AMOUNT_RIGHT = 387200


def source(page, rows):
    return dict(page_number=page, table_index=0, source_revision='a' * 64, table_source='text_alignment',
        rows=[dict(row_index=i, cells=[dict(column_index=j, expected_text=t,
            locator=dict(kind='page_rectangle', page=page, rect=[x, y, x + w, y + 8000],
                page_size=[612000, 792000], units='millipoints', space='pdf_displayed'))
            for j, (x, y, w, t) in enumerate(cells)]) for i, cells in enumerate(rows)])


def amount(y, value, right=AMOUNT_RIGHT):
    return (right - 4500 * len(value), y, 4500 * len(value), value)


def cover(page, period, summary):
    previous, payments, credits, purchases, fees, interest, new = summary
    return source(page, [
        [(64080, 29887, 120000, 'CITI®/AADVANTAGE® PLATINUM SELECT® CARD')],
        [(63119, 72002, 90000, HOLDER), (428160, 74882, 150000, 'Billing Inquiries and Customer Service')],
        [(63119, 83171, 250000, 'Member Since 2020 Account number ending in: 1234')],
        [(63119, 93602, 50000, 'Billing Period:'), (117120, 93602, 70000, period)],
        [(351119, 104879, 60000, 'www.citicards.com')],
        [(391440, 182615, 70000, 'Account Summary')],
        [(391440, 195645, 70000, 'Previous balance'), (532799, 195645, 44000, previous)],
        [(63120, 205405, 280000, 'Late Payment Warning: example text'), (391440, 206445, 40000, 'Payments'), (548640, 206445, 28000, payments)],
        [(391440, 217244, 40000, 'Credits'), (548640, 217244, 28000, credits)],
        [(391440, 227325, 40000, 'Purchases'), (546239, 227325, 30000, purchases)],
        [(391440, 238125, 60000, 'Cash advances'), (546239, 238125, 30000, '+$0.00')],
        [(391440, 250144, 30000, 'Fees'), (543359, 250144, 33000, fees)],
        [(391440, 260445, 30000, 'Interest'), (541200, 260445, 35000, interest)],
        [(391440, 274364, 50000, 'New balance'), (529200, 274364, 47000, new)],
        [(391440, 294455, 50000, 'Credit Limit')],
        # The payment coupon repeats the new balance outside the summary.
        [(386160, 598559, 50000, 'New balance'), (498720, 598559, 40000, new)],
        [(386160, 663405, 150000, 'Account number ending in 1234')],
    ])


def header(number, count):
    return [[(63120, 23042, 60000, 'www.citicards.com'), (347520, 23042, 120000, 'Customer Service 1-800-000-0000'),
             (551760, 23000, 40000, f'Page {number} of {count}')],
            [(63119, 41463, 90000, HOLDER)],
            [(63119, 214065, 70000, 'Account Summary'), (414719, 214065, 160000, 'Rewards text column')],
            [(63119, 230360, 20000, 'Trans.'), (109199, 230360, 20000, 'Post')],
            [(63119, 242264, 20000, 'date'), (109199, 242264, 20000, 'date'), (143279, 242264, 50000, 'Description'),
             (358559, 242264, 27000, 'Amount'), (414719, 242264, 160000, 'more rewards text')]]


def activity(page, count=2):
    rows = header(2, count) + [
        [(63119, 263922, 140000, 'Payments, Credits and Adjustments')],
        [(108959, 278339, 22000, '05/20'), (143039, 278339, 110000, 'ONLINE PAYMENT, THANK YOU'), amount(278339, '-$100.00'),
         (414720, 278339, 150000, 'Rewards text')],
        [(143039, 288920, 10000, '70'), (168399, 288920, 30000, '0000US'), (237359, 288920, 20000, '0000')],
        [(63119, 314310, 80000, 'Standard Purchases')],
        [(63119, 328417, 22000, '05/10'), (108479, 328417, 22000, '05/11'), (143039, 328417, 80000, 'EXAMPLE MARKET'),
         (232846, 328417, 50000, 'EXAMPLE CITY DC'), amount(328417, '$100.00'), (414720, 328417, 150000, 'Rewards text')],
        [(63119, 337400, 40000, 'REF12345'), (143039, 337400, 10000, '61'), (167279, 337400, 40000, 'A5814USA'), (231119, 337400, 20000, '2222')],
        # A two-line entry: its amount is printed on the second line.
        [(63119, 350570, 22000, '06/01'), (108479, 350570, 22000, '06/01'), (143039, 350570, 80000, 'EXAMPLE TRAIN'),
         (226534, 350570, 50000, '2020000000')],
        [(143039, 361880, 140000, 'Digital account number ending in 9999'), amount(361880, '$50.00')],
        [(63119, 430775, 60000, 'Fees charged')],
        [(63119, 450200, 20000, 'Date'), (108959, 450200, 50000, 'Description'), (358559, 450200, 27000, 'Amount')],
        [(63119, 465320, 22000, '06/04'), (108959, 465320, 140000, 'LATE FEE - MAY PAYMENT PAST DUE'), amount(465320, '$41.00')],
        [(63119, 479000, 50000, '00000000 66'), (165999, 479000, 20000, '0000')],
        # The total's amount sits on its own row just above its label.
        [amount(489500, '$41.00'), (414719, 488000, 160000, 'Rewards text')],
        [(63119, 494120, 180000, 'Total fees charged in this billing period')],
        [(63119, 518855, 60000, 'Interest charged')],
        [(63119, 537560, 20000, 'Date'), (112079, 537560, 50000, 'Description'), (358559, 537560, 27000, 'Amount')],
        [(63119, 552680, 22000, '06/04'), (112079, 552680, 150000, 'INTEREST CHARGED TO STANDARD PURCH'), amount(552680, '$20.00')],
        [(63119, 566360, 30000, '00000000'), (112079, 566360, 10000, '84'), (168399, 566360, 20000, '0000')],
        [(63119, 581480, 180000, 'Total interest charged in this billing period'), amount(581480, '$20.00')],
        [(66720, 603575, 100000, '2025 totals year-to-date')],
        [(92951, 625160, 120000, 'Total fees charged in 2025'), (313679, 625160, 30000, '$999.00')],
        [(66720, 662375, 100000, 'Interest charge calculation')],
        [(73839, 726440, 60000, 'Standard Purch'), (358080, 726440, 25000, '$20.00')],
    ]
    return source(page, rows)


def quiet(page, count=2):
    return source(page, header(2, count) + [
        [(63119, 430775, 60000, 'Fees charged')],
        [(63119, 494120, 180000, 'Total fees charged in this billing period'), amount(494120, '$0.00')],
        [(63119, 518855, 60000, 'Interest charged')],
        [(63119, 581480, 180000, 'Total interest charged in this billing period'), amount(581480, '$0.00')],
        [(66720, 603575, 100000, '2025 totals year-to-date')],
    ])


def statement():
    """Two cycles, newest first, as Citi productions print them."""
    return [cover(1, '05/06/25-06/04/25', ('$1,000.00', '-$100.00', '-$0.00', '+$150.00', '+$41.00', '+$20.00', '$1,111.00')),
            activity(2),
            cover(3, '04/05/25-05/05/25', ('$1,000.00', '-$0.00', '-$0.00', '+$0.00', '+$0.00', '+$0.00', '$1,000.00')),
            quiet(4)]


def rows_of(sources, choice):
    return propose_citi_statement([s for s in sources if s['page_number'] in choice['page_numbers']], 'USD', choice)['rows']


class CitiCatalogTests(TestCase):
    def test_every_cycle_is_its_own_statement_and_every_page_is_assigned(self):
        sources = statement(); before = deepcopy(sources)
        catalog = statement_catalog(sources)
        self.assertTrue(catalog['complete_coverage'])
        choices = currencies_by_statement(catalog['statements'], sources)
        self.assertEqual([(c['layout_id'], c['account_reference'], c['period_start'], c['period_end'], c['page_numbers'], c['currency'])
                          for c in choices],
                         [('citi-card', '****1234', '2025-05-06', '2025-06-04', [1, 2], 'USD'),
                          ('citi-card', '****1234', '2025-04-05', '2025-05-05', [3, 4], 'USD')])
        self.assertEqual({c['holder'] for c in choices}, {HOLDER})
        self.assertEqual(sources, before)

    def test_a_cycle_missing_or_misnumbering_a_page_is_not_recognised(self):
        s = statement(); del s[1]
        self.assertEqual([c['period_end'] for c in citi_catalog(s)[0]], ['2025-05-05'])
        s = statement(); s[1]['rows'][0]['cells'][2]['expected_text'] = 'Page 3 of 3'
        self.assertEqual([c['period_end'] for c in citi_catalog(s)[0]], ['2025-05-05'])
        s = statement(); s[0]['rows'][4]['cells'][0]['expected_text'] = 'www.example.com'
        self.assertEqual([c['period_end'] for c in citi_catalog(s)[0]], ['2025-05-05'])


class CitiProposalTests(TestCase):
    def test_lines_balances_and_totals_reconcile_as_amounts_owed(self):
        sources = statement()
        active, quiet_cycle = citi_catalog(sources)[0]
        rows = rows_of(sources, active)
        paid = [r for r in rows if not r['excluded']]
        self.assertEqual([(r['kind'], r['fields'].get('date'), r['fields'].get('booking_date'), r['fields']['direction'],
                           r['fields']['amount_minor'], r['fields']['description']) for r in paid], [
            ('transaction', '2025-05-20', None, 'credit', '10000', 'ONLINE PAYMENT, THANK YOU'),
            ('transaction', '2025-05-10', '2025-05-11', 'debit', '10000', 'EXAMPLE MARKET EXAMPLE CITY DC'),
            ('transaction', '2025-06-01', '2025-06-01', 'debit', '5000', 'EXAMPLE TRAIN 2020000000 Digital account number ending in 9999'),
            ('transaction', '2025-06-04', None, 'debit', '4100', 'LATE FEE - MAY PAYMENT PAST DUE'),
            ('transaction', '2025-06-04', None, 'debit', '2000', 'INTEREST CHARGED TO STANDARD PURCH')])
        self.assertEqual(paid[1]['fields']['reference'], 'REF12345 61 A5814USA 2222')
        self.assertEqual([r['fields'].get('charge_group') for r in paid], [None, None, None, 'fee', 'interest'])
        balances = {r['fields']['description']: r['fields']['balance'] for r in rows if r['kind'] == 'balance'}
        self.assertEqual(balances, {'Opening Balance': '100000', 'Closing Balance': '111100'})
        self.assertEqual(sorted(r['fields']['total_scope'] for r in rows if r['kind'] == 'statement_total'), ['fee', 'interest'])
        checks = {c['kind']: c['status'] for c in check_statement_rows(rows, liability=True)['checks']}
        self.assertEqual((checks['closing_balance'], checks['fee_total'], checks['interest_total']), ('matches', 'matches', 'matches'))
        quiet_rows = rows_of(sources, quiet_cycle)
        self.assertFalse([r for r in quiet_rows if not r['excluded']])
        self.assertEqual({c['kind']: c['status'] for c in check_statement_rows(quiet_rows, liability=True)['checks']}['closing_balance'], 'matches')

    def test_a_disagreement_with_the_printed_summary_is_held_never_admitted(self):
        def held(change):
            s = statement(); change(s)
            choice = citi_catalog(s)[0][0]
            return [r for r in rows_of(s, choice) if r['kind'] == 'unresolved' and not r['excluded'] and r['issues']]
        self.assertEqual(held(lambda s: None), [])
        # A purchase read differently from the printed purchases.
        self.assertTrue(held(lambda s: s[1]['rows'][9]['cells'][4].update(expected_text='$10.00')))
        # A payment line lost from the page.
        self.assertTrue(held(lambda s: s[1]['rows'].pop(6)))
        # An amount on its own line that belongs to no total or entry.
        self.assertTrue(held(lambda s: s[1]['rows'][18]['cells'][0].update(expected_text='Example notice')))

    def test_dates_are_month_first_and_a_line_posted_on_the_previous_closing_day_keeps_its_date(self):
        s = statement()
        s[1]['rows'][6]['cells'][0]['expected_text'] = '05/05'
        rows = rows_of(s, citi_catalog(s)[0][0])
        payment = next(r for r in rows if r['fields'].get('description') == 'ONLINE PAYMENT, THANK YOU')
        self.assertEqual((payment['fields']['date'], payment['issues']), ('2025-05-05', []))


class CitiNoActivityTests(TestCase):
    def test_a_summary_printing_every_movement_as_zero_proves_the_cycle_quiet(self):
        sources = statement()
        active, quiet_cycle = currencies_by_statement(citi_catalog(sources)[0], sources)
        pages = [s for s in sources if s['page_number'] in quiet_cycle['page_numbers']]
        rows = rows_of(sources, quiet_cycle)
        evidence = citi_no_activity_evidence(pages, quiet_cycle, rows, 'USD')
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['family'], evidence['balance_minor'], len(evidence['cited'])), ('citi-card', '100000', 8))
        # A cycle with movements is not a quiet question; a nonzero component is held.
        active_pages = [s for s in sources if s['page_number'] in active['page_numbers']]
        self.assertIsNone(citi_no_activity_evidence(active_pages, active, rows_of(sources, active), 'USD').get('verified') or None)
        s = statement(); s[2]['rows'][11]['cells'][1]['expected_text'] = '+$5.00'
        pages = [p for p in s if p['page_number'] in quiet_cycle['page_numbers']]
        self.assertEqual(citi_no_activity_evidence(pages, quiet_cycle, rows_of(s, quiet_cycle), 'USD')['reason'], 'totals_not_zero')
