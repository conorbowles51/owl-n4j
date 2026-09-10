"""Verify exact database audit bytes before including a prospective event chain."""
import hashlib
import re
from uuid import UUID
from sqlalchemy import select
from postgres.models.financial_audit import FinancialAuditEvent
from services.financial.reference_reviews import parse_review_json
from services.financial.ledger_summary import LedgerSummaryError

MAX_AUDIT_EVENTS = 10000
MAX_AUDIT_BYTES = 64 * 1024 * 1024
_HASH = re.compile(r'^[a-f0-9]{64}$')
AUDIT_COVERAGE = {
    'financial_source_documents': ['INSERT', 'UPDATE', 'DELETE'],
    'financial_accounts': ['INSERT', 'UPDATE', 'DELETE'],
    'financial_statement_periods': ['INSERT', 'UPDATE', 'DELETE'],
    'financial_transactions': ['INSERT', 'UPDATE', 'DELETE'],
    'financial_statement_review_drafts': ['INSERT', 'UPDATE', 'DELETE'],
    'evidence_files': ['INSERT', 'UPDATE', 'DELETE'],
    'workspace_entries': ['INSERT', 'UPDATE', 'DELETE'],
    'workspace_entry_links': ['INSERT', 'UPDATE', 'DELETE'],
    'workspace_entry_revisions': ['INSERT'],
    'workspace_entry_events': ['INSERT'],
    'adjudications': ['INSERT'],
    'financial_candidate_mappings': ['INSERT'],
    'financial_candidate_reviews': ['INSERT'],
    'financial_candidate_finalizations': ['INSERT'],
    'financial_pdf_nominations': ['INSERT', 'UPDATE'],
    'financial_ingestion_runs': ['INSERT', 'UPDATE'],
}


def verify_financial_audit_chain(entries, *, case_id, expected_head_sha256=None):
    """A supplied head detects tail removal only if retained independently beforehand."""
    case_id = str(UUID(str(case_id)))
    if not isinstance(entries, list) or len(entries) > MAX_AUDIT_EVENTS:
        raise LedgerSummaryError('Financial audit history exceeds the event limit.')
    previous = '0' * 64
    total = 0
    for sequence, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {'sequence', 'previous_sha256', 'entry_sha256', 'payload_text'}:
            raise LedgerSummaryError('Malformed financial audit event.')
        payload = entry['payload_text']
        if type(entry['sequence']) is not int or entry['sequence'] != sequence or entry['previous_sha256'] != previous:
            raise LedgerSummaryError('Financial audit history has a sequence or chain gap.')
        if not isinstance(payload, str) or not isinstance(entry['entry_sha256'], str) or not _HASH.fullmatch(entry['entry_sha256']):
            raise LedgerSummaryError('Malformed financial audit hash or payload.')
        content = payload.encode('utf-8')
        total += len(content)
        if total > MAX_AUDIT_BYTES:
            raise LedgerSummaryError('Financial audit history exceeds the byte limit; no partial history was produced.')
        digest = hashlib.sha256(bytes.fromhex(previous) + content).hexdigest()
        if digest != entry['entry_sha256']:
            raise LedgerSummaryError('Financial audit payload does not match its recorded hash.')
        try:
            value = parse_review_json(payload)
        except (ValueError, TypeError) as error:
            raise LedgerSummaryError('Financial audit payload is not unambiguous JSON.') from error
        if (not isinstance(value, dict) or value.get('schema_version') != 'loupe.financial.audit_event/1'
            or value.get('case_id') != case_id or type(value.get('sequence')) is not int
            or value['sequence'] != sequence
            or not isinstance(value.get('source_table'), str)
            or value.get('operation') not in AUDIT_COVERAGE.get(value.get('source_table'), [])):
            raise LedgerSummaryError('Financial audit payload scope or sequence is inconsistent.')
        previous = digest
    if expected_head_sha256 is not None and (not isinstance(expected_head_sha256, str)
        or not _HASH.fullmatch(expected_head_sha256) or expected_head_sha256 != previous):
        raise LedgerSummaryError('Financial audit head differs from the supplied checkpoint.')
    return dict(schema_version='loupe.financial.audit_verification/1', case_id=case_id,
        event_count=len(entries), head_sha256=previous,
        status='verified_recorded_chain' if entries else 'no_recorded_events',
        checkpoint_status='matches_supplied_head' if expected_head_sha256 is not None else 'not_supplied')


def capture_financial_audit_chain(session, *, case_id):
    entries = []
    total = 0
    rows = session.scalars(select(FinancialAuditEvent).where(FinancialAuditEvent.case_id == case_id)
        .order_by(FinancialAuditEvent.sequence).limit(MAX_AUDIT_EVENTS + 1).execution_options(yield_per=100))
    for row in rows:
        total += len(row.payload_text.encode('utf-8'))
        if len(entries) >= MAX_AUDIT_EVENTS or total > MAX_AUDIT_BYTES:
            raise LedgerSummaryError('Financial audit history exceeds the export limit; no partial history was produced.')
        entries.append(dict(sequence=row.sequence, previous_sha256=row.previous_sha256,
            entry_sha256=row.entry_sha256, payload_text=row.payload_text))
    verification = verify_financial_audit_chain(entries, case_id=case_id)
    return dict(schema_version='loupe.financial.audit_chain/1', case_id=str(case_id),
        verification=verification, entries=entries, coverage=AUDIT_COVERAGE,
        installed_by_migration='20260910_financial_audit_chain',
        coverage_migrations=['20260910_financial_audit_chain','20260910_audit_state_changes'],
        hash_algorithm='SHA-256(previous hash as 32 bytes || exact payload_text UTF-8 bytes)',
        limitation='Prospective database trigger history for the listed tables and operations only. Earlier records were not backfilled. Private run fields and evidence storage paths, errors, profile metadata and document text are represented by digests, not plaintext. Actors use case-bound authorized request context when available, otherwise source records or unavailable identity; an ingestion-run actor does not identify who caused each later run update. This covers listed ledger/evidence registration/Workspace operations since their respective migrations, not complete custody, source preparation replacements, graph/entity merges or export history. Database guards reject updates, deletes and truncation, but a database owner can disable them. No external timestamp or independently retained head was checked; an internally consistent chain alone cannot detect wholesale rewriting or tail removal.')
