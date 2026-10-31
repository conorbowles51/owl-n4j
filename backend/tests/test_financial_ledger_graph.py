from unittest.mock import patch
from services.financial.ledger_graph import ledger_posting_graph
from services.financial.ledger_summary import LedgerSummaryError
from tests.test_financial_ledger_transfers import LedgerTransferTests

class LedgerGraphTests(LedgerTransferTests):
    def test_postings_are_source_bound_and_label_groups_do_not_merge_accounts(self):
        debit, credit = self.pair()
        debit.counterparty_raw = credit.counterparty_raw = '<name & label>'
        self.db.commit()
        graph = ledger_posting_graph(self.capture())
        self.assertEqual(len(graph['edges']), 2)
        self.assertEqual(len(graph['nodes']), 4)
        by_id = {node['id']: node for node in graph['nodes']}
        edge = next(e for e in graph['edges'] if e['id'] == str(debit.id))
        self.assertEqual(by_id[edge['source']]['kind'], 'account')
        self.assertEqual(by_id[edge['target']]['kind'], 'source_label')
        self.assertEqual(edge['amount_minor'], '9007199254740993')
        self.assertEqual(edge['source_document_id'], str(debit.source_document_id))
        self.assertEqual(ledger_posting_graph(self.capture(), population='verified')['edges'], [])
    def test_without_label_origins_only_they_are_left_out_and_the_answer_says_so(self):
        self.pair()
        full = ledger_posting_graph(self.capture())
        lean = ledger_posting_graph(self.capture(), label_origins=False)
        self.assertTrue(all('label_sources' in edge for edge in full['edges']))
        self.assertTrue(full['edges'] and not any('label_sources' in edge for edge in lean['edges']))
        self.assertEqual([{k: v for k, v in edge.items() if k != 'label_sources'} for edge in full['edges']], lean['edges'])
        self.assertEqual({k: v for k, v in full.items() if k not in ('edges', 'limitation')},
                         {k: v for k, v in lean.items() if k not in ('edges', 'limitation')})
        self.assertIn('each edge records its label origins', full['limitation'])
        self.assertIn('label origins are left out of this answer', lean['limitation'])
    def test_exclusion_is_not_hidden(self):
        debit, credit = self.pair()
        from postgres.models.enums import LedgerStatus
        credit.ledger_status = LedgerStatus.rejected; self.db.commit()
        graph = ledger_posting_graph(self.capture())
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['excluded_rows'], 1)
        import json
        from types import SimpleNamespace
        captured = self.capture()
        payload = json.loads(captured.snapshot.content)
        included = next(r for r in payload['ledger']['readings'] if r['row']['key'] == str(debit.id))
        payload['ledger']['readings'] = [dict(included, row=dict(included['row'], key=f'payment-{i}')) for i in range(25000)]
        payload['ledger']['considered_rows'] = 25000
        graph = ledger_posting_graph(SimpleNamespace(snapshot=SimpleNamespace(content=json.dumps(payload), sha256='a' * 64)))
        self.assertEqual(len(graph['edges']), 25000)
        self.assertEqual(graph['edges'][-1]['transaction_id'], 'payment-24999')
        self.assertEqual(sum(int(e['amount_minor']) for e in graph['edges']), int(debit.amount_minor) * 25000)
