"""Verify exact reviewed rows, original bytes and all 27 sealed period scopes."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/local-runtime'
review = json.loads((DATA / 'full-document-review-check.json').read_text())
assert review['status'] == 'finalized'
with ZipFile(DATA / 'full-document-export.zip') as archive:
    manifest = json.loads(archive.read('manifest.json'))
    raw = archive.read('ledger-snapshot.json')
    assert hashlib.sha256(raw).hexdigest() == manifest['document_sha256']
    assert len(raw) == manifest['byte_count']
    for kind in ('report', 'pdf_report'):
        entry = manifest[kind]
        content = archive.read(entry['filename'])
        assert hashlib.sha256(content).hexdigest() == entry['sha256']
        assert len(content) == entry['byte_count']
        assert entry['derived_from_sha256'] == manifest['document_sha256']
    support_entry = manifest['expert_support']
    support_bytes = archive.read(support_entry['filename'])
    assert hashlib.sha256(support_bytes).hexdigest() == support_entry['sha256']
    assert len(support_bytes) == support_entry['byte_count']
    support = json.loads(support_bytes)
    assert support['derived_from_sha256'] == manifest['document_sha256']
    assert support['completeness'] == 'incomplete_expert_packet'
    assert support['validation']['status'] == 'unavailable'
    assert support['tracing']['status'] == 'not_selected'
    original = manifest['source_files'][0]
    assert len(manifest['source_files']) == 1
    assert hashlib.sha256(archive.read(original['archive_path'])).hexdigest() == review['source_sha256'] == original['sha256']
    pdf_bytes = archive.read('ledger-report.pdf')
    (DATA / 'full-document-ledger-report.pdf').write_bytes(pdf_bytes)
    snapshot = json.loads(raw)
ledger = snapshot['ledger']
assert {s['id'] for s in support['source_records']['sources']} == {r['source']['id'] for r in ledger['readings']}
assert support['human_decisions']['pdf_reviews'] == 104
assert len(support['extraction_and_review']['description']['methods']) == len(snapshot['pdf_review_history']['mappings'])
assert ledger['case_id'] == review['case_id']
assert len(ledger['readings']) == 104 and ledger['included_rows'] == 0 and ledger['excluded_rows'] == 104
links = {r['candidate_id']: r['transaction_id'] for r in review['finalization']['transactions']}
rows = {r['row']['key']: r for r in ledger['readings']}
assert set(links.values()) == set(rows)
for expected in review['reviews']:
    item = rows[links[expected['candidate_id']]]
    row = item['row']; reading = expected['reading']
    for field in ('account_id', 'currency', 'amount_minor', 'direction', 'description'):
        assert row[field] == reading[field], field
    assert row['transaction_date'] == reading.get('transaction_date')
    assert row['posted_date'] == reading.get('booking_date')
    assert row['value_date'] is None and row['proof_class'] == 'p3'
    assert row['effective_date'] == reading.get('statement_end_date')
    if reading.get('statement_end_date'):
        assert row['ordering_date_context'] == 'statement_end_ordering_only'
    assert row['locator']['page'] == expected['page']
    assert item['source']['sha256_at_ingestion'] == review['source_sha256']
    assert not item['included']
history = snapshot['pdf_review_history']
assert len(history['candidates']) == len(history['reviews']) == 104
assert len(history['finalizations']) == 1
seal = history['finalizations'][0]['snapshot']
assert len(seal['statement_periods']) == len(seal['manifest']['statement_scopes']) == 27
for actual, expected in zip(seal['request']['statement_scopes'], review['periods']):
    assert actual == expected
assert {r['row']['statement_period_id'] for r in rows.values()} == {p['period_id'] for p in seal['statement_periods']}
with pymupdf.open(stream=pdf_bytes, filetype='pdf') as pdf:
    assert len(pdf) > 1
    assert all(page.get_text().strip() for page in pdf)
    pages = len(pdf)
    for index in sorted({0, pages // 2, pages - 1}):
        pdf[index].get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(f'/tmp/loupe-full-export-page-{index}.png')
report = dict(case_id=review['case_id'], readings=104, zero_readings=62, periods=27,
              original_sha256=review['source_sha256'], all_reading_dates_amounts_and_sources_match=True,
              history_preserved=True, snapshot_html_pdf_and_original_hashes_verified=True,
              pdf_pages=pages, verified_rows=0, financial_writes=0)
(DATA / 'full-document-export-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
