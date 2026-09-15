import inspect
import unittest
from unittest.mock import patch
from routers import financial
from fastapi import HTTPException


class ReportFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_amount_bounds_match_the_table_and_are_written_in_the_report(self):
        kwargs = {name: value.default.default for name, value in inspect.signature(financial.export_financial_pdf).parameters.items()}
        kwargs.update(case_id='case-a', case_name='Case Ω', mode='intelligence', include_entity_notes=False, min_amount=100, max_amount=200)
        records = [dict(key='low', amount=99), dict(key='negative', amount=-150), dict(key='edge', amount=200), dict(key='high', amount=201)]
        with patch.object(financial.neo4j_service, 'get_financial_transactions', return_value=dict(transactions=records)), patch.object(financial, 'render_financial_export', return_value=dict(content=b'PDF', media_type='application/pdf', extension='pdf')) as render:
            response = await financial.export_financial_pdf(**kwargs)
            self.assertEqual([r['key'] for r in render.call_args.args[0]], ['negative', 'edge'])
            self.assertIn('Minimum amount (absolute value): 100', render.call_args.args[2])
            self.assertIn('Maximum amount (absolute value): 200', render.call_args.args[2])
            self.assertEqual(render.call_args.kwargs['dataset_mode'], 'intelligence')
            self.assertEqual(response.status_code, 200)
            kwargs.update(min_amount=201, max_amount=100)
            with self.assertRaises(HTTPException) as failure:
                await financial.export_financial_pdf(**kwargs)
            self.assertEqual(failure.exception.status_code, 422)

    def test_sender_groups_do_not_combine_currencies(self):
        records = [dict(amount=100, currency='EUR', from_entity=dict(key='one',name='Same sender')),
                   dict(amount=200, currency='USD', from_entity=dict(key='one',name='Same sender')),
                   dict(amount=50, currency='EUR', from_entity=dict(key='one',name='Same sender'))]
        rows = financial._build_entity_flow_rows(records, 'from_entity', set())
        self.assertEqual({r['currency']: (r['count'],r['totalAmount']) for r in rows}, {'EUR':(2,150),'USD':(1,200)})

    async def test_category_and_sender_names_with_commas_stay_intact(self):
        kwargs = {name: value.default.default for name, value in inspect.signature(financial.export_financial_pdf).parameters.items()}
        kwargs.update(case_id='case-a', mode='intelligence', include_entity_notes=False,
                      category_names=['Review, priority'], sender_values=['Example, Ltd'])
        records = [dict(key='wanted',amount=100,category='Review, priority',from_entity=dict(name='Example, Ltd')),
                   dict(key='other',amount=100,category='Review',from_entity=dict(name='Example'))]
        with patch.object(financial.neo4j_service, 'get_financial_transactions', return_value=dict(transactions=records)), patch.object(financial, 'render_financial_export', return_value=dict(content=b'PDF',media_type='application/pdf',extension='pdf')) as render:
            await financial.export_financial_pdf(**kwargs)
            self.assertEqual([r['key'] for r in render.call_args.args[0]], ['wanted'])

    async def test_end_date_includes_timestamps_on_the_recorded_last_day(self):
        kwargs = {name: value.default.default for name, value in inspect.signature(financial.export_financial_pdf).parameters.items()}
        kwargs.update(case_id='case-a', mode='intelligence', include_entity_notes=False, start_date='2026-09-02', end_date='2026-09-02')
        records = [dict(key=str(i), date=value, amount=100) for i, value in enumerate([
            '2026-09-01', '2026-09-02', '2026-09-02T23:59:59-04:00', '2026-09-03', 'Sep 2', '2026-02-30'])]
        with patch.object(financial.neo4j_service, 'get_financial_transactions', return_value=dict(transactions=records)), patch.object(financial, 'render_financial_export', return_value=dict(content=b'PDF', media_type='application/pdf', extension='pdf')) as render:
            await financial.export_financial_pdf(**kwargs)
            self.assertEqual([row['key'] for row in render.call_args.args[0]], ['1', '2'])
            for start, end in [('2026-02-30', '2026-09-02'), ('2026-09-03', '2026-09-02'), ('2026-09', '2026-09-02')]:
                with self.assertRaises(HTTPException) as failure:
                    await financial.export_financial_pdf(**{**kwargs, 'start_date': start, 'end_date': end})
                self.assertEqual(failure.exception.status_code, 422)

    def test_recorded_dates_do_not_use_missing_or_impossible_parts(self):
        for value in ['2026-02-30', '2026-02-29', '2026-09', 'Sep 29', '09/02/2026', '2026-09-02T24:00', '0000-01-01']:
            self.assertIsNone(financial._financial_record_day(value), value)
        self.assertEqual(financial._financial_record_day('2024-02-29'), '2024-02-29')
        self.assertEqual(financial._financial_record_day('2026-09-02T00:10:00+03:00'), '2026-09-02')

    async def test_list_endpoint_refuses_invalid_date_range_before_reading(self):
        with patch.object(financial.neo4j_service, 'get_financial_transactions') as read:
            with self.assertRaises(HTTPException) as failure:
                await financial.get_financial_transactions(case_id='case-a', mode='intelligence', types=None, start_date='2026-09-03', end_date='2026-09-02', categories=None, db=None)
            self.assertEqual(failure.exception.status_code, 422)
            read.assert_not_called()

    def test_database_list_uses_the_same_calendar_date_filter(self):
        from importlib import import_module
        module = import_module('services.neo4j.financial_service')
        from unittest.mock import MagicMock
        service = module.FinancialService()
        connection = MagicMock()
        connection.session.return_value.__enter__.return_value.run.return_value = [
            dict(key=str(i), date=value) for i, value in enumerate([
                '2026-09-02', '2026-09-02T23:59:59-04:00', '2026-09-02T24:00', '2026-09-03', 'Sep 2'])]
        with patch.object(module, 'driver', connection), patch.object(service, '_get_dataset_metadata', return_value={'uses_legacy_financial_model': False}), patch.object(service, '_record_to_transaction', side_effect=lambda row, **kw: row), patch.object(service, '_sanitize_transaction', side_effect=lambda row: row):
            result = service.get_financial_transactions(case_id='case-a', mode='intelligence', start_date='2026-09-02', end_date='2026-09-02')
        self.assertEqual([row['key'] for row in result['transactions']], ['0', '1'])
        self.assertEqual(result['total'], 2)
        query = connection.session.return_value.__enter__.return_value.run.call_args.args[0]
        self.assertIn('substring(trim(toString(n.date)), 0, 10) <= $end_date', query)
