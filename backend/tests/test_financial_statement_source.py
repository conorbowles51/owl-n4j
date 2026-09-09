import unittest
from unittest.mock import patch, Mock
from sqlalchemy import select
from fastapi import HTTPException
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialStatementPeriod
from services.financial.ledger_source import statement_source, LedgerSourceError
from services.financial.statement_checks import StatementCheckError
from tests import test_financial_duplicates as fixture
from routers import financial_ledger as router

class StatementSourceTests(fixture.DuplicateTestCase):
    def setUp(self):
        super().setUp()
        from postgres.models.financial_candidates import FinancialCandidateFinalization
        FinancialCandidateFinalization.__table__.create(self.engine, checkfirst=True)
        self.document = self.make_copy()
        self.period = self.db.scalar(select(FinancialStatementPeriod))
        self.file = self.db.get(EvidenceFile, self.document.evidence_file_id)
    def read(self, **changes):
        return statement_source(self.db, **{'case_id':self.case.id,'period_id':self.period.id,**changes})
    def test_citation_is_read_only_without_invented_page(self):
        result=self.read()
        self.assertEqual(result['evidence_file_id'],str(self.file.id))
        self.assertFalse(result['file_bytes_verified'])
        self.assertNotIn('page',result)
        self.assertNotIn('stored_path',result)
        self.assertFalse(self.db.dirty or self.db.new)
    def test_other_case_is_not_disclosed(self):
        with self.assertRaises(LedgerSourceError) as ctx:self.read(case_id=self.other_case.id)
        self.assertEqual(ctx.exception.status_code,404)
    def test_cross_case_links_are_not_disclosed(self):
        for linked in (self.document,self.file):
            original=linked.case_id;linked.case_id=self.other_case.id;self.db.commit()
            with self.assertRaises(LedgerSourceError):self.read()
            linked.case_id=original;self.db.commit()
    def test_cross_case_account_is_not_disclosed(self):
        self.period.account_id=self.other_account.id;self.db.commit()
        with self.assertRaises(LedgerSourceError):self.read()
    def test_digest_mismatch_and_invalid_equal_digests_are_refused(self):
        self.file.sha256='f'*64;self.db.commit()
        with self.assertRaises(LedgerSourceError):self.read()
        self.file.sha256=self.document.sha256_at_ingestion='invalid';self.db.commit()
        with self.assertRaises(LedgerSourceError):self.read()

class StatementRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_check_scope_and_safe_error(self):
        db=Mock()
        with patch.object(router,'capture_statement_checks',return_value={'applied':False}) as read:
            self.assertEqual(await router.get_statement_checks('case',25,db),{'applied':False})
        read.assert_called_once_with(db.get_bind(),case_id='case',offset=25)
        with patch.object(router,'capture_statement_checks',side_effect=StatementCheckError('Scope mismatch')):
            with self.assertRaises(HTTPException) as ctx:await router.get_statement_checks('case',0,db)
        self.assertEqual(ctx.exception.status_code,422)
    async def test_source_scope_and_status(self):
        with patch.object(router,'statement_source',return_value={}) as read:
            await router.get_statement_source('period','case','db')
        read.assert_called_once_with('db',case_id='case',period_id='period')
        with patch.object(router,'statement_source',side_effect=LedgerSourceError('Missing',404)):
            with self.assertRaises(HTTPException) as ctx:await router.get_statement_source('period','case','db')
        self.assertEqual(ctx.exception.status_code,404)
