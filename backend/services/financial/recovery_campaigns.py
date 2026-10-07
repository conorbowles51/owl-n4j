"""Explicit reader repair manifests; deployment alone is not a reread request.

Reader-specific campaigns identify demonstrated fixes and exact earlier reader
revisions. The authorized unresolved-work follow-up has its own content and
disposition eligibility policy; it is not a generic parser-version sweep.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecoveryCampaign:
    release: str
    affected_readers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    eligible_outcomes: tuple[str, ...] = ('review',)
    initial_snapshot: bool = False
    source_probe: str | None = None
    unresolved_followup: bool = False
    repair_of: str | None = None
    # Re-read held batch statements whose retained reading was produced by an
    # exact earlier engine revision (affected_readers names engine source files).
    batch_reread: bool = False

    def __post_init__(self):
        if not self.release or len(self.release) > 64:
            raise ValueError('Recovery campaigns require a stable release identifier of at most 64 characters.')
        if not self.initial_snapshot and not self.affected_readers and not self.unresolved_followup:
            raise ValueError('A selective recovery campaign must identify its affected readers and prior revisions.')
        if any(not versions or any(not isinstance(version, str) or not version for version in versions)
               for versions in self.affected_readers.values()):
            raise ValueError('Recovery reader revisions must be explicit nonempty strings.')

    def eligible(self, previous, observed_readers=None):
        if self.initial_snapshot:
            return True
        if self.batch_reread:
            # The retained reading's own runtime record is the evidence; there
            # is no earlier recovery outcome to qualify a held batch statement.
            observed = observed_readers or {}
            return any(observed.get(reader) in versions for reader, versions in self.affected_readers.items())
        if previous is None or previous.status not in self.eligible_outcomes:
            return False
        observed = observed_readers if observed_readers is not None else (previous.result or {}).get('readers') or {}
        return any(str(observed.get(reader, '')) in versions
                   for reader, versions in self.affected_readers.items())


INITIAL_RELEASE = 'statement-recovery-2026-09-24-v1'
FOLLOWUP_RELEASE = 'statement-recovery-2026-09-25-unresolved-v1'
RESTORED_REPAIR_RELEASE = 'statement-recovery-2026-09-25-restored-v2'
ANDREWS_BALANCE_RELEASE = 'statement-recovery-2026-09-25-andrews-balances-v1'
READER_RECOVERY_RELEASE = 'statement-recovery-2026-10-02-readers-v1'
READER_RECOVERY_FLAG = 'LOUPE_FINANCIAL_READER_RECOVERY'
# Exact SHA-256 of every committed evidence-engine pdf_extraction.py that wrote
# a PDF processing record (the record exists from 7b0013fb, 10 Sept), oldest
# first, up to and including 41e64eca (2 Oct, scan preparation for degraded
# and tilted scans), plus c-image-fields' file (cc9c6224, revision v13, only
# ever read the benchmark corpus). The current file (wave 5 merged: identical
# to c-andrews-residue's 3f00cf5d, revision v13; BBVA and Capital One
# unreadable money cells reread from their own cell, held Andrews money cells
# take the printed reading their agreed controls pin, embedded OCR layers that
# left printed lines unread replaced by the page image) is deliberately absent
# so a reading made by this release is never selected again. Since 29 Sept the
# engine gained: Andrews amount/balance crop reread (bb3ccef3), money-cell crop
# verification (0f75eddc), the pinned generic repair (13d03dbe), the glyph
# second reader (7bd84c16), scan preparation (41e64eca), the BBVA / Capital One
# cell reread and the pinned Andrews reading (wave 5). Unknown or unrecorded
# fingerprints are never swept. r1-reproduced (revision v14) added the wave-5
# file 6d388613: its readings called pages of small image tiles under an
# invisible OCR layer born-digital, so their money cells were never
# crop-verified. r3-andrews (revision v15) added r1-reproduced's file 5eca9825:
# its readings never crop-verified Andrews cells that join the amount and the
# running balance (they were parsed unchecked) and held every Andrews page
# carrying a club share. If a later change edits pdf_extraction.py, add the
# digest of the current file here.
AFFECTED_EXTRACTION_SHA256 = (
    '838372af7b656fa02f655aaa564582ff7ba15c5c17ff46020935ce3356152495',  # 7b0013fb
    '8f9e668367c9c3c9f577e1357cd8130952d9206742a653b6a0a42b1da1d62489',  # 14edbfec
    '419d9cbb27f0635d29f965c9d519937b07ab7d900136f28cdf68be5870df2dd4',  # 5ae7ef47
    '4f5a75a7bc6975e0d2249a4f9d5f7d9eae2d699e0dc60e14f852ca035cdc6a65',  # 2117ae62
    'ea91148920ad6cd893bdb3b7a122567cc462bc0087d7469b6706240dd7423c85',  # 1e006ae1
    '2550c8214ce3540d6a8973467477518462078d4777d4d65da9c165c3b1c35e92',  # a465f6fc
    '0bc79a33b9a70d3c533828715debb9d31677b3e529a90b8d843fe474075f4d0b',  # 60b6706a
    'ec9cfca7b4120060c7292491f83daccfb9f0591f7e66d90f950a93638ac1d5b4',  # b9414962
    '05b595733283c2f77483f6348aab948d65c57d650293dd2709d4be26d9653efc',  # d9a04e8a
    '56b70de3562c0919646342b5a2ee260db7e17f11ffc2fe97e817581022bf26b4',  # e886aff6
    '35b7854d7f4e7c5325a5ef34c8c99d690b8fee1d6bb241a26a28134d27a5f253',  # a48958e0
    '773d3e88130b2958009a47ed658235c31643f2351678974693a3fbfad3b58bd7',  # bb3ccef3
    '3af21e5e970dfee0346c6789a6236dc6386fccaaf5216ca0bab5a55d845766d1',  # 0f75eddc
    '1084b5e6882ec589595bd4fe5ab4a07618e12797e803e837995c2324aa8686c3',  # 13d03dbe
    'e6526e20f4c5f001281a019c2242a355340dd35fac4af1e361fe08d8c4b4ff5f',  # 7bd84c16
    '003d53a6ec546adf97032e01ac476e4dd1bada96073a1ee9efc3de987f4a44df',  # 41e64eca
    'f0afcaf91e36bfec1577d6d2ace6e693c421fb0b72055d5e55e41921bf87a835',  # cc9c6224 (c-image-fields)
    '6d388613fcdb471890f68921103ad8db18f1a4db91bedc44049e9d28a394db1e',  # wave 5 (v13)
    '5eca9825fe4fdd4c06783eb7820fb91d8bc359cd8d77bb45487e307161d6942e',  # 7b00e2f3 r1-reproduced (v14)
)
READER_RECOVERY = RecoveryCampaign(READER_RECOVERY_RELEASE, {'pdf_extraction.py': AFFECTED_EXTRACTION_SHA256},
    batch_reread=True)
CAMPAIGNS = (RecoveryCampaign(INITIAL_RELEASE, initial_snapshot=True),
    RecoveryCampaign(FOLLOWUP_RELEASE, unresolved_followup=True),
    RecoveryCampaign(RESTORED_REPAIR_RELEASE, unresolved_followup=True, repair_of=FOLLOWUP_RELEASE))
# Retain the measured diagnosis without automatically scheduling a new campaign:
# the current Andrews sample has not demonstrated an additional admitted period.
REGISTERED_CAMPAIGNS = (*CAMPAIGNS,
    RecoveryCampaign(ANDREWS_BALANCE_RELEASE, {'andrews-share-statement': ('statement-review-v31',)},
        source_probe='andrews-unreadable-running-balance-v1'),
    READER_RECOVERY)


def reader_recovery_enabled(environ=None):
    """Off unless explicitly switched on: Neil decides activation."""
    value = (os.environ if environ is None else environ).get(READER_RECOVERY_FLAG, '')
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


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
