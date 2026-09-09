"""Independently verify original PDF bytes, exact snapshots and review history in bundles."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parents[1]
files=[('first','006406-006461 Hopper Lashika 0225 esubp resp_Redacted.pdf','5a3ad9b75a08280af2d80240974831fed7848105fc3a6168b47bb365947e9409'),
       ('second','statements - Copy (3)_Redacted.pdf','f9292c6e6c360b0bb6dc1534019a682bc0e0f04f656a36f723fff60f64a27c7b')]
reports=[]
for name,filename,digest in files:
    original=(root/'data/loupe-test-pdfs'/filename).read_bytes()
    assert hashlib.sha256(original).hexdigest()==digest
    with ZipFile(root/f'data/local-runtime/{name}-pdf-with-sources.zip') as archive:
        manifest=json.loads(archive.read('manifest.json'))
        raw=archive.read('ledger-snapshot.json');snapshot=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==manifest['document_sha256']
        assert hashlib.sha256(archive.read('ledger-report.html')).hexdigest()==manifest['report']['sha256']
        assert manifest['source_files_verified_against_ingestion'] is True
        assert len(manifest['source_files'])==1
        record=manifest['source_files'][0]
        assert archive.read(record['archive_path'])==original
        assert record['sha256']==digest and record['byte_count']==len(original)
        assert record['filename']==filename
        assert len(archive.namelist())==4
        assert snapshot['ledger']['included_rows']==0 and snapshot['ledger']['excluded_rows']==2
        assert len(snapshot['pdf_review_history']['reviews'])==2
        reports.append(dict(sample=name,sha256=digest,source_bytes=len(original),original_unchanged=True,
            bundled_source_identical=True,snapshot_and_report_hashes_verified=True,included_rows=0,excluded_rows=2))
(root/'data/local-runtime/original-source-export-verification.json').write_text(json.dumps(reports,indent=2))
print(json.dumps(reports))
