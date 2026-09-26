import asyncio
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock
from uuid import uuid4, UUID
from sqlalchemy import select
from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.evidence import EvidenceFolder, IngestionLog
from services.financial import import_batches as service
from services.financial.statement_import import StatementImportRequest, StatementReviewDraft
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import import StatementImportTests as Fixture


class BatchImportTests(TestCase):
    def test_choose_unknown_currency_and_repeat_after_lost_response(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        # No explicit symbols: an unknown-currency statement must be reparsed
        # after selection. Euro-prefixed fixture values deliberately reject USD.
        from postgres.models.evidence import EvidenceTableGeometry
        import json
        with self.f.SessionLocal() as db:
            geometry = db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == self.f.file.id))
            geometry.payload = json.loads(json.dumps(geometry.payload, ensure_ascii=False).replace('€', ''))
            db.commit()
        with patch('services.financial.statement_currency.detect_statement_currency', return_value=''):
            batch = self.create(); self.advance(batch)
            with self.f.SessionLocal() as db:
                item = db.scalar(select(Item).where(Item.batch_id == batch))
                self.assertEqual(item.summary['currency'], '')
                selection = SimpleNamespace(id=item.id, revision=service.currency_revision(item))
                request_id = uuid4()
                first = service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=[selection], currency='USD', actor=self.f.actor, request_id=request_id)
                repeated = service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=[selection], currency='USD', actor=self.f.actor, request_id=request_id)
                self.assertEqual(first['updated'], 1)
                self.assertTrue(repeated['already_applied'])
                self.assertEqual(item.review_request['currency'], 'USD')
                self.assertEqual(len(item.summary['currency_history']), 1)
                self.assertEqual(item.summary['transaction_count'], 12)
                with self.assertRaisesRegex(PdfMappingError, 'different changes'):
                    service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                        selections=[selection], currency='EUR', actor=self.f.actor, request_id=request_id)
        self.assertEqual(self.f.preview()['currency'], 'USD')

    def test_reason_counts_filters_and_navigation_cover_the_whole_batch(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            original = db.scalar(select(Item).where(Item.batch_id == batch))
            added = []
            for number in range(101):
                extra = Item(id=uuid4(), batch_id=batch, file_id=original.file_id,
                    statement_key=f'synthetic-period-{number}', status='attention',
                    summary={**original.summary, 'filename': f'{number:03d}-synthetic.pdf', 'holder': '',
                        'problems': [dict(kind='statement_detail', field='holder', row_id=None, message='The account holder has not been identified.')], 'problem_count': 1})
                db.add(extra); added.append(extra)
            db.commit()
            first = service.batch_status(db, case_id=self.f.case.id, batch_id=batch, review_group='holder', limit=100)
            self.assertEqual(first['total'], 101)
            self.assertEqual(len(first['items']), 100)
            self.assertEqual(next(g for g in first['review_summary']['groups'] if g['id']=='holder')['statement_count'], 101)
            self.assertEqual(first['review_group_label'], 'Missing account holder')
            self.assertEqual(first['items'][0]['problems'][0]['review_reason'], 'holder')
            self.assertNotIn('review_reason', added[0].summary['problems'][0])
            second = service.batch_status(db, case_id=self.f.case.id, batch_id=batch, review_group='holder', offset=100)
            self.assertEqual(len(second['items']), 1)
            self.assertEqual(second['review_summary'], first['review_summary'])
            self.assertEqual(service.next_statement(db, case_id=self.f.case.id, batch_id=batch,
                item_id=added[0].id, review_group='holder')['item_id'], str(added[1].id))
            added[0].summary = {**added[0].summary, 'holder': 'Reviewed synthetic holder', 'problems': [], 'problem_count': 0}
            db.commit()
            self.assertEqual(service.next_statement(db, case_id=self.f.case.id, batch_id=batch,
                item_id=added[0].id, review_group='holder')['item_id'], str(added[1].id))
            remaining = service.batch_status(db, case_id=self.f.case.id, batch_id=batch, review_group='holder')
            self.assertEqual(remaining['total'], 100)
            self.assertEqual(next(g for g in remaining['review_summary']['groups'] if g['id']=='holder')['statement_count'], 100)
            added[1].summary = {**added[1].summary, 'problem_count': 2, 'problems': [
                dict(kind='reading', row_id='other-row', message='Check an unrelated row.'),
                *added[1].summary['problems']]}
            db.commit()
            next_problem = service.next_problem(db, case_id=self.f.case.id, batch_id=batch,
                item_id=added[0].id, review_group='holder')
            self.assertEqual(next_problem['item_id'], str(added[1].id))
            self.assertIsNone(next_problem['row_id'])
            with self.assertRaises(PdfMappingError):
                service.batch_status(db, case_id=uuid4(), batch_id=batch, review_group='holder')

    def test_pending_holder_directory_is_case_scoped_and_explains_unimported_statements(self):
        from services.financial.candidate_store import list_candidate_accounts
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = {**(item.review_request or {}), 'holder': 'Second synthetic company'}
            db.commit()
            state = list_candidate_accounts(db, case_id=self.f.case.id, include_pending=True)
            self.assertIn({'name':'Second synthetic company', 'count':1}, state['pending_holders'])
            self.assertFalse(list_candidate_accounts(db, case_id=uuid4(), include_pending=True)['pending_holders'])
            item.status = 'imported'; db.commit()
            self.assertFalse(list_candidate_accounts(db, case_id=self.f.case.id, include_pending=True)['pending_holders'])

    def test_next_statement_includes_imported_and_skipped_without_wrapping(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            first = db.scalar(select(Item).where(Item.batch_id == batch))
            first.summary = {**first.summary, 'filename': 'A.pdf'}
            first_id = first.id
            second_id = uuid4()
            db.add(Item(id=second_id, batch_id=batch, file_id=first.file_id, statement_key='synthetic-second',
                status='imported', summary={**first.summary, 'filename': 'B.pdf'}))
            db.commit()
            result = service.next_statement(db, case_id=self.f.case.id, batch_id=batch, item_id=first_id)
            self.assertEqual(result['item_id'], str(second_id))
            self.assertEqual(result['position'], 2)
            self.assertIsNone(service.next_statement(db, case_id=self.f.case.id, batch_id=batch, item_id=second_id)['item_id'])
            self.assertEqual(service.next_statement(db, case_id=self.f.case.id, batch_id=batch, item_id=second_id, direction='previous')['item_id'], str(first_id))

    def test_unfinished_navigation_skips_imported_and_decided_without_wrapping(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            first = db.scalar(select(Item).where(Item.batch_id == batch))
            first.summary = {**first.summary, 'filename': 'A.pdf'}
            following = []
            for name, status in [('B.pdf', 'imported'), ('C.pdf', 'skipped'),
                                 ('E.pdf', 'attention')]:
                extra = Item(id=uuid4(), batch_id=batch, file_id=first.file_id,
                    statement_key='synthetic-' + name, status=status,
                    summary={**first.summary, 'filename': name})
                db.add(extra); following.append(extra)
            db.commit()
            result = service.next_statement(db, case_id=self.f.case.id, batch_id=batch,
                item_id=first.id, review_group='unfinished')
            self.assertEqual(result['item_id'], str(following[-1].id))
            self.assertEqual(result['total'], 2)
            self.assertIsNone(service.next_statement(db, case_id=self.f.case.id, batch_id=batch,
                item_id=following[-1].id, review_group='unfinished')['item_id'])
            following[-1].status = 'imported'; db.commit()
            current = service.batch_status(db, case_id=self.f.case.id, batch_id=batch,
                review_group='unfinished')
            self.assertEqual([r['id'] for r in current['items']], [str(first.id)])
            self.assertEqual(current['statement_summary']['imported'], 2)
            saved = service.batch_status(db, case_id=self.f.case.id, batch_id=batch, review_group='saved')
            self.assertEqual(saved['total'], 2)

    def test_missing_prepared_reference_recovers_only_from_case_original(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            original = record.files[0]['source_id']
            files = deepcopy(record.files)
            files[0].update(file_id=str(uuid4()), status='error', error='Statement not found in this case.')
            record.files = files; db.commit()
            status = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(status['files'][0]['review_file_id'], original)
            self.assertIn('original PDF is retained', status['files'][0]['error'])
            service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=UUID(original))
            db.refresh(record)
            self.assertEqual(record.files[0]['file_id'], original)
        self.advance(batch)
        self.assertEqual(self.status(batch)['files'][0]['status'], 'checked')

    def test_retry_failed_file_during_another_worker_turn_preserves_lease(self):
        from postgres.models.evidence import EvidenceFile
        from datetime import datetime, timedelta, timezone
        batch = self.create(); self.advance(batch)
        token = str(uuid4())
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            files = deepcopy(record.files)
            files[0].update(status='error', error='A transient reading failure')
            db.get(EvidenceFile, UUID(files[0]['file_id'])).status = 'failed'
            record.files = files
            record.status = 'preparing'
            record.worker_token = token
            record.lease_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            db.commit()
            result = service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=UUID(files[0]['source_id']))
            self.assertTrue(result['queued'])
            db.refresh(record)
            self.assertEqual(record.worker_token, token)
            self.assertEqual(record.files[0]['status'], 'waiting')
            again = service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=UUID(files[0]['source_id']))
            self.assertFalse(again['queued'])

    def test_retry_recovers_a_checked_file_when_its_prepared_reference_is_missing(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            files = deepcopy(record.files)
            original = UUID(files[0]['source_id'])
            files[0].update(file_id=str(uuid4()), status='checked')
            record.files = files
            db.commit()
            shown = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(shown['files'][0]['status'], 'error')
            self.assertEqual(shown['files'][0]['review_file_id'], str(original))
            result = service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=original)
            self.assertTrue(result['queued'])
            self.assertEqual(result['status'], 'waiting')
            self.assertEqual(result['action'], 'retry_reading')
            self.assertFalse(service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=original)['queued'])
        self.advance(batch)
        shown = self.status(batch)
        self.assertEqual(shown['files'][0]['status'], 'checked')
        self.assertEqual(shown['available_statements'], 1)
        self.assertEqual(shown['ready_transactions'], 12)
        self.assertEqual(len(shown['items']), 1)

    def test_retry_missing_reference_preserves_saved_payments_and_review(self):
        from routers.financial_statement_import import list_financial_batches
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=self.status(batch)['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        with self.f.SessionLocal() as db:
            before = set(db.scalars(select(FinancialTransaction.id)))
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = {**service.initial_request(self.f.preview()), 'holder': 'Investigator reviewed holder'}
            reviewed = deepcopy(item.review_request)
            record = db.get(Batch, batch)
            record.files = [{**record.files[0], 'file_id': str(uuid4()), 'status': 'checked'}]
            db.commit()
            listed = list_financial_batches(case_id=self.f.case.id, db=db)['batches'][0]
            self.assertFalse(listed['completed'])
            self.assertEqual(listed['failed_files'], 1)
            self.assertEqual(listed['checked_files'], 0)
            service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=self.f.file.id)
        self.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(set(db.scalars(select(FinancialTransaction.id))), before)
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            self.assertEqual(item.status, 'imported')
            self.assertEqual(item.review_request, reviewed)
            self.assertEqual(self.status(batch)['files'][0]['status'], 'checked')
            self.assertEqual(list_financial_batches(case_id=self.f.case.id, db=db)['batches'][0]['failed_files'], 0)

    def test_retry_missing_reference_never_uses_another_cases_original(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            foreign = self.f.evidence('f' * 64)
            foreign.case_id = self.f.other_case.id
            self.f.db.commit()
            record.files = [{**record.files[0], 'source_id': str(foreign.id),
                'file_id': str(uuid4()), 'status': 'checked'}]
            db.commit()
            result = service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=foreign.id)
            self.assertFalse(result['queued'])
            self.assertEqual(result['action'], 'source_unavailable')
            self.assertIsNone(result['review_file_id'])
            db.refresh(record)
            self.assertEqual(record.files[0]['status'], 'error')
            self.assertIn('Restore the original in Evidence', record.files[0]['error'])

    def test_retry_failed_engine_reading_submits_once_then_waits_for_completion(self):
        from postgres.models.evidence import EvidenceFile
        batch = self.create()
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            record.files = [{**record.files[0], 'status': 'error', 'error': 'Reading interrupted'}]
            record.status = 'review'
            db.get(EvidenceFile, self.f.file.id).status = 'failed'
            db.commit()
            service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=self.f.file.id)
        async def process(db, **kwargs):
            self.assertEqual(kwargs['preparation_mode'], 'pdf_review')
            self.assertEqual(kwargs['file_ids'], [self.f.file.id])
            db.get(EvidenceFile, self.f.file.id).status = 'processing'
            db.commit()
            return {'job_ids': ['synthetic-retry-job']}
        worker = AsyncMock(side_effect=process)
        asyncio.run(service.advance_batch(self.f.SessionLocal, batch, Path, worker))
        worker.assert_awaited_once()
        self.assertEqual(self.status(batch)['files'][0]['status'], 'processing')
        with self.f.SessionLocal() as db:
            self.assertFalse(service.retry_file(db, case_id=self.f.case.id, batch_id=batch, source_id=self.f.file.id)['queued'])
            db.get(EvidenceFile, self.f.file.id).status = 'processed'
            db.commit()
        self.advance(batch)
        self.assertEqual(self.status(batch)['ready_transactions'], 12)

    def test_check_specific_import_request_before_during_and_after_execution(self):
        from services.financial.import_operations import check_operation
        batch = self.create(); self.advance(batch)
        request_id = uuid4()
        def check(case_id=None):
            with self.f.SessionLocal() as db:
                return check_operation(db, case_id=case_id or self.f.case.id,
                    batch_id=batch, request_id=request_id)
        self.assertIsNone(check()['operation'])
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=self.status(batch)['ready_revision'], actor=self.f.actor, request_id=request_id)
        self.assertEqual(check()['operation']['status'], 'in_progress')
        self.advance(batch)
        self.assertEqual(check()['operation']['transaction_count'], 12)
        self.assertEqual(check()['operation']['status'], 'complete')
        with self.assertRaises(PdfMappingError):
            check(uuid4())

    def test_accepted_import_runs_before_unfinished_pdf_preparation_and_turn_is_bounded(self):
        from unittest.mock import patch
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=self.status(batch)['ready_revision'], actor=self.f.actor)
            record = db.get(Batch, batch)
            record.files = [{**{k: v for k, v in record.files[0].items() if not k.startswith('last_')}, 'status': 'waiting', 'source_id': str(uuid4())} for _ in range(7)]
            db.commit()
        events = []
        actual_import = service._import_item
        def importing(*args):
            events.append('import')
            return actual_import(*args)
        async def preparing(*args, **kwargs):
            events.append('prepare')
            return dict(outcome='processing', evidence_file_id=str(self.f.file.id))
        with patch.object(service, '_import_item', side_effect=importing), patch.object(service, 'prepare_existing_financial_file', side_effect=preparing):
            self.advance(batch)
        self.assertEqual(events[0], 'import')
        self.assertLessEqual(events.count('prepare'), service.FILES_PER_TURN)
        shown = self.status(batch)
        self.assertEqual(shown['operations'][0]['status'], 'complete')
        self.assertEqual(shown['status'], 'preparing')
        self.assertEqual(sum('last_checked_at' in f for f in shown['files']), service.FILES_PER_TURN)

    def test_import_receipt_survives_response_loss_and_reopening_without_duplicates(self):
        from services.financial.batch_transaction_scope import imported_batch_scope
        from postgres.models.financial_import_batches import FinancialImportOperation
        batch = self.create(); self.advance(batch)
        revision = self.status(batch)['ready_revision']
        request_id = uuid4()
        def submit(case_id=None):
            with self.f.SessionLocal() as db:
                return service.queue_import(db, case_id=case_id or self.f.case.id, batch_id=batch,
                    expected_revision=revision, actor=self.f.actor, request_id=request_id)
        first = submit()
        self.assertEqual(submit()['operation']['id'], first['operation']['id'])
        self.advance(batch)
        complete = submit()['operation']
        self.assertEqual(complete['status'], 'complete')
        self.assertEqual(complete['transaction_count'], 12)
        self.assertEqual(self.status(batch)['operations'][0], complete)
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialImportOperation)))), 1)
            result = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=request_id)
            self.assertEqual(result['transaction_count'], 12)
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=uuid4())
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            submit(uuid4())

    def test_failed_import_has_a_durable_actionable_receipt_and_is_not_reoffered(self):
        from unittest.mock import patch
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=self.status(batch)['ready_revision'], actor=self.f.actor)
        with patch.object(service, 'confirm_statement_import', side_effect=PdfMappingError('Check the statement currency.', 409)):
            self.advance(batch)
        shown = self.status(batch)
        self.assertEqual(shown['operations'][0]['status'], 'needs_review')
        self.assertEqual(shown['operations'][0]['outcomes'][0]['message'], 'Check the statement currency.')
        self.assertEqual(shown['available_statements'], 0)
        self.assertEqual(shown['counts']['imported'], 0)

    def test_one_review_saves_payments_and_returns_exact_batch_result_idempotently(self):
        from services.financial.batch_transaction_scope import imported_batch_scope
        from services.financial.transaction_query import list_transactions
        batch = self.create(); self.advance(batch)
        item = self.status(batch)['items'][0]
        raw = service.initial_request(self.f.preview())
        raw['holder'] = 'Reviewed account holder'
        args = dict(session_factory=self.f.SessionLocal, case_id=self.f.case.id, batch_id=batch,
            item_id=UUID(item['id']), request=StatementReviewDraft.model_validate(raw),
            expected_review_revision=service._digest({}), actor=self.f.actor, resolve_path=Path)
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            service.confirm_review(**{**args, 'case_id': uuid4()})
        with self.assertRaisesRegex(PdfMappingError, 'Another user'):
            service.confirm_review(**{**args, 'expected_review_revision': '0'*64})
        receipt = service.confirm_review(**args)
        self.assertEqual(receipt['transaction_count'], 12)
        self.assertEqual(service.confirm_review(**args), receipt)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            scope = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(scope['source_document_ids'], [receipt['source_document_id']])
            self.assertEqual(scope['transaction_count'], 12)
            rows = list_transactions(db, self.f.case.id)
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(str(row.source_document_id) == receipt['source_document_id'] for row in rows))
        changed = {**raw, 'holder': 'Different later edit'}
        with self.assertRaisesRegex(PdfMappingError, 'different values'):
            service.confirm_review(**{**args, 'request': StatementReviewDraft.model_validate(changed)})

    def test_individual_import_updates_an_older_batch_without_resaving_its_bad_draft(self):
        from services.financial.batch_transaction_scope import imported_batch_scope
        batch = self.create(); self.advance(batch)
        item = self.status(batch)['items'][0]
        raw = service.initial_request(self.f.preview())
        with self.f.SessionLocal() as db:
            saved = db.get(Item, UUID(item['id']))
            saved.review_request = {**raw, 'rows': [*raw['rows'], dict(id='manual:bad', manual_page=999)]}
            saved.status = 'attention'
            saved.summary = {**saved.summary, 'can_import':False, 'review_model':service.REVIEW_MODEL,
                'balance_status':'unavailable', 'problems':[dict(message='Old invalid page')], 'problem_count':1}
            db.commit()
        receipt = self.f.confirm(raw)
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        with self.f.SessionLocal() as db:
            source_id = UUID(receipt['source_document_id'])
            details = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
            net = sum(int(row['amount_minor']) * (1 if row['direction'] == 'credit' else -1)
                for row in raw['rows'] if not row['excluded'])
            update_statement_details(db, case_id=self.f.case.id, source_id=source_id, actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=details['revision'],
                    **{key:details['details'][key] for key in ('holder', 'account_number', 'institution')}, opening=dict(amount_minor='0', page=1), closing=dict(amount_minor=str(net), page=1)))
        shown = self.status(batch)
        self.assertEqual(shown['counts']['imported'], 1, shown)
        self.assertEqual(shown['available_statements'], 0)
        self.assertEqual(shown['items'][0]['source_document_id'], receipt['source_document_id'])
        self.assertNotIn('Old invalid page', str(shown['items'][0]['problems']))
        # The edited opening/closing pair adds up, but zeroing the opening
        # conflicts with the first printed running balance. The current batch
        # projection must explain that real issue rather than keep old issues
        # or certify the period from the closing identity alone.
        self.assertEqual(shown['items'][0]['balance_status'], 'difference')
        self.assertEqual(shown['items'][0]['admission']['calculation']['difference_minor'], '0')
        self.assertTrue(any(p.get('check') == 'running_balance' for p in shown['items'][0]['problems']))
        with self.f.SessionLocal() as db:
            scope = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(scope['transaction_count'], 12)
            self.assertEqual(scope['source_document_ids'], [receipt['source_document_id']])
            self.assertEqual(db.get(Item, UUID(item['id'])).status, 'attention')

    def test_refresh_statement_list_keeps_saved_review_and_imports(self):
        batch = self.create(); self.advance(batch)
        item = self.status(batch)['items'][0]
        raw = service.initial_request(self.f.preview())
        raw['holder'] = 'Saved reviewer wording'
        with self.f.SessionLocal() as db:
            service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                service.refresh_statement_list(db, case_id=uuid4(), batch_id=batch)
            self.assertEqual(service.refresh_statement_list(db, case_id=self.f.case.id, batch_id=batch)['files'], 1)
            self.assertTrue(service.refresh_statement_list(db, case_id=self.f.case.id, batch_id=batch)['already_processing'])
        self.advance(batch)
        status = self.status(batch)
        self.assertEqual(status['items'][0]['holder'], raw['holder'])
        self.assertEqual(status['total'], 1)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        with self.f.SessionLocal() as db:
            service.refresh_statement_list(db, case_id=self.f.case.id, batch_id=batch)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)

    def test_legacy_saved_review_upgrades_and_imports_without_losing_edits(self):
        from unittest.mock import patch
        from services.financial.statement_progress import save_progress
        batch = self.create(); self.advance(batch)
        with patch('services.financial.statement_import.VERSION', 'statement-review-v28'):
            old = self.f.preview()
            raw = service.initial_request(old)
            raw['holder'] = 'Saved investigator correction'
            raw['account_number'] = '00123456789'
            next(row for row in raw['rows'] if not row['excluded'])['description'] = 'Saved description'
            with self.f.SessionLocal() as db:
                save_progress(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                    request=StatementReviewDraft.model_validate(raw), expected_review_revision='initial', actor=self.f.actor)
                item = db.scalar(select(Item).where(Item.batch_id == batch))
                item.review_request = raw
                item.summary = {**item.summary, **service.assess(old, raw)[1], 'review_model': 'older'}
                db.commit()
        current = self.f.preview()
        self.assertNotEqual(current['revision'], old['revision'])
        self.assertEqual(current['saved_review']['request']['expected_revision'], current['revision'])
        self.assertEqual(current['saved_review']['request']['holder'], raw['holder'])
        status = self.status(batch)
        self.assertTrue(status['items'][0]['can_import'])
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            from postgres.models.financial import FinancialSourceDocument
            imported = db.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.document_type == 'statement_review'))
            self.assertEqual(imported.metadata_['statement_import_request']['holder'], raw['holder'])
            self.assertTrue(any(row.description == 'Saved description' for row in db.scalars(select(FinancialTransaction))))

    def test_saved_holder_correction_clears_the_batch_warning_for_balance_only_statement(self):
        batch = self.create(); self.advance(batch)
        item = self.status(batch)['items'][0]
        raw = service.initial_request(self.f.preview())
        for row in raw['rows']:
            row['excluded'] = True
        raw['holder'] = ''
        with self.f.SessionLocal() as db:
            first = service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
            self.assertTrue(any(p.get('field') == 'holder' for p in self.status(batch)['items'][0]['problems']))
            raw['holder'] = 'Manually confirmed holder'
            service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=first['review_revision'])
        saved = self.status(batch)['items'][0]
        self.assertEqual(saved['holder'], raw['holder'])
        self.assertFalse(any(p.get('field') == 'holder' for p in saved['problems']))
        self.assertFalse(saved['can_import'])
        self.assertEqual(saved['transaction_count'], 0)

    def test_bulk_currency_uses_refreshed_reading_for_unreviewed_legacy_batch(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.summary = {**item.summary, 'revision': 'f'*64, 'review_model': 'older'}
            db.commit()
            current = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)['items'][0]
            self.assertNotEqual(current['revision'], 'f'*64)
            service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                selections=[SimpleNamespace(id=item.id, revision=current['currency_revision'])], currency='USD', actor=self.f.actor)
            self.assertEqual(db.get(Item, item.id).review_request['currency'], 'USD')

    def test_bulk_currency_keeps_corrections_reopens_and_imports_in_selected_currency(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            proposal = self.f.preview()
            raw = service.initial_request(proposal)
            raw['account_number'] = '00123456789'
            raw['holder'] = 'Manually checked holder'
            next(r for r in raw['rows'] if not r['excluded'])['description'] = 'Saved wording'
            item.review_request = raw
            db.commit()
            selection = SimpleNamespace(id=item.id, revision=service.currency_revision(item))
            result = service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                selections=[selection], currency='MXN', actor=self.f.actor)
            self.assertEqual(result['updated'], 1)
            db.refresh(item)
            self.assertEqual(item.review_request['currency'], 'MXN')
            self.assertEqual(item.review_request['holder'], raw['holder'])
            self.assertEqual(item.review_request['account_number'], '00123456789')
            self.assertEqual(next(r for r in item.review_request['rows'] if not r['excluded'])['description'], 'Saved wording')
            self.assertEqual([r['amount_minor'] for r in item.review_request['rows']], [r['amount_minor'] for r in raw['rows']])
            with self.assertRaisesRegex(PdfMappingError, 'changed'):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=[selection], currency='USD', actor=self.f.actor)
        self.assertEqual(self.f.preview()['currency'], 'MXN')
        status = self.status(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=status['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            self.assertEqual({r.currency for r in db.scalars(select(FinancialTransaction))}, {'MXN'})

    def test_bulk_currency_preserves_manual_amounts_across_scales(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            raw = service.initial_request(self.f.preview())
            row = next(r for r in raw['rows'] if not r['excluded'])
            row['amount_minor'] = '12300'
            row['reason'] = 'Reviewed amount'
            raw['rows'].append(dict(id='manual:opening-balance', excluded=True, manual_page=1,
                date='', description='opening balance', counterparty='', amount_minor='0', direction=None,
                balance_minor='25000', reason=''))
            item.review_request = raw
            db.commit()
            for code, amount, balance in [('GBP','12300','25000'), ('JPY','123','250'), ('KWD','123000','250000')]:
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=[SimpleNamespace(id=item.id, revision=service.currency_revision(item))], currency=code, actor=self.f.actor)
                db.refresh(item)
                self.assertEqual(next(r for r in item.review_request['rows'] if r['id']==row['id'])['amount_minor'], amount)
                self.assertEqual(item.review_request['rows'][-1]['balance_minor'], balance)
            status = self.status(batch)
            self.assertFalse(status['items'][0]['can_import'])
            with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
                service.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=self.f.actor)
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])

    def test_bulk_currency_cannot_touch_imported_or_cross_case_items(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            selection = SimpleNamespace(id=item.id, revision=service.currency_revision(item))
            with self.assertRaises(PdfMappingError):
                service.set_selected_currency(db, case_id=uuid4(), batch_id=batch, selections=[selection], currency='USD', actor=self.f.actor)
            item.status = 'pending_import'; db.commit()
            with self.assertRaisesRegex(PdfMappingError, 'changed'):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch, selections=[selection], currency='USD', actor=self.f.actor)
            self.assertEqual(db.get(Item, item.id).summary['currency'], 'EUR')

    def test_bulk_currency_rolls_back_prior_items_if_a_later_period_is_unavailable(self):
        from types import SimpleNamespace
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            first = db.scalar(select(Item).where(Item.batch_id == batch))
            last = Item(id=UUID(int=2**128-1), batch_id=batch, file_id=first.file_id,
                statement_key='unavailable-period', status='attention', summary=deepcopy(first.summary))
            db.add(last); db.commit()
            selections = [SimpleNamespace(id=item.id, revision=service.currency_revision(item)) for item in (first, last)]
            with self.assertRaises(PdfMappingError):
                service.set_selected_currency(db, case_id=self.f.case.id, batch_id=batch,
                    selections=selections, currency='USD', actor=self.f.actor)
            db.refresh(first)
            self.assertEqual(first.summary['currency'], 'EUR')
            self.assertIsNone(first.review_request)
        self.assertEqual(self.f.preview()['currency'], 'EUR')

    def test_pause_retains_import_receipt_and_resume_runs_it_once(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=self.status(batch)['ready_revision'], actor=self.f.actor)
            service.control_batch(db, case_id=self.f.case.id, batch_id=batch, action='pause')
        self.advance(batch)
        paused = self.status(batch)
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(paused['counts']['pending_import'], 1)
        self.assertEqual(paused['counts']['imported'], 0)
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'paused'):
                service.refresh_statement_list(db, case_id=self.f.case.id, batch_id=batch)
            service.control_batch(db, case_id=self.f.case.id, batch_id=batch, action='resume')
        self.advance(batch); self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        self.assertEqual(self.status(batch)['operations'][0]['transaction_count'], 12)

    def test_pause_during_reading_finishes_current_statement_then_stops(self):
        from unittest.mock import patch
        batch = self.create()
        actual = service._review_file
        calls = []
        def reviewed(*args):
            calls.append(args[-1]['file_id'])
            with self.f.SessionLocal() as db:
                state = service.control_batch(db, case_id=self.f.case.id, batch_id=batch, action='pause')
                self.assertEqual(state['status'], 'pausing')
                with self.assertRaisesRegex(PdfMappingError, 'still finishing'):
                    service.control_batch(db, case_id=self.f.case.id, batch_id=batch, action='resume')
            return actual(*args)
        with patch.object(service, '_review_file', side_effect=reviewed):
            self.advance(batch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.status(batch)['status'], 'paused')
        self.assertEqual(self.status(batch)['files'][0]['status'], 'checked')
        self.assertEqual(len(self.status(batch)['items']), 1)

    def test_expired_pause_after_process_restart_does_not_run_pending_work(self):
        from datetime import datetime, timedelta, timezone
        batch = self.create()
        with self.f.SessionLocal() as db:
            record = db.get(Batch, batch)
            record.status = 'pausing'; record.worker_token = str(uuid4())
            record.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        self.advance(batch)
        self.assertEqual(self.status(batch)['status'], 'paused')
        self.assertEqual(self.status(batch)['total'], 0)

    def test_shutdown_waits_for_atomic_statement_thread_before_acknowledgement(self):
        from threading import Event
        entered, release, finished = Event(), Event(), Event()
        def writing():
            entered.set(); release.wait(5); finished.set()
        async def scenario():
            task = asyncio.create_task(service._finish_atomic(writing))
            while not entered.is_set(): await asyncio.sleep(.001)
            task.cancel(); await asyncio.sleep(.01)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertTrue(finished.is_set())
        asyncio.run(scenario())

    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.f.file.status="processed"
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def create(self, folder_ids=None, request_id=None):
        f=self.f
        with f.SessionLocal() as db:
            return service.create_batch(db,case_id=f.case.id,request_id=request_id or uuid4(),
                file_ids=[] if folder_ids else [f.file.id],folder_ids=folder_ids or [],actor=f.actor)

    def status(self,batch,**kwargs):
        with self.f.SessionLocal() as db:
            return service.batch_status(db,case_id=self.f.case.id,batch_id=batch,**kwargs)

    def advance(self,batch):
        process=AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(service.advance_batch(self.f.SessionLocal,batch,Path,process))
        process.assert_not_awaited()

    def test_folder_preparation_bulk_confirmation_and_repeat_do_not_duplicate(self):
        f=self.f
        folder=EvidenceFolder(id=uuid4(),case_id=f.case.id,name='Financial batch fixture')
        f.db.add(folder);f.db.flush();f.file.folder_id=folder.id;f.db.commit()
        batch=self.create([folder.id])
        self.advance(batch)
        before=self.status(batch)
        self.assertEqual(before['status'],'review')
        self.assertEqual(before['counts']['ready'],1,before)
        self.assertEqual(before['ready_transactions'],12)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
        self.advance(batch)
        after=self.status(batch)
        self.assertEqual(after['counts']['imported'],1,after)
        self.assertEqual(after['items'][0]['transaction_count'],12)
        self.advance(batch)
        # A second folder batch recognises the existing import too.
        second=self.create([folder.id]);self.advance(second)
        self.assertEqual(self.status(second)['counts']['imported'],1)
        with f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),12)

    def test_bulk_import_saves_balance_only_statement_and_file_status_without_payments(self):
        from services.financial.statement_file_status import statement_file_status
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()
        from tests.financial_reconciled_fixture import install_reconciled_source
        from services.financial.statement_admission import assess_admission
        install_reconciled_source(self.f, quiet=True)
        batch = self.create()
        self.advance(batch)
        before = self.status(batch)
        self.assertEqual(before['ready_transactions'], 0)
        self.assertFalse(before['items'][0]['can_import'])
        proposal = self.f.preview(); raw = service.initial_request(proposal)
        assessment = assess_admission(proposal, StatementImportRequest.model_validate(raw))
        raw.update(no_activity_confirmed=True, no_activity_revision=assessment['revision'])
        with self.f.SessionLocal() as db:
            service.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(before['items'][0]['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
        before = self.status(batch)
        self.assertTrue(before['items'][0]['can_import'])
        with self.f.SessionLocal() as db:
            queued = service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=before['ready_revision'], actor=self.f.actor)
        self.assertEqual(queued['queued'], 1)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            status = statement_file_status(db, case_id=self.f.case.id)
            self.assertEqual(status['files'][0]['current_transactions'], 0)
            self.assertEqual(len(status['files'][0]['periods']), 1)
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
        repeated = self.create()
        self.advance(repeated)
        self.assertEqual(self.status(repeated)['counts']['imported'], 1)

    def test_readiness_separates_flagged_rows_and_balance_differences(self):
        proposal=self.f.preview()
        status,clean=service.assess(proposal)
        self.assertEqual(status,'ready',clean)
        changed=deepcopy(proposal)
        payment=next(r for r in changed['rows'] if not r['excluded'])
        payment['issues']=['Check the date against the PDF.']
        status,summary=service.assess(changed)
        self.assertEqual(status,'attention')
        self.assertIn(payment['id'],[p['row_id'] for p in summary['problems']])
        self.assertFalse(any(p['row_id'] is None for p in summary['problems']))
        self.assertEqual(summary['problems'][0]['page'], payment['page_number'])
        raw=service.initial_request(changed)
        next(r for r in raw['rows'] if r['id']==payment['id'])['reason']='Checked against the PDF.'
        self.assertEqual(service.assess(changed,raw)[0],'ready')
        edited=service.initial_request(proposal)
        next(r for r in edited['rows'] if r['id']==payment['id'])['description']='Corrected description'
        status,summary=service.assess(proposal,edited)
        self.assertEqual(status,'ready')
        self.assertTrue(summary['can_import'])
        self.assertEqual(summary['problems'], [])
        # An arithmetical mismatch never joins ready statements.
        changed=deepcopy(proposal)
        changed['rows'].append(dict(id='end',kind='balance',excluded=True,issues=[],page_number=1,fields=dict(description='Closing balance',balance='1')))
        self.assertEqual(service.assess(changed)[0],'attention')

    def test_bulk_worker_imports_undated_interest_with_its_period_and_no_printed_date(self):
        self.f.card_balance_request()
        import hashlib
        from postgres.models.evidence import EvidenceDocumentText
        text = self.f.db.get(EvidenceDocumentText, self.f.file.id)
        text.content = text.content.replace('Currency: EUR', 'Currency: USD')
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        self.f.db.commit()
        batch = self.create()
        self.advance(batch)
        before = self.status(batch)
        self.assertEqual(before['counts']['ready'], 1, before)
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                                 expected_revision=before['ready_revision'], actor=self.f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'], 1)
        with self.f.SessionLocal() as db:
            rows = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(rows), 3)
            charge = next(r for r in rows if r.description == 'Interest Charge on Purchases')
            self.assertIsNone(charge.transaction_date)
            self.assertEqual(charge.provenance['date_basis'], 'statement_end_ordering_only')

    def test_confirmation_only_queues_the_ready_snapshot_and_cases_are_isolated(self):
        f=self.f;batch=self.create();self.advance(batch)
        before=self.status(batch)
        with f.SessionLocal() as db:
            original=db.scalar(select(Item).where(Item.batch_id==batch))
            flagged=Item(id=uuid4(),batch_id=batch,file_id=f.file.id,statement_key='other-period',status='attention',summary={**original.summary,'period_start':'2024-01-01','period_end':'2024-12-31','can_import':False,'problems':[{'message':'Check an amount.','row_id':'1:0:1'}]})
            db.add(flagged);db.commit()
            # An unrelated attention item does not alter the approved ready list.
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            self.assertEqual(flagged.status,'attention')
        with f.SessionLocal() as db:
            receipt = service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            self.assertEqual(receipt['operation']['pending'], 1)
            with self.assertRaisesRegex(PdfMappingError,'ready statements changed'):
                service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor,request_id=uuid4())
            with self.assertRaisesRegex(PdfMappingError,'not found'):
                service.batch_status(db,case_id=uuid4(),batch_id=batch)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['attention'],1)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        self.assertEqual(self.status(batch,only_problems=True)['total'],1)

    def test_saved_corrections_are_used_by_background_import(self):
        f=self.f;batch=self.create();self.advance(batch)
        item=self.status(batch)['items'][0]
        raw=service.initial_request(f.preview())
        payment=next(r for r in raw['rows'] if not r['excluded'])
        payment['description']='Corrected fixture payment'
        payment['reason']='Compared with the synthetic statement.'
        with f.SessionLocal() as db:
            result=service.save_review(db,case_id=f.case.id,batch_id=batch,item_id=UUID(item['id']),request=StatementImportRequest.model_validate(raw),expected_review_revision=service._digest({}))
            self.assertEqual(result['status'],'ready')
            with self.assertRaisesRegex(PdfMappingError,'Another user saved'):
                service.save_review(db,case_id=f.case.id,batch_id=batch,item_id=UUID(item['id']),request=StatementImportRequest.model_validate(raw),expected_review_revision=service._digest({}))
        ready=self.status(batch)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=ready['ready_revision'],actor=f.actor)
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        with f.SessionLocal() as db:
            rows=list(db.scalars(select(FinancialTransaction)))
            self.assertIn('Corrected fixture payment',[r.description for r in rows])

    def test_individual_saved_progress_is_retained_when_added_to_a_batch(self):
        from services.financial.statement_progress import save_progress
        f=self.f
        raw=service.initial_request(f.preview())
        payment=next(row for row in raw['rows'] if not row['excluded'])
        payment.update(date='', reason='Date correction is not finished')
        with f.SessionLocal() as db:
            save_progress(db,case_id=f.case.id,evidence_file_id=f.file.id,
                request=StatementReviewDraft.model_validate(raw),expected_review_revision='initial',actor=f.actor)
        batch=self.create(); self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['attention'],1)
        with f.SessionLocal() as db:
            item=db.scalar(select(Item).where(Item.batch_id==batch))
            self.assertEqual(next(row for row in item.review_request['rows'] if row['id']==payment['id'])['date'],'')

    def test_incomplete_progress_is_saved_but_cannot_enter_transactions(self):
        f=self.f; batch=self.create(); self.advance(batch)
        item=self.status(batch)['items'][0]
        raw=service.initial_request(f.preview())
        payment=next(r for r in raw['rows'] if not r['excluded'])
        payment['amount_minor']=''
        raw['holder']=''
        with f.SessionLocal() as db:
            result=service.save_review(db, case_id=f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=service._digest({}))
            self.assertEqual(result['status'], 'attention')
            saved=db.get(Item, UUID(item['id']))
            self.assertEqual(saved.review_request['holder'], '')
            self.assertEqual(result['review_revision'], service._digest(saved.review_request))
            self.assertFalse(saved.summary['can_import'])
            with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
                service.queue_import(db, case_id=f.case.id, batch_id=batch,
                    expected_revision=service.ready_revision([saved]), actor=f.actor)
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
            self.assertEqual(next(r for r in saved.review_request['rows'] if r['id']==payment['id'])['amount_minor'], '')

    def test_next_problem_crosses_list_pages_and_never_crosses_cases(self):
        f=self.f; batch=self.create(); self.advance(batch)
        original=self.status(batch)['items'][0]
        target=None
        with f.SessionLocal() as db:
            for n in range(130):
                identity=uuid4()
                if n == 128: target=identity
                db.add(Item(id=identity, batch_id=batch, file_id=f.file.id, statement_key=f'synthetic-{n}',
                    status='attention' if n == 128 else 'ready',
                    summary={**original, 'filename':f'Z synthetic {n:03d}', 'account':f'TEST{n+1000}', 'problems':[dict(row_id='3:0:4', message='Check date')] if n == 128 else []}))
            db.commit()
            result=service.next_problem(db, case_id=f.case.id, batch_id=batch, item_id=UUID(original['id']))
            self.assertEqual(result['item_id'], str(target))
            self.assertEqual(result['row_id'], '3:0:4')
            self.assertEqual(service.next_problem(db, case_id=f.case.id, batch_id=batch, item_id=target)['item_id'], None)
            with self.assertRaises(PdfMappingError):
                service.next_problem(db, case_id=uuid4(), batch_id=batch, item_id=target)

    def test_start_is_idempotent_and_worker_recovers_after_recorded_import(self):
        f=self.f;request=uuid4();batch=self.create(request_id=request)
        self.assertEqual(self.create(request_id=request),batch)
        self.advance(batch)
        ready=self.status(batch)
        with f.SessionLocal() as db:
            service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=ready['ready_revision'],actor=f.actor)
        self.advance(batch)
        # Simulate a process exit after the writer commits, before the batch receipt.
        with f.SessionLocal() as db:
            item=db.scalar(select(Item).where(Item.batch_id==batch));item.status='pending_import'
            db.get(Batch,batch).status='preparing';db.commit()
        self.advance(batch)
        self.assertEqual(self.status(batch)['counts']['imported'],1)
        with f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))),12)

    def test_each_recognised_period_is_checked_separately_and_unknown_currency_stays_out(self):
        from unittest.mock import patch
        f=self.f;batch=self.create();base=f.preview()
        choices=[dict(id='a'*64),dict(id='b'*64)]
        calls=[]
        def reading(*args,**kwargs):
            calls.append(kwargs)
            result=deepcopy(base);result['statement_choices']=choices
            result['statement_id']=kwargs.get('statement_id')
            if result['statement_id']=='b'*64:
                next(row for row in result['rows'] if not row['excluded'])['issues']=['Check the date.']
            return result
        with f.SessionLocal() as db, patch.object(service,'read_statement_import',side_effect=reading):
            owner=db.get(Batch,batch)
            service.prepare_reviews(db,owner,owner.files[0])
        status=self.status(batch)
        self.assertEqual(status['counts']['ready'],1)
        self.assertEqual(status['counts']['attention'],1)
        self.assertEqual({i['statement_id'] for i in status['items']},{'a'*64,'b'*64})
        self.assertIs(calls[0]['_cache'],calls[1]['_cache'])
        unknown=deepcopy(base);unknown['currency']=''
        self.assertEqual(service.assess(unknown)[0],'attention')

    def test_newly_ready_statement_requires_a_new_confirmation(self):
        f=self.f;batch=self.create();self.advance(batch);before=self.status(batch)
        with f.SessionLocal() as db:
            original=db.scalar(select(Item).where(Item.batch_id==batch))
            db.add(Item(id=uuid4(),batch_id=batch,file_id=f.file.id,statement_key='late-period',status='ready',summary=deepcopy(original.summary)))
            db.commit()
            with self.assertRaisesRegex(PdfMappingError,'ready statements changed'):
                service.queue_import(db,case_id=f.case.id,batch_id=batch,expected_revision=before['ready_revision'],actor=f.actor)
            self.assertFalse(list(db.scalars(select(Item).where(Item.status=='pending_import'))))
