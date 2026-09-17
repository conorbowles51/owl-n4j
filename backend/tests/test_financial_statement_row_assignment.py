from copy import deepcopy
import hashlib
from unittest import TestCase
from uuid import uuid4, UUID
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial import statement_row_assignment as service
from services.financial.statement_import import read_statement_import, StatementReviewDraft
from services.financial.statement_progress import save_progress
from services.financial.import_batches import initial_request, prepare_reviews
from tests import test_financial_statement_import as fixture
from tests.test_financial_statement_import_card import card_source
from tests.test_financial_pdf_geometry_candidates import rectangle


def two_period_file(f):
    first = f.db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == f.file.id))
    grids = [card_source(), deepcopy(card_source())]
    for row in grids[1]['rows']:
        for cell in row['cells']:
            cell['expected_text'] = cell['expected_text'].replace('Jun.', 'Jul.').replace('May', 'Jun.').replace('31 days', '30 days')
            cell['expected_text'] = cell['expected_text'].replace('1234', '5678')
    for page, grid in enumerate(grids, 1):
        payload = [dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=page, table=dict(rectangle(0,x=0,width=600,height=600),page=page),unlocated_values=0,
                values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                    locator=dict(rectangle(20+r['row_index']*20,x=20+c['column_index']*100,width=90,height=15),page=page))
                    for r in grid['rows'] for c in r['cells']]))]
        if page == 1:
            first.payload = payload
        else:
            f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id,page_number=page,engine_job_id=first.engine_job_id,payload=payload))
    text = f.db.get(EvidenceDocumentText, f.file.id)
    contents = ['\n'.join(c['expected_text'] for r in grid['rows'] for c in r['cells']) for grid in grids]
    text.content = '\n'.join(contents)
    text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
    text.character_count = len(text.content)
    text.source_locations = [dict(kind='page',page_number=1,start_char=0,end_char=len(contents[0]),text_origin='digital_text_layer'),
        dict(kind='page',page_number=2,start_char=len(contents[0])+1,end_char=len(text.content),text_origin='digital_text_layer')]
    f.db.commit()
    with f.SessionLocal() as db:
        return read_statement_import(db,case_id=f.case.id,evidence_file_id=f.file.id,currency='USD')['statement_choices']


class RowAssignmentTests(TestCase):
    def setUp(self):
        self.f = fixture.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.choices = two_period_file(self.f)
        self.source, self.target = [c['id'] for c in self.choices]
        self.proposal = self.read(self.source)
        self.row = next(r for r in self.proposal['rows'] if r['kind'] == 'transaction' and not r['issues'])

    def tearDown(self):
        self.f.tearDown()

    def read(self, key):
        with self.f.SessionLocal() as db:
            return read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,currency='USD',statement_id=key)

    def body(self, **updates):
        proposal = self.read(self.source)
        saved = proposal.get('saved_review')
        raw = deepcopy(saved['request']) if saved else initial_request(proposal)
        return service.RowAssignmentRequest.model_validate(dict(request=raw,target_statement_id=self.target,
            row_ids=[self.row['id']],reason='The printed account section belongs to the second statement.',
            expected_review_revision=saved['review_revision'] if saved else 'initial',**updates))

    def call(self, body, apply=False, case_id=None):
        with self.f.SessionLocal() as db:
            return service.reassign_rows(db,case_id=case_id or self.f.case.id,evidence_file_id=self.f.file.id,
                body=body,actor=self.f.actor,apply=apply)

    def move(self, body=None):
        body = body or self.body()
        preview = self.call(body)
        return self.call(body.model_copy(update={'expected_preview':preview['revision']}),True)

    def test_preview_is_read_only_and_move_preserves_sources_edits_and_both_checks(self):
        dest = self.read(self.target)
        draft = initial_request(dest)
        draft['holder'] = 'Corrected destination holder'
        draft['details_reason'] = 'Checked printed holder'
        with self.f.SessionLocal() as db:
            save_progress(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,request=StatementReviewDraft.model_validate(draft),expected_review_revision='initial',actor=self.f.actor)
        body = self.body()
        raw_body = body.model_dump(mode='json')
        row = next(r for r in raw_body['request']['rows'] if r['id'] == self.row['id'])
        row['description'] = 'Correction retained through move'
        row['reason'] = 'Checked original description'
        body = service.RowAssignmentRequest.model_validate(raw_body)
        self.f.db.expire_all()
        before_metadata = deepcopy(self.f.db.get(EvidenceFile,self.f.file.id).metadata_)
        preview = self.call(body)
        self.f.db.expire_all()
        self.assertEqual(self.f.db.get(EvidenceFile,self.f.file.id).metadata_,before_metadata)
        self.assertEqual([(s['before']['transaction_count'],s['after']['transaction_count']) for s in preview['statements']],[(3,2),(3,4)])
        result = self.call(body.model_copy(update={'expected_preview':preview['revision']}),True)
        self.assertTrue(result['applied'])
        source, target = self.read(self.source), self.read(self.target)
        self.assertNotIn(self.row['id'],[r['id'] for r in source['rows']])
        moved = next(r for r in target['rows'] if r['id']==self.row['id'])
        self.assertEqual(moved['source_cells'],self.row['source_cells'])
        self.assertEqual(moved['page_number'],self.row['page_number'])
        self.assertEqual(moved['fields'],self.row['fields'])
        saved = next(r for r in target['saved_review']['request']['rows'] if r['id']==self.row['id'])
        self.assertEqual(saved['description'],'Correction retained through move')
        self.assertIn('Checked original description',saved['reason'])
        self.assertIn(body.reason,saved['reason'])
        self.assertEqual(target['saved_review']['request']['holder'],'Corrected destination holder')
        self.assertEqual([c['checks']['transaction_count'] for c in target['statement_choices']],[2,4])
        self.assertFalse(list(self.f.db.scalars(select(FinancialTransaction))))
        self.f.db.expire_all()
        self.assertEqual(len(self.f.db.get(EvidenceFile,self.f.file.id).metadata_['financial_assignment_history']),1)

    def test_preview_rejects_changed_destination_and_forbidden_rows_without_writes(self):
        body = self.body(); preview = self.call(body)
        with self.f.SessionLocal() as db:
            raw = initial_request(self.read(self.target))
            raw['holder'] = ''
            save_progress(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,request=StatementReviewDraft.model_validate(raw),expected_review_revision='initial',actor=self.f.actor)
        with self.assertRaisesRegex(PdfMappingError,'changed after the preview'):
            self.call(body.model_copy(update={'expected_preview':preview['revision']}),True)
        with self.assertRaisesRegex(PdfMappingError,'not found'):
            self.call(body,case_id=uuid4())
        control = next(r for r in self.proposal['rows'] if r['kind'] not in ('transaction','unresolved'))
        with self.assertRaisesRegex(PdfMappingError,'Only extracted transaction'):
            self.call(body.model_copy(update={'row_ids':[control['id']]}))
        self.assertIsNone(self.read(self.source)['saved_review'])

    def test_each_batch_keeps_its_own_corrected_values_and_rejects_pending_import(self):
        batch_id = uuid4()
        with self.f.SessionLocal() as db:
            batch = Batch(id=batch_id,case_id=self.f.case.id,created_by=self.f.user.id,status='review',actor={},files=[])
            db.add(batch);db.commit()
            prepare_reviews(db,batch,dict(file_id=str(self.f.file.id),source_id=str(self.f.file.id),filename='Synthetic.pdf',currency='USD'))
            item = db.scalar(select(Item).where(Item.batch_id==batch_id,Item.statement_key==self.source))
            raw = initial_request(self.proposal)
            row = next(r for r in raw['rows'] if r['id']==self.row['id'])
            row['description']='Separate bulk correction';row['reason']='Bulk review reason'
            item.review_request=raw;db.commit()
        self.move()
        with self.f.SessionLocal() as db:
            destination = db.scalar(select(Item).where(Item.batch_id==batch_id,Item.statement_key==self.target))
            row = next(r for r in destination.review_request['rows'] if r['id']==self.row['id'])
            self.assertEqual(row['description'],'Separate bulk correction')
            self.assertEqual(destination.summary['transaction_count'],4)
            source = db.scalar(select(Item).where(Item.batch_id==batch_id,Item.statement_key==self.source))
            self.assertNotIn(self.row['id'],[r['id'] for r in source.review_request['rows']])
            source.status='pending_import';db.commit()
        self.source,self.target = self.target,self.source
        with self.assertRaisesRegex(PdfMappingError,'being imported'):
            self.call(self.body())

    def test_move_back_retains_history_and_changed_extraction_cannot_use_old_assignment(self):
        self.move()
        self.source,self.target = self.target,self.source
        self.move()
        restored = self.read(self.target)
        self.assertEqual(sum(r['id']==self.row['id'] for r in restored['rows']),1)
        self.assertEqual(restored['transaction_count'],3)
        moved = next(r for r in restored['rows'] if r['id']==self.row['id'])
        self.assertEqual(len(moved['assignment']['history']),2)
        with self.f.SessionLocal() as db:
            table = db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id==self.f.file.id,EvidenceTableGeometry.page_number==1))
            payload=deepcopy(table.payload); payload[0]['table']['values'][0]['text']+=' Changed reading'
            table.payload=payload;db.commit()
        with self.assertRaisesRegex(PdfMappingError,'reading changed'):
            self.read(self.target)

    def test_imports_of_both_periods_keep_one_copy_of_moved_row_and_its_locator(self):
        self.move()
        receipts=[]
        for key in (self.target,self.source):
            proposal=self.read(key)
            raw=deepcopy(proposal['saved_review']['request'])
            for row in raw['rows']:
                if not row['excluded'] and not row['date']:
                    row['date']=raw['period_end'];row['reason']+=' Checked synthetic interest date.'
            from services.financial.review_arithmetic import check_proposed_rows
            checks=check_proposed_rows(proposal,raw['rows'])
            raw.update(balance_exception_reason='Synthetic reassignment regression: controls intentionally remain in original periods.',balance_exception_revision=checks['checks_revision'])
            receipt=self.f.confirm(raw); receipts.append(receipt)
            self.assertFalse(self.f.confirm(raw)['created'])
        self.assertEqual([r['transaction_count'] for r in receipts],[4,2])
        with self.f.SessionLocal() as db:
            rows=list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(rows),6)
            reassigned=[r for r in rows if (r.provenance or {}).get('statement_import_original',{}).get('assignment')]
            self.assertEqual(len(reassigned),1)
        with self.assertRaisesRegex(PdfMappingError,'already imported'):
            self.call(self.body())

    def test_move_recalculates_real_printed_balance_differences_on_both_sides(self):
        from tests.test_financial_statement_import_card import summary_source
        with self.f.SessionLocal() as db:
            for table in db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id==self.f.file.id)):
                grid=summary_source()
                for row in grid['rows']:
                    for cell in row['cells']:
                        if table.page_number==2:
                            cell['expected_text']=cell['expected_text'].replace('Jun.','Jul.').replace('May','Jun.').replace('1234','5678').replace('31 days','30 days')
                payload=deepcopy(table.payload)
                payload.append(dict(table_source='drawn_geometry',geometry_source='cell_rectangles',
                    table=dict(page=table.page_number,table=dict(rectangle(0,x=0,width=600,height=800),page=table.page_number),unlocated_values=0,
                        values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator={**c['locator'],'page':table.page_number}) for r in grid['rows'] for c in r['cells']])))
                table.payload=payload
            db.commit()
            choices=read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,currency='USD')['statement_choices']
        self.source,self.target=[c['id'] for c in choices]
        self.proposal=self.read(self.source)
        self.row=next(r for r in self.proposal['rows'] if r['kind']=='transaction' and r['fields']['direction']=='credit')
        preview=self.call(self.body())
        closing=[next(c for c in s['after']['checks'] if c['kind']=='closing_balance') for s in preview['statements']]
        self.assertEqual([s['before']['balance_status'] for s in preview['statements']],['matches','matches'])
        self.assertEqual([c['status'] for c in closing],['difference','difference'])
        self.assertEqual([c['difference_minor'] for c in closing],['18000','-18000'])
