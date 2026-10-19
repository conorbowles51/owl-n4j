"""Synthetic teller receipts: separate dates/balances and no new ledger payment."""
from copy import deepcopy
from uuid import UUID, uuid4
from pathlib import Path
import unittest
from sqlalchemy import select, func
from postgres.models.financial import FinancialTransaction
from postgres.models.evidence import EvidenceTableGeometry
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.deposit_receipt_proposal import propose_deposit_receipt, deposit_receipt_choices
from services.financial.payment_document_review import read_payment_document, save_payment_document, matching_payments
from services.financial.statement_import import read_statement_import
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_payment_document_review import PaymentDocumentReviewTests
from tests.test_financial_pdf_geometry_candidates import rectangle


def receipt_source(page=2):
    lines=['Andrews Federal Credit Union','EXAMPLE BRANCH','Acct XXXXXX5678 EXAMPLE PERSON',
           'Eff: 03/23/21 Date: 03/24/21','Tlr: 1234 12:35pm','Deposit to FREE CHECKING 0040',
           'Prev Bal: 10.00','Amount: 120.00','New Bal: 130.00','Seq: TEST123',
           'Acct XXXXXX5678','Avail Bal S0040 100.00','Check Received','Receipt Delivery:']
    return dict(page_number=page,table_index=0,source_revision='b'*64,rows=[
        dict(row_index=i,cells=[dict(column_index=0,expected_text=t,locator={**rectangle(20+i*24,x=20,width=min(500,len(t)*4),height=10),'page':page})])
        for i,t in enumerate(lines)])


class ReceiptProposalTests(unittest.TestCase):
    def test_masked_reference_dates_and_separate_balances_are_not_guessed(self):
        source=receipt_source();before=deepcopy(source);p=propose_deposit_receipt(source)
        f={f['key']:f for f in p['fields']}
        self.assertEqual(f['payment_amount']['value'],'120.00')
        self.assertEqual(f['previous_balance']['value'],'10.00')
        self.assertEqual(f['new_balance']['value'],'130.00')
        self.assertEqual(f['available_balance']['value'],'100.00')
        self.assertEqual(f['account_reference']['value'],'XXXXXX5678')
        for key in ('currency','effective_date','receipt_date'):
            self.assertEqual(f[key]['value'],'');self.assertTrue(f[key]['issues'])
        self.assertEqual(f['effective_date']['raw'],'03/23/21')
        self.assertEqual(f['receipt_date']['raw'],'03/24/21')
        self.assertFalse(p['creates_transactions']);self.assertEqual(source,before)
        self.assertNotEqual(deposit_receipt_choices([source])[0]['id'],deposit_receipt_choices([receipt_source(3)])[0]['id'])

    def test_conflicting_accounts_balances_and_multiple_sections_remain_unresolved(self):
        s=receipt_source();s['rows'][10]['cells'][0]['expected_text']='Acct XXXXXX9999'
        f={f['key']:f for f in propose_deposit_receipt(s)['fields']}
        self.assertEqual(f['account_reference']['value'],'');self.assertTrue(f['account_reference']['issues'])
        s=receipt_source();s['rows'][8]['cells'][0]['expected_text']='New Bal: 131.00'
        self.assertTrue(any('differs' in i for i in propose_deposit_receipt(s)['issues']))
        s=receipt_source();s['rows'][6]['cells'][0]['expected_text']='Prev Bal: 1O.00'
        self.assertEqual(next(f for f in propose_deposit_receipt(s)['fields'] if f['key']=='previous_balance')['value'],'')
        s['rows'].append(deepcopy(s['rows'][5]));self.assertFalse(propose_deposit_receipt(s)['supported'])
        s=receipt_source();s['rows'][0]['cells'][0]['expected_text']='Another Bank';self.assertIsNone(propose_deposit_receipt(s))


class ReceiptSaveTests(PaymentDocumentReviewTests):
    def add_receipt(self, page=2):
        grid=receipt_source(page);first=self.db.get(EvidenceTableGeometry,(self.wire.id,1))
        self.db.add(EvidenceTableGeometry(evidence_file_id=self.wire.id,page_number=page,engine_job_id=first.engine_job_id,
            payload=[dict(table_source='text_alignment',geometry_source='cell_rectangles',table=dict(page=page,
                table={**rectangle(0,x=0,width=600,height=800),'page':page},unlocated_values=0,
                values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator=c['locator']) for r in grid['rows'] for c in r['cells']]))]))
        self.db.commit();return deposit_receipt_choices([grid])[0]['id']

    def receipt_request(self, identifier):
        p=read_payment_document(self.db,case_id=self.case.id,evidence_file_id=self.wire.id,document_id=identifier)
        values={f['key']:f['value'] for f in p['fields']}
        values.update(currency='USD',effective_date='2021-03-23',receipt_date='2021-03-24')
        return dict(request_id=str(uuid4()),document_id=identifier,expected_revision=p['revision'],title='Synthetic receipt',values=values,
                    reasons={key:'Checked full date and currency against supporting evidence.' for key in ('currency','effective_date','receipt_date')})

    def test_receipt_save_retains_selected_page_and_never_adds_a_payment(self):
        identifier=self.add_receipt();req=self.receipt_request(identifier)
        first=self.save(req);self.assertFalse(self.save(req)['created'])
        note=self.db.get(WorkspaceEntry,UUID(first['entry_id']));self.assertIn('receipt-review',note.tags)
        link=self.db.scalar(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id==note.id))
        self.assertEqual(link.source_anchor['page_number'],2)
        original=link.link_metadata['original'];self.assertEqual(original['document_id'],identifier)
        self.assertEqual(next(f for f in original['fields'] if f['key']=='receipt_date')['raw'],'03/24/21')
        self.assertEqual(link.link_metadata['reviewed_values']['receipt_date'],'2021-03-24')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)),0)
        from services.financial.statement_file_status import statement_file_status
        status=statement_file_status(self.db,case_id=self.case.id)['files'][0]
        self.assertEqual(status['receipt_review_count'],1);self.assertNotIn('wire_review_count',status)

    def test_selection_revision_dates_and_link_direction_are_checked(self):
        identifier=self.add_receipt();req=self.receipt_request(identifier)
        with self.assertRaises(PdfMappingError):
            read_payment_document(self.db,case_id=self.case.id,evidence_file_id=self.wire.id,document_id='0'*64)
        wrong=deepcopy(req);wrong['document_id']=self.add_receipt(3)
        with self.assertRaisesRegex(PdfMappingError,'reading changed'):self.save(wrong)
        wrong=deepcopy(req);wrong['values']['receipt_date']='2021-02-30';wrong['reasons']['receipt_date']='Bad correction'
        with self.assertRaisesRegex(PdfMappingError,'dates'):self.save(wrong)
        from postgres.models.enums import TransactionDirection
        row=self.payment(direction=TransactionDirection.debit)
        match=matching_payments(self.db,case_id=self.case.id,request=dict(amount='120.00',currency='USD',value_date='2021-03-23'))['candidates'][0]
        self.assertEqual(matching_payments(self.db,case_id=self.case.id,request=dict(amount='120.00',currency='USD',value_date='2021-03-23'),direction='credit')['candidates'],[])
        req.update(transaction_id=str(row.id),transaction_revision=match['revision'],link_reason='Incorrectly linked an outgoing payment')
        with self.assertRaisesRegex(PdfMappingError,'no longer matches'):self.save(req)

    def test_same_file_receipt_and_payment_keep_both_anchors_on_one_link(self):
        identifier=self.add_receipt();req=self.receipt_request(identifier)
        row=self.payment()
        from postgres.models.financial import FinancialSourceDocument
        document=self.db.get(FinancialSourceDocument,row.source_document_id)
        document.evidence_file_id=self.wire.id
        document.sha256_at_ingestion=self.wire.sha256
        self.db.commit()
        candidate=self.matching()['candidates'][0]
        req.update(transaction_id=str(row.id),transaction_revision=candidate['revision'],link_reason='Receipt and statement in the same PDF.')
        result=self.save(req)
        self.assertFalse(self.save(req)['created'])
        links=list(self.db.scalars(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id==UUID(result['entry_id']))))
        self.assertEqual(len(links),1)
        link=links[0]
        self.assertEqual(link.target_id,str(self.wire.id))
        self.assertEqual(link.source_anchor['page_number'],2)
        self.assertEqual(link.source_anchor['financial_transaction_ids'],[str(row.id)])
        self.assertEqual(link.link_metadata['original']['document_id'],identifier)
        self.assertEqual(link.link_metadata['transactions'][0]['key'],str(row.id))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)),1)

    def test_mixed_pdf_offers_receipt_separately_from_each_account(self):
        from tests.test_financial_statement_import_andrews import two_shares
        grid=two_shares()
        self.db.get(EvidenceTableGeometry,(self.wire.id,1)).payload=[dict(table_source='text_alignment',geometry_source='cell_rectangles',table=dict(page=1,
            table=rectangle(0,x=0,width=600,height=800),unlocated_values=0,
            values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator=c['locator']) for r in grid['rows'] for c in r['cells']]))]
        self.db.commit();identifier=self.add_receipt()
        options=read_statement_import(self.db,case_id=self.case.id,evidence_file_id=self.wire.id)
        self.assertEqual(len(options['statement_choices']),3)
        receipt=read_statement_import(self.db,case_id=self.case.id,evidence_file_id=self.wire.id,statement_id=identifier)
        self.assertEqual(receipt['document_review']['kind'],'deposit_receipt');self.assertEqual(receipt['rows'],[])
        choice=next(c for c in options['statement_choices'] if c.get('share_reference')=='0040')
        statement=read_statement_import(self.db,case_id=self.case.id,evidence_file_id=self.wire.id,statement_id=choice['id'],currency='USD')
        self.assertNotIn('document_review',statement)
        self.assertEqual(statement['transaction_count'],1)
        self.assertTrue(all(r['page_number']==1 for r in statement['rows']))
