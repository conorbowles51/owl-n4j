"""An account's holder or bank corrected for all its statements, split statements re-joined, reversible."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest import TestCase
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial import account_details_correction as service
from services.financial.account_selection import holder_account_ids
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details
import tests.test_financial_statement_import as statement_import_tests

CORRECTED = 'Corrected Company SA'


class AccountDetailsCorrectionTests(TestCase):
    def setUp(self):
        # Two statements of one account, from the statement import fixture.
        self.f = statement_import_tests.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.first = UUID(self.f.confirm()['source_document_id'])
        f, original = self.f, self.f.file
        path = Path(f._directory) / 'statement-2024.pdf'
        path.write_bytes(b'%PDF-1.4\nSecond statement test only')
        second = f.evidence(hashlib.sha256(path.read_bytes()).hexdigest())
        second.stored_path = str(path)
        text = f.db.get(EvidenceDocumentText, original.id)
        content = text.content.replace('2023', '2024')
        f.db.add(EvidenceDocumentText(evidence_file_id=second.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=text.engine_job_id, source_locations=json.loads(json.dumps(text.source_locations).replace('2023', '2024'))))
        geometry = f.db.get(EvidenceTableGeometry, (original.id, 1))
        f.db.add(EvidenceTableGeometry(evidence_file_id=second.id, page_number=1, engine_job_id=geometry.engine_job_id,
            payload=json.loads(json.dumps(geometry.payload).replace('2023', '2024'))))
        f.db.commit()
        f.file = second
        self.second = UUID(f.confirm()['source_document_id'])
        f.file = original
        with f.SessionLocal() as db:
            self.account_id = db.scalar(select(FinancialStatementPeriod.account_id).where(
                FinancialStatementPeriod.source_document_id == self.first))
            self.assertEqual(db.scalar(select(FinancialStatementPeriod.account_id).where(
                FinancialStatementPeriod.source_document_id == self.second)), self.account_id)

    def tearDown(self):
        self.f.tearDown()

    def details(self, source_id):
        with self.f.SessionLocal() as db:
            return read_statement_details(db, case_id=self.f.case.id, source_id=source_id)

    def split_second(self, holder=CORRECTED):
        """The per-statement edit that split a statement off its account."""
        view = self.details(self.second)
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.second, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=holder,
                    account_number=view['details']['account_number'], institution=view['details']['institution']))
        return UUID(self.details(self.second)['account_id'])

    def state(self, account_id=None):
        with self.f.SessionLocal() as db:
            return service.account_details_state(db, case_id=self.f.case.id, account_id=account_id or self.account_id)

    def correct(self, actor=None, revision=None, reason='Page 1 prints the holder', **values):
        with self.f.SessionLocal() as db:
            return service.save_account_details(db, case_id=self.f.case.id, account_id=self.account_id, actor=actor or self.f.actor,
                request=service.AccountDetailsRequest(expected_revision=revision or self.state()['revision'], reason=reason, **values))

    def undo(self, correction_id, reason='Corrected the wrong account'):
        with self.f.SessionLocal() as db:
            return service.undo_account_details(db, case_id=self.f.case.id, account_id=self.account_id, actor=self.f.actor,
                request=service.UndoAccountDetailsRequest(expected_revision=self.state()['revision'], correction_id=correction_id, reason=reason))

    def accounts_of(self, *sources):
        with self.f.SessionLocal() as db:
            periods = {db.scalar(select(FinancialStatementPeriod.account_id).where(FinancialStatementPeriod.source_document_id == s)) for s in sources}
            rows = set(db.scalars(select(FinancialTransaction.account_id).where(FinancialTransaction.source_document_id.in_(sources))))
            return periods | rows

    def holder_filter(self, name):
        with self.f.SessionLocal() as db:
            ids = holder_account_ids(db, self.f.case.id, [name])
            return set(db.scalars(select(FinancialTransaction.source_document_id).where(FinancialTransaction.account_id.in_(ids))))

    def test_per_statement_edit_still_splits_and_the_account_correction_rejoins_it(self):
        split = self.split_second()
        self.assertNotEqual(split, self.account_id)
        self.assertEqual(self.holder_filter(CORRECTED), {self.second})
        result = self.correct(holder=CORRECTED.upper())
        self.assertEqual(result['holder'], CORRECTED.upper())
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        # Every statement records the correction in its own history; the split
        # statement keeps its own spelling and is back on the account.
        self.assertEqual(self.details(self.first)['details']['holder'], CORRECTED.upper())
        self.assertEqual(self.details(self.second)['details']['holder'], CORRECTED)
        correction = result['correction']
        self.assertEqual([s['source_document_id'] for s in correction['statements']], [str(self.first)])
        self.assertEqual([(s['source_document_id'], s['from_account_id']) for s in correction['rejoined']], [(str(self.second), str(split))])
        self.assertEqual(correction['before']['holder'], 'Test Company')
        self.assertEqual(correction['reason'], 'Page 1 prints the holder')
        with self.f.SessionLocal() as db:
            history = db.get(FinancialSourceDocument, self.first).metadata_['statement_details_history']
            self.assertEqual(history[-1]['before']['details']['holder'], 'Test Company')
            self.assertEqual(db.get(FinancialAccount, split).metadata_['rejoined_into'][0]['account_id'], str(self.account_id))
            self.assertFalse(db.get(FinancialAccount, self.account_id).identity_key.startswith('unidentified'))
        # The ledger holder filter follows the account record at once.
        self.assertEqual(self.holder_filter(CORRECTED), {self.first, self.second})
        self.assertEqual(self.holder_filter('Test Company'), set())
        # A later edit of one statement now agrees with its account.
        view = self.details(self.first)
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.first, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=CORRECTED,
                    account_number=view['details']['account_number'], institution=view['details']['institution']))
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})

    def test_a_split_with_another_holder_stays_until_its_own_holder_is_corrected(self):
        # The split statement's holder is not the corrected one ('SA' added by
        # hand): the account correction leaves it; correcting that statement's
        # holder to the printed value brings it back to the corrected account.
        split = self.split_second(holder=CORRECTED + ' DE CV')
        result = self.correct(holder=CORRECTED)
        self.assertEqual(result['correction']['rejoined'], [])
        self.assertEqual(self.accounts_of(self.second), {split})
        view = self.details(self.second)
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.second, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=CORRECTED,
                    account_number=view['details']['account_number'], institution=view['details']['institution']))
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        self.assertEqual(self.holder_filter(CORRECTED), {self.first, self.second})

    def test_preview_lists_statements_and_splits_and_writes_nothing(self):
        split = self.split_second()
        before = self.state()
        with self.f.SessionLocal() as db:
            preview = service.preview_account_details(db, case_id=self.f.case.id, account_id=self.account_id,
                request=service.AccountDetailsRequest(expected_revision=before['revision'], reason='x', holder=CORRECTED))
        self.assertEqual(preview['after']['holder'], CORRECTED)
        self.assertEqual([s['source_document_id'] for s in preview['statements']], [str(self.first)])
        self.assertEqual([r['account_id'] for r in preview['rejoin']], [str(split)])
        self.assertEqual(self.state(), before)
        # A split differing in anything else (here the holder) is not offered.
        with self.f.SessionLocal() as db:
            preview = service.preview_account_details(db, case_id=self.f.case.id, account_id=self.account_id,
                request=service.AccountDetailsRequest(expected_revision=before['revision'], reason='x', holder='Someone Else SA'))
        self.assertEqual(preview['rejoin'], [])

    def test_only_a_person_with_a_reason_on_the_current_revision(self):
        before = self.state()
        system = Actor(name='System', email='auto-save@system.local')
        for kwargs, status in ((dict(actor=system), 403), (dict(reason='  '), 422), (dict(revision='0' * 64), 409)):
            with self.assertRaises(PdfMappingError) as raised:
                self.correct(holder=CORRECTED, **kwargs)
            self.assertEqual(raised.exception.status_code, status)
        with self.assertRaises(PdfMappingError):
            self.correct(holder='Test Company')
        with self.assertRaises(PdfMappingError):
            self.correct(holder='   ')
        self.assertEqual(self.state(), before)

    def test_undo_restores_previous_values_and_splits_back(self):
        split = self.split_second()
        correction = self.correct(holder=CORRECTED)['correction']
        restored = self.undo(correction['id'])
        self.assertEqual(restored['holder'], 'Test Company')
        self.assertEqual(self.details(self.first)['details']['holder'], 'Test Company')
        self.assertEqual(self.accounts_of(self.first), {self.account_id})
        self.assertEqual(self.accounts_of(self.second), {split})
        self.assertEqual(self.details(self.second)['details']['holder'], CORRECTED)
        history = restored['history']
        self.assertEqual([item['kind'] for item in history], ['correction', 'undo'])
        self.assertEqual(history[0]['undone_by'], history[1]['id'])
        with self.assertRaises(PdfMappingError):
            self.undo(correction['id'])
        self.assertEqual(self.holder_filter('Test Company'), {self.first})

    def test_a_person_confirms_a_correction_claude_made_and_it_stays_claudes(self):
        from services.financial.model_work import model_actor
        claude = model_actor(for_name=self.f.actor.name, for_email=self.f.actor.email, for_user_id=self.f.actor.user_id,
                             citation=dict(page=1))
        correction = self.correct(actor=claude, holder=CORRECTED)['correction']
        self.assertEqual(correction['origin']['kind'], 'model')

        def confirm(actor, correction_id=correction['id'], basis='Page 1 prints the holder above the address.'):
            with self.f.SessionLocal() as db:
                return service.confirm_account_details(db, case_id=self.f.case.id, account_id=self.account_id,
                    actor=actor, request=service.ConfirmAccountDetailsRequest(
                        expected_revision=self.state()['revision'], correction_id=correction_id, basis=basis))
        before = self.state()
        for actor, basis, status in ((claude, 'x', 403), (self.f.actor, ' ', 422)):
            with self.assertRaises(PdfMappingError) as raised:
                confirm(actor, basis=basis)
            self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(self.state(), before)
        result = confirm(self.f.actor)
        entry = result['history'][-1]
        self.assertEqual((entry['actor_name'], entry['confirmed']['by'], entry['after']['holder'], result['holder']),
                         (claude.name, self.f.actor.name, CORRECTED, CORRECTED))
        with self.assertRaises(PdfMappingError) as raised:
            confirm(self.f.actor)
        self.assertEqual(raised.exception.status_code, 409)

    def claude_correction(self):
        from services.financial.model_work import model_actor
        claude = model_actor(for_name=self.f.actor.name, for_email=self.f.actor.email, for_user_id=self.f.actor.user_id,
                             citation=dict(page=1))
        return self.correct(actor=claude, holder=CORRECTED)['correction']

    def relay(self, correction_id, apply=True, note='Entered by Claude on the person\'s instruction of 2026-10-30',
              basis='Approved by message; page 1 prints the holder.', entered_by='Claude', **person):
        from services.financial.relayed_confirmation import enter_relayed_confirmation
        who = dict(dict(user_id=self.f.actor.user_id, name=self.f.actor.name, email=self.f.actor.email), **person)
        with self.f.SessionLocal() as db:
            return enter_relayed_confirmation(db, case_id=self.f.case.id, account_id=self.account_id,
                correction_id=correction_id, basis=basis, relay_note=note, apply=apply, entered_by=entered_by, **who)

    def test_a_relayed_confirmation_is_the_persons_and_says_who_entered_it(self):
        correction = self.claude_correction()
        before = self.state()
        # A dry run goes through the same path and keeps nothing.
        dry = self.relay(correction['id'], apply=False)
        self.assertEqual(dry['confirmed']['relayed']['by'], 'Claude')
        self.assertEqual(self.state(), before)
        # Refused without a relay note, and for anyone the users table does not have under that name and address.
        for kwargs in (dict(note='  '), dict(name='Someone Else'), dict(email='other@example.com'),
                       dict(entered_by=self.f.actor.name)):
            with self.assertRaises(PdfMappingError):
                self.relay(correction['id'], **kwargs)
            self.assertEqual(self.state(), before)
        confirmed = self.relay(correction['id'])['confirmed']
        self.assertEqual((confirmed['by'], confirmed['user_id'], confirmed['relayed']['by'], confirmed['relayed']['note']),
                         (self.f.actor.name, str(self.f.actor.user_id), 'Claude',
                          'Entered by Claude on the person\'s instruction of 2026-10-30'))
        after = self.state()
        entry = after['history'][-1]
        # Returned with the account, values and the model origin unchanged.
        self.assertEqual(entry['confirmed'], confirmed)
        self.assertEqual((entry['origin']['kind'], entry['actor_name'], after['holder']),
                         ('model', correction['actor_name'], CORRECTED))
        self.assertEqual({k: v for k, v in after.items() if k not in ('history', 'revision')},
                         {k: v for k, v in before.items() if k not in ('history', 'revision')})
        # A later instruction from the same person sits beside the first relay, which stays as it was.
        again = self.relay(correction['id'], note='Second instruction', basis='Asked again on 2026-10-31.')['confirmed']
        self.assertEqual({k: v for k, v in again.items() if k != 'later_relays'}, confirmed)
        self.assertEqual([(item['note'], item['basis']) for item in again['later_relays']],
                         [('Second instruction', 'Asked again on 2026-10-31.')])

    def test_a_relay_never_adds_to_a_confirmation_the_person_made_themselves(self):
        correction = self.claude_correction()
        with self.f.SessionLocal() as db:
            service.confirm_account_details(db, case_id=self.f.case.id, account_id=self.account_id, actor=self.f.actor,
                request=service.ConfirmAccountDetailsRequest(expected_revision=self.state()['revision'],
                    correction_id=correction['id'], basis='Checked page 1'))
        before = self.state()
        with self.assertRaises(PdfMappingError) as raised:
            self.relay(correction['id'])
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.state(), before)
        self.assertNotIn('relayed', before['history'][-1]['confirmed'])

    def test_no_route_can_enter_a_relayed_confirmation(self):
        import inspect
        from routers import financial_statement_import as routes
        self.assertNotIn('relayed', inspect.getsource(routes))
        self.assertNotIn('relayed', service.ConfirmAccountDetailsRequest.model_fields)

    def test_bank_correction_rekeys_the_account_and_refuses_another_accounts_key(self):
        with self.f.SessionLocal() as db:
            old_key = db.get(FinancialAccount, self.account_id).identity_key
        result = self.correct(institution='Other Synthetic Bank')
        with self.f.SessionLocal() as db:
            account = db.get(FinancialAccount, self.account_id)
            self.assertEqual(account.institution_name, 'Other Synthetic Bank')
            self.assertNotEqual(account.identity_key, old_key)
            self.assertIn('other synthetic bank', account.identity_key)
            # Another account takes the old key; undoing would collide with it.
            other = FinancialAccount(case_id=self.f.case.id, identity_key=old_key, identifier_as_printed='TEST123',
                identifier_normalised='123', currency=account.currency, metadata_={})
            db.add(other)
            db.commit()
        with self.assertRaises(PdfMappingError) as raised:
            self.undo(result['correction']['id'])
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.details(self.first)['details']['institution'], 'Other Synthetic Bank')


CLABE = '128180000000238632'


class AccountNumberCorrectionTests(AccountDetailsCorrectionTests):
    """Two statements saved with the CLABE as the account number: the account becomes the printed account
    number, the CLABE is kept as its alias, and statements saved either way stay on one account."""

    def setUp(self):
        real = statement_import_tests.StatementImportTests.request
        def with_clabe(fixture):
            return {**real(fixture), 'account_number': CLABE}
        from unittest.mock import patch
        with patch.object(statement_import_tests.StatementImportTests, 'request', with_clabe):
            super().setUp()

    def test_the_printed_number_replaces_the_clabe_which_is_kept_and_undo_restores_it(self):
        with self.f.SessionLocal() as db:
            key = db.get(FinancialAccount, self.account_id).identity_key
        result = self.correct(account_number='194-98075-001-8', reason='Page 1 prints 194-98075-001-8 beside the CLABE')
        self.assertEqual((result['account_number'], result['account_clabe']), ('194-98075-001-8', CLABE))
        with self.f.SessionLocal() as db:
            account = db.get(FinancialAccount, self.account_id)
            self.assertEqual((account.identifier_normalised, account.identity_key), ('194980750018', key))
        for source in (self.first, self.second):
            details = self.details(source)['details']
            self.assertEqual((details['account_number'], details['account_clabe']), ('194-98075-001-8', CLABE))
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        # A later edit of one statement, a holder spelling, stays on the account.
        view = self.details(self.first)
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.first, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder='TEST COMPANY',
                    account_number=view['details']['account_number'], institution=view['details']['institution']))
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        restored = self.undo(result['correction']['id'])
        self.assertEqual((restored['account_number'], restored['account_clabe']), (CLABE, ''))
        self.assertEqual(self.details(self.second)['details']['account_number'], CLABE)
        self.assertNotIn('account_clabe', self.details(self.second)['details'])
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})

    def test_a_clabe_is_refused_as_the_corrected_number(self):
        self.correct(account_number='194-98075-001-8')
        self.account_id = self.account_id
        with self.assertRaisesRegex(PdfMappingError, 'A CLABE is not the account number'):
            self.correct(account_number='012180001184673749')

    def test_a_split_saved_with_the_printed_number_rejoins_the_account(self):
        view = self.details(self.second)
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.second, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=view['details']['holder'],
                    account_number='194-98075-001-8', institution=view['details']['institution']))
        split = UUID(self.details(self.second)['account_id'])
        self.assertNotEqual(split, self.account_id)
        with self.f.SessionLocal() as db:
            preview = service.preview_account_details(db, case_id=self.f.case.id, account_id=self.account_id,
                request=service.AccountDetailsRequest(expected_revision=self.state()['revision'], reason='Page 1',
                                                      account_number='194-98075-001-8'))
        self.assertEqual([item['account_id'] for item in preview['rejoin']], [str(split)])
        result = self.correct(account_number='194-98075-001-8')
        self.assertEqual([s['source_document_id'] for s in result['correction']['rejoined']], [str(self.second)])
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})


    def test_a_statement_saved_with_its_own_holder_spelling_stays_on_the_account_when_its_number_is_corrected(self):
        # The account keeps the first spelling of the holder it was given; its statements print another (the
        # ingestion writer records such a spelling as a conflict and never splits on it). The account-wide number
        # correction must not split those statements off onto accounts of their own.
        holder = self.details(self.first)['details']['holder']
        with self.f.SessionLocal() as db:
            db.get(FinancialAccount, self.account_id).holder_name = holder + ' S.A. DE C.V.'
            db.commit()
        result = self.correct(account_number='194-98075-001-8', reason='Page 1 prints 194-98075-001-8 beside the CLABE')
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        for source in (self.first, self.second):
            details = self.details(source)['details']
            self.assertEqual((details['holder'], details['account_number'], details['account_clabe']),
                             (holder, '194-98075-001-8', CLABE))
        self.undo(result['correction']['id'])
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        self.assertEqual(self.details(self.second)['details']['account_number'], CLABE)
        self.assertEqual(len(result['correction']['statements']), 2)

    def test_a_statement_spelling_the_bank_its_own_way_joins_with_its_account_and_goes_nowhere_else(self):
        # A printed-number account whose record spells the bank as the account does, holding a statement whose own
        # details spell it the long way (the record kept the first spelling it was given). The correction joins
        # that statement to the corrected account; it is never moved to an account of its own.
        view = self.details(self.second)
        bank = view['details']['institution']
        with self.f.SessionLocal() as db:
            update_statement_details(db, case_id=self.f.case.id, source_id=self.second, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=view['details']['holder'],
                    account_number='194-98075-001-8', institution=bank + ', S.A., INSTITUCION DE BANCA MULTIPLE'))
        split = UUID(self.details(self.second)['account_id'])
        self.assertNotEqual(split, self.account_id)
        with self.f.SessionLocal() as db:
            db.get(FinancialAccount, split).institution_name = bank
            db.commit()
        result = self.correct(account_number='194-98075-001-8', reason='Page 1 prints 194-98075-001-8 beside the CLABE')
        self.assertEqual([s['source_document_id'] for s in result['correction']['rejoined']], [str(self.second)])
        self.assertEqual(self.accounts_of(self.first, self.second), {self.account_id})
        self.assertEqual(self.details(self.second)['details']['institution'], bank + ', S.A., INSTITUCION DE BANCA MULTIPLE')

    # BNB2 2026-10-30, ECOTERRA BBVA USD Sep-Dec 2022: one statement produced twice, one copy saved under the CLABE
    # and one under the printed number, so on two accounts. The number correction joins them; the copy is set aside at
    # once by the duplicates rule, linked to the copy kept, and undoing the correction restores it.
    def saved_copy(self, number):
        from postgres.models.evidence import IngestionLog
        from postgres.models.financial_judgements import FinancialJudgement
        f, original = self.f, self.f.file
        for table in (IngestionLog.__table__, FinancialJudgement.__table__):
            table.create(f.db.get_bind(), checkfirst=True)
        path = Path(f._directory) / 'statement-copy.pdf'
        path.write_bytes(b'%PDF-1.4\nThe same statement, produced again')
        copy = f.evidence(hashlib.sha256(path.read_bytes()).hexdigest())
        copy.stored_path = str(path)
        # The other production prints (and its reading gives) the account number; the first gave the CLABE.
        text = f.db.get(EvidenceDocumentText, original.id)
        content = text.content.replace('TEST123', number)
        f.db.add(EvidenceDocumentText(evidence_file_id=copy.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=text.engine_job_id, source_locations=json.loads(json.dumps(text.source_locations).replace('TEST123', number))))
        geometry = f.db.get(EvidenceTableGeometry, (original.id, 1))
        f.db.add(EvidenceTableGeometry(evidence_file_id=copy.id, page_number=1, engine_job_id=geometry.engine_job_id,
            payload=json.loads(json.dumps(geometry.payload).replace('TEST123', number))))
        f.db.commit()
        f.file = copy
        try:
            return UUID(f.confirm({**f.request(), 'account_number': number})['source_document_id'])
        finally:
            f.file = original

    def ledger(self):
        with self.f.SessionLocal() as db:
            periods = db.execute(select(FinancialStatementPeriod.account_id, FinancialStatementPeriod.period_start)
                .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
                .where(FinancialStatementPeriod.case_id == self.f.case.id, FinancialSourceDocument.status == 'admitted')).all()
            rows = db.scalars(select(FinancialTransaction.amount_minor).where(FinancialTransaction.case_id == self.f.case.id,
                FinancialTransaction.ledger_status == 'admitted')).all()
            return sorted((str(a), str(p)) for a, p in periods), sorted(rows)

    def test_the_correction_sets_aside_a_copy_it_brings_onto_the_account_and_undo_restores_it(self):
        number = '194-98075-001-8'
        copy = self.saved_copy(number)
        own = self.accounts_of(copy)
        self.assertNotIn(self.account_id, own)
        before = self.ledger()
        with self.f.SessionLocal() as db:
            copy_rows = db.scalars(select(FinancialTransaction.amount_minor).where(
                FinancialTransaction.source_document_id == copy, FinancialTransaction.ledger_status == 'admitted')).all()
        result = self.correct(account_number=number, reason='Page 1 prints 194-98075-001-8 beside the CLABE')
        self.assertEqual([item['source_document_id'] for item in result['correction']['rejoined']], [str(copy)])
        self.assertEqual([(item['source_document_id'], item['retained_source_document_id'])
                          for item in result['correction']['copies_set_aside']], [(str(copy), str(self.first))])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, copy)
            self.assertEqual((document.status, document.superseded_by_id), ('superseded', self.first))
            entry = db.get(FinancialAccount, self.account_id).metadata_['account_details_history'][-1]
            self.assertEqual([item['source_document_id'] for item in entry['copies_set_aside']], [str(copy)])
        # The account holds each period once; the copy's payments no longer count twice.
        periods, rows = self.ledger()
        self.assertEqual(len(periods), len(set(periods)))
        self.assertEqual(len(periods), len(before[0]) - 1)
        self.assertEqual(Counter(before[1]) - Counter(copy_rows), Counter(rows))
        restored = self.undo(result['correction']['id'])
        self.assertEqual(restored['correction']['copies_restored'], [str(copy)])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, copy).status, 'admitted')
        self.assertEqual(self.accounts_of(copy), own)
        self.assertEqual(self.ledger(), before)

    def test_switched_off_the_copy_stays_saved(self):
        from unittest.mock import patch
        from services.financial import admitted_statement_duplicates as admitted
        copy = self.saved_copy('194-98075-001-8')
        with patch.object(admitted, 'AFTER_ACCOUNT_CHANGE', False):
            result = self.correct(account_number='194-98075-001-8')
        self.assertNotIn('copies_set_aside', result['correction'])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, copy).status, 'admitted')


class AccountDetailsRouteTests(TestCase):
    def test_routes_read_preview_save_and_undo_with_edit_access_for_changes(self):
        from routers.financial_statement_import import router
        routes = {(route.path, method): route for route in router.routes for method in route.methods}
        base = '/api/financial/statement-import/accounts/{account_id}/details'
        for path, method in ((base, 'GET'), (base + '/preview', 'POST'), (base, 'POST'), (base + '/undo', 'POST')):
            self.assertIn((path, method), routes)
        # Changes add the case edit check to the router's view checks.
        viewing = len(routes[(base + '/preview', 'POST')].dependencies)
        for path in (base, base + '/undo'):
            self.assertEqual(len(routes[(path, 'POST')].dependencies), viewing + 1)
