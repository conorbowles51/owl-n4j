"""Truist consolidated statements (one PDF, one statement per account): the library profile and the general engine
rules it needs. Fixtures are stored readings of real pages with every name, address, account number, card digit,
payment id and production stamp replaced (layout, positions, amounts and the bank's own wording kept)."""
import json
import os
import unittest
from copy import deepcopy
from decimal import Decimal
from unittest import mock

from services.financial import statement_engine as E
from services.financial.statement_engine import read_statements
from services.financial.statement_engine_routing import _profiled

FIXTURES = os.path.dirname(__file__)


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as handle:
        return json.load(handle)


def reading(sources):
    statements, profile = _profiled(sources, read_statements(sources))
    return {st['account_reference']: st for st in statements}, profile


def sums(statement):
    rows = [r for r in statement['_rows'] if r['kind'] == 'transaction' and not r['excluded']]
    credit = sum(int(r['fields'].get('credit') or 0) for r in rows)
    debit = sum(int(r['fields'].get('debit') or 0) for r in rows)
    return len(rows), credit, debit


def control(statement, description):
    return next(r['fields']['balance'] for r in statement['_rows'] if r['fields'].get('description') == description)


class ConsolidatedStatementTests(unittest.TestCase):
    def setUp(self):
        self.statements, self.profile = reading(fixture('financial_truist_consolidated_fixture.json'))

    def test_each_account_is_its_own_proved_period(self):
        self.assertEqual(self.profile, 'truist-consolidated')
        self.assertEqual(set(self.statements), {'9990001112223', '9990004445556'})
        for statement in self.statements.values():
            self.assertTrue(statement['engine']['proved'], statement['engine'])
            # The period is the two balances' printed dates; the production stamp '03/17/2025' on every page is not.
            self.assertEqual((statement['period_start'], statement['period_end']), ('2024-04-11', '2024-05-13'))
            self.assertEqual((statement['currency'], statement['institution']), ('USD', 'Truist Bank'))
            self.assertEqual(statement['holder'], 'JANE Q EXAMPLE PERSON')

    def test_checking_balances_rows_and_totals(self):
        checking = self.statements['9990001112223']
        self.assertEqual(control(checking, 'Opening Balance'), '33365')
        self.assertEqual(control(checking, 'Closing Balance'), '-62981')  # printed '= $-629.81'
        self.assertEqual(control(checking, 'Total debit'), '475104')
        self.assertEqual(control(checking, 'Total credit'), '378758')
        self.assertEqual(sums(checking), (128, 378758, 475104))
        self.assertEqual(33365 + 378758 - 475104, -62981)
        # 'OVERDRAFT FEE NOT CHARGED 36 | 36.00': the amount is the amount column's figure only.
        fees = [r for r in checking['_rows'] if r['kind'] == 'transaction'
                and r['fields']['description'].startswith('OVERDRAFT FEE NOT CHARGED')]
        self.assertTrue(fees)
        self.assertTrue(all(r['fields']['debit'] == '3600' for r in fees))
        # A printed 0.00 line is kept as a zero line.
        self.assertEqual(sum(r['kind'] == 'zero_line' for r in checking['_rows']), 1)

    def test_savings_reads_only_its_account_summary(self):
        savings = self.statements['9990004445556']
        # The interest summary printed beside the account summary ('Interest paid this statement period $0.01') is
        # not a control and not a movement.
        self.assertEqual(control(savings, 'Opening Balance'), '326384')
        self.assertEqual(control(savings, 'Closing Balance'), '327')
        self.assertEqual(sums(savings), (21, 1, 326058))
        self.assertEqual(savings['page_numbers'][0], 4)

    def test_continued_notice_and_stamp_are_not_descriptions(self):
        for statement in self.statements.values():
            for row in statement['_rows']:
                if row['kind'] == 'transaction':
                    text = row['fields']['description'].lower()
                    self.assertNotIn('continued', text)
                    self.assertNotIn('_truist_', text)

    def test_december_to_january_dates_take_the_period_years(self):
        sources = deepcopy(fixture('financial_truist_consolidated_fixture.json'))
        for source in sources:
            for row in source['rows']:
                for cell in row['cells']:
                    text = cell['expected_text']
                    text = text.replace('04/11/2024', '12/11/2023').replace('05/13/2024', '01/13/2024')
                    if len(text) == 5 and text[2] == '/' and text[:2] in ('04', '05'):
                        text = ('12' if text[:2] == '04' else '01') + text[2:]
                    cell['expected_text'] = text
        statements, _ = reading(sources)
        checking = statements['9990001112223']
        self.assertTrue(checking['engine']['proved'], checking['engine'])
        self.assertEqual((checking['period_start'], checking['period_end']), ('2023-12-11', '2024-01-13'))
        dates = {r['fields']['date'] for r in checking['_rows'] if r['kind'] == 'transaction'}
        self.assertIn('2023-12-12', dates)
        self.assertIn('2024-01-07', dates)
        self.assertTrue(all('2023-12-11' <= d <= '2024-01-13' for d in dates))

    def test_balance_dates_rule_switch(self):
        with mock.patch.object(E, 'BALANCE_DATES_PERIOD', False):
            E._READINGS.clear()
            E._LIVE_READINGS.clear()
            statements = read_statements(fixture('financial_truist_consolidated_fixture.json'),
                                         profile=_truist())
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        self.assertTrue(all(not st['period_start'] and not st['engine']['proved'] for st in statements))


def _truist():
    from services.financial.statement_engine_profiles import PROFILES
    return next(p for p in PROFILES if p['name'] == 'truist-consolidated')


class ChecksTableAndQuietSavingsTests(unittest.TestCase):
    def setUp(self):
        self.statements, self.profile = reading(fixture('financial_truist_checks_fixture.json'))

    def test_checks_table_has_its_own_amount_column_and_total(self):
        checking = self.statements['9990001112223']
        self.assertTrue(checking['engine']['proved'], checking['engine'])
        self.assertEqual((checking['period_start'], checking['period_end']), ('2023-10-13', '2023-11-10'))
        self.assertEqual(control(checking, 'Opening Balance'), '180043')
        self.assertEqual(control(checking, 'Closing Balance'), '-47685')
        count, credit, debit = sums(checking)
        self.assertEqual((credit, debit), (1140269, 650000 + 717997))
        # Two debit tables: each printed total is scoped to its own heading.
        scoped = {r['fields'].get('total_scope'): r['fields']['balance'] for r in checking['_rows']
                  if r['kind'] == 'statement_total' and r['fields'].get('total_direction') == 'debit'}
        self.assertEqual(scoped, {'checks': '650000', 'other withdrawals, debits and service charges': '717997'})
        checks = [r for r in checking['_rows'] if r['kind'] == 'transaction' and r['fields'].get('debit') in ('450000', '200000')]
        self.assertEqual(len(checks), 2)

    def test_a_check_printed_without_its_number_is_described_by_its_table_heading(self):
        # (2) prints '01/05 | 210.00' under 'Checks' with no check number: a real check, not an unreadable line.
        sources = fixture('financial_truist_checks_fixture.json')
        for source in sources:
            for row in source['rows']:
                if [c['expected_text'] for c in row['cells']] == ['10/30', 'MERCHANT1', '4,500.00']:
                    row['cells'] = [c for c in row['cells'] if c['expected_text'] != 'MERCHANT1']
        checking = reading(sources)[0]['9990001112223']
        self.assertTrue(checking['engine']['proved'], checking['engine'])
        [check] = [r for r in checking['_rows'] if r['kind'] == 'transaction' and r['fields'].get('debit') == '450000']
        self.assertEqual((check['fields']['description'], check['fields']['description_basis']), ('Checks', 'table_heading'))
        self.assertNotIn('The transaction description is missing.', check['issues'])
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        with mock.patch.object(E, 'HEADING_DESCRIBES_ROW', False):
            checking = reading(sources)[0]['9990001112223']
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        [check] = [r for r in checking['_rows'] if r['kind'] == 'transaction' and r['fields'].get('debit') == '450000']
        self.assertIn('The transaction description is missing.', check['issues'])

    def test_quiet_savings_is_proved_by_its_printed_zero_components(self):
        savings = self.statements['9990004445556']
        self.assertTrue(savings['engine']['proved'], savings['engine'])
        self.assertEqual(savings['engine'].get('basis'), E.SUMMARY_COMPONENTS_BASIS)
        self.assertEqual(sums(savings), (0, 0, 0))
        self.assertEqual((control(savings, 'Opening Balance'), control(savings, 'Closing Balance')), ('250', '250'))


    def test_quiet_savings_zero_lines_are_found_again_for_the_no_activity_proof(self):
        # The summary prints the interest block beside its components, in the profile's own words: before, the
        # proof could not find the lines again and every quiet month waited for a person ('line_missing').
        from services.financial import statement_printed_no_activity as N
        sources = fixture('financial_truist_checks_fixture.json')
        savings = self.statements['9990004445556']
        evidence = N.summary_components_evidence(savings['_rows'], savings, 'USD', sources, family='generic')
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual(sorted(line['text'].split(' + ')[0].split(' - ')[0] for line in evidence['cited'][2:]),
                         ['Deposits, credits and interest', 'Other withdrawals, debits and service charges'])
        with mock.patch.object(N, 'PROFILE_COMPONENT_LINES', False):
            evidence = N.summary_components_evidence(savings['_rows'], savings, 'USD', sources, family='generic')
        self.assertEqual(evidence['reason'], 'line_missing')



class BusinessStatementTests(unittest.TestCase):
    """'Your account statement' for a business account (OPDMD66, Bee Thrifty): one account, a product name with
    digits ('BUSINESS VALUE 200 CHECKING'), and a blank fourth page the numbering counts ('Page 1 of 4')."""

    def setUp(self):
        self.statements, self.profile = reading(fixture('financial_truist_business_fixture.json'))

    def test_business_statement_is_proved(self):
        self.assertEqual(self.profile, 'truist-consolidated')
        [account] = self.statements
        statement = self.statements[account]
        self.assertEqual(account, '9990007778889')
        self.assertTrue(statement['engine']['proved'], statement['engine'])
        self.assertEqual((statement['period_start'], statement['period_end']), ('2023-09-29', '2023-10-31'))
        self.assertEqual((control(statement, 'Opening Balance'), control(statement, 'Closing Balance')),
                         ('5162173', '5122744'))
        count, credit, debit = sums(statement)
        self.assertEqual((credit, debit), (33564907, 33604336))
        # Page 4 is printed blank: no movement can be on it, after the table printed its last total (A3).
        self.assertTrue(statement['engine'].get('pages_unread_after_table'))

    def test_a_product_name_with_digits_still_names_the_account(self):
        self.assertEqual(E._number_heading_account(dict(text='BUSINESS VALUE 200 CHECKING 1000000000001')),
                         '1000000000001')


    def test_checks_printed_three_to_a_line_are_one_movement_each(self):
        statements, profile = reading(fixture('financial_truist_side_by_side_checks_fixture.json'))
        statement = statements['9990006667778']
        self.assertTrue(statement['engine']['proved'], statement['engine'])
        self.assertEqual((control(statement, 'Opening Balance'), control(statement, 'Closing Balance')),
                         ('7550838', '4473278'))
        checks = [r for r in statement['_rows'] if r['kind'] == 'transaction' and ':box' in r['id']]
        self.assertEqual(len(checks), 8)
        self.assertEqual(sum(int(r['fields']['debit']) for r in checks), 8033700)  # 'Total checks = $80,337.00'
        # Each check keeps its own printed cell: date, number and amount of that check only.
        self.assertEqual({len(r['source_cells']) for r in checks}, {1})
        self.assertTrue(all(r['source_cells'][0]['expected_text'].startswith(r['fields']['date'][5:].replace('-', '/'))
                            for r in checks))
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        with mock.patch.object(E, 'REPEATED_COLUMN_GROUPS', False):
            statements, _ = reading(fixture('financial_truist_side_by_side_checks_fixture.json'))
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        self.assertFalse(any(st['engine']['proved'] for st in statements.values()))


class HolderBlockRuleTests(unittest.TestCase):
    def test_spaced_zip_is_a_postal_line(self):
        self.assertTrue(E._postal(E.fold('SPRING HILLS MD 2 0 9 9 9 - 1 2 3 4')))
        self.assertTrue(E._postal(E.fold('SPRING HILLS MD 2 0 9 9 9')))
        with mock.patch.object(E, 'SPACED_ZIP', False):
            self.assertFalse(E._postal(E.fold('SPRING HILLS MD 2 0 9 9 9 - 1 2 3 4')))

    def test_presort_line_is_not_a_name(self):
        self.assertTrue(E._presort_line(dict(text='111-22-33-44 55555 0 C 001 07 S 66 002')))
        self.assertFalse(E._presort_line(dict(text='JANE Q EXAMPLE PERSON')))
        self.assertFalse(E._presort_line(dict(text='100 MAIN ST APT 2')))

    def test_a_column_heading_is_not_a_holder(self):
        found = set()
        row = dict(raw=dict(cells=[dict(expected_text='ACCOUNT NAME'), dict(expected_text='ACCOUNT NUMBER'),
                                   dict(expected_text='BALANCE($)')]))
        E._holder_label(row, found)
        self.assertEqual(found, set())
        row = dict(raw=dict(cells=[dict(expected_text='ACCOUNT NAME'), dict(expected_text='JANE Q EXAMPLE')]))
        E._holder_label(row, found)
        self.assertEqual(found, {'JANE Q EXAMPLE'})

    def test_number_heading_account(self):
        self.assertEqual(E._number_heading_account(dict(text='TRUIST ONLINE SAVINGS 9990004445556')), '9990004445556')
        self.assertEqual(E._number_heading_account(dict(text='TRUIST STUDENT CHECKING 9990001112223 (continued)')),
                         '9990001112223')
        self.assertEqual(E._number_heading_account(dict(text='CUSTOMER ID 12345678 (continued)')), '12345678')
        self.assertEqual(E._number_heading_account(dict(text='TELEFONO 5512345678')), '')


if __name__ == '__main__':
    unittest.main()
