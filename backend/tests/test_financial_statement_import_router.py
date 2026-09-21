import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import financial_statement_import as module
from postgres.session import get_db
from routers.users import get_current_db_user
from tests.test_route_authorization import _CaseAccessDb


class StatementImportAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI()
        self.app.include_router(module.router)
        self.client=TestClient(self.app)
        self.file_id=uuid4()
        self.db=_CaseAccessDb()

    def user(self,permissions):
        self.db.membership=SimpleNamespace(permissions=permissions) if permissions is not None else None
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.app.dependency_overrides[get_current_db_user]=lambda:SimpleNamespace(id=uuid4(),global_role='user',is_active=True)

    def endpoint(self,suffix=''):
        return f'/api/financial/statement-import/{self.file_id}{suffix}?case_id={self.db.case.id}'

    def test_removal_confirmation_routes_selection_to_removal_not_statement_import(self):
        prefix = f'/api/financial/statement-import/removals'
        with patch('services.financial.import_removal.preview_removal', return_value={'revision': 'a'*64}) as preview, \
                patch('services.financial.import_removal.remove_imports', return_value={'removed': True}) as remove, \
                patch.object(module, 'confirm_statement_import') as import_statement, \
                patch.object(module, 'actor_from_user'):
            for selection in (
                {'file_ids': [str(self.file_id)], 'batch_ids': []},
                {'file_ids': [str(uuid4()) for _ in range(8)], 'batch_ids': []},
                {'file_ids': [], 'batch_ids': [str(uuid4()), str(uuid4())]},
            ):
                self.user({'case': {'view': True, 'edit': True}})
                response = self.client.post(f'{prefix}/preview?case_id={self.db.case.id}', json=selection)
                self.assertEqual(response.status_code, 200, response.text)
                response = self.client.post(f'{prefix}/confirm?case_id={self.db.case.id}',
                    json={**selection, 'expected_revision': response.json()['revision']})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()['removed'])
                self.assertEqual(remove.call_args.kwargs['case_id'], self.db.case.id)
                self.assertEqual([str(value) for value in remove.call_args.kwargs['file_ids']], selection['file_ids'])
                self.assertEqual([str(value) for value in remove.call_args.kwargs['batch_ids']], selection['batch_ids'])
                self.assertEqual(remove.call_args.kwargs['expected_revision'], 'a'*64)
            import_statement.assert_not_called()

    def test_removal_routes_require_case_edit_and_valid_revision(self):
        prefix = '/api/financial/statement-import/removals'
        body = {'file_ids': [str(self.file_id)], 'expected_revision': 'a'*64}
        with patch('services.financial.import_removal.remove_imports') as remove:
            url = f'{prefix}/confirm?case_id={self.db.case.id}'
            self.assertEqual(self.client.post(url, json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.post(url, json={**body, 'expected_revision': 'stale'}).status_code, 422)
            remove.assert_not_called()

    def test_bulk_currency_requires_case_edit_and_selected_revisions(self):
        url = f'/api/financial/statement-import/batches/{uuid4()}/currency?case_id={self.db.case.id}'
        body = dict(currency='MXN', statements=[dict(id=str(uuid4()), revision='a'*64)])
        with patch.object(module.import_batches, 'set_selected_currency', return_value={}) as save, patch.object(module, 'actor_from_user'):
            self.assertEqual(self.client.post(url, json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            save.assert_not_called()
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.post(url, json=body).status_code, 200)
            self.assertEqual(save.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(save.call_args.kwargs['currency'], 'MXN')
            self.assertEqual(self.client.post(url, json={**body, 'statements': []}).status_code, 422)

    def test_refresh_statement_list_requires_case_edit(self):
        batch_id = uuid4()
        url = f'/api/financial/statement-import/batches/{batch_id}/refresh-statements?case_id={self.db.case.id}'
        with patch.object(module.import_batches, 'refresh_statement_list', return_value={'queued': True}) as refresh:
            self.assertEqual(self.client.post(url).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(url).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(url).status_code, 403)
            refresh.assert_not_called()
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.post(url).status_code, 200)
            self.assertEqual(refresh.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(refresh.call_args.kwargs['batch_id'], batch_id)

    def test_direct_batch_confirmation_requires_edit_and_passes_review_revision(self):
        self.db.get_bind = lambda: None
        batch_id, item_id = uuid4(), uuid4()
        url = f'/api/financial/statement-import/batches/{batch_id}/items/{item_id}/confirm?case_id={self.db.case.id}'
        body = dict(expected_review_revision='b'*64, request=dict(expected_revision='a'*64,
            currency='USD', holder='Reviewed owner', account_number='00123', rows=[dict(id='row')]))
        with patch.object(module.import_batches, 'confirm_review', return_value={}) as save, patch.object(module, 'actor_from_user'), patch.object(module, 'sessionmaker'):
            self.assertEqual(self.client.post(url, json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            save.assert_not_called()
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.post(url, json=body).status_code, 200)
            self.assertEqual(save.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(save.call_args.kwargs['batch_id'], batch_id)
            self.assertEqual(save.call_args.kwargs['item_id'], item_id)
            self.assertEqual(save.call_args.kwargs['expected_review_revision'], 'b'*64)
            self.assertEqual(save.call_args.kwargs['request'].holder, 'Reviewed owner')
            self.assertEqual(self.client.post(url, json={**body, 'expected_review_revision': 'stale'}).status_code, 422)

    def test_imported_details_require_case_edit_permission(self):
        url = f'/api/financial/statement-import/sources/{self.file_id}/details?case_id={self.db.case.id}'
        body = dict(expected_revision='a'*64, holder='Holder', account_number='00123', institution='Bank')
        with patch.object(module, 'read_statement_details', return_value={}) as read, patch.object(module, 'update_statement_details', return_value={}) as save, patch.object(module, 'actor_from_user'):
            self.assertEqual(self.client.get(url).status_code, 401)
            self.assertEqual(self.client.put(url, json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.put(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.put(url, json=body).status_code, 403)
            save.assert_not_called()
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.put(url, json=body).status_code, 200)
            self.assertEqual(save.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(save.call_args.kwargs['request'].account_number, '00123')

    def test_refresh_reading_requires_case_edit_and_passes_revision(self):
        self.db.get_bind = lambda: None
        url = f'/api/financial/statement-import/sources/{self.file_id}/refresh-reading?case_id={self.db.case.id}'
        body = dict(expected_revision='a'*64)
        with patch('services.financial.legacy_statement_refresh.refresh_legacy_import', return_value={}) as refresh, patch.object(module, 'actor_from_user'), patch.object(module, 'sessionmaker'):
            self.assertEqual(self.client.post(url, json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(url, json=body).status_code, 403)
            refresh.assert_not_called()
            self.user({'case': {'view': True, 'edit': True}})
            self.assertEqual(self.client.post(url, json=body).status_code, 200)
            self.assertEqual(refresh.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(refresh.call_args.kwargs['source_id'], self.file_id)
            self.assertEqual(refresh.call_args.kwargs['expected_revision'], body['expected_revision'])
            self.assertEqual(self.client.post(url, json={'expected_revision': 'stale'}).status_code, 422)

    def test_unauthenticated_requests_do_not_reach_statement_services(self):
        with patch.object(module,'read_statement_import') as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,401)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,401)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,401)
        read.assert_not_called();write.assert_not_called();version.assert_not_called()

    def test_non_member_cannot_read_or_mutate(self):
        self.user(None)
        with patch.object(module,'read_statement_import') as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        read.assert_not_called();write.assert_not_called();version.assert_not_called()

    def test_viewer_can_review_but_cannot_import_or_reprocess(self):
        self.user({'case':{'view':True,'edit':False},'evidence':{'upload':False}})
        with patch.object(module,'read_statement_import',return_value={'available':True}) as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,200)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        self.assertEqual(read.call_args.kwargs['case_id'],self.db.case.id)
        write.assert_not_called();version.assert_not_called()

    def test_arithmetic_checks_are_case_scoped_read_only_and_revision_bound(self):
        body=dict(expected_revision='a'*64, currency='EUR', rows=[])
        with patch.object(module, 'read_statement_import') as read:
            self.assertEqual(self.client.post(self.endpoint('/checks'), json=body).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.post(self.endpoint('/checks'), json=body).status_code, 403)
            read.assert_not_called()
            self.user({'case': {'view': True, 'edit': False}})
            read.return_value=dict(revision='a'*64, currency='EUR', metadata={}, rows=[])
            response=self.client.post(self.endpoint('/checks'), json=body)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['applied'])
            self.assertEqual(read.call_args.kwargs['case_id'], self.db.case.id)
            self.assertFalse(read.call_args.kwargs['_include_period_checks'])
            body['expected_revision']='b'*64
            self.assertEqual(self.client.post(self.endpoint('/checks'), json=body).status_code, 409)

    def test_saving_review_progress_requires_case_edit(self):
        with patch.object(module, 'save_progress') as save:
            self.assertEqual(self.client.put(self.endpoint('/progress'), json={}).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.put(self.endpoint('/progress'), json={}).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.put(self.endpoint('/progress'), json={}).status_code, 403)
            save.assert_not_called()

    def test_row_assignment_preview_and_apply_require_case_edit(self):
        with patch.object(module, 'reassign_rows') as move:
            for suffix in ('/row-assignment/preview', '/row-assignment/apply'):
                self.app.dependency_overrides.clear()
                self.assertEqual(self.client.post(self.endpoint(suffix), json={}).status_code, 401)
                self.user(None)
                self.assertEqual(self.client.post(self.endpoint(suffix), json={}).status_code, 403)
                self.user({'case': {'view': True, 'edit': False}})
                self.assertEqual(self.client.post(self.endpoint(suffix), json={}).status_code, 403)
            move.assert_not_called()

    def test_previous_reviews_require_case_view_and_comparison_requires_edit(self):
        with patch.object(module, 'previous_review_detail', return_value={'found': True}) as read, patch.object(module, 'acknowledge_recovery') as write:
            endpoint = self.endpoint('/previous-reviews/' + 'a' * 64)
            compare = self.endpoint('/previous-reviews/compare')
            self.assertEqual(self.client.get(endpoint).status_code, 401)
            self.assertEqual(self.client.post(compare, json={}).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.get(endpoint).status_code, 403)
            self.assertEqual(self.client.post(compare, json={}).status_code, 403)
            read.assert_not_called()
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.get(endpoint).status_code, 200)
            self.assertEqual(read.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(self.client.post(compare, json={'expected_revision': 'a' * 64}).status_code, 403)
            write.assert_not_called()

    def test_incomplete_records_require_case_view_and_completion_requires_edit(self):
        read_url = f'/api/financial/statement-import/incomplete-records?case_id={self.db.case.id}'
        write_url = f'/api/financial/statement-import/sources/{uuid4()}/complete-record?case_id={self.db.case.id}'
        with patch('services.financial.imported_records.imported_records', return_value={'records':[], 'total':0}) as read, patch('services.financial.imported_records.complete_record') as write:
            self.assertEqual(self.client.get(read_url).status_code, 401)
            self.assertEqual(self.client.post(write_url, json={}).status_code, 401)
            self.user(None)
            self.assertEqual(self.client.get(read_url).status_code, 403)
            self.assertEqual(self.client.post(write_url, json={}).status_code, 403)
            self.user({'case':{'view':True, 'edit':False}})
            self.assertEqual(self.client.get(read_url).status_code, 200)
            self.assertEqual(read.call_args.kwargs['case_id'], self.db.case.id)
            self.assertEqual(self.client.post(write_url, json={}).status_code, 403)
            self.assertEqual(self.client.get(read_url + '&limit=101').status_code, 422)
            write.assert_not_called()

    def test_case_edit_does_not_grant_evidence_upload_permission(self):
        self.user({'case':{'view':True,'edit':True},'evidence':{'upload':False}})
        with patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        version.assert_not_called()

    def test_reprocess_validates_and_passes_image_reading_method(self):
        self.user({'case':{'view':True},'evidence':{'upload':True}})
        saved = SimpleNamespace(id=uuid4(), engine_job_id='job', status='processing')
        with patch.object(module, 'actor_from_user'), patch.object(module, 'create_statement_version', return_value=saved) as version, patch.object(module, 'process_db_files', AsyncMock()) as process:
            body = {'request_id':str(uuid4()), 'reading_mode':'page_images'}
            self.assertEqual(self.client.post(self.endpoint('/reprocess'), json=body).status_code, 200)
            self.assertEqual(version.call_args.kwargs['reading_mode'], 'page_images')
            version.reset_mock()
            body['reading_mode'] = 'guess'
            self.assertEqual(self.client.post(self.endpoint('/reprocess'), json=body).status_code, 422)
            version.assert_not_called()
            process.assert_not_awaited()

    def test_wire_routes_require_case_access_and_edit_before_saving(self):
        with patch.object(module, 'read_payment_document') as read, patch.object(module, 'save_payment_document') as save:
            for suffix in ('/payment-document/matches', '/payment-document/save'):
                self.assertEqual(self.client.post(self.endpoint(suffix), json={}).status_code, 401)
            self.user(None)
            for suffix in ('/payment-document/matches', '/payment-document/save'):
                self.assertEqual(self.client.post(self.endpoint(suffix), json={}).status_code, 403)
            self.user({'case': {'view': True, 'edit': False}})
            self.assertEqual(self.client.post(self.endpoint('/payment-document/save'), json={}).status_code, 403)
            with patch.object(module, 'matching_payments', return_value={'candidates': []}) as matches:
                response = self.client.post(self.endpoint('/payment-document/matches'), json={
                    'amount': '120.00', 'currency': 'USD', 'value_date': '2021-03-23'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(matches.call_args.kwargs['case_id'], self.db.case.id)
            save.assert_not_called()
            self.assertEqual(read.call_args.kwargs['case_id'], self.db.case.id)

    def test_financial_file_actions_require_case_edit_and_preparation_requires_upload(self):
        with patch.object(module, 'set_financial_file_visibility') as visibility, patch.object(module, 'prepare_existing_financial_file', AsyncMock()) as prepare:
            self.assertEqual(self.client.post(self.endpoint('/visibility'), json={'removed': True, 'expected_revision': 'initial'}).status_code, 401)
            self.user({'case': {'view': True}})
            self.assertEqual(self.client.post(self.endpoint('/visibility'), json={'removed': True, 'expected_revision': 'initial'}).status_code, 403)
            self.assertEqual(self.client.post(self.endpoint('/prepare-existing'), json={'expected_revision': 'initial'}).status_code, 403)
            self.user({'case': {'view': True, 'edit': True}, 'evidence': {'upload': False}})
            self.assertEqual(self.client.post(self.endpoint('/prepare-existing'), json={'expected_revision': 'initial'}).status_code, 403)
            visibility.assert_not_called(); prepare.assert_not_awaited()
            with patch.object(module, 'actor_from_user'):
                visibility.return_value = {'financial_removed': True}
                result = self.client.post(self.endpoint('/visibility'), json={'removed': True, 'expected_revision': 'initial'})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(visibility.call_args.kwargs['case_id'], self.db.case.id)
                self.assertEqual(visibility.call_args.kwargs['evidence_file_id'], self.file_id)

    def test_batch_routes_require_case_access_and_edit(self):
        prefix='/api/financial/statement-import/batches'
        batch=uuid4()
        with patch.object(module.import_batches,'create_batch') as create, patch.object(module.import_batches,'queue_import') as write, patch.object(module.import_batches,'batch_status',return_value={'ready':1}) as read:
            self.assertEqual(self.client.get(f'{prefix}/{batch}?case_id={self.db.case.id}').status_code,401)
            self.user(None)
            self.assertEqual(self.client.get(f'{prefix}/{batch}?case_id={self.db.case.id}').status_code,403)
            self.user({'case':{'view':True,'edit':False},'evidence':{'upload':False}})
            self.assertEqual(self.client.get(f'{prefix}/{batch}?case_id={self.db.case.id}').status_code,200)
            self.assertEqual(self.client.post(f'{prefix}?case_id={self.db.case.id}',json={'request_id':str(uuid4()),'file_ids':[str(self.file_id)]}).status_code,403)
            self.assertEqual(self.client.post(f'{prefix}/{batch}/confirm?case_id={self.db.case.id}',json={'expected_ready_revision':'a'*64}).status_code,403)
            self.assertEqual(self.client.put(f'{prefix}/{batch}/items/{uuid4()}?case_id={self.db.case.id}',json={}).status_code,403)
            create.assert_not_called();write.assert_not_called()
            self.assertEqual(read.call_args.kwargs['case_id'],self.db.case.id)
