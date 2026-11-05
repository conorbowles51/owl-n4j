"""Phone numbers for the rebuild (docs/cellebrite/02 section 8.2), on the pinned ``phonenumbers==9.0.31``.

``parse(text, region)`` returns ``(e164, display, valid, region_basis)``; a number written with ``+`` is parsed
with no region (PN-1), one without ``+`` under ``region`` (PN-2). Only a number the library reports valid has an
E.164 form (PN-3); its display is the library's INTERNATIONAL format (PN-4).
"""
from __future__ import annotations

from functools import lru_cache

import phonenumbers

PINNED = "9.0.31"


def regions() -> frozenset:
    """Every country code a phone can be read in (ISO 3166-1 alpha-2)."""
    return frozenset(phonenumbers.SUPPORTED_REGIONS)


@lru_cache(maxsize=None)
def region_name(region) -> str:
    """The country's name in words, from the library's own data; the code when it has none."""
    from phonenumbers import geocoder
    example = phonenumbers.example_number(region)
    return (geocoder.country_name_for_number(example, "en") if example else "") or region


@lru_cache(maxsize=1)
def region_list() -> list:
    """Every region with its name, by name."""
    return sorted(({"code": c, "name": region_name(c)} for c in regions()), key=lambda r: r["name"])


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
