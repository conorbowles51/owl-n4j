import uuid
from sqlalchemy import select
from services.financial.account_parties import AccountPartyError, AccountPartyRequest, account_parties, set_account_party
from postgres.models.financial import FinancialAccount, AdjudicationEvent
from tests.test_financial_duplicates import DuplicateTestCase
from services.financial.account_relationships import owners_on
from services.financial.account_selection import holder_account_ids
from services.financial.candidate_store import list_candidate_accounts
from pydantic import ValidationError


class AccountPartyTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.make_copy()
        self.account = self.db.scalar(select(FinancialAccount).where(FinancialAccount.case_id == self.case.id))

    def state(self):
        return account_parties(self.db, case_id=self.case.id)

    def assign(self, **kwargs):
        args = dict(expected_revision=self.state()['revision'], account_ids=[self.account.id],
                    new_party_name='Reviewed person', reason='Checked the account-holder source')
        args.update(kwargs)
        return set_account_party(self.db, case_id=self.case.id,
            request=AccountPartyRequest(**args), actor=self.actor)

    def test_assign_and_clear_replay_without_changing_source_account(self):
        original_holder = self.account.holder_name
        result = self.assign()
        self.assertEqual(result['accounts'][0]['party']['name'], 'Reviewed person')
        self.assertTrue(result['applied'])
        self.db.expire_all()
        self.assertEqual(self.state()['accounts'][0]['party'], result['parties'][0])
        cleared = self.assign(clear=True, new_party_name=None)
        self.assertIsNone(cleared['accounts'][0]['party'])
        self.assertEqual(len(cleared['history']), 2)
        self.assertEqual(len(cleared['parties']), 1)
        self.assertEqual(self.account.holder_name, original_holder)

    def test_stale_retry_cannot_append_another_group(self):
        revision = self.state()['revision']
        self.assign()
        with self.assertRaises(AccountPartyError) as caught:
            self.assign(expected_revision=revision)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(self.state()['history']), 1)

    def test_unknown_account_or_other_case_party_refused(self):
        for changes in [dict(account_ids=[uuid.uuid4()]),dict(new_party_name=None,party_id=uuid.uuid4())]:
            with self.assertRaises(AccountPartyError):
                self.assign(**changes)
        self.assertEqual(self.state()['history'], [])

    def test_existing_group_can_be_reused_after_clear(self):
        party = self.assign()['parties'][0]
        self.assign(new_party_name=None, clear=True)
        result = self.assign(new_party_name=None, party_id=party['id'])
        self.assertEqual(result['accounts'][0]['party'], party)
        self.assertEqual(len(result['history']), 3)

    def test_inconsistent_history_is_not_silently_repaired(self):
        self.assign()
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.decision == 'set_account_party'))
        event.before = {'party': {'id': str(uuid.uuid4()), 'name':'Unrecorded'}}
        self.db.flush()
        with self.assertRaises(AccountPartyError): self.state()

    def test_reviewed_joint_holders_survive_reopen_and_shared_selection(self):
        original = self.account.holder_name
        first = self.assign(relationship={'role': 'holder'})
        alice = first['parties'][0]
        result = self.assign(new_party_name='Joint holder', relationship={'role': 'holder'})
        self.db.expire_all()
        account = self.state()['accounts'][0]
        self.assertIsNone(account['party'])  # No legacy grouping was manufactured.
        self.assertEqual(len(account['holder_parties']), 2)
        self.assertEqual(len(owners_on(account)), 2)
        for person in account['holder_parties']:
            self.assertEqual(holder_account_ids(self.db, self.case.id, ['party:' + person['id']]), [self.account.id])
        directory = list_candidate_accounts(self.db, case_id=self.case.id)
        self.assertEqual({p['id'] for p in directory['items'][0]['holder_parties']}, {p['id'] for p in result['parties']})
        self.assertEqual(self.account.holder_name, original)
        self.assertIn(alice, account['holder_parties'])

    def test_controller_and_signatory_do_not_become_owner_filters(self):
        for role in ('controller', 'signatory', 'analysis_group'):
            result = self.assign(new_party_name=role, relationship={'role': role})
            person = next(p for p in result['parties'] if p['name'] == role)
            self.assertEqual(holder_account_ids(self.db, self.case.id, ['party:' + person['id']]), [])
        self.assertEqual(owners_on(self.state()['accounts'][0]), [])

    def test_edit_then_unlink_one_holder_keeps_other_holder_and_history(self):
        first = self.assign(relationship={'role': 'holder'})
        person = first['parties'][0]
        link = first['accounts'][0]['relationships'][0]
        self.assign(new_party_name='Other holder', relationship={'role': 'holder'})
        self.assign(new_party_name=None, party_id=person['id'], relationship={
            'id':link['id'], 'role':'holder', 'effective_from':'2025-01-01', 'effective_to':'2025-12-31'})
        account = self.state()['accounts'][0]
        self.assertEqual(len(account['relationships']), 2)
        self.assertEqual({p['name'] for p in owners_on(account, '2025-06-01')}, {'Reviewed person', 'Other holder'})
        for day in (None, '2024-12-31', '2026-01-01'):
            self.assertEqual([p['name'] for p in owners_on(account, day)], ['Other holder'])
        self.assign(new_party_name=None, clear=True, relationship={'id':link['id']})
        reopened = self.state()
        self.assertEqual([p['name'] for p in reopened['accounts'][0]['holder_parties']], ['Other holder'])
        self.assertEqual(len(reopened['history']), 4)

    def test_legacy_group_never_becomes_a_reviewed_owner(self):
        self.assign()
        account = self.state()['accounts'][0]
        self.assertEqual(account['party']['name'], 'Reviewed person')
        self.assertEqual(owners_on(account), [])
        self.assign(new_party_name='Actual holder', relationship={'role':'holder'})
        self.assign(new_party_name=None, clear=True)
        self.assertEqual([p['name'] for p in owners_on(self.state()['accounts'][0])], ['Actual holder'])

    def test_existing_identity_reused_across_banks_and_currencies(self):
        account = self._account(self.case.id, identity_key='another-bank-87654')
        account.institution_name, account.currency = 'Another bank', 'USD'
        self.db.add(account); self.db.commit()
        result = self.assign(account_ids=[self.account.id, account.id], relationship={'role':'holder'})
        person = result['parties'][0]
        self.assertEqual(set(holder_account_ids(self.db, self.case.id, ['party:' + person['id']])), {self.account.id, account.id})
        with self.assertRaisesRegex(AccountPartyError, 'already exists'):
            self.assign(account_ids=[account.id], new_party_name='  REVIEWED   person ', relationship={'role':'holder'})

    def test_source_scope_validation_and_stale_save_are_atomic(self):
        revision = self.state()['revision']
        with self.assertRaisesRegex(AccountPartyError, 'not found in this case'):
            self.assign(relationship={'basis':'source','sources':[{'source_document_id':str(uuid.uuid4()),'page_number':1}]})
        self.assertEqual(self.state()['revision'], revision)
        self.assign(relationship={'role':'holder'})
        with self.assertRaises(AccountPartyError) as error:
            self.assign(expected_revision=revision,new_party_name='Retry',relationship={'role':'holder'})
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.state()['history']), 1)

    def test_missing_basis_reversed_dates_and_wrong_account_link_are_refused(self):
        for relationship in ({'basis':'source'}, {'effective_from':'2026-02-01','effective_to':'2026-01-01'}):
            with self.assertRaises(ValidationError): self.assign(relationship=relationship)
        with self.assertRaises(AccountPartyError): self.assign(relationship={'id':str(uuid.uuid4())})
        self.assertEqual(self.state()['history'], [])

    def test_corrupt_relationship_history_is_reported(self):
        self.assign(relationship={'role':'holder'})
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.decision == 'set_account_party'))
        event.after = {**event.after, 'relationships':[{'role':'holder'}]}
        self.db.flush()
        with self.assertRaisesRegex(AccountPartyError, 'malformed'): self.state()
