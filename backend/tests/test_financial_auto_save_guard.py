"""What the System must prove before it saves a balanced statement on its own (auto_save_guard).

Measured shapes from BNB2 (fin-queue3, 2026-10-25): Monex's euro section saved
in pesos; a Kapital holder read from the address block; BBVA euro statements
saved under 0410274607 instead of 0110274607; a currency assumed as the case's
usual one.
"""
from datetime import date
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from postgres.models.financial_import_batches import FinancialImportBatchItem as Item, FinancialImportOperation as Operation
from services.financial import auto_save_guard as guard
from services.financial import queue_save
from services.financial.review_queue import classify, describe
from tests.test_financial_review_queue import QueueReadTests


def cells(*texts):
    return dict(cells=[dict(expected_text=t) for t in texts])


# Monex 2836625 May 2025, pages 6-8 of the euro section (065542a9): its heading, then a glossary naming every currency.
MONEX_EURO = [dict(page_number=6, table_index=0, rows=[cells('CUENTA VISTA'), cells('RESUMEN CUENTA'),
                                                       cells('euro', 'al 31 Mayo 2025'), cells('EN PESOS $6,591,688.03')]),
              dict(page_number=7, table_index=0, rows=[cells('MOVIMIENTOS DE MAYO EN EURO')]),
              dict(page_number=8, table_index=0, rows=[cells('PESO MEXICANO'), cells('DOLAR AMERICANO SOBRE CUENTAS EN E.U.A.'),
                                                       cells('EURO')])]
# Monex Dec 2025 pesos statement: its summary page and every section's page (several currencies: settles nothing).
MONEX_ALL = [dict(page_number=2, table_index=0, rows=[cells('CUENTA', 'RESUMEN CUENTA'),
                                                      cells('RESUMEN DIVISAS', 'PESO MEXICANO', 'AL 31 DICIEMBRE 2025')]),
             dict(page_number=3, table_index=0, rows=[cells('RESUMEN CUENTA'), cells('DOLAR AMERICANO', 'AL 31 DICIEMBRE 2025')]),
             dict(page_number=4, table_index=0, rows=[cells('RESUMEN CUENTA'), cells('EURO', 'AL 31 DICIEMBRE 2025')])]


def period(account, start, end, opening, closing, currency='EUR', bank='BBVA MEXICO', doc=''):
    return guard.SavedPeriod(account, bank, currency, date.fromisoformat(start), date.fromisoformat(end), opening, closing,
                             doc or str(uuid4()))


def summary(**values):
    base = dict(currency='EUR', holder='ARRENDO SERV SA DE CV', account='0110274607', institution='BBVA MEXICO',
                period_start='2025-07-01', period_end='2025-07-31',
                admission=dict(calculation=dict(opening_minor=235837, printed_closing_minor=240000)))
    opening = values.pop('opening', None)
    closing = values.pop('closing', None)
    base.update(values)
    if opening is not None or closing is not None:
        base['admission'] = dict(calculation=dict(opening_minor=opening, printed_closing_minor=closing))
    return base


class SectionCurrencyTests(TestCase):
    def test_the_section_heading_names_its_currency_and_a_glossary_does_not(self):
        self.assertEqual(guard.section_currencies(MONEX_EURO), {'EUR': 6})
        self.assertEqual(guard.section_currencies(MONEX_ALL), {'MXN': 2, 'USD': 3, 'EUR': 4})

    def test_a_euro_section_saved_in_pesos_is_held(self):
        held = guard.hold(summary(currency='MXN', section_currencies=guard.section_currencies(MONEX_EURO)), ledger=[])
        self.assertEqual(held[0], 'currency')
        self.assertIn('EUR (page 6)', held[1])
        self.assertIsNone(guard.hold(summary(currency='EUR', section_currencies={'EUR': 6}), ledger=[]))

    def test_pages_holding_several_sections_settle_nothing(self):
        self.assertIsNone(guard.hold(summary(currency='MXN', section_currencies={'MXN': 2, 'USD': 3, 'EUR': 4}), ledger=[]))

    def test_the_cases_usual_currency_saves_only_with_the_file_name_and_the_page(self):
        basis = "Currency MXN: currency assumed: case's usual (not printed)"
        held = guard.hold(summary(currency='MXN'), ledger=[], currency_basis=basis, filename='07 ARRENDO SANTANDER JUL 2022.pdf')
        self.assertEqual(held[0], 'currency')
        self.assertIsNotNone(guard.hold(summary(currency='MXN'), ledger=[], currency_basis=basis,
                                        filename='07 ARRENDO SANTANDER MXN JUL 2022.pdf'))
        self.assertIsNone(guard.hold(summary(currency='MXN'), ledger=[], currency_basis=basis,
                                     filename='07 ARRENDO SANTANDER MXN JUL 2022.pdf', named_currencies=['MXN']))
        self.assertIsNone(guard.hold(summary(currency='MXN'), ledger=[],
                                     currency_basis="Currency MXN: same account's 6 saved statements, all MXN"))


class HolderTests(TestCase):
    def test_an_address_line_is_not_a_holder(self):
        self.assertTrue(guard.holder_is_address('LOMAS DE CHAPULTEPEC III SECCION, MIGUEL HIDALGO'))
        self.assertTrue(guard.holder_is_address('AV. PASEO DE LA REFORMA 2620 PISO 7'))
        self.assertTrue(guard.holder_is_address('COL. POLANCO C.P. 11560'))
        for name in ('INGENIERIA APLICADA R2 SA DE CV', 'ARRENDO SERV SA DE CV', 'MONETA PATRIMONIAL SA DE CV',
                     'ECOTERRA AVANCE SAPI', 'COLINA INVERSIONES SA', 'SERVICIOS INTEGRALES DEL NORTE'):
            self.assertFalse(guard.holder_is_address(name), name)
        held = guard.hold(summary(holder='LOMAS DE CHAPULTEPEC III SECCION, MIGUEL HIDALGO'), ledger=[])
        self.assertEqual(held[0], 'holder')


class ChainTests(TestCase):
    ledger = [period('0110274607', '2025-06-01', '2025-06-30', 100, 235837),
              period('0110274607', '2025-08-01', '2025-08-31', 240000, 250000)]

    def test_a_statement_that_continues_its_neighbours_saves(self):
        self.assertIsNone(guard.hold(summary(opening=235837, closing=240000), ledger=self.ledger))

    def test_an_opening_that_does_not_continue_the_previous_closing_is_held(self):
        held = guard.hold(summary(opening=230837, closing=240000), ledger=self.ledger)
        self.assertEqual(held[0], 'balance')
        self.assertIn('2,358.37', held[1])

    def test_a_closing_that_does_not_carry_into_the_next_statement_is_held(self):
        self.assertEqual(guard.hold(summary(opening=235837, closing=241000), ledger=self.ledger)[0], 'balance')

    def test_the_opposite_sign_leaves_the_sign_unproven(self):
        ledger = [period('5579', '2025-06-01', '2025-06-30', -100, -5000, currency='MXN', bank='BANCO CARD')]
        held = guard.hold(summary(account='5579', currency='MXN', institution='BANCO CARD', opening=5000, closing=7000),
                          ledger=ledger)
        self.assertEqual(held[0], 'sign')

    def test_other_accounts_currencies_and_distant_months_are_not_neighbours(self):
        ledger = [period('0110274607', '2025-06-01', '2025-06-30', 0, 1, currency='USD'),
                  period('9999999999', '2025-06-01', '2025-06-30', 0, 1),
                  period('0110274607', '2025-04-01', '2025-04-30', 0, 1)]
        self.assertIsNone(guard.hold(summary(opening=235837, closing=240000), ledger=ledger))


class MisreadAccountTests(TestCase):
    # BBVA EUR: 0110274607 saved every month to Jun 2025, then three months under 0410274607 (OCR 1 -> 4).
    right = [period('0110274607', f'2025-0{m}-01', f'2025-0{m}-28', m * 10, m * 10 + 10) for m in range(1, 7)]
    wrong = [period('0410274607', '2025-07-01', '2025-07-31', 70, 80)]

    def test_a_number_one_digit_off_whose_balances_continue_is_held(self):
        held = guard.hold(summary(account='0410274607', period_start='2025-08-01', period_end='2025-08-31',
                                  opening=80, closing=90), ledger=self.right + self.wrong)
        self.assertEqual(held[0], 'account')
        self.assertIn('0110274607', held[1])

    def test_the_established_number_is_not_held_for_the_odd_one(self):
        self.assertIsNone(guard.hold(summary(account='0110274607', period_start='2025-08-01', period_end='2025-08-31',
                                             opening=80, closing=90), ledger=self.right + self.wrong))

    def test_two_real_accounts_sharing_months_are_not_a_misreading(self):
        other = [period('0410274607', '2025-03-01', '2025-03-28', 30, 40)]
        self.assertIsNone(guard.misread_account(guard.statement_of(summary(
            account='0410274607', period_start='2025-07-01', period_end='2025-07-31', opening=70, closing=80)),
            self.right + other))


class QueueTests(QueueReadTests):
    """The real queue and automatic save: a held statement is not saved by the System and says why."""
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None
    SENTENCE = 'The account holder read, "COL. POLANCO", is an address line: check the holder printed on the page'

    def test_the_system_does_not_save_what_it_cannot_prove_and_the_queue_says_why(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(guard, 'hold', return_value=('holder', self.SENTENCE)):
            self.advance(batch)
            with self.f.SessionLocal() as db:
                record = db.query(Item).filter(Item.batch_id == batch).one()
                item_id = record.id
                self.assertEqual(record.status, 'ready')
                self.assertEqual(db.query(Operation).count(), 0)
                result = queue_save.save_statements(db, case_id=self.f.case.id, item_ids=[item_id],
                                                    actor=queue_save.SYSTEM_ACTOR, only_reconciled=True)
            self.assertEqual((result['queued'], [h['reason'] for h in result['held']]), (0, [self.SENTENCE]))
            queue = self.queue()
            self.assertEqual((queue['counts']['ready'], queue['counts']['waiting']), (0, 1), queue['counts'])
            entry = queue['items'][0]
            self.assertEqual((entry['issue_reason'], entry['issue'], entry['field']),
                             ('auto_save_check', self.SENTENCE, 'holder'))
            # A person's save is not the System's: it is not held by the guard.
            with self.f.SessionLocal() as db:
                mine = queue_save.save_statements(db, case_id=self.f.case.id, item_ids=[item_id], actor=self.f.actor)
            self.assertEqual(mine['queued'], 1)

    def test_the_switch_restores_the_earlier_automatic_save(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.object(guard, 'ENABLED', False), \
                patch.object(guard, 'hold', return_value=('holder', self.SENTENCE)), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.advance(batch)
            with self.f.SessionLocal() as db:
                self.assertEqual(db.query(Item).filter(Item.batch_id == batch).one().status, 'pending_import')

    def test_a_person_reviewed_statement_is_not_held(self):
        hold = NS(status='ready', summary=dict(can_import=True, problems=[], problem_count=0,
                                               auto_save_hold=dict(reason='holder', sentence=self.SENTENCE)))
        self.assertEqual(classify(hold), 'waiting')
        self.assertEqual(describe(hold.summary)['sentence'], self.SENTENCE)
        self.assertFalse(queue_save.fully_reconciled(NS(review_request=None, statement_key=''), hold, None))
        with patch.object(guard, 'hold', return_value=('holder', self.SENTENCE)):
            from services.financial.import_batches import _auto_save_hold
            reviewed = NS(review_request={'holder': 'X'}, statement_key='', file_id=None)
            self.assertIsNone(_auto_save_hold(None, None, reviewed, {}, None, {}))

    def test_an_imported_statement_a_ledger_check_finds_wrong_waits_with_its_reason(self):
        """fin-queue3 0b/L28: a saved statement whose holder is an address line no longer counts silently as
        imported; it waits for a person with the check's sentence. Nothing saved is changed."""
        from postgres.models.financial import FinancialAccount
        from services.financial import import_batches as service
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            state = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=state['ready_revision'],
                                 actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.queue()['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            from postgres.models.financial import FinancialStatementPeriod
            account = db.get(FinancialAccount, db.query(FinancialStatementPeriod).one().account_id)
            account.holder_name = 'LOMAS DE CHAPULTEPEC III SECCION, MIGUEL HIDALGO'
            db.commit()
            found = guard.saved_checks(db, self.f.case.id)
        self.assertEqual([reason for reason, _ in found.values()], ['holder'])
        queue = self.queue()
        self.assertEqual((queue['counts']['imported'], queue['counts']['waiting']), (0, 1), queue['counts'])
        entry = queue['items'][0]
        self.assertEqual((entry['issue_reason'], entry['field'], entry['status']), ('saved_check', 'holder', 'imported'))
        self.assertIn('is an address line', entry['issue'])
        with patch('services.financial.review_queue.SAVED_CHECKS', False):
            self.assertEqual(self.queue()['counts']['imported'], 1)


class SavedLedgerTests(TestCase):
    def test_a_bank_typed_two_ways_is_one_bank(self):
        """'BANCO MONEX' (one reading) and 'Monex' (another) were compared as two banks, so the Monex Nov/Dec
        2025 reprints saved twice were not seen as the same account (BNB2, fin-queue3)."""
        self.assertEqual(guard._bank('BANCO MONEX'), guard._bank('Monex'))
        self.assertEqual(guard._bank('BANCO SANTANDER MEXICO'), guard._bank('Santander'))
        self.assertEqual(guard._bank('BBVA MEXICO'), guard._bank('BBVA'))
        self.assertNotEqual(guard._bank('Banco Kapital'), guard._bank('Intercam Banco'))
        prior = period('2836625', '2025-10-01', '2025-10-31', 100, 200, currency='MXN', bank='BANCO MONEX')
        self.assertEqual(guard.chain_problem(guard.statement_of(summary(account='2836625', currency='MXN', institution='Monex',
            period_start='2025-11-01', period_end='2025-11-30', opening=300, closing=300)), [prior])[0], 'balance')

    def test_the_cases_usual_currency_is_proven_by_the_file_name_and_the_accounts_own_history(self):
        """BNB2 sample #52: Santander 65-50462403-4 Dec 2021, a scan whose 'MONEDA : MONEDA NACIONAL' line the text
        reading lost. The file name says MXN and every saved statement of the account is MXN: proven."""
        basis = guard.CASE_DEFAULT_LABEL
        statement = summary(currency='MXN', account='65-50462403-4', institution='BANCO SANTANDER MEXICO',
                            period_start='2021-12-01', period_end='2021-12-31', opening=None, closing=None)
        history = [period('65504624034', '2021-11-01', '2021-11-30', None, None, currency='MXN', bank='Santander')]
        name = '12 ARRENDO SANTANDER MXN DIC 2021.pdf'
        self.assertIsNone(guard.hold(statement, ledger=history, currency_basis=basis, filename=name))
        # One signal is not enough: no history, or a file name naming nothing, or history in another currency.
        self.assertEqual(guard.hold(statement, ledger=[], currency_basis=basis, filename=name)[0], 'currency')
        self.assertEqual(guard.hold(statement, ledger=history, currency_basis=basis, filename='12 ARRENDO DIC 2021.pdf')[0], 'currency')
        usd = [period('65504624034', '2021-11-01', '2021-11-30', None, None, currency='USD', bank='Santander')]
        self.assertEqual(guard.hold(statement, ledger=history + usd, currency_basis=basis, filename=name)[0], 'currency')


class SavedTwiceByTypeTests(TestCase):
    """One Navy Federal statement prints 'EveryDay Checking 3701' and 'Checking Line of Credit 3701': saved as a
    deposit account and a card, same last digits and dates. They are neither copies nor one balance chain."""

    def row(self, kind, start, end, opening, closing, doc, key):
        return (kind, '3701', 'Navy Federal Credit Union', 'G DORSEY', 'USD', date.fromisoformat(start),
                date.fromisoformat(end), opening, closing, doc, 'sha', key)

    def rows(self, loc_kind='credit_card'):
        return [self.row('checking', '2021-04-17', '2021-05-16', 25000000, 29061346, 'c1', 'k1'),
                self.row('checking', '2021-05-17', '2021-06-16', 29061346, 28000000, 'c2', 'k2'),
                self.row(loc_kind, '2021-04-17', '2021-05-16', 0, 0, 'l1', 'k3'),
                self.row(loc_kind, '2021-05-17', '2021-06-16', 0, 0, 'l2', 'k4')]

    def test_two_products_of_one_statement_are_not_copies_nor_one_chain(self):
        self.assertEqual(guard.ledger_checks(self.rows()), {})

    def test_the_same_type_saved_twice_is_still_a_copy(self):
        found = guard.ledger_checks(self.rows(loc_kind='checking'))
        self.assertIn('copy', {reason for reason, _ in found.values()})

    def test_switched_off_compares_without_the_type(self):
        with patch.object(guard, 'SAVED_TWICE_BY_TYPE', False):
            self.assertIn('copy', {reason for reason, _ in guard.ledger_checks(self.rows()).values()})


class CardLedgerSignTests(TestCase):
    """Credit One 1930: a card statement prints the amount owed (75.00); the ledger stores its saved neighbours'
    owed balances negative (-75.00). Compared as printed, every such statement was held as 'the opposite sign'."""

    ledger = [period('1930', '2020-10-04', '2020-10-15', 0, -7500, currency='USD', bank='CREDIT ONE BANK'),
              period('1930', '2020-11-16', '2020-12-15', -256, -37188, currency='USD', bank='CREDIT ONE BANK')]

    def card(self, opening, closing, convention='liability_owed'):
        return summary(account='1930', currency='USD', institution='CREDIT ONE BANK', period_start='2020-10-16',
                       period_end='2020-11-15', admission=dict(calculation=dict(
                           opening_minor=str(opening), printed_closing_minor=str(closing), balance_convention=convention)))

    def test_a_card_statement_that_continues_its_neighbours_in_the_ledger_convention_saves(self):
        self.assertIsNone(guard.hold(self.card(7500, 256), ledger=self.ledger))

    def test_a_real_break_or_sign_is_still_held(self):
        self.assertEqual(guard.hold(self.card(7600, 256), ledger=self.ledger)[0], 'balance')
        positive = [period('1930', '2020-10-04', '2020-10-15', 0, 7500, currency='USD', bank='CREDIT ONE BANK')]
        self.assertEqual(guard.hold(self.card(7500, 256), ledger=positive)[0], 'sign')

    def test_switched_off_compares_as_printed(self):
        with patch.object(guard, 'LEDGER_SIGN', False):
            self.assertEqual(guard.hold(self.card(7500, 256), ledger=self.ledger)[0], 'sign')
