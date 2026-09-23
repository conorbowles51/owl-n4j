"""Synthetic movement/account sections; no client source or financial data."""
from copy import deepcopy
from unittest import TestCase
from services.financial.statement_import_santander import santander_catalog, propose_santander_statement
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_review_checks import check_statement_rows
from tests.test_financial_statement_import_scotiabank import source


def statement(merged=False):
    header=[[(30000,20000,200000,'Banco Santander Mexico, S.A.')],
        [(30000,40000,210000,'EXAMPLE SERVICES SA DE CV'),(350000,40000,190000,'CODIGO DE CLIENTE NO. 12345678')],
        [(330000,60000,220000,'PERIODO DEL 01-SEP-2024 AL 30-SEP-2024')],
        [(330000,80000,65000,'MONEDA'),(430000,80000,100000,'MONEDA NACIONAL')]]
    columns=lambda y:[(30000,y,45000,'FECHA'),(80000,y,30000,'FOLIO'),(120000,y,80000,'DESCRIPCION'),(370000,y,50000,'DEPOSITO'),(435000,y,50000,'RETIRO'),(500000,y,50000,'SALDO')]
    rows=header+[
        [(30000,120000,400000,'Detalle de movimientos cuenta de cheques.')],
        [(30000,140000,400000,'CUENTA SANTANDER PYME 65-00001234-0')],
        [(30000,160000,210000,'SALDO FINAL DEL PERIODO ANTERIOR:'),(300000,160000,60000,'$100.00')],columns(180000),
        [(30000,200000,45000,'02-SEP-2024'),(80000,200000,30000,'0000001'),(120000,200000,180000,'EXAMPLE DEPOSIT'),(380000,200000,40000,'25.00'),(510000,200000,40000,'125.00')],
        [(30000,230000,45000,'03-SEP-2024'),(80000,230000,30000,'0000002'),(120000,230000,180000,'EXAMPLE PAYMENT\nA SECOND DESCRIPTION LINE'),(445000,230000,40000,'50.00'),(510000,230000,40000,'75.00')],
        [(120000,260000,80000,'TOTAL'),(380000,260000,40000,'25.00'),(445000,260000,40000,'50.00')],
        [(30000,280000,260000,'SALDO FINAL DEL PERIODO:'),(510000,280000,40000,'$75.00')],
        [(30000,330000,400000,'Detalles de movimientos Dinero Creciente Santander.')],
        [(30000,350000,400000,'INVERSION CRECIENTE 66-00001234-0')],
        [(30000,370000,260000,'SALDO FINAL DEL PERIODO ANTERIOR:'),(510000,370000,40000,'0.00')],columns(390000),
        [(120000,410000,80000,'TOTAL'),(380000,410000,40000,'0.00'),(445000,410000,40000,'0.00')],
        [(30000,430000,260000,'SALDO FINAL DEL PERIODO:'),(510000,430000,40000,'$0.00')]]
    if merged:
        for i in [8,9]:
            first=rows[i][:3];rows[i]=[(30000,first[0][1],270000,'|'.join(c[3] for c in first))]+rows[i][3:]
    return [source(1,rows)]


class SantanderTests(TestCase):
    def test_native_and_scanned_rows_save_distinct_accounts_and_controls(self):
        for merged in [False,True]:
            with self.subTest(merged=merged):
                ss=statement(merged);before=deepcopy(ss)
                choices=currencies_by_statement(santander_catalog(ss)[0],ss)
                self.assertEqual(len(choices),2)
                self.assertEqual([c['currency'] for c in choices],['MXN','MXN'])
                for choice,count in zip(choices,[2,0]):
                    rows=propose_santander_statement(ss,'MXN',choice)['rows']
                    tx=[r for r in rows if not r['excluded']]
                    self.assertEqual(len(tx),count)
                    checks=check_statement_rows(rows)
                    self.assertEqual(checks['balance_status'],'matches')
                    self.assertEqual(checks['flagged_rows'],0)
                    if count:
                        self.assertEqual([r['fields']['direction'] for r in tx],['credit','debit'])
                        self.assertEqual([r['fields']['amount_minor'] for r in tx],['2500','5000'])
                        self.assertIn('SECOND DESCRIPTION',tx[1]['fields']['description'])
                self.assertEqual(ss,before)

    def test_unknown_currency_is_not_guessed_from_dollar_symbol(self):
        ss=statement()
        for r in ss[0]['rows']:
            for c in r['cells']:
                c['expected_text']=c['expected_text'].replace('MONEDA NACIONAL','UNREADABLE')
        self.assertTrue(all(c['currency']=='' for c in currencies_by_statement(santander_catalog(ss)[0],ss)))

    def test_conflicting_period_or_unbranded_copy_is_not_accepted(self):
        for change in ['period','bank']:
            ss=statement()
            if change=='bank':ss[0]['rows'][0]['cells'][0]['expected_text']='Another bank'
            else:ss[0]['rows'][2]['cells'][0]['expected_text']+=' PERIODO DEL 01-OCT-2024 AL 31-OCT-2024'
            self.assertEqual(santander_catalog(ss)[0],[])
