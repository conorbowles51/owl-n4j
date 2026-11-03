"""Brokerage statements in the ledger (lx-brokerage B, C, D): trades and holdings with instrument and quantity.

Formats measured on the live collection (3 Nov 2026): the casa de bolsa movement table (Intercam, 22 statements with
a text layer, every movement line one stored cell; Kapital, 4 scanned statements, one stored cell per column with
OCR slips) and the position tables of the same statements. Every line below is synthetic in that layout.

The parser tests fail on the old code (no ``brokerage_reading``); the ledger tests fail on the old code (no
``financial_security_rows``, no ``sync_document``) and prove the cash rows are never written.
"""
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_securities import FinancialSecurityRow
from services.financial import brokerage_reading as R
from tests.test_financial_duplicates import DuplicateTestCase

# One stored cell holding the whole printed line (the text-layer statements).
INTERCAM_REPO_START = ('17) 17) 27500001) )Compra de Reporto BONDESD 251016 0 100,009) 99.99014363) 1) 10.250000) '
                       '(9,999,914.27) 0.00) 0.00) 0.00) (9,999,914.27)')
INTERCAM_REPO_MATURITY = ('31) 01) 18500002) )Compra de Reporto BPAG91 270506 0 10,153) 101.40656389) 1) 8.000000) '
                          '1,029,580.84) 0.00) 228.80) 14.10) 1,029,795.54)')
INTERCAM_FUND_BUY = ('01) 01) 38500003) )Compra Fondos Inv +TASA M1 0 380,834) 1.39135500) 0) 0.000000) '
                     '(529,875.29) 0.00) 0.00) 0.00) (529,875.29)')
INTERCAM_WITHDRAWAL = ('01) 01) 2600004) )Retiro 0 0) 1.00000000) 0) 0.000000) 500,000.00) 0.00) 0.00) 0.00) '
                       '(500,000.00)')
# One stored cell per column, as the scanned statements are read, with the two OCR slips measured on them.
KAPITAL_SCANNED = ['22 23.', '809110001', 'Comprade Reporto CFE', '07126', '0', '7,155', '98.81522561', '1',
                   '6.000000', '707 ,022.94', '0.00', '117.84', '17.43', '707,123.35?']


def cells(*texts):
    return [dict(column_index=i, expected_text=t) for i, t in enumerate(texts)]


class BrokerageReadingTests(DuplicateTestCase):
    """C: one test per format found on live."""

    def test_text_layer_line_reads_instrument_quantity_price_dates_and_money_columns(self):
        t = R.trade_from_cash_row(cells=cells(INTERCAM_REPO_MATURITY), description='', settlement=date(2025, 4, 1),
                                  amount_minor=102979554, direction='credit')
        assert (t['instrument'], t['issuer'], t['series']) == ('BPAG91 270506', 'BPAG91', '270506')
        assert (t['quantity'], t['price']) == (Decimal('10153'), Decimal('101.40656389'))
        # The operation day (31) falls in the month before the settlement day (1 April).
        assert (t['trade_date'], t['settlement_date']) == (date(2025, 3, 31), date(2025, 4, 1))
        assert (t['gross_minor'], t['premium_minor'], t['tax_minor'], t['net_minor']) == (102958084, 22880, 1410,
                                                                                          102979554)
        assert t['checks'] == {'net_equals_cash_leg': True, 'gross_premium_less_tax_and_commission_equals_net': True}
        assert t['execution_time'] is None and 'execution_time' in t['not_printed'] and t['not_read'] == []

    def test_repo_leg_and_fund_buy_are_named_and_a_cash_line_moves_no_security(self):
        start = R.trade_from_cash_row(cells=cells(INTERCAM_REPO_START),
                                      description='27500001 Compra de Reporto BONDESD 251016 0 100,009 Inicio',
                                      settlement=date(2025, 1, 17), amount_minor=999991427, direction='debit')
        assert start['side'] == 'repo_start' and start['operation'] == 'Compra de Reporto Inicio'
        fund = R.trade_from_cash_row(cells=cells(INTERCAM_FUND_BUY), description='', settlement=date(2025, 4, 1),
                                     amount_minor=52987529, direction='debit')
        assert (fund['side'], fund['instrument'], fund['quantity_printed']) == ('buy', '+TASA M1', '380,834')
        assert R.trade_from_cash_row(cells=cells(INTERCAM_WITHDRAWAL), description='', settlement=date(2025, 4, 1),
                                     amount_minor=50000000, direction='debit') is None

    def test_scanned_columns_with_split_days_and_split_amount_read_as_printed(self):
        t = R.trade_from_cash_row(cells=cells(*KAPITAL_SCANNED),
                                  description='809110001 Comprade Reporto CFE 07126 0 7,155 98.81522561 1 6.000000 Venc',
                                  settlement=date(2026, 7, 23), amount_minor=70712335, direction='credit')
        assert t['basis'] == 'printed_line' and t['side'] == 'repo_maturity'
        assert (t['trade_date'], t['settlement_date']) == (date(2026, 7, 22), date(2026, 7, 23))
        assert (t['gross_minor'], t['net_minor']) == (70702294, 70712335)
        assert t['checks']['gross_premium_less_tax_and_commission_equals_net'] is True

    def test_a_reading_that_kept_only_a_note_keeps_the_instrument_and_says_what_it_did_not_read(self):
        t = R.trade_from_cash_row(cells=[], description='27077898 Compra de Reporto I BONDESD 231221 (ope 05, liq 05; '
                                  'NETO (8,165,571.60)', settlement=date(2023, 12, 5), amount_minor=816557160,
                                  direction='debit')
        assert t['instrument'] == 'BONDESD 231221' and t['quantity'] is None
        assert {'quantity', 'price'} <= set(t['not_read']) and t['trade_date'] == date(2023, 12, 5)
        assert R.trade_from_cash_row(cells=[], description='28100001 Cobro por Timbrado (ope 30, liq 30; NETO (0.01)',
                                     settlement=date(2023, 12, 30), amount_minor=1, direction='debit') is None

    def test_holdings_read_only_lines_that_prove_their_own_valuation(self):
        sources = [dict(page_number=2, table_index=0, rows=[
            dict(row_index=0, cells=cells('POSICION AL 31 DE MARZO DE 2025', 'POSICION AL 30 DE ABRIL DE 2025')),
            dict(row_index=1, cells=cells('EMISORA SERIE CUP MON', 'CANTIDAD PRECIO')),
            dict(row_index=2, cells=cells('+TASA M1 0) MXN)', '0) 0.0000000)', '0.00)',
                                          '63,246) 1.3981020) 0.00000)0.00 0.0000)', '88,424.36)', '0) 0) 0.0)')),
            dict(row_index=3, cells=cells('+TASA M2 0) MXN)', '0) 0.0000000)', '0.00)',
                                          '63,246) 1.3981020) 0.00000)', '99,999.99)')),
            dict(row_index=4, cells=cells('REPORTOS VIGENTES AL 31 DE MARZO DE 2025')),
            dict(row_index=5, cells=cells('8500002 2025/03/31 2025/04/01 1 8.0000000) BPAG91 270506 '
                                          '1,029,580.84) 0 0.00) 1 228.80) 1,029,580.84)')),
        ])]
        found = R.holdings_from_tables(sources)
        assert [(h['holding_kind'], h['instrument']) for h in found] == [('security', '+TASA M1'),
                                                                       ('repo', 'BPAG91 270506')]
        security, repo = found
        assert (security['quantity'], security['market_value_minor'], security['as_of']) == (
            Decimal('63246'), 8842436, date(2025, 4, 30))
        assert (repo['market_value_minor'], repo['settlement_date'], repo['as_of']) == (
            102958084, date(2025, 4, 1), date(2025, 3, 31))


def _rows_digest(db):
    rows = db.query(FinancialTransaction).order_by(FinancialTransaction.id).all()
    return hashlib.sha256(json.dumps([[str(r.id), r.amount_minor, r.direction, str(r.transaction_date), r.description,
                                       r.ledger_status, r.provenance, r.metadata_, str(r.updated_at)] for r in rows],
                                     sort_keys=True, default=str).encode()).hexdigest()


class BrokerageLedgerTests(DuplicateTestCase):
    """B and D: the security rows follow the cash rows, never write them, and keep corrections and origin."""

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[FinancialSecurityRow.__table__])
        self.account.institution_name = 'Intercam Casa de Bolsa'
        self.doc = self.make_document()
        self.doc.proof_class = 'p3'
        self.period = self.make_period(self.doc)
        self.db.commit()

    def cash(self, line, *, amount, direction, day, description='', key='3:1:1', origin=None):
        from postgres.models.enums import TransactionDirection
        row = self.add_row(self.period, self.doc, amount=amount, direction=TransactionDirection(direction))
        row.transaction_date = row.ordering_date = day
        row.description = description or line
        row.proof_class = 'p3'
        confirmed = dict(name='Investigator', email='investigator@example.test')
        if origin:
            confirmed = dict(name='Claude (for Investigator)', email='investigator@example.test', origin=origin)
        row.provenance = dict(locator=dict(kind='page_rectangle', page=3, rect=[1, 2, 3, 4]), confirmed_by=confirmed,
                              statement_import_original=dict(id=key, page_number=3, table_index=1, row_index=1,
                                                             source_cells=cells(line) if line else []))
        self.db.commit()
        return row

    def sync(self, sources=()):
        from services.financial.brokerage_ledger import sync_document
        with patch('services.financial.brokerage_ledger._page_tables', return_value=list(sources)):
            out = sync_document(self.db, self.doc.id)
        self.db.commit()
        return out

    def admitted(self):
        return self.db.query(FinancialSecurityRow).filter_by(ledger_status='admitted').all()

    def test_trades_are_linked_to_their_cash_leg_with_its_proof_class_and_no_cash_row_is_written(self):
        repo = self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        self.cash(INTERCAM_WITHDRAWAL, amount=50000000, direction='debit', day=date(2025, 4, 1), key='3:1:2')
        before = _rows_digest(self.db)
        out = self.sync()
        assert (out['brokerage'], out['trades'], out['added']) == (True, 1, 1)
        (trade,) = self.admitted()
        assert trade.cash_transaction_id == repo.id and trade.proof_class == 'p3'
        assert trade.provenance['cash_leg']['amount_minor'] == 102979554
        assert trade.provenance['locator']['page'] == 3 and trade.reading_key == 'cash:3:1:1'
        assert _rows_digest(self.db) == before  # 0 cash rows changed
        again = self.sync()
        assert (again['added'], again['unchanged'], again['superseded']) == (0, 1, 0)
        assert _rows_digest(self.db) == before

    def test_a_statement_of_a_bank_is_not_read_for_trades(self):
        self.account.institution_name = 'Intercam'
        self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        assert self.sync()['brokerage'] is False and self.admitted() == []

    def test_a_correction_keeps_the_value_as_read_and_carries_while_the_reading_stands(self):
        from services.financial.brokerage_ledger import correct_row, query_rows
        repo = self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        self.sync()
        (trade,) = self.admitted()
        out = correct_row(self.db, case_id=self.case.id, row_id=trade.id, field='quantity', value='10,154',
                          reason='Printed 10,154 on the page', actor=self.actor)
        assert out['quantity'] == '10154' and out['corrections']['quantity']['read'] == '10153'
        listed = query_rows(self.db, case_id=self.case.id)
        assert listed['total'] == 1 and listed['items'][0]['quantity'] == '10154'
        # The cash leg is corrected through its own path: the trade is re-read, the person's correction carries.
        repo.ledger_status = 'superseded'
        new = self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        hidden = query_rows(self.db, case_id=self.case.id)
        assert hidden['total'] == 0 and hidden['not_shown_cash_leg_not_in_ledger'] == 1
        self.sync()
        (current,) = self.admitted()
        assert current.cash_transaction_id == new.id and current.corrections['quantity']['value'] == '10154'
        assert self.db.query(FinancialSecurityRow).filter_by(ledger_status='superseded').count() == 1

    def test_a_model_reading_is_labelled_until_a_person_confirms_and_a_model_cannot_correct(self):
        from services.financial.brokerage_ledger import (SecurityRowError, confirm_row, correct_row, query_rows)
        from services.financial.model_work import model_actor, model_origin
        origin = model_origin(for_name='Investigator', citation=dict(page=3))
        self.cash('', amount=816557160, direction='debit', day=date(2023, 12, 5), origin=origin,
                  description='27077898 Compra de Reporto I BONDESD 231221 (ope 05, liq 05; NETO (8,165,571.60)')
        self.sync()
        item = query_rows(self.db, case_id=self.case.id)['items'][0]
        assert item['origin']['kind'] == 'model' and item['origin']['text'] == 'Read by Claude · not confirmed'
        model = model_actor(for_name='Investigator', for_email='investigator@example.test')
        for call in (lambda: correct_row(self.db, case_id=self.case.id, row_id=item['id'], field='quantity',
                                         value='1', reason='x', actor=model),
                     lambda: confirm_row(self.db, case_id=self.case.id, row_id=item['id'], reason='', actor=model)):
            try:
                call()
                raise AssertionError('a model wrote a person\'s decision')
            except SecurityRowError as exc:
                assert exc.status_code == 403
        confirm_row(self.db, case_id=self.case.id, row_id=item['id'], reason='Checked page 3', actor=self.actor)
        item = query_rows(self.db, case_id=self.case.id)['items'][0]
        assert item['origin'] == dict(kind='confirmed', text='Confirmed by Investigator')

    def test_another_case_cannot_correct_or_read_the_rows(self):
        from services.financial.brokerage_ledger import SecurityRowError, correct_row, query_rows
        self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        self.sync()
        (trade,) = self.admitted()
        assert query_rows(self.db, case_id=self.other_case.id)['total'] == 0
        try:
            correct_row(self.db, case_id=self.other_case.id, row_id=trade.id, field='quantity', value='1',
                        reason='x', actor=self.actor)
            raise AssertionError('corrected from another case')
        except SecurityRowError as exc:
            assert exc.status_code == 404

    def test_holdings_are_written_from_the_statement_tables(self):
        sources = [dict(page_number=2, table_index=0, rows=[
            dict(row_index=0, cells=cells('POSICION AL 31 DE MARZO DE 2025', 'POSICION AL 30 DE ABRIL DE 2025')),
            dict(row_index=2, cells=cells('+TASA M1 0) MXN)', '0) 0.0000000)', '0.00)',
                                          '63,246) 1.3981020) 0.00000)', '88,424.36)'))])]
        self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        out = self.sync(sources)
        assert (out['trades'], out['holdings']) == (1, 1)
        holding = self.db.query(FinancialSecurityRow).filter_by(row_kind='holding').one()
        assert (holding.instrument, holding.currency, holding.as_of_date) == ('+TASA M1', 'MXN', date(2025, 4, 30))
        assert holding.market_value_minor == 8842436 and holding.provenance['source']['page'] == 2

    def test_get_trades_keeps_the_ledger_tool_contract(self):
        from contextlib import contextmanager
        from services.agent.tools import AgentToolContext, make_agent_tools
        self.cash(INTERCAM_REPO_MATURITY, amount=102979554, direction='credit', day=date(2025, 4, 1))
        self.cash(INTERCAM_FUND_BUY, amount=52987529, direction='debit', day=date(2025, 4, 1), key='3:1:3')
        self.sync()

        @contextmanager
        def session():
            with self.SessionLocal() as s:
                yield s

        def call(case_id, **args):
            ctx = AgentToolContext(case_id=str(case_id), ledger_session_factory=session)
            return {t.name: t for t in make_agent_tools(ctx)}['get_trades'].invoke(args)

        out = call(self.case.id, limit=1)
        data = out['data']
        assert out['status'] == 'success', out
        assert (data['total'], data['returned'], data['next_offset']) == (2, 1, 1) and data['revision']
        item = data['items'][0]
        assert item['citation']['href'].startswith('/cases/%s/financial?view=trades' % self.case.id)
        assert item['citation']['cash_leg_href'].endswith('payment=%s' % item['citation']['cash_leg']['transaction_id'])
        totals = {t['instrument']: t for t in data['totals_by_instrument']}
        assert totals['+TASA M1']['quantity_in'] == '380834' and totals['+TASA M1']['net_paid_minor'] == 52987529
        # Money reaches the agent formatted beside its minor units (a model read centavos as pesos otherwise).
        assert totals['+TASA M1']['net_paid'] == 'GBP 529,875.29' and totals['+TASA M1']['currency_exponent'] == 2
        assert item['net'] == ('GBP 1,029,795.54' if item['net_minor'] == 102979554 else 'GBP 529,875.29')
        assert item['currency_exponent'] == 2
        elsewhere = call(self.case.id, account_id=str(self.other_account.id))
        nowhere = call(self.case.id, account_id=str(uuid.uuid4()))
        assert elsewhere['data']['reason'] == nowhere['data']['reason'] == 'That account is not in this case.'
        assert call(self.other_case.id)['data']['total'] == 0


FUND_TABLES = [dict(page_number=1, table_index=0, rows=[
    dict(row_index=0, cells=cells('ESTADO DE CUENTA FONDOS DE INVERSIÓN')),
    dict(row_index=1, cells=cells('Periodo', 'Del 01/11/2025 Al 28/11/2025')),
    dict(row_index=2, cells=cells('MONEDA NACIONAL')),
    dict(row_index=3, cells=cells('SYNTHFD B-2 00')),
    dict(row_index=4, cells=cells('0 43.259385 0.00 44,090 43.455366 1,915,947.08 1,359,856.81 43.287161 100.00')),
]), dict(page_number=3, table_index=0, rows=[
    dict(row_index=0, cells=cells('Detalle de Movimientos Realizados Fondo: SYNTHFD 00 B-2')),
    dict(row_index=1, cells=cells('03/NOV', '03/NOV', 'RECLASIFICACION', '31,429', '43.259385', '1,359,599.21',
                                  '31,429', '1,359,599.21', '0.00')),
    dict(row_index=2, cells=cells('06/NOV', '06/NOV', 'VENTA', '-11,553', '43.281603', '-500,032.35', '19,876',
                                  '860,265.14', '0.00')),
]), dict(page_number=4, table_index=0, rows=[
    # The table continues on the next page without its heading.
    dict(row_index=0, cells=cells('18/NOV', '18/NOV', 'COMPRA', '44,971', '43.361108', '1,949,992.38', '64,847',
                                  '2,811,857.52', '0.00')),
    dict(row_index=1, cells=cells('19/NOV', '19/NOV', 'VENTA', '-100', '43.000000', '-9,999.99', '64,747',
                                  '2,801,857.53', '0.00')),
])]


class FundStatementTests(DuplicateTestCase):
    """C: the investment-fund statement format (BBVA, 12 statements on live, set aside from the money ledger)."""

    def test_fund_movements_and_positions_read_with_their_own_arithmetic(self):
        out = R.fund_statement_rows(FUND_TABLES)
        assert out['period'] == (date(2025, 11, 1), date(2025, 11, 28))
        trades = out['trades']
        assert [(t['side'], t['instrument'], t['quantity'], t['trade_date']) for t in trades] == [
            ('other', 'SYNTHFD B-2', Decimal('31429'), date(2025, 11, 3)),
            ('sell', 'SYNTHFD B-2', Decimal('11553'), date(2025, 11, 6)),
            ('buy', 'SYNTHFD B-2', Decimal('44971'), date(2025, 11, 18))]
        assert trades[1]['checks'] == {'units_times_price_equals_amount': True, 'units_chain': True}
        assert trades[2]['checks']['units_chain'] is True and trades[2]['currency'] == 'MXN'
        # 100 x 43.000000 is 4,300.00, not the printed 9,999.99: the line is not read, and says so.
        assert out['not_read'] == [dict(page_number=4, printed_text=out['not_read'][0]['printed_text'],
                                        why='units x price != amount')]
        (holding,) = out['holdings']
        assert (holding['instrument'], holding['quantity'], holding['market_value_minor'], holding['as_of']) == (
            'SYNTHFD B-2', Decimal('44090'), 191594708, date(2025, 11, 28))

    def test_only_the_first_copy_of_a_fund_statement_gets_rows(self):
        from postgres.models.evidence import EvidenceFile
        from services.financial import brokerage_ledger as BL
        Base.metadata.create_all(self.engine, tables=[FinancialSecurityRow.__table__])
        doc = self.make_document()
        first = self.db.get(EvidenceFile, doc.evidence_file_id)
        copy = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename='copy.pdf', stored_path='x',
                            sha256=first.sha256, size=1)
        self.db.add(copy)
        self.db.commit()
        from datetime import datetime, timedelta, timezone
        first.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        copy.created_at = first.created_at + timedelta(days=1)
        self.db.commit()
        with patch.object(BL, '_file_tables', return_value=FUND_TABLES), \
                patch.object(BL, '_text_content', return_value=''):
            one = BL.sync_fund_statement(self.db, first.id)
            two = BL.sync_fund_statement(self.db, copy.id)
        self.db.commit()
        assert (one['fund_statement'], one['trades'], one['holdings']) == (True, 3, 1)
        assert (two['copy'], two['trades']) == (True, 0)
        rows = self.db.query(FinancialSecurityRow).filter_by(ledger_status='admitted').all()
        assert {r.evidence_file_id for r in rows} == {first.id}
        assert all(r.proof_class == 'p3' and r.source_document_id is None for r in rows)

