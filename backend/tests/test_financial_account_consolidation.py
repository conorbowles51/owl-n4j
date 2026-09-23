import copy
import unittest
from uuid import uuid4, UUID
from services.financial.account_consolidation import consolidation_state, ConsolidationRequest, UndoConsolidationRequest, save_consolidation, undo_consolidation
from services.financial.account_parties import AccountPartyError
from services.financial.decisions import Actor
from services.financial.transaction_query import list_transactions, to_view
from services.financial.working_totals import working_ledger_summary
from tests.test_financial_account_selection import AccountSelectionTests


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = AccountSelectionTests(); self.fixture.setUp()
        self.f = self.fixture.f
        self.other = self.fixture.second
        self.actor = Actor(name='Reviewer', email='reviewer@example.test')
        self.a, _ = self.f.add(100); self.b, _ = self.f.add(200)
        self.b.account_id = self.other.id
        self.f.account.identifier_as_printed = self.other.identifier_as_printed = '0012345678'
        self.f.db.commit()
    def tearDown(self): self.fixture.tearDown()
    def request(self):
        return ConsolidationRequest(request_id=uuid4(), expected_revision=consolidation_state(self.f.db, self.f.case.id)['revision'], account_ids=[self.f.account.id, self.other.id], retained_id=self.f.account.id, reason='Compared full account identifiers and source statements.')
    def test_merge_replay_scope_and_undo_preserve_postings(self):
        before = copy.deepcopy([(r.id, r.account_id, r.amount_minor, r.provenance) for r in (self.a, self.b)])
        request = self.request()
        saved = save_consolidation(self.f.db, case_id=self.f.case.id, request=request, actor=self.actor)
        self.assertFalse(save_consolidation(self.f.db, case_id=self.f.case.id, request=request, actor=self.actor)['applied'])
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id, account_id=self.other.id)), 2)
        self.assertEqual(working_ledger_summary(self.f.db, case_id=self.f.case.id, account_ids=[self.other.id])['included_rows'], 2)
        self.assertEqual(to_view(self.b, account=self.other).canonical_account_id, str(self.f.account.id))
        request = UndoConsolidationRequest(request_id=uuid4(), expected_revision=saved['revision'], merge_id=saved['merges'][0]['id'], reason='Reviewed and kept separate.')
        undo_consolidation(self.f.db, case_id=self.f.case.id, request=request, actor=self.actor)
        self.assertFalse(undo_consolidation(self.f.db, case_id=self.f.case.id, request=request, actor=self.actor)['applied'])
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id, account_id=self.other.id)), 1)
        self.assertEqual(before, [(r.id, r.account_id, r.amount_minor, r.provenance) for r in (self.a, self.b)])
    def test_conflicts_wrong_case_and_stale_revision_do_not_merge(self):
        request = self.request()
        self.other.identifier_as_printed = '9999999999'; self.f.db.commit()
        with self.assertRaises(AccountPartyError): save_consolidation(self.f.db, case_id=self.f.case.id, request=request, actor=self.actor)
        with self.assertRaisesRegex(AccountPartyError, 'conflicting'):
            save_consolidation(self.f.db, case_id=self.f.case.id, request=self.request(), actor=self.actor)
        with self.assertRaises(AccountPartyError): save_consolidation(self.f.db, case_id=self.f.other_case.id, request=request, actor=self.actor)
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id, account_id=self.other.id)), 1)

    def test_reviewed_counterparty_and_graph_resolve_merge_then_undo(self):
        from services.financial.payment_labels import PaymentLabelsRequest, update_payment_labels
        from services.financial.identity_graph import identity_graph_plan
        from services.financial.account_relationships import owners_on
        from services.financial.account_parties import account_parties, AccountPartyRequest, set_account_party
        directory = account_parties(self.f.db, case_id=self.f.case.id)
        set_account_party(self.f.db, case_id=self.f.case.id, request=AccountPartyRequest(
            expected_revision=directory['revision'], account_ids=[self.other.id], new_party_name='Synthetic owner',
            relationship={'role':'holder'}, reason='Compared synthetic ownership evidence'), actor=self.actor)
        update_payment_labels(self.f.db, case_id=self.f.case.id, actor=self.actor, request=PaymentLabelsRequest(
            transactions=[{'id':self.a.id,'version':0}], counterparty_link={'kind':'account','id':self.other.id}))
        before = identity_graph_plan(self.f.db, self.f.case.id)
        stored = copy.deepcopy(self.a.metadata_)
        saved = save_consolidation(self.f.db, case_id=self.f.case.id, request=self.request(), actor=self.actor)
        merged = identity_graph_plan(self.f.db, self.f.case.id)
        self.assertNotEqual(before['revision'], merged['revision'])
        self.assertEqual(len(merged['account_links']), 1)
        self.assertEqual(merged['payment_links'][0]['target'], merged['account_links'][0]['target'])
        self.assertEqual(to_view(self.a, account=self.f.account).counterparty_link['id'], str(self.f.account.id))
        directory = account_parties(self.f.db, case_id=self.f.case.id)
        self.assertEqual(owners_on(next(a for a in directory['accounts'] if a['id'] == str(self.f.account.id)), '2026-01-01')[0]['name'], 'Synthetic owner')
        undo_consolidation(self.f.db, case_id=self.f.case.id, actor=self.actor, request=UndoConsolidationRequest(
            request_id=uuid4(), expected_revision=saved['revision'], merge_id=saved['merges'][0]['id'], reason='Additional review'))
        undone = identity_graph_plan(self.f.db, self.f.case.id)
        self.assertFalse(undone['account_links'])
        self.assertEqual(before['payment_links'], undone['payment_links'])
        self.assertEqual(stored, self.a.metadata_)
