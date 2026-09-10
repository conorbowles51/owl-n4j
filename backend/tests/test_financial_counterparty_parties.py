from uuid import uuid4
from services.financial.counterparty_parties import counterparty_parties,set_counterparty_party,CounterpartyPartyRequest
from services.financial.account_parties import AccountPartyError
from tests.test_financial_ledger_summary import LedgerSummaryTests

class CounterpartyPartyTests(LedgerSummaryTests):
    def state(self):return counterparty_parties(self.db,case_id=self.case.id)
    def assign(self,rows,**changes):
        args=dict(expected_revision=self.state()['revision'],transaction_ids=[r.id for r in rows],new_party_name='Reviewed recipient',reason='Checked the original payment sources')
        args.update(changes)
        return set_counterparty_party(self.db,case_id=self.case.id,request=CounterpartyPartyRequest(**args),actor=self.actor)
    def test_selected_rows_only_unchanged_money_and_raw_name(self):
        a,_=self.add(100);b,_=self.add(200);c,_=self.add(300)
        for row in (a,b,c):row.counterparty_raw='SIMILAR NAME'
        self.db.commit();before=self.read()
        result=self.assign([a,b]);self.assertTrue(result['applied'])
        links={r['transaction_id']:r['party'] for r in result['readings']}
        self.assertEqual(links[str(a.id)],links[str(b.id)]);self.assertIsNone(links[str(c.id)])
        self.assertEqual(self.read(),before)
        self.assertTrue(all(row.counterparty_raw=='SIMILAR NAME' for row in (a,b,c)))
        self.assign([a],new_party_name=None,clear=True)
        state=self.state();self.assertEqual(len(state['history']),3)
        self.assertIsNone(next(r for r in state['readings'] if r['transaction_id']==str(a.id))['party'])
    def test_stale_wrong_scope_and_unknown_party_fail_atomically(self):
        a,_=self.add();revision=self.state()['revision'];self.assign([a])
        for changes in (dict(expected_revision=revision),dict(transaction_ids=[uuid4()]),dict(new_party_name=None,party_id=uuid4())):
            with self.assertRaises(AccountPartyError):self.assign([a],**changes)
        self.assertEqual(len(self.state()['history']),1)
    def test_amount_correction_inherits_and_explicit_clear_overrides(self):
        from services.financial.corrections import correct_transaction
        from services.financial.duplicate_decisions import duplicate_revision
        from postgres.models.financial import FinancialTransaction
        a,doc=self.add();a.counterparty_raw='Original label';doc.metadata_={'source_shape':'statement_document'};self.db.commit()
        assigned=self.assign([a]);party=assigned['parties'][0]
        correct_transaction(self.db,case_id=self.case.id,transaction_id=a.id,amount_minor=101,direction='credit',expected_revision=duplicate_revision(self.db,doc),actor=self.actor,reason='Synthetic amount correction')
        self.db.refresh(a);replacement=self.db.get(FinancialTransaction,a.superseded_by_id)
        inherited=next(r for r in self.state()['readings'] if r['transaction_id']==str(replacement.id))
        self.assertEqual(inherited['party'],party);self.assertEqual(inherited['decision_transaction_id'],str(a.id))
        self.assign([replacement],new_party_name=None,clear=True)
        self.assertIsNone(next(r for r in self.state()['readings'] if r['transaction_id']==str(replacement.id))['party'])
    def test_captured_identity_analysis_groups_selected_rows_with_exact_sources(self):
        import hashlib,json
        from services.financial.ledger_snapshot import LedgerExport,LedgerSnapshot,capture_ledger_snapshot,_capture_history
        from services.financial.counterparty_parties import counterparty_party_analysis
        a,_=self.add(100);b,_=self.add(200);c,_=self.add(300)
        for row in (a,b,c):row.counterparty_raw='Same raw name'
        self.db.commit();self.assign([a,b])
        base=capture_ledger_snapshot(self.db,case_id=self.case.id)
        document=_capture_history(self.db,json.loads(base.content),case_id=self.case.id)
        content=json.dumps(document,sort_keys=True,separators=(',',':'))
        export=LedgerExport(LedgerSnapshot(content,hashlib.sha256(content.encode()).hexdigest(),len(content.encode())),'{}')
        result=counterparty_party_analysis(export)
        self.assertEqual(len(result['counterparties']),2)
        linked=next(g for g in result['counterparties'] if g['party'])
        self.assertEqual(set(linked['transaction_ids']),{str(a.id),str(b.id)})
        self.assertEqual(linked['credits_minor'],'300');self.assertEqual(linked['raw_labels'],['Same raw name'])
        self.assertEqual(sum(int(g['credits_minor']) for g in result['counterparties']),600)
        self.assertEqual(result['snapshot_json'],content)
        self.assertEqual(result['snapshot_sha256'],export.snapshot.sha256)
        self.assertFalse(self.db.new or self.db.dirty)

    def test_payment_created_party_can_be_reused_for_account_and_survives_clear(self):
        from services.financial.account_parties import account_parties, set_account_party, AccountPartyRequest
        row,_=self.add(100)
        original=self.read()
        old_state=account_parties(self.db,case_id=self.case.id)
        party=self.assign([row])['parties'][0]
        state=account_parties(self.db,case_id=self.case.id)
        self.assertIn(party,state['parties'])
        self.assertNotEqual(state['revision'],old_state['revision'])
        request=dict(account_ids=[row.account_id],party_id=party['id'],reason='Reuse the explicitly reviewed synthetic identity')
        with self.assertRaises(AccountPartyError):
            set_account_party(self.db,case_id=self.case.id,request=AccountPartyRequest(expected_revision=old_state['revision'],**request),actor=self.actor)
        result=set_account_party(self.db,case_id=self.case.id,request=AccountPartyRequest(expected_revision=state['revision'],**request),actor=self.actor)
        self.assertEqual(next(a for a in result['accounts'] if a['id']==str(row.account_id))['party'],party)
        self.assign([row],new_party_name=None,clear=True)
        self.db.expire_all()
        self.assertIn(party,account_parties(self.db,case_id=self.case.id)['parties'])
        self.assertNotIn(party,account_parties(self.db,case_id=self.other_case.id)['parties'])
        self.assertEqual(self.read(),original)

    def test_payment_directory_conflicting_party_names_are_refused(self):
        from services.financial.account_parties import account_parties
        from postgres.models.financial import AdjudicationEvent
        from sqlalchemy import select
        a,_=self.add();b,_=self.add()
        party=self.assign([a])['parties'][0]
        self.assign([b],new_party_name=None,party_id=party['id'])
        event=self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id==b.id))
        event.after={**event.after,'party':{**party,'name':'Conflicting name'}}
        self.db.flush()
        with self.assertRaises(AccountPartyError):account_parties(self.db,case_id=self.case.id)
