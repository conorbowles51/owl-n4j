"""Full-range views read the ledger readings and decision log directly and stamp a ledger-scope fingerprint.

The same scope gives the same ledger-scope fingerprint as the export's manifest; each stamp names what it
covers; guarded scenario writes compare like with like and still refuse on any payment or decision change."""
import hashlib
import json
from unittest.mock import patch

from postgres.models.enums import TransactionDirection
from services.financial.ledger_snapshot import (FULL_DOCUMENT_COVERS, LEDGER_SCOPE_COVERS, LedgerExport, LedgerScope,
    LedgerSnapshot, capture_ledger_export, capture_ledger_scope, snapshot_matches)
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_transfers import evaluate_transfer_scenario, ledger_transfer_candidates
from tests.test_financial_ledger_summary import LedgerSummaryTests

STAMPS = ('snapshot_sha256', 'digest_covers', 'snapshot_json')


def _review_history(text):
    return lambda session, **kw: dict(reviews=[dict(note=text)], candidates=[], finalizations=[])


class LedgerScopeTests(LedgerSummaryTests):
    def consistent(self):
        # SQLite stands in for the view's read-only PostgreSQL snapshot: the caller's connection is used as is.
        return patch('services.financial.ledger_snapshot._in_consistent_read', return_value=True)

    def export(self, review='none', **scope):
        # Notes are an export-only section whose table the SQLite fixture does not create.
        with self.consistent(), patch('services.financial.ledger_review_history.capture_pdf_review_history', _review_history(review)), \
                patch('services.financial.transaction_notes.capture_transaction_notes', return_value=[]):
            return capture_ledger_export(self.db.connection(), case_id=self.case.id, **scope)

    def scope(self, **scope):
        with self.consistent():
            return capture_ledger_scope(self.db.connection(), case_id=self.case.id, **scope)

    def pair(self):
        account = self._account(self.case.id, identity_key='second-account'); self.db.add(account); self.db.commit()
        debit, _ = self.add(125000, TransactionDirection.debit)
        doc = self.make_document(); period = self.make_period(doc, account=account)
        credit = self.add_row(period, doc, amount=125000, account=account)
        debit.proof_class = credit.proof_class = 'p3'; self.db.commit()
        return debit, credit

    def decide(self, row, reason):
        from services.financial.quarantine_row import quarantine_case_row
        quarantine_case_row(self.db, case_id=self.case.id, transaction_id=row.id, actor=self.user, reason=reason)

    def test_same_scope_gives_the_same_ledger_scope_fingerprint_on_both_paths(self):
        debit, _ = self.pair(); self.add(700)
        self.decide(debit, 'Scope fingerprint test')
        export, scope = self.export(), self.scope()
        manifest = json.loads(export.manifest)
        self.assertEqual(scope.sha256, export.ledger_scope_sha256)
        self.assertEqual(manifest['ledger_scope_sha256'], scope.sha256)
        self.assertEqual(manifest['ledger_scope_digest_covers'], LEDGER_SCOPE_COVERS)
        self.assertEqual(manifest['digest_covers'], FULL_DOCUMENT_COVERS)
        self.assertEqual(manifest['document_sha256'], hashlib.sha256(export.snapshot.content.encode()).hexdigest())
        self.assertNotEqual(scope.sha256, export.snapshot.sha256)
        document = json.loads(export.snapshot.content)
        self.assertEqual(json.loads(json.dumps(scope.document['ledger'])), document['ledger'])
        self.assertEqual(scope.document['decisions'], document['decisions'])
        self.assertEqual(len(scope.document['decisions']), 1)

    def test_every_view_gives_the_same_result_from_either_capture_and_names_its_stamp(self):
        from services.financial.counterparty_parties import counterparty_party_analysis
        from services.financial.ledger_graph import ledger_posting_graph
        from services.financial.ledger_timeline import ledger_timeline
        from services.financial.pattern_review import screen_ledger_patterns
        debit, _ = self.pair(); self.add(700); self.add(700)
        self.decide(debit, 'View equality test')
        export, scope = self.export(), self.scope()
        views = (ledger_posting_graph, ledger_timeline, ledger_transfer_candidates, counterparty_party_analysis,
                 lambda capture: screen_ledger_patterns(capture, window_days=30))
        for view in views:
            old, new = view(export), view(scope)
            self.assertEqual(old['digest_covers'], FULL_DOCUMENT_COVERS)
            self.assertEqual(old['snapshot_sha256'], export.snapshot.sha256)
            self.assertEqual(new['digest_covers'], LEDGER_SCOPE_COVERS)
            self.assertEqual(new['snapshot_sha256'], scope.sha256)
            strip = lambda result: json.loads(json.dumps({k: v for k, v in result.items() if k not in STAMPS}))
            self.assertEqual(strip(old), strip(new))
        self.assertIsNone(counterparty_party_analysis(scope)['snapshot_json'])

    def test_the_stamp_changes_with_any_payment_or_decision_and_not_with_review_history(self):
        debit, credit = self.pair()
        first = self.scope().sha256
        self.assertEqual(self.scope().sha256, first)
        self.assertEqual(self.export(review='one').ledger_scope_sha256, self.export(review='two').ledger_scope_sha256)
        self.assertNotEqual(self.export(review='one').snapshot.sha256, self.export(review='two').snapshot.sha256)
        credit.description = 'Edited after the stamp'; self.db.commit()
        second = self.scope().sha256
        self.assertNotEqual(second, first)
        self.decide(debit, 'Decision after the stamp')
        self.assertNotEqual(self.scope().sha256, second)

    def request(self, expected, debit, credit):
        return dict(expected_snapshot_sha256=expected, population='working', tolerance_days=3,
            pairs=[dict(debit_id=str(debit.id), credit_id=str(credit.id))], basis='Synthetic proposed transfer test')

    def test_a_scenario_from_a_ledger_scope_stamp_is_guarded_by_readings_and_decisions(self):
        debit, credit = self.pair()
        stamp = ledger_transfer_candidates(self.scope())['snapshot_sha256']
        # Review history alone changed between the view and the scenario: still the same readings and decisions.
        scenario = evaluate_transfer_scenario(self.export(review='later'), self.request(stamp, debit, credit))
        document = json.loads(scenario['scenario_json'])
        self.assertEqual(document['expected_snapshot_digest_covers'], LEDGER_SCOPE_COVERS)
        self.assertEqual(document['ledger_manifest']['ledger_scope_sha256'], stamp)
        credit.description = 'Changed payment'; self.db.commit()
        with self.assertRaisesRegex(LedgerSummaryError, 'changed'):
            evaluate_transfer_scenario(self.export(), self.request(stamp, debit, credit))
        stamp = ledger_transfer_candidates(self.scope())['snapshot_sha256']
        evaluate_transfer_scenario(self.export(), self.request(stamp, debit, credit))
        self.decide(self.add(5)[0], 'A decision in scope')
        with self.assertRaisesRegex(LedgerSummaryError, 'changed'):
            evaluate_transfer_scenario(self.export(), self.request(stamp, debit, credit))

    def test_an_old_full_document_stamp_is_still_checked_against_the_full_document(self):
        debit, credit = self.pair()
        export = self.export(review='same')
        old = export.snapshot.sha256
        document = json.loads(evaluate_transfer_scenario(self.export(review='same'), self.request(old, debit, credit))['scenario_json'])
        self.assertNotIn('expected_snapshot_digest_covers', document)
        self.assertEqual(snapshot_matches(export, old), FULL_DOCUMENT_COVERS)
        # The full-document stamp covers review history too, as it always did.
        with self.assertRaisesRegex(LedgerSummaryError, 'changed'):
            evaluate_transfer_scenario(self.export(review='other'), self.request(old, debit, credit))
        # A stored export without the ledger-scope fingerprint (made before it existed) still matches its own stamp.
        stored = LedgerExport(LedgerSnapshot(export.snapshot.content, old, export.snapshot.byte_count), '{}')
        self.assertEqual(snapshot_matches(stored, old), FULL_DOCUMENT_COVERS)
        self.assertIsNone(snapshot_matches(stored, export.ledger_scope_sha256))
        self.assertIsNone(snapshot_matches(self.scope(), old))

    def test_the_view_capture_has_no_document_size_limit_and_keeps_the_row_limit(self):
        self.add(1); self.add(2)
        with patch('services.financial.ledger_snapshot.MAX_LEDGER_SNAPSHOT_BYTES', 1):
            with self.assertRaisesRegex(LedgerSummaryError, '64 MiB'):
                self.export()
            self.assertIsInstance(self.scope(), LedgerScope)
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS', 1), self.assertRaises(LedgerSummaryError):
            self.scope()
        with patch('services.financial.ledger_snapshot.MAX_EXPORT_DECISIONS', 0):
            self.decide(self.add(3)[0], 'Over the decision limit')
            with self.assertRaisesRegex(LedgerSummaryError, 'no truncated'):
                self.scope()

    def test_the_view_capture_refuses_a_connection_outside_a_consistent_read(self):
        with self.assertRaises(LedgerSummaryError):
            capture_ledger_scope(self.db.get_bind(), case_id=self.case.id)

    def test_a_working_reading_the_export_refuses_is_refused_by_the_views_too(self):
        row, _ = self.add(700); row.proof_class = 'p3'; row.currency = 'XXQ'; self.db.commit()
        with self.assertRaises(LedgerSummaryError):
            self.export()
        with self.assertRaises(LedgerSummaryError):
            self.scope()
