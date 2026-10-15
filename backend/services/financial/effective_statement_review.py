"""Resolve saved standalone and batch work without last-writer-wins edits."""
from collections import OrderedDict
from threading import Lock
from services.financial.pdf_candidates import _digest


# Raw content digest -> signature. The signature is a pure function of the
# request's content; validating a large review was ~3.6 ms per call, 0.75 s of
# every comparison on a case with 800 pending periods. Hashing is ~0.4 ms.
_SIGNATURES = OrderedDict()
_SIGNATURES_LOCK = Lock()
SIGNATURES_KEPT = 8192


def request_signature(request):
    if not request:
        return None
    try:
        key = _digest(request)
    except (TypeError, ValueError):
        return _request_signature(request)
    with _SIGNATURES_LOCK:
        if key in _SIGNATURES:
            _SIGNATURES.move_to_end(key)
            return _SIGNATURES[key]
    signature = _request_signature(request)
    with _SIGNATURES_LOCK:
        _SIGNATURES[key] = signature
        while len(_SIGNATURES) > SIGNATURES_KEPT:
            _SIGNATURES.popitem(last=False)
    return signature


def _request_signature(request):
    from services.financial.statement_import import StatementReviewDraft
    try:
        return _digest(StatementReviewDraft.model_validate(request).model_dump(mode='json'))
    except ValueError:
        # Legacy incomplete drafts remain comparable without breaking a list.
        # They never gain equivalence through dropped invalid fields.
        return _digest(request)


def resolve_review(batch_request, saved, *, baseline=None):
    """Return (effective request, conflict); no parsing, writes or silent merge.

    A batch can follow a shared draft only while it still equals that draft or
    its recorded predecessor. Independently changed values require a decision.
    """
    if not saved:
        return batch_request, False
    request = saved['request']
    if not batch_request:
        return request, False
    signature = request_signature(batch_request)
    compatible = {request_signature(request), *saved.get('superseded_request_signatures', [])}
    if baseline:
        compatible.add(request_signature(baseline))
    if saved.get('initial_request_signature'):
        compatible.add(saved['initial_request_signature'])
    if signature in compatible:
        return request, False
    return batch_request, True


def conflict_summary(summary):
    problem = dict(kind='review_conflict', row_id=None,
        message='The individual statement and batch have different saved edits. Compare both reviews before importing; neither has been overwritten.')
    return {**summary, 'can_import': False, 'problems': [problem, *summary.get('problems', [])],
        'problem_count': summary.get('problem_count', 0) + 1}


def batch_review_revision(request, saved):
    # Keep old tokens compatible when there has never been a shared save.
    if not saved:
        return _digest(request or {})
    return _digest(dict(batch=request or {}, shared=saved['review_revision']))
