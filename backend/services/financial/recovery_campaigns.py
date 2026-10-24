"""Explicit reader repair manifests, and the engine-release re-read of held statements.

Reader-specific campaigns identify demonstrated fixes and exact earlier reader
revisions. The authorized unresolved-work follow-up has its own content and
disposition eligibility policy; it is not a generic parser-version sweep.

The engine-release campaign (``reader_campaign``) is the one generic sweep,
and only of held batch statements nobody has worked on: a statement whose
retained reading records a ``pdf_extraction.py`` other than the engine source
deployed now is read again by its batch (``recovery_readers``). Its release id
names the current engine source, so each engine release is one durable,
resumable snapshot per case; a reading the current engine made, or one with no
valid engine record, is never selected. On by default; env
``LOUPE_FINANCIAL_READER_RECOVERY=0`` turns it off.
"""
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path


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
    # Engine source file -> its digest deployed now (None: unknown). A batch
    # re-read campaign with current readers selects a recorded reading whose
    # digest differs from it, instead of an exact list of earlier digests.
    current_readers: dict[str, str | None] = field(default_factory=dict)

    def __post_init__(self):
        if not self.release or len(self.release) > 64:
            raise ValueError('Recovery campaigns require a stable release identifier of at most 64 characters.')
        if self.current_readers and not self.batch_reread:
            raise ValueError('Only a batch re-read campaign may select readings by the current reader.')
        if (not self.initial_snapshot and not self.affected_readers and not self.unresolved_followup
                and not self.current_readers):
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
            if self.current_readers:
                # Recorded by another engine source than the one deployed now.
                # An unknown current source or an unrecorded reading never qualifies.
                return any(current and observed.get(reader) and observed[reader] != current
                           for reader, current in self.current_readers.items())
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
# carrying a club share. r4-cards (revision v16) added r3-andrews' file 3e234391:
# its readings held every card credit whose minus the crops lost, every card
# row date whose slash the layer read as 1, every summary balance whose dollar
# sign it read as S, and kept garbled Merrick layers that cannot read the
# statement date. r5-andrews-cards (revision v17) added r4-cards' file b9248b80:
# its readings stored no printed readings for held money cells, so no
# statement-wide control could pin a cell its own page could not (first and
# last payments of a page), offered no page reading whose minus the crops
# read as 2 or +, and pinned no cell whose neighbour was itself only pinned.
# r8-mt-engine (revision v20) added r7-alex-queue's file 8f3539f3 (v19): on vector-text pages its
# readings lost every printed line page OCR skipped (an addressee's name line, summary lines), kept
# dates whose two 1s stand a space-wide bearing apart as OCR misread them ('41/05/2021'), and did not
# record which printed lines stayed unread, so no addressless name block could be checked.
# r9-engine-santander (revision v21) added r8-mt-engine's file ed905742 (v20): on vector-text pages it read a
# printed line's label without its amount whenever the amount printed a thousands comma (the comma was
# grouped as a line of its own), so a closing line read as 'SALDO FINAL DEL PERIODO:' with no amount and
# the Santander closing reread no longer ran.
# The layer guard (revision v22) added r9-engine-santander's file 3d3b9d2b (v21): its targeted re-reads
# could be outvoted by skipped-line layer rows overlapping them, so a period the page proved without the
# layer was held.
# r11-bbva-vector (revision v23) added the layer guard's file ee536c50 (v22): on vector-text pages it kept a
# word OCR read with characters lost inside it (an operation date read '14NAR' over the outlines of a printed
# date) unread, so the movement line carried no readable date, and could rebuild a word from the outlines
# under a box that had cut a printed figure off beside it, so an amount lost a figure.
# r12-kapital (revision v24) added r11-bbva-vector's file 8a06b0ca (v23): on vector-text pages a day of the month
# OCR skipped at the start of a movement line (printed against the table's left rule) was read by no word, so
# the movement stayed undated and its period was held.
# r13-andrews (revision v25) added r12-kapital's file c8d57e3d (v24): on Andrews pages a money cell whose page
# reading was damaged beyond every money reading (a colon or slash for the point, a hyphen inside the figures)
# was never cropped, and a held cell kept only the readings the crops repeated, so a period whose printed
# value was the page reading alone, or a minority crop reading, stayed held.
# This exact list is history: the engine-release campaign (reader_campaign)
# selects any reading recorded by another pdf_extraction.py than the deployed
# one, so a later engine change needs no digest added here.
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
    '3e2343916ad66c94b85230947d48841235f8c4ff22963adb1f7c3a58c6591149',  # bffe7375 r3-andrews (v15)
    'b9248b807d535565e21969c81fcc59adb148cf1d6f185232958afb181bc129a1',  # r4-cards (v16)
    '015bd1d2a28867ae8771cb7a69b67fca4e30302468e394b93d572fcef6e8800a',  # r5-andrews-cards (v17)
    '8f3539f3afca7d9e4d613967aff51000e1c0fd93688f2e35a6534cb1628f0b37',  # 7b877d0b r7-alex-queue (v19)
    'ed905742085b39bead123c80c47af29dd08f3c73790a8769e964b4e39c266815',  # 7c215ef1 r8-mt-engine (v20)
    '3d3b9d2b0ab124c1722573dbde774c5030c8eddf2feb3daaacf284873a837e13',  # 3a97716c r9-engine-santander (v21)
    'ee536c5020bcd44185621b179ceb9e2a0db9329e81b49eb676bf37ee602f30c9',  # 060d7470 layer guard (v22)
    '8a06b0ca727b00b602ea636e451f27cff0daba645ee081ea841916a9e3b7612e',  # 24593077 r11-bbva-vector (v23)
    'c8d57e3dda4e5aef378eac7da4cd50157aad94d84d71986b25e1a99b60d3a38a',  # 2a6df8be r12-kapital (v24)
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
    """On unless switched off (``LOUPE_FINANCIAL_READER_RECOVERY=0``, false, no or off)."""
    value = (os.environ if environ is None else environ).get(READER_RECOVERY_FLAG, '')
    return value.strip().lower() not in ('0', 'false', 'no', 'off')


# Engine-release campaigns: one release id per deployed engine source.
READER_RELEASE_PREFIX = 'statement-recovery-engine-'
ENGINE_READER_SOURCE = Path(__file__).resolve().parents[3] / 'evidence-engine' / 'app' / 'pipeline' / 'pdf_extraction.py'
_engine_digest = []


def current_engine_reader():
    """SHA-256 of the deployed engine's pdf_extraction.py (the digest its readings record), or None.

    Read once per process from the same tree the engine image is built from.
    None (the source is not beside the backend) schedules nothing.
    """
    if not _engine_digest:
        try:
            _engine_digest.append(hashlib.sha256(ENGINE_READER_SOURCE.read_bytes()).hexdigest())
        except OSError:
            _engine_digest.append(None)
    return _engine_digest[0]


def is_reader_release(release):
    return bool(release) and release.startswith(READER_RELEASE_PREFIX)


# Which held statements the engine-release campaign may hand back (recovery_readers.classify). The snapshot is
# taken once per release id, so a change to that selection must change the id too, or a deploy carrying it
# never looks at a case the deployed engine already snapshotted. Bump on every change to the selection rules.
# v2 (aq-b-santander): a removal recorded before the batch holding the restart was made no longer protects it,
# and a statement already settled without a person's work (saved, or set aside by the System) no longer
# protects the held statements of its file (recovery_readers.SETTLED_SIBLINGS), and a batch file whose
# preparation failed and that holds nothing is an idle member of its original (FAILED_MEMBER_IDLE); a held
# copy of an account and period the case already saved is left for comparison (COPY_OF_SAVED_PROTECTS).
READER_SELECTION = 'held-selection-v2'


def reader_release_id(engine_digest):
    """The campaign id of an engine source under the current selection rules (at most 64 characters)."""
    return READER_RELEASE_PREFIX + hashlib.sha256(f'{engine_digest}:{READER_SELECTION}'.encode()).hexdigest()[:32]


def reader_campaign(release=None):
    """The engine-release campaign: held statements read by another engine source than today's.

    Without ``release``, the campaign of the engine deployed now under today's
    selection rules (None when its source is unknown). With an earlier
    release's id (its run is still being followed), the same rule against
    today's engine: a statement read by today's engine is never read again.
    """
    current = current_engine_reader()
    if release is None:
        if current is None:
            return None
        release = reader_release_id(current)
    return RecoveryCampaign(release, current_readers={'pdf_extraction.py': current}, batch_reread=True)


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
    if is_reader_release(release):
        return reader_campaign(release)
    return next((campaign for campaign in REGISTERED_CAMPAIGNS if campaign.release == release), None)
