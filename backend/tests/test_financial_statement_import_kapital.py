"""Synthetic Kapital product tables, including continuation and currency scopes."""
from copy import deepcopy
from unittest import TestCase
from services.financial.statement_import_kapital import kapital_catalog, propose_kapital_statement
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_review_checks import check_statement_rows
from tests.test_financial_statement_import_scotiabank import source


def header():
    return [
        [(20000,20000,120000,'kapital'),(360000,20000,200000,'ESTADO DE CUENTA UNICO')],
        [(360000,40000,220000,'Periodo DEL 2026-05-01 AL 2026-05-31')],
        [(360000,60000,35000,'Numero'),(410000,60000,100000,'420260512345678')],
        [(360000,80000,35000,'Cliente'),(410000,80000,100000,'12345678')],
        [(360000,100000,35000,'R.F.C.'),(410000,100000,100000,'EXA010101AB1')],
    ]


def product(currency='MN',clabe='128000000000000001',top=300000):
    return [
        [(40000,top,205000,'SERVICIO EMPRESARIAL FX KAPITAL 123-456-001-6'),(260000,top,170000,'CLABE '+clabe)],
        [(40000,top+20000,170000,'Moneda'),(220000,top+20000,40000,currency)],
        [(40000,top+40000,170000,'Saldo Inicial'),(220000,top+40000,40000,'0.00 '+currency)],
        [(40000,top+60000,170000,'+ Depositos'),(220000,top+60000,40000,('0.01 ' if currency=='MN' else '0.00 ')+currency)],
        [(40000,top+80000,170000,'- Retiros'),(220000,top+80000,40000,('0.01 ' if currency=='MN' else '0.00 ')+currency)],
        [(40000,top+100000,170000,'Saldo Final'),(220000,top+100000,40000,'0.00')],
    ]


def table(top=430000):
    return [
        [(245000,top,46000,'CONCEPTO'),(400000,top,46000,'DEPOSITOS'),(467000,top,35000,'RETIROS'),(529000,top,28000,'SALDO')],
        [(41000,top+10000,7000,'29'),(78000,top+10000,35000,'12345678'),(147000,top+10000,130000,'COMISION POR TIMBRADO FISCAL'),(499000,top+10000,13000,'0.01'),(555000,top+10000,16000,'0.01-')],
        [(41000,top+20000,7000,'29'),(78000,top+20000,35000,'12345678'),(147000,top+20000,130000,'DESCUENTO POR TIMBRADO FISCAL'),(440000,top+20000,13000,'0.01'),(558000,top+20000,13000,'0.00')],
        [(370000,top+30000,23000,'Total'),(440000,top+30000,13000,'0.01'),(499000,top+30000,13000,'0.01'),(558000,top+30000,13000,'0.00')],
    ]


def statement():
    return [source(1,header()+[
        [(30000,120000,160000,'EXAMPLE SERVICES')],[(30000,150000,160000,'Persona Moral')],
    ]+product()+table()),source(2,header()+product('USD','128000000000000002'))]


class KapitalProposalTests(TestCase):
    def test_small_opposite_postings_keep_shared_folio_and_trailing_negative_balance(self):
        s=statement();before=deepcopy(s)
        choices=currencies_by_statement(kapital_catalog(s)[0],s)
        self.assertEqual([c['currency'] for c in choices],['MXN','USD'])
        self.assertEqual([c['account_reference'] for c in choices],['128000000000000001','128000000000000002'])
        self.assertTrue(all(c['holder']=='EXAMPLE SERVICES' for c in choices))
        rows=propose_kapital_statement(s,'MXN',choices[0])['rows']
        tx=[r for r in rows if not r['excluded']]
        self.assertEqual([r['fields']['date'] for r in tx],['2026-05-29']*2)
        self.assertEqual([r['fields']['amount_minor'] for r in tx],['1','1'])
        self.assertEqual([r['fields']['direction'] for r in tx],['debit','credit'])
        self.assertEqual([r['fields']['balance'] for r in tx],['-1','0'])
        self.assertEqual(check_statement_rows(rows)['balance_status'],'matches')
        self.assertEqual(check_statement_rows(rows)['flagged_rows'],0)
        usd=propose_kapital_statement(s,'USD',choices[1])['rows']
        self.assertEqual(check_statement_rows(usd)['transaction_count'],0)
        self.assertEqual(check_statement_rows(usd)['balance_status'],'matches')
        self.assertEqual(s,before)

    def test_monthly_header_number_is_not_the_account_identity(self):
        s=statement();before=kapital_catalog(s)[0]
        for source_ in s:
            for row in source_['rows']:
                for cell in row['cells']:
                    cell['expected_text']=cell['expected_text'].replace('420260512345678','420260612345678').replace('2026-05-01','2026-06-01').replace('2026-05-31','2026-06-30')
        after=kapital_catalog(s)[0]
        self.assertEqual([c['account_reference'] for c in before],[c['account_reference'] for c in after])
        self.assertNotEqual(before[0]['statement_reference'],after[0]['statement_reference'])

    def test_both_products_cite_the_holder_identifier_from_the_cover(self):
        from services.financial.account_ownership import holder_identifiers
        s=statement()
        for clabe in ('128000000000000001','128000000000000002'):
            found=holder_identifiers(s,account_reference=clabe,holder='EXAMPLE SERVICES')
            self.assertEqual({v['value'] for v in found},{'EXA010101AB1'})
            self.assertTrue(all(v['page_number']==1 for v in found))

    def test_malformed_payment_remains_visible_and_does_not_become_balances_only(self):
        s=statement();s[0]['rows'][-3]['cells'][-2]['expected_text']='?.01'
        c=kapital_catalog(s)[0][0];rows=propose_kapital_statement(s,'MXN',c)['rows']
        self.assertEqual(check_statement_rows(rows)['transaction_count'],2)
        self.assertGreater(check_statement_rows(rows)['flagged_rows'],0)
        self.assertEqual(check_statement_rows(rows)['balance_status'],'unavailable')

    def test_source_currency_conflict_is_flagged_instead_of_overwriting_printed_currency(self):
        s=statement();c=kapital_catalog(s)[0][0]
        rows=propose_kapital_statement(s,'USD',c)['rows']
        self.assertTrue(any('printed amount is MXN' in issue for r in rows for issue in r['issues']))

    def test_missing_header_retains_the_unresolved_payments_for_review(self):
        s=statement();s[0]['rows'][-4]['cells'][0]['expected_text']='Unreadable heading'
        c=kapital_catalog(s)[0][0]
        rows=propose_kapital_statement(s,'MXN',c)['rows']
        self.assertEqual(check_statement_rows(rows)['transaction_count'],2)
        self.assertEqual(check_statement_rows(rows)['flagged_rows'],2)
        self.assertTrue(all(r['issues'] for r in rows if not r['excluded']))

    def test_wrapped_transfer_and_payment_continue_before_the_next_currency_product(self):
        first=header()+[[(30000,120000,160000,'EXAMPLE SERVICES')],[(30000,150000,160000,'Persona Moral')]]+product()
        for row in first:
            for cell_index,cell in enumerate(row):
                if cell[3]=='0.01 MN':row[cell_index]=(*cell[:3],'5,000.00 MN')
        first += table()[:2]
        first[-1]=[(41000,440000,7000,'17'),(78000,440000,35000,'11111111'),(147000,440000,130000,'RECEPCION SPEI | EXAMPLE BANK'),(415000,440000,38000,'5,000.00'),(532000,440000,39000,'5,000.00')]
        first += [[(147000,450000,180000,'EXAMPLE SERVICES | TRASPASO ENTRE CUENTAS')]]
        second=header()+table(180000)[:1]+[
            [(41000,190000,7000,'17'),(78000,190000,35000,'22222222'),(147000,190000,130000,'ENVIO SPEI | WATER AUTHORITY'),(474000,190000,38000,'5,000.00'),(558000,190000,13000,'0.00')],
            [(370000,200000,23000,'Total')],
        ]+product('USD','128000000000000002')
        s=[source(1,first),source(2,second)];c=kapital_catalog(s)[0]
        rows=propose_kapital_statement(s,'MXN',c[0])['rows'];tx=[r for r in rows if not r['excluded']]
        self.assertEqual(len(tx),2)
        self.assertIn('TRASPASO ENTRE CUENTAS',tx[0]['fields']['description'])
        self.assertTrue(tx[0]['continuation_sources'])
        self.assertEqual([r['fields']['amount_minor'] for r in tx],['500000','500000'])
        self.assertEqual([r['fields']['direction'] for r in tx],['credit','debit'])
        self.assertEqual(check_statement_rows(rows)['balance_status'],'matches')
        self.assertEqual(check_statement_rows(propose_kapital_statement(s,'USD',c[1])['rows'])['transaction_count'],0)


class KapitalImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        from tests.test_financial_statement_import_scotiabank import ScotiabankImportTests
        self.f=StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation');self.f.setUp()
        ScotiabankImportTests.prepare(self,statement())
    def tearDown(self):self.f.tearDown()
    def test_import_sections_reopen_and_retry_keeps_two_real_postings(self):
        from services.financial.statement_import import read_statement_import
        from services.financial.import_batches import initial_request
        receipts=[]
        with self.f.SessionLocal() as db:
            choices=read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id)['statement_choices']
        for c,count in zip(choices,[2,0]):
            with self.f.SessionLocal() as db:
                proposal=read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,statement_id=c['id'])
            self.assertEqual(proposal['transaction_count'],count)
            self.assertEqual(proposal['needs_attention'],0)
            request=initial_request(proposal);receipt=self.f.confirm(request);receipts.append(receipt)
            self.assertEqual(receipt['transaction_count'],count)
            self.assertEqual(receipt['incomplete_count'],0)
            self.assertFalse(self.f.confirm(request)['created'])
        self.assertNotEqual(receipts[0]['account_id'],receipts[1]['account_id'])
