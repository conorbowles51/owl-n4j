import copy
import json
import unittest
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.payment_labels import PaymentLabelsRequest, PaymentLabelsError, update_payment_labels
from services.financial.transaction_query import to_view
from services.financial.ledger_snapshot import capture_ledger_snapshot
from services.financial.ledger_table_view import capture_table_view


class PaymentLabelsTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests()
        self.f.setUp()
        self.receipt = self.f.confirm()
        self.rows = list(self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(self.receipt['source_document_id']))))

    def tearDown(self):
        self.f.tearDown()

    def save(self, rows, **changes):
        request = PaymentLabelsRequest(transactions=[dict(id=row.id,
            version=(row.metadata_ or {}).get('investigation_labels', {}).get('version', 0)) for row in rows], **changes)
        return update_payment_labels(self.f.db, case_id=self.f.case.id, request=request, actor=self.f.actor)

    def test_labels_survive_reload_and_reach_reads_snapshot_filter_and_graph_without_rewriting_source(self):
        row = self.rows[0]
        original = (row.description, row.counterparty_raw, row.amount_minor, row.content_hash, copy.deepcopy(row.provenance))
        self.save([row], category='Travel', from_name='Investigator sender', to_name='Investigator recipient')
        self.f.db.expire_all()
        row = self.f.db.get(FinancialTransaction, row.id)
        view = to_view(row, account=row.account).to_json()
        self.assertEqual((view['category'], view['from_name'], view['to_name'], view['label_version']),
            ('Travel', 'Investigator sender', 'Investigator recipient', 1))
        self.assertEqual(original, (row.description, row.counterparty_raw, row.amount_minor, row.content_hash, row.provenance))
        snapshot = json.loads(capture_ledger_snapshot(self.f.db, case_id=self.f.case.id).content)
        captured = next(r for r in snapshot['ledger']['readings'] if r['row']['key'] == str(row.id))
        self.assertEqual(captured['investigation_label_history'][0]['actor_email'], self.f.actor.email)
        filtered = capture_table_view(snapshot['ledger'], dict(category='Travel'))
        self.assertEqual(filtered['row_ids'], [str(row.id)])
        from services.financial.ledger_graph import ledger_posting_graph
        from types import SimpleNamespace
        snapshot['export_ready'] = True
        snapshot['ledger']['history_captured'] = True
        graph = ledger_posting_graph(SimpleNamespace(snapshot=SimpleNamespace(content=json.dumps(snapshot), sha256='a'*64)))
        edge = next(e for e in graph['edges'] if e['id'] == str(row.id))
        self.assertEqual(edge['category'], 'Travel')
        self.assertTrue(any(n['label'] == ('Investigator sender' if row.direction == 'credit' else 'Investigator recipient') for n in graph['nodes']))

    def test_bulk_assignment_and_clear_retain_individual_names_and_audit(self):
        self.save(self.rows, category='Case-specific review')
        self.assertTrue(all(to_view(r).category == 'Case-specific review' for r in self.rows))
        self.save(self.rows[:2], category='')
        self.assertEqual(to_view(self.rows[0]).category, '')
        self.assertEqual(to_view(self.rows[2]).category, 'Case-specific review')
        from routers.financial_ledger import get_ledger_categories
        self.assertEqual(get_ledger_categories(case_id=self.f.case.id, db=self.f.db)['categories'], ['Case-specific review'])
        self.assertEqual(len(self.rows[0].metadata_['investigation_label_history']), 2)

    def test_stale_or_cross_case_bulk_edit_changes_nothing(self):
        self.save([self.rows[0]], category='Reviewed')
        stale = PaymentLabelsRequest(transactions=[dict(id=r.id, version=0) for r in self.rows], category='Wrong')
        with self.assertRaisesRegex(PaymentLabelsError, 'Someone edited'):
            update_payment_labels(self.f.db, case_id=self.f.case.id, request=stale, actor=self.f.actor)
        self.f.db.expire_all()
        self.assertEqual(to_view(self.rows[1]).category, '')
        foreign = PaymentLabelsRequest(transactions=[dict(id=self.rows[1].id, version=0), dict(id=uuid4(), version=0)], category='Wrong')
        with self.assertRaisesRegex(PaymentLabelsError, 'unavailable'):
            update_payment_labels(self.f.db, case_id=self.f.case.id, request=foreign, actor=self.f.actor)
        self.f.db.expire_all()
        self.assertEqual(to_view(self.rows[1]).category, '')

    def test_graph_name_edit_assigns_correct_side_for_incoming_and_outgoing(self):
        self.assertEqual({r.direction for r in self.rows}, {'credit', 'debit'})
        self.save(self.rows, counterparty_name='Reviewed business')
        for row in self.rows:
            view = to_view(row, account=row.account)
            self.assertEqual(view.from_name if row.direction == 'credit' else view.to_name, 'Reviewed business')
            self.assertNotEqual(view.to_name if row.direction == 'credit' else view.from_name, 'Reviewed business')

    def test_description_suggestions_reach_filters_exports_and_survive_explicit_clear(self):
        from routers.financial_ledger import get_ledger_categories
        from services.financial.ledger_snapshot import render_ledger_report
        row = next(r for r in self.rows if r.direction == 'debit')
        row.description = 'NIKE.COM AP8008066453OR'
        row.counterparty_raw = None
        self.f.db.commit()
        original = (row.amount_minor, row.currency, row.running_balance_minor, row.content_hash, copy.deepcopy(row.provenance))
        view = to_view(row, account=row.account).to_json()
        self.assertEqual((view['category'], view['to_name']), ('Shopping', 'Nike'))
        self.assertEqual(view['label_sources']['to_name']['source'], 'description')
        self.assertIn('Shopping', get_ledger_categories(case_id=self.f.case.id, db=self.f.db)['categories'])
        snapshot = capture_ledger_snapshot(self.f.db, case_id=self.f.case.id)
        document = json.loads(snapshot.content)
        filtered = capture_table_view(document['ledger'], dict(category='Shopping'))
        self.assertEqual(filtered['row_ids'], [str(row.id)])
        html = render_ledger_report(snapshot)
        self.assertIn('Nike (suggested)', html)
        self.assertIn('Shopping (suggested)', html)
        self.save([row], category='Shopping')
        self.f.db.expire_all()
        self.assertEqual(to_view(row, account=row.account).label_sources['category']['source'], 'investigator')
        self.assertEqual(row.metadata_['investigation_label_history'][0]['before']['category'], 'Shopping')
        self.assertEqual(row.metadata_['investigation_label_history'][0]['previous_label_sources']['category']['source'], 'description')
        self.save([row], category='', to_name='')
        self.f.db.expire_all()
        view = to_view(row, account=row.account).to_json()
        self.assertEqual((view['category'], view['to_name']), ('', ''))
        self.assertNotIn('Shopping', get_ledger_categories(case_id=self.f.case.id, db=self.f.db)['categories'])
        self.assertEqual(original, (row.amount_minor, row.currency, row.running_balance_minor, row.content_hash, row.provenance))
