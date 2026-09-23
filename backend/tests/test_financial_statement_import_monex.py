"""Synthetic multi-currency Monex statements; no client records in fixtures."""
from copy import deepcopy
from unittest import TestCase
from uuid import UUID

from services.financial.statement_import_monex import monex_catalog, propose_monex_statement
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_review_checks import check_statement_rows
from tests.test_financial_statement_import_scotiabank import source


def statement():
    cover = source(1, [
        [(20000,20000,100000,'Monex'), (300000,20000,100000,'Estado de Cuenta')],
        [(300000,100000,200000,'EXAMPLE SERVICES SA DE CV')],
        [(300000,120000,200000,'EXAMPLE ADDRESS')],
        [(300000,140000,50000,'C.P.'),(420000,140000,50000,'00000')],
        [(300000,160000,100000,'TIPO DE CONTRATO:'),(420000,160000,150000,'PERSONA MORAL')],
        [(300000,180000,100000,'CONTRATO:'),(420000,180000,50000,'7654321')],
        [(300000,200000,100000,'CTA. CLABE:'),(420000,200000,150000,'112000000000000001')],
        [(300000,220000,100000,'RFC TITULAR:'),(420000,220000,150000,'EXA010101AB1')],
        [(300000,240000,100000,'PERIODO:'),(420000,240000,180000,'Del 1 Mayo 2026 al 31 mayo 2026')],
    ])
    pages = [cover]
    for page, label, balance in [(2,'Peso Mexicano','321.45'),(3,'euro','0.79')]:
        pages.append(source(page, [
            [(20000,20000,100000,'MONEX'),(400000,20000,150000,'CONTRATO: 7654321')],
            [(20000,50000,140000,'Resumen Cuenta')],
            [(20000,70000,140000,label)],
            [(20000,90000,140000,'Saldo inicial:'),(200000,90000,60000,balance)],
            [(20000,110000,140000,'+ Total abonos:'),(200000,110000,60000,'0.00')],
            [(20000,130000,140000,'- Total cargos:'),(200000,130000,60000,'0.00')],
            [(20000,150000,140000,'Saldo vista:'),(200000,150000,60000,balance)],
            [(20000,170000,140000,'Saldo promedio:'),(200000,170000,60000,balance)],
            [(440000,700000,100000,f'Hoja {page} de 6')],
        ]))
    for page, label in [(4,'Referencias bancarias'),(5,'Estimado cliente:'),(6,'Aviso de seguridad de la informacion')]:
        pages.append(source(page, [
            [(20000,20000,100000,'MONEX'),(400000,20000,150000,'CONTRATO: 7654321')],
            [(20000,50000,250000,label)],
            [(20000,70000,250000,'Routing instructions USD EUR GBP MXN')],
            [(440000,700000,100000,f'Hoja {page} de 6')],
        ]))
    return pages


class MonexProposalTests(TestCase):
    def test_currency_sections_keep_zero_activity_and_balances_separate(self):
        sources = statement(); before = deepcopy(sources)
        catalog = statement_catalog(sources)
        self.assertTrue(catalog['complete_coverage'])
        choices = currencies_by_statement(catalog['statements'], sources)
        self.assertEqual([c['currency'] for c in choices], ['MXN','EUR'])
        self.assertEqual(len({c['id'] for c in choices}), 2)
        for choice, balance in zip(choices, ['32145','79']):
            self.assertEqual(choice['holder'], 'EXAMPLE SERVICES SA DE CV')
            self.assertEqual(choice['account_reference'], '7654321')
            self.assertEqual(choice['period_start'], '2026-05-01')
            rows = propose_monex_statement(sources, choice['currency'], choice)['rows']
            self.assertEqual([r['fields']['balance'] for r in rows if r['kind']=='balance'],[balance,balance])
            self.assertTrue(all(r['excluded'] and not r['issues'] for r in rows))
            self.assertEqual(check_statement_rows(rows)['balance_status'],'matches')
            self.assertEqual(len(rows),sum(len(s['rows']) for s in sources))
        self.assertEqual(sources,before)

    def test_missing_pages_nonzero_activity_conflicts_and_unknown_pages_prevent_zero_shortcut(self):
        variants = []
        s=statement();s.pop();variants.append(s)
        s=statement();s[1]['rows'][4]['cells'][-1]['expected_text']='12.00';variants.append(s)
        s=statement();s[1]['rows'][6]['cells'][-1]['expected_text']='310.45';variants.append(s)
        s=statement();s[1]['rows'][4]['cells'][-1]['expected_text']='?';variants.append(s)
        s=statement();s[3]['rows'][1]['cells'][0]['expected_text']='Detalle de movimientos';variants.append(s)
        s=statement();s[4]['rows'][0]['cells'][-1]['expected_text']='CONTRATO: 9999999';variants.append(s)
        s=statement();s[2]['rows'][2]['cells'][0]['expected_text']='Currency not readable';variants.append(s)
        for i,s in enumerate(variants):
            with self.subTest(i=i):self.assertEqual(monex_catalog(s),([],set()))

    def test_other_statements_in_same_pdf_do_not_supply_missing_monex_pages(self):
        s=statement();s[2]['rows'][0]['cells'][0]['expected_text']='Another Bank'
        self.assertEqual(monex_catalog(s),([],set()))

    def test_owner_identifier_is_the_explicit_holder_field_not_a_bank_or_routing_identifier(self):
        from services.financial.account_ownership import holder_identifiers
        s=statement()
        s[3]['rows'].extend(source(4,[[(20000,200000,100000,'RFC TITULAR:'),(200000,200000,120000,'BNK010101AB1')]])['rows'])
        found=holder_identifiers(s,account_reference='7654321',holder='EXAMPLE SERVICES SA DE CV')
        self.assertEqual({v['value'] for v in found},{'EXA010101AB1'})
        self.assertTrue(all(v['page_number']==1 and v['locator'] for v in found))
        self.assertEqual(holder_identifiers(s,account_reference='7654321',holder='Different company'),[])


class MonexImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        from tests.test_financial_statement_import_scotiabank import ScotiabankImportTests
        ScotiabankImportTests.prepare(self,statement())

    def tearDown(self):self.f.tearDown()

    def preview(self, statement_id=None):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,statement_id=statement_id)

    def test_select_import_both_currencies_retry_and_reopen_without_duplicate_payments(self):
        from services.financial.import_batches import initial_request
        from services.financial.statement_details import read_statement_details
        from services.financial.imported_records import imported_records
        receipts=[]
        choices=self.preview()['statement_choices']
        self.assertEqual(len(choices),2)
        for choice,balance in zip(choices,['32145','79']):
            proposal=self.preview(choice['id'])
            self.assertEqual(proposal['transaction_count'],0)
            self.assertEqual(proposal['needs_attention'],0)
            self.assertTrue(proposal['can_import_balances'])
            self.assertEqual(proposal['metadata']['holder'],'EXAMPLE SERVICES SA DE CV')
            request=initial_request(proposal)
            receipt=self.f.confirm(request);receipts.append(receipt)
            self.assertEqual((receipt['transaction_count'],receipt['incomplete_count']),(0,0))
            self.assertFalse(self.f.confirm(request)['created'])
            self.assertEqual(self.preview(choice['id'])['current_import']['source_document_id'],receipt['source_document_id'])
            with self.f.SessionLocal() as db:
                details=read_statement_details(db,case_id=self.f.case.id,source_id=UUID(receipt['source_document_id']))
                self.assertEqual(details['currency'],choice['currency'])
                self.assertEqual(details['balances']['opening']['amount_minor'],balance)
                self.assertEqual(details['balances']['closing']['amount_minor'],balance)
                self.assertEqual(details['details']['period_end'],'2026-05-31')
                self.assertEqual(imported_records(db,case_id=self.f.case.id,account_id=None,start_date=None,end_date=None)['total'],0)
        self.assertNotEqual(receipts[0]['account_id'],receipts[1]['account_id'])

    def test_editing_one_currency_section_retains_the_other_section_and_source(self):
        from services.financial.import_batches import initial_request
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        from postgres.models.financial import FinancialAccount
        choices=self.preview()['statement_choices']
        receipts=[self.f.confirm(initial_request(self.preview(c['id']))) for c in choices]
        with self.f.SessionLocal() as db:
            first,second=[read_statement_details(db,case_id=self.f.case.id,source_id=UUID(r['source_document_id'])) for r in receipts]
            after=update_statement_details(db,case_id=self.f.case.id,source_id=UUID(receipts[1]['source_document_id']),actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=second['revision'], holder=second['details']['holder'],
                    institution=second['details']['institution'],account_number=second['details']['account_number'],currency='GBP'))
            self.assertEqual(after['currency'],'GBP')
            self.assertEqual(after['balances']['opening']['amount_minor'],'79')
            self.assertEqual(db.get(FinancialAccount,UUID(after['account_id'])).currency,'GBP')
            untouched=read_statement_details(db,case_id=self.f.case.id,source_id=UUID(receipts[0]['source_document_id']))
            self.assertEqual(untouched,first)
            self.assertEqual(after['evidence_file_id'],first['evidence_file_id'])
