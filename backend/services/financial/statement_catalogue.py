"""A multi-statement file's statement catalogue, stored once per file.

Every saved period used to carry its file's whole ``statement_choices`` inside
``statement_import_original``: ~0.6 MB per period of a 217-period production,
102 MB of the 130 MB of saved metadata for one file. PostgreSQL detoasts the
whole record to read any key of it, so every duplicate check over the file's
saved periods grew with every import.

A saved period now keeps only its own choice in ``statement_choices`` and a
reference to the catalogue it was read with:

- ``statement_import_catalogue_sha256``: digest of the whole catalogue;
- ``statement_import_original_full_sha256``: digest of the reading as it was
  read, catalogue included (the value ``statement_import_original_sha256``
  used to hold), so the full reading can still be proved after rejoining;
- ``statement_import_catalogue``: the catalogue itself, on exactly one saved
  record of the file per distinct catalogue (the first one saved with it).

``statement_import_original_sha256`` is the digest of what is stored, so every
integrity check over saved records (`_digest(original) == sha256`) is
unchanged. Records saved before this change stay as they are and read the same.
"""
from copy import deepcopy

from sqlalchemy import select

from services.financial.pdf_candidates import _digest

CATALOGUE = 'statement_import_catalogue'
CATALOGUE_SHA256 = 'statement_import_catalogue_sha256'
FULL_SHA256 = 'statement_import_original_full_sha256'


def compact_original(proposal, statement_id):
    """(stored reading, catalogue or None). The catalogue is None when there is nothing to factor out."""
    choices = proposal.get('statement_choices') if isinstance(proposal, dict) else None
    if not isinstance(choices, list) or len(choices) < 2:
        return proposal, None
    stored = dict(proposal)
    stored['statement_choices'] = [choice for choice in choices
                                   if isinstance(choice, dict) and choice.get('id') == statement_id]
    return stored, choices


def stored_reading(session, *, case_id, evidence_file_id, proposal, statement_id):
    """The metadata entries that record a reading on a saved period.

    The catalogue is written only when no record of this file already holds
    the same catalogue. Saves of one file are serialised by the case lock, so
    a concurrent second copy can only arise across cases (it is harmless).
    """
    stored, catalogue = compact_original(proposal, statement_id)
    entries = dict(statement_import_original=stored, statement_import_original_sha256=_digest(stored))
    if catalogue is None:
        return entries
    digest = _digest(catalogue)
    entries[CATALOGUE_SHA256] = digest
    entries[FULL_SHA256] = _digest(proposal)
    if catalogue_holder(session, case_id=case_id, evidence_file_id=evidence_file_id, digest=digest) is None:
        entries[CATALOGUE] = dict(sha256=digest, choices=catalogue)
    return entries


def catalogue_holder(session, *, case_id, evidence_file_id, digest):
    """The id of the saved record of this file that holds the catalogue with this digest."""
    from postgres.models.financial import FinancialSourceDocument as Source
    # Compares one short key; the catalogue itself is never loaded here.
    return session.scalar(select(Source.id).where(
        Source.case_id == case_id, Source.evidence_file_id == evidence_file_id,
        Source.metadata_[CATALOGUE]['sha256'].as_string() == digest).order_by(Source.id).limit(1))


def saved_catalogue(session, document):
    """The whole statement catalogue a saved period was read with (old records: their own copy)."""
    from postgres.models.financial import FinancialSourceDocument as Source
    metadata = document.metadata_ or {}
    digest = metadata.get(CATALOGUE_SHA256)
    if not digest:
        return (metadata.get('statement_import_original') or {}).get('statement_choices') or []
    held = metadata.get(CATALOGUE)
    if not (held and held.get('sha256') == digest):
        holder_id = catalogue_holder(session, case_id=document.case_id,
                                     evidence_file_id=document.evidence_file_id, digest=digest)
        held = session.scalar(select(Source.metadata_[CATALOGUE]).where(Source.id == holder_id)) if holder_id else None
    if not held or _digest(held.get('choices')) != digest:
        raise ValueError('The statement catalogue this period was read with is not available.')
    return held['choices']


def full_original(session, document):
    """The reading exactly as it was read, catalogue included, proved against its recorded digest."""
    metadata = document.metadata_ or {}
    original = metadata.get('statement_import_original')
    if original is None or not metadata.get(CATALOGUE_SHA256):
        return original
    full = deepcopy(original)
    full['statement_choices'] = deepcopy(saved_catalogue(session, document))
    if _digest(full) != metadata.get(FULL_SHA256):
        raise ValueError('The saved reading does not match its recorded digest.')
    return full
