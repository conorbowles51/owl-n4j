"""Read-only authenticated requested coverage against the isolated synthetic fixture."""
import json
from pathlib import Path
from uuid import uuid4
import httpx

root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
endpoint = '/api/financial/requested-statement-coverage'
params = dict(case_id=fixture['case_id'], account_id=fixture['gap_account_id'],
              start_date='2026-02-01', end_date='2026-02-28')
with httpx.Client(base_url='http://127.0.0.1:58002', timeout=30) as client:
    assert client.get(endpoint, params=params).status_code in (401, 403)
    login = client.post('/api/auth/login', json={'username': 'loupe-local@example.com', 'password': 'Loupe-local-test-2026'})
    login.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    reports = {}
    for name, expected in (('gap', 28), ('enclosing', 0)):
        params['account_id'] = fixture[name + '_account_id']
        response = client.get(endpoint, params=params)
        response.raise_for_status()
        result = response.json()
        assert result['case_id'] == fixture['case_id'] and result['account_id'] == params['account_id']
        assert result['applied'] is False and result['available'] is True
        assert result['currencies'][0]['uncovered_days'] == expected
        assert result['currencies'][0]['covered_days'] == 28 - expected
        reports[name] = result
    assert client.get(endpoint, params={**params, 'account_id': str(uuid4())}).status_code == 404
    assert client.get(endpoint, params={**params, 'start_date': '2026-03-01'}).status_code == 422
    (root / 'data/local-runtime/requested-coverage-check.json').write_text(json.dumps(reports, indent=2))
    print(json.dumps(dict(case_id=fixture['case_id'], gap_days=28, enclosing_gap_days=0, result='passed')))
