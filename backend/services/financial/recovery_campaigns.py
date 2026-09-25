"""Explicit reader repair manifests; deployment alone is not a reread request.

Add a campaign only with a demonstrated reader fix and the exact earlier reader
revisions it repairs. Successful, removed, skipped and unidentified readings are
not swept back into processing by a generic version bump.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecoveryCampaign:
    release: str
    affected_readers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    eligible_outcomes: tuple[str, ...] = ('review',)
    initial_snapshot: bool = False
    source_probe: str | None = None

    def __post_init__(self):
        if not self.release or len(self.release) > 64:
            raise ValueError('Recovery campaigns require a stable release identifier of at most 64 characters.')
        if not self.initial_snapshot and not self.affected_readers:
            raise ValueError('A selective recovery campaign must identify its affected readers and prior revisions.')
        if any(not versions or any(not isinstance(version, str) or not version for version in versions)
               for versions in self.affected_readers.values()):
            raise ValueError('Recovery reader revisions must be explicit nonempty strings.')

    def eligible(self, previous, observed_readers=None):
        if self.initial_snapshot:
            return True
        if previous is None or previous.status not in self.eligible_outcomes:
            return False
        observed = observed_readers if observed_readers is not None else (previous.result or {}).get('readers') or {}
        return any(str(observed.get(reader, '')) in versions
                   for reader, versions in self.affected_readers.items())


INITIAL_RELEASE = 'statement-recovery-2026-09-24-v1'
ANDREWS_BALANCE_RELEASE = 'statement-recovery-2026-09-25-andrews-balances-v1'
CAMPAIGNS = (RecoveryCampaign(INITIAL_RELEASE, initial_snapshot=True),)
# Retain the measured diagnosis without automatically scheduling a new campaign:
# the current Andrews sample has not demonstrated an additional admitted period.
REGISTERED_CAMPAIGNS = (*CAMPAIGNS,
    RecoveryCampaign(ANDREWS_BALANCE_RELEASE, {'andrews-share-statement': ('statement-review-v31',)},
        source_probe='andrews-unreadable-running-balance-v1'))


def source_reader_evidence(session, file, campaign):
    """Qualify a legacy reading by its recorded software and actual defect.

    Older recovery results lack reader inventory. Do not guess from filenames,
    dates or empty rows: require the validated preparation fingerprint and a
    recognized Andrews payment whose printed running balance remains unreadable.
    """
    if campaign.source_probe != 'andrews-unreadable-running-balance-v1':
        return None
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from services.financial.pdf_processing_manifest import validate_pdf_processing_manifest
    from services.financial.statement_reading_quality import sources_from_tables
    from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
    document = session.get(EvidenceDocumentText, file.id)
    if document is None:
        return {}
    try:
        preparation = validate_pdf_processing_manifest(document.processing_manifest)
    except ValueError:
        return {}
    if not preparation:
        return {}
    content = preparation['content']
    # Exact retained v6 extractor source observed in the supplied sample audit.
    # Unknown versions remain available for explicit review; they are not swept.
    if (content['source_files_sha256'].get('pdf_extraction.py') !=
            'ec9cfca7b4120060c7292491f83daccfb9f0591f7e66d90f950a93638ac1d5b4'
            or content['settings'].get('pdf_reading_mode', 'automatic') != 'automatic'):
        return {}
    for geometry in session.scalars(select(EvidenceTableGeometry).where(
            EvidenceTableGeometry.evidence_file_id == file.id,
            EvidenceTableGeometry.engine_job_id == document.engine_job_id)):
        for source in sources_from_tables(geometry.payload):
            page = andrews_page(source, allow_unbranded=True)
            if not page:
                continue
            scope = dict(page_number=source['page_number'], table_index=source['table_index'],
                heading_rows=page['heading_rows'], row_indices=[r['row_index'] for r in source['rows'] if r['row_index'] >= page['body_start']])
            proposal = propose_andrews_statement([source], 'USD', dict(period_start=page['start'], period_end=page['end'], sources=[scope]))
            if any(not row['excluded'] and row['kind'] == 'transaction' and
                   row['fields'].get('statement_layout') == 'andrews-share-statement' and
                   'balance' not in row['fields'] for row in proposal['rows']):
                return {'andrews-share-statement': 'statement-review-v31'}
    return {}


def manifest(release):
    return next((campaign for campaign in REGISTERED_CAMPAIGNS if campaign.release == release), None)
