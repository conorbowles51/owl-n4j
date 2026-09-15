"""Capture automatic statement proposals for an offline extraction comparison.

Reads already prepared PDFs in a repeatable, read-only database transaction.
Does not import payments, run OCR, call a model or generate reference labels.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.statement_import_proposal import VERSION
from services.financial.extraction_evaluation import EvaluationDocument


def document_predictions(proposals, source_sha256):
    rows = {}
    for proposal in proposals:
        if proposal.get('document_review'):
            continue
        for row in proposal['rows']:
            if row['excluded']:
                continue
            source_id = f"page-{row['page_number']:04d}/table-{row['table_index']:03d}/row-{row['row_index']:04d}"
            fields = {key: row['fields'][key] for key in ('date', 'amount_minor', 'direction')
                      if row['fields'].get(key) not in (None, '')}
            if proposal.get('currency'):
                fields['currency'] = proposal['currency']
            if proposal['metadata'].get('account_number'):
                fields['account'] = proposal['metadata']['account_number']
            if not fields:
                raise ValueError('An unclassified proposed row has no measurable fields. Retain it for explicit review.')
            value = dict(source_id=source_id, fields=fields, admitted=False)
            if source_id in rows and rows[source_id] != value:
                raise ValueError('A source row has conflicting account/statement proposals. Resolve its evaluation scope explicitly.')
            rows[source_id] = value
    document = EvaluationDocument.model_validate(dict(source_sha256=source_sha256,
        extraction_layer='template', extractor_version=VERSION,
        truth=[], predictions=[rows[key] for key in sorted(rows)], proof_class='p3',
        balance_gate='unavailable', quarantined=False)).model_dump(mode='json')
    document.pop('truth')
    return document


def capture(session, inventory):
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from services.financial.statement_import import read_statement_import
    from services.financial.pdf_candidates import _digest
    if not 1 <= len(inventory['sources']) <= 1000:
        raise ValueError('Select between one and 1,000 sources.')
    from pydantic import TypeAdapter
    from services.financial.extraction_evaluation import Identifier
    for key in ('corpus_id', 'corpus_version'):
        TypeAdapter(Identifier).validate_python(inventory[key])
    documents, captures, seen = [], [], set()
    for item in inventory['sources']:
        case_id, file_id = UUID(item['case_id']), UUID(item['evidence_file_id'])
        source = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == case_id))
        if source is None or source.sha256 != item['source_sha256']:
            raise ValueError('A selected source is missing or differs from the retained source digest.')
        if source.sha256 in seen:
            raise ValueError('Select each unique original PDF once.')
        seen.add(source.sha256)
        initial = read_statement_import(session, case_id=case_id, evidence_file_id=file_id, currency=item['currency'])
        choices = initial.get('statement_choices', [])
        proposals = [read_statement_import(session, case_id=case_id, evidence_file_id=file_id,
                     currency=item['currency'], statement_id=choice['id']) for choice in choices] if choices else [initial]
        # current_import describes case activity, not the automatic reader output.
        for proposal in proposals:
            proposal.pop('current_import', None)
        capture_digest = _digest(proposals)
        if item.get('expected_proposals_sha256') and item['expected_proposals_sha256'] != capture_digest:
            raise ValueError('Prepared readings or reader outputs differ from this run inventory. Keep the previous capture and review the change.')
        documents.append(document_predictions(proposals, source.sha256))
        captures.append(dict(source_sha256=source.sha256, proposals_sha256=capture_digest, proposals=proposals))
    if not documents:
        raise ValueError('Select at least one prepared source PDF.')
    predictions = dict(schema_version='loupe.extraction_predictions/1', corpus_id=inventory['corpus_id'],
                       corpus_version=inventory['corpus_version'], documents=documents)
    return predictions, captures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--database-url-env', default='LOUPE_VALIDATION_DATABASE_URL')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory must be new.')
    database_url = os.environ.get(args.database_url_env)
    if not database_url:
        parser.error('The selected database URL environment variable is unavailable.')
    inventory = json.loads(args.inventory.read_text())
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine(database_url, isolation_level='REPEATABLE READ')
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            with connection.begin(), Session(bind=connection) as session:
                predictions, captures = capture(session, inventory)
    finally:
        engine.dispose()
    # Serialize everything before creating the destination; never print credentials.
    values = {'predictions.json': predictions, 'captured-proposals.json': captures, 'input-inventory.json': inventory}
    serialized = {name: (json.dumps(value, indent=2, sort_keys=True) + '\n').encode() for name, value in values.items()}
    manifest = dict(schema_version='loupe.statement_prediction_capture/1', reader_version=VERSION,
        source_count=len(captures), reference_review_status='not_supplied', original_bytes_checked=False,
        files=[dict(path=name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()) for name, content in serialized.items()],
        limitation='Automatic proposals from retained prepared PDFs, not independently reviewed truth or new PDF/OCR extraction. All rows remain unadmitted. Quarantined is false because this runner performs no admission or quarantine step; balance-gate results are unavailable. Row addresses refer to this captured preparation; changed geometry needs reviewed alignment before a comparison. Caller-supplied currency context is retained in the input inventory.')
    args.output.mkdir()
    for name, content in serialized.items():
        (args.output / name).write_bytes(content)
    (args.output / 'capture-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(f'Captured {len(captures)} prepared sources using {VERSION}. No payments imported and no reference labels generated.')


if __name__ == '__main__':
    main()
