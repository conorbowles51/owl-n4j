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
    def test_exclusion_and_row_limits_are_not_hidden(self):
        debit, credit = self.pair()
        from postgres.models.enums import LedgerStatus
        credit.ledger_status = LedgerStatus.rejected; self.db.commit()
        graph = ledger_posting_graph(self.capture())
        self.assertEqual(len(graph['edges']), 1)
        self.assertEqual(graph['excluded_rows'], 1)
        with patch('services.financial.ledger_graph.MAX_GRAPH_ROWS', 0):
            with self.assertRaises(LedgerSummaryError): ledger_posting_graph(self.capture())
