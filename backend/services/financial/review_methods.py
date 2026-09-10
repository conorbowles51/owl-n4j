"""Describe recorded PDF review methods without claiming measured accuracy."""
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.pdf_candidates import _digest


def pdf_review_methods(document):
    history = document.get('pdf_review_history')
    if history is None:
        return None
    methods = []
    for mapping in history['mappings']:
        snapshot = mapping['snapshot']
        if _digest(snapshot) != mapping['snapshot_sha256']:
            raise LedgerSummaryError('PDF method history does not match its stored digest.')
        proposal = snapshot['proposal']
        nomination = snapshot.get('nomination_snapshot')
        model = None
        if nomination:
            request = nomination['request']
            if (_digest(request) != nomination['request_sha256']
                    or nomination['id'] != proposal.get('nomination_id')
                    or nomination['case_id'] != proposal['case_id']
                    or nomination['evidence_file_id'] != proposal['evidence_file_id']
                    or request['source_revision'] != proposal['source_revision']):
                raise LedgerSummaryError('PDF model provenance is inconsistent; report refused.')
            model = {key: request[key] for key in ('provider', 'model_id', 'schema_version', 'execution_mode', 'prompt_sha256')}
            model['attempt_id'] = nomination['id']
            model['created_at'] = nomination['created_at']
            transport = (nomination.get('result') or {}).get('transport')
            model['transport_status'] = transport.get('status', 'unavailable') if transport else 'not_recorded'
            if transport:
                model['adapter_runtime'] = transport.get('adapter_runtime')
            if transport and transport.get('status') == 'captured':
                import hashlib
                import json
                arguments = transport.get('request_arguments')
                encoded = json.dumps(arguments, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
                if not isinstance(arguments, dict) or hashlib.sha256(encoded).hexdigest() != transport.get('request_arguments_sha256'):
                    raise LedgerSummaryError('Recorded provider request arguments do not match their digest.')
                model['provider_reported_model'] = transport.get('response_metadata', {}).get('reported_model')
                model['provider_response_id'] = transport.get('response_metadata', {}).get('response_id')
                model['request_arguments_sha256'] = transport['request_arguments_sha256']
                model['adapter_sha256'] = transport.get('adapter_sha256')
        methods.append(dict(mapping_id=mapping['id'], evidence_file_id=mapping['evidence_file_id'],
            source_revision=proposal['source_revision'], schema_version=proposal['schema_version'],
            model=model))
    return dict(methods=methods,
        procedure='Stored PDF text and source locations are bound to saved readings. Investigators record review decisions separately. Model proposals, when present, select existing cells and do not establish financial accuracy or admit transactions.',
        validation='No measured extraction error rate or independently adjudicated evaluation corpus is included in this snapshot. Automated software test counts are not an extraction accuracy measurement.',
        scope='This appendix describes saved PDF mappings for the referenced source files. It is not a complete case custody record, expert opinion, or record of every software component.')
