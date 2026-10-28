"""The other side of a payment as each statement layout prints it.

Every description below is a real statement line with its layout kept exactly
(spacing, separators, OCR marks, footnotes); only names, accounts and
references are replaced by invented ones so no case material is committed.
"""
import unittest

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
                'EJEMPLO SERV (1 (1) DATO NO VERIFICADO POR ESTA INSTITUCION CLAVE DE RASTREO 2025010140014 BETO000000000001')
        self.assertEqual(party(torn)[0], 'EJEMPLO SERV')

    def test_delimited_spei_takes_the_name_field_without_the_qualification(self):
        sent = ('ENVIO SPEI BBVA MEXICO | EJEMPLO SERV AMB DATO NO VERIFICADO POR ESTA INSTITUCION | 012180001100000000 | '
                '136- 01/01/2025/01-1900000001 | 0000001 | TRASPASO CTAS PROPIAS | INTERCAM BANCO | EJEMPLO SERVICIOS S.A. DE C')
        self.assertEqual(party(sent), ('EJEMPLO SERV AMB', 'spei-delimited-party'))
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
                               'Nombre Beneficiario: EJEMPLO SERV SA DE CV Clave de Rastreo: 10000001 Referencia Numerica: 1'),
                         ('EJEMPLO SERV SA DE CV', 'monex-named-party'))
        self.assertEqual(party('Depósito Emisor: BBVA BANCOMER ] Fecha Confirmacion de liquidacion:01-01-2019 12:00:00 ] Monto :100000 ] '
                               'Cuenta ordenante:012180000000000000 ] Nombre del Ordenante:EJEMPLO SERV SA DE C V ] Clave de Rastreo:0026',
                               'credit')[0], 'EJEMPLO SERV SA DE C V')
        self.assertEqual(party('RETIRO BENEFICIARIO KEN EJEMPLO BANCO MIZUHO BANK, LTD. CUENTA 1300000000')[0], 'KEN EJEMPLO')
        self.assertEqual(party('RETIRO BENEFICIARIO EJEMPLO SERV SA DE CV RFC:ASE000000AA0 BANCO BBVA BANCOMER CUENTA 0110000000 Texto:eur')[0],
                         'EJEMPLO SERV SA DE CV')
        self.assertEqual(party('RETIRO Receptor BBVA MEXICO, Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERV SA DE CV, '
                               'Concepto TRASPASO CUENTAS PROPIAS, Ref 100000002')[0], 'EJEMPLO SERV SA DE CV')
        # On a deposit the printed beneficiary is the account holder, so no other side is taken from it.
        self.assertIsNone(party('Depósito En Cta De Captación Con Origen En Cta De Captación BENEFICIARIO EJEMPLO SERV SA DE CV '
                                'RFC:ASE000000AA0 BANCO BANCO MONEX CUENTA 2800000 traspaso de fondos del contrato 3000000', 'credit'))

    def test_bbva_spei_name_follows_the_references(self):
        self.assertEqual(party('T20 SPEI RECIBIDOSANTANDER 10000000000000001 Ref. 0100000001 014 0001400000001 1000001 '
                               '20250101400140ABC0000000000001 EJEMPLO GERENCIA DE TESORERI', 'credit'),
                         ('EJEMPLO GERENCIA DE TESORERI', 'bbva-transfer-party'))
        self.assertEqual(party('117 SPE] ENVIADO KAPITAL 0010125TRASPASO CUENTAS PROPIAS Ref. 0000000001 128 00128180000000000000 '
                               '002601002501010000000001 EJEMPLO SERV')[0], 'EJEMPLO SERV')
        self.assertEqual(party('T20 SPEI RECIBIDOKUSPIT 0000001PRESTAMO Ref. 0100000002 653 00653180000000000000 EXAMPLEPAY '
                               '0100000003 EJEMPLO IMPULSORA SA DE CV', 'credit')[0], 'EJEMPLO IMPULSORA SA DE CV')
        self.assertEqual(party('T17 SPEI ENVIADO AZTECA 0010125NOMINA 010125 Ref. 0000000002 127 CARLOS EJEMPLO PRUEBA')[0], 'CARLOS EJEMPLO PRUEBA')
        self.assertEqual(party('T17 SPEI ENVIADO BANORTE 0010125NOMINA 1A QNA ENE25 00001234567800000000 JULIO EJEMPLO PRUEBA')[0],
                         'JULIO EJEMPLO PRUEBA')
        self.assertEqual(party('T17 SPEI ENVIADO BANCOPPEL 0010125NOMINA 010125 LUIS EJEMPLO PRUEBA')[0], 'LUIS EJEMPLO PRUEBA')
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
        # A federal tax payment names no payee; it is not the bank's.
        self.assertIsNone(party('0000000 CGO IMPTO FED TRANSF ELECT 01011XA0000000000001'))

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
               'Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERV SA DE CV, Ref 100000003')
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
        # The member's own share or loan is not another party.
        self.assertIsNone(party('Withdrawal Online Banking Transfer To Share 0001 Funds Transfer via Mobile'))
        self.assertIsNone(party('Withdrawal Online Banking Transfer To Loan ############0001 Funds Transfer via Mobile'))
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
                                       ('Check 1001', 'debit'), ('R01 PAGO DE NOMINA EJEMPLO SERV SA DE CV Ref. BC 1000000001', 'debit')]:
            with self.subTest(description=description):
                self.assertIsNone(party(description, direction))

    def test_review_regressions(self):
        # OCR splits the debit card prefix after M&T's bar: the merchant is read, not the split word.
        self.assertEqual(party('~Ii thdrawal Debit Card / 01/01 0 0000000007 0 LYFT *SCOOTER RIDE LYFT.COM CA')[0], 'Lyft')
        self.assertEqual(party('~Wi thdrawal Debit Card 01/01 0 0000000001 0 EJEMPLO CAFE MD')[0], 'EJEMPLO CAFE')
        # A bank service on an account with no bank recorded names nobody, not the name printed in it.
        for description in ['Comision Por Transferencia Retiro de Comision e IVA (Comision $5.00, IVA $.80), Receptor BBVA MEXICO, '
                            'Cuenta beneficiaria 012180000000000000, Beneficiario EJEMPLO SERV SA DE CV, Ref 100000003',
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


if __name__ == '__main__':
    unittest.main()
