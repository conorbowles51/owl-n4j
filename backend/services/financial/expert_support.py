"""Inventory captured support for an expert, with explicit missing evidence.

This is a reproducible index into the exported snapshot, not a signed opinion or
an assertion of complete custody, independent validation, or admissibility.
"""
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
        source_records=dict(status='recorded_source_inventory',processing_records=document.get('processing_provenance'),sources=[sources[key] for key in sorted(sources)],
            fresh_byte_checks=[{key:value for key,value in item.items() if key!='content'} for item in source_files],
            limitation='Recorded ingestion source references and optional export-time byte checks do not establish every custody transfer. Complete custody event history is not captured here.'),
        human_decisions=dict(status='captured_scope' if document.get('export_ready') else 'unavailable',
            wider_case_financial_history=dict(status='included',snapshot_reference='case_financial_history',
                decision_count=len(document['case_financial_history']['decisions']),
                audit_chain_verification=(document['case_financial_history'].get('audit_chain') or {}).get('verification'),
                pdf_review_count=len(document['case_financial_history']['pdf_review_history']['reviews']),
                limitation=document['case_financial_history']['limitation']) if 'case_financial_history' in document else dict(status='not_selected'),
            recorded_decisions=len(document.get('decisions',[])),pdf_reviews=len(history['reviews']) if history else 0,
            scope=document.get('decision_scope'),snapshot_references=['decisions','pdf_review_history','ledger.readings'],
            limitation='Relevant captured ledger and PDF review decisions only; not all decisions or opinions in the case.'),
        versions=dict(export_code_version=code_version,
            pdf_processing_manifests=[dict(mapping_id=m['mapping_id'],manifest=m['processing_manifest']) for m in methods['methods'] if m.get('processing_manifest')] if methods else [],
            financial_processing_runs=(document.get("processing_provenance") or {}).get("runs"),
            source_parsers=[dict(source_document_id=key,parser_name=sources[key].get("parser_name"),parser_version=sources[key].get("parser_version")) for key in sorted(sources)],
            model_requests=[m for m in methods['methods'] if m['model']] if methods else [],
            limitation='Export code version and recorded PDF model requests are included. A complete historical component/toolchain manifest is unavailable.'),
        validation=dict(status='unavailable',
            reason='No versioned independently reviewed extraction evaluation is attached to this snapshot. Software test counts are not measured extraction accuracy.'),
        tracing=dict(status='not_selected',
            reason='This ledger export does not capture a tracing scenario. Export the selected scenario separately with its source readings, assumptions and method comparisons.'),
        completeness='incomplete_expert_packet')

    if imports is not None:
        from services.financial.pdf_candidates import _digest
        from services.financial.ledger_summary import LedgerSummaryError
        captured_imports = []
        for index, item in enumerate(imports):
            if (_digest(item['confirmation']) != item['confirmation_sha256']
                    or (item.get('original_sha256') is not None
                        and _digest(item['original']) != item['original_sha256'])):
                raise LedgerSummaryError('Statement import support does not match its recorded digest.')
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
        support['human_decisions']['snapshot_references'].append('processing_provenance.statement_import_history')

    case_custody = (document.get('case_financial_history') or {}).get('custody_reports')
    source_custody = (document.get('processing_provenance') or {}).get('custody_reports')
    if case_custody is not None or source_custody is not None:
        support['source_records']['case_custody_reports'] = case_custody
        support['source_records']['source_custody_reports'] = source_custody
        support['source_records']['limitation'] = ('Attributed custody reports are included where recorded; missing earlier history remains unknown. '
            'Recorded source hashes and optional fresh byte checks do not establish authenticity or all custody transfers.')
    return support
