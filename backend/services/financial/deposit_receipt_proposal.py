"""Read a labelled Andrews deposit receipt, including one inside a collection."""
import re
from datetime import date
from services.financial.pdf_candidates import _digest
from services.financial.payment_document_proposal import SCHEMA, _position
from services.financial.statement_import_proposal import exact_amount

VERSION = 'andrews-deposit-receipt-v1'


def _text(row):
    return ' '.join(c['expected_text'].strip() for c in row['cells'])


def _field(source, key, label, pattern, kind='text', *, repeated=False):
    readings = []
    for row in source['rows']:
        match = re.fullmatch(pattern, _text(row))
        if match:
            readings.append((match[1], row['cells']))
    raw = '\n'.join(value for value, _ in readings)
    cells = [c for _, items in readings for c in items]
    value = readings[0][0] if readings else ''
    issues = []
    if (not readings or (len(readings) != 1 and not repeated)
            or len({v for v, _ in readings}) != 1
            or any(_position(c) is None for c in cells)):
        value = ''
        issues.append('This detail could not be read uniquely. Check its original text and position in the PDF.')
    elif kind == 'date':
        m = re.fullmatch(r'(\d{2})/(\d{2})/(20\d{2})', value)
        try:
            value = date(int(m[3]), int(m[1]), int(m[2])).isoformat() if m else ''
        except ValueError:
            value = ''
        if not value:
            issues.append('Enter the full date after checking the original. A two-digit year needs its century checked.')
    elif kind == 'amount':
        try:
            amount = int(exact_amount(value, 'USD'))  # Decimal shape only; currency remains unconfirmed.
            if key == 'payment_amount' and amount <= 0:
                raise ValueError('Deposit amount must be positive')
        except ValueError:
            value = ''
            issues.append('Check the amount in the PDF, including every digit and separator.')
    return dict(key=key, label=label, input_type=kind, printed_label=label,
                raw=raw, value=value, issues=issues, source_cells=cells)


def propose_deposit_receipt(source):
    rows = source['rows']
    # A statement's mention of a deposit or receipt is not a teller receipt.
    bank = [c for r in rows for c in r['cells'] if c['expected_text'].strip() == 'Andrews Federal Credit Union'
            and _position(c) and _position(c)[0][1] < _position(c)[1][1] * .25]
    headings = [r for r in rows if re.fullmatch(r'Deposit to (FREE CHECKING|BASE SHARE SAVINGS|VISA PAYMENT) \d{4}', _text(r))]
    if len(bank) != 1 or not headings or not any(_text(r).startswith('Tlr:') for r in rows):
        return None
    identifier = _digest(dict(page=source['page_number'], table=source['table_index'], kind='andrews_deposit'))
    empty = dict(schema=SCHEMA, version=VERSION, kind='deposit_receipt', document_id=identifier,
                 page_numbers=[source['page_number']], fields=[], supported=False, issues=[], creates_transactions=False)
    if len(headings) != 1 or any(re.search(r'Account\s*Statement|Previous Balance', _text(r)) for r in rows):
        return dict(empty, issues=['This page contains multiple or conflicting document sections. Check the original before recording the receipt separately.'])
    share = re.fullmatch(r'Deposit to (.+) (\d{4})', _text(headings[0]))[2]
    fields = [
        _field(source,'payment_amount','Deposit amount',r'Amount:\s+(.+)','amount'),
        dict(key='currency',label='Receipt currency',input_type='currency',printed_label='Currency',raw='',value='',source_cells=[],
             issues=['Choose the currency after checking the receipt and supporting evidence. The bank name does not identify it.']),
        _field(source,'effective_date','Effective date',r'Eff:\s+(\S+)\s+Date:\s+\S+','date'),
        _field(source,'receipt_date','Receipt date',r'Eff:\s+\S+\s+Date:\s+(\S+)','date'),
        _field(source,'account_reference','Account reference as printed',r'Acct\s+([Xx*\d]+)(?:\s+.*)?',repeated=True),
        _field(source,'holder','Name on receipt',r'Acct\s+[Xx*\d]+\s+(.+)'),
        _field(source,'deposit_account','Deposit account and share',r'Deposit to (.+)'),
        _field(source,'previous_balance','Previous balance',r'Prev Bal:\s+(.+)','amount'),
        _field(source,'new_balance','New balance',r'New Bal:\s+(.+)','amount'),
        _field(source,'available_balance','Available balance',r'Avail Bal S'+re.escape(share)+r'\s+(.+)','amount'),
        _field(source,'sequence','Receipt sequence',r'Seq:\s+(.+)'),
        _field(source,'teller_time','Teller and printed time',r'Tlr:\s+(.+)'),
    ]
    issues = ['Save the checked receipt in Findings. Its deposit may already appear on a bank statement; saving a receipt does not add a transaction.',
              'Check any handwritten marks in the original PDF. They are not interpreted automatically. Keep a masked account reference as printed.']
    values = {f['key']:f['value'] for f in fields}
    if all(values.get(k) for k in ('previous_balance','new_balance','payment_amount')):
        if int(exact_amount(values['previous_balance'],'USD')) + int(exact_amount(values['payment_amount'],'USD')) != int(exact_amount(values['new_balance'],'USD')):
            issues.append('The previous balance plus the deposit differs from the new balance. Compare all three amounts with the original.')
    return dict(empty,supported=True,fields=fields,issues=issues,source_revision=_digest(dict(version=VERSION,source=source)))


def deposit_receipt_choices(sources):
    choices = []
    for source in sources:
        p = propose_deposit_receipt(source)
        if p is None:
            continue
        f = {field['key']:field for field in p['fields']}
        choices.append(dict(id=p['document_id'], document_kind=p['kind'], institution='Andrews Federal Credit Union',
            account_reference=f.get('account_reference',{}).get('value',''), account_label='Deposit receipt',
            period_start='',period_end='', printed_statement_date=f.get('effective_date',{}).get('raw',''),
            page_numbers=p['page_numbers']))
    return choices
