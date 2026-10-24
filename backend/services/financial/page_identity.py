"""Whether two PDFs are the same document page for page, whatever their bytes or reading.

Productions repeat evidence: the same statement arrives twice, saved again by
another program, so the bytes differ while every page shows the same thing.
Equal bytes already make two uploads one document. This module extends that to
equal pages: every page of the file is rendered at a fixed small resolution and
the pixels are hashed; the file's identity is the hash of its page hashes in
order. Two files with the same identity look identical on every page, so a
statement read from one is the statement printed in the other, however either
reading went (another reader, another institution wording, a failed reading).

It is computed once per file when its reading is prepared and stored on the
evidence file with the bytes and renderer it came from. Only identities of the
same version, renderer and resolution are compared; anything else (a file
prepared before this existed, another renderer release) is simply not a page
copy, so the copy rule falls back to bytes and readings.

What it does not do: two scans of one sheet of paper, or a reprint with another
resolution, render differently and are not page copies. Measured on the real
statements (r10-copies) a tolerant image comparison could not tell a page from
the same account's next month, so no tolerance is applied: identity or nothing.

Like ``page_render`` it is written against the shape of a fitz document
(``page_count``, ``load_page``, a page's ``rect`` and ``get_pixmap``) so the
logic is testable without the library; the caller that opens the PDF owns the
guarded import.
"""
from __future__ import annotations

import hashlib
import logging

log = logging.getLogger(__name__)

METADATA_KEY = 'financial_page_identity'
VERSION = 'page-identity-v1'
# Equal at 40 and at 60 dpi on every pixel-identical real copy measured
# (t-visual-v05, v06; r10-copies whole set); 40 keeps a 300-page file cheap.
DPI = 40
# Switch: False stops computing identities, and stored ones are not used.
ENABLED = True


def compute(document, *, renderer: str, dpi: int = DPI) -> dict | None:
    """The page identity of a fitz-shaped ``document``; None for a document without pages."""
    count = document.page_count
    if count < 1:
        return None
    zoom = dpi / 72.0
    pages = hashlib.sha256()
    for index in range(count):
        page = document.load_page(index)
        pixmap = page.get_pixmap(matrix=(zoom, 0.0, 0.0, zoom, 0.0, 0.0), alpha=False)
        digest = hashlib.sha256(f'{pixmap.width}x{pixmap.height}:'.encode())
        digest.update(pixmap.samples)
        pages.update(digest.digest())
    return dict(version=VERSION, renderer=renderer, dpi=dpi, page_count=count, identity=pages.hexdigest())


def stored(file) -> dict | None:
    """The file's stored page identity when it is comparable now, else None.

    It must belong to the file's current bytes: an identity recorded for other
    bytes says nothing about these.
    """
    if not ENABLED:
        return None
    value = (getattr(file, 'metadata_', None) or {}).get(METADATA_KEY)
    if not isinstance(value, dict) or value.get('version') != VERSION or value.get('dpi') != DPI:
        return None
    if not value.get('identity') or not value.get('renderer'):
        return None
    if value.get('source_sha256') and getattr(file, 'sha256', None) and value['source_sha256'] != file.sha256:
        return None
    return value


def same_pages(left, right) -> bool:
    """Two evidence files whose every page renders identically (stored identities)."""
    a, b = stored(left), stored(right)
    return bool(a and b and a['renderer'] == b['renderer'] and a['page_count'] == b['page_count']
                and a['identity'] == b['identity'])


def _renderer(fitz) -> str:
    return 'pymupdf-' + str(getattr(fitz, 'VersionBind', '') or getattr(fitz, '__version__', ''))


def renderer() -> str | None:
    """The renderer this process would use, or None without PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return None
    return _renderer(fitz)


def needs_record(file) -> bool:
    """True for a PDF without a comparable identity from this process's renderer."""
    if not ENABLED or file is None or not str(getattr(file, 'original_filename', '') or '').lower().endswith('.pdf'):
        return False
    current = stored(file)
    return not (current and current['renderer'] == renderer())


def identity_of_path(path, sha256) -> dict | None:
    """The page identity of the PDF at ``path`` (bytes ``sha256``), or None.

    Never raises: a file that cannot be rendered (missing, encrypted, damaged)
    has no identity and is compared by bytes and readings as before. Takes no
    database session, so callers render outside their locks.
    """
    try:
        import fitz
    except ImportError:
        return None
    try:
        with fitz.open(str(path)) as document:
            value = compute(document, renderer=_renderer(fitz))
    except Exception as error:
        log.info('Page identity not computed: %s', type(error).__name__)
        return None
    if value is not None:
        value['source_sha256'] = sha256
    return value


def store(file, value) -> None:
    """Record ``value`` on the evidence file; the caller holds its row and commits."""
    metadata = dict(file.metadata_ or {})
    metadata[METADATA_KEY] = value
    file.metadata_ = metadata


def same_document_files(session, case_id, file) -> dict:
    """{file id: basis} of the other files in the case that hold this same document.

    ``identical_bytes`` for the same sha256, ``identical_pages`` for every page
    rendering identically. Lineage versions of one original are included; the
    callers already govern those by their replacement rules.
    """
    from sqlalchemy import select, or_
    from postgres.models.evidence import EvidenceFile
    own = stored(file)
    conditions = []
    if getattr(file, 'sha256', None):
        conditions.append(EvidenceFile.sha256 == file.sha256)
    if own:
        conditions.append(EvidenceFile.metadata_[METADATA_KEY]['identity'].as_string() == own['identity'])
    if not conditions:
        return {}
    result = {}
    for other in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
            EvidenceFile.id != file.id, or_(*conditions))):
        if file.sha256 and other.sha256 == file.sha256:
            result[str(other.id)] = 'identical_bytes'
        elif same_pages(file, other):
            result[str(other.id)] = 'identical_pages'
    return result
