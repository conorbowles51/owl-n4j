"""Reader-failure alarm (fin-holes B, approved by Neil 2026-10-27).

OPDMD66, 2026-10-27: seven Truist consolidated statements, a layout no text reader knew, were read as
nothing (no payment, no period, no balance) while 249 lines stayed "unclassified". Because lines were
read, the queue did not call the reading empty: the statement waited for a person ("Needs you": enter a
balance), and nobody on our side was told. A statement whose reader got nothing out of pages that do
carry text is a reader problem, not a person's task.

``reader_gap(summary)``: a held statement whose text was read into lines (at least one unclassified line)
but which has no payment (complete or not), no period start or end, and no opening or closing balance,
and which is not set aside as a document that is not a payment statement or assigned without reading.
Such a statement is listed under "Waiting for a reader fix" with every action it has today, and is
reported to us: a durable register (JSON, case-independent, under the evidence data root) with case,
file, bank guess, layout fingerprint, pages with text, first and last seen, and how many files share the
fingerprint; a journal WARNING for every newly seen file; and the admin dashboard lists it.
Switch: LOUPE_FINANCIAL_READER_GAP_ALARM (default on); off, nothing is moved, registered or reported.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from services.financial.journal import journal

log = journal(__name__)

ENABLED = os.environ.get('LOUPE_FINANCIAL_READER_GAP_ALARM', '1').strip().lower() not in ('0', 'false', 'off', 'no', '')
SWEEP_SECONDS = 600
# Plain words, for the person (queue) and for the register.
SENTENCE = ("Loupe could not read this statement's layout yet: nothing was read from its pages. It has been reported "
            "so the reader can be taught this layout, and it is read again when that is released. You can still open "
            "it and act on it as before, including \"This isn't a statement\".")
FILE_MESSAGE = ("Loupe could not read this layout yet ({n} statement{s}): it has been reported so the reader can be "
                "taught it. Each statement can still be opened and acted on as before.")


def register_path():
    configured = os.environ.get('LOUPE_FINANCIAL_READER_GAPS_PATH')
    if configured:
        return Path(configured)
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT) / 'financial-reader-gaps.json'


def _balances_read(summary):
    for check in summary.get('checks') or []:
        if isinstance(check, dict) and check.get('kind') == 'closing_balance':
            return check.get('opening_minor') is not None or check.get('printed_minor') is not None
    return False


def reader_gap(summary, status='attention'):
    """True when the reader got nothing out of a held statement whose pages carry text (see module doc)."""
    if not ENABLED or status != 'attention':
        return False
    summary = summary or {}
    if summary.get('not_payment_statement') or summary.get('assignment_only') or summary.get('document_review'):
        return False
    if not summary.get('unclassified_count'):
        return False  # no line of text was read: an image-only scan, the page-image reader's work
    if summary.get('transaction_count') or summary.get('record_count') or summary.get('incomplete_count'):
        return False
    if summary.get('period_start') or summary.get('period_end'):
        return False
    return not _balances_read(summary)


# ---------------------------------------------------------------------------
# Layout fingerprint: the printed labels of the first page with text
# ---------------------------------------------------------------------------

LABEL_LINES = 5
MAX_LABEL_WORDS = 8


def _letters(line):
    return ' '.join(re.findall(r'[^\W\d_]+', line.lower()))


def label_lines(lines):
    """The first printed labels of a page: lines with no digit, 2 to 8 words, printed in mixed case (headings and
    labels, not a name or address block, which is printed in capitals, nor a notice in sentences). A page printing
    its labels in capitals only: its digit-free lines of 2 to 8 words after its first three lines."""
    def words(line):
        return re.findall(r'[^\W\d_]+', line)
    plain = [line for line in lines if not re.search(r'\d', line) and 2 <= len(words(line)) <= MAX_LABEL_WORDS]
    mixed = [line for line in plain if re.search(r'[a-z]', line) and re.search(r'[A-Z]', line)]
    chosen = mixed or [line for line in plain if line not in lines[:3]]
    return [_letters(line) for line in chosen[:LABEL_LINES]]


# The layout is named by its first two labels only: later labels carry the scan's misreadings and month-to-month
# notices (measured 2026-10-27: four Kapital statements share their first two labels, not their third).
FINGERPRINT_LABELS = 2


def fingerprint(lines):
    labels = label_lines(lines)
    if not labels:
        return '', []
    return hashlib.sha1('\n'.join(labels[:FINGERPRINT_LABELS]).encode()).hexdigest()[:12], labels


_DOMAIN = re.compile(r'\b([A-Za-z][A-Za-z-]{2,})\.com\b')


def bank_guess(summary, lines):
    """The bank the statement names: the reading's bank, else the web domain the first page prints."""
    named = str((summary or {}).get('institution') or '').strip()
    if named and len(named) <= 40 and not re.search(r'[().]', named):
        return named
    for line in lines:
        found = _DOMAIN.search(line)
        if found:
            return found.group(1).capitalize()
    return named[:40]


def page_text(db, case_id, file_id):
    """(pages with text, lines of the first page with text) from the file's stored text geometry."""
    from postgres.models.evidence import EvidenceTableGeometry
    from services.financial.candidate_sources import read_candidate_source
    geometry = db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == file_id)
                          .order_by(EvidenceTableGeometry.page_number)).all()
    pages, first = [], []
    for page in geometry:
        tables = len(page.payload or [])
        lines = []
        for index in range(tables):
            try:
                source = read_candidate_source(db, case_id=case_id, evidence_file_id=file_id,
                                               page_number=page.page_number, table_index=index)
            except Exception:  # noqa: BLE001 - a page whose text cannot be read counts as no text
                continue
            lines += [' | '.join(str(c.get('expected_text') or '') for c in row.get('cells') or [])
                      for row in source.get('rows') or []]
        if any(line.strip() for line in lines):
            pages.append(page.page_number)
            if not first:
                first = [line for line in lines if line.strip()][:60]
    return pages, first


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------

@contextmanager
def _locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_register(path=None):
    path = Path(path or register_path())
    try:
        with open(path) as handle:
            data = json.load(handle)
    except FileNotFoundError:
        data = {}
    data.setdefault('statements', {})
    data.setdefault('layouts', {})
    return data


def _write(path, data):
    temporary = Path(str(path) + '.tmp')
    with open(temporary, 'w') as handle:
        json.dump(data, handle, indent=1, sort_keys=True, default=str)
    os.replace(temporary, path)


def _key(file_id, statement_key):
    return '%s:%s' % (file_id, statement_key or '')


def record(found, *, now=None, path=None):
    """Bring the register up to date with the reader gaps held now. ``found``: {key: entry}. A statement no longer
    a gap keeps its record with ``resolved_at`` (nothing is deleted). Returns the newly seen entries."""
    path = Path(path or register_path())
    now = now or datetime.now(timezone.utc).isoformat()
    new = []
    with _locked(path):
        data = read_register(path)
        statements = data['statements']
        for key, entry in found.items():
            known = statements.get(key)
            if known is None or known.get('resolved_at'):
                statements[key] = dict(entry, first_seen=(known or {}).get('first_seen') or now, last_seen=now,
                                       times_seen=((known or {}).get('times_seen') or 0) + 1,
                                       **({'reopened_at': now} if known else {}))
                statements[key].pop('resolved_at', None)
                new.append(statements[key])
            else:
                statements[key] = dict(known, **entry, last_seen=now, times_seen=(known.get('times_seen') or 0) + 1)
        for key, known in statements.items():
            if key not in found and not known.get('resolved_at'):
                known['resolved_at'] = now
        layouts = {}
        for known in statements.values():
            mark = known.get('fingerprint') or 'unknown'
            layout = layouts.setdefault(mark, dict(fingerprint=mark, labels=known.get('labels') or [],
                                                  banks=set(), files=set(), held_files=set(), cases=set(),
                                                  first_seen=known.get('first_seen')))
            layout['banks'].add(known.get('bank') or '')
            layout['files'].add(known.get('file_id'))
            layout['cases'].add(known.get('case_id'))
            if not known.get('resolved_at'):
                layout['held_files'].add(known.get('file_id'))
            layout['first_seen'] = min(layout['first_seen'] or now, known.get('first_seen') or now)
        data['layouts'] = {mark: dict(layout, banks=sorted(b for b in layout['banks'] if b), files=len(layout['files']),
                                      held_files=len(layout['held_files']), cases=len(layout['cases']))
                           for mark, layout in layouts.items()}
        for known in statements.values():
            known['files_with_layout'] = data['layouts'][known.get('fingerprint') or 'unknown']['files']
        data['updated_at'] = now
        _write(path, data)
    return new


def scan(db, *, page_text_of=None, known=None):
    """{register key: entry} of every held statement (all cases) that is a reader gap. Reads only."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    page_text_of = page_text_of or page_text
    known = known or {}
    found = {}
    rows = db.execute(select(Item.id, Item.file_id, Item.statement_key, Item.summary, Item.status, Batch.case_id,
                             EvidenceFile.original_filename)
                      .join(Batch, Batch.id == Item.batch_id).join(EvidenceFile, EvidenceFile.id == Item.file_id)
                      .where(Item.status == 'attention', Batch.status != 'removed'))
    for item_id, file_id, statement_key, summary, status, case_id, filename in rows:
        if not reader_gap(summary, status):
            continue
        key = _key(file_id, statement_key)
        previous = known.get(key) or {}
        if previous.get('revision') == (summary or {}).get('revision') and previous.get('fingerprint') is not None \
                and not previous.get('resolved_at'):
            pages, lines, mark, labels = previous.get('text_pages') or [], None, previous['fingerprint'], previous.get('labels') or []
        else:
            pages, lines = page_text_of(db, case_id, file_id)
            mark, labels = fingerprint(lines)
        if not pages:
            continue  # no page carries text: not a text-layout gap
        found[key] = dict(case_id=str(case_id), file_id=str(file_id), statement_key=statement_key or '',
                          item_id=str(item_id), filename=filename or '', revision=(summary or {}).get('revision'),
                          bank=previous.get('bank') if lines is None else bank_guess(summary, lines),
                          fingerprint=mark, labels=labels, text_pages=pages, page_count=len(pages),
                          unclassified_lines=(summary or {}).get('unclassified_count') or 0)
    return found


def sweep(factory, *, path=None, page_text_of=None):
    """Background round: register the reader gaps held now; a journal WARNING for each newly seen one. Never raises."""
    if not ENABLED:
        return dict(held=0, new=0)
    try:
        known = read_register(path)['statements']
        with factory() as db:
            found = scan(db, page_text_of=page_text_of, known=known)
            db.rollback()
        new = record(found, path=path)
    except Exception:  # noqa: BLE001
        log.exception('Reader-gap round failed; the next round retries')
        return dict(held=0, new=0, failed=True)
    for entry in new:
        log.warning('READER GAP: case %s file %s "%s" statement %s: nothing read from %s page%s of text '
                    '(%s unclassified lines); bank %s, layout %s (%s file%s with this layout). Labels: %s',
                    entry['case_id'][:8], entry['file_id'][:8], entry['filename'], (entry['statement_key'] or '-')[:8],
                    entry['page_count'], '' if entry['page_count'] == 1 else 's', entry['unclassified_lines'],
                    entry['bank'] or '?', entry['fingerprint'] or '?', entry.get('files_with_layout'),
                    '' if entry.get('files_with_layout') == 1 else 's', ' / '.join(entry['labels']))
    if new:
        log.warning('Reader-gap round: %s held statement%s nothing was read from, %s newly seen',
                    len(found), '' if len(found) == 1 else 's', len(new))
    return dict(held=len(found), new=len(new))


def summary_for_admin(path=None):
    """The register for the admin dashboard: held gaps first, then resolved; layouts by held files."""
    data = read_register(path)
    statements = sorted(data['statements'].values(), key=lambda e: (bool(e.get('resolved_at')), e.get('first_seen') or ''))
    layouts = sorted(data['layouts'].values(), key=lambda l: (-(l.get('held_files') or 0), l.get('first_seen') or ''))
    return dict(updated_at=data.get('updated_at'), held=sum(1 for e in statements if not e.get('resolved_at')),
                statements=statements[:500], layouts=layouts)
