import unittest
from uuid import uuid4
from sqlalchemy.orm import Session
from postgres.base import Base
from postgres.models.financial_candidates import FinancialStatementReviewDraft
from services.financial.statement_review_drafts import read_statement_draft, save_statement_draft
from services.financial.candidate_store import CandidateStoreError
from tests import test_financial_candidate_statement_scopes as fixture

class StatementDraftTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.StatementScopeTests()
        self.f.setUp()
        Base.metadata.create_all(self.f.engine, tables=[FinancialStatementReviewDraft.__table__])
    def tearDown(self): self.f.tearDown()
    def read(self, **changes):
        return read_statement_draft(self.f.db, **{**dict(case_id=self.f.case.id, evidence_file_id=self.f.file.id), **changes})
    def save(self, revision=None, scopes=None):
        return save_statement_draft(self.f.db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
            request=dict(expected_revision=revision, statement_scopes=[self.f.scope()] if scopes is None else scopes), actor=self.f.actor)
    def test_save_reopen_replace_and_stale_update(self):
        self.assertIsNone(self.read()['revision'])
        saved = self.save()
        with Session(self.f.engine) as db:
            reopened = read_statement_draft(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id)
        self.assertEqual(saved['statement_scopes'], reopened['statement_scopes'])
        self.assertEqual(saved['revision'], reopened['revision'])
        with self.assertRaisesRegex(CandidateStoreError, 'changed'): self.save()
        cleared = self.save(saved['revision'], [])
        self.assertNotEqual(cleared['revision'], saved['revision'])
        self.assertEqual(self.read()['statement_scopes'], [])
        self.assertEqual(self.f.transactions(), [])
    def test_wrong_case_rows_and_accounts_are_refused(self):
        with self.assertRaises(CandidateStoreError): self.read(case_id=uuid4())
        scope = self.f.scope(); scope['candidate_ids']=[str(uuid4())]
        with self.assertRaises(CandidateStoreError): self.save(scopes=[scope])
        scope = self.f.scope(); scope['account_id']=str(uuid4())
        with self.assertRaises(CandidateStoreError): self.save(scopes=[scope])
        self.assertIsNone(self.read()['revision'])
    def test_incomplete_editor_survives_reopen_and_scope_only_save(self):
        editor = dict(group='',selected=[],start='2026-01-01',end='',opening='123.',closing='',convention='',reason='Unfinished',cells={})
        saved = save_statement_draft(self.f.db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,
            request=dict(statement_scopes=[],editor_draft=editor),actor=self.f.actor)
        with Session(self.f.engine) as db:
            reopened = read_statement_draft(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id)
        self.assertEqual(reopened['editor_draft'],editor)
        scoped = self.save(saved['revision'])
        self.assertEqual(scoped['editor_draft'],editor)
        self.assertEqual(self.f.transactions(),[])
        with self.assertRaisesRegex(CandidateStoreError,'changed'):
            save_statement_draft(self.f.db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,
                request=dict(expected_revision=saved['revision'],statement_scopes=[],editor_draft=editor),actor=self.f.actor)

    def test_editor_cannot_reference_another_case_candidate(self):
        editor = dict(group='',selected=[str(uuid4())],start='',end='',opening='',closing='',convention='',reason='',cells={})
        with self.assertRaisesRegex(CandidateStoreError,'this PDF'):
            save_statement_draft(self.f.db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,
                request=dict(statement_scopes=[],editor_draft=editor),actor=self.f.actor)
        self.assertIsNone(self.read()['revision'])

    def test_finalization_seals_draft_writes(self):
        saved = self.save()
        self.f.finalize(self.f.scoped_request())
        with self.assertRaisesRegex(CandidateStoreError, 'finalized'): self.save(saved['revision'], [])
        self.assertEqual(self.read()['revision'], saved['revision'])
