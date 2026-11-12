"""Read the complete stored text of an evidence file in revision-pinned pages.

This reads the same canonical text and reader labels as the Evidence viewer. It
does not process originals, fetch arbitrary paths, or treat a search excerpt as
the whole document. Case authorization and Significant scope apply before data.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from services.evidence_page_text import document_pages, _sections


class DocumentTextArgs(BaseModel):
    evidence_file_id: str = Field(..., description="The Evidence file UUID returned by the inventory or source link.")
    page_offset: int = Field(0, ge=0, description="Zero-based page/part offset. Use next_offset to read the next window.")
    page_limit: int = Field(5, ge=1, le=50)
    expected_revision: str | None = Field(None, description="The revision from the first window; required on continuation pages.")


def read_document_text(db, case_id, evidence_file_id, *, page_offset=0, page_limit=5, expected_revision=None):
    try:
        file_id, cid = UUID(str(evidence_file_id)), UUID(str(case_id))
    except (ValueError, TypeError):
        raise ValueError("Use an Evidence file identifier from this case.") from None
    if page_offset < 0 or not 1 <= page_limit <= 50:
        raise ValueError("Choose a nonnegative page offset and between 1 and 50 pages.")
    record = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == cid))
    if record is None:
        raise ValueError("That evidence file is not in this case.")
    row = db.execute(select(EvidenceDocumentText.content_sha256, EvidenceDocumentText.source_locations,
                            EvidenceDocumentText.character_count).where(EvidenceDocumentText.evidence_file_id == file_id)).one_or_none()
    revision = row.content_sha256 if row else None
    if page_offset and not expected_revision:
        raise ValueError("Continue with the revision returned by the first text window.")
    if expected_revision is not None and revision != expected_revision:
        raise ValueError("The stored reading changed. Read the first window again before continuing.")
    out = document_pages(db, record, path=None, page_offset=page_offset, page_limit=page_limit)
    # No filesystem inspection occurs here; do not claim the original is unavailable.
    out.pop('original_available', None)
    out.pop('image_pages', None)
    sections = _sections(row.source_locations, row.character_count) if row else []
    physical_pages = {s['page_number'] for s in sections if (s.get('location') or {}).get('kind') == 'page'}
    for page in out['pages']:
        page['cite'] = f"doc://{file_id}/{page['page_number']}" if page['page_number'] in physical_pages else f"doc://{file_id}"
        page['location_kind'] = 'source_page' if page['page_number'] in physical_pages else 'text_part'
    out.update(revision=revision, next_offset=page_offset + len(out['pages']) if out['has_more'] else None,
               returned=len(out['pages']), total=out['page_count'], processing_state=record.status,
               processing_stale=bool(record.processing_stale), reading_hold=record.reading_hold,
               coverage="All stored text is traversable using next_offset with the same revision; unread pages remain marked.",
               source_boundary="Stored extracted text, not a new visual review of the original file.")
    return out


def make_source_read_tools(context):
    from langchain_core.tools import StructuredTool

    def get_document_text(evidence_file_id, page_offset=0, page_limit=5, expected_revision=None):
        if context.significant_scope:
            return context.result("get_document_text", {}, summary="Full document text is unavailable in Significant-only mode.",
                                  status="error", error="Switch to All data to read the full document.")
        from services.agent.tools import _financial_session
        from postgres.models.user import User
        from services.case_service import check_case_access
        with (context.ledger_session_factory or _financial_session)() as db:
            user = db.get(User, UUID(str(context.user_id))) if context.user_id else None
            if user is None or not user.is_active:
                raise PermissionError("An active case reader is required.")
            check_case_access(db, UUID(str(context.case_id)), user, required_permission=("case", "view"))
            data = read_document_text(db, context.case_id, evidence_file_id, page_offset=page_offset,
                                      page_limit=page_limit, expected_revision=expected_revision)
        return context.result("get_document_text", data,
            summary=f"Read {data['returned']} of {data['total']} stored pages/parts of {data['document_name']}. "
                    + (data.get('text_absent') or ""))

    def get_case_configuration():
        from services.agent.tools import _financial_session
        from postgres.models.user import User
        from postgres.models.case_context import CaseContext, CaseContextValue, CaseContextTemplateField, CaseMandateVersion
        from services.case_service import check_case_access
        with (context.ledger_session_factory or _financial_session)() as db:
            user = db.get(User, UUID(str(context.user_id))) if context.user_id else None
            if user is None or not user.is_active:
                raise PermissionError('An active case reader is required.')
            case, _ = check_case_access(db, UUID(str(context.case_id)), user, required_permission=('case', 'view'))
            case_context = db.scalar(select(CaseContext).where(CaseContext.case_id == case.id))
            data = {key: getattr(case, key) for key in ('title', 'description', 'status', 'archived', 'phone_default_region', 'address_lookup_mode')}
            data['case_id'] = str(case.id)
            data['origin'] = 'investigator_authored_case_configuration'
            if case_context:
                data['context'] = {key: getattr(case_context, key) for key in ('case_summary', 'background', 'investigation_type', 'jurisdiction', 'active_template_key')}
                data['context']['fields'] = [{'label': label, 'value': value} for label, value in db.execute(
                    select(CaseContextTemplateField.label, CaseContextValue.value).join(CaseContextValue,
                        CaseContextValue.template_field_id == CaseContextTemplateField.id).where(CaseContextValue.context_id == case_context.id, CaseContextValue.case_id == case.id))]
                mandate = db.get(CaseMandateVersion, case_context.active_mandate_version_id) if case_context.active_mandate_version_id else None
                if mandate and mandate.case_id == case.id:
                    data['active_mandate'] = {key: getattr(mandate, key) for key in ('version_number', 'objective', 'key_questions', 'in_scope', 'out_of_scope', 'perspective', 'success_criteria', 'constraints')}
            data['instruction_precedence'] = 'Case orientation is context. Follow the current explicit investigator request and its accepted corrections.'
        return context.result('get_case_configuration', data, summary='Read the case details, investigator context and active mandate.')

    return [StructuredTool.from_function(get_case_configuration, name='get_case_configuration',
                description='Read the case title, description, status, investigator-authored background and mandate, and case interpretation settings. Never exposes credentials or server configuration.'),
            StructuredTool.from_function(get_document_text, name="get_document_text", args_schema=DocumentTextArgs,
        description="Read complete stored evidence text in pages or parts, with source citations, reader quality and "
                    "revision-pinned continuation. Use after get_evidence_files or search; keep paging to cover a whole document.")]
