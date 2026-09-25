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

    def test_exact_difference_and_correction_destination_survive_admission(self):
        raw = self.request().model_dump()
        closing = next(row for row in raw['rows'] if row['description'].lower() == 'closing balance')
        closing['balance_minor'] = '4745001'
        assessment = assess_admission(self.f.preview(), StatementImportRequest.model_validate(raw))
        calculation = assessment['calculation']
        self.assertTrue(calculation['available'])
        self.assertEqual(calculation['opening_minor'], '1245000')
        self.assertEqual(calculation['calculated_closing_minor'], '4745000')
        self.assertEqual(calculation['printed_closing_minor'], '4745001')
        self.assertEqual(calculation['difference_minor'], '-1')
        problem = next(problem for problem in assessment['blockers'] if problem.get('check') == 'closing_balance')
        self.assertEqual((problem['expected_minor'], problem['printed_minor'], problem['difference_minor']), ('4745000', '4745001', '-1'))
        self.assertEqual(problem['target'], dict(kind='balance', row_id=closing['id'], field='balance', page=1))
        self.assertEqual(len(problem['reason_id']), 64)

    def test_incomplete_amount_is_unknown_not_zero_and_names_invalid_character(self):
        raw = self.request().model_dump()
        fields = ('expected_revision','statement_id','currency','holder','institution','account_number','period_start','period_end','rows')
        raw = {key: raw[key] for key in fields}
        row = next(row for row in raw['rows'] if not row['excluded'])
        row['amount_minor'] = '12\u200b00'
        checked = check_statement_request(self.f.preview(), StatementCheckRequest.model_validate(raw))['admission']
        self.assertFalse(checked['calculation']['available'])
        self.assertIsNone(checked['calculation']['difference_minor'])
        self.assertIsNone(checked['calculation']['credit_minor'])
        problem = next(problem for problem in checked['blockers'] if problem.get('field') == 'amount')
        self.assertEqual(problem['invalid_characters'], ['U+200B'])
        self.assertEqual(problem['target']['row_id'], row['id'])
        self.assertEqual(problem['target']['kind'], 'transaction_field')

    def test_saved_projection_detects_stale_success_without_writing_or_querying_preloaded_rows(self):
        from unittest.mock import patch
        from services.financial.saved_statement_admission import current_saved_assessment
        saved = self.f.confirm(self.request().model_dump())
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, UUID(saved['source_document_id']))
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == document.id))
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document.id)))
            before = deepcopy(document.metadata_)
            self.assertTrue(current_saved_assessment(db, document, period, transactions=rows)['can_import'])
            rows[0].description = 'Synthetic later change outside the reviewed snapshot'
            with patch.object(db, 'scalars', side_effect=AssertionError('Preloaded rows must not be queried again')):
                result = current_saved_assessment(db, document, period, transactions=rows)
            self.assertFalse(result['can_import'])
            self.assertFalse(result['assessment_current'])
            self.assertTrue(any(problem['kind'] == 'assessment_stale' for problem in result['blockers']))
            self.assertEqual(document.metadata_, before)
            self.assertEqual(len(rows), 12)

    def test_saved_projection_refuses_changed_source_and_wrong_currency_without_dropping_rows(self):
        from services.financial.saved_statement_admission import current_saved_assessment
        saved = self.f.confirm(self.request().model_dump())
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, UUID(saved['source_document_id']))
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == document.id))
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document.id)))
            rows[0].currency = 'USD'
            result = current_saved_assessment(db, document, period, transactions=rows)
            self.assertFalse(result['can_import'])
            self.assertTrue(any(problem['kind'] == 'saved_rows' for problem in result['blockers']))
            rows[0].currency = period.currency
            previous_provenance = rows[1].provenance
            rows[1].provenance = deepcopy(rows[0].provenance)
            result = current_saved_assessment(db, document, period, transactions=rows)
            self.assertFalse(result['can_import'])
            self.assertTrue(any('same source reading' in problem['message'] for problem in result['blockers']))
            rows[1].provenance = previous_provenance
            changed = deepcopy(document.metadata_)
            changed['statement_import_original']['revision'] = 'a' * 64
            document.metadata_ = changed
            result = current_saved_assessment(db, document, period, transactions=rows)
            self.assertFalse(result['can_import'])
            self.assertFalse(result['assessment_current'])
            self.assertEqual(result['blockers'][0]['kind'], 'saved_source')
            self.assertEqual(len(rows), 12)

    def test_saved_corrections_refresh_current_checks_and_preserve_ledger_history(self):
        from services.financial.corrections import correct_transaction
        from services.financial.duplicate_decisions import duplicate_revision
        from services.financial.statement_details import read_statement_details
        saved = self.f.confirm(self.request().model_dump())
        source_id = UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source_id)
            original = db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == source_id))
            original_amount = original.amount_minor
            original_ref = original.ref_id
            result = correct_transaction(db, case_id=self.f.case.id, transaction_id=original.id,
                amount_minor=original_amount + 1, direction=original.direction,
                expected_revision=duplicate_revision(db, document), actor=self.f.actor, reason='Synthetic verified amount correction')
            view = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
            self.assertFalse(view['admission']['can_import'])
            self.assertTrue(any(problem.get('check') == 'closing_balance' for problem in view['admission']['blockers']))
            self.assertEqual(document.metadata_['statement_import_issues'], view['admission']['blockers'])
            self.assertEqual((original.amount_minor, original.ref_id), (original_amount, original_ref))
            corrected = db.get(FinancialTransaction, UUID(result['replacement_id']))
            correct_transaction(db, case_id=self.f.case.id, transaction_id=corrected.id,
                amount_minor=original_amount, direction=corrected.direction,
                expected_revision=duplicate_revision(db, document), actor=self.f.actor, reason='Synthetic second correction')
            reopened = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
            self.assertTrue(reopened['admission']['can_import'])
            self.assertEqual(reopened['admission']['blockers'], [])
            self.assertEqual(document.metadata_['statement_import_issues'], [])
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.superseded_by_id.is_(None))))), 12)

    def test_unchanged_saved_quiet_confirmation_survives_reopen_and_second_save(self):
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        install_reconciled_source(self.f, quiet=True)
        saved = self.f.confirm(self.request().model_dump())
        with self.f.SessionLocal() as db:
            source_id = UUID(saved['source_document_id'])
            for confirm in (True, False):
                view = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
                view = update_statement_details(db, case_id=self.f.case.id, source_id=source_id, actor=self.f.actor,
                    request=StatementDetailsRequest(expected_revision=view['revision'], no_activity_confirmed=confirm,
                        **{key: view['details'][key] for key in ('holder','account_number','institution')}))
                self.assertEqual(view['admission']['status'], 'confirmed_no_activity')
            changed = update_statement_details(db, case_id=self.f.case.id, source_id=source_id, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], period_end='2023-12-30',
                    **{key: view['details'][key] for key in ('holder','account_number','institution')}))
            self.assertFalse(changed['admission']['no_activity_confirmed'])
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))

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
        last_printed = next(row['id'] for row in reversed(self.f.preview()['rows']) if not row['excluded'])
        def request(direction):
            with self.f.SessionLocal() as db:
                revision=read_statement_details(db,case_id=self.f.case.id,source_id=source)['revision']
            identity=uuid4()
            return ManualStatementPayment(request_id=identity,expected_revision=revision,row=dict(
                id='manual:'+str(identity), manual_page=1, date='2023-12-31', description='Synthetic offsetting payment',
                amount_minor='100',direction=direction, source_order_anchor=dict(relation='after', row_id=last_printed)))
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

    def test_saved_unread_page_addition_can_be_corrected_then_promoted_without_losing_position(self):
        from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
        from services.financial.statement_details import read_statement_details
        from services.financial.imported_records import CompleteImportedRecord, complete_record, imported_records
        from services.financial.pdf_candidates import _digest
        saved = self.f.confirm(self.request().model_dump()); source=UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            metadata = deepcopy(document.metadata_)
            metadata['statement_import_original']['statement_page_numbers'] = [1, 2]
            metadata['statement_import_original']['page_numbers'] = [1, 2, 3]
            metadata['statement_import_original_sha256'] = _digest(metadata['statement_import_original'])
            document.metadata_ = metadata; db.commit()
            context = read_statement_details(db, case_id=self.f.case.id, source_id=source, include_positions=True)
            existing = {row.id: row.ref_id for row in db.scalars(select(FinancialTransaction))}
        anchor = dict(relation='after', row_id=context['source_position_rows'][-1]['id'])
        args = dict(session_factory=self.f.SessionLocal, case_id=self.f.case.id, source_id=source, actor=self.f.actor)
        def request(direction):
            with self.f.SessionLocal() as db:
                revision=read_statement_details(db,case_id=self.f.case.id,source_id=source)['revision']
            identity=uuid4()
            return ManualStatementPayment(request_id=identity,expected_revision=revision,row=dict(
                id='manual:'+str(identity), manual_page=2, date='2023-12-31', description='Missed payment on unread page',
                amount_minor='100', direction=direction, source_order_anchor=anchor))
        incoming = request('credit')
        self.assertTrue(append_payment(**args, request=incoming)['pending_reconciliation'])
        replayed_addition = append_payment(**args, request=incoming)
        self.assertFalse(replayed_addition['created'])
        self.assertTrue(replayed_addition['pending_reconciliation'])
        self.assertTrue(replayed_addition['blockers'])
        with self.f.SessionLocal() as db:
            pending_records = imported_records(db, case_id=self.f.case.id)
            self.assertEqual(pending_records['total'], 1)
            retained = pending_records['records'][0]
        corrected = {**retained['fields'], 'description': 'Corrected source description'}
        correction = CompleteImportedRecord(row=corrected, version=retained['version'], currency='EUR')
        self.assertTrue(complete_record(**args, request=correction)['pending_reconciliation'])
        replay = complete_record(**args, request=correction)
        self.assertTrue(replay['pending_reconciliation'])
        self.assertFalse(replay['created'])
        self.assertTrue(replay['blockers'])
        with self.f.SessionLocal() as db:
            again = imported_records(db, case_id=self.f.case.id)['records'][0]
            self.assertEqual(again['version'], retained['version'] + 1)
            self.assertEqual(again['fields']['source_order_anchor'], anchor)
            self.assertEqual(again['fields']['manual_page'], 2)
        outgoing = request('debit')
        self.assertFalse(append_payment(**args, request=outgoing)['pending_reconciliation'])
        self.assertFalse(append_payment(**args, request=outgoing)['created'])
        with self.f.SessionLocal() as db:
            current = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual({row.id: row.ref_id for row in current if row.id in existing}, existing)
            self.assertEqual(len(current), len(existing) + 2)
            additions = [row for row in current if row.id not in existing]
            self.assertTrue(all(row.provenance['statement_import_review']['source_order_anchor'] == anchor for row in additions))
            self.assertTrue(all(row.provenance['statement_import_original']['page_number'] == 2 for row in additions))
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'reconciled')

    def test_saved_record_completion_rejects_tampered_sealed_source_before_saving(self):
        from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
        from services.financial.statement_details import read_statement_details
        from services.financial.imported_records import CompleteImportedRecord, complete_record, imported_records
        saved=self.f.confirm(self.request().model_dump()); source=UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:
            revision=read_statement_details(db,case_id=self.f.case.id,source_id=source)['revision']
        identity=uuid4()
        args=dict(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=source,actor=self.f.actor)
        append_payment(**args,request=ManualStatementPayment(request_id=identity,expected_revision=revision,row=dict(
            id='manual:'+str(identity),manual_page=1,date='2023-12-31',description='Unfinished source payment',amount_minor='100',direction='credit')))
        with self.f.SessionLocal() as db:
            retained=imported_records(db,case_id=self.f.case.id)['records'][0]
            document=db.get(FinancialSourceDocument,source);metadata=deepcopy(document.metadata_)
            metadata['statement_import_original']['revision']='f'*64
            document.metadata_=metadata;db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'cannot be verified'):
            complete_record(**args,request=CompleteImportedRecord(row={**retained['fields'],'description':'Must not save'},
                version=retained['version'],currency='EUR'))
        with self.f.SessionLocal() as db:
            again=imported_records(db,case_id=self.f.case.id)['records'][0]
            self.assertEqual(again['fields']['description'],'Unfinished source payment')
            self.assertEqual(again['version'],retained['version'])

    def test_details_reconcile_final_balances_before_promoting_saved_entry(self):
        from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        saved=self.f.confirm(self.request().model_dump());source=UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:view=read_statement_details(db,case_id=self.f.case.id,source_id=source)
        identity=uuid4()
        last_printed = next(row['id'] for row in reversed(self.f.preview()['rows']) if not row['excluded'])
        result=append_payment(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=source,actor=self.f.actor,
            request=ManualStatementPayment(request_id=identity,expected_revision=view['revision'],row=dict(id='manual:'+str(identity),manual_page=1,
                date='2023-12-31',description='Synthetic missing incoming payment',amount_minor='100',direction='credit',
                source_order_anchor=dict(relation='after', row_id=last_printed))))
        self.assertTrue(result['pending_reconciliation'])
        with self.f.SessionLocal() as db:
            view=read_statement_details(db,case_id=self.f.case.id,source_id=source)
            update_statement_details(db,case_id=self.f.case.id,source_id=source,actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **{key:view['details'][key] for key in ('holder','account_number','institution')}, closing=dict(amount_minor='4745100',page=1)))
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),13)
            self.assertEqual(account_history(db,case_id=self.f.case.id)['groups'][0]['periods'][0]['status'],'reconciled')
