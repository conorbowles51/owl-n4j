"""Account type set after import: re-signed balances, flagged investigator rows, confirmed flips."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select

from postgres.models.financial import AdjudicationEvent, FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial import account_type_change as service
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_details import CONVENTION_REVIEW, read_statement_details
import tests.test_financial_statement_import as statement_import_tests


class AccountTypeChangeTests(TestCase):
    def setUp(self):
        # Built from the statement import fixture (not collected again here).
        self.f = statement_import_tests.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        request = self.f.request()
        # The investigator adds a missed payment and a missed fee by hand. Under
        # the bank convention she entered the payment as money out and the fee
        # as money in, which is how a card reconciled "like a bank" looks.
        request['rows'] += [
            dict(id='manual:payment', manual_page=1, excluded=False, date='2023-12-29', description='PAYMENT - THANK YOU',
                 counterparty='', amount_minor='20000', direction='debit', balance_minor=None, reason='Missed on reading'),
            dict(id='manual:fee', manual_page=1, excluded=False, date='2023-12-30', description='LATE FEE',
                 counterparty='', amount_minor='20000', direction='credit', balance_minor=None, reason='Missed on reading')]
        # Seeded as already-saved history (the manual pair sits outside the
        # printed running-balance order, which today's review would ask for).
        self.receipt = self.f.confirm_legacy(request)
        with self.f.SessionLocal() as db:
            self.source_id = UUID(self.receipt['source_document_id'])
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == self.source_id))
            self.account_id = period.account_id
            self.balances = (period.opening_balance_minor, period.closing_balance_minor)
            account = db.get(FinancialAccount, self.account_id)
            account.account_type = None
            db.commit()

    def tearDown(self):
        self.f.tearDown()

    def state(self):
        with self.f.SessionLocal() as db:
            return service.account_type_state(db, case_id=self.f.case.id, account_id=self.account_id)

    def change(self, account_type, revision=None):
        with self.f.SessionLocal() as db:
            request = service.AccountTypeRequest(account_type=account_type, reason='Printed card statement',
                expected_revision=revision or self.state()['revision'])
            return service.save_account_type(db, case_id=self.f.case.id, account_id=self.account_id,
                request=request, actor=self.f.actor)

    def test_preview_writes_nothing_and_flags_the_investigator_rows(self):
        with self.f.SessionLocal() as db:
            preview = service.preview_account_type(db, case_id=self.f.case.id, account_id=self.account_id, account_type='credit_card')
        self.assertEqual(preview['changed_statements'], 1)
        statement = preview['statements'][0]
        self.assertEqual((statement['convention_before'], statement['convention_after']), ('asset_balance', 'liability_owed'))
        self.assertEqual(sorted(row['description'] for row in statement['flagged_rows']), ['LATE FEE', 'PAYMENT - THANK YOU'])
        self.assertEqual({row['proposed_direction'] for row in statement['flagged_rows'] if row['description'] == 'LATE FEE'}, {'debit'})
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == self.source_id))
            self.assertEqual((period.opening_balance_minor, period.closing_balance_minor), self.balances)
            self.assertIsNone(db.get(FinancialAccount, self.account_id).account_type)
            self.assertNotIn(CONVENTION_REVIEW, db.get(FinancialSourceDocument, self.source_id).metadata_)

    def test_change_re_signs_balances_keeps_sealed_reading_and_history_and_never_rereads(self):
        with self.f.SessionLocal() as db:
            before = dict(db.get(FinancialSourceDocument, self.source_id).metadata_)
            running = {t.id: t.running_balance_minor for t in db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == self.source_id))}
        with patch('services.financial.statement_import.read_statement_import', side_effect=AssertionError('no re-read')):
            result = self.change('credit_card')
        self.assertEqual(result['account_type'], 'credit_card')
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.source_id)
            metadata = document.metadata_
            # Sealed reading and import request are untouched.
            for key in ('statement_import_original', 'statement_import_request'):
                self.assertEqual(metadata[key], before[key])
                self.assertEqual(_digest(metadata[key]), metadata[key + '_sha256'])
            review = metadata[CONVENTION_REVIEW]
            self.assertEqual((review['previous_convention'], review['balance_convention']), ('asset_balance', 'liability_owed'))
            self.assertEqual(review['actor_name'], self.f.actor.name)
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == self.source_id))
            self.assertEqual((period.opening_balance_minor, period.closing_balance_minor),
                tuple(-value if value is not None else None for value in self.balances))
            for t in db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.source_id)):
                self.assertEqual(t.running_balance_minor, -running[t.id] if running[t.id] is not None else None)
            account = db.get(FinancialAccount, self.account_id)
            self.assertEqual(account.metadata_['account_type_history'][-1]['before'], '')
            self.assertEqual(account.metadata_['account_type_history'][-1]['after'], 'credit_card')
            view = read_statement_details(db, case_id=self.f.case.id, source_id=self.source_id)
            self.assertEqual(view['balance_convention'], 'liability_owed')
            # The printed balances read the same; only their ledger sign changed.
            self.assertEqual(view['balances']['closing']['amount_minor'], str(self.balances[1]))
        # The statement adds up as entered, so the two rows stay flagged, not flipped.
        flagged = result['statements'][0]['flagged_rows']
        self.assertEqual(len(flagged), 2)
        self.assertEqual({row['direction'] for row in flagged if row['description'] == 'PAYMENT - THANK YOU'}, {'debit'})

    def test_confirmed_flip_uses_the_correction_chain_and_cannot_be_applied_twice(self):
        state = self.change('credit_card')
        flagged = state['statements'][0]['flagged_rows']
        request = service.FlipRowsRequest(source_document_id=self.source_id,
            transaction_ids=[UUID(row['transaction_id']) for row in flagged], expected_revision=state['revision'])
        with self.f.SessionLocal() as db:
            after = service.flip_flagged_rows(db, case_id=self.f.case.id, account_id=self.account_id, request=request, actor=self.f.actor)
        self.assertEqual(after['flagged_rows'], 0)
        with self.f.SessionLocal() as db:
            for row in flagged:
                original = db.get(FinancialTransaction, UUID(row['transaction_id']))
                self.assertEqual(original.ledger_status, 'superseded')
                replacement = db.get(FinancialTransaction, original.superseded_by_id)
                self.assertEqual(replacement.direction, row['proposed_direction'])
                self.assertEqual(replacement.amount_minor, int(row['amount_minor']))
                self.assertIn('account type was corrected', db.scalar(select(AdjudicationEvent.reason)
                    .where(AdjudicationEvent.subject_id == original.id)))
        # The same request again refers to rows no longer flagged: refused.
        with self.f.SessionLocal() as db, self.assertRaises(PdfMappingError):
            service.flip_flagged_rows(db, case_id=self.f.case.id, account_id=self.account_id,
                request=request.model_copy(update={'expected_revision': after['revision']}), actor=self.f.actor)

    def _make_card_entries_only_add_up_flipped(self):
        """The fee was entered as 50.00 and the printed closing is the card's:
        it adds up only with both hand-entered rows reversed."""
        with self.f.SessionLocal() as db:
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.source_id,
                                                                      FinancialTransaction.ledger_status != 'superseded')))
            fee = next(row for row in rows if row.description == 'LATE FEE')
            fee.amount_minor = 5000
            manual = {'LATE FEE', 'PAYMENT - THANK YOU'}
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == self.source_id))
            total = -period.opening_balance_minor
            for row in rows:
                credit = (row.direction == 'credit') != (row.description in manual)
                total += row.amount_minor if credit else -row.amount_minor
            period.closing_balance_minor = -total
            db.commit()

    def test_rows_flip_with_the_type_change_when_the_statement_then_adds_up_exactly(self):
        self._make_card_entries_only_add_up_flipped()
        with self.f.SessionLocal() as db:
            preview = service.preview_account_type(db, case_id=self.f.case.id, account_id=self.account_id, account_type='credit_card')
        statement = preview['statements'][0]
        self.assertEqual((statement['reconciles'], statement['reconciles_with_flagged_flipped'], statement['auto_flip']),
                         (False, True, True))
        self.assertEqual(preview['auto_flip_rows'], 2)
        result = self.change('credit_card')
        self.assertEqual(result['auto_flipped_rows'], 2)
        self.assertEqual(result['flagged_rows'], 0)
        self.assertTrue(result['statements'][0]['reconciles'])
        with self.f.SessionLocal() as db:
            originals = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.source_id,
                FinancialTransaction.description.in_(['LATE FEE', 'PAYMENT - THANK YOU']), FinancialTransaction.ledger_status == 'superseded')))
            self.assertEqual(len(originals), 2)
            for original in originals:
                self.assertNotEqual(db.get(FinancialTransaction, original.superseded_by_id).direction, original.direction)
                self.assertIn('adds up exactly', db.scalar(select(AdjudicationEvent.reason)
                    .where(AdjudicationEvent.subject_id == original.id)))
        # Changing back is the reverse decision: the flipped rows are not flagged again.
        self.assertEqual(self.change('checking')['auto_flipped_rows'], 0)

    def test_only_currently_flagged_rows_can_be_flipped(self):
        state = self.change('credit_card')
        with self.f.SessionLocal() as db:
            machine = db.scalar(select(FinancialTransaction.id).where(FinancialTransaction.source_document_id == self.source_id,
                FinancialTransaction.description == 'Outgoing'))
        request = service.FlipRowsRequest(source_document_id=self.source_id, transaction_ids=[machine],
            expected_revision=state['revision'])
        with self.f.SessionLocal() as db, self.assertRaises(PdfMappingError):
            service.flip_flagged_rows(db, case_id=self.f.case.id, account_id=self.account_id, request=request, actor=self.f.actor)

    def test_stale_revision_changes_nothing(self):
        stale = self.state()['revision']
        self.change('credit_card')
        with self.assertRaises(PdfMappingError):
            self.change('checking', revision=stale)
        self.assertEqual(self.state()['account_type'], 'credit_card')

    def test_changing_back_restores_the_balances_and_keeps_both_decisions(self):
        self.change('credit_card')
        self.change('checking')
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == self.source_id))
            self.assertEqual((period.opening_balance_minor, period.closing_balance_minor), self.balances)
            review = db.get(FinancialSourceDocument, self.source_id).metadata_[CONVENTION_REVIEW]
            self.assertEqual(review['balance_convention'], 'asset_balance')
            self.assertEqual(len(review['history']), 1)
            self.assertEqual(len(db.get(FinancialAccount, self.account_id).metadata_['account_type_history']), 2)

    def test_card_wording_suggests_a_credit_card(self):
        from postgres.models.evidence import EvidenceDocumentText
        with self.f.SessionLocal() as db:
            text = db.get(EvidenceDocumentText, self.f.file.id)
            text.content = text.content + 'New Balance $1.00\nMinimum Payment Due $1.00\nPayment Due Date 01/01/2024\n'
            text.source_locations = [dict(kind='page', page_number=1, start_char=0, end_char=len(text.content))]
            db.commit()
            review = service.account_type_review(db, case_id=self.f.case.id)
        row = next(a for a in review['accounts'] if a['account_id'] == str(self.account_id))
        self.assertEqual(row['suggested_type'], 'credit_card')
        self.assertEqual(row['card_signals'], ['minimum payment due', 'new balance', 'payment due date'])
        self.assertEqual(self.state()['suggested_type'], 'credit_card')


class AccountTypeHelpersTests(TestCase):
    def test_identity_with_flagged_rows_flipped(self):
        rows = [SimpleNamespace(id=1, direction='debit', amount_minor=20800),
                SimpleNamespace(id=2, direction='credit', amount_minor=13538)]
        # Card convention: owed 6,391.38 -> 6,318.76 after a payment and charges.
        self.assertFalse(service._identity(-639138, -631876, rows))
        self.assertTrue(service._identity(-639138, -631876, rows, {1, 2}))
        self.assertTrue(service._identity(639138, 631876, rows))
        self.assertIsNone(service._identity(None, 1, rows))

    def test_full_card_numbers_and_bank_roots(self):
        self.assertEqual(service.full_card_number('4111 1111 1111 1111'), '4111111111111111')
        self.assertIsNone(service.full_card_number('4111 1111 1111 1112'))  # not a card number
        self.assertIsNone(service.full_card_number('XXXX XXXX XXXX 1111'))
        self.assertIsNone(service.full_card_number('123456789012345'))
        self.assertEqual(service.bank_root('Example Bank Card'), service.bank_root('EXAMPLE BANK'))
        self.assertNotEqual(service.bank_root('Example Bank'), service.bank_root('Other Bank'))


class SameCardMergeTests(TestCase):
    """Two accounts that are one printed card are offered for the reversible merge."""
    setUp = AccountTypeChangeTests.setUp
    tearDown = AccountTypeChangeTests.tearDown

    def _card_accounts(self, second_number='4111 1111 1111 1111'):
        with self.f.SessionLocal() as db:
            ids = []
            for bank, number in (('Example Bank Card', '4111 1111 1111 1111'), ('Example Bank', second_number)):
                account = FinancialAccount(id=uuid4(), case_id=self.f.case.id,
                    identity_key='institution_account\x1f' + bank.lower() + '\x1f' + number.replace(' ', ''),
                    institution_name=bank, identifier_as_printed=number, holder_name='Synthetic Holder', currency='USD',
                    metadata_=dict(display_label='Synthetic Holder · ' + number))
                db.add(account); ids.append(account.id)
            db.commit()
        return ids

    def test_same_printed_card_is_suggested_and_can_be_previewed_for_merge(self):
        from services.financial.account_consolidation import consolidation_state, preview_consolidation, ConsolidationRequest
        ids = self._card_accounts()
        with self.f.SessionLocal() as db:
            review = service.account_type_review(db, case_id=self.f.case.id)
            self.assertEqual([sorted(group['account_ids']) for group in review['same_card']], [sorted(map(str, ids))])
            state = consolidation_state(db, self.f.case.id)
            preview = preview_consolidation(db, case_id=self.f.case.id, request=ConsolidationRequest(request_id=uuid4(),
                expected_revision=state['revision'], account_ids=ids, retained_id=ids[0], reason='Same printed card'))
            self.assertEqual(len(preview['accounts']), 2)

    def test_different_numbers_are_not_suggested_and_different_banks_still_refuse(self):
        from services.financial.account_consolidation import consolidation_state, preview_consolidation, ConsolidationRequest
        from services.financial.account_parties import AccountPartyError
        ids = self._card_accounts(second_number='5555 5555 5555 4444')
        with self.f.SessionLocal() as db:
            self.assertEqual(service.account_type_review(db, case_id=self.f.case.id)['same_card'], [])
            state = consolidation_state(db, self.f.case.id)
            with self.assertRaises(AccountPartyError):
                preview_consolidation(db, case_id=self.f.case.id, request=ConsolidationRequest(request_id=uuid4(),
                    expected_revision=state['revision'], account_ids=ids, retained_id=ids[0], reason='Same printed card'))
