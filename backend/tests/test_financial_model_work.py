"""Work a model did for a person is recorded and shown as the model's until a person confirms it."""
import copy
import unittest
from uuid import UUID

from sqlalchemy import select

from postgres.models.financial import FinancialTransaction
from services.financial.decisions import Actor, DecisionError
from services.financial.model_work import (ModelWorkError, actor_from_record, actor_record, describe, is_model,
                                           model_actor, require_person)
from services.financial.payment_labels import (ConfirmPaymentLabelsRequest, PaymentLabelsError, PaymentLabelsRequest,
                                               RemovePaymentLabelsRequest, confirm_payment_labels,
                                               payment_label_view, remove_payment_labels, update_payment_labels)
from services.financial.transaction_query import to_view


def claude(citation=None):
    return model_actor(for_name='Neil Byrne', for_email='neil@example.test', model_id='claude-opus-5-5',
                       citation=citation or dict(page=3, file='statement.pdf'), how='read from the page image')


class ModelActorTests(unittest.TestCase):
    def test_model_actor_names_the_model_and_keeps_the_person_it_worked_for(self):
        actor = claude()
        self.assertEqual(actor.name, 'Claude (for Neil Byrne)')
        self.assertTrue(is_model(actor))
        self.assertEqual(actor.origin['for']['name'], 'Neil Byrne')
        self.assertEqual(actor.origin['citation'], dict(page=3, file='statement.pdf'))
        self.assertEqual(describe(actor.origin), 'Read by Claude · not confirmed')

    def test_origin_round_trips_through_the_stored_record(self):
        actor = claude()
        again = actor_from_record(actor_record(actor))
        self.assertEqual((again.name, again.email, again.origin), (actor.name, actor.email, actor.origin))
        person = actor_from_record(dict(name='Alex', email='alex@example.test', user_id=None))
        self.assertIsNone(person.origin)
        self.assertNotIn('origin', actor_record(person))

    def test_origin_is_a_field_never_read_from_the_name(self):
        legacy = Actor(name='Neil Byrne (via Claude)', email='neil@example.test')
        self.assertFalse(is_model(legacy))
        with self.assertRaises(DecisionError):
            Actor(name='x', email='y@z', origin=dict(kind='person'))

    def test_only_a_person_confirms(self):
        with self.assertRaises(ModelWorkError) as caught:
            require_person(claude())
        self.assertEqual(caught.exception.status_code, 403)
        require_person(Actor(name='Alex', email='alex@example.test'))


class ModelLabelTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests()
        self.f.setUp()
        self.receipt = self.f.confirm()
        self.rows = list(self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(self.receipt['source_document_id']))
            .order_by(FinancialTransaction.id)))
        self.row = self.rows[0]
        self.side = 'from_name' if self.row.direction == 'credit' else 'to_name'

    def tearDown(self):
        self.f.tearDown()

    def targets(self, rows):
        return [dict(id=row.id, version=(row.metadata_ or {}).get('investigation_labels', {}).get('version', 0))
                for row in rows]

    def save(self, rows, actor, reason=None, **changes):
        return update_payment_labels(self.f.db, case_id=self.f.case.id, actor=actor, reason=reason,
                                     request=PaymentLabelsRequest(transactions=self.targets(rows), **changes))

    def confirm(self, rows, actor):
        return confirm_payment_labels(self.f.db, case_id=self.f.case.id, actor=actor,
                                      request=ConfirmPaymentLabelsRequest(transactions=self.targets(rows)))

    def source(self, row):
        self.f.db.expire_all()
        row = self.f.db.get(FinancialTransaction, row.id)
        return row, payment_label_view(row, row.account)

    def test_model_reading_is_stored_with_its_origin_and_shown_as_the_models(self):
        before = (self.row.amount_minor, self.row.description, copy.deepcopy(self.row.provenance), self.row.proof_class)
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        row, view = self.source(self.row)
        self.assertEqual(view[self.side], 'ACME LTD')
        source = view['label_sources'][self.side]
        self.assertEqual(source['source'], 'model_reading')
        self.assertEqual(source['label'], 'Read by Claude · not confirmed')
        self.assertIn('Read from statement.pdf, page 3', source['explanation'])
        self.assertEqual(source['origin']['citation']['page'], 3)
        entry = row.metadata_['investigation_label_history'][-1]
        self.assertEqual(entry['actor_name'], 'Claude (for Neil Byrne)')
        self.assertEqual(entry['origin']['kind'], 'model')
        # Nothing else about the payment changes, proof class included.
        self.assertEqual(before, (row.amount_minor, row.description, row.provenance, row.proof_class))
        self.assertEqual(to_view(row, account=row.account).to_json()['label_sources'][self.side]['source'],
                         'model_reading')

    def test_a_persons_name_outranks_a_model_reading(self):
        self.save([self.row], self.f.actor, counterparty_name='Person Name')
        with self.assertRaises(PaymentLabelsError) as caught:
            self.save([self.row], claude(), counterparty_name='Model Name')
        self.assertEqual(caught.exception.status_code, 409)
        _, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('Person Name', 'investigator'))

    def test_a_person_corrects_a_model_reading_and_the_reading_stays_in_history(self):
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        self.row = self.f.db.get(FinancialTransaction, self.row.id)
        self.save([self.row], self.f.actor, counterparty_name='ACME LIMITED')
        row, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('ACME LIMITED', 'investigator'))
        history = row.metadata_['investigation_label_history']
        self.assertEqual([e['actor_name'] for e in history], ['Claude (for Neil Byrne)', self.f.actor.name])
        # Undoing the correction puts the model's reading back, still as the model's.
        remove_payment_labels(self.f.db, case_id=self.f.case.id, actor=self.f.actor,
                              request=RemovePaymentLabelsRequest(transactions=self.targets([row]),
                                                                 fields=['counterparty_name']))
        _, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('ACME LTD', 'model_reading'))

    def test_confirm_makes_the_person_the_actor_without_changing_the_value(self):
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        row = self.f.db.get(FinancialTransaction, self.row.id)
        with self.assertRaises(PaymentLabelsError) as caught:
            self.confirm([row], claude())
        self.assertEqual(caught.exception.status_code, 403)
        result = self.confirm([row], self.f.actor)
        self.assertEqual((result['confirmed'], result['skipped']), (1, 0))
        row, view = self.source(self.row)
        source = view['label_sources'][self.side]
        self.assertEqual((view[self.side], source['source']), ('ACME LTD', 'investigator'))
        self.assertTrue(source['explanation'].startswith(f'Confirmed by {self.f.actor.name} from the statement on '))
        self.assertIn('Read first by Claude', source['explanation'])
        history = row.metadata_['investigation_label_history']
        self.assertEqual(history[0]['origin']['kind'], 'model')
        self.assertEqual(history[-1]['confirmed'], [self.side])
        # Confirming again finds nothing unconfirmed.
        self.assertEqual(self.confirm([row], self.f.actor)['skipped'], 1)

    def test_export_carries_the_origin_and_lists_unconfirmed_work_as_a_limitation(self):
        import json
        from services.financial.expert_support import build_expert_support
        from services.financial.ledger_snapshot import (LedgerSnapshot, _capture_history, capture_ledger_snapshot,
                                                        render_ledger_report)

        from postgres.base import Base
        import postgres.models.financial_candidates  # noqa: F401 - registers the review-history tables
        Base.metadata.create_all(self.f.db.connection(), tables=[t for name, t in Base.metadata.tables.items()
                                                                  if name.startswith('financial_candidate')])
        self.f.db.commit()

        def capture_ledger_export(_bind, case_id):
            # The export's own capture needs PostgreSQL; this is the same snapshot and history capture on SQLite.
            document = _capture_history(self.f.db, json.loads(capture_ledger_snapshot(self.f.db, case_id=case_id).content),
                                        case_id=case_id)
            from types import SimpleNamespace
            return SimpleNamespace(snapshot=LedgerSnapshot(json.dumps(document), 'a' * 64, 0))
        self.save([self.row], claude(), counterparty_name='ACME LTD', reason='Printed under the amount.')
        self.f.db.commit()
        export = capture_ledger_export(self.f.db.get_bind(), case_id=self.f.case.id)
        document = json.loads(export.snapshot.content)
        reading = next(r for r in document['ledger']['readings'] if r['row']['key'] == str(self.row.id))
        self.assertEqual(reading['row']['label_sources'][self.side]['source'], 'model_reading')
        self.assertEqual(reading['investigation_label_history'][-1]['origin']['kind'], 'model')
        self.assertTrue(any('not yet confirmed by a person: 1 names' in v for v in document['limitations']))
        report = render_ledger_report(export.snapshot)
        self.assertIn('ACME LTD (Read by Claude · not confirmed: Read by Claude for Neil Byrne', report)
        self.assertIn('page 3', report)
        support = build_expert_support(document, snapshot_sha256=export.snapshot.sha256)
        self.assertEqual((support['model_work']['unconfirmed_names'], support['model_work']['names'][0]['page']), (1, 3))
        # Confirmed: the report names the person and the model's reading stays in the captured history.
        row = self.f.db.get(FinancialTransaction, self.row.id)
        self.confirm([row], self.f.actor)
        self.f.db.commit()
        export = capture_ledger_export(self.f.db.get_bind(), case_id=self.f.case.id)
        report = render_ledger_report(export.snapshot)
        self.assertIn(f'ACME LTD (Confirmed by {self.f.actor.name} from the statement on', report)
        document = json.loads(export.snapshot.content)
        self.assertFalse(any('not yet confirmed by a person' in v for v in document['limitations']))
        self.assertEqual(build_expert_support(document, snapshot_sha256='x')['model_work']['confirmed_names'], 1)

    def test_pending_reads_load_as_model_readings_and_refused_lines_stay(self):
        import json
        from services.financial.model_reads import load_model_reads as load
        person_row = self.rows[1]
        self.save([person_row], self.f.actor, counterparty_name='Person Name')
        line = lambda row, value: json.dumps(dict(case=str(self.f.case.id), payment_id=str(row.id), value=value,
                                                  page=2, file='statement.pdf', why='Printed under the amount.',
                                                  **{'for': 'Neil Byrne'}, for_email='neil@example.test')) + '\n'
        lines = [line(self.row, 'ACME LTD'), line(person_row, 'Model Name'), '{"case": "x"}\n']
        results, keep = load(self.f.db, lines, apply=False)
        self.assertEqual([r['status'] for r in results], ['would_save', 'refused', 'refused'])
        self.assertEqual(self.source(self.row)[1]['label_sources'][self.side].get('source'), 'missing'
                         if not self.row.counterparty_raw else 'statement')
        results, keep = load(self.f.db, lines, apply=True)
        self.assertEqual([r['status'] for r in results], ['saved', 'refused', 'refused'])
        self.assertEqual(keep, lines[1:])
        _, view = self.source(self.row)
        source = view['label_sources'][self.side]
        self.assertEqual((view[self.side], source['source'], source['origin']['citation']['page']),
                         ('ACME LTD', 'model_reading', 2))
        _, view = self.source(person_row)
        self.assertEqual(view['to_name' if person_row.direction == 'debit' else 'from_name'], 'Person Name')
        # The same reading again: the payment already carries it, so nothing is recorded and it is reported.
        results, keep = load(self.f.db, lines[:1], apply=True)
        self.assertEqual(([r['status'] for r in results], keep), (['unchanged'], []))

    def test_a_model_reads_names_only(self):
        for changes in (dict(category='Travel'), dict(counterparty_name='')):
            with self.assertRaises(PaymentLabelsError):
                self.save([self.row], claude(), **changes)
        with self.assertRaises(PaymentLabelsError) as caught:
            remove_payment_labels(self.f.db, case_id=self.f.case.id, actor=claude(),
                                  request=RemovePaymentLabelsRequest(transactions=self.targets([self.row]),
                                                                     fields=['counterparty_name']))
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()


class ModelStatementSaveTests(unittest.TestCase):
    """A statement saved to the case by a model: every payment's save records the model's origin, the statement
    carries one open call until a person confirms it, and the proof class is the one a person's save gets."""

    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests()
        self.f.setUp()
        from postgres.models.financial_judgements import FinancialJudgement
        from postgres.base import Base
        Base.metadata.create_all(self.f.db.connection(), tables=[FinancialJudgement.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def save_as(self, actor):
        self.f.actor = actor
        receipt = self.f.confirm()
        return receipt, list(self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(receipt['source_document_id']))))

    def model(self):
        return model_actor(for_name=self.f.user.name, for_email=self.f.user.email, for_user_id=self.f.user.id,
                           citation=dict(file='statement.pdf'))

    def test_model_save_stores_origin_and_one_open_statement_call(self):
        from services.financial import judgements
        receipt, rows = self.save_as(self.model())
        self.assertTrue(rows)
        for row in rows:
            saver = row.provenance['confirmed_by']
            self.assertEqual(saver['name'], f'Claude (for {self.f.user.name})')
            self.assertEqual(saver['origin']['kind'], 'model')
        document_id = UUID(receipt['source_document_id'])
        work = judgements.statement_model_work(self.f.db, self.f.case.id, document_id)
        self.assertEqual((work['status'], work['model'], work['for_person']), ('not_confirmed', 'Claude', self.f.user.name))
        self.assertEqual([c['rule_id'] for c in work['calls']], ['model.statement_save'])
        self.assertEqual(judgements.model_work_statements(self.f.db, self.f.case.id), {str(document_id): 'not_confirmed'})
        # Only a person confirms; one action confirms the statement and names the person.
        with self.assertRaises(judgements.JudgementError) as caught:
            judgements.confirm_statement(self.f.db, case_id=self.f.case.id, source_document_id=document_id,
                                         actor=self.model())
        self.assertEqual(caught.exception.status_code, 403)
        person = Actor(name='Alex Person', email='alex@example.test')
        work = judgements.confirm_statement(self.f.db, case_id=self.f.case.id, source_document_id=document_id,
                                           actor=person)
        self.assertEqual((work['status'], work['confirmed_by']), ('confirmed', 'Alex Person'))
        with self.assertRaises(judgements.JudgementError):
            judgements.confirm_statement(self.f.db, case_id=self.f.case.id, source_document_id=document_id,
                                         actor=person)

    def test_proof_class_and_values_are_the_same_as_a_persons_save(self):
        _, by_model = self.save_as(self.model())
        model_rows = sorted((r.amount_minor, r.direction, r.description, r.proof_class, r.transaction_date)
                            for r in by_model)
        self.f.tearDown()
        self.setUp()
        _, by_person = self.save_as(Actor(self.f.user.name, self.f.user.email, self.f.user.id))
        person_rows = sorted((r.amount_minor, r.direction, r.description, r.proof_class, r.transaction_date)
                             for r in by_person)
        self.assertEqual(model_rows, person_rows)
        self.assertNotIn('origin', by_person[0].provenance['confirmed_by'])

    def test_a_persons_save_records_no_model_call(self):
        from services.financial import judgements
        receipt, _ = self.save_as(Actor(self.f.user.name, self.f.user.email, self.f.user.id))
        self.assertIsNone(judgements.statement_model_work(self.f.db, self.f.case.id,
                                                          UUID(receipt['source_document_id'])))


class LegacyMigrationTests(unittest.TestCase):
    """Records saved as '<person> (via Claude)' move to the model origin; nothing else changes; twice is once."""

    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        from postgres.models.financial_judgements import FinancialJudgement
        from postgres.base import Base
        self.f = StatementImportTests()
        self.f.setUp()
        Base.metadata.create_all(self.f.db.connection(), tables=[FinancialJudgement.__table__])
        self.f.db.commit()
        self.legacy = Actor(name=f'{self.f.user.name} (via Claude)', email=self.f.user.email, user_id=self.f.user.id)
        self.f.actor = self.legacy
        self.receipt = self.f.confirm()
        self.document_id = UUID(self.receipt['source_document_id'])
        self.rows = list(self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document_id).order_by(FinancialTransaction.id)))
        self.row = self.rows[0]
        self.side = 'from_name' if self.row.direction == 'credit' else 'to_name'
        update_payment_labels(self.f.db, case_id=self.f.case.id, actor=self.legacy, reason='Read from page 1.',
                              request=PaymentLabelsRequest(transactions=[dict(id=self.row.id, version=0)],
                                                           counterparty_name='ACME LTD'))

    def tearDown(self):
        self.f.tearDown()

    def snapshot(self):
        self.f.db.expire_all()
        rows = self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.case_id == self.f.case.id).order_by(FinancialTransaction.id))
        out = []
        for row in rows:
            view = payment_label_view(row, row.account)
            out.append((str(row.id), row.amount_minor, row.direction, row.description, row.proof_class,
                        row.transaction_date, row.ledger_status, row.content_hash, view['from_name'], view['to_name'],
                        view['category'], (row.metadata_ or {}).get('investigation_labels', {}).get(self.side)))
        return out

    def test_migration_moves_names_to_the_origin_and_changes_no_value(self):
        from services.financial import judgements
        from services.financial.model_work_migration import migrate
        before = self.snapshot()
        _, view = self.source()
        self.assertEqual(view['label_sources'][self.side]['source'], 'investigator')  # the legacy presentation
        result = migrate(self.f.db, case_ids=[self.f.case.id], apply=True)
        self.assertEqual(result['records']['transaction.saved_by'], len(self.rows))
        self.assertEqual(result['records']['transaction.label'], 1)
        self.assertEqual(result['statement_calls'], {'recorded': 1})
        self.assertEqual(before, self.snapshot())
        row, view = self.source()
        source = view['label_sources'][self.side]
        self.assertEqual((view[self.side], source['source']), ('ACME LTD', 'model_reading'))
        self.assertIn('Read from page 1.', source['explanation'])
        saver = row.provenance['confirmed_by']
        self.assertEqual(saver['name'], f'Claude (for {self.f.user.name})')
        self.assertEqual(saver['origin']['recorded_as'], f'{self.f.user.name} (via Claude)')
        self.assertEqual(saver['origin']['migrated']['by'], 'Loupe model-work origin migration')
        self.assertEqual(saver['origin']['for']['user_id'], str(self.f.user.id))
        work = judgements.statement_model_work(self.f.db, self.f.case.id, self.document_id)
        self.assertEqual(work['status'], 'not_confirmed')
        # Idempotent: a second run finds nothing to move and records nothing.
        again = migrate(self.f.db, case_ids=[self.f.case.id], apply=True)
        self.assertEqual((again['records'], again['statement_calls']), ({}, {}))
        self.assertEqual(before, self.snapshot())

    def test_a_sealed_original_keeps_its_bytes_and_its_origin_is_stored_beside_it(self):
        from postgres.models.financial import FinancialSourceDocument
        from services.financial.model_work_migration import SEALED_KEY, migrate, remaining
        from services.financial.pdf_candidates import _digest
        document = self.f.db.get(FinancialSourceDocument, self.document_id)
        metadata = dict(document.metadata_ or {})
        original = dict(metadata.get('statement_import_original') or {})
        original['saved_review'] = dict(saved_by=self.legacy.name, saved_at='2026-10-25T10:00:00+00:00')
        metadata['statement_import_original'] = original
        metadata['statement_import_original_sha256'] = _digest(original)
        metadata['account_refiles'] = [dict(by=self.legacy.name, at='2026-10-25T11:00:00+00:00')]
        document.metadata_ = metadata
        self.f.db.commit()
        result = migrate(self.f.db, case_ids=[self.f.case.id], apply=True)
        self.assertEqual(result['actors']['source_document.sealed'], 1)
        self.f.db.expire_all()
        stored = self.f.db.get(FinancialSourceDocument, self.document_id).metadata_
        # The sealed original is byte for byte what was recorded, and its digest still verifies.
        self.assertEqual(stored['statement_import_original'], original)
        self.assertEqual(_digest(stored['statement_import_original']), stored['statement_import_original_sha256'])
        note, = stored[SEALED_KEY]
        self.assertEqual((note['path'], note['name']), (['statement_import_original', 'saved_review', 'saved_by'],
                                                        f'Claude (for {self.f.user.name})'))
        self.assertEqual(note['origin']['recorded_as'], self.legacy.name)
        # An unsealed record moves to the origin as usual.
        self.assertEqual(stored['account_refiles'][0]['by'], f'Claude (for {self.f.user.name})')
        self.assertEqual(remaining(self.f.db)['financial_source_documents.metadata'], 0) \
            if self.f.db.bind.dialect.name == 'postgresql' else None
        again = migrate(self.f.db, case_ids=[self.f.case.id], apply=True)
        self.assertEqual(again['records'], {})

    def test_a_statement_with_a_persons_payment_first_still_gets_its_call(self):
        from services.financial import judgements
        from services.financial.model_work_migration import migrate
        first = self.rows[0]
        provenance = dict(first.provenance)
        provenance['confirmed_by'] = dict(name=self.f.user.name, email=self.f.user.email, user_id=str(self.f.user.id))
        first.provenance = provenance
        self.f.db.commit()
        result = migrate(self.f.db, case_ids=[self.f.case.id], apply=True)
        self.assertEqual(result['statement_calls'], {'recorded': 1})
        work = judgements.statement_model_work(self.f.db, self.f.case.id, self.document_id)
        self.assertEqual(work['status'], 'not_confirmed')

    def test_a_first_name_names_the_account_only_when_one_account_has_it(self):
        from services.financial.model_work_migration import _Run
        run = _Run(now='x', users={'1': 'Neil Byrne', '2': 'Neil Other'}, people={'Neil Byrne': '1', 'Neil Other': '2'})
        self.assertEqual(run.person('claude (for Neil)', None), ('Neil', None))
        self.assertEqual(run.person('claude (for Neil Byrne)', None), ('Neil Byrne', '1'))
        run = _Run(now='x', users={'1': 'Neil Byrne'}, people={'Neil Byrne': '1'})
        self.assertEqual(run.person('claude (for Neil)', None), ('Neil Byrne', '1'))

    def test_dry_run_writes_nothing(self):
        from services.financial.model_work_migration import migrate
        result = migrate(self.f.db, case_ids=[self.f.case.id], apply=False)
        self.assertEqual(result['records']['transaction.saved_by'], len(self.rows))
        self.f.db.expire_all()
        row = self.f.db.get(FinancialTransaction, self.row.id)
        self.assertEqual(row.provenance['confirmed_by']['name'], f'{self.f.user.name} (via Claude)')

    def test_legacy_names_are_recognised_and_people_are_not(self):
        from services.financial.model_work_migration import legacy_person
        self.assertEqual(legacy_person('Neil Byrne (via Claude)'), 'Neil Byrne')
        self.assertEqual(legacy_person('claude (for Neil)'), 'Neil')
        for name in ('Neil Byrne', 'System', 'Claude (for Neil Byrne)x', None, 'Alexandra Solórzano'):
            self.assertIsNone(legacy_person(name), name)

    def source(self):
        self.f.db.expire_all()
        row = self.f.db.get(FinancialTransaction, self.row.id)
        return row, payment_label_view(row, row.account)
