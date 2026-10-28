"""Name the other side of a payment from its matching payment in another account of the same case.

A payment whose description names nobody may still have its other leg in the case: a transfer from one of the
case's companies to another is read once from each statement. The deterministic linkage tier
(services.financial.linkage.link_composite: same currency and amount, opposite directions, different accounts,
like-for-like dates within the tolerance, and each side's only candidate is the other) finds that leg; this module
only decides whether the two descriptions can be the same payment and, if so, names the other side as the matched
account. It never picks between candidates: anything the linkage tier leaves ambiguous stays unnamed.

The result is read-time, like every description suggestion: nothing stored changes, and a person's label, the
statement's recorded counterparty and a name the description prints all take precedence.
"""
import re
from datetime import date
from uuid import UUID

VERSION = 'matched-payment/2'
RULE = 'matched-payment'
TOLERANCE_DAYS = 3

# Bank names as statements print them, mapped to one key so that 'BANCOMER' on one line and 'BBVA Mexico' as
# another account's institution are the same bank. A word that is also a merchant's (CITI TRENDS) is not listed.
_BANKS = [
    ('BBVA', r'BBVA|BANCOMER'), ('SANTANDER', r'SANTANDER'), ('INBURSA', r'INBURSA'), ('MONEX', r'B?MONEX'),
    ('INTERCAM', r'INTERCAM'), ('KAPITAL', r'KAPITAL'), ('BANORTE', r'BANORTE|IXE'),
    ('BANAMEX', r'BANAMEX|CITIBANAMEX|CITI MEXICO'), ('HSBC', r'HSBC'), ('SCOTIABANK', r'SCOTIABANK|INVERLAT'),
    ('AZTECA', r'AZTECA'), ('BAJIO', r'BAN ?BAJIO|DEL BAJIO'), ('AFIRME', r'AFIRME'), ('MIFEL', r'MIFEL'),
    ('BANREGIO', r'BANREGIO'), ('MULTIVA', r'MULTIVA'), ('ACTINVER', r'ACTINVER'), ('INVEX', r'INVEX'),
    ('CIBANCO', r'CIBANCO'), ('STP', r'STP'), ('MIZUHO', r'MIZUHO'),
    ('CAPITAL ONE', r'CAPITAL ?ONE'), ('MERRICK', r'MERRICK'), ('CREDIT ONE', r'CREDIT ONE'),
    ('ANDREWS', r'ANDREWS'), ('NAVY FEDERAL', r'NAVY FEDERAL|NAVY FCU|NFCU'), ('TRUIST', r'TRUIST'),
    ('M&T', r'M ?& ?T'), ('CITIBANK', r'CITIBANK|CITI CARDS?|CITI AUTOPAY'), ('SYNCHRONY', r'SYNCHRONY|SYNCB'),
    ('WELLS FARGO', r'WELLS FARGO'), ('CHASE', r'CHASE'), ('BANK OF AMERICA', r'BANK OF AMERICA|BK OF AMER'),
    ('PNC', r'PNC'), ('APPLE CARD', r'APPLE ?CARD|GS BANK'), ('DISCOVER', r'DISCOVER'),
    ('AMERICAN EXPRESS', r'AMERICAN EXPRESS|AMEX'), ('FIRST', r'FIRST NATIONAL|FIRST PREMIER'),
]
_BANK_RES = [(key, re.compile(r'(?<![A-Z0-9])(?:' + pattern + r')(?![A-Z0-9])')) for key, pattern in _BANKS]

# Lines that are not a payment between two accounts: cash, card purchases at a store, the bank's own charges.
_NOT_A_TRANSFER = re.compile(r'(?<![A-Z])(?:ATM|CAJERO|EFECTIVO|CASH(?! APP)|RETIRO SIN TARJETA|POS|DEBIT CARD|'
                             r'COMPRA CON TARJETA|COMISION|IVA|ISR|INTERES(?:ES)?|DIVISAS|REPORTO)(?![A-Z])')

# Lines that only move money inside one bank: Santander Enlace transfers and BBVA third-party transfers. Their
# other end is at the same bank unless the line prints the other account's number or a reference both lines share.
_SAME_BANK_ONLY = re.compile(r'TRANSFERENCIA ENLACE|TRASPASO A TERCEROS|DEPOSITO DE TERCERO|PAGO CUENTA DE TERCERO')
_CHEQUE_DEPOSIT = re.compile(r'DEPOSITO (?:DE |CON )?CHEQUE|DEPOSIT\S* .*\bCHECK|MOBILE DEPOSIT|REMOTE DEPOSIT')
_CHEQUE = re.compile(r'(?<![A-Z])(?:CHEQUE|CHECK|CHQ|CK ?#)(?![A-Z])')
_COMMON_WORDS = frozenset('''ABONO CARGO PAGO TRANSFERENCIA ENLACE TRASPASO TERCEROS TERCERO DEPOSITO CUENTA CUENTAS SPEI SPID
    ENVIADO RECIBIDO HORA BMRCASH PAYMENT WITHDRAWAL DEPOSIT TYPE MOBILE ONLINE BANK BANCO MEXICO THANK PAID FROM'''.split())

# Description reasons for which a matching amount elsewhere in the case does not identify the other side.
_REASONS_NOT_MATCHED = ('Cash ', 'Card purchase', 'Government payment', 'Cashier')


def banks_in(text):
    """The bank keys a line or an institution name mentions."""
    from services.financial.payment_inference import normalized
    text = ' '.join(re.sub(r'[^A-Z0-9& ]', ' ', normalized(text or '')).split())
    return {key for key, pattern in _BANK_RES if pattern.search(text)}


def _same_holder(left, right):
    from services.financial.linkage import normalise_name, name_similarity
    left, right = normalise_name(left), normalise_name(right)
    if not left or not right:
        return False
    if left == right or left.startswith(right + ' ') or right.startswith(left + ' '):
        return True
    return (name_similarity(left, right) or 0) >= 0.85


def _related_holders(left, right):
    """The same holder, or one holder among a joint account's holders (ERICA HOPPER / LASHIKA HOPPER)."""
    parts = lambda v: [p for p in re.split(r'\s*(?:/|\n|\bAND\b|\bY\b|&)\s*', v or '') if p.strip()]
    return _same_holder(left, right) or any(_same_holder(a, b) for a in parts(left) for b in parts(right))


def _date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(value) if value else None


def _references(text):
    """Numbers of five or more digits a line prints, split from letters they are glued to (4014647ABONO)."""
    from services.financial.payment_inference import normalized
    return {n.lstrip('0') for n in re.findall(r'\d{5,}', normalized(text or '')) if len(n.lstrip('0')) >= 5}


def _concept(text):
    """What a line says besides its transfer wording, with spacing and numbers' leading zeros removed."""
    from services.financial.payment_inference import normalized
    words = [w for w in re.findall(r'[A-Z]+|\d+', normalized(text or '')) if w not in _COMMON_WORDS and not re.fullmatch(r'0+', w)]
    return ''.join(words)


def _shared(unnamed, other):
    """A reference number or the whole concept both lines print."""
    if _references(unnamed['description']) & _references(other['description']):
        return True
    left, right = _concept(unnamed['description']), _concept(other['description'])
    return len(left) >= 6 and left == right


def _prints_account(line, identifier):
    digits = re.sub(r'\D', '', identifier or '').lstrip('0')
    return len(digits) >= 6 and digits in _references(line)


def compatible(unnamed, other):
    """Whether two linked rows' descriptions and accounts can be the two ends of one payment. Plain-language
    reason when they cannot; None when they can."""
    if any(unnamed.get('reason', '').startswith(r) for r in _REASONS_NOT_MATCHED):
        return 'the description is a cash or card-purchase line, not a payment between accounts'
    from services.financial.payment_inference import normalized
    for row in (unnamed, other):
        if _NOT_A_TRANSFER.search(normalized(row['description'] or '')):
            return 'one line is cash, a card purchase, or the bank’s own charge, interest or exchange'
    lines = [normalized(r['description'] or '') for r in (unnamed, other)]
    if any(_CHEQUE_DEPOSIT.search(line) for line in lines) and not all(
            _CHEQUE.search(line.replace('CUENTA DE CHEQUES', '')) for line in lines):
        return 'a cheque deposit can only match a cheque'
    shared = _shared(unnamed, other)
    own_bank = banks_in(unnamed['institution'])
    other_bank = banks_in(other['institution'])
    if not own_bank or not other_bank:
        return 'an account has no recognisable bank'
    # A bank the line names (other than its own) must be the other account's bank.
    for row, bank, theirs in ((unnamed, own_bank, other_bank), (other, other_bank, own_bank)):
        named = banks_in(row['description']) - bank
        if named and not named & theirs:
            return 'a line names a different bank'
    for row, theirs, line in ((unnamed, other, lines[0]), (other, unnamed, lines[1])):
        if _SAME_BANK_ONLY.search(line) and not banks_in(row['institution']) & banks_in(theirs['institution']) \
                and not shared and not _prints_account(row['description'], theirs['identifier']):
            return 'a transfer inside one bank cannot be paid to or from another bank'
    names_holder = bool(other.get('name')) and _same_holder(other['name'], unnamed['holder'])
    related = _related_holders(unnamed['holder'], other['holder']) \
        and not unnamed.get('other_holders') and not other.get('other_holders')
    if not related and int(unnamed['amount_minor']) % 1000 == 0 \
            and not shared and not names_holder:
        return 'a round amount between different holders, with nothing else in common, can be a coincidence'
    name = other.get('name')
    if name:
        # The other row already names its own other side: it must be this account's holder or this bank.
        named_bank = banks_in(name)
        if named_bank:
            if named_bank & other_bank or not named_bank & own_bank:
                return 'the matching payment names its own bank or another bank'
        elif not _same_holder(name, unnamed['holder']):
            return 'the matching payment names someone else'
    return None


def match_parties(rows):
    """Map row id -> match for every unnamed row whose other leg the linkage tier resolves uniquely.

    Each row: id, account_id (the canonical account), source_document_id, amount_minor, currency, direction,
    ordering_date, ordering_date_source, transaction_date/posted_date/value_date/effective_date, description,
    holder, institution, identifier, name (the other side's effective name or None), reason (the description
    reason or ''). Rows dated only by statement end must be left out by the caller.
    """
    from postgres.models.enums import LinkRelation, LinkOutcome
    from services.financial.linkage import link_composite
    by_id = {}
    groups = {}
    # link_composite only ever pairs rows of one currency and amount whose like-for-like dates are within the
    # tolerance. So each currency and amount is split into runs of rows whose dates (every printed date) lie within
    # the tolerance of the run; rows in different runs can never pair, and a run with no unnamed payment cannot
    # name anything. Linking run by run gives the same links as linking everything at once, without comparing
    # every pair of a common amount across years.
    for row in rows:
        if not row.get('ordering_date') or not row.get('amount_minor'):
            continue
        by_id[str(row['id'])] = row
        groups.setdefault((row['currency'], int(row['amount_minor'])), []).append(row)
    links = []
    for bucket in groups.values():
        if all(row.get('name') for row in bucket):
            continue
        for run in _date_runs(bucket):
            if len(run) > 1 and not all(row.get('name') for row in run):
                links.extend(link_composite([_observation(row) for row in run], tolerance_days=TOLERANCE_DAYS).links)
    matches = {}
    for link in links:
        if link.relation != LinkRelation.counterparty or link.outcome != LinkOutcome.resolved:
            continue
        left, right = by_id[str(link.left_id)], by_id[str(link.right_id)]
        for unnamed, other in ((left, right), (right, left)):
            if unnamed.get('name') or compatible(unnamed, other):
                continue
            matches[str(unnamed['id'])] = describe(unnamed, other, link.date_agreement.gap_days if link.date_agreement else None)
    return matches


def _dates(row):
    return [d for d in (_date(row.get(f)) for f in ('ordering_date', 'transaction_date', 'posted_date', 'value_date',
                                                     'effective_date')) if d]


def _date_runs(bucket):
    """Split rows into runs: sorted by earliest date, a row starts a new run when its earliest date is more than the
    tolerance after the latest date seen in the run so far."""
    runs, current, latest = [], [], None
    for row in sorted(bucket, key=lambda r: min(_dates(r))):
        dates = _dates(row)
        if current and (min(dates) - latest).days > TOLERANCE_DAYS:
            runs.append(current)
            current, latest = [], None
        current.append(row)
        latest = max(dates) if latest is None else max(latest, max(dates))
    if current:
        runs.append(current)
    return runs


def _observation(row):
    from postgres.models.enums import DateSource, TransactionDirection
    from services.financial.linkage import LinkObservation
    from services.financial.money import Money
    return LinkObservation(
        transaction_id=UUID(str(row['id'])), account_id=UUID(str(row['account_id'])),
        source_document_id=UUID(str(row['source_document_id'])), amount=Money(int(row['amount_minor']), row['currency']),
        direction=TransactionDirection(row['direction']), ordering_date=_date(row['ordering_date']),
        ordering_date_source=DateSource(row['ordering_date_source']),
        **{f: _date(row.get(f)) for f in ('transaction_date', 'posted_date', 'value_date', 'effective_date')})


def describe(unnamed, other, gap_days):
    account = ' '.join(' '.join(str(v).split()) for v in (other['institution'], other['identifier']) if v)
    holder = ' '.join((other['holder'] or '').replace('\n', ' / ').split())
    disputed = other.get('other_holders') or []
    when = 'the same day' if not gap_days else ('1 day apart' if gap_days == 1 else f'{gap_days} days apart')
    how = (f'({"money in" if other["direction"] == "credit" else "money out"}, same amount and currency, {when}). '
           'It is the only payment in the case that matches this one, and this is the only one that matches it.')
    if disputed or not holder:
        # The account's statements print more than one holder name (or none): show the account, never a holder.
        own = False
        value = account or 'Another account in the case'
        explanation = (f'Named from the matching payment in {value} {how}'
                       + (' The account’s statements print more than one holder name (' + ', '.join([holder] + disputed)
                          + '), so the holder is not shown.' if disputed else ''))
    else:
        own = _related_holders(other['holder'], unnamed['holder']) and not unnamed.get('other_holders')
        value = (holder + ' · ' + account) if account else holder
        explanation = (f'Named from the matching payment in {value} {how}'
                       + (' The two accounts share a holder.' if own else ''))
    return dict(value=value, source='matched_payment', rule=RULE, version=VERSION, explanation=explanation,
                matched_transaction_id=str(other['id']), matched_account_id=str(other['account_id']),
                own_account=own)


_CASE_ROWS = """select t.id, t.account_id, t.source_document_id, t.amount_minor, t.currency,
 t.direction, t.ordering_date, t.ordering_date_source, t.transaction_date, t.posted_date, t.value_date, t.effective_date,
 t.description, t.counterparty_raw, t.metadata->'investigation_labels', t.provenance->'reviewed_counterparty',
 t.provenance->>'date_basis'
 from financial_transactions t join financial_accounts a on a.id = t.account_id
 where t.case_id = :case_id and a.case_id = :case_id and t.ledger_status = 'admitted' and t.superseded_by_id is null"""

# Accounts are read once per case: an account's holder conflicts are the same for every one of its payments.
_CASE_ACCOUNTS = """select a.id, a.metadata->>'canonical_account_id', a.holder_name, a.institution_name, a.identifier_as_printed,
 a.account_type, a.metadata->'identity_conflicts' from financial_accounts a where a.case_id = :case_id"""


def _plain(value):
    return value.value if hasattr(value, 'value') else value


def disputed_holders(holder, conflicts):
    """Other holder names the account's statements printed, recorded as identity conflicts on the account."""
    found = []
    for conflict in conflicts if isinstance(conflicts, list) else []:
        offered = conflict.get('offered') if isinstance(conflict, dict) and conflict.get('field') == 'holder_name' else None
        if offered and not _same_holder(offered, holder) and not any(_same_holder(offered, f) for f in found):
            found.append(' '.join(str(offered).split()))
    return found


def case_rows(session, case_id, *, dated_only=True):
    """Every current admitted payment of the case, reduced to what match_parties reads, with the other side's
    effective name as the Transactions table shows it (statement, person label or link, description).
    ``dated_only``: leave out payments dated only by their statement's end (they cannot be matched by date)."""
    from sqlalchemy import text
    from services.financial.payment_labels import _inferred_labels
    accounts = {str(id): (str(canonical or id), holder, institution, identifier, _plain(account_type), disputed_holders(holder, conflicts))
                for id, canonical, holder, institution, identifier, account_type, conflicts in session.execute(
                    text(_CASE_ACCOUNTS), dict(case_id=str(case_id)))}
    rows = []
    for (id, account_id, document, amount, currency, direction, ordering, ordering_source, td, pd, vd, ed,
         description, raw, labels, reviewed, date_basis) in session.execute(text(_CASE_ROWS), dict(case_id=str(case_id))):
        direction = _plain(direction)
        if (dated_only and date_basis == 'statement_end_ordering_only') or direction not in ('credit', 'debit'):
            continue
        canonical, holder, institution, identifier, account_type, other_holders = accounts[str(account_id)]
        labels = labels if isinstance(labels, dict) else {}
        side = 'from_name' if direction == 'credit' else 'to_name'
        inferred = _inferred_labels(description, direction, account_type, institution)
        reviewed = reviewed.get('label') if isinstance(reviewed, dict) else None
        name = ((raw or '').strip() or labels.get(side) or (labels.get('counterparty_link') or {}).get('label')
                or reviewed or (inferred.get('counterparty') or {}).get('value'))
        rows.append(dict(id=str(id), account_id=canonical, source_document_id=str(document),
                         amount_minor=amount, currency=currency, direction=direction, ordering_date=ordering,
                         ordering_date_source=_plain(ordering_source), transaction_date=td, posted_date=pd,
                         value_date=vd, effective_date=ed, description=description, holder=holder,
                         institution=institution, identifier=identifier, name=name,
                         reason=(inferred.get('counterparty_reason') or {}).get('value') or '',
                         reason_rule=(inferred.get('counterparty_reason') or {}).get('rule'),
                         other_holders=other_holders))
    return rows


_PRINTED_ACCOUNT = re.compile(r'CUENTA:\s*(\d{10,18})(?!\d)')


def printed_accounts(rows, named=frozenset()):
    """Row id -> other side, for unnamed rows whose line prints "CUENTA: <number>" where the number is another
    account of the case (all of its digits, as the case's statements print the account). Rows in ``named`` are
    skipped. When the accounts with that number carry different holders, the account is shown without a holder."""
    accounts = {}
    for row in rows:
        digits = re.sub(r'\D', '', row.get('identifier') or '')
        if len(digits) >= 10:
            accounts.setdefault(digits, {})[row['account_id']] = row
    found = {}
    for row in rows:
        if row.get('name') or row['id'] in named:
            continue
        numbers = set(_PRINTED_ACCOUNT.findall((row.get('description') or '').upper()))
        hits = [accounts[n] for n in numbers if n in accounts]
        if len(hits) != 1 or row['account_id'] in hits[0]:
            continue
        others = list(hits[0].values())
        holders = sorted({' '.join((o.get('holder') or '').split()) for o in others} - {''})
        disputed = sorted({h for o in others for h in o.get('other_holders') or []} - set(holders[:1]))
        first = others[0]
        account = ' '.join(' '.join(str(v).split()) for v in (first['institution'], first['identifier']) if v)
        number = next(n for n in numbers if n in accounts)
        if len(holders) == 1 and not disputed:
            value = holders[0] + ' · ' + account
            note = ''
        else:
            value = account
            note = (' The case holds more than one holder name for that account (' + ', '.join(holders + disputed)
                    + '), so the holder is not shown.')
        own = len(holders) == 1 and not disputed and _related_holders(holders[0], row['holder'])
        found[row['id']] = dict(
            value=value, source='printed_account', rule='printed-account', version=VERSION, own_account=own,
            matched_account_id=str(first['account_id']),
            explanation=f'The line prints account {number}, which is the account {account} in this case.' + note
                        + (' The two accounts share a holder.' if own else ''))
    return found


def case_party_matches(session, case_id):
    """Row id -> other side for every unnamed payment of the case: its matching payment in another account
    (match_parties), else an account of the case its line prints (printed_accounts)."""
    rows = case_rows(session, case_id)
    found = match_parties(rows)
    found.update(printed_accounts(rows, frozenset(found)))
    return found
