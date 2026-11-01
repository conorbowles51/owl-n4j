"""Financial manual changes recorded inside a service (the save that owns them), for the lessons inbox.

A statement review save records what the person changed against what was there before: the previous saved review,
or, on the first save, the system's own reading (``initial_request``). Only changed fields are recorded, by name
(``holder``, ``rows.amount_minor``), so twenty fixes of one misread on one layout group into one lesson pattern.
"""
import logging

log = logging.getLogger(__name__)
_IGNORED = {'expected_revision', 'statement_id', 'rows', 'replaces_source_document_id'}
_MAX_VALUES = 25


def request_diff(before, after):
    """(changed field names, {field: before values}, {field: after values}) between two review requests."""
    before, after = before or {}, after or {}
    fields, old, new = set(), {}, {}

    def note(name, a, b, where=None):
        fields.add(name)
        olds, news = old.setdefault(name, []), new.setdefault(name, [])
        if len(olds) < _MAX_VALUES:
            olds.append(a if where is None else {'row': where, 'value': a})
            news.append(b if where is None else {'row': where, 'value': b})

    for key in sorted((set(before) | set(after)) - _IGNORED):
        if before.get(key) != after.get(key):
            note(key, before.get(key), after.get(key))
    rows_before = {row.get('id'): row for row in before.get('rows') or [] if isinstance(row, dict)}
    rows_after = {row.get('id'): row for row in after.get('rows') or [] if isinstance(row, dict)}
    for ident, row in rows_after.items():
        prior = rows_before.get(ident)
        if prior is None:
            note('rows.added', None, ident)
            continue
        for key in sorted((set(prior) | set(row)) - {'id'}):
            if prior.get(key) != row.get(key):
                note(f'rows.{key}', prior.get(key), row.get(key), ident)
    for ident in rows_before.keys() - rows_after.keys():
        note('rows.removed', ident, None)
    return sorted(fields), old, new


def _normal(request):
    # As the saved-review comparison does (effective_statement_review.request_signature): both sides through the
    # draft model, so a default the browser fills in is not taken for an edit.
    try:
        from services.financial.statement_import import StatementReviewDraft
        return StatementReviewDraft.model_validate(request).model_dump(mode='json')
    except Exception:  # noqa: BLE001 - a legacy incomplete draft is compared as stored
        return request


def reading_producer(proposal):
    """(the layout reader that produced this reading, its layout fingerprint or bank)."""
    proposal = proposal or {}
    choice = next((c for c in proposal.get('statement_choices') or () if c.get('id') == proposal.get('statement_id')),
                  None) or {}
    metadata = proposal.get('metadata') or {}
    producer = choice.get('layout_id') or choice.get('document_kind') or ''
    layout = choice.get('layout_fingerprint') or choice.get('institution') or metadata.get('institution') or ''
    return str(producer), str(layout)


def record_review_edit(session, *, kind, case_id, evidence_file_id, before, after, actor, proposal):
    """Record one statement review save (in the caller's transaction). Nothing is recorded when nothing changed or
    no person saved it."""
    try:
        if actor is None or not getattr(actor, 'email', None):
            return None
        fields, old, new = request_diff(_normal(before), _normal(after))
        if not fields:
            return None
        from services.manual_changes import record_change
        producer, layout = reading_producer(proposal)
        statement = (after or {}).get('statement_id') or ''
        return record_change(
            session, kind, case_id, ('evidence_file', f'{evidence_file_id}#{statement}' if statement else
                                     str(evidence_file_id)), old, new, actor, '',
            f'/cases/{case_id}/financial?file={evidence_file_id}' + (f'&statement={statement}' if statement else ''),
            field=','.join(fields), producer=producer, layout=layout)
    except Exception:  # noqa: BLE001 - the person's save stands
        log.exception('Recording the review edit on %s failed', evidence_file_id)
        return None
