"""Read-only local health, real-PDF preservation and restored fixture check."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx
from sqlalchemy import create_engine, text

root = Path(__file__).resolve().parents[1]
expected = {
    '006406-006461 Hopper Lashika 0225 esubp resp_Redacted.pdf': '5a3ad9b75a08280af2d80240974831fed7848105fc3a6168b47bb365947e9409',
    'statements - Copy (3)_Redacted.pdf': 'f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b',
}
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'services': {}, 'real_pdfs': [], 'ai_processing_tested': False}
with httpx.Client(timeout=30) as client:
    for name, url in [('frontend','http://127.0.0.1:55174'),('backend','http://127.0.0.1:58002/health'),('engine','http://127.0.0.1:58003/health')]:
        response = client.get(url)
        assert response.status_code == 200, (name,response.status_code)
        report['services'][name] = response.status_code
    login = client.post('http://127.0.0.1:58002/api/auth/login', json={'username':'loupe-local@example.com','password':'Loupe-local-test-2026'})
    login.raise_for_status()
    response = client.get('http://127.0.0.1:58002/api/financial/ledger-summary',
        params={'case_id':'e0da5581-a1ac-4db5-a3a9-e17021fb807a'},
        headers={'Authorization':'Bearer '+login.json()['access_token']})
    response.raise_for_status()
    summary = response.json()
    assert summary['included_rows'] == 10 and summary['excluded_rows'] == 0
    assert summary['currencies'][0]['credits_minor'] == '210000'
    report['synthetic_fixture_restored'] = True
engine = create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
try:
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        for name, digest in expected.items():
            with (root / 'data/loupe-test-pdfs' / name).open('rb') as source:
                actual = hashlib.file_digest(source, 'sha256').hexdigest()
            assert actual == digest, 'PDF differs from inspection baseline: ' + name
            copies = connection.scalar(text('SELECT count(*) FROM evidence_files WHERE sha256=:digest OR original_filename=:name'), {'digest':digest,'name':name})
            assert copies == 0, 'Real PDF found in isolated test ingestion database: ' + name
            report['real_pdfs'].append({'file':name,'sha256':actual,'matches_inspection':True,'isolated_database_copies':copies})
finally:
    engine.dispose()
(root / 'data/local-runtime/handoff-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
