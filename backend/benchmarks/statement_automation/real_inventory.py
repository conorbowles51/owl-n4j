"""Private inventory of every real financial statement document (real-document phase).

Reads the live case database inside a READ ONLY transaction, never writes to it,
and never touches an original evidence file except to read its bytes. For every
evidence file that a financial batch item or a financial source document points
at, it records one private row per distinct document (distinct bytes):

* an opaque id (``d`` + the first 12 hex digits of the SHA-256),
* the SHA-256 and whether the original's bytes still match the evidence hash,
* the case(s), batch item ids and live statuses, source document ids/statuses,
* a family guess (from the document's own first-page text; the pipeline's institution label is only a fallback),
* the page count and whether pages carry a native text layer, an OCR text
  layer over a page image, or only an image (PyMuPDF; metadata, not truth).

Originals are copied (never moved) to ``<out>/docs/<id>.pdf``; the evidence
store is on another filesystem, so a hard link is not possible. Everything is
written under ``<out>``, which must be the private real-data directory: the
rows hold file names and case ids. Nothing here is committed.

From ``backend/``, with the service environment loaded ::

    python -m benchmarks.statement_automation.real_inventory --out /mnt/owl-data/fin-real
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# Family guesses from the document's own words. Order matters: the first
# pattern that matches the first pages' text wins. These are labels for
# grouping work, never facts used as ground truth.
FAMILY_PATTERNS = (
    ('andrews-deposit-receipt', r'andrews\s+federal.*(deposit\s+receipt|teller)'),
    ('andrews-share', r'andrews\s+federal|andrewsfcu'),
    ('credit-one-card', r'credit\s*one\s*bank'),
    ('capital-one-card', r'capital\s*one'),
    ('merrick-card', r'merrick\s*bank'),
    ('bbva-mexico', r'\bbbva\b|bancomer'),
    ('santander-mexico', r'santander'),
    ('scotiabank-mexico', r'scotiabank|scotia\b'),
    ('monex-mexico', r'\bmonex\b'),
    ('kapital-mexico', r'\bkapital\b'),
    ('intercam-mexico', r'intercam'),
    ('banorte-mexico', r'banorte'),
    ('banamex-mexico', r'banamex|citibanamex'),
    ('hsbc', r'\bhsbc\b'),
    ('bank-of-america', r'bank\s+of\s+america'),
    ('wells-fargo', r'wells\s+fargo'),
    ('chase', r'jpmorgan|chase\s+bank|\bchase\b'),
    ('navy-federal', r'navy\s+federal'),
    ('pnc', r'\bpnc\b'),
    ('truist', r'\btruist\b|suntrust|bb&t'),
    ('td-bank', r'\btd\s+bank\b'),
    ('citibank', r'citibank'),
    ('us-bank', r'u\.?s\.?\s+bank'),
    ('amex', r'american\s+express'),
    ('discover', r'discover\s+(card|bank)'),
    ('paypal', r'paypal'),
)
FULL_PAGE_IMAGE = 0.6   # share of the page area an image must cover to count as a scan


def guess_family(text, institution=None):
    lowered = (text or '').lower()
    for family, pattern in FAMILY_PATTERNS:
        if re.search(pattern, lowered, re.S):
            return family
    lowered = (institution or '').lower()
    for family, pattern in FAMILY_PATTERNS:
        if lowered and re.search(pattern, lowered, re.S):
            return family + '?'
    return 'unknown'


def classify_page(page):
    """``digital`` | ``scan_text_layer`` | ``image_only`` | ``blank`` for one PyMuPDF page.

    Inventory metadata only (which pages need OCR or visual truth), so the
    fast reader is used here; ground truth itself is read with pdfplumber.
    """
    rect = page.rect
    area = float(rect.width * rect.height) or 1.0
    covered = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info['bbox']
        width = max(0.0, min(x1, rect.x1) - max(x0, rect.x0))
        height = max(0.0, min(y1, rect.y1) - max(y0, rect.y0))
        covered = max(covered, width * height / area)
    chars = len(''.join(page.get_text('text').split()))
    if covered >= FULL_PAGE_IMAGE:
        return 'scan_text_layer' if chars >= 20 else 'image_only'
    if chars >= 20:
        return 'digital'
    return 'image_only' if covered > 0.05 else 'blank'


def document_mode(kinds):
    counts = Counter(k for k in kinds if k != 'blank')
    if not counts:
        return 'blank'
    if len(counts) == 1:
        return next(iter(counts))
    return 'mixed'


def analyse(path, text_pages=3):
    """Pages, page kinds and the first pages' text."""
    import fitz
    kinds, text = [], []
    with fitz.open(str(path)) as pdf:
        for index, page in enumerate(pdf):
            try:
                kinds.append(classify_page(page))
                if index < text_pages:
                    text.append(page.get_text('text') or '')
            except Exception as error:  # a damaged page is recorded, not fatal
                kinds.append('error:' + type(error).__name__)
    return dict(pages=len(kinds), page_kinds=dict(Counter(kinds)), mode=document_mode(
        [k for k in kinds if not k.startswith('error:')]), first_text='\n'.join(text))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def opaque_id(sha256):
    return 'd' + sha256[:12]


def collect_live(session):
    """Every evidence file a financial batch item or source document points at (read-only)."""
    from sqlalchemy import text
    files = {}
    rows = session.execute(text(
        "SELECT ef.id, ef.case_id, ef.sha256, ef.stored_path, ef.original_filename, ef.status, ef.is_duplicate, ef.size "
        "FROM evidence_files ef WHERE ef.id IN (SELECT file_id FROM financial_import_batch_items "
        "UNION SELECT evidence_file_id FROM financial_source_documents)")).all()
    for row in rows:
        files[row[0]] = dict(evidence_file_id=str(row[0]), case_id=str(row[1]), sha256=row[2], stored_path=row[3],
                             filename=row[4], evidence_status=row[5], is_duplicate=bool(row[6]), size=row[7],
                             batch_items=[], source_documents=[])
    for row in session.execute(text(
            "SELECT i.id, i.file_id, i.batch_id, i.status, i.statement_key, i.summary->>'institution', "
            "i.summary->>'period_start', i.summary->>'period_end' FROM financial_import_batch_items i")).all():
        if row[1] in files:
            files[row[1]]['batch_items'].append(dict(id=str(row[0]), batch_id=str(row[2]), status=row[3],
                statement_key=row[4], institution=row[5], period_start=row[6], period_end=row[7]))
    for row in session.execute(text(
            "SELECT d.id, d.evidence_file_id, d.status, d.institution_name, d.parser_name, d.page_count, "
            "d.document_type, d.sha256_at_ingestion, d.metadata->>'statement_id' FROM financial_source_documents d")).all():
        if row[1] in files:
            files[row[1]]['source_documents'].append(dict(id=str(row[0]), status=row[2], institution=row[3],
                parser=row[4], page_count=row[5], document_type=row[6], sha256_at_ingestion=row[7],
                statement_id=row[8]))
    return list(files.values())


def build(out, files, resolve_path, analyse_fn=analyse, copy=True):
    """Group live evidence files by bytes, verify, copy and analyse. Returns the inventory."""
    out = Path(out)
    docs = out / 'docs'
    docs.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    by_hash = defaultdict(list)
    for record in files:
        by_hash[record['sha256']].append(record)
    rows, problems = [], Counter()
    for sha, records in sorted(by_hash.items()):
        doc_id = opaque_id(sha)
        target = docs / f'{doc_id}.pdf'
        row = dict(id=doc_id, sha256=sha, cases=sorted({r['case_id'] for r in records}),
                   evidence_files=[{k: v for k, v in r.items() if k not in ('batch_items', 'source_documents')}
                                   for r in records],
                   batch_item_ids=[i['id'] for r in records for i in r['batch_items']],
                   batch_item_status=dict(Counter(i['status'] for r in records for i in r['batch_items'])),
                   source_document_status=dict(Counter(d['status'] for r in records for d in r['source_documents'])),
                   source_documents=[d for r in records for d in r['source_documents']],
                   batch_items=[i for r in records for i in r['batch_items']],
                   copies=len(records))
        hash_state = 'unavailable'
        if target.is_file() and sha256_file(target) == sha:
            hash_state = 'verified'
        else:
            for record in records:
                path = resolve_path(record['stored_path'])
                if path is None or not Path(path).is_file():
                    continue
                if sha256_file(path) != sha:
                    hash_state = 'original_changed'
                    continue
                if copy:
                    shutil.copyfile(path, target)
                    os.chmod(target, 0o600)
                hash_state = 'verified'
                break
        row['hash'] = hash_state
        problems[hash_state] += 1
        institution = next((d['institution'] for d in row['source_documents'] if d.get('institution')), None) or \
            next((i['institution'] for i in row['batch_items'] if i.get('institution')), None)
        if hash_state == 'verified':
            try:
                info = analyse_fn(target)
                row.update(pages=info['pages'], page_kinds=info['page_kinds'], mode=info['mode'],
                           family=guess_family(info['first_text'], institution))
            except Exception as error:
                row.update(pages=None, mode='unreadable', analyse_error=f'{type(error).__name__}: {error}'[:200],
                           family=guess_family('', institution))
        else:
            row.update(pages=None, mode='unavailable', family=guess_family('', institution))
        rows.append(row)
    inventory = dict(generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                     documents=rows, hash_states=dict(problems))
    (out / 'inventory.json').write_text(json.dumps(inventory, indent=1, sort_keys=True, default=str) + '\n')
    os.chmod(out / 'inventory.json', 0o600)
    return inventory


def counts(inventory):
    """Counts only (safe to share): documents by case index, family, mode, hash state."""
    docs = inventory['documents']
    cases = sorted({c for d in docs for c in d['cases']})
    case_label = {c: f'case{n + 1}({c[:8]})' for n, c in enumerate(cases)}
    return dict(documents=len(docs), evidence_files=sum(d['copies'] for d in docs),
                pages=sum(d.get('pages') or 0 for d in docs),
                by_case={case_label[c]: sum(c in d['cases'] for d in docs) for c in cases},
                by_family=dict(Counter(d['family'] for d in docs).most_common()),
                by_mode=dict(Counter(d['mode'] for d in docs).most_common()),
                hash=dict(Counter(d['hash'] for d in docs)),
                batch_item_status=dict(sum((Counter(d['batch_item_status']) for d in docs), Counter())),
                source_document_status=dict(sum((Counter(d['source_document_status']) for d in docs), Counter())))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True, help='private real-data directory')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(BACKEND))
    from postgres.session import _get_session_local
    from scripts.financial_reader_recovery_estimate import _resolver, read_only
    with _get_session_local()() as db:
        read_only(db)
        files = collect_live(db)
        db.rollback()
    inventory = build(args.out, files, _resolver())
    print(json.dumps(counts(inventory), indent=1))


if __name__ == '__main__':
    main()
