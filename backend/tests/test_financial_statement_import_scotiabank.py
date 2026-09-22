"""Synthetic source geometry for a complete Scotiabank no-activity statement."""
import hashlib
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select
from services.financial.statement_import_scotiabank import scotiabank_catalog, propose_scotiabank_statement
from services.financial.statement_currency import detect_statement_currency


def source(page, rows):
    return dict(page_number=page, table_index=0, source_revision='a' * 64, table_source='text_alignment',
        rows=[dict(row_index=i, cells=[dict(column_index=j, expected_text=t,
            locator=dict(kind='page_rectangle', page=page, rect=[x, y, x+w, y+6000],
                page_size=[612000, 792000], units='millipoints', space='pdf_displayed'))
            for j, (x, y, w, t) in enumerate(cells)]) for i, cells in enumerate(rows)])


def statement():
    rows = [
        [(100000,10000,100000,'PAGINA 1 DE 3')],
        [(390000,30000,150000,'Scotiabank')],
        [(380000,55000,70000,'Estado de Cuenta'),(460000,55000,100000,'SCOTIA INV DISP PM +')],
        [(40000,70000,190000,'e2) EXAMPLE HOLDINGS SA DE CV')],
        [(400000,80000,50000,'Cuenta'),(470000,80000,80000,'00001234567')],
        [(400000,100000,50000,'Periodo'),(470000,100000,120000,'19-ENE-26/30-ENE-26')],
        [(400000,120000,50000,'Moneda'),(470000,120000,80000,'NACIONAL')],
        [(90000,260000,100000,'Resumen de Saldos')],
        [(240000,250000,190000,'Comportamiento de transacciones en tu cuenta')],
        [(390000,275000,63000,'Saldo — inicial = $0.00'),(465000,275000,100000,'Saldo final= - $0.00')],
        [(50000,290000,100000,'Saldo inicial')],
        [(50000,310000,100000,'(+) Depésitos')],
        [(50000,330000,160000,'(+) Intereses recibidos (Tasa 0.00%)')],
        [(50000,350000,100000,'(-) Retiros')],
        [(50000,365000,100000,'(-) Comisiones cobradas')],
        [(50000,380000,100000,'(-) Impuestos')],
        [(50000,397000,130000,'(=) Saldo final de la cuenta'),(215000,397000,18000,'$0.00')]
            + [(x,397000,14000,'$0.00') for x in (340000,390000,440000,490000,540000)],
        [(330000,424000,35000,'Depésitos _.'),(378000,424000,32000,'Intereses'),
         (414000,424000,57000,'Retiros . en efectivo .'),(478000,424000,42000,'Otros cargos*'),
         (528000,424000,42000,'Comisiones .')],
        [(40000,455000,130000,'Sdo. Prom. Min. requerido en cuenta'),(198000,455000,35000,'$10,000.00')],
        [(40000,550000,540000,'A PARTIR DEL 01-02-26 LA COMISION SERA $14.66 MAS IVA.')],
    ]
    return [source(1, rows), source(2, [
        [(100000,10000,100000,'PAGINA 2 DE 3'),(260000,10000,150000,'Cuenta 00001234567')],
        [(40000,130000,540000,'LOS SIGUIENTES DATOS SON INFORMATIVOS')],
        [(40000,180000,200000,'Total de comisiones cobradas en el Periodo:'),(270000,180000,50000,'$0.00')],
        [(40000,340000,100000,'Advertencias')],
    ]), source(3, [
        [(100000,10000,100000,'PAGINA 3 DE 3'),(260000,10000,150000,'Cuenta 00001234567')],
        [(40000,150000,100000,'ABREVIATURAS:')],
        [(40000,180000,190000,'USD-DOLAR ESTADOUNIDENSE')],
        [(40000,210000,220000,'TRANSFERENCIAS ELECTRONICAS')],
        [(40000,620000,200000,'SCOTIABANK INVERLAT, S.A.')],
    ])]


class ScotiabankProposalTests(TestCase):
    def test_balance_summary_chart_and_glossary_are_not_payments(self):
        sources = statement(); before = deepcopy(sources)
        choices, handled = scotiabank_catalog(sources)
        self.assertEqual(len(choices), 1)
        choice = choices[0]
        self.assertEqual(choice['holder'], 'EXAMPLE HOLDINGS SA DE CV')
        self.assertEqual(choice['account_reference'], '00001234567')
        self.assertEqual((choice['period_start'],choice['period_end']),('2026-01-19','2026-01-30'))
        self.assertEqual(detect_statement_currency(sources,layout_id=choice['layout_id']), 'MXN')
        proposal = propose_scotiabank_statement(sources,'MXN',choice)
        self.assertTrue(all(row['excluded'] and not row['issues'] for row in proposal['rows']))
        controls = [r for r in proposal['rows'] if r['kind'] == 'balance']
        self.assertEqual([r['fields']['balance'] for r in controls],['0','0'])
        self.assertEqual(len({r['id'] for r in proposal['rows']}), len(proposal['rows']))
        self.assertEqual({(r['page_number'],r['row_index']) for r in proposal['rows']},
            {(s['page_number'],r['row_index']) for s in sources for r in s['rows']})
        self.assertEqual(handled,{(1,0),(2,0),(3,0)})
        self.assertEqual(sources,before)

    def test_nonzero_unchanged_balances_are_retained(self):
        sources=statement()
        for cell in sources[0]['rows'][9]['cells']:
            cell['expected_text']=cell['expected_text'].replace('- $0.00','$123.45').replace('$0.00','$123.45')
        sources[0]['rows'][16]['cells'][1]['expected_text']='$123.45'
        choices,_=scotiabank_catalog(sources)
        rows=propose_scotiabank_statement(sources,'MXN',choices[0])['rows']
        self.assertEqual([r['fields']['balance'] for r in rows if r['kind']=='balance'],['12345','12345'])

    def test_incomplete_or_conflicting_evidence_never_suppresses_rows(self):
        variants=[]
        s=statement(); s.pop(); variants.append(s)
        s=statement(); s[1]['rows'][0]['cells'][-1]['expected_text']='Cuenta 00009999999'; variants.append(s)
        s=statement(); s[0]['rows'][16]['cells'][-1]['expected_text']='$12.34'; variants.append(s)
        s=statement(); s[0]['rows'][16]['cells'].pop(); variants.append(s)
        s=statement(); s[0]['rows'][9]['cells'][-1]['expected_text']='Saldo final= $123.45'; variants.append(s)
        s=statement(); s[0]['rows'][6]['cells'][-1]['expected_text']='DOLARES'; variants.append(s)
        s=statement(); s[1]['rows']+=source(2,[[(40000,400000,300000,'Fecha Descripcion Retiros Depositos Saldo')]])['rows']; variants.append(s)
        s=statement(); s[1]['rows']+=source(2,[[(40000,400000,300000,'20-ENE-26 TRANSFERENCIA 123.45')]])['rows']; variants.append(s)
        s=statement(); s[0]['rows'][13]['cells'].append(source(1,[[(210000,350000,30000,'$12.34')]])['rows'][0]['cells'][0]); variants.append(s)
        s=statement(); s[0]['rows'][16]['cells'][1]['expected_text']='$12.34'; variants.append(s)
        s=statement(); s[0]['rows'][13]['cells'].append(source(1,[[(210000,350000,30000,'$1..2')]])['rows'][0]['cells'][0]); variants.append(s)
        s=statement(); s[1]['rows']+=source(2,[[(40000,400000,300000,'20-ENE-26 TRANSFERENCIA I23.45 MXN')]])['rows']; variants.append(s)
        for i,sources in enumerate(variants):
            with self.subTest(i=i): self.assertEqual(scotiabank_catalog(sources),([],set()),str(i))

    def test_currency_mismatch_is_a_review_issue_not_an_exception(self):
        sources=statement(); choices,_=scotiabank_catalog(sources)
        rows=propose_scotiabank_statement(sources,'EUR',choices[0])['rows']
        self.assertTrue(all(r['issues'] and 'balance' not in r['fields'] for r in rows if r['kind']=='balance'))


class ScotiabankImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f=StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.prepare(statement())

    def tearDown(self): self.f.tearDown()

    def prepare(self,sources):
        from postgres.models.evidence import EvidenceDocumentText,EvidenceTableGeometry
        f=self.f
        for old in list(f.db.scalars(select(EvidenceTableGeometry))): f.db.delete(old)
        f.db.flush()
        text=f.db.get(EvidenceDocumentText,f.file.id)
        text.content='\n'.join(' '.join(c['expected_text'] for c in r['cells']) for s in sources for r in s['rows'])
        text.content_sha256=hashlib.sha256(text.content.encode()).hexdigest()
        text.character_count=len(text.content)
        for s in sources:
            page=s['page_number']
            f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id,page_number=page,engine_job_id=text.engine_job_id,
                payload=[dict(table_source='text_alignment',geometry_source='cell_rectangles',table=dict(page=page,
                    table=dict(kind='page_rectangle',page=page,rect=[0,0,612000,792000],page_size=[612000,792000],units='millipoints',space='pdf_displayed'),
                    unlocated_values=0,values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator=c['locator']) for r in s['rows'] for c in r['cells']]))]))
        f.db.commit()

    def preview(self):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db,case_id=self.f.case.id,evidence_file_id=self.f.file.id,currency='MXN')

    def test_fresh_import_reopen_keeps_zero_balances_period_and_no_missing_records(self):
        from services.financial.import_batches import initial_request
        from services.financial.imported_records import imported_records
        from services.financial.statement_details import read_statement_details
        proposal=self.preview()
        self.assertEqual(proposal['transaction_count'],0)
        self.assertEqual(proposal['needs_attention'],0)
        self.assertTrue(proposal['can_import_balances'])
        request=initial_request(proposal)
        receipt=self.f.confirm(request)
        self.assertEqual((receipt['transaction_count'],receipt['incomplete_count']),(0,0))
        self.assertFalse(self.f.confirm(request)['created'])
        self.assertEqual(self.preview()['current_import']['incomplete_count'],0)
        with self.f.SessionLocal() as db:
            details=read_statement_details(db,case_id=self.f.case.id,source_id=UUID(receipt['source_document_id']))
            self.assertEqual(details['details']['period_start'],'2026-01-19')
            self.assertEqual(details['balances']['opening']['amount_minor'],'0')
            self.assertEqual(details['balances']['closing']['amount_minor'],'0')
            self.assertEqual(imported_records(db,case_id=self.f.case.id,account_id=None,start_date=None,end_date=None)['total'],0)

    def test_old_false_records_refresh_preserves_history_and_manual_account_details(self):
        from services.financial.import_batches import initial_request
        from services.financial.legacy_statement_refresh import refresh_legacy_import
        from services.financial.imported_records import imported_records
        from postgres.models.financial import FinancialSourceDocument
        with patch('services.financial.statement_import_scotiabank.scotiabank_catalog',return_value=([],set())):
            raw=initial_request(self.preview())
            raw.update(holder='Investigator corrected holder',account_number='00001234567')
            for row in raw['rows']: row['excluded']=False
            old=self.f.confirm(raw)
        self.assertGreater(old['incomplete_count'],20)
        p=self.preview()
        self.assertTrue(p['current_import']['refresh_available'])
        kwargs=dict(session_factory=self.f.SessionLocal,case_id=self.f.case.id,source_id=UUID(old['source_document_id']),
            expected_revision=p['current_import']['revision'],expected_reading_revision=p['revision'],actor=self.f.actor,resolve_path=Path)
        receipt=refresh_legacy_import(**kwargs)
        self.assertEqual((receipt['transaction_count'],receipt['incomplete_count']),(0,0))
        self.assertFalse(refresh_legacy_import(**kwargs)['created'])
        p=self.preview()
        self.assertEqual(p['current_import']['details']['holder'],'Investigator corrected holder')
        with self.f.SessionLocal() as db:
            history=db.get(FinancialSourceDocument,UUID(old['source_document_id']))
            self.assertEqual(history.status,'superseded')
            self.assertEqual(len(history.metadata_['statement_incomplete_records']),old['incomplete_count'])
            self.assertEqual(imported_records(db,case_id=self.f.case.id,account_id=None,start_date=None,end_date=None)['total'],0)

    def test_a_saved_row_correction_blocks_automatic_replacement(self):
        from services.financial.import_batches import initial_request
        from postgres.models.financial import FinancialSourceDocument
        with patch('services.financial.statement_import_scotiabank.scotiabank_catalog',return_value=([],set())):
            raw=initial_request(self.preview())
            for row in raw['rows']: row['excluded']=False
            old=self.f.confirm(raw)
        with self.f.SessionLocal() as db:
            doc=db.get(FinancialSourceDocument,UUID(old['source_document_id']))
            meta=deepcopy(doc.metadata_)
            meta['statement_incomplete_records'][0]['correction']={'description':'Saved review'}
            doc.metadata_=meta; db.commit()
        self.assertFalse(self.preview()['current_import']['refresh_available'])
