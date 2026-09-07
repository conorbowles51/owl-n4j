"""Read-only counterparty summary parity on the isolated synthetic case."""
import json
from pathlib import Path
import httpx
root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:58002', timeout=30) as client:
    endpoint = '/api/financial/ledger-counterparties'
    assert client.get(endpoint, params={'case_id': fixture['case_id']}).status_code in (401,403)
    login = client.post('/api/auth/login', json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'})
    login.raise_for_status(); client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    reports = {}
    for name, filters, rows in [('case',{},10), ('account',{'account_id':fixture['gap_account_id']},4), ('empty',{'start_date':'2027-01-01'},0)]:
        params = {'case_id':fixture['case_id'], **filters}
        response = client.get(endpoint, params=params); response.raise_for_status(); data = response.json()
        summary = client.get('/api/financial/ledger-summary', params=params); summary.raise_for_status()
        assert data['currencies'] == summary.json()['currencies']
        assert data['included_rows'] == rows
        assert sum(group['rows'] for group in data['counterparties']) == rows
        for group in data['counterparties']:
            assert group['label'] is None
            assert len(group['transaction_ids']) == group['rows']
            assert group['source_document_ids']
        reports[name] = data
    (root / 'data/local-runtime/ledger-counterparties-check.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps({'case_rows':10,'account_rows':4,'empty_rows':0,'summary_parity':True}))
