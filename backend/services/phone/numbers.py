"""Phone numbers for the rebuild (docs/cellebrite/02 section 8.2), on the pinned ``phonenumbers==9.0.31``.

``parse(text, region)`` returns ``(e164, display, valid, region_basis)``; a number written with ``+`` is parsed
with no region (PN-1), one without ``+`` under ``region`` (PN-2). Only a number the library reports valid has an
E.164 form (PN-3); its display is the library's INTERNATIONAL format (PN-4).
"""
from __future__ import annotations

import phonenumbers

PINNED = "9.0.31"


def parse(text, region="US", region_basis="assumed_default"):
    s = (text or "").strip()
    explicit = s.startswith("+")
    try:
        n = phonenumbers.parse(s, None if explicit else region)
    except phonenumbers.NumberParseException:
        return None, None, False, None
    basis = "explicit_plus" if explicit else region_basis
    if not phonenumbers.is_valid_number(n):
        return None, None, False, basis
    return (phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164),
            phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.INTERNATIONAL), True, basis)


def library_version():
    return getattr(phonenumbers, "__version__", None)
