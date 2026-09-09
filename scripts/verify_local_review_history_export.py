"""Verify exact review history in the existing real-PDF sample export."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parents[1]/'data/local-runtime'
expected=json.loads((root/'real-pdf-review-check.json').read_text())
with ZipFile(root/'real-pdf-history-export.zip') as z:
    raw=z.read('ledger-snapshot.json');manifest=json.loads(z.read('manifest.json'));html=z.read('ledger-report.html')
assert hashlib.sha256(raw).hexdigest()==manifest['document_sha256']
assert len(raw)==manifest['byte_count']
assert hashlib.sha256(html).hexdigest()==manifest['report']['sha256']
snapshot=json.loads(raw);history=snapshot['pdf_review_history']
assert snapshot['schema']=='loupe.financial.ledger_snapshot/3'
assert snapshot['ledger']['included_rows']==0 and snapshot['ledger']['excluded_rows']==2
assert manifest['decision_count']==0 and manifest['pdf_candidate_review_count']==2
assert manifest['pdf_candidate_count']==2 and manifest['pdf_finalization_count']==1
assert {c['id'] for c in history['candidates']}==set(expected['candidate_ids'])
assert {l['transaction_id'] for l in history['transaction_links']}=={r['transaction_id'] for r in expected['finalization']['transactions']}
assert sorted(r['reading']['amount_minor'] for r in history['reviews'])==['10000','1400']
assert all(r['actor'] and r['reason'] and r['previous_revision'] for r in history['reviews'])
assert any('OC' in str(c['snapshot']) for c in history['candidates'])
assert all('DC' in r['reading']['description'] for r in history['reviews'])
assert b'PDF reading review history' in html
report=dict(case_id=expected['case_id'],candidates=2,reviews=2,finalizations=1,originals_and_corrections_preserved=True,hashes_verified=True,included_rows=0,excluded_rows=2)
(root/'review-history-export-verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
