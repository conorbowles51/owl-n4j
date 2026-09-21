import copy
import unittest
from types import SimpleNamespace
from services.financial.payment_inference import infer_payment_labels, balance_reading_status
from services.financial.payment_labels import payment_label_view


class PaymentInferenceTests(unittest.TestCase):
    def infer(self, description, direction='debit', kind='credit_card'):
        return infer_payment_labels(description, direction=direction, account_type=kind, institution='Capital One' if kind == 'credit_card' else 'BBVA')

    def test_merchants_and_descriptors_from_supplied_statements(self):
        for description, name, category in [
            ('NIKE.COM AP8008066453OR', 'Nike', 'Shopping'),
            ('DOORDASH*DENNYS6506819470CA', 'DoorDash', 'Meals'),
            ('DD *DOORDASH IHOP8559731040CA', 'DoorDash', 'Meals'),
            ('UBER TRIP8005928996CA', 'Uber', 'Transport'),
            ('UBER EATS8005928996CA', 'Uber Eats', 'Meals'),
            ('PlaystationNetworkSan MateoCA', 'PlayStation', 'Entertainment'),
            ('GRUBHUBMCDONALDS8775851085NY', 'Grubhub', 'Meals'),
            ('HLU*HULUPLUSSANTA MONICACA', 'Hulu', 'Subscriptions'),
            ('BESTBUY.COMRICHFIELDMN', 'Best Buy', 'Shopping'),
            ('FOUR SEASONS BALTIMOREMD FOLIO:', 'Four Seasons', 'Travel'),
        ]:
            with self.subTest(description=description):
                result = self.infer(description)
                self.assertEqual(result['counterparty']['value'], name)
                self.assertEqual(result['category']['value'], category)
                self.assertEqual(result['category']['source'], 'description')
                self.assertTrue(result['category']['explanation'])
                self.assertTrue(result['category']['version'])

    def test_spanish_bank_types_do_not_invent_a_payee(self):
        for description, direction, category, party in [
            ('C19 INTERESES GANADOS', 'credit', 'Interest income', 'BBVA'),
            ('C20 I.S.R. RETENIDO', 'debit', 'Taxes', None),
            ('E20 IVA COMISION ORDEN PAGO 16% Ref. 9644859.0173.01', 'debit', 'Taxes', None),
            ('E18 COMISION ORDEN DE PAGO Ref. 9644859.0173.01', 'debit', 'Bank fees', 'BBVA'),
            ('W01 TRASPASO A TERCEROS RENTA 21 DE 30 BMRCASH Ref. REFBNTC00509957', 'debit', 'Rent and leases', None),
            ('W02 DEPOSITO DE TERCERO CARGOTECNIA BMRCASH Ref. REFBNTC00059250', 'credit', 'Deposits', 'CARGOTECNIA'),
            ('E17 ORDEN DE PAGO EXTRANJERO ORDENANTE: /4451254647 Ref. 9644859.0173.01', 'credit', 'Transfers', None),
        ]:
            with self.subTest(description=description):
                result = self.infer(description, direction, 'checking')
                self.assertEqual(result['category']['value'], category)
                self.assertEqual(result.get('counterparty', {}).get('value'), party)

    def test_transfer_beneficiary_comes_after_tracking_reference_not_bank(self):
        desc = 'T17 SPID ENVIADO BANORTE 0000007PAGO FACT CAMION Ref. 0000000001 072 00000000000000000001 000000000000000000000001 EXAMPLE TRUCKS DE MEXICO'
        self.assertEqual(self.infer(desc, kind='checking')['counterparty']['value'], 'EXAMPLE TRUCKS DE MEXICO')
        self.assertNotIn('counterparty', self.infer('T17 SPID ENVIADO BANORTE 0001494PAGO F1494 Ref. 0004700971 072', kind='checking'))
        self.assertNotIn('counterparty', self.infer(desc, 'credit', 'checking'))

    def test_directional_names_are_not_reversed(self):
        self.assertEqual(self.infer('Transfer to Example Ltd Ref: 123', kind='checking')['counterparty']['value'], 'Example Ltd')
        self.assertEqual(self.infer('Wire from Example Ltd', 'credit', 'checking')['counterparty']['value'], 'Example Ltd')
        self.assertNotIn('counterparty', self.infer('Transfer from Example Ltd', kind='checking'))
        self.assertNotIn('counterparty', self.infer('Transfer to third party', kind='checking'))

    def test_cie_payees_are_taken_from_the_named_payment_not_an_intermediary(self):
        text = 'P14 INTERCAM BANCO SA IB REF:00000000000111901872 CIE:1254405 Ref. GUIA:2297229'
        self.assertEqual(self.infer(text, kind='checking')['counterparty']['value'], 'INTERCAM BANCO SA IB')
        self.assertEqual(self.infer('P14 EXAMPLE SERVICES SA REF:000111 CIE:1234 Ref. GUIA:1', kind='checking')['counterparty']['value'], 'EXAMPLE SERVICES SA')
        for description, direction, kind in [(text, 'credit', 'checking'), (text, 'debit', 'credit_card'), ('P14 REF:123 CIE:45', 'debit', 'checking'), ('T17 SPID ENVIADO BANORTE Ref. 123', 'debit', 'checking')]:
            self.assertNotIn('counterparty', self.infer(description, direction, kind))
        row = SimpleNamespace(account_id='a', case_id='case', metadata_={'investigation_labels': {'to_name': ''}}, description=text, direction='debit', counterparty_raw=None)
        account = SimpleNamespace(id='a',case_id='case',holder_name='Owner',identifier_as_printed='1',account_type='checking',institution_name='BBVA')
        self.assertEqual(payment_label_view(row, account)['to_name'], '')

    def test_returned_transfers_are_not_a_new_payer(self):
        result = self.infer('T22 SPID DEVUELTOBANORTE 0000000PAGO F1494 Ref. 0004700971 072', 'credit', 'checking')
        self.assertEqual(result['category']['value'], 'Returned transfers')
        self.assertNotIn('counterparty', result)

    def test_card_payments_rewards_and_merchant_credits_are_not_income(self):
        payment = self.infer('CAPITAL ONE MOBILE PYMTAuthDate', 'credit')
        self.assertEqual(payment['category']['value'], 'Card payments')
        self.assertNotIn('counterparty', payment)
        self.assertEqual(self.infer('CREDIT-CASH BACK REWARD', 'credit')['category']['value'], 'Card rewards')
        self.assertEqual(self.infer('NIKE.COM AP8008066453OR', 'credit')['category']['value'], 'Merchant credits')
        self.assertNotIn('category', self.infer('CAPITAL ONE MOBILE PYMTAuthDate', 'credit', 'checking'))

    def test_unclear_names_and_incidental_brand_mentions_stay_unresolved(self):
        for description in ['', 'COLUMBIA HEIGHTS', '60371 - 2141 K STWASHINGTONDC', 'NIKELSON LTD', 'SHELLY JONES', 'Unknown entry', 'Reference Nike shopping payment']:
            with self.subTest(description=description):
                self.assertEqual(self.infer(description), {})
        self.assertEqual(self.infer('NIKE.COM', direction='invalid'), {})

    def test_existing_readings_and_individual_manual_edits_take_precedence(self):
        account = SimpleNamespace(id='account', case_id='case', holder_name='Owner', identifier_as_printed='123', account_type='credit_card', institution_name='Capital One')
        row = SimpleNamespace(account_id='account', case_id='case', metadata_={}, description='NIKE.COM AP8008066453OR', direction='debit', counterparty_raw=None)
        original = copy.deepcopy(vars(row))
        view = payment_label_view(row, account)
        self.assertEqual((view['category'], view['from_name'], view['to_name']), ('Shopping', 'Owner', 'Nike'))
        self.assertEqual(view['label_sources']['from_name']['source'], 'account')
        self.assertEqual(view['label_sources']['to_name']['source'], 'description')
        self.assertEqual(vars(row), original)
        row.counterparty_raw = 'Printed name'
        self.assertEqual(payment_label_view(row, account)['to_name'], 'Printed name')
        row.metadata_ = {'investigation_labels': {'category': 'Case purchase', 'to_name': 'Confirmed recipient', 'version': 2}}
        view = payment_label_view(row, account)
        self.assertEqual((view['category'], view['to_name']), ('Case purchase', 'Confirmed recipient'))
        self.assertEqual(view['label_sources']['category']['source'], 'investigator')
        row.metadata_['investigation_labels']['category'] = ''
        self.assertEqual(payment_label_view(row, account)['category'], '')
        account.case_id = 'other'
        self.assertNotEqual(payment_label_view(row, account)['from_name'], 'Owner')

    def test_missing_running_balances_are_not_invented_or_assumed_absent(self):
        row = SimpleNamespace(running_balance_minor=None, provenance={})
        self.assertEqual(balance_reading_status(row), 'unavailable')
        row.provenance = {'statement_import_original': {'fields': {'printed_section':'Transactions','card_ending':'9392'}, 'issues':[]}}
        self.assertEqual(balance_reading_status(row), 'not_printed')
        self.assertIsNone(row.running_balance_minor)
        row.provenance['statement_import_original']['issues'] = ['Check unreadable balance']
        self.assertEqual(balance_reading_status(row), 'unavailable')
        row.running_balance_minor = 0
        self.assertEqual(balance_reading_status(row), 'recorded')
