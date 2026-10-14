"""Keep saved edits when only the statement reader version has changed."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4
from services.financial.pdf_candidates import _digest


def upgrade_request(request, proposal):
    if not request or request.get('expected_revision') == proposal['revision']:
        return request
    if request.get('expected_revision') not in proposal.get('_compatible_review_revisions', ()):
        return None
    originals = {row['id']: row for row in proposal['rows']}
    result = deepcopy(request)
    for row in result['rows']:
        original = originals.get(row['id'])
        if original is None:
            if row.get('manual_page'):
                continue
            return None
        # Old readers offered unknown source text as empty selected payments.
        # Preserve any investigator-entered value or note; only untouched empty
        # entries are moved back to the source text where they belong.
        if (original['kind'] == 'unclassified' and not row.get('reason', '').strip()
                and not any(row.get(key) for key in ('date', 'description', 'counterparty', 'direction', 'balance_minor'))
                and row.get('amount_minor') in ('', None, '0')):
            row['excluded'] = True
            row['amount_minor'] = '0'
    result['expected_revision'] = proposal['revision']
    return result


def versioned_digests(snapshot, versions):
    """Return `_digest({**snapshot, 'version': v})` for each version.

    The snapshot holds every source cell of the statement, so serializing it
    once per historical version dominated each reading. Serialize it once with
    a unique placeholder and hash the shared prefix once; the bytes hashed for
    each version are exactly those `_digest` would produce.
    """
    marker = f'review-version-placeholder-{uuid4().hex}'
    encoded = json.dumps({**snapshot, 'version': marker}, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False)
    token = json.dumps(marker)
    if encoded.count(token) != 1 or not all(
            json.dumps(v, ensure_ascii=False) == json.dumps(v) for v in versions):
        return [_digest({**snapshot, 'version': version}) for version in versions]
    before, after = encoded.split(token)
    prefix = hashlib.sha256(before.encode('utf-8'))
    after = after.encode('utf-8')
    result = []
    for version in versions:
        digest = prefix.copy()
        digest.update(json.dumps(version).encode('utf-8'))
        digest.update(after)
        result.append(digest.hexdigest())
    return result


def attach_upgrade(proposal, snapshot):
    # Matching the full old digest proves the PDF bytes, source text/locations,
    # account/period metadata and currency are identical. A filename or period
    # match alone must never migrate a saved correction.
    proposal['_compatible_review_revisions'] = versioned_digests(
        snapshot, [f'statement-review-v{version}' for version in range(1, 30)])
    saved = proposal.get('saved_review')
    if saved and saved['request'].get('expected_revision') != proposal['revision']:
        upgraded = upgrade_request(saved['request'], proposal)
        if not upgraded and proposal.get('rows') and proposal.get('metadata'):
            # A metadata/parser improvement can change the revision even when
            # every saved row equals the new extraction. There are no row edits
            # to discard or remap in that case. Keep saved account details as-is.
            from services.financial.import_batches import initial_request
            from services.financial.statement_import import DraftImportRow
            request = saved['request']
            current = initial_request(proposal)
            try:
                same_rows = (
                    request.get('statement_id') == proposal.get('statement_id') and
                    request.get('currency') == proposal.get('currency') and
                    [DraftImportRow.model_validate(r) for r in request['rows']] ==
                    [DraftImportRow.model_validate(r) for r in current['rows']])
            except (ValueError, KeyError):
                same_rows = False
            if same_rows:
                upgraded = {**deepcopy(request), 'expected_revision': proposal['revision']}
        if upgraded:
            # Keep review_revision as the stored concurrency token until save.
            proposal['saved_review'] = {**saved, 'request': upgraded, 'upgraded_from_revision': saved['request']['expected_revision']}
    return proposal
