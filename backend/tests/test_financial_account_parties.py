import uuid
from sqlalchemy import select
from services.financial.account_parties import AccountPartyError, AccountPartyRequest, account_parties, set_account_party
from postgres.models.financial import FinancialAccount, AdjudicationEvent
from tests.test_financial_duplicates import DuplicateTestCase


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
