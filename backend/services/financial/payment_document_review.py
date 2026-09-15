"""Save a checked payment document as a finding without changing ledger totals."""
import hashlib
import re
from datetime import date
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, or_
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from postgres.models.workspace_entry import WorkspaceEntry
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.candidate_sources import read_candidate_source
from services.financial.payment_document_proposal import propose_payment_document, SCHEMA
from services.financial.statement_import_proposal import exact_amount
from services.financial.money import MoneyError


def payment_document_response(file, sources, *, case_id, document_id=None):
    if document_id:
        from services.financial.deposit_receipt_proposal import propose_deposit_receipt
        matches = [p for source in sources if (p := propose_deposit_receipt(source)) and p['document_id'] == document_id]
        proposal = matches[0] if len(matches) == 1 else None
    else:
        proposal = propose_payment_document(sources)
    if proposal is None:
        return None
    proposal.update(case_id=str(case_id), evidence_file_id=str(file.id), filename=file.original_filename,
                    file_sha256=file.sha256)
    proposal['revision'] = _digest(proposal)
    return proposal


def read_payment_document(session, *, case_id, evidence_file_id, document_id=None):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Document not found in this case.', 404)
    pages = list(session.scalars(select(EvidenceTableGeometry).where(
        EvidenceTableGeometry.evidence_file_id == file.id).order_by(EvidenceTableGeometry.page_number)))
    if not pages or len(pages) > 500:
        raise PdfMappingError('Prepare the PDF before reviewing its payment details.', 409)
    sources = [read_candidate_source(session, case_id=case_id, evidence_file_id=file.id,
        page_number=p.page_number, table_index=index) for p in pages for index in range(len(p.payload or []))]
    proposal = payment_document_response(file, sources, case_id=case_id, document_id=document_id)
    if proposal is None or not proposal['supported']:
        raise PdfMappingError('This selection is not a supported payment document.', 422)
    return proposal


class PaymentMatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: str = Field(max_length=100)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    value_date: date


def _match_conditions(case_id, request, *, direction=None):
    try:
        minor = int(exact_amount(request.amount, request.currency))
    except (ValueError, MoneyError) as exc:
        raise PdfMappingError('Check the amount and currency before finding payments.', 422) from exc
    if minor < 0:
        raise PdfMappingError('Enter a positive payment amount.', 422)
    start = date.fromordinal(max(date.min.toordinal(), request.value_date.toordinal() - 3))
    end = date.fromordinal(min(date.max.toordinal(), request.value_date.toordinal() + 3))
    return ((FinancialTransaction.direction == direction,) if direction else ()) + (FinancialTransaction.case_id == case_id,
        FinancialTransaction.ledger_status == 'admitted', FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.status == 'admitted', FinancialTransaction.currency == request.currency,
        FinancialTransaction.amount_minor == minor,
        or_(*(column.between(start, end) for column in (FinancialTransaction.transaction_date,
            FinancialTransaction.posted_date, FinancialTransaction.value_date, FinancialTransaction.effective_date))))


def matching_payments(session, *, case_id, request, direction=None):
    from services.financial.ledger_source import ledger_source
    request = PaymentMatchRequest.model_validate(request)
    rows = list(session.scalars(select(FinancialTransaction).join(FinancialSourceDocument,
        FinancialTransaction.source_document_id == FinancialSourceDocument.id).where(*_match_conditions(case_id, request, direction=direction))
        .order_by(FinancialTransaction.ordering_date, FinancialTransaction.id).limit(26)))
    candidates = []
    for row in rows[:25]:
        source = ledger_source(session, case_id=case_id, transaction_id=row.id)
        candidates.append(dict(transaction_id=str(row.id), transaction=source['transaction'],
            filename=source['filename'], revision=_digest(source)))
    return dict(case_id=str(case_id), candidates=candidates, more_matches=len(rows)>25,
        explanation='Same currency and amount, with a recorded payment date within three days. Check both sources before choosing a payment.')


class PaymentDocumentReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    document_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=1, max_length=200)
    values: dict[str, str]
    reasons: dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default='', max_length=8000)
    transaction_id: UUID | None = None
    transaction_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    link_reason: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def bounded(self):
        if not self.title.strip() or len(self.values)>20 or len(self.reasons)>20:
            raise ValueError('Enter a title and only the document fields shown in this review.')
        if any(len(k)>60 or len(v)>2000 for fields in (self.values,self.reasons) for k,v in fields.items()):
            raise ValueError('A document field or correction reason is too long.')
        if bool(self.transaction_id) != bool(self.transaction_revision) or self.transaction_id and not self.link_reason.strip():
            raise ValueError('Explain the payment link and include the selected payment revision.')
        return self


def save_payment_document(session, *, case_id, evidence_file_id, request, user, resolve_path):
    from services.financial.ledger_source import ledger_source
    from services.workspace_entry_service import create_entry
    request = PaymentDocumentReviewRequest.model_validate(request)
    digest = _digest(request.model_dump(mode='json', exclude={'document_id'} if request.document_id is None else set()))
    identifier = uuid5(NAMESPACE_URL, f'loupe-wire-review:{case_id}:{evidence_file_id}:{request.request_id}')
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update())
    if file is None:
        raise PdfMappingError('Document not found in this case.', 404)
    existing = session.get(WorkspaceEntry, identifier)
    if existing:
        if (existing.case_id != case_id or existing.deleted_at is not None or
                existing.migration_metadata.get('payment_document_request_sha256') != digest):
            raise PdfMappingError('This save request has already been used. Reopen the saved review before making another.', 409)
        return dict(case_id=str(case_id), entry_id=str(existing.id), created=False, transaction_count=0)
    session.execute(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == file.id).with_for_update()).all()
    session.execute(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == file.id).with_for_update()).all()
    proposal = read_payment_document(session, case_id=case_id, evidence_file_id=file.id, document_id=request.document_id)
    if proposal['revision'] != request.expected_revision:
        raise PdfMappingError('The document reading changed. Reload it before saving.', 409)
    originals = {field['key']:field for field in proposal['fields']}
    if set(request.values) != set(originals) or not set(request.reasons) <= set(originals):
        raise PdfMappingError('The review fields changed. Reload the document.', 409)
    for key, original in originals.items():
        value = request.values[key]
        if (value != original['value'] or value and original['issues']) and not request.reasons.get(key,'').strip():
            raise PdfMappingError(f'Explain the correction or check for {original["label"].lower()}.', 422)
    values = request.values
    receipt = proposal['kind'] == 'deposit_receipt'
    amount_key, date_key = ('payment_amount', 'effective_date') if receipt else ('wire_amount', 'value_date')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', values[date_key]):
            raise ValueError('date')
        match_request = PaymentMatchRequest(amount=values[amount_key], currency=values['currency'], value_date=date.fromisoformat(values[date_key]))
        _match_conditions(case_id, match_request)
        if receipt:
            if int(exact_amount(values[amount_key], values['currency'])) <= 0:
                raise ValueError('Deposit must be positive')
            for field in proposal['fields']:
                value = values[field['key']]
                if value and field['input_type'] == 'date':
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                        raise ValueError('date')
                    date.fromisoformat(value)
                if value and field['input_type'] == 'amount':
                    exact_amount(value, values['currency'])
    except (ValueError, MoneyError) as exc:
        raise PdfMappingError('Check the payment amount, currency, dates and any recorded balances before saving.', 422) from exc
    path = resolve_path(file.stored_path)
    if path is None or not path.is_file() or path.stat().st_size > 256*1024*1024:
        raise PdfMappingError('The original PDF is unavailable for verification.', 409)
    file_hash = hashlib.sha256()
    with path.open('rb') as stream:
        count = 0
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            count += len(chunk)
            if count > 256*1024*1024:
                raise PdfMappingError('The original PDF exceeds the supported size.', 409)
            file_hash.update(chunk)
    if file_hash.hexdigest() != file.sha256:
        raise PdfMappingError('The original PDF differs from the recorded file. No review was saved.', 409)
    link_source = None
    if request.transaction_id:
        transaction = session.scalar(select(FinancialTransaction).join(FinancialSourceDocument,
            FinancialTransaction.source_document_id == FinancialSourceDocument.id).where(
                FinancialTransaction.id == request.transaction_id, *_match_conditions(case_id, match_request, direction='credit' if receipt else None)).with_for_update())
        if transaction is None:
            raise PdfMappingError('The selected payment no longer matches this document review. Find payments again.', 409)
        link_source = ledger_source(session, case_id=case_id, transaction_id=transaction.id)
        if _digest(link_source) != request.transaction_revision:
            raise PdfMappingError('The selected payment changed. Open it and check the link again.', 409)
    capture = dict(schema=SCHEMA, original=proposal, reviewed_values=values, correction_reasons=request.reasons,
                   notes=request.notes, link_reason=request.link_reason, file_bytes_verified=True)
    links = [dict(target_type='evidence', target_id=str(file.id), target_label=file.original_filename,
        relationship='context', source_anchor=dict(page_number=proposal['page_numbers'][0]), metadata=capture)]
    if link_source:
        payment_link = dict(target_type='evidence', target_id=link_source['evidence_file_id'],
            target_label=link_source['filename'], relationship='supports',
            source_anchor=dict(financial_transaction_ids=[link_source['transaction_id']],
                financial_ref_ids=[link_source['ref_id']], locator=link_source['locator']),
            metadata=dict(schema='loupe.financial.transaction_note/1', transactions=[link_source['transaction']]))
        if payment_link['target_id'] == str(file.id):
            # One file can contain both the receipt and the statement. Workspace
            # links are unique per file; retain both anchors on that one link.
            links[0]['source_anchor'].update(payment_link['source_anchor'])
            links[0]['metadata']['transactions'] = payment_link['metadata']['transactions']
            links[0]['relationship'] = 'supports'
        else:
            links.append(payment_link)
    body = ('Deposit receipt review\n\n' if receipt else 'Wire report review\n\n') + '\n'.join(f'{field["label"]}: {values[field["key"]] or "Not recorded"}' for field in proposal['fields'])
    for key, reason in request.reasons.items():
        if reason.strip(): body += f'\n\n{originals[key]["label"]}, correction or check: {reason.strip()}'
    if request.notes.strip(): body += '\n\nInvestigation note: '+request.notes.strip()
    if link_source: body += '\n\nLinked payment '+link_source['ref_id']+': '+request.link_reason.strip()
    body += '\n\nSaving this review did not add a payment to account totals.'
    entry = create_entry(session, case_id=case_id, current_user=user, entry_id=identifier,
        entry_type='note', title=request.title.strip(), body=body, tags=['financial', 'receipt-review' if receipt else 'wire-review'],
        links=links, compatibility_metadata=dict(payment_document_request_sha256=digest))
    return dict(case_id=str(case_id), entry_id=entry['id'], created=True, transaction_count=0)
