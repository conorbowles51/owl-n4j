"""Authoritative posting graph: source-label groups are not resolved identities."""
import hashlib
import json
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.working_totals import working_totals_from_readings



def ledger_posting_graph(export, *, population='working'):
    if population not in ('working', 'verified'):
        raise LedgerSummaryError('Choose working or verified readings.')
    document = json.loads(export.snapshot.content)
    ledger = document['ledger']
    if not document.get('export_ready') or not ledger.get('history_captured'):
        raise LedgerSummaryError('A posting graph requires a consistent ledger and source history.')
    totals = working_totals_from_readings(ledger) if population == 'working' else ledger
    readings = [r for r in ledger['readings'] if (r['exclusion_reason'] in (None, 'proof_class_not_included') if population == 'working' else r['included'])]
    nodes, edges = {}, []
    for reading in readings:
        row = reading['row']; account = row.get('canonical_account_id') or row['account_id']; label = row.get('from_name' if row['direction'] == 'credit' else 'to_name', row['counterparty_raw'])
        if label is not None and not isinstance(label, str): raise LedgerSummaryError('A source counterparty label is invalid.')
        account_key = 'account:' + account
        account_details = reading.get('account', {})
        nodes.setdefault(account_key, dict(id=account_key, kind='account', account_id=account,
            label=row.get('canonical_account_label') or account_details.get('label') or ('Account ' + account[:8])))
        group_key = 'source-label:' + hashlib.sha256(json.dumps([account, row['currency'], label], ensure_ascii=False).encode()).hexdigest()
        if not row.get('counterparty_link'):
            nodes.setdefault(group_key, dict(id=group_key, kind='source_label', account_id=account,
                label=label or 'Name not identified'))
        identity = row.get('counterparty_link')
        if identity:
            group_key = identity['kind'] + ':' + identity['id']
            nodes.setdefault(group_key, dict(id=group_key, kind='account' if identity['kind'] == 'account' else 'source_label', account_id=identity['id'] if identity['kind'] == 'account' else account, label=identity['label']))
        source, target = (account_key, group_key) if row['direction']=='debit' else (group_key, account_key)
        edges.append(dict(id=row['key'], source=source, target=target, transaction_id=row['key'],
            source_document_id=row['source_document_id'], currency=row['currency'], amount_minor=row['amount_minor'],
            direction=row['direction'], ordering_date=row['ordering_date'], description=row['description'],
            proof_class=row['proof_class'], category=row.get('category', ''),
            label_sources=row.get('label_sources', {})))
    return dict(case_id=ledger['case_id'], account_id=ledger['account_id'], start_date=ledger['start_date'], end_date=ledger['end_date'],
        population=population, snapshot_sha256=export.snapshot.sha256, applied=False,
        nodes=sorted(nodes.values(), key=lambda n:n['id']), edges=edges, currencies=totals['currencies'], excluded_rows=totals['excluded_rows'],
        limitation='One edge per current posting. Arrows show the account posting direction. Names may come from the statement, investigator edits, or description suggestions; each edge records its label origins. Name groups are local to each account and currency; equal names do not establish identity. Missing labels do not identify a party. Transfers are not paired in this graph; use the separate transfer scenario for explicit pairing assumptions.')
