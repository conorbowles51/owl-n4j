"""The other side of a payment as each statement layout prints it.

Every description below is a real statement line with its layout kept exactly
(spacing, separators, OCR marks, footnotes); only names, accounts and
references are replaced by invented ones so no case material is committed.
"""
import unittest
from services.financial.payment_party_reasons import unnamed_reason

from services.financial.payment_inference import infer_payment_labels, VERSION


def party(description, direction='debit', kind='checking', institution='Example Bank'):
    found = infer_payment_labels(description, direction=direction, account_type=kind, institution=institution)
    found = found.get('counterparty')
    if found:
        assert found['source'] == 'description' and found['version'] == VERSION and found['explanation']
    return (found['value'], found['rule']) if found else None


class PrintedPartyTests(unittest.TestCase):
    def test_santander_cliente_is_the_party_not_the_receiving_bank(self):
        sent = ('1000001 PAGO TRANSFERENCIA SPEI HORA 10:00:01 ENVIADO A BBVA MEXICO A LA CUENTA 012180001111111111 '
                'AL CLIENTE EJEMPLO SERVICIOS SA DE CV (1) (1) DATO NO VERIFICADO POR ESTA INSTITUCION CLAVE DE '
                'RASTREO 202501014001 40ABC0000001')
        self.assertEqual(party(sent), ('EJEMPLO SERVICIOS SA DE CV', 'spei-cliente-party'))
        spaced = ('PAGO TRANSFERENCIA SPEI HORA 10:00:02 ENVIADO A BANAMEX ALA CUENTA 002180000000000000 AL CLIENTE '
                  'DANIEL EJEMPLO PRUEBA ( 1) (1) DATO NO VERIFICADO POR ESTA INSTITUCION CLAVE DE RASTREO 20250101')
        self.assertEqual(party(spaced)[0], 'DANIEL EJEMPLO PRUEBA')
        got = ('ABONO TRANSFERENCIA SPEI HORA 10:00:03 RECIBIDO DE BANORTE DE LA CUENTA 072180000000000000 DEL CLIENTE '
               'EJEMPLO SERVICIOS SA DE CV CLAVE DE RASTREO 1234ABC1202501011234567890 REF 0000001 CONCEPTO ARR ENE 25')
        self.assertEqual(party(got, 'credit'), ('EJEMPLO SERVICIOS SA DE CV', 'spei-cliente-party'))
        self.assertIsNone(party(got, 'debit'))
        tef = ('1000002 PAGO TRANSFERENCIA TEF HORA 10:00:04 ENVIADO A AZTECA A LA CUENTA 127180000000000000 AL '
               'CLIENTE JORGE EJEMPLO PRUEBA (1) (1) DATO NO VERIFICADO POR ESTA INSTITUCION CLAVE DE RASTREO 2025010140014')
        self.assertEqual(party(tef)[0], 'JORGE EJEMPLO PRUEBA')
        torn = ('1000003 PAGO TRANSFERENCIA SPEI HORA 10:00:05 ENVIADO A BBVA MEXICO A LA CUENTA 0121800000000 00000 AL CLIENTE '
                'EJEMPLO SERVICIOS (1 (1) DATO NO VERIFICADO POR ESTA INSTITUCION CLAVE DE RASTREO 2025010140014 BETO000000000001')
        self.assertEqual(party(torn)[0], 'EJEMPLO SERVICIOS')

    def test_delimited_spei_takes_the_name_field_without_the_qualification(self):
        sent = ('ENVIO SPEI BBVA MEXICO | EJEMPLO SERVICIOS AMB DATO NO VERIFICADO POR ESTA INSTITUCION | 012180001100000000 | '
                '136- 01/01/2025/01-1900000001 | 0000001 | TRASPASO CTAS PROPIAS | INTERCAM BANCO | EJEMPLO SERVICIOS S.A. DE C')
        self.assertEqual(party(sent), ('EJEMPLO SERVICIOS AMB', 'spei-delimited-party'))
        got = ('RECEPCION SPEI | BBVA MEXICO | EJEMPLO SERVICIOS A MBIENTALES SA DE CV DATO NO VERIFICADO POR ESTA '
               'INSTITUCION | 012180001100000000 | BNET01002501010000000005 | 0010125 |')
        self.assertEqual(party(got, 'credit')[0], 'EJEMPLO SERVICIOS A MBIENTALES SA DE CV')
        typo = ("ENVIO SPEI SANTANDER | INGENIERIA EJEMPLO Z9 DATO NO 'VERIFICADO POR ESTA INSTITUCION | 014180000000000000 | "
                '136- 01/01/2025/01-1900000002 | 0000002 | TRASPASO CUENTAS PROPIAS | | INGENIERIA EJEMPLO Z9 S.A. DE C.V. |')
        self.assertEqual(party(typo)[0], 'INGENIERIA EJEMPLO Z9')
        bare = 'ENVIO SPEI BANAMEX MIGUEL EJEMPLO PRUEBA 002180000000000000 NOMINA 1ER QNA ENE 25 100000001'
        self.assertEqual(party(bare), ('MIGUEL EJEMPLO PRUEBA', 'spei-delimited-party'))
        self.assertIsNone(party(sent, 'credit'))

    def test_monex_beneficiary_and_ordering_party_fields_not_the_bank(self):
        self.assertEqual(party('RETIRO Nombre Receptor: BBVA BANCOMER Monto Pago: 100000 Cuenta beneficiaria: 012180000000000000 '
                               'Nombre Beneficiario: EJEMPLO SERVICIOS SA DE CV Clave de Rastreo: 10000001 Referencia Numerica: 1'),
                         ('EJEMPLO SERVICIOS SA DE CV', 'monex-named-party'))
        self.assertEqual(party('Depósito Emisor: BBVA BANCOMER ] Fecha Confirmacion de liquidacion:01-01-2019 12:00:00 ] Monto :100000 ] '
                               'Cuenta ordenante:012180000000000000 ] Nombre del Ordenante:EJEMPLO SERVICIOS SA DE C V ] Clave de Rastreo:0026',
                               'credit')[0], 'EJEMPLO SERVICIOS SA DE C V')
        self.assertEqual(party('RETIRO BENEFICIARIO KEN EJEMPLO BANCO MIZUHO BANK, LTD. CUENTA 1300000000')[0], 'KEN EJEMPLO')
        self.assertEqual(party('RETIRO BENEFICIARIO EJEMPLO SERVICIOS SA DE CV RFC:ASE000000AA0 BANCO BBVA BANCOMER CUENTA 0110000000 Texto:eur')[0],
                         'EJEMPLO SERVICIOS SA DE CV')
        self.assertEqual(party('RETIRO Receptor BBVA MEXICO, Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERVICIOS SA DE CV, '
                               'Concepto TRASPASO CUENTAS PROPIAS, Ref 100000002')[0], 'EJEMPLO SERVICIOS SA DE CV')
        # On a deposit the printed beneficiary is the account holder, so the other side is the contract it came from.
        self.assertEqual(party('Depósito En Cta De Captación Con Origen En Cta De Captación BENEFICIARIO EJEMPLO SERVICIOS SA DE CV '
                               'RFC:ASE000000AA0 BANCO BANCO MONEX CUENTA 2800000 traspaso de fondos del contrato 3000000', 'credit'),
                         ('Account 3000000 (no name printed)', 'third-party-account'))

    def test_bbva_spei_name_follows_the_references(self):
        self.assertEqual(party('T20 SPEI RECIBIDOSANTANDER 10000000000000001 Ref. 0100000001 014 0001400000001 1000001 '
                               '20250101400140ABC0000000000001 EJEMPLO GERENCIA DE TESORERI', 'credit'),
                         ('EJEMPLO GERENCIA DE TESORERI', 'bbva-transfer-party'))
        self.assertEqual(party('117 SPE] ENVIADO KAPITAL 0010125TRASPASO CUENTAS PROPIAS Ref. 0000000001 128 00128180000000000000 '
                               '002601002501010000000001 EJEMPLO SERVICIOS')[0], 'EJEMPLO SERVICIOS')
        self.assertEqual(party('T20 SPEI RECIBIDOKUSPIT 0000001PRESTAMO Ref. 0100000002 653 00653180000000000000 EXAMPLEPAY '
                               '0100000003 EJEMPLO IMPULSORA SA DE CV', 'credit')[0], 'EJEMPLO IMPULSORA SA DE CV')
        self.assertEqual(party('T17 SPEI ENVIADO AZTECA 0010125NOMINA 010125 Ref. 0000000002 127 CARLOS EJEMPLO PRUEBA')[0], 'CARLOS EJEMPLO PRUEBA')
        self.assertEqual(party('T17 SPEI ENVIADO BANORTE 0010125NOMINA 1A QNA ENE25 00001234567800000000 JULIO EJEMPLO PRUEBA')[0],
                         'JULIO EJEMPLO PRUEBA')
        self.assertEqual(party('T17 SPEI ENVIADO BANCOPPEL 0010125NOMINA 010125 LUIS EJEMPLO PRUEBA')[0], 'LUIS EJEMPLO PRUEBA')
        # A word with a digit glued to it belongs to the name; a legal form alone is no name.
        self.assertEqual(party('T17 SPEI ENVIADO SANTANDER 10101251040 Ref. 0000000007 014 00014180000000000007 '
                               '002601002501010000000007 EJEMPLO7 31 SA DE CV')[0], 'EJEMPLO7 31 SA DE CV')
        self.assertIsNone(party('T17 SPEI ENVIADO SANTANDER 10101251040 Ref. 0000000008 014 00014180000000000008 '
                                '002601002501010000000008 SA DE CV'))
        # A short key mixing letters and digits is still a reference, not the start of the name.
        self.assertEqual(party('T17 SPEI ENVIADO SANTANDER 10101251040 Ref. 0000000009 014 00014180000000000009 '
                               '1ABC2D3E JUAN EJEMPLO PRUEBA')[0], 'JUAN EJEMPLO PRUEBA')
        # An equipment word left from the concept (RETRO for retroexcavadora) is not part of the name.
        self.assertEqual(party('T17 SPEI ENVIADO BANAMEX 0010125PAGO F A101 RETRO EJEMPLO SA DE CV')[0], 'EJEMPLO SA DE CV')
        # Concept and name run together with nothing to tell them apart: no name.
        self.assertIsNone(party('T17 SPEI ENVIADO SCOTIABANK 0010125ANT PRUEBAS PEDRO EJEMPLO PRUEBA'))
        self.assertIsNone(party('T17 SPEI ENVIADO SANTANDER 0000004NOMINA 2A QNA ENE25 Ref. 0000000003 014'))
        # A transfer whose concept mentions a commission is still a transfer to the printed beneficiary.
        self.assertEqual(party('T17 SPEI ENVIADO SANTANDER 0010125PAGO F 19 COMISION MERCANTIL Ref. 0000000004 014 '
                               '00014180000000000000 BNET01002501010000000004 ANA EJEMPLO PRUEBA')[0], 'ANA EJEMPLO PRUEBA')

    def test_third_party_account_is_shown_when_no_name_is_printed(self):
        self.assertEqual(party('N06 PAGO CUENTA DE TERCERO BNET 1500000000 NOMINA 010125 Ref. 0000000006'),
                         ('Account 1500000000 (no name printed)', 'third-party-account'))

    def test_mexican_payees(self):
        self.assertEqual(party('0000000 DOMICILIACION PAGO SERVICIO 0000001 RFC EFS010101AA1 COBRO 0,000,100.00 '
                               'EJEMPLO FINANCIAL SERVICES DE MEXICO S.A.')[0], 'EJEMPLO FINANCIAL SERVICES DE MEXICO S.A')
        self.assertEqual(party('P14 EJEMPLO S DE RL D REF:1000000PD01000000001 CIE:1000001 Ref. GUIA:1000002'),
                         ('EJEMPLO S DE RL D', 'bbva-cie-payee'))
        self.assertEqual(party('P31 RADIO EJEMPLO DIPSA TE00001 0000000000001 Ref. ABC010101 QU4'),
                         ('RADIO EJEMPLO DIPSA', 'bbva-direct-debit-payee'))
        self.assertEqual(party('P31 EJEMPLO PAGOS DE PRUEB12345 EJEMPLOMT0000 Ref. EUN010101AA1')[0], 'EJEMPLO PAGOS DE PRUEB')
        self.assertEqual(party('PAGO SERVICIO GOBIERNO DE CDMX'), ('GOBIERNO DE CDMX', 'service-payee'))
        self.assertEqual(party('(BE) PAGO: PAGO REFERENCIADO SAT'), ('SAT', 'tax-authority-payee'))
        self.assertEqual(party('X01 IMSS/INF/AFORE VIA ELECT. PAGO SIPARE E1000000001 202501 100001 Ref. 100N000001'),
                         ('IMSS/INF/AFORE', 'social-security-payee'))
        # A federal tax payment is paid to the tax authority, not to the bank.
        self.assertEqual(party('0000000 CGO IMPTO FED TRANSF ELECT 01011XA0000000000001'),
                         ('SAT (Servicio de Administración Tributaria)', 'tax-authority-payee'))

    def test_the_statement_bank_is_the_other_side_of_its_own_services(self):
        for description, direction, rule in [
            ('0000000 ABO POR INTERESES DEL PERIODO 01-07-2021 AL 31-07-2021', 'credit', 'bank-interest'),
            ('RETENCION | S R COBRO DE ISR SOBRE INTERESES ACREEDORES', 'debit', 'bank-tax-withheld'),
            ('0000000 I V A ABR 2021', 'debit', 'bank-tax-withheld'),
            ('S39 SERV BANCA INTERNET Ref. OPS SERV BCA IN', 'debit', 'bank-charge'),
            ('W83 COM TRANSACCIONES BNTC EJEMPLO ENE 2025 Ref. 100001', 'debit', 'bank-charge'),
            ('Y45 COMPENSACION POR RETRASO Ref. COMP SPEI', 'credit', 'bank-charge'),
            ('Compra de divisas 1,000.00 USD a un tipo de cambio de 20.000000 Importe en pesos $20,000.00', 'credit', 'bank-currency-exchange'),
            ('100000001 Compra de Reporto CETES 250101 0 1,000,000 9.00000000 1 7.500000', 'debit', 'bank-investment'),
            ('N11 APERTURA DE INVERSION INVERSION: 104 BNTC Ref. 10000001', 'debit', 'bank-investment'),
            ('Retiro Retiro de fondos para transferencia :Traspaso a Crédito No. 3', 'debit', 'bank-credit-line'),
            ('| M&T ADD-ON FEE: OVERDRAFT TRANSFERS', 'debit', 'bank-charge'),
            ('| INTEREST PAYMENT', 'credit', 'bank-interest'),
            ('Dividend', 'credit', 'bank-interest'),
        ]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction), ('Example Bank', rule))
        # A fee for a transfer is the bank's even though the transfer's beneficiary is printed in it.
        fee = ('Comision Por Transferencia Retiro de Comision e IVA (Comision $5.00, IVA $.80), Receptor BBVA MEXICO, '
               'Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERVICIOS SA DE CV, Ref 100000003')
        self.assertEqual(party(fee), ('Example Bank', 'bank-charge'))
        self.assertIsNone(party('0000000 ABO POR INTERESES DEL PERIODO 01-07-2021', 'credit', institution=None))
        # A card issuer's interest charge is the issuer's.
        self.assertEqual(party('INTEREST CHARGED TO STANDARD PURCH', kind='credit_card'), ('Example Bank', 'bank-interest'))

    def test_us_ach_transfers_and_payees(self):
        self.assertEqual(party('Withdrawal ACH Credit One Bank TYPE: Payment ID: WEB000001 CO: Credit One Bank NAME: JANE '
                               'EXAMPLE ACH Trace Number: 000000000000001'), ('Credit One Bank', 'ach-company'))
        self.assertEqual(party('Deposit ACH ST OF MARYLAND TYPE: DIRCT DPST ID: 0000000001 CO: ST OF MARYLAND ACH Trace Number: 05500',
                               'credit')[0], 'ST OF MARYLAND')
        self.assertEqual(party('Withdrawal Online Banking Transfer To EXAMPLE,JANE Q XXXXXXXXXX Share 0001 Gift'),
                         ('EXAMPLE,JANE Q', 'credit-union-transfer-party'))
        self.assertEqual(party('Deposit Online Banking Transfer January From EXAMPLE,JANE Q xxxxxxxxxx Share 0001', 'credit')[0],
                         'EXAMPLE,JANE Q')
        # The member's own share or loan is not another party: it is shown as the member's own account.
        self.assertEqual(party('Withdrawal Online Banking Transfer To Share 0001 Funds Transfer via Mobile'),
                         ('Own share account 0001', 'own-account-transfer'))
        self.assertEqual(party('Withdrawal Online Banking Transfer To Loan ############0001 Funds Transfer via Mobile'),
                         ('Own loan account …0001', 'own-account-transfer'))
        self.assertEqual(party('Withdrawal Bill Payment Bill Paid-AMERICAN EDUCATION SE Conf #01'), ('AMERICAN EDUCATION SE', 'bill-payee'))
        self.assertEqual(party('Paid To - Pepco Paymentus Billpay'), ('Pepco Paymentus Billpay', 'named-payment-party'))
        self.assertEqual(party('Paid To - Capital One Mobile Pmt Chk 1000001')[0], 'Capital One')
        self.assertEqual(party('Deposit - ACH Paid From DFAS-Cleveland Ret Alt 01Abc1', 'credit')[0], 'DFAS-Cleveland Ret Alt')
        self.assertEqual(party('ZELLE PAYMENT FROM JANE EXAMPLE PAYMENT ID ABC0DEF1GHIJ', 'credit'), ('JANE EXAMPLE', 'zelle-party'))
        self.assertEqual(party('Deposit Faster Payments zel* JOHN EXAMPLE AB10000CDEfG', 'credit'), ('JOHN EXAMPLE', 'zelle-party'))
        self.assertEqual(party('Deposit Debit Card Cash App*Cash Out Visa Direct CA Date 01/01/21 o 0000000001 o 0001', 'credit'),
                         ('Cash App*Cash Out', 'card-push-payment-source'))
        self.assertEqual(party('MC VI DEP TRUIST MERCH SVC EXAMPLE CAMP SPRINGS CUSTOMER ID 000000000001 0000000001', 'credit'),
                         ('TRUIST MERCH SVC', 'card-settlement-payer'))

    def test_debit_card_merchants_as_printed(self):
        for description, direction, expected in [
            ('Withdrawal Debit Card 01/01 O 0000000002 0 GRUBHUBMCDONALDS GRUBHUB.COM NY', 'debit', ('Grubhub', 'debit-card-merchant')),
            ('Withdrawal POS #000000000003 CVS/PHARMACY #01 01001--1 Washington DC', 'debit', ('CVS', 'debit-card-merchant')),
            ('Withdrawal Debit Card 01/0 1 0 0000000004 0 EXAMPLE HEIGHTS MARKET WASHINGTON DC', 'debit',
             ('EXAMPLE HEIGHTS MARKET', 'debit-card-descriptor')),
            ('DEBIT CARD PURCHASE ROSS STORES #1001 01-01 OXON HILL MD 0001', 'debit', ('ROSS STORES', 'debit-card-descriptor')),
            ('DEBIT CARD PURCHASE Subway 101 01-01 Suitland MD 0001', 'debit', ('Subway', 'debit-card-descriptor')),
            ('DEBIT CARD RECURRING PYMT EXAMPLE COVER MUSIC 01-01 JOHN.DOE@ CA 0001', 'debit', ('EXAMPLE COVER MUSIC', 'debit-card-descriptor')),
            ('POS Debit- Debit Card 0001 01-01-23 Example Seniorcare 800-555-0100 MD', 'debit', ('Example Seniorcare', 'debit-card-descriptor')),
            ('POS Debit- Debit Card 0001 01-01-21 USPS Change Of Add 800-555-0101 TN', 'debit', ('USPS Change Of Add', 'debit-card-descriptor')),
            ('Withdrawal Debit Card 01/01 0 0000.000001 0 Amazon Digit*AB0CD1EF2 888-555-0102 WA', 'debit', ('Amazon', 'debit-card-merchant')),
            ('Withdrawal Debit Card 01/01 0 0000000005 0 BOOKSY HTTPSWWW.BOOK IL', 'debit', ('BOOKSY', 'debit-card-descriptor')),
            ('DEBIT CARD PURCHASE TST* El Ejemplo Cafe 01-01 Temple Hills MD 0001', 'debit', ('El Ejemplo Cafe', 'debit-card-descriptor')),
            ('| DD DOORDASH REDLOBSTE 855-973-1040', 'debit', ('DoorDash', 'debit-card-merchant')),
            ('| EXAMPLEINSCO INSUR PREM', 'debit', ('EXAMPLEINSCO', 'statement-line-payee')),
            ('| ATT Payment', 'debit', ('ATT', 'statement-line-payee')),
            ('| SSA TREAS 310 XXSOC SEC', 'credit', ('SSA TREAS', 'statement-line-payee')),
        ]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction), expected)
        # A terminal printed as its street address names no merchant.
        self.assertIsNone(party('Withdrawal Debit Card 01/01 0 0000000006 0 12345 - 100 MAIN AV ANYTOWN MD'))
        self.assertIsNone(party('| CHECK NUMBER 1001'))
        self.assertEqual(party('| |IVA POR COMISIONES 16.00% SCOTIA EN LINEA ADMINISTRACION RENTA DE BANCAINTERNET'), ('Example Bank', 'bank-tax-withheld'))
        self.assertEqual(party('DEBIT CARD PURCHASE REV AUTH EXAMPLE PAYST 01-01 BOWIE MD 0001')[0], 'EXAMPLE PAYST')
        self.assertEqual(party('DEBIT CARD PURCHASE FACEBK 1ABCDEF2G3 01-01 650-5550100 CA 0001')[0], 'FACEBK')
        self.assertEqual(party('| PURCHASE ON 01/01 EXAMPLE HEIGH1234 1ST STREET WASHINGTON DC')[0], 'EXAMPLE HEIGH')
        self.assertIsNone(party('| COBRO DE COMISION 000000000000000000000000 SCOTIA EN LINEA ADMINISTRACION', institution=None))

    def test_nothing_is_invented_where_no_party_is_printed(self):
        for description, direction in [('DEPOSIT', 'credit'), ('ABONO A CUENTA DE CHEQUES', 'credit'), ('W01 TRASPASO A TERCEROS', 'debit'),
                                       ('G30 RECIBO NO. Ref. A0BCDE100FGH', 'debit'), ('CARGO A CUENTA DE CHEQUES', 'debit'),
                                       ('Check 1001', 'debit'), ('R01 PAGO DE NOMINA EJEMPLO SERVICIOS SA DE CV Ref. BC 1000000001', 'debit')]:
            with self.subTest(description=description):
                self.assertIsNone(party(description, direction))

    def test_review_regressions(self):
        # OCR splits the debit card prefix after M&T's bar: the merchant is read, not the split word.
        self.assertEqual(party('~Ii thdrawal Debit Card / 01/01 0 0000000007 0 LYFT *SCOOTER RIDE LYFT.COM CA')[0], 'Lyft')
        self.assertEqual(party('~Wi thdrawal Debit Card 01/01 0 0000000001 0 EJEMPLO CAFE MD')[0], 'EJEMPLO CAFE')
        # A bank service on an account with no bank recorded names nobody, not the name printed in it.
        for description in ['Comision Por Transferencia Retiro de Comision e IVA (Comision $5.00, IVA $.80), Receptor BBVA MEXICO, '
                            'Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERVICIOS SA DE CV, Ref 100000003',
                            'Withdrawal Debit Card Fee\nINTERNATIONAL FEE\nDate 01/01/23', '| SERVICE CHARGE']:
            with self.subTest(description=description):
                self.assertIsNone(party(description, institution=None))
        # Card credits keep the merchant descriptor reading and its category.
        for description in ['MONTHLY FEE REFUND', 'OVERDRAFT PROTECTION', '| INTEREST PAYMENT', 'PAGO CAP. DE INVERSIÓN']:
            with self.subTest(description=description):
                found = infer_payment_labels(description, direction='credit', account_type='credit_card', institution='Example Bank')
                self.assertEqual((found['category']['value'], found['counterparty']['rule']), ('Merchant credits', 'card-statement-descriptor'))
        # The name keeps the accents the statement prints.
        self.assertEqual(party('ENVIO SPEI BANAMEX JOSÉ EJEMPLO PEÑA 002180000000000000 NOMINA 1ER QNA ENE 25 100000001')[0],
                         'JOSÉ EJEMPLO PEÑA')
        self.assertIsNone(party('Recurring w·ithdrawal Debit Card 01/01 0 00.00000001 0 EJEMPLO SHOP CA'))
        self.assertEqual(party('ABONO TRANSFERENCIA SPEI HORA 1 RECIBIDO DE BMONEX DE LA CUENTA 1121 DEL CLIENTE EJEMPLO SA DE CV '
                               'DE RASTREO 10000001 fe CONCEPTO OC 1', 'credit')[0], 'EJEMPLO SA DE CV')
        self.assertEqual(party('Withdrawal Bill Payment Bill Paid-EJEMPLO LOANS Con£ #01'), ('EJEMPLO LOANS', 'bill-payee'))
        # Wording inside a transfer's concept does not make the bank the other side.
        for description, direction in [('ABONO TRANSFERENCIA ENLACE COMISION EJEMPLO 1', 'credit'),
                                       ('T17 SPEI ENVIADO INBURSA 0010125PAGO COMISION F 1 Ref. 0000000001 036', 'debit'),
                                       ('T20 SPEI RECIBIDOBANAMEX 0000001COMISION Ref. 0000000002 002', 'credit'),
                                       ('W01 TRASPASO A TERCEROS PAGO COMISION BMRCASH Ref. REFBNTC00000003', 'debit'),
                                       ('0000000 CARGO TRANSFERENCIA ENLACE PAGO F 11AB COMISION', 'debit'),
                                       ('ABONO POR TRANSFERENCIA H001 COMISION', 'credit')]:
            with self.subTest(description=description):
                self.assertIsNone(party(description, direction))
        self.assertEqual(party('=: 01/ENE T20 SPEI RECIBIDOBANAMEX 0100001REC Ref. 0100000009 002 00002180000000000000 '
                               '085900000000000001 COMISION ESTATAL DE EJEMPLO', 'credit'), ('COMISION ESTATAL DE EJEMPLO', 'bbva-transfer-party'))
        self.assertEqual(party('0000000 COMISION TRANSFERENCIA SPEI'), ('Example Bank', 'bank-charge'))
        self.assertNotEqual((party('PAGO SERVICIO COMISION FEDERAL DE ELECTRICIDAD') or (None,))[0], 'Example Bank')
        # Only the bank's own fee, interest and dividend wording names the bank.
        for description, direction in [('OVERDRAFT PROTECTION TRANSFER FROM SAVINGS 0001', 'credit'), ('COM. FEDERAL DE ELECTRICIDAD PAGO', 'debit'),
                                       ('DIVIDEND EXAMPLE CORP COMMON STOCK', 'credit'), ('INTEREST PAYMENT TO EXAMPLE LENDER', 'debit')]:
            with self.subTest(description=description):
                self.assertNotEqual((party(description, direction) or (None,))[0], 'Example Bank')
        self.assertEqual(party('Comisión por servicios bancarios COMISION DE DIVISAS 1'), ('Example Bank', 'bank-charge'))
        self.assertEqual(party('PAGO TRANSFERENCIA SPEI HORA 10:00:06 ENVIADO A BANAMEX A LA CUENTA 002180000000000000 AL CLIENTE '
                               'EJEMPLO SA DE CV {1} DATO NO VERIFICADO POR ESTA INSTITUCION')[0], 'EJEMPLO SA DE CV')
        self.assertEqual(party('ENVIO SPEI HSBC MEXICO JUAN EJEMPLO 021180000000000000 PAGO 1')[0], 'JUAN EJEMPLO')
        self.assertEqual(party('ENVIO SPEI BBVA MEXICO | EJEMPLO SA DAT0 NO VERIFICADO | 012180001100000000 |')[0], 'EJEMPLO SA')


def reason(description, direction='debit', kind='checking', institution='Example Bank'):
    found = infer_payment_labels(description, direction=direction, account_type=kind, institution=institution)
    assert 'counterparty' not in found or 'counterparty_reason' not in found
    found = found.get('counterparty_reason')
    if found:
        assert found['source'] == 'description' and found['version'] == VERSION and found['explanation'] and found['value']
    return found['rule'] if found else None


class PhaseTwoPartyTests(unittest.TestCase):
    def test_own_account_transfers(self):
        for description, direction, expected in [
            ('3000001 CARGO TRANSFERENCIA ENLACE TRASPASO CUENTAS PROPIAS', 'debit', 'Own account (number not printed)'),
            ('AB TRANSF SPEI TRASPASO CTAS PROPIAS 1 012790000000001239', 'credit', 'Own account …1239'),
            ('N03 TRASPASO CUENTAS PROPIAS CUENTA: 0100000077 BNET Ref. 0040000007', 'credit', 'Own account …0077'),
            ('Withdrawal Online Banking Transfer To Loan ############0067 Funds Transfer via Mobile', 'debit', 'Own loan account …0067'),
            ('Deposit Transfer From Share 0000', 'credit', 'Own share account 0000'),
            ('TRUIST ONLINE TRANSFER ONLINE TO ****0014-', 'debit', 'Own account ****0014'),
            ('AUTO OVERDRAFT TRANSFER ACCOUNT NUMBER 1000000000123', 'credit', 'Own account …0123'),
            ('E57 TRASPASO ENTRE CUENTAS FOLIO: 0010000001 250.00MXP Ref. 1000001.1002.01', 'credit', 'Own account (number not printed)'),
        ]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction), (expected, 'own-account-transfer'))
        # A name printed in the transfer's own field wins over the own-account wording.
        self.assertEqual(party('ENVIO SPEI BBVA MEXICO | EJEMPLO SA DE CV DATO NO VERIFICADO POR ESTA INSTITUCION | '
                               '012180000000001234 | TRASPASO CTAS PROPIAS |')[0], 'EJEMPLO SA DE CV')
        # The wrong direction is not read as the holder's own transfer.
        self.assertIsNone(party('Deposit Transfer From Share 0000', 'debit'))

    def test_fixed_place_mexican_lines(self):
        self.assertEqual(party('0000000 CGO IMPTO FED TRANSF ELECT 04200AB1000000000001')[1], 'tax-authority-payee')
        self.assertEqual(party('PAGO CUOTAS PATRONALES Y00AAAA00A0000000000000000AAA000000N000N00Z000000010LA')[1], 'social-security-payee')
        self.assertEqual(party('C61 COMPRA CHEQUE DE CAJA JUAN EJEMPLO PEREZ Ref. 1001'), ('JUAN EJEMPLO PEREZ', 'cashier-cheque-payee'))
        self.assertEqual(party('TJ3 SITH200100001 EJEMPLO GAS S DE RL DE CV 1000001 Ref. 100000000000001', 'credit'),
                         ('EJEMPLO GAS S DE RL DE CV', 'bbva-sit-payer'))
        self.assertEqual(party('Z32 BBVA LEASING PAGO FACTURA FE000000000001 Ref. 200001'), ('BBVA LEASING', 'bbva-cie-payee'))
        self.assertEqual(party('Z3 CARGO COBRANZA EJEMPLO ARRENDADORA SA DE CV Ref. 0000200001'), ('EJEMPLO ARRENDADORA SA DE CV', 'bbva-direct-debit-payee'))
        self.assertEqual(party('RECEPCION SPEI | CB INTERCAM | DATO NO VERIFICADO POR ESTA INSTITUCION | | INTERCACB20220101-1 | 1 | '
                               'ABONO INTERCAM CTO 1 FOL 1 | INTERCAM BANCO | EJEMPLO SERVICIOS | 136180000000000001 |', 'credit')[1], 'brokerage-party')
        self.assertEqual(party('P14 PODER EJECUTIVO DEL 1000001 Ref. GUIA:1000001'), ('PODER EJECUTIVO DEL', 'bbva-cie-payee'))
        self.assertEqual(party('618000001 PAGO SERVICIO GOBIERNO DE EJEMPLO'), ('GOBIERNO DE EJEMPLO', 'service-payee'))
        self.assertEqual(party('0000000 DOMICILIACION PAGO SERVICIO 0000001 RFC EJE010101AB1 240301 0,000,048.48 EJEMPLO FINANCIAL SERVICES'),
                         ('EJEMPLO FINANCIAL SERVICES', 'direct-debit-payee'))
        self.assertEqual(party('DOMICILIACION PAGO SERVICIO 0250115 RFC EJE010101AB1'), ('RFC EJE010101AB1 (no name printed)', 'third-party-account'))
        self.assertEqual(party('ABONO POR DEVOLUCIONES SPEI HORA 10:00:00 DEVUELTO POR EJEMPLO BANK CUENTA 021180000000000001 '
                               'CLIENTE EJEMPLO SEGUROS SA CLAVE DE RASTREO 20250101400140BET0000000000001 CAUSA DEVOLUCION 02 Cuenta bloqueada',
                               'credit'), ('EJEMPLO SEGUROS SA', 'returned-transfer-party'))
        self.assertEqual(party('7000001 PAGO TRANSFERENCIA SPEI HORA 14:00:00 ENVIADO A BANAMEX A LA CUENTA 002000000000000001 —_— AL CLIENTE '
                               'MARIA EJEMPLO (1) (1) DATO NO VERIFICADO POR ESTA INSTITUCION')[0], 'MARIA EJEMPLO')
        self.assertEqual(party('ABONO TRANSFERENCIA TEF RECIBIDO DE BBVA MEXICO DE LA CUENTA 012180000000000001 DEL CLIENTE ANA EJEMPLO '
                               'CLAVE DE RASTREO SU0000000000 01 1000000001 REF 1', 'credit')[0], 'ANA EJEMPLO')
        for description, direction in [('(BE)TRASPASO A CUENTA: 001900000028', 'debit'),
                                       ('N06 PAGO CUENTA DE TERCERO CUENTA: 1500000088 BNET Ref. 0000600047', 'debit'),
                                       ('15/DIC_NO6 PAGO CUENTA DE TERCERO BNET 1100000086 NOMINA 1ER QNA DIC Ref. 0010000016', 'debit'),
                                       ('E17 ORDEN DE PAGO EXTRANJERO ORDENANTE: /04400000020 Ref. 3800006.0173.01', 'credit')]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction)[1], 'third-party-account')

    def test_bbva_concept_and_name_typed_together(self):
        self.assertEqual(party('T17 SPEI ENVIADO MIFEL 0310125NOMINA 2A QNA ENE25 JUAN EJEMPLO PEREZ'), ('JUAN EJEMPLO PEREZ', 'bbva-transfer-party'))
        self.assertEqual(party('T17 SPEI ENVIADO SANTANDER 0310125FINIQUITO ANA EJEMPLO GARCIA'), ('ANA EJEMPLO GARCIA', 'bbva-transfer-party'))
        self.assertEqual(party('T17 SPEI ENVIADO BANAMEX 0280225GTOS A COMPROBAR LUIS EJEMPLO DIAZ')[0], 'LUIS EJEMPLO DIAZ')
        self.assertEqual(party('T17 SPEI ENVIADO BANAMEX 0140325PAGO COT C10001 EJEMPLO EMPRESA SA DE CV')[0], 'EJEMPLO EMPRESA SA DE CV')
        # A concept with no name after it names nobody.
        self.assertIsNone(party('T17 SPEI ENVIADO BANAMEX 0000001NOMINA 2A QNA ENE21 Ref. 0000500001 002'))
        self.assertIsNone(party('T17 SPEI ENVIADO SANTANDER'))

    def test_us_layouts(self):
        self.assertEqual(party('DEBIT CARD PURCHASE AB/CD #300001 Z99 11-15 EXAMPLETOWN MD 7000'), ('AB/CD', 'debit-card-descriptor'))
        self.assertEqual(party('ACH CORP DEBIT FDMS PYMT EXAMPLE SHOP CUSTOMER ID 000-0000001-000')[0], 'FDMS')
        self.assertEqual(party('ACH CORP DEBIT DISCOUNT TRUIST MERCH SVC EXAMPLESHOP CUSTOMER ID 1')[0], 'TRUIST MERCH SVC')
        self.assertEqual(party('Recurring Withdrawal Bill Payment #000060000001 EXAMPLE LEASING 1 EXAMPLE DR EXAMPLE UT'),
                         ('EXAMPLE LEASING', 'bill-payee'))
        self.assertEqual(party('Deposit Debit Card CASH APP*JANE*CASH OUT San Francisco CA Date 12/30/23 o 0000800001 O 4000', 'credit'),
                         ('Cash App (JANE)', 'card-push-payment-source'))
        self.assertEqual(party('POS Credit Adjustment 2000 Transaction 10-25-21 Example Seniorcare', 'credit')[0], 'Example Seniorcare')
        self.assertEqual(party('VISA MONEY TRANSFER CREDIT 04-16-24 NEW YORK NY 7000 EXAMPLEPAY', 'credit')[0], 'EXAMPLEPAY')
        self.assertEqual(party('Wi thdrawal ACH EXAMPLE POWER TYPE: BILLPAY ID: 0000000001 CO: EXAMPLE POWER NAME: JANE DOE ACH Trace Number: 1')[0],
                         'EXAMPLE POWER')
        self.assertEqual(party('Withdrawal Debit Card 11/30 ~ 0000040001 0 EXAMPLE PARKING LOC 600 WASHINGTON DC')[1], 'debit-card-descriptor')

    def test_card_statement_lines(self):
        card = dict(kind='credit_card')
        for description, expected in [('EXAMPLE STEAK 0100001 EXAMPLETOWN VA', 'EXAMPLE STEAK'),
                                      ('F200000JP000ABCDE EXAMPLE NAIL BAR WASHINGTON DC', 'EXAMPLE NAIL BAR'),
                                      ('EXAMPLEAIR0010000000001 FORT WORTH TX NAME: DOE/JANE DEPART: 08/31/23', 'EXAMPLEAIR')]:
            with self.subTest(description=description):
                self.assertEqual(party(description, **card), (expected, 'card-line-merchant'))
        # Places, addresses and the issuer's own entries are not merchants.
        self.assertIsNone(party('COLUMBIA HEIGHTS', **card))
        self.assertIsNone(party('60001 - 1000 Q STEXAMPLETOWNDC', **card))
        self.assertIsNone(party('OFFER 04 MOVED TO STANDARD PURCH Promo Purchase-Offer 4', **card))
        self.assertEqual(party('tnl.e.resl Charge on Purchases', **card), ('Example Bank', 'bank-charge'))
        self.assertEqual(party('PYMT CARD SECURITY 800-0000001', **card), ('Example Bank', 'bank-charge'))

    def test_more_bank_services(self):
        for description, direction, rule in [('F04 VENTA FONDOS DE INVERSION OPERADO EN CANAL BNET Ref. EJEMPLO B-5 00', 'credit', 'bank-investment'),
                                             ('Y45 COMPENSACI N POR RETRASO Ref. COMP SPEI', 'credit', 'bank-charge'),
                                             ('C201.S.R. RETENIDO', 'debit', 'bank-tax-withheld'),
                                             ('M50 CAMBIOS/DERIVADOS/VOSTRO 100002 EJEMPLO SA DE CV Ref. 9990000001', 'credit', 'bank-currency-exchange'),
                                             ('CARGO A CUENTA|CLIENTE COMPRA|DEAL: 10000001|MEX|INTERCAM PAGA 1000.00 MXP|TC 20.2010', 'debit', 'bank-currency-exchange'),
                                             ('Deposit Dividend 0.050% Annual Percentage Yield Earned 0.05% from 07/01/22 through 09/30/22', 'credit', 'bank-interest'),
                                             ('| LINE OF CREDIT PAYMENT 200000000000001', 'debit', 'bank-credit-line'),
                                             ('NO CHARGE POSITIVE AVAIL BAL 36', 'credit', 'bank-charge')]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction), ('Example Bank', rule))

    def test_reasons_where_no_name_is_printed(self):
        for description, direction, kind, rule in [
            ('CAPITAL ONE MOBILE PYMTAuthDate 30-Sep', 'credit', 'credit_card', 'card-payment-source'),
            ('ONLINE PAYMENT, THANK YOU', 'credit', 'credit_card', 'card-payment-source'),
            # A card line that opens with the issuer's posting reference (invented reference).
            ('1234567AB00CDEFGH MOBILE PAYMENT - THANK YOU', 'credit', 'credit_card', 'card-payment-source'),
            ('1234567AB00CDEFGH PAYMENT - THANK YOU', 'credit', 'credit_card', 'card-payment-source'),
            ('W01 TRASPASO A TERCEROS PAGO EJEMPLO BMRCASH Ref. REFBNTC00000001', 'debit', 'checking', 'bbva-batch-payment'),
            ('_WO01 TRASPASO A TERCEROS ABONO PROYECTO EJEMPLO BMRCASH Ref. REFBNTC00000001', 'debit', 'checking', 'bbva-batch-payment'),
            ('W02 DEPOSITO DE TERCERO 20000001 BMRCASH Ref. REFBNTC00000002', 'credit', 'checking', 'bbva-batch-payment'),
            ('R01 PAGO DE NOMINA EJEMPLO SERVICIOS SA DE CV Ref. BC 4200000001', 'debit', 'checking', 'payroll-batch'),
            ('BT3 TRANSF SPEI BANAMEX NC0000004 NOMINA 1A QNA MAR25 Ref. 0000000001 002', 'debit', 'checking', 'payroll-batch'),
            ('E01 ORDEN DE PAGO EXTRANJERO INTERNET 0000000001000000030000.00USD Ref. 4000001.0177.01', 'debit', 'checking', 'foreign-payment-order'),
            ('3481', 'debit', 'checking', 'cheque-number-only'),
            ('| CHECK NUMBER 9001', 'debit', 'checking', 'cheque-number-only'),
            ('M97 DEPOSITO CHEQUE BBVA', 'credit', 'checking', 'cheque-deposit'),
            ('G30 RECIBO NO. Ref. P0QAAA0000AA', 'debit', 'checking', 'bank-collected-premium'),
            ('0000000 APORT LINEA CAPTURA INTERNET 060000000001', 'debit', 'checking', 'capture-line-payment'),
            ('T22 SPEI DEVUELTOBANAMEX', 'credit', 'checking', 'returned-transfer'),
            ('CARGO A CUENTA DE CHEQUES', 'debit', 'checking', 'type-only'),
            ('BUS ONLINE ACH SETTLEMENT', 'debit', 'checking', 'ach-batch'),
            ('T17 SPEI ENVIADO SANTANDER', 'debit', 'checking', 'bbva-transfer-no-name'),
            ('11000001 Retiro 0 0 1.00000000 0 0.000000', 'debit', 'checking', 'brokerage-cash-movement'),
        ]:
            with self.subTest(description=description):
                self.assertIsNone(party(description, direction, kind))
                self.assertEqual(reason(description, direction, kind), rule)
        # Cash is the other side of a cash movement: named Cash, not left unnamed. A mixed ATM deposit can hold cheques.
        for description, direction, rule in [('C02 DEPOSITO EN EFECTIVO Ref. 10001', 'credit', 'cash-deposit'),
                ('Withdrawal at ATM #000000000001 1000 EXAMPLE ST NE WASHINGTON DC ZZ0001', 'debit', 'cash-withdrawal'),
                ('ATM CASH WITHDRAWAL ON 01/02 1000 EXAMPLE AVE WASHINGTON DC', 'debit', 'cash-withdrawal')]:
            with self.subTest(description=description):
                self.assertEqual(party(description, direction, 'checking'), ('Cash', rule))
                self.assertIsNone(reason(description, direction, 'checking'))
        self.assertEqual(reason('TRUIST ATM MIXED DEPOSIT 01-02-24 10:00 AB01 EXAMPLE BRANCH 00000001', 'credit', 'checking'), 'cash-deposit')
        # A printed name is never replaced by a reason, and an unknown layout gets neither.
        self.assertIsNone(reason('T17 SPEI ENVIADO MIFEL 0310125NOMINA 2A QNA ENE25 JUAN EJEMPLO PEREZ'))
        self.assertIsNone(reason('SOMETHING UNREADABLE 1A2B'))

    def test_precision_review_fixes(self):
        # An account number is taken only when it is a valid CLABE (bank code and control digit) and printed
        # before the fiscal block; otherwise the own account is shown without a number.
        self.assertEqual(party('AB TRANSF SPEI TRASPASO CTAS PROPIAS 012180000000000125', 'credit'),
                         ('Own account …0125', 'own-account-transfer'))
        self.assertEqual(party('AB TRANSF SPEI TRASPASO CTAS PROPIAS 012180000000000126', 'credit'),
                         ('Own account (number not printed)', 'own-account-transfer'))
        self.assertEqual(party('ABONO TRANSFERENCIA ENLACE TRASPASO CUENTAS PROPIAS Informacion fiscal UUID 012345678901234567', 'credit'),
                         ('Own account (number not printed)', 'own-account-transfer'))
        for description, name in [
            ('Withdrawal Bill Payment #000000000001 EXAMPLE STREAM 800-555-0100 CA', 'EXAMPLE STREAM'),
            ('Withdrawal Bill Payment #000000000002 EXAMPLE PAY* LOAN 1A2B3C4D 800-555-0101 CA', 'EXAMPLE PAY'),
            ('Withdrawal Bill Payment #000000000003 Example Club•AB12CD34E Example.com/bill WA', 'Example Club'),
            ('Withdrawal Bill Payment #000000000004 EXAMPLE LEASING12345 HTTPSEXAMPLE.COM UT', 'EXAMPLE LEASING'),
        ]:
            with self.subTest(description=description):
                self.assertEqual(party(description), (name, 'bill-payee'))
        self.assertIsNone(party('ACH CORP DEBIT PYMT'))
        # Only named card processors are taken from ACH CORP DEBIT lines; other words there may be the entry's wording.
        self.assertIsNone(party('ACH CORP DEBIT EXAMPLE UTILITY PYMT'))
        self.assertEqual(party('T17 SPEI ENVIADO BANCOPPEL 0300425PRESTAMO PERSONAL JUAN EJEMPLO PEREZ'),
                         ('JUAN EJEMPLO PEREZ', 'bbva-transfer-party'))
        for description, name in [
            ('24000000AAAAAAAA1 TSTº EXAMPLE CAFE WASHINGTON DC', 'EXAMPLE CAFE'),
            ('sa "EXAMPLE APPAREL TOWNSVILLE MD', 'EXAMPLE APPAREL TOWNSVILLE'),
            ('24000000AAAAAAAA2 EXAMPLE STORE • 800-555-0102 MN', 'EXAMPLE STORE'),
            ('TM ·EXAMPLETIX S0S-555-0103 CA', 'TM ·EXAMPLETIX'),
        ]:
            with self.subTest(description=description):
                self.assertEqual(party(description, 'debit', 'credit_card'), (name, 'card-line-merchant'))


    def test_concepts_places_and_addresses_are_not_parties(self):
        for description, direction in [
            ('ACH CORP DEBIT ONLINE PAYMENT 123456', 'debit'), ('ACH CORP DEBIT AUTOPAY PMT 123456', 'debit'),
            ('ACH CORP DEBIT TRANSFER FEE', 'debit'), ('ACH CORP DEBIT LOAN PYMT 123', 'debit'),
            ('C61 COMPRA CHEQUE DE CAJA PAGO ANTICIPO OBRA Ref. 123', 'debit'), ('Z3 CARGO COBRANZA MENSUALIDAD Ref. 1', 'debit'),
            ('TJ3 SITH1234567 PAGO COLEGIATURA 12345 Ref. 1', 'credit'),
            ('VISA MONEY TRANSFER CREDIT 01-02-26 VISA DIRECT CA 1234 SAN FRANCISCO CA', 'credit'),
            ('VISA MONEY TRANSFER DEBIT 01-02-26 ANYTOWN 1234 RENT PAYMENT', 'debit'),
            ('CD PREMIUM MONTHLY 12345', 'debit'), ('RECURRING INTERNET PAYMENT CRCARDPMT ONLINE 12345', 'debit'),
            ('POS CREDIT ADJUSTMENT 1234 TRANSACTION 01-02-26 REFUND 12345', 'credit'),
            ('DEBIT CARD PURCHASE ANYTOWN TX #123456 12345', 'debit'), ('DEBIT CARD PURCHASE 123 MAIN #123456 12345', 'debit'),
            ('DOMICILIACION PAGO SERVICIO 12345 RFC ABC010203XY1 99 1,234.00 MENSUALIDAD', 'debit'),
            ('WITHDRAWAL BILL PAYMENT #123 RENT 555-123-4567', 'debit'),
        ]:
            with self.subTest(description=description):
                self.assertIsNone(party(description, direction))
        for description in ['ANYTOWN TX 555-123-4567', 'SALE CANCELLED 555-123-4567']:
            with self.subTest(description=description):
                self.assertIsNone(party(description, 'debit', 'credit_card'))
        # The statement bank still answers for its own fee; a name holding REF is not cut there.
        self.assertEqual(party('ACH CORP DEBIT MONTHLY SERVICE FEE'), ('Example Bank', 'bank-charge'))
        self.assertEqual(party('C61 COMPRA CHEQUE DE CAJA JUAN EJEMPLO REFACCIONES Ref. 1')[0], 'JUAN EJEMPLO REFACCIONES')
        # A BBVA concept and its reference, then the name to the end of the line.
        self.assertEqual(party('T17 SPEI ENVIADO BANCOPPEL 0100125AGUINALDO 2024 JUAN EJEMPLO PEREZ'), ('JUAN EJEMPLO PEREZ', 'bbva-transfer-party'))
        self.assertEqual(party('T17 SPEI ENVIADO BAJIO 0100125PAGO F A1000 EJEMPLO ELECTRONICA SA DE CV')[0], 'EJEMPLO ELECTRONICA SA DE CV')
        # Free concept text is named only when it has the shape of a party.
        for description in ['T17 SPEI ENVIADO BAJIO 0100125PAGO F A1000 EJEMPLO ELECTRONICA INDUSTRIAL',
                            'T17 SPEI ENVIADO BBVA 0012345PAGO FACTURA 123 RENTA OFICINA CENTRO',
                            'T17 SPEI ENVIADO BBVA 0012345FINIQUITO SEGUNDA PARTE',
                            'T17 SPEI ENVIADO BBVA 0012345NOMINA 12 SEMANA OCHO',
                            'C61 COMPRA CHEQUE DE CAJA OBRA NEGRA Ref. 1',
                            'Z3 CARGO COBRANZA EJEMPLO LEASING SEGUNDO PAGO Ref. 1']:
            with self.subTest(description=description):
                self.assertIsNone(party(description))
        self.assertIsNone(party('T17 SPEI ENVIADO BANORTE 0100125PAGO F 1000 CAMION JUAN EJEMPLO PEREZ'))

    def test_no_reason_is_given_where_a_name_may_be_printed(self):
        for description, direction, kind in [
            ('AB TRANSF SPEI JUAN EJEMPLO LOPEZ', 'credit', 'checking'),
            ('ABONO POR TRANSFERENCIA DE MARIA EJEMPLO GARCIA', 'credit', 'checking'),
            ('E17 ORDEN DE PAGO EXTRANJERO ORDENANTE: EJEMPLO TRADING LLC', 'credit', 'checking'),
            ('T17 SPEI ENVIADO BANORTE 0012345PAGO RENTA EJEMPLO PEREZ GOMEZ', 'debit', 'checking'),
            ('T20 SPEI RECIBIDO BANAMEX 0012345 REFERENCIA EJEMPLO PEREZ GOMEZ', 'credit', 'checking'),
            ('DEPOSITO EN EFECTIVO DE JUAN EJEMPLO', 'credit', 'checking'),
            ('C01 DEPOSITO EN EFECTIVO Ref. 1000AT JUAN', 'credit', 'checking'),
            ('76 STATION 1234 ANYTOWN CA', 'debit', 'credit_card'),
            ('54 PLACE BISTRO NEW YORK NY', 'debit', 'credit_card'),
        ]:
            with self.subTest(description=description):
                self.assertIsNone(reason(description, direction, kind))
        # The same layouts with only their own wording keep their reason.
        self.assertEqual(reason('T17 SPEI ENVIADO BANAMEX 0100125NOMINA 1A QNA ENE25 Ref. 0000000001 002'), 'bbva-transfer-no-name')
        self.assertEqual(reason('ABONO TRANSFERENCIA SPEI HORA 10:11:12', 'credit'), 'type-only')
        # Layouts with only a free-text concept and no payee field say exactly that, whatever the concept holds.
        self.assertEqual(reason('0000001 CARGO TRANSFERENCIA ENLACE PAGO PROVEEDOR EJEMPLO SA DE CV'), 'enlace-transfer')
        self.assertIn('no payee field', unnamed_reason('W01 TRASPASO A TERCEROS JUAN EJEMPLO LOPEZ BMRCASH', direction='debit')[0])
        for description, direction, kind in [('AB TRANSF SPEI ANA', 'credit', 'checking'), ('AB TRANSF SPEI LI WU', 'credit', 'checking'),
                                             ('ABONO POR TRANSFERENCIA DE GRUPO MEXICO', 'credit', 'checking'),
                                             ('T20 SPEI RECIBIDO BANORTE 0012345 BANCO AZTECA', 'credit', 'checking'),
                                             ('A01 DEPOSITO CHEQUE JUAN', 'credit', 'checking'), ('VTA CHQ CAJ JUAN EJEMPLO LOPEZ', 'debit', 'checking'),
                                             ('ATM DEPOSIT FROM JOHN EXAMPLE', 'credit', 'checking'), ('WITHDRAWAL AT ATM JOHN EXAMPLE', 'debit', 'checking'),
                                             ('CASH WITHDRAWAL TO JOHN EXAMPLE', 'debit', 'checking'), ('PAYMENT JOHN EXAMPLE', 'credit', 'credit_card'),
                                             ('123 MAIN ST JOES PIZZA', 'debit', 'credit_card'), ('1 - 800 FLOWERS', 'debit', 'credit_card')]:
            with self.subTest(description=description):
                self.assertIsNone(reason(description, direction, kind))
        self.assertEqual(party('C01 DEPOSITO EN EFECTIVO Ref. 1000', 'credit'), ('Cash', 'cash-deposit'))
        self.assertEqual(reason('60001 - 1000 Q STEXAMPLETOWNDC', 'debit', 'credit_card'), 'card-address-only')

    def test_no_place_address_bank_or_concept_as_a_party(self):
        # Card lines whose descriptor is a place, an address, a bank, a concept or a directed phrase name no merchant.
        for description in ['MONTERREY NL 555-123-4567', 'CIUDAD DE MEXICO 5512345678 MX', 'GUADALAJARA JAL 3312345678',
                            'SAN FRANCISCO #1234', 'AV REFORMA 222 CDMX 5512345678', 'CALLE 5 DE MAYO 5512345678',
                            'FINIQUITO 555-123-4567', 'BBVA MEXICO 5551234567', 'BANK OF AMERICA 555-123-4567',
                            'ZELLE TO JOHN EXAMPLE 5551234567', 'WELLS FARGO BANK 5551234567', 'CHASE BANK 5551234567',
                            'BANCO SANTANDER MEXICO 5512345678', 'BANK OF AMERICA ATM 555-123-4567', 'BANCOMER SA 5512345678',
                            'PASEO DE LA REFORMA 222 5512345678', 'INSURGENTES SUR 1602 5512345678', 'INSURGENTES SUR #1602 5512345678',
                            'INSURGENTES SUR 1602-A 5512345678', 'INSURGENTES SUR NO 1602 5512345678', 'MAIN STREET 12A 5551234567',
                            'THE BANK OF AMERICA 5551234567', 'MAIN ST. 12 5551234567', 'MAIN ST, 12 5551234567',
                            'MAIN ST STE 100 5551234567', 'MAIN ST APT 4 5551234567', 'INSURGENTES SUR NUM. 1602 5512345678',
                            'INSURGENTES SUR N 1602 5512345678', 'INSURGENTES SUR NO.1602 5512345678', 'BANORTE SUCURSAL 1234 5512345678',
                            'SANTANDER SUC 123 5512345678', 'HSBC BRANCH 555-123-4567', 'BANAMEX CAJERO 5512345678',
                            'JUAREZ NTE 12 5512345678', 'MAIN AV 12 5551234567', 'ELM PL 12 5551234567', 'PARK CIR 5 5551234567',
                            'MAIN ST12 5551234567', 'INSURGENTES SUR1602 5512345678', 'BBVA PRACTICAJA 5512345678',
                            'BANORTE CORRESPONSAL 1234 5512345678', 'SANTANDER SUPERMOVIL 5512345678']:
            with self.subTest(description=description):
                self.assertIsNone(party(description, 'debit', 'credit_card'))
        self.assertEqual(party('STARBUCKS #12345 WASHINGTON DC', 'debit', 'credit_card')[0], 'Starbucks')
        # Names taken from free text must be shaped like a party: not a borough, a town and state, a concept with a legal form.
        for tail in ['NOMINA A12 MIGUEL HIDALGO', 'BENITO JUAREZ', 'DOLORES HIDALGO GTO', 'JESUS MARIA AGS', 'VICTORIA DE DURANGO',
                     'FINIQUITO GUADALUPE NL', 'NOMINA A12 VIDA SA', 'BONO SC', 'HORAS EXTRA SC', 'CDMX AC', 'CALLE JUAREZ SA',
                     'GRUPO DE TRABAJO']:
            with self.subTest(tail=tail):
                self.assertIsNone(party('T17 SPEI ENVIADO BANORTE 0012345 ' + tail))
        self.assertIsNone(party('TJ3 SITH1234567 VICTORIA DE DURANGO 12345 Ref. 1', 'credit'))
        self.assertIsNone(party('C61 COMPRA CHEQUE DE CAJA MIGUEL HIDALGO Ref. 123'))
        self.assertEqual(party('CITI TRENDS 123 5551234567', 'debit', 'credit_card')[0], 'CITI TRENDS')
        for tail in ['SANTANDER SA', 'BANORTE SA DE CV', 'BANCO AZTECA SA', 'PASEO DE LA REFORMA SA DE CV', 'INSURGENTES SUR SA DE CV',
                     'INSURGENTES SUR 1602-A SA']:
            with self.subTest(tail=tail):
                self.assertIsNone(party('T17 SPEI ENVIADO BANORTE 0012345 ' + tail))
        # A company word after a name still names the company (a truncated CORPORATIVO, FINANCIAL).
        self.assertEqual(party('TJ3 SITH1234567 EJEMPLO SERVICIOS CORPORAT1234567 Ref. 1234567', 'credit')[0], 'EJEMPLO SERVICIOS CORPORAT')
        # The card issuer named in a card payment is the payee.
        self.assertEqual(party('RECURRING INTERNET PAYMENT CRCARDPMT CAPITAL ONE 3ABCDEFGHIJ1234')[0], 'CAPITAL ONE')

    def test_no_reason_where_a_name_is_printed(self):
        for description, direction, kind in [
            ('CARGO TRANSFERENCIA ENLACE BENEFICIARIO JUAN EJEMPLO', 'debit', 'checking'),
            ('ABONO TRANSFERENCIA ENLACE DEL CLIENTE JUAN EJEMPLO', 'credit', 'checking'),
            ('W01 TRASPASO A TERCEROS BENEFICIARIO JUAN EJEMPLO', 'debit', 'checking'),
            ('T16 PAGO DE NOMINA BENEFICIARIO JUAN EJEMPLO', 'debit', 'checking'),
            ('T17 SPEI ENVIADO BANORTE 0012345BIMBO', 'debit', 'checking'),
            ('T20 SPEI RECIBIDOBANORTE 0012345JUAN', 'credit', 'checking'),
            ('ABONO 7ELEVEN', 'credit', 'checking'), ('CARGO 99MINUTOS', 'debit', 'checking'),
            ('ATM CASH DEPOSIT 12 ACME LLC', 'credit', 'checking'), ('ATM DEPOSIT 12345 MARIA EJEMPLO', 'credit', 'checking'),
            ('ATM WITHDRAWAL 12 JOHN EXAMPLE', 'debit', 'checking'),
            ('DEPOSIT SHARED BRANCH MOBILE DEPOSIT JOHN EXAMPLE TX', 'credit', 'checking'),
            ('PAYMENT TO JOHN TX', 'credit', 'credit_card'),
            ('T17 SPEI ENVIADO BANORTE 0012345BIMBO123', 'debit', 'checking'), ('T17 SPEI ENVIADO BANORTE BIMBO0012345', 'debit', 'checking'),
            ('T17 SPEI ENVIADO BANORTE 0012345REF1BIMBO', 'debit', 'checking'), ('T17 SPEI ENVIADO BANORTE 123ELEVEN', 'debit', 'checking'),
            ('T17 SPEI ENVIADO BANAMEX 0012345 Ref. 0000001 002 EJEMPLO AUTO', 'debit', 'checking'),
            ('CARGO TRANSFERENCIA ENLACE PAGO A JUAN EJEMPLO', 'debit', 'checking'),
        ]:
            with self.subTest(description=description):
                self.assertIsNone(reason(description, direction, kind))
        # References that hold letters (insurance receipts) are not names.
        self.assertEqual(reason('G30 RECIBO NO. Ref. P12Q34OB56CR'), 'bank-collected-premium')
        self.assertEqual(reason('W01 TRASPASO A TERCEROS SALDO A FAVOR BMRCASH Ref. REFBNTC00123'), 'bbva-batch-payment')


class ReadingSpeedKeepsReadingsTests(unittest.TestCase):
    """The faster readers give exactly what the pattern-per-call readers gave."""

    def test_name_as_printed_is_the_last_regex_printing(self):
        import random, re, unicodedata
        from services.financial.payment_parties import _as_printed

        def by_regex(name, raw):
            folded, at = [], []
            for i, c in enumerate(raw):
                for b in (' ' if c.isspace() else ''.join(x for x in unicodedata.normalize('NFKD', c) if not unicodedata.combining(x)).upper()):
                    folded.append(b)
                    at.append(i)
            found = [*re.finditer(r'(?<![A-Z0-9])' + r'\s+'.join(re.escape(w) for w in name.upper().split()) + r'(?![A-Z0-9])', ''.join(folded))]
            return ' '.join(raw[at[found[-1].start()]:at[found[-1].end() - 1] + 1].split()) if found else name

        cases = [('A A', 'a a a'), ('JOSE PEREZ', 'SPEI ENVIADO José  Pérez REF 1 José\u00a0Pérez'), ('ANA', 'ANAANA ANA1 ana.'),
                 ('SS', 'Straße'), ('FI', 'ﬁ x'), ('J', 'ǰ'), ('A B', 'A\x1cB'), ('A', '¨A')]
        rng = random.Random(7)
        chars = ['A', 'B', 'a', 'á', 'É', ' ', '\t', '\x1c', '\u00a0', '¨', '.', '1', 'ß', 'ǰ', 'ﬁ', '*', '(']
        for _ in range(3000):
            raw = ''.join(rng.choice(chars) for _ in range(rng.randint(0, 12)))
            name = ' '.join(''.join(rng.choice('AB1.*(J') for _ in range(rng.randint(1, 2))) for _ in range(rng.randint(1, 3)))
            cases.append((name, raw))
        for name, raw in cases:
            self.assertEqual(_as_printed(name, raw), by_regex(name, raw), (name, raw))

    def test_first_merchant_in_list_order_wins(self):
        from services.financial.payment_inference import MERCHANTS, merchant_match

        def by_loop(text):
            for pattern, merchant, kind in MERCHANTS:
                found = pattern.match(text)
                if found:
                    return found[0], merchant, kind
            return None

        for text in ['UBER EATS 123', 'UBER TRIP', 'UBERX', 'TRU BY HILTON DC', 'HILTON', 'DD *DOORDASH X', 'WAL-MART #1',
                     'AMAZON.COM*AB1', 'AMZN MKTP', 'THE OLIVE GARD1', 'SHELLY', 'CVS/PHARMACY #02', 'NOTHING', '']:
            self.assertEqual(merchant_match(text), by_loop(text), text)

    def test_folding_character_by_character_matches_the_whole_string(self):
        import unicodedata
        from services.financial.payment_inference import normalized
        for text in ['José  Pérez', 'Straße', 'ǰ', 'ﬁ', 'e\u0301\u0327', 'ÅNGSTRÖM\u00a0x', 'plain ascii', '', None]:
            whole = ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text or '') if not unicodedata.combining(c)).upper().split())
            self.assertEqual(normalized(text), whole, text)

if __name__ == '__main__':
    unittest.main()
