"""Every route that records a manual change, with its own recording settings: a save that commits writes exactly one
inbox line of its kind, a refused save writes none, and a failed append is added once by the sync."""
import asyncio
import inspect
import typing
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services import manual_changes as mc
from tests.test_manual_changes import FeedTestBase

PERSON = SimpleNamespace(id=uuid.uuid4(), name='Alex Reviewer', email='alex@example.com')
CASE = uuid.UUID('11111111-2222-3333-4444-555555555555')
SKIP_VALUES = {'preview', 'check'}

# Every kind the inventory (docs/manual-change-feed.md) lists as recorded by a route decorator.
ROUTE_KINDS = {
    'candidate_review', 'quarantine', 'release', 'file_admit', 'transaction_correction', 'duplicate_decision',
    'duplicate_keep_copy', 'reader_replacement_restore', 'candidate_finalize', 'account_party', 'counterparty_party',
    'model_attempt_abandon', 'payment_label_change', 'payment_label_confirm', 'payment_label_remove',
    'category_apply_like', 'category_rule_save', 'category_rule_retire', 'payment_edit', 'account_identity',
    'account_consolidation', 'account_consolidation_undo', 'judgement_confirm', 'model_statement_confirm',
    'judgement_reopen', 'statement_account_details', 'statement_section_split', 'statement_details', 'account_type',
    'row_direction_flip', 'account_details', 'account_details_confirm', 'account_details_undo',
    'duplicate_disposition', 'not_payment_statement', 'payment_document_review', 'manual_payment',
    'record_withdrawal', 'record_restore', 'record_completion', 'row_assignment', 'review_recovery_ack',
    'statement_currency', 'file_currency', 'layout_memory_confirm', 'layout_memory_withdraw', 'field_proposal_group',
    'statement_save', 'statement_review_confirm', 'page_image_offer_accept', 'page_image_offer_decline',
    'page_rows_confirm', 'batch_item_skip', 'transaction_category', 'transaction_from_to', 'transaction_details',
    'transaction_amount', 'transaction_bulk_correct', 'sub_transaction_link', 'sub_transaction_unlink',
    'entity_property_edit', 'entity_location_correct', 'entity_location_remove', 'insight_confirm', 'insight_reject',
    'fact_pin', 'entity_merge', 'merge_suggestion_reject', 'merge_suggestion_unreject', 'entity_delete',
    'entity_restore', 'transcript_speaker_correct', 'evidence_relevance_set', 'device_name_override',
    'significant_entity_add', 'significant_entity_remove', 'significant_entity_clear', 'workspace_ai_accept',
    'workspace_ai_reject', 'attention_dismiss', 'attention_clear', 'timeline_event_add', 'statement_draft_edit',
}


def decorated_routes():
    from main import app
    seen = {}
    for route in app.routes:
        endpoint = getattr(route, 'endpoint', None)
        config = getattr(endpoint, 'manual_change', None)
        if config is not None:
            seen[f"{sorted(route.methods)[0]} {route.path}"] = (endpoint, config)
    return seen


def _pick(annotation):
    if typing.get_origin(annotation) is typing.Literal:
        options = [o for o in typing.get_args(annotation) if o not in SKIP_VALUES]
        return options[0]
    return None


def _model(cls):
    values = {}
    for name, info in cls.model_fields.items():
        picked = _pick(info.annotation)
        if picked is not None:
            values[name] = picked
    return cls.model_construct(**values)


def synthetic_kwargs(endpoint, session):
    out = {}
    for name, param in inspect.signature(endpoint.__wrapped__).parameters.items():
        annotation = param.annotation
        args = [a for a in typing.get_args(annotation) if inspect.isclass(a)] if typing.get_origin(annotation) in (
            typing.Union, getattr(__import__('types'), 'UnionType', typing.Union)) else []
        if name == 'db' or annotation is Session:
            out[name] = session
        elif name in ('current_user', 'user', 'current_db_user'):
            out[name] = PERSON
        elif name == 'case_id':
            out[name] = CASE
        elif _pick(annotation) is not None:
            out[name] = _pick(annotation)
        elif inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            out[name] = _model(annotation)
        elif args and inspect.isclass(args[0]) and issubclass(args[0], BaseModel):
            out[name] = _model(args[0])
        elif annotation is uuid.UUID:
            out[name] = uuid.uuid4()
        elif annotation is int:
            out[name] = 1
        elif annotation is bool:
            out[name] = False
        else:
            out[name] = 'k1'
    return out


class EveryRouteKindTests(FeedTestBase):
    @classmethod
    def setUpClass(cls):
        cls.routes = decorated_routes()

    def setUp(self):
        super().setUp()
        for name, value in (('producer_for', mock.Mock(return_value=('reader@1', 'layout-a'))),
                            ('_own_session', lambda: Session(self.engine))):
            patcher = mock.patch.object(mc, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, endpoint, config, outcome):
        """The route's own recording settings around a stand-in for its service (``outcome`` runs as the save)."""
        def stand_in(**kwargs):
            return outcome()
        stand_in.__signature__ = inspect.signature(endpoint.__wrapped__)
        wrapped = mc.records(**config)(stand_in)
        with Session(self.engine) as session:
            kwargs = synthetic_kwargs(endpoint, session)
            return wrapped(**kwargs)

    def test_every_inventoried_kind_has_a_route_and_every_route_a_kind(self):
        kinds = set()
        for endpoint, config in self.routes.values():
            kind = config['kind']
            kinds.add(kind if isinstance(kind, str) else '?')
        self.assertEqual(kinds, ROUTE_KINDS)

    def test_each_route_writes_one_line_after_its_save_and_none_when_refused(self):
        for key, (endpoint, config) in sorted(self.routes.items()):
            with self.subTest(route=key):
                self.inbox.write_text('')
                self.call(endpoint, config, lambda: {'ok': True})
                lines = self.lines()
                self.assertEqual(len(lines), 1, key)
                self.assertEqual(lines[0]['kind'], config['kind'])
                self.assertEqual(lines[0]['actor'], 'person')
                self.assertTrue(lines[0]['pattern_key'].startswith(config['kind'] + '|'))

                self.inbox.write_text('')

                def refused():
                    raise HTTPException(status_code=409, detail='refused')
                with self.assertRaises(HTTPException):
                    self.call(endpoint, config, refused)
                self.assertEqual(self.lines(), [], key)

    def test_each_route_change_whose_append_failed_is_added_once_by_the_sync(self):
        for key, (endpoint, config) in sorted(self.routes.items()):
            with self.subTest(route=key):
                self.inbox.write_text('')
                with mock.patch.object(mc, 'append', side_effect=OSError('disk full')):
                    self.call(endpoint, config, lambda: {'ok': True})
                self.assertEqual(self.lines(), [])
                with Session(self.engine) as session:
                    self.assertEqual(mc.check(session)['appended'], 1)
                    self.assertEqual(mc.check(session)['appended'], 0)
                    session.query(mc_model()).delete()
                    session.commit()

    def test_an_async_route_records_after_it_returns(self):
        async def route(case_id=None, current_user=None):
            return {'ok': True}
        wrapped = mc.records('entity_merge', 'change')(route)
        self.assertTrue(inspect.iscoroutinefunction(wrapped))
        asyncio.run(wrapped(case_id=CASE, current_user=PERSON))
        self.assertEqual([line['kind'] for line in self.lines()], ['entity_merge'])

    def test_a_route_without_a_body_never_records_the_callers_identity_as_the_value(self):
        def route(node_key='', case_id=None, user=None):
            return {'ok': True}
        mc.records('entity_delete', 'set_aside', subject_type='entity')(route)(
            node_key='n1', case_id=CASE, user={'username': 'alex@example.com'})
        line = self.lines()[0]
        self.assertNotIn('alex@example.com', str(line['after']))
        self.assertEqual(line['subject_id'], 'n1')

    def test_the_payments_a_change_applies_to_are_its_subject_not_a_field(self):
        def route(body=None, case_id=None, current_user=None):
            return {'ok': True}
        mc.records('payment_label_change', 'change')(route)(
            body={'transactions': [{'id': 't1', 'version': 0}], 'to_name': 'X'}, case_id=CASE, current_user=PERSON)
        self.assertEqual(self.lines()[0]['field'], 'to_name')
        self.assertEqual((self.lines()[0]['subject_type'], self.lines()[0]['subject_id']), ('transaction', 't1'))

    def test_the_route_signature_fastapi_reads_is_unchanged(self):
        for key, (endpoint, _config) in self.routes.items():
            with self.subTest(route=key):
                self.assertEqual(inspect.signature(endpoint), inspect.signature(endpoint.__wrapped__))


def mc_model():
    from postgres.models.manual_change import ManualChange
    return ManualChange


if __name__ == '__main__':
    unittest.main()
