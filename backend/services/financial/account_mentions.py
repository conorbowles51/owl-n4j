"""Account references explicitly printed in current payment descriptions.

These are investigation leads, not account identities. Only labelled references
are nominated; arbitrary payment amounts, telephone numbers and trace IDs are
not interpreted as account numbers.
"""
import re
from sqlalchemy import select, func
from postgres.models.financial import FinancialTransaction as Payment, FinancialSourceDocument as Source, FinancialAccount as Account, FinancialStatementPeriod as Period
from services.financial.pdf_candidates import _digest
from services.financial.check_digits import IBAN_COUNTRY_LENGTHS
from services.financial.proof_class import LEDGER_CLASSES

# A marker is required. Keep the exact printed text as well as its comparison
# form. Do not consume following narrative words or invent masked digits.
REFERENCE = re.compile(r'''(?ix)
    \b(?P<label>iban|account|acct\.?|a/c|card|share)
    \s*(?:(?:number|no\.?|ending\s+(?:in\s+)?)\s*)?[:\#]?\s*
    (?P<value>(?:[A-Z]{2}\d{2}(?:[ \-]?[A-Z0-9]){11,30})|(?:[A-Z]{1,8}-)?[X*•\d][X*•\d\-]{2,33})
    (?![A-Z0-9])
''')


def normalise(value):
    value = re.sub(r'[\s\-]', '', value).upper().replace('•', '*')
    return value.replace('X', '*') if re.fullmatch(r'[X*\d]+', value) else value


def mentions(text):
    result = []
    from services.financial.spei_description import kapital_spei
    spei = kapital_spei(text)
    if spei:
        for role in ('sender', 'recipient'):
            account = spei[role]['account']
            result.append(dict(kind='account', value=account['text'], printed=account['text'],
                normalised=account['text'], partial=False, start=account['start'], end=account['end'],
                identifier_kind='clabe', direction_role=role, bank=spei[role]['bank']['text'],
                holder=spei[role]['party']['name'], holder_qualifier=spei[role]['party']['qualifier']))
    for match in REFERENCE.finditer(text or ''):
        label, value = match['label'].lower(), match['value'].strip()
        end = match.end()
        # Use the country length for an IBAN followed by narrative, so words
        # after its final character are not swallowed into the reference.
        iban = re.match(r'(?i)^[A-Z]{2}\d{2}', value)
        if iban:
            length = IBAN_COUNTRY_LENGTHS.get(value[:2].upper())
            if length:
                seen = 0
                for index, char in enumerate(value):
                    seen += char.isalnum()
                    if seen == length:
                        value = value[:index+1]
                        end = match.start('value') + index+1
                        break
                if seen < length or (end < len(text) and text[end].isalnum()):
                    continue
        compact = normalise(value)
        if not re.search(r'\d', compact):
            continue
        # Date-shaped or decimal values after "account" are not identifiers.
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) or (end + 1 < len(text) and text[end] in './' and text[end+1].isdigit()):
            continue
        if label == 'iban' and not re.fullmatch(r'[A-Z]{2}\d{2}[A-Z0-9]{11,30}', compact):
            continue
        if len(re.sub(r'\D', '', compact)) < 4:
            continue
        kind = 'share' if label == 'share' else 'iban' if re.match(r'^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$', compact) else 'account'
        partial = '*' in compact or label in ('card', 'share') or len(re.sub(r'\D', '', compact)) <= 4
        result.append(dict(kind=kind, value=value, printed=text[match.start():end].strip(), normalised=compact, partial=partial,
                           start=match.start(), end=end))
    return result


def account_references(session, *, case_id, offset=0, limit=25, search='', show='missing'):
    """Stream current payments, then return complete groups on the chosen page."""
    # Investigation includes every current imported payment, including rows
    # accepted after review. This is not a verified-total calculation.
    classes = [p.value for p in LEDGER_CLASSES]
    query = (select(Payment.id, Payment.description, Payment.counterparty_raw, Payment.account_id)
        .join(Source, Source.id == Payment.source_document_id)
        .join(Account, Account.id == Payment.account_id)
        .where(Payment.case_id == case_id, Source.case_id == case_id, Account.case_id == case_id,
            Payment.ledger_status == 'admitted', Payment.superseded_by_id.is_(None), Source.status == 'admitted',
            Payment.proof_class.in_(classes), Source.proof_class.in_(classes)).order_by(Payment.id))
    groups, scanned = {}, 0
    for payment_id, description, counterparty, account_id in session.execute(query).yield_per(2000):
        scanned += 1
        for field, text in (('description', description), ('counterparty', counterparty)):
            for ref in mentions(text):
                key = (ref.get('identifier_kind', ref['kind']), ref['normalised'])
                group = groups.setdefault(key, dict(reference=ref['value'], kind=key[0], partial=ref['partial'],
                    variants=set(), payment_ids=set(), source_account_ids=set(), examples=[]))
                group['partial'] |= ref['partial']
                group['variants'].add(ref['printed'])
                group['payment_ids'].add(str(payment_id))
                group['source_account_ids'].add(str(account_id))
                if len(group['examples']) < 3 and not any(e['payment_id'] == str(payment_id) for e in group['examples']):
                    group['examples'].append(dict(payment_id=str(payment_id), field=field, text=text,
                                                 start=ref['start'], end=ref['end']))
    periods = (select(Period.account_id, func.count(Period.id)).join(Source, Source.id == Period.source_document_id)
        .where(Period.case_id == case_id, Source.case_id == case_id, Source.status == 'admitted').group_by(Period.account_id))
    counts = dict(session.execute(periods).all())
    accounts = list(session.scalars(select(Account).where(Account.case_id == case_id)))
    results = []
    for (kind, token), group in groups.items():
        matches = []
        for account in accounts:
            printed = account.iban if kind == 'iban' and account.iban else account.identifier_as_printed or ''
            comparable = normalise(printed)
            if kind == 'share':
                share = re.search(r'(?i)\bshare\s*([\dX*•-]+)', printed)
                possible = bool(share and normalise(share[1]) == token)
            elif group['partial'] or '*' in comparable:
                ending = re.search(r'\d{4,}$', token)
                possible = bool(ending and comparable.endswith(ending.group()))
            else:
                from services.financial.account_identity import matches_identifier
                possible = matches_identifier(account, kind, token)
            if possible:
                matches.append(dict(account_id=str(account.id), reference=printed, holder=account.holder_name,
                    bank=account.institution_name, statement_count=counts.get(account.id, 0)))
        group.update(id=_digest(dict(kind=kind, token=token)), status='possible_statement' if any(a['statement_count'] for a in matches) else 'no_statement_found',
            possible_accounts=matches, payment_count=len(group['payment_ids']))
        for key in ('variants', 'payment_ids', 'source_account_ids'):
            group[key] = sorted(group[key])
        results.append(group)
    results.sort(key=lambda g: (-g['payment_count'], g['reference'], g['id']))
    revision = _digest([dict(id=g['id'], payments=g['payment_ids'], matches=g['possible_accounts']) for g in results])
    missing = sum(g['status'] == 'no_statement_found' for g in results)
    selected = [g for g in results if (show == 'all' or g['status'] == 'no_statement_found')
        and (not search or search.casefold() in ' '.join([g['reference'], *g['variants'], *(e['text'] for e in g['examples'])]).casefold())]
    return dict(case_id=str(case_id), revision=revision, scanned_payments=scanned,
        missing_count=missing, possible_match_count=len(results)-missing,
        offset=offset, limit=limit, total=len(selected), items=selected[offset:offset+limit])
