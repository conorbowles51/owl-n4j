"""Keep saved edits when only the statement reader version has changed."""
import hashlib
import json
import os
from copy import deepcopy
from itertools import combinations
from uuid import uuid4
from services.financial.pdf_candidates import _digest

# A reader fix can fill a statement detail (account number, holder, bank, period) the earlier reading left blank and
# the person had already typed into the saved review (Truist STATEMENTS 5630.pdf: the account read past a scanned
# heading bullet). That changes the revision while every row stays as the review was saved against, so the review
# carries over unchanged when the earlier revision is this reading's snapshot with those filled values blank again.
# Reverse: LOUPE_FINANCIAL_FILLED_DETAILS_UPGRADE=0.
FILLED_DETAILS_UPGRADE = os.environ.get('LOUPE_FINANCIAL_FILLED_DETAILS_UPGRADE', '1') != '0'
FILLED_FIELDS = ('holder', 'account_number', 'institution', 'period_start', 'period_end')


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
        if not upgraded and FILLED_DETAILS_UPGRADE:
            upgraded = filled_details_upgrade(saved, proposal, snapshot)
        if upgraded:
            # Keep review_revision as the stored concurrency token until save.
            proposal['saved_review'] = {**saved, 'request': upgraded, 'upgraded_from_revision': saved['request']['expected_revision']}
    return proposal


def filled_details_upgrade(saved, proposal, snapshot):
    """The saved request on the new reading when that reading only filled details the saved review already holds.

    Proof: the earlier revision is the digest of this reading's snapshot (PDF bytes, every source cell, every other
    detail) with some filled details blank again. Rows, row ids and the values the review was saved against are
    then unchanged, so the saved request carries over as saved."""
    request = saved['request']
    metadata = snapshot.get('metadata') or {}
    if not request.get('expected_revision') or not isinstance(metadata, dict):
        return None
    filled = [key for key in FILLED_FIELDS if isinstance(metadata.get(key), str) and metadata[key].strip()
              and metadata[key].strip() == str(request.get(key) or '').strip()]
    for size in range(1, len(filled) + 1):
        for blank in combinations(filled, size):
            if _digest({**snapshot, 'metadata': {**metadata, **{key: '' for key in blank}}}) == request['expected_revision']:
                return {**deepcopy(request), 'expected_revision': proposal['revision']}
    return None
