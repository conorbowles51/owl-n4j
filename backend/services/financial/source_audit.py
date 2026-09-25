"""Read-only, content-neutral inventory for an investigator's Financial audit.

Only recorded provenance is projected. No reader, classifier, filesystem access,
job or mutation is invoked. Text is selected by a bounded SQL substring on an
individual case-owned file; list responses never include document bodies.
"""
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, func, cast, String
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from postgres.models.financial import FinancialSourceDocument as Source, FinancialStatementPeriod as Period, FinancialTransaction as Transaction
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.file_scope import SCHEMA
from services.financial.file_visibility import financial_file_visibility
from services.financial.source_lineage import lineage_groups, current_version
from services.financial.pdf_candidates import PdfMappingError


def _present(value):
    text = cast(value, String)
    return text.is_not(None) & text.notin_(('', '{}', '[]', 'null'))


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _index(session, case_id):
    # Scalar fields only: review bodies, geometry, paths, credentials and full
    # source metadata are deliberately not loaded into this audit inventory.
    m = EvidenceFile.metadata_
    fields = dict(root=m['statement_root_evidence_id'].as_string(),
        parent=m['statement_parent_evidence_id'].as_string(),
        schema=m['financial_workspace']['schema'].as_string(),
        selected_at=m['financial_workspace']['selected_at'].as_string(),
        selected_by=m['financial_workspace']['selected_by'].as_string(),
        mode=EvidenceFile.last_processed_profile_snapshot['preparation_mode'].as_string(),
        removed=m['financial_file_visibility']['removed'].as_boolean(),
        visibility_revision=m['financial_file_visibility']['revision'].as_string(),
        visibility_changed_at=m['financial_file_visibility']['changed_at'].as_string(),
        has_visibility=_present(m['financial_file_visibility']),
        has_import_removal=_present(m['financial_import_removal']),
        has_progress=_present(m['financial_review_progress']),
        has_history=_present(m['financial_review_history']),
        has_version=_present(m['statement_version_request']))
    rows = session.execute(select(EvidenceFile.id, EvidenceFile.case_id, EvidenceFile.original_filename,
        EvidenceFile.sha256, EvidenceFile.status, EvidenceFile.created_at,
        *[value.label(key) for key, value in fields.items()]).where(EvidenceFile.case_id == case_id)).mappings()
    files, facts = {}, {}
    for row in rows:
        identifier = str(row['id'])
        files[identifier] = SimpleNamespace(id=row['id'], case_id=row['case_id'],
            original_filename=row['original_filename'], sha256=row['sha256'], status=row['status'],
            created_at=row['created_at'], metadata_={
                'statement_root_evidence_id': row['root'], 'statement_parent_evidence_id': row['parent'],
                'financial_file_visibility': dict(removed=row['removed'] is True,
                    revision=row['visibility_revision'] or 'initial', changed_at=row['visibility_changed_at'])})
        enrolled = row['schema'] == SCHEMA
        facts[identifier] = dict(member=bool(enrolled or row['mode'] == 'pdf_review' or any(row[key] for key in
            ('has_visibility', 'has_import_removal', 'has_progress', 'has_history', 'has_version'))),
            enrollment_recorded=enrolled, explicit_selection=bool(enrolled and row['selected_by']),
            selected_at=row['selected_at'], selected_by=row['selected_by'], preparation_mode=row['mode'],
            saved_review_storage_count=int(bool(row['has_progress'])) + int(bool(row['has_history'])),
            batch_ids=set(), scopes=set(), readers=set(), imported_source_count=0, saved_source_count=0, saved_period_count=0,
            payment_count=0, note_count=0, active_work=row['status'] == 'processing',
            has_import_removal=bool(row['has_import_removal']), retained_text_available=False)
    def fact(identifier):
        return facts.get(str(identifier))
    from services.financial.active_recovery import active_recovery_file_ids
    for identifier in active_recovery_file_ids(session, case_id=case_id):
        if (value := fact(identifier)) is not None:
            value['member'] = True
            value['active_work'] = True
    for model in (FinancialCandidateMapping, FinancialStatementReviewDraft):
        for identifier, count in session.execute(select(model.evidence_file_id, func.count()).where(
                model.case_id == case_id).group_by(model.evidence_file_id)):
            if (value := fact(identifier)) is not None:
                value['member'] = True
                value['saved_review_storage_count'] += count
    for identifier, count in session.execute(select(EvidenceDocumentText.evidence_file_id,
            func.length(EvidenceDocumentText.content)).join(EvidenceFile,
            EvidenceDocumentText.evidence_file_id == EvidenceFile.id).where(EvidenceFile.case_id == case_id)):
        if (value := fact(identifier)) is not None:
            value['retained_text_available'] = bool(count)
    for batch_id, status, entries, token, lease in session.execute(select(Batch.id, Batch.status,
            Batch.files, Batch.worker_token, Batch.lease_until).where(Batch.case_id == case_id)):
        if lease and lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        leased = bool(token and lease and lease > datetime.now(timezone.utc))
        for entry in entries or []:
            for key in ('source_id', 'file_id'):
                if (value := fact(entry.get(key))) is None:
                    continue
                value['member'] = True
                value['batch_ids'].add(str(batch_id))
                if status != 'removed' and (entry.get('status') in ('waiting', 'processing') or
                        leased and entry.get('status') not in ('checked', 'error')):
                    value['active_work'] = True
    for identifier, batch_id, batch_status, item_status, statement, has_review, reader in session.execute(select(
            Item.file_id, Item.batch_id, Batch.status, Item.status, Item.statement_key,
            _present(Item.review_request), Item.summary['layout_id'].as_string()).join(Batch,
            Item.batch_id == Batch.id).where(Batch.case_id == case_id)):
        if (value := fact(identifier)) is None:
            continue
        value['member'] = True
        value['batch_ids'].add(str(batch_id))
        value['saved_review_storage_count'] += int(bool(has_review))
        value['scopes'].add(statement or '')
        if reader:
            value['readers'].add(reader)
        if batch_status != 'removed' and item_status == 'pending_import':
            value['active_work'] = True
    for identifier, source_id, status, parser, statement, choices in session.execute(select(Source.evidence_file_id,
            Source.id, Source.status, Source.parser_name,
            Source.metadata_['statement_import_statement_id'].as_string(),
            Source.metadata_['statement_import_original']['statement_choices']).where(Source.case_id == case_id)):
        if (value := fact(identifier)) is None:
            continue
        value['member'] = True
        value['saved_source_count'] += 1
        value['imported_source_count'] += int(status == 'admitted')
        if statement is not None:
            value['scopes'].add(statement)
        for choice in choices or []:
            if isinstance(choice, dict) and isinstance(choice.get('layout_id'), str):
                value['readers'].add(choice['layout_id'][:160])
        if parser:
            value['readers'].add(parser)
    for model, name in ((Period, 'saved_period_count'), (Transaction, 'payment_count')):
        for identifier, count in session.execute(select(Source.evidence_file_id, func.count()).join(model,
                model.source_document_id == Source.id).where(Source.case_id == case_id,
                model.case_id == case_id).group_by(Source.evidence_file_id)):
            if (value := fact(identifier)) is not None:
                value[name] += count
    from services.financial.payment_document_proposal import SCHEMA as DOCUMENT_SCHEMA
    for identifier, schema, deleted in session.execute(select(WorkspaceEntryLink.target_id,
            WorkspaceEntryLink.link_metadata['schema'].as_string(), WorkspaceEntry.deleted_at)
            .join(WorkspaceEntry, WorkspaceEntry.id == WorkspaceEntryLink.entry_id).where(
                WorkspaceEntry.case_id == case_id, WorkspaceEntryLink.case_id == case_id,
                WorkspaceEntryLink.target_type == 'evidence')):
        try:
            identifier = str(UUID(identifier))
        except (TypeError, ValueError):
            continue
        if (value := fact(identifier)) is not None:
            value['member'] |= schema == DOCUMENT_SCHEMA
            value['note_count'] += int(deleted is None)
    groups = {key: versions for key, versions in lineage_groups(list(files.values())).items()
              if any(facts[str(file.id)]['member'] for file in versions)}
    return files, facts, groups


def _group(root, versions, facts):
    current = current_version(versions)
    values = [facts[str(file.id)] for file in versions]
    provenance = {name: sum(value[name] for value in values) for name in (
        'saved_review_storage_count', 'imported_source_count', 'saved_source_count', 'saved_period_count', 'payment_count', 'note_count')}
    provenance.update(enrollment_recorded=any(v['enrollment_recorded'] for v in values),
        explicit_selection=any(v['explicit_selection'] for v in values),
        imports_removed=any(v['has_import_removal'] for v in values),
        review_count_basis='storage_representations',
        preparation_mode='pdf_review' if any(v['preparation_mode'] == 'pdf_review' for v in values) else None,
        batch_count=len(set().union(*(v['batch_ids'] for v in values))),
        parsed_statement_period_count=len(set().union(*(v['scopes'] for v in values))),
        recognized_readers=sorted(set().union(*(v['readers'] for v in values))))
    active = any(v['active_work'] for v in values)
    reasons = []
    for code, condition, message in (
        ('active_work', active, 'Reading, preparation, import or statement recovery is queued or active.'),
        ('saved_financial_records', any(provenance[key] for key in ('saved_source_count', 'saved_period_count', 'payment_count')), 'Saved financial records or their history are retained.'),
        ('saved_review', bool(provenance['saved_review_storage_count']), 'Saved review or correction work is retained.'),
        ('case_notes', bool(provenance['note_count']), 'Case notes or document reviews link to this evidence.'),
        ('explicit_selection', provenance['explicit_selection'], 'An investigator explicitly selected this source for Financial.'),
    ):
        if condition:
            reasons.append(dict(code=code, message=message))
    visibility = financial_file_visibility(current)
    return dict(root_file_id=root, current_file_id=str(current.id), filename=current.original_filename,
        version_count=len(versions), hidden_version_count=sum(financial_file_visibility(v)['financial_removed'] for v in versions),
        visibility='hidden' if visibility['financial_removed'] else 'visible',
        visibility_revision=visibility['financial_visibility_revision'], provenance=provenance,
        protection_reasons=reasons, active_work=active,
        retained_text_available=any(v['retained_text_available'] for v in values))


def list_source_audit(session, *, case_id, offset=0, limit=50, visibility='all'):
    if not 0 <= offset or not 1 <= limit <= 50 or visibility not in ('all', 'visible', 'hidden'):
        raise PdfMappingError('Choose a valid audit page and visibility filter.', 422)
    with session.no_autoflush:
        _, facts, groups = _index(session, case_id)
        rows = [_group(root, groups[root], facts) for root in sorted(groups)]
    selected = [row for row in rows if visibility == 'all' or row['visibility'] == visibility]
    return dict(applied=False, case_id=str(case_id), total=len(selected), offset=offset, limit=limit,
        summary=dict(groups=len(rows), visible=sum(r['visibility'] == 'visible' for r in rows),
            hidden=sum(r['visibility'] == 'hidden' for r in rows), protected=sum(bool(r['protection_reasons']) for r in rows),
            active_work=sum(r['active_work'] for r in rows), with_retained_text=sum(r['retained_text_available'] for r in rows),
            without_retained_text=sum(not r['retained_text_available'] for r in rows)),
        groups=selected[offset:offset + limit],
        limitation='Recorded provenance is not a content classification. Counts include retained history; saved review storage representations can repeat the same review or contain several periods and are not a count of distinct reviews. Missing text does not mean non-financial content.')


def source_audit_detail(session, *, case_id, file_id, text_offset=0, text_limit=4000):
    if text_offset < 0 or not 1 <= text_limit <= 8000:
        raise PdfMappingError('Choose a valid retained-text window.', 422)
    with session.no_autoflush:
        files, facts, groups = _index(session, case_id)
        family = next(((root, versions) for root, versions in groups.items()
            if any(file.id == file_id for file in versions)), None)
        if family is None:
            raise PdfMappingError('Financial source not found in this case.', 404)
        root, versions = family
        selected = files[str(file_id)]
        summary = session.execute(select(func.substr(EvidenceFile.summary, 1, 1500), func.length(EvidenceFile.summary))
            .where(EvidenceFile.case_id == case_id, EvidenceFile.id == file_id)).one()
        text = session.execute(select(func.length(EvidenceDocumentText.content),
            func.substr(EvidenceDocumentText.content, text_offset + 1, text_limit)).join(EvidenceFile,
            EvidenceDocumentText.evidence_file_id == EvidenceFile.id).where(
                EvidenceFile.case_id == case_id, EvidenceDocumentText.evidence_file_id == file_id)).first()
        ordered = sorted(versions, key=lambda v: str(v.id))
        records = [dict(evidence_file_id=str(file.id), filename=file.original_filename, status=file.status,
            created_at=_iso(file.created_at), visibility='hidden' if financial_file_visibility(file)['financial_removed'] else 'visible',
            selected_by=(facts[str(file.id)]['selected_by'] or '')[:80] or None,
            selected_at=(facts[str(file.id)]['selected_at'] or '')[:80] or None,
            preparation_mode=facts[str(file.id)]['preparation_mode'],
            retained_text_available=facts[str(file.id)]['retained_text_available']) for file in ordered[:100]]
        return dict(applied=False, case_id=str(case_id), evidence_file_id=str(selected.id),
            group=_group(root, versions, facts), versions=records, versions_truncated=len(ordered) > 100,
            source_summary=summary[0], source_summary_truncated=bool(summary[1] and summary[1] > 1500),
            text_excerpt=dict(evidence_file_id=str(selected.id), available=bool(text and text[0]),
                offset=text_offset, total_characters=text[0] if text else 0, text=text[1] if text else '',
                truncated=bool(text and text_offset + text_limit < text[0])),
            limitation='This is retained extracted text, not a new reading or a determination of financial relevance. Inspect the original when text is missing or inconclusive.')
