"""Read-only independent check of the real-PDF statement-control acceptance export."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
root = Path(__file__).resolve().parents[1]
report = json.loads((root/'data/local-runtime/statement-controls-review-check.json').read_text())
with ZipFile(root/'data/local-runtime/statement-controls-sample-export.zip') as archive:
    raw = archive.read('ledger-snapshot.json')
    snapshot = json.loads(raw)
    manifest = json.loads(archive.read('manifest.json'))
    assert hashlib.sha256(raw).hexdigest() == manifest['document_sha256']
    assert snapshot['ledger']['included_rows'] == 0
    assert snapshot['ledger']['excluded_rows'] == 2
    sealed = snapshot['pdf_review_history']['finalizations']
    assert len(sealed) == 1
    receipt = sealed[0]['snapshot']
    scopes = receipt['manifest']['statement_scopes']
    assert len(scopes) == 1
    scope = scopes[0]
    assert scope['balance_convention'] == 'liability_owed'
    assert scope['opening']['amount_minor'] == '670018'
    assert scope['closing']['amount_minor'] == '663796'
    assert scope['bound_controls']['opening']['source']['expected_text'] == '$6,700.18'
    assert scope['bound_controls']['closing']['source']['expected_text'] == '= $6,637.96'
    assert all(scope['bound_controls'][role]['locator']['page'] == 1 for role in ('start','end','opening','closing'))
    periods = receipt['statement_periods']
    assert len(periods) == 1
    assert periods[0]['period_id'] == report['statement_checks']['items'][0]['period_id']
    assert set(periods[0]['candidate_ids']) == set(report['candidate_ids'])
    assert report['statement_checks']['items'][0]['amounts']['difference'] == '5616'
original = root/'data/loupe-test-pdfs/statements - Copy (3)_Redacted.pdf'
assert hashlib.sha256(original.read_bytes()).hexdigest() == 'f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b'
result = dict(case_id=report['case_id'], source_controls_retained=True, original_unchanged=True,
              discrepancy_minor='5616', currency='USD', included_rows=0, excluded_rows=2)
(root/'data/local-runtime/statement-controls-export-verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
