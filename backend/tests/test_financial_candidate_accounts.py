import unittest
from uuid import UUID, uuid4
from unittest.mock import patch
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from postgres.base import Base
from postgres.models.financial import FinancialAccount, FinancialIngestionRun
from services.financial.candidate_accounts import CandidateAccountRequest, create_candidate_account
from services.financial.candidate_reviews import read_candidate_review
from services.financial.candidate_store import CandidateStoreError, list_candidate_accounts
from tests import test_financial_candidate_store as fixture


class CandidateAccountTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CandidateStoreTests()
        self.f.setUp()
        Base.metadata.create_all(self.f.engine, tables=[FinancialAccount.__table__, FinancialIngestionRun.__table__])
        self.saved = self.f.save()
        self.candidate = UUID(self.saved['candidates'][0]['id'])
        self.request = dict(expected_revision=self.saved['candidates'][0]['review_revision'],
                            label='Redacted card A', currency='GBP', reason='Account number unreadable in this source.')
        self.factory = sessionmaker(bind=self.f.engine)

    def tearDown(self):
        self.f.tearDown()

    def create(self, **updates):
        return create_candidate_account(session_factory=self.factory, case_id=self.f.case,
            candidate_id=self.candidate, request={**self.request, **updates}, actor=self.f.actor)

    def test_account_is_provisional_with_no_invented_identifier_or_holder(self):
        result = self.create()
        self.assertTrue(result['created'])
        self.assertTrue(result['account']['provisional'])
        self.assertIsNone(result['account']['identifier'])
        self.assertIsNone(result['account']['holder'])
        self.assertFalse(result['applied'])
        with self.factory() as db:
            account = db.get(FinancialAccount, UUID(result['account']['id']))
            self.assertTrue(account.metadata_['identity_provisional'])
            self.assertEqual(account.metadata_['candidate_account_source_file_id'], str(self.f.file))
            self.assertEqual(read_candidate_review(db, case_id=self.f.case, candidate_id=self.candidate)['status'], 'pending')
            run = db.get(FinancialIngestionRun, UUID(result['run_id']))
            self.assertEqual(run.status, 'completed')
            self.assertEqual(run.started_by_email, self.f.actor.email)
            self.assertEqual(run.config['request']['reason'], self.request['reason'])

    def test_identical_retry_reuses_account_and_retains_first_seen_run(self):
        first, second = self.create(), self.create()
        self.assertEqual(first['account']['id'], second['account']['id'])
        self.assertFalse(second['created'])
        with self.factory() as db:
            self.assertEqual(str(db.get(FinancialAccount, UUID(first['account']['id'])).first_seen_run_id), first['run_id'])

    def test_different_labels_or_currencies_do_not_merge(self):
        first = self.create()
        other_label = self.create(label='Redacted card B')
        other_currency = self.create(currency='USD')
        self.assertEqual(len({r['account']['id'] for r in (first,other_label,other_currency)}),3)

    def test_provisional_label_is_searchable_only_in_its_case(self):
        result = self.create()
        with self.factory() as db:
            self.assertEqual(list_candidate_accounts(db, case_id=self.f.case, search='Redacted card')['items'][0]['id'],result['account']['id'])
            self.assertEqual(list_candidate_accounts(db, case_id=uuid4(), search='Redacted card')['items'],[])

    def test_wrong_case_creates_neither_run_nor_account(self):
        with self.assertRaises(CandidateStoreError) as caught:
            create_candidate_account(session_factory=self.factory, case_id=uuid4(), candidate_id=self.candidate,
                                     request=self.request, actor=self.f.actor)
        self.assertEqual(caught.exception.status_code,404)
        with self.factory() as db:
            self.assertEqual(list(db.scalars(select(FinancialIngestionRun))),[])

    def test_stale_review_refused_with_failed_run_and_no_account(self):
        with self.assertRaises(CandidateStoreError): self.create(expected_revision='f'*64)
        with self.factory() as db:
            self.assertEqual(list(db.scalars(select(FinancialAccount))),[])
            self.assertEqual(db.scalar(select(FinancialIngestionRun)).status,'failed')

    def test_source_drift_refused(self):
        self.f.text.engine_job_id=uuid4()
        self.f.db.commit()
        with self.assertRaises(CandidateStoreError):self.create()

    def test_invalid_currency_blank_reason_label_and_extra_identity_are_refused(self):
        for changes in ({'currency':'XYZ'},{'reason':' '},{'label':' '},{'identifier':'1234'},{'label':'a'*129}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                CandidateAccountRequest.model_validate({**self.request,**changes})

    def test_account_write_failure_rolls_back_and_run_records_failure(self):
        with patch('services.financial.candidate_accounts.record_account', side_effect=RuntimeError('simulated write failure')):
            with self.assertRaises(RuntimeError):self.create()
        with self.factory() as db:
            self.assertEqual(list(db.scalars(select(FinancialAccount))),[])
            self.assertEqual(db.scalar(select(FinancialIngestionRun)).status,'failed')
