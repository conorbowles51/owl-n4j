"""Readable bibliography entries from authorized, saved source results.

This projects presentation only. The authored reference and saved source receipt
remain unchanged, and unresolved references are visible rather than invented.
"""
from __future__ import annotations

import re
from uuid import UUID


def _locator(result):
    pages = [p for p in result.get('pages', []) if isinstance(p, dict)]
    numbers = sorted({p['page_number'] for p in pages
                      if isinstance(p.get('page_number'), int) and p['page_number'] > 0})
    if not numbers:
        return None
    physical = all(p.get('location_kind') == 'source_page' for p in pages)
    noun = ('Page' if len(numbers) == 1 else 'Pages') if physical else ('Text part' if len(numbers) == 1 else 'Text parts')
    ranges, start, end = [], numbers[0], numbers[0]
    for number in numbers[1:]:
        if number == end + 1:
            end = number
        else:
            ranges.append(str(start) if start == end else f'{start}–{end}')
            start = end = number
    ranges.append(str(start) if start == end else f'{start}–{end}')
    return noun + ' ' + ', '.join(ranges)


def present_sources(payload, result_store):
    """Call after checking access; never mutates a saved payload or source result."""
    if not isinstance(payload.get('sources'), list):
        return payload
    entries = []
    for source in payload['sources']:
        result_id = source.get('result_id') if isinstance(source, dict) else source
        if not isinstance(result_id, str) or not re.fullmatch(r'res_[A-Za-z0-9_-]+', result_id):
            entries.append(source)
            continue
        entry = dict(source) if isinstance(source, dict) else {'result_id': result_id}
        result = result_store.get(result_id, {})
        result = result if isinstance(result, dict) else {}
        label = entry.get('label') or entry.get('title')
        if label == result_id:
            label = None
        try:
            identity = str(UUID(str(result.get('evidence_id'))))
        except (ValueError, TypeError, AttributeError):
            identity = None
        if identity and result.get('document_name'):
            entry['label'] = label or result['document_name']
            entry.setdefault('url', f'doc://{identity}')
            locator = _locator(result)
            if locator:
                entry.setdefault('locator', locator)
        else:
            entry['label'] = label or 'Source reference unavailable'
            entry.setdefault('locator', 'Reopen the saved source and confirm its citation.')
        entries.append(entry)
    return {**payload, 'sources': entries}
