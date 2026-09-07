"""Check the ZIPs saved by check_local_cross_view_exclusion.cjs; no DB writes."""
from pathlib import Path
import json
import zipfile
import hashlib
root=Path(__file__).resolve().parents[1] / 'data/local-runtime'
report=json.loads((root/'cross-view-exclusion-check.json').read_text())
snapshots=[]
for name,total,rows in [('excluded','170000',9),('restored','210000',10)]:
    with zipfile.ZipFile(root/f'cross-view-{name}.zip') as archive:
        content=archive.read('ledger-snapshot.json')
        manifest=json.loads(archive.read('manifest.json'))
        html=archive.read('ledger-report.html')
        assert hashlib.sha256(content).hexdigest()==manifest['document_sha256']
        assert hashlib.sha256(html).hexdigest()==manifest['report']['sha256']
        assert len(content)==manifest['byte_count'] and len(html)==manifest['report']['byte_count']
        data=json.loads(content)
        assert data['ledger']['case_id']==report['case_id']
        assert data['ledger']['included_rows']==rows and data['ledger']['excluded_rows']==10-rows
        assert data['ledger']['currencies'][0]['credits_minor']==total
        reading=next(r for r in data['ledger']['readings'] if r['row']['key']==report['excluded_row_id'])
        assert reading['included']==(name=='restored')
        assert reading['row']['amount_minor']=='40000'
        snapshots.append(data)
assert len(snapshots[1]['decisions'])==len(snapshots[0]['decisions'])+1
assert any(d['subject_id']==report['excluded_row_id'] and d['decision']=='quarantine_row' for d in snapshots[0]['decisions'])
report.update(exports_verified=True,excluded_decisions=len(snapshots[0]['decisions']),restored_decisions=len(snapshots[1]['decisions']),hashes_verified=True)
(root/'cross-view-exclusion-check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
