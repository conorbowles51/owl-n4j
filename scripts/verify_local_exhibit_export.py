"""Check the read-only real-statement exhibit capture, including its rendered PDF."""
import hashlib
import json
import zipfile
from pathlib import Path
import pymupdf

root = Path(__file__).resolve().parents[1]
with zipfile.ZipFile(root / 'data/local-runtime/ledger-exhibit-export.zip') as archive:
    document = json.loads(archive.read('ledger-snapshot.json'))
    manifest = json.loads(archive.read('manifest.json'))
    assert hashlib.sha256(archive.read('ledger-snapshot.json')).hexdigest() == manifest['document_sha256']
    sections = document['exhibit_assessment']['sections']
    assert not sections[0]['available']
    working = next(s for s in sections if s['population'] == 'working_totals')
    table = next(s for s in sections if s['population'] == 'table_view')
    assert working['software_rule'] == 'rule_107' and working['net_postings_minor'] == '6222'
    assert table['software_rule'] == 'rule_107' and table['net_postings_minor'] == '-6162'
    assert all(not source['disclosure_recorded'] for section in sections if section['available'] for source in section['sources'])
    pdf = archive.read('ledger-report.pdf')
    assert hashlib.sha256(pdf).hexdigest() == manifest['pdf_report']['sha256']
    pages = pymupdf.open(stream=pdf, filetype='pdf')
    text = '\n'.join(page.get_text() for page in pages)
    assert 'below the ledger' not in text
    assert 'review and decision history' in text
    matching = []
    for index, page in enumerate(pages):
        if 'Exhibit assessment' in page.get_text() or 'Rule 107' in page.get_text():
            page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(f'/tmp/loupe-exhibit-page-{index+1}.png')
            matching.append(index+1)
    assert matching
    report = dict(case_id=document['ledger']['case_id'], pages=len(pages), assessment_pages=matching,
                  working_net_minor='6222', table_net_minor='-6162', classification='rule_107',
                  disclosure_claimed=False, hashes_verified=True)
    (root / 'data/local-runtime/ledger-exhibit-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
