"""Inventory captured support for an expert, with explicit missing evidence.

This is a reproducible index into the exported snapshot, not a signed opinion or
an assertion of admissibility. Its marker says whether all four parts of the expert
packet hold for this export (services.financial.expert_packet).
"""
from services.financial.expert_packet import NO_MEASUREMENT, component_rows, made_by, packet_parts
from services.financial.review_methods import pdf_review_methods


def build_expert_support(document, *, snapshot_sha256, code_version=None, source_files=()):
    sources={}
    for reading in document['ledger']['readings']:
        source=reading['source']
        if source['id'] in sources and sources[source['id']]!=source:
            from services.financial.ledger_summary import LedgerSummaryError
            raise LedgerSummaryError('Conflicting source records in expert support inventory.')
        sources[source['id']]=source
    history=document.get('pdf_review_history')
    methods=pdf_review_methods(document)
    processing = document.get('processing_provenance') or {}
    imports = processing.get('statement_import_history')
    support = dict(schema_version='loupe.financial.expert_support/1',
        derived_from_sha256=snapshot_sha256,
        case_id=document['ledger']['case_id'],preparation=document.get('export_context'),
        purpose='Preparation support for expert review. Not an expert opinion, signature, complete custody certification or legal admissibility determination.',
        extraction_and_review=dict(status='captured_pdf_scope' if methods is not None else 'unavailable',description=methods,
            snapshot_reference='pdf_review_history.mappings'),
        source_records=dict(status='recorded_source_inventory',processing_records=_processing_index(document),
            audit_chain=document.get('audit_chain_summary'),sources=[sources[key] for key in sorted(sources)],
            fresh_byte_checks=[{key:value for key,value in item.items() if key!='content'} for item in source_files],
            limitation='Recorded ingestion source references and optional export-time byte checks do not establish every custody transfer. Complete custody event history is not captured here.'),
        human_decisions=dict(status='captured_scope' if document.get('export_ready') else 'unavailable',
            wider_case_financial_history=dict(status='included',snapshot_reference='case_financial_history',
                decision_count=len(document['case_financial_history']['decisions']),
                audit_chain_verification=(document['case_financial_history'].get('audit_chain') or {}).get('verification'),
                pdf_review_count=len(document['case_financial_history']['pdf_review_history']['reviews']),
                limitation=document['case_financial_history']['limitation']) if 'case_financial_history' in document else dict(status='not_selected'),
            recorded_decisions=len(document.get('decisions',[])),pdf_reviews=len(history['reviews']) if history else 0,
            coverage=document.get('decision_coverage'),
            made_by=[dict(id=item['id'],subject_type=item['subject_type'],subject_id=item['subject_id'],decision=item['decision'],
                made_by=made_by(item)) for item in document.get('decisions',[])],
            judgement_calls=dict(count=len(document.get('judgement_calls') or []),snapshot_reference='judgement_calls',
                not_answered=sum(item['status']=='open' for item in document.get('judgement_calls') or [])),
            scope=document.get('decision_scope'),snapshot_references=['decisions','judgement_calls','pdf_review_history','ledger.readings'],
            limitation='Decisions and judgement calls on the captured rows, their accounts, statements, periods and files. Decisions on other subjects are in the wider case history only.'),
        versions=dict(export_code_version=code_version,
            pdf_processing_manifests=[dict(mapping_id=m['mapping_id'],manifest=m['processing_manifest']) for m in methods['methods'] if m.get('processing_manifest')] if methods else [],
            financial_processing_runs=(document.get("processing_provenance") or {}).get("runs"),
            source_parsers=[dict(source_document_id=key,parser_name=sources[key].get("parser_name"),parser_version=sources[key].get("parser_version")) for key in sorted(sources)],
            model_requests=[m for m in methods['methods'] if m['model']] if methods else [],
            components=component_rows(document),
            limitation='Each stage shows the versions recorded when it ran. "not recorded" means history does not hold that fact; current versions are never used in its place. Models are configured names, not proof of a fixed provider revision.'),
        validation=_validation(document),
        tracing=_tracing(document),
        model_work=model_work_inventory(document))

    if imports is not None:
        from services.financial.pdf_candidates import _digest
        from services.financial.ledger_summary import LedgerSummaryError
        captured_imports = []
        processing_records = []
        for index, item in enumerate(imports):
            if (_digest(item['confirmation']) != item['confirmation_sha256']
                    or (item.get('original_sha256') is not None
                        and _digest(item['original']) != item['original_sha256'])):
                raise LedgerSummaryError('Statement import support does not match its recorded digest.')
            from services.financial.pdf_processing_manifest import validate_pdf_processing_manifest
            for source_index, source in enumerate(item['original'].get('sources', [])):
                try:
                    manifest = validate_pdf_processing_manifest(source.get('processing_manifest'))
                except (TypeError, ValueError) as exc:
                    raise LedgerSummaryError('Statement PDF processing record is inconsistent; report refused.') from exc
                processing_records.append(dict(source_document_id=item['source_document_id'],
                    page_number=source.get('page_number'), table_index=source.get('table_index'),
                    status='captured' if manifest is not None else 'not_recorded',
                    manifest=manifest,
                    snapshot_reference=f'processing_provenance.statement_import_history[{index}].original.sources[{source_index}].processing_manifest'))
            captured_imports.append(dict(
                source_document_id=item['source_document_id'], evidence_file_id=item['evidence_file_id'],
                original_sha256=item.get('original_sha256'),
                confirmation_sha256=item['confirmation_sha256'],
                snapshot_reference=f'processing_provenance.statement_import_history[{index}]'))
        support['extraction_and_review']['statement_imports'] = dict(
            status='captured_scope', count=len(captured_imports), records=captured_imports,
            procedure='Each referenced record retains the original statement proposal and the confirmed import, including recorded corrections and exclusions. Subsequent transaction changes are retained in the decision history.',
            limitation='A missing original digest remains unknown. Confirmation records an investigator decision, not independent extraction accuracy.')
        if captured_imports and methods is None:
            support['extraction_and_review']['status'] = 'captured_statement_import_scope'
        support['human_decisions']['statement_import_confirmations'] = len(captured_imports)
        support['versions']['statement_pdf_processing_records'] = processing_records
        support['human_decisions']['snapshot_references'].append('processing_provenance.statement_import_history')

    case_custody = (document.get('case_financial_history') or {}).get('custody_reports')
    source_custody = (document.get('processing_provenance') or {}).get('custody_reports')
    if case_custody is not None or source_custody is not None:
        support['source_records']['case_custody_reports'] = case_custody
        support['source_records']['source_custody_reports'] = source_custody
        support['source_records']['limitation'] = ('Attributed custody reports are included where recorded; missing earlier history remains unknown. '
            'Recorded source hashes and optional fresh byte checks do not establish authenticity or all custody transfers.')
    status = packet_parts(document)
    support.update(completeness=status['completeness'], packet_parts=status['parts'], packet_sentence=status['sentence'])
    return support


def _processing_index(document):
    """The processing records without the statement readings, which the snapshot holds once."""
    processing = document.get('processing_provenance')
    if processing is None:
        return None
    return {**{key: value for key, value in processing.items() if key not in ('statement_import_history', 'prepared_text')},
            'statement_import_history_reference': 'processing_provenance.statement_import_history',
            'prepared_text_reference': 'processing_provenance.prepared_text'}


def _validation(document):
    validation = document.get('extraction_validation')
    if validation is None:
        return dict(status='unavailable', reason=NO_MEASUREMENT)
    return validation


def _tracing(document):
    selected = document.get('selected_tracing')
    if selected is None:
        return dict(status='not_captured', reason='This snapshot does not record the case\'s saved tracing calculations.')
    if not selected:
        return dict(status='none_saved', reason='No investigator has saved a tracing calculation in this case.')
    return dict(status='saved_calculations', count=len(selected), selected=selected,
        snapshot_reference='selected_tracing',
        limitation='The methods and parameters the investigators chose, re-run at export. Only selected methods and recorded assumptions; no legal applicability or verified-attribution finding.')


def model_work_inventory(document):
    """Work Claude did for a person in the captured rows that no person has confirmed: names it read and payments
    it saved to the case. Listed as a limitation: a model's reading is not a person's until a person confirms it."""
    names, saved, statements, confirmed_names = [], [], set(), 0
    for reading in document['ledger']['readings']:
        row = reading.get('row') or {}
        for field in ('from_name', 'to_name'):
            source = ((row.get('label_sources') or {}).get(field) or {})
            if source.get('source') == 'model_reading':
                cited = (source.get('origin') or {}).get('citation') or {}
                names.append(dict(transaction_id=row.get('key'), field=field, value=row.get(field),
                                  label=source.get('label') or 'Read by Claude · not confirmed',
                                  page=cited.get('page'), source_document_id=cited.get('source_document_id')))
            elif source.get('confirmed_model_reading'):
                confirmed_names += 1
        work = reading.get('model_work') or {}
        if work and work.get('statement_status') == 'not_confirmed':
            saved.append(row.get('key'))
            statements.add((reading.get('source') or {}).get('id'))
    limitation = ('Work Claude did for a person, not yet confirmed by a person: '
                  f'{len(names)} names read from the cited pages and {len(saved)} payments in {len(statements)} '
                  'statements saved to the case. They are shown as Claude\'s, with their citations, and are not a '
                  'person\'s reading until a person confirms them.')
    return dict(status='listed', unconfirmed_names=len(names), unconfirmed_saved_payments=len(saved),
                unconfirmed_statements=len(statements), confirmed_names=confirmed_names, names=names,
                saved_payment_ids=saved, limitation=limitation)
