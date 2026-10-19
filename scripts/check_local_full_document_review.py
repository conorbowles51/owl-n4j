"""Guarded full-file acceptance using public local APIs and reviewed PDF readings.

Only the isolated case below may be written. Default prepares/reviews; --finalize
requires the saved reviewed checkpoint. Never rerun a completed writer. Original
PDF is read-only; zero charge readings remain explicit, not nonzero payments.
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'data/local-runtime'
CASE = 'a2dae109-477c-4526-8642-c6a358a73479'
FILE = '91705496-fdcc-4ab4-b971-6463d39d4fca'
REPORT = RUNTIME / 'full-document-review-check.json'
PDF = ROOT / 'data/loupe-test-pdfs/statements - Copy (3)_Redacted.pdf'
SHA = 'f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b'


def save(report):
    REPORT.write_text(json.dumps(report, indent=2))


def resolve_date(raw, period):
    choices = []
    for year in {period['start'][:4], period['end'][:4]}:
        try:
            value = datetime.strptime(raw.replace('.', '') + ' ' + year, '%b %d %Y').date().isoformat()
        except ValueError:
            continue
        if period['start'] <= value <= period['end']:
            choices.append(value)
    if len(choices) != 1:
        raise ValueError('Printed row date is unresolved')
    return choices[0]


def main():
    finalize = sys.argv[1:] == ['--finalize']
    if sys.argv[1:] and not finalize:
        raise SystemExit('Use no arguments to prepare, or --finalize at the reviewed checkpoint.')
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise SystemExit('Original source changed')
    intake = json.loads((RUNTIME / 'full-document-pdf-intake-check.json').read_text())
    if intake['case_id'] != CASE or intake['status'] != 'source_ready' or intake['upload']['files'][0]['id'] != FILE:
        raise SystemExit('Unexpected intake checkpoint')
    if finalize:
        report = json.loads(REPORT.read_text())
        if report['status'] != 'reviewed' or report['case_id'] != CASE:
            raise SystemExit('Not at reviewed checkpoint; inspect before any retry')
    else:
        if REPORT.exists():
            raise SystemExit('Writer checkpoint exists; inspect before resuming')
        report = dict(case_id=CASE, evidence_file_id=FILE, source_sha256=SHA,
                      status='started', accounts={}, periods=[], mappings=[], reviews=[])
        save(report)
    with httpx.Client(base_url='http://127.0.0.1:58002', timeout=120, trust_env=False) as client:
        auth = client.post('/api/auth/login', json={'username': 'loupe-local@example.com', 'password': 'Loupe-local-test-2026'})
        auth.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + auth.json()['access_token']

        def call(method, route, body=None):
            response = client.request(method, '/api/financial/' + route, params={'case_id': CASE}, json=body)
            if not response.is_success:
                raise RuntimeError(f'{method} {route}: {response.status_code}: {response.text[:600]}')
            return response.json()

        if finalize:
            preview = call('POST', f'candidate-sources/{FILE}/finalization-preview', {'statement_scopes': report['periods']})
            if preview['revision'] != report['preview']['revision']:
                raise RuntimeError('Reviewed preview changed; no finalization attempted')
            report['status'] = 'finalizing'
            save(report)
            report['finalization'] = call('POST', f'candidate-sources/{FILE}/finalize', {
                'expected_revision': preview['revision'], 'statement_scopes': report['periods'],
                'documentary_financial_rows': True, 'accept_incomplete_coverage': True,
                'reason': 'Local full-document acceptance: 27 printed statement periods, 104 explicit readings including 62 printed zero charge lines. Header endings 3539 and 8441 kept as separate provisional accounts; no identity merge. Visually reviewed transaction-page layouts and source-bound date/amount cells. Undated interest retains statement-end ordering only. Preserve P3 and uncertainty about wider evidence completeness; no proof promotion.'})
            report['status'] = 'finalized'
            save(report)
            print(json.dumps({'status': report['status'], 'transactions': report['finalization']['transaction_count']}))
            return

        inventory = json.loads((RUNTIME / 'full-statement-inventory.json').read_text())
        if inventory['file_sha256'] != SHA or len(inventory['periods']) != 27 or any(p['status'] != 'arithmetically_agrees' for p in inventory['periods']):
            raise RuntimeError('Inventory requires inspection')
        with pymupdf.open(PDF) as pdf:
            for period in inventory['periods']:
                page = period['transaction_pages'][0]
                # Header ending is the statement perspective, not ownership or a
                # decision that a supplementary card is a separate bank account.
                header = re.findall(r'(?:Account|Mastercard|Card) ending (?:in )?(\d{4})', pdf[page - 1].get_text(), re.I)
                if len(set(header)) != 1 or header[0] not in ('3539', '8441'):
                    raise RuntimeError('Printed statement account header is unresolved')
                ending = header[0]
                source = call('GET', f'candidate-sources/{FILE}/pages/{page}')
                rows = {row['row_index']: row for row in source['rows']}
                grouped = defaultdict(list)
                for reading in period['readings']:
                    cells = rows[reading['row_index']]['cells']
                    by_column = {c['column_index']: c for c in cells}
                    original = reading['amount_source']
                    if by_column[original['column_index']]['expected_text'] != original['expected_text']:
                        raise RuntimeError('Fresh amount source differs from reviewed inventory')
                    if reading['date'] is None:
                        label = reading['label_source']
                        if by_column[label['column_index']]['expected_text'] != label['expected_text']:
                            raise RuntimeError('Fresh charge label differs')
                        roles = ((label['column_index'], 'description'), (original['column_index'], 'amount'))
                        description = label['expected_text']
                        dates = {'statement_end_date': period['end']}
                    else:
                        amount_col = original['column_index']
                        if amount_col not in (2, 3) or reading['date_source']['column_index'] != 0:
                            raise RuntimeError('Unreviewed dated row layout')
                        if by_column[0]['expected_text'] != reading['date_source']['expected_text']:
                            raise RuntimeError('Fresh date differs')
                        dates = {'transaction_date': resolve_date(by_column[0]['expected_text'], period)}
                        roles = [(0, 'transaction_date')]
                        if amount_col == 3:
                            roles.append((1, 'booking_date'))
                            dates['booking_date'] = resolve_date(by_column[1]['expected_text'], period)
                        description = by_column[amount_col - 1]['expected_text']
                        roles.extend([(amount_col - 1, 'description'), (amount_col, 'amount')])
                        roles = tuple(roles)
                    grouped[roles].append((reading, description, dates))
                candidate_ids = []
                for roles, values in grouped.items():
                    proposal = dict(schema_version='pdf-grid-mapping-v1', case_id=CASE, evidence_file_id=FILE,
                        source_revision=source['source_revision'], page_number=page, table_index=0,
                        columns=[dict(column_index=col, meaning=role) for col, role in roles],
                        rows=[dict(row_index=r['row_index'], cells=[dict(column_index=c['column_index'], expected_text=c['expected_text']) for c in rows[r['row_index']]['cells'] if c['column_index'] in {col for col, _ in roles}]) for r, _, _ in values])
                    mapped = call('POST', 'candidate-mappings', proposal)
                    report['mappings'].append(mapped['id'])
                    save(report)
                    candidates = {c['row_index']: c for c in mapped['candidates']}
                    for reading, description, dates in values:
                        candidate = candidates[reading['row_index']]
                        cid = candidate['id']
                        state = call('GET', f'candidates/{cid}/review')
                        if ending not in report['accounts']:
                            created = call('POST', f'candidates/{cid}/provisional-account', dict(
                                expected_revision=state['review_revision'], currency='USD',
                                label=f'LOCAL PDF REVIEW — statement ending {ending}',
                                reason=f'Printed statement header ending {ending}. Document-scoped provisional perspective only. Other header ending remains separate; supplementary-card sections do not establish ownership or cross-account identity.'))
                            report['accounts'][ending] = created['account']['id']
                            save(report)
                        reviewed = dict(account_id=report['accounts'][ending], currency='USD',
                            amount_minor=reading['amount_minor'], direction=reading['direction'],
                            description=description, **dates)
                        reason = (f'Local source review PDF page {page}, printed period {period["start"]}–{period["end"]}. '
                            'Original date and amount cells checked against prepared copy; sign interpreted using printed credit-card liability convention. '
                            'Separate printed transaction/posting dates retained where present. No inferred recipient identity. '
                            + ('Printed charge has no row date; statement end is ordering only. ' if reading['date'] is None else '')
                            + ('Printed zero charge retained explicitly; this is not a nonzero payment. ' if reading['amount_minor'] == '0' else '')
                            + 'Summary, APR and year-to-date repeated totals are not additional readings. P3 remains; wider record completeness is not certified.')
                        saved = call('POST', f'candidates/{cid}/review', dict(expected_revision=state['review_revision'], status='resolved', reason=reason, reading=reviewed))
                        if saved['reading']['amount_minor'] != reading['amount_minor']:
                            raise RuntimeError('Exact saved reading changed')
                        report['reviews'].append(dict(candidate_id=cid, page=page, row_index=reading['row_index'], reading=reviewed))
                        candidate_ids.append(cid)
                        save(report)
                summary_page = period['summary_pages'][0]
                summary = call('GET', f'candidate-sources/{FILE}/pages/{summary_page}')
                def bound(observation):
                    cell = observation['source']
                    matches = [c for row in summary['rows'] if row['row_index'] == observation['row_index'] for c in row['cells'] if c['column_index'] == cell['column_index'] and c['expected_text'] == cell['expected_text']]
                    if len(matches) != 1:
                        raise RuntimeError('Fresh printed control differs from inventory')
                    return dict(page_number=summary_page, table_index=0, row_index=observation['row_index'], column_index=cell['column_index'], expected_text=cell['expected_text'], source_revision=summary['source_revision'])
                scope = dict(account_id=report['accounts'][ending], currency='USD', candidate_ids=candidate_ids,
                    start=dict(value=period['start'], source=bound(period['date_source'])),
                    end=dict(value=period['end'], source=bound(period['date_source'])),
                    opening=dict(amount_minor=period['opening']['minor'], source=bound(period['opening'])),
                    closing=dict(amount_minor=period['closing']['minor'], source=bound(period['closing'])),
                    balance_convention='liability_owed', reason=f'Local acceptance: exact printed summary cells on PDF page {summary_page}, assigned source rows on page {page}. Liability owed convention; zero charges retained explicitly. Same arithmetic does not establish complete evidence or holder identity.')
                report['periods'].append(scope)
                save(report)
                print(json.dumps({'reviewed_periods': len(report['periods']), 'reviewed_readings': len(report['reviews'])}), flush=True)
        report['preview'] = call('POST', f'candidate-sources/{FILE}/finalization-preview', {'statement_scopes': report['periods']})
        if report['preview']['resolved_count'] != 104 or len(report['preview']['statement_scopes']) != 27:
            raise RuntimeError('Full preview scope is inconsistent')
        report['status'] = 'reviewed'
        report['zero_readings'] = sum(r['reading']['amount_minor'] == '0' for r in report['reviews'])
        save(report)
        print(json.dumps({'status': 'reviewed', 'readings': 104, 'zero_readings': report['zero_readings'], 'periods': 27}), flush=True)


if __name__ == '__main__':
    main()
