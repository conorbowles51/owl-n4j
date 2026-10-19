from uuid import uuid4, UUID
from sqlalchemy import select, func
from postgres.models.financial import FinancialAccount, FinancialStatementPeriod, FinancialTransaction
from services.financial.account_identity import IdentityRequest, identity_state, save_identity, matches_identifier
from services.financial.account_parties import AccountPartyError, AccountPartyRequest, account_parties, set_account_party
from services.financial.identity_graph import identity_graph_plan
from tests.test_financial_duplicates import DuplicateTestCase


class AccountIdentityTests(DuplicateTestCase):
    def request(self, **changes):
        values = dict(account_id=self.account.id, expected_revision=identity_state(self.db, self.case.id)['revision'],
            identifiers=[dict(kind='clabe', value='012345678901234567')], basis={'basis':'investigator_knowledge'}, reason='Reviewed original account instructions')
        return IdentityRequest(**{**values, **changes})

    def save(self, request, **kwargs):
        return save_identity(self.db, case_id=self.case.id, request=request, actor=self.actor, **kwargs)

    def test_aliases_are_typed_audited_and_idempotent_without_rewriting_printed_account(self):
        printed = self.account.identifier_as_printed
        request = self.request(identifiers=[dict(kind='clabe',value='012345678901234567'), dict(kind='customer_number',value='9988776655')])
        state = self.save(request)
        self.assertTrue(state['applied'])
        self.assertFalse(self.save(request)['applied'])
        self.assertTrue(matches_identifier(self.account, 'clabe', '012345678901234567'))
        self.assertFalse(matches_identifier(self.account, 'account', '9988776655'))
        self.assertEqual(self.account.identifier_as_printed, printed)
        self.assertEqual(len(state['identity_history']), 1)
        self.save(self.request(identifiers=[]))
        self.assertFalse(matches_identifier(self.account, 'clabe', '012345678901234567'))
        self.assertEqual(len(identity_state(self.db, self.case.id)['identity_history']), 2)

    def test_reference_creates_no_transactions_or_periods_and_can_gain_reviewed_owner(self):
        before = [self.db.scalar(select(func.count()).select_from(model)) for model in (FinancialTransaction, FinancialStatementPeriod)]
        identifier = uuid4()
        state = self.save(self.request(account_id=identifier, reference={'institution':'Other bank', 'holder':'Example company', 'currency':'GBP'}))
        self.assertEqual(before, [self.db.scalar(select(func.count()).select_from(model)) for model in (FinancialTransaction, FinancialStatementPeriod)])
        account = next(a for a in state['accounts'] if a['id'] == str(identifier))
        self.assertTrue(account['referenced_only'])
        directory = account_parties(self.db, case_id=self.case.id)
        set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(expected_revision=directory['revision'], account_ids=[identifier, self.account.id], new_party_name='Example company', relationship={'role':'holder'}, reason='Reviewed ownership documents'), actor=self.actor)
        plan = identity_graph_plan(self.db, self.case.id)
        self.assertEqual(len(plan['parties']), 1)
        self.assertEqual({p['type'] for p in plan['links']}, {'HOLDS_ACCOUNT'})
        self.assertEqual(len(plan['links']), 2)
        self.assertTrue(next(a for a in plan['accounts'] if a['ledger_account_id'] == str(identifier))['financial_referenced_only'])

    def test_stale_and_cross_case_identity_changes_are_rejected(self):
        stale = self.request()
        self.save(self.request(identifiers=[dict(kind='account_number', value='NEW-0001')]))
        with self.assertRaisesRegex(AccountPartyError, 'changed'):
            self.save(stale)
        foreign = self._account(self.other_case.id, identity_key='foreign-identity')
        self.db.add(foreign); self.db.commit()
        with self.assertRaisesRegex(AccountPartyError, 'not found'):
            self.save(self.request(account_id=foreign.id))

    def test_general_entity_link_is_explicit_scoped_and_preserves_relationship_roles(self):
        directory = account_parties(self.db, case_id=self.case.id)
        owned = set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(expected_revision=directory['revision'], account_ids=[self.account.id], new_party_name='Example company', relationship={'role':'controller'}, reason='Reviewed controller'), actor=self.actor)
        party = owned['parties'][0]['id']
        request = self.request(entity_links=[{'party_id':party, 'entity_key':'case-company-17'}])
        with self.assertRaisesRegex(AccountPartyError, 'entity in this case'):
            self.save(request, entity_lookup=lambda key, case: None)
        self.save(request, entity_lookup=lambda key, case: {'key':key} if case == str(self.case.id) else None)
        plan = identity_graph_plan(self.db, self.case.id)
        self.assertEqual(plan['links'][0]['type'], 'CONTROLS_ACCOUNT')
        self.assertEqual(plan['entity_links'][0]['target'], 'case-company-17')
        self.assertEqual(plan['entity_links'][0]['source'], 'financial-party:' + party)


def test_graph_projection_shutdown_waits_for_current_case_before_clients_close(monkeypatch):
    import asyncio
    from threading import Event
    from services.financial import identity_graph
    entered, finished = Event(), Event()
    def project(stop):
        entered.set()
        assert stop.wait(5)
        finished.set()
    monkeypatch.setattr(identity_graph, 'sync_saved_identities', project)
    async def scenario():
        task = asyncio.create_task(identity_graph.run_identity_graph_forever())
        while not entered.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert finished.is_set()
    asyncio.run(scenario())
