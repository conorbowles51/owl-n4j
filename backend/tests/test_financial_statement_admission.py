from copy import deepcopy
from unittest import TestCase
from uuid import UUID, uuid4
from sqlalchemy import select
from tests import test_financial_statement_import as fixtures
from tests.financial_reconciled_fixture import install_reconciled_source
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_admission import assess_admission, require_admission
from services.financial.statement_check_request import StatementCheckRequest, check_statement_request
from services.financial.import_batches import assess, initial_request
from services.financial.account_history import account_history
from services.financial.pdf_candidates import PdfMappingError
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialStatementPeriod


class StatementAdmissionTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests(); self.f.setUp()
        install_reconciled_source(self.f)
    def tearDown(self): self.f.tearDown()
    def request(self): return StatementImportRequest.model_validate(initial_request(self.f.preview()))

    def test_reconciled_individual_and_batch_share_rule_and_history(self):
        proposal = self.f.preview(); request=self.request()
        self.assertTrue(assess(proposal, request.model_dump())[1]['can_import'])
        result=self.f.confirm(request.model_dump()); self.assertEqual(result['transaction_count'],12)
        self.assertFalse(self.f.confirm(request.model_dump())['created'])
        with self.f.SessionLocal() as db:
            history=account_history(db,case_id=self.f.case.id)
            period=history['groups'][0]['periods'][0]
            self.assertEqual(period['status'],'reconciled')
            self.assertEqual(period['closing_minor'],'4745000')
            self.assertEqual(sum(a['count'] for a in period['activity']),12)
            self.assertFalse(account_history(db,case_id=uuid4())['groups'])

    def test_difference_cannot_be_waived_and_writes_nothing(self):
        proposal=self.f.preview(); raw=self.request().model_dump()
        closing=next(r for r in raw['rows'] if r['description'].lower()=='closing balance')
        closing['balance_minor']='1'
        from services.financial.review_arithmetic import check_proposed_rows
        raw.update(balance_exception_reason='The source is wrong.',balance_exception_revision=check_proposed_rows(proposal,raw['rows'])['checks_revision'])
        self.assertFalse(assess(proposal,raw)[1]['can_import'])
        with self.assertRaisesRegex(PdfMappingError,'no payments were imported'):self.f.confirm(raw)
        with self.f.SessionLocal() as db:self.assertFalse(list(db.scalars(select(FinancialTransaction))))

    def test_missing_balance_or_payment_and_unknown_dates_are_blockers(self):
        for kind in ('balance','amount','dates'):
            with self.subTest(kind=kind):
                raw=self.request().model_dump()
                if kind=='balance':next(r for r in raw['rows'] if r['description'].lower()=='closing balance')['balance_minor']=None
                elif kind=='amount':next(r for r in raw['rows'] if not r['excluded'])['amount_minor']=''
                else:raw['period_end']=''
                self.assertFalse(assess(self.f.preview(),raw)[1]['can_import'])
                with self.assertRaises(PdfMappingError):self.f.confirm(raw)

    def test_equal_balances_need_review_and_confirmation_expires_after_edit(self):
        install_reconciled_source(self.f,quiet=True)
        raw=self.request().model_dump(); proposal=self.f.preview()
        first=assess_admission(proposal,StatementImportRequest.model_validate(raw))
        self.assertEqual([p['kind'] for p in first['blockers']],['no_activity'])
        raw.update(no_activity_confirmed=True,no_activity_revision=first['revision'])
        self.assertTrue(assess_admission(proposal,StatementImportRequest.model_validate(raw))['can_import'])
        changed={**raw,'period_end':'2023-12-30'}
        self.assertFalse(assess_admission(proposal,StatementImportRequest.model_validate(changed))['can_import'])
        saved=self.f.confirm(raw);self.assertEqual(saved['transaction_count'],0)
        with self.f.SessionLocal() as db:
            period=account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]
            self.assertEqual(period['status'],'confirmed_no_activity')
            self.assertEqual(period['opening_minor'],period['closing_minor'])
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))
            stored=db.get(FinancialStatementPeriod,UUID(period['id']));stored.closing_balance_minor+=1;db.commit()
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'needs_review')

    def test_old_import_is_retained_but_not_asserted_verified(self):
        saved=self.f.confirm(self.request().model_dump())
        with self.f.SessionLocal() as db:
            document=db.get(FinancialSourceDocument,UUID(saved['source_document_id']))
            metadata=dict(document.metadata_);metadata.pop('statement_admission');document.metadata_=metadata;db.commit()
            period=account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]
            self.assertEqual((period['status'],period['transaction_count']),('needs_review',12))

    def test_checks_contract_accepts_unfinished_amount_and_returns_correction(self):
        raw=self.request().model_dump()
        fields=('expected_revision','statement_id','currency','holder','institution','account_number','period_start','period_end','rows')
        raw={k:raw[k] for k in fields}
        for row in raw['rows']:row.pop('date_values',None)
        next(r for r in raw['rows'] if not r['excluded'])['amount_minor']=''
        result=check_statement_request(self.f.preview(),StatementCheckRequest.model_validate(raw))
        self.assertFalse(result['admission']['can_import'])
        self.assertTrue(any(p.get('field')=='amount' for p in result['admission']['blockers']))

    def test_legacy_corrections_are_saved_then_promoted_together_after_reconciliation(self):
        from services.financial.imported_records import complete_record, CompleteImportedRecord, imported_records
        from services.financial.pdf_candidates import _digest
        request=self.request().model_dump(); saved=self.f.confirm(request)
        repaired=[r for r in request['rows'] if not r['excluded']][:2]
        with self.f.SessionLocal() as db:
            document=db.get(FinancialSourceDocument,UUID(saved['source_document_id']))
            metadata=deepcopy(document.metadata_)
            rows=list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id==document.id)))
            target_ids={r['id'] for r in repaired}
            # Emulate a pre-policy import with two retained, unadmitted readings.
            for tx in rows:
                if tx.provenance['statement_import_original']['id'] in target_ids:
                    tx.ledger_status='superseded';tx.superseded_by_id=next(t.id for t in rows if t.provenance['statement_import_original']['id'] not in target_ids)
            originals={r['id']:r for r in metadata['statement_import_original']['rows']}
            metadata['statement_incomplete_records']=[]
            for row in metadata['statement_import_request']['rows']:
                if row['id'] in target_ids:
                    row['amount_minor']=''
                    metadata['statement_incomplete_records'].append(dict(id=row['id'],fields=deepcopy(row),original=originals[row['id']],missing_fields=['amount'],version=0))
            metadata['statement_import_request_sha256']=_digest(metadata['statement_import_request'])
            metadata.pop('statement_admission',None);document.metadata_=metadata;db.commit()
        args=dict(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=UUID(saved['source_document_id']),actor=self.f.actor)
        first=complete_record(**args,request=CompleteImportedRecord(row=repaired[0],currency='EUR',version=0))
        self.assertTrue(first['pending_reconciliation'])
        with self.f.SessionLocal() as db:
            records=imported_records(db,case_id=self.f.case.id)['records']
            self.assertEqual(next(r for r in records if r['id']==repaired[0]['id'])['fields']['amount_minor'],repaired[0]['amount_minor'])
        second=complete_record(**args,request=CompleteImportedRecord(row=repaired[1],currency='EUR',version=0))
        self.assertFalse(second['pending_reconciliation'])
        with self.f.SessionLocal() as db:
            period=account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]
            self.assertEqual((period['status'],period['transaction_count']),('reconciled',12))

    def test_unverified_balances_save_without_claiming_no_activity(self):
        install_reconciled_source(self.f, quiet=True)
        saved = self.f.confirm(self.request().model_dump())
        self.assertEqual(saved['transaction_count'], 0)
        with self.f.SessionLocal() as db:
            period = account_history(db, case_id=self.f.case.id)['groups'][0]['periods'][0]
            self.assertEqual(period['status'], 'needs_review')
            self.assertEqual(period['closing_minor'], period['opening_minor'])
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        with self.f.SessionLocal() as db:
            source=UUID(saved['source_document_id']);view=read_statement_details(db,case_id=self.f.case.id,source_id=source)
            update_statement_details(db,case_id=self.f.case.id,source_id=source,actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'],no_activity_confirmed=True,
                    **{key:view['details'][key] for key in ('holder','account_number','institution')}))
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'confirmed_no_activity')

    def test_manual_additions_wait_for_complete_statement_then_promote_once(self):
        from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
        from services.financial.statement_details import read_statement_details
        from services.financial.imported_records import imported_records
        saved = self.f.confirm(self.request().model_dump()); source=UUID(saved['source_document_id'])
        def request(direction):
            with self.f.SessionLocal() as db:
                revision=read_statement_details(db,case_id=self.f.case.id,source_id=source)['revision']
            identity=uuid4()
            return ManualStatementPayment(request_id=identity,expected_revision=revision,row=dict(
                id='manual:'+str(identity), manual_page=1, date='2023-12-31', description='Synthetic offsetting payment',
                amount_minor='100',direction=direction))
        def save(req):return append_payment(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=source,request=req,actor=self.f.actor)
        first=request('credit'); result=save(first)
        self.assertTrue(result['pending_reconciliation'])
        self.assertFalse(save(first)['created'])
        with self.f.SessionLocal() as db:
            self.assertEqual(len(imported_records(db,case_id=self.f.case.id)['records']),1)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),12)
        second=request('debit'); result=save(second)
        self.assertFalse(result['pending_reconciliation'])
        self.assertFalse(save(second)['created'])
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),14)
            self.assertEqual(imported_records(db,case_id=self.f.case.id)['records'],[])
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'reconciled')

    def test_details_reconcile_final_balances_before_promoting_saved_entry(self):
        from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        saved=self.f.confirm(self.request().model_dump());source=UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:view=read_statement_details(db,case_id=self.f.case.id,source_id=source)
        identity=uuid4()
        result=append_payment(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=source,actor=self.f.actor,
            request=ManualStatementPayment(request_id=identity,expected_revision=view['revision'],row=dict(id='manual:'+str(identity),manual_page=1,
                date='2023-12-31',description='Synthetic missing incoming payment',amount_minor='100',direction='credit')))
        self.assertTrue(result['pending_reconciliation'])
        with self.f.SessionLocal() as db:
            view=read_statement_details(db,case_id=self.f.case.id,source_id=source)
            update_statement_details(db,case_id=self.f.case.id,source_id=source,actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **{key:view['details'][key] for key in ('holder','account_number','institution')}, closing=dict(amount_minor='4745100',page=1)))
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),13)
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'reconciled')
