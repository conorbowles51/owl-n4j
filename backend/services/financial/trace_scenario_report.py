"""Readable saved tracing inputs and results, after archive replay has verified them."""
from html import escape

from services.financial.ledger_summary import LedgerSummaryError
from services.financial.money import Money


METHOD_NAMES = {
    'first_in_first_out': 'First in, first out (FIFO)',
    'last_in_first_out': 'Last in, first out (LIFO)',
    'pro_rata': 'Proportional allocation',
    'lowest_intermediate_balance': 'Lowest intermediate balance',
    'direct': 'Direct tracing',
}
METHOD_NOTES = {
    'shortfall_shared_rateably_between_claims': 'The available money was insufficient and the shortfall was shared proportionally between claims.',
    'balance_went_negative_traceable_fund_exhausted': 'The balance went below zero, exhausting the money available to trace at that point.',
    'intraday_order_not_evidenced': 'The statements do not establish the order of payments on the same day.',
    'withdrawal_drew_on_opening_balance': 'A withdrawal used some of the opening money.',
    'direct_match_ambiguous_and_refused': 'More than one direct match was possible, so no match was selected.',
    'direct_withdrawal_not_identified': 'The direct method could not assign a withdrawal to a deposit.',
}


class _Link(str):
    """Only internally constructed links bypass cell escaping."""


def render_scenario_report(scenario, *, scenario_sha256, preparation=None):
    def text(value):
        return escape('Not recorded' if value is None else str(value), quote=True)

    def table(headers, rows):
        return '<table><thead><tr>' + ''.join('<th>' + text(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join('<td data-label="' + text(headers[i]) + '">' +
                            (str(value) if isinstance(value, _Link) else text(value)) + '</td>'
                            for i, value in enumerate(row)) + '</tr>' for row in rows) + '</tbody></table>'

    def money(value, currency):
        return 'Not recorded' if value is None else Money(int(value), currency).format()

    def recorded_money(value):
        return money(value['minor_units'], value['currency'])

    inputs = scenario['inputs']
    network = scenario['schema'] == 'loupe.financial.network_trace/1'
    results = scenario['results'] if network else scenario['comparison']['results']
    currency = inputs['currency'] if network else next(iter(results.values()))['currency']
    readings = scenario['ledger_snapshot']['ledger']['readings']
    by_id = {item['row']['key']: item for item in readings}
    anchors = {item['row']['key']: 'payment-' + str(i) for i, item in enumerate(readings, 1)}
    accounts = {item['row']['account_id']: (item.get('account') or {}).get('label') for item in readings}
    registrations = (scenario['ledger_snapshot'].get('processing_provenance') or {}).get('evidence_registrations', [])
    filenames = {item['id']: item.get('original_filename') for item in registrations}

    def account(key):
        return (accounts[key] + ' (' + key + ')') if accounts.get(key) else key

    def payment(key):
        if key not in by_id:
            raise LedgerSummaryError('Tracing report references a payment outside the captured source readings.')
        row = by_id[key]['row']
        label = (row.get('ref_id') or key) + ': ' + row['ordering_date'] + ' ' + (row.get('description') or 'No description')
        return _Link('<a href="#' + anchors[key] + '">' + text(label) + '</a>')

    marking = {'unmarked': 'No privilege marking selected', 'confidential': 'Confidential',
               'privileged_confidential': 'Privileged and confidential'}.get((preparation or {}).get('privilege_marking', 'unmarked'))
    if marking is None:
        raise LedgerSummaryError('Unsupported tracing report marking.')
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Saved money tracing calculation</title>',
        '<style>body{font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}h1{color:#a51b34}h2{margin-top:2.5rem}table{border-collapse:collapse;width:100%;table-layout:fixed;margin:1rem 0}th,td{border:1px solid #aab;padding:.5rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eef1f5}p,li,code{overflow-wrap:anywhere}a{color:#8b1730}section:target{outline:2px solid #a51b34;outline-offset:6px}section{scroll-margin-top:1rem}@media screen and (max-width:600px){table,tbody,tr,td{display:block;width:auto}thead{display:none}tr{border:1px solid #aab;margin:1rem 0}td{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;border:0;border-bottom:1px solid #dde}td:before{content:attr(data-label);font-weight:600}}@media print{thead{display:table-header-group}h2,h3,h4{break-after:avoid}tr{break-inside:avoid}}@page{size:A4;margin:18mm 16mm 20mm}</style></head><body>',
        '<p><a href="../../review-index.html">Package contents</a> · <a href="scenario.json">Original saved calculation</a> · <a href="expert-support.json">Processing and review records</a></p>',
        '<h1>Saved money tracing calculation</h1><p>' + text(marking) + '</p>',
        '<p>This report explains the saved inputs and shows the result under each selected method. Select a payment link to see its captured values and statement reference. It does not load or change the current case.</p>',
        table(['Saved setting', 'Value'], [
            ['Case', scenario['case_id']], ['Accounts', 'Several accounts' if network else account(inputs['account_id'])],
            ['From', inputs['start_date']], ['To', inputs['end_date']], ['Currency', currency],
            ['Transaction selection', 'Imported transactions, including those awaiting further verification' if inputs['population'] == 'working' else 'Separately verified transactions'],
            ['Payments in the chosen order', len(inputs['ordered_transaction_ids'])],
            ['Selected methods', ', '.join(METHOD_NAMES.get(name, name.replace('_', ' ')) for name in inputs['doctrines'])]]),
        '<nav><a href="#assumptions">Recorded reasons</a> · <a href="#results">Results by method</a> · <a href="#payments">Payments and sources</a></nav>',
        '<h2 id="assumptions">Recorded reasons and assumptions</h2>',
        '<p>These are the investigator\'s saved choices. They are not additional facts extracted from the statements.</p>']
    openings = inputs['openings'] if network else [dict(account_id=inputs['account_id'], amount_minor=inputs['opening_balance_minor'], basis=inputs['opening_basis'])]
    parts += ['<h3>Opening money</h3>', table(['Account', 'Amount', 'Reason'], [
        [account(item['account_id']), money(item['amount_minor'], currency), item['basis']] for item in openings]),
        '<h3>Money assigned to each claim</h3><p>A claim is the named amount being followed through the selected payments.</p>',
        table(['Payment', 'Claim', 'Amount assigned', 'Reason'], [
            [payment(item['transaction_id']), item['claim_id'], money(item['amount_minor'], currency), item['basis']] for item in inputs['attributions']]),
        '<h3>Payment order</h3><p>' + text(inputs['order_basis']) + '</p>',
        table(['Position', 'Payment'], [[i, payment(key)] for i, key in enumerate(inputs['ordered_transaction_ids'], 1)])]
    if network:
        parts += ['<h3>Selected transfers</h3><p>' + text(inputs['basis']) + '</p>',
            table(['Money leaving', 'Money received'], [[payment(pair['debit_id']), payment(pair['credit_id'])] for pair in inputs['pairs']]),
            table(['Timing setting', 'Value'], [
                ['Allowed date difference (days)', inputs['tolerance_days']],
                ['Earlier receipt allowed', 'Yes' if inputs['allow_backward'] else 'No'],
                ['Earlier receipt used in this calculation', 'Yes' if scenario['backward_timing_used'] else 'No'],
                ['Reason for earlier receipt', inputs['backward_basis'] or 'Not selected']])]

    def allocation(values, unit):
        rows = [[claim, money(amount, unit)] for claim, amount in values['allocated_by_claim'].items()]
        # The saved outside-claims total already includes unidentified/unfunded
        # portions. Split it before displaying additive allocation categories.
        other = int(values['outside_claims_minor']) - int(values['unidentified_minor']) - int(values['unfunded_minor'])
        if other < 0:
            raise LedgerSummaryError('Saved asset allocation components exceed the outside-claims total.')
        rows.append(['Other recorded funds', money(other, unit)])
        rows += [[label, money(values[field], unit)] for field, label in (
            ('unidentified_minor', 'Not assigned by this method'),
            ('unfunded_minor', 'Not covered by the recorded funds'))]
        return table(['Allocation', 'Amount'], rows)

    def assets_report(assets):
        result = ['<h3>Asset purchases and resales</h3>']
        if not assets:
            return ''.join(result) + '<p>No asset purchases or resales were selected.</p>'
        result += ['<p>These amounts are already represented in the cash payments. Do not add them to the cash results again.</p>']
        for item in assets:
            unit = item['currency']
            result += ['<h4>' + text(item['asset_label']) + '</h4>',
                table(['Recorded item', 'Value'], [
                    ['Purchase payment', payment(item['transaction_id'])], ['Reason', item['basis']],
                    ['Whole payment', money(item['amount_minor'], unit)],
                    ['Amount assigned to this purchase', money(item.get('asset_amount_minor', item['amount_minor']), unit)],
                    ['Payment left after this allocation', money(item.get('remaining_withdrawal_minor'), unit)],
                    ['Allocation order', item.get('allocation_sequence')],
                    ['Allocation rule', (item.get('allocation_basis') or 'Not recorded').replace('_', ' ')]]),
                allocation(item, unit), '<p>' + text(item['limitation']) + '</p>']
            resale = item.get('resale')
            if resale:
                result += ['<h4>Resale</h4>', table(['Recorded item', 'Value'], [
                    ['Receipt payment', payment(resale['transaction_id'])], ['Reason', resale['basis']],
                    ['Whole receipt', money(resale.get('receipt_minor'), unit)],
                    ['Proceeds assigned to this resale', money(resale['proceeds_minor'], unit)],
                    ['Allocation rule', resale['allocation_basis'].replace('_', ' ')]]),
                    allocation(resale, unit), '<p>' + text(resale['limitation']) + '</p>']
        return ''.join(result)

    parts += ['<h2 id="results">Results by method</h2>',
        '<p>Each method is a separate calculation of the same saved payments. Compare the results; do not add results from different methods together.</p>']
    for method in inputs['doctrines']:
        result = results[method]
        parts += ['<h3>' + text(METHOD_NAMES.get(method, method.replace('_', ' '))) + '</h3>']
        if network:
            parts += [table(['Claim', 'Starting amount assigned', 'Remaining across accounts', 'Withdrawn outside selected transfers'], [
                [claim, money(item['root_attributed_minor'], currency), money(item['reported_remaining_minor'], currency),
                 money(item['withdrawn_without_selected_transfer_minor'], currency)] for claim, item in result['claims'].items()]),
                '<p>Withdrawals not assigned by this method: ' + text(money(result['unidentified_withdrawals_minor'], currency)) + '.</p>',
                '<h4>Money carried through each transfer</h4>']
            for hop in result['hops']:
                parts += [table(['Transfer detail', 'Value'], [
                    ['From account', account(hop['from_account'])], ['To account', account(hop['to_account'])],
                    ['Money leaving', payment(hop['debit_id'])], ['Money received', payment(hop['credit_id'])],
                    ['Whole transfer', money(hop['amount_minor'], currency)], ['Earlier receipt used', 'Yes' if hop['backward_timing'] else 'No']]),
                    table(['Claim carried to receiving account', 'Amount'], [[claim, money(amount, currency)] for claim, amount in hop['propagated_by_claim'].items()]),
                    '<p>Other or unidentified transfer money: ' + text(money(hop['unattributed_or_unidentified_minor'], currency)) + '.</p>']
            account_results = result['accounts']
        else:
            account_results = {inputs['account_id']: result}
        for account_id, calculation in account_results.items():
            parts += ['<h4>' + text(account(account_id)) + '</h4>',
                table(['Claim', 'Amount assigned', 'Remaining in account', 'Withdrawn'], [
                    [claim, recorded_money(item['deposited']), recorded_money(item['surviving']), recorded_money(item['withdrawn'])]
                    for claim, item in calculation['outcomes'].items()]),
                '<p>Account-level figures can include money received through a selected transfer. Do not sum them to calculate the starting claim.</p>' if network else '',
                '<ul>' + ''.join('<li>' + text(METHOD_NOTES.get(note, note)) + '</li>' for note in calculation['notes']) + '</ul>']
        parts += [assets_report(result.get('asset_uses', []) if network else scenario.get('asset_uses', {}).get(method, []))]

    parts += ['<h2 id="payments">Payments and sources</h2>',
        '<p>The chosen payment order above identifies which readings were used. Other readings may be present in the saved snapshot as context. The statement reference points to the original file and page where recorded; missing locations remain unavailable.</p>']
    positions = {key: i for i, key in enumerate(inputs['ordered_transaction_ids'], 1)}
    for item in readings:
        row, source = item['row'], item['source']
        parts += ['<section id="' + anchors[row['key']] + '"><h3>' + text(row.get('ref_id') or row['key']) + '</h3>',
            table(['Saved payment field', 'Value'], [
                ['Position in selected order', positions.get(row['key'], 'Not selected')], ['Account', account(row['account_id'])],
                ['Description', row.get('description')], ['Amount', money(row['amount_minor'], row['currency'])],
                ['Statement entry', {'credit': 'Credit', 'debit': 'Debit'}.get(row.get('direction'), 'Not recorded')],
                ['Date used for ordering', row['ordering_date']], ['Transaction date', row.get('transaction_date')],
                ['Posting date', row.get('posted_date')], ['Value date', row.get('value_date')],
                ['Source file', filenames.get(source.get('evidence_file_id')) or source.get('evidence_file_id') or source['id']],
                ['PDF page', (row.get('locator') or {}).get('page')], ['Source SHA-256', source.get('sha256_at_ingestion')],
                ['Payment ID', row['key']]]), '</section>']
    parts += ['<h2>Limits recorded with the calculation</h2><ul>' + ''.join('<li>' + text(note) + '</li>' for note in scenario['limitations']) + '</ul>',
        '<h2>Saved file reference</h2><p>Original scenario SHA-256: <code>' + text(scenario_sha256) + '</code>.</p>',
        '<p>The package manifest identifies this HTML report separately. The original JSON retains the full calculation, source readings and review history. The recalculation check confirms the saved arithmetic, not the accuracy of the evidence or the investigator\'s assumptions.</p></body></html>']
    content = ''.join(parts).encode('utf-8')
    if len(content) > 16 * 1024 * 1024:
        raise LedgerSummaryError('Readable tracing report exceeds 16 MiB; reduce the selected scenario.')
    return content
