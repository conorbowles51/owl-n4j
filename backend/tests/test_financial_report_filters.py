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
