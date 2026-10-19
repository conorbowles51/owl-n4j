"""Synthetic wire reports only; no private account or party details."""
import unittest
from copy import deepcopy
from services.financial.payment_document_proposal import propose_payment_document
from tests.test_financial_pdf_geometry_candidates import rectangle


def wire_source():
    lines = [
        [(20, 'Wire Transfer Detail Report')], [(20, 'WELLS FARGO BANK, N.A.')],
        [(20, 'Wire Amount:'), (330, 'Instructed Currency/Amount:')],
        [(20, '120.00'), (330, 'USD/120.00')],
        [(20, 'Value Date:'), (330, 'Completed Timestamp:')],
        [(20, '03/23/2021'), (330, '03/23/2021 02:07 PM CT')],
        [(20, 'Sending Party Name and Address:'), (330, 'Receiving Party Name and Address:')],
        [(20, 'EXAMPLE SENDER LLC'), (330, 'EXAMPLE RECEIVER LLC')],
        [(20, '1 TEST STREET'), (330, '2 SAMPLE STREET')],
        [(20, 'Transaction Reference Number:'), (330, 'Beneficiary Name and Address:')],
        [(20, 'TEST-REFERENCE'), (330, 'EXAMPLE BENEFICIARY LLC')],
        [(20, 'USD Equivalent Amount:'), (330, 'Bank to Bank Info:')],
        [(20, '120.00'), (330, 'N/A')], [(20, 'Note: Synthetic test')],
    ]
    return dict(page_number=1, table_index=0, source_revision='a'*64, rows=[
        dict(row_index=i,cells=[dict(column_index=j,expected_text=text,
            locator=rectangle(20+i*22,x=x,width=min(575-x,len(text)*3),height=10)) for j,(x,text) in enumerate(line)])
        for i,line in enumerate(lines)])


class WireProposalTests(unittest.TestCase):
    def fields(self, source):
        result=propose_payment_document([source])
        self.assertTrue(result['supported'])
        self.assertFalse(result['creates_transactions'])
        return {f['key']:f for f in result['fields']}

    def test_fields_stay_in_their_labelled_column_and_keep_source_cells(self):
        source=wire_source();before=deepcopy(source);fields=self.fields(source)
        self.assertEqual(fields['sending_party']['value'],'EXAMPLE SENDER LLC\n1 TEST STREET')
        self.assertEqual(fields['receiving_party']['value'],'EXAMPLE RECEIVER LLC\n2 SAMPLE STREET')
        self.assertEqual(fields['beneficiary']['value'],'EXAMPLE BENEFICIARY LLC')
        self.assertEqual(fields['wire_amount']['value'],'120.00')
        self.assertEqual(fields['value_date']['value'],'2021-03-23')
        self.assertEqual(fields['currency']['value'],'USD')
        self.assertEqual(fields['transaction_reference']['source_cells'][0]['expected_text'],'TEST-REFERENCE')
        self.assertEqual(source,before)

    def test_damaged_currency_is_not_repaired_using_usd_equivalent(self):
        source=wire_source();source['rows'][3]['cells'][1]['expected_text']='USO/120.00'
        fields=self.fields(source)
        self.assertEqual(fields['currency']['value'],'')
        self.assertTrue(fields['currency']['issues'])
        self.assertEqual(fields['currency']['raw'],'USO/120.00')
        self.assertEqual(fields['usd_equivalent']['value'],'120.00')

    def test_missing_or_duplicate_labels_do_not_inherit_another_party(self):
        for replacement in ('Receiving arty Name and Address:','Sending Party Name and Address:'):
            source=wire_source();source['rows'][6]['cells'][1]['expected_text']=replacement
            fields=self.fields(source)
            self.assertEqual(fields['receiving_party']['value'],'')
            self.assertTrue(fields['receiving_party']['issues'])
            if replacement.startswith('Sending'):
                self.assertEqual(fields['sending_party']['value'],'')

    def test_damaged_dates_amounts_and_redacted_references_are_not_reconstructed(self):
        source=wire_source();source['rows'][3]['cells'][0]['expected_text']='12O.00'
        source['rows'][5]['cells'][0]['expected_text']='03/32/2021'
        source['rows'][10]['cells'][0]['expected_text']='XXXX123'
        fields=self.fields(source)
        for key in ('wire_amount','value_date','transaction_reference'):
            self.assertEqual(fields[key]['value'],'')
            self.assertTrue(fields[key]['issues'])
        self.assertEqual(fields['transaction_reference']['raw'],'XXXX123')

    def test_unrecognised_and_multiple_reports_are_not_bank_statements(self):
        source=wire_source();source['rows'][0]['cells'][0]['expected_text']='Other report'
        self.assertIsNone(propose_payment_document([source]))
        source=wire_source();source['rows'][1]['cells'][0]['expected_text']='Another bank'
        self.assertFalse(propose_payment_document([source])['supported'])
        source=wire_source()
        self.assertFalse(propose_payment_document([source,deepcopy(source)])['supported'])

    def test_foreign_instruction_and_different_equivalent_do_not_determine_wire_currency(self):
        for instructed, equivalent in [('EUR/120.00', '130.00'), ('USD/120.00', '130.00')]:
            source = wire_source()
            source['rows'][3]['cells'][1]['expected_text'] = instructed
            source['rows'][12]['cells'][0]['expected_text'] = equivalent
            self.assertEqual(self.fields(source)['currency']['value'], '')

    def test_damaged_timestamp_is_flagged_and_a_title_inside_body_is_not_a_report(self):
        source = wire_source()
        source['rows'][5]['cells'][1]['expected_text'] = '0312312021 02:07 PM CT'
        field = self.fields(source)['completed_at']
        self.assertEqual(field['value'], '')
        self.assertTrue(field['issues'])
        self.assertEqual(field['raw'], '0312312021 02:07 PM CT')
        source['rows'][0]['cells'][0]['locator'] = rectangle(300, x=20, width=160, height=10)
        self.assertIsNone(propose_payment_document([source]))
