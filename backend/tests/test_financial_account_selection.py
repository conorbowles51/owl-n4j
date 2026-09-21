import json
import unittest
from services.financial.transaction_query import list_transactions
from services.financial.ledger_snapshot import capture_ledger_snapshot
from services.financial.working_totals import working_ledger_summary
from services.financial.candidate_store import list_candidate_accounts
from tests.test_financial_ledger_summary import LedgerSummaryTests

class AccountSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=LedgerSummaryTests(); self.f.setUp()
        self.second=self.f._account(self.f.case.id)
        self.second.identity_key='second-bank'
        self.f.db.add(self.second); self.f.db.commit()
    def tearDown(self): self.f.tearDown()
    def test_same_selection_for_transactions_totals_snapshot_and_new_ingestion(self):
        f=self.f
        a,doc=f.add(100); b,doc=f.add(200); c,doc=f.add(300)
        a.account.holder_name='Example Company'
        b.account_id=self.second.id; self.second.holder_name='Other Company'
        f.db.commit()
        chosen=dict(account_holders=[' example  company ', 'Other Company'], account_ids=[f.account.id, self.second.id])
        rows=list_transactions(f.db,f.case.id,**chosen)
        self.assertEqual({r.id for r in rows},{a.id,b.id,c.id})
        snapshot=json.loads(capture_ledger_snapshot(f.db,case_id=f.case.id,**chosen).content)['ledger']
        self.assertEqual({r['row']['key'] for r in snapshot['readings']},{str(r.id) for r in rows})
        self.assertEqual(working_ledger_summary(f.db,case_id=f.case.id,**chosen)['included_rows'],3)
        only_other=dict(account_holders=['Other Company'],account_ids=[f.account.id])
        self.assertEqual(list_transactions(f.db,f.case.id,**only_other),[])
        f.add(400)
        self.assertEqual(len(list_transactions(f.db,f.case.id,account_holders=['example company'])),3)
        self.assertEqual(list_transactions(f.db,f.other_case.id,**chosen),[])
    def test_directory_pagination_is_complete(self):
        f=self.f
        first=list_candidate_accounts(f.db,case_id=f.case.id,limit=1)
        second=list_candidate_accounts(f.db,case_id=f.case.id,limit=1,offset=1)
        self.assertTrue(first['has_more'])
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
