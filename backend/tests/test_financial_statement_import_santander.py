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


def multipage_statement():
    """Two accounts share a page; following pages repeat only the columns."""
    base = statement()[0]['rows']
    def cells(index, y):
        return [(c['locator']['rect'][0], y,
                 c['locator']['rect'][2]-c['locator']['rect'][0], c['expected_text'])
                for c in base[index]['cells']]
    context = lambda: [cells(i, 20000+i*20000) for i in range(4)]
    payment = lambda y, day, ref, direction, amount, balance: [
        (30000, y, 270000, f'{day}-SEP-2024/{ref} EXAMPLE PAYMENT'),
        (380000 if direction == 'credit' else 445000,y,40000,amount),
        (510000,y,40000,balance)]
    return [source(1, context()+[cells(i,120000+(i-4)*20000) for i in range(4,9)]),
        source(2, context()+[cells(7,120000), cells(9,150000), cells(10,180000),
            cells(11,210000), cells(12,260000), cells(13,290000), cells(14,320000),
            cells(15,350000), payment(380000,'04','0000003','credit','40.00','40.00')]),
        source(3, context()+[cells(15,120000),
            payment(150000,'05','0000004','debit','10.00','30.00'),
            [(120000,180000,80000,'TOTAL'),(380000,180000,40000,'40.00'),(445000,180000,40000,'10.00')],
            [(30000,210000,260000,'SALDO FINAL DEL PERIODO:'),(510000,210000,40000,'$30.00')]])]


class SantanderTests(TestCase):
    def test_continuation_pages_keep_account_scope_across_shared_page(self):
        ss = multipage_statement(); before = deepcopy(ss)
        choices, handled = santander_catalog(ss)
        self.assertEqual(len(choices), 2)
        self.assertEqual([c['page_numbers'] for c in choices], [[1,2], [1,2,3]])
        self.assertEqual(handled, {(1,0),(2,0),(3,0)})
        for choice, amounts in zip(choices, [['2500','5000'], ['4000','1000']]):
            rows = propose_santander_statement(ss, 'MXN', choice)['rows']
            payments = [r for r in rows if not r['excluded']]
            self.assertEqual([r['fields']['amount_minor'] for r in payments], amounts)
            self.assertEqual(check_statement_rows(rows)['balance_status'], 'matches')
            self.assertEqual(check_statement_rows(rows)['flagged_rows'], 0)
        self.assertEqual(ss, before)

    def test_continuation_never_bridges_missing_conflicting_or_closed_section(self):
        for kind in ('gap','customer','period','brand','closed','columns'):
            with self.subTest(kind=kind):
                ss = multipage_statement()
                if kind == 'gap':
                    ss[2]['page_number'] = 4
                elif kind in ('customer','period','brand'):
                    old,new = {'customer':('12345678','87654321'),
                        'period':('SEP','OCT'), 'brand':('Santander','Other Bank')}[kind]
                    for row in ss[2]['rows']:
                        for cell in row['cells']:
                            cell['expected_text'] = cell['expected_text'].replace(old,new)
                elif kind == 'closed':
                    ss[1]['rows'].append(source(2,[[(30000,420000,260000,'SALDO FINAL DEL PERIODO:'),
                        (510000,420000,40000,'$40.00')]])['rows'][0] | {'row_index':99})
                else:
                    ss[2]['rows'] = [row for row in ss[2]['rows'] if row['row_index'] != 4]
                choices,handled = santander_catalog(ss)
                investment = next(c for c in choices if c['account_type']=='savings')
                self.assertEqual(investment['page_numbers'], [1,2])
                self.assertNotIn((ss[2]['page_number'],0), handled)
                rows=propose_santander_statement(ss,'MXN',investment)['rows']
                self.assertEqual(sum(not r['excluded'] for r in rows),1)

    def test_unreadable_columns_and_money_remain_incomplete_not_quiet(self):
        ss=statement()
        ss[0]['rows'][7]['cells'][3]['expected_text']='UNREADABLE'
        choice=santander_catalog(ss)[0][0]
        rows=propose_santander_statement(ss,'MXN',choice)['rows']
        self.assertEqual(sum(not r['excluded'] for r in rows),2)
        self.assertTrue(all(r['kind']=='unresolved' and r['issues'] for r in rows if not r['excluded']))
        from services.financial.statement_import import StatementImportRequest
        from services.financial.statement_admission import assess_admission
        proposal=dict(rows=rows,revision='a'*64,metadata={'balance_convention':'asset_balance'})
        request=StatementImportRequest(expected_revision='a'*64, currency='MXN',
            account_number='EXAMPLE123',holder='EXAMPLE SERVICES',institution='Santander',
            period_start='2024-09-01',period_end='2024-09-30',rows=[dict(
                id=r['id'],excluded=r['excluded'],description=r['fields'].get('description',''),
                date=r['fields'].get('date',''),direction=r['fields'].get('direction'),
                amount_minor=r['fields'].get('amount_minor',''),balance_minor=r['fields'].get('balance'))
                for r in rows])
        admission=assess_admission(proposal,request)
        self.assertFalse(admission['can_import'])
        self.assertFalse(admission['no_activity_confirmed'])
        self.assertEqual(admission['status'],'needs_review')
        self.assertTrue(any(b['kind']=='missing_field' for b in admission['blockers']))
        ss=statement()
        ss[0]['rows'][8]['cells'][3]['expected_text']='2.5,0.00'
        rows=propose_santander_statement(ss,'MXN',santander_catalog(ss)[0][0])['rows']
        payment=next(r for r in rows if not r['excluded'])
        self.assertEqual(payment['fields']['direction'],'credit')
        self.assertNotIn('amount_minor',payment['fields'])
        self.assertTrue(payment['issues'])
        self.assertEqual(payment['source_cells'][3]['expected_text'],'2.5,0.00')

    def test_footer_numbers_and_interest_rates_are_not_extra_payments(self):
        ss=multipage_statement()
        ss[2]['rows'].extend([r | {'row_index':100+i} for i,r in enumerate(source(3,[
            [(390000,165000,60000,'TASA 3.01250')],
            [(530000,760000,50000,'123456')]])['rows'])])
        choices,_=santander_catalog(ss)
        rows=propose_santander_statement(ss,'MXN',choices[1])['rows']
        self.assertEqual(sum(not r['excluded'] for r in rows),2)

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


class SantanderSavedReviewTests(TestCase):
    def test_new_continuations_require_comparison_and_keep_manual_addition(self):
        from unittest.mock import patch
        from sqlalchemy import select
        from postgres.models.evidence import EvidenceTableGeometry, EvidenceFile, EvidenceDocumentText
        from postgres.models.financial import FinancialTransaction
        from services.financial.statement_import import read_statement_import, StatementReviewDraft, StatementImportRequest, check_import_request
        from services.financial.import_batches import initial_request
        from services.financial.statement_progress import save_progress
        from services.financial.pdf_candidates import PdfMappingError
        from tests.test_financial_statement_import import StatementImportTests
        f=StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        f.setUp()
        try:
            ss=multipage_statement()
            document=f.db.get(EvidenceDocumentText,f.file.id)
            document.source_locations=[dict(kind='page',page_number=p,start_char=0,
                end_char=document.character_count,text_origin='ocr') for p in (1,2,3)]
            for geometry in list(f.db.scalars(select(EvidenceTableGeometry))):f.db.delete(geometry)
            f.db.flush()
            for s in ss:
                f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id,page_number=s['page_number'],
                    engine_job_id=document.engine_job_id,
                    payload=[dict(table_source='drawn_geometry',geometry_source='cell_rectangles',table=dict(
                        page=s['page_number'],table=dict(kind='page_rectangle',page=s['page_number'],
                            rect=[0,0,612000,792000],page_size=[612000,792000],units='millipoints',space='pdf_displayed'),
                        unlocated_values=0,values=[dict(row=r['row_index'],column=c['column_index'],
                            text=c['expected_text'],locator=c['locator']) for r in s['rows'] for c in r['cells']]))]))
            f.db.commit()
            real_catalog=santander_catalog
            def legacy(sources):
                choices,handled=real_catalog(sources)
                choice=next(c for c in choices if c['account_type']=='checking')
                choice['sources']=[s for s in choice['sources'] if s['page_number']==1]
                choice['section_sources']=[s for s in choice['section_sources'] if s['page_number']==1]
                choice['page_numbers']=[1]
                return choices,handled
            with patch('services.financial.statement_import_santander.santander_catalog',side_effect=legacy):
                catalog=read_statement_import(f.db,case_id=f.case.id,evidence_file_id=f.file.id)
                selected=next(c for c in catalog['statement_choices'] if c['account_type']=='checking')['id']
                old=read_statement_import(f.db,case_id=f.case.id,evidence_file_id=f.file.id,statement_id=selected)
                self.assertEqual(old['transaction_count'],1)
                raw=initial_request(old)
                raw['rows'].append(dict(id='manual:synthetic-missed-payment',manual_page=2,excluded=False,
                    date='2024-09-03',description='INVESTIGATOR SAVED PAYMENT',amount_minor='5000',
                    direction='debit',balance_minor='7500',reason='Checked against source'))
                saved=save_progress(f.db,case_id=f.case.id,evidence_file_id=f.file.id,
                    request=StatementReviewDraft.model_validate(raw),expected_review_revision='initial',actor=f.actor)
            fresh=read_statement_import(f.db,case_id=f.case.id,evidence_file_id=f.file.id,statement_id=selected)
            self.assertEqual(fresh['transaction_count'],2)
            self.assertNotEqual(fresh['revision'],old['revision'])
            self.assertEqual(fresh['saved_review']['request'],saved['request'])
            self.assertEqual(fresh['saved_review']['request']['rows'][-1]['id'],'manual:synthetic-missed-payment')
            with self.assertRaisesRegex(PdfMappingError,'older reading'):
                check_import_request(fresh,StatementImportRequest.model_validate(initial_request(fresh)))
            f.db.expire_all()
            self.assertEqual(f.db.get(EvidenceFile,f.file.id).metadata_['financial_review_progress'][selected]['request'],saved['request'])
            self.assertFalse(list(f.db.scalars(select(FinancialTransaction))))
        finally:
            f.tearDown()
