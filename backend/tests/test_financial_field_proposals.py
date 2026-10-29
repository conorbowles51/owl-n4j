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


# The automatic fills switched off: the proposal rules as they were before them.
OLD = patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_CURRENCY': '0', 'LOUPE_FINANCIAL_AUTOFILL_IDENTITY': '0'})

MONTHS = [saved(start=f'2021-{m:02d}-01', end=f'2021-{m:02d}-28') for m in (1, 2, 3, 9, 10)]


class CurrencyTests(TestCase):
    def test_same_account_agreeing_statements_confirm_the_currency(self):
        result = fp.propose(values(), knowledge(account(*MONTHS)))
        currency = result['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'same_account', True))
        self.assertEqual(currency['label'], "same account's 5 saved statements, all MXN")

    def test_one_saved_statement_is_a_proposal_only(self):
        with OLD:
            currency = fp.propose(values(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['value'], currency['confirmed']), ('MXN', False))

    def test_account_number_alone_is_one_field(self):
        with OLD:
            currency = fp.propose(values(institution='', holder=''), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('same_account', False))

    def test_saved_statement_on_the_same_dates_blocks_confirmation(self):
        # Several currency sections can share one account number and one period.
        same = saved(start='2021-06-01', end='2021-06-30')
        currency = fp.propose(values(), knowledge(account(*MONTHS, same)))['currency']
        self.assertEqual((currency['value'], currency['confirmed'], currency['same_dates_saved']), ('MXN', False, True))

    def test_disagreeing_currencies_propose_no_case_default(self):
        # The account's own history holds several currencies: the case's usual one would contradict it.
        mixed = account(*MONTHS, saved(currency='USD', start='2021-11-01', end='2021-11-30'))
        self.assertNotIn('currency', fp.propose(values(), knowledge(mixed, default='USD', default_count=7, total=9)))

    def test_account_record_currency_must_agree_too(self):
        self.assertNotIn('currency', fp.propose(values(), knowledge(account(*MONTHS, currency='EUR'))))

    def test_unmatched_statement_still_gets_the_case_default(self):
        currency = fp.propose(values(account_number='99-9999999-9'), knowledge(account(*MONTHS), default='USD',
                                                                             default_count=7, total=9))['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('USD', 'case_default', False))
        self.assertEqual(currency['label'], "the case's usual currency (7 of 9 saved statements)")

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

    def test_renamed_account_proposes_no_holder_with_the_neighbours_switch_off(self):
        renamed = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'))
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_HOLDER_NEIGHBOURS': '0'}):
            self.assertNotIn('holder', fp.propose(values(holder='', currency='MXN'), knowledge(renamed)))

    def test_renamed_account_proposes_the_holder_its_nearest_statements_agree_on(self):
        # The holder changed once, after this period: the nearest saved statements on both sides print one holder.
        renamed = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'))
        holder = fp.propose(values(holder='', currency='MXN'), knowledge(renamed))['holder']
        self.assertEqual((holder['value'], holder['basis'], holder['confirmed']),
                         ('ACME SA DE CV', fp.NEAREST_HOLDER_BASIS, True))

    def test_renamed_account_proposes_no_holder_for_a_period_between_the_two_holders(self):
        renamed = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'))
        result = fp.propose(values(holder='', currency='MXN', period_start='2021-11-01', period_end='2021-11-30'),
                            knowledge(renamed))
        self.assertNotIn('holder', result)

    def test_holder_changing_twice_proposes_no_holder(self):
        twice = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'),
                        saved(start='2022-01-01', end='2022-01-31'))
        self.assertNotIn('holder', fp.propose(values(holder='', currency='MXN'), knowledge(twice)))

    def test_renamed_account_matched_on_a_masked_number_proposes_no_holder(self):
        # Six digits shown, so the number alone proves the account; only the masked-number guard refuses.
        renamed = account(*MONTHS, saved(holder='NEW NAME SA DE CV', start='2021-12-01', end='2021-12-31'))
        result = fp.propose(values(holder='', currency='MXN', account_number='****345678'), knowledge(renamed))
        self.assertNotIn('holder', result)

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


class AccountCurrencyTests(TestCase):
    """(b') A brokerage cash ledger printing no currency takes its account's one currency (Neil, 2026-10-24)."""

    def broker(self, **overrides):
        return values(brokerage_cash_ledger=True, **overrides)

    def test_one_saved_statement_establishes_the_account_currency(self):
        currency = fp.propose(self.broker(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'account_currency', True))
        self.assertTrue(currency['label'].startswith('account currency: '))

    def test_only_brokerage_cash_ledgers(self):
        with OLD:
            currency = fp.propose(values(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('same_account', False))

    def test_conflicting_account_currencies_stay_held(self):
        self.assertNotIn('currency', fp.propose(self.broker(), knowledge(account(MONTHS[0], saved(
            currency='USD', start='2021-02-01', end='2021-02-28')))))

    def test_no_saved_statement_of_the_account_stays_held(self):
        currency = fp.propose(self.broker(), knowledge(account(MONTHS[0], number='99-9999999-9')))['currency']
        self.assertFalse(currency['confirmed'])

    def test_identity_on_two_fields_and_no_saved_statement_on_the_same_dates(self):
        with OLD:
            alone = fp.propose(self.broker(institution='', holder=''), knowledge(account(MONTHS[0])))['currency']
        same = fp.propose(self.broker(period_start='2021-01-01', period_end='2021-01-31'),
                          knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((alone['confirmed'], same['confirmed']), (False, False))

    def test_a_currency_printed_in_the_holdings_is_not_replaced(self):
        printed = dict(value='USD', page_number=2, table_index=0, row_index=3, expected_text='USD')
        currency = fp.propose(self.broker(printed_currency=printed), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['value'], currency['confirmed']), ('USD', False))

    def test_switch(self):
        with patch.object(fp, 'ACCOUNT_CURRENCY', False), OLD:
            currency = fp.propose(self.broker(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('same_account', False))

    def test_summary_values_carry_the_brokerage_flag(self):
        self.assertTrue(fp.summary_values(dict(brokerage_cash_ledger=True))['brokerage_cash_ledger'])
        self.assertFalse(fp.summary_values({})['brokerage_cash_ledger'])

    def test_a_printed_currency_differing_from_the_account_is_a_conflict(self):
        known = knowledge(account(MONTHS[0]))
        self.assertEqual(fp.account_currency_conflict(self.broker(currency='USD'), known), 'MXN')
        self.assertEqual(fp.account_currency_conflict(self.broker(currency='MXN'), known), '')
        self.assertEqual(fp.account_currency_conflict(values(currency='USD'), known), '')
        with patch.object(fp, 'ACCOUNT_CURRENCY', False):
            self.assertEqual(fp.account_currency_conflict(self.broker(currency='USD'), known), '')


class AutofillCurrencyTests(TestCase):
    """CURRENCY (Neil, 2026-10-24): no printed currency takes the one matching account's agreed currency."""

    def test_one_saved_statement_fills_it(self):
        currency = fp.propose(values(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'account_currency', True))
        self.assertEqual(currency['account_key'], 'a1')

    def test_the_printed_account_number_alone_identifies_the_account(self):
        currency = fp.propose(values(institution='', holder=''), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['value'], currency['confirmed']), ('MXN', True))

    def test_held_when_the_saved_statements_disagree(self):
        mixed = account(MONTHS[0], saved(currency='USD', start='2021-02-01', end='2021-02-28'))
        self.assertFalse(fp.propose(values(institution='', holder=''), knowledge(mixed)).get('currency', {}).get('confirmed'))

    def test_held_when_the_statement_prints_another_currency(self):
        printed = dict(value='USD', page_number=2, table_index=0, row_index=1, expected_text='USD')
        currency = fp.propose(values(printed_currency=printed), knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['value'], currency['confirmed']), ('USD', False))

    def test_held_when_a_saved_statement_covers_the_same_dates(self):
        same = saved(start='2021-06-01', end='2021-06-30')
        self.assertFalse(fp.propose(values(institution='', holder=''), knowledge(account(MONTHS[0], same)))['currency']['confirmed'])

    def test_held_on_a_short_or_masked_number(self):
        for number in ('****5678', '45678'):
            short = account(*[saved(account=number)], number=number)
            currency = fp.propose(values(account_number=number, institution='', holder=''), knowledge(short))['currency']
            self.assertFalse(currency['confirmed'], number)

    def test_held_when_two_accounts_share_the_number(self):
        other = account(saved(institution='BBVA'), institution='BBVA', key='a2')
        currency = fp.propose(values(institution='', holder=''), knowledge(account(*MONTHS), other))['currency']
        self.assertFalse(currency['confirmed'])

    def test_a_printed_currency_is_never_replaced(self):
        self.assertNotIn('currency', fp.propose(values(currency='USD', institution=''), knowledge(account(MONTHS[0]))))

    def test_switch_off_is_the_old_rule(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_CURRENCY': '0'}):
            currency = fp.propose(values(), knowledge(account(MONTHS[0])))['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('same_account', False))


class AutofillIdentityTests(TestCase):
    """IDENTITY (Neil, 2026-10-24): a missing bank from the one account whose printed number the statement carries."""

    def test_bank_from_the_printed_number_alone(self):
        result = fp.propose(values(institution='', holder='', currency='MXN'), knowledge(account(*MONTHS)))
        self.assertEqual((result['institution']['value'], result['institution']['confirmed'], result['institution']['basis']),
                         ('BANCO SANTANDER', True, 'same_account_number'))

    def test_holder_keeps_its_bracketing_rule(self):
        # The truth set holds an account printed under a new name after its saved statements.
        holder = fp.propose(values(institution='', holder='', currency='MXN', period_start='2025-03-01',
                                   period_end='2025-03-31'), knowledge(account(*MONTHS)))['holder']
        self.assertFalse(holder['confirmed'])

    def test_held_when_the_saved_statements_disagree(self):
        mixed = account(*MONTHS, saved(institution='BBVA', start='2021-11-01', end='2021-11-30'))
        result = fp.propose(values(institution='', holder='', currency='MXN'), knowledge(mixed))
        self.assertNotIn('institution', result)

    def test_held_on_a_masked_number_with_few_digits(self):
        result = fp.propose(values(account_number='****5678', institution='', holder='', currency='MXN'),
                            knowledge(account(*MONTHS)))
        self.assertFalse(result['institution']['confirmed'])
        self.assertNotIn('account_number', {k for k, p in result.items() if p['confirmed']})

    def test_no_number_printed_nothing_is_invented(self):
        result = fp.propose(values(account_number='', institution='', holder='', currency='MXN'), knowledge(account(*MONTHS)))
        self.assertEqual(result, {})

    def test_a_printed_bank_is_never_replaced(self):
        self.assertNotIn('institution', fp.propose(values(holder='', currency='MXN'), knowledge(account(*MONTHS))))

    def test_switch_off_is_the_old_rule(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_IDENTITY': '0'}):
            result = fp.propose(values(institution='', holder='', currency='MXN'), knowledge(account(*MONTHS)))
        self.assertFalse(result['institution']['confirmed'])

    def test_the_fill_never_overwrites_a_persons_value(self):
        # Proposals are applied in fill_missing mode only: a value a person entered is not empty, so not proposed.
        self.assertNotIn('institution', fp.propose(values(institution='Typed by a person', holder='', currency='MXN'),
                                                   knowledge(account(*MONTHS))))


class AutomaticFillTests(TestCase):
    """REAPPLY: the no-click fill of a current reading applies a stricter subset of the confirmed proposals.

    Each limit is one the leave-one-out run on the saved statements and the truth set needed: a currency
    section of another currency sharing the account number (balance chain), a bank renamed or a holder changed
    outside the saved span (bracketing), another account sharing a masked number's visible digits (never an
    account number), and the case's usual currency (never).
    """

    def ledger(self, *, currency='MXN', institution='BANCO SANTANDER', holder='ACME SA DE CV'):
        from dataclasses import replace
        march = replace(saved(currency=currency, start='2021-03-01', end='2021-03-31', institution=institution,
                              holder=holder), opening_minor=500, closing_minor=1000)
        september = replace(saved(currency=currency, start='2021-09-01', end='2021-09-30', institution=institution,
                                  holder=holder), opening_minor=3000, closing_minor=3500)
        return knowledge(account(march, september, currency=currency))

    def fills(self, known, **overrides):
        statement = values(**{**dict(opening_minor=1000, closing_minor=2000), **overrides})
        return fp.automatic_fills(statement, fp.propose(statement, known), known)

    def test_currency_when_the_balances_continue_the_account_ledger(self):
        currency = self.fills(self.ledger())['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'account_ledger', True))
        # The closing side alone is enough (its opening unread).
        self.assertIn('currency', self.fills(self.ledger(), opening_minor=None, closing_minor=3000))

    def test_no_currency_when_the_balances_do_not_chain(self):
        self.assertNotIn('currency', self.fills(self.ledger(), opening_minor=999, closing_minor=2999))
        self.assertNotIn('currency', self.fills(self.ledger(), opening_minor=None, closing_minor=None))

    def test_a_zero_balance_proves_nothing(self):
        from dataclasses import replace
        known = self.ledger()
        known.accounts[0].statements[0] = replace(known.accounts[0].statements[0], closing_minor=0)
        self.assertNotIn('currency', self.fills(known, opening_minor=0, closing_minor=2999))

    def test_a_mixed_currency_account_stays_held(self):
        from dataclasses import replace
        known = self.ledger()
        known.accounts[0].statements.append(replace(known.accounts[0].statements[1], currency='USD',
                                                    period_start='2021-11-01', period_end='2021-11-30'))
        self.assertNotIn('currency', self.fills(known))

    def test_never_the_case_usual_currency_nor_a_printed_one(self):
        known = knowledge(default='MXN')
        self.assertEqual(fp.propose(values(), known)['currency']['basis'], 'case_default')
        self.assertEqual(self.fills(known), {})
        printed = dict(value='USD', page_number=2, table_index=0, row_index=1, expected_text='USD')
        self.assertNotIn('currency', self.fills(self.ledger(), printed_currency=printed))
        self.assertEqual(self.fills(self.ledger(), currency='MXN', institution='', holder='').get('currency'), None)

    def test_a_saved_statement_on_the_same_dates_stays_held(self):
        from dataclasses import replace
        known = self.ledger()
        known.accounts[0].statements.append(replace(known.accounts[0].statements[0], period_start='2021-06-01',
                                                    period_end='2021-06-30', opening_minor=7, closing_minor=8))
        self.assertNotIn('currency', self.fills(known))

    def test_bank_and_holder_only_inside_the_saved_span(self):
        bank = self.fills(self.ledger(), currency='MXN', institution='')
        holder = self.fills(self.ledger(), currency='MXN', holder='')
        self.assertEqual((sorted(bank), sorted(holder)), (['institution'], ['holder']))
        self.assertEqual(bank['institution']['basis'], 'same_account_bracketed')
        later = dict(period_start='2022-01-01', period_end='2022-01-31')
        self.assertTrue(fp.propose(values(currency='MXN', institution='', **later), self.ledger())['institution']['confirmed'])
        self.assertEqual(self.fills(self.ledger(), currency='MXN', institution='', **later), {})
        self.assertEqual(self.fills(self.ledger(), currency='MXN', holder='', **later), {})

    def test_never_an_account_number(self):
        known = self.ledger()
        result = fp.propose(values(account_number='****345678', currency='MXN'), known)
        self.assertTrue(result['account_number']['confirmed'])
        self.assertNotIn('account_number', fp.automatic_fills(values(account_number='****345678', currency='MXN'),
                                                              result, known))

    def test_an_ambiguous_account_fills_nothing(self):
        known = self.ledger()
        known.accounts.append(account(saved(institution='BBVA'), institution='BBVA', key='a2'))
        statement = values(institution='', holder='', opening_minor=1000)
        self.assertEqual(fp.automatic_fills(statement, fp.propose(statement, known), known), {})

    def test_switch_off_fills_nothing(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_REAPPLY': '0'}):
            self.assertFalse(fp.reapply_enabled())
            self.assertEqual(self.fills(self.ledger()), {})
        self.assertTrue(fp.reapply_enabled())

    def test_summary_values_carry_the_printed_balances(self):
        summary = dict(checks=[dict(kind='closing_balance', opening_minor='1000', printed_minor='2000')])
        self.assertEqual((fp.summary_values(summary)['opening_minor'], fp.summary_values(summary)['closing_minor']),
                         (1000, 2000))
        self.assertEqual(fp.summary_values({})['opening_minor'], None)


class CaseCurrencyTests(TestCase):
    """LOUPE_FINANCIAL_AUTOFILL_CASE_CURRENCY: the case's usual currency when no currency is printed anywhere."""

    def setUp(self):
        self.case = knowledge(account(*MONTHS), default='MXN', default_count=714, total=1202)
        self.unmatched = values(account_number='', institution='', holder='', currency_marks=[])

    def test_nothing_printed_and_no_account_assumes_the_case_currency(self):
        currency = fp.propose(self.unmatched, self.case)['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']),
                         ('MXN', 'case_default_assumed', True))
        self.assertEqual(currency['label'], "currency assumed: case's usual (not printed)")
        fills = fp.automatic_fills(self.unmatched, {'currency': currency}, self.case)
        self.assertEqual(fills['currency']['basis'], 'case_default_assumed')
        self.assertTrue(fp.resolves_all({'currency'}, fills))

    def test_a_bare_dollar_sign_allows_the_case_currency(self):
        marks = [['AUD', 'BBD', 'BMD', 'BSD', 'CAD', 'FJD', 'HKD', 'JMD', 'MXN', 'NZD', 'SGD', 'TTD', 'USD', 'XCD']]
        self.assertTrue(fp.case_currency_assumable(dict(self.unmatched, currency_marks=marks), self.case))

    def test_another_currency_printed_anywhere_refuses(self):
        # A page naming another currency gets no case default (and two named currencies, no 'only printed').
        self.assertNotIn('currency', fp.propose(dict(self.unmatched, currency_marks=[['MXN'], ['USD']]), self.case))

    def test_the_case_currency_itself_printed_refuses(self):
        # 'No currency printed': a statement naming pesos is left for a person, even in a pesos case.
        self.assertFalse(fp.case_currency_assumable(dict(self.unmatched, currency_marks=[['MXN']]), self.case))
        self.assertFalse(fp.case_currency_assumable(dict(self.unmatched, currency_marks=[['?']]), self.case))

    def test_malformed_markers_refuse_without_raising(self):
        for marks in ([1], [None], ['MXN'], [['MXN', 1]], 'MXN'):
            self.assertFalse(fp.case_currency_assumable(dict(self.unmatched, currency_marks=marks), self.case), marks)

    def test_an_account_sharing_the_number_in_another_currency_refuses_whatever_its_holder(self):
        usd = account(saved(currency='USD', holder='JUAN PEREZ'), currency='USD', institution='BBVA')
        case = knowledge(usd, default='MXN', default_count=714, total=1202)
        stranger = values(holder='MARIA LOPEZ', institution='BANCO SANTANDER MEXICO', currency_marks=[])
        self.assertFalse(fp.case_currency_assumable(stranger, case))

    def test_a_reading_without_recorded_markers_refuses(self):
        currency = fp.propose(values(account_number='', institution='', holder=''), self.case)['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('case_default', False))

    def test_a_holdings_currency_refuses(self):
        printed = dict(value='MXN', page_number=2)
        self.assertFalse(fp.case_currency_assumable(dict(self.unmatched, printed_currency=printed), self.case))

    def test_a_matched_account_in_another_currency_refuses(self):
        mixed = account(*MONTHS, saved(currency='USD', start='2021-11-01', end='2021-11-30'))
        case = knowledge(mixed, default='MXN', default_count=714, total=1202)
        self.assertFalse(fp.propose(values(currency_marks=[]), case).get('currency', {}).get('confirmed'))
        record = knowledge(account(*MONTHS, currency='USD'), default='MXN', default_count=714, total=1202)
        self.assertFalse(fp.case_currency_assumable(values(currency_marks=[]), record))

    def test_a_matched_account_all_in_the_case_currency_is_filled(self):
        # One saved statement only: the account alone confirms nothing; the case's currency does.
        with OLD:
            case = knowledge(account(MONTHS[0]), default='MXN', default_count=714, total=1202)
            currency = fp.propose(values(currency_marks=[]), case)['currency']
        self.assertEqual((currency['basis'], currency['confirmed']), ('case_default_assumed', True))

    def test_no_clear_majority_refuses(self):
        for count, total in ((600, 1202), (15, 18)):
            case = knowledge(default='MXN', default_count=count, total=total)
            self.assertFalse(fp.case_currency_assumable(self.unmatched, case), (count, total))

    def test_switch_off_restores_the_one_click_proposal(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_CASE_CURRENCY': '0'}):
            currency = fp.propose(self.unmatched, self.case)['currency']
            self.assertEqual((currency['basis'], currency['confirmed']), ('case_default', False))
            self.assertEqual(fp.automatic_fills(self.unmatched, {'currency': dict(currency, confirmed=True,
                             basis='case_default_assumed')}, self.case), {})

    def test_summary_values_carries_the_markers_only_as_a_list(self):
        self.assertEqual(fp.summary_values({'currency_marks': [['MXN']]})['currency_marks'], [['MXN']])
        self.assertIsNone(fp.summary_values({'currency_marks': 'MXN'})['currency_marks'])
        self.assertIsNone(fp.summary_values({})['currency_marks'])


class CurrencyMarksTests(TestCase):
    def test_markers(self):
        from services.financial.statement_currency import currency_marks
        self.assertEqual(currency_marks([], 'IPC 62,769.18\nFX USD/MXN 18.57\nKPTLUSD HR AAA'), [])
        self.assertEqual(currency_marks([], 'COMPRA DOLARES'), [['USD']])
        self.assertEqual(currency_marks([], 'Moneda: Nacional'), [['MXN']])
        self.assertEqual(currency_marks([], 'EUR 1,234.56'), [['EUR']])
        self.assertIn('MXN', currency_marks([], '$1,234.56')[0])
        self.assertEqual(currency_marks([], 'SALDO €1.234,56 a la fecha'), [['EUR']])
        self.assertEqual(currency_marks([], 'pago US$ 1,234.56'), [['USD']])
        self.assertEqual(currency_marks([], 'USD/MES 10'), [['USD']])
        self.assertEqual(currency_marks([], 'MONEDA: QUETZALES'), [['?']])
        self.assertEqual(currency_marks([], 'CUENTA EN MONEDA NACIONAL'), [['MXN']])
        self.assertEqual(currency_marks([], 'R$ 10,00'), [['BRL']])
        self.assertEqual(currency_marks([{'page_number': 1, 'table_index': 0, 'rows': [{'cells': [{'expected_text': None}]}]}]), [])
        self.assertEqual(currency_marks([], 'REF 1,234.56'), [])


class AccountHistoryCurrencyTests(TestCase):
    """LOUPE_FINANCIAL_AUTOFILL_ACCOUNT_HISTORY: the account's established currency, printed among others."""

    def setUp(self):
        # BNB2 BBVA 0110280038: 60 USD statements and one saved as MXN, far from the held one.
        usd = [saved(currency='USD', start=f'{y}-{m:02d}-01', end=f'{y}-{m:02d}-28', institution='BBVA Mexico')
               for y in (2024, 2025) for m in range(1, 13) if (y, m) != (2025, 7)]
        usd[10] = replace_currency(usd[10], 'MXN')  # Nov 2024
        self.known = knowledge(account(*usd, number='0110280038', institution='BBVA Mexico', currency=''),
                               default='MXN', default_count=714, total=1202)
        self.held = values(institution='BBVA Mexico', account_number='0110280038', period_start='2025-07-01',
                           period_end='2025-07-31', currency_marks=[['MXN'], ['PEN'], ['USD']])

    def test_fills_the_established_currency_with_no_click(self):
        currency = fp.propose(self.held, self.known)['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('USD', 'account_history', True))
        self.assertIn('22 of this account', currency['label'])
        self.assertIn('MXN Nov 2024', currency['label'])
        self.assertEqual(fp.automatic_fills(self.held, {'currency': currency}, self.known)['currency']['value'], 'USD')
        self.assertEqual(fp.currency_why(self.held, self.known, currency), ('', []))

    def test_page_must_print_the_currency(self):
        self.assertFalse(fp.propose(dict(self.held, currency_marks=[['MXN']]), self.known).get('currency', {}).get('confirmed'))

    def test_a_neighbour_in_another_currency_refuses(self):
        neighbour = next(a for a in self.known.accounts[0].statements if a.period_start == '2025-06-01')
        self.known.accounts[0].statements.remove(neighbour)
        self.known.accounts[0].statements.append(replace_currency(neighbour, 'MXN'))
        self.assertIsNone(fp.account_history_currency(self.held, self.known))

    def test_below_ninety_percent_refuses(self):
        for s in self.known.accounts[0].statements[:3]:
            self.known.accounts[0].statements.append(replace_currency(s, 'MXN', shift='2023'))
        self.assertIsNone(fp.account_history_currency(self.held, self.known))

    def test_same_dates_saved_refuses(self):
        self.known.accounts[0].statements.append(saved(currency='USD', start='2025-07-01', end='2025-07-31'))
        self.assertIsNone(fp.account_history_currency(self.held, self.known))

    def test_masked_number_refuses(self):
        self.assertIsNone(fp.account_history_currency(dict(self.held, account_number='****0038'), self.known))

    def test_switch_off(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_ACCOUNT_HISTORY': '0'}):
            self.assertIsNone(fp.account_history_currency(self.held, self.known))
            self.assertNotIn('currency', fp.propose(self.held, self.known))

    def test_why_names_the_failed_check(self):
        headline, why = fp.currency_why(dict(self.held, currency_marks=[['MXN'], ['PEN']]), self.known)
        self.assertEqual(headline, 'Currency unclear: the pages mention MXN and PEN')
        self.assertTrue(any('the pages do not print USD anywhere' in w for w in why), why)


def replace_currency(statement, currency, shift=None):
    from dataclasses import replace
    if shift:
        return replace(statement, currency=currency, period_start=shift + statement.period_start[4:],
                       period_end=shift + statement.period_end[4:])
    return replace(statement, currency=currency)


class OneClickCurrencyTests(TestCase):
    def test_same_number_and_holder_at_the_previous_bank(self):
        # BNB2: Intercam Casa de Bolsa statements up to Jun 2025, then Kapital (same number, same holder).
        intercam = account(*[saved(start=f'2025-0{m}-01', end=f'2025-0{m}-28', institution='Intercam Casa de Bolsa',
                                   holder='MONETA PATRIMONIAL') for m in range(1, 7)],
                           number='00022008', institution='Intercam Casa de Bolsa')
        held = values(institution='Kapital Mexico Casa de Bolsa', holder='MONETA PATRIMONIAL', account_number='00022008',
                      period_start='2025-12-01', period_end='2025-12-31', currency_marks=[['UDI']])
        known = knowledge(intercam)
        currency = fp.propose(held, known)['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']),
                         ('MXN', 'same_number_previous_bank', False))
        self.assertIn('moved from Intercam Casa de Bolsa', currency['label'])
        headline, why = fp.currency_why(held, known, currency)
        self.assertEqual(headline, "Currency not printed as the statement's own: MXN proposed, confirm it")
        self.assertTrue(any('never assumes accounts at two banks' in w for w in why))
        self.assertTrue(any(w.startswith('UDI also appears') for w in why))
        self.assertTrue(why[0].startswith('Apart from UDI'))
        # A statement of the old bank dated after the new one's: not a takeover.
        later = values(**dict(held, period_start='2025-03-01', period_end='2025-03-31'))
        self.assertNotEqual(fp.propose(later, known).get('currency', {}).get('basis'), 'same_number_previous_bank')

    def test_file_name_with_page_and_account(self):
        monex = account(*[saved(currency=c, start=f'2021-0{m}-01', end=f'2021-0{m}-28', institution='Monex')
                          for m, c in zip(range(1, 9), ['MXN', 'USD', 'EUR', 'MXN', 'USD', 'MXN', 'EUR', 'MXN'])],
                        number='2836625', institution='Monex', currency='')
        held = values(institution='Monex', account_number='2836625', filename='05 ARRENDO MONEX MXN MAY 2025.pdf',
                      currency_marks=[['EUR'], ['MXN'], ['USD']])
        known = knowledge(monex)
        currency = fp.propose(held, known)['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'file_name', False))
        _, why = fp.currency_why(held, known, currency)
        self.assertTrue(any('its own section under one account number' in w for w in why), why)
        # A name the page does not print proposes nothing.
        self.assertNotIn('currency', fp.propose(dict(held, filename='GBP.pdf'), known))

    def test_only_currency_the_pages_mention(self):
        held = values(account_number='', institution='', holder='', currency_marks=[['MXN']])
        currency = fp.propose(held, knowledge(account(*MONTHS)))['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']), ('MXN', 'only_printed_currency', False))


class NotRecordedMarksTests(TestCase):
    def test_an_older_preparation_never_claims_the_page_lacks_a_currency(self):
        usd = [saved(currency='USD', start=f'2024-{m:02d}-01', end=f'2024-{m:02d}-28') for m in range(1, 13)]
        known = knowledge(account(*usd, currency=''))
        held = values(period_start='2025-01-01', period_end='2025-01-31')  # no currency_marks: prepared earlier
        self.assertIsNone(fp.account_history_currency(held, known))
        _, why = fp.currency_why(held, known)
        self.assertFalse(any('do not print' in w for w in why), why)
        self.assertTrue(any('prepared before' in w for w in why), why)


class FileAndPageCurrencyTests(TestCase):
    """LOUPE_FINANCIAL_AUTOFILL_FILE_AND_PAGE (fin-queue3 L4, 2026-10-26): a statement of no saved account whose file
    name gives one currency, the only real currency its pages print, takes it with no click."""
    held = values(institution='Kapital Mexico Casa de Bolsa', holder='EMPRESA DE PRUEBA', account_number='00099001',
                  period_start='2026-06-01', period_end='2026-06-30', filename='06 EMPRESA KAPITAL MXN JUN 26.pdf',
                  currency_marks=[['MXN'], ['UDI'], ['MXN', 'USD']])

    def test_the_file_name_and_the_pages_only_currency_fill_it(self):
        known = knowledge(account(*MONTHS))
        currency = fp.propose(self.held, known)['currency']
        self.assertEqual((currency['value'], currency['basis'], currency['confirmed']),
                         ('MXN', fp.FILE_AND_PAGE_BASIS, True))
        fills = fp.automatic_fills(self.held, {'currency': currency}, known)
        self.assertEqual(fills['currency']['value'], 'MXN')
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTOFILL_FILE_AND_PAGE': '0'}):
            self.assertFalse(fp.propose(self.held, known)['currency']['confirmed'])
            self.assertEqual(fp.automatic_fills(self.held, {'currency': currency}, known), {})

    def test_any_disagreeing_signal_leaves_it_a_question(self):
        known = knowledge(account(*MONTHS))
        refused = dict(
            other_name=dict(self.held, filename='06 EMPRESA KAPITAL USD JUN 26.pdf'),
            two_names=dict(self.held, filename='06 EMPRESA MXN USD.pdf'),
            no_name=dict(self.held, filename='06 EMPRESA KAPITAL JUN 26.pdf'),
            page_names_another=dict(self.held, currency_marks=[['MXN'], ['USD']]),
            marker_excludes_it=dict(self.held, currency_marks=[['MXN'], ['EUR', 'GBP']]),
            nothing_recorded=dict(self.held, currency_marks=None),
            printed_in_holdings=dict(self.held, printed_currency=dict(value='MXN', page_number=2)))
        for name, held in refused.items():
            currency = fp.propose(held, known).get('currency') or {}
            self.assertNotEqual(currency.get('basis'), fp.FILE_AND_PAGE_BASIS, name)
        # The same digits at another bank, saved in another currency.
        elsewhere = account(saved(currency='USD', account='00099001'), number='00099001', institution='Intercam',
                            currency='USD', key='a2')
        self.assertIsNone(fp.file_and_page_currency(self.held, knowledge(elsewhere)))
