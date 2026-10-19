"""Read-only verification of the isolated two-row real-PDF acceptance export."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'data/local-runtime'
intake = json.loads((RUNTIME / 'real-pdf-intake-check.json').read_text())
review = json.loads((RUNTIME / 'real-pdf-review-check.json').read_text())
with ZipFile(RUNTIME / 'real-pdf-sample-export.zip') as archive:
    snapshot_bytes = archive.read('ledger-snapshot.json')
    manifest = json.loads(archive.read('manifest.json'))
    html = archive.read('ledger-report.html')
assert hashlib.sha256(snapshot_bytes).hexdigest() == manifest['document_sha256']
assert len(snapshot_bytes) == manifest['byte_count']
assert hashlib.sha256(html).hexdigest() == manifest['report']['sha256']
assert len(html) == manifest['report']['byte_count']
snapshot = json.loads(snapshot_bytes)
ledger = snapshot['ledger']
assert ledger['case_id'] == intake['case_id'] == review['case_id']
assert ledger['included_rows'] == 0 and ledger['excluded_rows'] == 2
rows = ledger['readings']
assert sorted(r['row']['amount_minor'] for r in rows) == ['10000', '1400']
assert {r['row']['key'] for r in rows} == {r['transaction_id'] for r in review['finalization']['transactions']}
for item in rows:
    row = item['row']
    assert not item['included'] and row['proof_class'] == 'p3'
    assert row['currency'] == 'USD' and row['direction'] == 'debit'
    assert row['locator']['kind'] == 'page_rectangle' and row['locator']['page'] == 4
    assert item['source']['evidence_file_id'] == intake['upload']['files'][0]['id']
    assert item['source']['sha256_at_ingestion'] == intake['original_sha256']
assert hashlib.sha256((ROOT/'data/loupe-test-pdfs'/intake['filename']).read_bytes()).hexdigest() == intake['original_sha256']
report = dict(case_id=intake['case_id'], exact_amounts_minor=['1400','10000'],currency='USD',
    included_rows=0,excluded_rows=2,source_page=4,original_unchanged=True,
    snapshot_hash_verified=True,html_hash_verified=True,
    limitation='Two selected P3 rows only; no full-statement verification. Structured candidate-review history is not bundled in the ledger export.')
(RUNTIME/'real-pdf-export-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
