"""Stable identifiers for phone rows (02 section 1.2).

``record_uid`` and ``file_uid`` are uuid5 of 01's positional key under a fixed namespace. 01's ordinals are a
function of the report bytes, so the identifiers are the same on every re-run and resume. The engine writes
``file_uid`` on each ``phone_files`` row at capture (``evidence-engine/app/phone/ids.py`` holds the same namespace;
a test on each side pins it).
"""
from __future__ import annotations

import uuid

PHONE_NS = uuid.UUID("8fa2f9a7-e6b9-4809-a082-208cf14fa25c")


def record_uid(extraction_id, document_index: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(PHONE_NS, f"{extraction_id}/{document_index}/r{ordinal}")


def file_uid(extraction_id, document_index: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(PHONE_NS, f"{extraction_id}/{document_index}/f{ordinal}")
