"""The expert packet says which of its four parts hold for one export, from that export's own records."""
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial import FinancialIngestionRun
from postgres.models.financial_audit import FinancialAuditEvent
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial import expert_packet
from services.financial.component_manifest import run_components
from services.financial.processing_provenance import capture_processing_provenance
from services.financial.expert_packet import (COMPLETE, INCOMPLETE, NO_MEASUREMENT, NOT_RECORDED, archive_packet_header,
    capture_audit_summary, capture_extraction_validation, capture_packet_records, capture_selected_tracing, component_rows, made_by, packet_parts)
from services.financial.expert_support import build_expert_support
from services.financial.ledger_snapshot import (LedgerExport, LedgerSnapshot, _capture_history, capture_ledger_snapshot,
    ledger_export_archive, render_ledger_report)
from tests import test_financial_ledger_summary as fixture

LATER, EARLIER = '2026-02-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'


def snapshot_of(document):
    content = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return LedgerSnapshot(content, hashlib.sha256(content.encode()).hexdigest(), len(content.encode()))


def whole_document():
    """Every part holding: the one shape in which a packet may be called complete."""
    run = dict(id='run', code_version='1.0.0+abc', ruleset_version='rules', started_at=LATER,
               components=dict(commit='a' * 40, configured_models=dict(OPENAI_MODEL='m'), packages=dict(PyMuPDF='1')))
    return dict(
        ledger=dict(case_id='case', readings=[]),
        decision_coverage=dict(stored_total=2, in_export_total=2, sequence_gaps=[], changed_rows=1,
                               changed_rows_without_a_record=[]),
        judgement_calls=[dict(status='confirmed')],
        audit_chain_summary=dict(status='links_verified', event_count=3, head_sha256='f' * 64),
        selected_tracing=[dict(status='matching_calculations')],
        extraction_validation=dict(status='linked_independent_measurement', label_status='independently_reviewed'),
        processing_provenance=dict(
            runs=[run], readers=[dict(source_document_id='doc', layout_id='generic')],
            source_documents=[dict(id='doc', evidence_file_id='file', ingestion_run_id='run', parser_name='reader',
                                   parser_version='1', extraction_layer=1)],
            prepared_text=[dict(evidence_file_id='file', engine_job_id='job', extracted_at=EARLIER,
                processing_manifest=dict(sha256='e' * 64, content=dict(python_version='3.12', packages={},
                                                                       tesseract=dict(status='not_used'))))],
            custody_reports=[dict(events=[dict(id='received')])]))


class PacketMarkerTests(unittest.TestCase):
    def test_complete_only_when_all_four_parts_hold(self):
        status = packet_parts(whole_document())
        self.assertEqual(status['completeness'], COMPLETE)
        self.assertTrue(all(part['holds'] for part in status['parts']))
        self.assertIn('not an expert opinion', status['sentence'])

    def test_each_missing_part_alone_keeps_the_marker_and_is_named(self):
        def without(path, value):
            def change(document):
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
            return change
        breaks = dict(
            custody_and_decisions=[without(('processing_provenance', 'custody_reports'), [dict(events=[])]),
                without(('decision_coverage', 'in_export_total'), 1),
                without(('decision_coverage', 'changed_rows_without_a_record'), [dict(transaction_id='t')]),
                without(('decision_coverage', 'sequence_gaps'), [dict(subject_id='s')]),
                without(('audit_chain_summary',), dict(status='chain_gap'))],
            components=[without(('processing_provenance', 'runs'), []),
                without(('processing_provenance', 'readers'), []),
                without(('processing_provenance', 'prepared_text'), [])],
            validation=[without(('extraction_validation',), dict(status='no_independent_measurement')),
                without(('extraction_validation',), dict(status='linked_independent_measurement', label_status='synthetic_test'))],
            tracing=[without(('selected_tracing',), []), without(('selected_tracing',), [dict(status='saved_bytes_differ')])])
        for key, changes in breaks.items():
            for change in changes:
                with self.subTest(part=key):
                    document = whole_document()
                    change(document)
                    status = packet_parts(document)
                    self.assertEqual(status['completeness'], INCOMPLETE)
                    state = {part['key']: part['holds'] for part in status['parts']}
                    self.assertFalse(state[key])
                    self.assertIn(next(part['label'] for part in status['parts'] if part['key'] == key),
                                  status['sentence'].split('Incomplete:')[1])

    def test_an_old_capture_claims_nothing(self):
        status = packet_parts(dict(ledger=dict(case_id='case', readings=[])))
        self.assertEqual(status['completeness'], INCOMPLETE)
        self.assertEqual([part['holds'] for part in status['parts']], [False] * 4)
        self.assertIn('Complete: none', status['sentence'])

    def test_validation_gives_words_and_no_figure_for_a_lawyer(self):
        status = packet_parts(dict(ledger=dict(case_id='case', readings=[])))
        detail = next(part for part in status['parts'] if part['key'] == 'validation')['detail']
        self.assertEqual(detail, NO_MEASUREMENT)
        self.assertIn('No independently reviewed measurement', detail)
        self.assertNotRegex(detail, r'\d')

    def test_export_manifest_support_and_response_header_say_the_same(self):
        document = whole_document()
        document.update(export_ready=True, schema='loupe.financial.ledger_snapshot/3')
        support = build_expert_support(document, snapshot_sha256='s')
        self.assertEqual(support['completeness'], COMPLETE)
        document['extraction_validation'] = dict(status='no_independent_measurement', statement=NO_MEASUREMENT)
        support = build_expert_support(document, snapshot_sha256='s')
        self.assertEqual(support['completeness'], INCOMPLETE)
        self.assertEqual(support['validation']['statement'], NO_MEASUREMENT)
        self.assertIn('Measured validation', support['packet_sentence'])

    def test_header_is_ascii_with_size_parts_and_sentence(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(dict(expert_support=dict(completeness=INCOMPLETE,
                sentence='Not whole · yet', parts=[dict(label='Tracing', holds=False, detail='long')]))))
        header = archive_packet_header(stream.getvalue())
        self.assertTrue(header.isascii())
        value = json.loads(header)
        self.assertEqual(value['byte_count'], len(stream.getvalue()))
        self.assertEqual(value['parts'], [dict(label='Tracing', holds=False)])


class DecisionWordsTests(unittest.TestCase):
    def test_a_model_decision_is_never_a_person(self):
        record = dict(actor_name='Claude (for Neil Byrne)', actor_email='neil@example.com', by_machine=False,
                      actor_origin=dict(kind='model', model='Claude', **{'for': dict(name='Neil Byrne')}))
        self.assertEqual(made_by(record), 'Claude for Neil Byrne · not confirmed')

    def test_software_and_person(self):
        self.assertEqual(made_by(dict(actor_name='Loupe', by_machine=True)), 'Software')
        self.assertEqual(made_by(dict(actor_name='Ann Reviewer', by_machine=False)), 'Ann Reviewer (person)')

    def test_model_read_names_keep_their_label_in_the_support(self):
        reading = dict(row=dict(key='t', to_name='ANN', label_sources=dict(to_name=dict(source='model_reading',
            label='Read by Claude · not confirmed', origin=dict(citation=dict(page=3, source_document_id='d'))))),
            source=dict(id='d'))
        support = build_expert_support(dict(ledger=dict(case_id='case', readings=[reading])), snapshot_sha256='s')
        self.assertEqual(support['model_work']['names'][0]['label'], 'Read by Claude · not confirmed')


class ComponentTests(unittest.TestCase):
    def test_history_without_a_record_says_not_recorded_and_never_the_current_version(self):
        document = whole_document()
        document['processing_provenance']['runs'][0]['components'] = None
        document['processing_provenance']['readers'] = []
        row = component_rows(document)[0]
        self.assertEqual(row['saving']['commit'], NOT_RECORDED)
        self.assertEqual(row['reading']['layout'], NOT_RECORDED)
        self.assertEqual(row['models']['configured'], NOT_RECORDED)
        self.assertEqual(row['saving']['code_version'], '1.0.0+abc')
        self.assertNotIn(run_components()['code_version'], json.dumps(row))

    def test_text_prepared_again_after_saving_is_not_the_recorded_preparation(self):
        document = whole_document()
        document['processing_provenance']['prepared_text'][0]['extracted_at'] = '2026-03-01T00:00:00+00:00'
        row = component_rows(document)[0]
        self.assertEqual(row['preparation']['status'], 'prepared_again_later')
        self.assertFalse(next(part for part in packet_parts(document)['parts'] if part['key'] == 'components')['holds'])

    def test_run_components_are_stored_at_processing_time(self):
        with patch.dict(os.environ, dict(OPENAI_MODEL='model-at-the-time')):
            components = run_components()
        self.assertEqual(components['configured_models']['OPENAI_MODEL'], 'model-at-the-time')
        for key in ('commit', 'code_version', 'statement_reader', 'python_version', 'packages', 'recorded_at'):
            self.assertIn(key, components)
        with patch('services.financial.component_manifest._running_commit', side_effect=RuntimeError):
            self.assertIsNone(run_components()['commit'])


class ValidationTests(unittest.TestCase):
    def corpus(self, label):
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        self.addCleanup(os.unlink, handle.name)
        json.dump(dict(documents=[dict(source_sha256='a' * 64)]), handle)
        handle.close()
        patcher = patch.dict(os.environ, {expert_packet.VALIDATION_SETTING: handle.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        return patch('services.financial.extraction_evaluation.evaluate_extraction',
                     return_value=dict(label_status=label))

    def test_nothing_stored_is_stated_in_words(self):
        with patch.dict(os.environ, {expert_packet.VALIDATION_SETTING: ''}):
            value = capture_extraction_validation([])
        self.assertEqual(value, dict(status='no_independent_measurement', statement=NO_MEASUREMENT))

    def test_synthetic_labels_never_count(self):
        with self.corpus('synthetic_test'):
            self.assertEqual(capture_extraction_validation([])['status'], 'no_independent_measurement')

    def test_independent_labels_are_linked_with_overlap(self):
        with self.corpus('independently_reviewed'):
            value = capture_extraction_validation([dict(sha256_at_ingestion='a' * 64), dict(sha256_at_ingestion='b' * 64)])
        self.assertEqual(value['status'], 'linked_independent_measurement')
        self.assertEqual(value['source_overlap']['matching_source_sha256'], ['a' * 64])
        self.assertEqual(value['source_overlap']['unmeasured_source_sha256'], ['b' * 64])

    def test_unreadable_record_is_not_a_measurement(self):
        with patch.dict(os.environ, {expert_packet.VALIDATION_SETTING: '/no/such/file.json'}):
            value = capture_extraction_validation([])
        self.assertEqual(value['status'], 'measurement_unreadable')
        self.assertEqual(value['statement'], NO_MEASUREMENT)


class CapturedRecordsTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.LedgerSummaryTests()
        self.f.setUp()
        self.row, self.doc = self.f.add()

    def tearDown(self):
        self.f.tearDown()

    def captured(self, case_id=None):
        document = json.loads(capture_ledger_snapshot(self.f.db, case_id=self.f.case.id).content)
        document = _capture_history(self.f.db, document, case_id=case_id or self.f.case.id)
        document['processing_provenance'] = capture_processing_provenance(self.f.db, case_id=self.f.case.id,
                                                                          readings=document['ledger']['readings'])
        return capture_packet_records(self.f.db, document, case_id=self.f.case.id)

    def test_count_check_matches_the_store_and_finds_a_changed_row_without_a_record(self):
        from services.financial.quarantine_row import quarantine_case_row
        document = self.captured()
        self.assertEqual(document['decision_coverage']['changed_rows'], 0)
        other, _ = self.f.add(7)
        quarantine_case_row(self.f.db, case_id=self.f.case.id, transaction_id=other.id, actor=self.f.user, reason='Checked')
        document = self.captured()
        coverage = document['decision_coverage']
        self.assertEqual((coverage['stored_total'], coverage['in_export_total']), (1, 1))
        self.assertEqual(coverage['made_by'], dict(person=1))
        readings = document['ledger']['readings']
        for reading in readings:
            if reading['row']['key'] == str(self.row.id):
                reading['row']['label_sources'] = dict(to_name=dict(source='investigator'))
        checked = expert_packet.capture_decision_coverage(self.f.db, case_id=self.f.case.id,
            scopes=dict(transaction={self.row.id, other.id}), decisions=document['decisions'], readings=readings)
        self.assertEqual(checked['changed_rows_without_a_record'],
                         [dict(transaction_id=str(self.row.id), fields=['to_name'], superseded=False)])

    def test_a_dropped_decision_shows_in_the_count(self):
        from services.financial.quarantine_row import quarantine_case_row
        quarantine_case_row(self.f.db, case_id=self.f.case.id, transaction_id=self.row.id, actor=self.f.user, reason='Checked')
        document = self.captured()
        checked = expert_packet.capture_decision_coverage(self.f.db, case_id=self.f.case.id,
            scopes=dict(transaction={self.row.id}), decisions=[], readings=document['ledger']['readings'])
        self.assertEqual((checked['stored_total'], checked['in_export_total']), (1, 0))

    def judgement(self, subject_id, **changes):
        row = FinancialJudgement(**{**dict(id=uuid4(), case_id=self.f.case.id, subject_type='transaction', subject_id=subject_id,
            source_document_id=None, statement_period_id=None, rule_id='L1.glyph_cell', target_key='amount', reading='1',
            origin='processor', strength='proved', summary='Damaged money cell fixed', evidence={}, status='open',
            created_at=datetime.now(timezone.utc)), **changes})
        self.f.db.add(row)
        self.f.db.commit()
        return row

    def test_judgement_calls_of_captured_rows_are_carried_and_others_are_not(self):
        kept = self.judgement(self.row.id, origin='agent')
        self.judgement(uuid4())
        document = self.captured()
        self.assertEqual([item['id'] for item in document['judgement_calls']], [str(kept.id)])
        self.assertEqual(document['judgement_calls'][0]['origin'], 'agent')
        report = render_ledger_report(snapshot_of(document))
        self.assertIn('Judgement calls on these records', report)
        self.assertIn('Model · not confirmed', report)
        self.assertIn('Damaged money cell fixed', report)

    def test_audit_summary_reads_past_the_wider_history_limit_and_finds_a_gap(self):
        previous = '0' * 64
        for sequence in range(1, 4):
            entry = f'{sequence:064d}'
            self.f.db.add(FinancialAuditEvent(case_id=self.f.case.id, sequence=sequence, previous_sha256=previous,
                                              entry_sha256=entry, payload_text='{}'))
            previous = entry
        self.f.db.commit()
        with patch('services.financial.audit_chain.MAX_AUDIT_EVENTS', 1):
            summary = capture_audit_summary(self.f.db, case_id=self.f.case.id)
        self.assertEqual((summary['status'], summary['event_count'], summary['head_sha256']), ('links_verified', 3, previous))
        last = self.f.db.query(FinancialAuditEvent).filter_by(sequence=3).one()
        last.previous_sha256 = 'f' * 64
        self.f.db.commit()
        self.assertEqual(capture_audit_summary(self.f.db, case_id=self.f.case.id)['status'], 'chain_gap')

    def saved_trace(self, envelope):
        entry = WorkspaceEntry(id=uuid4(), case_id=self.f.case.id, entry_type='note', title='Deposit followed', body='',
            tags=['financial', 'saved-trace'], author_name='Ann Reviewer', author_email='ann@example.com')
        self.f.db.add(entry)
        self.f.db.flush()
        self.f.db.add(WorkspaceEntryLink(id=uuid4(), entry_id=entry.id, case_id=self.f.case.id, target_type='evidence',
            target_id=str(uuid4()), relationship_type='context',
            link_metadata=dict(schema='loupe.financial.saved_trace/1', envelope=envelope)))
        self.f.db.commit()
        return entry

    def test_no_saved_calculation_is_stated(self):
        self.assertEqual(self.captured()['selected_tracing'], [])
        status = packet_parts(self.captured())
        self.assertIn('No investigator has saved', next(p for p in status['parts'] if p['key'] == 'tracing')['detail'])

    def test_saved_calculation_carries_its_methods_and_parameters(self):
        scenario = json.dumps(dict(schema='loupe.financial.conditional_trace/1', inputs=dict(doctrines=['fifo'], opening_basis='Nil'),
                                   comparison=dict(results=dict(fifo=dict(left='1')))))
        self.saved_trace(dict(scenario_json=scenario, scenario_sha256=hashlib.sha256(scenario.encode()).hexdigest()))
        with patch('services.financial.trace_replay.replay_trace', return_value=dict(status='matching_calculations')):
            selected = capture_selected_tracing(self.f.db, case_id=self.f.case.id)
        self.assertEqual(selected[0]['methods'], ['fifo'])
        self.assertEqual(selected[0]['parameters']['opening_basis'], 'Nil')
        self.assertEqual(selected[0]['results'], dict(fifo=dict(left='1')))
        self.assertEqual(selected[0]['saved_by'], 'Ann Reviewer')

    def test_changed_saved_bytes_do_not_count_as_selected_tracing(self):
        self.saved_trace(dict(scenario_json='{}', scenario_sha256='0' * 64))
        selected = capture_selected_tracing(self.f.db, case_id=self.f.case.id)
        self.assertEqual(selected[0]['status'], 'saved_bytes_differ')

    def test_a_deleted_finding_is_not_a_selection(self):
        entry = self.saved_trace(dict(scenario_json='{}', scenario_sha256='0' * 64))
        entry.deleted_at = datetime.now(timezone.utc)
        self.f.db.commit()
        self.assertEqual(capture_selected_tracing(self.f.db, case_id=self.f.case.id), [])

    def test_recorded_components_and_prepared_text_reach_the_export(self):
        run = self.f.db.get(FinancialIngestionRun, self.doc.ingestion_run_id)
        run.config = dict(secret='private', components=dict(commit='b' * 40, configured_models=dict(OPENAI_MODEL='m')))
        self.f.db.commit()
        processing = self.captured()['processing_provenance']
        self.assertEqual(processing['runs'][0]['components']['commit'], 'b' * 40)
        self.assertNotIn('private', json.dumps(processing))

    def test_the_layout_comes_from_the_saved_reading(self):
        self.doc.metadata_ = dict(statement_import_statement_id='s', statement_import_original=dict(
            statement_choices=[dict(id='s', layout_id='capital-one-card')]))
        self.f.db.commit()
        self.assertEqual(self.captured()['processing_provenance']['readers'][0]['layout_id'], 'capital-one-card')

    def test_the_default_capture_has_no_packet_records_so_a_trace_fingerprint_survives_audit_writes(self):
        """Tracing compares this fingerprint between two reads; the audit head moves with any write in the case."""
        from services.financial import ledger_snapshot
        with patch('services.financial.ledger_snapshot._consistent_connection') as connection, \
                patch('services.financial.ledger_snapshot._in_consistent_read', return_value=True), \
                patch('sqlalchemy.orm.Session') as session, \
                patch('services.financial.expert_packet.capture_packet_records') as packet:
            session.return_value.__enter__.return_value = self.f.db
            connection.return_value.__enter__.return_value = SimpleNamespace()
            for wanted in (False, True):
                ledger_snapshot.capture_ledger_export(SimpleNamespace(), case_id=self.f.case.id, packet_records=wanted)
                self.assertEqual(packet.call_count, 1 if wanted else 0)

    def test_the_readable_report_states_each_part_in_present_tense(self):
        document = self.captured()
        report = render_ledger_report(snapshot_of(document))
        self.assertIn('Expert packet: what this export holds', report)
        self.assertIn('This export is not a complete expert packet.', report)
        self.assertIn('No independently reviewed measurement', report)

    def test_the_archive_manifest_carries_the_parts(self):
        document = self.captured()
        snapshot = snapshot_of(document)
        content = ledger_export_archive(LedgerExport(snapshot, '{"manifest":true}'))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['expert_support']['completeness'], INCOMPLETE)
        self.assertEqual([part['key'] for part in manifest['expert_support']['parts']],
                         ['custody_and_decisions', 'components', 'validation', 'tracing'])
        self.assertEqual(json.loads(archive_packet_header(content))['completeness'], INCOMPLETE)
