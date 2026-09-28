"""Resolve saved standalone and batch work without last-writer-wins edits."""
from services.financial.pdf_candidates import _digest


def request_signature(request):
    if not request:
        return None
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
