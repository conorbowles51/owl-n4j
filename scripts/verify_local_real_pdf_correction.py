"""Independently verify exact correction values and original source in the saved export."""
import hashlib,json
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parents[1]
report=json.loads((root/'data/local-runtime/real-pdf-correction-check.json').read_text())
with ZipFile(root/'data/local-runtime/real-pdf-corrected-export.zip') as z:
    raw=z.read('ledger-snapshot.json');s=json.loads(raw);manifest=json.loads(z.read('manifest.json'))
    assert hashlib.sha256(raw).hexdigest()==manifest['document_sha256']
    assert hashlib.sha256(z.read('ledger-report.html')).hexdigest()==manifest['report']['sha256']
    rows={r['row']['key']:r for r in s['ledger']['readings']}
    old=rows[report['original']['transaction_id']];new=rows[report['result']['replacement_id']]
    assert old['row']['amount_minor']=='6126' and new['row']['amount_minor']=='6162'
    assert old['exclusion_reason']=='superseded' and new['exclusion_reason']=='proof_class_not_included'
    assert old['provenance']['locator']==new['provenance']['locator']
    assert old['provenance']['locator']['page']==3
    assert any(c['text']=='$61.62' for c in old['provenance']['candidate_original']['cells'])
    decision=next(d for d in s['decisions'] if d['id']==report['result']['adjudication_id'])
    assert decision['before']['row']['amount_minor']=='6126' and decision['after']['row']['amount_minor']=='6162'
    assert s['ledger']['included_rows']==0 and s['ledger']['excluded_rows']==3
original=root/'data/loupe-test-pdfs/statements - Copy (3)_Redacted.pdf'
assert hashlib.sha256(original.read_bytes()).hexdigest()=='f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b'
result=dict(case_id=report['case_id'],original_minor='6126',replacement_minor='6162',printed_source='$61.62',original_unchanged=True,included_rows=0,excluded_rows=3)
(root/'data/local-runtime/real-pdf-correction-export-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
