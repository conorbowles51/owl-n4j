"""The expert packet's four parts: what one export holds, measured from that export.

The specification's packet has four parts: custody and decisions, the component and toolchain manifest, measured
validation, and the selected tracing methods. ``capture_packet_records`` reads what those parts need in the export's
own consistent read. ``packet_parts`` states, from the captured document alone, whether each part holds; the packet is
called complete only when all four do. Nothing here supplies a value history does not have: an unknown stays
"not recorded", and an absent measurement is said in words, never as a figure.
"""
import hashlib
import json
import os
from collections import Counter
from uuid import UUID

from sqlalchemy import func, select

from services.financial.ledger_summary import LedgerSummaryError

NOT_RECORDED = 'not recorded'
COMPLETE = 'complete_expert_packet'
INCOMPLETE = 'incomplete_expert_packet'
NO_MEASUREMENT = ('No independently reviewed measurement. Nobody independent has compared a sample of these readings '
    'with the original documents and recorded an error rate, so this packet gives no accuracy figure. The software\'s '
    'own tests are not such a measurement.')
VALIDATION_SETTING = 'FINANCIAL_EXTRACTION_VALIDATION_CORPUS'
_BATCH = 5000
_READER_BATCH = 100
_LABELS = dict(custody_and_decisions='Custody and decisions', components='Component and toolchain manifest',
    validation='Measured validation', tracing='Selected tracing methods')


def made_by(record):
    """Who or what made a recorded decision, in the words a reader sees."""
    origin = _origin(record)
    if origin.get('kind') == 'model':
        person = (origin.get('for') or {}).get('name') or 'a person'
        return f"{origin.get('model') or 'A model'} for {person} · not confirmed"
    if record.get('by_machine'):
        return 'Software'
    return f"{record.get('actor_name') or record.get('actor_email') or NOT_RECORDED} (person)"


def _origin(record):
    origin = record.get('actor_origin') or record.get('origin')
    return origin if isinstance(origin, dict) else {}


def _maker_kind(record):
    origin = _origin(record)
    return 'model' if origin.get('kind') == 'model' else 'software' if record.get('by_machine') else 'person'


def capture_judgement_calls(session, *, case_id, scopes):
    """Every call the reader or a model made on the captured rows, statements and periods, with its answer."""
    from postgres.models.financial_judgements import FinancialJudgement
    from services.financial.judgements import as_dict
    rows = session.scalars(select(FinancialJudgement).where(FinancialJudgement.case_id == case_id)
        .order_by(FinancialJudgement.created_at, FinancialJudgement.id))
    transactions, documents = scopes['transaction'], scopes['source_document']
    periods = scopes['statement_period']
    keep = ('id', 'subject_type', 'subject_id', 'source_document_id', 'statement_period_id', 'rule_id', 'rule_label',
            'target_key', 'origin', 'strength', 'summary', 'evidence', 'status', 'resolved_by', 'resolved_at',
            'resolution_reason', 'adjudication_id', 'created_at')
    result = []
    for row in rows:
        if (row.subject_id in transactions or row.source_document_id in documents
                or row.statement_period_id in periods):
            view = as_dict(row)
            result.append({key: view[key] for key in keep})
    return result


def capture_decision_coverage(session, *, case_id, scopes, decisions, readings):
    """Count check: the records in the export against the store, then each changed row against those records."""
    from postgres.models.financial import AdjudicationEvent as Event
    stored, gaps = {}, []
    for kind, ids in scopes.items():
        ordered = sorted(ids, key=str)
        stored[kind] = 0
        for offset in range(0, len(ordered), _BATCH):
            stored[kind] += session.scalar(select(func.count()).select_from(Event).where(Event.case_id == case_id,
                Event.subject_type == kind, Event.subject_id.in_(ordered[offset:offset + _BATCH])))
    captured = Counter(item['subject_type'] for item in decisions)
    sequences = {}
    for item in decisions:
        sequences.setdefault((item['subject_type'], item['subject_id']), []).append(item['subject_sequence'])
    for subject, values in sorted(sequences.items()):
        if sorted(values) != list(range(1, len(values) + 1)):
            gaps.append(dict(subject_type=subject[0], subject_id=subject[1], sequences=sorted(values)))
    decided = {item['subject_id'] for item in decisions if item['subject_type'] == 'transaction'}
    documents = {item['subject_id'] for item in decisions if item['subject_type'] == 'source_document'}
    unexplained, label_changes = [], []
    changed = 0
    for reading in readings:
        row = reading['row']
        history = reading.get('investigation_label_history') or []
        labelled = {field for entry in history if isinstance(entry, dict) for field in entry.get('after') or {}}
        label_changes.extend(dict(transaction_id=row['key'], ref_id=row.get('ref_id'), at=entry.get('at'),
            made_by=made_by(entry), before=entry.get('before'), after=entry.get('after'))
            for entry in history if isinstance(entry, dict))
        reasons = [field for field, source in (row.get('label_sources') or {}).items()
                   if (source or {}).get('source') in ('investigator', 'model_reading')]
        if reasons or reading.get('investigation_label_history') or row.get('superseded_by_id'):
            changed += 1
            # A replaced row can be replaced by a decision on its whole statement; a name or reading needs its own.
            whole_statement = bool(row.get('superseded_by_id')) and not reasons and row.get('source_document_id') in documents
            # A name or category change is recorded on the payment itself: who, when, from what, to what.
            on_the_payment = bool(history) and set(reasons) <= labelled
            if row['key'] not in decided and not whole_statement and not on_the_payment:
                unexplained.append(dict(transaction_id=row['key'], fields=reasons,
                                        superseded=bool(row.get('superseded_by_id'))))
    return dict(schema_version='loupe.financial.decision_coverage/1',
        by_subject=[dict(subject_type=kind, stored=stored[kind], in_export=captured.get(kind, 0)) for kind in sorted(stored)],
        stored_total=sum(stored.values()), in_export_total=len(decisions), sequence_gaps=gaps,
        made_by=dict(Counter(_maker_kind(item) for item in decisions)),
        corrections_without_original=sum(1 for item in decisions if item.get('before') is None and item.get('after') is not None),
        changed_rows=changed, changed_rows_without_a_record=unexplained, label_changes=label_changes)


def capture_audit_summary(session, *, case_id):
    """Links of the whole case chain, however long. Bytes are re-hashed only with the wider history export."""
    from postgres.models.financial_audit import FinancialAuditEvent as Event
    previous, count = '0' * 64, 0
    for sequence, before, entry in session.execute(select(Event.sequence, Event.previous_sha256, Event.entry_sha256)
            .where(Event.case_id == case_id).order_by(Event.sequence).execution_options(yield_per=5000)):
        count += 1
        if sequence != count or before != previous:
            return dict(status='chain_gap', event_count=count, head_sha256=None, first_gap_sequence=sequence, scope=_AUDIT_SCOPE)
        previous = entry
    return dict(status='links_verified' if count else 'no_recorded_events', event_count=count,
                head_sha256=previous if count else None, scope=_AUDIT_SCOPE)


_AUDIT_SCOPE = ('Every recorded event of the case, checked link by link at export. The events themselves are in the '
    'export only when the wider case history is selected; that option also re-hashes each event.')


def capture_selected_tracing(session, *, case_id):
    """The calculations investigators saved in Findings: their methods, parameters and results, re-run now."""
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services.financial.trace_replay import replay_trace
    links = session.execute(select(WorkspaceEntry, WorkspaceEntryLink).join(WorkspaceEntryLink,
        WorkspaceEntryLink.entry_id == WorkspaceEntry.id).where(WorkspaceEntry.case_id == case_id,
        WorkspaceEntry.deleted_at.is_(None)).order_by(WorkspaceEntry.created_at, WorkspaceEntry.id))
    selected = []
    for entry, link in links:
        metadata = link.link_metadata or {}
        if metadata.get('schema') != 'loupe.financial.saved_trace/1':
            continue
        envelope = metadata.get('envelope') or {}
        content = str(envelope.get('scenario_json') or '').encode('utf-8')
        item = dict(entry_id=str(entry.id), title=entry.title, saved_by=entry.author_name or entry.author_email or NOT_RECORDED,
            saved_at=entry.created_at.isoformat() if entry.created_at else None, actor_origin=entry.actor_origin,
            scenario_sha256=envelope.get('scenario_sha256'), scenario_byte_count=len(content))
        if hashlib.sha256(content).hexdigest() != envelope.get('scenario_sha256'):
            selected.append({**item, 'status': 'saved_bytes_differ'})
            continue
        try:
            replay = replay_trace(content)
        except LedgerSummaryError as error:
            selected.append({**item, 'status': 'cannot_recalculate', 'reason': str(error)})
            continue
        scenario = json.loads(content)
        selected.append({**item, 'status': replay['status'], 'schema': scenario['schema'],
            'methods': scenario['inputs'].get('doctrines'), 'parameters': scenario['inputs'],
            'results': scenario.get('comparison', {}).get('results') if 'comparison' in scenario else scenario.get('results'),
            'limitations': scenario.get('limitations')})
    return selected


def source_overlap(sources, corpus):
    """Compare recorded source digests only; do not infer extractor equivalence."""
    known = {source.get('sha256_at_ingestion') for source in sources if source.get('sha256_at_ingestion')}
    measured = {document['source_sha256'] for document in corpus['documents']}
    return dict(scope='selected_ledger_source_records',
        matching_source_sha256=sorted(known & measured),
        unmeasured_source_sha256=sorted(known - measured),
        sources_without_digest=sum(not source.get('sha256_at_ingestion') for source in sources),
        corpus_sources_not_selected=sorted(measured - known),
        extraction_version_equivalence='not_established',
        limitation='Recorded digest overlap does not establish that the case used the measured extraction version, settings or review process. Pending sources outside selected ledger readings are not covered by this comparison.')


def capture_extraction_validation(sources):
    """The stored evaluation linked to this export, recalculated from its corpus; only independent labels count."""
    path = os.environ.get(VALIDATION_SETTING)
    if not path:
        return dict(status='no_independent_measurement', statement=NO_MEASUREMENT)
    from services.financial.extraction_evaluation import evaluate_extraction
    try:
        with open(path, 'rb') as stored:
            content = stored.read()
        corpus = json.loads(content)
        measurement = evaluate_extraction(corpus)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return dict(status='measurement_unreadable', statement=NO_MEASUREMENT,
                    reason=f'The stored evaluation could not be read ({type(error).__name__}).')
    if measurement['label_status'] != 'independently_reviewed':
        return dict(status='no_independent_measurement', statement=NO_MEASUREMENT)
    return dict(status='linked_independent_measurement', corpus_sha256=hashlib.sha256(content).hexdigest(),
        label_status=measurement['label_status'], measurement=measurement, source_overlap=source_overlap(sources, corpus),
        limitation='These measurements describe the stored corpus. Reviewer independence and representativeness are declared inputs. No equivalence to the selected case documents or extraction versions is inferred.')


def _capture_component_records(session, document, *, case_id):
    """What each stage recorded when it ran: the run's components, the reading's layout, the prepared text's manifest."""
    from postgres.models.evidence import EvidenceDocumentText as Text
    from postgres.models.financial import FinancialIngestionRun as Run, FinancialSourceDocument as Source
    processing = document['processing_provenance']
    run_ids = [UUID(run['id']) for run in processing['runs']]
    document_ids = [UUID(item['id']) for item in processing['source_documents']]
    file_ids = sorted({UUID(item['evidence_file_id']) for item in processing['source_documents'] if item['evidence_file_id']}, key=str)
    configs = {}
    for offset in range(0, len(run_ids), _BATCH):
        configs.update((str(key), value) for key, value in session.execute(select(Run.id, Run.config).where(
            Run.case_id == case_id, Run.id.in_(run_ids[offset:offset + _BATCH]))))
    for run in processing['runs']:
        run['components'] = (configs.get(run['id']) or {}).get('components')
    readers, prepared = [], []
    for offset in range(0, len(document_ids), _READER_BATCH):
        # Only the two values the layout needs: the whole saved reading of a large case is gigabytes.
        for key, statement, choices in session.execute(select(Source.id, Source.metadata_['statement_import_statement_id'],
                Source.metadata_['statement_import_original']['statement_choices']).where(Source.case_id == case_id,
                Source.id.in_(document_ids[offset:offset + _READER_BATCH]))):
            readers.append(dict(source_document_id=str(key), **_reader(statement, choices)))
    for offset in range(0, len(file_ids), _BATCH):
        prepared.extend(dict(evidence_file_id=str(key), engine_job_id=str(job) if job else None,
            extracted_at=extracted.isoformat() if extracted else None, processing_manifest=manifest)
            for key, job, extracted, manifest in session.execute(select(Text.evidence_file_id, Text.engine_job_id,
                Text.extracted_at, Text.processing_manifest).where(Text.evidence_file_id.in_(file_ids[offset:offset + _BATCH]))))
    processing['readers'] = sorted(readers, key=lambda item: item['source_document_id'])
    processing['prepared_text'] = sorted(prepared, key=lambda item: item['evidence_file_id'])


def _reader(statement, choices):
    """The printed layout the saved reading was made with, as that reading recorded it."""
    choices = [item for item in choices or [] if isinstance(item, dict)]
    chosen = next((item for item in choices if item.get('id') == statement), choices[0] if len(choices) == 1 else None)
    return dict(layout_id=(chosen or {}).get('layout_id'))


def capture_packet_records(session, document, *, case_id):
    readings = document['ledger']['readings']
    scopes = {kind: {UUID(value) for value in values} for kind, values in document['decision_scope'].items()}
    _capture_component_records(session, document, case_id=case_id)
    document['judgement_calls'] = capture_judgement_calls(session, case_id=case_id, scopes=scopes)
    document['decision_coverage'] = capture_decision_coverage(session, case_id=case_id, scopes=scopes,
        decisions=document['decisions'], readings=readings)
    document['audit_chain_summary'] = capture_audit_summary(session, case_id=case_id)
    document['selected_tracing'] = capture_selected_tracing(session, case_id=case_id)
    sources = {reading['source']['id']: reading['source'] for reading in readings}
    document['extraction_validation'] = capture_extraction_validation([sources[key] for key in sorted(sources)])
    return document


def component_rows(document):
    """One row per statement in the export: each stage's versions as recorded, or "not recorded"."""
    processing = document.get('processing_provenance') or {}
    runs = {run['id']: run for run in processing.get('runs') or []}
    readers = {item['source_document_id']: item for item in processing.get('readers') or []}
    prepared = {item['evidence_file_id']: item for item in processing.get('prepared_text') or []}
    files = {item['id']: item for item in processing.get('source_documents') or []}
    rows = []
    for key in sorted(files):
        document_row = files[key]
        run = runs.get(document_row.get('ingestion_run_id')) or {}
        components = run.get('components') or {}
        text = prepared.get(document_row.get('evidence_file_id')) or {}
        manifest = text.get('processing_manifest') or {}
        content = manifest.get('content') if isinstance(manifest.get('content'), dict) else None
        started, extracted = run.get('started_at'), text.get('extracted_at')
        # Text prepared again after this reading was saved is a later preparation, not the one the reading used.
        current = content is not None and bool(started and extracted and extracted <= started)
        reader = readers.get(key) or {}
        rows.append(dict(source_document_id=key,
            preparation=dict(status='recorded' if current else 'prepared_again_later' if content else NOT_RECORDED,
                prepared_at=extracted if content else NOT_RECORDED, engine_job_id=text.get('engine_job_id') or NOT_RECORDED,
                manifest_sha256=manifest.get('sha256') or NOT_RECORDED,
                python=(content or {}).get('python_version') or NOT_RECORDED,
                packages=(content or {}).get('packages') or NOT_RECORDED,
                tesseract=((content or {}).get('tesseract') or {}).get('status') or NOT_RECORDED),
            reading=dict(reader=document_row.get('parser_name') or NOT_RECORDED,
                version=document_row.get('parser_version') or NOT_RECORDED,
                layer=document_row.get('extraction_layer') or NOT_RECORDED,
                layout=reader.get('layout_id') or NOT_RECORDED),
            saving=dict(run_id=run.get('id') or NOT_RECORDED, code_version=run.get('code_version') or NOT_RECORDED,
                commit=components.get('commit') or NOT_RECORDED, ruleset=run.get('ruleset_version') or NOT_RECORDED),
            models=dict(configured=components.get('configured_models') or NOT_RECORDED,
                packages=components.get('packages') or NOT_RECORDED)))
    return rows


def _component_holes(rows):
    holes = Counter()
    for row in rows:
        if row['preparation']['status'] != 'recorded':
            holes['text preparation'] += 1
        if NOT_RECORDED in (row['reading']['version'], row['reading']['layout']):
            holes['reader or layout version'] += 1
        if row['saving']['commit'] == NOT_RECORDED or row['saving']['code_version'] == NOT_RECORDED:
            holes['exact code commit'] += 1
        if row['models']['configured'] == NOT_RECORDED:
            holes['models'] += 1
    return holes


def _custody_part(document):
    coverage = document.get('decision_coverage')
    processing = document.get('processing_provenance') or {}
    if coverage is None:
        return False, 'Not captured in this snapshot.'
    reports = processing.get('custody_reports') or []
    reported = sum(bool(item.get('events')) for item in reports)
    missing = coverage['stored_total'] - coverage['in_export_total']
    unexplained = len(coverage['changed_rows_without_a_record'])
    audit = document.get('audit_chain_summary') or {}
    judgements = document.get('judgement_calls') or []
    unanswered = sum(item['status'] == 'open' for item in judgements)
    holds = (missing == 0 and not coverage['sequence_gaps'] and not unexplained and bool(reports)
             and reported == len(reports) and audit.get('status') == 'links_verified')
    words = [f"{coverage['in_export_total']} of {coverage['stored_total']} recorded decisions are in the export",
        f"{coverage['changed_rows'] - unexplained} of {coverage['changed_rows']} changed payments have their decision record",
        f"{len(judgements)} judgement calls by the reader or a model are listed, {unanswered} not yet answered by a person",
        f"{reported} of {len(reports)} source files have a recorded custody report",
        f"the case audit chain has {audit.get('event_count', 0)} events ({audit.get('status', NOT_RECORDED).replace('_', ' ')})"]
    return holds, '; '.join(words) + '.'


def _components_part(document):
    rows = component_rows(document)
    if not rows:
        return False, 'No processing records in this export.', rows
    holes = _component_holes(rows)
    if not holes:
        return True, f'Every stage of all {len(rows)} statements is recorded.', rows
    return False, f'{len(rows)} statements listed. Not recorded: ' + ', '.join(
        f'{name} for {count}' for name, count in sorted(holes.items())) + '.', rows


def _validation_part(validation):
    if (validation or {}).get('status') in ('linked_independent_measurement', 'reconciled_reference_measurement_context',
                                            'supplied_measurement_context') \
            and validation.get('label_status') == 'independently_reviewed':
        return True, 'Linked to an independently reviewed measurement; it describes its own corpus.'
    return False, NO_MEASUREMENT


def _tracing_part(document, override=None):
    if override is not None:
        return True, 'The selected scenario, its methods and its recalculation are in this package.'
    selected = document.get('selected_tracing')
    if selected is None:
        return False, 'Not captured in this snapshot.'
    if not selected:
        return False, 'No investigator has saved a tracing calculation in this case.'
    matching = sum(item['status'] == 'matching_calculations' for item in selected)
    words = f'{len(selected)} saved calculations with their methods and parameters; {matching} recalculate to the saved result.'
    return matching == len(selected), words


def packet_parts(document, *, validation=None, tracing=None):
    """Each part, whether it holds, and the marker. A marker of complete needs all four."""
    custody, custody_words = _custody_part(document)
    components, component_words, _ = _components_part(document)
    measured, measured_words = _validation_part(validation or document.get('extraction_validation'))
    traced, traced_words = _tracing_part(document, tracing)
    parts = [dict(key=key, label=_LABELS[key], holds=holds, status='complete' if holds else 'incomplete', detail=detail)
             for key, holds, detail in (('custody_and_decisions', custody, custody_words),
                 ('components', components, component_words), ('validation', measured, measured_words),
                 ('tracing', traced, traced_words))]
    return dict(completeness=COMPLETE if all(part['holds'] for part in parts) else INCOMPLETE, parts=parts,
                sentence=packet_sentence(parts))


def packet_sentence(parts):
    complete = [part['label'] for part in parts if part['holds']]
    missing = [part['label'] for part in parts if not part['holds']]
    if not missing:
        return 'All four parts of the expert packet hold for this export. This is not an expert opinion, signature or legal admissibility determination.'
    return ('This export is not a complete expert packet. Complete: ' + (', '.join(complete) or 'none')
            + '. Incomplete: ' + ', '.join(missing) + '.')


def packet_header(status, *, byte_count):
    """The parts as the download's response header: ASCII JSON, short enough for any proxy."""
    return json.dumps(dict(completeness=status['completeness'], byte_count=byte_count, sentence=status['sentence'],
        parts=[dict(label=part['label'], holds=part['holds']) for part in status['parts']]),
        ensure_ascii=True, separators=(',', ':'))


def archive_packet_header(content):
    """The response header for a built ledger archive, read from the archive's own manifest."""
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        support = json.loads(archive.read('manifest.json'))['expert_support']
    return packet_header(dict(completeness=support['completeness'], parts=support['parts'], sentence=support['sentence']),
                         byte_count=len(content))
