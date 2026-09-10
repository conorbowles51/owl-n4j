"""Verify the read-only browser export of the existing pending real-PDF case."""
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile
from pypdf import PdfReader

with ZipFile('/tmp/loupe-case-review-export.zip') as archive:
    manifest = json.loads(archive.read('manifest.json'))
    raw = archive.read('ledger-snapshot.json')
    document = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == manifest['document_sha256']
    history = document['case_financial_history']
    reviews = history['pdf_review_history']
    assert history['case_id'] == document['ledger']['case_id'] == '3db2ae11-da7f-405a-a087-b465bdc9f12d'
    assert manifest['case_financial_history_included'] is True
    assert not document['ledger']['readings'] and not document['pdf_review_history']['candidates']
    assert len(reviews['candidates']) == 12 and not reviews['finalizations']
    for key in ('report', 'pdf_report', 'expert_support'):
        entry = manifest[key]
        content = archive.read(entry['filename'])
        assert len(content) == entry['byte_count'] and hashlib.sha256(content).hexdigest() == entry['sha256']
    support = json.loads(archive.read('expert-support.json'))
    assert support['human_decisions']['wider_case_financial_history']['status'] == 'included'
    pdf = archive.read('ledger-report.pdf')
    reader = PdfReader(io.BytesIO(pdf))
    assert 'Wider case financial review history' in ''.join(page.extract_text() for page in reader.pages)
    Path('/tmp/loupe-case-review-report.pdf').write_bytes(pdf)
    print(json.dumps(dict(pages=len(reader.pages), ledger_readings=0, wider_pending_candidates=12,
                         all_hashes_verified=True, financial_writes=0)))
