"""Synthetic content/provenance audit: bounded reads and no classification."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.financial_recovery import FinancialRecoveryRun as RecoveryRun, FinancialRecoveryItem as RecoveryItem
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from postgres.session import get_db
from routers.users import get_current_db_user
from services.financial.pdf_candidates import PdfMappingError
from services.financial.source_audit import list_source_audit, source_audit_detail
from services.financial.file_visibility import _removal_guard, financial_file_visibility
from services.financial.active_recovery import active_recovery_file_ids
from tests import test_financial_file_intake as intake_fixtures
from tests.test_route_authorization import _CaseAccessDb


class SourceAuditTests(TestCase):
    def setUp(self):
        self.f = intake_fixtures.FinancialFileIntakeTests('test_remove_restore_persist_with_original_and_history')
        self.f.setUp()
        Base.metadata.create_all(self.f.db.connection(), tables=[FinancialCandidateMapping.__table__,
            FinancialStatementReviewDraft.__table__, WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def selected(self, name='Synthetic source.unusual'):
        file = self.f.new_file(name, status='unprocessed')
        file.metadata_ = {'financial_workspace': dict(schema='loupe.financial.file/1',
            selected_by=str(self.f.user.id), selected_at='2026-01-01T12:00:00Z')}
        self.f.db.commit()
        return file

    def listing(self, **kwargs):
        return list_source_audit(self.f.db, case_id=self.f.case.id, **kwargs)

    def test_ordinary_evidence_is_not_enrolled_and_no_format_determines_membership(self):
        self.assertEqual(self.listing()['total'], 0)
        for name in ('Synthetic.txt', 'Synthetic.csv', 'Synthetic.jpeg', 'Synthetic.pdf', 'Synthetic.anything'):
            self.selected(name)
        result = self.listing()
        self.assertEqual(result['total'], 5)
        self.assertEqual(result['summary']['protected'], 5)
        self.assertTrue(all(r['provenance']['explicit_selection'] for r in result['groups']))
        self.assertEqual(result['summary']['without_retained_text'], 5)
        self.assertNotIn(str(self.f.file.id), [r['current_file_id'] for r in result['groups']])

    def test_verified_lineage_groups_versions_but_equal_hash_alone_does_not(self):
        first = self.selected()
        copy = self.f.new_file('Synthetic retained reading.pdf')
        copy.metadata_ = dict(statement_root_evidence_id=str(first.id), statement_parent_evidence_id=str(first.id))
        independent = self.selected('Synthetic independent.pdf')
        independent.metadata_ = {**independent.metadata_, 'financial_file_visibility': dict(removed=True, revision='hidden-r1')}
        foreign = self.f.new_file('Foreign case source.txt', case=self.f.other_case)
        foreign.metadata_ = dict(statement_root_evidence_id=str(first.id), financial_workspace=dict(schema='loupe.financial.file/1'))
        self.f.db.commit()
        result = self.listing()
        self.assertEqual(result['summary']['groups'], 2)
        self.assertEqual(result['summary']['visible'], 1)
        self.assertEqual(result['summary']['hidden'], 1)
        self.assertEqual(next(g for g in result['groups'] if g['root_file_id'] == str(first.id))['version_count'], 2)
        self.assertEqual(self.listing(visibility='hidden')['total'], 1)
        self.assertEqual([g['root_file_id'] for g in result['groups']], sorted(g['root_file_id'] for g in result['groups']))
        self.assertEqual(self.listing(offset=1, limit=1)['groups'], result['groups'][1:2])
        with self.assertRaises(PdfMappingError):
            source_audit_detail(self.f.db, case_id=self.f.case.id, file_id=foreign.id)
        with self.assertRaises(PdfMappingError):
            source_audit_detail(self.f.db, case_id=self.f.case.id, file_id=self.f.file.id)

    def test_detail_reads_only_requested_stored_text_window_without_jobs_or_mutations(self):
        file = self.selected()
        content = 'Synthetic stored content. ' * 500
        self.f.db.add(EvidenceDocumentText(evidence_file_id=file.id, content=content,
            content_sha256='a'*64, character_count=len(content), source_locations=[]))
        file.metadata_ = {**file.metadata_, 'financial_review_progress': {'': {'request': {'description': 'PRIVATE_BODY_SENTINEL'}}}}
        file.summary = 'Synthetic retained summary. ' * 100
        self.f.db.commit()
        before = deepcopy(file.metadata_)
        statements = []
        def capture(connection, cursor, statement, params, context, executemany):
            statements.append(statement)
        event.listen(self.f.db.get_bind(), 'before_cursor_execute', capture)
        try:
            with patch('services.financial.statement_import.read_statement_import', side_effect=AssertionError('No parser in audit')):
                listing = self.listing()
                result = source_audit_detail(self.f.db, case_id=self.f.case.id, file_id=file.id,
                    text_offset=7, text_limit=83)
        finally:
            event.remove(self.f.db.get_bind(), 'before_cursor_execute', capture)
        self.assertNotIn('PRIVATE_BODY_SENTINEL', str(listing) + str(result))
        self.assertNotIn(content[:40], str(listing))
        self.assertEqual(result['text_excerpt']['text'], content[7:90])
        self.assertEqual(result['text_excerpt']['total_characters'], len(content))
        self.assertTrue(result['text_excerpt']['truncated'])
        self.assertFalse(result['applied'])
        self.assertEqual(result['source_summary'], file.summary[:1500])
        self.assertTrue(result['source_summary_truncated'])
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for sql in statements))
        self.assertTrue(any('substr(' in sql.lower() for sql in statements))
        self.assertEqual(file.metadata_, before)
        self.assertNotIn('stored_path', str(result))

    def test_saved_records_batch_and_pending_work_are_explained_as_protection(self):
        document = self.f.make_document()
        period = self.f.make_period(document)
        self.f.add_row(period, document, amount=100)
        batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.user.id, actor={},
            status='review', files=[dict(source_id=str(document.evidence_file_id), status='waiting')])
        self.f.db.add(batch); self.f.db.flush()
        self.f.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
            statement_key='synthetic-period', status='pending_import', review_request={'reason':'Synthetic draft'},
            summary={'layout_id':'synthetic-recorded-reader'}))
        self.f.db.commit()
        row = next(g for g in self.listing()['groups'] if g['current_file_id'] == str(document.evidence_file_id))
        self.assertEqual(row['provenance']['saved_period_count'], 1)
        self.assertEqual(row['provenance']['payment_count'], 1)
        self.assertEqual(row['provenance']['batch_count'], 1)
        self.assertEqual(row['provenance']['parsed_statement_period_count'], 1)
        self.assertIn('synthetic-recorded-reader', row['provenance']['recognized_readers'])
        self.assertTrue({'active_work', 'saved_review', 'saved_financial_records'} <= {r['code'] for r in row['protection_reasons']})

    def recovery(self, file, *, run_status='running', item_status='pending', result=None, case=None):
        run = RecoveryRun(id=uuid4(), case_id=(case or self.f.case).id,
            release='synthetic-' + str(uuid4()), status=run_status)
        self.f.db.add(run); self.f.db.flush()
        item = RecoveryItem(id=uuid4(), run_id=run.id, file_id=file.id,
            status=item_status, result=result or {})
        self.f.db.add(item); self.f.db.commit()
        return run, item

    def test_queued_recovery_protects_verified_family_before_processing_starts(self):
        root = self.selected()
        child = self.f.new_file('Synthetic recovery reading.anything', status='unprocessed')
        child.metadata_ = dict(statement_root_evidence_id=str(root.id), statement_parent_evidence_id=str(root.id))
        independent = self.selected('Synthetic independent upload.anything')
        run, item = self.recovery(root, result={'reading_file_id': str(child.id)})
        before = deepcopy(root.metadata_), deepcopy(child.metadata_), deepcopy(item.result)
        for state in ('pending', 'waiting', 'reading'):
            with self.subTest(state=state):
                item.status = state; self.f.db.commit()
                result = self.listing()
                group = next(g for g in result['groups'] if g['root_file_id'] == str(root.id))
                self.assertTrue(group['active_work'])
                self.assertEqual(result['summary']['active_work'], 1)
                self.assertIn('active_work', {r['code'] for r in group['protection_reasons']})
                for member in (root, child):
                    with self.assertRaisesRegex(PdfMappingError, 'recovery.*queued or active'):
                        self.f.change(True, file=member)
                _removal_guard(self.f.db, self.f.case.id, [independent])
                self.assertEqual((run.status, item.status), ('running', state))
                self.assertEqual(before, (root.metadata_, child.metadata_, item.result))
                self.assertFalse(financial_file_visibility(root)['financial_removed'])

    def test_paused_and_terminal_recovery_do_not_lock_membership(self):
        file = self.selected()
        run, item = self.recovery(file)
        for run_state, item_state in (('paused', 'pending'), ('paused', 'reading'),
                ('complete', 'waiting'), ('running', 'review'), ('running', 'recovered'),
                ('running', 'unchanged'), ('running', 'kept')):
            with self.subTest(run=run_state, item=item_state):
                run.status, item.status = run_state, item_state; self.f.db.commit()
                self.assertFalse(self.listing()['groups'][0]['active_work'])
                hidden = self.f.change(True, financial_file_visibility(file)['financial_visibility_revision'], file=file)
                self.assertTrue(hidden['financial_removed'])
                self.f.change(False, hidden['financial_visibility_revision'], file=file)
                self.assertEqual((run.status, item.status), (run_state, item_state))

    def test_recovery_targets_are_case_scoped_and_review_count_is_storage_not_distinct(self):
        original, target = self.selected(), self.selected('Synthetic retained target.txt')
        foreign = self.f.new_file('Synthetic other-case source.txt', case=self.f.other_case)
        self.recovery(foreign, case=self.f.other_case, result={'reading_file_id': str(target.id)})
        self.assertEqual(active_recovery_file_ids(self.f.db, case_id=self.f.case.id), set())
        run, item = self.recovery(original, result={'reading_file_id': str(target.id)})
        self.assertEqual(active_recovery_file_ids(self.f.db, case_id=self.f.case.id,
            file_ids=[target.id]), {target.id})
        with self.assertRaisesRegex(PdfMappingError, 'recovery.*queued or active'):
            self.f.change(True, file=target)
        item.result = {'reading_file_id': str(foreign.id)}
        original.metadata_ = {**original.metadata_, 'financial_review_progress': {'request': 'Synthetic saved review'},
            'financial_review_history': [{'request': 'Synthetic saved review'}]}
        self.f.db.commit()
        self.assertEqual(active_recovery_file_ids(self.f.db, case_id=self.f.case.id), {original.id})
        row = next(g for g in self.listing()['groups'] if g['current_file_id'] == str(original.id))
        self.assertEqual(row['provenance']['saved_review_storage_count'], 2)
        self.assertEqual(row['provenance']['review_count_basis'], 'storage_representations')
        self.assertNotIn('review_count_is_minimum', row['provenance'])


class SourceAuditAuthorizationTests(TestCase):
    def setUp(self):
        from routers import financial_source_audit as module
        self.module = module
        self.app = FastAPI(); self.app.include_router(module.router)
        self.client = TestClient(self.app); self.db = _CaseAccessDb()
        self.url = f'/api/financial/source-audit?case_id={self.db.case.id}'

    def user(self, permissions):
        self.db.membership = SimpleNamespace(permissions=permissions) if permissions is not None else None
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_db_user] = lambda: SimpleNamespace(id=uuid4(),global_role='user',is_active=True)

    def test_read_requires_auth_and_case_view_with_bounded_parameters_and_no_write_routes(self):
        with patch.object(self.module, 'list_source_audit', return_value={'applied':False}) as listing, \
                patch.object(self.module, 'source_audit_detail', return_value={'applied':False}) as detail:
            for path in (self.url, f'/api/financial/source-audit/{uuid4()}?case_id={self.db.case.id}'):
                self.assertEqual(self.client.get(path).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            listing.assert_not_called(); detail.assert_not_called()
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(self.client.get(self.url+'&limit=51').status_code, 422)
            self.assertEqual(self.client.get(self.url+'&offset=-1').status_code, 422)
            self.assertEqual(self.client.get(self.url+'&visibility=pdf').status_code, 422)
            self.assertEqual(self.client.get(f'/api/financial/source-audit/{uuid4()}?case_id={self.db.case.id}&text_limit=8001').status_code, 422)
            self.assertEqual(self.client.post(self.url, json={}).status_code, 405)
