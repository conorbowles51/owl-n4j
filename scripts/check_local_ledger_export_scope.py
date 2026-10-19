"""Read-only authenticated export/summary parity and refusal checks on synthetic data."""
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4
import zipfile
import httpx

root = Path(__file__).resolve().parents[1]
fixture = json.loads((root / 'data/local-runtime/coverage-check.json').read_text())
endpoint = '/api/financial/ledger-export'
with httpx.Client(base_url='http://127.0.0.1:58002', timeout=60) as client:
    assert client.get(endpoint, params={'case_id': fixture['case_id']}).status_code in (401, 403)
    login = client.post('/api/auth/login', json={'username': 'loupe-local@example.com', 'password': 'Loupe-local-test-2026'})
    login.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
    reports = {}
    for name, filters, expected in (
        ('case', {}, 10),
        ('account', {'account_id': fixture['gap_account_id']}, 4),
        ('closed_interval', {'account_id': fixture['gap_account_id'], 'start_date': '2026-01-15', 'end_date': '2026-01-15'}, 4),
        ('empty', {'start_date': '2026-02-01', 'end_date': '2026-02-28'}, 0),
        ('unknown_account_empty', {'account_id': str(uuid4())}, 0),
    ):
        params = {'case_id': fixture['case_id'], **filters}
        response = client.get(endpoint, params=params)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            snapshot = archive.read('ledger-snapshot.json')
            report = archive.read('ledger-report.html')
            manifest = json.loads(archive.read('manifest.json'))
            data = json.loads(snapshot)
        summary = client.get('/api/financial/ledger-summary', params=params)
        summary.raise_for_status()
        for key in ('case_id', 'account_id', 'start_date', 'end_date', 'currencies', 'included_rows', 'excluded_rows', 'exclusions'):
            assert data['ledger'][key] == summary.json()[key], (name, key)
        assert data['ledger']['included_rows'] == expected
        assert hashlib.sha256(snapshot).hexdigest() == manifest['document_sha256']
        assert hashlib.sha256(report).hexdigest() == manifest['report']['sha256']
        assert manifest['report']['derived_from_sha256'] == manifest['document_sha256']
        for key in ('account_id', 'start_date', 'end_date'):
            assert response.headers['X-Loupe-' + key.replace('_', '-')] == filters.get(key, '')
        reports[name] = {'rows': expected, 'summary_matches': True, 'hashes_match': True}
    for name, params, statuses in (
        ('missing_case', {'case_id': str(uuid4())}, (403, 404)),
        ('reversed_dates', {'case_id': fixture['case_id'], 'start_date': '2026-02-01', 'end_date': '2026-01-01'}, (422,)),
    ):
        response = client.get(endpoint, params=params)
        assert response.status_code in statuses, (name, response.status_code)
        assert 'application/zip' not in response.headers.get('content-type', '')
        reports[name] = {'refused': True, 'status': response.status_code}
    (root / 'data/local-runtime/ledger-export-scope-check.json').write_text(json.dumps(reports, indent=2))
    print(json.dumps(reports))
