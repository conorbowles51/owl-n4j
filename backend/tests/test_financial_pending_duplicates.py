"""Synthetic statements prove ignored copies preserve evidence and review work."""
from copy import deepcopy
from pathlib import Path
from uuid import UUID
from unittest import TestCase
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from services.financial.pending_statement_duplicates import (
    apply_duplicate_disposition, decide_duplicate_disposition, METADATA_KEY, _financial_reading,
)
from services.financial.statement_import import read_statement_import
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_statement_overlap as overlap_fixture


class PendingDuplicateTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.primary = self.f.file

    def tearDown(self):
        self.fixture.tearDown()

    def decision(self, file, action='check', **kwargs):
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=file.id)
            return decide_duplicate_disposition(db, case_id=self.f.case.id, evidence_file_id=file.id,
                action=action, expected_reading_revision=proposal['revision'], currency=proposal['currency'],
                statement_id=proposal.get('statement_id'), actor=self.f.actor, **kwargs)['duplicate_disposition']

    def test_unprinted_start_import_copy_and_coverage_keep_known_end(self):
        from hashlib import sha256
        from postgres.models.evidence import EvidenceDocumentText
        from services.financial.account_history import account_history
        from postgres.models.financial import FinancialStatementPeriod
        from tests.financial_reconciled_fixture import install_reconciled_source
        install_reconciled_source(self.f)
        text = self.f.db.get(EvidenceDocumentText, self.primary.id)
        text.content = '\n'.join(line for line in text.content.splitlines() if not line.startswith('Statement Period:'))
        text.content_sha256 = sha256(text.content.encode()).hexdigest()
        text.character_count = len(text.content)
        self.f.db.commit()
        other = self.fixture.copy_file()
        Path(other.stored_path).write_bytes(self.f.path.read_bytes())
        other.sha256 = self.primary.sha256
        self.f.db.commit()
        def request():
            raw = self.f.request()
            raw.update(period_start='', period_end='2023-12-31', period_start_unprinted=True)
            return raw
        self.assertFalse(self.f.preview()['metadata']['period_start'])
        raw = request()
        first = self.f.confirm(raw)
        self.assertEqual(first['transaction_count'], 12)
        self.assertFalse(self.f.confirm(raw)['created'])
        with self.f.SessionLocal() as db:
            period = account_history(db, case_id=self.f.case.id)['groups'][0]['periods'][0]
            self.assertIsNone(period['start'])
            self.assertEqual(period['end'], '2023-12-31')
            self.assertEqual(period['status'], 'reconciled')
            stored = db.get(FinancialStatementPeriod, UUID(period['id']))
            self.assertEqual(stored.period_start_source, 'absent')
            self.assertEqual(stored.period_end_source, 'printed')
        self.f.file = other
        copied = request()
        with self.f.SessionLocal() as db:
            proposal = self.f.preview()
            proposal['statement_page_numbers'] = [2]
            result = apply_duplicate_disposition(db, case_id=self.f.case.id,
                file=db.get(EvidenceFile, other.id), proposal=proposal, request=copied)
            self.assertNotEqual(result['status'], 'ignored')
        changed = deepcopy(copied)
        changed['rows'][1]['description'] = 'Investigator correction retained for comparison'
        with self.assertRaises(PdfMappingError):
            self.f.confirm(changed)
        receipt = self.f.confirm(copied)
        self.assertEqual(receipt['outcome'], 'duplicate_ignored')
        self.assertEqual(receipt['duplicate_disposition']['retained']['source_document_id'], first['source_document_id'])
        self.assertEqual(self.f.confirm(copied)['outcome'], 'duplicate_ignored')
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
            self.assertIsNotNone(db.get(EvidenceFile, other.id))

    def test_investigator_can_leave_matching_copy_unimported_and_restore(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (other.id, 1))
            payload = deepcopy(geometry.payload)
            value = next(v for v in payload[0]['table']['values'] if v['row'] == 2 and v['column'] == 1)
            value['text'] = 'Different retained reading description'
            value = next(v for v in payload[0]['table']['values'] if v['row'] == 2 and v['column'] == 0)
            value['text'] = '2023-03-19'
            geometry.payload = payload
            db.commit()
        self.assertEqual(self.decision(other)['status'], 'needs_comparison')
        before = self.f.preview()['transaction_count']
        ignored = self.decision(other, 'ignore')
        self.assertEqual(ignored['basis'], 'investigator_decision')
        self.assertEqual(ignored['status'], 'ignored')
        self.assertTrue(ignored['current'])
        self.assertEqual(self.decision(other)['revision'], ignored['revision'])
        self.f.file = other
        self.assertEqual(self.f.confirm()['outcome'], 'duplicate_ignored')
        restored = self.decision(other, 'restore', expected_decision_revision=ignored['revision'])
        self.assertEqual(restored['status'], 'restored')
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), before)
            self.assertIsNotNone(db.get(EvidenceFile, other.id))

    def test_ignore_requires_a_current_matching_statement(self):
        with self.assertRaises(PdfMappingError):
            self.decision(self.primary, 'ignore')

    def test_identical_reading_ignored_at_import_and_reopening_is_idempotent(self):
        first = self.f.confirm()
        other = self.fixture.copy_file()
        self.f.file = other
        receipt = self.f.confirm()
        self.assertEqual(receipt.get('outcome'), 'duplicate_ignored', receipt)
        self.assertEqual(receipt['duplicate_disposition']['basis'], 'identical_financial_reading')
        self.assertEqual(receipt['duplicate_disposition']['retained']['source_document_id'], first['source_document_id'])
        again = self.f.confirm()
        self.assertEqual(again['duplicate_disposition']['revision'], receipt['duplicate_disposition']['revision'])
        self.assertEqual(self.f.preview()['duplicate_disposition']['status'], 'ignored')
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
            stored = db.get(EvidenceFile, other.id).metadata_[METADATA_KEY]['']
            self.assertEqual(stored['history'], [])
            self.assertIsNotNone(db.get(EvidenceFile, self.primary.id))

    def test_restore_survives_auto_check_but_new_edits_invalidate_decision(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        ignored = self.decision(other)
        self.assertEqual(ignored['status'], 'ignored')
        restored = self.decision(other, 'restore', expected_decision_revision=ignored['revision'])
        self.assertEqual(restored['status'], 'restored')
        self.assertEqual(self.decision(other)['revision'], restored['revision'])
        self.f.file = other
        draft = self.f.request()
        draft['rows'][1]['description'] = 'An investigator correction'
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, other.id)
            file.metadata_ = {**file.metadata_, 'financial_review_progress': {'': {'request': draft}}}
            db.commit()
        self.assertFalse(self.f.preview()['duplicate_disposition']['current'])
        self.assertEqual(self.decision(other)['status'], 'needs_comparison')

    def test_unique_corrected_value_is_not_hidden(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        self.f.file = other
        raw = self.f.request()
        raw['rows'][1]['description'] = 'New supported detail'
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, other.id)
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=other.id)
            result = apply_duplicate_disposition(db, case_id=self.f.case.id, file=file, proposal=proposal, request=raw)
            self.assertEqual(result['status'], 'needs_comparison')

    def revise_copy(self, other, column, text):
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (other.id, 1))
            payload = deepcopy(geometry.payload)
            value = next(item for item in payload[0]['table']['values'] if item['row'] == 2 and item['column'] == column)
            value['text'] = text
            geometry.payload = payload
            db.commit()

    def test_changed_financial_content_requires_comparison(self):
        self.f.confirm()
        for column, text in [(0, '2023-03-19'), (2, '€125,001')]:
            with self.subTest(column=column):
                other = self.fixture.copy_file()
                self.revise_copy(other, column, text)
                self.assertEqual(self.decision(other)['status'], 'needs_comparison')

    def test_copy_read_with_other_wording_but_equal_money_is_a_duplicate(self):
        """Decision (r1-reproduced): another production of a statement whose
        payments and balances are equal is set aside even when its wording was
        read differently. Reverse: require the whole reading to be equal."""
        first = self.f.confirm()
        other = self.fixture.copy_file()
        self.revise_copy(other, 1, 'A revised transaction description')
        decision = self.decision(other)
        self.assertEqual(decision['status'], 'ignored', decision)
        self.assertEqual(decision['basis'], 'identical_financial_reading')
        self.assertEqual(decision['retained']['source_document_id'], first['source_document_id'])

    def test_blank_reading_cannot_establish_identical_financial_content(self):
        fingerprint, usable = _financial_reading(dict(rows=[], metadata={}))
        self.assertTrue(fingerprint)
        self.assertFalse(usable)

    def test_identity_guards_do_not_suppress_different_compartments_or_periods(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        self.f.file = other
        original = self.f.request()
        for field, value in [('account_number', '0TEST123'), ('account_number', 'OTHER123'), ('holder', 'Different Company'),
                             ('institution', 'Different Bank'), ('period_end', '2024-01-01'),
                             ('currency', 'USD'), ('account_number', '***123')]:
            with self.subTest(field=field, value=value), self.f.SessionLocal() as db:
                proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=other.id)
                result = apply_duplicate_disposition(db, case_id=self.f.case.id, file=db.get(EvidenceFile, other.id),
                    proposal=proposal, request={**original, field: value})
                self.assertNotEqual(result['status'], 'ignored', result)

    def test_identical_bytes_copy_receives_ignored_receipt_not_another_import(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, other.id)
            file.sha256 = self.primary.sha256
            file.stored_path = self.primary.stored_path
            db.commit()
        self.f.file = other
        result = self.f.confirm()
        self.assertEqual(result['outcome'], 'duplicate_ignored')
        self.assertEqual(result['duplicate_disposition']['basis'], 'identical_bytes')

    def test_pending_batch_ignores_only_copy_and_restore_reopens_review(self):
        other = self.fixture.copy_file()
        batch = self.fixture.create(other, self.primary)
        state = self.fixture.b.status(batch)
        self.assertEqual(state['counts']['ready'], 1)
        self.assertEqual(state['counts']['duplicate_ignored'], 1)
        self.assertEqual(state['available_transactions'], 12)
        ignored_item = next(item for item in state['items'] if item['status'] == 'duplicate_ignored')
        ignored_file = other if ignored_item['file_id'] == str(other.id) else self.primary
        ignored = ignored_item['duplicate_disposition']
        restored = self.decision(ignored_file, 'restore', expected_decision_revision=ignored['revision'])
        self.assertEqual(restored['status'], 'restored')
        # A lost response can retry the same original restore revision.
        self.assertEqual(self.decision(ignored_file, 'restore', expected_decision_revision=ignored['revision'])['revision'], restored['revision'])
        current = self.fixture.b.status(batch)
        reopened = next(item for item in current['items'] if item['id'] == ignored_item['id'])
        self.assertEqual(reopened['status'], 'attention')
        self.assertFalse(reopened['can_import'])
        self.assertEqual(reopened['duplicate_disposition']['status'], 'restored')
        self.assertEqual(self.decision(ignored_file)['status'], 'restored')

    def test_period_decision_does_not_hide_another_period_in_the_same_file(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        ignored = self.decision(other)
        self.assertEqual(ignored['status'], 'ignored')
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=other.id)
            second = deepcopy(proposal)
            second['statement_id'] = 'f' * 64
            second['metadata'] = {**second['metadata'], 'period_start': '2024-01-01', 'period_end': '2024-12-31'}
            second['saved_review'] = None
            result = apply_duplicate_disposition(db, case_id=self.f.case.id, file=db.get(EvidenceFile, other.id), proposal=second)
            self.assertEqual(result['status'], 'retained')
            db.commit()
            decisions = db.get(EvidenceFile, other.id).metadata_[METADATA_KEY]
            self.assertEqual(decisions['']['status'], 'ignored')
            self.assertEqual(decisions['f' * 64]['status'], 'retained')

    def test_stale_reading_and_cross_case_decisions_are_rejected(self):
        from uuid import uuid4
        with self.f.SessionLocal() as db:
            for case_id, revision in [(uuid4(), 'a' * 64), (self.f.case.id, 'a' * 64)]:
                with self.subTest(case_id=case_id), self.assertRaises(PdfMappingError):
                    decide_duplicate_disposition(db, case_id=case_id, evidence_file_id=self.primary.id,
                        action='check', expected_reading_revision=revision, actor=self.f.actor)
                db.rollback()

    def test_retained_source_removal_invalidates_ignored_projection(self):
        first = self.f.confirm()
        other = self.fixture.copy_file()
        self.decision(other)
        from postgres.models.financial import FinancialSourceDocument
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, UUID(first['source_document_id']))
            source.metadata_ = {**source.metadata_, 'financial_import_removal': {'reason': 'Synthetic removal'}}
            db.commit()
        self.f.file = other
        decision = self.f.preview()['duplicate_disposition']
        self.assertFalse(decision['current'])
        self.assertEqual(decision['status'], 'needs_comparison')

    def test_batch_only_correction_is_not_hidden_by_individual_duplicate_check(self):
        from services.financial import import_batches as batches
        from services.financial.statement_import import StatementReviewDraft
        self.f.confirm()
        other = self.fixture.copy_file()
        batch = self.fixture.create(other)
        item = self.fixture.b.status(batch)['items'][0]
        self.assertEqual(item['status'], 'duplicate_ignored')
        self.f.file = other
        raw = self.f.request()
        next(row for row in raw['rows'] if not row['excluded'])['description'] = 'Unique batch-only investigator detail'
        # Since 8cade27d an ignored duplicate requires explicit restoration
        # before further edits (automation-delivery-plan-2026-09-28).
        with self.f.SessionLocal() as db, self.assertRaisesRegex(PdfMappingError, 'Restore this duplicate explicitly'):
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=batches._digest({}))
        self.assertEqual(self.fixture.b.status(batch)['items'][0]['status'], 'duplicate_ignored')
        ignored = self.decision(other)
        self.assertEqual(ignored['status'], 'ignored')
        self.assertEqual(self.decision(other, 'restore', expected_decision_revision=ignored['revision'])['status'], 'restored')
        item = self.fixture.b.status(batch)['items'][0]
        self.assertIn(item['status'], ('ready', 'attention'))
        from postgres.models.financial_import_batches import FinancialImportBatchItem
        from services.financial.effective_statement_review import batch_review_revision
        from services.financial.statement_progress import review_progress
        with self.f.SessionLocal() as db:
            stored = db.get(FinancialImportBatchItem, UUID(item['id']))
            revision = batch_review_revision(stored.review_request,
                review_progress(db.get(EvidenceFile, stored.file_id), stored.statement_key))
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=revision)
        self.assertEqual(self.fixture.b.status(batch)['items'][0]['status'], 'attention')
        self.assertEqual(self.decision(other)['status'], 'needs_comparison')

    def masked_copy_batch(self, *, identical=True, revised=False):
        import hashlib
        from postgres.models.evidence import EvidenceDocumentText
        text = self.f.db.get(EvidenceDocumentText, self.primary.id)
        text.content = text.content.replace('TEST123', '***123')
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        self.f.db.commit()
        other = self.fixture.copy_file(revised=revised)
        if identical:
            file = self.f.db.get(EvidenceFile, other.id)
            file.sha256 = self.primary.sha256
            file.stored_path = self.primary.stored_path
            self.f.db.commit()
        return other, self.fixture.create(self.primary, other)

    def test_identical_masked_copies_have_one_ready_period_and_one_excluded_copy(self):
        other, batch = self.masked_copy_batch()
        state = self.fixture.b.status(batch)
        self.assertEqual(state['counts']['duplicate_ignored'], 1, state)
        self.assertEqual(state['available_transactions'], 12)
        ignored = next(item for item in state['items'] if item['status'] == 'duplicate_ignored')
        self.assertEqual(ignored['duplicate_disposition']['basis'], 'identical_bytes')
        # A batch GET must validate persisted fingerprints, not reconstruct all
        # ignored PDFs. Reopening cannot write decisions or restart reading.
        from unittest.mock import patch
        with patch('services.financial.statement_import.read_statement_import', side_effect=AssertionError('reparsed duplicate')), \
             patch('services.financial.import_batches.read_statement_import', side_effect=AssertionError('reparsed duplicate')):
            reopened = self.fixture.b.status(batch)
        self.assertEqual(reopened['counts'], state['counts'])

    def test_masked_identity_and_equal_money_in_other_bytes_is_a_duplicate(self):
        """A card statement prints four digits; another production of it is
        still the same statement when its money is equal (decision r1-reproduced;
        before it, only identical bytes could set a masked copy aside)."""
        other, batch = self.masked_copy_batch(identical=False)
        state = self.fixture.b.status(batch)
        self.assertEqual(state['counts']['duplicate_ignored'], 1, state)
        self.assertEqual(state['available_transactions'], 12)
        ignored = next(item for item in state['items'] if item['status'] == 'duplicate_ignored')
        disposition = ignored['duplicate_disposition']
        self.assertEqual(disposition['basis'], 'identical_financial_reading')
        self.assertIn('payments_and_balances', disposition['matched_fields'])
        self.assertNotIn('full_account_number', disposition['matched_fields'])

    def test_masked_copy_with_different_money_holds_both_for_comparison(self):
        _, batch = self.masked_copy_batch(identical=False, revised=True)
        state = self.fixture.b.status(batch)
        self.assertEqual(state['counts']['duplicate_ignored'], 0, state)
        self.assertEqual(state['available_statements'], 0, state)
        for item in state['items']:
            self.assertFalse(item['can_import'])
            self.assertTrue(any(problem.get('matching_statement') for problem in item['problems']), item['problems'])

    def test_edited_masked_copy_returns_to_review(self):
        _, batch = self.masked_copy_batch()
        state = self.fixture.b.status(batch)
        item = next(item for item in state['items'] if item['status'] == 'duplicate_ignored')
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        with self.f.SessionLocal() as db:
            file_id = UUID(item['file_id'])
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=file_id)
            from services.financial.import_batches import initial_request
            draft = initial_request(proposal)
            next(row for row in draft['rows'] if not row['excluded'])['description'] = 'Investigator correction'
            db.get(Item, UUID(item['id'])).review_request = draft
            db.commit()
        current = self.fixture.b.status(batch)
        edited = next(row for row in current['items'] if row['id'] == item['id'])
        self.assertNotEqual(edited['status'], 'duplicate_ignored')

    def test_masked_copy_batch_imports_payments_once_and_preserves_both_sources(self):
        other, batch = self.masked_copy_batch()
        from services.financial import import_batches as batches
        state = self.fixture.b.status(batch)
        with self.f.SessionLocal() as db:
            batches.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=state['ready_revision'], actor=self.f.actor)
        self.fixture.b.advance(batch)
        current = self.fixture.b.status(batch)
        self.assertEqual(current['counts']['imported'], 1)
        self.assertEqual(current['counts']['duplicate_ignored'], 1)
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
            self.assertIsNotNone(db.get(EvidenceFile, self.primary.id))
            self.assertIsNotNone(db.get(EvidenceFile, other.id))

    def test_identical_bytes_different_source_section_requires_comparison(self):
        other, batch = self.masked_copy_batch()
        from unittest.mock import patch
        from services.financial import pending_statement_duplicates as duplicates
        original = duplicates._candidate
        def different_section(*args, **kwargs):
            result = original(*args, **kwargs)
            if result:
                file, proposal, request = result
                proposal = {**proposal, 'statement_page_numbers': [2]}
                return file, proposal, request
            return result
        with patch.object(duplicates, '_candidate', side_effect=different_section):
            decision = self.decision(other)
        self.assertEqual(decision['status'], 'needs_comparison')


class ReproducedStatementTests(TestCase):
    """Another production of a statement can read its holder or bank name
    differently; equal money still makes it the same statement."""
    setUp = PendingDuplicateTests.setUp
    tearDown = PendingDuplicateTests.tearDown
    decision = PendingDuplicateTests.decision

    def reread_copy(self, other, old, new):
        import hashlib
        from postgres.models.evidence import EvidenceDocumentText
        with self.f.SessionLocal() as db:
            text = db.get(EvidenceDocumentText, other.id)
            self.assertIn(old, text.content)
            text.content = text.content.replace(old, new)
            text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
            text.character_count = len(text.content)
            db.commit()

    def test_holder_read_differently_with_equal_money_is_a_duplicate(self):
        first = self.f.confirm()
        other = self.fixture.copy_file()
        self.reread_copy(other, 'Account Name: Test Company', 'Account Name: Test Company Limited')
        decision = self.decision(other)
        self.assertEqual(decision['status'], 'ignored', decision)
        self.assertEqual(decision['retained']['source_document_id'], first['source_document_id'])
        self.assertNotIn('account_holder', decision['matched_fields'])
        self.assertIn('bank', decision['matched_fields'])

    def test_bank_read_differently_needs_equal_payments(self):
        first = self.f.confirm()
        other = self.fixture.copy_file()
        self.reread_copy(other, 'Bank: Synthetic Bank', 'Bank: Synthetic Bank NA')
        decision = self.decision(other)
        self.assertEqual(decision['status'], 'ignored', decision)
        self.assertEqual(decision['retained']['source_document_id'], first['source_document_id'])
        self.assertNotIn('bank', decision['matched_fields'])
        revised = self.fixture.copy_file(revised=True)
        self.reread_copy(revised, 'Bank: Synthetic Bank', 'Bank: Synthetic Bank NA')
        # Different money under a differently named bank is not proof of anything.
        self.assertEqual(self.decision(revised)['status'], 'retained')

    def test_same_printed_period_ignores_holder_and_reference_strength_only(self):
        from services.financial.statement_import_overlap import same_printed_period
        base = dict(identity='x', account_reference='****1234', currency='USD', start='2020-05-12',
                    end='2020-06-11', account_type='credit_card', holder='a', full_reference=False)
        self.assertTrue(same_printed_period(base, {**base, 'holder': 'b', 'identity': 'y', 'account_reference': '...1234'}))
        self.assertTrue(same_printed_period(base, {**base, 'account_reference': 'xxxx1234'}))
        letters = {**base, 'account_reference': 'gater1'}
        for other in ('gates1', 'gateh1', '1', '****1'):
            with self.subTest(other=other):
                self.assertFalse(same_printed_period(letters, {**letters, 'account_reference': other}))
        for key, value in [('account_reference', '****1235'), ('currency', 'EUR'), ('start', '2020-05-13'),
                           ('end', '2020-06-12'), ('account_type', 'checking'), ('account_reference', '')]:
            with self.subTest(key=key):
                self.assertFalse(same_printed_period(base, {**base, key: value}))
        self.assertFalse(same_printed_period({**base, 'account_reference': 'n/a'}, {**base, 'account_reference': 'n/a'}))
