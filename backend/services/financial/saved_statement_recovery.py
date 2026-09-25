"""Review a combined saved import as separate account/currency sections.

Every current payment is assigned exactly once. The original source, amounts,
corrections and citations survive; replacement rows form normal correction
chains so saved casework can still resolve them. Preview and save share the
same validation and revision, and all replacements commit together.
"""
from copy import deepcopy
from dataclasses import fields
from datetime import date, datetime, timezone
from types import SimpleNamespace
import re
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, TransactionDirection
from postgres.models.financial import FinancialAccount, FinancialIngestionRun, FinancialSourceDocument, FinancialTransaction
from services.financial.currency_correction import CurrencyCode, rescale_minor
from services.financial.decisions import record
from services.financial.duplicate_decisions import duplicate_revision
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_details import BalanceEdit, _load, _view
from services.financial.transaction_query import to_view


class RecoverySection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=80)
    holder: str = Field(min_length=1, max_length=255)
    account_number: str = Field(min_length=1, max_length=128)
    institution: str = Field(min_length=1, max_length=128)
    currency: CurrencyCode
    period_start: date
    period_end: date
    transaction_ids: list[UUID]
    incomplete_ids: list[str] = Field(default_factory=list)
    opening: BalanceEdit = Field(default_factory=lambda: BalanceEdit(amount_minor=None))
    closing: BalanceEdit = Field(default_factory=lambda: BalanceEdit(amount_minor=None))


class StatementRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    sections: list[RecoverySection] = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=1, max_length=4096)
    expected_preview: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


def _current(session, document, *, lock=True):
    query = select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.case_id == document.case_id,
        FinancialTransaction.ledger_status != 'superseded',
        FinancialTransaction.superseded_by_id.is_(None))
    query = query.order_by(FinancialTransaction.id).execution_options(populate_existing=True)
    return list(session.scalars(query.with_for_update() if lock else query))


def read_recovery(session, *, case_id, source_id):
    document, period, account = _load(session, case_id, source_id, lock=True)
    rows = _current(session, document)
    details = _view(document, period, account)
    unresolved = [item for item in (document.metadata_ or {}).get('statement_incomplete_records', [])
        if not item.get('resolved_transaction_id')]
    return dict(**details, recovery_revision=_digest(dict(details=details,
        document=duplicate_revision(session, document), incomplete=unresolved,
        row_reviews={str(row.id): row.metadata_ for row in rows})),
        transactions=[{**to_view(row, account=account).to_json(),
            'page': (row.provenance or {}).get('statement_import_original', {}).get('page_number'),
            'amount_minor': str(row.amount_minor), 'running_balance_minor': str(row.running_balance_minor)
            if row.running_balance_minor is not None else None} for row in rows],
        incomplete_records=deepcopy(unresolved))


def _prepare(session, case_id, source_id, request):
    # Use the same case → evidence → document order as imports/removals. A
    # preview cannot race an import into the same original source.
    session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    document = session.scalar(select(FinancialSourceDocument).where(
        FinancialSourceDocument.id == source_id, FinancialSourceDocument.case_id == case_id))
    if document is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    evidence = session.scalar(select(EvidenceFile).where(EvidenceFile.id == document.evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update())
    if evidence is None or evidence.sha256 != document.sha256_at_ingestion:
        raise PdfMappingError('The original evidence no longer matches this import. Review its source history before separating records.', 409)
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    pending = session.scalar(select(Item.id).join(Batch, Item.batch_id == Batch.id).where(
        Batch.case_id == case_id, Item.file_id == evidence.id, Item.status == 'pending_import').limit(1))
    if pending:
        raise PdfMappingError('This PDF has an import in progress. Wait for its receipt before separating the saved records.', 409)
    view = read_recovery(session, case_id=case_id, source_id=source_id)
    if view['recovery_revision'] != request.expected_revision:
        raise PdfMappingError('This saved import changed. Reload it and review the assignments again.', 409)
    if not request.reason.strip():
        raise PdfMappingError('Explain why these records belong to separate statement sections.', 422)
    ids = [identity for section in request.sections for identity in section.transaction_ids]
    incomplete_ids = [identity for section in request.sections for identity in section.incomplete_ids]
    rows = _current(session, document)
    if len(ids) != len(set(ids)) or set(ids) != {row.id for row in rows}:
        raise PdfMappingError('Assign every saved payment to exactly one section. None may be omitted or counted twice.', 422)
    if len(incomplete_ids) != len(set(incomplete_ids)) or set(incomplete_ids) != {r['id'] for r in view['incomplete_records']}:
        raise PdfMappingError('Assign every incomplete record to exactly one section too.', 422)
    if len({s.key for s in request.sections}) != len(request.sections):
        raise PdfMappingError('Each section needs a distinct identifier.', 422)
    signatures = set()
    examples = []
    by_id = {row.id: row for row in rows}
    for section in request.sections:
        if section.period_start > section.period_end:
            raise PdfMappingError('The section start must be on or before its end date.', 422)
        for value in (section.holder, section.account_number, section.institution):
            if not value.strip() or any(ord(c) < 32 for c in value):
                raise PdfMappingError('Enter the printed account details on a single line for each section.', 422)
        signature = tuple(value.strip().casefold() for value in (section.account_number, section.institution)) + (
            section.currency, section.period_start, section.period_end)
        if signature in signatures:
            raise PdfMappingError('Two sections describe the same account, currency and dates. Combine those assignments.', 422)
        signatures.add(signature)
        for role in ('opening', 'closing'):
            edit = getattr(section, role)
            if edit.amount_minor is not None and (edit.page not in view['pages'] or abs(int(edit.amount_minor)) > 9223372036854775807):
                raise PdfMappingError('Each balance needs its original PDF page and a supported amount.', 422)
        if not section.transaction_ids and not section.incomplete_ids and all(
                getattr(section, role).amount_minor is None for role in ('opening', 'closing')):
            raise PdfMappingError('An empty section needs a printed balance. Do not invent a section without evidence.', 422)
        totals = dict(credit=0, debit=0)
        for identity in section.transaction_ids:
            row = by_id[identity]
            amount = rescale_minor(row.amount_minor, row.currency, section.currency)
            rescale_minor(row.running_balance_minor, row.currency, section.currency)
            if row.ledger_status == 'admitted':
                totals[row.direction] += amount
        _section_metadata(document, section, view, rows)  # Validate pending readings in the preview too.
        examples.append(dict(key=section.key, holder=section.holder, account_number=section.account_number,
            institution=section.institution, currency=section.currency,
            period_start=section.period_start.isoformat(), period_end=section.period_end.isoformat(),
            transaction_count=len(section.transaction_ids), incomplete_count=len(section.incomplete_ids),
            credit_minor=str(totals['credit']), debit_minor=str(totals['debit']),
            opening=section.opening.model_dump(), closing=section.closing.model_dump()))
    revision = _digest(dict(current=view['recovery_revision'], request=request.model_dump(mode='json', exclude={'expected_preview'})))
    return document, view, rows, dict(revision=revision, sections=examples, transaction_count=len(rows),
        incomplete_count=len(incomplete_ids), source_document_id=str(source_id),
        explanation='Amounts keep their printed numeric values. Original records and saved corrections remain in history; existing citations follow their replacement payments.')


def preview_recovery(session, *, case_id, source_id, request):
    try:
        return _prepare(session, case_id, source_id, request)[3]
    finally:
        session.rollback()


def _section_metadata(document, section, view, rows):
    metadata = document.metadata_
    by_id = {row.id: row for row in rows}
    original_ids = {(by_id[identity].provenance or {}).get('statement_import_original', {}).get('id')
        for identity in section.transaction_ids} | set(section.incomplete_ids)
    proposal = deepcopy(metadata['statement_import_original'])
    proposal['rows'] = [r for r in proposal['rows'] if r['id'] in original_ids]
    proposal['statement_id'] = _digest(dict(recovery_source=str(document.id), key=section.key))
    proposal['current_import'] = None
    proposal['saved_review'] = None
    proposal['statement_row_addresses'] = [[r['page_number'], r['table_index'], r['row_index']]
        for r in proposal['rows'] if all(key in r for key in ('page_number', 'table_index', 'row_index'))]
    proposal.pop('statement_source_regions', None)
    # The page/table evidence remains available, but the former combined
    # totals and balances must not become controls for each new account.
    proposal['issues'] = []
    proposal['metadata'] = {**proposal['metadata'], **{key: getattr(section, key).strip()
        for key in ('holder', 'account_number', 'institution')}, 'currency': section.currency,
        'period_start': section.period_start.isoformat(), 'period_end': section.period_end.isoformat()}
    raw = deepcopy(metadata['statement_import_request'])
    original_currency = raw.get('currency')
    raw.update({key: value for key, value in section.model_dump(mode='json').items()
        if key in ('holder', 'account_number', 'institution', 'currency', 'period_start', 'period_end')})
    raw.update(statement_id=proposal['statement_id'], expected_revision=proposal.get('revision'))
    raw['rows'] = [r for r in raw['rows'] if r['id'] in original_ids]
    if original_currency and original_currency != section.currency:
        for row in raw['rows']:
            for key in ('amount_minor', 'balance_minor'):
                value = row.get(key)
                if value is None or re.fullmatch(r'-?\d+', str(value)):
                    row[key] = rescale_minor(value, original_currency, section.currency)
    unresolved = [deepcopy(item) for item in view['incomplete_records'] if item['id'] in section.incomplete_ids]
    for item in unresolved:
        values = deepcopy(item.get('correction') or item['fields'])
        before_currency = item.get('correction_currency') or metadata['statement_import_request'].get('currency')
        if before_currency and before_currency != section.currency:
            for key in ('amount_minor', 'balance_minor'):
                value = values.get(key)
                if value is None or re.fullmatch(r'-?\d+', str(value)):
                    values[key] = rescale_minor(value, before_currency, section.currency)
        item.update(correction=values, correction_currency=section.currency)
    return dict(statement_import_statement_id=proposal['statement_id'],
        statement_import_original=proposal, statement_import_original_sha256=_digest(proposal),
        statement_import_request=raw, statement_import_request_sha256=_digest(raw),
        statement_import_issues=[deepcopy(issue) for issue in metadata.get('statement_import_issues', [])
            if issue.get('row_id') in original_ids and issue.get('field') != 'currency'], statement_incomplete_records=unresolved,
        source_shape=metadata.get('source_shape'),
        admissibility_reservations=deepcopy(metadata.get('admissibility_reservations', [])),
        whole_document_extraction_verified=False,
        statement_recovery_parent_id=str(document.id))


def recovery_catalog(session, file, choices, selected_id):
    """Reopen reviewed sections without running them through a changed parser.

    Unrelated periods stay in the chooser. The old combined scope is replaced
    by the sections explicitly reviewed by the investigator, never inferred
    again from page-level overlap.
    """
    from services.financial.statement_details import saved_details, saved_currency
    documents = list(session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == file.case_id, FinancialSourceDocument.evidence_file_id == file.id,
        FinancialSourceDocument.status == 'admitted',
        FinancialSourceDocument.metadata_['statement_recovery_parent_id'].as_string().is_not(None))
        .order_by(FinancialSourceDocument.id)))
    if not documents:
        return choices, None, False
    removed_ids = set()
    for document in documents:
        parent = session.get(FinancialSourceDocument, UUID(document.metadata_['statement_recovery_parent_id']))
        visited = {document.id}
        while parent and parent.case_id == file.case_id:
            if parent.id in visited or parent.evidence_file_id != file.id:
                raise PdfMappingError('Saved section history is inconsistent. Review the source history before reopening it.')
            visited.add(parent.id)
            removed_ids.add(parent.metadata_.get('statement_import_statement_id'))
            identity = parent.metadata_.get('statement_recovery_parent_id')
            parent = session.get(FinancialSourceDocument, UUID(identity)) if identity else None
    choices = [] if None in removed_ids else [choice for choice in choices if choice['id'] not in removed_ids]
    chosen = None
    for document in documents:
        original = document.metadata_['statement_import_original']
        details = saved_details(document)
        rows = _current(session, document, lock=False)
        incomplete = [r for r in document.metadata_.get('statement_incomplete_records', []) if not r.get('resolved_transaction_id')]
        identity = document.metadata_['statement_import_statement_id']
        pages = sorted({source['page_number'] for source in original.get('sources', [])})
        choices.append(dict(id=identity, institution=details['institution'], account_reference=details['account_number'],
            account_label=details['holder'], currency=saved_currency(document), period_start=details['period_start'],
            period_end=details['period_end'], page_numbers=pages, checks=dict(balance_status='unavailable',
                flagged_rows=len(incomplete), transaction_count=len(rows))))
        if selected_id == identity:
            chosen = {**deepcopy(original), 'case_id': str(file.case_id), 'evidence_file_id': str(file.id),
                'filename': file.original_filename, 'statement_id': identity, 'metadata': {**original['metadata'], **details},
                'currency': saved_currency(document), 'recovered_saved_section': True,
                'transaction_count': len(rows), 'needs_attention': len(incomplete), 'page_numbers': pages,
                'current_import': dict(source_document_id=str(document.id), evidence_file_id=str(file.id),
                    account_id=document.metadata_['statement_account_id'], filename=file.original_filename,
                    revision=duplicate_revision(session, document), transaction_count=sum(r.ledger_status == 'admitted' for r in rows),
                    incomplete_count=len(incomplete), record_count=len(rows) + len(incomplete), details=details,
                    currency=saved_currency(document), issues=document.metadata_.get('statement_import_issues', []))}
    if chosen is not None:
        chosen['statement_choices'] = choices
    return choices, chosen, selected_id in removed_ids


def save_recovery(session, *, case_id, source_id, request, actor):
    from services.financial.accounts import AccountDraft, AccountIdentityError, record_account
    from services.financial.periods import StatementPeriodDraft, PeriodBounds, BalanceObservation, record_statement_period
    from services.financial.money import Money
    from services.financial.references import RowReading, content_hash, ref_id
    from services.financial.reconcile import reconcile_period
    try:
        session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
        original = session.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.id == source_id,
            FinancialSourceDocument.case_id == case_id).execution_options(populate_existing=True))
        previous = (original.metadata_ or {}).get('statement_recovery_receipt') if original else None
        payload = request.model_dump(mode='json')
        if previous and previous.get('request') == payload:
            return previous['result']  # Lost response: never create a second split.
        document, view, rows, preview = _prepare(session, case_id, source_id, request)
        if request.expected_preview != preview['revision']:
            raise PdfMappingError('Review the current section assignments before saving.', 409)
        by_id = {row.id: row for row in rows}
        source_period_id = view['period_id']
        references = set(session.scalars(select(FinancialTransaction.ref_id).where(FinancialTransaction.case_id == case_id)))
        sections, replacements = [], []
        now = datetime.now(timezone.utc)
        for section in request.sections:
            run = FinancialIngestionRun(id=uuid4(), case_id=case_id, status='completed',
                code_version='saved-statement-recovery-v1', ruleset_version='1', started_by_user_id=actor.user_id,
                started_by_email=actor.email, completed_at=now, documents_seen=1,
                transactions_admitted=sum(by_id[key].ledger_status == 'admitted' for key in section.transaction_ids),
                config=dict(operation='split_saved_statement', source_document_id=str(source_id), reason=request.reason.strip()))
            session.add(run); session.flush()
            stamp = SimpleNamespace(case_id=case_id, run_id=run.id)
            stamp.stamp = lambda item: (setattr(item, 'case_id', case_id), setattr(item, 'ingestion_run_id', run.id))
            old_account = session.get(FinancialAccount, UUID(view['account_id']))
            try:
                account_draft = AccountDraft.observed(identifier_as_printed=section.account_number.strip(),
                    holder_name=section.holder.strip(), institution_name=section.institution.strip(),
                    currency=section.currency, account_type=old_account.account_type,
                    metadata=dict(account_reference_kind=(old_account.metadata_ or {}).get('account_reference_kind')))
            except AccountIdentityError as exc:
                raise PdfMappingError('Enter a printed account identifier for each section; placeholder text does not identify an account.', 422) from exc
            account = record_account(session, stamp, account_draft)
            metadata = _section_metadata(document, section, view, rows)
            metadata['statement_account_id'] = str(account.id)
            new_source = FinancialSourceDocument(id=uuid4(), case_id=case_id, evidence_file_id=document.evidence_file_id,
                ingestion_run_id=run.id, sha256_at_ingestion=document.sha256_at_ingestion, document_type='statement_review',
                proof_class=document.proof_class, extraction_layer=document.extraction_layer,
                parser_name='saved-statement-recovery', parser_version='1', currency=section.currency,
                institution_name=section.institution, page_count=document.page_count, status='admitted', metadata_=metadata)
            session.add(new_source); session.flush()
            sign = -1 if view['balance_convention'] == 'liability_owed' else 1
            balances = {role: BalanceObservation.printed(Money(sign * int(getattr(section, role).amount_minor), section.currency))
                if getattr(section, role).amount_minor is not None else BalanceObservation.absent() for role in ('opening', 'closing')}
            period = record_statement_period(session, stamp, StatementPeriodDraft(account_id=account.id,
                source_document_id=new_source.id, currency=section.currency,
                bounds=PeriodBounds.printed(section.period_start, section.period_end), **balances))
            review = dict(details={key: metadata['statement_import_request'][key] for key in
                ('holder', 'account_number', 'institution', 'period_start', 'period_end')},
                balances={role: getattr(section, role).model_dump() for role in ('opening', 'closing')},
                account_id=str(account.id), period_id=str(period.id), source_document_id=str(new_source.id),
                currency=section.currency, balance_convention=view['balance_convention'])
            new_source.metadata_ = {**metadata, 'statement_details_review': review, 'statement_details_review_sha256': _digest(review)}
            for identity in section.transaction_ids:
                row = by_id[identity]
                amounts = {key: rescale_minor(getattr(row, key), row.currency, section.currency)
                    for key in ('amount_minor', 'running_balance_minor')}
                reading = {field.name: getattr(row, field.name) for field in fields(RowReading)}
                reading.update(currency=section.currency, direction=TransactionDirection(row.direction), **amounts)
                occurrence = 0
                while True:
                    digest = content_hash(RowReading(**reading), occurrence)
                    reference = ref_id(document.sha256_at_ingestion, digest)
                    if reference not in references: break
                    occurrence += 1
                references.add(reference)
                values = {prop.key: deepcopy(getattr(row, prop.key)) for prop in FinancialTransaction.__mapper__.column_attrs
                    if prop.key not in {'id', 'created_at', 'updated_at'}}
                values.update(id=uuid4(), source_document_id=new_source.id, ingestion_run_id=run.id,
                    account_id=account.id, statement_period_id=period.id, currency=section.currency,
                    content_hash=digest, ref_id=reference, superseded_by_id=None, **amounts)
                values['provenance'] = {**(values['provenance'] or {}), 'correction': dict(
                    previous_transaction_id=str(row.id), previous_ref_id=row.ref_id, occurrence=occurrence, version=1),
                    'statement_recovery': dict(previous_source_id=str(source_id), previous_period_id=source_period_id,
                        reason=request.reason.strip(), section_key=section.key)}
                replacement = FinancialTransaction(**values)
                session.add(replacement); session.flush()
                before = to_view(row).to_json()
                record(session, case_id=case_id, subject=row, subject_type=AdjudicationSubject.transaction,
                    decision=AdjudicationDecision.correct_transaction, actor=actor, reason=request.reason.strip(),
                    before=dict(row=before, replacement_id=None, original_status=row.ledger_status,
                        original_quarantine_reason=row.quarantine_reason, reviewed_revision=preview['revision']),
                    after=dict(row={**to_view(replacement).to_json(), 'amount_minor': str(replacement.amount_minor)},
                        replacement_id=str(replacement.id), original_status='superseded', original_quarantine_reason=None,
                        reviewed_revision=preview['revision']))
                row.ledger_status = 'superseded'; row.quarantine_reason = None; row.superseded_by_id = replacement.id
                replacements.append(dict(previous_id=str(row.id), id=str(replacement.id)))
            session.flush()
            reconcile_period(session, period)
            sections.append(dict(key=section.key, source_document_id=str(new_source.id), account_id=str(account.id),
                period_id=str(period.id), currency=section.currency, transaction_count=len(section.transaction_ids)))
        result = dict(source_document_id=str(source_id), sections=sections, replacements=replacements, applied=True)
        document.status = 'superseded'
        document.quarantine_reason = None
        document.metadata_ = {**document.metadata_, 'statement_recovery_receipt': dict(
            request=payload, result=result, preview=preview, saved_at=now.isoformat(),
            saved_by=dict(user_id=str(actor.user_id), name=actor.name))}
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
