import hashlib,json
from types import SimpleNamespace
from uuid import uuid4
from unittest import TestCase
from services.financial.claim_comparison import compare_ledger_claim
from services.financial.ledger_summary import LedgerSummaryError

class ClaimComparisonTests(TestCase):
    def fixture(self, amount='10000',unknown=False):
        case,account,file,rowid=map(str,[uuid4(),uuid4(),uuid4(),uuid4()])
        row=dict(key=rowid,account_id=account,ordering_date='2026-01-02',transaction_date=None if unknown else '2026-01-02',ordering_date_context='statement_end_ordering_only' if unknown else None,direction='debit',amount_minor=amount,currency='GBP',counterparty_raw='Bob',description='Recorded payment',proof_class='p3')
        data=dict(export_ready=True,ledger=dict(case_id=case,account_id=account,start_date=None,end_date=None,history_captured=True,readings=[dict(row=row,account={'label':'Account A'},included=False,exclusion_reason='proof_class_not_included')]))
        content=json.dumps(data);export=SimpleNamespace(snapshot=SimpleNamespace(content=content,sha256=hashlib.sha256(content.encode()).hexdigest()),manifest='{}')
        request=dict(account_id=account,source_file_id=file,quote='I paid Bob one hundred pounds.',source_location='Interview page 2',payer='Alice',payee='Bob',currency='GBP',amount_low_minor='10000',amount_high_minor='10000',earliest='2026-01-01',latest='2026-01-03',account_holder='Alice',interpretation_basis='Investigator assumption for the synthetic account',population='working')
        return export,request,dict(id=file,case_id=case,filename='Synthetic interview',sha256='a'*64)
    def test_preserves_p4_and_sources_without_claiming_reconciliation(self):
        export,request,source=self.fixture();envelope=compare_ledger_claim(export,request,source);result=json.loads(envelope['scenario_json'])
        self.assertEqual(result['claim_proof_class'],'p4');self.assertEqual(result['comparison']['outcome'],'corroborated');self.assertEqual(result['comparison']['candidates'][0]['entry']['proof_class'],'p3');self.assertIsNone(result['comparison']['candidates'][0]['entry']['reconciled']);self.assertIn('Statement reconciliation was not independently assessed in this comparison.',result['comparison']['notes']);self.assertEqual(result['claim_source'],source);self.assertEqual(hashlib.sha256(envelope['scenario_json'].encode()).hexdigest(),envelope['scenario_sha256'])
    def test_absence_amount_difference_and_unknown_dates_cannot_contradict(self):
        for options in [dict(amount='4000'),dict(unknown=True)]:
            export,request,source=self.fixture(**options);result=json.loads(compare_ledger_claim(export,request,source)['scenario_json']);self.assertEqual(result['comparison']['outcome'],'unresolved')
        export,request,source=self.fixture();request['population']='verified';result=json.loads(compare_ledger_claim(export,request,source)['scenario_json']);self.assertEqual(result['comparison']['outcome'],'unresolved');self.assertEqual(result['comparison']['candidates'],[])
    def test_source_case_and_blank_interpretation_refused(self):
        export,request,source=self.fixture()
        with self.assertRaises(LedgerSummaryError):compare_ledger_claim(export,request,{**source,'case_id':str(uuid4())})
        with self.assertRaises(LedgerSummaryError):compare_ledger_claim(export,{**request,'interpretation_basis':' '},source)
