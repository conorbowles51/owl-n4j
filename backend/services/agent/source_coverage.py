"""Audit which canonical document characters were delivered by source-reading tools.

Retrieving a full source into a result store is distinct from exposing all of it to the
model. Paging previews never count as a complete reading. Receipts say delivered,
not understood, corroborated or true.
"""
from __future__ import annotations

import json

from langchain_core.messages import ToolMessage


def source_observations(messages, results):
    """Only source observations included in a projected model request count as delivered."""
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        identity, seen = payload.get('result_id'), set()
        while identity and identity not in seen:
            seen.add(identity)
            value = results.get(identity)
            if not isinstance(value, dict):
                break
            if value.get('evidence_id') and isinstance(value.get('pages'), list):
                if payload.get('data'):
                    yield message
                break
            identity = value.get('page_of')


def document_coverage(messages, results):
    documents, origins = {}, {}
    for result_id, value in results.items():
        if not isinstance(value, dict) or not value.get('evidence_id') or not isinstance(value.get('pages'), list):
            continue
        key = (str(value['evidence_id']), value.get('revision'))
        doc = documents.setdefault(key, {'evidence_id': key[0], 'revision': key[1], 'name': value.get('document_name'),
            'total_pages': value.get('page_count', 0), 'pages': {}, 'result_id': result_id})
        origins[result_id] = value
        for index, page in enumerate(value['pages']):
            number = page.get('page_number')
            doc['pages'].setdefault(number, {'text': page.get('text') or '', 'missing': page.get('text_missing'),
                'intervals': [], 'result_id': result_id, 'path': ['data', 'pages', index, 'text']})

    def origin(result_id):
        seen = set()
        while result_id not in seen:
            seen.add(result_id)
            if result_id in origins:
                return origins[result_id]
            value = results.get(result_id)
            if not isinstance(value, dict) or not value.get('page_of'):
                break
            result_id = value['page_of']
        return None

    def record(doc, number, text, start=0):
        page = doc['pages'].get(number)
        if page and isinstance(text, str) and text and page['text'][start:start + len(text)] == text:
            page['intervals'].append((start, start + len(text)))

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        source = origin(payload.get('result_id'))
        if not source:
            continue
        doc = documents[(str(source['evidence_id']), source.get('revision'))]
        def visit(value):
            if isinstance(value, list):
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                if value.get('page_number') is not None and isinstance(value.get('text'), str):
                    record(doc, value['page_number'], value['text'])
                elif isinstance(value.get('text'), str):
                    for note in value.get('_paging', []):
                        path = note.get('path') or []
                        if (note.get('unit') == 'characters' and len(path) == 4 and path[:2] == ['data', 'pages']
                                and path[3] == 'text' and isinstance(path[2], int) and 0 <= path[2] < len(source['pages'])):
                            record(doc, source['pages'][path[2]]['page_number'], value['text'], note.get('offset', 0))
                for key in ('data', 'pages', 'items'):
                    if key in value:
                        visit(value[key])
        visit(payload.get('data'))

    receipts = []
    for doc in documents.values():
        missing, complete = [], 0
        for number, page in sorted(doc['pages'].items()):
            end = 0
            for start, stop in sorted(page['intervals']):
                if start > end:
                    break
                end = max(end, stop)
            if not page['missing'] and page['text'] and end >= len(page['text']):
                complete += 1
            else:
                missing.append({'page': number, 'delivered_prefix_chars': end, 'total_chars': len(page['text']),
                    'unreadable': bool(page['missing'] or not page['text']),
                    'next_read': {'result_id': page['result_id'], 'path': page['path'], 'offset': end}})
        receipts.append({key: value for key, value in doc.items() if key != 'pages'} | {
            'complete_pages': complete, 'fetched_pages': len(doc['pages']), 'incomplete_pages': missing,
            'status': 'complete_text_delivered' if complete == doc['total_pages'] and complete else 'partial_text_delivered',
            'scope': 'Canonical text characters delivered in tool observations; no claim of understanding or source truth.'})
    return receipts
