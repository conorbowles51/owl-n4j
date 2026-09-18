"""An orphan continuation needs an explicit, saved account assignment."""
from copy import deepcopy
import hashlib
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from sqlalchemy import select
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches, statement_row_assignment
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import read_statement_import, confirm_statement_import
from tests import test_financial_statement_import as fixture
from tests.test_financial_statement_import_andrews import source
from tests.test_financial_pdf_geometry_candidates import rectangle


def orphan_file(f):
    grids = [source([
        [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
        [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')],
        [(15, 'Continued on following page')]]),
        source([
            [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '70.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '70.00')]], page=2, printed_page=3, names=False)]
    first = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    for page, grid in enumerate(grids, 1):
        payload = [dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=page, table=dict(rectangle(0, x=0, width=600, height=700), page=page), unlocated_values=0,
                values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                        for r in grid['rows'] for c in r['cells']]))]
        if page == 1:
            first.payload = payload
        else:
            f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id, page_number=page,
                engine_job_id=first.engine_job_id, payload=payload))
    text = f.db.get(EvidenceDocumentText, f.file.id)
    contents = ['\n'.join(c['expected_text'] for r in grid['rows'] for c in r['cells']) for grid in grids]
    text.content = '\n'.join(contents)
    text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
    text.character_count = len(text.content)
    text.source_locations = [dict(kind='page', page_number=1, start_char=0, end_char=len(contents[0]), text_origin='digital_text_layer'),
        dict(kind='page', page_number=2, start_char=len(contents[0])+1, end_char=len(text.content), text_origin='digital_text_layer')]
    f.db.commit()
    return grids


class UnassignedStatementTests(TestCase):
    def setUp(self):
        self.f = fixture.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        orphan_file(self.f)
        choices = self.read()['statement_choices']
        self.source = next(c['id'] for c in choices if c.get('assignment_only'))
        self.target = next(c['id'] for c in choices if not c.get('assignment_only'))

    def tearDown(self):
        self.f.tearDown()

    def read(self, key=None):
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                                         currency='USD', statement_id=key)

    def call(self, body, apply=False):
        with self.f.SessionLocal() as db:
            return statement_row_assignment.reassign_rows(db, case_id=self.f.case.id,
                evidence_file_id=self.f.file.id, body=body, actor=self.f.actor, apply=apply)

    def test_orphan_cannot_import_even_with_account_fields_and_moves_without_duplicate(self):
        proposal = self.read(self.source)
        self.assertTrue(proposal['assignment_only'])
        self.assertEqual(proposal['printed_main_account'], '123456789')
        row = next(r for r in proposal['rows'] if not r['excluded'])
        raw = import_batches.initial_request(proposal)
        attempted = deepcopy(raw)
        attempted.update(holder='Checked holder', account_number='123456789 / Share 0040', details_reason='Typed account')
        with self.assertRaisesRegex(PdfMappingError, 'Assign these payments'):
            confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
                evidence_file_id=self.f.file.id, request=attempted, actor=self.f.actor, resolve_path=Path)
        self.assertEqual(import_batches.assess(proposal)[0], 'attention')
        self.assertEqual(import_batches.assess(proposal, attempted)[0], 'attention')
        next(r for r in raw['rows'] if r['id'] == row['id'])['description'] = 'Checked shop description'
        body = statement_row_assignment.RowAssignmentRequest.model_validate(dict(request=raw,
            target_statement_id=self.target, row_ids=[row['id']], reason='Confirmed checking share using supporting records',
            expected_review_revision='initial'))
        preview = self.call(body)
        self.assertEqual(self.read(self.source)['transaction_count'], 1)
        self.call(body.model_copy(update={'expected_preview': preview['revision']}), True)
        after = self.read(self.source)
        self.assertEqual(after['transaction_count'], 0)
        self.assertEqual(import_batches.assess(after, after['saved_review']['request'])[0], 'assigned')
        target = self.read(self.target)
        self.assertEqual(target['transaction_count'], 2)
        moved = next(r for r in target['rows'] if r['id'] == row['id'])
        self.assertEqual(moved['source_cells'], row['source_cells'])
        self.assertEqual(moved['page_number'], 2)
        saved = target['saved_review']['request']
        self.assertEqual(next(r for r in saved['rows'] if r['id'] == row['id'])['description'], 'Checked shop description')
        self.assertIn(body.reason, next(r for r in saved['rows'] if r['id'] == row['id'])['reason'])
        self.assertEqual(import_batches.assess(target, saved)[0], 'ready')
        result = confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            evidence_file_id=self.f.file.id, request=saved, actor=self.f.actor, resolve_path=Path)
        repeated = confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            evidence_file_id=self.f.file.id, request=saved, actor=self.f.actor, resolve_path=Path)
        self.assertEqual(result['transaction_count'], 2)
        self.assertFalse(repeated['created'])
        reopened = self.read(self.source)
        self.assertIsNone(reopened['current_import'])
        self.assertEqual(import_batches.assess(reopened, reopened['saved_review']['request'])[0], 'assigned')
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 2)

    def test_unassigned_page_cannot_receive_rows_and_partial_exclusion_does_not_resolve_it(self):
        proposal = self.read(self.target)
        row = next(r for r in proposal['rows'] if not r['excluded'])
        body = statement_row_assignment.RowAssignmentRequest.model_validate(dict(request=import_batches.initial_request(proposal),
            target_statement_id=self.source, row_ids=[row['id']], reason='Wrong destination', expected_review_revision='initial'))
        with self.assertRaisesRegex(PdfMappingError, 'unassigned page cannot receive'):
            self.call(body)
        proposal = self.read(self.source)
        raw = import_batches.initial_request(proposal)
        for row in raw['rows']:
            row.update(excluded=True, reason='Not yet assigned')
        self.assertEqual(import_batches.assess(proposal, raw)[0], 'attention')

    def test_batch_records_assignment_completion_and_keeps_destination_ready(self):
        f = self.f
        with f.SessionLocal() as db:
            batch = Batch(id=uuid4(), case_id=f.case.id, created_by=f.user.id, status='review', files=[],
                actor=dict(name=f.actor.name, email=f.actor.email, user_id=str(f.actor.user_id)))
            db.add(batch); db.flush()
            file = db.get(type(f.file), f.file.id)
            # This fixture deliberately supplies the printed currency context.
            file.metadata_ = {**(file.metadata_ or {}), 'statement_currency': 'USD'}
            db.commit()
            batch_id = batch.id
            for key in (self.source, self.target):
                proposal = self.read(key)
                status, summary = import_batches.assess(proposal)
                db.add(Item(id=uuid4(), batch_id=batch_id, file_id=f.file.id, statement_key=key,
                    status=status, summary={**summary, 'filename':'synthetic.pdf', 'source_id':str(f.file.id)},
                    review_request=import_batches.initial_request(proposal)))
            db.commit()
        proposal = self.read(self.source)
        raw = import_batches.initial_request(proposal)
        body = statement_row_assignment.RowAssignmentRequest.model_validate(dict(request=raw,
            target_statement_id=self.target, row_ids=[r['id'] for r in proposal['rows'] if not r['excluded']],
            reason='Checked printed account', expected_review_revision='initial'))
        preview = self.call(body)
        self.call(body.model_copy(update={'expected_preview':preview['revision']}), True)
        with f.SessionLocal() as db:
            status = import_batches.batch_status(db, case_id=f.case.id, batch_id=batch_id)
        self.assertEqual(status['counts']['assigned'], 1)
        self.assertEqual(status['counts']['ready'], 1)
        self.assertEqual(status['ready_transactions'], 2)
        with f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch_id, Item.statement_key == self.source))
            revision = import_batches._digest(dict(status=item.status, request=item.review_request,
                decision=item.summary.get('import_decision')))
            with self.assertRaisesRegex(PdfMappingError, 'statement changed'):
                import_batches.leave_unimported(db, case_id=f.case.id, batch_id=batch_id, item_id=item.id,
                    action='skip', reason='Cannot skip completed assignment', expected_revision=revision, actor=f.actor)
