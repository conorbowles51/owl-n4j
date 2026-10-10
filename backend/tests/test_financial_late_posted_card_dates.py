"""Saved late-posted card charges: the printed date just before the cycle is
proposed and kept only when the statement reconciles (synthetic fixture)."""
from copy import deepcopy
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID
from sqlalchemy import select
from tests import test_financial_statement_import as fixtures
from tests.financial_reconciled_fixture import install_reconciled_source
from services.financial.statement_import import StatementImportRequest
from services.financial.import_batches import initial_request
from services.financial.pdf_candidates import _digest
from services.financial import late_posted_card_dates as late
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialStatementPeriod



class LatePostedCardDateTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests(); self.f.setUp()
        install_reconciled_source(self.f)

    def tearDown(self): self.f.tearDown()

    def _saved_undated(self, *, days_before=1, amount_delta=0):
        request = StatementImportRequest.model_validate(initial_request(self.f.preview())).model_dump()
        saved = self.f.confirm(request); source = UUID(saved['source_document_id'])
        target = [r for r in request['rows'] if not r['excluded']][0]
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == source))
            printed = period.period_start - timedelta(days=days_before)
            # The fixture period is a whole year, so the printed date carries its year.
            text = f'{printed.month:02d}/{printed.day:02d}/{printed.year}'
            metadata = deepcopy(document.metadata_)
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == source)))
            tx = next(t for t in rows if t.provenance['statement_import_original']['id'] == target['id'])
            tx.ledger_status = 'superseded'; tx.superseded_by_id = next(t.id for t in rows if t is not tx)
            original = deepcopy(next(r for r in metadata['statement_import_original']['rows'] if r['id'] == target['id']))
            original['issues'] = [late.DATE_ISSUE]
            original['layout_context'] = dict(date_source=dict(expected_text=text), posting_date_source=None)
            for row in metadata['statement_import_request']['rows']:
                if row['id'] == target['id']:
                    row['date'] = ''
                    row['amount_minor'] = str(int(row['amount_minor']) + amount_delta)
                    metadata['statement_incomplete_records'] = [dict(id=row['id'], fields=deepcopy(row),
                        original=original, missing_fields=['date'], version=0)]
            metadata['statement_import_request_sha256'] = _digest(metadata['statement_import_request'])
            metadata.pop('statement_admission', None); document.metadata_ = metadata; db.commit()
        return source, target, printed

    def _listing(self):
        from services.financial.imported_records import imported_records
        with self.f.SessionLocal() as db:
            return imported_records(db, case_id=self.f.case.id)['records']

    def _admit(self, source):
        from services.financial.imported_records import admit_ready_records
        return admit_ready_records(session_factory=self.f.SessionLocal, case_id=self.f.case.id, source_id=source, actor=self.f.actor)

    def _record(self, source):
        with self.f.SessionLocal() as db:
            return db.get(FinancialSourceDocument, source).metadata_['statement_incomplete_records'][0]

    def test_printed_date_just_before_the_cycle_enters_when_the_statement_reconciles(self):
        source, target, printed = self._saved_undated()
        [listed] = self._listing()
        self.assertEqual(listed['missing_fields'], ['date'])
        self.assertTrue(listed['can_enter_now'])
        self.assertEqual(listed['proposed_date']['date'], printed.isoformat())
        self.assertEqual(self._admit(source)['admitted'], 1)
        record = self._record(source)
        self.assertEqual(record['completed_by_rule']['rule'], late.RULE)
        self.assertEqual(record['correction']['date'], printed.isoformat())
        with self.f.SessionLocal() as db:
            tx = db.get(FinancialTransaction, UUID(record['resolved_transaction_id']))
            self.assertEqual(tx.ledger_status, 'admitted')
            self.assertEqual((tx.transaction_date or tx.effective_date).isoformat(), printed.isoformat())
        self.assertEqual(self._listing(), [])

    def test_a_proposal_that_does_not_reconcile_leaves_the_record_untouched(self):
        source, _target, _printed = self._saved_undated(amount_delta=100)
        [listed] = self._listing()
        self.assertFalse(listed['can_enter_now'])
        self.assertIsNone(listed['proposed_date'])
        self.assertEqual(self._admit(source)['admitted'], 0)
        record = self._record(source)
        self.assertEqual((record['missing_fields'], record.get('correction'), record.get('hold_reason')), (['date'], None, None))

    def test_more_than_one_cycle_before_or_rule_off_proposes_nothing(self):
        source, _target, _printed = self._saved_undated(days_before=40)
        self.assertFalse(self._listing()[0]['can_enter_now'])
        self.assertEqual(self._admit(source)['admitted'], 0)
        with patch.object(late, 'LATE_POSTED_CARD_DATES', False):
            record = self._record(source)
            self.assertIsNone(late.proposed_date(record, '2024-01-01', '2024-01-31'))
