"""Proposals for a held statement's missing currency, bank, holder and account number.

Pins the order (same account's saved statements, then the case's usual
currency), the auto-confirmation limits (two independent exact fields, at
least two agreeing statements for a currency, no saved statement on the same
dates, a holder established on both sides of the period) and the fail-closed
cases measured on the real truth set (an account renamed, two accounts sharing
the last digits, several currencies under one account number).
"""
import os
from unittest import TestCase
from unittest.mock import patch

from services.financial import field_proposals as fp
from services.financial.field_proposals import CaseKnowledge, KnownAccount, SavedStatement


def saved(currency='MXN', start='2021-01-01', end='2021-01-31', holder='ACME SA DE CV', institution='BANCO SANTANDER',
          account='65-1234567-8'):
    return SavedStatement(currency=currency, period_start=start, period_end=end, institution=institution,
                          holder=holder, account_number=account)


def account(*statements, number='65-1234567-8', institution='Santander', currency='MXN', key='a1'):
    digits, masked = fp.account_identity(number)
    return KnownAccount(key=key, account=number, digits=digits, masked=masked, institution=institution,
                        currency=currency, statements=list(statements))


def knowledge(*accounts, default='MXN', default_count=10, total=12):
    return CaseKnowledge(accounts=list(accounts), default_currency=default, default_count=default_count,
                         saved_total=total)


def values(**overrides):
    base = dict(currency='', institution='BANCO SANTANDER MEXICO', holder='ACME SA DE CV',
                account_number='65-1234567-8', period_start='2021-06-01', period_end='2021-06-30')
    base.update(overrides)
    return base


MONTHS = [saved(start=f'2021-{m:02d}-01', end=f'2021-{m:02d}-28') for m in (1, 2, 3, 9, 10)]


class CurrencyTests(TestCase):
    def test_same_account_agreeing_statements_confirm_the_currency(self):
        result = fp.propose(values(), knowledge(account(*MONTHS)))
        currency = result['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'same_account', True))
        self.assertEqual(currency['label'], "same account's 5 saved statements, all MXN")

    def test_one_saved_statement_is_a_proposal_only(self):
        currency = fp.propose(values(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['value'], currency['confirmed']), ('MXN', False))

    def test_account_number_alone_is_one_field(self):
        currency = fp.propose(values(institution='', holder=''), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('same_account', False))

    def test_saved_statement_on_the_same_dates_blocks_confirmation(self):
        # Several currency sections can share one account number and one period.
        same = saved(start='2021-06-01', end='2021-06-30')
        currency = fp.propose(values(), knowledge(account(*MONTHS, same)))['currency']
        self.assertEqual((currency['value'], currency['confirmed'], currency['same_dates_saved']), ('MXN', False, True))

    def test_disagreeing_currencies_fall_back_to_the_case_default_unconfirmed(self):
        mixed = account(*MONTHS, saved(currency='USD', start='2021-11-01', end='2021-11-30'))
        currency = fp.propose(values(), knowledge(mixed, default='USD', default_count=7, total=9))['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('USD', 'case_default', False))
        self.assertEqual(currency['label'], "the case's usual currency (7 of 9 saved statements)")

    def test_account_record_currency_must_agree_too(self):
        currency = fp.propose(values(), knowledge(account(*MONTHS, currency='EUR')))['currency']
        self.assertEqual(currency['basis'], 'case_default')

    def test_no_account_identity_gives_the_case_default(self):
        currency = fp.propose(values(account_number='', institution='', holder=''), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('case_default', False))

    def test_no_saved_statements_no_proposal(self):
        self.assertEqual(fp.propose(values(), CaseKnowledge(accounts=[])), {})

    def test_a_printed_currency_is_never_replaced(self):
        self.assertEqual(fp.propose(values(currency='USD'), knowledge(account(*MONTHS))), {})


class PrintedElsewhereCurrencyTests(TestCase):
    """A currency the statement prints only in its holdings is proposed with its page, never confirmed by itself."""
    printed = dict(value='MXN', page_number=2, table_index=1, row_index=2, expected_text='0 MXN', cells=1)

    def test_proposed_with_its_page_and_never_confirmed(self):
        for known in (knowledge(), knowledge(default='USD'), knowledge(account(MONTHS[0]))):
            currency = fp.propose(values(printed_currency=self.printed), known)['currency']
            self.assertEqual((currency['value'], currency['basis'], currency['confirmed']),
                             ('MXN', 'printed_on_statement', False))
            self.assertEqual(currency['label'], "printed in this statement's holdings on page 2")
            self.assertEqual(currency['cited']['expected_text'], '0 MXN')
        self.assertIn('Confirm it', fp.sentence('currency', fp.propose(values(printed_currency=self.printed), knowledge())))

    def test_an_agreeing_automatic_confirmation_stands_and_a_disagreeing_one_is_withdrawn(self):
        agreeing = fp.propose(values(printed_currency=self.printed), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((agreeing['basis'], agreeing['confirmed']), ('same_account', True))
        usd = [saved(currency='USD', start=m.period_start, end=m.period_end) for m in MONTHS]
        other = fp.propose(values(printed_currency=self.printed), knowledge(account(*usd, currency='USD')))['currency']
        self.assertEqual((other['value'], other['basis'], other['confirmed']), ('MXN', 'printed_on_statement', False))

    def test_a_printed_currency_on_the_statement_itself_is_never_replaced(self):
        self.assertNotIn('currency', fp.propose(values(currency='USD', printed_currency=self.printed), knowledge()))

    def test_the_summary_carries_the_cited_cell(self):
        self.assertEqual(fp.summary_values(dict(printed_currency=self.printed))['printed_currency'], self.printed)
        self.assertIsNone(fp.summary_values({})['printed_currency'])


class HoldingsCurrencyTests(TestCase):
    def test_one_code_in_the_holdings_currency_column_with_its_cell(self):
        from services.financial.statement_currency import printed_holdings_currency
        from tests.test_financial_statement_import_proposal import source

        def page(*grid, number=2):
            data = source(list(grid))
            data['page_number'] = number
            return data
        heading = ['EMISORA SERIE CUP MON', 'CANTIDAD', 'VALUACION PESOS']
        found = printed_holdings_currency([page(heading, ['+FUND', '0) MXN)', '1,000.00'])])
        self.assertEqual((found['value'], found['page_number'], found['expected_text']), ('MXN', 2, '0) MXN)'))
        for grid in ([['EXAMPLE', '0 MXN']],                                     # no holdings heading
                     [heading, ['FX USD/MXN', '17.00']],                         # an exchange rate
                     [heading, ['+FUND', 'MXN'], ['+OTHER', 'USD']],             # two currencies
                     [heading, ['+FUND', 'CUP ALL', '1.00']]):                   # not a holdings code
            with self.subTest(grid=grid):
                self.assertIsNone(printed_holdings_currency([page(*grid)]))
        self.assertIsNone(printed_holdings_currency([page(heading, ['+FUND', 'MXN']), page(heading, ['+X', 'USD'], number=3)]))


class DetailTests(TestCase):
    def test_holder_confirmed_when_bank_matches_and_both_sides_print_it(self):
        holder = fp.propose(values(holder='', currency='MXN'), knowledge(account(*MONTHS)))['holder']
        self.assertEqual((holder['value'], holder['confirmed']), ('ACME SA DE CV', True))
        self.assertIn('account number and bank match', holder['label'])

    def test_holder_after_every_saved_statement_is_a_proposal_only(self):
        # The truth set holds an account printed under a new company name after its saved statements.
        holder = fp.propose(values(holder='', currency='MXN', period_start='2025-03-01', period_end='2025-03-31'),
                            knowledge(account(*MONTHS)))['holder']
        self.assertEqual((holder['value'], holder['confirmed']), ('ACME SA DE CV', False))

    def test_renamed_account_proposes_no_holder(self):
        renamed = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'))
        self.assertNotIn('holder', fp.propose(values(holder='', currency='MXN'), knowledge(renamed)))

    def test_statement_holder_conflicting_with_the_account_matches_nothing(self):
        result = fp.propose(values(holder='OTHER COMPANY', institution=''), knowledge(account(*MONTHS)))
        self.assertNotIn('institution', result)
        self.assertEqual(result['currency']['basis'], 'case_default')

    def test_bank_from_account_number_and_holder(self):
        institution = fp.propose(values(institution='', currency='MXN'), knowledge(account(*MONTHS)))['institution']
        self.assertEqual((institution['value'], institution['confirmed']), ('BANCO SANTANDER', True))

    def test_masked_number_gets_the_full_number_of_the_one_matching_account(self):
        result = fp.propose(values(account_number='****5678', currency='MXN'), knowledge(account(*MONTHS)))
        self.assertEqual((result['account_number']['value'], result['account_number']['confirmed']), ('65-1234567-8', True))

    def test_two_accounts_with_the_same_last_digits_are_ambiguous_even_if_a_holder_differs(self):
        # Truth-set case: the paired account shares the last digits; the holder must not pick one.
        other = account(*[saved(holder='OLD NAME SA DE CV', account='66-1234567-8') for _ in range(3)],
                        number='66-1234567-8', key='a2')
        result = fp.propose(values(account_number='****5678', currency='MXN'), knowledge(account(*MONTHS), other))
        self.assertNotIn('account_number', result)

    def test_masked_known_accounts_propose_no_full_number(self):
        masked = account(*[saved(account='****5678') for _ in range(3)], number='****5678')
        self.assertNotIn('account_number', fp.propose(values(account_number='XXXX5678', currency='MXN'), knowledge(masked)))

    def test_institution_names_compare_on_their_core_words(self):
        self.assertTrue(fp.same_institution('BANCO SANTANDER MEXICO', 'Santander'))
        self.assertTrue(fp.same_institution('SYNCHRONY BANK CARD', 'Synchrony Bank'))
        self.assertFalse(fp.same_institution('BBVA Mexico', 'Santander'))
        self.assertTrue(fp.same_holder('EXAMPLE LEASING SA DE C', 'EXAMPLE LEASING SA DE CV'))
        self.assertFalse(fp.same_holder('JANE ROE', 'JANE DOE'))


class SwitchAndQueueTests(TestCase):
    def test_switches(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_CURRENCY_PROPOSALS': '0'}):
            self.assertNotIn('currency', fp.propose(values(), knowledge(account(*MONTHS))))
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_DETAIL_PROPOSALS': '0'}):
            self.assertEqual(set(fp.propose(values(holder=''), knowledge(account(*MONTHS)))), {'currency'})

    def test_resolves_all_only_with_confirmed_proposals_for_every_reason(self):
        confirmed = dict(currency=dict(value='MXN', confirmed=True, label='x'))
        self.assertTrue(fp.resolves_all({'currency'}, confirmed))
        self.assertFalse(fp.resolves_all({'currency', 'balance'}, confirmed))
        self.assertFalse(fp.resolves_all({'currency'}, dict(currency=dict(value='MXN', confirmed=False, label='x'))))
        self.assertFalse(fp.resolves_all(set(), confirmed))

    def test_queue_sentences_show_the_value_and_its_source(self):
        proposal = dict(value='USD', confirmed=False, label="the case's usual currency (175 of 175 saved statements)")
        self.assertEqual(fp.sentence('currency', dict(currency=proposal)),
                         "Currency not printed: USD proposed (the case's usual currency (175 of 175 saved statements)). Confirm it")
        self.assertEqual(fp.sentence('holder', dict(holder=dict(value='ACME', confirmed=True, label='same account'))),
                         'Account holder filled: ACME (same account)')
        self.assertIsNone(fp.sentence('balance', dict(currency=proposal)))

    def test_queue_moves_a_statement_whose_every_problem_is_filled(self):
        from types import SimpleNamespace
        from services.financial.review_queue import _proposals, status_line
        summary = dict(problems=[dict(message='Choose the currency printed on these statements.', row_id=None)],
                       problem_count=1, can_import=False, currency='', institution='BANCO SANTANDER MEXICO',
                       holder='ACME SA DE CV', account='65-1234567-8', period_start='2021-06-01', period_end='2021-06-30')
        detail = dict(reason='currency', sentence='Currency not printed: choose one')
        proposals, resolved = _proposals(summary, knowledge(account(*MONTHS)), detail)
        self.assertTrue(resolved)
        self.assertEqual(detail['sentence'], "Currency filled: MXN (same account's 5 saved statements, all MXN)")
        summary['problems'].append(dict(kind='reading', message='Check this row.', row_id='1:0:1', page=1))
        self.assertFalse(_proposals(summary, knowledge(account(*MONTHS)), dict(detail))[1])
        counts = dict(imported=1, saving=0, waiting=2, filled=3, ready=0, copies=0, unreadable=0, rechecking=0,
                      left_unimported=0, assigned=0, unexplained=0, unreadable_files=0)
        self.assertIn('Details filled automatically 3', status_line(counts))
