"""Find unsupported precise details in prose that cites canonical document text.

This is a conservative consistency check, not an entailment or truth verifier. A
date occurring somewhere on a cited page does not prove the surrounding claim.
Missing dates, times and structured record identifiers do require correction or
an explicit, reproducible derived claim before a sourced report is complete.
"""
from __future__ import annotations

import re


_DOC = re.compile(r'doc://([0-9a-fA-F-]{36})(?:/(\d+))?')
_URL = re.compile(r'(?:https?://|doc://)[^\s<>\)\]]+')
_DATE = re.compile(r'(?<!\w)\d{4}-\d{2}-\d{2}(?!\w)')
_TIME = re.compile(r'(?<![\w:])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?![\w:])')
_IDENTIFIER = re.compile(r'(?<![\w-])(?=[A-Za-z\d-]*[A-Za-z])(?=[A-Za-z\d-]*\d)[A-Za-z\d]+(?:-[A-Za-z\d]+)+(?![\w-])')


def _sections(data):
    for key in ('sections', 'children'):
        for section in data.get(key, []) or []:
            if isinstance(section, dict):
                yield section
                yield from _sections(section)


def inspect_source_grounding(data, result_store, *, checked_bindings=()):
    pages = {}
    for result_id, result in result_store.items():
        if not isinstance(result, dict) or not result.get('evidence_id') or not isinstance(result.get('pages'), list):
            continue
        identity = str(result['evidence_id']).lower()
        for page in result['pages']:
            if isinstance(page, dict) and page.get('page_number') is not None:
                key = (identity, str(page['page_number']))
                # Distinct revisions are not silently combined into a corroborating source.
                entry = pages.setdefault(key, {})
                entry.setdefault(result.get('revision'), {'text': page.get('text') or '',
                    'missing': bool(page.get('text_missing')), 'result_id': result_id})
    checked, issues = [], []
    sections = list(_sections(data))
    has_citations = any(_DOC.search(str(section.get('content') or '')) for section in sections)
    for section in sections:
        prose = str(section.get('content') or '')
        citations = list(dict.fromkeys((m.group(1).lower(), m.group(2)) for m in _DOC.finditer(prose)))
        if not citations:
            visible = _URL.sub('', prose)
            hypothetical = re.search(r'\b(?:assumptions?|hypothetical|proposed|illustrative)\b', str(section.get('heading') or ''), re.I)
            if pages and has_citations and not hypothetical and any(pattern.search(visible) for pattern in (_DATE, _TIME, _IDENTIFIER)):
                heading = section.get('heading') or section.get('id') or 'Section'
                issues.append(f'{heading}: precise details have no document citation in this section. Cite the actual pages used. Keep assumptions, proposals or hypothetical examples in a clearly labelled section so they cannot be mistaken for source facts.')
            continue
        scope, missing, ambiguous, sources = [], [], [], []
        for identity, number in citations:
            keys = [(identity, number)] if number else [key for key in pages if key[0] == identity]
            if not keys:
                missing.append(f'doc://{identity}')
            for key in keys:
                versions = pages.get(key, {})
                if len(versions) > 1:
                    ambiguous.append(f'doc://{key[0]}/{key[1]}')
                elif not versions or next(iter(versions.values()))['missing']:
                    missing.append(f'doc://{key[0]}/{key[1]}')
                else:
                    entry = next(iter(versions.values()))
                    scope.append(entry['text'])
                    sources.append({'result_id': entry['result_id'], 'page': key[1]})
        source = '\n'.join(scope)
        visible = _URL.sub('', prose)
        # Explicitly checked calculations can introduce a value absent from the
        # source; their exact rendered claim was verified by claim_validation.
        for binding in checked_bindings:
            if (binding.get('status') == 'checked' and binding.get('calculation')
                    and binding.get('location', {}).get('section_id') == section.get('id')):
                visible = visible.replace(binding['binding']['claim_text'], '')
        unsupported = {}
        for label, pattern in (('dates', _DATE), ('times', _TIME), ('identifiers', _IDENTIFIER)):
            normalize = (lambda value: ':'.join(str(int(p)) for p in value.split(':'))) if label == 'times' else str.casefold
            supported = {normalize(value) for value in pattern.findall(source)}
            absent = sorted({value for value in pattern.findall(visible) if normalize(value) not in supported})
            if absent:
                unsupported[label] = absent
        heading = section.get('heading') or section.get('id') or 'Cited section'
        if missing:
            issues.append(f'{heading}: cited source pages have not been read or have no readable text: ' + ', '.join(missing))
        if ambiguous:
            issues.append(f'{heading}: cited source pages have competing stored revisions; reread the current source and resolve the revision before completion: ' + ', '.join(ambiguous))
        for label, values in unsupported.items():
            issues.append(f'{heading}: {len(values)} {label} are absent from its cited source text: ' + ', '.join(values[:12])
                + ('. Read metadata.claim_evidence.source_grounding for the complete list.' if len(values) > 12 else '.')
                + ' Recheck the actual source and correct the prose; do not infer additional records from a pattern.')
        checked.append({'section_id': section.get('id'), 'sources': sources, 'missing_sources': missing,
            'ambiguous_sources': ambiguous, 'unsupported_details': unsupported,
            'status': 'needs_revision' if missing or ambiguous or unsupported else 'precise_details_located'})
    return {'sections': checked, 'issues': issues,
        'scope': 'ISO dates, clock times and hyphenated alphanumeric identifiers in document-cited sections are checked for presence in the cited canonical text. Presence is not entailment; other prose, source truth and analytical adequacy are not established.'}
