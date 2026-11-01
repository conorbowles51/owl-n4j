"""Stable identifiers for phone rows (02 section 1.2): uuid5 of 01's positional key under a fixed namespace.

The backend holds the same namespace in ``backend/services/phone/ids.py`` (the engine never imports the backend);
a test on each side pins the value.
"""
from __future__ import annotations

import uuid

PHONE_NS = uuid.UUID("8fa2f9a7-e6b9-4809-a082-208cf14fa25c")


def record_uid(extraction_id, document_index: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(PHONE_NS, f"{extraction_id}/{document_index}/r{ordinal}")


def file_uid(extraction_id, document_index: int, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(PHONE_NS, f"{extraction_id}/{document_index}/f{ordinal}")
