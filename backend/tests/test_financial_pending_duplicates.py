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

    def test_investigator_can_leave_matching_copy_unimported_and_restore(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (other.id, 1))
            payload = deepcopy(geometry.payload)
            value = next(v for v in payload[0]['table']['values'] if v['row'] == 2 and v['column'] == 1)
            value['text'] = 'Different retained reading description'
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

    def test_changed_financial_content_requires_comparison(self):
        self.f.confirm()
        other = self.fixture.copy_file()
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (other.id, 1))
            payload = deepcopy(geometry.payload)
            value = next(item for item in payload[0]['table']['values'] if item['row'] == 2 and item['column'] == 1)
            value['text'] = 'A revised transaction description'
            geometry.payload = payload
            db.commit()
        self.assertEqual(self.decision(other)['status'], 'needs_comparison')

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
        with self.f.SessionLocal() as db:
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=batches._digest({}))
        self.assertEqual(self.fixture.b.status(batch)['items'][0]['status'], 'attention')
        self.assertEqual(self.decision(other)['status'], 'needs_comparison')
