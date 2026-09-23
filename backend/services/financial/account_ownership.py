"""Source-supported common-holder suggestions, shared by every Financial view.

This never assigns ownership or merges accounts. A matching holder identifier
is a reason to review a link, not a replacement for the investigator decision.
"""
import re
import unicodedata
from collections import defaultdict

from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument
from services.financial.pdf_candidates import _digest


def normalise_name(value):
    return ' '.join(re.sub(r'[^\w]+', ' ', ''.join(c for c in unicodedata.normalize(
        'NFKD', value or '').upper() if not unicodedata.combining(c))).split())


def _identifier(label, value):
    label = re.sub(r'[^A-Z]', '', label.upper())
    token = re.sub(r'[\s.-]', '', value.upper())
    if label in ('RFC', 'RFCTITULAR', 'RFCDELCLIENTE', 'RFCDELTITULAR', 'HOLDERRFC'):
        if re.fullmatch(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}', token) and token not in (
                'XAXX010101000', 'XEXX010101000'):
            return 'MX:RFC', token
    if label in ('EIN', 'EMPLOYERIDENTIFICATIONNUMBER') and re.fullmatch(r'\d{9}', token):
        return 'US:EIN', token
    # Generic Tax ID without an issuing jurisdiction is deliberately not a
    # universal identity key. Unsupported labels remain in the source review.
    return None


def holder_identifiers(sources, *, account_reference, holder):
    """Read labelled header fields only in an explicitly identified account.

    Require both the recorded holder and account reference on the page, plus a
    label/value row in the upper half. Footer bank identifiers and names in the
    payment table cannot establish account ownership.
    """
    pages = defaultdict(list)
    for source in sources:
        pages[source.get('page_number')].extend(source.get('rows') or [])
    result = []
    reference = re.sub(r'\W', '', account_reference or '').upper()
    name = normalise_name(holder)
    if not reference or len(reference) < 5 or not name:
        return result
    # This bank's cover puts the holder fields below the physical midpoint.
    # Its recognised contract/period and explicit RFC TITULAR label provide
    # the scope; arbitrary low-page RFCs and routing beneficiaries do not.
    from services.financial.statement_import_monex import monex_catalog
    monex, _ = monex_catalog(sources)
    covers = {min(c['page_numbers']) for c in monex
        if c['account_reference'] == account_reference and normalise_name(c['holder']) == name}
    from services.financial.statement_import_kapital import kapital_catalog
    kapital, _ = kapital_catalog(sources)
    kapital_covers = {min(c['page_numbers']) for c in kapital
        if c['account_reference'] == account_reference and normalise_name(c['holder']) == name}
    for source in sources:
        if source['page_number'] not in covers | kapital_covers:
            continue
        for row in source['rows']:
            cells = row['cells']
            for index, cell in enumerate(cells[:-1]):
                allowed = 'RFCTITULAR' if source['page_number'] in covers else 'RFC'
                if re.sub(r'[^A-Z]', '', cell['expected_text'].upper()) != allowed:
                    continue
                evidence = cells[index+1]
                value = evidence['expected_text'].strip()
                identity = _identifier('RFC TITULAR', value)
                rect = (evidence.get('locator') or {}).get('rect')
                size = (evidence.get('locator') or {}).get('page_size')
                if identity and evidence.get('locator') and (allowed == 'RFCTITULAR' or
                    rect and size and rect[3] < size[1] * .25):
                    result.append(dict(scheme=identity[0], value=identity[1], page_number=source['page_number'],
                        printed_label=cell['expected_text'], printed_value=value, locator=evidence['locator'],
                        holder_as_recorded=holder, account_reference=account_reference))
    for page, rows in pages.items():
        if type(page) is not int or page < 1:
            continue
        header = []
        for row in rows:
            cells = []
            for cell in row.get('cells') or []:
                location = cell.get('locator') or {}
                box, size = location.get('rect'), location.get('page_size')
                if (isinstance(box, list) and len(box) == 4 and isinstance(size, list)
                        and len(size) == 2 and all(type(n) in (int, float) for n in [*box, *size])
                        and size[1] > 0 and 0 <= box[1] < box[3] <= size[1] * .5):
                    cells.append(cell)
            if cells:
                header.append(cells)
        texts = [cell.get('expected_text', '') for row in header for cell in row]
        if not any(name == normalise_name(text) for text in texts):
            continue
        # Match a complete identifier, not an account-number suffix, date or
        # substring of a CLABE. Alternate identifiers are a separate contract.
        if not any(reference == re.sub(r'\W', '', text).upper() for text in texts):
            continue
        for cells in header:
            for index, cell in enumerate(cells):
                label = cell.get('expected_text', '').strip()
                choices = []
                if index + 1 < len(cells):
                    choices.append((label, cells[index+1].get('expected_text', ''), cells[index+1]))
                inline = re.fullmatch(r'\s*(R\.?F\.?C\.?|EIN|Holder RFC|RFC del titular|RFC del cliente)\s*:\s*(\S+)\s*', label, re.I)
                if inline:
                    choices.append((inline[1], inline[2], cell))
                for field, value, evidence in choices:
                    identity = _identifier(field, value.strip())
                    if identity:
                        scheme, token = identity
                        item = dict(scheme=scheme, value=token, page_number=page,
                            printed_label=field, printed_value=value.strip(),
                            locator=evidence.get('locator'), holder_as_recorded=holder,
                            account_reference=account_reference)
                        if item not in result:
                            result.append(item)
    return result


def ownership_suggestions(session, *, case_id, accounts):
    """Derive suggestions from saved originals, including older imports.

    Reading this directory performs no client-data backfill or ingestion. New
    statement imports preserve the same observations in their source snapshot.
    """
    indexed = {a['id']: a for a in accounts}
    evidence = defaultdict(list)
    documents = session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.status == 'admitted').order_by(FinancialSourceDocument.id))
    for document in documents:
        metadata = document.metadata_ or {}
        account_id = metadata.get('statement_account_id')
        if account_id not in indexed:
            continue
        original = metadata.get('statement_import_original') or {}
        original_metadata = original.get('metadata') or {}
        # A subsequent correction to the account holder invalidates a proposed
        # identity until its source and corrected holder are reviewed together.
        account = indexed[account_id]
        if normalise_name(original_metadata.get('holder')) != normalise_name(account['holder_as_recorded']):
            continue
        observations = holder_identifiers(original.get('sources') or [],
            account_reference=original_metadata.get('account_number'), holder=original_metadata.get('holder'))
        for observation in observations:
            evidence[account_id].append({**observation, 'account_id': account_id,
                'source_document_id': str(document.id),
                'evidence_file_id': str(document.evidence_file_id) if document.evidence_file_id else None,
                'source_sha256': document.sha256_at_ingestion})
    groups = defaultdict(dict)
    conflicts = []
    for account_id, observations in evidence.items():
        schemes = defaultdict(set)
        for observation in observations:
            schemes[observation['scheme']].add(observation['value'])
        if any(len(values) > 1 for values in schemes.values()):
            conflicts.append(dict(account_id=account_id, reason='Different holder identifiers occur in the saved statements. Review the sources before linking ownership.', evidence=observations))
            continue
        for observation in observations:
            key = (observation['scheme'], observation['value'])
            groups[key].setdefault(account_id, []).append(observation)
    suggestions = []
    for (scheme, value), matches in sorted(groups.items()):
        if len(matches) < 2:
            continue
        ids = sorted(matches)
        parties = {indexed[id]['party']['id'] for id in ids if indexed[id]['party']}
        if len(parties) == 1 and all(indexed[id]['party'] for id in ids):
            continue
        basis = dict(scheme=scheme, value=value, account_ids=ids,
            evidence=[entry for id in ids for entry in matches[id]])
        suggestions.append(dict(id=_digest(basis), **basis,
            suggested_name=next((indexed[id]['party']['name'] for id in ids if indexed[id]['party']), None)
                or indexed[ids[0]]['holder_as_recorded'] or 'Recorded account holder',
            existing_party_id=next(iter(parties)) if len(parties) == 1 else None,
            has_conflicting_links=len(parties) > 1,
            reason=f"These accounts show the same holder {scheme}: {value}. Check the cited headers before saving a common-owner link."))
    return dict(suggestions=suggestions, conflicts=conflicts)
